"""Full-record construction — the specification, and the defects it closes.

Every implementation that existed before this module was wrong in some way
(see the module docstring), so these tests are written against the SCHEMA
and the operator's rules, not against either prior implementation. Where a
test pins a defect, it names it.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from eidr_core.inheritance import (
    INHERITABLE_FIELDS,
    NEVER_INHERITED,
    TitleConstructionError,
    build_full_base,
    build_full_record,
    has_user_supplied_title,
    is_absent,
    provenance,
    system_generated_title,
)

# --- the field policy -------------------------------------------------------

def test_administrators_is_never_inheritable():
    """XML_to_JSON's defect 1, pinned.

    The schema comments the exclusion on the field itself: "Administrators
    isn't inherited because it contains the registrant". A child that
    inherits it asserts it was registered by whoever registered its parent
    — and BMR-Review's match-audit reads Registrant to decide which member
    to notify about a mis-assigned ID.
    """
    assert "Administrators" in NEVER_INHERITED
    assert "Administrators" not in INHERITABLE_FIELDS


@pytest.mark.parametrize("f", ["ID", "AlternateID", "Description",
                               "RegistrantExtra", "AlternateResourceName"])
def test_the_rest_of_the_never_inherited_set(f):
    assert f in NEVER_INHERITED and f not in INHERITABLE_FIELDS


@pytest.mark.parametrize("f", [
    "StructuralType", "Mode", "ReferentType", "ResourceName",
    "OriginalLanguage", "VersionLanguage",
    "AssociatedOrg", "ReleaseDate", "CountryOfOrigin", "Status",
    "ApproximateLength", "Credits",
])
def test_the_inheritable_set_is_complete(f):
    # Asserted in full rather than spot-checked: XML_to_JSON carried only 6
    # of these, and the ones it lacked were the defect.
    assert f in INHERITABLE_FIELDS


def test_the_inheritable_set_has_exactly_twelve_fields():
    # A count, so ADDING one is as loud as removing one. It was 13 until
    # 2026-08-30, when the operator corrected AlternateResourceName out.
    assert len(INHERITABLE_FIELDS) == 12


def test_only_the_primary_title_inherits():
    """Operator, 2026-08-30, correcting the schema summary this was seeded from.

    A child does not acquire its parent's ALTERNATE titles -- only the
    primary one.
    """
    assert "ResourceName" in INHERITABLE_FIELDS
    assert "AlternateResourceName" not in INHERITABLE_FIELDS
    full, _ = build_full_base(
        {}, {"ResourceName": [{"Title": "P"}],
             "AlternateResourceName": [{"Title": "P Alt"}]}, "Edit")
    assert "AlternateResourceName" not in full


def test_the_two_sets_do_not_overlap():
    assert not (INHERITABLE_FIELDS & NEVER_INHERITED)


# --- system-generated titles ------------------------------------------------

@pytest.mark.parametrize("ctype,kw,expected,klass", [
    ("Season", {"sequence_number": "6"}, "30 Something: Season 6", "series numeric"),
    ("Season", {"release_date": "2006"}, "30 Something [2006]", "series numeric"),
    ("Episode", {"distribution_number": "1"}, "30 Something: Episode 1", "season numeric"),
    ("Episode", {"release_date": "2023-04-07"}, "30 Something [2023-04-07]", "season numeric"),
])
def test_all_four_registry_patterns(ctype, kw, expected, klass):
    assert system_generated_title("30 Something", ctype, **kw) == (expected, klass)


def test_the_number_wins_over_the_date():
    # The date form is the FALLBACK, not an alternative.
    assert system_generated_title(
        "S", "Season", sequence_number="2", release_date="1999",
    ) == ("S: Season 2", "series numeric")


def test_the_date_fallback_is_the_defect_that_left_children_untitled():
    """XML_to_JSON's defect 2, pinned.

    Its `_construct_child_title` implemented only the numbered rows and
    returned None otherwise, so a Season with no Sequence Number got NO
    title. An untitled child drops the field the de-dup engine weights most
    heavily (70 Basic / 40 Episode), so a genuine duplicate loses its
    strongest signal.
    """
    assert system_generated_title("S", "Season", release_date="2006") is not None
    assert system_generated_title("S", "Episode", release_date="2006") is not None


def test_no_number_and_no_date_yields_nothing():
    assert system_generated_title("S", "Season") is None
    assert system_generated_title("", "Season", sequence_number="1") is None


def test_types_that_get_no_constructed_title():
    for ctype in ("Edit", "Clip", "Manifestation", "Basic", "Series"):
        assert system_generated_title("S", ctype, sequence_number="1") is None


# --- shape 1: registry JSON -------------------------------------------------

PARENT = {
    "ResourceName": [{"Title": "The Series", "TitleClass": "resource name"}],
    "Mode": "AudioVisual",
    "ReferentType": "Series",
    "CountryOfOrigin": ["US"],
    "ReleaseDate": "2001",
    "Administrators": {"Registrant": "10.5237/PARENT-PARTY"},
    "AlternateID": [{"AltID": "tt0000001"}],
    "Description": "parent description",
}


def test_json_child_inherits_the_allowed_fields():
    full, prov = build_full_base({"StructuralType": "Abstraction"}, PARENT, "Edit")
    assert full["Mode"] == "AudioVisual"
    assert full["CountryOfOrigin"] == ["US"]
    assert prov["Mode"] == "inherited"
    assert prov["StructuralType"] == "self"


def test_json_child_does_not_inherit_administrators_altid_or_description():
    full, _ = build_full_base({}, PARENT, "Edit")
    for forbidden in ("Administrators", "AlternateID", "Description"):
        assert forbidden not in full, f"{forbidden} must not be inherited"


def test_json_self_defined_values_are_never_overwritten():
    full, prov = build_full_base({"Mode": "Audio"}, PARENT, "Edit")
    assert full["Mode"] == "Audio"
    assert prov["Mode"] == "self"


def test_json_edit_inherits_the_parent_title_verbatim():
    full, prov = build_full_base({}, PARENT, "Edit")
    assert full["ResourceName"][0]["Title"] == "The Series"
    assert prov["ResourceName"] == "inherited"


def test_json_season_gets_a_constructed_title_not_the_parents():
    full, prov = build_full_base({}, PARENT, "Season",
                                 extra={"SequenceNumber": "6"})
    assert full["ResourceName"] == [{
        "Title": "The Series: Season 6",
        "TitleClass": "series numeric",
        "SystemGenerated": "true",
    }]
    assert prov["ResourceName"] == "system"


def test_json_season_without_a_number_falls_back_to_the_date():
    full, _ = build_full_base({}, PARENT, "Season",
                              extra={"ReleaseDate": "2006"})
    assert full["ResourceName"][0]["Title"] == "The Series [2006]"


def test_a_child_with_no_number_and_no_date_of_its_own_raises_not_borrows():
    """The date fallback may NOT be reached through an INHERITED date.

    Operator ruling 2026-08-30: titles are generated BEFORE inheritance, from
    data guaranteed present in the child. This test asserted the opposite
    until that ruling, and the old behaviour was wrong on its own terms --
    the date pattern exists to tell SIBLINGS apart, so sourcing the date from
    the shared parent makes every sibling collide on one string: a false
    de-dup signal produced by the module meant to make children comparable.

    PARENT carries ReleaseDate 2001; this child gives neither number nor date.
    """
    with pytest.raises(TitleConstructionError) as caught:
        build_full_base({}, PARENT, "Season")
    exc = caught.value

    # RULE 2 fails loudly rather than leaving a child untitled -- but the
    # partial is COMPLETE. Inheritance still ran before the raise, so a caller
    # that proceeds need not re-derive it through a second path, and
    # ResourceName fell back to the parent's real title rather than staying
    # empty. XML_to_JSON's fallback handler depends on exactly this.
    assert exc.partial["ResourceName"] == PARENT["ResourceName"]
    assert exc.provenance["ResourceName"] == "inherited"
    assert exc.partial["ReleaseDate"] == PARENT["ReleaseDate"]
    assert exc.partial["Mode"] == PARENT["Mode"]


def test_both_shapes_agree_that_an_inherited_date_cannot_title_a_child():
    """The ordering must hold in BOTH adapters.

    This is the probe the previous cycle lacked. Both adapters generated
    AFTER inheriting, so they agreed with each other: every cross-shape
    determinism test passed while both were wrong, which is how the defect
    survived to be reported by a consumer instead of caught here. Reverting
    either adapter alone now reddens this.
    """
    with pytest.raises(TitleConstructionError):
        build_full_base({}, PARENT, "Season")
    with pytest.raises(TitleConstructionError):
        build_full_record(_Rec(creation_type="Season"), _parent_rec(),
                          creation_type="Season")


def test_a_childs_own_date_still_titles_it():
    """The date pattern is untouched when the date is the child's OWN."""
    full, _ = build_full_base({"ReleaseDate": "2006"}, PARENT, "Season")
    assert full["ResourceName"][0]["Title"] == "The Series [2006]"

    rec = build_full_record(_Rec(creation_type="Season", release_date="2006"),
                            _parent_rec(), creation_type="Season")
    assert rec.titles[0].text == "The Series [2006]"


