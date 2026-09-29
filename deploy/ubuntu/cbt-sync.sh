#!/usr/bin/env bash
# =============================================================================
#  cbt-sync.sh  —  CBT GitHub Auto-Sync Script
#  Triggered by cbt-sync.timer (daily at midnight + 60s after boot) and by
#  `sudo cbt-deploy`.
#
#  Pulls origin/<branch>; on new commits it reinstalls changed deps, rebuilds,
#  and restarts the services.
#
#  NO PATHS ARE HARDCODED. The repo/app locations are read from /etc/cbt/cbt.env
#  (written by ubuntu-setup.sh), with fallbacks so this script also works when
#  run straight from a checkout on a dev machine.
#
#  Layout note: the CTB repo nests the app below the repo root
#  (<repo>/Users/azims/CBT), so git operations run in the REPO root while
#  builds run in the APP root. Changed-file patterns are written to match at
#  any depth so both layouts work.
#
#  Privileges: runs git/npm/npx/pip as the app user (CBT_USER) so artifacts
#  stay correctly owned, and only escalates for `systemctl restart`.
# =============================================================================
set -euo pipefail

LOG_PREFIX="[cbt-sync]"
log()  { echo "${LOG_PREFIX} $(date '+%Y-%m-%d %H:%M:%S') $*"; }
die()  { echo "${LOG_PREFIX} FATAL: $*" >&2; exit 1; }

# --------------------------------------------------------------------------- #
# 1. Discover paths
# --------------------------------------------------------------------------- #
CBT_CONFIG="${CBT_CONFIG:-/etc/cbt/cbt.env}"
# shellcheck disable=SC1090
[ -f "$CBT_CONFIG" ] && . "$CBT_CONFIG"

CBT_USER="${CBT_USER:-}"
CBT_REPO_DIR="${CBT_REPO_DIR:-}"
CBT_PROJECT_DIR="${CBT_PROJECT_DIR:-}"
CBT_GIT_BRANCH="${CBT_GIT_BRANCH:-main}"

# Fallback A: script is being run from inside a checkout (dev machine).
if [ -z "$CBT_PROJECT_DIR" ] || [ ! -d "$CBT_PROJECT_DIR" ]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    if [ -f "$SCRIPT_DIR/../../.env.example" ] && [ -f "$SCRIPT_DIR/../../package.json" ]; then
        CBT_PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
        log "No $CBT_CONFIG — using checkout at $CBT_PROJECT_DIR"
    else
        die "Cannot locate the CBT app root and $CBT_CONFIG is missing.
   Fix: sudo bash <app-root>/deploy/ubuntu/ubuntu-setup.sh"
    fi
fi

# Fallback B: app owner, for privilege dropping.
if [ -z "$CBT_USER" ]; then
    CBT_USER="$(stat -c '%U' "$CBT_PROJECT_DIR" 2>/dev/null || echo "")"
    [ -n "$CBT_USER" ] || die "Cannot determine the owner of $CBT_PROJECT_DIR"
fi

# Fallback C: repo root (where .git lives) from the app root.
if [ -z "$CBT_REPO_DIR" ] || [ ! -d "$CBT_REPO_DIR/.git" ]; then
    CBT_REPO_DIR="$(git -C "$CBT_PROJECT_DIR" rev-parse --show-toplevel 2>/dev/null || true)"
    if [ -z "$CBT_REPO_DIR" ]; then
        [ -d "$CBT_PROJECT_DIR/.git" ] && CBT_REPO_DIR="$CBT_PROJECT_DIR" \
            || die "$CBT_PROJECT_DIR is not inside a git checkout — nothing to sync."
    fi
fi

# Shallowest dir under the repo holding .env.example + package.json.
detect_project_dir() {
    local repo="$1" entry dir
    if [ -f "$repo/.env.example" ] && [ -f "$repo/package.json" ]; then
        printf '%s\n' "$repo"; return 0
    fi
    while read -r entry; do
        [ -n "$entry" ] || continue
        dir="${entry#* }"
        if [ -f "$dir/package.json" ]; then printf '%s\n' "$dir"; return 0; fi
    done < <(find "$repo" -mindepth 2 -maxdepth 5 -type f -name '.env.example' \
                 -not -path '*/.git/*' -not -path '*/node_modules/*' -not -path '*/.venv/*' \
                 -printf '%d %h\n' 2>/dev/null | sort -n)
    return 1
}

validate_project_dir() {
    if [ ! -f "$CBT_PROJECT_DIR/package.json" ] || [ ! -f "$CBT_PROJECT_DIR/.env.example" ]; then
        log "App root $CBT_PROJECT_DIR no longer looks valid — re-detecting ..."
        local found
        if found="$(detect_project_dir "$CBT_REPO_DIR")"; then
            CBT_PROJECT_DIR="$found"
            log "App root moved to $CBT_PROJECT_DIR (update $CBT_CONFIG to silence this)."
        else
            die "Cannot locate the app root under $CBT_REPO_DIR — aborting before any restart."
        fi
    fi
}
validate_project_dir

