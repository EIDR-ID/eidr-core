"""Tests for the shared BMR writer composition — the silences it refuses.

Why these exist (2026-09-11, extraction of eidr-wikidata ``bmr/writer.py``)
--------------------------------------------------------------------------
Two consumers are being asked to delete a working writer each and depend on
this one. Their own suites (358 BMR tests in eidr-wikidata alone) will prove
equivalence on THEIR sheets when they adopt; what is pinned here is the part
neither of them tested because neither of them had it:

* the anchor/insert split as a PARAMETER (group 1 keeps its Class column
  next to it whether or not new groups get one);
* the two-tier cap (a consumer ceiling is honoured, a ceiling above the
  registry's is refused);
* the extra-column convention (one blank separator, then adjacent);
* and the report — a value with no column is counted, never lost silently.

Every wrong answer this module can give is a plausible-looking workbook, so
each test reads the workbook back rather than trusting the return value.
"""
from __future__ import annotations

import pytest

from eidr_core.bmr_io import (
    DATA_START,
    HEADER_ROW,
    SCHEMA_MAX,
    SHEET_TO_TEMPLATE,
    TEMPLATES,
    families_for,
    max_counts,
    template_for_creation_type,
    write_sheet,
)

openpyxl = pytest.importorskip("openpyxl")

SHEET = "Stand-Alone Works"

# A faithful subset of the real Stand-Alone Works header row (2026-09-11):
# two Alternate Title groups WITH a Class column each, three Alt ID groups
# with Relation, fixed Director 1-2 / Actor 1-4, and the three trailing
# columns every template ends with.
HEADERS = [
    "Unique Row ID", "Mode", "Structural Type", "Referent Type", "Title",
    "Title Language", "Title Class",
    "Original Language 1", "Language Mode 1",
    "Alternate Title 1", "Alt Title Language 1", "Alt Title Class 1",
    "Alternate Title 2", "Alt Title Language 2", "Alt Title Class 2",
    "Country of Origin 1",
    "Associated Org 1", "Associated Org Role 1", "Associated Org Party ID 1",
    "Release Date", "Publication Status", "Approx Length",
    "Director 1", "Director 2", "Actor 1", "Actor 2", "Actor 3", "Actor 4",
    "Alt ID 1", "Domain 1", "Relation 1",
    "Alt ID 2", "Domain 2", "Relation 2",
    "Alt ID 3", "Domain 3", "Relation 3",
    "Operator's Notes", "Assigned EIDR ID", "Registration Errors & Notes",
]


