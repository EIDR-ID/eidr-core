"""AltIDTool format: the strict feed parser and the edit-file superset.

Why (2026-09-11): python-tools' ``AltIDTool`` reads removal lines (1 or 2
columns, or an empty value) that the v1 spec never described, so a vendored
``altidtool_io`` would have broken its removal path. ``parse_edit_line`` is
the superset; ``parse_line`` stays strict so a feed generator can never emit
a removal by accident. Both directions are pinned here.

Spec v1.6 (operator ruling 2026-10-19) narrowed removals to two valid forms
-- a named type, and Proprietary with its domain -- and refuses the rest,
every spelling of remove-all first among them.
"""
from __future__ import annotations

import pytest

from eidr_core.altidtool_io import (
    AltIdRemoval,
    AltIdRow,
    format_line,
    parse_edit_line,
    parse_line,
)

ID = "10.5240/7791-8534-2C23-9030-8610-5"


@pytest.mark.parametrize("line,expected", [
    (f"{ID}\tIMDB\ttt0133093", AltIdRow(ID, "IMDB", "tt0133093")),
    (f"{ID}\tProprietary\t603\tthemoviedb.org/movie",
     AltIdRow(ID, "Proprietary", "603", "themoviedb.org/movie")),
    (f"{ID}\tIMDB\ttt9999999\t\tDeprecated", AltIdRow(ID, "IMDB", "tt9999999", "", "Deprecated")),
    (f"{ID}\tIMDB\ttt0133093\t\t", AltIdRow(ID, "IMDB", "tt0133093")),   # fixed-5 dialect
])
def test_parse_line_accepts_the_three_widths_and_the_fixed_five_dialect(line, expected):
    assert parse_line(line) == expected
    assert parse_edit_line(line) == expected


@pytest.mark.parametrize("line", [ID, f"{ID}\tIMDB", "a\tb\tc\td\te\tf"])
def test_parse_line_stays_strict(line):
    with pytest.raises(ValueError, match="not an AltIDTool line"):
        parse_line(line)


# Dictionary audit 2026-10-02; 0.68.0. Both of these used to come back as
# rows: an empty Value as value='' (a removal handed to addition-only code)
# and a // comment with the comment text as the EIDR ID. parse_edit_line
# reads the same lines as a removal and a comment; that is unchanged.
@pytest.mark.parametrize("line", [
    f"{ID}\tIMDB\t",            # three columns, empty Value: a removal per the spec
    f"{ID}\tIMDB\t \t",         # whitespace-only Value is empty too
    f"{ID}\tIMDB\t\t\t",        # fixed-5 dialect with no Value
])
def test_parse_line_refuses_an_empty_value(line):
    with pytest.raises(ValueError, match="empty Value"):
        parse_line(line)
    assert parse_edit_line(line) == AltIdRemoval(ID, "IMDB")


@pytest.mark.parametrize("line", ["// c\tx\ty", "  // note\tIMDB\ttt1\n"])
def test_parse_line_refuses_a_comment(line):
    with pytest.raises(ValueError, match="comment"):
        parse_line(line)
    assert parse_edit_line(line) is None


@pytest.mark.parametrize("line,expected", [
    (f"{ID}\tIMDB\r\n", AltIdRemoval(ID, "IMDB")),       # remove every IMDB
    (f"{ID}\tIMDB\t", AltIdRemoval(ID, "IMDB")),         # empty value == removal of the type
    (f"  {ID}  \t IMDB \t tt0133093 ", AltIdRow(ID, "IMDB", "tt0133093")),  # per-column trim
    ("", None), ("   \n", None), ("// a comment\n", None),
])
def test_parse_edit_line_reads_removals_and_comments(line, expected):
    assert parse_edit_line(line) == expected


# Spec v1.6, operator ruling 2026-10-19: "Refuse removing all alt IDs. The
# pattern ID<tab>Proprietary<tab><tab>Domain should remove all IDs of that
# domain only (Proprietary by itself without a domain should be refused)."
# Every removal the ruling leaves valid is pinned first, then every refused
# spelling. A refused line used to come back as a removal that removed MORE
# than its author meant, which is silent until the registry has lost the IDs.

