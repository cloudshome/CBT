#!/usr/bin/env bash
#
# sync_local.sh — Keep a local clone of cloudshome/CTB aligned with GitHub.
#
# Designed to be safe to run on a schedule (systemd timer / cron) and to recover
# after a reboot or power outage. Strategy:
#   * self-locates the repo root, so it works from ANY sub-directory
#   * fast-forward only (never merges) -> surfaces conflicts instead of hiding them
#   * updates BOTH the configured sync branch and `main`
#
# Usage:
#   bash sync_local.sh                 # uses defaults (see CTB_* below)
#   bash sync_local.sh main            # sync a specific branch only (still updates main)
#
# Environment overrides:
#   CTB_REMOTE   url/name of the remote to sync (default: origin)
#   CTB_BRANCH   branch to keep checked out (default: main)
#   CTB_QUIET    if set, suppress the alignment report
#
# Exit codes: 0 = in sync, 1 = sync problem (conflict / fetch failure).
set -uo pipefail

CTB_REMOTE="${CTB_REMOTE:-origin}"
CTB_BRANCH="${CTB_BRANCH:-main}"
BRANCH="${1:-$CTB_BRANCH}"

# --- Locate the repo root regardless of cwd -------------------------------
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [ -z "$ROOT" ]; then
  echo "[ctb-sync] ERROR: not inside a git work tree. Run from inside the clone." >&2
  exit 1
fi
cd "$ROOT"

# Allow this repo to be owned by another user / run as root (systemd), so git
# does not reject it as an unsafe directory. Use --system (HOME-independent)
# so it works even when run by systemd as a different user.
git config --system --add safe.directory "$ROOT" 2>/dev/null || true
git config --global --add safe.directory "$ROOT" 2>/dev/null || true

log() { printf '[ctb-sync %s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }

log "repo=$ROOT remote=$CTB_REMOTE branch=$BRANCH"

# --- Make git fetch see EVERY branch (so feature/arena refs exist) --------
git config remote."$CTB_REMOTE".fetch '+refs/heads/*:refs/remotes/'"$CTB_REMOTE"'/*'

# --- Fetch + prune stale remote-tracking refs -----------------------------
if ! git fetch --prune "$CTB_REMOTE"; then
  log "ERROR: git fetch failed (network / auth?)."
  exit 1
fi

# --- Update the requested branch (fast-forward only) -----------------------
if git show-ref --verify --quiet "refs/remotes/$CTB_REMOTE/$BRANCH"; then
  git switch "$BRANCH" 2>/dev/null || git checkout "$BRANCH" 2>/dev/null || true
  if ! git merge --ff-only "refs/remotes/$CTB_REMOTE/$BRANCH"; then
    log "WARN: could not fast-forward '$BRANCH' (diverged or uncommitted changes). Leave as-is."
  else
    log "updated '$BRANCH' -> $(git rev-parse --short HEAD)"
  fi
else
  log "WARN: remote branch '$CTB_REMOTE/$BRANCH' not found; skipping switch."
fi

# --- Also bring `main` up to date -----------------------------------------
if git show-ref --verify --quiet "refs/remotes/$CTB_REMOTE/main"; then
  git switch main 2>/dev/null || git checkout main 2>/dev/null || true
  if ! git merge --ff-only "refs/remotes/$CTB_REMOTE/main"; then
    log "WARN: could not fast-forward 'main' (diverged or uncommitted changes)."
  else
    log "updated 'main' -> $(git rev-parse --short HEAD)"
  fi
fi

# --- Return to the requested branch ---------------------------------------
git switch "$BRANCH" 2>/dev/null || git checkout "$BRANCH" 2>/dev/null || true

# --- Alignment report -----------------------------------------------------
if [ -z "${CTB_QUIET:-}" ] && git show-ref --verify --quiet "refs/remotes/$CTB_REMOTE/$BRANCH"; then
  LR="$(git rev-list --left-right --count "refs/remotes/$CTB_REMOTE/$BRANCH"...HEAD 2>/dev/null || echo "0 0")"
  AHEAD="$(echo "$LR" | awk '{print $1}')"
  BEHIND="$(echo "$LR" | awk '{print $2}')"
  log "branch=$BRANCH ahead=$AHEAD behind=$BEHIND"
  if [ "$AHEAD" -eq 0 ] && [ "$BEHIND" -eq 0 ]; then
    log "OK: local '$BRANCH' is identical to '$CTB_REMOTE/$BRANCH'"
  else
    log "NOTE: local '$BRANCH' differs from '$CTB_REMOTE/$BRANCH' (ahead $AHEAD, behind $BEHIND)"
  fi
fi

log "done."
