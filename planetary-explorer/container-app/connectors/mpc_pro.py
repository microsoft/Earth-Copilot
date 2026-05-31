"""MPC Pro connector — re-export of the existing :mod:`mcp_catalog_client`.

This module exists so new code can import the canonical platform
connector via ``from connectors.mpc_pro import MpcMcpClient`` without
having to know that the underlying implementation lives in
``container-app/mcp_catalog_client.py``. Existing imports of
``mcp_catalog_client`` continue to work unchanged.
"""
from __future__ import annotations

from mcp_catalog_client import (  # noqa: F401  (re-export)
    MpcMcpClient,
    MpcMcpUnavailable,
    get_client,
    is_enabled,
)

__all__ = ["MpcMcpClient", "MpcMcpUnavailable", "get_client", "is_enabled"]
