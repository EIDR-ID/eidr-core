# AltIDTool Input File Format (SPEC v1.6)

**Status:** landed 2026-08-04 (register R9 / Phase 3 item 3). The reference
implementation is **`eidr_core.altidtool_io`** (`format_line` / `write_lines`
/ `parse_line`); the production feed generator (eidr-wikidata
`bmr/altidtool.py`) composes every line through it.

## The format

Tab-separated, UTF-8, LF line endings, **no header line**:

    EIDR_ID <TAB> Type <TAB> Value [<TAB> Domain] [<TAB> Relation]

| Column | Content | Rules |
|---|---|---|
| 1 | EIDR ID | `10.5240/…` of the record receiving the Alt ID |
| 2 | Type | A named EIDR Alt ID type (IMDB, ISAN, …) or `Proprietary` |
| 3 | Value | The identifier value (URI-safe; validated upstream) |
| 4 | Domain | ONLY for `Proprietary` rows (the qualified altIdDomain). Named types leave it out — except as an EMPTY placeholder when column 5 is present |
| 5 | Relation | ONLY when non-empty. **Blank/absent ≡ IsSameAs** (the registry default). Known non-default values in production feeds: `Deprecated`, `IsEntirelyContainedBy` |

Lines are therefore **3, 4, or 5 columns wide**:

    10.5240/AAAA-…-X	IMDB	tt0133093
    10.5240/AAAA-…-X	Proprietary	603	themoviedb.org/movie
    10.5240/AAAA-…-X	IMDB	tt9999999		Deprecated
    10.5240/AAAA-…-X	Proprietary	Q42	wikidata.org	IsEntirelyContainedBy

## Known producers and their conformance

| Producer | Shape | Status |
|---|---|---|
| eidr-wikidata `bmr/altidtool.py` (`altid_additions.tsv`, ~2.2M rows/run) + `outputs` (`missing_from_eidr.altid.tsv`) | canonical variable-width | ✅ composes via `eidr_core.altidtool_io.format_line` (2026-08-04) |
| BMRtoAltID `bmr_to_altid.py` | canonical variable-width | ✅ composes via `eidr_core.altidtool_io.format_line` (2026-08-04; **operator ruling**: variable columns, max 5, no trailing tabs — the fixed-5 dialect is retired; `parse_line` still tolerates old files) |
| EIDR MCP `eidrtoaltid.py` | **NOT this format** — a 2–4 column extract *report* WITH a header (id + value, optional Relation/Resource Name). Previously mischaracterized as a parallel emitter (OVERLAPS row 4 / drift group); corrected 2026-08-04 | out of scope |

## Removal lines (v1.1, 2026-09-11; narrowed v1.6, 2026-10-19)

Edit files also carry **removal** lines, which no portfolio feed generator
emits but which the python-tools `AltIDTool` applies. A line is a removal
when its Value (column 3) is empty or absent. Blank lines and lines starting
with `//` are comments. Exactly two removals are valid:

    10.5240/AAAA-…-X	IMDB                         remove every IMDB Alt ID
    10.5240/AAAA-…-X	IMDB	                     same (empty Value)
    10.5240/AAAA-…-X	Proprietary		themoviedb.org/movie   remove every Proprietary Alt ID of that domain

**Operator ruling, 2026-10-19:** "Refuse removing all alt IDs. The pattern
ID<tab>Proprietary<tab><tab>Domain should remove all IDs of that domain only
(Proprietary by itself without a domain should be refused)."

Every form, by columns after splitting on TAB (trailing empty columns, the
fixed-5 dialect, change nothing; `*` = any or none):

| Line | v1.1–v1.5 | v1.6 |
|---|---|---|
| `ID` | remove every Alt ID | **refused** (remove-all) |
| `ID<TAB>`, `ID<TAB><TAB>`, … (empty Type, empty Value, empty Domain) | remove every Alt ID (stray tabs) | **refused** (remove-all) |
| `ID<TAB><TAB><TAB>Domain` (empty Type, Domain given) | remove every Alt ID (Domain ignored) | **refused** (remove-all) |
| `ID<TAB><TAB>Value…` (empty Type, Value given) | an addition with no Type | **refused** (no Type) |
| `ID<TAB>Named` / `ID<TAB>Named<TAB>` | remove every Alt ID of that type | unchanged |
| `ID<TAB>Named<TAB><TAB>Domain` | remove the type (Domain ignored) | **refused** (Domain is for Proprietary only) |
| `ID<TAB>Proprietary` / `ID<TAB>Proprietary<TAB>` / `…<TAB><TAB>` | remove every Proprietary Alt ID | **refused** (no Domain) |
| `ID<TAB>Proprietary<TAB><TAB>Domain` | remove every Proprietary Alt ID (Domain ignored) | **remove the Proprietary Alt IDs of that Domain only** |
| `ID<TAB>*<TAB><TAB>*<TAB>Relation` (any removal with a Relation) | Relation ignored | **refused** (a removal carries no Relation) |

