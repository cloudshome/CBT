# SKY 24/7 Trading Intelligence Agent — Operations Guide

> **Read this on the Ubuntu 24.04 SKY Hub before you enable the agent.**
> The agent is research-only: it never places a trade, never bypasses the risk gate, never writes `main`.

## 1. What the agent does (and does NOT do)

```
AI  = researcher + analyst + assistant   (proposes hypotheses, reads data, codes against tests)
SKY = quantitative engine + validator    (backtester, scorer, risk gate are authoritative)
HUMAN = final decision maker              (you approve; you trade)
```

**Allowed:** collect public market data, classify regime, generate hypotheses, run `run_backtest_on_store`, compute `E_R`/`PF`/`DD`/`N_eff`, produce `WATCH/CONSIDER/WAIT/AVOID` with `FACT/INTERPRETATION/HYPOTHESIS` tags, send `HIGH/CRITICAL` alerts, write `intelligence_reports`.

**Forbidden:** `place_order`, `withdraw`, `sudo`, private keys, `--force` without `SKY_ALLOW_FORCE_APPROVE`, direct `main` writes.

## 2. Install on Ubuntu 24.04 (SKY Hub)

```bash
# 1. Check out SKY Hub (FHS layout)
python main.py hub setup --mode local        # creates /opt/sky, /etc/sky, /var/lib/sky (or use --prefix for dry run)
python main.py hub doctor                    # must be green

# 2. Enable the dashboard (already)
sudo systemctl enable --now sky-dashboard.service
python main.py hub role                      # this PC = Hub, one agent
python main.py sky-agent health --json       # readiness strip

# 3. Enable the 24/7 intelligence agent (same FHS env as the dashboard)
sudo cp ops/systemd/sky-agent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now sky-agent.service
systemctl is-active sky-agent.service       # should print "active"
journalctl -u sky-agent -f                  # live logs (no secrets; redacted)
```

The unit is `Restart=always`, `RestartSec=5`, `WatchdogSec=60`, `WantedBy=multi-user.target` — it survives reboot, SSH disconnect, crash.

To run without systemd (foreground, same code `ExecStart` uses):

```bash
python -m sky_agent.daemon                  # or
python main.py sky-agent run --demo         # offline smoke (no network)
```

## 3. Configuration (`.env` / `/etc/sky/sky.env`)

| Key | Default | Notes |
|---|---|---|
| `SKY_AGENT_MARKET_POLL_SECONDS` | 300 | 5m regime poll |
| `SKY_AGENT_EDGAR_POLL_SECONDS` | 1800 | SEC poll; `SEC_MAX_RPS` stays ≤10 (we default 5) |
| `SKY_SEC_USER_AGENT` | `SKY Research Agent …` | Required by SEC fair-access |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | — | `HIGH/CRITICAL` alerts (optional) |
| `DISCORD_ANNOUNCE_WEBHOOK` | — | Fallback `HIGH/CRITICAL` |
| `LLM_PROVIDER` | `off` | Only escalated on `HIGH/CRITICAL` scored events |

No exchange trading credentials are read. The agent is public-data only.

## 4. Daily use

```bash
python main.py sky-agent health --json      # readiness + system probe
python main.py sky-agent status --json      # hypotheses · reports · regimes · sec_events
python main.py sky-agent collect --target all --demo --json
python main.py sky-agent report             # markdown daily report (05:00 UTC timer also fires)
python main.py sky-agent report --json      # JSON for dashboard/MCP consumers
python main.py sky-agent hypothesize --json
python main.py sky-agent hypothesize --hypothesis-id H-001 --json   # compare baseline vs filtered

# Scheduled report (systemd timer, daemon is primary)
systemctl list-timers sky-agent.timer
```

**Dashboard:** `/api/sky-agent/health`, `/api/sky-agent/status`, `/api/sky-agent/report`, `/api/sky-agent/hypotheses` — also surfaced on the System tab cards.

**MCP (Claude/Cursor):** `sky_agent_status`, `sky_agent_report`, `sky_agent_health`, `sky_agent_hypotheses` (read-only, allow-list enforced like `ask/risk/health`).

