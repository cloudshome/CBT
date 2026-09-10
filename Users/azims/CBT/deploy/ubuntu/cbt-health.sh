#!/usr/bin/env bash
# =============================================================================
#  cbt-health.sh  —  CBT Service Health Check
#  Run anytime to see the full status of all CBT services.
#  Good to run after a reboot / power outage to confirm auto-recovery worked.
# =============================================================================
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'

SERVICES=("cbt-fastapi" "cbt-express" "cbt-frontend")
TIMER="cbt-sync.timer"
REPO_DIR="/home/cbt/CBT"

echo ""
echo -e "${CYAN}============================================================${NC}"
echo -e "${CYAN}   CBT Health Check — $(date '+%Y-%m-%d %H:%M:%S')${NC}"
echo -e "${CYAN}============================================================${NC}"
echo ""

# Services
echo -e "  ${CYAN}Systemd Services:${NC}"
for svc in "${SERVICES[@]}"; do
    STATUS=$(systemctl is-active "$svc" 2>/dev/null || echo "unknown")
    UPTIME=$(systemctl show "$svc" -p ActiveEnterTimestamp --value 2>/dev/null || echo "")
    if [ "$STATUS" = "active" ]; then
        echo -e "    ${GREEN}●${NC} $svc — ${GREEN}running${NC}  (since $UPTIME)"
    else
        echo -e "    ${RED}●${NC} $svc — ${RED}$STATUS${NC}"
        echo -e "      └ Fix: sudo systemctl restart $svc"
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
    echo -e "      Fix: sudo systemctl start cbt-sync.timer"
fi

# Git status
echo ""
echo -e "  ${CYAN}Git Sync Status:${NC}"
LOCAL=$(git -C "$REPO_DIR" rev-parse --short HEAD 2>/dev/null || echo "unknown")
git -C "$REPO_DIR" fetch origin main --quiet 2>/dev/null || true
REMOTE=$(git -C "$REPO_DIR" rev-parse --short origin/main 2>/dev/null || echo "unknown")
if [ "$LOCAL" = "$REMOTE" ]; then
    echo -e "    ${GREEN}●${NC} Up to date (${LOCAL})"
else
    echo -e "    ${YELLOW}●${NC} Behind origin/main (local: $LOCAL, remote: $REMOTE)"
    echo -e "      Sync will pull in next timer cycle (≤5 min)"
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
echo "    sudo /usr/local/bin/cbt-sync.sh      # Force sync now"
echo ""
