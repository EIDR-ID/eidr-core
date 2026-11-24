"""Full-record construction: what a child inherits from its parent.

THE RULES (operator, 2026-08-30). These are the authority. Nothing in the
portfolio may reimplement, reinterpret or locally extend them.

  1. If the record is NOT a child record, inheritance does not apply.
     Self-Defined and Full are identical. Stop.
     The child records are EXACTLY Season, Episode, Edit, Clip and
     Manifestation (:data:`CHILD_TYPES`). Compilation is NOT a child -- it
     sits at the registration tree root; it has entries, but no Parent ID.
     Both adapters enforce this: for a non-child creation type a supplied
     parent is IGNORED and Self is returned as Full, so a caller mistake
     cannot produce inheritance the registry would never perform.

  2. If the record is a Season or Episode supplied WITHOUT a user-provided
     ResourceName (primary title), generate one from the record's own data
     plus the parent's title. The parent always has a title and the child
     always has what the pattern needs -- so failure is a DATA defect and
     raises :class:`TitleConstructionError`, never a silent untitled child.

  3. If the record has no data in an inheritable field, copy the parent's
     values (if any). If it already has data in that field, that blocks
     inheritance for that field.

     Of the two title fields ONLY ``ResourceName`` is inheritable.
     ``AlternateResourceName`` is never inherited (operator, 2026-08-30).

     What blocks is a USER-SUPPLIED value. A **system-generated**
     ``ResourceName`` does NOT block -- it is not something the submitter
     provided, so it is replaced by the parent's real title (Edit / Clip /
     Manifestation) or regenerated (Season / Episode).

  ORDER. Title generation (rule 2) runs BEFORE field inheritance (rule 3).
  The generated title uses the parent's title plus data guaranteed to be in
  the CHILD record; inheritance then fills every inheritable field the child
  still lacks; and the generated title, being data in the field, blocks
  ResourceName inheritance for Season/Episode.

  The order is load-bearing, not stylistic. Inheriting first lets a child
  with no number reach the release-date pattern through a date it just took
  from its parent -- so every sibling under one parent generates the SAME
  string ("The Series [2006]"). The date pattern exists to tell siblings
  apart, so that is a false de-dup signal manufactured by the module whose
  job is to make children comparable. A Season or Episode with no number and
  no date of its own therefore RAISES; it does not borrow one.
  (Operator ruling 2026-08-30, reported by XML_to_JSON -- which had asked for
  the inherited-date behaviour a day earlier, after reading a docstring here
  that asserted it was intended. The docstring was wrong.)

Rules 2 and 3 are ONE rule with two applications: a user-supplied value is
never replaced -- not by an inherited one, not by a generated one. Everything
else is fair game.

INHERITANCE IS DETERMINISTIC. The same starting record must produce the same
full record through every code path in every program. That is why this module
exists and why no consumer keeps a parallel implementation: as of 2026-08-30
XML_to_JSON's exporter, BMR-Review's ``inherit.materialize`` and its
``mirror.reconstruct_full`` all delegate here, and each repo carries a test
asserting its paths agree.

A child record (Season, Episode, Edit, Clip, Manifestation) carries only
*self-defined* metadata. The record the registry actually holds is that plus
everything inherited from the parent's FULL record. Comparing a sparse
self-defined child against a full registry candidate compares populated
fields to empty ones — no credit for agreement, no penalty for conflict, in
both directions — so anything that scores or exports a child needs the full
form first.

Two consumers, one specification (register R13, accepted 2026-08-29):

* **XML_to_JSON** builds full records from the registry JSON shape and is
  the reference implementation this was seeded from.
* **BMR-Review** needs the same thing for BMR-sheet children, and had
  stubbed a consumption seam (``eidr_dedup_score/full_record.py``) rather
  than write a second copy.

WHY THIS IS A SPECIFICATION, NOT A CONVENIENCE
----------------------------------------------
R13's usual test is "wait for the second consumer". That test is met, but
it is not the strongest argument. The field policy comes straight from the
EIDR schema's ``inheritedBaseObjectInfoGroup`` and the title patterns are
registry BEHAVIOUR — so a second implementation is not a difference of
opinion, it is a second chance to get a published rule wrong. Both
independent implementations that existed when this landed were in fact
wrong, in different ways:

* XML_to_JSON inherited ``Administrators``, which the schema forbids
  *because it carries the Registrant* — so a child asserted it was
  registered by whoever registered its parent. Not cosmetic: BMR-Review's
  match-audit reads Registrant to decide **which member to notify** about
  a mis-assigned ID.
* XML_to_JSON implemented only the two NUMBERED title patterns, so a Season
  with no Sequence Number or an Episode with no Distribution Number got no
  system-generated title at all — and an untitled child drops the field
  the de-dup engine weights most heavily (70 for Basic, 40 for Episode).
* BMR-Review carried TWO inheritance paths that disagreed with each other:
  ``mirror.reconstruct_full`` inherited ``Mode``/``ReferentType`` but not
  ``ReleaseDate``; ``inherit.materialize`` inherited ``ReleaseDate`` but
  not ``Mode``/``ReferentType``. A record scored differently depending on
  which built it.

TWO SHAPES, ONE POLICY
----------------------
The consumers work in different shapes and neither should have to convert
wholesale, so the policy lives once and two thin adapters sit over it:

* :func:`build_full_base` — registry JSON (``BaseObjectData`` dicts).
* :func:`build_full_record` — record objects addressed by attribute.

This package deliberately imports NEITHER consumer's model. The object
adapter works through :data:`RECORD_ATTRS`, a documented canonical-name →
attribute-name convention the caller may override.

PROVENANCE
----------
Both builders report, per canonical field, whether the value is ``self``,
``inherited`` or ``system``. That is not decoration: BMR-Review's next
tuning cycle implements the operator's rule that an inherited MISMATCH must
not eliminate a candidate while an inherited MATCH may still confirm, and
its model carries no flag at all for scalars like ``ReleaseDate`` or
``ApproximateLength`` — exactly the fields where inherited values are most
common.
"""
from __future__ import annotations

