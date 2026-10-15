"""Read BMR-Review's verdicts back off an assessed-and-reviewed BMR sheet.

THE shared verdict resolver (reconciliation plan component C4), extracted
2026-10-15 from BMRtoAltID ``bmr_altid/verdicts.py`` (content-sha1
``be06328b6431``, its T5a) with the helpers it reaches in ``extract.py`` and
``ids.py``; interface ruled in eidr-core-ops ``PHASE2-3-INTERFACES-2026-10-15.md``.
Interface authority for the sheet: BMR-Review's ``CONTRACT.md``. Two
parameters were added on extraction, each defaulting to BMRtoAltID's
behaviour: ``assigned_id_role`` and ``no_id_sentinels``. This module decides, per
row, whether BMR-Review and its reviewer resolved the row to an EIDR ID —
and to which. It writes nothing: :func:`resolve_sheet` returns
:class:`Resolution` objects and :func:`fill_map` turns the confirmed ones
into the ``{sheet_row: eidr_id}`` dict the sheet-fill step takes.

WHY THE DECISION ORDER IS WHAT IT IS
------------------------------------
Two rules from the contract drive the whole design, and both are easy to
get wrong in a way that fails SILENTLY and in the direction of preferring a
machine answer over a human one.

**1. Branch on ``Human Review`` FIRST.** ``Human Reviewed Match`` supersedes
``EIDR Proposed Match`` — except on ``MATCH_NOT_LISTED``, where it is
BLANK unless the reviewer named the record, because the reviewer is saying
*the right record exists and you did not show it to me* (a named ID is
used; BMR-Review CONTRACT section 3). The obvious implementation ::

    resolved = row["Human Reviewed Match"] or row["EIDR Proposed Match"]

is correct for every other code and catastrophic for that one: the blank
falls through to the proposal the human just rejected. A truthiness check
cannot see the difference. So this module never reads the machine's column
until it knows the human did not decide.

**2. The no-review test is a RULE, not a list.** BMR-Review clears a row
without a human when the assessment is one of ``TERMINAL_ASSESSMENTS``, OR
starts with ``Skip``, OR starts with ``Accept:``. Clauses 2 and 3 are prefix
tests precisely so a new verdict in those families needs no consumer change.
Enumerating the verdicts misses them — which is exactly the defect that
produced this contract: an earlier three-item list omitted
``Accept: sole match``, 55% of a real sheet.

WHAT THIS MODULE DOES NOT DO
----------------------------
It does not write AltIDTool lines (that stays with the audit, run against
the filled sheet), does not consult the mirror, and does not modify its
input.
"""
from __future__ import annotations

import re
from collections.abc import Collection
from typing import NamedTuple

from eidr_core.bmr_io import ASSIGNED_ID_COLUMN, ROW_ID_COLUMN, open_sheet
from eidr_core.ids import fault as _eidr_fault

__all__ = [
    "ASSESSMENT_COLUMN",
    "AssertedId",
    "NOTES_COLUMN",
    "NO_ID_SENTINELS",
    "read_asserted_id",
    "trim",
    "HUMAN_REVIEW_COLUMN",
    "NO_MATCH",
    "STATUSES",
    "TERMINAL_ASSESSMENTS",
    "Resolution",
    "ResolveStats",
    "clears_without_a_human",
    "fill_map",
    "resolve_row",
    "resolve_sheet",
    "reviewer_relation",
    "summarize",
]

# --- cell helpers (from BMRtoAltID ids.py and extract.py) ------------------

# Values the BMR sheet uses to mean "no EIDR ID was assigned to this row"
# (operator ruling 2026-08-26). Compared case-insensitively after trimming.
# Anything NOT in this set and not empty must parse as a valid EIDR ID or it
# is an error: a typo must never silently degrade to "unassigned", which is
# how a wrong ID survives review. They are the BMR tool's own cell values,
# so a caller may widen the set (``no_id_sentinels=``), never narrow it by
# accident.
NO_ID_SENTINELS = frozenset({"candidates found", "no match"})

