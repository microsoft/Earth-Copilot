# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

"""
Core configuration for Earth Copilot application.
"""
import os
from typing import Optional
from .env_loader import load_root_env, get_env_var, validate_environment

# Ensure environment is loaded
load_root_env()


class Settings:
    """Application settings using simple environment variable access."""
    
    def __init__(self):
        # App Configuration
        self.app_name = "Earth Copilot"
        self.app_version = "2.0.0"
        self.debug = os.getenv("DEBUG", "false").lower() in ("1", "true", "yes")
        self.port = int(os.getenv("PORT", "8080"))
        self.host = os.getenv("HOST", "0.0.0.0")
        
        # Azure OpenAI Configuration - using your existing variable names
        self.azure_openai_endpoint = os.getenv("AOAI_ENDPOINT")
        self.azure_openai_api_key = os.getenv("AOAI_KEY")
        self.azure_openai_api_version = os.getenv("AOAI_API_VERSION", "2024-02-01")
        self.azure_openai_deployment_name = os.getenv("AOAI_DEPLOYMENT", "gpt-5")
        
        # Additional properties for AI service compatibility
        self.AOAI_ENDPOINT = self.azure_openai_endpoint
        self.AOAI_KEY = self.azure_openai_api_key
        self.AOAI_API_VERSION = self.azure_openai_api_version
        self.AOAI_DEPLOYMENT = self.azure_openai_deployment_name
        
        # Foundry Model Router Configuration
        self.foundry_model_router = os.getenv("FOUNDRY_MODEL_ROUTER")
        self.foundry_hub_key = os.getenv("FOUNDRY_HUB_KEY")
        self.foundry_project_id = os.getenv("FOUNDRY_PROJECT_ID")
        self.foundry_project_name = os.getenv("FOUNDRY_PROJECT_NAME")
        self.foundry_project_key = os.getenv("FOUNDRY_PROJECT_KEY")
        
        # Azure AI Search Configuration
        self.ai_search_endpoint = os.getenv("AI_SEARCH_ENDPOINT")
        self.ai_search_key = os.getenv("AI_SEARCH_KEY")
        
        # Azure Maps Configuration
        self.azure_maps_subscription_key = os.getenv("AZURE_MAPS_SUBSCRIPTION_KEY")
        self.azure_maps_client_id = os.getenv("AZURE_MAPS_CLIENT_ID")
        
        # Storage Configuration
        self.storage_account_name = os.getenv("STORAGE_ACCOUNT_NAME")
        self.storage_account_key = os.getenv("STORAGE_ACCOUNT_KEY")
        self.storage_container_name = os.getenv("STORAGE_CONTAINER_NAME")
        
        # Alternative OpenAI Configuration (fallback)
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-5")
        
        # Azure Configuration
        self.azure_tenant_id = os.getenv("AZURE_TENANT_ID")
        self.azure_client_id = os.getenv("AZURE_CLIENT_ID")
        self.azure_client_secret = os.getenv("AZURE_CLIENT_SECRET")
        
        # Planetary Computer / STAC Configuration
        self.planetary_computer_subscription_key = os.getenv("PLANETARY_COMPUTER_SUBSCRIPTION_KEY")
        self.stac_api_url = os.getenv("PLANETARY_COMPUTER_STAC_URL", "https://planetarycomputer.microsoft.com/api/stac/v1")
        
        # Monitoring
        self.application_insights_connection_string = os.getenv("APPLICATION_INSIGHTS_CONNECTION_STRING")
        
        # CORS Settings
        self.allow_cors = os.getenv("ALLOW_CORS", "1").lower() in ("1", "true", "yes")
        
        # Redis Configuration
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    
    @property
    def cors_origins_list(self) -> list:
        """Get CORS origins as a list."""
        cors_env = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173")
        return [origin.strip() for origin in cors_env.split(",") if origin.strip()]


# Global settings instance
settings = Settings()
