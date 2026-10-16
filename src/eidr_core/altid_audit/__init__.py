"""The Alt-ID audit ladder: verify Alt IDs against the mirror, then say which
additions are safe to make (reconciliation component C5).

Extracted 2026-10-15 from BMRtoAltID ``bmr_altid/audit.py`` (content-sha1
``a95b7f5aa740``) and ``bmr_altid/mirror.py`` (``593edc33e089``), on the
interface ruled in eidr-core-ops ``PHASE2-3-INTERFACES-2026-10-15.md``. The
input is Alt ID tuples, not sheet rows: reading a sheet (tab selection, the
Domain -> Type split, the registry's Type casing, a reviewer's ``RELATION:``
line applied to the row's Alt IDs, ``--write-only``) is the caller's, and so
is formatting the findings into a report.

The procedure, per row (BMRtoAltID's operator specification, 2026-08-26):

1. If the row has an asserted EIDR ID, follow its alias chain and write to the
   target instead. A chain that ends at the tombstone (``ids.TOMBSTONE_ID``)
   means the record was deleted: ``ASSERTED_ID_DELETED``, nothing written.
2. An Alt ID with an EXPRESSED relation other than IsSameAs is not audited:
   it asserts no identity, so it cannot conflict with another record's.
   Blank is the registry default and means IsSameAs, so blank IS audited.
3. Look each audited Alt ID up in the mirror, counting only rows whose
   relation is IsSameAs or absent.
4. Adjudicate. An Alt ID on more than one record is always an error. The
   row's Alt IDs must agree on one record, and with the asserted ID when
   there is one. Rule 6 (altidtool-format v1.4): a single-form Kind carries
   ONE identity value per record, so a second one -- on the row, or against
   one the record already claims -- is ``SAME_KIND_CONFLICT``. The Kinds the
   registry keeps multi-valued are exempt; pass
   ``altidtool_io.multi_form_domains()``. With none passed, Proprietary
   Kinds are not checked at all: unknown means exempt, because a false
   conflict withholds a row and a missed one costs nothing the registry's
   own rules do not catch.
5. Already on the target under the SAME relation (blank = IsSameAs) is
   skipped silently; under a DIFFERENT relation it is
   ``ALT_ID_RELATION_CONFLICT``, never written (one Alt ID must not sit on a
   record twice) and always reported. That is per Alt ID: the record's
   identity is not in question (ruling 2026-09-21).
6. A row with no asserted ID is never written against the record its Alt
   IDs agree on: an Alt ID match alone does not confirm a record. It is
   reported as ``UNASSERTED_RESOLVED`` (INFO); BMR-Review is where it goes.

Quarantine (ruled 2026-10-15, item 6). ``"row"``, BMRtoAltID's ruling: any
identity finding withholds every Alt ID of the row, and the ones not
themselves in conflict come back as ``collateral`` so the caller can list
them. ``"alt_id"``, eidr-wikidata's writer: an identity finding withholds
only its own Alt ID. Either way a finding with no Alt ID of its own (the
asserted ID is invalid, its alias chain does not end, the reviewer's relation
names another record, the record was deleted) leaves nothing to write
against, so it withholds the row; rule 7 and the emission checks are always per Alt ID.

Rows are audited in batches so the mirror is queried three times per batch,
not once per Alt ID (a 60k-row sheet at 200 Alt IDs a row is 12M lookups).
Results still come back one row at a time in input order, which keeps each
EIDR ID's lines together in an AltIDTool file.

Containment (BMRtoAltID's ruling, 2026-08-27): an unexpected error while
adjudicating one row comes back as that row's ``error``, with no lines and
no findings, and the rest of the batch carries on. ``MirrorError`` is never
contained: a mirror failure is systemic, and a run that went on would write
rows that are clean only because their lookups never happened (2026-08-26).
"""
from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Sequence
from typing import NamedTuple

from eidr_core.altidtool_io import (
    AltIdRow,
    emission_problem,
    format_line,
    is_identity_relation,
)
from eidr_core.db_schemas import assert_tables
from eidr_core.ids import TOMBSTONE_ID, fault

