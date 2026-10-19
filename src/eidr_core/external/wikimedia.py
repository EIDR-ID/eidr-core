"""Wikimedia's access rules for an unauthenticated client, once (C8, part 1).

eidr-metadata-sources' Wikidata integration package (2026-10-17, section
3.8) found the same rules written three times: eidr-wikidata
(``wikidata/etiquette.py``, ``api.py`` ``_http_json`` / ``_get_retry``),
eidr-dq (``external/wikidata.py``) and BMR-Review (``verify.py``
``WikidataVerifier._api``). This module is the Action API half, extracted
from eidr-wikidata's, which already ran on eidr-core's ``RequestPacer`` and
``call_with_failover``:

* AC1, a User-Agent naming the program with a way to reach EIDR
  (``user_agent``);
* AC2 and AC9, one request in flight for ALL of EIDR's programs, at most
  200 a minute, 5 s after a request that took over 1 s
  (``action_api_pacer``: a ``RequestPacer`` on the machine-wide scope
  ``ACTION_API_SCOPE``, 0.61.0);
* AC3, ``Retry-After`` on 429/503, 5 s without one, and the next request
  waits too (``back_off``);
* AC4, gzip, and ``maxlag`` with a lag refusal treated as a wait.

SPARQL (0.65.0): ``WDQS_ENDPOINT`` first; QLever's Wikidata endpoint was
cleared on 2026-10-18 (eidr-metadata-sources OD-49) as a FALLBACK only, on
conditions QAC1-QAC6: used only after WDQS fails for that request, never
primary and never for scheduled or bulk work; the ``/api/wikidata`` endpoint
only; Wikidata's triples only; one request at a time at least 1 s apart for
every caller (``sparql_pacer`` on the machine-wide ``SPARQL_SCOPE``, the
scope name eidr-wikidata chose); its values are Wikidata's. ``SPARQL_CHAIN``
is that order. The entity mapping is ``external.wikidata``.

SPARQL transport (0.66.0, C8 part 3), extracted from eidr-dq
``external/wikidata.py``, the portable stdlib client: ``sparql_request``
picks GET or POST per host (QLever answers POST with a 308 and serves GET;
WDQS takes POST, safer for a long VALUES clause), asks for gzip and decodes
it; ``classify_sparql_http`` reads urllib's structure after the shared
outage signatures; ``sparql_select`` runs one query across the chain under
the pacer and returns the endpoint that answered, so a caller can record
which values QLever served (eidr-metadata-sources' design ask, OD-49).
Queries must carry ``SPARQL_PREFIXES``: QLever does not predeclare them.
"""
from __future__ import annotations

import gzip
import json
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from typing import Any

from eidr_core.external.failover import (
    FATAL,
    NEXT_ENDPOINT,
    OUTAGE,
    RETRY,
    RequestPacer,
    call_with_failover,
    classify_sparql_error,
    http_status,
    retry_after_seconds,
)

__all__ = [
    "ACTION_API",
    "ACTION_API_SCOPE",
    "GZIP_HEADERS",
    "MAXLAG_SECONDS",
    "MIN_429_WAIT_SECONDS",
    "QLEVER_WIKIDATA_ENDPOINTS",
    "SPARQL_CHAIN",
    "SPARQL_ENDPOINT_METHODS",
    "SPARQL_MIN_INTERVAL",
    "SPARQL_PREFIXES",
    "SPARQL_SCOPE",
    "WDQS_ENDPOINT",
    "MaxLag",
    "action_api_json",
    "action_api_pacer",
    "classify_action_api",
    "classify_sparql_http",
    "sparql_pacer",
    "sparql_request",
    "sparql_select",
    "user_agent",
]

ACTION_API = "https://www.wikidata.org/w/api.php"
WDQS_ENDPOINT = "https://query.wikidata.org/sparql"
# QLever's Wikidata endpoint on both hosts (OD-49 covers both; QAC2: never
# another QLever dataset -- qlever.dev/imdb carries IMDb's data).
QLEVER_WIKIDATA_ENDPOINTS = ("https://qlever.cs.uni-freiburg.de/api/wikidata",
                             "https://qlever.dev/api/wikidata")
