"""Country and language code helpers — shared portfolio authority.

Consumed by eidr-wikidata (`bmr/country.py`) and BMR-Review
(`eidr_dedup_score/normalize.py`); the SU→SUHH crosswalk previously lived as a
duplicate in each and is now single-homed here (register R1 / OVERLAPS.md 9a).

EIDR country-code convention (portfolio-wide):
  * ISO 3166-1 alpha-2 for currently ACTIVE countries
  * ISO 3166-3 alpha-4 for countries that no longer exist
  * UN M49 integer-3 for regions
  * "XX" = unknown

Because the code sets are distinguishable by shape, the alpha-2 form of a
dissolved/renamed country is always wrong for EIDR: Wikidata's P297 emits "SU"
for the USSR, but EIDR requires the alpha-4 "SUHH". ``normalize_country_code``
performs that year-INDEPENDENT code-set rewrite.

Why a static table and not ``dq_country_validity``: that table has no
"former alpha-2" column, so the SU↔SUHH crosswalk — the exact datum needed —
cannot be derived from it. ISO 3166-3 is a stable, rarely-extended historical
set, so a small explicit map is appropriate. Every target below is a valid
alpha-4 code in dq_country_validity; every source is absent from it (verified
2026-07-25). Add entries here — never fork them back into a consumer.

"CS" is ambiguous in ISO 3166-3 (Czechoslovakia CSHH vs Serbia and Montenegro
CSXX); the Czechoslovakia reading is kept, overwhelmingly the common case in
film metadata. A Serbia-and-Montenegro record coded "CS" would need per-record
disambiguation, not attempted here.

Longer-term this module also grows the year-aware validity reader over
``dq_country_validity`` and the language crosswalk over ``language_registry``
(register Phase 1.4).
"""

from __future__ import annotations

# The public surface, as DICTIONARY.md documents it (2026-10-02).
# Star-imports (BMR-Review's shims use them) now take only these names,
# not the stdlib and third-party modules this file imports.
__all__ = [
    "OBSOLETE_ALPHA2_TO_ALPHA4",
    "UNKNOWN_COUNTRY",
    "country_list",
    "normalize_country_code",
]

# The code for "country unknown". Only valid ALONE: it cannot be combined
# with a real code (the portfolio's convention, register R1).
UNKNOWN_COUNTRY = "XX"

# Former ISO 3166-1 alpha-2 codes of dissolved/renamed countries → alpha-4.
OBSOLETE_ALPHA2_TO_ALPHA4: dict[str, str] = {
    "SU": "SUHH",   # U.S.S.R., dissolved 1991
    "YU": "YUCS",   # Yugoslavia (SFR), dissolved 1992
    "CS": "CSHH",   # Czechoslovakia, dissolved 1993 (not S&M CSXX)
    "DD": "DDDE",   # German Democratic Republic (East Germany), merged 1990
    "BU": "BUMM",   # Burma (former name of Myanmar)
}


def normalize_country_code(code: str | int | None) -> str:
    """Return the EIDR-canonical form of one country code.

    Rewrites the alpha-2 form of a dissolved/renamed country to its ISO 3166-3
    alpha-4 code (SU → SUHH); leaves every other code untouched — active
    alpha-2, existing alpha-4, M49 region integers, and "XX". Uppercased and
    whitespace-stripped; empty/None → "". Pure and year-independent, so both
    the Wikidata ingest path and the de-dupe comparators can call it.

    An ``int`` is taken as an M49 region code and given in the three-digit
    form a string carries: ``150`` → ``"150"``, ``19`` → ``"019"`` (0.68.0).
    """
    # None and int both reach this from real callers (spreadsheet cells and
    # JSON numbers); an int raised AttributeError on .strip() until 0.68.0
    # (dictionary audit 2026-10-02). M49 codes are three digits with leading
    # zeros ("019" Americas), and a numeric STRING passes through unchanged,
    # so an int is padded to match it -- str(19) would give "19", which is no
    # code at all. bool is an int subclass but never a country code.
    if code is None:
        return ""
    if isinstance(code, int) and not isinstance(code, bool):
        return f"{code:03d}"
    c = str(code).strip().upper()
    if not c:
        return ""
    return OBSOLETE_ALPHA2_TO_ALPHA4.get(c, c)


def country_list(codes) -> list[str]:
    """The Country of Origin values for one row, in the EIDR convention.

    Each code is normalised (``normalize_country_code``), blanks and repeats
    are dropped in order, and ``XX`` is kept only when it is the ONLY code:
    beside a real country it is dropped (register R1). No codes at all gives
    ``["XX"]``, the plan's S6 default, so every row states the field.
    Extracted 2026-10-17 (C2) from eidr-wikidata ``CountryValidator.
    validate_list``'s XX rule; eidr-imdb wrote ``XX`` beside real codes.
    """
    out: list[str] = []
    for code in codes or ():
        c = normalize_country_code(code)
        if c and c not in out:
            out.append(c)
    real = [c for c in out if c != UNKNOWN_COUNTRY]
    return real or [UNKNOWN_COUNTRY]
