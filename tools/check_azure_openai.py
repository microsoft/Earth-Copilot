"""
Azure OpenAI Configuration Checker
==================================
This script helps you identify and test your Azure OpenAI configura        print("   3. Deploy a GPT model (gpt-5 or gpt-4)")ion.
"""

import os
import json
import subprocess
import requests

def check_azure_cli():
    """Check if Azure CLI is installed and logged in"""
    try:
        result = subprocess.run(['az', 'account', 'show'], 
                              capture_output=True, text=True, check=True)
        account_info = json.loads(result.stdout)
        print(f"✅ Azure CLI logged in as: {account_info.get('user', {}).get('name', 'Unknown')}")
        print(f"   Subscription: {account_info.get('name', 'Unknown')} ({account_info.get('id', 'Unknown')})")
        return True
    except (subprocess.CalledProcessError, json.JSONDecodeError, FileNotFoundError):
        print("❌ Azure CLI not installed or not logged in")
        print("   Install: https://docs.microsoft.com/en-us/cli/azure/install-azure-cli")
        print("   Login: az login")
        return False

def list_cognitive_services():
    """List Azure Cognitive Services resources"""
    try:
        result = subprocess.run([
            'az', 'cognitiveservices', 'account', 'list', 
            '--query', '[?kind==`OpenAI`].{name:name, location:location, endpoint:properties.endpoint}',
            '--output', 'json'
        ], capture_output=True, text=True, check=True)
        
        resources = json.loads(result.stdout)
        if resources:
            print("\n🤖 Found Azure OpenAI resources:")
            for resource in resources:
                print(f"   • {resource['name']} ({resource['location']})")
                print(f"     Endpoint: {resource['endpoint']}")
            return resources
        else:
            print("\n❌ No Azure OpenAI resources found")
            return []
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        print("\n❌ Could not list Azure OpenAI resources")
        return []

def list_deployments(resource_name, resource_group=None):
    """List deployments for a specific Azure OpenAI resource"""
    try:
        if not resource_group:
            # Try to find the resource group
            result = subprocess.run([
                'az', 'cognitiveservices', 'account', 'show',
                '--name', resource_name,
                '--query', 'resourceGroup',
                '--output', 'tsv'
            ], capture_output=True, text=True, check=True)
            resource_group = result.stdout.strip()
        
        result = subprocess.run([
            'az', 'cognitiveservices', 'account', 'deployment', 'list',
            '--name', resource_name,
            '--resource-group', resource_group,
            '--query', '[].{name:name, model:properties.model.name, version:properties.model.version}',
            '--output', 'json'
        ], capture_output=True, text=True, check=True)
        
        deployments = json.loads(result.stdout)
        if deployments:
            print(f"\n🚀 Deployments in {resource_name}:")
            for deployment in deployments:
                print(f"   • {deployment['name']}: {deployment['model']} (v{deployment['version']})")
            return deployments
        else:
            print(f"\n❌ No deployments found in {resource_name}")
            return []
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        print(f"\n❌ Could not list deployments for {resource_name}")
        return []

def get_api_key(resource_name, resource_group=None):
    """Get API key for Azure OpenAI resource"""
    try:
        if not resource_group:
            # Try to find the resource group
            result = subprocess.run([
                'az', 'cognitiveservices', 'account', 'show',
                '--name', resource_name,
                '--query', 'resourceGroup',
                '--output', 'tsv'
            ], capture_output=True, text=True, check=True)
            resource_group = result.stdout.strip()
        
        result = subprocess.run([
            'az', 'cognitiveservices', 'account', 'keys', 'list',
            '--name', resource_name,
            '--resource-group', resource_group,
            '--query', 'key1',
            '--output', 'tsv'
        ], capture_output=True, text=True, check=True)
        
        api_key = result.stdout.strip()
        print(f"\n🔑 API Key for {resource_name}: {api_key[:8]}...{api_key[-4:]}")
        return api_key
    except subprocess.CalledProcessError:
        print(f"\n❌ Could not get API key for {resource_name}")
        return None

def generate_local_settings(endpoint, api_key, deployment_name):
    """Generate local.settings.json configuration"""
    config = {
        "AZURE_OPENAI_ENDPOINT": endpoint,
        "AZURE_OPENAI_API_KEY": api_key,
        "AZURE_OPENAI_API_VERSION": "2024-02-01",
        "AZURE_OPENAI_DEPLOYMENT_NAME": deployment_name
    }
    
    print("\n📋 Configuration for local.settings.json:")
    print("   Add these to the 'Values' section:")
    for key, value in config.items():
        print(f'    "{key}": "{value}",')
    
    return config

def main():
    print("🔍 Azure OpenAI Configuration Checker")
    print("=" * 50)
    
    # Check Azure CLI
    if not check_azure_cli():
        return
    
    # List Azure OpenAI resources
    resources = list_cognitive_services()
    if not resources:
        print("\n💡 To create an Azure OpenAI resource:")
        print("   1. Go to https://portal.azure.com")
        print("   2. Create a new Azure OpenAI Service resource")
        print("   3. Deploy a GPT model (gpt-5 or gpt-4)"))
        return
    
    # Check each resource
    for resource in resources:
        print(f"\n🔍 Checking resource: {resource['name']}")
        deployments = list_deployments(resource['name'])
        
        if deployments:
            api_key = get_api_key(resource['name'])
            if api_key:
                # Suggest the best deployment
                best_deployment = None
                for deployment in deployments:
                    if 'gpt-5' in deployment['name'].lower():
                        best_deployment = deployment
                        break
                    elif 'gpt-5' in deployment['name'].lower() or 'gpt-4' in deployment['name'].lower():
                        best_deployment = deployment
                
                if best_deployment:
                    print(f"\n✅ Recommended configuration:")
                    generate_local_settings(
                        resource['endpoint'],
                        api_key,
                        best_deployment['name']
                    )
                else:
                    print("\n⚠️  No GPT-5 or GPT-4 deployment found")
                    print("   Available deployments:", [d['name'] for d in deployments])

if __name__ == "__main__":
    main()