def test_a_generated_title_blocks_inheriting_the_parents_title():
    """Ordering consequence: the generated title is data, so it blocks.

    Season 2 keeps "The Series: Season 2" -- the field loop, reaching
    ResourceName afterwards, must not overwrite it with the parent's title.
    """
    full, prov = build_full_base({}, PARENT, "Season",
                                 extra={"SequenceNumber": "2"})
    assert full["ResourceName"][0]["Title"] == "The Series: Season 2"
    assert prov["ResourceName"] == "system"


def test_siblings_with_numbers_do_not_collide():
    """The point of the ruling, stated as a test."""
    made = {
        n: build_full_base(
            {}, PARENT, "Season", extra={"SequenceNumber": n},
        )[0]["ResourceName"][0]["Title"]
        for n in ("1", "2", "3")
    }
    assert len(set(made.values())) == 3


def test_an_explicit_extra_date_outranks_an_inherited_one():
    """Precedence, pinned after trying it the other way round.

    XML_to_JSON flagged that the two adapters resolve this in opposite
    orders and offered consistency as optional. Aligning to record-first
    was tried and is wrong: by the time the title is built, the record's
    ReleaseDate may itself have been INHERITED from the parent, so
    record-first lets an inherited value outrank an argument the caller
    passed specifically to build this title. PARENT carries 2001; the
    caller says 2006; the caller wins.
    """
    full, _ = build_full_base({}, PARENT, "Season",
                              extra={"ReleaseDate": "2006"})
    assert full["ResourceName"][0]["Title"] == "The Series [2006]"


