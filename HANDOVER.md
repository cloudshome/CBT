# SKY — Session Handover

**Read this first if you are the next coding session.**

Last updated: 2026-08-17 · branch `arena/01a00eac-sky` · **P18.2 shipped** —
the versioned `/api/v1` contract is working code + UI (see §1a). P18.1
authentication/authorization shipped in the previous session (see §1).

> **Current direction supersedes the old “two terminal lines” end state.** The
> owner wants installable production software on Ubuntu, Windows (`.exe`), and
> Android (`.apk`) that he can use and monitor without managing source code.
> [`ROADMAP.md`](ROADMAP.md) is now the canonical merged P1–P22 roadmap. The
> current build is still source-installed; do not claim installers exist.
>
> **Next code:** P18.3 persisted background jobs + SSE (long jobs — `backfill`,
> `backtest`, `simulator`, evidence build — still run inside one blocking POST),
> then P18.4 PWA. P18.2 is done: `/api/v1` is stable, so native wrappers now
> have a contract to build against. Chosen topology: one Ubuntu Hub owns
> DB/workers/risk/audit; Windows and Android begin as companion clients.
> Packaging never adds exchange-order code or changes graduation.

---

## 1a. What THIS session shipped — P18.2 stable application API

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

### Priority 0 — P18.3 background job manager and streaming

This is now the top of the queue, and W1 below depends on it.

1. Move long jobs (`backfill`, `backtest`, `simulator`, evidence build) behind
   a **persisted** job queue with status, progress, cancel and audit history.
   They currently run inside one blocking POST behind a timeout.
2. **Server-sent events** for job progress; reconnect resumes from the last
   event rather than restarting work.
3. Only allow-listed jobs and validated arguments — no shell-command endpoint.
   `web/command_center.py` already models the allow-list correctly; extend it,
   do not replace it.
4. **Reuse `web/api_v1.py::IdempotencyStore`** as the deduplication key for job
   submission rather than inventing a second mechanism — duplicate clicks must
   not start duplicate runs, which is the same problem P18.2 already solved.
5. Expose it in the v1 contract (`/api/v1/jobs`…) using the existing envelope
   and error codes, and add the route declarations to `apiv1.ROUTES` so the
   role gate and the published catalog stay in sync.

### Carried-forward W1 — help him actually earn the unlock

This is now the highest-value work, because the Evidence tab makes the gap
visible and the user will immediately want to close it. Everything he needs
exists as separate buttons; what is missing is the **guided run**:

1. A single **"Build my evidence"** flow that chains Backfill → Backtest →
   Simulator → Scorecard with live progress, instead of four separate clicks
   that each block for minutes.
2. Stream the output (SSE) — `backfill` and `simulator` can run for many
   minutes and currently sit behind one blocking POST with only a timeout.
3. Show the **projected** unlock: "at this rate, ~N more simulator rounds".
4. Then, honestly report the result. **If the setups turn out to have no edge,
   say so plainly** — the correct outcome may be "this strategy does not work,
   here is what the data says", not a green bar. Do not tune parameters until
   something passes; that is curve-fitting and `validate lookahead` /
   `scorecard --quality` exist specifically to catch it.

### Priority 1 — finish the chart workstation

1. **Live streaming.** `data/ws_client.py` already exists. Push candle updates
   over SSE or a WebSocket instead of the 30-second poll, and call
   `series.update()` rather than redrawing the whole chart.
2. **Drawing tools** — trendlines, horizontal rays and boxes the user can
   place, persisted per symbol/timeframe (localStorage is fine to start) and
   attachable to the scan record.
3. **Zone overlays** — order blocks, fair-value gaps and liquidity sweeps as
   chart rectangles. The data already exists in `payload["snapshot"]["structure"]`
   and `intelligence.order_block` / `.fair_value_gap`; it is currently only text.
4. **Replay mode** over stored candles, clearly labelled so it can never be
   confused with live or paper evidence.

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

- Server-sent events so slow commands (`backtest`, `simulator`, `backfill`)
  stream output instead of blocking for minutes behind one POST.
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
