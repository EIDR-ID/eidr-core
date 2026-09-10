"""
Non-linear aggregation of a list of per-pair match qualities.

Given matched-pair qualities q1 >= q2 >= ... (each in [0,1]; 1.0 for an exact
controlled-vocabulary / Alt-ID match, the fuzzy score for text) and n
"opportunities", the aggregate is:

    score = sum_i q_(i) * r^(i-1)  /  sum_{j=1..n} r^(j-1)

The first match is worth the most; each additional match contributes r x the
previous one. When every opportunity is matched perfectly the score is 1.0.
With all-exact matches this reduces to (1 - r^k)/(1 - r^n).

r is config.NL_MODIFIER (Rovi: 0.75).

opportunities() was removed 2026-09-10. It read config.LIST_DENOMINATOR,
which no registered parameter source has ever defined -- so with params
registered (the real-run condition) it raised AttributeError on its own
documented default. It had no caller in any repository; the live path is
accumulate(), which never needed an opportunity count. Found by BMR-Review
and De-Dupe UI independently while checking the call graph rather than the
mention. A parameter read only through _params has no textual reference in
the repo that supplies it, so nothing flags an unmet contract until the line
executes -- which is why a function that raises on its default is worse than
dead code: it is a loaded trap for whoever reads the signature years later.
"""
from . import _params as config


def aggregate(qualities, n_opportunities, r=None, denom_basis=None):
    if r is None:
        r = config.NL_MODIFIER
    qs = sorted((q for q in qualities if q > 0), reverse=True)
    if not qs or n_opportunities <= 0:
        return 0.0
    n = max(n_opportunities, len(qs))
    numer = sum(q * (r ** i) for i, q in enumerate(qs))
    denom = sum(r ** j for j in range(n))
    return numer / denom if denom else 0.0


def corroborate(qualities, n_opportunities, r=None):
    """Deprecated in favour of accumulate(); kept for callers that still pass an
    opportunity count. Delegates to accumulate (opportunity count ignored)."""
    return accumulate(qualities, r)


def accumulate(qualities, r=None, bonus_cap=None):
    """Within-field accumulation (no opportunity denominator).

    A single matched element earns FULL first-match credit (its quality),
    regardless of how many elements exist on either side -- 1 of 100 scores the
    same as 1 of 1. Each additional match adds a diminishing bonus
    (q_k * r^(k-1)), so multiple matches raise the field score but never as much
    as the first match. Total bonus is capped (bonus_cap) so one long list cannot
    dominate. Result lies in [0, 1 + bonus_cap].
    """
    if r is None:
        r = config.NL_MODIFIER
    if bonus_cap is None:
        bonus_cap = config.FIELD_BONUS_CAP
    qs = sorted((q for q in qualities if q > 0), reverse=True)
    if not qs:
        return 0.0
    best = qs[0]
    bonus = sum(q * (r ** (j + 1)) for j, q in enumerate(qs[1:]))
    return best + min(bonus_cap, bonus)