__all__ = [
    "ALT_ID_TABLES",
    "DEFAULT_BATCH_ALT_IDS",
    "FINDING_CLASSES",
    "INFO_CLASSES",
    "IS_SAME_AS",
    "MIRROR_NEEDS",
    "AliasResolution",
    "AltId",
    "AuditRow",
    "Finding",
    "MirrorClient",
    "MirrorError",
    "RowAudit",
    "audit",
    "audit_rows",
    "is_audited",
    "is_single_form",
    "kind_key",
    "same_relation",
]

# Alt IDs accumulated before a batch goes to the mirror. Sized so the
# unnest() arrays stay comfortable while the query count stays low.
DEFAULT_BATCH_ALT_IDS = 20_000

# Blank/NULL is the registry default and means IsSameAs (BMRtoAltID ruling
# 2026-08-26; specs/altidtool-format.md column 5).
IS_SAME_AS = "IsSameAs"

# Every class this module can put in a Finding. The names are BMRtoAltID's
# report vocabulary and keep its spelling (ruling 2026-10-11: vocabulary
# stable); their descriptions and the report's columns stay with the caller.
FINDING_CLASSES = frozenset({
    "INVALID_ASSERTED_ID", "ALIAS_DEPTH_EXCEEDED", "REVIEWER_RELATION_MISMATCH",
    "ASSERTED_ID_DELETED",
    "MULTI_RECORD_ALT_ID", "ASSERTED_ID_MISMATCH", "ALT_IDS_DISAGREE",
    "SAME_KIND_CONFLICT", "UNASSERTED_RESOLVED", "REVIEWER_RELATION_APPLIED",
    "ALT_ID_RELATION_CONFLICT", "MISSING_ALT_ID_TYPE", "NON_ASCII_VALUE",
})
# The two that report something learned rather than something wrong.
INFO_CLASSES = frozenset({"UNASSERTED_RESOLVED", "REVIEWER_RELATION_APPLIED"})

# The findings that question WHICH record a row is. Under quarantine "row"
# any of them withholds the row; the rest never do.
_IDENTITY_CLASSES = frozenset({
    "INVALID_ASSERTED_ID", "ALIAS_DEPTH_EXCEEDED", "REVIEWER_RELATION_MISMATCH",
    "ASSERTED_ID_DELETED",
    "MULTI_RECORD_ALT_ID", "ASSERTED_ID_MISMATCH", "ALT_IDS_DISAGREE",
    "SAME_KIND_CONFLICT",
})

# Declared for eidr_core.db_schemas.assert_tables, so schema breakage shows up
# at startup naming the contract version, not as a SQL error an hour into a
# 60k-row sheet.
MIRROR_NEEDS = {
    "content_core": ["content_id", "status", "target_id"],
    "content_alternate_ids_self": [
        "content_id", "alt_id", "id_type", "domain", "relation",
    ],
    "content_alternate_ids": [
        "content_id", "alt_id", "id_type", "domain", "relation",
    ],
}

# Alt IDs are never inherited (BMRtoAltID operator ruling 2026-08-27), so the
# two tables hold the same values and the choice cannot change a result.
# ``_self`` is the default because it names what the audit means: the Alt IDs
# a record asserts about itself, which is what AltIDTool writes to. The other
# is an escape hatch; a difference between them would be a mirror defect.
ALT_ID_TABLES = ("content_alternate_ids_self", "content_alternate_ids")


class MirrorError(RuntimeError):
    """Any failure talking to the mirror. Always fatal to a run."""


class AltId(NamedTuple):
    """One Alt ID as its source asserts it.

    Field order is BMRtoAltID's, so its tuples pass unchanged. ``source``
    names where the Alt ID came from (a sheet's column header) and is quoted
    in findings: an operator looking at a conflict needs to know which of 200
    columns to open. It plays no part in the audit.
    """

    alt_type: str
    domain: str
    value: str
    relation: str = ""
    source: str = ""

    @property
    def kind(self) -> tuple[str, str]:
        """The duplicate-identity key: Kind ``(Type, Domain)``.

        Register R8 (closed): a blank Domain matches only blank, never by
        resolved URL, so the IMDB type and the imdb.com domain stay two Kinds.
        """
        return (self.alt_type, self.domain)


