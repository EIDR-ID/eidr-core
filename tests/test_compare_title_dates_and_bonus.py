"""Two title rules from BMR-Review's handoff of 2026-11-23, inert until enabled.

Both were approved by the operator on 2026-11-23 and ship as T3 did:
eidr-core lands the MECHANISM, read from an optional parameter, and
BMR-Review sets the knob in its config.py in its own measured cycle, at the
compare-spec version reserved for it.

* ``TITLE_BONUS_MIN_BEST`` (2.22.0): below this best title pair, the title
  quality is the best pair alone, with no accumulation bonus. Two 0.69 pairs
  had added up to 1.133, and a different film scored 94.0 Accept.
* ``TITLE_DATE_TOKENS`` (2.23.0): an Episode/Season title's date is read as
  a date, not split on "/" into segments. "13/08/2026 - Quem Ama Nao Esquece"
  scored 0.20 against the registry's undated title.

Every wrong answer here is silent: a plausible score, a missing flag. So the
knob-absent path is pinned as today's behaviour, byte for byte, and each rule
is pinned in both directions (fires where it should, and nowhere else).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest

pytest.importorskip("rapidfuzz")

from eidr_core.compare import _params, cmp_titles, set_params  # noqa: E402
from eidr_core.compare.spec import load_spec  # noqa: E402
from eidr_core.compare.titles import (  # noqa: E402
    COMBINATION_DIFFERS_QUALITY,
    date_tokens,
    dates_ambiguous,
    title_similarity,
)

QUEM = "Quem Ama Não Esquece"


@dataclass
class _Title:
    text: str
    lang: str | None = "en"
    title_class: str | None = None
    system_generated: bool = False


@dataclass
class _Rec:
    titles: list = field(default_factory=list)
    creation_type: str = "Basic"


def _rec(ctype, *texts):
    return _Rec([_Title(t) for t in texts], ctype)


@pytest.fixture(autouse=True)
def _restore_source():
    before = _params.get_source()
    yield
    set_params(before)


def _params_with(**knobs):
    spec = load_spec()
    for k in ("TITLE_BONUS_MIN_BEST", "TITLE_DATE_TOKENS"):
        spec.pop(k, None)
    set_params(SimpleNamespace(**{**spec, **knobs}))


# --- date tokens: recognition ------------------------------------------------

@pytest.mark.parametrize("raw,dates,rest", [
    (f"13/08/2026 - {QUEM}", [("dmy", 13, 8, 26, 2026)], QUEM),
    ("Show 13.08.2026", [("dmy", 13, 8, 26, 2026)], "Show"),
    ("2026-08-13 Show", [("dmy", 13, 8, 26, 2026)], "Show"),       # y-m-d reordered
    ("13-08-26: Show", [("dmy", 13, 8, 26, None)], "Show"),         # two-digit year
    ("Mon, 6/16 - Show", [("md", 6, 16)], "Show"),                  # weekday + m/d
    ("Tue. 12/25", [("md", 12, 25)], ""),
    ("The Show, Part 2 (13/08/2026)", [("dmy", 13, 8, 26, 2026)], "The Show, Part 2"),
    ("9/11", [], "9/11"),                                           # no year, no weekday
    ("6/16", [], "6/16"),
    ("Show 32/13/2026", [], "Show 32/13/2026"),                     # cannot be a date
    ("Show 13/08-2026", [], "Show 13/08-2026"),                     # mixed separators
    ("Colossal Squid / Jawfish", [], "Colossal Squid / Jawfish"),
])
def test_date_tokens_finds_dates_and_only_dates(raw, dates, rest):
    assert date_tokens(raw) == (dates, rest)


# --- date tokens: similarity (the handoff's acceptance cases) ----------------

@pytest.mark.parametrize("a,b,want", [
    (f"13/08/2026 - {QUEM}", f"13/08/2026 - {QUEM}", 1.0),
    (f"13/08/2026 - {QUEM}", f"18/08/2026 - {QUEM}", COMBINATION_DIFFERS_QUALITY),
    (f"13/08/2026 - {QUEM}", QUEM, 1.0),                    # reported ambiguous
    ("Colossal Squid / Jawfish", "Colossal Squid; Jawfish", 1.0),
    ("9/11", "9/11", 1.0),
    ("07/09/2026 - Novela", "08/09/2026 - Novela", COMBINATION_DIFFERS_QUALITY),
    ("Mon, 6/16", "Mon, 6/17", COMBINATION_DIFFERS_QUALITY),
    ("2026-08-13 Show", "13.08.2026 - Show", 1.0),
    ("13/08/26 - Show", "13/08/2026 - Show", 1.0),
    ("13/08/26 - Show", "13/08/2025 - Show", COMBINATION_DIFFERS_QUALITY),
    ("13/08/1926 - Show", "13/08/2026 - Show", COMBINATION_DIFFERS_QUALITY),
    ("13/08/2026", "13/08/2026", 1.0),
    ("Mon, 6/16 - Show", "16/06/2026 - Show", COMBINATION_DIFFERS_QUALITY),  # shapes differ
])
def test_dates_on_episode_titles(a, b, want):
    assert title_similarity(a, b, episodic=True, dates=True) == pytest.approx(want)


def test_dates_off_is_todays_behaviour():
    # The defect, pinned so the knob-absent path cannot drift.
    assert title_similarity(f"13/08/2026 - {QUEM}", QUEM, episodic=True) \
        == COMBINATION_DIFFERS_QUALITY


def test_dates_never_touch_a_film():
    # Episode/Season only (operator, 2026-11-23): without episodic the flag
    # changes nothing.
    for a, b in [(f"13/08/2026 - {QUEM}", QUEM), ("07/09/2026 - X", "08/09/2026 - X")]:
        assert title_similarity(a, b, dates=True) == title_similarity(a, b)


def test_a_one_sided_date_is_ambiguous_and_nothing_else_is():
    assert dates_ambiguous([f"13/08/2026 - {QUEM}"], [QUEM])
    assert dates_ambiguous([QUEM], ["Mon, 6/16 - " + QUEM])
    assert not dates_ambiguous([f"13/08/2026 - {QUEM}"], [f"13/08/2026 - {QUEM}"])
    assert not dates_ambiguous([f"13/08/2026 - {QUEM}"], [f"18/08/2026 - {QUEM}"])
    assert not dates_ambiguous([f"13/08/2026 - {QUEM}"], ["Something Else Entirely"])


# --- cmp_titles: TITLE_DATE_TOKENS -------------------------------------------

def test_without_the_date_knob_cmp_titles_is_unchanged():
    _params_with()
    r = cmp_titles(_rec("Episode", f"13/08/2026 - {QUEM}"), _rec("Episode", QUEM))
    assert r.quality == COMBINATION_DIFFERS_QUALITY
    assert "date_ambiguous" not in r.meta
    assert "date-ambiguous" not in r.detail


def test_with_the_date_knob_an_episode_pair_compares_the_rest_and_flags_it():
    _params_with(TITLE_DATE_TOKENS=True)
    r = cmp_titles(_rec("Episode", f"13/08/2026 - {QUEM}"), _rec("Episode", QUEM))
    assert r.quality == 1.0
    assert r.meta["date_ambiguous"] is True
    assert "date-ambiguous" in r.detail
    r = cmp_titles(_rec("Episode", f"13/08/2026 - {QUEM}"),
                   _rec("Episode", f"18/08/2026 - {QUEM}"))
    assert r.quality == COMBINATION_DIFFERS_QUALITY
    assert r.meta["date_ambiguous"] is False


def test_the_date_knob_leaves_a_film_pair_alone():
    _params_with(TITLE_DATE_TOKENS=True)
    a, b = _rec("Basic", f"13/08/2026 - {QUEM}"), _rec("Basic", QUEM)
    on = cmp_titles(a, b)
    _params_with()
    off = cmp_titles(a, b)
    assert on.quality == off.quality
    assert on.meta["date_ambiguous"] is False


def test_with_dates_on_a_date_does_not_hide_a_part_number():
    # The part checks read the dated titles with their dates removed, as the
    # similarity does: "Part 2" against "Part 3" is still a part conflict.
    _params_with(TITLE_DATE_TOKENS=True)
    r = cmp_titles(_rec("Episode", "13/08/2026 - The Show Part 2"),
                   _rec("Episode", "13/08/2026 - The Show Part 3"))
    assert r.meta["part_conflict"]
    # A bracketed date at the end hides the part number from parse_part on
    # the raw title; with the date removed it is found.
    r = cmp_titles(_rec("Episode", "The Show, Part 2 (13/08/2026)"),
                   _rec("Episode", "The Show, Part 3"))
    assert r.meta["part_conflict"]


@pytest.mark.parametrize("bad", ["true", 1, 0.0])
def test_a_malformed_date_knob_fails_loudly(bad):
    _params_with(TITLE_DATE_TOKENS=bad)
    with pytest.raises(ValueError, match="TITLE_DATE_TOKENS"):
        cmp_titles(_rec("Basic", "A"), _rec("Basic", "A"))


# --- cmp_titles: TITLE_BONUS_MIN_BEST ----------------------------------------

GIFT = _rec("Basic", "A Christmas Gift of Love", "The Royal Christmas Mix-Up")
ANTIQUE = _rec("Basic", "An Antique Christmas", "Christmas Antiques Show")
STRONG = _rec("Basic", "An Antique Christmas", "Mix-Up at Christmas")


def test_without_the_bonus_knob_a_weak_best_still_earns_the_bonus():
    _params_with()
    r = cmp_titles(GIFT, ANTIQUE)
    assert r.meta["best_sim"] < 0.85 < r.quality       # 0.69 best, 1.159 field
    assert "weak best" not in r.detail


def test_with_the_bonus_knob_a_weak_best_is_the_whole_title_quality():
    _params_with(TITLE_BONUS_MIN_BEST=0.85)
    r = cmp_titles(GIFT, ANTIQUE)
    assert r.quality == pytest.approx(r.meta["best_sim"])
    assert r.quality < 0.85
    assert "no bonus, weak best" in r.detail


def test_with_the_bonus_knob_a_strong_best_keeps_its_bonus():
    _params_with()
    before = cmp_titles(GIFT, STRONG).quality
    _params_with(TITLE_BONUS_MIN_BEST=0.85)
    r = cmp_titles(GIFT, STRONG)
    assert r.meta["best_sim"] >= 0.85
    assert r.quality == before > r.meta["best_sim"]


@pytest.mark.parametrize("bad", [0, 1.5, True, "0.85"])
def test_a_malformed_bonus_knob_fails_loudly(bad):
    _params_with(TITLE_BONUS_MIN_BEST=bad)
    with pytest.raises(ValueError, match="TITLE_BONUS_MIN_BEST"):
        cmp_titles(GIFT, ANTIQUE)
