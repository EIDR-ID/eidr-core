"""eidr_core.dictionary must answer from the dictionary that ships with the code.

A lookup that returns the wrong entry, or nothing, sends a consumer off to
write its own version, silently. So these pin: the package copy IS the root
file; a bare, a partial and a full name each find their entry; a module path
finds its section; a miss is None; and --changes filters by version.
"""
import subprocess
import sys
from pathlib import Path

from eidr_core import dictionary

ROOT = Path(__file__).resolve().parent.parent


def test_the_package_copy_is_the_root_file():
    assert dictionary.text() == (ROOT / "DICTIONARY.md").read_text(encoding="utf-8")


def test_lookup_by_bare_partial_and_full_name():
    for name in ("norm_title", "normalize.norm_title", "eidr_core.normalize.norm_title"):
        entry = dictionary.lookup(name)
        assert entry and "def norm_title(" in entry and "**Does.**" in entry, name
        assert "def norm_name(" not in entry, "an entry must stop at the next heading"


def test_lookup_of_a_module_returns_its_section():
    section = dictionary.lookup("eidr_core.ids")
    assert section and section.startswith("## `eidr_core.ids`")
    assert "**Purpose.**" in section and "def is_valid_eidr_id(" in section
    assert "## `eidr_core.inheritance`" not in section


def test_a_miss_is_none():
    assert dictionary.lookup("no_such_function_anywhere") is None
    assert dictionary.lookup("") is None


def test_changes_since_a_version_leaves_that_version_out():
    newer = dictionary.changes("0.44.0")
    assert "### 0.45.0" in newer and "### 0.44.0" not in newer
    assert dictionary.changes().startswith("## Changes")


def test_the_cli_prints_an_entry_and_fails_on_a_miss():
    ok = subprocess.run([sys.executable, "-m", "eidr_core.dictionary", "is_valid_eidr_id"],
                        capture_output=True, text=True, encoding="utf-8")
    assert ok.returncode == 0 and "def is_valid_eidr_id(" in ok.stdout
    miss = subprocess.run([sys.executable, "-m", "eidr_core.dictionary", "nope_nope"],
                          capture_output=True, text=True, encoding="utf-8")
    assert miss.returncode == 1
