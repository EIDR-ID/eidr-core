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

It also writes a standard record back to registry XML (``record_to_xml``,
the inverse of ``record_from_xml``), extracted from XML_to_JSON's
``standard_render`` for python-tools' ``-bmrin`` (2026-11-26).

Stdlib only, plus ``bmr_io`` (for ``family_layout``), ``inheritance`` (for
``is_absent``), ``ordering`` (for ``is_shortdoi``) and ``mddf_json`` (the
schema-ordered XML writer ``record_to_xml`` builds on). bmr_io imports
``ids``, so a vendoring consumer lists
``["bmr_map", "bmr_io", "inheritance", "ids", "ordering", "mddf_json"]``,
which is closed under imports (tests/test_vendor.py syncs exactly that).
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Mapping
from datetime import datetime, time
from functools import lru_cache
from typing import Any, cast

from eidr_core.bmr_io import family_layout
from eidr_core.inheritance import is_absent
from eidr_core.mddf_json import eidr_schema, json_to_xml, xml_to_json
from eidr_core.ordering import is_shortdoi

__all__ = ["SUPPORTED_TEMPLATES", "PRODUCED_BASES", "NEVER_PRODUCED", "header_base",
           "select_blocks", "administrators_of",
           "row_from_blocks", "row_from_record",
           "creation_type_from_row", "record_from_row", "record_from_xml",
           "record_to_xml", "RecordXmlError"]

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
    """A cell's text: None for None or blank, else stripped ``str``.

    A spreadsheet date cell arrives as a ``datetime`` (openpyxl has no
    date-only type), and ``str()`` gave ``2020-01-01 00:00:00``: not an
    xs:date, and it reached generated titles (``Show [2020-01-01 00:00:00]``)
    and XML output as such (found 2026-11-13, MDDF JSON step 3). A midnight
    datetime is the date; any other is the xs:dateTime spelling (``T``).
    """
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip()
        return s if s != "" else None
    if isinstance(v, datetime):
        return v.date().isoformat() if v.time() == time(0) else v.isoformat()
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


def _as_list(v: Any, scalar: tuple[type, ...]) -> list[Any]:
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

def _names_a_parent(md: Any) -> bool:
    """Does this block's ExtraObjectMetadata name a Parent? Parent is the only
    relationship the registry inherits through (Season, Episode, Edit, Clip,
    Manifestation); the lightweight relationships (lists) never carry one."""
    extra = (md.get("ExtraObjectMetadata") if isinstance(md, Mapping) else None) or {}
    return any(isinstance(info, Mapping) and not is_absent(info.get("Parent"))
               for info in extra.values())


def select_blocks(record: Mapping[str, Any], source: str = "self",
                  ) -> tuple[dict[str, Any], dict[str, Any]]:
    """The ``(BaseObjectData, ExtraObjectMetadata)`` pair a sheet is built from.

    ``SelfDefinedMetadata`` only, so a value the record does not define itself
    is left EMPTY on the sheet. The operator ruled on 2026-11-12 that
    inherited data never appears in BMR spreadsheet output, and on
    2026-11-13 that this holds for ALL BMR spreadsheet generation: a sheet
    cannot mark a value inherited, so registering it would make the value
    the record's own and stop it following the parent.

    ``source="full"`` (``FullMetadata``) was WITHDRAWN at 0.73.0 and raises
    ``ValueError``; the keyword stays so existing ``source="self"`` callers
    keep working.

    A record with no Self block but a Full block (a ``type=Full`` resolve
    result): the Full block is used when it names no Parent, because a record
    with no parent inherits nothing, so its Full and Self values are the same.
    When it names a Parent, inherited values cannot be told apart from the
    record's own, and this raises ``ValueError`` rather than guess. A record
    with neither block gives empty blocks, as before.
    """
    if source == "full":
        raise ValueError(
            "source='full' was withdrawn at eidr-core 0.73.0: BMR spreadsheet "
            "output never carries inherited data (operator rulings 2026-11-12 "
            "and 2026-11-13). Use source='self'.")
    if source != "self":
        raise ValueError(f"source must be 'self', not {source!r}")
    md = record.get("SelfDefinedMetadata") or {}
    if not md and record.get("FullMetadata"):
        full = record["FullMetadata"]
        if _names_a_parent(full):
            raise ValueError(
                "the record has no SelfDefinedMetadata and its FullMetadata names "
                "a Parent, so inherited values cannot be told apart from its own; "
                "supply the self-defined block (resolve with type=SelfDefined)")
        md = full
    base = (md.get("BaseObjectData") if isinstance(md, Mapping) else None) or {}
    extra = (md.get("ExtraObjectMetadata") if isinstance(md, Mapping) else None) or {}
    return base, extra


def administrators_of(record: Mapping[str, Any], base: Mapping[str, Any]) -> dict[str, Any]:
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
    (``select_blocks``). Pass self-defined blocks only: inherited data never
    belongs on a BMR sheet (operator, 2026-11-12 and 2026-11-13); this
    function maps whatever it is given and cannot check that for you.
    ``administrators`` supplies Registrant and Metadata Authority; when
    omitted, ``base["Administrators"]`` is used, so a record built from a
    sheet never silently loses them. A caller holding a whole
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
      ``Title Language``; ``AlternateResourceName`` (and, in the older
      one-list shape, ResourceName entries 1..n) are ``Alternate Title N`` and
      companions in record order (no re-sort on this path). An alternate is
      never promoted into ``Title`` (0.75.0). ``system_titles="drop"``
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
    alternates = base.get("AlternateResourceName") or []
    if isinstance(alternates, dict):
        alternates = [alternates]

    def _entry(t: Any) -> tuple[str | None, str | None, str | None] | None:
        # A title with no text writes no cells at all: its class and language
        # alone would be an empty element (operator, 2026-11-15), and they
        # vanish on the next round trip anyway.
        if isinstance(t, str):
            return (_text(t), None, None) if _text(t) else None
        if not isinstance(t, Mapping):
            return None
        text = _text(t.get("Title")) or _text(t.get("value"))
        if text is None:
            return None
        return (text, _text(t.get("TitleClass")) or _text(t.get("_titleClass")),
                _text(t.get("_lang")))

    # The main title is ResourceName entry 0 and nothing else. An alternate
    # is never promoted into Title: a record with only alternates leaves
    # Title empty (operator, 2026-11-15: "if the main title is missing, you do
    # not promote the Alternate"). Until 0.75.0 an entry with no text was
    # passed over until one had text, which promoted the first alternate.
    # Alternates are AlternateResourceName (0.75.0) plus, for a record in the
    # one-list shape some callers still build, ResourceName entries 1..n.
    # Entry 0 BEFORE any filtering: filtering first made entry 1 (an
    # alternate in the one-list shape) the main title when entry 0 was not a
    # dict.
    main = _entry(titles[0]) if titles else None
    main_generated = bool(titles) and isinstance(titles[0], Mapping) and \
        str(titles[0].get("SystemGenerated")).strip().lower() == "true"
    alt_titles = [e for e in (_entry(t) for t in list(titles[1:]) + list(alternates))
                  if e is not None]
    if system_titles == "drop" and main_generated:
        # The registry's own title is withheld; the alternates stay where
        # they are (BMR-Review measured the promotion trap on 2 of 681).
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


