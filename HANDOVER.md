# SKY — Session Handover

**Read this first if you are the next coding session.**

Last updated: 2026-08-18 · **v2.40.0 — P22.3 signing + clean-target drills** (`docs/HANDOVER_2026-08-18_P22_3.md`). Catalog + fail-closed evidence. No signed installer claimed. Next: run drills on trusted hosts. No threshold moved; no order path.

> **Current direction supersedes the old “two terminal lines” end state.** The
> owner wants installable production software on Ubuntu, Windows (`.exe`), and
> Android (`.apk`) that he can use and monitor without managing source code.
> [`ROADMAP.md`](ROADMAP.md) is the canonical merged P1–P22 roadmap. The current
> build is still source-installed; do not claim installers exist.
>
> **Next code:** P22.2 native Windows/Android projects, then trusted signing
> and clean physical-target drills. P22.1 release metadata/CI/diagnostics is
> shipped; P21 Android + P20 Windows remain contracts and unsigned recipes.
> Chosen topology: one Ubuntu Hub owns DB/workers/risk/audit; browser/PWA,
> Windows and Android are companion clients. Packaging never adds
> exchange-order code or changes graduation.

## Next session — start here

> **Triage durable (2026-08-18):** `docs/CHATGPT_6IDEA_TRIAGE_2026-08-18.md` is still the `6-idea -> Take/Park/Reject` decision — `P18.4` already satisfied `*02/#3 + *05 compact` as shell-only PWA; `*01/*04/*06` stay parked as external labs after `P19+graduation`. **Do not re-triage, do not add torch/OpenDataLoader/LMRing deps.**

**P19–P22.3 are done as source contracts (v2.35.0–v2.40.0).** Sign and
physically drill only in the trusted release environment. Do not mark P22
complete from catalog JSON or Linux CI. P11 paper grind stays parallel.

Two things to carry into P19:

- **Never cache private payloads in the package either.** The `sw.js` never-caches `/api/*`, auth, SSE, private state or mutations; the Hub's reverse proxy and any backup tool must also never capture `data/cryptobrain.db` or `data/store/**` as world-readable artifacts.
- **The served-script trap.** `web/app.py`'s `HTML` is a plain (non-raw) Python string: a backslash escape written inside the embedded JavaScript is eaten by Python before the browser sees it. Use `String.fromCharCode(10)` for a newline. `tests/test_dashboard_js.py::test_served_script_is_valid_javascript` and `tests/test_pwa.py::test_html_still_valid_js` now parse the *evaluated* template — keep them.

Optional P18.4 polish (not P19): designed icons (replace solid-color placeholders in `web/static/icons/`), iOS `navigator.standalone` handling, push VAPID wiring.

---

## 1b. What THIS session shipped — W2 (part 2): live streaming + drawing tools

Working code + UI. Full contract:
[`docs/HANDOVER_2026-08-17_W2_part2.md`](docs/HANDOVER_2026-08-17_W2_part2.md).

- **`web/live_stream.py` + `GET /api/chart/stream`** — SSE frames of the newest
  bar for one symbol/timeframe, polled from the same source `/api/chart` uses.
  Cadence clamped to 2–15 s; a failing source emits an `error` frame and backs
  off instead of dropping the connection; every frame is a full snapshot with an
  `id:`, so a reconnect resumes with no server-side cursor. Behind the P18.1
  auth gate.
- **◉ Live toggle** — the browser calls `series.update()` in place (no rebuild,
  so zoom/overlays/zones/drawings survive) and the status line always says which
  of *off / connecting / live / waiting / stale / feed error / disconnected* is
  true. Foreign symbols and older bars are dropped; the stream follows the
  selected series and stops when replay starts.
- **Drawing tools** — ╱ Trend, ─ Ray, ▭ Box, ⌫ Undo, 🗑 Clear, a MY DRAWINGS
  list with per-item delete, and 📎 Attach to journal note (the human still
  picks the trade and saves). Marks snap to the nearest loaded bar and persist
  in `localStorage` per symbol + timeframe; corrupt storage is discarded.

### 1d. The bug this build caught: the dashboard was dead in real browsers

