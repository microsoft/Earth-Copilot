#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Test Earth Copilot Services - Complete Pipeline Testing
.DESCRIPTION
    This script tests all Earth Copilot services and the GPT-5 query translator:
    1. Tests each service health endpoint
    2. Tests the GPT-5 query translator with sample queries
    3. Tests the complete pipeline end-to-end
.EXAMPLE
    .\test-all-services.ps1
    .\test-all-services.ps1 -Verbose
#>

param(
    [switch]$Verbose,
    [string[]]$TestQueries = @(
        "Show me Sentinel-1 radar data for Seattle from 2024",
        "Find optical imagery of New York City from last month", 
        "Get elevation data for the Pacific Northwest",
        "Show me land cover classification for California"
    )
)

# Configuration
$Services = @(
    @{
        Name = "Router Function"
        Port = 7071
        HealthEndpoint = "http://localhost:7071/api/health"
        TestEndpoint = "http://localhost:7071/api/query"
        Method = "POST"
    },
    @{
        Name = "STAC Search Function"
        Port = 7072
        HealthEndpoint = "http://localhost:7072/api/health"
        TestEndpoint = "http://localhost:7072/api/stac-search"
        Method = "POST"
    },
    @{
        Name = "React UI"
        Port = 5173
        HealthEndpoint = "http://localhost:5173"
        TestEndpoint = "http://localhost:5173"
        Method = "GET"
    }
)

function Write-TestHeader {
    param($Message)
    Write-Host "`n" -NoNewline
    Write-Host "🧪 " -NoNewline -ForegroundColor Blue
    Write-Host $Message -ForegroundColor White -BackgroundColor Blue
    Write-Host "─" * ($Message.Length + 3) -ForegroundColor Blue
}

function Write-Success {
    param($Message)
    Write-Host "✅ $Message" -ForegroundColor Green
}

function Write-Failure {
    param($Message)
    Write-Host "❌ $Message" -ForegroundColor Red
}

function Write-Info {
    param($Message)
    Write-Host "ℹ️  $Message" -ForegroundColor Yellow
}

function Test-ServiceHealth {
    param($Service)
    
    Write-Info "Testing $($Service.Name) health..."
    
    try {
        $response = Invoke-RestMethod -Uri $Service.HealthEndpoint -Method GET -TimeoutSec 10
        Write-Success "$($Service.Name) is healthy!"
        
        if ($Verbose -and $response) {
            Write-Host "   Response: $($response | ConvertTo-Json -Compress -Depth 2)" -ForegroundColor Gray
        }
        
        return $true
    }
    catch {
        Write-Failure "$($Service.Name) health check failed: $($_.Exception.Message)"
        return $false
    }
}

function Test-RouterQuery {
    param($Query)
    
    Write-Info "Testing query: '$Query'"
    
    try {
        $body = @{ query = $Query } | ConvertTo-Json
        $response = Invoke-RestMethod -Uri "http://localhost:7071/api/query" -Method POST -Body $body -ContentType "application/json" -TimeoutSec 30
        
        Write-Success "Query successful!"
        
        if ($response) {
            Write-Host "   📊 Response Summary:" -ForegroundColor Cyan
            
            if ($response.stac_params) {
                Write-Host "   🗂️  Collections: $($response.stac_params.collections -join ', ')" -ForegroundColor Gray
                Write-Host "   📍 Location: $($response.stac_params.bbox -join ', ')" -ForegroundColor Gray
                Write-Host "   📅 Time: $($response.stac_params.datetime)" -ForegroundColor Gray
                Write-Host "   📈 Items Found: $($response.stac_results.features.Count)" -ForegroundColor Gray
            }
            
            if ($Verbose) {
                Write-Host "   🔍 Full Response:" -ForegroundColor DarkGray
                Write-Host "   $($response | ConvertTo-Json -Depth 3)" -ForegroundColor DarkGray
            }
        }
        
        return $true
    }
    catch {
        Write-Failure "Query failed: $($_.Exception.Message)"
        
        if ($Verbose) {
            Write-Host "   Error Details: $($_.Exception)" -ForegroundColor DarkRed
        }
        
        return $false
    }
}

function Test-DirectSTACCall {
    Write-Info "Testing direct STAC function call..."
    
    try {
        $stacBody = @{
            collections = @("sentinel-1-grd")
            bbox = @(-122.4194, 47.6062, -122.3394, 47.6462)  # Seattle area
            datetime = "2024-01-01T00:00:00Z/2024-12-31T23:59:59Z"
            limit = 5
        } | ConvertTo-Json
        
        $response = Invoke-RestMethod -Uri "http://localhost:7072/api/stac-search" -Method POST -Body $stacBody -ContentType "application/json" -TimeoutSec 30
        
        Write-Success "Direct STAC call successful!"
        Write-Host "   📈 Items Found: $($response.features.Count)" -ForegroundColor Gray
        
        return $true
    }
    catch {
        Write-Failure "Direct STAC call failed: $($_.Exception.Message)"
        return $false
    }
}

