# CBT 24/7 P2_RP Shadow Runner Daemon (Ubuntu / systemd)

Runs CBT's audited `P2_RP` risk-parity shadow desk idempotently at `00:02`, `04:02`, `08:02`, `12:02`, `16:02`, `20:02` UTC (2 minutes after every 4h candle close). Strictly `TIER_0_PAPER` (`REAL_CAPITAL_ENABLED = False`).

## 4-Step Activation Note

```bash
sudo cp deploy/systemd/cbt-p2-shadow.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now cbt-p2-shadow.timer
systemctl list-timers cbt-p2-shadow.timer
```

## Useful Operational Commands

- Check timer schedule: `systemctl status cbt-p2-shadow.timer`
- Trigger one manual cycle: `sudo systemctl start cbt-p2-shadow.service`
- Inspect execution journal logs: `journalctl -u cbt-p2-shadow.service -n 50 -f`
