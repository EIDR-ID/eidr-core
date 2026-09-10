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

PARTY, SERVICE AND USER IDS (deferral of 2026-08-26 CLOSED 2026-09-10)
----------------------------------------------------------------------
The deferral asked the CLI work for "confirmed real party-ID vectors".
python-tools supplied them, and they settle the question the original
proposal got wrong: **these IDs carry NO check character.** Both fixture
samples "failed" the Mod 37,36 test not because the checksum is applied
differently but because there is nothing to check. The suffix is eight
hex digits and nothing more.

Evidence (schema 2.7.0, ``common.xsd`` / ``service.xsd``, and live IDs):

* party    ``10.5237/XXXX-XXXX`` hex, case-insensitive, OR the literal
           ``10.5237/superparty`` (the one non-hex party). Real:
           ``10.5237/9DD9-E249``, ``10.5237/F625-DC51``, the tombstone
           ``10.5237/0000-0000``.
* service  ``10.5239/XXXX-XXXX`` -- the schema pattern is upper-case only,
           but the party pattern is explicitly case-insensitive and the
           registry treats hex as hex, so both are accepted here
           case-insensitively. Real: ``10.5239/1575-4C9C``.
* user     ``10.5238/<username>`` where the username is 3-32 characters
           from ``0-9 a-z A-Z _ # . - ( )`` -- free-form, so validation is the
           pattern and nothing else.

So ``is_valid_party_id`` / ``is_valid_service_id`` / ``is_valid_user_id``
are PATTERN checks, and ``category()`` classifies a DOI by prefix.
``fault()`` on a party ID now says so instead of "malformed content ID",
which was the misleading verdict the deferral warned callers about.

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
           "is_valid_eidr_id", "fault",
           "PARTY_ID_RE", "SERVICE_ID_RE", "USER_ID_RE",
           "is_valid_party_id", "is_valid_service_id", "is_valid_user_id",
           "category"]

# ISO 7064 Mod 37,36 works over base-36: digits then letters, in order.
ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

# 10.5240/ + five 4-hex groups + a single base-36 check character.
# The check character is NOT hex — it ranges over 0-9A-Z — so it gets its
# own class; writing [0-9A-F] there would reject roughly half of all valid
# IDs while looking symmetric and correct.
EIDR_CONTENT_ID_RE = re.compile(
    r"^10\.5240/[0-9A-F]{4}(?:-[0-9A-F]{4}){4}-[0-9A-Z]$", re.I
)


# Party / service / user DOIs. NO check character on any of these -- see the
# module docstring for the evidence. Patterns transcribed from schema 2.7.0
# (common.xsd partyDOIType / userDOIType, service.xsd serviceDOIType).
PARTY_ID_RE = re.compile(r"^10\.5237/(?:[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}|superparty)$")
SERVICE_ID_RE = re.compile(r"^10\.5239/[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}$")
USER_ID_RE = re.compile(r"^10\.5238/[0-9a-zA-Z_#.\-()]{3,32}$")

_PREFIX_CATEGORY = {
    "10.5240/": "content",
    "10.5237/": "party",
    "10.5238/": "user",
    "10.5239/": "service",
}


def category(doi: str | None) -> str | None:
    """Which EIDR ID family a DOI belongs to, by prefix: ``'content'``,
    ``'party'``, ``'user'``, ``'service'`` -- or ``None`` when it is not an
    EIDR DOI at all. Mirrors the SDK's ``IDCategory``. Prefix only: a
    party-prefixed string with a bad suffix is still ``'party'``, and it is
    ``is_valid_party_id`` that says whether it is well-formed."""
    if doi is None:
        return None
    text = str(doi).strip()
    for prefix, cat in _PREFIX_CATEGORY.items():
        if text.startswith(prefix):
            return cat
    return None


def is_valid_party_id(party_id: str | None) -> bool:
    """``10.5237/XXXX-XXXX`` (hex, either case) or ``10.5237/superparty``."""
    return bool(party_id) and PARTY_ID_RE.match(str(party_id).strip()) is not None


def is_valid_service_id(service_id: str | None) -> bool:
    """``10.5239/XXXX-XXXX`` (hex, either case)."""
    return bool(service_id) and SERVICE_ID_RE.match(str(service_id).strip()) is not None


def is_valid_user_id(user_id: str | None) -> bool:
    """``10.5238/<username>``, 3-32 characters of ``[0-9a-zA-Z_#.-()]``."""
    return bool(user_id) and USER_ID_RE.match(str(user_id).strip()) is not None


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
        # Say what kind of ID it IS before saying it is not a content ID.
        # Until 2026-09-10 a well-formed party ID came back "malformed
        # content ID", and the deferral note had to warn callers not to
        # read that as a verdict about the party ID. Now it is the verdict.
        cat = category(text)
        if cat == "party":
            ok = is_valid_party_id(text)
            return (f"{text!r} is a party ID, not a content ID"
                    + ("" if ok else " (and malformed: expected 10.5237/XXXX-XXXX or superparty)"))
        if cat == "service":
            ok = is_valid_service_id(text)
            return (f"{text!r} is a service ID, not a content ID"
                    + ("" if ok else " (and malformed: expected 10.5239/XXXX-XXXX)"))
        if cat == "user":
            ok = is_valid_user_id(text)
            return (f"{text!r} is a user ID, not a content ID"
                    + ("" if ok else " (and malformed: expected 10.5238/<3-32 char username>)"))
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
