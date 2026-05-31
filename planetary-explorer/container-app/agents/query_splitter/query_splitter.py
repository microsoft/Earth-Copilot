"""
QuerySplitter
=============

Detects multi-part user queries that would otherwise force a single backend
turn to make several expensive tool calls (and likely time out at the
Azure Container Apps ingress, which kills idle requests at ~240s).

Strategy
--------
1. **Cheap heuristic gate** — only invoke the LLM when the query looks
   plausibly multi-part (multiple `?`, conjunctions, numbered lists,
   multiple sentences). Single-clause questions skip the LLM entirely so
   we add zero latency in the common case.

2. **LLM splitter (gpt-5, structured output)** — given the list of
   "combined" tools that already return multiple values together (e.g.
   `get_temperature_projection` returns max+min+mean), it decides:
     - `is_multi_part = false` → run as today.
     - `is_multi_part = true`  → return a list of parts, each with an
       optional `depends_on` index pointing to a previous part whose
       answer must be substituted into this part before dispatch.

3. **Fail-open** — any error returns `is_multi_part = false`, so the
   normal pipeline always runs. No new failure modes are introduced.

Caller (fastapi_app.py) handles the rest:
- If `is_multi_part`, return `action: "sequential_parts"` with the part
  list and an intro message. The frontend then dispatches each part as
  a separate `/api/query` call (sharing `session_id`), inheriting all
  existing routing, clarification, and session-context behavior.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public data shapes
# ---------------------------------------------------------------------------


class SplitPart(BaseModel):
    """A single part of a split multi-part query."""

    id: int = Field(..., description="1-based ordinal of this part.")
    query: str = Field(..., description="Self-contained natural-language sub-question.")
    depends_on: List[int] = Field(
        default_factory=list,
        description=(
            "List of earlier part ids whose answers must be available "
            "before this part can run. Empty = independent."
        ),
    )


class SplitDecision(BaseModel):
    """Splitter result returned to the caller."""

    is_multi_part: bool
    parts: List[SplitPart] = Field(default_factory=list)
    intro: str = Field(
        default="",
        description="Short user-facing message announcing the split.",
    )
    reason: str = Field(default="", description="Internal reasoning for logs.")


# ---------------------------------------------------------------------------
# Cheap heuristic gate
# ---------------------------------------------------------------------------


# Words that, when joined to another verb-clause via "and", strongly suggest
# a second independent question.  We deliberately keep this tight to avoid
# false positives on "max and min temperature" (a single tool can answer).
_MULTI_PART_HINTS = re.compile(
    r"""(
        \?\s*[A-Za-z].*\?            # multiple question marks
      | \band\s+(is|are|will|how|why|does|do|when|where|what|which|who)\b
      | \balso\s+(tell|show|find|give|describe|explain|compare|analyze)\b
      | \bthen\s+(tell|show|find|give|describe|explain|compare|analyze)\b
      | \b(first|second|third|finally|next)[,\s]
      | ^\s*\d+[.)]\s                # numbered list at start
      | \n\s*\d+[.)]\s               # numbered list mid-text
    )""",
    re.IGNORECASE | re.VERBOSE | re.MULTILINE,
)


def _looks_multi_part(query: str) -> bool:
    """Cheap pattern check before paying for an LLM call."""
    if not query or len(query) < 25:
        return False
    if _MULTI_PART_HINTS.search(query):
        return True
    # Two or more sentences ending in a question mark or period followed by
    # a capitalized word also suggests multiple asks.
    if re.search(r"[.?!]\s+[A-Z][a-z]", query):
        return True
    return False


# ---------------------------------------------------------------------------
# LLM splitter
# ---------------------------------------------------------------------------


SPLITTER_SYSTEM_PROMPT = """You are a query planner for an Earth-data assistant.

Your ONLY job: decide if the user's message is ONE question or SEVERAL
independent questions that would each require a separate, expensive backend
tool call. Return structured JSON.

