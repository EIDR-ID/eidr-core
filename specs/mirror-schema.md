# Mirror Schema Contract (`eidr_mirror_db`) — DESIGN for operator review

**Status: DRAFT (register Phase 2.4, 2026-08-03). No code changed.** This is
the design-before-touching document the register requires for the
portfolio's highest-blast-radius contract. Nothing here executes until the
operator approves §6 and answers §7.

## 1. The problem, with evidence

One writer, four readers, and **no single authority** for what the mirror
schema *is*. Found on disk today:

| Artifact | Where | State |
|---|---|---|
| The live database | PostgreSQL `eidr_mirror_db` | ground truth by definition |
| `EXPECTED_SCHEMA` dict | `MCP/src/eidr/config.py:74` | hand-maintained tables→columns map; `_self` twins generated in code; used by `schema_validator.py` at MCP startup |
| `db/eidr_mirror_db.sql` | MCP repo | 843 lines — appears to be an OLDER vintage |
| `src/eidr_mirror_db.sql` | MCP repo | 1,165 lines — different hash from db/ copy |
| `eidr_mirror_db.sql` | XML_to_JSON repo | 1,165 lines — same length as MCP/src but **content differs throughout** (drifted copy) |

Meanwhile each reader hardcodes its own column knowledge (distinct mirror
table names referenced): eidr-wikidata `mirror_client.py` ~16, BMR-Review
`mirror.py` ~21, XML_to_JSON exporter ~33, eidr-dq's rule SQL ~36 across ~66
rules. A column MCP renames breaks up to four programs, each discovering it
as a mid-run SQL error.

## 2. Goal and non-goal

**Goal:** ONE authoritative, versioned schema contract in eidr-core;
everything else (MCP's validator, the stray DDL copies, reader assumptions)
either derives from it or is validated against it — with schema changes
surfacing as clear, early alerts in every consumer.

**Explicit non-goal (register decision, reaffirmed):** NO shared
mirror-access library, typed row models, or query layer. Contract only.
Readers keep their own SQL.

## 3. The canonical artifacts (proposed)

Live in this repo, versioned together:

```
specs/mirror-schema/
  eidr_mirror_db.sql        # normalized pg_dump --schema-only of the live mirror
  mirror-schema.json        # generated manifest: {version, generated_at,
                            #   tables: {name: {columns: [{name, type, nullable}...]}}}
  CHANGES.md                # per-version: what changed, which tables, who is affected
```

* The **DDL** is for humans and for standing up a fresh mirror.
* The **JSON manifest** is the machine contract — what validators and
  startup assertions read. Generated FROM the DDL/live DB, never hand-edited.
* **Version** = date-based (`2026.08.03`) bumped on any schema change;
  consumers report it, same pattern as `compare-spec.json`.

Generation tool: a small script (proposed home: `MCP/db/dump_schema.py`,
since MCP owns the credentials and the schema) that runs
`pg_dump --schema-only`, normalizes (strip owner/grant noise, stable
ordering), emits both artifacts into eidr-core, and prints the diff vs the
previous version for the CHANGES entry.

## 4. Consumer adoption (each step independent)

| Consumer | Change | Effect |
|---|---|---|
| **EIDR MCP** | `EXPECTED_SCHEMA` loaded from `mirror-schema.json` instead of the hand-kept dict (the `_self`-twin generation logic is subsumed — the manifest lists every table explicitly). `schema_validator.py` mechanics unchanged. DELETE both local DDL copies. | MCP validates the live DB against the same contract everyone else reads; the hand-dict can no longer drift from the DDL. |
| **XML_to_JSON** | DELETE its `eidr_mirror_db.sql` copy; reference the spec. | One fewer drifted copy. |
| **Readers (all four)** | OPTIONAL, opportunistic: a tiny startup assertion — declare the tables/columns that reader actually uses and check them against the manifest (offline) or `information_schema` (live). Future helper `eidr_core.mirror_schema.assert_tables(needs)` (~40 lines); until then even a per-repo 10-line check suffices. | Schema breakage surfaces at STARTUP with "table X lost column Y (schema 2026.08.03 → 2026.09.01)" instead of a mid-run SQL error. |

## 5. Change workflow (the alert mechanism)

1. A schema change is made in MCP (the only legitimate origin).
2. Operator (or MCP tooling) runs the dump script → new DDL + manifest +
   version bump + `CHANGES.md` entry naming affected tables → commit/push
   eidr-core.
3. Consumers learn three ways: (a) their startup assertions fail loudly if a
   table/column they declared is gone/changed; (b) the `CHANGES.md` entry
   names affected tables so the operator can relay targeted warnings via
   CLAUDE.md change logs; (c) MCP's own validator confirms the live DB
   matches the published contract after migration.

Same philosophy as the compare-spec/golden-pair loop: the version bump is
the signal; a stale consumer fails a check, not a production run.

## 6. Decision requested

Approve: (a) canonical home `eidr-core/specs/mirror-schema/` with
DDL + generated JSON manifest + date version; (b) dump-script approach with
MCP as the generation point; (c) MCP's `EXPECTED_SCHEMA` re-sourced from the
manifest and the three stray DDL copies deleted; (d) reader startup
assertions as optional/opportunistic (no shared access library).

## 7. Open questions for the operator

1. **Ground truth to dump from:** the production mirror DB, correct? (Not
   one of the divergent DDL files.)
2. **MCP's two DDL copies:** is `src/` (1,165 lines) the current one and
   `db/` (843) stale — or does `db/` serve a distinct purpose (e.g. minimal
   bootstrap)? Both are proposed for deletion after the canonical lands.
3. **Schema-change cadence:** are changes rare enough that a manual
   dump-script run per change is acceptable (recommended), or should MCP
   run it automatically at startup when validation detects drift?
4. **The MySQL export kit** (`MCP/src/export/schema_mysql.sql`): in or out
   of scope? (Proposed: out — it's a one-off migration artifact.)
5. Any consumers of the DDL files I haven't found (docs, provisioning
   scripts, other machines)?