def _episodic_tail(row: dict[str, str | None], extra: Mapping[str, Any]) -> None:
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


def _details(row: dict[str, str | None], info: Mapping[str, Any], family: str) -> None:
    details = info.get("Details") or []
    if isinstance(details, dict):
        details = [details]
    for i, d in enumerate(details, start=1):
        if isinstance(d, dict):
            row[f"{family} {i}"] = _text(d.get("Details")) or _text(d.get("value"))
            row[f"{family} Domain {i}"] = _text(d.get("Domain")) or _text(d.get("_domain"))


def _numbered(row: dict[str, str | None], family: str, values: Any) -> None:
    for i, v in enumerate(_as_list(values, (str, int, float)), start=1):
        row[f"{family} {i}"] = _text(v)


def _edit_tail(row: dict[str, str | None], ei: Any) -> None:
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


def _manifestation_tail(row: dict[str, str | None], mi: Any) -> None:
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

    Selects the self-defined blocks (``select_blocks``; ``source="full"`` was
    withdrawn at 0.73.0 and raises) and, unless ``administrators`` is given,
    takes them from ``administrators_of``. This is exactly what XML_to_JSON's
    ``--sheet-out`` did per record, minus the two things that stay with its
    caller: the ``Unique Row ID`` column and
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


def _classes(row: Mapping[str, Any], family: str) -> list[str]:
    """A class or region family with repeats removed, first occurrence kept.

    EIDR allows no duplicate values (operator, 2026-11-15); the registry
    nevertheless holds ``Segment, Segment`` on 9 Episodes, and a sheet can
    repeat a value as easily, so the readers drop the repeat.
    """
    return list(dict.fromkeys(_values(row, family)))


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


def _sequence_info(row: Mapping[str, Any]) -> dict[str, Any] | None:
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


def _details_from_row(row: Mapping[str, Any], family: str) -> list[dict[str, Any]] | None:
    # A domain without details text would be an empty element, which EIDR
    # does not allow (operator, 2026-11-15), so such a group is not read.
    out = [{"Details": g.get(family), "_domain": g.get(f"{family} Domain")}
           for g in _groups(row, [family, f"{family} Domain"])
           if g.get(family) is not None]
    return out or None


def _extra_from_row(row: Mapping[str, Any], template: str,
                    creation_type: str) -> dict[str, Any] | None:
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
                             "SeasonClass": _classes(row, "Season Class"), **flags,
                             "SequenceNumber": _text(row.get("Season No."))})
            return {"SeasonInfo": season} if season else None
        episode = _prune({"Parent": parent, "SequenceInfo": _sequence_info(row),
                          "EpisodeClass": _classes(row, "Episode Class"),
                          "TimeSlot": _text(row.get("Time Slot"))})
        return {"EpisodeInfo": episode} if episode else None
    if template == "edit":
        obj = _prune({
            "Parent": parent, "EditUse": _text(row.get("Edit Use")),
            "EditClass": _classes(row, "Edit Class"),
            "MadeForRegion": _classes(row, "Made for Region"),
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
            "Parent": parent, "ManifestationClass": _classes(row, "Manif Class"),
            "MadeForRegion": _classes(row, "Made for Region"),
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


def record_from_row(row: Mapping[str, Any], template: str) -> dict[str, Any]:
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
                       "_lang": _text(row.get("Title Language"))})
    # No "SystemGenerated" key: a sheet cannot mark a title system-generated,
    # and an absent flag is left out rather than written "false" (operator,
    # 2026-11-13: empty or removed fields are gone from the output, never a
    # false or null placeholder). Until 0.71.0 every sheet title said "false".
    #
    # Alternates go to AlternateResourceName, never into the ResourceName
    # list (0.75.0). A child row may carry only an Alternate Title; it stays
    # an alternate and the main title is inherited or generated (operator,
    # 2026-11-15). In the one list, a blank Title put the first alternate at
    # entry 0, where every reader takes the main title from.
    alternates = []
    for g in _groups(row, ["Alternate Title", "Alt Title Class", "Alt Title Language"]):
        if g.get("Alternate Title") is None:
            continue
        alternates.append({"Title": g["Alternate Title"], "TitleClass": g.get("Alt Title Class"),
                           "_lang": g.get("Alt Title Language")})
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
        "AlternateResourceName": alternates,
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
        # Only with text: a Description that is only a language is an empty
        # element, which EIDR does not allow (operator, 2026-11-15).
        "Description": ({"Description": description, "_lang": description_lang}
                        if description else None),
    })
    # _prune is typed Any (it recurses over any JSON value); a dict in is a
    # dict out, which the cast states for the checker without a runtime test.
    return cast(dict[str, Any], _prune({
        "CreationType": creation_type,
        "SelfDefinedMetadata": {
            "_xmlns": "http://www.eidr.org/schema",
            "_xmlns:md": "http://www.movielabs.com/schema/md/v2.8/md",
            "_xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
            "BaseObjectData": base,
            "ExtraObjectMetadata": _extra_from_row(row, template, creation_type),
        },
    }))


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


