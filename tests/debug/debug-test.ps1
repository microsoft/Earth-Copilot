#!/usr/bin/env pwsh

# Earth Copilot Debug Test Script
# Quick tests for debugging end-to-end functionality

param(
    [string]$TestType = "all",     # all, health, query, stac, ui
    [string]$Query = "Show me wildfire damage in California from August 2024",
    [switch]$Verbose
)

Write-Host "🧪 Earth Copilot Debug Test Script" -ForegroundColor Green
Write-Host "==================================" -ForegroundColor Green

$ErrorActionPreference = "Continue"

# Helper function for JSON formatting
function Format-Json {
    param([string]$Json)
    try {
        return ($Json | ConvertFrom-Json | ConvertTo-Json -Depth 10)
    }
    catch {
        return $Json
    }
}

# Helper function for colored output
function Write-TestResult {
    param(
        [string]$Test,
        [bool]$Success,
        [string]$Details = "",
        [object]$Data = $null
    )
    
    $status = if ($Success) { "✅ PASS" } else { "❌ FAIL" }
    $color = if ($Success) { "Green" } else { "Red" }
    
    Write-Host "$status $Test" -ForegroundColor $color
    if ($Details) {
        Write-Host "   $Details" -ForegroundColor Gray
    }
    if ($Data -and $Verbose) {
        Write-Host "   Data: $(Format-Json ($Data | ConvertTo-Json -Depth 3))" -ForegroundColor DarkGray
    }
    Write-Host ""
}

# Test 1: Health Checks
function Test-HealthEndpoints {
    Write-Host "🏥 Testing Health Endpoints..." -ForegroundColor Cyan
    
    # STAC Function Health
    try {
        $stacHealth = Invoke-RestMethod -Uri "http://localhost:7072/api/health" -TimeoutSec 5
        Write-TestResult "STAC Function Health" $true "Port 7072 responding" $stacHealth
    }
    catch {
        Write-TestResult "STAC Function Health" $false "Port 7072 not responding: $($_.Exception.Message)"
    }
    
    # Router Function Health
    try {
        $routerHealth = Invoke-RestMethod -Uri "http://localhost:7071/api/health" -TimeoutSec 5
        Write-TestResult "Router Function Health" $true "Port 7071 responding" $routerHealth
    }
    catch {
        Write-TestResult "Router Function Health" $false "Port 7071 not responding: $($_.Exception.Message)"
    }
    
    # React UI
    try {
        $uiResponse = Invoke-WebRequest -Uri "http://localhost:5173" -TimeoutSec 5
        $success = $uiResponse.StatusCode -eq 200
        Write-TestResult "React UI" $success "Port 5173 status: $($uiResponse.StatusCode)"
    }
    catch {
        Write-TestResult "React UI" $false "Port 5173 not responding: $($_.Exception.Message)"
    }
}

