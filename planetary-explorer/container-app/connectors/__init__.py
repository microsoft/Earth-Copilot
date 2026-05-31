"""Typed connector package — one module per external platform.

Each module is a thin, typed wrapper that owns:

- endpoint / auth resolution (env vars, Managed Identity, key fallback)
- retry + timeout policy
- request/response shaping
- optional in-memory caching

Agent code never reaches into ``httpx``, ``mcp``, or ``azure.search``
directly — it imports a connector. This keeps fork-tax low (one place
to change per platform) and centralises the recurring AOAI-vs-Foundry
endpoint confusion to a single boundary.

Modules:
    :mod:`weather`     Aurora / Earth-2 / MAI Weather provider abstraction
    :mod:`mpc_pro`     Microsoft Planetary Computer Pro (re-exports
                       ``mcp_catalog_client``)
    :mod:`fabric`      Microsoft Fabric (re-exports ``fabric_client``)
    :mod:`foundry`     Azure AI Foundry online endpoints (score + auth)
    :mod:`ai_search`   Azure AI Search (thin async wrapper)
    :mod:`openmeteo`   Open-Meteo free public API (fallback weather)
    :mod:`mcp_registry`  Re-exports the MCP tool registry from
                       ``container-app/mcp_runtime/registry.py``

See ``connectors/README.md`` for the one-page contract per platform.
"""
