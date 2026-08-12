# SESSION_STATE.md — CryptoBrain / SKY

> **Purpose:** the *single* handoff file a new Arena session reads first
> to resume work without re-deriving context. **Update at the end of
> every session** (see "End-of-session checklist" at the bottom).
> **Read first** at the start of every new session (see "Start-of-session
> recipe" at the bottom).
>
> **Contract:** do a **full-document reconciliation pass every time** —
> re-read the entire file, fix pre-existing placeholders and stale
> status lines, not just append new sections.

**Last updated:** 2026-08-12 (TODO-1.bis shipped + P10 data-infrastructure roadmap recorded)
**Branch:** `arena/019ff4c3-sky`
**HEAD commit:** see "Last commit" below
**Default branch:** `main` @ `f0eff12` (PR #6 merged 2026-08-12)
**PR:** [#7](https://github.com/Azimshawon/SKY/pull/7) — this branch → `main`.
Opened as the closing step of the session (the standing convention:
work the session, open the PR before ending it).
**Python:** 3.10+ tested on 3.10–3.13 + Windows (per existing CI)

> **This session's decision:** the user asked "can we work on?" and,
> from the options offered, chose **TODO-1.bis** (the combined
> dashboard doctor strip) with **no PR**. That was the last
> non-blocked, non-parked item on the list, so it was implemented
> end-to-end across all four surfaces.
>
> **Then** the user supplied a large data-infrastructure plan (own the
> market data, TradingView-style terminal) and asked for it to be
> recorded for future workload, with corrections, keeping the path to
> the aim straight. That is now **P10**, planned in
> [`docs/DATA_INFRASTRUCTURE_ROADMAP.md`](docs/DATA_INFRASTRUCTURE_ROADMAP.md).
> No P10 code was written this session — planning only, deliberately.

---

## Project

**CryptoBrain / SKY** — multi-source, multi-indicator, conditional-signal
trading engine for BTC, ETH, and XAUUSD/GOLD with a strict human-approval
gate. **Read-only by design** — the engine *cannot* place a real exchange
order; the human approves, the paper-runner executes, the engine proposes.
The full proposition, sources, and progression ladder are in
[`BLUEPRINT.md`](./BLUEPRINT.md). The history of the two-upstream merge
is in [`MERGE_NOTES.md`](./MERGE_NOTES.md). The professional trading
plan (18 phases, 15-item rulebook) is in
[`PROFESSIONAL_PLAN_DECISIONS.md`](./PROFESSIONAL_PLAN_DECISIONS.md).

---

## The aim (never changes)

**Become a fully independent, consistently profitable trader.**
Independence has two halves: **decision independence** (our own engine
+ risk gate + approval loop — ✅ done, P1–P9) and **data independence**
(our own stored market history — ❌ not started, P10). Every phase
below is ordered by how directly it moves those two lines.

---

## Current phase

**P9 (Capability Endpoints) — complete.** Every planned P7/P8/P9 code
item has landed. Open items: two *human* GitHub actions (TODO-7,
TODO-8), the next *engine* item (TODO-11 / P11, paper-book proof), and
the next *major milestone* (TODO-12 / P10, data infrastructure).

| Phase | Theme | Status | Notes |
|---|---|---|---|
| P1 | RAG Library | ✅ Complete | `brain/library.py`, `brain/ask.py` |
| P2 | LLM Reasoning | ✅ Complete | `brain/brief.py`, `ai/llm_brain.py` |
| P3 | Autonomous Hands | ✅ Complete | `brain/agents.py`, `agent_runs` table |
| P4 | MCP Nervous System | ✅ Complete | `mcp_server.py` (zero-dep stdio JSON-RPC 2.0) |
| P5 | Immune System | ✅ Complete | `brain/immune.py` |
| P6 | Hidden Alpha & Variance | ✅ Complete | `engine/hidden_alpha.py`, `engine/execution.py`, `engine/correlation.py`, `brain/analytics.py` |
| P7 | Agent Surface (SKILL + CLI) | ✅ Complete | `SKILL.md`, `python main.py doctor`, `python main.py skill` |
| P8 | Source Channels (router) | ✅ Complete | `brain/channels.py` + `/api/channels` + dashboard "Channels" panel |
| **P9** | **Capability Endpoints** | **✅ Complete** | MCP 13 tools (incl. `desk_status`, `readiness`); readiness strip on all surfaces; wheel-gate content landed (CI activation = TODO-7) |
| **P11** | **Paper-book proof** | 🔜 Next | Grind to a real 100/20, journal closed trades, move the graduation gate |
| **P10** | **Data infrastructure + market terminal** | 📋 Planned | 12 milestones in [`docs/DATA_INFRASTRUCTURE_ROADMAP.md`](docs/DATA_INFRASTRUCTURE_ROADMAP.md) |
| **P12** | **Regime-conditional backtests** | ⏸ After P10 | Years of stored data, conditioned on OI / funding / CVD |

Full phase matrix: [`AI_ANATOMY_ROADMAP.md`](./AI_ANATOMY_ROADMAP.md).
Full P7/P8/P9 plan with risk + rollback: [`ROADMAP_AGENT_REACH_UPGRADE.md`](./ROADMAP_AGENT_REACH_UPGRADE.md).

---

## Completed work

### Session 2026-08-12 (this branch): TODO-1.bis readiness strip

Branched from `main` @ `f0eff12`. 0 regressions.
Tests **324 → 339 pass / 1 skip** (+15). Version **2.1.0 → 2.2.0**.

One verdict answering "can I trust the desk right now?", rolled up
**worst-first** across three pillars that already existed separately:

| Pillar | Source of truth | Levels |
|---|---|---|
| `channels` | `brain.channels.probe_all()` | ok / degraded / down |
| `immune` | `brain.immune.run_health_check()` | ok / degraded / down |
| `risk_gate` | the gate inside `desk_status()` | ok / degraded / blocked |

Ladder: `ok < degraded < blocked < down`; only `ok` sets `ready: true`.

**Files changed:**
- `brain/agent.py` — `readiness_strip()`, `format_readiness_strip()`,
  `_channels_pillar()`, `_immune_pillar()`, `_gate_pillar()`,
  `_worst()`, plus the `_READINESS_ORDER` / `_IMMUNE_TO_LEVEL` /
  `_CHANNEL_TO_LEVEL` maps. Every pillar is exception-isolated.
- `main.py` — `doctor --strip` flag; `cmd_doctor` leads with the strip
  in text mode and adds a `readiness` key in `--json` mode.
- `web/app.py` — `GET /api/readiness` (never 500s), `.strip` CSS,
  the `#readiness` element above every tab, `loadReadiness()`, wired
  into `render()`, the init IIFE, and the 5-minute diagnostic timer.
- `mcp_server.py` — `readiness` tool; `SERVER_VERSION` 1.2.0 → 1.3.0.
- `config.py` + `pyproject.toml` — version 2.2.0.
- Tests: `test_agent.py` (+5), `test_web_api.py` (+2),
  `test_dashboard_js.py` (+2, node-executed), `test_channels.py` (+3),
  `test_mcp_stdio.py` (+1 and `ROOT_TOOLS` updated).
- Docs: `SKILL.md`, `README.md`, `ARCHITECTURE.md` (new invariant #10),
  `AI_ANATOMY_ROADMAP.md`, `CHANGELOG.md` (v2.2.0), `TODO.md`,
  `docs/HUMAN_ACTIONS.md` (corrected the dead `wheel-gate-job.yml` link).

**Also found and documented:** `main`'s last commit renamed the
wheel-gate spec to `docs/.github/workflows/ci.yml`. That path is
**inert** — nested under `docs/`, GitHub Actions never reads it. TODO-7
is still open and `docs/HUMAN_ACTIONS.md` now says so explicitly.

### Prior sessions (already on `main`)

- **v2.1.0 / PR #6** — `desk_status()` advisory, `next_scheduled_agent()`,
  `python main.py desk`, MCP `desk_status`, `/api/desk`, wheel-gate
  content (`ci/wheel_gate.py` + `pyproject.toml`), D1–D5 recorded.
- **v2.0.x / PR #5** — P7 SKILL + doctor/skill CLI, P8 channels router
  + dashboard panel, P9 MCP 11-tool surface, handoff memory files.

See CHANGELOG v2.0.1–v2.2.0 for file-level detail.

---

## Currently working on

Nothing in flight. The working tree is committed and pushed to
`arena/019ff4c3-sky`.

**Planning landed this session (no code):**
`docs/DATA_INFRASTRUCTURE_ROADMAP.md` — P10, the market-data
independence phase. It reconciles a user-supplied plan against what
SKY already has, and records seven corrections (analytics ~80% already
built; SQLite+Parquet not Postgres+Redis; Lightweight Charts standalone
not React/Next; no FastAPI/Docker; liquidations can't be backfilled;
reuse the existing cross-exchange probe; one-PR-per-session).

---

## Remaining work (prioritised)

1. **TODO-11 (P11)** — prove the paper book: grind `simulator` to a
   real 100/20, journal the closed trades so `compliance` stops being
   `None`, move the graduation line. Next *code* item. Small.
2. **TODO-12 (P10)** — data infrastructure + market terminal. The next
   *major* milestone; 12 shippable steps in
   [`docs/DATA_INFRASTRUCTURE_ROADMAP.md`](docs/DATA_INFRASTRUCTURE_ROADMAP.md).
   Start at P10.1 (schema + Parquet store). **Read the roadmap first** —
   it records which parts of the incoming plan were corrected and why.
3. **TODO-7** — human pastes the wheel-gate job into the **real**
   `.github/workflows/ci.yml` (the `docs/` copy is inert).
4. **TODO-8** — human protects `main` (require PR). Token: HTTP 403.
5. **TODO-9 / TODO-10** — Dify then LibreChat. Parked behind both the
   graduation gate *and* P10. Do not start next session.

Full list and rationale: see [`TODO.md`](./TODO.md).

---

## Known problems / caveats

1. **D1–D5 are answered.** See `ROADMAP_AGENT_REACH_UPGRADE.md` §4.
2. **Arena's GitHub integration: one PR per chat session.** The
   session convention is: do the work, then open **one** PR as the
   closing step. PR #7 is this session's.
3. **`mcp>=1.0` is listed in `requirements.txt` but not required**
   for the zero-dep `mcp_server.py`. It is only needed for the
   SDK-based `python main.py mcp` server.
4. **Immune system reports `CRITICAL` in `DEMO_MODE=1`** because the
   committed sample data is stale by design. Expected, not a bug —
   and it is why `doctor --strip` reports `down` offline. On live
   data the same pillar goes green.
5. **Arena cannot push under `.github/workflows/`.** The wheel-gate
   job spec therefore lives at `docs/.github/workflows/ci.yml`, which
   GitHub Actions does **not** execute. Source of truth for running
   the gate is `ci/wheel_gate.py` locally (TODO-7).
6. **`CHANGELOG.md` is current** through v2.2.0.
7. **The dashboard readiness strip lives outside `#app`.** `render()`
   replaces `#app.innerHTML` wholesale, so anything inside it would be
   destroyed on every scan. Keep the strip where it is.
8. **SKY stores no market data.** Every scan fetches ~500 candles and
   discards them; `data/database.py` has 10 tables and none hold
   candles. This is the structural limit P10 exists to remove — it
   caps every backtest at one API response.
9. **`BinanceClient.liquidations()` is not liquidation data.** It is a
   24h-ticker proxy. Real forced-order data only comes from the
   `!forceOrder@arr` WebSocket stream and **cannot be backfilled** —
   it accumulates from the day collection starts. P10.4 renames it.
10. **Cross-exchange logic already exists** in
    `brain/agent.py:_cross_exchange_probe()` (KuCoin + OKX). P10.7
    generalises it into a stored series — do not write a second one.

---

## Next recommended action

1. Next *code* session: start **TODO-11** (paper-book proof). Do not
   add another AI surface — there are already five and they all agree.
2. A human does TODO-7 + TODO-8 from
   [`docs/HUMAN_ACTIONS.md`](docs/HUMAN_ACTIONS.md).
3. Do **not** start Dify/LibreChat.

**Suggested next-session prompt:**

> Continue SKY from SESSION_STATE.md, branch arena/019ff4c3-sky.
> The readiness strip (TODO-1.bis) is done and the agent surface is
> complete. Start TODO-11 (P11): prove the paper book. Run
> `python main.py simulator`, grind to a real 100/20, journal the
> closed trades, and move the graduation gate. Do not add new agents,
> panels, or endpoints. Do not start Dify or LibreChat.
>
> After P11 lands, the next major milestone is TODO-12 (P10, data
> infrastructure) — read `docs/DATA_INFRASTRUCTURE_ROADMAP.md` in full
> before writing any of it, and start at milestone P10.1.

---

## Last successful test command

```bash
cd /home/user/SKY
DEMO_MODE=1 .venv/bin/python -m pytest tests/ -q
# 339 passed, 1 skipped in 61.80s
```

Local wheel-gate (build + dup-check, no install):

```bash
DEMO_MODE=1 .venv/bin/python ci/wheel_gate.py
# builds cryptobrain-2.2.0-py3-none-any.whl ; no duplicate entries
```

Readiness strip, all four surfaces:

```bash
DEMO_MODE=1 python main.py doctor --strip          # CLI text
DEMO_MODE=1 python main.py doctor --strip --json   # CLI JSON
curl -s localhost:8080/api/readiness                # HTTP
# MCP: tools/call {"name": "readiness", "arguments": {}}
```

(The 1 skipped test is the SDK-already-installed fallback, present
since the consolidated build per `MERGE_NOTES.md`.)

## Last commit

```
see `git log --oneline -3` on arena/019ff4c3-sky
(this session: one commit — feat(readiness): combined doctor strip)
```

---

## Start-of-session recipe (paste this when starting a new session)

```
You are continuing development of the existing SKY project at
github.com/Azimshawon/SKY, branch arena/019ff4c3-sky.

First, inspect the GitHub repository before making changes.

Read in this order:
1. SESSION_STATE.md         (current state, current TODO, last commit)
2. TODO.md                  (prioritised remaining work)
3. ARCHITECTURE.md          (module map + invariants)
4. CHANGELOG.md             (what shipped, when)
5. README.md                (user-facing overview)
6. ROADMAP_AGENT_REACH_UPGRADE.md  (the P7/P8/P9 plan + D1–D5 decisions)

Then inspect the relevant source files and tests.

Your job is to continue from the exact state left by the previous
session, starting with the top-priority item in TODO.md.

Rules:
- Do NOT recreate or redesign completed components.
- Do NOT assume anything that is not present in the repository.
- Preserve existing architecture unless there is a demonstrated
  reason to change it.
- Before modifying code, explain briefly what you found and what
  the next implementation step is.
- Implement the next highest-priority task from TODO.md.
- Run the relevant tests after implementation.
- Fix failures before considering the task complete.
- Maintain test count at ≥ 339 pass.
- Update SESSION_STATE.md with completed/current/remaining/known/
  next action. Full-document reconciliation, not append-only.
- Update CHANGELOG.md.
- Commit and push.

If the task is too large for the remaining session, split it into a
safe checkpoint rather than leaving the repository in an undocumented
state.

Before ending the session, open ONE pull request from this branch to
main (Arena allows one PR per chat session). Do not merge it yourself.
```

## End-of-session checklist (run before closing this session)

1. [x] Finish or safely stop the current task.
2. [x] Run `DEMO_MODE=1 python -m pytest tests/ -q` — must stay
   ≥ 339 pass.
3. [x] Fix any obvious failures.
4. [x] Update `SESSION_STATE.md` with the exact current state.
5. [x] Update `TODO.md` — mark finished items done, reprioritise.
6. [x] Update `CHANGELOG.md`.
7. [x] Record all files changed in `SESSION_STATE.md`.
8. [x] Record the last successful test command.
9. [x] Record the last commit reference.
10. [x] Record any known bugs or unresolved issues.
11. [x] `git add` / `git commit` / `git push origin arena/019ff4c3-sky`.
12. [x] Open the session PR as the closing step — PR #7.
