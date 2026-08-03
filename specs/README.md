# specs/ — language-neutral shared contracts

Everything in this directory is consumable from BOTH the Python suite and
the node.js side (eidr-ui-nextjs modules such as De-Dupe UI). This is the
bridge tier: UI projects share requirements and specifications with the
Python programs, never code.

## Planned artifacts (Phase 2 of the overlap register)

| Artifact | Contents | Seeded from |
|---|---|---|
| `normalized-record.md` | ✅ **LANDED (v1 draft, 2026-07-27)** — field model + canonical ordering; documents & resolves the two XML_to_JSON↔BMR-Review divergences (title order, alt-ID order). Awaiting operator ratification of §4/§6. | XML_to_JSON codec + BMR-Review `render_record` |
| `unified-scoring.md` | ✅ **APPROVED 2026-07-27** — ONE match-candidate scoring engine (layered; L3 seeded from BMR-Review; states = banded qualities; UI consumes engine payloads; per-creation-type weights preserved as the tuning structure). Migration §6 active. | BMR-Review engine + De-Dupe UI spec v1.4.5→v1.4.6 |
| `compare-spec.json` (+ `compare-spec.md`) | ✅ **LANDED v2.0.0 (2026-07-28)** — THE tuning surface. Runtime file is packaged at `src/eidr_core/specs/compare-spec.json` (importlib.resources-locatable; `EIDR_COMPARE_SPEC` override); `compare-spec.md` here carries the curated rationale + tuning workflow. BMR-Review `config.py` is now a loader shim. | BMR-Review `config.py` (1:1) + De-Dupe UI declarative-config discipline |
| `golden_pairs/` | ✅ **LANDED (2026-07-29)** — 8 seed pairs at `src/eidr_core/specs/golden_pairs/*.json`, each pinning a learned lesson (`why`) with version-INDEPENDENT `invariants` + an exact `expected` snapshot at the current compare-spec version. Conformance: BMR-Review `tests/test_golden_pairs.py`; regeneration: `regen_golden_pairs.py` (refuses pairs whose lessons a tune breaks). Every scoring bug fixed anywhere becomes a permanent pair. | SU≡SUHH, epoch dates, corroboration, part numbers, format sales, early cinema, alt-ID conflict shaping, baseline Accept |
| `altid-display-order.md` + `title-display-order.md` | ✅ **API Shim handoffs (2026-07-29/30)** — the two ratified DISPLAY orders (Alt IDs: ShortDOI suppressed, IMDb first, then (kind, value); Titles: three buckets, ResourceName first even when Internal, SystemGenerated/Internal visually marked). the matching system presents in Shim order → the Shim emits these. Worked examples verified against the reference implementation (BMR-Review `render_record`). | normalized-record.md §4.1/§4.2 |
| `dedupe-worklist.md` | ✅ **LANDED (v1, 2026-07-27)** — work-list / results / supplement JSONL formats incl. the per-candidate scoring payload (score, band, field states+qualities, rationale) shared verbatim with Shim-mode; unscored-request flow; decisions carry engine context for the eval set | Operator design 2026-07-18 + unified-scoring §3 |
| `altidtool-format.md` | The AltIDTool 5-column TSV contract | eidr-wikidata `bmr/altidtool.py` behavior |
| `mirror-schema.md` (→ `mirror-schema/`) | ⚠ **DESIGN DRAFTED 2026-08-03, awaiting operator review** — canonical DDL + generated JSON manifest + date version; MCP validator re-sourced; three drifted DDL copies retired; optional reader startup assertions | live `eidr_mirror_db` (ground truth) |

## The sync mechanism

Each program carries ONE conformance test that runs its own engine against
`golden-pairs/` at the pinned spec version. Whoever tunes rules or weights:

1. edits `compare-spec.json`,
2. bumps its version,
3. regenerates golden-pair expectations.

Every sibling's conformance test then fails until that program adopts the
change. **The failing test is the cross-project alert** — no additional
process required.
