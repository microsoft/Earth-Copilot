#!/usr/bin/env pwsh

# Earth Copilot Debug Startup Script
# Starts all services in debug mode with enhanced logging

param(
    [switch]$Quick,           # Quick start without health checks
    [switch]$SkipUI,          # Skip React UI startup
    [switch]$Debug,           # Enable debug mode with breakpoints
    [switch]$Clean            # Clean previous processes first
)

Write-Host "🌍 Earth Copilot Debug Startup Script" -ForegroundColor Green
Write-Host "=====================================" -ForegroundColor Green

# Set error handling
$ErrorActionPreference = "Continue"

# Function to check if port is in use
function Test-Port {
    param([int]$Port)
    try {
        $null = New-Object System.Net.Sockets.TcpClient("localhost", $Port)
        return $true
    }
    catch {
        return $false
    }
}

# Function to kill processes on specific ports
function Stop-ProcessOnPort {
    param([int]$Port)
    try {
        $processes = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess
        foreach ($processId in $processes) {
            Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
            Write-Host "🛑 Killed process $processId on port $Port" -ForegroundColor Yellow
        }
    }
    catch {
        Write-Host "⚠️  No processes found on port $Port" -ForegroundColor Yellow
    }
}

# Clean previous processes if requested
if ($Clean) {
    Write-Host "🧹 Cleaning previous processes..." -ForegroundColor Yellow
    Stop-ProcessOnPort 5173  # React UI
    Stop-ProcessOnPort 7071  # Router Function
    Stop-ProcessOnPort 7072  # STAC Function
    Start-Sleep -Seconds 3
}

# Check for port conflicts
$conflictPorts = @()
if (Test-Port 5173) { $conflictPorts += 5173 }
if (Test-Port 7071) { $conflictPorts += 7071 }
if (Test-Port 7072) { $conflictPorts += 7072 }

if ($conflictPorts.Count -gt 0) {
    Write-Host "⚠️  Port conflicts detected on: $($conflictPorts -join ', ')" -ForegroundColor Red
    Write-Host "💡 Run with -Clean to automatically kill existing processes" -ForegroundColor Cyan
    $response = Read-Host "Continue anyway? (y/N)"
    if ($response -notmatch '^[Yy]') {
        exit 1
    }
}

# Change to workspace directory
# Path configuration
$workspaceRoot = "c:\Users\melisabardhi\OneDrive - Microsoft\Desktop\Workspace\Earth-Copilot"
Set-Location $workspaceRoot

# Load .env file if it exists
$envFile = Join-Path $workspaceRoot ".env"
if (Test-Path $envFile) {
    Write-Host "📄 Loading .env file..." -ForegroundColor Cyan
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^([^#][^=]+)=(.*)$') {
            $name = $matches[1].Trim()
            $value = $matches[2].Trim()
            [System.Environment]::SetEnvironmentVariable($name, $value, [System.EnvironmentVariableTarget]::Process)
        }
    }
}

# Verify environment
Write-Host "🔍 Verifying environment..." -ForegroundColor Cyan

# Check Azure Functions Core Tools
try {
    $funcVersion = func --version 2>$null
    Write-Host "✅ Azure Functions Core Tools: $funcVersion" -ForegroundColor Green
}
catch {
    Write-Host "❌ Azure Functions Core Tools not found" -ForegroundColor Red
    Write-Host "💡 Install: npm install -g azure-functions-core-tools@4 --unsafe-perm true" -ForegroundColor Cyan
}

# Check Node.js
try {
    $nodeVersion = node --version 2>$null
    Write-Host "✅ Node.js: $nodeVersion" -ForegroundColor Green
}
catch {
    Write-Host "❌ Node.js not found" -ForegroundColor Red
}

# Check Python
try {
    $pythonVersion = python --version 2>$null
    Write-Host "✅ Python: $pythonVersion" -ForegroundColor Green
}
catch {
    Write-Host "❌ Python not found" -ForegroundColor Red
}

# Check environment variables
if ($env:AZURE_OPENAI_ENDPOINT) {
    Write-Host "✅ AZURE_OPENAI_ENDPOINT configured" -ForegroundColor Green
} else {
    Write-Host "⚠️  AZURE_OPENAI_ENDPOINT not set" -ForegroundColor Yellow
}

if ($env:AZURE_OPENAI_API_KEY) {
    Write-Host "✅ AZURE_OPENAI_API_KEY configured" -ForegroundColor Green
} else {
    Write-Host "⚠️  AZURE_OPENAI_API_KEY not set" -ForegroundColor Yellow
}

Write-Host ""

# Start services in debug mode
if ($Debug) {
    Write-Host "🐛 Starting in DEBUG mode - use VSCode debugger to attach" -ForegroundColor Magenta
    Write-Host "💡 Use 'Debug Full Earth Copilot System' configuration in VSCode" -ForegroundColor Cyan
    Start-Sleep -Seconds 2
}

# 1. Start STAC Function (Port 7072)
Write-Host "🔍 Starting STAC Function App (Port 7072)..." -ForegroundColor Blue
$stacLocation = Join-Path $workspaceRoot "earth_copilot\stac_search_function"
$stacJob = Start-Job -ScriptBlock {
    param($location, $debug)
    Set-Location $location
    if ($debug) {
        # Debug mode with enhanced logging
        $env:AZURE_FUNCTIONS_ENVIRONMENT = "Development"
        $env:AZURE_FUNCTIONS_WORKER_DEBUG = "true"
        func start --port 7072 --verbose --debug
    } else {
        func start --port 7072 --verbose
    }
} -ArgumentList $stacLocation, $Debug

# Wait for STAC function to start
Write-Host "⏳ Waiting for STAC Function to initialize..." -ForegroundColor Yellow
Start-Sleep -Seconds 20

