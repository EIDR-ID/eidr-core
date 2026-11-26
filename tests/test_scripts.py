"""eidr_core.scripts, extracted from LanguageTool (proposal 2, 2026-11-24;
accepted in part 2026-11-26).

A wrong script profile is silent: it is a plausible answer ("Latin", 0.6)
that sends a title down the wrong branch of a consumer's rules. The cases
are LanguageTool's (tests/test_text.py: test_profile,
test_kana_share_counts_kanji, test_fullwidth_is_latin, test_is_non_latin),
minus the single_language() column, which is language policy and stayed in
LanguageTool.

Everything but the missing-extra test needs the ``[scripts]`` extra (regex)
and is skipped without it, so the base install's suite still runs green.
"""
from __future__ import annotations

import importlib.util
import sys

import pytest

from eidr_core import scripts

needs_regex = pytest.mark.skipif(
    importlib.util.find_spec("regex") is None,
    reason="the [scripts] extra (regex) is not installed")


# --- ported: test_profile (script_key column) --------------------------------


@needs_regex
@pytest.mark.parametrize("text,key", [
    ("七人の侍", "Kana"),          # kana present: Kana wins over Han
    ("기생충", "Hangul"),
    ("Ο Θίασος", "Greek"),
    ("BTS 방탄소년단", "Hangul"),   # dominant by letter count
    ("The Matrix", "Latin"),
    ("卧虎藏龙", "Han"),            # Han alone stays Han
])
def test_profile_script_key(text, key):
    assert scripts.profile(text).script_key == key


@needs_regex
def test_kana_share_counts_kanji():
    p = scripts.profile("七人の侍")
    assert p.share == 1.0
    assert p.counts == {"Han": 3, "Kana": 1}
    assert p.has_kana


@needs_regex
def test_fullwidth_is_latin():
    assert scripts.profile("ＡＫＩＲＡ").is_latin


@needs_regex
def test_is_non_latin():
    assert scripts.is_non_latin("読売テレビ")
    assert not scripts.is_non_latin("Pathé")
    assert not scripts.is_non_latin("2046")           # no letters at all


# --- the rest of the surface --------------------------------------------------


@needs_regex
@pytest.mark.parametrize("ch,expected", [
    ("a", "Latin"), ("é", "Latin"), ("ж", "Cyrillic"), ("λ", "Greek"),
    ("漢", "Han"), ("の", "Hiragana"), ("カ", "Katakana"), ("한", "Hangul"),
    ("ש", "Hebrew"), ("ب", "Arabic"), ("ก", "Thai"), ("ᚠ", "Other"),  # Runic
    ("1", None), (" ", None), ("-", None), ("́", None),     # combining acute
    # Common-script letters: by Script_Extensions, else None (not "Other").
    ("ー", "Hiragana"), ("ｰ", "Hiragana"), ("ʼ", "Latin"), ("ʻ", None),
])
def test_char_script(ch, expected):
    assert scripts.char_script(ch) == expected


@needs_regex
@pytest.mark.parametrize("text", ["コーヒー", "ラーメン", "スーパーマン"])
def test_prolonged_sound_mark_counts_as_kana(text):
    # The source counted 'ー' as "Other": 'コーヒー' had "Other" dominant and
    # a share of 0.5. Fixed at extraction (char_script's Script_Extensions
    # step); this pins it.
    p = scripts.profile(text)
    assert p.dominant == "Kana" and p.share == 1.0 and p.counts == {"Kana": len(text)}
    assert p.tokens == len(text)


@needs_regex
def test_profile_fields():
    p = scripts.profile("Hello Мир")
    assert p.counts == {"Latin": 5, "Cyrillic": 3}
    assert p.dominant == "Latin"
    assert p.share == 5 / 8
    assert p.letters == 8
    assert p.tokens == 2
    assert p.is_mixed and not p.has_kana


@needs_regex
def test_unspaced_script_counts_characters_as_tokens():
    assert scripts.profile("卧虎藏龙").tokens == 4
    assert scripts.profile("七人の侍").tokens == 4      # Kana counts as unspaced too
    assert scripts.profile("Spider-Man: Homecoming").tokens == 3


@needs_regex
@pytest.mark.parametrize("text", ["", None, "2046 !?"])
def test_empty_profile(text):
    p = scripts.profile(text)
    assert (p.letters, p.dominant, p.share, p.counts) == (0, None, 0.0, {})


@needs_regex
def test_is_non_latin_threshold():
    # Two Latin letters of five: 0.4 Latin.
    assert scripts.is_non_latin("ab вгд")
    assert not scripts.is_non_latin("ab вгд", min_share=0.4)


def test_unspaced_needs_no_extra():
    assert "Han" in scripts.UNSPACED and "Latin" not in scripts.UNSPACED


def test_missing_extra_raises_an_importerror_naming_it(monkeypatch):
    # sys.modules[name] = None makes `import regex` raise ImportError, which
    # is what a base install without the extra sees.
    monkeypatch.setitem(sys.modules, "regex", None)
    scripts._regex.cache_clear()
    scripts._patterns.cache_clear()
    scripts.char_script.cache_clear()
    try:
        with pytest.raises(ImportError, match=r"eidr-core\[scripts\]"):
            scripts.profile("abc")
    finally:
        # Leave no cached failure (or cached success) for the other tests.
        scripts._regex.cache_clear()
        scripts._patterns.cache_clear()
        scripts.char_script.cache_clear()
