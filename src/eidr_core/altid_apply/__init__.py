"""Apply an AltIDTool edit file to a registry, and never remove an ID by accident.

Reconciliation C7, extracted on 2026-11-26 from eidr-imdb
``src/eidr_imdb/applier.py`` and the ``apply`` command in its ``cli.py``
(commit ``c1ddbb9``), on the operator's instruction of 2026-11-24 relayed by
eidr-imdb. The tool driven is python-tools' Python ``AltIDTool``
(``eidr_tools.tools.altidtool``). eidr-core does not declare python-tools as a
dependency: the caller's interpreter must have it, as a caller must have its
own database driver for ``lookup``.

**The operator's rule this module exists to enforce** (2026-11-24): "Alt ID
updates should not remove existing IDs unless that's the specific intent
(never as a side effect). The Alt ID tool in normal operation just adds the
IDs in its input file, so it's generally safe to use if it's a bit out of
date." So :func:`apply_file` takes the edit file AND the removals intended
for each record (empty for an add-only file), always dry-runs first, and
withholds every record whose dry run would remove a value that is neither
re-added nor intended (:func:`unintended_removals`). Only the rest is
submitted, and only when the caller asks.

Three facts about the tool shape everything here. They are python-tools'
contracts, cited rather than re-derived:

* **File order is a contract** (``eidr_tools/altids.py``, pinned by its
  ``TestOrderIsFileOrder``): lines apply in file order per record, so a
  removal line followed by additions of the same type replaces that family
  in one pass. Filtering a file (:func:`filter_file`) therefore keeps each
  record's lines verbatim and in order.
* **``-f json`` is one document**, one entry per record, with ``added``,
  ``removed`` and ``unchanged`` values worked out against the TARGET
  registry's live record, and a ``submit`` object (:data:`SUBMIT_FIELDS`).
  In ``-multi`` mode a value already present with another relation is
  replaced, so it shows in both ``removed`` and ``added``: a relabel, not a
  loss.
* **``submitted: false`` is not "applied".** It means the edit pass found
  nothing to do, or that nothing was attempted. Only ``status == "success"``
  (:data:`APPLIED_STATUS`) counts as applied; a resume that confused the two
  would skip a record the registry never saw.

What stays with the consumer: recording outcomes in its own tables, reading
its own baseline (the pull a file was built from) for
:func:`check_staleness`, and any integrity manifest its exporter writes. Those
are each one project's storage; the decisions they feed are here.
"""
from __future__ import annotations

import json
import subprocess
import sys
from collections import OrderedDict
from collections.abc import Callable, Collection, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from eidr_core.altidtool_io import parse_edit_line

__all__ = [
    "SUBMIT_FIELDS", "APPLIED_STATUS", "STALE_WARN_AFTER", "PRODUCTION_REGISTRIES",
    "SIGNOFF_FLAG",
    "ApplyRefused", "Block", "Staleness", "Withheld", "ApplyResult",
    "parse_file", "filter_file", "read_intended", "unintended_removals",
    "check_staleness", "file_mtime", "production_gate",
    "build_command", "run_tool", "parse_report", "detail_text",
    "is_applied", "applied_ids", "apply_file",
]

#: The keys ``AltIDTool``'s ``-f json`` puts in each record's ``submit``
#: object. ``file`` is added on dry runs only (the preview XML path).
SUBMIT_FIELDS = ("submitted", "token", "status", "code", "type", "error")

#: The only ``submit.status`` that means the registry accepted the change.
#: ``unchanged`` (the edit pass found nothing to do), ``dryrun``, ``pending``
#: (a non-terminal answer) and ``rejected`` are all "not applied".
APPLIED_STATUS = "success"

#: How old a file may be before the caller is warned. eidr-imdb chose it
#: against measured churn rather than picking it: the registry gained 107 IMDb
#: Alt IDs in six days (~18/day), so a day-old file is very unlikely to be
#: wrong about one of the ~2,000 records a file rewrites. Past a day the odds
#: stop being negligible. A *newer pull* is a harder fact than any elapsed
#: time and refuses outright.
STALE_WARN_AFTER = timedelta(hours=24)

