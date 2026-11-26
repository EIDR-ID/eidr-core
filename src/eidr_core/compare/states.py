"""q→state banding + UI field-key mapping for scoring payloads.

Implements the ``states`` section of compare-spec.json (unified-scoring:
the De-Dupe UI's four comparison states are BANDS over the engine's per-field
continuous quality q — the UI renders states, it never computes them). Used
by payload producers (the BMR-Review work-list generator today; the Shim-mode
scoring service later) when building the per-candidate ``scoring`` object of
dedupe-worklist.md §4. Never used in scoring itself.

Banding (per spec, defaults identical_at=0.985 / similar_at=0.75):
    quality None            -> neutral   (field absent on a side)
    quality real but the row NOT applicable (2.13.0 Guard 1b: an inherited
    or system-generated value that mismatched and was dropped from the
    denominator) -> banded on the QUALITY like any other row, and the field
    is listed in ``field_not_counted`` -- operator ruling S-29 Option B,
    2026-09-23: the glyph follows the quality, the score follows the
    contribution, and a row where the two diverge carries a not-counted
    marker the UI renders. Four states remain four.
    q >= identical_at       -> identical
    q >= similar_at         -> similar
    below similar_at        -> mismatch when the field is discriminative
                               (conflict-bearing), else neutral

Field keys: banding operates on ENGINE field names (the rationale's
``field`` values); the emitted payload keys are the De-Dupe UI
field-manifest keys (review_field_manifest.json) so states bind to displayed
rows with no mapping layer in the UI.

Per-item states (``field_item_states``; compare-spec 2.25.0, S-41): one state
per LIST item, extracted from BMR-Review's ``item_states.py`` on eidr-core's
ruling that it lives here beside the comparators, as ``field_not_counted`` did
at 0.38.0. Unlike the rest of this module it reads the RECORDS, because a
rationale row carries one quality per field and an item state needs the
item-level matching -- which is why it may use the comparators' private
helpers: the matching must be the comparators' own, or the item glyphs and
the field quality could disagree about what matched.
"""
from __future__ import annotations

import re
from collections import defaultdict

from eidr_core.altidtool_io import is_identity_relation
from eidr_core.normalize import norm_country, norm_lang, norm_name
from eidr_core.ordering import is_shortdoi

from . import _internal_title_discount, _title_simf, alt_source, fuzzy, is_internal, select_titles
from . import _params as config

