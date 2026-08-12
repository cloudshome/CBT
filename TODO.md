# TODO.md — CryptoBrain / SKY

> **Purpose:** the prioritised, actionable list of remaining work.
> Read at the start of every new Arena session (after SESSION_STATE.md).
> Update at the end of every session. Items are ordered by **value
> per session** — top items unlock the most user-visible capability
> for the smallest change.

**Last updated:** 2026-08-12 (session `arena/019ff483-sky` — TODO-4 + D1–D5 + wheel-gate)

---

## 🔥 Top priority — start here in the next session

### TODO-7 · Activate GitHub Actions CI · human action

The workflow file lives at `.github/workflows/ci.yml` and now includes
a `wheel-gate` job. Arena's GitHub integration may still lack the
`workflows` permission (per commit `d40ff00`). A human with that
permission must confirm the workflow is enabled in the GitHub UI
(Actions tab → CI → Enable, or re-commit the file from the UI).

Until then, run the gate locally:

```bash
python ci/wheel_gate.py            # build + duplicate-entry check
python ci/wheel_gate.py --install  # also smoke-test a clean venv
```

### TODO-1.bis · (deferred) dashboard "doctor" view

A single readiness strip at the top of the dashboard combining
channels + immune system + risk gate. Out of scope this session;
`loadHealth()`, `loadRiskGate()`, `loadChannels()`, and the new
`loadDesk()` cards already cover the content separately.

---

## ✅ Done this session (2026-08-12)

### TODO-4 · `brain/agent.desk_status()` advisory · ✅ DONE

**What landed:**
- `desk_status()` + `format_desk_status()` in `brain/agent.py`
- `next_scheduled_agent()` in `brain/agents.py`
- CLI: `python main.py desk` / `desk --json`
- MCP tool `desk_status` (`SERVER_VERSION` 1.1.0 → 1.2.0)
- Dashboard: `GET /api/desk` + "DESK STATUS" card on the System tab
- `ask("what should I do?")` routes to the same snapshot
- Tests: agent / agents / mcp / web / CLI / dashboard-js

Advice is priority-ordered and capital-first:
`CLEAR_STATE → STAND_ASIDE → REVIEW_QUEUE → JOURNAL → PAPER_GRIND → SCAN`.

### TODO-6 · Answer D1–D5 · ✅ DONE

Recorded in `ROADMAP_AGENT_REACH_UPGRADE.md` §4:

| ID | Answer |
|---|---|
| D1 | full P7 (already shipped) |
| D2 | keep `health`, add `doctor` alias (already shipped) |
| D3 | 3 data sources + LLM only (already shipped) |
| D4 | **YES** — wheel-gate |
| D5 | **YES** — expose `docs/agent_install.md` raw URL |

### TODO-3 · CI wheel-gate content · ✅ DONE (activation = TODO-7)

- `pyproject.toml` (package `cryptobrain` v2.1.0, console script)
- `cryptobrain/__init__.py` facade so `import cryptobrain` works
- `ci/wheel_gate.py` — build, reject duplicate zip entries, optional
  `--install` smoke test (`import cryptobrain` + `cryptobrain doctor`)
- `wheel-gate` job added to `.github/workflows/ci.yml`
- `tests/test_wheel_gate.py`

### TODO-0 · PR #5 · ✅ MERGED

Merged 2026-08-11 (`4216448`). This session branched from that HEAD.

### TODO-1 · P8 dashboard Channels panel · ✅ DONE (prior session)
### TODO-2 · MCP capability endpoints · ✅ DONE (prior session)
### TODO-5 · CHANGELOG backfill · ✅ DONE (prior session; v2.1.0 added this session)

---

## 📋 Decisions waiting on user

None. D1–D5 are recorded. Remaining human action is TODO-7
(enable the GitHub Actions workflow from the UI if the token
cannot push under `.github/workflows/`).

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
