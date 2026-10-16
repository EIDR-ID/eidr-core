"""The non-Abstraction swap and its ``SWAPPED:`` note (reconciliation C9).

Operator rulings 2026-09-13 and 2026-09-21: a source ID (an IMDb title, a
Wikidata item) belongs on a TITLE record, an Abstraction. When the record
claiming it is a Performance, Edit or Manifestation, the row still asks
BMR-Review about the source ID but proposes the Abstraction ancestor instead,
and ``Operator's Notes`` opens with the fixed ``SWAPPED:`` note so the
reviewer sees the substitution and can still name the original. A claimant
with no valid Abstraction ancestor goes to the Help-Desk path. A claimant
with no structural type is kept: NULL means the mirror does not say.

That is all of it, and the simplicity is the operator's. Two refinements
were proposed and overruled, recorded so nobody rebuilds them: keeping the
part's row unswapped with a PART-OF note where the Abstraction already
claims the same ID, and dropping the part's row in that case. "The submitted
record does not go away -- we just change the proposed EIDR ID match"; "if
we end up with multiple rows that have the same ... ID, BMR-Review will
decide how we map them". Nothing here drops or de-duplicates.

Extracted 2026-10-16 from the two copies the plan found duplicated: eidr-imdb
``sheet.SWAP_NOTE`` / ``plan_non_abstraction`` / ``abstraction_ancestors``
and eidr-wikidata ``bmr/one_sided.SWAP_NOTE`` / ``split_non_abstraction`` /
``MirrorClient.resolve_abstraction_ancestor``, checked against both before
release. eidr-wikidata's rule that a VERIFIED pairing is never re-pointed is
the ``verified`` parameter.
"""
from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping
from typing import Any

__all__ = [
    "HELPDESK",
    "KEEP",
    "SWAP",
    "SWAP_NOTE",
    "abstraction_ancestors",
    "plan_swaps",
    "swap_note",
]

#: The fixed form BMR-Review's "Swapped original" control parses
#: (dedup_review_ui.html). Changing a word here silently removes that control.
SWAP_NOTE = ("SWAPPED: asserted {asserted} ({structural_type}) -> "
             "Abstraction ancestor {ancestor}")

KEEP, SWAP, HELPDESK = "keep", "swap", "helpdesk"

# One literal query per mirror table whose parent_id leads towards the
# Abstraction (eidr-imdb kept them literal so its schema scan can see them).
_PARENT_SQL = (
    "SELECT content_id, parent_id FROM edits WHERE content_id = ANY(%s)",
    "SELECT content_id, parent_id FROM manifestations WHERE content_id = ANY(%s)",
    "SELECT content_id, parent_id FROM clips WHERE content_id = ANY(%s)",
)


def swap_note(asserted: str, structural_type: str, ancestor: str) -> str:
    """The ``SWAPPED:`` note for one row, in the fixed form."""
    return SWAP_NOTE.format(asserted=asserted, structural_type=structural_type,
                            ancestor=ancestor)


def plan_swaps(claims: Iterable[tuple[str, str]],
               structural_types: Mapping[str, str | None],
               ancestors: Mapping[str, str | None], *,
               verified: Collection[tuple[str, str]] = frozenset(),
               ) -> dict[tuple[str, str], tuple[str, str | None]]:
    """Decide every ``(source_id, eidr_id)`` claim: ``{claim: (decision, ancestor)}``.

    KEEP for an Abstraction, an unknown type, or a ``verified`` claim (a
    pairing a human approved is never re-pointed: the verified list holds
    deliberate IDs on Performances); SWAP with the ancestor for any other
    claimant that has one; HELPDESK for one that does not. The decision never
    looks at the other claimants of the same source ID. Pure.
    """
    plan: dict[tuple[str, str], tuple[str, str | None]] = {}
    for claim in claims:
        _source_id, eidr_id = claim
        structural_type = structural_types.get(eidr_id)
        if not structural_type or structural_type == "Abstraction" or claim in verified:
            plan[claim] = (KEEP, None)
            continue
        ancestor = ancestors.get(eidr_id)
        plan[claim] = (SWAP, ancestor) if ancestor else (HELPDESK, None)
    return plan


def _rows(conn, sql: str, params: tuple) -> list[tuple[Any, ...]]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return [tuple(r.values()) if isinstance(r, dict) else tuple(r)
                for r in cur.fetchall()]


def abstraction_ancestors(eidr_ids: Iterable[str], *, conn,
                          max_depth: int = 12) -> dict[str, str | None]:
    """The first VALID Abstraction above each record, or None.

    A loop, not a single hop: the mirror holds 5,366 edits whose parent is an
    edit and 32,723 manifestations whose parent is an edit (eidr-wikidata,
    2026-09-20). A non-``valid`` ancestor counts as no ancestor: after a swap
    the row names the ancestor, and a batch names only valid records. The
    walk starts at each record's PARENT; ask only about non-Abstractions.
    One query per child table and one status query per level.
    """
    ids = list(dict.fromkeys(i for i in eidr_ids if i))
    found: dict[str, str | None] = {}
    frontier = {i: i for i in ids}              # original -> current position
    for _ in range(max_depth):
        if not frontier:
            break
        current = sorted(set(frontier.values()))
        parents: dict[str, str] = {}
        for sql in _PARENT_SQL:
            parents.update({cid: p for cid, p in _rows(conn, sql, (current,)) if p})
        wanted = sorted({parents[c] for c in frontier.values() if c in parents})
        facts = ({cid: (st, status) for cid, st, status in _rows(
            conn, "SELECT content_id, structural_type, status FROM content_core "
                  "WHERE content_id = ANY(%s)", (wanted,))} if wanted else {})
        nxt: dict[str, str] = {}
        for original, cur in frontier.items():
            parent = parents.get(cur)
            if not parent or parent not in facts:
                found[original] = None
                continue
            structural_type, status = facts[parent]
            if structural_type == "Abstraction":
                found[original] = parent if status == "valid" else None
            else:
                nxt[original] = parent
        frontier = nxt
    for original in frontier:                   # ran out of depth: a cycle
        found[original] = None
    return found
