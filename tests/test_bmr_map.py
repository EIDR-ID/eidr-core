"""eidr_core.bmr_map: the record <-> Template-22 row mapping (B5, 2026-10-13).

Mirrors the cases XML_to_JSON classified as mapper- or inverse-facing
(its tests/test_sheet_out_type.py and tests/test_administrators_roundtrip.py,
2026-09-23 and 2026-10-03), plus what only the shared module can be held to:
the produced-header declaration against the code and the stock templates,
and the two directions against each other. A wrong mapping here is silent
(a plausible row with a value in the wrong column, or a field gone), which
is why this module is tested locally rather than left to consumers.
"""
from __future__ import annotations

import copy

import pytest

from eidr_core import bmr_map as M
from eidr_core.bmr_io import TEMPLATES

SELF_ONLY_TITLE = "Sheet Supplied Title"
PID, PID2, REG = "10.5237/AAAA-BBBB", "10.5237/CCCC-DDDD", "10.5237/REG-0001"


# ── block selection (XML_to_JSON test_sheet_out_type.py, mirrored) ──────────

def _episode_record() -> dict:
    self_base = {"ID": "10.5240/AAAA-0000-0000-0000-0000-A", "StructuralType": "Abstraction",
                 "ResourceName": [{"Title": SELF_ONLY_TITLE, "TitleClass": "release",
                                   "SystemGenerated": "false"}]}
    extra = {"EpisodeInfo": {"Parent": "10.5240/BBBB-0000-0000-0000-0000-B", "SequenceNumber": "3"}}
    full_base = dict(self_base, Mode="AudioVisual", ReferentType="TV", CountryOfOrigin=["US"])
    return {"CreationType": "Episode",
            "SelfDefinedMetadata": {"BaseObjectData": self_base, "ExtraObjectMetadata": extra},
            "FullMetadata": {"BaseObjectData": full_base, "ExtraObjectMetadata": extra}}


def test_self_leaves_mirror_filled_gaps_empty():
    row = M.row_from_record(_episode_record(), "episodic", source="self")
    assert row.get("Title") == SELF_ONLY_TITLE
    assert row.get("Mode") is None and row.get("Referent Type") is None


def test_full_fills_gaps_from_the_full_block():
    row = M.row_from_record(_episode_record(), "episodic", source="full")
    assert row.get("Mode") == "AudioVisual" and row.get("Referent Type") == "TV"


def test_full_does_not_override_self_defined_values():
    rec = _episode_record()
    assert M.row_from_record(rec, "episodic", source="self")["Title"] == SELF_ONLY_TITLE
    assert M.row_from_record(rec, "episodic", source="full")["Title"] == SELF_ONLY_TITLE


def test_default_source_is_self():
    rec = _episode_record()
    assert M.row_from_record(rec, "episodic") == M.row_from_record(rec, "episodic", source="self")


def test_full_falls_back_to_self_when_full_absent():
    rec = _episode_record()
    del rec["FullMetadata"]
    assert M.row_from_record(rec, "episodic", source="full")["Title"] == SELF_ONLY_TITLE


def test_an_unknown_source_is_refused():
    with pytest.raises(ValueError):
        M.select_blocks(_episode_record(), "mirror")


# ── Administrators, both directions (test_administrators_roundtrip.py) ──────

def _row(**cells):
    row = {"Structural Type": "Abstraction", "Referent Type": "Movie", "Mode": "AudioVisual",
           "Title": "Test Film", "Title Language": "en", "Title Class": "release"}
    row.update(cells)
    return row


def _admins(row, template="non_episodic"):
    rec = M.record_from_row(row, template)
    return rec["SelfDefinedMetadata"]["BaseObjectData"].get("Administrators") or {}


def test_the_party_id_column_becomes_metadata_authority():
    assert _admins(_row(**{"Metadata Authority Party ID 1": PID}))["MetadataAuthority"] == [PID]


def test_the_name_column_never_becomes_an_id():
    assert "MetadataAuthority" not in _admins(_row(**{"Metadata Authority 1": "Acme Studios"}))


def test_with_both_columns_filled_the_party_id_wins():
    admins = _admins(_row(**{"Metadata Authority 1": "Acme Studios",
                              "Metadata Authority Party ID 1": PID}))
    assert admins["MetadataAuthority"] == [PID]


def test_groups_come_back_in_group_order_and_blanks_are_skipped():
    admins = _admins(_row(**{"Metadata Authority Party ID 1": None,
                              "Metadata Authority Party ID 3": PID2,
                              "Metadata Authority Party ID 2": PID}))
    assert admins["MetadataAuthority"] == [PID, PID2]