`HTML` in `web/app.py` is a plain (non-raw) triple-quoted Python string. The
P18.3/W1 job-log line contained a literal `'\n'`, which Python turned into a
real newline **inside a JavaScript string literal** — a `SyntaxError` that
disabled the entire inline script in any browser. Every JS check (both test
harnesses and CI) extracted the script from the *file text*, so none of them
could see it. Fixed with `String.fromCharCode(10)`, plus a new test and a CI
step that parse the evaluated template Flask actually serves.

Suite: **1053 passed / 1 skipped** (+23).

---

## 1c. Consolidated W1 — guided “Build my evidence” flow

The W1 implementation from PR #51 is the retained safety boundary. Full
contract: [`docs/HANDOVER_2026-08-17_W1.md`](docs/HANDOVER_2026-08-17_W1.md).

- **Fail closed before persistence.** Composite inputs reject unknown fields,
  unsupported choices, non-positive integers and oversized values. Expanded
  children are validated again through the same allow-list before execution.
- **One coherent run.** Asset/timeframe propagate through Backfill, Backtest and
  Simulator; market/history, backtest bars and simulator rounds reach their
  applicable steps. Explicit defaults and `{}` deduplicate identically.
- **Inline persisted progress.** The Evidence tab streams the four-step job in
  place and reconnects to an active evidence job after reload; it does not
  redirect the user to Command center.
- **Observed, honest projection.** Recent successful simulator/evidence log
  additions establish the aggregate pace. With no observations the estimate is
  `unknown`; zero additions with an outstanding gap is `stalled`; no fixed or
  invented sample yield is presented as fact.
- **Explicit no-edge result.** Once sample floors are met, absent/non-positive
  net expectancy is reported as `no_edge`, with a direct warning not to tune
  parameters merely to turn the result green. Graduation and risk gates remain
  separate and unchanged.

---

## 1d. What THIS session shipped — W2 (part 1): zone overlays + replay mode

Working code + UI. `web/chart_data.py` (`_zones` + `build_chart` "zones"),
`web/app.py` (Zones toggle + `drawZones` + replay controls), `tests/test_chart_data.py`
(new) and +2 tests in `tests/test_workstation_js.py`. Full contract:
[`docs/HANDOVER_2026-08-17_W2.md`](docs/HANDOVER_2026-08-17_W2.md).

- **Zone overlays.** `payload["snapshot"]["structure"]` (order blocks, fair-value
  gaps, buyside/sellside liquidity, sweeps, premium/discount dealing range) was
  text-only on the chart. `_zones` turns it into JSON-safe bands; the chart's
  "Zones" toggle draws each as paired top/bottom price lines — bullish green,
  bearish red, **dashed once tested/broken/filled** — plus liquidity lines and a
  highlighted sweep. Nothing invented; every level is engine-computed.
- **Replay mode.** A ▶ Replay button walks the already-loaded candles bar-by-bar
  (`series.setData` on a growing slice, no network, no new endpoint), with a
  1×–4× speed toggle and an unmissable "▶ REPLAY — historical playback, not
  live" badge so it can never be read as live or paper evidence.

> **Flagging honestly (per §0a):** no browser was opened in this sandbox — the
> zones and replay were verified through the node/jsdom harness (real dashboard
> JS against a stubbed chart library), the Flask test client, and a direct
> `build_chart` run on real engine structure output; the pixel look of the
> bands was not eyeballed. Zones render as paired price lines (Lightweight
> Charts v4 has no rectangle primitive). Drawing tools and live streaming are
> NOT here — see §4 of the W2 doc for the honest boundary.

---

## 1b. What THIS session shipped — P18.3 background jobs + SSE

Working code + UI. New module `web/jobs.py` (stdlib only), `web/app.py`
integration, one new `jobs` table in `data/database.py`, `tests/test_jobs.py`
(23 tests) and a clickable Background-jobs panel + one-click “Build my
evidence”. Full contract:
[`docs/HANDOVER_2026-08-17_P18_3.md`](docs/HANDOVER_2026-08-17_P18_3.md).

- Long jobs (`backfill`, `backtest`, `simulator`, `scorecard`, derivatives /
  cross collect, and the composite `evidence` Backfill→Backtest→Simulator→
  Scorecard) now run behind a **persisted queue** in the server process — a
  browser close cannot kill them, and status/progress/log survive a reload or
  a server restart (orphaned `running` rows are marked `interrupted`, never
  silently re-run).
