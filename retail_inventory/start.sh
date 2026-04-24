#!/usr/bin/env bash
# ShelfAI — One-click launcher for Mac/Linux

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"

echo ""
echo "  ============================================"
echo "    ShelfAI — AI Retail Inventory Monitor"
echo "  ============================================"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "  [ERROR] Python3 not found. Install Python 3.10+"
    exit 1
fi

# Check Node
if ! command -v node &> /dev/null; then
    echo "  [ERROR] Node.js not found. Install Node.js 18+"
    exit 1
fi

echo "  [1/4] Installing Python dependencies..."
cd "$BACKEND_DIR"
pip3 install -r requirements.txt --quiet 2>/dev/null || echo "  [WARN] Some packages may have failed"

echo "  [2/4] Installing frontend dependencies..."
cd "$FRONTEND_DIR"
if [ ! -d "node_modules" ]; then
    npm install --silent 2>/dev/null
else
    echo "         node_modules exists, skipping..."
fi

echo "  [3/4] Building frontend..."
npm run build --silent 2>/dev/null

echo "  [4/4] Starting backend server..."
echo ""
echo "  ============================================"
echo "    Dashboard:  http://localhost:8000"
echo "    API Docs:   http://localhost:8000/docs"
echo "  ============================================"
echo ""
echo "  Press Ctrl+C to stop the server."
echo ""

cd "$BACKEND_DIR"
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
