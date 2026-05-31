"""Planner ChatAgent for Site Intel — picks which dimensions to score and
how to weight them based on the user's free-text question.

Behavior matrix
---------------
``SITE_PLANNER`` unset / ``0``
    No-op. Emits a :class:`PlannedSpec` with all six dimensions active and
    :data:`executors.DEFAULT_WEIGHTS`. Output is bit-identical to v2.0
    (the workflow runs the same fan-out it always did).

``SITE_PLANNER=1``
    Calls Azure OpenAI (same pattern as
    :mod:`agents.query_splitter.query_splitter`) with a JSON-schema-constrained
    prompt. The model returns ``{dimensions, weights, reasoning}``; we
    sanity-clamp and emit the planned spec. Any error → fail-open to the
    default plan, with ``planner_engine='fallback'`` for observability.

The planner *never* fails the workflow — a bad LLM response always
degrades to the default plan so the audit still produces a dossier.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

try:
    from agent_framework import Executor, WorkflowContext, handler  # type: ignore
    AGENT_FRAMEWORK_AVAILABLE = True
except Exception as exc:  # pragma: no cover
    logger.info("agent_framework not available (%s); planner is a stub", exc)
    AGENT_FRAMEWORK_AVAILABLE = False
    Executor = object  # type: ignore
    handler = lambda f: f  # type: ignore  # noqa: E731

    class WorkflowContext:  # type: ignore
        """Stand-in so type hints resolve at import time."""

from .messages import ALL_DIMENSIONS, PlannedSpec, SiteSpec


# ──────────────────────────────────────────────────────────────────────────────
# Default plan — used when the planner is disabled or when the LLM call fails.
# Weights match v1 / v2.0 exactly so audits are byte-identical when the flag
# is off.
# ──────────────────────────────────────────────────────────────────────────────
DEFAULT_PLAN_WEIGHTS: dict[str, float] = {
    "power": 0.35,
    "water": 0.15,
    "hazards": 0.15,
    "competition": 0.10,
    "parcel": 0.10,       # NB: weights key is "parcel"; dimension is "parcel_match"
    "precedent": 0.15,
}


_PLANNER_SYSTEM_PROMPT = """\
You are the Site Intel planner. Given a candidate site for a utility or
grid asset (substation, transmission tap, solar / wind / BESS plant,
thermal generation, or interconnection) and a free-text question, decide
which of these six scoring dimensions should run:

  power         – grid proximity / available interconnection capacity
                  (closer to HV transmission + substations with headroom = better)
  water         – cooling or process water availability
                  (prune for solar / wind / BESS; keep for thermal / hydro)
  hazards       – wildfire, flood, seismic, elevation exposure
  competition   – existing generation / load density nearby
                  (saturation check — too much nearby capacity lowers value)
  parcel_match  – overlap with curated candidate parcel set
                  (zoning, easements, protected lands)
  precedent     – relevant permitting / interconnection precedent docs
                  (FERC, state PUC, NEPA, utility commission filings)

Pick the smallest set that meaningfully answers the question. Pruning is
allowed but at least 3 dimensions must remain active. Weights must sum to
1.0 (use the dimension keys above; for "parcel_match" use the weight key
"parcel"). Bias weights toward dimensions the user explicitly mentioned;
for asset types that don't need water (solar / wind / BESS), drop or down-
weight the water dimension and reallocate to power and hazards.

Respond with JSON only, matching this schema:
  { "dimensions": [...], "weights": {...}, "reasoning": "one sentence" }
