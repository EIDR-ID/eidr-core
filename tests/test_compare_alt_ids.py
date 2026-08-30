"""The common-Alt-ID definition, pinned.

A wrong answer here is SILENT and expensive: the `matches` count this
comparator returns drives the alt-ID bonus and ALT_CORROBORATION_STRONG_MIN,
which release both the unverified-alt-id Accept cap and the part-number cap.
So a spurious match does not merely nudge a score -- it can lift a pair into
Accept. That is why this surface gets local tests rather than relying on
consumers' conformance corpora alone.

The definition (operator ruling 2026-08-30): Kind (id_type + full domain) and
Value equal case-insensitively, AND the relation is identity -- missing,
null, empty, or IsSameAs. A Family ID is not an Alt ID.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pytest

pytest.importorskip("rapidfuzz")

from eidr_core.compare import cmp_alt_ids, set_params  # noqa: E402
from eidr_core.compare.spec import load_spec  # noqa: E402


@pytest.fixture(autouse=True)
def _params():
    """`nonlinear.accumulate` needs registered parameters to score a match.

    Uses the PACKAGED compare-spec rather than hand-made numbers, so these
    tests exercise the same tuning surface the consumers run against.
    """
    set_params(_SpecParams(load_spec()))


class _SpecParams:
    """Attribute view over the spec dict, which is what set_params expects."""

    def __init__(self, spec):
        params = spec.get("params", spec)
        self._p = {k.upper(): v for k, v in params.items()
                   if not isinstance(v, (dict, list))}

    def __getattr__(self, name):
        try:
            return self._p[name.upper()]
        except KeyError as exc:            # pragma: no cover - surfaced by tests
            raise AttributeError(name) from exc


@dataclass
class _Alt:
    value: str
    id_type: str | None = "Proprietary"
    domain: str | None = "themoviedb.org/movie"
    relation: str | None = None


@dataclass
class _Rec:
    alt_ids: list = field(default_factory=list)


def _cmp(a_alts, b_alts):
    return cmp_alt_ids(_Rec(alt_ids=a_alts), _Rec(alt_ids=b_alts))


# --- the identity relations -------------------------------------------------

@pytest.mark.parametrize("relation", [None, "", "   ", "IsSameAs", "issameas",
                                      "  IsSameAs  "])
def test_an_identity_relation_matches(relation):
    r = _cmp([_Alt("12345", relation=relation)], [_Alt("12345")])
    assert r.meta["matches"] == 1
    assert r.quality == 1.0


def test_values_compare_case_insensitively():
    r = _cmp([_Alt("tt00ABC")], [_Alt("tt00abc")])
    assert r.meta["matches"] == 1


# --- the defect this file was written for -----------------------------------

@pytest.mark.parametrize("relation", ["IsDerivedFrom", "IsPartOf",
                                      "Deprecated", "Other",
                                      "isderivedfrom"])
def test_a_non_identity_relation_is_not_a_match(relation):
    """Reported by BMR-Review 2026-08-30.

    `rel_ok` existed and was consulted ONLY in the conflict branch, so a
    shared Kind+Value scored 1.0 whatever the relation said. 58 of 62,646
    shared pairs across the four corpora -- but the relation vocabulary is
    not rare (Deprecated 145k, Other 35k), so exposure grows with any source
    that uses relations routinely.
    """
    r = _cmp([_Alt("12345", relation=relation)], [_Alt("12345")])
    assert r.meta["matches"] == 0, (
        f"relation {relation!r} names a different work; it is not identity "
        f"evidence"
    )
    assert r.quality is None


def test_a_non_identity_entry_does_not_poison_a_real_match():
    """The fix must not trade a false positive for a false NEGATIVE.

    Consulting the old per-SOURCE relation flag in the match branch would
    have done exactly that: one IsDerivedFrom entry would suppress every
    legitimate IsSameAs match under the same source. The relation is
    therefore filtered per ENTRY.
    """
    r = _cmp([_Alt("12345", relation="IsSameAs"),
              _Alt("99999", relation="IsDerivedFrom")],
             [_Alt("12345")])
    assert r.meta["matches"] == 1


def test_a_derived_id_cannot_manufacture_a_match_against_a_real_one():
    """The subtler case the per-source flag got wrong in the other direction.

    A holds X as its own identity and Y as a derived work; B holds Y as its
    identity. The shared value Y must NOT be a match -- and because both
    sides' remaining entries are identity relations that disagree, it is a
    conflict.
    """
    r = _cmp([_Alt("X", relation="IsSameAs"), _Alt("Y", relation="IsPartOf")],
             [_Alt("Y", relation="IsSameAs")])
    assert r.meta["matches"] == 0
    assert r.conflict == 1


# --- conflicts --------------------------------------------------------------

def test_disagreeing_identity_values_conflict():
    r = _cmp([_Alt("111")], [_Alt("222")])
    assert r.meta["matches"] == 0
    assert r.conflict == 1


def test_a_non_identity_entry_creates_no_conflict_either():
    """It is not evidence in EITHER direction -- it names another work."""
    r = _cmp([_Alt("111", relation="IsDerivedFrom")], [_Alt("222")])
    assert r.conflict == 0
    assert r.quality is None


# --- Kind ------------------------------------------------------------------

def test_the_full_domain_is_part_of_the_kind():
    """themoviedb.org/movie and /tv may reuse the same number."""
    r = _cmp([_Alt("42", domain="themoviedb.org/movie")],
             [_Alt("42", domain="themoviedb.org/tv")])
    assert r.meta["matches"] == 0


def test_a_shortdoi_is_not_a_third_party_identifier():
    """A ShortDOI aliases the EIDR ID itself; matching on it is circular."""
    r = _cmp([_Alt("10/abc", id_type="ShortDOI", domain="shortdoi")],
             [_Alt("10/abc", id_type="ShortDOI", domain="shortdoi")])
    assert r.meta["matches"] == 0
    assert r.quality is None
