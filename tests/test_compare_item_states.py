"""Per-item states (S-41; operator 2026-11-24, option (a)), extracted from
BMR-Review's ``item_states.py`` into ``eidr_core.compare.states``.

A wrong item state is SILENT: a glyph that is plausibly green or grey beside
a list entry. So, as for ``inheritance``, where two code paths must agree they
are tested against each other: the item states against the comparator's own
outcome for the same records (``test_items_agree_with_the_comparator``), over
every record pair in the golden corpus. The two fixtures that declare an
``item_states`` invariant are reproduced exactly; the rules De-Dupe UI's first
request read differently are pinned in both directions.

The record view the states align to is BMR-Review's ``render_record``. Its
list rules are mirrored in ``_view`` below for the keys the states read (the
casefold sort, the sort name as its own entry, an organization's alternate
names after it, the shared title and Alt ID display orders); BMR-Review's own
suite covers the real view.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from importlib.resources import files
from types import SimpleNamespace

import pytest

pytest.importorskip("rapidfuzz")

from eidr_core.compare import (  # noqa: E402
    COMPARATORS,
    _params,
    cmp_alt_ids,
    cmp_titles,
    set_params,
)
from eidr_core.compare.spec import load_spec  # noqa: E402
from eidr_core.compare.states import band, field_item_states, field_states  # noqa: E402
from eidr_core.ordering import altid_display_key, is_shortdoi, title_sort_key  # noqa: E402

# --- a minimal record model and fixture loader --------------------------------


@dataclass
class _Title:
    text: str
    lang: str | None = None
    title_class: str | None = None
    system_generated: bool = False
    is_resource: bool = False


@dataclass
class _Rec:
    creation_type: str = "Basic"
    release_date: str | None = None
    date_estimated: bool = False
    titles: list = field(default_factory=list)
    directors: list = field(default_factory=list)
    actors: list = field(default_factory=list)
    countries: list = field(default_factory=list)
    original_languages: list = field(default_factory=list)
    version_languages: list = field(default_factory=list)
    assoc_orgs: list = field(default_factory=list)
    alt_ids: list = field(default_factory=list)


def _name(n):
    if isinstance(n, str):
        return SimpleNamespace(display=n, sort_name=None)
    return SimpleNamespace(display=n["display"], sort_name=n.get("sort_name"))


def _org(o):
    if isinstance(o, str):
        return SimpleNamespace(name=o, party_id=None, alt_names=[])
    return SimpleNamespace(name=o.get("name"), party_id=o.get("party_id"),
                           alt_names=list(o.get("alt_names") or []))


def _code(c):
    return SimpleNamespace(code=c if isinstance(c, str) else c["code"])


def _build(d):
    """The list fields of a golden-pair record (golden-pairs.md section 2)."""
    titles = []
    for t in d.get("titles") or []:
        if isinstance(t, str):
            titles.append(_Title(t))
        else:
            titles.append(_Title(t["text"], t.get("lang"), t.get("title_class"),
                                 bool(t.get("system_generated")), bool(t.get("is_resource"))))
    return _Rec(
        creation_type=d.get("creation_type") or "Basic",
        release_date=d.get("release_date"),
        date_estimated=bool(d.get("date_estimated")),
        titles=titles,
        directors=[_name(n) for n in d.get("directors") or []],
        actors=[_name(n) for n in d.get("actors") or []],
        countries=[_code(c) for c in d.get("countries") or []],
        original_languages=[_code(c) for c in d.get("original_languages") or []],
        version_languages=[_code(c) for c in d.get("version_languages") or []],
        assoc_orgs=[_org(o) for o in d.get("assoc_orgs") or []],
        alt_ids=[SimpleNamespace(value=a["value"], id_type=a.get("id_type"),
                                 domain=a.get("domain"), relation=a.get("relation"))
                 for a in d.get("alt_ids") or []],
    )


def _ck(x):
    return str(x if x is not None else "").casefold()


def _view(rec):
    """The list part of BMR-Review's ``render_record`` (see the module note)."""
    credits = []
    for lst in (rec.directors, rec.actors):
        out = []
        for n in lst:
            if n.display:
                out.append([n.display, True])
            sn = (n.sort_name or "").strip()
            if sn and sn != (n.display or "").strip():
                out.append([sn, True])
        out.sort(key=lambda p: _ck(p[0]))
        credits.append(out)
    orgs, seen = [], set()
    for o in sorted(rec.assoc_orgs, key=lambda o: _ck(o.name or o.party_id)):
        for n in [o.name or o.party_id] + sorted([a for a in o.alt_names if a], key=_ck):
            if _ck(n) not in seen:
                seen.add(_ck(n))
                orgs.append([n, True])

    def codes(lst, dedup=False):
        items, keys = [], set()
        for c in lst:
            if c.code and not (dedup and _ck(c.code) in keys):
                keys.add(_ck(c.code))
                items.append([c.code, True])
        return sorted(items, key=lambda p: _ck(p[0]))

    titles = sorted([t for t in rec.titles if t.text],
                    key=lambda t: title_sort_key(t.text, t.title_class, t.is_resource))
    alts = sorted([a for a in rec.alt_ids if not is_shortdoi(a.id_type, a.domain)],
                  key=lambda a: altid_display_key(a.id_type, a.domain, a.value))
    return {
        "titles": [[t.text] for t in titles],
        "directors": credits[0],
        "actors": credits[1],
        "countries": codes(rec.countries),
        "languages": codes(rec.original_languages, dedup=True),
        "version_languages": codes(rec.version_languages, dedup=True),
        "assoc_orgs": orgs,
        "alt_ids": [[a.value, a.id_type, a.domain, a.relation] for a in alts],
    }


