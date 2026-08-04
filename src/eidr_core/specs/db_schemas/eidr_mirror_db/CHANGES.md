# eidr_mirror_db schema changes

## 2026.08.03-1 — alias tracking
(from 2026.08.03)
* ADDED table alias_log (id serial PK, content_id UNIQUE, creation_type,
  logged_at DEFAULT now; index on logged_at DESC). Written by MCP before
  record deletion (alias tracking, MCP commit 7d0e02a); excluded from
  TRUNCATABLE/DELETABLE. Retroactive entry: the manifest edit predated
  the live table; the table was created 2026-08-03 with a corrected DDL
  (the hand-written contract omitted the id SET DEFAULT nextval, which
  would have failed MCP's insert path) and the contract regenerated from
  the live DB.

## 2026.08.03 — 2026-08-03T16:30:17+00:00
(from 2026.08.03) No structural changes; regenerated.

