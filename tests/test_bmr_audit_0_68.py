"""bmr_io fixes from the 2026-10-02 dictionary audit, landed in 0.68.0.

Each of these was a SILENT wrong answer or a crash on a legal file, so each
test builds the awkward-but-legal workbook and reads the result back from
the file, never from a return value:

* ``transplant`` paired worksheets by part path, so a workbook whose parts
  are numbered out of tab order had its tabs' contents swapped.
* ``expand_family`` wrote new headers to row 3 whatever row the caller's
  headers came from.
* ``check_sheet`` (read-only) trusted the sheet's ``<dimension>``: absent,
  it raised TypeError; stale, it hid headers.
"""
from __future__ import annotations

import re
import zipfile

import pytest

from eidr_core.bmr_io import (
    HEADER_ROW,
    TEMPLATES,
    check_sheet,
    expand_family,
    read_headers,
    transplant,
)

openpyxl = pytest.importorskip("openpyxl")


def _rewrite(path, edits) -> None:
    """Rewrite parts of the zip at ``path``: ``edits`` maps part name to a
    function of its bytes. Everything else is copied unchanged."""
    with zipfile.ZipFile(path) as z:
        parts = [(i, z.read(i.filename)) for i in z.infolist()]
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for info, data in parts:
            fn = edits.get(info.filename)
            z.writestr(info, fn(data) if fn else data)


# ── transplant: pair by tab name ─────────────────────────────────────────

def _swap_parts(path) -> None:
    """Make tab 1 live in sheet2.xml and tab 2 in sheet1.xml: swap the two
    parts' contents AND their workbook-rels targets, so the file is still a
    correct workbook with the same tabs holding the same cells, only with
    its parts numbered against tab order."""
    with zipfile.ZipFile(path) as z:
        s1 = z.read("xl/worksheets/sheet1.xml")
        s2 = z.read("xl/worksheets/sheet2.xml")

    def _rels(b: bytes) -> bytes:
        b = b.replace(b"worksheets/sheet1.xml", b"worksheets/@@.xml")
        b = b.replace(b"worksheets/sheet2.xml", b"worksheets/sheet1.xml")
        return b.replace(b"worksheets/@@.xml", b"worksheets/sheet2.xml")

    _rewrite(path, {"xl/worksheets/sheet1.xml": lambda _b: s2,
                    "xl/worksheets/sheet2.xml": lambda _b: s1,
                    "xl/_rels/workbook.xml.rels": _rels})


def test_transplant_pairs_tabs_by_name_when_parts_are_out_of_tab_order(tmp_path):
    template = tmp_path / "template.xlsx"
    wb = openpyxl.Workbook()
    wb.active.title = "A"
    wb.active["A1"] = "template A"
    wb.create_sheet("B")["A1"] = "template B"
    wb.save(template)
    _swap_parts(template)
    # Precondition: the premise of the test holds -- tab A is in sheet2.xml
    # and openpyxl still reads each tab's own cell.
    with zipfile.ZipFile(template) as z:
        assert b"worksheets/sheet2.xml" in z.read("xl/_rels/workbook.xml.rels")
    chk = openpyxl.load_workbook(template)
    assert (chk["A"]["A1"].value, chk["B"]["A1"].value) == ("template A", "template B")

    # The edited copy is what every caller makes: load, change, save. openpyxl
    # renumbers parts in tab order, so A is sheet1.xml here.
    edited = tmp_path / "edited.xlsx"
    wb = openpyxl.load_workbook(template)
    wb["A"]["A1"] = "edited A"
    wb["B"]["A1"] = "edited B"
    wb.save(edited)

    transplant(str(template), str(edited))

    out = openpyxl.load_workbook(template)
    assert out["A"]["A1"].value == "edited A"
    assert out["B"]["A1"].value == "edited B"


