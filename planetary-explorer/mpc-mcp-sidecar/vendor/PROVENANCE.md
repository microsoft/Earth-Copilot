# Vendored upstream: GeoCatalog STAC MCP Server (server_main.js)

## Source

- Distribution: VS Code extension `ms-planetarycomputer.mpc-pro-mcp-tools` v1.0.9
- Marketplace ID: `ms-planetarycomputer.mpc-pro-mcp-tools`
- Inner package: `geocatalog-mcp-server` v1.0.9 (the `server/` directory inside the VSIX)
- Upstream repo (docs only, no source): https://github.com/Azure/microsoft-planetary-computer-pro/tree/main/tools/mpc_mcp_server
- License: **MIT** (declared in `package.upstream.json` and the marketplace listing)
- Captured: 2026-05-20 from local install at
  `C:\Users\<user>\.vscode\extensions\ms-planetarycomputer.mpc-pro-mcp-tools-1.0.9\server\`

## Why we vendor

Microsoft ships the MCP server only as a pre-built bundle inside the VSIX --
the GitHub repository's `tools/mpc_mcp_server/` directory contains only docs.
There is no `git clone && npm run build` path. To get an auditable,
container-deployable copy we must vendor.

## What we vendor

| File | Purpose |
|---|---|
| `server_main.js` | The bundled (esbuild-produced) Node ESM entrypoint. ~1 MB. |
| `package.upstream.json` | Original inner `package.json`. Used to know which deps to install via `npm ci` so the bundle's runtime `import "@azure/identity"` etc. resolve. |
| `package-lock.upstream.json` | Original inner lockfile. Used by our Dockerfile so we get the same dep versions Microsoft tested with. |

We do **not** vendor `node_modules/` -- the Dockerfile reproduces it via
`npm ci` from the upstream lockfile, which gives us a deterministic and
auditable tree.

## Transport

The bundled binary speaks **stdio only** (`StdioServerTransport` from
`@modelcontextprotocol/sdk`). To expose it over `streamable-http` for our
Planetary Explorer backend, we run it as a child of `bridge.mjs` (one level up)
which proxies between stdio and HTTP using the same MCP SDK.

## Credentials

The bundle uses `AzureCliCredential` from `@azure/identity` for its
GeoCatalog data-plane token. We do **not** patch the bundle. Instead, our
Docker image runs `az login --identity` at startup so the system-assigned
managed identity populates the Azure CLI token cache that
`AzureCliCredential` reads. See `../docker-entrypoint.sh`.

## Upgrade procedure

To bump to a newer upstream:

1. Install the newer VSIX in VS Code or download via the Marketplace API.
2. Re-copy `server_main.js`, `package.json` (→ `package.upstream.json`),
   and `package-lock.json` (→ `package-lock.upstream.json`) from the
   extension's `server/` folder.
3. Inspect the diff in this folder; if the bundle adds new auth paths
   beyond `AzureCliCredential` / `DefaultAzureCredential`, confirm the
   entrypoint still satisfies them.
4. Bump the image tag (e.g. `planetary-explorer-mpc-mcp:v1.0.9` → `…:v1.1.0`)
   in `infra/main.bicep` `param mpcMcpImageName`.
5. Update this file's "Captured" date and version.

## MIT attribution

The MIT license text from the upstream is reproduced unchanged in
`LICENSE-UPSTREAM` (sibling file).
