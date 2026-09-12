#!/usr/bin/env bash
# =============================================================================
# SKY / CTB — Production Database Backup Cron Job Wrapper
#
# Recommended crontab entry (daily at 02:00 UTC):
# 0 2 * * * /opt/cbt/deploy/backup_databases.sh >> /var/log/cbt_backup.log 2>&1
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

DATA_DIR="${DATA_DIR:-${ROOT_DIR}/data}"
BACKUP_DIR="${BACKUP_DIR:-${DATA_DIR}/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"

echo "=================================================================="
echo "Starting SKY / CTB Online Database Backup at $(date -u)"
echo "Data Directory: ${DATA_DIR}"
echo "Backup Directory: ${BACKUP_DIR}"
echo "Retention Days: ${RETENTION_DAYS}"
echo "=================================================================="

python3 "${SCRIPT_DIR}/backup_databases.py" \
    --data-dir "${DATA_DIR}" \
    --backup-dir "${BACKUP_DIR}" \
    --retention-days "${RETENTION_DAYS}"

echo "Backup finished successfully at $(date -u)"
