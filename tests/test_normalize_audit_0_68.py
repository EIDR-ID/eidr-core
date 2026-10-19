"""normalize fixes from the 2026-10-02 dictionary audit (0.68.0).

Both are silent-wrong-answer surfaces, which is what this thin suite covers:
an impossible ISO date came back as a full date (and only failed later, as
an uncaught ValueError inside compare.cmp_release_date), and sanitize_field
left a space where an edge control character had been.
"""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from eidr_core.compare import cmp_release_date
from eidr_core.normalize import days_between, parse_date, sanitize_field

# --- parse_date ---------------------------------------------------------------


@pytest.mark.parametrize("raw", [
    "2006-13-45",        # no such month or day
    "2006-02-30",        # no such day in February
    "2006-00-10",        # month zero
    "2006-04-31",        # April has 30 days
    "2005-02-29",        # not a leap year
])
def test_an_impossible_iso_date_keeps_its_year_but_not_a_ymd(raw):
    assert parse_date(raw) == (int(raw[:4]), None)


@pytest.mark.parametrize("raw,expected", [
    ("2006-02-28", (2006, (2006, 2, 28))),
    ("2004-02-29", (2004, (2004, 2, 29))),             # leap year
    ("2006-02-28T00:00:00Z", (2006, (2006, 2, 28))),   # suffix still ignored
])
def test_a_real_iso_date_is_unchanged(raw, expected):
    assert parse_date(raw) == expected


def test_the_iso_branch_now_agrees_with_the_slash_branch():
    # The slash branch always validated; the two must give the same shape
    # for the same impossible date.
    assert parse_date("2006-02-30") == parse_date("2/30/2006") == (2006, None)


@pytest.mark.parametrize("raw,expected", [
    ("3/4/2006", (2006, (2006, 3, 4))),     # M/D by default
    ("12/4/2006", (2006, (2006, 12, 4))),   # first field 12 is still a month
    ("13/4/2006", (2006, (2006, 4, 13))),   # D/M only when the first is > 12
])
def test_slash_order_is_md_unless_the_first_field_is_over_12(raw, expected):
    assert parse_date(raw) == expected


def test_days_between_is_never_handed_an_impossible_date():
    _, ymd = parse_date("2006-13-45")
    assert ymd is None          # so callers' `if ymd` guards skip the arithmetic
    assert days_between((2006, 1, 1), (2006, 1, 31)) == 30


@dataclass
class _R:
    release_date: str | None = None
    creation_type: str | None = "Basic"
    date_estimated: bool = False


def test_cmp_release_date_scores_an_impossible_date_as_year_only():
    """Before 0.68.0 this raised ValueError out of days_between. Now the
    impossible date degrades to year-only evidence -- compared against the
    genuinely year-only input, which must score identically."""
    from types import SimpleNamespace

    from eidr_core.compare import _params, set_params
    from eidr_core.compare.spec import load_spec

    # set_params is process-global: register the packaged spec (real
    # thresholds) and put back whatever was there before.
    before = _params.get_source()
    set_params(SimpleNamespace(**load_spec()))
    try:
        bad = cmp_release_date(_R("2006-13-45"), _R("2006-05-01"))
        year_only = cmp_release_date(_R("2006"), _R("2006-05-01"))
    finally:
        set_params(before)
    assert bad.quality is not None
    assert (bad.quality, bad.detail) == (year_only.quality, year_only.detail)


# --- sanitize_field -------------------------------------------------------------


@pytest.mark.parametrize("raw,expected", [
    ("a\t", "a"),
    ("\ta", "a"),
    ("\na\r\n", "a"),
    ("a\x07", "a"),                 # C0 at an edge
    ("\x00 a", "a"),                # NUL removed, then the space stripped
    ("\x1fa\x01", "a"),
    ("a\tb", "a b"),                # interior replacements are unchanged
    ("a\x00b", "ab"),
    ("\t\n\r", ""),                 # all-control is whitespace-only
    ("", ""),
    (None, ""),
    ("  padded  ", "padded"),
])
def test_sanitize_field_replaces_first_and_strips_last(raw, expected):
    assert sanitize_field(raw) == expected


@pytest.mark.parametrize("raw", ["a\x7f", "\x7fa", "a\x80b", "a\x9fb", "\x9fa"])
def test_sanitize_field_leaves_del_and_c1_controls_alone(raw):
    # eidr-wikidata pins that these pass through; only C0 is swept.
    assert sanitize_field(raw) == raw
