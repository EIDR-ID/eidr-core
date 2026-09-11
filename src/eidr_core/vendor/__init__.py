"""Vendoring mechanism — one implementation of shared logic inside a
package that cannot depend on eidr-core.

Why this exists (python-tools proposal 2026-09-08; accepted 2026-09-10;
python-sdk's consumer shape 2026-09-10; landed 0.31.0 on 2026-09-11)
-------------------------------------------------------------------------
Two portfolio deliverables must be self-contained: the Python SDK (``eidr``
on PyPI — and eidr-core depends on IT, so the arrow cannot point back) and
the command-line tools (``.py`` files that must run with only the SDK
installed). Both need logic that lives here — the SDK carries a second
implementation of ``eidr_core.ids`` today (``eidr.models._checkchar``),
which is the class of duplicate this repository exists to prevent, and the
one whose wrong answer looks like a confident one.

The dependency direction forbids importing. So the only way to have ONE
implementation is a mechanical, verified copy — and the mechanism itself
must have one home, or each consumer writes its own copier and the copies
drift in the copying. This module is that home; consumers run it, they do
not write their own.

The contract (``specs/vendoring.md``):

* ``vendor.toml`` in the consumer pins a **commit**, never a branch. The
  vendored copy is a release artefact of the consumer, so it must be
  reproducible; ``@main`` pinning stays the rule for consumers that depend
  on the package instead.
* ``sync`` copies the listed modules from that commit, rewrites every
  ``eidr_core`` import to the consumer's package, refuses a module list
  that is not closed under imports, and writes a manifest of SHA-256s.
* ``check`` (the consumer's CI gate, beside ruff / mypy / pytest) recomputes
  the hashes and refuses local edits, extra files, a pin that moved without
  a sync, and any residual reference to ``eidr_core`` in the copied text.
* **The copied package imports with no other eidr-core file present** —
  the SDK's stated requirement. The generated ``__init__.py`` imports
  nothing, ``_version.py`` is self-contained, and the closure rule means
  nothing in the copy reaches outside it. ``tests/test_vendor.py`` proves
  it by importing the copy in a subprocess with ``eidr_core`` blocked.
* A vendored module is read-only in the consumer. Fixes go to eidr-core
  and reach the consumer by moving the pin. Tests for the logic stay
  here; the consumer runs ``check`` and its own conformance tests.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

__all__ = ["VendorError", "Manifest", "SyncReport", "load_manifest", "sync", "check",
           "MANIFEST_FILE", "SPEC_VERSION"]

SPEC_VERSION = "1.0.0"
MANIFEST_FILE = "MANIFEST.json"
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_PACKAGE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")
_MODULE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class VendorError(RuntimeError):
    """The manifest, the source, or the vendored tree is not what the
    contract requires. The message says which and what to do."""


@dataclass(frozen=True)
class Manifest:
    """``vendor.toml``'s ``[vendor]`` table, validated."""
    source: str          # git URL or local path of eidr-core
    commit: str          # 40-hex, the exact commit vendored
    target: str          # directory in the consumer, relative to the manifest
    package: str         # import path the rewritten code uses, e.g. "eidr._core"
    modules: tuple[str, ...]
    path: Path = field(compare=False, default=Path("vendor.toml"))

    @property
    def target_dir(self) -> Path:
        return (self.path.parent / self.target).resolve()


def _parse_flat_toml(text: str) -> dict[str, dict[str, object]]:
    """The subset of TOML a vendor manifest uses — tables, string values,
    arrays of strings — for Python 3.10, which has no ``tomllib``. Anything
    outside that subset is refused rather than guessed."""
    tables: dict[str, dict[str, object]] = {}
    cur: dict[str, object] | None = None
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].strip() if not raw.strip().startswith('"') else raw.strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            cur = tables.setdefault(line[1:-1].strip(), {})
            continue
        if cur is None or "=" not in line:
            raise VendorError(f"vendor.toml line {lineno}: cannot parse {raw!r}")
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip()
        if val.startswith('"') and val.endswith('"'):
            cur[key] = val[1:-1]
        elif val.startswith("[") and val.endswith("]"):
            items = [v.strip() for v in val[1:-1].split(",") if v.strip()]
            bad = [v for v in items if not (v.startswith('"') and v.endswith('"'))]
            if bad:
                raise VendorError(f"vendor.toml line {lineno}: array items must be strings")
            cur[key] = [v[1:-1] for v in items]
        else:
            raise VendorError(f"vendor.toml line {lineno}: unsupported value {val!r} "
                              f"(strings and arrays of strings only)")
    return tables