Why refuse rather than read literally: each refused line removes more than
its author can have meant (stray tabs after an ID removed a record's every
Alt ID; a Domain or Relation that looked like it narrowed a removal was
dropped), and the failure is silent and lands on the registry. The legacy
Java tool read a remove-all from `ID` alone and a domain removal from the
THREE-column `ID<TAB>Proprietary<TAB>DOMAIN`
(`docs/research/legacy-java-tools-extraction.md` in python-tools); this
format never adopted that three-column form, which here is an addition
whose Value is the third column.

`parse_edit_line` in `eidr_core.altidtool_io` reads the superset (addition,
removal, comment) and raises `ValueError` for every refused line;
`AltIdRemoval` carries `eidr_id`, `alt_type` (never empty) and `domain` (set
on a Proprietary removal, empty on a named type). A caller that applies
removals must match the domain as well as the type. `parse_line` stays
strict so a feed generator can never produce a removal by accident. Added
so that the tools can vendor this module (`specs/vendoring.md`) without
losing their removal path.

## Identity, relation and what "already on the record" means (v1.2, 2026-09-23)

Stated by the operator for IMDb on 2026-09-23 and generalised here because the
shape is the same for every external identifier scheme; the rules are what a
producer or reader must hold to reason correctly, and each has already cost a
consumer a wrong answer.

1. **An identity claim is `IsSameAs` OR an absent relation.** Required Data
   Fields v1.15: a blank Relation reads as `IsSameAs`. The two are one class
   for every counting and lookup purpose. A reader that tests the literal
   string alone undercounts identity claims by ~70% (403,410 of 579,621 IMDb
   links carry no relation; eidr-imdb's crosswalk did this, 2026-09-23).
   **In the mirror an absent relation is stored as `NULL` since 2026-09-23;
   before that day it was the empty string**, so a predicate must admit
   `NULL`, `''` and `'IsSameAs'` alike — every one of
   `relation IS NULL OR relation = 'IsSameAs'`'s consumers (BMR-Review,
   eidr-dq, BMRtoAltID) was seeing 30% of the links until the repair.
2. **Identity is many-to-one from the external ID to EIDR, never
   one-to-many.** One external identifier names one thing; at most one EIDR
   record may claim it as identity. Several records claiming one identifier
   under `IsSameAs` is the defect the contested batches repair.
3. **`Deprecated` and `Duplicate` are unbounded and are not identity.** They
   coexist with an identity claim on the same record legitimately (543 IMDb
   records do). A validator enforcing "one identifier per record" flags them
   all wrongly.
4. **Containment and derivation relations (`IsEntirelyContainedBy`,
   `ContainsAllOf`, `IsDerivedFrom`, ...) are legitimate, are other tools' to
   create, and are every producer's to tolerate and never to invent.** A
   second record referencing the identifier under one of these is not a
   rule-2 violation.
5. **"Already on the target record" is Kind + value + relation** (operator
   rule 7, 2026-09-21). Presence is Kind `(Type, Domain)` + value under ANY
   relation; what a producer does with it depends on the relation: the same
   relation → nothing to write; a different relation → a finding for human
   reconciliation, per Alt ID, and never a second line for the same value.
   Producers implementing it: BMRtoAltID (`ALT_ID_RELATION_CONFLICT`),
   eidr-wikidata (`relation_conflict`).
