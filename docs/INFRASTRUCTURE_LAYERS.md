# Infrastructure layers — what matters for SKY

> **Purpose:** distill the OpenHands / Dify / LibreChat / Freqtrade /
> Backtrader discussion into *this* repository's terms. Read once. Do
> not re-derive next session.
> **Last updated:** 2026-08-13

**One rule:** these projects are **not** dependencies of SKY and
must never be vendored, forked-into, or `pip install`ed here.

They are *layers around* SKY — or, in Freqtrade's and Backtrader's
case, a *different product* we are not becoming:

| Layer | Project | Role for SKY | When |
|---|---|---|---|
| Development agent | Arena.ai (already) | Writes code on `arena/*` branches | Now |
| Engineering patterns | OpenHands (study only) | Plan → tool → test → commit → PR | Extract ideas, never copy |
| Knowledge / research | Dify | RAG + research workflows *around* the engine | After graduation *and* P10 |
| Chat UI | LibreChat | Human control panel | After Dify |
| Trading bot | **Freqtrade** | None. SKY is the brain; Freqtrade places orders | **Never** — see `docs/FREQTRADE_REVIEW.md` |
| Research backtester | **Backtrader** | None as a dependency. Its discipline (expectancy, WF/OOS, MC, regime matrix) is already P12 on our grader | **Never** — see `docs/BACKTRADER_REVIEW.md` (BT1–BT8) |

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
NOW     P10.7 → P10.12 · Own the data (cross-exchange, charts, WS, store-backed backtest)
ALONG   P11 · Prove the edge (simulator / paper / graduation gate) — do not move the bar
THEN    P12 · SKY Quant Validation Engine on OUR backtester + OUR store
              (walk-forward / lookahead / quality score / conditioned + net-of-costs
               expectancy / risk-of-ruin — per both review docs)
AFTER   Dify as a *separate* research layer (never imported by the engine)
LAST    LibreChat-style chat UI, if the dashboard is not enough
NEVER   Freqtrade / Hyperopt / FreqAI / Backtrader / signed order APIs
```

Promotion to Dify requires the existing graduation gate
(`python main.py agent ask "am i ready for micro?"`) to pass.
Not before.

**P10 still sits ahead of Dify and of P12's heavy items.** Owning our
market data moves the aim — a fully independent trader — because it
turns a 500-candle amnesiac scan into years of queryable evidence.
Another chat layer, or another bot framework, over the same thin data
moves nothing. Data first, validation second, wrappers last, bots never.

---

## Human actions this token cannot do

1. **Protect `main`.** GitHub reports `protected: false`. The Arena
   token gets HTTP 403 on the protection API. A repo admin should
   enable: require PR, no direct push, require status checks once
   CI is active (TODO-7).
2. **Activate CI / paste the wheel-gate job** into the real
   `.github/workflows/ci.yml`. The spec sits at
   `docs/.github/workflows/ci.yml`, which is **inert** — nested under
   `docs/`, so GitHub Actions never reads it (TODO-7).

Tracked as TODO-8 and TODO-7 in [`TODO.md`](../TODO.md).
