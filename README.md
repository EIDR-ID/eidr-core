# eidr-core

Shared home for the EIDR tool portfolio's cross-project assets, in three
tiers:

1. **LIBRARY** (`src/eidr_core/`) — Python modules extracted from the
   individual projects so identical logic exists exactly once. Python
   consumers install this package (editable during development:
   `pip install -e D:\Software\eidr-core`). Node.js projects
   (eidr-ui-nextjs modules such as De-Dupe UI) do NOT consume this code —
   they consume the spec tier below.
2. **SPEC** (`specs/`) — versioned, language-neutral contracts: the
   normalized-record specification, the record-comparison rules/weights
   (compare-spec), the golden-pair conformance corpus, and shared file
   formats (AltIDTool TSV, De-Dupe work-list/results). Python and JS
   implementations each prove conformance against the corpus; a spec
   version bump that a sibling hasn't adopted shows up as that sibling's
   failing conformance test — that failure is the cross-project change
   alert.
3. **Registry of duplication** (`OVERLAPS.md`) — the manifest of known
   vendored/parallel copies that still exist across projects, so drift is
   tracked until each one is retired by extraction.

The governing document — the cross-project overlap register and phased
plan — currently lives at
`D:\Software\eidr-wikidata\CROSS_PROJECT_OVERLAP_REGISTER.md` and migrates
into this repo once it is pushed to GitHub.

## Module map (planned; stubs document their seeds)

| Module | Contents | Extracted from |
|---|---|---|
| `eidr_core.bmr_io` | BMR template schema, family/repeat-group model, workbook reader + writer | eidr-wikidata `bmr/writer.py` (canonical), BMR-Review's two vendored copies, XML_to_JSON's BMR codec, eidr-dq `flatten.py` |
| `eidr_core.ordering` | Canonical EIDR record ordering (casefold sorts, title/credit/alt-ID ranking) | XML_to_JSON star-mode sort + BMR-Review `render_record` |
| `eidr_core.altidtool_io` | AltIDTool 5-column TSV read/write | eidr-wikidata `bmr/altidtool.py`, EIDR MCP `eidrtoaltid.py`, BMRtoAltID |
| `eidr_core.normalize` | Unicode fold, homoglyph maps, numeral/date/duration parsing | BMR-Review `normalize.py` (seed), eidr-dq homoglyph maps, EIDR MCP `_sanitize_field` |
| `eidr_core.registry` | SDK client factory (target selection, credential precedence, write gate) | eidr-wikidata `eidr/registry_client.py` |
| `eidr_core.compare` | Pure comparison primitives parameterized by compare-spec | eidr-dq `matching/compare.py` (already written for extraction) |
| `eidr_core.codes` | ✅ **LANDED** — `normalize_country_code` (SU→SUHH crosswalk), consumed by eidr-wikidata + BMR-Review. Grows the `dq_country_validity` + `language_registry` readers next. | eidr-wikidata `bmr/country.py`, BMR-Review `normalize.py`, eidr-dq validators |
| `eidr_core.secrets_loader` | One secrets loader (AWS Secrets Manager + local `.secrets.json`, one section layout) | eidr-dq/XML_to_JSON `secrets_loader.py`, EIDR MCP loader, eidr-wikidata `secrets.py` |
| `eidr_core.external` | Shared external-source chassis (cache, rate limit, retry) | eidr-dq `external/cache.py` (seed) |

Extraction order and rationale: see the overlap register, Phase 3.
