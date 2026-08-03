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
`D:\Software\eidr-core\CROSS_PROJECT_OVERLAP_REGISTER.md` and migrates
into this repo once it is pushed to GitHub.

## Module map (planned; stubs document their seeds)

| Module | Contents | Extracted from |
|---|---|---|
| `eidr_core.bmr_io` | BMR template schema, family/repeat-group model, workbook reader + writer | eidr-wikidata `bmr/writer.py` (canonical), BMR-Review's two vendored copies, XML_to_JSON's BMR codec, eidr-dq `flatten.py` |
| `eidr_core.compare` | ✅ **LANDED 0.1.0** — the L2 comparator library: field comparators (`COMPARATORS`, `FieldResult`), episode-aware `titles`, `nonlinear` accumulation; parameters via `set_params()` (BMR-Review registers its `config.py`; later the compare-spec) | BMR-Review `compare.py`/`titles.py`/`nonlinear.py` (now shims) |
| `eidr_core.normalize` | ✅ **LANDED 0.1.0** — L1 normalization: fold/case/alias/numeral, name/title/code normalizers incl. `norm_country`/`canon_country`, date/duration parsing, `word_alias.csv` | BMR-Review `normalize.py`/`aliases.py` (now shims) |
| `eidr_core.ordering` | ✅ **LANDED 0.2.0** — canonical + display ordering key functions per the ratified normalized-record spec (title three-bucket, alt-ID kind/value + display rule, ShortDOI test); consumed by XML_to_JSON star mode and BMR-Review `render_record` | XML_to_JSON + BMR-Review (both now importers) |
| `eidr_core.altidtool_io` | AltIDTool 5-column TSV read/write | eidr-wikidata `bmr/altidtool.py`, EIDR MCP `eidrtoaltid.py`, BMRtoAltID |
| `eidr_core.registry` | SDK client factory (target selection, credential precedence, write gate) | eidr-wikidata `eidr/registry_client.py` |
| `eidr_core.codes` | ✅ **LANDED** — `normalize_country_code` (SU→SUHH crosswalk), consumed by eidr-wikidata + BMR-Review. Grows the `dq_country_validity` + `language_registry` readers next. | eidr-wikidata `bmr/country.py`, BMR-Review `normalize.py`, eidr-dq validators |
| `eidr_core.secrets_loader` | One secrets loader (AWS Secrets Manager + local `.secrets.json`, one section layout) | eidr-dq/XML_to_JSON `secrets_loader.py`, EIDR MCP loader, eidr-wikidata `secrets.py` |
| `eidr_core.external` | Shared external-source chassis (cache, rate limit, retry) | eidr-dq `external/cache.py` (seed) |

Extraction order and rationale: see the overlap register, Phase 3.
