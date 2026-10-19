"""
Normalisation primitives.

Practical, dependency-light normalisation for v0.1. Hooks are left for heavier
treatment later (full transliteration, multilingual article lists, a real number
thesaurus). The goal is to neutralise harmless cross-source variation BEFORE
fuzzy comparison, not to be exhaustive.
"""
import math
import re
import unicodedata
from datetime import date
from typing import overload

# EIDR country code-set crosswalk (SU→SUHH, …), single-homed in eidr_core so
# eidr-wikidata and BMR-Review share ONE map (register R1 / OVERLAPS.md 9a).
# Exposed here as canon_country: uppercase-canonical, preserves "XX",
# empty→"". Used by cmp_countries (via norm_country) and the Series gate.
from eidr_core.codes import normalize_country_code as canon_country

from .aliases import alias_name, alias_title

# The public surface, as DICTIONARY.md documents it (2026-10-02).
# Star-imports (BMR-Review's shims use them) now take only these names,
# not the stdlib and third-party modules this file imports.
__all__ = [
    "ascii_fold",
    "canon_country",
    "cmp_key",
    "days_between",
    "nfkc",
    "norm_code",
    "norm_country",
    "norm_lang",
    "norm_name",
    "norm_title",
    "parse_date",
    "parse_minutes",
    "parse_registrant_extra",
    "sanitize_field",
]

# Leading articles to strip (extend per-language as needed).
_ARTICLES = {
    "the", "a", "an",            # en
    "le", "la", "les", "l", "un", "une", "des",   # fr
    "el", "los", "las", "una",   # es
    "der", "die", "das", "ein", "eine",           # de
    "il", "lo", "gli", "i",      # it
}

# Words that may follow the Italian plural article "i" without ending in -i
# themselves: the cardinal numbers and "piu" (ascii-folded "più"). See
# _is_leading_article for why "i" needs a follower test at all.
_IT_I_FOLLOWERS = {
    "due", "tre", "quattro", "cinque", "sette", "otto", "nove", "cento",
    "mille", "piu",
}

_ROMAN = {
    "i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7,
    "viii": 8, "ix": 9, "x": 10, "xi": 11, "xii": 12,
}
_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
}


# Overloads, not a bare ``-> str | None`` (dictionary audit 2026-10-02;
# 0.68.0): ``None`` passes through as ``None``, which the old ``-> str``
# annotation hid, but a str caller -- nearly all of them -- must keep a
# ``str`` result without a cast.
@overload
def nfkc(s: str) -> str: ...
@overload
def nfkc(s: None) -> None: ...
def nfkc(s: str | None) -> str | None:
    """NFKC-normalise ``s``. ``None`` and ``""`` come back unchanged; a
    non-str value is stringified first."""
    if s is None or s == "":
        return s
    if not isinstance(s, str):
        s = str(s)                      # numeric titles/episode numbers arrive as int
    return unicodedata.normalize("NFKC", s)


# Ligatures / special letters that do NOT decompose under NFKD.
_LIGATURES = {
    "æ": "ae", "Æ": "AE", "œ": "oe", "Œ": "OE", "ø": "o", "Ø": "O",
    "ß": "ss", "þ": "th", "Þ": "Th", "ð": "d", "Ð": "D", "đ": "d", "Đ": "D",
    "ł": "l", "Ł": "L", "ŋ": "ng", "ı": "i", "İ": "I", "ĳ": "ij", "Ĳ": "IJ",
    "ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl", "ﬆ": "st",
}


@overload
def ascii_fold(s: str) -> str: ...
@overload
def ascii_fold(s: None) -> None: ...
def ascii_fold(s: str | None) -> str | None:
    """Fold Latin diacritics and ligatures to ASCII (é->e, ø->o, æ->ae, ß->ss)
    so they don't count as differences. ``None`` and ``""`` come back
    unchanged.

    Non-Latin letters (CJK, Cyrillic, ...) are kept, so they still compare
    against each other -- but they lose their combining marks too (が->か,
    й->и, Ё->Е), so diacritic differences INSIDE those scripts are ignored
    as well. (The docstring said "left intact" until the dictionary audit
    2026-10-02; the code has always stripped every combining mark.)"""
    if not s:
        return s
    s = "".join(_LIGATURES.get(ch, ch) for ch in s)
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