def _languages_from_xml(bod: ET.Element, name: str) -> list[Any]:
    """A language family, one entry per (code, mode), in document order.

    The ``type`` attribute is not read: it is being deprecated and is not
    needed (operator, 2026-11-15). Without it, two entries that differed only
    by type are the same value, and EIDR allows no duplicate values; the
    registry holds 2,217 Full OriginalLanguage pairs of that kind (raw_records,
    2026-11-15). The same code with two modes (Audio and Visual) is two values
    and is kept: 5,404 registry records have one.
    """
    out: list[Any] = []
    for e in _kids(bod, name):
        lang = _language(e)
        if lang not in out:
            out.append(lang)
    return out


# Children that the schema repeats, so a single occurrence is still a list,
# as XML_to_JSON emits them.
_LIST_TAGS = {"SeasonClass", "EpisodeClass", "EditClass", "MadeForRegion",
              "ManifestationClass", "Entry", "Element"}
_DETAILS_TAGS = {"EditDetails", "ManifestationDetails", "Details"}
_LIGHTWEIGHT = {"AlternateContentInfo", "PackagingInfo", "PromotionInfo",
                "SupplementalContentInfo"}


def _number(el: ET.Element) -> dict[str, Any]:
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


def _info(el: ET.Element) -> dict[str, Any]:
    """One ExtraObjectMetadata *Info block in the standard shape."""
    out: dict[str, Any] = {}
    for c in el:
        name = _local(c.tag)
        if name in _DETAILS_TAGS:
            # An empty element (a domain and no text) is not allowed in EIDR
            # XML (operator, 2026-11-15), though the registry holds 1,363
            # ManifestationDetails and 162 EditDetails of that form
            # (raw_records, 2026-11-15). It carries no details, so it is not
            # read.
            if (c.text or "").strip():
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
            val = _generic(c)
            # No duplicate values (operator, 2026-11-15); the registry holds
            # EpisodeClass "Segment, Segment" on 9 Episodes.
            if val not in out.setdefault(name, []):
                out[name].append(val)
        elif name in out:
            if not isinstance(out[name], list):
                out[name] = [out[name]]
            out[name].append(_generic(c))
        else:
            out[name] = _generic(c)
    return out


def _base_from_xml(bod: ET.Element) -> dict[str, Any]:
    titles: list[dict[str, Any]] = []
    alternates: list[dict[str, Any]] = []
    for t in _kids(bod, "ResourceName"):
        if not (t.text or "").strip():
            continue     # an empty element is no title (operator, 2026-11-15)
        # SystemGenerated only when true: "false" (or an absent attribute) is
        # the absence of the flag, and absent fields are left out (operator,
        # 2026-11-13). XML_to_JSON's mirror path follows the same rule.
        generated = (_attr(t, "systemGenerated") or "").strip() in ("true", "1")
        titles.append({"Title": t.text, "TitleClass": _attr(t, "titleClass"),
                       "_lang": _attr(t, "lang"),
                       **({"SystemGenerated": "true"} if generated else {})})
    for t in _kids(bod, "AlternateResourceName"):
        if not (t.text or "").strip():
            continue     # an empty element is no title (operator, 2026-11-15)
        # The registry never generates an alternate (the mirror holds 0 of
        # 1,402,189 so marked), so there is no flag to carry. Until 0.71.0
        # this said "false", copying XML_to_JSON's old placeholder.
        #
        # Their own key (0.75.0), as in the XML: a SelfDefined block with only
        # an AlternateResourceName (2,711 in the mirror) would otherwise put
        # that alternate at ResourceName entry 0, where readers take the main
        # title from (operator, 2026-11-15: an alternate is never promoted).
        alternates.append({"Title": t.text, "TitleClass": _attr(t, "titleClass"),
                           "_lang": _attr(t, "lang")})
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
    credits: dict[str, list[dict[str, Any]]] = {}
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
        "AlternateResourceName": alternates,
        "OriginalLanguage": _languages_from_xml(bod, "OriginalLanguage"),
        "VersionLanguage": _languages_from_xml(bod, "VersionLanguage"),
        "AssociatedOrg": orgs,
        "ReleaseDate": _kid_text(bod, "ReleaseDate"),
        "CountryOfOrigin": [e.text for e in _kids(bod, "CountryOfOrigin")],
        "Status": _kid_text(bod, "Status"),
        "ApproximateLength": _kid_text(bod, "ApproximateLength"),
        "AlternateID": alt_ids,
        "Administrators": admins,
        "Credits": credits,
        "RegistrantExtra": _kid_text(bod, "RegistrantExtra"),
        # Only with text: <Description lang="en"/> is an empty element, not
        # allowed in EIDR XML (operator, 2026-11-15), though the registry
        # holds 1,351 (raw_records, 2026-11-15).
        "Description": ({"Description": desc[0].text, "_lang": _attr(desc[0], "lang")}
                        if desc and (desc[0].text or "").strip() else None),
    }


_BLOCKS = ("SelfDefinedMetadata", "FullMetadata")
_XMLNS = {"_xmlns": "http://www.eidr.org/schema",
          "_xmlns:md": "http://www.movielabs.com/schema/md/v2.8/md",
          "_xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance"}


def record_from_xml(xml: str | bytes | ET.Element) -> dict[str, Any]:
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
    return cast(dict[str, Any], _prune(out))  # a dict in is a dict out (see record_from_row)


