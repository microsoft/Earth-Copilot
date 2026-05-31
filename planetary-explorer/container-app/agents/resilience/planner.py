"""Hybrid resilience workflow — deterministic DAG + LLM planner loop.

This module bolts a *planner* layer on top of the standard
fan-out/fan-in workflow so the agent can answer queries the static graph
can't (counterfactuals, comparisons, multi-step investigations).

Layout
------

::

    user query ──► RouterExecutor
                       │
                       ├─ "standard" ────► run existing DAG ────┐
                       │                                         │
                       └─ "investigative" ─► PlannerExecutor ───┤
                                                  │ (tool loop) │
                                                  ▼             │
                                            CriticExecutor ◄────┘
                                                  │
                                                  ▼
                                              dossier

The router is one cheap classification call. The planner is a ReAct-style
tool-use loop over the catalogue in :mod:`agents.resilience.tools`.
The critic enforces the response contract — every claim has a citation,
errored tool calls are surfaced, schema matches the API.

Designed to be additive: the existing ``assess_resilience(...)``
entrypoint and standard workflow are untouched. The new entrypoint
is :func:`assess_resilience_smart`.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

try:
    from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler  # type: ignore
    AGENT_FRAMEWORK_AVAILABLE = True
except Exception as exc:  # pragma: no cover
    logger.info("agent_framework not available (%s); planner disabled", exc)
    AGENT_FRAMEWORK_AVAILABLE = False
    Executor = object  # type: ignore
    WorkflowContext = object  # type: ignore
    WorkflowBuilder = None  # type: ignore
    def handler(fn):  # type: ignore
        return fn

try:
    from azure.identity import DefaultAzureCredential, get_bearer_token_provider
    from openai import AsyncAzureOpenAI
    OPENAI_AVAILABLE = True
except Exception:  # pragma: no cover
    OPENAI_AVAILABLE = False
    AsyncAzureOpenAI = None  # type: ignore

from .tools import TOOL_DISPATCH, TOOL_SCHEMAS
from .workflow import assess_resilience


# ─────────────────────────────────────────────────────────────────────────
# Messages passed inside the planner workflow
# ─────────────────────────────────────────────────────────────────────────
@dataclass
class PlannerRequest:
    """Input to the smart workflow."""
    user_query: str
    region_filter: str | None = None
    horizon_days: int = 7
    hazards: list[str] | None = None


@dataclass
class RoutedRequest:
    """Router output — either go through the standard DAG or invoke the planner."""
    request: PlannerRequest
    route: str  # "standard" | "investigative"
    reason: str = ""


@dataclass
class PlannerDossier:
    """Pre-critique output from either path. Same shape as the API response."""
    dossier: dict[str, Any]
    route: str
    tool_trace: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


# ─────────────────────────────────────────────────────────────────────────
# Lazy AOAI client (mirrors clarifier_agent's pattern)
# ─────────────────────────────────────────────────────────────────────────
_client_singleton: "AsyncAzureOpenAI | None" = None


def _get_aoai_client() -> "AsyncAzureOpenAI":
    """Build (and cache) an AOAI client using managed-identity by default."""
    global _client_singleton
    if _client_singleton is not None:
        return _client_singleton
    if not OPENAI_AVAILABLE:
        raise RuntimeError("openai SDK not installed; planner requires it.")
    # Prefer the AOAI data-plane endpoint. The AI Foundry project endpoint
    # (AZURE_AI_PROJECT_ENDPOINT, https://*.services.ai.azure.com/api/projects/...)
    # is a different service and AsyncAzureOpenAI cannot speak to it — using
    # it returns 401 "audience is incorrect (https://ai.azure.com)" because
    # Foundry routes through a different token audience and API surface.
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT") or os.getenv("AZURE_AI_PROJECT_ENDPOINT")
    if not endpoint:
        raise RuntimeError(
            "PlannerExecutor requires AZURE_OPENAI_ENDPOINT (or AZURE_AI_PROJECT_ENDPOINT)."
        )
    api_key = os.getenv("AZURE_OPENAI_API_KEY") or None
    token_provider = None
    if not api_key:
        token_provider = get_bearer_token_provider(
            DefaultAzureCredential(),
            "https://cognitiveservices.azure.com/.default",
        )
    _client_singleton = AsyncAzureOpenAI(
        azure_endpoint=endpoint,
        api_key=api_key,
        azure_ad_token_provider=token_provider,
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview"),
    )
    return _client_singleton


def _planner_deployment() -> str:
    return os.getenv(
        "AZURE_OPENAI_RESILIENCE_PLANNER_DEPLOYMENT",
        os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5"),
    )


# ─────────────────────────────────────────────────────────────────────────
# RouterExecutor — cheap intent classification
# ─────────────────────────────────────────────────────────────────────────
ROUTER_SYSTEM = """You are a router for a facility-resilience agent.

