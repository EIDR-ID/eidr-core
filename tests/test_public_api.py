"""Every name a module advertises in ``__all__`` must actually exist.

Written after eidr-core 0.23.0 shipped `"pad_groups"` immediately followed by
`"ROW_ID_COLUMN"` with no comma between them. Python silently concatenated
the two string literals into one name, `pad_groupsROW_ID_COLUMN`, which:

  * made `from eidr_core.bmr_io import *` raise AttributeError, and
  * silently dropped BOTH real names from the public API.

Direct imports kept working, so no existing test noticed -- the suite imports
what it needs by name. Reported by XML_to_JSON, not caught here.

Adjacent-string concatenation is legal Python and invisible to ruff and mypy
in a list of literals, so the only thing that catches it is asserting the
contract. This runs over every module in the package rather than just the one
that broke, because the defect is a typo class, not a bmr_io problem.
"""
from __future__ import annotations

import importlib
import pkgutil

import pytest

import eidr_core

# Modules whose import pulls a third-party dependency the base install lacks.
_NEEDS_EXTRA = {
    "eidr_core.compare": "rapidfuzz",
}


def _modules():
    found = ["eidr_core"]
    for info in pkgutil.walk_packages(eidr_core.__path__, "eidr_core."):
        found.append(info.name)
    return found


@pytest.mark.parametrize("name", _modules())
def test_every_exported_name_exists(name):
    extra = _NEEDS_EXTRA.get(name)
    if extra:
        pytest.importorskip(extra)
    try:
        mod = importlib.import_module(name)
    except ImportError as exc:                    # optional-dependency module
        pytest.skip(f"{name}: {exc}")
    exported = getattr(mod, "__all__", None)
    if not exported:
        return
    missing = [n for n in exported if not hasattr(mod, n)]
    assert not missing, (
        f"{name}.__all__ advertises names the module does not define: "
        f"{missing}. A missing comma between two adjacent string literals "
        f"concatenates them into one bogus name and drops both real ones."
    )


@pytest.mark.parametrize("name", _modules())
def test_no_duplicate_exports(name):
    try:
        mod = importlib.import_module(name)
    except ImportError as exc:
        pytest.skip(f"{name}: {exc}")
    exported = list(getattr(mod, "__all__", []) or [])
    dupes = {n for n in exported if exported.count(n) > 1}
    assert not dupes, f"{name}.__all__ lists {sorted(dupes)} more than once"
