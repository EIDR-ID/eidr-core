"""BMR spreadsheet I/O (planned; not yet extracted).

Will hold: the BMR template schema, the family/repeat-group column model,
and the workbook reader + writer, so a template revision lands in exactly
one place.

Seeds (canonical implementations until extraction):
  * writer: eidr-wikidata ``src/eidr_wikidata/bmr/writer.py``
    (``FAMILIES`` + ``_expand_family``). BMR-Review vendors TWO copies of
    this file (``eidr_dedup_score/bmr_writer.py`` and ``audit/``) which
    become imports when this module lands.
  * reader: XML_to_JSON's BMR-input codec; BMRtoAltID's reader;
    eidr-wikidata ``scripts/combine_bmr_sheets.py``.
  * parallel reimplementation to retire: eidr-dq ``flatten.py`` repeat-group
    planner.
"""
