# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

#!/usr/bin/env python3
"""
Function Validation Script
Tests imports and basic functionality before starting the Azure Function
"""

import sys
import os
import traceback
import logging

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_imports():
    """Test all required imports"""
    logger.info("🧪 Testing imports...")
    
    try:
        # Test Azure Functions
        import azure.functions as func
        logger.info("✅ Azure Functions imported successfully")
        
        # Test environment variables
        from dotenv import load_dotenv
        env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env')
        load_dotenv(env_path)
        logger.info(f"✅ Environment loaded from: {env_path}")
        
        # Test Semantic Kernel
        try:
            from semantic_translator import SemanticQueryTranslator
            logger.info("✅ Semantic Kernel translator available")
        except ImportError as e:
            logger.warning(f"⚠️ Semantic Kernel not available: {e}")
        
        # Test collection profiles
        try:
            from collection_profiles import COLLECTION_PROFILES
            logger.info(f"✅ Collection profiles available: {len(COLLECTION_PROFILES)} collections")
        except ImportError as e:
            logger.warning(f"⚠️ Collection profiles not available: {e}")
        
        # Test environment variables
        logger.info("🔧 Environment Variables:")
        logger.info(f"  AZURE_OPENAI_ENDPOINT: {'✓' if os.getenv('AZURE_OPENAI_ENDPOINT') else '✗'}")
        logger.info(f"  AZURE_OPENAI_API_KEY: {'✓' if os.getenv('AZURE_OPENAI_API_KEY') else '✗'}")
        logger.info(f"  AZURE_OPENAI_DEPLOYMENT_NAME: {os.getenv('AZURE_OPENAI_DEPLOYMENT_NAME', 'Not Set')}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Import test failed: {e}")
        logger.error(f"❌ Traceback: {traceback.format_exc()}")
        return False

def test_function_creation():
    """Test creating the function app"""
    logger.info("🧪 Testing function app creation...")
    
    try:
        import azure.functions as func
        app = func.FunctionApp()
        logger.info("✅ Function app created successfully")
        return True
        
    except Exception as e:
        logger.error(f"❌ Function app creation failed: {e}")
        logger.error(f"❌ Traceback: {traceback.format_exc()}")
        return False

def main():
    """Run all validation tests"""
    logger.info("🚀 Starting Function Validation")
    logger.info("=" * 50)
    
    # Change to function directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    logger.info(f"📍 Working directory: {os.getcwd()}")
    
    # Run tests
    tests = [
        ("Import Test", test_imports),
        ("Function Creation Test", test_function_creation)
    ]
    
    results = []
    for test_name, test_func in tests:
        logger.info(f"\n🧪 Running {test_name}...")
        try:
            result = test_func()
            results.append((test_name, result))
            if result:
                logger.info(f"✅ {test_name} PASSED")
            else:
                logger.error(f"❌ {test_name} FAILED")
        except Exception as e:
            logger.error(f"❌ {test_name} CRASHED: {e}")
            results.append((test_name, False))
    
    # Summary
    logger.info("\n" + "=" * 50)
    logger.info("📊 VALIDATION SUMMARY")
    logger.info("=" * 50)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        logger.info(f"  {test_name}: {status}")
    
    logger.info(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        logger.info("🎉 All validations passed! Function should start successfully.")
        return 0
    else:
        logger.error("❌ Some validations failed. Check errors above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
