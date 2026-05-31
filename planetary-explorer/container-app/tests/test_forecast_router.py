"""Tests for the Forecast Agent router (explicit / llm / fallback_all)."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

# Allow ``from agents.forecast.router ...`` style imports under pytest.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from connectors.weather.provider import Capability  # noqa: E402

from agents.forecast.messages import ForecastAgentQuery  # noqa: E402
from agents.forecast.router import RoutingDecision, route  # noqa: E402


# ── Fake providers ────────────────────────────────────────────────────
class _FakeProvider:
    def __init__(self, pid: str, vendor: str, caps: tuple[Capability, ...]) -> None:
        self.provider_id = pid
        self.vendor = vendor
        self.capabilities = caps


def _providers() -> list[_FakeProvider]:
    return [
        _FakeProvider("aurora-1.x", "Microsoft", (Capability.GLOBAL, Capability.CYCLONE_TRACKS)),
        _FakeProvider("earth2-fcn", "NVIDIA", (Capability.GLOBAL, Capability.MEDIUM_RANGE_10D)),
        _FakeProvider("mai-weather-1.x", "Microsoft", (Capability.GLOBAL, Capability.MEDIUM_RANGE_10D)),
    ]


# ── Mode 1: explicit allow-list wins ──────────────────────────────────
@pytest.mark.asyncio
async def test_explicit_requested_providers_skips_llm(monkeypatch):
    # If the LLM client ever gets constructed, this raises and fails the test.
    monkeypatch.setattr(
        "agents.forecast.router._try_llm_client",
        lambda: pytest.fail("LLM must not be called in explicit mode"),
    )
    q = ForecastAgentQuery(
        lat=0.0, lon=0.0,
        requested_providers=("aurora-1.x",),
        user_query="Use whatever — explicit list should win",
    )
    decision = await route(q, _providers())
    assert decision.mode == "explicit"
    assert decision.provider_ids == ("aurora-1.x",)
    assert "explicitly requested" in decision.reason.lower()


@pytest.mark.asyncio
async def test_explicit_unknown_provider_is_reported(monkeypatch):
    monkeypatch.setattr("agents.forecast.router._try_llm_client", lambda: None)
    q = ForecastAgentQuery(
        lat=0.0, lon=0.0,
        requested_providers=("not-a-real-model",),
    )
    decision = await route(q, _providers())
    assert decision.mode == "explicit"
    assert decision.provider_ids == ()
    assert "not configured" in decision.reason.lower()


# ── Mode 3: fallback_all when no LLM ──────────────────────────────────
@pytest.mark.asyncio
async def test_fallback_when_no_llm_returns_all_global(monkeypatch):
    monkeypatch.setattr("agents.forecast.router._try_llm_client", lambda: None)
    q = ForecastAgentQuery(lat=0.0, lon=0.0, user_query="What's the weather?")
    decision = await route(q, _providers())
    assert decision.mode == "fallback_all"
    assert set(decision.provider_ids) == {
        "aurora-1.x", "earth2-fcn", "mai-weather-1.x",
    }


@pytest.mark.asyncio
async def test_fallback_when_no_user_query(monkeypatch):
    # Even with an LLM configured, no query text means no routing brain to invoke.
    monkeypatch.setattr(
        "agents.forecast.router._try_llm_client",
        lambda: pytest.fail("LLM must not be called without user_query"),
    )
    q = ForecastAgentQuery(lat=0.0, lon=0.0, user_query=None)
    decision = await route(q, _providers())
    assert decision.mode == "fallback_all"


# ── Mode 2: LLM routing ───────────────────────────────────────────────
class _FakeLlm:
    """Mimics LlmClient with a scripted chat() response."""

    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.calls: list[dict] = []

    async def chat(self, **kwargs):  # noqa: D401
        self.calls.append(kwargs)
        msg = SimpleNamespace(content=json.dumps(self._payload))
        choice = SimpleNamespace(message=msg)
        return SimpleNamespace(choices=[choice])

    async def aclose(self):
        pass


@pytest.mark.asyncio
async def test_llm_routes_cyclone_query_to_cyclone_tracks(monkeypatch):
    fake = _FakeLlm({
        "required_capabilities": ["CYCLONE_TRACKS"],
        "provider_ids": [],
        "reason": "Hurricane track request — only Aurora has CYCLONE_TRACKS.",
    })
    monkeypatch.setattr("agents.forecast.router._try_llm_client", lambda: fake)

    q = ForecastAgentQuery(
        lat=25.0, lon=-80.0,
        user_query="Forecast hurricane tracks for the next 96 hours.",
    )
    decision = await route(q, _providers())

    assert decision.mode == "llm"
    assert decision.provider_ids == ("aurora-1.x",)
    assert Capability.CYCLONE_TRACKS in decision.required_capabilities
    assert "hurricane" in decision.reason.lower() or "cyclone" in decision.reason.lower()
    assert len(fake.calls) == 1


@pytest.mark.asyncio
async def test_llm_explicit_provider_subset_is_honored(monkeypatch):
    fake = _FakeLlm({
        "required_capabilities": ["GLOBAL"],
        "provider_ids": ["mai-weather-1.x"],
        "reason": "User asked for MAI Weather specifically.",
    })
    monkeypatch.setattr("agents.forecast.router._try_llm_client", lambda: fake)

    q = ForecastAgentQuery(lat=0, lon=0, user_query="Use MAI Weather only.")
    decision = await route(q, _providers())
    assert decision.mode == "llm"
    assert decision.provider_ids == ("mai-weather-1.x",)


@pytest.mark.asyncio
async def test_llm_unsatisfiable_capability_falls_back_to_global(monkeypatch):
    fake = _FakeLlm({
        "required_capabilities": ["KM_SCALE"],   # nobody has KM_SCALE in this fixture
        "reason": "Asked for km-scale downscaling.",
    })
    monkeypatch.setattr("agents.forecast.router._try_llm_client", lambda: fake)

    q = ForecastAgentQuery(lat=0, lon=0, user_query="Give me km-scale convective downscale.")
    decision = await route(q, _providers())
    assert decision.mode == "llm"
    # Degraded to GLOBAL because no provider satisfies KM_SCALE.
    assert decision.required_capabilities == (Capability.GLOBAL,)
    assert len(decision.provider_ids) == 3


@pytest.mark.asyncio
async def test_llm_returns_non_json_falls_back(monkeypatch):
    class _BadLlm(_FakeLlm):
        async def chat(self, **kwargs):
            msg = SimpleNamespace(content="not json at all")
            return SimpleNamespace(choices=[SimpleNamespace(message=msg)])

    monkeypatch.setattr(
        "agents.forecast.router._try_llm_client", lambda: _BadLlm({})
    )
    q = ForecastAgentQuery(lat=0, lon=0, user_query="forecast")
    decision = await route(q, _providers())
    # JSON parse failure inside _llm_route → eligible defaults to all GLOBAL,
    # capabilities default to (GLOBAL,). Still mode="llm" since the LLM was called.
    assert decision.mode == "llm"
    assert decision.required_capabilities == (Capability.GLOBAL,)
    assert len(decision.provider_ids) == 3


# ── Empty registry ────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_empty_provider_list():
    q = ForecastAgentQuery(lat=0, lon=0)
    decision = await route(q, [])
    assert decision.provider_ids == ()
    assert decision.mode == "fallback_all"


# ── RoutingDecision serialization ─────────────────────────────────────
def test_routing_decision_as_dict_shape():
    d = RoutingDecision(
        provider_ids=("aurora-1.x",),
        required_capabilities=(Capability.CYCLONE_TRACKS,),
        reason="hurricane",
        mode="llm",
        llm_raw={"x": 1},
    )
    out = d.as_dict()
    assert out["mode"] == "llm"
    assert out["provider_ids"] == ["aurora-1.x"]
    assert out["required_capabilities"] == ["CYCLONE_TRACKS"]
    assert out["llm_raw"] == {"x": 1}
