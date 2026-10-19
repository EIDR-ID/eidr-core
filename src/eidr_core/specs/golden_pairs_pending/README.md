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

* `episode-part-one-sided-corroborated-stays-in-review` (2026-10-19) --
  waiting on a **ruling**, not on an engine version, which is the exception
  to rule 1: it PASSES on compare-spec 2.21.0 and fails on 2.20.0. It pins
  that a one-sided Episode part ("The Long Night Part 2" vs "The Long Night")
  stays in Review at 79.0 even with two agreeing identity Alt ID sources:
  since 2.21.0 the pair takes BMR-Review's part-ambiguous cap, where it used
  to take the part-number override (>= ALT_CORROBORATION_STRONG_MIN sources,
  no cap) and Accept at 99.6. That override's own comment names this very
  case ("a series title's volume designation is often carried by only one
  side"), so whether the ambiguous branch should honour the same
  corroboration is BMR-Review's scorer decision. If BMR-Review keeps the cap,
  the fixture moves into `../golden_pairs/` and is regenerated; the
  behaviour belongs to 2.21.0, so whether moving it needs a stamp of its own
  is this repo's call under golden-pairs.md section 7. If it honours
  corroboration, this repo deletes or inverts the fixture in the cycle that
  lands that change. Mutation evidence is in its `why`.

The last four (`internal-title-bridges-languages`, `internal-title-second-pair-earns-no-bonus`, `internal-title-carried-match-needs-alt-id-to-accept` and `sibling-title-lookalike-altid-anchor-is-held`) moved into `golden_pairs/` with compare-spec 2.18.0 (2026-10-02).
