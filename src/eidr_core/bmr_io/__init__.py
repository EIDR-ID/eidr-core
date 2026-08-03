"""BMR workbook-surgery primitives — THE shared implementation.

Extracted 2026-08-03 (register Phase 3 item 1 / OVERLAPS rows 1-2) from
eidr-wikidata ``bmr/writer.py`` (canonical), unifying the audit copy in
BMR-Review that had drifted from it. Six primitives, canonical semantics:

* ``read_headers(ws)`` — header-row map {col_index: header_text}.
* ``count_family(headers, primary)`` — how many numbered copies of a family
  the template carries (returns the MAX index — robust to gaps, unlike the
  old audit-copy count-of-matches).
* ``rightmost_in(headers, members)`` — rightmost column of a family.
* ``expand_family(ws, primary, anchor_members, insert_members, want, headers)``
  — add family groups. The anchor/insert split is the operator's 2026-05-09
  direction (anchor = existing group-1 columns used to find the insertion
  point; insert = which columns new groups actually add). The pre-split
  behavior is the special case ``anchor_members=members, insert_members=members``
  (how the BMR-Review audit writer calls it).
* ``transplant(template_xlsx, edited_xlsx)`` — swap edited worksheet XML +
  shared strings into the template, preserving formulas/validations/macros.
* ``fix_shared_strings(xlsx_path)`` — inlineStr -> shared-string conversion
  for EPPlus-based BMR tooling compatibility.

Orchestration stays per-consumer BY DESIGN: eidr-wikidata's typed
``BMRWriter``/``FAMILIES`` and BMR-Review's dict-based multi-template
``write_bmr_files`` serve different jobs; only the workbook surgery was
duplicated. Full reader/writer consolidation (bmr_io reader) remains open.
"""
from __future__ import annotations

import html
import logging
import os
import re
import shutil
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from typing import Optional

log = logging.getLogger(__name__)

# Row 3 carries the column headers in every EIDR BMR template
# (identical in both pre-extraction writers).
HEADER_ROW = 3

__all__ = ["HEADER_ROW", "read_headers", "count_family", "rightmost_in",
           "expand_family", "transplant", "fix_shared_strings"]


def read_headers(ws) -> dict[int, str]:
    out: dict[int, str] = {}
    for c in range(1, ws.max_column + 1):
        v = ws.cell(HEADER_ROW, c).value
        if v is not None:
            s = str(v).strip()
            if s:
                out[c] = s
    return out

def count_family(headers: dict[int, str], primary: str) -> int:
    best = 0
    for h in headers.values():
        if h == primary:
            best = max(best, 1)
        elif h.startswith(primary + " "):
            try:
                best = max(best, int(h[len(primary) + 1:]))
            except ValueError:
                pass
    return best

def rightmost_in(headers: dict[int, str], members: list[str]) -> Optional[int]:
    right: Optional[int] = None
    for col, h in headers.items():
        for m in members:
            if h == m or h.startswith(m + " "):
                right = max(right, col) if right is not None else col
    return right

def expand_family(ws, primary: str,
                   anchor_members: list[str], insert_members: list[str],
                   want: int, headers: dict[int, str]) -> None:
    """Add ``want - have`` new groups for the given family.

    ``anchor_members`` drives where new groups land (rightmost match
    in template). ``insert_members`` drives what columns are added
    per group; on each iteration the anchor advances by
    ``len(insert_members)`` to keep new groups packed together.
    """
    have = count_family(headers, primary)
    if want <= have:
        return
    anchor_col = rightmost_in(headers, anchor_members)
    if anchor_col is None:
        log.warning("No anchor column for family '%s' — skipping", primary)
        return
    for n in range(have + 1, want + 1):
        insert_at = anchor_col + 1
        ws.insert_cols(insert_at, len(insert_members))
        new_hdrs = [f"{m} {n}" for m in insert_members]
        for i, h in enumerate(new_hdrs):
            ws.cell(HEADER_ROW, insert_at + i).value = h
        # Shift headers dict right for moved columns
        shifted = {}
        for col, h in headers.items():
            shifted[col + len(insert_members) if col >= insert_at else col] = h
        for i, h in enumerate(new_hdrs):
            shifted[insert_at + i] = h
        headers.clear()
        headers.update(shifted)
        anchor_col += len(insert_members)   # keep anchor pointing at last inserted

