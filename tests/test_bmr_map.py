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
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import pytest

from eidr_core import bmr_map as M
from eidr_core.bmr_io import TEMPLATES
from eidr_core.mddf_json import SchemaSet, eidr_schema

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


def test_full_is_withdrawn_no_inherited_data_on_any_bmr_sheet():
    # Operator, 2026-11-12 and 2026-11-13: "No inherited data applies to all
    # BMR spreadsheet generation." source="full" wrote the Full block's
    # inherited values (Mode, Referent Type here) onto the sheet.
    with pytest.raises(ValueError, match="withdrawn"):
        M.row_from_record(_episode_record(), "episodic", source="full")
    with pytest.raises(ValueError, match="withdrawn"):
        M.select_blocks(_episode_record(), "full")


def test_default_source_is_self():
    rec = _episode_record()
    assert M.row_from_record(rec, "episodic") == M.row_from_record(rec, "episodic", source="self")


def test_a_full_only_record_with_no_parent_maps_its_full_block():
    # A type=Full resolve of a Basic: nothing to inherit, so Full == Self.
    base = {"ID": "10.5240/CCCC-0000-0000-0000-0000-C", "StructuralType": "Abstraction",
            "Mode": "AudioVisual", "ResourceName": [{"Title": "A Film"}]}
    rec = {"FullMetadata": {"BaseObjectData": base}}
    row = M.row_from_record(rec, "non_episodic")
    assert row["Title"] == "A Film" and row["Mode"] == "AudioVisual"


def test_a_full_only_record_with_a_parent_is_refused_not_guessed():
    # Without the Self block its inherited values cannot be told apart.
    rec = _episode_record()
    del rec["SelfDefinedMetadata"]
    with pytest.raises(ValueError, match="Parent"):
        M.row_from_record(rec, "episodic")


def test_a_self_block_is_used_even_when_full_has_more():
    rec = _episode_record()
    row = M.row_from_record(rec, "episodic")
    assert row["Title"] == SELF_ONLY_TITLE and row.get("Country of Origin 1") is None


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


def test_a_sheet_records_registrant_and_ma_reach_the_output_row():
    row = _row(**{"Registrant": REG, "Metadata Authority Party ID 1": PID})
    rec = M.record_from_row(row, "non_episodic")
    assert "ProvenanceMetadata" not in rec  # the shape that exposed the 2026-10-02 defect
    row = M.row_from_record(rec, "non_episodic")
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
    M.row_from_record(rec, "episodic")
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


# ── Language Mode belongs to the template's own language family (0.51.0) ────
# Every tab has ONE Language Mode family: Original Language's on the
# Abstraction templates, Version Language's on Edit and Manifestation.
# XML_to_JSON measured both directions wrong in the reference: 398 of 400
# Edit rows written from `full` carried the parent's inherited Original mode
# beside the Edit's Version Language, and the row -> record direction dropped
# the column on about 254,000 real rows.

def test_an_edits_inherited_original_mode_is_not_written_beside_its_version_language():
    base = {"OriginalLanguage": [{"value": "en", "_mode": "Audio"}], "VersionLanguage": ["fr"]}
    row = M.row_from_blocks(base, {}, "edit")
    assert row["Version Language 1"] == "fr" and "Language Mode 1" not in row


def test_the_templates_own_family_writes_its_mode():
    base = {"OriginalLanguage": [{"value": "en", "_mode": "Audio"}],
            "VersionLanguage": [{"value": "fr", "_mode": "Visual"}]}
    assert M.row_from_blocks(base, {}, "non_episodic")["Language Mode 1"] == "Audio"
    assert M.row_from_blocks(base, {}, "manifestation")["Language Mode 1"] == "Visual"
    assert "Language Mode 1" not in M.row_from_blocks(base, {}, "clip")


@pytest.mark.parametrize("template,family,key", [
    ("non_episodic", "Original Language", "OriginalLanguage"),
    ("episodic", "Original Language", "OriginalLanguage"),
    ("edit", "Version Language", "VersionLanguage"),
    ("manifestation", "Version Language", "VersionLanguage")])
def test_language_mode_is_read_back_into_its_family(template, family, key):
    row = {"Referent Type": "Movie", f"{family} 1": "fr", "Language Mode 1": "Visual",
           f"{family} 2": "en", "Language Mode 2": "Audio", f"{family} 3": "de"}
    langs = M.record_from_row(row, template)["SelfDefinedMetadata"]["BaseObjectData"][key]
    assert langs == ["de", {"value": "en", "_mode": "Audio"}, {"value": "fr", "_mode": "Visual"}]
    back = M.row_from_record(M.record_from_row(row, template), template)
    pairs = {(back[f"{family} {i}"], back.get(f"Language Mode {i}")) for i in (1, 2, 3)}
    assert pairs == {("de", None), ("en", "Audio"), ("fr", "Visual")}


