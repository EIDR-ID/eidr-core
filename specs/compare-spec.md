# compare-spec — the unified engine's tuning surface (companion doc)

**The runtime file is `src/eidr_core/specs/compare-spec.json`** (inside the
package so `eidr_core.compare.spec.load_spec` finds it via importlib.resources
in any install mode; override with the `EIDR_COMPARE_SPEC` env var for
experiments). **The version is the JSON's `$spec.version`;** this document no
longer repeats it, because the copy here went stale (it read 2.0.0 until
2.18.0). 2.0.0 was the 1:1 externalization of BMR-Review's `config.py` as of
2026-07-28 (that file's annotated original is preserved in BMR-Review git
history, commit `17574c4` and earlier).

## Tuning workflow (the whole point)

1. Edit the JSON — **per creation type** wherever possible: the `weights`
   section is organized Basic / Series / Season / Episode / Edit /
   Compilation (+ Clip and Manifestation as `$alias` of Edit) precisely so a
   tune has constrained, type-scoped impact (operator requirement, 2026-07-27).
2. Bump `$spec.version`.
3. Run BMR-Review's tests — `tests/test_spec_loading.py` pins a scored pair
   and will fail on any behavior change: re-verify, update its expectations.
4. Commit eidr-core AND note the tune in BMR-Review's CLAUDE.md change log.
   The version bump is the cross-tool signal: golden-pair expectations
   (Phase 2.3) regenerate against it, and every consumer (work-list payloads,
   future scoring service) reports it as provenance.

## Structure

| Section | Contents |
|---|---|
| `$spec` | version, provenance, loader |
| `types` | container semantics (`set`/`frozenset`/`tuple`) restored by the loader — JSON arrays alone would silently change `in`/unpacking behavior |
| `weights` | per-creation-type `{thresholds: [lo, hi], weights: {field: w}}`; `$alias` entries share the target's object (tune Edit → Clip/Manifestation follow) |
| `values` | every other engine constant, unchanged names |
| `states` | q→state banding for UI payloads (identical ≥ 0.985 or exact; similar ≥ 0.75; below → mismatch on discriminative fields, else neutral; absent → neutral). Payload producers only — never used in scoring |
| `rationale_schema` | the explainability payload contract (additive changes only) |

## Key empirical rationale (curated from the original config.py)

These numbers were tuned against ~1,371 human decisions and observed upstream matcher
outcomes; the reasoning matters more than the values. When re-tuning, revisit
the reasoning, not just the number.

* **Scoring model.** Within a field, `accumulate()`: one matched element earns
  full first-match credit regardless of list length (1-of-100 == 1-of-1);
  extra matches add a diminishing bonus (`NL_MODIFIER` 0.75, Rovi lineage)
  capped by `FIELD_BONUS_CAP` so one long list can't dominate. Record level:
  weighted average over fields present on both sides; absent fields drop from
  the denominator (`ALWAYS_APPLICABLE` can keep a field in regardless; empty
  since 2.16.0, when a one-sided release date stopped penalising);
  calibrated per creation type onto the shared bands (<30 Reject, 30–<80
  Review, ≥80 Accept).
* **Cross-type candidates (2.16.0, operator ruling 2026-09-26).** Which pairs
  of different creation types are compared at all is an exhaustive list in
  BMR-Review's gate: a shared identity Alt ID (any pair; the only route for
  Clips and Manifestations); a user-titled Pilot/Special/Standalone or
  anthology Episode with Basic, and any Pilot also under its series title;
  Season with Series when the Season has a real title; Series/Season with
  Basic for mini/limited series; Series with a Series-class Compilation; an
  Edit with the siblings of its nearest Abstraction ancestor when its user
  title differs from the ancestor's or its class is in
  `GATE_EDIT_SPLIT_CLASSES` (`split`). Every such pair is scored on the Basic
  profile and capped at Review. `CROSSTYPE_REVIEW_FLOOR` is off: the older
  title-strong / related-Alt-ID floors no longer lift an agreeing pair.
