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
    # criterion: at least half the records carrying the Kind hold >1 identity value
    for e in _raw()["domains"]:
        assert e["multi"] * 2 >= e["records"], e


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