#: Registries that are not a sandbox. Naming any of these needs the explicit
#: operator sign-off (eidr-imdb ruling D9: development runs against Sandbox
#: 2, and a path that could write to production is gated, never a default).
PRODUCTION_REGISTRIES = frozenset({"prod", "production"})

#: The flag :func:`production_gate` tells the operator to pass, unless the
#: caller names its own. eidr-imdb's spelling, kept so its messages read as
#: before.
SIGNOFF_FLAG = "--i-have-operator-signoff"

# Withholding reasons. They go in the withheld file and in ApplyResult, so a
# reviewer reading either knows what to do next without reading this code.
_REASON_UNINTENDED = ("the dry run would remove Alt IDs that are not intended removals "
                      "(the registry record most likely gained them after the file "
                      "was built); rebuild the file from a fresh reading")
_REASON_UNREAD = ("absent from the dry-run report, so its removals could not be "
                  "checked (AltIDTool could not read the record, or its EIDR ID is "
                  "not written in canonical form)")


class ApplyRefused(Exception):
    """A precondition failed. Nothing was sent to any registry."""


@dataclass
class Block:
    """One record's lines from the edit file.

    ``lines`` keeps them verbatim and in file order, because file order is
    the tool's contract and a rewritten block must preserve it.
    """

    eidr_id: str
    lines: list[str] = field(default_factory=list)


def parse_file(path: Path) -> list[Block]:
    """Read an edit file into per-record blocks, file order preserved.

    Blocks are keyed by record and ordered by first appearance -- the same
    grouping ``AltIDTool`` itself does, so a filtered file drives the tool
    exactly as the original would have. Blank lines and ``//`` comments are
    skipped.

    Raises:
        ApplyRefused: the file is missing or has no edit lines, or a line is
            one ``altidtool_io.parse_edit_line`` refuses (no EIDR ID, more than
            five columns, any removal spec v1.6 refuses). A malformed file is
            never "mostly fine": ``AltIDTool`` refuses the whole file on one
            such line, and a block applied with a line missing could delete
            an identifier.
    """
    if not path.exists():
        raise ApplyRefused(f"no edit file at {path}")
    blocks: OrderedDict[str, Block] = OrderedDict()
    for number, raw in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1):
        # Every line is judged by the shared parser that python-tools vendors,
        # so this refuses exactly what the tool would. eidr-imdb's applier
        # checked only for an EIDR ID; a refused removal then failed the whole
        # tool run, which reached the guard as an empty report.
        try:
            parsed = parse_edit_line(raw)
        except ValueError as exc:
            raise ApplyRefused(f"{path}:{number}: {exc}") from None
        if parsed is None:
            continue
        blocks.setdefault(parsed.eidr_id, Block(parsed.eidr_id)).lines.append(raw)
    if not blocks:
        raise ApplyRefused(f"{path} has no edit lines; nothing to apply")
    return list(blocks.values())


