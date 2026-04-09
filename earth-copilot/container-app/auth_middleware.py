# =============================================================================
# Entra ID (Azure AD) JWT Authentication Middleware for FastAPI
# =============================================================================
# Validates Bearer tokens from the frontend (forwarded from App Service EasyAuth).
# Replaces Container Apps EasyAuth which does not reliably support excludedPaths.
#
# How it works:
#   1. Frontend App Service has EasyAuth enabled — user logs in via Entra ID
#   2. Frontend JS reads the id_token from /.auth/me and sends it as
#      Authorization: Bearer <token> on every API call
#   3. This middleware validates the token signature (JWKS), audience, issuer,
#      and expiry on protected routes
#   4. Health check, docs, and static assets are excluded from auth
#
# Configuration (env vars):
#   AZURE_AD_TENANT_ID  — Entra tenant (default: Earth Copilot tenant)
#   AZURE_AD_CLIENT_ID  — App registration client ID (same as frontend)
#   DISABLE_AUTH        — Set to "true" to skip all auth (local dev)
# =============================================================================

import os
import logging
from typing import List, Set

import jwt
from jwt import PyJWKClient

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
TENANT_ID = os.environ.get(
    "AZURE_AD_TENANT_ID", "c6ebf7d6-138f-4295-ac73-89296b95a8a3"
)
CLIENT_ID = os.environ.get(
    "AZURE_AD_CLIENT_ID", "e02449b1-4ece-460c-a459-9935bae807ee"
)
JWKS_URL = (
    f"https://login.microsoftonline.com/{TENANT_ID}/discovery/v2.0/keys"
)

# Accept both v1.0 and v2.0 token formats (depends on how frontend EasyAuth
# is configured — v1.0 uses sts.windows.net, v2.0 uses login.microsoftonline.com)
VALID_ISSUERS: List[str] = [
    f"https://login.microsoftonline.com/{TENANT_ID}/v2.0",
    f"https://sts.windows.net/{TENANT_ID}/",
]

# Audiences — the app registration client ID in both raw and api:// form
VALID_AUDIENCES: List[str] = [CLIENT_ID, f"api://{CLIENT_ID}"]

# ---------------------------------------------------------------------------
# Paths that do NOT require authentication
# ---------------------------------------------------------------------------
OPEN_PATHS: Set[str] = {
    "/api/health",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/pc_rendering_config.json",
    "/pc_collections_metadata.json",
    "/stac_collections.json",
    "/favicon.ico",
    "/",
}

OPEN_PREFIXES: List[str] = ["/assets/", "/static/"]


def _is_open_path(path: str) -> bool:
    """Return True if the path should be accessible without auth."""
    if path in OPEN_PATHS:
        return True
    return any(path.startswith(prefix) for prefix in OPEN_PREFIXES)


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
class EntraAuthMiddleware(BaseHTTPMiddleware):
    """
    Starlette middleware that validates Entra ID Bearer tokens on protected
    routes.  Unauthenticated requests to protected routes receive 401.
    """

    def __init__(self, app):
        super().__init__(app)
        self._jwks_client: PyJWKClient | None = None
        self._enabled = os.environ.get("DISABLE_AUTH", "").lower() not in (
            "true",
            "1",
            "yes",
        )
        if self._enabled:
            logger.info(
                "[AUTH] Entra ID auth middleware ENABLED  "
                f"(tenant={TENANT_ID}, client={CLIENT_ID})"
            )
        else:
            logger.info("[AUTH] Entra ID auth middleware DISABLED (DISABLE_AUTH=true)")

    @property
    def jwks_client(self) -> PyJWKClient:
        """Lazy-init the JWKS client so startup doesn't fail if AAD is unreachable."""
        if self._jwks_client is None:
            self._jwks_client = PyJWKClient(JWKS_URL, cache_keys=True)
        return self._jwks_client

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # --- Always allow open paths ---
        if _is_open_path(path):
            return await call_next(request)

        # --- Always allow CORS preflight (OPTIONS) ---
        if request.method == "OPTIONS":
            return await call_next(request)

        # --- Auth disabled — pass through ---
        if not self._enabled:
            return await call_next(request)

        # --- Extract Bearer token ---
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            logger.warning(f"[AUTH] 401 — missing Bearer token on {request.method} {path}")
            return JSONResponse(
                status_code=401,
                content={"error": "Missing or invalid Authorization header"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        token = auth_header[len("Bearer "):]

        # --- Validate JWT ---
        try:
            signing_key = self.jwks_client.get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=VALID_AUDIENCES,
                options={
                    "verify_exp": True,
                    "verify_iss": False,  # manual issuer check below (accept v1 + v2)
                },
            )

            # Manual issuer validation (v1.0 and v2.0)
            iss = payload.get("iss", "")
            if iss not in VALID_ISSUERS:
                logger.warning(f"[AUTH] 401 — invalid issuer '{iss}' on {path}")
                return JSONResponse(
                    status_code=401,
                    content={"error": f"Invalid token issuer: {iss}"},
                )

            # Attach user claims to request state for downstream handlers
            request.state.user = payload
            logger.debug(
                f"[AUTH] OK — user={payload.get('preferred_username') or payload.get('upn') or payload.get('sub')} on {path}"
            )

        except jwt.ExpiredSignatureError:
            logger.warning(f"[AUTH] 401 — expired token on {path}")
            return JSONResponse(
                status_code=401,
                content={"error": "Token has expired"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        except jwt.InvalidAudienceError:
            logger.warning(f"[AUTH] 401 — invalid audience on {path}")
            return JSONResponse(
                status_code=401,
                content={"error": "Invalid token audience"},
            )

        except Exception as e:
            logger.warning(f"[AUTH] 401 — token validation failed on {path}: {e}")
            return JSONResponse(
                status_code=401,
                content={"error": f"Token validation failed: {str(e)}"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        return await call_next(request)
