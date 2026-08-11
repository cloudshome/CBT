# SESSION_STATE.md — CryptoBrain / SKY

> **Purpose:** the *single* handoff file a new Arena session reads first
> to resume work without re-deriving context. **Update at the end of
> every session** (see "End-of-session checklist" at the bottom).
> **Read first** at the start of every new session (see "Start-of-session
> recipe" at the bottom).

**Last updated:** 2026-08-11 (end of TODO-1 session)
**Branch:** `arena/019ff045-sky`
**HEAD commit:** `4ca00bb feat(dashboard): P8 Channels panel + /api/channels + /api/doctor (TODO-1)`
**Default branch:** `main` (last commit `99ace0d`, untouched this session)
**Python:** 3.10+ tested on 3.10–3.13 + Windows (per existing CI)

> **Self-reflection — lesson from the start of this session:**
> the previous session's SESSION_STATE.md said "Last commit: `b0fe82f`"
> but the actual HEAD was already `498d753` (the docs commit landed
> after SESSION_STATE.md was written). The handoff memory went stale
> *inside the same chat* and a fresh session would have had to
> reconcile it. **Rule for this and every future session: update
> SESSION_STATE.md at the START, not just at the end.** This file
> was rewritten to reflect HEAD `498d753` before TODO-1 began, and
> again at the end of this session to reflect the TODO-1 commit.

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
| **P8** | **Source Channels (router)** | **✅ Complete** | `brain/channels.py` + `/api/channels` + dashboard "Channels" panel + `/api/doctor` |
| P9 | Capability Endpoints (extended MCP + CI wheel-gate) | ⏳ Not started | See `ROADMAP_AGENT_REACH_UPGRADE.md` §6 |

Full phase matrix: [`AI_ANATOMY_ROADMAP.md`](./AI_ANATOMY_ROADMAP.md).
Full P7/P8/P9 plan with risk + rollback: [`ROADMAP_AGENT_REACH_UPGRADE.md`](./ROADMAP_AGENT_REACH_UPGRADE.md).

---

## Completed work

### Session 2026-08-11 #1: P7 + P8 code layer — commit `b0fe82f`

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

### Session 2026-08-11 #2: Handoff memory — commit `498d753`

4 files, +849 lines of documentation, **0 code changes**, **0 test impact**,
tests stayed at **285 pass / 1 skip**.

**New files:**
- `SESSION_STATE.md` (256 lines) — handoff memory + start-of-session
  recipe + end-of-session checklist.
- `TODO.md` (156 lines) — prioritised TODO-1..TODO-7.
- `ARCHITECTURE.md` (266 lines) — module map + 10 invariants + data
  flow + config + testing cheatsheets.
- `CHANGELOG.md` (171 lines) — v2.0.0 + v2.0.1 + Unreleased.

### Session 2026-08-11 #3: TODO-1 P8 dashboard panel — commit `<new-sha>`

3 files changed, **0 regressions**, tests **285 → 289 pass / 1 skip**.

**Modified files (additive only):**
- `web/app.py` — two new endpoints (`/api/channels`, `/api/doctor`),
  new full-width dashboard "CHANNELS" card, new `loadChannels()` JS,
  new 5-minute diagnostic auto-refresh. Docstring endpoint list updated.
- `tests/test_web_api.py` — 4 new tests covering: registry shape,
  numpy-leak safety, probe-isolation, doctor text output.

**Also updated (docs):**
- `TODO.md` — TODO-1 marked done; TODO-1.bis noted as deferred.
- `CHANGELOG.md` — v2.0.2 entry added; Unreleased updated.
- `SESSION_STATE.md` — current state, last commit, last test count
  all updated.

### Pushed

- All three commits on `arena/019ff045-sky` pushed to `origin`.
- **No PR opened** (user explicitly chose Option B: branch only).
- `main` branch untouched at `99ace0d`.

---

## Currently working on

**Nothing — this session (TODO-1) is complete.** P8 is now fully
shipped: code layer (`brain/channels.py`) + CLI surface
(`python main.py doctor | channels`) + dashboard panel
(`/api/channels` + "CHANNELS" card). The next session should start
with **TODO-2: extend MCP `tools/list` with the new read-only
tools** (see TODO.md).

**Self-reflection on scope:** I almost scoped-crept this session —
there was a temptation to also add TODO-1.bis (the combined
readiness strip combining channels + immune + risk gate) because
it would be visually nicer. I did NOT do that because:
- it is a *different* change with a *different* definition-of-done;
- TODO-1.bis is a polish item, not a P8-closure item;
- bundling it would have made this commit harder to review and the
  handoff less clean.

**Rule going forward:** if the user says "go next" they mean "the
next item in TODO.md", not "the next thing you can think of".

---

## Remaining work (prioritised)

1. **TODO-2** — P9 MCP `tools/list` extension (add `channels`,
   `correlation`, `hidden.*` tools; keep deny list visible)
2. **TODO-3** — P9 CI wheel-gate job in `.github/workflows/`
3. **TODO-4** — P9 `brain/agent.desk_status()` advisory + MCP exposure
4. **TODO-5** — `CHANGELOG.md` is no longer stale (this session
   added v2.0.0, v2.0.1, v2.0.2 entries). Marked ✅ done in TODO.md.
5. **TODO-6** — answer the D1–D5 decision list in
   `ROADMAP_AGENT_REACH_UPGRADE.md` §4 (currently unanswered)
6. **TODO-7** — activate GitHub Actions CI from the UI

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

1. **`CHANGELOG.md` is no longer stale.** v2.0.0 + v2.0.1 + v2.0.2
   entries added across the two prior sessions; pre-2.0.0 history
   cross-referenced to MERGE_NOTES.md. Marked done in TODO.md.
2. **D1–D5 decisions in `ROADMAP_AGENT_REACH_UPGRADE.md` §4 are
   unanswered.** User chose full implementation for P7/P8, but the
   sub-decisions (D2: keep `health` and add `doctor` alias vs rename;
   D3: channels scope; D4: wheel-gate CI; D5: install URL exposure)
   need explicit confirmation before P9 coding. **TODO-6.**
3. **Arena's GitHub integration: one PR per chat session** (per Arena
   docs). Don't open multiple PRs from one session. All three
   sessions this far pushed without opening a PR (user choice).