# BMR-Review's reviewer free-text column (their report.NEW_COLS). Read for
# ONE thing: its FIRST line, when BMR-Review's Relation control wrote it
# (their CONTRACT section 4, 2026-09-21): `RELATION: <EIDR ID> <Relation>`.
NOTES_COLUMN = "Human Review Notes"
_RELATION_LINE = re.compile(r"^RELATION:\s+(\S+)\s+(\S+)\s*$", re.IGNORECASE)


def trim(v: object) -> str:
    """Trim any cell value to a string. ``None`` becomes ``""``."""
    if v is None:
        return ""
    return str(v).strip()


class AssertedId:
    """The result of reading an "Assigned EIDR ID" (or decided-ID) cell.

    Three outcomes, kept distinct because they lead to different places:
    ``absent`` (nothing to check), ``valid`` (usable), and ``invalid`` (an
    error in its own right, with ``reason`` from ``ids.fault``:
    malformed and failed check character need different responses).
    """

    __slots__ = ("raw", "value", "invalid", "reason")

    def __init__(self, raw: str, value: str = "", invalid: bool = False,
                 reason: str = ""):
        self.raw = raw
        self.value = value
        self.invalid = invalid
        self.reason = reason

    @property
    def absent(self) -> bool:
        return not self.value and not self.invalid

    def __repr__(self) -> str:      # pragma: no cover - debugging aid
        return (f"AssertedId(raw={self.raw!r}, value={self.value!r}, "
                f"invalid={self.invalid}, reason={self.reason!r})")


def read_asserted_id(cell: object, sentinels: Collection[str] = NO_ID_SENTINELS
                     ) -> AssertedId:
    """Interpret an ID cell: empty or a sentinel means "no EIDR ID"; anything
    else must be a valid EIDR Content ID (upper-cased), or it is invalid."""
    raw = trim(cell)
    if not raw or raw.lower() in sentinels:
        return AssertedId(raw)
    reason = _eidr_fault(raw)
    if reason is None:
        return AssertedId(raw, raw.upper())
    return AssertedId(raw, invalid=True, reason=reason)


def reviewer_relation(notes: object) -> tuple[str, str] | None:
    """``(eidr_id, relation)`` from a `RELATION:` FIRST line, else None.

    BMR-Review's UI writes exactly one such line, first, only when the
    reviewer chose a relation other than IsSameAs; absence means "this row
    is the claimant". Only the first line is examined, as their contract
    says, so free text mentioning the word never fires this.
    """
    first = str(notes or "").strip().splitlines()[:1]
    m = _RELATION_LINE.match(first[0]) if first else None
    return (m.group(1), m.group(2)) if m else None


# --- BMR-Review's seven appended columns (BMR-REVIEW-CONTRACT.md) ---------
# `report.NEW_COLS` on their side. Five are read for the verdict; `EIDR
# Confidence` informs a human, not us; and `Human Review Notes` is read for
# ONE thing -- its first line, when BMR-Review's Relation control wrote it
# (their CONTRACT section 4, 2026-09-21): `RELATION: <EIDR ID> <Relation>`.
# The parser is ``reviewer_relation`` above; applying the relation to every
# Alt ID on the row (T8, 2026-09-23) is the caller's step before
# ``altid_audit`` (C5 item 10).
ASSESSMENT_COLUMN = "EIDR Assessment"
PROPOSED_MATCH_COLUMN = "EIDR Proposed Match"
HUMAN_REVIEW_COLUMN = "Human Review"
HUMAN_MATCH_COLUMN = "Human Reviewed Match"
DUPLICATE_IDS_COLUMN = "Duplicate EIDR IDs"

# The value BMR-Review writes for "no registry record is right".
NO_MATCH = "NO MATCH"

# CLAUSE ONE of three. Named for what it is, not for "the verdicts that
# clear" -- it is not that, and treating it as that is the documented bug.
# See clears_without_a_human() for the other two clauses.
TERMINAL_ASSESSMENTS = frozenset({
    "Agree",
    "Agree: no match",
    "Disagree: all candidates rejected",
})

