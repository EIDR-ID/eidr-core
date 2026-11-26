"""A TMDb v3 client on the external chassis (reconciliation C8, TMDb).

TMDb reached its second consumer: eidr-dq and BMR-Review use it today, and
eidr-imdb needs it for Phase 5 (handoff 2026-11-24 section 4). Its access is
settled: PERMISSION-GRANTED through membership (eidr-metadata-sources OD-59),
integration complete (OD-72, 2026-11-25), rank 8 among sources (OD-54).
The membership covers the data, so no attribution line is owed beyond the
Alt ID that links each record back to TMDb (OD-20b; the catalog's "attribution
required" note was superseded by OD-59). No integration package followed,
so the shape below is the one the two existing clients already ran.

Extracted, not written fresh:

* the transport, the status handling and the fact dicts from eidr-dq
  ``src/dq/external/tmdb.py`` (``_fetch_with_retry``, ``_get_json``,
  ``_read_body``, ``fetch_find``, ``fetch_one``, ``_facts_from_movie`` /
  ``_tv`` / ``_episode``, ``_external_ids``, ``_load_credentials``), which
  already ran on ``call_with_failover`` and sent a contact User-Agent and
  ``Accept-Encoding: gzip`` (operator, 2026-11-24);
* the credit reading from BMR-Review ``eidr_dedup_score/verify.py``
  ``TmdbVerifier._meta_from``: directors are the crew whose job is
  ``Director``, and the cast is kept WHOLE.

What changed on the way, and why:

* **The User-Agent is the caller's.** eidr-dq's carried eidr-dq's contact;
  a shared library must not put any program's (or person's) address on
  another program's requests, so ``user_agent`` is required. Build it with
  ``eidr_core.external.wikimedia.user_agent(program, version, contact)``.
* **Credentials are passed in.** eidr-dq read the environment and its own
  secrets file inside the module. Here ``credentials_from_secrets`` reads a
  secrets mapping the caller already loaded (``eidr_core.secrets_loader``),
  with the same section and keys as the portfolio's skeleton
  (``"tmdb": {"bearer_token": ...}`` or ``{"api_key": ...}``) and the same
  environment overrides, so no test ever needs a real secrets file.
* **The API key never reaches a log.** ``call_with_failover`` logs the
  endpoint it was given; eidr-dq gave it the URL with ``api_key=`` in it.
  Here the chassis sees the URL without the key, and the key is added
  inside the attempt. A v4 bearer token travels in a header, never a URL.
* **One pace for the machine.** TMDb limits by IP address, so every EIDR
  program on a machine shares ``tmdb_pacer`` (scope ``TMDB_SCOPE``, 0.3 s
  between requests: eidr-dq's 300 ms default, two orders of magnitude under
  TMDb's posted ~50 a second). eidr-dq slept in its own loop instead.
* **Only allow-listed fields come back** (eidr-metadata-sources OD-14b: a
  shared client returns only what the allow-list lets EIDR retain). Credits
  are directors and actors only, never writers, producers or other crew;
  ``bmr_facts`` keys its answer by Template-22 header like
  ``external.wikidata.bmr_facts``. The lists are complete, for matching and
  voting (OD-62); ``bmr_rows.cap_credits`` cuts them for a sheet.

Every method returns a status envelope, never raises for one bad ID: the
fact-dict contract of ``eidr_core.external`` (``"found"`` / ``"not_found"``
/ ``"error"``). The exception is HTTP 401, ``TmdbAuthError``, so a caller can
switch the source off for the run with a clear message.
"""
from __future__ import annotations

import gzip
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from eidr_core.codes import normalize_country_code
from eidr_core.external.failover import (
    RETRY,
    RequestPacer,
    call_with_failover,
    retry_after_seconds,
)

__all__ = [
    "ALT_ID_DOMAINS",
    "ENV_API_KEY",
    "ENV_BEARER_TOKEN",
    "KINDS",
    "SECRETS_SECTION",
    "TMDB_API",
    "TMDB_MIN_INTERVAL",
    "TMDB_SCOPE",
    "TmdbAuthError",
    "TmdbClient",
    "TmdbCredentials",
    "credentials_from_secrets",
    "tmdb_pacer",
]

TMDB_API = "https://api.themoviedb.org/3"
# The machine-wide pacer scope every EIDR TMDb client uses: TMDb counts
# requests per IP address, so two programs on one machine are one client.
TMDB_SCOPE = "tmdb-api"
TMDB_MIN_INTERVAL = 0.3

