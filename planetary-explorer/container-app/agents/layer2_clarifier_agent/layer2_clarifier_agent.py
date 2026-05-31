"""
Layer-2 Clarifier Agent.

Mirrors `ClarifierAgent` (Layer-1) but constrained to the Layer-2 schema:
  - decides TEXT / VISION / BOTH and (when possible) the specific analyzer
  - asks one focused follow-up when the modality / target is unclear

Single structured-output AOAI call, lazy client (key OR managed identity),
fail-open passthrough so we never deadlock the request on LLM error.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

from openai import AsyncAzureOpenAI
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

from prompts.layer2_clarifier_prompt import (
    LAYER2_CLARIFIER_SYSTEM_PROMPT,
    LAYER2_CLARIFIER_USER_PROMPT_TEMPLATE,
)

from .layer2_clarifier_models import Layer2ClarifierDecision, Layer2ClarifierInput

logger = logging.getLogger(__name__)


LAYER2_CLARIFIER_DECISION_SCHEMA = {
    "name": "layer2_clarifier_decision",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["passthrough", "clarify"]},
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
                "enum": ["analyzer_kind", "analysis_target", "has_imagery", "collection", None],
            },
            "user_response": {"type": "string"},
            "options": {"type": "array", "items": {"type": "string"}},
            "reasoning": {"type": "string"},
        },
        "required": [
            "action", "analyzer_kind", "analyzer", "missing_slot",
            "user_response", "options", "reasoning",
        ],
        "additionalProperties": False,
    },
}


class Layer2ClarifierAgent:
    """Layer-2 conversational router — modality + analyzer."""

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
        # AZURE_OPENAI_ENDPOINT must win -- the AI Foundry project URL
        # is not an OpenAI chat-completions endpoint and 401s with
        # "audience is incorrect (https://ai.azure.com)" against the
        # cognitiveservices-scoped token below.
        self.endpoint = (
            endpoint
            or os.getenv("AZURE_OPENAI_ENDPOINT")
            or os.getenv("AZURE_AI_PROJECT_ENDPOINT")
        )
        if not self.endpoint:
            raise ValueError(
                "Layer2ClarifierAgent requires AZURE_OPENAI_ENDPOINT or "
                "AZURE_AI_PROJECT_ENDPOINT to be set."
            )
        self.api_version = api_version
        self._client: Optional[AsyncAzureOpenAI] = None

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

    async def decide(self, payload: Layer2ClarifierInput) -> Layer2ClarifierDecision:
        try:
            pin_lat_lng = (
                f"({payload.pin_lat:.4f}, {payload.pin_lng:.4f})"
                if payload.has_pin and payload.pin_lat is not None and payload.pin_lng is not None
                else "null"
            )
            user_prompt = LAYER2_CLARIFIER_USER_PROMPT_TEMPLATE.format(
                query=payload.query,
                target_route=payload.target_route,
                has_rendered_map=payload.has_rendered_map,
                has_screenshot=payload.has_screenshot,
                has_last_bbox=payload.has_last_bbox,
                has_pin=payload.has_pin,
                pin_lat_lng=pin_lat_lng,
                loaded_collections=", ".join(payload.loaded_collections) or "none",
                prior_analyzer_kind=payload.prior_analyzer_kind or "null",
                prior_analyzer=payload.prior_analyzer or "null",
                prior_analysis_target=payload.prior_analysis_target or "null",
            )

            client = self._get_client()
            response = await client.chat.completions.create(
                model=self.deployment,
                messages=[
                    {"role": "system", "content": LAYER2_CLARIFIER_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": LAYER2_CLARIFIER_DECISION_SCHEMA,
                },
                temperature=0.0,
                reasoning_effort="minimal",
            )
            content = response.choices[0].message.content or "{}"
            data = json.loads(content)
            decision = Layer2ClarifierDecision.model_validate(data)
            logger.info(
                f"[L2_CLARIFIER] action={decision.action} "
                f"kind={decision.analyzer_kind} analyzer={decision.analyzer} "
                f"slot={decision.missing_slot} "
                f"reason={decision.reasoning[:120]}"
            )
            return decision
        except Exception as e:
            logger.warning(
                f"[L2_CLARIFIER] LLM call failed ({e!r}); falling back to passthrough vision"
            )
            return Layer2ClarifierDecision(
                action="passthrough",
                analyzer_kind="vision",
                analyzer="vision",
                missing_slot=None,
                user_response="",
                options=[],
                reasoning=f"fallback_passthrough_due_to_error: {e}",
            )


_singleton: Optional[Layer2ClarifierAgent] = None


def get_layer2_clarifier_agent() -> Layer2ClarifierAgent:
    global _singleton
    if _singleton is None:
        _singleton = Layer2ClarifierAgent()
    return _singleton
