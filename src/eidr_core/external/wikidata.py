"""A Wikidata entity read into BMR template fields (reconciliation C8, part 2).

Operator, 2026-10-18: the mapped fields are the BMR templates' own columns
(Episodic and Non-Episodic), so ``bmr_facts`` keys its answer by Template-22
header (``Title``, ``Release Date``, ``Director``, ...). And: "When populating
data for BMR, cut off after the first 4 actors (or 2 directors). When
evaluating for a match (or when voting among sites on the most correct
answer), fetch all available data, since a full cast list dramatically
increases the accuracy of a match using 4 or fewer actors in an eidr record."
So ``bmr_facts`` returns EVERY director and actor; ``bmr_rows.cap_credits``
cuts them for a sheet (the EIDR API takes at most 4 actors), and a matcher
against the mirror uses the full lists.

Extracted from eidr-wikidata ``wikidata/api.py`` (``_pick_date_with_source``,
``_release_date_is_estimate``, ``_duration_minutes``, ``_title_and_lang``,
``_alt_titles``, the claim readers), with the rules eidr-metadata-sources'
integration package (2026-10-17) sets for the shared client:

* deprecated-rank statements are never used, from any property, and
  preferred rank comes before normal (eidr-wikidata read most properties
  regardless of rank);
* Release Date by the tiers: P577 general, then territory-specific (P291)
  only as an estimate, P580, P571 inception (an estimate), with the P580
  exception: on a Series or Season it is the first broadcast, not an
  estimate (``RD:Pro;`` goes on estimates);
* P2441 (literal translation) is never an Alternate Title. Labels and
  aliases are, as eidr-wikidata uses them, until the operator rules on
  their examples (OD-47);
* each statement's references (P248 stated in, P143 imported from) are
  readable (``references``), so a caller can tell a value Wikidata took from
  IMDb from an independent one (OD-31).

Pure: no network. Fetch entities with ``external.wikimedia.action_api_json``
(``wbgetentities``), then the related items (people, companies, language and
country items) the same way, and pass them in as ``related``.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any, NamedTuple

from eidr_core.codes import normalize_country_code

__all__ = [
    "P_CAST_MEMBER",
    "P_COUNTRY_OF_ORIGIN",
    "P_DIRECTOR",
    "P_DURATION",
    "P_IMPORTED_FROM",
    "P_INCEPTION",
    "P_LANGUAGE_OF_WORK",
    "P_ORIGINAL_LANGUAGE",
    "P_ORIGINAL_TITLE",
    "P_PLACE_OF_PUB",
    "P_PRODUCTION_COMPANY",
    "P_PUBLICATION_DATE",
    "P_STATED_IN",
    "P_START_TIME",
    "ReleaseDate",
    "alternate_titles",
    "bmr_facts",
    "claims",
    "duration_minutes",
    "item_ids",
    "label",
    "references",
    "release_date",
    "title",
]

P_ORIGINAL_TITLE = "P1476"
P_PUBLICATION_DATE = "P577"
P_START_TIME = "P580"
P_INCEPTION = "P571"
P_PLACE_OF_PUB = "P291"
P_DURATION = "P2047"
P_ORIGINAL_LANGUAGE = "P364"
P_LANGUAGE_OF_WORK = "P407"
P_COUNTRY_OF_ORIGIN = "P495"
P_DIRECTOR = "P57"
P_CAST_MEMBER = "P161"
P_PRODUCTION_COMPANY = "P272"
P_STATED_IN = "P248"
P_IMPORTED_FROM = "P143"
_P_ISO639_1 = "P218"
_P_WIKIMEDIA_LANG = "P424"
_P_ISO3166_1 = "P297"

_UNITS = {"Q7727": 1.0, "Q11574": 1 / 60.0, "Q25235": 60.0}   # minute, second, hour
_PUNCT_RE = re.compile(r"[\W_]+", re.UNICODE)


def _get(d: Any, *path: str) -> Any:
    for p in path:
        if not isinstance(d, dict) or p not in d:
            return None
        d = d[p]
    return d


def claims(entity: Mapping[str, Any], prop: str, *,
           include_deprecated: bool = False) -> list[dict]:
    """The property's statements: deprecated rank dropped (unless asked
    for), preferred before normal, then statement order."""
    out = [c for c in ((entity.get("claims") or {}).get(prop) or [])
           if include_deprecated or c.get("rank") != "deprecated"]
    return sorted(out, key=lambda c: c.get("rank") != "preferred")


def _value(claim: dict) -> dict | None:
    dv = _get(claim, "mainsnak", "datavalue")
    return dv if isinstance(dv, dict) else None


def item_ids(entity: Mapping[str, Any], prop: str) -> list[str]:
    """The item IDs (QIDs) a property names, by rank, de-duplicated."""
    out: list[str] = []
    for c in claims(entity, prop):
        dv = _value(c)
        if dv and dv.get("type") == "wikibase-entityid":
            q = (dv.get("value") or {}).get("id")
            if q and q not in out:
                out.append(q)
    return out


def references(claim: Mapping[str, Any]) -> list[tuple[str, str]]:
    """``(property, item)`` for each P248 (stated in) and P143 (imported
    from) in the statement's references: where Wikidata says it got the
    value. An IMDb-sourced value is not an independent vote (OD-31)."""
    out: list[tuple[str, str]] = []
    for ref in claim.get("references") or []:
        for prop in (P_STATED_IN, P_IMPORTED_FROM):
            for snak in (ref.get("snaks") or {}).get(prop) or []:
                q = _get(snak, "datavalue", "value", "id")
                if q:
                    out.append((prop, q))
    return out


def label(entity: Mapping[str, Any] | None, lang: str = "en") -> str:
    """The entity's label in ``lang``, or ""."""
    return (_get(entity, "labels", lang, "value") or "") if entity else ""


