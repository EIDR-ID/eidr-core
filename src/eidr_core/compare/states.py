"""q→state banding + UI field-key mapping for scoring payloads.

Implements the ``states`` section of compare-spec.json (unified-scoring:
the De-Dupe UI's four comparison states are BANDS over the engine's per-field
continuous quality q — the UI renders states, it never computes them). Used
by payload producers (the BMR-Review work-list generator today; the Shim-mode
scoring service later) when building the per-candidate ``scoring`` object of
dedupe-worklist.md §4. Never used in scoring itself.

Banding (per spec, defaults identical_at=0.985 / similar_at=0.75):
    quality None            -> neutral   (field absent on a side)
    q >= identical_at       -> identical
    q >= similar_at         -> similar
    below similar_at        -> mismatch when the field is discriminative
                               (conflict-bearing), else neutral

Field keys: banding operates on ENGINE field names (the rationale's
``field`` values); the emitted payload keys are the De-Dupe UI
field-manifest keys (review_field_manifest.json) so states bind to displayed
rows with no mapping layer in the UI.
"""
from __future__ import annotations

# Engine rationale field -> De-Dupe UI field-manifest key. Engine names not
# listed map to themselves (they already coincide, e.g. release_date,
# director, actor, original_language, version_language, edit_class).
_ENGINE_TO_UI = {
    "title": "titles",
    "country": "country_of_origin",
    "assoc_org": "associated_org",
    "length": "duration",
    "alt_id": "alternate_id",
    "sequence_number": "season_number",
    "distribution_number": "episode_distribution_number",
    "house_sequence": "episode_house_sequence",
    "time_slot": "episode_time_slot",
}


def ui_field_key(field: str, creation_type: str | None = None) -> str:
    """Map an engine rationale field name to the UI field-manifest key."""
    if field == "end_date":
        # end_date scores on Series and Season profiles; the UI displays it
        # as two creation-type-specific rows.
        return ("season_end_date"
                if (creation_type or "").strip().lower() == "season"
                else "series_end_date")
    return _ENGINE_TO_UI.get(field, field)


def band(quality, field: str, state_bands: dict) -> str:
    """Band one per-field quality into identical|similar|mismatch|neutral."""
    if quality is None:
        return "neutral"
    default = state_bands.get("default", {})
    per_field = state_bands.get("per_field", {}).get(field, {})
    identical_at = per_field.get("identical_at",
                                 default.get("identical_at", 0.985))
    similar_at = per_field.get("similar_at", default.get("similar_at", 0.75))
    if quality >= identical_at:
        return "identical"
    if quality >= similar_at:
        return "similar"
    if field in set(state_bands.get("discriminative_fields", ())):
        return "mismatch"
    return "neutral"


def field_states(rationale: list, state_bands: dict,
                 creation_type: str | None = None) -> tuple[dict, dict]:
    """Build (field_states, field_qualities) for a scoring payload from an
    engine rationale (list of {field, weight, quality, contribution,
    applicable}). Keys are UI field-manifest keys; banding happens on the
    engine field name (the spec's discriminative_fields use engine names).
    Inapplicable fields are included as neutral/None so the UI can render
    every scored row's glyph slot."""
    states: dict = {}
    qualities: dict = {}
    for row in rationale or []:
        f = row.get("field")
        if not f:
            continue
        q = row.get("quality") if row.get("applicable") else None
        key = ui_field_key(f, creation_type)
        states[key] = band(q, f, state_bands or {})
        qualities[key] = q
    return states, qualities
