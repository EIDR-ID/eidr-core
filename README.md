# eidr-core

Shared library and specifications for the EIDR tool portfolio, in two tiers:

1. **LIBRARY** (`src/eidr_core/`) — Python modules extracted from the
   individual EIDR projects so identical logic exists exactly once.
   Node.js projects do NOT consume this code — they consume the spec tier.
2. **SPEC** (`specs/`) — versioned, language-neutral contracts: the
   normalized-record specification, the record-comparison rules/weights
   (compare-spec), the golden-pair conformance corpus, and shared file
   formats (AltIDTool TSV, De-Dupe work-list/results). Python and JS
   implementations each prove conformance against the corpus; a spec
   version bump that a consumer hasn't adopted shows up as that consumer's
   failing conformance test — that failure is the cross-project change
   alert.

The organizing principle: **a piece of logic moves here when it has a
second consumer.** Until then it stays in its home project. Anything here
is, by construction, used by at least two programs.

## Installing

eidr-core is **not on PyPI** — it installs straight from this repo:

```
pip install "eidr-core[bmr,aws] @ git+https://github.com/EIDR-ID/eidr-core.git@main"
```

or as a line in `requirements.txt` / `pyproject.toml` `dependencies`, with
whichever extras the consumer actually needs (table below).

**Pin to `@main`, not a version tag.** Consumers are expected to track
eidr-core's tip, so that a change to shared logic reaches every consumer in
the same work cycle rather than waiting on a release bump in each one. What
makes that safe is this repo's CI gate: ruff + mypy (a typed contract is
published via `py.typed`) + the full test suite, on both ends of the
supported Python range, with tool versions pinned exactly. Where a
reproducible build genuinely matters, pin a commit SHA (`@<sha>`) instead
and say why in a comment.

If you run mypy against your own code, pin the **same** mypy version this
repo's CI uses. A typed contract written under one mypy and read under
another produces findings in eidr-core's annotations that redden your build
while this repo's CI stays green.

### Extras

The base install has **no third-party dependencies** — every module listed
under "(none)" is stdlib-only.

| Extra | Pulls | Needed for |
|---|---|---|
| *(none)* | — | `codes`, `db_schemas`, `altidtool_io`, `ordering`, `normalize`, `external` (including the retry/failover chassis), `verify`, `inheritance`, and `registry.operation_status` |
| `compare` | rapidfuzz | `eidr_core.compare` (imported at module load) |
| `bmr` | openpyxl | `eidr_core.bmr_io.read_sheet` / `open_sheet` (lazy). `read_headers` / `family_layout` need no extra — they take an already-open worksheet or plain header names |
| `aws` | boto3 | `eidr_core.secrets_loader` AWS path (lazy) |
| `registry` | `eidr[client]` (the EIDR Python SDK, from PyPI) | `eidr_core.registry.get_registry_client` (lazy) |

Extras are additive: `eidr-core[compare,bmr]`.

### Dependency direction

```
consumers ──► eidr-core ──► eidr (the Python SDK, on PyPI)
```

The arrow points one way. The EIDR Python SDK is published to PyPI and
depends only on external packages — never on eidr-core. `eidr_core.registry`
is the model: it wraps `eidr.Client` and imports it lazily.

### For local development on eidr-core itself

```
pip install -e ".[dev]"
pytest tests/ -q
```

Note that an editable install freezes the distribution *metadata* at install
time, so `importlib.metadata.version("eidr-core")` can report a stale number
after a later `git pull`. `eidr_core.__version__` reads the checkout's own
`pyproject.toml` in that mode and is always current — trust it over
`pip show eidr-core`.

## Module map

| Module | Contents |
|---|---|
| `eidr_core.bmr_io` | Workbook surgery (writer primitives: HEADER_ROW, read/count/rightmost/expand family, transplant, fix_shared_strings) **+** the reader half — `open_sheet` (streaming context manager, lazy rows with absolute sheet row numbers), `read_sheet` (a `list()` over it), `read_headers`, sparse `family_layout`, shared `RepeatPlan`/`pad_groups`. Orchestration stays per-consumer by design |
| `eidr_core.compare` | The L2 comparator library: field comparators (`COMPARATORS`, `FieldResult`), episode-aware `titles`, `nonlinear` accumulation; parameters via `set_params()`, driven by `compare-spec.json` (see `compare.spec`) |
| `eidr_core.normalize` | L1 normalization: fold/case/alias/numeral, name/title/code normalizers incl. `norm_country`/`canon_country`, date/duration parsing, `sanitize_field`, `word_alias.csv` |
| `eidr_core.ordering` | Canonical + display ordering key functions per the normalized-record spec (title three-bucket, alt-ID kind/value + display rule, ShortDOI test) |
| `eidr_core.altidtool_io` | AltIDTool input-line format (variable 3/4/5-col compose, tolerant parse; contract in `specs/altidtool-format.md`) |
| `eidr_core.registry` | The SDK client factory (sandbox2 default, credential precedence incl. `.secrets.json` registry section, superparty gate, lazy SDK import) **+** `operation_status` — the three-way success / failed-with-reason / no-verdict-yet parse that mitigates an SDK defect where a rejected write can report as PENDING |
| `eidr_core.inheritance` | Full-record construction: what a child record inherits from its parent (schema `inheritedBaseObjectInfoGroup`) plus the four system-generated title patterns. Two shape adapters over one policy — `build_full_base` (registry JSON) and `build_full_record` (record objects) — plus a per-field `provenance` map. eidr-core imports neither consumer's model |
| `eidr_core.ids` | EIDR **Content ID** syntax + ISO 7064 Mod 37,36 check character (`check_character`, `is_valid_eidr_id`, `fault`). Party IDs (`10.5237/`) are not covered — see the module docstring |
| `eidr_core.codes` | `normalize_country_code`, including the SU→SUHH crosswalk |
| `eidr_core.secrets_loader` | One secrets loader (AWS Secrets Manager + local `.secrets.json`, one section layout) |
| `eidr_core.verify` | External-fact verification primitives — categorical, precision-aware comparison (release-date precision is the asymmetry that makes this a separate engine from `compare`) |
| `eidr_core.db_schemas` | Schema-contract assertions (`assert_tables`) against packaged manifests for the portfolio databases |
| `eidr_core.external` | The shared external-source chassis: `FactCache` protocol + `Null`/`Dict` implementations and the fact-dict contract; retry/backoff + endpoint failover (`external/failover.py`) |

Per-source external clients (Wikidata, TMDb, IMDb) are deliberately **not**
here — each source has exactly one implementation home until a genuine
second consumer appears.

## Repository layout

- `src/eidr_core/` — the LIBRARY tier.
- `specs/` — the SPEC tier: narrative contracts consumable from both Python
  and Node.js. See `specs/README.md`.
- `tests/` — deliberately thin: spec-driven modules are verified by
  consumers' conformance tests instead. Local tests cover the safety
  surfaces whose wrong answer is *silent* (`registry.operation_status`,
  `external.failover`, `inheritance`).

## Contributing

See [`CLAUDE.md`](CLAUDE.md) for the rules that govern changes to shared
code — in particular: propose a change before adopting it, and never ship a
consumer that depends on a proposal that hasn't landed here yet.

## License

MIT — free to use with attribution. See [`LICENSE`](LICENSE).