* **Sibling-title ambiguity needs a shared anchor (2.17.0, BMR-Review T37,
  2026-09-30).** The auto-match blocker "multiple siblings under the same
  parent share this title" holds a sole Accept only when a look-alike sibling
  ALSO carries the submission's anchor -- the same full date or the same
  distribution number, where a trailing part letter is the same number (21A
  and 21B share 21) -- because a daily programme's episodes differ only by a
  date prefix the fuzzy title comparator cannot see, and the blocker had held
  20 rows a reviewer confirmed 20 of 20. A rule change with no value moved;
  pinned both ways by `sibling-title-lookalike-with-distinct-anchor-clears`
  and `sibling-title-lookalike-sharing-the-anchor-is-held`. **Precisely**
  (stated at 2.18.0; the engine has done this since 2.17.0): (1) the sibling
  is compared on the ONE anchor kind that picked the proposal -- full date,
  distribution number, house sequence, sequence number or end date; (2) an
  `alt-id` anchor keeps the gate as before, because identifiers copied
  across a set are the known source of wrong 100s; (3) an anchor kind the
  comparison does not recognise counts as SHARED, so the gate fires; (4) the
  part-letter strip applies only in the sibling comparison. (2) and (3)
  together are pinned by `sibling-title-lookalike-altid-anchor-is-held`
  (2.18.0, De-Dupe UI S-33): an engine that drops the alt-id exception and
  defaults an unknown kind to not-shared clears it.
* **Internal titles count, discounted (2.18.0, LanguageTool's request,
  BMR-Review T38; operator GO and "Accept both changes", 2026-10-02).**
  `INTERNAL_TITLE_DISCOUNT` (0.8): an Internal-class title -- a machine
  translation, mostly an English rendering of a non-English registered title
  -- takes part in title comparison with its similarity multiplied by the
  discount, on the normal path and on the Internal-only fallback alike
  (normalized-record 4.1: diminished, never ignored). Only the best aligned
  pair may be Internal-sourced: a further aligned Internal pair earns no
  accumulation bonus, because once the real titles are aligned a translation
  is left pairing with whatever title remains, and that is not a second
  agreeing title (eidr-core 0.44.0). `INTERNAL_TITLE_ACCEPT_REQUIRES_ALT_ID`
  (true): when the title agreement rests on an Internal title (the title
  meta's `internal_title_used`: an Internal pair strictly beats every real
  pair), an Accept-band score is capped at `REVIEW_TOP` unless an identity
  Alt ID agrees with no conflict -- a translated generic title with year,
  country and length is not identity evidence. Measured by BMR-Review over
  every labelled corpus: five labelled false positives become Reviews, 13
  correct cross-language bridges clear, 0 flips. Pinned by
  `internal-title-bridges-languages`,
  `internal-title-second-pair-earns-no-bonus` and
  `internal-title-carried-match-needs-alt-id-to-accept`.

**Porting requirements** (from BMR-Review's ENGINE_SYNC `BMR-20260926-1` for
2.16.0, lifted verbatim at 2.17.0 as ruled 2026-09-26). These are the places a
second engine can pass most of the corpus and still be wrong; "our" is
BMR-Review.

1. **Ancestry climbing is load-bearing.** The anthology and pilot rules test
   the SERIES, reached by climbing Episode -> Season -> Series. An engine that
   cannot climb loses real matches silently: 12 labelled anthology matches
   (Looney Tunes, Beck, Screen One, Unter Verdacht, Halifax f.p., Cinema 16)
   read as terminal no-matches in our own mirror-less harness and reach
   Review at 79.0 live.
2. **The recovered sole-Accept uses only-Rejects, never the weak-rival test.**
   A port that reuses the shortlist branch's weak-rival exception clears
   `recovered-accept-with-review-rival-is-reviewed` wrongly; that fixture
   exists to refuse it.
3. **The relationship exclusion runs BEFORE scoring**, so a targeted record
   can never become the proposal by elimination; the vendor's own candidate
   list is kept for the AUTO labels.