def kind_key(alt: AltId) -> tuple[str, str, str]:
    """Full R8 identity: Kind ``(Type, Domain)`` plus value."""
    return (alt.alt_type, alt.domain, alt.value)


class AuditRow(NamedTuple):
    """One row to audit: the record it claims and the Alt IDs it carries.

    ``sheet_row`` and ``row_id`` only identify the row to the caller. The
    asserted ID arrives already read: ``asserted_id`` is the valid ID
    upper-cased, or "" when absent or invalid; ``asserted_invalid`` and
    ``asserted_reason`` (``ids.fault``'s text) say which. ``alt_ids`` arrive
    with any reviewer relation already applied (C4 item 10: applying it is
    the caller's step); ``reviewer_relation`` and ``relation_overrides`` say
    so for the report, and ``reviewer_relation_mismatch`` carries the detail
    when the relation named a record other than the asserted one.
    """

    sheet_row: int
    row_id: str
    asserted_raw: str
    asserted_id: str
    asserted_invalid: bool
    asserted_reason: str = ""
    alt_ids: tuple[AltId, ...] = ()
    reviewer_relation: str = ""
    relation_overrides: tuple[str, ...] = ()
    reviewer_relation_mismatch: str = ""


class Finding(NamedTuple):
    """One thing the audit found. ``alt_id`` is None for a row-level finding;
    ``relation`` is the Alt ID's own, or the reviewer's for
    ``REVIEWER_RELATION_APPLIED``; ``conflicting`` is sorted."""

    error_class: str
    alt_id: AltId | None
    detail: str
    effective_id: str = ""
    relation: str = ""
    conflicting: tuple[str, ...] = ()


class RowAudit(NamedTuple):
    """The audit of one row.

    ``additions`` are the lines safe to write (``lines`` formats them).
    ``collateral`` is, under quarantine ``"row"``, every Alt ID withheld only
    because another on the row is in conflict. ``clean`` means no identity
    finding. ``error`` is an unexpected exception contained to this row; when
    set, everything else is empty and the row's tallies are zero.
    """

    row: AuditRow
    effective_id: str = ""
    additions: tuple[AltIdRow, ...] = ()
    findings: tuple[Finding, ...] = ()
    collateral: tuple[AltId, ...] = ()
    clean: bool = False
    error: BaseException | None = None
    audited: int = 0
    skipped: int = 0
    already_present: int = 0
    relation_conflicts: int = 0
    already_contributed: int = 0
    alias_followed: bool = False

    @property
    def lines(self) -> list[str]:
        """``additions`` as AltIDTool lines, without line ends."""
        return [format_line(*a) for a in self.additions]


class AliasResolution(NamedTuple):
    """Where an asserted EIDR ID actually points."""

    target: str
    depth: int
    exceeded: bool


def is_audited(alt: AltId) -> bool:
    """True when this Alt ID asserts identity, so the audit tests it."""
    return is_identity_relation(alt.relation)


def is_single_form(alt: AltId, multi_form_domains: frozenset[str] | None) -> bool:
    """Does rule 6 apply to this Alt ID's Kind?

    Every named type is single-form. A Proprietary Kind is single-form unless
    its domain is in the multi-form set; with no set, unknown means exempt.
    """
    if alt.alt_type != "Proprietary":
        return True
    if multi_form_domains is None:
        return False
    return alt.domain.strip().casefold() not in multi_form_domains


def same_relation(existing: set[str], relation: str) -> bool:
    """Does ``relation`` match one the record already carries?

    Blank and ``IsSameAs`` are one relation on both sides; otherwise the
    names compare case-insensitively.
    """
    def norm(rel: str) -> str:
        rel = rel.strip()
        return IS_SAME_AS.casefold() if not rel else rel.casefold()
    want = norm(relation)
    return any(norm(r) == want for r in existing)