"""


_PLANNER_SCHEMA: dict[str, Any] = {
    "name": "SiteIntelPlan",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "dimensions": {
                "type": "array",
                "items": {"type": "string", "enum": list(ALL_DIMENSIONS)},
                "minItems": 3,
            },
            "weights": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "power": {"type": "number"},
                    "water": {"type": "number"},
                    "hazards": {"type": "number"},
                    "competition": {"type": "number"},
                    "parcel": {"type": "number"},
                    "precedent": {"type": "number"},
                },
                "required": ["power", "water", "hazards", "competition", "parcel", "precedent"],
            },
            "reasoning": {"type": "string", "maxLength": 240},
        },
        "required": ["dimensions", "weights", "reasoning"],
    },
}


def _default_plan(spec: SiteSpec, engine: str = "default", reasoning: str = "") -> PlannedSpec:
    return PlannedSpec(
        spec=spec,
        active_dimensions=set(ALL_DIMENSIONS),
        weights=dict(DEFAULT_PLAN_WEIGHTS),
        planner_reasoning=reasoning or "Default plan (planner disabled).",
        planner_engine=engine,
    )


async def _llm_plan(spec: SiteSpec) -> PlannedSpec:
    """Call Azure OpenAI to produce a tailored plan. Raises on any error."""
    endpoint = (
        os.getenv("AZURE_AI_PROJECT_ENDPOINT")
        or os.getenv("AZURE_OPENAI_ENDPOINT")
    )
    if not endpoint:
        raise RuntimeError("AZURE_OPENAI_ENDPOINT / AZURE_AI_PROJECT_ENDPOINT not set")

    from openai import AsyncAzureOpenAI
    from azure.identity import DefaultAzureCredential, get_bearer_token_provider

    api_key = os.environ.get("AZURE_OPENAI_API_KEY") or None
    token_provider = None
    if not api_key:
        token_provider = get_bearer_token_provider(
            DefaultAzureCredential(),
            "https://cognitiveservices.azure.com/.default",
        )
    client = AsyncAzureOpenAI(
        azure_endpoint=endpoint,
        api_key=api_key,
        azure_ad_token_provider=token_provider,
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21"),
    )

    deployment = os.getenv("SITE_PLANNER_DEPLOYMENT") or os.getenv(
        "AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5"
    )
    user_msg = (
        f"Site: ({spec.lat:.4f}, {spec.lng:.4f}), proposed asset capacity {spec.claimed_mw} MW.\n"
        f"User question: {spec.user_query or '(no specific question — full utility-siting audit)'}\n"
    )

    response = await client.chat.completions.create(
        model=deployment,
        messages=[
            {"role": "system", "content": _PLANNER_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        response_format={"type": "json_schema", "json_schema": _PLANNER_SCHEMA},
        temperature=0.0,
        reasoning_effort="minimal",
    )
    raw = json.loads(response.choices[0].message.content or "{}")

    dims = [d for d in raw.get("dimensions", []) if d in ALL_DIMENSIONS]
    if len(dims) < 3:
        raise ValueError(f"planner returned too few dimensions: {dims}")

    weights = {k: float(v) for k, v in raw.get("weights", {}).items()}
    # Zero out weights for inactive dimensions, then re-normalize so sum=1.
    dim_to_weight_key = {
        "power": "power", "water": "water", "hazards": "hazards",
        "competition": "competition", "parcel_match": "parcel",
        "precedent": "precedent",
    }
    active_weight_keys = {dim_to_weight_key[d] for d in dims}
    for k in list(weights):
        if k not in active_weight_keys:
            weights[k] = 0.0
    total = sum(weights.values())
    if total <= 0:
        raise ValueError("planner weights summed to 0")
    weights = {k: v / total for k, v in weights.items()}

    return PlannedSpec(
        spec=spec,
        active_dimensions=set(dims),
        weights=weights,
        planner_reasoning=str(raw.get("reasoning", "")).strip()[:240],
        planner_engine="llm",
    )


# ──────────────────────────────────────────────────────────────────────────────
# Executor
# ──────────────────────────────────────────────────────────────────────────────
class PlannerExecutor(Executor):  # type: ignore[misc]
    """Start-of-graph executor that turns a :class:`SiteSpec` into a
    :class:`PlannedSpec`. Never raises — falls back to the default plan
    on any error."""

    def __init__(self, id: str = "planner") -> None:
        if AGENT_FRAMEWORK_AVAILABLE:
            super().__init__(id=id)
        self.id = id

    if AGENT_FRAMEWORK_AVAILABLE:
        @handler  # type: ignore
        async def on_message(
            self,
            spec: SiteSpec,
            ctx: "WorkflowContext[PlannedSpec]",
        ) -> None:
            flag = os.getenv("SITE_PLANNER", "0").lower() in ("1", "true", "yes", "on")
            if not flag:
                await ctx.send_message(_default_plan(spec))
                return
            try:
                plan = await _llm_plan(spec)
                logger.info(
                    "[PLANNER] active=%s reasoning=%r",
                    sorted(plan.active_dimensions), plan.planner_reasoning,
                )
                await ctx.send_message(plan)
            except Exception as exc:  # noqa: BLE001
                logger.warning("[PLANNER] LLM plan failed (%s); using default", exc)
                await ctx.send_message(
                    _default_plan(spec, engine="fallback", reasoning=f"LLM failed: {exc}")
                )
