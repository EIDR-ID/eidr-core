"""Conformance: eidr_core.merge against the merge-rules golden fixtures.

Why (S3, 2026-11-26): merge-rules.md section 7 makes the fixture corpus the
propagation mechanism, as golden pairs are for compare-spec. Each fixture
pins one lesson; this test checks the engine's report against the fixture's
version-independent invariants, that the corpus on disk is exactly what
tools/gen_merge_pairs.py authors (so nobody edits an expectation by hand in
one place only), and -- golden-pairs.md section 6 item 1 -- that every
fixture whose invariants name its rule FAILS when that rule is disabled. A
fixture that passes without its rule certifies nothing.
"""
from __future__ import annotations

import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import pytest

import eidr_core.merge as merge_mod
from eidr_core.bmr_map import record_from_row, record_from_xml
from eidr_core.mddf_json import eidr_schema
from eidr_core.merge import MergeOptions, merge

ROOT = Path(__file__).resolve().parents[1]
PAIRS = ROOT / "src" / "eidr_core" / "specs" / "merge_pairs"
FIXTURES = sorted(p.parent for p in PAIRS.rglob("expected.json"))


def _run(d: Path) -> tuple[dict[str, Any], merge_mod.ChangeReport]:
    exp = json.loads((d / "expected.json").read_text(encoding="utf-8"))
    current = (d / "current.xml").read_text(encoding="utf-8")
    row = d / "supplied_row.json"
    supplied: Any
    if row.is_file():
        spec = json.loads(row.read_text(encoding="utf-8"))
        supplied = record_from_row(spec["cells"], spec["template"])
    else:
        supplied = (d / "supplied.xml").read_text(encoding="utf-8")
    full = (d / "full.xml").read_text(encoding="utf-8") if (d / "full.xml").is_file() else None
    return exp, merge(current, supplied, MergeOptions(**exp["options"]), full=full)


def _at(rec: Any, path: str) -> Any:
    for part in path.split("/"):
        if rec is None:
            return None
        rec = rec[int(part)] if isinstance(rec, list) else rec.get(part)
    return rec


def _problems(exp: dict[str, Any], rep: merge_mod.ChangeReport) -> list[str]:
    inv = exp["invariants"]
    out = []
    if rep.changed != inv["changed"]:
        out.append(f"changed {rep.changed} != {inv['changed']}")
    got_changes = [list(c) for c in rep.changes]
    if got_changes != inv["changes"]:
        out.append(f"changes {got_changes} != {inv['changes']}")
    got_conf = [[c.rule, c.field, c.code] for c in rep.conflicts]
    if got_conf != inv["conflicts"]:
        out.append(f"conflicts {got_conf} != {inv['conflicts']}")
    got_skip = [[s.rule, s.field] for s in rep.skipped]
    if got_skip != inv["skipped"]:
        out.append(f"skipped {got_skip} != {inv['skipped']}")
    if (rep.merged_xml is None) == rep.changed:
        out.append("merged_xml must be set exactly when changed")
    if rep.merged_xml is not None:
        merged = record_from_xml(rep.merged_xml)["SelfDefinedMetadata"]
        for path, want in inv["merged"]:
            if _at(merged, path) != want:
                out.append(f"merged {path} = {_at(merged, path)!r}, want {want!r}")
    elif inv["merged"]:
        out.append("merged values stated but nothing changed")
    if "altid_lines" in inv and list(rep.altid_lines) != inv["altid_lines"]:
        out.append(f"altid_lines {list(rep.altid_lines)} != {inv['altid_lines']}")
    return out


@pytest.mark.parametrize("d", FIXTURES, ids=lambda d: f"{d.parent.name}/{d.name}")
def test_fixture(d):
    exp, rep = _run(d)
    assert not _problems(exp, rep), _problems(exp, rep)


def _schema_positions(parent_type: Any) -> dict[str, int]:
    model = eidr_schema().content(parent_type)
    return {c.qname: c.position for c in model.children.values()}


def _assert_schema_order(el: ET.Element, typ: Any) -> None:
    pos = _schema_positions(typ)
    seen = [pos[c.tag] for c in el if c.tag in pos]
    assert seen == sorted(seen), [c.tag for c in el]
    model = eidr_schema().content(typ)
    for c in el:
        child = model.children.get(c.tag)
        if child is not None and not eidr_schema().content(child.type).simple:
            _assert_schema_order(c, child.type)


@pytest.mark.parametrize("d", FIXTURES, ids=lambda d: f"{d.parent.name}/{d.name}")
def test_merged_xml_is_in_schema_order(d):
    """Section 6's last defect, checked on every fixture that changes
    anything: each element's children follow the schema's content model."""
    _, rep = _run(d)
    if rep.merged_xml is None:
        return
    root = ET.fromstring(rep.merged_xml)
    _assert_schema_order(root, eidr_schema().element_type(root.tag))


@pytest.mark.parametrize("d", FIXTURES, ids=lambda d: f"{d.parent.name}/{d.name}")
def test_fixture_fails_without_its_rule(d, monkeypatch):
    exp = json.loads((d / "expected.json").read_text(encoding="utf-8"))
    rule = exp["rule"]
    inv = exp["invariants"]
    named = any(e[0] == rule for key in ("changes", "conflicts", "skipped") for e in inv[key])
    if rule is None or not named:
        pytest.skip("no entry of its own rule to remove (a not-firing fixture; see 'mutation')")
    monkeypatch.setitem(merge_mod._PIPELINE, rule, lambda ctx: None)
    exp, rep = _run(d)
    assert _problems(exp, rep), f"{d.name} still passes with rule {rule} disabled"


def test_corpus_matches_its_generator():
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "gen_merge_pairs.py"), "--check"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_every_shipped_rule_has_a_fixture():
    """Section 7: one pair per rule and per pre-process step."""
    rules = {json.loads((d / "expected.json").read_text(encoding="utf-8"))["rule"]
             for d in FIXTURES}
    missing = [r for r, _, _ in merge_mod.RULES if r not in rules]
    assert not missing, missing