import contextlib
import copy
import re
from typing import Any


class TitleConstructionError(ValueError):
    """A Season/Episode needed a generated title and the data could not make one.

    The operator's rule states this cannot happen: "The parent record will
    always have a title and the current record will always have the data
    necessary to generate a title." So reaching this is a DATA defect, not a
    normal branch.

    It is an exception rather than a silent ``None`` because the silent form
    is a known, expensive bug: an untitled child drops the field the de-dup
    engine weights most heavily (70 Basic / 40 Episode), so a genuine
    duplicate loses its strongest signal and is missed. XML_to_JSON shipped
    exactly that shape in August 2026.

    It is a distinct type so a batch caller can catch it per record and skip
    the row with a reason, rather than choosing between aborting the run and
    not knowing.

    The exception carries the work already done, so a caller that chooses to
    proceed does not re-derive inheritance through a second code path (the
    exact hazard this module removes):

    * ``partial`` -- the full record/base with every inheritable field
      applied and NO title;
    * ``provenance`` -- the per-field map for that partial result.

    "NO title" includes a stale system-generated title the self record
    already carried: both adapters DROP it from ``partial`` (the JSON
    adapter removes the ``ResourceName`` key, the object adapter removes
    those elements from ``titles``) and ``provenance`` has no
    ``ResourceName`` entry. It is the string generation just failed to
    rebuild, so handing it on would let a caller such as XML_to_JSON export
    an old derived title as current (operator ruling 2026-10-19; 0.69.0).
    """

    partial: Any = None
    provenance: dict | None = None


__all__ = [
    "INHERITABLE_FIELDS",
    "CHILD_TYPES",
    "TitleConstructionError",
    "NEVER_INHERITED",
    "TITLE_EXEMPT_TYPES",
    "TITLE_INHERITING_TYPES",
    "is_absent",
    "has_user_supplied_title",
    "RECORD_ATTRS",
    "system_generated_title",
    "build_full_base",
    "build_full_record",
    "provenance",
]

# ---------------------------------------------------------------------------
# The field policy. Operator-supplied as authoritative, from the EIDR schema's
# allInheritedInfoType / inheritedBaseObjectInfoGroup.
# ---------------------------------------------------------------------------

INHERITABLE_FIELDS: frozenset[str] = frozenset({
    "StructuralType", "Mode", "ReferentType",
    "ResourceName",                      # AlternateResourceName is NOT here
    "OriginalLanguage", "VersionLanguage",
    "AssociatedOrg", "ReleaseDate", "CountryOfOrigin",
    "Status", "ApproximateLength", "Credits",
})

# Explicit rather than "everything not inheritable", because the reason
# differs per field and the reasons are what stop someone re-adding one.
NEVER_INHERITED: frozenset[str] = frozenset({
    "ID",              # identity
    "Administrators",  # carries the Registrant — schema comments the exclusion
    "AlternateID",     # a parent's alt IDs are not the child's
    # A child does not acquire its parent's alternate titles. Only the
    # PRIMARY title inherits (operator ruling 2026-08-30, correcting the
    # schema summary this module was seeded from, which listed both).
    "AlternateResourceName",
    "Description",
    "RegistrantExtra",
    # ...plus everything in ExtraObjectMetadata: all creation-type-specific
    # blocks (Series, Season, Episode, Edit, Clip, Manifestation,
    # Compilation). Handled structurally rather than by name.
})

# The ONLY creation types that inherit at all. Compilation is deliberately
# absent: it sits at the registration tree root -- it has entries, but no
# Parent ID -- so it is not a child record (operator, 2026-08-30, correcting
# an audit note that used it as an example of an "unanticipated child type").
CHILD_TYPES: frozenset[str] = frozenset({
    "Season", "Episode", "Edit", "Clip", "Manifestation",
})

# Season and Episode do NOT inherit the parent's title — a system-generated
# one is constructed instead. The other three child types inherit it
# verbatim, which is ordinary field inheritance. With CHILD_TYPES closed,
# TITLE_INHERITING_TYPES is exactly CHILD_TYPES - TITLE_EXEMPT_TYPES; kept as
# a documented export, but code branches on the exemption, never on this
# set.
TITLE_EXEMPT_TYPES: frozenset[str] = frozenset({"Season", "Episode"})
TITLE_INHERITING_TYPES: frozenset[str] = frozenset({"Edit", "Clip", "Manifestation"})