class MirrorClient:
    """Batched, read-only mirror (``eidr_mirror_db``) queries. One per run.

    ``conn`` is a DB-API connection the caller opened; eidr-core declares no
    driver. Each batch issues three statements whatever its size: alias
    resolution (iterated, capped), Alt ID -> content_id, and the target
    records' existing Alt IDs.
    """

    def __init__(self, conn, *, alt_id_table: str = ALT_ID_TABLES[0],
                 alias_status: str = "alias", max_alias_depth: int = 10):
        if alt_id_table not in ALT_ID_TABLES:
            raise ValueError(
                f"unknown alt id table {alt_id_table!r}; "
                f"expected one of {ALT_ID_TABLES}"
            )
        self._conn = conn
        self._table = alt_id_table
        self._alias_status = alias_status
        self._max_alias_depth = max_alias_depth

    @staticmethod
    def assert_schema() -> None:
        """Fail at startup when the mirror contract lacks what this needs."""
        assert_tables("eidr_mirror_db", MIRROR_NEEDS)

    def _query(self, sql: str, params: tuple):
        try:
            with self._conn.cursor() as cur:
                cur.execute(sql, params)
                return cur.fetchall()
        except Exception as exc:
            # A lookup failure aborts the run (BMRtoAltID ruling 2026-08-26).
            raise MirrorError(f"mirror query failed: {exc}") from exc

    def known_id_types(self) -> dict[str, str]:
        """``{uppercased type: the registry's own casing}``.

        For a caller to adopt the registry's casing before the audit, so a
        source saying ``imdb`` both matches and is written as ``IMDB``.
        Canonicalising up front keeps the lookups exact-match and on their
        indexes, which a ``lower()`` in the join would throw away.
        """
        rows = self._query(
            f"SELECT DISTINCT id_type FROM {self._table} "  # noqa: S608
            "WHERE id_type IS NOT NULL", ())
        out: dict[str, str] = {}
        for (id_type,) in rows:
            if id_type:
                out.setdefault(id_type.upper(), id_type)
        return out

    def resolve_aliases(self, eidr_ids: list[str]) -> dict[str, AliasResolution]:
        """Follow each ID's alias chain to its end.

        Capped at ``max_alias_depth`` hops (sheets do not carry deep chains;
        10 is BMRtoAltID's ruled cutoff) with a per-chain cycle guard, so a
        cyclic alias stops rather than spins. A non-alias resolves to itself
        at depth 0.
        """
        result = {i: AliasResolution(i, 0, False) for i in eidr_ids}
        if not eidr_ids:
            return result
        # Every chain still moving, keyed by the ORIGINAL id.
        frontier = {i: i for i in eidr_ids}
        seen = {i: {i} for i in eidr_ids}
        for depth in range(1, self._max_alias_depth + 1):
            targets = sorted(set(frontier.values()))
            rows = self._query(
                "SELECT content_id, target_id FROM content_core "
                "WHERE content_id = ANY(%s) AND status = %s "
                "AND target_id IS NOT NULL",
                (targets, self._alias_status),
            )
            hops = {cid: tid for cid, tid in rows if tid}
            if not hops:
                break
            nxt: dict[str, str] = {}
            for original, current in frontier.items():
                target = hops.get(current)
                if target is None:
                    continue
                if target in seen[original]:
                    # Cycle. Stop this chain where it stands and flag it.
                    result[original] = AliasResolution(current, depth - 1, True)
                    continue
                seen[original].add(target)
                result[original] = AliasResolution(target, depth, False)
                nxt[original] = target
            if not nxt:
                break
            frontier = nxt
        else:
            # The loop ran to the cap with chains still moving.
            for original, current in frontier.items():
                result[original] = AliasResolution(current, self._max_alias_depth, True)
        return result

    def lookup_alt_ids(self, kinds: list[tuple[str, str, str]]
                       ) -> dict[tuple[str, str, str], set[str]]:
        """``{(type, domain, value): {content_id, ...}}`` over identity rows.

        A key with no match is absent from the result.
        """
        out: dict[tuple[str, str, str], set[str]] = {}
        if not kinds:
            return out
        types = [k[0] for k in kinds]
        # R8: a blank Domain matches only a blank one. The mirror stores a
        # named type's blank domain as '' and never as NULL (measured
        # 2026-10-15: 4,830,585 rows '', none NULL), so a blank is sent as ''.
        # Until 0.57.0 it was sent as NULL and matched under IS NOT DISTINCT
        # FROM, which matched NO named-type row at all: every IMDB and ISAN
        # identity lookup came back empty, so their conflicts were never
        # found (a 20,000-key batch: 0 rows, against 20,080 with ''). COALESCE
        # keeps a NULL domain matching blank if the mirror ever stores one;
        # the planner drives the join from the alt_id index either way.
        domains: list[str] = [k[1] or "" for k in kinds]
        values = [k[2] for k in kinds]
        # The relation predicate repeats the partial index
        # idx_cais_type_domain_relnorm_altid's own, but the planner does NOT
        # use that index here: it drives the join from the plain alt_id index
        # (idx_content_alt_ids_self_alt_id), whatever the domain and relation
        # wording (BMRtoAltID, EXPLAIN ANALYZE on the live mirror, 2026-10-16;
        # the earlier claim that a reword loses the index was never true for
        # this query). It stays as written because identity_relation_sql()'s
        # extra "OR relation = ''" matches nothing since the 2026-09-23 mirror
        # repair, not to protect an index.
        rows = self._query(
            "SELECT k.t, k.d, k.v, a.content_id "
            "FROM unnest(%s::text[], %s::text[], %s::text[]) "
            "     AS k(t, d, v) "
            f"JOIN {self._table} a "  # noqa: S608
            "  ON a.id_type = k.t "
            " AND a.alt_id = k.v "
            " AND COALESCE(a.domain, '') = k.d "
            "WHERE a.relation IS NULL OR a.relation = %s",
            (types, domains, values, IS_SAME_AS),
        )
        for t, d, v, content_id in rows:
            out.setdefault((t, d or "", v), set()).add(content_id)
        return out

    def existing_alt_ids(self, content_ids: list[str]
                         ) -> dict[str, dict[tuple[str, str, str], set[str]]]:
        """``{content_id: {(type, domain, value): {relation, ...}}}``, every
        relation.

        Unfiltered on purpose: presence is Kind plus value, so a value on the
        record under ANY relation is the same Alt ID and is never re-added.
        The relation is kept because the audit tells two cases apart (same
        relation: skip; different: conflict). NULL comes back as ``""``, and
        a set because the registry may already hold a duplicate.
        """
        out: dict[str, dict[tuple[str, str, str], set[str]]] = {}
        if not content_ids:
            return out
        rows = self._query(
            "SELECT content_id, id_type, domain, alt_id, relation "
            f"FROM {self._table} WHERE content_id = ANY(%s)",  # noqa: S608
            (sorted(set(content_ids)),),
        )
        for content_id, id_type, domain, alt_id, relation in rows:
            kinds = out.setdefault(content_id, {})
            kinds.setdefault((id_type or "", domain or "", alt_id or ""),
                             set()).add(relation or "")
        return out


