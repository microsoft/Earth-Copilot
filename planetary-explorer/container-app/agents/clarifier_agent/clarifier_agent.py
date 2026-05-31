"""
Clarifier Agent — single-step LLM agent that returns a ClarifierDecision.

Pattern mirrors PostgresSQL-GraphRAG's QueryRouteDetector:
  1. A prompt template (in `prompts/clarifier_prompt.py`)
  2. A Pydantic structured-output schema (`ClarifierDecision`)
  3. One LLM call via Azure OpenAI

The work itself is wrapped in an `agent_framework.Executor` so this agent
can later be composed into a larger WorkflowBuilder graph alongside the
RouterAgent. For now it's invoked directly through `ClarifierAgent.decide()`
which is what `fastapi_app.py` calls per request.

If `agent_framework` is unavailable (e.g. during local dev with stripped
requirements), the agent falls back to calling the LLM directly without
the executor wrapper — same prompt, same schema, same outputs.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

from openai import AsyncAzureOpenAI
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

from prompts.clarifier_prompt import (
    CLARIFIER_SYSTEM_PROMPT,
    CLARIFIER_USER_PROMPT_TEMPLATE,
)

from .clarifier_models import ClarifierDecision, ClarifierInput

logger = logging.getLogger(__name__)


# ============================================================================
# JSON SCHEMA (mirrors ClarifierDecision Pydantic model)
# ============================================================================

CLARIFIER_DECISION_SCHEMA = {
    "name": "clarifier_decision",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["passthrough", "clarify"],
            },
            "target_route": {
                "type": ["string", "null"],
                "enum": [
                    "navigate_to", "stac_search", "vision_analysis",
                    "contextual", "hybrid", None,
                ],
            },
            "analyzer_kind": {
                "type": ["string", "null"],
                "enum": ["text", "vision", "both", None],
            },
            "analyzer": {
                "type": ["string", "null"],
                "enum": [
                    "contextual", "graph_rag",
                    "vision", "raster_sampling", "terrain", "mobility",
                    "extreme_weather", "netcdf_computation", "building_damage",
                    "comparison", None,
                ],
            },
            "missing_slot": {
                "type": ["string", "null"],
                "enum": [
                    "intent", "location", "collection", "has_imagery",
                    "question", "analyzer_kind", "analysis_target",
                    "time_range", None,
                ],
            },
            "user_response": {"type": "string"},
            "options": {
                "type": "array",
                "items": {"type": "string"},
            },
            "reasoning": {"type": "string"},
        },
        "required": [
            "action", "target_route", "analyzer_kind", "analyzer",
            "missing_slot", "user_response", "options", "reasoning",
        ],
        "additionalProperties": False,
    },
}


# ============================================================================
# AGENT
# ============================================================================

class ClarifierAgent:
    """
    Layer-0 conversational router. Decides whether to PASSTHROUGH a
    request to the downstream router or to CLARIFY with the user.

    All behavior is defined by the prompt in `prompts/clarifier_prompt.py`
    plus the `ClarifierDecision` schema. No hard-coded word lists.
    """

    def __init__(
        self,
        *,
        deployment: Optional[str] = None,
        endpoint: Optional[str] = None,
        api_version: str = "2024-12-01-preview",
    ):
        self.deployment = deployment or os.getenv(
            "AZURE_OPENAI_CLARIFIER_DEPLOYMENT",
            os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5"),
        )
        self.endpoint = endpoint or os.getenv(
            "AZURE_AI_PROJECT_ENDPOINT"
        ) or os.getenv("AZURE_OPENAI_ENDPOINT")
        if not self.endpoint:
            raise ValueError(
                "ClarifierAgent requires AZURE_AI_PROJECT_ENDPOINT or "
                "AZURE_OPENAI_ENDPOINT to be set."
            )
        self.api_version = api_version
        self._client: Optional[AsyncAzureOpenAI] = None

    # ------------------------------------------------------------------
    # Lazy LLM client
    # ------------------------------------------------------------------
    def _get_client(self) -> AsyncAzureOpenAI:
        if self._client is not None:
            return self._client
        api_key = os.environ.get("AZURE_OPENAI_API_KEY") or None
        token_provider = None
        if not api_key:
            token_provider = get_bearer_token_provider(
                DefaultAzureCredential(),
                "https://cognitiveservices.azure.com/.default",
            )
        # api_key must be None (not "") so the OpenAI SDK falls through
        # to azure_ad_token_provider for managed-identity auth.
        self._client = AsyncAzureOpenAI(
            azure_endpoint=self.endpoint,
            api_key=api_key,
            azure_ad_token_provider=token_provider,
            api_version=self.api_version,
        )
        return self._client

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------
    async def decide(self, payload: ClarifierInput) -> ClarifierDecision:
        """
        Run the clarifier prompt and return a ClarifierDecision.

        Falls back to a deterministic passthrough on any error so the
        request keeps working even if the LLM is unreachable.
        """
        try:
            pin_lat_lng = (
                f"({payload.pin_lat:.4f}, {payload.pin_lng:.4f})"
                if payload.has_pin and payload.pin_lat is not None and payload.pin_lng is not None
                else "null"
            )
            user_prompt = CLARIFIER_USER_PROMPT_TEMPLATE.format(
                query=payload.query,
                has_rendered_map=payload.has_rendered_map,
                has_screenshot=payload.has_screenshot,
                has_last_bbox=payload.has_last_bbox,
                pending_clarification=payload.pending_clarification,
                has_pin=payload.has_pin,
                pin_lat_lng=pin_lat_lng,
                prior_action=payload.prior_action or "null",
                prior_target_route=payload.prior_target_route or "null",
                prior_location=payload.prior_location or "null",
                prior_collection=payload.prior_collection or "null",
            )

            client = self._get_client()
            response = await client.chat.completions.create(
                model=self.deployment,
                messages=[
                    {"role": "system", "content": CLARIFIER_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": CLARIFIER_DECISION_SCHEMA,
                },
                temperature=0.0,
                reasoning_effort="minimal",
            )

            content = response.choices[0].message.content or "{}"
            data = json.loads(content)
            decision = ClarifierDecision.model_validate(data)
            logger.info(
                f"[CLARIFIER] action={decision.action} "
                f"route={decision.target_route} slot={decision.missing_slot} "
                f"reason={decision.reasoning[:120]}"
            )
            return decision

        except Exception as e:
            logger.warning(
                f"[CLARIFIER] LLM call failed ({e!r}); falling back to passthrough"
            )
            return ClarifierDecision(
                action="passthrough",
                target_route=None,
                missing_slot=None,
                user_response="",
                options=[],
                reasoning=f"fallback_passthrough_due_to_error: {e}",
            )


# ============================================================================
# Module-level singleton (cheap re-use across requests)
# ============================================================================

_singleton: Optional[ClarifierAgent] = None


def get_clarifier_agent() -> ClarifierAgent:
    """Return a process-wide ClarifierAgent instance."""
    global _singleton
    if _singleton is None:
        _singleton = ClarifierAgent()
    return _singleton
