# enable-agent-service.ps1
# Programmatically enables Azure AI Agent Service on an existing AI Foundry (AIServices) account.
#
# What this script does:
#   1. Enables allowProjectManagement on the CogSvc account
#   2. Creates a CogSvc project sub-resource (required for Agent Service)
#   3. Creates account-level capability host (capabilityHostKind=Agents)
#   4. Creates project-level capability host
#   5. Assigns required roles to the container app managed identity
#   6. Updates the container app env var with the correct endpoint
#
# Prerequisites:
#   - Azure CLI logged in (az login)
#   - Contributor + User Access Administrator on the resource group
#
# Usage:
#   .\scripts\enable-agent-service.ps1

param(
    [string]$SubscriptionId = "",
    [string]$ResourceGroup = "rg-earthcopilot",
    [string]$AccountName = "",
    [string]$ProjectName = "earth-copilot-agents",
    [string]$ContainerAppName = "",
    [string]$ApiVersion = "2025-04-01-preview"
)

$ErrorActionPreference = "Stop"

# Auto-discover values if not provided
if ([string]::IsNullOrEmpty($SubscriptionId)) {
    $SubscriptionId = az account show --query id -o tsv
    Write-Host "Using current subscription: $SubscriptionId" -ForegroundColor Cyan
}

if ([string]::IsNullOrEmpty($AccountName)) {
    $AccountName = az cognitiveservices account list --resource-group $ResourceGroup --query "[?kind=='AIServices'].name | [0]" -o tsv
    Write-Host "Discovered AI Foundry account: $AccountName" -ForegroundColor Cyan
}

if ([string]::IsNullOrEmpty($ContainerAppName)) {
    $ContainerAppName = az containerapp list --resource-group $ResourceGroup --query "[0].name" -o tsv
    Write-Host "Discovered Container App: $ContainerAppName" -ForegroundColor Cyan
}
$baseUrl = "https://management.azure.com/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.CognitiveServices/accounts/$AccountName"

function Wait-ForProvisioning {
    param([string]$Url, [int]$TimeoutSeconds = 120)
    $elapsed = 0
    while ($elapsed -lt $TimeoutSeconds) {
        Start-Sleep -Seconds 10
        $elapsed += 10
        $state = az rest --method get --url "$Url`?api-version=$ApiVersion" --query "properties.provisioningState" -o tsv 2>$null
        Write-Host "  State: $state ($elapsed`s)"
        if ($state -eq "Succeeded") { return $true }
        if ($state -eq "Failed") { throw "Provisioning failed" }
    }
    throw "Provisioning timed out after $TimeoutSeconds seconds"
}

# Step 1: Enable allowProjectManagement
Write-Host "`n=== Step 1: Enable allowProjectManagement ===" -ForegroundColor Cyan
$body = @{
    location = "eastus2"
    kind = "AIServices"
    sku = @{ name = "S0" }
    identity = @{ type = "SystemAssigned" }
    properties = @{
        allowProjectManagement = $true
        customSubDomainName = $AccountName
        publicNetworkAccess = "Enabled"
        disableLocalAuth = $true
        networkAcls = @{ defaultAction = "Allow" }
    }
} | ConvertTo-Json -Depth 3
$bodyFile = [System.IO.Path]::GetTempFileName()
$body | Set-Content -Path $bodyFile -Encoding utf8

$result = az rest --method put --url "$baseUrl`?api-version=$ApiVersion" --body "@$bodyFile" --query "properties.allowProjectManagement" -o tsv 2>&1
Write-Host "  allowProjectManagement: $result"
Wait-ForProvisioning -Url $baseUrl
Remove-Item $bodyFile

# Step 2: Create CogSvc project sub-resource
Write-Host "`n=== Step 2: Create CogSvc project '$ProjectName' ===" -ForegroundColor Cyan
$projectBody = @{
    location = "eastus2"
    identity = @{ type = "SystemAssigned" }
    properties = @{
        description = "Earth Copilot GEOINT Agent Project"
        displayName = "Earth Copilot Agents"
    }
} | ConvertTo-Json -Depth 3
$projectFile = [System.IO.Path]::GetTempFileName()
$projectBody | Set-Content -Path $projectFile -Encoding utf8

