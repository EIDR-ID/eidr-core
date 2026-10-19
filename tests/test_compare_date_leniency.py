"""Estimated-date leniency in cmp_release_date (operator ruling 2026-10-19,
"Fix this"; eidr-core 0.69.0, compare-spec 2.21.0).

Until 0.69.0 the profile year path MULTIPLIED the credit by
DATE_ESTIMATED_LENIENCY (capped at 1.0). With RD:Pro on one side an Episode
pair a year apart scored 1.0 while an exact Episode year match scored 0.80 --
an inversion, the defect class DATE_PROFILES exist to prevent. The band and
fall-through paths ignored leniency yet still wrote " est" in the detail.

The rule now: every distance is divided by the leniency before lookup (a
fractional year gap interpolates the table). These tests pin the four
properties the ruling asked for, against the PACKAGED profiles, because a
wrong answer here is silent -- a plausible score, never an error.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

pytest.importorskip("rapidfuzz")

from eidr_core.compare import (  # noqa: E402
    cmp_release_date,
    set_params,
    validate_date_profile,
)
from eidr_core.compare.spec import load_spec  # noqa: E402


@dataclass
class R:
    release_date: str | None = None
    creation_type: str | None = "Basic"
    date_estimated: bool = False


@pytest.fixture(autouse=True)
def _params():
    set_params(SimpleNamespace(**load_spec()))


def _year(gap, ct, est):
    return cmp_release_date(R("2000", ct, est), R(str(2000 + gap), ct))


def _days(days, ct, est, start=dt.date(2020, 3, 1)):
    # Start on March 1 so 0..120 days stays inside one calendar year: the
    # calendar gap, which can legitimately lift a pair across New Year, is
    # then not part of what the monotonicity check is measuring.
    b = (start + dt.timedelta(days=days)).isoformat()
    return cmp_release_date(R(start.isoformat(), ct, est), R(b, ct))


CTS = ("Episode", "Basic")


@pytest.mark.parametrize("ct", CTS)
def test_the_shipped_profiles_still_validate(ct):
    profile = load_spec()["DATE_PROFILES"][ct]
    assert validate_date_profile(profile, ct) == []


@pytest.mark.parametrize("ct", CTS)
def test_an_estimated_one_year_gap_scores_below_the_year_match(ct):
    """(a) The defect: Episode gap 1 with one side estimated scored 1.0
    against 0.80 for an exact year match."""
    match = _year(0, ct, False).quality
    assert _year(1, ct, True).quality < match
    assert _year(0, ct, True).quality == match     # a match is unaffected


@pytest.mark.parametrize("ct", CTS)
@pytest.mark.parametrize("gap", [1, 2, 3])
def test_leniency_helps_against_the_same_gap_unflagged(ct, gap):
    """(b) The flag still means something."""
    assert _year(gap, ct, True).quality > _year(gap, ct, False).quality


@pytest.mark.parametrize("ct", CTS)
@pytest.mark.parametrize("est", [False, True])
def test_a_larger_year_gap_never_scores_higher(ct, est):
    """(c) Monotonic non-increasing over the whole range, floor included."""
    qs = [_year(g, ct, est).quality for g in range(0, 9)]
    assert all(q1 <= q0 + 1e-12 for q0, q1 in zip(qs, qs[1:], strict=False)), qs


@pytest.mark.parametrize("ct", CTS)
def test_a_larger_day_distance_never_scores_higher_when_estimated(ct):
    qs = [_days(d, ct, True).quality for d in range(1, 121)]
    assert all(q1 <= q0 + 1e-12 for q0, q1 in zip(qs, qs[1:], strict=False)), qs


@pytest.mark.parametrize("ct", CTS)
def test_an_estimated_full_date_never_reaches_day_exact(ct):
    exact = _days(0, ct, False).quality
    assert all(_days(d, ct, True).quality < exact for d in range(1, 121))


def test_the_episode_numbers():
    """The rule, at the numbers compare-spec.md states: the gap divided by
    DATE_ESTIMATED_LENIENCY (2.0), half gaps read halfway along the table."""
    assert [round(_year(g, "Episode", True).quality, 6) for g in range(6)] == \
        [0.8, 0.685, 0.57, 0.375, 0.18, 0.14]


@pytest.mark.parametrize("ct", CTS)
@pytest.mark.parametrize("gap", range(0, 9))
def test_est_appears_only_where_leniency_changed_the_year_score(ct, gap):
    """(d) Beyond twice the table, the floor is the floor either way."""
    flagged, plain = _year(gap, ct, True), _year(gap, ct, False)
    assert ("est" in flagged.detail) == (flagged.quality != plain.quality)


@pytest.mark.parametrize("ct", CTS)
@pytest.mark.parametrize("days", [1, 5, 10, 20, 40, 62, 63, 100, 400, 800])
def test_est_appears_only_where_leniency_changed_the_full_date_score(ct, days):
    """(d) on the band and fall-through paths, which until 0.69.0 ignored
    leniency and said " est" regardless. 1 and 5 days stay in the same band;
    20 days halved is still past the 7-day band."""
    flagged, plain = _days(days, ct, True), _days(days, ct, False)
    assert ("est" in flagged.detail) == (flagged.quality != plain.quality)


def test_est_is_absent_where_the_band_does_not_move():
    r = _days(5, "Basic", True)
    assert r.quality == pytest.approx(0.95) and "est" not in r.detail
