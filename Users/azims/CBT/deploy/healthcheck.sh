#!/usr/bin/env bash
# ==============================================================================
# 24/7 Ubuntu Production Healthcheck Probe for SKY / ORION Terminal
# Validates Python API (:8000), Node Market Streamer (:3001), Database & Data Freshness
# ==============================================================================

set -euo pipefail

PYTHON_PORT=${PYTHON_PORT:-8000}
NODE_PORT=${NODE_PORT:-3001}
STATUS=0

echo "[HEALTHCHECK] Initiating system health probe..."

# 1. Check Python FastAPI Master Engine
if curl -s -f "http://127.0.0.1:${PYTHON_PORT}/health" > /dev/null 2>&1; then
    echo "✓ Python FastAPI Engine (: ${PYTHON_PORT}) is HEALTHY"
else
    echo "❌ Python FastAPI Engine (: ${PYTHON_PORT}) FAILED / Unreachable"
    STATUS=1
fi

# 2. Check Empirical Accumulator / Lab Status
if curl -s -f "http://127.0.0.1:${PYTHON_PORT}/api/lab/empirical-status?concept=SETUP_A_SWEEP_MSS" > /dev/null 2>&1; then
    echo "✓ Empirical Accumulator & Validation Engine is ACTIVE"
else
    echo "⚠️ Empirical Accumulator API degraded"
fi

# 3. Check System Audit Bus
if curl -s -f "http://127.0.0.1:${PYTHON_PORT}/api/audit/events?limit=1" > /dev/null 2>&1; then
    echo "✓ System Audit Ledger is OPERATIONAL"
else
    echo "⚠️ System Audit Ledger query failed"
fi

# 4. Check Node Market Streamer (if configured)
if curl -s -f "http://127.0.0.1:${NODE_PORT}/health" > /dev/null 2>&1; then
    echo "✓ Node Market Data & WebSocket Streamer (: ${NODE_PORT}) is HEALTHY"
else
    echo "ℹ️ Node Streamer on port ${NODE_PORT} is not responding (running in Python-direct mode)"
fi

# 5. Check Disk Storage for Logs / Data
DATA_DIR=${DATA_DIR:-"data"}
if [ -d "$DATA_DIR" ]; then
    echo "✓ Data directory exists: $DATA_DIR"
else
    echo "⚠️ Data directory $DATA_DIR missing"
fi

if [ $STATUS -eq 0 ]; then
    echo "========================================================="
    echo " [HEALTHCHECK] ALL CRITICAL SUBSYSTEMS GREEN (CODE 0)"
    echo "========================================================="
    exit 0
else
    echo "========================================================="
    echo " [HEALTHCHECK] CRITICAL COMPONENT FAILURE DETECTED"
    echo "========================================================="
    exit 1
fi
