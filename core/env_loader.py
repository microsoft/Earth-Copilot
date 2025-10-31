# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

"""
Centralized environment variable loader for Earth Copilot.
This module ensures all services load from the root .env file consistently.
"""

import os
from pathlib import Path
from dotenv import load_dotenv


def load_root_env():
    """
    Load environment variables from the root .env file.
    This function should be called by all modules that need environment variables.
    """
    # Get the root directory (3 levels up from this file)
    root_dir = Path(__file__).parent.parent.parent
    env_path = root_dir / ".env"
    
    if env_path.exists():
        print(f"[OK] Loading environment from: {env_path}")
        load_dotenv(env_path, override=True)
        return True
    else:
        print(f"[WARNING] Root .env file not found at: {env_path}")
        print("Using system environment variables")
        return False


def get_env_var(key: str, default: str = None, required: bool = False) -> str:
    """
    Get an environment variable with optional default and validation.
    
    Args:
        key: Environment variable name
        default: Default value if not found
        required: If True, raises ValueError if not found
        
    Returns:
        Environment variable value
        
    Raises:
        ValueError: If required=True and variable not found
    """
    value = os.getenv(key, default)
    
    if required and not value:
        raise ValueError(f"Required environment variable '{key}' not found")
    
    return value


def validate_environment():
    """
    Validate that all required environment variables are present.
    Returns a dict with validation results.
    """
    required_vars = [
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_API_KEY",
        "AOAI_ENDPOINT",
        "AOAI_KEY"
    ]
    
    validation_results = {
        "valid": True,
        "missing": [],
        "present": []
    }
    
    for var in required_vars:
        value = os.getenv(var)
        if value:
            validation_results["present"].append(var)
        else:
            validation_results["missing"].append(var)
            validation_results["valid"] = False
    
    return validation_results


# Auto-load environment when this module is imported
load_root_env()