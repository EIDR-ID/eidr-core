"""Title matching — THE shared implementation (eidr_core.compare.titles).

Updated 2026-08-05 from the BMR-Review engine cycle: multi-language part
words (Teil/partie/parte/del/osa/Folge…), postfix and mid-title part
numbering, bare trailing numbers (Rocky 2), and select_titles internal-
as-fallback semantics. Consumed by eidr_core.compare.cmp_titles and
BMR-Review's scorer — keep single-homed HERE (the local BMR-Review
titles.py is a shim).

Original module docstring follows (merged into this one literal so the
imports below are genuinely module-top).

Title matching with episode-aware rules.

  * Part numbering is *distinguishing*: "Show, Part 1" vs "Show, Part 2"
    (and "Show 1 of 2", "Show (Pt. II)", ...) are DIFFERENT works -- same base,
    different part -> near-zero title match. Same base + same part -> match.
  * Segment titles are *order-independent*: "Segment A / Segment B" matches
    "Segment B / Segment A" (the multiset of segments is what matters), but a
    single "Segment A" only partially matches "Segment A / Segment B".
  * System-generated titles are ignored when real titles exist on both sides,
    and used only as a last resort.
  * Internal-class titles (system-generated machine translations) are, by
    default, treated like system-generated ones: used only as a fallback.
    When the registered parameters carry INTERNAL_TITLE_DISCOUNT they are
    included instead, at a discount (``select_titles(include_internal=True)``
    here; the discount itself is applied in ``compare.cmp_titles``).

Part/segment rules apply to all creation types (part numbering shows up in
non-episodic titles too); system-generated filtering is most relevant to
episodes.
"""
import re

from rapidfuzz import fuzz

from eidr_core.normalize import norm_title

# The public surface, as DICTIONARY.md documents it (2026-10-02).
# Star-imports (BMR-Review's shims use them) now take only these names,
# not the stdlib and third-party modules this file imports.
__all__ = [
    "fuzzy",
    "COMBINATION_DIFFERS_QUALITY",
    "PART_AMBIGUOUS_QUALITY",
    "date_tokens",
    "dates_ambiguous",
    "is_internal",
    "parse_part",
    "parts_ambiguous",
    "parts_conflict",
    "segments",
    "select_titles",
    "title_similarity",
]

_ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7,
          "viii": 8, "ix": 9, "x": 10, "xi": 11, "xii": 12}
_SPELLED = {w: i for i, w in enumerate(
    ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
     "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
     "sixteen", "seventeen", "eighteen", "nineteen", "twenty"])}
_ORDINAL = {w: i + 1 for i, w in enumerate(
    ["first", "second", "third", "fourth", "fifth", "sixth", "seventh",
     "eighth", "ninth", "tenth", "eleventh", "twelfth"])}

_NUM_TOKEN = (r"(?:[0-9]{1,2}(?:st|nd|rd|th)?|[ivx]{1,4}|"
              + "|".join(list(_SPELLED)[1:] + list(_ORDINAL)) + r")")

# "part" in several languages (Teil = German, partie = French, etc.)
_PART_WORD = (r"(?:part|pt|teil|partie|parte|deel|del|dele|chapter|ch|chapitre"
              r"|kapitel|capitulo|episode|episodio|episode|folge|avsnitt|osa"
              r"|book|vol|volume)")
_PART = re.compile(
    r"^(.*?)[\s,:;.\-]+" + _PART_WORD + r"\.?\s*(" + _NUM_TOKEN + r")\s*$", re.I)
# Nordic/postfix form: the number precedes the part word ("3. del", "2. Del",
# "3 osa"). The ordinal dot after the digit is optional.
_PART_POST = re.compile(
    r"^(.*?)[\s,:;.\-]+(" + _NUM_TOKEN + r")\.?\s*" + _PART_WORD + r"\s*$", re.I)
