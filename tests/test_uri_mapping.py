"""uri_mapping.resolvable: the wrong answers that read as right -- a named
type that finds no template, an Allow-without-URL Kind that raises, a JSON
API offered to a person, a value the Kind rejects given a link anyway, an
unknown Kind in the published copy reported as certainly unknown. Offline:
the published copy is fetched through an injected opener."""
from __future__ import annotations

import gzip
import json

import pytest

from eidr_core import uri_mapping as U

# The entry shapes of eidr-wikidata's data/uri_mapping.json (2026-11-26).
ENTRIES = [
    {"name": "IMDb", "ui": True, "mediaType": "text/html",
     "uriTemplate": "https://www.imdb.com/title/{0}", "altIdType": "IMDB"},
    {"name": "IMDB", "altIdDomain": "imdb.com", "ui": True, "mediaType": "text/html",
     "uriTemplate": "https://www.imdb.com/title/{0}"},
    {"name": "The Movie DB", "altIdDomain": "themoviedb.org/movie", "ui": True,
     "mediaType": "text/html", "uriTemplate": "https://www.themoviedb.org/movie/{0}"},
    {"name": "DFI (JSON API)", "altIdDomain": "dfi.dk/movie", "ui": False,
     "mediaType": "application/json",
     "uriTemplate": "https://nationalfilmografien.service.dfi.dk/movie.svc/json/{0}"},
    {"name": "DFI", "altIdDomain": "dfi.dk/movie", "ui": True, "mediaType": "text/html",
     "uriTemplate": "https://www.dfi.dk/viden-om-film/filmdatabasen/film/{0}"},
    {"name": "AllGame", "altIdDomain": "allgame.com", "ui": False, "mediaType": "text/html"},
    {"name": "Armenian Cinema ID", "altIdDomain": "arm-cinema.am", "ui": False,
     "relation": "Deprecated"},
    {"name": "Legacy", "altIdDomain": "legacy.example", "ui": True},
    {"name": "Luminate Season", "altIdDomain": "luminatedata.com/SeasonID", "ui": False,
     "mediaType": "text/html", "uriTemplate": "https://filmandtv.luminatedata.com/login.php"},
    {"name": "iTunes", "altIdDomain": "itunes.apple.com", "ui": True, "mediaType": "text/html",
     "uriTemplate": "https://itunes.apple.com/movie/{0}", "valuePattern": "^id"},
    {"name": "Trakt (shows)", "altIdDomain": "trakt.tv/shows", "ui": True,
     "mediaType": "text/html", "uriTemplate": "https://app.trakt.tv/shows/{0}",
     "valueStripPrefix": "shows/"},
    {"name": "Broken", "altIdDomain": "broken.example", "ui": True,
     "uriTemplate": "https://broken.example/{0}", "valuePattern": "(["},
    {"name": "DOI", "ui": True, "uriTemplate": "https://doi.org/{0}", "altIdType": "DOI",
     "mediaType": "text/html"},
]


@pytest.fixture
def m():
    return U.UriMapping(ENTRIES)


def test_a_named_type_resolves_by_its_type_name(m):
    # eidr-wikidata's resolution_url indexed templates by domain only, so
    # IMDB (no altIdDomain) came back "".
    r = m.resolvable("IMDB", None, "tt0133093")
    assert r == U.Resolvability("https://www.imdb.com/title/tt0133093", U.RESOLVES, "IMDB",
                                "IMDB resolves to https://www.imdb.com/title/tt0133093")
    assert m.resolvable("imdb", "", "tt1").url == "https://www.imdb.com/title/tt1"


def test_a_proprietary_kind_resolves_by_its_domain_case_insensitively(m):
    r = m.resolvable("Proprietary", "TheMovieDB.org/movie", " 603 ")
    assert (r.url, r.kind) == ("https://www.themoviedb.org/movie/603", "themoviedb.org/movie")
    assert m.resolvable("", "imdb.com", "tt1").reason == U.RESOLVES


def test_a_person_gets_the_html_page_not_the_api(m):
    assert m.resolvable("Proprietary", "dfi.dk/movie", "123").url == \
        "https://www.dfi.dk/viden-om-film/filmdatabasen/film/123"


def test_allow_without_url_is_url_none_with_a_reason_never_an_exception(m):
    for domain in ("allgame.com", "arm-cinema.am"):
        r = m.resolvable("Proprietary", domain, "42")
        assert r.url is None and r.reason == U.NO_URL and r.kind == domain


def test_a_template_less_entry_not_marked_ui_false_is_not_approved(m):
    r = m.resolvable("Proprietary", "legacy.example", "1")
    assert r.url is None and r.reason == U.NO_TEMPLATE