def system_generated_title(
    parent_title: str,
    creation_type: str,
    *,
    sequence_number: Any = None,      # Season
    distribution_number: Any = None,  # Episode
    release_date: Any = None,         # the fallback for both
    time_slot: Any = None,            # Episode, date form only (0.74.0)
    end_date: Any = None,             # Season, date form only (0.76.0)
    series_title: Any = None,         # Episode under a user-titled Season (0.78.0)
) -> tuple[str, str] | None:
    """``(title, title_class)`` for a Season or Episode, or None.

    The registry's four patterns, operator-supplied:

    ===============================  ==========================================
    Season **with** Sequence Number  ``<Series Title>: Season <N>``
    Season **without**               ``<Series Title> [<Season Release Year>]``
    Episode **with** Dist. Number    ``<Season Title>: Episode <N>``
    Episode **without**              ``<Season Title> [<Episode Release Date>]``
    ===============================  ==========================================

    A dated Season's brackets hold the YEAR of its release date, or
    ``<year>-<end year>`` when the Season's ``EndDate`` falls in another
    year: ``5Vor12 [2017]`` for release date 2017-09-18
    (10.5240/88A3-8C1A-DE86-1D38-EDF6-U, the operator's example, 2026-11-16),
    ``Motorsport Mundial [2021-2022]``. Measured over the mirror's 1,461
    bracket Seasons on 2026-11-15: 0 hold a full date; 910 hold a year-only
    release date, 427 the year of a full release date, 86 a year range from
    the end year, and 38 whose end year equals the start year the year
    alone. Until 0.76.0 the whole date was written, so 534 of them (427 +
    86 + the 21 of the 38 with a full release date) failed to match the
    registry's own record. No generated Season has an end year BEFORE its
    release year, so the registry shows nothing for that bad-data case; it
    gets the range as given (``[2022-2021]``) rather than a guessed repair.
    A release date that does not start with a four-digit year is written as
    given rather than guessed at, and then no range is built: there is no
    release year to compare the end year with. An Episode's
    brackets keep the full date (0 of 1,601 registry Episode bracket titles
    hold a year only).

    An Episode without a Distribution Number that has a ``TimeSlot`` gets the
    slot's ``HH:MM`` inside the brackets: ``<Season Title> [<date> <HH:MM>]``.
    Measured on the mirror, 2026-11-13: all 158 Episodes with a TimeSlot have
    a generated title of exactly that form (``BBC London News [2012-05-19
    16:50]`` from slot ``16:50:00``), and 0 of them matched this function
    before 0.74.0, so each failed to match the registry's own record. The
    slot is used only when it reads as ``HH:MM`` (seconds dropped), the only
    shape the mirror holds; anything else is ignored rather than guessed.
    Never on the numbered form or on a Season: the registry has no such
    title (no Episode with both a number and a slot exists to show one).

    An Episode whose Season title the SUBMITTER supplied is titled from the
    Series as well: ``<Series Title>: <Season Title>: Episode <N>``, or
    ``<Series Title> [<Episode Release Date>]`` (the Season's title left out),
    when ``series_title`` is given (operator ruling 2026-11-24, "Yes" to
    following the registry). Measured on the mirror, 2026-11-15: 37,046
    numbered Episodes under a user-titled Season take the first form and 0
    take ``<Season>: Episode <N>`` (live: 10.5240/4778-F5B5-8ACC-3F5B-53A0-U
    "America Reports: 2024: Episode 110" under the Season titled "2024"); all
    60 dated ones take the second ("Parallels [2015-03-01]" under the Season
    "One Night Movie Version"). It applies even when the Season title already
    starts with the Series title ("Free Ride: Free Ride 2008: Episode 6"). A
    generated Season title already holds the Series title, which is why only
    a user-supplied one needs it. The CALLER decides: the builders pass
    ``series_title`` only when the parent's main title is user-supplied.

    The date form is a FALLBACK, not an error path — the pre-2026-08-29
    XML_to_JSON implementation had only the numbered rows and returned None
    otherwise, leaving such children untitled.

    ``parent_title`` for an Episode is the SEASON's title, which is itself
    often system-generated. Construction is therefore recursive in effect,
    but each step needs only the parent's FULL record — never a walk to the
    root.

    The title class is ``series numeric`` for the two numbered forms and
    ``series date`` for the two bracket forms, as the registry writes them:
    measured over every generated title in the mirror on 2026-11-15 (Season
    numbered 87,347, bracket 1,461; Episode numbered 809,428, bracket 1,601;
    0 exceptions), and over 75,296 of the registry's own XML records. Until
    0.75.0 an Episode got ``season numeric``, which is not in the schema's
    titleClass enumeration, and a dated Season ``series numeric``.

    The title's language is not decided here: the adapters copy the
    IMMEDIATE parent's main-title language (see :func:`build_full_base`).

    Deliberately NOT consulted: ``HouseSequence``. XML_to_JSON fell back to
    it for the episode number, which is not in the registry's rules — an
    episode with a house sequence but no distribution number would get a
    title the registry never generates, and so would fail to match the
    registry's own record for itself.
    """
    title = str(parent_title or "").strip()
    if not title:
        return None

    if creation_type == "Season":
        seq = _text(sequence_number)
        if seq:
            return f"{title}: Season {seq}", "series numeric"
        date = _text(release_date)
        if not date:
            return None
        start = _year(date)
        if not start:
            return f"{title} [{date}]", "series date"
        end = _year(_text(end_date))
        stamp = f"{start}-{end}" if end and end != start else start
        return f"{title} [{stamp}]", "series date"

    if creation_type == "Episode":
        series = _text(series_title)
        dist = _text(distribution_number)
        if dist:
            prefix = f"{series}: {title}" if series else title
            return f"{prefix}: Episode {dist}", "series numeric"
        date = _text(release_date)
        if not date:
            return None
        slot = _hh_mm(time_slot)
        stamp = f"{date} {slot}" if slot else date
        return f"{series or title} [{stamp}]", "series date"

    return None


_HH_MM = re.compile(r"^(\d{2}:\d{2})(?::\d{2}(?:\.\d+)?)?$")
# A year at the start of an xs:date / xs:gYear / datetime text. The negative
# lookahead stops "20170918" (no separators) from reading as the year 2017.
_YEAR = re.compile(r"^(\d{4})(?!\d)")


def _year(value: str) -> str:
    """The leading four-digit year of a date text (``2017-09-18`` -> ``2017``), else ""."""
    m = _YEAR.match(value)
    return m.group(1) if m else ""


def _hh_mm(value: Any) -> str:
    """``HH:MM`` from a TimeSlot (``16:50:00`` -> ``16:50``), else ""."""
    m = _HH_MM.match(_text(value))
    return m.group(1) if m else ""


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _items(titles: Any) -> list:
    if is_absent(titles):
        return []
    return list(titles) if isinstance(titles, (list, tuple)) else [titles]


def _is_generated(item: Any) -> bool:
    if isinstance(item, dict):
        return str(item.get("SystemGenerated")).strip().lower() == "true"
    return bool(getattr(item, "system_generated", False))


def _title_text(item: Any) -> str:
    if isinstance(item, dict):
        return _text(item.get("Title") if item.get("Title") is not None
                     else item.get("value"))
    if hasattr(item, "text"):
        return _text(item.text)
    return _text(item)


