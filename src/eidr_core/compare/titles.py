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


def segments(raw):
    """Split a slash-delimited segment title into a normalised set, or None."""
    if not raw or "/" not in str(raw):
        return None
    parts = [norm_title(p) for p in str(raw).split("/")]
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


def title_similarity(a_raw, b_raw):
    """Pairwise title similarity in [0,1] honouring part/segment rules."""
    pa, pb = parse_part(a_raw), parse_part(b_raw)
    if pa and pb:
        base = _fuzzy(pa[0], pb[0])
        if base >= 0.85:                       # same show, explicit part numbers
            return 1.0 if pa[1] == pb[1] else 0.05
        # different bases -> fall through to ordinary comparison
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
        return matched / max(len(sa), len(sb))
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
