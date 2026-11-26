"""external.tmdb (C8, TMDb): the failures that pass silently -- an API key
written into a log line, a 401 taken for "not found", a transient status
taken for an answer, a cast cut to four before matching, a field outside the
allow-list handed on. HTTP is mocked throughout; no real secrets are read."""
from __future__ import annotations

import gzip
import io
import json
import logging
import urllib.error

import pytest

from eidr_core.external import RequestPacer
from eidr_core.external import tmdb as T

UA = "eidr-test/1.0 (https://eidr.org)"


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr("eidr_core.external.failover.time.sleep", lambda s: None)


class Resp:
    def __init__(self, body, *, gz=False, status=200):
        raw = json.dumps(body).encode()
        self._raw = gzip.compress(raw) if gz else raw
        self.status = status
        self.headers = {"Content-Encoding": "gzip"} if gz else {}

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


def _http(code, body=None, retry_after=None):
    hdrs = {"Retry-After": retry_after} if retry_after is not None else {}
    raw = json.dumps(body).encode() if body is not None else b""
    return urllib.error.HTTPError("u", code, "x", hdrs, io.BytesIO(raw))


def _client(*answers, creds=None, pacer=None):
    op = Opener(*answers)
    c = T.TmdbClient(creds or T.TmdbCredentials(bearer_token="tok"), user_agent=UA,
                     pacer=pacer or Pacer(), opener=op)
    return c, op


# -- credentials and construction --------------------------------------------

def test_credentials_environment_first_then_the_secrets_section():
    secrets = {"tmdb": {"bearer_token": "from-file"}}
    assert T.credentials_from_secrets(secrets, environ={}).bearer_token == "from-file"
    env = {"TMDB_API_KEY": "from-env"}
    got = T.credentials_from_secrets(secrets, environ=env)
    assert (got.bearer_token, got.api_key) == (None, "from-env")
    assert not T.credentials_from_secrets({}, environ={})
    assert not T.credentials_from_secrets(None, environ={})
    assert not T.credentials_from_secrets({"tmdb": "garbage"}, environ={})


def test_credentials_never_show_in_a_repr():
    c = T.TmdbCredentials(bearer_token="SECRET-TOKEN", api_key="SECRET-KEY")
    assert "SECRET" not in repr(c) and "bearer_token" in repr(c)


def test_a_client_needs_credentials_and_a_caller_user_agent():
    with pytest.raises(ValueError):
        T.TmdbClient(T.TmdbCredentials(), user_agent=UA, pacer=Pacer())
    with pytest.raises(ValueError):
        T.TmdbClient(T.TmdbCredentials(api_key="k"), user_agent=" ", pacer=Pacer())


def test_the_pacer_is_on_the_machine_wide_scope(tmp_path):
    p = T.tmdb_pacer(scope_dir=str(tmp_path))
    assert p.shared_scope == T.TMDB_SCOPE == "tmdb-api"
    assert p.min_interval == 0.3 and p.slow_pause == 0.0


# -- transport ----------------------------------------------------------------

def test_headers_bearer_gzip_and_the_callers_user_agent():
    c, op = _client(Resp({"id": 1, "title": "X"}, gz=True))
    assert c.facts("movie", "1")["status"] == "found"
    req = op.requests[0]
    assert req.get_header("User-agent") == UA
    assert req.get_header("Accept-encoding") == "gzip"
    assert req.get_header("Authorization") == "Bearer tok"
    assert "api_key" not in req.full_url


def test_an_api_key_goes_in_the_url_but_never_in_a_log_line(caplog):
    c, op = _client(_http(503), Resp({"id": 1}), creds=T.TmdbCredentials(api_key="SECRETKEY"))
    with caplog.at_level(logging.DEBUG):
        assert c.facts("movie", "1")["status"] == "found"
    assert all("api_key=SECRETKEY" in r.full_url for r in op.requests)
    assert op.requests[0].get_header("Authorization") is None
    assert caplog.records, "the retry should have logged"
    assert "SECRETKEY" not in caplog.text


def test_a_transient_status_is_retried_once_and_then_is_the_answer():
    c, op = _client(_http(503), _http(429, {"status_code": 25}))
    got = c.facts("movie", "1")
    assert got == {"status": "error", "facts": {}, "error": "HTTP 429"}
    assert len(op.requests) == 2


def test_a_transport_error_twice_is_an_error_string_not_an_exception():
    c, _op = _client(TimeoutError("t1"), ConnectionResetError("boom"))
    got = c.facts("tv", "5")
    assert got["status"] == "error" and got["error"] == "ConnectionResetError: boom"


def test_a_final_status_is_never_retried_and_404_is_not_found():
    c, op = _client(_http(404), Resp({"never": 1}))
    assert c.facts("movie", "1") == {"status": "not_found", "facts": {}}
    assert len(op.requests) == 1


