"""Provider registry — discovers configured weather model providers
from environment variables, exposes capability-based selection.
"""
from __future__ import annotations

import logging
from functools import lru_cache

from .aurora import AuroraProvider
from .earth2 import Earth2FCNProvider
from .mai_weather import MaiWeatherProvider
from .provider import Capability, WeatherModelProvider

logger = logging.getLogger(__name__)


class WeatherProviderRegistry:
    """Discovers + holds the set of providers configured for this env."""

    def __init__(self, providers: list[WeatherModelProvider]) -> None:
        self._providers = providers
        self._by_id = {p.provider_id: p for p in providers}

    @classmethod
    def discover(cls) -> "WeatherProviderRegistry":
        """Build a registry from env vars. Order matters for default selection."""
        providers: list[WeatherModelProvider] = []
        for factory in (
            AuroraProvider.try_from_env,
            Earth2FCNProvider.try_from_env,
            MaiWeatherProvider.try_from_env,
        ):
            try:
                p = factory()
            except Exception as exc:  # noqa: BLE001
                logger.warning("provider %s discovery failed: %s", factory, exc)
                continue
            if p is not None:
                providers.append(p)
        logger.info("weather provider registry discovered %d providers: %s",
                    len(providers), [p.provider_id for p in providers])
        return cls(providers)

    # ── Accessors ────────────────────────────────────────────────────────
    @property
    def all(self) -> list[WeatherModelProvider]:
        return list(self._providers)

    def get(self, provider_id: str) -> WeatherModelProvider | None:
        return self._by_id.get(provider_id)

    def supporting(self, capability: Capability) -> list[WeatherModelProvider]:
        return [p for p in self._providers if capability in p.capabilities]

    def select(
        self,
        *,
        required: tuple[Capability, ...] = (),
        preferred_ids: tuple[str, ...] = (),
    ) -> list[WeatherModelProvider]:
        """Return providers matching all required caps, ordered by preferred_ids first."""
        eligible = [
            p for p in self._providers
            if all(c in p.capabilities for c in required)
        ]
        if not preferred_ids:
            return eligible
        rank = {pid: i for i, pid in enumerate(preferred_ids)}
        return sorted(
            eligible,
            key=lambda p: rank.get(p.provider_id, len(preferred_ids)),
        )


@lru_cache(maxsize=1)
def get_registry() -> WeatherProviderRegistry:
    """Cached singleton — built once per process."""
    return WeatherProviderRegistry.discover()
