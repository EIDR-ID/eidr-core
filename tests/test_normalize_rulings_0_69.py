"""normalize rulings of 2026-10-19 (operator; 0.69.0), from the 2026-10-02
dictionary audit.

All three feed scoring through compare, and each one's old wrong answer was
silent -- a plausible value, not an error -- which is what this thin suite
covers:

- norm_title: the leading-article test now sees the first word as written,
  before numeral and alias folding, so Italian 'i' and 'lo' are stripped;
  a leading 'i' is an article only when an Italian plural follows, so the
  English pronoun and the Roman numeral keep their old behaviour.
- parse_minutes: every valid ISO 8601 runtime form is read whole, and
  anything else is None rather than a partial parse; two-part 'a:b' is M:SS.
- norm_lang: the wildcard test runs on the primary subtag.
"""
from __future__ import annotations

import math

import pytest

from eidr_core.normalize import norm_code, norm_lang, norm_title, parse_minutes

# --- norm_title: leading articles before folding ------------------------------


@pytest.mark.parametrize("raw,expected", [
    # The audit's two cases: never stripped before 0.69.0.
    ("I Promessi Sposi", "promessi sposi"),        # was '1 promessi sposi'
    ("Lo Hobbit", "hobbit"),                       # was 'low hobbit'
    # Italian 'i' before a plural in -i, a cardinal number, or "più".
    ("I soliti ignoti", "soliti ignoti"),
    ("I Pagliacci", "pagliacci"),
    ("I due Foscari", "due foscari"),
    ("I tre moschettieri", "tre moschettieri"),
    ("I più grandi di tutti", "piu grandi di tutti"),
    ("I miserabili", "miserabili"),                # De-Dupe UI vector NT-12 moves
    # Spanish/Italian 'lo'.
    ("Lo imposible", "imposible"),
    ("Lo chiamavano Trinità", "chiamavano trinita"),
])
def test_italian_leading_articles_are_now_stripped(raw, expected):
    assert norm_title(raw) == expected


def test_the_article_and_the_bare_title_now_meet():
    # The point of article stripping: one source writes the article, one
    # does not. Before 0.69.0 these pairs normalised apart.
    assert norm_title("I promessi sposi") == norm_title("Promessi sposi")
    assert norm_title("Lo Hobbit") == norm_title("Hobbit")


@pytest.mark.parametrize("raw,expected", [
    # English 'I' -- pronoun or numeral -- is NOT an article: these are
    # exactly the 0.68 outputs, pinned so the Italian fix cannot leak.
    ("I Love Lucy", "1 love lucy"),
    ("I, Robot", "1 robot"),                       # punctuation after 'I'
    ("I Spy", "1 spy"),
    ("I Am Sam", "1 am sam"),
    ("I'm Still Here", "1 m still here"),          # apostrophe after 'I'
    ("Rocky I", "rocky 1"),                        # not the first word at all
    ("I", "i"),                                    # a one-letter title, verbatim
    ("I & II", "i and 2"),                         # an initial beside '&'
])
def test_english_i_keeps_its_old_normalisation(raw, expected):
    assert norm_title(raw) == expected


def test_i_spy_and_spy_stay_apart():
    # Two different films. Stripping 'i' unconditionally would merge them,
    # which is the regression the follower test exists to prevent.
    assert norm_title("I Spy") != norm_title("Spy")


@pytest.mark.parametrize("raw,expected", [
    ("The Matrix", "matrix"),
    ("L'Auberge espagnole", "auberge espagnole"),
    ("A&E Networks LLC", "a and e networks llc"),  # the initial is protected
    ("The A&E Story", "a and e story"),
    ("Lo", "low"),                                 # one word: never stripped, still aliased
    ("Rocky II", "rocky 2"),
])
def test_other_titles_are_unchanged(raw, expected):
    assert norm_title(raw) == expected


def test_strip_articles_false_still_folds_the_first_word():
    assert norm_title("I promessi sposi", strip_articles=False) == "1 promessi sposi"
    assert norm_title("Lo Hobbit", strip_articles=False) == "low hobbit"


# --- parse_minutes: whole valid forms only -------------------------------------