def _split_titles(titles: Any) -> tuple[Any, list]:
    """``(main title, alternates)`` from a title list, in either shape.

    The main title is entry 0 of a list of dicts, whatever its text: an
    alternate is never promoted to main (operator, 2026-11-15: "if the main
    title is missing, you do not promote the Alternate"). For record objects
    that carry ``is_resource`` (BMR-Review's model), the main title is the
    element marked ``is_resource`` and there may be none; for objects without
    the attribute, entry 0 as for dicts.
    """
    items = _items(titles)
    if not items:
        return None, []
    if not isinstance(items[0], dict) and any(hasattr(t, "is_resource") for t in items):
        mains = [t for t in items if getattr(t, "is_resource", False)]
        main = mains[0] if mains else None
        return main, [t for t in items if t is not main]
    return items[0], items[1:]


def has_user_supplied_title(titles: Any) -> bool:
    """Does this ResourceName value carry a MAIN title the SUBMITTER provided?

    Only a user-supplied title blocks inheritance or regeneration. A
    system-generated one does not: the registry produced it, not the
    submitter, so replacing it with the parent's real title (Edit / Clip /
    Manifestation) or regenerating it (Season / Episode) is correct rather
    than destructive. Operator, 2026-08-30 -- "only Resource Name can be
    inherited (if it is not provided or system-generated)".

    Only the MAIN title counts (0.75.0; see :func:`_split_titles` for which
    one that is). An alternate title never blocks: "For child records, you
    can have only an Alternate Title, which must remain an Alternate Title.
    The main title will be inherited or system generated, as normal"
    (operator, 2026-11-15). Until 0.75.0 any non-generated entry blocked, so
    a child with a stale generated title plus one alternate (8,766 in the
    mirror) kept the stale title, and an alt-only child kept its alternate
    as its title.

    Accepts either shape: registry-JSON title dicts (``SystemGenerated`` is
    the string ``"true"``) or record objects with a ``system_generated``
    attribute. A main title with no text is no title. Anything unrecognised
    counts as user-supplied, because the safe error is to PRESERVE a title
    rather than overwrite one.
    """
    main, _ = _split_titles(titles)
    if main is None:
        return False
    if isinstance(main, dict) or hasattr(main, "text"):
        return bool(_title_text(main)) and not _is_generated(main)
    return not _is_generated(main)


def _split_base_titles(base: dict) -> None:
    """Move ResourceName entries 1..n to ``AlternateResourceName``, in place.

    The JSON adapter's output keeps the two title fields apart, as the
    registry XML does (0.75.0): ``ResourceName`` holds the main title only,
    ``AlternateResourceName`` the alternates. Callers that still build the
    older one-list shape (main first, alternates after) are accepted; their
    alternates come back under their own key, ahead of any already there.

    A main entry with no title text is removed, not promoted over: it is an
    empty element, which EIDR does not allow (operator, 2026-11-15), and an
    entry the provenance map would otherwise leave out.
    """
    titles = base.get("ResourceName")
    if titles is None:
        return
    items = list(titles) if isinstance(titles, (list, tuple)) else [titles]
    main, extra = (items[0], [t for t in items[1:] if t is not None]) if items else (None, [])
    if main is not None and _title_text(main):
        base["ResourceName"] = [main]
    else:
        base.pop("ResourceName", None)
    if extra:
        alts = base.get("AlternateResourceName")
        alts = list(alts) if isinstance(alts, (list, tuple)) else ([alts] if alts else [])
        base["AlternateResourceName"] = extra + alts


def is_absent(value: Any) -> bool:
    """THE emptiness rule: is this value absent for inheritance purposes?

    Public because it is POLICY, not a helper. "If the self-defined record
    does not provide a value, it is inherited" (operator, 2026-08-30) turns
    entirely on what "does not provide" means, and getting it wrong breaks the
    rule in BOTH directions -- a plain truthiness test replaces a self-defined
    ``0`` with the parent's value AND declines to inherit a legitimate ``0``.

    Exported 2026-08-30 because XML_to_JSON hit exactly that and had to COPY
    the logic: it was private and not in ``__all__``, and importing another
    package's underscore name is worse than a documented copy. A rule that a
    consumer must reimplement to obey is not single-homed.

    None, empty string, whitespace-only string, empty container.
    ``0`` and ``False`` are NOT absent -- a real ``ApproximateLength`` of 0 or
    a real ``False`` flag must not be overwritten by the parent's value.
    """
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) == 0
    return False


# Internal alias: the module's own call sites read better with the short name,
# and renaming ~10 uses would churn a diff consumers track via @main.
_is_empty = is_absent


# ---------------------------------------------------------------------------
# Shape 1 — registry JSON (BaseObjectData dicts). XML_to_JSON's native form.
# ---------------------------------------------------------------------------

def _series_prefix(parent_titles: Any, series_title: Any) -> str | None:
    """The Series title the generator should prefix, or None.

    Only when the parent's MAIN title is user-supplied: a generated Season
    title already holds the Series title, and a stale generated one is
    regenerated rather than kept. Both adapters call this, so they cannot
    disagree on when the Series title applies. (The generator uses it for an
    Episode only; a Season ignores it.)
    """
    if not _text(series_title):
        return None
    return _text(series_title) if has_user_supplied_title(parent_titles) else None


