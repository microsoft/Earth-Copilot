#!/usr/bin/env pwsh
"""
🔍 DEBUG STARTUP SCRIPT: Enhanced error tracing for token limit issues
"""

Write-Host "🔍 DEBUG: Starting Earth Copilot with enhanced error tracing" -ForegroundColor Yellow

# Function to check if a port is in use
function Test-Port {
    param([int]$Port)
    try {
        $connection = New-Object System.Net.Sockets.TcpClient
        $connection.Connect("localhost", $Port)
        $connection.Close()
        return $true
    } catch {
        return $false
    }
}

# Function to kill processes on specific ports
function Stop-ProcessOnPort {
    param([int]$Port)
    Write-Host "🔄 Checking port $Port..." -ForegroundColor Cyan
    
    try {
        $processes = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess
        if ($processes) {
            foreach ($processId in $processes) {
                $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
                if ($process) {
                    Write-Host "🛑 Stopping process: $($process.Name) (PID: $processId)" -ForegroundColor Red
                    Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
                }
            }
            Start-Sleep 2
        }
    } catch {
        Write-Host "⚠️ Could not check/kill processes on port $Port" -ForegroundColor Yellow
    }
}

# Load environment variables from .env if it exists
if (Test-Path ".env") {
    Write-Host "📋 Loading environment variables from .env" -ForegroundColor Green
    Get-Content ".env" | ForEach-Object {
        if ($_ -match "^([^#][^=]+)=(.*)$") {
            $name = $matches[1].Trim()
            $value = $matches[2].Trim()
            # Remove surrounding quotes if present
            if ($value -match '^"(.*)"$') { $value = $matches[1] }
            if ($value -match "^'(.*)'$") { $value = $matches[1] }
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
            Write-Host "  ✅ Set $name" -ForegroundColor Gray
        }
    }
} else {
    Write-Host "⚠️ No .env file found - using system environment variables" -ForegroundColor Yellow
}

# Check required environment variables
$requiredEnvVars = @(
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_API_KEY", 
    "AZURE_OPENAI_MODEL_NAME"
)

Write-Host "🔍 Checking environment variables:" -ForegroundColor Cyan
foreach ($envVar in $requiredEnvVars) {
    $value = [Environment]::GetEnvironmentVariable($envVar)
    if ($value) {
        Write-Host "  ✅ $envVar: $($value.Substring(0, [Math]::Min(20, $value.Length)))..." -ForegroundColor Green
    } else {
        Write-Host "  ❌ $envVar: NOT SET" -ForegroundColor Red
    }
}

# Clean up any existing processes
Write-Host "🧹 Cleaning up existing processes..." -ForegroundColor Yellow
Stop-ProcessOnPort 5173
Stop-ProcessOnPort 5174  
Stop-ProcessOnPort 7071
Stop-ProcessOnPort 7072

# Kill any remaining func.exe processes
Get-Process -Name "func" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep 3

Write-Host "🚀 Starting applications with enhanced debug logging..." -ForegroundColor Green

# Start React UI first (most stable)
Write-Host "🌐 Starting React UI..." -ForegroundColor Cyan
Start-Process -FilePath "pwsh" -ArgumentList "-NoExit", "-Command", "cd 'earth_copilot\react-ui'; npm run dev" -WindowStyle Normal

# Wait for React UI to start
Start-Sleep 5

# Start STAC Function with enhanced logging
Write-Host "📊 Starting STAC Function with debug logging..." -ForegroundColor Cyan
$stacArgs = @(
    "-NoExit",
    "-Command", 
    "cd 'earth_copilot\stac_search_function'; `$env:FUNCTIONS_WORKER_RUNTIME='python'; `$env:AzureWebJobsFeatureFlags='EnableWorkerIndexing'; Write-Host 'Starting STAC Function...'; func start --port 7072 --python --verbose"
)
Start-Process -FilePath "pwsh" -ArgumentList $stacArgs -WindowStyle Normal

# Wait for STAC function to start
Start-Sleep 8

# Start Router Function with enhanced logging
Write-Host "🔄 Starting Router Function with debug logging..." -ForegroundColor Cyan
$routerArgs = @(
    "-NoExit", 
    "-Command",
    "cd 'earth_copilot\router_function_app'; `$env:FUNCTIONS_WORKER_RUNTIME='python'; `$env:AzureWebJobsFeatureFlags='EnableWorkerIndexing'; Write-Host 'Starting Router Function...'; func start --port 7071 --python --verbose"
)
Start-Process -FilePath "pwsh" -ArgumentList $routerArgs -WindowStyle Normal

# Wait for services to start
Start-Sleep 10

# Check service health
Write-Host "🏥 Checking service health..." -ForegroundColor Cyan

# Check React UI
if (Test-Port 5174) {
    Write-Host "  ✅ React UI: Running on port 5174" -ForegroundColor Green
} elseif (Test-Port 5173) {
    Write-Host "  ✅ React UI: Running on port 5173" -ForegroundColor Green
} else {
    Write-Host "  ❌ React UI: Not responding" -ForegroundColor Red
}

# Check STAC Function
if (Test-Port 7072) {
    Write-Host "  ✅ STAC Function: Running on port 7072" -ForegroundColor Green
    try {
        $stacHealth = Invoke-RestMethod -Uri "http://localhost:7072/api/health" -Method GET -TimeoutSec 5
        Write-Host "    🔍 STAC Health: $($stacHealth | ConvertTo-Json -Compress)" -ForegroundColor Gray
    } catch {
        Write-Host "    ⚠️ STAC Health check failed: $($_.Exception.Message)" -ForegroundColor Yellow
    }
} else {
    Write-Host "  ❌ STAC Function: Not responding on port 7072" -ForegroundColor Red
}

# Check Router Function
if (Test-Port 7071) {
    Write-Host "  ✅ Router Function: Running on port 7071" -ForegroundColor Green
    try {
        $routerHealth = Invoke-RestMethod -Uri "http://localhost:7071/api/health" -Method GET -TimeoutSec 5
        Write-Host "    🔍 Router Health: $($routerHealth | ConvertTo-Json -Compress)" -ForegroundColor Gray
    } catch {
        Write-Host "    ⚠️ Router Health check failed: $($_.Exception.Message)" -ForegroundColor Yellow
    }
} else {
    Write-Host "  ❌ Router Function: Not responding on port 7071" -ForegroundColor Red
}

Write-Host "🎯 DEBUG STARTUP COMPLETE" -ForegroundColor Green
Write-Host "📋 Available endpoints:" -ForegroundColor Cyan
Write-Host "  🌐 React UI: http://localhost:5173 or http://localhost:5174" -ForegroundColor Gray
Write-Host "  📊 STAC Function: http://localhost:7072" -ForegroundColor Gray  
Write-Host "  🔄 Router Function: http://localhost:7071" -ForegroundColor Gray
Write-Host ""
Write-Host "🔍 To debug token limit errors, check the function app terminal windows for detailed logs" -ForegroundColor Yellow
Write-Host "📝 Logs are also saved to semantic_translator_debug.log" -ForegroundColor Gray
