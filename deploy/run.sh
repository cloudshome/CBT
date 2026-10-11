#!/usr/bin/env bash
set -euo pipefail

echo "========================================================="
echo " Launching AI Quant Sentinel / Crypto Brain Terminal (CBT)"
echo "========================================================="

# Create necessary persistent directories
mkdir -p data/vector_store data/github_sandbox data/uploads data/backups

# Pre-flight environment check
if [ ! -f ".env" ]; then
    echo "Creating .env from .env.example..."
    cp .env.example .env
fi

# Run pre-flight verification tests
echo "Running Pre-Flight Verification Gates..."
if [ -d ".venv" ]; then
    ./.venv/bin/pytest tests/ -q
    echo "Starting Uvicorn Server on http://0.0.0.0:8000..."
    exec ./.venv/bin/uvicorn app:app --host 0.0.0.0 --port 8000
else
    python3 -m pytest tests/ -q
    exec python3 -m uvicorn app:app --host 0.0.0.0 --port 8000
fi
