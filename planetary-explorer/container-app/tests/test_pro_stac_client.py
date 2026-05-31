"""Unit tests for pro_stac_client.

Covers the pure-Python surface that doesn't require live Azure:
  - is_pro_url host detection
  - _ensure_api_version idempotency + query-string preservation
  - get_pro_stac_base env-var resolution and /search stripping
  - _acquire_token caching (via monkeypatched credential)
  - pro_get / pro_post issue Authorization + api-version (via aiohttp mock)
"""

from __future__ import annotations

import asyncio
import sys
import types
from typing import Any, Dict
from unittest.mock import patch

import pytest

import pro_stac_client as psc


# ---------------------------------------------------------------------------
# is_pro_url
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://geocatalog.foo.northcentralus.geocatalog.spatio.azure.com/stac", True),
        ("https://geocatalog.foo.northcentralus.geocatalog.spatio.azure.com/stac/search", True),
        ("https://planetarycomputer.microsoft.com/api/stac/v1/search", False),
        ("https://openveda.cloud/api/stac/search", False),
        ("", False),
        ("not-a-url", False),
        (None, False),
    ],
)
def test_is_pro_url(url, expected):
    assert psc.is_pro_url(url) is expected


# ---------------------------------------------------------------------------
# _ensure_api_version
# ---------------------------------------------------------------------------

def test_ensure_api_version_appends_when_missing():
    out = psc._ensure_api_version("https://x.geocatalog.spatio.azure.com/stac/search")
    assert f"api-version={psc.PRO_API_VERSION}" in out


def test_ensure_api_version_preserves_existing():
    url = "https://x.geocatalog.spatio.azure.com/stac/search?api-version=2099-01-01"
    out = psc._ensure_api_version(url)
    assert out == url


def test_ensure_api_version_preserves_other_query_params():
    url = "https://x.geocatalog.spatio.azure.com/stac/collections/foo/items/bar?limit=10"
    out = psc._ensure_api_version(url)
    assert "limit=10" in out
    assert f"api-version={psc.PRO_API_VERSION}" in out


# ---------------------------------------------------------------------------
# get_pro_stac_base
# ---------------------------------------------------------------------------

def test_get_pro_stac_base_returns_none_when_unset(monkeypatch):
    for var in ("MPC_PRO_STAC_URL", "PC_DATA_API_URL", "STAC_API_URL"):
        monkeypatch.delenv(var, raising=False)
    assert psc.get_pro_stac_base() is None


def test_get_pro_stac_base_strips_trailing_search(monkeypatch):
    monkeypatch.setenv(
        "MPC_PRO_STAC_URL",
        "https://x.geocatalog.spatio.azure.com/stac/search/",
    )
    monkeypatch.delenv("PC_DATA_API_URL", raising=False)
    monkeypatch.delenv("STAC_API_URL", raising=False)
    assert psc.get_pro_stac_base() == "https://x.geocatalog.spatio.azure.com/stac"


def test_get_pro_stac_base_ignores_non_pro_urls(monkeypatch):
    monkeypatch.delenv("MPC_PRO_STAC_URL", raising=False)
    monkeypatch.delenv("PC_DATA_API_URL", raising=False)
    monkeypatch.setenv("STAC_API_URL", "https://planetarycomputer.microsoft.com/api/stac/v1")
    assert psc.get_pro_stac_base() is None


def test_get_pro_stac_base_prefers_mpc_pro_var(monkeypatch):
    monkeypatch.setenv("MPC_PRO_STAC_URL", "https://a.geocatalog.spatio.azure.com/stac")
    monkeypatch.setenv("PC_DATA_API_URL", "https://b.geocatalog.spatio.azure.com/stac")
    monkeypatch.delenv("STAC_API_URL", raising=False)
    assert psc.get_pro_stac_base() == "https://a.geocatalog.spatio.azure.com/stac"


# ---------------------------------------------------------------------------
# _acquire_token (caching via stub credential)
# ---------------------------------------------------------------------------

class _StubToken:
    def __init__(self, value: str, expires_on: float) -> None:
        self.token = value
        self.expires_on = expires_on


class _StubCredential:
    """Counts get_token calls so we can prove the cache short-circuits."""

    calls = 0

    async def get_token(self, scope: str):
        type(self).calls += 1
        return _StubToken("fake-token-xyz", expires_on=2**31 - 1)  # far-future

    async def close(self):
        pass


def _install_stub_azure_identity():
    """Inject a stub azure.identity.aio.DefaultAzureCredential into sys.modules."""
    aio_mod = types.ModuleType("azure.identity.aio")
    aio_mod.DefaultAzureCredential = _StubCredential  # type: ignore[attr-defined]
    identity_mod = types.ModuleType("azure.identity")
    azure_mod = types.ModuleType("azure")
    sys.modules.setdefault("azure", azure_mod)
    sys.modules["azure.identity"] = identity_mod
    sys.modules["azure.identity.aio"] = aio_mod