# --- the reviewer's vocabulary (bmrCode() in dedup_review_ui.html) --------
# Grouped by what they mean for US, which is not how they are grouped for a
# reviewer. A code absent from all three sets is a contract change: it
# resolves UNRESOLVED and is named in the detail, never guessed at.
_HUMAN_CODES_USE_MATCH = frozenset({
    "ACCEPT_TAMR",       # Tamr's id
    "CORRECT_OURS",      # BMR-Review's proposed id
    "CORRECT_PICK",      # the id the reviewer picked
    "DUPLICATES_MERGE",  # the survivor; Duplicate EIDR IDs holds the rest
})
_HUMAN_CODES_NO_MATCH = frozenset({
    "ACCEPT_NOMATCH",
    "CORRECT_NOMATCH",
    "SET_NOMATCH",
})
# Deliberately alone: its Human Reviewed Match is blank unless the reviewer
# NAMED the record, and that blank means "not among these", never "fall back
# to the machine". A named ID is the reviewer's answer and is used.
_HUMAN_CODE_NOT_LISTED = "MATCH_NOT_LISTED"

STATUSES = (
    "CONFIRMED",      # a resolved EIDR ID exists and validates -> fill it
    "NO_MATCH",       # resolved to NO MATCH -> register a new record
    "UNRESOLVED",     # a human looked and the answer is not an ID we can use
    "NEEDS_REVIEW",   # no human, and the machine verdict does not clear
    "NOT_CLEARED",    # no human, machine clears, but --require-human-review
    "INVALID",        # a resolved value that is neither an ID nor NO MATCH
)


class Resolution(NamedTuple):
    """What one sheet row resolved to, and on whose authority."""

    sheet_row: int
    row_id: str
    status: str
    resolved_id: str        # "" unless status == "CONFIRMED"
    source: str             # the column or code that decided it
    assessment: str         # EIDR Assessment, verbatim
    human_review: str       # Human Review, verbatim ("" when none)
    merged_ids: tuple[str, ...]   # DUPLICATES_MERGE only
    detail: str
    # The reviewer's clarifying relation (BMR-Review CONTRACT section 4),
    # "" when the row is the IsSameAs claimant. Carried for the report;
    # the audit re-reads it from the sheet, so the fill need not write it.
    relation: str = ""


class ResolveStats(NamedTuple):
    rows_read: int
    by_status: dict[str, int]

    @property
    def confirmed(self) -> int:
        return self.by_status.get("CONFIRMED", 0)

    @property
    def findings(self) -> int:
        """Statuses that mean a human has to look at the report."""
        return (self.by_status.get("UNRESOLVED", 0)
                + self.by_status.get("INVALID", 0))


def clears_without_a_human(assessment: str) -> bool:
    """BMR-Review's own no-review test, as a RULE (three clauses).

    ``dedup_review_ui.html::needsReview`` is the authority; this is its
    negation. Do NOT rewrite this as ``assessment in {...}`` -- clauses two
    and three are prefix tests so that a new verdict in the ``Skip`` or
    ``Accept:`` families needs no change here.
    """
    a = trim(assessment)
    return (a in TERMINAL_ASSESSMENTS
            or a.startswith("Skip")
            or a.startswith("Accept:"))


def _split_ids(cell: object) -> tuple[str, ...]:
    """`Duplicate EIDR IDs` is a delimited list; the delimiter is not fixed."""
    raw = trim(cell)
    if not raw:
        return ()
    for sep in (",", ";", "|"):
        if sep in raw:
            return tuple(p for p in (x.strip() for x in raw.split(sep)) if p)
    return (raw,)


def _classify_value(value: str, *, source: str, sheet_row: int, row_id: str,
                    assessment: str, human_review: str,
                    merged_ids: tuple[str, ...] = (),
                    sentinels: Collection[str] = NO_ID_SENTINELS) -> Resolution:
    """Turn a resolved cell value into CONFIRMED / NO_MATCH / INVALID."""
    def _make(status: str, resolved_id: str, detail: str) -> Resolution:
        return Resolution(sheet_row=sheet_row, row_id=row_id, status=status,
                          resolved_id=resolved_id, source=source,
                          assessment=assessment, human_review=human_review,
                          merged_ids=merged_ids, detail=detail)

    if value.strip().upper() == NO_MATCH:
        return _make("NO_MATCH", "",
                     f"{source}: no registry record is right; a new record is "
                     f"to be registered. Nothing to fill.")

    asserted = read_asserted_id(value, sentinels)
    if asserted.invalid:
        return _make("INVALID", "",
                     f"{source}: {value!r} is not a usable EIDR ID "
                     f"({asserted.reason}).")
    if asserted.absent:
        # Blank, or a BMR sentinel like "Candidates Found", where a decided
        # value was expected. Not an ID and not NO MATCH, so not usable.
        return _make("UNRESOLVED", "",
                     f"{source}: expected a resolved EIDR ID but found "
                     f"{value!r}.")
    return _make("CONFIRMED", asserted.value, f"{source}: {asserted.value}.")