# --------------------------------------------------------------------------
# Standard record -> registry XML (python-tools' -bmrin, handoff 2026-11-25)
# --------------------------------------------------------------------------
#
# EXTRACTED from XML_to_JSON ``standard_render.py`` (render_view_xml and the
# _base/_extra/_metadata/_provenance/_alias builders under it, read
# 2026-11-26 at XML_to_JSON a5b0949). eidr-core's 2026-11-13 plan kept that
# writer in XML_to_JSON until a second consumer needed it; python-tools'
# ``-bmrin`` (sheet row -> record_from_row -> registry submission) is that
# consumer. The extraction keeps the original's mapping and output, with the
# differences listed in record_to_xml's docstring, so XML_to_JSON can
# delegate to it.
#
# How: each view is first built as a practice-shaped dict (the names only:
# which record key is which element or attribute), then written by
# mddf_json.json_to_xml, which places every child in the EIDR 2.7.0 schema's
# content-model order. Element order is therefore the schema's by
# construction, never a list transcribed here.

class RecordXmlError(ValueError):
    """The record holds something ``record_to_xml`` has no element for.

    Raised rather than dropped: a key the mapping does not know would vanish
    from the XML without a trace, and a registration built from that XML
    would silently lose the value (python-tools' acceptance item 4, the same
    obligation ``WriteReport.dropped`` meets on the way out to a sheet). The
    message names the key and where it was found.
    """


# The concrete xsi:types of eidr:alternateIDType are the alternateIDTypeType
# enumeration of the bundled schema, less Proprietary (the only one that
# takes a domain). Read from the schema, never typed here: XML_to_JSON's
# hand-typed list once left out Ad-ID (review, 2026-11-13). Read lazily, so
# importing bmr_map does not parse an XSD.
@lru_cache(maxsize=1)
def _alt_id_types() -> frozenset[str]:
    hit = eidr_schema().types.get(f"{{{_XMLNS['_xmlns']}}}alternateIDTypeType")
    if hit is None:
        raise RuntimeError("alternateIDTypeType is not in the bundled EIDR schema")
    xs = "{http://www.w3.org/2001/XMLSchema}"
    names = {e.get("value") for e in hit[0].iter(f"{xs}enumeration")}
    return frozenset(n for n in names if n and n != "Proprietary")


# The four lightweight relationships: one element per relationship, its class
# element named after the info element.
_LIGHTWEIGHT_CLASS = {
    "AlternateContentInfo": "AlternateContentClass",
    "PackagingInfo": "PackagingClass",
    "PromotionInfo": "PromotionClass",
    "SupplementalContentInfo": "SupplementalContentClass",
}


def _xml_text(v: Any) -> str | None:
    """A value as XML text, or None when the record does not provide one.

    Absent is ``inheritance.is_absent`` (None, blank, empty containers), the
    rule record_from_row and record_from_xml prune with. Typed values (an
    int SequenceNumber from the mirror) are ``str``-ed; booleans are the
    schema's ``true``/``false``. Not stripped: the value is written as the
    record holds it, as in the original.
    """
    if is_absent(v):
        return None
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def _xml_list(v: Any) -> list[Any]:
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def _check_keys(where: str, obj: Mapping[str, Any], known: set[str] | frozenset[str]) -> None:
    extra = [k for k in obj if k not in known and not str(k).startswith("_xmlns")]
    if extra:
        raise RecordXmlError(f"{where}: no element for record key(s) {sorted(extra)}")


def _one_of(where: str, entry: Mapping[str, Any], *keys: str) -> Any:
    """The value under whichever spelling ``entry`` uses for one field.

    The record shapes spell some fields two ways (``Title`` or ``value``;
    ``_domain`` from record_from_row, ``Domain`` from record_from_xml). The
    original took the first and ignored the second; two spellings with
    DIFFERENT values would lose one silently, so that raises.
    """
    present = [k for k in keys if k in entry and not is_absent(entry[k])]
    values = {_xml_text(entry[k]) for k in present}
    if len(values) > 1:
        raise RecordXmlError(f"{where}: {present} disagree ({sorted(map(str, values))})")
    return entry[present[0]] if present else None


def _put(out: dict[str, Any], key: str, value: Any) -> None:
    # Absent values are not written (operator, 2026-11-13).
    if value is None or value == [] or value == {}:
        return
    out[key] = value


def _xml_texts(v: Any) -> list[str]:
    return [t for t in (_xml_text(x) for x in _xml_list(v)) if t is not None]


def _with_attrs(value: str | None, attrs: Mapping[str, str | None]) -> Any:
    """An element with text and attributes, attributes in the registry's order.

    The registry writes attributes alphabetically (``lang``,
    ``systemGenerated``, ``titleClass``), measured by XML_to_JSON on its
    2026-11-13 resolve corpus; the callers pass them in that order.

    An element with no text is not written, whatever its attributes: EIDR
    does not allow empty elements (operator, 2026-11-15), and both readers
    (record_from_row, record_from_xml) already treat ``<Description
    lang="en"/>`` or a domain without details as no value, so this is the
    shared policy, not a loss.
    """
    if value is None:
        return None
    present = {f"_{k}": a for k, a in attrs.items() if a is not None}
    return {"value": value, **present} if present else value


_TITLE_KEYS = frozenset({"Title", "value", "TitleClass", "_titleClass", "_lang",
                         "SystemGenerated", "_systemGenerated"})


def _xml_title(entry: Any, main: bool) -> Any:
    if not isinstance(entry, Mapping):
        return _xml_text(entry)
    where = "ResourceName entry" if main else "AlternateResourceName entry"
    _check_keys(where, entry, _TITLE_KEYS)
    flag = (_xml_text(_one_of(where, entry, "SystemGenerated", "_systemGenerated")) or "")
    flag = flag.strip().lower()
    if flag not in ("", "true", "1", "false", "0"):
        raise RecordXmlError(f"{where}: SystemGenerated {flag!r} is not a boolean")
    generated = flag in ("true", "1")
    if generated and not main:
        # The registry marks only the main title (the mirror holds 0 of
        # 1,402,189 alternates so marked); the original dropped the flag
        # here, which is a silent loss of a stated value.
        raise RecordXmlError(f"{where}: SystemGenerated true on an alternate title has no "
                             "place in EIDR XML")
    # Only "true" is a statement (operator, 2026-11-13: no "false"
    # placeholders).
    return _with_attrs(_xml_text(_one_of(where, entry, "Title", "value")), {
        "lang": _xml_text(entry.get("_lang")),
        "systemGenerated": "true" if generated else None,
        "titleClass": _xml_text(_one_of(where, entry, "TitleClass", "_titleClass")),
    })


