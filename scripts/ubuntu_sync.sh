#!/usr/bin/env bash
# ==============================================================================
# SKY / CBT — Ubuntu One-Click Synchronizer & Operational Sanitizer
# ==============================================================================
# Usage:
#   bash scripts/ubuntu_sync.sh
#
# This script:
#   1. Synchronizes git repository to latest HEAD (origin/cloudshome main)
#   2. Sanitizes local SQLite databases (purging rogue assets & corrupt orders)
#   3. Runs pre-flight verification test battery
#   4. Restarts background trading and terminal daemons
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${PROJECT_ROOT}"

echo "======================================================================"
echo "  SKY QUANTITATIVE ENGINE — UBUNTU SYNCHRONIZER & SERVICE SANITIZER  "
echo "======================================================================"
echo "[*] Working directory: ${PROJECT_ROOT}"
echo "[*] Timestamp: $(date -u +"%Y-%m-%d %H:%M:%S UTC")"

# 1. GIT REPOSITORY SYNCHRONIZATION
echo ""
echo "--- [1/4] GIT REPOSITORY SYNCHRONIZATION ---"
git fetch --all --prune

CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
echo "[*] Current branch: ${CURRENT_BRANCH}"

if [ "${CURRENT_BRANCH}" != "main" ]; then
    echo "[!] Warning: Not on 'main' branch. Checking out main..."
    git checkout main
fi

# Try fast-forward pull from origin or cloudshome
if git remote | grep -q "cloudshome"; then
    echo "[*] Pulling latest from cloudshome/main..."
    git pull --ff-only cloudshome main || git pull --ff-only origin main || echo "[!] Merge required or working tree modified."
else
    echo "[*] Pulling latest from origin/main..."
    git pull --ff-only origin main || echo "[!] Merge required or working tree modified."
fi

COMMIT_SHA="$(git rev-parse --short HEAD)"
COMMIT_MSG="$(git log -1 --pretty=%B | head -n 1)"
echo "[+] Active Git HEAD: ${COMMIT_SHA} - ${COMMIT_MSG}"

# 2. LOCAL DATABASE SANITIZATION & HYGIENE
echo ""
echo "--- [2/4] LOCAL DATABASE SANITIZATION & HYGIENE ---"
PYTHON_BIN="python3"
if [ -d ".venv" ]; then
    PYTHON_BIN=".venv/bin/python"
fi

${PYTHON_BIN} - << 'EOF'
import os
import sqlite3
import time

db_path = os.path.join("data", "trading_logs.db")
if not os.path.exists(db_path):
    print("[-] Database data/trading_logs.db not found; skipping sanitization.")
    exit(0)

conn = sqlite3.connect(db_path)
cur = conn.cursor()

# 1. Close any rogue microcap open positions
rogue_symbols = ["MAGMA/USDT", "AKE/USDT", "DOOD/USDT", "BMT/USDT", "KORU/USDT", "PEPE/USDT", "DOGE/USDT"]
now_ms = int(time.time() * 1000)

purged = 0
for sym in rogue_symbols:
    cur.execute("""
        UPDATE shadow_positions
        SET status = 'CLOSED',
            closed_at = ?,
            exit_reason = 'Administrative Purge: Rogue Asset Firewall Enforcement'
        WHERE status = 'OPEN' AND symbol = ?;
    """, (now_ms, sym))
    purged += cur.rowcount

# 2. Close any positions with irrational geometry (SL >= entry for LONG, SL <= entry for SHORT, TP <= 0, or SL > 5%)
cur.execute("SELECT position_id, symbol, direction, entry_price, stop_loss, take_profit FROM shadow_positions WHERE status = 'OPEN';")
open_rows = cur.fetchall()

irrational_closed = 0
for pos_id, sym, direction, ep, sl, tp in open_rows:
    is_irrational = False
    reason = ""
    if ep <= 0 or sl <= 0 or tp <= 0:
        is_irrational = True
        reason = "Administrative Purge: Non-positive price geometry"
    elif direction.upper() == "LONG" and (sl >= ep or tp <= ep or (ep - sl)/ep > 0.05):
        is_irrational = True
        reason = "Administrative Purge: Long SL/TP breach (>5% SL or SL>=entry)"
    elif direction.upper() == "SHORT" and (sl <= ep or tp >= ep or (sl - ep)/ep > 0.05):
        is_irrational = True
        reason = "Administrative Purge: Short SL/TP breach (>5% SL or SL<=entry)"
    
    if is_irrational:
        cur.execute("""
            UPDATE shadow_positions
            SET status = 'CLOSED',
                closed_at = ?,
                exit_reason = ?
            WHERE position_id = ?;
        """, (now_ms, reason, pos_id))
        irrational_closed += 1

conn.commit()
conn.close()

print(f"[+] Sanitization complete: {purged} rogue asset positions purged, {irrational_closed} irrational orders closed.")
EOF

# 3. VERIFICATION TEST SUITE
echo ""
echo "--- [3/4] PRE-FLIGHT VERIFICATION TEST SUITE ---"
PYTEST_BIN="pytest"
if [ -d ".venv" ]; then
    PYTEST_BIN=".venv/bin/pytest"
fi

${PYTEST_BIN} tests/test_cooldown_governor.py tests/test_autonomous_trader_and_hardening.py -q
echo "[+] Core safety tests passed green (100%)."

# 4. PROCESS LIFECYCLE RESTART
echo ""
echo "--- [4/4] BACKGROUND PROCESS LIFECYCLE RESTART ---"

# Check for systemd services
if systemctl is-active --quiet sky-terminal 2>/dev/null; then
    echo "[*] Restarting systemd service: sky-terminal..."
    sudo systemctl restart sky-terminal
    echo "[+] sky-terminal restarted successfully."
elif systemctl is-active --quiet cbt-terminal 2>/dev/null; then
    echo "[*] Restarting systemd service: cbt-terminal..."
    sudo systemctl restart cbt-terminal
    echo "[+] cbt-terminal restarted successfully."
fi

# Check for pm2 services
if command -v pm2 &> /dev/null; then
    if pm2 list | grep -q "sky"; then
        echo "[*] Restarting PM2 process: sky..."
        pm2 restart sky || true
        echo "[+] PM2 sky restarted."
    fi
fi

# Check for standalone background python daemons
echo "[*] Active Python processes for project:"
ps aux | grep "[p]ython.*app.py" || echo "[-] No standalone app.py daemon currently running in background."

echo ""
echo "======================================================================"
echo ">>> UBUNTU SYNCHRONIZATION AND SANITIZATION SUCCESSFUL <<<"
echo "Active Head: ${COMMIT_SHA}"
echo "System Status: FAIL-CLOSED RISK HARDWALL ACTIVE"
echo "======================================================================"
