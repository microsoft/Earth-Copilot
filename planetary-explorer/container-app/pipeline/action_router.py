"""
Layer 1 — Action Router.

One LLM call per chat turn classifies the user's request into one of four
actions:

  * NAVIGATE          — fly the map to a location, no data load, no analysis
  * LOAD              — STAC search + render imagery, no analysis
  * ANALYZE           — use already-loaded data + map state to answer
  * LOAD_AND_ANALYZE  — load new imagery, then analyze it

This is intentionally narrower than the legacy 5-intent classifier. WHICH
analyzer to invoke is decided by the AnalysisRouter (Layer 2), not here.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from ._aoai import fast_deployment, get_aoai_client
from .contracts import ActionDecision
from .prompts import ACTION_ROUTER_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "action": {
            "type": "string",
            "enum": ["NAVIGATE", "LOAD", "ANALYZE", "LOAD_AND_ANALYZE"],
        },
        "location": {"type": ["string", "null"]},
        "use_current_location": {"type": "boolean"},
        "stac_query": {"type": ["string", "null"]},
        "analysis_question": {"type": ["string", "null"]},
        "reasoning": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
    },
    "required": [
        "action",
        "location",
        "use_current_location",
        "stac_query",
        "analysis_question",
        "reasoning",
        "confidence",
    ],
}


class ActionRouter:
    """Single-call structured-output classifier."""

    def __init__(self, deployment: str | None = None) -> None:
        self._deployment = deployment or fast_deployment()

    async def route(
        self,
        query: str,
        loaded_collections: list[str] | None = None,
        has_pin: bool = False,
        has_screenshot: bool = False,
    ) -> ActionDecision:
        ctx_lines = []
        if loaded_collections:
            ctx_lines.append(f"Currently loaded collections: {', '.join(loaded_collections)}")
        if has_pin:
            ctx_lines.append("A pin is dropped on the map.")
        if has_screenshot:
            ctx_lines.append("A screenshot of the map is available.")
        context_block = "\n".join(ctx_lines) or "(empty map state)"

        client = get_aoai_client()
        started = time.time()
        try:
            resp = await client.chat.completions.create(
                model=self._deployment,
                messages=[
                    {"role": "system", "content": ACTION_ROUTER_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"MAP STATE:\n{context_block}\n\nUSER QUERY:\n{query}",
                    },
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "ActionDecision",
                        "schema": _RESPONSE_SCHEMA,
                        "strict": True,
                    },
                },
                temperature=0.0,
            )
            payload = json.loads(resp.choices[0].message.content or "{}")
            decision = ActionDecision.model_validate(payload)
        except Exception as exc:  # noqa: BLE001 - fail-open to ANALYZE
            logger.warning("[ACTION_ROUTER] Falling back to ANALYZE on error: %s", exc)
            decision = ActionDecision(
                action="ANALYZE",
                analysis_question=query,
                reasoning=f"router_fallback:{type(exc).__name__}",
                confidence=0.0,
            )

        elapsed = int((time.time() - started) * 1000)
        logger.info(
            "[ACTION_ROUTER] %s confidence=%.2f elapsed_ms=%d",
            decision.action,
            decision.confidence,
            elapsed,
        )
        return decision