def cmp_key(s: str) -> str:
    """Canonical comparison key: ASCII-folded, case-folded (Unicode casefold,
    matching the XML-to-JSON converter), with spaces,
    punctuation and underscores removed. Equal keys are treated as a match."""
    if not s:
        return ""
    return re.sub(r"[\W_]+", "", ascii_fold(s).casefold(), flags=re.UNICODE)


def _num_token(tok: str) -> str:
    """Fold roman/word numerals to digits so 'Part II' == 'Part 2' == 'Part Two'."""
    low = tok.casefold()
    if low in _ROMAN:
        return str(_ROMAN[low])
    if low in _WORDS:
        return str(_WORDS[low])
    return tok


def _tokens_around_ampersands(s: str, alias) -> tuple[list[str], bool, list[str]]:
    """Tokenise ``s`` with ``&``/``+`` read as "and", folding numerals and
    aliasing words -- EXCEPT the single letters that sit beside an
    ampersand, and a name that is one letter long.

    Why (python-tools, 2026-09-12): the old order was "replace & with and,
    then alias every token", and the alias tables map the Romance
    conjunctions ``e``/``y`` to "and" and the Roman numerals
    ``i``/``v``/``x`` to digits. So ``A&E Networks`` became
    ``a and and networks``, ``V&A`` became ``5 and a`` and ``X&Y`` became
    ``10 and and`` -- and ``A&E Television Networks`` is a real production
    party (10.5237/DF2A-52D3). A letter beside an ampersand is an initial,
    never a conjunction or a numeral. Everything else is aliased exactly as
    before, so ``Juan y Maria`` still reads "john and mary" and
    ``Simon & Schuster`` still reads "simon and schuster".

    Returns the tokens, whether the FIRST token is such an initial (so
    ``norm_title`` does not strip the ``A`` of ``A&E`` as an article), and
    the same tokens BEFORE numeral and alias folding, position for position,
    so ``norm_title`` can test the first word as it was written (operator
    ruling 2026-10-19; 0.69.0).
    """
    bare = s.strip()
    if len(bare) == 1 and bare.isalpha():
        return [bare], True, [bare]                     # a one-letter name
    parts = re.split(r"[&+]", s)
    out: list[str] = []
    raw: list[str] = []
    first_initial = False
    for i, part in enumerate(parts):
        words = re.sub(r"[^\w\s]", " ", part, flags=re.UNICODE).split()
        for j, w in enumerate(words):
            beside_amp = (j == 0 and i > 0) or (j == len(words) - 1 and i < len(parts) - 1)
            if beside_amp and len(w) == 1 and w.isalpha():
                if not out:
                    first_initial = True
                out.append(w)                          # an initial: verbatim
            else:
                out.append(alias(_num_token(w)))
            raw.append(w)
        if i < len(parts) - 1:
            out.append("and")
            raw.append("and")
    return out, first_initial, raw


