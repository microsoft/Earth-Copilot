"""Unified LLM client — single entry point for chat completions.

Resolves the recurring AOAI-vs-Foundry confusion: ``AZURE_OPENAI_ENDPOINT``
is the data-plane URL; ``AZURE_AI_PROJECT_ENDPOINT`` is the project URL
(used only as a fallback when no AOAI endpoint exists). This client
picks the right one once at construction time and exposes one ``chat()``
method that agents call.

Also handles the gpt-5 parameter quirk: the new model family rejects
``temperature``, ``top_p``, ``frequency_penalty``, ``presence_penalty``.
We strip them when the deployment name looks like gpt-5.

Auth is API key by default (``AZURE_OPENAI_API_KEY``); when absent we
fall back to ``DefaultAzureCredential`` via the SDK's bearer token
provider.
"""
from __future__ import annotations

import logging
import os
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

# Lazy SDK import — many agents already pull this in, but the framework
# should not force ``openai`` on environments that don't use it.
try:
    from openai import AsyncAzureOpenAI

    _SDK_AVAILABLE = True
except Exception:  # noqa: BLE001
    _SDK_AVAILABLE = False


class LlmEndpointKind(str, Enum):
    AOAI = "aoai"          # Azure OpenAI data-plane endpoint
    FOUNDRY = "foundry"    # AI Foundry project endpoint (fallback)


# Models that reject sampling params. Conservative pattern — any name
# containing "gpt-5" or "o1" or "o3" is treated as restricted.
_RESTRICTED_PATTERNS = ("gpt-5", "o1", "o3")
_SAMPLING_KEYS = ("temperature", "top_p", "frequency_penalty", "presence_penalty")


def _is_restricted(model: str) -> bool:
    m = (model or "").lower()
    return any(p in m for p in _RESTRICTED_PATTERNS)


class LlmClient:
    """One-call wrapper around ``AsyncAzureOpenAI``."""

    def __init__(
        self,
        endpoint: str,
        kind: LlmEndpointKind,
        api_version: str,
        api_key: str | None,
        deployment: str,
    ) -> None:
        if not _SDK_AVAILABLE:
            raise RuntimeError("`openai` package not installed; cannot create LlmClient")
        self.endpoint = endpoint
        self.kind = kind
        self.api_version = api_version
        self.api_key = api_key
        self.deployment = deployment

        kwargs: dict[str, Any] = {
            "azure_endpoint": endpoint,
            "api_version": api_version,
        }
        if api_key:
            kwargs["api_key"] = api_key
        else:
            # Fall back to DefaultAzureCredential via SDK helper.
            from azure.identity.aio import DefaultAzureCredential
            from openai.lib.azure import AsyncAzureADTokenProvider  # type: ignore

            cred = DefaultAzureCredential()

            async def _token_provider() -> str:
                tok = await cred.get_token("https://cognitiveservices.azure.com/.default")
                return tok.token

            kwargs["azure_ad_token_provider"] = _token_provider  # type: ignore[assignment]
        self._client = AsyncAzureOpenAI(**kwargs)

    @classmethod
    def from_env(cls, *, deployment_env: str = "AZURE_OPENAI_DEPLOYMENT") -> "LlmClient":
        """Resolve endpoint + auth from env vars.

        Resolution order for the endpoint:
            1. ``AZURE_OPENAI_ENDPOINT`` — preferred (AOAI data-plane)
            2. ``AZURE_AI_PROJECT_ENDPOINT`` — Foundry project fallback

        Raises ``RuntimeError`` if neither is set.
        """
        endpoint = (os.getenv("AZURE_OPENAI_ENDPOINT") or "").strip()
        kind = LlmEndpointKind.AOAI
        if not endpoint:
            endpoint = (os.getenv("AZURE_AI_PROJECT_ENDPOINT") or "").strip()
            kind = LlmEndpointKind.FOUNDRY
        if not endpoint:
            raise RuntimeError(
                "LlmClient: set AZURE_OPENAI_ENDPOINT (preferred) or "
                "AZURE_AI_PROJECT_ENDPOINT"
            )
        api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21")
        api_key = (os.getenv("AZURE_OPENAI_API_KEY") or "").strip() or None
        deployment = (os.getenv(deployment_env) or "").strip()
        if not deployment:
            raise RuntimeError(f"LlmClient: {deployment_env} must be set")
        logger.info(
            "LlmClient configured: kind=%s endpoint=%s deployment=%s auth=%s",
            kind.value,
            endpoint,
            deployment,
            "key" if api_key else "managed-identity",
        )
        return cls(
            endpoint=endpoint,
            kind=kind,
            api_version=api_version,
            api_key=api_key,
            deployment=deployment,
        )

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        deployment: str | None = None,
        temperature: float | None = 0.2,
        top_p: float | None = None,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
        **extra: Any,
    ) -> Any:
        """Run a chat completion. Strips sampling params for restricted models."""
        model = deployment or self.deployment
        kwargs: dict[str, Any] = {"model": model, "messages": messages}
        if temperature is not None:
            kwargs["temperature"] = temperature
        if top_p is not None:
            kwargs["top_p"] = top_p
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        if response_format is not None:
            kwargs["response_format"] = response_format
        kwargs.update(extra)

        if _is_restricted(model):
            removed = [k for k in _SAMPLING_KEYS if k in kwargs]
            for k in removed:
                kwargs.pop(k, None)
            if removed:
                logger.debug(
                    "LlmClient: model %s is restricted; stripped %s",
                    model,
                    removed,
                )
        return await self._client.chat.completions.create(**kwargs)

    async def aclose(self) -> None:
        await self._client.close()
