"""Forecast Agent routing — decides which weather providers to call.

Three modes, in order of priority:

1. ``explicit``   — caller passes ``requested_providers``; we honor it
                    verbatim and skip the LLM. Intersected with the set
                    of providers actually configured in the registry.
2. ``llm``        — caller passes a natural-language ``user_query`` and
                    an ``LlmClient`` is configured. The LLM picks the
                    required ``Capability`` set and (optionally) an
                    explicit provider allow-list, with a short reason.
3. ``fallback_all``— no LLM configured or no query text; fall back to
                    "every provider supporting GLOBAL forecast" — the
                    pre-router behavior. Preserves CPU-stub demos and
                    keeps unit tests deterministic.

This module is intentionally LLM-optional: ``route()`` never raises if
the LLM client cannot be constructed — it transparently falls back to
mode 3. That keeps the Forecast Agent runnable in the weather-stub
smoke harness with no AOAI credentials.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Iterable

from connectors.weather import Capability, WeatherModelProvider

from .messages import ForecastAgentQuery

logger = logging.getLogger(__name__)

# Local import — keeps the router importable in environments that don't
# install the `openai` SDK. Resolved lazily inside _try_llm_client().
_LlmClient = None  # type: ignore[assignment]


@dataclass
class RoutingDecision:
    """Output of the router — drives provider fan-out and dossier UI."""

    provider_ids: tuple[str, ...]
    required_capabilities: tuple[Capability, ...]
    reason: str
    mode: str  # "explicit" | "llm" | "fallback_all"
    llm_raw: dict[str, Any] | None = None  # for debugging / dossier transparency

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "provider_ids": list(self.provider_ids),
            "required_capabilities": [c.value for c in self.required_capabilities],
            "reason": self.reason,
            "llm_raw": self.llm_raw,
        }


# ──────────────────────────────────────────────────────────────────────
# Public entry point
# ──────────────────────────────────────────────────────────────────────
async def route(
    query: ForecastAgentQuery,
    providers: list[WeatherModelProvider],
) -> RoutingDecision:
    """Pick a subset of ``providers`` for this query.

    Always returns a RoutingDecision; never raises. The caller is
    responsible for handling the empty-provider case.
    """
    if not providers:
        return RoutingDecision(
            provider_ids=(),
            required_capabilities=(Capability.GLOBAL,),
            reason="No weather providers configured.",
            mode="fallback_all",
        )

    # ── Mode 1: explicit allow-list wins, no LLM call ────────────────
    if query.requested_providers:
        wanted = set(query.requested_providers)
        chosen = [p for p in providers if p.provider_id in wanted]
        ids = tuple(p.provider_id for p in chosen)
        missing = sorted(wanted - {p.provider_id for p in chosen})
        reason = f"User explicitly requested providers: {list(wanted)}."
        if missing:
            reason += f" Skipped (not configured): {missing}."
        return RoutingDecision(
            provider_ids=ids,
            required_capabilities=(Capability.GLOBAL,),
            reason=reason,
            mode="explicit",
        )

    # ── Mode 2: LLM router (only if we have both a query and a client) ──
    if (query.user_query or "").strip():
        client = _try_llm_client()
        if client is not None:
            try:
                decision = await _llm_route(query, providers, client)
                return decision
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Forecast LLM router failed (%s); falling back to all-GLOBAL.",
                    exc,
                )
            finally:
                # Best-effort close. The LlmClient holds an httpx pool;
                # leaking is harmless across one request but noisy in tests.
                try:
                    await client.aclose()
                except Exception:  # noqa: BLE001
                    pass

    # ── Mode 3: no LLM / no query → preserve legacy "all GLOBAL" behavior ──
    eligible = [p for p in providers if Capability.GLOBAL in p.capabilities]
    return RoutingDecision(
        provider_ids=tuple(p.provider_id for p in eligible),
        required_capabilities=(Capability.GLOBAL,),
        reason=(
            "No user_query or no LlmClient available; routed to all "
            f"GLOBAL-capable providers: {[p.provider_id for p in eligible]}."
        ),
        mode="fallback_all",
    )


# ──────────────────────────────────────────────────────────────────────
# LLM routing internals
# ──────────────────────────────────────────────────────────────────────
def _try_llm_client():
    """Construct an LlmClient from env, or return None.

    Lazy import so the forecast package doesn't hard-depend on the
    `_framework` package or `openai` SDK.
    """
    global _LlmClient
    if _LlmClient is None:
        try:
            from _framework.llm_client import LlmClient as _Cls  # type: ignore
            _LlmClient = _Cls
        except Exception as exc:  # noqa: BLE001
            logger.debug("LlmClient import failed (%s); router will fall back.", exc)
            return None
    try:
        return _LlmClient.from_env()
    except Exception as exc:  # noqa: BLE001
        logger.debug("LlmClient.from_env() failed (%s); router will fall back.", exc)
        return None


_SYSTEM_PROMPT = """\
You are the routing brain of a multi-model AI weather forecasting agent.

