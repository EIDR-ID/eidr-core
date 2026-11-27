"""Merge a supplied record into the current registry record (S3, merge-rules 1.0.0).

``merge(current, supplied)`` compares the record a sheet row (or any other
source) supplies with the record the registry holds, applies the rule table
of ``specs/merge-rules.md`` and returns a ``ChangeReport``: ``changed`` False
means the caller submits nothing; True means ``merged_xml`` is the Modify to
submit, with every edit listed in ``changes``. It replaces the .NET BMR
tool's Merge mode (``CompareEidrRecord.cs``), whose rules it carries in the
.NET order with the operator's revisions applied; the spec governs where the
two differ, and the docstrings below name each place the .NET source was read
to settle a reading the spec leaves open.

**Pure.** No I/O, SDK, registry or mirror: the caller fetches the current
record and hands over its XML. Stdlib only (``xml.etree`` through the modules
it builds on), so it vendors: the closure is ``["merge", "bmr_map",
"bmr_io", "inheritance", "ids", "ordering", "mddf_json", "altidtool_io",
"normalize", "codes"]`` (tests/test_vendor.py syncs exactly that). A
vendored copy cannot read ``altidtool_io.multi_form_domains()`` (package
data), so a vendoring caller passes ``MergeOptions.multi_form_domains``.

**How.** Both sides are read into the standard record shape
(``bmr_map.record_from_xml``), the rules edit a copy of the current record's
``SelfDefinedMetadata`` (the modification base), and ``bmr_map.record_to_xml``
writes the result. Every element therefore lands in the EIDR 2.7.0 schema's
content-model order by construction (``mddf_json.json_to_xml``), never at a
hand-chosen position: the .NET tool's insertion was ``// TODO: ensure
location correct`` throughout (merge-rules section 6). Per-family caps are the
schema's ``maxOccurs`` read from the bundled ``common.xsd``, never the .NET
hardcoded caps; named Alt ID types, their value patterns and the relation
vocabulary are read from the same schema.

**What is not here.** The section 5 HELD items -- AddTitleClass,
SetStructuralType, the post-process primary-title overwrite
(CorrectMismatchedTitleLanguageCountryOfOrigin) and the replace-class rules
2, 4, 5, 6 and 7 -- are not shipped. ``MergeOptions(replace=True)`` raises
rather than silently running the add-only rules, because a caller who asked
for replacement and got none would believe the record was reconciled.

**Inherited counts as present** (operator, 2026-10-02): rule 15 decides
presence on the full record. Pass the registry's ``FullMetadata`` (in the
same document as the ``SelfDefinedMetadata``, as an API Shim message carries
both, or as ``full=``). Without it, a record with a parent whose own length is
absent is skipped with a reason rather than guessed at.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from functools import cache, lru_cache
from typing import Any, NamedTuple

from eidr_core.altidtool_io import (
    AltId,
    AltIdRow,
    _norm_relation,
    emission_problem,
    format_line,
    is_audited,
    is_single_form,
    kind_key,
    multi_form_domains,
    same_relation,
)
from eidr_core.bmr_map import record_from_xml, record_to_xml
from eidr_core.inheritance import is_absent
from eidr_core.mddf_json import eidr_schema
from eidr_core.normalize import ascii_fold, parse_minutes

__all__ = ["SPEC_VERSION", "FUZZY_THRESHOLD", "FUZZY_THRESHOLD_ORG", "RULES", "HELD_RULES",
           "FIELD_KEYS", "MergeOptions", "Change", "Conflict", "Skip", "ChangeReport",
           "merge", "spec_values_digest"]

# The merge-rules.md version this engine implements. eidr-core assigns it;
# a rule, knob or field-key change is a version bump with a new values pin
# (tests/merge_rules_values_pin.json), exactly as compare-spec is versioned.
SPEC_VERSION = "1.0.0"

# The .NET constants, carried verbatim (CompareEidrRecord.cs lines 12-14).
# Reviewable knobs, NOT rulings (merge-rules section 2): "different" means a
# Levenshtein distance ABOVE the threshold between the normalised strings.
FUZZY_THRESHOLD = 4
FUZZY_THRESHOLD_ORG = 6   # org names, so "Company" and "Co" still match

# (id, .NET name, class) in the order the rules run. "pre.N" are the
# pre-process steps (section 3.2) on the fetched record; "skip" rules never
# edit and only report when the supplied record carries the field.
RULES: tuple[tuple[str, str, str], ...] = (
    ("pre.1", "RemoveRepeatingTitles", "pre"),
    ("pre.2", "RemoveRepeatingDirectors", "pre"),
    ("pre.3", "RemoveRepeatingActors", "pre"),
    ("pre.4", "RemoveRepeatingAssOrgPartyIDs", "pre"),
    ("pre.5", "RemoveRepeatingMetadataAuthorityPartyIDs", "pre"),
    ("pre.6", "CleanCountryOfOrigin", "pre"),
    ("pre.7", "CleanStructuralType", "pre"),
    ("1", "ReplaceTitleLanguage", "add"),
    ("3", "AddMissingTitle", "add"),
    ("8", "AddMissingCountryOfOrigin", "add"),
    ("9", "AddMissingOriginalLanguage", "add"),
    ("10", "AddMissingVersionLanguage", "add"),
    ("11", "AddMissingAssociatedOrg", "add"),
    ("12", "AddMissingDirector", "add"),
    ("13", "AddMissingActor", "add"),
    ("14", "SetPublicationStatus", "skip"),
    ("15", "ReplaceApproxLength", "add"),
    ("16", "AddMissingDescription", "add"),
    ("17", "AddMissingRegistrantExtra", "add"),
    ("18a", "AddMissingMetadataAuthority", "add"),
    ("18", "AddMissingAlternateID", "add"),
    ("19", "AddMissingSeriesInfo", "skip"),
    ("20", "AddMissingSeriesClass", "add"),
    ("21", "AddMissingEndDate", "add"),
    ("22", "AddMissingSeasonNumber", "add"),
    ("23", "AddMissingSeasonClasses", "add"),
    ("24", "AddMissingEpisodeClasses", "add"),
    ("25", "AddMissingDistributionNumber", "add"),
    ("26", "AddMissingHouseNumber", "add"),
    ("27", "AddMissingAlternateNumbers", "add"),
    ("28", "AddMissingTimeSlot", "add"),
)

# Section 5: held for the operator's review after S3's fixtures. Not run.
HELD_RULES: tuple[tuple[str, str], ...] = (
    ("AddTitleClass", "title @titleClass"),
    ("2", "ReplaceMode"),
    ("4", "ReplaceReleaseYear1"),
    ("5", "ReplaceReleaseYear2"),
    ("6", "ReplaceReleaseDate"),
    ("7", "ReplaceCountryOfOrigin"),
    ("SetStructuralType", "StructuralType"),
    ("post.1", "CorrectMismatchedTitleLanguageCountryOfOrigin"),
)

# The field key of every Change / Conflict / Skip (merge-rules section 5.1,
# ruled 2026-11-26: eidr-wikidata's proposal). Stable across sheet and record,
# so the two-phase contribution ledger keys on (field, value) without
# re-deriving anything; Alt IDs use the ledger's own convention. ``<x>`` is
# lowercased. The normalised value (``Change.value``) is the value
# ``str.strip().lower()``, the ledger's ``value_norm``.
FIELD_KEYS: dict[str, str] = {
    "title:primary": "the main title (ResourceName); value = its text",
    "title:alternate": "an alternate title (AlternateResourceName); value = its text",
    "title_language:primary": "the main title's lang; old/new = the codes, value = its text",
    "title_language:alternate": "an alternate's lang; old/new = the codes, value = its text",
    # The keys of the held rules are fixed now, so the table is complete for
    # the day they ship (AddTitleClass, rules 2 and 4 to 6).
    "title_class:primary": "the main title's titleClass (held AddTitleClass); value = its text",
    "title_class:alternate": "an alternate's titleClass (held AddTitleClass); value = its text",
    "structural_type": "StructuralType",
    "referent_type": "ReferentType",
    "mode": "Mode (held rule 2)",
    "release_date": "ReleaseDate (held rules 4 to 6)",
    "status": "Status (rule 14 only reports)",
    "country_of_origin": "one CountryOfOrigin code",
    "original_language": "one OriginalLanguage; value = code, or code|mode when a mode is set",
    "version_language": "one VersionLanguage; value as original_language",
    "associated_org:<role>": "one AssociatedOrg of that role; value = its party ID, else its name",
    "director": "one Credits/Director; value = its DisplayName",
    "actor": "one Credits/Actor; value = its DisplayName",
    "approximate_length": "ApproximateLength",
    "description:<lang>": "Description with its lang attribute; value = its text",
    "registrant_extra:<key>": "one key:value pair of RegistrantExtra; value = the pair's value",
    "metadata_authority": "one Administrators/MetadataAuthority party ID",
    "alt_id:<type>|<domain>": "one AlternateID of that Kind (domain empty for a named type); "
                              "value = the Alt ID value",
    "series_info": "SeriesInfo flags (rule 19 only reports)",
    "series_class": "SeriesInfo/SeriesClass",
    "end_date": "SeriesInfo/EndDate",
    "season_number": "SeasonInfo/SequenceNumber",
    "season_class": "one SeasonInfo/SeasonClass",
    "episode_class": "one EpisodeInfo/EpisodeClass",
    "distribution_number:<domain>": "SequenceInfo/DistributionNumber",
    "house_sequence:<domain>": "SequenceInfo/HouseSequence",
    "alternate_number:<domain>": "one SequenceInfo/AlternateNumber",
    "time_slot": "EpisodeInfo/TimeSlot",
}

_EIDR = "{http://www.eidr.org/schema}"
_MD = "{http://www.movielabs.com/schema/md/v2.8/md}"
_XS = "{http://www.w3.org/2001/XMLSchema}"


# --------------------------------------------------------------------------
# The report
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class MergeOptions:
    """How to merge.

    ``replace`` asks for the replace-class rules (MergeTool ``--replace``);
    they are HELD (section 5), so True raises ``ValueError``. ``altids_only``
    runs rule 18 alone (BMRtoAltID's standard mode; no pre-process either, so
    nothing but Alt IDs can change). ``multi_form_domains`` is rule 18.5's
    exempt Kinds; None reads ``altidtool_io.multi_form_domains()``, which a
    vendored copy cannot do, so a vendoring caller passes the set.
    """

    replace: bool = False
    altids_only: bool = False
    multi_form_domains: frozenset[str] | None = None


class Change(NamedTuple):
    """One edit made to the modification base. ``field`` is a ``FIELD_KEYS``
    key, ``action`` is ``add``, ``replace`` or ``remove``, ``old``/``new`` the
    element's value before and after (None where there is none), ``value`` the
    normalised value the ledger keys on."""

    rule: str
    field: str
    action: str
    old: str | None
    new: str | None
    value: str


class Conflict(NamedTuple):
    """A supplied value withheld because it contradicts the record or itself;
    never written. ``code`` is C5's vocabulary where C5 has the case
    (``ALT_ID_RELATION_CONFLICT``, ``SAME_KIND_CONFLICT``,
    ``MISSING_ALT_ID_TYPE``, ``NON_ASCII_VALUE``), else ``ALT_ID_*``."""

    rule: str
    field: str
    code: str
    detail: str


class Skip(NamedTuple):
    """A supplied value a rule declined, with the reason (e.g. a similar title
    is present, a schema maximum is reached, a Pro flag)."""

    rule: str
    field: str
    reason: str


@dataclass(frozen=True)
class ChangeReport:
    """What ``merge`` did. A contract from v1 (ruled 2026-09-23): MergeTool's
    ``-f json`` output and eidr-wikidata's ledger read it (``as_dict``).

    ``altid_lines`` holds one AltIDTool line per Alt ID rule 18 added,
    composed by ``altidtool_io.format_line`` (rule 18.6; the ``--altids-only``
    report), and is empty when the current record carries no ID.
    """

    changed: bool
    merged_xml: str | None
    changes: tuple[Change, ...] = ()
    conflicts: tuple[Conflict, ...] = ()
    skipped: tuple[Skip, ...] = ()
    altid_lines: tuple[str, ...] = ()
    spec_version: str = SPEC_VERSION

    def as_dict(self) -> dict[str, Any]:
        """The report as plain JSON-ready data (named fields, not tuples)."""
        return {"spec_version": self.spec_version, "changed": self.changed,
                "merged_xml": self.merged_xml,
                "changes": [c._asdict() for c in self.changes],
                "conflicts": [c._asdict() for c in self.conflicts],
                "skipped": [s._asdict() for s in self.skipped],
                "altid_lines": list(self.altid_lines)}


def spec_values_digest() -> str:
    """sha256 of the values merge-rules pins per version: the two knobs, the
    rule order, the held list and the field-key families. tests/
    merge_rules_values_pin.json holds one digest per ``SPEC_VERSION``, so a
    knob or rule change without a version bump fails the suite."""
    values = {"FUZZY_THRESHOLD": FUZZY_THRESHOLD, "FUZZY_THRESHOLD_ORG": FUZZY_THRESHOLD_ORG,
              "RULES": [list(r) for r in RULES], "HELD_RULES": [list(r) for r in HELD_RULES],
              "FIELD_KEYS": sorted(FIELD_KEYS)}
    blob = json.dumps(values, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()


# --------------------------------------------------------------------------
# Comparison classes (section 2)
# --------------------------------------------------------------------------

# CompareString.Compare's punctuation table (StringPunctuation.cs), verbatim
# and in its order: "&" reads "and", dashes become spaces, the rest go.
_PUNCT: tuple[tuple[str, str], ...] = (
    ("&", "and"), ("-", " "), ("‒", " "), ("—", " "), ("～", " "),
    *((c, "") for c in ".。·•…‥,，،、:：;；?"
                       "¿？!¡！\"'‘’“”「」"
                       "﹁﹂『』[]{}()（）【】［］"
                       "«»《》<>/⁄\\|〽"),
)
_SPACES = re.compile(r"\s+")


def _norm(s: object) -> str:
    """The .NET comparison form: diacritics folded (normalize.ascii_fold, the
    portfolio's fold, standing in for the .NET ascii-fold.txt table),
    punctuation per the table above, whitespace collapsed, upper-cased."""
    text = ascii_fold(str(s or ""))
    for a, b in _PUNCT:
        text = text.replace(a, b)
    return _SPACES.sub(" ", text).strip().upper()


def _lev(a: str, b: str) -> int:
    """Levenshtein distance (the .NET LevenshteinDistance2, plain DP)."""
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _distance(a: object, b: object) -> int:
    return _lev(_norm(a), _norm(b))


def _same(a: object, b: object) -> bool:
    """normalized-exact (countries, languages, org IDs, roles)."""
    return _norm(a) == _norm(b)


def _cf(v: object) -> str:
    """exact class: equal after case-fold (controlled vocabularies)."""
    return str(v or "").strip().casefold()


def _low(v: object) -> str:
    """The ledger's value_norm."""
    return str(v or "").strip().lower()


def _strip_nickname(name: str) -> str:
    # CompareEidrRecord.cond_NotDisplayNameFuzzyMatch: the first quoted span
    # is the nickname. An unclosed quote drops only the quote mark (the .NET
    # Substring(-1 + 1) appended the whole name again).
    i = name.find('"')
    if i < 0:
        return name
    j = name.find('"', i + 1)
    return name[:i] + (name[j + 1:] if j >= 0 else name[i + 1:])


def _names_differ(a: str, b: str) -> bool:
    """Director/actor display names, nickname-in-quotes tolerant (the .NET
    three-step test): the full names, then without the quoted nickname, then
    from the first quote on."""
    if _distance(a, b) <= FUZZY_THRESHOLD:
        return False
    if '"' not in a and '"' not in b:
        return True
    if _distance(_strip_nickname(a), _strip_nickname(b)) <= FUZZY_THRESHOLD:
        return False
    tail_a = a.split('"', 1)[1] if '"' in a else a
    tail_b = b.split('"', 1)[1] if '"' in b else b
    return _distance(tail_a, tail_b) > FUZZY_THRESHOLD


def _as_list(v: Any) -> list[Any]:
    if is_absent(v):
        return []
    return list(v) if isinstance(v, list) else [v]


# --------------------------------------------------------------------------
# Schema facts (common.xsd, bundled with mddf_json)
# --------------------------------------------------------------------------

_PATHS = {"base": ("SelfDefinedMetadata", "BaseObjectData"),
          "credits": ("SelfDefinedMetadata", "BaseObjectData", "Credits"),
          "admins": ("SelfDefinedMetadata", "BaseObjectData", "Administrators"),
          "series": ("SelfDefinedMetadata", "ExtraObjectMetadata", "SeriesInfo"),
          "season": ("SelfDefinedMetadata", "ExtraObjectMetadata", "SeasonInfo"),
          "episode": ("SelfDefinedMetadata", "ExtraObjectMetadata", "EpisodeInfo"),
          "sequence": ("SelfDefinedMetadata", "ExtraObjectMetadata", "EpisodeInfo",
                       "SequenceInfo")}


@cache
def _cap(parent: str, child: str) -> float:
    """maxOccurs of ``child`` under ``parent`` in the self-defined schema
    (merge-rules section 2: SCHEMA_MAX from common.xsd, never the .NET caps).
    ``inf`` for unbounded."""
    sch = eidr_schema()
    path = _PATHS[parent]
    typ = sch.element_type(_EIDR + path[0])
    for name in path[1:]:
        typ = sch.content(typ).by_local(name)[0].type
    hits = sch.content(typ).by_local(child)
    if not hits:
        raise RuntimeError(f"the bundled schema has no {child} under {'/'.join(path)}")
    return hits[0].max


def _restriction(type_name: str) -> tuple[list[str], int | None]:
    hit = eidr_schema().types.get(_EIDR + type_name)
    if hit is None:
        return [], None
    node = hit[0]
    pats = [p.get("value", "") for p in node.iter(_XS + "pattern")]
    lengths = [int(m.get("value", "0")) for m in node.iter(_XS + "maxLength")]
    return pats, (min(lengths) if lengths else None)


def _enumeration(type_name: str) -> frozenset[str]:
    hit = eidr_schema().types.get(_EIDR + type_name)
    if hit is None:
        raise RuntimeError(f"{type_name} is not in the bundled EIDR schema")
    return frozenset(e.get("value", "") for e in hit[0].iter(_XS + "enumeration"))


@lru_cache(maxsize=1)
def _alt_id_schema() -> tuple[frozenset[str], dict[str, tuple[list[re.Pattern[str]], int | None]],
                              frozenset[str], int | None, list[re.Pattern[str]]]:
    """Alt ID facts from the schema (section 6: never a hardcoded type list):
    the type names, each named type's value patterns and maxLength, the
    relation vocabulary, the value length every type inherits
    (string1024Type) and the Proprietary domain pattern (constrainedURIType).
    XSD patterns are implicitly anchored, so they are matched in full."""
    types = _enumeration("alternateIDTypeType")
    per_type: dict[str, tuple[list[re.Pattern[str]], int | None]] = {}
    for t in types:
        pats, maxlen = _restriction(t)
        per_type[t] = ([re.compile(p) for p in pats], maxlen)
    _, value_max = _restriction("string1024Type")
    domain_pats, _ = _restriction("constrainedURIType")
    return (types, per_type, _enumeration("alternateIDRelationType"), value_max,
            [re.compile(p) for p in domain_pats])


def _altid_problem(alt: AltId) -> tuple[str, str] | None:
    """Rule 18.7: why this Alt ID cannot be written, or None. Reported, never
    dropped silently. The AltIDTool format checks are altidtool_io's
    ``emission_problem`` (C5's); the rest is the schema's own constraints."""
    problem = emission_problem(AltIdRow("", alt.alt_type, alt.value, alt.domain, alt.relation))
    if problem is not None:
        return problem
    types, per_type, relations, value_max, domain_pats = _alt_id_schema()
    if alt.alt_type not in types:
        return ("ALT_ID_UNKNOWN_TYPE", f"{alt.alt_type!r} is not an Alt ID type of the schema")
    if alt.relation.strip() and alt.relation.strip() not in relations:
        return ("ALT_ID_INVALID_RELATION", f"{alt.relation!r} is not a schema relation")
    if not alt.value.strip():
        return ("ALT_ID_INVALID_VALUE", "empty value")
    if value_max is not None and len(alt.value) > value_max:
        return ("ALT_ID_INVALID_VALUE", f"value longer than {value_max} characters")
    if alt.alt_type == "Proprietary":
        if not alt.domain.strip():
            return ("ALT_ID_MISSING_DOMAIN", "a Proprietary Alt ID needs a domain")
        if domain_pats and not any(p.fullmatch(alt.domain) for p in domain_pats):
            return ("ALT_ID_INVALID_DOMAIN", f"domain {alt.domain!r} fails the schema pattern")
        return None
    pats, maxlen = per_type.get(alt.alt_type, ([], None))
    if maxlen is not None and len(alt.value) > maxlen:
        return ("ALT_ID_INVALID_VALUE", f"{alt.alt_type} value longer than {maxlen} characters")
    if pats and not any(p.fullmatch(alt.value) for p in pats):
        return ("ALT_ID_INVALID_VALUE", f"{alt.value!r} does not match the {alt.alt_type} "
                                        f"pattern of the schema")
    return None


# --------------------------------------------------------------------------
# Reading the two records
# --------------------------------------------------------------------------

_BLOCKS = ("SelfDefinedMetadata", "FullMetadata")


def _parse(xml: str | bytes | ET.Element) -> ET.Element:
    return xml if isinstance(xml, ET.Element) else ET.fromstring(xml)


def _read_supplied(supplied: str | bytes | ET.Element | Mapping[str, Any]) -> dict[str, Any]:
    """The supplied block (SelfDefinedMetadata preferred) in the canonical
    record_from_xml shape.

    A standard record (``bmr_map.record_from_row``, B5: a sheet row read
    sparsely on ``bmr_io.family_layout``) is written with ``record_to_xml``
    and read back, so its Alt IDs get their schema Type and both sides share
    one shape. XML may also be a creation element (``Basic``, ``Episode``...),
    whose children are those of a self-defined block.
    """
    if isinstance(supplied, Mapping):
        view = next((b for b in _BLOCKS if isinstance(supplied.get(b), Mapping)), None)
        if view is None:
            raise ValueError("the supplied record has no SelfDefinedMetadata or FullMetadata")
        supplied = record_to_xml(supplied, view=view)
    root = _parse(supplied)
    try:
        rec = record_from_xml(root)
    except ValueError:
        holder = next((el for el in root.iter()
                       if any(c.tag == _EIDR + "BaseObjectData" for c in el)), None)
        if holder is None:
            raise ValueError("the supplied XML has no BaseObjectData") from None
        wrapped = ET.Element(_EIDR + "SelfDefinedMetadata")
        wrapped.extend(list(holder))
        rec = record_from_xml(wrapped)
    block = rec.get("SelfDefinedMetadata") or rec.get("FullMetadata") or {}
    return dict(block)


def _read_current(current: str | bytes | ET.Element, full: str | bytes | ET.Element | None
                  ) -> tuple[dict[str, Any], dict[str, Any] | None]:
    rec = record_from_xml(_parse(current))
    base = rec.get("SelfDefinedMetadata")
    if not isinstance(base, Mapping):
        # A FullMetadata base would bake inherited values into the record (the
        # .NET tool merged into FullMetadata and submitted it).
        raise ValueError("current must carry SelfDefinedMetadata, the modification base")
    full_block = rec.get("FullMetadata")
    if full is not None:
        full_block = record_from_xml(_parse(full)).get("FullMetadata")
        if full_block is None:
            raise ValueError("full= holds no FullMetadata")
    return copy.deepcopy(dict(base)), (dict(full_block) if full_block else None)


# --------------------------------------------------------------------------
# The working state
# --------------------------------------------------------------------------

@dataclass
class _Ctx:
    bod: dict[str, Any]
    eom: dict[str, Any]
    s_bod: dict[str, Any]
    s_eom: dict[str, Any]
    f_bod: dict[str, Any] | None
    has_parent: bool
    opts: MergeOptions
    changes: list[Change] = field(default_factory=list)
    conflicts: list[Conflict] = field(default_factory=list)
    skipped: list[Skip] = field(default_factory=list)
    removed_rx: set[str] = field(default_factory=set)
    altid_adds: list[AltId] = field(default_factory=list)
    _mfd: frozenset[str] | None = None
    _mfd_read: bool = False

    def change(self, rule: str, key: str, action: str, old: Any, new: Any, value: Any) -> None:
        self.changes.append(Change(rule, key, action, None if old is None else str(old),
                                   None if new is None else str(new), _low(value)))

    def skip(self, rule: str, key: str, reason: str) -> None:
        self.skipped.append(Skip(rule, key, reason))

    def conflict(self, rule: str, key: str, code: str, detail: str) -> None:
        self.conflicts.append(Conflict(rule, key, code, detail))

    def mfd(self) -> frozenset[str]:
        # Read once and only when a Proprietary identity value needs rule 6,
        # so a vendored copy without the set fails only where it matters.
        if not self._mfd_read:
            self._mfd = (self.opts.multi_form_domains if self.opts.multi_form_domains is not None
                         else multi_form_domains())
            self._mfd_read = True
        return self._mfd or frozenset()


def _full_cap_reached(ctx: _Ctx, rule: str, key: str, have: int, cap: float) -> bool:
    if have >= cap:
        ctx.skip(rule, key, f"schema maximum {int(cap)} reached")
        return True
    return False


# -- titles ----------------------------------------------------------------

def _title_text(t: Any) -> str:
    return str(t.get("Title") if isinstance(t, Mapping) else t or "")


def _titles(bod: Mapping[str, Any]) -> tuple[list[Any], list[Any]]:
    """(main titles, alternates) as the record holds them (ResourceName is a
    list whose entry 0 is the main title)."""
    return _as_list(bod.get("ResourceName")), _as_list(bod.get("AlternateResourceName"))


def _pre_titles(ctx: _Ctx) -> None:
    """pre.1: alternates equal (normalized-exact) to the main title or to an
    earlier alternate go. The .NET compared against EVERY earlier sibling
    (ID, Mode, ReferentType included), so an alternate "Movie" would have
    been removed beside ReferentType Movie; only titles count here."""
    mains, alts = _titles(ctx.bod)
    seen = {_norm(_title_text(t)) for t in mains}
    kept = []
    for t in alts:
        n = _norm(_title_text(t))
        if n in seen:
            ctx.change("pre.1", "title:alternate", "remove", _title_text(t), None, _title_text(t))
            continue
        seen.add(n)
        kept.append(t)
    if len(kept) != len(alts):
        _set(ctx.bod, "AlternateResourceName", kept)


def _sub(d: dict[str, Any], key: str) -> dict[str, Any]:
    """``d[key]`` when it is a dict (edited in place), else a new empty one
    the caller stores back with ``_set``."""
    v = d.get(key)
    return v if isinstance(v, dict) else {}


def _set(d: dict[str, Any], key: str, value: Any) -> None:
    if is_absent(value):
        d.pop(key, None)
    else:
        d[key] = value


def _dedupe(ctx: _Ctx, rule: str, key: str, items: list[Any],
            ident: Callable[[Any], str | None], show: Callable[[Any], str]) -> list[Any]:
    seen: set[str] = set()
    kept = []
    for it in items:
        k = ident(it)
        if k is not None and k in seen:
            ctx.change(rule, key, "remove", show(it), None, show(it))
            continue
        if k is not None:
            seen.add(k)
        kept.append(it)
    return kept


def _person_name(p: Any) -> str:
    return str(p.get("DisplayName") or "") if isinstance(p, Mapping) else str(p or "")


def _pre_credits(role: str, rule: str) -> Callable[[_Ctx], None]:
    def run(ctx: _Ctx) -> None:
        credits = ctx.bod.get("Credits")
        if not isinstance(credits, dict):
            return
        people = _as_list(credits.get(role))
        kept = _dedupe(ctx, rule, role.lower(), people, lambda p: _norm(_person_name(p)),
                       _person_name)
        if len(kept) != len(people):
            _set(credits, role, kept)
            _set(ctx.bod, "Credits", credits)
    return run


def _org_show(o: Mapping[str, Any]) -> str:
    return str(o.get("DisplayName") or o.get("_organizationID") or "")


def _pre_orgs(ctx: _Ctx) -> None:
    """pre.4: a repeated (role, party ID) among EIDR-party-ID orgs; an org
    without one is never a duplicate (the .NET gave it a fresh GUID)."""
    orgs = _as_list(ctx.bod.get("AssociatedOrg"))

    def ident(o: Any) -> str | None:
        if not isinstance(o, Mapping) or o.get("_idType") != "EIDRPartyID":
            return None
        return _norm(f"{o.get('_role') or ''}{o.get('_organizationID') or ''}")

    kept = []
    seen: set[str] = set()
    for o in orgs:
        k = ident(o)
        if k is not None and k in seen:
            ctx.change("pre.4", f"associated_org:{_low(o.get('_role'))}", "remove", _org_show(o),
                       None, o.get("_organizationID") or _org_show(o))
            continue
        if k is not None:
            seen.add(k)
        kept.append(o)
    if len(kept) != len(orgs):
        _set(ctx.bod, "AssociatedOrg", kept)


def _pre_authorities(ctx: _Ctx) -> None:
    adm = ctx.bod.get("Administrators")
    if not isinstance(adm, dict):
        return
    mas = _as_list(adm.get("MetadataAuthority"))
    kept = _dedupe(ctx, "pre.5", "metadata_authority", mas, _norm, str)
    if len(kept) != len(mas):
        _set(adm, "MetadataAuthority", kept)


def _pre_countries(ctx: _Ctx) -> None:
    """pre.6 CleanCountryOfOrigin, verbatim: a lone AQ becomes XX; with more
    than one country, every XX goes."""
    coo = _as_list(ctx.bod.get("CountryOfOrigin"))
    if len(coo) == 1 and coo[0] == "AQ":
        ctx.bod["CountryOfOrigin"] = ["XX"]
        ctx.change("pre.6", "country_of_origin", "replace", "AQ", "XX", "XX")
    elif len(coo) > 1 and "XX" in coo:
        for _ in range(coo.count("XX")):
            ctx.change("pre.6", "country_of_origin", "remove", "XX", None, "XX")
        _set(ctx.bod, "CountryOfOrigin", [c for c in coo if c != "XX"])


def _pre_structural(ctx: _Ctx) -> None:
    """pre.7 CleanStructuralType, verbatim: a Season or Series is an
    Abstraction, and so is a record whose SeasonInfo names no Parent."""
    st = ctx.bod.get("StructuralType")
    if st is None:
        return
    season = ctx.eom.get("SeasonInfo")
    abstraction = (ctx.bod.get("ReferentType") in ("Season", "Series")
                   or (isinstance(season, Mapping) and is_absent(season.get("Parent"))))
    if abstraction and st != "Abstraction":
        ctx.bod["StructuralType"] = "Abstraction"
        ctx.change("pre.7", "structural_type", "replace", st, "Abstraction", "Abstraction")


# -- rules 1 and 3 ----------------------------------------------------------

def _rule1(ctx: _Ctx) -> None:
    """ReplaceTitleLanguage: an EIDR title whose lang is ``und`` takes the
    lang of a supplied title (main or alternate) with a real lang and the
    same normalized text; the first such supplied title wins."""
    s_titles = [t for group in _titles(ctx.s_bod) for t in group if isinstance(t, Mapping)]
    mains, alts = _titles(ctx.bod)
    for key, group in (("title_language:primary", mains), ("title_language:alternate", alts)):
        for t in group:
            if not isinstance(t, dict) or t.get("_lang") != "und":
                continue
            for s in s_titles:
                lang = s.get("_lang")
                if lang and lang != "und" and _same(_title_text(t), _title_text(s)):
                    t["_lang"] = lang
                    ctx.change("1", key, "replace", "und", lang, _title_text(t))
                    break


def _rule3(ctx: _Ctx) -> None:
    """AddMissingTitle: each supplied title (main, then alternates) that is
    fuzzy-different from EVERY EIDR title, the ones this rule already added
    included, becomes an alternate. A near match (distance 1 to
    FUZZY_THRESHOLD) is reported as skipped; an exact one is silent."""
    mains, alts = _titles(ctx.bod)
    cap = _cap("base", "AlternateResourceName")
    added = False
    for s in [t for group in _titles(ctx.s_bod) for t in group]:
        if not isinstance(s, Mapping) or s.get("SystemGenerated"):
            continue      # a generated title is the registry's, never supplied data
        text = _title_text(s)
        dists = [_distance(text, _title_text(t)) for t in mains + alts]
        if dists and min(dists) <= FUZZY_THRESHOLD:
            if min(dists) > 0:
                ctx.skip("3", "title:alternate", f"similar title present: {text!r}")
            continue
        if _full_cap_reached(ctx, "3", "title:alternate", len(alts), cap):
            continue
        new = {k: v for k, v in (("Title", text), ("TitleClass", s.get("TitleClass")),
                                 ("_lang", s.get("_lang"))) if not is_absent(v)}
        alts.append(new)
        added = True
        ctx.change("3", "title:alternate", "add", None, text, text)
    if added:
        ctx.bod["AlternateResourceName"] = alts


# -- rules 8 to 10 -----------------------------------------------------------

def _rule8(ctx: _Ctx) -> None:
    """AddMissingCountryOfOrigin: supplied codes not present (normalized-
    exact) are added, a supplied XX never (the .NET cond_CountryMismatch);
    then XX goes when anything else is listed."""
    coo = _as_list(ctx.bod.get("CountryOfOrigin"))
    cap = _cap("base", "CountryOfOrigin")
    for c in _as_list(ctx.s_bod.get("CountryOfOrigin")):
        if _norm(c) == "XX" or any(_same(c, e) for e in coo):
            continue
        if _full_cap_reached(ctx, "8", "country_of_origin", len(coo), cap):
            continue
        coo.append(c)
        ctx.change("8", "country_of_origin", "add", None, c, c)
    if "XX" in coo and len(coo) > 1:
        for _ in range(coo.count("XX")):
            ctx.change("8", "country_of_origin", "remove", "XX", None, "XX")
        coo = [c for c in coo if c != "XX"]
    _set(ctx.bod, "CountryOfOrigin", coo)


def _lang_parts(entry: Any) -> tuple[str, str]:
    if isinstance(entry, Mapping):
        return str(entry.get("value") or ""), str(entry.get("_mode") or "")
    return str(entry or ""), ""


def _lang_show(entry: Any) -> str:
    code, mode = _lang_parts(entry)
    return f"{code} ({mode})" if mode else code


def _lang_value(entry: Any) -> str:
    code, mode = _lang_parts(entry)
    return f"{code}|{mode}" if mode else code


def _languages(name: str, rule: str, key: str) -> Callable[[_Ctx], None]:
    def run(ctx: _Ctx) -> None:
        """Add supplied (code, mode) pairs not present (code normalized-exact,
        mode exact); a supplied ``und`` never (cond_OriginalLanguageMatch).
        Then, within each mode, ``und`` goes when another language is listed,
        and so does ``zxx``: a silent Audio track beside English intertitles
        keeps both."""
        langs = _as_list(ctx.bod.get(name))
        cap = _cap("base", name)
        for s in _as_list(ctx.s_bod.get(name)):
            code, mode = _lang_parts(s)
            if not code or _norm(code) == "UND":
                continue
            if any(_same(code, _lang_parts(e)[0]) and _cf(mode) == _cf(_lang_parts(e)[1])
                   for e in langs):
                continue
            if _full_cap_reached(ctx, rule, key, len(langs), cap):
                continue
            langs.append(copy.deepcopy(s))
            ctx.change(rule, key, "add", None, _lang_show(s), _lang_value(s))
        by_mode: dict[str, list[str]] = {}
        for e in langs:
            code, mode = _lang_parts(e)
            by_mode.setdefault(_cf(mode), []).append(_cf(code))
        kept = []
        for e in langs:
            code, mode = _lang_parts(e)
            codes = by_mode[_cf(mode)]
            if _cf(code) in ("und", "zxx") and any(c != _cf(code) for c in codes):
                ctx.change(rule, key, "remove", _lang_show(e), None, _lang_value(e))
                continue
            kept.append(e)
        _set(ctx.bod, name, kept)
    return run


# -- rule 11 ------------------------------------------------------------------

def _org_matches(e: Mapping[str, Any], s: Mapping[str, Any]) -> bool:
    """cond_OrgsDontMatch, inverted, with org names on FUZZY_THRESHOLD_ORG as
    the spec says (the .NET used FUZZY_THRESHOLD when both sides named the
    org and only the supplied one had an ID). Roles must agree first."""
    if not _same(e.get("_role"), s.get("_role")):
        return False
    s_id, s_name = s.get("_organizationID"), s.get("DisplayName")
    e_id, e_name = e.get("_organizationID"), e.get("DisplayName")
    if s_id and e_id:
        return _same(s_id, e_id)
    if s_name and e_name:
        return _distance(s_name, e_name) <= FUZZY_THRESHOLD_ORG
    return False


def _rule11(ctx: _Ctx) -> None:
    orgs = _as_list(ctx.bod.get("AssociatedOrg"))
    cap = _cap("base", "AssociatedOrg")
    for s in _as_list(ctx.s_bod.get("AssociatedOrg")):
        if not isinstance(s, Mapping) or not (s.get("_organizationID") or s.get("DisplayName")):
            continue
        key = f"associated_org:{_low(s.get('_role'))}"
        if any(isinstance(e, Mapping) and _org_matches(e, s) for e in orgs):
            continue
        if _full_cap_reached(ctx, "11", key, len(orgs), cap):
            continue
        orgs.append(copy.deepcopy(dict(s)))
        ctx.change("11", key, "add", None, _org_show(s), s.get("_organizationID") or _org_show(s))
    _set(ctx.bod, "AssociatedOrg", orgs)


# -- rules 12 and 13 ----------------------------------------------------------

def _credits_rule(role: str, rule: str) -> Callable[[_Ctx], None]:
    def run(ctx: _Ctx) -> None:
        s_credits = ctx.s_bod.get("Credits")
        if not isinstance(s_credits, Mapping):
            return
        credits = _sub(ctx.bod, "Credits")
        people = _as_list(credits.get(role))
        cap = _cap("credits", role)
        for s in _as_list(s_credits.get(role)):
            name = _person_name(s)
            if not name or not all(_names_differ(name, _person_name(e)) for e in people):
                continue
            if _full_cap_reached(ctx, rule, role.lower(), len(people), cap):
                continue
            people.append(copy.deepcopy(dict(s)))
            ctx.change(rule, role.lower(), "add", None, name, name)
        _set(credits, role, people)
        _set(ctx.bod, "Credits", credits)
    return run


# -- rule 14 ------------------------------------------------------------------

def _rule14(ctx: _Ctx) -> None:
    s = ctx.s_bod.get("Status")
    if s and _cf(s) != _cf(ctx.bod.get("Status")):
        ctx.skip("14", "status", "rule 14 is skipped: the registry will not allow it")


# -- rules 15 and 17: RegistrantExtra ------------------------------------------

def _rx_pairs(text: Any) -> list[tuple[str, str, bool]]:
    """RegistrantExtra as (key, value, had_colon) per semicolon-terminated
    token, in order."""
    out = []
    for tok in str(text or "").split(";"):
        tok = tok.strip()
        if not tok:
            continue
        k, colon, v = tok.partition(":")
        out.append((k.strip(), v.strip(), bool(colon)))
    return out


def _rx_text(pairs: list[tuple[str, str, bool]]) -> str | None:
    if not pairs:
        return None
    return " ".join(f"{k}:{v};" if c else f"{k};" for k, v, c in pairs)


def _has_pro(text: Any, key: str) -> bool:
    return any(_cf(k) == key and _cf(v) == "pro" for k, v, _ in _rx_pairs(text))


def _referent_switch(ctx: _Ctx, length: str) -> None:
    """Rule 15 preserves ReferentType (the .NET overwrote it from the sheet,
    section 6), except Movie under 45 minutes becomes Short and Short at 45
    or more becomes Movie."""
    minutes = parse_minutes(length)
    rt = ctx.bod.get("ReferentType")
    if minutes is None or rt not in ("Movie", "Short"):
        return
    new = rt
    if rt == "Movie" and minutes < 45:
        new = "Short"
    elif rt == "Short" and minutes >= 45:
        new = "Movie"
    if new != rt:
        ctx.bod["ReferentType"] = new
        ctx.change("15", "referent_type", "replace", rt, new, new)


def _same_length(a: Any, b: Any) -> bool:
    ma, mb = parse_minutes(a), parse_minutes(b)
    return (ma is not None and mb is not None and abs(ma - mb) < 1e-9) or _cf(a) == _cf(b)


def _rule15(ctx: _Ctx) -> None:
    """ReplaceApproxLength as ruled (sections 3 and 4): add when the record
    has no length, self-defined or inherited; replace an ``AL:Pro;``-flagged
    one with an unflagged supplied one and drop the flag; never bring in a
    supplied ``AL:Pro;`` length. The .NET round-figure replacement (10, 15,
    30, 60, 90 or 120 minutes replaced by a non-round supplied value) is not
    part of the ruled rule and is not carried."""
    s_len = ctx.s_bod.get("ApproximateLength")
    if is_absent(s_len):
        return
    s_pro = _has_pro(ctx.s_bod.get("RegistrantExtra"), "al")
    e_len = ctx.bod.get("ApproximateLength")
    key = "approximate_length"
    if not is_absent(e_len):
        if _same_length(e_len, s_len):
            return
        if s_pro:
            ctx.skip("15", key, "supplied length is flagged AL:Pro;: the existing length is "
                                "retained (section 4)")
            return
        if not _has_pro(ctx.bod.get("RegistrantExtra"), "al"):
            return
        ctx.bod["ApproximateLength"] = s_len
        ctx.change("15", key, "replace", e_len, s_len, s_len)
        pairs = _rx_pairs(ctx.bod.get("RegistrantExtra"))
        kept = [p for p in pairs if not (_cf(p[0]) == "al" and _cf(p[1]) == "pro")]
        for k, v, _ in pairs:
            if _cf(k) == "al" and _cf(v) == "pro":
                ctx.change("15", "registrant_extra:al", "remove", f"{k}:{v};", None, v)
        ctx.removed_rx.add("al")
        _set(ctx.bod, "RegistrantExtra", _rx_text(kept))
        _referent_switch(ctx, str(s_len))
        return
    inherited = ctx.f_bod.get("ApproximateLength") if ctx.f_bod else None
    if not is_absent(inherited):
        if not _same_length(inherited, s_len):
            ctx.skip("15", key, "the record inherits its length, and an inherited value counts "
                                "as present (section 4.2)")
        return
    if ctx.has_parent and ctx.f_bod is None:
        ctx.skip("15", key, "the record has a parent and no FullMetadata was given, so whether "
                            "it inherits a length is unknown (section 4.2)")
        return
    if s_pro:
        ctx.skip("15", key, "supplied length is flagged AL:Pro;: never brought in (section 4)")
        return
    ctx.bod["ApproximateLength"] = s_len
    ctx.change("15", key, "add", None, s_len, s_len)
    _referent_switch(ctx, str(s_len))


def _rule16(ctx: _Ctx) -> None:
    """AddMissingDescription: the description AND its language, or nothing
    (one is invalid without the other)."""
    s = ctx.s_bod.get("Description")
    if not isinstance(s, Mapping) or is_absent(s.get("Description")):
        return
    if isinstance(ctx.bod.get("Description"), Mapping):
        return
    lang = s.get("_lang")
    key = f"description:{_low(lang)}"
    if is_absent(lang):
        ctx.skip("16", key, "supplied description has no language; one is invalid without "
                            "the other")
        return
    ctx.bod["Description"] = {"Description": s["Description"], "_lang": lang}
    ctx.change("16", key, "add", None, s["Description"], s["Description"])


def _rule17(ctx: _Ctx) -> None:
    """AddMissingRegistrantExtra: supplied pairs whose key the record lacks
    are added. A supplied ``RD:Pro;`` or ``AL:Pro;`` is never copied (it
    describes the supplied value, which rules 4 to 6 and 15 declined), and a
    key another rule removed in this merge is not put back."""
    pairs = _rx_pairs(ctx.bod.get("RegistrantExtra"))
    have = {_cf(k): v for k, v, _ in pairs}
    added = False
    for k, v, colon in _rx_pairs(ctx.s_bod.get("RegistrantExtra")):
        key = f"registrant_extra:{_low(k)}"
        if _cf(k) in ("rd", "al") and _cf(v) == "pro":
            ctx.skip("17", key, f"{k}:{v}; describes the supplied value: never copied "
                                f"(section 4)")
            continue
        if _cf(k) in ctx.removed_rx:
            ctx.skip("17", key, "removed by another rule in this merge; not put back")
            continue
        if _cf(k) in have:
            if _cf(have[_cf(k)]) != _cf(v):
                ctx.skip("17", key, "the record has this key with another value")
            continue
        pairs.append((k, v, colon))
        have[_cf(k)] = v
        added = True
        ctx.change("17", key, "add", None, f"{k}:{v};" if colon else f"{k};", v)
    if added:
        _set(ctx.bod, "RegistrantExtra", _rx_text(pairs))


# -- rules 18a and 18 ----------------------------------------------------------

def _rule18a(ctx: _Ctx) -> None:
    """AddMissingMetadataAuthority (restored; the .NET call was commented
    out): party IDs not present, to the schema maximum."""
    s_adm = ctx.s_bod.get("Administrators")
    if not isinstance(s_adm, Mapping):
        return
    adm = _sub(ctx.bod, "Administrators")
    mas = _as_list(adm.get("MetadataAuthority"))
    cap = _cap("admins", "MetadataAuthority")
    for m in _as_list(s_adm.get("MetadataAuthority")):
        if any(_cf(m) == _cf(e) for e in mas):
            continue
        if _full_cap_reached(ctx, "18a", "metadata_authority", len(mas), cap):
            continue
        mas.append(m)
        ctx.change("18a", "metadata_authority", "add", None, m, m)
    _set(adm, "MetadataAuthority", mas)
    _set(ctx.bod, "Administrators", adm)


def _alt(entry: Mapping[str, Any], source: str = "") -> AltId:
    return AltId(str(entry.get("Type") or ""), str(entry.get("Domain") or ""),
                 str(entry.get("AltID") or ""), str(entry.get("Relation") or ""), source)


def _altid_key(alt: AltId) -> str:
    return f"alt_id:{alt.alt_type.lower()}|{alt.domain.lower()}"


def _rule18(ctx: _Ctx) -> None:
    """AddMissingAlternateID: BMRtoAltID's rules (section 3.1), relation-aware
    as C5 ``altid_audit`` is since 2026-11-24, on C5's own helpers.

    In order, per supplied Alt ID: 18.7 validation; an exact repeat is kept
    once, and one Kind+value offered under two relations withholds every copy
    (``ALT_ID_RELATION_CONFLICT``); rule 6 (18.5) withholds every identity
    value of a single-form Kind when the supplied record offers two, or when
    the record already claims a different one (``SAME_KIND_CONFLICT``; the
    Kinds ``multi_form_domains`` declares are exempt); then presence (18.2 to
    18.4): the same Kind+value under the same relation (blank = IsSameAs) is
    skipped silently, under another relation it is a conflict. The rest is
    added, and each conflict holds back only its own Alt ID.
    """
    supplied = [_alt(e, f"AlternateID {i}")
                for i, e in enumerate(_as_list(ctx.s_bod.get("AlternateID")), 1)
                if isinstance(e, Mapping)]
    if not supplied:
        return
    current = _as_list(ctx.bod.get("AlternateID"))
    held: dict[tuple[str, str, str], set[str]] = {}
    for e in current:
        if isinstance(e, Mapping):
            a = _alt(e)
            held.setdefault(kind_key(a), set()).add(a.relation)

    valid = []
    for alt in supplied:
        problem = _altid_problem(alt)
        if problem is not None:
            ctx.conflict("18", _altid_key(alt), problem[0], f"{alt.value!r}: {problem[1]}")
        else:
            valid.append(alt)

    # Exact repeats kept once; one value under two relations: every copy out.
    seen: set[tuple[tuple[str, str, str], str]] = set()
    relations: dict[tuple[str, str, str], set[str]] = {}
    unique: list[AltId] = []
    for alt in valid:
        rel = _norm_relation(alt.relation)
        relations.setdefault(kind_key(alt), set()).add(rel)
        if (kind_key(alt), rel) not in seen:
            seen.add((kind_key(alt), rel))
            unique.append(alt)
    split = {k for k, rels in relations.items() if len(rels) > 1}
    withheld: set[tuple[str, str, str]] = set()
    for alt in unique:
        if kind_key(alt) in split:
            ctx.conflict("18", _altid_key(alt), "ALT_ID_RELATION_CONFLICT",
                         f"{alt.value!r} is offered under more than one relation; every copy "
                         f"withheld (18.4)")
            withheld.add(kind_key(alt))

    def single(a: AltId) -> bool:
        return is_single_form(a, ctx.mfd() if a.alt_type == "Proprietary" else None)

    identity = [a for a in unique if is_audited(a) and kind_key(a) not in split]
    by_kind: dict[tuple[str, str], set[str]] = {}
    for a in identity:
        if single(a):
            by_kind.setdefault(a.kind, set()).add(a.value)
    on_record: dict[tuple[str, str], set[str]] = {}
    for (t, d, v), rels in held.items():
        if any(is_audited(AltId(t, d, v, r)) for r in rels):
            on_record.setdefault((t, d), set()).add(v)
    for a in identity:
        if not single(a):
            continue
        if len(by_kind.get(a.kind, ())) > 1:
            ctx.conflict("18", _altid_key(a), "SAME_KIND_CONFLICT",
                         f"{a.value!r}: the supplied record offers "
                         f"{len(by_kind[a.kind])} identity values of one single-form Kind "
                         f"({', '.join(sorted(by_kind[a.kind]))}); withheld (18.5)")
            withheld.add(kind_key(a))
        elif on_record.get(a.kind) and a.value not in on_record[a.kind]:
            ctx.conflict("18", _altid_key(a), "SAME_KIND_CONFLICT",
                         f"{a.value!r}: the record already claims "
                         f"{', '.join(sorted(on_record[a.kind]))} as this Kind's identity; "
                         f"withheld (18.5)")
            withheld.add(kind_key(a))

    added = False
    for alt in unique:
        if kind_key(alt) in withheld:
            continue
        present = held.get(kind_key(alt))
        if present is not None:
            if not same_relation(present, alt.relation):
                ctx.conflict("18", _altid_key(alt), "ALT_ID_RELATION_CONFLICT",
                             f"{alt.value!r} is on the record under relation "
                             f"{', '.join(sorted(r or 'IsSameAs' for r in present))}; the "
                             f"supplied record says {alt.relation.strip() or 'IsSameAs'} (18.4)")
            continue
        entry = {k: v for k, v in (("AltID", alt.value), ("Type", alt.alt_type),
                                   ("Domain", alt.domain or None),
                                   ("Relation", alt.relation.strip() or None)) if v is not None}
        current.append(entry)
        held.setdefault(kind_key(alt), set()).add(alt.relation)
        ctx.altid_adds.append(alt)
        added = True
        ctx.change("18", _altid_key(alt), "add", None, alt.value, alt.value)
    if added:
        ctx.bod["AlternateID"] = current


# -- rules 19 to 28: episodic info ----------------------------------------------

def _info(eom: Mapping[str, Any], name: str) -> dict[str, Any] | None:
    v = eom.get(name)
    return v if isinstance(v, dict) else None


def _rule19(ctx: _Ctx) -> None:
    s = _info(ctx.s_eom, "SeriesInfo") or {}
    e = _info(ctx.eom, "SeriesInfo") or {}
    flags = ("NumberRequired", "DateRequired", "OriginalTitleRequired")
    if any(not is_absent(s.get(f)) and _cf(s.get(f)) != _cf(e.get(f)) for f in flags):
        ctx.skip("19", "series_info", "rule 19 is skipped: SeriesInfo flags must already "
                                      "exist on a Series")


def _series(ctx: _Ctx) -> dict[str, Any] | None:
    """The record's SeriesInfo, created empty on a Series that lacks one."""
    info = _info(ctx.eom, "SeriesInfo")
    if info is None and ctx.bod.get("ReferentType") == "Series":
        info = {}
    return info


def _store(ctx: _Ctx, name: str, info: dict[str, Any]) -> None:
    _set(ctx.eom, name, info)


def _rule20(ctx: _Ctx) -> None:
    s_classes = _as_list((_info(ctx.s_eom, "SeriesInfo") or {}).get("SeriesClass"))
    info = _series(ctx)
    if not s_classes or info is None or not is_absent(info.get("SeriesClass")):
        return
    cap = _cap("series", "SeriesClass")
    out: list[Any] = []
    for c in s_classes:
        if any(_cf(c) == _cf(o) for o in out):
            continue
        if _full_cap_reached(ctx, "20", "series_class", len(out), cap):
            continue
        out.append(c)
        ctx.change("20", "series_class", "add", None, c, c)
    # SeriesClass occurs once in the schema; record_to_xml writes a scalar.
    info["SeriesClass"] = out[0] if cap == 1 else out
    _store(ctx, "SeriesInfo", info)


def _rule21(ctx: _Ctx) -> None:
    """AddMissingEndDate, as ruled; the .NET condition null-dereferenced
    (``ssi == null && ssi.Element(...)``) and never fired."""
    end = (_info(ctx.s_eom, "SeriesInfo") or {}).get("EndDate")
    info = _series(ctx)
    if is_absent(end) or info is None or not is_absent(info.get("EndDate")):
        return
    info["EndDate"] = end
    _store(ctx, "SeriesInfo", info)
    ctx.change("21", "end_date", "add", None, end, end)


def _rule22(ctx: _Ctx) -> None:
    n = (_info(ctx.s_eom, "SeasonInfo") or {}).get("SequenceNumber")
    info = _info(ctx.eom, "SeasonInfo")
    if is_absent(n) or info is None or not is_absent(info.get("SequenceNumber")):
        return
    info["SequenceNumber"] = n
    ctx.change("22", "season_number", "add", None, n, n)


def _classes_rule(rule: str, info_name: str, cls: str, key: str,
                  parent: str) -> Callable[[_Ctx], None]:
    def run(ctx: _Ctx) -> None:
        """Every supplied class not present (exact) is added; the .NET season
        condition copied the season-NUMBER test and never ran (section 6)."""
        info = _info(ctx.eom, info_name)
        s_classes = _as_list((_info(ctx.s_eom, info_name) or {}).get(cls))
        if info is None or not s_classes:
            return
        have = _as_list(info.get(cls))
        cap = _cap(parent, cls)
        for c in s_classes:
            if any(_cf(c) == _cf(h) for h in have):
                continue
            if _full_cap_reached(ctx, rule, key, len(have), cap):
                continue
            have.append(c)
            ctx.change(rule, key, "add", None, c, c)
        _set(info, cls, have)
    return run


def _number(v: Any) -> tuple[str, str]:
    if isinstance(v, Mapping):
        return str(v.get("Number") or ""), str(v.get("Domain") or "")
    return str(v or ""), ""


def _sequence_rule(rule: str, name: str, key: str) -> Callable[[_Ctx], None]:
    def run(ctx: _Ctx) -> None:
        info = _info(ctx.eom, "EpisodeInfo")
        s_seq = (_info(ctx.s_eom, "EpisodeInfo") or {}).get("SequenceInfo")
        s_val = s_seq.get(name) if isinstance(s_seq, Mapping) else None
        if info is None or is_absent(s_val) or not _number(s_val)[0]:
            return
        seq = _sub(info, "SequenceInfo")
        if not is_absent(seq.get(name)):
            return
        seq[name] = copy.deepcopy(s_val)
        info["SequenceInfo"] = seq
        num, dom = _number(s_val)
        ctx.change(rule, f"{key}:{dom.lower()}", "add", None, num, num)
    return run


def _rule27(ctx: _Ctx) -> None:
    """AddMissingAlternateNumbers: a (number, domain) pair not present,
    case-insensitive, up to the schema maximum (the .NET capped at 1)."""
    info = _info(ctx.eom, "EpisodeInfo")
    s_seq = (_info(ctx.s_eom, "EpisodeInfo") or {}).get("SequenceInfo")
    s_nums = _as_list(s_seq.get("AlternateNumber")) if isinstance(s_seq, Mapping) else []
    if info is None or not s_nums:
        return
    seq = _sub(info, "SequenceInfo")
    have = _as_list(seq.get("AlternateNumber"))
    cap = _cap("sequence", "AlternateNumber")
    for n in s_nums:
        num, dom = _number(n)
        key = f"alternate_number:{dom.lower()}"
        if not num or any((_cf(num), _cf(dom)) == tuple(map(_cf, _number(h))) for h in have):
            continue
        if _full_cap_reached(ctx, "27", key, len(have), cap):
            continue
        have.append(copy.deepcopy(n))
        ctx.change("27", key, "add", None, num, num)
    if have:
        seq["AlternateNumber"] = have
        info["SequenceInfo"] = seq


def _rule28(ctx: _Ctx) -> None:
    slot = (_info(ctx.s_eom, "EpisodeInfo") or {}).get("TimeSlot")
    info = _info(ctx.eom, "EpisodeInfo")
    if is_absent(slot) or info is None or not is_absent(info.get("TimeSlot")):
        return
    info["TimeSlot"] = slot
    ctx.change("28", "time_slot", "add", None, slot, slot)


# The pipeline, in RULES order. Kept as a table the conformance test can
# disable one entry of, to prove each fixture fails without its rule.
_PIPELINE: dict[str, Callable[[_Ctx], None]] = {
    "pre.1": _pre_titles,
    "pre.2": _pre_credits("Director", "pre.2"),
    "pre.3": _pre_credits("Actor", "pre.3"),
    "pre.4": _pre_orgs,
    "pre.5": _pre_authorities,
    "pre.6": _pre_countries,
    "pre.7": _pre_structural,
    "1": _rule1,
    "3": _rule3,
    "8": _rule8,
    "9": _languages("OriginalLanguage", "9", "original_language"),
    "10": _languages("VersionLanguage", "10", "version_language"),
    "11": _rule11,
    "12": _credits_rule("Director", "12"),
    "13": _credits_rule("Actor", "13"),
    "14": _rule14,
    "15": _rule15,
    "16": _rule16,
    "17": _rule17,
    "18a": _rule18a,
    "18": _rule18,
    "19": _rule19,
    "20": _rule20,
    "21": _rule21,
    "22": _rule22,
    "23": _classes_rule("23", "SeasonInfo", "SeasonClass", "season_class", "season"),
    "24": _classes_rule("24", "EpisodeInfo", "EpisodeClass", "episode_class", "episode"),
    "25": _sequence_rule("25", "DistributionNumber", "distribution_number"),
    "26": _sequence_rule("26", "HouseSequence", "house_sequence"),
    "27": _rule27,
    "28": _rule28,
}


def merge(current: str | bytes | ET.Element,
          supplied: str | bytes | ET.Element | Mapping[str, Any],
          options: MergeOptions | None = None, *,
          full: str | bytes | ET.Element | None = None) -> ChangeReport:
    """Merge ``supplied`` into ``current`` under merge-rules 1.0.0.

    ``current`` is the registry's XML for the record: it must hold a
    ``SelfDefinedMetadata`` (the modification base) and may also hold the
    ``FullMetadata`` (a resolve message carrying both), which rule 15 uses to
    decide whether a value is inherited; ``full`` gives the FullMetadata
    separately. ``supplied`` is XML (a self-defined or full block, or a
    creation element such as ``Basic``) or a standard record
    (``bmr_map.record_from_row``). Returns a ``ChangeReport``; ``merged_xml``
    is None when nothing changed. Raises ``ValueError`` for
    ``options.replace`` (held, section 5) and for input without the blocks
    named above.
    """
    opts = options or MergeOptions()
    if opts.replace:
        raise ValueError("the replace-class rules (2, 4, 5, 6, 7) are held for the operator's "
                         "review (merge-rules.md section 5); merge add-only")
    base, full_block = _read_current(current, full)
    s_block = _read_supplied(supplied)
    bod = base.setdefault("BaseObjectData", {})
    eom = _sub(base, "ExtraObjectMetadata")
    ctx = _Ctx(
        bod=bod, eom=eom,
        s_bod=dict(s_block.get("BaseObjectData") or {}),
        s_eom=dict(s_block.get("ExtraObjectMetadata") or {}),
        f_bod=dict(full_block.get("BaseObjectData") or {}) if full_block else None,
        has_parent=any(isinstance(v, Mapping) and not is_absent(v.get("Parent"))
                       for v in eom.values()),
        opts=opts)
    steps = ["18"] if opts.altids_only else [r[0] for r in RULES]
    for rule in steps:
        _PIPELINE[rule](ctx)
    _set(base, "ExtraObjectMetadata", ctx.eom)
    changed = bool(ctx.changes)
    eidr_id = str(bod.get("ID") or "")
    lines = tuple(format_line(eidr_id, a.alt_type, a.value,
                              a.domain if a.alt_type == "Proprietary" else "", a.relation.strip())
                  for a in ctx.altid_adds) if eidr_id else ()
    return ChangeReport(
        changed=changed,
        merged_xml=record_to_xml({"SelfDefinedMetadata": base}) if changed else None,
        changes=tuple(ctx.changes), conflicts=tuple(ctx.conflicts),
        skipped=tuple(ctx.skipped), altid_lines=lines)
