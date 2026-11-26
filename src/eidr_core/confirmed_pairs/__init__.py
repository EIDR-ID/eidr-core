"""The confirmed-pair history: every adjudicated source-ID / EIDR-ID pair, kept
as append-only history (reconciliation component C6).

Ruled in eidr-core-ops ``PHASE2-3-INTERFACES-2026-10-15.md`` (C6) and built on
the operator's instruction of 2026-11-24, relayed by eidr-imdb
(``HANDOFF-TO-EIDR-CORE-2026-11-24-...``, section 1): *"Keep an historical list
of all confirmed IMDb/EIDR ID pairs. eidr-wikidata needs to do a similar thing
for Wikidata/EIDR ID pairs -- both applications should use a similar method to
record and retain confirmed Alt ID pairs."* The source is eidr-wikidata's
``confirmed_pairs`` table (``storage/db.py``). What the instruction changed
from that table, and why each change is here:

* **History, never overwritten.** eidr-wikidata's table is one row per pair,
  replaced in place (``INSERT OR REPLACE``) and deleted when a newer export
  disagrees, so "what did we believe on 2026-12-01?" has no answer there.
  Here every write is an INSERT. A pair that is superseded, contradicted,
  merged, aliased or withdrawn gets a new *ending row* that points at the
  row it ends (``ends_event``); the ended row is never touched.
* **Rejections are recorded.** A reviewer's "not this record" is a verdict
  (``rejected``), so the next cycle can refuse to propose the pair again
  (eidr-imdb R4.1d; operator 2026-09-21: an adjudicated pair is not
  re-matched).
* **One table for every source.** ``source`` (``imdb``, ``wikidata``, ...)
  is a column, so both projects keep the same rows under the same rules, in
  their own database (storage stays per consumer, as ruled).

THE MODEL
---------
A row is either a **verdict** (``ends_event`` NULL: this pair was confirmed or
rejected, from ``effective_at``) or an **ending** (``ends_event`` = the
verdict's ``event_id``: that verdict stopped holding at the ending's
``effective_at``, for ``end_reason``). A verdict is *in force at T* when it
took effect at or before T and no ending of it took effect at or before T.
The unique index on ``ends_event`` lets the database itself refuse a second
ending of one verdict, so two writers racing cannot both end it.

A new verdict on a (source, source_id, eidr_id) whose verdict in force says
something else ends that one (``superseded``) in the same write. One that
says the same thing (same verdict, relation and provenance) writes nothing,
so re-loading the same export is a no-op rather than a doubling of history.
A verdict on a DIFFERENT EIDR ID for the same source ID ends nothing: two
records legitimately claiming one source ID is a finding for a human
(eidr-imdb's *The Smurfs*, C1), so a caller that decides it is a
contradiction says so with :func:`end_pairs` (``contradicted``).

Aliases are followed on READ, never by rewriting a row:
:func:`follow_aliases` hands the stored EIDR IDs to
``lookup.resolve_aliases`` and returns each record beside where its ID points
now. The history keeps the ID that was adjudicated, which is what an audit
needs.

STORAGE AND SQL
---------------
:func:`ddl` is the one reference schema; it runs unchanged on PostgreSQL,
DuckDB and SQLite (TEXT, INTEGER, CHECK, ``IF NOT EXISTS``; times as
ISO-8601 UTC text with a fixed width, so text order IS time order on every
engine and no driver converts them). Every helper takes a DB-API connection
the caller opened; eidr-core declares no driver.

The SQL is written once with ``?`` placeholders. The placeholder the driver
wants is decided from the connection, deliberately and never by trial:
``paramstyle=`` when the caller passes it, otherwise the ``paramstyle`` of
the driver module the connection's class comes from (``psycopg`` and
``psycopg2``: pyformat, so ``?`` becomes ``%s``; ``duckdb`` and ``sqlite3``:
qmark, kept). A connection whose driver cannot be identified raises
``ValueError`` asking for ``paramstyle=`` rather than guessing.

The module writes no backup (eidr-wikidata's request, 2026-11-24, that the
read-back trigger its match-state backup): a write takes ``on_write``, a
callable run after the write is committed, so the consumer's own backup runs
on the event that changed the state.
"""
from __future__ import annotations

import re
import secrets
import sys
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import date, datetime, timedelta, timezone
from typing import Any, NamedTuple

from eidr_core.altidtool_io import is_identity_relation
from eidr_core.bmr_rows import REGISTRY_IDS_COLUMN, SOURCE_ASSERTED_COLUMN
from eidr_core.ids import is_valid_eidr_id
from eidr_core.lookup import AliasResult, resolve_aliases
from eidr_core.verdicts import Resolution