def _is_leading_article(raw: list[str], s: str) -> bool:
    """Is the first word of a title, AS WRITTEN, a leading article?

    Tested on the raw word, before numeral and alias folding (operator
    ruling 2026-10-19; 0.69.0). Folding ran first until then, so two
    entries of ``_ARTICLES`` could never match: Italian ``i`` became the
    numeral ``1`` and ``lo`` became ``low`` (word_alias.csv row 270), and
    'I promessi sposi' normalised to '1 promessi sposi' while 'Promessi
    sposi' stayed 'promessi sposi'. No other article is changed by folding,
    and no folded word lands on an article, so for every other entry the
    order makes no difference.

    ``i`` gets one extra test, because it is also the English pronoun and
    the Roman numeral one. Stripping it everywhere would make 'I Spy' and
    'Spy' (two different films) normalise identically and empty half of
    'I Am Sam'. ``norm_title`` has no language to consult, so the test is
    the Italian grammar itself: the masculine plural article is followed by
    a plural, which ends in -i ('I promessi sposi', 'I soliti ignoti', 'I
    Pagliacci'), or by a cardinal number or "più" ('I due Foscari', 'I tre
    moschettieri'), and never by punctuation ('I, Robot', "I'm"). English
    titles almost never meet that: 'I Love Lucy', 'I, Robot' and 'I Spy'
    keep folding to '1 love lucy', '1 robot' and '1 spy' exactly as before.
    Measured on the mirror's 5.0M content_titles (2026-10-19): of 31018
    titles that start with 'I', 2244 now lose it -- 1751 tagged Italian,
    164 Greek (the transliterated feminine article, so stripping it is
    right too), 145 Corsican (mostly opera titles), 72 English, nearly all
    of them Italian or Greek titles under the wrong tag. The rule misses
    about 1 in 40 Italian-tagged ones (loanwords: 'I babysitter'). Known
    false positives outside Italian and Greek: 'I Heidi Take Thee
    Spencer...', 'I Rossellini, D Arquette, Cake' (an initial), and a few
    romanised Chinese and Korean titles ('I Shi Chu Nu Zuo').
    """
    first = raw[0]
    if first != "i":
        return first in _ARTICLES
    if re.match(r"\s*i\s*[^\w\s]", s):
        return False                    # 'I, Robot', "I'm", 'I.' -- never an article
    nxt = raw[1]
    return (len(nxt) > 1 and nxt.isalpha() and nxt.endswith("i")) or nxt in _IT_I_FOLLOWERS


def norm_title(s: str, strip_articles: bool = True) -> str:
    """Normalise a title for comparison: NFKC, ASCII fold, casefold, ``&``/``+``
    read as "and", Roman and spelled numerals folded to digits, word aliases
    applied, and (``strip_articles``) one leading article dropped.

    The article test looks at the first word as written, before folding, so
    Italian ``lo`` and ``i`` are stripped ('Lo Hobbit' -> 'hobbit', 'I
    promessi sposi' -> 'promessi sposi'); a leading ``i`` counts as an
    article only when an Italian plural follows it, so English 'I Love
    Lucy' stays '1 love lucy' (operator ruling 2026-10-19; 0.69.0; the rule
    is in _is_leading_article). A one-word title is never stripped, nor a
    first letter that is an initial beside an ampersand ('A&E')."""
    if not s:
        return ""
    s = ascii_fold(nfkc(s)).casefold()
    s = re.sub(r"[\u2018\u2019\u201c\u201d]", "'", s)
    toks, first_initial, raw = _tokens_around_ampersands(s, alias_title)
    if (strip_articles and len(toks) > 1 and not first_initial
            and _is_leading_article(raw, s)):
        toks = toks[1:]
    return " ".join(toks).strip()


def norm_name(s: str) -> str:
    """Normalise a personal/org name; invert 'Last, First' -> 'first last'."""
    if not s:
        return ""
    s = ascii_fold(nfkc(s)).strip()
    if "," in s and s.count(",") == 1:
        last, first = [p.strip() for p in s.split(",", 1)]
        if first:
            s = f"{first} {last}"
    toks, _, _ = _tokens_around_ampersands(s.casefold(), alias_name)
    return " ".join(toks).strip()


def norm_code(s: str) -> str:
    """Country/language code normaliser. Returns '' for wildcard/unknown."""
    if not s:
        return ""
    c = nfkc(s).strip().casefold()
    if c in {"xx", "und", "zz", "none", "null"}:   # XX/und => treated as absent
        return ""
    return c


def norm_country(s: str) -> str:
    """Country-code normaliser for field comparison: norm_code() (casefold,
    drops XX/wildcards) plus the obsolete alpha-2 -> alpha-4 crosswalk, so
    code-set variants of one country compare equal. Deliberately NOT folded
    into norm_code(): that is shared with language codes, and 'su' is the
    language Sundanese, not the USSR."""
    c = norm_code(s)
    if not c:
        return ""
    return canon_country(c).casefold()


