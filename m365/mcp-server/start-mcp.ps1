# start-mcp.ps1
# One-shot launcher for the Planetary Explorer Resilience MCP server.
#
# Usage:
#   .\start-mcp.ps1
#   .\start-mcp.ps1 -BackendUrl https://<your-backend-tunnel>-8080.use.devtunnels.ms
#   .\start-mcp.ps1 -NewToken
#   .\start-mcp.ps1 -ResetTunnel

[CmdletBinding()]
param(
    [string]$BackendUrl = "",
    [int]   $Port       = 8765,
    [string]$TunnelName = "resilience-mcp",
    [switch]$NewToken,
    [switch]$ResetTunnel,
    [switch]$SkipBackendTunnelHeader
)

$ErrorActionPreference = "Stop"
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Here

function Write-Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "    $msg" -ForegroundColor Green }
function Write-Warn2($msg){ Write-Host "    $msg" -ForegroundColor Yellow }

# 1. Find devtunnel.exe
Write-Step "Locating devtunnel.exe"
$dt = (Get-Command devtunnel -ErrorAction SilentlyContinue).Source
if (-not $dt -or -not (Test-Path $dt)) {
    $candidates = @(
        "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\Microsoft.devtunnel_Microsoft.Winget.Source_8wekyb3d8bbwe\devtunnel.exe",
        "$env:LOCALAPPDATA\Microsoft\WinGet\Links\devtunnel.exe",
        "$env:ProgramFiles\Microsoft\devtunnel\devtunnel.exe"
    )
    $dt = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $dt) {
        $found = Get-ChildItem -Path "$env:LOCALAPPDATA\Microsoft\WinGet" -Recurse -Filter devtunnel.exe -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($found) { $dt = $found.FullName }
    }
}
if (-not $dt) {
    throw "Could not locate devtunnel.exe. Install with: winget install Microsoft.devtunnel"
}
Write-Ok "devtunnel: $dt"

# 2. Venv + deps
Write-Step "Ensuring Python venv at .venv"
if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    python -m venv .venv
    Write-Ok "venv created"
} else {
    Write-Ok "venv exists"
}
$Py = Resolve-Path ".\.venv\Scripts\python.exe"

Write-Step "Installing dependencies (quiet)"
& $Py -m pip install --quiet --upgrade pip
& $Py -m pip install --quiet -e ".[dev]"
Write-Ok "deps installed"

# 3. Bearer token in .env
Write-Step "Resolving MCP_BEARER_TOKEN"
$EnvFile = Join-Path $Here ".env"
$Token = $null
if ((Test-Path $EnvFile) -and -not $NewToken) {
    $line = Get-Content $EnvFile | Where-Object { $_ -match "^MCP_BEARER_TOKEN=" } | Select-Object -First 1
    if ($line) { $Token = $line -replace "^MCP_BEARER_TOKEN=", "" }
}
if (-not $Token) {
    $Token = "pe-resilience-" + ([Guid]::NewGuid().ToString("N"))
    "MCP_BEARER_TOKEN=$Token" | Set-Content $EnvFile -Encoding ASCII
    Write-Ok "new token written to .env"
} else {
    Write-Ok "reusing token from .env"
}

# 4. Start MCP server (background job)
Write-Step "Starting MCP server on port $Port"
$busy = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($busy) {
    Write-Warn2 "Port $Port already in use by PID $($busy.OwningProcess), killing"
    Stop-Process -Id $busy.OwningProcess -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 500
}

$LogFile = Join-Path $Here "mcp-server.log"
if (Test-Path $LogFile) { Remove-Item $LogFile -Force }

$ServerScript = {
    param($PyPath, $Cwd, $BackendUrl, $Token, $Port, $SkipTunnelHeader, $LogFile)
    Set-Location $Cwd
    $env:RESILIENCE_API_BASE_URL = $BackendUrl
    if (-not $SkipTunnelHeader) { $env:RESILIENCE_TUNNEL_SKIP = "1" }
    $env:MCP_BEARER_TOKEN = $Token
    $env:MCP_PORT = "$Port"
    & $PyPath "server.py" *>&1 | Tee-Object -FilePath $LogFile
}

