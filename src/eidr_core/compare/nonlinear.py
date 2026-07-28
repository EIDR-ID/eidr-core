"""
Non-linear aggregation of a list of per-pair match qualities.

Given matched-pair qualities q1 >= q2 >= ... (each in [0,1]; 1.0 for an exact
controlled-vocabulary / Alt-ID match, the fuzzy score for text) and n
"opportunities", the aggregate is:

    score = sum_i q_(i) * r^(i-1)  /  sum_{j=1..n} r^(j-1)

The first match is worth the most; each additional match contributes r x the
previous one. When every opportunity is matched perfectly the score is 1.0.
With all-exact matches this reduces to (1 - r^k)/(1 - r^n).

r is config.NL_MODIFIER (Rovi: 0.75). n basis is config.LIST_DENOMINATOR.
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


def opportunities(len_a, len_b, basis=None):
    basis = basis or config.LIST_DENOMINATOR
    if len_a == 0 or len_b == 0:
        return 0
    return min(len_a, len_b) if basis == "min" else max(len_a, len_b)


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
