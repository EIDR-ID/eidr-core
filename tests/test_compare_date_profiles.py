"""Per-creation-type date profiles, and the inversion they exist to kill.

Under the flat legacy constants a year-only Episode MISMATCH outscored a
MATCH for every gap below ~4.4 years: the match credit (0.6) and the decay
curve (half-life 6y, so 0.891 at gap 1) were on different scales. A table
cannot invert, which is the structural point -- BMR-Review measured the shape
across 3,306 human decisions and it is not exponential.
"""
from __future__ import annotations

from dataclasses import dataclass

import pytest

pytest.importorskip("rapidfuzz")

from eidr_core.compare import cmp_release_date, date_profile, set_params  # noqa: E402


@dataclass
class R:
    release_date: str | None = None
    creation_type: str | None = "Basic"
    date_estimated: bool = False


_PROFILES = {
    "Basic": {
        "year_gap_credit": {0: 0.60, 1: 0.43, 2: 0.13},
        "year_gap_floor": 0.10,
        "full_date_bands": [(0, 1.00), (7, 0.95), (31, 0.70)],
    },
}


class _Cfg:
    """The PACKAGED spec, with DATE_PROFILES layered on.

    Wrapping the real spec rather than hand-rolling constants: the comparator
    reads more of them than this test cares about (the 1970-epoch guards among
    them), and a hand-rolled source silently omits whichever ones get added
    next.
    """

    DATE_PROFILES = _PROFILES

    def __init__(self, profiles=_PROFILES):
        from eidr_core.compare.spec import load_spec
        spec = load_spec()
        params = spec.get("params", spec)
        self._p = {k.upper(): v for k, v in params.items()
                   if not isinstance(v, (dict, list))}
        self.DATE_PROFILES = profiles

    def __getattr__(self, name):
        try:
            return self._p[name.upper()]
        except KeyError as exc:
            raise AttributeError(name) from exc


@pytest.fixture
def profiled():
    set_params(_Cfg())


@pytest.fixture
def legacy():
    set_params(_Cfg(profiles=None))


def _q(a_year, b_year, ct="Episode"):
    return cmp_release_date(R(str(a_year), ct), R(str(b_year), ct)).quality


# --- the defect -------------------------------------------------------------

def test_a_match_outscores_every_mismatch(profiled):
    """The whole point. Monotonic non-increasing in the gap."""
    qs = [_q(2000, 2000 + g) for g in range(4)]
    assert qs == sorted(qs, reverse=True), f"not monotonic: {qs}"
    assert all(qs[0] > x for x in qs[1:]), f"a mismatch beat the match: {qs}"


def test_the_legacy_constants_really_did_invert(legacy):
    """Pins the defect, so the fix cannot be quietly reverted."""
    assert _q(2000, 2000) == pytest.approx(0.6)
    assert _q(2000, 2001) > 0.6


# --- the table --------------------------------------------------------------

@pytest.mark.parametrize("gap,expected", [(0, 0.60), (1, 0.43), (2, 0.13)])
def test_year_gap_credits_come_from_the_table(profiled, gap, expected):
    assert _q(2000, 2000 + gap) == pytest.approx(expected)


def test_beyond_the_table_the_floor_applies(profiled):
    """Large gaps are unlikely but never ruled out -- sources differ."""
    for gap in (3, 8, 40):
        assert _q(2000, 2000 + gap) == pytest.approx(0.10)


@pytest.mark.parametrize("days,expected", [(0, 1.00), (5, 0.95), (20, 0.70)])
def test_full_date_bands(profiled, days, expected):
    import datetime as dt
    a = dt.date(2000, 6, 1)
    b = a + dt.timedelta(days=days)
    got = cmp_release_date(R(a.isoformat(), "Basic"), R(b.isoformat(), "Basic"))
    assert got.quality == pytest.approx(expected)


