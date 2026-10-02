"""Internal-class titles in `cmp_titles`: inert without the knob, discounted with it.

Why this file exists (eidr-core 0.40.0, 2026-09-30). LanguageTool asked for
Internal titles -- system-generated machine translations (operator,
2026-09-30), ~450,000 of them registry-wide -- to take part in title
comparison, as normalized-record.md section 4.1 (ratified 2026-07-29) already
requires: "diminished value is acceptable, but they must NOT be ignored
entirely". Section 7 gap 1 records that `select_titles` ignored them.

The ruling split the work as T3 was: eidr-core ships the MECHANISM, inert
until a parameter source carries `INTERNAL_TITLE_DISCOUNT`; BMR-Review adds
the knob to its config.py and measures it before a compare-spec version
makes it live. Both halves are silent-failure surfaces, which is why they are
pinned here rather than left to the golden corpus alone:

* knob ABSENT must be today's behaviour byte for byte -- BMR-Review registers
  its config (no knob yet) and every consumer pins @main, so a drift here
  moves live scores with no version bump to announce it;
* knob PRESENT must discount exactly, never reduce a real-title match, and
  leave the 2026-08-30 system-generated both-sides drop where it was.

The knob-absent expectations below were captured by running these exact
cases against 0.39.0 BEFORE the change, then pinned.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest

pytest.importorskip("rapidfuzz")          # eidr_core.compare imports it eagerly

from eidr_core.compare import _params, cmp_titles, set_params  # noqa: E402
from eidr_core.compare.spec import load_spec  # noqa: E402

DISCOUNT = 0.8


@dataclass
class _Title:
    text: str
    lang: str | None = None
    title_class: str | None = None
    system_generated: bool = False


@dataclass
class _Rec:
    titles: list = field(default_factory=list)
    creation_type: str = "Basic"


def _real(text, lang="en"):
    return _Title(text, lang)


def _internal(text, lang="en"):
    return _Title(text, lang, title_class="Internal")


def _system(text):
    return _Title(text, "en", system_generated=True)


# The LanguageTool case: registered in French, carrying an Internal English
# translation, against a record registered with that English title.
FRENCH = _Rec([_real("Le Grand Voyage", "fr"), _internal("The Great Journey")])
ENGLISH = _Rec([_real("The Great Journey")])
INTERNAL_ONLY = _Rec([_internal("The Great Journey")])


@pytest.fixture(autouse=True)
def _restore_source():
    # set_params is process-global; put back whatever was registered so the
    # knob never leaks into another module's tests.
    before = _params.get_source()
    yield
    set_params(before)


def _without_knob():
    set_params(SimpleNamespace(**load_spec()))


def _with_knob(value=DISCOUNT):
    set_params(SimpleNamespace(**load_spec(), INTERNAL_TITLE_DISCOUNT=value))


# --- (a) knob absent: exactly 0.39.0 ---------------------------------------

def test_absent_knob_french_vs_english_is_unchanged():
    """Pinned from 0.39.0: the Internal English is dropped, so only the French
    title is compared and the pair reads 0.48 -- the gap the ruling closes."""
    _without_knob()
    r = cmp_titles(FRENCH, ENGLISH)
    assert r.quality == 0.48
    assert r.detail == "best=0.48 matches=1"
    assert r.meta == {"best_sim": 0.48, "part_conflict": False,
                      "part_base_match": 0.0, "part_ambiguous": False}


def test_absent_knob_adds_no_meta_key_and_no_rationale():
    # The new flag is emitted only with the knob, so consumers that compare
    # meta dicts (golden-pair expectations, De-Dupe UI vectors) see no change.
    _without_knob()
    r = cmp_titles(INTERNAL_ONLY, ENGLISH)
    assert "internal_title_used" not in r.meta
    assert "internal" not in r.detail


def test_absent_knob_internal_only_on_both_sides_is_still_dropped():
    """Pinned from 0.39.0: both sides fall back, so the title is dropped under
    the both-sides rule (with its system-generated wording)."""
    _without_knob()
    r = cmp_titles(INTERNAL_ONLY, _Rec([_internal("The Great Journey")]))
    assert r.quality is None
    assert r.detail == "system-generated titles only - ignored"
    assert r.meta == {}


# --- (b) knob present: quality == discount x the same texts as real titles --

@pytest.mark.parametrize("a_text,b_text", [
    ("The Great Journey", "The Great Journey"),     # exact: 1.0 -> 0.8
    ("The Great Journey", "The Grate Journy"),      # fuzzy: 0.88 -> 0.704
])
def test_present_knob_discounts_exactly(a_text, b_text):
    _with_knob()
    as_real = cmp_titles(_Rec([_real(a_text)]), _Rec([_real(b_text)])).quality
    as_internal = cmp_titles(_Rec([_internal(a_text)]),
                             _Rec([_real(b_text)])).quality
    assert as_real is not None and as_real > 0
    assert as_internal == pytest.approx(DISCOUNT * as_real)


def test_present_knob_french_vs_english_uses_the_translation():
    """The cross-language bridge: 0.48 on the French title alone becomes
    0.8 x 1.0 through the Internal English translation."""
    _with_knob()
    r = cmp_titles(FRENCH, ENGLISH)
    assert r.quality == pytest.approx(DISCOUNT)
    assert r.meta["best_sim"] == pytest.approx(DISCOUNT)


def test_present_knob_is_symmetric():
    _with_knob()
    assert (cmp_titles(FRENCH, ENGLISH).quality
            == cmp_titles(ENGLISH, FRENCH).quality)


# --- (c) a real-title match is never reduced ------------------------------

def test_real_exact_match_beside_an_internal_title_stays_full():
    _with_knob()
    a = _Rec([_real("Le Grand Voyage", "fr"), _internal("The Great Journey")])
    r = cmp_titles(a, _Rec([_real("Le Grand Voyage", "fr")]))
    assert r.quality == 1.0
    assert r.meta["internal_title_used"] is False


def test_a_tie_is_credited_to_the_real_title():
    # With the discount at 1.0 an Internal pair can equal a real one; the flag
    # must then say the real title carried the match.
    _with_knob(1.0)
    a = _Rec([_real("The Great Journey"), _internal("The Great Journey")])
    r = cmp_titles(a, ENGLISH)
    assert r.quality == 1.0
    assert r.meta["internal_title_used"] is False


# --- (d) fallback-only Internal on one side ------------------------------

def test_internal_only_side_is_full_weight_without_the_knob():
    """Pinned from 0.39.0: the fallback path compares it at FULL weight."""
    _without_knob()
    assert cmp_titles(INTERNAL_ONLY, ENGLISH).quality == 1.0
    assert cmp_titles(ENGLISH, INTERNAL_ONLY).quality == 1.0


def test_internal_only_side_is_discounted_with_the_knob():
    # Consistency (ruling R-I2): an Internal title is discounted whether or not
    # the record has a real title beside it.
    _with_knob()
    assert cmp_titles(INTERNAL_ONLY, ENGLISH).quality == pytest.approx(DISCOUNT)
    assert cmp_titles(ENGLISH, INTERNAL_ONLY).quality == pytest.approx(DISCOUNT)


def test_internal_only_on_both_sides_is_compared_with_the_knob():
    # The both-sides drop is for system-generated titles; a translation is
    # not derived from the record's structure, so it is compared (discounted).
    _with_knob()
    r = cmp_titles(INTERNAL_ONLY, _Rec([_internal("The Great Journey")]))
    assert r.quality == pytest.approx(DISCOUNT)


# --- (e) meta flag and rationale ------------------------------------------

def test_meta_flag_and_rationale_when_the_translation_carries_the_match():
    _with_knob()
    r = cmp_titles(FRENCH, ENGLISH)
    assert r.meta["internal_title_used"] is True
    assert r.detail.endswith("internal title, discounted")


def test_meta_flag_false_and_plain_rationale_when_a_real_title_wins():
    _with_knob()
    r = cmp_titles(_Rec([_real("The Great Journey"),
                         _internal("Le Grand Voyage", "fr")]), ENGLISH)
    assert r.meta["internal_title_used"] is False
    assert "internal" not in r.detail


# --- (e2) an Internal pair earns first-match credit only (2026-10-02) ------

# The measured case (a labelled no-match): the real titles agree at ~0.96, and
# once they are aligned the Internal translation is left pairing with the
# French subtitle at a fraction of its discount.
WEISS_SUB = _Rec([_real("Weisss Blut"),
                  _real("1948 : Du sang blanc pour l'Afrique du Sud")])
WEISS_CAND = _Rec([_real("Weisses Blut", "de"), _internal("White blood")])


def test_a_second_aligned_internal_pair_adds_no_bonus():
    _without_knob()
    plain = cmp_titles(WEISS_SUB, WEISS_CAND)
    _with_knob()
    r = cmp_titles(WEISS_SUB, WEISS_CAND)
    assert r.quality == plain.quality          # the real pair, nothing added
    assert r.meta["internal_title_used"] is False
    assert r.detail.startswith(f"best={plain.quality:.2f} matches=1")


def test_an_internal_best_pair_still_counts():
    _with_knob()
    r = cmp_titles(FRENCH, ENGLISH)
    assert r.quality == pytest.approx(DISCOUNT)


def test_further_real_pairs_keep_their_bonus_beside_an_internal_best():
    # Two real titles agreeing still accumulate even when an Internal title
    # is present on the record.
    _with_knob()
    a = _Rec([_real("Alpha"), _real("Beta Gamma"), _internal("Delta")])
    b = _Rec([_real("Alpha"), _real("Beta Gamma")])
    assert cmp_titles(a, b).quality > 1.0


# --- (f) the system-generated both-sides drop is unchanged ----------------

@pytest.mark.parametrize("knob", [False, True])
def test_system_generated_on_both_sides_is_dropped_either_way(knob):
    _with_knob() if knob else _without_knob()
    r = cmp_titles(_Rec([_system("A: Season 1")]), _Rec([_system("B: Season 1")]))
    assert r.quality is None
    assert r.detail == "system-generated titles only - ignored"


def test_system_generated_beside_internal_only_is_compared_with_the_knob():
    # One side system-generated only, the other Internal only: today both fall
    # back and the title is dropped; with the knob the Internal side is usable,
    # so this is the one-sided system-generated case (compared, 2026-08-30),
    # discounted because the pair involves an Internal title.
    _without_knob()
    assert cmp_titles(_Rec([_system("The Great Journey")]),
                      INTERNAL_ONLY).quality is None
    _with_knob()
    r = cmp_titles(_Rec([_system("The Great Journey")]), INTERNAL_ONLY)
    assert r.quality == pytest.approx(DISCOUNT)


def test_a_title_flagged_both_internal_and_system_generated_is_system():
    # The system-generated flag is the stronger statement; such a title stays
    # fallback-only so the both-sides drop still covers it.
    _with_knob()
    both = _Title("A: Season 1", "en", title_class="Internal", system_generated=True)
    r = cmp_titles(_Rec([both]), _Rec([_system("B: Season 1")]))
    assert r.quality is None


# --- the knob's contract --------------------------------------------------

@pytest.mark.parametrize("bad", [0, 0.0, -0.5, 1.01, True, "0.8"])
def test_a_malformed_knob_fails_loudly(bad):
    _with_knob(bad)
    with pytest.raises(ValueError, match="INTERNAL_TITLE_DISCOUNT"):
        cmp_titles(FRENCH, ENGLISH)


def test_an_explicit_none_reads_as_absent():
    _with_knob(None)
    assert cmp_titles(FRENCH, ENGLISH).quality == 0.48
