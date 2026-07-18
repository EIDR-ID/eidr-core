"""Pure record-comparison primitives (planned; not yet extracted).

Will hold: field comparators parameterized by the versioned compare-spec
in ``specs/`` — runtime tolerance (max(5 min, 10%)), precision-aware
release-date windows, year arbitration, string-similarity wrappers.
No I/O; engines in each program compose these their own way.

Seed: eidr-dq ``matching/compare.py`` (explicitly written for extraction:
``compare_runtime``, ``compare_release_date``, ``compare_year_arbitration``,
``parse_iso_date``).

Scoring engines themselves stay per-program (BMR-Review, eidr-wikidata,
the De-Dupe UI module in eidr-ui-nextjs); each proves conformance against
``specs/golden-pairs``.
"""