6. **A second `IsSameAs` of one Kind with a DIFFERENT value contradicts the
   first** (eidr-wikidata, 2026-08-09; ruled portfolio-wide 2026-09-23 for the
   merge engine): withheld and reported, never written -- **except on the
   Kinds listed by `eidr_core.altidtool_io.multi_form_domains()`** (v1.4,
   2026-09-26; ruled entries v1.5, 2026-10-02). A Kind is `(type, domain AS THE REGISTRY STORES IT)`:
   `trakt.tv`, `trakt.tv/movies` and `trakt.tv/shows` are three Kinds.
   The exempt list is DECLARED in `src/eidr_core/specs/multi_form_kinds.json`,
   each entry with its measurement: a Kind is listed when at least half the
   registry records carrying it already hold more than one identity value of
   it, so the registry's own practice says it is multi-valued (2026-09-26:
   `pbs.org` 98.9%, `decellc.com` 79.7%; the next Kind down is 14.2%).
   **v1.3 derived the set from `uri_mapping.json` entry counts and was wrong,
   measured 2026-09-26:** duplicate entries are alternate URL templates of ONE
   form (`wikidata.org` x5, `dfi.dk/movie` x3), and v1.3's worked example was
   false -- the registry stores the `trakt.tv` slug under the separate Kind
   `trakt.tv/movies` (85,036 values), while `trakt.tv` holds 20,931 numeric
   values with two records carrying more than one. The derivation as built
   in eidr-wikidata returned `{thetvdb.com/movie}` (a canonical alias, not a
   second form) and exempted nothing v1.3 intended. The 2,657 `trakt.tv`
   doubles in sheet 029 and the 133,223 withheld proposals v1.3 cited
   predate eidr-wikidata's 2026-08-29 Tier 0 (P8013 slug to
   `trakt.tv/movies`, P12492 numeric to `trakt.tv`); the current writer
   withholds no `trakt.tv` proposal. A Kind with two values from one source
   (`dvdcompare.net`, `kinobox.cz`, `youtube.com`) IS a rule-6 case: the
   source lists two, the registry may hold one as identity, a human decides.
   Consumers call the function; none keeps its own copy of the list.
   **v1.5 (2026-10-02): a Kind may also be listed by operator RULING.** When
   a Kind's identifiers come in two forms that cannot be told apart from
   outside the registrant, the operator may declare it two-form; the entry
   quotes the ruling and records the measurement taken when it was made.
   First entry: `mediafilm.ca` -- operator: "We can't tell, so accept both
   for now." Measured 2026-10-02: 7,681 `mf-tt-N` values (`mf-tt-1624656` to
   `mf-tt-9999443355`) and 3,534 numeric values (127 to 91228), DISJOINT
   ranges, so neither is a rendering of the other; 3 of 11,212 records hold
   one of each and none holds two of one form; the published URL template
   returns 404 for both. Raised by BMRtoAltID's first batch (T6: 77 of 731
   rows carried a numeric value against a record holding `mf-tt-...`, all
   withheld under v1.4). Provisional: reviewed if Mediafilm says the forms
   are one identifier or one is retired. The separate Kind
   `mediafilm.ca/film` (727 values, all `mf-tt`) is single-form and not
   listed.

## For consumers/readers

`parse_line` accepts all three widths and the fixed-5 dialect. Remediation
action TSVs (`registry_remediation_actions.tsv` etc.) are a DIFFERENT format
(they carry action verbs and context columns) and are not covered here.

## Change history

Earlier versions are marked in the section headings they introduced (v1.1
removal lines, v1.2 identity and relation rules, v1.3-v1.5 rule 6 and the
multi-form Kinds).

- **v1.6 (2026-10-19)** -- removal lines narrowed on the operator's ruling of
  2026-10-19 ("Refuse removing all alt IDs. The pattern
  ID<tab>Proprietary<tab><tab>Domain should remove all IDs of that domain
  only (Proprietary by itself without a domain should be refused)"). Every
  spelling of remove-all (`ID`, `ID<TAB>`, `ID<TAB><TAB>`,
  `ID<TAB><TAB><TAB>Domain`) is refused; `ID<TAB>Proprietary<TAB><TAB>Domain`
  removes that domain's Proprietary Alt IDs only and `AltIdRemoval` gains a
  `domain` field to carry it; a Proprietary removal without a Domain, a
  Domain on a named-type removal, a Relation on any removal, and an addition
  with an empty Type (`ID<TAB><TAB>value`) are refused. Named-type removals
  (`ID<TAB>Type`, with or without an empty Value) are unchanged. Raised by
  the 2026-10-02 dictionary audit.