# Test 2: Natural Language Query Processing
function Test-QueryProcessing {
    Write-Host "🌍 Testing Natural Language Query Processing..." -ForegroundColor Cyan
    
    $queryPayload = @{
        query = $Query
    } | ConvertTo-Json
    
    try {
        Write-Host "📤 Sending query: '$Query'" -ForegroundColor Yellow
        
        $response = Invoke-RestMethod -Uri "http://localhost:7071/api/query" `
            -Method POST `
            -ContentType "application/json" `
            -Body $queryPayload `
            -TimeoutSec 30
        
        if ($response.success) {
            Write-TestResult "Natural Language Query" $true "Successfully processed query"
            
            # Check for key components
            $hasCollections = $response.collections -and $response.collections.Count -gt 0
            Write-TestResult "  Collections Selected" $hasCollections "Found $($response.collections.Count) collections" $response.collections
            
            $hasBbox = $response.bbox -and $response.bbox.Count -eq 4
            Write-TestResult "  Location Resolution" $hasBbox "Bounding box: $($response.bbox -join ', ')" $response.bbox
            
            $hasDatetime = $response.datetime -and $response.datetime.Length -gt 0
            Write-TestResult "  Temporal Resolution" $hasDatetime "Date range: $($response.datetime)" $response.datetime
            
            $hasResults = $response.results -and $response.results.features -and $response.results.features.Count -gt 0
            Write-TestResult "  STAC Results" $hasResults "Found $($response.results.features.Count) satellite images"
            
            if ($Verbose) {
                Write-Host "📊 Full Response:" -ForegroundColor DarkCyan
                Write-Host (Format-Json ($response | ConvertTo-Json -Depth 5)) -ForegroundColor DarkGray
            }
        }
        else {
            Write-TestResult "Natural Language Query" $false "Query failed: $($response.error)" $response
        }
    }
    catch {
        Write-TestResult "Natural Language Query" $false "Request failed: $($_.Exception.Message)"
        if ($Verbose) {
            Write-Host "Exception Details: $($_.Exception)" -ForegroundColor Red
        }
    }
}

# Test 3: Direct STAC Function Test
function Test-STACFunction {
    Write-Host "🔍 Testing STAC Function Directly..." -ForegroundColor Cyan
    
    $stacPayload = @{
        collections = @("sentinel-2-l2a")
        bbox = @(-124.0, 32.0, -114.0, 42.0)  # California
        datetime = "2024-08-01T00:00:00Z/2024-08-31T23:59:59Z"
        limit = 5
        query = @{
            "eo:cloud_cover" = @{ "lt" = 20 }
        }
    } | ConvertTo-Json -Depth 5
    
    try {
        Write-Host "📤 Sending STAC query..." -ForegroundColor Yellow
        
        $response = Invoke-RestMethod -Uri "http://localhost:7072/api/stac-search" `
            -Method POST `
            -ContentType "application/json" `
            -Body $stacPayload `
            -TimeoutSec 30
        
        if ($response.success) {
            $featureCount = $response.results.features.Count
            Write-TestResult "STAC Direct Query" $true "Found $featureCount features"
            
            if ($featureCount -gt 0) {
                $firstFeature = $response.results.features[0]
                Write-TestResult "  Feature Properties" $true "ID: $($firstFeature.id), Collection: $($firstFeature.collection)"
                
                $hasAssets = $firstFeature.assets -and $firstFeature.assets.Count -gt 0
                Write-TestResult "  Asset Availability" $hasAssets "Assets: $($firstFeature.assets.Keys -join ', ')"
            }
            
            if ($Verbose) {
                Write-Host "📊 STAC Response:" -ForegroundColor DarkCyan
                Write-Host (Format-Json ($response | ConvertTo-Json -Depth 3)) -ForegroundColor DarkGray
            }
        }
        else {
            Write-TestResult "STAC Direct Query" $false "STAC query failed: $($response.error)" $response
        }
    }
    catch {
        Write-TestResult "STAC Direct Query" $false "Request failed: $($_.Exception.Message)"
    }
}

# Test 4: React UI Integration
function Test-UIIntegration {
    Write-Host "⚛️ Testing React UI Integration..." -ForegroundColor Cyan
    
    # Check if UI is accessible
    try {
        $uiResponse = Invoke-WebRequest -Uri "http://localhost:5173" -TimeoutSec 10
        $success = $uiResponse.StatusCode -eq 200
        Write-TestResult "UI Accessibility" $success "Status: $($uiResponse.StatusCode)"
        
        # Check if it contains expected React content
        $hasReactContent = $uiResponse.Content -match "react" -or $uiResponse.Content -match "earth.copilot" -or $uiResponse.Content -match "root"
        Write-TestResult "UI Content Check" $hasReactContent "Contains expected React content"
        
        # Test API proxy (simplified test)
        try {
            $proxyTest = Invoke-WebRequest -Uri "http://localhost:5173/api/health" -TimeoutSec 5
            $proxyWorking = $proxyTest.StatusCode -eq 200
            Write-TestResult "UI Proxy Configuration" $proxyWorking "Proxy to backend working"
        }
        catch {
            Write-TestResult "UI Proxy Configuration" $false "Proxy test failed: $($_.Exception.Message)"
        }
    }
    catch {
        Write-TestResult "UI Accessibility" $false "UI not accessible: $($_.Exception.Message)"
    }
}

