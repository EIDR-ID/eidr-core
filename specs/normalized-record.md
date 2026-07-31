# Normalized EIDR Record — field model & canonical ordering (SPEC v1)

**Status: ✅ RATIFIED with amendments by the operator, 2026-07-29** (register
Phase 2.1). The amendments are folded in below: §3 field-model corrections
(Parent scope, sequence-number scoping, Conversion Table as the field
authority), §4.1 (title scoring semantics + the three-bucket presentation
order), §4.2 (canonical (kind, value) sort; IMDb-first + ShortDOI-suppression
confirmed as display rules — see the API Shim handoff,
`altid-display-order.md`). Engine-behavior gaps surfaced by §4.1 are flagged
in §7 for the next BMR engine cycle.
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
| `Parent` | string | parent EIDR ID — ALL child records (Season, Episode, Edit, Clip, Manifestation), not just Season/Episode |
| `SequenceNumber` | int | Seasons ONLY: `ExtraObjectMetadata/SeasonInfo/SequenceNumber` |
| `DistributionNumber` | int/string | Episodes ONLY: `ExtraObjectMetadata/EpisodeInfo/SequenceInfo/md:DistributionNumber` |
| `MadeForRegion` | list⟨code⟩ | Edits/Manifestations only; ordering §3.2 |

Sub-models:
* **Title** = `{ Title, TitleClass?, SystemGenerated?, Language? }`.
* **Org** = `{ PartyID?, Role?, Name: [DisplayName, …AlternateNames] }`.
* **AltID** = `{ AltID (value), Kind (domain if present else type), Relation? }`.

**Field authority (operator, 2026-07-29):** the per-type fields are NOT
enumerated here. The authoritative cross-reference of every EIDR record field
is `D:\Software\XML_to_JSON\XML_to_JSON-ConversionTable.xlsx`. Any EIDR field
can appear in a BMR spreadsheet (technically the SELF-DEFINED record, not the
full record); the matching system evaluates only the fields in the Conversion Table's
**StarSchema** column. This spec pins the ordering primitives and the
comparison-bearing families the tools share.

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

### 4.1 Titles — RATIFIED 2026-07-29

**Evaluation (scoring) — order-independent; class affects WEIGHT, never
membership:**
* ALL titles — ResourceName and every AlternateResourceName — participate in
  comparison equally. Title Class is ignored for scoring, with two
  diminished-impact cases:
  * `Internal` titles: diminished value is acceptable, but they must NOT be
    ignored entirely.
  * `SystemGenerated` titles: diminished impact; the title field is ignored
    entirely ONLY when both the submitted and the candidate side are
    SystemGenerated.

**Presentation / canonical serialization — three buckets:**
1. **ResourceName** — always first. There is only ever one, so no sort; it
   stays first EVEN IF its class is Internal.
2. **AlternateResourceNames excluding Internal** (0..n) — alphabetical,
   casefold.
3. **AlternateResourceNames that are Internal** (0..n) — last, alphabetical,
   casefold.

In the display, SystemGenerated and Internal titles are visually marked to
indicate their limited impact on de-duplication.

**API Shim handoff:** the standalone document for the (separate) API Shim
project is **`title-display-order.md`** in this directory (narrative +
pseudocode + worked example verified against the reference implementation) —
sibling of `altid-display-order.md`.

### 4.2 Alt IDs — RATIFIED 2026-07-29

**Canonical order:** sort by `(casefold(kind), casefold(value))`, where
**kind is the composite of Type and Domain**. Groups same-kind IDs adjacently
(so two distinct IMDb IDs sit together — ties into the 2026-07-25 multi-value
fix). ShortDOI is retained in the canonical/export form (it is a valid Alt ID
type).

**Display order (ratified as a display rule, applied on top of canonical):**
1. **Suppress ShortDOI** — it is not used in de-dupe evaluation and serves no
   purpose in human review.
2. **IMDb first** — the most-used Alt ID; presenting it first has real review
   value. Within IMDb, and within every other kind group, order is
   `(casefold(kind), casefold(value))` as canonical.

**API Shim note:** the matching system does not sort Alt ID entries — it presents them in
API-Shim order, so **the API Shim must emit the display order**. The
standalone handoff for that (separate) project is
**`altid-display-order.md`** in this directory: narrative + language-neutral
pseudocode + worked example.

## 5. Conformance

Phase 2.3 adds golden-pair fixtures pinning §3–§4 output. Each program runs its
own ordering implementation against them; a spec change bumps the version and
regenerates expectations, so a lagging program fails its conformance test — the
cross-project drift alarm for ordering (complementary to the file-hash drift
check, which deliberately does NOT track these region-level rules).

## 6. Decisions — RESOLVED (operator, 2026-07-29)

1. §4.1 titles: ratified as amended — evaluation is order-independent with
   class-based *weighting* (Internal/SystemGenerated diminished, never
   silently excluded except the both-sides-SystemGenerated case);
   presentation = the three-bucket order with ResourceName first even when
   Internal.
2. §4.2 alt IDs: canonical `(casefold(kind), casefold(value))` with kind =
   Type+Domain composite; IMDb-first and ShortDOI-suppression confirmed as
   DISPLAY rules; ShortDOI excluded from evaluation.
3. §2 canonical-vs-display split: confirmed.
4. §3: Parent applies to all child records; sequence numbers scoped to
   Season (`SeasonInfo/SequenceNumber`) and Episode
   (`EpisodeInfo/SequenceInfo/md:DistributionNumber`); the Conversion Table
   is the field authority; the matching system evaluates StarSchema-column fields only.

## 7. Engine gaps surfaced by §4.1 (for the next BMR engine cycle)

The ratified title-scoring semantics differ from the CURRENT engine
(`eidr_core.compare` `cmp_titles`/`select_titles`) in two ways:

1. **Internal titles are currently EXCLUDED from evaluation** entirely;
   ratified: include with diminished value.
2. **The title field is currently dropped when EITHER side has only
   system-generated titles**; ratified: diminished impact when one side is
   SystemGenerated, dropped only when BOTH sides are.

These are engine-behavior changes with tuning implications (the diminished
weights are compare-spec knobs — e.g. `SYSTEM_TITLE_DISCOUNT`, and a new
Internal discount). They belong in the next engine-tuning cycle alongside the
human-results review: implement → add golden pairs pinning both behaviors →
bump the compare-spec version. Flagged in BMR-Review's CLAUDE.md.