def build_full_base(
    self_base: dict,
    parent_base: dict | None,
    creation_type: str,
    extra: dict | None = None,
    *,
    series_title: str | None = None,
) -> tuple[dict, dict[str, str]]:
    """Build a child's FULL ``BaseObjectData`` from its self-defined one.

    ``parent_base`` is the parent's **FULL** ``BaseObjectData`` (not its
    self-defined one) — inheritance is one hop, because the parent's full
    record already carries whatever IT inherited.

    Titles (0.75.0): the result's ``ResourceName`` is the main title only and
    ``AlternateResourceName`` holds the child's own alternates, which are
    never inherited and never replaced by a generated or inherited main
    title. A one-list ``ResourceName`` (main first) is still accepted; its
    alternates come back under ``AlternateResourceName``. Only the parent's
    MAIN title (ResourceName entry 0) is ever used, for generation or
    inheritance; until 0.75.0 an Edit inherited the parent's whole list,
    alternates included, which the registry never does (0 of 564,425
    mirror records with alternates show a parent's alternate).

    ``extra`` supplies the title inputs: ``SequenceNumber`` (Season),
    ``DistributionNumber`` (Episode), ``ReleaseDate`` (the fallback for
    both), ``TimeSlot`` (Episode, date form; 0.74.0), ``EndDate`` (the
    Season's ``SeasonInfo/EndDate``, date form; 0.76.0). A missing
    ``ReleaseDate`` falls back to the child's own ``self_base['ReleaseDate']``
    (never an inherited one); missing ``SequenceNumber``/``DistributionNumber``
    mean the numbered pattern cannot fire.

    ``series_title`` (0.78.0) is the Series' main title, for an Episode whose
    parent is a Season. Pass it whenever the parent is a Season; it is used
    only when that Season's main title is user-supplied, where the registry
    titles the Episode ``<Series>: <Season>: Episode <N>`` or ``<Series>
    [<date>]`` (see :func:`system_generated_title`). Without it such an
    Episode gets ``<Season>: Episode <N>``, the pre-0.78.0 title, which does
    not match the registry's.

    Returns ``(full_base, provenance)`` where provenance maps each canonical
    field present in the result to ``'self'``, ``'inherited'`` or
    ``'system'``. The caller owns ``ExtraObjectMetadata``: it is
    creation-type-specific and never inherited, so it is not touched here.
    """
    extra = extra or {}
    full: dict = copy.deepcopy(self_base or {})
    # One representation in the output: ResourceName is the main title only,
    # AlternateResourceName the alternates (0.75.0). A one-list input has
    # its entries 1..n moved; entry 0 is the main title, and one with no
    # text is dropped rather than replaced by an alternate.
    _split_base_titles(full)
    # A system-generated ResourceName is not "self" -- the submitter did not
    # supply it. Left unset here; the construction block below marks it.
    prov: dict[str, str] = {
        f: "self" for f, v in full.items()
        if not _is_empty(v)
        and (f != "ResourceName" or has_user_supplied_title(v))
    }

    # RULE 1 -- childness is TYPE-defined. For a non-child creation type a
    # supplied parent is IGNORED: the registry performs no inheritance for a
    # Compilation (tree root: entries, no Parent ID) or any other root type,
    # so neither does this. Self IS Full.
    if creation_type not in CHILD_TYPES or not parent_base:
        return full, prov

    # ORDER: TITLE GENERATION RUNS BEFORE FIELD INHERITANCE (operator ruling
    # 2026-08-30). The generated title uses the parent's title plus data
    # GUARANTEED to be in the child record; inheritance then fills whatever
    # the child still lacks, and the title just written counts as data, so it
    # blocks ResourceName inheritance for Season/Episode.
    #
    # This is not a refactor. Until 2026-08-30 the loop ran first, so a
    # Season/Episode with no number could reach the release-date pattern via a
    # date it had just INHERITED -- making every sibling under one parent
    # generate the identical title ("The Series [2006]"), a false de-dup
    # signal manufactured by the module whose job is to make children
    # comparable. Reported by XML_to_JSON, which had itself asked for the old
    # behaviour after reading a docstring that asserted it was intended.
    title_error: TitleConstructionError | None = None
    if (creation_type in TITLE_EXEMPT_TYPES
            and not has_user_supplied_title(full.get("ResourceName"))):
        built = system_generated_title(
            _best_title(parent_base),
            creation_type,
            sequence_number=extra.get("SequenceNumber"),
            distribution_number=extra.get("DistributionNumber"),
            time_slot=extra.get("TimeSlot"),
            # The Season's own SeasonInfo/EndDate (0.76.0). Never inherited:
            # ExtraObjectMetadata is the caller's, and only the caller has it.
            end_date=extra.get("EndDate"),
            series_title=_series_prefix(parent_base.get("ResourceName"), series_title),
            # `full` has not been through the loop yet, so this is the child's
            # OWN date -- which is the point of generating first. `extra`
            # still wins: it is the caller saying "use this date for the
            # title", and nothing should outrank that.
            release_date=extra.get("ReleaseDate") or full.get("ReleaseDate"),
        )
        if built:
            text, title_class = built
            made = {"Title": text, "TitleClass": title_class}
            # The IMMEDIATE parent's main-title language, written only when
            # it has one (absent fields stay absent). The registry does this
            # for 899,829 of 899,837 generated titles (the 8 others are stale
            # records), including all 6,987 Episodes under a user-titled
            # Season whose language differs from the Series' (mirror,
            # 2026-11-15). Until 0.75.0 a generated title had no language,
            # which the schema requires.
            lang = _text((_main_title(parent_base) or {}).get("_lang"))
            if lang:
                made["_lang"] = lang
            made["SystemGenerated"] = "true"
            full["ResourceName"] = [made]
            prov["ResourceName"] = "system"
        else:
            # RULE 2 says this is impossible. Reaching it means the parent has
            # no title, or the child has neither a number nor a release date
            # OF ITS OWN. Deliberately not raised here: inheritance still has
            # to run so `exc.partial` hands back a base complete in every
            # OTHER field, which XML_to_JSON's fallback handler depends on.
            # Raised at the end.
            title_error = TitleConstructionError(
                f"{creation_type} has no user-supplied ResourceName and no "
                f"generated title could be built: parent title="
                f"{_best_title(parent_base)!r}, "
                f"sequence_number={extra.get('SequenceNumber')!r}, "
                f"distribution_number={extra.get('DistributionNumber')!r}, "
                f"release_date="
                f"{extra.get('ReleaseDate') or full.get('ReleaseDate')!r}. "
                "Leaving the child untitled would silently drop the "
                "heaviest-weighted comparison field."
            )

    # The PARENT's key order, then the rest sorted: never the frozenset's own
    # iteration order, which follows string hashing and so changed from one
    # process to the next (PYTHONHASHSEED). Inherited fields are appended to
    # `full` in this order, so until 0.49.1 the same input gave Full JSON
    # with differently ordered keys on every run (found 2026-10-13 comparing
    # two XML_to_JSON runs byte for byte; values were always equal).
    ordered = [f for f in parent_base if f in INHERITABLE_FIELDS]
    ordered += sorted(INHERITABLE_FIELDS.difference(ordered))
    for field in ordered:
        if field in NEVER_INHERITED:
            continue                                    # belt and braces
        if field == "ResourceName":
            # Season/Episode NEVER inherit a title. Theirs is user-supplied or
            # generated above -- and if generation FAILED, untitled is the
            # correct outcome, NOT the parent's title. Copying that in gives
            # the child a Full title byte-identical to its parent's (a false
            # parent-child duplicate for the de-dup engine) carrying the
            # parent's SystemGenerated="false", asserting a human-supplied
            # title nobody supplied. XML_to_JSON pinned that leak in a test;
            # eidr-core briefly reintroduced it on 2026-08-30 by deleting this
            # exemption as "covered by the general blocking rule" -- which
            # holds only when generation SUCCEEDS.
            if creation_type in TITLE_EXEMPT_TYPES:
                continue
            # Other child types DO inherit one, and only a user-supplied title
            # blocks: a system-generated one is not the submitter's, so it is
            # replaced by the parent's real title rather than outliving a
            # corrected parent.
            if has_user_supplied_title(full.get(field)):
                continue
        elif not _is_empty(full.get(field)):
            continue
        pv = parent_base.get(field)
        if field == "ResourceName":
            # The parent's MAIN title only: a child never acquires its
            # parent's alternates (NEVER_INHERITED), and a parent in the
            # one-list shape carries them in this field.
            main = _main_title(parent_base)
            pv = [main] if main is not None and _title_text(main) else None
        if _is_empty(pv):
            continue
        full[field] = copy.deepcopy(pv)
        prov[field] = "inherited"

    if title_error is not None:
        # Inheritance has now run, so hand over a base complete in every
        # field EXCEPT the title -- which is exactly why it is a `partial`.
        # The caller need not re-derive the inherited fields through a second
        # path, and does not silently receive the parent's title standing in
        # for the one that could not be built.
        #
        # A stale system-generated title the self base already carried is
        # dropped too: it is the string generation just failed to rebuild,
        # and it reached XML_to_JSON's export through `exc.partial` with no
        # provenance entry (operator ruling 2026-10-19; 0.69.0). Only
        # generated entries can be here -- a user-supplied one would have
        # skipped generation -- but the filter keeps anything else anyway.
        kept = _without_generated(full.get("ResourceName"))
        if kept:
            full["ResourceName"] = kept
        else:
            full.pop("ResourceName", None)
        prov.pop("ResourceName", None)
        title_error.partial, title_error.provenance = full, dict(prov)
        raise title_error

    return full, prov


