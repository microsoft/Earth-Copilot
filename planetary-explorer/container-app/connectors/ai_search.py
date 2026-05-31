"""Azure AI Search connector.

Thin async wrapper around ``azure-search-documents`` so agents stay
decoupled from the SDK and we have one place for auth + retries +
error normalisation.

Env vars:
    AZURE_SEARCH_ENDPOINT   https://<service>.search.windows.net  (required)
    AZURE_SEARCH_INDEX      default index name used by ``search()``  (optional)
    AZURE_SEARCH_KEY        admin or query key; if absent, Managed
                            Identity is used via :class:`DefaultAzureCredential`

The client is *inert* until at least ``AZURE_SEARCH_ENDPOINT`` is set:
``AiSearchClient.from_env()`` returns ``None`` and callers fall back to
their existing path (today most callers already handle this — see the
``ai_search`` provenance entries in ``agents/resilience/executors.py``).
"""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# Keep SDK imports lazy — this connector should not force the
# ``azure-search-documents`` install on environments that don't use it.
try:
    from azure.core.credentials import AzureKeyCredential
    from azure.identity.aio import DefaultAzureCredential
    from azure.search.documents.aio import SearchClient

    _SDK_AVAILABLE = True
except Exception:  # noqa: BLE001
    _SDK_AVAILABLE = False


class AiSearchClient:
    """Minimal async client. One instance per index."""

    def __init__(self, endpoint: str, index: str, credential: Any) -> None:
        if not _SDK_AVAILABLE:
            raise RuntimeError(
                "azure-search-documents is not installed; cannot use AiSearchClient"
            )
        self.endpoint = endpoint
        self.index = index
        self._credential = credential
        self._client = SearchClient(
            endpoint=endpoint, index_name=index, credential=credential
        )

    @classmethod
    def from_env(cls, index: str | None = None) -> "AiSearchClient | None":
        endpoint = (os.getenv("AZURE_SEARCH_ENDPOINT") or "").strip()
        if not endpoint:
            return None
        idx = index or os.getenv("AZURE_SEARCH_INDEX") or ""
        if not idx:
            logger.warning("AZURE_SEARCH_INDEX not set; pass `index=` explicitly")
            return None
        if not _SDK_AVAILABLE:
            logger.warning("azure-search-documents missing; AI Search disabled")
            return None
        key = (os.getenv("AZURE_SEARCH_KEY") or "").strip()
        credential = AzureKeyCredential(key) if key else DefaultAzureCredential()
        return cls(endpoint=endpoint, index=idx, credential=credential)

    async def search(
        self,
        query: str,
        *,
        top: int = 5,
        filter: str | None = None,  # noqa: A002 (Azure SDK uses `filter`)
        select: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Run a full-text search. Returns list of dict documents."""
        results = await self._client.search(
            search_text=query, top=top, filter=filter, select=select
        )
        docs: list[dict[str, Any]] = []
        async for doc in results:
            docs.append(dict(doc))
        return docs

    async def get_document(self, key: str) -> dict[str, Any] | None:
        try:
            doc = await self._client.get_document(key=key)
            return dict(doc) if doc is not None else None
        except Exception as exc:  # noqa: BLE001
            logger.debug("ai_search get_document(%s) failed: %s", key, exc)
            return None

    async def aclose(self) -> None:
        await self._client.close()
        if hasattr(self._credential, "close"):
            try:
                await self._credential.close()
            except Exception:  # noqa: BLE001
                pass
