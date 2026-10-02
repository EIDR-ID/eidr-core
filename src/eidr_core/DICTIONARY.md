# eidr-core dictionary

Documents eidr-core <!-- dict-version -->0.46.0<!-- /dict-version -->. The canonical
copy is `DICTIONARY.md` at the root of
[EIDR-ID/eidr-core](https://github.com/EIDR-ID/eidr-core) (public); on the
portfolio machine, `D:\Software\eidr-core\DICTIONARY.md`. A file named
`EIDR-CORE-DICTIONARY.md` in your project is a published copy that eidr-core
refreshes. Never edit it.

## Read this first

**What this is.** Every public function, class and constant in eidr-core. For
each: the exact signature; each parameter's type, default and purpose; what it
returns; and what it does. Each module also says when to use it and when not
to. The closing sections cover the language-neutral specs and data files, and
the conventions every consumer follows.

**The rule for every project (operator, 2026-10-02).** Read this dictionary
before you ask eidr-core a question, or propose a change or an addition to it.

* If it answers your question, you have your answer.
* If eidr-core already does what you need, call it. Do not write your own
  copy. A second implementation of shared logic is treated as a bug until
  proven otherwise (eidr-core `CLAUDE.md`, "The organizing rule").
* If a function almost fits, propose widening it. A new parameter whose
  default keeps today's behaviour is cheap. A parallel function is not.
* A proposal names the entries it touches and says why they do not serve.

**Where to start.** "Find it fast" maps common needs to the right name. The
Index lists every public name in one line each. Then read the module section.

**How to read an entry.**

* The code block is the exact signature, copied from the source.
* The table lists each parameter. The Default column says "required" when there
  is none, and "keyword-only" when the argument must be passed by name.
* **Returns** gives the annotated return type and what it means.
* **Does.** says what the symbol does, its side effects, and the errors it
  raises. **Notes.**, when present, lists pitfalls.
* For a class, the table lists its fields or its methods.

**How it stays true.** `tools/gen_dictionary.py` writes the signatures, types
and defaults from the source, and a person writes the prose. eidr-core's test
suite fails in any of these cases:

* a public name has no entry;
* an entry names something that no longer exists;
* a generated part is stale, or a purpose is missing;
* a release has no heading under Changes.

So no eidr-core release ships without its dictionary update.

**How it reaches you.** eidr-core publishes a fresh copy to every project,
as `EIDR-CORE-DICTIONARY.md` at its root, whenever eidr-core changes in a way
a consumer could notice. That means a release, a new or changed public name,
or a spec change. **Changes**, below, says what moved, newest first. When your
copy changes, read the new Changes entries first.

**Installing.** eidr-core is not on PyPI. Install it from the repository,
with the extras you need, and pin `@main`:

    pip install "eidr-core[bmr,registry] @ git+https://github.com/EIDR-ID/eidr-core.git@main"

| Extra | Pulls | Needed for |
|---|---|---|
| (none) | nothing: the base install is stdlib-only | every module not listed below |
| `compare` | rapidfuzz | `eidr_core.compare` (imported at module load) |
| `bmr` | openpyxl | `eidr_core.bmr_io` functions that open or write a workbook |
| `aws` | boto3 | the AWS path of `eidr_core.secrets_loader` |
| `registry` | `eidr[client]`, the EIDR Python SDK from PyPI | `eidr_core.registry.get_registry_client` |

`eidr_core.__version__` is the installed version. Under an editable install,
it reads the checkout's `pyproject.toml`, so it is never stale.

## Changes

Newest first. Each entry says what a consumer could notice.

### 0.46.0 (2026-10-02)

* **New module `eidr_core.dictionary`.** Run `python -m eidr_core.dictionary
  <name>`, or call `lookup(name)`, `changes(since)` or `text()`. It answers
  from the copy of this dictionary that ships inside the installed package,
  so the answer always matches the code you run. The copy in your
  project's root is a convenience for sessions that cannot run Python.
* **Every public module now declares `__all__`.** The lists contain exactly
  the names this dictionary documents, plus `normalize.canon_country`.
  * Importing by name is unchanged.
  * `from eidr_core.X import *` no longer brings in the modules' own
    imports (`re`, `fuzz`, `dataclass` and so on). From `eidr_core.compare`
    it no longer brings `config`, the private parameter module, either.
  * BMR-Review's shims were checked: every name its code takes through them
    is in the new lists.
* The **Used by.** line of each module is now generated from a scan of the
  consumer trees at each release. Vendored copies are listed with their pin.

### 0.45.1 (2026-10-02)

* `altidtool_io` can be vendored again. `multi_form_domains()` no longer
  names its own package in a string, which had made `eidr_core.vendor`
  refuse the module since 0.39.0. Where eidr-core is installed, nothing
  changes. In a vendored copy, `multi_form_domains()` raises `RuntimeError`,
  because no package data is carried; the line functions work as before.
  `tests/test_vendor.py` now runs the real module through `sync`.

### 0.45.0 (2026-10-02)

Two silent-failure fixes that the dictionary audit found. Both were
approved by the operator.

* `normalize.alias_name` / `normalize.norm_name`: the name alias map (CT + T)
  is resolved as one map, so a chain that crosses the two domains is
  followed. Exactly one entry moves: `jacque` now gives `jacob`, as
  `jacques` already did. `Jacque Brel` and `Jacques Brel` now normalise
  alike. Title normalisation is unchanged.
* `secrets_loader.load_local`: the trailing-comma repair no longer touches
  string values. Before, a password containing `,}` or `,]` was silently
  altered. A file with a UTF-8 byte-order mark now loads.
  `secrets_loader.load_aws` raises `SecretsError` for a payload that is not
  JSON.

### 0.44.0 (2026-10-02)

* **compare-spec 2.18.0: Internal titles count, discounted.** The packaged
  spec now defines `INTERNAL_TITLE_DISCOUNT` (0.8) and
  `INTERNAL_TITLE_ACCEPT_REQUIRES_ALT_ID` (true). A consumer that registers
  `load_spec()` with `compare.set_params` now gets Internal-class titles
  (machine translations) in `compare.cmp_titles`, at the discount. Scores
  move wherever a candidate carries an Internal title.
* `compare.cmp_titles` with the discount registered: an Internal pair earns
  first-match credit only, never the accumulation bonus. Without the knob,
  nothing changes.
* The Accept cap for an Internal-carried title is BMR-Review's scorer rule.
  eidr-core carries only its constant in the spec.
* The golden corpus has 38 fixtures (24 `pair`, 13 `case`, 1
  `recovery_pool`). `case` fixtures' `notes_match` and `notes_not_match` now
  read the assessment's notes AND its reason, and `expected` records
  `reason`. See `specs/golden-pairs.md`.

### 0.43.0 (2026-10-02)

* **First edition of this dictionary.** It covers all public names in
  0.43.0, the specs, and the conventions.
* `eidr_core.altidtool_io.multi_form_domains()` now also returns
  `mediafilm.ca`, the first entry listed by operator ruling (altidtool-format
  v1.5, operator: "We can't tell, so accept both for now"). A numeric value
  beside an `mf-tt-N` value of that Kind is no longer a rule-6 conflict.
  Callers change nothing.
* `specs/merge-rules.md` (a DRAFT; nothing is built): section 4.2, "an
  inherited value counts as present", is now the operator's ruling.

### Before 0.43.0

The full release history is in the comments at the top of `pyproject.toml`.
These recent changes may still be reaching consumers:

* **0.42.1:** an `<OperationStatus>` block that says pending (Code 2) is no
  verdict. `parse_operation_status` returns `None` for it, and
  `parse_operation_statuses` leaves it out.
* **0.42.0:** `call_with_failover` honours Retry-After on 429 and 503. Memory
  across calls is a caller-owned `cooldowns` dict, never hidden module state.
* **0.40.0:** `cmp_titles` includes Internal-class titles at a discount when
  the registered params carry `INTERNAL_TITLE_DISCOUNT`. It is inert until a
  compare-spec version defines the knob.

## Find it fast

| I need to... | Use | Read first |
|---|---|---|
| Check that a value is a well-formed EIDR Content ID, or say why it is not | `ids.is_valid_eidr_id`, `ids.fault` | syntax and checksum only, never registration |
| Find Content IDs in free text | `ids.find_content_ids` | |
| Tell a content, party, user or service DOI apart | `ids.category`, `ids.is_valid_party_id` and its siblings | |
| Make any live registry call, read or write | `registry.get_registry_client` | never construct `eidr.Client` yourself |
| Learn whether a registry write succeeded | `registry.token_operation_status`, `registry.parse_operation_status(es)` | `None` means no verdict yet, not failure |
| Load a program's secrets (`.secrets.json` or AWS) | `secrets_loader.load_secrets` (`load_local`, `load_aws`) | |
| Call an external HTTP or SPARQL service with retries, Retry-After and failover | `external.call_with_failover`, `external.endpoint_chain`, `external.classify_sparql_error` | pass your own `cooldowns` and `outage_endpoints` across calls |
| Cache facts fetched from an external source | `external.FactCache` and its implementations | |
| Check a registered runtime or release date against an external fact | `verify.compare_runtime`, `verify.compare_release_date`, `verify.compare_year_arbitration` | |
| Normalize a title or a name for comparison | `normalize.norm_title`, `normalize.norm_name`, `normalize.cmp_key` | |
| Parse a date or a duration from registry text | `normalize.parse_date`, `normalize.parse_minutes`, `normalize.days_between` | |
| Read the `RD:Pro;` / `AL:Pro;` estimate flags | `normalize.parse_registrant_extra` | |
| Make text safe for TSV, CSV or PostgreSQL COPY | `normalize.sanitize_field` | |
| Normalize a country code (SU to SUHH) | `codes.normalize_country_code`; `normalize.norm_country` when comparing | |
| Compare two records field by field | `compare.COMPARATORS` and the `compare.cmp_*` functions, after `compare.set_params` | the full scorer and verdict layer live in BMR-Review |
| Load the compare-spec tuning values | `compare.spec.load_spec` | |
| Turn engine qualities into De-Dupe UI field states | `compare.states.field_states`, `compare.states.band` | |
| Parse a part number, or choose which titles to compare | `compare.titles.parse_part`, `compare.titles.select_titles`, `compare.titles.title_similarity` | |
| Build a child's full record (inheritance, system-generated titles) | `inheritance.build_full_record`, `inheritance.build_full_base`, `inheritance.is_absent` | |
| Sort titles or Alt IDs in canonical or display order | `ordering.title_sort_key`, `ordering.altid_canonical_key`, `ordering.altid_display_key` | |
| Read a BMR workbook, streamed or in memory | `bmr_io.open_sheet`, `bmr_io.read_sheet` | |
| Write a BMR workbook from records | `bmr_io.write_sheet`, `bmr_io.RepeatPlan` | |
| Copy chosen rows of a BMR sheet, or fill one column | `bmr_io.subset_rows`, `bmr_io.fill_column`; `bmr_io.check_sheet` first | |
| Resolve a BMR row's parent | `bmr_io.index_rows`, then `bmr_io.resolve_parent` or `bmr_io.parent_chain` | |
| Route a creation type to its Template-22 template | `bmr_io.template_for_creation_type` | |
| Write or read an AltIDTool line | `altidtool_io.format_line`, `altidtool_io.write_lines`, `altidtool_io.parse_line`, `altidtool_io.parse_edit_line` | `specs/altidtool-format.md` |
| Know which Alt ID Kinds are exempt from rule 6 | `altidtool_io.multi_form_domains` | never keep your own copy of the list |
| Check that a database has the tables and columns you read | `db_schemas.assert_tables` | |
| Carry eidr-core code into a package that cannot depend on it | `python -m eidr_core.vendor` (`sync`, `check`) | `specs/vendoring.md` |

Names are relative to `eidr_core`. The **Used by.** line in each module
section comes from a scan of the consumer trees on the date of the
edition's Changes entry.

## Index

<!-- dict-index -->
| Name | Kind | Does |
|---|---|---|
| [`eidr_core.altidtool_io.format_line`](#format_line) | function | Composes one AltIDTool input line from its fields under the canonical variable-width rules. |
| [`eidr_core.altidtool_io.multi_form_domains`](#multi_form_domains) | function | Returns the Proprietary domains exempt from altidtool-format rule 6, read from the packaged `multi_form_kinds.json`. |
| [`eidr_core.altidtool_io.parse_edit_line`](#parse_edit_line) | function | Parses one AltIDTool edit-file line into an addition, a removal, or None for a blank or comment line. |
| [`eidr_core.altidtool_io.parse_line`](#parse_line) | function | Parses one 3-, 4- or 5-column AltIDTool addition line back into an AltIdRow. |
| [`eidr_core.altidtool_io.write_lines`](#write_lines) | function | Writes rows to `path` as an AltIDTool input file (UTF-8, LF line endings, no header) and returns the count. |
| [`eidr_core.altidtool_io.AltIdRemoval`](#altidremoval-class) | class | Represents one AltIDTool removal line, as returned by `parse_edit_line`. |
| [`eidr_core.altidtool_io.AltIdRow`](#altidrow-class) | class | Holds one AltIDTool addition line as a NamedTuple in column order. |
| [`eidr_core.bmr_io.check_sheet`](#check_sheet) | function | Checks, without writing, whether `subset_rows` or `fill_column` would accept a sheet, and reports its columns. |
| [`eidr_core.bmr_io.count_family`](#count_family) | function | Returns how many numbered groups of a column family a header map carries, as the highest group number. |
| [`eidr_core.bmr_io.expand_family`](#expand_family) | function | Inserts columns so a family reaches `want` groups, writing the new header names on row 3. |
| [`eidr_core.bmr_io.families_for`](#families_for) | function | Returns one template's column families, optionally narrowing which columns new groups add. |
| [`eidr_core.bmr_io.family_layout`](#family_layout) | function | Maps a repeating family's headers to `{group number: {member: header}}`, keeping the sheet's own group numbers. |
| [`eidr_core.bmr_io.fill_column`](#fill_column) | function | Copies a BMR workbook and writes values into one column of one sheet, keyed by absolute sheet row number. |
| [`eidr_core.bmr_io.fix_shared_strings`](#fix_shared_strings) | function | Converts inline-string cells in every worksheet of an `.xlsx` to shared-string references, rewriting the file in place. |
| [`eidr_core.bmr_io.header_map`](#header_map) | function | Applies the shared header-row policy to a plain row of values, returning `{1-based column: trimmed header}`. |
| [`eidr_core.bmr_io.index_rows`](#index_rows) | function | Indexes sheet rows by Row ID so `resolve_parent` and `parent_chain` can look parents up. |
| [`eidr_core.bmr_io.max_counts`](#max_counts) | function | Returns the highest group number each family needs across mapped rows, keyed by family primary. |
| [`eidr_core.bmr_io.open_sheet`](#open_sheet) | function | Opens one BMR sheet for streaming reads, yielding the header map and a lazy iterator of numbered row dicts. |
| [`eidr_core.bmr_io.pad_groups`](#pad_groups) | function | Flattens one family's values to exactly `count` groups of `width` cells, padding missing groups with `fill`. |
| [`eidr_core.bmr_io.parent_chain`](#parent_chain) | function | Walks a row's parent references within the sheet, nearest parent first, returning one `ParentRef` per step. |
| [`eidr_core.bmr_io.read_headers`](#read_headers) | function | Returns the header map `{1-based column: header}` of an open worksheet, using the shared `header_map` policy. |
| [`eidr_core.bmr_io.read_sheet`](#read_sheet) | function | Reads one BMR sheet fully into memory as a header map plus one `{header: value}` dict per data row. |
| [`eidr_core.bmr_io.resolve_parent`](#resolve_parent) | function | Resolves one child row's `Parent EIDR/Row ID` cell, which holds an EIDR ID or a Row ID, into a `ParentRef`. |
| [`eidr_core.bmr_io.rightmost_in`](#rightmost_in) | function | Returns the rightmost column whose header is a family member name, bare or followed by a space. |
| [`eidr_core.bmr_io.subset_rows`](#subset_rows) | function | Copies a BMR workbook, keeping the header rows and only the chosen data rows of one sheet, in source order. |
| [`eidr_core.bmr_io.template_for_creation_type`](#template_for_creation_type) | function | Returns the Template-22 template key a creation type routes to, from the one shared routing table. |
| [`eidr_core.bmr_io.transplant`](#transplant) | function | Replaces the worksheet XML and shared strings in one `.xlsx` with another file's, keeping all its other parts. |
| [`eidr_core.bmr_io.write_sheet`](#write_sheet) | function | Writes mapped rows onto a copy of one Template-22 sheet, expanding column families, and reports what it could not place. |
| [`eidr_core.bmr_io.Family`](#family-class) | class | Describes one repeating column family on a Template-22 sheet: its primary, group-1 and new-group columns. |
| [`eidr_core.bmr_io.FillReport`](#fillreport-class) | class | Reports what `fill_column` wrote and what it found about the sheet's columns. |
| [`eidr_core.bmr_io.ParentRef`](#parentref-class) | class | Holds the outcome of resolving one `Parent EIDR/Row ID` cell; `bool(ref)` is True only when an EIDR ID was found. |
| [`eidr_core.bmr_io.RepeatPlan`](#repeatplan-class) | class | Accumulates union-max repeat-group counts across a set of records, with optional per-family minimums. |
| [`eidr_core.bmr_io.SheetCheck`](#sheetcheck-class) | class | Reports what `check_sheet` learned about a sheet's columns, without anything being written. |
| [`eidr_core.bmr_io.SubsetReport`](#subsetreport-class) | class | Reports what `subset_rows` wrote and what it found about the sheet's columns. |
| [`eidr_core.bmr_io.Template`](#template-class) | class | Describes one Template-22 content workbook: key, file name, data tab, column families and shipped header row. |
| [`eidr_core.bmr_io.TemplateMismatch`](#templatemismatch-class) | class | Signals that a sheet is not, or is no longer, a conforming Template-22 data sheet. |
| [`eidr_core.bmr_io.WriteReport`](#writereport-class) | class | Reports what `write_sheet` did, including what it could not place. |
| [`eidr_core.bmr_io.ASSIGNED_ID_COLUMN`](#assigned_id_column-constant) | constant | Header of the column holding a row's registered EIDR ID. |
| [`eidr_core.bmr_io.CREATION_TYPES`](#creation_types-constant) | constant | The schema's ten creation types without the `Create` prefix: Basic, Series, Season, Episode, Edit, Clip, Manifestation, Compilation, Interactive, Composite. |
| [`eidr_core.bmr_io.DATA_START`](#data_start-constant) | constant | 1-based first data row of every Template-22 sheet (rows 1-2 are the banner, row 3 the headers). |
| [`eidr_core.bmr_io.HEADER_ROW`](#header_row-constant) | constant | 1-based row carrying the column headers on every Template-22 sheet. |
| [`eidr_core.bmr_io.PARENT_COLUMN`](#parent_column-constant) | constant | Header of the parent reference column, which holds EITHER the parent's EIDR ID or the parent row's `Unique Row ID`. |
| [`eidr_core.bmr_io.ROW_ID_COLUMN`](#row_id_column-constant) | constant | Header of each row's own ID, the key `index_rows` indexes on and the column parent references name. |
| [`eidr_core.bmr_io.SCHEMA_MAX`](#schema_max-constant) | constant | Registry maximum group count per family, from the schema's `maxOccurs` (`common.xsd`; Alternate No. |
| [`eidr_core.bmr_io.SHEET_TO_TEMPLATE`](#sheet_to_template-constant) | constant | Data tab name to `TEMPLATES` key: `"Episodics"` to `episodic`, `"Stand-Alone Works"` to `non_episodic`, `"Edits"` to `edit`, `"Clips"` to `clip`, `"Manifestations"` to `manifestation`, `"Compilations"` to `compilation`. |
| [`eidr_core.bmr_io.TEMPLATES`](#templates-constant) | constant | The six Template-22 content templates as `Template` values, keyed `episodic`, `non_episodic`, `edit`, `clip`, `manifestation` and `compilation`. |
| [`eidr_core.bmr_io.subset.required_headers`](#required_headers) | function | Returns the shipped headers whose absence makes a sheet not that template's data sheet: sheet mechanics plus required, never-inherited columns. |
| [`eidr_core.codes.normalize_country_code`](#normalize_country_code) | function | Returns the EIDR form of one country code, rewriting a dissolved or renamed country's alpha-2 code to alpha-4. |
| [`eidr_core.codes.OBSOLETE_ALPHA2_TO_ALPHA4`](#obsolete_alpha2_to_alpha4-constant) | constant | The crosswalk from former ISO 3166-1 alpha-2 codes of dissolved or renamed countries to their ISO 3166-3 alpha-4 codes: SU to SUHH, YU to YUCS, CS to CSHH (Czechoslovakia, not Serbia and Montenegro's CSXX), DD to DDDE, BU to BUMM. |
| [`eidr_core.compare.alt_source`](#alt_source) | function | Returns the namespace key under which an Alt ID's value is compared: its casefolded domain, else its casefolded type. |
| [`eidr_core.compare.cmp_actors`](#cmp_actors) | function | Compares actors lists by greedy one-to-one name alignment; quality is matched strength over the smaller list's size. |
| [`eidr_core.compare.cmp_alt_ids`](#cmp_alt_ids) | function | Compares third-party identifiers per namespace: a shared value is identity evidence; disagreeing values in a shared namespace are a conflict. |
| [`eidr_core.compare.cmp_assoc_orgs`](#cmp_assoc_orgs) | function | Matches associated organisations one-to-one, by equal party ID (1.0) or fuzzy normalised name, then scores proportionally. |
| [`eidr_core.compare.cmp_countries`](#cmp_countries) | function | Compares country-of-origin codes as exact matches after `norm_country`, so SU and SUHH count as one country. |
| [`eidr_core.compare.cmp_directors`](#cmp_directors) | function | Compares directors lists by greedy one-to-one name alignment; quality is matched strength over the smaller list's size. |
| [`eidr_core.compare.cmp_distribution_number`](#cmp_distribution_number) | function | Compares episode distribution numbers as tokens after stripping whitespace and leading zeros, with half credit for a likely renumbering. |
| [`eidr_core.compare.cmp_end_date`](#cmp_end_date) | function | Compares series or season end dates at year precision with an exponential half-life decay. |
| [`eidr_core.compare.cmp_house_sequence`](#cmp_house_sequence) | function | Compares house sequence numbers as exact tokens after stripping whitespace and leading zeros, so `0415` equals `415`. |
| [`eidr_core.compare.cmp_length`](#cmp_length) | function | Compares durations leniently, taking the better of an absolute and a relative credit. |
| [`eidr_core.compare.cmp_original_language`](#cmp_original_language) | function | Compares original-language codes as exact matches on the primary subtag after `norm_lang`, so `en-US` equals `en`. |
| [`eidr_core.compare.cmp_release_date`](#cmp_release_date) | function | Scores two release dates by precision, comparing full dates by day distance and anything coarser by year gap. |
| [`eidr_core.compare.cmp_sequence_number`](#cmp_sequence_number) | function | Compares season sequence numbers as exact tokens after stripping whitespace and leading zeros, so `05` equals `5`. |
| [`eidr_core.compare.cmp_time_slot`](#cmp_time_slot) | function | Compares episode time slots as exact strings after stripping surrounding whitespace. |
| [`eidr_core.compare.cmp_titles`](#cmp_titles) | function | Compares two records' title lists with part and segment rules, greedy one-to-one alignment, and diminishing credit for extra matches. |
| [`eidr_core.compare.cmp_version_language`](#cmp_version_language) | function | Compares version-language codes as exact matches on the primary subtag after `norm_lang`, so `fr-CA` equals `fr`. |
| [`eidr_core.compare.date_profile`](#date_profile) | function | Returns the date-comparison profile for a pair: the shared creation type's `DATE_PROFILES` entry, else the `Basic` entry. |
| [`eidr_core.compare.set_params`](#set_params) | function | Registers the process-wide object from which every comparator reads its tuning constants (`NL_MODIFIER`, `NAME_MATCH_MIN`, `DATE_*`, `DUR_*`, ...). |
| [`eidr_core.compare.validate_date_profile`](#validate_date_profile) | function | Checks a date profile for authoring defects and returns them as messages rather than raising them. |
| [`eidr_core.compare.FieldResult`](#fieldresult-class) | class | Holds one comparator's result for one field: quality, readable detail, Alt-ID conflict count and optional metadata. |
| [`eidr_core.compare.COMPARATORS`](#comparators-constant) | constant | Maps each engine field name to its comparator for the 14 weighted fields; every function takes `(submitted, candidate)` and returns a `FieldResult`. |
| [`eidr_core.compare.DATE_PROFILE_DEFAULT`](#date_profile_default-constant) | constant | The `DATE_PROFILES` key `date_profile` uses when the two creation types differ, a type is missing, or a type has no profile of its own. |
| [`eidr_core.compare.nonlinear.accumulate`](#accumulate) | function | Returns the best quality plus a capped, diminishing bonus q_k * r^(k-1) for each further match k. |
| [`eidr_core.compare.nonlinear.aggregate`](#aggregate) | function | Returns the opportunity-normalised series score: matched qualities weighted r^(i-1), divided by the weight sum of all opportunities. |
| [`eidr_core.compare.nonlinear.corroborate`](#corroborate) | function | Returns `accumulate(qualities, r)`, ignoring the opportunity count; deprecated. |
| [`eidr_core.compare.spec.load_spec`](#load_spec) | function | Loads compare-spec.json and returns its constants as a `{NAME: value}` dict with Python container semantics restored. |
| [`eidr_core.compare.spec.spec_path`](#spec_path) | function | Returns the path of the packaged compare-spec.json, located through importlib.resources rather than a source-tree path. |
| [`eidr_core.compare.states.band`](#band) | function | Bands one quality into a UI state: identical from `identical_at`, similar from `similar_at`, else mismatch or neutral. |
| [`eidr_core.compare.states.field_not_counted`](#field_not_counted) | function | Lists fields that have a real quality but were not counted in the score, naming the affected side. |
| [`eidr_core.compare.states.field_states`](#field_states) | function | Builds the payload's `field_states` and `field_qualities` maps from an engine rationale, keyed by UI field-manifest keys. |
| [`eidr_core.compare.states.ui_field_key`](#ui_field_key) | function | Maps an engine field name to its De-Dupe UI field-manifest key, such as `title` to `titles`. |
| [`eidr_core.compare.titles.is_internal`](#is_internal) | function | Returns True for a title with text whose class is `Internal` (case-insensitive, stripped) and that is not also system-generated. |
| [`eidr_core.compare.titles.parse_part`](#parse_part) | function | Parses a part number out of a title and returns the normalised base title with the part as an integer. |
| [`eidr_core.compare.titles.parts_ambiguous`](#parts_ambiguous) | function | Returns True when any title pair has a part number on exactly one side and the bases agree. |
| [`eidr_core.compare.titles.parts_conflict`](#parts_conflict) | function | Returns True when titles carry a distinguishing part signal: one base, different part numbers, or numbered against bare. |
| [`eidr_core.compare.titles.segments`](#segments) | function | Splits a compound title on `/` or `;` into normalised segments; returns None for a single-segment title. |
| [`eidr_core.compare.titles.select_titles`](#select_titles) | function | Chooses which titles to compare: the real ones if any exist, otherwise every title with text, flagged as fallback. |
| [`eidr_core.compare.titles.title_similarity`](#title_similarity) | function | Returns the similarity of two raw titles in [0, 1], applying part-number and segment rules before plain fuzzy matching. |
| [`eidr_core.compare.titles.COMBINATION_DIFFERS_QUALITY`](#combination_differs_quality-constant) | constant | Similarity `title_similarity(..., episodic=True)` returns when two compound titles are different segment combinations, or when an undelimited title does not hold every segment of a delimited one. |
| [`eidr_core.compare.titles.PART_AMBIGUOUS_QUALITY`](#part_ambiguous_quality-constant) | constant | Similarity `title_similarity(..., episodic=True)` returns when only one title carries a part number and the bases agree (>= 0.85), so the title alone cannot carry a pair to Accept. |
| [`eidr_core.db_schemas.assert_tables`](#assert_tables) | function | Checks that every table and column a consumer declares exists in the packaged schema contract. |
| [`eidr_core.db_schemas.contract_version`](#contract_version) | function | Returns the version string of a database's packaged schema contract. |
| [`eidr_core.db_schemas.load_manifest`](#load_manifest) | function | Loads and returns a database's packaged schema manifest as a dict. |
| [`eidr_core.db_schemas.table_columns`](#table_columns) | function | Returns the column names of one table as listed in the packaged contract. |
| [`eidr_core.db_schemas.DATABASES`](#databases-constant) | constant | The four database names that have a packaged contract. |
| [`eidr_core.dictionary.changes`](#changes) | function | Returns the dictionary's Changes entries, newest first, optionally only those after a version. |
| [`eidr_core.dictionary.lookup`](#lookup) | function | Returns the dictionary entry for a name, or the section for a module path. |
| [`eidr_core.dictionary.text`](#text) | function | Reads the dictionary shipped inside the installed package. |
| [`eidr_core.external.call_with_failover`](#call_with_failover) | function | Runs one request across an ordered endpoint chain, retrying, backing off, honouring Retry-After and failing over per your verdicts. |
| [`eidr_core.external.classify_sparql_error`](#classify_sparql_error) | function | Classifies a SPARQL exception into a failover verdict by matching its message text in a fixed order. |
| [`eidr_core.external.endpoint_chain`](#endpoint_chain) | function | Builds the ordered, de-duplicated endpoint list for `call_with_failover`: primary first, then fallbacks. |
| [`eidr_core.external.DictFactCache`](#dictfactcache-class) | class | Keeps fact entries in a plain in-memory dict, with no expiry and no persistence. |
| [`eidr_core.external.FactCache`](#factcache-class) | class | Defines the two-method cache interface that source clients and crosswalks take instead of a database connection. |
| [`eidr_core.external.JsonFactCache`](#jsonfactcache-class) | class | Persists fact entries in one JSON file, with an optional single expiry time and atomic whole-file writes. |
| [`eidr_core.external.NullFactCache`](#nullfactcache-class) | class | Implements `FactCache` by storing nothing and returning nothing, so every lookup becomes a fetch. |
| [`eidr_core.external.Entry`](#entry-constant) | constant | Type alias (plain `dict` at runtime) for one cached fact dict in the fact-dict contract: key "status" is "found", "not_found" or "error"; key "facts" may hold "runtime_minutes" (list of float), "episode_runtime_minutes" (list of float), "release_date" ("YYYY-MM-DD", earliest known), "release_date_precision" ("day", "month" or "year") and "label" (str); key "error" (str) is present when status is "error". |
| [`eidr_core.external.FATAL`](#fatal-constant) | constant | Verdict string a `classify` returns when no endpoint can help (authentication failure, malformed input): the walk stops at once and `call_with_failover` returns `(None, None, exc)`. |
| [`eidr_core.external.Key`](#key-constant) | constant | Type alias for a cache key: `(source, external_id)`, both strings, for example `("wikidata", "Q42")` as eidr-dq writes them. |
| [`eidr_core.external.NEXT_ENDPOINT`](#next_endpoint-constant) | constant | Verdict string for "this endpoint will not take this request" (for example a stricter SPARQL parser): move to the next endpoint at once, without remembering it, since it may still serve other requests. |
| [`eidr_core.external.OUTAGE`](#outage-constant) | constant | Verdict string for "this endpoint is down for the whole workload": move on at once and add it to `outage_endpoints`, so later calls sharing that set skip it instead of spending their retry budget. |
| [`eidr_core.external.RETRY`](#retry-constant) | constant | Verdict string for a transient failure (429 or 5xx class): retry the same endpoint after backoff (and any Retry-After wait), up to `max_retries` attempts in total. |
| [`eidr_core.external.failover.cooldown_remaining`](#cooldown_remaining) | function | Returns how many seconds remain before an endpoint may be called, according to a `cooldowns` memo. |
| [`eidr_core.external.failover.http_status`](#http_status) | function | Reads the HTTP status an exception carries from its attributes (urllib, requests, botocore, provider exceptions), never from text. |
| [`eidr_core.external.failover.is_bad_query_error`](#is_bad_query_error) | function | Tests whether a SPARQL exception is a query-syntax or bad-request error that retrying will not fix. |
| [`eidr_core.external.failover.is_outage_error`](#is_outage_error) | function | Tests whether an exception's text carries a known Wikidata Query Service outage signature. |
| [`eidr_core.external.failover.retry_after_seconds`](#retry_after_seconds) | function | Returns the Retry-After interval an exception carries, in seconds, from the delta-seconds or HTTP-date form. |
| [`eidr_core.external.failover.DEFAULT_MAX_RETRY_AFTER`](#default_max_retry_after-constant) | constant | Default `max_retry_after`, in seconds (10 minutes): the longest Retry-After or cooldown wait slept inside one call. |
| [`eidr_core.external.failover.DEFAULT_RATE_LIMIT_FLOOR`](#default_rate_limit_floor-constant) | constant | Default `rate_limit_floor`, in seconds: the wait before the next attempt on an endpoint that answered 429 or 503 without a Retry-After value (Wikimedia's "wait at least five seconds" rule, applied to 503 as well). |
| [`eidr_core.external.failover.OUTAGE_SIGNATURES`](#outage_signatures-constant) | constant | Message fragments, matched case-insensitively by `is_outage_error`, meaning a WDQS endpoint is rate-limiting the whole workload (observed verbatim in the 2026-05-09/10 WDQS outages). |
| [`eidr_core.external.failover.RATE_LIMIT_STATUSES`](#rate_limit_statuses-constant) | constant | HTTP statuses (429 Too Many Requests, 503 Service Unavailable) for which `call_with_failover` waits `rate_limit_floor` and records a cooldown when the exception carries no Retry-After value. |
| [`eidr_core.external.failover.TRANSIENT_HTTP_MARKERS`](#transient_http_markers-constant) | constant | Status-code substrings that make `classify_sparql_error` return `RETRY` when found anywhere in an exception's text (tested after the outage and bad-query checks). |
| [`eidr_core.ids.category`](#category) | function | Classifies a DOI into its EIDR ID family by prefix alone. |
| [`eidr_core.ids.check_character`](#check_character) | function | Computes the ISO 7064 Mod 37,36 check character for an EIDR suffix payload. |
| [`eidr_core.ids.fault`](#fault) | function | Returns the reason a Content ID is unsound, or `None` when it is sound. |
| [`eidr_core.ids.find_content_ids`](#find_content_ids) | function | Extracts every EIDR Content ID mentioned in free text, upper-cased and de-duplicated in order of appearance. |
| [`eidr_core.ids.is_valid_eidr_id`](#is_valid_eidr_id) | function | Tests whether a value is a well-formed, checksum-valid EIDR Content ID. |
| [`eidr_core.ids.is_valid_party_id`](#is_valid_party_id) | function | Tests whether a value matches the party DOI pattern `PARTY_ID_RE`. |
| [`eidr_core.ids.is_valid_service_id`](#is_valid_service_id) | function | Tests whether a value matches the service DOI pattern `SERVICE_ID_RE`. |
| [`eidr_core.ids.is_valid_user_id`](#is_valid_user_id) | function | Tests whether a value matches the user DOI pattern `USER_ID_RE`. |
| [`eidr_core.ids.ALPHABET`](#alphabet-constant) | constant | The ISO 7064 Mod 37,36 base-36 alphabet, digits then upper-case letters. |
| [`eidr_core.ids.CONTENT_ID_SEARCH_RE`](#content_id_search_re-constant) | constant | Compiled, case-insensitive, UNANCHORED Content ID shape for searching free text. |
| [`eidr_core.ids.EIDR_CONTENT_ID_RE`](#eidr_content_id_re-constant) | constant | Compiled, case-insensitive, ANCHORED Content ID shape: `10.5240/`, five 4-hex groups, one check character. |
| [`eidr_core.ids.PARTY_ID_RE`](#party_id_re-constant) | constant | Compiled, anchored party DOI pattern: `10.5237/` plus `PARTY_ID_SUFFIX`. |
| [`eidr_core.ids.PARTY_ID_SUFFIX`](#party_id_suffix-constant) | constant | Regex source string (not compiled) for the part after `10.5237/`: `XXXX-XXXX` hex in either case, or the literal lower-case `superparty`. |
| [`eidr_core.ids.SERVICE_ID_RE`](#service_id_re-constant) | constant | Compiled, anchored service DOI pattern: `10.5239/` plus `SERVICE_ID_SUFFIX`. |
| [`eidr_core.ids.SERVICE_ID_SUFFIX`](#service_id_suffix-constant) | constant | Regex source string for the part after `10.5239/`: `XXXX-XXXX`, hex, either case, no check character. |
| [`eidr_core.ids.USER_ID_RE`](#user_id_re-constant) | constant | Compiled, anchored user DOI pattern: `10.5238/` plus `USER_ID_SUFFIX`. |
| [`eidr_core.ids.USER_ID_SUFFIX`](#user_id_suffix-constant) | constant | Regex source string for the username after `10.5238/`: 3 to 32 characters from `0-9 a-z A-Z _ # . |
| [`eidr_core.inheritance.build_full_base`](#build_full_base) | function | Builds a child's full registry-JSON `BaseObjectData` from its self-defined one plus its parent's full one. |
| [`eidr_core.inheritance.build_full_record`](#build_full_record) | function | Builds a child's full record object from its self-defined one and its parent's full record, by the `build_full_base` policy. |
| [`eidr_core.inheritance.has_user_supplied_title`](#has_user_supplied_title) | function | Tells whether a ResourceName value carries at least one title the submitter supplied, as opposed to a system-generated one. |
| [`eidr_core.inheritance.is_absent`](#is_absent) | function | Applies the portfolio's emptiness rule, deciding whether a value is absent for inheritance purposes. |
| [`eidr_core.inheritance.provenance`](#provenance) | function | Returns the per-field provenance map `build_full_record` attached to a record. |
| [`eidr_core.inheritance.system_generated_title`](#system_generated_title) | function | Builds the registry's system-generated title for a Season or Episode from the parent's title plus a number or a date. |
| [`eidr_core.inheritance.TitleConstructionError`](#titleconstructionerror-class) | class | Signals that a Season or Episode needed a generated title and the data could not build one. |
| [`eidr_core.inheritance.CHILD_TYPES`](#child_types-constant) | constant | The only creation types that inherit at all. |
| [`eidr_core.inheritance.INHERITABLE_FIELDS`](#inheritable_fields-constant) | constant | The 12 canonical `BaseObjectData` fields a child may inherit from its parent's full record. |
| [`eidr_core.inheritance.NEVER_INHERITED`](#never_inherited-constant) | constant | Fields a child never inherits, listed explicitly so none is re-added by mistake. |
| [`eidr_core.inheritance.RECORD_ATTRS`](#record_attrs-constant) | constant | Default map from canonical EIDR field name to record attribute name for `build_full_record`. |
| [`eidr_core.inheritance.TITLE_EXEMPT_TYPES`](#title_exempt_types-constant) | constant | The child types that never inherit the parent's title and get a system-generated one instead. |
| [`eidr_core.inheritance.TITLE_INHERITING_TYPES`](#title_inheriting_types-constant) | constant | The child types that inherit the parent's ResourceName verbatim. |
| [`eidr_core.normalize.ascii_fold`](#ascii_fold) | function | Folds Latin diacritics and ligatures to ASCII so they do not count as differences. |
| [`eidr_core.normalize.cmp_key`](#cmp_key) | function | Builds the canonical comparison key; equal keys are treated as a match. |
| [`eidr_core.normalize.days_between`](#days_between) | function | Returns the absolute number of days between two `(year, month, day)` tuples. |
| [`eidr_core.normalize.nfkc`](#nfkc) | function | Applies Unicode NFKC normalisation, folding compatibility forms such as full-width letters and ligature code points. |
| [`eidr_core.normalize.norm_code`](#norm_code) | function | Normalises a country or language code for comparison, treating wildcard and unknown codes as absent. |
| [`eidr_core.normalize.norm_country`](#norm_country) | function | Normalises a country code for field comparison, adding the obsolete alpha-2 to alpha-4 crosswalk to `norm_code`. |
| [`eidr_core.normalize.norm_lang`](#norm_lang) | function | Reduces a language tag to its lower-case primary subtag for comparison. |
| [`eidr_core.normalize.norm_name`](#norm_name) | function | Normalises a personal or organisation name for comparison. |
| [`eidr_core.normalize.norm_title`](#norm_title) | function | Normalises a title for comparison, folding Unicode, case, punctuation, numerals and common word variants. |
| [`eidr_core.normalize.parse_date`](#parse_date) | function | Parses a date into a year and an optional `(year, month, day)` tuple. |
| [`eidr_core.normalize.parse_minutes`](#parse_minutes) | function | Parses a duration into minutes. |
| [`eidr_core.normalize.parse_registrant_extra`](#parse_registrant_extra) | function | Reads the length and release-date estimate flags from a Registrant Extra value. |
| [`eidr_core.normalize.sanitize_field`](#sanitize_field) | function | Makes a text value safe to carry through a TSV file or PostgreSQL COPY stream without changing what it says. |
| [`eidr_core.normalize.aliases.alias_name`](#alias_name) | function | Returns the canonical form of a personal or organisation name token. |
| [`eidr_core.normalize.aliases.alias_title`](#alias_title) | function | Returns the canonical form of a title or company token. |
| [`eidr_core.normalize.aliases.ORDINALS`](#ordinals-constant) | constant | Spelled ordinals `first` to `twelfth` (lower-case keys) mapped to the digit strings `'1'` to `'12'`. |
| [`eidr_core.ordering.altid_canonical_key`](#altid_canonical_key) | function | Returns the canonical sort key for one Alt ID: kind (Type, Domain), then value, all casefolded. |
| [`eidr_core.ordering.altid_collapsed_canonical_key`](#altid_collapsed_canonical_key) | function | Returns the canonical sort key for an Alt ID whose Type and Domain arrive as one Kind string. |
| [`eidr_core.ordering.altid_display_key`](#altid_display_key) | function | Returns the display sort key for one Alt ID: IMDb-typed entries first, then canonical kind and value. |
| [`eidr_core.ordering.altid_kind`](#altid_kind) | function | Returns the Alt ID kind composite (casefolded Type, casefolded Domain) used for grouping and sorting. |
| [`eidr_core.ordering.ck`](#ck) | function | Returns the casefolded sort key for a value, treating None as an empty string. |
| [`eidr_core.ordering.is_internal_class`](#is_internal_class) | function | Tests whether a Title Class is `Internal` (casefolded, exact match). |
| [`eidr_core.ordering.is_resource_class`](#is_resource_class) | function | Tests whether a Title Class marks the primary title, meaning it casefolds to `release` or `resource`. |
| [`eidr_core.ordering.is_shortdoi`](#is_shortdoi) | function | Tests whether an Alt ID is a ShortDOI, by its Type or its Domain (casefolded, exact match). |
| [`eidr_core.ordering.title_bucket`](#title_bucket) | function | Returns the three-bucket rank of a title: ResourceName, then non-Internal alternates, then Internal alternates. |
| [`eidr_core.ordering.title_sort_key`](#title_sort_key) | function | Returns the full title sort key: the three-bucket rank, then the casefolded text. |
| [`eidr_core.registry.build_registry_credentials`](#build_registry_credentials) | function | Builds SDK `Credentials` from a project secrets dict, falling back to the SDK's own credential discovery. |
| [`eidr_core.registry.get_registry_client`](#get_registry_client) | function | Builds the configured SDK `Client` that every portfolio program must use for live registry calls. |
| [`eidr_core.registry.parse_operation_status`](#parse_operation_status) | function | Extracts the registry's verdict on one write from a status-lookup body; None means no verdict yet. |
| [`eidr_core.registry.parse_operation_statuses`](#parse_operation_statuses) | function | Extracts every operation verdict from a paged status-lookup body, skipping blocks that still say pending. |
| [`eidr_core.registry.token_operation_status`](#token_operation_status) | function | Polls a live SDK write token and returns the registry's real verdict, or None when there is none yet. |
| [`eidr_core.registry.OperationStatus`](#operationstatus-class) | class | Holds the registry's reached verdict on one submitted write: code, type, details and token. |
| [`eidr_core.registry.CODE_PENDING`](#code_pending-constant) | constant | The registry's in-block "still processing" code (observed 2026-10-01 on sandbox1 as Code 2 / Type pending). |
| [`eidr_core.registry.CODE_SUCCESS`](#code_success-constant) | constant | The registry's only success code. |
| [`eidr_core.registry.DEFAULT_REGISTRY`](#default_registry-constant) | constant | Default `registry` for `get_registry_client`: Sandbox 2, which mirrors the production schema and is safe to write to. |
| [`eidr_core.secrets_loader.load_aws`](#load_aws) | function | Fetches one secret from AWS Secrets Manager and parses it as JSON. |
| [`eidr_core.secrets_loader.load_local`](#load_local) | function | Reads a local secrets JSON file, tolerating trailing commas before `}` or `]`. |
| [`eidr_core.secrets_loader.load_secrets`](#load_secrets) | function | Loads a program's secrets in the portfolio order: explicit path, local-mode flag, then AWS with local fallback. |
| [`eidr_core.secrets_loader.SecretsError`](#secretserror-class) | class | Signals that secrets could not be loaded: missing or invalid local file, missing boto3, or an AWS failure. |
| [`eidr_core.vendor.check`](#check) | function | Returns the drift problems between a vendored copy and its manifest; an empty list means clean. |
| [`eidr_core.vendor.load_manifest`](#load_manifest) | function | Reads and validates a consumer's `vendor.toml` into a Manifest. |
| [`eidr_core.vendor.sync`](#sync) | function | Replaces the consumer's target directory with the listed modules copied from the pinned commit, imports rewritten. |
| [`eidr_core.vendor.Manifest`](#manifest-class) | class | Holds the validated `[vendor]` table of a consumer's `vendor.toml`. |
| [`eidr_core.vendor.SyncReport`](#syncreport-class) | class | Reports what `sync` wrote: target directory, commit, eidr-core version and per-file hashes. |
| [`eidr_core.vendor.VendorError`](#vendorerror-class) | class | Signals that the manifest, the eidr-core source, or the vendored tree breaks the vendoring contract. |
| [`eidr_core.vendor.MANIFEST_FILE`](#manifest_file-constant) | constant | File name of the hash manifest that `sync` writes in the target directory and `check` reads. |
| [`eidr_core.vendor.SPEC_VERSION`](#spec_version-constant) | constant | Version of `specs/vendoring.md` this tool implements. |
| [`eidr_core.verify.compare_release_date`](#compare_release_date) | function | Compares a registered release date or year with an external release-date fact, honouring the fact's precision. |
| [`eidr_core.verify.compare_runtime`](#compare_runtime) | function | Compares a registered runtime with the closest external runtime, within the larger of two tolerances. |
| [`eidr_core.verify.compare_year_arbitration`](#compare_year_arbitration) | function | Reports which of a record's two disagreeing date fields an external release date supports. |
| [`eidr_core.verify.parse_iso_date`](#parse_iso_date) | function | Parses the leading YYYY-MM-DD date from a value, returning None instead of raising. |
| [`eidr_core.verify.runtime_candidates`](#runtime_candidates) | function | Collects every comparable runtime in a fact set as floats in minutes, including series episode runtimes. |
<!-- /dict-index -->

## `eidr_core.altidtool_io`

<!-- dict-module:eidr_core.altidtool_io -->
Source `src/eidr_core/altidtool_io/__init__.py`. Public names: 5 functions, 2 classes (declared by `__all__`).
<!-- /dict-module -->

**Purpose.** The one implementation of the EIDR AltIDTool input-file line format: tab-separated `EIDR_ID, Type, Value[, Domain][, Relation]`, UTF-8, no header, 3 to 5 columns wide. It was extracted on 2026-08-04 from eidr-wikidata `bmr/altidtool.py` (the production feed generator) so that every producer composes lines the same way and every reader parses them the same way. Since spec v1.1 it also reads AltIDTool edit files (removal lines and `//` comments). Since v1.4 it also hosts the declared list of Proprietary domains exempt from rule 6 (`multi_form_domains`).

**Use it when.** You are in one of these situations:
* You write a file for the AltIDTool. Compose each line with `format_line`, or write the whole file with `write_lines`.
* You read back an additions-only file that a portfolio producer wrote: `parse_line`.
* You read an AltIDTool edit file that may hold removals, blank lines or `//` comments: `parse_edit_line`.
* You apply altidtool-format rule 6 (a second `IsSameAs` value of one Kind is a conflict) and need the Kinds exempt from it: `multi_form_domains()`.

**Do not use it when.** The job is one of these:
* Do not reimplement the line format (an f-string with `\t`, a fixed-5 writer, trailing tabs). Call `format_line` or `write_lines`. The empty-Domain placeholder and "Relation only when non-empty" rules are easy to get wrong.
* Do not keep a local copy of the multi-form domain list. Call `multi_form_domains()`.
* Other formats: MCP's `eidrtoaltid.py` extract report (it has a header and its own columns), remediation action TSVs, and BMR-Review's de-dupe outputs are not this format.
* Do not read an edit file with `parse_line`. It refuses 1- or 2-column removals and most comments, but it reads a 3-column removal (empty Value) as an addition with an empty value, and a `//` comment holding 2 to 4 tabs as a row. Use `parse_edit_line`.
* Content validation: nothing here checks EIDR ID syntax (use `eidr_core.ids`), whether a domain belongs on a named type, or whether a value is URI-safe. That is the caller's job.
* Vendoring: since 0.39.0 the module cannot be vendored. `multi_form_domains` reads package data through `files("eidr_core")`, so `eidr_core.vendor.sync` refuses the module (residual reference). python-tools' vendored copy is pinned at 0.34.1, before that function existed.

**Used by.**
<!-- dict-usedby:eidr_core.altidtool_io -->
Scan of 2026-10-02; regenerated at each release from the consumer trees.
* **BMRtoAltID**: `format_line`, `multi_form_domains`
* **eidr-imdb**: `AltIdRow`, `format_line`, `parse_line`, `write_lines`
* **eidr-wikidata**: `format_line`, `multi_form_domains`, `parse_line`
* **python-tools**: (vendors the module, pin `cc13c83`)
<!-- /dict-usedby -->

**Specs.** `specs/altidtool-format.md` v1.5 fixes the column layout, the removal lines (v1.1), the identity and relation rules 1-6, and the multi-form exemption. `src/eidr_core/specs/multi_form_kinds.json` holds the exempt list, with the measurement or operator ruling behind each entry.

### `format_line`

<!-- dict:eidr_core.altidtool_io.format_line -->
```python
def format_line(eidr_id: str, alt_type: str, value: str, domain: str = "", relation: str = "") -> str
```

Defined in `src/eidr_core/altidtool_io/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `eidr_id` | `str` | required | Column 1: the EIDR Content ID (`10.5240/...`) of the record that receives the Alt ID. Written as given, not validated. |
| `alt_type` | `str` | required | Column 2: a named Alt ID type (`IMDB`, `ISAN`, ...) or `Proprietary`. Written as given. |
| `value` | `str` | required | Column 3: the identifier value. Written as given; a tab or newline inside it breaks the line. |
| `domain` | `str` | `""` | Column 4: the altIdDomain for `Proprietary` rows. Leave `""` for named types. Any non-empty string is written, whatever the type. |
| `relation` | `str` | `""` | Column 5. `""` means IsSameAs and nothing is written. A non-empty value (`Deprecated`, `IsEntirelyContainedBy`) is written, after an empty Domain placeholder when `domain` is `""`. |

**Returns** `str` -- One line with no trailing newline: 3 columns (no domain, no relation), 4 columns (domain, no relation), or 5 columns (relation present; column 4 empty when there is no domain).
<!-- /dict -->

**Does.** Composes one AltIDTool input line from its fields under the canonical variable-width rules. Pure, with no I/O, and never raises for string input. It validates and escapes nothing, and an explicit `"IsSameAs"` relation is written as given (pass `""` to leave the column off).

### `multi_form_domains`

<!-- dict:eidr_core.altidtool_io.multi_form_domains -->
```python
def multi_form_domains() -> frozenset[str]
```

Defined in `src/eidr_core/altidtool_io/__init__.py`.

No parameters.

**Returns** `frozenset[str]` -- Lowercased, whitespace-stripped Proprietary domains exempt from rule 6. At 0.43.0: `decellc.com`, `mediafilm.ca`, `pbs.org`. Named types never appear.
<!-- /dict -->

**Does.** Returns the Proprietary domains exempt from altidtool-format rule 6, read from the packaged `multi_form_kinds.json`. Compare a Kind's domain, lowercased, against the set; a listed Kind may legitimately hold several `IsSameAs` values. It reads the package data file on every call (no cache) and raises if the file is missing or malformed (FileNotFoundError, json.JSONDecodeError, KeyError). An entry is listed on a `measured` or an operator-`ruled` basis, but callers get one set either way.

**Notes.** Call it once per run and keep the result, rather than once per row. Never copy the list into a consumer. This function is why the module cannot be vendored today: the literal `files("eidr_core")` fails `sync`'s residual-reference check, and the JSON file sits outside the module directory.

### `parse_edit_line`

<!-- dict:eidr_core.altidtool_io.parse_edit_line -->
```python
def parse_edit_line(line: str) -> AltIdRow | AltIdRemoval | None
```

Defined in `src/eidr_core/altidtool_io/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `line` | `str` | required | One line of an AltIDTool edit file. Trailing `\r` and `\n` are stripped, the line is split on tabs, and each column is whitespace-trimmed. |

**Returns** `AltIdRow | AltIdRemoval | None` -- An `AltIdRow` for an addition (3-5 columns with a non-empty Value). An `AltIdRemoval` for a removal (1 column, 2 columns, or 3-5 columns with an empty Value). `None` for a blank line or one whose first non-space characters are `//`.
<!-- /dict -->

**Does.** Parses one AltIDTool edit-file line into an addition, a removal, or None for a blank or comment line. Raises ValueError when column 1 (the EIDR ID) is empty or the line has more than 5 columns. Unlike `parse_line` it trims each column, so the two parsers can return different strings for the same addition line.

**Notes.** An empty Type in a removal shape gives `alt_type=""`, the remove-every-Alt-ID sentinel. So `ID<TAB>` and `ID<TAB><TAB>` both parse as "remove all". An addition with an empty Type (`ID<TAB><TAB>value`) comes back as an `AltIdRow`, not an error. Check rows before you apply them.

### `parse_line`

<!-- dict:eidr_core.altidtool_io.parse_line -->
```python
def parse_line(line: str) -> AltIdRow
```

Defined in `src/eidr_core/altidtool_io/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `line` | `str` | required | One AltIDTool line of 3, 4 or 5 tab-separated columns. Trailing `\r` and `\n` are stripped; nothing else is trimmed. |

**Returns** `AltIdRow` -- The row, with missing trailing columns set to `""`. Column text is kept exactly as found, surrounding spaces included.
<!-- /dict -->

**Does.** Parses one 3-, 4- or 5-column AltIDTool addition line back into an AltIdRow. Raises ValueError for any other column count, which catches blank lines, 1- or 2-column removals and `//` comments with fewer than 2 tabs. It also accepts the retired BMRtoAltID fixed-5 dialect with empty trailing columns. Only the column count is checked: an empty Value or a malformed EIDR ID is returned as found.

**Notes.** Under spec v1.1 a 3-column line with an empty Value is a removal, but `parse_line` returns it as an `AltIdRow` with `value=""`. A `//` comment that holds 2 to 4 tabs also comes back as an `AltIdRow` (with `eidr_id` starting `//`). Use `parse_edit_line` for any file that may contain removals or comments.

### `write_lines`

<!-- dict:eidr_core.altidtool_io.write_lines -->
```python
def write_lines(path: str | os.PathLike[str], rows: Iterable[AltIdRow | tuple[str, ...]]) -> int
```

Defined in `src/eidr_core/altidtool_io/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `path` | `str \| os.PathLike[str]` | required | File to write. It is opened for writing, so an existing file is overwritten. The parent directory must already exist. |
| `rows` | `Iterable[AltIdRow \| tuple[str, ...]]` | required | Rows in `format_line` argument order: `AltIdRow` objects, or plain tuples of 3 to 5 strings `(eidr_id, alt_type, value[, domain[, relation]])`. A generator works. |

**Returns** `int` -- The number of lines written. An empty `rows` returns 0 and still leaves an empty file.
<!-- /dict -->

**Does.** Writes rows to `path` as an AltIDTool input file (UTF-8, LF line endings, no header) and returns the count. Each row is unpacked into `format_line`. A tuple with fewer than 3 or more than 5 items raises TypeError at that row, leaving a partly written file.

### `AltIdRemoval` (class)

<!-- dict:eidr_core.altidtool_io.AltIdRemoval -->
```python
class AltIdRemoval(NamedTuple)
```

Defined in `src/eidr_core/altidtool_io/__init__.py`.

| Field | Type | Default | Purpose |
|---|---|---|---|
| `eidr_id` | `str` | required | EIDR ID of the record whose Alt IDs are removed (column 1). |
| `alt_type` | `str` | `""` | Type whose Alt IDs are all removed (`IMDB`, ...). `""` means remove every Alt ID on the record. |
<!-- /dict -->

**Does.** Represents one AltIDTool removal line, as returned by `parse_edit_line`. Portfolio producers never emit removals; the python-tools `AltIDTool` reads them. This module has no formatter for removals.

### `AltIdRow` (class)

<!-- dict:eidr_core.altidtool_io.AltIdRow -->
```python
class AltIdRow(NamedTuple)
```

Defined in `src/eidr_core/altidtool_io/__init__.py`.

| Field | Type | Default | Purpose |
|---|---|---|---|
| `eidr_id` | `str` | required | EIDR Content ID that receives the Alt ID (column 1). |
| `alt_type` | `str` | required | Named Alt ID type or `Proprietary` (column 2). |
| `value` | `str` | required | The identifier value (column 3). |
| `domain` | `str` | `""` | altIdDomain for `Proprietary` rows (column 4). `""` for named types. |
| `relation` | `str` | `""` | Relation (column 5). `""` means IsSameAs. |
<!-- /dict -->

**Does.** Holds one AltIDTool addition line as a NamedTuple in column order. The field order matches `format_line`, so `format_line(*row)` composes the line and `write_lines` accepts rows directly. `parse_line` and `parse_edit_line` return it.

## `eidr_core.bmr_io`

<!-- dict-module:eidr_core.bmr_io -->
Source `src/eidr_core/bmr_io/__init__.py`. Public names: 21 functions, 9 classes, 9 constants (declared by `__all__`). Some are defined in, and also importable from: `src/eidr_core/bmr_io/subset.py`, `src/eidr_core/bmr_io/writer.py`.
<!-- /dict-module -->

**Purpose.** The one shared implementation for reading, writing and editing EIDR BMR workbooks: the Template-22 `.xlsx` sheets the BMR tool registers from. It holds the workbook surgery (extracted 2026-08-03 from eidr-wikidata `bmr/writer.py`, replacing a copy in BMR-Review that had drifted), the reader half (2026-08-06; the streaming `open_sheet` was contributed by BMRtoAltID), parent-reference resolution, the Template-22 facts and the writer composition (2026-09-11, from eidr-wikidata, with BMR-Review as second consumer), and the row-subset copy (2026-09-11, for BMRtoAltID). It is shared because several projects read or write these sheets and their private copies drifted: header scans that stopped at the first blank cell, family pairing that shifted companion columns, and routing tables that disagreed on Compilation.

**Use it when.**
* You read a BMR sheet: `open_sheet` (streaming, with absolute row numbers) or `read_sheet` (materialized); `read_headers` or `header_map` for the header row alone.
* You pair the columns of a repeating family (`Alternate Title N` with `Alt Title Language N`, and so on): `family_layout`.
* You resolve `Parent EIDR/Row ID`: build an index with `index_rows`, then call `resolve_parent` or `parent_chain`.
* You write rows onto a Template-22 sheet: map each row to `{column name: value}` in your project, route it with `template_for_creation_type`, then call `write_sheet`.
* You send some rows of an existing BMR sheet onward (`subset_rows`), write one column back into a sheet (`fill_column`), or want to know first whether a sheet conforms (`check_sheet`).
* You flatten records into a wide repeat-group layout: `RepeatPlan` plus `pad_groups`.

**Do not use it when.**
* You are deciding WHAT a row says: field mapping, value trimming, blank sentinels, the "." to Proprietary domain split, ShortDOI filtering, IMDb/ISAN singleton promotion, sheet auto-detection. That is consumer policy and stays in your project.
* You need a Service template sheet: `TEMPLATES` deliberately leaves it out.
* Your sheet's headers are not on row 3 (a workbook round-tripped through review). Find the header row yourself, then pass `header_row=` to `open_sheet` / `read_sheet` / `read_headers`, or call `header_map` on that row. `check_sheet`, `subset_rows`, `fill_column`, `write_sheet` and `expand_family` all assume row 3.
* Do not reimplement a header scan, a numbered-family regex, a `Parent EIDR/Row ID` lookup, a creation-type routing table or a zip-level worksheet swap. Call `header_map` / `read_headers`, `family_layout` / `count_family`, `resolve_parent`, `template_for_creation_type`, `transplant`.
* Do not rebuild a subset of a BMR sheet from parsed records. Copy it with `subset_rows`, which cannot lose a column you never parsed.

**Used by.**
<!-- dict-usedby:eidr_core.bmr_io -->
Scan of 2026-10-02; regenerated at each release from the consumer trees.
* **BMR-Review**: `families_for`, `header_map`, `index_rows`, `read_headers`, `resolve_parent`, `template_for_creation_type`, `write_sheet`
* **BMRtoAltID**: `ASSIGNED_ID_COLUMN`, `check_sheet`, `DATA_START`, `family_layout`, `fill_column`, `HEADER_ROW`, `open_sheet`, `ROW_ID_COLUMN`, `SHEET_TO_TEMPLATE`, `subset_rows`, `TemplateMismatch`
* **eidr-dq**: `pad_groups`, `RepeatPlan`
* **eidr-imdb**: `DATA_START`, `HEADER_ROW`, `TEMPLATES`, `write_sheet`
* **eidr-wikidata**: `count_family`, `DATA_START`, `expand_family`, `families_for`, `family_layout`, `fix_shared_strings`, `HEADER_ROW`, `pad_groups`, `read_headers`, `read_sheet`, `RepeatPlan`, `rightmost_in`, `SCHEMA_MAX`, `transplant`, `write_sheet`
* **XML_to_JSON**: `DATA_START`, `family_layout`, `HEADER_ROW`, `index_rows`, `read_headers`, `read_sheet`, `resolve_parent`, `SHEET_TO_TEMPLATE`, `template_for_creation_type`, `TEMPLATES`, `write_sheet`
<!-- /dict-usedby -->

**Specs.** No versioned spec governs this module. `specs/merge-rules.md` (DRAFT) makes `SCHEMA_MAX` (as `write_sheet` uses it) the per-family caps of the planned merge engine, never the .NET tool's hardcoded caps, and requires the planned B5 mapper to read families sparsely, as `family_layout` does. `specs/vendoring.md` 1.0.0 section 6 notes that a vendored `bmr_io.read_sheet` still needs openpyxl. `specs/merge-rules.md` also plans for python-tools' `MergeTool` to vendor `bmr_io` (S4), but the module is not vendorable as it stands: comments and docstrings in `__init__.py` and `subset.py` contain the text `eidr_core`, which `vendor sync` refuses, and `resolve_parent` needs `ids` vendored with it.

### `check_sheet`

<!-- dict:eidr_core.bmr_io.check_sheet -->
```python
def check_sheet(src_xlsx: str, sheet_name: str) -> SheetCheck
```

Defined in `src/eidr_core/bmr_io/subset.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `src_xlsx` | `str` | required | Path of the BMR workbook to check. A missing file raises `FileNotFoundError`. |
| `sheet_name` | `str` | required | Data tab name exactly as `SHEET_TO_TEMPLATE` spells it (`"Episodics"`, `"Stand-Alone Works"`, ...). It selects the template; any other name raises `TemplateMismatch`. |

**Returns** `SheetCheck` -- the template key resolved from the tab name, the row-3 header map, the extra columns and the missing optional columns. Nothing is written.
<!-- /dict -->

**Does.** Checks, without writing, whether `subset_rows` or `fill_column` would accept a sheet, and reports its columns. Raises `TemplateMismatch` when the tab name is not a Template-22 data sheet, the workbook has no such tab, or a required column (see `required_headers`) is missing from row 3; raises `FileNotFoundError` for a missing file. Opens the file read-only and needs openpyxl (the `bmr` extra). It runs the same conformance function as `subset_rows` and `fill_column`, so a sheet that passes here passes their conformance check too; their own argument checks (an unknown `column` or `blank_columns` name) still apply.

### `count_family`

<!-- dict:eidr_core.bmr_io.count_family -->
```python
def count_family(headers: dict[int, str], primary: str) -> int
```

Defined in `src/eidr_core/bmr_io/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `headers` | `dict[int, str]` | required | Header map `{column: header text}`, as `read_headers` returns it. |
| `primary` | `str` | required | The family's primary column name without a number, e.g. `"Alternate Title"`. |

**Returns** `int` -- the highest group number present (a bare `primary` header counts as 1); 0 when the family is absent.
<!-- /dict -->

**Does.** Returns how many numbered groups of a column family a header map carries, as the highest group number. Gaps do not lower the count: headers `Alt ID 1` and `Alt ID 3` give 3. A header that starts with `primary` and a space but has a non-integer suffix (`Associated Org Role 1` for primary `Associated Org`) is ignored.

### `expand_family`

<!-- dict:eidr_core.bmr_io.expand_family -->
```python
def expand_family(ws, primary: str, anchor_members: list[str], insert_members: list[str], want: int, headers: dict[int, str]) -> None
```

Defined in `src/eidr_core/bmr_io/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `ws` | - | required | Open openpyxl worksheet (not read-only); modified in place. |
| `primary` | `str` | required | Family primary column; `count_family` on it gives the current group count. |
| `anchor_members` | `list[str]` | required | Every column group 1 carries, without numbers. New groups go after the rightmost column matching any of them. |
| `insert_members` | `list[str]` | required | Columns each new group adds, in order; each is written as `"{member} {n}"`. |
| `want` | `int` | required | Target group count. Nothing happens when it is not above the current count. |
| `headers` | `dict[int, str]` | required | Header map for `ws`; updated in place to match the inserted columns. |

**Returns** `None` -- the worksheet and `headers` are changed in place.
<!-- /dict -->

**Does.** Inserts columns so a family reaches `want` groups, writing the new header names on row 3. New groups of `len(insert_members)` columns are packed one after another, starting right after the rightmost anchor column. If no anchor column exists it logs a warning and returns without raising. The headers always go to `HEADER_ROW` (row 3), whatever row the sheet's real headers are on.

**Notes.** Prefer `write_sheet`, which sizes and expands every family from the rows and reports what grew. An incomplete `anchor_members` lands new groups too far left (see `Family`).

### `families_for`

<!-- dict:eidr_core.bmr_io.families_for -->
```python
def families_for(template: str, *, insert_members: Mapping[str, Sequence[str]] | None = None) -> list[Family]
```

Defined in `src/eidr_core/bmr_io/writer.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `template` | `str` | required | A `TEMPLATES` key: `"episodic"`, `"non_episodic"`, `"edit"`, `"clip"`, `"manifestation"` or `"compilation"`. Anything else raises `KeyError`. |
| `insert_members` | `Mapping[str, Sequence[str]] \| None` | `None` (keyword-only) | Per-family override of the columns each new group adds, keyed by family primary. Each value must be a subset of that family's anchor members and must include the primary. `None` means no overrides. |

**Returns** `list[Family]` -- the template's families in template order, overrides applied; a new list on every call.
<!-- /dict -->

**Does.** Returns one template's column families, optionally narrowing which columns new groups add. Raises `KeyError` for an unknown template key, and `ValueError` when an override names a family not on the template, names a column outside that family, or leaves out the primary column. Pass the result to `write_sheet(families=...)`; eidr-wikidata uses it to leave `Alt Title Class` and `Relation` out of groups 2 and up.

### `family_layout`

<!-- dict:eidr_core.bmr_io.family_layout -->
```python
def family_layout(header_names: Iterable[str], members: Sequence[str]) -> dict[int, dict[str, str]]
```

Defined in `src/eidr_core/bmr_io/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `header_names` | `Iterable[str]` | required | Header texts to scan, e.g. `headers.values()` or a row dict's keys. Compared exactly, not trimmed. |
| `members` | `Sequence[str]` | required | The family's column names without numbers, e.g. `["Alternate Title", "Alt Title Language", "Alt Title Class"]`. |

**Returns** `dict[int, dict[str, str]]` -- `{group number: {member: actual header text}}`. Groups with no matching header, and members missing from a group, are absent (sparse).
<!-- /dict -->

**Does.** Maps a repeating family's headers to `{group number: {member: header}}`, keeping the sheet's own group numbers. A bare member name counts as group 1; `"Member N"` (whitespace, then digits) is group N and wins over the bare form for group 1. Gaps are kept, so a blank group 1 cannot shift group 2's companion columns. Pair companions by group number first, and only then densify into a list if you need one.

### `fill_column`

<!-- dict:eidr_core.bmr_io.fill_column -->
```python
def fill_column(src_xlsx: str, dst_xlsx: str, sheet_name: str, column: str, values: Mapping[int, object]) -> FillReport
```

Defined in `src/eidr_core/bmr_io/subset.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `src_xlsx` | `str` | required | Path of the BMR workbook to copy. Must exist; never modified. |
| `dst_xlsx` | `str` | required | Output path. Overwritten by the copy; deleted if the call fails after copying (a refusal before the copy, such as an unknown tab name or a missing source, leaves an existing file alone). Must differ from `src_xlsx` (`shutil.SameFileError` otherwise). |
| `sheet_name` | `str` | required | Data tab name from `SHEET_TO_TEMPLATE`; selects the template for the conformance check. |
| `column` | `str` | required | Exact row-3 header of the column to fill, e.g. `"Assigned EIDR ID"`. A name not on the sheet raises `ValueError`. |
| `values` | `Mapping[int, object]` | required | `{absolute sheet row number: value}`, using the row numbers `open_sheet` yields. Values are written as given; `None` clears the cell. Use `int` keys. |

**Returns** `FillReport` -- rows filled, requested row numbers that are not data rows, and the conformance findings.
<!-- /dict -->

**Does.** Copies a BMR workbook and writes values into one column of one sheet, keyed by absolute sheet row number. Every row is kept and no other column is changed; this is not a subset. Raises `TemplateMismatch` (unknown tab name, tab missing, required column missing), `FileNotFoundError` (missing source) or `ValueError` (unknown column); any failure after the copy deletes `dst_xlsx`. Row numbers below `DATA_START` or past the sheet's last row are listed in `rows_absent` and not written.

**Notes.** The workbook is re-saved by openpyxl and `transplant` swaps in every worksheet of that save, so formula cells keep their formula text but lose their cached values until Excel re-saves the file (a `data_only=True` reader sees `None`). Keys of `values` are converted with `int()` for sorting but looked up as given, so a digit-string key such as `"5"` raises `KeyError` once it falls on a data row (a non-numeric string raises `ValueError`); pass `int` keys.

### `fix_shared_strings`

<!-- dict:eidr_core.bmr_io.fix_shared_strings -->
```python
def fix_shared_strings(xlsx_path: str) -> None
```

Defined in `src/eidr_core/bmr_io/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `xlsx_path` | `str` | required | Path of the `.xlsx` to rewrite in place. |

**Returns** `None` -- the file is rewritten in place, or left untouched when no worksheet has an inline-string cell.
<!-- /dict -->

**Does.** Converts inline-string cells in every worksheet of an `.xlsx` to shared-string references, rewriting the file in place. The EPPlus-based BMR tool needs shared strings. Existing shared strings keep their indices but are re-emitted as plain text (rich-text runs are flattened), and the `[Content_Types].xml` entry for the shared-strings part is added if missing. Writes to a temp file in the same directory, then replaces the original.

**Notes.** If an existing `xl/sharedStrings.xml` fails to parse, the error is swallowed and the table is rebuilt from the inline strings alone, which leaves pre-existing shared-string cells pointing at the wrong entries. When the file has no `xl/sharedStrings.xml` (an openpyxl save writes none; 18 of the 462 readable workbooks under `D:\BMR` had none on 2026-10-02), the part it creates gets a `[Content_Types].xml` entry but no relationship in `xl/_rels/workbook.xml.rels`. `write_sheet`, `subset_rows` and `fill_column` already call this; call it yourself only after your own openpyxl save plus `transplant`.

### `header_map`

<!-- dict:eidr_core.bmr_io.header_map -->
```python
def header_map(values: Iterable) -> dict[int, str]
```

Defined in `src/eidr_core/bmr_io/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `values` | `Iterable` | required | The cell values of one row, left to right, e.g. a tuple from `iter_rows(values_only=True)`. Non-string values are converted with `str()`. |

**Returns** `dict[int, str]` -- `{1-based integer column: trimmed header text}`; `None`, empty and whitespace-only cells are left out.
<!-- /dict -->

**Does.** Applies the shared header-row policy to a plain row of values, returning `{1-based column: trimmed header}`. A blank cell is skipped without ending the scan, and the columns after it keep their true indices. Keys are integers, never column letters, so `[m[c] for c in sorted(m)]` gives sheet order even past column Z. Use it when you located the header row yourself; BMR-Review finds it by searching for `Unique Row ID`.

**Notes.** Two cells with the same text keep separate keys; if you invert the map to `{name: column}`, the rightmost one wins.

### `index_rows`

<!-- dict:eidr_core.bmr_io.index_rows -->
```python
def index_rows(rows: Iterable[Mapping[str, Any]], row_id_column: str = ROW_ID_COLUMN) -> dict[str, Mapping[str, Any]]
```

Defined in `src/eidr_core/bmr_io/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `rows` | `Iterable[Mapping[str, Any]]` | required | Row mappings `{header: value}`, as `read_sheet` or `open_sheet` yield them. |
| `row_id_column` | `str` | `ROW_ID_COLUMN` | Header that holds each row's own ID; default `"Unique Row ID"`. |

**Returns** `dict[str, Mapping[str, Any]]` -- `{trimmed, casefolded Row ID: row mapping}`. Rows with no Row ID are left out; the mappings are the originals, not copies.
<!-- /dict -->

**Does.** Indexes sheet rows by Row ID so `resolve_parent` and `parent_chain` can look parents up. Keys are `str(value).strip().casefold()`, so a reference `"s0007"` finds row `"S0007"`. A duplicate Row ID keeps the first row, so a later row cannot capture children that already point at the earlier one.

**Notes.** Always build the index with this function: `resolve_parent` looks up the casefolded reference, so an index keyed by the original text misses every Row ID that has an uppercase letter (such as `S0007`) or surrounding spaces.

### `max_counts`

<!-- dict:eidr_core.bmr_io.max_counts -->
```python
def max_counts(rows: Iterable[Mapping[str, Any]], families: Sequence[Family]) -> dict[str, int]
```

Defined in `src/eidr_core/bmr_io/writer.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `rows` | `Iterable[Mapping[str, Any]]` | required | Mapped rows `{column name: value}` whose family columns are already numbered (`"Domain 4"`). |
| `families` | `Sequence[Family]` | required | Families to count, e.g. from `families_for`. A column counts toward a family when its member name is in that family's `anchor_members`. |

**Returns** `dict[str, int]` -- `{family primary: highest group number holding a non-empty value}`; families with no such value are absent.
<!-- /dict -->

**Does.** Returns the highest group number each family needs across mapped rows, keyed by family primary. Any member column counts: `"Domain 4"` alone means four `Alt ID` groups. `None` and `""` values are ignored (a whitespace-only string counts), and only `"<member> <digits>"` names with a single space count; a bare member name does not.

**Notes.** `write_sheet` calls this itself; you need it only to plan a layout without writing.

### `open_sheet`

<!-- dict:eidr_core.bmr_io.open_sheet -->
```python
def open_sheet(path: str, sheet_name: str, *, header_row: int = HEADER_ROW, data_start: int = DATA_START, stop: str | None = None) -> Iterator[tuple[dict[int, str], Iterator[tuple[int, dict[str, object]]]]]
```

Defined in `src/eidr_core/bmr_io/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `path` | `str` | required | Path of the `.xlsx` to read. openpyxl's own error propagates for a missing or unreadable file. |
| `sheet_name` | `str` | required | Exact tab name. A missing tab raises `ValueError` listing the tabs found. |
| `header_row` | `int` | `HEADER_ROW` (keyword-only) | 1-based row holding the headers. Pass the discovered row for a sheet whose headers moved off row 3. |
| `data_start` | `int` | `DATA_START` (keyword-only) | 1-based first data row. |
| `stop` | `str \| None` | `None` (keyword-only) | End-of-data rule. `None`: read to the end, skipping blank rows. `"blank_first_col"`: stop at the first row whose column A is empty or whitespace. `"blank_row"`: stop at the first row with no value under any header. Anything else raises `ValueError` before the file is opened. |

**Returns** `Iterator[tuple[dict[int, str], Iterator[tuple[int, dict[str, object]]]]]` -- a context manager yielding `(headers, rows)`. `headers` is `{1-based column: header}`; `rows` lazily yields `(absolute sheet row number, {header: value})` and works only inside the `with` block.
<!-- /dict -->

**Does.** Opens one BMR sheet for streaming reads, yielding the header map and a lazy iterator of numbered row dicts. Use it as `with open_sheet(path, tab) as (headers, rows):`; leaving the block closes the workbook, which on Windows releases the file lock that would otherwise block Excel. The file is opened read-only with `data_only=True`, so a formula cell gives its cached value (`None` if never calculated). Values are raw and untrimmed (str, int, float, datetime, ...); empty cells, `""` values and columns without a header are absent from each dict.

**Notes.** Row numbers jump over blank rows that `stop=None` skipped. Keep them: they are what `subset_rows` and `fill_column` take, and what an operator sees in Excel. Needs openpyxl (the `bmr` extra); importing `eidr_core.bmr_io` does not.

### `pad_groups`

<!-- dict:eidr_core.bmr_io.pad_groups -->
```python
def pad_groups(items: Sequence, count: int, width: int, fill: str = "") -> list
```

Defined in `src/eidr_core/bmr_io/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `items` | `Sequence` | required | One record's groups for one family: each a tuple or list of `width` cells, or a single value when `width` is 1. |
| `count` | `int` | required | Number of groups to emit, usually `RepeatPlan.get(family)`. |
| `width` | `int` | required | Cells per group. |
| `fill` | `str` | `""` | Value put in every cell of a missing group. |

**Returns** `list` -- a flat list of exactly `count * width` cells.
<!-- /dict -->

**Does.** Flattens one family's values to exactly `count` groups of `width` cells, padding missing groups with `fill`. Raises `ValueError` when a tuple or list item has the wrong number of cells, or when a single value is given with `width` other than 1. Items beyond `count` are dropped without warning, so size `count` with `RepeatPlan` over the same records first.

### `parent_chain`

<!-- dict:eidr_core.bmr_io.parent_chain -->
```python
def parent_chain(row: Mapping[str, Any], index: Mapping[str, Mapping[str, Any]], *, parent_column: str = PARENT_COLUMN, assigned_id_column: str = ASSIGNED_ID_COLUMN, row_id_column: str = ROW_ID_COLUMN, max_depth: int = 16) -> list[ParentRef]
```

Defined in `src/eidr_core/bmr_io/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `row` | `Mapping[str, Any]` | required | The child row mapping whose ancestry to walk. |
| `index` | `Mapping[str, Mapping[str, Any]]` | required | Row index built by `index_rows` over the same sheet. |
| `parent_column` | `str` | `PARENT_COLUMN` (keyword-only) | Header of the parent reference cell. |
| `assigned_id_column` | `str` | `ASSIGNED_ID_COLUMN` (keyword-only) | Header holding each row's registered EIDR ID. |
| `row_id_column` | `str` | `ROW_ID_COLUMN` (keyword-only) | Header of the starting row's own ID; used only to seed cycle detection. |
| `max_depth` | `int` | `16` (keyword-only) | Most parent links followed; at this limit the walk ends quietly with what it has. |

**Returns** `list[ParentRef]` -- one ref per step, nearest parent first; empty when the row's parent cell is blank.
<!-- /dict -->

**Does.** Walks a row's parent references within the sheet, nearest parent first, returning one `ParentRef` per step. The walk goes on through in-sheet parent rows, including ones that already have an Assigned EIDR ID. It stops after the first ref that names no row (the cell held an EIDR ID, or the reference is unresolved), at a blank parent cell, at a cycle, or after `max_depth` steps. On a cycle, the ref that closes the loop is included as the last element.

**Notes.** To stop at the nearest buildable ancestor, test `bool(ref)` on each element yourself.

### `read_headers`

<!-- dict:eidr_core.bmr_io.read_headers -->
```python
def read_headers(ws, header_row: int = HEADER_ROW) -> dict[int, str]
```

Defined in `src/eidr_core/bmr_io/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `ws` | - | required | Open openpyxl worksheet. A normal (not read-only) worksheet is best: this reads cells one by one, which is slow in read-only mode. |
| `header_row` | `int` | `HEADER_ROW` | 1-based row holding the headers; pass the discovered row for a round-tripped sheet. |

**Returns** `dict[int, str]` -- `{1-based integer column: trimmed header}`, blank cells skipped (the `header_map` policy).
<!-- /dict -->

**Does.** Returns the header map `{1-based column: header}` of an open worksheet, using the shared `header_map` policy. It scans columns 1 to `ws.max_column` of `header_row`. For a file path rather than an open worksheet, use `open_sheet` or `read_sheet`.

### `read_sheet`

<!-- dict:eidr_core.bmr_io.read_sheet -->
```python
def read_sheet(path: str, sheet_name: str, *, header_row: int = HEADER_ROW, data_start: int = DATA_START, stop: str | None = None) -> tuple[dict[int, str], list[dict[str, object]]]
```

Defined in `src/eidr_core/bmr_io/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `path` | `str` | required | Path of the `.xlsx` to read. |
| `sheet_name` | `str` | required | Exact tab name; a missing tab raises `ValueError`. |
| `header_row` | `int` | `HEADER_ROW` (keyword-only) | 1-based header row, as in `open_sheet`. |
| `data_start` | `int` | `DATA_START` (keyword-only) | 1-based first data row. |
| `stop` | `str \| None` | `None` (keyword-only) | End-of-data rule: `None`, `"blank_first_col"` or `"blank_row"`, exactly as in `open_sheet`. |

**Returns** `tuple[dict[int, str], list[dict[str, object]]]` -- `(headers, rows)`: `headers` as in `open_sheet`; `rows` is a list of `{header: value}` dicts, one per data row, without row numbers.
<!-- /dict -->

**Does.** Reads one BMR sheet fully into memory as a header map plus one `{header: value}` dict per data row. It is a `list()` over `open_sheet`, so the header policy, value handling and stop rules are identical. Row numbers are not returned; use `open_sheet` when you need them or when the sheet is large (a 60k-row, 500-column sheet is multi-GB here).

### `resolve_parent`

<!-- dict:eidr_core.bmr_io.resolve_parent -->
```python
def resolve_parent(row: Mapping[str, Any], index: Mapping[str, Mapping[str, Any]], *, parent_column: str = PARENT_COLUMN, assigned_id_column: str = ASSIGNED_ID_COLUMN) -> ParentRef
```

Defined in `src/eidr_core/bmr_io/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `row` | `Mapping[str, Any]` | required | The child row mapping `{header: value}`. |
| `index` | `Mapping[str, Mapping[str, Any]]` | required | Row index built by `index_rows` (casefolded keys). |
| `parent_column` | `str` | `PARENT_COLUMN` (keyword-only) | Header of the parent reference cell; default `"Parent EIDR/Row ID"`. |
| `assigned_id_column` | `str` | `ASSIGNED_ID_COLUMN` (keyword-only) | Header holding the parent row's registered ID; default `"Assigned EIDR ID"`. |

**Returns** `ParentRef` -- resolved (`eidr_id` set), deferred (`row` set, no `eidr_id`), unresolved (`unresolved` True), or an empty `ParentRef()` when the parent cell is blank.
<!-- /dict -->

**Does.** Resolves one child row's `Parent EIDR/Row ID` cell, which holds an EIDR ID or a Row ID, into a `ParentRef`. A checksum-valid EIDR Content ID (`eidr_core.ids.is_valid_eidr_id`) is used as written; anything else is looked up in `index` as a Row ID. A found row supplies its `Assigned EIDR ID` only when that is a valid ID, so a sentinel such as `NO MATCH` gives a deferred ref. A mistyped ID with a bad check character is looked up as a Row ID and normally comes back unresolved, rather than passing downstream as a parent that cannot exist.

**Notes.** Only `bool(ref)` (an EIDR ID was found) licenses building a full record (operator ruling 2026-09-03). Never drop or rewrite the parent cell of a deferred or unresolved row; a later pass resolves it.

### `rightmost_in`

<!-- dict:eidr_core.bmr_io.rightmost_in -->
```python
def rightmost_in(headers: dict[int, str], members: list[str]) -> int | None
```

Defined in `src/eidr_core/bmr_io/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `headers` | `dict[int, str]` | required | Header map `{column: header text}`. |
| `members` | `list[str]` | required | Family member names without numbers. |

**Returns** `int | None` -- the highest column whose header equals a member, or starts with a member followed by a space; `None` when nothing matches.
<!-- /dict -->

**Does.** Returns the rightmost column whose header is a family member name, bare or followed by a space. Matching is by prefix, not by number, so member `"Associated Org"` also matches `"Associated Org Role 1"`. `expand_family` uses it to decide where new groups go.

### `subset_rows`

<!-- dict:eidr_core.bmr_io.subset_rows -->
```python
def subset_rows(src_xlsx: str, dst_xlsx: str, sheet_name: str, keep_rows: Iterable[int], *, blank_columns: Sequence[str] = ()) -> SubsetReport
```

Defined in `src/eidr_core/bmr_io/subset.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `src_xlsx` | `str` | required | BMR workbook to copy rows from. Must exist; never modified. |
| `dst_xlsx` | `str` | required | Output path. Overwritten by the copy; deleted if the call fails after copying (a refusal before the copy, such as an unknown tab name, a header-row number or a missing source, leaves an existing file alone). Must differ from `src_xlsx` (`shutil.SameFileError` otherwise). |
| `sheet_name` | `str` | required | Data tab name from `SHEET_TO_TEMPLATE`; it selects the template (there is no `template=` parameter). |
| `keep_rows` | `Iterable[int]` | required | Absolute sheet row numbers to keep, as `open_sheet` yields them. Order and duplicates do not matter; a number below `DATA_START` raises `ValueError`. |
| `blank_columns` | `Sequence[str]` | `()` (keyword-only) | Header names whose values are cleared in the kept rows, e.g. `("Assigned EIDR ID", "Registration Errors & Notes")` for a fresh BMR-Review assessment. A name not on the sheet raises `ValueError`. |

**Returns** `SubsetReport` -- rows kept, requested rows past the end of the sheet, per-column blank counts, and the conformance findings.
<!-- /dict -->

**Does.** Copies a BMR workbook, keeping the header rows and only the chosen data rows of one sheet, in source order. Kept rows are written values-only into the same columns, packed from `DATA_START`, and the rows after them are deleted so the sheet's size matches the subset. Raises `TemplateMismatch` (unknown tab name, tab missing, required column missing), `ValueError` (header-row numbers, unknown `blank_columns`) or `FileNotFoundError`; any failure after the copy deletes `dst_xlsx`. Requested rows past the source's last row go to `rows_missing` instead of raising.

**Notes.** Cell formatting does not travel with a moved row, and a kept row that is blank in the source is a blank row in the output. The workbook is re-saved by openpyxl and transplanted, so formula cells keep their text but lose their cached values until Excel re-saves the file. A formula in a moved row keeps its text verbatim, so its relative references are not adjusted (`=A6` moved from row 6 to row 4 still reads `A6`). Copy, do not construct: this is the sanctioned way to pass BMR rows on.

### `template_for_creation_type`

<!-- dict:eidr_core.bmr_io.template_for_creation_type -->
```python
def template_for_creation_type(creation_type: str) -> str | None
```

Defined in `src/eidr_core/bmr_io/writer.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `creation_type` | `str` | required | An EIDR creation type such as `"Episode"`, or the schema spelling `"CreateEpisode"`. Surrounding whitespace is ignored; matching is case-sensitive. |

**Returns** `str | None` -- the `TEMPLATES` key for that type, or `None` for `Interactive` and `Composite`, which have no Template-22 sheet.
<!-- /dict -->

**Does.** Returns the Template-22 template key a creation type routes to, from the one shared routing table. Basic goes to `non_episodic`; Series, Season and Episode to `episodic`; Edit, Clip, Manifestation and Compilation each to their own template. Anything that is not a creation type raises `ValueError`, including `None`, `""`, a lowercase name and a referent type such as `"Movie"`, so a mis-sourced type cannot silently land in the "no template" bucket.

### `transplant`

<!-- dict:eidr_core.bmr_io.transplant -->
```python
def transplant(template_xlsx: str, edited_xlsx: str) -> None
```

Defined in `src/eidr_core/bmr_io/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `template_xlsx` | `str` | required | The container to keep, OVERWRITTEN in place. Pass a copy of the template or source workbook, never the original. |
| `edited_xlsx` | `str` | required | The openpyxl-saved file whose worksheet XML (and shared strings, if it has them) replaces the container's. Not modified. |

**Returns** `None` -- `template_xlsx` is rewritten in place.
<!-- /dict -->

**Does.** Replaces the worksheet XML and shared strings in one `.xlsx` with another file's, keeping all its other parts. Workbook structure, styles, macros and relationships all come from `template_xlsx`, which is how they survive an openpyxl save. Worksheet parts are paired by part path (`xl/worksheets/sheetN.xml`), not by tab name, and a worksheet present in only one file is not exchanged. Writes to a temp file in the same directory, then replaces `template_xlsx`.

**Notes.** Pairing by part path assumes both files number their worksheet parts the same way. openpyxl numbers them in tab order, so a source whose parts are numbered otherwise would get each tab's content under the wrong tab (reproduced with a constructed file; on 2026-10-02 the shipped templates and all 462 readable workbooks under `D:\BMR` were in tab order). `write_sheet`, `subset_rows` and `fill_column` already call it.

### `write_sheet`

<!-- dict:eidr_core.bmr_io.write_sheet -->
```python
def write_sheet(template_path: str, sheet_name: str, rows: Iterable[Mapping[str, Any]], out_path: str, *, families: Sequence[Family] | None = None, caps: Mapping[str, int | None] | None = None, extra_columns: Sequence[str] = (), strict: bool = False) -> WriteReport
```

Defined in `src/eidr_core/bmr_io/writer.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `template_path` | `str` | required | Path of the Template-22 `.xlsx` to start from (eidr-core does not ship these files). Never modified; a missing file raises `FileNotFoundError`. |
| `sheet_name` | `str` | required | Data tab to write, e.g. `"Episodics"`. Must exist in the template (`ValueError`); with `families=None` it must also be a `SHEET_TO_TEMPLATE` key. |
| `rows` | `Iterable[Mapping[str, Any]]` | required | Rows already mapped to `{exact header text: value}`, family members already numbered (`"Alternate Title 2"`). Read once; written from `DATA_START` in order. |
| `out_path` | `str` | required | Output path; overwritten if it exists. |
| `families` | `Sequence[Family] \| None` | `None` (keyword-only) | Families to expand. `None` uses the sheet's own from `TEMPLATES`; pass `families_for(key, insert_members=...)` to apply your own policy. |
| `caps` | `Mapping[str, int \| None] \| None` | `None` (keyword-only) | Your expansion ceilings, keyed by family primary, each at or below `SCHEMA_MAX`. A key not in `SCHEMA_MAX`, a cap above it, or `None` for a bounded family raises `ValueError`. `None` means the schema maxima. |
| `extra_columns` | `Sequence[str]` | `()` (keyword-only) | Header names appended after the template's last column, following one blank separator column; their values come from the rows under the same names. A name already on the sheet raises `ValueError`. |
| `strict` | `bool` | `False` (keyword-only) | `True` raises `ValueError` when any non-empty value has no column on the sheet; `False` counts it in `WriteReport.dropped`. |

**Returns** `WriteReport` -- rows written, families expanded, families capped, and values dropped for lack of a column.
<!-- /dict -->

**Does.** Writes mapped rows onto a copy of one Template-22 sheet, expanding column families, and reports what it could not place. The sequence: copy the template, expand each family to the highest group any row uses (up to its cap), append `extra_columns`, clear every row from `DATA_START` down, write each value by header name, save, `transplant` into the copy, then `fix_shared_strings`. `None` and `""` values leave the cell blank. Needs openpyxl (the `bmr` extra).

**Notes.** A refusal after the copy (missing tab, duplicate extra column, `strict=True`) leaves `out_path` behind as an unmodified copy of the template; unlike `subset_rows`, it does not delete it. Caps limit expansion only: a value in a group the template already ships is written even when that group is above your cap (it shows in `capped`, not in `dropped`). Decide what each row says, and which template it goes to, in your own mapper.

### `Family` (class)

<!-- dict:eidr_core.bmr_io.Family -->
```python
class Family(NamedTuple)
```

Defined in `src/eidr_core/bmr_io/writer.py`.

| Field | Type | Default | Purpose |
|---|---|---|---|
| `primary` | `str` | required | Column whose numbered copies `count_family` counts; also the key for `SCHEMA_MAX`, `caps=` and `max_counts`. |
| `anchor_members` | `tuple[str, ...]` | required | Every column group 1 carries, without numbers. Finds the insertion point, and tells `max_counts` which columns belong to the family. Must be complete. |
| `insert_members` | `tuple[str, ...]` | required | Columns each new group adds. Equal to `anchor_members` in the shipped families; `families_for` lets you narrow it but requires it to keep `primary`. |
<!-- /dict -->

**Does.** Describes one repeating column family on a Template-22 sheet: its primary, group-1 and new-group columns. Take families from `TEMPLATES[key].families` or `families_for` rather than building them by hand. An incomplete `anchor_members` makes new groups land too far left and pushes the missing column rightward (eidr-wikidata, 2026-05-09).

### `FillReport` (class)

<!-- dict:eidr_core.bmr_io.FillReport -->
```python
@dataclass
class FillReport
```

Defined in `src/eidr_core/bmr_io/subset.py`.

| Field | Type | Default | Purpose |
|---|---|---|---|
| `path` | `str` | required | The output file written (`dst_xlsx`). |
| `template` | `str` | required | `TEMPLATES` key resolved from the tab name. |
| `sheet` | `str` | required | The tab that was filled. |
| `rows_filled` | `int` | required | Number of `values` entries written. |
| `rows_absent` | `list[int]` | `field(default_factory=list)` | Requested row numbers below `DATA_START` or past the sheet's last row, ascending; not written. |
| `extra_columns` | `list[str]` | `field(default_factory=list)` | Sheet headers not on the shipped template, in sheet order; left as they are. |
| `missing_optional` | `list[str]` | `field(default_factory=list)` | Shipped optional headers the sheet lacks, in template order; reported, not refused. |
<!-- /dict -->

**Does.** Reports what `fill_column` wrote and what it found about the sheet's columns. It is returned only on success; a refusal or failure raises instead.

### `ParentRef` (class)

<!-- dict:eidr_core.bmr_io.ParentRef -->
```python
@dataclass(frozen=True)
class ParentRef
```

Defined in `src/eidr_core/bmr_io/__init__.py`.

| Field | Type | Default | Purpose |
|---|---|---|---|
| `raw` | `str` | `""` | The parent cell as written, trimmed; `""` when the cell was blank. Keep it for diagnostics and later passes. |
| `eidr_id` | `str \| None` | `None` | The parent's EIDR ID: the cell itself when it is a valid ID, otherwise the referenced row's valid `Assigned EIDR ID`; `None` when there is neither. |
| `row` | `Mapping[str, Any] \| None` | `None` | The parent's row mapping when the cell named a row found in the index; `None` otherwise. |
| `unresolved` | `bool` | `False` | True when the cell is not a valid EIDR ID and names no row in the index. |

| Method | Signature | Purpose |
|---|---|---|
| `deferred` | `def deferred() -> bool` (property) | True when `row` is set but there is no `eidr_id`: the parent is in the sheet but not registered yet. Keep the parent cell verbatim and retry on a later pass. |
<!-- /dict -->

**Does.** Holds the outcome of resolving one `Parent EIDR/Row ID` cell; `bool(ref)` is True only when an EIDR ID was found. That is the single case that licenses building a full record (operator ruling 2026-09-03). A deferred ref (`ref.deferred`) is not an error but is not buildable either; an unresolved ref is a broken reference; an empty `ParentRef()` (`raw == ""`) means the row has no parent.

**Notes.** eidr-core 0.23.0 made a deferred ref truthy and told callers to build from the in-sheet row; that guidance was withdrawn. Read `if ref:` as "may I build?", not "did I find anything?".

### `RepeatPlan` (class)

<!-- dict:eidr_core.bmr_io.RepeatPlan -->
```python
class RepeatPlan
```

Defined in `src/eidr_core/bmr_io/__init__.py`.

| Method | Signature | Purpose |
|---|---|---|
| `__init__` | `def __init__(minimums: Mapping[str, int] \| None = None)` | Creates an empty plan. `minimums`: per-family floors that `finalize` applies, e.g. `{"Director": 2, "Actor": 4}`; `None` means none. The mapping is copied. |
| `bump` | `def bump(family: str, n: int \| None) -> None` | Records that one record needs `n` groups of `family`, keeping the largest seen. `n` is converted with `int()`; `None` is ignored. |
| `finalize` | `def finalize() -> None` | Applies `minimums` (adding families that were never bumped) and raises every recorded family to at least 1. Call once after the last `bump`; calling again changes nothing. |
| `get` | `def get(family: str, default: int = 1) -> int` | Returns the group count for `family`, never below 1. `default`: used when the family was never recorded. Minimums count only after `finalize`. |
<!-- /dict -->

**Does.** Accumulates union-max repeat-group counts across a set of records, with optional per-family minimums. Use it to size a wide layout so every record fits, then emit each record with `pad_groups(items, plan.get(family), width)`. The counts are in the public `counts` dict and the floors in `minimums`.

### `SheetCheck` (class)

<!-- dict:eidr_core.bmr_io.SheetCheck -->
```python
@dataclass
class SheetCheck
```

Defined in `src/eidr_core/bmr_io/subset.py`.

| Field | Type | Default | Purpose |
|---|---|---|---|
| `template` | `str` | required | `TEMPLATES` key resolved from the tab name. |
| `sheet` | `str` | required | The tab that was checked. |
| `headers` | `dict[int, str]` | required | Row-3 header map `{1-based column: header}`, by the `header_map` policy. |
| `extra_columns` | `list[str]` | `field(default_factory=list)` | Headers not on the shipped template, in sheet order. |
| `missing_optional` | `list[str]` | `field(default_factory=list)` | Shipped optional headers the sheet lacks, in template order. |
<!-- /dict -->

**Does.** Reports what `check_sheet` learned about a sheet's columns, without anything being written. It is returned only when the sheet conforms; a non-conforming sheet raises `TemplateMismatch` instead.

### `SubsetReport` (class)

<!-- dict:eidr_core.bmr_io.SubsetReport -->
```python
@dataclass
class SubsetReport
```

Defined in `src/eidr_core/bmr_io/subset.py`.

| Field | Type | Default | Purpose |
|---|---|---|---|
| `path` | `str` | required | The output file written (`dst_xlsx`). |
| `template` | `str` | required | `TEMPLATES` key resolved from the tab name. |
| `sheet` | `str` | required | The tab that was subset. |
| `rows_kept` | `int` | required | Number of data rows written to the output. |
| `rows_missing` | `list[int]` | `field(default_factory=list)` | Requested row numbers past the source sheet's last row, ascending; skipped, not an error. |
| `blanked` | `dict[str, int]` | `field(default_factory=dict)` | `{column: number of non-empty values cleared}` for each `blank_columns` name, zeros included. |
| `extra_columns` | `list[str]` | `field(default_factory=list)` | Source headers not on the shipped template, in sheet order; copied as they are. |
| `missing_optional` | `list[str]` | `field(default_factory=list)` | Shipped optional headers the source lacks, in template order; reported, not refused. |
<!-- /dict -->

**Does.** Reports what `subset_rows` wrote and what it found about the sheet's columns. It is returned only on success; a refused or failed subset raises, and any copy it had already made is deleted.

### `Template` (class)

<!-- dict:eidr_core.bmr_io.Template -->
```python
class Template(NamedTuple)
```

Defined in `src/eidr_core/bmr_io/writer.py`.

| Field | Type | Default | Purpose |
|---|---|---|---|
| `key` | `str` | required | The `TEMPLATES` key, e.g. `"episodic"`. |
| `filename` | `str` | required | File name of the shipped workbook, e.g. `"EIDR_Episodic_Template-22.xlsx"`. eidr-core does not ship the file; consumers keep their own copy. |
| `sheet` | `str` | required | Data tab name, e.g. `"Episodics"`. |
| `families` | `tuple[Family, ...]` | required | Column families in template left-to-right order. |
| `headers` | `tuple[str, ...]` | `()` | The data sheet's row-3 headers as shipped, in order. Empty only for a caller-built `Template`. |
<!-- /dict -->

**Does.** Describes one Template-22 content workbook: key, file name, data tab, column families and shipped header row. Read these from `TEMPLATES` instead of hard-coding tab names or header lists. `headers` is the reference for `check_sheet`, `subset_rows` and `fill_column`: only the subset that `required_headers` returns must be present (exact text); other shipped columns may be missing (reported), and extra columns and expanded families are allowed.

### `TemplateMismatch` (class)

<!-- dict:eidr_core.bmr_io.TemplateMismatch -->
```python
class TemplateMismatch(ValueError)
```

Defined in `src/eidr_core/bmr_io/subset.py`.
<!-- /dict -->

**Does.** Signals that a sheet is not, or is no longer, a conforming Template-22 data sheet. `check_sheet`, `subset_rows` and `fill_column` raise it for an unknown tab name, a tab missing from the workbook, or missing required columns. It subclasses `ValueError`, so catch it first if you also catch `ValueError`. `write_sheet` raises a plain `ValueError` for an unknown tab instead.

### `WriteReport` (class)

<!-- dict:eidr_core.bmr_io.WriteReport -->
```python
@dataclass
class WriteReport
```

Defined in `src/eidr_core/bmr_io/writer.py`.

| Field | Type | Default | Purpose |
|---|---|---|---|
| `path` | `str` | required | The output file written (`out_path`). |
| `rows` | `int` | required | Number of rows written, including rows whose values were all empty. |
| `expanded` | `dict[str, int]` | `field(default_factory=dict)` | `{family primary: group count now on the sheet}` for each family that grew. |
| `capped` | `dict[str, int]` | `field(default_factory=dict)` | `{family primary: groups the rows asked for}` where that exceeded the effective cap. |
| `dropped` | `dict[str, int]` | `field(default_factory=dict)` | `{column name: number of non-empty values that had no column on the sheet}`. |
<!-- /dict -->

**Does.** Reports what `write_sheet` did, including what it could not place. Check `dropped` after every write: with `strict=False`, a value whose column is not on the sheet is skipped and only counted here (and in a log line).

### `ASSIGNED_ID_COLUMN` (constant)

<!-- dict:eidr_core.bmr_io.ASSIGNED_ID_COLUMN -->
Defined in `src/eidr_core/bmr_io/__init__.py`.

**Value** `ASSIGNED_ID_COLUMN = "Assigned EIDR ID"` -- Header of the column holding a row's registered EIDR ID. `resolve_parent` reads the parent row's ID from it; non-ID text such as `NO MATCH` or `Candidates Found` counts as no ID.
<!-- /dict -->

### `CREATION_TYPES` (constant)

<!-- dict:eidr_core.bmr_io.CREATION_TYPES -->
Defined in `src/eidr_core/bmr_io/writer.py`.

**Value** `CREATION_TYPES: frozenset[str] = frozenset({ "Basic", "Series", "Season", "Episode", "Edit", "Clip", "Manifestation", "C...` -- The schema's ten creation types without the `Create` prefix: Basic, Series, Season, Episode, Edit, Clip, Manifestation, Compilation, Interactive, Composite. These (or `Create` plus one) are what `template_for_creation_type` accepts; Interactive and Composite have no template.
<!-- /dict -->

### `DATA_START` (constant)

<!-- dict:eidr_core.bmr_io.DATA_START -->
Defined in `src/eidr_core/bmr_io/__init__.py`.

**Value** `DATA_START = 4` -- 1-based first data row of every Template-22 sheet (rows 1-2 are the banner, row 3 the headers).
<!-- /dict -->

### `HEADER_ROW` (constant)

<!-- dict:eidr_core.bmr_io.HEADER_ROW -->
Defined in `src/eidr_core/bmr_io/__init__.py`.

**Value** `HEADER_ROW = 3` -- 1-based row carrying the column headers on every Template-22 sheet. A sheet round-tripped through review may have moved it; the readers take `header_row=` for that.
<!-- /dict -->

### `PARENT_COLUMN` (constant)

<!-- dict:eidr_core.bmr_io.PARENT_COLUMN -->
Defined in `src/eidr_core/bmr_io/__init__.py`.

**Value** `PARENT_COLUMN = "Parent EIDR/Row ID"` -- Header of the parent reference column, which holds EITHER the parent's EIDR ID or the parent row's `Unique Row ID`. Resolve it with `resolve_parent`; never treat it as an EIDR ID alone.
<!-- /dict -->

### `ROW_ID_COLUMN` (constant)

<!-- dict:eidr_core.bmr_io.ROW_ID_COLUMN -->
Defined in `src/eidr_core/bmr_io/__init__.py`.

**Value** `ROW_ID_COLUMN = "Unique Row ID"` -- Header of each row's own ID, the key `index_rows` indexes on and the column parent references name.
<!-- /dict -->

### `SCHEMA_MAX` (constant)

<!-- dict:eidr_core.bmr_io.SCHEMA_MAX -->
Defined in `src/eidr_core/bmr_io/writer.py`.

**Value** `SCHEMA_MAX: dict[str, int \| None] = { "Original Language": 32, "Alternate Title": 128, "Country of Origin": 32, "Associated...` -- Registry maximum group count per family, from the schema's `maxOccurs` (`common.xsd`; Alternate No. from the md-v2.8 SequenceInfo), keyed by family primary; `None` means unbounded. Original Language 32, Alternate Title 128, Country of Origin 32, Associated Org 16, Alt ID unbounded, Director 2, Actor 4, Season Class unbounded, Episode Class unbounded, Edit Class 8, Made for Region 8, Edit Details 8, Version Language 64, Manif Class 8, Manif Details 8, Metadata Authority 4, Alternate No. unbounded. These are `write_sheet`'s default caps, and `caps=` may only lower them. Director and Actor are facts for mappers, not expandable families.
<!-- /dict -->

### `SHEET_TO_TEMPLATE` (constant)

<!-- dict:eidr_core.bmr_io.SHEET_TO_TEMPLATE -->
Defined in `src/eidr_core/bmr_io/writer.py`.

**Value** `SHEET_TO_TEMPLATE: dict[str, str] = {t.sheet: k for k, t in TEMPLATES.items()}` -- Data tab name to `TEMPLATES` key: `"Episodics"` to `episodic`, `"Stand-Alone Works"` to `non_episodic`, `"Edits"` to `edit`, `"Clips"` to `clip`, `"Manifestations"` to `manifestation`, `"Compilations"` to `compilation`. A tab not listed is not a Template-22 data sheet.
<!-- /dict -->

### `TEMPLATES` (constant)

<!-- dict:eidr_core.bmr_io.TEMPLATES -->
Defined in `src/eidr_core/bmr_io/writer.py`.

**Value** `TEMPLATES: dict[str, Template] = { "episodic": Template( "episodic", "EIDR_Episodic_Template-22.xlsx", "Episodics", (_OR...` -- The six Template-22 content templates as `Template` values, keyed `episodic`, `non_episodic`, `edit`, `clip`, `manifestation` and `compilation`. The Service template is deliberately absent. Treat it as read-only; `SHEET_TO_TEMPLATE` is computed from it once at import.
<!-- /dict -->

## `eidr_core.bmr_io.subset`

<!-- dict-module:eidr_core.bmr_io.subset -->
Source `src/eidr_core/bmr_io/subset.py`. Public names: 1 function (declared by `__all__`).
<!-- /dict-module -->

**Purpose.** The submodule behind `subset_rows`, `check_sheet` and `fill_column` (all re-exported from `eidr_core.bmr_io` and documented there), and the home of the Template-22 conformance rules. It was added 2026-09-11 for BMRtoAltID under the "copy, do not construct" ruling: BMR rows sent onward are copied, so no column a downstream scorer reads can be lost. `required_headers` is the one public name here that `eidr_core.bmr_io` does not re-export.

**Use it when.** You need the list of columns whose absence makes a sheet non-conforming for a template, for example to build a test fixture or to explain a `TemplateMismatch` to an operator: `from eidr_core.bmr_io.subset import required_headers`.

**Do not use it when.**
* You want to check a real file. Call `check_sheet`, which applies `required_headers` together with the tab and header-row checks in the one shared place.
* Do not keep your own list of required BMR columns. The two-tier rule (operator ruling 2026-09-11: a column that is optional in the registry, or that a child record can inherit, may be empty or missing) lives here.
* Import `subset_rows`, `check_sheet`, `fill_column` and their report classes from `eidr_core.bmr_io`, not from this submodule.

**Used by.**
<!-- dict-usedby:eidr_core.bmr_io.subset -->
Scan of 2026-10-02; regenerated at each release from the consumer trees.
* **BMRtoAltID**: `required_headers`
<!-- /dict-usedby -->

### `required_headers`

<!-- dict:eidr_core.bmr_io.subset.required_headers -->
```python
def required_headers(template: str) -> tuple[str, ...]
```

Defined in `src/eidr_core/bmr_io/subset.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `template` | `str` | required | A `TEMPLATES` key such as `"non_episodic"`. Anything else raises `KeyError`. |

**Returns** `tuple[str, ...]` -- the required header names, in shipped row-3 order.
<!-- /dict -->

**Does.** Returns the shipped headers whose absence makes a sheet not that template's data sheet: sheet mechanics plus required, never-inherited columns. Every template requires `Unique Row ID`, `Operator's Notes`, `Assigned EIDR ID` and `Registration Errors & Notes`. Stand-Alone Works and Compilations add the root base fields (Structural Type, Mode, Referent Type, Title, Title Language, Original Language 1, Release Date, Country of Origin 1, Publication Status, Approx Length); Episodics add only `Parent EIDR/Row ID`; Edits, Clips and Manifestations add the parent plus their mandatory creation-type columns. Every other shipped column is optional: reported when missing, never refused.

**Notes.** The creation-type columns: Edits require Edit Use, Color Type, In 3D, Description, Approx Length and Release Date; Clips require Component Mode, Start Time and Content Duration; Manifestations require Manif Class 1. `Registrant` is never required, because the BMR tool supplies it from its Configuration tab.

## `eidr_core.codes`

<!-- dict-module:eidr_core.codes -->
Source `src/eidr_core/codes/__init__.py`. Public names: 1 function, 1 constant (declared by `__all__`).
<!-- /dict-module -->

**Purpose.** Country-code rules that every portfolio program must apply the same way. EIDR's convention is ISO 3166-1 alpha-2 for countries that exist, ISO 3166-3 alpha-4 for dissolved ones, UN M49 numbers for regions, and `XX` for unknown. So the alpha-2 code of a dissolved country (Wikidata P297 gives `SU` for the USSR) is always wrong for EIDR and is rewritten to alpha-4 (`SUHH`). The crosswalk used to be duplicated in eidr-wikidata and BMR-Review and is now single-homed here (register R1).

**Use it when.** You handle country codes in one of these ways:
* You take country codes from an outside source (Wikidata, a BMR sheet, an API) and need them in the EIDR code set.
* You compare two country codes or code lists and `SU` must equal `SUHH`.

**Do not use it when.** You need something else:
* Year-aware validity ("was this code valid in 1965?"): this rewrite ignores years. Use a `dq_country_validity` reader, such as eidr-wikidata's `bmr/country.py` CountryValidator. That reader is not shared yet (the module docstring plans it here), so a second project that needs it should propose extracting it rather than write another.
* A source's private codes (IMDb `XWG`, `XYU`): those belong in the source adapter's own table (eidr-imdb `mapping.py`).
* Language codes. `su` is the language Sundanese, and this function would turn it into `SUHH`.
* A Serbia and Montenegro record coded `CS`: it always becomes `CSHH` (Czechoslovakia).
* For field comparison, `eidr_core.normalize.norm_country` already applies this rewrite (and casefolds, and drops `XX`). `eidr_core.normalize.canon_country` is this same function under another name.
* Do not reimplement the SU to SUHH map, or add entries in a consumer. Add them to `OBSOLETE_ALPHA2_TO_ALPHA4` here.

**Used by.**
<!-- dict-usedby:eidr_core.codes -->
Scan of 2026-10-02; regenerated at each release from the consumer trees.
* **eidr-wikidata**: `normalize_country_code`
<!-- /dict-usedby -->

**Specs.** `specs/compare-spec.md` says country codes compare through the SU = SUHH crosswalk. The golden pair `src/eidr_core/specs/golden_pairs/country-codeset-su-suhh.json` pins it for every engine.

### `normalize_country_code`

<!-- dict:eidr_core.codes.normalize_country_code -->
```python
def normalize_country_code(code: str) -> str
```

Defined in `src/eidr_core/codes/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `code` | `str` | required | One country code in any case, surrounding whitespace allowed. `None` or `""` gives `""`. Pass M49 region codes as strings: an int raises AttributeError. |

**Returns** `str` -- The code stripped and uppercased, with an obsolete alpha-2 code replaced by its alpha-4 code (`SU` to `SUHH`, `YU` to `YUCS`, `CS` to `CSHH`, `DD` to `DDDE`, `BU` to `BUMM`). `""` for empty input.
<!-- /dict -->

**Does.** Returns the EIDR form of one country code, rewriting a dissolved or renamed country's alpha-2 code to alpha-4. Every other code is only stripped and uppercased: active alpha-2 codes, alpha-4 codes, M49 numbers and `XX`. It does not check that the code exists. Pure and independent of year.

### `OBSOLETE_ALPHA2_TO_ALPHA4` (constant)

<!-- dict:eidr_core.codes.OBSOLETE_ALPHA2_TO_ALPHA4 -->
Defined in `src/eidr_core/codes/__init__.py`.

**Value** `OBSOLETE_ALPHA2_TO_ALPHA4: dict[str, str] = { "SU": "SUHH", # U.S.S.R., dissolved 1991 "YU": "YUCS", # Yugoslavia (SFR), dissolved ...` -- The crosswalk from former ISO 3166-1 alpha-2 codes of dissolved or renamed countries to their ISO 3166-3 alpha-4 codes: SU to SUHH, YU to YUCS, CS to CSHH (Czechoslovakia, not Serbia and Montenegro's CSXX), DD to DDDE, BU to BUMM. Keys and values are uppercase. Read it, never mutate it: `normalize_country_code` uses this dict, so a change applies to the whole process. New entries are added in eidr-core.
<!-- /dict -->

## `eidr_core.compare`

<!-- dict-module:eidr_core.compare -->
Source `src/eidr_core/compare/__init__.py`. Public names: 19 functions, 1 class, 2 constants (declared by `__all__`). Some are defined in, and also importable from: `src/eidr_core/compare/_params.py`.
<!-- /dict-module -->

**Purpose.** The portfolio's one field-comparator library (layer L2 of unified-scoring.md): each `cmp_*` function compares one field of two EIDR records and returns a `FieldResult` with a continuous quality and, for Alt IDs, a conflict count. It was extracted from BMR-Review `eidr_dedup_score/compare.py` on 2026-07-28, so BMR-Review's scorer, its golden-pair evaluator and De-Dupe UI's conformance-vector generator all score through the same code. The compare-spec tuning constants are not hardcoded: comparators read them lazily from the object a consumer registers with `set_params`. The title-rule thresholds and quality constants in `titles` are the exception: they are module constants.

**Use it when.**
* You need the per-field quality of an EIDR-versus-EIDR candidate pair: dedup scoring, work-list payloads, golden-pair evaluation, conformance vectors.
* You are building a scorer: iterate `COMPARATORS` for the weighted fields and call `cmp_alt_ids` separately for the conflict signal.
* You author or load `DATE_PROFILES` and want them checked (`validate_date_profile`).

**Do not use it when.**
* Comparing an EIDR record with an external fact (Wikidata, IMDb, TMDb). Use `eidr_core.verify`: release-date precision makes that a different engine, and eidr-wikidata's tests assert its primitives never leak in here.
* You want the record-level score, band or verdict. That is BMR-Review's scorer (L3); this module returns field qualities only.
* You only need normalisation (`norm_title`, `parse_date`, ...). Import it from `eidr_core.normalize`; the same functions are reachable here only because this module imports them. The source keeps `norm_code` and `norm_title` for BMR-Review's star-import shim, but nothing reads them through `compare` today (grep, 2026-10-02).
* Do not reimplement the title or Alt-ID rules (part numbers, segments, the system-generated drop, the Alt-ID namespace, relation and ShortDOI rules). Call `cmp_titles`, `titles.title_similarity` or `cmp_alt_ids`; to change a rule, propose it here.

**Used by.**
<!-- dict-usedby:eidr_core.compare -->
Scan of 2026-10-02; regenerated at each release from the consumer trees.
* **BMR-Review**: `cmp_alt_ids`, `COMPARATORS`, `FieldResult`, `set_params`
* **De-Dupe UI**: `cmp_alt_ids`, `cmp_length`, `cmp_release_date`, `cmp_titles`
<!-- /dict-usedby -->

**Specs.**
* `specs/compare-spec.md` and `src/eidr_core/specs/compare-spec.json` (2.18.0): the constants the comparators read, `DATE_PROFILES`, and the definition of a common Alt ID (Kind, Value, identity relation; ShortDOI skipped).
* `specs/unified-scoring.md`: the L1/L2/L3 layering that makes this the single comparator library.
* `specs/normalized-record.md` section 4.1: Internal and system-generated titles are diminished, never ignored (the `INTERNAL_TITLE_DISCOUNT` mechanism).
* `specs/golden-pairs.md`: the corpus that pins comparator output across Python and JavaScript.

### `alt_source`

<!-- dict:eidr_core.compare.alt_source -->
```python
def alt_source(a)
```

Defined in `src/eidr_core/compare/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `a` | - | required | An Alt-ID object with `id_type` and `domain` attributes; either may be None or empty. |

**Returns** not annotated -- `str` namespace key (stripped, casefolded), or `None` for an opaque registry ID with no domain.
<!-- /dict -->

**Does.** Returns the namespace key under which an Alt ID's value is compared: its casefolded domain, else its casefolded type. Opaque types (Proprietary, Baseline, Other, EIDR, empty) without a domain give `None`: they are not cross-source identifiers. Beyond trimming and casefolding nothing is canonicalised, so `themoviedb.org/movie` and `themoviedb.org/tv` are different keys and a bare `themoviedb.org` matches neither. When a domain is present the type is ignored, so `IMDB` + `imdb.com` and `Proprietary` + `imdb.com` share one key.

**Notes.** It does not skip ShortDOIs; `cmp_alt_ids` does that itself. BMR-Review's `scorer._shares_any_alt_id` reuses this function for its relation-agnostic test; reuse it rather than writing a second key function.

### `cmp_actors`

<!-- dict:eidr_core.compare.cmp_actors -->
```python
def cmp_actors(a, b)
```

Defined in `src/eidr_core/compare/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `a` | - | required | Submitted record: any object with a `actors` list of objects carrying `.display` (the BMR-Review `CanonicalRecord` / `Name` shape). |
| `b` | - | required | Candidate record, same shape as `a`. |

**Returns** not annotated -- `FieldResult` with field `"actor"`: quality in [0, 1], or `None` (detail `absent`) when either side has no named entry.
<!-- /dict -->

**Does.** Compares actors lists by greedy one-to-one name alignment; quality is matched strength over the smaller list's size. Names go through `norm_name` ("Last, First" becomes "first last"), then fuzzy similarity: space-insensitive equality is 1.0, otherwise the larger of rapidfuzz `token_set_ratio` and `WRatio`. A pair below `NAME_MATCH_MIN` (0.80 at compare-spec 2.18.0) scores 0, so different people earn no partial credit. The result is capped at 1.0: people use proportional credit, not `accumulate`, so two 4-name lists sharing one name score 0.25, while a 1-name list matched inside a 4-name list scores 1.0.

**Notes.** Needs registered parameters (`NAME_MATCH_MIN`), else RuntimeError. Entries with an empty `display` are ignored on both sides.

### `cmp_alt_ids`

<!-- dict:eidr_core.compare.cmp_alt_ids -->
```python
def cmp_alt_ids(a, b)
```

Defined in `src/eidr_core/compare/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `a` | - | required | Submitted record: any object with an `alt_ids` list of objects carrying `id_type`, `domain`, `value`, `relation`. |
| `b` | - | required | Candidate record, same shape as `a`. |

**Returns** not annotated -- `FieldResult` with field `"alt_id"`: quality from `accumulate` over matched namespaces (1.0 each), `conflict` = number of shared namespaces whose values do not overlap, `meta={"matches": n}`. Quality is `None` when no namespace is shared or every shared one conflicts.
<!-- /dict -->

**Does.** Compares third-party identifiers per namespace: a shared value is identity evidence; disagreeing values in a shared namespace are a conflict. Entries are dropped first when they are ShortDOIs (an alias of the EIDR ID), opaque registry IDs (`alt_source` gives None), or carry a non-identity relation (anything but missing, empty or `IsSameAs`, tested per entry). Values compare stripped and casefolded; a namespace counts as matched when any value overlaps, so a shared IMDb ID is not cancelled by a second, unshared one. This is the only comparator that produces a negative signal.

**Notes.** Not in `COMPARATORS`: call it separately and read `conflict` and `meta["matches"]` (BMR-Review's scorer does, for the conflict penalty and the corroboration count). Quality `None` with `conflict > 0` is a normal result. The namespace is `alt_source`'s key (domain, else type), which is looser than the "id_type AND the full domain" Kind in the docstring and in compare-spec.md. No registered parameters are needed unless a namespace matches (`accumulate`).

### `cmp_assoc_orgs`

<!-- dict:eidr_core.compare.cmp_assoc_orgs -->
```python
def cmp_assoc_orgs(a, b)
```

Defined in `src/eidr_core/compare/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `a` | - | required | Submitted record: any object with an `assoc_orgs` list of objects carrying `name` and `party_id` (either may be None). |
| `b` | - | required | Candidate record, same shape as `a`. |

**Returns** not annotated -- `FieldResult` with field `"assoc_org"`: quality in [0, 1], or `None` (detail `absent`) when either list is empty.
<!-- /dict -->

**Does.** Matches associated organisations one-to-one, by equal party ID (1.0) or fuzzy normalised name, then scores proportionally. For each submitted org, in list order, the best remaining candidate org is taken if it reaches `NAME_MATCH_MIN`; quality is matched strength over the smaller list's length, capped at 1.0. The denominator counts every listed org, including ones with neither a name nor a party ID. Matching is greedy in submitted-list order, unlike people and titles, which take the best-scoring pair first across both lists.

### `cmp_countries`

<!-- dict:eidr_core.compare.cmp_countries -->
```python
def cmp_countries(a, b)
```

Defined in `src/eidr_core/compare/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `a` | - | required | Submitted record: any object whose `countries` is a list of objects carrying `.code`. |
| `b` | - | required | Candidate record, same shape as `a`. |

**Returns** not annotated -- `FieldResult` with field `"country"`: quality from `accumulate` (1.0 per matched code, so two matches give 1.75 at compare-spec values, up to 1 + `FIELD_BONUS_CAP`), or `None` (detail `absent`) when either side has no usable code.
<!-- /dict -->

**Does.** Compares country-of-origin codes as exact matches after `norm_country`, so SU and SUHH count as one country. `norm_country` casefolds, drops wildcards such as XX, and applies the obsolete alpha-2 to alpha-4 crosswalk. Each submitted code consumes at most one equal candidate code; the matches feed `accumulate`, so one match scores 1.0 and each further match adds a diminishing bonus. Do not swap in `norm_code`: that would break SU/SUHH equivalence, which BMR-Review's `tests/test_country_normalization.py` pins.

### `cmp_directors`

<!-- dict:eidr_core.compare.cmp_directors -->
```python
def cmp_directors(a, b)
```

Defined in `src/eidr_core/compare/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `a` | - | required | Submitted record: any object with a `directors` list of objects carrying `.display` (the BMR-Review `CanonicalRecord` / `Name` shape). |
| `b` | - | required | Candidate record, same shape as `a`. |

**Returns** not annotated -- `FieldResult` with field `"director"`: quality in [0, 1], or `None` (detail `absent`) when either side has no named entry.
<!-- /dict -->

**Does.** Compares directors lists by greedy one-to-one name alignment; quality is matched strength over the smaller list's size. Names go through `norm_name` ("Last, First" becomes "first last"), then fuzzy similarity: space-insensitive equality is 1.0, otherwise the larger of rapidfuzz `token_set_ratio` and `WRatio`. A pair below `NAME_MATCH_MIN` (0.80 at compare-spec 2.18.0) scores 0, so different people earn no partial credit. The result is capped at 1.0: people use proportional credit, not `accumulate`, so two 4-name lists sharing one name score 0.25, while a 1-name list matched inside a 4-name list scores 1.0.

**Notes.** Needs registered parameters (`NAME_MATCH_MIN`), else RuntimeError. Entries with an empty `display` are ignored on both sides.

### `cmp_distribution_number`

<!-- dict:eidr_core.compare.cmp_distribution_number -->
```python
def cmp_distribution_number(a, b)
```

Defined in `src/eidr_core/compare/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `a` | - | required | Submitted record: any object with `distribution_number`, `house_sequence`, `alt_numbers` (list of tuples whose first item is a number) and `release_date`. |
| `b` | - | required | Candidate record, same shape as `a`. |

**Returns** not annotated -- `FieldResult` with field `"distribution_number"`: 1.0, 0.5 or 0.0, or `None` (detail `absent`) when either side has no distribution number.
<!-- /dict -->

**Does.** Compares episode distribution numbers as tokens after stripping whitespace and leading zeros, with half credit for a likely renumbering. Equal numbers score 1.0. Unequal numbers score 0.5 when any number from {distribution number, house sequence, alternate numbers} is shared across the records, or when both carry identical full (day-level) release dates; otherwise 0.0. A mismatch is a real 0, not absence, so it stays in the scorer's denominator.

**Notes.** Needs no registered parameters. Comparison is exact string equality after stripping, so `21A` and `21a` differ.

### `cmp_end_date`

<!-- dict:eidr_core.compare.cmp_end_date -->
```python
def cmp_end_date(a, b)
```

Defined in `src/eidr_core/compare/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `a` | - | required | Submitted record: any object with `end_date` (raw string in any `normalize.parse_date` form). |
| `b` | - | required | Candidate record, same shape as `a`. |

**Returns** not annotated -- `FieldResult` with field `"end_date"`: 1.0 for the same year, else 0.5 ** (year gap / `DATE_YEAR_HALFLIFE_YEARS`); `None` (detail `absent`) when either year is unparseable.
<!-- /dict -->

**Does.** Compares series or season end dates at year precision with an exponential half-life decay. Month and day are ignored, and the quality never goes negative. It reads `DATE_YEAR_HALFLIFE_YEARS` (4.0 at compare-spec 2.18.0), so a 4-year gap scores 0.5; `DATE_PROFILES` do not apply here.

### `cmp_house_sequence`

<!-- dict:eidr_core.compare.cmp_house_sequence -->
```python
def cmp_house_sequence(a, b)
```

Defined in `src/eidr_core/compare/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `a` | - | required | Submitted record: any object with `house_sequence` (string or number). |
| `b` | - | required | Candidate record, same shape as `a`. |

**Returns** not annotated -- `FieldResult` with field `"house_sequence"`: 1.0 or 0.0, or `None` (detail `absent`) when either side is missing.
<!-- /dict -->

**Does.** Compares house sequence numbers as exact tokens after stripping whitespace and leading zeros, so `0415` equals `415`. Boolean: 1.0 or 0.0, no partial credit. Needs no registered parameters.

### `cmp_length`

<!-- dict:eidr_core.compare.cmp_length -->
```python
def cmp_length(a, b)
```

Defined in `src/eidr_core/compare/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `a` | - | required | Submitted record: any object with `length_minutes` (number or string such as `78`, `PT1H18M`, `01:18:00`) and `length_estimated` (bool, the AL:Pro flag). |
| `b` | - | required | Candidate record, same shape as `a`. |

**Returns** not annotated -- `FieldResult` with field `"length"`: quality in (0, 1], or `None` (detail `absent`) when either duration is missing, unparseable or zero.
<!-- /dict -->

**Does.** Compares durations leniently, taking the better of an absolute and a relative credit. Absolute credit is 0.5 ** (minute difference / `DUR_ABS_HALFLIFE_MIN`), with the half-life multiplied by `DUR_ESTIMATED_LENIENCY` when either side is estimated; relative credit is shorter / longer. It never goes negative: 90 against 100 minutes scores 0.9 (the relative credit).

### `cmp_original_language`

<!-- dict:eidr_core.compare.cmp_original_language -->
```python
def cmp_original_language(a, b)
```

Defined in `src/eidr_core/compare/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `a` | - | required | Submitted record: any object whose `original_languages` is a list of objects carrying `.code`. |
| `b` | - | required | Candidate record, same shape as `a`. |

**Returns** not annotated -- `FieldResult` with field `"original_language"`: quality from `accumulate` (1.0 per matched code, so two matches give 1.75 at compare-spec values, up to 1 + `FIELD_BONUS_CAP`), or `None` (detail `absent`) when either side has no usable code.
<!-- /dict -->

**Does.** Compares original-language codes as exact matches on the primary subtag after `norm_lang`, so `en-US` equals `en`. Wildcards (`und`, `xx`, `zz`) count as absent. Matches feed `accumulate`: one match scores 1.0, further matches add a diminishing bonus.

### `cmp_release_date`

<!-- dict:eidr_core.compare.cmp_release_date -->
```python
def cmp_release_date(a, b)
```

Defined in `src/eidr_core/compare/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `a` | - | required | Submitted record: any object with `release_date` (raw string: `YYYY`, `YYYY-MM`, `YYYY-MM-DD...`, `M/D/YYYY`), `date_estimated` (bool, the RD:Pro flag) and `creation_type`. |
| `b` | - | required | Candidate record, same shape as `a`. |

**Returns** not annotated -- `FieldResult` with field `"release_date"`: quality in [0, 1], never negative, or `None` (detail `absent`) when either year is unparseable. `detail` is `exact` for identical full dates (except 1970-01-01, which is an epoch suspect).
<!-- /dict -->

**Does.** Scores two release dates by precision, comparing full dates by day distance and anything coarser by year gap. With `DATE_PROFILES` registered, full dates use the profile's `full_date_bands` and, beyond the last band, its year table keyed on the larger of the calendar year gap and the distance-equivalent gap (at least 1), clamped to the last band; year-level pairs use `year_gap_credit` and `year_gap_floor`. Without profiles, or when a table cannot answer, the legacy half-life curves (`DATE_FULL_HALFLIFE_DAYS`, `DATE_YEAR_HALFLIFE_YEARS*`) apply. Epoch suspects (year-only 1970, or 1970-01-01) get the `DATE_EPOCH_*` credits instead of a full match and a floor on a mismatch.

**Notes.** The estimated flag acts differently by path: in the year-table path it multiplies the credit by `DATE_ESTIMATED_LENIENCY` (capped at 1.0, so at 2.0 a one-year gap scores 1.0, which for Episode beats the 0.80 a year match earns at compare-spec 2.18.0); in the legacy curves it lengthens the half-life; the day-band and fall-through paths ignore it apart from the ` est` detail suffix. A month-precision date (`YYYY-MM`) compares at year level. An impossible full ISO date such as `2001-02-30` against a different full date raises ValueError (from `days_between`).

### `cmp_sequence_number`

<!-- dict:eidr_core.compare.cmp_sequence_number -->
```python
def cmp_sequence_number(a, b)
```

Defined in `src/eidr_core/compare/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `a` | - | required | Submitted record: any object with `sequence_number` (string or number). |
| `b` | - | required | Candidate record, same shape as `a`. |

**Returns** not annotated -- `FieldResult` with field `"sequence_number"`: 1.0 or 0.0, or `None` (detail `absent`) when either side is missing.
<!-- /dict -->

**Does.** Compares season sequence numbers as exact tokens after stripping whitespace and leading zeros, so `05` equals `5`. Boolean, no partial credit, no registered parameters needed.

### `cmp_time_slot`

<!-- dict:eidr_core.compare.cmp_time_slot -->
```python
def cmp_time_slot(a, b)
```

Defined in `src/eidr_core/compare/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `a` | - | required | Submitted record: any object with `time_slot`. |
| `b` | - | required | Candidate record, same shape as `a`. |

**Returns** not annotated -- `FieldResult` with field `"time_slot"`: 1.0 or 0.0, or `None` (detail `absent`) when either side is None or empty.
<!-- /dict -->

**Does.** Compares episode time slots as exact strings after stripping surrounding whitespace. It is case-sensitive and keeps leading zeros, unlike the number comparators: `A` and `a` differ. A whitespace-only value is not absent: it is compared, and scores 0.0 against a real slot. Needs no registered parameters.

### `cmp_titles`

<!-- dict:eidr_core.compare.cmp_titles -->
```python
def cmp_titles(a, b)
```

Defined in `src/eidr_core/compare/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `a` | - | required | Submitted record: any object with a `titles` list (objects with `text`, optional `system_generated`, `title_class`) and optional `creation_type`. |
| `b` | - | required | Candidate record, same shape as `a`. |

**Returns** not annotated -- `FieldResult` with field `"title"`: quality from `accumulate` over the aligned pairs (above 1.0 when several titles match), or `None` with `meta={}` when a side has no title text or both sides hold only fallback titles. Otherwise `meta` has `best_sim`, `part_conflict`, `part_base_match`, `part_ambiguous`, plus `internal_title_used` when the Internal knob is registered.
<!-- /dict -->

**Does.** Compares two records' title lists with part and segment rules, greedy one-to-one alignment, and diminishing credit for extra matches. Real titles are preferred (`select_titles`): system-generated and, by default, Internal titles are fallback only, and the field is dropped when both sides fall back. Pair similarity is `titles.title_similarity`, with the episode rules on only when both records are Episode or Season. With `INTERNAL_TITLE_DISCOUNT` registered (a number in (0, 1]; compare-spec 2.18.0 sets 0.8), Internal titles are included, every pair touching one is multiplied by it, and an Internal pair counts only as the best aligned pair, never as an accumulation bonus; any other non-None value raises ValueError.

**Notes.** Needs registered parameters unless the field is dropped (`accumulate` reads `NL_MODIFIER`, `FIELD_BONUS_CAP`). `part_ambiguous` is reported only for episodic pairs with no part conflict, and `parts_conflict` already flags a numbered title against its bare base, so two episodes titled `Show Part 2` and `Show` report `part_conflict: True`, `part_ambiguous: False` while scoring `PART_AMBIGUOUS_QUALITY` (0.70). The detail strings `no real title to compare` and `system-generated titles only - ignored` are pinned by De-Dupe UI's spec audit; do not reword them casually.

### `cmp_version_language`

<!-- dict:eidr_core.compare.cmp_version_language -->
```python
def cmp_version_language(a, b)
```

Defined in `src/eidr_core/compare/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `a` | - | required | Submitted record: any object whose `version_languages` is a list of objects carrying `.code`. |
| `b` | - | required | Candidate record, same shape as `a`. |

**Returns** not annotated -- `FieldResult` with field `"version_language"`: quality from `accumulate` (1.0 per matched code, so two matches give 1.75 at compare-spec values, up to 1 + `FIELD_BONUS_CAP`), or `None` (detail `absent`) when either side has no usable code.
<!-- /dict -->

**Does.** Compares version-language codes as exact matches on the primary subtag after `norm_lang`, so `fr-CA` equals `fr`. Wildcards (`und`, `xx`, `zz`) count as absent. Matches feed `accumulate`: one match scores 1.0, further matches add a diminishing bonus.

### `date_profile`

<!-- dict:eidr_core.compare.date_profile -->
```python
def date_profile(a_ct, b_ct)
```

Defined in `src/eidr_core/compare/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `a_ct` | - | required | Submitted record's creation type (`"Basic"`, `"Episode"`, ...); None or empty is allowed. |
| `b_ct` | - | required | Candidate record's creation type. |

**Returns** not annotated -- `dict` profile with `year_gap_credit`, `year_gap_floor`, `full_date_bands`; or `None` when `DATE_PROFILES` is absent or empty, or holds neither the type nor `Basic`.
<!-- /dict -->

**Does.** Returns the date-comparison profile for a pair: the shared creation type's `DATE_PROFILES` entry, else the `Basic` entry. Cross-type pairs, a missing type and a type without its own profile all get `Basic` (`DATE_PROFILE_DEFAULT`). `None` signals a legacy configuration, and `cmp_release_date` then uses the flat half-life constants. Raises RuntimeError when no parameter source is registered at all.

**Notes.** Year keys may be int (authored in Python) or str (read back from JSON). `cmp_release_date` normalises them; if you index `year_gap_credit` yourself, normalise the keys to int first or a JSON-loaded profile silently misses every lookup.

### `set_params`

<!-- dict:eidr_core.compare.set_params -->
```python
def set_params(obj) -> None
```

Defined in `src/eidr_core/compare/_params.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `obj` | - | required | Any object whose attributes are the tuning constants: a config module, a class instance, or `types.SimpleNamespace(**load_spec())`. A plain dict does not work (attribute access only). `None` unregisters. |

**Returns** `None` -- registration only.
<!-- /dict -->

**Does.** Registers the process-wide object from which every comparator reads its tuning constants (`NL_MODIFIER`, `NAME_MATCH_MIN`, `DATE_*`, `DUR_*`, ...). Reads are lazy, so call it once at startup before the first scoring call; import order does not matter. Nothing is validated at registration: a missing constant raises AttributeError at the first comparator that reads it, and a comparator that reads a constant before any registration raises RuntimeError. A later call replaces the source for every caller in the process.

**Notes.** Optional attributes: `DATE_PROFILES` (absent means the legacy date curves) and `INTERNAL_TITLE_DISCOUNT` (absent means Internal titles stay fallback-only). `load_spec()` returns a dict, so wrap it: `set_params(types.SimpleNamespace(**load_spec()))`. BMR-Review registers `eidr_dedup_score.config` in its compare shim, and anything that imports that shim (De-Dupe UI's vector generator) inherits the registration.

### `validate_date_profile`

<!-- dict:eidr_core.compare.validate_date_profile -->
```python
def validate_date_profile(profile, name="profile")
```

Defined in `src/eidr_core/compare/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `profile` | - | required | One `DATE_PROFILES` entry: a dict with `year_gap_credit` ({gap: quality}, int or str keys), optional `year_gap_floor`, optional `full_date_bands` ([(max_days, quality), ...]). |
| `name` | - | `"profile"` | Label used as the prefix of every problem message, e.g. the creation type. |

**Returns** not annotated -- `list[str]` of problems; empty means the profile is sound.
<!-- /dict -->

**Does.** Checks a date profile for authoring defects and returns them as messages rather than raising them. It reports a year table that rises with distance, a floor above the last credit, and a last full-date band below the gap-1 credit (the band-to-year boundary would step up). Non-integer year keys return a single problem immediately. Call it from tests or when loading a spec; scoring never calls it, and the clamp in `cmp_release_date` covers only the band-to-year step, so a non-monotonic year table scores exactly as authored.

**Notes.** Needs no registered parameters. Both profiles shipped in compare-spec 2.18.0 validate clean; the docstring's remark that `Basic` fails by 0.01 describes 2.8.0. A year key that parses as an integer but is not written canonically (`"01"`, `" 1"`) raises KeyError instead of being reported.

### `FieldResult` (class)

<!-- dict:eidr_core.compare.FieldResult -->
```python
@dataclass
class FieldResult
```

Defined in `src/eidr_core/compare/__init__.py`.

| Field | Type | Default | Purpose |
|---|---|---|---|
| `field` | `str` | required | Engine field name: `title`, `director`, `actor`, `country`, `original_language`, `version_language`, `assoc_org`, `release_date`, `length`, `sequence_number`, `distribution_number`, `house_sequence`, `time_slot`, `end_date` or `alt_id`. Map it to a UI key with `states.ui_field_key`. |
| `quality` | `float \| None` | required | Continuous quality from 0 upward. `None` means not comparable (absent on a side, or titles dropped) and the scorer removes the field from the denominator. Accumulated fields (title, country, languages, alt_id) can exceed 1.0, up to 1 + `FIELD_BONUS_CAP`. |
| `detail` | `str` | `""` | Short readable explanation, e.g. `exact`, `4d apart`, `matches=1/2`, `absent`. Some strings are contract: BMR-Review's scorer tests for `exact` in the release-date detail, and De-Dupe UI's audit pins several. |
| `conflict` | `int` | `0` | Number of conflicting Alt-ID namespaces; only `cmp_alt_ids` sets it above 0. |
| `meta` | `dict \| None` | `None` | Extra structured output: `cmp_titles` fills `best_sim`, `part_conflict`, `part_base_match`, `part_ambiguous` (and `internal_title_used` with the knob), or `{}` when it drops the field; `cmp_alt_ids` fills `{"matches": n}`; the other comparators leave `None`. |
<!-- /dict -->

**Does.** Holds one comparator's result for one field: quality, readable detail, Alt-ID conflict count and optional metadata. A plain mutable dataclass with no methods and no validation. Read `quality is None` as "not comparable", never as 0.

### `COMPARATORS` (constant)

<!-- dict:eidr_core.compare.COMPARATORS -->
Defined in `src/eidr_core/compare/__init__.py`.

**Value** `COMPARATORS = { "title": cmp_titles, "director": cmp_directors, "actor": cmp_actors, "country": cmp_c...` -- Maps each engine field name to its comparator for the 14 weighted fields; every function takes `(submitted, candidate)` and returns a `FieldResult`. `alt_id` is deliberately absent: call `cmp_alt_ids` separately for its conflict count. Iterate this dict instead of hardcoding the field list, so a new comparator reaches every scorer.
<!-- /dict -->

### `DATE_PROFILE_DEFAULT` (constant)

<!-- dict:eidr_core.compare.DATE_PROFILE_DEFAULT -->
Defined in `src/eidr_core/compare/__init__.py`.

**Value** `DATE_PROFILE_DEFAULT = "Basic"` -- The `DATE_PROFILES` key `date_profile` uses when the two creation types differ, a type is missing, or a type has no profile of its own.
<!-- /dict -->

## `eidr_core.compare.nonlinear`

<!-- dict-module:eidr_core.compare.nonlinear -->
Source `src/eidr_core/compare/nonlinear.py`. Public names: 3 functions (declared by `__all__`).
<!-- /dict-module -->

**Purpose.** Within-field aggregation of per-element match qualities, extracted from BMR-Review together with `compare`. `accumulate` is the live path: the best match earns full credit whatever the list lengths, and each further match adds a diminishing, capped bonus (`NL_MODIFIER`, 0.75 in the Rovi lineage; `FIELD_BONUS_CAP`). `aggregate` and `corroborate` are older opportunity-count variants with no caller in any repository; `opportunities()` was removed on 2026-09-10.

**Use it when.**
* You write a comparator for a list-valued field and need the engine's within-field credit (titles, country and language codes, and Alt IDs all go through `accumulate`).
* You generate or check conformance vectors (De-Dupe UI does).

**Do not use it when.**
* You want a proportional "shared fraction" in [0, 1]. People and organisations use a private proportional rule inside `compare`, not this module.
* Do not reimplement the r^k series in a consumer; call `accumulate`, passing `r` and `bonus_cap` explicitly if you have no registered parameters.
* Do not use `corroborate` (deprecated, ignores its opportunity count) or `aggregate` (undocumented, no caller) in new code.

**Used by.**
<!-- dict-usedby:eidr_core.compare.nonlinear -->
Scan of 2026-10-02; regenerated at each release from the consumer trees.
* **BMR-Review**: `accumulate`, `aggregate`, `corroborate`, (the module)
* **De-Dupe UI**: `accumulate`
<!-- /dict-usedby -->

**Specs.** `specs/compare-spec.md` ("Scoring model") and compare-spec.json `values`: `NL_MODIFIER` (0.75) and `FIELD_BONUS_CAP` (1.0) at 2.18.0.

### `accumulate`

<!-- dict:eidr_core.compare.nonlinear.accumulate -->
```python
def accumulate(qualities, r=None, bonus_cap=None)
```

Defined in `src/eidr_core/compare/nonlinear.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `qualities` | - | required | Iterable of per-element match qualities (floats, normally 0 to 1); values of 0 or less are discarded. |
| `r` | - | `None` | Decay ratio applied to each further match; `None` reads `NL_MODIFIER` from the registered parameters. |
| `bonus_cap` | - | `None` | Maximum total bonus above the best match; `None` reads `FIELD_BONUS_CAP` from the registered parameters. |

**Returns** not annotated -- `float` in [0, 1 + bonus_cap] for inputs in [0, 1]; 0.0 when no quality is positive.
<!-- /dict -->

**Does.** Returns the best quality plus a capped, diminishing bonus q_k * r^(k-1) for each further match k. Qualities are sorted descending, so k = 2 is the second-best match; one match out of a hundred scores the same as one out of one. At compare-spec values (r 0.75, cap 1.0) `[1.0, 1.0]` gives 1.75 and `[0.9, 0.8]` gives 1.5. Raises RuntimeError when a defaulted `r` or `bonus_cap` is needed and no parameters are registered, even for an empty list.

### `aggregate`

<!-- dict:eidr_core.compare.nonlinear.aggregate -->
```python
def aggregate(qualities, n_opportunities, r=None, denom_basis=None)
```

Defined in `src/eidr_core/compare/nonlinear.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `qualities` | - | required | Iterable of match qualities; values of 0 or less are discarded. |
| `n_opportunities` | - | required | Number of elements that could have matched; raised to the count of positive qualities when smaller. 0 or less returns 0.0. |
| `r` | - | `None` | Decay ratio; `None` reads `NL_MODIFIER` from the registered parameters. |
| `denom_basis` | - | `None` | Ignored: the body never reads it. |

**Returns** not annotated -- `float`, in [0, 1] for inputs in [0, 1]: sum of q_i * r^(i-1) over the sum of r^(j-1) for j = 1..n; 0.0 when no quality is positive.
<!-- /dict -->

**Does.** Returns the opportunity-normalised series score: matched qualities weighted r^(i-1), divided by the weight sum of all opportunities. Every opportunity matched perfectly gives 1.0, and unmatched opportunities dilute the score (2 exact of 4 at r 0.75 gives 0.64). It has no docstring and no caller in any repository; the live engine uses `accumulate`. Raises RuntimeError when `r` is None and no parameters are registered.

### `corroborate`

<!-- dict:eidr_core.compare.nonlinear.corroborate -->
```python
def corroborate(qualities, n_opportunities, r=None)
```

Defined in `src/eidr_core/compare/nonlinear.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `qualities` | - | required | Iterable of match qualities, passed to `accumulate`. |
| `n_opportunities` | - | required | Ignored; kept for old call sites. |
| `r` | - | `None` | Decay ratio passed to `accumulate`; `None` reads `NL_MODIFIER`. |

**Returns** not annotated -- `float` exactly as `accumulate(qualities, r)`: in [0, 1 + `FIELD_BONUS_CAP`], not a [0, 1] ratio.
<!-- /dict -->

**Does.** Returns `accumulate(qualities, r)`, ignoring the opportunity count; deprecated. The bonus cap always comes from the registered `FIELD_BONUS_CAP`, so registered parameters are required. A caller expecting `aggregate`'s normalised [0, 1] score gets a different scale. No caller exists in any repository.

## `eidr_core.compare.spec`

<!-- dict-module:eidr_core.compare.spec -->
Source `src/eidr_core/compare/spec.py`. Public names: 2 functions (declared by `__all__`).
<!-- /dict-module -->

**Purpose.** Loader for `compare-spec.json`, the portfolio's single versioned tuning surface for match-candidate scoring (unified-scoring.md). It restores the Python semantics JSON loses: `set` / `frozenset` / `tuple` containers, and per-creation-type `WEIGHTS` in which `$alias` profiles share one dict object (tune Edit and Clip follows), plus the spec version and the `states` banding section. Since 2026-08-05 BMR-Review's `config.py` is the authoring surface and generates the JSON; this loader is the contract for every other reader.

**Use it when.**
* You need the engine's constants outside BMR-Review: golden-pair regeneration, a scoring service, conformance tooling, or `STATE_BANDS` for `states.field_states`.
* You generate the spec and want to round-trip it (BMR-Review's `regen_compare_spec.py` does).
* You need the packaged file's location (`spec_path`).

**Do not use it when.**
* You are tuning: edit BMR-Review's `config.py` and regenerate, never the JSON by hand.
* Do not read the engine constants with your own `json.load`: you lose the container types and the alias identity. Call `load_spec`.
* Do not pass its dict straight to `set_params`; wrap it in an attribute object first.

**Used by.**
<!-- dict-usedby:eidr_core.compare.spec -->
Scan of 2026-10-02; regenerated at each release from the consumer trees.
* **BMR-Review**: `load_spec`, `spec_path`, (the module)
<!-- /dict-usedby -->

**Specs.** `specs/compare-spec.md` (structure and tuning workflow) and `src/eidr_core/specs/compare-spec.json` (sections `$spec`, `types`, `weights`, `values`, `states`, `rationale_schema`; version 2.18.0 on 2026-10-02). `rationale_schema` is not returned by `load_spec`.

### `load_spec`

<!-- dict:eidr_core.compare.spec.load_spec -->
```python
def load_spec(path: str | os.PathLike | None = None) -> dict
```

Defined in `src/eidr_core/compare/spec.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `path` | `str \| os.PathLike \| None` | `None` | Spec file to read. `None` or empty: the `EIDR_COMPARE_SPEC` environment variable when set and non-empty, else the packaged file (`spec_path()`). |

**Returns** `dict` -- `{NAME: value}`: every `values` entry (containers rebuilt per `types`), plus `WEIGHTS`, `COMPARE_SPEC_VERSION` (str) and `STATE_BANDS` (the `states` section, `{}` if absent).
<!-- /dict -->

**Does.** Loads compare-spec.json and returns its constants as a `{NAME: value}` dict with Python container semantics restored. `WEIGHTS` maps creation type to `{"thresholds": tuple, "weights": dict}`, and an `$alias` entry is the same dict object as its target. Raises ValueError for an unknown container type or an alias whose target is not defined, KeyError for a missing `$spec.version` or a weights entry without `thresholds` / `weights`, and OSError or JSONDecodeError for an unreadable file. It reads the file on every call, caches nothing and does not check values (it does not run `validate_date_profile`).

**Notes.** The docstring promises a failure on a duplicate alias; there is no such check, and duplicate JSON keys silently keep the last value. An alias to another alias loads only when the target alias comes earlier in `weights`; otherwise it raises ValueError. To register the result: `set_params(types.SimpleNamespace(**load_spec()))`.

### `spec_path`

<!-- dict:eidr_core.compare.spec.spec_path -->
```python
def spec_path() -> Path
```

Defined in `src/eidr_core/compare/spec.py`.

No parameters.

**Returns** `Path` -- Path to `eidr_core/specs/compare-spec.json` inside the installed package.
<!-- /dict -->

**Does.** Returns the path of the packaged compare-spec.json, located through importlib.resources rather than a source-tree path. The result is a plain filesystem `Path`, so it is readable in regular and editable installs, not from a zipped package. It ignores `EIDR_COMPARE_SPEC` and does not check that the file exists. Call `load_spec()` with no argument to honour the environment override.

## `eidr_core.compare.states`

<!-- dict-module:eidr_core.compare.states -->
Source `src/eidr_core/compare/states.py`. Public names: 4 functions (declared by `__all__`).
<!-- /dict-module -->

**Purpose.** Turns the engine's per-field continuous qualities into the De-Dupe UI's four comparison states (identical, similar, mismatch, neutral) and maps engine field names to UI field-manifest keys. It implements the `states` section of compare-spec.json for payload producers building the per-candidate `scoring` object of dedupe-worklist.md section 4. Presentation only: it is never used in scoring.

**Use it when.**
* You build a work-list or Shim-mode scoring payload: `field_states` for `field_states` / `field_qualities`, `field_not_counted` for the optional `scoring.field_not_counted` map.
* You need the UI manifest key for an engine field (`ui_field_key`).

**Do not use it when.**
* You are in the UI: dedupe-worklist.md says the UI renders the payload's states and never recomputes them.
* You are scoring: the bands have no effect on the score.
* Do not hardcode 0.985 / 0.75 or the engine-to-UI key table in a consumer; pass the spec's `states` section and call `band` / `ui_field_key`.

**Used by.**
<!-- dict-usedby:eidr_core.compare.states -->
Scan of 2026-10-02; regenerated at each release from the consumer trees.
* **BMR-Review**: `band`, `field_not_counted`, `field_states`, `ui_field_key`, (the module)
<!-- /dict-usedby -->

**Specs.** `specs/dedupe-worklist.md` section 4 (payload shape, UI-manifest keys, states never recomputed by the UI); compare-spec.json `states` (defaults 0.985 / 0.75, empty `per_field`, `discriminative_fields` alt_id, release_date, length, edit_class, manifestation_class at 2.18.0); `specs/unified-scoring.md` (states are bands over q).

### `band`

<!-- dict:eidr_core.compare.states.band -->
```python
def band(quality, field: str, state_bands: dict) -> str
```

Defined in `src/eidr_core/compare/states.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `quality` | - | required | Per-field quality (float, may exceed 1.0), or `None` for a field absent on a side. |
| `field` | `str` | required | ENGINE field name (`title`, `alt_id`, ...), not the UI key: per-field overrides and `discriminative_fields` are keyed by engine names. |
| `state_bands` | `dict` | required | The spec's `states` section (`load_spec()["STATE_BANDS"]` or BMR-Review `config.STATE_BANDS`): `default`, `per_field`, `discriminative_fields`. Missing parts fall back to 0.985 / 0.75 and no discriminative fields. |

**Returns** `str` -- `"identical"`, `"similar"`, `"mismatch"` or `"neutral"`.
<!-- /dict -->

**Does.** Bands one quality into a UI state: identical from `identical_at`, similar from `similar_at`, else mismatch or neutral. Below `similar_at` the state is `mismatch` only for a discriminative field and `neutral` for every other field. `None` is always `neutral`. Per-field thresholds override the defaults key by key.

### `field_not_counted`

<!-- dict:eidr_core.compare.states.field_not_counted -->
```python
def field_not_counted(rationale: list, creation_type: str | None = None) -> dict
```

Defined in `src/eidr_core/compare/states.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `rationale` | `list` | required | Engine rationale rows (dicts with `field`, `quality`, `applicable`, `detail`); None or empty gives `{}`. |
| `creation_type` | `str \| None` | `None` | The pair's creation type; it only changes the key for `end_date` (Season gives `season_end_date`, anything else `series_end_date`). |

**Returns** `dict` -- UI manifest key to `"submitted"`, `"candidate"` or `"both"`; empty when every row with a quality was counted.
<!-- /dict -->

**Does.** Lists fields that have a real quality but were not counted in the score, naming the affected side. That row shape comes from compare-spec 2.13.0 Guard 1b: an inherited or system-generated value that mismatched. The side is parsed from the `detail` suffix "not the record's own value on the <side> side", defaulting to `both`. Emit the map as `scoring.field_not_counted` only when non-empty, so payload `format_version` 2.0 stays valid.

**Notes.** A row with a quality and no `applicable` key counts as not counted (the test is falsiness), so always emit `applicable`.

### `field_states`

<!-- dict:eidr_core.compare.states.field_states -->
```python
def field_states(rationale: list, state_bands: dict, creation_type: str | None = None) -> tuple[dict, dict]
```

Defined in `src/eidr_core/compare/states.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `rationale` | `list` | required | Engine rationale rows (dicts with `field`, `quality`, ...); rows without a `field` are skipped, None gives empty maps. |
| `state_bands` | `dict` | required | The spec's `states` section, as for `band`; None is treated as `{}`. |
| `creation_type` | `str \| None` | `None` | The pair's creation type; it only changes the `end_date` key. |

**Returns** `tuple[dict, dict]` -- `(states, qualities)`, both keyed by UI manifest key: states are `band` results, qualities the raw values (None kept).
<!-- /dict -->

**Does.** Builds the payload's `field_states` and `field_qualities` maps from an engine rationale, keyed by UI field-manifest keys. Banding uses the engine field name and the row's `quality` whatever `applicable` says, so a disagreement Guard 1b removed from the score still shows its glyph (operator ruling S-29 Option B, 2026-09-23). Pair it with `field_not_counted` to mark those rows. When two rows map to one key, the later row wins.

### `ui_field_key`

<!-- dict:eidr_core.compare.states.ui_field_key -->
```python
def ui_field_key(field: str, creation_type: str | None = None) -> str
```

Defined in `src/eidr_core/compare/states.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `field` | `str` | required | Engine rationale field name. |
| `creation_type` | `str \| None` | `None` | Used only for `end_date`: `Season` (case-insensitive, stripped) gives `season_end_date`; anything else, including None, gives `series_end_date`. |

**Returns** `str` -- UI field-manifest key; unknown names are returned unchanged.
<!-- /dict -->

**Does.** Maps an engine field name to its De-Dupe UI field-manifest key, such as `title` to `titles`. Renamed: title, country, assoc_org, length, alt_id, sequence_number, distribution_number, house_sequence, time_slot; other names (release_date, director, actor, original_language, version_language, edit_class) pass through. `end_date` splits by creation type into `season_end_date` or `series_end_date`.

## `eidr_core.compare.titles`

<!-- dict-module:eidr_core.compare.titles -->
Source `src/eidr_core/compare/titles.py`. Public names: 7 functions, 2 constants (declared by `__all__`).
<!-- /dict-module -->

**Purpose.** The one implementation of title matching: part-number parsing in several languages, order-independent segment titles, episode-only semantics, and the choice of which titles to compare (real versus system-generated or Internal). It was updated from BMR-Review's engine cycle on 2026-08-05, and BMR-Review's own `titles.py` is now a shim over it. `compare.cmp_titles` is built on it.

**Use it when.**
* You need the engine's pairwise similarity for two raw title strings (`title_similarity`), for example in an experiment or a verifier.
* You need to know whether titles carry a distinguishing part number (`parse_part`, `parts_conflict`, `parts_ambiguous`).
* You must pick the usable titles of a record (`select_titles`, `is_internal`).

**Do not use it when.**
* You want the field-level quality for two records: call `compare.cmp_titles`, which adds alignment, accumulation, the both-fallback drop and the Internal discount.
* You need display or canonical title order: use `eidr_core.ordering`.
* You only need a normalised title: use `eidr_core.normalize.norm_title`.
* Do not write your own part-number regexes or segment splitting; call `parse_part` / `segments`. Do not copy the private `_fuzzy` composite either (De-Dupe UI's vector generator carries a copy).

**Used by.**
<!-- dict-usedby:eidr_core.compare.titles -->
Scan of 2026-10-02; regenerated at each release from the consumer trees.
* **BMR-Review**: `parse_part`, `parts_conflict`, `segments`, `select_titles`, `title_similarity`
* **De-Dupe UI**: `COMBINATION_DIFFERS_QUALITY`, `parse_part`, `PART_AMBIGUOUS_QUALITY`, `parts_conflict`, `segments`, `title_similarity`
* **LanguageTool**: `title_similarity`
<!-- /dict-usedby -->

**Specs.** `specs/normalized-record.md` section 4.1 (Internal and system-generated titles are diminished, never ignored; section 7 gap 1) and `specs/compare-spec.md` (part numbering is distinguishing). The thresholds and the two quality constants are hardcoded here, not in compare-spec.json; De-Dupe UI's conformance vectors pin them.

### `is_internal`

<!-- dict:eidr_core.compare.titles.is_internal -->
```python
def is_internal(t)
```

Defined in `src/eidr_core/compare/titles.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `t` | - | required | Title object with `text`, optional `system_generated` (bool) and optional `title_class` (str). |

**Returns** not annotated -- `bool`.
<!-- /dict -->

**Does.** Returns True for a title with text whose class is `Internal` (case-insensitive, stripped) and that is not also system-generated. Internal titles are machine translations (operator, 2026-09-30). A title flagged both ways counts as system-generated, which keeps the both-sides drop in `cmp_titles` intact.

**Notes.** `eidr_core.ordering.is_internal_class` tests the class alone, for display buckets. For comparison use this function, which also returns False for empty text and for system-generated titles.

### `parse_part`

<!-- dict:eidr_core.compare.titles.parse_part -->
```python
def parse_part(raw, *, bare=True)
```

Defined in `src/eidr_core/compare/titles.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `raw` | - | required | Raw title (converted with `str()`); None or empty gives None. |
| `bare` | - | `True` (keyword-only) | When True, a trailing number without a part word also counts (`Rocky 2`, `Rocky II`, `Ocean's Eight`); trailing 4-digit numbers are years and never count. |

**Returns** not annotated -- `(base, part)`: base normalised by `norm_title` (leading article dropped), part an `int`; or `None` when no part number is found.
<!-- /dict -->

**Does.** Parses a part number out of a title and returns the normalised base title with the part as an integer. Forms tried in order: `X (1 of 2)`; `X, Part 2` with part words in several languages (part, pt, teil, partie, parte, deel, del, chapter, kapitel, episode, folge, avsnitt, osa, book, vol, ...); postfix `X 3. del`; mid-title `X 2: Subtitle`; and, with `bare`, a trailing `X 2`. Number tokens are 1-2 digits with optional st/nd/rd/th, roman numerals i to xii, spelled one to twenty, or ordinals first to twelfth (the `of` form takes any digits). A number with no base title before it gives None (`3. del` alone).

**Notes.** With `bare` on, a title that is only a part word and a number (`Part 2`) parses as base `part`, part 2. Roman tokens beyond xii (`Show xiii`) give None.

### `parts_ambiguous`

<!-- dict:eidr_core.compare.titles.parts_ambiguous -->
```python
def parts_ambiguous(a_titles, b_titles)
```

Defined in `src/eidr_core/compare/titles.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `a_titles` | - | required | Submitted side's raw title STRINGS (not Title objects), as a list. |
| `b_titles` | - | required | Candidate side's raw title strings, as a list: it is iterated once per submitted title, so a generator is exhausted after the first. |

**Returns** not annotated -- `bool`.
<!-- /dict -->

**Does.** Returns True when any title pair has a part number on exactly one side and the bases agree. Bases agree at fuzzy similarity >= 0.85; the un-numbered title may be one part or all parts combined, so the pair should not reach Accept on the title. It checks every pair, not only the best-matching pair its docstring mentions. `cmp_titles` uses it only for episodic pairs with no part conflict.

### `parts_conflict`

<!-- dict:eidr_core.compare.titles.parts_conflict -->
```python
def parts_conflict(a_raws, b_raws)
```

Defined in `src/eidr_core/compare/titles.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `a_raws` | - | required | Submitted side's raw title strings, as a list (iterated more than once; a generator gives wrong answers); empty entries are ignored. |
| `b_raws` | - | required | Candidate side's raw title strings, as a list. |

**Returns** not annotated -- `bool`.
<!-- /dict -->

**Does.** Returns True when titles carry a distinguishing part signal: one base, different part numbers, or numbered against bare. Same base means fuzzy similarity >= 0.85; the bare-base test uses plain edit-distance ratio >= 0.92, so a short base cannot subset-match a longer unrelated title, and it applies only when the other side has no same-base numbered title. A bare title starting with a numeral token is also tried without it (`I miserabili` normalises to `1 miserabili`). `Rocky 2` vs `Rocky 3` and `Rocky 2` vs `Rocky` are conflicts; `Rocky 2` vs `Rocky 2` is not.

### `segments`

<!-- dict:eidr_core.compare.titles.segments -->
```python
def segments(raw)
```

Defined in `src/eidr_core/compare/titles.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `raw` | - | required | Raw title; None or empty gives None. |

**Returns** not annotated -- `list[str]` of normalised segments in original order, or `None` when there is no `/` or `;` or fewer than two non-empty segments.
<!-- /dict -->

**Does.** Splits a compound title on `/` or `;` into normalised segments; returns None for a single-segment title. Every `/` splits, so `AC/DC: Live` gives `['ac', 'dc live']`; `title_similarity` treats compound titles as combinations only when `episodic` is set. The docstring says "set", but the result is a list and keeps duplicates.

### `select_titles`

<!-- dict:eidr_core.compare.titles.select_titles -->
```python
def select_titles(titles, *, include_internal=False)
```

Defined in `src/eidr_core/compare/titles.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `titles` | - | required | List (or other re-iterable collection) of title objects with `text`, optional `system_generated` and optional `title_class`. It is iterated twice, so a one-shot generator returns an empty fallback. |
| `include_internal` | - | `False` (keyword-only) | When True, Internal-class titles count as real and the caller must discount them (`cmp_titles` does, with `INTERNAL_TITLE_DISCOUNT`); when False (default) they are fallback-only. |

**Returns** not annotated -- `(titles, used_fallback)`: the real titles and False, or, when there are none, every title with text and True (possibly an empty list).
<!-- /dict -->

**Does.** Chooses which titles to compare: the real ones if any exist, otherwise every title with text, flagged as fallback. Real means non-empty text, not system-generated, and (unless `include_internal`) not class Internal. The default keeps the pre-0.40.0 behaviour byte for byte; the switch exists because normalized-record.md section 4.1 says Internal titles are diminished, never ignored.

### `title_similarity`

<!-- dict:eidr_core.compare.titles.title_similarity -->
```python
def title_similarity(a_raw, b_raw, *, episodic=False)
```

Defined in `src/eidr_core/compare/titles.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `a_raw` | - | required | First raw title string. |
| `b_raw` | - | required | Second raw title string. |
| `episodic` | - | `False` (keyword-only) | Turns on the episode-only rules: compound titles are combinations (a different set gives 0.20) and a part number on one side only is ambiguous (0.70). Off by default because both rules are wrong for films. |

**Returns** not annotated -- `float` in [0, 1].
<!-- /dict -->

**Does.** Returns the similarity of two raw titles in [0, 1], applying part-number and segment rules before plain fuzzy matching. Same base (>= 0.85) with part numbers on both sides (bare trailing numbers count) gives 1.0 for the same part and 0.05 for different parts. Compound titles score 1.0 for the same segment set in any order; otherwise films get proportional credit (lifted to the flat full-token score when that reaches 0.85) and episodes get `COMBINATION_DIFFERS_QUALITY`, or 1.0 when an undelimited side holds every segment. Plain titles compare by `norm_title` and then max(token_set_ratio, WRatio), with space-insensitive equality scoring 1.0.

**Notes.** Pure: needs no registered parameters. Because of token_set_ratio, a title whose tokens are a subset of the other's scores 1.0 (`The Matrix` vs `The Matrix Reloaded`); that is the engine's behaviour, so do not "fix" it locally.

### `COMBINATION_DIFFERS_QUALITY` (constant)

<!-- dict:eidr_core.compare.titles.COMBINATION_DIFFERS_QUALITY -->
Defined in `src/eidr_core/compare/titles.py`.

**Value** `COMBINATION_DIFFERS_QUALITY = 0.20` -- Similarity `title_similarity(..., episodic=True)` returns when two compound titles are different segment combinations, or when an undelimited title does not hold every segment of a delimited one. A different combination is a different program (operator, 2026-09-01). Module constant: not in compare-spec.json and not settable through `set_params`.
<!-- /dict -->

### `PART_AMBIGUOUS_QUALITY` (constant)

<!-- dict:eidr_core.compare.titles.PART_AMBIGUOUS_QUALITY -->
Defined in `src/eidr_core/compare/titles.py`.

**Value** `PART_AMBIGUOUS_QUALITY = 0.70` -- Similarity `title_similarity(..., episodic=True)` returns when only one title carries a part number and the bases agree (>= 0.85), so the title alone cannot carry a pair to Accept. Module constant: not in compare-spec.json and not settable through `set_params`.
<!-- /dict -->

## `eidr_core.db_schemas`

<!-- dict-module:eidr_core.db_schemas -->
Source `src/eidr_core/db_schemas/__init__.py`. Public names: 4 functions, 1 constant (declared by `__all__`).
<!-- /dict-module -->

**Purpose.** Consumer access to the schema contracts of the four portfolio PostgreSQL databases: the EIDR mirror, the DQ database, the language registry and the IMDb snapshot. The owners generate each contract from the live database and it ships inside eidr-core as `manifest.json`, `schema.sql` and `CHANGES.md` per database. The API is deliberately small, a startup assertion and three lookups with no typed models and no query layer (register 2.4). A reader then learns about a schema break at startup, with the contract version in the message, instead of from a SQL error halfway through a run.

**Use it when.** Your program reads one of the four databases:
* Call `assert_tables` once at startup, or in a test, listing exactly the tables and columns you read.
* Use `contract_version` when you need the contract's version for a log line or report, and `table_columns` for a table's column list.
* A database owner's drift check needs the published contract: `load_manifest` (MCP's schema validator does this).

**Do not use it when.** You need one of these instead:
* What the LIVE database holds. These functions read the packaged contract and never connect, so a live database that changed without the contract being regenerated still passes. Live-versus-contract drift is caught by the owner's dump tool (`--check`, eidr-core-ops `tools/dump_db_schema.py`) and MCP's freshness warning.
* Column types or nullability. `assert_tables` checks names only; read `load_manifest` for types.
* Do not write your own `information_schema` probe to guard a reader. Declare what you read with `assert_tables`. An owner validating its own live database (MCP's code-owned `EXPECTED_SCHEMA`) is a different job.
* A database not in `DATABASES`. Adding one is a change to eidr-core (manifest plus tuple entry), requested here.
* Vendoring: the module reads package data by the name `eidr_core`, so `eidr_core.vendor.sync` refuses it.

**Used by.**
<!-- dict-usedby:eidr_core.db_schemas -->
Scan of 2026-10-02; regenerated at each release from the consumer trees.
* **BMR-Review**: `assert_tables`, `contract_version`, `DATABASES`, `load_manifest`, `table_columns`
* **BMRtoAltID**: `assert_tables`
* **eidr-dq**: `assert_tables`, `contract_version`, `load_manifest`
* **eidr-imdb**: `assert_tables`, `load_manifest`
* **eidr-wikidata**: `assert_tables`, `contract_version`
* **MCP**: `load_manifest`
* **XML_to_JSON**: `assert_tables`, `load_manifest`
<!-- /dict-usedby -->

**Specs.** `specs/db-schema-contracts.md` (the approved pattern, the owners, the change workflow). The contracts themselves are in `src/eidr_core/specs/db_schemas/<database>/`: `manifest.json` (the machine contract), `schema.sql`, `CHANGES.md`.

### `assert_tables`

<!-- dict:eidr_core.db_schemas.assert_tables -->
```python
def assert_tables(database: str, needs: dict) -> None
```

Defined in `src/eidr_core/db_schemas/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `database` | `str` | required | One of `DATABASES`, for example `"eidr_mirror_db"`. Any other name raises KeyError. |
| `needs` | `dict` | required | `{table: [column, ...]}` naming only what this program reads. An empty list (or None) checks only that the table exists. |

**Returns** `None` -- Nothing. It returns normally when every declared table and column is in the contract.
<!-- /dict -->

**Does.** Checks that every table and column a consumer declares exists in the packaged schema contract. On any miss it raises RuntimeError naming every missing table and column, the database and the contract version. Raises KeyError for an unknown database. It reads only the packaged manifest (cached) and never connects to a database.

**Notes.** The RuntimeError message points to "eidr-core specs/db_schemas/<db>/CHANGES.md", but the file is at `src/eidr_core/specs/db_schemas/<db>/CHANGES.md`.

### `contract_version`

<!-- dict:eidr_core.db_schemas.contract_version -->
```python
def contract_version(database: str) -> str
```

Defined in `src/eidr_core/db_schemas/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `database` | `str` | required | One of `DATABASES`. Any other name raises KeyError. |

**Returns** `str` -- The contract's date version, such as `"2026.08.03-1"` (the mirror at 0.43.0).
<!-- /dict -->

**Does.** Returns the version string of a database's packaged schema contract. Raises KeyError for an unknown database. Log it at startup so an operator can match a failure to a `CHANGES.md` entry.

### `load_manifest`

<!-- dict:eidr_core.db_schemas.load_manifest -->
```python
def load_manifest(database: str) -> dict
```

Defined in `src/eidr_core/db_schemas/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `database` | `str` | required | One of `DATABASES`. Any other name raises KeyError. |

**Returns** `dict` -- The parsed `manifest.json`, with keys `database`, `version`, `generated_at`, `owner`, `source` and `tables`. `tables` maps each table name (no schema prefix) to `{"columns": [{"name", "type", "nullable"}, ...]}`.
<!-- /dict -->

**Does.** Loads and returns a database's packaged schema manifest as a dict. Raises KeyError for a name not in `DATABASES`. The result is cached for the life of the process (`functools.cache`), so every call returns the same dict object.

**Notes.** Never mutate the returned dict: every later call in the process sees the change, `assert_tables` included. `eidr_core.vendor.load_manifest` has the same name and is unrelated.

### `table_columns`

<!-- dict:eidr_core.db_schemas.table_columns -->
```python
def table_columns(database: str, table: str) -> list[str]
```

Defined in `src/eidr_core/db_schemas/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `database` | `str` | required | One of `DATABASES`. Any other name raises KeyError. |
| `table` | `str` | required | Table name as the contract lists it, with no schema prefix. A table not in the contract raises KeyError. |

**Returns** `list[str]` -- The table's column names, in contract order.
<!-- /dict -->

**Does.** Returns the column names of one table as listed in the packaged contract. Raises KeyError for an unknown database or a table the contract does not list. A new list on every call; reads the cached manifest.

### `DATABASES` (constant)

<!-- dict:eidr_core.db_schemas.DATABASES -->
Defined in `src/eidr_core/db_schemas/__init__.py`.

**Value** `DATABASES = ("eidr_mirror_db", "eidr_dq_db", "language_registry", "imdb_snapshot_db")` -- The four database names that have a packaged contract. Every function in this module accepts exactly these names and raises KeyError for any other. The order has no meaning.
<!-- /dict -->

## `eidr_core.dictionary`

<!-- dict-module:eidr_core.dictionary -->
Source `src/eidr_core/dictionary.py`. Public names: 3 functions (declared by `__all__`).
<!-- /dict-module -->

**Purpose.** Reads this dictionary from the copy shipped inside the installed
package, so an answer always describes the code the caller actually runs. A
session can look up one name instead of reading the whole file. Added in 0.46.0
(an operator-accepted suggestion). It imports nothing else from eidr-core and
needs no extra.

**Use it when.**
* Before you write a helper, check whether eidr-core already has one:
  `python -m eidr_core.dictionary <name>`, or `--index` to see every name.
* After you upgrade eidr-core, see what moved:
  `python -m eidr_core.dictionary --changes <the version you had>`.
* A tool or test needs an entry's text (`lookup`), or the whole dictionary
  (`text`).

**Do not use it when.**
* You cannot run Python, as in a chat session. Read the published
  `EIDR-CORE-DICTIONARY.md` instead.
* You want the signatures as data. Import the module and use `inspect`. This
  module returns Markdown meant for reading.

**Used by.**
<!-- dict-usedby:eidr_core.dictionary -->
No consumer imports it directly (scan of 2026-10-02).
<!-- /dict-usedby -->

### `changes`

<!-- dict:eidr_core.dictionary.changes -->
```python
def changes(since: str | None = None) -> str
```

Defined in `src/eidr_core/dictionary.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `since` | `str \| None` | `None` | A version such as `0.44.0`. Only entries for later versions are returned. `None` returns the whole Changes section. |

**Returns** `str` -- Markdown: the Changes section, or only the newer entries; `No changes after <since>.` when there are none.
<!-- /dict -->

**Does.** Returns the dictionary's Changes entries, newest first, optionally only those after a version. Versions compare numerically on their first three numbers, so `0.10.0` is newer than `0.9.0`.

### `lookup`

<!-- dict:eidr_core.dictionary.lookup -->
```python
def lookup(name: str) -> str | None
```

Defined in `src/eidr_core/dictionary.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `name` | `str` | required | A bare (`norm_title`), partial (`normalize.norm_title`) or full (`eidr_core.normalize.norm_title`) name, or a module path (`eidr_core.ids`). Surrounding whitespace is ignored. |

**Returns** `str | None` -- Markdown for the entry or module section; several entries separated by `---` when a bare name exists in more than one module; `None` when nothing matches or `name` is empty.
<!-- /dict -->

**Does.** Returns the dictionary entry for a name, or the section for a module path. An entry runs from its heading to the next heading; a module section runs to the next module.

### `text`

<!-- dict:eidr_core.dictionary.text -->
```python
def text() -> str
```

Defined in `src/eidr_core/dictionary.py`.

No parameters.

**Returns** `str` -- The whole dictionary as Markdown, identical to `DICTIONARY.md` at the root of the eidr-core commit that was installed.
<!-- /dict -->

**Does.** Reads the dictionary shipped inside the installed package. It is found through the package's own resources, so it works in a normal or editable install, not from a zipped one.

## `eidr_core.external`

<!-- dict-module:eidr_core.external -->
Source `src/eidr_core/external/__init__.py`. Public names: 3 functions, 4 classes, 6 constants (declared by `__all__`). Some are defined in, and also importable from: `src/eidr_core/external/failover.py`.
<!-- /dict-module -->

**Purpose.** The shared chassis for clients of outside data sources (Wikidata, TMDb, IMDb). It holds the fact-cache seam (the `FactCache` protocol plus three ready implementations), the fact-dict contract that providers return and `eidr_core.verify` consumes, and a re-export of the retry and endpoint-failover loop from `eidr_core.external.failover`. The cache half was extracted from eidr-dq `src/dq/external/cache.py` (register R13, 2026-08-06); the failover half came from eidr-wikidata. Stdlib only: nothing here imports a database driver or an HTTP library.

**Use it when.**
* A source client or identity crosswalk needs a cache: take a `FactCache` argument, never a database connection, so the code works over any store.
* You need a cache and have no database: `JsonFactCache` (one JSON file, optional expiry), `DictFactCache` (in memory), `NullFactCache` (no caching at all).
* You call an outside HTTP or SPARQL service and need retries, backoff, Retry-After handling and failover: `call_with_failover` with your own `attempt` and `classify`.
* You store or pass fetched facts: use the fact-dict shape `{"status": "found" | "not_found" | "error", "facts": {...}, "error": str}` so `eidr_core.verify` can read it (see `Entry`).

**Do not use it when.**
* You want a ready Wikidata, TMDb or IMDb client. Per-source clients are not here: Wikidata's home is eidr-wikidata, TMDb's is eidr-dq, IMDb's is eidr-imdb. Only the chassis is shared.
* Several processes or threads write one cache: `JsonFactCache` is single-writer. Implement `FactCache` over a database instead (eidr-dq's `DbFactCache` is the model).
* Do not write your own retry/backoff loop or Retry-After parser; call `call_with_failover` (a one-element endpoint list is fine for a single host) and `retry_after_seconds`.
* Do not invent another fact-dict shape. The cache and `eidr_core.verify` are two halves of one contract: change it here and in `verify` together, or not at all.

**Used by.**
<!-- dict-usedby:eidr_core.external -->
Scan of 2026-10-02; regenerated at each release from the consumer trees.
* **eidr-dq**: `call_with_failover`, `classify_sparql_error`, `DictFactCache`, `endpoint_chain`, `Entry`, `FactCache`, `FATAL`, `Key`, `NEXT_ENDPOINT`, `NullFactCache`, `OUTAGE`, `RETRY`
* **eidr-imdb**: `call_with_failover`, `endpoint_chain`, `FATAL`, `NEXT_ENDPOINT`, `OUTAGE`, `RETRY`
* **eidr-wikidata**: `call_with_failover`, `classify_sparql_error`, `DictFactCache`, `endpoint_chain`, `FactCache`, `NullFactCache`
<!-- /dict-usedby -->

### `call_with_failover`

<!-- dict:eidr_core.external.call_with_failover -->
```python
def call_with_failover(endpoints: Sequence[str], attempt: Callable[[str], Any], classify: Callable[[Exception], str], *, max_retries: int = 5, backoff: float = 2.0, jitter: float = 0.5, delay_seconds: float = 0.0, outage_endpoints: set[str] | None = None, op_label: str = "", chunk_label: str = "", rate_limit_floor: float = DEFAULT_RATE_LIMIT_FLOOR, max_retry_after: float = DEFAULT_MAX_RETRY_AFTER, cooldowns: dict[str, float] | None = None) -> tuple[Any, str | None, Exception | None]
```

Defined in `src/eidr_core/external/failover.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `endpoints` | `Sequence[str]` | required | Endpoints (URLs, or any label your `attempt` understands), tried in order. Build it with `endpoint_chain`. A one-element list gives retry without failover. Empty: nothing is attempted. |
| `attempt` | `Callable[[str], Any]` | required | Called as `attempt(endpoint)`: performs ONE request and returns the parsed result. Must raise on any failure and must never return None (None is the "all endpoints exhausted" signal). |
| `classify` | `Callable[[Exception], str]` | required | Called as `classify(exc)` on each exception `attempt` raises; returns `RETRY`, `NEXT_ENDPOINT`, `OUTAGE` or `FATAL`. Any other string acts as `NEXT_ENDPOINT`. An exception raised by `classify` itself propagates to your caller. Use `classify_sparql_error` for SPARQL. |
| `max_retries` | `int` | `5` (keyword-only) | Attempts per endpoint, INCLUDING the first (5 = one try plus up to 4 retries). 0 or less: no endpoint is attempted. |
| `backoff` | `float` | `2.0` (keyword-only) | Base of the retry sleep, in seconds: before retry n (n = 1, 2, ...) the loop sleeps `backoff * 2**n + uniform(0, jitter)`, or the owed Retry-After or rate-limit wait if that is longer, so 4.0 to 4.5 s before the first retry with the defaults. Not capped by `max_retry_after`. |
| `jitter` | `float` | `0.5` (keyword-only) | Upper bound, in seconds, of the random amount added to each retry sleep. 0 disables it. |
| `delay_seconds` | `float` | `0.0` (keyword-only) | Pacing sleep, in seconds, before EVERY attempt including the first, on top of any retry sleep. 0 or less disables it. |
| `outage_endpoints` | `set[str] \| None` | `None` (keyword-only) | Cross-call outage memo, mutated in place: endpoints in it are skipped, and an `OUTAGE` verdict adds the endpoint. Pass one set to every call of a multi-chunk operation. None: a private set for this call only. |
| `op_label` | `str` | `""` (keyword-only) | Operation name used in log lines (`call` when empty). |
| `chunk_label` | `str` | `""` (keyword-only) | Chunk name appended to log lines in parentheses; empty adds nothing. |
| `rate_limit_floor` | `float` | `DEFAULT_RATE_LIMIT_FLOOR` (keyword-only) | Minimum wait, in seconds, before the next attempt on an endpoint whose exception has HTTP status 429 or 503 but no Retry-After value. Default 5.0 (Wikimedia's rule). |
| `max_retry_after` | `float` | `DEFAULT_MAX_RETRY_AFTER` (keyword-only) | Longest single Retry-After or cooldown wait, in seconds, slept inside one call (the exponential backoff is not capped by it). A Retry-After or cooldown longer than this makes the loop leave that endpoint for the rest of the call instead of sleeping. |
| `cooldowns` | `dict[str, float] \| None` | `None` (keyword-only) | Cross-call Retry-After memo, endpoint -> `time.monotonic()` deadline, mutated in place. Pass one dict to every call in an operation so a later call does not probe a cooling endpoint. None: waits are honoured only within this call. Never persist it across processes. |

**Returns** `tuple[Any, str | None, Exception | None]` -- `(result, endpoint_used, last_exception)`. Success: `(result, endpoint, None)`. A `FATAL` verdict: `(None, None, exc)`. Every endpoint exhausted or skipped: `(None, None, last_exc)`, where `last_exc` is the most recent exception, or None when no attempt was made at all (empty chain, every endpoint in `outage_endpoints` or cooling for longer than `max_retry_after`, `max_retries` <= 0). Test `result is None` to detect failure, not the exception slot.
<!-- /dict -->

**Does.** Runs one request across an ordered endpoint chain, retrying, backing off, honouring Retry-After and failing over per your verdicts. Per verdict: `RETRY` retries the same endpoint after the backoff sleep or the Retry-After interval, whichever is longer; `NEXT_ENDPOINT` moves on at once; `OUTAGE` moves on and adds the endpoint to `outage_endpoints`; `FATAL` stops the whole walk. Any exception carrying a Retry-After interval (or a 429/503 status) is recorded in `cooldowns` whatever the verdict, and at the start of each endpoint a cooling one is skipped when a later endpoint is usable, otherwise its remaining window is slept, unless that window exceeds `max_retry_after`, in which case it is skipped too. Only `Exception` subclasses from `attempt` are caught; sleeps are blocking `time.sleep` calls, and every failure is logged as a WARNING (success on a fallback as INFO) on the `eidr_core.external.failover` logger.

**Notes.** An endpoint that was skipped or left is not revisited later in the same call. For a single host pass `[url]` rather than writing a parallel loop (eidr-dq's TMDb client does this). A provider whose transport hides response headers should set `exc.retry_after` (seconds) and an HTTP status as `exc.status` or `exc.code` on the exception it raises, so the Retry-After leg can see them.

### `classify_sparql_error`

<!-- dict:eidr_core.external.classify_sparql_error -->
```python
def classify_sparql_error(exc: Exception) -> str
```

Defined in `src/eidr_core/external/failover.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `exc` | `Exception` | required | The exception a SPARQL `attempt` raised (typically from SPARQLWrapper). Only `str(exc)` is examined. |

**Returns** `str` -- `OUTAGE` if `is_outage_error(exc)`; else `NEXT_ENDPOINT` if `is_bad_query_error(exc)`; else `RETRY` if the text contains 429, 500, 502, 503 or 504; else `NEXT_ENDPOINT`. Never `FATAL`.
<!-- /dict -->

**Does.** Classifies a SPARQL exception into a failover verdict by matching its message text in a fixed order. The order is deliberate: an outage message can contain "429" and a bad-query echo can contain anything, so both are tested before the status-code scan. The code scan is a plain substring test, so any matching digit run in the message counts. Pass it as `classify` for Wikidata Query Service and QLever endpoints; write your own `classify` for sources that report status codes (TMDb, S3).

### `endpoint_chain`

<!-- dict:eidr_core.external.endpoint_chain -->
```python
def endpoint_chain(primary: str | None, fallbacks: Iterable[str] | None = None) -> list[str]
```

Defined in `src/eidr_core/external/failover.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `primary` | `str \| None` | required | The first endpoint. None or blank is allowed and simply dropped. |
| `fallbacks` | `Iterable[str] \| None` | `None` | Further endpoints, in order; None and blank entries are dropped. Pass a list, not a bare string: a string is iterated character by character. |

**Returns** `list[str]` -- The endpoints in order, primary first, each stripped of surrounding whitespace, with blanks and exact duplicates removed. May be empty.
<!-- /dict -->

**Does.** Builds the ordered, de-duplicated endpoint list for `call_with_failover`: primary first, then fallbacks. Duplicates are compared exactly after stripping (no case folding, no trailing-slash normalisation), so `https://x/sparql` and `https://x/sparql/` both stay. Deciding which endpoints to use (config, environment, defaults) stays with the caller.

### `DictFactCache` (class)

<!-- dict:eidr_core.external.DictFactCache -->
```python
class DictFactCache
```

Defined in `src/eidr_core/external/__init__.py`.

| Method | Signature | Purpose |
|---|---|---|
| `__init__` | `def __init__(initial: dict[Key, Entry] \| None = None) -> None` | `initial`: entries to start with, copied shallowly (later changes to your dict are not seen). None: start empty. |
| `load` | `def load(keys: list[Key], *, refresh: bool = False) -> dict[Key, Entry]` | Returns the stored entries among `keys`; missing keys are absent. `refresh`: when true returns `{}` (entries are kept). Nothing ever expires. |
| `store` | `def store(results: dict[Key, Entry]) -> None` | Adds or overwrites entries. The entry dicts are kept by reference, not copied. |
<!-- /dict -->

**Does.** Keeps fact entries in a plain in-memory dict, with no expiry and no persistence. Meant for tests and short-lived runs; everything is lost with the object.

### `FactCache` (class)

<!-- dict:eidr_core.external.FactCache -->
```python
@runtime_checkable
class FactCache(Protocol)
```

Defined in `src/eidr_core/external/__init__.py`.

| Method | Signature | Purpose |
|---|---|---|
| `load` | `def load(keys: list[Key], *, refresh: bool = False) -> dict[Key, Entry]` | Must return the live (unexpired) entries among `keys`; a missing or expired key is simply absent, which the caller reads as "fetch it". `refresh`: when true the implementation must return nothing, forcing a refetch. |
| `store` | `def store(results: dict[Key, Entry]) -> None` | Must persist the entries, overwriting any existing entry for the same key. |
<!-- /dict -->

**Does.** Defines the two-method cache interface that source clients and crosswalks take instead of a database connection. It is a structural `typing.Protocol`: any object with `load` and `store` qualifies, with no inheritance. Because it is `runtime_checkable`, `isinstance(x, FactCache)` works, but it only checks that the two methods exist, not their signatures. Expiry is the implementation's business (error entries may expire sooner than found ones, for example), and an implementation that keeps nothing is valid.

### `JsonFactCache` (class)

<!-- dict:eidr_core.external.JsonFactCache -->
```python
class JsonFactCache
```

Defined in `src/eidr_core/external/__init__.py`.

| Method | Signature | Purpose |
|---|---|---|
| `__init__` | `def __init__(path: str \| os.PathLike[str], *, ttl_seconds: float \| None = None) -> None` | `path`: the JSON file, read now if it exists (missing means an empty cache; the file is created on the first `store`). `ttl_seconds`: entries stored more than this many seconds ago (wall clock) are invisible to `load`; None means never expire. A file that is not valid JSON raises `json.JSONDecodeError` here, and one in another shape usually raises `ValueError` or `TypeError` (an empty object `{}` loads as an empty cache). |
| `load` | `def load(keys: list[Key], *, refresh: bool = False) -> dict[Key, Entry]` | Returns the live entries among `keys`; missing or expired keys are absent. `refresh`: when true returns `{}` without deleting anything. |
| `store` | `def store(results: dict[Key, Entry]) -> None` | Stamps each entry with the current time, merges it in, and rewrites the WHOLE file atomically (writes `<path>.tmp`, then `os.replace`). Entries must be JSON-serialisable: a bad one raises `TypeError`, leaves a partial `<path>.tmp`, and stays in memory, so every later `store` on that object fails too. |
<!-- /dict -->

**Does.** Persists fact entries in one JSON file, with an optional single expiry time and atomic whole-file writes. A crash mid-store leaves the previous file intact. Expired entries are never purged: they stay in the file and are rewritten on every store, and one `ttl_seconds` applies to every status (found, not_found and error alike). Not safe for two writers at once (processes or threads); use a database-backed `FactCache` for that.

**Notes.** Every `store` rewrites the whole file, so store a batch of results in one call rather than one key at a time on a large cache. Added in 0.35.0 for BMR-Review T25, which has not adopted it yet.

### `NullFactCache` (class)

<!-- dict:eidr_core.external.NullFactCache -->
```python
class NullFactCache
```

Defined in `src/eidr_core/external/__init__.py`.

| Method | Signature | Purpose |
|---|---|---|
| `load` | `def load(keys: list[Key], *, refresh: bool = False) -> dict[Key, Entry]` | Always returns `{}`, whatever `keys` and `refresh` are. |
| `store` | `def store(results: dict[Key, Entry]) -> None` | Discards the entries. |
<!-- /dict -->

**Does.** Implements `FactCache` by storing nothing and returning nothing, so every lookup becomes a fetch. Use it in tests, one-shot tools, or wherever a cache argument is required but persistence is not wanted.

### `Entry` (constant)

<!-- dict:eidr_core.external.Entry -->
Defined in `src/eidr_core/external/__init__.py`.

**Value** `Entry = dict` -- Type alias (plain `dict` at runtime) for one cached fact dict in the fact-dict contract: key "status" is "found", "not_found" or "error"; key "facts" may hold "runtime_minutes" (list of float), "episode_runtime_minutes" (list of float), "release_date" ("YYYY-MM-DD", earliest known), "release_date_precision" ("day", "month" or "year") and "label" (str); key "error" (str) is present when status is "error". The "facts" dict is what `eidr_core.verify`'s compare functions take.
<!-- /dict -->

### `FATAL` (constant)

<!-- dict:eidr_core.external.FATAL -->
Defined in `src/eidr_core/external/failover.py`.

**Value** `FATAL = "fatal"` -- Verdict string a `classify` returns when no endpoint can help (authentication failure, malformed input): the walk stops at once and `call_with_failover` returns `(None, None, exc)`.
<!-- /dict -->

### `Key` (constant)

<!-- dict:eidr_core.external.Key -->
Defined in `src/eidr_core/external/__init__.py`.

**Value** `Key = tuple[str, str]` -- Type alias for a cache key: `(source, external_id)`, both strings, for example `("wikidata", "Q42")` as eidr-dq writes them.
<!-- /dict -->

### `NEXT_ENDPOINT` (constant)

<!-- dict:eidr_core.external.NEXT_ENDPOINT -->
Defined in `src/eidr_core/external/failover.py`.

**Value** `NEXT_ENDPOINT = "next-endpoint"` -- Verdict string for "this endpoint will not take this request" (for example a stricter SPARQL parser): move to the next endpoint at once, without remembering it, since it may still serve other requests. Any unrecognised verdict string is treated the same way.
<!-- /dict -->

### `OUTAGE` (constant)

<!-- dict:eidr_core.external.OUTAGE -->
Defined in `src/eidr_core/external/failover.py`.

**Value** `OUTAGE = "outage"` -- Verdict string for "this endpoint is down for the whole workload": move on at once and add it to `outage_endpoints`, so later calls sharing that set skip it instead of spending their retry budget.
<!-- /dict -->

### `RETRY` (constant)

<!-- dict:eidr_core.external.RETRY -->
Defined in `src/eidr_core/external/failover.py`.

**Value** `RETRY = "retry"` -- Verdict string for a transient failure (429 or 5xx class): retry the same endpoint after backoff (and any Retry-After wait), up to `max_retries` attempts in total.
<!-- /dict -->

## `eidr_core.external.failover`

<!-- dict-module:eidr_core.external.failover -->
Source `src/eidr_core/external/failover.py`. Public names: 5 functions, 5 constants (declared by `__all__`).
<!-- /dict-module -->

**Purpose.** The retry, backoff, Retry-After and endpoint-failover loop shared by every outside-service client in the portfolio, plus the SPARQL error classifiers. It was extracted from eidr-wikidata's `_query_endpoints` (register R13, 2026-08-09) to replace three diverging retry loops. The chassis owns the loop; the caller owns the transport (`attempt`) and the meaning of errors (`classify`). Stdlib only; its verdicts, `call_with_failover`, `classify_sparql_error` and `endpoint_chain` are also re-exported from `eidr_core.external`.

**Use it when.**
* A client calls an HTTP or SPARQL service and needs retries: wrap one request in `attempt`, write or reuse a `classify`, and call `call_with_failover`.
* You have several equivalent endpoints (WDQS plus QLever mirrors, for example): build the list with `endpoint_chain`.
* You run a multi-chunk or multi-batch job: share one `outage_endpoints` set and one `cooldowns` dict across all its calls.
* Your own code needs the Retry-After interval or the HTTP status an exception carries: `retry_after_seconds`, `http_status`.

**Do not use it when.**
* You need pacing between the requests of a batch loop, or a token bucket: inter-batch sleeps stay with the batch loop that owns them, and no token-bucket pacer exists yet. Only `delay_seconds` (a sleep before each attempt) is here.
* The source reports status codes rather than exception text: do not use `classify_sparql_error`; write a small `classify` of your own (eidr-dq's TMDb client and eidr-imdb's S3 client do).
* Do not hand-roll a retry loop, a Retry-After parser (delta-seconds and HTTP-date forms) or a local copy of `OUTAGE_SIGNATURES`; call `call_with_failover` (with `[url]` for a single host) and `retry_after_seconds`.

**Used by.**
<!-- dict-usedby:eidr_core.external.failover -->
Scan of 2026-10-02; regenerated at each release from the consumer trees.
* **BMR-Review**: `retry_after_seconds`
* **eidr-imdb**: `DEFAULT_RATE_LIMIT_FLOOR`
* **eidr-wikidata**: `is_bad_query_error`, `is_outage_error`, `retry_after_seconds`
<!-- /dict-usedby -->

### `cooldown_remaining`

<!-- dict:eidr_core.external.failover.cooldown_remaining -->
```python
def cooldown_remaining(cooldowns: dict[str, float] | None, endpoint: str) -> float
```

Defined in `src/eidr_core/external/failover.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `cooldowns` | `dict[str, float] \| None` | required | The memo passed as `call_with_failover(cooldowns=...)`: endpoint -> `time.monotonic()` deadline. None or empty: the result is 0. |
| `endpoint` | `str` | required | The endpoint to look up, spelled exactly as in the memo. |

**Returns** `float` -- Seconds still to wait (greater than 0), or 0.0 when there is no memo, no entry, or the entry has expired.
<!-- /dict -->

**Does.** Returns how many seconds remain before an endpoint may be called, according to a `cooldowns` memo. Side effect: an expired entry is removed from the dict. Deadlines are monotonic-clock values, meaningful only inside the process that wrote them.

### `http_status`

<!-- dict:eidr_core.external.failover.http_status -->
```python
def http_status(exc: BaseException) -> int | None
```

Defined in `src/eidr_core/external/failover.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `exc` | `BaseException` | required | Any exception. Only its attributes are read, never its message text. |

**Returns** `int | None` -- The first int found among `exc.code`, `exc.status`, `exc.status_code`, `exc.response.status_code` and `exc.response["ResponseMetadata"]["HTTPStatusCode"]` (botocore), in that order; booleans are ignored. None when none of them holds an int.
<!-- /dict -->

**Does.** Reads the HTTP status an exception carries from its attributes (urllib, requests, botocore, provider exceptions), never from text. Any int `code` attribute counts, so an exception that uses `code` for something other than an HTTP status yields that number. `call_with_failover` uses it to apply `rate_limit_floor` to a 429 or 503 that carries no Retry-After.

### `is_bad_query_error`

<!-- dict:eidr_core.external.failover.is_bad_query_error -->
```python
def is_bad_query_error(exc: Exception) -> bool
```

Defined in `src/eidr_core/external/failover.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `exc` | `Exception` | required | The exception to test. Only `str(exc)` is examined, ignoring case. |

**Returns** `bool` -- True if the text contains `QueryBadFormed`, `Invalid SPARQL query`, or both `bad request` and `sparql` (any case); otherwise False.
<!-- /dict -->

**Does.** Tests whether a SPARQL exception is a query-syntax or bad-request error that retrying will not fix. The right response is the next endpoint, not `FATAL`: WDQS predeclares common prefixes and QLever does not, so another endpoint's parser may accept the same query.

### `is_outage_error`

<!-- dict:eidr_core.external.failover.is_outage_error -->
```python
def is_outage_error(exc: Exception) -> bool
```

Defined in `src/eidr_core/external/failover.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `exc` | `Exception` | required | The exception to test. Only `str(exc)` is examined, ignoring case. |

**Returns** `bool` -- True if the text contains any entry of `OUTAGE_SIGNATURES`, ignoring case; otherwise False.
<!-- /dict -->

**Does.** Tests whether an exception's text carries a known Wikidata Query Service outage signature. Matching has been case-insensitive since 2026-08-27, so a sentence-initial or title-cased "WDQS outage" still matches. An outage means skip that endpoint for the whole operation, not retry it.

### `retry_after_seconds`

<!-- dict:eidr_core.external.failover.retry_after_seconds -->
```python
def retry_after_seconds(exc: BaseException, now: datetime | None = None) -> float | None
```

Defined in `src/eidr_core/external/failover.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `exc` | `BaseException` | required | An exception from your transport. Read in order: `exc.retry_after` (seconds, or a header string; set it when your transport hides headers), else the `Retry-After` header of `exc.headers` (urllib `HTTPError`), or of `exc.response.headers` (requests) only when `exc.headers` is absent or None. A present `exc.headers` without the header gives None; `exc.response.headers` is then not tried. |
| `now` | `datetime \| None` | `None` | Reference time for the HTTP-date form; None means the current UTC time. Must be timezone-aware: a naive datetime raises `TypeError` when the value is an HTTP-date. Exists for tests. |

**Returns** `float | None` -- The interval in seconds, never negative (a past date or a negative number gives 0.0), or None when no value is present or it cannot be parsed.
<!-- /dict -->

**Does.** Returns the Retry-After interval an exception carries, in seconds, from the delta-seconds or HTTP-date form. An explicit `exc.retry_after` wins even when it cannot be parsed (the result is then None; headers are not consulted). An HTTP-date without a time zone is taken as UTC. The header is read with `headers.get("Retry-After")`: case-insensitive for urllib and requests header objects, exact-case for a plain dict.

### `DEFAULT_MAX_RETRY_AFTER` (constant)

<!-- dict:eidr_core.external.failover.DEFAULT_MAX_RETRY_AFTER -->
Defined in `src/eidr_core/external/failover.py`.

**Value** `DEFAULT_MAX_RETRY_AFTER = 600.0` -- Default `max_retry_after`, in seconds (10 minutes): the longest Retry-After or cooldown wait slept inside one call. A longer interval makes the call leave that endpoint; the `cooldowns` memo still keeps later calls off it until the interval passes.
<!-- /dict -->

### `DEFAULT_RATE_LIMIT_FLOOR` (constant)

<!-- dict:eidr_core.external.failover.DEFAULT_RATE_LIMIT_FLOOR -->
Defined in `src/eidr_core/external/failover.py`.

**Value** `DEFAULT_RATE_LIMIT_FLOOR = 5.0` -- Default `rate_limit_floor`, in seconds: the wait before the next attempt on an endpoint that answered 429 or 503 without a Retry-After value (Wikimedia's "wait at least five seconds" rule, applied to 503 as well).
<!-- /dict -->

### `OUTAGE_SIGNATURES` (constant)

<!-- dict:eidr_core.external.failover.OUTAGE_SIGNATURES -->
Defined in `src/eidr_core/external/failover.py`.

**Value** `OUTAGE_SIGNATURES = ( "wdqs outage", "Aggressively rate-limiting", )` -- Message fragments, matched case-insensitively by `is_outage_error`, meaning a WDQS endpoint is rate-limiting the whole workload (observed verbatim in the 2026-05-09/10 WDQS outages). Read it from here; do not keep a local copy.
<!-- /dict -->

### `RATE_LIMIT_STATUSES` (constant)

<!-- dict:eidr_core.external.failover.RATE_LIMIT_STATUSES -->
Defined in `src/eidr_core/external/failover.py`.

**Value** `RATE_LIMIT_STATUSES = frozenset({429, 503})` -- HTTP statuses (429 Too Many Requests, 503 Service Unavailable) for which `call_with_failover` waits `rate_limit_floor` and records a cooldown when the exception carries no Retry-After value.
<!-- /dict -->

### `TRANSIENT_HTTP_MARKERS` (constant)

<!-- dict:eidr_core.external.failover.TRANSIENT_HTTP_MARKERS -->
Defined in `src/eidr_core/external/failover.py`.

**Value** `TRANSIENT_HTTP_MARKERS = ("429", "500", "502", "503", "504")` -- Status-code substrings that make `classify_sparql_error` return `RETRY` when found anywhere in an exception's text (tested after the outage and bad-query checks).
<!-- /dict -->

## `eidr_core.ids`

<!-- dict-module:eidr_core.ids -->
Source `src/eidr_core/ids/__init__.py`. Public names: 8 functions, 9 constants (declared by `__all__`).
<!-- /dict-module -->

**Purpose.** The one implementation of EIDR identifier syntax. It validates Content IDs (`10.5240/`) including the ISO 7064 Mod 37,36 check character, pattern-checks party (`10.5237/`), user (`10.5238/`) and service (`10.5239/`) DOIs (which carry no check character), classifies a DOI by prefix, and pulls Content IDs out of free text. It was accepted on 2026-08-26 from BMR-Review's proposal, seeded from its `validate_returned_ids.py`, and shared without waiting for a second consumer because the ID shape and the checksum are published standards: a local copy is a second chance to get them wrong silently (BMR-Review's first copy reported all 2,996 valid production IDs it checked as broken). It imports only `re`, so it is closed under imports and a package that cannot depend on eidr-core (python-sdk) can vendor it whole.

**Use it when.**
* You must decide whether a value is a real-looking EIDR Content ID: `is_valid_eidr_id` for yes or no, `fault` when a person needs the reason.
* You are pulling Content IDs out of a notes column, log line or error message: `find_content_ids`.
* You need to know which family a DOI belongs to (content, party, user, service): `category`.
* You validate party, service or user DOIs: `is_valid_party_id`, `is_valid_service_id`, `is_valid_user_id`.
* You validate only the part after the prefix: compose from `PARTY_ID_SUFFIX`, `SERVICE_ID_SUFFIX`, `USER_ID_SUFFIX`.
* You need synthetic test IDs with a correct check character: `check_character`.

**Do not use it when.**
* You need to know whether an ID is registered. Everything here is syntax and checksum only; a valid ID may not exist in the registry.
* The value carries a `doi:` prefix or is a DOI URL. `fault`, `is_valid_eidr_id` and `category` strip only whitespace, so strip the prefix first. `find_content_ids` does find `doi:10.5240/...` but not `https://doi.org/10.5240/...`.
* You need a ShortDOI or non-EIDR DOI check. Nothing here recognises them (for an alternate ID's type and domain, see `eidr_core.ordering.is_shortdoi`).
* Do not write a local `10.5240/` regex or a Mod 37,36 loop: call `is_valid_eidr_id`, `fault` or `find_content_ids`. A package that cannot depend on eidr-core vendors this module with `eidr_core.vendor` instead of copying it by hand: python-sdk does, and python-tools reaches it through the SDK rather than keeping a second copy.

**Used by.**
<!-- dict-usedby:eidr_core.ids -->
Scan of 2026-10-02; regenerated at each release from the consumer trees.
* **BMR-Review**: `category`, `fault`, `find_content_ids`, `is_valid_eidr_id`
* **BMRtoAltID**: `fault`
* **De-Dupe UI**: `ALPHABET`, `check_character`, `is_valid_eidr_id`
* **eidr-wikidata**: `fault`, `is_valid_eidr_id`
* **python-sdk**: (vendors the module, pin `46cd70a`)
* **XML_to_JSON**: `is_valid_eidr_id`
<!-- /dict-usedby -->

**Specs.** `specs/vendoring.md` fixes how python-sdk carries this module (`modules = ["ids"]`, closed under imports because it imports only `re`). `specs/golden-pairs.md` section 2 fixes that synthetic fixture IDs use the hex `FEED-` prefix with a correct check character where validity matters, because `is_valid_eidr_id` rejects the non-hex `GOLD-`.

### `category`

<!-- dict:eidr_core.ids.category -->
```python
def category(doi: str | None) -> str | None
```

Defined in `src/eidr_core/ids/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `doi` | `str \| None` | required | The value to classify. Any object is accepted; it is converted with `str()` and stripped of surrounding whitespace. `None` returns `None`. |

**Returns** `str | None` -- `'content'` (`10.5240/`), `'party'` (`10.5237/`), `'user'` (`10.5238/`) or `'service'` (`10.5239/`); `None` when `doi` is `None` or the stripped text does not start with one of those prefixes.
<!-- /dict -->

**Does.** Classifies a DOI into its EIDR ID family by prefix alone. The suffix is not checked: `10.5237/garbage` is still `'party'`, so pair it with `is_valid_party_id` (or `fault`) when well-formedness matters. A prefixed form such as `doi:10.5240/...` or a DOI URL returns `None`. Mirrors the SDK's `IDCategory` and never raises.

### `check_character`

<!-- dict:eidr_core.ids.check_character -->
```python
def check_character(payload: str) -> str
```

Defined in `src/eidr_core/ids/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `payload` | `str` | required | The suffix with hyphens removed and WITHOUT the check character: 20 hex characters for a Content ID. Either case. Any character outside 0-9 and A-Z (a hyphen included) raises `ValueError`. Length is not checked. |

**Returns** `str` -- One upper-case character from `ALPHABET` (0-9 or A-Z). An empty payload returns `'1'` rather than raising.
<!-- /dict -->

**Does.** Computes the ISO 7064 Mod 37,36 check character for an EIDR suffix payload. The register starts at 36, not 1; BMR-Review's first copy started at 1 and rejected essentially every valid ID. Use it to build test IDs or to name the expected character; to validate a whole ID, call `is_valid_eidr_id` or `fault`.

### `fault`

<!-- dict:eidr_core.ids.fault -->
```python
def fault(eidr_id: str | None) -> str | None
```

Defined in `src/eidr_core/ids/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `eidr_id` | `str \| None` | required | The candidate Content ID. Converted with `str()` and stripped of surrounding whitespace; either case is accepted. No `doi:` or URL prefix is removed. |

**Returns** `str | None` -- `None` when the value is a well-formed Content ID whose check character validates; otherwise a human-readable reason. Never raises.
<!-- /dict -->

**Does.** Returns the reason a Content ID is unsound, or `None` when it is sound. The reasons distinguish a missing value (`None`), an empty one, a party, service or user ID given where a content ID was expected (with "(and malformed ...)" added when that ID is itself malformed), any other malformed shape, and a good shape whose check character does not validate (naming the expected and the found character). The split matters: a malformed ID usually means a parsing or transcription problem upstream, while a bad check character usually means a corrupted or fabricated value.

**Notes.** The reason text is for people, and it has changed before (party IDs got their own wording on 2026-09-10). Branch on `None` versus not-`None`, and use `category` when you need the family.

### `find_content_ids`

<!-- dict:eidr_core.ids.find_content_ids -->
```python
def find_content_ids(text: str | None, *, valid_only: bool = True) -> list[str]
```

Defined in `src/eidr_core/ids/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `text` | `str \| None` | required | Free text to search (a notes column, a log line, an error message). Converted with `str()`. `None` or empty returns `[]`. |
| `valid_only` | `bool` | `True` (keyword-only) | `True` keeps only IDs whose check character validates, so a typo is not handed on as a candidate. `False` returns every ID-shaped match, for example to report the bad ones with `fault`. |

**Returns** `list[str]` -- Content IDs in order of first appearance, upper-cased and de-duplicated; `[]` when none are found.
<!-- /dict -->

**Does.** Extracts every EIDR Content ID mentioned in free text, upper-cased and de-duplicated in order of appearance. Matching uses `CONTENT_ID_SEARCH_RE`, which refuses a match glued to a preceding letter, digit or `/`, or to a following letter, digit or hyphen. Party, service and user IDs are ignored.

**Notes.** An ID inside a URL path is NOT found: `https://doi.org/10.5240/...` returns `[]` because the ID follows a `/`. Strip URL prefixes first if your text carries them. `doi:10.5240/...`, `id=10.5240/...` and `(10.5240/...)` are found.

### `is_valid_eidr_id`

<!-- dict:eidr_core.ids.is_valid_eidr_id -->
```python
def is_valid_eidr_id(eidr_id: str | None) -> bool
```

Defined in `src/eidr_core/ids/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `eidr_id` | `str \| None` | required | The candidate Content ID, handled as in `fault`: stringified, whitespace-stripped, either case. `None` and empty return `False`. |

**Returns** `bool` -- `True` when the value is a syntactically sound Content ID whose check character validates; `False` otherwise.
<!-- /dict -->

**Does.** Tests whether a value is a well-formed, checksum-valid EIDR Content ID. It is exactly `fault(eidr_id) is None`, so call `fault` when you need to say why not. Party, service and user IDs return `False`; use `category` and the matching `is_valid_*_id` for those.

### `is_valid_party_id`

<!-- dict:eidr_core.ids.is_valid_party_id -->
```python
def is_valid_party_id(party_id: str | None) -> bool
```

Defined in `src/eidr_core/ids/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `party_id` | `str \| None` | required | The candidate party DOI. Stringified and whitespace-stripped; `None` or empty returns `False`. |

**Returns** `bool` -- `True` for `10.5237/XXXX-XXXX` (hex, either case) or the literal `10.5237/superparty`; `False` otherwise.
<!-- /dict -->

**Does.** Tests whether a value matches the party DOI pattern `PARTY_ID_RE`. Pattern check only: party IDs carry no check character, so a typo in the hex cannot be detected. The hex is case-insensitive but `superparty` must be lower-case, so `10.5237/SUPERPARTY` returns `False`.

### `is_valid_service_id`

<!-- dict:eidr_core.ids.is_valid_service_id -->
```python
def is_valid_service_id(service_id: str | None) -> bool
```

Defined in `src/eidr_core/ids/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `service_id` | `str \| None` | required | The candidate service DOI. Stringified and whitespace-stripped; `None` or empty returns `False`. |

**Returns** `bool` -- `True` for `10.5239/XXXX-XXXX` (hex, either case); `False` otherwise.
<!-- /dict -->

**Does.** Tests whether a value matches the service DOI pattern `SERVICE_ID_RE`. Pattern check only; service IDs carry no check character. The schema writes the hex upper-case only, but lower-case is accepted on purpose because the registry treats hex as hex.

### `is_valid_user_id`

<!-- dict:eidr_core.ids.is_valid_user_id -->
```python
def is_valid_user_id(user_id: str | None) -> bool
```

Defined in `src/eidr_core/ids/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `user_id` | `str \| None` | required | The candidate user DOI. Stringified and whitespace-stripped; `None` or empty returns `False`. |

**Returns** `bool` -- `True` for `10.5238/` followed by a username of 3 to 32 characters from `0-9 a-z A-Z _ # . - ( )`; `False` otherwise.
<!-- /dict -->

**Does.** Tests whether a value matches the user DOI pattern `USER_ID_RE`. The username is free-form, so the pattern (schema 2.7.0 `userDOIType`) is the only check there is.

### `ALPHABET` (constant)

<!-- dict:eidr_core.ids.ALPHABET -->
Defined in `src/eidr_core/ids/__init__.py`.

**Value** `ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"` -- The ISO 7064 Mod 37,36 base-36 alphabet, digits then upper-case letters. A character's index is its value in `check_character`, and every check character is one of these.
<!-- /dict -->

### `CONTENT_ID_SEARCH_RE` (constant)

<!-- dict:eidr_core.ids.CONTENT_ID_SEARCH_RE -->
Defined in `src/eidr_core/ids/__init__.py`.

**Value** `CONTENT_ID_SEARCH_RE = re.compile( r"(?<![0-9A-Z/])10\.5240/[0-9A-F]{4}(?:-[0-9A-F]{4}){4}-[0-9A-Z](?![0-9A-Z-...` -- Compiled, case-insensitive, UNANCHORED Content ID shape for searching free text. It will not match when glued to a preceding letter, digit or `/` (so not inside a DOI URL), or to a following letter, digit or hyphen. Shape only, no checksum: `find_content_ids` adds the check and is what most callers want. De-Dupe UI's engine mirrors this rule in JavaScript, so treat the pattern as a cross-language fact.
<!-- /dict -->

### `EIDR_CONTENT_ID_RE` (constant)

<!-- dict:eidr_core.ids.EIDR_CONTENT_ID_RE -->
Defined in `src/eidr_core/ids/__init__.py`.

**Value** `EIDR_CONTENT_ID_RE = re.compile( r"^10\.5240/[0-9A-F]{4}(?:-[0-9A-F]{4}){4}-[0-9A-Z]$", re.I )` -- Compiled, case-insensitive, ANCHORED Content ID shape: `10.5240/`, five 4-hex groups, one check character. The check character ranges over 0-9A-Z, not only hex. Shape only; it does not verify the check character, so validate with `is_valid_eidr_id`. Match it against stripped text.
<!-- /dict -->

### `PARTY_ID_RE` (constant)

<!-- dict:eidr_core.ids.PARTY_ID_RE -->
Defined in `src/eidr_core/ids/__init__.py`.

**Value** `PARTY_ID_RE = re.compile(r"^10\.5237/" + PARTY_ID_SUFFIX + r"$")` -- Compiled, anchored party DOI pattern: `10.5237/` plus `PARTY_ID_SUFFIX`. No `re.I` flag; the case rules live in the suffix. `is_valid_party_id` wraps it.
<!-- /dict -->

### `PARTY_ID_SUFFIX` (constant)

<!-- dict:eidr_core.ids.PARTY_ID_SUFFIX -->
Defined in `src/eidr_core/ids/__init__.py`.

**Value** `PARTY_ID_SUFFIX = r"(?:[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}\|superparty)"` -- Regex source string (not compiled) for the part after `10.5237/`: `XXXX-XXXX` hex in either case, or the literal lower-case `superparty`. Exported so a validator of the bare suffix composes from it instead of parsing the anchored pattern; `PARTY_ID_RE` is built from the same string, so the two cannot drift.
<!-- /dict -->

### `SERVICE_ID_RE` (constant)

<!-- dict:eidr_core.ids.SERVICE_ID_RE -->
Defined in `src/eidr_core/ids/__init__.py`.

**Value** `SERVICE_ID_RE = re.compile(r"^10\.5239/" + SERVICE_ID_SUFFIX + r"$")` -- Compiled, anchored service DOI pattern: `10.5239/` plus `SERVICE_ID_SUFFIX`. `is_valid_service_id` wraps it.
<!-- /dict -->

### `SERVICE_ID_SUFFIX` (constant)

<!-- dict:eidr_core.ids.SERVICE_ID_SUFFIX -->
Defined in `src/eidr_core/ids/__init__.py`.

**Value** `SERVICE_ID_SUFFIX = r"[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}"` -- Regex source string for the part after `10.5239/`: `XXXX-XXXX`, hex, either case, no check character. Compose from it rather than parsing `SERVICE_ID_RE`.
<!-- /dict -->

### `USER_ID_RE` (constant)

<!-- dict:eidr_core.ids.USER_ID_RE -->
Defined in `src/eidr_core/ids/__init__.py`.

**Value** `USER_ID_RE = re.compile(r"^10\.5238/" + USER_ID_SUFFIX + r"$")` -- Compiled, anchored user DOI pattern: `10.5238/` plus `USER_ID_SUFFIX`. `is_valid_user_id` wraps it.
<!-- /dict -->

### `USER_ID_SUFFIX` (constant)

<!-- dict:eidr_core.ids.USER_ID_SUFFIX -->
Defined in `src/eidr_core/ids/__init__.py`.

**Value** `USER_ID_SUFFIX = r"[0-9a-zA-Z_#.\-()]{3,32}"` -- Regex source string for the username after `10.5238/`: 3 to 32 characters from `0-9 a-z A-Z _ # . - ( )`, transcribed from schema 2.7.0 `userDOIType`. python-sdk builds its user-ID check from this string.
<!-- /dict -->

## `eidr_core.inheritance`

<!-- dict-module:eidr_core.inheritance -->
Source `src/eidr_core/inheritance/__init__.py`. Public names: 6 functions, 1 class, 6 constants (declared by `__all__`).
<!-- /dict-module -->

**Purpose.** Builds the FULL record of a child record (Season, Episode, Edit, Clip, Manifestation) from its self-defined record plus its parent's full record: which fields inherit, the four system-generated Season and Episode title patterns, and a per-field provenance map (`self`, `inherited`, `system`). The rules are the operator's (2026-08-30), taken from the schema's `inheritedBaseObjectInfoGroup`, and the module states that nothing in the portfolio may reimplement, reinterpret or extend them, because inheritance must give the same full record through every code path. It was seeded from XML_to_JSON's exporter and shared with BMR-Review (register R13, accepted 2026-08-29). One policy sits behind two adapters: `build_full_base` for registry-JSON `BaseObjectData` dicts and `build_full_record` for record objects addressed by attribute; eidr-core imports neither consumer's model.

**Use it when.**
* You score, compare or export a child record. Compare the FULL form: a sparse self-defined child against a full registry candidate gets neither credit nor penalty on the fields it leaves empty.
* You decide whether a field is "present" for a merge rule that counts inherited values (`specs/merge-rules.md` section 4.2: rule 15 and rules 4 to 6).
* You need a Season or Episode system-generated title (`system_generated_title`), or need to know whether a title was user-supplied (`has_user_supplied_title`).
* You need the emptiness rule for "the record does not provide a value" (`is_absent`): `0` and `False` are values.
* You need to know whether a value was self-defined, inherited or system-generated (`provenance`, or the second item `build_full_base` returns).

**Do not use it when.**
* You only have the parent's SELF-defined record. Pass the parent's FULL record; inheritance is one hop, so build the parent first. Never walk to the tree root.
* The record is a Series, Compilation or other non-child type. The builders return Self as Full and ignore any parent, so calling is harmless but inherits nothing (`build_full_record` still stamps `self_defined` on elements and attaches a provenance map).
* You want `ExtraObjectMetadata`, `AlternateResourceName`, `Description`, `AlternateID`, `Administrators` or `RegistrantExtra` to flow down. They never inherit, by rule.
* Do not keep a local list of inheritable fields, a local emptiness test or local title patterns: import `INHERITABLE_FIELDS`, `is_absent` and `system_generated_title`. After a `TitleConstructionError`, use `exc.partial`; do not re-derive inheritance through a second path.

**Used by.**
<!-- dict-usedby:eidr_core.inheritance -->
Scan of 2026-10-02; regenerated at each release from the consumer trees.
* **BMR-Review**: `build_full_record`, `provenance`, `RECORD_ATTRS`, `TitleConstructionError`, (the module)
* **XML_to_JSON**: `build_full_base`, `INHERITABLE_FIELDS`, `TitleConstructionError`
<!-- /dict-usedby -->

**Specs.** `specs/merge-rules.md` section 4.2 fixes that an inherited value counts as present for rule 15 (ApproximateLength) and rules 4 to 6 (release date), so the merge engine needs the full record this module builds. `specs/golden-pairs.md` fixes that a fixture record may carry a `provenance` block, which a loader must set on the attribute `provenance()` reads, and that a record without one is self-asserted.

### `build_full_base`

<!-- dict:eidr_core.inheritance.build_full_base -->
```python
def build_full_base(self_base: dict, parent_base: dict | None, creation_type: str, extra: dict | None = None) -> tuple[dict, dict[str, str]]
```

Defined in `src/eidr_core/inheritance/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `self_base` | `dict` | required | The child's SELF-defined `BaseObjectData` (registry JSON, canonical field names as keys). Deep-copied, never modified. `None` is treated as `{}`. |
| `parent_base` | `dict \| None` | required | The parent's FULL `BaseObjectData`, not its self-defined one. `None` or `{}` means no parent, and Self is returned as Full. |
| `creation_type` | `str` | required | The child's creation type, exact spelling (`'Season'`, `'Episode'`, ...). A type outside `CHILD_TYPES` returns Self as Full and ignores the parent. |
| `extra` | `dict \| None` | `None` | Title inputs only: `SequenceNumber` (Season), `DistributionNumber` (Episode), `ReleaseDate` (fallback for both; when non-empty it outranks the child's own `ReleaseDate`). The numbers are read ONLY from here, never from `self_base`, so a missing `SequenceNumber` or `DistributionNumber` means the numbered pattern cannot fire. A missing or empty `ReleaseDate` falls back to the child's own `self_base["ReleaseDate"]`. |

**Returns** `tuple[dict, dict[str, str]]` -- `(full_base, provenance)`: a new dict, and a map from each field populated in the result to `'self'`, `'inherited'` or `'system'`. A system-generated ResourceName that was carried over rather than built here has no entry.
<!-- /dict -->

**Does.** Builds a child's full registry-JSON `BaseObjectData` from its self-defined one plus its parent's full one. For a Season or Episode without a user-supplied ResourceName it first generates the title from the number or date in `extra` (or the child's own `ReleaseDate`), then copies from the parent every `INHERITABLE_FIELDS` value the child lacks (per `is_absent`). Edit, Clip and Manifestation inherit the parent's ResourceName unless they carry a user-supplied one; Season and Episode never inherit it. Raises `TitleConstructionError`, after inheritance has run and with `partial` and `provenance` attached, when a Season or Episode title cannot be built (parent untitled, or the child has no number and no date of its own).

**Notes.** A Season or Episode with no number and no date of its own does NOT borrow the parent's date for its title; it raises, because every sibling would otherwise get the same title. The generated element is `{"Title": ..., "TitleClass": "series numeric" or "season numeric", "SystemGenerated": "true"}`. `ExtraObjectMetadata` belongs to the caller and is not touched.

### `build_full_record`

<!-- dict:eidr_core.inheritance.build_full_record -->
```python
def build_full_record(self_rec: Any, parent_full: Any, creation_type: str | None = None, *, attrs: dict[str, str] | None = None) -> Any
```

Defined in `src/eidr_core/inheritance/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `self_rec` | `Any` | required | The child's self-defined record object, of any class, read and written by attribute. Deep-copied; the original is not modified. |
| `parent_full` | `Any` | required | The parent's FULL record object, with the same attribute names. `None` means no parent, and Self is returned as Full. |
| `creation_type` | `str \| None` | `None` | The child's creation type. `None` falls back to `self_rec.creation_type`. Only `CHILD_TYPES` inherit. |
| `attrs` | `dict[str, str] \| None` | `None` (keyword-only) | Map from canonical EIDR field name to attribute name. It REPLACES `RECORD_ATTRS` (no merge); `None` or `{}` means `RECORD_ATTRS`. Titles (`titles`), credits (`directors`, `actors`) and the title inputs use fixed attribute names, not this map. |

**Returns** `Any` -- A deep copy of `self_rec` with inherited values filled in and the provenance map attached as the attribute `eidr_provenance` (read it with `provenance()`).
<!-- /dict -->

**Does.** Builds a child's full record object from its self-defined one and its parent's full record, by the `build_full_base` policy. Title inputs come from the child's `sequence_number`, `distribution_number` and `release_date` attributes; a generated title is a deep copy of the parent's first title element with `text`, `title_class`, `system_generated=True`, `self_defined=False` and `is_resource=True` set where the class has them. Elements of the list attributes get `self_defined` stamped (False when inherited, otherwise `not system_generated`, and an existing explicit False is kept), so running it again over an already-built cached record does not promote inherited values to self-defined. Raises `TitleConstructionError` as `build_full_base` does, after inheritance, with `partial` and `provenance` attached.

**Notes.** When the record's `titles` attribute is missing or `None`, title handling is skipped entirely: no title is generated and no `TitleConstructionError` is raised, unlike `build_full_base`. A field whose attribute is missing on either record is skipped silently. If the object cannot take the `eidr_provenance` attribute (slotted or frozen), the map is dropped silently and `provenance()` returns `{}`. Do not put `ResourceName` in a custom `attrs`: the field loop would then copy the parent's title into `exc.partial` when a Season or Episode title fails and `titles` is empty, and a system-generated title it does not replace would be reported as `'self'`.

### `has_user_supplied_title`

<!-- dict:eidr_core.inheritance.has_user_supplied_title -->
```python
def has_user_supplied_title(titles: Any) -> bool
```

Defined in `src/eidr_core/inheritance/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `titles` | `Any` | required | A ResourceName value: a list or tuple of title elements, or one element. A registry-JSON dict is generated when its `SystemGenerated` value reads `true` after `str()`, strip and lower-casing (`'true'`, `'TRUE'` or the bool `True`); an object when its `system_generated` attribute is truthy. An absent value (per `is_absent`) returns `False`. |

**Returns** `bool` -- `True` when at least one element is not system-generated; `False` when the value is absent or every element is system-generated.
<!-- /dict -->

**Does.** Tells whether a ResourceName value carries at least one title the submitter supplied, as opposed to a system-generated one. Only a user-supplied title blocks inheritance (Edit, Clip, Manifestation) or regeneration (Season, Episode). Anything unrecognised, including a bare string or a dict without `SystemGenerated`, counts as user-supplied, because preserving a title is the safe error.

### `is_absent`

<!-- dict:eidr_core.inheritance.is_absent -->
```python
def is_absent(value: Any) -> bool
```

Defined in `src/eidr_core/inheritance/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `value` | `Any` | required | Any field value. |

**Returns** `bool` -- `True` for `None`, an empty or whitespace-only string, or an empty `list`, `tuple`, `set` or `dict`; `False` for everything else, including `0`, `False` and empty containers of other types such as `frozenset()`.
<!-- /dict -->

**Does.** Applies the portfolio's emptiness rule, deciding whether a value is absent for inheritance purposes. It is policy, not a helper: a plain truthiness test would overwrite a real `0` or `False` with the parent's value and also refuse to inherit a legitimate `0`. Use it wherever "the record does not provide a value" must agree with what the builders decide.

### `provenance`

<!-- dict:eidr_core.inheritance.provenance -->
```python
def provenance(rec: Any) -> dict[str, str]
```

Defined in `src/eidr_core/inheritance/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `rec` | `Any` | required | A record object, normally one returned by `build_full_record`. Its `eidr_provenance` attribute is read; a missing attribute is not an error. |

**Returns** `dict[str, str]` -- A copy of the map from canonical field name to `'self'`, `'inherited'` or `'system'`; `{}` when the record carries no map.
<!-- /dict -->

**Does.** Returns the per-field provenance map `build_full_record` attached to a record. An empty map means "unknown", never "self-defined"; per the golden-pairs spec such a record is self-asserted throughout and never earns an inherited-value exemption. Golden-pair loaders set the same attribute from a fixture's `provenance` block.

### `system_generated_title`

<!-- dict:eidr_core.inheritance.system_generated_title -->
```python
def system_generated_title(parent_title: str, creation_type: str, *, sequence_number: Any = None, distribution_number: Any = None, release_date: Any = None) -> tuple[str, str] | None
```

Defined in `src/eidr_core/inheritance/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `parent_title` | `str` | required | The parent's title text; for an Episode that is the Season's title, often itself generated. Stripped; empty or `None` returns `None`. |
| `creation_type` | `str` | required | `'Season'` or `'Episode'`, exact spelling. Any other value returns `None`. |
| `sequence_number` | `Any` | `None` (keyword-only) | Season number. Converted with `str()` and stripped; any non-empty value (`0` included) gives `Season <N>`. |
| `distribution_number` | `Any` | `None` (keyword-only) | Episode distribution number, handled the same way; gives `Episode <N>`. |
| `release_date` | `Any` | `None` (keyword-only) | Fallback when the number is empty, rendered verbatim as `[<date>]`. Pass the child's OWN date, never an inherited one. |

**Returns** `tuple[str, str] | None` -- `(title, title_class)`, with title_class `'series numeric'` for a Season and `'season numeric'` for an Episode (date forms included); `None` when no pattern can fire.
<!-- /dict -->

**Does.** Builds the registry's system-generated title for a Season or Episode from the parent's title plus a number or a date. The patterns are `<Series Title>: Season <N>`, `<Series Title> [<date>]`, `<Season Title>: Episode <N>` and `<Season Title> [<date>]`. `HouseSequence` is deliberately never consulted, because the registry's rules do not use it. Never raises; the builders turn a `None` into `TitleConstructionError`.

### `TitleConstructionError` (class)

<!-- dict:eidr_core.inheritance.TitleConstructionError -->
```python
class TitleConstructionError(ValueError)
```

Defined in `src/eidr_core/inheritance/__init__.py`.

| Field | Type | Default | Purpose |
|---|---|---|---|
| `partial` | `Any` | `None` | Set on the raised instance: the full base dict or record object with every inheritable field applied and no newly built title (a system-generated title the child already carried stays in place). `None` on the class itself. |
| `provenance` | `dict \| None` | `None` | Set on the raised instance: a copy of the provenance map for `partial`. `None` on the class itself. |
<!-- /dict -->

**Does.** Signals that a Season or Episode needed a generated title and the data could not build one. The operator's rule says this cannot happen, so it marks a data defect, not a normal branch; it subclasses `ValueError` and its message names the parent title, the numbers and the date it tried. Batch callers should catch it per record and either skip the row with the message as the reason or proceed with `exc.partial`, never re-derive inheritance another way.

### `CHILD_TYPES` (constant)

<!-- dict:eidr_core.inheritance.CHILD_TYPES -->
Defined in `src/eidr_core/inheritance/__init__.py`.

**Value** `CHILD_TYPES: frozenset[str] = frozenset({ "Season", "Episode", "Edit", "Clip", "Manifestation", })` -- The only creation types that inherit at all. Compilation is deliberately absent: it is a tree root with entries but no Parent ID. Both builders return Self as Full for any type not in this set.
<!-- /dict -->

### `INHERITABLE_FIELDS` (constant)

<!-- dict:eidr_core.inheritance.INHERITABLE_FIELDS -->
Defined in `src/eidr_core/inheritance/__init__.py`.

**Value** `INHERITABLE_FIELDS: frozenset[str] = frozenset({ "StructuralType", "Mode", "ReferentType", "ResourceName", # AlternateResour...` -- The 12 canonical `BaseObjectData` fields a child may inherit from its parent's full record. They are StructuralType, Mode, ReferentType, ResourceName, OriginalLanguage, VersionLanguage, AssociatedOrg, ReleaseDate, CountryOfOrigin, Status, ApproximateLength, Credits. Of the two title fields only ResourceName inherits. Import this set rather than keeping a local list.
<!-- /dict -->

### `NEVER_INHERITED` (constant)

<!-- dict:eidr_core.inheritance.NEVER_INHERITED -->
Defined in `src/eidr_core/inheritance/__init__.py`.

**Value** `NEVER_INHERITED: frozenset[str] = frozenset({ "ID", # identity "Administrators", # carries the Registrant — schema commen...` -- Fields a child never inherits, listed explicitly so none is re-added by mistake. They are ID (identity), Administrators (carries the Registrant), AlternateID (a parent's alt IDs are not the child's), AlternateResourceName (only the primary title inherits), Description and RegistrantExtra. All of `ExtraObjectMetadata` is also never inherited, but it is handled structurally, not listed here.
<!-- /dict -->

### `RECORD_ATTRS` (constant)

<!-- dict:eidr_core.inheritance.RECORD_ATTRS -->
Defined in `src/eidr_core/inheritance/__init__.py`.

**Value** `RECORD_ATTRS: dict[str, str] = { "StructuralType": "structural_type", "Mode": "mode", "ReferentType": "referent_type",...` -- Default map from canonical EIDR field name to record attribute name for `build_full_record`. Entries: StructuralType `structural_type`, Mode `mode`, ReferentType `referent_type`, OriginalLanguage `original_languages`, VersionLanguage `version_languages`, AssociatedOrg `assoc_orgs`, ReleaseDate `release_date`, CountryOfOrigin `countries`, ApproximateLength `length_minutes`, Status `status`. ResourceName and Credits are not in it; they use the fixed attributes `titles`, `directors` and `actors`. A naming convention, not an import of any consumer model.
<!-- /dict -->

### `TITLE_EXEMPT_TYPES` (constant)

<!-- dict:eidr_core.inheritance.TITLE_EXEMPT_TYPES -->
Defined in `src/eidr_core/inheritance/__init__.py`.

**Value** `TITLE_EXEMPT_TYPES: frozenset[str] = frozenset({"Season", "Episode"})` -- The child types that never inherit the parent's title and get a system-generated one instead. The builders branch on this set.
<!-- /dict -->

### `TITLE_INHERITING_TYPES` (constant)

<!-- dict:eidr_core.inheritance.TITLE_INHERITING_TYPES -->
Defined in `src/eidr_core/inheritance/__init__.py`.

**Value** `TITLE_INHERITING_TYPES: frozenset[str] = frozenset({"Edit", "Clip", "Manifestation"})` -- The child types that inherit the parent's ResourceName verbatim. Documentation only: it equals `CHILD_TYPES - TITLE_EXEMPT_TYPES`, and the code branches on `TITLE_EXEMPT_TYPES`, never on this set.
<!-- /dict -->

## `eidr_core.normalize`

<!-- dict-module:eidr_core.normalize -->
Source `src/eidr_core/normalize/__init__.py`. Public names: 13 functions (declared by `__all__`).
<!-- /dict-module -->

**Purpose.** Level-1 normalisation primitives for de-dup comparison: Unicode and diacritic folding, a punctuation-blind comparison key, title and name normalisers with numeral folding and word aliasing, country and language code normalisers, date and duration parsers, and the Registrant Extra flag parser. The module moved from BMR-Review on 2026-07-28 (`specs/unified-scoring.md` migration step 1), and BMR-Review keeps a re-export shim. The comparison normalisers are lossy on purpose (case, articles and punctuation go) so that harmless cross-source variation is neutralised before fuzzy comparison. `sanitize_field` is a different job, transport safety, extracted from EIDR MCP. The module also re-exports `canon_country`, which is `eidr_core.codes.normalize_country_code` (upper-case canonical, `SU` -> `SUHH`, keeps `XX`).

**Use it when.**
* You compare titles or names across sources: `norm_title`, `norm_name`, or `cmp_key` for a punctuation-blind equality key.
* You compare country or language codes: `norm_country`, `norm_lang`.
* You parse sheet or registry dates and durations for comparison: `parse_date`, `days_between`, `parse_minutes`.
* You read the `AL:Pro` and `RD:Pro` estimate flags: `parse_registrant_extra`.
* You write text into a TSV file or a PostgreSQL COPY stream: `sanitize_field`.

**Do not use it when.**
* You need the value to store, display or emit. The comparison normalisers destroy information; keep the original for output. Never compare on `sanitize_field` output, and never write `norm_*` output as data.
* You need canonical or display ordering: use `eidr_core.ordering`.
* You need a country code to store: use `canon_country` / `eidr_core.codes.normalize_country_code`. `norm_country` returns lower-case and blanks `XX`.
* You need field scores: use `eidr_core.compare`, which calls these normalisers itself.
* Do not reimplement title or name folding, numeral folding or the alias table locally: call `norm_title` or `norm_name`. If you need more (a trailing article such as `Matrix, The`, numerals past twelve), propose widening them here.

**Used by.**
<!-- dict-usedby:eidr_core.normalize -->
Scan of 2026-10-02; regenerated at each release from the consumer trees.
* **BMR-Review**: `ascii_fold`, `cmp_key`, `days_between`, `nfkc`, `norm_code`, `norm_country`, `norm_lang`, `norm_name`, `norm_title`, `parse_date`, `parse_minutes`, `parse_registrant_extra`
* **De-Dupe UI**: `ascii_fold`, `cmp_key`, `norm_code`, `norm_country`, `norm_lang`, `norm_name`, `norm_title`, `parse_date`, `parse_minutes`, `parse_registrant_extra`
* **eidr-wikidata**: `norm_title`, `sanitize_field`
* **LanguageTool**: `norm_title`
* **MCP**: `sanitize_field`
<!-- /dict-usedby -->

**Specs.** `specs/unified-scoring.md` names this module, with the normalized-record spec, as layer L1 (normalisation) of the one scoring engine. `specs/normalized-record.md` section 3.x defines "casefold" as Unicode `str.casefold()`, which `cmp_key` and the title and name normalisers use.

### `ascii_fold`

<!-- dict:eidr_core.normalize.ascii_fold -->
```python
def ascii_fold(s: str) -> str
```

Defined in `src/eidr_core/normalize/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `s` | `str` | required | Text to fold. `None`, `''` and any other falsy value are returned unchanged. A non-string such as an `int` raises `TypeError`. |

**Returns** `str` -- The folded text, case preserved; not lower-cased and not whitespace-normalised. A falsy input comes back as itself, so `None` returns `None` despite the annotation.
<!-- /dict -->

**Does.** Folds Latin diacritics and ligatures to ASCII so they do not count as differences. It maps a fixed ligature table (æ -> ae, ß -> ss, ø -> o), applies NFKD, then drops every combining mark (é -> e). Because combining marks are dropped in every script, some non-Latin letters change too (Cyrillic й -> и, Japanese が -> か), although the docstring says non-Latin scripts are left intact. NFKD also folds compatibility forms (full-width `Ａ` -> `A`, `²` -> `2`).

### `cmp_key`

<!-- dict:eidr_core.normalize.cmp_key -->
```python
def cmp_key(s: str) -> str
```

Defined in `src/eidr_core/normalize/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `s` | `str` | required | Text to key. A falsy value returns `''`. A non-string such as an `int` raises `TypeError`. |

**Returns** `str` -- The key: ASCII-folded, Unicode-casefolded, with every non-word character and every underscore removed, spaces included (`'The Matrix: Reloaded!'` -> `'thematrixreloaded'`).
<!-- /dict -->

**Does.** Builds the canonical comparison key; equal keys are treated as a match. It does not strip articles, fold numerals or apply aliases, so use `norm_title` or `norm_name` when those matter. The case folding is Unicode `casefold()`, matching the XML-to-JSON converter.

### `days_between`

<!-- dict:eidr_core.normalize.days_between -->
```python
def days_between(a_ymd, b_ymd)
```

Defined in `src/eidr_core/normalize/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `a_ymd` | - | required | A `(year, month, day)` tuple of ints, as in the second item `parse_date` returns. |
| `b_ymd` | - | required | The other `(year, month, day)` tuple. Order does not matter. |

**Returns** not annotated -- An `int`: the absolute difference in days.
<!-- /dict -->

**Does.** Returns the absolute number of days between two `(year, month, day)` tuples. Raises `TypeError` if either is `None`, and `ValueError` for an impossible date, which `parse_date` can hand back for `YYYY-MM-DD` input because it does not validate that form. Check both tuples before calling.

### `nfkc`

<!-- dict:eidr_core.normalize.nfkc -->
```python
def nfkc(s: str) -> str
```

Defined in `src/eidr_core/normalize/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `s` | `str` | required | Text. `None` and `''` are returned unchanged; any other non-`str` value is converted with `str()` first (numeric titles and episode numbers arrive as `int`). |

**Returns** `str` -- The NFKC-normalised string, or the input itself when it is `None` or `''` (so despite the annotation it can return `None`).
<!-- /dict -->

**Does.** Applies Unicode NFKC normalisation, folding compatibility forms such as full-width letters and ligature code points. It does not fold case or strip diacritics. `norm_title`, `norm_name` and `norm_code` call it first.

### `norm_code`

<!-- dict:eidr_core.normalize.norm_code -->
```python
def norm_code(s: str) -> str
```

Defined in `src/eidr_core/normalize/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `s` | `str` | required | A country or language code. A falsy value returns `''`. |

**Returns** `str` -- The code NFKC-normalised, stripped and casefolded (so lower-case); `''` for the wildcards `xx`, `und`, `zz`, `none` and `null` in any case.
<!-- /dict -->

**Does.** Normalises a country or language code for comparison, treating wildcard and unknown codes as absent. It applies no crosswalk and no subtag split: use `norm_country` for countries and `norm_lang` for languages.

### `norm_country`

<!-- dict:eidr_core.normalize.norm_country -->
```python
def norm_country(s: str) -> str
```

Defined in `src/eidr_core/normalize/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `s` | `str` | required | A country code: alpha-2, alpha-4, an M49 region number, or anything else `codes.normalize_country_code` passes through. A falsy value returns `''`. |

**Returns** `str` -- The lower-case canonical code, with an obsolete alpha-2 rewritten to alpha-4 (`'SU'` -> `'suhh'`); `''` for empty input and for the wildcards, `XX` included.
<!-- /dict -->

**Does.** Normalises a country code for field comparison, adding the obsolete alpha-2 to alpha-4 crosswalk to `norm_code`. Code-set variants of one country therefore compare equal (`SU` and `SUHH`). The crosswalk is kept out of `norm_code` because that is shared with language codes, and `su` is the language Sundanese, not the USSR. For a code to store or emit, use `canon_country` / `eidr_core.codes.normalize_country_code`, which is upper-case and keeps `XX`.

### `norm_lang`

<!-- dict:eidr_core.normalize.norm_lang -->
```python
def norm_lang(s: str) -> str
```

Defined in `src/eidr_core/normalize/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `s` | `str` | required | A language tag such as `en-US` or `zh-Hans`. A falsy value returns `''`. |

**Returns** `str` -- The primary subtag, lower-case (`'en-US'` -> `'en'`); `''` for empty input and when the WHOLE tag is one of the wildcards `und`, `xx`, `zz`, `none` or `null`.
<!-- /dict -->

**Does.** Reduces a language tag to its lower-case primary subtag for comparison. It splits only on `-`, so `en_US` stays `en_us`. It does not map between ISO 639 code lengths, so `eng` and `en` stay different. The wildcard test runs on the whole tag before the split, so `und-Latn` returns `'und'`, not `''`.

### `norm_name`

<!-- dict:eidr_core.normalize.norm_name -->
```python
def norm_name(s: str) -> str
```

Defined in `src/eidr_core/normalize/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `s` | `str` | required | A personal or organisation name. A falsy value returns `''`; another non-`str` value is stringified. |

**Returns** `str` -- Lower-case, ASCII-folded tokens joined by single spaces, with `Last, First` inverted (`'Smith, John'` -> `'john smith'`).
<!-- /dict -->

**Does.** Normalises a personal or organisation name for comparison. Text with exactly one comma is read as `Last, First` and inverted when the part after the comma is non-empty. Then `&` and `+` become `and`, other punctuation becomes a space, Roman numerals i to xii and number words one to twelve become digits, and each token passes through `alias_name` (ordinals, the CT list and the T nickname list, so `bill` -> `william`). A single letter beside an ampersand, or a one-letter name, is kept verbatim (`A&E` -> `a and e`), and no article is stripped.

**Notes.** Generational suffixes fold too (`John Smith III` -> `john smith 3`). Since 0.45.0 the alias map is idempotent across its two domains, so `Jacque Brel` and `Jacques Brel` normalise alike.

### `norm_title`

<!-- dict:eidr_core.normalize.norm_title -->
```python
def norm_title(s: str, strip_articles: bool = True) -> str
```

Defined in `src/eidr_core/normalize/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `s` | `str` | required | A title. A falsy value (`0` included) returns `''`; another non-`str` value is stringified. |
| `strip_articles` | `bool` | `True` | `True` drops one leading article (from a fixed English, French, Spanish, German and Italian list), but only when the title has more than one token, so a title that is only an article (`'The'`) is kept, and never when the first token is an initial beside an ampersand. `False` keeps it. |

**Returns** `str` -- Lower-case, ASCII-folded tokens joined by single spaces (`'The Matrix'` -> `'matrix'`).
<!-- /dict -->

**Does.** Normalises a title for comparison, folding Unicode, case, punctuation, numerals and common word variants. The steps are NFKC, ASCII fold, casefold, curly quotes to `'`, `&` and `+` to `and`, other punctuation to spaces, then per token Roman numerals i to xii and number words one to twelve to digits and `alias_title` (ordinals and the CT list), so `Part II`, `Part 2` and `Part Two` agree. A letter beside an ampersand stays verbatim and is never taken for an article (`A&E Networks` -> `a and e networks`).

**Notes.** Numeral folding and aliasing run before the article check, so two listed articles are never stripped: Italian `i` becomes `1` (`I Promessi Sposi` -> `1 promessi sposi`) and `lo` becomes `low`. Apostrophes split words (`Don't` -> `don t`, `L'Amour` -> `amour`). A trailing article (`Matrix, The`) is not moved back to the front.

### `parse_date`

<!-- dict:eidr_core.normalize.parse_date -->
```python
def parse_date(raw)
```

Defined in `src/eidr_core/normalize/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `raw` | - | required | A date: `YYYY`, `YYYY-MM`, `YYYY-MM-DD` (anything may follow, such as a time), `M/D/YYYY` or `D/M/YYYY`. Stringified and stripped. `None` returns `(None, None)`. |

**Returns** not annotated -- `(year, ymd)`: `year` an `int` or `None`, and `ymd` a `(year, month, day)` tuple of ints, or `None` when there is no day or the day cannot be read. `(None, None)` for anything unrecognised.
<!-- /dict -->

**Does.** Parses a date into a year and an optional `(year, month, day)` tuple. Slash dates are read US-style as M/D/YYYY unless the first field exceeds 12, then as D/M/YYYY, so `05/06/2007` is May 6. Slash dates are validated (an impossible one gives `(year, None)`), but `YYYY-MM-DD` is NOT, so `2006-13-45` returns `(2006, (2006, 13, 45))` and `days_between` will raise on it. `YYYY-MM` keeps only the year, and `YYYY/MM/DD` or month names are not recognised.

### `parse_minutes`

<!-- dict:eidr_core.normalize.parse_minutes -->
```python
def parse_minutes(raw)
```

Defined in `src/eidr_core/normalize/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `raw` | - | required | A duration: bare minutes (`'78'`, `78`, `'1.5'`), ISO 8601 (`'PT1H18M'`, with `D` days allowed), or a timecode `HH:MM`, `HH:MM:SS` or `HH:MM:SS:FF`. Stringified and stripped; `None` or empty returns `None`. |

**Returns** not annotated -- Minutes as a `float`, or `None` when the value cannot be parsed.
<!-- /dict -->

**Does.** Parses a duration into minutes. ISO durations count a day as 1440 minutes, support no years, months or weeks (`P78M` is read as 78 minutes), and drop fractional seconds entirely (`PT1H18M30.5S` gives 78.0). A two-part timecode is read as hours and minutes (`78:30` is 4710.0), and frames are ignored. Bare numbers go through `float()`, so `'nan'` and `'-5'` come back as numbers rather than `None`.

### `parse_registrant_extra`

<!-- dict:eidr_core.normalize.parse_registrant_extra -->
```python
def parse_registrant_extra(raw)
```

Defined in `src/eidr_core/normalize/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `raw` | - | required | The Registrant Extra text, for example `AL:Pro;RD:Pro;`. Stringified; a falsy value returns `(False, False)`. |

**Returns** not annotated -- `(length_estimated, date_estimated)`, two bools.
<!-- /dict -->

**Does.** Reads the length and release-date estimate flags from a Registrant Extra value. `AL:Pro` means the approximate length is estimated, `RD:Pro` means the release date is. It is a case-insensitive substring test, so the flags may appear anywhere and in any order; other tokens such as `RT:Podcast;` are ignored.

### `sanitize_field`

<!-- dict:eidr_core.normalize.sanitize_field -->
```python
def sanitize_field(s) -> str
```

Defined in `src/eidr_core/normalize/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `s` | - | required | Any value. `None` returns `''`; anything else is converted with `str()`. |

**Returns** `str` -- The value on one line: stripped, NUL bytes removed, and tab, CR, LF and every other C0 control character replaced by a space; `''` for `None`, empty or whitespace-only input. Never `None`.
<!-- /dict -->

**Does.** Makes a text value safe to carry through a TSV file or PostgreSQL COPY stream without changing what it says. It strips surrounding whitespace, removes NUL bytes (PostgreSQL rejects them), and replaces tab, CR, LF and every other C0 control character with a space. Apply it last, on the way out, and never compare on its output.

**Notes.** It escapes nothing: backslashes, quotes and commas pass through, so CSV quoting and COPY's own backslash escaping stay the writer's job. It does not collapse runs of spaces, and because stripping runs first, a control character that `str.strip()` does not treat as whitespace (for example `\x01`) becomes a leading or trailing space when it sits at either end. DEL (0x7F) and C1 controls (0x80 to 0x9F) pass through unchanged. EIDR MCP keeps two local copies by decision (register R6, extract-only); new code calls this one.

## `eidr_core.normalize.aliases`

<!-- dict-module:eidr_core.normalize.aliases -->
Source `src/eidr_core/normalize/aliases.py`. Public names: 2 functions, 1 constant (declared by `__all__`).
<!-- /dict-module -->

**Purpose.** Token-level word aliasing for `norm_title` and `norm_name`: it maps one word to a canonical form before string-distance comparison. The source is the third-party WordAlias list, packaged once portfolio-wide as `src/eidr_core/normalize/data/word_alias.csv`, plus the spelled ordinals `first` to `twelfth`. The list has two domains, CT (titles, company terms, international name variants) and T (personal-name nicknames), and each domain's map is resolved so that chains and cycles collapse to one representative and applying an alias twice is stable. The name map merges the two resolved maps without resolving again, so a chain that crosses domains is not followed (see `alias_name`). It moved from BMR-Review together with `normalize` on 2026-07-28.

**Use it when.**
* You tokenise text yourself and need the same per-token canonical form `norm_title` or `norm_name` would give.
* You need the spelled-ordinal to digit map (`ORDINALS`).

**Do not use it when.**
* You have a whole title or name: call `norm_title` or `norm_name`, which tokenise, fold numerals and handle `&` and `+` around these lookups.
* Your tokens are not already lower-case: lookups are exact and case-sensitive and the list is lower-case, so `First` comes back unchanged.
* You want symbol aliases: entries whose word or target is not alphanumeric (`&`, `+`, `b.v.`) are dropped from the maps; `normalize` turns `&` and `+` into `and` itself.
* Do not copy `word_alias.csv` into your project or keep a local nickname table; propose additions to the CSV here. The one held copy is De-Dupe UI's, for its JavaScript engine spec, and it is pinned and drift-checked against this file.

**Used by.**
<!-- dict-usedby:eidr_core.normalize.aliases -->
Scan of 2026-10-02; regenerated at each release from the consumer trees.
* **BMR-Review**: `alias_name`, `alias_title`, `ORDINALS`
<!-- /dict-usedby -->

### `alias_name`

<!-- dict:eidr_core.normalize.aliases.alias_name -->
```python
def alias_name(tok)
```

Defined in `src/eidr_core/normalize/aliases.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `tok` | - | required | One token, already casefolded and free of punctuation. Matched exactly and case-sensitively. |

**Returns** not annotated -- The canonical form (a digit string for a spelled ordinal), or `tok` unchanged when no map holds it.
<!-- /dict -->

**Does.** Returns the canonical form of a personal or organisation name token. It checks the ordinals, then the CT and T lists combined (T wins on a clash), so `bill` -> `william` and `y` -> `and`. The CSV is read once and cached for the process; if the file is missing the CSV maps are silently empty and every token except a spelled ordinal comes back unchanged.

**Notes.** Since 0.45.0 the name map is CT + T resolved as one map, so it is idempotent across domains (`jacque` and `jacques` both give `jacob`). Before, a T entry whose target was itself a CT word stopped one step short. `tests/test_normalize_aliases.py` pins both maps.

### `alias_title`

<!-- dict:eidr_core.normalize.aliases.alias_title -->
```python
def alias_title(tok)
```

Defined in `src/eidr_core/normalize/aliases.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `tok` | - | required | One token, already casefolded and free of punctuation. Matched exactly and case-sensitively. |

**Returns** not annotated -- The canonical form (a digit string for an ordinal), or `tok` unchanged when no map holds it.
<!-- /dict -->

**Does.** Returns the canonical form of a title or company token. It checks the ordinals and the CT list only, with no nicknames, so `first` -> `1`, `10th` -> `10` and `lo` -> `low`. Caching and missing-file behaviour are the same as `alias_name`.

### `ORDINALS` (constant)

<!-- dict:eidr_core.normalize.aliases.ORDINALS -->
Defined in `src/eidr_core/normalize/aliases.py`.

**Value** `ORDINALS = { "first": "1", "second": "2", "third": "3", "fourth": "4", "fifth": "5", "sixth": "6",...` -- Spelled ordinals `first` to `twelfth` (lower-case keys) mapped to the digit strings `'1'` to `'12'`. Both alias functions check it before the CSV lists. Numeric ordinals such as `10th` come from the CT list; Roman numerals and number words are folded in `normalize`.
<!-- /dict -->

## `eidr_core.ordering`

<!-- dict-module:eidr_core.ordering -->
Source `src/eidr_core/ordering/__init__.py`. Public names: 10 functions (declared by `__all__`).
<!-- /dict-module -->

**Purpose.** Sort-key functions for the canonical order and the display order of an EIDR record's titles and Alternate IDs. They implement the ratified normalized-record spec (§3.x casefold, §4.1 titles, §4.2 Alt IDs) and the two API Shim handoff documents. Extracted on 2026-08-02 (register R2) so that XML_to_JSON's star-mode export and BMR-Review's `render_record` stop maintaining the same rules in parallel. The functions take plain values (text, class, type, domain, value), never model objects, and only the keys are casefolded: the values you emit keep their case.

**Use it when.** You sort titles or Alt IDs:
* Titles, for display or canonical serialization: `sorted(titles, key=lambda t: title_sort_key(t.text, t.title_class, t.is_resource))`.
* Alt IDs in canonical order (export, hashing, comparison): `altid_canonical_key`. For a source that already merges Type and Domain into one Kind column: `altid_collapsed_canonical_key`.
* Alt IDs for a human: drop the entries where `is_shortdoi(...)` is true, then stable-sort by `altid_display_key`.
* Any place that needs the casefold key rule: `ck`.

**Do not use it when.** The job is one of these:
* An export or other canonical surface. Never use `altid_display_key` or ShortDOI filtering there: IMDb-first and ShortDOI suppression are display-only rules. Canonical order keeps ShortDOI and has no IMDb preference.
* Scoring or matching. Order never changes evaluation; title-class weighting belongs to `eidr_core.compare`.
* Code lists, organisations and credits (spec §3.2-3.4): not covered here.
* Do not reimplement the three-bucket title rule, the kind composite or the ShortDOI test inline. Call these functions.
* Padded input. Keys are not whitespace-stripped, so `" IMDB"` is not IMDb. Strip values first if your source may pad them.

**Used by.**
<!-- dict-usedby:eidr_core.ordering -->
Scan of 2026-10-02; regenerated at each release from the consumer trees.
* **BMR-Review**: `altid_canonical_key`, `altid_collapsed_canonical_key`, `altid_display_key`, `altid_kind`, `is_shortdoi`, `title_bucket`, `title_sort_key`
* **XML_to_JSON**: `altid_collapsed_canonical_key`, `title_sort_key`
<!-- /dict-usedby -->

**Specs.** `specs/normalized-record.md` (§2 canonical versus display order, §3.x casefold, §4.1 titles, §4.2 Alt IDs). `specs/title-display-order.md` and `specs/altid-display-order.md` (the API Shim handoffs, each with a worked example the implementation is tested against).

### `altid_canonical_key`

<!-- dict:eidr_core.ordering.altid_canonical_key -->
```python
def altid_canonical_key(id_type, domain, value) -> tuple
```

Defined in `src/eidr_core/ordering/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `id_type` | - | required | Alt ID Type (`IMDB`, `ISAN`, `Proprietary`, ...). None or `""` allowed; other values go through `str()`. |
| `domain` | - | required | Alt ID Domain. None or `""` for named types. |
| `value` | - | required | The identifier value. |

**Returns** `tuple` -- `(casefold(type), casefold(domain), casefold(value))`: a 3-tuple of str, with the kind spread over the first two items.
<!-- /dict -->

**Does.** Returns the canonical sort key for one Alt ID: kind (Type, Domain), then value, all casefolded. IDs of the same kind sort next to each other, and ShortDOI is kept. Use it for export, hashing and comparison. Pure.

### `altid_collapsed_canonical_key`

<!-- dict:eidr_core.ordering.altid_collapsed_canonical_key -->
```python
def altid_collapsed_canonical_key(kind, value) -> tuple
```

Defined in `src/eidr_core/ordering/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `kind` | - | required | The source's single Kind column, with Type and Domain already merged (as in XML_to_JSON star mode). None allowed. |
| `value` | - | required | The identifier value. |

**Returns** `tuple` -- `(casefold(kind), casefold(value))`.
<!-- /dict -->

**Does.** Returns the canonical sort key for an Alt ID whose Type and Domain arrive as one Kind string. Pure. Its keys are 2-tuples and `altid_canonical_key`'s are 3-tuples, so never mix the two in one sort.

**Notes.** On the same data its order can differ from `altid_canonical_key`'s, because that key sorts by Type first and this one by the merged Kind string.

### `altid_display_key`

<!-- dict:eidr_core.ordering.altid_display_key -->
```python
def altid_display_key(id_type, domain, value) -> tuple
```

Defined in `src/eidr_core/ordering/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `id_type` | - | required | Alt ID Type. Only the Type decides IMDb-first (casefold equals `imdb`), so a `Proprietary` row with domain `imdb.com` is not moved up. |
| `domain` | - | required | Alt ID Domain. None or `""` for named types. |
| `value` | - | required | The identifier value. |

**Returns** `tuple` -- `(0 if the Type is IMDB else 1, casefold(type), casefold(domain), casefold(value))`.
<!-- /dict -->

**Does.** Returns the display sort key for one Alt ID: IMDb-typed entries first, then canonical kind and value. It does not drop ShortDOI. Filter with `is_shortdoi` first, then stable-sort with this key; display only, never for export or comparison.

### `altid_kind`

<!-- dict:eidr_core.ordering.altid_kind -->
```python
def altid_kind(id_type, domain) -> tuple
```

Defined in `src/eidr_core/ordering/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `id_type` | - | required | Alt ID Type. None counts as `""`. |
| `domain` | - | required | Alt ID Domain. None counts as `""`. |

**Returns** `tuple` -- `(casefold(type), casefold(domain))`.
<!-- /dict -->

**Does.** Returns the Alt ID kind composite (casefolded Type, casefolded Domain) used for grouping and sorting. A missing half becomes `""`, so domain-only entries group under `("", domain)` and sort before named Types, as the spec intends. It is an ordering key, not a rule-6 identity Kind.

### `ck`

<!-- dict:eidr_core.ordering.ck -->
```python
def ck(s) -> str
```

Defined in `src/eidr_core/ordering/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `s` | - | required | Any value. None becomes `""`; anything else goes through `str()`. |

**Returns** `str` -- `str(s).casefold()`, or `""` for None.
<!-- /dict -->

**Does.** Returns the casefolded sort key for a value, treating None as an empty string. This is the spec's §3.x rule: keys fold, emitted values keep their case. It does not strip whitespace or remove accents.

### `is_internal_class`

<!-- dict:eidr_core.ordering.is_internal_class -->
```python
def is_internal_class(title_class) -> bool
```

Defined in `src/eidr_core/ordering/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `title_class` | - | required | The title's Title Class. None allowed (gives False). |

**Returns** `bool` -- True only when the class casefolds to exactly `internal`.
<!-- /dict -->

**Does.** Tests whether a Title Class is `Internal` (casefolded, exact match). No whitespace trimming, so `" Internal"` gives False. An Internal title goes to bucket 2 unless it is the ResourceName.

### `is_resource_class`

<!-- dict:eidr_core.ordering.is_resource_class -->
```python
def is_resource_class(title_class) -> bool
```

Defined in `src/eidr_core/ordering/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `title_class` | - | required | The title's Title Class. None allowed (gives False). |

**Returns** `bool` -- True when the class casefolds to `release` or `resource`.
<!-- /dict -->

**Does.** Tests whether a Title Class marks the primary title, meaning it casefolds to `release` or `resource`. It serves sources that mark the ResourceName with a class instead of a structural flag. `title_bucket` uses it alongside `is_resource`.

**Notes.** Any title whose class is `Release` or `Resource` lands in bucket 0, an alternate title included. The title spec identifies the ResourceName by structure, never by class. If your source has the structural flag, pass `is_resource` and check whether your alternate titles can carry these class values.

### `is_shortdoi`

<!-- dict:eidr_core.ordering.is_shortdoi -->
```python
def is_shortdoi(id_type, domain) -> bool
```

Defined in `src/eidr_core/ordering/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `id_type` | - | required | Alt ID Type. None allowed. |
| `domain` | - | required | Alt ID Domain. None allowed. |

**Returns** `bool` -- True when the Type or the Domain casefolds to exactly `shortdoi`.
<!-- /dict -->

**Does.** Tests whether an Alt ID is a ShortDOI, by its Type or its Domain (casefolded, exact match). Use it to hide ShortDOI from display and to leave it out of evaluation. Never use it to filter an export: canonical and export forms keep ShortDOI.

### `title_bucket`

<!-- dict:eidr_core.ordering.title_bucket -->
```python
def title_bucket(title_class, is_resource: bool = False) -> int
```

Defined in `src/eidr_core/ordering/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `title_class` | - | required | The title's Title Class. None allowed. |
| `is_resource` | `bool` | `False` | True when the title is structurally the ResourceName (`md:ResourceName`). It outranks every class, `Internal` included. |

**Returns** `int` -- 0 for the ResourceName, 1 for a non-Internal alternate, 2 for an Internal alternate.
<!-- /dict -->

**Does.** Returns the three-bucket rank of a title: ResourceName, then non-Internal alternates, then Internal alternates. A title is bucket 0 when `is_resource` is True or its class is `release` or `resource`, and `Internal` never overrides that. Pure.

### `title_sort_key`

<!-- dict:eidr_core.ordering.title_sort_key -->
```python
def title_sort_key(text, title_class=None, is_resource: bool = False) -> tuple
```

Defined in `src/eidr_core/ordering/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `text` | - | required | The title text. None counts as `""`. |
| `title_class` | - | `None` | The title's Title Class, or None for no class. |
| `is_resource` | `bool` | `False` | True when the title is structurally the ResourceName. Puts it first whatever its class. |

**Returns** `tuple` -- `(bucket, casefold(text))`, where bucket is `title_bucket(title_class, is_resource)`.
<!-- /dict -->

**Does.** Returns the full title sort key: the three-bucket rank, then the casefolded text. Use it with a stable sort (`sorted`, `list.sort`) so that equal keys keep their input order. The same key serves display and canonical serialization of titles.

## `eidr_core.registry`

<!-- dict-module:eidr_core.registry -->
Source `src/eidr_core/registry/__init__.py`. Public names: 5 functions, 1 class, 3 constants (declared by `__all__`). Some are defined in, and also importable from: `src/eidr_core/registry/operation_status.py`.
<!-- /dict-module -->

**Purpose.** The one place the portfolio builds an EIDR Python SDK `Client` (package `eidr`, from PyPI) for live registry calls. Credential precedence, target selection (sandbox2 by default; production only by explicit choice), the superparty gate and the TLS trust default all live here, so there is one import path to audit for registry writes. It also re-exports `operation_status`, the parse that tells a rejected write from a pending one when the SDK's own token status cannot. Extracted from eidr-wikidata `eidr/registry_client.py` (2026-08-05, register R5); the SDK is imported lazily (extra `eidr-core[registry]`), and the operation-status half is stdlib only.

**Use it when.**
* A program reads from or writes to the live EIDR registry: `with get_registry_client(...) as client:`.
* You hold a `.secrets.json`-shaped dict and need SDK `Credentials`: `build_registry_credentials`.
* After a write you need the registry's actual verdict: `token_operation_status(token)` for a live SDK token, or `parse_operation_status` / `parse_operation_statuses` over a raw status-lookup body.

**Do not use it when.**
* You read EIDR records in bulk: the local PostgreSQL mirror is the read path, not the live registry.
* Do not construct `eidr.Client(...)` or `eidr.Credentials(...)` yourself; call `get_registry_client` and `build_registry_credentials`, or you lose the sandbox2 default, the system-trust TLS default, case-insensitive keys and whitespace stripping.
* Do not judge a write by `token.operation_result()` or `last_response.status_code` alone: as of SDK v1.1.1 a rejected write still reports as pending there. Use `token_operation_status`.
* Do not read `None` from the verdict functions as failure or as success: it means no verdict yet.
* EIDR MCP is exempt until the SDK grows mirror-ingest surfaces.

**Used by.**
<!-- dict-usedby:eidr_core.registry -->
Scan of 2026-10-02; regenerated at each release from the consumer trees.
* **BMR-Review**: `get_registry_client`
* **eidr-dq**: `build_registry_credentials`, `get_registry_client`
* **eidr-wikidata**: `build_registry_credentials`, `CODE_SUCCESS`, `DEFAULT_REGISTRY`, `get_registry_client`, `OperationStatus`, `parse_operation_status`, `parse_operation_statuses`, `token_operation_status`
* **LanguageTool**: `get_registry_client`, `parse_operation_status`, `token_operation_status`
* **python-tools**: `build_registry_credentials`, `get_registry_client`
<!-- /dict-usedby -->

### `build_registry_credentials`

<!-- dict:eidr_core.registry.build_registry_credentials -->
```python
def build_registry_credentials(secrets: dict | None = None) -> _SDKCredentials
```

Defined in `src/eidr_core/registry/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `secrets` | `dict \| None` | `None` | A loaded secrets dict (what `load_secrets` or `load_local` returns). Credentials come from its `registry` section, else its `eidr_registry` section, else `USER_ID` / `PARTY_ID` / `PASSWORD` at the top level. The section names `registry` and `eidr_registry` must be lower-case exactly; the keys inside a section, and the top-level keys, match case-insensitively. None, or none of those present: the SDK's `Credentials.load()` is used instead. |

**Returns** `_SDKCredentials` -- An SDK `eidr.Credentials` (`_SDKCredentials` is a type-checking alias for it). Built from the dict: `user_id`, `party_id` and `password` stripped of surrounding whitespace, and `base_url` from the section when present, else None. From the fallback: whatever `Credentials.load()` returns.
<!-- /dict -->

**Does.** Builds SDK `Credentials` from a project secrets dict, falling back to the SDK's own credential discovery. A section that is present but lacks `user_id`, `party_id` or `password` raises `KeyError`; an empty section counts as absent. Without the SDK installed it raises `ImportError`, even when `secrets` is None. The fallback `Credentials.load()` (environment variables, EIDR XML config, `~/.eidr/secrets.json` or `./.secrets.json`, AWS) raises `EIDRCredentialsNotFoundError` when nothing resolves and, in SDK 1.3.0, `EIDRCredentialAmbiguityError` when more than one source does.

**Notes.** The `registry` key must hold a dict: a string there (a target name, for example) raises `AttributeError`. Values are not validated: each goes through `str()`, so an empty string stays empty and a JSON null becomes the string `"None"`; nothing rejects either before the registry call. A section spelled in any other case (`Registry`) is not recognised: the top-level keys are tried, then the SDK fallback.

### `get_registry_client`

<!-- dict:eidr_core.registry.get_registry_client -->
```python
def get_registry_client(*, registry: str | Any = DEFAULT_REGISTRY, credentials: _SDKCredentials | None = None, secrets: dict | None = None, transport_config: Any | None = None, tracing: Any | None = None, enforce_superparty_gate: bool = True, writable: bool | None = None, trust: Literal["certifi", "system"] | None = "system") -> _SDKClient
```

Defined in `src/eidr_core/registry/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `registry` | `str \| Any` | `DEFAULT_REGISTRY` (keyword-only) | Target: a name (`sandbox2`, `sandbox1`, `production`, or another name the SDK accepts such as `sb2`, `prod`, `resolve`; any case), an `http://` or `https://` URL, or a ready SDK `Registry` (passed through). An unknown name raises `KeyError` from the SDK. |
| `credentials` | `_SDKCredentials \| None` | `None` (keyword-only) | Pre-built SDK `Credentials`. None: built from `secrets` by `build_registry_credentials`. |
| `secrets` | `dict \| None` | `None` (keyword-only) | Loaded secrets dict, used only when `credentials` is None. None: the SDK's `Credentials.load()` discovery. |
| `transport_config` | `Any \| None` | `None` (keyword-only) | SDK `TransportConfig` (timeouts, retries, TLS). Passed through untouched, so `trust` is then yours to set on it. None: one is built from `trust`. |
| `tracing` | `Any \| None` | `None` (keyword-only) | SDK `TraceSink`, or True for the SDK's default file sink, to capture request/response diagnostics. None: off. |
| `enforce_superparty_gate` | `bool` | `True` (keyword-only) | Keep the SDK's gate that refuses Party-administration calls (create, modify, delete party and similar) unless the credential's party is the superparty. Disable only after verifying the party-write policy with the registry operator. |
| `writable` | `bool \| None` | `None` (keyword-only) | Assert whether a URL target may be written: the factory builds a `CUSTOM` SDK `Registry` with this flag, which the SDK enforces. Only valid when `registry` is a URL string; with a name or a `Registry` it raises `ValueError`. None: no assertion. |
| `trust` | `Literal["certifi", "system"] \| None` | `"system"` (keyword-only) | TLS trust store when the factory builds the transport: `system` (the OS store, needed behind TLS inspection such as antivirus), `certifi`, or None (SDK default). Applied only if the installed SDK's `TransportConfig` accepts `trust` (1.3.0+). With your own `transport_config`, `system` only logs a warning if that config is on certifi with no `ca_bundle`. |

**Returns** `_SDKClient` -- A configured SDK `eidr.Client` (`_SDKClient` is a type-checking alias for it). Use it as a context manager (`with get_registry_client() as client:`) so its HTTP transport is closed.
<!-- /dict -->

**Does.** Builds the configured SDK `Client` that every portfolio program must use for live registry calls. Defaults are sandbox2 and OS-store TLS trust; production must be named explicitly. `writable=` with a non-URL target raises `ValueError` before the SDK is imported, a missing SDK raises `ImportError`, and credential errors come from `build_registry_credentials`. Credentials are always resolved, so this factory never builds an anonymous client, and it logs a WARNING (logger `eidr_core.registry`) when a supplied transport config has dropped system trust.

### `parse_operation_status`

<!-- dict:eidr_core.registry.parse_operation_status -->
```python
def parse_operation_status(raw_body: str | bytes | None, token: str = "") -> OperationStatus | None
```

Defined in `src/eidr_core/registry/operation_status.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `raw_body` | `str \| bytes \| None` | required | Raw XML of a registry status-lookup response (for example `token.last_response.raw_body`). Bytes are decoded as UTF-8 with bad bytes replaced. None or empty: the result is None. |
| `token` | `str` | `""` | Token value to attach when the matched block has no `<Token>`; a token found in the body always wins. It does NOT select which block is returned. |

**Returns** `OperationStatus | None` -- The first non-pending verdict in the body, or None when there is none. None means "still pending": never read it as success or failure.
<!-- /dict -->

**Does.** Extracts the registry's verdict on one write from a status-lookup body; None means no verdict yet. Only text from an `<OperationStatus>` tag onward is read, so the envelope's own success status, which comes first, can never be mistaken for the write's, and a block with code 2 or type `pending` (any case) is skipped. Parsing is a regex over the raw text: the tags must appear literally (no namespace prefix, no attributes), and `Details` text comes back without XML entities decoded (`&amp;` stays `&amp;`). For a paged batch body use `parse_operation_statuses`; this returns only the first verdict.

**Notes.** The match does not stop at `</OperationStatus>`. A block with no `<Code>`/`<Type>` pair of its own takes the NEXT block's verdict under its own token, and that next block is then not reported separately. A `<Token>` is captured only when it directly follows `<OperationStatus>`. The registry bodies seen so far always carry both, but this applies to `parse_operation_statuses` too.

### `parse_operation_statuses`

<!-- dict:eidr_core.registry.parse_operation_statuses -->
```python
def parse_operation_statuses(raw_body: str | bytes | None) -> list[OperationStatus]
```

Defined in `src/eidr_core/registry/operation_status.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `raw_body` | `str \| bytes \| None` | required | Raw XML of a registry status-lookup response. Bytes are decoded as UTF-8 with bad bytes replaced. None or empty: the result is an empty list. |

**Returns** `list[OperationStatus]` -- Every non-pending verdict in document order; empty when none has been reached. A token missing from the list is still in flight.
<!-- /dict -->

**Does.** Extracts every operation verdict from a paged status-lookup body, skipping blocks that still say pending. One lookup page can carry a verdict per operation (the envelope's `PageSize`, default 25), so batch writers must read them all, not just the first. Parsing rules are those of `parse_operation_status`; a block without `<Token>` gives an empty `token`.

### `token_operation_status`

<!-- dict:eidr_core.registry.token_operation_status -->
```python
def token_operation_status(token: Any) -> OperationStatus | None
```

Defined in `src/eidr_core/registry/operation_status.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `token` | `Any` | required | A live SDK `Token` returned by a write (for example `client.modify(record, immediate=False)`). The function calls `token.poll()`, then reads `token.last_response.raw_body` and `token.value`. |

**Returns** `OperationStatus | None` -- The registry's verdict, or None when there is no verdict yet or the poll failed. Treat None as "ask again later".
<!-- /dict -->

**Does.** Polls a live SDK write token and returns the registry's real verdict, or None when there is none yet. `token.poll()` makes a registry request, and any exception from it is swallowed, because this runs on the error path of write loops and must never end a run. If the poll fails, whatever `token.last_response` already holds is still parsed, so the verdict may come from an earlier response. Use it instead of `token.operation_result()`, which as of SDK v1.1.1 reports a rejected write as pending.

### `OperationStatus` (class)

<!-- dict:eidr_core.registry.OperationStatus -->
```python
@dataclass(frozen=True)
class OperationStatus
```

Defined in `src/eidr_core/registry/operation_status.py`.

| Field | Type | Default | Purpose |
|---|---|---|---|
| `code` | `int` | required | Registry status code. `CODE_SUCCESS` (0) is the only success; anything else is a rejection (for example 4, validation error). Never 2 when produced by the parse functions. |
| `type` | `str` | required | Registry status type text, stripped (for example `success`, `validation error`). |
| `details` | `str` | required | Registry `Details` text, stripped; empty when the registry omitted it. |
| `token` | `str` | `""` | Operation token from the block, or the one the caller supplied; empty if neither. |

| Method | Signature | Purpose |
|---|---|---|
| `is_success` | `def is_success() -> bool` (property) | True when `code` is 0. |
| `is_failure` | `def is_failure() -> bool` (property) | True when `code` is not 0: the registry REJECTED the write. Safe only because an instance never means pending; with `OperationStatus \| None`, branch on None first. |
<!-- /dict -->

**Does.** Holds the registry's reached verdict on one submitted write: code, type, details and token. It is a frozen dataclass (immutable and hashable), and `str()` gives `code=4 type=validation error details=...`, leaving out details when empty. There is deliberately no `is_pending`: "no verdict yet" is None from the parse functions, never an instance, so do not build one with code 2 yourself.

### `CODE_PENDING` (constant)

<!-- dict:eidr_core.registry.CODE_PENDING -->
Defined in `src/eidr_core/registry/operation_status.py`.

**Value** `CODE_PENDING = 2` -- The registry's in-block "still processing" code (observed 2026-10-01 on sandbox1 as Code 2 / Type pending). Not a verdict: the parse functions skip any block with this code or with type "pending", so it never appears in an `OperationStatus` they return.
<!-- /dict -->

### `CODE_SUCCESS` (constant)

<!-- dict:eidr_core.registry.CODE_SUCCESS -->
Defined in `src/eidr_core/registry/operation_status.py`.

**Value** `CODE_SUCCESS = 0` -- The registry's only success code. Any other code in an `OperationStatus` is a rejection with a reason; there is no partially-applied verdict.
<!-- /dict -->

### `DEFAULT_REGISTRY` (constant)

<!-- dict:eidr_core.registry.DEFAULT_REGISTRY -->
Defined in `src/eidr_core/registry/__init__.py`.

**Value** `DEFAULT_REGISTRY = "sandbox2"` -- Default `registry` for `get_registry_client`: Sandbox 2, which mirrors the production schema and is safe to write to. Production is never a default; pass `registry="production"` explicitly.
<!-- /dict -->

## `eidr_core.secrets_loader`

<!-- dict-module:eidr_core.secrets_loader -->
Source `src/eidr_core/secrets_loader/__init__.py`. Public names: 3 functions, 1 class (declared by `__all__`).
<!-- /dict-module -->

**Purpose.** The portfolio's single secrets loader: a local `.secrets.json` file or an AWS Secrets Manager secret, in one fixed resolution order with an AWS-to-local fallback. It replaced the variants eidr-dq, XML_to_JSON and eidr-wikidata each carried (register Phase 3 item 7, OVERLAPS row 12), keeping the best behaviour of each: a visible stderr warning on fallback, trailing-comma tolerance for the hand-edited file, and broad truthiness for the local-mode flag. boto3 is imported lazily (extra `eidr-core[aws]`), so local-only consumers do not need it.

**Use it when.**
* A program needs its secrets dict: write a thin wrapper that calls `load_secrets` with your historical environment-variable names, your default AWS secret name and a `validate` callable.
* You have an explicit file path (a `--secrets` option, for example): `load_local(path)`, or `load_secrets(path, ...)` to also run `validate`.
* You need registry credentials from the result: pass the dict to `eidr_core.registry.build_registry_credentials`.

**Do not use it when.**
* You want schema checks or section normalisation: those stay per program; pass them in as `validate`.
* Do not parse `.secrets.json` with `json.load` yourself, and do not call boto3 `get_secret_value` yourself; call `load_local` or `load_secrets`.
* You must not fall back from AWS to a local file: pass `aws_fallback_to_local=False`, or call `load_aws` directly.
* You expect a search for the file: there is none. A relative path resolves against the current working directory only.

**Used by.**
<!-- dict-usedby:eidr_core.secrets_loader -->
Scan of 2026-10-02; regenerated at each release from the consumer trees.
* **BMR-Review**: `load_local`
* **BMRtoAltID**: `load_secrets`, `SecretsError`
* **eidr-dq**: `load_secrets`, `SecretsError`
* **eidr-imdb**: `load_secrets`, `SecretsError`
* **eidr-wikidata**: `load_local`, `load_secrets`, `SecretsError`
* **LanguageTool**: `load_local`
* **python-tools**: `load_local`
* **XML_to_JSON**: `load_secrets`, `SecretsError`
<!-- /dict-usedby -->

### `load_aws`

<!-- dict:eidr_core.secrets_loader.load_aws -->
```python
def load_aws(secret_name: str, region: str, profile: str | None = None) -> dict
```

Defined in `src/eidr_core/secrets_loader/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `secret_name` | `str` | required | The secret to fetch, passed as `SecretId` to Secrets Manager `get_secret_value`. |
| `region` | `str` | required | AWS region for the Secrets Manager client, for example `us-west-2`. |
| `profile` | `str \| None` | `None` | AWS named profile for the boto3 session. None or empty: boto3's default session. |

**Returns** `dict` -- The secret parsed as JSON, from `SecretString`, else `SecretBinary` decoded as UTF-8. Not checked to be a dict.
<!-- /dict -->

**Does.** Fetches one secret from AWS Secrets Manager and parses it as JSON. Raises `SecretsError` when boto3 is not installed, on any botocore error (credentials, profile, access, missing secret), when the payload is empty, or (since 0.45.0) when it is not valid JSON.

### `load_local`

<!-- dict:eidr_core.secrets_loader.load_local -->
```python
def load_local(path: str | os.PathLike) -> dict
```

Defined in `src/eidr_core/secrets_loader/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `path` | `str \| os.PathLike` | required | Path to the JSON file; a relative path resolves against the current working directory. |

**Returns** `dict` -- The parsed JSON (normally a dict; not checked).
<!-- /dict -->

**Does.** Reads a local secrets JSON file, tolerating trailing commas before `}` or `]`. Raises `SecretsError` if the file does not exist, or is still not valid JSON after the trailing commas are removed; an unreadable file raises the underlying `OSError`. The file is read as UTF-8 with an optional byte-order mark (since 0.45.0), and bytes that are not UTF-8 raise `UnicodeDecodeError`. The comma repair runs only when the first parse fails, and it never touches string values (since 0.45.0; before, a password containing `,}` was altered).

### `load_secrets`

<!-- dict:eidr_core.secrets_loader.load_secrets -->
```python
def load_secrets(path: str | os.PathLike | None = None, *, default_secret_name: str, secret_name_envs: Sequence[str] = ("AWS_SECRET_ID",), region_envs: Sequence[str] = ("AWS_REGION",), default_region: str = "us-west-2", profile_envs: Sequence[str] = ("AWS_PROFILE",), default_profile: str | None = None, local_flag_envs: Sequence[str] = ("USE_LOCAL_SECRETS",), local_path_envs: Sequence[str] = ("SECRETS_PATH",), default_local_path: str = ".secrets.json", aws_fallback_to_local: bool = True, validate: Callable[[dict], Any] | None = None) -> dict
```

Defined in `src/eidr_core/secrets_loader/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `path` | `str \| os.PathLike \| None` | `None` | Explicit local file. When given it is loaded with `load_local` and nothing else is consulted (no flags, no AWS, no fallback). |
| `default_secret_name` | `str` | required (keyword-only) | AWS secret name used when none of `secret_name_envs` is set. |
| `secret_name_envs` | `Sequence[str]` | `("AWS_SECRET_ID",)` (keyword-only) | Environment variables checked in order for the AWS secret name; the first non-empty one wins. |
| `region_envs` | `Sequence[str]` | `("AWS_REGION",)` (keyword-only) | Environment variables checked in order for the AWS region. |
| `default_region` | `str` | `"us-west-2"` (keyword-only) | Region used when none of `region_envs` is set. |
| `profile_envs` | `Sequence[str]` | `("AWS_PROFILE",)` (keyword-only) | Environment variables checked in order for the AWS profile. |
| `default_profile` | `str \| None` | `None` (keyword-only) | Profile used when none of `profile_envs` is set; None means boto3's default session. |
| `local_flag_envs` | `Sequence[str]` | `("USE_LOCAL_SECRETS",)` (keyword-only) | Environment variables that select local mode when any is truthy (`1`, `true`, `yes`, `on`, any case). Keep it non-empty: its first name is used in an error message. |
| `local_path_envs` | `Sequence[str]` | `("SECRETS_PATH",)` (keyword-only) | Environment variables checked in order for the local file path, used by local mode and by the AWS fallback. Keep it non-empty, for the same reason. |
| `default_local_path` | `str` | `".secrets.json"` (keyword-only) | Local file path when none of `local_path_envs` is set; relative to the current working directory. |
| `aws_fallback_to_local` | `bool` | `True` (keyword-only) | On ANY failure of the AWS path, load the local file instead if it exists, with a stderr warning. False: raise `SecretsError`. |
| `validate` | `Callable[[dict], Any] \| None` | `None` (keyword-only) | Called as `validate(cfg)` before return; it may mutate the dict (to inject defaults, for example). Its return value is ignored; raise to reject, and the exception propagates unchanged. |

**Returns** `dict` -- The loaded secrets (the parsed JSON, after `validate` has run).
<!-- /dict -->

**Does.** Loads a program's secrets in the portfolio order: explicit path, local-mode flag, then AWS with local fallback. Local mode with a missing file raises `SecretsError` without trying AWS. On an AWS failure, with fallback on and the local file present, it prints a `[secrets WARNING]` line to stderr and loads that file (a bad file then raises `load_local`'s error); otherwise it raises `SecretsError` chained to the AWS error. Empty environment variables count as unset.

**Notes.** Each consumer passes its own historical environment-variable names (eidr-dq reads `DQ_SECRETS_PATH`, for example), so operator environments keep working; keep your names when you adopt it rather than switching to the defaults.

### `SecretsError` (class)

<!-- dict:eidr_core.secrets_loader.SecretsError -->
```python
class SecretsError(RuntimeError)
```

Defined in `src/eidr_core/secrets_loader/__init__.py`.
<!-- /dict -->

**Does.** Signals that secrets could not be loaded: missing or invalid local file, missing boto3, or an AWS failure. It is a plain `RuntimeError` subclass with no extra fields; the message says what failed, and the original exception is chained as `__cause__` where there is one. Through `load_secrets` every AWS problem arrives as `SecretsError` (or as a fallback to the file), but a direct `load_aws` call raises `json.JSONDecodeError` for a non-JSON payload, and `validate` rejections propagate unchanged.

## `eidr_core.vendor`

<!-- dict-module:eidr_core.vendor -->
Source `src/eidr_core/vendor/__init__.py`. Public names: 3 functions, 3 classes, 2 constants (declared by `__all__`).
<!-- /dict-module -->

**Purpose.** The one mechanism for copying eidr-core modules into a package that cannot depend on eidr-core. Two packages need it: the Python SDK (`eidr`, which eidr-core itself depends on) and the python-tools command-line scripts, which must run with only the SDK installed. It copies the listed modules from a pinned commit, rewrites their `eidr_core` imports to the consumer's package, refuses a module list that is not closed under imports, and records SHA-256 hashes so that `check` can gate the consumer's CI against drift. Proposed by python-tools; landed in 0.31.0 (2026-09-11). Run it as `python -m eidr_core.vendor sync|check --config vendor.toml`.

**Use it when.** Your package cannot import eidr-core:
* The dependency direction forbids it (the SDK), or the deliverable must run without it (the CLI tools), yet it needs shared logic.
* For the CI gate, run `python -m eidr_core.vendor check --config vendor.toml`. Add `--resync` where eidr-core is installed at the pin.
* To refresh the copy after moving the pin, run `python -m eidr_core.vendor sync --config vendor.toml`. Add `--from <eidr-core checkout at the pin>` to skip the clone.
* CLI exit codes: 0 means OK, 1 means `check` found drift, 2 means a `VendorError` (or an argument error). An exception that is not a `VendorError` (no `vendor.toml`, a TOML syntax error on Python 3.11+, `git` missing from PATH, a corrupt `MANIFEST.json`) prints a traceback and also exits 1, so read the output before treating 1 as drift.

**Do not use it when.** Another route applies:
* Your project can depend on eidr-core. Then install it (`@main`) and import it; vendoring is the exception the dependency direction forces.
* Never edit a vendored copy, never hand-copy a module, and never write your own copier. Fix the code in eidr-core and move the pin.
* The module mentions `eidr_core` in its text or reads package data by that name. `sync` refuses it (the residual-reference rule). A trial sync of 0.43.0 accepts only `ids`, `codes`, `ordering` and `secrets_loader` on their own. It refuses `altidtool_io` (since 0.39.0), `verify` (its docstring names `eidr_core`), `db_schemas`, `bmr_io`, `external`, `inheritance` and `registry` for residual text, and `compare` and `normalize` for residual text even when their imports are listed. A refused module needs a seam in eidr-core first, which is a proposal.
* At runtime in the shipped package. Deployed code imports its vendored copy and never `eidr_core.vendor`.

**Used by.**
<!-- dict-usedby:eidr_core.vendor -->
Scan of 2026-10-02; regenerated at each release from the consumer trees.
* **python-tools**: `check`, `load_manifest`, (the module)
<!-- /dict-usedby -->

**Specs.** `specs/vendoring.md` 1.0.0 fixes the `vendor.toml` format, the `sync` and `check` steps, the guarantees (the copy imports with no other eidr-core file present; same pin gives the same bytes) and the policy (vendored code is read-only). `SPEC_VERSION` mirrors its version.

### `check`

<!-- dict:eidr_core.vendor.check -->
```python
def check(manifest: Manifest, *, source_path: str | os.PathLike[str] | None = None, resync: bool = False) -> list[str]
```

Defined in `src/eidr_core/vendor/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `manifest` | `Manifest` | required | The consumer's parsed `vendor.toml`, from `load_manifest`. |
| `source_path` | `str \| os.PathLike[str] \| None` | `None` (keyword-only) | Local eidr-core checkout to re-copy from (CLI `--from`). Its HEAD must equal the pin and its `src/eidr_core` must be clean. Passing it also turns on the re-copy comparison. |
| `resync` | `bool` | `False` (keyword-only) | Also re-copy the pin into a temporary directory and compare byte for byte. Without `source_path` this clones `manifest.source` with git (network access when the source is a URL). |

**Returns** `list[str]` -- Human-readable drift problems. An empty list means the copy is clean.
<!-- /dict -->

**Does.** Returns the drift problems between a vendored copy and its manifest; an empty list means clean. It always checks that `MANIFEST.json` exists and was written under this `SPEC_VERSION`, that its commit and module list match `vendor.toml`, that every file's SHA-256 matches with none extra or missing, and that no `.py` file still contains `eidr_core`. A missing `MANIFEST.json` returns that single problem at once. The byte-for-byte re-copy runs only when those checks pass and `resync` or `source_path` is given, and it can raise VendorError (git failure, checkout not at the pin, module not vendorable).

**Notes.** Read-only on the vendored tree; the re-copy goes to a temporary directory. The generated `README.md` is left out of the re-copy comparison.

### `load_manifest`

<!-- dict:eidr_core.vendor.load_manifest -->
```python
def load_manifest(path: str | os.PathLike[str]) -> Manifest
```

Defined in `src/eidr_core/vendor/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `path` | `str \| os.PathLike[str]` | required | Path to the consumer's `vendor.toml`. Relative paths resolve against the current directory. |

**Returns** `Manifest` -- The validated `[vendor]` table, with `commit` lowercased and `path` made absolute.
<!-- /dict -->

**Does.** Reads and validates a consumer's `vendor.toml` into a Manifest. Raises VendorError when the `[vendor]` table or a required key is missing, `commit` is not a 40-hex SHA (branches and tags are refused), `package` is not a dotted import path, or `modules` is empty, holds a non-identifier, or repeats a name. On Python 3.11+ it parses with `tomllib`, so a TOML syntax error raises `tomllib.TOMLDecodeError`, not VendorError; on 3.10 a strict flat-TOML parser raises VendorError instead. A missing file raises FileNotFoundError.

**Notes.** `eidr_core.db_schemas.load_manifest` has the same name and is unrelated.

### `sync`

<!-- dict:eidr_core.vendor.sync -->
```python
def sync(manifest: Manifest, *, source_path: str | os.PathLike[str] | None = None) -> SyncReport
```

Defined in `src/eidr_core/vendor/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `manifest` | `Manifest` | required | The consumer's parsed `vendor.toml`, from `load_manifest`. |
| `source_path` | `str \| os.PathLike[str] \| None` | `None` (keyword-only) | Local eidr-core checkout to copy from instead of cloning (CLI `--from`). Its HEAD must equal the pin and `src/eidr_core` must have no uncommitted changes. None clones `manifest.source` at the pin into a temporary directory (needs git and network). |

**Returns** `SyncReport` -- The absolute target directory, the pinned commit, the eidr-core version at that commit, and the SHA-256 of every file written except `MANIFEST.json`.
<!-- /dict -->

**Does.** Replaces the consumer's target directory with the listed modules copied from the pinned commit, imports rewritten. It deletes the whole target directory first, then writes the copied modules (package data included), a generated `__init__.py` that imports nothing, `_version.py`, `README.md` and `MANIFEST.json`. Before touching the target it raises VendorError if git fails, the local checkout is not at the pin or is dirty, a module does not exist, an import reaches a module not listed, a copied `.py` still contains `eidr_core`, or `pyproject.toml` has no version. Needs `git` on PATH, even with `source_path`; without it the call raises FileNotFoundError, not VendorError.

### `Manifest` (class)

<!-- dict:eidr_core.vendor.Manifest -->
```python
@dataclass(frozen=True)
class Manifest
```

Defined in `src/eidr_core/vendor/__init__.py`.

| Field | Type | Default | Purpose |
|---|---|---|---|
| `source` | `str` | required | Git URL or local path of eidr-core that `sync` clones from. Not validated. |
| `commit` | `str` | required | The exact 40-hex commit to vendor, lowercase. Never a branch or tag. |
| `target` | `str` | required | Directory of the copy, relative to the `vendor.toml` file. The tool owns it and replaces it on every sync. |
| `package` | `str` | required | Dotted import path the rewritten imports use, such as `eidr._core`. |
| `modules` | `tuple[str, ...]` | required | Top-level eidr_core module names to copy, such as `("ids",)`. Must be closed under imports. |
| `path` | `Path` | `field(compare=False, default=Path("vendor.toml"))` | Path of the `vendor.toml` this was read from (absolute when built by `load_manifest`). `target` resolves against its directory. Ignored by equality. |

| Method | Signature | Purpose |
|---|---|---|
| `target_dir` | `def target_dir() -> Path` (property) | The copy's absolute directory: `path.parent / target`, resolved. |
<!-- /dict -->

**Does.** Holds the validated `[vendor]` table of a consumer's `vendor.toml`. Frozen. Build it with `load_manifest` so that validation runs; the constructor checks nothing.

### `SyncReport` (class)

<!-- dict:eidr_core.vendor.SyncReport -->
```python
@dataclass
class SyncReport
```

Defined in `src/eidr_core/vendor/__init__.py`.

| Field | Type | Default | Purpose |
|---|---|---|---|
| `target` | `str` | required | Absolute path of the directory written. |
| `commit` | `str` | required | The 40-hex commit copied. |
| `version` | `str` | required | eidr-core's version from `pyproject.toml` at that commit. |
| `files` | `dict[str, str]` | required | Path relative to the target (forward slashes) mapped to its SHA-256 hex after rewriting. Includes the generated `__init__.py`, `_version.py` and `README.md`; excludes `MANIFEST.json`. |
<!-- /dict -->

**Does.** Reports what `sync` wrote: target directory, commit, eidr-core version and per-file hashes. The same `files` map goes into `MANIFEST.json`, where `check` reads it.

### `VendorError` (class)

<!-- dict:eidr_core.vendor.VendorError -->
```python
class VendorError(RuntimeError)
```

Defined in `src/eidr_core/vendor/__init__.py`.
<!-- /dict -->

**Does.** Signals that the manifest, the eidr-core source, or the vendored tree breaks the vendoring contract. Raised by `load_manifest` and `sync`, and by `check` during a re-copy; the message says what is wrong and what to do. The CLI prints it and exits with code 2.

### `MANIFEST_FILE` (constant)

<!-- dict:eidr_core.vendor.MANIFEST_FILE -->
Defined in `src/eidr_core/vendor/__init__.py`.

**Value** `MANIFEST_FILE = "MANIFEST.json"` -- File name of the hash manifest that `sync` writes in the target directory and `check` reads. It records the contract version, source, commit, eidr-core version, package, modules, sync time and every file's SHA-256, and it is left out of its own hash table.
<!-- /dict -->

### `SPEC_VERSION` (constant)

<!-- dict:eidr_core.vendor.SPEC_VERSION -->
Defined in `src/eidr_core/vendor/__init__.py`.

**Value** `SPEC_VERSION = "1.0.0"` -- Version of `specs/vendoring.md` this tool implements. Written into `MANIFEST.json` and the generated `_version.py`. `check` reports a copy synced under a different version as drift ("run sync").
<!-- /dict -->

## `eidr_core.verify`

<!-- dict-module:eidr_core.verify -->
Source `src/eidr_core/verify/__init__.py`. Public names: 5 functions (declared by `__all__`).
<!-- /dict-module -->

**Purpose.** Pure primitives that compare a REGISTERED value (runtime, release date) with an EXTERNAL fact from TMDb, IMDb, Wikidata or a similar source, and return a categorical result. The result is `match`, `mismatch`, `insufficient` (the comparison cannot be made at the precision required) or `none` (no usable fact). It honours the external fact's stated precision, so a year-precision fact never produces a false day-level mismatch. Extracted verbatim from eidr-dq `src/dq/matching/compare.py` (2026-08-06); thresholds are parameters, never module constants.

**Use it when.** You check a registry field against an outside source:
* A DQ rule or verifier needs a match, mismatch or cannot-tell answer for a runtime or a release date.
* You hold facts in the `eidr_core.external` fact-dict shape (`release_date`, `release_date_precision`, `runtime_minutes`, `episode_runtime_minutes`).
* A record's release_date year and release_year disagree, and you want to know which one an outside source supports (`compare_year_arbitration`).

**Do not use it when.** The job is one of these:
* Comparing two EIDR records for de-duplication. Use `eidr_core.compare` (continuous scores, compare-spec, golden pairs). The two are separate on purpose; do not merge one into the other or wrap one with the other.
* You want a score or a confidence. Map the categorical result yourself.
* Do not copy the tolerance arithmetic or the precision logic into a consumer. Pass your own tolerances as arguments.
* Fetching facts. This module does no I/O; each source's client lives in its home project, and the fact-dict shape is documented in `eidr_core.external`.
* Vendoring: `sync` refuses the module, because its docstring names `eidr_core`.

**Used by.**
<!-- dict-usedby:eidr_core.verify -->
Scan of 2026-10-02; regenerated at each release from the consumer trees.
* **eidr-dq**: `compare_release_date`, `compare_runtime`, `compare_year_arbitration`, `parse_iso_date`, `runtime_candidates`
* **eidr-wikidata**: `compare_release_date`, `compare_runtime`, `compare_year_arbitration`, `parse_iso_date`, `runtime_candidates`
<!-- /dict-usedby -->

### `compare_release_date`

<!-- dict:eidr_core.verify.compare_release_date -->
```python
def compare_release_date(reg_date: date | None, reg_year: int | None, facts: dict, *, mode: str = "window", tolerance_days: int = 30) -> tuple[str, str]
```

Defined in `src/eidr_core/verify/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `reg_date` | `date \| None` | required | The registered full release date. None when the registry holds only a year, or nothing. |
| `reg_year` | `int \| None` | required | The registered release year, or None. Used for year comparisons; when it is None (or 0) the year of `reg_date` is used. |
| `facts` | `dict` | required | The inner `facts` dict of the `eidr_core.external` contract, not the outer `{status, facts}` wrapper. Reads `release_date`, which must be a full `YYYY-MM-DD` string even for month or year precision (first 10 characters parsed), and `release_date_precision` (`day`, `month` or `year`; absent means `day`). |
| `mode` | `str` | `"window"` (keyword-only) | `exact_date`: the same day is required. `year`: years only. `window`: within `tolerance_days`, falling back to month or year as precision allows. Any other string behaves as `window`, with no error. |
| `tolerance_days` | `int` | `30` (keyword-only) | Window mode only: the largest day difference that still matches a day-precision fact. At 28 or more, an adjacent month also matches a month-precision fact. |

**Returns** `tuple[str, str]` -- `(comparison, note)`. comparison is `match`, `mismatch`, `insufficient` or `none`; note is a short human-readable reason, such as `"date 2001-05-04 vs 2001-05-20 (16d, match)"`.
<!-- /dict -->

**Does.** Compares a registered release date or year with an external release-date fact, honouring the fact's precision. Returns `none` when the fact has no `release_date` or it does not parse, and `insufficient` when the registry lacks what the mode needs or (in `exact_date` mode) the fact is not day-precision. In window mode a day-precision fact is compared in days and a month-precision fact by month; anything else (year precision, an unrecognised precision, or no registered full date) is compared by year. Pure; `year` mode ignores precision.

**Notes.** A mistyped `mode` silently gets window behaviour, so validate mode strings that come from configuration.

### `compare_runtime`

<!-- dict:eidr_core.verify.compare_runtime -->
```python
def compare_runtime(reg_minutes: float, facts: dict, *, tolerance_minutes: float = 5.0, tolerance_pct: float = 0.10) -> tuple[str, str]
```

Defined in `src/eidr_core/verify/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `reg_minutes` | `float` | required | The registered runtime in minutes. None raises TypeError once the facts hold a runtime; with no runtime the result is `none` before `reg_minutes` is read. |
| `facts` | `dict` | required | The inner `facts` dict. Reads `runtime_minutes` and `episode_runtime_minutes` through `runtime_candidates`. |
| `tolerance_minutes` | `float` | `5.0` (keyword-only) | Absolute tolerance, in minutes. |
| `tolerance_pct` | `float` | `0.10` (keyword-only) | Relative tolerance as a fraction (0.10 is 10%) of the closest EXTERNAL runtime, not of `reg_minutes`. The larger of the two tolerances applies. |

**Returns** `tuple[str, str]` -- `(comparison, note)`. comparison is `match` or `mismatch`, or `none` (note `"no runtime"`) when the facts hold no runtime. Never `insufficient`.
<!-- /dict -->

**Does.** Compares a registered runtime with the closest external runtime, within the larger of two tolerances. The closest candidate wins, so a work with several catalogued cuts is supported by the cut the registry describes. Series episode runtimes count as candidates, because a series' ApproximateLength is its typical episode duration. Pure.

### `compare_year_arbitration`

<!-- dict:eidr_core.verify.compare_year_arbitration -->
```python
def compare_year_arbitration(reg_date: date | None, reg_year: int | None, facts: dict) -> tuple[str, str]
```

Defined in `src/eidr_core/verify/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `reg_date` | `date \| None` | required | The registered full release date. None gives `insufficient` when the fact has a parseable `release_date` (otherwise `none`). |
| `reg_year` | `int \| None` | required | The registered release_year. None gives `insufficient` when the fact has a parseable `release_date` (otherwise `none`). |
| `facts` | `dict` | required | The inner `facts` dict. Reads only `release_date`; precision is ignored and the year of the parsed date is used. |

**Returns** `tuple[str, str]` -- `(comparison, note)`. `mismatch` whenever the external date parses and both registry fields are present, with the note naming the field the external year agrees with, or saying it agrees with neither. Otherwise `none` or `insufficient`. Never `match`.
<!-- /dict -->

**Does.** Reports which of a record's two disagreeing date fields an external release date supports. It returns `mismatch` whenever it can compare, because the record is inconsistent whatever the outside source says, and the note tells a curator which field to fix. `none` when the fact has no parseable `release_date` (checked first), then `insufficient` when either registry field is None.

**Notes.** Call it only for records whose release_date year and release_year differ; it does not check. On a consistent record whose years equal the external year it still returns `mismatch`, with the false note "matches neither release_date (...) nor release_year (...)".

### `parse_iso_date`

<!-- dict:eidr_core.verify.parse_iso_date -->
```python
def parse_iso_date(s: str) -> date | None
```

Defined in `src/eidr_core/verify/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `s` | `str` | required | A value that starts with an ISO date. Anything is accepted and passed through `str()`. Only the first 10 characters are parsed, so a timestamp such as `"2001-05-04T10:00"` works. |

**Returns** `date | None` -- The date, or None when the first 10 characters are not a date `date.fromisoformat` accepts (for example `"1999"`, `"1999-05"`, `""`, None).
<!-- /dict -->

**Does.** Parses the leading YYYY-MM-DD date from a value, returning None instead of raising. Never raises.

**Notes.** What parses depends on the running Python's `date.fromisoformat`. On 3.11+ the compact form `20010504` and week dates such as `2001-W01-1` also parse; on 3.10 they return None. Feed it `YYYY-MM-DD` when results must agree across the supported range.

### `runtime_candidates`

<!-- dict:eidr_core.verify.runtime_candidates -->
```python
def runtime_candidates(facts: dict) -> list[float]
```

Defined in `src/eidr_core/verify/__init__.py`.

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `facts` | `dict` | required | The inner `facts` dict. `runtime_minutes` and `episode_runtime_minutes` must each be a LIST of numbers or numeric strings; missing, None or empty means no candidates from that key. |

**Returns** `list[float]` -- Every runtime in minutes, `runtime_minutes` first and then `episode_runtime_minutes`. `[]` when there are none.
<!-- /dict -->

**Does.** Collects every comparable runtime in a fact set as floats in minutes, including series episode runtimes. Raises ValueError or TypeError when an item cannot be converted to float.

**Notes.** A scalar in place of a list is not caught cleanly. A number raises TypeError, and a string such as `"90"` is read character by character, giving `[9.0, 0.0]`.

## Specs and data files

The `specs/` directory holds language-neutral contracts. Python and
JavaScript implementations both prove conformance against them. **A change
to anything under `specs/` needs a version bump and regenerated golden-pair
expectations.** A consumer's failing conformance test is the cross-project
alert that a spec moved. The one exception is `merge-rules.md`, a DRAFT with
no version yet.

| Spec | What it fixes | Status | Machine-readable data | Implemented or checked by |
|---|---|---|---|---|
| `specs/normalized-record.md` | The field model of an EIDR record and its canonical ordering (titles, Alt IDs, credits) | SPEC v1, ratified 2026-07-29 | none | `eidr_core.ordering`; consumers XML_to_JSON, BMR-Review, eidr-wikidata, De-Dupe UI |
| `specs/unified-scoring.md` | The design of the one match-candidate scoring engine: layers, banded states, per-creation-type weights | approved 2026-07-27 | its runtime config is the compare-spec | BMR-Review's engine (reference), De-Dupe UI (JavaScript) |
| `specs/compare-spec.md` | The engine's tuning surface: weights, values, states, rationale, and the porting requirements | the version is the JSON's `$spec.version`: 2.18.0 on 2026-10-02 | `src/eidr_core/specs/compare-spec.json`, loaded by `eidr_core.compare.spec.load_spec` (override with `EIDR_COMPARE_SPEC`) | Authored in BMR-Review `eidr_dedup_score/config.py` and regenerated, never hand-edited; conforming: BMR-Review, De-Dupe UI |
| `specs/golden-pairs.md` | The conformance corpus formats (`pair`, `case`, `recovery_pool`), invariants, and the optional `ancestry` block | landed; 38 fixtures at compare-spec 2.18.0 | `src/eidr_core/specs/golden_pairs/*.json`; `golden_pairs_pending/` holds fixtures that wait on an engine version | Evaluator: BMR-Review `eidr_dedup_score/golden.py`; conforming: BMR-Review, De-Dupe UI |
| `specs/dedupe-worklist.md` | The De-Dupe work-list, results and supplement JSONL formats, including the per-candidate scoring payload | SPEC v2 (2026-08-30) | none | Producer BMR-Review `run_worklist.py`; consumer De-Dupe UI |
| `specs/altidtool-format.md` | The AltIDTool input line (3, 4 or 5 tab-separated columns) and the portfolio's Alt ID rules (relation, presence, rule 6) | SPEC v1.5 (2026-10-02) | `src/eidr_core/specs/multi_form_kinds.json`, read by `multi_form_domains()` | `eidr_core.altidtool_io`; producers eidr-wikidata and BMRtoAltID; vendored by python-tools |
| `specs/altid-display-order.md`, `specs/title-display-order.md` | The display order of Alt IDs and titles that the API Shim must emit | handoffs to the API Shim team, 2026-07-29 and 2026-07-30 | none | the API Shim (outside this portfolio) |
| `specs/db-schema-contracts.md` | The schema contracts of the portfolio databases: mirror, DQ, language registry, IMDb snapshot | approved and landed 2026-08-03 | `src/eidr_core/specs/db_schemas/<db>/` (manifest, DDL, CHANGES), regenerated by `D:\Software\eidr-core-ops\tools\dump_db_schema.py` | `eidr_core.db_schemas.assert_tables`; every program that reads one of those databases |
| `specs/vendoring.md` | How a package that cannot depend on eidr-core carries one implementation anyway (`vendor.toml`, `sync`, `check`) | 1.0.0 (2026-09-11) | the consumer's `vendor.toml` | `python -m eidr_core.vendor`; python-sdk vendors `ids`, python-tools vendors `altidtool_io` |
| `specs/merge-rules.md` | The MergeTool rule table: merging a supplied record into the registry record | DRAFT, no version, nothing built | none | nobody yet (planned `eidr_core.merge`) |

## Conventions every consumer follows

* **Pin `@main`.** Every push to eidr-core reaches your next install, so a
  behaviour change can reach you with no code change of yours. (In 0.43.0,
  for example, `multi_form_domains()` gained an entry.) eidr-core's CI is the
  gate, and eidr-core re-runs every consumer's suite after each release. If
  you run mypy over code that imports eidr-core, pin the same mypy version as
  eidr-core's CI.
* **Ask and propose by handoff.** Write a file to
  `D:\Software\eidr-core-ops\handoffs-received\`, named
  `HANDOFF-FROM-<PROJECT>-<date>-<topic>.md`. Read this dictionary first, and
  cite the entries the handoff touches. eidr-core answers with a ruling and
  its reasons, including when the answer is no.
* **A patch with tests is the best proposal, and it is still a proposal.**
  Send only the files it touches. Never send a whole-file copy of a file like
  `pyproject.toml`, which would revert whatever landed since you forked.
  Never pick the version number. Write "additive, suggest a minor bump" and
  leave the number to eidr-core.
* **Never ship a consumer that depends on a proposal that has not landed.**
  Wait for the change to land and be announced. Then adopt it, in a separate
  cycle.
* **No local copies of shared logic.** If your copy differs from eidr-core's,
  ask why before you call the difference justified. The usual cause is a
  signature gap, and widening the signature is cheaper than keeping two
  implementations.
* **Vendor only through the mechanism.** A package that cannot depend on
  eidr-core uses `python -m eidr_core.vendor` under `specs/vendoring.md`.
  Never copy files by hand.
