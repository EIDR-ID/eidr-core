"""
The registry's verdict on a submitted write — success, failure, or no verdict yet.

Why this module exists (2026-08-09)
-----------------------------------
A registry status lookup nests TWO statuses, and only the outer one is
obvious:

* the **envelope** status — did the status-lookup call itself work;
* the **operation** status — what happened to the write you submitted.

When the registry REJECTS a write, the envelope still says success. The
rejection lives in the inner ``OperationStatus``, captured verbatim from
production (token ``1786308010989200992``)::

    <Response><Status><Code>0</Code><Type>success</Type></Status>
      <RequestStatusResults><OperationStatus>
        <Token>1786308010989200992</Token>
        <Status><Code>4</Code><Type>validation error</Type>
          <Details>Duplicate Alternate ID: Proprietary, 640..., comcast.com</Details>
        </Status>
      </OperationStatus></RequestStatusResults></Response>

As of SDK v1.1.1 ``Token.poll()`` / ``Token.operation_result()`` leave that
token reporting **pending** — the ``Code 4`` is never surfaced, and
``last_response.status_code`` carries the ENVELOPE's ``0 / success``. A
caller reading the obvious fields sees a successful lookup of a pending
operation, which is the exact opposite of the truth.

The cost is measured, not theoretical: the 2026-07-18 production
remediation left 62 of 152,639 records unapplied. The applier logged them
as timeouts, the operator never learned a validation error existed, and the
records sat broken for three weeks until a re-run reproduced the failure
identically. The registry had been reporting precisely what was wrong the
whole time.

Why it lives in eidr-core rather than in one consumer
-----------------------------------------------------
This module's sibling ``__init__`` documents ``token.operation_result()``
as THE portfolio write pattern, so eidr-core was advertising the unsafe
call. Three independent implementations of this parse already exist
(eidr-wikidata's ``eidr/registry_errors.py``; BulkMatchRegister's
``ApplyModBaseToolWrapper`` and ``StatusToolWrapper``, over Java CLI
stdout), which is the duplication trigger in OVERLAPS.md / register R5.

**This is a seam, not a workaround.** The three-way distinction below is a
fact about the registry protocol and stays useful after the SDK is fixed;
only the *implementation* underneath is temporary. When the SDK surfaces
operation status natively, rewrite the body of ``token_operation_status``
to read it and leave this API alone — consumers should not have to change.

"Pending" inside the block (2026-10-01)
---------------------------------------
The registry can also put its "still processing" state INSIDE the
``<OperationStatus>`` block, as ``<Code>2</Code><Type>pending</Type>``.
LanguageTool polled five sandbox1 writes on 2026-10-01: four came back that
way, read as REJECTED (``is_failure`` is ``not is_success``), and a minute
later all four were ``0 / success``. That is the 2026-07-18 incident
inverted -- successes reported as rejections, and a caller that retries on
``is_failure`` re-submits writes that already landed. Such a block is no
verdict, so the parse skips it: "no verdict yet" again has exactly one
representation, ``None`` (or absence from the batch list).

The parse is deliberately regex-over-raw-XML rather than ElementTree:
``raw_body`` is the one field the SDK hands over untouched, so this keeps
working even if the SDK's own parsing changes underneath us.
"""

from __future__ import annotations

import contextlib
import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

__all__ = [
    "CODE_PENDING",
    "CODE_SUCCESS",
    "OperationStatus",
    "parse_operation_status",
    "parse_operation_statuses",
    "token_operation_status",
]

# Anchored on <OperationStatus> so the ENVELOPE's Status can never match —
# that confusion is the entire bug this module exists to prevent, so the
# anchor is load-bearing and is pinned by a test.
# <Details> is optional: the registry omits it for some outcomes.
_OP_STATUS_RE = re.compile(
    r"<OperationStatus>\s*"
    r"(?:<Token>(?P<token>[^<]*)</Token>\s*)?"
    r".*?"
    r"<Code>(?P<code>\d+)</Code>\s*"
    r"<Type>(?P<type>[^<]*)</Type>"
    r"(?:\s*<Details>(?P<details>[^<]*)</Details>)?",
    re.S,
)

