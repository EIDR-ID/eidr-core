"""JsonFactCache: persists across instances, honours refresh and ttl, and a
crash mid-store leaves the previous file (0.35.0)."""
import json

from eidr_core.external import FactCache, JsonFactCache


def test_round_trips_across_instances_and_is_a_fact_cache(tmp_path):
    p = tmp_path / "facts.json"
    c1 = JsonFactCache(p)
    assert isinstance(c1, FactCache)
    c1.store({("tmdb", "1"): {"status": "found", "facts": {"year": 1939}}})
    c2 = JsonFactCache(p)
    got = c2.load([("tmdb", "1"), ("tmdb", "2")])
    assert got == {("tmdb", "1"): {"status": "found", "facts": {"year": 1939}}}
    assert c2.load([("tmdb", "1")], refresh=True) == {}


def test_ttl_hides_old_entries_and_a_store_overwrites(tmp_path, monkeypatch):
    import eidr_core.external as ext
    p = tmp_path / "facts.json"
    now = [1_000.0]
    monkeypatch.setattr(ext.time, "time", lambda: now[0])
    c = JsonFactCache(p, ttl_seconds=60)
    c.store({("wd", "Q1"): {"status": "found", "facts": {}}})
    assert ("wd", "Q1") in c.load([("wd", "Q1")])
    now[0] += 61
    assert c.load([("wd", "Q1")]) == {}
    c.store({("wd", "Q1"): {"status": "found", "facts": {"x": 1}}})
    assert c.load([("wd", "Q1")])[("wd", "Q1")]["facts"] == {"x": 1}


def test_the_file_is_replaced_atomically(tmp_path):
    p = tmp_path / "facts.json"
    c = JsonFactCache(p)
    c.store({("a", "1"): {"status": "found", "facts": {}}})
    assert not (tmp_path / "facts.json.tmp").exists()
    with open(p, encoding="utf-8") as fh:
        assert json.load(fh)[0][:2] == ["a", "1"]
