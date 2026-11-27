# merge-rules — merging a supplied record into the current registry record

**Status: LANDED 1.0.0 (2026-11-26).** Implemented by `eidr_core.merge`
(S3, `merge.SPEC_VERSION`); golden fixtures under
`src/eidr_core/specs/merge_pairs/` (section 7); values pin
`tests/merge_rules_values_pin.json` (the two knobs, the rule order, the held
list and the field-key families, hashed per version by
`merge.spec_values_digest()`). This file is the canonical home of the rule
table as ruled on 2026-09-23 (register row "MergeTool design ... RULED"),
the operator's Pro-flag rulings of 2026-09-30, section 4.2 of 2026-10-02
and the field-key ruling of 2026-11-26 (section 5.1). From 1.0.0 it is
versioned exactly like `compare-spec.md`: eidr-core assigns the version, a
rule, knob or field-key change is a version bump with a new values-pin line
and regenerated fixtures, and consumers' conformance tests are the
propagation mechanism. Change history: section 8.

Sources: eidr-wikidata's design handoff of 2026-09-23 (sections 2 to 5), its
follow-up of the same day, python-tools' review of section 5 (no conflicts),
the eidr-core ruling of 2026-09-23, eidr-wikidata's two Pro-flag
handoffs of 2026-09-30, and the operator's confirmation of section 4.2
(2026-10-02).

## 1. Purpose and placement

The .NET BMR tool's Merge mode was the only implementation of "compare a
supplied record with the current registry record under merge rules; submit
nothing if nothing changes, a Modify if something does". It is .NET and it
loses Alt IDs (section 6). This spec replaces it.

| Piece | Home | State |
|---|---|---|
| The rules | this file | 1.0.0 (2026-11-26) |
| Engine `eidr_core.merge` | eidr-core; pure (no I/O, SDK or registry), stdlib `xml.etree` only so it can be vendored (closure `merge`, `bmr_map`, `bmr_io`, `inheritance`, `ids`, `ordering`, `mddf_json`, `altidtool_io`, `normalize`, `codes`; tests/test_vendor.py) | built (S3, 2026-11-26) |
| BMR row to supplied record (B5) | eidr-core, from XML_to_JSON; acceptance criteria are python-tools' interface (register, 2026-09-23) | built: `bmr_map.record_from_row` (0.49.0), families read sparsely on `bmr_io.family_layout` |
| `MergeTool` (public CLI) | python-tools, vendoring `merge`, `bmr_io` and B5 through `vendor.toml` | not built (S4) |
| Unattended caller | eidr-wikidata, for confirmed Wikidata to EIDR pairs (`bmr_confirmed_*.xlsx`) | not built (S6) |
| Identity gate (audit / subset / resolve) | BMRtoAltID, narrowed and renamed; its output is the verified sheet MergeTool takes | S5, after S4 |

"Supplied" is the sheet row's record. "EIDR" is the current registry record
fetched for the Modify (the modification base).

### 1.1 Engine contract (from v1)

```
merge(current, supplied, MergeOptions(replace=False, altids_only=False,
                                      multi_form_domains=None), *, full=None) -> ChangeReport
```

`current` is the registry's XML for the record and must hold its
`SelfDefinedMetadata` (the modification base); it may also hold the
`FullMetadata` (a resolve message carrying both), or `full=` gives it, and
rule 15 decides presence on it (section 4.2). `supplied` is XML (a
self-defined or full block, or a creation element such as `Basic`) or a
standard record from B5 (`bmr_map.record_from_row`). A `FullMetadata`
without its `SelfDefinedMetadata` is refused: the .NET tool merged into
FullMetadata and submitted it, baking inherited values into the record.

| `ChangeReport` field | Meaning |
|---|---|
| `changed` | `False` means the caller submits nothing |
| `merged_xml` | the modification base with the edits applied, every element in schema order; `None` when `changed` is `False` |
| `changes` | `(rule, field, action, old, new, value)` per edit, in rule order; `field` is the key of section 5.1, `action` is `add`, `replace` or `remove`, `value` the normalised value |
| `conflicts` | `(rule, field, code, detail)`, e.g. `ALT_ID_RELATION_CONFLICT`; never written |
| `skipped` | `(rule, field, reason)`, e.g. "similar title present" |
| `altid_lines` | one AltIDTool line per Alt ID rule 18 added (18.6); empty when the record has no ID |
| `spec_version` | this file's version |

