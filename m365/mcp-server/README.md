# Planetary Explorer Resilience Agent — MCP Server

A Model Context Protocol (MCP) server that wraps the four
`/api/resilience/*` endpoints of the Planetary Explorer backend so any
MCP-aware client (Copilot Studio, Claude Desktop, VS Code, Cursor, ChatGPT
desktop) can call the resilience agent as a tool.

## Tools exposed

| Tool | Backend call |
|---|---|
| `check_resilience_health` | `GET /api/resilience/health` |
| `list_facilities` | `GET /api/resilience/facilities` |
| `assess_resilience` | `POST /api/resilience/assess` |
| `get_resilience_snapshot` | `GET /api/resilience/snapshot` (returns URL) |

## Local run

### One-shot launcher (recommended)

```powershell
cd m365/mcp-server
.\start-mcp.ps1
```

This finds `devtunnel.exe`, sets up the venv, installs deps, generates and
persists a bearer token in `.env`, starts the MCP server, brings up the
public tunnel, and prints the exact Copilot Studio paste values. Ctrl+C
shuts everything down.

Useful flags:

| Flag | Effect |
|---|---|
| `-BackendUrl <url>` | Override the backend tunnel URL |
| `-Port <int>` | Use a different local port (default 8765) |
| `-NewToken` | Rotate the bearer token |
| `-ResetTunnel` | Delete and recreate the devtunnel |

### Manual run
cd m365/mcp-server
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .

# Point at your backend (local or tunnel)
$env:RESILIENCE_API_BASE_URL = "https://<your-backend-tunnel>-8080.use.devtunnels.ms"
$env:RESILIENCE_TUNNEL_SKIP = "1"

# Strongly recommended before exposing the tunnel: set a bearer token
$env:MCP_BEARER_TOKEN = "use-a-long-random-string-here"

python server.py
```

Server starts on `http://0.0.0.0:8765` with the MCP **streamable HTTP**
transport at `/mcp` and an unauthenticated liveness probe at `/healthz`.

Liveness probe:

```powershell
curl http://localhost:8765/healthz   # -> "ok"
```

If `MCP_BEARER_TOKEN` is set, every request to `/mcp` must include:

```
Authorization: Bearer <your-token>
```

The server will respond `401 Unauthorized` otherwise. If the token is
unset, the server logs a `WARNING` on startup and accepts all requests
(development mode only).

## Tests

```powershell
pip install -e ".[dev]"
pytest -q
```

15 tests cover: tool happy paths, structured error mapping
(`backend_error`, `backend_timeout`, `backend_unreachable`), the
devtunnel header injection, snapshot image content blocks, and all four
bearer-token middleware code paths.

## Expose to Copilot Studio via devtunnel

Copilot Studio needs a public HTTPS URL. Open a second tunnel on port 8765:

```powershell
devtunnel create resilience-mcp --allow-anonymous
devtunnel port create resilience-mcp -p 8765 --protocol https
devtunnel host resilience-mcp
```

Copy the public URL (e.g. `https://abc123-8765.use.devtunnels.ms`). The MCP
endpoint is `<that-url>/mcp`.

## Register in Copilot Studio (GCC)

1. Open your agent in `gcc.copilotstudio.microsoft.us`
2. **Tools → + Add a tool → + New tool**
3. Click the **Model Context Protocol** tile in the "Create new" row
4. Fill the form:

    | Field | Value |
    |---|---|
    | Server name | `Planetary Explorer Resilience Agent` |
    | Server description | `Operational resilience assessment for facilities: live weather risk scoring, supply-chain blast radius, BCP playbook retrieval.` |
    | Server URL | `https://<your-tunnel>-8765.use.devtunnels.ms/mcp` |
    | Authentication | `None` (dev) — switch to API key when you deploy |

5. Save. Copilot Studio should auto-discover the four tools.
6. Test from the right-hand pane: *"Which Texas facilities are at risk this week?"*

## Use from VS Code

Add to `.vscode/mcp.json`:

```json
{
  "servers": {
    "planetary-explorer-resilience": {
      "type": "http",
      "url": "http://localhost:8765/mcp"
    }
  }
}
```

## Use from Claude Desktop

Edit `claude_desktop_config.json` (Settings → Developer → Edit Config):

```json
{
  "mcpServers": {
    "planetary-explorer-resilience": {
      "url": "http://localhost:8765/mcp"
    }
  }
}
```

## Environment variables

| Var | Default | Purpose |
|---|---|---|
| `RESILIENCE_API_BASE_URL` | `http://localhost:8080` | Backend root URL |
| `RESILIENCE_API_KEY` | unset | Optional Bearer token forwarded to backend |
| `RESILIENCE_TUNNEL_SKIP` | `0` | Set to `1` when backend is on a devtunnel |
| `MCP_HOST` | `0.0.0.0` | Bind host |
| `MCP_PORT` | `8765` | Bind port |
| `MCP_BEARER_TOKEN` | unset | If set, required on every `/mcp` request |
| `MCP_LOG_LEVEL` | `INFO` | Python logging level |

## Production deploy (later)

`Dockerfile` included. Push to Azure Container Apps, front with Application
Gateway or APIM, swap Copilot Studio auth from `None` → `API key` or
`OAuth 2.0` (Entra), retire the devtunnel.
