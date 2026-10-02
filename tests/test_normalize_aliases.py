"""The alias maps must be idempotent, and a wrong answer here is SILENT.

norm_name / norm_title apply the maps token by token before comparison. A
non-idempotent entry makes two spellings of one name normalise differently,
so a director or actor comparison quietly scores 0 for the same person. The
dictionary audit (2026-10-02) found exactly one: T 'jacque' -> 'jacques' and
CT 'jacques' -> 'jacob', resolved per domain and then merged.
"""
from eidr_core.normalize import norm_name
from eidr_core.normalize.aliases import _load, alias_name, alias_title


def test_both_maps_are_idempotent():
    for m in _load():
        bad = {w: (v, m[v]) for w, v in m.items() if m.get(v, v) != v}
        assert not bad, bad


def test_cross_domain_chain_is_followed():
    assert alias_name("jacque") == alias_name("jacques") == alias_name(alias_name("jacque"))
    assert norm_name("Jacque Brel") == norm_name("Jacques Brel")


def test_title_map_is_unchanged_by_the_name_fix():
    # The CT (title) map is resolved on its own exactly as before.
    assert alias_title(alias_title("jacques")) == alias_title("jacques")
