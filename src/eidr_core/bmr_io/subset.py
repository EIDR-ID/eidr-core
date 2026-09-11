"""Row-subset COPY of a BMR sheet — the "copy, do not construct" ruling.

Why this exists (register 2026-09-10, BMRtoAltID)
--------------------------------------------------
BMRtoAltID's input IS a BMR sheet, and the rows it wants to send on to
BMR-Review are rows of that sheet. Constructing them from parsed records
would lose every column BMRtoAltID never parses — and BMR-Review scores
some of those. A COPY cannot lose a column; a construction can. So the
reusable piece is not a writer but a subsetter, and it lives here rather
than in the consumer because the second consumer of a BMR sheet subset is
a matter of time, not of design.

Two answers BMRtoAltID asked for before this signature shipped (2026-09-11,
their P0), both baked in rather than documented:

* **There is no ``template=`` parameter.** Template family ("Non-Episodic"),
  file name and data-tab name ("Stand-Alone Works") are three strings for
  one thing, and the tab name is the one the caller already passes. The
  template is resolved from ``sheet_name`` through ``SHEET_TO_TEMPLATE``;
  a tab that is not a Template-22 data sheet is refused with the list.
* **``blank_columns=`` exists**, because the alternative is the consumer
  editing rows after the copy — the exact modification copying exists to
  prevent. Their sheets carry ``Candidates Found`` in ``Assigned EIDR ID``
  on 6,364 of 6,545 rows, written there by BMR-Review's own set-match. Is
  that a pre-fill? Read from BMR-Review's classifier (``classify_tamr``,
  2026-09-11): an ID is an assertion, ``NO MATCH`` is an assertion, and
  ANYTHING else — a sentinel or an empty cell alike — means "candidates:
  read them from ``Registration Errors & Notes``". So the sentinel alone is
  benign, but the notes beside it are not: a re-assessment that leaves the
  old notes in place evaluates the OLD candidate list instead of asking the
  fresh question, and a row that says ``NO MATCH`` asserts one. For a fresh
  assessment, blank BOTH ``Assigned EIDR ID`` and ``Registration Errors &
  Notes``. The blanking is explicit, by header name, refused for a name the
  sheet lacks (a typo must not be a silent no-op), and counted in the
  report.

Conformance is checked HERE, at emit time, against the shipped header row
(``Template.headers``), in two tiers — because the strict reading was
tested against the operator's real sheets on 2026-09-11 and would have
refused most of them:

* **Required**: the scalar structure columns and each family's group-1
  PRIMARY (``Alternate Title 1``, ``Alt ID 1``, ``Associated Org 1``, ...).
  Missing one of these is a ``TemplateMismatch`` and the emit is refused,
  leaving no output file behind.
* **Optional**: anything that qualifies another column (``Alt Title Class
  1``, ``Domain 1``, ``Associated Org Role 1``, ``Relation N``, ``Title
  Class``, ``IMDb Relation``), every group-2+ member, and the ``IMDb`` /
  ``ISAN`` identifier pair older template revisions lacked. The survey of
  every workbook under ``D:\\BMR`` (294 Template-22 data sheets): 190 carry
  every shipped column; 104 omit something, and what they omit is
  companions (``Alt Title Class`` on 84, ``Relation 2/3`` on 54), whole
  groups the member never used (a second Alternate Title on 24, a third
  Associated Org on 20), a single group-1 qualifier on four sheets, and
  the ``IMDb`` / ``ISAN`` pair on three. The BMR tool took every one of
  them and BMR-Review assessed many. A missing optional column is REPORTED
  (``SubsetReport.missing_optional``), never refused: the subsetter copies
  what the member supplied, and a column the member never had is not a
  defect in the copy. Under the two tiers the survey refuses exactly one
  sheet, which has no Template-22 header row at all.

Extra columns and expanded families conform. "Is my input conforming
enough" is therefore answered per sheet, every time, rather than assumed
once — and answered against what the BMR tool actually accepts rather than
against the template's fullest form.

The copy is POSITIONAL and values-only: header rows 1..``DATA_START``-1 and
every kept row are written cell-for-cell into the same columns, in source
row order, onto a copy of the SOURCE workbook (so its other sheets,
validations and macros come along via the same transplant the writers
use). Nothing is renamed, reordered or re-mapped.
"""
from __future__ import annotations

