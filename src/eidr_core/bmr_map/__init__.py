"""Standard record <-> Template-22 BMR row mapping — THE shared implementation.

Extracted 2026-10-13 (register B5 / P5) from XML_to_JSON
``xml_to_json_exporter.py`` at content-sha1 ``4cda07af7ba7``:
``_bmr_rows_from_standard_records`` (record -> row) and
``build_standard_record_from_bmr_row`` with its ``_collect_*`` helpers
(row -> record). Second consumer: python-tools (``FlattenTool -f bmr`` and
the ``-bmrin`` readers). The six conditions XML_to_JSON set on 2026-09-23,
accepted by eidr-core on 2026-09-24, are the specification; each is named
where it applies below.

**What this module is.** Cell <-> field mechanism for ONE record and ONE row.
A "standard record" is the registry-shaped JSON XML_to_JSON emits
(``SelfDefinedMetadata`` / ``FullMetadata`` / ``ProvenanceMetadata`` blocks,
each with ``BaseObjectData`` and ``ExtraObjectMetadata``). A row is a dict
keyed by Template-22 column header, numbered families written as
``"<base> N"``.

**What it deliberately is not** (each has a home already, or is a ruling of
one consumer):

* Routing a creation type to a template: ``bmr_io.template_for_creation_type``
  (the caller passes the template key).
* Expanding families into columns, the per-family maximum, and reporting
  values that have no column: ``bmr_io.write_sheet`` (``SCHEMA_MAX``,
  ``WriteReport.dropped``). There is no second cap here: a second expansion
  or cap path is exactly what python-tools asked not to have (2026-09-23).
* ``Unique Row ID`` and echoing an unconvertible row verbatim: XML_to_JSON's
  operator rulings of 2026-09-03, kept with the caller (condition 1).
* ``Assigned EIDR ID`` / ``Registration Errors & Notes``: never written; the
  writer pops them (the registry's and the reviewer's columns).
* Parent resolution (``bmr_io.resolve_parent``) and Full-record construction
  (``inheritance.build_full_base``): the row -> record direction returns the
  SELF-defined record only (condition 5).
* ``DisplayName``: a display convention of the caller's output format, not a
  registry field; ``record_from_row`` leaves it out.

Stdlib only, plus ``bmr_io`` (for ``family_layout``) and ``inheritance``
(for ``is_absent``), so a vendoring consumer lists
``["bmr_map", "bmr_io", "inheritance"]``, which is closed under imports.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Mapping
from typing import Any

from eidr_core.bmr_io import family_layout
from eidr_core.inheritance import is_absent
from eidr_core.ordering import is_shortdoi

__all__ = ["SUPPORTED_TEMPLATES", "PRODUCED_BASES", "NEVER_PRODUCED", "header_base",
           "select_blocks", "administrators_of",
           "row_from_blocks", "row_from_record",
           "creation_type_from_row", "record_from_row", "record_from_xml"]

# Template keys are bmr_io.TEMPLATES keys. Compilation has a Template-22
# sheet, but this mapper cannot populate its Header/Entry structure, so it is
# refused rather than written as a half row (XML_to_JSON reported such
# records as not exportable since 2026-09-11; it keeps doing so).
SUPPORTED_TEMPLATES: tuple[str, ...] = (
    "non_episodic", "episodic", "edit", "manifestation", "clip")

# The reference implementation branched on group LABELS; the labels are kept
# internal so the public surface speaks only eidr-core's template keys.
_LABEL = {"non_episodic": "Non-Episodic", "episodic": "Episodic", "edit": "Edit",
          "manifestation": "Manifestation", "clip": "Clip"}

# Header BASES (the name without a trailing group number) this module can
# write, per template (condition 4). XML_to_JSON's fail-fast guardrail
# compares a template's columns against THIS declaration instead of a
# transcribed list. tests/test_bmr_map.py derives the actual set from a
# record that exercises every branch and asserts it equals this one, and
# that every column of each stock template is in it or in NEVER_PRODUCED,
# so the declaration cannot drift from the code or the templates. A base
# can be produced without being a column of that template (Clip carries no
# Alternate Title): the value then reaches write_sheet, which reports it as
# dropped, exactly as before the extraction.
_COMMON = frozenset({
    "Structural Type", "Mode", "Referent Type",
    "Title", "Title Class", "Title Language",
    "Alternate Title", "Alt Title Class", "Alt Title Language",
    "Associated Org", "Associated Org Role", "Associated Org Party ID",
    "Release Date", "Country of Origin", "Publication Status", "Approx Length",
    "Alt ID", "Domain", "Relation", "IMDb", "IMDb Relation",
    "Registrant", "Metadata Authority Party ID",
    "Director", "Actor", "Registrant Extra", "Description", "Description Language",
    # Read from Series/Season/EpisodeInfo whatever the template, as the
    # reference does; on a non-episodic template they only appear when the
    # record carries an episodic info block, and write_sheet drops them.
    "Time Slot", "Series Class", "Season Class", "Episode Class",
    "Number Required", "Date Required", "Original Title Required",
    "Season No.", "Episode No.",
})
_ISAN = frozenset({"ISAN", "ISAN Relation"})
_EPISODIC = frozenset({
    "Parent EIDR/Row ID", "End Date",
    "Distribution No.", "Dist. No. Domain", "House No.", "House No. Domain",
    "Alternate No.", "Alt. No. Domain",
})
_MODE = frozenset({"Language Mode"})
# Each tab carries ONE language family (0.56.0, BMR-Review's T20 finding):
# Original Language on the Abstraction templates, Version Language on Edit
# and Manifestation, none on Clip. Before 0.56.0 both were written whatever
# the template, so every Edit built from `full` carried its inherited
# Original Language into a column the tab does not have, and write_sheet
# dropped and reported it (272 values on BMR-Review's 271 audit Edit rows).
_ORIGINAL = frozenset({"Original Language"})
_VERSION = frozenset({"Version Language"})
PRODUCED_BASES: dict[str, frozenset[str]] = {
    "non_episodic": _COMMON | _ISAN | _MODE | _ORIGINAL,
    "episodic": _COMMON | _ISAN | _EPISODIC | _MODE | _ORIGINAL,
    "edit": _COMMON | _ISAN | _MODE | _VERSION | frozenset({
        "Parent EIDR/Row ID", "Edit Use", "Edit Class", "Made for Region",
        "Color Type", "In 3D", "Edit Details", "Edit Details Domain"}),
    "manifestation": _COMMON | _ISAN | _MODE | _VERSION | frozenset({
        "Parent EIDR/Row ID", "Made for Region", "Manif Class",
        "Operator's Notes", "Manif Details", "Manif Details Domain"}),
    "clip": _COMMON | frozenset({
        "V-ISAN", "V-ISAN Relation", "Parent EIDR/Row ID", "Start Time",
        "Content Duration", "Component Mode"}),
}

# Template columns this module never writes, each for a stated reason, so a
# consumer's guardrail can check "every column of the template is either
# produced or deliberately not" without keeping its own list:
#   Unique Row ID                -- the caller's (XML_to_JSON ruling, 2026-09-03)
#   Assigned EIDR ID,
#   Registration Errors & Notes  -- the registry's and the reviewer's
#   Metadata Authority           -- the display NAME; only the Party ID column
#                                   is written (a name is not an ID)
#   Operator's Notes             -- written on Manifestation only (Digital XML)
# A base can appear in PRODUCED_BASES and on a template's list here only for
# Operator's Notes, which is produced for manifestation alone.
NEVER_PRODUCED: frozenset[str] = frozenset({
    "Unique Row ID", "Assigned EIDR ID", "Registration Errors & Notes",
    "Metadata Authority", "Operator's Notes"})

# Every Template-22 tab has ONE "Language Mode" family, and it belongs to the
# one language family that tab carries (XML_to_JSON, 2026-10-14): Original
# Language on the Abstraction templates, Version Language on Edit and
# Manifestation; Clip carries no language column. Until 0.51.0 both language
# loops wrote "Language Mode N", so on an Edit or Manifestation sheet built
# from `full` the parent's inherited Original Language mode landed beside the
# Edit's Version Language (398 of 400 rows in one delivered sheet), and the
# row -> record direction never read the column at all.
_LANGUAGE_FAMILY: dict[str, str] = {
    "non_episodic": "Original Language", "episodic": "Original Language",
    "compilation": "Original Language",
    "edit": "Version Language", "manifestation": "Version Language",
}

_GROUP_SUFFIX = re.compile(r"\s+\d+$")


def header_base(header: str) -> str:
    """``"Alt ID 3"`` -> ``"Alt ID"``; a header without a group number is its own base."""
    return _GROUP_SUFFIX.sub("", header)


def _template_label(template: str) -> str:
    try:
        return _LABEL[template]
    except KeyError:
        raise ValueError(
            f"bmr_map cannot write template {template!r}; supported: "
            f"{', '.join(SUPPORTED_TEMPLATES)}") from None


# --------------------------------------------------------------------------
# Small helpers. Both are carried over verbatim from the reference: their
# exact answers are what the rows contain.
# --------------------------------------------------------------------------

def _text(v: Any) -> str | None:
    """A cell's text: None for None or blank, else stripped ``str``."""
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip()
        return s if s != "" else None
    return str(v).strip()


