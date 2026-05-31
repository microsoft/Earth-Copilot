"""Tests for the M365_APP_CLIENT_ID audience extension in auth_middleware.

The M365 declarative agent uses a separate Entra app registration. We
need to accept tokens whose ``aud`` matches that registration's client
id (or ``api://<client-id>``), but only when the env var is set —
otherwise prod gets a silently widened audience list.
"""

from __future__ import annotations

import importlib
import os

import pytest


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    # Strip any leaked test state
    monkeypatch.delenv("M365_APP_CLIENT_ID", raising=False)
    # The middleware reads env at import time, so each test re-imports.
    yield


def _reload_middleware():
    import auth_middleware

    return importlib.reload(auth_middleware)


def test_m365_audience_absent_by_default():
    mod = _reload_middleware()
    # Sanity: original audiences still there
    assert mod.CLIENT_ID in mod.VALID_AUDIENCES
    # No m365-app entries should leak in
    assert not any(a.startswith("00000000-m365") for a in mod.VALID_AUDIENCES)


def test_m365_audience_added_when_env_set(monkeypatch):
    monkeypatch.setenv("M365_APP_CLIENT_ID", "11111111-2222-3333-4444-555555555555")
    mod = _reload_middleware()
    assert "11111111-2222-3333-4444-555555555555" in mod.VALID_AUDIENCES
    assert "api://11111111-2222-3333-4444-555555555555" in mod.VALID_AUDIENCES


def test_original_audiences_preserved_when_m365_set(monkeypatch):
    monkeypatch.setenv("M365_APP_CLIENT_ID", "11111111-2222-3333-4444-555555555555")
    mod = _reload_middleware()
    # The five non-m365 base audiences are still present
    assert mod.CLIENT_ID in mod.VALID_AUDIENCES
    assert f"api://{mod.CLIENT_ID}" in mod.VALID_AUDIENCES
    assert mod.FABRIC_API_CLIENT_ID in mod.VALID_AUDIENCES
    assert mod.GRAPH_APP_ID in mod.VALID_AUDIENCES