# ── the languages follow the tab's family too (0.56.0; BMR-Review T20) ──────
# An Edit built from `full` inherits its parent's Original Language; the Edit
# tab has no such column, so writing it only made write_sheet drop and report
# it (272 values on BMR-Review's 271 audit Edit rows).

@pytest.mark.parametrize("template,kept,dropped", [
    ("non_episodic", "Original Language 1", "Version Language 1"),
    ("episodic", "Original Language 1", "Version Language 1"),
    ("edit", "Version Language 1", "Original Language 1"),
    ("manifestation", "Version Language 1", "Original Language 1")])
def test_only_the_tabs_own_language_family_is_written(template, kept, dropped):
    base = {"OriginalLanguage": ["en"], "VersionLanguage": ["fr"]}
    row = M.row_from_blocks(base, {}, template)
    assert kept in row and dropped not in row


def test_clip_writes_no_language():
    row = M.row_from_blocks({"OriginalLanguage": ["en"], "VersionLanguage": ["fr"]}, {}, "clip")
    assert not any("Language" in h and h != "Title Language" for h in row)


# ── a system-generated main title on a sheet that may be registered (0.56.0) ─
# A sheet cannot mark a title as system-generated, so registering one makes it
# user-supplied and stops regeneration (inheritance rule 2). "drop" withholds
# it AFTER the main title is chosen, so an alternate is never promoted.

def _titled():
    return {"ResourceName": [
        {"value": "Edit of X", "_titleClass": "release", "_lang": "en", "SystemGenerated": "true"},
        {"value": "FKA X", "_titleClass": "FKA", "_lang": "en", "SystemGenerated": "false"}]}


def test_system_titles_keep_is_the_default_and_writes_it():
    row = M.row_from_blocks(_titled(), {}, "edit")
    assert row["Title"] == "Edit of X" and row["Alternate Title 1"] == "FKA X"


def test_system_titles_drop_withholds_it_without_promoting_the_next():
    row = M.row_from_blocks(_titled(), {}, "edit", system_titles="drop")
    assert "Title" not in row and "Title Class" not in row and "Title Language" not in row
    assert row["Alternate Title 1"] == "FKA X"
    record = {"SelfDefinedMetadata": {"BaseObjectData": _titled()}}
    assert "Title" not in M.row_from_record(record, "edit", system_titles="drop")


def test_system_titles_drop_keeps_a_user_supplied_title():
    base = {"ResourceName": [{"value": "Real", "SystemGenerated": "false"}]}
    assert M.row_from_blocks(base, {}, "edit", system_titles="drop")["Title"] == "Real"
    with pytest.raises(ValueError):
        M.row_from_blocks(base, {}, "edit", system_titles="yes")


# ── registry XML -> standard record (0.52.0; BMR-Review T20) ────────────────
# Differentially checked before release: for 363 registry records (60 each of
# Basic, Series, Season, Episode, Edit, Manifestation, chosen for group 2+ of
# every family), row_from_record(record_from_xml(resolve XML)) equals
# row_from_record(XML_to_JSON's mirror export) on 722 of 722 rows (self and
# full), except where XML_to_JSON's rendering differs from the XML itself:
# duration normalisation (PT0H vs PT0S), ShortDOI (the export drops it) and a
# Self Status the SelfDefined XML does not state.