def filter_file(blocks: list[Block], skip: Collection[str], dest: Path) -> tuple[int, int]:
    """Write the blocks not in *skip*, in file order, to *dest*.

    Returns ``(records, lines)`` written. Line order within each block is
    preserved verbatim, because a removal-then-restate sequence is only
    correct in the order its builder wrote it.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    records = lines = 0
    with dest.open("w", encoding="utf-8", newline="\n") as fh:
        for block in blocks:
            if block.eidr_id in skip:
                continue
            records += 1
            for line in block.lines:
                fh.write(line + "\n")
                lines += 1
    return records, lines


def read_intended(path: Path | None) -> dict[str, set[str]]:
    """Read an intended-removal list: ``{eidr_id: {value, ...}}``. Empty for None.

    The file is tab-separated with one header line, then one intended removal
    per line: the EIDR ID in column 1 and the Alt ID value in column 2 (more
    columns are ignored). eidr-imdb's ``altid_remove.intended.tsv``
    (``eidr_id<TAB>imdb_id``) is that shape.

    Raises:
        ApplyRefused: *path* is given and missing. A removal file is never
            applied without the list that says which removals are meant.
    """
    intended: dict[str, set[str]] = {}
    if path is None:
        return intended
    if not path.exists():
        raise ApplyRefused(f"intended-removal list {path} is missing; a removal "
                           f"file is never applied without it")
    for raw in path.read_text(encoding="utf-8").splitlines()[1:]:
        if raw.strip():
            eidr_id, value = raw.split("\t")[:2]
            intended.setdefault(eidr_id, set()).add(value)
    return intended


def unintended_removals(entries: Iterable[Mapping[str, Any]],
                        intended: Mapping[str, Collection[str]]) -> dict[str, list[str]]:
    """Records whose report shows a removal nobody asked for.

    The operator's rule of 2026-11-24: "Alt ID updates should not remove
    existing IDs unless that's the specific intent (never as a side effect)."
    AltIDTool's report gives each record's ``removed`` and ``added`` values,
    worked out against the TARGET registry's live record. A value removed and
    re-added is a restated or re-labelled one, not a loss. Whatever is left
    must be in the record's intended removals; anything else is a side effect
    (most likely the registry gained an ID after the file was built).

    Returns ``{eidr_id: sorted lost values}`` for the failing records only.

    The comparison is by VALUE, because the report carries values only, not
    their Type or Domain: a value removed under one Kind and added under
    another reads as re-added. eidr-imdb's files hold one Kind (IMDB), where
    that cannot happen.
    """
    found: dict[str, list[str]] = {}
    for entry in entries:
        eidr_id = str(entry.get("id") or "")
        removed = {str(v) for v in entry.get("removed") or []}
        added = {str(v) for v in entry.get("added") or []}
        lost = removed - added - set(intended.get(eidr_id, ()))
        if lost:
            found[eidr_id] = sorted(lost)
    return found


def file_mtime(path: Path) -> datetime:
    """The file's modification time, timezone-aware (UTC)."""
    # Aware, so a comparison against a database's aware timestamp raises on a
    # mismatch rather than silently misjudging it.
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)


@dataclass
class Staleness:
    """What the freshness check found. ``refuse`` is set when it must stop."""

    refuse: str | None = None
    warnings: list[str] = field(default_factory=list)
    age: timedelta = timedelta(0)


def check_staleness(path: Path, file_time: datetime, pull_id: int | str,
                    pulled_at: datetime | None,
                    newest: tuple[int | str, datetime] | None,
                    now: datetime, *,
                    warn_after: timedelta = STALE_WARN_AFTER) -> Staleness:
    """Decide whether a file built from one registry reading may still be applied.

    A *pull* is the reading of the registry (or its mirror) that the file was
    built from; the caller reads its id and time, and the newest pull's, from
    its own store. Three questions, in increasing order of how sure we can be:

    1. **Is the file older than its own pull?** Then it was not built from
       that pull at all. Refuse.
    2. **Is there a newer pull?** Then the registry has been re-read since
       this file was built, and the newer reading is the one to believe. A
       block that restates a record would delete anything gained in between.
       Refuse.
    3. **Is the file simply old?** Elapsed time is weaker evidence than
       either of the above -- the registry may have changed nothing -- so
       past *warn_after* it warns rather than refuses.

    The dry-run guard in :func:`apply_file` reads the live record and is the
    stronger check; this one stops a run before it reaches the registry at
    all when the file is known to be stale.
    """
    result = Staleness(age=now - file_time)
    if pulled_at is None:
        result.refuse = (f"pull {pull_id} is not recorded; the file has "
                         f"no baseline to be safe against")
        return result
    if file_time < pulled_at:
        result.refuse = (
            f"{path} (written {file_time:%Y-%m-%d %H:%M}Z) predates pull "
            f"{pull_id} ({pulled_at:%Y-%m-%d %H:%M}Z); it was not built from it")
        return result
    if newest and newest[0] != pull_id:
        result.refuse = (
            f"pull {newest[0]} ({newest[1]:%Y-%m-%d %H:%M}Z) is newer than the "
            f"pull {pull_id} this file was built from; anything the registry "
            f"gained in between would be DELETED by blocks that restate a record")
        return result
    if result.age > warn_after:
        hours = result.age.total_seconds() / 3600
        result.warnings.append(
            f"{path} is {hours:.0f}h old. A block that restates a record states "
            f"its FINAL Alt ID list, so anything the registry has gained since "
            f"the pull would be removed; the dry-run check withholds such "
            f"records, but rebuild the file if in doubt.")
    return result