def test_beyond_the_last_band_falls_through_not_off_a_cliff(profiled):
    """A distant full date is worth no more than a distant year pair."""
    import datetime as dt
    a = dt.date(2000, 6, 1)
    far = (a + dt.timedelta(days=400)).isoformat()
    got = cmp_release_date(R(a.isoformat(), "Basic"), R(far, "Basic"))
    assert got.quality is not None and 0.0 < got.quality < 0.70


# --- profile selection ------------------------------------------------------

def test_an_unknown_creation_type_falls_back_to_basic(profiled):
    assert date_profile("Manifestation", "Manifestation") is _PROFILES["Basic"]


def test_a_cross_type_pair_uses_basic(profiled):
    """The Accept cap for cross-type pairs is the gate's job, not this one."""
    assert date_profile("Basic", "Episode") is _PROFILES["Basic"]


def test_a_config_without_profiles_keeps_the_legacy_behaviour(legacy):
    """No consumer is forced onto the new shape in the cycle it lands."""
    assert date_profile("Basic", "Basic") is None
    assert _q(2000, 2000, "Basic") == pytest.approx(1.0)


# --- the JSON shape (added 2026-08-31) --------------------------------------
# A profile authored in Python may key by int and use tuples. The SAME profile
# read back from compare-spec.json is keyed by STRING with list bands, because
# JSON has nothing else. Both must score identically, or the tuning surface
# means one thing here and another to every consumer that loads the versioned
# artifact -- including the De-Dupe UI's JavaScript engine, which can ONLY see
# the JSON form.
#
# Everything above this line uses the Python shape, which is why the defect
# these pin was invisible: `gap in credits` fails silently against string keys,
# the caller falls back to the legacy exponential, and a profile that looks
# configured has no effect at all.

_JSON_PROFILES = {
    "Basic": {
        "year_gap_credit": {"0": 0.60, "1": 0.43, "2": 0.13},
        "year_gap_floor": 0.10,
        "full_date_bands": [[0, 1.00], [7, 0.95], [31, 0.70]],
    },
}


@pytest.fixture
def json_profiled():
    set_params(_Cfg(profiles=_JSON_PROFILES))


@pytest.mark.parametrize("gap", [0, 1, 2, 3, 7])
def test_json_shape_scores_identically_to_python_shape(gap):
    set_params(_Cfg())                      # int keys, tuple bands
    native = _q(2000, 2000 + gap)
    set_params(_Cfg(profiles=_JSON_PROFILES))   # string keys, list bands
    from_json = _q(2000, 2000 + gap)
    assert native == from_json, (
        f"gap {gap}: Python-authored profile scores {native} but the same "
        f"profile read from JSON scores {from_json}")


def test_a_json_shaped_profile_is_actually_used(json_profiled):
    """The silent-no-op guard.

    If the string keys are not matched the caller falls through to the legacy
    exponential, which at gap 1 gives ~0.891 for an Episode -- so a wrong
    implementation does not error, it just quietly ignores the table.
    """
    assert _q(2000, 2001) == 0.43
    assert _q(2000, 2000) == 0.60


def test_json_shaped_floor_applies_beyond_the_table(json_profiled):
    assert _q(2000, 2009) == 0.10


def test_max_key_is_numeric_not_lexicographic():
    """`max()` over string keys compares lexicographically: "2" > "10".

    A table reaching gap 10 would treat 2 as its largest key and apply the
    floor to every gap above 2 -- silently wrong in the middle of the range,
    where most real pairs sit.
    """
    set_params(_Cfg(profiles={"Basic": {
        "year_gap_credit": {"0": 1.0, "2": 0.5, "10": 0.2},
        "year_gap_floor": 0.01,
        "full_date_bands": [[0, 1.0]],
    }}))
    assert _q(2000, 2010) == 0.2      # the largest key, not the floor
    assert _q(2000, 2011) == 0.01     # beyond it, the floor
    assert _q(2000, 2005) is None or _q(2000, 2005) != 0.01
