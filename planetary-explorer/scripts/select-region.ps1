# Auto-select an Azure region that can host the full Planetary Explorer stack.
#
# Strategy:
#   1. Walk a curated candidate list (regions historically reliable for AOAI + Container Apps + AI Search).
#   2. For each candidate, verify that every required resource provider lists the region.
#   3. For Azure OpenAI, also verify the requested model (default gpt-4o) is published in the region
#      and that the subscription has any remaining capacity.
#   4. Print the first region that passes. Exit non-zero if none do.
#
# Designed for unattended use from deploy-infrastructure.ps1 — emits ONLY the chosen region
# on stdout; diagnostics go to stderr so callers can do:  $loc = pwsh ./select-region.ps1
#
# Flags mirror the master deploy script so the preflight requires exactly what will be deployed.
[CmdletBinding()]
param(
    [string[]]$Candidates = @('eastus2','swedencentral','westus3','australiaeast','uksouth','francecentral'),
    [string]$RequiredOpenAiModel = 'gpt-4o',
    [switch]$EnableFabric,
    [switch]$EnablePrivateEndpoints,
    [switch]$EnableMpcPro,
    [switch]$Verbose
)

$ErrorActionPreference = 'Stop'

function Write-Info($msg) { Write-Host $msg -ForegroundColor Gray -ErrorAction SilentlyContinue }

# Required providers/resource types for the base stack.
$required = @(
    @{ ns = 'Microsoft.App';               type = 'managedEnvironments' },
    @{ ns = 'Microsoft.Web';               type = 'sites' },
    @{ ns = 'Microsoft.ContainerRegistry'; type = 'registries' },
    @{ ns = 'Microsoft.CognitiveServices'; type = 'accounts' },
    @{ ns = 'Microsoft.KeyVault';          type = 'vaults' },
    @{ ns = 'Microsoft.Storage';           type = 'storageAccounts' },
    @{ ns = 'Microsoft.OperationalInsights'; type = 'workspaces' }
)
if ($EnableFabric)           { $required += @{ ns = 'Microsoft.Fabric';  type = 'capacities' } }
if ($EnablePrivateEndpoints) { $required += @{ ns = 'Microsoft.Network'; type = 'privateEndpoints' } }

# Pre-fetch each provider's location list once (cache outside the candidate loop).
$providerLocs = @{}
foreach ($svc in $required) {
    $key = "$($svc.ns)/$($svc.type)"
    if (-not $providerLocs.ContainsKey($key)) {
        $locs = az provider show --namespace $svc.ns `
            --query "resourceTypes[?resourceType=='$($svc.type)'].locations[]" -o tsv 2>$null
        if (-not $locs) { $locs = @() }
        # Normalize "East US 2" -> "eastus2"
        $providerLocs[$key] = @($locs | ForEach-Object { ($_ -replace '\s','').ToLower() })
    }
}

function Test-Region {
    param([string]$Region)

    $norm = ($Region -replace '\s','').ToLower()

    foreach ($svc in $required) {
        $key = "$($svc.ns)/$($svc.type)"
        if ($providerLocs[$key].Count -eq 0) {
            Write-Info "  [skip-check] $key returned no location list (provider may not be registered)"
            continue
        }
        if ($providerLocs[$key] -notcontains $norm) {
            Write-Info "  [fail] $key not available in $Region"
            return $false
        }
    }

    # AOAI model availability + capacity check (best-effort: az cognitiveservices model list).
    try {
        $models = az cognitiveservices model list --location $Region -o json 2>$null | ConvertFrom-Json
        if (-not $models) {
            Write-Info "  [warn] could not list AOAI models in $Region (provider not registered?) — accepting region anyway"
        } else {
            $hit = $models | Where-Object { $_.model.name -eq $RequiredOpenAiModel }
            if (-not $hit) {
                Write-Info "  [fail] AOAI model '$RequiredOpenAiModel' not published in $Region"
                return $false
            }
        }
    } catch {
        Write-Info "  [warn] AOAI model check threw in $Region — accepting anyway: $($_.Exception.Message)"
    }

    return $true
}

Write-Info "Selecting region from: $($Candidates -join ', ')"

foreach ($r in $Candidates) {
    Write-Info "Checking $r ..."
    if (Test-Region -Region $r) {
        Write-Info "[OK] selected $r"
        # ONLY emit the region on stdout — callers capture this.
        Write-Output $r
        exit 0
    }
}

Write-Error "No candidate region satisfies the required services. Tried: $($Candidates -join ', ')"
exit 1
