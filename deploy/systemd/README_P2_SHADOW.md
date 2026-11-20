# CBT 24/7 P2_RP Shadow Runner & Ops Watchdog Daemons (Ubuntu / systemd)

Runs CBT's audited `P2_RP` risk-parity shadow desk idempotently at `00:02`, `04:02`, `08:02`, `12:02`, `16:02`, `20:02` UTC (2 minutes after every 4h candle close), accompanied by an hourly Ops Watchdog checking missed bars, DB integrity, disk space, and safe automated `.db.gz` backups. Strictly `TIER_0_PAPER` (`REAL_CAPITAL_ENABLED = False`).

## Combined Activation Note (Both Shadow Runner & Watchdog)

```bash
# 1. Copy both systemd unit pairs to systemd directory
sudo cp deploy/systemd/cbt-p2-shadow.{service,timer} /etc/systemd/system/
sudo cp deploy/systemd/cbt-p2-watchdog.{service,timer} /etc/systemd/system/

# 2. Reload systemd daemon
sudo systemctl daemon-reload

# 3. Enable and start both timers
sudo systemctl enable --now cbt-p2-shadow.timer
sudo systemctl enable --now cbt-p2-watchdog.timer

# 4. Verify timer schedules
systemctl list-timers cbt-p2-shadow.timer cbt-p2-watchdog.timer
```

## Useful Operational Commands

- Check shadow runner status: `systemctl status cbt-p2-shadow.timer`
- Check watchdog status: `systemctl status cbt-p2-watchdog.timer`
- Trigger one manual shadow cycle: `sudo systemctl start cbt-p2-shadow.service`
- Trigger one manual watchdog check: `sudo systemctl start cbt-p2-watchdog.service`
- Inspect shadow runner logs: `journalctl -u cbt-p2-shadow.service -n 50 -f`
- Inspect watchdog logs: `journalctl -u cbt-p2-watchdog.service -n 50 -f`
