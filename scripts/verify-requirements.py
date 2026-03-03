# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

#!/usr/bin/env python3
"""
Earth Copilot Installation Verification Script
Run this script to verify that all critical dependencies are correctly installed.
"""

import sys
import importlib.util
from packaging import version

def check_module(module_name, min_version=None, exact_version=None):
    """Check if a module can be imported and meets version requirements."""
    try:
        module = importlib.import_module(module_name)
        module_version = getattr(module, '__version__', 'unknown')
        
        if exact_version and module_version != exact_version:
            print(f"  {module_name}: {module_version} (expected exactly {exact_version})")
            return False
        elif min_version and version.parse(module_version) < version.parse(min_version):
            print(f" {module_name}: {module_version} (need >= {min_version})")
            return False
        else:
            print(f" {module_name}: {module_version}")
            return True
            
    except ImportError as e:
        print(f" {module_name}: Not installed ({e})")
        return False
    except Exception as e:
        print(f"  {module_name}: Error checking version ({e})")
        return False

def test_semantic_kernel_imports():
    """Test semantic kernel specific imports that commonly fail."""
    print("\n Testing Semantic Kernel imports...")
    
    try:
        from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion
        print(" AzureChatCompletion import successful")
    except ImportError as e:
        print(f" AzureChatCompletion import failed: {e}")
        return False
    
    try:
        from semantic_kernel.functions import KernelFunction, KernelArguments
        print(" KernelFunction, KernelArguments import successful")
    except ImportError as e:
        print(f" KernelFunction, KernelArguments import failed: {e}")
        return False
    
    try:
        from semantic_kernel import Kernel
        kernel = Kernel()
        print(" Kernel creation successful")
    except Exception as e:
        print(f" Kernel creation failed: {e}")
        return False
    
    return True

def main():
    print(" Earth Copilot Installation Verification")
    print("=" * 50)
    
    # Critical dependencies with exact versions
    critical_exact = {
        'semantic_kernel': '1.36.2',
        'pydantic': '2.11.9',
        'openai': '1.107.2'
    }
    
    # Core dependencies with minimum versions
    core_deps = {
        'azure.functions': '1.18.0',
        'aiohttp': '3.9.0',
        'requests': '2.31.0',
        'pystac_client': '0.7.0'
    }
    
    # Optional but recommended
    optional_deps = [
        'planetary_computer',
        'shapely',
        'numpy',
        'pandas'
    ]
    
    print("\n Checking critical dependencies (exact versions required):")
    critical_ok = True
    for module, exact_ver in critical_exact.items():
        if not check_module(module, exact_version=exact_ver):
            critical_ok = False
    
    print("\n Checking core dependencies:")
    core_ok = True
    for module, min_ver in core_deps.items():
        if not check_module(module, min_version=min_ver):
            core_ok = False
    
    print("\n Checking optional dependencies:")
    for module in optional_deps:
        check_module(module)
    
    # Test semantic kernel imports
    imports_ok = test_semantic_kernel_imports()
    
    print("\n" + "=" * 50)
    if critical_ok and core_ok and imports_ok:
        print(" SUCCESS: All critical components are working!")
        print("\nNext steps:")
        print("1. Run: ./setup-all-services.ps1 (or .sh)")
        print("2. Run: ./run-all-services.ps1 (or .sh)")
        print("3. Open: http://localhost:5173")
        return 0
    else:
        print(" FAILED: Some components need attention")
        print("\nTo fix issues:")
        print("1. pip install -r requirements.txt")
        print("2. For semantic kernel issues:")
        print("   pip install --force-reinstall semantic-kernel==1.36.2 pydantic==2.11.9 openai==1.107.2")
        print("3. Re-run this script to verify")
        return 1

if __name__ == '__main__':
    sys.exit(main())
