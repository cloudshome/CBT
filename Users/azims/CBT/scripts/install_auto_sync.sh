#!/usr/bin/env bash
#
# install_auto_sync.sh — ONE-COMMAND setup: keep a local CTB clone in sync
# with GitHub, automatically, forever.
#
# Sets up:
#   * clones (or updates) the repo at --target
#   * writes a self-contained sync script ctb-sync.sh into the repo root
#     (so it works even if the default GitHub branch is ahead of the file)
#   * a systemd SERVICE (ctb-sync.service) that runs that script
#   * a systemd TIMER   (ctb-sync.timer)   that runs it every --interval,
#     enabled at boot, with Persistent=true so a run missed during a reboot
#     / power outage is caught up automatically
#   * falls back to a cron job if systemd is unavailable
#
# THE ONE COMMAND YOU RUN (as root / sudo):
#   sudo bash <(curl -fsSL https://raw.githubusercontent.com/cloudshome/CTB/arena/01a087d1-ctb/Users/azims/CBT/scripts/install_auto_sync.sh) \
#     --repo https://github.com/cloudshome/CTB.git \
#     --target /home/st/SKY/CTB \
#     --interval 1h
set -uo pipefail

# --- defaults -------------------------------------------------------------
REPO="https://github.com/cloudshome/CTB.git"
TARGET=""
INTERVAL="1h"
BRANCH="main"
# Optional command to run after a real code pull when a change is detected.
# Empty = auto-detect and restart the docker-compose stack. Set to override,
# e.g.  --restart-cmd 'systemctl --user restart ctb-backend ctb-node ctb-frontend'
RESTART_CMD=""
QUIET=0

usage() { sed -n 's/^#   //p' "$0"; exit 0; }

while [ $# -gt 0 ]; do
  case "$1" in
    --repo)        REPO="$2"; shift 2 ;;
    --target)      TARGET="$2"; shift 2 ;;
    --interval)    INTERVAL="$2"; shift 2 ;;
    --branch)      BRANCH="$2"; shift 2 ;;
    --restart-cmd) RESTART_CMD="$2"; shift 2 ;;
    --quiet)       QUIET=1; shift ;;
    -h|--help)     usage ;;
    *) echo "Unknown option: $1" >&2; usage ;;
  esac
done

if [ -z "$TARGET" ]; then
  echo "ERROR: --target is required (the directory to clone into)." >&2
  usage
fi

echo "==> Repo:      $REPO"
echo "==> Target:    $TARGET"
echo "==> Interval:  $INTERVAL"
echo "==> Branch:    $BRANCH"
echo

# --- 1. Obtain the repo ---------------------------------------------------
if [ -d "$TARGET/.git" ]; then
  echo "==> Repo already present at $TARGET — using it."
  cd "$TARGET"
else
  echo "==> Cloning $REPO into $TARGET ..."
  mkdir -p "$TARGET"
  git clone "$REPO" "$TARGET"
  cd "$TARGET"
fi
# Trust the clone machine-wide so systemd (as root) can operate on it.
git config --system --add safe.directory "$TARGET" 2>/dev/null || true
git config --global --add safe.directory "$TARGET" 2>/dev/null || true

# --- 2. Write a self-contained sync script at the repo root ---------------
# This is deliberately written out by the installer so the auto-sync does NOT
# depend on the file already existing in the cloned default branch.
SYNC_SCRIPT="$TARGET/ctb-sync.sh"
CLEAN_LOG="$TARGET/ctb-sync.log"

