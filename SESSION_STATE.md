# SESSION_STATE.md — CryptoBrain / SKY

> **Purpose:** the *single* handoff file a new Arena session reads first
> to resume work without re-deriving context. **Update at the end of
> every session** (see "End-of-session checklist" at the bottom).
> **Read first** at the start of every new session (see "Start-of-session
> recipe" at the bottom).

**Last updated:** 2026-08-11 (end of session that landed commit `b0fe82f`)
**Branch:** `arena/019ff045-sky`
**HEAD commit:** `b0fe82f feat(agent-surface): adopt Agent-Reach patterns (P7/P8)`
**Default branch:** `main` (last commit `99ace0d`, untouched this session)
**Python:** 3.10+ tested on 3.10–3.13 + Windows (per existing CI)

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

## Current phase

**P8 (Source Channels) — implementation complete, dashboard panel pending.**

| Phase | Theme | Status | Notes |
|---|---|---|---|
| P1 | RAG Library | ✅ Complete | `brain/library.py`, `brain/ask.py` |
| P2 | LLM Reasoning | ✅ Complete | `brain/brief.py`, `ai/llm_brain.py` |
| P3 | Autonomous Hands | ✅ Complete | `brain/agents.py`, `agent_runs` table |
| P4 | MCP Nervous System | ✅ Complete | `mcp_server.py` (zero-dep stdio JSON-RPC 2.0) |
| P5 | Immune System | ✅ Complete | `brain/immune.py` |
| P6 | Hidden Alpha & Variance | ✅ Complete | `engine/hidden_alpha.py`, `engine/execution.py`, `engine/correlation.py`, `brain/analytics.py` |
| **P7** | **Agent Surface (SKILL + CLI)** | **✅ Complete (this commit)** | `SKILL.md`, `python main.py doctor`, `python main.py skill` |
| **P8** | **Source Channels (router)** | **🟡 Code complete, dashboard panel pending** | `brain/channels.py` exists; `web/app.py` "Channels" panel not yet added |
| P9 | Capability Endpoints (extended MCP + CI wheel-gate) | ⏳ Not started | See `ROADMAP_AGENT_REACH_UPGRADE.md` §6 |

Full phase matrix: [`AI_ANATOMY_ROADMAP.md`](./AI_ANATOMY_ROADMAP.md).
Full P7/P8/P9 plan with risk + rollback: [`ROADMAP_AGENT_REACH_UPGRADE.md`](./ROADMAP_AGENT_REACH_UPGRADE.md).

---

## Completed work (this session, 2026-08-11)

### Commit `b0fe82f` — `feat(agent-surface): adopt Agent-Reach patterns (P7/P8)`

7 files, +1624 / -1, **0 regressions**, tests **258 → 285 pass / 1 skip**.

**New files:**
- `SKILL.md` (155 lines) — agent-facing skill file: full tool surface,
  safety guarantee ("never place an exchange order"), citation contract,
  behavioural examples. Mirrors the Agent-Reach pattern of "one URL
  the agent reads."
- `ROADMAP_AGENT_REACH_UPGRADE.md` (348 lines) — full P7/P8/P9 plan with
  per-phase risk + rollback + definition-of-done + D1–D5 decision list.
- `docs/agent_install.md` (74 lines) — the one-pager an agent fetches
  when told "install CryptoBrain."
- `brain/channels.py` (491 lines) — ordered-backend router. Four channels
  (cryptodada / discord / news / llm), each with a primary → fallback
  chain ending in an always-available tail (`none` or `rule_based`).
  Probes are exception-isolated; a broken channel can't crash `doctor`.
- `tests/test_channels.py` (339 lines, 27 tests) — registry shape, probe
  isolation, fallback ordering, each source's "off" state, SKILL.md
  content contract, every new CLI subcommand including `skill --install`
  refusing without `--system`.

**Modified files (additive only):**
- `main.py` (+184 lines) — three new subcommands: `cmd_doctor`,
  `cmd_channels`, `cmd_skill`. Default inspect-only; `--system` required
  for any `$HOME` write.
- `AI_ANATOMY_ROADMAP.md` (+34 lines) — short P7/P8/P9 summary table
  linked to the new planning document.

### Pushed

- Branch `arena/019ff045-sky` pushed to `origin` (set as upstream).
- **No PR opened** (user explicitly chose Option B: leave as branch).
- `main` branch untouched at `99ace0d`.

---

## Currently working on

**Nothing — this session has completed its planned scope (P7 + P8 code
layer).** The next session should start with **P8 dashboard panel**
(see TODO.md item **TODO-1**).

---

## Remaining work (prioritised)

1. **TODO-1** — P8 dashboard "Channels" panel in `web/app.py`
2. **TODO-2** — P9 MCP `tools/list` extension (add `channels`,
   `correlation`, `hidden.*` tools; keep deny list visible)
3. **TODO-3** — P9 CI wheel-gate job in `.github/workflows/`
4. **TODO-4** — P9 `brain/agent.desk_status()` advisory + MCP exposure
5. **TODO-5** — backfill `CHANGELOG.md` (currently stops at v1.3.1;
   repo is at v2.0.0)
6. **TODO-6** — answer the D1–D5 decision list in
   `ROADMAP_AGENT_REACH_UPGRADE.md` §4 (currently unanswered)

Full list and rationale: see [`TODO.md`](./TODO.md).

---

## Current files (added/modified this session)

| File | Status | Lines | Purpose |
|---|---|---|---|
| `SKILL.md` | NEW | 155 | Agent-facing skill file |
| `ROADMAP_AGENT_REACH_UPGRADE.md` | NEW | 348 | P7/P8/P9 plan + risk + rollback |
| `docs/agent_install.md` | NEW | 74 | One-pager for the agent |
| `brain/channels.py` | NEW | 491 | Ordered-backend router |
| `tests/test_channels.py` | NEW | 339 | 27 new tests |
| `main.py` | MODIFIED | +184 | `doctor`, `channels`, `skill` subcommands |
| `AI_ANATOMY_ROADMAP.md` | MODIFIED | +34 | P7/P8/P9 summary |

---

## Known problems / caveats

1. **`CHANGELOG.md` is stale.** The repo's `pyproject.toml` is at
   v2.0.0 but the changelog stops at v1.3.1. **TODO-5.**
2. **D1–D5 decisions in `ROADMAP_AGENT_REACH_UPGRADE.md` §4 are
   unanswered.** User chose full implementation for P7/P8, but the
   sub-decisions (D2: keep `health` and add `doctor` alias vs rename;
   D3: channels scope; D4: wheel-gate CI; D5: install URL exposure)
   need explicit confirmation before P9 coding. **TODO-6.**
3. **Arena's GitHub integration: one PR per chat session** (per Arena
   docs). Don't open multiple PRs from one session. The current session
   pushed without opening a PR (user choice).
