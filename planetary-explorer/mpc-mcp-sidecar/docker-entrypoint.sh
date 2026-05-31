#!/bin/sh
# =============================================================================
# docker-entrypoint.sh
#
# Acquire a managed-identity-backed token cache for the Azure CLI, then exec
# the bridge. The vendored upstream binary uses AzureCliCredential for its
# GeoCatalog data-plane calls; AzureCliCredential reads the token cache that
# ``az login`` populates. Running ``az login --identity`` here means MI just
# works without patching upstream auth code.
#
# Behaviour:
#   - In a Container App with system-assigned MI: ``az login --identity``
#     (no client id) hits IMDS and caches a token.
#   - In a Container App with user-assigned MI: set
#     ``MPC_MCP_IDENTITY_CLIENT_ID`` to the user-assigned identity's client
#     id; we pass ``--username`` so the right MI is picked.
#   - Locally (dev box, no IMDS): set ``MPC_MCP_SKIP_AZ_LOGIN_IDENTITY=1``
#     and the existing ``az login`` session in your user profile is used.
# =============================================================================
set -eu

if [ "${MPC_MCP_SKIP_AZ_LOGIN_IDENTITY:-0}" = "1" ]; then
    echo "[entrypoint] MPC_MCP_SKIP_AZ_LOGIN_IDENTITY=1; relying on existing az session"
elif [ -n "${MPC_MCP_IDENTITY_CLIENT_ID:-}" ]; then
    echo "[entrypoint] az login --identity --username <user-assigned MI>"
    az login --identity --username "${MPC_MCP_IDENTITY_CLIENT_ID}" --output none
else
    echo "[entrypoint] az login --identity (system-assigned MI)"
    az login --identity --output none
fi

# exec so signals (SIGTERM from Container Apps) flow directly to Node.
exec node /app/bridge.mjs