Contributed = Callable[[str, AltId], bool]


def audit_rows(rows: Iterable[AuditRow], client, *,
               batch_alt_ids: int = DEFAULT_BATCH_ALT_IDS,
               quarantine: str = "row",
               multi_form_domains: frozenset[str] | None = None,
               contributed: Contributed | None = None) -> Iterator[RowAudit]:
    """Audit ``rows`` against the mirror, yielding one ``RowAudit`` per row in
    input order.

    ``client`` is a ``MirrorClient`` (or anything with its three batch
    methods). ``rows`` is consumed lazily, ``batch_alt_ids`` Alt IDs at a
    time, so a caller can contain its own reading errors in the iterable.
    ``contributed(eidr_id, alt)``, when given, is the contribution-ledger
    gate (C5 item 14): an Alt ID it answers True for was contributed before,
    is not on the record now, and is not offered again; it is counted, not
    reported.
    """
    if quarantine not in ("row", "alt_id"):
        raise ValueError(f"quarantine must be 'row' or 'alt_id', not {quarantine!r}")
    batch: list[AuditRow] = []
    pending = 0
    for row in rows:
        batch.append(row)
        pending += len(row.alt_ids)
        if pending >= batch_alt_ids:
            yield from _flush(batch, client, quarantine, multi_form_domains, contributed)
            batch, pending = [], 0
    if batch:
        yield from _flush(batch, client, quarantine, multi_form_domains, contributed)


