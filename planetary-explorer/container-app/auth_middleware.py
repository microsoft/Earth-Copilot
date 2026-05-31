# =============================================================================
# Entra ID Authentication Middleware for FastAPI
# =============================================================================
# Two paths, both verify the user is signed into the Entra tenant:
#
#   (A) PRIMARY — `X-MS-CLIENT-PRINCIPAL` header (production, post-proxy)
#       Set by App Service / Container Apps EasyAuth when the request flows
#       through an auth-gated origin. Base64-encoded JSON with claims that
#       EasyAuth has *already validated*. The backend trusts the header
#       because the network topology guarantees it can only have been
#       injected by EasyAuth (the container is reachable only via the
#       EasyAuth-fronted origin).
#
#   (B) FALLBACK — `Authorization: Bearer <jwt>` (transitional)
#       The current topology has the browser calling the backend container
#       directly, bypassing EasyAuth. While we still operate that way, the
#       frontend forwards the user's `/.auth/me` access_token and we
#       validate signature + tenant issuer here. Audience is checked against
#       an allow-list that includes the UI app, the Fabric API app, and
#       Microsoft Graph — because depending on EasyAuth's scope config the
#       returned token's `aud` can be any of them, but ALL are still
#       AAD-signed proof that the user is authenticated to our tenant.
#
#       This fallback can be removed once the UI App Service proxies /api/*
#       through itself so that EasyAuth headers are injected on every
#       backend request (see `docs/auth-architecture.md`).
#
# Downstream data access (Fabric, OneLake, Power BI) does NOT use the user's
# token. The backend uses its own Managed Identity via `fabric_client`. So
# this middleware's only job is "is this person signed in?" — not "what can
# this person see?".
# =============================================================================

import base64
import json
import os
import logging
from typing import List, Optional, Set

import jwt
from jwt import PyJWKClient

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
TENANT_ID = os.environ.get("AZURE_AD_TENANT_ID", "")
CLIENT_ID = os.environ.get("AZURE_AD_CLIENT_ID", "")
# Fabric OBO API app — when frontend forwards an access_token with this audience.
FABRIC_API_CLIENT_ID = os.environ.get("FABRIC_CLIENT_ID", "")
# Microsoft Graph app id (constant across all tenants). EasyAuth often hands
# back a Graph-scoped access_token from /.auth/me when the login scope is
# `openid profile email offline_access` — those tokens are still signed by
# our tenant so they remain valid proof of authentication.
GRAPH_APP_ID = "00000003-0000-0000-c000-000000000000"

# Separate JWKS endpoints for v1.0 vs v2.0 tokens. AAD signs v1 and v2 tokens
# with overlapping but not identical key sets; pick by the token's `iss` claim.
JWKS_URL_V2 = f"https://login.microsoftonline.com/{TENANT_ID}/discovery/v2.0/keys"
JWKS_URL_V1 = f"https://login.microsoftonline.com/{TENANT_ID}/discovery/keys"
# Cross-tenant common endpoints — useful for Graph-signed tokens whose signing
# key may not appear in any single-tenant JWKS during rotation windows.
JWKS_URL_COMMON_V2 = "https://login.microsoftonline.com/common/discovery/v2.0/keys"
JWKS_URL_COMMON_V1 = "https://login.microsoftonline.com/common/discovery/keys"

# Accept both v1.0 and v2.0 issuer formats
VALID_ISSUERS: List[str] = [
    f"https://login.microsoftonline.com/{TENANT_ID}/v2.0",
    f"https://sts.windows.net/{TENANT_ID}/",
]

# Accepted audiences: the UI app itself, the Fabric OBO API app, and Microsoft
# Graph. We accept Graph because EasyAuth's `/.auth/me` typically returns a
# Graph access_token when the login scope includes `offline_access`. The token
# is still a valid AAD-signed proof of the user's identity, which is all the
# backend needs — downstream Fabric calls use service-principal credentials
# (`fabric_client.acquire_app_token`), not user-OBO.
VALID_AUDIENCES: List[str] = [
    CLIENT_ID,
    f"api://{CLIENT_ID}",
    FABRIC_API_CLIENT_ID,
    f"api://{FABRIC_API_CLIENT_ID}",
    GRAPH_APP_ID,
    f"https://graph.microsoft.com",
    f"https://graph.microsoft.com/",
]

