#!/usr/bin/env bash
#
# sync_local.sh — Keep a local clone of cloudshome/CTB aligned with GitHub.
#
# Safe, fast-forward only. Refuses to pull with a merge, so a dirty/diverged
# branch is surfaced instead of silently resolving. See docs/LOCAL_SYNC.md.
#
# Usage:  ./scripts/sync_local.sh [branch]
#         Default branch: arena/01a087d1-ctb (edit below or pass one).
set -euo pipefail

BRANCH="${1:-arena/01a087d1-ctb}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "==> Repo:     $(basename "$(git rev-parse --show-toplevel)")"
echo "==> Branch:   $BRANCH"
echo "==> Current:  $(git branch --show-current)"

# 1. Mirror every branch so branch-specific remote-tracking refs exist.
echo "==> Setting fetch refspec to mirror all branches..."
git config remote.origin.fetch '+refs/heads/*:refs/remotes/origin/*'

# 2. Fetch + prune stale remote-tracking branches.
echo "==> Fetching from origin..."
git fetch --prune origin

# 3. Fast-forward the requested branch against its upstream.
echo "==> Updating $BRANCH (fast-forward only)..."
git checkout "$BRANCH" 2>/dev/null || git switch "$BRANCH"
git pull --ff-only origin "$BRANCH"

# 4. Also refresh local main (fast-forward only).
echo "==> Updating main (fast-forward only)..."
git checkout main 2>/dev/null || git switch main
git pull --ff-only origin main

# 5. Return to the working branch.
echo "==> Returning to $BRANCH..."
git checkout "$BRANCH" 2>/dev/null || git switch "$BRANCH"

# 6. Report alignment.
echo
echo "==> Alignment report"
git status -sb
AHEAD="$(git rev-list --left-right --count "origin/$BRANCH"...HEAD | awk '{print $1}')"
BEHIND="$(git rev-list --left-right --count "origin/$BRANCH"...HEAD | awk '{print $2}')"
echo "    Ahead: $AHEAD   Behind: $BEHIND"
if [ "$AHEAD" -eq 0 ] && [ "$BEHIND" -eq 0 ]; then
  echo "    OK: local $BRANCH is identical to origin/$BRANCH"
else
  echo "    NOTE: local $BRANCH differs from origin/$BRANCH (ahead $AHEAD, behind $BEHIND)"
fi
