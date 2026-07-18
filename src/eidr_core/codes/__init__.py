"""Country and language code validation (planned; not yet extracted).

Data authorities (this module is a thin consumer — share-as-DATA):
  * Countries: ``eidr_dq_db.dq_country_validity`` (owned by eidr-dq),
    year-aware validity.
  * Languages: ``language_registry`` (owned by LanguageCode) — BCP-47 /
    ISO-639 / EIDR / DOI / CLDR crosswalk.

Portfolio code-set convention (operator, 2026-07-18): alpha-2 for ACTIVE
countries, alpha-4 (ISO 3166-3) for OBSOLETE countries, integer-3 (UN M49)
for regions — the code set is identifiable by inspection. Obsolete
countries stay alpha-4 (SUHH, not SU and not a successor recode).

Planned API: ``validate_country(code, year)``, ``normalize_country(code)``
(e.g. SU -> SUHH), ``validate_language(tag)``, ``map_language(tag, scheme)``.

Seeds: eidr-wikidata ``bmr/country.py::CountryValidator`` (the proven
dq_country_validity consumer), eidr-dq's three hardcoded country sets
(``iso3166_validator``, ``region_validator``, ``bcp47_validator`` — to be
consolidated onto the table, they currently disagree over XK/SU/YU).
"""
