#requires -Version 5.1
<#
.SYNOPSIS
  End-to-end smoke test for the Forecast Agent + weather stub.

.DESCRIPTION
  Step 1: start the weather-stub server (uvicorn) on localhost:8090.
  Step 2: hit /health, /info, /aurora/score, /earth2/fcn/score directly.
  Step 3: start the backend (uvicorn fastapi_app:app) pointed at the
          stub via env vars, hit /api/geoint/forecast/health and
          /api/geoint/forecast.
  Step 4: print a one-line PASS/FAIL summary and tear both servers down.

.EXAMPLE
  pwsh -File scripts/smoke-weather.ps1

  -StubOnly only runs the stub (skip backend) - useful when you just
  want to poke /aurora/score by hand.
#>
[CmdletBinding()]
param(
  [switch]$StubOnly,
  [int]$StubPort = 8090,
  [int]$BackendPort = 8095
)

$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$stubDir = Join-Path $repoRoot "weather-stub-server"
$backendDir = Join-Path $repoRoot "container-app"

function Wait-Url($url, $timeoutSec = 20) {
  $deadline = (Get-Date).AddSeconds($timeoutSec)
  while ((Get-Date) -lt $deadline) {
    try {
      $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
      if ($r.StatusCode -eq 200) { return $true }
    } catch { Start-Sleep -Milliseconds 300 }
  }
  return $false
}

$stubProc = $null
$backendProc = $null

try {
  # ── 1. start stub ─────────────────────────────────────────────────────
  Write-Host "[1/4] starting weather-stub on :$StubPort ..." -ForegroundColor Cyan
  Push-Location $stubDir
  $stubProc = Start-Process -FilePath "uvicorn" `
      -ArgumentList @("app:app","--host","127.0.0.1","--port",$StubPort) `
      -PassThru -WindowStyle Hidden
  Pop-Location
  if (-not (Wait-Url "http://127.0.0.1:$StubPort/health")) {
    throw "weather-stub did not become healthy in time"
  }
  Write-Host "    stub /health OK" -ForegroundColor Green

  # ── 2. direct stub calls ──────────────────────────────────────────────
  Write-Host "[2/4] hitting stub endpoints directly ..." -ForegroundColor Cyan
  $body = @{ lat=38.9; lon=-77.0; lead_hours=72; variables=@("t2m","precip"); grid_size=4 } | ConvertTo-Json
  foreach ($path in @("/aurora/score","/earth2/fcn/score")) {
    $resp = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:$StubPort$path" -Body $body -ContentType "application/json"
    if (-not $resp.model -or -not $resp.variables.t2m) { throw "stub $path returned unexpected shape" }
    Write-Host "    POST $path -> model=$($resp.model) center t2m=$([math]::Round($resp.variables.t2m[2][2],2))K" -ForegroundColor Green
  }

  if ($StubOnly) {
    Write-Host "`nPASS (stub only). Stub still running at http://127.0.0.1:$StubPort -- Ctrl+C to stop." -ForegroundColor Green
    Write-Host "    Ctrl+C this script, or run: Stop-Process -Id $($stubProc.Id)"
    Wait-Process -Id $stubProc.Id
    return
  }

  # ── 3. start backend pointed at stub ──────────────────────────────────
  Write-Host "[3/4] starting backend (fastapi_app) on :$BackendPort pointed at stub ..." -ForegroundColor Cyan
  $env:AURORA_ENDPOINT_URL = "http://127.0.0.1:$StubPort"
  $env:EARTH2_FCN_ENDPOINT_URL = "http://127.0.0.1:$StubPort"
  $env:FORECAST_AGENT_ENABLED = "1"
  Push-Location $backendDir
  $backendProc = Start-Process -FilePath "uvicorn" `
      -ArgumentList @("fastapi_app:app","--host","127.0.0.1","--port",$BackendPort,"--log-level","warning") `
      -PassThru -WindowStyle Hidden
  Pop-Location
  if (-not (Wait-Url "http://127.0.0.1:$BackendPort/api/geoint/forecast/health" 40)) {
    throw "backend forecast /health did not become reachable"
  }
  $health = Invoke-RestMethod -Uri "http://127.0.0.1:$BackendPort/api/geoint/forecast/health"
  Write-Host "    forecast /health status=$($health.status) providers=$($health.providers.Count)" -ForegroundColor Green
  if ($health.providers.Count -lt 2) { throw "expected 2 providers, got $($health.providers.Count)" }

  # ── 4. agent call ─────────────────────────────────────────────────────
  Write-Host "[4/4] calling /api/geoint/forecast ..." -ForegroundColor Cyan
  $reqBody = @{
    latitude = 38.9; longitude = -77.0; lead_hours = 72
    variables = @("t2m","precip","u10","v10"); grid_size = 6
    user_query = "Forecast for Washington, DC next 72 hours"
    location_label = "Washington, DC"
  } | ConvertTo-Json
  $resp = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:$BackendPort/api/geoint/forecast" -Body $reqBody -ContentType "application/json"
  if ($resp.status -ne "success") { throw "agent returned status=$($resp.status)" }
  $result = $resp.result
  Write-Host "    providers_succeeded: $($result.providers_succeeded -join ', ')" -ForegroundColor Green
  Write-Host "    workflow_ms       : $($result.timing_ms.workflow_ms)" -ForegroundColor Green
  if ($result.ensemble_summary.variables.t2m) {
    $t = $result.ensemble_summary.variables.t2m
    Write-Host ("    ensemble t2m      : mean={0}K spread={1}K (n={2})" -f $t.mean,$t.spread,$t.samples) -ForegroundColor Green
  }
  if (-not $result.providers_succeeded -or $result.providers_succeeded.Count -lt 2) {
    throw "expected 2 providers to succeed; got $($result.providers_succeeded.Count)"
  }

  Write-Host "`n[PASS] Forecast Agent end-to-end smoke test succeeded." -ForegroundColor Green
}
catch {
  Write-Host "`n[FAIL] $_" -ForegroundColor Red
  exit 1
}
finally {
  foreach ($p in @($backendProc, $stubProc)) {
    if ($p -and -not $p.HasExited) {
      try { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue } catch {}
    }
  }
}