## 5. Scoring & notification policy

Per-event 7 subscores (0–10): `relevance, impact, confidence, urgency, novelty, reliability, relation` → total 0–70 → `LOW (<20) / MEDIUM (20–35) / HIGH (35–50) / CRITICAL (>50)`.

Only `HIGH/CRITICAL` push to Telegram/Discord; `MEDIUM` → daily report; `LOW` → stored. Deduplication window 1h (`sha256(kind+params)`), rate-limited.

## 6. SEC EDGAR notes

- Consumer only (`data.sec.gov` + bulk ZIPs, no filer credentials, no `sec-api.io` requirement).
- Columns: `cik, accession_number, form_type, filing_date, acceptance_datetime, period_of_report, event_type, severity (1–5), direction, source_url`.
- Backtester **must** join on `acceptance_datetime` — using `period_of_report` is look-ahead bias and is rejected by tests.
- 8-K taxonomy: `bankruptcy, going_concern, debt_default, secondary_offering, buyback, acquisition, ceo_resignation, guidance_* , litigation, earnings_release, other`. `sec-api.io` is only added if full-text search proves necessary after measuring the official API.

## 7. Hardening drills (do these on real hardware)

Each drill has a measurable pass condition — the `python main.py sky-agent health --json` after the drill must return to `ok` or `blocked` (never *silent*).

| Drill | Command | Expect |
|---|---|---|
| Reboot | `sudo reboot` then `systemctl is-active sky-agent` | `active` without manual start |
| Crash | `sudo kill -9 $(pgrep -f sky_agent)` | `RestartSec=5` respawn, `agent_runs` heartbeat resumes |
| Network | `sudo iptables -A OUTPUT -d api.binance.com -j DROP` then restore | Backoff, no duplicate rows, `level` stays `degraded` not `down` silently |
| Rate-limit 429 | stub Binance `weight=1200` response | Exponential backoff, `Retry-After` honoured |
| Corrupt Parquet | `echo corrupt > /var/lib/sky/store/.../part.parquet` | `quality.py` quarantines, `doctor --strip` reports `NOT READY`, no signal emitted |
| Disk pressure | `fallocate -l 95% /var/lib/sky/fill.img` | `disk >85%` CRITICAL alert, collector pauses writes |
| Duplicate accession | run `sky-agent collect --target edgar` twice | Second run `rows_added=0` (accession PK) |
| Long run | `sky-agent run --max-ticks 1000 --demo` | No leak: RSS stable, `idempotency` holds |

Automated regression for the idempotent/corrupt/duplicate cases lives in `tests/test_sky_agent_hardening.py` (offline, `DEMO_MODE=1`).

## 8. Safety invariants (tested)

- Recommendation is only `WATCH/WAIT/CONSIDER/AVOID` — `BUY NOW` never produced.
- `risk_gate` blocks are preserved (`RISK_GATE_CLOSED` typed code, never auto-overridden).
- `SKY_ALLOW_FORCE_APPROVE` is the only escape hatch and is audited.
- Signal memory and Parquet PKs prevent duplicate trades or candles.

## 9. Uninstall / pause

```bash
sudo systemctl disable --now sky-agent.service   # pauses monitoring only
sudo systemctl disable --now sky-agent.timer
python main.py hub doctor                         # sanity after
```

The Hub database (`/var/lib/sky/cryptobrain.db`) and store (`/var/lib/sky/store`) are kept; `hub backup/restore` still works.

## 10. Where to look

- Code: `sky_agent/` + `sky_agent/collectors/edgar.py` + `sky_agent/daemon.py`
- Discovery & trade-offs: `docs/DISCOVERY_2026-08-19_AGENT.md`
- This guide: `docs/AGENT_OPERATIONS.md`
- Tests: `tests/test_sky_agent.py`, `tests/test_sky_agent_hardening.py`, `tests/test_mcp_stdio.py`
- Service: `ops/systemd/sky-agent.service`