__all__ = [
    "DECIDERS",
    "DEFAULT_TABLE",
    "END_REASONS",
    "VERDICTS",
    "PairRecord",
    "WriteResult",
    "ddl",
    "end_pairs",
    "ensure_table",
    "ever_rejected",
    "follow_aliases",
    "history",
    "in_force",
    "is_confirmed",
    "is_rejected",
    "pairs_from_verdicts",
    "record",
]

VERDICTS = ("confirmed", "rejected")

# Who decided. "import" is for rows seeded from an earlier list that did not
# keep per-pair authority (eidr-wikidata's BMR-Review bulk export mixes
# rule-cleared and human rows in two columns); calling those "human" or
# "rule" would invent provenance the source never had.
DECIDERS = ("human", "rule", "import")

# Why a verdict stopped holding. "superseded" is written by record() itself
# when a newer verdict on the same pair says something else; the rest are a
# caller's decision through end_pairs():
#   contradicted -- another verdict (usually on another record) shows it wrong
#   merged       -- the EIDR record was merged away (its survivor carries on)
#   aliased      -- the EIDR record became an alias and the caller chose to
#                   end rather than follow it (follow_aliases needs no ending)
#   withdrawn    -- retracted, with no replacement
END_REASONS = ("superseded", "contradicted", "merged", "aliased", "withdrawn")

DEFAULT_TABLE = "pair_verdicts"

# A plain or schema-qualified identifier (eidr-imdb may keep the table in a
# schema). The name is put into SQL text, so it must never carry a caller's
# data; same rule as altidtool_io.identity_relation_sql.
_SQL_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?")

# Fixed-width UTC text: lexicographic order equals chronological order on
# every engine, and a date-only bound can be expressed exactly.
_TIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"

_COLUMNS = ("event_id", "ends_event", "source", "source_id", "eidr_id", "relation",
            "verdict", "decided_by", "basis", "sheet", "sheet_row", "c4_status",
            "note", "effective_at", "end_reason", "run", "recorded_at")


class PairRecord(NamedTuple):
    """One adjudicated pair: the single record type both consumers use.

    To WRITE, fill the first five fields (and any provenance you have) and pass
    it to :func:`record`; the stored fields (``event_id``, ``ended_at``, ...)
    must be left at their defaults. Reads return it with them filled.

    ``relation`` is ``""`` for IsSameAs (the identity claim; ``IsSameAs`` and
    ``None`` are stored as ``""``, rule 1 of altidtool-format) or the
    clarifying relation BMR-Review's reviewer chose (``Deprecated``,
    ``IsDerivedFrom``, ...). ``basis`` is what decided it: the BMR-Review
    assessment for a rule (``Accept: sole match``), the reviewer's code for a
    human (``CORRECT_PICK``). ``c4_status`` is the ``verdicts.Resolution``
    status the verdict came from.
    """

    source: str
    source_id: str
    eidr_id: str
    verdict: str
    decided_by: str
    relation: str = ""
    basis: str = ""
    sheet: str = ""
    sheet_row: int | None = None
    c4_status: str = ""
    note: str = ""
    effective_at: str = ""      # "" on write: the call's `at`
    run: str = ""
    # -- stored; filled on read -------------------------------------------
    event_id: str = ""
    recorded_at: str = ""
    ended_at: str | None = None
    end_reason: str | None = None
    end_run: str | None = None

    @property
    def is_identity(self) -> bool:
        """True for an IsSameAs pair (``altidtool_io.is_identity_relation``)."""
        return is_identity_relation(self.relation)

    @property
    def live(self) -> bool:
        """True when no ending is known for it (in the view that returned it)."""
        return self.ended_at is None


class WriteResult(NamedTuple):
    """What a write changed. ``written`` are the new verdicts as stored;
    ``ended`` the verdicts this write ended, with their ending filled in;
    ``unchanged`` the inputs that matched the verdict already in force."""

    written: tuple[PairRecord, ...]
    ended: tuple[PairRecord, ...]
    unchanged: tuple[PairRecord, ...]

    @property
    def changed(self) -> bool:
        return bool(self.written or self.ended)


# -- schema ------------------------------------------------------------------

def _table(table: str) -> str:
    if not _SQL_IDENTIFIER.fullmatch(table or ""):
        raise ValueError(f"not a SQL table identifier: {table!r}")
    return table


