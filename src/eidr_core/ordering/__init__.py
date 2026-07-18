"""Canonical EIDR record ordering (planned; not yet extracted).

Will hold: the single implementation of the portfolio's canonical sort —
uniform casefold comparators, resource-name-first title ranking, credit
name flattening, IMDb-first alt-ID ordering.

Seeds: XML_to_JSON star-mode sort (NOTE its OriginalLanguage sort at :985
and BMR-input lang/country sorts at :3166-3170 are case-sensitive bugs to
fix on extraction) and BMR-Review ``report.py::render_record``, which
explicitly reproduces the XML_to_JSON rules today.

The ordering RULES are also written into ``specs/`` (normalized-record
spec) so non-Python implementations can match them.
"""