def _without_generated(titles: Any) -> list:
    """``titles`` minus its system-generated entries, in either shape.

    Used only on the TitleConstructionError path, to keep a stale generated
    title out of ``exc.partial`` (operator ruling 2026-10-19; 0.69.0). Reads
    the flag the same way :func:`has_user_supplied_title` does, so the two
    cannot disagree about which entries are generated.
    """
    if is_absent(titles):
        return []
    items = titles if isinstance(titles, (list, tuple)) else [titles]
    kept = []
    for item in items:
        if isinstance(item, dict):
            generated = str(item.get("SystemGenerated")).strip().lower() == "true"
        else:
            generated = bool(getattr(item, "system_generated", False))
        if not generated:
            kept.append(item)
    return kept


def _main_title(base: dict | None) -> dict | None:
    """The main-title entry (ResourceName entry 0) of a BaseObjectData dict."""
    if not base:
        return None
    main, _ = _split_titles(base.get("ResourceName"))
    return main if isinstance(main, dict) else None


def _best_title(base: dict | None) -> str:
    """The parent's MAIN title text (ResourceName entry 0), or "".

    Until 0.75.0 this was the first entry with text, so a parent whose main
    title was empty lent its first alternate (operator, 2026-11-15: an
    alternate is never promoted). The mirror has one such parent, an alias
    with no titles at all.
    """
    if not base:
        return ""
    main, _ = _split_titles(base.get("ResourceName"))
    return _title_text(main) if main is not None else ""


# ---------------------------------------------------------------------------
# Shape 2 — record objects addressed by attribute. BMR-Review's native form.
# ---------------------------------------------------------------------------

# Canonical EIDR field name -> attribute name on a portfolio record object.
# A convention, not an import: eidr-core must not depend on any consumer's
# model. Pass `attrs=` to override. Fields absent from a given model are
# skipped silently, which is why `Status` (which CanonicalRecord does not
# carry) needs no special handling.
RECORD_ATTRS: dict[str, str] = {
    "StructuralType": "structural_type",
    "Mode": "mode",
    "ReferentType": "referent_type",
    "OriginalLanguage": "original_languages",
    "VersionLanguage": "version_languages",
    "AssociatedOrg": "assoc_orgs",
    "ReleaseDate": "release_date",
    "CountryOfOrigin": "countries",
    "ApproximateLength": "length_minutes",
    "Status": "status",
}

# Credits arrive as one schema field but are modelled as separate lists.
_CREDIT_ATTRS = ("directors", "actors")

_PROVENANCE_ATTR = "eidr_provenance"


