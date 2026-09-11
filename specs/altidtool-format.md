# AltIDTool Input File Format (SPEC v1.1)

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

## For consumers/readers

`parse_line` accepts all three widths and the fixed-5 dialect. Remediation
action TSVs (`registry_remediation_actions.tsv` etc.) are a DIFFERENT format
(they carry action verbs and context columns) and are not covered here.
