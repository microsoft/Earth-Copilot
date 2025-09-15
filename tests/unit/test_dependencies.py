# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

#!/usr/bin/env python3
"""Test script to validate Router Function dependencies"""

try:
    print("Testing core imports...")
    import json
    print("✓ json imported successfully")
    
    import logging
    print("✓ logging imported successfully")
    
    import os
    print("✓ os imported successfully")
    
    import sys
    print("✓ sys imported successfully")
    
    from datetime import datetime, timedelta
    print("✓ datetime imported successfully")
    
    from typing import Dict, Any, List, Optional, Tuple
    print("✓ typing imported successfully")
    
    import aiohttp
    print("✓ aiohttp imported successfully")
    
    from dotenv import load_dotenv
    print("✓ dotenv imported successfully")
    
    import azure.functions as func
    print("✓ azure.functions imported successfully")
    
    from azure.functions import HttpRequest, HttpResponse
    print("✓ azure.functions HttpRequest/HttpResponse imported successfully")
    
    print("\nTesting Router Function specific imports...")
    sys.path.append(os.path.dirname(__file__))
    
    try:
        from stac_query_checker_integration import STACQueryChecker
        print("✓ STACQueryChecker imported successfully")
    except Exception as e:
        print(f"✗ STACQueryChecker import failed: {e}")
    
    try:
        from semantic_translator import SemanticTranslator
        print("✓ SemanticTranslator imported successfully")
    except Exception as e:
        print(f"✗ SemanticTranslator import failed: {e}")
    
    print("\nAll core dependencies validated successfully!")
    
except Exception as e:
    print(f"FAILED: {e}")
    import traceback
    traceback.print_exc()