def test_401_raises_rather_than_reading_as_not_found():
    c, _op = _client(_http(401, {"status_code": 7}))
    with pytest.raises(T.TmdbAuthError):
        c.find_imdb("tt0133093")


def test_retry_after_makes_the_next_request_wait():
    p = Pacer()
    c, _op = _client(_http(429, retry_after="3"), Resp({"id": 1}), pacer=p)
    c.facts("movie", "1")
    assert p.backed == [3.0]


def test_the_default_opener_is_looked_up_at_call_time(monkeypatch):
    op = Opener(Resp({"id": 1}))
    monkeypatch.setattr("urllib.request.urlopen", op)
    c = T.TmdbClient(T.TmdbCredentials(bearer_token="t"), user_agent=UA, pacer=Pacer())
    assert c.facts("movie", "1")["status"] == "found" and len(op.requests) == 1


# -- find ---------------------------------------------------------------------

def test_find_by_imdb_id_gives_eidr_dqs_shape_and_the_alt_id_kinds():
    body = {"movie_results": [{"id": 603}], "tv_results": [],
            "tv_episode_results": [{"show_id": 1399, "season_number": 1, "episode_number": 2}]}
    c, op = _client(Resp(body))
    got = c.find_imdb(" TT0133093 ")
    assert got == {"status": "found",
                   "resolved": [("tmdb_movie", "603"), ("tmdb_episode", "1399:1:2")],
                   "alt_ids": [("themoviedb.org/movie", "603")]}
    assert "/find/tt0133093?" in op.requests[0].full_url
    assert "external_source=imdb_id" in op.requests[0].full_url


def test_find_rejects_a_bad_id_without_a_request_and_empty_results_are_not_found():
    c, op = _client(Resp({"movie_results": [], "tv_results": []}))
    assert c.find_imdb("nm0000206")["status"] == "error" and not op.requests
    assert c.find_imdb("tt1") == {"status": "not_found", "resolved": [], "alt_ids": []}


# -- facts (eidr-dq parity) ---------------------------------------------------

def test_facts_movie_tv_and_episode():
    movie = {"title": "The Matrix", "runtime": 136, "release_date": "1999-03-30",
             "imdb_id": "tt0133093", "external_ids": {"wikidata_id": "Q83495"},
             "overview": "never returned"}
    tv = {"name": "Game of Thrones", "episode_run_time": [60, 55, 60],
          "first_air_date": "2011-04-17", "last_air_date": "2019-05-19"}
    ep = {"name": "The Kingsroad", "runtime": 56, "air_date": "2011-04-24"}
    c, op = _client(Resp(movie), Resp(tv), Resp(ep))
    assert c.facts("movie", "603")["facts"] == {
        "label": "The Matrix", "external_ids": {"imdb": "tt0133093", "wikidata": "Q83495"},
        "runtime_minutes": [136.0], "release_date": "1999-03-30",
        "release_date_precision": "day"}
    assert c.facts("tv", "1399")["facts"] == {
        "label": "Game of Thrones", "episode_runtime_minutes": [55.0, 60.0],
        "release_date": "2011-04-17", "release_date_precision": "day",
        "last_air_date": "2019-05-19"}
    assert c.facts("episode", "1399:1:2")["facts"] == {
        "label": "The Kingsroad", "runtime_minutes": [56.0],
        "release_date": "2011-04-24", "release_date_precision": "day"}
    assert "append_to_response=external_ids" in op.requests[0].full_url
    assert op.requests[2].full_url.endswith("/tv/1399/season/1/episode/2")


def test_bad_kind_or_id_is_an_error_without_a_request():
    c, op = _client()
    assert c.facts("person", "1")["status"] == "error"
    assert c.credits("movie", "abc")["status"] == "error"
    assert c.bmr_facts("episode", "1399:1")["status"] == "error"
    assert not op.requests


# -- credits: complete, directors and actors only -----------------------------

def test_movie_credits_are_the_whole_cast_in_billing_order_and_directors_only():
    cast = [{"name": f"Actor {i}", "order": i} for i in range(9, -1, -1)]
    cast.append({"name": "Actor 3", "order": 11})            # a second role
    crew = [{"name": "Lana Wachowski", "job": "Director"},
            {"name": "Lilly Wachowski", "job": "Director"},
            {"name": "Joel Silver", "job": "Producer"}]
    c, op = _client(Resp({"cast": cast, "crew": crew}))
    got = c.credits("movie", "603")
    assert got["directors"] == ["Lana Wachowski", "Lilly Wachowski"]
    assert got["actors"] == [f"Actor {i}" for i in range(10)]      # NOT cut to 4
    assert set(got) == {"status", "directors", "actors"}
    assert op.requests[0].full_url.endswith("/movie/603/credits")