# Mid-title numbering: the part number sits between the base and a subtitle
# ("Miserabili 2: Tempesta su Parigi", "Kampf um Rom II - Der Verrat"). Only
# 1-2 digit or roman tokens qualify (years never match), and both a base and a
# subtitle must be present.
_PART_MID = re.compile(r"^(.*?\S)\s+([0-9]{1,2}|[ivx]{1,4})\s*[:\-\u2013\u2014]\s+\S.+$", re.I)
# "... 2 of 3", "... (1 of 2)"
_PART_OF = re.compile(r"^(.*?)[\s,:;.\-]*\(?\b([0-9]+)\s+of\s+([0-9]+)\)?\s*$", re.I)
# bare trailing number, no part word: "Rocky 2", "Rocky II", "Ocean's Eight".
# 4-digit numbers are excluded (years); the base must be non-empty.
_BARE_NUM = re.compile(r"^(.*?\S)[\s\-–:]+(" + _NUM_TOKEN + r")\s*$", re.I)


def _to_int(tok):
    tok = tok.strip().casefold()
    if tok[-2:] in ("st", "nd", "rd", "th") and tok[:-2].isdigit():
        return int(tok[:-2])
    if tok.isdigit():
        return int(tok)
    if tok in _SPELLED:
        return _SPELLED[tok]
    if tok in _ORDINAL:
        return _ORDINAL[tok]
    return _ROMAN.get(tok)


def parse_part(raw, *, bare=True):
    """Return (base_normalised, part_index:int) or None. With ``bare`` (the
    default), a trailing number without a part word also counts ('Rocky 2',
    'Ocean's Eight'); 4-digit trailing numbers are treated as years, not
    parts."""
    if not raw:
        return None
    s = str(raw).strip()
    m = _PART_OF.match(s)
    if m:
        idx = _to_int(m.group(2))
        if idx is not None and m.group(1).strip():
            return norm_title(m.group(1)), idx
    m = _PART.match(s)
    if m:
        idx = _to_int(m.group(2))
        if idx is not None and m.group(1).strip():
            return norm_title(m.group(1)), idx
    m = _PART_POST.match(s)
    if m:
        idx = _to_int(m.group(2))
        if idx is not None and m.group(1).strip():
            return norm_title(m.group(1)), idx
    m = _PART_MID.match(s)
    if m:
        idx = _to_int(m.group(2))
        if idx is not None and m.group(1).strip():
            return norm_title(m.group(1)), idx
    if bare:
        m = _BARE_NUM.match(s)
        if m and not re.fullmatch(r"[0-9]{4}", m.group(2)):
            idx = _to_int(m.group(2))
            base = m.group(1).strip().rstrip(",:;.-")
            if idx is not None and base:
                return norm_title(base), idx
    return None


# Compound-title and part-number semantics (operator rulings, 2026-09-01).
COMBINATION_DIFFERS_QUALITY = 0.20   # a different set of segments is a different program
PART_AMBIGUOUS_QUALITY = 0.70        # numbered vs un-numbered: cannot reach Accept on title


# --- date tokens in Episode titles (0.77.0) ---------------------------------
# A daily programme puts the broadcast date in its title: "13/08/2026 - Quem
# Ama Nao Esquece". segments() splits on "/", so that title became three
# segments ("13", "08", "2026 quem ama nao esquece") and scored the
# combination-differs 0.20 against the registry's undated title, with the
# parent, date, number and length all matching (BMR-Review handoff of
# 2026-11-23: 44 audited rows, 3 closed as a no-match nobody saw). Not
# splitting digit/digit is not the fix: "07/09/2026 - X" against
# "08/09/2026 - X" would then score 0.97, two days of one programme read as
# one. So the date is recognised as a date and compared as one (operator
# approved 2026-11-23, Episode/Season pairs only). Enabled by
# title_similarity(dates=True); cmp_titles passes it when the registered
# parameters carry TITLE_DATE_TOKENS true.
_WEEKDAY = (r"(?:monday|mon|tuesday|tues|tue|wednesday|wed|thursday|thurs|thur"
            r"|thu|friday|fri|saturday|sat|sunday|sun)\.?")
