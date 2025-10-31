# Test Two-Agent System with Azure Credentials
# This script loads Azure OpenAI credentials from the Container App and runs tests

param(
    [Parameter(Mandatory=$false)]
    [string]$ResourceGroup = "earthcopilot-rg",
    
    [Parameter(Mandatory=$false)]
    [string]$ContainerAppName = "earthcopilot-api"
)

$ErrorActionPreference = "Stop"

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "TWO-AGENT SYSTEM TEST RUNNER" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# Get environment variables from Azure Container App
Write-Host "[Loading Azure OpenAI credentials from Container App]" -ForegroundColor Yellow

try {
    $envVars = az containerapp show `
        --name $ContainerAppName `
        --resource-group $ResourceGroup `
        --query "properties.template.containers[0].env" `
        --output json | ConvertFrom-Json
    
    # Extract required environment variables
    $endpoint = ($envVars | Where-Object { $_.name -eq "AZURE_OPENAI_ENDPOINT" }).value
    $apiKey = ($envVars | Where-Object { $_.name -eq "AZURE_OPENAI_API_KEY" }).secretRef
    $modelName = ($envVars | Where-Object { $_.name -eq "AZURE_OPENAI_DEPLOYMENT_NAME" }).value
    
    if ($apiKey) {
        # If API key is stored as a secret, we need to get it differently
        Write-Host "[Note] API Key is stored as a secret in Container App" -ForegroundColor Gray
        Write-Host "[Action Required] Please set the API key manually:" -ForegroundColor Yellow
        Write-Host '  $env:AZURE_OPENAI_API_KEY="your-api-key"' -ForegroundColor Gray
        Write-Host "`nOr retrieve it from Azure Key Vault if stored there.`n" -ForegroundColor Gray
    }
    
    # Set environment variables
    if ($endpoint) {
        $env:AZURE_OPENAI_ENDPOINT = $endpoint
        Write-Host "[OK] AZURE_OPENAI_ENDPOINT set" -ForegroundColor Green
    }
    
    if ($modelName) {
        $env:AZURE_OPENAI_DEPLOYMENT_NAME = $modelName
        Write-Host "[OK] AZURE_OPENAI_DEPLOYMENT_NAME set to: $modelName" -ForegroundColor Green
    } else {
        $env:AZURE_OPENAI_DEPLOYMENT_NAME = "gpt-4o"
        Write-Host "[OK] AZURE_OPENAI_DEPLOYMENT_NAME defaulted to: gpt-4o" -ForegroundColor Green
    }
    
    # Check if API key is set
    if (-not $env:AZURE_OPENAI_API_KEY) {
        Write-Host "`n[WARNING] AZURE_OPENAI_API_KEY not set!" -ForegroundColor Red
        Write-Host "Please set it manually before running tests:" -ForegroundColor Yellow
        Write-Host '  $env:AZURE_OPENAI_API_KEY="your-api-key"' -ForegroundColor Gray
        Write-Host "`nThen run:" -ForegroundColor Yellow
        Write-Host "  python test_two_agents.py" -ForegroundColor Gray
        Write-Host ""
        exit 1
    }
    
} catch {
    Write-Host "[ERROR] Failed to load credentials from Container App" -ForegroundColor Red
    Write-Host "Error: $_" -ForegroundColor Red
    Write-Host "`nPlease set environment variables manually:" -ForegroundColor Yellow
    Write-Host '  $env:AZURE_OPENAI_ENDPOINT="https://your-endpoint.openai.azure.com/"' -ForegroundColor Gray
    Write-Host '  $env:AZURE_OPENAI_API_KEY="your-api-key"' -ForegroundColor Gray
    Write-Host '  $env:AZURE_OPENAI_DEPLOYMENT_NAME="gpt-4o"' -ForegroundColor Gray
    Write-Host ""
    exit 1
}

# Run the test
Write-Host "`n[Running Two-Agent System Tests]" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

$pythonPath = "C:/Users/melisabardhi/OneDrive - Microsoft/Desktop/Workspace/earth-copilot-container/.venv/Scripts/python.exe"

& $pythonPath test_two_agents.py

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "Test run complete!" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan
