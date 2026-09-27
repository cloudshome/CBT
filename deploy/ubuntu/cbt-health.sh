#!/usr/bin/env bash
# =============================================================================
#  cbt-health.sh  —  CBT Service Health Check
#  Run anytime to see the full status of all CBT services.
#  Good to run after a reboot / power outage to confirm auto-recovery worked.
#
#  Installed as /usr/local/bin/cbt-health by ubuntu-setup.sh.
#  Paths come from /etc/cbt/cbt.env (no hardcoded home dir), with a fallback
#  that derives them from this script's own location inside a checkout.
# =============================================================================
set -uo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'

SERVICES=("cbt-fastapi" "cbt-express" "cbt-frontend")
TIMER="cbt-sync.timer"
CBT_CONFIG="${CBT_CONFIG:-/etc/cbt/cbt.env}"

# --------------------------------------------------------------------------- #
# Discover paths
# --------------------------------------------------------------------------- #
# shellcheck disable=SC1090
[ -f "$CBT_CONFIG" ] && . "$CBT_CONFIG"

if [ -z "${CBT_PROJECT_DIR:-}" ] || [ ! -d "${CBT_PROJECT_DIR:-}" ]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    if [ -f "$SCRIPT_DIR/../../.env.example" ]; then
        CBT_PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
    fi
fi
if [ -n "${CBT_PROJECT_DIR:-}" ] && { [ -z "${CBT_REPO_DIR:-}" ] || [ ! -d "${CBT_REPO_DIR:-}/.git" ]; }; then
    CBT_REPO_DIR="$(git -C "$CBT_PROJECT_DIR" rev-parse --show-toplevel 2>/dev/null || echo "$CBT_PROJECT_DIR")"
fi
CBT_GIT_BRANCH="${CBT_GIT_BRANCH:-main}"

echo ""
echo -e "${CYAN}============================================================${NC}"
echo -e "${CYAN}   CBT Health Check — $(date '+%Y-%m-%d %H:%M:%S')${NC}"
echo -e "${CYAN}============================================================${NC}"
echo ""

# Paths
echo -e "  ${CYAN}Installation:${NC}"
if [ -n "${CBT_PROJECT_DIR:-}" ]; then
    echo -e "    Repo root   : ${CBT_REPO_DIR:-unknown}"
    echo -e "    App root    : ${CBT_PROJECT_DIR}"
    echo -e "    Env file    : ${CBT_PROJECT_DIR}/.env"
    if [ -f "$CBT_PROJECT_DIR/.env" ]; then
        echo -e "      ${GREEN}●${NC} .env present"
    else
        echo -e "      ${RED}●${NC} .env MISSING — services will fail to start"
        echo -e "        Fix: sudo cp '$CBT_PROJECT_DIR/.env.example' '$CBT_PROJECT_DIR/.env' && sudo nano '$CBT_PROJECT_DIR/.env'"
    fi
    if [ -f "$CBT_CONFIG" ]; then
        echo -e "    Path config : ${CBT_CONFIG}"
    else
        echo -e "    Path config : ${YELLOW}${CBT_CONFIG} not found (using script location)${NC}"
    fi
else
    echo -e "    ${RED}●${NC} Could not locate the CBT app root."
    echo -e "      Fix: sudo bash <repo>/deploy/ubuntu/ubuntu-setup.sh"
fi

# Services
echo ""
echo -e "  ${CYAN}Systemd Services:${NC}"
for svc in "${SERVICES[@]}"; do
    STATUS=$(systemctl is-active "$svc" 2>/dev/null || echo "unknown")
    UPTIME=$(systemctl show "$svc" -p ActiveEnterTimestamp --value 2>/dev/null || echo "")
    if [ "$STATUS" = "active" ]; then
        echo -e "    ${GREEN}●${NC} $svc — ${GREEN}running${NC}  (since $UPTIME)"
    else
        echo -e "    ${RED}●${NC} $svc — ${RED}$STATUS${NC}"
        echo -e "      └ Fix: sudo systemctl restart $svc   (logs: sudo journalctl -u $svc -n 50)"
    fi
done

# Timer
echo ""
echo -e "  ${CYAN}Auto-Sync Timer:${NC}"
TIMER_STATUS=$(systemctl is-active "$TIMER" 2>/dev/null || echo "unknown")
NEXT=$(systemctl list-timers "$TIMER" --no-pager 2>/dev/null | grep cbt-sync | awk '{print $1, $2}' || echo "unknown")
if [ "$TIMER_STATUS" = "active" ]; then
    echo -e "    ${GREEN}●${NC} $TIMER — ${GREEN}active${NC}"
    echo -e "      Next run: $NEXT"
else
    echo -e "    ${RED}●${NC} $TIMER — ${RED}$TIMER_STATUS${NC}"
    echo -e "      Fix: sudo systemctl start $TIMER"
fi

# Git status
echo ""
echo -e "  ${CYAN}Git Sync Status:${NC}"
if [ -n "${CBT_REPO_DIR:-}" ] && [ -d "${CBT_REPO_DIR:-}/.git" ]; then
    LOCAL=$(git -C "$CBT_REPO_DIR" rev-parse --short HEAD 2>/dev/null || echo "unknown")
    GIT_TERMINAL_PROMPT=0 git -C "$CBT_REPO_DIR" fetch origin "$CBT_GIT_BRANCH" --quiet 2>/dev/null || true
    REMOTE=$(git -C "$CBT_REPO_DIR" rev-parse --short "origin/$CBT_GIT_BRANCH" 2>/dev/null || echo "unknown")
    if [ "$LOCAL" = "$REMOTE" ]; then
        echo -e "    ${GREEN}●${NC} Up to date (${LOCAL})"
    else
        echo -e "    ${YELLOW}●${NC} Behind origin/$CBT_GIT_BRANCH (local: $LOCAL, remote: $REMOTE)"
        echo -e "      Sync will pull on the next timer run — or force it: sudo cbt-deploy"
    fi
    DIRTY=$(git -C "$CBT_REPO_DIR" status --porcelain 2>/dev/null | head -5)
    if [ -n "$DIRTY" ]; then
        echo -e "    ${YELLOW}●${NC} Uncommitted local changes present — 'git pull --ff-only' may fail:"
        printf '%s\n' "$DIRTY" | sed 's/^/        /'
    fi
else
    echo -e "    ${RED}●${NC} No git checkout found at ${CBT_REPO_DIR:-<unknown>}"
fi

# Port availability
echo ""
echo -e "  ${CYAN}Port Availability:${NC}"
for PORT in 8000 3000 5173; do
    if ss -tlnp 2>/dev/null | grep -q ":$PORT "; then
        echo -e "    ${GREEN}●${NC} Port $PORT — listening"
    else
        echo -e "    ${RED}●${NC} Port $PORT — NOT listening"
    fi
done

echo ""
echo -e "  ${CYAN}Useful Commands:${NC}"
echo "    sudo journalctl -fu cbt-fastapi      # FastAPI live logs"
echo "    sudo journalctl -fu cbt-express      # Express live logs"
echo "    sudo journalctl -fu cbt-sync         # Sync history"
echo "    sudo cbt-deploy                      # Force sync + rebuild now"
echo ""
