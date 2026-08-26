"""Parity tests for the shared BMR reader — the two defects it must not have.

Why these exist (2026-08-25, XML_to_JSON handoff `bmr-io-adoption`)
-------------------------------------------------------------------
``eidr_core.bmr_io``'s reader half is asked to replace XML_to_JSON's local
codec on the strength of two claims made only in its DOCSTRING:

* ``read_sheet`` scans the full header width, so a spacer column does not
  hide every column to its right;
* ``family_layout`` is sparse and index-preserving, so a blank group 1
  cannot shift later groups' companion columns.

A consumer is being asked to delete working code and depend on those
claims. Until now nothing verified them — the shared reader's correctness
was asserted, not tested, which is the same "documented but unproven"
shape that let the SDK's 1243-test suite certify a bug (register R5). So
both claims are pinned here, in the terms of the defects they prevent,
BEFORE the adoption lands rather than after.

These are also the fixtures the handoff's §6 asked for: they double as the
executable spec of what an adopting consumer should expect to get back.
"""
from __future__ import annotations

import pytest

from eidr_core.bmr_io import (
    DATA_START,
    HEADER_ROW,
    family_layout,
    read_headers,
    read_sheet,
)

# openpyxl is the `bmr` extra — the reader half is the only part of bmr_io
# that needs it, so a base install legitimately cannot run these.
openpyxl = pytest.importorskip("openpyxl")

SHEET = "Episodics"


