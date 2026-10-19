"""db_schemas: the contract cannot be changed by one of its readers (0.68.0).

Why: ``load_manifest`` was ``functools.cache``d and returned the cached dict,
so a caller that mutated its result changed the contract for every later
caller in the process -- ``assert_tables`` then passed or failed on the
mutation, not on the schema (dictionary audit 2026-10-02).
"""
from __future__ import annotations

import pytest

from eidr_core.db_schemas import (
    DATABASES,
    assert_tables,
    contract_version,
    load_manifest,
    table_columns,
)

DB = "eidr_dq_db"


def test_mutating_a_loaded_manifest_does_not_reach_later_callers():
    first = load_manifest(DB)
    n_tables = len(first["tables"])
    table = next(iter(first["tables"]))
    cols = table_columns(DB, table)
    version = contract_version(DB)

    first["tables"].clear()
    first["version"] = "mutated"

    again = load_manifest(DB)
    assert again is not first
    assert len(again["tables"]) == n_tables
    assert table_columns(DB, table) == cols
    assert contract_version(DB) == version
    assert_tables(DB, {table: cols})   # still satisfied by the real contract


def test_nested_values_are_copied_too():
    a = load_manifest(DB)
    table = next(iter(a["tables"]))
    a["tables"][table]["columns"].clear()
    assert load_manifest(DB)["tables"][table]["columns"]


def test_unknown_database_still_raises_keyerror():
    with pytest.raises(KeyError):
        load_manifest("no_such_db")


def test_assert_tables_points_at_the_packaged_changes_file():
    for db in DATABASES:
        with pytest.raises(RuntimeError) as e:
            assert_tables(db, {"no_such_table_xyz": []})
        assert f"src/eidr_core/specs/db_schemas/{db}/CHANGES.md" in str(e.value)
