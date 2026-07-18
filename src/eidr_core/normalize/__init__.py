"""Text/title/ID normalization primitives (planned; not yet extracted).

Will hold: Unicode fold (NFC/NFKD + combining-mark strip + casefold),
homoglyph maps (Latin/Cyrillic/Greek, Turkish dotless-i class), roman/word
numeral parsing, date and ISO-duration parsing, and EIDR-ID/ShortDOI
normalization.

Seeds: BMR-Review ``normalize.py`` (richest — primary seed), eidr-wikidata
``bmr/dedup._norm`` + ``bmr/title_clean``, eidr-dq
``homoglyph_remediation`` maps, EIDR MCP ``_sanitize_field`` (copy-pasted
twice there) and ``_verify_shortdoi_on_write``.

Normalization BEHAVIOR is part of the compare-spec so the node.js side can
match it without sharing this code.
"""
