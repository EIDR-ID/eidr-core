"""Unicode script profiling for titles and names.

Which script a string is written in decides much of what a tool may do with
it: whether a transliteration is needed, whether a name must be romanized,
whether a title declared in a Latin-script language is really written in
one. Python's ``unicodedata`` has no Script property, so this module reads
it through the third-party ``regex`` package (``\\p{Script=...}``), which
tracks the current Unicode release. That is the ``[scripts]`` extra::

    pip install "eidr-core[scripts] @ git+https://github.com/EIDR-ID/eidr-core.git@main"

``regex`` is imported on first use, not at import time, so ``UNSPACED`` and
the module itself are available without it; every function raises an
ImportError naming the extra when it is missing.

Extracted from LanguageTool ``src/language_tool/scripts.py`` (proposal 2,
2026-11-24; register OVERLAPS row 20, accepted in part 2026-11-26). Only the
script MECHANICS moved. Which language a script implies
(``SINGLE_LANGUAGE_SCRIPTS``, ``single_language()``,
``refine_single_language()``) is language policy measured on EIDR data and
stays in LanguageTool: a profile says what is written, not what it means.
"""
from __future__ import annotations

import unicodedata
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

__all__ = [
    "UNSPACED",
    "ScriptProfile",
    "char_script",
    "is_non_latin",
    "profile",
]

# The scripts char_script names, tried in this order. A letter in none of
# them is "Other". Hiragana and Katakana are kept apart here; profile()
# merges them as "Kana". LanguageTool's list, unchanged.
_SCRIPTS = (
    "Latin", "Cyrillic", "Greek", "Han", "Hiragana", "Katakana", "Hangul",
    "Arabic", "Hebrew", "Thai", "Devanagari", "Bengali", "Tamil", "Telugu",
    "Kannada", "Malayalam", "Gujarati", "Gurmukhi", "Oriya", "Sinhala",
    "Georgian", "Armenian", "Ethiopic", "Khmer", "Lao", "Myanmar", "Tibetan",
    "Mongolian", "Thaana", "Syriac", "Bopomofo",
)

# Scripts written without spaces between words, so a length in words means
# nothing and profile() counts characters instead. "Kana" (profile's merged
# name) is treated the same way.
UNSPACED = frozenset({"Han", "Hiragana", "Katakana", "Thai", "Lao", "Khmer", "Myanmar", "Tibetan"})

_INSTALL_HINT = (
    "eidr_core.scripts needs the third-party 'regex' package for Unicode "
    "Script properties. Install the extra: "
    "pip install \"eidr-core[scripts] @ git+https://github.com/EIDR-ID/eidr-core.git@main\""
)


@lru_cache(maxsize=1)
def _regex() -> Any:
    """The ``regex`` module, imported once on first use.

    Lazy so that a consumer that never profiles text does not need the
    extra (the base install is stdlib-only); typed ``Any`` because regex
    ships no type information and mypy runs without the extra installed."""
    try:
        import regex
    except ImportError as exc:
        raise ImportError(_INSTALL_HINT) from exc
    return regex


@lru_cache(maxsize=1)
def _patterns() -> tuple[tuple[tuple[str, Any, Any], ...], Any]:
    """Per script: its Script and Script_Extensions patterns; and one
    pattern for the Common and Inherited scripts."""
    rx = _regex()
    per_script = tuple((s, rx.compile(rf"\p{{Script={s}}}"), rx.compile(rf"\p{{scx={s}}}"))
                       for s in _SCRIPTS)
    return per_script, rx.compile(r"[\p{Script=Common}\p{Script=Inherited}]")


