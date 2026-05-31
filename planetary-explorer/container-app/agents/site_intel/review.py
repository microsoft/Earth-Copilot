"""Post-aggregation executors: EvidenceExecutor and ReviewExecutor.

These nodes chain serially *after* :class:`AggregatorExecutor` so the dossier
is progressively enriched before being yielded as the workflow output.

Topology
--------
::

    Aggregator ──► Evidence ──► Review ──► (yield_output)

Both are no-ops when their feature flags are off — they pass the dossier
through untouched. This keeps the graph shape constant across deployments
(so the same workflow object can be reused) while letting us roll the
features out independently.

Feature flags
~~~~~~~~~~~~~
``SITE_EVIDENCE=1``
    Walk every ``evidence`` entry, pull stable IDs (``id``, ``site_id``,
    ``item_id``, ``substation_id`` …) and attach a ``sources`` block to
    each dimension under ``data_provenance``. Pure data shaping — no
    external calls — so it's safe to leave on by default once verified.

``SITE_REVIEW=1``
    LLM critique pass over the assembled dossier. Returns
    ``review = {confidence, concerns: [...], next_steps: [...]}`` so the
    UI can render a "What to validate next" panel. Fails open: any LLM
    error leaves the dossier untouched and logs a warning.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

try:
    from agent_framework import Executor, WorkflowContext, handler  # type: ignore
    from typing_extensions import Never  # type: ignore
    AGENT_FRAMEWORK_AVAILABLE = True
except Exception as exc:  # pragma: no cover
    logger.info("agent_framework not available (%s); review executors are stubs", exc)
    AGENT_FRAMEWORK_AVAILABLE = False
    Executor = object  # type: ignore
    handler = lambda f: f  # type: ignore  # noqa: E731
    Never = None  # type: ignore

    class WorkflowContext:  # type: ignore
        """Stand-in so type hints resolve at import time."""


# Evidence keys we recognize as stable source identifiers across the three
# upstream sources (Fabric Lakehouse, Planetary Computer STAC, AI Search).
_ID_KEYS = ("id", "site_id", "substation_id", "asset_id", "item_id", "doc_id", "url")


def _extract_source_ids(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pull stable identifiers out of raw evidence rows.

    Returns one ``{kind, id}`` record per evidence row that has any
    recognizable identifier; rows without identifiers are dropped.
    """
    sources: list[dict[str, Any]] = []
    for ev in evidence:
        if not isinstance(ev, dict):
            continue
        kind = ev.get("kind") or ev.get("source") or "evidence"
        for k in _ID_KEYS:
            if k in ev and ev[k]:
                sources.append({"kind": kind, "field": k, "id": ev[k]})
                break
    return sources


# ──────────────────────────────────────────────────────────────────────────────
# EvidenceExecutor
# ──────────────────────────────────────────────────────────────────────────────
class EvidenceExecutor(Executor):  # type: ignore[misc]
    """Enrich each provenance block with per-dimension source IDs.

    Pass-through when ``SITE_EVIDENCE=0``.
    """

    def __init__(self, id: str = "evidence") -> None:
        if AGENT_FRAMEWORK_AVAILABLE:
            super().__init__(id=id)
        self.id = id

    if AGENT_FRAMEWORK_AVAILABLE:
        @handler  # type: ignore
        async def on_message(
            self,
            dossier: dict[str, Any],
            ctx: "WorkflowContext[dict[str, Any]]",
        ) -> None:
            flag = os.getenv("SITE_EVIDENCE", "0").lower() in ("1", "true", "yes", "on")
            if not flag:
                await ctx.send_message(dossier)
                return

            try:
                # Group evidence by its `kind` prefix so we can index by
                # dimension. Most _score_* functions tag their evidence with
                # kind="<dim>_<detail>"; we just group on whatever appears.
                by_kind: dict[str, list[dict[str, Any]]] = {}
                for ev in dossier.get("evidence", []):
                    kind = (ev.get("kind") or "misc").split("_")[0] if isinstance(ev, dict) else "misc"
                    by_kind.setdefault(kind, []).append(ev)

                provenance = list(dossier.get("data_provenance", []))
                # Append a single "sources" entry summarizing all extracted IDs.
                all_sources = _extract_source_ids(dossier.get("evidence", []))
                if all_sources:
                    provenance.append({
                        "source": "evidence_extractor",
                        "sources_by_kind": {
                            k: _extract_source_ids(v) for k, v in by_kind.items()
                        },
                        "total_source_ids": len(all_sources),
                    })
                dossier = {**dossier, "data_provenance": provenance}
            except Exception as exc:  # noqa: BLE001
                logger.warning("[EVIDENCE] enrichment failed (%s); passing through", exc)

            await ctx.send_message(dossier)