_MSG = """<Message xmlns="http://www.eidr.org/schema"
 xmlns:md="http://www.movielabs.com/schema/md/v2.8/md"
 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><Operation name="create">
<FullMetadata><BaseObjectData><ID>10.5240/AAAA-0000-0000-0000-0000-A</ID>
<StructuralType>Abstraction</StructuralType><Mode>AudioVisual</Mode>
<ReferentType>TV</ReferentType>
<ResourceName lang="en" titleClass="release">Pilot</ResourceName>
<AlternateResourceName lang="fr" titleClass="translated">Le Pilote</AlternateResourceName>
<OriginalLanguage mode="Audio">en</OriginalLanguage><OriginalLanguage>fr</OriginalLanguage>
<AssociatedOrg idType="EIDRPartyID" organizationID="10.5237/B03D-06E1" role="producer">
<md:DisplayName>Org One</md:DisplayName><md:AlternateName>Org 1</md:AlternateName>
</AssociatedOrg>
<AssociatedOrg role="broadcaster"><md:DisplayName>Org Two</md:DisplayName></AssociatedOrg>
<ReleaseDate>2017-02-01</ReleaseDate><CountryOfOrigin>US</CountryOfOrigin>
<CountryOfOrigin>FR</CountryOfOrigin>
<Status>valid</Status><ApproximateLength>PT1H0M</ApproximateLength>
<AlternateID xsi:type="IMDB">tt0000001</AlternateID>
<AlternateID domain="example.org" xsi:type="Proprietary" relation="IsSameAs">X1</AlternateID>
<AlternateID xsi:type="ShortDOI">10/abcd</AlternateID>
<Administrators><Registrant>10.5237/REG1</Registrant>
<MetadataAuthority>10.5237/MA1</MetadataAuthority></Administrators>
<Credits><Director><md:DisplayName>D One</md:DisplayName></Director>
<Actor><md:DisplayName>A One</md:DisplayName></Actor><Actor>
<md:DisplayName>A Two</md:DisplayName></Actor></Credits>
<Description lang="en">A test</Description></BaseObjectData>
<ExtraObjectMetadata><EpisodeInfo><Parent>10.5240/BBBB-0000-0000-0000-0000-B</Parent>
<SequenceInfo><md:DistributionNumber domain="rovicorp.com">1</md:DistributionNumber>
<md:HouseSequence domain="rovicorp.com">101</md:HouseSequence>
<md:AlternateNumber domain="x.com">7</md:AlternateNumber></SequenceInfo></EpisodeInfo>
</ExtraObjectMetadata>
</FullMetadata>
<SelfDefinedMetadata><BaseObjectData><ID>10.5240/AAAA-0000-0000-0000-0000-A</ID>
<StructuralType>Abstraction</StructuralType>
<ResourceName lang="en" titleClass="release">Pilot</ResourceName>
</BaseObjectData></SelfDefinedMetadata></Operation></Message>"""


def test_record_from_xml_builds_the_standard_shape():
    rec = M.record_from_xml(_MSG)
    base = rec["FullMetadata"]["BaseObjectData"]
    # Alternates under their own key, as in the XML (0.75.0).
    assert base["ResourceName"] == [
        {"Title": "Pilot", "TitleClass": "release", "_lang": "en"}]
    assert base["AlternateResourceName"] == [
        {"Title": "Le Pilote", "TitleClass": "translated", "_lang": "fr"}]
    assert base["OriginalLanguage"] == [{"value": "en", "_mode": "Audio"}, "fr"]
    assert base["AssociatedOrg"][0] == {
        "_idType": "EIDRPartyID", "_organizationID": "10.5237/B03D-06E1",
        "_role": "producer", "DisplayName": "Org One", "AlternateName": ["Org 1"]}
    assert base["AlternateID"][0] == {"AltID": "tt0000001", "Type": "IMDB"}
    # kept: whether a ShortDOI belongs in a registration is the caller's policy
    assert {"AltID": "10/abcd", "Type": "ShortDOI"} in base["AlternateID"]
    assert base["Administrators"] == {"Registrant": "10.5237/REG1",
                                      "MetadataAuthority": ["10.5237/MA1"]}
    seq = rec["FullMetadata"]["ExtraObjectMetadata"]["EpisodeInfo"]["SequenceInfo"]
    assert seq == {"DistributionNumber": {"Number": "1", "Domain": "rovicorp.com"},
                   "HouseSequence": {"Number": "101", "Domain": "rovicorp.com"},
                   "AlternateNumber": [{"Number": "7", "Domain": "x.com"}]}
    assert rec["SelfDefinedMetadata"]["BaseObjectData"]["ResourceName"] == [
        {"Title": "Pilot", "TitleClass": "release", "_lang": "en"}]


def test_record_from_xml_feeds_row_from_record():
    # Every column at once: the Full block's content presented as the record's
    # own (a sheet takes only self-defined values; _MSG's Self block is thin).
    rec = M.record_from_xml(_MSG)
    row = M.row_from_record({"SelfDefinedMetadata": rec["FullMetadata"]}, "episodic")
    assert row["IMDb"] == "tt0000001"
    assert (row["Alt ID 1"], row["Domain 1"]) == ("X1", "example.org")
    assert row["Parent EIDR/Row ID"] == "10.5240/BBBB-0000-0000-0000-0000-B"
    assert (row["Distribution No."], row["Alternate No. 1"]) == ("1", "7")
    assert row["Language Mode 1"] == "Audio" and row["Original Language 2"] == "fr"
    assert (row["Associated Org 2"], row["Actor 2"]) == ("Org Two", "A Two")
    assert row["Metadata Authority Party ID 1"] == "10.5237/MA1"


