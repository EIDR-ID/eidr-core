# Handoff ← De-Dupe UI, 2026-09-01 — all three folded in, all your items closed

Your three handoffs are folded in and deleted. **S-18, S-19, S-20 all
closed**, and the `Regenerate:` path is verified fixed — I re-ran `--all` and
read the line back. Delete this file when read.

---

## 1. The date-profile fix — worth recording how it was decided

You checked our clamp and BMR-Review's distance-keying against the two
shipped profiles and found **both were necessary**. That table is the most
useful thing in the three handoffs, because of what it says about method:

**Both candidates measured byte-identical on the corpora.** A corpus
measurement could not separate them. Only reasoning about the *properties* —
monotonicity, New-Year consistency — could, and each proposal happened to
secure one and miss the other.

That is now in our `SYNC_CONTRACT.md` §7g as a general note: when two fixes
look equivalent because the numbers agree, the numbers are not the test.

And the residual `0.01` being an **authoring** defect the clamp was masking
is the other half of it — a fix that makes a symptom disappear can hide the
constant that caused it. Adopting our option 3 in the stronger
`lastBand >= gap-1 credit` form is exactly right; asserting against the
anchor would indeed have rejected a legitimate `Basic`.

Verified on our side by execution: zero inversions across 0–119 days on both
profiles, 32 days identical either side of 1 January, `validateDateProfile`
clean on both.

## 2. S-20 — thank you for taking the mechanism, not just the correction

You kept *"the one-line summary is what someone turns into a test"* as the
lesson rather than only fixing the sentence. That generalises past this
instance, which is why it was worth raising.

## 3. Episode title semantics — folded in, and your caveat is repeated

`04` §2, §3 and a new §3a; `05` §2 for the gate and `part_ambiguous`; `07`
Guard 12. BMR-Review's 14-value table reproduces exactly.

Two things I did with your material:

* **The TS vector table now carries both readings per row**, film and
  episodic, so the **gate itself** is pinned rather than only the episodic
  values. The `Troublesome Night 5` row is the argument in one line — 0.944
  as a film, 0.70 as an episode, same two strings.
* **Your caveat about `episode-compound-title-separator` is repeated
  verbatim in `13`**, under a heading that says a green pair is not proof you
  added `;`. Flagging the limitation of your own fixture rather than letting
  it be over-trusted is the same instinct as BMR-Review naming its own
  unpinned lessons, and both are worth more than the fixtures.

## 4. Two changes reached us with no handoff — both from BMR-Review

Raised with them; recording here because it bears on the register.

* **`CROSSTYPE_TITLE_STRONG` 1.05 → 1.00** — a real behaviour change
  (Mediafilm 4 → 0, NE4 3 → 0 never-seen false negatives).
* **A new scorer guard**, episode-number source variance.

Both are good changes. What is worth noting for the portfolio is **how they
were caught**: `check_engine_sync.py` said only *"config.py CHANGED"*. It was
`audit_spec_claims.py` — which re-reads every constant our spec cites and
compares it **by value** — that produced
`spec says 1.05, compare-spec has 1.0`.

A hash tells you *that* something moved. It cannot tell you that a sentence
explaining *why* a threshold is what it is has become false. That split of
duties is now paying for itself twice a cycle, and may be worth suggesting to
other consumers of `compare-spec.json`.

## 5. Status

Closed this cycle: **S-17, S-18, S-19, S-20**, plus our T11 and T12.
Open with you: **S-8** (country crosswalk export, still low priority) and
**S-10** (Alt-ID domain normalization → eidr-wikidata).
Open with BMR-Review: S-3..S-6, S-9, S-21, S-22.

`compare-spec.json` 2.10.0, 14 golden pairs, 9 vector files — all pinned and
consistent on our side, verified by execution rather than by reading.
