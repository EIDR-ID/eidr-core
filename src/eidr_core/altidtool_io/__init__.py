"""AltIDTool input-file I/O — THE shared line format implementation.

The EIDR AltIDTool consumes tab-separated lines:

    EIDR_ID <TAB> Type <TAB> Value [<TAB> Domain] [<TAB> Relation]

Canonical composition rules (extracted 2026-08-04 from eidr-wikidata
``bmr/altidtool.py``, the production feed generator — register Phase 3
item 3 / OVERLAPS row 4; format contract: ``specs/altidtool-format.md``):

* No header line.
* **Named types** (IMDB, ISAN, …) carry NO Domain column; **Proprietary**
  rows carry the domain in column 4.
* **Relation is emitted only when non-empty** (blank/absent ≡ IsSameAs to
  the registry). When a named-type row needs a Relation (e.g. Deprecated),
  an EMPTY Domain placeholder keeps the tab positions consistent, so
  Relation is always column 5 when present.
* Lines are therefore 3, 4, or 5 columns wide. ``parse_line`` accepts all
  three shapes (and tolerates BMRtoAltID's fixed-5 output, where trailing
  empties collapse to the same row).

BMR-Review's dedupe pipeline does not emit this format; MCP's
``eidrtoaltid.py`` is a different artifact (an extract REPORT with a header
and its own columns) and is deliberately NOT unified here.
"""
from __future__ import annotations

import os
from collections.abc import Iterable
from typing import NamedTuple

__all__ = ["AltIdRow", "AltIdRemoval", "format_line", "write_lines", "parse_line",
           "multi_form_domains",
           "parse_edit_line"]


class AltIdRow(NamedTuple):
    eidr_id: str
    alt_type: str
    value: str
    domain: str = ""
    relation: str = ""


class AltIdRemoval(NamedTuple):
    """A REMOVAL line, which the AltIDTool also accepts (spec v1.1, 2026-09-11):
    one column removes every alternate ID from the record; two columns remove
    every ID of that type; three columns with an EMPTY value likewise remove
    the type. ``alt_type`` is "" for remove-all. Producers in this portfolio
    never emit these (they add); the python-tools ``AltIDTool`` reads them, and
    it needed a shared parser that knows the shape so that vendoring this
    module does not break its removal path."""
    eidr_id: str
    alt_type: str = ""


def format_line(eidr_id: str, alt_type: str, value: str,
                domain: str = "", relation: str = "") -> str:
    """Compose one AltIDTool line per the canonical rules above."""
    if domain:
        line = f"{eidr_id}\t{alt_type}\t{value}\t{domain}"
        if relation:
            line = f"{line}\t{relation}"
    else:
        if relation:
            # empty Domain placeholder keeps Relation at column 5
            line = f"{eidr_id}\t{alt_type}\t{value}\t\t{relation}"
        else:
            line = f"{eidr_id}\t{alt_type}\t{value}"
    return line


def write_lines(path: str | os.PathLike[str],
                rows: Iterable[AltIdRow | tuple[str, ...]]) -> int:
    """Write rows (AltIdRow or plain tuples) to ``path`` as an AltIDTool
    input file (UTF-8, LF). Returns the row count."""
    n = 0
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(format_line(*r) + "\n")
            n += 1
    return n


def parse_line(line: str) -> AltIdRow:
    """Parse a 3/4/5-column AltIDTool line back into an AltIdRow."""
    parts = line.rstrip("\r\n").split("\t")
    if not 3 <= len(parts) <= 5:
        raise ValueError(f"not an AltIDTool line ({len(parts)} columns): {line!r}")
    parts += [""] * (5 - len(parts))
    return AltIdRow(*parts)


def parse_edit_line(line: str) -> AltIdRow | AltIdRemoval | None:
    """Parse one line of an AltIDTool EDIT file: an addition (``AltIdRow``),
    a removal (``AltIdRemoval``), or ``None`` for a blank or ``//`` comment
    line. This is the superset ``parse_line`` refuses: ``parse_line`` stays
    strict (3-5 columns, no comments) because the feed generators that call
    it must never emit a removal by accident.

    Whitespace: only the line terminator is stripped before splitting -- a
    tab is significant and an empty domain column between type and relation
    carries meaning; each column's own surrounding whitespace is trimmed.
    """
    body = line.rstrip("\r\n")
    if not body.strip() or body.lstrip().startswith("//"):
        return None
    cols = [c.strip() for c in body.split("\t")]
    eidr_id = cols[0]
    if not eidr_id:
        raise ValueError(f"not an AltIDTool edit line (no EIDR ID in column 1): {line!r}")
    if len(cols) == 1:
        return AltIdRemoval(eidr_id)
    if len(cols) == 2:
        return AltIdRemoval(eidr_id, cols[1])
    if len(cols) > 5:
        raise ValueError(f"not an AltIDTool line ({len(cols)} columns): {line!r}")
    if not cols[2]:
        return AltIdRemoval(eidr_id, cols[1])
    cols += [""] * (5 - len(cols))
    return AltIdRow(*cols)


def multi_form_domains() -> frozenset[str]:
    """Proprietary domains exempt from rule 6 (altidtool-format v1.4), lowercase.

    Rule 6 withholds a second ``IsSameAs`` value of one Kind as a conflict.
    A handful of Kinds are multi-valued BY REGISTRY PRACTICE -- most records
    carrying them already hold several identity values -- and rule 6 must not
    fire there. The set is DECLARED in ``specs/multi_form_kinds.json`` with
    the measurement that justifies each entry, because it cannot be derived:
    v1.3 derived it from ``uri_mapping.json`` entry counts and that was wrong
    on both counts measured 2026-09-26 (duplicate entries are alternate URL
    templates of one form; ``trakt.tv`` numeric and ``trakt.tv/movies`` slug
    are separate registry Kinds, and ``trakt.tv`` holds 20,931 numeric values
    with two records carrying more than one).

    Hosted here, not in a consumer, because it is portfolio data about the
    registry: BMRtoAltID (row audit, T10) and eidr-wikidata (AltIDTool writer)
    must exempt the same Kinds, and BMRtoAltID has no domain table of its own.
    Compare a Kind's domain lowercased; named types (IMDB, ISAN, ...) are
    never in the set.
    """
    import json
    from importlib.resources import files

    raw = json.loads((files("eidr_core") / "specs" / "multi_form_kinds.json")
                     .read_text(encoding="utf-8"))
    return frozenset(str(e["domain"]).strip().lower() for e in raw["domains"])