def test_a_landing_page_is_not_a_page_for_the_value(m):
    r = m.resolvable("Proprietary", "luminatedata.com/seasonid", "9")
    assert r.url is None and r.reason == U.LANDING_PAGE and "login.php" in r.detail


def test_value_pattern_and_strip_prefix_in_eidr_wikidatas_order(m):
    bad = m.resolvable("Proprietary", "itunes.apple.com", "505147674")
    assert bad.url is None and bad.reason == U.VALUE_PATTERN
    assert m.resolvable("Proprietary", "itunes.apple.com", "id1596624032").reason == U.RESOLVES
    assert m.resolvable("Proprietary", "trakt.tv/shows", "shows/the-wire").url == \
        "https://app.trakt.tv/shows/the-wire"
    assert m.resolvable("Proprietary", "trakt.tv/shows", "the-wire").url == \
        "https://app.trakt.tv/shows/the-wire"


def test_an_invalid_value_pattern_is_ignored_not_raised(m):
    assert m.resolvable("Proprietary", "broken.example", "x").reason == U.RESOLVES


def test_unknown_kind_and_missing_parts(m):
    assert m.resolvable("Proprietary", "nope.example", "1").reason == U.UNKNOWN_KIND
    assert m.resolvable("Proprietary", None, "1").reason == U.UNKNOWN_KIND
    assert m.resolvable(None, None, None).reason == U.UNKNOWN_KIND
    r = m.resolvable("IMDB", None, "  ")
    assert r.reason == U.NO_VALUE and r.url is None


def test_values_keep_their_slashes_and_only_unsafe_characters_are_encoded(m):
    assert m.resolvable("DOI", None, "10.5240/7791-8534").url == "https://doi.org/10.5240/7791-8534"
    assert m.resolvable("Proprietary", "themoviedb.org/movie", "a b").url.endswith("/a%20b")


def test_every_entry_shape_answers_without_raising_and_every_reason_is_known(m):
    for e in ENTRIES:
        for value in ("x", "", None, "id1"):
            r = m.resolvable(e.get("altIdType") or "Proprietary", e.get("altIdDomain"), value)
            assert r.reason in U.REASONS
            assert (r.url is not None) == (r.reason == U.RESOLVES)


def test_the_object_form_is_read_too():
    m = U.UriMapping({"themoviedb.org/tv": {"ui": True, "uriTemplate": "https://t/{0}"}})
    assert m.resolvable("Proprietary", "themoviedb.org/tv", "1").url == "https://t/1"


# -- loading: a file, and the published copy only when asked -------------------

class Resp:
    def __init__(self, body, *, gz=False):
        raw = json.dumps(body).encode()
        self._raw = gzip.compress(raw) if gz else raw
        self.headers = {"Content-Encoding": "gzip"} if gz else {}

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_load_reads_the_file_and_never_fetches_when_it_is_there(tmp_path):
    p = tmp_path / U.AUTHORITY_FILENAME
    p.write_text(json.dumps(ENTRIES), encoding="utf-8")

    def fetch():
        raise AssertionError("fetched although the file was readable")
    m = U.load(p, fetch_fallback=fetch)
    assert m.complete and m.resolvable("IMDB", None, "tt1").reason == U.RESOLVES


def test_load_without_a_fallback_raises_the_files_error(tmp_path):
    with pytest.raises(OSError):
        U.load(tmp_path / "missing.json")
    with pytest.raises(FileNotFoundError):
        U.load(None)


def test_the_fallback_is_the_published_copy_and_it_says_it_is_incomplete(tmp_path):
    seen = []

    def opener(req, timeout):
        seen.append(req)
        return Resp([e for e in ENTRIES if e.get("uriTemplate")], gz=True)

    m = U.load(tmp_path / "missing.json",
               fetch_fallback=lambda: U.fetch_published(user_agent="t/1 (https://eidr.org)",
                                                        opener=opener))
    assert seen[0].full_url == U.PUBLISHED_URL == "https://ui.eidr.org/assets/uri-mapping.json"
    assert seen[0].get_header("User-agent") == "t/1 (https://eidr.org)"
    assert not m.complete
    r = m.resolvable("Proprietary", "allgame.com", "1")
    assert r.reason == U.UNKNOWN_KIND and "published copy" in r.detail
    assert m.resolvable("IMDB", None, "tt1").reason == U.RESOLVES


def test_fetch_published_rejects_a_body_that_is_not_a_mapping():
    with pytest.raises(ValueError):
        U.fetch_published(opener=lambda req, timeout: Resp("not a mapping"))
