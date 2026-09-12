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
    ("10.5237/9DD9-E249", "party ID"),                       # named as what it IS, since 0.28.0
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


# --- party / service / user IDs: the 2026-08-26 deferral, closed ------------
#
# The deferral asked for "confirmed real party-ID vectors" before validating
# party IDs at all, because the obvious reading (last character is a Mod 37,36
# check) failed on both samples in the portfolio. python-tools supplied the
# vectors on 2026-09-08 and they settle it: there is NO check character. Both
# samples "failed" because there was nothing to check. Every ID below is real
# (created on sandbox2, or live), or is the schema-defined literal.

from eidr_core.ids import (  # noqa: E402
    category,
    is_valid_party_id,
    is_valid_service_id,
    is_valid_user_id,
)

REAL_PARTY_IDS = [
    "10.5237/9DD9-E249",    # the BulkMatchRegister fixture that "failed" the checksum
    "10.5237/F625-DC51",
    "10.5237/805A-BE88",
    "10.5237/8340-5F9F",
    "10.5237/0000-0000",    # the tombstone
    "10.5237/superparty",   # the one non-hex party, a schema literal
]
REAL_SERVICE_IDS = ["10.5239/1575-4C9C", "10.5239/CB5F-4F4E", "10.5239/B375-AF2D"]


@pytest.mark.parametrize("pid", REAL_PARTY_IDS)
def test_real_party_ids_validate(pid):
    assert is_valid_party_id(pid)
    assert category(pid) == "party"


@pytest.mark.parametrize("sid", REAL_SERVICE_IDS)
def test_real_service_ids_validate(sid):
    assert is_valid_service_id(sid)
    assert category(sid) == "service"


def test_party_and_service_hex_is_case_insensitive():
    """The party pattern says so explicitly; the service pattern is written
    upper-case only, but the registry treats hex as hex. Rejecting a
    lower-case service ID would be a false alarm of exactly the kind this
    module exists to prevent."""
    assert is_valid_party_id("10.5237/9dd9-e249")
    assert is_valid_service_id("10.5239/1575-4c9c")


@pytest.mark.parametrize("bad", [
    "10.5237/ZZZZ-0000",     # not hex
    "10.5237/9DD9E249",      # no hyphen
    "10.5237/9DD9-E249-1",   # content-ID-shaped suffix on a party prefix
    "10.5237/SUPERPARTY",    # the literal is lower-case in the schema
    "10.5239/superparty",    # no such service literal
    "",
    None,
])
def test_malformed_party_and_service_ids_are_rejected(bad):
    assert not is_valid_party_id(bad)
    assert not is_valid_service_id(bad)


def test_user_ids_are_a_username_pattern_and_nothing_more():
    assert is_valid_user_id("10.5238/rkroon")
    assert is_valid_user_id("10.5238/a.b-c_(d)#1")
    assert not is_valid_user_id("10.5238/ab")          # under 3
    assert not is_valid_user_id("10.5238/" + "x" * 33)  # over 32
    assert not is_valid_user_id("10.5238/has space")
    assert category("10.5238/rkroon") == "user"


def test_category_is_by_prefix_only():
    """A party-prefixed string with a bad suffix is still a party ID that
    happens to be malformed. Category and validity are separate questions."""
    assert category("10.5237/ZZZZ-0000") == "party"
    assert category("10.5240/1FB4-801D-C016-5F48-86E6-9") == "content"
    assert category("10.9999/anything") is None
    assert category(None) is None


def test_fault_names_the_family_instead_of_calling_a_party_id_malformed():
    """Until 2026-09-10 a well-formed party ID came back 'malformed content
    ID', and the module docstring had to warn callers not to read that as a
    verdict on the party ID. Now the reason IS the verdict."""
    assert fault("10.5237/9DD9-E249") == "'10.5237/9DD9-E249' is a party ID, not a content ID"
    assert "malformed" in fault("10.5237/ZZZZ-0000")
    assert "service ID" in fault("10.5239/1575-4C9C")
    assert "user ID" in fault("10.5238/rkroon")
    assert fault("10.9999/nope").startswith("malformed ID")


# ── free-text extraction (2026-09-11) ─────────────────────────────────────

VALID = "10.5240/7791-8534-2C23-9030-8610-5"
BAD_CHECK = "10.5240/7791-8534-2C23-9030-8610-6"


def test_find_content_ids_pulls_ids_out_of_a_notes_column_in_order():
    from eidr_core.ids import find_content_ids
    text = f"candidates: {VALID.lower()}; also {VALID} (dup) then 10.5237/9DD9-E249 (a party)"
    assert find_content_ids(text) == [VALID]          # de-duplicated, upper-cased, party ignored


def test_find_content_ids_drops_a_bad_check_character_unless_asked_not_to():
    from eidr_core.ids import find_content_ids
    text = f"{BAD_CHECK} and {VALID}"
    assert find_content_ids(text) == [VALID]
    assert find_content_ids(text, valid_only=False) == [BAD_CHECK, VALID]


def test_find_content_ids_respects_boundaries_and_empty_input():
    from eidr_core.ids import find_content_ids
    # An extra trailing character makes it not an ID, not a longer one.
    assert find_content_ids(f"x{VALID}Q y") == []
    assert find_content_ids(f"({VALID})") == [VALID]
    assert find_content_ids(None) == [] and find_content_ids("") == []



# ── 0.33.0: the suffix rules are exported on their own ─────────────────────

def test_the_anchored_patterns_are_composed_from_the_exported_suffixes():
    """python-sdk validates the part after the prefix and used to derive it
    by string surgery on USER_ID_RE.pattern; a named group or a flag added
    here would have produced a wrong suffix pattern with no test noticing.
    Composing the anchored regexes from the exported suffixes makes the two
    one fact. The literal spellings are pinned so a refactor cannot move
    them silently."""
    import re

    from eidr_core import ids
    assert ids.PARTY_ID_RE.pattern == r"^10\.5237/" + ids.PARTY_ID_SUFFIX + "$"
    assert ids.SERVICE_ID_RE.pattern == r"^10\.5239/" + ids.SERVICE_ID_SUFFIX + "$"
    assert ids.USER_ID_RE.pattern == r"^10\.5238/" + ids.USER_ID_SUFFIX + "$"
    # schema 2.7.0 transcriptions, verbatim
    assert ids.USER_ID_SUFFIX == r"[0-9a-zA-Z_#.\-()]{3,32}"
    assert ids.SERVICE_ID_SUFFIX == r"[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}"
    assert ids.PARTY_ID_SUFFIX == r"(?:[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}|superparty)"
    # a suffix anchored on its own agrees with the full-ID validator
    user = re.compile("^" + ids.USER_ID_SUFFIX + "$")
    for suffix, ok in (("ab", False), ("abc", True), ("a" * 32, True), ("a" * 33, False),
                       ("x#(y).z", True), ("no space", False)):
        assert bool(user.match(suffix)) is ok, suffix
        assert ids.is_valid_user_id("10.5238/" + suffix) is ok, suffix
