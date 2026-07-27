# Unified Match-Candidate Evaluation & Scoring (design, v1)

**Status: ✅ APPROVED by operator, 2026-07-27** (register Phase 2.2 shape
decision). Operator emphasis on approval: **per-creation-type rules and
weights are the load-bearing structure** — they enable future tuning with
constrained, type-scoped impact and MUST be preserved as the organizing
structure of `compare-spec.json`. Migration (§6) may proceed; step 1 starts
after the parallel BMR-Review tuning thread has ingested the coordination
notes in BMR-Review's CLAUDE.md.
**Problem:** BMR-Review and De-Dupe UI evaluate the same thing — the matching system-generated
match candidates against EIDR records — with two independently designed scoring
engines. The operator wants ONE approach so accuracy work in either tool
benefits both.

---

## 1. What the two engines actually are

| | BMR-Review (`eidr_dedup_score`) | De-Dupe UI (spec v1.4.5) |
|---|---|---|
| Job emphasis | Batch adjudication: Accept / Review / Reject, auto-accept safety | Interactive review: rank candidates in a the matching system bucket, per-field glyphs |
| Field comparison | Continuous quality q ∈ [0, 1+bonus]: fuzzy titles, greedy alignment, precision-aware date half-lives, duration abs/relative credit, epoch-date handling | Four discrete states — identical / similar / mismatch / neutral — per named rule with normalization flags |
| Aggregation | Weighted average of per-field qualities over fields present on both sides; per-creation-type weights + calibration thresholds onto shared bands (<30 Reject, 30–<80 Review, ≥80 Accept) | Baseline 50 + additive weights per fired rule, − penalties, clamp 0–100 |
| Guards | Large learned library: alt-ID conflict shaping, Accept-corroboration, Series format-sale gate, supplemental short-form, early-cinema profile, part numbers, cross-season/cross-type, epoch dates, inherited-field discount, IMDb reconciliation | None (deliberately simple) |
| Explainability | `ScoreResult.rationale`: per-field weight/quality/contribution + gate notes | Normative requirement: debug reports which rules fired |
| Config | Python constants (`config.py`) — though `score_pair` already consumes a weights *spec dict* | Declarative JSON (`review_score_rules.json`), "tune here, never in code" |
| Validation | ~1,371 human decisions; empirically tuned (e.g. the 99+ auto-accept threshold) | Untested (unbuilt) |

**Key observations**

1. The engines agree at the **comparison layer** in intent: both need "how alike
   are these two titles / dates / durations / people lists?" De-Dupe UI's four
   states are a *quantization* of BMR-Review's continuous quality — `identical`
   ≈ q at/near 1 after normalization, `similar` ≈ mid-band q, `mismatch` ≈ low q
   on a conflict-bearing field, `neutral` ≈ field absent (q = None). They are
   the same measurement at two resolutions, not two measurements.
2. They genuinely differ at the **aggregation layer** — and there the additive
   model is measurably weaker for accuracy: it loses information at the state
   boundary (a 0.79 and a 0.94 title similarity can band identically), has no
   per-creation-type calibration, biases sparse records toward the baseline,
   and carries none of the guard library. Every guard in BMR-Review exists
   because a real misclassification was observed; that library **is** the
   accumulated experience the operator wants shared.
3. De-Dupe UI's real contributions are not its formula: they are the
   **declarative-config discipline**, the normative **explainability
   requirement**, the **state/glyph presentation model**, and the **candidate
   sort** (bucket → score → stable tie-break).

## 2. Proposed unification: one engine, layered; the second engine becomes a view

Do not merge the two formulas. Adopt a four-layer architecture with a single
scoring engine, where everything De-Dupe UI needs is a *projection* of that
engine's output:

```
L1 Normalization      normalized-record spec + eidr_core.normalize
L2 Field comparison   ONE comparator library → per-field quality q + meta
                      (conflict, precision, estimated, system-generated…)
L3 Aggregation        ONE scoring model (seeded from BMR-Review): weights,
                      calibration, guard library → score, band, verdict,
                      rationale       ← configured by compare-spec.json
L4 Presentation       per-surface views of L2/L3 output:
                      • BMR-Review reports: verdict + rationale rows
                      • De-Dupe UI: state glyphs (banded q), candidate sort,
                        debug "rules fired" (= rationale + gate notes)
```

* **L3 keeps BMR-Review's model** — continuous, calibrated, guard-rich,
  empirically validated. This is the accuracy decision.
* **The compare-spec (Phase 2.2) becomes this engine's versioned runtime
  config**, adopting De-Dupe UI's tune-in-JSON philosophy: everything now in
  `config.py` (weights per creation type, thresholds, gate constants, band
  edges) externalizes to `eidr-core/specs/compare-spec.json` with a version
  number. `score_pair` already takes a spec dict, so this is a config-loading
  change, not a rewrite. One tune → both tools, by construction.
