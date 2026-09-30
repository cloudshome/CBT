# CTB Repository — Complete Review & Future Roadmap

**Date:** 2026-09-04 · **Repo:** cloudshome/CBT · **Commit reviewed:** `46c0c87` (main HEAD)
**Scope:** All 19 remote branches + 2 tags, PR/issue/Actions state, full CI-equivalent local run (pytest, ruff, eslint, jest, tsc), security, architecture, and deployment audit.

> Note: the actual project root is `/`. Everything below refers to that tree unless noted.

---

## 🔄 Addendum 2026-09-04 — First CI run enabled, diagnosed, and turned green (new HEAD `e3c59b9`)

This section supersedes the "CI never ran / must be proven in CI" caveats above. GitHub Actions are now **enabled** and the pipeline is **fully green on `main`** for the first time.

**What happened in sequence (this review's verification pass):**
- PR #30 (`fix(ci): relocate .github to repository root…`, branch `arena/01a06bda-ctb`) merged — GitHub then discovered `.github/workflows/ci.yml` **CI Pipeline** and its first-ever run executed on `main` (run `33871777426`) and **failed at the Jest step** (Ruff + 224 pytest + ESLint passed; Docker-compose validation and the build had never run because the job aborted early).
- The sandbox could not read the Actions log (hosted on an Azure blob that is egress-blocked) nor re-run `prisma generate` locally (engine host blocked), so a **temporary diagnostic workflow** mirrored `ci.yml`, ran Jest, and published the full log to a throwaway branch. This surfaced the *real* failures and disproved one false positive:
  - ❌ **False positive** — `tests/frontend_precision_and_kronos` "TS2307 decimal.js": caused by the diagnostic initially omitting the `npm --prefix frontend ci` install step. With frontend deps installed it **passes**. Not a bug.
  - ✅ **Real bug 1 — `tests/readiness.test.ts`** expected `version === '0.1.0'`, but `src/server.ts` reports **`3.0.0`** (test not updated during the v3.0.0 bump). *Fixed in PR #44.*
  - ✅ **Real bug 2 — `GET /api/institutional/dossier` returned 500** whenever live exchange feeds are unreachable **and** the SQLite cache is empty. GitHub-hosted runners are geo-restricted by Binance (HTTP 451) / Bybit (HTTP 403), so `fetchCandlesWithFallback` threw and the handler 500'd before reaching the built-in fallback reference price. The 8-pillar dossier is a deterministic model with hardcoded fallbacks; the handler now catches the fetch failure, degrades to those, and still serves 200. *Fixed in PR #44.*

**Fixes merged → CI green on `main`:** PR #44 (`fix(test): make Jest suite pass in CI…`) merged as `e3c59b9`. The subsequent `main` push run completed **success**: Ruff → **224 pytest** → ESLint → **Jest 20/20 suites, 122 tests** → `docker compose` (both files) validation → full production build. Docker-compose validation and the build are now proven in CI for the first time.

**Branch protection on `main` (requires `Lint, Test & Build`) — NOT ENABLED.** The bot token is not a repo admin (`403 Resource not accessible by integration` for branch-protection endpoints); it *can* push/delete branches/PRs but **cannot** set protection. A human repo admin must run (recommended: require the status check, PRs, linear history):

```bash
gh api -X PUT repos/cloudshome/CBT/branches/main/protection \
  --input - <<'JSON'
{
  "required_status_checks": { "strict": true, "contexts": ["Lint, Test & Build"] },
  "enforce_admins": false,
  "required_pull_request_reviews": null,
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "required_linear_history": true,
  "required_conversation_resolution": true
}
JSON
```

**Housekeeping done this pass:** deleted remote leftover branch `feature/agent-constitution` (its ARCHITECTURE/ROADMAP/SECURITY/AGENTS.md content was already adopted via PR #29).

**Future matters (fresh, now that CI is real):**
1. The single most important un-done step is the branch-protection above — make `Lint, Test & Build` a required check on `main` so the green pipeline is actually enforced.
2. Tests that hit **live Binance/Bybit endpoints** (visible as `console.warn` in `candles`, `dossier`, `sky`, etc.) are inherently flaky/non-deterministic — GitHub runners are geo-restricted (451/403) and rate-limited. Recommend **mocking the market-data layer / seeding SQLite fixtures** in these suites (as `paper`/`paper_error_paths` already do) rather than relying on live feeds.
3. Version drift risk remains: `version` is a hardcoded literal in `src/server.ts` and asserted as a literal in `readiness.test.ts`. Prefer reading `package.json` version at startup and asserting against it, so future bumps cannot silently break `/` again.
4. **Actions deprecation:** Node.js 20 runner actions are deprecated and forced onto Node 24 (warnings on every run). Review and bump `actions/checkout`, `actions/setup-node`, `actions/setup-python` (dependabot PRs #31–#33) — but confirm the major-version targets are valid before merging.
5. **13 open dependabot PRs** (major bumps: numpy 2.x, pandas 3.x, uvicorn, aiohttp, yfinance, pydantic, ruff, scipy, pytest-asyncio, python-multipart, actions). These are large Python dep jumps; CI now exists to gate them — merge carefully and watch the (now-green) pipeline.
6. `main` push also triggers a **Dependabot `github_actions`/"Update" dynamic check** group that currently reports `failure` (npm_and_yarn in `/frontend` and `/`) — unrelated to the app pipeline, but worth reconciling so `main` shows a clean overall Actions surface.
7. Prior-review P0–P3 items still stand where not yet done: tag `v3.0.0-institutional-platform-ready`, delete the remaining ~17 merged branches, create the AGENTS.md-mandated `type:*`/`scope:*` labels, and add `LICENSE`.
8. Low priority now that CI is real: consider a scheduled nightly run (or cron on a `dev` branch) for the burn-in/`pytest` + Jest matrix, and add coverage thresholds as CI gates.

---

## ✅ Implementation status (2026-09-04 — "complete all your findings")

All actionable findings below have been implemented on branch `arena/01a06ba6-ctb`:

- **Branches:** merged `feature/institutional-quant-platform-and-chart-tools` (6 live-data commits, clean merge); adopted ARCHITECTURE/ROADMAP/SECURITY from `feature/agent-constitution`.
- **Correctness:** `np` import in `core/institutional_alpha.py`; missing `Tuple` import in `fvg_engine.py`; missing `time` import in `app.py` (latent 500 on paper trade); `httpx` added to `requirements.txt`; Telegram test made deterministic (offline contract); version aligned to **3.0.0** everywhere.
- **Security:** auth + size limits + risk gate + sanitized UUID upload filenames on research/paper endpoints; Telegram webhook secret verification; `TRUST_PROXY_XFF` gating in both rate limiters; non-root Python container; Caddy healthcheck fixed.
- **Routing parity:** nginx + Caddy now mirror `vite.config.ts` PYTHON_PREFIXES (FastAPI authoritative for the terminal API; Express = readiness/metrics/legacy) — dev/prod divergence removed.
- **Quality gates:** Ruff configured (`pyproject.toml`) and **0 findings** (1,839 originally, incl. 2 more real bugs found); ESLint **0 warnings**; **224 pytest tests pass** (was 201 pass / 1 fail); frontend build green; deprecated `on_event` migrated to lifespan.
- **Governance:** CI pinned deps + `permissions/timeout`; `dependabot.yml`, `CODEOWNERS`, root `AGENTS.md` rewritten as canonical index; systemd conflict documented; docs updated.

**Still requiring human/infra action:** verify CI actually runs (enable GitHub Actions — see §3.1), merge the PRs this turn produces, tag `v3.0.0`, create `type:*`/`scope:*` labels per AGENTS.md, and delete the 17 merged branches.

---

## 1. Executive Summary

| Area | Verdict |
|---|---|
| Architecture vision | Very good — 91 Python quant modules, 12+ institutional layers, Kronos forecasting, provenance/knowledge-graph research lab, strong constitutional docs |
| Branch hygiene | Good — 17/19 branches merged; only 2 pending (1 clean merge, 1 conflict) |
| CI/CD | **Broken/never ran** — GitHub Actions has **0 runs and 0 registered workflows**; every "all gates green" claim in commits is local-only |
| Python tests | 201 passed / **1 failed** on `main` (deterministic); CI would also fail on collection due to missing `httpx` |
| Python lint | Ruff: **1,771 findings** (1,398 auto-fixable; **5 real `F821` bugs**) |
| Node lint/build | ESLint 0 errors (6 warnings). Jest/tsc could not be conclusively verified locally (Prisma engine download blocked) — must be proven in CI |
| Security | **2 High** (unauthenticated file upload with path traversal; unauthenticated Telegram webhook), 4 Medium, several Low |
| Architecture debt | Dual backends (Express + FastAPI) with duplicate routes and **dev/prod routing divergence**; 2,445-line `app.py`; legacy `static/` UI; duplicate AGENTS.md; version/phase-number drift |
| Deployment | Solid Docker + Caddy + systemd footprint, with a few config/healthcheck gaps |
| Docs | Rich (`TODO.md`, `SKY_STATUS.md`, protocols) but duplicated/stale in places; best roadmap (`ROADMAP.md`) is sitting **unmerged** on a branch |

---

## 2. Branch Audit (all branches checked)

**Merged & can be deleted (17):** `feature/init-foundation`, `feature/market-candles-rest`, `feature/market-candles-bybit`, `feature/paper-trading`, `feature/smc-scanner`, `feature/gemini-desk-intelligence`, `feature/desk-terminal-ui`, `feature/pwa-notifications`, `feature/ci-pipeline`, `feature/dockerization`, `feature/final-documentation`, `fix/prisma-docker`, `fix/docker-ts-build`, `fix/nginx-proxy-readiness`, `fix/gemini-types-and-test-stability`, `feature/mtf-primitives`, `feature/institutional-quant-platform-and-chart-tools` (history up to PR #28).

**NOT merged — 2 branches:**

1. **`feature/agent-constitution`** — tip `ba24bd9`, 1 commit, 4 files, +479/−113.
   - Contents: rewritten `AGENTS.md`, new `ARCHITECTURE.md`, `ROADMAP.md` (excellent Gantt vision + Phase 2–5 plan), `SECURITY.md`.
   - ⚠️ `git merge-tree` reports a **content conflict in `Users/azims/CBT/AGENTS.md`** (main added §9 "Surgical Engineering Discipline" in `b21ecf8` after this branch forked). Needs a manual rebase; the 3 new docs are safe to adopt.
   - **Recommendation:** rebase and merge — this is the single most valuable unmerged work (it contains the 5-phase future roadmap the repo lacks in `main`).

2. **`feature/institutional-quant-platform-and-chart-tools`** — tip `283d81b`, 6 commits pushed **after** PR #28 merged (`71406ea` base):
   - `81a5e0c` INTENT-0 standalone asset dossiers (Gold/BTC/ETH/SOL) · `f73f137` ground dossiers in live WebSocket tickers · `25a5a79` live SMCEngine scanner with exact R-multiples for Telegram timeframes · `53c5300` Header Mark Price ↔ Watchlist ticker sync · `fb59fb0` Kronos live-candle probabilistic projection cone · `283d81b` Vite `/api/kronos` → FastAPI proxy.
   - ✅ `git merge-tree` reports **clean merge** into `main`.
   - **Recommendation:** open PR #29 immediately (title: "feat(telegram-ai/kronos): live asset dossiers, live SMC R-multiples, Kronos projection cone").

**Tags:** only `v2.2.0-production-upgrade` and `v2.2.1-liquidation-model-fix` exist. Commit `b8b57d7` says "lock v3.0.0-institutional-platform-ready" but **v3.0.0 was never tagged** — release hygiene gap.

**GitHub state:** 28 PRs, all merged, 0 open · 0 issues · merged branches still exist remotely (clutter) · labels: only GitHub defaults — **AGENTS.md rule 9 requires `type:*` / `scope:*` labels that do not exist**. No dependabot/renovate.

---

## 3. Verification Evidence (what I actually ran)

Environment: Python 3.11.2 (venv), Node 22 / npm 10, fresh `npm ci` (root + frontend), `pip install -r requirements.txt`. ⚠️ `prisma validate/generate` could not run in the sandbox (network blocked to `binaries.prisma.sh`), so TS results below are **unverified against a real generated client** — note them as "must be proven in CI", not as confirmed defects.

### 3.1 GitHub Actions — never ran
```
gh api repos/cloudshome/CBT/actions/runs      → total_count: 0
gh api repos/cloudshome/CBT/actions/workflows → total_count: 0
```
The workflow files exist (`.github/workflows/ci.yml` etc.) but are **not registered/enabled on the repo**. Consequence: every commit message claiming "N passing tests / all 4 preflight gates green / 100% green" has never been validated by CI. This is the single most important process finding.

### 3.2 Python — pytest
- With the exact `requirements.txt`: **11 of 39 test files fail to even collect** — `fastapi.testclient` requires `httpx`, and **`httpx` is missing from `requirements.txt`** (verified: no installed package declares it as a dependency). Clean CI environments will fail here.
- After adding `httpx` manually: **201 passed, 1 failed, deterministic** on `main`:
  - `tests/test_voice_and_telegram.py::test_smart_brain_notification_engine` — asserts `telegram_bot.send_position_alert(...) is True`, but `send_message()` returns `False` when `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` are unset (core/telegram_bot.py:671-674). A test that requires real Telegram credentials in CI can never pass. **Main is not green.**

### 3.3 Python — Ruff
`ruff check core/ tests/` → **1,771 findings**:
`UP006` 703 · `F401` 329 · `UP035` 266 · `UP045` 186 · `I001` 134 · `BLE001` 57 · `F541` 24 · `F841` 17 · `S110` 8 · `F821` 5 (+ smaller counts for SIM/PL/RUF/PIE). 1,398 are auto-fixable (style).

**Real bugs inside the noise — `F821` undefined name `np` (5×) at `core/institutional_alpha.py:264-269`** — `_generate_baseline_candles()` uses `np.random.normal` but the module never imports numpy. This path runs **whenever fewer than 20 candles are supplied** (the documented fallback in `evaluate_alpha`, which backs `/api/institutional/alpha`), so it is a guaranteed `NameError` during any market-data outage. Also `F841` shows dead/broken logic in `core/cvd_absorption.py:61`, `core/debate_committee.py:79`, `core/knowledge_graph_engine.py:495-546`.

### 3.4 Node — ESLint / Jest / tsc
- ESLint: **0 errors, 6 warnings** (`no-explicit-any`) — clean.
- Jest: 20 suites, **13 fail to compile** with `TS7006: Parameter implicitly has an 'any' type` at `src/middleware/riskGate.ts:138` (`.reduce((acc,t)=>…)` over `prisma.paperTrade`) and `src/services/candlesCacheService.ts:63` (`.map((r)=>…)` over `prisma.candlesCache`). These are consistent with an **ungenerated Prisma client** in this sandbox, so treat as unverified — but it also means the repo's Jest/tsc health has **never been demonstrated by CI** (3.1).
- `npm run build` (root): same 3 TS errors locally; unverified in a full-Prisma environment.

### 3.5 Coverage review
- Python: 202 tests / 39 files, but only **48 unique `/api/*` paths are referenced** in tests vs **102 FastAPI routes** — most routes (and most of the 91 core modules) are untested.
- Jest coverage sample: backend `src/` ≈71% stmts, `quantEngine.ts` ≈54%, `riskGate.ts` not even reported — the risk math is the least-tested critical code. No frontend component tests (25 `*.tsx` components are only type-checked).

---

## 4. Security Review (severity order)

### 🔴 High
1. **Unauthenticated arbitrary file write / path traversal** — `POST /api/research/ingest-file` (app.py:1641) has **no auth dependency**, no size limit, and writes `Path(DATA_DIR)/uploads/<file.filename>` using the client-supplied filename directly (`../` and absolute paths escape the upload dir). Any internet caller can write files into the container and force parsing of them.
2. **Unauthenticated Telegram webhook with no secret verification** — `POST /api/telegram/webhook` (app.py:1963) accepts arbitrary updates; Telegram's `X-Telegram-Bot-Api-Secret-Token` is never checked (`grep` found zero implementations). Anyone can inject fake messages/commands/alerts into the bot.

### 🟠 Medium
3. **Unauthenticated mutations** — `/api/research/ingest` (writes vault + may incur LLM cost), `/api/paper/trade`, `/api/paper/close`, `/api/research/candidates/{id}/backtest` (writes DB), all unprotected on FastAPI. This is inconsistent with `/api/shadow/*`, `/api/desk/ask`, `/api/command/parse`, `/api/telegram/broadcast`, `/api/ingest/source`, etc., which use `require_api_key`.
4. **Dev/prod routing divergence (high-impact correctness issue)** — `frontend/vite.config.ts` (`PYTHON_PREFIXES`) routes `/api/paper`, `/api/desk`, `/api/institutional` to **FastAPI :8000**, while `frontend/nginx.conf` and `deploy/Caddyfile` route the same prefixes to **Express :3000**. Consequence:
   - Dev paper trading talks to the FastAPI implementation, which has **no Risk Gate** (`/api/paper/trade` is a direct `portfolio_shadow.open_position` call), bypassing the institutional risk gate the project advertises (rule 3 of the constitution).
   - Prod talks to the Express implementation (risk gate + `apiKeyAuth`).
   - Both backends implement overlapping endpoints (`candles/tickers/mtf/scan/paper/desk/institutional/sky/metrics`) → guaranteed drift; fixes must be duplicated.
5. **Rate limiter trusts client `X-Forwarded-For`** — `core/rate_limiter.py:_resolve_client` uses the first XFF value with no validation; per-IP limits are trivially spoofable if FastAPI is ever reached without a trusted proxy rewriting XFF. (Express `rateLimit.ts` similarly trusts `x-forwarded-for` — verify at lines 45-55).

### 🟡 Low
6. FastAPI Dockerfile runs as **root** (`Dockerfile` has no `USER`; only `Dockerfile.backend` uses `USER node`).
7. `CORS_ORIGIN` default is `*` in both dev and `docker-compose.prod.yml` (overrides allow `*`) — public endpoints callable from any site; key-based endpoints are safe (no cookies/credentials), but defense-in-depth calls for an explicit origin in prod.
8. Caddy healthcheck `wget http://localhost:80/health` hits the **frontend nginx (SPA returns index.html 200)** → always "healthy" even with both backends down. Compose backend healthchecks are fine.
9. No request-body size limits on `/api/voice/transcribe` / `ingest-file` (memory DoS surface, partially mitigated by rate limiting).
10. Pydantic models lack constraints (`PaperTradeRequest.size` can be negative, `sl >= entry` not validated, symbols free-form).

**What is good:** zero secrets in git history (scanned all commits for `AIza…/sk-…/AKIA…/private keys`); constant-time comparisons (`hmac.compare_digest`, `crypto.timingSafeEqual`); dual-tier rate limiting with standard headers; Prisma parameterized queries; OWASP headers in nginx; `.env`/`*.db` excluded via `.dockerignore`; Python SQLite uses parameterized queries (only `PRAGMA user_version` uses int-cast f-string).

---

## 5. Architecture & Code-Quality Findings

1. **Dual backend duplication** — 102 FastAPI routes vs 29 Express routes with overlapping prefixes. The comment header in `vite.config.ts` even claims Node handles routes that the code then routes to Python. Recommend picking one authoritative implementation per endpoint (see roadmap).
2. **`app.py` monolith** — 2,445 lines / 102 routes + startup + models; `@app.on_event("startup")` is deprecated FastAPI API (use lifespan). 91 `core/*.py` modules are imported at startup (import-time side effects, hard to test in isolation).
3. **Legacy duplicate frontend** — `static/index.html` + 29 KB `static/js/chart_engine.js` served at `/` by FastAPI, coexisting with the React PWA. Two UIs to maintain.
4. **Naming/version drift** — FastAPI reports `2.1.0`, Express/package.json `0.1.0`, release lock `v3.0.0` (untagged). TODO.md phase numbering (Phase 10=Voice, 11=Telegram) conflicts with commit messages ("Phase 16 Voice, Phase 17 Telegram"); README says "12-layer", SKY_STATUS says "17-phase".
5. **Two AGENTS.md files** — repo root `AGENTS.md` is a stale template with unfilled Mission/Architecture/install/run/test/contacts; `Users/azims/CBT/AGENTS.md` is the real 11 KB operating manual. Agents can easily read the wrong one.
6. **Frontend dependency smell** — `frontend/package.json` declares `"ctb-terminal": "file:.."` (pulls the whole backend into frontend installs); `grep` shows it is never imported.
7. **Systemd duplication** — `orion.service` (hardcoded `ubuntu`, `/home/ubuntu/CBT/.venv`, uvicorn :8000) and `cbt-stack@.service` (docker compose, also exposes :8000) can conflict if both enabled; `cbt-stack@.service` Documentation URL is wrong (`github.com/CBT`).
8. **Immutability/audit positive** — provenance hashing, audit bus, test-DB isolation via conftest, causal/research firewalls, deterministic sizing and kill-switch claims are real in code, not just docs. Good.

---

## 6. Future Matter — Recommendations (priority order)

### 🔥 P0 — This week (correctness + process before any feature work)
1. **Enable CI and make it required.** Re-register/verify `.github/workflows/ci.yml` (0 runs today), add `httpx` (or use `fastapi[standard]`) to `requirements.txt`, pin `ruff`, and run the pipeline for the first time. Set branch protection so `main` requires it.
2. **Fix the 3 confirmed defects:** add `import numpy as np` to `core/institutional_alpha.py`; fix the Telegram notification test (make `send_message` return `True` (queued) when unconfigured, or mock properly); tag `v3.0.0-institutional-platform-ready`.
3. **Ruff triage:** run `ruff check --fix` (1,398 auto-fixable), then configure for real gates: `select = ["E","F","I"]` + `BLE001/S110/F841/F821` as warnings, and add `F821/BLE001` to the blocking set. CI should not be red on `UP006` style churn while real bugs hide in it.
4. **Merge the 2 pending branches:** open PR #29 from `feature/institutional-quant-platform-and-chart-tools` (clean merge, live-data improvements); rebase `feature/agent-constitution` selectively (keep ARCHITECTURE/ROADMAP/SECURITY, reconcile AGENTS.md §9).
5. **Security burst:** auth + validation on `/api/research/ingest*`, `/api/paper/*`, candidate backtest, and telegram webhook; filename sanitization (UUID + extension allowlist); Telegram `X-Telegram-Bot-Api-Secret-Token` verification; body-size caps; alignment matrix test that dev proxy == prod proxy routing.

### 📈 P1 — Next 2 sprints
6. **Single source of truth:** pick the Express or FastAPI implementation per endpoint (suggest FastAPI for intelligence/research, Express for market/paper — or converge everything onto one), generate an OpenAPI contract, and add a contract/consistency test. This kills the dev/prod divergence class of bugs.
7. **Modularize `app.py`** into `routers/` (market, risk, research, telegram, kronos); migrate to `lifespan`; remove the legacy `static/` UI after confirming nothing external depends on it.
8. **Deployment hardening:** non-root Python container; backend healthchecks for Caddy (probe `/api/readiness` on Express + `/api/health` on Python); trust XFF only from the Caddy network (document/configure); swap `prisma db push` for committed migrations; inject secrets via Docker secrets/env-file; delete or mutually exclude `orion.service`; fix wrong doc URLs.
9. **Test hardening:** add an auth-matrix test (every route × public/private), path-traversal and upload tests, webhook-spoof tests, property-based tests for `quantEngine`/Kelly sizing, and raise coverage gates (≥80% on `src/`, ≥60% on core risk modules). Wire `deploy/staging_burn_in.py` into a nightly CI schedule.

### 🧭 P2 — Mid term (adopt `ROADMAP.md` from the unmerged branch as the canonical plan)
10. **Phase 16 (planned in TODO.md):** Live Canary / Shadow Deployment — automated multi-day burn-in daemon, tick-level telemetry (latency/queue/slippage), CUSUM-based incident response with Telegram escalation. Reuse existing `/metrics` Prometheus + `staging_burn_in.py`.
11. **Storage evolution:** PostgreSQL/TimescaleDB + Redis (queues/cache) — remove SQLite from the hot path; blob storage for uploads (removes the file-write risk surface); keep provenance hashes as the audit anchor.
12. **Live execution phase** (Binance/Bybit private APIs): HMAC/Ed25519 signing, hardware/environment key vault, exchange-side SL/TP manager, circuit breakers, and a human-approval gate as required by the constitution — only after canary evidence.
13. **Observability & SRE:** Grafana dashboards, alerting rules, structured JSON logging, retention/rollup for time-series, backup restore drills (you already have `brain_backup.py` + `restore_databases.py` — test them).

### 🛡️ P3 — Governance & supply chain
14. Add the AGENTS.md-mandated labels (`type:feature`, `type:fix`, `scope:api`, …), `CODEOWNERS`, dependabot for npm/pip, `pip-audit` + `npm audit` + Trivy in CI, and a LICENSE file (currently absent). Merge `SECURITY.md` (on the unmerged branch) and add a security-advisories disclosure path.
15. Delete all 17 merged branches, add `v3.0.0` tag, and adopt a single phase-numbering scheme across TODO.md/commits/docs (one table: roadmap phases ↔ P-series ↔ K-series).

---

## 7. Appendix — Quick Facts

- **Git:** 132 commits, 1 author (`cloudshome`), 2026-08-24 → 2026-09-03; 337 tracked files; ~44k LOC (24.3k Python, ~19.9k TS/TSX); 2 tags; 28 merged PRs; 0 issues/PRs open.
- **Stack:** Python FastAPI + FastAPI-level WebSockets (102 routes) · Node/Express 4 + Prisma/SQLite (29 routes) · React 18 + Vite 6 + Tailwind + lightweight-charts PWA · Docker Compose (python-backend, backend, nginx frontend, Caddy) + systemd alternatives.
- **Tests:** 202 pytest tests (39 files) · 20 Jest suites · ESLint 0 errors · Ruff 1,771 findings.
- **Key files:** `app.py` (monolith), `core/` (91 modules), `core/sky_intelligence/` (18), `core/models/kronos/` (12), `frontend/src/` (25 components), `deploy/`, `TODO.md` (master board), `SKY_STATUS.md` (handoff ledger), `docs/` (research protocol, constitution).

*This review contains no code changes — findings only, ready to be converted into issues/PRs.*