# The two separators in a date must be the same character ("13/08/2026",
# "13.08.2026", "13-08-2026"), and nothing digit-like may touch the token, so
# "1.2.10" inside a longer number run or "9/11" (no year) never qualifies.
_YMD = re.compile(r"(?<![\d/.\-])(\d{4})([/.\-])(\d{1,2})\2(\d{1,2})(?![\d/.\-])")
_DMY = re.compile(r"(?<![\d/.\-])(\d{1,2})([/.\-])(\d{1,2})\2(\d{4}|\d{2})(?![\d/.\-])")
# Month/day after a weekday: "Mon, 6/16". Without the weekday, "6/16" is as
# likely a fraction or a segment pair as a date, so it is not taken.
_WD_MD = re.compile(r"\b" + _WEEKDAY + r",?\s+(\d{1,2})/(\d{1,2})(?![\d/])", re.I)
# A date written in brackets, "Show, Part 2 (13/08/2026)", leaves "()" behind.
_EMPTY_BRACKETS = re.compile(r"[(\[]\s*[)\]]")
_EDGE = re.compile(r"^[\s\-\u2013\u2014:|,./]+|[\s\-\u2013\u2014:|,./]+$")


def _plausible(a, b):
    # Day and month in either order (d/m or m/d): both at most 31, one at
    # most 12. A pair that cannot be a date is left in the title untouched.
    return 1 <= a <= 31 and 1 <= b <= 31 and min(a, b) <= 12


def date_tokens(raw):
    """``(dates, rest)``: the date tokens in a title, in order, and the title
    with them removed.

    Recognised: ``d/m/y``, ``d.m.y``, ``d-m-y`` (two- or four-digit year),
    ``y-m-d`` (any of the three separators), and ``m/d`` after a weekday
    (``Mon, 6/16``, the weekday removed with it). Each date is a tuple compared
    literally, never interpreted: ``('dmy', first, second, yy, yyyy)``, the
    year's last two digits and the four-digit year or None (``y-m-d``
    reordered to that shape, so ``2026-08-13`` equals ``13/08/2026``), or
    ``('md', month, day)``. ``rest`` has the separators left at its edges
    trimmed. A title with no date returns ``([], raw)``.
    """
    s = "" if raw is None else str(raw)
    found = []                    # (start, end, key)

    def _free(a, b):
        return all(b <= x or a >= y for x, y, _ in found)

    for m in _YMD.finditer(s):
        y, mo, d = int(m.group(1)), int(m.group(3)), int(m.group(4))
        if 1 <= mo <= 12 and 1 <= d <= 31 and _free(m.start(), m.end()):
            found.append((m.start(), m.end(), ("dmy", d, mo, y % 100, y)))
    for m in _DMY.finditer(s):
        a, b, y = int(m.group(1)), int(m.group(3)), m.group(4)
        if _plausible(a, b) and _free(m.start(), m.end()):
            found.append((m.start(), m.end(),
                          ("dmy", a, b, int(y) % 100, int(y) if len(y) == 4 else None)))
    for m in _WD_MD.finditer(s):
        mo, d = int(m.group(1)), int(m.group(2))
        if _plausible(mo, d) and _free(m.start(), m.end()):
            found.append((m.start(), m.end(), ("md", mo, d)))
    if not found:
        return [], s
    found.sort()
    rest, last = [], 0
    for a, b, _ in found:
        rest.append(s[last:a])
        last = b
    rest.append(s[last:])
    joined = _EMPTY_BRACKETS.sub(" ", " ".join(p.strip() for p in rest if p.strip()))
    return [k for _, _, k in found], _EDGE.sub("", " ".join(joined.split()))


def _same_date(x, y):
    """Literal equality of two date keys. A two-digit year equals a
    four-digit one with the same last two digits (the century is not
    guessed); a month/day equals only another month/day, since d/m against
    m/d cannot be told apart."""
    if x[0] != y[0]:
        return False
    if x[0] == "md":
        return x == y
    if x[1:4] != y[1:4]:
        return False
    return x[4] is None or y[4] is None or x[4] == y[4]


def _same_dates(da, db):
    return len(da) == len(db) and all(_same_date(x, y) for x, y in zip(da, db, strict=True))


