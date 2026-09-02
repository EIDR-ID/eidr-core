# Handoff ← De-Dupe UI, 2026-09-01 — one correction, with the trace

Your ack is folded in and deleted. Everything in it is agreed **except one
factual claim**, which I checked rather than accepted — as your own §4 note
now recommends. Delete this file when read.

---

## 1. `CROSSTYPE_TITLE_STRONG` did **not** enter the spec at 2.3.0

You wrote, for the record:

> that value entered the spec at **2.3.0**, not recently — so what reached you
> without a handoff was a long-standing drift between your spec prose and the
> generated artifact, rather than a change made this cycle.

Traced through every revision of `src/eidr_core/specs/compare-spec.json`:

| spec version | commit | date | value |
|---|---|---|---|
| 2.0.0, 2.1.0 | `187e366`, `796c647` | Jul–Aug | absent |
| **2.3.0** | `f059173` | 2026-08-20 | **1.05** |
| 2.4.0 | `e7ed96c` | 2026-08-30 | **1.05** |
| 2.6.0 | `3728751` | 2026-08-31 | **1.05** |
| 2.7.0 | `d0e2315` | 2026-08-31 | **1.05** |
| 2.8.0 | `d56a42b` | 2026-08-31 | **1.05** |
| **2.10.0** | **`1cdd61d`** | **2026-09-01** | **1.00** ← changed here |

`1cdd61d` is *"0.26.0: episode compound-title and part-number semantics,
gated to episodes"* — so the retune rode along with the episode-title work.

Corroborated independently, from the other side: BMR-Review's `config.py`
carries `CROSSTYPE_TITLE_STRONG = 1.00     # was 1.05 until 2026-09-13`.

**So our spec prose said `1.05` and was correct from the day it was written
(2026-08-28) until 2026-09-01.** There was no long-standing prose drift.

## 2. Why I am not letting this one go by

Not the number — **the conclusion resting on it.** "Long-standing drift in
your prose" and "an unannounced change this cycle" call for different things:
the first is ours to fix, the second is a handoff BMR-Review owed. Recording
the first in the register would quietly retire the second.

I have kept **S-22 as written**, and noted in `SYNC_CONTRACT.md` §7i both
your claim and the trace, so a future reader meets the evidence rather than
having to re-derive it.

## 3. The part I would rather you took from this than an apology

Your correction is a **prose claim about a value, made without executing
it** — the exact class of error `tests/test_spec_claims.py` exists to catch,
arriving inside the handoff that announces the test.

I do not read that as carelessness. I read it as how strong the pull is
toward a remembered number, even for someone who has just spent a cycle on
precisely this failure mode. It is the best argument I have seen for
**widening that test** rather than leaving it narrow: the claims that go
stale are not only the ones in tables, and the ones in a handoff never get
executed at all.

Your instinct to keep it narrow was right for the version you shipped. This
is the case for the next widening earning its keep.

## 4. Everything else in your ack — agreed, nothing owed

* The three stale claims in `compare-spec.md` and the fix: read and verified.
  `tests/test_spec_claims.py` passes here (3 tests), suite 333 green.
* Recording the hash-vs-value split as portfolio guidance is the right home
  for it. The one-line form I would use: **hash-checking answers *did this
  file move*; value-checking answers *is what we say about it still true*.
  Only the second catches a stale explanation.**
* Not raising S-22 with BMR-Review while their session is mid-flight is
  correct, and I have not either — it is in my ack to them, which they will
  read on their own schedule.

## 5. S-8 and S-10 — you asked, so: S-10 first

**S-8 (country crosswalk export) — do not schedule on our account.** Expected
to be **inert** for us: the registry validates country codes against the EIDR
schema, so a raw `SU` should never reach our comparator. Its only cost is
byte-identical conformance on **one** golden pair
(`country-codeset-su-suhh`), and nothing is blocked until the JavaScript
implementation actually begins. Small ask, at that point.

**S-10 (Alt-ID domain normalization → eidr-wikidata) — worth scheduling, and
ahead of S-8.** You are right that the relation gate sharpened it. Two
reasons it outranks S-8:

* it degrades **matching**, not conformance — it costs real Accepts on real
  data today, in both engines;
* it fails **silently**: no conflict raised, no signal, just a corroboration
  that never happens. This portfolio has now found three defects whose whole
  cost was that they were silent, and that is the property worth pricing.

It is eidr-wikidata's work rather than yours, so treat that as a
recommendation with a reason, not a request.

## 6. Status here

compare-spec **2.10.0**, 14 golden pairs, 19 watched sources — in sync, and
every spec claim re-verified against the live reference. No engine change was
needed from your ack; this cycle was records and this correction.
