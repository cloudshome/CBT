#!/usr/bin/env bash
# =============================================================================
#  cbt-sync.sh  —  CBT GitHub Auto-Sync Script
#  Runs every 5 minutes via systemd timer.
#  Pulls from origin/main; on new commits rebuilds and restarts services.
# =============================================================================
set -euo pipefail

REPO_DIR="/home/cbt/CBT"
LOG_PREFIX="[cbt-sync]"

log() { echo "${LOG_PREFIX} $*"; }

cd "$REPO_DIR"

# --- Fetch latest without merging ---
git fetch origin main --quiet

LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)

if [ "$LOCAL" = "$REMOTE" ]; then
    log "Already up to date (${LOCAL:0:7}). Nothing to do."
    exit 0
fi

log "New commits detected: ${LOCAL:0:7} -> ${REMOTE:0:7}"
log "Pulling origin/main ..."
git pull origin main --ff-only

# --- Python: install any new deps ---
if git diff --name-only "$LOCAL" "$REMOTE" | grep -q "requirements"; then
    log "requirements.txt changed — reinstalling Python deps ..."
    .venv/bin/pip install -r requirements.txt --quiet
fi

# --- Node: install any new deps and rebuild Express backend ---
if git diff --name-only "$LOCAL" "$REMOTE" | grep -qE "package.*\.json|package-lock"; then
    log "package.json changed — reinstalling Node deps ..."
    npm ci --silent
fi

# --- Always rebuild Express TypeScript (fast, <5s) ---
log "Rebuilding Express TypeScript ..."
npm run build:backend --silent

# --- Rebuild frontend only if frontend files changed ---
if git diff --name-only "$LOCAL" "$REMOTE" | grep -q "^frontend/"; then
    log "Frontend files changed — rebuilding Vite ..."
    npm run frontend:build --silent
fi

# --- Apply Prisma schema ---
if git diff --name-only "$LOCAL" "$REMOTE" | grep -q "prisma/"; then
    log "Prisma schema changed — updating database schema ..."
    npx prisma generate && npx prisma db push --skip-generate
fi

# --- Restart all 3 services ---
log "Restarting services ..."
systemctl restart cbt-fastapi cbt-express cbt-frontend

log "Sync complete! Now at $(git rev-parse --short HEAD)"
