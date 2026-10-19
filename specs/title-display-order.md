# Title Display Ordering — handoff for the API Shim project

**Version:** v1.1 (2026-10-19). v1 was the 2026-07-30 handoff. See the
change history at the end.

**Audience:** the API Shim team (a separate project from the EIDR portfolio
tools). **Why you:** the upstream matching system does not sort title
entries — it presents them in the order the API Shim delivers them. So the
Shim must emit titles already in the display order below; every downstream
review surface (that system, the De-Duplication Review UI) then shows them
consistently.
**Source of truth:** `normalized-record.md` §4.1, ratified by the operator
2026-07-29. Sibling document: `altid-display-order.md` (the Alternate ID
equivalent).

## The rule, in words — three buckets

1. **ResourceName first, always.** There is only ever one ResourceName
   (`md:ResourceName`), so it is not sorted — it simply leads. It stays
   first **even when its Title Class is Internal**.
2. **AlternateResourceNames that are NOT Internal** (0..n) — alphabetical,
   case-insensitive (Unicode casefold).
3. **AlternateResourceNames that ARE Internal** (0..n) — last, alphabetical,
   case-insensitive.

**Title Class does not place a title, except Internal** (operator ruling
2026-10-19: "Ignore title classes, except for Internal and transliterated").
Which title is the ResourceName is a fact about the record's structure, never
about its class: an AlternateResourceName of class Release, Resource or any
other class except Internal is an ordinary bucket-2 alternate, and does not
move ahead of the ResourceName. Internal sends an alternate to bucket 3 and
is visually marked. The ruling's other named exception, `transliterated`
(EIDR's own transliterations), has no ordering treatment in this spec: it
orders as an ordinary alternate.

Two display annotations ride along (they do not affect order):

* **SystemGenerated** and **Internal** titles must be **visually marked** in
  review surfaces, to signal their limited impact on de-duplication.
* Ordering is presentation only. Comparison/scoring is order-independent:
  ALL titles participate (Internal and SystemGenerated at diminished weight —
  never silently excluded; the title field is dropped only when BOTH the
  submitted and the candidate side carry nothing but SystemGenerated titles).

## Pseudocode (language-neutral)

```
function display_order(resource_name, alternate_names):
    # resource_name: the single md:ResourceName entry (never sorted)
    # alternate_names: the md:AlternateResourceName entries

    function is_internal(t):
        return casefold(t.title_class or "") == "internal"

    function sort_key(t):
        return casefold(t.text)

    non_internal = stable_sort([t for t in alternate_names if not is_internal(t)],
                               by=sort_key)
    internal     = stable_sort([t for t in alternate_names if is_internal(t)],
                               by=sort_key)

    return [resource_name] + non_internal + internal
```

Notes:
* `casefold` = full Unicode case folding (lowercase fallback acceptable).
* Sorts must be **stable** so equal keys keep their input order.
* The ResourceName is identified STRUCTURALLY (the `md:ResourceName`
  element), never by position in a combined list and never by its Title
  Class. A source that delivers one combined list must carry the
  ResourceName flag with it; it must not infer the ResourceName from a
  class such as Release (v1.1).

## Worked example

Input (API order, unsorted alternates):

| Element | Title Class | System Generated | Text |
|---|---|---|---|
| ResourceName | Internal | | Working Cut 7 |
| AlternateResourceName | | | Zeta Release Title |
| AlternateResourceName | Internal | | Alpha Internal Label |
| AlternateResourceName | | yes | Beta Generated Title |
| AlternateResourceName | Release | | Aardvark Festival Title |

Output (display order):

| Text | Why here |
|---|---|
| Working Cut 7 | ResourceName always first — even though Internal (marked Internal in the UI) |
| Aardvark Festival Title | non-Internal alternates, alphabetical — class Release does not make it the ResourceName |
| Beta Generated Title | non-Internal alternates, alphabetical (marked SystemGenerated in the UI) |
| Zeta Release Title | non-Internal alternates, alphabetical |
| Alpha Internal Label | Internal alternates last (marked Internal in the UI) |

(This exact input/output is verified against the reference implementation:
eidr-core `tests/test_ordering.py` reads these two tables and sorts the input
with `eidr_core.ordering.title_sort_key`. Before v1.1 the shared key put a
Release-class alternate in the ResourceName bucket, so "Aardvark Festival
Title" sorted ABOVE "Working Cut 7".)

## Reference implementation

The De-Duplication Review pipeline applies the identical rule in BMR-Review
`eidr_dedup_score/report.py::render_record` (Python, `title_rank`), which
calls the shared key `eidr_core.ordering.title_sort_key`. If
behavior ever seems to differ between the Shim and the review tools, that
function and this file are the two artifacts to reconcile — via the operator,
who owns both specs.

## Change history

* **v1.1 — 2026-10-19.** Title Class no longer places a title, except
  Internal (operator ruling 2026-10-19: "Ignore title classes, except for
  Internal and transliterated"; from the 2026-10-02 dictionary audit). The
  rule and pseudocode already identified the ResourceName structurally, but
  the shared key `eidr_core.ordering.title_bucket` also put any title of
  class Release or Resource in the ResourceName bucket, so such an
  alternate could sort above the real ResourceName. eidr-core 0.69.0
  removes that (and the `is_resource_class` helper). The worked example
  gains a Release-class alternate to pin it. `transliterated` is named by
  the ruling but has no ordering treatment here; it orders as an ordinary
  alternate.
* **v1 — 2026-07-30.** The handoff, from `normalized-record.md` §4.1 as
  ratified 2026-07-29.
