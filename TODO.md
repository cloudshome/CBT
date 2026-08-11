# TODO.md — CryptoBrain / SKY

> **Purpose:** the prioritised, actionable list of remaining work.
> Read at the start of every new Arena session (after SESSION_STATE.md).
> Update at the end of every session. Items are ordered by **value
> per session** — top items unlock the most user-visible capability
> for the smallest change.

**Last updated:** 2026-08-11 (post-merge-resolution session)

---

## 🔥 Top priority — start here in the next session

### TODO-0 · Merge PR #5 · https://github.com/Azimshawon/SKY/pull/5

**Status:** READY TO MERGE. PR #5 is now `MERGEABLE` (was `CONFLICTING`).
The user/reviewer just needs to click "Merge" on the GitHub UI.

**What this PR contains:** 11 commits including P7 (agent surface),
P8 dashboard panel + channels router, P9 MCP capability endpoints
(11 read-only tools), and handoff memory files. Conflict resolution
completed in this session (commit `04ac6f9`).

**Once merged:** the next session should branch from `main` (not from
`arena/019ff045-sky`). Update SESSION_STATE.md to point at the new
HEAD on main.

### TODO-1 · P8 dashboard "Channels" panel · `web/app.py` · ✅ DONE (commits `4ca00bb` + `d3a7e8c`)

**Status:** complete in this session.

**What landed:**
- `GET /api/channels` — JSON endpoint wrapping
  `brain.channels.probe_all()`; exception-isolated; goes through
  `_sanitize_for_json` (no numpy-leak 500s).
- `GET /api/doctor` — JSON-wrapped text report (same as `python main.py doctor`).
- Dashboard HTML gained a "CHANNELS — ordered-backend registry (P8)"
  full-width card. JS: `loadChannels()` renders a status pill row
  (one per channel) plus a per-channel backend table with
  `configured / ok / detail / (active)` columns.
- 5-minute separate auto-refresh for the channels panel (vs. the
  30s scan tick) — channels are diagnostic state, not signal state.
- 4 new tests in `tests/test_web_api.py`:
  `test_channels_endpoint_returns_registry`,
  `test_channels_endpoint_is_json_serializable_under_numpy_leak`,
  `test_channels_endpoint_isolates_probe_exceptions`,
  `test_doctor_endpoint_returns_text_report`.
- Test count: 285 → **289 pass / 1 skip** (0 regressions).

**Risk note:** the new panel is "live" but reflects the same
`brain.channels` registry the CLI uses — so what the operator sees
in the dashboard is the same data the agent sees in MCP, and the
same data the CLI prints. No new source of truth, no drift.

### TODO-1.bis · (deferred) dashboard "doctor" view that combines
channels + immune system + risk gate into a single readiness strip at
the top of the dashboard. Out of scope for this session; the
existing `loadHealth()` and `loadRiskGate()` cards already cover
this content (they just don't include the channels layer).

---

## 🟡 P9 — Capability Endpoints (after TODO-1)

### TODO-2 · Extend MCP `tools/list` with the new read-only tools · ✅ DONE

**Status:** complete in this session.

**What landed (TODO-2 commits):**
- `mcp_server.py`: 5 new tools in `ALLOWED_TOOLS` (same
  single-source-of-truth pattern as the existing 6):
  - `channels` — wraps `brain.channels.list_channels(as_json=True)`
  - `correlation` — wraps `engine.correlation.fetch_report`
  - `hidden_chart_read` — wraps `engine.hidden_alpha.hidden_alpha_report`
  - `hidden_analytics_mae` — wraps `brain.analytics.mae_mfe_summary`
  - `hidden_analytics_mc` — wraps `brain.analytics.monte_carlo_equity`
- `SERVER_VERSION` bumped `1.0.0 → 1.1.0` (capability-surface bump).
- New docstring on the deny list — it now names the forbidden tools
  (`approve | reject | execute | close | place_order | sign | withdraw
  | transfer`) so the next person to edit the file knows the
  invariant.
- `tests/test_mcp_stdio.py`: `ROOT_TOOLS` extended; 6 new tests:
  - `test_root_mcp_channels_tool`
  - `test_root_mcp_correlation_tool`
  - `test_root_mcp_hidden_chart_read_tool`
  - `test_root_mcp_hidden_analytics_mae_tool`
  - `test_root_mcp_hidden_analytics_mc_tool`
  - `test_root_mcp_deny_list_still_enforced` (8 forbidden names
    checked both in `tools/list` AND by direct call)
- `SKILL.md` tool table: 5 new MCP names filled in (was `—`).
- Test count: 289 → **295 pass / 1 skip** (0 regressions).

**Live verification:** spawned `mcp_server.py` as a subprocess, did
`initialize` + `tools/list` (11 tools returned), called all 5 new
tools (all returned clean data), called 4 forbidden tools (all
rejected with "not permitted").

### TODO-3 · CI wheel-gate job · ⏸️ BLOCKED

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

**Blockers (per Session 2026-08-11 #4, TODO-2 self-reflection):**
1. **D4 decision unanswered** — wheel-gate yes/no is a sub-decision
   in `ROADMAP_AGENT_REACH_UPGRADE.md` §4.
2. **Arena GitHub integration cannot push under `.github/workflows/`.**
   The existing `ci.yml` lives at `docs/.github/workflows/ci.yml`
   for exactly this reason (per the `d40ff00` commit note). A
   human with the `workflows` permission must activate it from the
   GitHub UI before the wheel-gate job can run on GitHub Actions.
3. **No `pyproject.toml`** — TODO-3's scope itself flags this as
   a sub-decision.

**Status as of end of TODO-2 session:** this session attempted to
do TODO-3 (per the user's "if this session cover todo3, than go
for it" instruction). The three blockers above mean TODO-3 is
NOT cleanly coverable in a single Arena session. The user's
fallback ("els stop and end this session and make PR before end
this") was applied: the session stopped, this TODO.md note was
added, and a PR was opened from `arena/019ff045-sky` → `main` to
consolidate the P7/P8/P9 work that's already done.

**TODO-3.bis (future session):** once D4 = yes, a future session
can write the wheel-gate job *content* (e.g. as a Python script
in `ci/wheel_gate.py` that runs locally + a `ci.yml` job spec for
GitHub Actions). The actual push to `.github/workflows/` is a
human action — TODO-7.

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
