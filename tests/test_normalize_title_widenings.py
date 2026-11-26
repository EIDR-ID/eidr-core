"""normalize widenings accepted from LanguageTool (proposal 1, 2026-11-24;
ruled 2026-11-26): norm_title(trailing_articles=), title_numbers,
romanization_key.

Each one's wrong answer is silent -- a key that merges two titles, or
fails to merge one title written two ways, is a plausible string, not an
error -- which is what this thin suite covers.

The cases are LanguageTool's (tests/test_text.py: test_near_duplicates,
test_not_duplicates, test_romanization_scheme_fold,
test_numbers_reads_large_roman_numerals). Those tests assert on
dedupe.similarity, a rapidfuzz score above 0.85; eidr_core.normalize has no
fuzzy scorer, so they are ported as the statements about KEYS that the
score rests on: equal keys mean similarity 1.0, unequal title_numbers mean
0.0, and anything else is left to the caller's fuzzy stage.
"""
from __future__ import annotations

import pytest

from eidr_core.normalize import norm_title, romanization_key, title_numbers


def _key(s: str) -> str:
    """LanguageTool's dedupe.fold, as it would read after adoption."""
    return norm_title(s, trailing_articles=True)


# --- ported: test_near_duplicates ---------------------------------------------


@pytest.mark.parametrize("a,b", [
    ("The Matrix", "Matrix, The"),
    ("The Matrix", "Matrix"),
    ("AKIRA", "ＡＫＩＲＡ"),
    ("Encyclopaedia", "Encyclopædia"),
    ("Amélie", "Amelie"),
    ("Rocky II", "Rocky 2"),
    ("Spider-Man: Homecoming", "Spider Man - Homecoming"),
])
def test_near_duplicates_share_a_key(a, b):
    assert _key(a) == _key(b)
    assert title_numbers(_key(a)) == title_numbers(_key(b))


def test_spelling_variant_is_left_to_the_fuzzy_stage():
    # LanguageTool's eighth near-duplicate pair. Not equal as keys (no alias
    # maps colour/color); equal numbers, so the fuzzy ratio decides.
    a, b = _key("The Colour Purple"), _key("The Color Purple")
    assert a != b
    assert title_numbers(a) == title_numbers(b) == []


# --- ported: test_not_duplicates ----------------------------------------------


@pytest.mark.parametrize("a,b", [
    ("Rocky II", "Rocky III"),
    ("Treehouse of Horror XXI", "Treehouse of Horror XXII"),
    ("Part 1", "Part 2"),
    ("Rocky XIII", "Rocky XIV"),        # past norm_title's i..xii fold
])
def test_a_number_change_is_a_different_title(a, b):
    assert title_numbers(_key(a)) != title_numbers(_key(b))


def test_unrelated_titles_are_left_to_the_fuzzy_stage():
    a, b = _key("Pantin de chair"), _key("Flesh Puppet")
    assert a != b
    assert title_numbers(a) == title_numbers(b)


# --- ported: test_numbers_reads_large_roman_numerals --------------------------


def test_numbers_reads_large_roman_numerals():
    assert title_numbers(_key("Treehouse of Horror XXI")) == [21]


# --- ported: test_romanization_scheme_fold ------------------------------------


@pytest.mark.parametrize("a,b", [
    ("Kazoku o omou toki", "kazoku wo omou toki"),     # particle wo/o
    ("Tōkyō monogatari", "Toukyou monogatari"),        # macron vs ou
    ("Tokyo monogatari", "Toukyou monogatari"),
    ("Shichinin no samurai", "Sitinin no samurai"),    # Hepburn vs Kunrei
    ("Fuji", "Huzi"),
    ("Shimbun", "Shinbun"),                            # m before a labial
])
def test_romanization_schemes_share_a_key(a, b):
    assert romanization_key(_key(a)) == romanization_key(_key(b))


def test_romanization_key_is_needed_for_those_pairs():
    # Without it the keys differ: the fold is a separate step on purpose.
    assert _key("Kazoku o omou toki") != _key("kazoku wo omou toki")
    assert _key("Tōkyō monogatari") != _key("Toukyou monogatari")


