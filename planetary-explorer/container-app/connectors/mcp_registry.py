"""MCP registry connector — re-export of :mod:`mcp_runtime`.

Lets new agents import the registry + traced client through the
``connectors`` namespace alongside :mod:`connectors.mpc_pro`,
:mod:`connectors.fabric`, etc.
"""
from __future__ import annotations

from mcp_runtime import (  # noqa: F401  (re-export)
    McpRegistry,
    McpServerSpec,
    PermissionTier,
    TraceEntry,
    TracedMcpClient,
    classify_tool,
    get_registry,
)

__all__ = [
    "McpRegistry",
    "McpServerSpec",
    "PermissionTier",
    "TraceEntry",
    "TracedMcpClient",
    "classify_tool",
    "get_registry",
]
