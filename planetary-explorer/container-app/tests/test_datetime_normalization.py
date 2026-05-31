"""Unit tests for the STAC datetime normalization helper.

The helper converts the date-only shorthand the semantic translator emits
(``YYYY-MM-DD`` / ``YYYY-MM-DD/YYYY-MM-DD``) into strict RFC3339 before
the query is sent to any STAC endpoint. Public PC tolerates the
shorthand; GeoCatalog (pgstac strict) returns HTTP 400. Normalizing once
at the single STAC boundary keeps both endpoints working.
"""

from __future__ import annotations

import importlib

import pytest


def _load(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://stub")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "stub")
    try:
        fastapi_app = importlib.import_module("fastapi_app")
    except Exception as exc:  # pragma: no cover - env-dependent
        pytest.skip(f"fastapi_app import failed in test env: {exc}")
    return fastapi_app._normalize_stac_datetime


@pytest.mark.parametrize(
    "raw, expected",
    [
        # Date-only range -> RFC3339 start + end-of-day.
        ("2026-05-20/2026-05-21", "2026-05-20T00:00:00Z/2026-05-21T23:59:59Z"),
        # Single date -> RFC3339 start-of-day.
        ("2026-05-20", "2026-05-20T00:00:00Z"),
        # Already RFC3339 -> unchanged.
        ("2026-05-20T00:00:00Z/2026-05-21T23:59:59Z",
         "2026-05-20T00:00:00Z/2026-05-21T23:59:59Z"),
        # Open upper bound preserved.
        ("2023-01-01/..", "2023-01-01T00:00:00Z/.."),
        # Open lower bound preserved.
        ("../2026-05-21", "../2026-05-21T23:59:59Z"),
        # Mixed (one date-only, one RFC3339).
        ("2026-05-20/2026-05-21T12:00:00Z",
         "2026-05-20T00:00:00Z/2026-05-21T12:00:00Z"),
    ],
)
def test_normalize_stac_datetime_known_shapes(monkeypatch, raw, expected):
    normalize = _load(monkeypatch)
    assert normalize(raw) == expected


@pytest.mark.parametrize("raw", [None, ""])
def test_normalize_stac_datetime_empty_passthrough(monkeypatch, raw):
    normalize = _load(monkeypatch)
    assert normalize(raw) == raw


def test_normalize_stac_datetime_year_only_passthrough(monkeypatch):
    """Year-only ('2026') and month-only ('2026-05') aren't STAC-spec
    range shorthands; pass them through unchanged so the server can
    decide. Most clients don't emit these."""
    normalize = _load(monkeypatch)
    assert normalize("2026") == "2026"
    assert normalize("2026-05") == "2026-05"
