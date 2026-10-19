#!/usr/bin/env bash
# =============================================================================
#   CRYPTO BRAIN TERMINAL (CBT / SKY) - INSTITUTIONAL DESK
#   Ubuntu / Linux Unified Launcher
# =============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================================"
echo "  CRYPTO BRAIN TERMINAL (CBT / SKY) - UBUNTU LAUNCHER"
echo "============================================================"

# Detect Python interpreter (prefer .venv, fallback to python3/python)
if [ -f "$SCRIPT_DIR/.venv/bin/python" ]; then
    PYTHON_CMD="$SCRIPT_DIR/.venv/bin/python"
elif command -v python3 &>/dev/null; then
    PYTHON_CMD="python3"
else
    PYTHON_CMD="python"
fi

echo "[1/2] Starting Python FastAPI Backend on Port 8000 using $PYTHON_CMD..."
$PYTHON_CMD app.py &
BACKEND_PID=$!

echo "[2/2] Waiting for backend initialization..."
sleep 3

echo "[3/3] Starting Vite Frontend on Port 5173..."
npm --prefix frontend run dev &
FRONTEND_PID=$!

cleanup() {
    echo ""
    echo "Shutting down CBT services..."
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null || true
    wait $BACKEND_PID $FRONTEND_PID 2>/dev/null || true
    echo "Services stopped cleanly."
}

trap cleanup EXIT INT TERM

echo ""
echo "============================================================"
echo "  All systems active!"
echo "  Open your browser at: http://localhost:5173"
echo "============================================================"
echo "Press Ctrl+C to stop all servers."
wait

