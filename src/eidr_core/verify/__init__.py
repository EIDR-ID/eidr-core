"""External-fact verification primitives — pure, no I/O, no config objects.

Compares a REGISTERED value against an EXTERNAL FACT (TMDb, IMDb, Wikidata,
…) and returns a categorical verdict. Extracted verbatim from eidr-dq
``src/dq/matching/compare.py`` (register R12 tail / Phase 3 item 6,
2026-08-06), where it had been written for extraction from the start.

Each comparator returns ``(comparison, note)`` where comparison is one of:

    match         the external fact agrees with the registered value
    mismatch      the external fact disagrees
    insufficient  the comparison could not be made at the required
                  precision (a real answer: we looked and could not tell)
    none          no usable external fact of this type

The caller decides what those mean. This module deliberately knows nothing
about verdicts, findings, rules, or confidence scores: eidr-dq maps these to
corroborated/contradicted, and a matching program would map them to score
contributions, from the same primitives.

WHY THIS IS NOT ``eidr_core.compare``
-------------------------------------
Both packages contain a function that compares two release dates, and they
are deliberately NOT merged. They answer different questions with different
contracts:

* ``eidr_core.compare`` (L2, seeded from BMR-Review) scores an EIDR record
  against ANOTHER EIDR RECORD for de-duplication. It returns a continuous
  quality in [0, 1+bonus] via half-life decay, is tuned through
  ``compare-spec.json``, and its behaviour is pinned by the golden-pair
  corpus. Both sides are registry-shaped, so neither carries a stated
  precision.
* ``eidr_core.verify`` (this module) checks a registered value against an
  OUTSIDE SOURCE. It returns a categorical verdict because a DQ finding is
  binary, and it honours the external fact's stated precision — a
  year-precision fact can only support a year-level claim, so an exact-date
  question returns ``insufficient`` rather than a false ``mismatch``.
  ``release_date_precision`` has no analogue on the dedup side.

Folding one into the other would put two different meanings of "compare
release date" in a namespace the compare-spec governs, which is exactly the
silent-semantic-drift the golden pairs exist to catch. Consumers that need
both import both.

Tuning values are PARAMETERS here, never module constants: eidr-dq passes
per-rule tolerances from its rule config. A second consumer with different
tolerances (e.g. eidr-wikidata's year bands) passes its own — the shared
part is the arithmetic and the precision logic, not the thresholds.
"""
from __future__ import annotations

from datetime import date

__all__ = [
    "parse_iso_date",
    "runtime_candidates",
    "compare_runtime",
    "compare_release_date",
    "compare_year_arbitration",
]


def parse_iso_date(s: str) -> date | None:
    """Parse a leading ISO date (YYYY-MM-DD) from a string. None if unparseable."""
    try:
        return date.fromisoformat(str(s)[:10])
    except (TypeError, ValueError):
        return None


def runtime_candidates(facts: dict) -> list[float]:
    """All comparable runtimes in a fact set, in minutes.

    Series ApproximateLength is the typical episode duration per the best
    practices, so TMDb episode_run_time is directly comparable and is
    included alongside runtime_minutes.
    """
    out = list(facts.get("runtime_minutes") or [])
    out += list(facts.get("episode_runtime_minutes") or [])
    return [float(x) for x in out]


def compare_runtime(reg_minutes: float, facts: dict,
                    *, tolerance_minutes: float = 5.0,
                    tolerance_pct: float = 0.10) -> tuple[str, str]:
    """Compare a registered runtime against external runtime facts.

    The closest external candidate wins, on the reasoning that a work with
    several catalogued cuts should be corroborated by whichever cut the
    registry describes, not contradicted by the others.
    """
    cands = runtime_candidates(facts)
    if not cands:
        return "none", "no runtime"
    best = min(cands, key=lambda c: abs(c - reg_minutes))
    tol = max(float(tolerance_minutes), float(tolerance_pct) * best)
    if abs(best - reg_minutes) <= tol:
        return "match", f"runtime {best:g} vs {reg_minutes:g} (match)"
    return "mismatch", f"runtime {best:g} vs {reg_minutes:g} (mismatch)"


