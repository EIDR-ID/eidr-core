"""eidr_core.lookup (C1, 0.57.0): the answers that are wrong silently.

Before release it was checked on the live mirror against the code it
replaces: all 50,902 aliases, 2,000 valid records, the tombstone and a
missing ID gave the same answer as eidr-wikidata's resolve_alias_chain and
altid_audit's resolve_aliases, and live_status equalled eidr-imdb's
live_statuses on all of them. What is pinned here is what those callers
could not tell apart: WHY a chain stopped.
"""
from __future__ import annotations

import pytest

from eidr_core import lookup
from eidr_core.ids import TOMBSTONE_ID

A, B, C, D = (f"10.5240/000{i}-0000-0000-0000-0000-0" for i in range(1, 5))
S1, S2 = "10.5240/5555-0000-0000-0000-0000-1", "10.5240/5555-0000-0000-0000-0000-2"


class FakeMirror:
    """content_core, an Alt ID table and seasons, answering the four queries."""

    def __init__(self, core, alt_ids=(), seasons=(), dict_rows=False):
        self.core = core            # {content_id: (status, target_id)}
        self.alt_ids = list(alt_ids)  # (content_id, type, domain, value, relation)
        self.seasons = list(seasons)  # (content_id, parent_id, sequence_number)
        self.dict_rows = dict_rows
        self.queries = 0

    def cursor(self):
        return _Cursor(self)


class _Cursor:
    def __init__(self, db):
        self.db, self.out = db, []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params):
        db = self.db
        db.queries += 1
        if sql.startswith("SELECT content_id, status"):
            self.out = [(i, db.core[i][0]) for i in params[0] if i in db.core]
        elif sql.startswith("SELECT content_id, target_id"):
            self.out = [(i, db.core[i][1]) for i in params[0] if i in db.core]
        elif "unnest" in sql:
            want = set(zip(params[0], [d or "" for d in params[1]], params[2], strict=True))
            self.out = [(t, d or None, v, c) for c, t, d, v, r in db.alt_ids
                        if (t, d or "", v) in want and r in (None, "IsSameAs")]
        elif "FROM seasons" in sql:
            self.out = sorted((c,) for c, p, n in db.seasons
                              if p == params[0] and n == params[1] and db.core[c][0] == "valid")
        else:  # pragma: no cover
            raise AssertionError(sql)

    def fetchall(self):
        if self.db.dict_rows:
            return [dict(zip(("a", "b", "c", "d")[: len(r)], r, strict=True)) for r in self.out]
        return self.out


def test_every_outcome_is_told_apart():
    db = FakeMirror({A: ("alias", B), B: ("alias", C), C: ("valid", None),
                     D: ("alias", TOMBSTONE_ID), TOMBSTONE_ID: ("valid", None),
                     S1: ("alias", S2), S2: ("alias", S1),
                     "10.5240/DANG-0000-0000-0000-0000-0": ("alias", "10.5240/GONE")})
    r = lookup.resolve_aliases([A, C, D, TOMBSTONE_ID, S1, "10.5240/NOPE",
                                "10.5240/DANG-0000-0000-0000-0000-0"], conn=db)
    assert r[A] == lookup.AliasResult(C, (A, B, C), "live") and r[A].usable
    assert r[C] == lookup.AliasResult(C, (C,), "live")
    assert r[D].outcome == "tombstoned" and r[D].target == TOMBSTONE_ID and not r[D].usable
    assert r[TOMBSTONE_ID].outcome == "tombstoned"
    assert r[S1] == lookup.AliasResult(S2, (S1, S2), "cycle")
    assert r["10.5240/NOPE"].outcome == "missing"
    # A dangling alias (the mirror holds 8): the old followers returned the
    # missing target as if it were a record.
    assert r["10.5240/DANG-0000-0000-0000-0000-0"].outcome == "missing"


def test_the_depth_cap_is_exceeded_only_by_a_chain_still_moving():
    ids = [f"10.5240/{i:04d}-0000-0000-0000-0000-0" for i in range(13)]
    core = {ids[i]: ("alias", ids[i + 1]) for i in range(12)}
    core[ids[12]] = ("valid", None)
    db = FakeMirror(core)
    assert lookup.resolve_alias(ids[2], conn=db, max_depth=10).outcome == "live"
    over = lookup.resolve_alias(ids[0], conn=db, max_depth=10)
    assert over.outcome == "exceeded" and len(over.chain) == 11


def test_one_query_per_level_not_per_id():
    core = {f"10.5240/{i:04d}-0000-0000-0000-0000-0": ("valid", None) for i in range(500)}
    db = FakeMirror(core)
    lookup.resolve_aliases(list(core), conn=db)
    assert db.queries == 1


def test_claimants_never_chooses_and_carries_status_and_alias():
    db = FakeMirror({A: ("valid", None), B: ("alias", C), C: ("valid", None)},
                    alt_ids=[(B, "IMDB", None, "tt1", None), (A, "IMDB", None, "tt1", "IsSameAs"),
                             (C, "IMDB", None, "tt1", "IsDerivedFrom")])
    got = lookup.claimants("IMDB", "tt1", conn=db)
    assert [c.eidr_id for c in got] == [A, B]          # sorted; the non-identity row is not one
    assert got[1].status == "alias" and got[1].alias.target == C
    assert lookup.claimants("IMDB", "tt9", conn=db) == []
    with pytest.raises(ValueError):
        lookup.claimants_of([("IMDB", "", "tt1")], conn=db, alt_id_table="content_core")


def test_a_blank_domain_matches_only_a_null_one():
    db = FakeMirror({A: ("valid", None), B: ("valid", None)},
                    alt_ids=[(A, "Proprietary", "x.com", "1", None),
                             (B, "Proprietary", None, "1", None)])
    got = lookup.claimants_of([("Proprietary", "x.com", "1"), ("Proprietary", "", "1")], conn=db)
    assert [c.eidr_id for c in got[("Proprietary", "x.com", "1")]] == [A]
    assert [c.eidr_id for c in got[("Proprietary", "", "1")]] == [B]


def test_seasons_under_lists_only_valid_seasons():
    db = FakeMirror({S1: ("valid", None), S2: ("alias", S1), A: ("valid", None)},
                    seasons=[(S1, A, 2), (S2, A, 2), (B, A, 3)])
    assert lookup.seasons_under(A, 2, conn=db) == [S1]
    assert lookup.seasons_under(A, 7, conn=db) == []


def test_dict_rows_are_read_like_tuples():
    db = FakeMirror({A: ("alias", C), C: ("valid", None)}, dict_rows=True)
    assert lookup.resolve_alias(A, conn=db).target == C
    assert lookup.live_status([A], conn=db) == {A: "alias"}
