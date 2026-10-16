"""eidr_core.altid_audit (C5, 0.54.0): the surfaces whose wrong answer is silent.

The ladder itself is pinned by BMRtoAltID's suite (its 731-line test_audit
runs against this module since the adoption) and by the release's back to
back differential on the live mirror. What is tested here is what only this
module decides: the two quarantine modes, the ledger gate, containment, and
that the batch size and the single-row form never change an answer -- a
batching bug would produce plausible, wrong lines, not an error.
"""
from __future__ import annotations

import pytest

from eidr_core.altid_audit import (
    AliasResolution,
    AltId,
    AuditRow,
    MirrorClient,
    MirrorError,
    audit,
    audit_rows,
    same_relation,
)
from eidr_core.altidtool_io import AltIdRow, emission_problem
from eidr_core.ids import TOMBSTONE_ID

E1 = "10.5240/7791-8534-2C23-9030-8610-5"
E2 = "10.5240/FB57-D43B-1EED-CAD7-929C-N"


class Fake:
    """MirrorClient's three batch methods over in-memory rows.

    ``alt_ids``: ``(content_id, type, domain, value, relation)``.
    """

    def __init__(self, alt_ids=(), aliases=None):
        self.alt_ids = list(alt_ids)
        self.aliases = dict(aliases or {})
        self.batches = 0

    def resolve_aliases(self, ids):
        self.batches += 1
        out = {}
        for i in ids:
            cur, depth = i, 0
            while cur in self.aliases and depth < 10:
                cur, depth = self.aliases[cur], depth + 1
            out[i] = AliasResolution(cur, depth, cur in self.aliases)
        return out

    def lookup_alt_ids(self, kinds):
        want, out = set(kinds), {}
        for cid, t, d, v, rel in self.alt_ids:
            if rel in (None, "", "IsSameAs") and (t, d or "", v) in want:
                out.setdefault((t, d or "", v), set()).add(cid)
        return out

    def existing_alt_ids(self, ids):
        out: dict = {}
        for cid, t, d, v, rel in self.alt_ids:
            if cid in ids:
                out.setdefault(cid, {}).setdefault((t, d or "", v), set()).add(rel or "")
        return out


def row(n, asserted, *alts, **kw):
    return AuditRow(sheet_row=n, row_id=str(n), asserted_raw=asserted,
                    asserted_id=asserted, asserted_invalid=False,
                    alt_ids=tuple(alts), **kw)


A = AltId("Proprietary", "a.com", "1", "", "Alt ID 1")
B = AltId("Proprietary", "b.com", "2", "", "Alt ID 2")


def test_row_quarantine_withholds_the_row_and_names_the_collateral():
    # A is on E2, so a row asserting E1 has an identity finding on A.
    fake = Fake([(E2, "Proprietary", "a.com", "1", None)])
    [r] = audit_rows([row(4, E1, A, B)], fake)
    assert [f.error_class for f in r.findings] == ["ASSERTED_ID_MISMATCH"]
    assert r.additions == () and r.collateral == (B,) and not r.clean


def test_alt_id_quarantine_withholds_only_the_alt_id_in_conflict():
    fake = Fake([(E2, "Proprietary", "a.com", "1", None)])
    [r] = audit_rows([row(4, E1, A, B)], fake, quarantine="alt_id")
    assert [f.error_class for f in r.findings] == ["ASSERTED_ID_MISMATCH"]
    assert r.lines == [f"{E1}\tProprietary\t2\tb.com"]
    assert r.collateral == () and not r.clean


def test_a_row_level_finding_withholds_the_row_in_either_mode():
    # Nothing to write against when the asserted ID itself is invalid.
    bad = AuditRow(4, "4", "nonsense", "", True, "malformed", (A,))
    for mode in ("row", "alt_id"):
        [r] = audit_rows([bad], Fake(), quarantine=mode)
        assert r.additions == () and r.collateral == (A,)
        assert r.findings[0].error_class == "INVALID_ASSERTED_ID"


def test_the_ledger_gate_skips_and_counts_without_reporting():
    seen = []

    def contributed(eidr_id, alt):
        seen.append((eidr_id, alt.value))
        return alt.value == "1"
    [r] = audit_rows([row(4, E1, A, B)], Fake(), contributed=contributed)
    assert r.lines == [f"{E1}\tProprietary\t2\tb.com"]
    assert r.already_contributed == 1 and r.findings == ()
    assert seen == [(E1, "1"), (E1, "2")]


def test_rule_7_is_per_alt_id_and_presence_is_silent():
    fake = Fake([(E1, "Proprietary", "a.com", "1", "Deprecated"),
                 (E1, "Proprietary", "b.com", "2", None)])
    [r] = audit_rows([row(4, E1, A, B)], fake)
    assert [f.error_class for f in r.findings] == ["ALT_ID_RELATION_CONFLICT"]
    assert r.additions == () and r.already_present == 1 and r.relation_conflicts == 1
    assert r.clean          # rule 7 never questions which record the row is


