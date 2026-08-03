# Database Schema Contracts — mirror, DQ, language (register 2.4)

**Status: ✅ APPROVED (operator, 2026-08-03) and LANDED.** Supersedes the
`mirror-schema.md` draft; scope expanded per the approval: **all three
portfolio databases, one pattern.**

## The contracts

Generated FROM the live databases — the authoritative source (§7.1) — and
packaged so every consumer locates them via importlib.resources:

| Database | Owner/writer | Contract | Change cadence |
|---|---|---|---|
| `eidr_mirror_db` (48 tables) | EIDR MCP | `src/eidr_core/specs/db_schemas/eidr_mirror_db/` | rare |
| `eidr_dq_db` (17 tables) | eidr-dq | `…/eidr_dq_db/` | infrequent (most active of the three) |
| `language_registry` (7 tables) | LanguageCode | `…/language_registry/` | rare |

Each directory: `manifest.json` (the machine contract: tables → columns with
type + nullability, date version, provenance), `schema.sql` (normalized
`pg_dump --schema-only`, the human/provisioning form), `CHANGES.md`
(per-version entries naming changed tables).

## Tooling

* **Regenerate** (deliberate act, part of any schema change):
  `python eidr-core/tools/dump_db_schema.py --db {mirror|dq|language}` —
  dumps live DB → manifest + DDL, bumps the date version, prepends the
  CHANGES entry with the computed table/column diff. Commit + push eidr-core.
* **Drift check**: same tool with `--check` — compares the live DB to the
  committed contract; exit 1 = "the published contract is stale."
* **Consumer assertion**: `eidr_core.db_schemas.assert_tables(db, needs)` —
  a reader declares only the tables/columns it actually uses and gets a
  startup-time failure naming the contract version instead of a mid-run SQL
  error. First adopter: BMR-Review (`tests/test_db_schemas.py::MIRROR_NEEDS`
  doubles as its declaration). No typed models, no query layer — reaffirmed.

## Design amendments vs the draft (operator Q&A, 2026-08-03)

1. **`EXPECTED_SCHEMA` stays code-owned in MCP** (draft had proposed
   re-sourcing it from the manifest). Two reasons: the operator clarified its
   purpose — it declares what the CODE expects, so live-DB divergence flags a
   code-synchronization issue — and inspection showed its keys also derive
   MCP's TRUNCATABLE/DELETABLE table lists, so sourcing it from a DB dump
   would put unmanaged tables into destructive-operation lists. Instead,
   MCP's `schema_validator` gained an ADDITIVE, warn-only
   **contract-freshness check**: live DB vs the published contract, catching
   "DB changed but nobody regenerated" — the failure mode that would strand
   readers on a stale contract. (Gracefully skipped if eidr-core is absent.)
2. **Stray DDL copies retired**: MCP `src/eidr_mirror_db.sql` (out of date —
   operator deleted), XML_to_JSON's copy (outdated — operator deleted), and
   MCP `db/eidr_mirror_db.sql` (was current, manually maintained — deleted
   2026-08-03 now that the generated contract + dump tool replace the manual
   workflow; recoverable from MCP git history). **The manual-update workflow
   is replaced by running the dump tool.**
3. **Reader list includes match-audit** (§7.5) — folded into BMR-Review; its
   audit path reads the mirror through the same package, so BMR-Review's
   assertion covers it.
4. **MySQL export kit: out of scope** (§7.4).
5. Owner provisioning/bootstrap scripts (e.g. eidr-dq's `db/eidr_dq_db.sql`,
   which also seeds reference data) remain in their repos where genuinely
   needed for CREATION; the eidr-core contract is what CONSUMERS build
   against, and `--check` is the drift alarm between the two.

## Change workflow (the alert loop)

1. Schema change happens in the owner program (MCP / eidr-dq / LanguageCode).
2. Owner (or operator) runs the dump tool for that DB → version bump +
   CHANGES entry → commit/push eidr-core.
3. Consumers learn via: their `assert_tables` startup checks / test suites;
   the CHANGES entry naming affected tables (operator relays targeted
   warnings via CLAUDE.md change logs); and MCP's freshness warning if
   regeneration was forgotten.
