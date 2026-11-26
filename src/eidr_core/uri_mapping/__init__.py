"""Alt ID resolvability over ``uri_mapping.json``: does this Alt ID have a page?

eidr-imdb's companion sweep (its R4.2) asks, for the other Alt IDs on a
record whose IMDb mapping is bad, which of them resolve, so the help-desk
ticket can carry a link a person opens. eidr-wikidata already answered that
question for its own Help Desk research report (2026-11-24), so this module
is EXTRACTED from it, not written fresh: eidr-wikidata
``bmr/altid_types.py`` -- ``AltIDTypeResolver._load_uri_mapping`` (how an
entry is read and the "Allow without URL" rule), ``resolution_url``,
``value_strip_prefix`` and ``value_pattern`` -- and the emit order in
``bmr/altidtool.py`` (strip the prefix first, then test the pattern).

THE DATA IS NOT HERE
--------------------
Register R8: ``uri_mapping.json`` is DATA with ONE maintainer, eidr-wikidata
(``data/uri_mapping.json``), and every other program reads it. eidr-core
deliberately carries no copy: a copy that exists to make an outage less
visible goes stale silently (register 2026-09-10, "the number of copies of an
authority should be one"; an eidr-core fallback copy was struck as S-24). So
the caller hands in the entries: from the authority file
(``UriMapping.from_file``), or from the copy the Web UI publishes at
``PUBLISHED_URL`` (``fetch_published``). ``load`` tries a file and falls back
to a fetch ONLY when the caller passes the fetch in: no hidden network.

Two facts about the published copy decide how much it can say:

* it can be unreadable from some machines (R8, 2026-08-27: access
  restrictions on ``ui.eidr.org``), so the fetch is a fallback, never the
  primary source;
* since 2026-11-25 it leaves out every entry with no ``uriTemplate``
  (eidr-wikidata ``scripts/build_published_uri_mapping.py``: the registry's
  LinkedAlternateID view crashed on them). A mapping built from it is
  marked ``complete=False``, and an Alt ID it does not know is reported as
  possibly an "Allow without URL" Kind, not as an unknown one.

WHAT AN ANSWER MEANS
--------------------
``resolvable`` never raises for anything an entry or a value can hold: the
38 "Allow without URL" entries (``ui: false``, no template) give
``url=None`` with ``reason=NO_URL``. ``url`` is set only when the value has
a page of its own; a landing-page template (no ``{0}``: Luminate's login
page, kukla.tv) gives ``url=None`` and names the page in ``detail``.

R8 also forbids the other use: a resolution URL is for a PERSON to open.
It never decides whether two Alt IDs are duplicates (identity is Kind
``(Type, Domain)`` + value, operator 2026-08-10), so do not compare URLs.
"""
from __future__ import annotations

import gzip
import json
import logging
import os
import re
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable, Mapping
from typing import Any, NamedTuple

__all__ = [
    "AUTHORITY_FILENAME",
    "LANDING_PAGE",
    "NO_TEMPLATE",
    "NO_URL",
    "NO_VALUE",
    "PUBLISHED_URL",
    "REASONS",
    "RESOLVES",
    "UNKNOWN_KIND",
    "VALUE_PATTERN",
    "Resolvability",
    "UriMapping",
    "fetch_published",
    "load",
    "load_entries",
]

log = logging.getLogger(__name__)

# The authority's file name (underscore) and the published asset (hyphen).
# The two spellings already differ (R8); both are stated so nobody guesses.
AUTHORITY_FILENAME = "uri_mapping.json"
PUBLISHED_URL = "https://ui.eidr.org/assets/uri-mapping.json"

# Reason codes: stable strings a caller can branch on. ``detail`` carries
# the sentence for a person; these carry the decision.
RESOLVES = "resolves"
NO_URL = "allowed-without-url"       # ui:false and no uriTemplate: approved, no page
LANDING_PAGE = "landing-page-only"   # a template with no {0}: one page for every value
VALUE_PATTERN = "value-pattern-mismatch"
NO_TEMPLATE = "no-template"          # an entry with no template that is NOT ui:false
UNKNOWN_KIND = "unknown-kind"
NO_VALUE = "no-value"
REASONS = frozenset({RESOLVES, NO_URL, LANDING_PAGE, VALUE_PATTERN, NO_TEMPLATE,
                     UNKNOWN_KIND, NO_VALUE})

# Characters left as they are when a value goes into a template. Everything
# an Alt ID value legitimately holds (a DOI's slashes, trakt's "movies/slug",
# a query value) is kept; only spaces, controls and non-ASCII are encoded,
# which a browser would do anyway. eidr-wikidata substituted the raw value.
_SAFE = "/:?#[]@!$&'()*+,;=-._~%"