def test_record_from_xml_reads_one_block_and_edit_details():
    xml = ('<FullMetadata xmlns="http://www.eidr.org/schema">'
           '<BaseObjectData><ID>x</ID></BaseObjectData>'
           '<ExtraObjectMetadata><EditInfo><Parent>p</Parent><EditClass>a</EditClass>'
           '<EditDetails domain="d1">one</EditDetails><EditDetails domain="d2">two</EditDetails>'
           '</EditInfo></ExtraObjectMetadata></FullMetadata>')
    rec = M.record_from_xml(xml)
    assert set(rec) == {"FullMetadata"}
    ei = rec["FullMetadata"]["ExtraObjectMetadata"]["EditInfo"]
    assert ei == {"Parent": "p", "EditClass": ["a"],
                  "Details": [{"Details": "one", "Domain": "d1"},
                              {"Details": "two", "Domain": "d2"}]}


def test_record_from_xml_refuses_xml_without_a_block():
    with pytest.raises(ValueError):
        M.record_from_xml("<Message xmlns='http://www.eidr.org/schema'/>")


# ── a BMR row never carries a ShortDOI (0.58.0) ──────────────────────────────

def test_a_shortdoi_never_reaches_a_row():
    base = {"AlternateID": [{"AltID": "10/abcd", "Type": "ShortDOI", "Relation": "IsSameAs"},
                            {"AltID": "p1", "Domain": "example.org"},
                            {"AltID": "10/efgh", "Type": " shortdoi "}]}
    row = M.row_from_blocks(base, {}, "non_episodic")
    assert row["Alt ID 1"] == "p1" and "Alt ID 2" not in row
    assert "10/abcd" not in row.values()


# ── absent fields stay absent (operator, 2026-11-13) ─────────────────────────
# "Empty or removed fields should simply be gone from the output. They should
# not carry false or null or any other flag." A "false" SystemGenerated is
# still a valid-looking record, so only a test sees it come back.

def test_a_sheet_title_carries_no_system_generated_placeholder():
    rec = M.record_from_row(_row(**{"Alternate Title 1": "Other"}), "non_episodic")
    base = rec["SelfDefinedMetadata"]["BaseObjectData"]
    titles = base["ResourceName"] + base["AlternateResourceName"]
    assert [t["Title"] for t in titles] == ["Test Film", "Other"]
    assert all("SystemGenerated" not in t for t in titles)


@pytest.mark.parametrize("attr, want", [("", None), (' systemGenerated="false"', None),
                                        (' systemGenerated="true"', "true"),
                                        (' systemGenerated="1"', "true")])
def test_xml_system_generated_is_kept_only_when_true(attr, want):
    xml = _MSG.replace('<ResourceName lang="en" titleClass="release">',
                       f'<ResourceName lang="en" titleClass="release"{attr}>')
    main = M.record_from_xml(xml)["FullMetadata"]["BaseObjectData"]["ResourceName"][0]
    assert main.get("SystemGenerated") == want


# ── cell values (MDDF JSON step 3, 2026-11-13) ───────────────────────────────

def test_a_date_cell_is_an_xs_date_not_a_python_datetime_string():
    # openpyxl gives a date cell as a datetime; str() made "2020-01-01 00:00:00",
    # which is not an xs:date and reached generated titles as such.
    from datetime import date, datetime

    rec = M.record_from_row(_row(**{"Release Date": datetime(2020, 1, 1)}), "non_episodic")
    assert rec["SelfDefinedMetadata"]["BaseObjectData"]["ReleaseDate"] == "2020-01-01"
    assert M._text(datetime(2020, 1, 1, 21, 25)) == "2020-01-01T21:25:00"
    assert M._text(date(2020, 1, 1)) == "2020-01-01"


# ── titles: an alternate is never the main title (operator, 2026-11-15) ──────
# "For child records, you can have only an Alternate Title, which must remain
# an Alternate Title ... if the main title is missing, you do not promote the
# Alternate." Until 0.75.0 alternates shared the ResourceName list, where
# entry 0 is the main title, so a blank Title promoted the first alternate:
# a plausible record, wrong only in which title is which.