The report is a contract from v1 (ruled 2026-09-23): MergeTool's `-f json`
output (`ChangeReport.as_dict()`) and eidr-wikidata's two-phase contribution
ledger read it. `detail` and `reason` are prose for a human and are not part
of the contract; the codes and keys are.

`MergeOptions.multi_form_domains` is rule 18.5's exempt set: `None` reads
`altidtool_io.multi_form_domains()`, which a vendored copy cannot (package
data), so a vendoring caller passes the set; it is read only when a
Proprietary identity value needs it.

### 1.2 Switches (MergeTool; all existing suite switches)

| Switch | Effect |
|---|---|
| *(none)* | add-only rules; writes by default, like every suite tool (no `--apply`) |
| `--replace` | also runs the replace-class rules (class `replace` below). Held (section 5): the engine raises rather than run add-only silently |
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
**every** existing element, those it added in the same merge included (so a
value supplied twice is added once). Per-family caps are the `maxOccurs` of
the bundled EIDR 2.7.0 schema (`common.xsd`, and EIDR's `md-v28-eidr.xsd`
for SequenceInfo), read by the engine, never the .NET hardcoded caps; a value
refused at a cap is reported in `skipped`.

The normalisation is the .NET `CompareString.Compare`: diacritics folded
(`normalize.ascii_fold`, the portfolio's fold, standing in for the .NET
`ascii-fold.txt` table), its punctuation table (`&` reads `and`, dashes become
spaces, the rest go), whitespace collapsed, upper-cased.

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
| 21 | AddMissingEndDate | SeriesInfo/EndDate | add the supplied date when EIDR has none (a Series has no parent, so section 4.2 does not apply); fixes the dead .NET condition | add |
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
| 18.5 | Same-kind conflict (altidtool-format.md rule 6; ruled into the engine 2026-09-23): a supplied `IsSameAs` value whose Kind EIDR already holds under `IsSameAs` with a DIFFERENT value is withheld and reported as a conflict, never written, except on the Kinds `eidr_core.altidtool_io.multi_form_domains()` declares (v1.4; ruled entries v1.5, `src/eidr_core/specs/multi_form_kinds.json`). The engine calls the function; it keeps no copy of the list |
| 18.6 | Every AltIDTool-format line (the `--altids-only` report) is composed by `eidr_core.altidtool_io.format_line` |
| 18.7 | Values are validated with the AltIDTool rule set already in the portfolio (URI-safe value, named-type regex after corrections, length); the engine reports, never silently drops |

### 3.2 Pre-process (on the fetched EIDR record; ON in v1, benign de-dup)

Remove alternate titles equal to the primary; remove duplicate directors,
actors, org party IDs and metadata-authority IDs; `CleanCountryOfOrigin`;
`CleanStructuralType`. Rule ids `pre.1` to `pre.7` in that order. Equal is
normalized-exact. `pre.1` compares an alternate with the main title and the
earlier alternates only (the .NET compared it with every earlier sibling, so
an alternate "Movie" went beside ReferentType Movie). `pre.4` compares
(role, party ID) among orgs with `idType` EIDRPartyID; an org without one is
never a duplicate. `pre.6` verbatim: a lone `AQ` becomes `XX`; with more than
one country every `XX` goes. `pre.7` verbatim: a Season or Series is an
Abstraction, and so is a record whose SeasonInfo names no Parent. A
pre-process edit is a `Change` like any other and makes `changed` True (an
open question for the operator: the S3 report).

### 3.3 Readings settled when the engine was built (1.0.0)

Where the table leaves a choice open, 1.0.0 reads it so; the .NET source
(`CompareEidrRecord.cs`, read 2026-11-26) settled each where it could, and
this file governs where they differ.

