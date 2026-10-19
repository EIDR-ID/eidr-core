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
  empties collapse to the same row). It refuses an empty Value and a ``//``
  comment, which are not additions (0.68.0).

Edit files (``parse_edit_line``) may also hold REMOVAL lines (spec v1.1,
narrowed by v1.6 on the operator's ruling of 2026-10-19): ``ID<TAB>Type``
removes every Alt ID of a named type, ``ID<TAB>Proprietary<TAB><TAB>Domain``
removes every Proprietary Alt ID of that domain, and every other removal is
refused -- above all any spelling that would remove ALL of a record's Alt
IDs, and a bare ``Proprietary`` removal that names no domain.

BMR-Review's dedupe pipeline does not emit this format; MCP's
``eidrtoaltid.py`` is a different artifact (an extract REPORT with a header
and its own columns) and is deliberately NOT unified here.
"""
from __future__ import annotations

import os
import re
from collections.abc import Iterable
from typing import NamedTuple

__all__ = ["AltIdRow", "AltIdRemoval", "format_line", "write_lines", "parse_line",
           "multi_form_domains",
           "parse_edit_line",
           "is_identity_relation", "identity_relation_sql",
           "emission_problem"]


class AltIdRow(NamedTuple):
    eidr_id: str
    alt_type: str
    value: str
    domain: str = ""
    relation: str = ""


class AltIdRemoval(NamedTuple):
    """A REMOVAL line from an AltIDTool edit file (spec v1.1; narrowed v1.6).

    ``parse_edit_line`` returns one of two shapes, and only these:

    * ``AltIdRemoval(id, "IMDB")`` -- remove every Alt ID of that NAMED type
      (``ID<TAB>IMDB``, or the same with an empty Value).
    * ``AltIdRemoval(id, "Proprietary", "themoviedb.org/movie")`` -- remove
      every Proprietary Alt ID whose domain is ``domain``
      (``ID<TAB>Proprietary<TAB><TAB>Domain``).

    ``alt_type`` is never empty and a Proprietary removal always carries its
    domain. Operator ruling, 2026-10-19: "Refuse removing all alt IDs. The
    pattern ID<tab>Proprietary<tab><tab>Domain should remove all IDs of that
    domain only (Proprietary by itself without a domain should be refused)."
    Before v1.6 a one-column line (or ``ID<TAB>``, ``ID<TAB><TAB>``) came back
    as ``AltIdRemoval(id, "")``, a remove-EVERYTHING sentinel that stray tabs
    could produce, and ``ID<TAB>Proprietary<TAB><TAB>Domain`` came back with
    the domain dropped -- a removal of every domain. Both are now refused or
    carried, so a caller that acts on ``alt_type`` alone would over-remove
    on a Proprietary line: act on ``domain`` too.

    ``domain`` was added in v1.6 with a default, so ``AltIdRemoval(id, t)``
    still constructs and attribute access is unchanged; a caller that unpacks
    a removal positionally into two names must take three. Producers in this
    portfolio never emit removals (they add); the python-tools ``AltIDTool``
    applies them, and it vendors this module.
    """
    eidr_id: str
    alt_type: str = ""
    domain: str = ""


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
    """Parse a 3/4/5-column AltIDTool ADDITION line back into an AltIdRow.

    Strict: raises ``ValueError`` for anything that is not an addition --
    a width outside 3-5, a ``//`` comment line, or an EMPTY (or
    whitespace-only) Value. Use ``parse_edit_line`` to read edit files,
    which may hold removals and comments.
    """
    body = line.rstrip("\r\n")
    # A comment is not an addition. Before 0.68.0 a ``//`` line with enough
    # tabs came back as a row whose eidr_id was the comment text (dictionary
    # audit 2026-10-02; 0.68.0).
    if body.lstrip().startswith("//"):
        raise ValueError(f"not an AltIDTool line (a // comment): {line!r}")
    parts = body.split("\t")
    if not 3 <= len(parts) <= 5:
        raise ValueError(f"not an AltIDTool line ({len(parts)} columns): {line!r}")
    # The spec reads a three-column line with an empty Value as a REMOVAL of
    # the type (v1.1), so returning it as an addition with value '' handed a
    # removal to code that only knows additions -- the accident parse_line's
    # strictness exists to prevent (dictionary audit 2026-10-02; 0.68.0).
    if not parts[2].strip():
        raise ValueError(f"not an AltIDTool addition (empty Value; the spec reads "
                         f"this as a removal -- use parse_edit_line): {line!r}")
    parts += [""] * (5 - len(parts))
    return AltIdRow(*parts)


def parse_edit_line(line: str) -> AltIdRow | AltIdRemoval | None:
    """Parse one line of an AltIDTool EDIT file: an addition (``AltIdRow``),
    a removal (``AltIdRemoval``), or ``None`` for a blank or ``//`` comment
    line. ``parse_line`` stays strict (3-5 columns, no comments, no empty
    Value) because the feed generators that call it must never emit a removal
    by accident; this function reads the edit-file superset (less one line
    ``parse_line`` still takes: an addition with an empty Type, refused here).

    Removals (spec v1.6, operator ruling 2026-10-19) -- a line is a removal
    when its Value is empty or absent:

    * ``ID<TAB>Type`` with a NAMED type -> ``AltIdRemoval(id, type)``.
    * ``ID<TAB>Proprietary<TAB><TAB>Domain`` -> ``AltIdRemoval(id,
      "Proprietary", domain)``: that domain's Proprietary Alt IDs only.

    Raises ``ValueError`` for every other removal: an empty Type (``ID``,
    ``ID<TAB>``, ``ID<TAB><TAB>``, ``ID<TAB><TAB><TAB>Domain``, ...), which
    would remove ALL of the record's Alt IDs; ``Proprietary`` with no domain;
    a Domain on a named-type removal; and a Relation on any removal. It also
    raises for an addition with an empty Type (``ID<TAB><TAB>value``), and
    for a line with no EIDR ID or more than five columns.

    Whitespace: only the line terminator is stripped before splitting -- a
    tab is significant and an empty domain column between type and relation
    carries meaning; each column's own surrounding whitespace is trimmed.
    Trailing empty columns (the fixed-5 dialect) change nothing.
    """
    body = line.rstrip("\r\n")
    if not body.strip() or body.lstrip().startswith("//"):
        return None
    cols = [c.strip() for c in body.split("\t")]
    if not cols[0]:
        raise ValueError(f"not an AltIDTool edit line (no EIDR ID in column 1): {line!r}")
    if len(cols) > 5:
        raise ValueError(f"not an AltIDTool line ({len(cols)} columns): {line!r}")
    # One- and two-column lines are padded like the rest, so every width is
    # judged by the same column rules below rather than by its width.
    cols += [""] * (5 - len(cols))
    eidr_id, alt_type, value, domain, relation = cols
    if value:
        # An addition the AltIDTool cannot place: it needs a Type. Before
        # v1.6 this came back as an AltIdRow with alt_type '' (dictionary
        # audit 2026-10-02; operator ruling 2026-10-19).
        if not alt_type:
            raise ValueError(f"not an AltIDTool line (a Value with no Type): {line!r}")
        return AltIdRow(*cols)
    # A removal. Each refusal below is a line whose literal reading removes
    # more than its author can have meant -- the failure is silent and lands
    # on the registry, so the parser refuses rather than guesses.
    if not alt_type:
        # Remove-all, however it is spelled. Stray tabs after an ID used to
        # produce it (``ID<TAB>``, ``ID<TAB><TAB>``), and so did a domain
        # with no type (``ID<TAB><TAB><TAB>Domain``): ruling 2026-10-19,
        # "Refuse removing
        # all alt IDs."
        raise ValueError(f"refused: an AltIDTool removal with no Type would remove "
                         f"every Alt ID on the record (spec v1.6): {line!r}")
    if relation:
        # The spec gives a removal no Relation; ignoring one would remove
        # every relation's IDs when the author asked for one relation's.
        raise ValueError(f"refused: an AltIDTool removal carries no Relation "
                         f"(spec v1.6): {line!r}")
    if alt_type.casefold() == "proprietary":
        if not domain:
            # Ruling 2026-10-19: "Proprietary by itself without a domain
            # should be refused" -- it would remove every domain's IDs.
            raise ValueError(f"refused: a Proprietary removal must name its Domain "
                             f"(ID<TAB>Proprietary<TAB><TAB>Domain; spec v1.6): {line!r}")
        return AltIdRemoval(eidr_id, alt_type, domain)
    if domain:
        # Domain qualifies Proprietary only (column table). On a named type
        # it cannot narrow the removal, so honouring the line would remove
        # the whole type when its author meant less.
        raise ValueError(f"refused: a Domain belongs to Proprietary removals only "
                         f"(spec v1.6): {line!r}")
    return AltIdRemoval(eidr_id, alt_type)


def multi_form_domains() -> frozenset[str]:
    """Proprietary domains exempt from rule 6 (altidtool-format v1.5), lowercase.

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

    An entry is listed on one of two bases, each recorded in the file
    (v1.5, 2026-10-02): ``measured`` (the registry's own practice, above) or
    ``ruled`` -- the operator declares a Kind two-form when its identifiers
    come in two forms nobody outside the registrant can reconcile
    (``mediafilm.ca``: numeric and ``mf-tt-N``, disjoint number ranges).
    Callers see one set either way; the basis matters only to whoever
    reviews the list.
    """
    import json
    from importlib.resources import files

    # The data is found through this module's PARENT package, never by its
    # literal name: a literal name made the vendoring tool refuse the whole
    # module (its residual-reference rule), which froze python-tools' vendored
    # copy at 0.34.1 from 0.39.0 on (dictionary audit, 2026-10-02). A vendored
    # copy carries no package data, so there this function says so plainly;
    # format_line / parse_line / write_lines work in a vendored copy as before.
    data = files(__name__.rpartition(".")[0]) / "specs" / "multi_form_kinds.json"
    if not data.is_file():
        raise RuntimeError(
            "multi_form_domains() reads the declared list from eidr-core's package "
            "data (specs/multi_form_kinds.json); a vendored copy does not carry it, "
            "so call it where eidr-core itself is installed")
    raw = json.loads(data.read_text(encoding="utf-8"))
    return frozenset(str(e["domain"]).strip().lower() for e in raw["domains"])


# -- the identity relation (0.47.0, BMR-Review's proposal) -------------------
# Rule 1 of altidtool-format: a blank relation MEANS IsSameAs, so "is this Alt
# ID an identity link?" admits a missing relation, an empty one and IsSameAs.
# The portfolio wrote that test out in about twenty places, and the copies are
# where it went wrong: on 2026-09-23 the mirror stored every absent relation
# as '' while the identity predicates admitted only NULL, and 69.6% of IMDb
# identity links were invisible to them. One definition, in both forms.

_IDENTITY_RELATIONS = frozenset({"", "issameas"})
_SQL_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?")


def is_identity_relation(relation: object) -> bool:
    """True when an Alt ID with this relation is an identity link.

    ``None``, an empty or whitespace-only string, and ``IsSameAs`` in any case
    are identity; any other relation (``IsDerivedFrom``, ``Deprecated``,
    ``IsEntirelyContainedBy``, ...) is not.
    """
    return relation is None or str(relation).strip().casefold() in _IDENTITY_RELATIONS


def identity_relation_sql(column: str = "relation") -> str:
    """The same test as a SQL condition for mirror queries.

    Returns ``(<column> IS NULL OR <column> = '' OR <column> = 'IsSameAs')``.
    ``column`` must be a plain identifier, optionally table-qualified
    (``a.relation``); anything else raises ``ValueError``, because this builds
    SQL text and must never carry a caller's data into it. The SQL compares
    ``IsSameAs`` exactly, as the mirror stores it; the Python test also folds
    case and whitespace.
    """
    if not _SQL_IDENTIFIER.fullmatch(column or ""):
        raise ValueError(f"not a SQL column identifier: {column!r}")
    return f"({column} IS NULL OR {column} = '' OR {column} = 'IsSameAs')"



# -- fit to write (0.54.0, reconciliation C5) --------------------------------
# Extracted from BMRtoAltID ``emit.emission_problem`` (content-sha1
# 64cb667f788b). The two checks are constraints of THIS format, not of any one
# producer: AltIDTool needs a Type, and its input is ASCII. Every producer of
# the format needs them, so they live beside ``format_line``.

_EMISSION_FIELDS = ("EIDR ID", "Alt ID Type", "Alt ID Value", "Alt ID Domain",
                    "Alt ID Relation")


def emission_problem(row: AltIdRow, *, source: str = "") -> tuple[str, str] | None:
    """Why this line cannot be written, or ``None`` if it can.

    Returns ``(error_class, detail)``, with ``error_class`` one of
    ``MISSING_ALT_ID_TYPE`` and ``NON_ASCII_VALUE``. A missing Type is
    reported first: it is a defect to fix in the source, where non-ASCII is a
    limit of the transport. ``source`` names where the Alt ID came from (a
    BMR sheet's column header); when given, the detail says the Type was to
    come from that column's Domain, which is how a BMR sheet carries it.
    """
    if not row.alt_type:
        if source:
            detail = (f"Column {source!r} has a value but its Domain column is "
                      f"empty, so no Alt ID Type can be derived.")
        else:
            detail = (f"Alt ID value {row.value!r} has no Alt ID Type; AltIDTool "
                      f"requires one.")
        return ("MISSING_ALT_ID_TYPE", detail)
    for label, value in zip(_EMISSION_FIELDS, (row.eidr_id, row.alt_type, row.value,
                                                row.domain, row.relation), strict=True):
        if value and not value.isascii():
            return ("NON_ASCII_VALUE",
                    f"{label} contains non-ASCII characters ({value!r}); AltIDTool "
                    f"input must be ASCII.")
    return None
