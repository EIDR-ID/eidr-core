"""EIDR Content ID syntax + ISO 7064 Mod 37,36 check character.

Accepted 2026-08-26 from the BMR-Review session's proposal
(`HANDOFF-EIDR-CORE-2026-08-26.md` §1), seeded from its
``validate_returned_ids.py``.

WHY THIS OVERRIDES R13's "WAIT FOR A SECOND CONSUMER"
-----------------------------------------------------
R13's rule exists to stop premature abstraction while the right SHAPE of
a thing is still uncertain — it protects against guessing an interface.
Neither risk is present here: the ID shape is fixed by the EIDR
specification and the checksum by ISO 7064, so a second local copy is not
a divergence of opinion, it is a second chance to implement a published
standard incorrectly.

And getting it wrong is silent and expensive. BMR-Review's first
implementation initialised the register to 1 instead of 36 and reported
**100% of 2,996 valid production IDs as broken** — which, had it reached
a defect report to the API Shim team, would have been a serious false
alarm against real data. That is the same class as R5's SDK defect (a
wrong answer that looks like a confident answer), and the portfolio's
answer to that class is: one implementation, centrally tested.

WHAT IS DELIBERATELY NOT HERE
-----------------------------
**Party IDs (``10.5237/``) are NOT validated. DEFERRED by the operator
(2026-08-26) to the command-line tools work — do not re-litigate it here
in the meantime.** The original proposal suggested covering them "same
checksum over a different shape". That was tested against the only two
samples in the portfolio (``10.5237/9DD9-E249``, ``10.5237/2FE2-24F2``,
both in BulkMatchRegister's test fixtures) on the obvious reading — last
character is the check — and BOTH failed. Either the shape differs, the
checksum is applied over different input, or those fixtures are
synthetic. Shipping a guess here would recreate precisely the failure
this module exists to prevent. What it needs is confirmed real party-ID
vectors, which the CLI work is expected to supply. Until then a party ID
fails ``fault()`` as a *malformed content ID* — callers must not read
that as a verdict about the party ID itself.

TEST VECTORS
------------
Validated against 7 real production Content IDs drawn from three
independent places (register R8's remediation record, eidr-wikidata test
fixtures, and eidr-wikidata's ``data/missing_uri_template_counts.json``):
4 with digit check characters, 3 with letters. See
``tests/test_ids.py`` — the vectors are pinned there, not here.
"""
from __future__ import annotations

import re

__all__ = ["ALPHABET", "EIDR_CONTENT_ID_RE", "check_character",
           "is_valid_eidr_id", "fault"]

# ISO 7064 Mod 37,36 works over base-36: digits then letters, in order.
ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

# 10.5240/ + five 4-hex groups + a single base-36 check character.
# The check character is NOT hex — it ranges over 0-9A-Z — so it gets its
# own class; writing [0-9A-F] there would reject roughly half of all valid
# IDs while looking symmetric and correct.
EIDR_CONTENT_ID_RE = re.compile(
    r"^10\.5240/[0-9A-F]{4}(?:-[0-9A-F]{4}){4}-[0-9A-Z]$", re.I
)


def check_character(payload: str) -> str:
    """ISO 7064 Mod 37,36 check character for an EIDR suffix.

    ``payload`` is the suffix WITHOUT hyphens and WITHOUT the existing
    check character (20 hex characters for a Content ID).

    The register starts at 36, not at 1. That single line is what
    BMR-Review's first implementation got wrong, and the failure mode is
    not a few edge cases — it rejects essentially every valid ID, which
    reads like a data disaster rather than like a bug in the checker.
    """
    m = 36
    p = m
    for ch in payload.upper():
        try:
            a = ALPHABET.index(ch)
        except ValueError:
            raise ValueError(
                f"character {ch!r} is not valid in an EIDR suffix"
            ) from None
        # S == 0 folds to M (the "hybrid" step that makes Mod 37,36 catch
        # transpositions a plain modulus misses).
        s = (p + a) % m or m
        p = (2 * s) % (m + 1)
    return ALPHABET[(m + 1 - p) % m]


def fault(eidr_id: str | None) -> str | None:
    """``None`` when the ID is sound, else a human-readable reason.

    Returns a REASON rather than a bool because the two failure modes want
    different responses: a malformed ID is usually a parsing or
    transcription problem upstream, while a good-looking ID whose check
    character does not validate is usually a corrupted or fabricated
    value. Collapsing them into False loses the distinction exactly when
    someone is trying to explain a rejection.
    """
    if eidr_id is None:
        return "malformed ID: missing"
    text = str(eidr_id).strip()
    if not text:
        return "malformed ID: empty"
    if not EIDR_CONTENT_ID_RE.match(text):
        return f"malformed ID {text!r}: not 10.5240/XXXX-XXXX-XXXX-XXXX-XXXX-C"
    suffix = text.split("/", 1)[1]
    body, _, given = suffix.rpartition("-")
    expected = check_character(body.replace("-", ""))
    if expected.upper() != given.upper():
        return (f"check character does not validate for {text!r}: "
                f"expected {expected}, found {given.upper()}")
    return None


def is_valid_eidr_id(eidr_id: str | None) -> bool:
    """True when ``eidr_id`` is a syntactically sound, checksum-valid
    EIDR Content ID. Use ``fault()`` when you need to say WHY not."""
    return fault(eidr_id) is None