Given a user's natural-language weather question, pick which of the
available AI weather models should run. You do NOT answer the weather
question — you only choose models.

Each model is tagged with capabilities:
  - GLOBAL                : global atmospheric forecast
  - REGIONAL              : regional / limited-area forecast
  - MEDIUM_RANGE_10D      : skill out to ~10 days
  - LONG_RANGE_14D_PLUS   : skill beyond 14 days
  - CYCLONE_TRACKS        : named-storm / tropical-cyclone tracking
  - KM_SCALE              : convection-resolving (km-scale) downscaling

Routing heuristics:
  - Hurricane / cyclone / typhoon tracks      → CYCLONE_TRACKS
  - "Km-scale", "downscale", "convective"     → KM_SCALE
  - 10+ days lookahead                        → MEDIUM_RANGE_10D (or LONG_RANGE_14D_PLUS)
  - Ensemble / model comparison               → multiple GLOBAL providers
  - Generic short-range point forecast        → all GLOBAL providers

If the user names specific models (e.g. "use Aurora", "Earth-2 only"),
emit that exact subset in `provider_ids`.

ALWAYS return a JSON object with this exact schema:

{
  "required_capabilities": [<one or more Capability strings>],
  "provider_ids":          [<optional explicit subset of available provider_ids>],
  "reason":                "<one-sentence justification>"
}

If `provider_ids` is empty/missing, the router will use every available
provider that satisfies `required_capabilities`.
"""


def _provider_catalog(providers: Iterable[WeatherModelProvider]) -> list[dict[str, Any]]:
    return [
        {
            "provider_id": p.provider_id,
            "vendor": p.vendor,
            "capabilities": [c.value for c in p.capabilities],
        }
        for p in providers
    ]


def _coerce_capabilities(values: Any) -> tuple[Capability, ...]:
    if not values:
        return (Capability.GLOBAL,)
    out: list[Capability] = []
    for v in values:
        try:
            out.append(Capability(str(v)))
        except ValueError:
            logger.debug("router: ignoring unknown capability %r", v)
    return tuple(out) if out else (Capability.GLOBAL,)


def _select_by_capabilities(
    providers: list[WeatherModelProvider],
    caps: tuple[Capability, ...],
) -> list[WeatherModelProvider]:
    """All-of semantics: every required cap must be present on the provider."""
    return [p for p in providers if all(c in p.capabilities for c in caps)]


async def _llm_route(
    query: ForecastAgentQuery,
    providers: list[WeatherModelProvider],
    client: Any,
) -> RoutingDecision:
    user_payload = {
        "user_query": query.user_query,
        "location_label": query.location_label,
        "lat": query.lat,
        "lon": query.lon,
        "lead_hours": query.lead_hours,
        "variables": list(query.variables),
        "available_providers": _provider_catalog(providers),
    }
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
    ]
    resp = await client.chat(
        messages=messages,
        temperature=0.0,
        max_tokens=400,
        response_format={"type": "json_object"},
    )
    raw = resp.choices[0].message.content or "{}"
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("router: LLM returned non-JSON, falling back. raw=%r", raw[:200])
        parsed = {}

    caps = _coerce_capabilities(parsed.get("required_capabilities"))
    eligible = _select_by_capabilities(providers, caps)
    if not eligible:
        # LLM asked for capabilities nobody has — degrade gracefully.
        logger.info(
            "router: no providers satisfy %s; falling back to GLOBAL",
            [c.value for c in caps],
        )
        caps = (Capability.GLOBAL,)
        eligible = _select_by_capabilities(providers, caps)

    explicit_ids = parsed.get("provider_ids") or []
    if explicit_ids:
        wanted = {str(x) for x in explicit_ids}
        narrowed = [p for p in eligible if p.provider_id in wanted]
        if narrowed:
            eligible = narrowed

    reason = (parsed.get("reason") or "").strip()
    if not reason:
        reason = f"LLM routed to capabilities {[c.value for c in caps]}."

    return RoutingDecision(
        provider_ids=tuple(p.provider_id for p in eligible),
        required_capabilities=caps,
        reason=reason,
        mode="llm",
        llm_raw=parsed if isinstance(parsed, dict) else {"_raw": raw},
    )