# --- a title date against the OTHER record's release date ---------------------
# A daily programme's undated sibling ("Esporte Total: Season 2025: Episode
# 182", system-generated) scored close to "04/09/2026 - Esporte Total" once
# the date was set aside, so a sibling a year away reached Review beside the
# true record and the recovered sole-Accept refused to clear it (BMR-Review
# handoff of 2026-11-24, 14 rows). The undated record's own ReleaseDate says
# which day it is, so it stands in for the date its title lacks (operator
# approved 2026-11-26). Enabled by title_similarity(release_dates=...);
# cmp_titles passes them when the registered parameters carry
# TITLE_DATE_VS_RELEASE_DATE true beside TITLE_DATE_TOKENS true.

def _date_fits(key, ymd):
    """Can the date-token ``key`` name the calendar day ``ymd`` = (y, m, d)?

    Read in BOTH orders, d/m and m/d: date_tokens keeps a written date
    literally and "09/04/2026" is the 4th of September to one registrant and
    the 9th of April to another. This rule declares two programmes different,
    so it may fire only when NO reading fits; an ambiguous date that can be
    the day is not evidence against it. (A ``y-m-d`` title is reordered by
    date_tokens and so gets the same lenience; it errs the same safe way.) A
    two-digit year matches on its last two digits, as ``_same_date`` does. An
    ``md`` token has no year, so only its month and day are compared.
    """
    y, m, d = ymd
    if key[0] == "md":
        return (key[1], key[2]) in ((m, d), (d, m))
    _, first, second, yy, yyyy = key
    if yy != y % 100 or (yyyy is not None and yyyy != y):
        return False
    return (first, second) in ((d, m), (m, d))


def _one_sided_date_differs(da, db, release_dates):
    """True when exactly one title of a pair is dated and none of its dates
    can be the OTHER record's release day.

    ``release_dates`` is ``(a_date, b_date)``: the full release date, as
    (y, m, d) or None, of the record each title belongs to. Only the
    one-sided case reads it. When both titles are dated, the titles' own
    dates are the direct evidence and ``_same_dates`` already decides; the
    release date only stands in for a date a title does not carry.
    """
    if release_dates is None or bool(da) == bool(db):
        return False
    dates, other = (da, release_dates[1]) if da else (db, release_dates[0])
    return other is not None and not any(_date_fits(k, other) for k in dates)


def dates_ambiguous(a_titles, b_titles, *, release_dates=None):
    """True when ANY pair of raw titles has a date on exactly ONE side and the
    rest agrees (similarity >= 0.85, Episode rules) -- the undated title may
    be any one day's broadcast, so, like a one-sided part number, the pair may
    not reach Accept on the title. Read only with dates enabled (0.77.0).

    With ``release_dates`` (as for ``title_similarity``), a one-sided pair
    whose title date cannot be the undated record's release day is not
    ambiguous: it is two different days, which ``title_similarity`` scores as
    a different programme. Absent, nothing changes."""
    for a in a_titles:
        da, ra = date_tokens(a)
        for b in b_titles:
            db, rb = date_tokens(b)
            if (bool(da) != bool(db)
                    and not _one_sided_date_differs(da, db, release_dates)
                    and title_similarity(
                        ra if da else a, rb if db else b, episodic=True) >= 0.85):
                return True
    return False


def segments(raw):
    """Split a slash- or semicolon-delimited segment title into an ordered
    list of normalised segments (duplicates kept, empties dropped), or None
    when there are fewer than two."""
    if not raw or not re.search(r"[/;]", str(raw)):
        return None
    parts = [norm_title(p) for p in re.split(r"[/;]", str(raw))]
    parts = [p for p in parts if p]
    return parts if len(parts) > 1 else None


def fuzzy(a, b):
    """Composed similarity of two already-normalised strings, in [0, 1].

    1.0 when the strings are equal ignoring spaces; otherwise the larger of
    rapidfuzz's ``token_set_ratio`` and ``WRatio``, over 100. 0.0 when either
    is empty. Public since 0.47.0 (De-Dupe UI S-35): it is the raw value the
    person, organisation and title comparators build on, and a consumer that
    needs it had to import a private name or copy the body.
    """
    if not a or not b:
        return 0.0
    # inputs are already ASCII-folded/lower-cased/punct-stripped; ignoring spaces
    # too means diacritics, ligatures, punctuation, case and spacing never count
    # as a difference for an otherwise-identical string.
    if a.replace(" ", "") == b.replace(" ", ""):
        return 1.0
    return max(fuzz.token_set_ratio(a, b), fuzz.WRatio(a, b)) / 100.0