class Resolvability(NamedTuple):
    """The answer for one Alt ID.

    ``url`` is the value's own page, or None. ``reason`` is one of
    ``REASONS``. ``kind`` is the mapping key that answered (``"IMDB"``,
    ``"themoviedb.org/movie"``), or ``""`` when none did. ``detail`` is a
    sentence fit for a help-desk ticket (it names no local path).
    """

    url: str | None
    reason: str
    kind: str
    detail: str


def _kind_key(alt_type: str | None, domain: str | None) -> str:
    """The mapping key for an Alt ID: the named type, or for a Proprietary
    one its domain. Named-type entries carry ``altIdType`` and no domain
    (IMDB, ISAN, DOI, ...), Proprietary ones ``altIdDomain``."""
    t = (alt_type or "").strip()
    if t and t.casefold() != "proprietary":
        return t
    return (domain or "").strip()


def _preferred(entries: list[Mapping[str, Any]]) -> Mapping[str, Any]:
    """The entry whose template a person should open, among several for one
    key. Several entries for a key are alternate formats of ONE Kind
    (wikidata.org x5, dfi.dk/movie x3, one per mediaType). eidr-wikidata kept
    the FIRST template, which for dfi.dk/movie is the JSON API; a person
    wants the HTML page, so: ``ui: true`` with ``text/html``, then any
    ``ui: true``, then any with a template, then the first."""
    def score(e: Mapping[str, Any]) -> int:
        has_t = bool(str(e.get("uriTemplate") or "").strip())
        ui = e.get("ui", True) is not False
        html = str(e.get("mediaType") or "").strip().lower() == "text/html"
        return ((4 if has_t and ui and html else 0) + (2 if has_t and ui else 0)
                + (1 if has_t else 0))
    return max(entries, key=score)   # max keeps the first of equal scores


class UriMapping:
    """``uri_mapping.json`` entries indexed for ``resolvable``.

    ``entries`` is the parsed file: a list of entry objects, or the older
    ``{domain: entry}`` object form, which eidr-wikidata's loader also
    accepts. ``complete`` is False for the published copy, which omits the
    "Allow without URL" entries. ``source`` names where the entries came
    from, for ``detail`` and logs. Read-only once built, so one instance can
    serve a whole run and several threads.
    """

    def __init__(self, entries: Iterable[Mapping[str, Any]] | Mapping[str, Any], *,
                 complete: bool = True, source: str = "") -> None:
        if isinstance(entries, Mapping):
            # The object form keys each entry by its domain (eidr-wikidata
            # ``_load_uri_mapping``).
            entries = [{"altIdDomain": k, **v} for k, v in entries.items()
                       if isinstance(v, Mapping)]
        self.complete = complete
        self.source = source
        self._by_key: dict[str, list[Mapping[str, Any]]] = {}
        self._patterns: dict[str, re.Pattern[str] | None] = {}
        for e in entries:
            if not isinstance(e, Mapping):
                continue
            # A named type is indexed by its type name, a Proprietary Kind
            # by its domain. eidr-wikidata indexed templates by domain only,
            # so ``resolution_url("IMDB", ...)`` found nothing: the
            # named-type entries carry no altIdDomain.
            for key in {str(e.get("altIdType") or "").strip(),
                        str(e.get("altIdDomain") or "").strip()}:
                if key:
                    self._by_key.setdefault(key.casefold(), []).append(e)

    def __len__(self) -> int:
        return len(self._by_key)

    @classmethod
    def from_file(cls, path: str | os.PathLike[str]) -> UriMapping:
        """Read the authority file (or any copy of it) from disk."""
        return cls(load_entries(path), complete=True, source=os.fspath(path))

    def _pattern(self, key: str, entry: Mapping[str, Any]) -> re.Pattern[str] | None:
        """The compiled ``valuePattern`` for a key, or None. An invalid
        pattern is logged and ignored, as eidr-wikidata does: one bad entry
        must not disable the mapping, or make an answer raise."""
        if key not in self._patterns:
            raw = str(entry.get("valuePattern") or "").strip()
            compiled: re.Pattern[str] | None = None
            if raw:
                try:
                    compiled = re.compile(raw)
                except re.error as exc:
                    log.warning("uri_mapping entry %r: invalid valuePattern %r (%s); ignored",
                                key, raw, exc)
            self._patterns[key] = compiled
        return self._patterns[key]

    def resolvable(self, alt_type: str | None, domain: str | None,
                   value: str | None) -> Resolvability:
        """Whether this Alt ID has a page of its own, and its URL.

        ``alt_type`` is the registry's Alt ID type (``IMDB``, ``ISAN``,
        ``Proprietary``); ``domain`` is read for a Proprietary one (and when
        ``alt_type`` is empty). Keys match case-insensitively, as
        eidr-wikidata's loader does. The entry's ``valueStripPrefix`` is
        removed from the value first and ``valuePattern`` tested after, the
        order eidr-wikidata emits in. Never raises.
        """
        key = _kind_key(alt_type, domain)
        v = str(value if value is not None else "").strip()
        if not key:
            return Resolvability(None, UNKNOWN_KIND, "",
                                 "no Alt ID type, and no domain for a Proprietary one")
        found = self._by_key.get(key.casefold())
        if not found:
            if self.complete:
                # Not ``self.source``: a local path does not belong in a
                # help-desk ticket.
                why = f"{key!r} has no entry in uri_mapping.json"
            else:
                why = (f"{key!r} is not in the published copy, which leaves out the "
                       "Allow-without-URL Kinds; it is unknown or allowed without a URL")
            return Resolvability(None, UNKNOWN_KIND, "", why)
        entry = _preferred(found)
        kind = str(entry.get("altIdType") or entry.get("altIdDomain") or key).strip()
        if not v:
            return Resolvability(None, NO_VALUE, kind, "the Alt ID has no value")
        template = str(entry.get("uriTemplate") or "").strip()
        if not template:
            if entry.get("ui", True) is False:
                return Resolvability(None, NO_URL, kind,
                                     f"{kind} is approved without a URL (no public page)")
            # eidr-wikidata does not approve this shape: a template-less
            # entry that is not ui:false is malformed or legacy.
            return Resolvability(None, NO_TEMPLATE, kind,
                                 f"{kind} has an entry with no uriTemplate and is not "
                                 "marked ui:false")
        prefix = str(entry.get("valueStripPrefix") or "")
        if prefix and v.startswith(prefix):
            v = v[len(prefix):]
        pattern = self._pattern(key.casefold(), entry)
        if pattern is not None and not pattern.search(v):
            return Resolvability(None, VALUE_PATTERN, kind,
                                 f"value {v!r} does not match {kind}'s valuePattern "
                                 f"{pattern.pattern!r}, so it is not a valid {kind} value")
        if "{0}" not in template:
            return Resolvability(None, LANDING_PAGE, kind,
                                 f"{kind} has no page per value; its link is the landing "
                                 f"page {template}")
        url = template.replace("{0}", urllib.parse.quote(v, safe=_SAFE))
        return Resolvability(url, RESOLVES, kind, f"{kind} resolves to {url}")


