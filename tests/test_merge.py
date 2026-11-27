"""eidr_core.merge (S3): the surfaces the fixture corpus cannot pin by itself.

Why (2026-11-26). The golden fixtures (test_merge_pairs.py) pin each rule.
What they cannot see:

* Rule 18 and C5 ``altid_audit`` must agree (merge-rules 3.1; the operator's
  relation-aware rulings of 2026-11-24 live in C5). Two code paths that must
  agree are tested against each other (CLAUDE.md): the same record and the
  same supplied Alt IDs through both, and the additions and the withheld
  values compared.
* The caps come from the schema, and bmr_io carries a transcribed
  ``SCHEMA_MAX``; the two are compared, so a schema update that one path
  sees and the other does not is caught.
* The values pin: a knob or rule change without a spec version bump fails.
* The refusals (held ``--replace``, a current record without its
  modification base) must be errors, not quiet add-only runs.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from eidr_core.altid_audit import AltId, AuditRow, audit_rows
from eidr_core.bmr_io import SCHEMA_MAX
from eidr_core.bmr_map import record_to_xml
from eidr_core.merge import (
    FUZZY_THRESHOLD,
    FUZZY_THRESHOLD_ORG,
    SPEC_VERSION,
    MergeOptions,
    _cap,
    _distance,
    merge,
    spec_values_digest,
)

ROOT = Path(__file__).resolve().parents[1]
E1 = "10.5240/7791-8534-2C23-9030-8610-5"
BASE = {"StructuralType": "Abstraction", "Mode": "AudioVisual", "ReferentType": "Movie",
        "ResourceName": [{"Title": "Example Film", "_lang": "en"}],
        "ReleaseDate": "2001", "CountryOfOrigin": ["US"], "ApproximateLength": "PT90M",
        "Administrators": {"Registrant": "10.5237/A1B2-C3D4"}}


def _xml(alt_ids=(), **over):
    bod = dict(BASE, ID=E1, **over)
    if alt_ids:
        bod["AlternateID"] = [_entry(a) for a in alt_ids]
    return record_to_xml({"SelfDefinedMetadata": {"BaseObjectData": bod}})


def _entry(a: AltId) -> dict:
    return {k: v for k, v in (("AltID", a.value), ("Type", a.alt_type),
                              ("Domain", a.domain or None),
                              ("Relation", a.relation or None)) if v}


def _supplied(alt_ids):
    return {"SelfDefinedMetadata": {"BaseObjectData": dict(
        BASE, AlternateID=[_entry(a) for a in alt_ids])}}


class OneRecordMirror:
    """C5's mirror reads over ONE record's Alt IDs: no other record holds
    anything, so only the on-record and on-row rules can fire -- exactly the
    part rule 18 shares with the audit ladder."""

    def __init__(self, held):
        self.held = held

    def resolve_aliases(self, ids):
        from eidr_core.altid_audit import AliasResolution
        return {i: AliasResolution(i, 0, False) for i in ids}

    def lookup_alt_ids(self, kinds):
        return {}

    def existing_alt_ids(self, ids):
        out: dict = {}
        for a in self.held:
            out.setdefault(E1, {}).setdefault((a.alt_type, a.domain, a.value), set()).add(
                a.relation)
        return out


IMDB = AltId("IMDB", "", "tt0133093")
IMDB2 = AltId("IMDB", "", "tt0234215")
TMDB = AltId("Proprietary", "themoviedb.org/movie", "603")
PBS_A = AltId("Proprietary", "pbs.org", "A1")
PBS_B = AltId("Proprietary", "pbs.org", "B2")
MFD = frozenset({"pbs.org"})

SCENARIOS = {
    "new value": ([IMDB], [TMDB]),
    "present same relation": ([IMDB], [IMDB._replace(relation="IsSameAs")]),
    "present other relation": ([IMDB], [IMDB._replace(relation="Deprecated"), TMDB]),
    "same kind on record": ([IMDB], [IMDB2]),
    "same kind on row": ([], [IMDB, IMDB2]),
    "non-identity rival": ([IMDB], [IMDB2._replace(relation="Deprecated")]),
    "multi-form kind": ([PBS_A], [PBS_B]),
    "two relations on row": ([], [TMDB, TMDB._replace(relation="Deprecated")]),
    "exact repeat on row": ([], [TMDB, TMDB]),
    "deprecated on record, identity offered": ([IMDB._replace(relation="Deprecated")], [IMDB]),
}


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_rule_18_agrees_with_the_audit_ladder(name):
    held, offered = SCENARIOS[name]
    rep = merge(_xml(held), _supplied(offered), MergeOptions(multi_form_domains=MFD))
    added = {(c.field, c.new) for c in rep.changes if c.rule == "18"}
    withheld = sorted((c.field, c.code) for c in rep.conflicts)

    row = AuditRow(1, "1", E1, E1, False, alt_ids=tuple(
        a._replace(source=f"Alt ID {i}") for i, a in enumerate(offered, 1)))
    [audit] = audit_rows([row], OneRecordMirror(held), quarantine="alt_id",
                         multi_form_domains=MFD)
    c5_added = {(f"alt_id:{a.alt_type.lower()}|{a.domain.lower()}", a.value)
                for a in audit.additions}
    c5_withheld = sorted((f"alt_id:{f.alt_id.alt_type.lower()}|{f.alt_id.domain.lower()}",
                          f.error_class) for f in audit.findings if f.alt_id is not None)
    assert added == c5_added
    assert withheld == c5_withheld


# bmr_io.SCHEMA_MAX says "Alternate No." is unbounded (md-v2.8 SequenceInfo);
# the bundled md-v28-eidr.xsd, which carries EIDR's redefinitions, says 32.
# Merge reads the schema; the bmr_io entry is reported to the operator
# (S3 report, 2026-11-26) rather than changed here.
_KNOWN_DIVERGENCE = {"Alternate No."}
_FAMILY = {"Original Language": ("base", "OriginalLanguage"),
           "Version Language": ("base", "VersionLanguage"),
           "Alternate Title": ("base", "AlternateResourceName"),
           "Country of Origin": ("base", "CountryOfOrigin"),
           "Associated Org": ("base", "AssociatedOrg"),
           "Alt ID": ("base", "AlternateID"),
           "Director": ("credits", "Director"), "Actor": ("credits", "Actor"),
           "Season Class": ("season", "SeasonClass"),
           "Episode Class": ("episode", "EpisodeClass"),
           "Metadata Authority": ("admins", "MetadataAuthority"),
           "Alternate No.": ("sequence", "AlternateNumber")}


@pytest.mark.parametrize("family", sorted(_FAMILY))
def test_caps_from_the_schema_agree_with_bmr_io(family):
    cap = _cap(*_FAMILY[family])
    expected = SCHEMA_MAX[family]
    if family in _KNOWN_DIVERGENCE:
        assert (cap, expected) == (32, None), "the known divergence moved: update both"
        return
    assert cap == (float("inf") if expected is None else expected)


def test_values_pin_matches_this_spec_version():
    pins = json.loads((ROOT / "tests" / "merge_rules_values_pin.json").read_text(encoding="utf-8"))
    assert SPEC_VERSION in pins, (
        f"merge-rules {SPEC_VERSION} has no values pin: add \"{SPEC_VERSION}\": "
        f"\"{spec_values_digest()}\" in the same commit as the change")
    assert pins[SPEC_VERSION] == spec_values_digest(), (
        "a knob, the rule order, the held list or the field keys changed without a "
        "merge-rules version bump")


def test_knobs_are_the_dotnet_constants():
    # Reviewable knobs carried verbatim (CompareEidrRecord.cs lines 12-14).
    assert (FUZZY_THRESHOLD, FUZZY_THRESHOLD_ORG) == (4, 6)


def test_comparison_form_folds_diacritics_and_the_dotnet_punctuation():
    assert _distance("Amélie & Co.", "Amelie and Co") == 0
    assert _distance("Spider-Man", "Spider Man") == 0
    assert _distance("«Le Film»", "le film") == 0


def test_replace_is_held_and_refused():
    with pytest.raises(ValueError, match="held"):
        merge(_xml(), _supplied([]), MergeOptions(replace=True))


def test_current_must_carry_the_modification_base():
    full = record_to_xml({"FullMetadata": {"BaseObjectData": dict(BASE, ID=E1)}},
                         view="FullMetadata")
    with pytest.raises(ValueError, match="SelfDefinedMetadata"):
        merge(full, _supplied([]))


def test_supplied_creation_element_is_read_as_a_self_defined_block():
    sup = record_to_xml(_supplied([TMDB])).replace("SelfDefinedMetadata", "Basic")
    rep = merge(_xml(), sup)
    assert [c.new for c in rep.changes] == ["603"]


def test_report_as_dict_is_json_ready():
    rep = merge(_xml([IMDB]), _supplied([IMDB2, TMDB]), MergeOptions(multi_form_domains=MFD))
    data = json.loads(json.dumps(rep.as_dict()))
    assert data["spec_version"] == SPEC_VERSION and data["changed"] is True
    assert data["changes"][0]["field"] == "alt_id:proprietary|themoviedb.org/movie"
    assert data["conflicts"][0]["code"] == "SAME_KIND_CONFLICT"


def test_no_change_means_no_merged_xml():
    rep = merge(_xml(), _supplied([]))
    assert rep.changed is False and rep.merged_xml is None


def test_multi_form_list_is_read_only_when_a_proprietary_identity_needs_it(monkeypatch):
    # A vendored copy cannot read the list; it must not fail on a record whose
    # Alt IDs never need rule 6's Proprietary exemption.
    import eidr_core.merge as m

    def boom():
        raise RuntimeError("vendored copy")
    monkeypatch.setattr(m, "multi_form_domains", boom)
    assert merge(_xml([IMDB]), _supplied([IMDB2])).conflicts[0].code == "SAME_KIND_CONFLICT"
    with pytest.raises(RuntimeError):
        merge(_xml(), _supplied([TMDB]))


def test_pin_file_digests_are_sha256():
    pins = json.loads((ROOT / "tests" / "merge_rules_values_pin.json").read_text(encoding="utf-8"))
    assert all(len(v) == len(hashlib.sha256().hexdigest())
               for k, v in pins.items() if not k.startswith("_"))