def _write_sheet(path, header_row: list, data_rows: list[list]) -> str:
    """Build a minimal BMR-shaped workbook: banner rows 1-2, headers on row
    3, data from row 4 — the layout every EIDR template uses."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = SHEET
    ws.cell(1, 1).value = "EIDR BMR (test fixture)"
    for col, val in enumerate(header_row, 1):
        if val is not None:
            ws.cell(HEADER_ROW, col).value = val
    for r, row in enumerate(data_rows, DATA_START):
        for col, val in enumerate(row, 1):
            if val is not None:
                ws.cell(r, col).value = val
    p = str(path / "fixture.xlsx")
    wb.save(p)
    return p


# ---------------------------------------------------------------------------
# Defect 1 — header scan must not stop at the first blank header cell.
#
# XML_to_JSON's codec built its header list with `for c in ws[3]: if blank:
# break`, so every column right of a spacer was invisible. Stock EIDR data
# tabs happen to carry no mid-row spacer (verified across all seven
# Template-22 workbooks 2026-08-25 — the spacers live in the `Code Tables`
# tabs, which the codec never reads), so this is latent rather than live.
# It stops being latent the moment a template adds a spacer or an operator
# clears a header cell.
# ---------------------------------------------------------------------------

def test_spacer_column_does_not_truncate_the_header_map(tmp_path):
    headers, _ = read_sheet(
        _write_sheet(tmp_path,
                     ["Unique Row ID", "Title", None, "Release Date"],
                     [["1", "A Film", None, "2020-01-01"]]),
        SHEET,
    )
    # Column 3 is the spacer: absent from the map, but columns after it
    # survive with their TRUE 1-based indices (not renumbered).
    assert headers == {1: "Unique Row ID", 2: "Title", 4: "Release Date"}


def test_values_right_of_a_spacer_are_not_dropped(tmp_path):
    _, rows = read_sheet(
        _write_sheet(tmp_path,
                     ["Unique Row ID", "Title", None, "Release Date"],
                     [["1", "A Film", None, "2020-01-01"]]),
        SHEET,
    )
    # The defect's real cost: a column read as absent is written back as
    # empty under a read-modify-write round trip, producing a well-formed
    # workbook with data silently missing.
    assert rows == [{"Unique Row ID": "1", "Title": "A Film",
                     "Release Date": "2020-01-01"}]


def test_multiple_spacers_and_a_trailing_blank(tmp_path):
    headers, rows = read_sheet(
        _write_sheet(tmp_path,
                     ["A", None, "B", None, None, "C", None],
                     [["1", None, "2", None, None, "3", None]]),
        SHEET,
    )
    assert headers == {1: "A", 3: "B", 6: "C"}
    assert rows == [{"A": "1", "B": "2", "C": "3"}]


# ---------------------------------------------------------------------------
# Defect 2 — companion columns must pair on the sheet's OWN group index.
#
# XML_to_JSON's `_collect_alt_titles` densified `Alternate Title N` (drop
# blanks, renumber from 1) and only then paired each with `Alt Title Class
# {i}` / `Alt Title Language {i}` using the DENSE position. A blank group 1
# therefore hands group 2's title the metadata of group 1 — not merely a
# shift, but a real title tagged with the wrong language code.
# ---------------------------------------------------------------------------

ALT_MEMBERS = ["Alternate Title", "Alt Title Class", "Alt Title Language"]

ALT_HEADERS = [
    "Alternate Title 1", "Alt Title Class 1", "Alt Title Language 1",
    "Alternate Title 2", "Alt Title Class 2", "Alt Title Language 2",
    "Alternate Title 3", "Alt Title Class 3", "Alt Title Language 3",
]


def test_family_layout_preserves_original_group_indices():
    layout = family_layout(ALT_HEADERS, ALT_MEMBERS)
    assert sorted(layout) == [1, 2, 3]
    assert layout[2] == {
        "Alternate Title": "Alternate Title 2",
        "Alt Title Class": "Alt Title Class 2",
        "Alt Title Language": "Alt Title Language 2",
    }


def test_blank_group_one_does_not_shift_companion_pairing(tmp_path):
    """The end-to-end defect-2 scenario, in the shape a consumer meets it.

    Group 1's TITLE is blank while its class/language cells still carry
    leftover values — exactly the workbook state that made the densifying
    codec hand 'Le Film' the class 'AKA' and the language 'en'.
    """
    path = _write_sheet(
        tmp_path,
        ALT_HEADERS,
        [[None, "AKA", "en",
          "Le Film", "translated", "fr",
          "El Filme", "translated", "es"]],
    )
    headers, rows = read_sheet(path, SHEET)
    row = rows[0]
    layout = family_layout(headers.values(), ALT_MEMBERS)

    paired = [
        (row[grp["Alternate Title"]],
         row.get(grp.get("Alt Title Class", "")),
         row.get(grp.get("Alt Title Language", "")))
        for _, grp in sorted(layout.items())
        if grp.get("Alternate Title") and row.get(grp["Alternate Title"])
    ]

    # Each title keeps ITS OWN language. Under the densifying codec this
    # asserted ("Le Film", "AKA", "en") — a French title labelled English.
    assert paired == [
        ("Le Film", "translated", "fr"),
        ("El Filme", "translated", "es"),
    ]


def test_family_layout_treats_a_bare_member_as_group_one():
    # `count_family` counts a bare name as group 1; the layout must agree,
    # or the two disagree about how wide a family is.
    layout = family_layout(["Alternate Title", "Alt Title Class"], ALT_MEMBERS)
    assert layout[1]["Alternate Title"] == "Alternate Title"


def test_numbered_group_one_beats_a_bare_duplicate():
    layout = family_layout(["Alternate Title", "Alternate Title 1"], ALT_MEMBERS)
    assert layout[1]["Alternate Title"] == "Alternate Title 1"


# ---------------------------------------------------------------------------
# Stop rules — the parameter that let one reader serve three consumers.
# XML_to_JSON's codec is the `blank_row` caller; getting this wrong
# truncates a sheet mid-read, so each rule is pinned explicitly.
# ---------------------------------------------------------------------------

STOP_HEADERS = ["Unique Row ID", "Title"]
STOP_ROWS = [
    ["1", "First"],
    [None, "Orphaned"],     # blank first column, row not blank
    ["3", "Third"],
    [None, None],           # fully blank row
    ["5", "After the gap"],
]


def test_stop_blank_row_halts_at_the_first_fully_blank_row(tmp_path):
    _, rows = read_sheet(_write_sheet(tmp_path, STOP_HEADERS, STOP_ROWS),
                         SHEET, stop="blank_row")
    assert [r.get("Title") for r in rows] == ["First", "Orphaned", "Third"]


def test_stop_blank_first_col_halts_when_column_a_empties(tmp_path):
    _, rows = read_sheet(_write_sheet(tmp_path, STOP_HEADERS, STOP_ROWS),
                         SHEET, stop="blank_first_col")
    assert [r.get("Title") for r in rows] == ["First"]


def test_stop_none_skips_blank_rows_instead_of_stopping(tmp_path):
    # Chunked BMR output carries trailing pre-allocated empty rows, so for
    # the combine reader a blank row is padding, never end-of-data.
    _, rows = read_sheet(_write_sheet(tmp_path, STOP_HEADERS, STOP_ROWS),
                         SHEET, stop=None)
    assert [r.get("Title") for r in rows] == [
        "First", "Orphaned", "Third", "After the gap"]


def test_unknown_stop_rule_is_rejected_loudly(tmp_path):
    # A typo'd stop rule must not silently degrade to "read everything".
    with pytest.raises(ValueError, match="unknown stop rule"):
        read_sheet(_write_sheet(tmp_path, STOP_HEADERS, STOP_ROWS),
                   SHEET, stop="blank-row")


def test_missing_sheet_names_what_it_found(tmp_path):
    with pytest.raises(ValueError, match="expected sheet"):
        read_sheet(_write_sheet(tmp_path, STOP_HEADERS, STOP_ROWS),
                   "No Such Tab")


# ---------------------------------------------------------------------------
# One header policy, two entry points (reconciled 2026-08-25).
#
# `read_headers` (live worksheet, random access) and `read_sheet` (path,
# streaming read-only) reach the header row differently for a real
# performance reason, but must agree on what a header IS. They duplicated
# that policy until both were routed through `_header_map`; these pin the
# agreement so the copies cannot re-diverge silently.
# ---------------------------------------------------------------------------

def test_both_entry_points_return_the_same_header_map(tmp_path):
    hdrs = ["Unique Row ID", "Title", None, "  Padded  ", "", "Release Date"]
    path = _write_sheet(tmp_path, hdrs, [["1", "A", None, "x", None, "2020"]])

    from_sheet, _ = read_sheet(path, SHEET)
    wb = openpyxl.load_workbook(path)          # live worksheet, not read-only
    try:
        from_ws = read_headers(wb[SHEET])
    finally:
        wb.close()

    assert from_ws == from_sheet
    # ...and both apply the policy: trimmed, blanks skipped, true indices.
    assert from_ws == {1: "Unique Row ID", 2: "Title", 4: "Padded",
                       6: "Release Date"}


def test_header_order_is_sheet_order_past_column_z(tmp_path):
    """The integer-key contract, asserted the way consumers rely on it.

    Both XML_to_JSON call sites recover sheet order with
    ``[m[c] for c in sorted(m)]``. That identity holds only because the
    keys are integers: as column LETTERS, ``'AA'`` sorts before ``'B'``
    and everything past Z is silently reordered — values follow their
    misplaced headers, presenting as a data-mapping bug in the consumer
    with nothing pointing back at bmr_io. Stock templates reach 602
    columns, so this is well past hypothetical.

    Asserted against an independently constructed expectation rather than
    anything derived from the reader, so it fails on scrambling rather
    than agreeing with it.
    """
    names = [f"Col {i:03d}" for i in range(1, 61)]   # 60 cols: A..BH
    path = _write_sheet(tmp_path, names, [[f"v{i:03d}" for i in range(1, 61)]])

    headers, rows = read_sheet(path, SHEET)
    assert [headers[c] for c in sorted(headers)] == names
    assert sorted(headers) == list(range(1, 61))     # ints, contiguous

    wb = openpyxl.load_workbook(path)
    try:
        from_ws = read_headers(wb[SHEET])
    finally:
        wb.close()
    assert [from_ws[c] for c in sorted(from_ws)] == names
    # Values still track their own headers past Z.
    assert rows[0]["Col 060"] == "v060"


def test_read_headers_accepts_a_discovered_header_row(tmp_path):
    """The parameter that lets BMR-Review adopt the shared reader.

    Its workbooks come back from review with the header row no longer
    reliably at row 3, so it locates the row by searching for a known
    column. Before this argument existed the shared reader simply could
    not serve that caller, which is why a second implementation survived.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = SHEET
    # Header row pushed to row 5 by two inserted banner rows.
    for col, val in enumerate(["Unique Row ID", None, "Title"], 1):
        if val:
            ws.cell(5, col).value = val
    p = str(tmp_path / "shifted.xlsx")
    wb.save(p)

    wb2 = openpyxl.load_workbook(p)
    try:
        ws2 = wb2[SHEET]
        found = next(r for r in range(1, ws2.max_row + 1)
                     if any(ws2.cell(r, c).value == "Unique Row ID"
                            for c in range(1, ws2.max_column + 1)))
        assert found == 5
        assert read_headers(ws2, found) == {1: "Unique Row ID", 3: "Title"}
        # The default still points at the template's row 3, which is empty
        # here — the parameter widens the contract without changing it.
        assert read_headers(ws2) == {}
    finally:
        wb2.close()
