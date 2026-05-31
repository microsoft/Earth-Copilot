"""MCP server + tool registry.

A single :class:`McpRegistry` instance per process holds the configured
MCP servers and (lazily) the tool schemas they advertise. Today only
the MPC Pro sidecar is registered; this is the seam where future
servers (Foundry-hosted MCPs, internal tool servers, etc.) plug in.

The registry **does not perform tool calls** — that's the job of
:class:`TracedMcpClient` (see ``traced_client.py``). Keeping discovery
separate from invocation lets the UI list available tools without
having to wrap every server in a full traced client.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class McpServerSpec:
    """Connection + capability descriptor for one MCP server."""

    server_id: str                  # stable id used in UI traces
    display_name: str               # human-readable label
    url: str                        # streamable-HTTP base URL
    enabled: bool = True
    api_key_env: str | None = None  # env var holding the bearer token, if any
    tools: tuple[str, ...] = field(default_factory=tuple)  # filled in by discover

    @property
    def api_key(self) -> str | None:
        if not self.api_key_env:
            return None
        return os.getenv(self.api_key_env) or None


class McpRegistry:
    """Holds the set of configured MCP servers."""

    def __init__(self, servers: list[McpServerSpec]) -> None:
        self._servers = servers
        self._by_id = {s.server_id: s for s in servers}

    @classmethod
    def discover(cls) -> "McpRegistry":
        """Build a registry from env vars. Inert when nothing is configured."""
        servers: list[McpServerSpec] = []
        # MPC Pro sidecar — same env vars the legacy mcp_catalog_client uses.
        url = (os.getenv("MPC_MCP_URL") or "").strip()
        enabled = (os.getenv("USE_MPC_MCP") or "").lower() in ("1", "true", "yes")
        if url and enabled:
            servers.append(
                McpServerSpec(
                    server_id="mpc_pro",
                    display_name="MPC Pro",
                    url=url,
                    enabled=True,
                    api_key_env="MPC_MCP_API_KEY",
                )
            )
        logger.info(
            "mcp registry discovered %d server(s): %s",
            len(servers),
            [s.server_id for s in servers],
        )
        return cls(servers)

    @property
    def all(self) -> list[McpServerSpec]:
        return list(self._servers)

    def get(self, server_id: str) -> McpServerSpec | None:
        return self._by_id.get(server_id)

    def is_enabled(self) -> bool:
        return any(s.enabled for s in self._servers)

    def as_dict(self) -> dict[str, Any]:
        """Cheap serialisable snapshot for the /health endpoint and the
        future UI tool-trace drawer."""
        return {
            "enabled": self.is_enabled(),
            "servers": [
                {
                    "server_id": s.server_id,
                    "display_name": s.display_name,
                    "url": s.url,
                    "enabled": s.enabled,
                    "tool_count": len(s.tools),
                }
                for s in self._servers
            ],
        }


@lru_cache(maxsize=1)
def get_registry() -> McpRegistry:
    """Process-wide singleton."""
    return McpRegistry.discover()
