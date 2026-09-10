# Golden-pair corpus — fixture formats

**Status:** `pair` mode LANDED 2026-07-29; `case` mode and `recovery_pool`
RATIFIED 2026-09-10 (S-26 / S-9), implementation pending in the evaluator.
**Owner of the format:** eidr-core. **Owner of the evaluator:** BMR-Review
(`eidr_dedup_score/golden.py`). **Conforming implementation:** De-Dupe UI,
in JavaScript, with no database.

The corpus lives at `src/eidr_core/specs/golden_pairs/*.json` and is the
only thing that pins cross-language engine behaviour. Every fixture carries
one *learned lesson*, and the lesson must be stated in `why` — including the
fixture's **scope**, which is what a later rewrite most easily loses.

---

## 1. Why three shapes, and why not one

A `pair` runs the **pair scorer** (`score_pair`) on one submitted record and
one candidate and pins field qualities, states, and the score band. That is
everything the corpus covered until 2026-09-09, and it decides *presentation*
and *score*.

It cannot pin the **verdict layer** — `report.evaluate_case` is never
entered. So nothing in the corpus could express: any assessment string, or
which of them clear without a reviewer; `TERMINAL_NOMATCH`, and therefore
which rows get a registry search before they close; the Edit gate in either
direction; the sole-Accept and controversial paths; or anything about
candidate *sets*, since a pair is one candidate by definition. Three of De-Dupe
UI's fourteen specification files (`09`, `10`, half of `11`) were therefore
**unpinned by construction, not by omission** — and those are the files that
decide *outcomes*.

That layer is also where the last three silent defects lived. A wrong verdict
string reads correctly (`"Disagree: no match"` is better English than
`"Disagree: all candidates rejected"`, and only the second clears without a
reviewer). A set-membership error has no symptom at all. Hence `case`.

`recovery_pool` is separate again: recovery needs a candidate *pool* that a
mirror returned, and under-recall is the one defect that produces a wrong
**outcome** rather than a worse-presented one — the reviewer sees nothing,
confirms No Match, and the match stays in the registry.

## 2. Common fields

```json
{
  "id":    "<kebab-case, unique, names the lesson>",
  "added": "YYYY-MM-DD",
  "why":   "<the lesson, the defect it pins, and the fixture's SCOPE>",
  "mode":  "pair" | "case" | "recovery_pool",
  "expected": { "spec_version": "...", ... },
  "invariants": { ... }
}
```

* `mode` absent means `"pair"`. **Every fixture that existed before
  2026-09-10 is unchanged and the loader stays backward compatible.**
* `expected` is a **regenerated snapshot** stamped with `spec_version`.
  Never hand-edit it; `regen_golden_pairs.py` writes it. A stale
  `spec_version` is the designed post-tune alert.
* `invariants` are **version-independent lessons**, hand-written, and are
  what a fixture is *for*. See §6.
* Synthetic IDs use the `FEED-` prefix with a correct check character where
  validity matters to the lesson (`is_valid_eidr_id` rejects `GOLD-`, which
  is not hex). Only pairs whose lesson depends on validity need valid IDs;
  the rest may keep `GOLD-` and the inconsistency is deliberate.

## 3. `mode: "pair"` (default)

```json
{
  "submitted": { <record> },
  "candidate": { "eidr_id": "...", <record> },
  "expected": {
    "spec_version": "2.11.0", "confidence": 94.6, "verdict": "Accept",
    "field_qualities": { ... }, "field_states": { ... }, "alt_id_conflicts": 0
  },
  "invariants": { "verdict_in": [...], "score_min": 80.0, ... }
}
```

Invariant vocabulary: `verdict_in`, `verdict_not_in`, `score_min`,
`score_max`, `field_quality_min {field: q}`, `field_quality_max {field: q}`,
`alt_id_conflicts_min`. Prefer `verdict_not_in` over `verdict_in` and a
`field_quality_max` over a pinned value: **a property survives a retune, a
value must be re-approved at each one.**