def build_full_record(
    self_rec: Any,
    parent_full: Any,
    creation_type: str | None = None,
    *,
    attrs: dict[str, str] | None = None,
    series_title: str | None = None,
) -> Any:
    """Build a child's FULL record object from its self-defined one.

    Same policy as :func:`build_full_base`, over attributes instead of dict
    keys. Returns a deep copy; ``self_rec`` is not modified.

    The provenance map is attached to the result as ``eidr_provenance`` and
    read back by :func:`provenance`, because a record object alone cannot
    say which of its values were inherited — and for scalars such as
    ``release_date`` the model carries no flag at all.

    Titles: elements are marked ``self_defined`` / ``system_generated``
    where the model exposes those, so the existing element-level flags stay
    truthful alongside the new field-level map.

    ``attrs`` maps canonical field names to attribute names. A
    ``ResourceName`` entry in it is ignored: the title is always decided by
    the title logic (user-supplied test, then generation or inheritance) on
    the model's ``titles`` attribute, never copied or reported by presence.
    A model whose ``titles`` is ``None`` is treated as untitled; only a model
    with no ``titles`` attribute at all skips title handling.

    ``series_title`` (0.78.0): as for :func:`build_full_base`, the Series'
    main title when the parent is a Season.
    """
    attrs = attrs or RECORD_ATTRS
    full = copy.deepcopy(self_rec)
    ctype = creation_type or getattr(full, "creation_type", None) or ""
    # A main title element with no text is an empty element, not a title
    # (0.75.0, as build_full_base): removed, never replaced by an alternate.
    main, _ = _split_titles(getattr(full, "titles", None))
    if main is not None and not _title_text(main):
        with contextlib.suppress(Exception):
            full.titles = [t for t in full.titles if t is not main]

    # A record this builder has ALREADY built carries its own provenance, and
    # presence alone cannot distinguish "the submitter supplied it" from "an
    # earlier pass inherited it". Callers materialize in place over a CACHED
    # record, so re-entry is normal, not exceptional -- carry the earlier
    # reading forward and let presence decide only what it can.
    prior = dict(getattr(full, _PROVENANCE_ATTR, None) or {})

    prov: dict[str, str] = {}
    for field, attr in attrs.items():
        # ResourceName is skipped here and in the inheritance loop below,
        # even when a caller's custom `attrs` maps it: titles are decided by
        # the title logic (the user-supplied test just below, and
        # _apply_title), never by presence. Read by presence, a
        # system-generated title was reported 'self' -- a title nobody
        # submitted (dictionary audit 2026-10-02; 0.68.0).
        if field == "ResourceName":
            continue
        if hasattr(full, attr) and not _is_empty(getattr(full, attr)):
            prov[field] = "self"
    for attr in _CREDIT_ATTRS:
        if hasattr(full, attr) and not _is_empty(getattr(full, attr)):
            prov["Credits"] = "self"
    if has_user_supplied_title(getattr(full, "titles", None)):
        prov["ResourceName"] = "self"
    for field, state in prior.items():
        if state != "self":
            prov[field] = state

    # Everything the submitter supplied is self-defined -- EXCEPT an element
    # already flagged system_generated, which by definition the submitter did
    # not supply. Stamping those True produced contradictory flags
    # (system_generated=True, self_defined=True) on the no-parent path, and
    # BMR-Review's inherited-discount rule reads both flags.
    #
    # An element already flagged self_defined=False was not supplied by the
    # submitter EITHER: it was inherited, by an earlier run of this builder
    # over the same object. Callers materialize in place over a CACHED record
    # (BMR-Review's report.evaluate_case, over mirror.MirrorSource.load), so
    # any record appearing on two rows reaches this loop twice, and stamping
    # True on the second pass promoted inherited values to self-defined --
    # silently disabling the consumer's inherited-value discount and rewriting
    # provenance from `inherited` to `self`. Respect an explicit False for the
    # same reason system_generated is respected.
    for attr in ("titles", "directors", "actors", "countries",
                 "original_languages", "version_languages", "assoc_orgs",
                 "alt_ids"):
        for element in getattr(full, attr, None) or []:
            if not hasattr(element, "self_defined"):
                continue
            if getattr(element, "self_defined", None) is False:
                continue
            element.self_defined = not getattr(
                element, "system_generated", False)

    # RULE 1 -- see build_full_base: for a non-child type a supplied parent
    # is ignored. Self IS Full.
    if ctype not in CHILD_TYPES or parent_full is None:
        _attach(full, prov)
        return full

    # Title BEFORE inheritance -- see the matching comment in
    # build_full_base. Doing it here means `full.release_date` is still the
    # child's OWN date, and the title written below is data that the loop
    # then treats as blocking, exactly as a submitted title would be.
    title_error = _apply_title(full, parent_full, ctype, prov, series_title)

    for field, attr in attrs.items():
        if field not in INHERITABLE_FIELDS or field in NEVER_INHERITED:
            continue
        # _apply_title above already made the title decision. Copying here
        # would hand a Season/Episode whose generation FAILED its parent's
        # title marked 'inherited' -- the false parent-child duplicate the
        # JSON adapter's ResourceName exemption exists to prevent. Reachable
        # only through a custom `attrs` that maps ResourceName (dictionary
        # audit 2026-10-02; 0.68.0).
        if field == "ResourceName":
            continue
        if not hasattr(full, attr) or not hasattr(parent_full, attr):
            continue
        if not _is_empty(getattr(full, attr)):
            continue
        pv = getattr(parent_full, attr)
        if _is_empty(pv):
            continue
        inherited = copy.deepcopy(pv)
        for element in inherited if isinstance(inherited, list) else []:
            if hasattr(element, "self_defined"):
                element.self_defined = False
        setattr(full, attr, inherited)
        prov[field] = "inherited"

    # Credits: one schema field, two lists; inherit each independently but
    # report them under the single canonical name. When the two lists
    # DISAGREE -- the child supplied directors and inherited actors, or the
    # reverse -- the single name must carry the WEAKER reading. Reporting
    # "self" there would assert the child supplied values it never supplied,
    # and a consumer that renders Credits across both roles would put a
    # self-defined glyph on inherited data. `setdefault` was doing exactly
    # that, because the self-loop above sets "self" when EITHER list is
    # populated. Assign, do not setdefault.
    for attr in _CREDIT_ATTRS:
        if not hasattr(full, attr) or not hasattr(parent_full, attr):
            continue
        if not _is_empty(getattr(full, attr)) or _is_empty(getattr(parent_full, attr)):
            continue
        inherited = copy.deepcopy(getattr(parent_full, attr))
        for element in inherited or []:
            if hasattr(element, "self_defined"):
                element.self_defined = False
        setattr(full, attr, inherited)
        prov["Credits"] = "inherited"

    if title_error is not None:
        # Inheritance has run, so the partial is complete in every field
        # EXCEPT the title: generation failed and the loops above never copy
        # ResourceName, so the parent's title does not stand in for the one
        # that could not be built. Same contract as build_full_base,
        # including dropping a stale system-generated title and any
        # ResourceName provenance a previous pass left in `prior` (operator
        # ruling 2026-10-19; 0.69.0).
        if getattr(full, "titles", None):
            full.titles = _without_generated(full.titles)
        prov.pop("ResourceName", None)
        _attach(full, prov)
        title_error.partial, title_error.provenance = full, dict(prov)
        raise title_error
    _attach(full, prov)
    return full