def test_series_credits_use_aggregate_credits_most_episodes_first():
    crew = [{"name": "Once", "jobs": [{"job": "Director", "episode_count": 1}]},
            {"name": "Writer", "jobs": [{"job": "Writer", "episode_count": 9}]},
            {"name": "Often", "jobs": [{"job": "Director", "episode_count": 6},
                                       {"job": "Producer", "episode_count": 3}]}]
    cast = [{"name": "Lead", "order": 0}, {"name": "Second", "order": 1}]
    c, op = _client(Resp({"cast": cast, "crew": crew}))
    got = c.credits("tv", "1399")
    assert got["directors"] == ["Often", "Once"] and got["actors"] == ["Lead", "Second"]
    assert op.requests[0].full_url.endswith("/tv/1399/aggregate_credits")


def test_episode_credits_add_guest_stars_after_the_regular_cast():
    c, _op = _client(Resp({"cast": [{"name": "Regular", "order": 0}],
                           "guest_stars": [{"name": "Guest", "order": 0}],
                           "crew": [{"name": "Tim Van Patten", "job": "Director"}]}))
    got = c.credits("episode", "1399:1:2")
    assert got["actors"] == ["Regular", "Guest"] and got["directors"] == ["Tim Van Patten"]


# -- bmr_facts ----------------------------------------------------------------

_BMR_KEYS = {"Title", "Title Language", "Alternate Title", "Release Date", "End Date",
             "Approx Length", "Original Language", "Country of Origin", "Director",
             "Actor", "Associated Org"}


def test_bmr_facts_movie_keys_values_and_nothing_off_the_allow_list():
    body = {"original_title": "Le Samouraï", "title": "Le Samouraï", "original_language": "fr",
            "release_date": "1967-10-25", "runtime": 105.4, "origin_country": ["FR", "IT"],
            "production_companies": [{"name": "Filmel"}, {"name": "CICC"}],
            "overview": "a synopsis", "vote_average": 8.0, "budget": 1, "genres": [{"name": "x"}],
            "credits": {"cast": [{"name": f"A{i}", "order": i} for i in range(6)],
                        "crew": [{"name": "Jean-Pierre Melville", "job": "Director"},
                                 {"name": "Henri Decaë", "job": "Director of Photography"}]}}
    c, op = _client(Resp(body))
    got = c.bmr_facts("movie", "5511")
    f = got["facts"]
    assert got["status"] == "found" and set(f) == _BMR_KEYS
    assert f["Title"] == "Le Samouraï" and f["Title Language"] == "fr"
    assert f["Alternate Title"] == []                      # same as the original
    assert f["Approx Length"] == 105 and f["End Date"] == ""
    assert f["Country of Origin"] == ["FR", "IT"] and f["Original Language"] == ["fr"]
    assert f["Director"] == ["Jean-Pierre Melville"] and len(f["Actor"]) == 6
    assert f["Associated Org"] == ["Filmel", "CICC"]
    assert "a synopsis" not in json.dumps(got, ensure_ascii=False)
    url = op.requests[0].full_url
    assert "append_to_response=credits" in url and "language=en-US" in url


def test_bmr_facts_series_end_date_country_fallback_and_no_language():
    body = {"original_name": "Деревня", "name": "The Village", "original_language": "xx",
            "first_air_date": "1990-01-01", "last_air_date": "1991-06-01", "status": "Ended",
            "episode_run_time": [45], "production_countries": [{"iso_3166_1": "SU"}],
            "aggregate_credits": {"cast": [{"name": "Lead", "order": 0}], "crew": []}}
    c, op = _client(Resp(body))
    f = c.bmr_facts("tv", "77")["facts"]
    assert f["Title"] == "Деревня" and f["Title Language"] == "zxx"
    assert f["Alternate Title"] == [("The Village", "en")]
    assert f["End Date"] == "1991-06-01" and f["Approx Length"] is None
    assert f["Country of Origin"] == ["SUHH"] and f["Original Language"] == ["zxx"]
    assert "append_to_response=aggregate_credits" in op.requests[0].full_url


def test_bmr_facts_a_running_series_has_no_end_date_and_an_episode_no_title_language():
    c, _op = _client(Resp({"name": "S", "original_name": "S", "status": "Returning Series",
                           "last_air_date": "2026-01-01"}),
                     Resp({"name": "Pilot", "air_date": "2020-01-01", "runtime": 50}))
    assert c.bmr_facts("tv", "1")["facts"]["End Date"] == ""
    ep = c.bmr_facts("episode", "1:1:1")["facts"]
    assert (ep["Title"], ep["Title Language"], ep["Approx Length"]) == ("Pilot", "", 50)
    assert ep["Original Language"] == []
