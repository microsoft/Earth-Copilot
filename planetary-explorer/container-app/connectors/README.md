# `connectors/` — typed external-platform clients

One module per platform. Each owns endpoint + auth + retry + caching for
that platform; agents import the connector and never touch raw HTTP or
SDK constructors directly.

This package is the single source of truth for **how PE talks to the
outside world**. If you're forking PE for a customer, this is the file
you read first to see what's pluggable.

| Module                 | Wraps                              | Auth                             | Status      |
|------------------------|------------------------------------|----------------------------------|-------------|
| `weather.*`            | Aurora / Earth-2 / MAI Weather     | bearer key or Managed Identity   | live (stubs) |
| `mpc_pro`              | MPC Pro MCP sidecar                | bearer key                       | live (re-export of `mcp_catalog_client`) |
| `fabric`               | Microsoft Fabric REST + OneLake    | Managed Identity (preferred)     | live (re-export of `fabric_client`) |
| `ai_search`            | Azure AI Search                    | key or Managed Identity          | live (thin wrapper) |
| `openmeteo`            | Open-Meteo free forecast API       | none                             | live (thin wrapper) |
| `mcp_registry`         | MCP tool registry                  | inherits per-server              | re-export of `container-app/mcp/registry.py` |

## One-page contract per platform

### `weather` (sub-package)
- Capability-tagged `WeatherModelProvider` protocol.
- Registry singleton `get_registry()` returns the configured providers.
- Each provider activates only when its `*_ENDPOINT_URL` env var is set.
- See `weather/README.md` (if present) and `weather/provider.py` for the contract.

### `mpc_pro`
- Re-exports `MpcMcpClient` from `mcp_catalog_client`.
- Inert until `USE_MPC_MCP=true` + `MPC_MCP_URL=https://...`.
- Wraps all 35 MPC Pro MCP tools — search, ingest, lifecycle, rendering.
- See top docstring of `mcp_catalog_client.py` for tool coverage.

### `fabric`
- Re-exports `FabricClient` from `fabric_client`.
- App-identity auth (Managed Identity in prod, service principal locally).
- Reads Fabric workspaces / lakehouses / Delta tables / SQL endpoint.

### `ai_search`
- `AiSearchClient.from_env()` factory; honours `AZURE_SEARCH_ENDPOINT`,
  `AZURE_SEARCH_KEY` (or Managed Identity if no key), `AZURE_SEARCH_INDEX`.
- Two methods: `search(query, top, filter)` and `get_document(key)`.
- Returns dicts, not SDK objects, so agents stay decoupled from `azure-search-documents`.

### `openmeteo`
- `OpenMeteoClient` — `forecast(lat, lon, hourly=..., days=...)`.
- Public, no auth. Fallback only — Aurora / Earth-2 / MAI take priority.
- TTL-cached in-process (10 minutes) to absorb chat retries.

### `mcp_registry`
- Re-exports `McpRegistry` and `TracedMcpClient` from
  `container-app/mcp/registry.py`. The registry discovers tools across all
  configured MCP servers; the traced client wraps every call with a
  per-turn trace buffer suitable for the future tool-trace UI.

## Migration plan

Existing agents currently import `mcp_catalog_client`, `fabric_client`,
and various `AsyncAzureOpenAI` constructors directly. **They keep
working.** New agents (Forecast, Curator, Lineage) should import from
`connectors/` instead. We migrate existing agents one at a time, each
in its own PR, never as a big bang.
