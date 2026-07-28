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
| `compare-spec.json` (+ `compare-spec.md`) | **Versioned** runtime config of the unified engine (per `unified-scoring.md`): per-creation-type weights, calibration thresholds, gate constants, band edges, q→state banding, normalization semantics. Generated from BMR-Review `config.py` in migration step 2. | BMR-Review `config.py` + De-Dupe UI declarative-config discipline |
| `golden-pairs/` | Conformance corpus: record pairs with expected per-field comparator outputs and total-score bands, versioned WITH the compare-spec | Every scoring bug fixed anywhere becomes a permanent pair (SU/SUHH, epoch dates, homoglyph titles, ...) |
| `dedupe-worklist.md` | ✅ **LANDED (v1, 2026-07-27)** — work-list / results / supplement JSONL formats incl. the per-candidate scoring payload (score, band, field states+qualities, rationale) shared verbatim with Shim-mode; unscored-request flow; decisions carry engine context for the eval set | Operator design 2026-07-18 + unified-scoring §3 |
| `altidtool-format.md` | The AltIDTool 5-column TSV contract | eidr-wikidata `bmr/altidtool.py` behavior |
| `mirror-schema/` | The `eidr_mirror_db` DDL as single source of truth (EIDR MCP's `EXPECTED_SCHEMA` and all readers derive from it) | EIDR MCP `db/` DDL |

## The sync mechanism

Each program carries ONE conformance test that runs its own engine against
`golden-pairs/` at the pinned spec version. Whoever tunes rules or weights:

1. edits `compare-spec.json`,
2. bumps its version,
3. regenerates golden-pair expectations.

Every sibling's conformance test then fails until that program adopts the
change. **The failing test is the cross-project alert** — no additional
process required.
