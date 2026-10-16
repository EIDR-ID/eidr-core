"""Registry lookups against the mirror: alias chains, live status, who claims a
source ID, and the seasons under a series (reconciliation component C1).

Ruled in eidr-core-ops ``PHASE2-3-INTERFACES-2026-10-15.md``. The pieces are
extracted, not written fresh:

* ``live_status`` is eidr-imdb's ``sheet.live_statuses`` (2026-09-13): the
  stored status of a pulled record goes stale at about one merge every two
  days, so a batch re-reads it from the mirror at build time.
* ``resolve_aliases`` merges the portfolio's three private alias followers:
  eidr-wikidata's ``MirrorClient.resolve_alias_chain`` (breadth-first, a
  cycle and the tombstone mean "unusable"), its ``pair_validator``
  recursion, and BMRtoAltID's (now ``altid_audit.MirrorClient``: capped,
  cycle-guarded). They differed in what they reported, not in what they
  followed: the mirror has only two statuses, ``valid`` (no target) and
  ``alias`` (a target), so "has a target" and "status is alias" pick the same
  rows (measured 2026-10-15: 3,609,737 valid, 50,902 alias, nothing else).
  What none of them reported together is WHY a chain stopped, so
  ``AliasResult.outcome`` says it.
* ``claimants`` is the identity lookup ``altid_audit`` uses (the partial
  index's predicate verbatim), with each claimant's status and alias
  resolution attached, and it never chooses one (eidr-imdb's case 1, *The
  Smurfs*: two Series records claim one IMDb ID; the caller decides).
* ``seasons_under`` is the lookup eidr-imdb measured R9 with (2026-10-14:
  ``seasons.sequence_number`` under the series' ``parent_id``): before a
  Season row is manufactured, the season is looked up under its series.

``conn`` is a DB-API connection the caller opened; eidr-core declares no
driver. Rows may come back as tuples or as dicts (eidr-wikidata's pool uses a
dict row factory); both are read.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any, NamedTuple

from eidr_core.ids import TOMBSTONE_ID

__all__ = [
    "OUTCOMES",
    "AliasResult",
    "Claimant",
    "claimants",
    "claimants_of",
    "live_status",
    "resolve_alias",
    "resolve_aliases",
    "seasons_under",
]

# Why an alias chain stopped where it did.
#   live        -- it ended at a record that is not an alias (the ID itself
#                  when it is not one): usable.
#   tombstoned  -- it ended at ids.TOMBSTONE_ID: the record was deleted.
#   cycle       -- it came back to an ID already on the chain.
#   missing     -- an ID on the chain (the start, or a target) has no
#                  content_core row at all.
#   exceeded    -- still moving after max_depth hops.
# Only "live" names a record to write to or point at.
OUTCOMES = ("live", "tombstoned", "cycle", "missing", "exceeded")


class AliasResult(NamedTuple):
    """Where an EIDR ID points, the IDs on the way, and why it stopped.

    ``chain`` starts with the ID asked about and ends with ``target``; it has
    one element when the ID is not an alias. ``target`` is where the chain
    stopped, whatever the outcome; only ``outcome == "live"`` makes it usable.
    """

    target: str
    chain: tuple[str, ...]
    outcome: str

    @property
    def usable(self) -> bool:
        return self.outcome == "live"


class Claimant(NamedTuple):
    """A record carrying a source ID as an identity Alt ID."""

    eidr_id: str
    status: str | None
    alias: AliasResult


def _rows(conn, sql: str, params: tuple) -> list[tuple[Any, ...]]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return [tuple(r.values()) if isinstance(r, dict) else tuple(r)
                for r in cur.fetchall()]


def live_status(ids: Iterable[str], *, conn) -> dict[str, str | None]:
    """The mirror's ``status`` for each ID it holds, read now.

    An ID the mirror does not hold is absent from the result; a NULL status
    comes back as None. One query.
    """
    wanted = list(dict.fromkeys(i for i in ids if i))
    if not wanted:
        return {}
    return dict(_rows(conn, "SELECT content_id, status FROM content_core "
                            "WHERE content_id = ANY(%s)", (wanted,)))


def resolve_aliases(ids: Iterable[str], *, conn,
                    max_depth: int = 10) -> dict[str, AliasResult]:
    """Follow each ID's alias chain, one query per LEVEL, not per ID.

    Chains really are chains (203 aliases point at an alias, measured
    2026-10-15), so one hop is not enough; ``max_depth`` caps the walk.
    """
    starts = list(dict.fromkeys(i for i in ids if i))
    if not starts:
        return {}
    present: set[str] = set()
    targets: dict[str, str] = {}
    frontier = starts
    # Level 0 asks about the starts themselves, so existence comes for free;
    # each later level asks only about targets not seen yet. One more level
    # than max_depth is read so a chain that is still moving can be told
    # apart from one that ends exactly at the cap.
    for _ in range(max_depth + 1):
        rows = _rows(conn, "SELECT content_id, target_id FROM content_core "
                           "WHERE content_id = ANY(%s)", (sorted(set(frontier)),))
        nxt = []
        for cid, tid in rows:
            present.add(cid)
            if tid and tid != cid:
                targets[cid] = tid
                if tid not in present and tid not in targets:
                    nxt.append(tid)
        if not nxt:
            break
        frontier = nxt

    out: dict[str, AliasResult] = {}
    for start in starts:
        chain = [start]
        outcome = "live"
        while True:
            cur = chain[-1]
            if cur not in present:
                outcome = "missing"
                break
            nxt_id = targets.get(cur)
            if nxt_id is None:
                outcome = "tombstoned" if cur == TOMBSTONE_ID else "live"
                break
            if nxt_id in chain:
                outcome = "cycle"
                break
            if len(chain) > max_depth:
                outcome = "exceeded"
                break
            chain.append(nxt_id)
        out[start] = AliasResult(chain[-1], tuple(chain), outcome)
    return out


def resolve_alias(eidr_id: str, *, conn, max_depth: int = 10) -> AliasResult:
    """``resolve_aliases`` for one ID."""
    return resolve_aliases([eidr_id], conn=conn, max_depth=max_depth)[eidr_id]


def claimants_of(kinds: Sequence[tuple[str, str, str]], *, conn,
                 alt_id_table: str = "content_alternate_ids_self",
                 max_depth: int = 10) -> dict[tuple[str, str, str], list[Claimant]]:
    """Every identity claimant of each ``(alt_type, domain, value)``, batched.

    A blank domain matches only a blank one (register R8). Each list is
    sorted by EIDR ID and may hold several records: this never chooses. A
    kind nobody claims maps to ``[]``.
    """
    if alt_id_table not in ("content_alternate_ids_self", "content_alternate_ids"):
        raise ValueError(f"unknown alt id table {alt_id_table!r}")
    keys = list(dict.fromkeys(kinds))
    out: dict[tuple[str, str, str], list[Claimant]] = {k: [] for k in keys}
    if not keys:
        return out
    # The relation predicate is the mirror's partial index
    # idx_cais_type_domain_relnorm_altid VERBATIM (as altid_audit's lookup):
    # rewording it, even to altidtool_io.identity_relation_sql(), costs the
    # index on what can be millions of lookups. A blank domain is sent as ''
    # because that is how the mirror stores it (never NULL; see
    # altid_audit.MirrorClient.lookup_alt_ids, 0.57.0).
    rows = _rows(conn,
                 "SELECT k.t, k.d, k.v, a.content_id "
                 "FROM unnest(%s::text[], %s::text[], %s::text[]) AS k(t, d, v) "
                 f"JOIN {alt_id_table} a "  # noqa: S608
                 "  ON a.id_type = k.t AND a.alt_id = k.v "
                 " AND COALESCE(a.domain, '') = k.d "
                 "WHERE a.relation IS NULL OR a.relation = %s",
                 ([k[0] for k in keys], [k[1] or "" for k in keys],
                  [k[2] for k in keys], "IsSameAs"))
    found: dict[tuple[str, str, str], set[str]] = {}
    for t, d, v, cid in rows:
        found.setdefault((t, d or "", v), set()).add(cid)
    ids = sorted({c for s in found.values() for c in s})
    status = live_status(ids, conn=conn)
    alias = resolve_aliases(ids, conn=conn, max_depth=max_depth)
    for key, cids in found.items():
        if key in out:
            out[key] = [Claimant(c, status.get(c), alias[c]) for c in sorted(cids)]
    return out


def claimants(alt_type: str, value: str, *, conn, domain: str | None = None,
              alt_id_table: str = "content_alternate_ids_self") -> list[Claimant]:
    """Every live-or-not record carrying ``value`` as an identity Alt ID of
    this Kind, with its status and alias resolution. Never chooses one: a
    caller that cannot point at a single parent points at the in-sheet row
    instead (eidr-imdb's case 1)."""
    key = (alt_type, domain or "", value)
    return claimants_of([key], conn=conn, alt_id_table=alt_id_table)[key]


def seasons_under(series_id: str, season_number: int, *, conn) -> list[str]:
    """The valid Season records numbered ``season_number`` under ``series_id``.

    R9's lookup-first step: before a Season row is manufactured, look the
    season up under its series. A list, sorted, because the registry can
    hold two (the same reason ``claimants`` never chooses). Aliased seasons
    are left out: pointing an Episode at a merged-away record is wrong.
    """
    rows = _rows(conn,
                 "SELECT s.content_id FROM seasons s "
                 "JOIN content_core c ON c.content_id = s.content_id "
                 "WHERE s.parent_id = %s AND s.sequence_number = %s "
                 "AND c.status = 'valid' ORDER BY s.content_id",
                 (series_id, int(season_number)))
    return [r[0] for r in rows]
