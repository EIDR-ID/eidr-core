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

RETRY-AFTER (2026-09-30)
------------------------
A 429 or 503 is the endpoint telling the client how long to stay away.
Wikimedia's access rules, which its Terms of Use incorporate, require a
client to wait the ``Retry-After`` interval of a 429, and at least five
seconds when the header is absent; continuing inside the window risks a
temporary ban from the query service. Until 0.41.0 this loop ignored the
header and retried after ``backoff * 2**attempt + jitter`` -- about 2-3 s on
the first retry with the defaults (raised by eidr-metadata-sources from its
Wikidata licence review, 2026-09-30).

The chassis never sees a response, only the exception the provider raised,
so it reads the interval from the exception (``retry_after_seconds``):

* an explicit ``exc.retry_after`` (seconds), for a provider whose transport
  hides the headers -- set it when raising;
* else the ``Retry-After`` header of ``exc.headers`` (urllib's ``HTTPError``,
  which SPARQLWrapper re-raises unchanged for 429 and 503) or of
  ``exc.response.headers`` (requests), as seconds or an HTTP-date.

Before the next attempt on the SAME endpoint the loop sleeps
``max(Retry-After, the computed backoff)``. With no header on a 429 or 503
(status read from the exception, ``http_status``) it sleeps at least
``rate_limit_floor`` (5 s). An interval longer than ``max_retry_after`` is
not slept inside one call: the endpoint is left for the rest of the call.

The interval is a fact about the ENDPOINT, so it should outlive the call.
A caller that makes several calls in one operation passes one
``cooldowns`` dict to all of them -- the same shape as the outage memo --
and every interval is recorded there. A later call that reaches a cooling
endpoint skips it when another endpoint in its chain is usable, and
otherwise waits out the remainder (up to ``max_retry_after``) before the
first request: eidr-wikidata's ``pairs_batch`` re-probes WDQS at the start
of every batch, and that probe must not land inside the window. Failing
over to a DIFFERENT endpoint is never delayed. Without a memo, the wait is
still honoured inside the call.

Why a caller-owned memo and not a process-wide table (0.41.0 had one for
an hour): hidden module state leaks between independent callers -- a mocked
429 in one eidr-dq test kept the real WDQS endpoint "cooling" in the next
test, and the suite went red. Explicit state is the portfolio's convention
(``outage_endpoints``, the fact caches).

