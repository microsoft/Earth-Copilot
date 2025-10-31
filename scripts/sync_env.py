#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

"""
Sync environment variables from root .env to React UI .env
This script copies relevant environment variables to the React UI,
prefixing them with VITE_ as required by Vite.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

def sync_env_to_react():
    """Sync environment variables from root .env to React UI .env"""
    
    # Load root .env
    script_dir = Path(__file__).parent
    root_dir = script_dir.parent  # Go up one level from scripts/ to root
    root_env_path = root_dir / ".env"
    react_env_path = root_dir / "earth-copilot" / "react-ui" / ".env"
    
    if not root_env_path.exists():
        print(f"❌ Root .env file not found at: {root_env_path}")
        print(f"📁 Current working directory: {Path.cwd()}")
        print(f"📁 Script directory: {script_dir}")
        print(f"📁 Root directory: {root_dir}")
        return False
    
    print(f"✅ Found .env file at: {root_env_path}")
    
    # Load environment variables using override=True
    result = load_dotenv(root_env_path, override=True)
    print(f"🔧 dotenv load result: {result}")
    
    # Also try manual parsing
    env_vars = {}
    try:
        with open(root_env_path, 'r') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    env_vars[key.strip()] = value.strip()
                    os.environ[key.strip()] = value.strip()
        print(f"🔧 Manually parsed {len(env_vars)} variables")
    except Exception as e:
        print(f"❌ Error parsing .env file: {e}")
    
    # Debug: Show what variables are loaded
    print(f"📋 Environment variables after loading:")
    azure_vars = {}
    for key in os.environ:
        if any(keyword in key.upper() for keyword in ['AZURE', 'SEARCH', 'MAPS', 'OPENAI', 'AOAI']):
            azure_vars[key] = os.environ[key]
            print(f"   {key}={'*' * min(len(os.environ[key]), 10) if os.environ[key] else 'None'}")
    
    if not azure_vars:
        print("   No Azure-related variables found!")
        print(f"   Sample of all env vars: {list(os.environ.keys())[:5]}")
    print()
    
    # Map of root env vars to React env vars (with VITE_ prefix)
    env_mapping = {
        "AZURE_MAPS_SUBSCRIPTION_KEY": "VITE_AZURE_MAPS_SUBSCRIPTION_KEY",
        "AZURE_MAPS_CLIENT_ID": "VITE_AZURE_MAPS_CLIENT_ID",
        "SEARCH_ENDPOINT": "VITE_AZURE_SEARCH_ENDPOINT", 
        "SEARCH_API_KEY": "VITE_AZURE_SEARCH_API_KEY",
        "SEARCH_INDEX_NAME": "VITE_AZURE_SEARCH_INDEX",
        "AZURE_OPENAI_ENDPOINT": "VITE_AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_API_KEY": "VITE_AZURE_OPENAI_API_KEY"
    }
    
    # Additional React-specific variables
    react_specific = {
        "VITE_API_BASE_URL": "http://localhost:7071"
    }
    
    # Create React .env content
    react_env_content = [
        "# Auto-generated from root .env - DO NOT EDIT MANUALLY",
        "# Run sync_env.py to update this file",
        "",
        "# Backend API Configuration",
        f"VITE_API_BASE_URL={react_specific['VITE_API_BASE_URL']}",
        ""
    ]
    
    # Add mapped environment variables
    for root_var, react_var in env_mapping.items():
        value = os.getenv(root_var)
        if value:
            react_env_content.append(f"{react_var}={value}")
            print(f"✅ Mapped {root_var} -> {react_var}")
        else:
            print(f"⚠️  {root_var} not found in root .env")
    
    # Write React .env file
    react_env_path.parent.mkdir(parents=True, exist_ok=True)
    with open(react_env_path, 'w') as f:
        f.write('\n'.join(react_env_content))
    
    print(f"✅ React .env file updated at: {react_env_path}")
    print(f"📝 {len([line for line in react_env_content if '=' in line])} variables synced")
    
    return True

if __name__ == "__main__":
    print("🔄 Syncing environment variables to React UI...")
    success = sync_env_to_react()
    if success:
        print("✅ Environment sync completed successfully!")
    else:
        print("❌ Environment sync failed!")