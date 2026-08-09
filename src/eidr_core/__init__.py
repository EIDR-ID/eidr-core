"""eidr-core: shared library for the EIDR tool portfolio.

Modules are populated incrementally by extraction from consumer projects
(Phase 3 of the cross-project overlap register). Until a module lands here,
its canonical implementation remains in the source project named in the
module's docstring — change it THERE and update siblings per the register.
"""

# Must move in lockstep with pyproject.toml [project] version — this string
# sat stale at 0.6.0 through six releases (caught 2026-08-09) because nothing
# consumed it; consumers pin @main and read metadata, so pyproject.toml is
# the authority and this is a convenience mirror only.
__version__ = "0.13.0"
