"""The rule-6 exemption list is data, and a wrong entry is SILENT.

An extra Kind here means real conflicts are written to the registry as
second identity values; a missing one means whole rows withheld for nothing.
Neither raises. So the file is checked against its own stated criterion,
and the one measured fact that overturned v1.3 is pinned.
"""
import json
from importlib.resources import files

from eidr_core.altidtool_io import multi_form_domains


def _raw():
    return json.loads((files("eidr_core") / "specs" / "multi_form_kinds.json")
                      .read_text(encoding="utf-8"))


def test_every_listed_kind_meets_the_stated_criterion():
    # A 'measured' entry must meet the registry-practice criterion (at least
    # half the records carrying the Kind hold >1 identity value). A 'ruled'
    # entry cannot -- that is why it needed a ruling -- so it must instead
    # carry the ruling's words and date, or it is an unexplained exemption.
    for e in _raw()["domains"]:
        basis = e.get("basis", "measured")
        assert basis in {"measured", "ruled"}, e
        if basis == "measured":
            assert e["multi"] * 2 >= e["records"], e
        else:
            assert "Operator, 20" in e["ruling"] and '"' in e["ruling"], e


def test_mediafilm_is_ruled_two_form_and_its_film_kind_is_not():
    """Operator 2026-10-02: "We can't tell, so accept both for now." The two
    forms use disjoint number ranges (numeric 127..91228, mf-tt-1624656 and
    up), so a numeric value is not a rendering of an mf-tt one: rule 6 would
    withhold every second form (BMRtoAltID T6: 77 of 731 rows). The separate
    Kind mediafilm.ca/film holds only mf-tt values and stays single-form."""
    assert "mediafilm.ca" in multi_form_domains()
    assert "mediafilm.ca/film" not in multi_form_domains()
    entry = next(e for e in _raw()["domains"] if e["domain"] == "mediafilm.ca")
    assert entry["basis"] == "ruled"


def test_returns_lowercase_bare_domains():
    got = multi_form_domains()
    assert isinstance(got, frozenset) and got
    assert all(d == d.strip().lower() for d in got)
    assert {"pbs.org", "decellc.com"} <= got


def test_trakt_tv_is_single_form():
    """v1.3 named trakt.tv as THE multi-form example. Measured 2026-09-26 on
    the mirror: 20,931 numeric values, 2 records with more than one; the slug
    form is the separate Kind trakt.tv/movies. Re-adding it needs a new
    measurement, not the old example."""
    assert "trakt.tv" not in multi_form_domains()
    assert not any(d.startswith("trakt.tv") for d in multi_form_domains())


def test_named_types_are_never_in_the_set():
    assert not {"imdb", "isan", "eidr"} & multi_form_domains()