import contextlib
import logging
import os
import re
import shutil
import tempfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from eidr_core.bmr_io import DATA_START, fix_shared_strings, read_headers, transplant
from eidr_core.bmr_io.writer import SHEET_TO_TEMPLATE, TEMPLATES

log = logging.getLogger(__name__)

__all__ = ["TemplateMismatch", "SubsetReport", "subset_rows", "required_headers"]

# Singleton columns that QUALIFY another column (a class, a language, a
# relation) or that older template revisions did not carry (the IMDb / ISAN
# identifier pair). A sheet without them is still a BMR sheet.
_OPTIONAL_SINGLE = frozenset({
    "Title Class", "Description Language",
    "IMDb", "IMDb Relation", "ISAN", "ISAN Relation", "V-ISAN", "V-ISAN Relation",
})
_NUMBERED = re.compile(r"^(.*?) (\d+)$")


def _optional(header: str, template: str) -> bool:
    """A shipped column a real sheet may lack and still be a BMR sheet.

    Optional: any family member from group 2 up (a member who never used a
    second Alternate Title has no columns for it); any family member that
    is not the family's PRIMARY (``Associated Org Role 1``, ``Domain 1``,
    ``Alt Title Class 1`` qualify ``Associated Org 1`` / ``Alt ID 1`` /
    ``Alternate Title 1``); and the singleton qualifiers above. Required is
    what is left: the scalar structure (``Unique Row ID``, ``Title``,
    ``Referent Type``, ``Publication Status``, ``Assigned EIDR ID``, ...)
    and each family's group-1 primary — the columns whose absence means
    this is not that template's data sheet.
    """
    if header in _OPTIONAL_SINGLE:
        return True
    m = _NUMBERED.match(header)
    if not m:
        return False
    base, n = m.group(1), int(m.group(2))
    if n >= 2:
        return True
    for fam in TEMPLATES[template].families:
        if base in fam.anchor_members and base != fam.primary:
            return True
    return False


def required_headers(template: str) -> tuple[str, ...]:
    """The shipped headers of ``template`` (a ``TEMPLATES`` key) whose
    absence makes a sheet NOT that template's data sheet (see module
    docstring)."""
    return tuple(h for h in TEMPLATES[template].headers if not _optional(h, template))


class TemplateMismatch(ValueError):
    """The sheet is not (or is no longer) a conforming Template-22 data sheet."""


@dataclass
class SubsetReport:
    path: str
    template: str                 # TEMPLATES key resolved from the sheet name
    sheet: str
    rows_kept: int
    # Requested row numbers that do not exist on the source sheet. Not an
    # error: a caller subsetting from a stale finding list should see the
    # gap, not crash after writing nothing.
    rows_missing: list[int] = field(default_factory=list)
    # {column: non-empty values blanked} for each name in blank_columns.
    blanked: dict[str, int] = field(default_factory=dict)
    # Source headers that are not on the shipped template — preserved
    # verbatim (that is the point), listed so the caller knows they exist.
    extra_columns: list[str] = field(default_factory=list)
    # Shipped OPTIONAL columns the source lacks (companions, group 2+).
    # Reported, not refused — see the module docstring for the evidence.
    missing_optional: list[str] = field(default_factory=list)