Default to "investigative" — the planner produces a richer, more grounded
answer for almost every real user question because it can cross-reference
Fabric (facilities, supply chain, BCP playbooks) with the Microsoft
Planetary Computer STAC catalogue (recent imagery, fire perimeters,
vegetation, land cover) before answering.

Only route to "standard" when the query is a literal one-shot dump with
no qualifiers, e.g.:
  - "Run the standard 7-day TX heat + wildfire check."
  - "Refresh the dossier."
  - "Recompute risk for all facilities."

Everything else — including a bare "What's at risk in Texas this week?" —
is "investigative" because the planner can choose the right MPC
collections, pull facility metadata, and synthesise a conversational
answer instead of returning only a table.

Respond with ONLY a JSON object: {"route": "standard"|"investigative", "reason": "..."}"""


class RouterExecutor(Executor):  # type: ignore[misc]
    """One LLM call to pick the path. Falls back to 'standard' on error."""

    def __init__(self, id: str = "router") -> None:
        if AGENT_FRAMEWORK_AVAILABLE:
            super().__init__(id=id)
        self.id = id

    if AGENT_FRAMEWORK_AVAILABLE:
        @handler  # type: ignore
        async def on_message(
            self,
            request: PlannerRequest,
            ctx: WorkflowContext[RoutedRequest],
        ) -> None:
            route, reason = await self._classify(request.user_query)
            await ctx.send_message(RoutedRequest(request=request, route=route, reason=reason))

    async def _classify(self, query: str) -> tuple[str, str]:
        try:
            client = _get_aoai_client()
            # NOTE: gpt-5 requires ``max_completion_tokens`` (not ``max_tokens``)
            # and only accepts the default temperature; passing ``temperature``
            # or ``max_tokens`` to gpt-5 returns HTTP 400 unsupported_parameter.
            resp = await client.chat.completions.create(
                model=_planner_deployment(),
                messages=[
                    {"role": "system", "content": ROUTER_SYSTEM},
                    {"role": "user", "content": query},
                ],
                response_format={"type": "json_object"},
                max_completion_tokens=200,
            )
            payload = json.loads(resp.choices[0].message.content or "{}")
            route = payload.get("route") or "standard"
            if route not in ("standard", "investigative"):
                route = "standard"
            return route, str(payload.get("reason") or "")
        except Exception as exc:  # noqa: BLE001 — never block the workflow on routing
            # Default to investigative: the planner is more useful than the
            # deterministic DAG for almost every real query, and it degrades
            # gracefully (worst case it just calls run_standard_assessment).
            logger.warning("[RESILIENCE.router] classification failed (%s); defaulting to investigative", exc)
            return "investigative", f"router error: {exc}"


# ─────────────────────────────────────────────────────────────────────────
# StandardPathExecutor — invokes the existing DAG when the router said so
# ─────────────────────────────────────────────────────────────────────────
class StandardPathExecutor(Executor):  # type: ignore[misc]
    """Thin shim that runs the existing fan-out/fan-in workflow.

    Lets us keep the deterministic path on a separate edge so the
    planner-loop graph isn't entangled with it.
    """

    def __init__(self, id: str = "standard_path") -> None:
        if AGENT_FRAMEWORK_AVAILABLE:
            super().__init__(id=id)
        self.id = id

    if AGENT_FRAMEWORK_AVAILABLE:
        @handler  # type: ignore
        async def on_message(
            self,
            routed: RoutedRequest,
            ctx: WorkflowContext[PlannerDossier],
        ) -> None:
            # Fan-in critic waits for one message from EACH upstream node.
            # If we early-return without sending, the workflow deadlocks /
            # produces no outputs. So the non-matching branch must emit a
            # ``skipped`` marker that the critic recognises and discards.
            if routed.route != "standard":
                await ctx.send_message(
                    PlannerDossier(dossier={}, route="skipped", error="standard_path_skipped")
                )
                return
            req = routed.request
            try:
                dossier = await assess_resilience(
                    user_assertion=req.user_query,
                    region_filter=req.region_filter,
                    horizon_days=req.horizon_days,
                    hazards=req.hazards,
                    user_query=req.user_query,
                )
                await ctx.send_message(PlannerDossier(dossier=dossier, route="standard"))
            except Exception as exc:  # noqa: BLE001
                logger.exception("[RESILIENCE.standard_path] assess_resilience failed")
                await ctx.send_message(
                    PlannerDossier(
                        dossier={
                            "summary": f"Standard assessment failed: {exc}",
                            "facilities": [],
                            "provenance": [],
                        },
                        route="standard",
                        error=str(exc),
                    )
                )


# ─────────────────────────────────────────────────────────────────────────
# PlannerExecutor — ReAct-style tool-use loop
# ─────────────────────────────────────────────────────────────────────────
PLANNER_SYSTEM = """You are an investigative resilience analyst. You combine
two grounded data sources to answer the user:

  A) **Microsoft Fabric (Lakehouse)** — the customer's own facility
     registry, supply edges, and BCP playbooks. Reached through:
       * `query_facilities`        — list facilities by region / type /
                                     criticality (no scoring)
       * `run_standard_assessment` — score a region's facilities over a
                                     horizon (heat, wildfire) using
                                     Open-Meteo forecasts + criticality
       * `simulate_outage`         — multi-hop supply-chain blast radius
       * `compare_periods`         — diff two assessment windows
       * `find_similar_facilities` — match by type/criticality
       * `search_playbooks`        — BCP runbook lookup

  B) **Microsoft Planetary Computer (public STAC)** — open Earth-observation
     catalogue. Reached through:
       * `list_mpc_stac_collections`   — discover what imagery exists
       * `search_mpc_stac_items`       — find scenes for a bbox + datetime
                                         range inside a collection
       * `get_mpc_collection_details`  — extent, assets, render options

