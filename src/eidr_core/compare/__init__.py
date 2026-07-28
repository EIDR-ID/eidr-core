"""
Field comparators -> FieldResult(quality in [0, 1+bonus]).

Within-field aggregation uses nonlinear.accumulate(): one match = full first-
match credit (independent of list length), additional matches add a diminishing,
capped bonus. Quality may exceed 1.0; the record-level average is clamped.

Only Alt-IDs are a negative signal (conflict). Dates and durations never go
negative -- distant values just earn little credit.

Extracted from BMR-Review ``eidr_dedup_score/compare.py`` (unified-scoring.md
migration step 1, 2026-07-28) together with ``titles`` and ``nonlinear``; the
L1 normalizers moved to ``eidr_core.normalize``. This is the portfolio's ONE
comparator library (L2): per-field continuous qualities consumed by the
scoring engine and, as banded states, by the De-Dupe UI payloads. Tuning
constants are read through ``_params`` — consumers register their config via
``set_params`` (BMR-Review registers its ``config.py``; later the loaded
compare-spec.json). BMR-Review keeps thin re-export shims so its internal
imports and the engine-tuning workflow are unchanged.
"""
from dataclasses import dataclass
from typing import Optional
from rapidfuzz import fuzz

from . import _params as config
from . import nonlinear
from ._params import set_source as set_params  # public registration API
from .titles import title_similarity, select_titles, parts_conflict
from eidr_core.normalize import (norm_title, norm_name, norm_code, norm_lang,
                        norm_country, parse_date, days_between, parse_minutes)


@dataclass
class FieldResult:
    field: str
    quality: Optional[float]
    detail: str = ""
    conflict: int = 0
    meta: dict = None


def _fuzzy(a, b):
    if not a or not b:
        return 0.0
    # inputs are already ASCII-folded/lower-cased/punct-stripped; ignoring spaces
    # too means diacritics, ligatures, punctuation, case and spacing never count
    # as a difference for an otherwise-identical string.
    if a.replace(" ", "") == b.replace(" ", ""):
        return 1.0
    return max(fuzz.token_set_ratio(a, b), fuzz.WRatio(a, b)) / 100.0


def _greedy_align(a_norm, b_norm, simf=None):
    simf = simf or _fuzzy
    pairs = []
    for i, x in enumerate(a_norm):
        for j, y in enumerate(b_norm):
            pairs.append((simf(x, y), i, j))
    pairs.sort(reverse=True)
    used_a, used_b, qs = set(), set(), []
    for q, i, j in pairs:
        if i in used_a or j in used_b:
            continue
        used_a.add(i); used_b.add(j); qs.append(q)
    return qs


# -------- titles (episode-aware: part/segment rules, system-gen filtering) --------
def _title_base_ratio(a, b):
    """Similarity of two already-normalised part BASE titles (0..1)."""
    from rapidfuzz import fuzz as _f
    if not a or not b:
        return 0.0
    if a.replace(" ", "") == b.replace(" ", ""):
        return 1.0
    return max(_f.token_set_ratio(a, b), _f.WRatio(a, b)) / 100.0