def test_transplant_keeps_a_template_tab_the_edited_copy_lacks(tmp_path):
    """A tab with no namesake keeps its own XML; under path pairing it took
    whatever part of the edited file happened to share its number. A number,
    not text: a kept tab's shared-string cells index the EDITED table (see
    the transplant docstring), which is not what this test is about."""
    template = tmp_path / "template.xlsx"
    wb = openpyxl.Workbook()
    wb.active.title = "A"
    wb.active["A1"] = "template A"
    wb.create_sheet("Only here")["A1"] = 42
    wb.save(template)

    edited = tmp_path / "edited.xlsx"
    wb = openpyxl.Workbook()
    wb.active.title = "A"
    wb.active["A1"] = "edited A"
    wb.create_sheet("Renamed")["A1"] = 7
    wb.save(edited)

    transplant(str(template), str(edited))

    out = openpyxl.load_workbook(template)
    assert out["A"]["A1"].value == "edited A"
    assert out["Only here"]["A1"].value == 42


# ── expand_family: header_row ────────────────────────────────────────────

def test_expand_family_writes_new_headers_to_the_given_header_row():
    wb = openpyxl.Workbook()
    ws = wb.active
    for c, h in enumerate(["Unique Row ID", "Actor 1", "Actor 2", "Notes"], 1):
        ws.cell(1, c).value = h
    headers = read_headers(ws, header_row=1)

    expand_family(ws, "Actor", ["Actor"], ["Actor"], 4, headers, header_row=1)

    assert read_headers(ws, header_row=1) == {
        1: "Unique Row ID", 2: "Actor 1", 3: "Actor 2", 4: "Actor 3",
        5: "Actor 4", 6: "Notes"}
    assert headers == read_headers(ws, header_row=1)
    # Nothing was written to the template's header row.
    assert read_headers(ws, header_row=HEADER_ROW) == {}


def test_expand_family_default_header_row_is_unchanged():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.cell(HEADER_ROW, 1).value = "Actor 1"
    headers = read_headers(ws)
    expand_family(ws, "Actor", ["Actor"], ["Actor"], 2, headers)
    assert read_headers(ws) == {1: "Actor 1", 2: "Actor 2"}


# ── check_sheet / read_headers: no or stale <dimension> ─────────────────

SHEET = "Stand-Alone Works"
CANON = list(TEMPLATES["non_episodic"].headers)


@pytest.fixture
def template_sheet(tmp_path):
    """A conforming Stand-Alone Works sheet built from the shipped headers,
    the same way test_bmr_subset builds its source."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = SHEET
    ws.cell(1, 1).value = "EIDR Bulk Metadata Registration"
    for c, h in enumerate(CANON, 1):
        ws.cell(HEADER_ROW, c).value = h
    ws.cell(HEADER_ROW + 1, 1).value = "R1"
    path = tmp_path / "sheet.xlsx"
    wb.save(path)
    return path


def _set_dimension(path, replacement: bytes) -> None:
    def _fix(b: bytes) -> bytes:
        new, n = re.subn(rb"<dimension\b[^>]*/>", replacement, b)
        assert n == 1, "fixture premise: openpyxl wrote one <dimension>"
        return new
    _rewrite(path, {"xl/worksheets/sheet1.xml": _fix})


def test_check_sheet_accepts_a_sheet_with_no_dimension(template_sheet):
    _set_dimension(template_sheet, b"")
    # Premise: read-only openpyxl really does see an unsized sheet.
    wb = openpyxl.load_workbook(template_sheet, read_only=True)
    try:
        assert wb[SHEET].max_column is None
    finally:
        wb.close()

    chk = check_sheet(str(template_sheet), SHEET)
    assert [chk.headers[c] for c in sorted(chk.headers)] == CANON


def test_check_sheet_reads_past_a_stale_dimension(template_sheet):
    """A dimension that under-reports the width used to hide every header
    past it, so the pre-flight refused a sheet subset_rows accepts."""
    _set_dimension(template_sheet, b'<dimension ref="A1:C4"/>')
    chk = check_sheet(str(template_sheet), SHEET)
    assert [chk.headers[c] for c in sorted(chk.headers)] == CANON


def test_read_headers_on_an_unsized_read_only_sheet(template_sheet):
    _set_dimension(template_sheet, b"")
    wb = openpyxl.load_workbook(template_sheet, read_only=True)
    try:
        headers = read_headers(wb[SHEET])
    finally:
        wb.close()
    assert [headers[c] for c in sorted(headers)] == CANON