$projectUrl = "$baseUrl/projects/$ProjectName"
$result = az rest --method put --url "$projectUrl`?api-version=$ApiVersion" --body "@$projectFile" --query "properties.provisioningState" -o tsv 2>&1
Write-Host "  Project state: $result"
if ($result -ne "Succeeded") { Wait-ForProvisioning -Url $projectUrl }
Remove-Item $projectFile

# Step 3: Create account-level capability host
Write-Host "`n=== Step 3: Create account capability host ===" -ForegroundColor Cyan
$capHostBody = '{"properties":{"capabilityHostKind":"Agents"}}'
$capFile = [System.IO.Path]::GetTempFileName()
$capHostBody | Set-Content -Path $capFile -Encoding utf8

$acctCapUrl = "$baseUrl/capabilityHosts/default"
$result = az rest --method put --url "$acctCapUrl`?api-version=$ApiVersion" --body "@$capFile" --query "properties.provisioningState" -o tsv 2>&1
Write-Host "  Account CapHost state: $result"
if ($result -ne "Succeeded") { Wait-ForProvisioning -Url $acctCapUrl }
Remove-Item $capFile

# Step 4: Create project-level capability host
Write-Host "`n=== Step 4: Create project capability host ===" -ForegroundColor Cyan
$projCapFile = [System.IO.Path]::GetTempFileName()
$capHostBody | Set-Content -Path $projCapFile -Encoding utf8

$projCapUrl = "$projectUrl/capabilityHosts/default"
$result = az rest --method put --url "$projCapUrl`?api-version=$ApiVersion" --body "@$projCapFile" --query "properties.provisioningState" -o tsv 2>&1
Write-Host "  Project CapHost state: $result"
if ($result -ne "Succeeded") { Wait-ForProvisioning -Url $projCapUrl }
Remove-Item $projCapFile

# Step 5: Assign roles to container app managed identity
Write-Host "`n=== Step 5: Assign roles to container app MI ===" -ForegroundColor Cyan
$principalId = az containerapp show -n $ContainerAppName -g $ResourceGroup --query "identity.principalId" -o tsv 2>$null
Write-Host "  Container app MI: $principalId"

$scope = "/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.CognitiveServices/accounts/$AccountName"
$roles = @("Azure AI User", "Cognitive Services OpenAI Contributor")
foreach ($role in $roles) {
    Write-Host "  Assigning: $role"
    az role assignment create --assignee-object-id $principalId --assignee-principal-type ServicePrincipal --role $role --scope $scope -o none 2>$null
}

# Step 6: Update container app env var
Write-Host "`n=== Step 6: Update AZURE_AI_PROJECT_ENDPOINT ===" -ForegroundColor Cyan
$endpoint = "https://$AccountName.services.ai.azure.com/api/projects/$ProjectName"
Write-Host "  Endpoint: $endpoint"
az containerapp update -n $ContainerAppName -g $ResourceGroup --set-env-vars "AZURE_AI_PROJECT_ENDPOINT=$endpoint" -o none 2>$null

# Step 7: Verify
Write-Host "`n=== Verification ===" -ForegroundColor Green
$token = az account get-access-token --resource "https://ai.azure.com" --query accessToken -o tsv 2>$null
try {
    $r = Invoke-RestMethod -Uri "$endpoint/agents?api-version=2025-05-15-preview" -Headers @{"Authorization"="Bearer $token"} -Method Get
    Write-Host "  Agent Service API: SUCCESS (agents: $($r.data.Count))" -ForegroundColor Green
} catch {
    Write-Host "  Agent Service API: FAILED - $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host "`nDone! Agent Service is enabled." -ForegroundColor Green