## 4. `mode: "case"` — the verdict layer

```json
{
  "id": "edit-info-absent-holds-for-review",
  "mode": "case",
  "creation_type": "Edit",
  "tamr_kind": "AUTO",
  "submitted": { <record> },
  "candidates": [ { "eidr_id": "...", <record> }, ... ],
  "expected": { "spec_version": "...", "assessment": "...", "proposed_id": "...", "notes": [...] },
  "invariants": {
    "assessment_not_in": ["Agree"],
    "proposed_id_not": "10.5240/FEED-...",
    "clears_without_review": false,
    "notes_match": ["base object data accepts", "asserts no EditInfo"],
    "notes_not_match": ["demonstrably different"]
  }
}
```

Rules, each of which comes from a defect that already happened:

* **`creation_type` is explicit**, never inferred from a candidate.
  `evaluate_case` takes it as an argument, and inferring it is exactly the
  kind of helpfulness that makes a fixture pass for the wrong reason.
* **`candidates` is a list.** Candidate-*set* behaviour (sole-Accept,
  controversy, sibling pools) is the point of the mode.
* **`clears_without_review` is COMPUTED from the terminal set**, never
  written as a literal string. It pins the *consequence* — did a reviewer
  see this row — rather than the *label*, and the label is precisely what
  moved under both engines in September 2026 without the consequence
  changing. A fixture that literalised `"Disagree: all candidates rejected"`
  would need re-approval for a change that altered no behaviour.
* **`assessment_not_in` beats `assessment_in`** for the same reason
  `verdict_not_in` does.
* **`notes_match` / `notes_not_match` take substrings (or patterns), never
  exact text.** Two reasons. Wording must stay free to improve without
  re-pinning every fixture. And exact text is *impossible* here anyway: the
  Edit-gate note embeds the candidate's EIDR ID mid-sentence, so no fixture
  could carry a string that survives a different candidate.
* **`notes_match` exists because `assessment_not_in` and
  `clears_without_review` cannot distinguish a correct outcome from a
  correct outcome reached for no stated reason.** The `notes[]` entry is the
  reviewer's only visible explanation. A row closed as rejected with no note
  is indistinguishable from an ordinary shortlist rejection; an
  implementation emitting the right assessment and silently skipping the
  note passes every other invariant and is wrong in exactly the place a
  human sees. *A reviewer must never be closed out by a difference the
  interface cannot show them — here, closed out with no reason shown.*
* **`notes_not_match` exists because a gate needs a fixture for NOT
  firing.** The Edit gate must not run on a BOD `Review` — ambiguous base
  data warrants a human (operator, 2026-09-08). An implementation that runs
  it anyway can land on the same assessment by coincidence and pass every
  positive invariant. This is the 2026-09-02 both-directions lesson applied
  to notes: without it, "passes" only means "agreed by accident".

**Scope statement, so consumers do not assume coverage:** notes are IN scope
via the two invariants above. Anything a `case` fixture does not name in
`invariants` is not covered by that fixture, whatever `expected` happens to
snapshot.

The two fixtures already drafted against this mode, both traps where a wrong
implementation passes every positive test:

1. `edit-info-absent-holds-for-review` — one side asserts no EditInfo; must
   reach Review, never auto-match. The trap: `_EDIT_INFO_FIELDS` (presence)
   and `_edit_key` (comparison) are deliberately asymmetric, and "tidying"
   them makes two empty keys compare equal — every pair auto-matches, no
   symptom.
2. `edit-approximate-length-normalisation` — differs only in
   `ApproximateLength`, expressed as a float (XML adapter) on one side and
   ISO-8601 text (mirror) on the other, same displayed minutes. Must be
   EQUAL. Comparing raw demoted 115 of 264 Edit rows whose displayed lengths
   were identical.

