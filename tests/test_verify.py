"""verify: the three silent wrong answers the 2026-10-02 dictionary audit found.

Why (0.68.0): each returned a plausible result instead of an error -- an
unknown ``mode`` ran the window rule, agreeing date fields got a
self-contradicting arbitration note, and a scalar runtime ``"90"`` became
two runtimes, 9 and 0. A DQ finding built on any of them looks like a real
one, which is the class of bug this repo's local tests exist for.
"""
from __future__ import annotations

from datetime import date

import pytest

from eidr_core.verify import (
    compare_release_date,
    compare_runtime,
    compare_year_arbitration,
    runtime_candidates,
)

FACTS = {"release_date": "2000-06-01"}


@pytest.mark.parametrize("mode", ["exactdate", "Window", "", "year_arbitration"])
def test_compare_release_date_refuses_an_unknown_mode(mode):
    with pytest.raises(ValueError, match="unknown mode"):
        compare_release_date(date(2000, 1, 1), 2000, FACTS, mode=mode)
    # Refused even when there is no fact to compare: a typo in a rule config
    # must not hide until the first record that has external data.
    with pytest.raises(ValueError, match="unknown mode"):
        compare_release_date(date(2000, 1, 1), 2000, {}, mode=mode)


@pytest.mark.parametrize("mode,want", [
    ("exact_date", "mismatch"), ("year", "match"), ("window", "mismatch"),
])
def test_compare_release_date_known_modes_unchanged(mode, want):
    assert compare_release_date(date(2000, 1, 1), 2000, FACTS, mode=mode)[0] == want


def test_year_arbitration_with_agreeing_fields_has_nothing_to_arbitrate():
    assert compare_year_arbitration(date(2000, 1, 1), 2000, FACTS) == (
        "insufficient", "release_date and release_year agree; nothing to arbitrate")


def test_year_arbitration_still_names_the_outlier():
    verdict, note = compare_year_arbitration(date(2000, 1, 1), 1999, FACTS)
    assert verdict == "mismatch" and "release_year (1999) is the outlier" in note


@pytest.mark.parametrize("facts,want", [
    ({"runtime_minutes": "90"}, [90.0]),           # was [9.0, 0.0]
    ({"runtime_minutes": 90}, [90.0]),             # was TypeError
    ({"runtime_minutes": 90.5, "episode_runtime_minutes": [22, "24"]}, [90.5, 22.0, 24.0]),
    ({"runtime_minutes": [100.0, 95]}, [100.0, 95.0]),
    ({"runtime_minutes": None, "episode_runtime_minutes": []}, []),
    ({}, []),
])
def test_runtime_candidates_reads_a_scalar_as_one_runtime(facts, want):
    assert runtime_candidates(facts) == want


def test_compare_runtime_on_a_string_runtime():
    assert compare_runtime(90.0, {"runtime_minutes": "90"})[0] == "match"