# The private name stays, so nothing that imported it moves.
_fuzzy = fuzzy


def title_similarity(a_raw, b_raw, *, episodic=False, dates=False, release_dates=None):
    """Pairwise title similarity in [0,1] honouring part/segment rules.

    `dates=True` (0.77.0; Episode/Season pairs only, so it acts only with
    `episodic=True`) reads a date in a title as a date (see `date_tokens`)
    before any other rule: both titles dated and the dates equal -> the rest
    is compared; both dated and the dates differ -> COMBINATION_DIFFERS_QUALITY,
    the conflict "13/08/2026" against "18/08/2026" already scored; one side
    dated -> the rest is compared, and `dates_ambiguous` reports the pair.

    `release_dates=(a_date, b_date)` (acts only with `dates` and `episodic`):
    the full release date, (y, m, d) or None, of the record each title belongs
    to. When only one title is dated and none of its dates can be the OTHER
    record's release day (either d/m or m/d reading; see `_date_fits`), the
    pair is two different days: COMBINATION_DIFFERS_QUALITY, as for two dated
    titles. None (the default) is the 0.77.0 behaviour. Pure: the caller
    decides which release dates may stand for a day (`compare.cmp_titles`
    passes none that are estimated, inherited or epoch defaults).

    `episodic=True` switches on two EPISODE-ONLY semantics (operator,
    2026-09-01) that are wrong for films and are therefore off by default:

    * a compound title is a COMBINATION of segments -- same set in any order
      is one program, a different set is a different program;
    * a part number on one side only is AMBIGUOUS (any one part, or all).

    For a film, "/" is usually a subtitle separator ("Jumanji/ nekusuto
    reberu") and a bare number vs its subtitled alternate ("Troublesome Night
    5" vs "Troublesome Night - The A Files") is the SAME film. Measured:
    applying the episode rules to films dropped 324 confirmed-match title
    pairs by >= 0.2 across three labelled corpora, 247 of them with no
    delimiter at all."""
    if dates and episodic:
        da, ra = date_tokens(a_raw)
        db, rb = date_tokens(b_raw)
        if da or db:
            if da and db and not _same_dates(da, db):
                return COMBINATION_DIFFERS_QUALITY
            if _one_sided_date_differs(da, db, release_dates):
                return COMBINATION_DIFFERS_QUALITY
            ra, rb = (ra if da else a_raw), (rb if db else b_raw)
            if da and db and not norm_title(ra) and not norm_title(rb):
                return 1.0                     # the titles are the same date alone
            return title_similarity(ra, rb, episodic=True)
    pa, pb = parse_part(a_raw), parse_part(b_raw)
    if pa and pb:
        base = _fuzzy(pa[0], pb[0])
        if base >= 0.85:                       # same show, explicit part numbers
            return 1.0 if pa[1] == pb[1] else 0.05
        # different bases -> fall through to ordinary comparison
    elif episodic and (pa or pb):
        # ONE side carries a part number and the other does not. If the bases
        # agree this is AMBIGUOUS, not a match: the un-numbered title may be
        # any one part, or all parts combined. It must not reach Accept on the
        # title alone, and it is not a conflict either (operator, 2026-09-01).
        numbered, plain = (pa, b_raw) if pa else (pb, a_raw)
        if _fuzzy(numbered[0], norm_title(plain)) >= 0.85:
            return PART_AMBIGUOUS_QUALITY
    sa, sb = segments(a_raw), segments(b_raw)
    if sa or sb:                               # at least one side is multi-segment
        sa = sa or [norm_title(a_raw)]
        sb = sb or [norm_title(b_raw)]
        matched = 0
        pool = list(sb)
        for x in sa:
            best, bi = 0.0, None
            for i, y in enumerate(pool):
                q = _fuzzy(x, y)
                if q > best:
                    best, bi = q, i
            if bi is not None and best >= 0.85:
                matched += 1
                pool.pop(bi)
        # A compound title is a COMBINATION of segments (several shorts in one
        # slot). The same segments in any order are the same program; a
        # different set -- a subset, a superset, one segment alone -- is a
        # program combined differently, i.e. a DIFFERENT work. Proportional
        # credit is therefore wrong: 2 of 3 matching is not "two-thirds the
        # same", it is a different combination (operator, 2026-09-01).
        if matched == len(sa) == len(sb):
            return 1.0
        if not episodic:
            # Film: proportional credit, and never below the flat comparison
            # (a separator on one side must not halve an identical title).
            #
            # The floor uses token_sort_ratio, NOT _fuzzy, for the same reason
            # the episode branch below does: _fuzzy's token_set_ratio scores
            # any token SUBSET at 1.0, so flooring with it would raise
            # "Squid / Jawfish / Puffer" vs "Squid / Jawfish" from 0.667 to a
            # perfect match, and "Squid / Jawfish" vs "Squid" from 0.500 to
            # 1.000 -- inventing film title matches out of subsets. token_sort
            # is order-insensitive but demands the FULL token set, so it lifts
            # only the case this floor is for: the same title written with and
            # without a separator.
            flat = fuzz.token_sort_ratio(norm_title(a_raw),
                                         norm_title(b_raw)) / 100.0
            proportional = matched / max(len(sa), len(sb))
            # The floor lifts ONLY when the flat texts agree at the same 0.85
            # this module uses throughout -- i.e. when the two sides really are
            # one title written with and without a separator. Taking an
            # unconditional max() would let a partial flat resemblance drag a
            # subset upward (0.667 -> 0.788), which is not what the floor is
            # for and is not a film match.
            return max(proportional, flat) if flat >= 0.85 else proportional
        if segments(a_raw) and segments(b_raw):
            return COMBINATION_DIFFERS_QUALITY
        # Only one side is delimited. The other side is the same combination
        # written without a separator ONLY if it contains every segment --
        # so compare the flat texts with token_sort_ratio, which is
        # order-insensitive but requires the full token set. _fuzzy's
        # token_set_ratio is deliberately NOT used here: it scores any token
        # SUBSET at 1.0, which is right for "Matrix, The" and wrong for a
        # single cartoon against the slot that contained it.
        fa, fb = norm_title(a_raw), norm_title(b_raw)
        strict = fuzz.token_sort_ratio(fa, fb) / 100.0
        return 1.0 if strict >= 0.85 else COMBINATION_DIFFERS_QUALITY
    return _fuzzy(norm_title(a_raw), norm_title(b_raw))


