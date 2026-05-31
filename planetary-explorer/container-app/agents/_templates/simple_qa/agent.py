"""SimpleQaAgent — minimal one-turn Q&A using the framework.

Demonstrates the canonical patterns:

* :class:`_framework.LlmClient` for chat
* :class:`_framework.OBOContextMixin` for OBO-bound downstream calls
* :class:`mcp_runtime.TracedMcpClient` for traced MCP tool use
"""
from __future__ import annotations

import logging
from typing import Any

from _framework import LlmClient, OBOContextMixin
from mcp_runtime import TracedMcpClient

logger = logging.getLogger(__name__)


class SimpleQaAgent(OBOContextMixin):
    """One-shot Q&A. Replace the system prompt + tool surface for your use case."""

    SYSTEM_PROMPT = (
        "You are a helpful assistant inside Planetary Explorer. "
        "Answer concisely. If you don't know, say so."
    )

    def __init__(self, llm: LlmClient | None = None, mcp: TracedMcpClient | None = None) -> None:
        self.llm = llm or LlmClient.from_env()
        # Agents default to the **public** MPC STAC catalogue for
        # geospatial reasoning — no auth, no sidecar required. MPC Pro
        # is reserved for direct chat queries (Pro toggle on) and for
        # private/personal collection access in the data catalogue.
        self.mcp = mcp or TracedMcpClient.from_mpc_public()

    async def answer(self, question: str, *, turn_id: str | None = None) -> dict[str, Any]:
        if turn_id and self.mcp is not None:
            self.mcp.turn_id = turn_id
        completion = await self.llm.chat(
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": question},
            ],
        )
        text = completion.choices[0].message.content or ""
        return {
            "answer": text,
            "trace": [e.to_dict() for e in (self.mcp.buffer if self.mcp else [])],
        }