def subset_rows(src_xlsx: str, dst_xlsx: str, sheet_name: str,
                keep_rows: Iterable[int], *,
                blank_columns: Sequence[str] = ()) -> SubsetReport:
    """Copy header rows and the ``keep_rows`` of ``sheet_name`` from
    ``src_xlsx`` into ``dst_xlsx``.

    ``keep_rows`` are ABSOLUTE sheet row numbers — what ``open_sheet`` /
    ``read_sheet`` emit and what a consumer's findings already carry. Rows
    below ``DATA_START`` are refused: the header rows are always kept and
    are not the caller's to choose.
    """
    import openpyxl  # the `bmr` extra

    key = SHEET_TO_TEMPLATE.get(sheet_name)
    if key is None:
        raise TemplateMismatch(
            f"{sheet_name!r} is not a Template-22 data sheet; one of "
            f"{sorted(SHEET_TO_TEMPLATE)}")
    keep = sorted({int(r) for r in keep_rows})
    low = [r for r in keep if r < DATA_START]
    if low:
        raise ValueError(f"keep_rows must be data rows (>= {DATA_START}); header "
                         f"rows are always kept. Got {low}")
    if not os.path.exists(src_xlsx):
        raise FileNotFoundError(f"BMR sheet not found: {src_xlsx}")

    shutil.copyfile(src_xlsx, dst_xlsx)
    try:
        wb = openpyxl.load_workbook(dst_xlsx, data_only=False)
        if sheet_name not in wb.sheetnames:
            raise TemplateMismatch(f"{src_xlsx} has no sheet {sheet_name!r} "
                                   f"(sheets: {wb.sheetnames})")
        ws = wb[sheet_name]
        headers = read_headers(ws)
        present = set(headers.values())
        shipped = TEMPLATES[key].headers
        missing = [h for h in required_headers(key) if h not in present]
        if missing:
            raise TemplateMismatch(
                f"sheet {sheet_name!r} of {src_xlsx} is missing "
                f"{len(missing)} required Template-22 column(s): {missing}")
        missing_optional = [h for h in shipped if h not in present and _optional(h, key)]
        name_to_col = {h: c for c, h in headers.items()}
        unknown = [b for b in blank_columns if b not in name_to_col]
        if unknown:
            raise ValueError(f"blank_columns not on sheet {sheet_name!r}: {unknown}")
        blank_cols = [name_to_col[b] for b in blank_columns]

        report = SubsetReport(
            path=dst_xlsx, template=key, sheet=sheet_name, rows_kept=0,
            blanked=dict.fromkeys(blank_columns, 0),
            extra_columns=[h for c, h in sorted(headers.items()) if h not in shipped],
            missing_optional=missing_optional)

        max_row, max_col = ws.max_row, ws.max_column
        kept: list[list[object]] = []
        for r in keep:
            if r > max_row:
                report.rows_missing.append(r)
                continue
            values = [ws.cell(r, c).value for c in range(1, max_col + 1)]
            for name, c in zip(blank_columns, blank_cols, strict=True):
                v = values[c - 1]
                if v is not None and v != "":
                    report.blanked[name] += 1
                    values[c - 1] = None
            kept.append(values)

        # Clear the data area, then lay the kept rows down contiguously
        # from DATA_START in source order — positional, values only.
        if max_row >= DATA_START:
            for r in range(DATA_START, max_row + 1):
                for c in range(1, max_col + 1):
                    ws.cell(r, c).value = None
        for i, values in enumerate(kept, DATA_START):
            for c, v in enumerate(values, 1):
                if v is not None:
                    ws.cell(i, c).value = v
        report.rows_kept = len(kept)

        out_dir = os.path.dirname(os.path.abspath(dst_xlsx)) or "."
        fd, tmp = tempfile.mkstemp(suffix=".xlsx", dir=out_dir)
        os.close(fd)
        try:
            wb.save(tmp)
            transplant(template_xlsx=dst_xlsx, edited_xlsx=tmp)
            fix_shared_strings(dst_xlsx)
        finally:
            with contextlib.suppress(OSError):
                if os.path.exists(tmp):
                    os.remove(tmp)
    except BaseException:
        # A refused or failed emit leaves no half-written sheet for a
        # downstream tool to pick up as if it were complete.
        with contextlib.suppress(OSError):
            os.remove(dst_xlsx)
        raise

    log.info("subset_rows: %d of %d requested row(s) -> %s [%s]%s",
             report.rows_kept, len(keep), dst_xlsx, sheet_name,
             f" blanked={report.blanked}" if any(report.blanked.values()) else "")
    return report
