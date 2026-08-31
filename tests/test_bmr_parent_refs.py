"""`Parent EIDR/Row ID` holds EITHER an EIDR ID or a Row ID.

The column name says so, and so does its description in the sheet:
"Usually, the Row ID of the work's Parent record, or the Parent's EIDR ID if
the Parent is not included as a row in the spreadsheet."

A consumer that assumes the cell is always an EIDR ID does not merely lose
the parent link. It loses inheritance and the generated title with it, so a
Season with a Season No. comes out UNTITLED -- dropping the field the de-dup
engine weights most heavily -- and the family gate then reports "different
Family ID (not the same series)" and rejects candidates that ARE the same
series. Observed on row N0008 of PV_EIDR_Episodic_SAMPLE_1000-2, whose parent
cell "S0007" names a row carrying the very EIDR ID the candidate had.
"""
from __future__ import annotations

from eidr_core.bmr_io import (
    ASSIGNED_ID_COLUMN,
    PARENT_COLUMN,
    ROW_ID_COLUMN,
    index_rows,
    parent_chain,
    resolve_parent,
)

SERIES_ID = "10.5240/1FB4-801D-C016-5F48-86E6-9"
OTHER_ID = "10.5240/B0D7-3EB3-AD70-BBBE-B5C9-R"


def _row(rid, parent="", assigned="", **extra):
    r = {ROW_ID_COLUMN: rid, PARENT_COLUMN: parent, ASSIGNED_ID_COLUMN: assigned}
    r.update(extra)
    return r


# --- the reported defect ----------------------------------------------------

def test_a_row_reference_resolves_to_the_parents_assigned_eidr_id():
    """N0008 -> S0007 -> the Series' EIDR ID. The whole point."""
    series = _row("S0007", assigned=SERIES_ID, Title="Drama Total Kids")
    season = _row("N0008", parent="S0007")
    ref = resolve_parent(season, index_rows([series, season]))
    assert ref.eidr_id == SERIES_ID
    assert ref.row is series
    assert ref.raw == "S0007"
    assert ref


def test_an_eidr_id_is_used_directly():
    """The other half of the column's contract: a parent not in the sheet."""
    child = _row("N0001", parent=SERIES_ID)
    ref = resolve_parent(child, index_rows([child]))
    assert ref.eidr_id == SERIES_ID
    assert ref.row is None


# --- the new-registration case ---------------------------------------------

def test_a_parent_row_with_no_id_yet_is_DEFERRED_not_buildable():
    """A Series registered alongside its Seasons has no EIDR ID yet.

    Operator ruling 2026-09-03: that row CANNOT be converted into a full
    metadata record. Not an error -- a deferral. Building from the in-sheet
    row would produce a record whose provenance is a spreadsheet cell while
    looking exactly like one whose provenance is the registry, and a consumer
    cannot tell them apart.

    eidr-core 0.23.0 said the opposite and made this ref TRUTHY, which
    encoded the superseded policy in the API's shape. XML_to_JSON implemented
    that guidance, measured it, and caught the contradiction. This test is the
    corrected contract.
    """
    series = _row("S0001", Title="New Series")
    season = _row("N0001", parent="S0001")
    ref = resolve_parent(season, index_rows([series, season]))

    assert not ref, "a deferred ref must be falsy: it does not license a build"
    assert ref.deferred is True
    assert ref.eidr_id is None
    assert ref.unresolved is False, "deferred is not the same as broken"

    # The row stays reachable -- for REPORTING the deferral and for the second
    # pass, not for building from.
    assert ref.row is series
    # And the raw reference is preserved verbatim so it can be written back.
    assert ref.raw == "S0001"


def test_the_three_outcomes_are_distinguishable():
    """resolved / deferred / unresolved must not collapse into each other."""
    series = _row("S0007", assigned=SERIES_ID)
    pending = _row("S0001")
    resolved = resolve_parent(_row("N1", parent="S0007"),
                              index_rows([series, pending]))
    deferred = resolve_parent(_row("N2", parent="S0001"),
                              index_rows([series, pending]))
    broken = resolve_parent(_row("N3", parent="S9999"),
                            index_rows([series, pending]))

    assert (bool(resolved), resolved.deferred, resolved.unresolved) == (True, False, False)
    assert (bool(deferred), deferred.deferred, deferred.unresolved) == (False, True, False)
    assert (bool(broken), broken.deferred, broken.unresolved) == (False, False, True)

    # Every one of them keeps the original cell, because a Parent ID is
    # converted or left as is -- never dropped.
    assert (resolved.raw, deferred.raw, broken.raw) == ("S0007", "S0001", "S9999")


def test_a_chain_walks_up_through_rows_that_have_no_ids():
    episode = _row("E00001", parent="N0001")
    season = _row("N0001", parent="S0001")
    series = _row("S0001")
    chain = parent_chain(episode, index_rows([episode, season, series]))
    assert [c.raw for c in chain] == ["N0001", "S0001"]


def test_a_chain_stops_when_it_leaves_the_sheet():
    season = _row("N0008", parent="S0007")
    series = _row("S0007", assigned=SERIES_ID, parent=OTHER_ID)
    chain = parent_chain(season, index_rows([season, series]))
    assert [c.raw for c in chain] == ["S0007", OTHER_ID]
    assert chain[-1].row is None


# --- the ways a hand-edited sheet goes wrong --------------------------------

def test_a_row_id_that_is_not_in_the_sheet_is_reported_unresolved():
    child = _row("N0001", parent="S9999")
    ref = resolve_parent(child, index_rows([child]))
    assert ref.unresolved is True
    assert ref.eidr_id is None and ref.row is None
    assert not ref


def test_a_mistyped_eidr_id_is_unresolved_not_passed_through():
    """Bad check character. Reporting it beats handing on an impossible parent."""
    bad = SERIES_ID[:-1] + "X"
    child = _row("N0001", parent=bad)
    ref = resolve_parent(child, index_rows([child]))
    assert ref.unresolved is True
    assert ref.eidr_id is None


def test_row_ids_match_case_insensitively_and_ignore_padding():
    series = _row("S0007", assigned=SERIES_ID)
    season = _row("N0008", parent="  s0007 ")
    ref = resolve_parent(season, index_rows([series, season]))
    assert ref.eidr_id == SERIES_ID


def test_an_empty_parent_cell_is_a_root_not_an_error():
    ref = resolve_parent(_row("S0001"), index_rows([]))
    assert not ref
    assert ref.raw == "" and ref.unresolved is False


def test_a_cycle_terminates():
    a = _row("A", parent="B")
    b = _row("B", parent="A")
    chain = parent_chain(a, index_rows([a, b]))
    assert [c.raw for c in chain] == ["B", "A"]


def test_a_self_reference_terminates():
    a = _row("A", parent="A")
    assert [c.raw for c in parent_chain(a, index_rows([a]))] == ["A"]


def test_a_duplicate_row_id_keeps_the_first():
    """A later row must not silently capture children of an earlier one."""
    first = _row("S0007", assigned=SERIES_ID)
    second = _row("S0007", assigned=OTHER_ID)
    assert index_rows([first, second])["s0007"] is first