_ROLES = ("member", "proposal")


def resolve_row(row: dict, sheet_row: int, *, require_human: bool = False,
                assigned_id_role: str = "member",
                no_id_sentinels: Collection[str] = NO_ID_SENTINELS,
                ) -> Resolution:
    """Resolve one assessed-and-reviewed row. Pure; reads nothing else.

    ``require_human=False`` (the default) accepts a row that BMR-Review's
    rule set cleared without a reviewer.

    OPERATOR RULING 2026-09-12: *"If BMR-Review determines that human review
    is not necessary, based on its rule set, then we accept that ID
    mapping."* That settles the question this module was first built
    undecided on. The three-clause rule IS BMR-Review's own definition of
    "no human needed", and D1's premise is that this repo consumes their
    process rather than re-implementing its policy from outside; a second
    gate here would be exactly that re-implementation.

    ``require_human=True`` is the opt-OUT, for a batch someone wants held to
    a stricter standard than BMR-Review's own. It is not the normal path.

    ``assigned_id_role`` says what a valid ID already in ``Assigned EIDR ID``
    is (BMRtoAltID's item 1, ruled 2026-10-15). ``"member"`` (default): the
    sheet asks "what is this?" and the column was blanked, so a value there
    is a member's own assertion, and a CONFIRMED record that differs becomes
    UNRESOLVED rather than overwrite it. ``"proposal"``: the sheet asks "is
    this pairing right?" and the column holds the claimant, so a reviewer
    choosing a different record IS the answer and is returned CONFIRMED.

    ``no_id_sentinels``: the cell values that mean "no ID" (the BMR tool's
    ``candidates found`` / ``no match``); a caller may widen them.
    """
    if assigned_id_role not in _ROLES:
        raise ValueError(f"assigned_id_role must be one of {_ROLES}, not {assigned_id_role!r}")
    got = _resolve_without_relation(row, sheet_row, require_human=require_human,
                                    sentinels=no_id_sentinels)
    if assigned_id_role == "member":
        got = _check_against_assertion(got, row, no_id_sentinels)
    return _with_reviewer_relation(got, row)


def _with_reviewer_relation(got: Resolution, row: dict) -> Resolution:
    """Carry a reviewer's `RELATION:` line, and refuse an inconsistent one.

    BMR-Review's Relation control (their CONTRACT section 4) says the
    matched record keeps the identifier under a clarifying relation, not as
    the IsSameAs claimant. The line names the EIDR ID it relates to, which
    must be the one this row resolved to; a different ID is a contradiction
    inside the row and is held, never filled. The relation itself is NOT
    written into the sheet by the fill (the sheet's `Relation N` columns
    are the member's, and a production sheet has 184 Alt ID sets against 3
    such columns): the audit re-reads this line and applies it to every
    Alt ID on the row (`extract.apply_reviewer_relation`).

    Until 2026-09-23 a row with this line was HELD unresolved as a
    fail-safe; T8 made it travel.
    """
    relation = reviewer_relation(row.get(NOTES_COLUMN))
    if relation is None:
        return got
    rel_id, rel = relation
    if got.status == "CONFIRMED" and rel_id.casefold() != got.resolved_id.casefold():
        return got._replace(
            status="UNRESOLVED", resolved_id="", source=NOTES_COLUMN,
            detail=f"the reviewer recorded RELATION: {rel_id} {rel}, but the "
                   f"row resolved to {got.resolved_id}. The relation names a "
                   f"different record from the match; held, not filled.")
    return got._replace(relation=rel)