def test_the_compilation_templates_bare_header_is_group_1():
    admins = _admins(_row(**{"Metadata Authority Party ID": PID}), "compilation")
    assert admins["MetadataAuthority"] == [PID]


def test_a_numbered_header_wins_over_a_bare_one_for_group_1():
    row = _row(**{"Referent Type": "Season", "Season Class": "bare",
                  "Season Class 1": "numbered", "Season Class 2": "two"})
    rec = M.record_from_row(row, "episodic")
    season = rec["SelfDefinedMetadata"]["ExtraObjectMetadata"]["SeasonInfo"]
    assert season["SeasonClass"] == ["numbered", "two"]


@pytest.mark.parametrize("source", ["self", "full"])
def test_a_sheet_records_registrant_and_ma_reach_the_output_row(source):
    row = _row(**{"Registrant": REG, "Metadata Authority Party ID 1": PID})
    rec = M.record_from_row(row, "non_episodic")
    assert "ProvenanceMetadata" not in rec  # the shape that exposed the 2026-10-02 defect
    row = M.row_from_record(rec, "non_episodic", source=source)
    assert row["Registrant"] == REG and row["Metadata Authority Party ID 1"] == PID


def test_a_mirror_record_still_takes_provenance_administrators():
    rec = M.record_from_row(_row(**{"Registrant": "10.5237/BLOCK",
                                    "Metadata Authority Party ID 1": PID2}), "non_episodic")
    rec["ProvenanceMetadata"] = {"Administrators": {"Registrant": REG, "MetadataAuthority": [PID]}}
    row = M.row_from_record(rec, "non_episodic")
    assert row["Registrant"] == REG and row["Metadata Authority Party ID 1"] == PID


def test_row_from_blocks_reads_the_blocks_administrators_unless_told_otherwise():
    base = {"Administrators": {"Registrant": REG}}
    assert M.row_from_blocks(base, {}, "non_episodic")["Registrant"] == REG
    assert M.row_from_blocks(base, {}, "non_episodic",
                             administrators={"Registrant": PID})["Registrant"] == PID


# ── documented defaults ─────────────────────────────────────────────────────

def test_alt_id_promotion_and_the_clip_v_isan_rule():
    base = {"AlternateID": [{"AltID": "tt1", "Type": "IMDB"},
                            {"AltID": "isan-1", "Type": "ISAN", "Relation": "IsPackagingOf"},
                            {"AltID": "x1", "Type": "Proprietary", "Domain": "example.org"}]}
    row = M.row_from_blocks(base, {}, "non_episodic")
    assert (row["IMDb"], row["ISAN"], row["ISAN Relation"]) == ("tt1", "isan-1", "IsPackagingOf")
    assert (row["Alt ID 1"], row["Domain 1"]) == ("x1", "example.org") and "Alt ID 2" not in row
    clip = M.row_from_blocks(base, {}, "clip")
    assert clip["V-ISAN"] == "isan-1" and "ISAN" not in clip


def test_metadata_authority_goes_to_the_party_id_column_only():
    row = M.row_from_blocks({}, {}, "edit", administrators={"MetadataAuthority": [PID, PID2]})
    assert row["Metadata Authority Party ID 2"] == PID2
    assert not any(k.startswith("Metadata Authority ") and "Party ID" not in k for k in row)


def test_manifestation_digital_xml_becomes_single_line_operators_notes():
    extra = {"ManifestationInfo": {"Digital": "<a>\n   <b> x </b>\n</a>"}}
    assert M.row_from_blocks({}, extra, "manifestation")["Operator's Notes"] == "<a><b> x </b></a>"
    assert "Operator's Notes" not in M.row_from_blocks({}, extra, "edit")


def test_unsupported_and_unknown_templates_are_refused():
    with pytest.raises(ValueError):
        M.row_from_blocks({}, {}, "compilation")
    with pytest.raises(ValueError):
        M.record_from_row({}, "Episodic")  # a group LABEL is not a template key


def test_inputs_are_not_mutated():
    rec = _episode_record()
    before = copy.deepcopy(rec)
    M.row_from_record(rec, "episodic", source="full")
    assert rec == before


# ── the produced-header declaration (condition 4) ───────────────────────────

