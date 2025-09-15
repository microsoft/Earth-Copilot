#!/bin/bash
# Earth Copilot - Complete System Startup Script (Linux/Mac)
# Starts both React UI and Azure Functions services

set -e  # Exit on any error

echo "🚀 Earth Copilot - Starting All Services"
echo "=================================================="
echo ""

# Function to check if a port is in use
check_port() {
    local port=$1
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
        return 0  # Port is in use
    else
        return 1  # Port is free
    fi
}

# Function to wait for service to be ready
wait_for_service() {
    local url=$1
    local service_name=$2
    local max_wait=${3:-30}
    
    echo "⏳ Waiting for $service_name to be ready..."
    local waited=0
    while [ $waited -lt $max_wait ]; do
        if curl -s "$url" >/dev/null 2>&1; then
            echo "✅ $service_name is ready!"
            return 0
        fi
        sleep 2
        waited=$((waited + 2))
        echo "   Still waiting... ($waited/$max_wait seconds)"
    done
    echo "❌ $service_name failed to start within $max_wait seconds"
    return 1
}

# Function to clean up existing processes
cleanup_services() {
    echo "🧹 Cleaning up existing processes..."
    pkill -f "func host" 2>/dev/null || true
    pkill -f "vite" 2>/dev/null || true
    pkill -f "npm run dev" 2>/dev/null || true
    sleep 2
}

echo "🎯 Architecture (2 Services):"
echo "  1. React UI (Port 5173)"
echo "  2. Azure Functions Backend (Port 7071)"
echo ""

# Check if ports are already in use
if check_port 7071; then
    echo "⚠️  Port 7071 is already in use. Cleaning up..."
    cleanup_services
fi

if check_port 5173; then
    echo "⚠️  Port 5173 is already in use. Cleaning up..."
    cleanup_services
fi

# 1. Start Azure Functions Backend (Port 7071)
echo "🔧 Starting Azure Functions Backend..."
cd earth-copilot/router-function-app

# Check if virtual environment exists and activate it
if [ -d "../../.venv" ]; then
    echo "   Activating virtual environment..."
    source ../../.venv/bin/activate
elif [ -d ".venv" ]; then
    echo "   Activating local virtual environment..."
    source .venv/bin/activate
else
    echo "   ⚠️  No virtual environment found. Please run setup-all-services.sh first"
fi

nohup func host start --port 7071 > /tmp/functions.log 2>&1 &
FUNC_PID=$!
echo "   Process ID: $FUNC_PID"
cd ../..

# Wait for backend to start
sleep 8
if wait_for_service "http://localhost:7071/api/health" "Azure Functions Backend" 30; then
    echo "   ✅ Backend endpoints available:"
    echo "      • Health: http://localhost:7071/api/health"
    echo "      • Query: http://localhost:7071/api/query"
    echo "      • STAC Search: http://localhost:7071/api/stac-search"
else
    echo "   ❌ Backend failed to start. Check logs: tail -f /tmp/functions.log"
    exit 1
fi

# 2. Start React UI Frontend (Port 5173)
echo ""
echo "🎨 Starting React UI Frontend..."
cd earth-copilot/react-ui
nohup npm run dev > /tmp/vite.log 2>&1 &
VITE_PID=$!
echo "   Process ID: $VITE_PID"
cd ../..

# Wait for frontend to start
sleep 5
if wait_for_service "http://localhost:5173" "React UI Frontend" 20; then
    echo "   ✅ Frontend available at: http://localhost:5173"
else
    echo "   ❌ Frontend failed to start. Check logs: tail -f /tmp/vite.log"
    exit 1
fi

# Test system connectivity
echo ""
echo "🔍 System Health Check..."
echo "----------------------------------------"

# Test backend health
if curl -s http://localhost:7071/api/health | grep -q '"status":"healthy"'; then
    echo "✅ Backend: Healthy"
else
    echo "❌ Backend: Not responding properly"
fi

# Test frontend
if curl -s -I http://localhost:5173/ | grep -q "HTTP/1.1 200"; then
    echo "✅ Frontend: Healthy"
else
    echo "❌ Frontend: Not responding properly"
fi

echo ""
echo "🎉 All Services Started Successfully!"
echo "=================================================="
echo ""
echo "📊 Service Status:"
echo "   Backend (Functions): PID $FUNC_PID - http://localhost:7071"
echo "   Frontend (React UI): PID $VITE_PID - http://localhost:5173"
echo ""
echo "📁 Service Logs:"
echo "   Backend: tail -f /tmp/functions.log"
echo "   Frontend: tail -f /tmp/vite.log"
echo ""
echo "🌐 Access Options:"
echo "   • In VS Code: Use Simple Browser with http://localhost:5173"
echo "   • In Codespaces: Use PORTS tab to forward port 5173 and make it public"
echo ""
echo "🧪 Testing Steps:"
echo "   1. Open the UI at http://localhost:5173"
echo "   2. Try a query like: 'Show me satellite imagery of California'"
echo "   3. Verify results appear on the map"
echo ""
echo "🛑 To stop services: ./kill-all-services.sh"
echo "   Or manually: pkill -f 'func host' && pkill -f 'vite'"