# eidr-dq's credential names: the secrets section and keys of the portfolio
# skeleton (eidr-imdb's sample.secrets.json carries the same block), and the
# environment variables that override it.
SECRETS_SECTION = "tmdb"
ENV_BEARER_TOKEN = "TMDB_BEARER_TOKEN"
ENV_API_KEY = "TMDB_API_KEY"

# What the client fetches. An episode's id is the composite
# "show:season:episode" that ``find_imdb`` returns, because TMDb addresses an
# episode through its show.
KINDS = ("movie", "tv", "episode")

# The registry's Alt ID Kinds for a TMDb id found through ``find_imdb``
# (uri_mapping.json: themoviedb.org/movie and /tv resolve to
# www.themoviedb.org/<kind>/<id>). No episode Kind: the composite id is not
# what the themoviedb.org/tv/episode template expects.
ALT_ID_DOMAINS = {"movie": "themoviedb.org/movie", "tv": "themoviedb.org/tv"}

_TRANSIENT_STATUSES = frozenset({429, 500, 502, 503, 504})
_AUTH_MESSAGE = ("TMDb returned 401 (invalid or missing credentials); check the "
                 "tmdb section of the secrets, or TMDB_BEARER_TOKEN / TMDB_API_KEY")
# TMDb's code for "no language"; the allow-list's is zxx.
_NO_LANGUAGE = {"xx": "zxx"}
_ENDED = frozenset({"Ended", "Canceled", "Cancelled"})


class TmdbAuthError(RuntimeError):
    """HTTP 401: the credentials are missing, wrong or revoked."""


@dataclass(frozen=True, repr=False)
class TmdbCredentials:
    """A v4 read-access token (sent as a Bearer header, preferred) and/or a
    v3 API key (sent as ``api_key``). False when both are empty. The repr
    never shows either value, so a credentials object in a log line or a
    traceback leaks nothing."""

    bearer_token: str | None = None
    api_key: str | None = None

    def __bool__(self) -> bool:
        return bool(self.bearer_token or self.api_key)

    def __repr__(self) -> str:
        has = [n for n, v in (("bearer_token", self.bearer_token),
                              ("api_key", self.api_key)) if v]
        return f"TmdbCredentials({', '.join(has) or 'empty'})"


def credentials_from_secrets(secrets: Mapping[str, Any] | None, *,
                             environ: Mapping[str, str] | None = None) -> TmdbCredentials:
    """TMDb credentials from a loaded secrets mapping, environment first.

    eidr-dq's order: ``TMDB_BEARER_TOKEN`` or ``TMDB_API_KEY`` in the
    environment win; otherwise the ``tmdb`` section's ``bearer_token`` and
    ``api_key``. ``secrets`` is what ``eidr_core.secrets_loader.load_secrets``
    (or a consumer's wrapper) returned; this function opens no file.
    ``environ`` defaults to ``os.environ``; tests pass a dict.
    """
    env = os.environ if environ is None else environ
    bearer = (env.get(ENV_BEARER_TOKEN) or "").strip() or None
    key = (env.get(ENV_API_KEY) or "").strip() or None
    if bearer or key:
        return TmdbCredentials(bearer, key)
    block = (secrets or {}).get(SECRETS_SECTION) if isinstance(secrets, Mapping) else None
    if not isinstance(block, Mapping):
        return TmdbCredentials()
    return TmdbCredentials(str(block.get("bearer_token") or "").strip() or None,
                           str(block.get("api_key") or "").strip() or None)


def tmdb_pacer(min_interval: float = TMDB_MIN_INTERVAL, *,
               scope_dir: str | None = None) -> RequestPacer:
    """A pacer on the machine-wide TMDb scope: one request in flight across
    every EIDR program, ``min_interval`` seconds apart. No slow-request
    pause: that is a Wikimedia rule, not TMDb's."""
    return RequestPacer(max(0.0, float(min_interval)), slow_pause=0.0, max_concurrent=1,
                        shared_scope=TMDB_SCOPE, scope_dir=scope_dir)


