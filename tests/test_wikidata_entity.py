"""external.wikidata (C8 part 2, 0.64.0) and bmr_rows.cap_credits: the rules
whose breach yields a plausible wrong value -- a deprecated date or cast
member, a territory-specific date passed off as the release, a cut cast list
used for matching."""
from __future__ import annotations

from eidr_core import bmr_rows
from eidr_core.external import wikidata as WD


def item(q, rank="normal", refs=()):
    c = {"rank": rank, "mainsnak": {"snaktype": "value", "datavalue": {
        "type": "wikibase-entityid", "value": {"id": q}}}}
    if refs:
        c["references"] = [{"snaks": {p: [{"datavalue": {"value": {"id": v}}}] for p, v in refs}}]
    return c


def time_(t, prec=11, rank="normal", territory=False):
    c = {"rank": rank, "mainsnak": {"datavalue": {"type": "time",
                                                  "value": {"time": t, "precision": prec}}}}
    if territory:
        c["qualifiers"] = {"P291": [{"datavalue": {}}]}
    return c


def string(v, prop_type="external-id"):
    return {"rank": "normal", "mainsnak": {"datavalue": {"type": prop_type, "value": v}}}


def test_release_date_tiers_and_the_p580_exception():
    e = {"claims": {"P577": [time_("+1999-03-31T00:00:00Z", rank="deprecated"),
                             time_("+1999-05-01T00:00:00Z", territory=True),
                             time_("+1999-04-02T00:00:00Z")]}}
    assert WD.release_date(e) == WD.ReleaseDate("1999-04-02", False, "P577")
    only_terr = {"claims": {"P577": [time_("+1999-05-01T00:00:00Z", territory=True)]}}
    assert WD.release_date(only_terr) == WD.ReleaseDate("1999-05-01", True, "P577+P291")
    start = {"claims": {"P580": [time_("+2001-00-00T00:00:00Z", prec=9)]}}
    assert WD.release_date(start, "Movie") == WD.ReleaseDate("2001", True, "P580")
    assert WD.release_date(start, "Series").estimate is False      # the first broadcast
    made = {"claims": {"P571": [time_("+1990-01-01T00:00:00Z")]}}
    assert WD.release_date(made).estimate is True


def test_deprecated_is_dropped_and_preferred_comes_first():
    e = {"claims": {"P161": [item("Q1"), item("Q2", "deprecated"), item("Q3", "preferred")]}}
    assert WD.item_ids(e, "P161") == ["Q3", "Q1"]


def test_duration_units_and_title_fallback():
    def dur(amount, unit):
        return {"claims": {"P2047": [{"rank": "normal", "mainsnak": {"datavalue": {
            "type": "quantity", "value": {"amount": amount,
                                          "unit": f"http://www.wikidata.org/entity/{unit}"}}}}]}}
    assert WD.duration_minutes(dur("+90", "Q7727")) == 90
    assert WD.duration_minutes(dur("+5400", "Q11574")) == 90
    assert WD.duration_minutes(dur("+1.5", "Q25235")) == 90
    assert WD.title({"labels": {"en": {"value": "Metropolis"}}}) == ("Metropolis", "en")
    p1476 = {"claims": {"P1476": [{"rank": "normal", "mainsnak": {"datavalue": {
        "type": "monolingualtext", "value": {"text": "Metropolis", "language": "de"}}}}]}}
    assert WD.title(p1476) == ("Metropolis", "de")
    assert WD.title({}) == ("", "und")


def test_alternate_titles_fold_case_and_punctuation_against_the_title():
    e = {"aliases": {"en": [{"value": "metropolis!"}, {"value": "City of Tomorrow"}]},
         "labels": {"fr": {"value": "Métropolis"}, "de": {"value": "City of tomorrow"}}}
    assert WD.alternate_titles(e, "Metropolis") == [
        ("City of Tomorrow", "en"), ("Métropolis", "fr")]


def test_references_name_where_wikidata_got_a_value():
    c = item("Q5", refs=[("P248", "Q37312"), ("P143", "Q328")])
    assert WD.references(c) == [("P248", "Q37312"), ("P143", "Q328")]


def test_bmr_facts_keeps_the_full_cast_and_cap_credits_cuts_it_for_a_sheet():
    cast = [item(f"Q{100 + i}") for i in range(7)]
    e = {"labels": {"en": {"value": "Film"}},
         "claims": {"P161": cast, "P57": [item("Q1"), item("Q2"), item("Q3")],
                    "P364": [item("Q1860")], "P495": [item("Q15180")],
                    "P577": [time_("+1927-01-10T00:00:00Z")]}}
    related = {f"Q{100 + i}": {"labels": {"en": {"value": f"Actor {i}"}}} for i in range(7)}
    related.update({q: {"labels": {"en": {"value": f"Dir {q}"}}} for q in ("Q1", "Q2", "Q3")})
    related["Q1860"] = {"claims": {"P218": [string("en")]}}
    related["Q15180"] = {"claims": {"P297": [string("SU")]}}
    f = WD.bmr_facts(e, related)
    assert len(f["Actor"]) == 7 and len(f["Director"]) == 3        # matching: everything
    assert f["Original Language"] == ["en"] and f["Country of Origin"] == ["SUHH"]
    assert f["Release Date"] == "1927-01-10" and f["Registrant Extra"] == ""
    d, a = bmr_rows.cap_credits(f["Director"], f["Actor"])           # a BMR row: 2 and 4
    assert d == ["Dir Q1", "Dir Q2"] and a == ["Actor 0", "Actor 1", "Actor 2", "Actor 3"]


def test_language_of_work_is_the_fallback_unless_original_language_is_no_value():
    rel = {"Q150": {"claims": {"P218": [string("fr")]}}}
    e = {"claims": {"P407": [item("Q150")]}}
    assert WD.bmr_facts(e, rel)["Original Language"] == ["fr"]
    nov = {"claims": {"P364": [{"rank": "normal", "mainsnak": {"snaktype": "novalue"}}],
                      "P407": [item("Q150")]}}
    assert WD.bmr_facts(nov, rel)["Original Language"] == []
