# Infrastructure layers — what matters for SKY

> **Purpose:** distill the OpenHands / Dify / LibreChat discussion into
> *this* repository's terms. Read once. Do not re-derive next session.
> **Last updated:** 2026-08-12

**One rule:** these three projects are **not** dependencies of SKY and
must never be vendored, forked-into, or `pip install`ed here.

They are *layers around* SKY, in this order:

| Layer | Project | Role for SKY | When |
|---|---|---|---|
| Development agent | Arena.ai (already) | Writes code on `arena/*` branches | Now |
| Engineering patterns | OpenHands (study only) | Plan → tool → test → commit → PR | Extract ideas, never copy |
| Knowledge / research | Dify | RAG + research workflows *around* the engine | After graduation (Phase 7) |
| Chat UI | LibreChat | Human control panel | After Dify (Phase 8) |

Persistent memory is **this GitHub repo** (commits + `SESSION_STATE.md`
+ `TODO.md` + tests). Nothing else "hacks" an Arena session limit.

---

## What SKY already has (do not rebuild)

OpenHands' loop is `plan → tool → workspace → execute → test → git → PR`.
SKY already has the trading-engine equivalent:

| OpenHands idea | SKY already |
|---|---|
| Typed tool permission map | `mcp_server.ALLOWED_TOOLS` + deny list |
| Sandboxed / safe execution | `DEMO_MODE`, paper-only runner, no exchange-order code |
| Action / Observation | `desk_status()`, `doctor`, `health`, `risk` |
| Event / audit log | `agent_runs`, `decisions`, journal |
| Specialized agents | `morning_brief`, `watchdog`, `paper_reviewer`, `weekly_review` |
| Test-then-commit | 320 pass / 1 skip, offline |
| Branch-not-main workflow | `arena/*` → PR → `main` |
| Handoff memory | `SESSION_STATE.md` (this *is* `PROJECT_STATUS.md`) |

Do **not** add a Market-Analyst / Risk-Manager / News-Analyst / Code-
Maintenance agent split. The four desk agents + `desk_status()` already
cover that job. A sixth agent that writes code is Arena itself.

---

## What is *not* worth copying

- OpenHands Docker sandbox / CodeAct / agent-server — SKY is a signal
  engine, not a general coding agent.
- Dify as an in-process dependency — would wrap an engine that is still
  in `PROGRESSION=student/simulator`.
- LibreChat inside `web/app.py` — the dashboard already exists.
- "Install all three so Arena has permanent memory" — false. Memory is
  GitHub. Dify only helps if *you* deploy it and point SKY at it later.

---

## Order of work (do not skip ahead)

```
NOW     Arena + GitHub + this repo's tests + desk_status
NEXT    Prove the edge (simulator / paper / graduation gate)
THEN    Dify as a *separate* research layer (never imported by the engine)
LAST    LibreChat-style chat UI, if the dashboard is not enough
```

Promotion to Dify requires the existing graduation gate
(`python main.py agent ask "am i ready for micro?"`) to pass.
Not before.

---

## Human actions this token cannot do

1. **Protect `main`.** GitHub reports `protected: false`. The Arena
   token gets HTTP 403 on the protection API. A repo admin should
   enable: require PR, no direct push, require status checks once
   CI is active (TODO-7).
2. **Activate CI / paste the wheel-gate job** into
   `.github/workflows/ci.yml` from `docs/wheel-gate-job.yml` (TODO-7).

Tracked as TODO-8 and TODO-7 in [`TODO.md`](../TODO.md).