# The public surface, as DICTIONARY.md documents it (2026-10-02).
# Star-imports (BMR-Review's shims use them) now take only these names,
# not the stdlib and third-party modules this file imports.
__all__ = [
    "band",
    "field_item_states",
    "field_not_counted",
    "field_states",
    "ui_field_key",
]

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

    A field whose quality is None (absent on a side; both sides inherited
    from one parent) is neutral/None so the UI can render every scored
    row's glyph slot. A field whose quality is REAL but which was not
    counted (``applicable`` false with a quality -- 2.13.0's Guard 1b) is
    banded on that quality: the reviewer must see the disagreement the rule
    preserved (S-29 Option B). ``field_not_counted`` says which those are.
    Until 2026-09-23 this function replaced such a quality with None, which
    hid the disagreement in every consumer at once."""
    states: dict = {}
    qualities: dict = {}
    for row in rationale or []:
        f = row.get("field")
        if not f:
            continue
        q = row.get("quality")            # the QUALITY, whatever applicable says
        key = ui_field_key(f, creation_type)
        states[key] = band(q, f, state_bands or {})
        qualities[key] = q
    return states, qualities


_NOT_COUNTED_SIDE = re.compile(
    r"not the record's own value on the (submitted|candidate|both) side")


def field_not_counted(rationale: list,
                      creation_type: str | None = None) -> dict:
    """``{manifest key: "submitted" | "candidate" | "both"}`` for every
    rationale row that carries a real quality and ``applicable`` false.

    That row shape exists only under Guard 1b (compare-spec 2.13.0): an
    inherited or system-generated value that mismatched and left the
    denominator. The side is read from Guard 1b's own ``detail`` suffix
    rather than re-derived from provenance, so this stays a pure function of
    the rationale; ``both`` when the suffix is absent. Emit the map in the
    scoring payload as ``scoring.field_not_counted`` ONLY when non-empty --
    an optional key absent on every previously valid payload, so
    ``format_version`` 2.0 stands (ruling 2026-09-24). Kept separate from
    ``field_states`` so its 2-tuple signature and callers are untouched.
    """
    out: dict = {}
    for row in rationale or []:
        f = row.get("field")
        if not f or row.get("quality") is None or row.get("applicable"):
            continue
        m = _NOT_COUNTED_SIDE.search(row.get("detail") or "")
        out[ui_field_key(f, creation_type)] = m.group(1) if m else "both"
    return out


# --------------------------------------------------------------------------
# Per-item states (S-41)
# --------------------------------------------------------------------------

# Rationale field -> the candidate record view's list key (BMR-Review's
# ``render_record``). Private: the view keys are the caller's contract, stated
# in ``field_item_states``'s docstring, not a table a consumer should import.
_VIEW_KEY = {
    "title": "titles",
    "director": "directors",
    "actor": "actors",
    "assoc_org": "assoc_orgs",
    "country": "countries",
    "original_language": "languages",
    "version_language": "version_languages",
    "alt_id": "alt_ids",
}

# Strength order for one view entry that stands for several items: mismatch
# outranks identical because a conflict is the thing a reviewer must not miss.
_RANK = {"neutral": 0, "similar": 1, "identical": 2, "mismatch": 3}


def _ck(x):
    # Casefolded, as the record view sorts and de-duplicates its entries, so
    # an item maps to the view entry that displays it.
    return str(x if x is not None else "").casefold()


def _free_text(q, field, bands):
    """Free-text lists band with the field's own bands and are never red:
    an unmatched name or title is an item with no counterpart, not a conflict
    (only the field as a whole can be discriminative)."""
    s = band(q, field, bands)
    return "neutral" if s == "mismatch" else s


def _keep(m, key, state):
    """A view entry may stand for several items (two people sharing a name):
    keep the strongest state, so an entry is never shown weaker than it is."""
    if _RANK[state] >= _RANK.get(m.get(key), -1):
        m[key] = state


def _item_titles(sub, cand, bands, field_dropped):
    """Each candidate title's best match against every submitted title, under
    exactly the rules ``cmp_titles`` uses: the same ``select_titles`` sets,
    the same Internal-title discount, and the same pairwise similarity
    (``_title_simf``, shared with the comparator, so a rule added there
    reaches the items too). Best-of-all rather than the comparator's greedy
    alignment: an item state answers "does this title have a counterpart",
    not "which pairing scored the field". A title outside the compared set
    (a system-generated title beside a real one) gets no entry: neutral."""
    view = {}
    if field_dropped:
        # Both sides system-generated only: the comparator ignored titles.
        return view
    discount = _internal_title_discount()
    inc = discount is not None
    s_use, _ = select_titles(sub.titles, include_internal=inc)
    c_use, _ = select_titles(cand.titles, include_internal=inc)
    s_use = [t for t in s_use if t.text]
    c_use = [t for t in c_use if t.text]
    if not s_use or not c_use:
        return view
    simf = _title_simf(sub, cand)[0]
    for ct in c_use:
        best = 0.0
        for st in s_use:
            q = simf(st.text, ct.text)
            if inc and (is_internal(st) or is_internal(ct)):
                q *= discount
            best = max(best, q)
        _keep(view, _ck(ct.text), _free_text(best, "title", bands))
    return view


def _item_people(sub_names, cand_names, field, bands):
    """Best ``fuzzy`` over normalised display names, zeroed below
    ``NAME_MATCH_MIN`` as the comparator zeroes it. The state is the
    PERSON's, so their sort-name entry in the view carries it too."""
    s_norm = [norm_name(p.display) for p in sub_names if p.display]
    view = {}
    for p in cand_names:
        if not p.display:
            continue
        cn = norm_name(p.display)
        best = max((fuzzy(sn, cn) for sn in s_norm), default=0.0)
        if best < config.NAME_MATCH_MIN:
            best = 0.0
        st = _free_text(best, field, bands)
        _keep(view, _ck(p.display), st)
        sn = getattr(p, "sort_name", None)
        if sn and str(sn).strip():
            _keep(view, _ck(str(sn).strip()), st)
    return view


def _item_orgs(sub, cand, bands):
    """The comparator's rule: equal party id is a full match, else ``fuzzy``
    over normalised names, below ``NAME_MATCH_MIN`` no match. An
    organization's alternate names carry the organization's state."""
    view = {}
    for oc in cand.assoc_orgs or []:
        best = 0.0
        for os_ in sub.assoc_orgs or []:
            if oc.party_id and os_.party_id and oc.party_id == os_.party_id:
                q = 1.0
            else:
                q = fuzzy(norm_name(os_.name or ""), norm_name(oc.name or ""))
            best = max(best, q)
        if best < config.NAME_MATCH_MIN:
            best = 0.0
        st = _free_text(best, "assoc_org", bands)
        for n in [oc.name or oc.party_id] + list(getattr(oc, "alt_names", None) or []):
            if n:
                _keep(view, _ck(n), st)
    return view


def _item_codes(sub_codes, cand_codes, normf):
    """Controlled vocabulary: ``identical`` when the normalised code is in
    the submitted record, else ``neutral`` -- never ``similar`` (a code
    matches or it does not) and never red (a second country is no conflict).
    ``XX`` / ``und`` normalise to nothing and stay neutral."""
    have = {normf(c.code) for c in sub_codes or [] if c.code} - {"", None}
    view = {}
    for c in cand_codes or []:
        if not c.code:
            continue
        n = normf(c.code)
        _keep(view, _ck(c.code), "identical" if n and n in have else "neutral")
    return view


def _item_alt_ids(sub, cand):
    """``cmp_alt_ids``'s own definition of a common Alt ID: Kind =
    ``alt_source``, identity relation only, ShortDOIs and opaque registry ids
    skipped. Equal value -> identical. The submission names the Kind with no
    equal value anywhere -> mismatch (the comparator's conflict). An extra
    value under a Kind that already matched -> neutral, because the
    comparator counts no conflict there. Keyed by (value, id_type, domain,
    relation) casefolded: Alt ID entries are not unique by value alone."""

    def ident(x):
        if is_shortdoi(getattr(x, "id_type", None), getattr(x, "domain", None)):
            return None
        if not is_identity_relation(x.relation):
            return None
        return alt_source(x)

    sub_by = defaultdict(set)
    for x in sub.alt_ids or []:
        k = ident(x)
        if k is not None:
            sub_by[k].add(str(x.value).strip().casefold())
    cand_by = defaultdict(set)
    for x in cand.alt_ids or []:
        k = ident(x)
        if k is not None:
            cand_by[k].add(str(x.value).strip().casefold())

    view = {}
    for x in cand.alt_ids or []:
        key = tuple(_ck(v) for v in (x.value, x.id_type, x.domain, x.relation))
        k = ident(x)
        v = str(x.value).strip().casefold()
        if k is None or k not in sub_by:
            st = "neutral"
        elif v in sub_by[k]:
            st = "identical"
        elif sub_by[k] & cand_by[k]:
            st = "neutral"          # the Kind matched through another value
        else:
            st = "mismatch"         # the comparator's conflict
        _keep(view, key, st)
    return view


def field_item_states(rationale, submitted, candidate, cand_view, state_bands,
                      creation_type: str | None = None) -> dict:
    """``{manifest key: [state, ...]}``: one state per list item, aligned
    index for index with the candidate's record-view lists.

    ``cand_view`` is the candidate's record view (BMR-Review's
    ``render_record``): each list is in display order and its entries are
    lists whose first element is the displayed text -- a credit's sort name
    and an organization's alternate names are their own entries -- except
    ``alt_ids``, whose entries begin ``[value, id_type, domain, relation]``.
    Keys read: titles, directors, actors, countries, languages,
    version_languages, assoc_orgs, alt_ids.

    Candidate side only. A field is emitted only when the engine COMPARED it
    (``rationale`` has its row) and its view list is non-empty, so a row with
    no field state has no item glyphs either; emit the result as
    ``scoring.field_item_states`` only when non-empty. An item state never
    changes q, the score, ``field_states`` or ``field_not_counted``, and may
    differ from the field state (one matching director makes the field
    identical; a second, unmatched director stays neutral).

    Needs the comparators' registered parameters (``NAME_MATCH_MIN`` and the
    title knobs), as the comparators do. Returns ``{}`` when either record or
    the view is missing.
    """
    if submitted is None or candidate is None or not cand_view:
        return {}
    bands = state_bands or {}
    rows = {r.get("field"): r for r in rationale or [] if r.get("field")}
    out: dict = {}
    for field, vkey in _VIEW_KEY.items():
        if field not in rows:
            continue
        items = cand_view.get(vkey) or []
        if not items:
            continue
        if field == "title":
            m = _item_titles(submitted, candidate, bands, rows[field].get("quality") is None)
        elif field in ("director", "actor"):
            attr = "directors" if field == "director" else "actors"
            m = _item_people(getattr(submitted, attr) or [], getattr(candidate, attr) or [],
                             field, bands)
        elif field == "assoc_org":
            m = _item_orgs(submitted, candidate, bands)
        elif field == "country":
            m = _item_codes(submitted.countries, candidate.countries, norm_country)
        elif field in ("original_language", "version_language"):
            attr = field + "s"
            m = _item_codes(getattr(submitted, attr), getattr(candidate, attr), norm_lang)
        else:
            m = _item_alt_ids(submitted, candidate)
        if field == "alt_id":
            states = [m.get(tuple(_ck(v) for v in it[:4]), "neutral") for it in items]
        else:
            states = [m.get(_ck(it[0]), "neutral") for it in items]
        out[ui_field_key(field, creation_type)] = states
    return out