# The registry's only success code. Everything else is a rejection with a
# reason; there is no "partially applied" verdict — see register R5 on the
# all-or-nothing transaction semantics.
CODE_SUCCESS = 0

# The registry's in-block "still processing" status (observed 2026-10-01 on
# sandbox1: Code 2 / Type pending). Not a verdict: skipped by the parse.
CODE_PENDING = 2
_PENDING_TYPES = frozenset({"pending"})


@dataclass(frozen=True)
class OperationStatus:
    """The registry's verdict on ONE submitted write.

    An instance always represents a verdict that has been *reached*. "No
    verdict yet" is represented by ``None`` from the parse functions, never
    by an instance — keeping those two apart is the whole point, so there
    is deliberately no ``is_pending`` here to blur them.
    """

    code: int
    type: str
    details: str
    token: str = ""

    @property
    def is_success(self) -> bool:
        return self.code == CODE_SUCCESS

    @property
    def is_failure(self) -> bool:
        """True when the registry has actually REJECTED the write.

        Safe as the negation of success only because an instance never
        represents "unknown" (see the class docstring). Callers holding an
        ``OperationStatus | None`` must branch on ``None`` first; treating
        a missing verdict as failure just inverts the SDK bug.
        """
        return not self.is_success

    def __str__(self) -> str:
        base = f"code={self.code} type={self.type or '?'}"
        return f"{base} details={self.details}" if self.details else base


def _iter_matches(raw_body: str | bytes | None) -> Iterator[OperationStatus]:
    if not raw_body:
        return
    text = (raw_body.decode("utf-8", "replace")
            if isinstance(raw_body, bytes) else raw_body)
    for m in _OP_STATUS_RE.finditer(text):
        code = int(m.group("code"))
        type_ = (m.group("type") or "").strip()
        # A pending block is the registry saying "no verdict yet" in-band.
        # Yielding it would make is_failure true for a write that may still
        # succeed (see the module docstring, 2026-10-01).
        if code == CODE_PENDING or type_.lower() in _PENDING_TYPES:
            continue
        yield OperationStatus(
            code=code,
            type=type_,
            details=(m.group("details") or "").strip(),
            token=(m.group("token") or "").strip(),
        )


def parse_operation_statuses(raw_body: str | bytes | None) -> list[OperationStatus]:
    """Extract EVERY operation status from a status-lookup body.

    A status lookup is paged (the envelope carries ``PageSize``, default
    25), so one body can carry a verdict per submitted operation. Batch
    writers must read all of them — taking only the first would silently
    drop the other 24 verdicts, which is the same class of data loss this
    module exists to stop.

    Returns an empty list when the body carries no ``<OperationStatus>``
    block at all — i.e. no verdict has been reached yet. A block that says
    pending (code 2) is likewise left out: the list holds verdicts reached,
    and a token missing from it is still in flight.
    """
    return list(_iter_matches(raw_body))


def parse_operation_status(raw_body: str | bytes | None,
                           token: str = "") -> OperationStatus | None:
    """Extract the FIRST operation status from a status-lookup body.

    The single-write convenience form. Returns ``None`` when the body
    carries no ``<OperationStatus>`` block, or only a pending one (code 2) —
    read that as "still pending", never as success or failure.

    ``token`` supplies the token value for bodies that omit it from the
    block; a token parsed out of the body always wins.
    """
    for status in _iter_matches(raw_body):
        if status.token or not token:
            return status
        # Body had no <Token> in the block — attribute it to the caller's.
        return OperationStatus(code=status.code, type=status.type,
                               details=status.details, token=token)
    return None


def token_operation_status(token: Any) -> OperationStatus | None:
    """Poll a live SDK ``Token`` and return the registry's verdict on it.

    Best-effort by design: a token that cannot be polled yields ``None``
    rather than raising, because this runs on the error path of a write
    loop and must never itself become the reason a run dies.

    ``None`` means "no verdict available" — either the registry has not
    reached one or the poll failed. Callers deciding whether to retry
    should treat it as "ask again later", not as either outcome.
    """
    with contextlib.suppress(Exception):  # see docstring: never fail the caller
        token.poll()
    resp = getattr(token, "last_response", None)
    return parse_operation_status(getattr(resp, "raw_body", None),
                                  getattr(token, "value", "") or "")
