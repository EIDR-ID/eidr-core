"""Tests for the vendoring mechanism — the guarantees specs/vendoring.md makes.

Why (2026-09-11, python-sdk's consumer shape)
---------------------------------------------
The SDK will replace its own ID implementation with a vendored copy of
``eidr_core.ids`` on the strength of three claims: the copy imports with no
other eidr-core file present, ``check`` catches every kind of drift, and the
module list is refused when it is not closed. A consumer deleting working
code on the strength of a docstring is the "documented but unproven" shape
the register has recorded twice, so each claim is pinned here, with a real
git repository as the source (the pin is a SHA and the tool verifies it —
a fake source would test a different tool).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from eidr_core.vendor import (
    MANIFEST_FILE,
    VendorError,
    _parse_flat_toml,
    check,
    load_manifest,
    main,
    sync,
)

REAL_IDS = Path(__file__).resolve().parent.parent / "src" / "eidr_core" / "ids" / "__init__.py"

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")


def _git(*args, cwd):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)
    return r.stdout.strip()


@pytest.fixture
def source(tmp_path):
    """A miniature eidr-core checkout, committed, with the REAL ids module
    (so the importability claim is tested on the thing the SDK will vendor),
    a module that imports it, and one that reaches outside the list."""
    src = tmp_path / "eidr-core"
    pkg = src / "src" / "eidr_core"
    (pkg / "ids").mkdir(parents=True)
    (pkg / "ids" / "__init__.py").write_bytes(REAL_IDS.read_bytes())
    (pkg / "__init__.py").write_text('"""root: must NOT be needed by a vendored copy"""\n'
                                     "raise RuntimeError('eidr_core root imported')\n")
    (pkg / "uses_ids.py").write_text(
        "from eidr_core.ids import is_valid_eidr_id\n"
        "import eidr_core.ids as _ids\n"
        "from eidr_core import ids\n"
        "def ok(x):\n    return is_valid_eidr_id(x) and _ids.is_valid_eidr_id(x)\n")
    (pkg / "reaches_out.py").write_text("from eidr_core.codes import something\n")
    (pkg / "string_ref.py").write_text(
        "import importlib.resources as r\n"
        "def f():\n    return r.files('eidr_core.specs')\n")
    (pkg / "normalize").mkdir()
    (pkg / "normalize" / "__init__.py").write_text("from .data import X\n")
    (pkg / "normalize" / "data").mkdir()
    (pkg / "normalize" / "data" / "__init__.py").write_text("X = 1\n")
    (pkg / "normalize" / "data" / "table.csv").write_text("a,b\n1,2\n")
    (src / "pyproject.toml").write_text('[project]\nname = "eidr-core"\nversion = "9.9.9"\n')
    _git("init", "-q", cwd=src)
    _git("-c", "user.email=t@t", "-c", "user.name=t", "add", "-A", cwd=src)
    _git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "seed", cwd=src)
    return src


def _manifest(tmp_path, source, modules, package="eidr._core", commit=None):
    consumer = tmp_path / "consumer"
    (consumer / "src" / "eidr").mkdir(parents=True, exist_ok=True)
    (consumer / "src" / "eidr" / "__init__.py").write_text("")
    commit = commit or _git("rev-parse", "HEAD", cwd=source)
    mods = ", ".join(f'"{m}"' for m in modules)
    (consumer / "vendor.toml").write_text(
        f'[vendor]\nsource = "{source.as_posix()}"\ncommit = "{commit}"\n'
        f'target = "src/eidr/_core"\npackage = "{package}"\nmodules = [{mods}]\n')
    return load_manifest(consumer / "vendor.toml")


# ── the SDK's requirement: imports with no other eidr-core file present ──

def test_vendored_ids_imports_with_eidr_core_blocked(tmp_path, source):
    m = _manifest(tmp_path, source, ["ids"])
    rep = sync(m, source_path=source)
    assert rep.version == "9.9.9"
    assert set(rep.files) == {"ids/__init__.py", "__init__.py", "_version.py", "README.md"}
    code = (
        "import sys\n"
        "sys.modules['eidr_core'] = None\n"          # any import of eidr_core raises
        f"sys.path.insert(0, {str(tmp_path / 'consumer' / 'src')!r})\n"
        "from eidr._core.ids import is_valid_eidr_id, category\n"
        "from eidr._core import _version\n"
        "assert is_valid_eidr_id('10.5240/7791-8534-2C23-9030-8610-5')\n"
        "assert category('10.5237/9DD9-E249') == 'party'\n"
        "assert _version.__version__ == '9.9.9' and len(_version.__commit__) == 40\n"
        "print('ok')\n")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "ok"


def test_generated_init_imports_nothing(tmp_path, source):
    m = _manifest(tmp_path, source, ["ids"])
    sync(m, source_path=source)
    init = (m.target_dir / "__init__.py").read_text()
    assert "import" not in init.replace("imports nothing", "")


# ── rewriting and closure ────────────────────────────────────────────────

def test_all_three_import_forms_are_rewritten_and_data_is_copied(tmp_path, source):
    m = _manifest(tmp_path, source, ["ids", "uses_ids", "normalize"], package="eidr_tools._core")
    sync(m, source_path=source)
    text = (m.target_dir / "uses_ids.py").read_text()
    assert "from eidr_tools._core.ids import is_valid_eidr_id" in text
    assert "import eidr_tools._core.ids as _ids" in text
    assert "from eidr_tools._core import ids" in text
    assert "eidr_core" not in text
    assert (m.target_dir / "normalize" / "data" / "table.csv").read_text() == "a,b\n1,2\n"
    assert (m.target_dir / "normalize" / "__init__.py").read_text() == "from .data import X\n"


def test_module_list_not_closed_under_imports_is_refused(tmp_path, source):
    m = _manifest(tmp_path, source, ["reaches_out"])
    with pytest.raises(VendorError, match=r"reaches_out\.py:1: imports eidr_core\.codes"):
        sync(m, source_path=source)
    assert not m.target_dir.exists(), "a refused sync leaves no target"


def test_residual_string_reference_is_refused(tmp_path, source):
    m = _manifest(tmp_path, source, ["string_ref"])
    with pytest.raises(VendorError, match="residual reference to eidr_core"):
        sync(m, source_path=source)


def test_unknown_module_is_refused(tmp_path, source):
    m = _manifest(tmp_path, source, ["nope"])
    with pytest.raises(VendorError, match="no module 'nope'"):
        sync(m, source_path=source)


# ── the pin is honoured ──────────────────────────────────────────────────

def test_local_checkout_must_be_at_the_pin_and_clean(tmp_path, source):
    m = _manifest(tmp_path, source, ["ids"], commit="0" * 40)
    with pytest.raises(VendorError, match="manifest pins 000000000000"):
        sync(m, source_path=source)
    m = _manifest(tmp_path, source, ["ids"])
    (source / "src" / "eidr_core" / "ids" / "__init__.py").write_text("# edited\n", newline="\n")
    with pytest.raises(VendorError, match="uncommitted changes"):
        sync(m, source_path=source)


def test_manifest_validation():
    with pytest.raises(VendorError, match="40-hex"):
        _load('commit = "main"')
    with pytest.raises(VendorError, match="closed|non-empty"):
        _load('modules = []')
    with pytest.raises(VendorError, match="dotted import path"):
        _load('package = "eidr-core"')
    with pytest.raises(VendorError, match="missing"):
        _load("", drop="target")


def _load(override: str, drop: str | None = None):
    import tempfile
    base = {"source": '"x"', "commit": '"' + "a" * 40 + '"', "target": '"t"',
            "package": '"p.q"', "modules": '["ids"]'}
    if drop:
        del base[drop]
    if override:
        k = override.split("=")[0].strip()
        base[k] = override.split("=", 1)[1].strip()
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "vendor.toml"
        p.write_text("[vendor]\n" + "\n".join(f"{k} = {v}" for k, v in base.items()) + "\n")
        return load_manifest(p)


def test_flat_toml_fallback_matches_the_subset_the_manifest_uses():
    text = ('# comment\n[vendor]\nsource = "https://x/y.git"  # trailing\n'
            'modules = ["ids", "codes"]\n')
    assert _parse_flat_toml(text) == {"vendor": {"source": "https://x/y.git",
                                                 "modules": ["ids", "codes"]}}
    with pytest.raises(VendorError, match="unsupported value"):
        _parse_flat_toml("[vendor]\nn = 3\n")


# ── check: every kind of drift ───────────────────────────────────────────

def test_check_is_clean_after_sync_and_catches_each_drift(tmp_path, source):
    m = _manifest(tmp_path, source, ["ids"])
    sync(m, source_path=source)
    assert check(m) == []
    assert check(m, source_path=source) == [], "byte comparison against a fresh copy"
    # local edit
    f = m.target_dir / "ids" / "__init__.py"
    f.write_text(f.read_text() + "\n# tweak\n")
    assert any("locally modified: ids/__init__.py" in p for p in check(m))
    sync(m, source_path=source)
    # extra file
    (m.target_dir / "extra.py").write_text("x = 1\n")
    assert any("extra file" in p for p in check(m))
    sync(m, source_path=source)
    # missing file
    (m.target_dir / "README.md").unlink()
    assert any("missing file: README.md" in p for p in check(m))
    sync(m, source_path=source)
    # pin moved without a sync
    moved = _manifest(tmp_path, source, ["ids"], commit="f" * 40)
    assert any("pin moved" in p for p in check(moved))
    # no manifest at all
    (m.target_dir / MANIFEST_FILE).unlink()
    assert check(m) == [f"{m.target_dir / MANIFEST_FILE} missing: run sync"]


def test_resync_comparison_catches_a_consistent_hand_edit(tmp_path, source):
    """A hand-edit followed by regenerating MANIFEST.json keeps the hash
    table consistent; only a fresh copy of the pin exposes it."""
    m = _manifest(tmp_path, source, ["ids"])
    sync(m, source_path=source)
    f = m.target_dir / "ids" / "__init__.py"
    f.write_text(f.read_text() + "\n# tweak\n")
    import hashlib
    man = json.loads((m.target_dir / MANIFEST_FILE).read_text())
    man["files"]["ids/__init__.py"] = hashlib.sha256(f.read_bytes()).hexdigest()
    (m.target_dir / MANIFEST_FILE).write_text(json.dumps(man))
    assert check(m) == [], "hash table is consistent, so the cheap check passes"
    assert any("differs from a fresh sync" in p for p in check(m, source_path=source))


def test_cli_exit_codes(tmp_path, source, capsys):
    m = _manifest(tmp_path, source, ["ids"])
    cfg = str(m.path)
    assert main(["sync", "--config", cfg, "--from", str(source)]) == 0
    assert main(["check", "--config", cfg]) == 0
    (m.target_dir / "extra.py").write_text("x = 1\n")
    assert main(["check", "--config", cfg]) == 1
    assert "extra file" in capsys.readouterr().err
    bad = _manifest(tmp_path, source, ["reaches_out"])
    assert main(["sync", "--config", str(bad.path), "--from", str(source)]) == 2
