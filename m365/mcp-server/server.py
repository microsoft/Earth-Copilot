"""MCP server exposing the Planetary Explorer Resilience agent.

Wraps the four `/api/resilience/*` endpoints of the Planetary Explorer
backend so any MCP-aware client (Copilot Studio, Claude Desktop, VS Code,
Cursor) can call them as tools.

Transport: Streamable HTTP (MCP 2025-03-26 spec) on port 8765 by default.

Env vars:
    RESILIENCE_API_BASE_URL  Backend base URL. Default: http://localhost:8080
    RESILIENCE_API_KEY       Optional Bearer token sent to the backend.
    RESILIENCE_TUNNEL_SKIP   If "1", adds the devtunnel anti-phishing header.
    MCP_HOST / MCP_PORT      Bind host/port. Defaults: 0.0.0.0 / 8765.
    MCP_BEARER_TOKEN         If set, clients MUST send Authorization:
                             Bearer <token> on every /mcp request. If unset,
                             the server logs a warning and runs open (dev).

Run:
    pip install -e .
    python server.py
"""
from __future__ import annotations

import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP, Image
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #

API_BASE = os.getenv("RESILIENCE_API_BASE_URL", "http://localhost:8080").rstrip("/")
API_KEY = os.getenv("RESILIENCE_API_KEY")
TUNNEL_SKIP = os.getenv("RESILIENCE_TUNNEL_SKIP", "0") == "1"
HOST = os.getenv("MCP_HOST", "0.0.0.0")
PORT = int(os.getenv("MCP_PORT", "8765"))
BEARER_TOKEN = os.getenv("MCP_BEARER_TOKEN")

# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #

logging.basicConfig(
    level=os.getenv("MCP_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("planetary-explorer-resilience-mcp")

# --------------------------------------------------------------------------- #
# Shared HTTP client (created/closed via FastMCP lifespan)
# --------------------------------------------------------------------------- #

_client: httpx.AsyncClient | None = None


def _backend_headers() -> dict[str, str]:
    h: dict[str, str] = {"Content-Type": "application/json"}
    if API_KEY:
        h["Authorization"] = f"Bearer {API_KEY}"
    if TUNNEL_SKIP:
        h["X-Tunnel-Skip-Anti-Phishing-Page"] = "true"
    return h


@asynccontextmanager
async def _lifespan(_server: FastMCP):
    """Manage a single httpx.AsyncClient for the server's lifetime."""
    global _client
    _client = httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=15.0))
    log.info(
        "MCP server up. backend=%s tunnel_skip=%s auth=%s",
        API_BASE,
        TUNNEL_SKIP,
        "bearer" if BEARER_TOKEN else "OPEN-NO-AUTH",
    )
    if not BEARER_TOKEN:
        log.warning(
            "MCP_BEARER_TOKEN is not set. Server is running without "
            "authentication. Set it before exposing the server publicly."
        )
    try:
        yield {}
    finally:
        await _client.aclose()
        _client = None
        log.info("MCP server shutting down.")


# --------------------------------------------------------------------------- #
# FastMCP instance
# --------------------------------------------------------------------------- #

mcp = FastMCP(
    name="planetary-explorer-resilience",
    instructions=(
        "Tools for the Planetary Explorer Resilience agent. Use these to "
        "assess operational risk for facilities over a 1-14 day forecast "
        "horizon, list the facility registry, fetch a static risk map "
        "snapshot, or check backend health. All numbers are grounded in "
        "live weather and the user's Fabric Lakehouse facility/supply-graph "
        "tables. Never invent facilities, scores, or coordinates."
    ),
    host=HOST,
    port=PORT,
    lifespan=_lifespan,
)


# --------------------------------------------------------------------------- #
# Internal helpers with structured error handling
# --------------------------------------------------------------------------- #


def _error(code: str, detail: str, **extra: Any) -> dict[str, Any]:
    """Build a structured error payload the agent can reason over."""
    return {"error": code, "detail": detail, **extra}


