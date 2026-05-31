"""Unit tests for the Planetary Explorer Resilience MCP server.

Mocks the backend with respx and calls the tool functions directly.
Auth middleware is exercised via the ASGI app with httpx ASGITransport.
"""
from __future__ import annotations

import os

import httpx
import pytest
import respx

# Configure env before importing the module-under-test.
os.environ.setdefault("RESILIENCE_API_BASE_URL", "http://backend.test")
os.environ.setdefault("RESILIENCE_TUNNEL_SKIP", "1")


@pytest.fixture
async def started_server():
    """Boot the lifespan so the shared httpx client is initialized."""
    import server as srv

    # Manually drive the lifespan
    cm = srv._lifespan(srv.mcp)
    await cm.__aenter__()
    try:
        yield srv
    finally:
        await cm.__aexit__(None, None, None)


# --------------------------------------------------------------------------- #
# Tool happy paths
# --------------------------------------------------------------------------- #


@respx.mock
async def test_check_resilience_health_returns_backend_body(started_server):
    respx.get("http://backend.test/api/resilience/health").mock(
        return_value=httpx.Response(200, json={"status": "ready", "enabled": True})
    )
    result = await started_server.check_resilience_health()
    assert result == {"status": "ready", "enabled": True}


@respx.mock
async def test_list_facilities_passes_region_param(started_server):
    route = respx.get("http://backend.test/api/resilience/facilities").mock(
        return_value=httpx.Response(200, json={"facilities": [], "source": "seed"})
    )
    result = await started_server.list_facilities(region="TX")
    assert result == {"facilities": [], "source": "seed"}
    assert route.calls.last.request.url.params["region"] == "TX"


@respx.mock
async def test_list_facilities_omits_region_when_none(started_server):
    route = respx.get("http://backend.test/api/resilience/facilities").mock(
        return_value=httpx.Response(200, json={"facilities": []})
    )
    await started_server.list_facilities()
    assert "region" not in route.calls.last.request.url.params


@respx.mock
async def test_assess_resilience_posts_body(started_server):
    route = respx.post("http://backend.test/api/resilience/assess").mock(
        return_value=httpx.Response(
            200,
            json={"assessment_id": "abc", "facilities": [], "summary": {}},
        )
    )
    result = await started_server.assess_resilience(
        region_filter="TX",
        horizon_days=5,
        hazards=["heat"],
        user_query="why TX?",
    )
    assert result["assessment_id"] == "abc"
    body = respx.calls.last.request.content
    assert b'"region_filter":"TX"' in body
    assert b'"horizon_days":5' in body
    assert b'"hazards":["heat"]' in body
    assert b'"user_query":"why TX?"' in body
    assert route.called


@respx.mock
async def test_assess_resilience_omits_optional_fields(started_server):
    respx.post("http://backend.test/api/resilience/assess").mock(
        return_value=httpx.Response(200, json={})
    )
    await started_server.assess_resilience()
    body = respx.calls.last.request.content
    assert b"region_filter" not in body
    assert b"hazards" not in body
    assert b"user_query" not in body
    assert b'"horizon_days":7' in body


@respx.mock
async def test_get_resilience_snapshot_returns_image(started_server):
    png_bytes = b"\x89PNG\r\n\x1a\nfake-png-data"
    respx.get("http://backend.test/api/resilience/snapshot").mock(
        return_value=httpx.Response(
            200, content=png_bytes, headers={"Content-Type": "image/png"}
        )
    )
    result = await started_server.get_resilience_snapshot(
        assessment_id="abc-123", width=512, height=384
    )
    # FastMCP Image holds raw bytes
    assert hasattr(result, "data") or hasattr(result, "_data")
    raw = getattr(result, "data", None) or getattr(result, "_data", None)
    assert raw == png_bytes


# --------------------------------------------------------------------------- #
# Error mapping
# --------------------------------------------------------------------------- #


@respx.mock
async def test_backend_5xx_returns_structured_error(started_server):
    respx.get("http://backend.test/api/resilience/health").mock(
        return_value=httpx.Response(503, json={"detail": "warming up"})
    )
    result = await started_server.check_resilience_health()
    assert result["error"] == "backend_error"
    assert result["status_code"] == 503
    assert result["backend_body"] == {"detail": "warming up"}
    assert "request_id" in result


@respx.mock
async def test_backend_connection_error_returns_unreachable(started_server):
    respx.get("http://backend.test/api/resilience/health").mock(
        side_effect=httpx.ConnectError("boom")
    )
    result = await started_server.check_resilience_health()
    assert result["error"] == "backend_unreachable"
    assert "boom" in result["detail"]


@respx.mock
async def test_snapshot_backend_404_returns_error_dict(started_server):
    respx.get("http://backend.test/api/resilience/snapshot").mock(
        return_value=httpx.Response(404, json={"detail": "assessment expired"})
    )
    result = await started_server.get_resilience_snapshot(assessment_id="missing")
    assert isinstance(result, dict)
    assert result["error"] == "backend_error"
    assert result["status_code"] == 404


# --------------------------------------------------------------------------- #
# Tunnel header injection
# --------------------------------------------------------------------------- #


@respx.mock
async def test_tunnel_skip_header_is_sent(started_server):
    respx.get("http://backend.test/api/resilience/health").mock(
        return_value=httpx.Response(200, json={})
    )
    await started_server.check_resilience_health()
    assert (
        respx.calls.last.request.headers.get("X-Tunnel-Skip-Anti-Phishing-Page")
        == "true"
    )


# --------------------------------------------------------------------------- #
# Bearer-token middleware
# --------------------------------------------------------------------------- #


async def _request_app(app, headers: dict[str, str] | None = None) -> httpx.Response:
    # Hit a non-MCP path so we test middleware in isolation without needing
    # the MCP transport's task group lifespan to be running.
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        return await client.get("/", headers=headers or {})


async def test_auth_middleware_no_token_means_open():
    import server as srv

    srv.BEARER_TOKEN = None
    app = srv.build_asgi_app()
    resp = await _request_app(app)
    # Without auth required, request reaches MCP transport which itself
    # responds (likely 405/406/400 because GET isn't a valid MCP request).
    # Crucially: NOT 401.
    assert resp.status_code != 401


async def test_auth_middleware_missing_header_is_401():
    import server as srv

    srv.BEARER_TOKEN = "secret-token"
    app = srv.build_asgi_app()
    resp = await _request_app(app)
    assert resp.status_code == 401
    assert resp.json()["error"] == "unauthorized"
    assert "Bearer" in resp.headers.get("WWW-Authenticate", "")


async def test_auth_middleware_wrong_token_is_401():
    import server as srv

    srv.BEARER_TOKEN = "secret-token"
    app = srv.build_asgi_app()
    resp = await _request_app(app, headers={"Authorization": "Bearer wrong"})
    assert resp.status_code == 401
    assert "invalid_token" in resp.headers.get("WWW-Authenticate", "")


async def test_auth_middleware_correct_token_passes_through():
    import server as srv

    srv.BEARER_TOKEN = "secret-token"
    app = srv.build_asgi_app()
    resp = await _request_app(
        app, headers={"Authorization": "Bearer secret-token"}
    )
    # Auth passed; whatever MCP transport responds with is fine, just not 401.
    assert resp.status_code != 401


async def test_healthz_bypasses_auth():
    import server as srv

    srv.BEARER_TOKEN = "secret-token"
    app = srv.build_asgi_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.text == "ok"