def test_json_no_parent_returns_self_unchanged():
    self_base = {"Mode": "Audio"}
    full, prov = build_full_base(self_base, None, "Season")
    assert full == self_base
    assert prov == {"Mode": "self"}


def test_json_build_does_not_mutate_its_inputs():
    self_base = {"Mode": "Audio"}
    parent = dict(PARENT)
    build_full_base(self_base, parent, "Edit")
    assert self_base == {"Mode": "Audio"}
    assert parent == PARENT


def test_json_inherited_containers_are_copied_not_aliased():
    full, _ = build_full_base({}, PARENT, "Edit")
    full["CountryOfOrigin"].append("FR")
    assert PARENT["CountryOfOrigin"] == ["US"], "parent was mutated through an alias"


def test_json_zero_is_not_treated_as_absent():
    # A real ApproximateLength of 0 must not be overwritten by the parent's.
    full, prov = build_full_base({"ApproximateLength": 0},
                                 {"ApproximateLength": 120}, "Edit")
    assert full["ApproximateLength"] == 0
    assert prov["ApproximateLength"] == "self"


# --- shape 2: record objects ------------------------------------------------

@dataclass
class _Title:
    text: str
    lang: str | None = None
    title_class: str | None = None
    system_generated: bool = False
    self_defined: bool = True
    is_resource: bool = False