def audit(eidr_id: str, alt_ids: Sequence[AltId], *, client=None, conn=None,
          quarantine: str = "row",
          multi_form_domains: frozenset[str] | None = None,
          contributed: Contributed | None = None) -> RowAudit:
    """Audit one record's Alt IDs: the single-row form of ``audit_rows``.

    ``eidr_id`` is the record to write to ("" for none). Pass ``client``, or
    ``conn`` to have a default ``MirrorClient`` built on it. Three queries a
    call: for more than a handful of records, use ``audit_rows``.
    """
    if client is None:
        if conn is None:
            raise ValueError("audit() needs a client or a conn")
        client = MirrorClient(conn)
    raw = (eidr_id or "").strip()
    reason = fault(raw) if raw else None
    row = AuditRow(
        sheet_row=0, row_id="", asserted_raw=raw,
        asserted_id=raw.upper() if raw and reason is None else "",
        asserted_invalid=reason is not None, asserted_reason=reason or "",
        alt_ids=tuple(alt_ids))
    return next(audit_rows([row], client, quarantine=quarantine,
                           multi_form_domains=multi_form_domains,
                           contributed=contributed))


def _flush(batch: list[AuditRow], client, quarantine: str,
           multi_form_domains: frozenset[str] | None,
           contributed: Contributed | None) -> Iterator[RowAudit]:
    """Resolve one batch against the mirror, then adjudicate row by row."""
    # 1. Aliases for the batch's asserted IDs.
    asserted_ids = sorted({w.asserted_id for w in batch if w.asserted_id})
    aliases = client.resolve_aliases(asserted_ids)
    # 2. Every audited Kind+value in the batch, looked up once.
    kinds = sorted({kind_key(a) for w in batch for a in w.alt_ids
                    if is_audited(a) and a.alt_type})
    matches = client.lookup_alt_ids(kinds)
    # 3. What the effective (post-alias) targets already carry: that is where
    #    AltIDTool would write.
    targets = sorted({aliases[w.asserted_id].target for w in batch if w.asserted_id})
    existing = client.existing_alt_ids(targets)

    for work in batch:
        try:
            yield _adjudicate(work, aliases, matches, existing, quarantine,
                              multi_form_domains, contributed)
        except MirrorError:
            raise
        except Exception as exc:
            yield RowAudit(row=work, error=exc)


def _find(cls: str, alt: AltId | None, detail: str, effective: str = "",
          conflicting: Iterable[str] = (), relation: str | None = None) -> Finding:
    return Finding(cls, alt, detail, effective,
                   relation if relation is not None else (alt.relation if alt else ""),
                   tuple(sorted(conflicting)))


