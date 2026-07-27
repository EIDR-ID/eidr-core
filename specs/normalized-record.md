# Normalized EIDR Record — field model & canonical ordering (SPEC v1)

**Status:** draft for operator ratification (register Phase 2.1, 2026-07-27).
**Consumers:** the Python suite (eidr-wikidata, BMR-Review, XML_to_JSON) and the
node.js side (eidr-ui-nextjs / De-Dupe UI). This is a language-neutral contract:
each program implements it, and conformance is pinned by the golden-pair corpus
(Phase 2.3). The eventual `eidr_core.ordering` module (Phase 3) is the reference
Python implementation.

Derived from the two current implementations:
* XML_to_JSON `xml_to_json_exporter.py` star-mode `_star_*` normalizers.
* BMR-Review `eidr_dedup_score/report.py::render_record`.

---

## 1. Why this exists

Two independent programs canonicalize the same EIDR record for the same reason —
a deterministic, presentation-neutral form so two records can be compared, hashed,
or diffed without spurious differences from field order, case, or DB insertion
order. They are maintained in parallel and have **drifted** in two fields (§4).
This spec makes the canonical order single-sourced so they can converge and a
golden-pair test catches future drift.

## 2. Scope — canonical vs display order

Two distinct orderings, kept separate:

* **Canonical order** (this spec): presentation-neutral and deterministic. Used
  for comparison, hashing, golden-pair conformance, and canonical JSON export.
* **Display order**: a human-review presentation a tool MAY apply *on top of*
  the canonical form (e.g. BMR-Review surfacing the IMDb ID or the Resource
  title first for a reviewer). Display order is explicitly NOT part of the
  normalized record and must never be used where canonical order matters.

Conflating the two is the root of the §4 divergences: BMR-Review's display
preferences leaked into what should be the canonical form.

## 3. Field model

A normalized record is a mapping of the fields below. Absent fields are omitted
(not null). Codes and names are carried verbatim except where a normalizer is
specified. Structural fields anchor identity; list fields carry the comparison
signal.

| Field | Shape | Notes |
|---|---|---|
| `ID` | string | EIDR DOI (`10.5240/…`); omitted for registration output |
| `StructuralType` | string | Abstraction / Performance / Digital / Composite |
| `ReferentType` | string | Movie / TV / Short / Web / Series / Season / Episode / Supplemental |
| `Mode` | string | Audio / Visual / AudioVisual |
| `ResourceName` | list⟨Title⟩ | see Title sub-model; ordering §4.1 |
| `OriginalLanguage` | list⟨code⟩ | language codes; ordering §3.2 |
| `VersionLanguage` | list⟨code⟩ | language codes; ordering §3.2 |
| `CountryOfOrigin` | list⟨code⟩ | country codes (alpha-2 active / alpha-4 obsolete / M49 region); ordering §3.2 |
| `AssociatedOrg` | list⟨Org⟩ | PartyID, Role, Name[]; ordering §3.3 |
| `Credits` | list⟨string⟩ | flattened cast/crew names; ordering §3.4 |
| `ReleaseDate` | string | ISO date (precision-aware: YYYY / YYYY-MM / YYYY-MM-DD) |
| `ApproximateLength` | string/int | duration (minutes) |
| `Status` | string | publication status |
| `AlternateID` | list⟨AltID⟩ | AltID(value), Kind(domain\|type), Relation; ordering §4.2 |
| `Parent` | string | parent EIDR ID (Season/Episode) |
| `SequenceNumber` | int | season/episode number |
| `MadeForRegion` | list⟨code⟩ | Edits/Manifestations only; ordering §3.2 |

Sub-models:
* **Title** = `{ Title, TitleClass?, SystemGenerated?, Language? }`.
* **Org** = `{ PartyID?, Role?, Name: [DisplayName, …AlternateNames] }`.
* **AltID** = `{ AltID (value), Kind (domain if present else type), Relation? }`.

(Exhaustive per-type fields — episodes, seasons, edits, composites, compilation
entries/elements — follow the same ordering primitives; see the source
normalizers. This spec pins the comparison-bearing families both tools share.)

