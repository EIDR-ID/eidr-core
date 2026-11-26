"""eidr_core.confirmed_pairs (C6): the answers that would be wrong silently.

Every test runs on SQLite (stdlib, so CI always runs them) and again on
DuckDB when it is importable (eidr-wikidata's engine; CI installs no DuckDB,
so there it is skipped). The SQL is the same text on both, which is the
point: one reference schema and one set of queries. PostgreSQL is covered
by construction (the paramstyle test drives the ``%s`` form through a
psycopg-shaped wrapper) rather than by a server.

What is pinned: an as-of answer after a verdict changes, the ending row
that leaves the old verdict untouched, a rejection that survives as
history, an alias followed without rewriting the row, and a hook that sees
committed state.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from eidr_core import confirmed_pairs as cp
from eidr_core.ids import check_character
from eidr_core.lookup import AliasResult
from eidr_core.verdicts import Resolution


def _eidr(n: int) -> str:
    payload = f"{n:020X}"
    groups = "-".join(payload[i:i + 4] for i in range(0, 20, 4))
    return f"10.5240/{groups}-{check_character(payload)}"


A, B, C = _eidr(0xA1), _eidr(0xB2), _eidr(0xC3)


def _sqlite(path: Path):
    return sqlite3.connect(path)


def _duckdb(path: Path):
    duckdb = pytest.importorskip("duckdb")
    return duckdb.connect(str(path))


ENGINES = {"sqlite": (_sqlite, "db.sqlite"), "duckdb": (_duckdb, "db.duckdb")}


@pytest.fixture(params=sorted(ENGINES))
def opener(request, tmp_path):
    """A function that opens (another) connection to one database file."""
    open_, name = ENGINES[request.param]
    path = tmp_path / name
    return lambda: open_(path)


@pytest.fixture
def db(opener):
    conn = opener()
    cp.ensure_table(conn)
    cp.ensure_table(conn)        # idempotent
    yield conn
    conn.close()


def _count(conn) -> int:
    cur = conn.cursor()
    cur.execute(f"SELECT COUNT(*) FROM {cp.DEFAULT_TABLE}")
    n = cur.fetchall()[0][0]
    cur.close()
    return int(n)


def _pair(eidr_id=A, verdict="confirmed", **kw):
    kw.setdefault("decided_by", "human")
    return cp.PairRecord("imdb", "tt0111161", eidr_id, verdict, **kw)


# -- as-of, supersession and endings ------------------------------------------

def test_a_new_verdict_ends_the_old_one_and_the_past_stays_answerable(db):
    first = cp.record(db, [_pair(sheet="s1.xlsx", sheet_row=4, c4_status="CONFIRMED")],
                      run="r1", at="2026-11-20T10:00:00Z")
    assert len(first.written) == 1 and not first.ended
    second = cp.record(db, [_pair(verdict="rejected", basis="CORRECT_PICK")], run="r2",
                       at="2026-12-05T09:00:00+00:00")
    assert [e.end_reason for e in second.ended] == ["superseded"]

    # What did we believe about tt0111161 on 2026-12-01? The confirmation.
    then = cp.in_force(db, source="imdb", source_id="tt0111161", at="2026-12-01")
    assert [(r.eidr_id, r.verdict, r.sheet_row) for r in then] == [(A, "confirmed", 4)]
    assert then[0].live                      # in that view it had no ending
    now = cp.in_force(db, source="IMDB", source_id="tt0111161")
    assert [r.verdict for r in now] == ["rejected"]

    # The old row was not edited: history shows it whole, with its ending.
    hist = cp.history(db, source="imdb", source_id="tt0111161")
    assert [(r.verdict, r.end_reason, r.end_run) for r in hist] == [
        ("confirmed", "superseded", "r2"), ("rejected", None, None)]
    assert hist[0].ended_at == "2026-12-05T09:00:00.000000Z"
    assert hist[0].effective_at == "2026-11-20T10:00:00.000000Z"
    assert _count(db) == 3                   # two verdicts and one ending


def test_a_bare_date_bound_includes_that_whole_day(db):
    cp.record(db, [_pair()], at="2026-12-01T23:30:00Z")
    assert cp.is_confirmed(db, "imdb", "tt0111161", A, at="2026-12-01")
    assert not cp.is_confirmed(db, "imdb", "tt0111161", A, at="2026-11-30")


def test_recording_the_same_verdict_again_writes_nothing(db):
    calls = []
    cp.record(db, [_pair(basis="Accept: sole match", decided_by="rule")], run="r1",
              on_write=calls.append)
    again = cp.record(db, [_pair(basis="Accept: sole match", decided_by="rule")],
                      run="r2", on_write=calls.append)
    assert not again.changed and len(again.unchanged) == 1
    assert _count(db) == 1
    assert len(calls) == 1                   # no hook for a no-op


def test_end_pairs_withdraws_and_is_harmless_twice(db):
    cp.record(db, [_pair()], at="2026-11-01T00:00:00Z")
    out = cp.end_pairs(db, [("imdb", "tt0111161", A.lower())], reason="withdrawn",
                       decided_by="human", run="r9", at="2026-11-02T00:00:00Z")
    assert [(e.eidr_id, e.end_reason) for e in out.ended] == [(A, "withdrawn")]
    assert cp.in_force(db, source="imdb", source_id="tt0111161") == []
    assert cp.is_confirmed(db, "imdb", "tt0111161", A, at="2026-11-01T12:00:00Z")
    again = cp.end_pairs(db, [("imdb", "tt0111161", A)], reason="withdrawn",
                         decided_by="human")
    assert not again.changed and _count(db) == 2
    with pytest.raises(ValueError):
        cp.end_pairs(db, [("imdb", "tt0111161", A)], reason="forgotten", decided_by="human")


def test_the_database_refuses_a_second_ending_of_one_verdict(db):
    # Two writers racing would each read the verdict as open; the unique
    # index on ends_event is what stops both endings landing.
    written = cp.record(db, [_pair()]).written[0]
    cp.end_pairs(db, [("imdb", "tt0111161", A)], reason="withdrawn", decided_by="human")
    cur = db.cursor()
    with pytest.raises(Exception):  # noqa: B017 -- IntegrityError / ConstraintException
        cur.execute(f"INSERT INTO {cp.DEFAULT_TABLE} (event_id, ends_event, source, "
                    "source_id, eidr_id, verdict, decided_by, effective_at, end_reason, "
                    "recorded_at) VALUES ('x', ?, 'imdb', 'tt0111161', ?, 'confirmed', "
                    "'human', 'z', 'withdrawn', 'z')", [written.event_id, A])


def test_a_verdict_older_than_the_one_in_force_cannot_end_it(db):
    cp.record(db, [_pair()], at="2026-11-10T00:00:00Z")
    with pytest.raises(ValueError, match="time order"):
        cp.record(db, [_pair(verdict="rejected")], at="2026-11-09T00:00:00Z")
    assert _count(db) == 1


def test_an_ending_and_its_replacement_land_together_or_not_at_all(db, monkeypatch):
    # Force the replacement verdict's insert to fail (a duplicate event_id)
    # after its ending row: the ending must roll back with it, or the pair
    # would be left ended with nothing in force.
    ids = iter(["e1", "e2", "e1"])
    monkeypatch.setattr(cp._Ids, "__call__", lambda self: next(ids))
    cp.record(db, [_pair()])
    with pytest.raises(Exception):  # noqa: B017 -- the driver's integrity error
        cp.record(db, [_pair(verdict="rejected")])
    assert _count(db) == 1
    assert cp.is_confirmed(db, "imdb", "tt0111161", A)


def test_a_second_record_for_one_source_id_ends_nothing(db):
    # Two records claiming one source ID is a finding for a human (C1's
    # The Smurfs), never an automatic contradiction.
    cp.record(db, [_pair(A), _pair(B)])
    assert {r.eidr_id for r in cp.in_force(db, source="imdb", source_id="tt0111161")} == {A, B}


def test_a_batch_applies_in_input_order(db):
    out = cp.record(db, [_pair(), _pair(verdict="rejected")])
    assert len(out.written) == 2 and len(out.ended) == 1
    assert [r.verdict for r in cp.in_force(db, source="imdb")] == ["rejected"]


# -- rejection and relation -------------------------------------------------------

def test_rejection_gates_until_confirmed_and_stays_in_history(db):
    cp.record(db, [_pair(verdict="rejected")], at="2026-11-01T00:00:00Z")
    assert cp.is_rejected(db, "imdb", "tt0111161", A)
    assert not cp.is_confirmed(db, "imdb", "tt0111161", A)
    cp.record(db, [_pair()], at="2026-11-05T00:00:00Z")
    assert not cp.is_rejected(db, "imdb", "tt0111161", A)
    assert cp.is_confirmed(db, "imdb", "tt0111161", A)
    assert cp.ever_rejected(db, "imdb", "tt0111161", A)
    assert cp.ever_rejected(db, "imdb", "tt0111161")
    assert not cp.ever_rejected(db, "imdb", "tt0111161", B)
    assert not cp.ever_rejected(db, "wikidata", "tt0111161")


def test_relation_is_stored_once_and_a_clarifying_one_is_not_identity(db):
    cp.record(db, [_pair(A, relation="IsSameAs"), _pair(B, relation=" Deprecated ")])
    rows = {r.eidr_id: r for r in cp.in_force(db, source="imdb")}
    assert rows[A].relation == "" and rows[A].is_identity
    assert rows[B].relation == "Deprecated" and not rows[B].is_identity
    assert cp.is_confirmed(db, "imdb", "tt0111161", A)
    assert not cp.is_confirmed(db, "imdb", "tt0111161", B)
    assert cp.is_confirmed(db, "imdb", "tt0111161", B, identity_only=False)


def test_bad_input_is_refused_before_anything_is_written(db):
    for bad in (_pair(eidr_id="10.5240/NOPE"), _pair(verdict="maybe"),
                _pair(decided_by="robot"), _pair(event_id="x"),
                cp.PairRecord("", "tt1", A, "confirmed", "human")):
        with pytest.raises(ValueError):
            cp.record(db, [_pair(B), bad])
    assert _count(db) == 0


# -- the hook ----------------------------------------------------------------------

def test_the_hook_runs_after_commit_and_sees_the_write(db, opener):
    seen = []

    def backup(result):
        # A consumer's backup opens its own connection (eidr-wikidata's
        # backup_after_change does); it must find the rows already committed.
        other = opener()
        try:
            seen.append((len(result.written), _count(other)))
        finally:
            other.close()

    cp.record(db, [_pair()], on_write=backup)
    cp.end_pairs(db, [("imdb", "tt0111161", A)], reason="merged", decided_by="rule",
                 on_write=backup)
    assert seen == [(1, 1), (0, 2)]


# -- aliases -----------------------------------------------------------------------

class _Mirror:
    """content_core for lookup.resolve_aliases: {content_id: target_id}."""

    def __init__(self, core):
        self.core = core

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params):
        assert sql.startswith("SELECT content_id, target_id")
        self.out = [(i, self.core[i]) for i in params[0] if i in self.core]

    def fetchall(self):
        return self.out


def test_aliases_are_followed_on_read_without_rewriting_the_row(db):
    cp.record(db, [_pair(A), _pair(C, verdict="rejected")])
    mirror = _Mirror({A: B, B: None, C: None})
    got = dict((r.eidr_id, res) for r, res in
               cp.follow_aliases(cp.in_force(db, source="imdb"), mirror_conn=mirror))
    assert got[A] == AliasResult(B, (A, B), "live")
    assert got[C] == AliasResult(C, (C,), "live")
    assert {r.eidr_id for r in cp.history(db, source="imdb")} == {A, C}


# -- paramstyle ---------------------------------------------------------------------

class _FormatConn:
    """A psycopg-shaped connection over SQLite: it only accepts %s, so a ?
    reaching it means the translation was skipped."""

    def __init__(self, inner):
        self.inner = inner

    def cursor(self):
        return _FormatCursor(self.inner.cursor())

    def commit(self):
        self.inner.commit()

    def rollback(self):
        self.inner.rollback()


class _FormatCursor:
    def __init__(self, cur):
        self.cur = cur

    def _q(self, sql):
        assert "?" not in sql
        return sql.replace("%s", "?")

    def execute(self, sql, params=()):
        self.cur.execute(self._q(sql), params)

    def executemany(self, sql, rows):
        self.cur.executemany(self._q(sql), rows)

    def fetchall(self):
        return self.cur.fetchall()

    def close(self):
        self.cur.close()


def test_the_placeholder_follows_the_connection(tmp_path):
    inner = sqlite3.connect(tmp_path / "f.sqlite")
    conn = _FormatConn(inner)
    with pytest.raises(ValueError, match="paramstyle"):
        cp.in_force(conn, source="imdb")         # unknown driver: never guessed
    cp.ensure_table(conn)
    cp.record(conn, [_pair()], paramstyle="format")
    assert cp.is_confirmed(conn, "imdb", "tt0111161", A, paramstyle="pyformat")
    with pytest.raises(ValueError):
        cp.in_force(conn, source="imdb", paramstyle="named")
    inner.close()


def test_table_names_are_identifiers_only():
    assert "CREATE TABLE IF NOT EXISTS recon.pair_verdicts" in cp.ddl("recon.pair_verdicts")
    assert "pair_verdicts_one_end_idx ON recon.pair_verdicts" in cp.ddl("recon.pair_verdicts")
    with pytest.raises(ValueError):
        cp.ddl("pair_verdicts; DROP TABLE x")


# -- from C4 verdicts -----------------------------------------------------------------

def _res(sheet_row, status, resolved="", human="", assessment="Accept: sole match",
         relation=""):
    return Resolution(sheet_row, f"R{sheet_row}", status, resolved, "col", assessment,
                      human, (), "", relation)


def test_pairs_from_verdicts_records_the_choice_and_what_it_rejected():
    rows = {
        5: {"IMDb ID": "tt1", "Source-Asserted EIDR ID": "", "Registry EIDR ID(s)":
            f"{A} | {B}"},
        6: {"IMDb ID": "tt2", "Registry EIDR ID(s)": C},
        7: {"IMDb ID": "tt3", "Registry EIDR ID(s)": A},
        8: {"IMDb ID": "", "Registry EIDR ID(s)": A},
    }
    verdicts = [_res(5, "CONFIRMED", resolved=A, relation="IsSameAs"),
                _res(6, "NO_MATCH", human="SET_NOMATCH"),
                _res(7, "NEEDS_REVIEW"),
                _res(8, "CONFIRMED", resolved=A)]
    got = cp.pairs_from_verdicts(rows, verdicts, source="imdb", source_id_column="IMDb ID",
                                 sheet="bmr_001.xlsx")
    assert [(p.source_id, p.eidr_id, p.verdict, p.decided_by, p.basis, p.c4_status)
            for p in got] == [
        ("tt1", A, "confirmed", "rule", "Accept: sole match", "CONFIRMED"),
        ("tt1", B, "rejected", "rule", "Accept: sole match", "CONFIRMED"),
        ("tt2", C, "rejected", "human", "SET_NOMATCH", "NO_MATCH"),
    ]
    assert got[0].relation == "" and got[0].sheet == "bmr_001.xlsx" and got[0].sheet_row == 5

    with pytest.raises(KeyError):            # a verdict with no row is never guessed
        cp.pairs_from_verdicts({}, verdicts[:1], source="imdb", source_id_column="IMDb ID")
    with pytest.raises(ValueError, match="row 6"):
        cp.pairs_from_verdicts({6: {"IMDb ID": "tt2", "Registry EIDR ID(s)": "junk"}},
                               verdicts[1:2], source="imdb", source_id_column="IMDb ID")
