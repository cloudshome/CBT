# TODO.md — CryptoBrain / SKY

> **Purpose:** the prioritised, actionable list of remaining work.
> Read at the start of every new Arena session (after SESSION_STATE.md).
> Update at the end of every session. Items are ordered by **value
> per session** — top items unlock the most user-visible capability
> for the smallest change.

**Last updated:** 2026-08-12 (TODO-1.bis readiness strip shipped)

---

## 🔥 Top priority — start here in the next session

### TODO-11 · Prove the paper book · next *code* item

The engine, the agent surface, and the readiness surface are all
done. The thing that is **not** done is the only thing that unlocks
real capital: `python main.py desk` still says `PAPER_GRIND` because
graduation needs 100 unique backtest samples, 20 decided paper
samples, positive expectancy, > 55% win rate, PF ≥ 1.5, and ≥ 90%
rule compliance.

Next session should grind and harden that path, not add more AI
wrapping:

```bash
python main.py simulator          # unique-sample grind
python main.py desk               # watch the graduation line move
```

Concretely: run the grind to a real 100/20, journal the closed
trades so `compliance` stops being `None`, and fix whatever the
graduation report reveals. Do **not** add new agents or panels.

### TODO-7 · Activate GitHub Actions wheel-gate · human action

The job spec sits at **`docs/.github/workflows/ci.yml`**, which is
**inert** — nested under `docs/`, so GitHub Actions never reads it.
Only the repository-root `.github/workflows/ci.yml` is executed, and
Arena's GitHub App token cannot write that path (push rejected twice:
`d40ff00`, and again this session's predecessor).

A human with the `workflows` permission pastes the `wheel-gate` job
from the GitHub UI. Click-path: [`docs/HUMAN_ACTIONS.md`](docs/HUMAN_ACTIONS.md).

Until then, run the gate locally:

```bash
python ci/wheel_gate.py            # build + duplicate-entry check
python ci/wheel_gate.py --install  # also smoke-test a clean venv
```

### TODO-8 · Protect `main` · human / repo admin

GitHub reports `main.protected = false`. Arena token gets HTTP 403
on the branch-protection API. Click-path is in
[`docs/HUMAN_ACTIONS.md`](docs/HUMAN_ACTIONS.md).
A trading risk-calc change must never land on `main` unreviewed.

---

## ⏸ Parked — do not start until the gate says so

Full rationale: [`docs/INFRASTRUCTURE_LAYERS.md`](docs/INFRASTRUCTURE_LAYERS.md).

### TODO-9 · Dify as a *separate* research layer · AFTER graduation

Not a SKY dependency. Deploy Dify elsewhere and point it at SKY's
read-only surfaces (`desk`, `readiness`, `ask`, MCP). Start only when
`python main.py agent ask "am i ready for micro?"` reports READY.

### TODO-10 · LibreChat-style chat UI · AFTER TODO-9

Not a SKY dependency. The dashboard already exists. Only if a
multi-model chat panel is still wanted after Dify.

---

## ✅ Done this session (2026-08-12 · `arena/019ff4c3-sky`)

### TODO-1.bis · combined dashboard doctor strip · ✅ DONE

One readiness verdict across channels + immune system + risk gate,
rolled up **worst-first** (`ok → degraded → blocked → down`).

**What landed:**
- `brain/agent.readiness_strip()` + `format_readiness_strip()`, with
  `_channels_pillar()` / `_immune_pillar()` / `_gate_pillar()` each
  exception-isolated.
- CLI: `python main.py doctor --strip` (+ `--json`); plain `doctor`
  now leads with the strip; `doctor --json` gained a `readiness` key.
- `GET /api/readiness` (never 500s — degrades to a JSON error).
- MCP tool `readiness`; `SERVER_VERSION` 1.2.0 → 1.3.0 (13 tools).
- Dashboard: colour-coded strip above **every** tab, one chip per
  pillar, refreshed on the 5-minute diagnostic cadence.
- Docs: SKILL.md, README, ARCHITECTURE (new invariant #10 "one
  computation, many surfaces"), AI_ANATOMY_ROADMAP, CHANGELOG.
- Version 2.1.0 → **2.2.0**.
- Tests 324 → **337 pass / 1 skip** (+13).

---

## ✅ Done in prior sessions

- **TODO-4** `desk_status()` advisory (v2.1.0)
- **TODO-6** D1–D5 answered — `ROADMAP_AGENT_REACH_UPGRADE.md` §4
- **TODO-3** wheel-gate *content* (`ci/wheel_gate.py`, `pyproject.toml`)
- **TODO-0** PR #5 merged; **PR #6** merged 2026-08-12
- **TODO-1** P8 dashboard Channels panel
- **TODO-2** MCP capability endpoints
- **TODO-5** CHANGELOG backfill

---

## 📋 Decisions waiting on user

| ID | Decision | Default |
|---|---|---|
| TODO-7 | Paste the wheel-gate job into the real `.github/workflows/ci.yml` | human |
| TODO-8 | Protect `main` (require PR, no direct push) | human / recommend yes |

D1–D5 are already recorded. Do **not** start TODO-9/TODO-10 this
session or the next.

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
- Vendoring / forking / `pip install` of **OpenHands, Dify, or
  LibreChat** into this repo. Study patterns only. See
  `docs/INFRASTRUCTURE_LAYERS.md`.
- Splitting the desk into new "Market Analyst / Risk Manager /
  News Analyst / Code Maintenance" agents. The four existing desk
  agents + `desk_status()` + `readiness_strip()` already cover that job.
- A *fourth* readiness surface. Channels, immune, gate, desk advice,
  and the strip are enough; anything new reads `readiness_strip()`.