def _resolve_without_relation(row: dict, sheet_row: int, *,
                              require_human: bool,
                              sentinels: Collection[str] = NO_ID_SENTINELS) -> Resolution:
    row_id = trim(row.get(ROW_ID_COLUMN))
    assessment = trim(row.get(ASSESSMENT_COLUMN))
    human_review = trim(row.get(HUMAN_REVIEW_COLUMN))
    proposed = trim(row.get(PROPOSED_MATCH_COLUMN))
    human_match = trim(row.get(HUMAN_MATCH_COLUMN))

    def _make(status: str, resolved_id: str, source: str, detail: str,
              merged: tuple[str, ...] = ()) -> Resolution:
        return Resolution(sheet_row=sheet_row, row_id=row_id, status=status,
                          resolved_id=resolved_id, source=source,
                          assessment=assessment, human_review=human_review,
                          merged_ids=merged, detail=detail)

    # --- STEP 1: the human, if there was one ----------------------------
    if human_review:
        if human_review == _HUMAN_CODE_NOT_LISTED and human_match:
            # The reviewer NAMED the record that was not offered. BMR-Review
            # CONTRACT section 3 (made precise 2026-09-20): the match column
            # is blank only when the prompt was left empty; a typed ID has
            # always been written, the operator ruled such IDs hand-entered
            # truth (2026-09-14), and the "Swapped original" control records
            # a SWAPPED row's original exactly this way. Treating every
            # MATCH_NOT_LISTED as unresolved silently drops those answers.
            # Still the HUMAN's column only -- the proposal is never USED.
            # It is READ for one purpose: MATCH_NOT_LISTED means "not among
            # those shown", and the proposal was shown, so a typed ID equal
            # to it contradicts the code. That row is a reviewer's error or
            # a UI regression, and confirming it would resolve the row to
            # the rejected candidate through the human's column instead of
            # the fallback -- the same wrong answer by a different door.
            # 0 of 75 on the real sheet (2026-09-20); a test pins that, but
            # only for that sheet. This guard holds for every sheet.
            if proposed and human_match.casefold() == proposed.casefold():
                return _make(
                    "UNRESOLVED", "", HUMAN_MATCH_COLUMN,
                    f"{_HUMAN_CODE_NOT_LISTED}: the reviewer says the correct "
                    f"record was not offered, but named {human_match}, which "
                    f"IS the offered proposal. Contradictory; not filled.")
            got = _classify_value(
                human_match, source=f"{HUMAN_MATCH_COLUMN} ({human_review})",
                sheet_row=sheet_row, row_id=row_id, assessment=assessment,
                human_review=human_review, merged_ids=(), sentinels=sentinels)
            return got

        if human_review == _HUMAN_CODE_NOT_LISTED:
            # THE TRAP. With no record named, Human Reviewed Match is blank
            # BY DESIGN and the blank means "the right record exists and was
            # not offered". Reading EIDR Proposed Match now would resolve
            # the row to the very candidate the reviewer rejected.
            return _make(
                "UNRESOLVED", "", HUMAN_REVIEW_COLUMN,
                f"{_HUMAN_CODE_NOT_LISTED}: the reviewer says the correct "
                f"record exists but was not offered. The machine's proposal "
                f"was rejected by that answer and is NOT used.")

        if human_review in _HUMAN_CODES_NO_MATCH:
            return _make("NO_MATCH", "", HUMAN_REVIEW_COLUMN,
                         f"{human_review}: the reviewer confirmed no registry "
                         f"record is right. Nothing to fill.")

        if human_review in _HUMAN_CODES_USE_MATCH:
            merged = (_split_ids(row.get(DUPLICATE_IDS_COLUMN))
                      if human_review == "DUPLICATES_MERGE" else ())
            if not human_match:
                # Reviewed, but no id recorded. UNRESOLVED, never a fallback:
                # a populated Human Review with a blank match is a decision
                # we cannot read, not an absent decision.
                return _make(
                    "UNRESOLVED", "", HUMAN_REVIEW_COLUMN,
                    f"{human_review}: reviewed, but {HUMAN_MATCH_COLUMN!r} is "
                    f"blank, so no resolved ID was recorded. The machine's "
                    f"proposal is NOT used in its place.",
                    merged)
            got = _classify_value(
                human_match, source=f"{HUMAN_MATCH_COLUMN} ({human_review})",
                sheet_row=sheet_row, row_id=row_id, assessment=assessment,
                human_review=human_review, merged_ids=merged, sentinels=sentinels)
            return got

        # A ninth code. BMR-Review's vocabulary is eight; anything else is a
        # contract change and is reported, not interpreted.
        return _make(
            "UNRESOLVED", "", HUMAN_REVIEW_COLUMN,
            f"{human_review!r} is not one of BMR-Review's documented review "
            f"codes. Treating it as unresolved rather than guessing; see "
            f"BMR-REVIEW-CONTRACT.md.")

    # --- STEP 2: no human; the three-clause rule ------------------------
    if not clears_without_a_human(assessment):
        return _make("NEEDS_REVIEW", "", ASSESSMENT_COLUMN,
                     f"{assessment!r} needs a reviewer and has not had one.")

    if require_human:
        # The opt-out (--require-human-review). Not the default: the
        # operator ruled 2026-09-12 that BMR-Review's own clearance is
        # accepted. This branch exists for a batch held to a stricter
        # standard than BMR-Review's, not for ordinary runs.
        return _make(
            "NOT_CLEARED", "", ASSESSMENT_COLUMN,
            f"{assessment!r} clears without a reviewer on BMR-Review's own "
            f"rule, but this run was asked to require a human decision "
            f"(--require-human-review).")

    got = _classify_value(
        proposed, source=f"{PROPOSED_MATCH_COLUMN} ({assessment})",
        sheet_row=sheet_row, row_id=row_id, assessment=assessment,
        human_review="", sentinels=sentinels)
    return got