function Show-ServiceStatus {
    Write-TestHeader "Current Service Status"
    
    foreach ($service in $Services) {
        try {
            $connection = Test-NetConnection -ComputerName localhost -Port $service.Port -InformationLevel Quiet -WarningAction SilentlyContinue
            $status = if ($connection) { "✅ RUNNING" } else { "❌ NOT RUNNING" }
            Write-Host "$($service.Name.PadRight(25)) | Port $($service.Port) | $status"
        }
        catch {
            Write-Host "$($service.Name.PadRight(25)) | Port $($service.Port) | ❌ ERROR" -ForegroundColor Red
        }
    }
}

function Show-TestCommands {
    Write-TestHeader "Quick Test Commands"
    
    Write-Host "🌐 React UI:           " -NoNewline -ForegroundColor Cyan
    Write-Host "Start-Process 'http://localhost:5173'" -ForegroundColor Gray
    
    Write-Host "🏥 Router Health:      " -NoNewline -ForegroundColor Cyan  
    Write-Host "Invoke-RestMethod -Uri 'http://localhost:7071/api/health'" -ForegroundColor Gray
    
    Write-Host "🏥 STAC Health:        " -NoNewline -ForegroundColor Cyan
    Write-Host "Invoke-RestMethod -Uri 'http://localhost:7072/api/health'" -ForegroundColor Gray
    
    Write-Host "🧠 Test GPT-5 Query:   " -NoNewline -ForegroundColor Cyan
    Write-Host "`$body = @{ query = 'Show me Sentinel-1 data for Seattle' } | ConvertTo-Json; Invoke-RestMethod -Uri 'http://localhost:7071/api/query' -Method POST -Body `$body -ContentType 'application/json'" -ForegroundColor Gray
}

# Main execution
Write-Host "🚀 Earth Copilot Pipeline Testing" -ForegroundColor White -BackgroundColor Blue
Write-Host "Testing Router (7071), STAC (7072), and React UI (5173)" -ForegroundColor White
Write-Host ""

# Check service status
Show-ServiceStatus

# Health checks
Write-TestHeader "Health Checks"
$healthResults = @{}
foreach ($service in $Services) {
    $healthResults[$service.Name] = Test-ServiceHealth $service
}

# Test direct STAC call first
Write-TestHeader "Direct STAC Function Test"
$stacWorking = Test-DirectSTACCall

# Test GPT-5 Query Translator
Write-TestHeader "GPT-5 Query Translator Tests"
$queryResults = @{}

foreach ($query in $TestQueries) {
    $queryResults[$query] = Test-RouterQuery $query
    Start-Sleep -Seconds 2  # Avoid overwhelming the service
}

# Results Summary
Write-TestHeader "Test Results Summary"

Write-Host "🏥 Health Checks:" -ForegroundColor Cyan
foreach ($result in $healthResults.GetEnumerator()) {
    $status = if ($result.Value) { "✅ PASS" } else { "❌ FAIL" }
    Write-Host "   $($result.Key): $status"
}

Write-Host "`n🧠 GPT-5 Query Tests:" -ForegroundColor Cyan
$passedQueries = ($queryResults.Values | Where-Object { $_ }).Count
$totalQueries = $queryResults.Count
Write-Host "   Passed: $passedQueries/$totalQueries queries"

foreach ($result in $queryResults.GetEnumerator()) {
    $status = if ($result.Value) { "✅" } else { "❌" }
    Write-Host "   $status $($result.Key)"
}

Write-Host "`n📊 Overall Pipeline Health:" -ForegroundColor Cyan
$routerHealthy = $healthResults["Router Function"]
$stacHealthy = $healthResults["STAC Search Function"] 
$uiHealthy = $healthResults["React UI"]
$queriesWorking = $passedQueries -gt 0

if ($routerHealthy -and $stacHealthy -and $uiHealthy -and $queriesWorking) {
    Write-Success "🎉 All systems operational! Pipeline is ready for testing."
} elseif ($routerHealthy -and $stacHealthy -and $uiHealthy) {
    Write-Info "⚠️  Services are healthy but GPT-5 queries need attention."
} else {
    Write-Failure "🚨 Some services need attention before full testing can proceed."
}

Show-TestCommands

Write-Host "`n🎯 Next Steps:" -ForegroundColor Cyan
Write-Host "   1. Use React UI at http://localhost:5173 for interactive testing" -ForegroundColor Gray
Write-Host "   2. Try different natural language queries in the UI" -ForegroundColor Gray
Write-Host "   3. Verify SAR, elevation, and classification data rendering" -ForegroundColor Gray
Write-Host "   4. Test temporal intelligence with date ranges" -ForegroundColor Gray
