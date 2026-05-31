"""Microsoft Fabric connector — re-export of the existing :mod:`fabric_client`.

This module is the canonical entry point for new code that needs to read
Fabric workspaces, lakehouses, Delta tables, or run SQL against the Power
BI analytics endpoint. The underlying implementation in
``container-app/fabric_client.py`` continues to back this surface and
existing imports keep working.

See ``fabric_client.py`` for the full credential resolution + scopes
discussion.
"""
from __future__ import annotations

from fabric_client import (  # noqa: F401  (re-export)
    FabricNotConfigured,
    acquire_app_token,
    exchange_user_token,
    execute_sql,
    extract_user_assertion,
    get_lakehouse_schema,
    is_configured,
    list_lakehouses,
    list_workspaces,
    search_documents,
)

__all__ = [
    "FabricNotConfigured",
    "acquire_app_token",
    "exchange_user_token",
    "execute_sql",
    "extract_user_assertion",
    "get_lakehouse_schema",
    "is_configured",
    "list_lakehouses",
    "list_workspaces",
    "search_documents",
]