def _same_kind_conflicts(audited: list[AltId], effective: str, held: dict,
                         multi_form_domains: frozenset[str] | None) -> list[Finding]:
    """Rule 6: a second identity value of a single-form Kind, on the row
    itself or already on the target record."""
    out: list[Finding] = []
    single = [a for a in audited if is_single_form(a, multi_form_domains)]

    # On the row: two values of one single-form Kind, both asserting
    # identity. At most one can be right.
    by_kind: dict[tuple[str, str], list[AltId]] = {}
    for alt in single:
        by_kind.setdefault(alt.kind, []).append(alt)
    for kind, alts in by_kind.items():
        values = sorted({a.value for a in alts})
        if len(values) < 2:
            continue
        for alt in alts:
            out.append(_find(
                "SAME_KIND_CONFLICT", alt,
                f"Column {alt.source!r}: the row asserts "
                f"{len(values)} different values as the identity of "
                f"Kind {kind[1] or kind[0]!r} ({', '.join(values)}); "
                f"a single-form Kind has one. Withheld; a human "
                f"decides which.", effective))

    # On the record: the target already claims a DIFFERENT value of this Kind
    # as identity. The same value is presence (rule 7), not a conflict.
    if not effective or not held:
        return out
    identity: dict[tuple[str, str], set[str]] = {}
    for (t, d, v), rels in held.items():
        if any(is_identity_relation(r) for r in rels):
            identity.setdefault((t, d), set()).add(v)
    for alt in single:
        have = identity.get(alt.kind)
        if have and alt.value not in have:
            out.append(_find(
                "SAME_KIND_CONFLICT", alt,
                f"Column {alt.source!r}: {effective} already claims "
                f"{', '.join(sorted(have))} as the identity of Kind "
                f"{alt.kind[1] or alt.kind[0]!r}; a single-form Kind "
                f"has one. Withheld; a human decides which is right.",
                effective, {effective}))
    return out


