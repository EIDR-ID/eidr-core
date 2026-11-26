"""A one-sided title date against the OTHER record's release date, inert until
enabled (``TITLE_DATE_VS_RELEASE_DATE``; operator approved 2026-11-26).

BMR-Review's handoff of 2026-11-24 (section 1, follow-up): 14 daily-programme
rows ("04/09/2026 - Esporte Total") lost their sole-Accept at 2.23.0 because
an undated sibling ("Esporte Total: Season 2025: Episode 182", a year away)
scored close once the date was set aside, and reached Review. The undated
record's own ReleaseDate names its day, so a title date that cannot be that
day counts as different dates.

Every wrong answer here is silent -- a plausible title quality -- so the
knob-absent path is pinned as today's behaviour, byte for byte, over the
whole golden corpus, and the rule is pinned in both directions: it fires on
the sibling, and not on the true record, an ambiguous d/m date, a date the
record does not assert, a film, or a pair whose titles are both dated.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from importlib.resources import files
from types import SimpleNamespace

import pytest

pytest.importorskip("rapidfuzz")

import eidr_core.compare as ec  # noqa: E402
from eidr_core.compare import _params, cmp_titles, set_params  # noqa: E402
from eidr_core.compare.spec import load_spec  # noqa: E402
from eidr_core.compare.states import field_item_states  # noqa: E402
from eidr_core.compare.titles import (  # noqa: E402
    COMBINATION_DIFFERS_QUALITY,
    dates_ambiguous,
    title_similarity,
)

KNOB = "TITLE_DATE_VS_RELEASE_DATE"
DATED = "04/09/2026 - Esporte Total"
SIBLING_TITLE = "Esporte Total: Season 2025: Episode 182"


@dataclass
class _Title:
    text: str
    lang: str | None = None
    title_class: str | None = None
    system_generated: bool = False


@dataclass
class _Rec:
    titles: list = field(default_factory=list)
    creation_type: str = "Episode"
    release_date: str | None = None
    date_estimated: bool = False


def _rec(release, *titles, ct="Episode", estimated=False):
    ts = [t if isinstance(t, _Title) else _Title(t) for t in titles]
    return _Rec(ts, ct, release, estimated)


SUBMITTED = _rec("2026-09-04", DATED)
SIBLING = _rec("2025-09-04", _Title(SIBLING_TITLE, system_generated=True))
# The true record carries the programme's name without the date (a generated
# "...: Episode 1" would read as a part number, a different rule).
TRUE = _rec("2026-09-04", "Esporte Total")


@pytest.fixture(autouse=True)
def _restore_source():
    before = _params.get_source()
    yield
    set_params(before)


def _params_with(**knobs):
    # The packaged spec carries TITLE_DATE_TOKENS true (2.23.0); KNOB is not in
    # it until BMR-Review lands it, but strip it so this stays true after.
    spec = load_spec()
    spec.pop(KNOB, None)
    set_params(SimpleNamespace(**{**spec, **knobs}))


# --- the Esporte Total shape, both ways --------------------------------------

@pytest.mark.parametrize("swap", [False, True], ids=["submitted-dated", "candidate-dated"])
def test_the_sibling_a_year_away_is_a_different_programme(swap):
    _params_with(**{KNOB: True})
    a, b = (SIBLING, SUBMITTED) if swap else (SUBMITTED, SIBLING)
    r = cmp_titles(a, b)
    assert r.quality == COMBINATION_DIFFERS_QUALITY
    assert r.meta["date_differs_from_release_date"] is True
    assert r.meta["date_ambiguous"] is False          # two days, not an unknown one
    assert "title date differs from release date" in r.detail


@pytest.mark.parametrize("swap", [False, True], ids=["submitted-dated", "candidate-dated"])
def test_the_true_record_on_that_day_is_not(swap):
    _params_with(**{KNOB: True})
    a, b = (TRUE, SUBMITTED) if swap else (SUBMITTED, TRUE)
    on = cmp_titles(a, b)
    _params_with()
    off = cmp_titles(a, b)
    assert on.quality == off.quality > COMBINATION_DIFFERS_QUALITY
    assert on.meta["date_differs_from_release_date"] is False
    assert on.meta["date_ambiguous"] is off.meta["date_ambiguous"] is True


def test_without_the_knob_the_sibling_scores_as_today():
    _params_with()
    r = cmp_titles(SUBMITTED, SIBLING)
    assert r.quality == 1.0                           # the 2.23.0 behaviour the rule fixes
    assert r.meta["date_ambiguous"] is True
    assert "date_differs_from_release_date" not in r.meta
    assert "release date" not in r.detail


def test_the_knob_needs_title_date_tokens():
    _params_with(**{KNOB: True, "TITLE_DATE_TOKENS": False})
    r = cmp_titles(SUBMITTED, SIBLING)
    _params_with(TITLE_DATE_TOKENS=False)
    assert r.quality == cmp_titles(SUBMITTED, SIBLING).quality
    assert r.meta["date_differs_from_release_date"] is False


@pytest.mark.parametrize("bad", ["true", 1, 0.0])
def test_a_malformed_knob_fails_loudly(bad):
    _params_with(**{KNOB: bad})
    with pytest.raises(ValueError, match=KNOB):
        cmp_titles(_rec(None, "A", ct="Basic"), _rec(None, "A", ct="Basic"))


# --- which release dates may stand for a day ---------------------------------

@pytest.mark.parametrize("sibling", [
    _rec("2025", _Title(SIBLING_TITLE, system_generated=True)),               # year only
    _rec("2025-09-04", _Title(SIBLING_TITLE, system_generated=True), estimated=True),
    _rec("1970-01-01", _Title(SIBLING_TITLE, system_generated=True)),         # epoch default
    _rec(None, _Title(SIBLING_TITLE, system_generated=True)),
], ids=["year-only", "estimated", "epoch", "absent"])
def test_a_date_the_record_does_not_assert_never_fires(sibling):
    _params_with(**{KNOB: True})
    r = cmp_titles(SUBMITTED, sibling)
    assert r.quality == 1.0
    assert r.meta["date_differs_from_release_date"] is False


def test_an_inherited_release_date_never_fires():
    _params_with(**{KNOB: True})
    sib = _rec("2025-09-04", _Title(SIBLING_TITLE, system_generated=True))
    sib.eidr_provenance = {"release_date": "inherited"}   # inheritance.provenance()
    assert cmp_titles(SUBMITTED, sib).quality == 1.0
    sib.eidr_provenance = {"release_date": "self"}
    assert cmp_titles(SUBMITTED, sib).quality == COMBINATION_DIFFERS_QUALITY


def test_a_film_pair_is_untouched():
    _params_with(**{KNOB: True})
    a = _rec("2026-09-04", DATED, ct="Basic")
    b = _rec("2025-09-04", "Esporte Total", ct="Basic")
    on = cmp_titles(a, b)
    _params_with()
    assert on.quality == cmp_titles(a, b).quality
    assert on.meta["date_differs_from_release_date"] is False


# --- title_similarity: the pure rule ------------------------------------------

DAY = (2026, 9, 4)


@pytest.mark.parametrize("dated,other_day,differs", [
    ("04/09/2026 - X", (2026, 9, 4), False),     # d/m reading
    ("09/04/2026 - X", (2026, 9, 4), False),     # m/d reading: ambiguous, so it fits
    ("13/09/2026 - X", (2026, 9, 4), True),      # no reading is the 4th of September
    ("04/09/2026 - X", (2025, 9, 4), True),      # a year away
    ("04/09/26 - X", (2026, 9, 4), False),       # two-digit year, last two digits
    ("04/09/26 - X", (1926, 9, 4), False),       # the century is not guessed
    ("04/09/26 - X", (2025, 9, 4), True),
    ("2026-09-04 X", (2026, 9, 4), False),       # y-m-d
    ("2026-09-05 X", (2026, 9, 4), True),
    ("Fri, 9/4 - X", (2025, 9, 4), False),       # m/d carries no year
    ("Fri, 9/5 - X", (2026, 9, 4), True),
])
def test_a_one_sided_date_against_the_other_records_day(dated, other_day, differs):
    want = COMBINATION_DIFFERS_QUALITY if differs else 1.0
    # Whichever side is dated, the OTHER record's day is the one read.
    assert title_similarity(dated, "X", episodic=True, dates=True,
                            release_dates=(None, other_day)) == pytest.approx(want)
    assert title_similarity("X", dated, episodic=True, dates=True,
                            release_dates=(other_day, None)) == pytest.approx(want)
    # The dated title's OWN record's day is never read.
    assert title_similarity(dated, "X", episodic=True, dates=True,
                            release_dates=(other_day, None)) == 1.0


def test_both_titles_dated_never_reads_the_release_dates():
    for days in [(DAY, (2020, 1, 1)), ((2020, 1, 1), (2021, 2, 2))]:
        assert title_similarity("04/09/2026 - X", "04/09/2026 - X", episodic=True,
                                dates=True, release_dates=days) == 1.0
        assert title_similarity("04/09/2026 - X", "05/09/2026 - X", episodic=True,
                                dates=True, release_dates=days) == COMBINATION_DIFFERS_QUALITY


def test_release_dates_act_only_with_dates_and_episodic():
    days = (None, (2025, 9, 4))
    assert title_similarity(DATED, "Esporte Total", episodic=True,
                            release_dates=days) == title_similarity(
        DATED, "Esporte Total", episodic=True)
    assert title_similarity(DATED, "Esporte Total", dates=True,
                            release_dates=days) == title_similarity(
        DATED, "Esporte Total", dates=True)


def test_a_rule_firing_pair_is_not_ambiguous():
    assert dates_ambiguous([DATED], ["Esporte Total"])
    assert dates_ambiguous([DATED], ["Esporte Total"], release_dates=(None, DAY))
    assert not dates_ambiguous([DATED], ["Esporte Total"], release_dates=(None, (2025, 9, 4)))


# --- the item states follow the comparator -----------------------------------

def test_item_states_read_the_title_pair_under_the_same_rule():
    rows = [{"field": "title", "quality": 1.0}]
    view = {"titles": [[SIBLING_TITLE]]}
    bands = load_spec()["STATE_BANDS"]
    _params_with()
    assert field_item_states(rows, SUBMITTED, SIBLING, view, bands, "Episode") == {
        "titles": ["identical"]}
    _params_with(**{KNOB: True})
    assert field_item_states(rows, SUBMITTED, SIBLING, view, bands, "Episode") == {
        "titles": ["neutral"]}


# --- the golden corpus, knob absent ------------------------------------------

def _corpus_record_pairs():
    root = files("eidr_core") / "specs" / "golden_pairs"
    for p in sorted(root.iterdir(), key=lambda p: p.name):
        if not p.name.endswith(".json"):
            continue
        fx = json.loads(p.read_text(encoding="utf-8"))
        cands = ([fx["candidate"]] if (fx.get("mode") or "pair") == "pair"
                 else fx.get("candidates") or [])
        if fx.get("mode") == "recovery_pool":
            continue
        for c in cands:
            yield fx["id"], fx["submitted"], c


def _titled(d):
    ts = []
    for t in d.get("titles") or []:
        ts.append(_Title(t) if isinstance(t, str) else
                  _Title(t["text"], t.get("lang"), t.get("title_class"),
                         bool(t.get("system_generated"))))
    r = _Rec(ts, d.get("creation_type") or "Basic", d.get("release_date"),
             bool(d.get("date_estimated")))
    if d.get("provenance"):
        r.eidr_provenance = dict(d["provenance"])
    return r


def test_the_golden_corpus_is_unchanged_with_the_knob_absent(monkeypatch):
    """Over every record pair in the corpus: with the knob absent no release
    date reaches the title rules (title_similarity and dates_ambiguous see
    ``release_dates=None`` only), and the result equals the knob set false."""
    seen = []
    real_sim, real_amb = ec.title_similarity, ec.dates_ambiguous

    def spy_sim(*a, release_dates=None, **k):
        seen.append(release_dates)
        return real_sim(*a, release_dates=release_dates, **k)

    def spy_amb(*a, release_dates=None, **k):
        seen.append(release_dates)
        return real_amb(*a, release_dates=release_dates, **k)

    monkeypatch.setattr(ec, "title_similarity", spy_sim)
    monkeypatch.setattr(ec, "dates_ambiguous", spy_amb)
    pairs = [(fid, _titled(s), _titled(c)) for fid, s, c in _corpus_record_pairs()]
    assert len(pairs) > 50
    for fid, a, b in pairs:
        _params_with()
        absent = cmp_titles(a, b)
        assert "date_differs_from_release_date" not in absent.meta, fid
        _params_with(**{KNOB: False})
        off = cmp_titles(a, b)
        off.meta.pop("date_differs_from_release_date", None)   # absent on a dropped field
        assert (absent.quality, absent.detail, absent.meta) == (
            off.quality, off.detail, off.meta), fid
    assert seen and all(rd is None for rd in seen)
