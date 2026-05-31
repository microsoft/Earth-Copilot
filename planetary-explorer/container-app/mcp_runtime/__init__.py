"""MCP integration — registry + traced client.

The registry holds a list of MCP servers (e.g. MPC Pro sidecar) and
their advertised tools. The :class:`TracedMcpClient` wraps every tool
invocation in a per-turn trace record so the UI (future tool-trace
drawer) can show "what did the agent actually call?".

Today only the MPC Pro sidecar is registered, and tracing is in-memory
and opt-in — calling code that already uses
``mcp_catalog_client.MpcMcpClient`` directly is **unaffected**.
"""

from .confirm_bus import (
    DEFAULT_CONFIRM_TIMEOUT_SECONDS,
    pending_count,
    request_confirmation,
    reset_for_tests as reset_confirm_bus_for_tests,
    resolve_confirmation,
)
from .public_stac_adapter import PublicStacAdapter
from .registry import McpRegistry, McpServerSpec, get_registry
from .trace_bus import emit as emit_trace
from .trace_bus import reset_listener, set_listener
from .traced_client import (
    PermissionTier,
    TraceEntry,
    TracedMcpClient,
    classify_tool,
)

__all__ = [
    "DEFAULT_CONFIRM_TIMEOUT_SECONDS",
    "McpRegistry",
    "McpServerSpec",
    "PermissionTier",
    "PublicStacAdapter",
    "TraceEntry",
    "TracedMcpClient",
    "classify_tool",
    "emit_trace",
    "get_registry",
    "pending_count",
    "request_confirmation",
    "reset_confirm_bus_for_tests",
    "reset_listener",
    "resolve_confirmation",
    "set_listener",
]
