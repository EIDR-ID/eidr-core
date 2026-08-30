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

``eidr_core`` deliberately imports NEITHER consumer's model. The object
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
) -> tuple[str, str] | None:
    """``(title, title_class)`` for a Season or Episode, or None.

    The registry's four patterns, operator-supplied:

    ===============================  ==========================================
    Season **with** Sequence Number  ``<Series Title>: Season <N>``
    Season **without**               ``<Series Title> [<Season Release Date>]``
    Episode **with** Dist. Number    ``<Season Title>: Episode <N>``
    Episode **without**              ``<Season Title> [<Episode Release Date>]``
    ===============================  ==========================================

    The date form is a FALLBACK, not an error path — the pre-2026-08-29
    XML_to_JSON implementation had only the numbered rows and returned None
    otherwise, leaving such children untitled.

    ``parent_title`` for an Episode is the SEASON's title, which is itself
    often system-generated. Construction is therefore recursive in effect,
    but each step needs only the parent's FULL record — never a walk to the
    root.

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
        return (f"{title} [{date}]", "series numeric") if date else None

    if creation_type == "Episode":
        dist = _text(distribution_number)
        if dist:
            return f"{title}: Episode {dist}", "season numeric"
        date = _text(release_date)
        return (f"{title} [{date}]", "season numeric") if date else None

    return None


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def has_user_supplied_title(titles: Any) -> bool:
    """Does this ResourceName value carry a title the SUBMITTER provided?

    Only a user-supplied title blocks inheritance or regeneration. A
    system-generated one does not: the registry produced it, not the
    submitter, so replacing it with the parent's real title (Edit / Clip /
    Manifestation) or regenerating it (Season / Episode) is correct rather
    than destructive. Operator, 2026-08-30 -- "only Resource Name can be
    inherited (if it is not provided or system-generated)".

    Accepts either shape: registry-JSON title dicts (``SystemGenerated`` is
    the string ``"true"``) or record objects with a ``system_generated``
    attribute. Anything unrecognised counts as user-supplied, because the
    safe error is to PRESERVE a title rather than overwrite one.
    """
    if is_absent(titles):
        return False
    items = titles if isinstance(titles, (list, tuple)) else [titles]
    for item in items:
        if isinstance(item, dict):
            flag = item.get("SystemGenerated")
            generated = str(flag).strip().lower() == "true"
        else:
            generated = bool(getattr(item, "system_generated", False))
        if not generated:
            return True          # at least one real title -> blocks
    return False


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

def build_full_base(
    self_base: dict,
    parent_base: dict | None,
    creation_type: str,
    extra: dict | None = None,
) -> tuple[dict, dict[str, str]]:
    """Build a child's FULL ``BaseObjectData`` from its self-defined one.

    ``parent_base`` is the parent's **FULL** ``BaseObjectData`` (not its
    self-defined one) — inheritance is one hop, because the parent's full
    record already carries whatever IT inherited.

    ``extra`` supplies the title inputs: ``SequenceNumber`` (Season),
    ``DistributionNumber`` (Episode), ``ReleaseDate`` (the fallback for
    both). Absent keys simply mean the corresponding pattern cannot fire.

    Returns ``(full_base, provenance)`` where provenance maps each canonical
    field present in the result to ``'self'``, ``'inherited'`` or
    ``'system'``. The caller owns ``ExtraObjectMetadata``: it is
    creation-type-specific and never inherited, so it is not touched here.
    """
    extra = extra or {}
    full: dict = copy.deepcopy(self_base or {})
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
    generated_title = False
    if (creation_type in TITLE_EXEMPT_TYPES
            and not has_user_supplied_title(full.get("ResourceName"))):
        built = system_generated_title(
            _best_title(parent_base),
            creation_type,
            sequence_number=extra.get("SequenceNumber"),
            distribution_number=extra.get("DistributionNumber"),
            # `full` has not been through the loop yet, so this is the child's
            # OWN date -- which is the point of generating first. `extra`
            # still wins: it is the caller saying "use this date for the
            # title", and nothing should outrank that.
            release_date=extra.get("ReleaseDate") or full.get("ReleaseDate"),
        )
        if built:
            text, title_class = built
            full["ResourceName"] = [{
                "Title": text,
                "TitleClass": title_class,
                "SystemGenerated": "true",
            }]
            prov["ResourceName"] = "system"
            generated_title = True
        else:
            # RULE 2 says this is impossible. Reaching it means the parent has
            # no title, or the child has neither a number nor a release date
            # OF ITS OWN. Deliberately not raised here: inheritance still has
            # to run so `exc.partial` hands back a fully-inherited base, which
            # XML_to_JSON's fallback handler depends on. Raised at the end.
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

    for field in INHERITABLE_FIELDS:
        if field in NEVER_INHERITED:
            continue                                    # belt and braces
        if field == "ResourceName":
            # A title generated moments ago is data in the field and blocks,
            # exactly as a submitted one does. A system-generated title the
            # record ARRIVED with does not block: it is not the submitter's,
            # so it was regenerated above, or is replaced by the parent's real
            # title here, rather than outliving a corrected parent.
            if generated_title or has_user_supplied_title(full.get(field)):
                continue
        elif not _is_empty(full.get(field)):
            continue
        pv = parent_base.get(field)
        if _is_empty(pv):
            continue
        full[field] = copy.deepcopy(pv)
        prov[field] = "inherited"

    if title_error is not None:
        # Inheritance has now run, so hand over a COMPLETE base: a caller that
        # proceeds must not have to re-derive it through a second path. Note
        # the child did pick up the parent's ResourceName in the loop above --
        # the best available fallback, and why this is a `partial` rather than
        # a bare failure.
        title_error.partial, title_error.provenance = full, dict(prov)
        raise title_error

    return full, prov


def _best_title(base: dict | None) -> str:
    """First non-empty ResourceName title string in a BaseObjectData dict."""
    if not base:
        return ""
    titles = base.get("ResourceName") or []
    if not isinstance(titles, list):
        titles = [titles]
    for t in titles:
        value = t.get("Title") if isinstance(t, dict) else t
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


# ---------------------------------------------------------------------------
# Shape 2 — record objects addressed by attribute. BMR-Review's native form.
# ---------------------------------------------------------------------------

# Canonical EIDR field name -> attribute name on a portfolio record object.
# A convention, not an import: eidr_core must not depend on any consumer's
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
    """
    attrs = attrs or RECORD_ATTRS
    full = copy.deepcopy(self_rec)
    ctype = creation_type or getattr(full, "creation_type", None) or ""

    prov: dict[str, str] = {}
    for field, attr in attrs.items():
        if hasattr(full, attr) and not _is_empty(getattr(full, attr)):
            prov[field] = "self"
    for attr in _CREDIT_ATTRS:
        if hasattr(full, attr) and not _is_empty(getattr(full, attr)):
            prov["Credits"] = "self"
    if has_user_supplied_title(getattr(full, "titles", None)):
        prov["ResourceName"] = "self"

    # Everything the submitter supplied is self-defined -- EXCEPT an element
    # already flagged system_generated, which by definition the submitter did
    # not supply. Stamping those True produced contradictory flags
    # (system_generated=True, self_defined=True) on the no-parent path, and
    # BMR-Review's inherited-discount rule reads both flags.
    for attr in ("titles", "directors", "actors", "countries",
                 "original_languages", "version_languages", "assoc_orgs",
                 "alt_ids"):
        for element in getattr(full, attr, None) or []:
            if hasattr(element, "self_defined"):
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
    title_error = _apply_title(full, parent_full, ctype, prov)

    for field, attr in attrs.items():
        if field not in INHERITABLE_FIELDS or field in NEVER_INHERITED:
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
    # report them under the single canonical name.
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
        prov.setdefault("Credits", "inherited")

    _attach(full, prov)
    if title_error is not None:
        # Inheritance has run, so the partial is complete -- including the
        # parent's title, picked up by the loop above because generation left
        # the field empty. Same contract as build_full_base.
        title_error.partial, title_error.provenance = full, dict(prov)
        raise title_error
    return full


