#!/usr/bin/env powershell
<#
.SYNOPSIS
    Earth Copilot - First-Time Setup Script
.DESCRIPTION
    Sets up Write-Host "  Installing router function dependencies..." -ForegroundColor Gray
python -m pip install -r earth-copilot\router-function-app\requirements.txt
    This script handles virtual environment creation, dependency installation,
    and initial configuration setup.
    
.PARAMETER Force
    Force recreate virtual environment if it exists
    
.EXAMPLE
    .\setup-all-services.ps1
    .\setup-all-services.ps1 -Force
#>

param(
    [switch]$Force
)

Write-Host "🚀 Earth Copilot - First-Time Setup" -ForegroundColor Green -BackgroundColor Black
Write-Host "=" * 50 -ForegroundColor Cyan
Write-Host ""

# Check prerequisites
Write-Host "📋 Step 1: Checking Prerequisites..." -ForegroundColor Yellow

# Check Python
try {
    $pythonVersion = python --version 2>&1
    if ($pythonVersion -match "Python (\d+)\.(\d+)\.(\d+)") {
        $major = [int]$matches[1]
        $minor = [int]$matches[2]
        if ($major -eq 3 -and $minor -ge 8) {
            Write-Host "  ✅ Python $pythonVersion found" -ForegroundColor Green
        } else {
            throw "Python 3.8+ required, found $pythonVersion"
        }
    } else {
        throw "Python not found or invalid version"
    }
} catch {
    Write-Host "  ❌ Python 3.8+ is required. Please install from https://python.org" -ForegroundColor Red
    Write-Host "     Make sure to add Python to PATH during installation." -ForegroundColor Yellow
    exit 1
}

# Check Node.js
try {
    $nodeVersion = node --version 2>&1
    if ($nodeVersion -match "v(\d+)\.(\d+)\.(\d+)") {
        $major = [int]$matches[1]
        if ($major -ge 16) {
            Write-Host "  ✅ Node.js $nodeVersion found" -ForegroundColor Green
        } else {
            throw "Node.js 16+ required, found $nodeVersion"
        }
    } else {
        throw "Node.js not found"
    }
} catch {
    Write-Host "  ❌ Node.js 16+ is required. Please install from https://nodejs.org" -ForegroundColor Red
    exit 1
}

# Check Azure Functions Core Tools
try {
    $funcVersion = func --version 2>&1
    Write-Host "  ✅ Azure Functions Core Tools $funcVersion found" -ForegroundColor Green
} catch {
    Write-Host "  ❌ Azure Functions Core Tools required. Install with:" -ForegroundColor Red
    Write-Host "     npm install -g azure-functions-core-tools@4 --unsafe-perm true" -ForegroundColor Yellow
    exit 1
}

Write-Host ""

# Step 2: Python Virtual Environment
Write-Host "🐍 Step 2: Setting up Python Virtual Environment..." -ForegroundColor Yellow

if (Test-Path ".venv" -PathType Container) {
    if ($Force) {
        Write-Host "  🗑️ Removing existing .venv (Force mode)" -ForegroundColor Yellow
        Remove-Item ".venv" -Recurse -Force
    } else {
        Write-Host "  ✅ Virtual environment already exists (use -Force to recreate)" -ForegroundColor Green
    }
}

if (-not (Test-Path ".venv" -PathType Container)) {
    Write-Host "  Creating virtual environment..." -ForegroundColor Gray
    python -m venv .venv
    Write-Host "  ✅ Virtual environment created" -ForegroundColor Green
}

# Activate virtual environment
Write-Host "  Activating virtual environment..." -ForegroundColor Gray
& ".venv\Scripts\Activate.ps1"

# Step 3: Install Python Dependencies
Write-Host ""
Write-Host "📦 Step 3: Installing Python Dependencies..." -ForegroundColor Yellow

Write-Host "  Installing root dependencies..." -ForegroundColor Gray
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

Write-Host "  Installing router function dependencies..." -ForegroundColor Gray
python -m pip install -r earth_copilot\router_function_app\requirements.txt

# Force install semantic-kernel if needed
Write-Host "  Installing verified semantic-kernel version..." -ForegroundColor Gray
python -m pip install --force-reinstall semantic-kernel==1.36.2 pydantic==2.11.9 openai==1.107.2

# Verify installation
Write-Host "  Verifying semantic-kernel installation..." -ForegroundColor Gray
python verify-requirements.py

Write-Host "  ✅ Python dependencies installed and verified" -ForegroundColor Green

# Step 4: Install Node.js Dependencies
Write-Host ""
Write-Host "📦 Step 4: Installing React UI Dependencies..." -ForegroundColor Yellow

Push-Location "earth-copilot\react-ui"
try {
    Write-Host "  Running npm install..." -ForegroundColor Gray
    npm install
    Write-Host "  ✅ React UI dependencies installed" -ForegroundColor Green
} finally {
    Pop-Location
}

# Step 5: Environment Configuration
Write-Host ""
Write-Host "⚙️ Step 5: Environment Configuration..." -ForegroundColor Yellow

if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Host "  ✅ Created .env from .env.example" -ForegroundColor Green
        Write-Host "  ⚠️ Please edit .env file with your Azure OpenAI credentials" -ForegroundColor Yellow
        Write-Host "     Required variables:" -ForegroundColor Gray
        Write-Host "     - AZURE_OPENAI_ENDPOINT" -ForegroundColor Gray
        Write-Host "     - AZURE_OPENAI_API_KEY" -ForegroundColor Gray
        Write-Host "     - AZURE_OPENAI_DEPLOYMENT_NAME" -ForegroundColor Gray
    } else {
        Write-Host "  ⚠️ No .env.example found. Please create .env manually" -ForegroundColor Yellow
    }
} else {
    Write-Host "  ✅ .env file already exists" -ForegroundColor Green
}

# React UI environment setup
Write-Host ""
Write-Host "  🎨 Setting up React UI environment..." -ForegroundColor Cyan
if (-not (Test-Path "earth-copilot/react-ui/.env")) {
    if (Test-Path "earth-copilot/react-ui/.env.example") {
        Copy-Item "earth-copilot/react-ui/.env.example" "earth-copilot/react-ui/.env"
        Write-Host "  ✅ Created React UI .env from .env.example" -ForegroundColor Green
        Write-Host "  ⚠️ Please edit earth-copilot/react-ui/.env with your Azure Maps credentials" -ForegroundColor Yellow
    } else {
        Write-Host "  ⚠️ No React UI .env.example found" -ForegroundColor Yellow
    }
} else {
    Write-Host "  ✅ React UI .env file already exists" -ForegroundColor Green
}

# Final Summary
Write-Host ""
Write-Host "🎉 Setup Complete!" -ForegroundColor Green -BackgroundColor Black
Write-Host "=" * 50 -ForegroundColor Cyan
Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Yellow
Write-Host "1. 📝 Edit .env file with your Azure OpenAI credentials" -ForegroundColor White
Write-Host "2. 🚀 Run services with: .\run-all-services.ps1" -ForegroundColor White
Write-Host "3. 🌐 Open http://localhost:5173 for React UI" -ForegroundColor White
Write-Host "4. 🔧 API endpoint: http://localhost:7071" -ForegroundColor White
Write-Host ""
Write-Host "For troubleshooting, see SYSTEM_REQUIREMENTS.md" -ForegroundColor Cyan