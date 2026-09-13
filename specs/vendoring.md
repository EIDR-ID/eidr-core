# Vendoring — one implementation inside a package that cannot depend on eidr-core

**Version:** 1.0.0 — LANDED 2026-09-11 (eidr-core 0.31.0, `eidr_core.vendor`).
**Proposed by:** python-tools (2026-09-08). **Accepted:** 2026-09-10.
**First consumer shape:** python-sdk (2026-09-10). **Owner of the mechanism:** eidr-core.

## 1. Why a copy, and why a mechanism

Two portfolio deliverables must be self-contained. The Python SDK (`eidr`, on
PyPI) is something eidr-core depends ON, so the SDK cannot depend back. The
command-line tools ship as `.py` files that must run with only the SDK
installed. Both need logic that lives here — the SDK today carries a second
implementation of `eidr_core.ids`, which is exactly the class of duplicate
this repository exists to prevent, in the module whose wrong answer looks
like a confident one.

The dependency direction is the proof that R13's "a copy is a bug until
proven otherwise" asks for: the copy is unavoidable. What is avoidable is a
copy made by hand, or by a copier each consumer writes for itself. So the
mechanism has one home (`eidr_core.vendor`), consumers run it, and the two
self-contained consumers get byte-identical copies whenever their pins are
equal — and exactly the pin's difference otherwise.

## 2. The consumer's manifest — `vendor.toml`

```toml
[vendor]
source  = "https://github.com/EIDR-ID/eidr-core.git"
commit  = "<40-hex sha>"          # the exact commit vendored; never a branch or tag
target  = "src/eidr/_core"        # directory, relative to this file; REPLACED on sync
package = "eidr._core"            # import path the rewritten code uses
modules = ["ids"]                 # eidr_core modules to copy; must be closed under imports
```

* `commit` is a SHA. A branch would make the vendored copy a moving target
  inside a release artefact; `@main` pinning stays the rule for consumers
  that depend on the *package*.
* `modules` must be **closed under imports**: if a listed module imports
  `eidr_core.X`, `X` must be listed too. `sync` refuses otherwise, naming
  the file and line. (`ids` imports only `re`, so `["ids"]` is closed.)
* `target` is owned by the tool. Nothing in it is hand-edited.

## 3. What `sync` does

```
python -m eidr_core.vendor sync --config vendor.toml            # fetch the pin
python -m eidr_core.vendor sync --config vendor.toml --from D:\Software\eidr-core
```

1. Obtains eidr-core **at the pinned commit**: a temporary clone, or with
   `--from` a local checkout whose `HEAD` must equal the pin and whose
   `src/eidr_core` must be clean. A local tree that has moved on would make
   the manifest lie about what was copied.
2. Copies `src/eidr_core/<module>/` (or `<module>.py`) for each listed
   module into `<target>/<module>`, package data included, `__pycache__`
   excluded.
3. Rewrites imports in every copied `.py`: `from eidr_core.X import Y`,
   `from eidr_core import X`, `import eidr_core.X` become `<package>...`.
   Relative imports are untouched. Any import reaching a module not in
   `modules` is an error.
4. Refuses the sync if any copied `.py` still contains the text
   `eidr_core` after rewriting — a string such as
   `importlib.resources.files("eidr_core.specs")` survives an import
   rewrite and fails at runtime in the consumer. A module that does that is
   not vendorable as-is; it needs a seam here first.
5. Writes the generated files: `__init__.py` (a docstring, **no
   imports**), `_version.py` (`__version__`, `__commit__`, `__source__`,
   `__modules__`, `__spec_version__`), `README.md`.
6. Writes `MANIFEST.json`: contract version, source, commit, eidr-core
   version, package, modules, sync time, and the SHA-256 of every file
   **after** rewriting. The manifest is the contract.

## 4. What `check` does — the consumer's CI gate

```
python -m eidr_core.vendor check --config vendor.toml            # hashes only
python -m eidr_core.vendor check --config vendor.toml --resync   # also re-copy the pin and compare
```

Exit 1 with a list of problems, or 0. Always: `MANIFEST.json` present and
at this contract; its commit equals the pin (a moved pin without a sync is
drift); every tracked file's hash matches (a local edit is drift); no extra
or missing files; no residual `eidr_core` text. With `--resync` or
`--from`, additionally a fresh copy of the pin is made in a temporary
directory and compared byte-for-byte, which catches a hand-edit that kept
the hash table consistent by re-running `sync` against an edited checkout.

## 4a. The consumer's own tests must not skip when eidr-core is absent

Absent eidr-core is the SHIPPING configuration -- it is the whole reason the
copy exists -- so a consumer test that `importorskip`s eidr-core passes on
exactly the machines the copy is for. `check` needs eidr-core installed (it
re-derives the closure), so it is the CI gate, not the deployment test.
The consumer's suite should verify the manifest with nothing but the
standard library: the pin equals `MANIFEST.json`'s commit, every SHA-256
matches, nothing is extra or missing, no residual `eidr_core` text -- and
run `check` as the authority *in addition* when eidr-core is importable.
A third test that no module in the consumer's package imports `eidr_core`
directly is the deployment promise itself, and it is otherwise invisible on
a developer machine. (python-tools `tests/test_vendor_pin.py`, 2026-09-12;
both paths mutation-tested against a hand edit.)

A vendored module lands inside the consumer's own package and so meets the
consumer's gate, including `mypy --strict` if that is what they run: keep
every public function here fully annotated (`write_lines` was not, 0.33.0).

## 5. Guarantees

* **The copy imports with no other eidr-core file present.** This is the
  SDK's stated requirement and it is tested: `tests/test_vendor.py` imports
  a vendored `ids` in a subprocess with `eidr_core` blocked from
  `sys.modules`. The generated `__init__.py` imports nothing, so a consumer
  may vendor a single module.
* **Behaviour does not change.** The consumer keeps its own conformance
  vectors (the SDK's 229 IDs) as tests against the vendored copy; the
  mechanism moves text, not semantics.
* **Deterministic.** Same pin, same modules, same package name → same bytes
  (the only non-deterministic field, `synced_at`, lives in `MANIFEST.json`
  and is excluded from comparison).

## 6. Policy

* A vendored module is **read-only** in the consumer. Fixes go to eidr-core
  and reach the consumer by moving the pin.
* Tests for vendored logic stay in eidr-core. The consumer runs `check` and
  its own conformance tests against `specs/`.
* Extras are the consumer's problem: a vendored `bmr_io.read_sheet` still
  needs openpyxl; the vendored module keeps its lazy imports and the
  consumer declares what it uses.
* A consumer documents the target as generated and not part of its public
  API (the SDK: `eidr._core`, in `STABILITY.md`).

## 7. What is vendorable today

| module | closed under imports | package data | residual `eidr_core` text |
|---|---|---|---|
| `ids` | yes (`re` only) | none | none |
| `codes`, `normalize`, `ordering`, `altidtool_io` | to be verified by `sync` at the consumer's pin | `normalize/data/*.csv` copied | to be verified |
| `compare` | reads `eidr_core.specs` by package name | `specs/` | **not vendorable as-is** |

`sync` is the verifier; this table is not. A module that fails step 4
needs a seam in eidr-core before it can be vendored, and that is a proposal
like any other.

## 8. Versioning

This document is versioned independently of the package. A change to the
manifest format, the generated files, or what `check` refuses is a bump
here and a note in `eidr_core.vendor.SPEC_VERSION`; `check` refuses a
`MANIFEST.json` written under a different contract version until the
consumer re-syncs.
