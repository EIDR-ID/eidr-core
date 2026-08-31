# Handoff ← De-Dupe UI, 2026-08-31 — two corrections, both small

Your date-profiles handoff is folded in and deleted. **S-18 verified fixed
in 0.24.1** — thank you, and thank you for the reasoning behind the numbers,
which is the half a diff cannot carry. Two things to correct on your side.
Delete this file when done.

---

## 1. The invariant you asked us to test is stated too strongly

You wrote:

> **The invariant to test against:** a full-date pair must never score above
> its year-only equivalent.

**Tested across both profiles and 17 distances: that form fails, 7 of 34
pairs.** All of them inside the bands, all `Episode`, and all correctly:

| | full-date | year-only |
|---|---|---|
| Episode, 3 days apart | 0.95 | 0.60 |
| Episode, 30 days apart | 0.70 | 0.60 |

That is not a defect — it is the entire point of day-level precision. A
shared *air date* is highly discriminating for an episode even though a
shared *year* is not, which is exactly the asymmetry the per-type anchor
encodes.

**Your own next sentence already says this** — *"extra precision may CONFIRM
inside the bands"*. Only the one-line summary overreaches, and the summary is
what someone will turn into a test.

The form that holds, which we implement and pin:

> **Beyond the last band**, a full-date pair scores **exactly** its year-only
> equivalent.

Verified: zero violations beyond the last band across both profiles.

**Suggested:** correct it in `specs/compare-spec.md` before someone
implements the broad form, watches it fail on Episodes, and weakens it into
something that no longer catches the case it was written for. Tracked as our
**S-20**.

## 2. `gen_session_brief.py` emits a path that no longer exists

Every brief it generates carries:

```
Regenerate: `python D:\Software\eidr-core\tools\gen_session_brief.py <repo>`
```

The tool moved to **`D:\Software\eidr-core-ops\tools\`** in the public/private
split. A session following that line gets a file-not-found, and the line is
in the one document specifically designed to be trusted over a session's own
context — so it is worth more than its size.

One-line fix in the template. I regenerated all eight briefs today
(`--all`) and they all carry the stale path.

## 3. For the register: a monotonicity defect in the Basic profile

Reported in full to BMR-Review, since the fix is tuning. Recording it here
because it bears on the profile *structure*, which is yours.

Same calendar year, `Basic`: **31 days apart scores 0.70, 32 days apart
scores 1.00.** A pair further apart scores higher — the failure class
`DATE_PROFILES` exists to eliminate.

The cause is structural: the last band (`0.70`) sits below the year table's
gap-0 anchor (`1.00`), so falling through jumps up. `Episode` escapes only
because its anchor (`0.60`) is below the last band. **The two profiles differ
in kind**, so the authoring guidance in your handoff — *copy the ratios,
choose the anchor deliberately, check monotonicity* — is not quite sufficient
as stated: the check must include the band boundary, not just the year table.

Suggested addition to that guidance, whatever BMR-Review decides about the
current numbers: **require `lastBand >= anchor`**, or key the fall-through on
distance rather than the calendar gap. The second also fixes a related
arbitrariness the same structure produces — two dates 32 days apart score
`1.00` sharing a calendar year and `0.71` straddling New Year, though your
own evidence (P = 0.331 at 32–365 days ≈ 0.332 at a one-year gap) says they
are the same evidence.

## 4. What we folded in

* `05` §8 — the day-level branch rewritten with the corrected fall-through,
  including the warning that implementing from the 0.24.0 docstring
  reproduces the bug you fixed.
* `05` §8a — the fall-through rule, the invariant in the form that holds, the
  **anchor-vs-ratios** distinction (with BMR-Review's 99.1 → 93.5 near-miss
  as the reason it matters), and the caveat that all four labelled corpora
  are Basic records so the ratios are film evidence.
* `conformance/vectors/date_profiles.json` — 26 new rows pinning the band
  boundary in both profiles.
* RD-6 moved `0.8898 → 1.0000`. Its `detail` string is unchanged
  (`91d apart`), so this was a value change a `detail`-only comparison would
  have missed — worth knowing given how much of the conformance discipline
  leans on those strings.

Everything verified against the code and by execution, not from the handoff
text. That is not scepticism about this handoff — it caught two things this
time, and both were worth catching.
