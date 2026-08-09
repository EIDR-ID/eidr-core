"""External data-source chassis — the fact-cache seam.

Extracted verbatim from eidr-dq ``src/dq/external/cache.py`` (register R13 /
Phase 3 item 9, 2026-08-06), which was explicitly written for extraction.

THE SEAM
--------
Source clients and identity crosswalks must never know what database, if any,
sits behind the cache. That single property is what decides whether this code
can be shared across the portfolio or stays welded to one program's schema.

So a crosswalk takes a ``FactCache``, never a connection. eidr-dq implements
it over ``dq_external_facts``; another consumer implements it over whatever it
has, over a plain dict, or over nothing at all (``NullFactCache``). Nothing in
this module imports a database driver, and nothing in it should ever need to.

TTL policy is deliberately the implementation's business, not the protocol's:
a caller asking for facts should not have to know how long a fetched fact
stays warm, or that error entries expire sooner than successful ones. An
implementation that keeps nothing is valid.

THE FACT-DICT CONTRACT
----------------------
Providers return, and caches store, normalized fact dicts::

    {
        "status": "found" | "not_found" | "error",
        "facts": {
            "runtime_minutes":         [float, ...],   # all known runtimes
            "episode_runtime_minutes": [float, ...],   # series episode durations
            "release_date":            "YYYY-MM-DD",   # earliest known
            "release_date_precision":  "day" | "month" | "year",
            "label":                   str,            # source's title/label
        },
        "error": str,        # present when status == "error"
    }

This is the same shape ``eidr_core.verify`` consumes — ``release_date_precision``
in particular is what lets a year-precision fact answer an exact-date question
with ``insufficient`` instead of a false ``mismatch``. Cache and verifier are
two halves of one contract; change the shape in both or neither.

ONE HOME PER SOURCE
-------------------
Per-source clients stay with their owning program until a genuine second
consumer appears; only the chassis is shared. Current homes:

* **Wikidata** — eidr-wikidata (``wikidata/api.py``, ``sparql.py``): the full
  client (entity fetch, episode expansion, endpoint-fallback chain).
  eidr-dq ALSO has a narrow one (``external/wikidata.py``: batched SPARQL for
  P2047 duration and P577 date only). That is a justified second
  implementation, not drift — eidr-dq's is stdlib-only by constraint ("no new
  dependencies on the DQ host"), which eidr-wikidata's SPARQLWrapper-based
  client cannot satisfy. See the register R13 note for the outage gap between
  them.
* **TMDb** — eidr-dq (``external/tmdb.py``).
* **IMDb** — planned (rate-managed, pre-configured library).

THE OTHER CHASSIS LEGS
----------------------
R13 scopes the chassis as cache + rate limit + retry/backoff + serialization +
secrets convention. Retry/backoff + endpoint failover landed 2026-08-09 in
``eidr_core.external.failover`` (extracted from eidr-wikidata's
``_query_endpoints``; re-exported here). The rate-limit leg is the
``delay_seconds`` pre-attempt pacing that travelled with it — a token-bucket
pacer waits for the planned IMDb client, its first real consumer. Secrets
convention lives in ``eidr_core.secrets_loader`` (R10); serialization is the
fact-dict contract above.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from .failover import (
    FATAL,
    NEXT_ENDPOINT,
    OUTAGE,
    RETRY,
    call_with_failover,
    classify_sparql_error,
    endpoint_chain,
)

__all__ = [
    "FactCache", "NullFactCache", "DictFactCache", "Key", "Entry",
    # failover chassis (canonical home: eidr_core.external.failover)
    "RETRY", "NEXT_ENDPOINT", "OUTAGE", "FATAL",
    "call_with_failover", "classify_sparql_error", "endpoint_chain",
]

Key = tuple[str, str]          # (source, external_id)
Entry = dict                   # {"status": str, "facts": dict}


@runtime_checkable
class FactCache(Protocol):
    """A batch-oriented store for fetched external facts."""

    def load(self, keys: list[Key], *, refresh: bool = False) -> dict[Key, Entry]:
        """Return the live (non-expired) entries among keys.

        Missing and expired keys are simply absent from the result; the
        caller treats absence as "fetch it". When refresh is true the
        implementation must return nothing, forcing a refetch.
        """
        ...

    def store(self, results: dict[Key, Entry]) -> None:
        """Persist entries, overwriting any existing entry for a key."""
        ...


class NullFactCache:
    """A cache that stores nothing and returns nothing.

    Useful for tests, for one-shot tools, and for a consumer that has no
    persistence and simply wants to fetch every time.
    """

    def load(self, keys: list[Key], *, refresh: bool = False) -> dict[Key, Entry]:
        return {}

    def store(self, results: dict[Key, Entry]) -> None:
        return None


class DictFactCache:
    """An in-memory cache with no expiry. For tests and short-lived runs."""

    def __init__(self, initial: dict[Key, Entry] | None = None) -> None:
        self._d: dict[Key, Entry] = dict(initial or {})

    def load(self, keys: list[Key], *, refresh: bool = False) -> dict[Key, Entry]:
        if refresh:
            return {}
        return {k: self._d[k] for k in keys if k in self._d}

    def store(self, results: dict[Key, Entry]) -> None:
        self._d.update(results)
