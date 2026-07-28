"""Runtime parameter source for the L2 comparators (interim mechanism).

The comparators read tuning constants (NL_MODIFIER, FIELD_BONUS_CAP,
LIST_DENOMINATOR, NAME_MATCH_MIN, DATE_*, DUR_*, ...) through this module via
plain attribute access (``config.NAME_MATCH_MIN`` style — the extracted code
is textually unchanged from its BMR-Review origin). A consumer registers its
parameter object once at startup:

    import eidr_core.compare
    eidr_core.compare.set_params(<module or object with the constants>)

BMR-Review registers its ``eidr_dedup_score.config`` in its compare shim, so
its tuning surface is exactly what it was before the extraction — tune there,
per creation type, as always. When ``compare-spec.json`` lands
(unified-scoring.md migration step 2) the registered object becomes the loaded
spec and this module is unchanged.

All comparator reads are lazy (inside function bodies — verified at
extraction time), so registration only needs to happen before the first
scoring call, not before import.
"""
from __future__ import annotations

_source = None


def set_source(obj) -> None:
    """Register the object whose attributes supply the tuning constants."""
    global _source
    _source = obj


def get_source():
    return _source


def __getattr__(name: str):
    # PEP 562 module-level attribute hook: forwards config.X reads to the
    # registered source. Only called for names not defined above.
    #
    # Underscore/dunder probes MUST raise AttributeError, not our helpful
    # RuntimeError: the import system itself does hasattr(module, '__path__')
    # during `from ._params import ...`, and hasattr() only swallows
    # AttributeError — anything else aborts the package import. Tuning
    # constants are UPPERCASE names, never underscore-prefixed, so this
    # split loses nothing.
    if name.startswith("_"):
        raise AttributeError(name)
    if _source is None:
        raise RuntimeError(
            "eidr_core.compare: no parameter source registered. Call "
            "eidr_core.compare.set_params(<config module or spec object>) "
            "before scoring. (BMR-Review does this in its compare shim.)")
    return getattr(_source, name)