def _bool_text(v: Any) -> str | None:
    """``"true"``/``"false"`` for recognised spellings; anything else verbatim."""
    if v is None:
        return None
    if isinstance(v, bool):
        return "true" if v else "false"
    s = str(v).strip().lower()
    if s in ("true", "t", "1", "yes", "y"):
        return "true"
    if s in ("false", "f", "0", "no", "n"):
        return "false"
    return str(v)


def _as_list(v: Any, scalar: tuple[type, ...]) -> list:
    """The reference's tolerance: a scalar (of the given types) is one entry."""
    if not v:
        return []
    return [v] if isinstance(v, scalar) else list(v)


def _single_line_xml(xml_text: str) -> str:
    s = (xml_text or "").strip()
    if not s:
        return s
    s = re.sub(r">\s+<", "><", s)
    return re.sub(r"\s+", " ", s).strip()


# --------------------------------------------------------------------------
# Record -> row
# --------------------------------------------------------------------------

def select_blocks(record: Mapping[str, Any], source: str = "self",
                  ) -> tuple[dict, dict]:
    """The ``(BaseObjectData, ExtraObjectMetadata)`` pair a sheet is built from.

    ``"self"`` (the documented default): ``SelfDefinedMetadata`` only, so a
    value the record does not define itself is left EMPTY on the sheet.
    ``"full"``: ``FullMetadata``, falling back to ``SelfDefinedMetadata`` when
    the record has no Full block (so a Self-only record never maps to an empty
    row). Selection is the caller's choice (condition 2); this is the rule
    XML_to_JSON's ``--sheet-out-type`` applies, offered so a second caller
    does not rewrite it.
    """
    if source == "full":
        md = record.get("FullMetadata") or record.get("SelfDefinedMetadata") or {}
    elif source == "self":
        md = record.get("SelfDefinedMetadata") or {}
    else:
        raise ValueError(f"source must be 'self' or 'full', not {source!r}")
    base = (md.get("BaseObjectData") if isinstance(md, Mapping) else None) or {}
    extra = (md.get("ExtraObjectMetadata") if isinstance(md, Mapping) else None) or {}
    return base, extra


def administrators_of(record: Mapping[str, Any], base: Mapping[str, Any]) -> dict:
    """Registrant and Metadata Authority, from where this record carries them.

    A mirror-exported record has ``ProvenanceMetadata.Administrators`` (the
    full Metadata Authority list, whatever block is selected); a record built
    from a BMR row has no ProvenanceMetadata and carries them only in its
    block's ``BaseObjectData.Administrators``. Provenance first, then the
    block. Until 2026-10-02 the reference read Provenance only, so every
    sheet-built row lost both on the way back out (XML_to_JSON, 24 of 24 real
    rows).
    """
    return dict((record.get("ProvenanceMetadata") or {}).get("Administrators")
                or base.get("Administrators") or {})


