"""compare-spec loader — the versioned tuning surface of the unified engine.

``compare-spec.json`` (packaged at ``eidr_core/specs/compare-spec.json``) is
the portfolio's SINGLE tuning surface for match-candidate evaluation
(unified-scoring.md, approved 2026-07-27; per-creation-type weights preserved
as the load-bearing structure for constrained-impact tuning). This module
loads it and restores exact Python semantics:

* ``types`` entries rebuild ``set`` / ``frozenset`` / ``tuple`` containers
  (JSON has only arrays);
* ``weights`` entries rebuild the per-creation-type ``WEIGHTS`` dict —
  ``thresholds`` as tuples, and ``{"$alias": "Edit"}`` entries resolved to the
  SAME dict object as their target, preserving the original
  ``WEIGHTS["Clip"] is WEIGHTS["Edit"]`` identity (tune Edit, Clip follows);
* the spec version is exposed as ``COMPARE_SPEC_VERSION``.

Direction of authority (INVERTED 2026-08-05): BMR-Review's
``eidr_dedup_score/config.py`` is the AUTHORING surface — its
``regen_compare_spec.py`` GENERATES this spec from config and round-trips
through ``load_spec`` before writing. This loader remains the consumer-side
contract for every OTHER reader (golden-pair regen, the future Shim-mode
scoring service); BMR-Review itself no longer loads the spec at runtime.

Spec resolution order: explicit ``path`` argument → ``EIDR_COMPARE_SPEC``
environment variable (test/experiment override) → the packaged file.
"""
from __future__ import annotations

import json
import os
from importlib.resources import files
from pathlib import Path

_ENV_VAR = "EIDR_COMPARE_SPEC"

_CONTAINER = {
    "set": set,
    "frozenset": frozenset,
    "tuple": tuple,
}


def spec_path() -> Path:
    """Path of the packaged compare-spec.json (before env/arg overrides)."""
    return Path(str(files("eidr_core") / "specs" / "compare-spec.json"))


def load_spec(path: str | os.PathLike | None = None) -> dict:
    """Load the spec and return ``{NAME: value}`` with Python semantics
    restored. Raises on a missing/duplicate-alias or unknown container type —
    a malformed tuning file must fail loudly, never score with defaults."""
    p = Path(path) if path else Path(os.environ.get(_ENV_VAR) or spec_path())
    data = json.loads(p.read_text(encoding="utf-8"))

    out: dict = {}
    types = data.get("types", {})
    for name, val in data.get("values", {}).items():
        t = types.get(name)
        if t is not None:
            try:
                val = _CONTAINER[t](val)
            except KeyError:
                raise ValueError(f"compare-spec: unknown container type {t!r} "
                                 f"for {name!r}") from None
        out[name] = val

    # WEIGHTS: two passes so an alias can reference any concrete profile.
    weights: dict = {}
    raw = data.get("weights", {})
    for ct, entry in raw.items():
        if "$alias" in entry:
            continue
        weights[ct] = {"thresholds": tuple(entry["thresholds"]),
                       "weights": dict(entry["weights"])}
    for ct, entry in raw.items():
        if "$alias" in entry:
            target = entry["$alias"]
            if target not in weights:
                raise ValueError(f"compare-spec: WEIGHTS[{ct!r}] aliases "
                                 f"unknown profile {target!r}")
            weights[ct] = weights[target]          # identity, like the original
    out["WEIGHTS"] = weights

    out["COMPARE_SPEC_VERSION"] = data["$spec"]["version"]
    out["STATE_BANDS"] = data.get("states", {})
    return out