def cmp_titles(a, b):
    a_use, a_fb = select_titles(a.titles)
    b_use, b_fb = select_titles(b.titles)
    a_raw = [t.text for t in a_use if t.text]
    b_raw = [t.text for t in b_use if t.text]
    if not a_raw or not b_raw or a_fb or b_fb:
        # No real (non-system-generated, non-internal) title on one or both sides.
        # A system-generated title is derived from the series/season/episode
        # structure that is ALREADY compared via parent/family/distribution
        # number, so scoring it would double-count -- and a titleless record gets
        # a system title in the registry. Drop the title from the average rather
        # than counting it as a 0 (which would swamp the weight-50 episode title).
        why = ("no real title to compare" if (not a_raw or not b_raw)
               else "system-generated titles only - ignored")
        return FieldResult("title", None, why, meta={})
    qs = _greedy_align(a_raw, b_raw, simf=title_similarity)
    best = max(qs) if qs else 0.0
    pconf = parts_conflict(a_raw, b_raw)
    # When a part conflict is present, record whether the two sides share the
    # same BASE title (the numbered serial case, e.g. "<Show> Part 2" vs
    # "<Show> Part 3"). The raw best_sim is near zero once the differing part
    # numbers are accounted for, so downstream "related parts" handling needs
    # this base-level signal rather than best_sim to tell a same-work serial
    # from two unrelated films that merely share a numbered-title shape.
    base_match = 0.0
    if pconf:
        from .titles import parse_part
        pa = [parse_part(x) for x in a_raw]
        pb = [parse_part(x) for x in b_raw]
        for x in pa:
            if not x:
                continue
            for y in pb:
                if not y:
                    continue
                base_match = max(base_match, _title_base_ratio(x[0], y[0]))
    return FieldResult("title", nonlinear.accumulate(qs),
                       f"best={best:.2f} matches={sum(1 for q in qs if q>0)}",
                       meta={"best_sim": best, "part_conflict": pconf,
                             "part_base_match": base_match})


def _proportional(qs, n_a, n_b):
    """Field quality = matched strength / size of the smaller list, in [0,1].
    A fully-matched smaller list -> 1.0 (tolerates an incomplete other side);
    a partial overlap (e.g. 1 of 4 shared) -> ~0.25; no overlap -> 0 (but the
    field is still present on both sides, so it stays in the denominator)."""
    denom = min(n_a, n_b)
    if not denom:
        return None
    return min(1.0, sum(qs) / denom)


# -------- people --------
def _cmp_people(a_names, b_names, field):
    a_norm = [norm_name(p.display) for p in a_names if p.display]
    b_norm = [norm_name(p.display) for p in b_names if p.display]
    if not a_norm or not b_norm:
        return FieldResult(field, None, "absent")
    qs = [q if q >= config.NAME_MATCH_MIN else 0.0
          for q in _greedy_align(a_norm, b_norm)]
    q = _proportional(qs, len(a_norm), len(b_norm))
    return FieldResult(field, q,
                       f"matches={sum(1 for x in qs if x>0)}/{min(len(a_norm),len(b_norm))}")


def cmp_directors(a, b):
    return _cmp_people(a.directors, b.directors, "director")


def cmp_actors(a, b):
    return _cmp_people(a.actors, b.actors, "actor")


# -------- code lists --------
def _cmp_codes(a_codes, b_codes, field, normf):
    A = [normf(c.code) for c in a_codes]; B = [normf(c.code) for c in b_codes]
    A = [c for c in A if c]; B = [c for c in B if c]
    if not A or not B:
        return FieldResult(field, None, "absent")
    bset = list(B); qs = []
    for c in A:
        if c in bset:
            qs.append(1.0); bset.remove(c)
    return FieldResult(field, nonlinear.accumulate(qs),
                       f"matches={len(qs)}/{min(len(A),len(B))}")


def cmp_countries(a, b):
    # norm_country (NOT norm_code) so a "SU" record matches a "SUHH" candidate:
    # same country, different EIDR code set. Register Phase 1.1; crosswalk is
    # single-homed in eidr_core.codes. Re-applied 2026-07-27 after a parallel
    # engine-improvement pass rebuilt this file from a pre-1.1 baseline —
    # pinned by tests/test_country_normalization.py, do not swap back.
    return _cmp_codes(a.countries, b.countries, "country", norm_country)


def cmp_original_language(a, b):
    return _cmp_codes(a.original_languages, b.original_languages,
                      "original_language", norm_lang)


def cmp_version_language(a, b):
    return _cmp_codes(a.version_languages, b.version_languages,
                      "version_language", norm_lang)


