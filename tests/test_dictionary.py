"""DICTIONARY.md must match the code, and a stale dictionary is SILENT.

Consumers read the dictionary to decide whether eidr-core already does what
they need (operator, 2026-10-02). A missing entry, or a signature that
drifted, sends them off to write a second implementation, and nothing
raises. So the suite runs the dictionary's own check. It fails when a public
name has no entry, an entry names a symbol that is gone, a generated block is
stale, a purpose is missing, or the release in pyproject.toml has no heading
under Changes. The fix is always the same:

    python tools/gen_dictionary.py --write

then fill in whatever it reports.
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _tool():
    spec = importlib.util.spec_from_file_location(
        "gen_dictionary", ROOT / "tools" / "gen_dictionary.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    # dataclasses resolves a class's module through sys.modules, so the tool
    # must be registered there before its body runs.
    sys.modules["gen_dictionary"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_dictionary_matches_the_code():
    tool = _tool()
    problems = tool.check((ROOT / "DICTIONARY.md").read_text(encoding="utf-8"))
    assert not problems, "\n".join(problems[:40])


def test_check_catches_an_undocumented_symbol():
    # The check must be able to fail: drop one entry and it has to notice.
    tool = _tool()
    text = (ROOT / "DICTIONARY.md").read_text(encoding="utf-8")
    marker = "<!-- dict:eidr_core.ids."
    start = text.index(marker)
    end = text.index("<!-- /dict -->", start) + len("<!-- /dict -->")
    problems = tool.check(text[:start] + text[end:])
    assert any(p.startswith("missing:") for p in problems), problems


def test_check_catches_a_drifted_signature():
    tool = _tool()
    text = (ROOT / "DICTIONARY.md").read_text(encoding="utf-8")
    start = text.index("<!-- dict:eidr_core.registry.get_registry_client -->")
    sig = text.index("def get_registry_client(", start)
    drifted = text[:sig] + "def get_registry_client(old_param, " + \
        text[sig + len("def get_registry_client("):]
    assert any("out of date" in p for p in tool.check(drifted))
