# specs/ — language-neutral shared contracts

Everything in this directory is consumable from BOTH the Python suite and
the node.js side (eidr-ui-nextjs modules such as De-Dupe UI). This is the
bridge tier: UI projects share requirements and specifications with the
Python programs, never code.

## Planned artifacts (Phase 2 of the overlap register)

| Artifact | Contents | Seeded from |
|---|---|---|
| `normalized-record.md` | ✅ **LANDED (v1 draft, 2026-07-27)** — field model + canonical ordering; documents & resolves the two XML_to_JSON↔BMR-Review divergences (title order, alt-ID order). Awaiting operator ratification of §4/§6. | XML_to_JSON codec + BMR-Review `render_record` |
| `compare-spec.json` (+ `compare-spec.md`) | **Versioned** comparison rules: per-field comparator, weights, thresholds (e.g. Jaro-Winkler 0.94), tolerance windows (e.g. runtime ±max(5 min, 10%)), epoch-date handling, normalization semantics | BMR-Review current tuning + De-Dupe UI `review_score_rules.json` / `review_comparison_rules.json` |
| `golden-pairs/` | Conformance corpus: record pairs with expected per-field comparator outputs and total-score bands, versioned WITH the compare-spec | Every scoring bug fixed anywhere becomes a permanent pair (SU/SUHH, epoch dates, homoglyph titles, ...) |
| `dedupe-worklist.md` | De-Dupe UI local work-list file format (produced by BMR-Review) and results-file format (appended by the UI as the operator progresses) | Operator design, 2026-07-18 — the UI's 4th data-source option |
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