4. **`mcp>=1.0` is listed in `requirements.txt` but not installed in
   the local `.venv`** — this is fine because `mcp_server.py` is
   intentionally zero-dependency (uses stdlib JSON-RPC over stdio).
   The `mcp` package is only needed if you want to use the
   `mcp>=1.0` client-side SDK.
5. **Immune system reports `CRITICAL` in `DEMO_MODE=1`** because the
   sample data is stale by design. This is expected and not a bug.
   The `python main.py doctor` command's text output shows the immune
   status for transparency; the channels layer is independent of it.

---

## Next recommended action

**Start the next session with TODO-1: the P8 dashboard "Channels" panel.**

The `brain/channels.py` layer is complete and tested. The remaining
work for P8 is to surface it in the Flask dashboard at `web/app.py` so
an operator can see per-source status at a glance. The
`_sanitize_for_json` regression fix (from `MERGE_NOTES.md`) must be
preserved — any new endpoint that returns numpy scalars from the
quant layer must go through the same sanitizer.

**Suggested next-session prompt:**

> Continue the SKY project from the state in SESSION_STATE.md.
> Implement TODO-1 (P8 dashboard "Channels" panel in web/app.py).
> Read brain/channels.py and web/app.py first. Do not redesign
> completed components. Add a /api/channels endpoint that returns
> the doctor JSON. Add a panel in the dashboard template that
> renders the per-source status. Run `DEMO_MODE=1 python -m pytest
> tests/ -q` — must stay ≥ 285 pass. Add a regression test for
> /api/channels. Update SESSION_STATE.md + CHANGELOG.md. Commit.

---

## Last successful test command

```bash
cd /home/user/SKY
DEMO_MODE=1 python -m pytest tests/ -q
# 285 passed, 1 skipped in 56.80s
```

(The 1 skipped is the SDK-already-installed fallback test, present
since the consolidated build per `MERGE_NOTES.md`.)

## Last commit

```
b0fe82f feat(agent-surface): adopt Agent-Reach patterns (P7/P8)
```

Pushed to `origin/arena/019ff045-sky`. No PR opened.

---

## Start-of-session recipe (paste this when starting a new session)

```
You are continuing development of the existing SKY project at
github.com/Azimshawon/SKY, branch arena/019ff045-sky.

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
- Maintain test count at ≥ 285 pass.
- Update SESSION_STATE.md with completed/current/remaining/known/
  next action.
- Update CHANGELOG.md.
- Commit and push.

If the task is too large for the remaining session, split it into a
safe checkpoint rather than leaving the repository in an undocumented
state.
```

## End-of-session checklist (run before closing this session)

1. [ ] Finish or safely stop the current task.
2. [ ] Run `DEMO_MODE=1 python -m pytest tests/ -q` — must stay
   ≥ 285 pass.
3. [ ] Fix any obvious failures.
4. [ ] Update `SESSION_STATE.md` with the exact current state.
5. [ ] Update `TODO.md` — mark finished items done, reprioritise.
6. [ ] Update `CHANGELOG.md`.
7. [ ] Record all files changed in `SESSION_STATE.md`.
8. [ ] Record the last successful test command.
9. [ ] Record the last commit SHA.
10. [ ] Record any known bugs or unresolved issues.
11. [ ] `git add -A && git commit -m "..."` and
    `git push origin arena/019ff045-sky`.
12. [ ] Only open a PR if the user explicitly says so
    (Arena GitHub limit: one PR per chat session).
