# merge-rules — merging a supplied record into the current registry record

**Status: DRAFT (design; not landed; no version; no consumer).** Nothing is
built in `eidr_core.merge`. S3 (the engine and its golden fixtures) is queued
behind B5 (the BMR-row to record mapper). This file is the canonical home of
the rule table as ruled on 2026-09-23 (register row "MergeTool design ...
RULED") plus the operator's Pro-flag rulings of 2026-09-30. It gets a version
number when S3 lands and is versioned exactly like `compare-spec.md` from
then on: a version, a values pin, a golden fixture per rule, and consumers'
conformance tests as the propagation mechanism. Until then a change here is
a design change, made by eidr-core, with no version to bump.

Sources: eidr-wikidata's design handoff of 2026-09-23 (sections 2 to 5), its
follow-up of the same day, python-tools' review of section 5 (no conflicts),
the eidr-core ruling of 2026-09-23, and eidr-wikidata's two Pro-flag
handoffs of 2026-09-30.

## 1. Purpose and placement

The .NET BMR tool's Merge mode was the only implementation of "compare a
supplied record with the current registry record under merge rules; submit
nothing if nothing changes, a Modify if something does". It is .NET and it
loses Alt IDs (section 6). This spec replaces it.

| Piece | Home | State |
|---|---|---|
| The rules | this file | DRAFT |
| Engine `eidr_core.merge` | eidr-core; pure (no I/O, SDK or registry), stdlib `xml.etree` only so it can be vendored | not built (S3, behind B5) |
| BMR row to supplied record (B5) | eidr-core, from XML_to_JSON; acceptance criteria are python-tools' interface (register, 2026-09-23) | not built (S2) |
| `MergeTool` (public CLI) | python-tools, vendoring `merge`, `bmr_io` and B5 through `vendor.toml` | not built (S4) |
| Unattended caller | eidr-wikidata, for confirmed Wikidata to EIDR pairs (`bmr_confirmed_*.xlsx`) | not built (S6) |
| Identity gate (audit / subset / resolve) | BMRtoAltID, narrowed and renamed; its output is the verified sheet MergeTool takes | S5, after S4 |

"Supplied" is the sheet row's record. "EIDR" is the current registry record
fetched for the Modify (the modification base).

### 1.1 Engine contract (from v1)

```
merge(current_xml, supplied_xml, MergeOptions(replace=False, altids_only=False)) -> ChangeReport
```

| `ChangeReport` field | Meaning |
|---|---|
| `changed` | `False` means the caller submits nothing |
| `merged_xml` | the modification base with the edits applied, elements inserted in schema order |
| `changes` | `(rule, field, action, old, new)` per edit |
| `conflicts` | `(rule, field, code, detail)`, e.g. `ALT_ID_RELATION_CONFLICT`; never written |
| `skipped` | `(rule, field, reason)`, e.g. "similar title present" |

The report is a contract from v1 (ruled 2026-09-23): MergeTool's `-f json`
output and eidr-wikidata's two-phase contribution ledger read it. The shape
of the field key inside `changes` is open (section 5).

### 1.2 Switches (MergeTool; all existing suite switches)

| Switch | Effect |
|---|---|
| *(none)* | add-only rules; writes by default, like every suite tool (no `--apply`) |
| `--replace` | also runs the replace-class rules (class `replace` below) |
| `--altids-only` | rule 18 only (BMRtoAltID's standard mode, which retires once shown equivalent on a real sheet) |
| `--dryrun PREFIX` | write what would be submitted; submit nothing |
| `-dd accept` | forced de-dupe Accept; superparty only, otherwise an error (no `--accept` alias: operator, 2026-09-23, "keep with the established conventions") |
| `--registry` / `-c` | required; no default registry |

## 2. Comparison classes

| Class | Applies to | Rule |
|---|---|---|
| exact | controlled vocabularies: Mode, codes, classes, ReferentType, types, relations | equal after case-fold |
| normalized-exact | countries, language codes, org IDs, roles | strip diacritics and punctuation, normalize whitespace, upper-case, then equal |
| per rule 18 | Alt IDs | NOT normalized-exact (the .NET class, deliberately not carried): the Kind `(Type, Domain)` is compared exactly, the domain as the registry stores it, and the value under BMRtoAltID's rules -- see 18.1 |
| fuzzy | every other text field: titles, director/actor display names (nickname-in-quotes tolerant), org names | normalize as above, then Levenshtein distance; "different" means distance > `FUZZY_THRESHOLD` |

| Constant | Value | Status |
|---|---|---|
| `FUZZY_THRESHOLD` | 4 | the .NET constant, carried verbatim; a reviewable knob, NOT a ruling |
| `FUZZY_THRESHOLD_ORG` | 6 (org names, "Company"/"Co") | the .NET constant, carried verbatim; a reviewable knob, NOT a ruling |

An add rule adds a supplied element only when its condition holds against
**every** existing element. Per-family caps are `SCHEMA_MAX` from
`common.xsd` (as `bmr_io.write_sheet` uses), never the .NET hardcoded caps.

## 3. The rules

Baseline is the .NET order and semantics ("verbatim first") with the
operator's 2026-09-23 revisions applied. Rules run in this order. The
unattended path is add-only; class `replace` runs only under `--replace`.
Rule 15's flagged replace is NOT replace-class: it replaces a value the
record itself flags as a placeholder, and runs unconditionally. Section 4
modifies rules 4, 5, 6, 15 and 17; read it with the table.

| # | Rule | Field(s) | Behaviour | Class |
|---|---|---|---|---|
| 1 | ReplaceTitleLanguage | title `@lang` | EIDR title lang `und` and a supplied title with a real lang that is normalized-exact the same text: copy the lang | add |
| - | AddTitleClass | title `@titleClass` | off; held (section 5) | - |
| 2 | ReplaceMode | Mode | overwrite from supplied; then, if the final Mode is `Visual`, set every OriginalLanguage/VersionLanguage `@mode` to `Visual` and discard resulting duplicates | replace |
| 3 | AddMissingTitle | AlternateResourceName | add each supplied title fuzzy-different from every EIDR title (primary and alternates) | add |
| 4 | ReplaceReleaseYear1 | ReleaseDate (year) | supplied year < EIDR year - 1: overwrite. Not when supplied carries `RD:Pro;` (section 4) | replace |
| 5 | ReplaceReleaseYear2 | ReleaseDate | supplied full date whose year <= EIDR's year-only value: overwrite with the full date. Not when supplied carries `RD:Pro;` | replace |
| 6 | ReplaceReleaseDate | ReleaseDate | both full, supplied earlier: overwrite. Not when supplied carries `RD:Pro;` | replace |
| 7 | ReplaceCountryOfOrigin | CountryOfOrigin[1] | EIDR `XX`, supplied neither `XX` nor `AQ`: overwrite | replace |
| 8 | AddMissingCountryOfOrigin | CountryOfOrigin | add supplied codes not present (normalized-exact); then, if the list holds `XX` plus anything else, drop `XX` | add |
| 9 | AddMissingOriginalLanguage | OriginalLanguage (+`@mode`) | add (code, mode) pairs not present; then drop `und` if anything else is present, and drop `zxx` if anything else is present. 8 runs before 9, so `XX` + `zxx` keeps `zxx` | add |
| 10 | AddMissingVersionLanguage | VersionLanguage | as rule 9 | add |
| 11 | AddMissingAssociatedOrg | AssociatedOrg | add when no (orgID normalized-exact, or name fuzzy) + role match is present | add |
| 12 | AddMissingDirector | Credits/Director | add when the DisplayName is fuzzy-absent (nickname tolerant) | add |
| 13 | AddMissingActor | Credits/Actor | as rule 12 | add |
| - | SetStructuralType | StructuralType | off; held (section 5) | - |
| 14 | SetPublicationStatus | Status | skipped: the registry will not allow it | - |
| 15 | ReplaceApproxLength | ApproximateLength, RegistrantExtra, ReferentType | add if EIDR has none (an inherited value counts as present: section 4.2); if EIDR is flagged `AL:Pro;` and supplied is not, replace with supplied; if the EIDR value changed, remove `AL:Pro;` from RegistrantExtra. Never brings in a supplied length flagged `AL:Pro;` (section 4). ReferentType is preserved, except `Movie` with resulting length < 45 min becomes `Short`, and `Short` with resulting length >= 45 min becomes `Movie` | add (+ flagged replace) |
| 16 | AddMissingDescription | Description + DescriptionLanguage | supplied has a description and EIDR has none: add the description AND its language (one is invalid without the other) | add |
| 17 | AddMissingRegistrantExtra | RegistrantExtra | parse both sides at `;` into semicolon-terminated `key:value` pairs; add supplied pairs whose key is absent in EIDR; honour removals other rules make (`AL:Pro;` by rule 15, `RD:Pro;` when a replace-class date rule replaces a provisional date). Never copies a supplied `RD:Pro;` or `AL:Pro;` (section 4) | add |
| 18a | AddMissingMetadataAuthority | Administrators/MetadataAuthority | restored (was commented out): add party IDs not present, schema cap | add |
| 18 | AddMissingAlternateID | AlternateID | BMRtoAltID's rules, section 3.1 (an intentional departure from verbatim) | add |
| 19 | AddMissingSeriesInfo | SeriesInfo flags | skipped: SeriesInfo must already exist on a Series | - |
| 20 | AddMissingSeriesClass | SeriesInfo/SeriesClass | add all when EIDR has none | add |
| 21 | AddMissingEndDate | SeriesInfo/EndDate | add the supplied date when EIDR has none (an inherited value counts as present: section 4.2); fixes the dead .NET condition | add |
| 22 | AddMissingSeasonNumber | SeasonInfo/SequenceNumber | add when EIDR has none | add |
| 23 | AddMissingSeasonClasses | SeasonInfo/SeasonClass | add every supplied class not present (exact) | add |
| 24 | AddMissingEpisodeClasses | EpisodeInfo/EpisodeClass | add every supplied class not present (exact; no fuzzy) | add |
| 25 | AddMissingDistributionNumber | SequenceInfo/DistributionNumber | add when EIDR has none | add |
| 26 | AddMissingHouseNumber | SequenceInfo/HouseSequence (+domain) | add when EIDR has none | add |
| 27 | AddMissingAlternateNumbers | SequenceInfo/md:AlternateNumber | add when the (number, domain) pair, case-insensitive, is not present | add |
| 28 | AddMissingTimeSlot | EpisodeInfo/TimeSlot | add when EIDR has none | add |

### 3.1 Rule 18 — Alt IDs (BMRtoAltID's rules)

The identity model is `specs/altidtool-format.md`, "Identity, relation and
what already on the record means" (v1.2, 2026-09-23; rule 6 at v1.4). It is
cited, not restated; where this list and that file disagree, that file wins.

| # | Rule |
|---|---|
| 18.1 | Identity is Kind + value. Kind = `(Type, Domain)` compared exactly, the domain as the registry stores it; a null Domain matches only a null Domain. Never by resolved URL; never a `uri_mapping.json` collision check (register R8, closed) |
| 18.2 | "Already present" is Kind + value + relation. A blank relation, the mirror's `''` and `NULL` all read as `IsSameAs` (ruled into this spec 2026-09-23; a consumer must be right under either stored value) |
| 18.3 | Same Kind + value, same relation: skipped silently (no change) |
| 18.4 | Same Kind + value, different relation: `ALT_ID_RELATION_CONFLICT` in `conflicts`, not written, per Alt ID; the row's other Alt IDs still go. Never re-add a present value under a second relation; never hide one |
| 18.5 | Same-kind conflict (altidtool-format.md rule 6; ruled into the engine 2026-09-23): a supplied `IsSameAs` value whose Kind EIDR already holds under `IsSameAs` with a DIFFERENT value is withheld and reported as a conflict, never written, except on the Kinds `eidr_core.altidtool_io.multi_form_domains()` declares (v1.4, `src/eidr_core/specs/multi_form_kinds.json`). The engine calls the function; it keeps no copy of the list |
| 18.6 | Every AltIDTool-format line (the `--altids-only` report) is composed by `eidr_core.altidtool_io.format_line` |
| 18.7 | Values are validated with the AltIDTool rule set already in the portfolio (URI-safe value, named-type regex after corrections, length); the engine reports, never silently drops |

### 3.2 Pre-process (on the fetched EIDR record; ON in v1, benign de-dup)

Remove alternate titles equal to the primary; remove duplicate directors,
actors, org party IDs and metadata-authority IDs; `CleanCountryOfOrigin`;
`CleanStructuralType`.

### 3.3 Post-process

| .NET step | v1 |
|---|---|
| `CorrectMismatchedTitleLanguageCountryOfOrigin` (overwrites the primary title's TEXT with an alternate's when the primary's lang does not match the first country; the lang attribute is not swapped) | OFF; held (section 5) |
| `CorrectTransliteratedTitle`, `RemoveSeasonEpisodeRecord` | stubs in .NET; not ported |

## 4. Data-quality flags on the supplied side (operator, 2026-09-30)

`RD:Pro;` and `AL:Pro;` in RegistrantExtra mark an uncertain or estimated
Release Date or Approximate Length. The rule table as ruled on 2026-09-23
read them on the EIDR side only. On the SUPPLIED side they are instructions
to the merge.

The operator, 2026-09-30, verbatim (relayed by eidr-wikidata):

> Continue using RD:Pro; and AL:Pro; to mark the use of uncertain or
> estimated data from an external source. This will be used if a new
> record is created from the resulting BMR sheet. If we use data merge to
> augment existing records, the tags indicate that those values should not
> be brought into the EIDR record and that the existing values should be
> retained.

> Release Date and Approximate Length are required fields, so they will
> always be present in every record (inherited or self-defined).
> Provisional (Pro) values are only recorded when a better value is not
> available for a required field, so the situation of a Pro-flagged value
> populating an Empty field in an EIDR registry record will never come up.

### 4.1 Effect on the rules

| Rule | Supplied row carries | Effect |
|---|---|---|
| 4, 5, 6 | `RD:Pro;` | do not fire; the existing date is retained (also under `--replace`) |
| 15 | `AL:Pro;` | never brings in the supplied length; the existing length is retained |
| 15 | `AL:Pro;`, EIDR also flagged `AL:Pro;` | EIDR's value stays (and so does its flag) |
| 15 | no flag, EIDR flagged `AL:Pro;` | unchanged: replace and drop EIDR's flag (the flagged-EIDR replace needs an unflagged supplied value anyway) |
| 17 | `RD:Pro;` or `AL:Pro;` | never copied onto the record: the flag describes the supplied value, which rules 4 to 6 and 15 declined, so copying it would mark the record's own retained value as an estimate |
| 17 | `RT:Podcast;`, `RT:MusicVideo;` | unaffected; still eligible |
| all | a `Pro`-flagged supplied value against an empty EIDR field | no gap-fill branch exists: Release Date and Approximate Length are required and always present (inherited or self-defined) |

### 4.2 Inherited counts as present (eidr-core's reading, adopted pending the operator's confirmation)

For rule 15 (ApproximateLength) and the release-date rules 4 to 6, an
INHERITED value counts as present and is the record's value for the
comparison: "add if EIDR has none" never fires on a record whose parent
supplies the value, and a supplied date is compared against the inherited
date, so a supplied value never overrides inheritance. Seasons and Episodes
are where it bites: their own ApproximateLength or ReleaseDate element may
be absent because the value comes from the parent. Rule 21
(SeriesInfo/EndDate) is unaffected: it applies to a Series, which has no
parent to inherit from. eidr-wikidata proposed the reading; the
operator's "inherited or self-defined" supports it; eidr-core adopted it
2026-09-30 and it stands until the operator says otherwise. The engine
therefore needs the full record (`eidr_core.inheritance`), not only the
record's own elements, to decide presence.

## 5. Held for review

| Item | Held since | Decided when |
|---|---|---|
| AddTitleClass, SetStructuralType, the post-process primary-title overwrite | 2026-09-23 | after S3's fixtures show what each does on real pairs |
| Replace-class rules 2, 4, 5, 6, 7 (whether and how they ship behind `--replace`) | 2026-09-23 | after S3's fixtures |
| `FUZZY_THRESHOLD` 4 / `FUZZY_THRESHOLD_ORG` 6 | 2026-09-23 | reviewable knobs; any change is a versioned change once this spec has a version |
| The field key in `ChangeReport.changes`: eidr-wikidata asked for a key stable across sheet and record (`alt_id:<type>\|<domain>` for Alt IDs, the ledger's convention, and a documented equivalent per family) plus the normalized value | 2026-09-23 | with S3, before the report shape is versioned |
| Section 4.2's reading | 2026-09-30 | the operator's confirmation |

## 6. .NET defects the engine must not carry

Each is a regression fixture (section 7).

| .NET location | Defect | Engine |
|---|---|---|
| `SpreadsheetData.cs` sheet to XML | the Alt ID loop stops at the first blank `Alt ID N`, losing every Alt ID to its right; a blank `Domain N` beside a value throws and fails the row; Country of Origin has the same stop-at-first-blank loop | B5 must read families sparsely, as `bmr_io.family_layout` does; a gap never ends a family |
| same | named Alt ID types are a hardcoded list of 25; anything else becomes `Proprietary` with the type as the domain | Alt ID types from the schema, never a hardcoded list |
| `CompareEidrRecord.cs` | hardcoded caps (2 directors, 4 actors, 16 orgs, 32 countries, 32/64 languages, 1 episode class, 1 alternate number, 128 titles) | `SCHEMA_MAX` from `common.xsd` |
| `AddMissingEndDate` | condition null-derefs (`ssi == null && ssi.Element(...)`); never fires | rule 21 as ruled |
| `AddMissingSeasonClasses` | condition copies the season-NUMBER condition; dead | rule 23 as ruled |
| `AddMissingSeriesInfo` | writes malformed XML (`<NumberRequired>false</NumberRequired`) | rule 19 skipped |
| `ReplaceApproxLength` | silently overwrites ReferentType from the sheet | rule 15 preserves it (Movie/Short switch only) |
| `SetPublicationStatus` | ignores the supplied value and forces `valid` | rule 14 skipped |
| throughout | element insertion is `// TODO: ensure location correct` | insertion in schema order |

## 7. Golden fixtures

Land with the engine (S3), not before; none exist yet. Fixture shape:
`current.xml` + `supplied.xml` -> expected `ChangeReport`, with
version-independent invariants as in `golden-pairs.md` section 6.

| Set | Fixtures |
|---|---|
| Per rule | one pair per rule in section 3 (both firing and not firing where a condition exists), and one per pre-process step |
| .NET regressions | one per defect in section 6 |
| Rule 18 | 18.2 with each of blank, `''` and `NULL` relation; 18.4 relation conflict with the row's other Alt IDs still written; 18.5 withheld on an ordinary Kind and written on a declared multi-form Kind |
| Pro flags (section 4) | supplied `RD:Pro;` against each of rules 4, 5, 6 under `--replace` (no change); supplied `AL:Pro;` vs unflagged EIDR (no change); both flagged (EIDR stays); unflagged supplied vs flagged EIDR (replaced, flag removed); rule 17 with supplied `RD:Pro;` / `AL:Pro;` (not copied) beside `RT:Podcast;` (copied); an Episode whose length is inherited (rule 15 does not fire) |
