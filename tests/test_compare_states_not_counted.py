"""S-29 Option B (operator, 2026-09-23): the glyph follows the quality, the
score follows the contribution; a row where they diverge is marked not
counted. Before this, field_states replaced a not-counted row's quality with
None and the disagreement Guard 1b preserved vanished in every consumer."""
from eidr_core.compare.states import field_not_counted, field_states

BANDS = {"default": {"identical_at": 0.985, "similar_at": 0.75},
         "discriminative_fields": ["release_date", "director", "length"]}
SUFFIX = ("| not the record's own value on the {side} side (inherited/system) "
          "-- mismatch not counted")


def _row(field, q, applicable, side=None):
    return {"field": field, "weight": 1, "quality": q, "applicable": applicable,
            "contribution": None if not applicable else q,
            "detail": (SUFFIX.format(side=side) if side else "")}


def test_a_not_counted_discriminative_field_bands_on_its_quality():
    states, qualities = field_states([_row("release_date", 0.1, False, "submitted")], BANDS)
    assert states["release_date"] == "mismatch"
    assert qualities["release_date"] == 0.1
    assert field_not_counted([_row("release_date", 0.1, False, "submitted")]) == {
        "release_date": "submitted"}


def test_a_not_counted_title_stays_neutral_and_the_marker_is_the_whole_signal():
    # Title is not discriminative: the glyph does not move, the key is the
    # entire signal. The case De-Dupe UI flagged as the one people get wrong.
    rows = [_row("title", 0.45, False, "candidate")]
    states, qualities = field_states(rows, BANDS)
    assert states["titles"] == "neutral" and qualities["titles"] == 0.45
    assert field_not_counted(rows) == {"titles": "candidate"}


def test_an_absent_field_is_still_neutral_none_and_not_marked():
    rows = [_row("actor", None, False)]
    states, qualities = field_states(rows, BANDS)
    assert states["actor"] == "neutral" and qualities["actor"] is None
    assert field_not_counted(rows) == {}


def test_an_applicable_row_is_untouched_and_not_marked():
    rows = [_row("director", 0.2, True)]
    states, _ = field_states(rows, BANDS)
    assert states["director"] == "mismatch"
    assert field_not_counted(rows) == {}


def test_side_defaults_to_both_when_the_suffix_is_absent():
    assert field_not_counted([_row("length", 0.3, False)]) == {"duration": "both"}


def test_the_signature_is_unchanged():
    assert field_states([], BANDS) == ({}, {})
