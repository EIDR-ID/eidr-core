"""eidr-core: shared library for the EIDR tool portfolio.

Modules are populated incrementally by extraction from consumer projects
(Phase 3 of the cross-project overlap register). Until a module lands here,
its canonical implementation remains in the source project named in the
module's docstring — change it THERE and update siblings per the register.
"""
from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version as _version

try:
    # pyproject.toml [project].version is the single source of truth; this
    # reads the INSTALLED distribution's metadata rather than duplicating
    # the string, which is what let __version__ sit stale at 0.6.0 through
    # six releases (caught 2026-08-09) with nothing to notice the drift.
    __version__ = _version("eidr-core")
except PackageNotFoundError:
    # Source checkout with no install record (e.g. running straight out of
    # a git clone without `pip install -e .`) — not expected for consumers,
    # who all install via pip, but fail soft rather than raise on import.
    __version__ = "0.0.0+unknown"