## 5. `mode: "recovery_pool"` — recovery search

```json
{
  "id": "episode-sibling-under-same-parent",
  "mode": "recovery_pool",
  "why": "...",
  "submitted": { <rendered view> },
  "pool": [ { <rendered view> }, ... ],
  "expect": { "recall": "10.5240/FEED-..." }
}
```

* **Captured, not queried.** A fixture is recorded once from a real mirror
  run (`run_assessment.py --record-canon PATH`, BMR-Review T17) and replays
  offline forever after. That is what makes it portable to JavaScript with
  no database — the whole point of S-9.
* **Records are rendered VIEWS, not EIDR-JSON**, deliberately. EIDR-JSON
  would need a second serializer that inverts `loaders.from_json`, free to
  drift from the parser it must mirror. A rendered view is already the
  payload De-Dupe UI consumes. The inverse (`canon.from_view`) is pinned by a
  round-trip assertion against `render_record` itself rather than field by
  field, so it cannot pass by agreeing with itself.
* **`pool` holds candidates AND parents.** A fixture that cannot resolve the
  parent chain cannot reproduce the family gate, and the family gate decides
  whether a recovered candidate was eligible at all.
* **The invariant is `recall`: the correct record IS IN the pool.** Not a
  score. Under-recall produces a wrong *outcome*; a score produces a
  worse-presented one. A recall assertion survives every retune; a score
  must be re-pinned at each one, which is how a fixture becomes noise.

**Status:** the shape is ratified; the first captured instance is owed by
BMR-Review (T17 step 2, needs a mirror run). The loader lands against that
instance rather than against this document alone.

## 6. What every fixture must satisfy before it lands

1. **Mutation-tested, and the mutation named in `why`.** Disable the rule
   the fixture pins and confirm the fixture FAILS while every other pair
   stays green. A fixture that passes its own mutation test is worse than
   no fixture — it certifies a lesson it does not hold. (First parent pair,
   2026-09-04: used different seasons, would have passed with the family
   gate broken; replaced.)
2. **Both directions for a gate.** The positive case alone pins the
   *absence* of the gate equally well. `season-resolved-parent-is-comparable`
   sat alone from 2026-09-05 and the corpus was blind to `_same_series`
   entirely until `crosstype-family-gate-ineligible` landed — during which
   De-Dupe UI downgraded that gap's severity on the strength of coverage
   that could not detect the thing it was crediting.
3. **One lesson per fixture.** Starve a fixture of anything that would let
   it pass for a *different* reason (the family-gate pair carries no Alt ID,
   because a common Alt ID would floor it to Review through Guard 7 — that
   is a separate lesson with its own pair).
4. **Scope stated when it is narrower than it looks.**
   `episode-compound-title-separator` fails against the full pre-0.26.0
   comparator but cannot isolate the `;` delimiter, because normalisation
   strips `;` and the fallback rescues it. That is in its `why` so that a JS
   implementation which also strips `;` does not read a green pair as proof
   it added the delimiter.
5. **Properties over values in `invariants`.** See §3.

## 7. Versioning and regeneration

`COMPARE_SPEC_VERSION` lives in BMR-Review's `config.py` (the authoring
surface). A tuning change: bump it there → `regen_compare_spec.py` → this
repo's `compare-spec.json` → `regen_golden_pairs.py` → every `expected`
re-stamped → commit BMR-Review and eidr-core together. The failing-snapshot
alert in between is designed, not a defect.

A **rule** change (a new verdict, a widened terminal set) is not a retune
and should not be absorbed into a corner of an unrelated cycle: it gets its
own bump, its own fixtures, and an ENGINE_SYNC handoff naming the corpus
*content* that changed — not just the count. Two pairs were replaced and an
invariant added on 2026-09-08 while the count stayed at 14 and the summary
said "regenerated: no"; that is the failure this paragraph exists to prevent.
