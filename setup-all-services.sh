#!/bin/bash
# Earth Copilot - First-Time Setup Script (Linux/Mac)
# Sets up the Earth Copilot repository for first-time use.

set -e  # Exit on any error

echo "🚀 Earth Copilot - First-Time Setup"
echo "=================================================="
echo ""

# Parse command line arguments
FORCE=false
if [ "$1" = "--force" ] || [ "$1" = "-f" ]; then
    FORCE=true
fi

# Check prerequisites
echo "📋 Step 1: Checking Prerequisites..."

# Check Python
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version 2>&1)
    if [[ $PYTHON_VERSION =~ Python\ ([0-9]+)\.([0-9]+) ]]; then
        MAJOR=${BASH_REMATCH[1]}
        MINOR=${BASH_REMATCH[2]}
        if [ "$MAJOR" -eq 3 ] && [ "$MINOR" -ge 8 ]; then
            echo "  ✅ $PYTHON_VERSION found"
        else
            echo "  ❌ Python 3.8+ required, found $PYTHON_VERSION"
            exit 1
        fi
    else
        echo "  ❌ Python not found or invalid version"
        exit 1
    fi
else
    echo "  ❌ Python 3.8+ is required. Please install it."
    exit 1
fi

# Check Node.js
if command -v node &> /dev/null; then
    NODE_VERSION=$(node --version 2>&1)
    if [[ $NODE_VERSION =~ v([0-9]+) ]]; then
        MAJOR=${BASH_REMATCH[1]}
        if [ "$MAJOR" -ge 16 ]; then
            echo "  ✅ Node.js $NODE_VERSION found"
        else
            echo "  ❌ Node.js 16+ required, found $NODE_VERSION"
            exit 1
        fi
    else
        echo "  ❌ Node.js not found"
        exit 1
    fi
else
    echo "  ❌ Node.js 16+ is required. Please install from https://nodejs.org"
    exit 1
fi

# Check Azure Functions Core Tools
if command -v func &> /dev/null; then
    FUNC_VERSION=$(func --version 2>&1)
    echo "  ✅ Azure Functions Core Tools $FUNC_VERSION found"
else
    echo "  ❌ Azure Functions Core Tools required. Install with:"
    echo "     npm install -g azure-functions-core-tools@4 --unsafe-perm true"
    exit 1
fi

echo ""

# Step 2: Python Virtual Environment
echo "🐍 Step 2: Setting up Python Virtual Environment..."

if [ -d ".venv" ]; then
    if [ "$FORCE" = true ]; then
        echo "  🗑️ Removing existing .venv (Force mode)"
        rm -rf .venv
    else
        echo "  ✅ Virtual environment already exists (use --force to recreate)"
    fi
fi

if [ ! -d ".venv" ]; then
    echo "  Creating virtual environment..."
    python3 -m venv .venv
    echo "  ✅ Virtual environment created"
fi

# Activate virtual environment
echo "  Activating virtual environment..."
source .venv/bin/activate

# Step 3: Install Python Dependencies
echo ""
echo "📦 Step 3: Installing Python Dependencies..."

echo "  Upgrading pip..."
python -m pip install --upgrade pip

echo "  Installing root dependencies..."
python -m pip install -r requirements.txt

echo "  Installing router function dependencies..."
cd earth-copilot/router-function-app
python -m pip install -r requirements.txt
cd ../..

# Install verified semantic-kernel version with compatible dependencies
echo "  Installing verified semantic-kernel version..."
python -m pip install semantic-kernel==1.36.2 pydantic==2.11.9 openai==1.107.2 azure-functions azure-functions-worker

# Verify installation
echo "Verifying installation..."
python verify-requirements.py

echo "  ✅ Python dependencies installed and verified"

# Step 4: Install Node.js Dependencies
echo ""
echo "📦 Step 4: Installing React UI Dependencies..."

cd earth-copilot/react-ui
echo "  Running npm install..."
npm install
echo "  ✅ React UI dependencies installed"
cd ../..

# Step 5: Environment Configuration
echo ""
echo "⚙️ Step 5: Environment Configuration..."

if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "  ✅ Created .env from .env.example"
        echo "  ⚠️  Please edit .env file with your Azure OpenAI credentials"
        echo "     Required variables:"
        echo "     - AZURE_OPENAI_ENDPOINT"
        echo "     - AZURE_OPENAI_API_KEY"
        echo "     - AZURE_OPENAI_DEPLOYMENT_NAME"
    else
        echo "  ⚠️  No .env.example found. Please create .env manually"
    fi
else
    echo "  ✅ .env file already exists"
fi

# React UI environment setup
echo ""
echo "  🎨 Setting up React UI environment..."
if [ ! -f "earth-copilot/react-ui/.env" ]; then
    if [ -f "earth-copilot/react-ui/.env.example" ]; then
        cp earth-copilot/react-ui/.env.example earth-copilot/react-ui/.env
        echo "  ✅ Created React UI .env from .env.example"
        echo "  ⚠️  Please edit earth-copilot/react-ui/.env with your Azure Maps credentials"
    else
        echo "  ⚠️  No React UI .env.example found"
    fi
else
    echo "  ✅ React UI .env file already exists"
fi

# Final Summary
echo ""
echo "🎉 Setup Complete!"
echo "=================================================="
echo ""
echo "Next Steps:"
echo "1. 📝 Edit .env file with your Azure OpenAI credentials"
echo "2. 🚀 Run services with: ./run-all-services.sh"
echo "3. 🌐 Open http://localhost:5173 for React UI"
echo "4. 🔧 API endpoint: http://localhost:7071"
echo ""
echo "For troubleshooting, see SYSTEM_REQUIREMENTS.md"