def test_batch_size_and_the_single_row_form_never_change_an_answer():
    fake = Fake([(E2, "Proprietary", "a.com", "1", None),
                 (E1, "Proprietary", "c.com", "9", None)],
                aliases={E2: E1})
    C = AltId("Proprietary", "c.com", "8", "", "Alt ID 3")
    rows = [row(4, E1, A, B), row(5, E1, B), row(6, "", A), row(7, E2, C, B),
            row(8, E1, C)]
    one_batch = [r._replace(row=None) for r in audit_rows(rows, fake)]
    per_row = [r._replace(row=None) for r in audit_rows(rows, fake, batch_alt_ids=1)]
    assert one_batch == per_row
    singles = [audit(w.asserted_id, w.alt_ids, client=fake)._replace(row=None)
               for w in rows]
    # Findings carry no row identity, so the single-row form must agree.
    assert singles == per_row


def test_audit_reads_and_validates_the_id_it_is_given():
    r = audit(E1.lower(), [B], client=Fake())
    assert r.effective_id == E1 and r.lines == [f"{E1}\tProprietary\t2\tb.com"]
    r = audit("10.5240/7791-8534-2C23-9030-8610-6", [B], client=Fake())
    assert r.findings[0].error_class == "INVALID_ASSERTED_ID"
    with pytest.raises(ValueError):
        audit(E1, [B])


def test_an_unexpected_error_is_contained_to_its_row_but_a_mirror_error_is_not():
    def boom(eidr_id, alt):
        if alt.value == "1":
            raise KeyError("one row's bug")
        return False
    results = list(audit_rows([row(4, E1, A), row(5, E1, B)], Fake(),
                              contributed=boom))
    assert isinstance(results[0].error, KeyError) and results[0].audited == 0
    assert results[1].lines == [f"{E1}\tProprietary\t2\tb.com"]

    def mirror_down(eidr_id, alt):
        raise MirrorError("connection reset")
    with pytest.raises(MirrorError):
        list(audit_rows([row(4, E1, A)], Fake(), contributed=mirror_down))


def test_unknown_quarantine_and_table_are_refused():
    with pytest.raises(ValueError):
        list(audit_rows([], Fake(), quarantine="none"))
    with pytest.raises(ValueError):
        MirrorClient(None, alt_id_table="content_core")


def test_same_relation_treats_blank_as_is_same_as():
    assert same_relation({""}, "IsSameAs") and same_relation({"IsSameAs"}, " ")
    assert not same_relation({"Deprecated"}, "")


def test_emission_problem_order_and_wording():
    assert emission_problem(AltIdRow(E1, "", "v")) == (
        "MISSING_ALT_ID_TYPE", "Alt ID value 'v' has no Alt ID Type; AltIDTool requires one.")
    cls, detail = emission_problem(AltIdRow(E1, "", "v"), source="Alt ID 3")
    assert detail.startswith("Column 'Alt ID 3' has a value")
    cls, detail = emission_problem(AltIdRow(E1, "Proprietary", "café", "a.com"))
    assert cls == "NON_ASCII_VALUE" and detail.startswith("Alt ID Value")
    assert emission_problem(AltIdRow(E1, "IMDB", "tt1")) is None


def test_a_deleted_record_is_never_written_to():
    # A deleted record aliases the tombstone, and the tombstone is a valid
    # record: following the chain and writing there would put the row's Alt
    # IDs on the tombstone (0.55.0). Asserting the tombstone itself is the
    # same case.
    fake = Fake(aliases={E1: TOMBSTONE_ID})
    for asserted in (E1, TOMBSTONE_ID):
        for mode in ("row", "alt_id"):
            [r] = audit_rows([row(4, asserted, A, B)], fake, quarantine=mode)
            assert [f.error_class for f in r.findings] == ["ASSERTED_ID_DELETED"]
            assert r.additions == () and r.collateral == (A, B) and not r.clean
            assert r.effective_id == TOMBSTONE_ID


def test_a_blank_domain_is_sent_as_the_mirrors_empty_domain():
    # The mirror stores a named type's blank domain as '' and never NULL.
    # Sending NULL (before 0.57.0) matched no IMDB or ISAN row at all, so
    # their conflicts were silently never found.
    seen = []

    class Cur:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, sql, params):
            seen.append((sql, params))

        def fetchall(self):
            return []

    class Conn:
        def cursor(self):
            return Cur()

    MirrorClient(Conn()).lookup_alt_ids([("IMDB", "", "tt1"), ("Proprietary", "a.com", "1")])
    sql, params = seen[0]
    assert params[1] == ["", "a.com"]
    assert "COALESCE(a.domain, '') = k.d" in sql
