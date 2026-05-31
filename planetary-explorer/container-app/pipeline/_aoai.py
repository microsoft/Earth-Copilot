"""
Shared Azure OpenAI client factory for the v2 pipeline.

Centralises endpoint/credential setup so routers, synthesizer, analyzers,
and the (Wave-4) Semantic-Kernel-free RouterAgent all use the same auth
path.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import AsyncAzureOpenAI

logger = logging.getLogger(__name__)

_COG_SCOPE = "https://cognitiveservices.azure.com/.default"


@lru_cache(maxsize=1)
def get_aoai_client() -> AsyncAzureOpenAI:
    # IMPORTANT: AsyncAzureOpenAI talks to the Cognitive Services
    # (`*.cognitiveservices.azure.com`) endpoint, NOT the AI Foundry
    # Projects endpoint (`*.services.ai.azure.com/api/projects/...`).
    # The project endpoint is a different control-plane API that requires
    # the `https://ai.azure.com` token audience and returns 401 for
    # chat.completions calls authenticated with `cognitiveservices.azure.com`
    # tokens. Prefer AZURE_OPENAI_ENDPOINT; only fall back to the project
    # endpoint for legacy configs.
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT") or os.getenv("AZURE_AI_PROJECT_ENDPOINT")
    if not endpoint:
        raise RuntimeError(
            "Pipeline v2 requires AZURE_OPENAI_ENDPOINT (or legacy AZURE_AI_PROJECT_ENDPOINT)"
        )
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")
    api_key = os.environ.get("AZURE_OPENAI_API_KEY")
    if api_key:
        client = AsyncAzureOpenAI(
            azure_endpoint=endpoint, api_key=api_key, api_version=api_version
        )
    else:
        token_provider = get_bearer_token_provider(DefaultAzureCredential(), _COG_SCOPE)
        client = AsyncAzureOpenAI(
            azure_endpoint=endpoint,
            azure_ad_token_provider=token_provider,
            api_version=api_version,
        )
    logger.info("[PIPELINE] AsyncAzureOpenAI client created (endpoint=%s)", endpoint)
    return client


def fast_deployment() -> str:
    """Cheap/fast model for routing + light synthesis."""
    return os.getenv("AZURE_OPENAI_FAST_DEPLOYMENT", "gpt-4o-mini")


def main_deployment() -> str:
    """Capable model for complex synthesis."""
    return os.getenv("AZURE_OPENAI_DEPLOYMENT") or os.getenv(
        "AZURE_OPENAI_FAST_DEPLOYMENT", "gpt-4o"
    )