def production_gate(registry: str, signed_off: bool, *,
                    signoff_flag: str = SIGNOFF_FLAG) -> str | None:
    """Refuse a production registry that has no operator sign-off.

    Returns the refusal text, or ``None`` when the registry may be used.
    Development runs against Sandbox 2, and any path that could write to
    production is gated behind an explicit operator flag, never a default
    (eidr-imdb ruling D9). The check is on the registry NAME, so a bare URL
    is refused rather than guessed at -- the tool accepts URLs, and a URL not
    recognised as a sandbox could be production. *signoff_flag* is the
    caller's spelling of the flag, quoted in the refusal.
    """
    name = registry.strip().lower()
    if name in PRODUCTION_REGISTRIES and not signed_off:
        return (f"--registry {registry} writes to PRODUCTION. Ruling D9 "
                f"requires Sandbox 2 first and an explicit operator sign-off; "
                f"pass {signoff_flag} as well, or use --registry sandbox2.")
    if name.startswith(("http://", "https://")) and not signed_off:
        return (f"--registry {registry} is a URL, and a URL cannot be shown "
                f"to be a sandbox. Name sandbox2, or pass {signoff_flag}.")
    return None


def build_command(*, infile: Path, registry: str, report: Path,
                  dryrun_prefix: Path | None,
                  secrets_path: str | None = None,
                  python: str | None = None) -> list[str]:
    """The ``AltIDTool`` command line.

    Invoked as ``python -m eidr_tools.tools.altidtool`` rather than through
    the ``AltIDTool`` console script, so the interpreter is unambiguously the
    caller's -- the console script's location depends on PATH, and a registry
    write is not the place to discover the wrong one was found.

    ``--registry`` is always passed: the tool requires it and assumes
    nothing, which is what the production gate depends on. ``-multi`` is the
    tool's default and is passed explicitly anyway, because ``-single`` would
    make the tool replace whole Kinds itself, and an edit file that wants a
    family replaced already says so, line by line, in the order it chose.
    ``-o`` keeps the JSON document off stdout, which carries progress notes.
    """
    cmd = [python or sys.executable, "-m", "eidr_tools.tools.altidtool",
           "--registry", registry, "-i", str(infile),
           "-multi", "-f", "json", "-o", str(report)]
    if secrets_path:
        cmd += ["-c", secrets_path]
    if dryrun_prefix is not None:
        cmd += ["--dryrun", str(dryrun_prefix)]
    return cmd


#: What :func:`run_tool` calls: ``subprocess.run``'s shape.
Runner = Callable[..., "subprocess.CompletedProcess[str]"]


def run_tool(cmd: list[str], cwd: Path | None = None,
             runner: Runner = subprocess.run) -> subprocess.CompletedProcess[str]:
    """Run AltIDTool. The runner is injectable so tests never touch a registry."""
    return runner(cmd, cwd=str(cwd) if cwd else None, capture_output=True,
                  text=True, check=False)