# 2. Start Router Function (Port 7071)
Write-Host "🌍 Starting Router Function App (Port 7071)..." -ForegroundColor Blue
$routerLocation = Join-Path $workspaceRoot "earth_copilot\router_function_app"
$routerJob = Start-Job -ScriptBlock {
    param($location, $debug)
    Set-Location $location
    if ($debug) {
        # Debug mode with enhanced logging
        $env:AZURE_FUNCTIONS_ENVIRONMENT = "Development"
        $env:AZURE_FUNCTIONS_WORKER_DEBUG = "true"
        func start --port 7071 --verbose --debug
    } else {
        func start --port 7071 --verbose
    }
} -ArgumentList $routerLocation, $Debug

# Wait for Router function to start
Write-Host "⏳ Waiting for Router Function to initialize..." -ForegroundColor Yellow
Start-Sleep -Seconds 20

# 3. Start React UI (Port 5173) - if not skipped
$uiJob = $null
if (-not $SkipUI) {
    Write-Host "⚛️  Starting React UI (Port 5173)..." -ForegroundColor Blue
    $uiLocation = Join-Path $workspaceRoot "earth_copilot\react-ui"
    $uiJob = Start-Job -ScriptBlock {
        param($location)
        Set-Location $location
        npm run dev
    } -ArgumentList $uiLocation
    
    Start-Sleep -Seconds 10
}

# Health checks (unless quick start)
if (-not $Quick) {
    Write-Host "🏥 Performing health checks..." -ForegroundColor Cyan
    
    # Test STAC Function
    try {
        $stacHealth = Invoke-RestMethod -Uri "http://localhost:7072/api/health" -TimeoutSec 10
        Write-Host "✅ STAC Function Health: OK" -ForegroundColor Green
    }
    catch {
        Write-Host "❌ STAC Function Health: FAILED" -ForegroundColor Red
        Write-Host "   Error: $($_.Exception.Message)" -ForegroundColor Red
    }
    
    # Test Router Function  
    try {
        $routerHealth = Invoke-RestMethod -Uri "http://localhost:7071/api/health" -TimeoutSec 10
        Write-Host "✅ Router Function Health: OK" -ForegroundColor Green
    }
    catch {
        Write-Host "❌ Router Function Health: FAILED" -ForegroundColor Red
        Write-Host "   Error: $($_.Exception.Message)" -ForegroundColor Red
    }
    
    # Test React UI (if started)
    if (-not $SkipUI) {
        try {
            $uiResponse = Invoke-WebRequest -Uri "http://localhost:5173" -TimeoutSec 10
            Write-Host "✅ React UI: OK" -ForegroundColor Green
        }
        catch {
            Write-Host "⚠️  React UI: Starting up..." -ForegroundColor Yellow
        }
    }
}

# Display service status
Write-Host ""
Write-Host "🚀 Earth Copilot Services Status:" -ForegroundColor Green
Write-Host "=================================" -ForegroundColor Green
Write-Host "🔍 STAC Function App:    http://localhost:7072/api/health" -ForegroundColor Cyan
Write-Host "🌍 Router Function App:  http://localhost:7071/api/health" -ForegroundColor Cyan
if (-not $SkipUI) {
    Write-Host "⚛️  React UI:            http://localhost:5173" -ForegroundColor Cyan
}
Write-Host ""

# Test query example
Write-Host "🧪 Example test query:" -ForegroundColor Yellow
Write-Host 'curl -X POST http://localhost:7071/api/query -H "Content-Type: application/json" -d "{\"query\": \"Show me wildfire damage in California from August 2024\"}"' -ForegroundColor Gray
Write-Host ""

# Debugging instructions
if ($Debug) {
    Write-Host "🐛 Debug Mode Instructions:" -ForegroundColor Magenta
    Write-Host "1. Open VSCode in this workspace" -ForegroundColor White
    Write-Host "2. Go to Run and Debug (Ctrl+Shift+D)" -ForegroundColor White
    Write-Host "3. Select 'Debug Full Earth Copilot System'" -ForegroundColor White
    Write-Host "4. Set breakpoints in your code" -ForegroundColor White
    Write-Host "5. Press F5 to attach debugger" -ForegroundColor White
    Write-Host ""
}

# Monitor jobs
Write-Host "🔄 Services are running. Press Ctrl+C to stop all services." -ForegroundColor Green
Write-Host "📊 Job monitoring:" -ForegroundColor Cyan

try {
    while ($true) {
        $jobs = @()
        if ($stacJob) { $jobs += $stacJob }
        if ($routerJob) { $jobs += $routerJob }
        if ($uiJob) { $jobs += $uiJob }
        
        $runningJobs = $jobs | Where-Object { $_.State -eq "Running" }
        $failedJobs = $jobs | Where-Object { $_.State -eq "Failed" }
        
        if ($failedJobs.Count -gt 0) {
            Write-Host "❌ Some services have failed:" -ForegroundColor Red
            foreach ($job in $failedJobs) {
                $output = Receive-Job $job -ErrorAction SilentlyContinue
                Write-Host "Failed job output: $output" -ForegroundColor Red
            }
            break
        }
        
        Write-Host "✅ $($runningJobs.Count) services running..." -ForegroundColor Green
        Start-Sleep -Seconds 30
    }
}
catch {
    Write-Host "🛑 Stopping all services..." -ForegroundColor Yellow
}
finally {
    # Cleanup
    $jobs = @($stacJob, $routerJob, $uiJob) | Where-Object { $_ }
    foreach ($job in $jobs) {
        Stop-Job $job -ErrorAction SilentlyContinue
        Remove-Job $job -ErrorAction SilentlyContinue
    }
    Write-Host "🏁 All services stopped." -ForegroundColor Green
}