def _xml_language(entry: Any) -> Any:
    if not isinstance(entry, Mapping):
        return _xml_text(entry)
    _check_keys("language entry", entry, {"value", "_mode", "_type"})
    return _with_attrs(_xml_text(entry.get("value")),
                       {"mode": _xml_text(entry.get("_mode")),
                        "type": _xml_text(entry.get("_type"))})


def _xml_org(entry: Any) -> dict[str, Any] | None:
    if not isinstance(entry, Mapping):
        raise RecordXmlError(f"AssociatedOrg entry is not an object: {entry!r}")
    _check_keys("AssociatedOrg entry", entry,
                {"_idType", "_organizationID", "_role", "DisplayName", "SortName",
                 "AlternateName"})
    out: dict[str, Any] = {}
    for a in ("_idType", "_organizationID", "_role"):
        _put(out, a, _xml_text(entry.get(a)))
    _put(out, "DisplayName", _xml_text(entry.get("DisplayName")))
    _put(out, "SortName", _xml_text(entry.get("SortName")))
    _put(out, "AlternateName", _xml_texts(entry.get("AlternateName")))
    return out or None


def _xml_alt_id(entry: Any) -> Any:
    if not isinstance(entry, Mapping):
        raise RecordXmlError(f"AlternateID entry is not an object: {entry!r}")
    _check_keys("AlternateID entry", entry, {"AltID", "Type", "Domain", "Relation"})
    value = _xml_text(entry.get("AltID"))
    typ, domain = _xml_text(entry.get("Type")), _xml_text(entry.get("Domain"))
    if typ is None:
        # The sheet shape (record_from_row) has no Type: row_from_blocks
        # writes `dom if dom else typ`, so a Domain naming one of the schema's
        # types IS the type, and any other Domain is a Proprietary domain.
        if domain in _alt_id_types():
            typ, domain = domain, None
        else:
            typ = "Proprietary"
    if typ != "Proprietary" and domain is not None:
        # Only Proprietary has a domain attribute in the schema. The original
        # dropped it here without a word.
        raise RecordXmlError(f"AlternateID {value!r}: Domain {domain!r} has no place on a "
                             f"{typ} ID (only Proprietary takes a domain)")
    return _with_attrs(value, {"domain": domain, "relation": _xml_text(entry.get("Relation")),
                               "xsi:type": typ})


def _xml_person(entry: Any) -> dict[str, Any] | None:
    if not isinstance(entry, Mapping):
        raise RecordXmlError(f"credit entry is not an object: {entry!r}")
    _check_keys("credit entry", entry, {"DisplayName", "SortName"})
    out: dict[str, Any] = {}
    _put(out, "DisplayName", _xml_text(entry.get("DisplayName")))
    _put(out, "SortName", _xml_text(entry.get("SortName")))
    if out and "DisplayName" not in out:
        # A credit without md:DisplayName is not a valid element, and the
        # original dropped its SortName silently.
        raise RecordXmlError(f"credit entry has a SortName but no DisplayName: {dict(entry)!r}")
    return out or None


_BASE_KEYS = frozenset({
    "ID", "StructuralType", "Mode", "ReferentType", "ResourceName", "AlternateResourceName",
    "OriginalLanguage", "VersionLanguage", "AssociatedOrg", "ReleaseDate", "CountryOfOrigin",
    "Status", "ApproximateLength", "AlternateID", "Administrators", "Credits",
    "RegistrantExtra", "Description"})


def _xml_administrators(adm: Mapping[str, Any]) -> dict[str, Any]:
    _check_keys("Administrators", adm, {"Registrant", "MetadataAuthority"})
    a: dict[str, Any] = {}
    _put(a, "Registrant", _xml_text(adm.get("Registrant")))
    _put(a, "MetadataAuthority", _xml_texts(adm.get("MetadataAuthority")))
    return a


def _xml_base(b: Mapping[str, Any]) -> dict[str, Any]:
    _check_keys("BaseObjectData", b, _BASE_KEYS)
    out: dict[str, Any] = {}
    for k in ("ID", "StructuralType", "Mode", "ReferentType"):
        _put(out, k, _xml_text(b.get(k)))
    # ResourceName is the main title, AlternateResourceName the alternates
    # (0.75.0); the older one-list shape (alternates as ResourceName entries
    # 1..n) is still read. Entry 0 is taken BEFORE any filtering, so an
    # alternate is never promoted (operator, 2026-11-15).
    titles = _xml_list(b.get("ResourceName"))
    alts = [_xml_title(t, main=False) for t in titles[1:] if t is not None] + [
        _xml_title(t, main=False) for t in _xml_list(b.get("AlternateResourceName"))]
    if titles and titles[0] is not None:
        _put(out, "ResourceName", _xml_title(titles[0], main=True))
    _put(out, "AlternateResourceName", [a for a in alts if a is not None])
    for k in ("OriginalLanguage", "VersionLanguage"):
        _put(out, k, [x for x in (_xml_language(e) for e in _xml_list(b.get(k)))
                      if x is not None])
    _put(out, "AssociatedOrg", [x for x in (_xml_org(e) for e in _xml_list(b.get("AssociatedOrg")))
                                if x is not None])
    _put(out, "ReleaseDate", _xml_text(b.get("ReleaseDate")))
    _put(out, "CountryOfOrigin", _xml_texts(b.get("CountryOfOrigin")))
    _put(out, "Status", _xml_text(b.get("Status")))
    _put(out, "ApproximateLength", _xml_text(b.get("ApproximateLength")))
    _put(out, "AlternateID", [x for x in (_xml_alt_id(e) for e in _xml_list(b.get("AlternateID")))
                              if x is not None])
    adm = b.get("Administrators")
    if isinstance(adm, Mapping):
        _put(out, "Administrators", _xml_administrators(adm))
    elif not is_absent(adm):
        raise RecordXmlError(f"Administrators is not an object: {adm!r}")
    cr = b.get("Credits")
    if isinstance(cr, Mapping):
        _check_keys("Credits", cr, {"Director", "Actor"})
        c: dict[str, Any] = {}
        for role in ("Director", "Actor"):
            _put(c, role, [x for x in (_xml_person(e) for e in _xml_list(cr.get(role)))
                           if x is not None])
        _put(out, "Credits", c)
    elif not is_absent(cr):
        raise RecordXmlError(f"Credits is not an object: {cr!r}")
    _put(out, "RegistrantExtra", _xml_text(b.get("RegistrantExtra")))
    d = b.get("Description")
    if isinstance(d, Mapping):
        _check_keys("Description", d, {"Description", "_lang", "value"})
        _put(out, "Description", _with_attrs(
            _xml_text(_one_of("Description", d, "Description", "value")),
            {"lang": _xml_text(d.get("_lang"))}))
    elif not is_absent(d):
        # Both record builders give {Description, _lang}; a bare string has
        # no lang, which the schema requires.
        raise RecordXmlError(f"Description is not an object: {d!r}")
    return out