4. **Internal titles (2.18.0, from BMR-Review's T38 execution steps).**
   Internal titles are included at the discount; only the best aligned pair
   may be Internal-sourced (further aligned Internal pairs add no bonus);
   `internal_title_used` is true only when an Internal pair strictly beats
   every real pair (a tie credits the real title); with it set, an
   Accept-band score is capped at `REVIEW_TOP` unless an identity Alt ID
   agrees with no conflict, and the note reads "title agreement rests on an
   internal (machine-translated) title: review only (no auto-accept without
   an Alt ID)".

## Date profiles: the ANCHOR is per creation type, the SHAPE is measured

`DATE_PROFILES` (compare-spec 2.8.0) gives each creation type a table:

<!-- VALUES-CHECKED: tests/test_spec_claims.py parses this block and
     compares it to compare-spec.json. Regenerate the numbers there,
     never here. -->
```
Basic    1.00 / 0.71 / 0.22 at year gaps 0/1/2, floor 0.17
Episode  0.80 / 0.57 / 0.18 at year gaps 0/1/2, floor 0.1
```

**Two different kinds of number live in one table, and they must not be read
off each other.**

* The **ratios** are measured. BMR-Review fitted them across 3,306 human
  decisions: P(match) 0.468 / 0.332 / 0.102 at gaps 0/1/2, i.e. 1 : 0.71 :
  0.22. They describe how confidence decays with distance, and they are the
  same for every type until a type has its own labelled data.
* The **anchor** — the gap-0 value — is a judgement about that type's
  discriminating power, and it differs for a reason. A season's worth of
  episodes shares one year, so a shared year is weak evidence for an Episode
  (0.80) and strong for a film (1.00). No corpus measurement can supply this:
  the ratios say nothing about what a same-year match is worth to begin with.

BMR-Review made exactly this mistake authoring the first draft — one profile
for all types, carrying the Episode anchor — and a pinned known pair caught it
at 99.1 → 93.5. The legacy code had reached 0.60 only through
`creation_type == "Episode"`, with Basic scoring 1.0.

**Adding a profile:** copy the ratios, choose the anchor deliberately, and
check the result is monotonically non-increasing. That property is what the
pre-2.8.0 constants violated — a year-only Episode MISMATCH outscored a MATCH
for every gap below 4.42 years, because the anchor and the decay curve were on
different scales.

**Beyond the last `full_date_bands` entry, the year-level table applies** —
not an exponential tail — keyed on the **distance-equivalent** year gap rather
than the calendar gap. A distant full-date pair carries no more information
than a distant year pair (0.331 at 32–365 days against 0.332 at a one-year
gap), which is why the bands stop at about a month.

Two corrections worth keeping, because the first wording of this rule caused
both:

* **Key on distance, not the calendar.** Keying on the calendar year made the
  same 32-day distance score the gap-0 anchor within one year and the gap-1
  value across New Year — same evidence, different answer.
* **The invariant is bounded to beyond the bands.** It was first stated as
  "a full-date pair must never score above its year-only equivalent". That is
  too strong and fails *correctly* inside the bands: an Episode 3 days apart
  scores 0.95 against a year-only 0.80, which is the whole point of day-level
  precision — a shared air date discriminates where a shared year does not.
  The form that holds is: **beyond the last band, a full-date pair scores
  exactly its year-level equivalent for that distance.**

**Authoring rule:** the last band must be at least the gap-1 credit, or the
band-to-year boundary steps UP and a pair further apart scores higher. A clamp
in `cmp_release_date` keeps a flawed profile monotonic, and
`eidr_core.compare.validate_date_profile()` reports the defect rather than
letting the clamp hide it. `Basic` failed this by 0.01 at 2.8.0 (last band
0.70 against a gap-1 credit of 0.71); BMR-Review raised the band to 0.71 at
2.10.0, so both shipped profiles now validate clean and the clamp no longer
binds.

## Naming the upstream matching system

**Ruling, 2026-08-31 (operator).** eidr-core is a public repository and the
commercial matching vendor's name was redacted from it. That redaction is
scoped to **prose** — comments, narrative documentation, spec text.

It explicitly does **not** extend to:

* **engine contract strings that reviewers see.** The assessment label
  `Disagree: Tamr missed`, the recovery notes, and the reviewer-facing
  `reason` strings stay verbatim. A specification's job is to describe what
  the engine actually emits; redacting the description alone would
  desynchronize it from the Python and JS implementations, and the label
  additionally drives routing, the terminal sets and the vocabulary vectors.
* **verbatim operator quotations.** Altering a quotation to satisfy a
  redaction misrepresents it.

Raised by De-Dupe UI (S-14) after finding that its redaction could not be
completed without changing what the engine reports. The alternative — a
coordinated rename in BMR-Review — is a compare-spec bump plus regenerated
vocabulary vectors plus spec and JS updated together, which is real cost for
a string that is accurate. Accepted as-is instead.

**New code should still prefer neutral phrasing** ("the upstream matching
system") wherever it is not reproducing an emitted value.

* **What counts as a COMMON Alt ID** (operator ruling, 2026-08-30) -- the
  definition both the match and the conflict paths apply, and the one thing
  in this document a consumer may not relax:
  * the **Kind** matches: `id_type` AND the FULL domain.
    `themoviedb.org/movie` and `themoviedb.org/tv` are different sources and
    may legitimately reuse the same number.
  * the **Value** matches, compared case-insensitively.
  * the **relation** is identity: missing, null, empty, or `IsSameAs`. Any
    other relation (`IsDerivedFrom`, `IsPartOf`, `Deprecated`, ...) says the
    identifier names a DIFFERENT work, so it is evidence of nothing in
    either direction -- neither a match nor a conflict. Entries failing this
    are dropped per ENTRY, not per source, so one derived-work identifier
    cannot suppress a legitimate match under the same source.

  A **Family ID is not an Alt ID**; only third-party identifiers registered
  as AlternateID count. ShortDOIs are skipped -- a ShortDOI aliases the EIDR
  ID itself, so matching on one is circular.

  The relation clause went unenforced on the MATCH path until 2026-08-30
  (`rel_ok` was computed and consulted only for conflicts), so a shared
  Kind+Value scored a full match whatever the relation said. Because the
  same `matches` count feeds the alt-ID bonus and
  `ALT_CORROBORATION_STRONG_MIN`, a non-identity relation could release the
  unverified-alt-id and part-number Accept caps and lift a pair into Accept.
* **Alt-ID conflicts** are the only metadata-internal negative signal. The
  penalty is shaped so a SINGLE uncorroborated conflict (a registrant's
  mistyped IMDb id) costs a modest slice while accumulating conflicts compound
  toward the cap. `ALT_ID_FLOOR_MAX_CONFLICTS = 3`, not 2: suppliers like
  Mediafilm commonly attach two-or-three wrong third-party IDs to an otherwise
  matching record.
* **Accept requires corroboration** beyond title + year-level date
  (`ACCEPT_REQUIRES_CORROBORATION`): title+year collides across works
  ("State" vs "Narco State", same year). Corroborators and their minimum
  qualities are in `CORROBORATION_FIELDS_HIGH`.
* **`AUTOMATCH_SCORE_BYPASS = 99.0`:** across ~1,371 human decisions no
  unanchored wrong candidate ever scored 99+; the only 99+ wrongs (two, both
  100.0) carried corrupted SHARED alt-ids — a channel only external
  verification or registry hygiene can catch.
* **Epoch dates** (`DATE_EPOCH_*`): third-party systems default unknown dates
  to 1970/1970-01-01. A match on an epoch-suspect value is weak evidence; a
  mismatch against one shouldn't punish like a real year gap.
* **Episode dates are soft** (`DATE_YEAR_HALFLIFE_YEARS_EPISODE = 6`,
  `DATE_EPISODE_YEAR_MATCH_CREDIT = 0.6`): first-run syndication has no
  original broadcast date; streaming drops whole seasons on one day; dozens of
  sibling episodes share a release year.
* **Early-cinema profile** (`EARLY_CINEMA_*`, both sides ≤1915 and ≤15 min):
  actuality-era corroborators are near-constant within a studio's output
  (same year/director/country/one-minute runtime), so identity rests on a
  genuinely close title (≥0.95; observed true matches ≥0.978, wrong ≤0.855)
  and alt-IDs. Re-shot subjects two+ years apart are different films
  (Sandow 1894/1896).
* **Series format-sale guard** (`SERIES_REQUIRE_COUNTRY_MATCH`): format sales
  (Love Island, Top Gear…) produce near-identical Series differing mainly by
  country and year; the full country-of-origin lists must be EQUAL (a remake
  often lists the original territory as co-production), and country codes
  compare through the SU≡SUHH crosswalk.
* **Part numbering is distinguishing** ("Show Part 2" vs "Part 3" = different
  works, capped to Review; floored back to Review — not no-match — when
  clearly related: base-title ≥ `PART_RELATED_TITLE_MIN` + matching year).
* **Supplemental short-form guard** (`SUPPLEMENTAL_SHORT_RATIO`): a
  Supplemental much shorter than an otherwise-matching record is its
  trailer/promo, not its duplicate.
* **Cross-type matches** (`GATE_EPISODE_CROSS_BASIC_CLASSES`,
  `GATE_ANTHOLOGY_CLASSES`, `GATE_COMPILATION_SERIES_CLASSES`): allowed under
  narrow conditions and ALWAYS capped to Review — a human resolves; ineligible
  type pairs clamp to Reject (`GATE_INELIGIBLE_CEILING`). `GATE_CROSS_REVIEW_CAP`
  stays in the spec as recorded intent (S-4) and is not applied as a value.
  The cross-season and cross-type knobs this bullet used to name were removed
  at 2.12.0 (T19): nothing read them; season adjacency is a candidate-recovery
  question.
* **IMDb reconciliation** (`IMDB_*`): an isolated date/length outlier on an
  otherwise-agreeing pair with a shared non-conflicting IMDb id is checked
  against IMDb and lifted rather than penalized when IMDb confirms same-work.
* **`NAME_MATCH_MIN = 0.80`:** below it, names are DIFFERENT people and score
  0 — different directors must not earn partial credit from incidental letter
  overlap ("Rosi" vs "Faggione").
* **System-generated titles** are dropped from the title comparison only when
  BOTH sides are system-generated (a one-sided one is compared; 0.19.0+). The
  system-title discount knob this bullet used to name was removed at 2.12.0
  (T19): it was shipped but read by nothing.