def _apply_title(
    full: Any, parent_full: Any, ctype: str, prov: dict,
) -> TitleConstructionError | None:
    """Season/Episode get a constructed title; other child types inherit one.

    Runs BEFORE field inheritance (operator ruling 2026-08-30), so the record
    still carries only its own data. RETURNS a TitleConstructionError rather
    than raising it: the caller has to finish inheriting before the error goes
    out, or `exc.partial` would hand back a base that is missing every
    inherited field.
    """
    titles = getattr(full, "titles", None)
    if titles is None:
        return None

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
            full.titles = [made]
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
        parent_titles = getattr(parent_full, "titles", None) or []
        if parent_titles:
            inherited = copy.deepcopy(parent_titles)
            for element in inherited:
                if hasattr(element, "self_defined"):
                    element.self_defined = False
            full.titles = inherited
            prov["ResourceName"] = "inherited"
    return None


def _best_record_title(rec: Any) -> str:
    for title in getattr(rec, "titles", None) or []:
        text = getattr(title, "text", None)
        if isinstance(text, str) and text.strip():
            return text.strip()
    return ""


def _clone_title(parent_full: Any, text: str, title_class: str) -> Any:
    """Build a title element of whatever class the parent's titles use.

    Constructing it from the parent's own type avoids importing a consumer
    model. If the parent has no titles to copy the shape from, there is
    nothing to build and the child stays untitled — which the title
    comparator already handles by dropping the field.
    """
    template = None
    for title in getattr(parent_full, "titles", None) or []:
        template = title
        break
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