@dataclass
class _Rec:
    creation_type: str = "Basic"
    structural_type: str | None = None
    mode: str | None = None
    referent_type: str | None = None
    release_date: str | None = None
    length_minutes: float | None = None
    sequence_number: str | None = None
    distribution_number: str | None = None
    titles: list = field(default_factory=list)
    countries: list = field(default_factory=list)
    original_languages: list = field(default_factory=list)
    version_languages: list = field(default_factory=list)
    assoc_orgs: list = field(default_factory=list)
    directors: list = field(default_factory=list)
    actors: list = field(default_factory=list)
    alt_ids: list = field(default_factory=list)


def _parent_rec():
    return _Rec(creation_type="Series", mode="AudioVisual",
                referent_type="Series", release_date="2001",
                length_minutes=45.0, countries=["US"],
                directors=[_Title(text="A Director")],
                titles=[_Title(text="The Series", is_resource=True)])


def test_record_inherits_scalars_the_old_paths_disagreed_about():
    """BMR-Review had TWO paths that disagreed: reconstruct_full inherited
    mode/referent_type but not release_date; inherit.materialize the
    reverse. One record scored differently depending on which built it.
    All three are inherited here."""
    full = build_full_record(_Rec(creation_type="Edit"), _parent_rec(), "Edit")
    assert full.mode == "AudioVisual"
    assert full.referent_type == "Series"
    assert full.release_date == "2001"
    prov = provenance(full)
    assert prov["Mode"] == prov["ReferentType"] == prov["ReleaseDate"] == "inherited"


def test_record_provenance_covers_scalars_the_model_cannot_flag():
    # The whole point of the map: CanonicalRecord has no self_defined flag on
    # release_date or length_minutes.
    prov = provenance(build_full_record(_Rec(creation_type="Edit"),
                                        _parent_rec(), "Edit"))
    assert prov["ReleaseDate"] == "inherited"
    assert prov["ApproximateLength"] == "inherited"


def test_record_self_defined_wins_and_is_reported_as_self():
    child = _Rec(creation_type="Edit", mode="Audio")
    prov = provenance(build_full_record(child, _parent_rec(), "Edit"))
    assert prov["Mode"] == "self"


def test_record_inherited_elements_are_marked_not_self_defined():
    full = build_full_record(_Rec(creation_type="Edit"), _parent_rec(), "Edit")
    assert full.directors[0].self_defined is False


def test_record_season_gets_a_constructed_system_generated_title():
    child = _Rec(creation_type="Season", sequence_number="6")
    full = build_full_record(child, _parent_rec(), "Season")
    assert [t.text for t in full.titles] == ["The Series: Season 6"]
    assert full.titles[0].system_generated is True
    assert full.titles[0].self_defined is False
    assert provenance(full)["ResourceName"] == "system"


def test_record_episode_falls_back_to_the_date():
    child = _Rec(creation_type="Episode", release_date="2023-04-07")
    full = build_full_record(child, _parent_rec(), "Episode")
    assert full.titles[0].text == "The Series [2023-04-07]"


def test_record_a_child_that_supplied_its_own_title_keeps_it():
    child = _Rec(creation_type="Season", sequence_number="6",
                 titles=[_Title(text="Given Title", is_resource=True)])
    full = build_full_record(child, _parent_rec(), "Season")
    assert full.titles[0].text == "Given Title"
    assert provenance(full)["ResourceName"] == "self"


def test_record_edit_inherits_the_parent_title():
    full = build_full_record(_Rec(creation_type="Edit"), _parent_rec(), "Edit")
    assert full.titles[0].text == "The Series"
    assert full.titles[0].self_defined is False
    assert provenance(full)["ResourceName"] == "inherited"


def test_record_build_does_not_mutate_the_input():
    child = _Rec(creation_type="Edit")
    build_full_record(child, _parent_rec(), "Edit")
    assert child.mode is None and child.titles == []