# --------------------------------------------------------------------------- #
# 2. Privilege helpers
# --------------------------------------------------------------------------- #
IS_ROOT=0; [ "$(id -u)" -eq 0 ] && IS_ROOT=1

# run_in <dir> <command...> — as the app user, never prompting for credentials.
run_in() {
    local dir="$1"; shift
    if [ "$IS_ROOT" -eq 1 ] && [ "$(id -un)" != "$CBT_USER" ]; then
        sudo -u "$CBT_USER" -H env GIT_TERMINAL_PROMPT=0 bash -c "cd '$dir' && $*"
    else
        env GIT_TERMINAL_PROMPT=0 bash -c "cd '$dir' && $*"
    fi
}

restart_services() {
    if [ "$IS_ROOT" -eq 1 ]; then
        systemctl restart cbt-fastapi cbt-express cbt-frontend
    elif command -v sudo &>/dev/null; then
        sudo systemctl restart cbt-fastapi cbt-express cbt-frontend
    else
        die "Not root and no sudo — cannot restart services. Run: sudo cbt-deploy"
    fi
}

log "Repo: $CBT_REPO_DIR | App: $CBT_PROJECT_DIR | User: $CBT_USER | Branch: $CBT_GIT_BRANCH"

# --------------------------------------------------------------------------- #
# 3. Fetch + compare
# --------------------------------------------------------------------------- #
if ! run_in "$CBT_REPO_DIR" "git fetch origin '$CBT_GIT_BRANCH' --quiet"; then
    die "git fetch failed. If the repo is private, credentials must be stored for
   user '$CBT_USER' (git config credential.helper store + one manual fetch), or
   the remote must use SSH. See deploy/ubuntu/README.md."
fi

LOCAL="$(run_in "$CBT_REPO_DIR" "git rev-parse HEAD")"
REMOTE="$(run_in "$CBT_REPO_DIR" "git rev-parse 'origin/$CBT_GIT_BRANCH'")"

if [ "$LOCAL" = "$REMOTE" ]; then
    log "Already up to date (${LOCAL:0:7}). Nothing to do."
    exit 0
fi

log "New commits detected: ${LOCAL:0:7} -> ${REMOTE:0:7}"
log "Pulling origin/$CBT_GIT_BRANCH ..."
run_in "$CBT_REPO_DIR" "git pull origin '$CBT_GIT_BRANCH' --ff-only"

# The pull may have moved/renamed the nested app dir — re-check before building.
validate_project_dir

CHANGED="$(run_in "$CBT_REPO_DIR" "git diff --name-only '$LOCAL' '$REMOTE'")"
# Paths are relative to the REPO root, so they are prefixed with the nesting
# (e.g. Users/azims/CBT/frontend/...). Match at any depth.
changed() { printf '%s\n' "$CHANGED" | grep -qE "$1"; }

# --------------------------------------------------------------------------- #
# 4. Reinstall changed dependencies
# --------------------------------------------------------------------------- #
if changed '(^|/)requirements[^/]*\.txt$'; then
    log "requirements.txt changed — reinstalling Python deps ..."
    run_in "$CBT_PROJECT_DIR" ".venv/bin/pip install -r requirements.txt --quiet"
fi

if changed '(^|/)package(-lock)?\.json$'; then
    log "package.json / lockfile changed — reinstalling Node deps ..."
    run_in "$CBT_PROJECT_DIR" "npm ci --silent"
    if changed '(^|/)frontend/package(-lock)?\.json$'; then
        run_in "$CBT_PROJECT_DIR" "npm --prefix frontend ci --silent"
    fi
fi

# --------------------------------------------------------------------------- #
# 5. Rebuild
# --------------------------------------------------------------------------- #
# Always rebuild the Express TypeScript bundle. tsc takes only a few seconds and
# an unconditional rebuild removes any chance of serving a stale dist/ (e.g. a
# dependency bump that changes types without touching src/).
log "Rebuilding Express TypeScript ..."
run_in "$CBT_PROJECT_DIR" "npm run build:backend --silent"

if changed '(^|/)frontend/'; then
    log "Frontend files changed — rebuilding Vite ..."
    run_in "$CBT_PROJECT_DIR" "npm run frontend:build --silent"
fi

if changed '(^|/)prisma/'; then
    log "Prisma schema changed — updating database schema ..."
    run_in "$CBT_PROJECT_DIR" "npx prisma generate && npx prisma db push --skip-generate"
fi

# --------------------------------------------------------------------------- #
# 6. Restart services
# --------------------------------------------------------------------------- #
log "Restarting services ..."
restart_services

log "Sync complete! Now at $(run_in "$CBT_REPO_DIR" "git rev-parse --short HEAD")"
