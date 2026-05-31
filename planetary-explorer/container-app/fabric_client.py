"""
Microsoft Fabric integration for Planetary Explorer.

This module provides a thin async client around the Fabric REST API + Power BI
analytics endpoint + OneLake Delta tables. Auth is by **app identity**
(Managed Identity in Container Apps, Service Principal locally), NOT user
OBO — the data exposed by this client is reference data identical for every
authenticated user (power grid, hydrology, parcels), so the right model is:

    1. User authenticates against the app (EasyAuth on the UI App Service).
    2. Backend confirms the user is authenticated (auth_middleware.py).
    3. Backend uses ITS OWN identity (this module) to read Fabric. The
       backend identity needs to be granted Contributor on the Fabric
       workspace exactly once at deploy time.

Credential resolution (priority order):
    a. `FABRIC_CLIENT_ID` + `FABRIC_CLIENT_SECRET` env vars  → ClientSecretCredential
       (Useful for local dev and the initial bootstrap before MI is wired.)
    b. Container Apps system-assigned Managed Identity              → ManagedIdentityCredential
       (Production default. No secrets to rotate. Granted Fabric workspace
       access via the `infra/` Bicep/Terraform.)
    c. Azure CLI / VS Code / Env credentials                        → DefaultAzureCredential chain
       (Developer-workstation convenience.)

For a NEW DEPLOYER, the one-time setup is:
    - Provision the Fabric workspace + lakehouse + tables (see `infra/fabric/`).
    - Grant the Container App's system-assigned MI Contributor on the workspace
      (one Fabric REST POST — `scripts/grant-fabric-access.ps1`).
    - Done. No secrets, no admin consent on delegated permissions, no OBO.

Scopes
------
- `https://api.fabric.microsoft.com/.default`         — workspace / item REST
- `https://analysis.windows.net/powerbi/api/.default` — SQL endpoint (Power BI XMLA / SQL)
- `https://storage.azure.com/.default`                — OneLake (abfss://)

Env vars
--------
- FABRIC_TENANT_ID         — AAD tenant id (defaults to AZURE_TENANT_ID)
- FABRIC_CLIENT_ID         — Service-principal client id (optional; MI used if absent)
- FABRIC_CLIENT_SECRET     — Service-principal secret (paired with FABRIC_CLIENT_ID)
- FABRIC_API_ENDPOINT      — default https://api.fabric.microsoft.com
- FABRIC_PBI_API_ENDPOINT  — default https://api.powerbi.com
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

FABRIC_API = os.getenv("FABRIC_API_ENDPOINT", "https://api.fabric.microsoft.com").rstrip("/")
PBI_API = os.getenv("FABRIC_PBI_API_ENDPOINT", "https://api.powerbi.com").rstrip("/")

FABRIC_SCOPE = "https://api.fabric.microsoft.com/.default"
PBI_SCOPE = "https://analysis.windows.net/powerbi/api/.default"


class FabricNotConfigured(RuntimeError):
    """Raised when Fabric env vars aren't set. Surfaces as a 503 to the UI."""


def is_configured() -> bool:
    """True when this module has *some* path to a Fabric token.

    We always assume Managed Identity may be available at runtime (it costs
    nothing to try and the credential chain falls through gracefully), so the
    only true "not configured" case is when the tenant id can't be resolved.
    """
    return bool(os.getenv("FABRIC_TENANT_ID") or os.getenv("AZURE_TENANT_ID"))


# ---------------------------------------------------------------------------
# Credential acquisition (app identity — MI in prod, SP for dev / bootstrap)
# ---------------------------------------------------------------------------

_credential = None  # azure.identity credential object — lazy-init
_credential_lock = asyncio.Lock()

# Cheap in-process token cache. Azure-identity's own caching covers most of
# this but we still avoid an `await get_token()` per request on the hot path.
_TOKEN_CACHE: Dict[str, tuple[float, str]] = {}   # scope -> (expires_at_epoch, token)
_TOKEN_CACHE_LOCK = asyncio.Lock()
_TOKEN_SAFETY_MARGIN_SEC = 60


