"""eidr-core: shared library for the EIDR tool portfolio.

Modules are populated incrementally by extraction from consumer projects
(Phase 3 of the cross-project overlap register). Until a module lands here,
its canonical implementation remains in the source project named in the
module's docstring — change it THERE and update siblings per the register.
"""
from __future__ import annotations

import re
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _version
from pathlib import Path


def _source_version() -> str | None:
    """Version declared by an adjacent source checkout, if we are one.

    Under an editable install the imported code IS the checkout, but
    ``importlib.metadata`` reports distribution metadata frozen at the last
    ``pip install -e .`` — a ``git pull`` updates the code and not the
    metadata, so the two silently disagree (observed 2026-08-10: a consumer
    environment reported 0.0.1 against a 0.13.0 tree, and the mismatch
    impersonated a real local-vs-CI code divergence; handoff T5). The
    checkout's own pyproject.toml is the truth in that mode. A site-packages
    install has no pyproject.toml two levels above the package and falls
    through to the metadata, which is authoritative there.
    """
    pyproject = Path(__file__).resolve().parent.parent.parent / "pyproject.toml"
    try:
        text = pyproject.read_text(encoding="utf-8")
    except OSError:
        return None
    # Regex rather than tomllib: the floor is Python 3.10 and tomllib is
    # 3.11+. The file is our own, so the simple form cannot mis-parse.
    m = re.search(r'(?m)^version\s*=\s*"([^"]+)"', text)
    return m.group(1) if m else None


try:
    # pyproject.toml [project].version is the single source of truth: read
    # it directly when running from a checkout (editable installs), else
    # read the installed distribution's metadata. Hand-mirroring the string
    # here is what let __version__ sit stale at 0.6.0 through six releases
    # (caught 2026-08-09) with nothing to notice the drift.
    __version__ = _source_version() or _version("eidr-core")
except PackageNotFoundError:
    # Source checkout with no install record and no readable pyproject —
    # fail soft rather than raise on import.
    __version__ = "0.0.0+unknown"
