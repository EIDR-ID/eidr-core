# compare-spec — the unified engine's tuning surface (companion doc)

**The runtime file is `src/eidr_core/specs/compare-spec.json`** (inside the
package so `eidr_core.compare.spec.load_spec` finds it via importlib.resources
in any install mode; override with the `EIDR_COMPARE_SPEC` env var for
experiments). Current version: **2.0.0** — a 1:1 externalization of BMR-Review's
`config.py` as of 2026-07-28 (that file's annotated original is preserved in
BMR-Review git history, commit `17574c4` and earlier).

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
  the denominator (`ALWAYS_APPLICABLE` keeps release_date in regardless);
  calibrated per creation type onto the shared bands (<30 Reject, 30–<80
  Review, ≥80 Accept).
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
* **Cross-season / cross-type matches** (`CROSS_SEASON_*`, `CROSS_TYPE_*`,
  `GATE_*`): allowed under narrow conditions and ALWAYS capped to Review
  (`GATE_CROSS_REVIEW_CAP`) — a human resolves; ineligible type pairs clamp
  to Reject (`GATE_INELIGIBLE_CEILING`).
* **IMDb reconciliation** (`IMDB_*`): an isolated date/length outlier on an
  otherwise-agreeing pair with a shared non-conflicting IMDb id is checked
  against IMDb and lifted rather than penalized when IMDb confirms same-work.
* **`NAME_MATCH_MIN = 0.80`:** below it, names are DIFFERENT people and score
  0 — different directors must not earn partial credit from incidental letter
  overlap ("Rosi" vs "Faggione").
* **System-generated titles** contribute at `SYSTEM_TITLE_DISCOUNT` and are
  ignored when real titles exist on both sides (they restate structure already
  compared via parent/sequence fields).
