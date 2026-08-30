# eidr-core

Shared home for the EIDR tool portfolio's cross-project assets, in three
tiers:

1. **LIBRARY** (`src/eidr_core/`) — Python modules extracted from the
   individual projects so identical logic exists exactly once. Node.js
   projects (eidr-ui-nextjs modules such as De-Dupe UI) do NOT consume this
   code — they consume the spec tier below.
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
plan — lives at [`CROSS_PROJECT_OVERLAP_REGISTER.md`](CROSS_PROJECT_OVERLAP_REGISTER.md)
in this repo (its permanent home; migrated here from eidr-wikidata
2026-08-02).

## Installing eidr-core in a consuming program

eidr-core is **not on PyPI** and is **not vendored** into consumers — it is
installed straight from this GitHub repo:

```
eidr-core[bmr,aws] @ git+https://github.com/EIDR-ID/eidr-core.git@main
```

in `requirements.txt` (or `pyproject.toml` `dependencies`), with whichever
extras the consumer actually needs (table below). **Pin to `@main`, not a
version tag** — every consumer is expected to track eidr-core's tip; where a
reproducible build genuinely matters, pin a commit SHA instead.

The repo is **private**, so the installing environment needs GitHub
credentials — this includes CI runners and Docker builds, which have none by
default. Full setup (the `EIDR_CORE_TOKEN` repository secret, the
`git config url.insteadOf` recipe, and how to verify a PAT actually works
before debugging a workflow) is in [`CLAUDE.md`](CLAUDE.md) → "Consuming
eidr-core from another application". Read that section — not just this
README — before adding the first `import eidr_core` to any program; it
covers a `ModuleNotFoundError` failure mode that only shows up on a clean
deploy, after the local dev checkout already works.

### Extras

The base install has **no third-party dependencies** — every module below
"(none)" is stdlib-only.

| Extra | Pulls | Needed for |
|---|---|---|
| *(none)* | — | `codes`, `db_schemas`, `altidtool_io`, `ordering`, `normalize`, `external` (including the retry/failover chassis), `verify`, and `registry.operation_status` |
| `compare` | rapidfuzz | `eidr_core.compare` (imported at module load) |
| `bmr` | openpyxl | `eidr_core.bmr_io.read_sheet` (lazy) |
| `aws` | boto3 | `eidr_core.secrets_loader` AWS path (lazy) |
| `registry` | `eidr[client]` (the SDK, from PyPI) | `eidr_core.registry.get_registry_client` (lazy) |

Extras are additive: `eidr-core[compare,bmr]`.

### For local development on eidr-core itself

```
pip install -e ".[dev]"
pytest tests/ -q
```

## Module map