def _lang2(lang: str | None) -> str:
    if not lang:
        return "und"
    primary = str(lang).strip().lower().split("-", 1)[0]
    if primary == "zh" or (len(primary) == 2 and primary.isalpha()):
        return primary
    return "und"


def _parse_time(time_str: str, precision: int | None) -> str:
    m = re.match(r"^[+-]?(\d{1,4})-(\d{2})-(\d{2})T", time_str or "")
    if not m:
        return ""
    year, month, day = m.groups()
    if month == "00" or day == "00" or (precision is not None and int(precision) < 11):
        return year
    return f"{year}-{month}-{day}"


class ReleaseDate(NamedTuple):
    """``date`` (YYYY or YYYY-MM-DD, "" for none); ``estimate``: it must
    carry ``RD:Pro;``; ``source``: the property, ``+P291`` when the date was
    territory-specific."""

    date: str
    estimate: bool
    source: str


def release_date(entity: Mapping[str, Any], referent_type: str = "") -> ReleaseDate:
    """The Release Date by the tiers (P577, then P580, then P571; within a
    property, general statements before territory-specific ones, preferred
    before normal; deprecated never), and whether it is an estimate."""
    for prop in (P_PUBLICATION_DATE, P_START_TIME, P_INCEPTION):
        stmts = claims(entity, prop)
        general = [c for c in stmts if not (c.get("qualifiers") or {}).get(P_PLACE_OF_PUB)]
        territorial = [c for c in stmts if (c.get("qualifiers") or {}).get(P_PLACE_OF_PUB)]
        for tier, source in ((general, prop), (territorial, f"{prop}+{P_PLACE_OF_PUB}")):
            for c in tier:
                dv = _value(c)
                if not dv or dv.get("type") != "time":
                    continue
                v = dv.get("value") or {}
                date = _parse_time(v.get("time", ""), v.get("precision"))
                if date:
                    return ReleaseDate(date, _is_estimate(source, referent_type), source)
    return ReleaseDate("", False, "")


def _is_estimate(source: str, referent_type: str) -> bool:
    if source.endswith("+" + P_PLACE_OF_PUB) or source == P_INCEPTION:
        return True
    if source == P_START_TIME:
        # The P580 exception (operator, 2026-10-11): Wikidata models a
        # Series' or Season's first broadcast as its start time.
        return referent_type not in ("Series", "Season")
    return False


def duration_minutes(entity: Mapping[str, Any]) -> int | None:
    """Approx Length in minutes from P2047 (minutes, seconds or hours)."""
    for c in claims(entity, P_DURATION):
        dv = _value(c)
        if not dv or dv.get("type") != "quantity":
            continue
        v = dv.get("value") or {}
        factor = _UNITS.get((v.get("unit") or "").rsplit("/", 1)[-1])
        try:
            amount = float(v.get("amount") or 0)
        except (TypeError, ValueError):
            continue
        if factor is not None:
            return int(round(amount * factor))
    return None