cat > "$SYNC_SCRIPT" <<'SYNCEOF'
#!/usr/bin/env bash
# Self-contained CTB GitHub sync. Written by install_auto_sync.sh.
set -uo pipefail
export GIT_TERMINAL_PROMPT=0   # never hang asking for credentials in a daemon
REMOTE="${CTB_REMOTE:-origin}"
BRANCH="${CTB_BRANCH:-main}"
ROOT="$(cd "$(dirname "$0")" && pwd)"
# Trust the repo machine-wide (HOME-independent, works under systemd as any user)
git config --system --add safe.directory "$ROOT" 2>/dev/null || true
git config --global --add safe.directory "$ROOT" 2>/dev/null || true
log() { printf '[ctb-sync %s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }
cd "$ROOT" || { log "ERROR: no such dir $ROOT"; exit 1; }
log "repo=$ROOT remote=$REMOTE branch=$BRANCH"
git config remote."$REMOTE".fetch '+refs/heads/*:refs/remotes/'"$REMOTE"'/*'
if ! git fetch --prune "$REMOTE"; then
  log "ERROR: fetch failed"; exit 1
fi

# --- Fast-forward the requested branch + main; track whether we MOVED ------
CHANGED=0
for b in "$BRANCH" main; do
  if git show-ref --verify --quiet "refs/remotes/$REMOTE/$b"; then
    git switch "$b" 2>/dev/null || git checkout "$b" 2>/dev/null || true
    BEFORE="$(git rev-parse HEAD 2>/dev/null)"
    if git merge --ff-only "refs/remotes/$REMOTE/$b" 2>/dev/null; then
      AFTER="$(git rev-parse HEAD 2>/dev/null)"
      if [ "$BEFORE" != "$AFTER" ]; then
        log "updated '$b' -> $(git rev-parse --short HEAD)"
        CHANGED=1
      else
        log "'$b' already up to date"
      fi
    else
      log "WARN: could not fast-forward '$b' (diverged/uncommitted). Left as-is."
    fi
  fi
done
git switch "$BRANCH" 2>/dev/null || git checkout "$BRANCH" 2>/dev/null || true

# --- Restart the app stack ONLY if the pull moved code ---------------------
restart_stack() {
  COMPOSE_DIR="$ROOT"
  if [ -f "$ROOT/Users/azims/CBT/docker-compose.yml" ]; then
    COMPOSE_DIR="$ROOT/Users/azims/CBT"
  elif [ -f "$ROOT/docker-compose.yml" ]; then
    COMPOSE_DIR="$ROOT"
  fi
  if command -v docker >/dev/null 2>&1 && [ -f "$COMPOSE_DIR/docker-compose.yml" ]; then
    log "restarting compose stack in $COMPOSE_DIR (code changed)"
    ( cd "$COMPOSE_DIR" && docker compose up -d --remove-orphans --build ) \
      || log "WARN: stack restart failed (exit $?)"
  else
    log "WARN: docker compose stack not found under $ROOT; nothing to restart."
  fi
}

if [ "$CHANGED" -eq 1 ]; then
  if [ -n "${CTB_RESTART_CMD:-}" ]; then
    log "code changed -> running custom restart: $CTB_RESTART_CMD"
    eval "$CTB_RESTART_CMD" || log "WARN: custom restart failed (exit $?)"
  else
    restart_stack
  fi
else
  log "no code change; restart not needed"
fi
log "done."
SYNCEOF

[ "$QUIET" -eq 1 ] || sed -i 's/^set -uo pipefail$/set -uo pipefail\nCTB_REMOTE="${CTB_REMOTE:-origin}"\nCTB_BRANCH="${CTB_BRANCH:-main}"/' "$SYNC_SCRIPT" 2>/dev/null || true
chmod +x "$SYNC_SCRIPT"
echo "==> Wrote self-contained sync script: $SYNC_SCRIPT"

# --- Run as the repo owner, NOT root. Root has no GitHub credentials in
# --- non-interactive systemd runs, so git fetch would prompt and fail.
# --- Determine the owner/group of the target dir and use it for the unit.
OWNER="$(stat -c '%U' "$TARGET" 2>/dev/null || echo root)"
GROUP="$(stat -c '%G' "$TARGET" 2>/dev/null || echo root)"
echo "==> Running the sync as user '$OWNER' (owner of the clone)."

# --- Persistent git credentials for a PRIVATE repo -----------------------
# A systemd service has no TTY, so git cannot prompt for a password and will
# fail (status 1) unless credentials are stored for the owning user. Install
# the 'store' credential helper for that user and prime it with one
# interactive login from a terminal. The stored username + PAT then let every
# non-interactive run authenticate. (For a public repo this is harmless.)
OWNER_HOME="$(getent passwd "$OWNER" 2>/dev/null | cut -d: -f6 || echo "/home/$OWNER")"
runuser -u "$OWNER" -- git config --global credential.helper store 2>/dev/null \
  || sudo -u "$OWNER" git config --global credential.helper store 2>/dev/null \
  || git config --file "$OWNER_HOME/.gitconfig" credential.helper store 2>/dev/null \
  || true
echo "==> Configured git credential helper 'store' for user '$OWNER'."
echo "    If the repo is PRIVATE, run ONE interactive fetch as $OWNER"
echo "    (you will be prompted once for username + PAT) so the daemon can"
echo "    authenticate later. e.g.:  sudo -u $OWNER -i git -C $TARGET fetch --prune origin"

# Make sure the log file exists and is writable by that user.
: > "$CLEAN_LOG" 2>/dev/null || true
chown "$OWNER:$GROUP" "$CLEAN_LOG" 2>/dev/null || true
chmod 664 "$CLEAN_LOG" 2>/dev/null || true

# --- 3. Install auto-runner (systemd preferred, cron fallback) ------------
UNIT_PREFIX="ctb-sync"
SYSTEMD=0
if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
  SYSTEMD=1
fi

if [ "$SYSTEMD" -eq 1 ]; then
  echo "==> Installing systemd units ($UNIT_PREFIX.service + $UNIT_PREFIX.timer) ..."
  cat > "/etc/systemd/system/$UNIT_PREFIX.service" <<EOF
[Unit]
Description=CTB GitHub auto-sync ($TARGET)
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=$OWNER
Group=$GROUP
ExecStart=/bin/bash $SYNC_SCRIPT
WorkingDirectory=$TARGET
Environment=CTB_BRANCH=$BRANCH
Environment=GIT_TERMINAL_PROMPT=0
Environment=CTB_RESTART_CMD=$RESTART_CMD
StandardOutput=append:$CLEAN_LOG
StandardError=append:$CLEAN_LOG
EOF

  cat > "/etc/systemd/system/$UNIT_PREFIX.timer" <<EOF
[Unit]
Description=Run CTB GitHub auto-sync every $INTERVAL

[Timer]
OnBootSec=2min
OnUnitActiveSec=$INTERVAL
OnCalendar=hourly
Persistent=true
Unit=$UNIT_PREFIX.service

[Install]
WantedBy=timers.target
EOF

  systemctl daemon-reload
  systemctl enable --now "$UNIT_PREFIX.timer"

  echo "==> Service installed & timer enabled."
  echo "    Run log : $CLEAN_LOG"
  echo "    Status  : systemctl status $UNIT_PREFIX.timer"
  echo "    Manual  : systemctl start $UNIT_PREFIX.service"
  echo
  echo "==> Running once immediately to verify ..."
  systemctl start "$UNIT_PREFIX.service" || true
  systemctl status "$UNIT_PREFIX.service" --no-pager || true
else
  echo "==> systemd not detected — falling back to cron (/etc/cron.d/$UNIT_PREFIX)."
  printf '%s\n' \
    "# CTB GitHub auto-sync — every hour on the hour" \
    "CTB_BRANCH=$BRANCH" \
    "GIT_TERMINAL_PROMPT=0" \
    "CTB_RESTART_CMD=$RESTART_CMD" \
    "0 * * * * $OWNER /usr/bin/env HOME=/home/$OWNER GIT_TERMINAL_PROMPT=0 /bin/bash $SYNC_SCRIPT >> $CLEAN_LOG 2>&1" > "/etc/cron.d/$UNIT_PREFIX"
  chmod 644 "/etc/cron.d/$UNIT_PREFIX"
  echo "==> Installed cron job.  Run log: $CLEAN_LOG"
fi

echo
echo "==> First sync (immediate) ..."
runuser -u "$OWNER" -- env CTB_BRANCH="$BRANCH" bash "$SYNC_SCRIPT" || true

echo
echo "==> DONE. Setup summary:"
echo "    Repo:     $TARGET"
echo "    Script:   $SYNC_SCRIPT"
echo "    Interval: $INTERVAL"
echo "    Log:      $CLEAN_LOG"
echo "    Boot/power-outage recovery: $([ $SYSTEMD -eq 1 ] && echo 'yes (systemd timer, Persistent=true)' || echo 'yes (cron on boot)')"
if [ -n "$RESTART_CMD" ]; then
  echo "    Restart on change: custom -> $RESTART_CMD"
else
  echo "    Restart on change: auto (docker-compose up -d --build when code changes)"
fi
echo "    Next run: $([ $SYSTEMD -eq 1 ] && systemctl list-timers "$UNIT_PREFIX.timer" --no-pager 2>/dev/null | grep -q "$UNIT_PREFIX" && echo 'scheduled (see systemctl list-timers)' || echo 'on the hour')"