async def _get_credential():
    """Build (once) the right azure-identity credential for the environment."""
    global _credential
    if _credential is not None:
        return _credential
    async with _credential_lock:
        if _credential is not None:
            return _credential
        from azure.identity.aio import (
            ClientSecretCredential,
            DefaultAzureCredential,
            ManagedIdentityCredential,
        )
        tenant = os.getenv("FABRIC_TENANT_ID") or os.getenv("AZURE_TENANT_ID")
        client_id = os.getenv("FABRIC_CLIENT_ID")
        client_secret = os.getenv("FABRIC_CLIENT_SECRET")
        if tenant and client_id and client_secret:
            logger.info("[FABRIC] auth: ClientSecretCredential (sp=%s, tenant=%s)", client_id, tenant)
            _credential = ClientSecretCredential(tenant, client_id, client_secret)
        else:
            # DefaultAzureCredential automatically picks ManagedIdentityCredential
            # when running in Container Apps; falls through to az CLI / env on dev.
            logger.info("[FABRIC] auth: DefaultAzureCredential (will use Managed Identity in Container Apps)")
            _credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
        return _credential


async def acquire_app_token(scope: str) -> str:
    """Get a token for `scope` using the app's own identity (MI or SP).

    This replaces the user-OBO flow. The token represents the **backend
    service**, not the signed-in user. The backend identity must be granted
    the relevant Fabric / OneLake / PowerBI permissions exactly once at
    deploy time — typically Contributor on the workspace.
    """
    now = time.time()
    async with _TOKEN_CACHE_LOCK:
        cached = _TOKEN_CACHE.get(scope)
        if cached and cached[0] - _TOKEN_SAFETY_MARGIN_SEC > now:
            return cached[1]

    cred = await _get_credential()
    try:
        access_token = await cred.get_token(scope)
    except Exception as exc:  # noqa: BLE001 — surface as a configured-failure
        logger.warning("[FABRIC] acquire_app_token(%s) failed: %s", scope, exc)
        raise FabricNotConfigured(f"Could not acquire app token for {scope}: {exc}")

    async with _TOKEN_CACHE_LOCK:
        _TOKEN_CACHE[scope] = (float(access_token.expires_on), access_token.token)
    return access_token.token


async def exchange_user_token(user_assertion: str, scope: str) -> str:  # noqa: ARG001
    """Back-compat shim.

    Older call sites passed a per-request user JWT for OBO. We no longer do
    OBO; the data is app-scoped reference data. The `user_assertion` argument
    is accepted-and-ignored so we don't have to update every call site at
    once. New code should call `acquire_app_token(scope)` directly.
    """
    return await acquire_app_token(scope)