def test_record_no_parent_is_safe():
    full = build_full_record(_Rec(creation_type="Season"), None, "Season")
    assert full.mode is None
    assert provenance(full) == {}


def test_provenance_of_a_record_we_did_not_build_is_empty_not_wrong():
    # Absence must read as "unknown", never as "self-defined".
    assert provenance(_Rec()) == {}


def test_creation_type_defaults_to_the_records_own():
    child = _Rec(creation_type="Season", sequence_number="2")
    full = build_full_record(child, _parent_rec())     # no explicit ctype
    assert full.titles[0].text == "The Series: Season 2"


# ---------------------------------------------------------------------------
# The one rule, applied to the thirteenth field too (raised by XML_to_JSON,
# operator ruling 2026-08-30).
#
# "If the self-defined record does not provide a title, then it is
# system-generated ... If a record has a user-supplied title, then it must
# never be replaced with a system-generated title. (Just as user-supplied data
# must never be replaced with inherited data.)"
#
# The JSON adapter honoured that for twelve fields and broke it on the
# thirteenth: `build_full_base` overwrote a submitted ResourceName
# unconditionally, while `build_full_record` guarded it. Two adapters in ONE
# file disagreeing is the exact failure the module docstring cites as its
# reason to exist. It went unnoticed because only the object shape had a test
# -- so both shapes are pinned here now.
# ---------------------------------------------------------------------------

def test_json_a_child_that_supplied_its_own_title_keeps_it():
    full, prov = build_full_base(
        {"ResourceName": [{"Title": "My Hand-Written Season Title"}]},
        PARENT, "Season", extra={"SequenceNumber": "6"})
    assert full["ResourceName"][0]["Title"] == "My Hand-Written Season Title"
    assert prov["ResourceName"] == "self"


def test_json_an_empty_title_list_still_counts_as_absent():
    # The emptiness rule, not truthiness: [] means "not provided".
    full, prov = build_full_base({"ResourceName": []}, PARENT, "Season",
                                 extra={"SequenceNumber": "6"})
    assert full["ResourceName"][0]["Title"] == "The Series: Season 6"
    assert prov["ResourceName"] == "system"


def test_both_adapters_agree_on_a_supplied_title():
    """The divergence itself, asserted across shapes.

    Neither adapter's own test can catch this -- only comparing them can.
    """
    json_full, json_prov = build_full_base(
        {"ResourceName": [{"Title": "Mine"}]}, PARENT, "Season",
        extra={"SequenceNumber": "6"})
    rec = _Rec(creation_type="Season", sequence_number="6",
               titles=[_Title(text="Mine", is_resource=True)])
    rec_full = build_full_record(rec, _parent_rec(), "Season")

    assert json_full["ResourceName"][0]["Title"] == rec_full.titles[0].text == "Mine"
    assert json_prov["ResourceName"] == provenance(rec_full)["ResourceName"] == "self"


def test_both_adapters_agree_on_generating_when_none_supplied():
    json_full, json_prov = build_full_base({}, PARENT, "Season",
                                           extra={"SequenceNumber": "6"})
    rec_full = build_full_record(_Rec(creation_type="Season",
                                      sequence_number="6"),
                                 _parent_rec(), "Season")
    assert json_full["ResourceName"][0]["Title"] == rec_full.titles[0].text
    assert json_prov["ResourceName"] == provenance(rec_full)["ResourceName"] == "system"


# --- is_absent is public policy, not a helper ------------------------------

@pytest.mark.parametrize("value", [None, "", "   ", [], {}, ()])
def test_absent_values(value):
    assert is_absent(value) is True


@pytest.mark.parametrize("value", [0, False, 0.0, "x", [0], {"a": 1}])
def test_present_values_including_falsy_ones(value):
    # The reason this is exported: a plain truthiness test breaks the rule in
    # BOTH directions on 0 -- replacing a self-defined 0, and refusing to
    # inherit a legitimate one. XML_to_JSON had to copy the logic because it
    # was private.
    assert is_absent(value) is False