def norm_lang(s: str) -> str:
    """Language code: keep only the primary subtag (left of the first hyphen).
    'en-US' -> 'en', 'zh-Hans' -> 'zh'. Wildcards/unknown -> ''.

    The wildcard test is norm_code's (xx, und, zz, none, null) and runs on
    the primary subtag, so 'und-Latn' and 'xx-YY' are dropped exactly as
    'und' and 'xx' are. ``zxx`` (no linguistic content) and ``mul``
    (multiple languages) are real codes here, not wildcards."""
    if not s:
        return ""
    # Trim to the primary subtag FIRST, then apply the wildcard test
    # (operator ruling 2026-10-19; 0.69.0). The test used to run on the
    # whole tag, so only a bare 'und' was dropped: 'und-Latn' came back as
    # 'und' and 'xx-YY' as 'xx' -- an "unknown" language that then compared
    # equal to another unknown instead of being treated as absent.
    return norm_code(nfkc(s).strip().split("-", 1)[0])


def parse_registrant_extra(raw):
    """Parse Registrant Extra flags. Returns (length_estimated, date_estimated).
    AL:Pro => approximate length estimated; RD:Pro => release date estimated."""
    if not raw:
        return False, False
    s = str(raw).lower()
    return ("al:pro" in s), ("rd:pro" in s)


# --- dates -----------------------------------------------------------------
def parse_date(raw):
    """Return (year:int|None, ymd:tuple|None). Handles 'YYYY', 'YYYY-MM',
    'YYYY-MM-DD' (anything after the day is ignored), and slash formats
    'M/D/YYYY' (US) / 'D/M/YYYY'. A slash date is read M/D; D/M order applies
    only when the first field is over 12.

    ``ymd`` is set only for a full date that exists on the calendar. An
    impossible one ('2006-13-45', '2006-02-30', '2/30/2006') keeps its year
    and gets ``ymd=None``, exactly as a year-only date does, so callers that
    do arithmetic on ``ymd`` (days_between) never see it."""
    if raw is None:
        return None, None
    s = str(raw).strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        y, mo, d = int(m[1]), int(m[2]), int(m[3])
        # Validated like the slash branch below (dictionary audit 2026-10-02;
        # 0.68.0). Unvalidated, '2006-13-45' came back as a full date and
        # days_between raised ValueError inside compare.cmp_release_date,
        # which does not catch it -- one malformed registry date failed the
        # whole comparison. The year is still good evidence, so keep it.
        try:
            date(y, mo, d)
        except ValueError:
            return y, None
        return y, (y, mo, d)
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", s)
    if m:
        a, b, y = int(m[1]), int(m[2]), int(m[3])
        # US M/D/Y by default; swap when the first field can't be a month
        mo, d = (a, b) if a <= 12 else (b, a)
        if mo > 12:            # both >12 shouldn't happen; clamp safely
            mo, d = d, mo
        try:
            date(y, mo, d)
            return y, (y, mo, d)
        except ValueError:
            return y, None
    m = re.match(r"^(\d{4})$", s)
    if m:
        return int(m[1]), None
    m = re.match(r"^(\d{4})-(\d{2})$", s)
    if m:
        return int(m[1]), None
    return None, None


def days_between(a_ymd, b_ymd):
    return abs((date(*a_ymd) - date(*b_ymd)).days)


# --- duration --------------------------------------------------------------
# Every pattern below is matched WHOLE (fullmatch). The 0.68 pattern was
# matched from the start only and took whole numbers only, so a valid
# 'PT1H18M30.5S' stopped at '30' and silently returned 78.0, and 'PT24.4S'
# matched nothing at all (operator ruling 2026-10-19; 0.69.0: anything that
# is not a whole valid form returns None, never a partial parse).
_DUR_NUM = r"\d+(?:[.,]\d+)?"          # ISO decimal sign is comma or dot
# ISO 8601 designator format: PnYnMnWnDTnHnMnS, every component optional but
# at least one present, and a T only when a time component follows it.
_ISO_DUR = re.compile(
    rf"P(?:(?P<y>{_DUR_NUM})Y)?(?:(?P<mo>{_DUR_NUM})M)?(?:(?P<w>{_DUR_NUM})W)?"
    rf"(?:(?P<d>{_DUR_NUM})D)?"
    rf"(?:T(?:(?P<h>{_DUR_NUM})H)?(?:(?P<mi>{_DUR_NUM})M)?(?:(?P<s>{_DUR_NUM})S)?)?",
    re.I)
