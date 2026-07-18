"""EIDR registry SDK client factory (planned; not yet extracted).

Portfolio policy (2026-07-18): ALL registry API interaction goes through
the official Python SDK. The mirror DB connection is excluded (Postgres,
not the registry API).

Seed: eidr-wikidata ``src/eidr_wikidata/eidr/registry_client.py`` — one
place for registry-target selection (sandbox2 default; production is an
explicit operator choice), credential precedence, and the superparty write
gate. eidr-dq's read-only ``registry_sync_verify._make_client`` adopts
this on extraction.

The SDK itself will separately grow pull-mirror (txn feed) and
registry-dump-file ingest surfaces; EIDR MCP is not being ported.
"""
