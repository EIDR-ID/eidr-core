# Alt ID Display Ordering — handoff for the API Shim project

**Audience:** the API Shim team (a separate project from the EIDR portfolio
tools). **Why you:** the matching system does not sort Alternate ID entries — it presents
them in the order the API Shim delivers them. So the Shim must emit Alt IDs
already in the display order below; every downstream review surface (the matching system,
the De-Duplication Review UI) then shows them consistently.
**Source of truth:** `normalized-record.md` §4.2, ratified by the operator
2026-07-29. Sibling document: `title-display-order.md` (the title-ordering
equivalent).

## The rule, in words

1. **Suppress ShortDOI.** Entries whose Type or Domain is `ShortDOI`
   (case-insensitive) are omitted: ShortDOI is not used in de-dupe
   evaluation and serves no purpose in human review.
2. **IMDb first.** IMDb is the most-used Alt ID, so all IMDb entries come
   before everything else.
3. **Then group by kind, ascending.** "Kind" is the composite of **Type and
   Domain** (an entry has one or the other, sometimes both). Compare
   case-insensitively (Unicode casefold).
4. **Within a kind, sort by value, ascending** (casefold). Two distinct IDs
   of the same kind (e.g. two IMDb IDs) therefore sit adjacent — both must
   be shown; never deduplicate distinct values.

Sorting is presentation only: it never changes evaluation, and the Relation
semantics (empty Relation ≡ `IsSameAs`) are untouched.

## Pseudocode (language-neutral)

```
function display_order(alt_ids):
    visible = [a for a in alt_ids
               if casefold(a.type)   != "shortdoi"
              and casefold(a.domain) != "shortdoi"]

    function sort_key(a):
        imdb_first = 0 if casefold(a.type) == "imdb" else 1
        kind       = (casefold(a.type or ""), casefold(a.domain or ""))
        return (imdb_first, kind, casefold(a.value or ""))

    return stable_sort(visible, by=sort_key)
```

Notes:
* `casefold` = full Unicode case folding (falls back to lowercase if the
  platform lacks it; Alt ID types/domains are ASCII in practice).
* The sort must be **stable** so equal keys keep their input order.
* Missing Type or Domain participates as the empty string — entries with
  only a Domain (Proprietary IDs) group by `("", domain)`.

## Worked example

Input (API order, unsorted):

| Type | Domain | Value |
|---|---|---|
| ShortDOI | | 10/abc12 |
| | themoviedb.org/movie | 603 |
| IMDB | | tt0234215 |
| ISAN | | 0000-0001-8CFA-0000-I-0000-0000-K |
| | imdb.com | tt0133093 |
| IMDB | | tt0133093 |

Output (display order):

| Type | Domain | Value | Why here |
|---|---|---|---|
| IMDB | | tt0133093 | IMDb first; values ascending |
| IMDB | | tt0234215 | IMDb first; values ascending |
| | imdb.com | tt0133093 | kind ("", imdb.com) — empty Type sorts before named Types |
| | themoviedb.org/movie | 603 | kind ("", themoviedb.org/movie) |
| ISAN | | 0000-0001-8CFA-… | kind ("isan", "") |
| ~~ShortDOI~~ | | ~~10/abc12~~ | suppressed |

(This exact input/output is verified against the reference implementation.)

(The kind composite compares Type before Domain, so type-less domain-only
entries — empty-string Type — sort before named-Type entries alphabetically;
that is the intended, deterministic outcome of the composite. If the operator
ever prefers domain-keyed grouping to interleave with named types, that is a
one-line change to the `kind` tuple — coordinate through the portfolio specs,
not locally.)

## Reference implementation

The De-Duplication Review pipeline applies the identical rule in BMR-Review
`eidr_dedup_score/report.py::render_record` (Python). If behavior ever seems
to differ between the Shim and the review tools, that function and this file
are the two artifacts to reconcile — via the operator, who owns both specs.
