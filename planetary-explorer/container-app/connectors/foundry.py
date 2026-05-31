"""Foundry connector — typed wrapper around Azure AI Foundry endpoints.

Foundry hosts the headline GA models (Aurora, Earth-2 family, MAI Weather
and friends). For the LLM-style endpoints, this re-uses
:class:`_framework.LlmClient` which already knows the AOAI-vs-Foundry
endpoint resolution rule. For the score endpoints (weather, vision,
custom), thin :func:`score` and :func:`health` helpers wrap an
authenticated POST against ``/score`` or a caller-supplied path.

Auth precedence:

1. ``FOUNDRY_API_KEY`` env var (Bearer token, deployment key)
2. ``DefaultAzureCredential`` token for ``https://ml.azure.com/.default``

The module is inert until ``FOUNDRY_ENDPOINT_URL`` (or a caller-supplied
URL) is set, so importing it never opens a network connection.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)


_DEFAULT_SCOPE = "https://ml.azure.com/.default"


def _resolve_endpoint(override: str | None) -> str | None:
    return override or os.getenv("FOUNDRY_ENDPOINT_URL") or None


async def _bearer() -> str | None:
    """Resolve a bearer token: env API key first, then managed identity."""
    key = os.getenv("FOUNDRY_API_KEY")
    if key:
        return key
    try:
        from azure.identity.aio import DefaultAzureCredential
    except Exception:  # noqa: BLE001
        return None
    try:
        cred = DefaultAzureCredential()
        try:
            tok = await cred.get_token(_DEFAULT_SCOPE)
            return tok.token
        finally:
            await cred.close()
    except Exception as exc:  # noqa: BLE001
        logger.debug("foundry: managed-identity token failed: %s", exc)
        return None


async def score(
    payload: dict[str, Any],
    *,
    endpoint_url: str | None = None,
    path: str = "/score",
    timeout: float = 60.0,
    extra_headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """POST ``payload`` to a Foundry online-endpoint scoring URL.

    Raises :class:`RuntimeError` if no endpoint is configured.
    """
    base = _resolve_endpoint(endpoint_url)
    if not base:
        raise RuntimeError(
            "FOUNDRY_ENDPOINT_URL is not set; pass endpoint_url=... or configure env"
        )
    headers = {"Content-Type": "application/json"}
    token = await _bearer()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if extra_headers:
        headers.update(extra_headers)
    url = base.rstrip("/") + path
    async with httpx.AsyncClient(timeout=timeout) as client:
        rsp = await client.post(url, json=payload, headers=headers)
        rsp.raise_for_status()
        return rsp.json()


async def health(
    *,
    endpoint_url: str | None = None,
    path: str = "/",
    timeout: float = 10.0,
) -> bool:
    """Cheap reachability probe."""
    base = _resolve_endpoint(endpoint_url)
    if not base:
        return False
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            rsp = await client.get(base.rstrip("/") + path)
            return rsp.status_code < 500
    except Exception:  # noqa: BLE001
        return False


def is_configured(endpoint_url: str | None = None) -> bool:
    return bool(_resolve_endpoint(endpoint_url))
