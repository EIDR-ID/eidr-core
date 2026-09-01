"""Episode title semantics, and the film behaviour they must NOT disturb.

Operator rulings 2026-09-01, via BMR-Review. Two rules apply to EPISODES only:

* a compound title is a COMBINATION of segments -- the same set in any order
  is one program, a different set is a different program;
* a part number on one side only is AMBIGUOUS -- the un-numbered title may be
  any one part, or all parts combined.

Both are wrong for films, where "/" is usually a subtitle separator
("Jumanji/ nekusuto reberu") and a bare number against a subtitled alternate
("Troublesome Night 5" vs "Troublesome Night - The A Files") is the SAME film.
BMR-Review measured the cost of not gating them: 324 confirmed-match film
title pairs dropped by >= 0.2 across three labelled corpora, 247 with no
delimiter at all. The gate is the load-bearing part of this feature.
"""
from __future__ import annotations

import pytest

pytest.importorskip("rapidfuzz")

from eidr_core.compare.titles import (  # noqa: E402
    COMBINATION_DIFFERS_QUALITY,
    PART_AMBIGUOUS_QUALITY,
    parts_ambiguous,
    segments,
    title_similarity,
)


def q(a, b, episodic):
    return title_similarity(a, b, episodic=episodic)


# --- the case that started it -----------------------------------------------

def test_a_semicolon_is_a_segment_delimiter_like_a_slash():
    """The submitter writes "/", the registry stores ";".

    `segments()` split only on "/", so one side was two segments and the other
    one, scoring exactly 0.5 -- and two confirmed matches were closed as
    terminal no-match on that alone.
    """
    assert segments("Colossal Squid; Jawfish") == segments("Colossal Squid / Jawfish")
    for ep in (False, True):
        assert q("Colossal Squid / Jawfish", "Jawfish; Colossal Squid", ep) == 1.0


def test_the_same_segments_in_any_order_are_one_program():
    assert q("A / B / C", "C; A; B", True) == 1.0


# --- episode: a different combination is a different program ----------------

@pytest.mark.parametrize("a,b,label", [
    ("Squid / Jawfish / Puffer", "Squid / Jawfish", "subset"),
    ("Squid / Jawfish", "Squid / Jawfish / Puffer", "superset"),
    ("Squid / Jawfish", "Squid", "one segment against the slot"),
])
def test_a_different_segment_set_is_not_partial_credit(a, b, label):
    """Proportional credit is wrong here: 2 of 3 is not "two-thirds the same",
    it is a different combination of shorts, i.e. a different program."""
    assert q(a, b, True) == pytest.approx(COMBINATION_DIFFERS_QUALITY)


def test_one_segment_does_not_match_its_slot_through_token_set():
    """rapidfuzz's token_set_ratio scores any token SUBSET at 1.0 -- correct
    for "Matrix, The", fatal for a single cartoon against the slot that held
    it. The episode path uses token_sort_ratio for exactly this reason."""
    assert q("Colossal Squid / Jawfish", "Colossal Squid", True) < 0.5


# --- episode: one-sided part numbers ----------------------------------------

def test_a_one_sided_part_number_is_ambiguous_not_a_match():
    """"The Trial Part 1" vs "The Trial": the un-numbered title may be part 1,
    part 2, or the whole thing. Not a match, and not a conflict either."""
    assert q("The Trial Part 1", "The Trial", True) == pytest.approx(PART_AMBIGUOUS_QUALITY)
    assert parts_ambiguous(["The Trial Part 1"], ["The Trial"]) is True


def test_matching_part_numbers_still_match_and_differing_ones_still_conflict():
    assert q("The Trial Part 1", "The Trial Part 1", True) == 1.0
    assert q("The Trial Part 1", "The Trial Part 2", True) == pytest.approx(0.05)
    assert parts_ambiguous(["The Trial Part 1"], ["The Trial Part 2"]) is False


# --- films must be undisturbed ----------------------------------------------

def test_a_films_number_is_an_edition_not_a_part():
    """The same film under its numbered and subtitled names."""
    assert q("Troublesome Night 5", "Troublesome Night - The A Files", False) > 0.9


def test_a_separator_on_one_side_does_not_halve_an_identical_film_title():
    """The one film case this feature is allowed to change: 0.500 -> 1.000."""
    assert q("Colossal Squid / Jawfish", "Colossal Squid Jawfish", False) == 1.0


@pytest.mark.parametrize("a,b,expected,label", [
    ("Squid / Jawfish / Puffer", "Squid / Jawfish", 0.667, "subset"),
    ("Squid / Jawfish", "Squid", 0.500, "one segment"),
])
def test_film_segment_scores_are_unchanged(a, b, expected, label):
    """The floor must not INVENT film matches out of subsets.

    As delivered, the film floor used _fuzzy -- whose token_set_ratio scores a
    subset at 1.0 -- so it raised these from 0.667 and 0.500 to a perfect
    match, contradicting the patch's own table. That is the same hazard the
    patch guards against on the episode side. The floor now uses
    token_sort_ratio and applies only at >= 0.85, so it lifts the
    written-with-and-without-a-separator case and nothing else.
    """
    assert q(a, b, False) == pytest.approx(expected, abs=0.01)


def test_a_film_one_sided_part_number_is_still_a_match():
    """parts_ambiguous is episode-only; 247 of the 324 measured film
    regressions had no delimiter at all and came from this rule."""
    assert q("The Trial Part 1", "The Trial", False) == 1.0