# ---------------------------------------------------------------------------
# Rule 2 is a GUARANTEE, so violating it is an error, not a quiet no-op.
#
# "The parent record will always have a title and the current record will
# always have the data necessary to generate a title" (operator, 2026-08-30).
# Returning None there would leave the child untitled, which drops the
# heaviest-weighted comparison field -- the exact silent failure XML_to_JSON
# shipped. Both adapters raise the SAME exception so they cannot differ even
# when the data is bad.
# ---------------------------------------------------------------------------

def test_json_untitleable_season_raises_rather_than_silently_untitled():
    with pytest.raises(TitleConstructionError, match="no user-supplied"):
        build_full_base({}, {"Mode": "AudioVisual"}, "Season")   # parent has no title


def test_record_untitleable_season_raises_the_same_way():
    parent = _Rec(creation_type="Series")                        # no titles
    with pytest.raises(TitleConstructionError):
        build_full_record(_Rec(creation_type="Season"), parent, "Season")


def test_both_adapters_raise_on_the_same_bad_input():
    """Determinism extends to the error path."""
    with pytest.raises(TitleConstructionError):
        build_full_base({}, {"Mode": "A"}, "Episode")
    with pytest.raises(TitleConstructionError):
        build_full_record(_Rec(creation_type="Episode"),
                          _Rec(creation_type="Season"), "Episode")


def test_a_supplied_title_means_no_construction_and_no_raise():
    # The guarantee only applies when a title must be GENERATED.
    full, prov = build_full_base({"ResourceName": [{"Title": "Mine"}]},
                                 {"Mode": "A"}, "Season")
    assert full["ResourceName"][0]["Title"] == "Mine"
    assert prov["ResourceName"] == "self"


def test_non_child_types_never_raise():
    # Edit/Clip/Manifestation inherit rather than generate; a parent with no
    # title simply means no title to inherit.
    full, _ = build_full_base({}, {"Mode": "A"}, "Edit")
    assert "ResourceName" not in full


# ---------------------------------------------------------------------------
# What BLOCKS is a USER-SUPPLIED value (operator, 2026-08-30): "only Resource
# Name can be inherited (if it is not provided or system-generated)".
#
# A system-generated title is not the submitter's, so it must not block --
# otherwise a stale derived string outlives a corrected parent title.
# ---------------------------------------------------------------------------

_GEN = [{"Title": "Old Generated", "SystemGenerated": "true"}]
_REAL = [{"Title": "Real Title"}]


def test_json_a_system_generated_title_does_not_block_inheritance():
    full, prov = build_full_base({"ResourceName": _GEN}, PARENT, "Edit")
    assert full["ResourceName"][0]["Title"] == "The Series"
    assert prov["ResourceName"] == "inherited"


def test_json_a_system_generated_title_is_regenerated_for_a_season():
    full, prov = build_full_base({"ResourceName": _GEN}, PARENT, "Season",
                                 extra={"SequenceNumber": "6"})
    assert full["ResourceName"][0]["Title"] == "The Series: Season 6"
    assert prov["ResourceName"] == "system"


def test_json_a_user_supplied_title_still_blocks_both():
    for ctype, extra in (("Edit", {}), ("Season", {"SequenceNumber": "6"})):
        full, prov = build_full_base({"ResourceName": _REAL}, PARENT, ctype,
                                     extra=extra)
        assert full["ResourceName"][0]["Title"] == "Real Title"
        assert prov["ResourceName"] == "self"


def test_record_a_system_generated_title_does_not_block():
    child = _Rec(creation_type="Edit",
                 titles=[_Title(text="Old Generated", is_resource=True,
                                system_generated=True)])
    full = build_full_record(child, _parent_rec(), "Edit")
    assert full.titles[0].text == "The Series"
    assert provenance(full)["ResourceName"] == "inherited"


def test_both_adapters_agree_on_the_system_generated_case():
    json_full, json_prov = build_full_base({"ResourceName": _GEN}, PARENT, "Edit")
    rec_full = build_full_record(
        _Rec(creation_type="Edit",
             titles=[_Title(text="Old Generated", is_resource=True,
                            system_generated=True)]),
        _parent_rec(), "Edit")
    assert json_full["ResourceName"][0]["Title"] == rec_full.titles[0].text
    assert json_prov["ResourceName"] == provenance(rec_full)["ResourceName"]