# The SPARQL chain for call_with_failover: WDQS, then QLever only when WDQS
# fails for that request (QAC1). Never put QLever first or use it for bulk.
SPARQL_CHAIN = (WDQS_ENDPOINT, QLEVER_WIKIDATA_ENDPOINTS[0])
# QAC4: one SPARQL request at a time, at least 1 s apart, for every caller.
SPARQL_SCOPE = "wikidata-sparql"
SPARQL_MIN_INTERVAL = 1.0

# Transport per endpoint HOST (eidr-dq, 2026-09-23): QLever 308-redirects a
# POST and serves GET; WDQS takes POST. Unlisted hosts get POST.
SPARQL_ENDPOINT_METHODS: dict[str, str] = {
    "query.wikidata.org": "POST",
    "qlever.dev": "GET",
    "qlever.cs.uni-freiburg.de": "GET",
}

# WDQS predeclares these and QLever does not; a query relying on
# predeclaration is "Invalid SPARQL" on the fallback, so prepend them.
SPARQL_PREFIXES = """PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX p: <http://www.wikidata.org/prop/>
PREFIX ps: <http://www.wikidata.org/prop/statement/>
PREFIX pq: <http://www.wikidata.org/prop/qualifier/>
PREFIX psv: <http://www.wikidata.org/prop/statement/value/>
PREFIX wikibase: <http://wikiba.se/ontology#>
PREFIX schema: <http://schema.org/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
"""

_TRANSIENT_HTTP = (429, 500, 502, 503, 504)
_NEXT_ENDPOINT_HTTP = (400, 414)   # this host will not serve it; another may
_FATAL_HTTP = (401, 403)           # no endpoint in the chain will help

# The machine-wide pacer scope every EIDR Action API client uses (AC9:
# EIDR counts as one operator). One name, so eidr-wikidata and BMR-Review
# cannot drift apart on it.
ACTION_API_SCOPE = "wikimedia-action-api"

GZIP_HEADERS = {"Accept-Encoding": "gzip"}
MAXLAG_SECONDS = 5                 # API:Etiquette, non-interactive requests
MIN_429_WAIT_SECONDS = 5.0         # Robot Policy: no Retry-After -> at least 5 s

_CONTACT = re.compile(r"(\S+@\S+\.\S+)|(https?://\S+)")


def user_agent(program: str, version: str, contact: str) -> str:
    """``"<program>/<version> (<contact>)"``. AC1: the contact must be an
    email address or a full URL, and never a browser's User-Agent; one per
    program (AC9), so build it once per program, not per call."""
    if not (program or "").strip() or not (version or "").strip():
        raise ValueError("user_agent needs a program name and a version")
    if not _CONTACT.fullmatch((contact or "").strip()):
        raise ValueError(f"user_agent contact must be an email address or a full URL: {contact!r}")
    return f"{program.strip()}/{version.strip()} ({contact.strip()})"


def action_api_pacer(min_interval: float = 0.3, *,
                     scope_dir: str | None = None) -> RequestPacer:
    """A pacer on the machine-wide Action API scope: one request in flight
    across every EIDR program, 0.3 s apart (200 a minute), 5 s after a slow
    one. Every pacer built here shares one state, so building several is
    harmless."""
    return RequestPacer(max(0.3, float(min_interval)), slow_threshold=1.0,
                        slow_pause=5.0, max_concurrent=1,
                        shared_scope=ACTION_API_SCOPE, scope_dir=scope_dir)


def sparql_pacer(*, scope_dir: str | None = None) -> RequestPacer:
    """A pacer on the machine-wide SPARQL scope: one request in flight, at
    least 1 s between starts (QLever's QAC4; it keeps WDQS well inside AC5
    too). No slow-request pause: that is an Action API rule, and a SPARQL
    query legitimately runs for tens of seconds. Extracted from eidr-wikidata
    ``etiquette.sparql_pacer``; same scope name and numbers."""
    return RequestPacer(SPARQL_MIN_INTERVAL, slow_pause=0.0, max_concurrent=1,
                        shared_scope=SPARQL_SCOPE, scope_dir=scope_dir)


