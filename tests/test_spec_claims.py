"""Spec PROSE must agree with the spec VALUES.

Suggested by De-Dupe UI, 2026-09-01, from a defect on their side and a
near-identical one here.

Their `check_engine_sync.py` hashes files and reported only "config.py
CHANGED". It was `audit_spec_claims.py` -- which re-reads every constant their
spec cites and compares it BY VALUE -- that produced "spec says 1.05,
compare-spec has 1.0". A hash tells you THAT something moved; it cannot tell
you that a sentence explaining WHY a threshold is what it is has become false.

WIDENED 2026-09-02, at De-Dupe UI's argument. The narrow version pinned only
the date-profile table -- and would NOT have caught the error that arrived in
the same handoff that announced it: eidr-core asserted, in prose and without
executing it, that `CROSSTYPE_TITLE_STRONG` entered the spec at 2.3.0. It did
not; it changed at 2.10.0, inside eidr-core's own commit. De-Dupe UI's point:
"the claims that go stale are not only the ones in tables, and the ones in a
handoff never get executed at all." This file cannot reach handoffs, but it
can reach every constant the specification NAMES.

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


def _credit(credits, gap):
    """One year-gap credit. Keys may be int (authored) or str (JSON round-trip)."""
    return float(credits[str(gap)] if str(gap) in credits else credits[gap])


def _actual_profiles():
    spec = json.loads(SPEC_JSON.read_text(encoding="utf-8"))
    out = {}
    for name, p in (spec["values"].get("DATE_PROFILES") or {}).items():
        credits = p["year_gap_credit"]
        out[name] = (_credit(credits, 0), _credit(credits, 1),
                     _credit(credits, 2), float(p["year_gap_floor"]))
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


# --- every constant the prose NAMES ----------------------------------------

_NAMED = re.compile(r"`([A-Z][A-Z0-9_]{3,})`")
# A backticked constant followed closely by a number is a value CLAIM.
_CLAIM = re.compile(
    "`([A-Z][A-Z0-9_]{3,})`"        # the constant, backticked
    "[^`\n]{0,40}?"                 # close by, not crossing a line
    r"(-?[0-9]+(?:\.[0-9]+)?)"       # the number it claims
)
# Named in the prose but deliberately not a tuning value.
_NOT_A_VALUE = {"EIDR_COMPARE_SPEC"}


def _spec_values():
    return json.loads(SPEC_JSON.read_text(encoding="utf-8"))["values"]


def _prose():
    return SPEC_MD.read_text(encoding="utf-8")


def test_every_constant_the_prose_names_exists_in_the_spec():
    """A citation of a constant that no longer exists is a stale explanation.

    Renaming or dropping a tuning constant leaves the prose reasoning about
    something the engine does not have, and nothing else would notice.
    """
    values = _spec_values()
    named = {n for n in _NAMED.findall(_prose())} - _NOT_A_VALUE
    missing = sorted(n for n in named if n not in values)
    assert not missing, (
        f"compare-spec.md names {missing}, which compare-spec.json does not "
        f"define. Either the prose is stale or the constant was renamed."
    )


def test_every_numeric_value_the_prose_claims_matches_the_spec():
    """Where the prose puts a number beside a constant, it must be the number.

    Deliberately conservative: only a number within 40 characters of the
    backticked name counts as a claim, so ordinary discussion is not
    misread as an assertion.
    """
    values = _spec_values()
    bad = []
    for name, claimed in _CLAIM.findall(_prose()):
        actual = values.get(name)
        if not isinstance(actual, (int, float)) or isinstance(actual, bool):
            continue
        if abs(float(claimed) - float(actual)) > 1e-9:
            bad.append(f"{name}: prose says {claimed}, spec has {actual}")
    assert not bad, "stale value claims in compare-spec.md: " + "; ".join(bad)