def load_manifest(path: str | os.PathLike[str]) -> Manifest:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    try:
        import tomllib  # Python 3.11+
        data = tomllib.loads(text)
    except ModuleNotFoundError:
        data = _parse_flat_toml(text)
    table = data.get("vendor")
    if not isinstance(table, dict):
        raise VendorError(f"{p}: no [vendor] table")
    missing = [k for k in ("source", "commit", "target", "package", "modules") if k not in table]
    if missing:
        raise VendorError(f"{p}: [vendor] is missing {missing}")
    commit = str(table["commit"]).strip().lower()
    if not _COMMIT_RE.match(commit):
        raise VendorError(f"{p}: commit must be a 40-hex SHA, never a branch or tag: "
                          f"{table['commit']!r}")
    package = str(table["package"]).strip()
    if not _PACKAGE_RE.match(package):
        raise VendorError(f"{p}: package {package!r} is not a dotted import path")
    modules = table["modules"]
    if not isinstance(modules, list) or not modules or not all(
            isinstance(m, str) and _MODULE_RE.match(m) for m in modules):
        raise VendorError(f"{p}: modules must be a non-empty list of eidr_core module names")
    if len(set(modules)) != len(modules):
        raise VendorError(f"{p}: modules lists a module twice")
    return Manifest(source=str(table["source"]).strip(), commit=commit,
                    target=str(table["target"]).strip(), package=package,
                    modules=tuple(modules), path=p.resolve())


# ── source acquisition ───────────────────────────────────────────────────