@pytest.mark.parametrize("line,expected", [
    # Named-type removals are unchanged, in every width that means them.
    (f"{ID}\tIMDB", AltIdRemoval(ID, "IMDB")),
    (f"{ID}\tISAN\t", AltIdRemoval(ID, "ISAN")),
    (f"{ID}\tIMDB\t\t\t", AltIdRemoval(ID, "IMDB")),                # fixed-5, no value
    # The domain-scoped Proprietary removal, the one new valid form.
    (f"{ID}\tProprietary\t\tthemoviedb.org/movie",
     AltIdRemoval(ID, "Proprietary", "themoviedb.org/movie")),
    (f"{ID}\tProprietary\t\tthemoviedb.org/movie\t",                # fixed-5 trailing tab
     AltIdRemoval(ID, "Proprietary", "themoviedb.org/movie")),
    (f"{ID}\t proprietary \t \t wikidata.org \n",                   # case and per-column trim
     AltIdRemoval(ID, "proprietary", "wikidata.org")),
])
def test_parse_edit_line_valid_removals(line, expected):
    assert parse_edit_line(line) == expected


def test_a_named_type_removal_carries_no_domain():
    # A caller matching on domain must see '' for a named type, so the two
    # shapes are told apart by the field, not by the type string alone.
    removal = parse_edit_line(f"{ID}\tIMDB")
    assert isinstance(removal, AltIdRemoval) and removal.domain == ""


@pytest.mark.parametrize("line", [
    ID,                                   # one column
    f"{ID}\n",
    f"{ID}\t",                            # stray tab
    f"{ID}\t\t",                          # stray tabs
    f"{ID}\t\t\t",
    f"{ID}\t\t\t\t",
    f"{ID}\t \t ",                        # whitespace-only Type and Value
    f"{ID}\t\t\tthemoviedb.org/movie",    # a domain with no type
    f"{ID}\t\t\t\tDeprecated",            # a relation with no type
])
def test_parse_edit_line_refuses_every_remove_all(line):
    with pytest.raises(ValueError, match="no Type would remove every Alt ID"):
        parse_edit_line(line)


@pytest.mark.parametrize("line", [
    f"{ID}\tProprietary",
    f"{ID}\tProprietary\t",
    f"{ID}\tProprietary\t\t",
    f"{ID}\tProprietary\t\t\t",
    f"{ID}\tPROPRIETARY",                 # the type compares without case
])
def test_parse_edit_line_refuses_proprietary_without_a_domain(line):
    with pytest.raises(ValueError, match="must name its Domain"):
        parse_edit_line(line)


def test_parse_edit_line_refuses_a_domain_on_a_named_type_removal():
    # Before v1.6 the domain was dropped and the WHOLE type was removed.
    with pytest.raises(ValueError, match="Proprietary removals only"):
        parse_edit_line(f"{ID}\tIMDB\t\timdb.com")


@pytest.mark.parametrize("line", [
    f"{ID}\tIMDB\t\t\tDeprecated",
    f"{ID}\tProprietary\t\twikidata.org\tIsSameAs",
])
def test_parse_edit_line_refuses_a_relation_on_a_removal(line):
    # Before v1.6 the relation was dropped and every relation's IDs removed.
    with pytest.raises(ValueError, match="carries no Relation"):
        parse_edit_line(line)


@pytest.mark.parametrize("line", [
    f"{ID}\t\ttt0133093",
    f"{ID}\t\t603\tthemoviedb.org/movie",
])
def test_parse_edit_line_refuses_a_value_with_no_type(line):
    # Dictionary audit 2026-10-02: this came back as an AltIdRow with an
    # empty Type, which the AltIDTool cannot place.
    with pytest.raises(ValueError, match="a Value with no Type"):
        parse_edit_line(line)


def test_alt_id_removal_still_constructs_without_a_domain():
    # The domain field was added with a default (v1.6) so existing
    # constructors and attribute readers keep working.
    assert AltIdRemoval(ID, "IMDB") == AltIdRemoval(ID, "IMDB", "")
    assert AltIdRemoval(ID, "IMDB").alt_type == "IMDB"


def test_parse_edit_line_refuses_a_line_without_an_id_and_over_five_columns():
    with pytest.raises(ValueError, match="no EIDR ID"):
        parse_edit_line("\tIMDB\ttt1")
    with pytest.raises(ValueError, match="6 columns"):
        parse_edit_line("a\tb\tc\td\te\tf")


def test_format_line_round_trips_through_both_parsers():
    for row in (AltIdRow(ID, "IMDB", "tt1"),
                AltIdRow(ID, "Proprietary", "Q42", "wikidata.org", "IsEntirelyContainedBy"),
                AltIdRow(ID, "IMDB", "tt2", "", "Deprecated")):
        line = format_line(*row)
        assert parse_line(line) == row and parse_edit_line(line) == row
