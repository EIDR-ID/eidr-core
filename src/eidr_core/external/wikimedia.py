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

AC8 for SPARQL: ``WDQS_ENDPOINT`` is the one default; QLever is not cleared
(eidr-metadata-sources, ``qlever-wikidata`` UNREVIEWED), so nothing here
names it. The entity mapping (C8 part 2) comes next.
"""
from __future__ import annotations

import gzip
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from typing import Any

from eidr_core.external.failover import (
    FATAL,
    RETRY,
    RequestPacer,
    call_with_failover,
    http_status,
    retry_after_seconds,
)

__all__ = [
    "ACTION_API",
    "ACTION_API_SCOPE",
    "GZIP_HEADERS",
    "MAXLAG_SECONDS",
    "MIN_429_WAIT_SECONDS",
    "WDQS_ENDPOINT",
    "MaxLag",
    "action_api_json",
    "action_api_pacer",
    "classify_action_api",
    "user_agent",
]

ACTION_API = "https://www.wikidata.org/w/api.php"
WDQS_ENDPOINT = "https://query.wikidata.org/sparql"

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
                    opener: Callable[..., Any] = urllib.request.urlopen,
                    op_label: str = "action-api") -> dict:
    """One Action API request under the rules, with retries.

    ``format=json`` and ``maxlag`` are added to ``params``. Retries go through
    ``call_with_failover``, which honours ``Retry-After`` (5 s floor without
    one) and a maxlag answer's interval; ``pacer.back_off`` makes the NEXT
    request wait as well, whichever program sends it. Raises the last error
    when every attempt fails.
    """
    query = {**params, "format": "json", "maxlag": str(MAXLAG_SECONDS)}
    url = endpoint + "?" + urllib.parse.urlencode(query)

    def attempt(u: str) -> dict:
        try:
            return _one_request(u, user_agent, timeout, pacer, opener)
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