# ──────────────────────────────────────────────────────────────────────────────
# ReviewExecutor
# ──────────────────────────────────────────────────────────────────────────────
_REVIEW_SYSTEM_PROMPT = """\
You are a senior utility-siting reviewer (substations, transmission,
generation, BESS, interconnection). You have been handed a Site Intel
dossier (scores + summaries across power / water / hazards / competition /
parcel_match / precedent). Produce a brief critique:

  • confidence: "low" | "medium" | "high" — your confidence in the overall score
  • concerns: 1–3 short bullets calling out the weakest signal, contradictions,
    or interconnection / permitting risks the data may have missed
  • next_steps: 1–3 short bullets the user should validate before filing an
    interconnection request or permit application

Be terse. Each bullet ≤120 chars. Reply with JSON only.
"""

_REVIEW_SCHEMA: dict[str, Any] = {
    "name": "SiteIntelReview",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
            "concerns": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
            "next_steps": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
        },
        "required": ["confidence", "concerns", "next_steps"],
    },
}


async def _llm_review(dossier: dict[str, Any]) -> dict[str, Any]:
    """Run the critique LLM. Raises on any error."""
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

    deployment = os.getenv("SITE_REVIEW_DEPLOYMENT") or os.getenv(
        "AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5"
    )
    # Trim the dossier we send to the model — we only want scores + summaries,
    # not the full evidence dump (which is large and not needed for critique).
    compact = {
        "scores": dossier.get("scores"),
        "summaries": dossier.get("summaries"),
        "skipped_dimensions": dossier.get("skipped_dimensions"),
        "planner": dossier.get("planner"),
    }
    response = await client.chat.completions.create(
        model=deployment,
        messages=[
            {"role": "system", "content": _REVIEW_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(compact, default=str)},
        ],
        response_format={"type": "json_schema", "json_schema": _REVIEW_SCHEMA},
        temperature=0.0,
        reasoning_effort="minimal",
    )
    return json.loads(response.choices[0].message.content or "{}")


class ReviewExecutor(Executor):  # type: ignore[misc]
    """Run an LLM critique pass over the assembled dossier and yield the
    final enriched dossier as the workflow output.

    Always emits :meth:`WorkflowContext.yield_output` at the end (whether or
    not the critique succeeded) so this node terminates the workflow.
    """

    def __init__(self, id: str = "review") -> None:
        if AGENT_FRAMEWORK_AVAILABLE:
            super().__init__(id=id)
        self.id = id

    if AGENT_FRAMEWORK_AVAILABLE:
        @handler  # type: ignore
        async def on_message(
            self,
            dossier: dict[str, Any],
            ctx: "WorkflowContext[Never, dict[str, Any]]",
        ) -> None:
            flag = os.getenv("SITE_REVIEW", "0").lower() in ("1", "true", "yes", "on")
            if flag:
                try:
                    review = await _llm_review(dossier)
                    dossier = {**dossier, "review": review}
                except Exception as exc:  # noqa: BLE001
                    logger.warning("[REVIEW] critique failed (%s); skipping", exc)
                    dossier = {**dossier, "review": {"error": str(exc)}}
            await ctx.yield_output(dossier)