def test_acquire_token_caches(monkeypatch):
    _install_stub_azure_identity()
    _StubCredential.calls = 0
    psc._token_cache.clear()

    async def go():
        t1 = await psc._acquire_token()
        t2 = await psc._acquire_token()
        return t1, t2

    t1, t2 = asyncio.run(go())
    assert t1 == t2 == "fake-token-xyz"
    assert _StubCredential.calls == 1, "second call should hit cache"


# ---------------------------------------------------------------------------
# pro_get / pro_post wire Authorization + api-version
# ---------------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, body: Dict[str, Any], status: int = 200) -> None:
        self._body = body
        self.status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def json(self):
        return self._body


class _FakeSession:
    def __init__(self) -> None:
        self.get_calls: list[dict] = []
        self.post_calls: list[dict] = []

    def get(self, url, *, headers, timeout):
        self.get_calls.append({"url": url, "headers": headers})
        return _FakeResponse({"ok": True, "verb": "GET"})

    def post(self, url, *, headers, json, timeout):
        self.post_calls.append({"url": url, "headers": headers, "json": json})
        return _FakeResponse({"ok": True, "verb": "POST"})


def test_pro_get_attaches_bearer_and_api_version(monkeypatch):
    _install_stub_azure_identity()
    psc._token_cache.clear()

    session = _FakeSession()

    async def go():
        return await psc.pro_get(session, "https://x.geocatalog.spatio.azure.com/stac/collections")

    body = asyncio.run(go())
    assert body == {"ok": True, "verb": "GET"}
    assert len(session.get_calls) == 1
    call = session.get_calls[0]
    assert call["headers"]["Authorization"].startswith("Bearer ")
    assert f"api-version={psc.PRO_API_VERSION}" in call["url"]


def test_pro_post_attaches_bearer_api_version_and_json_body(monkeypatch):
    _install_stub_azure_identity()
    psc._token_cache.clear()

    session = _FakeSession()
    payload = {"collections": ["naip-test"], "bbox": [-123, 47, -122.9, 47.1]}

    async def go():
        return await psc.pro_post(
            session,
            "https://x.geocatalog.spatio.azure.com/stac/search",
            payload,
        )

    body = asyncio.run(go())
    assert body == {"ok": True, "verb": "POST"}
    call = session.post_calls[0]
    assert call["headers"]["Authorization"].startswith("Bearer ")
    assert call["headers"]["Content-Type"] == "application/json"
    assert call["json"] == payload
    assert f"api-version={psc.PRO_API_VERSION}" in call["url"]


# ---------------------------------------------------------------------------
# pro_list_collections / get_pro_collection_ids
# ---------------------------------------------------------------------------

class _ListSession:
    """Returns a STAC collections payload from any GET."""

    def __init__(self, payload):
        self._payload = payload

    def get(self, url, *, headers, timeout):
        return _FakeResponse(self._payload)


def test_pro_list_collections_returns_empty_when_unconfigured(monkeypatch):
    _install_stub_azure_identity()
    psc._token_cache.clear()
    for var in ("MPC_PRO_STAC_URL", "PC_DATA_API_URL", "STAC_API_URL"):
        monkeypatch.delenv(var, raising=False)

    async def go():
        # session is unused in the unconfigured branch
        return await psc.pro_list_collections(session=None)  # type: ignore[arg-type]

    assert asyncio.run(go()) == []


def test_pro_list_collections_parses_payload(monkeypatch):
    _install_stub_azure_identity()
    psc._token_cache.clear()
    monkeypatch.setenv("MPC_PRO_STAC_URL", "https://x.geocatalog.spatio.azure.com/stac")

    session = _ListSession(
        {
            "collections": [
                {"id": "naip-test", "title": "NAIP Test"},
                {"id": "sar-test", "title": "SAR Test"},
            ]
        }
    )

    async def go():
        return await psc.pro_list_collections(session)

    cols = asyncio.run(go())
    assert [c["id"] for c in cols] == ["naip-test", "sar-test"]


def test_get_pro_collection_ids_caches(monkeypatch):
    _install_stub_azure_identity()
    psc._token_cache.clear()
    # Reset module cache
    psc._collection_ids_cache = (0.0, [])
    monkeypatch.setenv("MPC_PRO_STAC_URL", "https://x.geocatalog.spatio.azure.com/stac")

    call_count = {"n": 0}

    class _CountingSession(_ListSession):
        def get(self, url, *, headers, timeout):
            call_count["n"] += 1
            return super().get(url, headers=headers, timeout=timeout)

    session = _CountingSession({"collections": [{"id": "naip-test"}]})

    # Patch aiohttp.ClientSession context manager used internally so
    # both calls share our counting session.
    import aiohttp as _aiohttp

    class _CtxSession:
        async def __aenter__(self_inner):
            return session

        async def __aexit__(self_inner, *_):
            return False

    monkeypatch.setattr(_aiohttp, "ClientSession", lambda *a, **kw: _CtxSession())

    async def go():
        a = await psc.get_pro_collection_ids()
        b = await psc.get_pro_collection_ids()
        return a, b

    a, b = asyncio.run(go())
    assert a == b == ["naip-test"]
    assert call_count["n"] == 1, "second call should hit cache"
