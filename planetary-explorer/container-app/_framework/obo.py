"""On-behalf-of (OBO) helpers.

Centralises the user-assertion extraction + downstream-scope acquisition
pattern that today is duplicated across resilience/site_audit/contextual
agents. Pairs with :func:`fabric_client.exchange_user_token` (or any
future downstream scope) so agents can request "give me a token good
for Fabric for *this* user" with one call.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def extract_user_assertion(headers: dict[str, Any] | None) -> str | None:
    """Pull the user's bearer assertion off the inbound request headers.

    Honours both the EasyAuth ``X-MS-TOKEN-AAD-ACCESS-TOKEN`` header and a
    raw ``Authorization: Bearer ...`` header. Returns ``None`` if neither
    is present.
    """
    if not headers:
        return None
    # Header dicts may be case-sensitive or not depending on framework;
    # try both.
    def _get(name: str) -> str | None:
        v = headers.get(name) or headers.get(name.lower()) or headers.get(name.upper())
        return v if isinstance(v, str) else None

    tok = _get("X-MS-TOKEN-AAD-ACCESS-TOKEN")
    if tok:
        return tok
    auth = _get("Authorization") or _get("authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip() or None
    return None


class OBOContextMixin:
    """Mixin for agents that need an OBO context.

    Stores the user assertion the agent was constructed with and exposes
    helpers for the canonical downstream scope swaps. Concrete agents
    inherit this so they don't each reimplement the dance.
    """

    user_assertion: str | None = None

    def with_user_assertion(self, assertion: str | None) -> "OBOContextMixin":
        self.user_assertion = assertion
        return self

    async def fabric_token(self, scope: str = "https://api.fabric.microsoft.com/.default") -> str:
        """Exchange the stored user assertion for a Fabric-scoped token.

        Falls back to app identity (``acquire_app_token``) if no user
        assertion is available — many Fabric calls in PE use app
        identity because the data exposed is identical for all users.
        """
        try:
            from fabric_client import acquire_app_token, exchange_user_token
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"fabric_client unavailable: {exc}") from exc
        if self.user_assertion:
            try:
                return await exchange_user_token(self.user_assertion, scope)
            except Exception as exc:  # noqa: BLE001
                logger.warning("OBO exchange failed; falling back to app token: %s", exc)
        return await acquire_app_token(scope)