Every module below has landed; **Phase 3 of the register (library
extraction) is complete** as of 2026-08-09. What remains is consumer-side
*adoption* (tracked per-module below) and per-source external clients, which
move here only when a second consumer appears (see `external` and the
register's R13).

| Module | Contents | Extracted from |
|---|---|---|
| `eidr_core.bmr_io` | Workbook surgery (writer primitives: HEADER_ROW, read/count/rightmost/expand family, transplant, fix_shared_strings) **+** the reader half — `open_sheet` (streaming context manager, lazy rows with absolute sheet row numbers), `read_sheet` (a `list()` over it), `read_headers`, sparse `family_layout`, shared `RepeatPlan`/`pad_groups`. Orchestration stays per-consumer by design. | eidr-wikidata `bmr/writer.py` + BMR-Review `audit/bmr_writer.py` (both importers); eidr-dq `flatten.py` folded in; `open_sheet` contributed by BMRtoAltID |
| `eidr_core.compare` | The L2 comparator library: field comparators (`COMPARATORS`, `FieldResult`), episode-aware `titles`, `nonlinear` accumulation; parameters via `set_params()`, driven by `compare-spec.json` (see `compare.spec`) | BMR-Review `compare.py`/`titles.py`/`nonlinear.py` (now shims) |
| `eidr_core.normalize` | L1 normalization: fold/case/alias/numeral, name/title/code normalizers incl. `norm_country`/`canon_country`, date/duration parsing, `sanitize_field`, `word_alias.csv` | BMR-Review `normalize.py`/`aliases.py` (now shims) |
| `eidr_core.ordering` | Canonical + display ordering key functions per the ratified normalized-record spec (title three-bucket, alt-ID kind/value + display rule, ShortDOI test) | XML_to_JSON + BMR-Review `render_record` (both importers) |
| `eidr_core.altidtool_io` | AltIDTool input-line format (variable 3/4/5-col compose, tolerant parse; contract `specs/altidtool-format.md`) | eidr-wikidata `bmr/altidtool.py` (composes through it); BMRtoAltID keeps a deliberately separate fixed-5 dialect |
| `eidr_core.registry` | The SDK client factory (sandbox2 default, credential precedence incl. `.secrets.json` registry section, superparty gate, lazy SDK import) **+** `operation_status` — the three-way success/failed-with-reason/no-verdict-yet parse that mitigates an SDK defect where a rejected write reports as PENDING (durable seam; see register R5) | eidr-wikidata `eidr/registry_client.py` (now a shim) + eidr-wikidata's `registry_errors.py` (seed for `operation_status`) |
| `eidr_core.codes` | `normalize_country_code` (SU→SUHH crosswalk) | eidr-wikidata `bmr/country.py`, BMR-Review `normalize.py`, eidr-dq validators |
| `eidr_core.inheritance` | Full-record construction: what a child inherits from its parent (schema `inheritedBaseObjectInfoGroup`) + the four system-generated title patterns. Two shape adapters over one policy — `build_full_base` (registry JSON) and `build_full_record` (record objects), plus a per-field `provenance` map. eidr-core imports neither consumer's model | XML_to_JSON (reference implementation) + BMR-Review (which stubbed a seam rather than write a second copy) |
| `eidr_core.ids` | EIDR **Content ID** syntax + ISO 7064 Mod 37,36 check character (`check_character`, `is_valid_eidr_id`, `fault`). Party IDs (`10.5237/`) not covered — deferred to the CLI-tools work, which is expected to supply real vectors; see the module docstring | BMR-Review `validate_returned_ids.py`; adopted by BMRtoAltID `bmr_altid/ids.py` |
| `eidr_core.secrets_loader` | One secrets loader (AWS Secrets Manager + local `.secrets.json`, one section layout) | eidr-dq/XML_to_JSON `secrets_loader.py`, EIDR MCP loader, eidr-wikidata `secrets.py` |
| `eidr_core.verify` | External-fact verification primitives — categorical, precision-aware comparison (release-date precision is the asymmetry that makes this a separate engine from `compare`) | eidr-dq `matching/compare.py` (a shim now wraps it) |
| `eidr_core.db_schemas` | Schema-contract assertions (`assert_tables`) against the packaged manifests for all three portfolio databases (mirror, dq, language) | live databases (authoritative); manifests generated by `tools/dump_db_schema.py` |
| `eidr_core.external` | The shared external-source chassis: `FactCache` protocol + `Null`/`Dict` implementations and the fact-dict contract (`external/__init__.py`); retry/backoff + endpoint failover (`external/failover.py`) | eidr-dq `external/cache.py` (cache seed); eidr-wikidata `wikidata/sparql.py` `_query_endpoints` (failover seed) |

Per-source external clients (Wikidata, TMDb, IMDb) are deliberately **not**
here — each source has exactly one implementation home until a genuine
second consumer appears (register R13). Extraction order and full rationale
for every module: `CROSS_PROJECT_OVERLAP_REGISTER.md`, Phase 3.

## Repository layout

- `src/eidr_core/` — the LIBRARY tier (above).
- `specs/` — the SPEC tier: narrative contracts consumable from both Python
  and node.js. See `specs/README.md`.
- `OVERLAPS.md` — the duplication manifest.
- `drift/` — a baseline-hash checker that flags when a file duplicated
  across repos has changed, as a bridge until it's retired by extraction.
  See `drift/README.md`.
- `tools/` — `gen_session_brief.py` (per-session file-inventory briefs for
  the portfolio's chat-driven repos) and `dump_db_schema.py` (regenerates
  the packaged DB schema contracts from a live database).
- `tests/` — deliberately thin: spec-driven modules are verified by
  siblings' conformance tests instead. Only safety surfaces whose wrong
  answer is *silent* get local tests (`registry.operation_status`,
  `external.failover`).