_LIST_FIELDS = ("title", "director", "actor", "country", "original_language",
                "version_language", "assoc_org")


def _rationale(sub, cand):
    """The comparators' rows for the list fields: what the engine compared."""
    rows = []
    for f in _LIST_FIELDS:
        r = COMPARATORS[f](sub, cand)
        rows.append({"field": f, "quality": r.quality, "applicable": r.quality is not None})
    r = cmp_alt_ids(sub, cand)
    rows.append({"field": "alt_id", "quality": r.quality, "applicable": r.quality is not None})
    return rows


@pytest.fixture(autouse=True)
def _spec_params():
    before = _params.get_source()
    set_params(SimpleNamespace(**load_spec()))
    yield
    set_params(before)


def _bands():
    return load_spec()["STATE_BANDS"]


def _states(sub, cand, ct="Basic"):
    view = _view(cand)
    return field_item_states(_rationale(sub, cand), sub, cand, view, _bands(), ct), view


def _corpus():
    root = files("eidr_core") / "specs" / "golden_pairs"
    for p in sorted(root.iterdir(), key=lambda p: p.name):
        if p.name.endswith(".json"):
            yield json.loads(p.read_text(encoding="utf-8"))


def _record_pairs():
    for fx in _corpus():
        mode = fx.get("mode") or "pair"
        if mode == "pair":
            yield fx["id"], _build(fx["submitted"]), _build(fx["candidate"])
        elif mode == "case":
            for i, c in enumerate(fx.get("candidates") or []):
                yield f"{fx['id']}#{i}", _build(fx["submitted"]), _build(c)


# --- the corpus ---------------------------------------------------------------

@pytest.mark.parametrize("fx", [f for f in _corpus()
                                if "item_states" in (f.get("invariants") or {})],
                         ids=lambda f: f["id"])
def test_fixtures_that_declare_item_states_are_reproduced_exactly(fx):
    sub, cand = _build(fx["submitted"]), _build(fx["candidate"])
    got, _ = _states(sub, cand, cand.creation_type)
    for key, want in fx["invariants"]["item_states"].items():
        assert got.get(key) == want, key


