# syntax=docker/dockerfile:1.7
# =============================================================================
# Planetary Explorer -- MPC Pro MCP sidecar image (Option A: vendor + bridge).
#
# Components inside the image:
#   * /app/vendor/server_main.js  -- Microsoft GeoCatalog STAC MCP Server v1.0.9
#                                    (MIT, from the VS Code extension VSIX; see
#                                    vendor/PROVENANCE.md). stdio MCP only.
#   * /app/bridge.mjs             -- Our streamable-HTTP <-> stdio proxy. Uses
#                                    the same @modelcontextprotocol/sdk that
#                                    the vendored binary depends on.
#   * /app/node_modules           -- Installed via ``npm ci`` from the upstream
#                                    lockfile so the dep tree is byte-for-byte
#                                    what Microsoft tested with.
#   * az CLI                      -- Used at startup (``az login --identity``)
#                                    so the upstream's AzureCliCredential finds
#                                    a token cache backed by the workload's
#                                    managed identity. We do NOT patch upstream.
# =============================================================================

ARG NODE_IMAGE=node:20-bookworm-slim

# -----------------------------------------------------------------------------
# Stage 1: install Node deps from the upstream lockfile.
# Done in a separate stage so the runtime layer doesn't include npm caches.
# -----------------------------------------------------------------------------
FROM ${NODE_IMAGE} AS install

WORKDIR /app

# Re-use Microsoft's exact dep tree by renaming their lockfile/package.json
# into the conventional names ``npm ci`` expects.
COPY vendor/package.upstream.json      /app/package.json
COPY vendor/package-lock.upstream.json /app/package-lock.json

# --no-audit / --no-fund silence cosmetic output that breaks ACR build logs.
# --omit=dev because the vendored bundle only needs runtime deps.
# NOTE: no BuildKit cache mount here -- ``az acr build`` runs the classic
# Docker engine which rejects ``RUN --mount`` syntax.
RUN npm ci --omit=dev --no-audit --no-fund

# Vendored binary + provenance + our bridge code.
COPY vendor/server_main.js     /app/vendor/server_main.js
COPY vendor/PROVENANCE.md      /app/vendor/PROVENANCE.md
COPY vendor/LICENSE-UPSTREAM   /app/vendor/LICENSE-UPSTREAM
COPY bridge.mjs                /app/bridge.mjs
COPY healthcheck.mjs           /app/healthcheck.mjs

# -----------------------------------------------------------------------------
# Stage 2: runtime image with Azure CLI + tini for signal handling.
# -----------------------------------------------------------------------------
FROM ${NODE_IMAGE} AS runtime

ENV NODE_ENV=production \
    MCP_HTTP_HOST=0.0.0.0 \
    MCP_HTTP_PORT=8080 \
    MPC_MCP_VENDOR_BIN=/app/vendor/server_main.js \
    AZURE_CONFIG_DIR=/home/mcp/.azure

# Install Azure CLI via Microsoft's official Debian script + tini for PID-1
# signal forwarding. The CLI is used only at startup to populate the token
# cache that AzureCliCredential reads -- after that it is idle.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        ca-certificates curl tini; \
    curl -sL https://aka.ms/InstallAzureCLIDeb | bash; \
    apt-get clean; \
    rm -rf /var/lib/apt/lists/*

# Non-root user (uid 10001 to avoid clashes with host UIDs).
RUN groupadd --system --gid 10001 mcp \
 && useradd  --system --uid 10001 --gid mcp --create-home --shell /usr/sbin/nologin mcp

WORKDIR /app
COPY --from=install --chown=mcp:mcp /app /app
# NOTE: ``--chmod`` on COPY requires BuildKit; ``az acr build`` uses the
# classic Docker engine, so we set the mode in a separate RUN.
COPY --chown=0:0 docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod 0755 /usr/local/bin/docker-entrypoint.sh

USER mcp
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=45s \
    CMD ["node", "/app/healthcheck.mjs"]

# tini handles PID-1 + signal forwarding; the entrypoint does ``az login
# --identity`` then exec's node bridge.mjs.
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/docker-entrypoint.sh"]