class _Transient(Exception):
    """A status worth another try (429, 5xx), raised INSIDE the attempt so
    ``call_with_failover`` retries it; every other status is a final answer
    and is returned. ``status`` and ``retry_after`` are the attributes the
    chassis reads (``http_status``, ``retry_after_seconds``)."""

    def __init__(self, status: int, body: dict, retry_after: float | None) -> None:
        super().__init__(f"HTTP {status}")
        self.status, self.body, self.retry_after = status, body, retry_after


def _classify(exc: Exception) -> str:
    # The transient statuses and anything the transport raises (timeout,
    # reset, DNS) get the retry; nothing is fatal here, because a wrong
    # answer from TMDb is reported to the caller, never inferred (eidr-dq).
    return RETRY


def _read_body(resp: Any) -> bytes:
    """The body, gunzipped when the server compressed it (urllib does not
    decode Content-Encoding itself)."""
    raw = resp.read()
    headers = getattr(resp, "headers", None)
    enc = (headers.get("Content-Encoding") or "").strip().lower() if headers is not None else ""
    return gzip.decompress(raw) if enc in ("gzip", "x-gzip") else raw


def _json_or_empty(resp: Any) -> dict:
    try:
        data = json.loads(_read_body(resp).decode("utf-8"))
    except Exception:          # an error page that is not JSON: no body
        return {}
    return data if isinstance(data, dict) else {}


def _dedupe(names: Iterable[Any]) -> list[str]:
    """Names in order, blanks and repeats dropped (one actor in two roles
    appears twice in a cast list)."""
    out: list[str] = []
    seen: set[str] = set()
    for n in names:
        s = str(n or "").strip()
        if s and s.casefold() not in seen:
            seen.add(s.casefold())
            out.append(s)
    return out