You decide per turn which sources are needed. The two are complementary:
Fabric tells you *which* sites matter; MPC tells you *what's happening on
the ground around them*.

HARD RULES — do not violate these:

* NEVER ask the user clarifying questions. The tools can answer for you.
* NEVER reply with prose that ends in a question to the user.
* NEVER ask the user to upload, paste, share, or "send over" CSVs,
  facility lists, lane maps, volumes, SLAs, surge capacity, transport
  modes, or any other supply-chain data. **All of that data already lives
  in the Fabric lakehouse.** Use the tools to read it:
    - "which facilities depend on X?" → `simulate_outage(facility_id=X)`
      returns the downstream blast radius (every cascade, every lane).
    - "what facilities are in region Y?" → `query_facilities(region_filter=Y)`.
    - "what's the recommended workaround / runbook?" → `search_playbooks(...)`.
  If the user mentions a facility by name or city (e.g. "Houston port
  distribution center"), call `query_facilities` first to resolve it to
  a facility id, then `simulate_outage` on that id.
* NEVER fabricate facility names, IDs, scores, collection ids, or scene
  ids. Every entity in your answer must come from a tool result.
* When you cite imagery, use the *exact* STAC `collection` id returned by
  `list_mpc_stac_collections`. Never guess collection names from memory —
  pick the best match from the live catalogue.

Dynamic collection routing (when you need MPC imagery):

  1. Call `list_mpc_stac_collections` ONCE per turn to see what's
     available. (Result is small and cached at the server.)
  2. Pick the collection whose `title` / `description` / `keywords` best
     match the user's intent:
        * "fire" / "burn scar" / "wildfire perimeter" → look for
          "fire", "burn", "mtbs" in the catalogue
        * "vegetation" / "drought" / "greenness"     → look for
          "ndvi", "modis vegetation", "hls"
        * "land cover" / "imperviousness"            → look for
          "esa worldcover", "nlcd", "io-lulc"
        * "recent optical" / "see the area"          → "sentinel-2-l2a",
          "naip", "landsat-c2-l2"
        * "weather radar" / "precip"                 → "noaa-mrms-qpe",
          "goes-cmi"
        * "elevation"                                → "cop-dem-glo-30",
          "nasadem"
  3. If you're not sure, search the top 2 candidate collections with a
     small `limit` and pick the one that actually returned items.
  4. ALWAYS attach a tight `bbox` derived from the facility lat/lng
     (±0.25° is a reasonable default for a single site, ±1° for a region)
     and a relevant `datetime_range` (last 30 days for "current
     conditions", last 90 days for "recent trends").

Recommended workflow for a typical investigative question:

  Step 1 — Frame the question. If the user named a region / type, call
            `query_facilities` to get the candidate set.
  Step 2 — Score the candidates. Call `run_standard_assessment` with the
            region + hazards. This gives you heat/wildfire scores plus
            facility metadata in one shot.
  Step 3 — Ground-truth with MPC where it adds signal:
            * Wildfire question → `list_mpc_stac_collections`, pick a
              fire / hot-spot collection, `search_mpc_stac_items` over a
              bbox covering the highest-risk facilities.
            * Heat / cooling-water question → recent NDVI or Landsat
              thermal items over the bbox to confirm vegetation stress.
            * Outage / port question → recent optical imagery to see if
              the asset is operational, then `simulate_outage`.
  Step 4 — If runbooks / mitigations / playbooks were asked for, call
            `search_playbooks`.
  Step 5 — Stop calling tools and answer.

Stop calling tools as soon as adding a tool wouldn't change the answer.
A good answer usually needs 2–5 tool calls, not 6.

OUTPUT CONTRACT — return a single JSON object, no markdown fences:

  {
    "summary":   "one-sentence headline answer (plain text, no markdown)",
    "narrative": "the full conversational answer in markdown — see below",
    "facilities":  [...],   // ranked subset relevant to the question
    "provenance":  [...]    // aggregate of every tool's provenance array
  }

The `narrative` is the answer the user actually reads in the chat panel.
Write it as you would write a short, professional Slack reply:

  * Short paragraphs and bullet lists only. NEVER use markdown tables
    (no `|` pipes, no `---|---` separator rows). The chat panel is
    narrow and tables render as an unreadable wall of pipes.
  * Prefer bullets when comparing facilities. Each facility = one
    top-level bullet (`- **Facility Name** — risk NN · SEVERITY`) with
    1–3 indented sub-bullets for peak / driver / cascade impact.
  * Lead with the bottom line in the first sentence BEFORE the bullets.
  * Name specific facilities by their `name` field, not their id.
  * Inline-cite numbers from tools: e.g. "Austin Fab 3 hits 108 °F on
    Thursday (score 78/100)". Cite MPC scenes by collection id and date.
  * If you used MPC imagery, say WHICH collection and WHY it was the right
    one (e.g. "Sentinel-2 L2A from May 24 confirms no active smoke plume
    over the bbox"). This shows the user the planner reasoned about
    collection choice.
  * Close with a one-line recommendation when appropriate ("Consider
    pre-positioning chillers at Round Rock DC; lead time 2 days.").
  * Keep it scannable. Do not dump raw JSON. Do not say "the tool
    returned…" — write as a human analyst.

If a tool returns an error you cannot route around, set `summary` and
`narrative` to a clear, honest explanation of what's missing and still
return a valid JSON dossier."""

MAX_TOOL_HOPS = 8

# Minimum length of a non-degenerate narrative. If the planner returns
# something shorter, we run a second LLM pass that synthesises a proper
# chat-friendly answer from the gathered evidence so the UI always has a
# human-readable message to render.
MIN_NARRATIVE_CHARS = 220


class PlannerExecutor(Executor):  # type: ignore[misc]
    """LLM planner with tool-use loop. Runs only when router said 'investigative'."""

    def __init__(self, id: str = "planner") -> None:
        if AGENT_FRAMEWORK_AVAILABLE:
            super().__init__(id=id)
        self.id = id

    if AGENT_FRAMEWORK_AVAILABLE:
        @handler  # type: ignore
        async def on_message(
            self,
            routed: RoutedRequest,
            ctx: WorkflowContext[PlannerDossier],
        ) -> None:
            # See StandardPathExecutor: the non-matching branch must still
            # emit so the fan-in critic doesn't deadlock.
            if routed.route != "investigative":
                await ctx.send_message(
                    PlannerDossier(dossier={}, route="skipped", error="planner_skipped")
                )
                return
            try:
                dossier, trace, err = await self._plan(routed.request)
                # Critic-style finalize: guarantee a chat-quality narrative
                # before handing off to the next executor. Cheap LLM call,
                # only fires when the planner under-filled the field.
                dossier = await self._ensure_narrative(routed.request, dossier, trace)
            except Exception as exc:  # noqa: BLE001
                logger.exception("[RESILIENCE.planner] _plan crashed")
                dossier = {
                    "summary": f"Planner crashed: {exc}",
                    "facilities": [],
                    "provenance": [],
                }
                trace = []
                err = str(exc)
            await ctx.send_message(
                PlannerDossier(dossier=dossier, route="investigative", tool_trace=trace, error=err)
            )

    async def _plan(
        self, req: PlannerRequest
    ) -> tuple[dict[str, Any], list[dict[str, Any]], str | None]:
        """Run the tool-call loop. Returns (dossier, trace, error_or_None)."""
        try:
            client = _get_aoai_client()
        except Exception as exc:  # noqa: BLE001
            return ({"summary": f"Planner unavailable: {exc}", "facilities": [], "provenance": []}, [], str(exc))

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": PLANNER_SYSTEM},
            {"role": "user", "content": req.user_query},
        ]
        trace: list[dict[str, Any]] = []

        for hop in range(MAX_TOOL_HOPS):
            # On the first hop, force the model to call a tool. Without
            # this the LLM occasionally bails with prose like "share your
            # CSV" instead of using `query_facilities` / `simulate_outage`.
            # After the first hop, let it decide when it's done.
            tool_choice: Any = "required" if hop == 0 else "auto"
            resp = await client.chat.completions.create(
                model=_planner_deployment(),
                messages=messages,
                tools=TOOL_SCHEMAS,
                tool_choice=tool_choice,
            )
            msg = resp.choices[0].message
            messages.append(msg.model_dump(exclude_none=True))

            tool_calls = getattr(msg, "tool_calls", None) or []
            if not tool_calls:
                # Model decided it's done — parse the final answer.
                final_text = msg.content or ""
                dossier = _parse_final_dossier(final_text)
                return dossier, trace, None

            for call in tool_calls:
                name = call.function.name
                try:
                    args = json.loads(call.function.arguments or "{}")
                except json.JSONDecodeError as exc:
                    args = {}
                    logger.warning("[RESILIENCE.planner] bad tool args (%s): %s", name, exc)

                fn = TOOL_DISPATCH.get(name)
                if fn is None:
                    result: dict[str, Any] = {"error": f"unknown tool: {name}"}
                else:
                    try:
                        result = await fn(**args)
                    except Exception as exc:  # noqa: BLE001
                        logger.exception("[RESILIENCE.planner] tool %s raised", name)
                        result = {"error": f"{name} raised: {exc}"}

                trace.append({"hop": hop, "tool": name, "args": args, "result_keys": list(result.keys())})
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "name": name,
                    "content": json.dumps(result, default=str)[:12000],
                })

        # Hop budget exhausted — ask the model to finalise without more tools.
        messages.append({
            "role": "user",
            "content": "You've hit the tool-call budget. Produce the final JSON dossier now.",
        })
        resp = await client.chat.completions.create(
            model=_planner_deployment(),
            messages=messages,
        )
        return _parse_final_dossier(resp.choices[0].message.content or ""), trace, "tool_budget_exhausted"

    async def _ensure_narrative(
        self,
        req: PlannerRequest,
        dossier: dict[str, Any],
        trace: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Synthesize a chat-quality markdown narrative from the dossier.

        The main planner loop already asks for a ``narrative`` field, but
        models sometimes return only a `summary` + a facility table or
        truncate the narrative to a single sentence. This second pass runs
        a tiny LLM call that turns the structured evidence into the
        conversational answer the chat panel renders. Cheap, deterministic
        prompt; bounded to one round-trip.
        """
        existing = (dossier.get("narrative") or "").strip()
        if len(existing) >= MIN_NARRATIVE_CHARS:
            return dossier

        try:
            client = _get_aoai_client()
        except Exception:  # noqa: BLE001 — fall back silently to whatever we have
            dossier.setdefault("narrative", existing or (dossier.get("summary") or ""))
            return dossier

        # Compact evidence packet — names of tools called, top facilities,
        # any MPC scenes cited. We don't dump the full dossier because the
        # synthesiser doesn't need it.
        facilities = (dossier.get("facilities") or [])[:8]
        compact = {
            "user_query": req.user_query,
            "region_filter": req.region_filter,
            "horizon_days": req.horizon_days,
            "hazards": req.hazards,
            "headline": dossier.get("summary") or "",
            "tools_used": [t.get("tool") for t in trace if t.get("tool")],
            "top_facilities": [
                {
                    "name": f.get("name") or f.get("facility_id"),
                    "type": f.get("type"),
                    "region": f.get("region"),
                    "overall_risk": f.get("overall_risk"),
                    "severity": f.get("severity"),
                    "hazards": (f.get("hazards") or {}),
                }
                for f in facilities
            ],
            "provenance_sources": sorted(
                {p.get("source") for p in (dossier.get("provenance") or []) if p.get("source")}
            ),
            "existing_narrative": existing,
        }

        synth_system = (
            "You are a senior resilience analyst. Write a SHORT, scannable, "
            "human-friendly markdown answer to the user's question based on "
            "the structured evidence below. Rules:\n"
            "  * Use ONLY short paragraphs and bullet lists. NEVER use markdown "
            "    tables (no `|` pipes, no `---|---` separator rows). Tables do "
            "    not render in the chat panel.\n"
            "  * Structure: bullet list FIRST (the breakdown), then a closing "
            "    paragraph LAST that directly answers the user's question in "
            "    plain prose. The closing paragraph is mandatory and must "
            "    explicitly restate the answer (e.g. 'If Houston DC goes "
            "    offline for 48h, Corpus Christi DC and San Antonio Assembly "
            "    are the two downstream sites exposed; the recommended "
            "    workaround is to re-route via …').\n"
            "  * Do NOT include a 'Sources' / 'Evidence' / 'Citations' section "
            "    — the UI renders citations separately from the structured "
            "    provenance list. Just write the analysis.\n"
            "  * Prefer a tight bulleted list when comparing facilities. Each "
            "    facility = one top-level bullet (`- **Facility Name** — risk "
            "    NN · SEVERITY`) with 1–3 indented sub-bullets for peak, driver, "
            "    and cascade impact.\n"
            "  * Name facilities by name. Cite numbers (risk score, peak value, "
            "    peak day). Never invent facilities or scores.\n"
            "  * If any MPC STAC collections were queried (tools starting with "
            "    `list_mpc_stac_collections`, `search_mpc_stac_items`, or "
            "    `get_mpc_collection_details`), mention WHICH collection was used "
            "    and why it was the right choice for the question.\n"
            "  * NEVER ask the user a question.\n"
            "  * Output: plain markdown only. No JSON, no code fences, no tables, "
            "    no inline source links."
        )
        try:
            resp = await client.chat.completions.create(
                model=_planner_deployment(),
                messages=[
                    {"role": "system", "content": synth_system},
                    {"role": "user", "content": json.dumps(compact, default=str)[:8000]},
                ],
                max_completion_tokens=900,
            )
            text = (resp.choices[0].message.content or "").strip()
            if text:
                dossier["narrative"] = text
        except Exception as exc:  # noqa: BLE001
            logger.warning("[RESILIENCE.planner] narrative synthesis failed: %s", exc)
            dossier.setdefault("narrative", existing or (dossier.get("summary") or ""))
        return dossier


def _parse_final_dossier(text: str) -> dict[str, Any]:
    """Extract the final JSON dossier from the model's last message."""
    text = (text or "").strip()
    # Strip ```json fences if present.
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            parsed.setdefault("summary", "")
            parsed.setdefault("facilities", [])
            parsed.setdefault("provenance", [])
            return parsed
    except json.JSONDecodeError:
        pass
    return {
        "summary": text[:400] if text else "Planner produced no parseable answer.",
        "facilities": [],
        "provenance": [],
        "narrative": text,
    }


# ─────────────────────────────────────────────────────────────────────────
# CriticExecutor — validate the dossier before yielding it out
# ─────────────────────────────────────────────────────────────────────────
class CriticExecutor(Executor):  # type: ignore[misc]
    """Cheap validation pass: enforce schema, dedup provenance, surface tool errors."""

    def __init__(self, id: str = "critic") -> None:
        if AGENT_FRAMEWORK_AVAILABLE:
            super().__init__(id=id)
        self.id = id

    if AGENT_FRAMEWORK_AVAILABLE:
        @handler  # type: ignore
        async def on_message(
            self,
            messages: list[Any],
            ctx: WorkflowContext[Any, dict[str, Any]],
        ) -> None:
            # Fan-in: messages is a list of PlannerDossier emissions from
            # standard_path and planner. Exactly one of the two will carry
            # the real dossier; the other emits a ``skipped`` marker so the
            # fan-in always fires. Pick the non-skipped one.
            payload: PlannerDossier | None = None
            for msg in messages or []:
                if isinstance(msg, PlannerDossier) and msg.route != "skipped":
                    payload = msg
                    break
            if payload is None:
                # Both branches skipped (router produced an unknown route) or
                # they all failed silently — yield a clear diagnostic dossier.
                await ctx.yield_output({
                    "summary": "Resilience workflow produced no output.",
                    "facilities": [],
                    "provenance": [],
                    "route": "unknown",
                    "planner_warning": "no_dossier_from_router_branches",
                })
                return

            dossier = dict(payload.dossier or {})
            dossier.setdefault("summary", "")
            dossier.setdefault("facilities", [])
            dossier.setdefault("provenance", [])
            dossier["route"] = payload.route
            if payload.tool_trace:
                dossier["tool_trace"] = payload.tool_trace
            if payload.error:
                dossier["planner_warning"] = payload.error

            # Dedup provenance by (source, lakehouse, index) signature.
            seen: set[tuple[Any, ...]] = set()
            deduped: list[dict[str, Any]] = []
            for p in dossier["provenance"] or []:
                key = (p.get("source"), p.get("lakehouse"), p.get("index"), p.get("endpoint"))
                if key in seen:
                    continue
                seen.add(key)
                # Drop AI-Search rows that errored or returned 0 hits with no index.
                if p.get("source") == "ai_search" and (p.get("error") or p.get("skipped")):
                    continue
                deduped.append(p)
            dossier["provenance"] = deduped

            # Terminal node — yield_output so the workflow result picks it up.
            await ctx.yield_output(dossier)


# ─────────────────────────────────────────────────────────────────────────
# Workflow assembly + public entrypoint
# ─────────────────────────────────────────────────────────────────────────
def _build_smart_workflow():
    """Construct the hybrid router → (standard | planner) → critic graph."""
    if not AGENT_FRAMEWORK_AVAILABLE:
        raise RuntimeError("agent_framework not available")

    router = RouterExecutor()
    standard = StandardPathExecutor()
    planner = PlannerExecutor()
    critic = CriticExecutor()

    builder = WorkflowBuilder(start_executor=router)
    # Router fans out to BOTH handlers; each one is a no-op for the
    # route it doesn't own. (Conditional edges would be cleaner but
    # require a newer MAF; this is portable.)
    builder = builder.add_fan_out_edges(router, [standard, planner])
    builder = builder.add_fan_in_edges([standard, planner], critic)
    return builder.build()


async def assess_resilience_smart(
    *,
    user_query: str,
    region_filter: str | None = None,
    horizon_days: int = 7,
    hazards: list[str] | None = None,
) -> dict[str, Any]:
    """Hybrid entrypoint — router classifies, then standard DAG or planner runs.

    Returns the same dossier shape as :func:`assess_resilience` plus:

      - ``route``: "standard" | "investigative"
      - ``tool_trace`` (planner runs only): list of tool calls + arg keys
      - ``planner_warning`` (optional): set if the planner hit a budget or error

    The standard route is byte-for-byte identical to today's API contract
    so existing callers can swap entrypoints with no other changes.
    """
    if not AGENT_FRAMEWORK_AVAILABLE:
        raise RuntimeError(
            "assess_resilience_smart requires Microsoft Agent Framework."
        )
    workflow = _build_smart_workflow()
    request = PlannerRequest(
        user_query=user_query,
        region_filter=region_filter,
        horizon_days=horizon_days,
        hazards=hazards,
    )
    result = await workflow.run(request)
    outputs = result.get_outputs()
    if not outputs:
        raise RuntimeError("smart workflow produced no outputs")
    return outputs[-1]
