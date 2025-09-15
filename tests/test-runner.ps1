# Earth Copilot Test Runner (PowerShell)
# Usage: .\test-runner.ps1 [command]

param(
    [Parameter(Position=0)]
    [string]$Command = "help"
)

function Show-Help {
    Write-Host "Earth Copilot Test Suite Commands:" -ForegroundColor Green
    Write-Host ""
    Write-Host "  all        - Run all tests (unit + integration)" -ForegroundColor Yellow
    Write-Host "  unit       - Run only unit tests (fast)" -ForegroundColor Yellow
    Write-Host "  integration- Run only integration tests" -ForegroundColor Yellow
    Write-Host "  e2e        - Run end-to-end tests" -ForegroundColor Yellow
    Write-Host "  stac       - Run STAC-related tests" -ForegroundColor Yellow
    Write-Host "  agents     - Run agent tests" -ForegroundColor Yellow
    Write-Host "  network    - Run network tests" -ForegroundColor Yellow
    Write-Host "  fast       - Run fast tests (no network/slow)" -ForegroundColor Yellow
    Write-Host "  coverage   - Run tests with coverage report" -ForegroundColor Yellow
    Write-Host "  debug      - Run tests in debug mode" -ForegroundColor Yellow
    Write-Host "  clean      - Clean test artifacts" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Examples:" -ForegroundColor Cyan
    Write-Host "  .\test-runner.ps1 unit"
    Write-Host "  .\test-runner.ps1 stac"
    Write-Host "  .\test-runner.ps1 coverage"
}

function Run-Tests {
    param([string[]]$TestArgs)
    
    Write-Host "Running: python -m pytest $($TestArgs -join ' ')" -ForegroundColor Cyan
    & python -m pytest @TestArgs
}

switch ($Command.ToLower()) {
    "help" { Show-Help }
    "all" { Run-Tests @("tests/", "-v") }
    "unit" { Run-Tests @("tests/unit/", "-v") }
    "integration" { Run-Tests @("tests/integration/", "-v") }
    "e2e" { Run-Tests @("tests/e2e/", "-v") }
    "stac" { Run-Tests @("-m", "stac", "-v") }
    "agents" { Run-Tests @("-m", "agents", "-v") }
    "network" { Run-Tests @("-m", "network", "-v") }
    "fast" { Run-Tests @("tests/", "-v", "-m", "not network and not slow") }
    "coverage" { Run-Tests @("tests/", "--cov=earth_copilot", "--cov-report=html", "--cov-report=term") }
    "debug" { Run-Tests @("tests/", "-v", "-s", "--tb=long") }
    "clean" {
        Write-Host "Cleaning test artifacts..." -ForegroundColor Yellow
        Get-ChildItem -Recurse -Name "*.pyc" | Remove-Item -Force
        Get-ChildItem -Recurse -Name "__pycache__" -Directory | Remove-Item -Recurse -Force
        Remove-Item -Recurse -Force ".pytest_cache" -ErrorAction SilentlyContinue
        Remove-Item -Recurse -Force "htmlcov" -ErrorAction SilentlyContinue
        Write-Host "Cleanup complete!" -ForegroundColor Green
    }
    default { 
        Write-Host "Unknown command: $Command" -ForegroundColor Red
        Write-Host ""
        Show-Help 
    }
}
