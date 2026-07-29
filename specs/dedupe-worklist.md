# De-Dupe Work-List & Results File Formats (SPEC v1)

**Status:** v1 — **producer LANDED 2026-07-28**: `BMR-Review/run_worklist.py`
emits this format from a post-the matching system BMR sheet (same inputs and scoring pass as
`run_assessment.py`, so work list and assessment always agree; per-candidate
payloads are built inside `evaluate_case` itself). v1 producer notes:
`enqueued_at` = generation timestamp (the sheet carries no enqueue times;
Shim mode will supply real ones); `upstream_bucket` = null with an optional
`upstream_score` field instead (the sheet carries the matching system scores, not bucket
labels) — the UI may sort on it within the null bucket; lookup-failed
candidates carry `"unresolved": true` and no `scoring`; record views
currently follow BMR-Review `render_record` (canonical class-ranked titles ✓;
alt-ID display order pending normalized-record §4 ratification). Originally
drafted as register Phase 2.6, 2026-07-27. Language-neutral
contract between **BMR-Review** (producer: work list + scoring payloads) and
the **De-Dupe UI** eidr-ui-nextjs module (consumer: renders, appends
decisions). This is the pilot's data plane per the approved
`unified-scoring.md` §3: the UI never scores; every score/state it shows
arrives in these files. In API-Shim mode the SAME per-candidate payload
schema (§4) is served by the scoring service — one schema, two transports.

Both files are **JSON Lines** (UTF-8, one JSON object per line, `\n`
terminated) — BMR-Review's existing house format (`*.assessment.jsonl`) and
append-friendly for the results side.

---

## 1. Files and lifecycle

| File | Writer | Reader | Mode |
|---|---|---|---|
| `<name>.worklist.jsonl` | BMR-Review generation run | De-Dupe UI | write-once per generation |
| `<name>.results.jsonl` | De-Dupe UI | operator; BMR-Review rescore/ingest | append-only |
| `<name>.worklist.supplement.jsonl` | BMR-Review rescore pass | De-Dupe UI | append per rescore |

Lifecycle: generate work list → review in UI (decisions and `unscored_request`
rows append to results) → rescore pass reads requests, appends scored
candidates to the supplement → UI merges supplement lines by
`transaction_id` + `candidate_id`. Decisions in the results file feed the
engine's human-decision evaluation set (`unified-scoring.md` §5).

## 2. Header line (line 1 of every file)

```json
{"type": "header", "format": "dedupe-worklist" | "dedupe-results" | "dedupe-supplement",
 "format_version": "1.0", "generated_at": "2026-07-27T12:00:00Z",
 "engine": {"name": "eidr_dedup_score", "version": "<pkg or git rev>"},
 "compare_spec_version": "<compare-spec.json version, or 'config.py' until step 2 lands>",
 "source": {"registry": "production|sandbox1|sandbox2", "run": "<generation run id>"}}
```

Consumers MUST reject a file whose `format`/`format_version` they don't
understand, and SHOULD surface `compare_spec_version` in debug views (it is
the tuning provenance of every score in the file).

## 3. Work-list line (`"type": "transaction"`)

One line per reviewable transaction:

```json
{"type": "transaction",
 "transaction_id": "…",                  // the matching system/Shim transaction id (or synthetic for backfill)
 "enqueued_at": "…",                     // ISO-8601; drives FIFO + aging buckets
 "submitting_party": "10.5237/…",
 "submitted": { <record view> },          // §5
 "candidates": [ { <candidate> }, … ]     // §4; MAY be empty (reviewer may Search-Registry add)
}
```

## 4. Candidate object — THE scoring payload (shared with Shim mode)

```json
{"candidate_id": "10.5240/XXXX-…",       // EIDR ID of the candidate record
 "upstream_bucket": "Very High" | "High" | "Medium" | null,   // null = user-added (0th bucket)
 "record": { <record view> },             // §5
 "scoring": {                             // ABSENT only on not-yet-scored user-added candidates
   "score": 87.3,                         // engine confidence, 0–100, calibrated per creation type
   "band": "Accept" | "Review" | "Reject",// <30 Reject, 30–<80 Review, ≥80 Accept
   "creation_type": "Basic" | "Series" | …,// weight profile used (per-type tuning provenance)
   "field_states":    {"<fieldKey>": "identical"|"similar"|"mismatch"|"neutral", …},
   "field_qualities": {"<fieldKey>": 0.0–1.0+, …},   // continuous q behind each state
   "rationale": [ {"field": "…", "weight": 50, "quality": 0.93,
                   "contribution": 46.5, "applicable": true}, … ],
   "notes": ["series country of origin differs …", …],   // gate/guard messages, verbatim
   "alt_id_conflicts": 0
 }}
```

Rules:
* `fieldKey` values are the De-Dupe UI field-manifest keys
  (`review_field_manifest.json`), so states bind to displayed rows with no
  mapping layer.
* States are the engine's banded qualities (`unified-scoring.md` §2); the UI
  MUST NOT recompute or override them.
* A candidate with no `scoring` renders **Unscored**, sorts after scored
  candidates within its bucket, and MUST NOT be approximated client-side.

## 5. Record view

The submitted/candidate `record` object is the **normalized record** per
`normalized-record.md` (field model + canonical ordering), so the UI's
comparison grid renders both columns without re-sorting. Display-layer
re-ordering (e.g. IMDb-first Alt IDs) is applied by the UI per
`normalized-record.md` §2 and never persisted back.

## 6. Results line types (append-only; one event per line)

```json
{"type": "decision", "at": "…", "operator": "10.5237/…",
 "transaction_id": "…", "action": "publish" | "match" | "reject" | "skip",
 "matched_candidate_id": "10.5240/…" | null,     // required for match
 "reason": "<ui_labels reason code>" | null,      // reject/skip reasons
 "note": "…" | null,
 "context": {"score": 87.3, "band": "Accept", "upstream_bucket": "High",
             "compare_spec_version": "…"} }       // copied from the payload for the eval set

{"type": "unscored_request", "at": "…", "operator": "10.5237/…",
 "transaction_id": "…", "candidate_id": "10.5240/…",
 "added_via": "search_registry"}
```

`context` is what makes each decision usable as an evaluation/tuning example
without re-joining files — the human verdict and the engine's verdict travel
together.

## 7. Supplement line

Same shape as a §4 candidate plus `transaction_id`, emitted by the rescore
pass for previously-unscored candidates:

```json
{"type": "candidate_supplement", "transaction_id": "…", <candidate fields incl. scoring> }
```

## 8. Versioning & conformance

* `format_version` bumps on any breaking shape change; `compare_spec_version`
  changes do NOT bump the format (payloads are self-describing).
* Golden-pair conformance (Phase 2.3) will include one fixture work-list line
  + expected render outcomes, pinning producer and consumer to this spec.
* Producer implementation home: BMR-Review generation (`run_assessment`
  lineage); consumer: the eidr-ui-nextjs De-Dupe module (`environments.json`
  → `local_worklist`).