async def _call(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Make a backend call. Returns structured error dicts instead of raising."""
    if _client is None:
        return _error("server_not_ready", "HTTP client not initialized.")

    request_id = uuid.uuid4().hex[:8]
    started = time.perf_counter()
    url = f"{API_BASE}{path}"
    try:
        r = await _client.request(
            method,
            url,
            headers=_backend_headers(),
            params=params,
            json=json_body,
        )
    except httpx.TimeoutException as exc:
        log.warning("[%s] %s %s timed out: %s", request_id, method, path, exc)
        return _error(
            "backend_timeout",
            f"Backend did not respond within timeout: {exc}",
            request_id=request_id,
        )
    except httpx.HTTPError as exc:
        log.warning("[%s] %s %s transport error: %s", request_id, method, path, exc)
        return _error(
            "backend_unreachable",
            f"Could not reach backend: {exc}",
            request_id=request_id,
        )

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    if r.status_code >= 400:
        log.warning(
            "[%s] %s %s -> %d in %dms",
            request_id,
            method,
            path,
            r.status_code,
            elapsed_ms,
        )
        body: Any
        try:
            body = r.json()
        except ValueError:
            body = r.text[:500]
        return _error(
            "backend_error",
            f"Backend returned HTTP {r.status_code}",
            status_code=r.status_code,
            backend_body=body,
            request_id=request_id,
        )

    log.info("[%s] %s %s -> %d in %dms", request_id, method, path, r.status_code, elapsed_ms)
    try:
        return r.json()
    except ValueError:
        return _error(
            "backend_invalid_json",
            "Backend returned non-JSON body.",
            request_id=request_id,
            preview=r.text[:200],
        )


async def _get_bytes(
    path: str, params: dict[str, Any] | None = None
) -> tuple[bytes, str] | dict[str, Any]:
    """Fetch binary content (e.g. PNG). Returns (bytes, content_type) or error dict."""
    if _client is None:
        return _error("server_not_ready", "HTTP client not initialized.")
    request_id = uuid.uuid4().hex[:8]
    url = f"{API_BASE}{path}"
    try:
        r = await _client.get(url, headers=_backend_headers(), params=params)
    except httpx.HTTPError as exc:
        log.warning("[%s] GET %s failed: %s", request_id, path, exc)
        return _error("backend_unreachable", str(exc), request_id=request_id)

    if r.status_code >= 400:
        log.warning("[%s] GET %s -> %d", request_id, path, r.status_code)
        try:
            backend_body: Any = r.json()
        except ValueError:
            backend_body = r.text[:500]
        return _error(
            "backend_error",
            f"Backend returned HTTP {r.status_code}",
            status_code=r.status_code,
            backend_body=backend_body,
            request_id=request_id,
        )
    return r.content, r.headers.get("Content-Type", "application/octet-stream")


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #


@mcp.tool()
async def check_resilience_health() -> dict[str, Any]:
    """Check whether the Resilience backend is online and ready.

    Returns a small JSON object with status, agent framework availability,
    and whether the resilience feature flag is enabled. Call this first if
    other tools start returning errors.
    """
    return await _call("GET", "/api/resilience/health")


@mcp.tool()
async def list_facilities(region: str | None = None) -> dict[str, Any]:
    """List the facility registry the agent operates over.

    Args:
        region: Optional two-letter state code (e.g. "TX") to filter the
            registry. Omit to return every facility.

    Returns:
        A JSON object with the facility list (id, name, lat, lng, type,
        criticality, headcount, etc.), the supply-edge graph, and the
        underlying data source ("fabric" or "seed").
    """
    params = {"region": region} if region else None
    return await _call("GET", "/api/resilience/facilities", params=params)


@mcp.tool()
async def assess_resilience(
    region_filter: str | None = None,
    horizon_days: int = 7,
    hazards: list[str] | None = None,
    user_query: str | None = None,
) -> dict[str, Any]:
    """Assess operational resilience risk for facilities over a forecast horizon.

    This is the headline tool. Pulls the facility registry, fetches live
    Open-Meteo forecasts for each site, scores heat and wildfire smoke
    risk, joins to the supply-edge graph for blast-radius analysis, and
    retrieves the most relevant BCP playbook excerpts via AI Search. Every
    score is grounded - no values are invented.

    Args:
        region_filter: Optional two-letter state code (e.g. "TX"). Omit to
            assess every visible facility.
        horizon_days: Forecast horizon, 1-14 days. Defaults to 7. Values
            above 14 are clamped server-side.
        hazards: Hazards to score. Currently supported: "heat", "wildfire".
            Omit for all supported hazards.
        user_query: Optional free-text question to log alongside the run
            for provenance / audit trail.

    Returns:
        A dossier with: input echo, per-facility risk records (overall_risk
        0-100, severity low|moderate|high|severe, primary_hazard, hazard
        breakdown, upstream_at_risk, downstream, playbook citations), a
        summary block, a data_provenance array, and an assessment_id you
        can pass to get_resilience_snapshot.
    """
    body: dict[str, Any] = {"horizon_days": horizon_days}
    if region_filter:
        body["region_filter"] = region_filter
    if hazards:
        body["hazards"] = hazards
    if user_query:
        body["user_query"] = user_query
    return await _call("POST", "/api/resilience/assess", json_body=body)


@mcp.tool()
async def get_resilience_snapshot(
    assessment_id: str,
    width: int = 1024,
    height: int = 768,
) -> Any:
    """Get a static PNG map snapshot for a prior assessment.

    Pins each facility on an Azure Maps base layer, colored by severity
    (red=severe, orange=high, yellow=moderate, green=low). Use this after
    calling assess_resilience to render a visual companion to the dossier.

    Args:
        assessment_id: The UUID returned by a prior assess_resilience call.
            Cached for 15 minutes server-side.
        width: PNG width in pixels (256-2048). Defaults to 1024.
        height: PNG height in pixels (256-2048). Defaults to 768.

    Returns:
        An MCP image content block (PNG). If the backend returns an error
        (no Azure Maps key, expired assessment_id, etc.), returns a
        structured error dict instead.
    """
    result = await _get_bytes(
        "/api/resilience/snapshot",
        params={"assessment_id": assessment_id, "width": width, "height": height},
    )
    if isinstance(result, dict):
        return result  # error envelope
    data, content_type = result
    fmt = "png" if "png" in content_type.lower() else "jpeg"
    return Image(data=data, format=fmt)


# --------------------------------------------------------------------------- #
# Bearer-token middleware on the streamable HTTP transport
# --------------------------------------------------------------------------- #


class BearerAuthMiddleware(BaseHTTPMiddleware):
    """Enforce Authorization: Bearer <MCP_BEARER_TOKEN> on every request.

    If MCP_BEARER_TOKEN is unset, the middleware is a no-op (dev mode); the
    startup logs already warn about this.
    """

    def __init__(self, app, expected_token: str | None) -> None:
        super().__init__(app)
        self._expected = expected_token

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        if self._expected is None:
            return await call_next(request)

        if request.url.path == "/healthz":
            return Response("ok", status_code=200, media_type="text/plain")

        # Accept the token under any of the common header names that MCP
        # clients use. Copilot Studio's "API key" mode does not let the
        # author pick a header name, so we have to be liberal.
        candidate_headers = (
            "Authorization",
            "X-API-Key",
            "Api-Key",
            "X-Api-Key",
            "Ocp-Apim-Subscription-Key",
        )
        provided: str | None = None
        for h in candidate_headers:
            v = request.headers.get(h)
            if v:
                provided = v.strip()
                break

        if provided is None:
            return JSONResponse(
                {"error": "unauthorized", "detail": "Missing API key."},
                status_code=401,
                headers={"WWW-Authenticate": 'Bearer realm="mcp"'},
            )

        # Strip optional "Bearer " prefix so the same token works whether the
        # client sends "Bearer <token>" or just "<token>".
        if provided.lower().startswith("bearer "):
            provided = provided[7:].strip()

        if provided != self._expected:
            return JSONResponse(
                {"error": "unauthorized", "detail": "Invalid API key."},
                status_code=401,
                headers={
                    "WWW-Authenticate": 'Bearer realm="mcp", error="invalid_token"'
                },
            )
        return await call_next(request)


def build_asgi_app():
    """Return the Starlette ASGI app with auth middleware installed.

    Exposed so tests can hit it directly.
    """
    app = mcp.streamable_http_app()
    app.add_middleware(BearerAuthMiddleware, expected_token=BEARER_TOKEN)
    return app


# --------------------------------------------------------------------------- #
# Entrypoint
# --------------------------------------------------------------------------- #


def main() -> None:
    import uvicorn

    uvicorn.run(
        build_asgi_app(),
        host=HOST,
        port=PORT,
        log_level=os.getenv("MCP_LOG_LEVEL", "info").lower(),
    )


if __name__ == "__main__":
    main()
