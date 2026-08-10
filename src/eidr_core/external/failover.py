"""Endpoint failover + retry/backoff — the remaining chassis legs of R13.

Extracted from eidr-wikidata ``src/eidr_wikidata/wikidata/sparql.py``
``_query_endpoints`` (register R13 / Phase 3 item 9 tail, 2026-08-09) — the
strongest of the portfolio's three retry loops, and the register-named seed.
The other two are weaker shapes of the same loop: eidr-dq
``external/wikidata.py`` (one retry, fixed backoff, single endpoint — the
R13 finding: a WDQS outage silently zeroes its verification coverage
because there is no fallback endpoint to walk to) and eidr-dq
``external/tmdb.py`` (same, plus a terminal auth verdict on HTTP 401).

THE SEAM
--------
The chassis owns the LOOP; the provider owns the TRANSPORT. A caller
supplies two callables:

* ``attempt(endpoint)`` — perform one request against one endpoint and
  return the parsed result. Raise on any failure. Must not return None:
  None is reserved as the chassis's own "every endpoint exhausted" signal
  in the result triple.
* ``classify(exc)`` — map an exception to one of the four verdicts below.
  Classification is transport-specific knowledge (SPARQLWrapper buries
  HTTP codes in exception text; urllib raises HTTPError with a ``.code``),
  so it stays with the caller — but the WALK ORDER each verdict triggers
  is chassis policy, and that policy is what this module shares.

VERDICTS
--------
* ``RETRY`` — transient (429/5xx-class): retry the SAME endpoint with
  exponential backoff + jitter, up to ``max_retries`` attempts.
* ``NEXT_ENDPOINT`` — this endpoint will not accept this request (e.g. a
  stricter SPARQL parser rejecting undeclared prefixes): move on
  immediately, without a memo — the endpoint may still serve other
  queries in the same run.
* ``OUTAGE`` — the endpoint is down for the whole workload: move on
  immediately AND record it in ``outage_endpoints``, so subsequent calls
  in the same multi-chunk operation skip it instead of burning their full
  retry budget re-confirming the same outage.
* ``FATAL`` — no endpoint will help (auth failure, malformed input): stop
  the walk entirely and surface the exception in the result triple. This
  verdict is the one generalization over the seed, needed to cover TMDb's
  401-aborts-the-run shape; the seed never needed it because SPARQL
  endpoints are unauthenticated.

Any unrecognized verdict string is treated as ``NEXT_ENDPOINT`` — the
seed's behavior for errors it could not name was "break to the next
endpoint", and a misspelled verdict degrading to fewer retries is safer
than it degrading to more.

THE RATE-LIMIT LEG
------------------
``delay_seconds`` is a pre-attempt sleep, applied before EVERY attempt
including the first — extracted as-is from the seed, where it implements
Wikidata's usage-guideline pacing. The portfolio's other rate-limit
convention (a fixed sleep BETWEEN batches: ``sleep_ms`` in both eidr-dq
providers) stays with the batch loops that own it, because it is
inter-request state the single-call chassis cannot see. A token-bucket
pacer would be a fresh implementation, not an extraction — deferred until
the planned rate-managed IMDb client actually needs one (R13 rule: a
piece moves here when its second consumer appears).

WHAT STAYS PER-PROVIDER
-----------------------
Transport construction (SPARQLWrapper vs urllib), authentication, query
building, response parsing, batch chunking, and inter-batch pacing. The
per-source clients keep their single homes (R13: one home per source).
"""
from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable, Iterable, Sequence
from typing import Any

__all__ = [
    "RETRY",
    "NEXT_ENDPOINT",
    "OUTAGE",
    "FATAL",
    "OUTAGE_SIGNATURES",
    "TRANSIENT_HTTP_MARKERS",
    "is_outage_error",
    "is_bad_query_error",
    "classify_sparql_error",
    "endpoint_chain",
    "call_with_failover",
]

