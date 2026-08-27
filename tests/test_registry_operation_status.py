"""
Pin the registry operation-status parse against captured production bodies.

These are the first tests in eidr-core. The library's testing story has so
far been "sibling programs' conformance tests are the propagation
mechanism" (CLAUDE.md), which works for spec-driven modules whose consumers
re-verify them — but this module is a *safety* surface: the whole reason it
exists is that a wrong answer is silent and costs production records. It
has to be pinned where it lives.

The XML bodies below are captured verbatim from the production registry
during the 2026-08-09 investigation (token 1786308010989200992), not
hand-written to match the implementation.
"""

from __future__ import annotations

import dataclasses

import pytest

from eidr_core.registry import (
    OperationStatus,
    parse_operation_status,
    parse_operation_statuses,
    token_operation_status,
)

# Captured verbatim from production. The shape that matters: the ENVELOPE
# says Code 0 / success while the OPERATION says Code 4 / validation error.
REJECTED = """<?xml version="1.0" encoding="UTF-8"?>
<Response xmlns="http://www.eidr.org/schema" version="2.7.1">
  <Status><Code>0</Code><Type>success</Type></Status>
  <RequestStatus><Token>1786308010989200992</Token>
    <PageNumber>1</PageNumber><PageSize>25</PageSize></RequestStatus>
  <RequestStatusResults><CurrentSize>1</CurrentSize><TotalMatches>1</TotalMatches>
    <OperationStatus>
      <Token>1786308010989200992</Token>
      <Status>
        <Code>4</Code>
        <Type>validation error</Type>
        <Details>Duplicate Alternate ID: Proprietary, 6406358491388851112, comcast.com</Details>
      </Status>
    </OperationStatus>
  </RequestStatusResults>
</Response>"""

APPLIED = """<Response>
  <Status><Code>0</Code><Type>success</Type></Status>
  <RequestStatusResults>
    <OperationStatus>
      <Token>1786308010989200993</Token>
      <Status><Code>0</Code><Type>success</Type></Status>
    </OperationStatus>
  </RequestStatusResults>
</Response>"""

# No verdict reached yet: envelope only, no OperationStatus block at all.
NO_VERDICT = """<Response>
  <Status><Code>0</Code><Type>success</Type></Status>
  <RequestStatus><Token>1786308010989200992</Token></RequestStatus>
  <RequestStatusResults><CurrentSize>0</CurrentSize><TotalMatches>0</TotalMatches>
  </RequestStatusResults>
</Response>"""

# A paged lookup carrying several verdicts — PageSize is 25, so a batch
# writer routinely gets more than one per body.
BATCH = """<Response>
  <Status><Code>0</Code><Type>success</Type></Status>
  <RequestStatusResults><CurrentSize>3</CurrentSize><TotalMatches>3</TotalMatches>
    <OperationStatus><Token>t1</Token>
      <Status><Code>0</Code><Type>success</Type></Status></OperationStatus>
    <OperationStatus><Token>t2</Token>
      <Status><Code>4</Code><Type>validation error</Type>
        <Details>Duplicate Alternate ID: Proprietary, 999, comcast.com</Details>
      </Status></OperationStatus>
    <OperationStatus><Token>t3</Token>
      <Status><Code>7</Code><Type>authorization error</Type></Status></OperationStatus>
  </RequestStatusResults>
</Response>"""


class TestRejection:
    """The bug that started this: a rejected write must not read as pending."""

    def test_rejection_is_surfaced(self):
        status = parse_operation_status(REJECTED)
        assert status is not None, "a rejected write must not parse as 'no verdict'"
        assert status.code == 4
        assert status.type == "validation error"
        assert status.is_failure
        assert not status.is_success

    def test_details_identifies_the_offending_alt_id(self):
        # Details is the only field naming WHICH Alt ID collided, so it is
        # the difference between an actionable report and "something broke".
        status = parse_operation_status(REJECTED)
        assert "6406358491388851112" in status.details
        assert "comcast.com" in status.details

    def test_envelope_success_can_never_be_read_as_the_verdict(self):
        # The load-bearing assertion. The envelope's Code 0 appears FIRST in
        # the document; an unanchored parse would return it and report a
        # rejected write as applied. If this fails, the module is worse than
        # useless -- it is confidently wrong.
        status = parse_operation_status(REJECTED)
        assert status.code != 0
        assert status.type != "success"

    def test_token_comes_from_the_operation_block(self):
        assert parse_operation_status(REJECTED).token == "1786308010989200992"


class TestThreeWayDistinction:
    """success / failed-with-reason / no-verdict-yet must stay distinguishable."""

    def test_applied_write_is_success(self):
        status = parse_operation_status(APPLIED)
        assert status is not None
        assert status.is_success and not status.is_failure

    def test_no_operation_block_means_no_verdict(self):
        # None, NOT a failure. Collapsing "unknown" into "failed" merely
        # inverts the original bug and would make the applier abandon
        # writes that are still legitimately in flight.
        assert parse_operation_status(NO_VERDICT) is None

    @pytest.mark.parametrize("body", [None, "", b""])
    def test_empty_bodies_yield_no_verdict(self, body):
        assert parse_operation_status(body) is None

    def test_instances_never_represent_unknown(self):
        # The invariant is_failure relies on: every OperationStatus is a
        # verdict that was actually reached, so is_failure == not is_success.
        for body in (REJECTED, APPLIED):
            status = parse_operation_status(body)
            assert status.is_success != status.is_failure


