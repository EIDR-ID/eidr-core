"""Canonical + display ordering for EIDR records — THE shared implementation.

Implements the ratified `specs/normalized-record.md` (§3.x casefold, §4.1
titles, §4.2 alt IDs; operator 2026-07-29) and the two API Shim handoffs
(`specs/title-display-order.md`, `specs/altid-display-order.md`). Extracted
2026-08-02 (register R2) so XML_to_JSON's star-mode export and BMR-Review's
`render_record` stop hand-maintaining the same rules in parallel — both now
call these key functions; ordering fixtures in BMR-Review
`tests/test_ordering.py` pin the worked examples from the handoff docs.

Shape-neutral by design: callers pass plain values (text, class strings,
type/domain/value), never model objects or dicts, so the same functions serve
BMR-Review's dataclasses, XML_to_JSON's dict entries, and any future
consumer. All comparisons use Unicode ``str.casefold()`` on the KEY only —
emitted values keep their original case.

Three Alt ID orders, one per surface: canonical (``altid_canonical_key``,
no IMDb preference, ShortDOI kept), display (``altid_display_key``, IMDb
first, caller drops ShortDOI) and star export (``altid_star_key``, IMDb
first, ShortDOI kept; operator 2026-11-12, 0.72.0). ``is_imdb`` is the
single IMDb test behind the two IMDb-first keys.

Titles are placed STRUCTURALLY: the caller says which title is the
ResourceName (``is_resource``). A Title Class never makes a title the
ResourceName; the only class that moves a title is Internal (operator
ruling 2026-10-19; 0.69.0 -- "Ignore title classes, except for Internal and
transliterated").
"""
from __future__ import annotations

__all__ = [
    "ck", "is_internal_class", "title_bucket",
    "title_sort_key", "is_shortdoi", "altid_kind", "altid_canonical_key",
    "altid_display_key", "altid_collapsed_canonical_key",
    "is_imdb", "altid_star_key",
]


def ck(s) -> str:
    """Casefold sort key; None-safe. The §3.x rule: keys fold, values don't."""
    return str(s if s is not None else "").casefold()


# ── titles (§4.1 / title-display-order.md) ─────────────────────────────────

def is_internal_class(title_class) -> bool:
    """Is this the Internal Title Class (casefolded)? EIDR's own machine
    translations carry it; it sends an ALTERNATE to the last bucket."""
    return ck(title_class) == "internal"


# `is_resource_class` (release/resource class => ResourceName) was REMOVED
# at 0.69.0. It let an AlternateResourceName of class Release sort above the
# real ResourceName, against the specs' "identified structurally, never by
# its Title Class"; the operator ruled "Ignore title classes, except for
# Internal and transliterated" (ruling 2026-10-19; 0.69.0). No consumer
# imported it. Do not reintroduce a class-based ResourceName test: a caller
# with no structural flag must derive one (e.g. md:ResourceName, or entry 0
# of a ResourceName-first list), not guess from the class.


def title_bucket(title_class, is_resource: bool = False) -> int:
    """The ratified three buckets: 0 = ResourceName (ALWAYS first — even when
    its class is Internal), 1 = non-Internal alternates, 2 = Internal
    alternates.

    ResourceName identification is STRUCTURAL only: ``is_resource`` is the
    caller's statement that this is the ``md:ResourceName``. No Title Class
    puts a title in bucket 0 -- an alternate of class Release or Resource is
    an ordinary alternate (bucket 1). Of the classes, only Internal moves a
    title, and never the ResourceName. ``transliterated`` (EIDR's own
    transliterations) orders as an ordinary alternate: the operator
    confirmed on 2026-10-19 that only Internal is special for ordering, and
    that what sets transliterated titles apart is only that the language
    tool creates them when none exists.

    A caller that passes only a class gets bucket 1 or 2, never 0: such a
    caller must pin its ResourceName itself, as XML_to_JSON's star mode does
    by position.
    """
    if is_resource:
        return 0
    if is_internal_class(title_class):
        return 2
    return 1


