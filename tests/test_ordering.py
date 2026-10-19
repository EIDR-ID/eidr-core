"""Title display order: placement is STRUCTURAL; only Internal moves a title.

Operator ruling 2026-10-19 (0.69.0), from the 2026-10-02 dictionary audit:
"Ignore title classes, except for Internal and transliterated." Until then
``title_bucket`` put ANY title of class Release or Resource in bucket 0, the
ResourceName bucket, so an alternate of class Release could sort above the
real ResourceName in BMR-Review's ``render_record``. Nothing raised: the
order was simply wrong, which is why this lives here (a silent surface).

The spec's worked example is executed from the spec's own tables, so the
prose in ``specs/title-display-order.md`` cannot drift from the code.
"""
from __future__ import annotations

import pathlib

import pytest

import eidr_core.ordering as ordering
from eidr_core.ordering import title_bucket, title_sort_key

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = ROOT / "specs" / "title-display-order.md"


@pytest.mark.parametrize("klass", ["release", "Release", "RESOURCE", "resource"])
def test_a_release_or_resource_class_alternate_is_an_ordinary_alternate(klass):
    assert title_bucket(klass) == 1
    assert title_bucket(klass, is_resource=False) == 1


@pytest.mark.parametrize("klass", [None, "", "Release", "Internal", "transliterated"])
def test_the_structural_flag_alone_makes_the_resource_name(klass):
    assert title_bucket(klass, is_resource=True) == 0


def test_internal_moves_an_alternate_last_but_never_the_resource_name():
    assert title_bucket("Internal") == 2
    assert title_bucket("INTERNAL") == 2              # casefolded
    assert title_bucket("Internal", is_resource=True) == 0


def test_transliterated_has_no_ordering_treatment_yet():
    # The ruling names it as an exception, but neither spec defines an
    # ordering treatment for it, so it orders as an ordinary alternate.
    # Pinned so a future treatment is a visible decision, not drift.
    assert title_bucket("transliterated") == 1


def test_a_release_alternate_no_longer_sorts_above_the_resource_name():
    """The audit's case, as render_record sorts: one combined list carrying
    the structural flag. 'Aardvark' < 'Working' alphabetically, so under the
    old rule (both in bucket 0) the alternate came first."""
    titles = [("Working Cut 7", None, True),
              ("Aardvark Festival Title", "Release", False),
              ("Midway Title", None, False)]
    ordered = sorted(titles, key=lambda t: title_sort_key(*t))
    assert [t[0] for t in ordered] == [
        "Working Cut 7", "Aardvark Festival Title", "Midway Title"]


def test_the_class_based_resource_test_is_gone_from_the_public_surface():
    # Removed at 0.69.0: it embodied the rule the operator rejected, and no
    # consumer imported it. A class must never stand in for the flag.
    assert "is_resource_class" not in ordering.__all__
    assert not hasattr(ordering, "is_resource_class")


def _table_after(text: str, heading: str) -> list[list[str]]:
    """The first markdown table after ``heading``, minus header and rule."""
    lines = text[text.index(heading):].splitlines()
    rows: list[list[str]] = []
    for line in lines[1:]:
        if line.startswith("|"):
            rows.append([c.strip() for c in line.strip().strip("|").split("|")])
        elif rows:
            break
    return rows[2:]


def test_the_spec_worked_example_holds_when_executed():
    text = SPEC.read_text(encoding="utf-8")
    given = _table_after(text, "Input (API order")
    expected = [row[0] for row in _table_after(text, "Output (display order)")]
    assert any(row[1] == "Release" for row in given), "example lost its Release row"
    titles = [(row[3], row[1] or None, row[0] == "ResourceName") for row in given]
    ordered = sorted(titles, key=lambda t: title_sort_key(*t))
    assert [t[0] for t in ordered] == expected