def test_at_least_the_two_s41_fixtures_declare_item_states():
    # Guards the parametrize above against silently collecting nothing.
    ids = {f["id"] for f in _corpus() if "item_states" in (f.get("invariants") or {})}
    assert {"item-states-list-fields", "item-states-sort-and-alternate-names"} <= ids


@pytest.mark.parametrize("fid,sub,cand", list(_record_pairs()), ids=lambda x: x
                         if isinstance(x, str) else "")
def test_items_agree_with_the_comparator(fid, sub, cand):
    """The item states are not derived from the comparator's own pairing (an
    item asks "has this a counterpart", the comparator "which 1:1 pairing
    scores the field"), so this pins the two against each other, per family:

    * titles -- the strongest item state is the comparator's best pair,
      banded: both are the global maximum of the same (discounted) pair
      similarities;
    * people, organizations, codes -- an item is non-neutral exactly when the
      comparator credits the field at all;
    * Alt IDs -- Kinds with an identical item are the comparator's matches,
      Kinds with a mismatch item its conflicts.
    """
    got, view = _states(sub, cand, cand.creation_type)
    bands = _bands()
    t = cmp_titles(sub, cand)
    if "titles" in got and t.quality is not None:
        want = band(t.meta["best_sim"], "title", bands)
        want = "neutral" if want == "mismatch" else want
        rank = {"neutral": 0, "similar": 1, "identical": 2}
        assert max(got["titles"], key=rank.__getitem__) == want
    for f, key in (("director", "director"), ("actor", "actor"),
                   ("assoc_org", "associated_org"), ("country", "country_of_origin"),
                   ("original_language", "original_language"),
                   ("version_language", "version_language")):
        if key not in got:
            continue
        q = COMPARATORS[f](sub, cand).quality
        assert (any(s != "neutral" for s in got[key])) == bool(q), (f, got[key], q)
        assert "mismatch" not in got[key]
    if "alternate_id" in got:
        r = cmp_alt_ids(sub, cand)
        kinds = {"identical": set(), "mismatch": set()}
        from eidr_core.compare import alt_source
        for item, s in zip(view["alt_ids"], got["alternate_id"], strict=True):
            if s in kinds:
                kinds[s].add(alt_source(SimpleNamespace(id_type=item[1], domain=item[2])))
        assert len(kinds["identical"]) == r.meta["matches"]
        assert len(kinds["mismatch"]) == r.conflict


# --- the rules, in both directions -------------------------------------------

SUB = _build({"titles": [{"text": "Stolen", "is_resource": True}],
              "directors": ["Ann Lee"], "actors": ["John Smith"], "countries": ["US"],
              "assoc_orgs": ["Acme Pictures"],
              "alt_ids": [{"value": "tt0000001", "id_type": "IMDB"},
                          {"value": "555", "id_type": "Proprietary",
                           "domain": "thetvdb.com", "relation": "IsSameAs"}]})
CND = _build({"titles": [{"text": "Stolen", "is_resource": True}, "Stolen: The Movie"],
              "directors": ["Ann Lee", "Bo Diddley"],
              "actors": [{"display": "Jon Smyth", "sort_name": "Smyth, Jon"}, "Zed Nobody"],
              "countries": ["US", "GB"], "assoc_orgs": ["Acme Pictures Inc", "Nothing Alike"],
              "alt_ids": [{"value": "tt0000001", "id_type": "IMDB", "relation": ""},
                          {"value": "999", "id_type": "Proprietary", "domain": "thetvdb.com"},
                          {"value": "42", "id_type": "Proprietary",
                           "domain": "themoviedb.org/movie"},
                          {"value": "tt7777777", "id_type": "IMDB",
                           "relation": "IsDerivedFrom"},
                          {"value": "555", "id_type": "Proprietary", "domain": "thetvdb.com",
                           "relation": "IsDerivedFrom"}]})


def _by_text(view_list, states):
    assert len(view_list) == len(states)
    return {str(v[0]): s for v, s in zip(view_list, states, strict=True)}


