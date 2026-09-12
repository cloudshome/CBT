#!/usr/bin/env bash
set -euo pipefail

echo "========================================================="
echo " Installing System Packages & Python Dependencies (CBT)"
echo "========================================================="

if command -v apt-get &> /dev/null; then
    sudo apt-get update
    sudo apt-get install -y python3 python3-venv python3-pip sqlite3 ffmpeg git curl
fi

if [ ! -d ".venv" ]; then
    echo "Creating Python virtual environment (.venv)..."
    python3 -m venv .venv
fi

echo "Installing Python requirements..."
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -r requirements.txt

echo "✓ Dependencies installed successfully!"