def is_internal(t):
    """True for an Internal-class title that is not also system-generated.

    Internal = system-generated, a machine translation (operator, 2026-09-30,
    via LanguageTool). A title flagged BOTH ways is treated as system-generated:
    that flag is the stronger statement (the registry built the text from the
    record's own structure) and keeps the 2026-08-30 both-sides drop intact.
    """
    if not t.text or getattr(t, "system_generated", False):
        return False
    return (getattr(t, "title_class", "") or "").strip().lower() == "internal"


def select_titles(titles, *, include_internal=False):
    """Return (titles_to_use, used_fallback). Prefer 'real' titles; fall back to
    system-generated or internal-class (auto-translated) titles only if there is
    nothing else. Internal titles are auto-generated translations for reviewer
    convenience and must not carry full discriminating weight.

    ``include_internal=True`` counts Internal titles as usable (not fallback);
    the CALLER must then discount them -- ``compare.cmp_titles`` does, when the
    registered parameters carry ``INTERNAL_TITLE_DISCOUNT``. Why the switch
    exists: normalized-record.md section 4.1 (ratified 2026-07-29) says Internal
    titles are "diminished, never ignored", and section 7 gap 1 records that
    the default below ignores them whenever a real title exists. LanguageTool
    (2026-09-30) measured ~450,000 Internal titles registry-wide (11% of a 2%
    mirror sample) and showed they are the cross-language bridge: often the
    only English on a French-registered record. The default stays False so the
    behaviour is unchanged, byte for byte, until BMR-Review lands the knob and
    measures it (the T3-style split: mechanism in eidr-core, knob and
    measurement in BMR-Review). With the switch on, only system-generated
    titles remain fallback-only, so the both-sides drop in ``cmp_titles``
    applies to system-generated titles and never to Internal ones.
    """
    def is_real(t):
        if not t.text:
            return False
        if getattr(t, "system_generated", False):
            return False
        if include_internal:
            return True
        return (getattr(t, "title_class", "") or "").strip().lower() != "internal"
    real = [t for t in titles if is_real(t)]
    if real:
        return real, False
    fallback = [t for t in titles if t.text]
    return fallback, True


