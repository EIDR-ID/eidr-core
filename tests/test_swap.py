"""eidr_core.swap (C9, 0.59.0): the decision and the walk, where a wrong answer
is a plausible row proposing the wrong record.

Checked before release on the live mirror against both copies it replaces:
21,548 sampled Edits, Manifestations and Clips (deep chains included) gave the
same ancestor as eidr-imdb's abstraction_ancestors and eidr-wikidata's
resolve_abstraction_ancestor, and the same decision and note as
plan_non_abstraction and split_non_abstraction.
"""
from __future__ import annotations

from eidr_core import swap

ABS, ED, ED2, MAN, ALIASED = (f"10.5240/000{i}-0000-0000-0000-0000-0" for i in range(1, 6))


class FakeMirror:
    def __init__(self, parents, core):
        self.parents, self.core = parents, core   # {child: (table, parent)}, {id: (type, status)}

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
        ids = params[0]
        if "FROM content_core" in sql:
            self.out = [(i, *self.db.core[i]) for i in ids if i in self.db.core]
        else:
            table = sql.split(" FROM ")[1].split()[0]
            self.out = [(i, p) for i, (t, p) in self.db.parents.items() if i in ids and t == table]

    def fetchall(self):
        return self.out


def test_the_walk_climbs_past_non_abstractions_and_requires_a_valid_ancestor():
    db = FakeMirror(
        parents={MAN: ("manifestations", ED2), ED2: ("edits", ED), ED: ("edits", ABS),
                 "10.5240/AAAA-0000-0000-0000-0000-0": ("edits", ALIASED)},
        core={ABS: ("Abstraction", "valid"), ED: ("Performance", "valid"),
              ED2: ("Performance", "valid"), ALIASED: ("Abstraction", "alias")})
    got = swap.abstraction_ancestors([MAN, ED, "10.5240/AAAA-0000-0000-0000-0000-0",
                                      "10.5240/BBBB-0000-0000-0000-0000-0"], conn=db)
    assert got[MAN] == ABS and got[ED] == ABS
    assert got["10.5240/AAAA-0000-0000-0000-0000-0"] is None      # aliased ancestor
    assert got["10.5240/BBBB-0000-0000-0000-0000-0"] is None      # no parent at all


def test_a_cycle_runs_out_of_depth_as_no_ancestor():
    db = FakeMirror(parents={ED: ("edits", ED2), ED2: ("edits", ED)},
                    core={ED: ("Performance", "valid"), ED2: ("Performance", "valid")})
    assert swap.abstraction_ancestors([ED], conn=db, max_depth=5) == {ED: None}


def test_the_decision_and_the_verified_exemption():
    types = {ABS: "Abstraction", ED: "Performance", MAN: "Performance", ED2: None}
    ancestors = {ED: ABS, MAN: None}
    plan = swap.plan_swaps([("tt1", ABS), ("tt1", ED), ("tt2", MAN), ("tt3", ED2), ("tt4", ED)],
                           types, ancestors, verified={("tt4", ED)})
    assert plan[("tt1", ABS)] == (swap.KEEP, None)
    assert plan[("tt1", ED)] == (swap.SWAP, ABS)         # never looks at the other claimant
    assert plan[("tt2", MAN)] == (swap.HELPDESK, None)
    assert plan[("tt3", ED2)] == (swap.KEEP, None)       # unknown type: kept
    assert plan[("tt4", ED)] == (swap.KEEP, None)        # a human approved it


def test_the_note_keeps_its_fixed_form():
    # BMR-Review's "Swapped original" control parses exactly this.
    assert swap.swap_note(ED, "Performance", ABS) == (
        f"SWAPPED: asserted {ED} (Performance) -> Abstraction ancestor {ABS}")
