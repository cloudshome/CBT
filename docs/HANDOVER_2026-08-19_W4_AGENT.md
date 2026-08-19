# Handover 2026-08-19 W4 — 24/7 SKY Intelligence & Research Agent

**Branch:** `arena/01a01904-sky` → PR #64 vs `main`
**Commit:** `17a2ef2 Agent: 24/7 SKY Intelligence & Research Agent — discovery + daemon + SEC EDGAR + hardening`
**Version:** discovery `docs/DISCOVERY_2026-08-19_AGENT.md` + operations `docs/AGENT_OPERATIONS.md`

## What this session shipped

Single PR, 24 files, 2421 insertions, 0 threshold moved, 0 order path.

* **Discovery before code** — `docs/DISCOVERY_2026-08-19_AGENT.md` is the source of truth: repo map (P10 store, P12 validation/scorecard, risk gate, MCP, jobs, dashboard), gaps, chosen **hybrid daemon + scheduled workers + persisted job queue + MCP/CLI + systemd** topology (Hermes as *pattern* not binary; SEC EDGAR as isolated Fundamental/Event layer with `acceptance_datetime` boundary; `AI=researcher`, `SKY=validator`, `HUMAN=decision`).
* `sky_agent/` — `config`/`scoring`(7×0–10→LOW/MED/HIGH/CRITICAL, only HIGH/CRITICAL notify, 1h sha256 dedup)/`memory`(research_hypotheses/sec_filings/events/xbrl/intelligence_reports/market_regime_log, `ensure_memory_schema` idempotent)/`monitor_market`/`monitor_system`(CPU/RAM/disk/DB)/`collectors/edgar`(SEC `data.sec.gov` 10/s, taxonomy, demo stub)+`news`/`hypothesis`(H-001..3, `run_backtest_on_store` baseline vs filtered, stays hypothesis until graduation bar net)/`recommendation`(only WATCH/CONSIDER/WAIT/AVOID, `FACT/INTERPRETATION/HYPOTHESIS` + invalidation)/`notifications`(Telegram+Discord)/`daily_report`(05:00 UTC)/`daemon`(staggered, backoff, heartbeat to `agent_runs`, SIGTERM graceful, idempotent PKs).
* `ops/systemd/sky-agent.service` (`Restart=always`, `WatchdogSec=60`, `NoNewPrivileges`, `WantedBy=multi-user.target`) + `sky-agent.timer`.
* `main.py` — `sky-agent health|status|collect|report|run|hypothesize` (`--json`/`--demo`/`--target`/`--hypothesis-id`).
* `web/app.py` — `/api/sky-agent/health|status|report|hypotheses`.
* `mcp_server.py` — `sky_agent_status/report/health/hypotheses` (read-only allow-list; fixed inner-import scoping bug that made `SignalDB` local).
* Fixes: `sec_events` has no `form` column — queries now `accession,event_type,severity`.
* Tests: `tests/test_sky_agent.py` + `test_sky_agent_hardening.py` + `test_mcp_stdio.py:ROOT_TOOLS` (29+14 = 43 pass in this sandbox; `DEMO_MODE=1` offline).

## How to verify (offline, no creds)

```bash
SKY_NO_AUTO_INSTALL=1 DEMO_MODE=1 python -m pytest tests/test_sky_agent.py tests/test_sky_agent_hardening.py tests/test_mcp_stdio.py -q
SKY_NO_AUTO_INSTALL=1 DEMO_MODE=1 python main.py sky-agent health --json
SKY_NO_AUTO_INSTALL=1 DEMO_MODE=1 python main.py sky-agent collect --target edgar --demo --json
SKY_NO_AUTO_INSTALL=1 DEMO_MODE=1 python main.py sky-agent report --demo
curl http://127.0.0.1:8050/api/sky-agent/health
```

## What still needs a real Ubuntu 24.04 Hub host (human)

All 7 drills in `docs/AGENT_OPERATIONS.md §7` — reboot (`systemctl enable --now && reboot && systemctl is-active`), `kill -9`, network drop, corrupt Parquet → `quality.py` quarantine + `doctor --strip` NOT READY, disk 85%, duplicate accession, long run RSS stable. Run `python main.py hub setup --mode local && python main.py hub doctor` first.

## Next session jobs (pick one, in order)

1. **Tune scoring weights** after 7–14 days of live `intelligence_reports` (relevance/impact distribution on real market + real SEC filings). Do not hard-code new thresholds — measure.
2. **Wire EDGAR event study** — join `sec_events.acceptance_datetime` → `data/store` candles + `GET /api/scorecard` conditioned splits, compute `+5m/+1h/+1D` returns vs `SPY/QQQ` and expectancy in R; only promote event classes that clear sealed OOS.
3. **Dashboard Intelligence tab** — surface `sky_agent` health/status/report/hypotheses next to the System tab (reuse existing `GET /api/sky-agent/*`, add a cron-triggered `POST /api/sky-agent/report` archival).
4. **Derivatives → hypothesis filters** — connect stored `funding/OI/basis/CVD` (`data/derivatives.py`) into `sky_agent/hypothesis.py` filtered backtest (existing `H-002` is the stub).
5. **Hub FHS integration** — make `sky-agent.service` read `SKY_HUB_PREFIX` and `/etc/sky/sky.env` like `sky-dashboard.service` does; add `python main.py hub status` line for agent.
6. **Keep P11 paper grind parallel** — no threshold moved; packaging never unlocks trading.

## Known limitations to call out honestly

* No browser was opened in sandbox — daemon+MCP+web verified via Flask test client + jsdom + `python -m pytest` + `curl`, not eyeballing.
* EDGAR XBRL company-facts backfill is scaffolded (concept/frame) — deep per-concept metrics (revenue/EPS/cash/dilution) wait until 8-K event classes prove value.
* LLM escalation is stubbed behind `LLM_PROVIDER=off` — deterministic scoring is authoritative; no key required.
* `sky-agent collect --target market` currently pages `maybe_client().klines` not the Parquet store — swap to `StoreClient` for pure historical regime analysis.

## Files the next session reads first

`docs/DISCOVERY_2026-08-19_AGENT.md` → `docs/AGENT_OPERATIONS.md` → `sky_agent/` → `docs/HANDOVER_2026-08-19_W4_AGENT.md` (this file) → `SESSION_STATE.md` header will be updated after PR merges.
