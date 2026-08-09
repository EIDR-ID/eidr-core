# specs/ — language-neutral shared contracts

Everything in this directory is consumable from BOTH the Python suite and
the node.js side (eidr-ui-nextjs modules such as De-Dupe UI). This is the
bridge tier: UI projects share requirements and specifications with the
Python programs, never code.

## Artifacts (Phase 2 of the overlap register — complete)

| Artifact | Contents | Seeded from |
|---|---|---|
| `normalized-record.md` | ✅ **RATIFIED with amendments (2026-07-29)** — field model + canonical ordering; the two XML_to_JSON↔BMR-Review divergences resolved and IMPLEMENTED via `eidr_core.ordering` (0.2.0, both consumers wired); §7 engine gaps flagged for the next tune cycle | XML_to_JSON codec + BMR-Review `render_record` (both now import the shared module) |
| `unified-scoring.md` | ✅ **APPROVED 2026-07-27** — ONE match-candidate scoring engine (layered; L3 seeded from BMR-Review; states = banded qualities; UI consumes engine payloads; per-creation-type weights preserved as the tuning structure). Migration §6 active. | BMR-Review engine + De-Dupe UI spec v1.4.5→v1.4.6 |
| `compare-spec.json` (+ `compare-spec.md`) | ✅ **LANDED v2.0.0 (2026-07-28)** — THE tuning surface. Runtime file is packaged at `src/eidr_core/specs/compare-spec.json` (importlib.resources-locatable; `EIDR_COMPARE_SPEC` override); `compare-spec.md` here carries the curated rationale + tuning workflow. BMR-Review `config.py` is now a loader shim. | BMR-Review `config.py` (1:1) + De-Dupe UI declarative-config discipline |
| `golden_pairs/` | ✅ **LANDED (2026-07-29)** — 8 seed pairs at `src/eidr_core/specs/golden_pairs/*.json`, each pinning a learned lesson (`why`) with version-INDEPENDENT `invariants` + an exact `expected` snapshot at the current compare-spec version. Conformance: BMR-Review `tests/test_golden_pairs.py`; regeneration: `regen_golden_pairs.py` (refuses pairs whose lessons a tune breaks). Every scoring bug fixed anywhere becomes a permanent pair. | SU≡SUHH, epoch dates, corroboration, part numbers, format sales, early cinema, alt-ID conflict shaping, baseline Accept |
| `altid-display-order.md` + `title-display-order.md` | ✅ **API Shim handoffs (2026-07-29/30)** — the two ratified DISPLAY orders (Alt IDs: ShortDOI suppressed, IMDb first, then (kind, value); Titles: three buckets, ResourceName first even when Internal, SystemGenerated/Internal visually marked). the matching system presents in Shim order → the Shim emits these. Worked examples verified against the reference implementation (BMR-Review `render_record`). | normalized-record.md §4.1/§4.2 |
| `dedupe-worklist.md` | ✅ **LANDED (v1, 2026-07-27)** — work-list / results / supplement JSONL formats incl. the per-candidate scoring payload (score, band, field states+qualities, rationale) shared verbatim with Shim-mode; unscored-request flow; decisions carry engine context for the eval set | Operator design 2026-07-18 + unified-scoring §3 |
| `altidtool-format.md` | ✅ **RULED 2026-08-05** — variable 3/4/5-column format, no trailing tabs; implemented as `eidr_core.altidtool_io`. BMRtoAltID's fixed-5 dialect stays a separate, deliberate choice pending its own convergence decision (register R9) | eidr-wikidata `bmr/altidtool.py` behavior |
| `db-schema-contracts.md` + `src/eidr_core/specs/db_schemas/` | ✅ **APPROVED & LANDED 2026-08-03** — schema contracts for ALL THREE DBs (mirror 48 / dq 17 / language 7 tables): manifest + DDL + CHANGES, date-versioned, generated from the live DBs by `tools/dump_db_schema.py` (`--check` = drift alarm); consumers assert via `eidr_core.db_schemas.assert_tables` | live databases (authoritative) |

## The sync mechanism

Each program carries ONE conformance test that runs its own engine against
`golden-pairs/` at the pinned spec version. Whoever tunes rules or weights:

1. edits `compare-spec.json`,
2. bumps its version,
3. regenerates golden-pair expectations.

Every sibling's conformance test then fails until that program adopts the
change. **The failing test is the cross-project alert** — no additional
process required.