_ISO_PARTS = ("y", "mo", "w", "d", "h", "mi", "s")
_ISO_MINUTES = {"w": 10080.0, "d": 1440.0, "h": 60.0, "mi": 1.0, "s": 1 / 60.0}
# ISO 8601 alternative format, extended (P0000-00-01T01:18:00) or basic
# (P00000001T011800).
_ISO_DUR_ALT = re.compile(
    r"P(?P<y>\d{4})(?P<sep>-?)(?P<mo>\d{2})(?P=sep)(?P<d>\d{2})"
    r"T(?P<h>\d{2})(?P<tsep>:?)(?P<mi>\d{2})(?P=tsep)(?P<s>\d{2}(?:[.,]\d+)?)",
    re.I)
# Timecode: H:MM:SS, optionally fractional seconds or a frame count after ':'
# or ';' (drop-frame); or two-part M:SS (fractional seconds allowed). Hours
# and minutes-of-M:SS are unbounded; the fields after them must be 0-59.
_TIMECODE = re.compile(
    r"(?P<a>\d+):(?P<b>\d{1,2}(?:\.\d+)?)(?::(?P<c>\d{1,2}(?:\.\d+)?)(?:[:;]\d+)?)?")


def _dur_num(v: str) -> float:
    return float(v.replace(",", "."))


def parse_minutes(raw):
    """Parse a runtime into minutes (float), or None.

    Accepted (operator ruling 2026-10-19; 0.69.0 -- "handle unusual but
    valid situations"):

    - Bare minutes: ``'78'``, ``78``, ``'90.5'`` (anything ``float()``
      reads that is finite and not negative).
    - ISO 8601 durations, designator format: ``'PT1H18M'``, ``'P1DT2H'``,
      ``'PT1H18M30.5S'``, ``'PT30,5S'``, ``'P2W'``, ``'P1W2D'``, ``'PT0S'``,
      case-insensitive. A week is 10080 minutes and a day 1440. A decimal
      fraction (comma or dot) is allowed on the LAST component only, as ISO
      requires ('PT1.5H' -> 90.0; 'PT1.5H30M' -> None). Years and months are
      not a fixed number of minutes, so a non-zero Y or M date component
      returns None: ``'P78M'`` is 78 MONTHS in ISO and gives None (it read
      as 78 minutes until 0.69.0). Zero ones are accepted ('P0Y0M1D').
      Weeks combined with other components (ISO 8601-2) are accepted, being
      unambiguous.
    - ISO 8601 alternative format with zero years and months:
      ``'P0000-00-00T01:18:00'``, ``'P00000000T011800'``; hours below 24,
      minutes and seconds below 60.
    - Timecode ``H:MM:SS`` (``'01:18:00'``, ``'1:18:30.5'``), with a frame
      count after ``:`` or ``;`` ignored (``'01:18:00:12'``,
      ``'01:18:00;12'``). Minutes and seconds must be 0-59.
    - Two-part ``M:SS`` is MINUTES:SECONDS: ``'78:30'`` -> 78.5,
      ``'1:30'`` -> 1.5. It was read as H:MM until 0.69.0 ('78:30' ->
      4710.0). M:SS is how XML_to_JSON's ApproximateLength converter reads
      the same cell (``_format_xs_duration``: 'HH:MM:SS' or 'MM:SS'), so a
      sheet value and the duration registered from it compare equal; the
      mirror's ``length_timecode`` is always three-part, and an Excel
      time-formatted cell arrives three-part too.

    Everything else -- including any string that only STARTS like one of
    these, a negative or non-finite number, and ``None`` or ``''`` --
    returns None, never a partial parse.
    """
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        # Numbers directly, not via str(): str(1e-05) is '1e-05', and a
        # float's repr is no business of the string grammar below.
        v = float(raw)
        return v if math.isfinite(v) and v >= 0 else None
    s = str(raw).strip()
    if not s:
        return None
    if s[0] in "Pp":
        return _parse_iso_duration(s)
    if ":" in s:
        m = _TIMECODE.fullmatch(s)
        if not m:
            return None
        a, b, c = m["a"], m["b"], m["c"]
        if c is None:                   # two-part M:SS
            sec_f = float(b)
            return int(a) + sec_f / 60.0 if sec_f < 60 else None
        if not b.isdigit():
            return None                 # '1:18.5:00': only seconds take a fraction
        mi, sec_f = int(b), float(c)
        if mi >= 60 or sec_f >= 60:
            return None
        return int(a) * 60 + mi + sec_f / 60.0
    try:
        v = float(s)                    # bare minutes
    except ValueError:
        return None
    # 'nan', 'inf' and '-5' all parse as floats; none is a runtime.
    return v if math.isfinite(v) and v >= 0 else None


