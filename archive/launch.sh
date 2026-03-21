#!/bin/bash

# Wan2.2 Video Generator - Launch Script
# This script kills any existing processes and launches the GUI in your browser

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

echo "🎬 Wan2.2 Video Generator Launcher"
echo "===================================="
echo ""

# Kill any existing processes
echo "🛑 Stopping any existing processes..."
pkill -f "python -m src.main" 2>/dev/null || true
sleep 1

# Kill any process using port 7860
echo "🔓 Freeing port 7860..."
lsof -i :7860 | grep -v COMMAND | awk '{print $2}' | xargs -r kill -9 2>/dev/null || true
sleep 1

# Check if diffusion environment exists
if [ ! -d "diffusion" ]; then
    echo "❌ Error: 'diffusion' environment not found"
    echo "   Please run setup first: ./diffusion/bin/python -m pip install -r requirements.txt"
    exit 1
fi

# Launch the GUI
echo "🚀 Launching Wan2.2 Video Generator..."
echo "   Opening browser at http://127.0.0.1:7860"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

# Launch in background and open browser
./diffusion/bin/python -m src.main &
SERVER_PID=$!

# Wait for server to start
sleep 3

# Try to open browser (works on Linux, macOS, and WSL)
if command -v xdg-open &> /dev/null; then
    xdg-open "http://127.0.0.1:7860" 2>/dev/null || true
elif command -v open &> /dev/null; then
    open "http://127.0.0.1:7860" 2>/dev/null || true
elif command -v wslview &> /dev/null; then
    wslview "http://127.0.0.1:7860" 2>/dev/null || true
fi

# Keep script running
wait $SERVER_PID
