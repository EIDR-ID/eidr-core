"""AltIDTool format: the strict feed parser and the edit-file superset.

Why (2026-09-11): python-tools' ``AltIDTool`` reads removal lines (1 or 2
columns, or an empty value) that the v1 spec never described, so a vendored
``altidtool_io`` would have broken its removal path. ``parse_edit_line`` is
the superset; ``parse_line`` stays strict so a feed generator can never emit
a removal by accident. Both directions are pinned here.
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


@pytest.mark.parametrize("line,expected", [
    (f"{ID}\n", AltIdRemoval(ID)),                       # remove every alt ID
    (f"{ID}\tIMDB\r\n", AltIdRemoval(ID, "IMDB")),       # remove every IMDB
    (f"{ID}\tIMDB\t", AltIdRemoval(ID, "IMDB")),         # empty value == removal of the type
    (f"  {ID}  \t IMDB \t tt0133093 ", AltIdRow(ID, "IMDB", "tt0133093")),  # per-column trim
    ("", None), ("   \n", None), ("// a comment\n", None),
])
def test_parse_edit_line_reads_removals_and_comments(line, expected):
    assert parse_edit_line(line) == expected


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
