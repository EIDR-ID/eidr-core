"""eidr_core.bmr_rows and codes.country_list (C2, 0.60.0): the silent failures
-- a file over the BMR tool's limit, a split Series tree, a lost note, XX beside
a real country."""
from __future__ import annotations

import pytest

from eidr_core import bmr_rows
from eidr_core.codes import country_list
from eidr_core.swap import swap_note


def _trees(*sizes):
    rows = []
    for n, size in enumerate(sizes):
        rows.append(("Series", n))
        rows += [("Episode", n)] * (size - 1)
    return rows


def _series(row):
    return row[0] == "Series"


def test_the_limit_is_a_ceiling_and_no_tree_is_split():
    rows = _trees(3000, 2500, 1000, 4000)
    chunks = bmr_rows.chunk_rows(rows, starts_tree=_series)
    assert [len(c) for c in chunks] == [3000, 3500, 4000]
    for c in chunks:
        assert c[0][0] == "Series"
        trees = {n for _, n in c}
        assert all(sum(1 for r in rows if r[1] == t) == sum(1 for r in c if r[1] == t)
                   for t in trees)


def test_a_tree_over_the_limit_goes_alone():
    chunks = bmr_rows.chunk_rows(_trees(100, 6000, 100), starts_tree=_series)
    assert [len(c) for c in chunks] == [100, 6000, 100]


def test_without_trees_it_cuts_every_limit_rows():
    assert [len(c) for c in bmr_rows.chunk_rows(list(range(12001)))] == [5000, 5000, 2001]
    assert bmr_rows.chunk_rows([]) == []
    with pytest.raises(ValueError):
        bmr_rows.chunk_rows([1], limit=0)


def test_leading_orphans_form_their_own_group():
    rows = [("Episode", "o")] * 3 + _trees(4)
    assert [len(c) for c in bmr_rows.chunk_rows(rows, limit=5, starts_tree=_series)] == [3, 4]


def test_join_notes_puts_the_swap_note_first_and_skips_blanks():
    swap = swap_note("10.5240/A", "Performance", "10.5240/B")
    assert bmr_rows.join_notes("contested: also claimed", "", None, swap) == (
        f"{swap} | contested: also claimed")
    assert bmr_rows.join_notes() == ""


def test_registry_ids_cell_is_sorted_and_unique():
    assert bmr_rows.registry_ids_cell(["10.5240/B", "10.5240/A", " 10.5240/B ", ""]) == (
        "10.5240/A | 10.5240/B")


def test_number_families_omits_empty_members():
    row = {"Title": "T", "lang": [("en", "Audio"), ("fr", "")], "country": [("US",)]}
    out = bmr_rows.number_families(row, {"lang": ("Original Language", "Language Mode"),
                                         "country": ("Country of Origin",)})
    assert out == {"Title": "T", "Original Language 1": "en", "Language Mode 1": "Audio",
                   "Original Language 2": "fr", "Country of Origin 1": "US"}


@pytest.mark.parametrize("codes,want", [
    ([], ["XX"]), (["XX"], ["XX"]), (["XX", "us"], ["US"]), (["su", "SUHH", " "], ["SUHH"]),
    (["FR", "XX", "DE", "FR"], ["FR", "DE"])])
def test_country_list_keeps_xx_only_alone(codes, want):
    assert country_list(codes) == want
