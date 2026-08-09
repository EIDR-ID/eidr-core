"""Tests for eidr_core.external.failover — the R13 retry/failover chassis.

Like the registry tests, these break eidr-core's no-local-tests convention
deliberately: the chassis's wrong answer is silent (a misclassified verdict
or a swallowed result does not crash — it quietly erases external-fact
coverage, which is exactly the R13 finding this extraction closes).

All tests run with ``backoff=0, jitter=0, delay_seconds=0`` so every
internal sleep is ``time.sleep(0)`` — deterministic and instant.
"""
from __future__ import annotations

import pytest

from eidr_core.external.failover import (
    FATAL,
    NEXT_ENDPOINT,
    OUTAGE,
    RETRY,
    call_with_failover,
    classify_sparql_error,
    endpoint_chain,
)

FAST = dict(backoff=0.0, jitter=0.0, delay_seconds=0.0)


class Script:
    """An attempt callable driven by a per-endpoint list of outcomes.

    Each entry is either an Exception instance (raised) or a value
    (returned). Records the call sequence for walk-order assertions.
    """

    def __init__(self, outcomes: dict[str, list]):
        self.outcomes = {k: list(v) for k, v in outcomes.items()}
        self.calls: list[str] = []

    def __call__(self, endpoint: str):
        self.calls.append(endpoint)
        out = self.outcomes[endpoint].pop(0)
        if isinstance(out, Exception):
            raise out
        return out


def classify_all(verdict: str):
    return lambda exc: verdict


# --- endpoint_chain ---------------------------------------------------------

def test_chain_primary_then_fallbacks():
    assert endpoint_chain("a", ["b", "c"]) == ["a", "b", "c"]


def test_chain_drops_blanks_and_duplicates():
    # A config that lists the primary again as a fallback must not make
    # the walk visit it twice.
    assert endpoint_chain(" a ", ["", None, "a", "b "]) == ["a", "b"]


def test_chain_no_primary():
    assert endpoint_chain(None, ["b"]) == ["b"]
    assert endpoint_chain("", []) == []


# --- call_with_failover: success paths --------------------------------------

def test_first_endpoint_first_attempt():
    script = Script({"a": ["ok"]})
    result, used, exc = call_with_failover(
        ["a", "b"], script, classify_all(RETRY), **FAST)
    assert (result, used, exc) == ("ok", "a", None)
    assert script.calls == ["a"]


def test_transient_retries_same_endpoint_then_succeeds():
    script = Script({"a": [RuntimeError("503"), "ok"]})
    result, used, exc = call_with_failover(
        ["a", "b"], script, classify_all(RETRY), **FAST)
    assert (result, used, exc) == ("ok", "a", None)
    assert script.calls == ["a", "a"]


def test_retry_budget_exhausted_falls_over():
    script = Script({"a": [RuntimeError("503")] * 3, "b": ["ok"]})
    result, used, exc = call_with_failover(
        ["a", "b"], script, classify_all(RETRY), max_retries=3, **FAST)
    assert (result, used, exc) == ("ok", "b", None)
    assert script.calls == ["a", "a", "a", "b"]


# --- verdict walk semantics --------------------------------------------------

def test_next_endpoint_moves_on_without_retry():
    script = Script({"a": [RuntimeError("QueryBadFormed")], "b": ["ok"]})
    result, used, _ = call_with_failover(
        ["a", "b"], script, classify_all(NEXT_ENDPOINT), **FAST)
    assert (result, used) == ("ok", "b")
    assert script.calls == ["a", "b"]  # exactly one attempt on a


def test_outage_fails_fast_and_memoizes():
    memo: set[str] = set()
    script = Script({"a": [RuntimeError("wdqs outage")], "b": ["ok", "ok2"]})
    result, used, _ = call_with_failover(
        ["a", "b"], script, classify_all(OUTAGE),
        outage_endpoints=memo, **FAST)
    assert (result, used) == ("ok", "b")
    assert memo == {"a"}

    # Second call in the same multi-chunk operation: the memo makes the
    # walk skip the outage endpoint without attempting it at all.
    result2, used2, _ = call_with_failover(
        ["a", "b"], script, classify_all(OUTAGE),
        outage_endpoints=memo, **FAST)
    assert (result2, used2) == ("ok2", "b")
    assert script.calls == ["a", "b", "b"]


def test_fatal_stops_the_walk():
    boom = RuntimeError("401 unauthorized")
    script = Script({"a": [boom], "b": ["never reached"]})
    result, used, exc = call_with_failover(
        ["a", "b"], script, classify_all(FATAL), **FAST)
    assert (result, used) == (None, None)
    assert exc is boom
    assert script.calls == ["a"]  # b untouched — no endpoint will help


def test_unknown_verdict_degrades_to_next_endpoint():
    # A misspelled verdict must degrade to FEWER attempts, not more.
    script = Script({"a": [RuntimeError("x")], "b": ["ok"]})
    result, used, _ = call_with_failover(
        ["a", "b"], script, classify_all("tranisent-typo"), **FAST)
    assert (result, used) == ("ok", "b")
    assert script.calls == ["a", "b"]


def test_all_endpoints_exhausted_returns_last_exception():
    last = RuntimeError("second")
    script = Script({"a": [RuntimeError("first")], "b": [last]})
    result, used, exc = call_with_failover(
        ["a", "b"], script, classify_all(NEXT_ENDPOINT), **FAST)
    assert (result, used) == (None, None)
    assert exc is last


def test_empty_chain_returns_none_triple():
    result, used, exc = call_with_failover(
        [], lambda ep: "ok", classify_all(RETRY), **FAST)
    assert (result, used, exc) == (None, None, None)


# --- classify_sparql_error ---------------------------------------------------

@pytest.mark.parametrize("msg,verdict", [
    # Outage wins over the "429" embedded in the same message — the real
    # 2026-05-09 WDQS text carried both.
    ("HTTP 429: Aggressively rate-limiting to 1 req / min - this rule was "
     "created during active wdqs outage (d60aac9)", OUTAGE),
    ("QueryBadFormed: malformed query", NEXT_ENDPOINT),
    ("Invalid SPARQL query", NEXT_ENDPOINT),
    ("Bad Request: SPARQL parse failure", NEXT_ENDPOINT),
    ("HTTP Error 503: Service Unavailable", RETRY),
    ("HTTP Error 500: Internal Server Error", RETRY),  # dq harmonization
    ("EndPointNotFound: no such host", NEXT_ENDPOINT),
])
def test_classify_sparql_error(msg, verdict):
    assert classify_sparql_error(RuntimeError(msg)) == verdict
