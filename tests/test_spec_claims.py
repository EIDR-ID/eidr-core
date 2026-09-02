"""Spec PROSE must agree with the spec VALUES.

Suggested by De-Dupe UI, 2026-09-01, from a defect on their side and a
near-identical one here.

Their `check_engine_sync.py` hashes files and reported only "config.py
CHANGED". It was `audit_spec_claims.py` -- which re-reads every constant their
spec cites and compares it BY VALUE -- that produced "spec says 1.05,
compare-spec has 1.0". A hash tells you THAT something moved; it cannot tell
you that a sentence explaining WHY a threshold is what it is has become false.

eidr-core had the same defect at the time they raised it: `compare-spec.md`
stated the Episode date profile as 0.60 / 0.43 / 0.13 when the shipped spec
held 0.80 / 0.57 / 0.18, and still said `Basic` FAILED the authoring rule
after BMR-Review had fixed it. Nothing could have caught that, because prose
is not executed. This test executes it.
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC_MD = ROOT / "specs" / "compare-spec.md"
SPEC_JSON = ROOT / "src" / "eidr_core" / "specs" / "compare-spec.json"

_ROW = re.compile(
    r"^(?P<name>\w+)\s+"
    r"(?P<g0>[0-9.]+) / (?P<g1>[0-9.]+) / (?P<g2>[0-9.]+)"
    r" at year gaps 0/1/2, floor (?P<floor>[0-9.]+)\s*$"
)


def _claimed_profiles():
    """The date-profile table as compare-spec.md states it, in prose."""
    text = SPEC_MD.read_text(encoding="utf-8")
    marker = "<!-- VALUES-CHECKED:"
    i = text.index(marker)
    block = text[text.index("```", i) + 3:]
    block = block[:block.index("```")]
    out = {}
    for line in block.strip().splitlines():
        m = _ROW.match(line.strip())
        assert m, f"unparseable claim row: {line!r}"
        out[m.group("name")] = (
            float(m.group("g0")), float(m.group("g1")),
            float(m.group("g2")), float(m.group("floor")),
        )
    return out


def _actual_profiles():
    spec = json.loads(SPEC_JSON.read_text(encoding="utf-8"))
    out = {}
    for name, p in (spec["values"].get("DATE_PROFILES") or {}).items():
        g = p["year_gap_credit"]
        def at(i):
            return float(g[str(i)] if str(i) in g else g[i])
        out[name] = (at(0), at(1), at(2), float(p["year_gap_floor"]))
    return out


def test_the_prose_table_names_the_same_profiles_as_the_spec():
    assert set(_claimed_profiles()) == set(_actual_profiles())


@pytest.mark.parametrize("name", sorted(_actual_profiles()))
def test_every_claimed_profile_value_matches_the_spec(name):
    claimed = _claimed_profiles()[name]
    actual = _actual_profiles()[name]
    assert claimed == pytest.approx(actual), (
        f"compare-spec.md claims {name} = {claimed} but compare-spec.json "
        f"holds {actual}. Prose is not executed, so it goes stale silently -- "
        f"update the prose, never the generated spec."
    )