def ddl(table: str = DEFAULT_TABLE) -> str:
    """The reference schema, as SQL statements separated by ``;\\n``.

    Portable on purpose (PostgreSQL, DuckDB, SQLite): no SERIAL or sequence
    (``event_id`` is minted by the writer), no TIMESTAMP (drivers disagree on
    what they return for it), no partial index. Text columns default to
    ``''`` rather than NULL because the mirror taught the portfolio what a
    NULL-or-empty split costs (2026-09-23, ``identity_relation_sql``); the
    only NULLs are the columns whose absence means something (``ends_event``
    and ``end_reason`` on a verdict row, an unknown ``sheet_row``).
    """
    t = _table(table)
    base = t.rsplit(".", 1)[-1]   # an index name cannot be schema-qualified in PG
    return f"""CREATE TABLE IF NOT EXISTS {t} (
  event_id     TEXT PRIMARY KEY,          -- minted by the writer; sorts in write order
  ends_event   TEXT,                      -- NULL: a verdict row; else the verdict this row ends
  source       TEXT NOT NULL,             -- 'imdb', 'wikidata', ... (lower case)
  source_id    TEXT NOT NULL,             -- the source's ID (tt0111161, Q172241)
  eidr_id      TEXT NOT NULL,             -- the EIDR ID as adjudicated; never rewritten
  relation     TEXT NOT NULL DEFAULT '',  -- '' = IsSameAs; else the clarifying relation
  verdict      TEXT NOT NULL CHECK (verdict IN ('confirmed', 'rejected')),
  decided_by   TEXT NOT NULL CHECK (decided_by IN ('human', 'rule', 'import')),
  basis        TEXT NOT NULL DEFAULT '',  -- the BMR-Review assessment or the reviewer's code
  sheet        TEXT NOT NULL DEFAULT '',  -- the sheet the verdict was read from
  sheet_row    INTEGER,                   -- its row there
  c4_status    TEXT NOT NULL DEFAULT '',  -- verdicts.Resolution.status
  note         TEXT NOT NULL DEFAULT '',
  effective_at TEXT NOT NULL,             -- ISO-8601 UTC; on an ending row, the end time
  end_reason   TEXT CHECK (end_reason IS NULL OR end_reason IN
                 ('superseded', 'contradicted', 'merged', 'aliased', 'withdrawn')),
  run          TEXT NOT NULL DEFAULT '',  -- the consumer's run ID
  recorded_at  TEXT NOT NULL              -- ISO-8601 UTC wall clock of the write
);
CREATE INDEX IF NOT EXISTS {base}_source_idx ON {t} (source, source_id);
CREATE INDEX IF NOT EXISTS {base}_eidr_idx ON {t} (eidr_id);
CREATE UNIQUE INDEX IF NOT EXISTS {base}_one_end_idx ON {t} (ends_event)"""


def ensure_table(conn, *, table: str = DEFAULT_TABLE, commit: bool = True) -> None:
    """Create the table and its indexes if they do not exist (idempotent).

    Statements run one at a time because SQLite's ``execute`` refuses more
    than one. A consumer with its own migrations may run :func:`ddl` there
    instead; the schema is the same either way.
    """
    cur = _cursor(conn)
    try:
        for stmt in ddl(table).split(";\n"):
            cur.execute(stmt)
    finally:
        _close(conn, cur)
    if commit:
        conn.commit()


# -- connection plumbing -----------------------------------------------------

def _is_duckdb(conn) -> bool:
    return type(conn).__module__.split(".")[0] in ("duckdb", "_duckdb")


def _cursor(conn):
    # DuckDB's cursor() opens a SECOND connection with its own transaction
    # (measured on 1.5.1: a rollback on the connection left the cursor's
    # insert standing), so a write through it could not be atomic with
    # anything. The DuckDB connection is itself a cursor (execute,
    # executemany, fetchall), so it is used directly.
    return conn if _is_duckdb(conn) else conn.cursor()


def _close(conn, cur) -> None:
    if cur is not conn:
        cur.close()


def _paramstyle(conn, paramstyle: str | None) -> str:
    style = paramstyle
    if style is None:
        mod = sys.modules.get(type(conn).__module__.split(".")[0])
        style = getattr(mod, "paramstyle", None)
        if style is None:
            raise ValueError(
                f"cannot tell the paramstyle of a {type(conn).__module__}."
                f"{type(conn).__name__} connection; pass paramstyle='qmark' "
                f"(DuckDB, SQLite) or 'format' (psycopg, psycopg2)")
    if style == "qmark":
        return "qmark"
    if style in ("format", "pyformat"):
        # pyformat drivers (psycopg, psycopg2) accept positional %s too.
        return "format"
    raise ValueError(f"unsupported paramstyle {style!r}; use 'qmark' or 'format'")


