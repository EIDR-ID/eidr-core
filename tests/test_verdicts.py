"""eidr_core.verdicts: the shared verdict resolver (C4, 2026-10-15).

Extracted from BMRtoAltID's ``bmr_altid/verdicts.py``; before release its own
60 verdict tests were run against this module (aliased in place of theirs)
and passed, and every assessed sheet on this machine resolved identically
through both. These tests pin, here, the rules whose wrong answer is silent
(a row resolved to the record a human rejected looks like a good fill), and
the two parameters the extraction added.
"""
from __future__ import annotations

import pytest

from eidr_core import verdicts as V

E1 = "10.5240/7791-8534-2C23-9030-8610-5"
E2 = "10.5240/FB57-D43B-1EED-CAD7-929C-N"


def test_the_ids_used_here_are_valid():
    assert V.read_asserted_id(E1).value == E1 and V.read_asserted_id(E2).value == E2


def test_match_not_listed_with_a_blank_match_never_falls_back_to_the_proposal():
    """THE TRAP: the blank means 'not among those shown'."""
    got = V.resolve_row({"EIDR Assessment": "Accept: sole match", "EIDR Proposed Match": E1,
                         "Human Review": "MATCH_NOT_LISTED"}, 4)
    assert got.status == "UNRESOLVED" and got.resolved_id == ""


def test_a_named_record_under_match_not_listed_is_used_unless_it_is_the_proposal():
    row = {"EIDR Assessment": "Review", "EIDR Proposed Match": E1,
           "Human Review": "MATCH_NOT_LISTED", "Human Reviewed Match": E2}
    assert V.resolve_row(row, 4).resolved_id == E2
    row["Human Reviewed Match"] = E1  # contradiction guard: mechanism (item 2)
    assert V.resolve_row(row, 4).status == "UNRESOLVED"


@pytest.mark.parametrize("assessment,clears", [
    ("Agree", True), ("Agree: no match", True), ("Disagree: all candidates rejected", True),
    ("Accept: sole match", True), ("Accept: anything new", True), ("Skip: out of scope", True),
    ("Review", False), ("Disagree: tamr picked another", False), ("", False)])
def test_the_no_review_test_is_a_rule_not_a_list(assessment, clears):
    assert V.clears_without_a_human(assessment) is clears


def test_no_human_and_a_clearing_verdict_uses_the_proposal_unless_a_human_is_required():
    row = {"EIDR Assessment": "Accept: sole match", "EIDR Proposed Match": E1}
    assert V.resolve_row(row, 4).resolved_id == E1
    assert V.resolve_row(row, 4, require_human=True).status == "NOT_CLEARED"


def test_member_role_never_overwrites_an_assigned_id_and_proposal_role_answers_it():
    row = {"EIDR Assessment": "Review", "EIDR Proposed Match": E1, "Assigned EIDR ID": E1,
           "Human Review": "CORRECT_PICK", "Human Reviewed Match": E2}
    held = V.resolve_row(row, 4)
    assert held.status == "UNRESOLVED" and "Not overwriting" in held.detail
    answered = V.resolve_row(row, 4, assigned_id_role="proposal")
    assert (answered.status, answered.resolved_id) == ("CONFIRMED", E2)
    with pytest.raises(ValueError):
        V.resolve_row(row, 4, assigned_id_role="claimant")


def test_sentinels_mean_no_id_and_can_be_widened():
    row = {"EIDR Assessment": "Review", "Human Review": "CORRECT_PICK",
           "Human Reviewed Match": E2, "Assigned EIDR ID": "pending"}
    # "pending" is neither a sentinel nor an ID: the member check ignores an
    # unreadable assertion, so the reviewer's answer stands either way...
    assert V.resolve_row(row, 4).resolved_id == E2
    # ...and a widened set reads it as "no ID" explicitly.
    assert V.read_asserted_id("pending", V.NO_ID_SENTINELS | {"pending"}).absent
    assert V.read_asserted_id("Candidates Found").absent
    assert V.read_asserted_id("10.5240/7791-8534-2C23-9030-8610-X").invalid


def test_the_reviewers_relation_line_travels_and_a_contradicting_one_is_held():
    row = {"EIDR Assessment": "Review", "Human Review": "CORRECT_PICK",
           "Human Reviewed Match": E2, "Human Review Notes": f"RELATION: {E2} IsPackagingOf\nok"}
    assert V.resolve_row(row, 4).relation == "IsPackagingOf"
    row["Human Review Notes"] = f"RELATION: {E1} IsPackagingOf"
    assert V.resolve_row(row, 4).status == "UNRESOLVED"
    assert V.reviewer_relation("see RELATION: x y on line 1") is None


def test_an_unknown_review_code_is_reported_not_interpreted():
    got = V.resolve_row({"EIDR Assessment": "Review", "Human Review": "ACCEPT_SOMETHING",
                         "Human Reviewed Match": E1}, 4)
    assert got.status == "UNRESOLVED" and "not one of" in got.detail
