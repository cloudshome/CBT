#!/usr/bin/env bash
# =============================================================================
# SKY / CTB — Production Crontab Setup for Ubuntu 24/7 Deployment
#
# Configures:
#   1. Daily Online Hot-Backup at 02:00 UTC (14-day retention pruning)
#   2. Weekly DB Maintenance & Optimization at 03:00 UTC every Sunday
#   3. Daily SQLite WAL Truncate Checkpoint at 04:00 UTC
#   4. Every-5-minute Sentinel Watchdog with Telegram failure alerting
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOG_DIR="${ROOT_DIR}/data/logs"

mkdir -p "${LOG_DIR}"

CRON_BACKUP="0 2 * * * ${SCRIPT_DIR}/backup_databases.sh >> ${LOG_DIR}/cron_backup.log 2>&1"
CRON_OPTIMIZE="0 3 * * 0 python3 ${SCRIPT_DIR}/db_maintenance.py >> ${LOG_DIR}/cron_db_maintenance.log 2>&1"
CRON_WAL="0 4 * * * python3 ${SCRIPT_DIR}/wal_checkpoint.py >> ${LOG_DIR}/cron_wal_checkpoint.log 2>&1"
CRON_WATCHDOG="*/5 * * * * ${SCRIPT_DIR}/healthcheck.sh >> ${LOG_DIR}/cron_healthcheck.log 2>&1"

# Prepare temporary crontab file
TMP_CRON=$(mktemp)

# Read existing crontab if present, filtering out previous CBT entries
if crontab -l > /dev/null 2>&1; then
    crontab -l | grep -v "CBT" | grep -v "backup_databases.sh" | grep -v "db_maintenance.py" | grep -v "wal_checkpoint.py" | grep -v "healthcheck.sh" > "${TMP_CRON}" || true
fi

# Append CBT production cron jobs
cat << EOF >> "${TMP_CRON}"
# === SKY / CTB 24/7 Autonomous Sentinel Crons ===
${CRON_BACKUP}
${CRON_OPTIMIZE}
${CRON_WAL}
${CRON_WATCHDOG}
# ===============================================
EOF

# Install new crontab
crontab "${TMP_CRON}"
rm -f "${TMP_CRON}"

echo "=================================================================="
echo "✓ Production Crontab for SKY / CTB installed successfully!"
echo "Current Crontab entries:"
echo "=================================================================="
crontab -l
