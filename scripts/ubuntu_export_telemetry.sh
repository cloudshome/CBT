#!/usr/bin/env bash
# ==============================================================================
# scripts/ubuntu_export_telemetry.sh
# ==============================================================================
# Automated Daily Telemetry & Reconciliation Ledger Export for Ubuntu 24.
# Designed to run via daily cron to bridge headless servers to the CBT audit gate.
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${PROJECT_ROOT}"

TIMESTAMP=$(date -u +"%Y-%m-%d_%H%M%SZ")
TELEMETRY_DIR="${PROJECT_ROOT}/data/telemetry_snapshots"
mkdir -p "${TELEMETRY_DIR}"

SNAPSHOT_FILE="${TELEMETRY_DIR}/snapshot_${TIMESTAMP}.json"

echo "[*] Generating CBT telemetry snapshot at ${TIMESTAMP}..."

if [ -f ".venv/bin/python" ]; then
    PYTHON_BIN=".venv/bin/python"
else
    PYTHON_BIN="python3"
fi

${PYTHON_BIN} - <<EOF > "${SNAPSHOT_FILE}"
import json
import sqlite3
import os
from datetime import datetime, timezone

data = {
    "node": os.uname().nodename if hasattr(os, "uname") else "ubuntu-node",
    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    "orders": [],
    "reconciliation_fills": [],
    "daily_metrics": {}
}

trading_db = "data/trading_logs.db"
if os.path.exists(trading_db):
    try:
        conn = sqlite3.connect(trading_db)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        
        # Check tables
        cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [r[0] for r in cur.fetchall()]
        
        if "orders" in tables:
            cur.execute("SELECT * FROM orders ORDER BY created_at DESC LIMIT 500;")
            data["orders"] = [dict(r) for r in cur.fetchall()]
            
        if "reconciliation_fills" in tables:
            cur.execute("SELECT * FROM reconciliation_fills ORDER BY timestamp_ms DESC LIMIT 500;")
            data["reconciliation_fills"] = [dict(r) for r in cur.fetchall()]
            
        conn.close()
    except Exception as e:
        data["trading_db_error"] = str(e)

print(json.dumps(data, indent=2))
EOF

echo "[*] Snapshot saved to: ${SNAPSHOT_FILE}"

# Commit and push to telemetry-sync branch if git is configured
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
    echo "[*] Active branch: ${CURRENT_BRANCH}"
    
    # Check if remote exists
    if git remote | grep -q "origin"; then
        echo "[*] Committing snapshot to local git..."
        git add "${SNAPSHOT_FILE}"
        git commit -m "telemetry(ubuntu): automated snapshot ${TIMESTAMP}" || true
        echo "[*] Attempting push to origin..."
        git push origin "${CURRENT_BRANCH}" || echo "[WARNING] Git push failed. Snapshot preserved locally."
    fi
fi

echo "[PASS] Telemetry export complete."