def load_entries(path: str | os.PathLike[str]) -> list[dict] | dict:
    """The parsed JSON of a mapping file (list, or the older object form).
    Raises ``OSError`` or ``ValueError`` on an unreadable file or bad JSON:
    a caller asking for the authority must hear that it did not get it."""
    with open(path, encoding="utf-8-sig") as fh:
        data = json.load(fh)
    if not isinstance(data, (list, dict)):
        raise ValueError(f"{os.fspath(path)}: a uri mapping is a JSON list or object")
    return data


def fetch_published(*, url: str = PUBLISHED_URL, user_agent: str | None = None,
                    timeout: float = 30.0,
                    opener: Callable[..., Any] | None = None) -> UriMapping:
    """Fetch the copy the Web UI publishes and index it (``complete=False``).

    One request, no retries: this is a fallback, and a caller wanting
    retries wraps it in ``call_with_failover``. ``opener`` defaults to
    ``urllib.request.urlopen`` looked up at call time, so a test that patches
    it, or passes its own, reaches it. Raises what the transport raises, or
    ``ValueError`` on a body that is not a mapping.
    """
    headers = {"Accept": "application/json", "Accept-Encoding": "gzip"}
    if user_agent:
        headers["User-Agent"] = user_agent
    open_url = opener if opener is not None else urllib.request.urlopen
    req = urllib.request.Request(url, headers=headers)
    with open_url(req, timeout=timeout) as resp:
        raw = resp.read()
        enc = (resp.headers.get("Content-Encoding") or "").strip().lower()
    if enc in ("gzip", "x-gzip"):
        raw = gzip.decompress(raw)
    data = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(data, (list, dict)):
        raise ValueError(f"{url}: a uri mapping is a JSON list or object")
    return UriMapping(data, complete=False, source=url)


def load(path: str | os.PathLike[str] | None, *,
         fetch_fallback: Callable[[], UriMapping] | None = None) -> UriMapping:
    """The authority from ``path``; the published copy only if asked for.

    eidr-imdb's stated order ("``uri_mapping.json`` via eidr-core, falling
    back to ``ui.eidr.org``"): read ``path``; when it is None, missing or
    unreadable, call ``fetch_fallback`` (pass ``fetch_published``, or a
    ``functools.partial`` of it with your User-Agent and opener). Without a
    fallback the file's error is raised: nothing is fetched behind the
    caller's back.
    """
    if path is not None:
        try:
            return UriMapping.from_file(path)
        except (OSError, ValueError) as exc:
            if fetch_fallback is None:
                raise
            log.warning("uri mapping %s unreadable (%s); fetching the published copy",
                        os.fspath(path), exc)
    if fetch_fallback is None:
        raise FileNotFoundError("no uri_mapping.json path, and no fetch_fallback")
    return fetch_fallback()