| Rule | Reading |
|---|---|
| 1 | the first supplied title (main, then alternates) with a real lang and the same normalized text wins |
| 3 | a supplied main title counts as a candidate alternate; a near match (distance 1 to `FUZZY_THRESHOLD`) is reported as skipped, an exact one is silent; a system-generated supplied title is never added |
| 8 | a supplied `XX` is never added (the .NET `cond_CountryMismatch`) |
| 9, 10 | a supplied `und` is never added (`cond_OriginalLanguageMatch`); "drop `und`/`zxx` if anything else is present" is read **within one mode** (as the .NET `CleanOriginalLanguage`), so a silent Audio track beside Visual intertitles keeps both. Note the .NET kept `zxx` and dropped the rest; this table drops `zxx` |
| 11 | roles must agree (normalized-exact); then both party IDs present: they decide; otherwise both names present: fuzzy on `FUZZY_THRESHOLD_ORG` (the .NET used `FUZZY_THRESHOLD` when only the supplied org had an ID); a supplied org with neither is ignored |
| 12, 13 | the .NET nickname steps verbatim: full names, then without the first quoted span, then from the first quote on |
| 15 | the .NET round-figure replacement (EIDR 10, 15, 30, 60, 90 or 120 minutes replaced by a non-round supplied value) is not in the ruled rule and is not carried; the Movie/Short switch applies only when rule 15 changed the length; an inherited length that differs from the supplied one is reported as skipped; a record with a parent, no own length and no FullMetadata given is skipped ("unknown"), never filled |
| 16 | a supplied description without a language is skipped (one is invalid without the other) |
| 17 | tokens split at `;`, each `key:value` split at the first `:`; keys compare case-insensitively; a key present with another value is reported as skipped; the result is written `k:v; k:v;` |
| 18 | C5's relation-aware rules (2026-11-24) on the supplied side too: an exact repeat is written once; one Kind+value offered under two relations withholds every copy (`ALT_ID_RELATION_CONFLICT`); two identity values of one single-form Kind offered together are both withheld (`SAME_KIND_CONFLICT`); a value under a non-identity relation never makes a rule-6 conflict. The helpers are C5's own (`altidtool_io.AltId`, `kind_key`, `is_audited`, `is_single_form`, `same_relation`, moved there from `altid_audit` so the engine vendors), and tests/test_merge.py runs the same cases through both and compares |
| 18.7 | `altidtool_io.emission_problem` (no Type, non-ASCII), then the schema: a known type, a schema relation, length (`string1024Type`), each named type's patterns and `maxLength`, a Proprietary domain present and matching `constrainedURIType`. eidr-wikidata's further checks (URI-unsafe characters in a Proprietary value, the AMG/ISAN corrections) live in its `bmr/validator.py`, are not extracted, and are not applied (open question) |
| 20, 21 | a Series without a SeriesInfo block gets one; SeriesClass occurs once in the schema, so "add all" adds the first |
| 22 to 28 | apply only where the record has the info block (SeasonInfo, EpisodeInfo); SequenceInfo is created inside an EpisodeInfo that lacks it |

### 3.4 Post-process

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

### 4.2 Inherited counts as present (RULED by the operator, 2026-10-02)

For rule 15 (ApproximateLength) and the release-date rules 4 to 6, an
INHERITED value counts as present and is the record's value for the
comparison: "add if EIDR has none" never fires on a record whose parent
supplies the value, and a supplied date is compared against the inherited
date, so a supplied value never overrides inheritance. Seasons and Episodes
are where it bites: their own ApproximateLength or ReleaseDate element may
be absent because the value comes from the parent. Rule 21
(SeriesInfo/EndDate) is unaffected: it applies to a Series, which has no
parent to inherit from. eidr-wikidata proposed the reading and eidr-core
adopted it on 2026-09-30; the operator confirmed it on 2026-10-02,
verbatim: "Yes. Inherited counts as present." The engine
therefore needs the full record (`eidr_core.inheritance`), not only the
record's own elements, to decide presence.

## 5. Held for review

None of these runs in 1.0.0 (`merge.HELD_RULES`). The S3 report of
2026-11-26 lists what each would have done on the fixture pairs.

| Item | Held since | Decided when |
|---|---|---|
| AddTitleClass, SetStructuralType, the post-process primary-title overwrite | 2026-09-23 | after S3's fixtures show what each does on real pairs |
| Replace-class rules 2, 4, 5, 6, 7 (whether and how they ship behind `--replace`); `MergeOptions(replace=True)` raises until then | 2026-09-23 | after S3's fixtures |
| `FUZZY_THRESHOLD` 4 / `FUZZY_THRESHOLD_ORG` 6 | 2026-09-23 | reviewable knobs, carried verbatim in 1.0.0 (operator, 2026-11-26); a change is a version bump with a values-pin line |

### 5.1 The field key (RULED 2026-11-26)

