"""
ContextualAgent — designated agent for educational / general-knowledge
Earth-observation answers.

Owns the diagram's *Text → contextual* box. Single chat completion with a
tight Earth-observation scope. Used as the safe fallback when no
specialized analyzer fits.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

from openai import AsyncAzureOpenAI
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

from .contextual_models import ContextualInput, ContextualResult

logger = logging.getLogger(__name__)


_SYSTEM_PROMPT = """You are an Earth observation subject-matter expert. Answer
the user's question accurately and concisely. Stay within Earth observation,
remote sensing, geospatial analysis, and adjacent science. If you don't know
or the question is out of scope, say so plainly.

Do not invent dataset names, sensor specs, or numeric thresholds. If you
reference a methodology, name the source (paper, agency, standard) at a
high level.

Formatting rules: use plain text, markdown bold, bullets, and tables only.
NEVER use emojis or pictographs of any kind (no traffic-light circles,
checkmarks, warning signs, weather icons, etc.)."""


class ContextualAgent:
    def __init__(
        self,
        *,
        deployment: Optional[str] = None,
        endpoint: Optional[str] = None,
        api_version: str = "2024-12-01-preview",
    ) -> None:
        self.deployment = deployment or os.getenv(
            "AZURE_OPENAI_FAST_DEPLOYMENT",
            os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5"),
        )
        # AsyncAzureOpenAI requires an AOAI-style endpoint (e.g.
        # https://<resource>.cognitiveservices.azure.com/ or
        # https://<resource>.openai.azure.com/). The Foundry project URL
        # exposed via AZURE_AI_PROJECT_ENDPOINT
        # (https://<resource>.services.ai.azure.com/api/projects/<project>)
        # is NOT a valid AOAI endpoint -- the SDK fails the credential
        # check and surfaces a misleading "Missing credentials" error at
        # request time. Always prefer AZURE_OPENAI_ENDPOINT.
        self.endpoint = endpoint or os.getenv(
            "AZURE_OPENAI_ENDPOINT"
        ) or os.getenv("AZURE_AI_PROJECT_ENDPOINT")
        if not self.endpoint:
            raise ValueError(
                "ContextualAgent requires AZURE_OPENAI_ENDPOINT or "
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
        # NOTE: must pass api_key=None (not "") so the OpenAI SDK falls
        # through to azure_ad_token_provider. An empty string is treated as
        # an explicit (invalid) credential and triggers
        # "Missing credentials. Please pass an `api_key`..." failures.
        self._client = AsyncAzureOpenAI(
            azure_endpoint=self.endpoint,
            api_key=api_key,
            azure_ad_token_provider=token_provider,
            api_version=self.api_version,
        )
        return self._client

    async def run(self, payload: ContextualInput) -> ContextualResult:
        started = time.time()
        system_prompt = _SYSTEM_PROMPT
        if payload.hint:
            system_prompt = f"{_SYSTEM_PROMPT}\n\nROUTER_HINT: {payload.hint[:200]}"

        messages: list[dict] = [{"role": "system", "content": system_prompt}]
        # Light history (last 4 turns) so follow-ups make sense.
        for turn in (payload.history or [])[-4:]:
            role = (turn.get("role") or turn.get("sender") or "user")[:9]
            content = turn.get("content") or turn.get("text") or ""
            if content:
                messages.append({"role": role if role in ("user", "assistant") else "user",
                                 "content": str(content)[:600]})
        messages.append({"role": "user", "content": payload.question})

        try:
            client = self._get_client()
            # NOTE: temperature intentionally omitted. gpt-5 reasoning
            # deployments only accept the default temperature (1); passing
            # any other value returns HTTP 400 and bubbles up as the
            # user-visible "LLM call failed" sentinel.
            resp = await client.chat.completions.create(
                model=self.deployment,
                messages=messages,
            )
            answer = resp.choices[0].message.content or ""
        except Exception as exc:  # noqa: BLE001
            logger.warning("[CONTEXTUAL_AGENT] failed: %s", exc)
            return ContextualResult(
                success=False,
                answer="",
                confidence=0.0,
                error=f"{type(exc).__name__}: {exc}",
                elapsed_ms=int((time.time() - started) * 1000),
            )

        return ContextualResult(
            success=bool(answer.strip()),
            answer=answer,
            confidence=0.7 if answer.strip() else 0.0,
            elapsed_ms=int((time.time() - started) * 1000),
        )


_singleton: Optional[ContextualAgent] = None


def get_contextual_agent() -> ContextualAgent:
    global _singleton
    if _singleton is None:
        _singleton = ContextualAgent()
    return _singleton
