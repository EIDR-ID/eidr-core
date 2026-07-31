# Title Display Ordering — handoff for the API Shim project

**Audience:** the API Shim team (a separate project from the EIDR portfolio
tools). **Why you:** the matching system does not sort title entries — it presents them in
the order the API Shim delivers them. So the Shim must emit titles already in
the display order below; every downstream review surface (the matching system, the
De-Duplication Review UI) then shows them consistently.
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
  Class.

## Worked example

Input (API order, unsorted alternates):

| Element | Title Class | System Generated | Text |
|---|---|---|---|
| ResourceName | Internal | | Working Cut 7 |
| AlternateResourceName | | | Zeta Release Title |
| AlternateResourceName | Internal | | Alpha Internal Label |
| AlternateResourceName | | yes | Beta Generated Title |

Output (display order):

| Text | Why here |
|---|---|
| Working Cut 7 | ResourceName always first — even though Internal (marked Internal in the UI) |
| Beta Generated Title | non-Internal alternates, alphabetical (marked SystemGenerated in the UI) |
| Zeta Release Title | non-Internal alternates, alphabetical |
| Alpha Internal Label | Internal alternates last (marked Internal in the UI) |

(This exact input/output is verified against the reference implementation.)

## Reference implementation

The De-Duplication Review pipeline applies the identical rule in BMR-Review
`eidr_dedup_score/report.py::render_record` (Python, `title_rank`). If
behavior ever seems to differ between the Shim and the review tools, that
function and this file are the two artifacts to reconcile — via the operator,
who owns both specs.
