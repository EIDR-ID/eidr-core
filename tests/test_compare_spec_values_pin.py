"""Every tuning value in compare-spec.json is pinned to its $spec.version.

Why (S-22, 2026-09-01): CROSSTYPE_TITLE_STRONG moved 1.05 -> 1.00 inside a
regen commit about something else, with no version bump and no handoff,
and De-Dupe UI found it by comparing constants by value. This test makes
that commit shape fail: the values' digest is pinned per version, so a
regen that changes any value must also bump the version AND add the new
version's digest here -- which is the moment the change gets announced.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "src" / "eidr_core" / "specs" / "compare-spec.json"
PIN = ROOT / "tests" / "compare_spec_values_pin.json"


def _digest(values) -> str:
    blob = json.dumps(values, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()


def test_values_match_the_pin_for_this_version():
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    pins = json.loads(PIN.read_text(encoding="utf-8"))
    version = spec["$spec"]["version"]
    assert version in pins, (
        f"compare-spec {version} has no values pin: add "
        f"\"{version}\": \"{_digest(spec['values'])}\" to {PIN.name} in the SAME commit "
        f"as the regen, and say in the handoff which values moved")
    assert pins[version] == _digest(spec["values"]), (
        f"compare-spec values changed but $spec.version is still {version}: a tuning "
        f"change needs a version bump (BMR-Review config.COMPARE_SPEC_VERSION), a regen, "
        f"and a new pin line")


def test_the_pin_file_only_grows():
    pins = json.loads(PIN.read_text(encoding="utf-8"))
    versions = [k for k in pins if not k.startswith("_")]
    assert versions and all(len(pins[v]) == 64 for v in versions)