@lru_cache(maxsize=65536)
def char_script(ch: str) -> str | None:
    """The script of one character: one of the 31 names in ``_SCRIPTS``
    ("Latin", "Cyrillic", "Han", "Hiragana", "Katakana", "Hangul", ...),
    "Other" for a letter in any other script, or None for anything that is
    not a letter of a script (digits, punctuation, symbols, spaces,
    combining marks, and Common-script letters such as the okina ``ʻ``).

    A letter (``str.isalpha()``) is looked up by its Unicode Script
    property first. A letter whose Script is Common or Inherited is then
    looked up by its Script_Extensions, so the katakana-hiragana prolonged
    sound mark ``ー`` (U+30FC, Script=Common, extensions Hiragana and
    Katakana) counts as "Hiragana" -- profile() merges it into "Kana" -- and
    ``ʼ`` (U+02BC) as "Latin". One with no extension in the list is None.

    Why the extension step (eidr-core, at extraction 2026-11-26): the
    source returned "Other" for every Common-script letter, so 'コーヒー'
    profiled as Kana 2 / Other 2 with "Other" dominant and a share of 0.5,
    and 'ラーメン' at 0.75 -- under the 0.8 a consumer uses to trust a
    script -- while its own docstring promised None for Common.

    Raises ImportError when the ``regex`` package (the ``[scripts]`` extra)
    is absent."""
    if not ch.isalpha():
        return None
    per_script, common = _patterns()
    for name, script, _ in per_script:
        if script.match(ch):
            return name
    if common.match(ch):
        for name, _, extensions in per_script:
            if extensions.match(ch):
                return name
        return None
    return "Other"


@dataclass(frozen=True)
class ScriptProfile:
    """What profile() found in one string.

    ``counts`` maps each script to its number of letters, with Hiragana and
    Katakana merged as "Kana". ``dominant`` is the script with the most
    letters (None when there are none). ``share`` is the dominant script's
    fraction of all letters, except that with kana present it is the
    kana-plus-Han fraction, because Japanese mixes the two. ``letters`` is
    the letter count; ``tokens`` is the word count, or the letter count for
    an unspaced dominant script (see UNSPACED). ``has_kana`` is True when any
    kana is present."""

    counts: dict[str, int]
    dominant: str | None
    share: float
    letters: int
    tokens: int
    has_kana: bool

    @property
    def is_latin(self) -> bool:
        return self.dominant == "Latin"

    @property
    def is_mixed(self) -> bool:
        return len(self.counts) > 1

    @property
    def script_key(self) -> str | None:
        """Kana wins over Han: any kana means Japanese text, while Han alone
        may be Chinese, Japanese or Korean."""
        if self.has_kana:
            return "Kana"
        return self.dominant


def profile(text: str) -> ScriptProfile:
    """Profile the scripts of ``text`` (NFKC-normalised first, so full-width
    Latin counts as Latin). ``None`` or ``''`` gives an empty profile
    (no letters, ``dominant`` None, ``share`` 0.0). Raises ImportError when
    the ``[scripts]`` extra is absent."""
    text = unicodedata.normalize("NFKC", text or "")
    counts: Counter[str] = Counter()
    for ch in text:
        s = char_script(ch)
        if s is not None:
            counts[s] += 1
    has_kana = bool(counts.get("Hiragana") or counts.get("Katakana"))
    if has_kana:
        counts["Kana"] = counts.pop("Hiragana", 0) + counts.pop("Katakana", 0)
    letters = sum(counts.values())
    dominant, top = (counts.most_common(1)[0] if counts else (None, 0))
    if has_kana:
        # Japanese is written in kana AND kanji, so the share that says "this
        # is Japanese" counts both ('七人の侍' is 1.0, not 0.25).
        top = counts["Kana"] + counts.get("Han", 0)
    return ScriptProfile(
        counts=dict(counts),
        dominant=dominant,
        share=(top / letters) if letters else 0.0,
        letters=letters,
        tokens=_token_count(text, dominant),
        has_kana=has_kana,
    )


def _token_count(text: str, dominant: str | None) -> int:
    if dominant in UNSPACED or dominant == "Kana":
        return sum(1 for ch in text if char_script(ch) is not None)
    rx = _regex()
    return len([w for w in rx.split(r"[\s\p{P}\p{S}]+", text) if rx.search(r"\p{L}", w)])


def is_non_latin(text: str, min_share: float = 0.5) -> bool:
    """True when fewer than ``min_share`` of the letters are Latin. A string
    with no letters at all ('2046') is False. Raises ImportError when the
    ``[scripts]`` extra is absent."""
    p = profile(text)
    if not p.letters:
        return False
    return p.counts.get("Latin", 0) / p.letters < min_share