class MaxLag(Exception):
    """The API refused the request because its replicas are lagged.
    ``retry_after`` is the attribute ``failover.retry_after_seconds`` reads,
    so ``call_with_failover`` honours it."""

    def __init__(self, retry_after: float) -> None:
        super().__init__(f"maxlag (retry after {retry_after:.0f}s)")
        self.retry_after = retry_after


def classify_action_api(exc: Exception) -> str:
    """Retry what is transient (maxlag, 429, 5xx, a network error or a
    timeout); anything else, such as a 400 for a bad request, stops."""
    if isinstance(exc, MaxLag):
        return RETRY
    if isinstance(exc, urllib.error.HTTPError):
        return RETRY if http_status(exc) in (429, 500, 502, 503, 504) else FATAL
    if isinstance(exc, (urllib.error.URLError, TimeoutError, OSError)):
        return RETRY
    return FATAL


def _one_request(url: str, ua: str, timeout: float, pacer: RequestPacer,
                 opener: Callable[..., Any]) -> dict:
    """ONE paced request: a slot, the pace, the request, its duration
    recorded, gzip decoded, and a maxlag refusal raised as ``MaxLag``."""
    req = urllib.request.Request(
        url, headers={"User-Agent": ua, "Accept": "application/json", **GZIP_HEADERS})
    with pacer.request(), opener(req, timeout=timeout) as resp:
        raw = resp.read()
        encoding = (resp.headers.get("Content-Encoding") or "").lower()
        retry_after = resp.headers.get("Retry-After")
    if encoding == "gzip":
        raw = gzip.decompress(raw)
    data = json.loads(raw.decode("utf-8", errors="replace"))
    err = data.get("error") if isinstance(data, dict) else None
    if isinstance(err, dict) and err.get("code") == "maxlag":
        try:
            wait = float(retry_after) if retry_after is not None else MAXLAG_SECONDS
        except (TypeError, ValueError):
            wait = float(MAXLAG_SECONDS)
        raise MaxLag(wait)
    return data


def action_api_json(params: Mapping[str, Any], *, user_agent: str, pacer: RequestPacer,
                    timeout: float = 30.0, attempts: int = 5, backoff: float = 1.0,
                    endpoint: str = ACTION_API,
                    opener: Callable[..., Any] | None = None,
                    op_label: str = "action-api") -> dict:
    """One Action API request under the rules, with retries.

    ``format=json`` and ``maxlag`` are added to ``params``. Retries go through
    ``call_with_failover``, which honours ``Retry-After`` (5 s floor without
    one) and a maxlag answer's interval; ``pacer.back_off`` makes the NEXT
    request wait as well, whichever program sends it. Raises the last error
    when every attempt fails. ``opener`` defaults to ``urllib.request.urlopen``
    looked up at CALL time (0.65.0), so a test that patches
    ``urllib.request.urlopen`` reaches it (eidr-wikidata noticed the
    import-time default did not).
    """
    open_url = opener if opener is not None else urllib.request.urlopen
    query = {**params, "format": "json", "maxlag": str(MAXLAG_SECONDS)}
    url = endpoint + "?" + urllib.parse.urlencode(query)

    def attempt(u: str) -> dict:
        try:
            return _one_request(u, user_agent, timeout, pacer, open_url)
        except Exception as exc:
            ra = retry_after_seconds(exc)
            if ra is None and http_status(exc) in (429, 503):
                ra = MIN_429_WAIT_SECONDS
            if ra:
                pacer.back_off(ra)
            raise

    data, _used, exc = call_with_failover(
        [url], attempt, classify_action_api, max_retries=max(1, attempts),
        backoff=backoff, rate_limit_floor=MIN_429_WAIT_SECONDS, op_label=op_label)
    if data is None:
        raise exc if exc is not None else RuntimeError("Action API request failed")
    return data