def compare_release_date(reg_date: date | None, reg_year: int | None,
                         facts: dict, *, mode: str = "window",
                         tolerance_days: int = 30) -> tuple[str, str]:
    """Compare a registered release date against an external date fact.

    Honors the external fact's stated precision: a year-precision external
    fact can only support a year-level claim, so asking it an exact-date
    question returns insufficient rather than a false mismatch.

    mode:
        exact_date  the dates must be the same day
        year        only the years are compared
        window      within tolerance_days, degrading to month or year
                    comparison as the available precision requires
    """
    ext_raw = facts.get("release_date")
    if not ext_raw:
        return "none", "no release date"
    ext_date = parse_iso_date(ext_raw)
    if ext_date is None:
        return "none", "unparseable external date"
    precision = facts.get("release_date_precision", "day")

    if mode == "exact_date":
        if reg_date is None:
            return "insufficient", "registry has no full date"
        if precision != "day":
            return "insufficient", f"external precision {precision}"
        if ext_date == reg_date:
            return "match", f"date {ext_date} (exact match)"
        return "mismatch", f"date {ext_date} vs {reg_date} (mismatch)"

    if mode == "year":
        ry = reg_year or (reg_date.year if reg_date else None)
        if ry is None:
            return "insufficient", "registry has no year"
        if ext_date.year == int(ry):
            return "match", f"year {ext_date.year} (match)"
        return "mismatch", f"year {ext_date.year} vs {ry} (mismatch)"

    # mode == "window"
    if reg_date is not None and precision == "day":
        diff = abs((ext_date - reg_date).days)
        if diff <= tolerance_days:
            return "match", f"date {ext_date} vs {reg_date} ({diff}d, match)"
        return "mismatch", f"date {ext_date} vs {reg_date} ({diff}d, mismatch)"
    if reg_date is not None and precision == "month":
        same = (ext_date.year, ext_date.month) == (reg_date.year, reg_date.month)
        adjacent = abs((ext_date.year * 12 + ext_date.month)
                       - (reg_date.year * 12 + reg_date.month)) == 1
        if same or (adjacent and tolerance_days >= 28):
            return "match", f"month {ext_date:%Y-%m} vs {reg_date:%Y-%m} (match)"
        return "mismatch", f"month {ext_date:%Y-%m} vs {reg_date:%Y-%m} (mismatch)"
    # Year-precision external fact, or year-only registry value.
    ry = reg_year or (reg_date.year if reg_date else None)
    if ry is None:
        return "insufficient", "registry has no date"
    if ext_date.year == int(ry):
        return "match", f"year {ext_date.year} (match)"
    return "mismatch", f"year {ext_date.year} vs {ry} (mismatch)"


def compare_year_arbitration(reg_date: date | None, reg_year: int | None,
                             facts: dict) -> tuple[str, str]:
    """Arbitrate between a record's two self-contradicting date fields.

    For a record whose release_date's year and release_year disagree with
    each other, an external source cannot make the disagreement go away:
    the record is internally inconsistent whatever the outside world says.
    So this never returns match. What it can do, and the reason it exists,
    is say WHICH field the outside world backs, which is the actionable
    part for a curator.

    Returns mismatch whenever an external date is available (the finding is
    a true defect either way), with a note naming the field the external
    fact agrees with, or noting that it agrees with neither.
    """
    ext_raw = facts.get("release_date")
    if not ext_raw:
        return "none", "no release date"
    ext_date = parse_iso_date(ext_raw)
    if ext_date is None:
        return "none", "unparseable external date"
    if reg_date is None or reg_year is None:
        return "insufficient", "registry lacks both fields to arbitrate"

    ey = ext_date.year
    d_year = reg_date.year
    if ey == d_year and ey != int(reg_year):
        return ("mismatch",
                f"external year {ey} matches release_date ({d_year}); "
                f"release_year ({reg_year}) is the outlier")
    if ey == int(reg_year) and ey != d_year:
        return ("mismatch",
                f"external year {ey} matches release_year ({reg_year}); "
                f"release_date year ({d_year}) is the outlier")
    return ("mismatch",
            f"external year {ey} matches neither release_date ({d_year}) "
            f"nor release_year ({reg_year})")