def test_a_row_with_only_an_alternate_title_keeps_it_an_alternate():
    row = _row(**{"Title": None, "Title Language": None, "Title Class": None,
                  "Referent Type": "TV", "Alternate Title 1": "Le Pilote",
                  "Alt Title Language 1": "fr", "Alt Title Class 1": "translated"})
    base = M.record_from_row(row, "episodic")["SelfDefinedMetadata"]["BaseObjectData"]
    assert "ResourceName" not in base
    assert base["AlternateResourceName"] == [
        {"Title": "Le Pilote", "TitleClass": "translated", "_lang": "fr"}]
    back = M.row_from_blocks(base, {}, "episodic")
    assert back.get("Title") is None
    assert back["Alternate Title 1"] == "Le Pilote"


def test_registry_xml_with_only_an_alternate_keeps_it_an_alternate():
    # The shape of 10.5240/4D28-...-H's SelfDefined (2,711 such in the mirror).
    xml = _MSG.replace(
        '<SelfDefinedMetadata><BaseObjectData><ID>10.5240/AAAA-0000-0000-0000-0000-A</ID>\n'
        '<StructuralType>Abstraction</StructuralType>\n'
        '<ResourceName lang="en" titleClass="release">Pilot</ResourceName>',
        '<SelfDefinedMetadata><BaseObjectData><ID>10.5240/AAAA-0000-0000-0000-0000-A</ID>\n'
        '<StructuralType>Abstraction</StructuralType>\n'
        '<AlternateResourceName lang="fr">Le Pilote</AlternateResourceName>')
    base = M.record_from_xml(xml)["SelfDefinedMetadata"]["BaseObjectData"]
    assert "ResourceName" not in base
    row = M.row_from_blocks(base, {}, "episodic")
    assert row.get("Title") is None and row["Alternate Title 1"] == "Le Pilote"


def test_an_empty_main_entry_does_not_promote_the_next_title():
    # The one-list shape some callers still build: entry 0 is the main title
    # even when it has no text; entries 1..n are alternates.
    base = {"ResourceName": [{"TitleClass": "release"}, {"Title": "Alt", "_lang": "en"}]}
    row = M.row_from_blocks(base, {}, "non_episodic")
    assert row.get("Title") is None and row["Alternate Title 1"] == "Alt"


# ── no empty elements, no duplicate values (operator, 2026-11-15) ────────────

def test_xml_empty_elements_and_repeated_values_are_not_read():
    xml = _MSG.replace('<Description lang="en">A test</Description>',
                       '<Description lang="en"></Description>'
                       '<VersionLanguage mode="Audio">en</VersionLanguage>'
                       '<VersionLanguage mode="Visual">en</VersionLanguage>'
                       '<VersionLanguage mode="Audio" type="primary">en</VersionLanguage>')
    xml = xml.replace('<SequenceInfo>', '<EpisodeClass>Segment</EpisodeClass>'
                      '<EpisodeClass>Segment</EpisodeClass><SequenceInfo>')
    full = M.record_from_xml(xml)["FullMetadata"]
    base = full["BaseObjectData"]
    assert "Description" not in base
    # Same code, two modes: two values. Same code and mode: one (type unread).
    assert base["VersionLanguage"] == [{"value": "en", "_mode": "Audio"},
                                       {"value": "en", "_mode": "Visual"}]
    assert full["ExtraObjectMetadata"]["EpisodeInfo"]["EpisodeClass"] == ["Segment"]


def test_sheet_empty_details_and_repeated_classes_are_not_read():
    row = _row(**{"Referent Type": "TV", "Edit Class 1": "Original", "Edit Class 2": "Original",
                  "Edit Details Domain 1": "x.org", "Description Language": "en"})
    rec = M.record_from_row(row, "edit")["SelfDefinedMetadata"]
    info = rec["ExtraObjectMetadata"]["EditInfo"]
    assert info["EditClass"] == ["Original"] and "Details" not in info
    assert "Description" not in rec["BaseObjectData"]


@pytest.mark.parametrize("template,column,where,key", [
    ("episodic", "Season Class", "SeasonInfo", "SeasonClass"),
    ("episodic", "Episode Class", "EpisodeInfo", "EpisodeClass"),
    ("manifestation", "Manif Class", "ManifestationInfo", "ManifestationClass"),
    ("manifestation", "Made for Region", "ManifestationInfo", "MadeForRegion"),
    ("edit", "Made for Region", "EditInfo", "MadeForRegion"),
])
def test_every_class_family_drops_a_repeated_value(template, column, where, key):
    rt = {"SeasonInfo": "Season"}.get(where, "TV")
    row = _row(**{"Referent Type": rt, f"{column} 1": "X", f"{column} 2": "X",
                  f"{column} 3": "Y"})
    extra = M.record_from_row(row, template)["SelfDefinedMetadata"]["ExtraObjectMetadata"]
    assert extra[where][key] == ["X", "Y"]