def _by_order(people: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Billing order: TMDb's ``order`` field when present, else as listed
    (``sorted`` is stable, so ties and missing orders keep their place)."""
    rows = [p for p in people if isinstance(p, Mapping)]
    return sorted(rows, key=lambda p: p["order"] if isinstance(p.get("order"), int) else 10**9)


def _credits_from(obj: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    """``(directors, actors)`` from a credits object, complete.

    Three shapes: ``/movie/{id}/credits`` and an episode's credits (crew rows
    carry ``job``), and ``/tv/{id}/aggregate_credits`` (crew rows carry a
    ``jobs`` list with ``episode_count``). For a series every episode's
    director counts, most episodes first, so ``cap_credits`` keeps the
    series' principal directors. An episode's guest stars follow its regular
    cast. Every other crew job is left out (allow-list: never taken).
    """
    directors: list[tuple[int, int, str]] = []
    for idx, c in enumerate(obj.get("crew") or []):
        if not isinstance(c, Mapping) or not c.get("name"):
            continue
        if c.get("job") == "Director":
            directors.append((0, idx, c["name"]))
            continue
        directed = [j for j in (c.get("jobs") or [])
                    if isinstance(j, Mapping) and j.get("job") == "Director"]
        if directed:
            eps = sum(int(j.get("episode_count") or 0) for j in directed)
            directors.append((-eps, idx, c["name"]))
    cast = _by_order(obj.get("cast") or []) + _by_order(obj.get("guest_stars") or [])
    return (_dedupe(n for _e, _i, n in sorted(directors)),
            _dedupe(p.get("name") for p in cast))


def _external_ids(body: Mapping[str, Any]) -> dict:
    """Cross-references TMDb states about a work, under our source names
    (eidr-dq). They arrive free with ``append_to_response=external_ids``; a
    movie also carries ``imdb_id`` at the top level. TMDb began filling
    ``wikidata_id`` only in late 2022, so the IMDb id is the better bridge."""
    xi = body.get("external_ids") or {}
    out: dict = {}
    imdb = str(xi.get("imdb_id") or body.get("imdb_id") or "").strip().lower()
    if imdb.startswith("tt") and imdb[2:].isdigit():
        out["imdb"] = imdb
    wd = str(xi.get("wikidata_id") or "").strip()
    if wd.startswith("Q") and wd[1:].isdigit():
        out["wikidata"] = wd
    return out


def _facts(kind: str, body: Mapping[str, Any]) -> dict:
    """The fact dict ``eidr_core.verify`` reads (eidr-dq's three readers,
    merged: they differed only in which field holds the label, the date and
    the runtime)."""
    facts: dict = {}
    label = body.get("title") if kind == "movie" else body.get("name")
    if label:
        facts["label"] = label
    xrefs = _external_ids(body)
    if xrefs:
        facts["external_ids"] = xrefs
    if kind == "tv":
        run_times = [float(x) for x in (body.get("episode_run_time") or [])
                     if isinstance(x, (int, float)) and x > 0]
        if run_times:
            facts["episode_runtime_minutes"] = sorted(set(run_times))[:8]
    else:
        rt = body.get("runtime")
        if isinstance(rt, (int, float)) and rt > 0:
            facts["runtime_minutes"] = [float(rt)]
    date_field = {"movie": "release_date", "tv": "first_air_date", "episode": "air_date"}[kind]
    rd = str(body.get(date_field) or "").strip()
    if rd:
        facts["release_date"] = rd
        facts["release_date_precision"] = "day"
    if kind == "tv":
        lad = str(body.get("last_air_date") or "").strip()
        if lad:
            facts["last_air_date"] = lad
    return facts


def _lang(code: Any) -> str:
    c = str(code or "").strip().lower()
    return _NO_LANGUAGE.get(c, c)


def _bmr_facts(kind: str, body: Mapping[str, Any], credits: Mapping[str, Any]) -> dict[str, Any]:
    """TMDb's answer as BMR template fields, keyed by Template-22 header,
    with the same keys and value shapes as ``external.wikidata.bmr_facts``
    plus ``End Date``.

    Title is the original-language title (``original_title`` /
    ``original_name``) with ``original_language``; the English title, when it
    differs, is an Alternate Title (requested as ``en-US``). An episode has
    no original-language title in TMDb, so its name is the Title with no
    language. Approx Length is a movie's or an episode's runtime; a series
    has none (``episode_run_time`` is per episode). End Date only for a
    series TMDb marks ended or cancelled. Country of Origin from
    ``origin_country``, else the production countries.
    """
    if kind == "episode":
        main, main_lang = str(body.get("name") or ""), ""
        alts: list[tuple[str, str]] = []
    else:
        orig_key, en_key = (("original_title", "title") if kind == "movie"
                            else ("original_name", "name"))
        main = str(body.get(orig_key) or body.get(en_key) or "")
        main_lang = _lang(body.get("original_language")) if main else ""
        en = str(body.get(en_key) or "")
        alts = [(en, "en")] if en and en.casefold() != main.casefold() else []
    date_field = {"movie": "release_date", "tv": "first_air_date", "episode": "air_date"}[kind]
    rt = body.get("runtime") if kind != "tv" else None
    countries = [str(c) for c in (body.get("origin_country") or []) if c]
    if not countries:
        countries = [str(c.get("iso_3166_1")) for c in (body.get("production_countries") or [])
                     if isinstance(c, Mapping) and c.get("iso_3166_1")]
    end = (str(body.get("last_air_date") or "")
           if kind == "tv" and body.get("status") in _ENDED else "")
    directors, actors = _credits_from(credits)
    lang = _lang(body.get("original_language")) if kind != "episode" else ""
    return {
        "Title": main,
        "Title Language": main_lang,
        "Alternate Title": alts,
        "Release Date": str(body.get(date_field) or "").strip(),
        "End Date": end.strip(),
        "Approx Length": int(round(rt)) if isinstance(rt, (int, float)) and rt > 0 else None,
        "Original Language": [lang] if lang else [],
        "Country of Origin": _dedupe(normalize_country_code(c) for c in countries),
        "Director": directors,
        "Actor": actors,
        "Associated Org": _dedupe(c.get("name") for c in (body.get("production_companies") or [])
                                  if isinstance(c, Mapping)),
    }


def _path(kind: str, tmdb_id: str) -> tuple[str | None, str | None]:
    """``(path, error)`` for a kind and id (eidr-dq ``fetch_one``'s checks)."""
    tid = str(tmdb_id or "").strip()
    if kind == "episode":
        parts = tid.split(":")
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            return None, f"bad episode id: {tmdb_id!r}"
        return f"tv/{parts[0]}/season/{parts[1]}/episode/{parts[2]}", None
    if kind in ("movie", "tv"):
        if not tid.isdigit():
            return None, f"non-numeric TMDb id: {tmdb_id!r}"
        return f"{kind}/{tid}", None
    return None, f"bad kind: {kind!r}"


class TmdbClient:
    """TMDb v3, read-only: find by IMDb id, facts, credits, BMR fields.

    ``credentials`` from ``credentials_from_secrets`` (ValueError when
    empty: build the client only when there are credentials). ``user_agent``
    is required and names the CALLING program and its contact. ``pacer``
    defaults to ``tmdb_pacer()``, shared machine-wide. ``attempts`` and
    ``backoff`` are eidr-dq's budget: two tries about 2 s apart. ``opener``
    defaults to ``urllib.request.urlopen`` looked up at call time, so a test
    that patches it, or passes its own, reaches it.
    """

    def __init__(self, credentials: TmdbCredentials, *, user_agent: str,
                 pacer: RequestPacer | None = None, base_url: str = TMDB_API,
                 timeout: float = 20.0, attempts: int = 2, backoff: float = 1.0,
                 opener: Callable[..., Any] | None = None) -> None:
        if not credentials:
            raise ValueError("TmdbClient needs a bearer_token (v4) or an api_key (v3)")
        if not (user_agent or "").strip():
            raise ValueError("TmdbClient needs a user_agent naming the calling program "
                             "and a contact (eidr_core.external.wikimedia.user_agent)")
        self._creds = credentials
        self._ua = user_agent.strip()
        self._pacer = pacer if pacer is not None else tmdb_pacer()
        self._base = base_url.rstrip("/")
        self._timeout = timeout
        self._attempts = max(1, int(attempts))
        self._backoff = backoff
        self._opener = opener

    # -- transport -----------------------------------------------------------

    def _get(self, path: str, params: Mapping[str, str] | None = None
             ) -> tuple[int, dict, str | None]:
        """``(status, body, error)``: one GET through ``call_with_failover``.

        ``error`` is set only when the transport failed on every try; a
        transient status that outlasts the retries comes back as the status
        (eidr-dq's contract). The chassis is handed the URL WITHOUT the api
        key, because it logs the endpoint; the key is added per attempt.
        """
        query = dict(params or {})
        public_url = f"{self._base}/{path}"
        if query:
            public_url += "?" + urllib.parse.urlencode(query)
        headers = {"Accept": "application/json", "Accept-Encoding": "gzip",
                   "User-Agent": self._ua}
        if self._creds.bearer_token:
            headers["Authorization"] = f"Bearer {self._creds.bearer_token}"
        open_url = self._opener if self._opener is not None else urllib.request.urlopen

        def attempt(url: str) -> tuple[int, dict]:
            if not self._creds.bearer_token and self._creds.api_key:
                url += ("&" if "?" in url else "?") + urllib.parse.urlencode(
                    {"api_key": self._creds.api_key})
            req = urllib.request.Request(url, headers=headers)
            try:
                with self._pacer.request(), open_url(req, timeout=self._timeout) as resp:
                    return int(getattr(resp, "status", 200) or 200), _json_or_empty(resp)
            except urllib.error.HTTPError as e:
                body = _json_or_empty(e)
                if e.code in _TRANSIENT_STATUSES:
                    wait = retry_after_seconds(e)
                    if wait:
                        # The NEXT request waits too, whichever program sends it.
                        self._pacer.back_off(wait)
                    raise _Transient(e.code, body, wait) from None
                return e.code, body

        result, _used, last = call_with_failover(
            [public_url], attempt, _classify, max_retries=self._attempts,
            backoff=self._backoff, jitter=0.25, op_label="tmdb")
        if result is not None:
            return result[0], result[1], None
        if isinstance(last, _Transient):
            return last.status, last.body, None
        return 0, {}, f"{type(last).__name__}: {last}"

    def _answer(self, path: str, params: Mapping[str, str] | None = None
                ) -> tuple[str, dict, str | None]:
        """``(status word, body, error)``; raises ``TmdbAuthError`` on 401."""
        status, body, err = self._get(path, params)
        if err is not None:
            return "error", {}, err
        if status == 401:
            raise TmdbAuthError(_AUTH_MESSAGE)
        if status == 404:
            return "not_found", {}, None
        if status != 200:
            return "error", {}, f"HTTP {status}"
        return "found", body, None

    # -- the API -------------------------------------------------------------

    def find_imdb(self, imdb_id: str) -> dict:
        """TMDb's identities for an IMDb id, through ``/find``.

        The tt id is used only as a foreign key; everything returned is
        TMDb's own data. ``{"status", "resolved": [(kind, id), ...],
        "alt_ids": [(domain, value), ...]}`` (plus ``"error"``): ``resolved``
        as eidr-dq returned it, kinds ``tmdb_movie``, ``tmdb_tv`` and
        ``tmdb_episode`` (composite ``"show:season:episode"``), one per kind;
        ``alt_ids`` the registry Kinds a movie or series id goes in
        (``ALT_ID_DOMAINS``; OD-52: a resolvable identifier may be linked).
        """
        tt = str(imdb_id or "").strip().lower()
        if not tt.startswith("tt") or not tt[2:].isdigit():
            return {"status": "error", "resolved": [], "alt_ids": [],
                    "error": f"bad IMDb id: {imdb_id!r}"}
        word, body, err = self._answer(f"find/{tt}", {"external_source": "imdb_id"})
        if word != "found":
            out: dict = {"status": word, "resolved": [], "alt_ids": []}
            if err:
                out["error"] = err
            return out
        resolved: list[tuple[str, str]] = []
        alt_ids: list[tuple[str, str]] = []
        for key, kind in (("movie_results", "movie"), ("tv_results", "tv")):
            hits = body.get(key) or []
            if hits and isinstance(hits[0], Mapping) and hits[0].get("id") is not None:
                tid = str(hits[0]["id"])
                resolved.append((f"tmdb_{kind}", tid))
                alt_ids.append((ALT_ID_DOMAINS[kind], tid))
        ep = body.get("tv_episode_results") or []
        if ep and isinstance(ep[0], Mapping):
            show, season, num = (ep[0].get("show_id"), ep[0].get("season_number"),
                                 ep[0].get("episode_number"))
            if all(isinstance(x, int) for x in (show, season, num)):
                resolved.append(("tmdb_episode", f"{show}:{season}:{num}"))
        if not resolved:
            return {"status": "not_found", "resolved": [], "alt_ids": []}
        return {"status": "found", "resolved": resolved, "alt_ids": alt_ids}

    def facts(self, kind: str, tmdb_id: str) -> dict:
        """One record as a fact dict (``eidr_core.external`` contract):
        ``label``, ``runtime_minutes`` or ``episode_runtime_minutes``,
        ``release_date`` (day precision), a series' ``last_air_date``, and
        ``external_ids`` (``imdb``, ``wikidata``). eidr-dq ``fetch_one``."""
        path, bad = _path(kind, tmdb_id)
        if path is None:
            return {"status": "error", "facts": {}, "error": bad}
        # append_to_response rides in the SAME request: TMDb counts one call.
        params = {"append_to_response": "external_ids"} if kind != "episode" else None
        word, body, err = self._answer(path, params)
        if word != "found":
            return {"status": word, "facts": {}, **({"error": err} if err else {})}
        return {"status": "found", "facts": _facts(kind, body)}

    def credits(self, kind: str, tmdb_id: str) -> dict:
        """Every director and every actor, in billing order, for matching:
        ``{"status", "directors": [...], "actors": [...]}``. A series reads
        ``aggregate_credits`` (every season, not only the latest); an
        episode adds its guest stars. Cut for a sheet with
        ``bmr_rows.cap_credits``."""
        path, bad = _path(kind, tmdb_id)
        if path is None:
            return {"status": "error", "directors": [], "actors": [], "error": bad}
        sub = "aggregate_credits" if kind == "tv" else "credits"
        word, body, err = self._answer(f"{path}/{sub}")
        if word != "found":
            return {"status": word, "directors": [], "actors": [],
                    **({"error": err} if err else {})}
        directors, actors = _credits_from(body)
        return {"status": "found", "directors": directors, "actors": actors}

    def bmr_facts(self, kind: str, tmdb_id: str) -> dict:
        """The record as BMR template fields, in one request:
        ``{"status", "facts": {Template-22 header: value}}`` with the keys
        of ``external.wikidata.bmr_facts`` plus ``End Date``. Lists are
        complete (every director and actor); ``bmr_rows.cap_credits`` cuts
        them for a sheet."""
        path, bad = _path(kind, tmdb_id)
        if path is None:
            return {"status": "error", "facts": {}, "error": bad}
        sub = "aggregate_credits" if kind == "tv" else "credits"
        word, body, err = self._answer(path, {"append_to_response": sub, "language": "en-US"})
        if word != "found":
            return {"status": word, "facts": {}, **({"error": err} if err else {})}
        return {"status": "found", "facts": _bmr_facts(kind, body, body.get(sub) or {})}