def parse_report(text: str) -> list[dict[str, Any]]:
    """Read the ``-f json`` document into per-record entries.

    Each entry is normalised to carry a complete ``submit`` object, so a
    caller never has to guess what a missing key meant. A missing ``submit``
    is treated as ``submitted: false`` with an empty status -- which records
    as not-applied, the safe direction.

    Raises:
        ApplyRefused: the report is not one JSON array of objects. The tool
            emits exactly that since 2026-09-12 (it used to emit two
            documents); anything else means a tool version whose report shape
            has not been agreed.
    """
    stripped = text.strip()
    if not stripped:
        return []
    try:
        doc = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ApplyRefused(f"AltIDTool report is not JSON: {exc}") from None
    if not isinstance(doc, list):
        raise ApplyRefused(
            f"AltIDTool report is a {type(doc).__name__}, expected one JSON "
            f"array of per-record entries")
    entries: list[dict[str, Any]] = []
    for item in doc:
        if not isinstance(item, dict):
            raise ApplyRefused("AltIDTool report entry is not an object")
        submit = item.get("submit")
        if not isinstance(submit, dict):
            submit = {}
        normalised = {k: submit.get(k, "" if k != "submitted" else False)
                      for k in SUBMIT_FIELDS}
        if "file" in submit:
            normalised["file"] = submit["file"]
        entries.append({**item, "submit": normalised})
    return entries


def detail_text(submit: Mapping[str, Any]) -> str:
    """One line describing a record's registry outcome, for the caller to store.

    The token first and always, even on a rejection: it is what reconciles a
    run interrupted between the registry accepting and the caller recording
    it, via ``StatusTool -tok``. Then the registry's own ``code``/``type``
    pair verbatim, so a validation error can be told from an authorization
    one without parsing prose, and its ``error`` text last.
    """
    parts = [f"token={submit.get('token') or ''}",
             f"submitted={bool(submit.get('submitted'))}",
             f"code={submit.get('code') or ''}",
             f"type={submit.get('type') or ''}"]
    error = submit.get("error")
    if error:
        parts.append(f"error={error}")
    return " ".join(parts)


def is_applied(entry: Mapping[str, Any]) -> bool:
    """True only when the registry accepted this record's change.

    Takes a report entry (or its ``submit`` object). The status is the
    authority, not the ``submitted`` flag: ``submitted: false`` with status
    ``unchanged`` or ``dryrun`` is never applied.
    """
    submit = entry.get("submit", entry)
    return isinstance(submit, Mapping) and str(submit.get("status") or "") == APPLIED_STATUS


def applied_ids(entries: Iterable[Mapping[str, Any]]) -> set[str]:
    """The EIDR IDs whose entries :func:`is_applied` accepts.

    A caller's resume store should mark exactly these as done, and pass them
    back as ``done`` to :func:`apply_file` on the next run, so the two halves
    of the resume key off one definition of success.
    """
    return {str(e.get("id")) for e in entries if e.get("id") and is_applied(e)}


@dataclass
class Withheld:
    """A record the guard kept back, and why.

    ``values`` are the Alt ID values its dry run would have removed without
    intent; empty when the record had no dry-run reading at all.
    """

    eidr_id: str
    values: tuple[str, ...]
    reason: str


