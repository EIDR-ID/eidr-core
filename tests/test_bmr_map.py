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
    assert base["ResourceName"] == [
        {"Title": "Pilot", "TitleClass": "release", "_lang": "en"},
        {"Title": "Le Pilote", "TitleClass": "translated", "_lang": "fr",
         "SystemGenerated": "false"}]
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
    row = M.row_from_record(M.record_from_xml(_MSG), "episodic", source="full")
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
