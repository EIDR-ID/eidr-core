"""codes.normalize_country_code on the values real callers pass (0.68.0).

Why: it was annotated ``str`` but receives ``None`` (empty cells) and ints
(JSON numbers, spreadsheet cells holding an M49 region). ``None`` already gave
``""``; an int raised AttributeError (dictionary audit 2026-10-02). An int
must give the same string as the code written as text, or the same region
compares unequal to itself depending on where it was read.
"""
from __future__ import annotations

import pytest

from eidr_core.codes import country_list, normalize_country_code


@pytest.mark.parametrize("code,want", [
    (None, ""), ("", ""), (" su ", "SUHH"), ("US", "US"), ("XX", "XX"),
    ("150", "150"), ("019", "019"),
    (150, "150"), (419, "419"), (19, "019"), (1, "001"),
])
def test_normalize_country_code(code, want):
    assert normalize_country_code(code) == want


@pytest.mark.parametrize("as_int,as_str", [(150, "150"), (19, "019"), (2, "002")])
def test_an_int_region_equals_the_same_region_as_text(as_int, as_str):
    assert normalize_country_code(as_int) == normalize_country_code(as_str)


def test_country_list_accepts_int_regions():
    assert country_list(["FR", 150, None, "150"]) == ["FR", "150"]
