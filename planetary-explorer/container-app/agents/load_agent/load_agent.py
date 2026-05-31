"""LoadAgent — Layer-2 sibling that owns LOAD turns.

Pattern mirrors `Layer2ClarifierAgent`: a single structured-output AOAI call
with lazy MI-aware client, fail-open passthrough, and a Pydantic-validated
output. Invoked from `pipeline.dispatch.run_pipeline_v2` whenever Layer-1
classifies the turn as `LOAD` (and, optionally, `LOAD_AND_ANALYZE`).

Why this exists
---------------
Before this agent, v2's LOAD branch returned `answer=""` and let a legacy
keyword mapper render tiles silently — producing the user-visible
"No response received" bug. The LoadAgent fills the slot-extraction +
chat-answer gap without changing the tile-rendering path.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

from openai import AsyncAzureOpenAI
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

from prompts.load_agent_prompt import (
    LOAD_AGENT_SYSTEM_PROMPT,
    LOAD_AGENT_USER_PROMPT_TEMPLATE,
)

from .load_agent_models import DatetimeSlot, LoadAgentInput, LoadPlan, LocationSlot

logger = logging.getLogger(__name__)


# Top-K catalog candidates to retrieve from the live MPC catalog index
# and feed to the LLM. 5 keeps the prompt cheap but gives the LLM real
# choice between e.g. {modis-10A1-061, modis-10A2-061, modis-13A1-061,
# hls2-l30, sentinel-2-l2a} for a query like "snow cover for Quebec".
_CATALOG_TOPK = int(os.getenv("LOAD_AGENT_CATALOG_TOPK", "5"))
# Minimum score threshold for the dynamic family-signal check. Anything
# above zero means at least one collection in the live inventory matches
# the query lexically or semantically.
_CATALOG_FAMILY_THRESHOLD = float(
    os.getenv("LOAD_AGENT_CATALOG_FAMILY_THRESHOLD", "0.0")
)


# Tokens that look like STAC collection ids: lowercase letters/digits with at
# least one hyphen (e.g. ``sentinel-2-l2a``, ``sentinel2-fire``,
# ``landsat-c2-l2``, ``cop-dem-glo-30``). Mirrors
# ``collection_name_mapper.CollectionMapper._STAC_ID_TOKEN_RE`` so the two
# layers agree on what counts as a "literal collection id".
_STAC_ID_TOKEN_RE = re.compile(r"^[a-z][a-z0-9._]*-[a-z0-9._-]+$")
# Quoted strings (double, single, backtick) and bare hyphenated tokens. We
# split on whitespace/punctuation that are NOT hyphens, periods, or
# underscores so multi-hyphen ids survive intact.
_QUOTED_RE = re.compile(r"""["'`]([^"'`]+?)["'`]""")
_TOKEN_SPLIT_RE = re.compile(r"[\s,;()\[\]<>]+")


def _extract_explicit_collection_ids(query: str) -> List[str]:
    """Return collection-id tokens the user wrote literally in ``query``.

    Quoted forms (``"sentinel2-fire"``) take precedence over bare tokens.
    We preserve order and de-duplicate case-insensitively. Lower-cases the
    output because STAC ids are conventionally lowercase; downstream STAC
    search is case-insensitive anyway.
    """
    found: List[str] = []
    seen: set = set()

    def _maybe_add(tok: str) -> None:
        t = tok.strip().lower()
        if not t or t in seen:
            return
        if _STAC_ID_TOKEN_RE.match(t):
            seen.add(t)
            found.append(t)

    # 1. Anything inside quotes first -- the structured-search panel always
    #    quotes the id, so this is the high-signal source.
    for m in _QUOTED_RE.finditer(query):
        _maybe_add(m.group(1))

    # 2. Bare hyphenated tokens elsewhere in the query.
    for tok in _TOKEN_SPLIT_RE.split(query.lower()):
        _maybe_add(tok)

    return found


# ----------------------------------------------------------------------------
# Deterministic three-slot completeness check.
#
# When the user's query carries (a) a recognizable collection-family signal
# (any dataset/sensor word) AND (b) a time reference (year, month, season,
# or explicit date range), and Layer-1 has already extracted a location
# (location_name from ActionRouter, or has_bbox / has_pin in the payload),
# the request is FULLY SPECIFIED. There is nothing the LoadAgent could
# legitimately clarify -- a Terra-vs-Aqua / daily-vs-8day / animation-vs-
# layer prompt would just frustrate the user with a follow-up they already
# answered. In that case we override the LLM's action to 'execute' even if
# it returned 'clarify', and we let the executor render with the LLM's
# top-ranked candidate (or a deterministic family fallback).
#
# This is structural, not prompt-engineered: the LLM cannot opt out of it.
# ----------------------------------------------------------------------------

# Collection-family signals. Keys are lower-case tokens that, when present
# in the user's query, indicate a clear dataset/sensor intent. Order does
# not matter; any single hit counts as "family present".
_COLLECTION_FAMILY_TOKENS: set = {
    # Optical / multispectral
    "sentinel", "sentinel-1", "sentinel-2", "sentinel2", "sentinel-3",
    "landsat", "hls", "naip", "modis",
    # Land cover
    "nlcd", "esa worldcover", "worldcover", "io-lulc", "lulc",
    "land cover", "land-cover", "landcover",
    # Elevation / DEM
    "dem", "elevation", "cop-dem", "copernicus dem", "nasadem",
    "3dep", "lidar",
    # Water / SAR
    "jrc", "surface water", "sar", "alos",
    # Climate / atmosphere
    "era5", "chirps", "noaa cdr", "cdr", "goes",
    # Domain words that imply a known product family
    "snow cover", "snow", "ndvi", "evi", "lai", "fpar",
    "land surface temperature", "lst", "sst",
    "fire", "burn", "wildfire", "burned area", "active fire",
    "imagery", "rgb", "true color", "true-color", "false color",
    "vegetation", "reflectance",
    # Biomass / forest carbon
    "biomass", "chloris", "agb", "aboveground biomass",
    "above-ground biomass", "above ground biomass",
    "woody biomass", "forest biomass", "carbon",
}

# Time-reference signals. ANY one match means "user gave a time".
_TIME_PATTERNS = [
    re.compile(r"\b(19|20)\d{2}\b"),                                    # 2024, 2025
    re.compile(r"\b(19|20)\d{2}\s*[-/]\s*(19|20)?\d{2}\b"),              # 2010-2020
    re.compile(                                                          # month names
        r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|"
        r"jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|"
        r"nov(?:ember)?|dec(?:ember)?)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(spring|summer|fall|autumn|winter)\b", re.IGNORECASE),
    re.compile(r"\b(latest|recent|current|most recent|today|yesterday|last\s+\w+)\b", re.IGNORECASE),
    re.compile(r"\bQ[1-4]\s*(19|20)\d{2}\b", re.IGNORECASE),              # Q3 2024
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),                                 # ISO date
]


def _has_collection_family_signal(query: str) -> bool:
    q = (query or "").lower()
    if not q:
        return False
    return any(tok in q for tok in _COLLECTION_FAMILY_TOKENS)


def _has_time_signal(query: str) -> bool:
    if not query:
        return False
    return any(rx.search(query) for rx in _TIME_PATTERNS)


def _has_location_signal(payload) -> bool:  # type: ignore[no-untyped-def]
    """Layer-1 already does location extraction; trust it.

    A location is "present" when ActionRouter populated ``location_name``,
    or the caller already supplied a bbox/pin to anchor the search.
    """
    if getattr(payload, "has_bbox", False):
        return True
    if getattr(payload, "has_pin", False):
        return True
    name = getattr(payload, "location_name", None)
    return bool(name and name.strip() and name.strip().lower() != "null")


async def _fetch_catalog_candidates(query: str, stac_mode: Optional[str]) -> List[Dict[str, Any]]:
    """Best-effort: ask the live STAC inventory which real collection ids
    look most relevant to ``query``.

    Returns a list of ``{"id", "title", "score", "method"}`` dicts ranked
    by relevance (semantic when AOAI embeddings are configured, otherwise
    lexical Jaccard). Returns an empty list — never raises — when the
    catalog index hasn't loaded, the upstream is down, or the query is
    empty. The caller treats absence as "fall back to the keyword
    family-signal set" so a catalog outage degrades gracefully instead
    of breaking the LoadAgent.
    """
    if not query or not query.strip():
        return []
    try:
        # Lazy import to avoid a hard dependency cycle at module import
        # time and to keep the LoadAgent usable in unit tests that don't
        # stand up the index.
        from collection_index import get_collection_index  # type: ignore
    except Exception:  # pragma: no cover - missing module
        return []
    mode = (stac_mode or "public").strip().lower()
    if mode not in ("public", "pro"):
        mode = "public"
    try:
        index = await get_collection_index()
        cands = await index.search(query, mode, k=_CATALOG_TOPK)
    except Exception as exc:  # pragma: no cover - upstream catalog failure
        logger.debug("LoadAgent catalog lookup failed: %s", exc)
        return []
    out: List[Dict[str, Any]] = []
    for c in cands:
        meta = getattr(c, "meta", None)
        if meta is None:
            continue
        out.append({
            "id": meta.id,
            "title": meta.title or "",
            "score": float(getattr(c, "score", 0.0) or 0.0),
            "method": getattr(c, "method", "lexical"),
        })
    return out


def _format_catalog_matches(cands: List[Dict[str, Any]]) -> str:
    """Render catalog candidates as a compact bullet list for the prompt."""
    if not cands:
        return "  (none — live catalog index returned no matches or is unavailable)"
    lines: List[str] = []
    for c in cands:
        title = c.get("title") or ""
        score = c.get("score", 0.0)
        method = c.get("method", "lexical")
        lines.append(f"  - {c['id']}  ({method}, score={score:.3f}) — {title}")
    return "\n".join(lines)


LOAD_PLAN_SCHEMA = {
    "name": "load_plan",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["execute", "clarify"]},
            "intent": {
                "type": "string",
                "enum": [
                    "snapshot",
                    "temporal_change",
                    "timeseries",
                    "compare_collections",
                ],
            },
            "location": {
                "type": "object",
                "properties": {
                    "name": {"type": ["string", "null"]},
                    "needs_geocoding": {"type": "boolean"},
                    "suggested_bbox": {
                        "type": ["array", "null"],
                        "items": {"type": "number"},
                        "minItems": 4,
                        "maxItems": 4,
                    },
                },
                "required": ["name", "needs_geocoding", "suggested_bbox"],
                "additionalProperties": False,
            },
            "collection_candidates": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "title": {"type": "string"},
                        "rank": {"type": "integer"},
                        "reason": {"type": "string"},
                    },
                    "required": ["id", "title", "rank", "reason"],
                    "additionalProperties": False,
                },
            },
            "datetime": {
                "type": "object",
                "properties": {
                    "ambiguous": {"type": "boolean"},
                    "range": {
                        "type": ["array", "null"],
                        "items": {"type": "string"},
                        "minItems": 2,
                        "maxItems": 2,
                    },
                    "suggestions": {
                        "type": "array",
                        "items": {
                            "type": "array",
                            "items": {"type": "string"},
                            "minItems": 2,
                            "maxItems": 2,
                        },
                    },
                },
                "required": ["ambiguous", "range", "suggestions"],
                "additionalProperties": False,
            },
            "deliverable": {
                "type": "string",
                "enum": [
                    "single_layer",
                    "before_after",
                    "diff",
                    "stats_only",
                    "timeseries",
                ],
            },
            "stac_query": {"type": ["string", "null"]},
            "clarification_question": {"type": ["string", "null"]},
            "options": {"type": "array", "items": {"type": "string"}},
            "chat_summary": {"type": "string"},
            "confidence": {"type": "number"},
            "reasoning": {"type": "string"},
        },
        "required": [
            "action",
            "intent",
            "location",
            "collection_candidates",
            "datetime",
            "deliverable",
            "stac_query",
            "clarification_question",
            "options",
            "chat_summary",
            "confidence",
            "reasoning",
        ],
        "additionalProperties": False,
    },
}


class LoadAgent:
    """Single-call structured-output planner for LOAD turns."""

    def __init__(
        self,
        *,
        deployment: Optional[str] = None,
        endpoint: Optional[str] = None,
        api_version: str = "2024-12-01-preview",
    ):
        self.deployment = deployment or os.getenv(
            "AZURE_OPENAI_LOAD_AGENT_DEPLOYMENT",
            os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5"),
        )
        # Endpoint precedence: AZURE_OPENAI_ENDPOINT MUST win over
        # AZURE_AI_PROJECT_ENDPOINT. The AI Foundry "project" URL
        # (https://<x>.services.ai.azure.com/api/projects/<y>) is the
        # Agent Service surface and (a) is NOT an OpenAI-compatible
        # chat-completions endpoint, and (b) requires a token scoped
        # for the https://ai.azure.com audience -- our token provider
        # below requests https://cognitiveservices.azure.com, so the
        # Foundry endpoint always returns 401 with:
        #   "audience is incorrect (https://ai.azure.com)"
        # which silently degrades every LoadAgent call to the fail-open
        # path (and lets downstream agents fabricate clarifications the
        # LoadAgent prompt would have suppressed).
        self.endpoint = (
            endpoint
            or os.getenv("AZURE_OPENAI_ENDPOINT")
            or os.getenv("AZURE_AI_PROJECT_ENDPOINT")
        )
        if not self.endpoint:
            raise ValueError(
                "LoadAgent requires AZURE_AI_PROJECT_ENDPOINT or "
                "AZURE_OPENAI_ENDPOINT to be set."
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
        # api_key must be None (not "") so the SDK falls through to MI auth.
        self._client = AsyncAzureOpenAI(
            azure_endpoint=self.endpoint,
            api_key=api_key,
            azure_ad_token_provider=token_provider,
            api_version=self.api_version,
        )
        return self._client

    async def plan(self, payload: LoadAgentInput) -> LoadPlan:
        """Plan a STAC load. Always returns a LoadPlan with a non-empty chat_summary.

        Fails open: on any LLM error we return a minimal but valid plan that
        echoes the layer-1 hints so the legacy STAC search path still runs
        and the user sees a real chat answer instead of "No response received".
        """
        try:
            pin_lat_lng = (
                f"({payload.pin_lat:.4f}, {payload.pin_lng:.4f})"
                if payload.has_pin
                and payload.pin_lat is not None
                and payload.pin_lng is not None
                else "null"
            )

            # Live catalog lookup: ask the CollectionIndex which real
            # collection ids match this query right now. Replaces the
            # need for the LLM to memorize MPC's evolving inventory.
            # Best-effort — falls back to empty list on any failure.
            catalog_candidates = await _fetch_catalog_candidates(
                payload.query, payload.stac_mode
            )

            user_prompt = LOAD_AGENT_USER_PROMPT_TEMPLATE.format(
                query=payload.query,
                has_rendered_map=payload.has_rendered_map,
                loaded_collections=", ".join(payload.loaded_collections) or "",
                has_bbox=payload.has_bbox,
                bbox=payload.bbox,
                has_time_range=payload.has_time_range,
                time_range=payload.time_range,
                has_pin=payload.has_pin,
                pin_lat_lng=pin_lat_lng,
                location_name=payload.location_name or "null",
                layer1_stac_query=payload.layer1_stac_query or "null",
                layer1_reasoning=(payload.layer1_reasoning or "")[:200] or "null",
                stac_mode=payload.stac_mode or "public",
                available_pro_collections=", ".join(payload.available_pro_collections) or "<none configured>",
                catalog_matches=_format_catalog_matches(catalog_candidates),
                prior_query=payload.prior_query or "null",
                prior_clarification_question=payload.prior_clarification_question or "null",
                prior_clarification_options=", ".join(payload.prior_clarification_options) or "",
                prior_collection_candidates=", ".join(payload.prior_collection_candidates) or "",
                prior_clarification_history=(
                    "\n".join(
                        f"  Q{i+1}: {h.get('question', '')}\n  A{i+1}: {h.get('answer', '')}"
                        for i, h in enumerate(payload.prior_clarification_history)
                    )
                    or "  <none>"
                ),
                clarification_round=payload.clarification_round,
            )

            client = self._get_client()
            # Model-aware kwargs: gpt-5 / o-series reasoning models reject
            # `temperature` (only default=1 supported) and accept
            # `reasoning_effort`; classic chat models (gpt-4o*, gpt-4*)
            # reject `reasoning_effort` and accept arbitrary `temperature`.
            # Sending the wrong set silently fails-open on every request,
            # which had bypassed LoadAgent entirely in production.
            model_lc = (self.deployment or "").lower()
            is_reasoning = model_lc.startswith(("gpt-5", "o1", "o3", "o4"))
            extra: dict = {}
            if is_reasoning:
                extra["reasoning_effort"] = "minimal"
            else:
                extra["temperature"] = 0.0
            response = await client.chat.completions.create(
                model=self.deployment,
                messages=[
                    {"role": "system", "content": LOAD_AGENT_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": LOAD_PLAN_SCHEMA,
                },
                **extra,
            )
            content = response.choices[0].message.content or "{}"
            data = json.loads(content)
            plan = LoadPlan.model_validate(data)

            # ----------------------------------------------------------------
            # DETERMINISTIC OVERRIDE: honor explicit collection ids verbatim.
            #
            # The system prompt instructs the LLM to use literal/quoted
            # collection ids as rank-0 candidates, but LLMs occasionally
            # substitute a "better-known" id based on semantic context
            # (e.g. fire/California -> ``landsat-c2-l2`` even though the
            # user typed ``"sentinel2-fire"``). When that happens the chat
            # says "Searching sentinel2-fire" but the executor fetches the
            # wrong collection and renders the wrong tiles.
            #
            # Catch it here in code so we don't depend on LLM compliance.
            # If the raw query carries one or more literal STAC ids, force
            # the first one to rank 0 and set stac_query accordingly. We
            # only override when the LLM's top pick disagrees with the
            # user's explicit choice.
            # ----------------------------------------------------------------
            try:
                explicit_ids = _extract_explicit_collection_ids(payload.query)
                if explicit_ids:
                    from .load_agent_models import CollectionCandidate
                    user_choice = explicit_ids[0]
                    current_top = (
                        plan.collection_candidates[0].id.lower()
                        if plan.collection_candidates
                        else None
                    )
                    if current_top != user_choice:
                        logger.info(
                            "[LOAD_AGENT] explicit-id override: user=%s "
                            "llm_top=%s -- forcing rank 0 to %s",
                            user_choice, current_top, user_choice,
                        )
                        forced = CollectionCandidate(
                            id=user_choice,
                            title=user_choice,
                            rank=0,
                            reason="explicit_user_collection_id",
                        )
                        # Demote any existing candidate with the same id
                        # and re-rank everything else by +1.
                        rest = [
                            CollectionCandidate(
                                id=c.id,
                                title=c.title,
                                rank=c.rank + 1,
                                reason=c.reason,
                            )
                            for c in plan.collection_candidates
                            if c.id.lower() != user_choice
                        ]
                        plan.collection_candidates = [forced] + rest
                        plan.stac_query = user_choice
            except Exception as override_exc:  # pragma: no cover
                logger.warning(
                    "[LOAD_AGENT] explicit-id override skipped: %r",
                    override_exc,
                )

            # ----------------------------------------------------------------
            # DETERMINISTIC OVERRIDE: three-slot completeness.
            #
            # If the user gave LOCATION + COLLECTION-FAMILY + TIME, force
            # action='execute'. The LLM occasionally returns 'clarify' on
            # internal ambiguities (Terra vs Aqua, daily vs 8-day, animation
            # vs layer) even when every STAC slot the user controls is
            # filled. Those internal choices belong to the executor /
            # ranking heuristics, not to another round-trip with the user.
            # ----------------------------------------------------------------
            try:
                # Location signal: ActionRouter's location_name, OR an
                # explicit bbox/pin on the payload, OR the LoadAgent LLM
                # itself parsed a location into plan.location.name. The
                # third source is critical: ActionRouter's location
                # extractor is conservative and routinely misses biome
                # names ("Amazon rainforest"), regional descriptors
                # ("California coast"), or feature names that the LLM
                # picks up just fine. Without trusting plan.location.name
                # the override silently skips and the user gets stuck in
                # an LLM clarification the prompt explicitly forbids.
                has_loc = _has_location_signal(payload)
                if not has_loc:
                    _plan_loc = (
                        getattr(getattr(plan, "location", None), "name", None)
                        or ""
                    ).strip()
                    if _plan_loc and _plan_loc.lower() != "null":
                        has_loc = True
                        logger.info(
                            "[LOAD_AGENT] has_loc=True from plan.location.name=%r "
                            "(payload had no location)",
                            _plan_loc,
                        )
                # Family signal, in priority order (most structural first):
                #   1. The LLM itself extracted a non-empty stac_query or
                #      named at least one collection candidate. This IS the
                #      LLM telling us "I parsed a data noun from the user's
                #      message". If it managed that AND a location is
                #      present, asking the user "which data did you mean?"
                #      is contradictory — we already know.
                #   2. The live catalog index returned a candidate above
                #      the score threshold (handles cold-start when the
                #      LLM was conservative).
                #   3. Fast-path keyword fallback (cold-start, index
                #      disabled, offline tests). This is a best-effort
                #      list, NOT the source of truth.
                has_fam_llm = bool(
                    (plan.stac_query and plan.stac_query.strip())
                    or plan.collection_candidates
                )
                has_fam_catalog = any(
                    c.get("score", 0.0) > _CATALOG_FAMILY_THRESHOLD
                    for c in catalog_candidates
                )
                has_fam = (
                    has_fam_llm
                    or has_fam_catalog
                    or _has_collection_family_signal(payload.query)
                )
                # Time signal: present for explicit dates / years / "latest"
                # words. We treat time as effectively satisfied for ALL
                # intents here because there is no downstream temporal-
                # change / comparison executor in this build — LoadAgent
                # always renders a single STAC layer. Even when the LLM
                # labels intent='temporal_change' (e.g. the user said
                # "changes" or "over time"), asking the user for a year
                # range is dead-end UX: we'll just render the latest
                # snapshot regardless. Keep the helper around so the
                # override still fires when an explicit year IS present
                # (it logs a cleaner reason), but never gate on it.
                has_time_explicit = (
                    _has_time_signal(payload.query)
                    or payload.has_time_range
                )
                # No temporal-change agent wired in -> never block on time.
                has_time = True
                # Family + time is enough to override clarify. The LoadAgent
                # prompt forbids clarifying on deliverable / styling / scope
                # whenever the user named a data noun, but the LLM still
                # occasionally returns clarify with chat_summary like
                # "How would you like Chloris biomass for the Amazon -- map
                # layer, point value, or stats?". When has_fam is True we
                # know the user said a data noun, and we have a perfectly
                # good downstream geocoder that handles biome names like
                # "Amazon rainforest" even if ActionRouter / the LLM never
                # populated a structured location slot. Falling through to
                # an LLM clarification in that case is the worst outcome.
                if (
                    plan.action == "clarify"
                    and has_fam and has_time
                ):
                    logger.info(
                        "[LOAD_AGENT] family+time override: forcing "
                        "action=execute (loc=%s fam=%s time=%s) "
                        "llm_clarify=%r",
                        has_loc, has_fam, has_time,
                        plan.clarification_question,
                    )
                    plan.action = "execute"
                    plan.clarification_question = None
                    plan.options = []
                    plan.datetime.ambiguous = False
                    plan.datetime.suggestions = []
                    # Ensure stac_query is set so the executor can run.
                    if not plan.stac_query:
                        if plan.collection_candidates:
                            plan.stac_query = plan.collection_candidates[0].id
                        else:
                            plan.stac_query = (
                                payload.layer1_stac_query or payload.query
                            )
                    # Replace any clarification-shaped chat_summary with a
                    # neutral execute summary the post-render rebuilder
                    # will overwrite anyway.
                    top_id = (
                        plan.collection_candidates[0].id
                        if plan.collection_candidates
                        else plan.stac_query
                    )
                    loc_str = (
                        payload.location_name
                        or (
                            getattr(getattr(plan, "location", None), "name", None)
                            or ""
                        ).strip()
                        or payload.query
                        or "the requested area"
                    )
                    # Also surface plan.location.name to the executor so the
                    # downstream geocoder can resolve biome / region names
                    # the LLM extracted even when payload.location_name was
                    # empty.
                    if plan.location and not plan.location.name:
                        plan.location.name = (
                            payload.location_name or payload.query
                        )
                    if plan.location and plan.location.name and not payload.has_bbox:
                        plan.location.needs_geocoding = True
                    plan.chat_summary = (
                        f"Loading {top_id} over {loc_str}."
                    )
            except Exception as slot_exc:  # pragma: no cover
                logger.warning(
                    "[LOAD_AGENT] three-slot override skipped: %r",
                    slot_exc,
                )

            logger.info(
                "[LOAD_AGENT] action=%s intent=%s top=%s deliv=%s "
                "ambiguous_dt=%s conf=%.2f",
                plan.action,
                plan.intent,
                (plan.collection_candidates[0].id
                    if plan.collection_candidates else "<none>"),
                plan.deliverable,
                plan.datetime.ambiguous,
                plan.confidence,
            )
            return plan
        except Exception as e:  # pragma: no cover
            logger.warning(
                "[LOAD_AGENT] LLM call failed (%r); returning fail-open plan", e
            )
            # Fail-open: never let the chat go silent. Echo Layer-1's hint as
            # the stac query and let the legacy keyword path render tiles.
            fallback_query = payload.layer1_stac_query or payload.query
            location_str = payload.location_name or "the requested area"
            return LoadPlan(
                action="execute",
                intent="snapshot",
                location=LocationSlot(
                    name=payload.location_name,
                    needs_geocoding=bool(payload.location_name)
                    and not payload.has_bbox,
                    suggested_bbox=payload.bbox,
                ),
                collection_candidates=[],
                datetime=DatetimeSlot(
                    ambiguous=False,
                    range=payload.time_range,
                    suggestions=[],
                ),
                deliverable="single_layer",
                stac_query=fallback_query,
                clarification_question=None,
                options=[],
                chat_summary=(
                    # REQ-LOAD-3: never echo the user's raw query. The
                    # final chat reply is rebuilt post-render from
                    # actual features in fastapi_app.py; this string is
                    # only a non-empty placeholder to satisfy the
                    # Pydantic min_length constraint.
                    f"Loading imagery for {location_str}."
                ),
                confidence=0.0,
                reasoning=f"fallback_due_to_error: {e}",
            )


_singleton: Optional[LoadAgent] = None


def get_load_agent() -> LoadAgent:
    global _singleton
    if _singleton is None:
        _singleton = LoadAgent()
    return _singleton