def title(entity: Mapping[str, Any]) -> tuple[str, str]:
    """``(Title, Title Language)``: P1476, else the English label; the
    language as two letters (``und`` when there is none)."""
    for c in claims(entity, P_ORIGINAL_TITLE):
        dv = _value(c)
        if dv and dv.get("type") == "monolingualtext":
            v = dv.get("value") or {}
            if v.get("text"):
                return v["text"], _lang2(v.get("language"))
    lbl = label(entity)
    return lbl, ("en" if lbl else "und")


def _norm(s: str) -> str:
    return _PUNCT_RE.sub("", (s or "").strip().lower())


def alternate_titles(entity: Mapping[str, Any], primary: str = "") -> list[tuple[str, str]]:
    """``(Alternate Title, Alt Title Language)`` from aliases then labels,
    de-duplicated (punctuation and case folded) against each other and the
    primary title. Never P2441 (a literal translation is not a title the
    work was released under). Whether labels and aliases are release titles
    at all is with the operator (OD-47)."""
    found: list[tuple[str, str]] = []
    for lang_key, arr in (entity.get("aliases") or {}).items():
        for a in arr or []:
            if (a or {}).get("value"):
                found.append((a["value"], _lang2(lang_key)))
    for lang_key, obj in (entity.get("labels") or {}).items():
        if (obj or {}).get("value"):
            found.append((obj["value"], _lang2(lang_key)))
    seen = {_norm(primary)} if primary else set()
    out: list[tuple[str, str]] = []
    for text, lang in found:
        k = _norm(text)
        if k and k not in seen:
            seen.add(k)
            out.append((text, lang or "und"))
    return out


def _codes(related: Mapping[str, Any], qids: Iterable[str], *props: str) -> list[str]:
    out: list[str] = []
    for q in qids:
        ent = related.get(q) or {}
        for prop in props:
            vals = [_value(c) for c in claims(ent, prop)]
            code = next((dv.get("value") for dv in vals
                         if dv and dv.get("type") in ("string", "external-id")), None)
            if code:
                if code not in out:
                    out.append(code)
                break
    return out


def bmr_facts(entity: Mapping[str, Any], related: Mapping[str, Any] | None = None, *,
              referent_type: str = "") -> dict[str, Any]:
    """The entity as BMR template fields, keyed by Template-22 header.

    ``related`` holds the fetched entities the statements point at (people,
    companies, language and country items). Lists are complete: every
    director and actor, for matching; ``bmr_rows.cap_credits`` cuts them for
    a sheet. Language codes are the items' ISO 639-1 (else Wikimedia) codes,
    unvalidated: pass them through ``bmr_rows.original_languages`` and the
    language authority. Country codes are normalised (SU -> SUHH).
    ``Registrant Extra`` carries ``RD:Pro;`` for an estimated date.
    """
    rel = related or {}
    main, main_lang = title(entity)
    rd = release_date(entity, referent_type)
    lang_ids = item_ids(entity, P_ORIGINAL_LANGUAGE)
    if not lang_ids and not any(_get(c, "mainsnak", "snaktype") == "novalue"
                                for c in claims(entity, P_ORIGINAL_LANGUAGE)):
        lang_ids = item_ids(entity, P_LANGUAGE_OF_WORK)
    countries = [normalize_country_code(c) for c in
                 _codes(rel, item_ids(entity, P_COUNTRY_OF_ORIGIN), _P_ISO3166_1)]

    def names(prop: str) -> list[str]:
        return [n for n in (label(rel.get(q)) for q in item_ids(entity, prop)) if n]

    return {
        "Title": main,
        "Title Language": main_lang if main else "",
        "Alternate Title": alternate_titles(entity, main),
        "Release Date": rd.date,
        "Registrant Extra": "RD:Pro;" if rd.estimate else "",
        "Approx Length": duration_minutes(entity),
        "Original Language": _codes(rel, lang_ids, _P_ISO639_1, _P_WIKIMEDIA_LANG),
        "Country of Origin": [c for c in countries if c],
        "Director": names(P_DIRECTOR),
        "Actor": names(P_CAST_MEMBER),
        "Associated Org": names(P_PRODUCTION_COMPANY),
    }