def parts_ambiguous(a_titles, b_titles):
    """True when ANY pair of raw title strings (not only the best-matching
    pair) has a part number on exactly ONE side with agreeing bases (fuzzy
    >= 0.85) -- the un-numbered title may be any one part or all parts
    combined, so the pair may not reach Accept on the title."""
    for a in a_titles:
        for b in b_titles:
            pa, pb = parse_part(a), parse_part(b)
            if bool(pa) != bool(pb):
                numbered, plain = (pa, b) if pa else (pb, a)
                if _fuzzy(numbered[0], norm_title(plain)) >= 0.85:
                    return True
    return False


def _numbered_parts_conflict(a_raws, b_raws):
    """True for a same-base pair with DIFFERENT part numbers only -- the half
    of :func:`parts_conflict` that holds for episodes too.

    Private: ``compare.cmp_titles`` uses it for an Episode/Season pair, where
    the other half (numbered vs bare base) is AMBIGUOUS, not a conflict
    (operator ruling 2026-10-19, "That's ambiguous"; 0.69.0).
    """
    pa = [parse_part(x) for x in a_raws]
    pb = [parse_part(x) for x in b_raws]
    return any(x and y and x[1] != y[1] and _fuzzy(x[0], y[0]) >= 0.85
               for x in pa for y in pb)


def parts_conflict(a_raws, b_raws):
    """True when the titles carry a distinguishing part signal: a same-base
    pair with DIFFERENT part numbers ('Show Teil 1' vs 'Show Teil 2', 'Rocky'
    2 vs 3), or one title numbered while the other side carries the bare base
    with no number ('Rocky 2' vs 'Rocky') -- numbered sequels tend to be very
    similar otherwise.

    Episode-UNAWARE, deliberately: the numbered-vs-bare half is right for
    films and wrong for episodes, where it is ambiguous (operator ruling
    2026-10-19). ``compare.cmp_titles`` applies that distinction for an
    Episode/Season pair; this function keeps its film meaning because
    BMR-Review's verify step calls it directly."""
    pa = [parse_part(x) for x in a_raws]
    pb = [parse_part(x) for x in b_raws]
    na = [norm_title(x) for x in a_raws if x]
    nb = [norm_title(x) for x in b_raws if x]
    # Bare-base variants with a LEADING numeral token stripped. A leading
    # "I" that norm_title keeps (English "I Spy" -> "1 spy"; Italian "I ..."
    # is stripped as an article since 0.69.0) still normalises into a digit,
    # which hides the bare base from the one-sided comparison below. Either
    # reading -- word or part-one marker -- makes a pair against "<base> 2" a
    # part question, so the stripped variant participates in the bare-base
    # check.
    _lead = re.compile(r"^(?:[0-9]{1,2}|[ivx]{1,4})\s+")
    na = na + [_lead.sub("", t) for t in na if _lead.match(t)]
    nb = nb + [_lead.sub("", t) for t in nb if _lead.match(t)]
    for x in pa:
        if not x:
            continue
        for y in pb:
            if y and x[1] != y[1] and _fuzzy(x[0], y[0]) >= 0.85:
                return True
        # numbered on side A vs bare base on side B. Strict comparator
        # (plain edit distance, not token-set) so that a short base cannot
        # "subset-match" inside an unrelated longer title.
        if any(fuzz.ratio(x[0], t) / 100.0 >= 0.92 for t in nb) \
                and not any(y and _fuzzy(x[0], y[0]) >= 0.85 for y in pb):
            return True
    for y in pb:
        if not y:
            continue
        if any(fuzz.ratio(y[0], t) / 100.0 >= 0.92 for t in na) \
                and not any(x and _fuzzy(y[0], x[0]) >= 0.85 for x in pa):
            return True
    return False
