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


# --- the full-date fall-through ---------------------------------------------

def test_beyond_the_last_band_the_DISTANCE_equivalent_year_applies(profiled):
    """Not the calendar gap, and never above the last band.

    Two separate defects converge here.

    0.24.0 fell through to the legacy exponential (BMR-Review). 0.24.1 fixed
    that but keyed on the CALENDAR year, which produced a second inversion
    (De-Dupe UI): 31 days apart scored 0.70 and 32 days apart scored the
    profile's gap-0 anchor -- a pair further apart scoring higher, the exact
    failure class DATE_PROFILES exists to eliminate.

    The evidence settles the key: P(match) is 0.331 at 32-365 days against
    0.332 at a one-year gap, so a 32-day pair IS one-year evidence regardless
    of which side of New Year it falls.
    """
    import datetime as dt
    a = dt.date(2020, 3, 1)

    def q(days):
        b = (a + dt.timedelta(days=days)).isoformat()
        return cmp_release_date(R(a.isoformat()), R(b)).quality

    # 50 days is one-year evidence -> the gap-1 credit, not the gap-0 anchor.
    assert q(50) == pytest.approx(0.43)
    # Still one-year evidence most of the way to a year.
    assert q(200) == pytest.approx(0.43)
    # Three years -> the floor.
    assert q(1096) == pytest.approx(0.10)


def test_the_band_boundary_does_not_step_up(profiled):
    """The inversion De-Dupe UI found, pinned at one-day resolution."""
    import datetime as dt
    a = dt.date(2020, 3, 1)
    qs = []
    for days in range(25, 45):
        b = (a + dt.timedelta(days=days)).isoformat()
        qs.append((days, cmp_release_date(R(a.isoformat()), R(b)).quality))
    for (d0, q0), (d1, q1) in zip(qs, qs[1:]):
        assert q1 <= q0 + 1e-9, f"{d1}d scored {q1} against {q0} at {d0}d"


def test_the_same_distance_scores_the_same_across_new_year(profiled):
    """A calendar boundary is not evidence.

    Keying the fall-through on the calendar year made 32 days score the gap-0
    anchor within a year and the gap-1 value across one -- same distance, same
    evidence, different answer.
    """
    within = cmp_release_date(R("2020-03-01"), R("2020-04-02")).quality   # 32d
    across = cmp_release_date(R("2020-12-20"), R("2021-01-21")).quality   # 32d
    assert within == pytest.approx(across)


def test_the_shipped_profiles_are_validated(profiled):
    """A profile must not be authored so the boundary steps up.

    The clamp keeps a flawed profile monotonic, so this is the only thing that
    surfaces the authoring defect rather than silently masking it.
    """
    from eidr_core.compare import validate_date_profile
    assert validate_date_profile(_PROFILES["Basic"], "Basic") == []


def test_the_validator_catches_a_boundary_that_steps_up():
    """The condition, and the number to change, both named."""
    from eidr_core.compare import validate_date_profile
    bad = {"year_gap_credit": {0: 1.00, 1: 0.71, 2: 0.22},
           "year_gap_floor": 0.17,
           "full_date_bands": [(0, 1.00), (31, 0.70)]}
    problems = validate_date_profile(bad, "Basic")
    assert len(problems) == 1
    assert "0.71" in problems[0] and "0.7" in problems[0]


def test_the_validator_catches_a_non_monotonic_year_table():
    """The original inversion class, as an authoring check."""
    from eidr_core.compare import validate_date_profile
    bad = {"year_gap_credit": {0: 0.60, 1: 0.89}, "year_gap_floor": 0.10,
           "full_date_bands": [(0, 1.0)]}
    assert any("not monotonic" in p for p in validate_date_profile(bad))


def test_beyond_the_bands_a_full_date_matches_its_year_only_equivalent(profiled):
    """The invariant, in the form that actually holds.

    eidr-core first stated this as "a full-date pair must never score above
    its year-only equivalent". De-Dupe UI tested that form across both
    profiles and 17 distances and it fails 7 of 34 -- all INSIDE the bands,
    all Episode, and all correctly: an Episode 3 days apart scores 0.95
    against a year-only 0.60, which is the entire point of day-level
    precision. A shared air date is highly discriminating for an episode even
    though a shared year is not, and that asymmetry is what the per-type
    anchor encodes.

    The form that holds, and the one worth pinning: BEYOND the last band a
    full-date pair scores exactly what the same records would score on
    year-level evidence for that distance.
    """
    import datetime as dt
    a = dt.date(2020, 1, 1)
    for days in (40, 100, 200, 300, 364):
        b = a + dt.timedelta(days=days)
        full = cmp_release_date(R(a.isoformat()), R(b.isoformat())).quality
        year_only = cmp_release_date(R(str(a.year)), R(str(b.year))).quality
        assert full <= year_only + 1e-9, (
            f"{days}d apart scored {full} but year-only scores {year_only}")


def test_a_config_without_profiles_keeps_the_legacy_full_date_curve(legacy):
    """The fall-through must not disturb a consumer still on flat constants."""
    import datetime as dt
    a = dt.date(2020, 1, 1)
    b = (a + dt.timedelta(days=540)).isoformat()   # exactly one half-life
    got = cmp_release_date(R(a.isoformat()), R(b)).quality
    assert got == pytest.approx(0.5, abs=0.01)