def test_aligned_index_for_index_with_the_view():
    st, view = _states(SUB, CND)
    for key, vkey in (("titles", "titles"), ("director", "directors"), ("actor", "actors"),
                      ("country_of_origin", "countries"), ("associated_org", "assoc_orgs"),
                      ("alternate_id", "alt_ids")):
        assert len(st[key]) == len(view[vkey]), key


def test_free_text_identical_similar_no_counterpart_and_never_red():
    st, view = _states(SUB, CND)
    assert _by_text(view["directors"], st["director"]) == {
        "Ann Lee": "identical", "Bo Diddley": "neutral"}
    a = _by_text(view["actors"], st["actor"])
    assert a == {"Jon Smyth": "similar", "Smyth, Jon": "similar", "Zed Nobody": "neutral"}
    assert "mismatch" not in st["director"] + st["actor"] + st["titles"] + st["associated_org"]


def test_controlled_vocabulary_is_identical_or_neutral():
    st, view = _states(SUB, CND)
    assert _by_text(view["countries"], st["country_of_origin"]) == {
        "GB": "neutral", "US": "identical"}


def test_alt_ids_identical_conflict_no_counterpart_and_non_identity():
    st, view = _states(SUB, CND)
    got = {(v[0], v[2]): s for v, s in zip(view["alt_ids"], st["alternate_id"], strict=True)}
    assert got[("tt0000001", None)] == "identical"     # empty relation = IsSameAs
    assert got[("999", "thetvdb.com")] == "mismatch"   # same Kind, value differs
    assert got[("42", "themoviedb.org/movie")] == "neutral"   # no counterpart Kind
    assert got[("tt7777777", None)] == "neutral"      # IsDerivedFrom: never compared
    assert got[("555", "thetvdb.com")] == "neutral"   # equal value, but IsDerivedFrom


def test_an_extra_value_under_a_matched_kind_is_not_a_conflict():
    sub = _build({"alt_ids": [{"value": "tt0000001", "id_type": "IMDB"}]})
    cand = _build({"alt_ids": [{"value": "tt0000001", "id_type": "IMDB"},
                               {"value": "tt0000002", "id_type": "IMDB"}]})
    st, view = _states(sub, cand)
    assert dict(zip([v[0] for v in view["alt_ids"]], st["alternate_id"], strict=True)) == {
        "tt0000001": "identical", "tt0000002": "neutral"}


def test_the_field_state_is_not_painted_onto_items():
    st, _ = _states(SUB, CND)
    fs, _ = field_states(_rationale(SUB, CND), _bands(), "Basic")
    assert fs["director"] == "identical"
    assert st["director"].count("neutral") == 1


def test_a_system_generated_title_beside_a_real_one_is_neutral_and_a_dropped_field_too():
    sub = _build({"creation_type": "Episode", "titles": ["Pilot"]})
    cand = _build({"creation_type": "Episode", "titles": [
        "Pilot", {"text": "Show: Season 1: Episode 1", "system_generated": True}]})
    st, view = _states(sub, cand, "Episode")
    assert _by_text(view["titles"], st["titles"]) == {
        "Pilot": "identical", "Show: Season 1: Episode 1": "neutral"}
    gen = {"creation_type": "Episode",
           "titles": [{"text": "S: Season 1: Episode 2", "system_generated": True}]}
    st2, _ = _states(_build(gen), _build(gen), "Episode")
    assert st2["titles"] == ["neutral"]


def test_absent_when_not_compared_and_when_the_view_list_is_empty():
    rows = [r for r in _rationale(SUB, CND) if r["field"] != "director"]
    st = field_item_states(rows, SUB, CND, _view(CND), _bands(), "Basic")
    assert "director" not in st                       # no rationale row, no glyphs
    bare = _build({"titles": ["Stolen"]})
    st, _ = _states(SUB, bare)
    assert "director" not in st and "alternate_id" not in st
    assert field_item_states([], None, CND, _view(CND), _bands()) == {}