class TestBatch:
    """A paged body carries a verdict per operation; none may be dropped."""

    def test_every_verdict_is_returned(self):
        statuses = parse_operation_statuses(BATCH)
        assert [s.token for s in statuses] == ["t1", "t2", "t3"]
        assert [s.code for s in statuses] == [0, 4, 7]

    def test_failures_are_identifiable_within_the_batch(self):
        failed = [s for s in parse_operation_statuses(BATCH) if s.is_failure]
        assert {s.token for s in failed} == {"t2", "t3"}

    def test_missing_details_is_empty_not_an_error(self):
        # t3 carries no <Details>; the parse must still yield the verdict.
        t3 = [s for s in parse_operation_statuses(BATCH) if s.token == "t3"][0]
        assert t3.details == ""
        assert t3.type == "authorization error"

    def test_singular_form_returns_the_first(self):
        assert parse_operation_status(BATCH).token == "t1"

    def test_no_verdict_yields_empty_list(self):
        assert parse_operation_statuses(NO_VERDICT) == []


class TestEncodingAndFallbacks:
    def test_bytes_body_is_accepted(self):
        # raw_body arrives as bytes from some transports.
        status = parse_operation_status(REJECTED.encode("utf-8"))
        assert status.code == 4

    def test_undecodable_bytes_do_not_raise(self):
        assert parse_operation_status(b"\xff\xfe not xml") is None

    def test_caller_token_fills_in_when_the_block_omits_it(self):
        body = ("<Response><RequestStatusResults><OperationStatus>"
                "<Status><Code>4</Code><Type>validation error</Type></Status>"
                "</OperationStatus></RequestStatusResults></Response>")
        assert parse_operation_status(body, token="fallback").token == "fallback"

    def test_body_token_wins_over_caller_token(self):
        assert parse_operation_status(REJECTED, token="wrong").token == \
            "1786308010989200992"


class _FakeResponse:
    def __init__(self, raw_body):
        self.raw_body = raw_body
        # The envelope fields a caller would naively read. Present precisely
        # so a regression that starts trusting them fails loudly here.
        self.status_code = 0
        self.status_type = "success"


class _FakeToken:
    def __init__(self, raw_body, poll_raises=False):
        self.value = "1786308010989200992"
        self.last_response = _FakeResponse(raw_body)
        self._poll_raises = poll_raises
        self.polled = False

    def poll(self):
        self.polled = True
        if self._poll_raises:
            raise RuntimeError("transport died")


class TestTokenOperationStatus:
    def test_polls_then_reads_the_verdict(self):
        token = _FakeToken(REJECTED)
        status = token_operation_status(token)
        assert token.polled
        assert status.code == 4

    def test_poll_failure_yields_no_verdict_rather_than_raising(self):
        # This runs on the error path of a write loop; it must never be the
        # reason a run dies. The body is still readable, but a failed poll
        # means it may be stale -- callers get "ask again later".
        token = _FakeToken(NO_VERDICT, poll_raises=True)
        assert token_operation_status(token) is None

    def test_missing_response_is_tolerated(self):
        class _Bare:
            value = "t"

            def poll(self):
                pass

        assert token_operation_status(_Bare()) is None

    def test_str_is_operator_readable(self):
        # The applier logs this string; it must name the offending Alt ID.
        text = str(parse_operation_status(REJECTED))
        assert "code=4" in text and "comcast.com" in text


def test_dataclass_is_hashable_and_frozen():
    # Appliers accumulate these in sets/dicts keyed by outcome.
    status = parse_operation_status(REJECTED)
    assert isinstance(status, OperationStatus)
    hash(status)
    with pytest.raises(dataclasses.FrozenInstanceError):
        status.code = 0


# ---------------------------------------------------------------------------
# get_registry_client(writable=...) — raised by eidr-dq 2026-08-27.
#
# eidr-dq is read-only against the registry by design and previously passed
# writable=False when it built the Registry itself. Adopting the factory lost
# that assertion, turning a guarantee the SDK enforces into a convention the
# next reader has to re-verify. These pin the ARGUMENT CONTRACT without
# needing the SDK installed: the guard rejects target shapes that cannot
# carry the flag, and it does so BEFORE the lazy SDK import.
# ---------------------------------------------------------------------------

def test_writable_is_rejected_on_a_named_target():
    from eidr_core.registry import get_registry_client
    with pytest.raises(ValueError, match="only to a URL registry target"):
        get_registry_client(registry="sandbox2", writable=False)


def test_writable_is_rejected_rather_than_silently_ignored():
    # The whole point of the argument is to make a safety assertion. Dropping
    # it on an unsupported target shape would leave the caller believing a
    # guarantee they do not have -- the exact failure this removes.
    from eidr_core.registry import get_registry_client
    with pytest.raises(ValueError):
        get_registry_client(registry="production", writable=True)


def test_omitting_writable_does_not_reach_the_guard():
    # Default None must leave every existing call site byte-identical. With
    # no SDK installed the call fails at the lazy import, NOT at the guard --
    # proving the guard is not on the default path.
    from eidr_core.registry import get_registry_client
    with pytest.raises((ImportError, Exception)) as ei:
        get_registry_client(registry="sandbox2")
    assert "only to a URL registry target" not in str(ei.value)
