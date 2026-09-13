"""Names and titles built from initials around an ampersand (python-tools
finding, 2026-09-12). The wrong answer here was silent: `A&E` collided with
anything else reducing to "a and and", and a scorer comparing associated
organisations through norm_name would never have said why."""
import pytest

from eidr_core.normalize import norm_name, norm_title


@pytest.mark.parametrize("raw, expected", [
    ("A&E Networks LLC", "a and e networks llc"),
    ("A&E", "a and e"),
    ("V&A", "v and a"),
    ("I&I", "i and i"),
    ("X&Y", "x and y"),
    ("A & E Television Networks", "a and e television networks"),
    ("E", "e"),
])
def test_initials_beside_an_ampersand_are_neither_conjunctions_nor_numerals(raw, expected):
    assert norm_name(raw) == expected
    # with article stripping ON: the leading A of A&E is an initial, not an article
    assert norm_title(raw) == expected


def test_a_real_article_is_still_stripped_from_a_title():
    assert norm_title("The A&E Story") == "a and e story"
    assert norm_title("A Story") == "story"


@pytest.mark.parametrize("raw, expected", [
    ("Simon & Schuster", "simon and schuster"),
    ("AT&T", "at and t"),
    ("M&M", "m and m"),
    ("Juan y María", "john and mary"),        # the conjunction alias still applies mid-name
    ("Disney, Walt", "walter disney"),        # inversion and nickname expansion unchanged
])
def test_everything_else_normalises_as_before(raw, expected):
    assert norm_name(raw) == expected


def test_the_mutation_that_this_pins():
    """Aliasing the boundary letters again would collapse two real parties."""
    assert norm_name("A&E Networks") != norm_name("Y&E Networks")
