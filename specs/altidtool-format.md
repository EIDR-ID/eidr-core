# AltIDTool Input File Format (SPEC v1)

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
| BMRtoAltID `bmr_to_altid.py` | **fixed 5 columns** (trailing tabs when Domain/Relation empty) | tolerated by `parse_line` (trailing empties collapse); ⚠ **operator decision open**: switch it to the canonical variable-width writer, or record fixed-5 as an accepted dialect? |
| EIDR MCP `eidrtoaltid.py` | **NOT this format** — a 2–4 column extract *report* WITH a header (id + value, optional Relation/Resource Name). Previously mischaracterized as a parallel emitter (OVERLAPS row 4 / drift group); corrected 2026-08-04 | out of scope |

## For consumers/readers

`parse_line` accepts all three widths and the fixed-5 dialect. Remediation
action TSVs (`registry_remediation_actions.tsv` etc.) are a DIFFERENT format
(they carry action verbs and context columns) and are not covered here.