def _xml_scalars(where: str, src: Mapping[str, Any], names: tuple[str, ...],
                 lists: tuple[str, ...] = ()) -> dict[str, Any]:
    _check_keys(where, src, set(names) | set(lists))
    out: dict[str, Any] = {}
    for k in names:
        _put(out, k, _xml_text(src.get(k)))
    for k in lists:
        _put(out, k, _xml_texts(src.get(k)))
    return out


def _xml_numbered(entry: Any) -> Any:
    if not isinstance(entry, Mapping):
        return _xml_text(entry)
    _check_keys("sequence number", entry, {"Number", "Domain"})
    return _with_attrs(_xml_text(entry.get("Number")), {"domain": _xml_text(entry.get("Domain"))})


def _xml_details(v: Any) -> list[Any]:
    out = []
    for e in _xml_list(v):
        if isinstance(e, Mapping):
            # record_from_row spells the domain "_domain", record_from_xml
            # "Domain"; both are read (the original knew only "_domain").
            _check_keys("Details entry", e, {"Details", "_domain", "Domain"})
            x = _with_attrs(_xml_text(e.get("Details")),
                            {"domain": _xml_text(_one_of("Details entry", e, "_domain", "Domain"))})
        else:
            x = _xml_text(e)
        if x is not None:
            out.append(x)
    return out


def _xml_digital(xml_block: Any) -> Any:
    """The stored Digital block (XML text) as practice JSON for json_to_xml.

    Parsed inside a FullMetadata wrapper so the schema knows every element
    (Digital is not a global element), with the block's own namespace
    declarations dropped: the view's root declares them, as the registry's
    document does.
    """
    text = _xml_text(xml_block)
    if text is None:
        return None
    body = text.strip()
    if body.startswith("<?xml"):
        body = body.split("?>", 1)[1]
    wrapped = (f'<FullMetadata xmlns="{_XMLNS["_xmlns"]}" xmlns:md="{_XMLNS["_xmlns:md"]}" '
               f'xmlns:xsi="{_XMLNS["_xmlns:xsi"]}"><ExtraObjectMetadata><ManifestationInfo>'
               f"{body}</ManifestationInfo></ExtraObjectMetadata></FullMetadata>")
    tree = xml_to_json(wrapped, strict=True)
    dig = tree["FullMetadata"]["ExtraObjectMetadata"]["ManifestationInfo"]["Digital"]
    if isinstance(dig, dict):
        dig = {k: v for k, v in dig.items() if not k.startswith("_xmlns")}
    return dig


_EXTRA_KEYS = frozenset({"SeriesInfo", "SeasonInfo", "EpisodeInfo", "EditInfo", "ClipInfo",
                         "ManifestationInfo", "CompilationInfo", "CompositeInfo",
                         *_LIGHTWEIGHT_CLASS})


def _xml_info(e: Mapping[str, Any], key: str) -> Mapping[str, Any] | None:
    v = e.get(key)
    if isinstance(v, Mapping):
        return v
    if not is_absent(v):
        raise RecordXmlError(f"{key} is not an object: {v!r}")
    return None