def extract_user_assertion(headers: Dict[str, Any]) -> Optional[str]:
    """Pull the caller's AAD access token from EasyAuth's forwarded header.

    Retained for routes that genuinely want to inspect the caller's token
    (e.g. tenant-scoped logging). Not used for Fabric data access anymore.
    """
    tok = headers.get("X-MS-TOKEN-AAD-ACCESS-TOKEN") or headers.get("x-ms-token-aad-access-token")
    if tok:
        return tok.strip()
    auth = headers.get("Authorization") or headers.get("authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


# ---------------------------------------------------------------------------
# REST helpers
# ---------------------------------------------------------------------------

async def _get(url: str, token: str) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(url, headers={"Authorization": f"Bearer {token}"})
    if r.status_code != 200:
        raise httpx.HTTPStatusError(
            f"Fabric GET {url} -> {r.status_code}: {r.text[:300]}",
            request=r.request,
            response=r,
        )
    return r.json()


async def list_workspaces(user_assertion: str) -> List[Dict[str, Any]]:
    """List Fabric workspaces visible to the caller."""
    token = await exchange_user_token(user_assertion, FABRIC_SCOPE)
    data = await _get(f"{FABRIC_API}/v1/workspaces", token)
    return data.get("value", [])


async def list_lakehouses(user_assertion: str, workspace_id: str) -> List[Dict[str, Any]]:
    token = await exchange_user_token(user_assertion, FABRIC_SCOPE)
    data = await _get(f"{FABRIC_API}/v1/workspaces/{workspace_id}/lakehouses", token)
    return data.get("value", [])


async def get_lakehouse_schema(
    user_assertion: str, workspace_id: str, lakehouse_id: str
) -> Dict[str, Any]:
    """Best-effort schema enumeration. Uses Fabric's `tables` REST surface."""
    token = await exchange_user_token(user_assertion, FABRIC_SCOPE)
    url = f"{FABRIC_API}/v1/workspaces/{workspace_id}/lakehouses/{lakehouse_id}/tables"
    data = await _get(url, token)
    return {
        "workspace_id": workspace_id,
        "lakehouse_id": lakehouse_id,
        "tables": data.get("data", []),
    }


async def execute_sql(
    user_assertion: str,
    workspace_id: str,
    lakehouse_id: str,
    sql: str,
    timeout_sec: float = 60.0,
) -> Dict[str, Any]:
    """Execute a read-only SQL statement against a Lakehouse's SQL analytics endpoint.

    Uses the Power BI / Fabric SQL endpoint (DAX-over-REST equivalent for
    SQL). Returns rows as a list of dicts plus the column schema. The caller
    is responsible for SQL injection guards — typically text-to-SQL output is
    parsed + validated by AnalystAgent before reaching this function.

    NOTE: Fabric exposes Lakehouse SQL via the TDS endpoint
    (server: <ws>-<lh>.datawarehouse.fabric.microsoft.com); raw REST query is
    available through the "Execute Queries" Power BI API when the Lakehouse
    has a SQL endpoint. For the MVP we use the Power BI REST surface.
    """
    token = await exchange_user_token(user_assertion, PBI_SCOPE)
    # PBI dataset id for a lakehouse SQL endpoint == the lakehouse SQL endpoint id.
    # The caller may pass either; we trust the input.
    url = f"{PBI_API}/v1.0/myorg/groups/{workspace_id}/datasets/{lakehouse_id}/executeQueries"
    body = {"queries": [{"query": sql}], "serializerSettings": {"includeNulls": True}}
    async with httpx.AsyncClient(timeout=timeout_sec) as client:
        r = await client.post(url, headers={"Authorization": f"Bearer {token}"}, json=body)
    if r.status_code != 200:
        raise httpx.HTTPStatusError(
            f"Fabric SQL -> {r.status_code}: {r.text[:300]}",
            request=r.request,
            response=r,
        )
    return r.json()


async def search_documents(
    user_assertion: str,
    workspace_id: str,
    query: str,
    top_k: int = 5,
    *,
    filter_expr: str | None = None,
    select: List[str] | None = None,
    semantic: bool = True,
) -> List[Dict[str, Any]]:
    """Semantic doc search over a Fabric AI Search / Eventhouse vector index.

    The Planetary Explorer convention is that the customer indexes their corpus
    into either:
      (a) An Azure AI Search index whose endpoint is `FABRIC_DOC_SEARCH_URL`
          with key `FABRIC_DOC_SEARCH_KEY`, OR
      (b) A Fabric Eventhouse / KQL DB exposing `vector_search` over a known
          column.

    For the MVP we wire option (a) — it's stable, no preview surface, and
    the most common customer pattern. Option (b) can be added behind the
    same function signature.
    """
    endpoint = os.getenv("FABRIC_DOC_SEARCH_URL", "").rstrip("/")
    key = os.getenv("FABRIC_DOC_SEARCH_KEY")
    index = os.getenv("FABRIC_DOC_SEARCH_INDEX", "planetary-explorer-docs")
    if not endpoint or not key:
        raise FabricNotConfigured(
            "Document search not configured. Set FABRIC_DOC_SEARCH_URL + FABRIC_DOC_SEARCH_KEY + FABRIC_DOC_SEARCH_INDEX."
        )

    url = f"{endpoint}/indexes/{index}/docs/search?api-version=2023-11-01"
    body: Dict[str, Any] = {"search": query, "top": top_k}
    if semantic:
        body["queryType"] = "semantic"
        body["semanticConfiguration"] = "default"
    if filter_expr:
        body["filter"] = filter_expr
    if select:
        body["select"] = ",".join(select)
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.post(url, headers={"api-key": key, "Content-Type": "application/json"}, json=body)
    if r.status_code != 200:
        raise httpx.HTTPStatusError(
            f"Fabric doc search -> {r.status_code}: {r.text[:300]}",
            request=r.request,
            response=r,
        )
    data = r.json()
    return data.get("value", [])