def title_sort_key(text, title_class=None, is_resource: bool = False) -> tuple:
    """Full display/canonical sort key: (bucket, casefold(text)).

    ``is_resource`` must come from the record's structure (see
    :func:`title_bucket`); the class alone never identifies the ResourceName
    (operator ruling 2026-10-19; 0.69.0)."""
    return (title_bucket(title_class, is_resource), ck(text))


# ── alt IDs (§4.2 / altid-display-order.md) ────────────────────────────────

def is_shortdoi(id_type, domain) -> bool:
    """ShortDOI test (display suppression + evaluation exclusion; the
    canonical/export form RETAINS ShortDOI — do not use this in exporters).

    Whitespace around either half is ignored (0.47.0, BMR-Review's proposal):
    a padded ``"ShortDOI "`` was never a real third-party identifier, and the
    private copy inside ``compare.cmp_alt_ids`` already stripped -- the two
    disagreed on exactly that input, and it now calls this one."""
    return ck(id_type).strip() == "shortdoi" or ck(domain).strip() == "shortdoi"


def altid_kind(id_type, domain) -> tuple:
    """The ratified kind composite: (casefold(Type), casefold(Domain)).
    Missing halves participate as "" — so domain-only (Proprietary) entries
    group under ("", domain) and sort before named Types; deterministic and
    intended (altid-display-order.md worked example)."""
    return (ck(id_type), ck(domain))


def altid_canonical_key(id_type, domain, value) -> tuple:
    """Canonical order: (kind, casefold(value)) — same-kind IDs adjacent
    (e.g. two distinct IMDb IDs), ShortDOI retained. For export/comparison
    surfaces."""
    return (*altid_kind(id_type, domain), ck(value))


def is_imdb(id_type) -> bool:
    """The one IMDb test the IMDb-first orders share: the Type alone,
    casefolded, equals ``imdb``. A Proprietary entry whose Domain is
    ``imdb.com`` is NOT IMDb here, as the display worked example has always
    shown. Not whitespace-stripped (unlike ``is_shortdoi``): stripping would
    move a padded entry, a behaviour change no ruling asked for.

    Public since 0.72.0, so the star key and the display key cannot grow two
    definitions of IMDb (XML_to_JSON had to read it out of
    ``altid_display_key(...)[0]``)."""
    return ck(id_type) == "imdb"


def altid_display_key(id_type, domain, value) -> tuple:
    """Display order: IMDb entries first, then canonical (kind, value).
    Callers implement the display rule as: drop entries where
    ``is_shortdoi(...)``, then stable-sort by this key. (The API Shim's
    contract — altid-display-order.md.)"""
    imdb_first = 0 if is_imdb(id_type) else 1
    return (imdb_first, *altid_kind(id_type, domain), ck(value))


def altid_collapsed_canonical_key(kind, value) -> tuple:
    """Canonical key for sources whose (Type, Domain) is already collapsed
    into a single Kind column (XML_to_JSON star mode): (casefold(Kind),
    casefold(value)). Ordering among same-shaped entries is identical to the
    structured composite."""
    return (ck(kind), ck(value))


def altid_star_key(id_type, kind, value) -> tuple:
    """Star export order (operator ruling 2026-11-12; normalized-record
    §4.2 v1.2): IMDb first, then the collapsed Kind, then the value, all
    casefolded. ShortDOI is RETAINED -- suppressing it stays a display rule.

    ``id_type`` is the entry's Type BEFORE the star shape collapses Type and
    Domain into one Kind, because the collapse loses it (a Proprietary
    ``imdb.com`` entry and an ``IMDB`` entry must not both lead). The
    ruling's "keep any Alt ID already floated to the top" changes nothing:
    star had no preference before. This is the star SHAPE's key; canonical
    surfaces (hashing, comparison) keep ``altid_canonical_key`` and
    ``altid_collapsed_canonical_key``, which have no IMDb preference."""
    return (0 if is_imdb(id_type) else 1, *altid_collapsed_canonical_key(kind, value))
