"""The 0.47.0 widenings, each asked for in a 2026-10-02 dictionary reply.

Each is additive, so the pins below are of two kinds: the new behaviour does
what was asked, and the old behaviour is untouched where a caller relied on it.
A wrong answer from any of these is silent (a missed identity link, a
ShortDOI counted as evidence, a request paced too fast), which is why they
are pinned here rather than left to consumers.
"""
import re

import pytest

from eidr_core.altidtool_io import identity_relation_sql, is_identity_relation
from eidr_core.external import NEXT_ENDPOINT, OUTAGE, RETRY, RequestPacer, classify_sparql_error
from eidr_core.ids import CONTENT_ID_SEARCH_RE, CONTENT_ID_SUFFIX, EIDR_CONTENT_ID_RE
from eidr_core.ordering import is_shortdoi

# -- ordering.is_shortdoi strips (BMR-Review 3a) -----------------------------

def test_is_shortdoi_ignores_surrounding_whitespace():
    assert is_shortdoi(" ShortDOI ", None)
    assert is_shortdoi("Proprietary", " shortdoi")
    assert not is_shortdoi("IMDB", "imdb.com")


# -- the identity relation (BMR-Review 3b) -----------------------------------

@pytest.mark.parametrize("rel", [None, "", "   ", "IsSameAs", "issameas", " ISSAMEAS "])
def test_identity_relations(rel):
    assert is_identity_relation(rel)


@pytest.mark.parametrize("rel", ["IsDerivedFrom", "Deprecated", "IsEntirelyContainedBy", "x"])
def test_non_identity_relations(rel):
    assert not is_identity_relation(rel)


def test_identity_relation_sql_matches_the_mirror_form_and_refuses_injection():
    assert identity_relation_sql() == "(relation IS NULL OR relation = '' OR relation = 'IsSameAs')"
    assert identity_relation_sql("a.relation").startswith("(a.relation IS NULL")
    for bad in ("relation; DROP TABLE x", "relation OR 1=1", "", "a.b.c", "1col"):
        with pytest.raises(ValueError):
            identity_relation_sql(bad)


# -- classify_sparql_error(retry_timeouts=) (eidr-wikidata gap 2) -------------

def test_timeouts_retry_only_when_asked():
    for exc in (TimeoutError("read"), OSError("[WinError 10060] did not properly respond"),
                RuntimeError("Read timed out. (read timeout=30)")):
        assert classify_sparql_error(exc) == NEXT_ENDPOINT          # unchanged default
        assert classify_sparql_error(exc, retry_timeouts=True) == RETRY


def test_retry_timeouts_leaves_outage_and_other_verdicts_alone():
    # An outage message that also mentions a timeout is still an outage.
    outage = RuntimeError("Aggressively rate-limiting this client; request timed out")
    assert classify_sparql_error(outage) == OUTAGE
    assert classify_sparql_error(outage, retry_timeouts=True) == OUTAGE
    assert classify_sparql_error(RuntimeError("boom"), retry_timeouts=True) == NEXT_ENDPOINT


# -- external.RequestPacer (eidr-wikidata gap 1, BMR-Review's verifier) ------

class _Clock:
    def __init__(self):
        self.t = 100.0
        self.slept = []

    def now(self):
        return self.t

    def sleep(self, s):
        self.slept.append(round(s, 3))
        self.t += s


def test_pacer_spaces_requests_by_the_minimum_interval():
    c = _Clock()
    p = RequestPacer(clock=c.now, sleep=c.sleep)
    for _ in range(3):
        with p.request():
            c.t += 0.1                      # a fast request
    assert c.slept == [0.2, 0.2]            # 0.3 s spacing minus the 0.1 s each took


def test_pacer_pauses_after_a_slow_request_even_when_it_failed():
    c = _Clock()
    p = RequestPacer(clock=c.now, sleep=c.sleep)
    with pytest.raises(RuntimeError), p.request():
        c.t += 1.5                          # slower than 1 s, then fails
        raise RuntimeError("server error")
    with p.request():
        pass
    assert c.slept == [5.0]                 # the 5 s pause, counted from the end


def test_back_off_extends_but_never_shortens_the_wait():
    c = _Clock()
    p = RequestPacer(clock=c.now, sleep=c.sleep)
    p.back_off(10)
    p.back_off(2)
    p.wait()
    assert c.slept == [10.0]


def test_pacer_needs_a_slot():
    with pytest.raises(ValueError):
        RequestPacer(max_concurrent=0)


# -- ids.CONTENT_ID_SUFFIX (python-sdk) ---------------------------------------

_OLD_ANCHORED = re.compile(r"^10\.5240/[0-9A-F]{4}(?:-[0-9A-F]{4}){4}-[0-9A-Z]$", re.I)
_OLD_SEARCH = re.compile(
    r"(?<![0-9A-Z/])10\.5240/[0-9A-F]{4}(?:-[0-9A-F]{4}){4}-[0-9A-Z](?![0-9A-Z-])", re.I)
_SAMPLES = [
    "10.5240/07A9-90F4-F212-704C-0523-9", "10.5240/07a9-90f4-f212-704c-0523-9",
    "10.5240/07A9-90F4-F212-704C-0523", "10.5240/07A9-90F4-F212-704C-0523-99",
    "10.5240/G7A9-90F4-F212-704C-0523-9", "x 10.5240/7791-8534-2C23-9030-8610-5 y",
    "doi.org/10.5240/7791-8534-2C23-9030-8610-5", "10.5237/9DD9-E249",
]


def test_content_patterns_are_built_from_the_suffix_and_behave_as_before():
    assert re.fullmatch(CONTENT_ID_SUFFIX, "07A9-90F4-F212-704C-0523-9")
    assert re.fullmatch(CONTENT_ID_SUFFIX, "07a9-90f4-f212-704c-0523-9")   # no flag needed
    for s in _SAMPLES:
        assert bool(EIDR_CONTENT_ID_RE.match(s)) == bool(_OLD_ANCHORED.match(s)), s
        assert CONTENT_ID_SEARCH_RE.findall(s) == _OLD_SEARCH.findall(s), s