The operator, 2026-11-26, adopted eidr-wikidata's proposal of 2026-09-23: a
key stable across sheet and record, Alt IDs as `alt_id:<type>|<domain>` (its
ledger's convention), a documented equivalent for every other family, and
the normalised value. Every `Change`, `Conflict` and `Skip` carries it in
`field`; `Change.value` is the value `strip().lower()` (the ledger's
`value_norm`). `<x>` parts are lowercased. The table is
`eidr_core.merge.FIELD_KEYS`:

| Key | Element | `value` |
|---|---|---|
| `title:primary` | ResourceName | its text |
| `title:alternate` | an AlternateResourceName | its text |
| `title_language:primary`, `title_language:alternate` | a title's `lang` (old/new are the codes) | the title's text |
| `title_class:primary`, `title_class:alternate` | a title's `titleClass` (held AddTitleClass) | the title's text |
| `structural_type`, `referent_type`, `status`, `mode`, `release_date` | the element (`mode` and `release_date` belong to the held rules 2 and 4 to 6) | the value |
| `country_of_origin` | one CountryOfOrigin | the code |
| `original_language`, `version_language` | one language | `code`, or `code\|mode` when a mode is set |
| `associated_org:<role>` | one AssociatedOrg | its party ID, else its name |
| `director`, `actor` | one credit | its DisplayName |
| `approximate_length` | ApproximateLength | the length |
| `description:<lang>` | Description with its lang | its text |
| `registrant_extra:<key>` | one `key:value;` pair of RegistrantExtra | the pair's value |
| `metadata_authority` | one MetadataAuthority | the party ID |
| `alt_id:<type>\|<domain>` | one AlternateID (domain empty for a named type: `alt_id:imdb\|`) | the Alt ID value |
| `series_info` | SeriesInfo flags (rule 19 reports only) | - |
| `series_class`, `end_date` | SeriesInfo children | the value |
| `season_number`, `season_class` | SeasonInfo SequenceNumber / one SeasonClass | the value |
| `episode_class`, `time_slot` | EpisodeInfo children | the value |
| `distribution_number:<domain>`, `house_sequence:<domain>`, `alternate_number:<domain>` | SequenceInfo numbers | the number |

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

Landed with the engine (S3, 2026-11-26): 90 fixtures under
`src/eidr_core/specs/merge_pairs/<set>/<id>/`, each `current.xml` (the
registry's SelfDefinedMetadata) + `supplied.xml` (or `supplied_row.json`, a
Template-22 row read by `bmr_map.record_from_row`), optionally `full.xml`
(FullMetadata), and `expected.json`: `rule`, `why`, `mutation`, `options`
and the version-independent invariants of `golden-pairs.md` section 6 --
`changed`, every `changes` entry in order, the `conflicts` codes and
`skipped` keys (never the prose), named values of the merged record,
`altid_lines` where it matters, and the schema order of every merged
element. `tools/gen_merge_pairs.py` authors them (each expectation stated by
hand, never computed by the engine); eidr-core's `tests/test_merge_pairs.py`
checks the engine against them, checks the files equal the generator's
output, and disables each fixture's rule to prove the fixture then fails.

| Set (directory) | Fixtures |
|---|---|
| `per_rule` | 51: every rule, firing and not firing where a condition exists, plus the identical pair |
| `pre_process` | 8: every pre-process step (`pre.6` twice) |
| `net_regression` | 11: every section 6 defect (the sheet-reading one three times: Alt ID gap, Country gap, blank Domain) |
| `rule_18` | 11 |
| `pro_flags` | 9 |

The plan the sets were built to:

| Set | Fixtures |
|---|---|
| Per rule | one pair per rule in section 3 (both firing and not firing where a condition exists), and one per pre-process step |
| .NET regressions | one per defect in section 6 |
| Rule 18 | 18.2 with each of blank, `''` and `NULL` relation; 18.4 relation conflict with the row's other Alt IDs still written; 18.5 withheld on an ordinary Kind and written on a declared multi-form Kind |
| Pro flags (section 4) | supplied `RD:Pro;` against each of rules 4, 5, 6 under `--replace` (no change); supplied `AL:Pro;` vs unflagged EIDR (no change); both flagged (EIDR stays); unflagged supplied vs flagged EIDR (replaced, flag removed); rule 17 with supplied `RD:Pro;` / `AL:Pro;` (not copied) beside `RT:Podcast;` (copied); an Episode whose length is inherited (rule 15 does not fire) |

## 8. Change history

| Version | Date | Change |
|---|---|---|
| 1.0.0 | 2026-11-26 | First version, with `eidr_core.merge` (S3) and 90 golden fixtures. The field key ruled (5.1, eidr-wikidata's proposal); the knobs carried verbatim; the held items not shipped (`--replace` raises); readings settled in 3.3; Status DRAFT -> landed |