log = logging.getLogger(__name__)

# Verdict constants. Plain strings, not an Enum, so a consumer's classify
# callable can be written without importing anything from this module
# (eidr-dq's hard constraint is "no new dependencies on the DQ host";
# string verdicts keep even the coupling surface minimal).
RETRY = "retry"
NEXT_ENDPOINT = "next-endpoint"
OUTAGE = "outage"
FATAL = "fatal"


# ---------------------------------------------------------------------------
# SPARQL error classification — shared by BOTH Wikidata consumers.
#
# These signatures live here, not per-provider, precisely because keeping
# them in sync IS the point of the extraction: eidr-dq's provider had no
# outage handling at all, which is the R13 coverage-loss finding. TMDb (and
# any future HTTP-status-shaped source) writes its own classify instead —
# its failure signals arrive as status codes, not exception text.
# ---------------------------------------------------------------------------

# Substring fragments that, when present in a SPARQL exception, mean the
# endpoint is rate-limiting the entire workload (not just our request).
# Observed verbatim in the 2026-05-09/10 WDQS outages ("Aggressively
# rate-limiting to 1 req / min - this rule was created during active wdqs
# outage").
OUTAGE_SIGNATURES = (
    "wdqs outage",
    "Aggressively rate-limiting",
)

# HTTP codes worth retrying on the same endpoint. The seed retried
# 429/502/503/504; eidr-dq's providers also retry 500. Union adopted on
# harmonization: a WDQS 500 is transient in practice, and the cost of a
# wrong RETRY is bounded by max_retries, while the cost of a wrong
# NEXT_ENDPOINT is losing a healthy endpoint. Substring matching against
# exception text is inherited from the seed (SPARQLWrapper offers nothing
# more structured); the false-positive hazard (a code digit appearing in
# echoed query text) is mitigated by classification order — outage and
# bad-query signatures are checked first.
TRANSIENT_HTTP_MARKERS = ("429", "500", "502", "503", "504")


def is_outage_error(exc: Exception) -> bool:
    """True if the exception string carries a known WDQS-outage signature."""
    s = str(exc)
    return any(sig in s for sig in OUTAGE_SIGNATURES)


def is_bad_query_error(exc: Exception) -> bool:
    """True for query-syntax / bad-request errors that won't get better with
    retries. SPARQLWrapper raises ``QueryBadFormed`` for these; QLever
    additionally surfaces ``"Invalid SPARQL query"`` in its JSON error body.
    Non-retriable — but the NEXT endpoint may have a more permissive parser
    (WDQS predeclares wd/wdt/p/ps/pq; QLever requires the declarations), so
    the right verdict is NEXT_ENDPOINT, not FATAL.
    """
    s = str(exc)
    if "QueryBadFormed" in s:
        return True
    if "Invalid SPARQL query" in s:
        return True
    return "Bad Request" in s and "SPARQL" in s


def classify_sparql_error(exc: Exception) -> str:
    """The seed's classification, in the seed's order.

    Order matters: an outage message can contain "429", so outage must win
    over transient; a bad-query echo can contain anything, so it is checked
    before the substring code scan.
    """
    if is_outage_error(exc):
        return OUTAGE
    if is_bad_query_error(exc):
        return NEXT_ENDPOINT
    s = str(exc)
    if any(code in s for code in TRANSIENT_HTTP_MARKERS):
        return RETRY
    # The seed's default for errors it could not name: break to the next
    # endpoint rather than burn the retry budget on an unknown failure.
    return NEXT_ENDPOINT


def endpoint_chain(
    primary: str | None, fallbacks: Iterable[str] | None = None
) -> list[str]:
    """Ordered, de-duplicated endpoint list: primary first, then fallbacks.

    Blank and duplicate entries are dropped (a config listing the primary
    again as a fallback must not make the walk visit it twice). Resolving
    WHICH endpoints to use (config, env, defaults) stays with the caller —
    this only owns the chain discipline.
    """
    chain: list[str] = []
    for ep in [primary, *(fallbacks or [])]:
        ep = (ep or "").strip()
        if ep and ep not in chain:
            chain.append(ep)
    return chain