# -------- associated orgs --------
def cmp_assoc_orgs(a, b):
    if not a.assoc_orgs or not b.assoc_orgs:
        return FieldResult("assoc_org", None, "absent")
    qs = []; bpool = list(b.assoc_orgs)
    for oa in a.assoc_orgs:
        best, bi = 0.0, None
        for i, ob in enumerate(bpool):
            if oa.party_id and ob.party_id and oa.party_id == ob.party_id:
                q = 1.0
            else:
                q = _fuzzy(norm_name(oa.name or ""), norm_name(ob.name or ""))
            if q > best:
                best, bi = q, i
        if bi is not None and best >= config.NAME_MATCH_MIN:
            qs.append(best); bpool.pop(bi)
    q = _proportional(qs, len(a.assoc_orgs), len(b.assoc_orgs))
    return FieldResult("assoc_org", q, f"matches={sum(1 for x in qs if x>0)}/"
                       f"{min(len(a.assoc_orgs),len(b.assoc_orgs))}")


# -------- release date (non-linear, never negative, two modes) --------
def _epoch_suspect(y, ymd):
    """True when the date looks like a Unix-epoch default: year-only 1970, or
    exactly 1970-01-01. A specific 1970 date (e.g. 1970-06-15) is genuine."""
    if y != config.DATE_EPOCH_YEAR:
        return False
    return ymd is None or ymd == (config.DATE_EPOCH_YEAR, 1, 1)


def cmp_release_date(a, b):
    ay, aymd = parse_date(a.release_date)
    by, bymd = parse_date(b.release_date)
    if ay is None or by is None:
        return FieldResult("release_date", None, "absent")
    epoch_a = _epoch_suspect(ay, aymd)
    epoch_b = _epoch_suspect(by, bymd)
    epoch = epoch_a or epoch_b
    estimated = a.date_estimated or b.date_estimated
    leniency = config.DATE_ESTIMATED_LENIENCY if estimated else 1.0
    if aymd and bymd:
        if aymd == bymd:
            if epoch:      # both 1970-01-01: likely two systems defaulting
                return FieldResult("release_date", config.DATE_EPOCH_MATCH_CREDIT,
                                   "1970-01-01 epoch match (default-date suspect)")
            return FieldResult("release_date", 1.0, "exact")
        dd = days_between(aymd, bymd)
        hl = config.DATE_FULL_HALFLIFE_DAYS * leniency
        q = 0.5 ** (dd / hl)
        if epoch:
            q = max(q, config.DATE_EPOCH_MISMATCH_FLOOR)
            return FieldResult("release_date", q, f"{dd}d apart (1970 epoch suspect)")
        return FieldResult("release_date", q, f"{dd}d apart"
                           + (" est" if estimated else ""))
    gap = abs(ay - by)
    episode = (a.creation_type == "Episode" or b.creation_type == "Episode")
    if gap == 0:
        if epoch_a and epoch_b:    # 1970 == 1970: two defaults agreeing proves little
            return FieldResult("release_date", config.DATE_EPOCH_MATCH_CREDIT,
                               "1970 epoch match (default-date suspect)")
        if epoch:                  # a suspect side agreeing with a GENUINE 1970 date
            return FieldResult("release_date", config.DATE_EPOCH_MIXED_MATCH_CREDIT,
                               "1970 year match (one side epoch suspect)")
        if episode:                # year-only match between episodes: weak evidence
            return FieldResult("release_date", config.DATE_EPISODE_YEAR_MATCH_CREDIT,
                               "year match (year-only; weak for episodes)")
        return FieldResult("release_date", 1.0, "year match")
    hl_years = (config.DATE_YEAR_HALFLIFE_YEARS_EPISODE
                if episode
                else config.DATE_YEAR_HALFLIFE_YEARS)
    hl = hl_years * leniency
    q = 0.5 ** (gap / hl)
    if epoch:
        q = max(q, config.DATE_EPOCH_MISMATCH_FLOOR)
        return FieldResult("release_date", q, f"{gap}yr apart (1970 epoch suspect)")
    return FieldResult("release_date", q, f"{gap}yr apart"
                       + (" est" if estimated else ""))


