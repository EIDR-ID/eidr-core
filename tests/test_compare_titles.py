"""`cmp_titles` and the system-generated-title ruling (operator, 2026-08-30).

eidr-core's test suite is deliberately thin — the scoring engine is verified
by BMR-Review's golden-pair corpus, not here. This file is the exception the
convention allows: a rule whose wrong answer is SILENT.

Until 2026-08-30 the fallback test was ``a_fb or b_fb``, so a title was
dropped whenever EITHER side fell back to a system-generated one. The
one-sided case is precisely where the title carries the most information —
a real title beside a generated one is usually very different — and it was
being discarded with no signal that anything had been dropped.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest

pytest.importorskip("rapidfuzz")          # eidr_core.compare imports it eagerly

from eidr_core.compare import cmp_titles, set_params  # noqa: E402
from eidr_core.compare.spec import load_spec  # noqa: E402


@pytest.fixture(autouse=True)
def _params():
    """Register the packaged compare-spec as the parameter source.

    The comparators read tuning constants through a registered source rather
    than importing one, which is what lets BMR-Review keep `config.py` as the
    authoring surface. A test that scores must register something; the
    packaged spec is the portfolio's own values, so these assertions are
    against real thresholds rather than invented ones.
    """
    # load_spec() returns a dict; the source is read by ATTRIBUTE (BMR-Review
    # registers its config.py module), so wrap it.
    set_params(SimpleNamespace(**load_spec()))


@dataclass
class _Title:
    text: str
    lang: str | None = None
    title_class: str | None = None
    system_generated: bool = False
    self_defined: bool = True
    is_resource: bool = True


@dataclass
class _Rec:
    titles: list = field(default_factory=list)


def _rec(text: str, system_generated: bool = False) -> _Rec:
    return _Rec(titles=[_Title(text=text, system_generated=system_generated)])


def test_both_system_generated_is_still_dropped():
    """Unchanged, and the original reasoning still holds.

    A generated title restates series/season/episode structure that
    parent/family/distribution number already compare, so scoring it
    double-counts.
    """
    result = cmp_titles(_rec("A: Season 1", True), _rec("B: Season 1", True))
    assert result.quality is None
    assert "ignored" in result.detail


def test_one_system_generated_one_real_is_now_COMPARED():
    """The ruling. This case was dropped before 2026-08-30.

    "The only time you use a system-generated title is when one of the
    records in a comparison has a system-generated title but the other has
    a user-supplied title. Then, it must be used (and will likely be quite
    different.)" — operator, 2026-08-30.

    The both-sides argument does not extend here: the real-titled side
    carries information the structure does not.
    """
    result = cmp_titles(_rec("A: Season 1", True), _rec("Breaking Bad", False))
    assert result.quality is not None, "the one-sided case must be compared, not dropped"


def test_the_one_sided_case_in_the_other_order():
    # Symmetry: which side is generated must not matter.
    a = cmp_titles(_rec("A: Season 1", True), _rec("Breaking Bad", False))
    b = cmp_titles(_rec("Breaking Bad", False), _rec("A: Season 1", True))
    assert a.quality == b.quality


def test_both_real_titles_are_compared_unchanged():
    result = cmp_titles(_rec("Breaking Bad"), _rec("Breaking Bad"))
    assert result.quality == 1.0


def test_a_missing_title_is_still_dropped_not_scored_zero():
    """Absence is not disagreement.

    Scoring an absent title as 0 would swamp the field's weight; dropping it
    from the average is the long-standing behaviour and is unaffected by the
    ruling.
    """
    result = cmp_titles(_Rec(titles=[]), _rec("Breaking Bad"))
    assert result.quality is None
    assert "no real title" in result.detail


def test_the_discriminating_case_scores_low_rather_than_vanishing():
    """Why the ruling matters, not just that it was applied.

    A generated title next to an unrelated real one should read as weak
    evidence of similarity — which is information. Before the change it
    produced no field at all, so a reviewer saw nothing where there was
    something to see.
    """
    result = cmp_titles(_rec("The Series: Season 1", True),
                        _rec("Completely Different Show", False))
    assert result.quality is not None
    assert result.quality < 0.7
