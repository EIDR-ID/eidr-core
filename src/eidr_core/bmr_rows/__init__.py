"""BMR row helpers shared by the source tools that build inbound BMR sheets
(reconciliation component C2).

Ruled in eidr-core-ops ``PHASE2-3-INTERFACES-2026-10-15.md`` (C2,
2026-10-17). Routing is ``bmr_io.template_for_creation_type`` and writing is
``bmr_io.write_sheet``; this module holds what eidr-wikidata and eidr-imdb
each re-implemented around them:

* the two unconfirmed-ID columns of ruling R1, which replace
  ``Wikidata's EIDR ID`` (``Assigned EIDR ID`` stays empty: R2);
* ``number_families``: repeating families as numbered columns, extracted
  from eidr-imdb ``sheet.numbered`` (eidr-wikidata numbers inline);
* ``chunk_rows``: the 5,000-row files the BMR tool takes, keeping each
  Series tree whole, extracted from eidr-wikidata ``_split_episodic`` /
  ``_split_non_episodic`` with the ruled change: the limit is a CEILING. A
  chunk closes before a tree that would take it over the limit, where
  eidr-wikidata closed only after reaching it, so its files overshot by the
  rest of the open tree (5,143 rows on 2026-10-16);
* ``join_notes``: one separator for Operator's Notes, the ``SWAPPED:`` note
  first, because BMR-Review's control parses the opening of the cell.

The row defaults that wait on the operator (a silent work's language; the
Registrant and Metadata Authority on inbound sheets) are not here yet, and
neither is the episodic ordering, which lands with the first adoption.
Country of Origin is ``codes.country_list``.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any, TypeVar

from eidr_core.swap import SWAP_NOTE

__all__ = [
    "BMR_ROW_LIMIT",
    "NOTE_SEPARATOR",
    "REGISTRY_IDS_COLUMN",
    "SOURCE_ASSERTED_COLUMN",
    "UNCONFIRMED_ID_COLUMNS",
    "chunk_rows",
    "join_notes",
    "number_families",
    "registry_ids_cell",
]

# Ruling R1 (2026-10-14): appended after the template's columns.
SOURCE_ASSERTED_COLUMN = "Source-Asserted EIDR ID"   # Wikidata P2704; empty for IMDb
REGISTRY_IDS_COLUMN = "Registry EIDR ID(s)"          # records carrying the source ID
UNCONFIRMED_ID_COLUMNS = (SOURCE_ASSERTED_COLUMN, REGISTRY_IDS_COLUMN)

# The BMR tool takes sheets in 5,000-row chunks (plan section 1, step 2).
BMR_ROW_LIMIT = 5_000

NOTE_SEPARATOR = " | "
_SWAP_PREFIX = SWAP_NOTE.split("{", 1)[0]            # "SWAPPED: asserted "

R = TypeVar("R")


def registry_ids_cell(eidr_ids: Iterable[str]) -> str:
    """The ``Registry EIDR ID(s)`` value: the IDs, de-duplicated, sorted,
    joined by ``" | "`` (R1). Sorted so the cell does not change with query
    order; pass ``lookup.claimants`` IDs, which already never choose one."""
    return NOTE_SEPARATOR.join(sorted({i.strip() for i in eidr_ids if i and i.strip()}))


def join_notes(*parts: str | None) -> str:
    """Operator's Notes from its parts: non-empty parts joined by ``" | "``,
    a ``SWAPPED:`` note moved first. eidr-imdb joined with ``" | "`` and
    eidr-wikidata with a space; one form, so a reader can split it."""
    kept = [p.strip() for p in parts if p and p.strip()]
    swapped = [p for p in kept if p.startswith(_SWAP_PREFIX)]
    return NOTE_SEPARATOR.join(swapped + [p for p in kept if p not in swapped])


def number_families(row: Mapping[str, Any],
                    family_members: Mapping[str, Sequence[str]]) -> dict[str, Any]:
    """The row with every family list expanded to ``"<Member> <n>"`` columns,
    the ``{column: value}`` shape ``bmr_io.write_sheet`` takes.

    ``family_members`` maps a key of ``row`` to the member headers its tuples
    fill, in order (``{"country": ("Country of Origin",)}``). Other keys pass
    through. Empty members are omitted, so the writer neither writes empty
    strings nor counts them toward the family's width.
    """
    out: dict[str, Any] = {}
    for key, value in row.items():
        members = family_members.get(key)
        if members is None:
            out[key] = value
            continue
        for i, group in enumerate(value or (), 1):
            for member, v in zip(members, group, strict=False):
                if v not in (None, ""):
                    out[f"{member} {i}"] = v
    return out


def chunk_rows(rows: Sequence[R], *, limit: int = BMR_ROW_LIMIT,
               starts_tree: Callable[[R], bool] | None = None) -> list[list[R]]:
    """Split rows into files of at most ``limit`` rows.

    Without ``starts_tree`` the rows are cut every ``limit`` rows. With it,
    a tree runs from a row it answers True for (a Series) up to the next one,
    and trees are never split: a chunk closes BEFORE a tree that would take
    it over the limit, so every chunk is at most ``limit`` rows except one
    holding a single tree that is itself larger (the caller can find those:
    ``len(chunk) > limit``). Rows before the first tree start (orphans) form
    a group of their own. The rows must already be in tree order.
    """
    if limit < 1:
        raise ValueError("limit must be at least 1")
    if not rows:
        return []
    if starts_tree is None:
        return [list(rows[i:i + limit]) for i in range(0, len(rows), limit)]
    trees: list[list[R]] = []
    for row in rows:
        if not trees or starts_tree(row):
            trees.append([])
        trees[-1].append(row)
    chunks: list[list[R]] = []
    current: list[R] = []
    for tree in trees:
        if current and len(current) + len(tree) > limit:
            chunks.append(current)
            current = []
        current.extend(tree)
    if current:
        chunks.append(current)
    return chunks
