# golden_pairs_pending/ — fixtures drafted ahead of their engine version

A fixture here pins behaviour that the CURRENT compare-spec version does not
have yet. It would fail in `golden_pairs/`, and every consumer's conformance
test would go red for a change nobody has landed. So it waits here.

## Rules

1. **A pending fixture ships WITH the engine version that makes it pass.**
   Whoever lands that compare-spec version moves the file from this
   directory into `../golden_pairs/`, runs the regeneration (BMR-Review's
   `regen_golden_pairs.py`, which writes the `expected` block and refuses a
   fixture whose invariants the engine breaks), and commits both in the same
   change as the version bump. Never move a fixture without the version
   that makes it pass.
2. **No `expected` block here.** `expected` is a regenerated snapshot stamped
   with `spec_version` (golden-pairs.md §2). It does not exist until the
   engine that produces it does. The `invariants` are hand-written and
   value-independent, as in the corpus.
3. **Nothing reads this directory.** It is not package data
   (`pyproject.toml` ships `specs/golden_pairs/*.json` only), and no loader
   globs it, so a pending fixture cannot fail anyone's suite early. Read it
   from the eidr-core checkout.
4. **The `why` says why it is pending**: the handoff that asked for it, what
   the engine does today (and that the fixture fails on it), and which
   project's cycle lands it.
5. If the version that was meant to land it is rejected or changed, this
   repo revises or deletes the fixture. A fixture here is a draft, not a
   commitment.

## Waiting now

| Fixture | Waits for | Lands with |
|---|---|---|
| `internal-title-bridges-languages.json` | `INTERNAL_TITLE_DISCOUNT` in BMR-Review's `config.py` (the mechanism shipped inert in eidr-core 0.40.0) | the compare-spec version BMR-Review requests once its measurement holds and the operator says GO. Measured 2026-09-30 through BMR-Review's evaluator at 2.17.0: title 0.48, fails `field_quality_min {title: 0.5}`; with the knob at 0.8 (injected in-process only), title 0.80 and it passes |
| `internal-title-second-pair-earns-no-bonus.json` | the 2026-10-02 mechanism change (an Internal pair earns first-match credit only, branch `internal-title-no-bonus-2026-10-02`) plus the knob | the same version. Passes with the knob absent too, for the wrong reason (the translation is not compared), which is why it waits. Measured through BMR-Review's evaluator with the knob at 0.8: title 0.957 on the branch; 1.153 and FAILS `field_quality_max {title: 1.0}` on the 0.40.0 mechanism |
| `internal-title-carried-match-needs-alt-id-to-accept.json` | the knob plus BMR-Review's scorer rule `INTERNAL_TITLE_ACCEPT_REQUIRES_ALT_ID` (branch `internal-title-2026-10-02`) | the same version. Knob absent: title 0.33, FAILS `field_quality_min`; knob without the rule: 80.2 Accept, FAILS `verdict_not_in`; both: 79.0 Review, passes |
