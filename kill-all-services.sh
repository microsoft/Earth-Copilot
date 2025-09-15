#!/bin/bash
# Earth Copilot - Kill All Services Script (Linux/Mac)

echo "🛑 Stopping All Earth Copilot Services..."
echo "======================================="

# Function to kill processes on specific ports
kill_port() {
    local port=$1
    echo "🔍 Checking port $port..."
    
    local pids=$(lsof -ti:$port 2>/dev/null)
    if [ -n "$pids" ]; then
        echo "   Found processes on port $port: $pids"
        for pid in $pids; do
            if kill -9 "$pid" 2>/dev/null; then
                echo "   ✅ Stopped process $pid"
            else
                echo "   ⚠️  Could not stop process $pid"
            fi
        done
    else
        echo "   ✅ Port $port is free"
    fi
}

# Stop Azure Functions processes
echo "🔧 Stopping Azure Functions processes..."
pkill -f "func host" 2>/dev/null && echo "   ✅ Stopped func processes" || echo "   ✅ No func processes running"

# Stop React/Vite processes
echo "🎨 Stopping React UI processes..."
pkill -f "vite" 2>/dev/null && echo "   ✅ Stopped vite processes" || echo "   ✅ No vite processes running"
pkill -f "npm run dev" 2>/dev/null && echo "   ✅ Stopped npm dev processes" || echo "   ✅ No npm dev processes running"

# Kill processes on known ports
echo "🔌 Freeing up ports..."
kill_port 7071  # Azure Functions Backend
kill_port 5173  # React UI

# Clean up legacy ports if any
kill_port 7072  # Old STAC function port
kill_port 7073  # Old Router function port  
kill_port 8000  # Old main app port
kill_port 3000  # Alternative React port

# Clean up any orphaned Python processes related to Azure Functions
echo "🐍 Checking for orphaned Python Azure Functions processes..."
pkill -f "azure-functions-core-tools.*worker.py" 2>/dev/null && echo "   ✅ Stopped orphaned Python workers" || echo "   ✅ No orphaned Python workers"

# Wait for cleanup
echo "⏳ Waiting for cleanup..."
sleep 3

# Final port check
echo "🔍 Final port check..."
if lsof -Pi :7071 -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "   ⚠️  Port 7071 still in use"
else
    echo "   ✅ Port 7071 is free"
fi

if lsof -Pi :5173 -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "   ⚠️  Port 5173 still in use"
else
    echo "   ✅ Port 5173 is free"
fi

echo ""
echo "🎉 All services stopped successfully!"
echo "📚 Ready to start services with: ./run-all-services.sh"