def row_from_blocks(base: Mapping[str, Any], extra: Mapping[str, Any], template: str,
                    *, administrators: Mapping[str, Any] | None = None,
                    system_titles: str = "keep",
                    ) -> dict[str, str | None]:
    """Map one record's selected blocks to one Template-22 row.

    The caller has routed the record to ``template`` and selected the blocks
    (``select_blocks``). ``administrators`` supplies Registrant and Metadata
    Authority; when omitted, ``base["Administrators"]`` is used, so a record
    built from a sheet never silently loses them. A caller holding a whole
    record passes ``administrators_of(record, base)``, or uses
    ``row_from_record``, which does exactly that.

    The documented defaults (condition 3), each the reference's behaviour:

    * Alt IDs: the sheet Domain is the ID's ``Domain`` if present, else its
      ``Type``. ``IMDB`` goes to ``IMDb`` / ``IMDb Relation``; ``ISAN`` to
      ``ISAN`` / ``ISAN Relation``, except on the Clip template, where it is
      ``V-ISAN`` / ``V-ISAN Relation``; everything else to ``Alt ID N`` /
      ``Domain N`` / ``Relation N`` in record order, uncapped (``write_sheet``
      caps and reports). A ShortDOI is never written (0.58.0): the registry
      issues it, so it is not part of a submission.
    * Titles: ``ResourceName`` entry 0 is ``Title`` / ``Title Class`` /
      ``Title Language``; the rest are ``Alternate Title N`` and companions in
      record order (no re-sort on this path). ``system_titles="drop"``
      (0.56.0) leaves ``Title`` / ``Title Class`` / ``Title Language`` empty
      when that main title is the registry's own (``SystemGenerated`` true),
      for a sheet that may be registered: a sheet cannot mark a title as
      system-generated, so registering it would make the title user-supplied
      and stop the registry regenerating it (inheritance rule 2). The next
      title is NOT promoted into ``Title``. The default, ``"keep"``, writes it.
    * Metadata Authority: written ONLY to ``Metadata Authority Party ID N``,
      never to the display-name column.
    * Credits: ``Director N`` / ``Actor N`` from ``DisplayName``, then
      ``Name``, then ``value``.
    * Episodic: ``Parent EIDR/Row ID`` from EpisodeInfo over SeasonInfo over
      SeriesInfo; ``End Date`` Series then Season; ``Time Slot`` and the three
      ``* Required`` flags first found Episode -> Season -> Series.
    * Manifestation ``Digital`` XML goes to ``Operator's Notes`` as single-line
      XML, the only template that writes that column.
    * ``Language Mode N`` comes only from the template's own language family
      (Original Language on the Abstraction templates, Version Language on
      Edit and Manifestation, none on Clip); since 0.51.0, not from the reference.
      Since 0.56.0 the languages themselves follow the same rule: the other
      family has no column on the tab, so it is not produced.

    Values are text (``None`` for absent); keys a template does not carry are
    never produced (``PRODUCED_BASES``).
    """
    if system_titles not in ("keep", "drop"):
        raise ValueError(f"system_titles must be 'keep' or 'drop', not {system_titles!r}")
    group = _template_label(template)
    admins = dict(administrators) if administrators is not None else \
        dict(base.get("Administrators") or {})
    row: dict[str, str | None] = {}

    row["Structural Type"] = _text(base.get("StructuralType"))
    row["Mode"] = _text(base.get("Mode"))
    row["Referent Type"] = _text(base.get("ReferentType"))

    titles = base.get("ResourceName") or []
    if isinstance(titles, dict):
        titles = [titles]
    main: tuple[str | None, str | None, str | None] | None = None
    main_generated = False
    alt_titles: list[tuple[str | None, str | None, str | None]] = []
    for t in titles:
        if not isinstance(t, dict):
            continue
        entry = (_text(t.get("Title")) or _text(t.get("value")),
                 _text(t.get("TitleClass")) or _text(t.get("_titleClass")),
                 _text(t.get("_lang")))
        # Entry 0 is the main title, except that an entry with no title text
        # is passed over (its class and language with it) until one has text;
        # this is the reference's rule, kept because rows depend on it.
        if main is None or main[0] is None:
            main = entry
            main_generated = str(t.get("SystemGenerated")).strip().lower() == "true"
        else:
            alt_titles.append(entry)
    if system_titles == "drop" and main_generated:
        # Withheld AFTER choosing the main title, so the next title (an
        # alternate) is not promoted into Title (BMR-Review measured that
        # trap on 2 of 681 records).
        main = None
    if main is not None and main[0] is not None:
        row["Title"] = main[0]
    if main is not None and main[1] is not None:
        row["Title Class"] = main[1]
    if main is not None and main[2] is not None:
        row["Title Language"] = main[2]

    series_info = extra.get("SeriesInfo") if isinstance(extra, Mapping) else None
    season_info = extra.get("SeasonInfo") if isinstance(extra, Mapping) else None
    episode_info = extra.get("EpisodeInfo") if isinstance(extra, Mapping) else None

    for info in (episode_info, season_info, series_info):
        if isinstance(info, dict) and info.get("TimeSlot") is not None:
            row["Time Slot"] = _text(info.get("TimeSlot"))
            break
    if isinstance(series_info, dict) and series_info.get("SeriesClass") is not None:
        row["Series Class"] = _text(series_info.get("SeriesClass"))
    for family, info, key in (("Season Class", season_info, "SeasonClass"),
                              ("Episode Class", episode_info, "EpisodeClass")):
        values = info.get(key) if isinstance(info, dict) else None
        for i, v in enumerate(_as_list(values, (str, int, float, dict)), start=1):
            row[f"{family} {i}"] = (_text(v.get("Class")) or _text(v.get("value"))
                                    if isinstance(v, dict) else _text(v))

    flags: dict[str, Any] = {}
    for info in (episode_info, season_info, series_info):
        if isinstance(info, dict):
            for key in ("NumberRequired", "DateRequired", "OriginalTitleRequired"):
                if key not in flags and info.get(key) is not None:
                    flags[key] = info.get(key)
    for key, header in (("NumberRequired", "Number Required"),
                        ("DateRequired", "Date Required"),
                        ("OriginalTitleRequired", "Original Title Required")):
        if key in flags:
            row[header] = _bool_text(_text(flags[key]))

    if isinstance(season_info, dict) and season_info.get("SequenceNumber") is not None:
        row["Season No."] = _text(season_info.get("SequenceNumber"))
    if isinstance(episode_info, dict) and episode_info.get("SequenceNumber") is not None:
        row["Episode No."] = _text(episode_info.get("SequenceNumber"))

    for i, (tv, tc, tl) in enumerate(alt_titles, start=1):
        if tv is not None:
            row[f"Alternate Title {i}"] = tv
        if tc is not None:
            row[f"Alt Title Class {i}"] = tc
        if tl is not None:
            row[f"Alt Title Language {i}"] = tl

    # Only the template's OWN language family is written, with its "Language
    # Mode N" (_LANGUAGE_FAMILY); the other family has no column on the tab.
    own = _LANGUAGE_FAMILY.get(template)
    for family, key in (("Original Language", "OriginalLanguage"),
                        ("Version Language", "VersionLanguage")):
        if family != own:
            continue
        for i, v in enumerate(_as_list(base.get(key), (str, int, float)), start=1):
            if isinstance(v, dict):
                row[f"{family} {i}"] = _text(v.get("Language")) or _text(v.get("value"))
                if _text(v.get("_mode")):
                    row[f"Language Mode {i}"] = _text(v.get("_mode"))
            else:
                row[f"{family} {i}"] = _text(v)

    orgs = base.get("AssociatedOrg") or []
    if isinstance(orgs, dict):
        orgs = [orgs]
    for i, o in enumerate(orgs, start=1):
        if not isinstance(o, dict):
            continue
        row[f"Associated Org Party ID {i}"] = _text(o.get("_organizationID"))
        row[f"Associated Org Role {i}"] = _text(o.get("_role"))
        row[f"Associated Org {i}"] = _text(o.get("DisplayName"))

    row["Release Date"] = _text(base.get("ReleaseDate"))
    for i, v in enumerate(_as_list(base.get("CountryOfOrigin"), (str, int, float)), start=1):
        row[f"Country of Origin {i}"] = _text(v)
    row["Publication Status"] = _text(base.get("Status"))
    row["Approx Length"] = _text(base.get("ApproximateLength"))

    altids = base.get("AlternateID") or []
    if isinstance(altids, dict):
        altids = [altids]
    generic: list[tuple[str | None, str | None, str | None]] = []
    named: dict[str, tuple[str | None, str | None]] = {}
    for a in altids:
        if not isinstance(a, dict):
            continue
        aid = _text(a.get("AltID")) or _text(a.get("value"))
        dom = _text(a.get("Domain")) or _text(a.get("_domain"))
        typ = _text(a.get("Type")) or _text(a.get("_type"))
        rel = _text(a.get("Relation")) or _text(a.get("_relation"))
        if is_shortdoi(typ, dom):
            # A ShortDOI is issued by the registry, never submitted, so a BMR
            # row does not carry one (0.58.0). record_from_xml keeps it, as
            # the export spec requires (normalized-record 4.2), so without
            # this every XML-built row put it in an Alt ID column: BMR-Review
            # dropped it as a caller step, and XML_to_JSON asked for the rule
            # here before its exporter stops omitting ShortDOI.
            continue
        dom_out = dom if dom else typ
        if dom_out == "IMDB":
            named["IMDb"] = (aid, rel)
        elif dom_out == "ISAN":
            named["V-ISAN" if group == "Clip" else "ISAN"] = (aid, rel)
        else:
            generic.append((aid, dom_out, rel))
    for i, (aid, dom_out, rel) in enumerate(generic, start=1):
        row[f"Alt ID {i}"] = aid
        row[f"Domain {i}"] = dom_out
        row[f"Relation {i}"] = rel
    for column, (aid, rel) in named.items():
        if aid:  # an ISAN/IMDb entry with no value writes neither column
            row[column] = aid
            row[f"{column} Relation"] = rel

    row["Registrant"] = _text(admins.get("Registrant"))
    for i, v in enumerate(_as_list(admins.get("MetadataAuthority"), (str, int, float)), start=1):
        row[f"Metadata Authority Party ID {i}"] = _text(v)

    credits = base.get("Credits") or {}
    for role in ("Director", "Actor"):
        people = credits.get(role) or []
        if isinstance(people, dict):
            people = [people]
        for i, c in enumerate(people, start=1):
            row[f"{role} {i}"] = (
                _text(c.get("DisplayName")) or _text(c.get("Name")) or _text(c.get("value"))
                if isinstance(c, dict) else _text(c))

    row["Registrant Extra"] = _text(base.get("RegistrantExtra"))
    desc = base.get("Description") or {}
    if isinstance(desc, dict):
        row["Description"] = _text(desc.get("Description")) or _text(desc.get("value"))
        if _text(desc.get("_lang")):
            row["Description Language"] = _text(desc.get("_lang"))

    if group == "Episodic":
        _episodic_tail(row, extra)
    elif group == "Edit":
        _edit_tail(row, extra.get("EditInfo"))
    elif group == "Manifestation":
        _manifestation_tail(row, extra.get("ManifestationInfo"))
    elif group == "Clip":
        ci = extra.get("ClipInfo")
        if isinstance(ci, dict):
            row["Parent EIDR/Row ID"] = _text(ci.get("Parent"))
            row["Start Time"] = _text(ci.get("Start"))
            row["Content Duration"] = _text(ci.get("Duration"))
            row["Component Mode"] = _text(ci.get("ComponentsMode"))
    return row