def _maximal_blocks() -> tuple[dict, dict]:
    """A record that takes every branch of the mapper at least once."""
    two = ["a", "b"]
    base = {
        "StructuralType": "Abstraction", "Mode": "AudioVisual", "ReferentType": "Movie",
        "ResourceName": [{"Title": "T", "TitleClass": "release", "_lang": "en"},
                         {"Title": "A", "TitleClass": "alternative", "_lang": "fr"}],
        "OriginalLanguage": [{"Language": "en", "_mode": "Audio"}],
        "VersionLanguage": [{"Language": "fr", "_mode": "Visual"}],
        "AssociatedOrg": [{"_organizationID": PID, "_role": "producer", "DisplayName": "Org"}],
        "ReleaseDate": "1999", "CountryOfOrigin": ["US"], "Status": "valid",
        "ApproximateLength": "PT1H",
        "AlternateID": [{"AltID": "tt1", "Type": "IMDB", "Relation": "IsSameAs"},
                        {"AltID": "i1", "Type": "ISAN", "Relation": "IsSameAs"},
                        {"AltID": "p1", "Domain": "example.org", "Relation": "IsSameAs"}],
        "Administrators": {"Registrant": REG, "MetadataAuthority": [PID]},
        "Credits": {"Director": [{"DisplayName": "D"}], "Actor": [{"DisplayName": "A"}]},
        "RegistrantExtra": "x", "Description": {"Description": "d", "_lang": "en"},
    }
    info = {"Parent": "10.5240/P", "TimeSlot": "20:00", "EndDate": "2001", "SeriesClass": "c",
            "SeasonClass": two, "EpisodeClass": two, "NumberRequired": True, "DateRequired": True,
            "OriginalTitleRequired": True, "SequenceNumber": "1",
            "SequenceInfo": {"DistributionNumber": {"Number": "1", "Domain": "d"},
                             "HouseSequence": {"Number": "h", "Domain": "d"},
                             "AlternateNumber": [{"Number": "a", "Domain": "d"}]}}
    details = [{"Details": "dd", "Domain": "x"}]
    extra = {"SeriesInfo": info, "SeasonInfo": info, "EpisodeInfo": info,
             "EditInfo": {"Parent": "p", "EditUse": "u", "EditClass": two, "MadeForRegion": two,
                          "ColorType": "color", "ThreeD": "false", "Details": details},
             "ManifestationInfo": {"Parent": "p", "MadeForRegion": two, "ManifestationClass": two,
                                   "Digital": "<a/>", "Details": details},
             "ClipInfo": {"Parent": "p", "Start": "s", "Duration": "d", "ComponentsMode": "m"}}
    return base, extra


@pytest.mark.parametrize("template", M.SUPPORTED_TEMPLATES)
def test_the_declaration_is_exactly_what_the_code_writes(template):
    base, extra = _maximal_blocks()
    row = M.row_from_blocks(base, extra, template)
    produced = {M.header_base(h) for h, v in row.items() if v is not None}
    assert produced == M.PRODUCED_BASES[template]


@pytest.mark.parametrize("template", M.SUPPORTED_TEMPLATES)
def test_every_template_column_is_produced_or_deliberately_not(template):
    """The guardrail XML_to_JSON runs, pinned where the mapper lives."""
    columns = {M.header_base(h) for h in TEMPLATES[template].headers}
    assert columns - M.PRODUCED_BASES[template] - M.NEVER_PRODUCED == set()


# ── the two directions against each other ──────────────────────────────────

@pytest.mark.parametrize("template,referent", [
    ("non_episodic", "Movie"), ("episodic", "Series"), ("episodic", "Season"),
    ("episodic", "TV"), ("edit", "Movie"), ("manifestation", "Movie"), ("clip", "Movie")])
def test_a_sheet_row_survives_row_to_record_to_row(template, referent):
    """Every value a stock template carries comes back under the same header."""
    row = {"Referent Type": referent, "Structural Type": "Performance", "Mode": "AudioVisual",
           "Title": "T", "Title Class": "release", "Title Language": "en",
           "Release Date": "1999", "Publication Status": "valid", "Approx Length": "PT1H",
           "Registrant": REG, "Metadata Authority Party ID 1": PID,
           "Associated Org 1": "Org", "Associated Org Role 1": "producer",
           "Associated Org Party ID 1": PID2,
           "Alt ID 1": "p1", "Domain 1": "example.org", "Relation 1": "IsSameAs",
           "Director 1": "D", "Actor 1": "A", "Description": "d", "Description Language": "en",
           "Registrant Extra": "x", "Parent EIDR/Row ID": "10.5240/P"}
    columns = {M.header_base(h) for h in TEMPLATES[template].headers}
    row = {k: v for k, v in row.items() if M.header_base(k) in columns}
    rec = M.record_from_row(row, template)
    back = M.row_from_record(rec, template)
    if template == "episodic" and referent == "Series":
        row.pop("Parent EIDR/Row ID")  # a Series has no parent field
    assert {k: v for k, v in back.items() if v is not None} == row
