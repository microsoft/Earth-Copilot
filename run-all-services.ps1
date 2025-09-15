# Earth Copilot - Complete System Startup (Simplified Architecture)
# CRITICAL GOAL: End-to-end testing through UI to get STAC results on map

Write-Host "START - Starting Earth Copilot Complete System" -ForegroundColor Green
Write-Host "GOAL: UI -> Unified Function -> Microsoft Planetary Computer -> Map" -ForegroundColor Yellow
Write-Host ""

# Function to test if a port is available
function Test-Port {
    param($Port)
    $connection = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    return $connection -eq $null
}

# Function to wait for service to be ready
function Wait-ForService {
    param($Url, $ServiceName, $MaxWait = 30)
    Write-Host "WAIT - Waiting for $ServiceName to be ready..." -ForegroundColor Yellow
    $waited = 0
    while ($waited -lt $MaxWait) {
        try {
            $response = Invoke-RestMethod -Uri $Url -Method GET -TimeoutSec 3 -ErrorAction Stop
            Write-Host "OK - $ServiceName is ready!" -ForegroundColor Green
            return $true
        } catch {
            Start-Sleep -Seconds 2
            $waited += 2
            Write-Host "  WAIT - Still waiting... ($waited/$MaxWait seconds)" -ForegroundColor Gray
        }
    }
    Write-Host "ERROR - $ServiceName failed to start within $MaxWait seconds" -ForegroundColor Red
    return $false
}

Write-Host "SIMPLIFIED ARCHITECTURE (2 Services):" -ForegroundColor Cyan
Write-Host "  1. React UI (Port 5173)" -ForegroundColor White
Write-Host "  2. Unified Router+STAC Function (Port 7071)" -ForegroundColor White
Write-Host ""

# 1. Start Unified Router+STAC Function (Port 7071)
Write-Host "START - Starting Unified Router+STAC Function (Port 7071)..." -ForegroundColor Cyan
if (Test-Port 7071) {
    $functionPath = Join-Path $PSScriptRoot "earth-copilot\router-function-app"
    Start-Job -Name "UnifiedFunction" -ScriptBlock {
        param($path)
        Set-Location $path
        # Activate virtual environment if it exists
        if (Test-Path "..\..\venv\Scripts\Activate.ps1") {
            & "..\..\venv\Scripts\Activate.ps1"
        } elseif (Test-Path ".venv\Scripts\Activate.ps1") {
            & ".venv\Scripts\Activate.ps1"
        }
        func host start --port 7071
    } -ArgumentList $functionPath | Out-Null
    
    # Wait for function to be ready
    Start-Sleep -Seconds 8
    if (Wait-ForService "http://localhost:7071/api/health" "Unified Function") {
        Write-Host "OK - Unified Function online with 3 endpoints:" -ForegroundColor Green
        Write-Host "   * http://localhost:7071/api/health" -ForegroundColor Gray
        Write-Host "   * http://localhost:7071/api/query (Main endpoint)" -ForegroundColor Gray
        Write-Host "   * http://localhost:7071/api/stac-search" -ForegroundColor Gray
    }
} else {
    Write-Host "ERROR - Port 7071 is already in use" -ForegroundColor Red
    Write-Host "   Run: .\kill-all-services.ps1 first" -ForegroundColor Yellow
}

# 2. Start React UI (Port 5173)
Write-Host ""
Write-Host "START - Starting React UI (Port 5173)..." -ForegroundColor Cyan
if (Test-Port 5173) {
    $reactPath = Join-Path $PSScriptRoot "earth-copilot\react-ui"
    Start-Job -Name "ReactUI" -ScriptBlock {
        param($path)
        Set-Location $path
        npm run dev
    } -ArgumentList $reactPath | Out-Null
    
    Start-Sleep -Seconds 5
    Write-Host "OK - React UI starting at http://localhost:5173/" -ForegroundColor Green
} else {
    Write-Host "ERROR - Port 5173 is already in use" -ForegroundColor Red
    Write-Host "   Run: .\kill-all-services.ps1 first" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "STATUS - System Status Check:" -ForegroundColor Yellow
Write-Host "----------------------------------------" -ForegroundColor Gray

# Test Unified Function endpoints
Write-Host "Testing Unified Function endpoints..." -ForegroundColor Cyan
try {
    $healthResponse = Invoke-RestMethod -Uri "http://localhost:7071/api/health" -Method GET -TimeoutSec 5
    Write-Host "OK - Health check: $($healthResponse.status)" -ForegroundColor Green
} catch {
    Write-Host "ERROR - Health check failed" -ForegroundColor Red
}

try {
    $testQueryData = @{ query = "test satellite imagery of California" }
    $testQuery = $testQueryData | ConvertTo-Json
    $queryResponse = Invoke-RestMethod -Uri "http://localhost:7071/api/query" -Method POST -Body $testQuery -ContentType "application/json" -TimeoutSec 10
    Write-Host "OK - Query endpoint working" -ForegroundColor Green
} catch {
    Write-Host "ERROR - Query endpoint failed: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host ""
Write-Host "TESTING - Critical Testing Steps:" -ForegroundColor Yellow
Write-Host "1. Open: http://localhost:5173/" -ForegroundColor White
Write-Host "2. Type query: 'Show me recent satellite imagery of California wildfires'" -ForegroundColor White
Write-Host "3. Verify: STAC results appear on the map" -ForegroundColor White
Write-Host "4. Success: End-to-end functionality confirmed!" -ForegroundColor Green

Write-Host ""
Write-Host "JOBS - Running Jobs:" -ForegroundColor Cyan
Get-Job | Where-Object { $_.State -eq "Running" } | Format-Table Name, State, Location

Write-Host ""
Write-Host "STOP - To stop all services: .\kill-all-services.ps1" -ForegroundColor Red
Write-Host "READY - System ready for end-to-end testing!" -ForegroundColor Green