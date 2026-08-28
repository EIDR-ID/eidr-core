"""Guard: this suite must test the WORKING TREE, not an installed copy.

Why this exists (2026-08-28, and it is the second time this shape has bitten)
----------------------------------------------------------------------------
eidr-core uses a ``src/`` layout, so ``import eidr_core`` resolves through
whatever is installed — not through the checkout. An editable install
(``pip install -e .``) points back here and everything is fine. A NON-editable
install shadows the checkout with a copy in site-packages, and then:

* the suite silently tests the installed copy;
* every uncommitted edit in ``src/`` is invisible to it;
* it still passes, because the copy is usually @main and @main is usually
  green — so the signal reads exactly like success.

That is how a real defect shipped in 0.17.0: ``get_registry_client`` imported
``Registry`` from ``eidr`` (top level) instead of ``eidr.registries``, the fix
was made in the working tree, and the suite went on testing the copy that
still had the bug.

**How the non-editable install gets there is the important part**: nobody
installs it deliberately. Every consumer pins
``eidr-core @ git+https://github.com/EIDR-ID/eidr-core.git@main``, so running
``pip install -r requirements.txt`` in ANY consumer repo fetches a copy from
GitHub and replaces this repo's editable install without a word. The register
recorded the same root cause on 2026-08-18 wearing a different hat —
BMR-Review's ``regen_golden_pairs.py`` wrote regenerated expectations into
site-packages, where git could not see them, twice.

Fix when this fires::

    pip install -e D:\\Software\\eidr-core

and re-run. If you have just installed a consumer's requirements, expect it.
"""
from __future__ import annotations

from pathlib import Path

import pytest

_REPO_SRC = (Path(__file__).resolve().parent.parent / "src").resolve()


def pytest_configure(config: pytest.Config) -> None:
    """Fail the whole run, loudly, if eidr_core resolves outside this tree."""
    import eidr_core

    loaded = Path(eidr_core.__file__).resolve().parent.parent
    if loaded != _REPO_SRC:
        raise pytest.UsageError(
            "eidr_core is being imported from an INSTALLED COPY, not this "
            f"working tree.\n"
            f"  imported from : {loaded}\n"
            f"  expected      : {_REPO_SRC}\n\n"
            "The suite would silently test that copy and pass while your "
            "edits in src/ went unexercised — a green run that proves "
            "nothing. This usually means a non-editable install replaced the "
            "editable one, which happens whenever `pip install -r "
            "requirements.txt` is run in a consumer repo (they all pin "
            "eidr-core @ git+...@main).\n\n"
            "Fix:  pip install -e D:\\Software\\eidr-core"
        )