@pytest.mark.parametrize("titles,expected", [
    (None, False), ([], False),
    ([{"Title": "x"}], True),
    ([{"Title": "x", "SystemGenerated": "true"}], False),
    ([{"Title": "x", "SystemGenerated": "false"}], True),
    ([{"Title": "g", "SystemGenerated": "true"}, {"Title": "r"}], True),
])
def test_has_user_supplied_title(titles, expected):
    assert has_user_supplied_title(titles) is expected


# ---------------------------------------------------------------------------
# 2026-08-30 audit findings, pinned.
# ---------------------------------------------------------------------------

def test_compilation_is_not_a_child_and_a_supplied_parent_is_ignored():
    """Operator, 2026-08-30, correcting the previous version of this test.

    An earlier audit used Compilation as an example of an "unanticipated
    child type" and asserted it INHERITS. Wrong premise: Compilation sits at
    the registration tree root -- it has entries, but no Parent ID -- so it
    is not a child record at all. The child records are exactly CHILD_TYPES.
    Rule 1 is enforced in the module: a parent supplied for a non-child type
    is IGNORED, identically in both shapes, so a caller mistake cannot
    produce inheritance the registry would never perform.
    """
    json_full, json_prov = build_full_base(
        {"Mode": "Audio"},
        {"ResourceName": [{"Title": "The Parent"}], "Mode": "AudioVisual"},
        "Compilation")
    assert json_full == {"Mode": "Audio"}
    assert "inherited" not in json_prov.values()

    rec_full = build_full_record(_Rec(creation_type="Compilation", mode="Audio"),
                                 _parent_rec(), "Compilation")
    assert rec_full.mode == "Audio"
    assert rec_full.titles == []
    assert "inherited" not in provenance(rec_full).values()


def test_child_types_is_the_closed_world():
    from eidr_core.inheritance import CHILD_TYPES, TITLE_INHERITING_TYPES
    assert {"Season", "Episode", "Edit", "Clip", "Manifestation"} == CHILD_TYPES
    assert "Compilation" not in CHILD_TYPES
    # The three verbatim-inheriting types are exactly the non-exempt children.
    assert CHILD_TYPES - {"Season", "Episode"} == TITLE_INHERITING_TYPES


def test_title_failure_carries_the_partial_result_in_both_shapes():
    """A caller that proceeds past TitleConstructionError must not re-derive
    inheritance through a second code path -- that second path is the exact
    hazard this module removes. So the exception hands over the work done:
    every inheritable field applied, no title."""
    with pytest.raises(TitleConstructionError) as ei:
        build_full_base({}, {"Mode": "AudioVisual"}, "Season")
    assert ei.value.partial["Mode"] == "AudioVisual"
    assert "ResourceName" not in ei.value.partial
    assert ei.value.provenance["Mode"] == "inherited"

    with pytest.raises(TitleConstructionError) as ei2:
        build_full_record(_Rec(creation_type="Season"),
                          _Rec(creation_type="Series", mode="AudioVisual"),
                          "Season")
    assert ei2.value.partial.mode == "AudioVisual"
    assert ei2.value.partial.titles == []
    assert provenance(ei2.value.partial)["Mode"] == "inherited"


def test_a_kept_system_generated_title_is_not_stamped_self_defined():
    """Contradictory flags, pinned.

    On the no-parent path a system-generated input title survives -- and the
    blanket "submitter supplied it" stamp used to mark it self_defined=True
    while system_generated stayed True. Both flags are read downstream
    (BMR-Review's inherited-discount rule), so they must not contradict.
    """
    child = _Rec(creation_type="Season",
                 titles=[_Title(text="Old Gen", is_resource=True,
                                system_generated=True)])
    full = build_full_record(child, None, "Season")
    assert full.titles[0].system_generated is True
    assert full.titles[0].self_defined is False