def test_xml_original_language_is_one_entry_per_code_and_mode():
    xml = _MSG.replace('<OriginalLanguage mode="Audio">en</OriginalLanguage>',
                       '<OriginalLanguage mode="Audio" type="primary">en</OriginalLanguage>'
                       '<OriginalLanguage mode="Audio">en</OriginalLanguage>')
    base = M.record_from_xml(xml)["FullMetadata"]["BaseObjectData"]
    assert base["OriginalLanguage"] == [{"value": "en", "_mode": "Audio"}, "fr"]


def test_xml_details_and_titles_without_text_are_not_read():
    xml = _MSG.replace('<SequenceInfo>', '<EditDetails domain="x.org"/>'
                       '<EditDetails domain="y.org">  </EditDetails>'
                       '<EditDetails domain="z.org">Kept</EditDetails><SequenceInfo>')
    xml = xml.replace('<Description lang="en">A test</Description>',
                      '<Description lang="en">   </Description>'
                      '<AlternateResourceName lang="de" titleClass="FKA"/>')
    full = M.record_from_xml(xml)["FullMetadata"]
    assert full["ExtraObjectMetadata"]["EpisodeInfo"]["Details"] == [
        {"Details": "Kept", "Domain": "z.org"}]
    base = full["BaseObjectData"]
    assert "Description" not in base
    assert all(t.get("Title") for t in base.get("AlternateResourceName", []))


def test_row_titles_take_entry_0_before_any_filtering_and_accept_one_alternate_dict():
    row = M.row_from_blocks({"ResourceName": ["M", {"Title": "A"}],
                             "AlternateResourceName": {"Title": "B", "_lang": "fr"}},
                            {}, "non_episodic")
    assert row["Title"] == "M"
    assert (row["Alternate Title 1"], row["Alternate Title 2"]) == ("A", "B")
    assert row["Alt Title Language 2"] == "fr"


def test_a_title_without_text_writes_no_class_or_language():
    row = M.row_from_blocks({"ResourceName": [{"TitleClass": "release", "_lang": "en"}],
                             "AlternateResourceName": [{"TitleClass": "FKA", "_lang": "fr"},
                                                       {"Title": "Alt"}]},
                            {}, "non_episodic")
    assert row.get("Title Class") is None and row.get("Title Language") is None
    assert row["Alternate Title 1"] == "Alt" and row.get("Alt Title Class 1") is None


def test_drop_withholds_only_a_generated_main_title():
    base = {"ResourceName": [{"Title": "Mine"}],
            "AlternateResourceName": [{"Title": "Alt", "SystemGenerated": "true"}]}
    row = M.row_from_blocks(base, {}, "non_episodic", system_titles="drop")
    assert row["Title"] == "Mine" and row["Alternate Title 1"] == "Alt"
    base = {"ResourceName": [{"Title": "Gen", "SystemGenerated": "true"}],
            "AlternateResourceName": [{"Title": "Alt"}]}
    row = M.row_from_blocks(base, {}, "non_episodic", system_titles="drop")
    assert row.get("Title") is None and row["Alternate Title 1"] == "Alt"


# ── standard record -> registry XML (record_to_xml; python-tools -bmrin) ────
# Acceptance from python-tools' handoff of 2026-11-25, section 3: (1) the
# round trip record_from_xml(record_to_xml(r)) == r for each creation type a
# Template-22 sheet produces; (2) element order is the creation schema's;
# (4) a field the writer cannot place raises, naming it. A wrong answer is
# silent (a registration missing a value, or an element the registry
# reorders or rejects), so it is pinned here. Measured before release on
# XML_to_JSON's golden registry corpus (36 Self/Full documents, a5b0949):
# every one round-trips, and the XML written equals the registry's own text
# except the deprecated language `type` attribute (record_from_xml does not
# read it) and one Digital block whose Container preceded its Track.

_E = "{http://www.eidr.org/schema}"
_SPECS = Path(M.__file__).resolve().parent.parent / "specs" / "mddf_json"