def _apply_title(
    full: Any, parent_full: Any, ctype: str, prov: dict,
    series_title: str | None = None,
) -> TitleConstructionError | None:
    """Season/Episode get a constructed title; other child types inherit one.

    Runs BEFORE field inheritance (operator ruling 2026-08-30), so the record
    still carries only its own data. RETURNS a TitleConstructionError rather
    than raising it: the caller has to finish inheriting before the error goes
    out, or `exc.partial` would hand back a base that is missing every
    inherited field.
    """
    # Only a model with NO `titles` attribute is skipped: it cannot carry a
    # title, so there is nothing to build. A model whose `titles` is None
    # carries none YET, which is the empty list by another name -- returning
    # here left a Season/Episode silently untitled where build_full_base
    # builds one or raises (dictionary audit 2026-10-02; 0.68.0).
    if not hasattr(full, "titles"):
        return None
    titles = full.titles or []
    # The child's own alternates survive whatever happens to its main title
    # (0.75.0): generation and inheritance replace the main title only.
    _, alternates = _split_titles(titles)

    if ctype in TITLE_EXEMPT_TYPES:
        # A USER-SUPPLIED title is kept. A system-generated one is not the
        # submitter's and is regenerated, so a changed parent title
        # propagates instead of leaving a stale derived string.
        if has_user_supplied_title(titles):
            return None
        built = system_generated_title(
            _best_record_title(parent_full),
            ctype,
            sequence_number=getattr(full, "sequence_number", None),
            distribution_number=getattr(full, "distribution_number", None),
            release_date=getattr(full, "release_date", None),
            time_slot=getattr(full, "time_slot", None),
            # The record's own end date, as the JSON adapter's extra["EndDate"].
            end_date=getattr(full, "end_date", None),
            series_title=_series_prefix(getattr(parent_full, "titles", None), series_title),
        )
        if not built:
            # Same rule, same failure, same exception as build_full_base -- the
            # two adapters must not differ even on the error path.
            exc = TitleConstructionError(
                f"{ctype} has no user-supplied title and no generated title "
                f"could be built: parent title="
                f"{_best_record_title(parent_full)!r}, "
                f"sequence_number={getattr(full, 'sequence_number', None)!r}, "
                f"distribution_number="
                f"{getattr(full, 'distribution_number', None)!r}, "
                f"release_date={getattr(full, 'release_date', None)!r}."
            )
            return exc
        text, title_class = built
        made = _clone_title(parent_full, text, title_class)
        if made is not None:
            full.titles = [made] + list(alternates)
            prov["ResourceName"] = "system"
        return None

    # Inherit for EVERY non-exempt type, not only the three named ones. The
    # policy is the field policy: ResourceName is inheritable, and the ONLY
    # exemption is Season/Episode (which construct instead). Until 2026-08-30
    # this branch keyed on TITLE_INHERITING_TYPES, so a child of any other
    # type (e.g. Compilation) inherited its parent's title through the JSON
    # adapter but NOT through this one -- the exact cross-adapter divergence
    # this module exists to prevent, caught by a cross-shape probe.
    if ctype not in TITLE_EXEMPT_TYPES and not has_user_supplied_title(titles):
        # The parent's MAIN title only, as in build_full_base: until 0.75.0
        # the whole list was copied, alternates included, and the child's own
        # alternates were dropped.
        parent_main, _ = _split_titles(getattr(parent_full, "titles", None))
        if parent_main is not None and _title_text(parent_main):
            inherited = copy.deepcopy(parent_main)
            if hasattr(inherited, "self_defined"):
                inherited.self_defined = False
            full.titles = [inherited] + list(alternates)
            prov["ResourceName"] = "inherited"
    return None


def _best_record_title(rec: Any) -> str:
    """The parent's MAIN title text, never an alternate's (0.75.0)."""
    main, _ = _split_titles(getattr(rec, "titles", None))
    return _title_text(main) if main is not None else ""


def _clone_title(parent_full: Any, text: str, title_class: str) -> Any:
    """Build a title element of whatever class the parent's titles use.

    Constructing it from the parent's own type avoids importing a consumer
    model. If the parent has no titles to copy the shape from, there is
    nothing to build and the child stays untitled — which the title
    comparator already handles by dropping the field.
    """
    # The parent's MAIN title is the template, so the generated title takes
    # its language (the registry's rule; see build_full_base) and never an
    # alternate's (0.75.0: until then the first element, whatever it was).
    template, _ = _split_titles(getattr(parent_full, "titles", None))
    if template is None:
        return None
    made = copy.deepcopy(template)
    for attr, value in (("text", text), ("title_class", title_class),
                        ("system_generated", True), ("self_defined", False),
                        ("is_resource", True), ("lang", getattr(template, "lang", None))):
        if hasattr(made, attr):
            setattr(made, attr, value)
    return made


def _attach(rec: Any, prov: dict) -> None:
    # Suppressed rather than raised: a slotted or frozen model cannot carry
    # the attribute, and losing the provenance map is a degradation, not a
    # reason to fail the build. provenance() then reports {} == "unknown".
    with contextlib.suppress(Exception):
        setattr(rec, _PROVENANCE_ATTR, prov)


def provenance(rec: Any) -> dict[str, str]:
    """Per-field provenance for a record built by :func:`build_full_record`.

    ``{canonical field: 'self' | 'inherited' | 'system'}``. Empty for a
    record this module did not build — absence means "unknown", never
    "self-defined".
    """
    return dict(getattr(rec, _PROVENANCE_ATTR, None) or {})