## 3.x Casefold

Everywhere this spec says "casefold", it means Unicode `str.casefold()` (full
case folding, not ASCII `lower()`), applied to the sort KEY only — emitted values
keep their original case. Both implementations already use this.

### 3.2 Code lists (language, country, region) — CANONICAL, agreed

Distinct values, sorted ascending by casefold. Deduplication is by casefolded
value. (XML_to_JSON `_star_langs`/`_star_sorted_string_array`; BMR-Review
`codes_view`. Aligned 2026-07-25 after fixing XML_to_JSON's case-sensitive
language/country sorts — register Phase 0.2.)

### 3.3 Associated orgs — CANONICAL, agreed

Org entries sorted ascending by casefold of their Display Name (first Name
element); entries with no name sort last. Within an org, the Display Name stays
first and the Alternate Names follow, sorted ascending by casefold. (XML_to_JSON
`_star_associated_orgs`; BMR-Review org view — behaviour matches.)

### 3.4 Credits — CANONICAL, agreed

Each credit contributes BOTH its DisplayName and its SortName as separate strings
(e.g. a romanized name and its native-script form); the whole flat list is sorted
ascending by casefold. (XML_to_JSON `_star_credit_names`; BMR-Review credit view
— behaviour matches.)

## 4. Divergences to reconcile (operator decision)

Both fields below differ between the two implementations. Recommended canonical
rule stated; **the display preference is preserved as an explicit display-layer
step (§2), not baked into the canonical form.**

### 4.1 Titles — DIVERGENT

* XML_to_JSON: entry at position 0 is treated as primary and kept first; the rest
  are sorted by Title casefold. Primary is POSITIONAL.
* BMR-Review `title_rank`: grouped by CLASS — Resource Name (`is_resource`, or
  class `release`/`resource`) → top; `internal` → bottom; everything else →
  middle; each group sorted by text casefold.

**Recommended canonical rule:** class-based, like BMR-Review, because position-0
is fragile (depends on upstream list order). Canonical title order =
`(rank, casefold(text))` where rank is `0` for the Resource/primary title, `1`
for ordinary alternates, `2` for `internal`. XML_to_JSON adopts the class-based
rank in place of its positional primary.

### 4.2 Alt IDs — DIVERGENT

* XML_to_JSON: sorted by AltID **value** casefold. Presentation-neutral.
* BMR-Review: sorted `(IMDb-first, casefold(domain), casefold(type))` — value is
  not a key at all — and ShortDOI entries are excluded from the view.

**Recommended canonical rule:** sort by `(casefold(kind), casefold(value))` where
kind = domain if present else type — presentation-neutral and stable, and unlike
XML_to_JSON's value-only key it groups same-kind IDs together (so two IMDb IDs
sit adjacent). ShortDOI is **retained** in the canonical form (dropping it is a
BMR-Review display choice, and ShortDOI is a valid Alt ID type). BMR-Review's
"IMDb-first" and "hide ShortDOI" become an explicit display-layer re-sort applied
after canonicalization, not part of the normalized record.

> Rationale for keeping multi-value groups adjacent ties into the 2026-07-25 Alt
> ID fix (two distinct IMDb IDs must both survive): canonical order groups them by
> kind so a reviewer/diff sees them together.

## 5. Conformance

Phase 2.3 adds golden-pair fixtures pinning §3–§4 output. Each program runs its
own ordering implementation against them; a spec change bumps the version and
regenerates expectations, so a lagging program fails its conformance test — the
cross-project drift alarm for ordering (complementary to the file-hash drift
check, which deliberately does NOT track these region-level rules).

## 6. Open decisions for the operator

1. Ratify §4.1 (class-based canonical title order) and §4.2 (kind+value canonical
   Alt ID order; ShortDOI retained).
2. Confirm the canonical-vs-display split (§2): BMR-Review keeps IMDb-first / hide
   ShortDOI as a display layer, not in the normalized record.