def _episodic_tail(row: dict, extra: Mapping[str, Any]) -> None:
    parent = None
    for key in ("SeriesInfo", "SeasonInfo", "EpisodeInfo"):  # last non-empty wins
        info = extra.get(key)
        if isinstance(info, dict):
            parent = _text(info.get("Parent")) or parent
    if parent:
        row["Parent EIDR/Row ID"] = parent
    end_date = None
    if isinstance(extra.get("SeriesInfo"), dict):
        end_date = _text(extra["SeriesInfo"].get("EndDate"))
    if isinstance(extra.get("SeasonInfo"), dict):
        end_date = end_date or _text(extra["SeasonInfo"].get("EndDate"))
    if end_date:
        row["End Date"] = end_date
    seq = extra["EpisodeInfo"].get("SequenceInfo") \
        if isinstance(extra.get("EpisodeInfo"), dict) else None
    if not isinstance(seq, dict):
        return
    for key, number, domain in (("DistributionNumber", "Distribution No.", "Dist. No. Domain"),
                                ("HouseSequence", "House No.", "House No. Domain")):
        val = seq.get(key)
        if isinstance(val, dict):
            row[number] = _text(val.get("Number"))
            row[domain] = _text(val.get("Domain"))
    alt_nums = seq.get("AlternateNumber") or []
    if isinstance(alt_nums, dict):
        alt_nums = [alt_nums]
    for i, a in enumerate(alt_nums, start=1):
        if isinstance(a, dict):
            row[f"Alternate No. {i}"] = _text(a.get("Number"))
            row[f"Alt. No. Domain {i}"] = _text(a.get("Domain"))