def _xml_extra(e: Mapping[str, Any]) -> dict[str, Any]:
    _check_keys("ExtraObjectMetadata", e, _EXTRA_KEYS)
    out: dict[str, Any] = {}
    if (se := _xml_info(e, "SeriesInfo")) is not None:
        _put(out, "SeriesInfo", _xml_scalars(
            "SeriesInfo", se,
            ("EndDate", "SeriesClass", "NumberRequired", "DateRequired",
             "OriginalTitleRequired")))
    if (sa := _xml_info(e, "SeasonInfo")) is not None:
        _put(out, "SeasonInfo", _xml_scalars(
            "SeasonInfo", sa,
            ("Parent", "EndDate", "NumberRequired", "DateRequired", "OriginalTitleRequired",
             "SequenceNumber"), ("SeasonClass",)))
    if (ep := _xml_info(e, "EpisodeInfo")) is not None:
        _check_keys("EpisodeInfo", ep, {"Parent", "SequenceInfo", "EpisodeClass", "TimeSlot"})
        o: dict[str, Any] = {}
        _put(o, "Parent", _xml_text(ep.get("Parent")))
        seq = ep.get("SequenceInfo")
        if isinstance(seq, Mapping):
            _check_keys("SequenceInfo", seq,
                        {"DistributionNumber", "HouseSequence", "AlternateNumber"})
            s: dict[str, Any] = {}
            _put(s, "DistributionNumber", _xml_numbered(seq.get("DistributionNumber")))
            _put(s, "HouseSequence", _xml_numbered(seq.get("HouseSequence")))
            _put(s, "AlternateNumber",
                 [x for x in (_xml_numbered(n) for n in _xml_list(seq.get("AlternateNumber")))
                  if x is not None])
            _put(o, "SequenceInfo", s)
        elif not is_absent(seq):
            raise RecordXmlError(f"SequenceInfo is not an object: {seq!r}")
        _put(o, "EpisodeClass", _xml_texts(ep.get("EpisodeClass")))
        _put(o, "TimeSlot", _xml_text(ep.get("TimeSlot")))
        _put(out, "EpisodeInfo", o)
    if (ed := _xml_info(e, "EditInfo")) is not None:
        _check_keys("EditInfo", ed, {"Parent", "EditUse", "EditClass", "MadeForRegion",
                                     "Details", "ColorType", "ThreeD"})
        o = {}
        _put(o, "Parent", _xml_text(ed.get("Parent")))
        _put(o, "EditUse", _xml_text(ed.get("EditUse")))
        _put(o, "EditClass", _xml_texts(ed.get("EditClass")))
        _put(o, "MadeForRegion", _xml_texts(ed.get("MadeForRegion")))
        # The record's "Details" is EditDetails in the schema (and
        # ManifestationDetails below); the record name is shared with star.
        _put(o, "EditDetails", _xml_details(ed.get("Details")))
        _put(o, "ColorType", _xml_text(ed.get("ColorType")))
        _put(o, "ThreeD", _xml_text(ed.get("ThreeD")))
        _put(out, "EditInfo", o)
    if (cl := _xml_info(e, "ClipInfo")) is not None:
        _check_keys("ClipInfo", cl, {"Parent", "ComponentsMode", "Start", "Duration"})
        o = {}
        for k in ("Parent", "ComponentsMode", "Start"):
            _put(o, k, _xml_text(cl.get(k)))
        _put(o, "Duration", _xml_texts(cl.get("Duration")))
        _put(out, "ClipInfo", o)
    if (mf := _xml_info(e, "ManifestationInfo")) is not None:
        _check_keys("ManifestationInfo", mf,
                    {"Parent", "ManifestationClass", "MadeForRegion", "Details", "Digital"})
        o = {}
        _put(o, "Parent", _xml_text(mf.get("Parent")))
        _put(o, "ManifestationClass", _xml_texts(mf.get("ManifestationClass")))
        _put(o, "MadeForRegion", _xml_texts(mf.get("MadeForRegion")))
        _put(o, "ManifestationDetails", _xml_details(mf.get("Details")))
        _put(o, "Digital", _xml_digital(mf.get("Digital")))
        _put(out, "ManifestationInfo", o)
    if (co := _xml_info(e, "CompilationInfo")) is not None:
        # XML_to_JSON's mirror shape. A Template-22 Compilation row cannot be
        # built (SUPPORTED_TEMPLATES), and record_from_xml reads this block
        # generically, so such a record raises on its keys rather than
        # writing a partial Compilation.
        _check_keys("CompilationInfo", co, {"Entry", "CompilationClass"})
        o = {}
        entries = []
        for en in _xml_list(co.get("Entry")):
            if not isinstance(en, Mapping):
                raise RecordXmlError(f"CompilationInfo Entry is not an object: {en!r}")
            _check_keys("CompilationInfo Entry", en, {"Name", "Number", "Class", "ID"})
            x: dict[str, Any] = {}
            _put(x, "DisplayName", _xml_text(en.get("Name")))
            _put(x, "EntryNumber", _xml_text(en.get("Number")))
            _put(x, "EntryClass", _xml_text(en.get("Class")))
            _put(x, "ContentID", _xml_text(en.get("ID")))
            if x:
                entries.append(x)
        _put(o, "Entry", entries)
        cc = co.get("CompilationClass")
        if isinstance(cc, Mapping):
            _check_keys("CompilationClass", cc, {"value", "_hasOtherInclusions"})
            _put(o, "CompilationClass", _with_attrs(
                _xml_text(cc.get("value")),
                {"hasOtherInclusions": _xml_text(cc.get("_hasOtherInclusions"))}))
        else:
            _put(o, "CompilationClass", _xml_text(cc))
        _put(out, "CompilationInfo", o)
    comps = []
    for cp in _xml_list(e.get("CompositeInfo")):
        if not isinstance(cp, Mapping):
            raise RecordXmlError(f"CompositeInfo is not an object: {cp!r}")
        _check_keys("CompositeInfo", cp, {"CompositeClass", "Element"})
        o = {}
        _put(o, "CompositeClass", _xml_text(cp.get("CompositeClass")))
        elems = []
        for el in _xml_list(cp.get("Element")):
            if not isinstance(el, Mapping):
                raise RecordXmlError(f"CompositeInfo Element is not an object: {el!r}")
            # DestinationStart / DestinationDuration are XML_to_JSON's mirror
            # names (q_composite_info); the schema's are DestStart / DestDuration.
            _check_keys("CompositeInfo Element", el,
                        {"ID", "ComponentsMode", "SourceStart", "SourceDuration",
                         "DestinationStart", "DestinationDuration"})
            x = {}
            for src, dst in (("ID", "ID"), ("SourceStart", "SourceStart"),
                             ("SourceDuration", "SourceDuration"),
                             ("ComponentsMode", "ComponentsMode"),
                             ("DestinationStart", "DestStart"),
                             ("DestinationDuration", "DestDuration")):
                _put(x, dst, _xml_text(el.get(src)))
            if x:
                elems.append(x)
        _put(o, "Element", elems)
        if o:
            comps.append(o)
    _put(out, "CompositeInfo", comps)
    for info, cls in _LIGHTWEIGHT_CLASS.items():
        rels = []
        for r in _xml_list(e.get(info)):
            if not isinstance(r, Mapping):
                raise RecordXmlError(f"{info} entry is not an object: {r!r}")
            # "Class" is XML_to_JSON's mirror name; record_from_xml keys the
            # class by its element name. Both are read.
            _check_keys(f"{info} entry", r, {"ID", "Class", cls})
            x = {}
            _put(x, "ID", _xml_text(r.get("ID")))
            _put(x, cls, _xml_text(_one_of(f"{info} entry", r, "Class", cls)))
            if x:
                rels.append(x)
        _put(out, info, rels)
    return out