def test_romanization_key_merges_real_distinctions_in_ordinary_text():
    # The documented reason it is NOT inside norm_title.
    assert romanization_key("you") == "yo"
    assert romanization_key("door") == romanization_key("dor")


def test_romanization_key_empty():
    assert romanization_key("") == ""


# --- norm_title(trailing_articles=) ------------------------------------------


@pytest.mark.parametrize("raw", [
    "Matrix, The", "Huis, Het", "Amour, L'", "Good, the Bad and the Ugly, The",
    "Robot, I", "Promessi sposi, I",
])
def test_default_leaves_the_comma_form_alone(raw):
    # The compatibility promise: the default is the pre-keyword behaviour,
    # so no existing key or golden pair moves.
    assert norm_title(raw) == norm_title(raw, trailing_articles=False)
    assert norm_title("Matrix, The") == "matrix the"


@pytest.mark.parametrize("inverted,proper", [
    ("Matrix, The", "The Matrix"),
    ("Amour, L’", "L'Amour"),                     # curly apostrophe
    ("Huis, Het", "Het Huis"),                    # not in _ARTICLES: kept, both ways
    ("Good, the Bad and the Ugly, The", "The Good, the Bad and the Ugly"),
    ("Hobbit, Lo", "Lo Hobbit"),
])
def test_trailing_article_folds_like_the_title_proper(inverted, proper):
    assert _key(inverted) == norm_title(proper)


def test_italian_rule_still_decides_i_after_un_inverting():
    # The 0.69.0 rule runs on the un-inverted title: 'i' is stripped only
    # before an Italian plural, so the English pronoun keeps its old key.
    assert _key("Promessi sposi, I") == "promessi sposi" == norm_title("I promessi sposi")
    assert _key("Matrix, I") == "1 matrix"
    assert _key("Robot, I") == norm_title("I, Robot") == "1 robot"


def test_trailing_articles_with_strip_articles_false():
    kept = norm_title("Matrix, The", False, trailing_articles=True)
    assert kept == "the matrix" == norm_title("The Matrix", False)


@pytest.mark.parametrize("raw,expected", [
    ("Paris, Texas", "paris texas"),          # not an article
    ("Love, Them", "love them"),              # only a whole final word counts
    ("Matrix,The", "matrix"),                 # no space after the comma
    ("The", "the"),                           # one word: nothing to move
])
def test_trailing_article_edges(raw, expected):
    assert _key(raw) == expected


def test_trailing_articles_is_keyword_only():
    with pytest.raises(TypeError):
        norm_title("Matrix, The", True, True)


# --- title_numbers ------------------------------------------------------------


@pytest.mark.parametrize("text,expected", [
    ("", []),
    ("rocky", []),
    ("treehouse of horror xxi", [21]),
    ("TREEHOUSE OF HORROR XXI", [21]),         # any case
    ("rocky xiii", [13]),
    ("mcmxc", [1990]),
    ("2 fast 2 furious", [2, 2]),              # a multiset, sorted
    ("ocean s 13 xlii", [13, 42]),
    ("dial m for murder", []),                 # one letter: an initial
    ("a civil action", []),                    # not well formed: not a number
    ("mild", []),
    ("did", []),
    ("mix", [1009]),                           # well formed: counts (known limit)
])
def test_title_numbers(text, expected):
    assert title_numbers(text) == expected


def test_title_numbers_reads_single_letters_only_through_the_key():
    assert title_numbers("Rocky V") == []
    assert title_numbers(norm_title("Rocky V")) == [5]
    assert title_numbers(norm_title("Rocky Five")) == [5]


def test_mild_and_wild_are_not_a_number_change():
    # LanguageTool's numbers() read 'mild' as 1449, so this one-letter typo
    # scored 0 (a number change). The well-formed test is the fix.
    assert title_numbers(_key("Mild Things")) == title_numbers(_key("Wild Things"))