def _details(row: dict, info: Mapping[str, Any], family: str) -> None:
    details = info.get("Details") or []
    if isinstance(details, dict):
        details = [details]
    for i, d in enumerate(details, start=1):
        if isinstance(d, dict):
            row[f"{family} {i}"] = _text(d.get("Details")) or _text(d.get("value"))
            row[f"{family} Domain {i}"] = _text(d.get("Domain")) or _text(d.get("_domain"))


def _numbered(row: dict, family: str, values: Any) -> None:
    for i, v in enumerate(_as_list(values, (str, int, float)), start=1):
        row[f"{family} {i}"] = _text(v)


def _edit_tail(row: dict, ei: Any) -> None:
    if not isinstance(ei, dict):
        return
    row["Parent EIDR/Row ID"] = _text(ei.get("Parent"))
    row["Edit Use"] = _text(ei.get("EditUse"))
    _numbered(row, "Edit Class", ei.get("EditClass"))
    _numbered(row, "Made for Region", ei.get("MadeForRegion"))
    if _text(ei.get("ColorType")):
        row["Color Type"] = _text(ei.get("ColorType"))
    if _text(ei.get("ThreeD")) is not None:
        row["In 3D"] = _text(ei.get("ThreeD"))
    _details(row, ei, "Edit Details")


def _manifestation_tail(row: dict, mi: Any) -> None:
    if not isinstance(mi, dict):
        return
    row["Parent EIDR/Row ID"] = _text(mi.get("Parent"))
    _numbered(row, "Made for Region", mi.get("MadeForRegion"))
    _numbered(row, "Manif Class", mi.get("ManifestationClass"))
    digital = mi.get("Digital")
    if isinstance(digital, str) and digital.strip():
        row["Operator's Notes"] = _single_line_xml(digital)
    _details(row, mi, "Manif Details")


def row_from_record(record: Mapping[str, Any], template: str, *, source: str = "self",
                    administrators: Mapping[str, Any] | None = None,
                    system_titles: str = "keep",
                    ) -> dict[str, str | None]:
    """``row_from_blocks`` for a whole standard record, with the documented defaults.

    Selects the blocks by ``source`` (``select_blocks``) and, unless
    ``administrators`` is given, takes them from ``administrators_of``. This
    is exactly what XML_to_JSON's ``--sheet-out`` did per record, minus the
    two things that stay with its caller: the ``Unique Row ID`` column and
    the verbatim echo of an unconvertible row. ``system_titles`` is as for
    ``row_from_blocks``.
    """
    base, extra = select_blocks(record, source)
    admins = administrators if administrators is not None else administrators_of(record, base)
    return row_from_blocks(base, extra, template, administrators=admins,
                           system_titles=system_titles)


# --------------------------------------------------------------------------
# Row -> record
# --------------------------------------------------------------------------

def _prune(obj: Any) -> Any:
    """Drop absent values recursively; absence is ``inheritance.is_absent``.

    What a built record omits must agree with what inheritance treats as "the
    record does not provide a value", so the rule is the shared one.
    """
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            v2 = _prune(v)
            if not is_absent(v2):
                out[k] = v2
        return out
    if isinstance(obj, list):
        return [p for p in (_prune(x) for x in obj) if not is_absent(p)]
    return obj


def _groups(row: Mapping[str, Any], members: list[str]) -> list[dict[str, str | None]]:
    """A family's groups in the sheet's own group order, each as {member: text}.

    Built on ``bmr_io.family_layout`` (a bare header is group 1; a numbered
    one wins over it), so the pairing of companion columns is by the sheet's
    group index, never by dense position. Groups whose members are all blank
    are dropped.
    """
    by_text = {str(k): k for k in row}
    out = []
    for g in sorted(layout := family_layout(by_text, members)):
        vals = {m: _text(row.get(by_text[h])) for m, h in layout[g].items()}
        if any(v is not None for v in vals.values()):
            out.append(vals)
    return out


def _values(row: Mapping[str, Any], family: str) -> list[str]:
    return [v for g in _groups(row, [family]) if (v := g.get(family)) is not None]


def creation_type_from_row(template: str, row: Mapping[str, Any]) -> str:
    """The creation type a row of ``template`` describes.

    Episodic rows split on ``Referent Type`` (Series, Season, else Episode).
    An unknown template key RAISES: the reference's old ``return "Basic"``
    fallback is how every Episode became a Basic record on 2026-09-11.
    """
    if template == "non_episodic":
        return "Basic"
    if template == "episodic":
        rt = (_text(row.get("Referent Type")) or "").strip()
        return rt if rt in ("Series", "Season") else "Episode"
    fixed = {"edit": "Edit", "clip": "Clip", "manifestation": "Manifestation",
             "compilation": "Compilation"}
    if template in fixed:
        return fixed[template]
    raise ValueError(f"unknown Template-22 key {template!r}")