def call_with_failover(
    endpoints: Sequence[str],
    attempt: Callable[[str], Any],
    classify: Callable[[Exception], str],
    *,
    max_retries: int = 5,
    backoff: float = 2.0,
    jitter: float = 0.5,
    delay_seconds: float = 0.0,
    outage_endpoints: set[str] | None = None,
    op_label: str = "",
    chunk_label: str = "",
) -> tuple[Any, str | None, Exception | None]:
    """Execute one operation across the endpoint chain with full
    fallback + retry semantics.

    Returns ``(result, endpoint_used, last_exception)``; ``result`` is None
    when every endpoint in the chain exhausted its budget (which is why
    ``attempt`` must never return None as a legitimate result).

    Per endpoint: up to ``max_retries`` attempts, sleeping
    ``backoff * 2**attempt + uniform(0, jitter)`` before each retry, plus
    ``delay_seconds`` before every attempt (the rate-limit leg). The
    ``classify`` verdict decides everything else — see the module
    docstring for the four verdicts and their walk semantics.

    ``outage_endpoints`` is the cross-call memo: pass the same set to every
    ``call_with_failover`` in a multi-chunk operation and an endpoint that
    hits an outage on chunk N is skipped for chunks N+1.. instead of
    re-confirming the outage at full retry cost each time.

    ``op_label`` / ``chunk_label`` tag the log lines so operators can see
    which operation succeeded or failed where.
    """
    endpoints = list(endpoints)
    skip_outage: set[str] = (
        outage_endpoints if outage_endpoints is not None else set()
    )

    last_exc: Exception | None = None
    label_suffix = f" ({chunk_label})" if chunk_label else ""

    for endpoint in endpoints:
        if endpoint in skip_outage:
            continue

        for attempt_no in range(max_retries):
            if delay_seconds and delay_seconds > 0:
                time.sleep(delay_seconds)
            if attempt_no > 0:
                time.sleep(backoff * (2 ** attempt_no) + random.uniform(0, jitter))

            try:
                result = attempt(endpoint)
            except Exception as exc:  # classified below; never re-raised here
                last_exc = exc
                first_line = str(exc).split("\n", 1)[0][:200]
                verdict = classify(exc)

                if verdict == FATAL:
                    log.warning(
                        "%s fatal error on %s%s: %s — aborting endpoint walk",
                        op_label or "call", endpoint, label_suffix, first_line,
                    )
                    return None, None, exc
                if verdict == OUTAGE:
                    log.warning(
                        "%s outage signature on %s%s: %s "
                        "— failing fast, switching to next endpoint",
                        op_label or "call", endpoint, label_suffix, first_line,
                    )
                    skip_outage.add(endpoint)
                    break
                if verdict == RETRY:
                    if attempt_no + 1 < max_retries:
                        log.warning(
                            "%s transient error on %s%s (attempt %d/%d): %s "
                            "— retrying",
                            op_label or "call", endpoint, label_suffix,
                            attempt_no + 1, max_retries, first_line,
                        )
                        continue
                    log.warning(
                        "%s transient error on %s%s exhausted %d attempts: %s",
                        op_label or "call", endpoint, label_suffix,
                        max_retries, first_line,
                    )
                    break
                # NEXT_ENDPOINT, and the safe default for unknown verdicts.
                log.warning(
                    "%s non-retriable error on %s%s: %s "
                    "— switching to next endpoint",
                    op_label or "call", endpoint, label_suffix, first_line,
                )
                break
            else:
                if endpoint != endpoints[0]:
                    log.info(
                        "%s%s succeeded on fallback endpoint %s",
                        op_label or "call", label_suffix, endpoint,
                    )
                return result, endpoint, None

    return None, None, last_exc
