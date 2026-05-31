# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

"""
Cloud Environment Configuration for Azure Commercial and Azure Government

This module centralizes all cloud-specific endpoints, token scopes, and domain suffixes
so that the rest of the application can be cloud-agnostic. Set the AZURE_CLOUD_ENVIRONMENT
environment variable to 'Government' to switch all endpoints to Azure Government equivalents.

Usage:
    from cloud_config import cloud_cfg

    # Token scopes
    token = credential.get_token(cloud_cfg.COGNITIVE_SERVICES_SCOPE)
    
    # Azure Maps URLs
    url = f"{cloud_cfg.AZURE_MAPS_BASE_URL}/search/address/json"
    
    # STAC endpoint
    stac_url = cloud_cfg.STAC_API_URL
"""

import os
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CloudEnvironmentConfig:
    """Immutable configuration for a specific Azure cloud environment."""

    # --- Identity ---
    environment_name: str  # "Commercial" or "Government"

    # --- Cognitive Services / Azure OpenAI ---
    cognitive_services_scope: str  # Token scope for Azure OpenAI / AI Services
    openai_domain_suffix: str  # e.g. "openai.azure.com" or "openai.azure.us"
    ai_services_domain_suffix: str  # e.g. "services.ai.azure.com" or "services.ai.azure.us"

    # --- Azure Maps ---
    azure_maps_base_url: str  # e.g. "https://atlas.microsoft.com" or "https://atlas.microsoft.us"
    azure_maps_scope: str  # Token scope for Managed Identity auth

    # --- STAC / Planetary Computer ---
    stac_api_url: str  # Primary STAC search endpoint
    stac_catalog_url: str  # STAC catalog root (for browsing collections)
    pc_data_api_url: str  # Tile/preview rendering API

    # --- Storage ---
    blob_storage_suffix: str  # e.g. "blob.core.windows.net" or "blob.core.usgovcloudapi.net"
    storage_scope: str  # Token scope for storage access

    # --- Container Apps ---
    container_apps_suffix: str  # e.g. "azurecontainerapps.io" or "azurecontainerapps.us"

    # --- Portal & Entra ---
    portal_url: str
    entra_login_url: str

    # --- Search ---
    search_suffix: str  # e.g. "search.windows.net" or "search.windows.us"

    # --- Azure Resource Manager ---
    arm_endpoint: str


# ============================================================================
# Pre-built configurations
# ============================================================================

COMMERCIAL_CONFIG = CloudEnvironmentConfig(
    environment_name="Commercial",
    # Cognitive Services
    cognitive_services_scope="https://cognitiveservices.azure.com/.default",
    openai_domain_suffix="openai.azure.com",
    ai_services_domain_suffix="services.ai.azure.com",
    # Azure Maps
    azure_maps_base_url="https://atlas.microsoft.com",
    azure_maps_scope="https://atlas.microsoft.com/.default",
    # STAC / Planetary Computer (open data catalog)
    stac_api_url="https://planetarycomputer.microsoft.com/api/stac/v1/search",
    stac_catalog_url="https://planetarycomputer.microsoft.com/api/stac/v1",
    pc_data_api_url="https://planetarycomputer.microsoft.com/api/data/v1",
    # Storage
    blob_storage_suffix="blob.core.windows.net",
    storage_scope="https://storage.azure.com/.default",
    # Container Apps
    container_apps_suffix="azurecontainerapps.io",
    # Portal & Entra
    portal_url="https://portal.azure.com",
    entra_login_url="https://login.microsoftonline.com",
    # Search
    search_suffix="search.windows.net",
    # ARM
    arm_endpoint="https://management.azure.com",
)

GOVERNMENT_CONFIG = CloudEnvironmentConfig(
    environment_name="Government",
    # Cognitive Services
    cognitive_services_scope="https://cognitiveservices.azure.us/.default",
    openai_domain_suffix="openai.azure.us",
    ai_services_domain_suffix="services.ai.azure.us",
    # Azure Maps
    azure_maps_base_url="https://atlas.microsoft.us",
    azure_maps_scope="https://atlas.microsoft.us/.default",
    # STAC / Planetary Computer Pro (Gov GeoCatalog — override with STAC_API_URL env var)
    # NOTE: In Gov, customers deploy their own Planetary Computer Pro GeoCatalog instance.
    # The open Planetary Computer (planetarycomputer.microsoft.com) is also accessible from Gov.
    # Set STAC_API_URL to your GeoCatalog instance URL for private data.
    stac_api_url="https://planetarycomputer.microsoft.com/api/stac/v1/search",  # default: open PC still works from Gov
    stac_catalog_url="https://planetarycomputer.microsoft.com/api/stac/v1",
    pc_data_api_url="https://planetarycomputer.microsoft.com/api/data/v1",
    # Storage
    blob_storage_suffix="blob.core.usgovcloudapi.net",
    storage_scope="https://storage.usgovcloudapi.net/.default",
    # Container Apps
    container_apps_suffix="azurecontainerapps.us",
    # Portal & Entra
    portal_url="https://portal.azure.us",
    entra_login_url="https://login.microsoftonline.us",
    # Search
    search_suffix="search.windows.us",
    # ARM
    arm_endpoint="https://management.usgovcloudapi.net",
)


def _resolve_config() -> CloudEnvironmentConfig:
    """
    Resolve the cloud environment configuration from environment variables.
    
    Priority:
        1. AZURE_CLOUD_ENVIRONMENT = 'Government' | 'Commercial' (default)
        2. Individual overrides via env vars (e.g. STAC_API_URL)
    """
    env = os.getenv("AZURE_CLOUD_ENVIRONMENT", "Commercial").strip()

    if env.lower() in ("government", "gov", "usgovernment", "azureusgovernment"):
        base = GOVERNMENT_CONFIG
        logger.info("  Cloud environment: Azure Government")
    else:
        base = COMMERCIAL_CONFIG
        logger.info("  Cloud environment: Azure Commercial")

    # Allow per-service overrides via env vars (useful for hybrid scenarios or
    # customers who deploy Planetary Computer Pro with a custom GeoCatalog URL)
    stac_api_override = os.getenv("STAC_API_URL")
    if stac_api_override:
        # Build a new config with the override
        # Since the dataclass is frozen, we create a new instance
        override_fields = {
            "stac_api_url": stac_api_override.rstrip("/") + ("/search" if not stac_api_override.rstrip("/").endswith("/search") else ""),
            "stac_catalog_url": stac_api_override.rstrip("/").replace("/search", ""),
        }
        # Rebuild with overrides
        base = CloudEnvironmentConfig(
            **{k: override_fields.get(k, getattr(base, k)) for k in base.__dataclass_fields__}
        )
        logger.info(f"  STAC API overridden: {base.stac_api_url}")

    return base


# ============================================================================
# Module-level singleton — import this everywhere
# ============================================================================
cloud_cfg: CloudEnvironmentConfig = _resolve_config()
