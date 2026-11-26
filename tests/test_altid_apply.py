"""Tests for the AltIDTool apply wrapper (reconciliation C7).

A silent-wrong-answer surface, the kind CLAUDE.md's testing conventions single
out. Every failure here produces a plausible result rather than an error:

* recording ``submitted: false`` as "applied" tells the operator a change
  reached the registry when it never did, and a resume then skips it forever;
* a removal the file's builder did not intend (the registry gained an ID
  after the file was built) applies cleanly and silently deletes the ID --
  the operator's rule of 2026-11-24 forbids exactly that;
* a production write that slipped past the gate looks like a sandbox one.

Nothing here reaches a registry. ``FakeAltIDTool`` stands in for python-tools'
``AltIDTool``: it reads the same command line, applies the edit file to an
in-memory registry with the tool's ``-multi`` semantics (removals take a
named type or one Proprietary domain; a value already present with another
relation is replaced, so it is reported both removed and added), and writes
the ``-f json`` document the tool writes. The guard is therefore tested
against the arithmetic the real tool does, not against hand-written reports
alone.
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from eidr_core import altid_apply as aa
from eidr_core.altidtool_io import AltIdRemoval, format_line, format_removal, parse_edit_line

A = "10.5240/AAAA-AAAA-AAAA-AAAA-AAAA-A"
B = "10.5240/BBBB-BBBB-BBBB-BBBB-BBBB-B"
C = "10.5240/CCCC-CCCC-CCCC-CCCC-CCCC-C"


# ---------------------------------------------------------------------------
# A stand-in for AltIDTool
# ---------------------------------------------------------------------------

class FakeAltIDTool:
    """Runs like ``subprocess.run`` on an AltIDTool command line.

    ``registry`` maps an EIDR ID to its Alt IDs as ``(type, domain, value,
    relation)`` tuples. A dry run reads it; a real run also writes it.
    ``status`` overrides the registry's answer for a record on a real run
    (``rejected``, ``pending``); ``unreadable`` records are left out of the
    report, as the tool does when it cannot fetch a record; ``between`` runs
    after each dry run, to change the registry before the submission.
    """

    def __init__(self, registry, *, status=None, unreadable=(), between=None):
        self.registry = {k: list(v) for k, v in registry.items()}
        self.status = status or {}
        self.unreadable = set(unreadable)
        self.between = between
        self.calls: list[list[str]] = []
        self.inputs: list[str] = []

    def __call__(self, cmd, **kwargs):
        self.calls.append(cmd)
        infile = Path(cmd[cmd.index("-i") + 1])
        out = Path(cmd[cmd.index("-o") + 1])
        dry = "--dryrun" in cmd
        text = infile.read_text(encoding="utf-8")
        self.inputs.append(text)
        by_record: dict[str, list] = {}
        for raw in text.splitlines():
            parsed = parse_edit_line(raw)
            if parsed is not None:
                by_record.setdefault(parsed.eidr_id, []).append(parsed)
        report = []
        for eidr_id, edits in by_record.items():
            if eidr_id not in self.registry or eidr_id in self.unreadable:
                continue                        # the tool cannot fetch it
            keep, added, removed, unchanged = self._apply(self.registry[eidr_id], edits)
            entry = {"id": eidr_id, "added": added, "removed": removed,
                     "unchanged": unchanged}
            changed = bool(added or removed)
            if dry or not changed:
                entry["submit"] = {"submitted": False, "token": "",
                                   "status": "dryrun" if dry else "unchanged",
                                   "code": "", "type": "", "error": ""}
            else:
                status = self.status.get(eidr_id, "success")
                entry["submit"] = {"submitted": True, "token": f"tok-{eidr_id[-1]}",
                                   "status": status, "code": "0" if status == "success" else "4",
                                   "type": status, "error": "" if status == "success" else "no"}
                if status == "success":
                    self.registry[eidr_id] = keep
            report.append(entry)
        out.write_text(json.dumps(report), encoding="utf-8")
        if dry and self.between:
            self.between(self.registry)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    @staticmethod
    def _apply(existing, edits):
        """python-tools ``apply_edits`` in -multi mode, on tuples."""
        keep = list(existing)
        added, removed, unchanged = [], [], []

        def same(a, b):
            return a.lower() == b.lower()

        for e in edits:
            if isinstance(e, AltIdRemoval):
                def goes(a, e=e):
                    return same(a[0], e.alt_type) and (not e.domain or same(a[1], e.domain))
                removed += [a[2] for a in keep if goes(a)]
                keep = [a for a in keep if not goes(a)]
                continue
            new = (e.alt_type, e.domain, e.value, e.relation)
            already = [a for a in keep if same(a[0], new[0]) and same(a[1], new[1])
                       and same(a[2], new[2])]
            if already and all(a[3] == new[3] for a in already):
                unchanged += [a[2] for a in already]
                continue
            removed += [a[2] for a in already]
            keep = [a for a in keep if a not in already]
            keep.append(new)
            added.append(new[2])
        return keep, added, removed, unchanged


def imdb(*values, relation=""):
    return [("IMDB", "", v, relation) for v in values]


def write(path: Path, *lines: str) -> Path:
    path.write_text("".join(line + "\n" for line in lines), encoding="utf-8")
    return path


def run(path, tool, tmp_path, **kw):
    kw.setdefault("intended", {})
    kw.setdefault("staleness", None)
    return aa.apply_file(path, registry="sandbox2", out_dir=tmp_path / "out",
                         runner=tool, **kw)


# ---------------------------------------------------------------------------
# The guard: operator, 2026-11-24, "never as a side effect"
# ---------------------------------------------------------------------------

class TestTheGuard:
    def test_a_relabel_or_restate_is_not_a_loss(self):
        entries = [{"id": A, "removed": ["tt1", "tt2"], "added": ["tt1", "tt2"]}]
        assert aa.unintended_removals(entries, {}) == {}

    def test_an_intended_removal_passes(self):
        entries = [{"id": A, "removed": ["tt1", "tt2"], "added": ["tt2"]}]
        assert aa.unintended_removals(entries, {A: {"tt1"}}) == {}

    def test_an_id_the_builder_never_saw_is_caught(self):
        entries = [{"id": A, "removed": ["tt1", "tt9"], "added": []}]
        assert aa.unintended_removals(entries, {A: {"tt1"}}) == {A: ["tt9"]}

    def test_an_add_only_file_may_remove_nothing(self):
        entries = [{"id": A, "removed": ["tt1"], "added": []}]
        assert aa.unintended_removals(entries, {}) == {A: ["tt1"]}

    def test_intended_for_one_record_does_not_cover_another(self):
        entries = [{"id": B, "removed": ["tt1"], "added": []}]
        assert aa.unintended_removals(entries, {A: {"tt1"}}) == {B: ["tt1"]}

    def test_the_registry_gained_an_id_so_the_removal_record_is_withheld(self, tmp_path):
        """The case the rule was written for, end to end.

        The file removes A's IMDB family to drop tt1 and keep tt2. Since the
        file was built, A gained tt9. The dry run shows tt9 removed and not
        re-added; A is withheld and keeps tt9. B, whose removal is exactly the
        intended one, goes through.
        """
        f = write(tmp_path / "altid_remove.tsv",
                  format_removal(A, "IMDB"), format_line(A, "IMDB", "tt2"),
                  format_removal(B, "IMDB"))
        tool = FakeAltIDTool({A: imdb("tt1", "tt2", "tt9"), B: imdb("tt5")})
        result = run(f, tool, tmp_path, intended={A: {"tt1"}, B: {"tt5"}}, submit=True)
        assert set(result.withheld) == {A}
        assert result.withheld[A].values == ("tt9",)
        assert result.applied == {B}
        assert tool.registry[A] == imdb("tt1", "tt2", "tt9")      # untouched
        assert tool.registry[B] == []
        assert A not in tool.inputs[-1]                         # never submitted

    def test_an_add_only_file_with_a_hidden_removal_is_withheld(self, tmp_path):
        f = write(tmp_path / "altid_add.tsv",
                  format_line(A, "IMDB", "tt1", relation="Deprecated"),   # relabel: fine
                  format_removal(B, "IMDB"), format_line(B, "IMDB", "tt5"))
        tool = FakeAltIDTool({A: imdb("tt1"), B: imdb("tt5", "tt6")})
        result = run(f, tool, tmp_path, submit=True)
        assert set(result.withheld) == {B}
        assert result.applied == {A}
        assert tool.registry[A] == imdb("tt1", relation="Deprecated")
        assert tool.registry[B] == imdb("tt5", "tt6")

    def test_withheld_records_are_written_with_their_reason(self, tmp_path):
        f = write(tmp_path / "x.tsv", format_removal(A, "IMDB"))
        tool = FakeAltIDTool({A: imdb("tt1", "tt9")})
        run(f, tool, tmp_path, intended={A: {"tt1"}})
        rows = (tmp_path / "out" / "x.withheld_unintended_removal.tsv").read_text(
            encoding="utf-8").splitlines()
        assert rows[0] == "eidr_id\twould_remove\treason"
        assert rows[1].startswith(f"{A}\ttt9\t") and "not intended" in rows[1]

    def test_a_clean_run_removes_last_runs_withheld_list(self, tmp_path):
        """A stale list beside a clean run would send a reviewer after nothing."""
        stale = tmp_path / "out" / "x.withheld_unintended_removal.tsv"
        stale.parent.mkdir()
        stale.write_text("old", encoding="utf-8")
        f = write(tmp_path / "x.tsv", format_line(A, "IMDB", "tt2"))
        run(f, FakeAltIDTool({A: imdb("tt1")}), tmp_path)
        assert not stale.exists()

    def test_a_record_with_no_dry_run_reading_is_withheld(self, tmp_path):
        """No reading, no proof it removes nothing by accident."""
        f = write(tmp_path / "x.tsv", format_line(A, "IMDB", "tt2"),
                  format_line(B, "IMDB", "tt6"))
        tool = FakeAltIDTool({A: imdb("tt1"), B: imdb("tt5")}, unreadable={B})
        result = run(f, tool, tmp_path, submit=True)
        assert set(result.withheld) == {B}
        assert result.withheld[B].values == ()
        assert "absent from the dry-run report" in result.withheld[B].reason
        assert B not in tool.inputs[-1]

    def test_an_id_not_in_canonical_form_fails_safe(self, tmp_path):
        """The tool reports records canonically; a lowercase ID in the file
        cannot be matched to its report entry, so it is withheld rather than
        submitted unchecked."""
        lower = A.lower()
        f = write(tmp_path / "x.tsv", format_removal(lower, "IMDB"))

        def canonical(cmd, **kw):
            proc = tool(cmd, **kw)
            out = Path(cmd[cmd.index("-o") + 1])
            doc = json.loads(out.read_text(encoding="utf-8"))
            for e in doc:
                e["id"] = e["id"].upper()
            out.write_text(json.dumps(doc), encoding="utf-8")
            return proc

        tool = FakeAltIDTool({lower: imdb("tt1")})
        result = run(f, canonical, tmp_path, intended={A: {"tt1"}}, submit=True)
        assert set(result.withheld) == {lower}
        assert len(tool.calls) == 1                             # nothing submitted

    def test_a_removal_between_dry_run_and_submit_is_reported(self, tmp_path):
        """The window cannot be closed, so it must not be silent."""
        f = write(tmp_path / "x.tsv", format_removal(A, "IMDB"),
                  format_line(A, "IMDB", "tt2"))

        def gain(registry):
            registry[A].append(("IMDB", "", "tt9", ""))

        tool = FakeAltIDTool({A: imdb("tt1", "tt2")}, between=gain)
        result = run(f, tool, tmp_path, intended={A: {"tt1"}}, submit=True)
        assert result.withheld == {}
        assert result.late_removals == {A: ["tt9"]}

    def test_everything_withheld_means_no_submit_run(self, tmp_path):
        f = write(tmp_path / "x.tsv", format_removal(A, "IMDB"))
        tool = FakeAltIDTool({A: imdb("tt1")})
        result = run(f, tool, tmp_path, submit=True)
        assert set(result.withheld) == {A}
        assert len(tool.calls) == 1 and "--dryrun" in tool.calls[0]
        assert result.submitted_records == 0 and result.entries == []

    def test_value_comparison_is_by_value_across_kinds(self):
        """Pinned limitation: the report carries values, not Kinds."""
        entries = [{"id": A, "removed": ["603"], "added": ["603"]}]
        assert aa.unintended_removals(entries, {}) == {}


# ---------------------------------------------------------------------------
# Dry run by default; submitted: false is never applied
# ---------------------------------------------------------------------------

class TestDryRunAndApplied:
    def test_the_default_is_a_dry_run(self, tmp_path):
        f = write(tmp_path / "x.tsv", format_line(A, "IMDB", "tt2"))
        tool = FakeAltIDTool({A: imdb("tt1")})
        result = run(f, tool, tmp_path)
        assert len(tool.calls) == 1 and "--dryrun" in tool.calls[0]
        assert tool.registry[A] == imdb("tt1")
        assert result.entries == [] and result.applied == set()
        assert result.dry_run[0]["submit"]["status"] == "dryrun"

    def test_submit_still_dry_runs_first(self, tmp_path):
        f = write(tmp_path / "x.tsv", format_line(A, "IMDB", "tt2"))
        tool = FakeAltIDTool({A: imdb("tt1")})
        run(f, tool, tmp_path, submit=True)
        assert ["--dryrun" in c for c in tool.calls] == [True, False]

    def test_only_success_counts_as_applied(self):
        assert aa.APPLIED_STATUS == "success"

    @pytest.mark.parametrize("status", ["unchanged", "dryrun", "pending", "rejected", ""])
    def test_every_other_status_is_not_applied(self, status):
        entry = {"id": A, "submit": {"submitted": status != "unchanged", "status": status}}
        assert not aa.is_applied(entry)
        assert aa.applied_ids([entry]) == set()

    def test_status_is_the_authority_not_the_submitted_flag(self):
        entry = {"id": A, "submit": {"submitted": False, "status": "success"}}
        assert aa.is_applied(entry) and aa.is_applied(entry["submit"])

    def test_unchanged_and_rejected_are_not_applied_end_to_end(self, tmp_path):
        f = write(tmp_path / "x.tsv", format_line(A, "IMDB", "tt1"),   # already there
                  format_line(B, "IMDB", "tt6"), format_line(C, "IMDB", "tt8"))
        tool = FakeAltIDTool({A: imdb("tt1"), B: imdb("tt5"), C: imdb("tt7")},
                             status={B: "rejected"})
        result = run(f, tool, tmp_path, submit=True)
        assert result.applied == {C}
        assert result.not_applied == {A, B}
        by_id = {e["id"]: e["submit"] for e in result.entries}
        assert by_id[A]["submitted"] is False and by_id[A]["status"] == "unchanged"


# ---------------------------------------------------------------------------
# Resume by record
# ---------------------------------------------------------------------------

class TestResume:
    def test_done_records_are_not_sent_at_all(self, tmp_path):
        f = write(tmp_path / "x.tsv", format_line(A, "IMDB", "tt2"),
                  format_line(B, "IMDB", "tt6"))
        tool = FakeAltIDTool({A: imdb("tt1"), B: imdb("tt5")})
        result = run(f, tool, tmp_path, submit=True, done={A})
        assert all(A not in text for text in tool.inputs)
        assert result.applied == {B} and result.done == {A}

    def test_a_second_run_fed_the_first_runs_successes_does_nothing(self, tmp_path):
        """The two halves of the resume share one definition of success."""
        f = write(tmp_path / "x.tsv", format_line(A, "IMDB", "tt2"),
                  format_line(B, "IMDB", "tt6"))
        tool = FakeAltIDTool({A: imdb("tt1"), B: imdb("tt5")}, status={B: "rejected"})
        first = run(f, tool, tmp_path, submit=True)
        assert first.applied == {A}
        tool.status = {}
        second = run(f, tool, tmp_path, submit=True, done=first.applied)
        assert second.applied == {B}
        third = run(f, tool, tmp_path, submit=True, done=first.applied | second.applied)
        assert third.dry_run == [] and len(tool.calls) == 4     # no new tool runs

    def test_filtering_keeps_line_order_within_a_block(self, tmp_path):
        f = write(tmp_path / "x.tsv", format_removal(A, "IMDB"),
                  format_line(A, "IMDB", "tt2", relation="Deprecated"),
                  format_removal(B, "IMDB"), format_line(A, "IMDB", "tt3"))
        blocks = aa.parse_file(f)
        assert aa.filter_file(blocks, {B}, tmp_path / "p.tsv") == (1, 3)
        lines = (tmp_path / "p.tsv").read_text(encoding="utf-8").splitlines()
        assert lines == [format_removal(A, "IMDB"),
                         format_line(A, "IMDB", "tt2", relation="Deprecated"),
                         format_line(A, "IMDB", "tt3")]

    def test_last_runs_report_is_never_read(self, tmp_path):
        """A tool that writes nothing must not leave the old report standing in."""
        f = write(tmp_path / "x.tsv", format_line(A, "IMDB", "tt2"))
        old = tmp_path / "out" / "x.dryrun_report.json"
        old.parent.mkdir()
        old.write_text(json.dumps([{"id": A, "removed": [], "added": ["tt2"]}]),
                       encoding="utf-8")

        def silent(cmd, **kw):
            return subprocess.CompletedProcess(cmd, 2, "", "UsageError")

        result = run(f, silent, tmp_path, submit=True)
        assert result.dry_run == [] and set(result.withheld) == {A}
        assert result.returncodes == [2]


# ---------------------------------------------------------------------------
# The production gate and the staleness guard
# ---------------------------------------------------------------------------

class TestGates:
    @pytest.mark.parametrize("name", ["prod", "production", "PROD", " Production "])
    def test_production_is_refused_without_signoff(self, name):
        refusal = aa.production_gate(name, signed_off=False)
        assert refusal and aa.SIGNOFF_FLAG in refusal

    def test_the_callers_flag_is_named(self):
        assert "--prod-ok" in aa.production_gate("prod", False, signoff_flag="--prod-ok")

    @pytest.mark.parametrize("name", ["prod", "production"])
    def test_production_passes_with_signoff(self, name):
        assert aa.production_gate(name, signed_off=True) is None

    @pytest.mark.parametrize("name", ["sandbox2", "sandbox1", "sb2"])
    def test_a_sandbox_needs_no_signoff(self, name):
        assert aa.production_gate(name, signed_off=False) is None

    def test_a_url_is_refused_without_signoff(self):
        refusal = aa.production_gate("https://registry.eidr.org/EIDR", False)
        assert refusal and "URL" in refusal

    def test_the_gate_stops_apply_file_before_any_tool_run(self, tmp_path):
        f = write(tmp_path / "x.tsv", format_line(A, "IMDB", "tt2"))
        tool = FakeAltIDTool({A: imdb("tt1")})
        with pytest.raises(aa.ApplyRefused, match="PRODUCTION"):
            aa.apply_file(f, registry="prod", out_dir=tmp_path, intended={},
                          staleness=None, runner=tool)
        assert tool.calls == []

    def test_a_stale_refusal_stops_apply_file_unless_forced(self, tmp_path):
        f = write(tmp_path / "x.tsv", format_line(A, "IMDB", "tt2"))
        tool = FakeAltIDTool({A: imdb("tt1")})
        stale = aa.Staleness(refuse="pull 3 is newer")
        with pytest.raises(aa.ApplyRefused, match="newer"):
            run(f, tool, tmp_path, staleness=stale)
        assert tool.calls == []
        result = run(f, tool, tmp_path, staleness=stale, force_stale=True)
        assert result.warnings == ["--force-stale: pull 3 is newer"]
        assert len(tool.calls) == 1                         # the guard still ran

    def test_staleness_is_a_required_decision(self, tmp_path):
        f = write(tmp_path / "x.tsv", format_line(A, "IMDB", "tt2"))
        with pytest.raises(TypeError):
            aa.apply_file(f, registry="sandbox2", out_dir=tmp_path,   # type: ignore[call-arg]
                          intended={})


class TestStaleness:
    PULL_AT = datetime(2026, 9, 9, 15, 5, tzinfo=timezone.utc)
    BUILT = datetime(2026, 9, 9, 16, 0, tzinfo=timezone.utc)

    def test_a_fresh_file_against_its_own_pull_passes(self):
        r = aa.check_staleness(Path("f"), self.BUILT, 2, self.PULL_AT, (2, self.PULL_AT),
                               self.BUILT + timedelta(minutes=30))
        assert r.refuse is None and r.warnings == []

    def test_a_newer_pull_refuses(self):
        newer = (3, datetime(2026, 9, 13, 9, 0, tzinfo=timezone.utc))
        r = aa.check_staleness(Path("f"), self.BUILT, 2, self.PULL_AT, newer,
                               datetime(2026, 9, 13, 10, 0, tzinfo=timezone.utc))
        assert r.refuse and "newer than" in r.refuse and "DELETED" in r.refuse

    def test_a_file_older_than_its_pull_refuses(self):
        r = aa.check_staleness(Path("f"), self.PULL_AT - timedelta(hours=2), 2,
                               self.PULL_AT, (2, self.PULL_AT), self.BUILT)
        assert r.refuse and "predates pull" in r.refuse

    def test_a_missing_pull_refuses(self):
        r = aa.check_staleness(Path("f"), self.BUILT, 9, None, None, self.BUILT)
        assert r.refuse and "no baseline" in r.refuse

    def test_past_the_threshold_it_warns(self):
        r = aa.check_staleness(Path("f"), self.BUILT, 2, self.PULL_AT, (2, self.PULL_AT),
                               self.BUILT + timedelta(hours=30))
        assert r.refuse is None and "FINAL" in r.warnings[0]

    def test_the_threshold_is_the_callers_to_set(self):
        r = aa.check_staleness(Path("f"), self.BUILT, 2, self.PULL_AT, (2, self.PULL_AT),
                               self.BUILT + timedelta(hours=2),
                               warn_after=timedelta(hours=1))
        assert r.warnings

    def test_file_mtime_is_timezone_aware(self, tmp_path):
        f = write(tmp_path / "x.tsv", "x")
        assert aa.file_mtime(f).tzinfo is not None


# ---------------------------------------------------------------------------
# Reading the file, the intended list, and the report
# ---------------------------------------------------------------------------

class TestReading:
    def test_blocks_group_by_record_in_first_appearance_order(self, tmp_path):
        f = write(tmp_path / "x.tsv", "// a comment", format_removal(B, "IMDB"),
                  "", format_line(A, "IMDB", "tt1"), format_line(B, "IMDB", "tt2"))
        blocks = aa.parse_file(f)
        assert [b.eidr_id for b in blocks] == [B, A]
        assert blocks[0].lines == [format_removal(B, "IMDB"), format_line(B, "IMDB", "tt2")]

    @pytest.mark.parametrize("line,match", [
        (f"{A}\t", "remove every Alt ID"),
        (f"{A}\tProprietary", "must name its Domain"),
        ("\tIMDB\ttt1", "no EIDR ID"),
    ])
    def test_a_line_the_format_refuses_refuses_the_file(self, tmp_path, line, match):
        f = write(tmp_path / "x.tsv", format_line(A, "IMDB", "tt1"), line)
        with pytest.raises(aa.ApplyRefused, match=match):
            aa.parse_file(f)

    def test_a_missing_or_empty_file_is_refused(self, tmp_path):
        with pytest.raises(aa.ApplyRefused, match="no edit file"):
            aa.parse_file(tmp_path / "nope.tsv")
        with pytest.raises(aa.ApplyRefused, match="no edit lines"):
            aa.parse_file(write(tmp_path / "e.tsv", "", "// only a comment"))

    def test_read_intended(self, tmp_path):
        f = write(tmp_path / "i.tsv", "eidr_id\timdb_id", f"{A}\ttt1", f"{A}\ttt2",
                  "", f"{B}\ttt5\textra")
        assert aa.read_intended(f) == {A: {"tt1", "tt2"}, B: {"tt5"}}
        assert aa.read_intended(None) == {}
        with pytest.raises(aa.ApplyRefused, match="missing"):
            aa.read_intended(tmp_path / "absent.tsv")

    def test_a_report_parses_and_every_submit_key_is_present(self):
        text = json.dumps([{"id": A, "added": [], "removed": [], "unchanged": [],
                            "submit": {"submitted": False, "status": "dryrun",
                                       "file": "out/dryrun/x-0001.xml"}},
                           {"id": B}])
        entries = aa.parse_report(text)
        assert set(aa.SUBMIT_FIELDS) <= set(entries[0]["submit"])
        assert entries[0]["submit"]["file"].endswith("-0001.xml")
        assert entries[1]["submit"]["submitted"] is False
        assert entries[1]["submit"]["status"] == ""

    def test_an_empty_report_is_empty(self):
        assert aa.parse_report("  ") == []

    @pytest.mark.parametrize("text,match", [
        ("[]\n[]", "not JSON"), ('{"id": "x"}', "expected one JSON array"),
        ("[1]", "not an object"),
    ])
    def test_a_report_of_another_shape_is_refused(self, text, match):
        with pytest.raises(aa.ApplyRefused, match=match):
            aa.parse_report(text)

    def test_detail_text_keeps_the_token_even_on_a_rejection(self):
        detail = aa.detail_text({"token": "tok-9", "submitted": True, "code": "4",
                                 "type": "validation error", "error": "Status must be valid"})
        assert detail == ("token=tok-9 submitted=True code=4 type=validation error "
                          "error=Status must be valid")


class TestCommandLine:
    def _cmd(self, tmp_path, **kw):
        return aa.build_command(infile=tmp_path / "in.tsv", registry="sandbox2",
                                report=tmp_path / "r.json", **kw)

    def test_the_shape(self, tmp_path):
        cmd = self._cmd(tmp_path, dryrun_prefix=None, python="py")
        assert cmd[:3] == ["py", "-m", "eidr_tools.tools.altidtool"]
        assert cmd[cmd.index("--registry") + 1] == "sandbox2"
        assert cmd[cmd.index("-f") + 1] == "json"
        assert cmd[cmd.index("-o") + 1] == str(tmp_path / "r.json")
        assert "-multi" in cmd and "-single" not in cmd and "--dryrun" not in cmd

    def test_dryrun_and_secrets(self, tmp_path):
        cmd = self._cmd(tmp_path, dryrun_prefix=tmp_path / "pre", secrets_path="s.json")
        assert cmd[cmd.index("--dryrun") + 1] == str(tmp_path / "pre")
        assert cmd[cmd.index("-c") + 1] == "s.json"

    def test_the_runner_is_injectable(self):
        seen = {}

        def fake(cmd, **kwargs):
            seen.update(kwargs, cmd=cmd)
            return subprocess.CompletedProcess(cmd, 0, "", "")

        aa.run_tool(["x"], runner=fake)
        assert seen["cmd"] == ["x"] and seen["capture_output"] and seen["check"] is False
