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

Part/segment rules apply to all creation types (part numbering shows up in
non-episodic titles too); system-generated filtering is most relevant to
episodes.
"""
import re

from rapidfuzz import fuzz

from eidr_core.normalize import norm_title

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


def segments(raw):
    """Split a slash-delimited segment title into a normalised set, or None."""
    if not raw or not re.search(r"[/;]", str(raw)):
        return None
    parts = [norm_title(p) for p in re.split(r"[/;]", str(raw))]
    parts = [p for p in parts if p]
    return parts if len(parts) > 1 else None


def _fuzzy(a, b):
    if not a or not b:
        return 0.0
    # inputs are already ASCII-folded/lower-cased/punct-stripped; ignoring spaces
    # too means diacritics, ligatures, punctuation, case and spacing never count
    # as a difference for an otherwise-identical string.
    if a.replace(" ", "") == b.replace(" ", ""):
        return 1.0
    return max(fuzz.token_set_ratio(a, b), fuzz.WRatio(a, b)) / 100.0


def title_similarity(a_raw, b_raw, *, episodic=False):
    """Pairwise title similarity in [0,1] honouring part/segment rules.

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


def select_titles(titles):
    """Return (titles_to_use, used_fallback). Prefer 'real' titles; fall back to
    system-generated or internal-class (auto-translated) titles only if there is
    nothing else. Internal titles are auto-generated translations for reviewer
    convenience and must not carry full discriminating weight."""
    def is_real(t):
        if not t.text:
            return False
        if getattr(t, "system_generated", False):
            return False
        return (getattr(t, "title_class", "") or "").strip().lower() != "internal"
    real = [t for t in titles if is_real(t)]
    if real:
        return real, False
    fallback = [t for t in titles if t.text]
    return fallback, True


def parts_ambiguous(a_titles, b_titles):
    """True when the best-matching title pair has a part number on exactly ONE
    side with agreeing bases -- the un-numbered title may be any one part or
    all parts combined, so the pair may not reach Accept on the title."""
    for a in a_titles:
        for b in b_titles:
            pa, pb = parse_part(a), parse_part(b)
            if bool(pa) != bool(pb):
                numbered, plain = (pa, b) if pa else (pb, a)
                if _fuzzy(numbered[0], norm_title(plain)) >= 0.85:
                    return True
    return False


def parts_conflict(a_raws, b_raws):
    """True when the titles carry a distinguishing part signal: a same-base
    pair with DIFFERENT part numbers ('Show Teil 1' vs 'Show Teil 2', 'Rocky'
    2 vs 3), or one title numbered while the other side carries the bare base
    with no number ('Rocky 2' vs 'Rocky') -- numbered sequels tend to be very
    similar otherwise."""
    pa = [parse_part(x) for x in a_raws]
    pb = [parse_part(x) for x in b_raws]
    na = [norm_title(x) for x in a_raws if x]
    nb = [norm_title(x) for x in b_raws if x]
    # Bare-base variants with a LEADING numeral token stripped. Some articles
    # normalise into digits ("I miserabili" -> "1 miserabili": the Italian
    # article is read as roman numeral I), which hides the bare base from the
    # one-sided comparison below. Either reading -- article or part-one marker
    # -- makes a pair against "<base> 2" a part question, so the stripped
    # variant participates in the bare-base check.
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
