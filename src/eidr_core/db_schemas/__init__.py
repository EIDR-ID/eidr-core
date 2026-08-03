"""Portfolio database schema contracts — consumer access (register 2.4).

The contracts (generated FROM the live databases, the authoritative source —
operator 2026-08-03) are packaged at ``eidr_core/specs/db_schemas/<db>/``:
``manifest.json`` (machine contract), ``schema.sql`` (human/provisioning
form), ``CHANGES.md``. Regeneration + drift checking:
``eidr-core/tools/dump_db_schema.py``.

Consumers use :func:`assert_tables` as a STARTUP assertion — declare only the
tables/columns your program actually reads, and schema breakage surfaces at
startup with a clear message naming the contract version, instead of as a
mid-run SQL error. This is deliberately the whole API: no typed models, no
query layer (register decision, reaffirmed 2026-08-03).

    from eidr_core.db_schemas import assert_tables
    assert_tables("eidr_mirror_db", {
        "content_core": ["content_id", "referent_type", "release_date"],
        "content_titles": ["content_id", "title", "title_class"],
    })
"""
from __future__ import annotations

import json
from functools import lru_cache
from importlib.resources import files

DATABASES = ("eidr_mirror_db", "eidr_dq_db", "language_registry")


@lru_cache(maxsize=None)
def load_manifest(database: str) -> dict:
    """Load a database's schema manifest. Raises KeyError for unknown names."""
    if database not in DATABASES:
        raise KeyError(f"unknown database {database!r}; known: {DATABASES}")
    p = files("eidr_core") / "specs" / "db_schemas" / database / "manifest.json"
    return json.loads(p.read_text(encoding="utf-8"))


def contract_version(database: str) -> str:
    return load_manifest(database)["version"]


def table_columns(database: str, table: str) -> list[str]:
    """Column names of a table per the contract (KeyError if absent)."""
    return [c["name"] for c in load_manifest(database)["tables"][table]["columns"]]


def assert_tables(database: str, needs: dict) -> None:
    """Assert that every table/column this consumer NEEDS exists in the
    contract. ``needs`` = {table: [column, ...]} (empty list = table
    presence only). Raises RuntimeError listing every miss, with the
    contract version so the operator knows which schema change to look at."""
    m = load_manifest(database)
    problems = []
    for table, cols in needs.items():
        entry = m["tables"].get(table)
        if entry is None:
            problems.append(f"table {table!r} missing")
            continue
        have = {c["name"] for c in entry["columns"]}
        for col in cols or []:
            if col not in have:
                problems.append(f"{table}.{col} missing")
    if problems:
        raise RuntimeError(
            f"{database} schema contract {m['version']} does not satisfy this "
            f"consumer: " + "; ".join(problems) +
            ". See eidr-core specs/db_schemas/" + database + "/CHANGES.md.")