WHAT STAYS PER-PROVIDER
-----------------------
Transport construction (SPARQLWrapper vs urllib), authentication, query
building, response parsing, batch chunking, and inter-batch pacing. The
per-source clients keep their single homes (R13: one home per source).
"""
from __future__ import annotations

import email.utils
import logging
import random
import time
from collections.abc import Callable, Iterable, Sequence
from datetime import datetime, timezone
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
    "RATE_LIMIT_STATUSES",
    "DEFAULT_RATE_LIMIT_FLOOR",
    "DEFAULT_MAX_RETRY_AFTER",
    "http_status",
    "retry_after_seconds",
    "cooldown_remaining",
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
    """True if the exception string carries a known WDQS-outage signature.

    Matching is CASE-INSENSITIVE (2026-08-27, raised by eidr-dq). The two
    signatures above were transcribed from different positions in one
    observed message, so they disagree with each other about case —
    ``wdqs outage`` lower, ``Aggressively rate-limiting`` capitalised.
    Under case-sensitive matching, a `WDQS outage` at the start of a
    sentence, or a proxy that title-cases the body, misses both: the
    classifier falls through to the "429" substring check and the caller
    burns its whole retry budget per endpoint re-confirming an outage the
    memo exists to skip. The run still completes, just slower and with
    less coverage — a silent-miss shape, which is what this module is for.
    """
    s = str(exc).lower()
    return any(sig.lower() in s for sig in OUTAGE_SIGNATURES)


def is_bad_query_error(exc: Exception) -> bool:
    """True for query-syntax / bad-request errors that won't get better with
    retries. SPARQLWrapper raises ``QueryBadFormed`` for these; QLever
    additionally surfaces ``"Invalid SPARQL query"`` in its JSON error body.
    Non-retriable — but the NEXT endpoint may have a more permissive parser
    (WDQS predeclares wd/wdt/p/ps/pq; QLever requires the declarations), so
    the right verdict is NEXT_ENDPOINT, not FATAL.

    Also case-insensitive, for the same reason as ``is_outage_error``.
    eidr-dq raised this as a judgement call — ``QueryBadFormed`` is a
    Python class name and arguably case-sensitive, while the other two are
    endpoint prose. Folded anyway: lower-casing still matches the class
    name exactly, and no plausible message contains "querybadformed"
    meaning something else, so there is no false-positive to trade against
    the demonstrated false-negative.
    """
    s = str(exc).lower()
    if "querybadformed" in s:
        return True
    if "invalid sparql query" in s:
        return True
    return "bad request" in s and "sparql" in s


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


# ---------------------------------------------------------------------------
# Retry-After (see the module docstring, "RETRY-AFTER").
# ---------------------------------------------------------------------------

# The statuses by which a server says "slow down": 429 Too Many Requests and
# 503 Service Unavailable. Both may carry Retry-After (RFC 9110 section 10.2.3).
RATE_LIMIT_STATUSES = frozenset({429, 503})

# Wikimedia Robot Policy: with no Retry-After on a 429, "wait at least five
# seconds". Applied to 503 too: a server that is unavailable is not helped by
# a faster retry, and the cost of the floor is bounded by max_retries.
DEFAULT_RATE_LIMIT_FLOOR = 5.0

# The longest wait the loop will sleep inside ONE call. A larger Retry-After
# (WDQS has sent minutes during outages) leaves the endpoint for the rest of
# the call instead of blocking a batch job for the whole interval; the
# cooldown table still keeps later calls off it until the interval passes.
DEFAULT_MAX_RETRY_AFTER = 600.0


def http_status(exc: BaseException) -> int | None:
    """The HTTP status an exception carries, read from its attributes only.

    ``code`` (urllib ``HTTPError``), ``status`` / ``status_code`` (common
    provider exceptions, eidr-dq's ``_Transient``), ``response.status_code``
    (requests) or ``response["ResponseMetadata"]["HTTPStatusCode"]``
    (botocore). Never parsed from the message text: a digit run in echoed
    query text is not a status, and the text-based classification stays in
    ``classify_sparql_error`` where the order of checks guards it.
    """
    for attr in ("code", "status", "status_code"):
        val = getattr(exc, attr, None)
        if isinstance(val, int) and not isinstance(val, bool):
            return val
    resp = getattr(exc, "response", None)
    if resp is not None:
        val = getattr(resp, "status_code", None)
        if isinstance(val, int) and not isinstance(val, bool):
            return val
        if isinstance(resp, dict):
            val = (resp.get("ResponseMetadata") or {}).get("HTTPStatusCode")
            if isinstance(val, int) and not isinstance(val, bool):
                return val
    return None


def _parse_retry_after(raw: Any, now: datetime | None = None) -> float | None:
    """Seconds from a Retry-After value: delta-seconds or an HTTP-date."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return max(0.0, float(raw))
    text = str(raw).strip()
    if not text:
        return None
    try:
        return max(0.0, float(text))
    except ValueError:
        pass
    try:
        when = email.utils.parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        return None
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    ref = now or datetime.now(timezone.utc)
    return max(0.0, (when - ref).total_seconds())


def retry_after_seconds(exc: BaseException, now: datetime | None = None) -> float | None:
    """The Retry-After interval an exception carries, in seconds, or None.

    An explicit ``exc.retry_after`` wins (a provider that cannot expose
    headers sets it when raising); otherwise the header is read from
    ``exc.headers`` (urllib) or ``exc.response.headers`` (requests).
    ``now`` exists for tests of the HTTP-date form.
    """
    explicit = getattr(exc, "retry_after", None)
    if explicit is not None:
        return _parse_retry_after(explicit, now)
    headers = getattr(exc, "headers", None)
    if headers is None:
        headers = getattr(getattr(exc, "response", None), "headers", None)
    if headers is None:
        return None
    try:
        raw = headers.get("Retry-After")
    except AttributeError:
        return None
    return _parse_retry_after(raw, now)


def _note_cooldown(cooldowns: dict[str, float] | None, endpoint: str,
                   seconds: float) -> None:
    """Record that ``endpoint`` must not be called for ``seconds`` (memo only)."""
    if cooldowns is None or seconds <= 0:
        return
    until = time.monotonic() + seconds
    if until > cooldowns.get(endpoint, 0.0):
        cooldowns[endpoint] = until


def cooldown_remaining(cooldowns: dict[str, float] | None, endpoint: str) -> float:
    """Seconds still to wait before calling ``endpoint``, per a ``cooldowns`` memo.

    The memo maps endpoint -> ``time.monotonic()`` deadline; ``call_with_failover``
    fills it. An expired entry is removed. No memo, or no entry: 0.
    """
    if not cooldowns:
        return 0.0
    until = cooldowns.get(endpoint)
    if until is None:
        return 0.0
    left = until - time.monotonic()
    if left <= 0:
        cooldowns.pop(endpoint, None)
        return 0.0
    return left


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
    rate_limit_floor: float = DEFAULT_RATE_LIMIT_FLOOR,
    max_retry_after: float = DEFAULT_MAX_RETRY_AFTER,
    cooldowns: dict[str, float] | None = None,
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

    Retry-After (0.41.0; module docstring "RETRY-AFTER"): a RETRY verdict on
    an exception carrying a Retry-After interval, or a 429/503 status,
    makes the next attempt on that endpoint wait at least that interval
    (``rate_limit_floor`` when the header is absent); an interval over
    ``max_retry_after`` leaves the endpoint for this call. ``cooldowns`` is
    the cross-call memo (endpoint -> monotonic deadline): pass one dict to
    every call in an operation, as with ``outage_endpoints``, and a later
    call will not probe an endpoint inside its window.
    """
    endpoints = list(endpoints)
    skip_outage: set[str] = (
        outage_endpoints if outage_endpoints is not None else set()
    )

    last_exc: Exception | None = None
    label_suffix = f" ({chunk_label})" if chunk_label else ""

    for idx, endpoint in enumerate(endpoints):
        if endpoint in skip_outage:
            continue

        if cooldowns is not None:
            left = cooldown_remaining(cooldowns, endpoint)
            if left > 0:
                # Another endpoint can take the request now: use it rather
                # than wait. Only the last usable endpoint waits its window
                # out, and only up to max_retry_after.
                others = [e for e in endpoints[idx + 1:]
                          if e not in skip_outage
                          and cooldown_remaining(cooldowns, e) <= 0]
                if others or left > max_retry_after:
                    log.warning(
                        "%s skipping %s%s: Retry-After window has %.1f s left",
                        op_label or "call", endpoint, label_suffix, left,
                    )
                    continue
                log.warning(
                    "%s waiting %.1f s for the Retry-After window on %s%s",
                    op_label or "call", left, endpoint, label_suffix,
                )
                time.sleep(left)

        # The wait owed before the NEXT attempt on this endpoint, from the
        # last Retry-After or rate-limit status; 0 when there was none.
        owed = 0.0
        for attempt_no in range(max_retries):
            if delay_seconds and delay_seconds > 0:
                time.sleep(delay_seconds)
            if attempt_no > 0:
                computed = backoff * (2 ** attempt_no) + random.uniform(0, jitter)
                time.sleep(max(computed, owed))

            try:
                result = attempt(endpoint)
            except Exception as exc:  # classified below; never re-raised here
                last_exc = exc
                first_line = str(exc).split("\n", 1)[0][:200]
                verdict = classify(exc)

                # Retry-After is recorded whatever the verdict: an outage 429
                # still tells later calls how long to stay away.
                ra = retry_after_seconds(exc)
                status = http_status(exc)
                if ra is not None:
                    owed = ra
                elif status in RATE_LIMIT_STATUSES:
                    owed = rate_limit_floor
                else:
                    owed = 0.0
                if owed > 0:
                    _note_cooldown(cooldowns, endpoint, owed)

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
                    if owed > max_retry_after:
                        log.warning(
                            "%s %s%s asked for a %.0f s wait (over %.0f s): "
                            "leaving it for this call",
                            op_label or "call", endpoint, label_suffix,
                            owed, max_retry_after,
                        )
                        break
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