When NOT to split (return is_multi_part=false):
- Single-tool questions like "max and min temperature" — `get_temperature_projection`
  already returns max+min+mean in ONE call.
- "Temperature, humidity and wind?" — `get_climate_overview` returns all three.
- "Compare SSP245 vs SSP585" — `compare_climate_scenarios` is one tool.
- Pure rephrasings or follow-up clarifications.
- Ambiguous/short queries — let the downstream clarifier handle them.

When TO split (return is_multi_part=true, 2-3 parts MAX):
- Two truly independent asks that map to DIFFERENT tools/agents:
  - "What are projected temps AND is heat increasing?" →
    [get_temperature_projection, compute_trend]
  - "Show NAIP imagery AND give the elevation profile" →
    [LOAD action, terrain analyzer]
  - "Describe what's at this pin AND find similar areas" →
    [vision describe, similarity search]
- Questions with explicit step words ("first ... then ...", "also tell me ...").

Dependencies:
- If part 2 needs part 1's ANSWER as input (e.g. "find the hottest country,
  then show its trend"), set depends_on=[1] for part 2. The runner will
  substitute part 1's answer into part 2 before dispatch.
- Most splits are INDEPENDENT (depends_on=[]). Only mark dependent when
  truly necessary.

Constraints:
- Maximum 3 parts. If you'd produce more, merge the smallest related ones.
- Each `query` must be a complete, self-contained question that makes sense
  on its own (don't write "Now do part 2" — write the actual question).
- `intro` is a 1-sentence user-facing string like
  "I'll answer this in 2 parts so each comes back quickly."
- `reason` is internal-only debugging text explaining your tool mapping.

Available downstream tools/agents (for context — do NOT mention these to the user):
- get_temperature_projection (max + min + mean in one call)
- get_precipitation_projection (mean + peak + total)
- get_wind_projection
- get_humidity_projection
- get_radiation_projection
- get_climate_overview (all variables in one call)
- compare_climate_scenarios (SSP245 vs SSP585)
- compute_trend (multi-decade linear fit)
- compute_anomaly (year-vs-year change)
- sample_timeseries (monthly/seasonal pattern)
- sample_area_stats (bbox statistics)
- vision describe (what is shown in imagery)
- raster_sampling (numeric value at a pin)
- terrain analyzer (elevation, slope)
- mobility analyzer (route traversability between two pins)
- comparison analyzer (before/after temporal)
- building_damage analyzer
- LOAD action (search + render STAC tiles on the map)
- NAVIGATE action (fly map camera to a place)
- contextual (general explanations)
"""


SPLITTER_USER_PROMPT_TEMPLATE = """User message:
\"\"\"{query}\"\"\"

Decide whether to split. Be conservative: when in doubt, return is_multi_part=false."""


SPLITTER_DECISION_SCHEMA = {
    "name": "query_split_decision",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "is_multi_part": {"type": "boolean"},
            "parts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "query": {"type": "string"},
                        "depends_on": {
                            "type": "array",
                            "items": {"type": "integer"},
                        },
                    },
                    "required": ["id", "query", "depends_on"],
                    "additionalProperties": False,
                },
            },
            "intro": {"type": "string"},
            "reason": {"type": "string"},
        },
        "required": ["is_multi_part", "parts", "intro", "reason"],
        "additionalProperties": False,
    },
}


# ---------------------------------------------------------------------------
# Splitter agent
# ---------------------------------------------------------------------------


class QuerySplitter:
    """Single-LLM-call planner that decides if a query should be split."""

    MAX_PARTS = 3

    def __init__(
        self,
        *,
        deployment: Optional[str] = None,
        endpoint: Optional[str] = None,
        api_version: str = "2024-12-01-preview",
    ):
        self.deployment = deployment or os.getenv(
            "AZURE_OPENAI_SPLITTER_DEPLOYMENT",
            os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5"),
        )
        # AZURE_OPENAI_ENDPOINT must win -- the AI Foundry project URL
        # is not an OpenAI chat-completions endpoint and 401s with
        # "audience is incorrect (https://ai.azure.com)" against the
        # cognitiveservices-scoped token used below.
        self.endpoint = (
            endpoint
            or os.getenv("AZURE_OPENAI_ENDPOINT")
            or os.getenv("AZURE_AI_PROJECT_ENDPOINT")
        )
        self.api_version = api_version
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        if not self.endpoint:
            raise RuntimeError(
                "QuerySplitter requires AZURE_AI_PROJECT_ENDPOINT or "
                "AZURE_OPENAI_ENDPOINT to be set."
            )
        from openai import AsyncAzureOpenAI
        from azure.identity import DefaultAzureCredential, get_bearer_token_provider

        api_key = os.environ.get("AZURE_OPENAI_API_KEY") or None
        token_provider = None
        if not api_key:
            token_provider = get_bearer_token_provider(
                DefaultAzureCredential(),
                "https://cognitiveservices.azure.com/.default",
            )
        self._client = AsyncAzureOpenAI(
            azure_endpoint=self.endpoint,
            api_key=api_key,
            azure_ad_token_provider=token_provider,
            api_version=self.api_version,
        )
        return self._client

    async def split(self, query: str) -> SplitDecision:
        """Return a SplitDecision. Fails open to is_multi_part=false."""
        try:
            if not query or not query.strip():
                return SplitDecision(is_multi_part=False, reason="empty_query")

            # 1) Cheap pattern gate
            if not _looks_multi_part(query):
                return SplitDecision(is_multi_part=False, reason="heuristic_single")

            # 2) LLM call
            client = self._get_client()
            user_prompt = SPLITTER_USER_PROMPT_TEMPLATE.format(query=query.strip())
            response = await client.chat.completions.create(
                model=self.deployment,
                messages=[
                    {"role": "system", "content": SPLITTER_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": SPLITTER_DECISION_SCHEMA,
                },
                temperature=0.0,
                reasoning_effort="minimal",
            )
            content = response.choices[0].message.content or "{}"
            raw = json.loads(content)

            decision = SplitDecision(
                is_multi_part=bool(raw.get("is_multi_part")),
                parts=[SplitPart(**p) for p in raw.get("parts", [])],
                intro=raw.get("intro", "") or "",
                reason=raw.get("reason", "") or "",
            )

            # 3) Sanity-check / clamp
            if decision.is_multi_part:
                if not decision.parts or len(decision.parts) < 2:
                    logger.info("[SPLITTER] LLM said multi but returned <2 parts → single")
                    return SplitDecision(is_multi_part=False, reason="too_few_parts")
                if len(decision.parts) > self.MAX_PARTS:
                    logger.info(
                        f"[SPLITTER] Clamping {len(decision.parts)} parts to {self.MAX_PARTS}"
                    )
                    decision.parts = decision.parts[: self.MAX_PARTS]
                # Re-number ids 1..N and drop dangling depends_on references.
                valid_ids = set()
                for new_id, part in enumerate(decision.parts, start=1):
                    part.id = new_id
                    valid_ids.add(new_id)
                for part in decision.parts:
                    part.depends_on = [
                        d for d in part.depends_on if d in valid_ids and d < part.id
                    ]
                if not decision.intro:
                    decision.intro = (
                        f"I'll answer this in {len(decision.parts)} parts so each "
                        "comes back quickly."
                    )

            logger.info(
                f"[SPLITTER] is_multi_part={decision.is_multi_part} "
                f"parts={len(decision.parts)} reason={decision.reason!r}"
            )
            return decision

        except Exception as exc:  # noqa: BLE001 — fail open
            logger.warning(f"[SPLITTER] failed, falling through single-call: {exc}")
            return SplitDecision(is_multi_part=False, reason=f"error: {exc}")


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------


_singleton: Optional[QuerySplitter] = None


def get_query_splitter() -> QuerySplitter:
    global _singleton
    if _singleton is None:
        _singleton = QuerySplitter()
    return _singleton