def _check_against_assertion(got: Resolution, row: dict,
                             sentinels: Collection[str] = NO_ID_SENTINELS) -> Resolution:
    """Never silently overwrite a member's own Assigned EIDR ID.

    In this repo's own flow the column was blanked by ``--subset``, so this
    only fires on a sheet that did not come through us. When it does, the
    disagreement is the finding.
    """
    if got.status != "CONFIRMED":
        return got
    existing = trim(row.get(ASSIGNED_ID_COLUMN))
    if not existing or existing.lower() in sentinels:
        return got
    asserted = read_asserted_id(existing, sentinels)
    if asserted.invalid or asserted.absent:
        return got
    if asserted.value == got.resolved_id:
        return got
    return got._replace(
        status="UNRESOLVED", resolved_id="",
        detail=(f"{got.source} resolved to {got.resolved_id}, but the sheet "
                f"already asserts {asserted.value} in "
                f"{ASSIGNED_ID_COLUMN!r}. Not overwriting a member's own "
                f"assertion; the disagreement needs a human."))


def resolve_sheet(path: str, sheet: str, *, require_human: bool = False,
                  assigned_id_role: str = "member",
                  no_id_sentinels: Collection[str] = NO_ID_SENTINELS,
                  ) -> list[Resolution]:
    """Resolve every data row of an assessed-and-reviewed BMR sheet.

    Raises ``ValueError`` when the sheet carries no ``EIDR Assessment``
    column: that is not an assessed sheet, it fails identically on every
    row, and so it is systemic -- refused at the header before any row is
    read, like a missing Domain column.
    """
    out: list[Resolution] = []
    with open_sheet(path, sheet, stop="blank_first_col") as (headers, rows):
        names = {h for h in headers.values() if h}
        if ASSESSMENT_COLUMN not in names:
            raise ValueError(
                f"{sheet!r} has no {ASSESSMENT_COLUMN!r} column, so it has "
                f"not been through BMR-Review's assessment. Run "
                f"run_assessment.py on it first (see "
                f"BMR-REVIEW-CONTRACT.md). Headers seen: "
                + ", ".join(sorted(names)))
        for sheet_row, row in rows:
            out.append(resolve_row(row, sheet_row, require_human=require_human,
                                   assigned_id_role=assigned_id_role,
                                   no_id_sentinels=no_id_sentinels))
    return out


def fill_map(resolutions: list[Resolution]) -> dict[int, str]:
    """``{sheet_row: eidr_id}`` for the CONFIRMED rows, and only those."""
    return {r.sheet_row: r.resolved_id
            for r in resolutions if r.status == "CONFIRMED"}


def summarize(resolutions: list[Resolution]) -> ResolveStats:
    counts: dict[str, int] = {}
    for r in resolutions:
        counts[r.status] = counts.get(r.status, 0) + 1
    return ResolveStats(rows_read=len(resolutions), by_status=counts)