def _xml_metadata(block: Mapping[str, Any]) -> dict[str, Any]:
    _check_keys("metadata block", block, {"BaseObjectData", "ExtraObjectMetadata"})
    out: dict[str, Any] = {}
    for key, build in (("BaseObjectData", _xml_base), ("ExtraObjectMetadata", _xml_extra)):
        v = block.get(key)
        if isinstance(v, Mapping):
            _put(out, key, build(v))
        elif not is_absent(v):
            raise RecordXmlError(f"{key} is not an object: {v!r}")
    return out


def _xml_provenance(block: Mapping[str, Any]) -> dict[str, Any]:
    # CreatedBy / LastModifiedBy are not carried (XML_to_JSON never reads
    # them from the mirror, for privacy), so a record holding them raises.
    _check_keys("ProvenanceMetadata", block,
                {"ID", "IssueNumber", "Status", "Administrators", "CreationDate",
                 "LastModificationDate", "PublicationDate"})
    out: dict[str, Any] = {}
    for k in ("ID", "IssueNumber", "Status"):
        _put(out, k, _xml_text(block.get(k)))
    adm = block.get("Administrators")
    if isinstance(adm, Mapping):
        _put(out, "Administrators", _xml_administrators(adm))
    elif not is_absent(adm):
        raise RecordXmlError(f"Administrators is not an object: {adm!r}")
    for k in ("CreationDate", "LastModificationDate", "PublicationDate"):
        _put(out, k, _xml_text(block.get(k)))
    return out


def _xml_alias(block: Mapping[str, Any]) -> dict[str, Any]:
    return _xml_scalars("AliasContinuation", block, ("LastAliased", "TargetOfLastAliased"))


_VIEW_BUILDERS = {
    "SelfDefinedMetadata": _xml_metadata,
    "FullMetadata": _xml_metadata,
    "ProvenanceMetadata": _xml_provenance,
    "AliasContinuation": _xml_alias,
}


def record_to_xml(record: Mapping[str, Any], *, view: str = "SelfDefinedMetadata") -> str:
    """One view of a standard record as EIDR 2.7.0 XML text: the inverse of
    ``record_from_xml``.

    ``record`` is a standard record (``record_from_row``, ``record_from_xml``
    or XML_to_JSON's export); ``record[view]`` is written, other keys
    (``CreationType``, ``DisplayName``, other views) are ignored. ``view`` is
    ``"SelfDefinedMetadata"`` (the default), ``"FullMetadata"``,
    ``"ProvenanceMetadata"`` or ``"AliasContinuation"``. Returns the view
    element as a document (with an XML declaration). Children are in the
    EIDR 2.7.0 schema's content-model order (``mddf_json.json_to_xml``), the
    root declares the EIDR default namespace plus ``md`` and ``xsi`` only
    when used, and attributes are in the registry's (alphabetical) order.

    Round trip: ``record_from_xml(record_to_xml(r)) == r`` for a record
    ``record_from_xml`` built, for every creation type a Template-22 sheet
    produces. A ``record_from_row`` record is not in that normal form (its
    Alt IDs carry the sheet's Domain and no Type, its Details domain is
    ``_domain``), so it round-trips at the row level:
    ``row_from_record(record_from_xml(record_to_xml(r)), t)`` equals
    ``row_from_record(r, t)``.

    **For a registration** (python-tools' ``-bmrin``): the creation element
    has the same children as this view's (the schema's
    ``creationSelfDefinedInfo`` / ``creationFullInfo`` share the order of
    ``selfDefinedFieldsGroup``), so the caller renames the root to the
    creation type (``Episode``, ``Basic``...). A creation carries no ``ID``:
    a ``record_from_row`` record has none; drop it from a
    ``record_from_xml`` one. Nothing is filtered: a ShortDOI Alt ID, which
    the registry issues, is written if the record holds one.

    Absent values (``inheritance.is_absent``) are not written, so no empty
    element; an element with attributes but no text (``<Description
    lang="en"/>``) is not written either, as both readers already treat it
    as no value (operator, 2026-11-15).

    Raises ``RecordXmlError`` (a ``ValueError``) naming the key when the
    record holds a field this writer cannot place: an unknown key, a
    non-object where an object belongs, a Domain on a non-Proprietary Alt
    ID, ``SystemGenerated`` true on an alternate title, a credit with a
    SortName and no DisplayName, two spellings of one field that disagree,
    or a ``ManifestationInfo`` ``Film``/``Tape`` block. Also raises when
    ``record`` has no ``view`` block or the block writes nothing. Never
    drops a value silently.

    Extracted from XML_to_JSON ``standard_render.render_view_xml`` (a5b0949).
    Differences from it: takes the whole record (it took the block), returns
    ``str`` and raises for an empty view (it returned ``None``); the error is
    ``RecordXmlError`` (its ``RenderError``); Details accept ``Domain`` as
    well as ``_domain`` and the lightweight relationships their element-named
    class key as well as ``Class`` (record_from_xml's spellings); the five
    silent drops listed above raise instead; the Alt ID type list is read lazily from
    ``mddf_json.eidr_schema()`` instead of re-parsing ``common.xsd`` at import.
    """
    build = _VIEW_BUILDERS.get(view)
    if build is None:
        raise ValueError(f"view must be one of {sorted(_VIEW_BUILDERS)}, not {view!r}")
    block = record.get(view)
    if not isinstance(block, Mapping):
        raise RecordXmlError(f"the record has no {view} block")
    practice = build(block)
    if not practice:
        raise RecordXmlError(f"the record's {view} block holds nothing to write")
    root: dict[str, Any] = dict(_XMLNS)
    root.update(practice)
    xml = json_to_xml({view: root})
    used = {""}
    for el in ET.fromstring(xml).iter():
        for q in (el.tag, *el.attrib):
            if q.startswith("{"):
                used.add(q[1:].split("}", 1)[0])
    for key in ("_xmlns:md", "_xmlns:xsi"):
        uri = _XMLNS[key]
        if uri not in used:
            # json_to_xml writes the root's declarations exactly so, once, in
            # its start tag; the first occurrence is that one. A resolve
            # document declares md/xsi only when it uses them.
            xml = xml.replace(f' xmlns:{key[7:]}="{uri}"', "", 1)
    return xml