_ROW = {"Structural Type": "Performance", "Mode": "AudioVisual",
        "Title": "T", "Title Class": "release", "Title Language": "en",
        "Alternate Title 1": "A", "Alt Title Language 1": "fr",
        "Original Language 1": "en", "Language Mode 1": "Audio", "Version Language 1": "fr",
        "Country of Origin 1": "US", "Release Date": "1999", "Publication Status": "valid",
        "Approx Length": "PT1H", "Registrant": REG, "Metadata Authority Party ID 1": PID,
        "Associated Org 1": "Org", "Associated Org Role 1": "producer",
        "Associated Org Party ID 1": PID2,
        "Alt ID 1": "p1", "Domain 1": "example.org", "Relation 1": "IsSameAs",
        "IMDb": "tt1", "IMDb Relation": "IsSameAs", "ISAN": "0000-0001", "V-ISAN": "0000-0002",
        "Director 1": "D", "Actor 1": "A", "Description": "d", "Description Language": "en",
        "Registrant Extra": "x", "Parent EIDR/Row ID": "10.5240/P",
        "End Date": "2001", "Series Class": "c", "Season Class 1": "s1", "Episode Class 1": "e1",
        "Number Required": "true", "Season No.": "2", "Episode No.": "3",
        "Distribution No.": "7", "Dist. No. Domain": "d.org", "House No.": "h",
        "House No. Domain": "h.org", "Alternate No. 1": "a", "Alt. No. Domain 1": "a.org",
        "Time Slot": "20:00:00", "Edit Use": "u", "Edit Class 1": "c1",
        "Made for Region 1": "US", "Color Type": "color", "In 3D": "false",
        "Edit Details 1": "dd", "Edit Details Domain 1": "x.org", "Manif Class 1": "m1",
        "Manif Details 1": "md", "Manif Details Domain 1": "y.org",
        "Start Time": "PT0S", "Content Duration": "PT1M", "Component Mode": "AudioVisual"}

# Every creation type the Template-22 workbooks produce (Compilation is out of
# scope: the mapper has no Header/Entry shape for it).
_CREATION = [("non_episodic", "Movie", "Basic"), ("episodic", "Series", "Series"),
             ("episodic", "Season", "Season"), ("episodic", "TV", "Episode"),
             ("edit", "Movie", "Edit"), ("manifestation", "Movie", "Manifestation"),
             ("clip", "Movie", "Clip")]


def _sheet_record(template: str, referent: str) -> dict:
    columns = {M.header_base(h) for h in TEMPLATES[template].headers}
    row = {k: v for k, v in dict(_ROW, **{"Referent Type": referent}).items()
           if M.header_base(k) in columns}
    return M.record_from_row(row, template)


@pytest.mark.parametrize("template,referent,ctype", _CREATION)
def test_record_to_xml_round_trips_every_creation_type(template, referent, ctype):
    r = _sheet_record(template, referent)
    assert M.creation_type_from_row(template, {"Referent Type": referent}) == ctype
    # A record_from_row record is not in record_from_xml's normal form (its
    # Alt IDs carry the sheet's Domain and no Type), so it is compared at the
    # row level: the sheet gets back exactly what it gave.
    xml_r = M.record_from_xml(M.record_to_xml(r))
    assert M.row_from_record(xml_r, template) == M.row_from_record(r, template)
    # In the normal form the round trip is the identity, and the text is stable.
    x = M.record_to_xml(xml_r)
    assert M.record_from_xml(x) == xml_r
    assert M.record_to_xml(M.record_from_xml(x)) == x


@pytest.mark.parametrize("xml,view", [
    (_MSG, "FullMetadata"), (_MSG, "SelfDefinedMetadata"),
    ((_SPECS / "registry-edit-full.xml").read_text(encoding="utf-8"), "FullMetadata")])
def test_record_to_xml_inverts_record_from_xml_on_registry_xml(xml, view):
    r = M.record_from_xml(xml)
    assert M.record_from_xml(M.record_to_xml(r, view=view)) == {view: r[view]}


def test_registry_xml_comes_back_as_the_registry_wrote_it():
    # The resolve document itself, less the deprecated language `type`
    # attribute record_from_xml does not read (operator, 2026-11-15).
    src = (_SPECS / "registry-edit-full.xml").read_text(encoding="utf-8")
    out = M.record_to_xml(M.record_from_xml(src), view="FullMetadata")
    assert out == src.replace(' type="primary"', "")


def test_a_digital_block_in_schema_order_round_trips():
    digital = ('<Digital><Track><md:Video><md:Encoding><md:Codec>H.264</md:Codec>'
               '</md:Encoding></md:Video></Track><Container><md:Type>CFF</md:Type></Container>'
               '</Digital>')
    xml = ('<SelfDefinedMetadata xmlns="http://www.eidr.org/schema" '
           'xmlns:md="http://www.movielabs.com/schema/md/v2.8/md"><BaseObjectData>'
           '<StructuralType>Digital</StructuralType></BaseObjectData><ExtraObjectMetadata>'
           f'<ManifestationInfo><Parent>10.5240/P</Parent>{digital}</ManifestationInfo>'
           '</ExtraObjectMetadata></SelfDefinedMetadata>')
    r = M.record_from_xml(xml)
    out = M.record_to_xml(r)
    assert M.record_from_xml(out) == r
    assert digital in out


