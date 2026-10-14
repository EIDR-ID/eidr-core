"""bmr_io.fix_shared_strings must keep every cell value exactly (0.51.0).

Until 0.51.0 it decoded each inline string with ``html.unescape``, an HTML5
decoder, which maps numeric references 128-159 to Windows-1252: a C1 control
character such as U+0096 (written by openpyxl as ``&#150;``) came back as an
en dash. python-tools found it on 2026-10-14 exporting the production Service
registry; nothing reported the change. The wrong answer is a plausible value,
which is why this is tested here.
"""
from __future__ import annotations

import pytest

from eidr_core.bmr_io import fix_shared_strings

openpyxl = pytest.importorskip("openpyxl")

VALUES = [
    "SIC \x96 Internacional",          # C1: the case that changed
    "\x80\x85\x9f",                    # the rest of the HTML5-remapped range edges
    "Tom & Jerry <Pilot> \"quoted\" 'apos'",
    "Amélie – 日本",  # real en dash, accents, CJK stay as they are
    "  leading and trailing  ",
    "&amp; literally",                  # an ampersand-entity TEXT, not an entity
]


def _inline_cell(ref: str, value: str) -> str:
    """One inline-string cell as a writer produces it: XML-escaped, and C1
    characters as numeric references (openpyxl writes U+0096 as ``&#150;``)."""
    from xml.sax.saxutils import escape
    text = "".join(f"&#{ord(c)};" if 0x80 <= ord(c) <= 0x9F else c
                   for c in escape(value, {'"': "&quot;", "'": "&apos;"}))
    return f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>'


def test_every_value_survives_byte_for_byte(tmp_path):
    import zipfile
    path = tmp_path / "book.xlsx"
    wb = openpyxl.Workbook()
    wb.active["A1"] = "placeholder"
    wb.save(path)
    # Replace the sheet with inline-string cells, the shape write_sheet's
    # output has before this pass.
    rows = "".join(f'<row r="{i}">{_inline_cell(f"A{i}", v)}</row>'
                   for i, v in enumerate(VALUES, start=1))
    sheet = ('<?xml version="1.0" encoding="UTF-8"?>'
             '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
             f"<sheetData>{rows}</sheetData></worksheet>")
    src = tmp_path / "src.xlsx"
    with zipfile.ZipFile(path) as zin, zipfile.ZipFile(src, "w") as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename == "xl/worksheets/sheet1.xml":
                data = sheet.encode("utf-8")
            elif info.filename == "xl/sharedStrings.xml":
                continue  # the placeholder's; this sheet no longer uses it
            zout.writestr(info, data)
    fix_shared_strings(str(src))
    back = openpyxl.load_workbook(src).active
    assert [back.cell(i, 1).value for i in range(1, len(VALUES) + 1)] == VALUES


def test_the_xml_decoder_is_xmls_not_htmls():
    from eidr_core.bmr_io import _xml_unescape
    assert _xml_unescape("SIC &#150; x") == "SIC \x96 x"
    assert _xml_unescape("&#x96;&amp;&lt;&gt;&quot;&apos;") == "\x96&<>\"'"
    assert _xml_unescape("&nbsp; &eacute;") == "&nbsp; &eacute;"  # not XML entities