* **The four states are defined IN the spec** as bands over q with per-field
  thresholds and De-Dupe UI's `conflictState` semantics, so a UI glyph and a
  scoring contribution can never disagree — they are the same number.
* **Explainability is satisfied by construction**: the engine's rationale
  (field, weight, quality, contribution, applicability + gate notes) is exactly
  "which rules fired," surfaced in the UI's debug mode.

## 3. How the node.js UI gets scores without sharing Python code

The operator's Phase 4.1 pilot design already answers this: De-Dupe UI's first
data source is a **BMR-Review-generated work list**. Therefore:

1. **Pilot (file mode):** the engine scores every candidate at work-list
   generation time. The work-list format (Phase 2.6) carries, per candidate:
   `score`, `band/verdict`, per-field `state` + `quality`, and `rationale`.
   The UI *renders*; it never scores. Zero JS reimplementation, zero drift.
2. **User-added candidates** (the "conceptual 0th bucket"): during the pilot,
   the UI appends an `unscored` request row to the results file; a rescore pass
   (or the next work-list generation) fills it. Longer term —
3. **API-Shim mode:** the same engine runs behind a small scoring service
   (localhost or server-side), which the Shim path needs anyway. One engine
   everywhere.
4. If an in-browser scorer is ever truly required, the compare-spec + golden
   corpus make a faithful JS port *verifiable* — but it is not built now.

Efficiency: scoring happens batch-side in Python (rapidfuzz is C-backed); the
UI stays thin; there is one engine to maintain and one config to tune.

## 4. What each tool contributes to the unified design (nothing is "the loser")

* From **BMR-Review**: the comparator library, the aggregation model, the guard
  library, the calibration bands, the human-decision validation set.
* From **De-Dupe UI**: versioned declarative config as the ONLY tuning surface;
  the normative explainability contract; the identical/similar/mismatch/neutral
  presentation model + `conflictState`; the candidate sort
  (upstreamBucket → score → stable id); the field-manifest idea (binding displayed
  fields to comparison rules).
* Shared output scale: the <30 / 30–<80 / ≥80 bands become the portfolio's
  verdict semantics; De-Dupe UI's baseline-50 additive score is retired
  (its spec §9.5 revised to reference this design).

## 5. The feedback loop (the operator's stated goal)

One engine + one config + one corpus makes cross-tool learning automatic:

* Reviewer decisions appended to the De-Dupe UI results file join the
  human-decision evaluation set BMR-Review tuning already uses.
* Any tune is a compare-spec version bump; the golden-pair corpus (Phase 2.3)
  regenerates; both surfaces pick it up on next run — and a stale consumer
  fails its conformance test (the drift alarm).
* Every misclassification found in either tool becomes a golden pair, so no
  regression can silently return.

## 6. Migration plan (each step small and independently useful)

1. **Extract L2** comparators (+ `nonlinear`, gate helpers as needed) into
   `eidr_core.compare`; BMR-Review imports them. (Phase 3 item 6, pulled
   forward; eidr-dq's `matching/compare.py` primitives fold in here too.)
2. **Externalize L3 config**: generate `compare-spec.json` v2.0 from the
   current `config.py` values; the engine loads the spec; `config.py` becomes a
   thin loader. Define the q→state banding + rationale schema in the spec.
3. **Phase 2.6** work-list/results formats include the per-candidate scoring
   payload (score, band, states, rationale) + the `unscored` request row.
4. **Phase 4.1** builds De-Dupe UI as a renderer of those payloads.
5. **Phase 2.3** golden corpus pins the ONE engine; the ~1,371 human decisions
   become its evaluation set.
6. Later: scoring service for API-Shim mode; De-Dupe UI spec §9.5 revised.

## 7. Trade-offs stated plainly

* De-Dupe UI's additive model is discarded as a *scoring* mechanism. Its
  simplicity argument is real, but explainability is preserved via rationale
  reporting, and the additive model's information loss + no-calibration +
  sparse-record bias are accuracy costs the operator's goal rules out.
* The UI depends on engine-produced payloads (file now, service later) instead
  of being self-contained. That is the price of one engine — and it matches the
  already-chosen pilot architecture.
* De-Dupe UI spec v1.4.5 §9.5 must be revised (operator owns that document).

## 8. Decision requested

Ratify: (a) one engine, BMR-Review-seeded L3; (b) compare-spec.json as its
versioned config and the portfolio's single tuning surface; (c) states = banded
qualities defined in the spec; (d) UI consumes engine payloads (file → service),
no JS scorer. Then migration step 1 can start.