# -------- duration (absolute AND relative; lenient) --------
def cmp_length(a, b):
    am = parse_minutes(a.length_minutes); bm = parse_minutes(b.length_minutes)
    if not am or not bm:
        return FieldResult("length", None, "absent")
    estimated = a.length_estimated or b.length_estimated
    hl = config.DUR_ABS_HALFLIFE_MIN * (config.DUR_ESTIMATED_LENIENCY if estimated else 1.0)
    diff = abs(am - bm)
    credit_abs = 0.5 ** (diff / hl)
    credit_rel = min(am, bm) / max(am, bm)
    q = max(credit_abs, credit_rel)            # benefit of the doubt
    return FieldResult("length", q, f"{am:.0f}/{bm:.0f}m d={diff:.0f}"
                       + (" est" if estimated else ""))


# -------- episodic identity --------
def _cmp_token(av, bv, field):
    if av in (None, "") or bv in (None, ""):
        return FieldResult(field, None, "absent")
    q = 1.0 if str(av).strip() == str(bv).strip() else 0.0
    return FieldResult(field, q, f"{av}|{bv}")


def _strip_num(v):
    """Normalize a number token for boolean comparison: strip whitespace and
    leading zeros ('05' -> '5', '007' -> '7', '0' -> '0')."""
    if v in (None, ""):
        return None
    s = str(v).strip()
    return (s.lstrip("0") or "0") if s else None


def cmp_sequence_number(a, b):
    """Season sequence number: Boolean comparison after stripping leading zeros."""
    av, bv = _strip_num(a.sequence_number), _strip_num(b.sequence_number)
    if av is None or bv is None:
        return FieldResult("sequence_number", None, "absent")
    return FieldResult("sequence_number", 1.0 if av == bv else 0.0,
                       f"{a.sequence_number}|{b.sequence_number}")


def _epnums(rec):
    """A record's episodic numbers -- distribution number, house sequence, and
    alternate numbers -- normalized (leading zeros stripped)."""
    out = set()
    for v in [rec.distribution_number, rec.house_sequence]:
        s = _strip_num(v)
        if s is not None:
            out.add(s)
    for n in (rec.alt_numbers or []):
        s = _strip_num(n[0])
        if s is not None:
            out.add(s)
    return out


def cmp_distribution_number(a, b):
    """Episode distribution number: Boolean (after stripping leading zeros).
    When both records carry a distribution number it is always applicable, so a
    mismatch stays in the denominator with 0 credit (it degrades the score).
    Half credit is given for a likely renumbering:
      - any episodic number matches across the cross-product of
        {distribution number, house sequence, alternate number}; or
      - both records carry FULL release dates (day-level) that match exactly --
        air dates are effectively unique within a series, so an exact-date pair
        with differing numbers is usually the same episode numbered by a
        different scheme (validated against operator review decisions)."""
    da, db = _strip_num(a.distribution_number), _strip_num(b.distribution_number)
    if da is None or db is None:
        return FieldResult("distribution_number", None, "absent")
    if da == db:
        return FieldResult("distribution_number", 1.0, "number match")
    if _epnums(a) & _epnums(b):
        return FieldResult("distribution_number", 0.5,
                           "episodic number cross-match (dist differs)")
    _, ymd_a = parse_date(a.release_date)
    _, ymd_b = parse_date(b.release_date)
    if ymd_a is not None and ymd_a == ymd_b:
        return FieldResult("distribution_number", 0.5,
                           "dist differs but full release dates match exactly "
                           "(likely renumbering)")
    return FieldResult("distribution_number", 0.0,
                       f"distribution number mismatch ({a.distribution_number} != {b.distribution_number})")


def cmp_house_sequence(a, b):
    """House number: Boolean after stripping leading zeros ('0415' == '415')."""
    av, bv = _strip_num(a.house_sequence), _strip_num(b.house_sequence)
    if av is None or bv is None:
        return FieldResult("house_sequence", None, "absent")
    return FieldResult("house_sequence", 1.0 if av == bv else 0.0,
                       f"{a.house_sequence}|{b.house_sequence}")


def cmp_time_slot(a, b):
    return _cmp_token(a.time_slot, b.time_slot, "time_slot")


