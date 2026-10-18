"""external.wikimedia (C8 part 1, 0.63.0): the access rules whose breach is
silent until Wikimedia blocks the machine -- a missing contact, an
undecoded gzip body, a maxlag refusal taken for data, a 429 the next request
ignores."""
from __future__ import annotations

import gzip
import io
import json
import urllib.error

import pytest

from eidr_core.external import RequestPacer
from eidr_core.external import wikimedia as W


class Resp:
    def __init__(self, body: dict, *, gz=False, headers=None):
        raw = json.dumps(body).encode()
        self._raw = gzip.compress(raw) if gz else raw
        self.headers = {"Content-Encoding": "gzip"} if gz else {}
        self.headers.update(headers or {})

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Opener:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.requests = []

    def __call__(self, req, timeout):
        self.requests.append(req)
        a = self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a


class Pacer(RequestPacer):
    def __init__(self):
        super().__init__(min_interval=0.0, clock=lambda: 0.0, sleep=lambda s: None)
        self.backed = []

    def back_off(self, seconds):
        self.backed.append(seconds)


UA = "eidr-test/1.0 (https://eidr.org)"


def _http(code, retry_after=None):
    hdrs = {"Retry-After": retry_after} if retry_after is not None else {}
    return urllib.error.HTTPError("u", code, "x", hdrs, io.BytesIO(b""))


def test_user_agent_needs_a_contact():
    assert W.user_agent("eidr-dq", "1.0", "dq@eidr.org") == "eidr-dq/1.0 (dq@eidr.org)"
    assert W.user_agent("x", "2", "https://eidr.org") == "x/2 (https://eidr.org)"
    for bad in ("", "eidr", "Mozilla/5.0"):
        with pytest.raises(ValueError):
            W.user_agent("x", "1", bad)


def test_gzip_maxlag_and_user_agent_reach_the_request():
    op = Opener(Resp({"entities": {"Q1": {}}}, gz=True))
    got = W.action_api_json({"action": "wbgetentities", "ids": "Q1"}, user_agent=UA,
                            pacer=Pacer(), opener=op, backoff=0)
    assert got == {"entities": {"Q1": {}}}
    req = op.requests[0]
    assert req.get_header("User-agent") == UA and req.get_header("Accept-encoding") == "gzip"
    assert "maxlag=5" in req.full_url and "format=json" in req.full_url


def test_a_maxlag_refusal_is_a_wait_not_data():
    op = Opener(Resp({"error": {"code": "maxlag"}}, headers={"Retry-After": "0"}),
                Resp({"ok": 1}))
    p = Pacer()
    assert W.action_api_json({"action": "query"}, user_agent=UA, pacer=p, opener=op,
                             backoff=0) == {"ok": 1}
    assert len(op.requests) == 2


def test_a_429_makes_the_next_request_wait_and_a_400_stops(monkeypatch):
    # The chassis itself waits out the 5 s floor; not in a unit test.
    monkeypatch.setattr("eidr_core.external.failover.time.sleep", lambda s: None)
    p = Pacer()
    op = Opener(_http(429, "0"), Resp({"ok": 1}))
    W.action_api_json({"action": "query"}, user_agent=UA, pacer=p, opener=op, backoff=0)
    op2 = Opener(_http(429), Resp({"ok": 1}))
    W.action_api_json({"action": "query"}, user_agent=UA, pacer=p, opener=op2, backoff=0)
    assert p.backed[-1] == W.MIN_429_WAIT_SECONDS          # no Retry-After: 5 s floor
    with pytest.raises(urllib.error.HTTPError):
        W.action_api_json({"action": "query"}, user_agent=UA, pacer=Pacer(),
                          opener=Opener(_http(400)), backoff=0)


def test_the_pacer_is_on_the_machine_wide_scope(tmp_path):
    p = W.action_api_pacer(scope_dir=str(tmp_path))
    assert p.shared_scope == W.ACTION_API_SCOPE == "wikimedia-action-api"
    assert p.min_interval == 0.3
    assert W.action_api_pacer(0.1, scope_dir=str(tmp_path)).min_interval == 0.3


def test_the_sparql_pacer_and_chain_follow_qlevers_conditions(tmp_path):
    p = W.sparql_pacer(scope_dir=str(tmp_path))
    assert p.shared_scope == W.SPARQL_SCOPE == "wikidata-sparql"
    assert p.min_interval == 1.0 and p.slow_pause == 0.0
    # QAC1: QLever only after WDQS; QAC2: its Wikidata endpoint only.
    assert W.SPARQL_CHAIN[0] == W.WDQS_ENDPOINT
    assert all(u.endswith("/api/wikidata") for u in W.QLEVER_WIKIDATA_ENDPOINTS)


def test_the_default_opener_is_looked_up_at_call_time(monkeypatch):
    # eidr-wikidata (2026-10-18): an import-time default meant patching
    # urllib.request.urlopen never reached the request.
    op = Opener(Resp({"ok": 1}))
    monkeypatch.setattr("urllib.request.urlopen", op)
    assert W.action_api_json({"action": "query"}, user_agent=UA, pacer=Pacer()) == {"ok": 1}
    assert len(op.requests) == 1
