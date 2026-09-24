# AltIDTool Input File Format (SPEC v1.3)

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

## Removal lines (v1.1, 2026-09-11)

The AltIDTool itself also accepts **removal** lines, which no portfolio feed
generator emits but which the python-tools `AltIDTool` reads
(`docs/research/legacy-java-tools-extraction.md`: `ID` removes all Alt IDs;
`ID<TAB>TYPE` removes every Alt ID of that type). A three-column line whose
value is empty is a removal of that type, not an Alt ID with no value. Blank
lines and lines starting with `//` are comments.

    10.5240/AAAA-…-X                          remove every alternate ID
    10.5240/AAAA-…-X	IMDB                     remove every IMDB alternate ID
    10.5240/AAAA-…-X	IMDB	                 same (empty value)

`parse_edit_line` in `eidr_core.altidtool_io` reads the superset (addition,
removal, comment); `parse_line` stays strict so a feed generator can never
produce a removal by accident. Added so that the tools can vendor this
module (`specs/vendoring.md`) without losing their removal path.

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
6. **A second `IsSameAs` of one SINGLE-FORM Kind with a DIFFERENT value
   contradicts the first** (eidr-wikidata, 2026-08-09; ruled portfolio-wide
   2026-09-23 for the merge engine; **scope narrowed 2026-09-24**): withheld
   and reported, never written. *Single-form* means the Kind admits one
   identifier form: every named type (`IMDB`, `ISAN`, ...), and a Proprietary
   Kind to which exactly one `uri_mapping.json` entry collapses. A Kind to
   which SEVERAL entries collapse is **multi-form** and legitimately carries
   one identity value per form -- `trakt.tv` holds a numeric ID (entry
   `trakt.tv`) AND a slug (entry `trakt.tv/movies`, collapsed to the bare
   domain with the path in the value); likewise `cinematografo.it`,
   `disneyplus.com`, `fandom.com`. Rule 6 does not fire on a multi-form Kind.
   Measured by BMRtoAltID on eidr-wikidata's sheet 029: 2,741 of 5,000 rows
   carry two identity values of one Kind, 2,657 of them `trakt.tv`; and
   eidr-wikidata's own writer had withheld 133,223 `trakt.tv` proposals as
   conflicts under the unnarrowed rule. A single-form Kind with two values
   (`dvdcompare.net` 441 rows, `kinobox.cz`, `youtube.com`) IS a rule-6 case:
   the source lists two, the registry may hold one as identity, a human
   decides. The form is not recoverable from a stored value, so consumers
   derive the multi-form set from `uri_mapping.json` (eidr-wikidata
   `DomainMapper.multi_form_domains()` is the reference).

## For consumers/readers

`parse_line` accepts all three widths and the fixed-5 dialect. Remediation
action TSVs (`registry_remediation_actions.tsv` etc.) are a DIFFERENT format
(they carry action verbs and context columns) and are not covered here.