@dataclass
class ApplyResult:
    """What :func:`apply_file` did.

    ``dry_run`` is the dry-run report (parsed). ``entries`` is the submit
    pass's report, empty when nothing was submitted; record outcomes from it
    (``applied_ids``, ``detail_text``). ``late_removals`` holds unintended
    removals that appear only in the submit report -- the registry changed
    between the dry run and the submission. They have happened and cannot be
    withheld; they are reported so a human can restore them.
    """

    records: int
    done: frozenset[str]
    dry_run: list[dict[str, Any]] = field(default_factory=list)
    withheld: dict[str, Withheld] = field(default_factory=dict)
    submit_requested: bool = False
    submitted_records: int = 0
    entries: list[dict[str, Any]] = field(default_factory=list)
    late_removals: dict[str, list[str]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    returncodes: list[int] = field(default_factory=list)

    @property
    def applied(self) -> set[str]:
        """Records the registry accepted in this run's submit pass."""
        return applied_ids(self.entries)

    @property
    def not_applied(self) -> set[str]:
        """Records sent in the submit pass that the registry did not accept.

        Includes ``unchanged`` (nothing to do), which is not a failure but is
        not "applied" either.
        """
        return {str(e.get("id")) for e in self.entries
                if e.get("id") and not is_applied(e)}


def apply_file(path: Path, *, registry: str, out_dir: Path,
               intended: Mapping[str, Collection[str]],
               staleness: Staleness | None,
               submit: bool = False, signed_off: bool = False,
               force_stale: bool = False, done: Collection[str] = (),
               secrets_path: str | None = None, python: str | None = None,
               runner: Runner = subprocess.run, cwd: Path | None = None,
               log: Callable[[str], None] | None = None,
               signoff_flag: str = SIGNOFF_FLAG) -> ApplyResult:
    """Dry-run an AltIDTool edit file, withhold side-effect removals, then submit.

    The sequence (eidr-imdb's ``apply`` command, minus its database):

    1. :func:`production_gate` -- a production registry or a URL needs
       *signed_off*.
    2. :func:`parse_file` -- the file is read and every line judged.
    3. *staleness* (from :func:`check_staleness`, or ``None`` when the
       caller has no baseline): a refusal stops the run unless *force_stale*;
       its warnings go into the result either way. It is a required argument
       so that skipping the check is a decision, not an omission.
    4. Records in *done* (already applied, from the caller's resume store)
       are filtered out. Nothing left: return.
    5. **Always a dry run**, even when *submit* is set: it is the only reading
       of the target registry's live records, and the guard needs it.
    6. **The guard** (operator, 2026-11-24): a record whose dry run removes a
       value that is neither re-added nor in ``intended[eidr_id]`` is
       withheld, and so is a record absent from the dry-run report, whose
       removals cannot be checked. The withheld records are written to
       ``<stem>.withheld_unintended_removal.tsv`` in *out_dir*.
    7. Without *submit* the run stops there: dry run is the default.
       With it, the remaining records are submitted and the report parsed.

    Arguments:
        path: the edit file.
        registry: the registry name passed to AltIDTool (``sandbox2``).
        out_dir: where the filtered input (``<stem>.pending.tsv``), the
            reports (``<stem>.dryrun_report.json``,
            ``<stem>.apply_report.json``), the dry-run preview XML
            (``dryrun/<stem>/would-submit-NNNN.xml``) and the withheld list go.
        intended: the removals intended per record, ``{eidr_id: values}``;
            ``{}`` for an add-only file (:func:`read_intended` reads a list).
        staleness: the freshness verdict, or ``None`` for no baseline.
        submit: actually submit after the guard. Default False (a dry run).
        signed_off: the operator's production sign-off.
        force_stale: proceed despite a staleness refusal. The guard still
            withholds any record that would lose an ID it was not meant to.
        done: EIDR IDs already applied, skipped entirely.
        secrets_path: passed to AltIDTool as ``-c``.
        python: the interpreter that has python-tools; default this one.
        runner: ``subprocess.run`` or a stand-in with its shape (tests).
        cwd: working directory for AltIDTool.
        log: called with each progress line; silent when None.
        signoff_flag: the caller's spelling of the sign-off flag.

    Raises:
        ApplyRefused: the production gate, the file, the staleness check, or
            the report shape refused. Nothing was submitted.
    """
    say = log or (lambda _msg: None)
    refusal = production_gate(registry, signed_off, signoff_flag=signoff_flag)
    if refusal:
        raise ApplyRefused(refusal)
    blocks = parse_file(path)

    warnings: list[str] = []
    if staleness is not None:
        if staleness.refuse and not force_stale:
            raise ApplyRefused(staleness.refuse)
        if staleness.refuse:
            warnings.append(f"--force-stale: {staleness.refuse}")
        warnings.extend(staleness.warnings)

    done_set = frozenset(done)
    result = ApplyResult(records=len(blocks), done=done_set, submit_requested=submit,
                         warnings=warnings)
    remaining = [b for b in blocks if b.eidr_id not in done_set]
    say(f"{len(blocks):,} records in {path}; "
        f"{len(done_set & {b.eidr_id for b in blocks}):,} already applied; "
        f"{len(remaining):,} to attempt")
    if not remaining:
        return result

    out_dir.mkdir(parents=True, exist_ok=True)
    stem = path.stem

    def run(skip: Collection[str], dry: bool) -> tuple[list[dict[str, Any]], int]:
        filtered = out_dir / f"{stem}.pending.tsv"
        n_rec, n_lines = filter_file(blocks, skip, filtered)
        if not n_rec:
            # Everything withheld: an empty file is not worth a tool run.
            # (eidr-imdb's command ran the tool and then checked.)
            return [], 0
        report = out_dir / f"{stem}.{'dryrun' if dry else 'apply'}_report.json"
        if report.exists():
            report.unlink()              # never read last run's report
        prefix = out_dir / "dryrun" / stem / "would-submit" if dry else None
        cmd = build_command(infile=filtered, registry=registry, report=report,
                            dryrun_prefix=prefix, secrets_path=secrets_path,
                            python=python)
        say(f"{'dry run' if dry else 'applying'}: {n_rec:,} records, "
            f"{n_lines:,} lines -> {registry}")
        proc = run_tool(cmd, cwd=cwd, runner=runner)
        result.returncodes.append(proc.returncode)
        say(f"AltIDTool exited {proc.returncode}")
        if proc.stderr and proc.stderr.strip():
            say(proc.stderr.rstrip())
        text = report.read_text(encoding="utf-8") if report.exists() else (proc.stdout or "")
        return parse_report(text), n_rec

    entries, _n = run(done_set, dry=True)
    result.dry_run = entries
    lost = unintended_removals(entries, intended)
    for eidr_id, values in lost.items():
        result.withheld[eidr_id] = Withheld(eidr_id, tuple(values), _REASON_UNINTENDED)
    # A record with no dry-run reading cannot be shown to remove nothing by
    # accident, so it is withheld too. eidr-imdb's applier submitted such a
    # record unchecked; it is also how an EIDR ID written in a non-canonical
    # form fails safe, since the report names records in canonical form.
    reported = {str(e.get("id") or "") for e in entries}
    for block in remaining:
        if block.eidr_id not in reported and block.eidr_id not in result.withheld:
            result.withheld[block.eidr_id] = Withheld(block.eidr_id, (), _REASON_UNREAD)

    withheld_path = out_dir / f"{stem}.withheld_unintended_removal.tsv"
    if result.withheld:
        with withheld_path.open("w", encoding="utf-8", newline="\n") as fh:
            fh.write("eidr_id\twould_remove\treason\n")
            for eidr_id, w in sorted(result.withheld.items()):
                fh.write(f"{eidr_id}\t{';'.join(w.values)}\t{w.reason}\n")
        say(f"WITHHELD {len(result.withheld):,} records: {withheld_path}")
    else:
        say("side-effect check: no record would lose an ID it was not meant to lose")
        if withheld_path.exists():
            withheld_path.unlink()       # a stale list would mislead a reviewer

    if not submit:
        say("Nothing submitted (dry run).")
        return result

    if registry.strip().lower() in PRODUCTION_REGISTRIES:
        say("WRITING TO PRODUCTION with operator sign-off (ruling D9).")
    entries, n_rec = run(done_set | set(result.withheld), dry=False)
    result.submitted_records = n_rec
    if not n_rec:
        say("nothing left to submit after the side-effect check.")
        return result
    result.entries = entries
    # The registry can change between the dry run and the submission. What
    # the submit report shows removed without intent has already happened;
    # saying so is the only thing left to do, and silence would be worse.
    result.late_removals = unintended_removals(entries, intended)
    if result.late_removals:
        say(f"WARNING {len(result.late_removals):,} records lost an unintended Alt ID "
            f"between the dry run and the submission; see ApplyResult.late_removals")
    return result