@pytest.mark.parametrize("raw,expected", [
    # Unchanged from 0.68 (and De-Dupe UI vectors PM-1..PM-6).
    ("136", 136.0), ("PT2H16M", 136.0), ("PT1H18M", 78.0), ("01:18:00", 78.0),
    ("P1DT2H", 1560.0), ("90.5", 90.5), (78, 78.0), (41.5, 41.5), ("PT0S", 0.0),
    ("pt1h", 60.0),
    # Fractional seconds: 0.68 dropped them ('PT1H18M30.5S' -> 78.0) or
    # matched nothing ('PT24.4S' -> None). Both shapes are in the mirror.
    ("PT1H18M30.5S", 78 + 30.5 / 60), ("PT24.4S", 24.4 / 60),
    ("PT3M14.3S", 3 + 14.3 / 60), ("PT30,5S", 30.5 / 60),
    # The ISO decimal on the last component, whatever it is.
    ("PT1.5H", 90.0), ("PT1H30.5M", 90.5), ("P0.5D", 720.0),
    # Weeks and days.
    ("P2W", 20160.0), ("P1W2D", 12960.0), ("P1DT1H", 1500.0),
    ("P0Y0M1D", 1440.0),                           # zero years/months are harmless
    # The alternative format, extended and basic.
    ("P0000-00-00T01:18:00", 78.0), ("P00000000T011800", 78.0),
    ("P0000-00-01T00:00:30.5", 1440 + 30.5 / 60),
    # Timecodes.
    ("1:18:30.5", 78 + 30.5 / 60), ("01:18:00:12", 78.0), ("01:18:00;12", 78.0),
    ("100:00:00", 6000.0),
    # Two-part is M:SS (0.68 read H:MM: '78:30' -> 4710.0).
    ("78:30", 78.5), ("1:30", 1.5), ("0:45", 0.75), ("78:30.5", 78 + 30.5 / 60),
])
def test_valid_runtimes_parse_whole(raw, expected):
    assert parse_minutes(raw) == pytest.approx(expected)


@pytest.mark.parametrize("raw", [
    None, "", "   ", "1h", True,
    "P78M",                    # 78 MONTHS in ISO: no fixed length (0.68: 78.0)
    "P1Y", "P1Y2DT1H", "P0000-01-00T00:00:00",
    "P1H",                     # an hour needs the T (0.68: 60.0)
    "P", "PT", "P1DT",         # nothing, or a T that introduces nothing
    "PT1.5H30M",               # a fraction on a component that is not the last
    "PT1H18M junk",            # trailing text: not a partial parse
    "-PT5M",
    "P0000-00-00T24:00:00", "P0000-00-00T01:60:00",
    "01:78:00", "01:18:60", "78:60", "1:18.5:00", "1:2:3:4:5", "a:b",
    "nan", "inf", "-5", float("nan"), float("inf"), -5,
])
def test_anything_else_is_none(raw):
    assert parse_minutes(raw) is None


def test_a_float_input_is_not_routed_through_its_repr():
    # str(1e-05) is '1e-05'; the number itself is a valid (tiny) runtime.
    assert parse_minutes(1e-05) == 1e-05
    assert isinstance(parse_minutes(78), float)


def test_every_iso_result_is_a_float():
    for raw in ("P0Y", "PT0S", "P1W", "PT1H"):
        v = parse_minutes(raw)
        assert isinstance(v, float) and math.isfinite(v)


# --- norm_lang: wildcard test on the primary subtag ----------------------------


@pytest.mark.parametrize("raw", [
    "und", "und-Latn", "UND-latn", "xx", "xx-YY", "zz-ZZ", "none-x", "null-1",
])
def test_a_wildcard_primary_subtag_is_absent(raw):
    assert norm_lang(raw) == ""


@pytest.mark.parametrize("raw,expected", [
    ("en-US", "en"), ("zh-Hans", "zh"), ("pt-BR", "pt"), ("EN", "en"),
    ("zxx", "zxx"), ("zxx-Latn", "zxx"),   # no linguistic content: a real code
    ("mul", "mul"),                        # multiple languages: a real code
    (" en -US", "en"),
    ("", ""), (None, ""),
])
def test_real_languages_keep_their_primary_subtag(raw, expected):
    assert norm_lang(raw) == expected


def test_norm_code_itself_is_unchanged():
    # norm_code also serves countries, which have no subtags; the ruling is
    # about norm_lang only.
    assert norm_code("und-Latn") == "und-latn"
    assert norm_code("und") == ""
