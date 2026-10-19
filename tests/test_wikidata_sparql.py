"""C8 part 3 (0.66.0): the SPARQL transport and imdb_qids -- a POST QLever
silently refuses, a fallback that hides which endpoint answered, a tie between
claimants decided by chance."""
from __future__ import annotations

import gzip
import io
import json
import urllib.error

from eidr_core.external import NEXT_ENDPOINT, OUTAGE, RETRY, RequestPacer
from eidr_core.external import wikidata as WD
from eidr_core.external import wikimedia as W
from eidr_core.external.failover import FATAL

UA = "eidr-test/1.0 (https://eidr.org)"


class Resp:
    def __init__(self, body, gz=False):
        raw = json.dumps(body).encode()
        self._raw = gzip.compress(raw) if gz else raw
        self.headers = {"Content-Encoding": "gzip"} if gz else {}

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Opener:
    def __init__(self, answer):
        self.answer = answer
        self.requests = []

    def __call__(self, req, timeout):
        self.requests.append(req)
        a = self.answer(req)
        if isinstance(a, Exception):
            raise a
        return a


def _pacer():
    return RequestPacer(0.0, clock=lambda: 0.0, sleep=lambda s: None)


def _http(code):
    return urllib.error.HTTPError("u", code, "x", {}, io.BytesIO(b""))


def test_qlever_gets_get_wdqs_gets_post_and_gzip_is_decoded():
    op = Opener(lambda r: Resp({"results": {"bindings": []}}, gz=True))
    W.sparql_request(W.WDQS_ENDPOINT, "SELECT 1", user_agent=UA, opener=op)
    W.sparql_request(W.QLEVER_WIKIDATA_ENDPOINTS[0], "SELECT 1", user_agent=UA, opener=op)
    assert [r.get_method() for r in op.requests] == ["POST", "GET"]
    assert all(r.get_header("Accept-encoding") == "gzip" for r in op.requests)


def test_the_classifier_reads_urllibs_structure():
    assert W.classify_sparql_http(_http(429)) == RETRY
    assert W.classify_sparql_http(_http(414)) == NEXT_ENDPOINT
    assert W.classify_sparql_http(_http(403)) == FATAL
    assert W.classify_sparql_http(urllib.error.URLError("reset")) == RETRY
    assert W.classify_sparql_http(TimeoutError()) == RETRY
    # The shared outage signatures win before the status code.
    assert W.classify_sparql_http(Exception("WDQS outage: 429 everywhere")) == OUTAGE


def test_select_falls_back_to_qlever_and_says_so(monkeypatch):
    monkeypatch.setattr("eidr_core.external.failover.time.sleep", lambda s: None)

    def answer(req):
        if "query.wikidata.org" in req.full_url:
            return _http(503)
        return Resp({"results": {"bindings": [{"x": {"value": "1"}}]}})
    rows, used = W.sparql_select("SELECT ?x {}", user_agent=UA, pacer=_pacer(),
                                 opener=Opener(answer), max_retries=1)
    assert rows == [{"x": {"value": "1"}}] and used == W.QLEVER_WIKIDATA_ENDPOINTS[0]


def test_select_returns_nothing_when_the_chain_fails(monkeypatch):
    monkeypatch.setattr("eidr_core.external.failover.time.sleep", lambda s: None)
    assert W.sparql_select("SELECT 1", user_agent=UA, pacer=_pacer(), max_retries=1,
                           opener=Opener(lambda r: _http(503))) == ([], None)


def test_imdb_qids_cleans_ids_and_lowest_qid_wins():
    def answer(req):
        return Resp({"results": {"bindings": [
            {"imdb": {"value": "tt1"}, "item": {"value": "http://www.wikidata.org/entity/Q90"}},
            {"imdb": {"value": "tt1"}, "item": {"value": "http://www.wikidata.org/entity/Q12"}},
            {"imdb": {"value": "tt2"}, "item": {"value": "http://www.wikidata.org/entity/L5"}}]}})
    op = Opener(answer)
    got = WD.imdb_qids([" TT1 ", "tt2", "nonsense", "tt1"], user_agent=UA, pacer=_pacer(),
                       opener=op)
    assert got == {"tt1": "Q12"}
    assert len(op.requests) == 1 and b"VALUES" in op.requests[0].data