def _sequence_info(row: Mapping[str, Any]) -> dict | None:
    dist_no, dist_dom = _text(row.get("Distribution No.")), _text(row.get("Dist. No. Domain"))
    house_no, house_dom = _text(row.get("House No.")), _text(row.get("House No. Domain"))
    alt = [{"Number": g.get("Alternate No."), "Domain": g.get("Alt. No. Domain")}
           for g in _groups(row, ["Alternate No.", "Alt. No. Domain"])]
    obj = _prune({
        "DistributionNumber": ({"Number": dist_no, "Domain": dist_dom}
                               if dist_no or dist_dom else None),
        "HouseSequence": ({"Number": house_no, "Domain": house_dom}
                          if house_no or house_dom else None),
        "AlternateNumber": alt or None,
    })
    return obj or None


def _details_from_row(row: Mapping[str, Any], family: str) -> list[dict] | None:
    out = [{"Details": g.get(family), "_domain": g.get(f"{family} Domain")}
           for g in _groups(row, [family, f"{family} Domain"])]
    return out or None


def _extra_from_row(row: Mapping[str, Any], template: str, creation_type: str) -> dict | None:
    parent = _text(row.get("Parent EIDR/Row ID"))
    if template == "episodic":
        flags = {
            "NumberRequired": _bool_text(_text(row.get("Number Required"))),
            "DateRequired": _bool_text(_text(row.get("Date Required"))),
            "OriginalTitleRequired": _bool_text(_text(row.get("Original Title Required"))),
        }
        end_date = _text(row.get("End Date"))
        if creation_type == "Series":
            series = _prune({"EndDate": end_date, "SeriesClass": _text(row.get("Series Class")),
                             **flags})
            return {"SeriesInfo": series} if series else None
        if creation_type == "Season":
            season = _prune({"Parent": parent, "EndDate": end_date,
                             "SeasonClass": _values(row, "Season Class"), **flags,
                             "SequenceNumber": _text(row.get("Season No."))})
            return {"SeasonInfo": season} if season else None
        episode = _prune({"Parent": parent, "SequenceInfo": _sequence_info(row),
                          "EpisodeClass": _values(row, "Episode Class"),
                          "TimeSlot": _text(row.get("Time Slot"))})
        return {"EpisodeInfo": episode} if episode else None
    if template == "edit":
        obj = _prune({
            "Parent": parent, "EditUse": _text(row.get("Edit Use")),
            "EditClass": _values(row, "Edit Class"),
            "MadeForRegion": _values(row, "Made for Region"),
            "ColorType": _text(row.get("Color Type")),
            "ThreeD": _bool_text(_text(row.get("In 3D"))),
            "Details": _details_from_row(row, "Edit Details"),
        })
        return {"EditInfo": obj} if obj else None
    if template == "clip":
        obj = _prune({"Parent": parent, "ComponentsMode": _text(row.get("Component Mode")),
                      "Start": _text(row.get("Start Time")),
                      "Duration": _text(row.get("Content Duration"))})
        return {"ClipInfo": obj} if obj else None
    if template == "manifestation":
        obj = _prune({
            "Parent": parent, "ManifestationClass": _values(row, "Manif Class"),
            "MadeForRegion": _values(row, "Made for Region"),
            "Details": _details_from_row(row, "Manif Details"),
        })
        return {"ManifestationInfo": obj} if obj else None
    return None


def _casefold_set(values: Iterable[str]) -> list[str]:
    # The BMR-input canonical order: de-duplicated, case-insensitive sort, so
    # it matches the mirror-export path and BMR-Review's reproduction (register
    # Phase 0.2 / R2).
    return sorted(set(values), key=str.casefold)


def _languages(row: Mapping[str, Any], family: str, template: str) -> list[Any]:
    """A language family read back, with its mode when the template pairs one.

    For the template's own language family, ``Language Mode N`` is read with
    ``<family> N`` and the entry is ``{"value": lang, "_mode": mode}`` (the
    mirror export's shape); a language without a mode stays a plain string.
    Same canonical order as before: de-duplicated, case-insensitive by
    language, then by mode.
    """
    if family != _LANGUAGE_FAMILY.get(template):
        return _casefold_set(_values(row, family))
    pairs: set[tuple[str, str | None]] = {
        (lang, g.get("Language Mode"))
        for g in _groups(row, [family, "Language Mode"])
        if (lang := g.get(family)) is not None}
    return [{"value": lang, "_mode": mode} if mode else lang
            for lang, mode in sorted(pairs, key=lambda p: (p[0].casefold(), p[1] or ""))]