4. **`mcp>=1.0` is listed in `requirements.txt` but not installed in
   the local `.venv`** — this is fine because `mcp_server.py` is
   intentionally zero-dependency (uses stdlib JSON-RPC over stdio).
   The `mcp` package is only needed if you want to use the
   `mcp>=1.0` client-side SDK.
5. **Immune system reports `CRITICAL` in `DEMO_MODE=1`** because the
   sample data is stale by design. This is expected and not a bug.
   The `python main.py doctor` command's text output shows the immune
   status for transparency; the channels layer is independent of it.
6. **Arena's GitHub integration cannot push under `.github/workflows/`**
   (per the `d40ff00` commit note in the consolidated build's
   history). The `ci.yml` workflow file lives at the right path
   but the workflow itself must be activated from the GitHub UI
   by a human with the `workflows` permission. **TODO-7.**

---

## Next recommended action

**Start the next session with TODO-2: extend MCP `tools/list` with
the new read-only tools (`channels`, `correlation`, `hidden.*`).**

P8 is fully closed: code layer + CLI + dashboard panel + tests +
docs. P9 starts with extending the MCP tool surface. The
`mcp_server.py` deny list (`approve | reject | execute | close |
place_order`) must remain intact — only read-only tools are added.

**Suggested next-session prompt:**

> Continue the SKY project from the state in SESSION_STATE.md.
> Implement TODO-2 (extend MCP tools/list with channels,
> correlation, hidden.* tools). Read mcp_server.py first. Do not
> touch the deny list. Add 5 new tools. Update SKILL.md tool table.
> Add tests in tests/test_mcp_stdio.py. Run the full suite — must
> stay ≥ 289 pass. Update SESSION_STATE.md + CHANGELOG.md. Commit.

---

## Last successful test command

```bash
cd /home/user/SKY
DEMO_MODE=1 python -m pytest tests/ -q
# 289 passed, 1 skipped in 56.10s
```

(The 1 skipped is the SDK-already-installed fallback test, present
since the consolidated build per `MERGE_NOTES.md`.)

## Last commit

```
4ca00bb feat(dashboard): P8 Channels panel + /api/channels + /api/doctor (TODO-1)
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
