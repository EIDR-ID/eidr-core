"""build_registry_credentials: null/blank fields and a non-mapping section.

Both were silent or opaque (dictionary audit 2026-10-02; 0.68.0): a JSON
``null`` USER_ID went through ``str()`` and reached the registry as the
string ``'None'`` -- an authentication failure far from its cause -- and a
``"registry": "sandbox2"`` raised an AttributeError naming nothing.

The SDK is faked, as in test_registry_operation_status, so these run
without ``eidr`` installed (CI does not have it).
"""
from __future__ import annotations

import sys
import types

import pytest


class _FakeCredentials:
    def __init__(self, **kw):
        self.kw = kw

    @classmethod
    def load(cls):
        return cls(loaded=True)


@pytest.fixture
def build(monkeypatch):
    fake_eidr = types.ModuleType("eidr")
    fake_eidr.Credentials = _FakeCredentials  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "eidr", fake_eidr)
    from eidr_core.registry import build_registry_credentials
    return build_registry_credentials


GOOD = {"USER_ID": " 10.5238/u ", "PARTY_ID": "10.5237/p", "PASSWORD": "pw"}


def test_a_complete_section_is_stripped_and_passed_through(build):
    creds = build({"registry": dict(GOOD)})
    assert creds.kw == {"user_id": "10.5238/u", "party_id": "10.5237/p",
                        "password": "pw", "base_url": None}


def test_top_level_fields_are_accepted(build):
    assert build(dict(GOOD)).kw["user_id"] == "10.5238/u"


@pytest.mark.parametrize("bad", [None, "", "   "])
@pytest.mark.parametrize("field", ["USER_ID", "PARTY_ID", "PASSWORD"])
def test_null_or_blank_required_field_is_missing(build, field, bad):
    section = dict(GOOD, **{field: bad})
    with pytest.raises(KeyError, match=field):
        build({"registry": section})


def test_null_at_top_level_is_missing_too(build):
    with pytest.raises(KeyError, match="USER_ID"):
        build(dict(GOOD, USER_ID=None))


def test_an_absent_field_is_still_a_key_error(build):
    section = {k: v for k, v in GOOD.items() if k != "PASSWORD"}
    with pytest.raises(KeyError, match="PASSWORD"):
        build({"registry": section})


@pytest.mark.parametrize("key", ["registry", "eidr_registry"])
def test_a_non_mapping_section_is_a_type_error(build, key):
    with pytest.raises(TypeError, match="must be a mapping"):
        build({key: "sandbox2"})


def test_no_section_falls_back_to_the_sdk_auto_detect(build):
    assert build({"mirror_db": {}}).kw == {"loaded": True}
    assert build(None).kw == {"loaded": True}