def record_from_row(row: Mapping[str, Any], template: str) -> dict:
    """The SELF-defined standard record one Template-22 row describes.

    Returns ``{"CreationType": ..., "SelfDefinedMetadata": {...}}`` with
    absent values pruned. Every family is read on ``bmr_io.family_layout``
    (a bare header is group 1; companion columns pair by the sheet's own
    group index). Metadata Authority comes from the ``Metadata Authority
    Party ID`` column only: the display-name column is never an ID.
    ``Language Mode N`` is read into the template's own language family as
    ``{"value": lang, "_mode": mode}`` (0.51.0). Every ``Edit Details`` /
    ``Manif Details`` group is read; the reference read group 1 only. The
    ``IMDb``, ``ISAN`` and ``V-ISAN`` columns come back as Alt IDs with
    Domain ``IMDB`` / ``ISAN``. ShortDOI rows are NOT filtered: whether a
    ShortDOI belongs in a registration is the caller's policy.

    Not done here (condition 5): resolving ``Parent EIDR/Row ID`` (use
    ``bmr_io.resolve_parent``), building the Full record (use
    ``inheritance.build_full_base``), and ``DisplayName``. Raises
    ``ValueError`` for an unknown template key.
    """
    creation_type = creation_type_from_row(template, row)
    titles = []
    if _text(row.get("Title")) is not None:
        titles.append({"Title": _text(row.get("Title")),
                       "TitleClass": _text(row.get("Title Class")),
                       "_lang": _text(row.get("Title Language")),
                       "SystemGenerated": "false"})
    for g in _groups(row, ["Alternate Title", "Alt Title Class", "Alt Title Language"]):
        if g.get("Alternate Title") is None:
            continue
        titles.append({"Title": g["Alternate Title"], "TitleClass": g.get("Alt Title Class"),
                       "_lang": g.get("Alt Title Language"), "SystemGenerated": "false"})
    orgs: list[dict[str, Any]] = [
            {"_idType": "EIDRPartyID" if g.get("Associated Org Party ID") else None,
             "_organizationID": g.get("Associated Org Party ID"),
             "_role": g.get("Associated Org Role"),
             "DisplayName": g.get("Associated Org"),
             "AlternateName": []}
            for g in _groups(row, ["Associated Org", "Associated Org Role",
                                   "Associated Org Party ID"])]
    alt_ids = [{"AltID": g.get("Alt ID"), "Domain": g.get("Domain"), "Relation": g.get("Relation")}
               for g in _groups(row, ["Alt ID", "Domain", "Relation"])]
    for column, domain in (("IMDb", "IMDB"), ("ISAN", "ISAN"), ("V-ISAN", "ISAN")):
        value = _text(row.get(column))
        if value:
            alt_ids.append({"AltID": value, "Domain": domain,
                            "Relation": _text(row.get(f"{column} Relation"))})
    description = _text(row.get("Description"))
    description_lang = _text(row.get("Description Language"))
    base = _prune({
        "StructuralType": _text(row.get("Structural Type")),
        "Mode": _text(row.get("Mode")),
        "ReferentType": _text(row.get("Referent Type")),
        "ResourceName": titles,
        "OriginalLanguage": _languages(row, "Original Language", template),
        "VersionLanguage": _languages(row, "Version Language", template),
        "AssociatedOrg": orgs,
        "ReleaseDate": _text(row.get("Release Date")),
        "CountryOfOrigin": _casefold_set(_values(row, "Country of Origin")),
        "Status": _text(row.get("Publication Status")),
        "ApproximateLength": _text(row.get("Approx Length")),
        "AlternateID": alt_ids,
        "Administrators": {"Registrant": _text(row.get("Registrant")),
                           "MetadataAuthority": _values(row, "Metadata Authority Party ID")},
        "Credits": {role: [{"DisplayName": n, "SortName": None} for n in _values(row, role)]
                    for role in ("Director", "Actor")},
        "RegistrantExtra": _text(row.get("Registrant Extra")),
        "Description": ({"Description": description, "_lang": description_lang}
                        if description or description_lang else None),
    })
    return _prune({
        "CreationType": creation_type,
        "SelfDefinedMetadata": {
            "_xmlns": "http://www.eidr.org/schema",
            "_xmlns:md": "http://www.movielabs.com/schema/md/v2.8/md",
            "_xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
            "BaseObjectData": base,
            "ExtraObjectMetadata": _extra_from_row(row, template, creation_type),
        },
    })


# --------------------------------------------------------------------------
# Registry XML -> standard record (0.52.0; BMR-Review T20, python-tools)
# --------------------------------------------------------------------------
#
# The "standard record" is the shape XML_to_JSON builds from the mirror; this
# builds the same shape from the registry's own XML, so a consumer holding XML
# (the API Shim's messages, a resolve result) can call row_from_record without
# a private reader. Stdlib ElementTree, so the module stays vendorable. The
# SDK's codec (eidr.codecs.xml) parses the same XML but yields the MovieLabs
# JSON encoding, which differs in about 40 paths (md:DisplayName, _xsi:type,
# list-valued Parent, EditDetails, md:DistributionNumber with value), so it is
# not a substitute for this shape.

def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _attr(el: ET.Element, name: str) -> str | None:
    """An attribute by local name (namespaced ones, such as xsi:type, arrive
    as '{uri}type')."""
    for k, v in el.attrib.items():
        if _local(k) == name:
            return v
    return None


def _kids(el: ET.Element, name: str) -> list[ET.Element]:
    return [c for c in el if _local(c.tag) == name]


def _kid_text(el: ET.Element, name: str) -> str | None:
    found = _kids(el, name)
    return found[0].text if found else None


def _language(el: ET.Element) -> Any:
    mode = _attr(el, "mode")
    return {"value": el.text, "_mode": mode} if mode else el.text


# Children that the schema repeats, so a single occurrence is still a list,
# as XML_to_JSON emits them.
_LIST_TAGS = {"SeasonClass", "EpisodeClass", "EditClass", "MadeForRegion",
              "ManifestationClass", "Entry", "Element"}
_DETAILS_TAGS = {"EditDetails", "ManifestationDetails", "Details"}
_LIGHTWEIGHT = {"AlternateContentInfo", "PackagingInfo", "PromotionInfo",
                "SupplementalContentInfo"}


def _number(el: ET.Element) -> dict:
    return {"Number": el.text, "Domain": _attr(el, "domain")}


def _generic(el: ET.Element) -> Any:
    """An element with no special rule: its text; or a dict of its children
    (a repeated or _LIST_TAGS child becomes a list) and attributes (as
    '_name'), with the text as 'value' when it has attributes too."""
    children = list(el)
    attrs = {f"_{_local(k)}": v for k, v in el.attrib.items()}
    if not children:
        if attrs:
            return {"value": el.text, **attrs} if el.text is not None else attrs
        return el.text
    out: dict[str, Any] = dict(attrs)
    for c in children:
        name = _local(c.tag)
        val = _generic(c)
        if name in out:
            if not isinstance(out[name], list):
                out[name] = [out[name]]
            out[name].append(val)
        else:
            out[name] = [val] if name in _LIST_TAGS else val
    return out