- **Allow-list + validated args only** — always `python main.py <validated
  argv>`, never a shell string; `web/jobs.build_argv` reuses the Command
  Center's validation so the two share one allow-list.
- **Deduplication** — `params_hash = sha256(kind + canonical params)`; a
  duplicate click while a job is live returns the existing run instead of
  starting a second one.
- **Cancel** — queued jobs cancel outright; running jobs get a cancel request
  (SIGTERM→SIGKILL); finished jobs refuse.
- **SSE** — `GET /api/v1/jobs/<id>/events` streams full state snapshots
  (`event: job`), one terminal frame then close; reconnect resumes from the
  persisted state. New v1 typed codes `JOB_NOT_FOUND` / `JOB_NOT_CANCELLABLE`,
  routes declared in `apiv1.NATIVE_ROUTES` so the role gate and the published
  catalog stay in sync (path templates like `/jobs/<job_id>` now match).
- **UI** — Command center gained a Background-jobs panel (status badges,
  cancel, live streamed output); slow `🟠` commands submit jobs instead of
  blocking; the Evidence tab gained one-click “Build my evidence”.

> **Flagging honestly (per §0a):** no browser was opened in this sandbox — the
> UI was verified via jsdom + the Flask test client + a live `curl` smoke test
> (job submitted, ran in DEMO mode, streamed its log, SSE framed and closed),
> not by a human clicking. Within-step progress is whatever the command
> prints (mostly a final summary); only the *step* progress of the `evidence`
> composite is genuinely fractional — I did not fake a percentage.

---

## 1a. What the previous session shipped — P18.2 stable application API

Working code + UI. New module `web/api_v1.py` (stdlib only), `web/app.py`
integration, one new table in `data/database.py`, `tests/test_api_v1.py`
(59 tests) and 4 new dashboard-JS tests. Full contract:
[`docs/HANDOVER_2026-08-17_P18_2.md`](docs/HANDOVER_2026-08-17_P18_2.md).

- **One envelope** for every `/api/v1` response —
  `{ok, data, error{code,message,details}, meta{api_version, server_version,
  request_id, ts}}`. Legacy `/api/*` keeps its old shapes so the shipped
  dashboard does not break mid-migration (pinned by a test).
- **Typed error codes** (`ErrorCode`): clients branch on `error.code`, never on
  wording, and **never on terminal text**. The desk's deliberate refusals keep
  their own codes — a closed gate is `RISK_GATE_CLOSED` (409) carrying the
  structured `blocked_by` reasons.
- **Compatibility:** `GET /api/v1/version` is public (a client must discover
  the range before it can authenticate) and publishes min/max client versions.
  An out-of-range `X-SKY-Client-Version` gets `CLIENT_TOO_OLD`/`CLIENT_TOO_NEW`
  with an upgrade message — checked **before** auth, so an old app never shows
  the user a spurious "wrong password".
- **Idempotency keys** on `review` / `journal` / `paper/run` / `trader-state`.
  A retry replays the stored response (`meta.idempotent_replay: true`) instead
  of re-applying; four identical approvals write exactly **one** `decisions`
  row (test), with a no-key control proving the endpoint is not merely harmless
  to repeat. Same key + different body → `IDEMPOTENCY_KEY_REUSED`.
- **Device registration/revocation** as a stable contract plus `/api/v1/me`,
  `/api/v1/audit` and a machine-readable `/api/v1/routes` catalog.
- **UI:** System-tab card showing the version range, capability flags and the
  route catalog — including an honest ✗ for `live_exchange_execution`.
- **Security inherited, not re-implemented.** The P18.1 gate already covers
  `/api/`; v1 refusals are just rendered in the v1 envelope. Every P18.1
  invariant is re-asserted against the new surface — and **an operator still
  cannot bypass the risk gate**.

> **Flagging honestly (per §0a):** no real companion client exists yet, so the
> contract is proven against `curl`, the Flask test client and the node/jsdom
> harness — not against a real Windows or Android app, and not by a human
> looking at a browser (none is installable in this sandbox). P20/P21 will be
> the first true consumers. Also: `min == max == 1` today, so the upgrade paths
> are exercised with synthetic version headers rather than a genuinely old
> client.