def transplant(template_xlsx: str, edited_xlsx: str) -> None:
    out_dir = os.path.dirname(os.path.abspath(template_xlsx)) or "."
    fd, tmp = tempfile.mkstemp(suffix=".xlsx", dir=out_dir)
    os.close(fd)
    try:
        with (zipfile.ZipFile(template_xlsx, "r") as zt,
              zipfile.ZipFile(edited_xlsx, "r") as ze):
            t_names = {i.filename for i in zt.infolist()}
            e_names = {i.filename for i in ze.infolist()}
            replace_ws = [n for n in t_names
                          if n.startswith("xl/worksheets/") and n.endswith(".xml")
                          and n in e_names]
            replace_ss = "xl/sharedStrings.xml" in e_names
            with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as zn:
                for info in zt.infolist():
                    nm = info.filename
                    if nm in replace_ws:
                        continue
                    if replace_ss and nm == "xl/sharedStrings.xml":
                        continue
                    zn.writestr(info, zt.read(nm))
                for nm in replace_ws:
                    zn.writestr(nm, ze.read(nm))
                if replace_ss:
                    zn.writestr("xl/sharedStrings.xml", ze.read("xl/sharedStrings.xml"))
        os.replace(tmp, template_xlsx)
    finally:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass

def fix_shared_strings(xlsx_path: str) -> None:
    """Convert inlineStr cells to shared-string references for EPPlus compatibility."""
    out_dir = os.path.dirname(os.path.abspath(xlsx_path)) or "."
    fd, tmp = tempfile.mkstemp(suffix=".xlsx", dir=out_dir)
    os.close(fd)
    try:
        with zipfile.ZipFile(xlsx_path, "r") as z_in:
            names = set(z_in.namelist())
            sl: list[str] = []
            si: dict[str, int] = {}
            total = 0

            if "xl/sharedStrings.xml" in names:
                try:
                    root = ET.fromstring(z_in.read("xl/sharedStrings.xml"))
                    ns = root.tag.split("}")[0].strip("{")
                    for ssi in root.findall(f"{{{ns}}}si"):
                        s = "".join(t.text or "" for t in ssi.findall(f".//{{{ns}}}t"))
                        si[s] = len(sl); sl.append(s)
                except Exception:
                    sl, si = [], {}

            def _add(s: str) -> int:
                if s in si:
                    return si[s]
                idx = len(sl); si[s] = idx; sl.append(s); return idx

            cell_re = re.compile(rb'(<c\b[^>]*\bt="inlineStr"[^>]*>)(\s*<is>.*?</is>\s*)(</c>)', re.DOTALL)
            t_re    = re.compile(rb'<t(?:\s+[^>]*)?>(.*?)</t>', re.DOTALL)
            changed: dict[str, bytes] = {}

            for part in names:
                if not (part.startswith("xl/worksheets/") and part.endswith(".xml")):
                    continue
                xml = z_in.read(part)
                if b't="inlineStr"' not in xml:
                    continue

                def _sub(m: re.Match) -> bytes:
                    nonlocal total
                    texts = []
                    for tm in t_re.finditer(m.group(2)):
                        try:
                            texts.append(html.unescape(tm.group(1).decode("utf-8")))
                        except Exception:
                            texts.append(html.unescape(tm.group(1).decode("utf-8", "replace")))
                    idx = _add("".join(texts)); total += 1
                    return re.sub(rb't="inlineStr"', b't="s"', m.group(1), 1) + \
                           f"<v>{idx}</v>".encode() + m.group(3)

                changed[part] = cell_re.sub(_sub, xml)

            if not changed:
                return

            ss_ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
            root2 = ET.Element(f"{{{ss_ns}}}sst")
            root2.set("count", str(total)); root2.set("uniqueCount", str(len(sl)))
            for s in sl:
                ssi2 = ET.SubElement(root2, f"{{{ss_ns}}}si")
                t2 = ET.SubElement(ssi2, f"{{{ss_ns}}}t")
                if s.startswith(" ") or s.endswith(" ") or "\n" in s or "\t" in s:
                    t2.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
                t2.text = s
            new_ss = ET.tostring(root2, encoding="utf-8", xml_declaration=False)

            ct = z_in.read("[Content_Types].xml")
            if b"sharedStrings.xml" not in ct:
                ct = ct.replace(b"</Types>",
                    b'<Override PartName="/xl/sharedStrings.xml" '
                    b'ContentType="application/vnd.openxmlformats-officedocument'
                    b'.spreadsheetml.sharedStrings+xml"/></Types>')

            with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as z_out:
                for info in z_in.infolist():
                    nm = info.filename
                    if nm in changed:
                        z_out.writestr(info, changed[nm])
                    elif nm == "xl/sharedStrings.xml":
                        z_out.writestr(info, new_ss)
                    elif nm == "[Content_Types].xml":
                        z_out.writestr(info, ct)
                    else:
                        z_out.writestr(info, z_in.read(nm))
                if "xl/sharedStrings.xml" not in names:
                    z_out.writestr("xl/sharedStrings.xml", new_ss)

        os.replace(tmp, xlsx_path)
    finally:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
