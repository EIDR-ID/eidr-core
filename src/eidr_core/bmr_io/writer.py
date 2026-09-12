"""BMR Template-22 workbook WRITER — the shared composition, one copy.

Extracted 2026-09-11 (register R13, OVERLAPS row 1 reopened 2026-09-10)
from eidr-wikidata ``bmr/writer.py`` (canonical: the anchor/insert split
and the Pass-2 sequence) with BMR-Review ``audit/bmr_writer.py`` as the
second consumer (dict rows, per-template families, the extra-column
convention). Three working writers existed, BMRtoAltID nearly built a
fourth and eidr-imdb needs a fifth — the workbook SURGERY was shared on
2026-08-03 but the composition that calls it was not, and "orchestration
stays per-consumer by design" stopped being true when the third copy
appeared.

THE SEAM (proposed by eidr-wikidata 2026-09-10, ruled here)
-----------------------------------------------------------
The writer takes rows ALREADY MAPPED to ``{column name: value}`` with family
members already numbered (``"Alternate Title 2"``), plus the names of any
extra columns to append after the template's own. That line was chosen
because 24% of the source file (``_row_values``) is consumer POLICY —
``Publication Status`` hard-coded to ``"valid"``, ``title_lang or "und"``,
an explicit ``Relation`` written only for Alt ID 1 — and none of it is
this module's business. Everything that decides WHAT a row says stays in
the consumer's mapper. Everything that decides HOW a row becomes a sheet
(family expansion, the extra-column convention, clearing, writing by header
name, the transplant that preserves the template's macros and validations)
is mechanism, and lives here exactly once.

ROUTING is a third thing, separate from both. ``template_for_creation_type``
is the one shared table for it (python-tools P3; the two private copies
DISAGREED on Compilation and the operator ruled). BMR-Review's caveat of
2026-09-11 is the reason it is separate: their mapper decided the template
as a side effect of mapping, which is the shape that lets one consumer's
routing policy leak into every other through a shared writer.

CAPS are two different things wearing one name (eidr-wikidata, 2026-09-10),
and only one half is shared:

* ``SCHEMA_MAX`` — what the REGISTRY accepts, read from ``common.xsd``
  (``maxOccurs``). A sheet that carries more groups than this registers
  nothing, so a consumer cap above it is refused rather than honoured.
* ``caps=`` — a consumer's own expansion ceiling, at or below the schema
  maximum. eidr-wikidata's 8 / 128 / 8 / 5 were believed to be registry
  maxima; the schema says 32 / 128 / 32 / 16, so three of the four are
  that consumer's CHOICE and a second consumer must not inherit them
  silently. Hence a parameter, defaulting to the schema.

Two silences this module refuses to keep, because both consumers kept them:

* A value whose column does not exist on the sheet was dropped without a
  word by both writers. It is now counted in ``WriteReport.dropped`` and,
  under ``strict=True``, refused. The permissive default stands because
  both consumers legitimately rely on "this column is absent on THIS
  template, skip it" (a Season Class on the Stand-Alone sheet) — but a
  consumer can now SEE that it happened, which is the difference between a
  design decision and a silent loss.
* A family that a consumer's mapper numbers past what the template holds
  and nothing expands (eidr-wikidata writes ``Alternate No. {i}`` for every
  i; the template has one group and no writer grows it) is the same loss
  wearing a different hat, and surfaces in the same report.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, NamedTuple

from eidr_core.bmr_io import (
    DATA_START,
    HEADER_ROW,
    count_family,
    expand_family,
    fix_shared_strings,
    read_headers,
    transplant,
)

log = logging.getLogger(__name__)

__all__ = ["Family", "Template", "TEMPLATES", "SHEET_TO_TEMPLATE", "SCHEMA_MAX",
           "CREATION_TYPES", "families_for", "template_for_creation_type",
           "max_counts", "WriteReport", "write_sheet"]


class Family(NamedTuple):
    """One repeating column family on a Template-22 sheet.

    ``anchor_members`` — EVERY column the template's group 1 carries. Used
    to find the rightmost existing column, after which new groups are
    inserted. Must be complete: a template column missing from this list
    makes the anchor land too far left and pushes that column rightward
    when groups are inserted (eidr-wikidata, 2026-05-09).

    ``insert_members`` — the columns each NEW group actually adds. By
    default the same as the anchor (a new group has the same columns as
    group 1, which is what the template's own second Alternate Title group
    shows). eidr-wikidata's sheets omit ``Alt Title Class`` and ``Relation``
    from groups 2+ by operator direction; that is a per-consumer value
    passed through ``families_for(insert_members=...)``, not a structural
    fact, and landing it as a parameter from the start is what keeps a
    second adopter from discovering it as a bug.
    """
    primary: str
    anchor_members: tuple[str, ...]
    insert_members: tuple[str, ...]


def _fam(primary: str, *members: str) -> Family:
    return Family(primary, members, members)


# Registry maxima per family, from ``common.xsd`` ``maxOccurs`` (schema
# 2.7 / md 2.8, checked 2026-09-11 against D:\Software\schemas\prod). None
# means the schema says ``unbounded``. Keys are the family PRIMARY column
# names as the templates spell them. Director / Actor are here as facts
# for mappers, not for expansion: both templates ship exactly Director 1-2
# and Actor 1-4 and neither is a family.
SCHEMA_MAX: dict[str, int | None] = {
    "Original Language": 32,
    "Alternate Title":   128,
    "Country of Origin": 32,
    "Associated Org":    16,
    "Alt ID":            None,
    "Director":          2,
    "Actor":             4,
    "Season Class":      None,
    "Episode Class":     None,
    "Edit Class":        8,
    "Made for Region":   8,
    "Edit Details":      8,
    "Version Language":  64,
    "Manif Class":       8,
    "Manif Details":     8,
    # Added 2026-09-11: XML_to_JSON's mapper emits both (its own heuristic
    # expander grew any "... 1" run), and eidr-wikidata had been losing
    # `Alternate No. 2+` silently. MetadataAuthority maxOccurs=4 (common.xsd
    # :280); AlternateNumber is unbounded (md-v2.8 SequenceInfo :122).
    "Metadata Authority": 4,
    "Alternate No.":      None,
}

# The five families every content template shares (Clips have only the
# last two). Listed in template left-to-right order per sheet below —
# expansion shifts columns, and the shared ``headers`` dict is updated in
# place, so order is about keeping the walk readable rather than correct.
_ORIGINAL_LANGUAGE = _fam("Original Language", "Original Language", "Language Mode")
_ALTERNATE_TITLE = _fam("Alternate Title", "Alternate Title", "Alt Title Language",
                        "Alt Title Class")
_COUNTRY = _fam("Country of Origin", "Country of Origin")
_ASSOCIATED_ORG = _fam("Associated Org", "Associated Org", "Associated Org Role",
                       "Associated Org Party ID")
_ALT_ID = _fam("Alt ID", "Alt ID", "Domain", "Relation")
# Edit / Manifestation carry a Version Language instead of an Original
# Language; its companion column is ALSO called "Language Mode", which is
# why a family list never holds both.
_VERSION_LANGUAGE = _fam("Version Language", "Version Language", "Language Mode")
_MADE_FOR_REGION = _fam("Made for Region", "Made for Region")
# Every content template but Compilations ships "Metadata Authority 1" +
# "Metadata Authority Party ID 1" (Compilations carry the pair unnumbered).
_METADATA_AUTHORITY = _fam("Metadata Authority", "Metadata Authority",
                           "Metadata Authority Party ID")
# Episodics only: the SequenceInfo alternate numbers.
_ALTERNATE_NO = _fam("Alternate No.", "Alternate No.", "Alt. No. Domain")


class Template(NamedTuple):
    key: str
    filename: str
    sheet: str
    families: tuple[Family, ...]
    # The data sheet's header row as SHIPPED (row 3), read from the
    # templates on 2026-09-11. This is what "Template-22 conformance"
    # means for a sheet: every one of these names present, by exact text.
    # Extra columns and expanded families are conforming; a missing name
    # is not. Empty only for a caller-built Template.
    headers: tuple[str, ...] = ()


# Shipped header rows, one per data sheet (see Template.headers). Lengths
# cross-checked against the template files: 72 / 56 / 63 / 49 / 61 / 63.
_HEADERS: dict[str, tuple[str, ...]] = {
    "episodic": (
        'Unique Row ID', 'Parent EIDR/Row ID', 'Mode', 'Structural Type', 'Referent Type',
        'Title', 'Title Language', 'Title Class', 'Original Language 1', 'Language Mode 1',
        'Alternate Title 1', 'Alt Title Language 1', 'Alt Title Class 1',
        'Alternate Title 2', 'Alt Title Language 2', 'Alt Title Class 2',
        'Country of Origin 1', 'Associated Org 1', 'Associated Org Role 1',
        'Associated Org Party ID 1', 'Associated Org 2', 'Associated Org Role 2',
        'Associated Org Party ID 2', 'Associated Org 3', 'Associated Org Role 3',
        'Associated Org Party ID 3', 'Metadata Authority 1',
        'Metadata Authority Party ID 1', 'Release Date', 'End Date', 'Time Slot',
        'Series Class', 'Season Class 1', 'Episode Class 1', 'Number Required',
        'Date Required', 'Original Title Required', 'Season No.', 'Distribution No.',
        'Dist. No. Domain', 'House No.', 'House No. Domain', 'Alternate No. 1',
        'Alt. No. Domain 1', 'Publication Status', 'Approx Length', 'Registrant',
        'Director 1', 'Director 2', 'Actor 1', 'Actor 2', 'Actor 3', 'Actor 4', 'Alt ID 1',
        'Domain 1', 'Relation 1', 'Alt ID 2', 'Domain 2', 'Relation 2', 'Alt ID 3',
        'Domain 3', 'Relation 3', 'IMDb', 'IMDb Relation', 'ISAN', 'ISAN Relation',
        'Description', 'Description Language', 'Registrant Extra', "Operator's Notes",
        'Assigned EIDR ID', 'Registration Errors & Notes',
    ),
    "non_episodic": (
        'Unique Row ID', 'Mode', 'Structural Type', 'Referent Type', 'Title',
        'Title Language', 'Title Class', 'Original Language 1', 'Language Mode 1',
        'Alternate Title 1', 'Alt Title Language 1', 'Alt Title Class 1',
        'Alternate Title 2', 'Alt Title Language 2', 'Alt Title Class 2',
        'Country of Origin 1', 'Associated Org 1', 'Associated Org Role 1',
        'Associated Org Party ID 1', 'Associated Org 2', 'Associated Org Role 2',
        'Associated Org Party ID 2', 'Associated Org 3', 'Associated Org Role 3',
        'Associated Org Party ID 3', 'Metadata Authority 1',
        'Metadata Authority Party ID 1', 'Release Date', 'Publication Status',
        'Approx Length', 'Registrant', 'Director 1', 'Director 2', 'Actor 1', 'Actor 2',
        'Actor 3', 'Actor 4', 'Alt ID 1', 'Domain 1', 'Relation 1', 'Alt ID 2', 'Domain 2',
        'Relation 2', 'Alt ID 3', 'Domain 3', 'Relation 3', 'IMDb', 'IMDb Relation',
        'ISAN', 'ISAN Relation', 'Description', 'Description Language', 'Registrant Extra',
        "Operator's Notes", 'Assigned EIDR ID', 'Registration Errors & Notes',
    ),
    "edit": (
        'Unique Row ID', 'Parent EIDR/Row ID', 'Mode', 'Edit Use', 'Color Type', 'In 3D',
        'Edit Class 1', 'Edit Class 2', 'Edit Class 3', 'Made for Region 1',
        'Made for Region 2', 'Made for Region 3', 'Edit Details 1',
        'Edit Details Domain 1', 'Structural Type', 'Referent Type', 'Title',
        'Title Language', 'Title Class', 'Version Language 1', 'Language Mode 1',
        'Alternate Title 1', 'Alt Title Language 1', 'Alt Title Class 1',
        'Country of Origin 1', 'Associated Org 1', 'Associated Org Role 1',
        'Associated Org Party ID 1', 'Associated Org 2', 'Associated Org Role 2',
        'Associated Org Party ID 2', 'Associated Org 3', 'Associated Org Role 3',
        'Associated Org Party ID 3', 'Metadata Authority 1',
        'Metadata Authority Party ID 1', 'Release Date', 'Publication Status',
        'Approx Length', 'Registrant', 'Director 1', 'Director 2', 'Actor 1', 'Actor 2',
        'Actor 3', 'Actor 4', 'Alt ID 1', 'Domain 1', 'Relation 1', 'Alt ID 2', 'Domain 2',
        'Relation 2', 'Alt ID 3', 'Domain 3', 'Relation 3', 'ISAN', 'ISAN Relation',
        'Description', 'Description Language', 'Registrant Extra', "Operator's Notes",
        'Assigned EIDR ID', 'Registration Errors & Notes',
    ),
    "clip": (
        'Unique Row ID', 'Parent EIDR/Row ID', 'Mode', 'Start Time', 'Content Duration',
        'Component Mode', 'Structural Type', 'Referent Type', 'Title', 'Title Language',
        'Title Class', 'Associated Org 1', 'Associated Org Role 1',
        'Associated Org Party ID 1', 'Associated Org 2', 'Associated Org Role 2',
        'Associated Org Party ID 2', 'Associated Org 3', 'Associated Org Role 3',
        'Associated Org Party ID 3', 'Metadata Authority 1',
        'Metadata Authority Party ID 1', 'Release Date', 'Publication Status',
        'Approx Length', 'Registrant', 'Director 1', 'Director 2', 'Actor 1', 'Actor 2',
        'Actor 3', 'Actor 4', 'Alt ID 1', 'Domain 1', 'Relation 1', 'Alt ID 2', 'Domain 2',
        'Relation 2', 'Alt ID 3', 'Domain 3', 'Relation 3', 'V-ISAN', 'V-ISAN Relation',
        'Description', 'Description Language', 'Registrant Extra', "Operator's Notes",
        'Assigned EIDR ID', 'Registration Errors & Notes',
    ),
    "manifestation": (
        'Unique Row ID', 'Parent EIDR/Row ID', 'Structural Type', 'Manif Class 1',
        'Manif Class 2', 'Made for Region 1', 'Made for Region 2', 'Manif Details 1',
        'Manif Details Domain 1', 'Release Date', 'Publication Status', 'Approx Length',
        'Version Language 1', 'Language Mode 1', 'Mode', 'Referent Type', 'Title',
        'Title Language', 'Title Class', 'Alternate Title 1', 'Alt Title Language 1',
        'Alt Title Class 1', 'Alternate Title 2', 'Alt Title Language 2',
        'Alt Title Class 2', 'Country of Origin 1', 'Associated Org 1',
        'Associated Org Role 1', 'Associated Org Party ID 1', 'Associated Org 2',
        'Associated Org Role 2', 'Associated Org Party ID 2', 'Associated Org 3',
        'Associated Org Role 3', 'Associated Org Party ID 3', 'Metadata Authority 1',
        'Metadata Authority Party ID 1', 'Registrant', 'Director 1', 'Director 2',
        'Actor 1', 'Actor 2', 'Actor 3', 'Actor 4', 'Alt ID 1', 'Domain 1', 'Relation 1',
        'Alt ID 2', 'Domain 2', 'Relation 2', 'Alt ID 3', 'Domain 3', 'Relation 3', 'ISAN',
        'ISAN Relation', 'Description', 'Description Language', 'Registrant Extra',
        "Operator's Notes", 'Assigned EIDR ID', 'Registration Errors & Notes',
    ),
    "compilation": (
        'Unique Row ID', 'Header Row ID', 'Entry Number', 'Content ID', 'Display Name',
        'Entry Class', 'Compilation Class', 'Has Other Inclusions', 'Description',
        'Description Language', 'Mode', 'Structural Type', 'Referent Type', 'Title',
        'Title Language', 'Title Class', 'Original Language 1', 'Language Mode 1',
        'Alternate Title 1', 'Alt Title Language 1', 'Alt Title Class 1',
        'Alternate Title 2', 'Alt Title Language 2', 'Alt Title Class 2',
        'Country of Origin 1', 'Associated Org 1', 'Associated Org Role 1',
        'Associated Org Party ID 1', 'Associated Org 2', 'Associated Org Role 2',
        'Associated Org Party ID 2', 'Associated Org 3', 'Associated Org Role 3',
        'Associated Org Party ID 3', 'Metadata Authority', 'Metadata Authority Party ID',
        'Release Date', 'Publication Status', 'Approx Length', 'Registrant', 'Director 1',
        'Director 2', 'Actor 1', 'Actor 2', 'Actor 3', 'Actor 4', 'Alt ID 1', 'Domain 1',
        'Relation 1', 'Alt ID 2', 'Domain 2', 'Relation 2', 'Alt ID 3', 'Domain 3',
        'Relation 3', 'IMDb', 'IMDb Relation', 'ISAN', 'ISAN Relation', 'Registrant Extra',
        "Operator's Notes", 'Assigned EIDR ID', 'Registration Errors & Notes',
    ),
}

# Every Template-22 content sheet, as shipped (header rows read from the
# templates on 2026-09-11). The Service template (`EIDR_Service_Template-22`,
# renamed from Video Service on 2026-09-12) is deliberately absent: it
# registers Service records, not content records, its families are
# different and unverified, and no portfolio consumer writes it.
TEMPLATES: dict[str, Template] = {
    "episodic": Template(
        "episodic", "EIDR_Episodic_Template-22.xlsx", "Episodics",
        (_ORIGINAL_LANGUAGE, _ALTERNATE_TITLE, _COUNTRY, _ASSOCIATED_ORG, _METADATA_AUTHORITY,
         _fam("Season Class", "Season Class"), _fam("Episode Class", "Episode Class"),
         _ALTERNATE_NO, _ALT_ID),
        headers=_HEADERS["episodic"]),
    "non_episodic": Template(
        "non_episodic", "EIDR_Non-Episodic_Template-22.xlsx", "Stand-Alone Works",
        (_ORIGINAL_LANGUAGE, _ALTERNATE_TITLE, _COUNTRY, _ASSOCIATED_ORG,
        _METADATA_AUTHORITY, _ALT_ID),
        headers=_HEADERS["non_episodic"]),
    "edit": Template(
        "edit", "EIDR_Edit_Template-22.xlsx", "Edits",
        (_fam("Edit Class", "Edit Class"), _MADE_FOR_REGION,
         _fam("Edit Details", "Edit Details", "Edit Details Domain"),
         _VERSION_LANGUAGE, _ALTERNATE_TITLE, _COUNTRY, _ASSOCIATED_ORG,
         _METADATA_AUTHORITY, _ALT_ID),
        headers=_HEADERS["edit"]),
    "clip": Template(
        "clip", "EIDR_Clip_Template-22.xlsx", "Clips",
        (_ASSOCIATED_ORG, _METADATA_AUTHORITY, _ALT_ID),
        headers=_HEADERS["clip"]),
    "manifestation": Template(
        "manifestation", "EIDR_Manifestation_Template-22.xlsx", "Manifestations",
        (_fam("Manif Class", "Manif Class"), _MADE_FOR_REGION,
         _fam("Manif Details", "Manif Details", "Manif Details Domain"),
         _VERSION_LANGUAGE, _ALTERNATE_TITLE, _COUNTRY, _ASSOCIATED_ORG,
         _METADATA_AUTHORITY, _ALT_ID),
        headers=_HEADERS["manifestation"]),
    # Compilation rows come in Header + Entry groups (python-tools P4, not
    # this module's business); the column families are the Stand-Alone set.
    "compilation": Template(
        "compilation", "EIDR_Compilation_Template-22.xlsx", "Compilations",
        (_ORIGINAL_LANGUAGE, _ALTERNATE_TITLE, _COUNTRY, _ASSOCIATED_ORG, _ALT_ID),
        headers=_HEADERS["compilation"]),
}

SHEET_TO_TEMPLATE: dict[str, str] = {t.sheet: k for k, t in TEMPLATES.items()}

# The schema's ``creationType`` enumeration, without the ``Create`` prefix
# it carries there (``CreateEpisode``). Interactive and Composite are real
# creation types with NO Template-22 sheet, so they route to None on
# purpose — that is "no template", which is a different answer from "not a
# creation type", and the two used to be indistinguishable.
CREATION_TYPES: frozenset[str] = frozenset({
    "Basic", "Series", "Season", "Episode", "Edit", "Clip", "Manifestation",
    "Compilation", "Interactive", "Composite",
})

_ROUTING: dict[str, str | None] = {
    "Basic": "non_episodic",
    "Series": "episodic", "Season": "episodic", "Episode": "episodic",
    "Edit": "edit",
    "Clip": "clip",
    "Manifestation": "manifestation",
    # Operator ruling (2026-09-10): Compilation is a root type and routes
    # to the Compilations sheet. BMR-Review sent it to Stand-Alone Works;
    # XML_to_JSON did not route it at all. Neither was right.
    "Compilation": "compilation",
    "Interactive": None,
    "Composite": None,
}


def template_for_creation_type(creation_type: str) -> str | None:
    """Template key for a CREATION type — the schema's own vocabulary.

    Raises on anything that is not a creation type, instead of returning
    None. Both private copies returned None for unknown input, and one of
    them was being fed REFERENT types (``"Movie"``, ``"TV"``): a row whose
    type is misspelt or mis-sourced would silently join the "no template"
    bucket and never be exported, which is the wrong answer that looks like
    a decision. ``"CreateEpisode"`` (the enumeration spelling) is accepted.
    """
    ct = (creation_type or "").strip()
    if ct.startswith("Create") and ct[6:] in CREATION_TYPES:
        ct = ct[6:]
    if ct not in CREATION_TYPES:
        raise ValueError(
            f"{creation_type!r} is not an EIDR creation type "
            f"(one of {sorted(CREATION_TYPES)}); a referent type such as "
            f"'Movie' is not a creation type — route on the record's "
            f"creation type instead")
    return _ROUTING[ct]


def families_for(template: str, *,
                 insert_members: Mapping[str, Sequence[str]] | None = None,
                 ) -> list[Family]:
    """The families of one template, with optional per-consumer
    ``insert_members`` overrides keyed by family primary.

    An override must be a subset of the family's anchor and must still
    include the primary column — the primary is what ``count_family``
    counts, so a group inserted without it is invisible to the next
    expansion and the writer would insert it again.
    """
    try:
        fams = TEMPLATES[template].families
    except KeyError:
        raise KeyError(f"unknown Template-22 key {template!r}; "
                       f"one of {sorted(TEMPLATES)}") from None
    overrides = dict(insert_members or {})
    unknown = set(overrides) - {f.primary for f in fams}
    if unknown:
        raise ValueError(f"insert_members names families not on template "
                         f"{template!r}: {sorted(unknown)}")
    out: list[Family] = []
    for fam in fams:
        if fam.primary in overrides:
            ins = tuple(overrides[fam.primary])
            extra = set(ins) - set(fam.anchor_members)
            if extra:
                raise ValueError(f"insert_members for {fam.primary!r} names "
                                 f"columns outside the family: {sorted(extra)}")
            if fam.primary not in ins:
                raise ValueError(f"insert_members for {fam.primary!r} must "
                                 f"include the primary column")
            fam = fam._replace(insert_members=ins)
        out.append(fam)
    return out


_NUMBERED = re.compile(r"^(.*?) (\d+)$")


def max_counts(rows: Iterable[Mapping[str, Any]],
               families: Sequence[Family]) -> dict[str, int]:
    """Highest group number each family needs across ``rows``, keyed by
    family primary. Any member column counts (``"Domain 4"`` alone means
    four Alt ID groups). Only NON-EMPTY values count: a key present with
    None or "" would otherwise expand the sheet to hold nothing.
    """
    member_to_primary = {m: f.primary for f in families for m in f.anchor_members}
    counts: dict[str, int] = {}
    for row in rows:
        for col, val in row.items():
            if val is None or val == "":
                continue
            m = _NUMBERED.match(col)
            if not m:
                continue
            primary = member_to_primary.get(m.group(1))
            if primary is not None:
                counts[primary] = max(counts.get(primary, 0), int(m.group(2)))
    return counts


@dataclass
class WriteReport:
    """What ``write_sheet`` did, so a consumer can see what it could not.

    ``expanded`` — families that grew, with the group count now on the
    sheet. ``capped`` — families whose rows asked for MORE groups than the
    effective cap, with the number asked for (the trimmed values also
    appear in ``dropped``). ``dropped`` — column name → count of non-empty
    values that had no column to land in.
    """
    path: str
    rows: int
    expanded: dict[str, int] = field(default_factory=dict)
    capped: dict[str, int] = field(default_factory=dict)
    dropped: dict[str, int] = field(default_factory=dict)


def _effective_caps(caps: Mapping[str, int | None] | None) -> dict[str, int | None]:
    out: dict[str, int | None] = dict(SCHEMA_MAX)
    for primary, cap in (caps or {}).items():
        if primary not in SCHEMA_MAX:
            raise ValueError(f"cap for unknown family {primary!r}; "
                             f"one of {sorted(SCHEMA_MAX)}")
        schema = SCHEMA_MAX[primary]
        if cap is None and schema is not None:
            raise ValueError(f"cap for {primary!r} cannot be unbounded: the "
                             f"registry accepts at most {schema}")
        if cap is not None and schema is not None and cap > schema:
            raise ValueError(f"cap {cap} for {primary!r} exceeds the registry "
                             f"maximum of {schema}; a sheet carrying that many "
                             f"groups registers nothing")
        out[primary] = cap
    return out


def write_sheet(template_path: str, sheet_name: str,
                rows: Iterable[Mapping[str, Any]], out_path: str, *,
                families: Sequence[Family] | None = None,
                caps: Mapping[str, int | None] | None = None,
                extra_columns: Sequence[str] = (),
                strict: bool = False) -> WriteReport:
    """Write mapped rows onto a copy of one Template-22 sheet.

    The sequence is eidr-wikidata's, verbatim in effect: copy the template
    → expand families left-to-right to the largest group any row needs →
    append ``extra_columns`` → clear everything from ``DATA_START`` → write
    each value by header NAME → save to a temp file → ``transplant`` the
    edited worksheet back into the template container so its macros,
    validations and formulas survive openpyxl → ``fix_shared_strings`` for
    the EPPlus-based BMR tool.

    ``families`` defaults to the sheet's own (``TEMPLATES`` by sheet name);
    pass ``families_for(key, insert_members=...)`` to apply consumer
    policy. ``caps`` are per-family ceilings at or below ``SCHEMA_MAX``.

    ``extra_columns`` land after ONE blank separator column following the
    template's last header, then adjacent to each other. Both consumers
    did this (``last_col + 2``): the blank column keeps consumer-appended
    diagnostics visibly outside the template's data area, and the BMR tool
    ignores what it does not name. Their values come from the row dicts
    under the same names.
    """
    import openpyxl  # the `bmr` extra; everything else here is stdlib

    if not os.path.exists(template_path):
        raise FileNotFoundError(f"BMR template not found: {template_path}")
    if families is None:
        key = SHEET_TO_TEMPLATE.get(sheet_name)
        if key is None:
            raise ValueError(f"{sheet_name!r} is not a Template-22 data sheet "
                             f"({sorted(SHEET_TO_TEMPLATE)}); pass families= "
                             f"explicitly for a custom sheet")
        families = TEMPLATES[key].families
    effective = _effective_caps(caps)
    rows = list(rows)

    shutil.copyfile(template_path, out_path)
    wb = openpyxl.load_workbook(out_path, data_only=False)
    if sheet_name not in wb.sheetnames:
        raise ValueError(f"template {template_path} has no sheet {sheet_name!r}")
    ws = wb[sheet_name]

    headers = read_headers(ws)
    counts = max_counts(rows, families)
    report = WriteReport(path=out_path, rows=len(rows))
    for fam in families:
        want = counts.get(fam.primary, 0)
        cap = effective.get(fam.primary)
        if cap is not None and want > cap:
            report.capped[fam.primary] = want
            want = cap
        if want > count_family(headers, fam.primary):
            expand_family(ws, fam.primary, list(fam.anchor_members),
                          list(fam.insert_members), want, headers)
            report.expanded[fam.primary] = count_family(headers, fam.primary)
    # Re-read rather than trust the shifted dict: it is the authority on
    # what the sheet now says, and the two consumers disagreed on which to
    # trust. Same result when expand_family is correct; the honest one
    # when it is not.
    headers = read_headers(ws)

    if extra_columns:
        next_col = (max(headers) if headers else 0) + 2
        for name in extra_columns:
            if name in headers.values():
                raise ValueError(f"extra column {name!r} already exists on "
                                 f"sheet {sheet_name!r}")
            ws.cell(HEADER_ROW, next_col).value = name
            headers[next_col] = name
            next_col += 1
    name_to_col = {h: c for c, h in headers.items()}

    # Templates ship empty, but a template someone saved a trial row into
    # must not leak that row under the data.
    if ws.max_row >= DATA_START:
        for r in range(DATA_START, ws.max_row + 1):
            for c in range(1, ws.max_column + 1):
                ws.cell(r, c).value = None

    for row_idx, row in enumerate(rows, DATA_START):
        for name, value in row.items():
            # An empty value is not a value: a blank cell, never an empty
            # string, so a reader that distinguishes the two sees what
            # the mapper meant.
            if value is None or value == "":
                continue
            col = name_to_col.get(name)
            if col is None:
                report.dropped[name] = report.dropped.get(name, 0) + 1
                continue
            ws.cell(row_idx, col).value = value
    if report.dropped and strict:
        raise ValueError(f"{len(report.dropped)} column(s) have no home on "
                         f"sheet {sheet_name!r}: {sorted(report.dropped)}")

    out_dir = os.path.dirname(os.path.abspath(out_path)) or "."
    fd, tmp = tempfile.mkstemp(suffix=".xlsx", dir=out_dir)
    os.close(fd)
    try:
        wb.save(tmp)
        transplant(template_xlsx=out_path, edited_xlsx=tmp)
        fix_shared_strings(out_path)
    finally:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
    log.info("write_sheet: %d row(s) -> %s [%s]%s", len(rows), out_path, sheet_name,
             f" dropped={sorted(report.dropped)}" if report.dropped else "")
    return report