---

## 0a. How the owner wants you to communicate (he asked for this explicitly)

**Tell him what you are uncertain about, and say when you disagree.**

He specifically asked that this be carried forward:

> "Two things I want to flag honestly … also this type thought and suggestion
> pass for next session."

So, in every session:

- **Flag what you could not verify.** Example from this session: no browser is
  installable in the sandbox, so the UI was verified through `jsdom` rather
  than by looking at it. Say that plainly instead of implying you saw it work.
- **Say when you think a request is a bad idea, and why — then offer the safer
  version.** Example: he asked for "all" real-world connections including full
  trading keys. The right answer was to build 1–3 (live data, alerts, LLM,
  read-only account) and *decline* live execution, because SKY has no proven
  edge yet. He accepted that reasoning. Do not silently do the risky thing just
  because it was asked for, and do not silently skip it either — explain.
- **Do not overstate.** "Tests pass" is not "this is profitable". Distinguish
  *the software works* from *the strategy makes money*. Those are different
  claims and only the first one is currently true.
- **Volunteer the caveat he did not ask for** when it materially affects money
  or safety. He has said he values this.

He is deferential when you give him a real reason ("do whatever good for our
aim and goal"), so the reasoning matters more than the recommendation.

---

## 0. The one thing to understand about this project

The owner has asked, repeatedly, for the same thing:

> "I need an interface where all functions, modules, CLI commands and every
> piece of information are visible openly, and I can click like a website —
> like Binance or TradingView."

**Do not answer that request with a roadmap, a CLI explanation or a plan.**
Previous sessions did that and it was the wrong answer. The deliverable is
always *working, clickable UI shipped in the browser*. If you find yourself
writing "the next implementation should…", stop and implement it instead.

The user's entire intended workflow is two lines:

```bash
cd ~/SKY
python3 main.py     # then open http://localhost:8050
```

Everything else must be reachable by clicking.

---

## 1. What this session shipped

### P18.1 — authentication & authorization (this session's main deliverable)

Working code + UI, not a plan. New module `web/auth.py` (stdlib only) plus
`web/app.py` integration, `data/database.py` schema additions, and
`tests/test_auth.py` (17 security tests).

- **First-run owner creation** with PBKDF2-HMAC-SHA256 (260k iter) hashed
  passwords; constant-time verify; only hash+salt stored.
- **Roles:** `viewer` (read dashboards/evidence/health/paper state) and
  `operator` (viewer + approve/reject/execute/close). No role grants live
  execution (no order path exists).
- **Sessions & devices:** signed httpOnly/SameSite=Lax cookie sessions with
  absolute+idle expiry; revocable, **scoped** bearer device tokens for
  companion clients (a viewer-scoped token cannot act as operator).
- **CSRF** on every cookie-authenticated mutation (a fetch wrapper injects
  `X-CSRF-Token`), **login throttling** (username+IP lockout),
  **logout-all-devices**, and an **audit row per sensitive action**
  (`audit_log` table; viewable in the Account panel).
- **Remote guard:** `web/auth.enforce_deployment` refuses to bind non-loopback
  without an owner account **and** a TLS proxy (`SKY_TRUSTED_PROXY_IPS`) unless
  `SKY_ALLOW_REMOTE_NO_TLS=1`.
- **The review endpoint can no longer bypass the risk gate.** Force-approve is
  disabled unless `SKY_ALLOW_FORCE_APPROVE=1`, and always audited.
- **Activation model:** `SKY_AUTH_MODE` = `auto` (auth on once owner exists) |
  `required` | `disabled`. `auto` is the default so existing local use stays
  simple but locks the moment an owner is created.
- **UI:** first-run "create owner" screen, sign-in screen, top-bar user chip
  with role badge, and an ⚙ Account panel (change password, device list with
  create/revoke token, audit log for operators).

Auth is per `config.DB_PATH` (tables: `users`, `sessions`, `device_tokens`,
`audit_log`, `login_attempts`, `auth_meta`), idempotently migrated. The session
secret auto-persists next to the DB; set `SKY_SECRET_KEY` for multi-process.

### The chart is fixed and real

- **Serialization bug (the reported one) is fixed.** `/api/candles` used to
  pass raw `df.to_dict("records")` to Flask. A Pandas/NumPy scalar (`int64`,
  `float64`, `NaT`, `NaN`) makes `jsonify` raise `TypeError`, so the endpoint
  500'd and the page showed analysis cards with **no chart**. All values now
  go through a single `_num()` funnel in `web/chart_data.py`.
- **The stub is gone.** `web/static/lightweight-charts.standalone.js` was a
  hand-written stub that explicitly said "replace with the full production
  build". It is now the genuine **TradingView Lightweight Charts v4.2.3
  production build** (164 KB, Apache-2.0), vendored so it works offline.
- **New `Chart` tab** — candles, volume, RSI and MACD panes with linked time
  scales, EMA 20/50/200, VWAP, Bollinger, support/resistance/pivot lines and
  entry / stop / take-profit overlays. Every overlay is a checkbox.

### Every function is a button

| Tab | File / endpoint |
|---|---|
| 📊 Chart | `web/chart_data.py` → `GET /api/chart` |
| 🎛 Trade manager | `GET /api/trades` |
| 🛡 Risk center + sizer | `web/position_sizer.py` → `POST /api/position-size` |
| 📓 Journal form | `GET/POST /api/journal` |
| ⌘ Command center | `web/command_center.py` → `GET /api/commands`, `POST /api/commands/run` |
| 🧩 Modules | `GET /api/modules` |

All 55 CLI commands are now documented, clickable cards with inputs, a Run
button and their output shown in the page.

### Safety model (do not weaken this)

- `web/command_center.py` is an **allow-list**: only catalog ids run,
  arguments are built as an argv list (never a shell string), inputs are
  type-checked, every run has a timeout, and `watch` / `paper --watch` / `mcp`
  are `safety="blocked"` because they never exit.
- `web/position_sizer.py` caps risk at the progression ladder and returns
  **zero size** plus the blocking reason when the risk gate is closed.
- There is no exchange API key anywhere in this app. No real order can be
  placed. Keep it that way.

### Real-world connections (second half of this session)

The owner asked for real connections, not demo data. Shipped:

- **`brain/connections.py`** — a registry of every real-world link (market
  data, derivatives, news, Fear & Greed, macro, dominance, Telegram, Discord,
  LLM, exchange account). Each entry states what it *gives* you, what it
  *needs*, and step-by-step how to switch it on. All probes are read-only,
  parallel, individually timed out and exception-isolated.
- **`data/exchange_account.py`** — a **READ-ONLY** Binance account client:
  real balance and real open orders. GET-only, allow-listed endpoints, no
  `requests.post` anywhere in the file (a test enforces this), and it refuses
  to accept a key carrying trade/withdraw permission without flagging it.
- **`output/notifiers.py::send_test_alert`** — the Connections tab's
  "Send me a test alert" button, so the user can confirm alerts actually reach
  their phone.
- **🔌 Connections tab** with a live/not-live badge and a Test button per card.
- **`CONNECT_REAL_WORLD.md`** — the same steps in writing.

### The gate ("it blocks nearly everything")

That complaint was fair as *UX*, not as behaviour. The gate is correct — SKY
has no proven edge — but "blocked" with no path forward reads like a bug.
Shipped:

- **`brain/unlock.py`** — turns every `blocked_by` string into a plain-language
  explanation, a progress bar (current vs target), and a clickable next action.
  It distinguishes `earn` blocks (accumulate evidence) from `wait` blocks
  (daily limit resets, clear a trader-state flag).
- **🔓 Evidence tab** — "why you cannot trade right now", a 4-step
  one-click **evidence pipeline** (Backfill → Backtest → Simulator →
  Scorecard/Look-ahead), and a per-setup scoreboard.
- Verified end-to-end that this is a *real* path, not decoration: with
  110 backtest + 22 paper winning samples the bars go 0% → 50% → 100% and
  `risk_gate.evaluate()` flips to `allowed=True`. With *losing* samples the
  floors are met but expectancy fails and it correctly stays blocked.

**I did NOT loosen any threshold.** The 100/20/positive-expectancy bar is
unchanged. Do not lower it to make the desk feel more active — that would be
selling the user a worse system that merely feels better.

### Tests

`tests/test_workstation.py` (18), `tests/test_workstation_js.py` (15) and
`tests/test_connections.py` (23). The JS tests execute the real dashboard
JavaScript in node against stubbed APIs and assert each panel paints actual
numbers.

```bash
DEMO_MODE=1 python -m pytest -q          # 910 pass
```

Three failures are **pre-existing and environmental**, unrelated to this work
(verified by stashing the changes): `test_agent.py::test_health_report_ok` and
two `test_mcp_server.py` tests fail because the `mcp` package is not installed
and the sandbox has no outbound network.

---

## 2. Your job next session

> **2026-08-17 (update):** P18.1 (§1) **and** P18.2 (§1a) are shipped. Next is
> **P18.3** from `ROADMAP.md` — persisted background jobs + SSE. The
> workstation W1–W4 items below remain companions, integrated through the
> secured API/job foundation; they no longer precede it. Deliver working
> UI/code after each roadmap checkpoint.

Build these **as working UI**, not as a second roadmap.

### ~~Priority 0 — P18.2 stable application API~~ → **DONE** (v2.30.0)

All six sub-items shipped; see §1a and
[`docs/HANDOVER_2026-08-17_P18_2.md`](docs/HANDOVER_2026-08-17_P18_2.md).

### Priority 0 — P18.3 background job manager and streaming — ✅ SHIPPED this session

See §1b and
[`docs/HANDOVER_2026-08-17_P18_3.md`](docs/HANDOVER_2026-08-17_P18_3.md).

1. ✅ Long jobs run behind a **persisted** queue with status, progress, cancel
   and (audit rows for submit/cancel). No more blocking POST.
2. ✅ **SSE** (`/api/v1/jobs/<id>/events`); reconnect resumes from persisted
   state.
3. ✅ Allow-list + validated args only — `web/jobs.py` extends, does not
   replace, `web/command_center.py`'s allow-list.
4. ✅ Deduplication via `params_hash` (natural) on top of the v1 idempotency
   contract — duplicate clicks do not start duplicate runs.
5. ✅ Exposed in the v1 contract (`/api/v1/jobs`…) with the existing envelope
   and error codes; routes declared in `apiv1.NATIVE_ROUTES` (not `ROUTES`,
   because they are v1-native with no legacy equivalent) so the role gate and
   catalog stay in sync.

**Not shipped (honest):** live candle/health SSE (Priority 1 below) and the W1
projection UX — both are separate follow-ups that now have a layer to build on.

### Carried-forward W1 — ✅ shipped v2.32.0

The guided Evidence flow is complete: selected asset/timeframe/market/history
propagate through the four validated child jobs; progress and log stream inline
and restore after reload; observed unique-sample additions produce a caveated
round projection; and a completed sample bar with non-positive net expectancy
is reported as **no positive edge**, never tuned into a green result. See
`docs/HANDOVER_2026-08-17_W1.md`.

### Priority 1 — finish the chart workstation

1. **Live streaming.** `data/ws_client.py` already exists. Push candle updates
   over SSE or a WebSocket instead of the 30-second poll, and call
   `series.update()` rather than redrawing the whole chart.
2. **Drawing tools** — trendlines, horizontal rays and boxes the user can
   place, persisted per symbol/timeframe (localStorage is fine to start) and
   attachable to the scan record.
3. ✅ **Zone overlays** — order blocks, fair-value gaps, liquidity and sweeps
   as chart bands (shipped this session — §1d, `docs/HANDOVER_2026-08-17_W2.md`).
4. ✅ **Replay mode** over stored candles, clearly labelled so it can never be
   confused with live or paper evidence (shipped this session — §1d).

### Priority 2 — the weekly trader review

`python main.py agent weekly-review` exists and is already a button, but its
output is plain text in a `<pre>`. Turn it into a page: equity curve, R-multiple
distribution, violations, expectancy, drawdown and the next practice task, with
an export.

### Priority 3 — real-life training workflow

The user explicitly asked for this and it is not built yet. Design it as a
guided, stateful flow in the browser:

- a **daily ritual checklist** that remembers what you completed today;
- a **graduation tracker** per setup showing the exact missing evidence;
- **enforced journalling** — block the next approval while a closed trade is
  unjournalled (`brain/journal.py::graduation_discipline` already computes this);
- a practice mode that scores the user's own read against the desk's.

### Priority 4 — polish

- ~~Server-sent events so slow commands stream output instead of blocking for
  minutes behind one POST~~ → **done** (P18.3).
- Stale-data age badge on every market card.
- Mobile compact mode for the ritual and approval flow.
- ~~Optional auth before the dashboard is exposed beyond localhost~~ → **done**
  (P18.1). Beyond localhost now *requires* auth + TLS proxy.

---

## 3. How to work on this repo

```bash
# run it (DEMO_MODE=1 makes it fully offline; drop it for live Binance data)
DEMO_MODE=1 python main.py web --host 0.0.0.0 --port 8050

# tests
DEMO_MODE=1 python -m pytest -q
DEMO_MODE=1 python -m pytest tests/test_workstation.py tests/test_workstation_js.py -q
```

### Things that will bite you

- **The dashboard HTML is one big Python string** (`HTML = """…"""` in
  `web/app.py`, ~2000 lines). `tests/test_dashboard_js.py` extracts the last
  `<script>` block and runs `node --check` on it, so a syntax error fails CI
  rather than silently blanking the page. Inside that string, write newlines in
  JS as the `nl` variable, never `\n`.
- **Flask's `jsonify` is strict.** Any NumPy/Pandas scalar raises. Always route
  payloads through `_sanitize_for_json()` (web/app.py) or `_num()`
  (web/chart_data.py). This is the bug that broke the chart; do not reintroduce it.
- **`SignalDB.get_scan()` returns a flat SQL row**, but the analysis helpers
  expect the nested scan payload. Use `_scan_row_to_payload()` in `web/app.py`.
- **No network in the sandbox** except the npm registry. Binance calls fail, so
  use `DEMO_MODE=1`. Vendor front-end assets from
  `https://registry.npmjs.org/<pkg>/-/<pkg>-<version>.tgz`.
- **No browser is installable** in the sandbox (Playwright's download is
  blocked). To verify UI, use `jsdom` (`npm i jsdom` in a temp dir) and drive
  the real page against the running server — that is how this session confirmed
  every panel renders with zero JS errors.
- Adding a CLI command? Add it to `COMMANDS` in `web/command_center.py` too,
  or it will not appear as a button. `test_command_catalog_is_complete_and_documented`
  guards the important ones.

---

## 4. Message to carry into the session after next

If the workstation work above is done, the remaining arc is **evidence, not
features**. SKY still has no proven edge: the risk gate correctly refuses
almost everything because no setup has met the 100-backtest / 20-paper bar with
positive net expectancy.

So the next-next session should resist adding surface area and instead:

1. Backfill real history (`backfill`), then grade it (`backtest --source store`).
2. Run the simulator to accumulate honest samples per setup.
3. Use `scorecard --quality` and `validate lookahead` to check the edge is real
   and not curve-fit.
4. Only then discuss graduating a single setup from research to micro size.

**Never** connect real exchange trading keys, never present simulator output as
proof of profitability, and never let the UI bypass the risk gate. The point of
this system is to make the user a disciplined trader, not to promise profit.

### On the trading-keys question specifically

He has already asked for "all" real-world connections, including live trading.
This session built live market data, alerts, LLM and a **read-only** account,
and declined live execution with the reasoning in §0a. He accepted that.

Expect the question again. The answer is not "never" — it is **"not until the
evidence exists"**, and the Evidence tab now shows exactly how far away that is.
The preconditions, in order:

1. At least one setup genuinely proven (100 backtest / 20 paper / positive net
   expectancy) — not one you tuned until it passed.
2. A clean `validate lookahead` and a decent `scorecard --quality` (an edge that
   only exists at one parameter setting is not an edge).
3. A sustained live-paper run with journalling discipline near 100%.
4. Then: a **new, separate** execution module — never an extension of
   `data/exchange_account.py` — with per-order human confirmation, a hard
   position cap, and a kill switch. Start at a size where a total loss is
   genuinely irrelevant to him.

If he pushes to skip straight to step 4, say plainly what the expected outcome
is. That is the single most consequential moment in this project, and being
agreeable there would be doing him real harm.
