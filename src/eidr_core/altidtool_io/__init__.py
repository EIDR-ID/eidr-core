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

from typing import Iterable, NamedTuple

__all__ = ["AltIdRow", "format_line", "write_lines", "parse_line"]


class AltIdRow(NamedTuple):
    eidr_id: str
    alt_type: str
    value: str
    domain: str = ""
    relation: str = ""


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


def write_lines(path, rows: Iterable[AltIdRow | tuple]) -> int:
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
