# How to use the 24/7 Ubuntu PC

**Decision (2026-08-19, W4.2):** this machine **is the SKY Hub**.
Use **one** research agent. Do **not** add a second “PC-use” agent.

This is how the project gets bigger without losing the aim:
become a consistently profitable trader (paper first, prove one edge, then micro).

## What this PC runs

| Unit | Job | Required |
|---|---|---|
| `sky-dashboard.service` | Clickable desk at `127.0.0.1:8050` | yes |
| `sky-paper.service` | `paper --watch` — the money path (P11) | yes |
| `sky-scan.timer` | Scheduled scans into the store | yes |
| `sky-backup.timer` | Nightly SQLite-safe backup | yes |
| `sky-agent.service` | 24/7 research: WATCH / CONSIDER / WAIT / AVOID | yes |
| `sky-agent.timer` | 05:00 UTC daily-report nudge | optional |

All five required units read `/etc/sky/sky.env` (FHS). Tests use `SKY_HUB_PREFIX`.

## Do we need an agent for PC use?

**Yes — the one we already have.** `sky-agent.service` is the 24/7
researcher. It collects public data, scores events, writes memory, and
alerts on HIGH/CRITICAL. It never places a trade.

**No — do not add a second agent** that:

- logs into Gmail / banks / social accounts
- “uses the PC” like AutoGPT
- places or even drafts live exchange orders
- bypasses the risk gate

A second agent would look busy and hide who is in charge. SKY is the
brain. You are the decision maker.

## What you still do (human)

1. Approve or reject every paper trade.
2. Journal every decided real trade.
3. Sunday `python main.py weekly --export`.
4. Never lower the graduation bar (≥ +0.50R net, WR > 55%, PF ≥ 1.5,
   compliance ≥ 90%, ≥100 backtest + ≥20 paper).

## How to turn it on (this PC)

```bash
# first night (no root)
bash ops/first_night.sh
python3 main.py web --host 127.0.0.1 --port 8050

# 24h (sudo, once)
# see docs/HOME_HUB_FIRST_NIGHT.md §2
sudo systemctl enable --now sky-dashboard.service sky-paper.service \
  sky-scan.timer sky-backup.timer sky-agent.service sky-agent.timer

python3 main.py hub role
python3 main.py hub status
python3 main.py hub doctor
python3 main.py sky-agent health --json
```

Phone access = SSH tunnel or Caddy TLS (`ops/proxy/`). **Never**
port-forward 8050.

## Clickable surface

Dashboard **🧠 Agent** tab → **THIS PC — 24/7 HUB ROLE**.
Same payload as `GET /api/hub/role` and `python main.py hub role`.

## Honest limits

- This sandbox cannot `systemctl enable` a live host. Status reports
  “not installed” honestly.
- Scoring weights stay default until 7–14 days of *live* reports exist.
- EDGAR is optional research, not a BTC/ETH/GOLD edge.
- `p22_complete` stays false until real signers attach evidence.

Kept ideas that must not be thrown away: [`docs/KEPT_IDEAS.md`](KEPT_IDEAS.md).