def _parse_iso_duration(s: str) -> float | None:
    """The ISO 8601 half of parse_minutes; None unless ``s`` is one whole
    valid duration that a fixed number of minutes can express."""
    m = _ISO_DUR.fullmatch(s)
    if m:
        present = [k for k in _ISO_PARTS if m[k] is not None]
        if not present:
            return None                 # bare 'P'
        if "t" in s.casefold() and not any(m[k] is not None for k in ("h", "mi", "s")):
            return None                 # 'P1DT': a T must introduce a time
        if any(not m[k].isdigit() for k in present[:-1]):
            return None                 # a fraction on a component that is not the last
        if any(_dur_num(m[k]) for k in ("y", "mo") if m[k] is not None):
            return None                 # years/months: no fixed length
        return sum((_dur_num(m[k]) * _ISO_MINUTES[k] for k in present if k in _ISO_MINUTES), 0.0)
    m = _ISO_DUR_ALT.fullmatch(s)
    if m:
        if int(m["y"]) or int(m["mo"]):
            return None
        h, mi, sec = int(m["h"]), int(m["mi"]), _dur_num(m["s"])
        if h >= 24 or mi >= 60 or sec >= 60:
            return None
        return int(m["d"]) * 1440 + h * 60 + mi + sec / 60.0
    return None


# ---------------------------------------------------------------------------
# Transport safety (distinct from the comparison normalisers above)
# ---------------------------------------------------------------------------
# Everything above neutralises harmless variation BEFORE fuzzy comparison and
# is lossy by design (case, articles, punctuation all go). ``sanitize_field``
# is a different job: make a value SAFE TO CARRY through a delimited or
# database transport without changing what it says. Apply it last, on the way
# out — never as the basis for a comparison.

def sanitize_field(s) -> str:
    """Normalise a text field for bulk loading or delimited output.

    - ``None`` and whitespace-only become ``""``
    - Remove NUL bytes (PostgreSQL rejects them outright)
    - Replace tabs / CR / LF with spaces (they would break TSV, and COPY
      handles some but not all of them on its own)
    - Replace every remaining C0 control character except space with a space,
      so nothing invisible survives into the output
    - THEN strip leading/trailing whitespace, so a space that replaced an
      edge control character goes too (``'a\\t'`` -> ``'a'``)

    DEL (0x7F) and C1 controls (0x80-0x9F) are deliberately left alone
    (eidr-wikidata pins that they pass through), except where ``str.strip``
    already treats one as whitespace at an edge (U+0085).

    Extracted from EIDR MCP ``reset_alt_ids.py::_sanitize_field`` (register R6,
    2026-08-06) — the fuller of that repo's two copies, and the canonical
    behaviour. EXTRACT-ONLY: MCP keeps its own copies under the standing
    "not ported unless it independently needs a major update" decision, so
    this exists for NEW consumers and for the eventual port, not as a shim
    MCP imports today.

    The two MCP copies had drifted when this was extracted
    (``shortdoi_audit.py``'s lacked the NUL removal and C0 sweep); they were
    converged on 2026-08-26, and MCP's
    ``tests/test_schema_contract.py::test_the_three_sanitize_field_copies_agree``
    now pins all three to each other. A behaviour change here therefore
    means the same edit to both MCP copies (done for the 0.68.0
    strip-last change).
    """
    if s is None:
        return ""
    # Replace first, strip LAST (dictionary audit 2026-10-02; 0.68.0). The
    # old order stripped first, so an edge tab or control character was
    # turned into a space AFTER the strip had run: 'a\t' -> 'a ' and
    # '\ta' -> ' a', leaving padding the docstring promised was gone.
    s = str(s).replace("\x00", "")
    s = s.replace("\t", " ").replace("\r", " ").replace("\n", " ")
    s = "".join(" " if (ord(ch) < 0x20 and ch != " ") else ch for ch in s)
    return s.strip()