def _info(el: ET.Element) -> dict:
    """One ExtraObjectMetadata *Info block in the standard shape."""
    out: dict[str, Any] = {}
    for c in el:
        name = _local(c.tag)
        if name in _DETAILS_TAGS:
            out.setdefault("Details", []).append(
                {"Details": c.text, "Domain": _attr(c, "domain")})
        elif name == "SequenceInfo":
            seq: dict[str, Any] = {}
            for n in c:
                key = _local(n.tag)
                if key == "AlternateNumber":
                    seq.setdefault("AlternateNumber", []).append(_number(n))
                elif key in ("DistributionNumber", "HouseSequence"):
                    seq[key] = _number(n)
                else:
                    seq[key] = _generic(n)
            out["SequenceInfo"] = seq
        elif name == "Digital":
            # Carried as XML text, XML_to_JSON's shape; row_from_blocks
            # writes it to Operator's Notes on one line.
            out["Digital"] = ET.tostring(c, encoding="unicode")
        elif name in _LIST_TAGS:
            out.setdefault(name, []).append(_generic(c))
        elif name in out:
            if not isinstance(out[name], list):
                out[name] = [out[name]]
            out[name].append(_generic(c))
        else:
            out[name] = _generic(c)
    return out


def _base_from_xml(bod: ET.Element) -> dict:
    titles: list[dict] = []
    for t in _kids(bod, "ResourceName"):
        titles.append({"Title": t.text, "TitleClass": _attr(t, "titleClass"),
                       "_lang": _attr(t, "lang"),
                       "SystemGenerated": _attr(t, "systemGenerated")})
    for t in _kids(bod, "AlternateResourceName"):
        # XML_to_JSON marks every alternate SystemGenerated "false" (the
        # conversion table's note for alternates); kept, so both agree.
        titles.append({"Title": t.text, "TitleClass": _attr(t, "titleClass"),
                       "_lang": _attr(t, "lang"), "SystemGenerated": "false"})
    orgs = []
    for o in _kids(bod, "AssociatedOrg"):
        names = [n.text for n in _kids(o, "DisplayName") + _kids(o, "AlternateName") if n.text]
        orgs.append({"_idType": _attr(o, "idType"),
                     "_organizationID": _attr(o, "organizationID"),
                     "_role": _attr(o, "role"),
                     "DisplayName": names[0] if names else None,
                     "AlternateName": names[1:]})
    alt_ids = [{"AltID": a.text, "Type": _attr(a, "type"), "Domain": _attr(a, "domain"),
                "Relation": _attr(a, "relation")} for a in _kids(bod, "AlternateID")]
    admins: dict[str, Any] = {}
    for a_el in _kids(bod, "Administrators")[:1]:
        admins = {"Registrant": _kid_text(a_el, "Registrant"),
                  "MetadataAuthority": [m.text for m in _kids(a_el, "MetadataAuthority")]}
    credits: dict[str, list] = {}
    for c_el in _kids(bod, "Credits"):
        for role in ("Director", "Actor"):
            for person in _kids(c_el, role):
                credits.setdefault(role, []).append(
                    {"DisplayName": _kid_text(person, "DisplayName"),
                     "SortName": _kid_text(person, "SortName")})
    desc = _kids(bod, "Description")
    return {
        "ID": _kid_text(bod, "ID"),
        "StructuralType": _kid_text(bod, "StructuralType"),
        "Mode": _kid_text(bod, "Mode"),
        "ReferentType": _kid_text(bod, "ReferentType"),
        "ResourceName": titles,
        "OriginalLanguage": [_language(e) for e in _kids(bod, "OriginalLanguage")],
        "VersionLanguage": [_language(e) for e in _kids(bod, "VersionLanguage")],
        "AssociatedOrg": orgs,
        "ReleaseDate": _kid_text(bod, "ReleaseDate"),
        "CountryOfOrigin": [e.text for e in _kids(bod, "CountryOfOrigin")],
        "Status": _kid_text(bod, "Status"),
        "ApproximateLength": _kid_text(bod, "ApproximateLength"),
        "AlternateID": alt_ids,
        "Administrators": admins,
        "Credits": credits,
        "RegistrantExtra": _kid_text(bod, "RegistrantExtra"),
        "Description": ({"Description": desc[0].text, "_lang": _attr(desc[0], "lang")}
                        if desc else None),
    }


_BLOCKS = ("SelfDefinedMetadata", "FullMetadata")
_XMLNS = {"_xmlns": "http://www.eidr.org/schema",
          "_xmlns:md": "http://www.movielabs.com/schema/md/v2.8/md",
          "_xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance"}


def record_from_xml(xml: str | bytes | ET.Element) -> dict:
    """The standard record a piece of registry XML describes.

    ``xml`` is a ``SelfDefinedMetadata`` or ``FullMetadata`` element (a
    resolve result), or any element holding one or both (an API Shim
    ``Message``), as text, bytes or a parsed ElementTree element. Returns
    ``{"SelfDefinedMetadata": {...}, "FullMetadata": {...}}`` with whichever
    blocks the XML carries, each in the shape XML_to_JSON builds from the
    mirror, absent values pruned. Values are as the XML states them, not
    normalised (``PT2H0M`` stays ``PT2H0M``), and nothing is filtered:
    ShortDOI Alt IDs are kept, as the export spec requires (``row_from_blocks``
    leaves them out of a sheet row).
    No ``CreationType``, ``DisplayName`` or ``ProvenanceMetadata``: the
    blocks do not carry them, and routing is the caller's. Raises
    ``ValueError`` when the XML holds neither block.
    """
    root = xml if isinstance(xml, ET.Element) else ET.fromstring(xml)
    found: dict[str, ET.Element] = {}
    for el in root.iter():
        name = _local(el.tag)
        if name in _BLOCKS and name not in found:
            found[name] = el
    if not found:
        raise ValueError("no SelfDefinedMetadata or FullMetadata element in the XML")
    out: dict[str, Any] = {}
    for name in _BLOCKS:
        if name not in found:
            continue
        blk = found[name]
        bod = _kids(blk, "BaseObjectData")
        extra: dict[str, Any] = {}
        for eom in _kids(blk, "ExtraObjectMetadata")[:1]:
            for info in eom:
                key = _local(info.tag)
                if key in _LIGHTWEIGHT:
                    extra.setdefault(key, []).append(_generic(info))
                else:
                    extra[key] = _info(info)
        out[name] = {**_XMLNS, "BaseObjectData": _base_from_xml(bod[0]) if bod else None,
                     "ExtraObjectMetadata": extra or None}
    return _prune(out)
