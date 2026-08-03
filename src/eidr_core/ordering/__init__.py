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
"""
from __future__ import annotations

__all__ = [
    "ck", "is_internal_class", "is_resource_class", "title_bucket",
    "title_sort_key", "is_shortdoi", "altid_kind", "altid_canonical_key",
    "altid_display_key", "altid_collapsed_canonical_key",
]


def ck(s) -> str:
    """Casefold sort key; None-safe. The §3.x rule: keys fold, values don't."""
    return str(s if s is not None else "").casefold()


# ── titles (§4.1 / title-display-order.md) ─────────────────────────────────

def is_internal_class(title_class) -> bool:
    return ck(title_class) == "internal"


def is_resource_class(title_class) -> bool:
    """Title classes that mark the primary/ResourceName in sources that carry
    the distinction as a class rather than a structural flag."""
    return ck(title_class) in ("release", "resource")


def title_bucket(title_class, is_resource: bool = False) -> int:
    """The ratified three buckets: 0 = ResourceName (ALWAYS first — even when
    its class is Internal), 1 = non-Internal alternates, 2 = Internal
    alternates. ResourceName identification is structural (`is_resource`) or
    by a release/resource class; the Internal check never outranks it."""
    if is_resource or is_resource_class(title_class):
        return 0
    if is_internal_class(title_class):
        return 2
    return 1


def title_sort_key(text, title_class=None, is_resource: bool = False) -> tuple:
    """Full display/canonical sort key: (bucket, casefold(text))."""
    return (title_bucket(title_class, is_resource), ck(text))


# ── alt IDs (§4.2 / altid-display-order.md) ────────────────────────────────

def is_shortdoi(id_type, domain) -> bool:
    """ShortDOI test (display suppression + evaluation exclusion; the
    canonical/export form RETAINS ShortDOI — do not use this in exporters)."""
    return ck(id_type) == "shortdoi" or ck(domain) == "shortdoi"


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


def altid_display_key(id_type, domain, value) -> tuple:
    """Display order: IMDb entries first, then canonical (kind, value).
    Callers implement the display rule as: drop entries where
    ``is_shortdoi(...)``, then stable-sort by this key. (The API Shim's
    contract — altid-display-order.md.)"""
    imdb_first = 0 if ck(id_type) == "imdb" else 1
    return (imdb_first, *altid_kind(id_type, domain), ck(value))


def altid_collapsed_canonical_key(kind, value) -> tuple:
    """Canonical key for sources whose (Type, Domain) is already collapsed
    into a single Kind column (XML_to_JSON star mode): (casefold(Kind),
    casefold(value)). Ordering among same-shaped entries is identical to the
    structured composite."""
    return (ck(kind), ck(value))
