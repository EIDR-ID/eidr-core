"""Write (or check) the merge-rules golden fixtures under src/eidr_core/specs/merge_pairs/.

The fixtures are the language-neutral corpus (merge-rules.md section 7): per
fixture a directory with ``current.xml`` (the registry's SelfDefinedMetadata),
``supplied.xml`` (or ``supplied_row.json``, a Template-22 row that B5's
``bmr_map.record_from_row`` reads), optionally ``full.xml`` (the registry's
FullMetadata) and ``expected.json`` (the invariants). This script is the
authoring surface: each fixture below states its records as small
standard-record overrides of a base record and its EXPECTED report by hand.
Nothing here runs the engine, so an expectation is a claim the conformance
test (tests/test_merge_pairs.py) checks, never a snapshot of whatever the
engine did.

    python tools/gen_merge_pairs.py --write   # regenerate the corpus
    python tools/gen_merge_pairs.py --check   # exit 1 when the files differ

Invariants are version-independent in golden-pairs.md section 6's sense: the
report's entries (rule, field key, action, old, new, normalised value), the
conflict codes and skip keys -- never the prose of a reason -- plus named
values of the merged record. Each fixture's ``why`` says what it pins and
``mutation`` what must break it; the conformance test disables the
fixture's rule and asserts the fixture then FAILS (section 6 item 1).
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eidr_core.bmr_map import record_to_xml  # noqa: E402

OUT = ROOT / "src" / "eidr_core" / "specs" / "merge_pairs"
ID = "10.5240/7791-8534-2C23-9030-8610-5"
PARENT = "10.5240/0D7A-3B2C-1E5F-8A90-6C4D-K"
PARTY = "10.5237/A1B2-C3D4"

BASE: dict[str, Any] = {
    "StructuralType": "Abstraction", "Mode": "AudioVisual", "ReferentType": "Movie",
    "ResourceName": [{"Title": "Example Film", "_lang": "en"}],
    "OriginalLanguage": [{"value": "en", "_mode": "Audio"}],
    "ReleaseDate": "2001-05-04", "CountryOfOrigin": ["US"],
    "ApproximateLength": "PT1H40M",
    "Administrators": {"Registrant": PARTY},
}
CURRENT_ONLY = {"ID": ID, "Status": "valid"}

# The episodic shapes: an Episode (parent named, so it inherits), a Season and
# a Series.
EPISODE = {"ReferentType": "TV", "ReleaseDate": None, "ApproximateLength": None,
           "ResourceName": [{"Title": "Pilot", "_lang": "en"}]}
EPISODE_X = {"EpisodeInfo": {"Parent": PARENT,
                             "SequenceInfo": {"DistributionNumber": {"Number": "1"}}}}
SEASON = {"ReferentType": "Season", "ReleaseDate": None, "ApproximateLength": None,
          "ResourceName": [{"Title": "Example Show: Season 1", "_lang": "en"}]}
SEASON_X = {"SeasonInfo": {"Parent": PARENT}}
SERIES = {"ReferentType": "Series", "ResourceName": [{"Title": "Example Show", "_lang": "en"}],
          "ApproximateLength": "PT30M"}


def _apply(base: dict[str, Any], over: dict[str, Any] | None) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if v is None:
            out.pop(k, None)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _record(bod: dict[str, Any], extra: dict[str, Any] | None,
            view: str = "SelfDefinedMetadata") -> dict[str, Any]:
    block: dict[str, Any] = {"BaseObjectData": bod}
    if extra:
        block["ExtraObjectMetadata"] = extra
    return {view: block}


def F(fid: str, set_: str, rule: str | None, why: str, mutation: str, *,
      cur: dict[str, Any] | None = None, sup: dict[str, Any] | None = None,
      cur_x: dict[str, Any] | None = None, sup_x: dict[str, Any] | None = None,
      shape: tuple[dict[str, Any], dict[str, Any] | None] | None = None,
      full: dict[str, Any] | None = None, row: dict[str, Any] | None = None,
      patch: tuple[str, str] | None = None, options: dict[str, Any] | None = None,
      changed: bool, changes: list[list[Any]] = (), conflicts: list[list[str]] = (),  # type: ignore[assignment]
      skipped: list[list[str]] = (), merged: list[list[Any]] = (),  # type: ignore[assignment]
      altid_lines: list[str] | None = None, order: bool = False) -> dict[str, Any]:
    """One fixture. ``shape`` is (BaseObjectData overrides, ExtraObjectMetadata)
    applied to BOTH sides before ``cur``/``sup``; ``patch`` edits current.xml
    text (for attribute spellings record_to_xml never writes, like
    relation="")."""
    s_bod, s_x = (shape if shape else ({}, None))
    cur_bod = _apply(_apply(_apply(BASE, CURRENT_ONLY), s_bod), cur)
    sup_bod = _apply(_apply(BASE, s_bod), sup)
    cur_extra = _apply(s_x or {}, cur_x) or None
    sup_extra = _apply(s_x or {}, sup_x) or None
    return {"id": fid, "set": set_, "rule": rule, "why": why, "mutation": mutation,
            "options": options or {},
            "current": _record(cur_bod, cur_extra), "supplied": _record(sup_bod, sup_extra),
            "full": full, "row": row, "patch": patch,
            "invariants": {"changed": changed, "changes": [list(c) for c in changes],
                           "conflicts": [list(c) for c in conflicts],
                           "skipped": [list(s) for s in skipped],
                           "merged": [list(m) for m in merged],
                           **({"altid_lines": altid_lines} if altid_lines is not None else {}),
                           **({"schema_order": True} if order else {})}}


IMDB = {"AltID": "tt0133093", "Type": "IMDB"}
TMDB = {"AltID": "603", "Type": "Proprietary", "Domain": "themoviedb.org/movie"}
ORG = {"_idType": "EIDRPartyID", "_organizationID": "10.5237/1234-5678", "_role": "producer",
       "DisplayName": "Acme Pictures"}

FIXTURES: list[dict[str, Any]] = [
    # ---------------------------------------------------------------- per rule
    F("identical-records-change-nothing", "per_rule", None,
      "The base pair: a supplied record equal to the registry's changes nothing, so the "
      "caller submits nothing (changed false, merged_xml null).",
      "any rule that edits without its condition holding",
      changed=False),
    F("r01-title-language-copied", "per_rule", "1",
      "An EIDR title in 'und' takes the real lang of a supplied title with the same "
      "normalized text.", "rule 1 disabled",
      cur={"ResourceName": [{"Title": "Example Film", "_lang": "und"}]},
      changed=True, changes=[["1", "title_language:primary", "replace", "und", "en",
                              "example film"]],
      merged=[["BaseObjectData/ResourceName/0/_lang", "en"]]),
    F("r01-title-language-not-from-und", "per_rule", "1",
      "A supplied title that is itself 'und' gives nothing to copy.",
      "rule 1 copying any supplied lang", changed=False,
      cur={"ResourceName": [{"Title": "Example Film", "_lang": "und"}]},
      sup={"ResourceName": [{"Title": "Example Film", "_lang": "und"}]}),
    F("r03-different-title-added", "per_rule", "3",
      "A supplied title fuzzy-different from every EIDR title becomes an alternate, with its "
      "lang.", "rule 3 disabled",
      sup={"AlternateResourceName": [{"Title": "Un film d'exemple", "_lang": "fr"}]},
      changed=True, changes=[["3", "title:alternate", "add", None, "Un film d'exemple",
                              "un film d'exemple"]],
      merged=[["BaseObjectData/AlternateResourceName/0/_lang", "fr"]]),
    F("r03-similar-title-skipped", "per_rule", "3",
      "A supplied title within FUZZY_THRESHOLD of an EIDR title is not added and is reported "
      "(distance 1: Exemple/Example).", "rule 3 adding without the fuzzy test",
      sup={"AlternateResourceName": [{"Title": "Exemple Film", "_lang": "fr"}]},
      changed=False, skipped=[["3", "title:alternate"]]),
    F("r08-country-added", "per_rule", "8",
      "A supplied country not present is added.", "rule 8 disabled",
      sup={"CountryOfOrigin": ["US", "FR"]},
      changed=True, changes=[["8", "country_of_origin", "add", None, "FR", "fr"]],
      merged=[["BaseObjectData/CountryOfOrigin", ["US", "FR"]]]),
    F("r08-xx-dropped-when-a-country-arrives", "per_rule", "8",
      "XX goes once the list holds anything else.", "rule 8 disabled",
      cur={"CountryOfOrigin": ["XX"]}, sup={"CountryOfOrigin": ["FR"]},
      changed=True, changes=[["8", "country_of_origin", "add", None, "FR", "fr"],
                             ["8", "country_of_origin", "remove", "XX", None, "xx"]],
      merged=[["BaseObjectData/CountryOfOrigin", ["FR"]]]),
    F("r08-supplied-xx-never-added", "per_rule", "8",
      "A supplied XX is never added (cond_CountryMismatch).", "rule 8 adding XX",
      sup={"CountryOfOrigin": ["XX"]}, changed=False),
    F("r09-original-language-added", "per_rule", "9",
      "A supplied (code, mode) pair not present is added.", "rule 9 disabled",
      sup={"OriginalLanguage": [{"value": "en", "_mode": "Audio"},
                                {"value": "fr", "_mode": "Audio"}]},
      changed=True, changes=[["9", "original_language", "add", None, "fr (Audio)", "fr|audio"]]),
    F("r09-und-dropped-when-a-language-arrives", "per_rule", "9",
      "und goes once another language of the same mode is listed.", "rule 9 disabled",
      cur={"OriginalLanguage": [{"value": "und", "_mode": "Audio"}]},
      sup={"OriginalLanguage": [{"value": "fr", "_mode": "Audio"}]},
      changed=True, changes=[["9", "original_language", "add", None, "fr (Audio)", "fr|audio"],
                             ["9", "original_language", "remove", "und (Audio)", None,
                              "und|audio"]],
      merged=[["BaseObjectData/OriginalLanguage", [{"value": "fr", "_mode": "Audio"}]]]),
    F("r09-zxx-kept-beside-another-mode", "per_rule", "9",
      "zxx is dropped only beside another language OF ITS MODE: a silent Audio track and "
      "English intertitles (Visual) both stay. Scope: pins the per-mode reading of 'drop zxx "
      "if anything else is present' (open question in the S3 report).",
      "the zxx/und drop applied across modes",
      cur={"OriginalLanguage": [{"value": "zxx", "_mode": "Audio"}]},
      sup={"OriginalLanguage": [{"value": "en", "_mode": "Visual"}]},
      changed=True, changes=[["9", "original_language", "add", None, "en (Visual)",
                              "en|visual"]],
      merged=[["BaseObjectData/OriginalLanguage", [{"value": "zxx", "_mode": "Audio"},
                                                   {"value": "en", "_mode": "Visual"}]]]),
    F("r09-supplied-und-never-added", "per_rule", "9",
      "A supplied und is never added (cond_OriginalLanguageMatch).", "rule 9 adding und",
      sup={"OriginalLanguage": [{"value": "und", "_mode": "Audio"}]}, changed=False),
    F("r10-version-language-added", "per_rule", "10",
      "As rule 9, for VersionLanguage.", "rule 10 disabled",
      sup={"VersionLanguage": [{"value": "fr", "_mode": "Audio"}]},
      changed=True, changes=[["10", "version_language", "add", None, "fr (Audio)",
                              "fr|audio"]]),
    F("r11-org-added", "per_rule", "11",
      "A supplied org with no (party ID or fuzzy name) + role match is added; the key carries "
      "the role, the value the party ID.", "rule 11 disabled",
      sup={"AssociatedOrg": [ORG]},
      changed=True, changes=[["11", "associated_org:producer", "add", None, "Acme Pictures",
                              "10.5237/1234-5678"]]),
    F("r11-org-name-within-org-threshold", "per_rule", "11",
      "Org names match within FUZZY_THRESHOLD_ORG (6), not FUZZY_THRESHOLD (4): "
      "'Acme Pictures Co' vs 'Acme Pictures Company' is distance 5.",
      "rule 11 comparing names on FUZZY_THRESHOLD",
      cur={"AssociatedOrg": [{"_role": "producer", "DisplayName": "Acme Pictures Company"}]},
      sup={"AssociatedOrg": [{"_role": "producer", "DisplayName": "Acme Pictures Co"}]},
      changed=False),
    F("r11-same-org-other-role-added", "per_rule", "11",
      "The role is part of the match: the same party in another role is added.",
      "rule 11 ignoring the role",
      cur={"AssociatedOrg": [ORG]},
      sup={"AssociatedOrg": [dict(ORG, _role="distributor")]},
      changed=True, changes=[["11", "associated_org:distributor", "add", None, "Acme Pictures",
                              "10.5237/1234-5678"]]),
    F("r12-director-added", "per_rule", "12",
      "A director whose DisplayName is fuzzy-absent is added.", "rule 12 disabled",
      sup={"Credits": {"Director": [{"DisplayName": "Jane Doe"}]}},
      changed=True, changes=[["12", "director", "add", None, "Jane Doe", "jane doe"]]),
    F("r12-director-nickname-tolerant", "per_rule", "12",
      "A quoted nickname does not make a director different: 'Robert \"Bobby Joe\" Jones' is "
      "'Robert Jones' (distance 10 with the nickname, 0 without).",
      "rule 12 without the nickname steps",
      cur={"Credits": {"Director": [{"DisplayName": 'Robert "Bobby Joe" Jones'}]}},
      sup={"Credits": {"Director": [{"DisplayName": "Robert Jones"}]}},
      changed=False),
    F("r12-director-schema-maximum", "per_rule", "12",
      "Directors stop at the schema's maxOccurs (2), and the refusal is reported.",
      "rule 12 ignoring the schema cap",
      cur={"Credits": {"Director": [{"DisplayName": "Jane Doe"}, {"DisplayName": "John Roe"}]}},
      sup={"Credits": {"Director": [{"DisplayName": "Mary Major"}]}},
      changed=False, skipped=[["12", "director"]]),
    F("r13-actor-added", "per_rule", "13",
      "As rule 12, for actors.", "rule 13 disabled",
      sup={"Credits": {"Actor": [{"DisplayName": "Keanu Reeves"}]}},
      changed=True, changes=[["13", "actor", "add", None, "Keanu Reeves", "keanu reeves"]]),
    F("r14-status-never-merged", "per_rule", "14",
      "Rule 14 is skipped (the registry will not allow it); a different supplied Status is "
      "reported, never written.", "rule 14 writing the Status",
      sup={"Status": "in development"},
      changed=False, skipped=[["14", "status"]]),
    F("r15-length-added-when-none", "per_rule", "15",
      "A parentless record with no length takes the supplied one.", "rule 15 disabled",
      cur={"ApproximateLength": None},
      changed=True, changes=[["15", "approximate_length", "add", None, "PT1H40M", "pt1h40m"]]),
    F("r15-unflagged-length-kept", "per_rule", "15",
      "An unflagged EIDR length is never replaced (the .NET round-figure replacement is not "
      "ruled and not carried).", "rule 15 replacing an unflagged length",
      cur={"ApproximateLength": "PT1H30M"}, changed=False),
    F("r15-movie-under-45-minutes-becomes-short", "per_rule", "15",
      "ReferentType is preserved except Movie with a resulting length under 45 minutes "
      "becomes Short.", "rule 15 without the Movie/Short switch",
      cur={"ApproximateLength": None}, sup={"ApproximateLength": "PT30M"},
      changed=True, changes=[["15", "approximate_length", "add", None, "PT30M", "pt30m"],
                             ["15", "referent_type", "replace", "Movie", "Short", "short"]]),
    F("r16-description-added-with-language", "per_rule", "16",
      "A supplied description and its language are added together when EIDR has none.",
      "rule 16 disabled",
      sup={"Description": {"Description": "A film about an example.", "_lang": "en"}},
      changed=True, changes=[["16", "description:en", "add", None, "A film about an example.",
                              "a film about an example."]],
      merged=[["BaseObjectData/Description/_lang", "en"]]),
    F("r16-existing-description-kept", "per_rule", "16",
      "EIDR's own description is never replaced.", "rule 16 replacing a description",
      cur={"Description": {"Description": "The registry's text.", "_lang": "en"}},
      sup={"Description": {"Description": "A film about an example.", "_lang": "en"}},
      changed=False),
    F("r17-registrant-extra-pair-added", "per_rule", "17",
      "A supplied key:value pair whose key EIDR lacks is added.", "rule 17 disabled",
      sup={"RegistrantExtra": "RT:Podcast;"},
      changed=True, changes=[["17", "registrant_extra:rt", "add", None, "RT:Podcast;",
                              "podcast"]],
      merged=[["BaseObjectData/RegistrantExtra", "RT:Podcast;"]]),
    F("r17-key-present-with-other-value", "per_rule", "17",
      "A key EIDR already has is not overwritten; the other value is reported.",
      "rule 17 adding by pair instead of by key",
      cur={"RegistrantExtra": "RT:MusicVideo;"}, sup={"RegistrantExtra": "RT:Podcast;"},
      changed=False, skipped=[["17", "registrant_extra:rt"]]),
    F("r18a-metadata-authority-added", "per_rule", "18a",
      "Rule 18a is restored: a supplied Metadata Authority party ID not present is added.",
      "rule 18a disabled",
      sup={"Administrators": {"Registrant": PARTY, "MetadataAuthority": ["10.5237/9999-0000"]}},
      changed=True, changes=[["18a", "metadata_authority", "add", None, "10.5237/9999-0000",
                              "10.5237/9999-0000"]]),
    F("r18a-present-authority-not-repeated", "per_rule", "18a",
      "A party ID already listed (case-insensitive) is not added again.",
      "rule 18a comparing case-sensitively",
      cur={"Administrators": {"Registrant": PARTY, "MetadataAuthority": ["10.5237/ABCD-0000"]}},
      sup={"Administrators": {"Registrant": PARTY, "MetadataAuthority": ["10.5237/abcd-0000"]}},
      changed=False),
    F("r18-alt-id-added", "per_rule", "18",
      "A supplied Alt ID absent from the record is added, and its AltIDTool line composed by "
      "format_line (18.6).", "rule 18 disabled",
      sup={"AlternateID": [TMDB]},
      changed=True, changes=[["18", "alt_id:proprietary|themoviedb.org/movie", "add", None,
                              "603", "603"]],
      altid_lines=[f"{ID}\tProprietary\t603\tthemoviedb.org/movie"]),
    F("r18-alt-id-present-is-silent", "per_rule", "18",
      "The same Kind+value under the same relation is skipped silently (18.3).",
      "rule 18 re-adding a present value",
      cur={"AlternateID": [IMDB]}, sup={"AlternateID": [IMDB]}, changed=False),
    F("r19-series-info-flags-not-merged", "per_rule", "19",
      "Rule 19 is skipped: SeriesInfo flags are reported, never written.",
      "rule 19 writing flags", shape=(SERIES, None),
      sup_x={"SeriesInfo": {"NumberRequired": "true"}},
      changed=False, skipped=[["19", "series_info"]]),
    F("r20-series-class-added", "per_rule", "20",
      "A Series with no SeriesClass takes the supplied one.", "rule 20 disabled",
      shape=(SERIES, None), sup_x={"SeriesInfo": {"SeriesClass": "Mini-series"}},
      changed=True, changes=[["20", "series_class", "add", None, "Mini-series", "mini-series"]],
      merged=[["ExtraObjectMetadata/SeriesInfo/SeriesClass", "Mini-series"]]),
    F("r20-series-class-kept", "per_rule", "20",
      "A Series that has a SeriesClass keeps it.", "rule 20 replacing a class",
      shape=(SERIES, None), cur_x={"SeriesInfo": {"SeriesClass": "Episodic"}},
      sup_x={"SeriesInfo": {"SeriesClass": "Mini-series"}}, changed=False),
    F("r21-end-date-added", "per_rule", "21",
      "A Series with no EndDate takes the supplied one.", "rule 21 disabled",
      shape=(SERIES, None), sup_x={"SeriesInfo": {"EndDate": "2005-06-01"}},
      changed=True, changes=[["21", "end_date", "add", None, "2005-06-01", "2005-06-01"]]),
    F("r21-end-date-kept", "per_rule", "21",
      "An existing EndDate is kept.", "rule 21 replacing an EndDate",
      shape=(SERIES, None), cur_x={"SeriesInfo": {"EndDate": "2004-01-01"}},
      sup_x={"SeriesInfo": {"EndDate": "2005-06-01"}}, changed=False),
    F("r22-season-number-added", "per_rule", "22",
      "A Season with no SequenceNumber takes the supplied one.", "rule 22 disabled",
      shape=(SEASON, SEASON_X), sup_x={"SeasonInfo": {"Parent": PARENT, "SequenceNumber": "2"}},
      changed=True, changes=[["22", "season_number", "add", None, "2", "2"]]),
    F("r22-season-number-kept", "per_rule", "22",
      "An existing SequenceNumber is kept.", "rule 22 replacing a number",
      shape=(SEASON, SEASON_X), cur_x={"SeasonInfo": {"Parent": PARENT, "SequenceNumber": "1"}},
      sup_x={"SeasonInfo": {"Parent": PARENT, "SequenceNumber": "2"}}, changed=False),
    F("r23-season-class-added", "per_rule", "23",
      "Every supplied SeasonClass not present is added.", "rule 23 disabled",
      shape=(SEASON, SEASON_X),
      sup_x={"SeasonInfo": {"Parent": PARENT, "SeasonClass": ["Main"]}},
      changed=True, changes=[["23", "season_class", "add", None, "Main", "main"]]),
    F("r23-season-class-present", "per_rule", "23",
      "A class already present (exact, case-folded) is not added again.",
      "rule 23 comparing case-sensitively", shape=(SEASON, SEASON_X),
      cur_x={"SeasonInfo": {"Parent": PARENT, "SeasonClass": ["Main"]}},
      sup_x={"SeasonInfo": {"Parent": PARENT, "SeasonClass": ["main"]}}, changed=False),
    F("r24-episode-class-added", "per_rule", "24",
      "Every supplied EpisodeClass not present is added (exact; no fuzzy).",
      "rule 24 disabled", shape=(EPISODE, EPISODE_X),
      sup_x={"EpisodeInfo": dict(EPISODE_X["EpisodeInfo"], EpisodeClass=["Pilot"])},
      changed=True, changes=[["24", "episode_class", "add", None, "Pilot", "pilot"]]),
    F("r24-episode-class-no-fuzzy", "per_rule", "24",
      "Episode classes compare exactly: 'Recut' is not 'Main' though both are short words "
      "within FUZZY_THRESHOLD of each other.", "rule 24 comparing fuzzily",
      shape=(EPISODE, EPISODE_X),
      cur_x={"EpisodeInfo": dict(EPISODE_X["EpisodeInfo"], EpisodeClass=["Main"])},
      sup_x={"EpisodeInfo": dict(EPISODE_X["EpisodeInfo"], EpisodeClass=["Recut"])},
      changed=True, changes=[["24", "episode_class", "add", None, "Recut", "recut"]]),
    F("r25-distribution-number-added", "per_rule", "25",
      "An Episode with no DistributionNumber takes the supplied one; the key carries its "
      "domain.", "rule 25 disabled", shape=(EPISODE, None),
      cur_x={"EpisodeInfo": {"Parent": PARENT, "SequenceInfo": {"HouseSequence":
                                                                 {"Number": "H1"}}}},
      sup_x={"EpisodeInfo": {"Parent": PARENT, "SequenceInfo": {"DistributionNumber": {
          "Number": "5", "Domain": "example.com"}}}},
      changed=True, changes=[["25", "distribution_number:example.com", "add", None, "5", "5"]]),
    F("r25-distribution-number-kept", "per_rule", "25",
      "An existing DistributionNumber is kept.", "rule 25 replacing a number",
      shape=(EPISODE, EPISODE_X),
      sup_x={"EpisodeInfo": {"Parent": PARENT, "SequenceInfo": {"DistributionNumber": {
          "Number": "5"}}}}, changed=False),
    F("r26-house-sequence-added", "per_rule", "26",
      "An Episode with no HouseSequence takes the supplied one with its domain.",
      "rule 26 disabled", shape=(EPISODE, EPISODE_X),
      sup_x={"EpisodeInfo": {"Parent": PARENT, "SequenceInfo": {
          "DistributionNumber": {"Number": "1"},
          "HouseSequence": {"Number": "H-101", "Domain": "example.com"}}}},
      changed=True, changes=[["26", "house_sequence:example.com", "add", None, "H-101",
                              "h-101"]]),
    F("r26-house-sequence-kept", "per_rule", "26",
      "An existing HouseSequence is kept.", "rule 26 replacing a number",
      shape=(EPISODE, None),
      cur_x={"EpisodeInfo": {"Parent": PARENT, "SequenceInfo": {
          "DistributionNumber": {"Number": "1"}, "HouseSequence": {"Number": "H-100"}}}},
      sup_x={"EpisodeInfo": {"Parent": PARENT, "SequenceInfo": {
          "DistributionNumber": {"Number": "1"}, "HouseSequence": {"Number": "H-101"}}}},
      changed=False),
    F("r27-alternate-numbers-added", "per_rule", "27",
      "Each supplied (number, domain) pair not present is added.", "rule 27 disabled",
      shape=(EPISODE, EPISODE_X),
      sup_x={"EpisodeInfo": {"Parent": PARENT, "SequenceInfo": {
          "DistributionNumber": {"Number": "1"},
          "AlternateNumber": [{"Number": "101", "Domain": "a.example.com"},
                              {"Number": "S01E01", "Domain": "b.example.com"}]}}},
      changed=True, changes=[["27", "alternate_number:a.example.com", "add", None, "101",
                              "101"],
                             ["27", "alternate_number:b.example.com", "add", None, "S01E01",
                              "s01e01"]]),
    F("r27-alternate-number-case-insensitive", "per_rule", "27",
      "The pair compares case-insensitively.", "rule 27 comparing case-sensitively",
      shape=(EPISODE, None),
      cur_x={"EpisodeInfo": {"Parent": PARENT, "SequenceInfo": {
          "DistributionNumber": {"Number": "1"},
          "AlternateNumber": [{"Number": "S01E01", "Domain": "b.example.com"}]}}},
      sup_x={"EpisodeInfo": {"Parent": PARENT, "SequenceInfo": {
          "DistributionNumber": {"Number": "1"},
          "AlternateNumber": [{"Number": "s01e01", "Domain": "B.EXAMPLE.COM"}]}}},
      changed=False),
    F("r28-time-slot-added", "per_rule", "28",
      "An Episode with no TimeSlot takes the supplied one.", "rule 28 disabled",
      shape=(EPISODE, EPISODE_X),
      sup_x={"EpisodeInfo": dict(EPISODE_X["EpisodeInfo"], TimeSlot="20:00:00")},
      changed=True, changes=[["28", "time_slot", "add", None, "20:00:00", "20:00:00"]]),
    F("r28-time-slot-kept", "per_rule", "28",
      "An existing TimeSlot is kept.", "rule 28 replacing a slot",
      shape=(EPISODE, EPISODE_X),
      cur_x={"EpisodeInfo": dict(EPISODE_X["EpisodeInfo"], TimeSlot="21:00:00")},
      sup_x={"EpisodeInfo": dict(EPISODE_X["EpisodeInfo"], TimeSlot="20:00:00")},
      changed=False),
    # -------------------------------------------------------------- pre-process
    F("pre1-alternate-equal-to-main-removed", "pre_process", "pre.1",
      "An alternate equal (normalized) to the main title or an earlier alternate is removed "
      "from the fetched record, which alone makes the record change.", "pre.1 disabled",
      cur={"AlternateResourceName": [{"Title": "Example Film!", "_lang": "en"},
                                     {"Title": "Otro", "_lang": "es"},
                                     {"Title": "otro", "_lang": "es"}]},
      changed=True, changes=[["pre.1", "title:alternate", "remove", "Example Film!", None,
                              "example film!"],
                             ["pre.1", "title:alternate", "remove", "otro", None, "otro"]],
      merged=[["BaseObjectData/AlternateResourceName", [{"Title": "Otro", "_lang": "es"}]]]),
    F("pre2-duplicate-director-removed", "pre_process", "pre.2",
      "A director repeated (normalized DisplayName) is removed.", "pre.2 disabled",
      cur={"Credits": {"Director": [{"DisplayName": "Jane Doe"}, {"DisplayName": "JANE DOE"}]}},
      sup={"Credits": {"Director": [{"DisplayName": "Jane Doe"}]}},
      changed=True, changes=[["pre.2", "director", "remove", "JANE DOE", None, "jane doe"]]),
    F("pre3-duplicate-actor-removed", "pre_process", "pre.3",
      "An actor repeated is removed.", "pre.3 disabled",
      cur={"Credits": {"Actor": [{"DisplayName": "Ann Lee"}, {"DisplayName": "Ann Lee"}]}},
      sup={"Credits": {"Actor": [{"DisplayName": "Ann Lee"}]}},
      changed=True, changes=[["pre.3", "actor", "remove", "Ann Lee", None, "ann lee"]]),
    F("pre4-duplicate-org-party-id-removed", "pre_process", "pre.4",
      "An org repeating another's (role, EIDR party ID) is removed.", "pre.4 disabled",
      cur={"AssociatedOrg": [ORG, dict(ORG, DisplayName="Acme")]}, sup={"AssociatedOrg": [ORG]},
      changed=True, changes=[["pre.4", "associated_org:producer", "remove", "Acme", None,
                              "10.5237/1234-5678"]]),
    F("pre5-duplicate-metadata-authority-removed", "pre_process", "pre.5",
      "A repeated Metadata Authority party ID is removed.", "pre.5 disabled",
      cur={"Administrators": {"Registrant": PARTY,
                              "MetadataAuthority": ["10.5237/9999-0000", "10.5237/9999-0000"]}},
      sup={"Administrators": {"Registrant": PARTY, "MetadataAuthority": ["10.5237/9999-0000"]}},
      changed=True, changes=[["pre.5", "metadata_authority", "remove", "10.5237/9999-0000", None,
                              "10.5237/9999-0000"]]),
    F("pre6-lone-aq-becomes-xx", "pre_process", "pre.6",
      "CleanCountryOfOrigin: a lone AQ becomes XX.", "pre.6 disabled",
      cur={"CountryOfOrigin": ["AQ"]}, sup={"CountryOfOrigin": ["XX"]},
      changed=True, changes=[["pre.6", "country_of_origin", "replace", "AQ", "XX", "xx"]]),
    F("pre6-xx-removed-beside-others", "pre_process", "pre.6",
      "CleanCountryOfOrigin: with more than one country every XX goes.", "pre.6 disabled",
      cur={"CountryOfOrigin": ["XX", "US"]},
      changed=True, changes=[["pre.6", "country_of_origin", "remove", "XX", None, "xx"]]),
    F("pre7-season-is-an-abstraction", "pre_process", "pre.7",
      "CleanStructuralType: a Season (or Series) is an Abstraction.", "pre.7 disabled",
      shape=(SEASON, SEASON_X), cur={"StructuralType": "Performance"},
      changed=True, changes=[["pre.7", "structural_type", "replace", "Performance",
                              "Abstraction", "abstraction"]]),
    # ---------------------------------------------------------- .NET regressions
    F("net1-alt-id-family-read-past-a-gap", "net_regression", "18",
      "SpreadsheetData.cs stopped at the first blank 'Alt ID N', losing every Alt ID to its "
      "right. B5 reads the family sparsely (bmr_io.family_layout), so 'Alt ID 3' beside a blank "
      "'Alt ID 1' and 'Alt ID 2' still arrives and is added.",
      "B5 reading families densely, or rule 18 disabled",
      row={"template": "non_episodic", "cells": {
          "Title": "Example Film", "Title Language": "en", "Structural Type": "Abstraction",
          "Mode": "AudioVisual", "Referent Type": "Movie", "Release Date": "2001-05-04",
          "Country of Origin": "US", "Approx Length": "PT1H40M",
          "Original Language": "en", "Language Mode": "Audio", "Registrant": PARTY,
          "Alt ID 1": None, "Domain 1": None, "Alt ID 2": None, "Domain 2": None,
          "Alt ID 3": "603", "Domain 3": "themoviedb.org/movie"}},
      changed=True, changes=[["18", "alt_id:proprietary|themoviedb.org/movie", "add", None,
                              "603", "603"]]),
    F("net1-country-family-read-past-a-gap", "net_regression", "8",
      "The same stop-at-first-blank loop lost Countries of Origin: 'Country of Origin 2' "
      "beside a blank 'Country of Origin' arrives and is added.",
      "B5 reading families densely, or rule 8 disabled",
      row={"template": "non_episodic", "cells": {
          "Title": "Example Film", "Title Language": "en", "Structural Type": "Abstraction",
          "Mode": "AudioVisual", "Referent Type": "Movie", "Release Date": "2001-05-04",
          "Country of Origin": None, "Country of Origin 2": "FR", "Approx Length": "PT1H40M",
          "Original Language": "en", "Language Mode": "Audio", "Registrant": PARTY}},
      changed=True, changes=[["8", "country_of_origin", "add", None, "FR", "fr"]]),
    F("net1-blank-domain-reported-not-fatal", "net_regression", "18",
      "A blank 'Domain N' beside a value threw and failed the whole .NET row. Here that one "
      "Alt ID is reported (a Proprietary Alt ID needs a domain) and the row's other Alt ID "
      "is still added.", "rule 18 validation disabled, or a row-level failure",
      row={"template": "non_episodic", "cells": {
          "Title": "Example Film", "Title Language": "en", "Structural Type": "Abstraction",
          "Mode": "AudioVisual", "Referent Type": "Movie", "Release Date": "2001-05-04",
          "Country of Origin": "US", "Approx Length": "PT1H40M",
          "Original Language": "en", "Language Mode": "Audio", "Registrant": PARTY,
          "Alt ID 1": "12345", "Domain 1": None,
          "Alt ID 2": "603", "Domain 2": "themoviedb.org/movie"}},
      changed=True, conflicts=[["18", "alt_id:proprietary|", "ALT_ID_MISSING_DOMAIN"]],
      changes=[["18", "alt_id:proprietary|themoviedb.org/movie", "add", None, "603", "603"]]),
    F("net2-alt-id-type-from-the-schema", "net_regression", "18",
      "SpreadsheetData.cs knew 25 named types and turned anything else into Proprietary with "
      "the type as its domain. ShortDOI is a schema type missing from that list: it arrives "
      "as Type ShortDOI (key alt_id:shortdoi|), not Proprietary/ShortDOI.",
      "a hardcoded type list without ShortDOI",
      row={"template": "non_episodic", "cells": {
          "Title": "Example Film", "Title Language": "en", "Structural Type": "Abstraction",
          "Mode": "AudioVisual", "Referent Type": "Movie", "Release Date": "2001-05-04",
          "Country of Origin": "US", "Approx Length": "PT1H40M",
          "Original Language": "en", "Language Mode": "Audio", "Registrant": PARTY,
          "Alt ID 1": "10/abc12", "Domain 1": "ShortDOI"}},
      changed=True, changes=[["18", "alt_id:shortdoi|", "add", None, "10/abc12", "10/abc12"]]),
    F("net3-schema-cap-not-dotnet-cap", "net_regression", "27",
      "CompareEidrRecord.cs capped alternate numbers at 1 (and episode classes at 1); the "
      "schema allows 32. A second alternate number is added.",
      "rule 27 capped at 1", shape=(EPISODE, None),
      cur_x={"EpisodeInfo": {"Parent": PARENT, "SequenceInfo": {
          "DistributionNumber": {"Number": "1"},
          "AlternateNumber": [{"Number": "101", "Domain": "a.example.com"}]}}},
      sup_x={"EpisodeInfo": {"Parent": PARENT, "SequenceInfo": {
          "DistributionNumber": {"Number": "1"},
          "AlternateNumber": [{"Number": "S01E01", "Domain": "b.example.com"}]}}},
      changed=True, changes=[["27", "alternate_number:b.example.com", "add", None, "S01E01",
                              "s01e01"]]),
    F("net4-end-date-condition-live", "net_regression", "21",
      "AddMissingEndDate's condition null-dereferenced and never fired; rule 21 adds the "
      "EndDate to a Series that has a SeriesInfo but no EndDate.", "rule 21 disabled",
      shape=(SERIES, None), cur_x={"SeriesInfo": {"SeriesClass": "Episodic"}},
      sup_x={"SeriesInfo": {"SeriesClass": "Episodic", "EndDate": "2005-06-01"}},
      changed=True, changes=[["21", "end_date", "add", None, "2005-06-01", "2005-06-01"]]),
    F("net5-season-classes-condition-live", "net_regression", "23",
      "AddMissingSeasonClasses copied the season-NUMBER condition (EIDR without a number, "
      "supplied with one), so a Season that already had its number never got classes. Here "
      "both carry SequenceNumber and the class is still added.", "rule 23 disabled",
      shape=(SEASON, None),
      cur_x={"SeasonInfo": {"Parent": PARENT, "SequenceNumber": "1"}},
      sup_x={"SeasonInfo": {"Parent": PARENT, "SequenceNumber": "1", "SeasonClass": ["Main"]}},
      changed=True, changes=[["23", "season_class", "add", None, "Main", "main"]]),
    F("net6-series-info-flags-never-written", "net_regression", "19",
      "AddMissingSeriesInfo wrote malformed XML (<NumberRequired>false</NumberRequired). Rule "
      "19 is skipped: the flags are reported and nothing is written.",
      "rule 19 writing SeriesInfo flags", shape=(SERIES, None),
      sup_x={"SeriesInfo": {"NumberRequired": "true", "DateRequired": "false",
                            "OriginalTitleRequired": "false"}},
      changed=False, skipped=[["19", "series_info"]]),
    F("net7-referent-type-preserved", "net_regression", "15",
      "ReplaceApproxLength overwrote ReferentType from the sheet. Rule 15 replaces the "
      "flagged length and keeps ReferentType (Movie stays Movie at 100 minutes though the "
      "sheet says TV).", "rule 15 copying ReferentType",
      cur={"ApproximateLength": "PT1H30M", "RegistrantExtra": "AL:Pro;"},
      sup={"ReferentType": "TV"},
      changed=True, changes=[["15", "approximate_length", "replace", "PT1H30M", "PT1H40M",
                              "pt1h40m"],
                             ["15", "registrant_extra:al", "remove", "AL:Pro;", None, "pro"]],
      merged=[["BaseObjectData/ReferentType", "Movie"]]),
    F("net8-status-not-forced-valid", "net_regression", "14",
      "SetPublicationStatus ignored the supplied value and forced 'in development' to "
      "'valid'. Rule 14 is skipped: the Status is untouched.", "rule 14 forcing valid",
      cur={"Status": "in development"}, sup={"Status": "valid"},
      changed=False, skipped=[["14", "status"]]),
    F("net9-insertion-in-schema-order", "net_regression", "3",
      "Every .NET insertion was '// TODO: ensure location correct'. Additions to the middle "
      "of BaseObjectData (an alternate title, a country, an Alt ID, a director, a "
      "description) land in the schema's content-model order.", "insertion by append",
      cur={"AlternateID": [IMDB], "Credits": {"Actor": [{"DisplayName": "Ann Lee"}]}},
      sup={"AlternateResourceName": [{"Title": "Un film d'exemple", "_lang": "fr"}],
           "CountryOfOrigin": ["US", "FR"], "AlternateID": [IMDB, TMDB],
           "Credits": {"Director": [{"DisplayName": "Jane Doe"}]},
           "Description": {"Description": "A film.", "_lang": "en"}},
      changed=True, order=True,
      changes=[["3", "title:alternate", "add", None, "Un film d'exemple", "un film d'exemple"],
               ["8", "country_of_origin", "add", None, "FR", "fr"],
               ["12", "director", "add", None, "Jane Doe", "jane doe"],
               ["16", "description:en", "add", None, "A film.", "a film."],
               ["18", "alt_id:proprietary|themoviedb.org/movie", "add", None, "603", "603"]]),
    # ------------------------------------------------------------------ rule 18
    F("altid-null-relation-reads-is-same-as", "rule_18", "18",
      "18.2: the record's Alt ID without a relation (NULL) and a supplied IsSameAs are one "
      "relation: present, silent.", "same_relation treating NULL as its own relation",
      cur={"AlternateID": [IMDB]}, sup={"AlternateID": [dict(IMDB, Relation="IsSameAs")]},
      changed=False),
    F("altid-empty-relation-reads-is-same-as", "rule_18", "18",
      "18.2: relation=\"\" (the mirror's pre-2026-09-23 spelling) is IsSameAs.",
      "same_relation treating '' as its own relation",
      cur={"AlternateID": [IMDB]}, sup={"AlternateID": [dict(IMDB, Relation="IsSameAs")]},
      patch=('xsi:type="IMDB">', 'relation="" xsi:type="IMDB">'), changed=False),
    F("altid-blank-relation-reads-is-same-as", "rule_18", "18",
      "18.2: a whitespace-only relation is blank, so IsSameAs.",
      "same_relation not stripping",
      cur={"AlternateID": [IMDB]}, sup={"AlternateID": [dict(IMDB, Relation="IsSameAs")]},
      patch=('xsi:type="IMDB">', 'relation=" " xsi:type="IMDB">'), changed=False),
    F("altid-relation-conflict-others-still-written", "rule_18", "18",
      "18.4: a present value under a different relation is a conflict, never written, and "
      "the row's other Alt IDs still go.", "rule 18 withholding the whole row",
      cur={"AlternateID": [IMDB]},
      sup={"AlternateID": [dict(IMDB, Relation="Deprecated"), TMDB]},
      changed=True, conflicts=[["18", "alt_id:imdb|", "ALT_ID_RELATION_CONFLICT"]],
      changes=[["18", "alt_id:proprietary|themoviedb.org/movie", "add", None, "603", "603"]]),
    F("altid-same-kind-withheld-on-ordinary-kind", "rule_18", "18",
      "18.5: a second IsSameAs value of a single-form Kind the record already claims is "
      "withheld as SAME_KIND_CONFLICT.", "rule 6 not applied",
      cur={"AlternateID": [IMDB]}, sup={"AlternateID": [{"AltID": "tt0234215", "Type": "IMDB"}]},
      changed=False, conflicts=[["18", "alt_id:imdb|", "SAME_KIND_CONFLICT"]]),
    F("altid-same-kind-written-on-multi-form-kind", "rule_18", "18",
      "18.5: on a Kind multi_form_domains() declares (pbs.org) a second identity value is "
      "written.", "multi_form_domains ignored",
      cur={"AlternateID": [{"AltID": "A1", "Type": "Proprietary", "Domain": "pbs.org"}]},
      sup={"AlternateID": [{"AltID": "B2", "Type": "Proprietary", "Domain": "pbs.org"}]},
      changed=True, changes=[["18", "alt_id:proprietary|pbs.org", "add", None, "B2", "b2"]]),
    F("altid-two-relations-in-supplied-withheld", "rule_18", "18",
      "C5 2026-11-24: one value offered under two relations cannot be both; every copy is "
      "withheld.", "rule 18 writing the first copy",
      sup={"AlternateID": [TMDB, dict(TMDB, Relation="Deprecated")]},
      changed=False, conflicts=[["18", "alt_id:proprietary|themoviedb.org/movie",
                                 "ALT_ID_RELATION_CONFLICT"],
                                ["18", "alt_id:proprietary|themoviedb.org/movie",
                                 "ALT_ID_RELATION_CONFLICT"]]),
    F("altid-two-identity-values-in-supplied-withheld", "rule_18", "18",
      "Rule 6 on the supplied side: two identity values of one single-form Kind; at most one "
      "is right, so both are withheld.", "rule 6 applied only against the record",
      sup={"AlternateID": [{"AltID": "tt0133093", "Type": "IMDB"},
                           {"AltID": "tt0234215", "Type": "IMDB"}]},
      changed=False, conflicts=[["18", "alt_id:imdb|", "SAME_KIND_CONFLICT"],
                                ["18", "alt_id:imdb|", "SAME_KIND_CONFLICT"]]),
    F("altid-non-identity-never-conflicts", "rule_18", "18",
      "A value under a non-identity relation asserts no identity, so it never makes a rule-6 "
      "conflict (operator, 2026-11-24).", "rule 6 applied to every relation",
      cur={"AlternateID": [IMDB]},
      sup={"AlternateID": [{"AltID": "tt0234215", "Type": "IMDB", "Relation": "Deprecated"}]},
      changed=True, changes=[["18", "alt_id:imdb|", "add", None, "tt0234215", "tt0234215"]],
      altid_lines=[f"{ID}\tIMDB\ttt0234215\t\tDeprecated"]),
    F("altid-invalid-value-reported", "rule_18", "18",
      "18.7: a value failing its type's schema pattern is reported, not dropped silently and "
      "not written; the others go.", "rule 18.7 disabled",
      sup={"AlternateID": [{"AltID": "133093", "Type": "IMDB"}, TMDB]},
      changed=True, conflicts=[["18", "alt_id:imdb|", "ALT_ID_INVALID_VALUE"]],
      changes=[["18", "alt_id:proprietary|themoviedb.org/movie", "add", None, "603", "603"]]),
    F("altids-only-touches-nothing-else", "rule_18", "18",
      "--altids-only runs rule 18 alone: a new title, country and the pre-process duplicate "
      "director stay as they are.", "altids_only running other rules",
      options={"altids_only": True},
      cur={"Credits": {"Director": [{"DisplayName": "Jane Doe"}, {"DisplayName": "Jane Doe"}]}},
      sup={"AlternateResourceName": [{"Title": "Un film d'exemple", "_lang": "fr"}],
           "CountryOfOrigin": ["US", "FR"], "AlternateID": [TMDB]},
      changed=True, changes=[["18", "alt_id:proprietary|themoviedb.org/movie", "add", None,
                              "603", "603"]]),
    # ---------------------------------------------------------------- Pro flags
    F("pro-rd-rule4-shape-no-change", "pro_flags", "17",
      "Section 4: a supplied RD:Pro; year more than a year earlier (rule 4's shape). Rules 4-6 "
      "are held, so nothing touches the date; the flag is never copied. The held rule's own "
      "RD:Pro; guard is in the S3 dry run.", "rule 17 copying RD:Pro;",
      cur={"ReleaseDate": "2003"}, sup={"ReleaseDate": "2001", "RegistrantExtra": "RD:Pro;"},
      changed=False, skipped=[["17", "registrant_extra:rd"]]),
    F("pro-rd-rule5-shape-no-change", "pro_flags", "17",
      "Section 4: a supplied RD:Pro; full date against EIDR's year (rule 5's shape): no "
      "change, flag not copied.", "rule 17 copying RD:Pro;",
      cur={"ReleaseDate": "2001"}, sup={"ReleaseDate": "2001-05-04",
                                        "RegistrantExtra": "RD:Pro;"},
      changed=False, skipped=[["17", "registrant_extra:rd"]]),
    F("pro-rd-rule6-shape-no-change", "pro_flags", "17",
      "Section 4: a supplied RD:Pro; earlier full date (rule 6's shape): no change, flag not "
      "copied.", "rule 17 copying RD:Pro;",
      cur={"ReleaseDate": "2001-05-04"}, sup={"ReleaseDate": "2001-04-01",
                                              "RegistrantExtra": "RD:Pro;"},
      changed=False, skipped=[["17", "registrant_extra:rd"]]),
    F("pro-al-supplied-flagged-kept", "pro_flags", "15",
      "Section 4.1: a supplied AL:Pro; length never replaces EIDR's unflagged one.",
      "rule 15 ignoring the supplied flag",
      cur={"ApproximateLength": "PT1H30M"}, sup={"RegistrantExtra": "AL:Pro;"},
      changed=False, skipped=[["15", "approximate_length"], ["17", "registrant_extra:al"]]),
    F("pro-al-both-flagged-eidr-stays", "pro_flags", "15",
      "Section 4.1: both flagged; EIDR's value and its flag stay.",
      "rule 15 replacing on EIDR's flag alone",
      cur={"ApproximateLength": "PT1H30M", "RegistrantExtra": "AL:Pro;"},
      sup={"RegistrantExtra": "AL:Pro;"},
      changed=False, skipped=[["15", "approximate_length"], ["17", "registrant_extra:al"]]),
    F("pro-al-flagged-eidr-replaced", "pro_flags", "15",
      "Section 4.1: an unflagged supplied length replaces EIDR's AL:Pro; one, and the flag "
      "goes (RegistrantExtra emptied, so removed).", "rule 15 disabled",
      cur={"ApproximateLength": "PT1H30M", "RegistrantExtra": "AL:Pro;"},
      changed=True, changes=[["15", "approximate_length", "replace", "PT1H30M", "PT1H40M",
                              "pt1h40m"],
                             ["15", "registrant_extra:al", "remove", "AL:Pro;", None, "pro"]],
      merged=[["BaseObjectData/RegistrantExtra", None]]),
    F("pro-flags-not-copied-beside-rt", "pro_flags", "17",
      "Section 4.1: rule 17 copies RT:Podcast; and never RD:Pro; or AL:Pro;.",
      "rule 17 copying Pro flags",
      sup={"RegistrantExtra": "RD:Pro; AL:Pro; RT:Podcast;"},
      changed=True, skipped=[["17", "registrant_extra:rd"], ["17", "registrant_extra:al"]],
      changes=[["17", "registrant_extra:rt", "add", None, "RT:Podcast;", "podcast"]],
      merged=[["BaseObjectData/RegistrantExtra", "RT:Podcast;"]]),
    F("pro-inherited-length-counts-as-present", "pro_flags", "15",
      "Section 4.2: an Episode whose length is inherited (absent from its own block, present "
      "in FullMetadata) does not take the supplied length.",
      "rule 15 deciding presence on the self-defined block",
      shape=(EPISODE, EPISODE_X), sup={"ApproximateLength": "PT25M"},
      full={"ApproximateLength": "PT22M", "ReleaseDate": "2010-01-01"},
      changed=False, skipped=[["15", "approximate_length"]]),
    F("pro-parent-without-full-is-unknown", "pro_flags", "15",
      "Section 4.2: an Episode with no own length and no FullMetadata given cannot be judged; "
      "skipped with the reason, never added.", "rule 15 treating absent as none",
      shape=(EPISODE, EPISODE_X), sup={"ApproximateLength": "PT25M"},
      changed=False, skipped=[["15", "approximate_length"]]),
]


def _files(fx: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    cur_xml = record_to_xml(fx["current"])
    if fx["patch"]:
        old, new = fx["patch"]
        assert old in cur_xml, (fx["id"], old)
        cur_xml = cur_xml.replace(old, new, 1)
    out["current.xml"] = cur_xml + "\n"
    if fx["row"]:
        out["supplied_row.json"] = json.dumps(fx["row"], indent=1, ensure_ascii=False) + "\n"
    else:
        out["supplied.xml"] = record_to_xml(fx["supplied"]) + "\n"
    if fx["full"]:
        cur_bod = fx["current"]["SelfDefinedMetadata"]["BaseObjectData"]
        full_bod = _apply(cur_bod, fx["full"])
        extra = fx["current"]["SelfDefinedMetadata"].get("ExtraObjectMetadata")
        out["full.xml"] = record_to_xml(_record(full_bod, extra, "FullMetadata"),
                                        view="FullMetadata") + "\n"
    expected = {"id": fx["id"], "set": fx["set"], "rule": fx["rule"], "why": fx["why"],
                "mutation": fx["mutation"], "options": fx["options"],
                "invariants": fx["invariants"]}
    out["expected.json"] = json.dumps(expected, indent=1, ensure_ascii=False) + "\n"
    return out


def _all() -> dict[Path, str]:
    ids = [fx["id"] for fx in FIXTURES]
    assert len(ids) == len(set(ids)), "duplicate fixture id"
    files: dict[Path, str] = {}
    for fx in FIXTURES:
        for name, text in _files(fx).items():
            files[OUT / fx["set"] / fx["id"] / name] = text
    return files


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--write", action="store_true")
    g.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    files = _all()
    on_disk = {p for p in OUT.rglob("*") if p.is_file() and p.name != "README.md"} \
        if OUT.exists() else set()
    if args.check:
        bad = [str(p) for p, t in files.items()
               if not p.is_file() or p.read_text(encoding="utf-8") != t]
        bad += [str(p) for p in on_disk - set(files)]
        for b in bad:
            print(f"differs: {b}")
        return 1 if bad else 0
    for p in on_disk - set(files):
        p.unlink()
    for p, t in files.items():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(t.encode("utf-8"))
    print(f"wrote {len(FIXTURES)} fixtures under {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
