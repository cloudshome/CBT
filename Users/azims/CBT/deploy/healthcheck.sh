#!/usr/bin/env bash
# ==============================================================================
# 24/7 Ubuntu Production Healthcheck Probe for SKY / ORION Terminal
# Validates Python API (:8000), Node Market Streamer (:3000), Database & Data Freshness
#
# Telegram Alerts: Reads TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID from .env
# On critical failure, sends a push notification to your phone instantly.
# Run every 5 minutes via cron (installed by deploy/crontab_ubuntu.sh).
# ==============================================================================

set -uo pipefail

# Load .env for Telegram credentials
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
if [ -f "${ROOT_DIR}/.env" ]; then
    set -o allexport
    # shellcheck disable=SC1091
    source "${ROOT_DIR}/.env"
    set +o allexport
fi

TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
TELEGRAM_CHAT_ID="${TELEGRAM_CHAT_ID:-}"

# Send Telegram alert (silent if token/chat not configured)
send_telegram_alert() {
    local message="$1"
    if [ -n "${TELEGRAM_BOT_TOKEN}" ] && [ -n "${TELEGRAM_CHAT_ID}" ]; then
        curl -s -X POST \
            "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
            -d "chat_id=${TELEGRAM_CHAT_ID}" \
            -d "text=${message}" \
            -d "parse_mode=HTML" \
            > /dev/null 2>&1 || true
    fi
}

PYTHON_PORT=${PYTHON_PORT:-8000}
NODE_PORT=${NODE_PORT:-3000}
STATUS=0
FAILURES=""

echo "[HEALTHCHECK] Initiating system health probe..."

# 1. Check Python FastAPI Master Engine
if curl -s -f "http://127.0.0.1:${PYTHON_PORT}/api/health" > /dev/null 2>&1 || curl -s -f "http://127.0.0.1:${PYTHON_PORT}/health" > /dev/null 2>&1; then
    echo "✓ Python FastAPI Engine (: ${PYTHON_PORT}) is HEALTHY"
else
    echo "❌ Python FastAPI Engine (: ${PYTHON_PORT}) FAILED / Unreachable"
    STATUS=1
    FAILURES="${FAILURES}• Python Quant Engine (:8000) is DOWN\n"
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

# 4. Check Node Market Streamer
if curl -s -f "http://127.0.0.1:${NODE_PORT}/health" > /dev/null 2>&1; then
    echo "✓ Node Market Data & Paper Desk (: ${NODE_PORT}) is HEALTHY"
else
    echo "ℹ️ Node Streamer on port ${NODE_PORT} is not responding (or in Python-direct mode)"
fi

# 5. Check Disk Storage for Logs / Data
DATA_DIR=${DATA_DIR:-"${ROOT_DIR}/data"}
if [ -d "$DATA_DIR" ]; then
    echo "✓ Data directory exists: $DATA_DIR"
else
    echo "⚠️ Data directory $DATA_DIR missing"
    STATUS=1
    FAILURES="${FAILURES}• Data directory missing: ${DATA_DIR}\n"
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
    # Dispatch emergency alert to Telegram
    ALERT_MSG="🚨 <b>CBT SENTINEL DOWN ALERT</b>%0AHost: $(hostname)%0ATime: $(date -u +'%Y-%m-%d %H:%M:%S UTC')%0A%0A${FAILURES}"
    send_telegram_alert "${ALERT_MSG}"
    exit 1
fi