def _git(*args: str, cwd: str | os.PathLike[str] | None = None) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        raise VendorError(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout.strip()


@contextlib.contextmanager
def _source_checkout(manifest: Manifest, source_path: str | os.PathLike[str] | None):
    """Yield a directory holding eidr-core AT THE PINNED COMMIT.

    With ``source_path`` (``--from``), a local checkout is used and its
    HEAD must equal the pin — a local tree that has moved on would make the
    manifest lie about what was copied. Without it, the pin is fetched
    into a temporary clone, so what is vendored is what the URL holds at
    that SHA and nothing else.
    """
    if source_path is not None:
        src = Path(source_path).resolve()
        if not (src / "src" / "eidr_core").is_dir():
            raise VendorError(f"{src} is not an eidr-core checkout (no src/eidr_core)")
        head = _git("rev-parse", "HEAD", cwd=src)
        if head != manifest.commit:
            raise VendorError(f"local checkout {src} is at {head[:12]}, manifest pins "
                              f"{manifest.commit[:12]}; check out the pin or move the pin")
        if _git("status", "--porcelain", "--", "src/eidr_core", cwd=src):
            raise VendorError(f"local checkout {src} has uncommitted changes under "
                              f"src/eidr_core; a vendored copy must come from a commit")
        yield src
        return
    with tempfile.TemporaryDirectory(prefix="eidr-core-vendor-") as tmp:
        _git("clone", "--quiet", "--no-checkout", manifest.source, tmp)
        _git("checkout", "--quiet", manifest.commit, cwd=tmp)
        yield Path(tmp)


def _source_version(src: Path) -> str:
    m = re.search(r'(?m)^version\s*=\s*"([^"]+)"', (src / "pyproject.toml").read_text("utf-8"))
    if not m:
        raise VendorError(f"{src}/pyproject.toml has no version")
    return m.group(1)


# ── copy and rewrite ─────────────────────────────────────────────────────

_IMPORT_RE = re.compile(
    r"^(?P<indent>\s*)(?:from\s+eidr_core(?P<sub>(?:\.[A-Za-z_][A-Za-z0-9_]*)*)\s+import\s+(?P<names>.+)"
    r"|import\s+eidr_core(?P<sub2>(?:\.[A-Za-z_][A-Za-z0-9_]*)+)(?P<rest>.*))$")


def _rewrite(text: str, relpath: str, manifest: Manifest) -> str:
    """Rewrite ``eidr_core`` imports to ``manifest.package``, refusing any
    that reach a module outside the closed list."""
    allowed = set(manifest.modules)
    out = []
    for lineno, line in enumerate(text.splitlines(keepends=True), 1):
        m = _IMPORT_RE.match(line.rstrip("\r\n"))
        if not m:
            out.append(line)
            continue
        sub = m.group("sub") if m.group("sub") is not None else m.group("sub2")
        if sub:
            top = sub.split(".")[1]
            if top not in allowed:
                raise VendorError(
                    f"{relpath}:{lineno}: imports eidr_core.{top}, which is not in modules="
                    f"{list(manifest.modules)}; the module list must be closed under imports")
        elif m.group("names") is not None:
            # `from eidr_core import X, Y` — every X must be a listed module.
            names = [n.strip().split(" as ")[0].strip("() ")
                     for n in m.group("names").split(",") if n.strip()]
            bad = [n for n in names if n not in allowed]
            if bad:
                raise VendorError(
                    f"{relpath}:{lineno}: `from eidr_core import {', '.join(bad)}` reaches "
                    f"outside modules={list(manifest.modules)}")
        eol = line[len(line.rstrip("\r\n")):]
        new = line.rstrip("\r\n").replace("eidr_core", manifest.package, 1)
        out.append(new + eol)
    return "".join(out)


def _iter_module_files(src: Path, module: str) -> Iterable[tuple[Path, str]]:
    """(absolute path, path relative to the target) for one module."""
    root = src / "src" / "eidr_core"
    pkg = root / module
    if pkg.is_dir():
        for p in sorted(pkg.rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts:
                yield p, str(p.relative_to(root)).replace(os.sep, "/")
    elif (root / f"{module}.py").is_file():
        yield root / f"{module}.py", f"{module}.py"
    else:
        raise VendorError(f"eidr_core has no module {module!r} at the pinned commit")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass
class SyncReport:
    target: str
    commit: str
    version: str
    files: dict[str, str]          # relpath -> sha256 after rewriting


def _write_generated(target: Path, manifest: Manifest, version: str) -> None:
    """The three generated files. ``__init__.py`` imports NOTHING — the
    SDK's requirement is that the copy import with no other eidr_core file
    present, and an ``__init__`` that reached for a sibling would break
    that the day a sibling was not vendored."""
    # No literal "eidr_core" in the generated .py files: check() scans every
    # copied module for residual references, and the generated files must
    # pass the same scan. Commands live in README.md.
    (target / "__init__.py").write_text(
        f'"""Vendored from eidr-core {version} @ {manifest.commit[:12]} by the\n'
        f"eidr-core vendoring tool (specs/vendoring.md {SPEC_VERSION}). GENERATED,\n"
        f"READ-ONLY: fix in eidr-core and move the pin in {manifest.path.name}; see\n"
        f'README.md beside this file. This file imports nothing on purpose."""\n',
        encoding="utf-8", newline="\n")
    (target / "_version.py").write_text(
        '"""Provenance of this vendored copy. GENERATED by the eidr-core vendoring tool."""\n'
        f'__version__ = "{version}"\n'
        f'__commit__ = "{manifest.commit}"\n'
        f'__source__ = "{manifest.source}"\n'
        f"__modules__ = {list(manifest.modules)!r}\n"
        f'__spec_version__ = "{SPEC_VERSION}"\n', encoding="utf-8", newline="\n")
    (target / "README.md").write_text(
        f"# Vendored eidr-core (GENERATED)\n\n"
        f"eidr-core **{version}** at commit `{manifest.commit}`, modules "
        f"{', '.join(f'`{m}`' for m in manifest.modules)}, rewritten to import as "
        f"`{manifest.package}`.\n\n"
        f"Read-only. Fixes go to eidr-core; move the pin in `{manifest.path.name}` and run\n\n"
        f"    python -m eidr_core.vendor sync --config {manifest.path.name}\n\n"
        f"`python -m eidr_core.vendor check --config {manifest.path.name}` is the CI gate.\n"
        f"Contract: eidr-core `specs/vendoring.md` {SPEC_VERSION}.\n",
        encoding="utf-8", newline="\n")


def sync(manifest: Manifest, *, source_path: str | os.PathLike[str] | None = None) -> SyncReport:
    """Replace ``manifest.target_dir`` with the listed modules from the
    pinned commit, rewritten, plus the generated files and MANIFEST.json."""
    target = manifest.target_dir
    with _source_checkout(manifest, source_path) as src:
        version = _source_version(src)
        staged: dict[str, bytes] = {}
        for module in manifest.modules:
            for abs_path, rel in _iter_module_files(src, module):
                data = abs_path.read_bytes()
                if abs_path.suffix == ".py":
                    data = _rewrite(data.decode("utf-8"), rel, manifest).encode("utf-8")
                staged[rel] = data
    # Residual references — a string like importlib.resources.files("eidr_core.specs")
    # would survive the import rewrite and fail at runtime in the consumer.
    residual = [rel for rel, data in staged.items()
                if rel.endswith(".py") and b"eidr_core" in data]
    if residual:
        raise VendorError(f"residual reference to eidr_core after rewriting in {residual}; "
                          f"the module is not vendorable as-is (see specs/vendoring.md)")
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    for rel, data in staged.items():
        p = target / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    _write_generated(target, manifest, version)
    files = {rel: _sha256(target / rel) for rel in _tracked_files(target)}
    (target / MANIFEST_FILE).write_text(json.dumps({
        "spec_version": SPEC_VERSION,
        "source": manifest.source, "commit": manifest.commit, "version": version,
        "package": manifest.package, "modules": list(manifest.modules),
        "synced_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "files": files,
    }, indent=2) + "\n", encoding="utf-8", newline="\n")
    return SyncReport(target=str(target), commit=manifest.commit, version=version, files=files)


def _tracked_files(target: Path) -> list[str]:
    out = []
    for p in sorted(target.rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts and p.name != MANIFEST_FILE:
            out.append(str(p.relative_to(target)).replace(os.sep, "/"))
    return out


def check(manifest: Manifest, *, source_path: str | os.PathLike[str] | None = None,
          resync: bool = False) -> list[str]:
    """Return the list of drift problems (empty means clean).

    Always: MANIFEST.json present and at this contract; its commit equals
    the pin; every tracked file's hash matches; no extra or missing files;
    no residual ``eidr_core`` text. With ``resync=True`` (or a
    ``source_path``): also re-run the copy from the pin into a temporary
    directory and compare byte-for-byte, which catches a hand-edit that
    kept the hash table consistent by re-running sync locally against an
    edited checkout.
    """
    target = manifest.target_dir
    problems: list[str] = []
    mpath = target / MANIFEST_FILE
    if not mpath.is_file():
        return [f"{mpath} missing: run sync"]
    recorded = json.loads(mpath.read_text(encoding="utf-8"))
    if recorded.get("spec_version") != SPEC_VERSION:
        problems.append(f"MANIFEST.json is contract {recorded.get('spec_version')!r}, "
                        f"this tool is {SPEC_VERSION}: run sync")
    if recorded.get("commit") != manifest.commit:
        problems.append(f"pin moved: MANIFEST.json has {str(recorded.get('commit'))[:12]}, "
                        f"{manifest.path.name} pins {manifest.commit[:12]}: run sync")
    if list(recorded.get("modules", [])) != list(manifest.modules):
        problems.append("modules list changed since the last sync: run sync")
    on_disk = _tracked_files(target)
    files: dict[str, str] = recorded.get("files", {})
    for rel in on_disk:
        if rel not in files:
            problems.append(f"extra file not in MANIFEST.json: {rel}")
        elif _sha256(target / rel) != files[rel]:
            problems.append(f"locally modified: {rel} (vendored files are read-only; "
                            f"fix in eidr-core and move the pin)")
    for rel in files:
        if rel not in on_disk:
            problems.append(f"missing file: {rel}")
    for rel in on_disk:
        if rel.endswith(".py") and b"eidr_core" in (target / rel).read_bytes():
            problems.append(f"residual reference to eidr_core in {rel}")
    if (resync or source_path is not None) and not problems:
        with tempfile.TemporaryDirectory(prefix="eidr-core-vendor-check-") as tmp:
            shadow = Manifest(source=manifest.source, commit=manifest.commit,
                              target="shadow", package=manifest.package,
                              modules=manifest.modules, path=Path(tmp) / manifest.path.name)
            sync(shadow, source_path=source_path)
            for rel in _tracked_files(shadow.target_dir):
                if rel in ("README.md",):
                    continue
                a, b = shadow.target_dir / rel, target / rel
                if not b.is_file() or a.read_bytes() != b.read_bytes():
                    problems.append(f"differs from a fresh sync of the pin: {rel}")
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="python -m eidr_core.vendor",
                                 description="Vendor eidr-core modules into a self-contained "
                                             "package (specs/vendoring.md).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("sync", "check"):
        s = sub.add_parser(name)
        s.add_argument("--config", default="vendor.toml", help="path to vendor.toml")
        s.add_argument("--from", dest="source_path", default=None,
                       help="local eidr-core checkout at the pinned commit (no fetch)")
    sub.choices["check"].add_argument("--resync", action="store_true",
                                      help="also re-copy from the pin and compare")
    args = ap.parse_args(argv)
    try:
        manifest = load_manifest(args.config)
        if args.cmd == "sync":
            rep = sync(manifest, source_path=args.source_path)
            print(f"synced eidr-core {rep.version} @ {rep.commit[:12]} -> {rep.target} "
                  f"({len(rep.files)} files)")
            return 0
        problems = check(manifest, source_path=args.source_path, resync=args.resync)
        if problems:
            print("vendor check FAILED:", file=sys.stderr)
            for p in problems:
                print("  -", p, file=sys.stderr)
            return 1
        print(f"vendor check OK: {manifest.target_dir} matches {manifest.commit[:12]}")
        return 0
    except VendorError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
