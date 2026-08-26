"""EIDR Content ID validation — pinned against REAL production IDs.

These vectors matter more than usual. BMR-Review's first implementation of
this checksum rejected 100% of 2,996 valid production IDs because the
register was initialised to 1 instead of 36 — a wrong answer that looks
like a confident answer, and one that would have gone out as a defect
report against real registry data. A synthetic fixture cannot catch that
class of error, because a self-consistent wrong implementation agrees with
its own synthetic expectations. So every positive vector below is an ID
observed in the portfolio, not one this module generated.
"""
from __future__ import annotations

import pytest

from eidr_core.ids import check_character, fault, is_valid_eidr_id

# Real Content IDs, from three independent sources:
#   * register R8's remediation record (the comcast/xfinity Alt-ID case);
#   * eidr-wikidata test fixtures (test_episodic_tree, ledger seed);
#   * eidr-wikidata data/missing_uri_template_counts.json (production scan).
# Deliberately mixed: 4 digit check characters, 3 letters. An
# implementation can be wrong in a way that only shows on one or the other
# (the final modulus maps 0-35 onto '0'-'9' then 'A'-'Z', so an off-by-one
# there breaks the letter half while the digit half still passes).
REAL_IDS = [
    "10.5240/07A9-90F4-F212-704C-0523-9",
    "10.5240/0430-3D62-36AF-39A0-CB23-8",
    "10.5240/43A3-BBBA-125C-CD42-C155-7",
    "10.5240/D5AC-D4EB-F207-19AE-08C2-9",
    "10.5240/485E-0E15-5AF1-A4C1-2DA6-G",
    "10.5240/E925-8313-CDAD-3F68-6EF1-H",
    "10.5240/0000-40B8-6A21-DB8F-14F7-A",
]


@pytest.mark.parametrize("eidr_id", REAL_IDS)
def test_real_production_ids_validate(eidr_id):
    assert fault(eidr_id) is None, fault(eidr_id)
    assert is_valid_eidr_id(eidr_id)


def test_vector_set_covers_both_check_character_kinds():
    # Guards the SUITE, not the code: if someone prunes these vectors down
    # to one kind, the letter/digit asymmetry above stops being covered.
    last = [i[-1] for i in REAL_IDS]
    assert any(c.isdigit() for c in last)
    assert any(c.isalpha() for c in last)


def test_check_character_is_computed_not_echoed():
    # The load-bearing assertion: a hand-computed vector, so the test
    # cannot pass by reading the check character back off the input.
    assert check_character("485E0E155AF1A4C12DA6") == "G"


def test_the_p_equals_one_bug_is_caught():
    """The specific historical defect, reproduced and refuted.

    Initialising the register to 1 instead of 36 is the mistake that
    rejected every valid ID. Recomputing that way here proves these
    vectors actually discriminate against it rather than merely agreeing
    with the current implementation.
    """
    alpha = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

    def wrong(payload: str) -> str:
        m, p = 36, 1                      # the bug
        for ch in payload.upper():
            s = (p + alpha.index(ch)) % m or m
            p = (2 * s) % (m + 1)
        return alpha[(m + 1 - p) % m]

    disagreements = sum(
        1 for i in REAL_IDS
        if wrong(i.split("/", 1)[1].rpartition("-")[0].replace("-", "")) != i[-1]
    )
    assert disagreements == len(REAL_IDS), (
        "these vectors no longer discriminate against the p=1 defect"
    )


# --- rejections -------------------------------------------------------------

def test_corrupted_check_character_is_rejected_with_a_reason():
    bad = "10.5240/485E-0E15-5AF1-A4C1-2DA6-X"     # G -> X
    msg = fault(bad)
    assert msg is not None
    assert "check character" in msg
    # The reason names both what was expected and what was found, so a
    # rejection can be explained without re-running the checker by hand.
    assert "expected G" in msg and "found X" in msg


def test_transposition_is_caught():
    # Mod 37,36's whole reason for existing over a plain modulus.
    assert fault("10.5240/485E-0E15-5AF1-A4C1-2AD6-G") is not None


@pytest.mark.parametrize("value,fragment", [
    (None, "missing"),
    ("", "empty"),
    ("   ", "empty"),
    ("10.5240/485E-0E15-5AF1-A4C1-2DA6", "malformed"),      # no check char
    ("10.5240/485E0E155AF1A4C12DA6G", "malformed"),          # no hyphens
    ("10.5237/9DD9-E249", "malformed"),                      # party ID, not content
    ("tt0133093", "malformed"),
])
def test_malformed_inputs_named_not_crashed(value, fragment):
    msg = fault(value)
    assert msg is not None and fragment in msg
    assert is_valid_eidr_id(value) is False


def test_lowercase_and_surrounding_space_accepted():
    # Real IDs arrive from spreadsheets and shim exports; rejecting an ID
    # for its case or a stray space would be a false alarm of exactly the
    # kind this module exists to avoid.
    assert is_valid_eidr_id("  10.5240/485e-0e15-5af1-a4c1-2da6-g  ")


def test_check_character_rejects_non_base36_input():
    with pytest.raises(ValueError, match="not valid in an EIDR suffix"):
        check_character("485E-0E15")     # hyphen must be stripped by caller