def cmp_end_date(a, b):
    ay, _ = parse_date(a.end_date); by, _ = parse_date(b.end_date)
    if ay is None or by is None:
        return FieldResult("end_date", None, "absent")
    gap = abs(ay - by)
    if gap == 0:
        return FieldResult("end_date", 1.0, "year match")
    q = 0.5 ** (gap / config.DATE_YEAR_HALFLIFE_YEARS)
    return FieldResult("end_date", q, f"{gap}yr apart")


# -------- alt ids (only negative signal) --------
import re as _re
# Opaque registry-internal id types (no cross-source meaning unless domain-scoped).
_ALT_OPAQUE = {"proprietary", "baseline", "other", "eidr", ""}


def alt_source(a):
    """Namespace key for an Alt-ID: the domain exactly as presented, or the
    id_type when the type itself names the source. Nothing is stripped or
    canonicalised -- the FULL domain identifies the namespace, so
    'themoviedb.org/movie' and 'themoviedb.org/tv' are different sources and
    may reuse the same number. Comparison is case-insensitive only.
    Malformed or non-standard domains are a data-quality matter handled by the
    DQ review, not corrected here. Returns None for opaque registry ids that
    carry no domain (not a cross-source identifier)."""
    t = (a.id_type or "").strip().casefold()
    d = (a.domain or "").strip().casefold()
    if t in _ALT_OPAQUE:
        return d or None
    return d or t or None



def cmp_alt_ids(a, b):
    def rel_ok(r):
        return r is None or str(r).strip().lower() in ("", "issameas")

    def is_shortdoi(x):
        return (str(getattr(x, "id_type", "") or "").strip().lower() == "shortdoi"
                or str(getattr(x, "domain", "") or "").strip().lower() == "shortdoi")
    from collections import defaultdict
    av = defaultdict(set); bv = defaultdict(set)
    av_rel = defaultdict(lambda: True); bv_rel = defaultdict(lambda: True)
    for x in a.alt_ids:
        if is_shortdoi(x):                       # ShortDOI = alias of the EIDR id; ignore
            continue
        s = alt_source(x)
        if s is None:                            # opaque registry id; not cross-source
            continue
        av[s].add((s, str(x.value).strip().casefold()))
        av_rel[s] &= rel_ok(x.relation)
    for x in b.alt_ids:
        if is_shortdoi(x):
            continue
        s = alt_source(x)
        if s is None:
            continue
        bv[s].add((s, str(x.value).strip().casefold()))
        bv_rel[s] &= rel_ok(x.relation)
    shared = set(av) & set(bv)
    if not shared:
        return FieldResult("alt_id", None, "no shared source", meta={"matches": 0})
    qs, conflicts = [], 0
    for k in shared:
        # It is the FULL domain that identifies an Alt ID namespace:
        # themoviedb.org/movie and themoviedb.org/tv are different sources and
        # may legitimately reuse the same number. Entries under a shared stem
        # are only comparable when their full domains agree, or when one side
        # gives no path (a bare "themoviedb.org" aligns with either).
        if {v for _f, v in av[k]} & {v for _f, v in bv[k]}:
            qs.append(1.0)
        elif av_rel[k] and bv_rel[k]:
            conflicts += 1
    q = nonlinear.accumulate(qs) if qs else None
    return FieldResult("alt_id", q, f"match={len(qs)} conflict={conflicts}",
                       conflict=conflicts, meta={"matches": len(qs)})


COMPARATORS = {
    "title": cmp_titles, "director": cmp_directors, "actor": cmp_actors,
    "country": cmp_countries, "original_language": cmp_original_language,
    "version_language": cmp_version_language, "assoc_org": cmp_assoc_orgs,
    "release_date": cmp_release_date, "length": cmp_length,
    "sequence_number": cmp_sequence_number,
    "distribution_number": cmp_distribution_number,
    "house_sequence": cmp_house_sequence, "time_slot": cmp_time_slot,
    "end_date": cmp_end_date,
}