@pytest.fixture
def template(tmp_path):
    """A Template-22-shaped workbook: banner rows, headers on row 3, a
    second sheet that must survive the round trip, and one STALE data row
    that must not."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = SHEET
    ws.cell(1, 1).value = "EIDR Bulk Metadata Registration"
    ws.cell(2, 1).value = "banner"
    for c, h in enumerate(HEADERS, 1):
        ws.cell(HEADER_ROW, c).value = h
    ws.cell(DATA_START, 1).value = "STALE-ROW"
    ws.cell(DATA_START, 5).value = "left in the template by mistake"
    other = wb.create_sheet("Instructions")
    other.cell(1, 1).value = "keep me"
    path = tmp_path / "EIDR_Non-Episodic_Template-22.xlsx"
    wb.save(path)
    return str(path)


def _headers(path, sheet=SHEET) -> dict[int, str]:
    ws = openpyxl.load_workbook(path)[sheet]
    return {c: ws.cell(HEADER_ROW, c).value for c in range(1, ws.max_column + 1)
            if ws.cell(HEADER_ROW, c).value}


def _cell(path, row, header, sheet=SHEET):
    ws = openpyxl.load_workbook(path)[sheet]
    col = next(c for c, h in _headers(path, sheet).items() if h == header)
    return ws.cell(row, col).value


def _row(title="X", **cols):
    return {"Unique Row ID": "R1", "Title": title, "Title Language": "en", **cols}


# ── families and the anchor/insert split ─────────────────────────────────

def test_default_families_come_from_the_sheet_name(template, tmp_path):
    out = str(tmp_path / "out.xlsx")
    rows = [_row(**{f"Alternate Title {i}": f"t{i}" for i in range(1, 6)})]
    rep = write_sheet(template, SHEET, rows, out)
    hdr = _headers(out)
    assert "Alternate Title 5" in hdr.values()
    assert rep.expanded == {"Alternate Title": 5}
    # Default insert = anchor: a new group has the SAME columns as group 1,
    # which is what the template's own second group shows.
    assert "Alt Title Class 5" in hdr.values()


def test_group_one_keeps_its_class_column_whether_or_not_new_groups_get_one(
        template, tmp_path):
    """The 2026-05-09 defect: with Class excluded from insert but not from
    anchor, ``Alt Title Class 1`` must stay glued to its group. Pre-split it
    ended up between the last new group and Country of Origin."""
    out = str(tmp_path / "out.xlsx")
    rows = [_row(**{f"Alternate Title {i}": f"t{i}" for i in range(1, 6)})]
    fams = families_for("non_episodic", insert_members={
        "Alternate Title": ["Alternate Title", "Alt Title Language"]})
    write_sheet(template, SHEET, rows, out, families=fams)
    hdr = _headers(out)
    inv = {h: c for c, h in hdr.items()}
    assert "Alt Title Class 3" not in inv, "insert override ignored"
    assert inv["Alt Title Class 1"] == inv["Alt Title Language 1"] + 1
    assert inv["Alt Title Class 2"] == inv["Alt Title Language 2"] + 1
    # New groups land AFTER the rightmost anchor column (Class 2).
    assert inv["Alternate Title 3"] > inv["Alt Title Class 2"]
    assert inv["Alternate Title 5"] < inv["Country of Origin 1"]


def test_insert_override_is_checked_against_the_family():
    with pytest.raises(ValueError, match="outside the family"):
        families_for("non_episodic",
                     insert_members={"Alternate Title": ["Alternate Title", "Domain"]})
    with pytest.raises(ValueError, match="must include the primary"):
        families_for("non_episodic",
                     insert_members={"Alternate Title": ["Alt Title Language"]})
    with pytest.raises(ValueError, match="not on template"):
        families_for("clip", insert_members={"Alternate Title": ["Alternate Title"]})
    with pytest.raises(KeyError, match="unknown Template-22 key"):
        families_for("video_service")


def test_every_family_has_a_schema_ceiling_and_every_sheet_is_unique():
    for t in TEMPLATES.values():
        for fam in t.families:
            assert fam.primary in SCHEMA_MAX, (t.key, fam.primary)
            assert fam.primary in fam.anchor_members
            assert set(fam.insert_members) <= set(fam.anchor_members)
    assert len(SHEET_TO_TEMPLATE) == len(TEMPLATES)
    # Alt ID is the one deliberately unbounded content family.
    assert SCHEMA_MAX["Alt ID"] is None


# ── caps: consumer ceiling honoured, registry ceiling enforced ───────────

def test_consumer_cap_trims_and_says_so(template, tmp_path):
    out = str(tmp_path / "out.xlsx")
    rows = [_row(**{f"Alternate Title {i}": f"t{i}" for i in range(1, 6)})]
    rep = write_sheet(template, SHEET, rows, out, caps={"Alternate Title": 3})
    hdr = set(_headers(out).values())
    assert "Alternate Title 3" in hdr and "Alternate Title 4" not in hdr
    assert rep.capped == {"Alternate Title": 5}
    # The trimmed values are not lost silently: they are in the report.
    assert rep.dropped == {"Alternate Title 4": 1, "Alternate Title 5": 1}


def test_cap_above_the_registry_maximum_is_refused(template, tmp_path):
    out = str(tmp_path / "out.xlsx")
    with pytest.raises(ValueError, match="exceeds the registry maximum"):
        write_sheet(template, SHEET, [_row()], out, caps={"Associated Org": 17})
    with pytest.raises(ValueError, match="cannot be unbounded"):
        write_sheet(template, SHEET, [_row()], out, caps={"Original Language": None})
    with pytest.raises(ValueError, match="unknown family"):
        write_sheet(template, SHEET, [_row()], out, caps={"Alt Title": 3})


def test_registry_maximum_is_the_default_cap(template, tmp_path):
    """eidr-wikidata capped Country of Origin at 8 believing that was the
    registry's limit; the schema says 32. With no consumer cap the writer
    honours the schema, so a second consumer does not inherit a choice."""
    out = str(tmp_path / "out.xlsx")
    rows = [_row(**{f"Country of Origin {i}": "US" for i in range(1, 13)})]
    rep = write_sheet(template, SHEET, rows, out)
    assert "Country of Origin 12" in _headers(out).values()
    assert rep.capped == {} and rep.dropped == {}


# ── extra columns ────────────────────────────────────────────────────────

def test_extra_columns_land_after_one_blank_separator(template, tmp_path):
    out = str(tmp_path / "out.xlsx")
    rows = [_row(**{"Wikidata's EIDR ID": "10.5240/AAAA", "EIDR's Creation Type": "Episode"})]
    write_sheet(template, SHEET, rows, out,
                extra_columns=["Wikidata's EIDR ID", "EIDR's Creation Type"])
    ws = openpyxl.load_workbook(out)[SHEET]
    last_template_col = len(HEADERS)
    assert ws.cell(HEADER_ROW, last_template_col).value == "Registration Errors & Notes"
    assert ws.cell(HEADER_ROW, last_template_col + 1).value is None, "separator"
    assert ws.cell(HEADER_ROW, last_template_col + 2).value == "Wikidata's EIDR ID"
    assert ws.cell(HEADER_ROW, last_template_col + 3).value == "EIDR's Creation Type"
    assert ws.cell(DATA_START, last_template_col + 2).value == "10.5240/AAAA"
    assert ws.cell(DATA_START, last_template_col + 3).value == "Episode"


def test_extra_column_that_already_exists_is_refused(template, tmp_path):
    with pytest.raises(ValueError, match="already exists"):
        write_sheet(template, SHEET, [_row()], str(tmp_path / "o.xlsx"),
                    extra_columns=["Assigned EIDR ID"])


# ── the report: nothing is dropped silently ──────────────────────────────

def test_values_with_no_column_are_counted_not_lost(template, tmp_path):
    out = str(tmp_path / "out.xlsx")
    rows = [_row(**{"Season Class 1": "Regular", "Director 3": "third"}),
            _row(**{"Season Class 1": "Regular"})]
    rep = write_sheet(template, SHEET, rows, out)
    assert rep.dropped == {"Season Class 1": 2, "Director 3": 1}
    assert rep.rows == 2
    with pytest.raises(ValueError, match="no home on sheet"):
        write_sheet(template, SHEET, rows, out, strict=True)


def test_empty_values_neither_expand_nor_count(template, tmp_path):
    out = str(tmp_path / "out.xlsx")
    rows = [_row(**{"Alternate Title 4": "", "Alternate Title 5": None,
                    "Season Class 1": ""})]
    rep = write_sheet(template, SHEET, rows, out)
    assert "Alternate Title 3" not in _headers(out).values()
    assert rep.expanded == {} and rep.dropped == {}


def test_max_counts_counts_any_member_and_only_real_values():
    fams = families_for("non_episodic")
    rows = [{"Domain 4": "IMDB", "Alt ID 2": "x", "Alternate Title 7": None,
             "Unrelated 9": "y"}]
    assert max_counts(rows, fams) == {"Alt ID": 4}


# ── the sheet itself ─────────────────────────────────────────────────────

def test_stale_template_rows_are_cleared_and_data_starts_at_row_four(template, tmp_path):
    out = str(tmp_path / "out.xlsx")
    write_sheet(template, SHEET, [_row("First"), _row("Second")], out)
    assert _cell(out, DATA_START, "Unique Row ID") == "R1"
    assert _cell(out, DATA_START, "Title") == "First"
    assert _cell(out, DATA_START + 1, "Title") == "Second"
    ws = openpyxl.load_workbook(out)[SHEET]
    assert "STALE-ROW" not in {c.value for r in ws.iter_rows() for c in r}


def test_other_sheets_and_banner_survive_the_transplant(template, tmp_path):
    out = str(tmp_path / "out.xlsx")
    write_sheet(template, SHEET, [_row()], out)
    wb = openpyxl.load_workbook(out)
    assert wb["Instructions"].cell(1, 1).value == "keep me"
    assert wb[SHEET].cell(1, 1).value == "EIDR Bulk Metadata Registration"


def test_wrong_sheet_and_missing_template_fail_loudly(template, tmp_path):
    out = str(tmp_path / "out.xlsx")
    with pytest.raises(ValueError, match="has no sheet"):
        write_sheet(template, "Episodics", [_row()], out)
    with pytest.raises(ValueError, match="not a Template-22 data sheet"):
        write_sheet(template, "Instructions", [_row()], out)
    with pytest.raises(FileNotFoundError):
        write_sheet(str(tmp_path / "nope.xlsx"), SHEET, [_row()], out)


# ── routing (python-tools P3) ────────────────────────────────────────────

@pytest.mark.parametrize("ct,key", [
    ("Basic", "non_episodic"), ("Series", "episodic"), ("Season", "episodic"),
    ("Episode", "episodic"), ("Edit", "edit"), ("Clip", "clip"),
    ("Manifestation", "manifestation"),
    ("Compilation", "compilation"),      # operator ruling 2026-09-10
    ("Interactive", None), ("Composite", None),   # real types, no sheet
    ("CreateEpisode", "episodic"),       # the schema's own spelling
    (" Edit ", "edit"),
])
def test_routing_table(ct, key):
    assert template_for_creation_type(ct) == key


def test_routing_refuses_what_is_not_a_creation_type():
    """A referent type is not a creation type. Returning None here would
    put every 'Movie' row in the no-template bucket without a word."""
    for bad in ("Movie", "TV", "", "Alias", "movie"):
        with pytest.raises(ValueError, match="not an EIDR creation type"):
            template_for_creation_type(bad)
