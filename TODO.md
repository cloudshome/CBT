# TODO.md — CryptoBrain / SKY

> **Purpose:** the prioritised, actionable list of remaining work.
> Read at the start of every new Arena session (after SESSION_STATE.md).
> Update at the end of every session. Items are ordered by **value
> per session** — top items unlock the most user-visible capability
> for the smallest change.

**Last updated:** 2026-08-11

---

## 🔥 Top priority — start here in the next session

### TODO-1 · P8 dashboard "Channels" panel · `web/app.py`

**Why:** the `brain/channels.py` router is implemented and tested, but
it's not yet visible in the operator dashboard. Without this, the new
`python main.py doctor` and `python main.py channels` commands work
from the CLI but not from the web UI, which is the operator's primary
surface.

**Scope (small, ~50–100 lines):**
1. Add a `GET /api/channels` route in `web/app.py` that returns
   `brain.channels.doctor_report(as_json=True)`.
2. Add a regression test in `tests/test_web_api.py` that the endpoint
   returns 200 and valid JSON (the same `_sanitize_for_json` regression
   fix from `MERGE_NOTES.md` must apply).
3. Add a "Channels" panel in the dashboard template that renders the
   per-source status with the same data shape the CLI shows.
4. Auto-refresh the panel every 30s (matches the existing dashboard
   auto-refresh cadence).

**Definition of done:**
- `python main.py web` shows a "Channels" panel with cryptodada /
  discord / news / llm rows.
- `GET /api/channels` returns 200 with `{"channels": {...}}`.
- `DEMO_MODE=1 python -m pytest tests/ -q` is ≥ 286 pass.
- `SESSION_STATE.md` and `CHANGELOG.md` updated; commit + push.

**Risk:** low. `brain/channels.py` is already exception-isolated.
The `_sanitize_for_json` regression was already fixed in the
consolidated build per `MERGE_NOTES.md`.

---

## 🟡 P9 — Capability Endpoints (after TODO-1)

### TODO-2 · Extend MCP `tools/list` with the new read-only tools

**Why:** the `mcp_server.py` tool list currently exposes 6 tools
(`ask | tradestate | risk | health | brief | postreview`). After
TODO-1 ships, agents should also be able to call `channels`,
`correlation`, and the `hidden.*` family from MCP clients.

**Scope:**
1. Add to `ALLOWED_TOOLS` in `mcp_server.py`:
   - `channels` (wraps `brain.channels.list_channels(as_json=True)`)
   - `correlation` (wraps `cmd_correlation`)
   - `hidden_chart_read` (wraps `python main.py hidden chart_read`)
   - `hidden_analytics_mae` (wraps `python main.py hidden analytics mae`)
   - `hidden_analytics_mc` (wraps `python main.py hidden analytics mc`)
2. Keep the deny list for `approve | reject | execute | close |
   place_order` — these must never appear in `tools/list`.
3. Update `SKILL.md` tool table to reflect the new MCP surface.
4. Add tests in `tests/test_mcp_stdio.py` that the new tools appear
   in `tools/list` and that the deny list is still intact.

**Definition of done:** ≥ 290 pass; `tools/list` exposes the 11
read-only tools; deny list still enforced.

### TODO-3 · CI wheel-gate job

**Why:** Agent-Reach has it; SKY doesn't. Catches duplicate-wheel
bugs and broken packaged resources before they ship.

**Scope:**
1. Add a `wheel-gate` job to `.github/workflows/ci.yml` that:
   - builds the wheel from `pyproject.toml`,
   - detects duplicate wheel entries,
   - installs the wheel into a clean venv,
   - runs `python -c "import cryptobrain"` (or the actual module
     name) + a CLI smoke test (`python -c "import main; main.main(['doctor'])"`).

**Note:** the current repo doesn't have a `pyproject.toml` that
exposes a top-level `cryptobrain` import — `main.py` is at the repo
root. Either add a minimal `pyproject.toml` or scope the smoke test
to `python -c "import main"`. Decision belongs to TODO-6 (D4).

### TODO-4 · `brain/agent.desk_status()` advisory

**Why:** a single advisory response an agent can call to get the
operator's current state (risk gate, today's P&L, graduation verdict,
next scheduled agent, "what would a professional do right now?").

**Scope:**
1. Add `desk_status() -> dict` in `brain/agent.py` that aggregates
   `brain.risk_gate.evaluate_risk_gate` + `brain.metrics.business_metrics`
   + `data.simulator.graduation_status` + the next agent from
   `brain.agents`.
2. Expose via MCP (`desk_status` tool) and via `python main.py desk`.
3. Tests in `tests/test_agent.py`.

---

## 🟢 Maintenance / hygiene

### TODO-5 · Backfill `CHANGELOG.md`

The repo's `pyproject.toml` is at v2.0.0 but `CHANGELOG.md` stops at
v1.3.1. Add entries for v1.4, v1.5, v2.0 (the consolidated build),
and v2.0.1 (the P7/P8 commit on this branch).

### TODO-6 · Answer the D1–D5 decision list

In `ROADMAP_AGENT_REACH_UPGRADE.md` §4, the D1–D5 sub-decisions are
unanswered. The current session implemented the recommended default
(D1 = full P7, D2 = alias not rename, D3 = data sources only, D4 = ?
, D5 = ?). Get explicit confirmation before starting P9.

### TODO-7 · Activate GitHub Actions CI

The file `docs/CI-workflow.yml` was renamed to
`.github/workflows/ci.yml` (commit `8b16923`) to activate the
workflow, but Arena's GitHub integration can't push under
`.github/workflows/` (per commit `d40ff00` — automation token lacks
the `workflows` permission). The user must activate it from the
GitHub UI: rename / commit / re-enable. Then `wheel-gate` (TODO-3)
can use it.

---

## 📋 Decisions waiting on user

| ID | Decision | Default if no answer |
|---|---|---|
| D2 | `doctor` as alias of `health` (keep both) vs rename `health` → `doctor`? | Keep `health`, add `doctor` as alias (already done) |
| D3 | Channels scope: 3 data sources + LLM only, or also wrap risk gate / calibrator / journal? | 3 data sources + LLM (already done) |
| D4 | Add CI wheel-gate job? | **Open question** — recommend yes |
| D5 | OK to expose `docs/agent_install.md` as a `raw.githubusercontent.com` URL? | **Open question** — recommend yes |
| PR-1 | Open a PR from `arena/019ff045-sky` into `main`? | **Open question** — user chose "branch only" this session |

---

## 🚫 Explicitly out of scope (do NOT add to TODO)

- Web scraping of social platforms (Twitter / Reddit / Bilibili /
  Xiaohongshu / etc.) — out of scope per
  `ROADMAP_AGENT_REACH_UPGRADE.md` §5.
- Audio/video transcription — no audio source.
- Browser cookie extraction, third-party CLI orchestration
  (`gh` / `mcporter` / `twitter-cli` / `rdt-cli` / `bili-cli` /
  `OpenCLI` / `ffmpeg`) — CryptoBrain has zero of these dependencies.
- Autonomous exchange order placement — explicitly forbidden by
  `MERGE_NOTES.md` safety statement.
- Multi-language READMEs (CN/JP/KR) — single-language repo is fine.
