"""Unified secrets loading (planned; not yet extracted).

Will hold: one loader supporting AWS Secrets Manager and local
``.secrets.json``, with ONE documented section layout (mirror_db, dq_db,
registry, smtp, ...).

Replaces three conventions: EIDR MCP (``EIDR_MCP_Secrets`` /
``USE_LOCAL_SECRETS``), eidr-dq (``EIDR_DQ_Secrets``; XML_to_JSON carries
a literal copy of this loader), eidr-wikidata (local ``.secrets.json``
only, trailing-comma tolerant).
"""
