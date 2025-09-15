#!/bin/bash
# Quick setup script for VEDA Search POC

echo "🚀 VEDA Search POC Setup"
echo "========================"

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required but not installed."
    exit 1
fi

# Check if pip is installed
if ! command -v pip &> /dev/null; then
    echo "❌ pip is required but not installed."
    exit 1
fi

echo "✅ Python and pip found"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔄 Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "📚 Installing dependencies..."
cd veda_search_poc
pip install -r requirements.txt

# Install PromptFlow CLI
echo "🔧 Installing PromptFlow CLI..."
pip install promptflow[azure]

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Copy .env_template to .env and fill in your Azure service configurations"
echo "2. Run the indexing script: python ../scripts/create_search_index_with_vectors.py"
echo "3. Create PromptFlow connection: pf connection create --file azure_openai.yaml --name azure_open_ai_connection"
echo "4. Test locally: pf flow test --flow . --interactive"
echo ""
echo "🚀 Ready to explore VEDA data!"