# M365 declarative agent surface — separate app registration so its lifecycle
# (revoke, rescope, secret rotation) is independent from the UI's. Backward
# compatible: if the env var is absent, behavior is unchanged.
M365_APP_CLIENT_ID = os.environ.get("M365_APP_CLIENT_ID")
if M365_APP_CLIENT_ID:
    VALID_AUDIENCES.extend([M365_APP_CLIENT_ID, f"api://{M365_APP_CLIENT_ID}"])

# ---------------------------------------------------------------------------
# Paths that do NOT require authentication
# ---------------------------------------------------------------------------
OPEN_PATHS: Set[str] = {
    "/api/health",
    "/api/config",
    "/api/pro/collections",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/pc_rendering_config.json",
    "/pc_collections_metadata.json",
    "/stac_collections.json",
    "/favicon.ico",
    "/",
}

OPEN_PREFIXES: List[str] = [
    "/assets/",
    "/static/",
    "/api/pro/tile/",
    "/api/pro/tilejson",
    # Mosaic tilejson is synthesized server-side from a search_id and
    # served same-origin to the browser; no user AAD context required
    # (the upstream Pro raster API is talked to via managed identity).
    "/api/pro/mosaic/",
]


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
        # Up to four JWKS clients — one per AAD endpoint variant. Lazy-init.
        self._jwks_clients: dict[str, PyJWKClient] = {}
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

    def _get_jwks(self, url: str) -> PyJWKClient:
        c = self._jwks_clients.get(url)
        if c is None:
            c = PyJWKClient(url, cache_keys=True)
            self._jwks_clients[url] = c
        return c

    def _signing_key_for_token(self, token: str, iss: str):
        """Resolve the signing key for `token` by trying multiple JWKS endpoints.

        AAD's discovery endpoints aren't a single source of truth — depending
        on token version (v1/v2) and audience (your-app vs Graph) the kid
        may only appear in one specific JWKS feed. We try the most-likely
        endpoint first (based on iss claim) then fall back to the others.
        """
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid", "")
        is_v1 = "sts.windows.net" in iss

        # Try tenant-scoped first (matches iss), then cross-tenant common.
        urls = (
            [JWKS_URL_V1, JWKS_URL_V2, JWKS_URL_COMMON_V1, JWKS_URL_COMMON_V2]
            if is_v1
            else [JWKS_URL_V2, JWKS_URL_V1, JWKS_URL_COMMON_V2, JWKS_URL_COMMON_V1]
        )

        last_exc: Exception | None = None
        for url in urls:
            try:
                key = self._get_jwks(url).get_signing_key_from_jwt(token)
                logger.debug("[AUTH] kid=%s resolved via %s", kid, url)
                return key
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                continue
        logger.warning("[AUTH] kid=%s NOT FOUND in any JWKS feed (iss=%s)", kid, iss)
        assert last_exc is not None
        raise last_exc

    # -----------------------------------------------------------------------
    # Path A: EasyAuth-injected X-MS-CLIENT-PRINCIPAL header
    # -----------------------------------------------------------------------
    # EasyAuth has *already* validated the user before injecting this header.
    # The container trusts the header because the EasyAuth-fronted ingress is
    # the only network path that can set it. Tenant id is still verified so
    # we don't accept a header forged with a foreign tenant's principal.
    @staticmethod
    def _principal_from_easyauth_header(header_b64: str) -> Optional[dict]:
        try:
            decoded = base64.b64decode(header_b64).decode("utf-8")
            principal = json.loads(decoded)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[AUTH] X-MS-CLIENT-PRINCIPAL decode failed: %s", exc)
            return None
        # EasyAuth principal shape:
        #   { auth_typ, name_typ, role_typ, claims: [ {typ, val}, ... ] }
        claims = {c.get("typ"): c.get("val") for c in principal.get("claims", [])}
        tid = (
            claims.get("http://schemas.microsoft.com/identity/claims/tenantid")
            or claims.get("tid")
        )
        if tid and tid != TENANT_ID:
            logger.warning("[AUTH] X-MS-CLIENT-PRINCIPAL wrong tenant: %s", tid)
            return None
        return {
            "sub": claims.get("http://schemas.microsoft.com/identity/claims/objectidentifier")
                or claims.get("oid")
                or claims.get("sub"),
            "tid": tid,
            "preferred_username": (
                claims.get("preferred_username")
                or claims.get("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/upn")
                or claims.get("upn")
                or claims.get("name")
            ),
            "name": claims.get("name"),
            "claims": claims,
            "auth_source": "easyauth_header",
        }

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

        # --- Dev-mode bypass for M365 / Copilot Studio testing before
        #     Entra admin consent is in place. Logs a warning every request
        #     so this can't quietly leak into production.
        if os.environ.get("RESILIENCE_DEV_BYPASS_AUTH", "0").lower() in ("1", "true", "yes", "on"):
            logger.warning(
                "[AUTH] RESILIENCE_DEV_BYPASS_AUTH active — bypassing auth on %s %s",
                request.method,
                path,
            )
            request.state.user = {
                "sub": "dev-bypass",
                "preferred_username": "dev-bypass@local",
                "auth_source": "dev_bypass",
            }
            return await call_next(request)

        # ----------------------------------------------------------------
        # Path A: EasyAuth header (preferred — used when the request comes
        # through an EasyAuth-fronted origin like the UI App Service proxy)
        # ----------------------------------------------------------------
        easyauth_header = request.headers.get("X-MS-CLIENT-PRINCIPAL") or request.headers.get(
            "x-ms-client-principal"
        )
        if easyauth_header:
            principal = self._principal_from_easyauth_header(easyauth_header)
            if principal is not None:
                request.state.user = principal
                logger.debug(
                    "[AUTH] OK (easyauth) — user=%s on %s",
                    principal.get("preferred_username") or principal.get("sub"),
                    path,
                )
                return await call_next(request)
            # If the header was present but malformed, fall through to bearer
            # rather than 401 — gives the frontend a chance to retry with a
            # token if the proxy is misconfigured.

        # ----------------------------------------------------------------
        # Path B: bearer JWT (transitional — used while the browser still
        # talks directly to the backend container)
        # ----------------------------------------------------------------
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
            # Peek at the issuer (unverified) so we pick the right JWKS endpoint
            unverified = jwt.decode(token, options={"verify_signature": False})
            iss = unverified.get("iss", "")
            signing_key = self._signing_key_for_token(token, iss)
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
            payload["auth_source"] = "bearer_jwt"
            request.state.user = payload
            logger.debug(
                f"[AUTH] OK (bearer) — user={payload.get('preferred_username') or payload.get('upn') or payload.get('sub')} on {path}"
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
            # On any other failure, log the token header + claims (no signature)
            # so we can diagnose without round-tripping through DevTools.
            try:
                hdr = jwt.get_unverified_header(token)
                claims = jwt.decode(token, options={"verify_signature": False})
                logger.warning(
                    "[AUTH] 401 — bearer validation failed on %s: %s | "
                    "header=%s | iss=%s aud=%s ver=%s appid=%s upn=%s",
                    path, e, hdr,
                    claims.get("iss"), claims.get("aud"), claims.get("ver"),
                    claims.get("appid"), claims.get("upn") or claims.get("preferred_username"),
                )
            except Exception:
                logger.warning(f"[AUTH] 401 — bearer validation failed on {path}: {e} (token undecodable)")
            return JSONResponse(
                status_code=401,
                content={"error": f"Token validation failed: {str(e)}"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        return await call_next(request)