$Job = Start-Job -Name "mcp-server" -ScriptBlock $ServerScript -ArgumentList `
    $Py, $Here, $BackendUrl, $Token, $Port, [bool]$SkipBackendTunnelHeader, $LogFile

$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Milliseconds 500
    $listen = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($listen) { $ready = $true; break }
    if ($Job.State -eq "Failed" -or $Job.State -eq "Completed") { break }
}
if (-not $ready) {
    Write-Host "`nServer failed to start. Last 30 lines of log:`n" -ForegroundColor Red
    if (Test-Path $LogFile) { Get-Content $LogFile -Tail 30 }
    Stop-Job $Job -ErrorAction SilentlyContinue
    Remove-Job $Job -Force -ErrorAction SilentlyContinue
    exit 1
}
Write-Ok "uvicorn listening on http://0.0.0.0:$Port"

try {
    $probe = Invoke-WebRequest "http://127.0.0.1:$Port/healthz" -UseBasicParsing -TimeoutSec 5
    if ($probe.StatusCode -eq 200) { Write-Ok "/healthz returned 200 ok" }
} catch {
    Write-Warn2 "/healthz probe failed: $($_.Exception.Message)"
}

# 5. Tunnel
Write-Step "Preparing devtunnel '$TunnelName'"
if ($ResetTunnel) {
    Write-Warn2 "deleting existing tunnel"
    & $dt delete $TunnelName -f 2>$null | Out-Null
}

$exists = $false
$listOut = & $dt list 2>$null
if ($LASTEXITCODE -eq 0 -and $listOut -match [Regex]::Escape($TunnelName)) { $exists = $true }

if (-not $exists) {
    Write-Ok "creating tunnel"
    & $dt create $TunnelName --allow-anonymous | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "devtunnel create failed (exit $LASTEXITCODE). Try: $dt user login" }
}

# Idempotent port add (http because uvicorn serves plain HTTP locally;
# devtunnels still exposes HTTPS publicly)
& $dt port create $TunnelName -p $Port --protocol http 2>$null | Out-Null

Write-Step "Hosting tunnel (foreground)"
Write-Host ""
Write-Host "================================================================" -ForegroundColor DarkGray
Write-Host (" Backend (resilience API): {0}" -f $BackendUrl) -ForegroundColor Gray
Write-Host (" Local MCP server:         http://127.0.0.1:{0}/mcp" -f $Port) -ForegroundColor Gray
Write-Host (" Bearer token (.env):      {0}" -f $Token) -ForegroundColor Yellow
Write-Host "================================================================" -ForegroundColor DarkGray
Write-Host ""
Write-Host " Public tunnel URL prints below in a few seconds." -ForegroundColor Cyan
Write-Host " In Copilot Studio, use:" -ForegroundColor Cyan
Write-Host '   Server URL     = (public-url)/mcp' -ForegroundColor Cyan
Write-Host '   Authentication = API key' -ForegroundColor Cyan
Write-Host '   Header name    = Authorization' -ForegroundColor Cyan
Write-Host (' Header value   = Bearer {0}' -f $Token) -ForegroundColor Cyan
Write-Host ""
Write-Host " Press Ctrl+C to stop both the tunnel and the MCP server." -ForegroundColor DarkGray
Write-Host ""

$cleanup = {
    Write-Host "`nStopping MCP server background job..." -ForegroundColor DarkGray
    $j = Get-Job -Name 'mcp-server' -ErrorAction SilentlyContinue
    if ($j) {
        Stop-Job $j -ErrorAction SilentlyContinue
        Remove-Job $j -Force -ErrorAction SilentlyContinue
    }
    $busy2 = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($busy2) { Stop-Process -Id $busy2.OwningProcess -Force -ErrorAction SilentlyContinue }
}

try {
    & $dt host $TunnelName
}
finally {
    & $cleanup
}
