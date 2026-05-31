"""Dynamic collection selector (Phase 2 of MCPProobjective.md).

The selector is the **only** code path that decides which STAC collection
id and render preset a chat query maps to. It consumes the live inventory
exposed by :mod:`collection_index` and a single LLM call constrained to
the top-K candidates -- no hardcoded keyword tables, no regex, no static
allow-lists.

Pipeline (4 stages):

  Stage A -- Exact-id short-circuit
      Tokenize the query; for each token, ask ``CollectionIndex.lookup_exact``.
      Only ids that exist in the live inventory pass. ``"sentinel-2"`` (a
      lookalike) is rejected; ``"sentinel-2-l2a"`` (a real id) wins
      immediately.

  Stage B -- Semantic / lexical retrieval
      ``CollectionIndex.search(query, mode, k=8)`` returns the top-K rows
      ranked by cosine over embeddings (when AOAI embeddings are enabled)
      or by a deterministic lexical scorer (otherwise).

  Stage C -- LLM pick (constrained)
      One ``AsyncAzureOpenAI`` chat call with a strict JSON schema:
      ``{"collection_id": <one of cand ids>, "render_preset": <one of
      that cand's renders.keys() or null>, "rationale": str}``.
      The LLM is given ONLY the top-K candidate ids, titles, descriptions,
      and their available render presets. It cannot invent an id.

  Stage D -- Sanity guard
      Assert the returned ``collection_id`` is in the top-K. On any LLM
      failure or guard violation, fall back to the top-1 candidate from
      Stage B with a deterministic preset chosen by token overlap.

Feature flag :func:`selector_mode` reads ``COLLECTION_SELECTOR``:

  ``off``     -- selector is dormant (Phase 1 default).
  ``shadow``  -- selector runs alongside the legacy pipeline; both picks
                  are logged via :func:`record_shadow_decision` but the
                  legacy v1 result is still authoritative.
  ``v2``      -- selector is authoritative (Phase 3+).

This module does **not** import the legacy routing layers (keyword_map,
INTENT_TO_COLLECTIONS, etc.) -- by design, removing them later cannot
break the selector.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from collection_index import (
    Candidate,
    CollectionIndex,
    CollectionMeta,
    get_collection_index,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Alternative:
    """One disambiguation candidate surfaced to the user.

    Used when :class:`Selection` has ``needs_confirmation=True``. Each
    alternative is safe to send to the UI verbatim: the chat layer can
    render the ``title`` as a chip label and store ``collection_id`` as
    the deterministic slot value when the user clicks.
    """

    collection_id: str
    title: str
    description: str  # already truncated to ~160 chars
    score: float
    render_preset: Optional[str]

    def to_log(self) -> Dict[str, Any]:
        return {
            "collection_id": self.collection_id,
            "title": self.title,
            "score": round(self.score, 3),
            "render_preset": self.render_preset,
        }


@dataclass(frozen=True)
class Selection:
    """Outcome of one :func:`select_collection` call."""

    collection_id: Optional[str]
    render_preset: Optional[str]
    stage: str  # "exact" | "llm" | "fallback" | "disambiguate" | "none"
    reason: str
    candidates: Tuple[str, ...] = field(default_factory=tuple)
    rationale: str = ""
    elapsed_ms: float = 0.0
    # Phase 3 -- confidence + disambiguation
    confidence: float = 0.0  # top-1 score, normalized 0..1 when available
    needs_confirmation: bool = False
    alternatives: Tuple[Alternative, ...] = field(default_factory=tuple)

    def to_log(self) -> Dict[str, Any]:
        return {
            "collection_id": self.collection_id,
            "render_preset": self.render_preset,
            "stage": self.stage,
            "reason": self.reason,
            "candidates": list(self.candidates),
            "rationale": self.rationale,
            "elapsed_ms": round(self.elapsed_ms, 1),
            "confidence": round(self.confidence, 3),
            "needs_confirmation": self.needs_confirmation,
            "alternatives": [a.to_log() for a in self.alternatives],
        }


# ---------------------------------------------------------------------------
# Feature flag
# ---------------------------------------------------------------------------

_VALID_MODES = ("off", "shadow", "v2")


def selector_mode() -> str:
    """Return one of ``off`` | ``shadow`` | ``v2`` (lower-case)."""
    val = (os.getenv("COLLECTION_SELECTOR") or "off").strip().lower()
    return val if val in _VALID_MODES else "off"


# ---------------------------------------------------------------------------
# Tokenization helpers (kept tiny -- the index handles all real matching)
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9._-]{1,}")


def _candidate_tokens(query: str) -> List[str]:
    """Yield substrings that *could* be a collection id.

    We don't try to be clever: every alphanumeric run is a candidate,
    plus contiguous hyphen-joined runs (e.g. ``sentinel-2-l2a``). The
    inventory check in Stage A is what filters out the noise.
    """
    if not query:
        return []
    tokens = _TOKEN_RE.findall(query)
    seen: set[str] = set()
    out: List[str] = []
    for t in tokens:
        lo = t.lower()
        if lo in seen:
            continue
        seen.add(lo)
        out.append(lo)
    # Also try the whole-query slugified form (collapse whitespace to '-')
    slug = "-".join(t.lower() for t in tokens)
    if slug and slug not in seen:
        out.append(slug)
    return out


def _default_preset(meta: CollectionMeta, query: str) -> Optional[str]:
    """Pick a render preset from the collection's ``renders`` by token overlap.

    Used by Stage A (exact-id) and Stage D (fallback) when there's no LLM
    pick to consult. Returns ``None`` when the collection has no presets
    or none of them lexically match the query.
    """
    presets = meta.render_presets
    if not presets:
        return None
    q_lo = query.lower()
    # Heuristic scoring: prefer presets whose name tokens appear in the query.
    best_name: Optional[str] = None
    best_score = 0
    for name in presets:
        score = sum(1 for chunk in name.lower().replace("_", "-").split("-") if chunk and chunk in q_lo)
        if score > best_score:
            best_score = score
            best_name = name
    if best_name is not None and best_score > 0:
        return best_name
    # No preset name matched -- return the conventional default if present.
    for default_name in ("natural-color", "true-color", "rgb", "default"):
        if default_name in presets:
            return default_name
    return presets[0]


# ---------------------------------------------------------------------------
# Confidence + disambiguation (Phase 3)
# ---------------------------------------------------------------------------

# Defaults are tuned for the lexical-fallback scorer (weighted-Jaccard,
# typical winning scores 0.05--0.20). When AOAI embeddings are enabled the
# scorer is cosine-similarity (0..1), so override via env in that env.
_DEFAULT_CONFIDENCE_THRESHOLD = 0.06
_DEFAULT_TIE_THRESHOLD = 0.015
_ALT_DESC_MAX = 160


def _confidence_threshold() -> float:
    try:
        return float(os.getenv("COLLECTION_SELECTOR_CONFIDENCE_THRESHOLD")
                     or _DEFAULT_CONFIDENCE_THRESHOLD)
    except (TypeError, ValueError):
        return _DEFAULT_CONFIDENCE_THRESHOLD


def _tie_threshold() -> float:
    try:
        return float(os.getenv("COLLECTION_SELECTOR_TIE_THRESHOLD")
                     or _DEFAULT_TIE_THRESHOLD)
    except (TypeError, ValueError):
        return _DEFAULT_TIE_THRESHOLD


def _disambiguation_globally_enabled() -> bool:
    val = (os.getenv("COLLECTION_SELECTOR_DISAMBIGUATE") or "").strip().lower()
    return val in ("1", "true", "yes", "on")


def _truncate(s: str, n: int) -> str:
    s = (s or "").strip().replace("\n", " ")
    return s if len(s) <= n else (s[: n - 1].rstrip() + "…")


def _build_alternatives(
    cands: Sequence[Candidate], query: str, limit: int = 3
) -> Tuple[Alternative, ...]:
    out: List[Alternative] = []
    for c in cands[:limit]:
        m = c.meta
        out.append(
            Alternative(
                collection_id=m.id,
                title=m.title or m.id,
                description=_truncate(m.description or "", _ALT_DESC_MAX),
                score=float(c.score),
                render_preset=_default_preset(m, query),
            )
        )
    return tuple(out)


def _needs_disambiguation(cands: Sequence[Candidate]) -> Tuple[bool, str]:
    """Return (needs, reason) given the ranked candidates from Stage B.

    Two triggers:
      * top-1 absolute score is below the confidence floor, *and* there is
        at least one other candidate (otherwise we have nothing to offer).
      * top-1 and top-2 are within :func:`_tie_threshold` of each other --
        a tie that the user should resolve.
    """
    if len(cands) < 2:
        return False, ""
    top = float(cands[0].score)
    second = float(cands[1].score)
    conf_floor = _confidence_threshold()
    if top < conf_floor:
        return True, f"top score {top:.3f} below floor {conf_floor:.3f}"
    if (top - second) < _tie_threshold():
        return True, f"tie: top1-top2 gap {top - second:.3f} < {_tie_threshold():.3f}"
    return False, ""


# ---------------------------------------------------------------------------
# LLM pick (Stage C)
# ---------------------------------------------------------------------------

_LLM_TIMEOUT_SECONDS = 8.0
_LLM_DEPLOYMENT_ENV = "COLLECTION_SELECTOR_DEPLOYMENT"


def _llm_deployment() -> Optional[str]:
    """Deployment name for Stage C. Falls back to the general chat deployment."""
    for var in (_LLM_DEPLOYMENT_ENV, "AZURE_OPENAI_DEPLOYMENT", "AZURE_OPENAI_CHAT_DEPLOYMENT"):
        v = (os.getenv(var) or "").strip()
        if v:
            return v
    return None


def _build_llm_prompt(query: str, mode: str, cands: Sequence[Candidate]) -> List[Dict[str, str]]:
    cand_lines: List[str] = []
    for i, c in enumerate(cands):
        m = c.meta
        desc = (m.description or "").strip().replace("\n", " ")
        if len(desc) > 280:
            desc = desc[:277] + "..."
        presets = ", ".join(m.render_presets) if m.render_presets else "(none)"
        cand_lines.append(
            f"{i + 1}. id={m.id} | title={m.title} | renders=[{presets}]\n   {desc}"
        )
    system = (
        "You are routing a natural-language geospatial query to exactly ONE "
        "STAC collection from a closed candidate list. You must pick from "
        "the provided candidates only -- inventing an id is a hard error. "
        "You also pick at most one render preset, which must be one of the "
        "candidate's listed renders. Respond with JSON only, matching the "
        "schema: {\"collection_id\": string, \"render_preset\": string|null, "
        "\"rationale\": string}."
    )
    user = (
        f"Mode: {mode}\n"
        f"User query: {query}\n\n"
        f"Candidates (choose ONE id verbatim):\n" + "\n".join(cand_lines)
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


async def _llm_pick(
    query: str,
    mode: str,
    cands: Sequence[Candidate],
) -> Optional[Dict[str, Any]]:
    """Ask the LLM to pick one candidate. Returns ``None`` on any failure.

    Constrained-decoding via ``response_format={"type": "json_object"}``.
    The caller is still required to verify the returned id is in
    ``cands`` (Stage D), because some deployments ignore the response
    format hint.
    """
    deployment = _llm_deployment()
    endpoint = (os.getenv("AZURE_OPENAI_ENDPOINT") or "").strip()
    if not deployment or not endpoint:
        return None
    try:
        from openai import AsyncAzureOpenAI
    except Exception as exc:
        logger.warning("[COLLECTION-SELECTOR] openai SDK unavailable: %s", exc)
        return None
    api_version = (os.getenv("AZURE_OPENAI_API_VERSION") or "2024-02-01").strip()
    api_key = (os.getenv("AZURE_OPENAI_API_KEY") or "").strip() or None
    kwargs: Dict[str, Any] = {
        "azure_endpoint": endpoint,
        "api_version": api_version,
        "api_key": api_key,
    }
    if not api_key:
        try:
            from azure.identity.aio import DefaultAzureCredential, get_bearer_token_provider
            kwargs["azure_ad_token_provider"] = get_bearer_token_provider(
                DefaultAzureCredential(),
                "https://cognitiveservices.azure.com/.default",
            )
        except Exception as exc:
            logger.warning("[COLLECTION-SELECTOR] AAD provider unavailable: %s", exc)
            return None
    # Model-aware kwargs: gpt-5/o1/o3/o4 reject `temperature` and
    # `max_tokens`; gpt-4o family rejects `reasoning_effort`. Mirror
    # the LoadAgent shim so a single deployment env switch can't
    # silently break the LLM pick stage.
    extra: Dict[str, Any] = {}
    if deployment.startswith(("gpt-5", "o1", "o3", "o4")):
        extra["reasoning_effort"] = "minimal"
        extra["max_completion_tokens"] = 400
    else:
        extra["temperature"] = 0.0
        extra["max_tokens"] = 400
    try:
        client = AsyncAzureOpenAI(**kwargs)
        resp = await client.chat.completions.create(
            model=deployment,
            messages=_build_llm_prompt(query, mode, cands),
            response_format={"type": "json_object"},
            timeout=_LLM_TIMEOUT_SECONDS,
            **extra,
        )
    except Exception as exc:
        logger.warning("[COLLECTION-SELECTOR] LLM call failed: %s", exc)
        return None
    try:
        content = resp.choices[0].message.content or "{}"
        data = json.loads(content)
        if not isinstance(data, dict):
            return None
        return {
            "collection_id": (data.get("collection_id") or "").strip() or None,
            "render_preset": (data.get("render_preset") or None),
            "rationale": str(data.get("rationale") or "")[:240],
        }
    except Exception as exc:
        logger.warning("[COLLECTION-SELECTOR] LLM response parse failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Selector entry point
# ---------------------------------------------------------------------------

async def select_collection(
    query: str,
    mode: str,
    *,
    index: Optional[CollectionIndex] = None,
    allow_llm: bool = True,
    top_k: int = 8,
    disambiguate: Optional[bool] = None,
) -> Selection:
    """Resolve ``(collection_id, render_preset)`` for a natural-language query.

    ``mode`` is ``"public"`` or ``"pro"`` (matching :mod:`collection_index`).
    Pass ``allow_llm=False`` from tests to force Stage D fallback without
    network access.

    ``disambiguate`` (Phase 3) controls whether the selector may return
    a ``stage="disambiguate"`` :class:`Selection` when the top-1 score
    is below the confidence floor or the top-1/top-2 gap is below the
    tie threshold. ``None`` (default) consults
    ``COLLECTION_SELECTOR_DISAMBIGUATE`` env (off by default for backwards
    compatibility). Pass ``True`` explicitly from the chat layer once it
    can render the alternatives.
    """
    t0 = time.monotonic()
    if not query or mode not in ("public", "pro"):
        return Selection(
            collection_id=None,
            render_preset=None,
            stage="none",
            reason="empty query or invalid mode",
            elapsed_ms=(time.monotonic() - t0) * 1000.0,
        )

    idx = index if index is not None else await get_collection_index()

    # --- Stage A: exact-id passthrough -------------------------------------
    for tok in _candidate_tokens(query):
        hit = await idx.lookup_exact(tok, mode)
        if hit:
            meta = await idx.get(hit, mode)
            preset = _default_preset(meta, query) if meta else None
            return Selection(
                collection_id=hit,
                render_preset=preset,
                stage="exact",
                reason=f"token '{tok}' matched live id",
                candidates=(hit,),
                confidence=1.0,
                elapsed_ms=(time.monotonic() - t0) * 1000.0,
            )

    # --- Stage B: semantic / lexical retrieval -----------------------------
    cands = await idx.search(query, mode, k=top_k)
    if not cands:
        return Selection(
            collection_id=None,
            render_preset=None,
            stage="none",
            reason="no candidates from live inventory",
            elapsed_ms=(time.monotonic() - t0) * 1000.0,
        )
    cand_ids = tuple(c.meta.id for c in cands)
    top_conf = float(cands[0].score)

    # --- Phase 3: low-confidence / tie disambiguation ----------------------
    disambig_on = (
        disambiguate if disambiguate is not None
        else _disambiguation_globally_enabled()
    )
    if disambig_on:
        needs, reason = _needs_disambiguation(cands)
        if needs:
            alts = _build_alternatives(cands, query, limit=3)
            top = cands[0]
            return Selection(
                # Surface a tentative pick so callers that ignore
                # ``needs_confirmation`` still degrade to top-1 instead
                # of returning None.
                collection_id=top.meta.id,
                render_preset=_default_preset(top.meta, query),
                stage="disambiguate",
                reason=reason,
                candidates=cand_ids,
                confidence=top_conf,
                needs_confirmation=True,
                alternatives=alts,
                elapsed_ms=(time.monotonic() - t0) * 1000.0,
            )

    # --- Stage C: LLM pick (constrained) -----------------------------------
    if allow_llm and len(cands) > 1:
        pick = await _llm_pick(query, mode, cands)
        if pick and pick.get("collection_id") in set(cand_ids):
            chosen_id = pick["collection_id"]
            chosen_meta = next(c.meta for c in cands if c.meta.id == chosen_id)
            preset = pick.get("render_preset")
            # Stage D guard for the preset too: must be in renders or None.
            if preset and preset not in chosen_meta.render_presets:
                preset = _default_preset(chosen_meta, query)
            elif not preset:
                preset = _default_preset(chosen_meta, query)
            return Selection(
                collection_id=chosen_id,
                render_preset=preset,
                stage="llm",
                reason="LLM picked from top-K",
                candidates=cand_ids,
                rationale=pick.get("rationale") or "",
                confidence=top_conf,
                elapsed_ms=(time.monotonic() - t0) * 1000.0,
            )

    # --- Stage D: deterministic fallback to top-1 lexical/semantic ---------
    top = cands[0]
    return Selection(
        collection_id=top.meta.id,
        render_preset=_default_preset(top.meta, query),
        stage="fallback",
        reason=f"top-1 by {top.method} score={top.score:.3f}",
        candidates=cand_ids,
        confidence=top_conf,
        elapsed_ms=(time.monotonic() - t0) * 1000.0,
    )


# ---------------------------------------------------------------------------
# Shadow-mode recorder
# ---------------------------------------------------------------------------

def _diff(v1: Sequence[str], v2: Optional[str]) -> str:
    v1_set = {c for c in (v1 or []) if c}
    if v2 is None:
        return "v2=none v1=" + ",".join(sorted(v1_set))
    if v1_set == {v2}:
        return "match"
    return f"v1={','.join(sorted(v1_set)) or 'none'} v2={v2}"


async def record_shadow_decision(
    query: str,
    mode: str,
    v1_collections: Sequence[str],
    *,
    log_fn=None,
    session_id: str = "",
) -> Optional[Selection]:
    """Run the v2 selector and log it next to the v1 pick. Never raises.

    Returns the v2 :class:`Selection` (or ``None`` when the flag is off).
    The caller is free to ignore the return value -- the side-effect of
    logging is what matters in shadow mode. When ``COLLECTION_SELECTOR=v2``
    is set, the caller should *act* on the returned Selection instead.

    ``log_fn`` is the optional pipeline logger from ``fastapi_app`` so we
    don't pull a runtime dep into this module. When omitted, the standard
    Python logger is used.
    """
    if selector_mode() == "off":
        return None
    try:
        sel = await select_collection(query, mode)
    except Exception as exc:
        logger.warning("[COLLECTION-SELECTOR] shadow run failed: %s", exc)
        return None
    payload = {
        "query": (query or "")[:240],
        "mode": mode,
        "v1": list(v1_collections or []),
        "v2": sel.to_log(),
        "diff": _diff(v1_collections, sel.collection_id),
    }
    try:
        if log_fn is not None:
            log_fn(session_id, "COLLECTION_SELECTOR", "SHADOW", payload)
        else:
            logger.info("[COLLECTION-SELECTOR][SHADOW] %s", json.dumps(payload))
    except Exception:
        # Logging must never break the request.
        logger.debug("[COLLECTION-SELECTOR] log emit failed", exc_info=True)
    return sel


__all__ = [
    "Alternative",
    "Selection",
    "select_collection",
    "record_shadow_decision",
    "selector_mode",
]