def classify_sparql_http(exc: Exception) -> str:
    """Retry, next endpoint, outage or stop, for a urllib SPARQL failure.

    The shared outage signatures win first (an outage message can contain
    "429", and treating it as transient burns the retry budget re-confirming
    a known outage); then urllib's status: 429/5xx retry, 400/414 try the
    next endpoint, 401/403 stop; a transport failure (DNS, reset, TLS,
    timeout) retries; anything unnamed takes the shared default. Extracted
    from eidr-dq ``_classify_wdqs_error``.
    """
    if classify_sparql_error(exc) == OUTAGE:
        return OUTAGE
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code in _TRANSIENT_HTTP:
            return RETRY
        if exc.code in _FATAL_HTTP:
            return FATAL
        return NEXT_ENDPOINT
    if isinstance(exc, (urllib.error.URLError, socket.timeout, TimeoutError)):
        return RETRY
    return classify_sparql_error(exc)


def sparql_request(endpoint: str, query: str, *, user_agent: str, timeout: float = 60.0,
                   opener: Callable[..., Any] | None = None) -> dict:
    """One SPARQL request, GET or POST by host, gzip asked for and decoded.
    Raises on a ``null`` body: ``call_with_failover`` reserves None."""
    headers = {"User-Agent": user_agent, "Accept": "application/sparql-results+json",
               **GZIP_HEADERS}
    host = (urllib.parse.urlsplit(endpoint).hostname or "").lower()
    if SPARQL_ENDPOINT_METHODS.get(host, "POST") == "GET":
        req = urllib.request.Request(endpoint + "?" + urllib.parse.urlencode({"query": query}),
                                     headers=headers, method="GET")
    else:
        data = urllib.parse.urlencode({"query": query, "format": "json"}).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        req = urllib.request.Request(endpoint, data=data, headers=headers, method="POST")
    open_url = opener if opener is not None else urllib.request.urlopen
    with open_url(req, timeout=timeout) as resp:
        raw = resp.read()
        if (resp.headers.get("Content-Encoding") or "").strip().lower() in ("gzip", "x-gzip"):
            raw = gzip.decompress(raw)
    payload = json.loads(raw.decode("utf-8"))
    if payload is None:
        raise ValueError("SPARQL endpoint returned a null JSON body")
    return payload


def sparql_select(query: str, *, user_agent: str, pacer: RequestPacer | None = None,
                  chain: tuple[str, ...] | list[str] = SPARQL_CHAIN, timeout: float = 60.0,
                  max_retries: int = 3, outage_endpoints: set[str] | None = None,
                  cooldowns: dict[str, float] | None = None, op_label: str = "sparql",
                  opener: Callable[..., Any] | None = None
                  ) -> tuple[list[dict], str | None]:
    """Run one SELECT across the chain: ``(bindings, endpoint_used)``.

    Every attempt goes through ``pacer`` (default: a new ``sparql_pacer()``,
    the machine-wide one), so QLever's one-at-a-time, 1-s rule holds for every
    caller. ``endpoint_used`` says which endpoint answered: record it when
    QLever did. ``outage_endpoints`` and ``cooldowns`` are the cross-call
    memos of ``call_with_failover``. Returns ``([], None)`` when the whole
    chain fails, so a batch loop can skip one batch and carry on.
    """
    pace = pacer if pacer is not None else sparql_pacer()

    def attempt(endpoint: str) -> dict:
        with pace.request():
            return sparql_request(endpoint, query, user_agent=user_agent,
                                  timeout=timeout, opener=opener)

    payload, used, _exc = call_with_failover(
        list(chain), attempt, classify_sparql_http, max_retries=max_retries,
        outage_endpoints=outage_endpoints, cooldowns=cooldowns, op_label=op_label)
    if payload is None:
        return [], None
    return list((payload.get("results") or {}).get("bindings") or []), used
