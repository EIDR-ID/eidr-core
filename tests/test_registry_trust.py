"""Trust policy lives in the factory (0.36.0): system trust by default, passed
through only when the installed SDK knows the parameter, never over a caller's
own TransportConfig."""
from __future__ import annotations

import inspect

import pytest

eidr = pytest.importorskip("eidr")  # the [client] extra; these tests are about the SDK seam


class _CapturingClient:
    last_kwargs: dict = {}

    def __init__(self, **kwargs):
        type(self).last_kwargs = kwargs


@pytest.fixture
def capture(monkeypatch):
    monkeypatch.setattr(eidr, "Client", _CapturingClient)
    _CapturingClient.last_kwargs = {}
    return _CapturingClient


def _sdk_has_trust() -> bool:
    from eidr.client import TransportConfig
    return "trust" in inspect.signature(TransportConfig).parameters


def test_default_is_system_trust_when_the_sdk_knows_the_parameter(capture):
    from eidr_core.registry import get_registry_client
    get_registry_client(registry="sandbox2", credentials=object())
    tc = capture.last_kwargs["transport_config"]
    if _sdk_has_trust():
        assert tc is not None and getattr(tc, "trust", None) == "system"
    else:
        assert tc is None, "1.2.0 has no trust parameter; the default must stay the SDK's"


def test_a_callers_transport_config_is_passed_through_untouched(capture):
    from eidr_core.registry import get_registry_client
    mine = object()
    get_registry_client(registry="sandbox2", credentials=object(), transport_config=mine)
    assert capture.last_kwargs["transport_config"] is mine


def test_trust_none_leaves_the_sdk_default(capture):
    from eidr_core.registry import get_registry_client
    get_registry_client(registry="sandbox2", credentials=object(), trust=None)
    assert capture.last_kwargs["transport_config"] is None


def test_feature_detection_against_an_sdk_without_trust(monkeypatch, capture):
    """A TransportConfig that does not declare trust= must not be called with it."""
    import eidr.client as client_mod

    class OldTransportConfig:
        def __init__(self, connect_timeout=5.0):
            self.connect_timeout = connect_timeout

    monkeypatch.setattr(client_mod, "TransportConfig", OldTransportConfig)
    from eidr_core.registry import get_registry_client
    get_registry_client(registry="sandbox2", credentials=object())
    assert capture.last_kwargs["transport_config"] is None


class _Cfg:
    """Stands in for a caller's TransportConfig: only the two attributes
    the factory reads, so the test does not depend on the installed SDK."""

    def __init__(self, trust="certifi", ca_bundle=None):
        self.trust = trust
        self.ca_bundle = ca_bundle


def _warnings(caplog):
    return [r for r in caplog.records
            if r.levelname == "WARNING" and "certifi" in r.getMessage()]


def test_a_callers_certifi_config_is_passed_through_but_warned(capture, caplog):
    """Built for timeouts, lost the trust default: never mutated, never silent."""
    from eidr_core.registry import get_registry_client
    mine = _Cfg()
    with caplog.at_level("WARNING", logger="eidr_core.registry"):
        get_registry_client(registry="sandbox2", credentials=object(),
                            transport_config=mine)
    assert capture.last_kwargs["transport_config"] is mine
    assert mine.trust == "certifi", "the caller's config must not be rewritten"
    assert len(_warnings(caplog)) == 1


@pytest.mark.parametrize("cfg, trust", [
    (_Cfg(trust="system"), "system"),          # the caller already has it
    (_Cfg(ca_bundle="corp-ca.pem"), "system"),  # a trust decision was made
    (_Cfg(), None),                             # deliberate: trust=None says so
])
def test_no_warning_when_the_trust_choice_is_visible(capture, caplog, cfg, trust):
    from eidr_core.registry import get_registry_client
    with caplog.at_level("WARNING", logger="eidr_core.registry"):
        get_registry_client(registry="sandbox2", credentials=object(),
                            transport_config=cfg, trust=trust)
    assert capture.last_kwargs["transport_config"] is cfg
    assert _warnings(caplog) == []
