# eidr-core

Shared library (`src/eidr_core/`, Python) and language-neutral
specifications (`specs/`) for the EIDR tool portfolio. `README.md` has the
module map and install instructions; this file has the rules for changing
what lives here.

## The organizing rule

**A piece of logic moves here when it has a second consumer.** Until then
it stays in its home project. Everything here is, by construction, used by
at least two programs — which is what makes a change to it a cross-project
event rather than a local one.

Two corollaries:

- Modules are populated by **extraction** from a source project, not by
  writing a fresh parallel implementation.
- A consumer keeping its own copy of shared logic should be treated as a
  bug until proven otherwise. Check whether a **signature gap** is the
  real reason before concluding "justified divergence" — widening a shared
  signature with a compatible default is cheap; a second implementation is
  not.

## Changing shared code

**Anyone may propose a change. Never ship a consumer that depends on a
proposal that has not landed.**

The second half is the one that bites. If a consumer ships its adoption in
the same delivery as its proposal, this repo is no longer deciding — it is
choosing between accepting a design sight-unseen and leaving that consumer
broken. Had the proposal been rejected, or accepted with changes, a shipped
consumer would have been the argument for accepting it unchanged.

1. **Propose, then adopt — never in the same delivery.** Wait for the
   change to land here and be announced. THEN adopt, in a separate cycle.
   If that means your work sits unfinished for a turn, it sits unfinished.
2. **A working patch with tests is a better proposal than prose** — and it
   is still a *proposal*. This repo reviews, merges, and may change it.
3. **Never pick the version number.** Say "additive, suggest a minor bump"
   and leave the number to this repo. Two proposals numbering
   independently collide.
4. **Your patch is against a base that has already moved.** Send the
   narrowest set of files — propose the *function*, not the repo. A
   whole-file copy of `pyproject.toml` reverts whatever landed since you
   forked.
5. **A new shared API is a design decision, not a bug fix.** Fixing shared
   logic you already depend on is routine. Adding a new public surface — a
   new function, module, or return shape — changes what every other
   consumer must live with, so it needs a ruling BEFORE you build on it.
   That is the line rule 1 protects.

In return, a proposal gets **a ruling, promptly, with reasons — including
when the answer is no.** A proposal held indefinitely is its own failure
mode, and a consumer left waiting is why rule 1 gets broken.

## Specs

A change to anything under `specs/` requires a version bump and regenerated
golden-pair expectations. Consumers' conformance tests are the propagation
mechanism: a spec bump a consumer hasn't adopted surfaces as that
consumer's failing test, which is the intended cross-project alert.

## Compatibility and CI

Consumers pin `@main` (see README), so **every push here is live in every
consumer's next install.** CI is therefore a gate on what consumers depend
on, not a convenience: ruff + mypy + the test suite, on both ends of the
supported Python range, with tool versions pinned exactly (never floored —
a floored checker lets a tool release redden a build with no code change
from anyone).

When a push here breaks a consumer anyway — a behavioral change the gate
cannot see — the fix belongs in the same work cycle: fix forward or revert
immediately, rather than having the consumer pin around it.

## Testing conventions

`tests/` is deliberately thin. Spec-driven modules are verified by
consumers' conformance tests. Local tests cover the surfaces whose wrong
answer is **silent** — where a bug produces a plausible result rather than
an error.

Two conventions worth keeping:

- **`tests/conftest.py` fails the run if `eidr_core` resolves outside the
  working tree.** A `src/` layout plus an accidental non-editable install
  will otherwise test an installed *copy*, so a broken tree passes.
- **Where two code paths must agree, test them against each other.** A
  per-path test cannot catch divergence between paths; only a comparison
  can. `inheritance` is the worked example — its two shape adapters are
  asserted to produce identical results from identical inputs.

## Documentation

Comments should explain **why**, not what. When behavior changes, update
the comments, the docs, and the tests in the same change.
