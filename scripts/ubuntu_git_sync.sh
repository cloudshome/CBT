#!/usr/bin/env bash
# =============================================================================
# SKY / CBT — Ubuntu Scheduled Git Sync & Service Lifecycle Script
# Scheduled via crontab for automatic synchronization with Windows PC commits:
# Times: 12:01 PM, 12:30 PM, 1:30 PM, 2:30 PM, 3:30 PM, 4:30 PM, 11:55 PM
# =============================================================================

set -Eeuo pipefail

REPO_DIR="/home/cloudslover/CBT"
LOG_DIR="${REPO_DIR}/data/logs"
LOG_FILE="${LOG_DIR}/git_sync.log"

export HOME="/home/cloudslover"
export PATH="/home/cloudslover/CBT/.venv/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
export GIT_TERMINAL_PROMPT=0

# Resolve SSH authentication socket if running non-interactively (e.g. from cron)
if [ -z "${SSH_AUTH_SOCK:-}" ]; then
    CURRENT_UID="$(id -u)"
    for candidate_sock in "/run/user/${CURRENT_UID}/gcr/ssh" "/run/user/${CURRENT_UID}/keyring/ssh" "/run/user/1000/gcr/ssh"; do
        if [ -S "$candidate_sock" ]; then
            export SSH_AUTH_SOCK="$candidate_sock"
            break
        fi
    done
fi

mkdir -p "$LOG_DIR"

log() {
    echo "[SYNC $(date '+%Y-%m-%d %H:%M:%S %Z')] $*"
}

cd "$REPO_DIR"

log "Starting scheduled git sync check on $(hostname)..."

# 1. Fetch remote main branch
if ! git fetch origin main --quiet; then
    log "ERROR: git fetch origin main failed. Check network or SSH configuration."
    exit 1
fi

LOCAL_HASH=$(git rev-parse HEAD)
REMOTE_HASH=$(git rev-parse origin/main)

if [ "$LOCAL_HASH" = "$REMOTE_HASH" ]; then
    log "Repository already up to date at ${LOCAL_HASH:0:7}. No updates needed."
    exit 0
fi

log "Incoming changes detected: ${LOCAL_HASH:0:7} -> ${REMOTE_HASH:0:7}"

# 2. Inspect changed files between local and remote
CHANGED_FILES=$(git diff --name-only "$LOCAL_HASH" "$REMOTE_HASH")

# 3. Handle uncommitted local modifications (e.g. crawler cache) safely via stash
STASHED=0
if [ -n "$(git status --porcelain -uno)" ]; then
    log "Local tracked changes detected. Stashing before fast-forward..."
    git stash push --quiet -m "cbt-auto-sync-pre-pull-$(date +%s)"
    STASHED=1
fi

# 4. Fast-forward pull
if ! git pull --ff-only origin main; then
    log "ERROR: git pull --ff-only failed. Local branch may have diverged."
    if [ "$STASHED" -eq 1 ]; then
        git stash pop --quiet || true
    fi
    exit 1
fi

# Reapply local stash if created
if [ "$STASHED" -eq 1 ]; then
    log "Reapplying stashed local modifications..."
    git stash pop --quiet || log "WARNING: Stash pop reported conflicts; stashed changes preserved."
fi

NEW_HASH=$(git rev-parse --short HEAD)
log "Successfully pulled latest code (now at ${NEW_HASH})."

# 5. Dependency checks
if echo "$CHANGED_FILES" | grep -qE "(^|/)requirements.*\.txt$"; then
    log "Python dependencies changed. Updating virtualenv..."
    "${REPO_DIR}/.venv/bin/pip" install -r "${REPO_DIR}/requirements.txt" --quiet || log "WARNING: pip install encountered warnings."
fi

if echo "$CHANGED_FILES" | grep -qE "(^|/)package(-lock)?\.json$"; then
    log "Node dependencies changed. Updating packages..."
    npm install --silent || log "WARNING: npm install encountered warnings."
fi

# 6. Frontend rebuild if frontend files changed
RESTART_FRONTEND=0
if echo "$CHANGED_FILES" | grep -qE "(^|/)frontend/"; then
    log "Frontend source changed. Rebuilding Vite production bundle..."
    (cd "${REPO_DIR}/frontend" && npm run build --silent) || log "WARNING: Frontend build encountered warnings."
    RESTART_FRONTEND=1
fi

# 7. Service reload / restart
RESTART_BACKEND=0
if echo "$CHANGED_FILES" | grep -qE "(^|/)(app\.py|core/|web/|src/|\.env)"; then
    RESTART_BACKEND=1
fi

if [ "$RESTART_BACKEND" -eq 1 ] || [ "$RESTART_FRONTEND" -eq 1 ]; then
    log "Restarting affected systemd services..."
    if [ "$RESTART_BACKEND" -eq 1 ]; then
        systemctl restart cbt-fastapi.service || log "WARNING: Failed to restart cbt-fastapi.service"
        systemctl restart cbt-express.service || log "WARNING: Failed to restart cbt-express.service"
        log "cbt-fastapi and cbt-express services restarted."
    fi
    if [ "$RESTART_FRONTEND" -eq 1 ]; then
        systemctl restart cbt-frontend.service || log "WARNING: Failed to restart cbt-frontend.service"
        log "cbt-frontend service restarted."
    fi
else
    log "No service restarts required for this commit."
fi

log "Scheduled sync completed successfully at ${NEW_HASH}."
