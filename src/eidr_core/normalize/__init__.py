"""
Normalisation primitives.

Practical, dependency-light normalisation for v0.1. Hooks are left for heavier
treatment later (full transliteration, multilingual article lists, a real number
thesaurus). The goal is to neutralise harmless cross-source variation BEFORE
fuzzy comparison, not to be exhaustive.
"""
import re
import unicodedata

from .aliases import alias_title, alias_name

# EIDR country code-set crosswalk (SU→SUHH, …), single-homed in eidr_core so
# eidr-wikidata and BMR-Review share ONE map (register R1 / OVERLAPS.md 9a).
# Exposed here as canon_country: uppercase-canonical, preserves "XX",
# empty→"". Used by cmp_countries (via norm_country) and the Series gate.
from eidr_core.codes import normalize_country_code as canon_country

# Leading articles to strip (extend per-language as needed).
_ARTICLES = {
    "the", "a", "an",            # en
    "le", "la", "les", "l", "un", "une", "des",   # fr
    "el", "los", "las", "una",   # es
    "der", "die", "das", "ein", "eine",           # de
    "il", "lo", "gli", "i",      # it
}

_ROMAN = {
    "i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7,
    "viii": 8, "ix": 9, "x": 10, "xi": 11, "xii": 12,
}
_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
}


def nfkc(s: str) -> str:
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


def ascii_fold(s: str) -> str:
    """Fold Latin diacritics and ligatures to ASCII (é->e, ø->o, æ->ae, ß->ss)
    so they don't count as differences. Non-Latin scripts (CJK, Cyrillic, ...)
    are left intact so they still compare against each other."""
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


def norm_title(s: str, strip_articles: bool = True) -> str:
    if not s:
        return ""
    s = ascii_fold(nfkc(s)).casefold()
    s = re.sub(r"[\u2018\u2019\u201c\u201d]", "'", s)
    s = re.sub(r"[&+]", " and ", s)                      # &/+ -> and
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)   # drop punctuation
    toks = [alias_title(_num_token(t)) for t in s.split()]
    if strip_articles and len(toks) > 1 and toks[0] in _ARTICLES:
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
    s = re.sub(r"[&+]", " and ", s.casefold())
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    toks = [alias_name(_num_token(t)) for t in s.split()]
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
    'en-US' -> 'en', 'zh-Hans' -> 'zh'. Wildcards/unknown -> ''."""
    c = norm_code(s)
    return c.split("-", 1)[0] if c else ""


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
    'YYYY-MM-DD', and slash formats 'M/D/YYYY' (US) / 'D/M/YYYY'."""
    if raw is None:
        return None, None
    s = str(raw).strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        y, mo, d = int(m[1]), int(m[2]), int(m[3])
        return y, (y, mo, d)
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", s)
    if m:
        a, b, y = int(m[1]), int(m[2]), int(m[3])
        # US M/D/Y by default; swap when the first field can't be a month
        mo, d = (a, b) if a <= 12 else (b, a)
        if mo > 12:            # both >12 shouldn't happen; clamp safely
            mo, d = d, mo
        try:
            from datetime import date
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
    from datetime import date
    return abs((date(*a_ymd) - date(*b_ymd)).days)


# --- duration --------------------------------------------------------------
_ISO_DUR = re.compile(
    r"P(?:(?P<d>\d+)D)?T?(?:(?P<h>\d+)H)?(?:(?P<m>\d+)M)?(?:(?P<s>\d+)S)?", re.I)


def parse_minutes(raw):
    """Parse '78', 'PT1H18M', '01:18:00' -> minutes (float) or None."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    if s.upper().startswith("P"):
        m = _ISO_DUR.match(s.upper())
        if m and any(m.group(k) for k in ("d", "h", "m", "s")):
            d = int(m.group("d") or 0); h = int(m.group("h") or 0)
            mi = int(m.group("m") or 0); se = int(m.group("s") or 0)
            return d * 1440 + h * 60 + mi + se / 60.0
    if ":" in s:                       # timecode HH:MM:SS(:FF)
        parts = s.split(":")
        try:
            h, mi = int(parts[0]), int(parts[1])
            se = int(parts[2]) if len(parts) > 2 else 0
            return h * 60 + mi + se / 60.0
        except ValueError:
            return None
    try:
        return float(s)                # bare minutes
    except ValueError:
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
    - Strip leading/trailing whitespace
    - Remove NUL bytes (PostgreSQL rejects them outright)
    - Replace tabs / CR / LF with spaces (they would break TSV, and COPY
      handles some but not all of them on its own)
    - Replace every remaining C0 control character except space with a space,
      so nothing invisible survives into the output

    Extracted from EIDR MCP ``reset_alt_ids.py::_sanitize_field`` (register R6,
    2026-08-06) — the fuller of that repo's two copies, and the canonical
    behaviour. EXTRACT-ONLY: MCP keeps its own copies under the standing
    "not ported unless it independently needs a major update" decision, so
    this exists for NEW consumers and for the eventual port, not as a shim
    MCP imports today.

    NOTE for the MCP thread: the two copies had already drifted when this was
    extracted. ``shortdoi_audit.py``'s copy does only the strip-and-replace
    half — no NUL removal, no C0 sweep — and that script writes TSV, so a
    control character in registry XML can reach its output and break a
    downstream parse. This function is the behaviour to converge on.
    """
    if s is None:
        return ""
    s = str(s).strip()
    if not s:
        return ""
    s = s.replace("\x00", "")
    s = s.replace("\t", " ").replace("\r", " ").replace("\n", " ")
    return "".join(" " if (ord(ch) < 0x20 and ch != " ") else ch for ch in s)
