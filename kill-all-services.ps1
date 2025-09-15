# Earth Copilot - Kill All Services Script

Write-Host "STOP - Stopping All Earth Copilot Services..." -ForegroundColor Red

# Function to kill processes on specific ports
function Kill-Port {
    param($Port)
    Write-Host "Checking port $Port..." -ForegroundColor Yellow
    $connections = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    if ($connections) {
        Write-Host "Found processes on port $Port, stopping..." -ForegroundColor Yellow
        $connections | ForEach-Object {
            $processId = $_.OwningProcess
            if ($processId -and $processId -ne 0) {
                try {
                    Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
                    Write-Host "  OK - Stopped process $processId" -ForegroundColor Green
                } catch {
                    Write-Host "  WARNING - Could not stop process $processId" -ForegroundColor Yellow
                }
            }
        }
    } else {
        Write-Host "  OK - Port $Port is free" -ForegroundColor Green
    }
}

# Stop all func processes
Write-Host "Stopping Azure Functions processes..." -ForegroundColor Yellow
$funcProcesses = Get-Process -Name "func" -ErrorAction SilentlyContinue
if ($funcProcesses) {
    $funcProcesses | ForEach-Object {
        Write-Host "  Stopping func process: $($_.Id)" -ForegroundColor Yellow
        Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
    }
    Write-Host "  OK - All func processes stopped" -ForegroundColor Green
} else {
    Write-Host "  OK - No func processes running" -ForegroundColor Green
}

# Kill processes on known ports (Simplified Architecture)
Kill-Port 7071  # Unified Router+STAC Function
Kill-Port 5173  # React UI port
Kill-Port 3000  # Alternative React port

# Clean up old architecture ports (if any)
Kill-Port 7072  # Old STAC function port
Kill-Port 7073  # Old Router function port
Kill-Port 8000  # Old main app port

# Stop any Python processes that might be hanging
Write-Host "Checking for orphaned Python processes..." -ForegroundColor Yellow
$pythonProcesses = Get-Process -Name "python" -ErrorAction SilentlyContinue
if ($pythonProcesses) {
    $pythonProcesses | ForEach-Object {
        Write-Host "  Stopping orphaned Python process: $($_.Id)" -ForegroundColor Yellow
        Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
    }
} else {
    Write-Host "  OK - No orphaned Python processes" -ForegroundColor Green
}

# Wait a moment for cleanup
Start-Sleep -Seconds 3

Write-Host ""
Write-Host "CLEAN - All services stopped successfully!" -ForegroundColor Green
Write-Host "Ready to start services with run-all-services.ps1" -ForegroundColor Cyan