def _sql(text: str, style: str) -> str:
    # The module's SQL holds no literal '?' or '%', so the swap is exact.
    return text.replace("?", "%s") if style == "format" else text


def _fetch(cur) -> list[tuple[Any, ...]]:
    # eidr-wikidata's pool uses a dict row factory; read both (as lookup does).
    return [tuple(r.values()) if isinstance(r, dict) else tuple(r) for r in cur.fetchall()]


# -- normalising ---------------------------------------------------------------

def _utc_text(value: datetime | date | str | None, *, end_of_day: bool = False) -> str:
    """One fixed-width UTC string from a datetime, a date or ISO-8601 text.

    A bare date as a BOUND (``end_of_day``) means the end of that UTC day:
    "what did we believe on 2026-12-01" counts what was recorded during it.
    A naive datetime is taken as UTC, the portfolio's convention for stored
    times (eidr-wikidata's run_log).
    """
    if value is None:
        dt = datetime.now(timezone.utc)
    elif isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        dt = datetime(value.year, value.month, value.day)
        if end_of_day:
            dt += timedelta(days=1, microseconds=-1)
    else:
        text = str(value).strip()
        if len(text) == 10:          # YYYY-MM-DD
            return _utc_text(date.fromisoformat(text), end_of_day=end_of_day)
        # fromisoformat on 3.10 does not read a trailing Z.
        dt = datetime.fromisoformat(text[:-1] + "+00:00" if text.endswith("Z") else text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime(_TIME_FORMAT)


def _norm_source(source: str) -> str:
    s = (source or "").strip().casefold()
    if not s:
        raise ValueError("source is required ('imdb', 'wikidata', ...)")
    return s


def _norm_source_id(source_id: str) -> str:
    s = (source_id or "").strip()
    if not s:
        raise ValueError("source_id is required")
    return s


def _norm_eidr(eidr_id: str) -> str:
    # Stored upper case, as the registry and the mirror write it, so one
    # record is one key however a sheet cased it.
    e = (eidr_id or "").strip().upper()
    if not is_valid_eidr_id(e):
        raise ValueError(f"not a valid EIDR Content ID: {eidr_id!r}")
    return e


def _norm_relation(relation: str | None) -> str:
    return "" if is_identity_relation(relation) else str(relation).strip()


def _key(source: str, source_id: str, eidr_id: str) -> tuple[str, str, str]:
    return _norm_source(source), _norm_source_id(source_id), _norm_eidr(eidr_id)


def _same_claim(a: PairRecord, b: PairRecord) -> bool:
    # What makes a re-load a no-op. `run`, `note` and the times are left out:
    # loading the same verdict again in a new run is not a new verdict.
    return (a.verdict, a.relation, a.decided_by, a.basis, a.sheet, a.sheet_row,
            a.c4_status) == (b.verdict, b.relation, b.decided_by, b.basis, b.sheet,
                             b.sheet_row, b.c4_status)


class _Ids:
    """event_id: hex microseconds of the write, the ordinal within it, then
    random. Fixed width, so the text sorts in write order, which breaks ties
    between rows sharing an effective_at (a supersession and its ending)."""

    def __init__(self) -> None:
        self._base = time.time_ns() // 1000
        self._n = 0

    def __call__(self) -> str:
        self._n += 1
        return f"{self._base:016x}{self._n:06x}{secrets.token_hex(5)}"


# -- reading -------------------------------------------------------------------

_A_COLS = ", ".join(f"a.{c}" for c in _COLUMNS)


def _select(conn, table: str, *, where: Sequence[tuple[str, Any]], at: str | None,
            open_only: bool, paramstyle: str | None) -> list[PairRecord]:
    """Verdict rows with their ending (if any, and if it took effect by `at`)."""
    t = _table(table)
    params: list[Any] = []
    join = "e.ends_event = a.event_id"
    if at is not None:
        join += " AND e.effective_at <= ?"
        params.append(at)
    conds = ["a.ends_event IS NULL"]
    for clause, value in where:
        conds.append(clause)
        params.append(value)
    if at is not None:
        conds.append("a.effective_at <= ?")
        params.append(at)
    if open_only:
        conds.append("e.event_id IS NULL")
    sql = (f"SELECT {_A_COLS}, e.effective_at, e.end_reason, e.run "
           f"FROM {t} a LEFT JOIN {t} e ON {join} "
           f"WHERE {' AND '.join(conds)} ORDER BY a.effective_at, a.event_id")
    cur = _cursor(conn)
    try:
        cur.execute(_sql(sql, _paramstyle(conn, paramstyle)), params)
        rows = _fetch(cur)
    finally:
        _close(conn, cur)
    return [_from_row(r) for r in rows]


def _from_row(r: tuple[Any, ...]) -> PairRecord:
    d = dict(zip(_COLUMNS, r[:len(_COLUMNS)], strict=True))
    ended_at, end_reason, end_run = r[len(_COLUMNS):]
    return PairRecord(
        source=d["source"], source_id=d["source_id"], eidr_id=d["eidr_id"],
        verdict=d["verdict"], decided_by=d["decided_by"], relation=d["relation"] or "",
        basis=d["basis"] or "", sheet=d["sheet"] or "",
        sheet_row=None if d["sheet_row"] is None else int(d["sheet_row"]),
        c4_status=d["c4_status"] or "", note=d["note"] or "",
        effective_at=d["effective_at"], run=d["run"] or "", event_id=d["event_id"],
        recorded_at=d["recorded_at"], ended_at=ended_at, end_reason=end_reason,
        end_run=end_run)


def _filters(source: str, source_id: str | None, eidr_id: str | None,
             verdict: str | None = None) -> list[tuple[str, Any]]:
    where: list[tuple[str, Any]] = [("a.source = ?", _norm_source(source))]
    if source_id is not None:
        where.append(("a.source_id = ?", _norm_source_id(source_id)))
    if eidr_id is not None:
        where.append(("a.eidr_id = ?", _norm_eidr(eidr_id)))
    if verdict is not None:
        if verdict not in VERDICTS:
            raise ValueError(f"verdict must be one of {VERDICTS}, not {verdict!r}")
        where.append(("a.verdict = ?", verdict))
    return where


def in_force(conn, *, source: str, source_id: str | None = None,
             eidr_id: str | None = None, verdict: str | None = None,
             at: datetime | date | str | None = None, table: str = DEFAULT_TABLE,
             paramstyle: str | None = None) -> list[PairRecord]:
    """The verdicts in force, now or as of ``at``.

    ``at=None`` is "now": every verdict with no ending at all. With ``at``, a
    verdict counts when it took effect by then and was not yet ended, so
    ``in_force(conn, source="imdb", source_id="tt0111161", at="2026-12-01")``
    is what we believed about that title on that day (a bare date means the
    end of it, UTC). Omit ``source_id`` and ``eidr_id`` to read a whole source
    in one query, which is how a batch builds its sets. The returned records
    show no ending: in that view they had none.
    """
    bound = None if at is None else _utc_text(at, end_of_day=True)
    return _select(conn, table, where=_filters(source, source_id, eidr_id, verdict),
                   at=bound, open_only=True, paramstyle=paramstyle)


def history(conn, *, source: str, source_id: str | None = None,
            eidr_id: str | None = None, table: str = DEFAULT_TABLE,
            paramstyle: str | None = None) -> list[PairRecord]:
    """Every verdict ever recorded, oldest first, each with its ending
    (``ended_at``, ``end_reason``, ``end_run``) when it has one."""
    return _select(conn, table, where=_filters(source, source_id, eidr_id),
                   at=None, open_only=False, paramstyle=paramstyle)


def is_confirmed(conn, source: str, source_id: str, eidr_id: str, *,
                 identity_only: bool = True, at: datetime | date | str | None = None,
                 table: str = DEFAULT_TABLE, paramstyle: str | None = None) -> bool:
    """Is this pair confirmed (now, or as of ``at``)?

    ``identity_only=True`` (the default) counts only an IsSameAs confirmation,
    because that is what "a confirmed pair" licenses: writing the source ID
    onto the record as an identity Alt ID, and gating full-cast verification.
    A confirmed ``Deprecated`` or ``IsDerivedFrom`` pair is adjudicated but is
    NOT a sameness claim; pass ``identity_only=False`` to ask "adjudicated as
    confirmed under any relation" (the re-match gate).
    """
    found = in_force(conn, source=source, source_id=source_id, eidr_id=eidr_id,
                     verdict="confirmed", at=at, table=table, paramstyle=paramstyle)
    return any(r.is_identity for r in found) if identity_only else bool(found)


def is_rejected(conn, source: str, source_id: str, eidr_id: str, *,
                at: datetime | date | str | None = None, table: str = DEFAULT_TABLE,
                paramstyle: str | None = None) -> bool:
    """Is a rejection of this pair in force (now, or as of ``at``)? This is
    the gate that keeps a reviewer's "not this record" from being proposed
    again; a later confirmation supersedes it and lifts the gate."""
    return bool(in_force(conn, source=source, source_id=source_id, eidr_id=eidr_id,
                         verdict="rejected", at=at, table=table, paramstyle=paramstyle))


def ever_rejected(conn, source: str, source_id: str, eidr_id: str | None = None, *,
                  table: str = DEFAULT_TABLE, paramstyle: str | None = None) -> bool:
    """Was this pair (or, without ``eidr_id``, any pairing of this source ID)
    ever rejected, whether or not the rejection still holds?"""
    return any(r.verdict == "rejected" for r in
               history(conn, source=source, source_id=source_id, eidr_id=eidr_id,
                       table=table, paramstyle=paramstyle))


def follow_aliases(records: Iterable[PairRecord], *, mirror_conn,
                   max_depth: int = 10) -> list[tuple[PairRecord, AliasResult]]:
    """Each record beside where its EIDR ID points now in the registry.

    One ``lookup.resolve_aliases`` call on the distinct IDs, against the
    MIRROR connection (``mirror_conn``; not the history's own). The records
    are not changed and nothing is written: the history keeps the ID that
    was adjudicated. Only ``AliasResult.usable`` (outcome ``live``) names a
    record to write to; a tombstoned, cyclic or missing target is the
    caller's finding.
    """
    recs = list(records)
    resolved = resolve_aliases([r.eidr_id for r in recs], conn=mirror_conn,
                               max_depth=max_depth)
    return [(r, resolved[r.eidr_id]) for r in recs]


# -- writing -------------------------------------------------------------------

def _validate_input(p: PairRecord, at: str) -> PairRecord:
    if p.event_id or p.recorded_at or p.ended_at or p.end_reason or p.end_run:
        raise ValueError("record() takes new verdicts; leave event_id, recorded_at "
                         "and the ending fields empty (end a verdict with end_pairs)")
    if p.verdict not in VERDICTS:
        raise ValueError(f"verdict must be one of {VERDICTS}, not {p.verdict!r}")
    if p.decided_by not in DECIDERS:
        raise ValueError(f"decided_by must be one of {DECIDERS}, not {p.decided_by!r}")
    source, source_id, eidr_id = _key(p.source, p.source_id, p.eidr_id)
    return p._replace(source=source, source_id=source_id, eidr_id=eidr_id,
                      relation=_norm_relation(p.relation),
                      effective_at=_utc_text(p.effective_at) if p.effective_at else at)


def _open_verdicts(conn, table: str, keys: set[tuple[str, str, str]],
                   paramstyle: str | None) -> dict[tuple[str, str, str], list[PairRecord]]:
    """The verdicts with no ending, for the keys a write touches."""
    found: list[PairRecord] = []
    pairs = {(s, sid) for s, sid, _ in keys}
    # A big batch (an export re-load) reads each source once; a small one
    # reads per source ID, so recording one verdict never scans a source.
    if len(pairs) > 100:
        for source in sorted({s for s, _ in pairs}):
            found += _select(conn, table, where=_filters(source, None, None), at=None,
                             open_only=True, paramstyle=paramstyle)
    else:
        for source, source_id in sorted(pairs):
            found += _select(conn, table, where=_filters(source, source_id, None),
                             at=None, open_only=True, paramstyle=paramstyle)
    out: dict[tuple[str, str, str], list[PairRecord]] = {}
    for r in found:
        k = (r.source, r.source_id, r.eidr_id)
        if k in keys:
            out.setdefault(k, []).append(r)
    return out


def _ending_row(ended: PairRecord, *, event_id: str, at: str, reason: str,
                decided_by: str, note: str, run: str, now: str) -> tuple[Any, ...]:
    # The ending repeats the pair and verdict it ends, so a reader scanning
    # raw rows sees what stopped without joining.
    return (event_id, ended.event_id, ended.source, ended.source_id, ended.eidr_id,
            ended.relation, ended.verdict, decided_by, "", "", None, "", note, at,
            reason, run, now)


def _verdict_row(p: PairRecord) -> tuple[Any, ...]:
    return (p.event_id, None, p.source, p.source_id, p.eidr_id, p.relation, p.verdict,
            p.decided_by, p.basis, p.sheet, p.sheet_row, p.c4_status, p.note,
            p.effective_at, None, p.run, p.recorded_at)


def _check_order(old: PairRecord, at: str) -> None:
    if at < old.effective_at:
        raise ValueError(
            f"history is kept in time order: an ending at {at} cannot end the "
            f"verdict on ({old.source}, {old.source_id}, {old.eidr_id}) that took "
            f"effect at {old.effective_at}")


def _write(conn, table: str, rows: list[tuple[Any, ...]], *, commit: bool,
           paramstyle: str | None) -> None:
    if not rows:
        return
    sql = _sql(f"INSERT INTO {_table(table)} ({', '.join(_COLUMNS)}) "
               f"VALUES ({', '.join('?' for _ in _COLUMNS)})", _paramstyle(conn, paramstyle))
    # commit=True: this call owns the transaction, so the endings and the
    # verdicts that replace them land together or not at all. DuckDB needs an
    # explicit BEGIN (it autocommits); psycopg and sqlite3 open one implicitly.
    if commit and _is_duckdb(conn):
        conn.begin()
    cur = _cursor(conn)
    try:
        cur.executemany(sql, rows)
        if commit:
            conn.commit()
    except BaseException:
        if commit:
            conn.rollback()
        raise
    finally:
        _close(conn, cur)


def record(conn, pairs: Iterable[PairRecord], *, run: str = "",
           at: datetime | date | str | None = None, table: str = DEFAULT_TABLE,
           commit: bool = True, paramstyle: str | None = None,
           on_write: Callable[[WriteResult], object] | None = None) -> WriteResult:
    """Append new verdicts, ending what they supersede, in one transaction.

    Per (source, source_id, eidr_id), in input order: a verdict that matches
    the one in force (verdict, relation and provenance) is ``unchanged`` and
    writes nothing; any other ends every verdict in force on that key
    (``superseded``, at the new verdict's ``effective_at``) and is appended.
    ``effective_at`` on an input backdates it (seeding from an older list);
    empty means ``at`` (default now). A verdict older than the one it would
    supersede raises ``ValueError``: an ending before its start would make
    the as-of answer meaningless. ``run`` fills an input's empty ``run``.

    ``commit=True`` commits (and on failure rolls back) the connection's
    transaction; inside a transaction of your own pass ``commit=False`` and
    commit yourself. ``on_write(result)`` runs after the commit and only when
    something changed, so a consumer's backup sees committed state; an
    exception from it propagates, but the write has already landed, and a
    retry is a no-op because re-recording is idempotent.
    """
    now = _utc_text(None)
    default_at = _utc_text(at) if at is not None else now
    inputs = [_validate_input(p._replace(run=p.run or run), default_at) for p in pairs]
    keys = {(p.source, p.source_id, p.eidr_id) for p in inputs}
    open_by_key = _open_verdicts(conn, table, keys, paramstyle) if keys else {}

    new_id = _Ids()
    rows: list[tuple[Any, ...]] = []
    written: list[PairRecord] = []
    ended: list[PairRecord] = []
    unchanged: list[PairRecord] = []
    for p in inputs:
        k = (p.source, p.source_id, p.eidr_id)
        current = open_by_key.get(k, [])
        if len(current) == 1 and _same_claim(current[0], p):
            unchanged.append(current[0])
            continue
        for old in current:
            _check_order(old, p.effective_at)
            rows.append(_ending_row(old, event_id=new_id(), at=p.effective_at,
                                    reason="superseded", decided_by=p.decided_by,
                                    note="", run=p.run, now=now))
            ended.append(old._replace(ended_at=p.effective_at, end_reason="superseded",
                                      end_run=p.run))
        stored = p._replace(event_id=new_id(), recorded_at=now)
        rows.append(_verdict_row(stored))
        written.append(stored)
        open_by_key[k] = [stored]   # a later input in this batch supersedes it

    _write(conn, table, rows, commit=commit, paramstyle=paramstyle)
    result = WriteResult(tuple(written), tuple(ended), tuple(unchanged))
    if on_write is not None and result.changed:
        on_write(result)
    return result


def end_pairs(conn, keys: Iterable[tuple[str, str, str]], *, reason: str,
              decided_by: str, run: str = "", note: str = "",
              at: datetime | date | str | None = None, table: str = DEFAULT_TABLE,
              commit: bool = True, paramstyle: str | None = None,
              on_write: Callable[[WriteResult], object] | None = None) -> WriteResult:
    """End every verdict in force on each (source, source_id, eidr_id).

    For a pair that stops holding with no new verdict to replace it:
    ``contradicted``, ``merged``, ``aliased``, ``withdrawn`` (``superseded``
    is accepted too, for a caller recording a replacement elsewhere). A key
    with nothing in force is skipped, so ending twice is harmless. The
    ended verdicts come back in ``WriteResult.ended``. ``commit`` and
    ``on_write`` behave as in :func:`record`.
    """
    if reason not in END_REASONS:
        raise ValueError(f"reason must be one of {END_REASONS}, not {reason!r}")
    if decided_by not in DECIDERS:
        raise ValueError(f"decided_by must be one of {DECIDERS}, not {decided_by!r}")
    now = _utc_text(None)
    when = _utc_text(at) if at is not None else now
    wanted = {_key(*k) for k in keys}
    open_by_key = _open_verdicts(conn, table, wanted, paramstyle) if wanted else {}
    new_id = _Ids()
    rows: list[tuple[Any, ...]] = []
    ended: list[PairRecord] = []
    for k in sorted(open_by_key):
        for old in open_by_key[k]:
            _check_order(old, when)
            rows.append(_ending_row(old, event_id=new_id(), at=when, reason=reason,
                                    decided_by=decided_by, note=note, run=run, now=now))
            ended.append(old._replace(ended_at=when, end_reason=reason, end_run=run))
    _write(conn, table, rows, commit=commit, paramstyle=paramstyle)
    result = WriteResult((), tuple(ended), ())
    if on_write is not None and result.changed:
        on_write(result)
    return result


# -- from C4 verdicts ------------------------------------------------------------

def _candidates(row: Mapping[str, object], columns: Sequence[str], sheet_row: int) -> list[str]:
    out: list[str] = []
    for col in columns:
        for part in str(row.get(col) or "").split("|"):
            v = part.strip()
            if not v:
                continue
            # A bad ID in a column this portfolio wrote is a defect upstream;
            # dropping it would silently lose a rejection.
            out.append(_norm_eidr_at(v, col, sheet_row))
    return list(dict.fromkeys(out))


def _norm_eidr_at(value: str, column: str, sheet_row: int) -> str:
    try:
        return _norm_eidr(value)
    except ValueError:
        raise ValueError(f"row {sheet_row}, {column!r}: not a valid EIDR Content ID: "
                         f"{value!r}") from None


def pairs_from_verdicts(rows: Mapping[int, Mapping[str, object]],
                        verdicts: Iterable[Resolution], *, source: str, source_id_column: str,
                        sheet: str = "",
                        candidate_columns: Sequence[str] = (SOURCE_ASSERTED_COLUMN,
                                                            REGISTRY_IDS_COLUMN),
                        ) -> list[PairRecord]:
    """Turn C4 verdicts on an inbound sheet into pair records to :func:`record`.

    ``rows`` maps each sheet row number to its row (column header -> value),
    so a verdict is joined to its row by ``Resolution.sheet_row`` and a
    misaligned list cannot pair the wrong rows; ``verdicts`` are
    ``verdicts.Resolution`` objects. The rules (R6, and R4.1d for rejections):

    The default ``candidate_columns`` are where an inbound sheet carries the
    pairings the SOURCE proposed (``bmr_rows``, C2 ruling item 5): what a
    pipeline would propose again next cycle, so what a decisive verdict
    rejects.

    * ``CONFIRMED`` -> a ``confirmed`` pair (source ID, resolved ID) under the
      reviewer's relation, and a ``rejected`` pair for every other candidate
      in ``candidate_columns`` (default ``Source-Asserted EIDR ID`` and
      ``Registry EIDR ID(s)``: the pairings the source proposed).
    * ``NO_MATCH`` -> a ``rejected`` pair for every candidate.
    * Any other status decided nothing about the pair and yields nothing.

    ``decided_by`` is ``human`` when the row has a ``Human Review`` code and
    ``rule`` otherwise; ``basis`` is that code or the BMR-Review assessment.
    A row with no source ID yields nothing. A candidate that is not a valid
    EIDR ID raises ``ValueError`` naming the row.
    """
    src = _norm_source(source)
    out: list[PairRecord] = []
    for v in verdicts:
        if v.status not in ("CONFIRMED", "NO_MATCH"):
            continue
        row = rows[v.sheet_row]
        source_id = str(row.get(source_id_column) or "").strip()
        if not source_id:
            continue
        human = bool((v.human_review or "").strip())
        base = PairRecord(source=src, source_id=source_id, eidr_id="", verdict="",
                          decided_by="human" if human else "rule",
                          basis=(v.human_review if human else v.assessment).strip(),
                          sheet=sheet, sheet_row=v.sheet_row, c4_status=v.status)
        confirmed = _norm_eidr(v.resolved_id) if v.status == "CONFIRMED" else ""
        if confirmed:
            out.append(base._replace(eidr_id=confirmed, verdict="confirmed",
                                     relation=_norm_relation(v.relation)))
        for cand in _candidates(row, candidate_columns, v.sheet_row):
            if cand != confirmed:
                out.append(base._replace(eidr_id=cand, verdict="rejected"))
    return out