# Test 5: Semantic Translator Components
function Test-SemanticComponents {
    Write-Host "🧠 Testing Semantic Translator Components..." -ForegroundColor Cyan
    
    # Test location resolution
    $locationTest = @{
        query = "Show me data for San Francisco"
    } | ConvertTo-Json
    
    try {
        $response = Invoke-RestMethod -Uri "http://localhost:7071/api/query" `
            -Method POST `
            -ContentType "application/json" `
            -Body $locationTest `
            -TimeoutSec 20
        
        if ($response.bbox) {
            $bbox = $response.bbox
            # San Francisco should be roughly: [-122.5, 37.7, -122.3, 37.8]
            $isSFArea = $bbox[0] -lt -122.0 -and $bbox[0] -gt -123.0 -and $bbox[1] -gt 37.0 -and $bbox[1] -lt 38.0
            Write-TestResult "Location Resolution (SF)" $isSFArea "Bbox: $($bbox -join ', ')" $bbox
        }
        else {
            Write-TestResult "Location Resolution (SF)" $false "No bounding box returned"
        }
    }
    catch {
        Write-TestResult "Location Resolution (SF)" $false "Test failed: $($_.Exception.Message)"
    }
    
    # Test disaster detection
    $disasterTest = @{
        query = "Show me hurricane damage data"
    } | ConvertTo-Json
    
    try {
        $response = Invoke-RestMethod -Uri "http://localhost:7071/api/query" `
            -Method POST `
            -ContentType "application/json" `
            -Body $disasterTest `
            -TimeoutSec 20
        
        if ($response.collections) {
            $hasDisasterCollections = $response.collections -match "sentinel-1" -or $response.collections -match "sentinel-2"
            Write-TestResult "Disaster Detection" $hasDisasterCollections "Collections: $($response.collections -join ', ')"
        }
        else {
            Write-TestResult "Disaster Detection" $false "No collections returned"
        }
    }
    catch {
        Write-TestResult "Disaster Detection" $false "Test failed: $($_.Exception.Message)"
    }
}

# Main test execution
Write-Host "Starting tests for: $TestType" -ForegroundColor White
Write-Host "Test query: '$Query'" -ForegroundColor White
Write-Host ""

switch ($TestType.ToLower()) {
    "health" { Test-HealthEndpoints }
    "query" { Test-QueryProcessing }
    "stac" { Test-STACFunction }
    "ui" { Test-UIIntegration }
    "semantic" { Test-SemanticComponents }
    "all" {
        Test-HealthEndpoints
        Test-QueryProcessing
        Test-STACFunction
        Test-UIIntegration
        Test-SemanticComponents
    }
    default {
        Write-Host "❌ Unknown test type: $TestType" -ForegroundColor Red
        Write-Host "Available tests: health, query, stac, ui, semantic, all" -ForegroundColor Yellow
        exit 1
    }
}

Write-Host "🏁 Test run completed!" -ForegroundColor Green
Write-Host ""
Write-Host "💡 Tips for debugging:" -ForegroundColor Cyan
Write-Host "• Use -Verbose for detailed output" -ForegroundColor White
Write-Host "• Check service logs in VSCode integrated terminal" -ForegroundColor White
Write-Host "• Set breakpoints in semantic_translator.py (line 902)" -ForegroundColor White
Write-Host "• Monitor browser DevTools Network tab for API calls" -ForegroundColor White