def _assert_schema_order(el: ET.Element, typ: Any, sch: SchemaSet) -> None:
    """Every element's children are in its type's content-model order."""
    model = sch.content(typ)
    last = -1
    for child in el:
        hit = model.children.get(child.tag)
        assert hit is not None, f"{child.tag} is not allowed in {el.tag}"
        assert hit.position >= last, f"{child.tag} is out of schema order in {el.tag}"
        last = hit.position
        _assert_schema_order(child, hit.type, sch)


@pytest.mark.parametrize("template,referent,ctype", _CREATION)
def test_record_to_xml_writes_the_creation_schemas_order(template, referent, ctype):
    sch = eidr_schema()
    out = ET.fromstring(M.record_to_xml(_sheet_record(template, referent)))
    _assert_schema_order(out, sch.element_type(f"{_E}SelfDefinedMetadata"), sch)
    # The view's root renamed to the creation type IS the creation element
    # (python-tools' plan): the same children validate against the
    # create<Type>DataType content model, in the same order.
    _assert_schema_order(out, f"{_E}create{ctype}DataType", sch)


@pytest.mark.parametrize("mutate,named", [
    (lambda b, e: b.update(Rating="PG"), "Rating"),
    (lambda b, e: b["AlternateID"].append({"AltID": "tt9", "Type": "IMDB",
                                           "Domain": "imdb.com"}), "imdb.com"),
    (lambda b, e: b["AlternateResourceName"][0].update(SystemGenerated="true"),
     "SystemGenerated"),
    (lambda b, e: b["Credits"]["Actor"].append({"SortName": "Doe, J"}), "SortName"),
    (lambda b, e: b["Description"].update(value="other"), "Description"),
    (lambda b, e: e["ManifestationInfo"].update(Film={"x": 1}), "Film"),
    (lambda b, e: e["ManifestationInfo"]["Details"][0].update(Domain="z.org"), "_domain"),
    (lambda b, e: b.update(Credits=["D"]), "Credits"),
])
def test_record_to_xml_refuses_what_it_cannot_place(mutate, named):
    r = _sheet_record("manifestation", "Movie")
    md = r["SelfDefinedMetadata"]
    mutate(md["BaseObjectData"], md["ExtraObjectMetadata"])
    with pytest.raises(M.RecordXmlError, match=named):
        M.record_to_xml(r)


def test_record_to_xml_refuses_a_missing_or_empty_view_and_an_unknown_one():
    with pytest.raises(M.RecordXmlError, match="no FullMetadata block"):
        M.record_to_xml(_sheet_record("edit", "Movie"), view="FullMetadata")
    with pytest.raises(M.RecordXmlError, match="nothing to write"):
        M.record_to_xml({"SelfDefinedMetadata": {"BaseObjectData": {"Mode": " "}}})
    with pytest.raises(ValueError, match="view must be"):
        M.record_to_xml(_sheet_record("edit", "Movie"), view="Self")


def test_record_to_xml_refuses_a_compilation_rather_than_write_half_of_it():
    xml = ('<SelfDefinedMetadata xmlns="http://www.eidr.org/schema" '
           'xmlns:md="http://www.movielabs.com/schema/md/v2.8/md"><BaseObjectData>'
           '<StructuralType>Abstraction</StructuralType></BaseObjectData><ExtraObjectMetadata>'
           '<CompilationInfo><md:Entry><md:EntryNumber>1</md:EntryNumber></md:Entry>'
           '</CompilationInfo></ExtraObjectMetadata></SelfDefinedMetadata>')
    with pytest.raises(M.RecordXmlError, match="CompilationInfo"):
        M.record_to_xml(M.record_from_xml(xml))


def test_record_to_xml_declares_md_and_xsi_only_when_used():
    out = M.record_to_xml({"SelfDefinedMetadata": {"BaseObjectData": {"Mode": "AudioVisual"}}})
    assert "xmlns:md=" not in out and "xmlns:xsi=" not in out
    assert out.endswith('<SelfDefinedMetadata xmlns="http://www.eidr.org/schema">'
                        "<BaseObjectData><Mode>AudioVisual</Mode></BaseObjectData>"
                        "</SelfDefinedMetadata>")


def test_record_to_xml_does_not_mutate_its_input():
    r = _sheet_record("episodic", "TV")
    before = copy.deepcopy(r)
    M.record_to_xml(r)
    assert r == before