def _adjudicate(work: AuditRow, aliases: dict, matches: dict, existing: dict,
                quarantine: str, multi_form_domains: frozenset[str] | None,
                contributed: Contributed | None) -> RowAudit:
    findings: list[Finding] = []
    effective = ""
    alias_note = ""
    alias_followed = False

    if work.asserted_invalid:
        findings.append(_find(
            "INVALID_ASSERTED_ID", None,
            f"{work.asserted_raw!r} is not a valid EIDR ID and is "
            f"not a recognized no-match sentinel "
            f"({work.asserted_reason})."))
    elif work.asserted_id:
        resolution = aliases[work.asserted_id]
        effective = resolution.target
        if resolution.exceeded:
            findings.append(_find(
                "ALIAS_DEPTH_EXCEEDED", None,
                f"Alias chain from {work.asserted_id} did not "
                f"terminate within the configured depth (reached "
                f"{effective}); it may be cyclic.", effective))
        elif effective == TOMBSTONE_ID:
            # A deleted record aliases the tombstone, and the tombstone is a
            # valid record, so without this test the row's Alt IDs would be
            # written onto it (0.55.0; found measuring C1's premise).
            findings.append(_find(
                "ASSERTED_ID_DELETED", None,
                f"{work.asserted_id} was deleted: it "
                + (f"is an alias for the tombstone {TOMBSTONE_ID}"
                   if resolution.depth else "is the tombstone")
                + ". Nothing on the row is written; find the record that "
                  "replaced it.", effective))
        elif resolution.depth:
            alias_followed = True
            alias_note = (f" (asserted {work.asserted_id} is an alias for "
                          f"{effective})")

    if work.reviewer_relation_mismatch:
        # The reviewer's relation and the row's own ID disagree about which
        # record this is, so nothing on the row is safe under either reading.
        findings.append(_find("REVIEWER_RELATION_MISMATCH", None,
                              work.reviewer_relation_mismatch, effective))

    audited = [a for a in work.alt_ids if is_audited(a)]
    skipped = len(work.alt_ids) - len(audited)

    # Every record any of the row's audited Alt IDs points at.
    per_alt: dict[tuple[str, str, str], set[str]] = {}
    resolved: set[str] = set()
    for alt in audited:
        found = matches.get(kind_key(alt))
        if found:
            per_alt[kind_key(alt)] = found
            resolved |= found

    for alt in audited:
        found = per_alt.get(kind_key(alt))
        if not found:
            continue
        if len(found) > 1:
            findings.append(_find(
                "MULTI_RECORD_ALT_ID", alt,
                f"Column {alt.source!r}: this Alt ID is assigned to "
                f"{len(found)} EIDR records{alias_note}.", effective, found))
        elif effective and effective not in found:
            findings.append(_find(
                "ASSERTED_ID_MISMATCH", alt,
                f"Column {alt.source!r}: assigned to "
                f"{sorted(found)[0]}, but this row's EIDR ID is "
                f"{effective}{alias_note}.", effective, found))
        elif not effective and len(resolved) > 1:
            findings.append(_find(
                "ALT_IDS_DISAGREE", alt,
                f"Column {alt.source!r}: the row has no Assigned "
                f"EIDR ID and its Alt IDs resolve to "
                f"{len(resolved)} different records.", "", resolved))

    findings.extend(_same_kind_conflicts(
        audited, effective, existing.get(effective, {}), multi_form_domains))

    # A finding without an Alt ID of its own leaves no record to write to.
    row_held = any(f.alt_id is None for f in findings)
    if findings and (quarantine == "row" or row_held):
        named = {kind_key(f.alt_id) for f in findings if f.alt_id is not None and f.alt_id.value}
        collateral = tuple(a for a in work.alt_ids if kind_key(a) not in named)
        return RowAudit(row=work, effective_id=effective, findings=tuple(findings),
                        collateral=collateral, audited=len(audited), skipped=skipped,
                        alias_followed=alias_followed)
    clean = not findings
    # Under quarantine "alt_id", the Alt IDs a finding names are withheld and
    # the row's others go on to the presence and emission checks.
    held = {kind_key(f.alt_id) for f in findings if f.alt_id is not None}

    if not effective:
        # Nothing to write against. Report it only when something was learned,
        # so an ordinary unregistered row stays quiet.
        if clean and len(resolved) == 1:
            findings.append(_find(
                "UNASSERTED_RESOLVED", None,
                f"No Assigned EIDR ID; the row's Alt IDs agree on "
                f"{sorted(resolved)[0]}. Not written: an Alt ID "
                f"match alone does not confirm the record.", "", resolved))
        return RowAudit(row=work, findings=tuple(findings), clean=clean,
                        audited=len(audited), skipped=skipped,
                        alias_followed=alias_followed)

    if work.reviewer_relation:
        # One line per row saying WHY every Alt ID went out under a clarifying
        # relation, and which of the source's own relations it replaced.
        replaced = (f" It replaced the sheet's own relation on "
                    f"{', '.join(repr(s) for s in work.relation_overrides)}."
                    if work.relation_overrides else "")
        findings.append(_find(
            "REVIEWER_RELATION_APPLIED", None,
            f"BMR-Review's reviewer recorded RELATION: {effective} "
            f"{work.reviewer_relation}; all {len(work.alt_ids)} Alt "
            f"ID(s) on this row are written under it (CONTRACT "
            f"section 4: the relation applies to every Alt ID the "
            f"row carries).{replaced}", effective,
            relation=work.reviewer_relation))

    already = existing.get(effective, {})
    additions: list[AltIdRow] = []
    present_n = conflicts_n = contributed_n = 0
    for alt in work.alt_ids:
        if kind_key(alt) in held:
            continue
        present = already.get(kind_key(alt))
        if present is not None:
            if same_relation(present, alt.relation):
                present_n += 1
                continue
            # Rule 7: on the record under another relation. Never written, so
            # one Alt ID never sits on a record twice; always reported.
            conflicts_n += 1
            existing_rels = ", ".join(sorted(r or IS_SAME_AS for r in present))
            findings.append(_find(
                "ALT_ID_RELATION_CONFLICT", alt,
                f"Column {alt.source!r}: already on {effective} with "
                f"Relation {existing_rels}; the sheet says "
                f"{alt.relation.strip() or IS_SAME_AS}. Not written "
                f"(one Alt ID must not sit on a record under two "
                f"relations); reconcile by hand.", effective, {effective}))
            continue
        if contributed is not None and contributed(effective, alt):
            contributed_n += 1
            continue
        line = AltIdRow(effective, alt.alt_type, alt.value, alt.domain, alt.relation)
        problem = emission_problem(line, source=alt.source)
        if problem is not None:
            findings.append(_find(problem[0], alt, problem[1], effective))
            continue
        additions.append(line)
    return RowAudit(row=work, effective_id=effective, additions=tuple(additions),
                    findings=tuple(findings), clean=clean,
                    already_present=present_n, relation_conflicts=conflicts_n,
                    already_contributed=contributed_n, audited=len(audited),
                    skipped=skipped, alias_followed=alias_followed)
