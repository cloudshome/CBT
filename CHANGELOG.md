# Changelog

## [2.57.0] — 2026-08-22 · P13.5 — Monte-Carlo stability floor on decisive windows

MAJOR (research/validation): the edge verdict now resamples the decisive-window
net R series and applies a **Monte-Carlo stability floor** as a confirm
condition. The 5th-percentile bootstrap expectancy must be > 0 or the edge is
rejected — a book that is net-positive in the mean but has a fat left tail
(one bad streak from negative) no longer gets EDGE_CONFIRMED. Read-only, no
threshold moved, no order path, no graduation change.

- **`engine/edge_validation.py::monte_carlo_decisive()`** — resamples the
  decisive-window decided plans' net R series (bootstrap with replacement,
  configurable samples / risk_pct / ruin_threshold / seed). Reports:
  expectancy p5/p50/p95, drawdown median/p95, ruin probability, probability
  terminal equity below start, terminal equity p5/p50/p95, longest loss streak
  p50/p95.
- **`edge_verdict()` — Monte-Carlo floor.** When MC data is available and
  `monte_floor=True` (default), the 5th-percentile net expectancy must be > 0.
  A failing MC floor produces NO EDGE with a clear reason string. `monte_floor=
  False` disables the floor for review/exploration. MC unavailable (< 2
  decided trades) falls through to the basic rules.
- **`edge_validate_report()` — `monte` / `monte_samples` / `monte_risk_pct` /
  `monte_seed`** parameters. When `monte=True`, runs the MC and passes the
  block into the verdict. The MC result is available in the `monte` key of the
  returned report and in `edge["monte"]`.
- **`format_edge_verdict()` — MONTE CARLO block.** Prints the full MC table
  (trades, samples, risk, expectancy p5/p50/p95, drawdown, ruin prob, equity
  range, loss streak, MC floor pass/fail) when MC is available.
- **CLI: `python main.py edge-validate --monte`** — enables MC. Plus
  `--monte-samples`, `--monte-risk-pct`, `--monte-seed` knobs. Default is
  `--monte` off (same as pre-P13.5 behaviour) so existing invocations and the
  graduation gate are unaffected.
- **Tests:** 16 new regressions (`tests/test_edge_validation_monte.py`) —
  minimum-trades guard, structure, seed determinism, strong/losing book p5,
  undecided exclusion, risk-scales-drawdown, net R drives equity, MC confirms
  strong book, MC floor rejects fragile book, no-MC backward compatible,
  monte_floor=False opt-out, unavailable MC falls through, end-to-end with/
  without --monte, format with/without MC block.
- **Verification:** full suite **1375 passed / 1 skipped**; wheel gate green
  (`cryptobrain-2.57.0-py3-none-any.whl`, no duplicate entries).

## [2.56.0] — 2026-08-22 · P13.4 — backtest walk O(N²) eliminated

MAJOR: the backtester and simulator no longer re-run the full indicator suite
from bar 0 at every walk step. Indicators are precomputed once over the whole
series and each bar is analyzed through the new windowed `analyze_frame_at`;
the structure detectors are vectorized in place and the per-trade funding
lookup is cached per 8h bucket. **Behaviour-identical** by construction and by
test (16,575 graded rows byte-identical old-vs-new). Measured: **5.7× on 500
bars, 7.9× on 2000, ~200× on a 10k-bar walk** (est. 2h+ → ~40s). No threshold
moved, no exchange-order path.

- **Precompute + windowed walk** (`engine/signal_engine.py::analyze_frame_at`,
  `data/backtester.py`, `data/simulator.py`) — `add_all_indicators` runs once;
  per bar, structure looks at its tail(200), divergence tail(80), regime
  tail(20) and the snapshot at the last two rows + prefix length, so each
  step is O(lookback) instead of O(i).
- **Vectorized structure detectors** (`engine/structure.py`) — FVG fill and
  order-block tested/broken use reversed cummin/cummax instead of per-event
  tail scans; swings/liquidity read numpy arrays (identical results, verified
  against the pre-change detectors on 33 windows).
- **Funding lookup cache** (`data/costs.py`) — one store read per (symbol, 8h
  bucket) instead of per graded trade; the funding series is static during a
  backtest, so the cached value is the identical row.
- **Verification** — equivalence harness proves byte-identical graded rows,
  detectors and per-bar features/plans/structure/scores; suite 1238 passed /
  1 skipped locally (110 pre-existing JS-harness failures on Node v20 —
  `navigator` undefined, also failing on the pristine tree; CI's Node v22 is
  unaffected).

## [2.55.0+research] — 2026-08-22 · P13 Edge Validation — plan + first code (no version bump)

PATCH-free research/validation addition on top of v2.55.0 (no user-facing
version change, no threshold moved, no order path). Origin: the strategic
second opinion on the Accio review (`docs/STRATEGIC_CONSIDERATION_2026-08-22.md`)
and the P13 milestone spec (`docs/P13_EDGE_VALIDATION_SPEC.md`).

- **`engine/execution.py` — model reconciliation.** The config-declared
  `EXECUTION_MODEL` set `none | slip | impact` now actually works: previously
  only `"simple"` applied the fill model, so `slip`/`impact` silently produced
  zero slippage. Now `slip` / `impact` / `simple` enable it; `none` (and only
  `none`) opts out. The graduation gate and default backtest stay on `none`.
- **`engine/edge_validation.py` (new) + `python main.py edge-validate`.** An
  honest, regime-aware edge verdict — **EDGE CONFIRMED / NO EDGE /
  INSUFFICIENT_DATA** — computed on the **sealed OOS + recent** windows (the
  slices the walk never tuned on), segmented by market regime, all net of
  costs. Read-only: never places an order, never moves a threshold, never
  unlocks micro-live. Flags: `--execution none|slip|impact`, `--json`,
  `--min-decided`, `--regime-min-decided`, `--positive-regime-frac`,
  `--decisive-windows`, store/live source.
- Regressions: `tests/test_edge_validation.py` (11) + 2 execution-alias tests.
  Full suite **1359 passed / 1 skipped**. Contract:
  `docs/HANDOVER_2026-08-22_EDGE_VALIDATION.md`.


## [2.55.0] — 2026-08-21 · T6 — focused pages + mobile sections · T1–T6 complete

MINOR: the last Trade Terminal phase. Every nav area is now a **focused page**
(identity header + sub-section switcher, exactly one section at a time) and
phones get a four-section bottom bar with the paper ticket as a full-screen
sheet. Purely presentation: **zero new endpoints**, same `onTabShown()`
loaders, no threshold moved, no exchange-order path.

- **Focused pages** — Markets (Overview / Market radar / Intelligence),
  Portfolio (Positions / Decisions / Risk centre / Weekly review), Journal,
  Evidence (Evidence / Learning), System (Data health / Connections /
  Hub & agent / Command centre / Modules). One `.tabpanel` active at a time;
  sub-choice persists per browser with a safe fallback; every section is
  `#section` deep-linkable (init resolves a section hash to its owning page).
- **Backwards-compatible routing** — every old `switchTab(name)` call
  (quickbar, coach, deep links) lands on the right focused page+section;
  `render()`'s re-apply can never navigate the user off their page on a
  refresh. `NAV_TABS` removed — `AREA_SUBS` is the single section↔area map.
- **Mobile four-section bar** — Markets / Chart / Positions / AI (Copilot
  drawer), with active-state tracking that clears as you move on; full
  seven-area top nav remains, so no surface is amputated on small screens.
- **Ticket sheet** — on phones the paper ticket opens as a full-screen sheet
  from `🎫 Ticket` in the chart toolbar (backdrop / ✕ / area-switch closes
  it), and opening it **re-reads the risk gate fresh** (`/api/risk`, chip +
  ticket). Confirm still re-reads the gate on the server before enrolling.
- Regressions: `tests/test_focused_pages_js.py` (14 tests). Full suite
  **1348 passed / 1 skipped**; served-script `node --check` clean; wheel gate
  green; `config.VERSION` = `pyproject.toml` = `sky-shell-v2.55.0` lockstep.
  Contract: `docs/HANDOVER_2026-08-21_T6.md`.

## [2.54.0] — 2026-08-21 · T5 — Home screen & onboarding

MINOR: the post-login landing is now a concise command dashboard with one
primary door into the Trading Terminal, and a fresh desk gets onboarding that
points at the paper loop — never at a CLI. Purely presentation: **zero new
endpoints** (the board composes the existing read-only `/api/risk`,
`/api/readiness`, `/api/trades`, `/api/loop-health` payloads), no threshold
moved, no exchange-order path, no new permission.

- **Home command dashboard** — first nav area, and the landing when no hash or
  remembered view exists. Hero (time-of-day greeting, the paper-first
  one-liner), **Continue ‹symbol · timeframe›** (remembered market, validated
  against what the server still offers) and **Open Trading Terminal ⟶** as the
  primary button.
- **Seven concise cards, not every module** — Risk gate (real `blocked_by`
  reasons when closed), Data freshness (readiness level + data-pillar line,
  incl. P10.5 quarantine), Open positions (count + live R rows), Today's P&L
  (net % of equity, decided count, hard daily limit, amber limit warnings),
  Journal tasks (missing journals with the journal-first hold named, pending
  reviews, the daily question), Evidence progress (criteria x/4 or
  `GRADUATION READY`, real paper n, the unmoved bar, per-primary-setup sample
  rows), and Focus (the desk's advice action/headline + trader-state flags).
- **Honest states** — skeletons on first paint; every feed settles
  independently so a dead endpoint paints an explicit `could not load — retry`
  in its own card while the rest of the board renders; every visit re-reads
  (no one-shot cache); 60 s refresh while Home is visible. The board never
  POSTs.
- **Onboarding** — shown only for a fresh desk (no real paper trades, nothing
  open, nothing pending, not dismissed): five steps — open terminal → read the
  setup → prepare the paper ticket → confirm (paper only) → manage & journal —
  with the same primary CTA. Dismissal persists per browser; a private-mode
  browser still runs.
- Regressions: `tests/test_home_js.py` (8 tests — landing, card painting,
  blocked-gate/journal-first reasons, dead-feed retry, onboarding + dismiss,
  terminal navigation + remembered market, served markup). Full suite
  **1334 passed / 1 skipped**; served-script `node --check` clean; wheel gate
  green; `config.VERSION` = `pyproject.toml` = `sky-shell-v2.54.0` lockstep.
  Contract: `docs/HANDOVER_2026-08-21_T5.md`.

## [2.53.0] — 2026-08-20 · T4 (part 2) — resizable/collapsible panels, layout memory, connection state, tooltips, mobile

MINOR: the Trade Terminal becomes a workspace you can shape and it never
freezes silently. Purely presentation — no threshold moved, no new endpoint,
no exchange-order path. Every change is wrapped so a private-mode browser
(localStorage throwing) still runs, and the jsdom/CI harness is unaffected.

- **Resizable panels** — drag gutters between the watchlist ↔ chart, chart ↔
  order ticket, and chart ↔ bottom panel. Widths/height are CSS variables
  written live during the drag (charts re-measure in place); double-click a
  gutter to reset that dimension to its default. Touch-draggable too.
- **Collapsible panels** — the watchlist, order ticket and bottom panel each
  collapse to reclaim space; collapsed side panels leave a vertical re-open
  rail, the bottom panel a ▾/▴ toggle.
- **Layout memory** — panel sizes, collapsed states, the selected symbol and
  timeframe, and the watchlist filter are remembered per browser
  (`localStorage`) and re-applied on the next load. A remembered symbol/
  timeframe is only accepted if the server still offers it.
- **Explicit connection state** — every terminal feed reports success/failure
  to one place; after two consecutive failures a "Live data stale — retrying"
  strip with a **Retry** button appears, and a recovery clears it. A dead feed
  is never a silently frozen panel again.
- **Tooltips** — every order/bottom tab and icon button carries a descriptive
  `title`.
- **Compact mobile layout** — on phones the watchlist becomes a slide-over
  drawer (☰ in the chart toolbar, tap-outside to dismiss, auto-closes on
  symbol select) instead of vanishing; the bottom panel flows naturally.
- Regressions: `test_panel_collapse_toggles_persist_to_localstorage`,
  `test_panel_collapse_round_trips_from_saved_layout`,
  `test_terminal_connection_state_surfaces_after_repeated_failures`,
  `test_watchlist_failure_reports_the_feed_down`,
  `test_selecting_symbol_persists_and_closes_mobile_drawer`
  (`tests/test_terminal_js.py`). Full suite **1327 passed / 1 skipped**;
  served-script `node --check` clean; `config.VERSION` = `pyproject.toml` =
  `sky-shell-v2.53.0` lockstep. Contract: `docs/HANDOVER_2026-08-20_T4_part2.md`.

## [2.52.0] — 2026-08-20 · T4 (part 1) — honest sizing, live bottom tabs, skeletons

MINOR: the terminal's trade ticket no longer invents numbers, the bottom
tabs always re-fetch, and slow panels paint loading skeletons instead of
blank space. No new trading capability — advisory UI and one read-only
endpoint; no threshold moved, no exchange-order path.

- **`GET /api/ticket/meta`** — the honest inputs for the ticket: the real
  `ACCOUNT_BALANCE` (0 when unset) and the per-symbol cost model
  (`data.costs.cost_model_for_symbol` — round-trip taker/spot fee + full
  spread + slippage, no funding on gold spot). Read-only.
- **Honest ticket sizing** (`recalcTicket`) — risk dollars and units come
  from the server's account balance; when no `ACCOUNT_BALANCE` is set the
  ticket shows **—** (with a "set ACCOUNT_BALANCE" hint) instead of the old
  fabricated **$100k** default. The fee estimate now uses the desk's real
  cost model and shows both the dollar figure (when sized) and the
  round-trip %.
- **Bottom tabs re-fetch on every switch** — the one-shot `_bottomLoaded`
  cache is gone, so a position the paper runner just closed can no longer
  linger as a stale row. Alerts keeps its static content; skeletons paint
  while each tab loads.
- **Loading skeletons** — shimmer rows (`.skel`) for the watchlist and the
  bottom tabs while fetches are in flight.

## [2.51.0] — 2026-08-20 · T2 — AI Copilot polish

MINOR: the Copilot now renders the desk's answers as **titled sections**
with a **sources footer**, prepares (never approves) the trade ticket from
the desk plan, and answers about the market the trader is actually looking
at. No new trading capability — advisory UI and additive answer metadata
only; no threshold moved, no exchange-order path.

- **Structured answers + grounding sources** (`brain/agent.py::ask`). Every
  intent now returns `sections` (a list of `{title, body}`) and `sources`
  (the exact surfaces the numbers came from — e.g. `risk gate —
  brain.risk_gate.evaluate`, `open paper book — SignalDB.live_open_rows`).
  `market` answers split into **Market read** and **Desk decision**; the
  plain `answer` list is unchanged, so the CLI, MCP `cryptobrain_ask` and
  every existing test still read what they read before.
- **Richer exposure context** (`ask` exposure intent). Open-position answers
  now state the canonical live-book count (P12.16 `live_open_rows`) split
  from planned exposure, and attach the **measured expectancy** for each
  plan type the exposure is carrying (from the calibration profile).
- **Copilot rendering fixed** (served `web/app.py` script +
  `web/static/terminal_newjs.js`). The old section parser double-printed the
  raw answer and comma-joined the answer list into one line. The Copilot now
  joins list answers with newlines, renders the backend's own sections, and
  shows a dashed **Sources** footer — never a duplicate raw blob.
- **Prepare ticket from AI** (`aiPrepareTicket`). A new quick action (global
  drawer + order-panel Copilot) pre-fills side/type/entry/SL/TP from the desk
  plan and switches to the Ticket tab. Advisory only — it never confirms,
  never posts, and stands aside with a toast when the desk has no action.
- **Symbol/timeframe-aware Copilot** — `aiSend` now sends the selected
  `symbol`/`tf`, so "Review this signal" / "Explain this chart" target the
  market on screen instead of the server default.

## [2.50.0] — 2026-08-20 · T3 — the Trade Terminal runs the whole paper loop

MINOR: the terminal Confirm button now wires the **complete paper-trade
workflow** through the existing desk path — chart → understand → paper
trade → manage → close → journal. No new trading capability: the ticket
becomes a real scan row, the risk & discipline gate is re-read fresh on
the server immediately before the APPROVED decision, the paper runner
enrolls the position, and Close records the outcome into the existing
`TP_HIT` / `STOP_LOSS` buckets so every discipline surface still counts
it. No threshold moved; no exchange-order path exists.

- **`POST /api/terminal/confirm`** — fail-closed ticket validation
  (side, type, positive levels, stop on the correct side, `risk_pct ∈
  (0,100]` with an explicit `0` rejected, strictly-increasing targets),
  persists a real PENDING_REVIEW scan (`save_scan`), idempotent via the
  client `ticket_id` (`signal_id = terminal_<id>`; retries answer
  `duplicate:true`, used tickets 409), **fresh server-side
  `gate_evaluate` immediately before the decision** (409 + `blocked_by`
  + `force_available`, same `SKY_ALLOW_FORCE_APPROVE` force semantics
  and auditing as `/api/review`), the W3.3 journal-first gate with the
  same audited `acknowledge_journal` escape, then
  `PaperTradingRunner.run_once` — market tickets paper-fill at the
  confirmed entry (scan → EXECUTED), limit/conditional tickets wait for
  the level (`WAITING_ENTRY`) like any conditional desk plan.
- **`POST /api/terminal/close`** — closes an open paper position from
  the terminal: exit price = explicit value → runner `last_price` →
  latest candle close (refuses 409 rather than inventing one);
  WAITING_ENTRY positions are cancelled honestly (scan APPROVED →
  SKIPPED, `journal_required:false`); OPEN positions record the real
  economic outcome in the existing `TP_HIT` / `STOP_LOSS` buckets with
  `close_reason = manual terminal close …` + the exact R in the
  decision note; lifecycle advanced EXECUTED → CLOSED (APPROVED trades
  get their honest EXECUTED fill step first); concurrent runner closes
  answer 409. `journal_required` drives the client drawer.
- **Positions under the chart** — the bottom Open-positions tab now
  reads `/api/trades` (the same live-open book the Trade Manager uses):
  live R, MAE/MFE, minutes in trade, an inline management card with the
  desk management checklist, per-row Close, and re-fetch on
  confirm/close plus a 60 s visible-tab refresh. The watchlist position
  chip reads the same book.
- **Close → auto-journal** — closing switches to the Journal tab with
  an inline form (outcome + R headline, followed-rules Yes/No, emotion,
  mistake, notes) posting to the existing `POST /api/journal`; the
  journal-first gate clears on save.
- **Ticket gate honesty** — the ticket gate box now shows a live
  `/api/risk` read labelled as a preview; the confirm endpoint is the
  authoritative re-check, and a server block paints its real
  `blocked_by` back into the ticket. A demo runner stop-out is reported
  as “filled and already closed by the runner” instead of a fake open
  position.
- **Tests** — `tests/test_terminal_t3.py` (14 backend) and
  `tests/test_terminal_js.py` (6 node/jsdom) cover the desk-path
  confirm, idempotency, fail-closed validation, student-level block +
  force semantics, trader-state block, journal-first hold/ack, close
  outcome buckets, last-price closes and the drawer save. Full suite
  **1302 passed / 1 skipped** (was 1282 / 1).

## Docs — 2026-08-20 · Combined roadmap (core aim + terminal + evidence)

Documentation only. Software remains **v2.49.0**. No threshold moved. No
order path. No PWA cache bump.

- **`ROADMAP.md`** restored as the combined source of truth after PR #72's
  rewrite: the core aim (independent profitable trader; accumulate BTC /
  ETH / GOLD), three non-substitutable lanes (P11 paper proof / T1–T6
  terminal / P18–P22 distribution), and honest T1–T6 status (T1 layout
  shipped; Confirm does not enroll a paper trade; T3 is the next code
  build). Version header was still v2.48.1 with T1 marked NEXT; that is
  corrected.
- **`docs/PR_REVIEW_2026-08-20.md`** — review of merged PRs #62–#72.
- `TODO.md`, `HANDOVER.md`, `SESSION_STATE.md` reconciled to the same
  next step.

## [2.49.0] — 2026-08-20 · The Trade Terminal — professional layout

MINOR: the web dashboard is now a **professional Trade Terminal**. One screen
holds a watchlist (left), a large chart (centre), a paper-trade ticket + AI
panel (right) and a tabbed trading panel (bottom). Six primary navigation
areas replace the sixteen-tab bar. The roadmap was rewritten around this
vision. This is a **presentation-layer** release: every server endpoint, the
risk gate, the graduation bar, auth/roles/CSRF, `/api/v1`, jobs/SSE, PWA and
all trading logic are untouched. No threshold moved; no order path exists.

- **Trade Terminal (default view)** — `web/static/terminal_head.html` +
  `web/static/terminal_newjs.js` spliced into the `web/app.py` template:
  watchlist with search + live prices + 24h change + compact positions list;
  full chart workspace (EMA/VWAP/BB/levels/zones/plan/RSI/MACD, drawings,
  replay, live stream, 2×2 multi-chart, readings + levels strip); paper
  ticket (Buy/Sell, Market/Limit/Conditional, entry, SL, TP1–TP3, risk %,
  auto size, planned R:R, est. fees, risk-gate verdict, disabled-while-blocked
  Confirm); bottom panel with **Open positions · Pending plans · Trade
  history · Journal · Alerts · Strategy evidence · Background** tabs.
- **Six-area navigation** — Trade, Markets, Portfolio, Journal, Evidence,
  System with compact inline SVG icons. Modules and Command Center moved
  under System. The legacy dashboard shell is preserved intact as the
  non-Trade views (grouped), so no previous function was lost.
- **AI Copilot** — persistent right-side drawer (✦ in the top bar) plus a
  Copilot tab in the order panel. Eight quick actions + free chat through
  the existing `POST /api/ask` with automatic context injection (symbol,
  timeframe, signal, desk decision, risk-gate reasons, MTF, sentiment) and
  structured sectioned replies (Market facts / SKY interpretation / Risk
  concerns / Suggested next action). Advisory only.
- **Top-bar status chips** — feed freshness (`/api/readiness`), risk gate
  (`/api/risk`), open-position count (`/api/paper`).
- **Professional visual language** — flat dark `#0b0e14`, thin 1px borders,
  compact typography, green/red only for direction & P&L, amber warnings,
  cyan SKY actions.
- **Roadmap** — rewritten as the Professional Trading Terminal product plan
  with phases T1–T6 (T1 layout shipped here; T2 AI polish, T3 paper
  workflow wiring, T4 panel persistence/polish, T5 home screen, T6 focused
  pages).
- **Tests** — the jsdom harnesses (`test_dashboard_js.py`,
  `test_workstation_js.py`, `test_practice_js.py`, `test_weekly_js.py`) stay
  green against the spliced template; `test_served_script_is_valid_javascript`
  parses the served script; full suite **1282 passed / 1 skipped**; wheel
  gate builds `cryptobrain-2.49.0-py3-none-any.whl` with no duplicates.
- Contract: `docs/HANDOVER_2026-08-20_v2.49.0.md`.

## [2.48.1] — 2026-08-20 · PWA cache + test-environment reliability

PATCH: closes two release/reliability gaps found while establishing the clean
v2.48.0 baseline. Trading logic, thresholds, evidence populations, and the
no-order boundary are unchanged.

- **PWA cache rollover** — advances `web/static/sw.js` from the stale
  `sky-shell-v2.47.0` cache to `sky-shell-v2.48.1`, ensuring the worker source
  changes and activation retires the previous release precache.
- **Release invariant** — `tests/test_pwa.py` now requires `config.VERSION`,
  `pyproject.toml`, and the service-worker cache suffix to match exactly, so a
  future version bump cannot silently omit installed PWA clients.
- **Hermetic agent CLI tests** — the two `sky-agent` subprocess tests now use
  `sys.executable` and an absolute `main.py` path, matching the rest of the
  CLI suite instead of escaping a valid virtual environment through ambient
  `python`/working-directory assumptions.

## [2.48.0] — 2026-08-20 · W3.5 part 2 — 2×2 multi-chart synchronized crosshair

MINOR: completes the "multi-chart layout (2×2) with a synchronized
crosshair across assets" backlog item (`docs/HANDOVER_2026-08-20_W35_part2.md`).

- **Synchronized crosshair** — one pointer over any of the four panes moves
  the crosshair on all of them (`subscribeCrosshairMove` →
  `setCrosshairPosition(price, time, series)` via the vendored Lightweight
  Charts v4.2.3 API, with `clearCrosshairPosition()` when the pointer
  leaves). Re-entrancy guard keeps the broadcast one-way; panes use Normal
  crosshair mode so magnet snapping cannot fight the sync.
- **Per-browser sync toggles** — "Zoom sync" / "Crosshair sync" checkboxes
  in the comparison bar, on by default, persisted as `sky.multiSyncZoom` /
  `sky.multiSyncCrosshair`; act immediately, no reload.
- **Four distinct default slots** — the old defaults collapsed to three
  panes when the primary was BTCUSDT; `multiDefaults()` now fills the 2×2
  grid with four distinct views (primary on two timeframes + two other
  markets).
- **Honest empty slots** — a failed feed or unsupported pair paints an
  explicit "no candles for SYMBOL TF — error" slot, never a blank chart.
- **1970-date fix** — `multiCandleData()` handed `/api/chart` epoch seconds
  to `new Date()` as if milliseconds; every multi-chart pane silently
  painted January 1970. Times now normalise like the backend.
- **Served-script trap cleanup** — `urlBase64ToUint8Array()` VAPID helper
  dropped the Python-eaten `/\-/g` escape (identical served regex, no more
  DeprecationWarning).
- **CI maintenance** — GitHub deprecated Node-20 actions; the dormant
  `ci/release.workflow.yml` spec was bumped to the Node-24 majors
  (`checkout`/`setup-python`/`upload-artifact` @v7, verified `using: node24`
  via the GitHub API). The ACTIVE `.github/workflows/ci.yml` bump is a
  repo-admin human action (`docs/HUMAN_ACTIONS.md`) — the integration's
  workflow-file push is rejected by GitHub (no `workflows` permission).
  CI stays green with only the deprecation annotation until then.
- **Tests** — +5 multi-chart regressions in `tests/test_workstation_js.py`
  (crosshair broadcast + clear + toggle, zoom toggle, empty slot, distinct
  defaults + validation, timestamp normalisation); full suite
  **1282 passed, 1 skipped**; wheel gate green.

## [2.47.0] — 2026-08-20 · PWA Push (VAPID), Veto Timeline & R-Distribution

MINOR: Web Push (VAPID) notifications, designed vector PWA app icons,
iOS safe-area insets and standalone display mode handling, Risk Center
"Why Blocked?" Veto Timeline, and R-Multiple Distribution analytics.

- **Web Push (VAPID)** — `data/push_notifications.py` RFC 8292 Web Push
  manager using `cryptography` SECP256R1 keys and IEEE P1363 ECDSA JWT
  signatures. Endpoints: `GET /api/push/vapid-key`, `POST /api/push/subscribe`,
  `POST /api/push/unsubscribe`, `POST /api/push/test`. `web/static/sw.js` and
  `window.SKY_push` UI integration. Probe `_probe_webpush()` in `brain/connections.py`.
- **App Icons & iOS Polish** — `packaging/generate_icons.py` creates 180x180,
  192x192, 512x512, and 512x512 maskable PNG icons under `web/static/icons/`.
  iOS safe-area insets (`env(safe-area-inset-top)`) and standalone detection
  (`body.standalone` / `body.ios-standalone`).
- **Veto Timeline** — `risk_vetoes` table and `record_risk_veto()` in
  `data/database.py`, auto-logged from `brain/decision.py`. Endpoint
  `GET /api/risk/veto-timeline` + "🛡 VETO TIMELINE" card in Risk Center.
- **R-Distribution** — `r_distribution(db)` in `brain/analytics.py` computing
  realized net R histogram bins (`<-2R` to `>=3R`), mean/median R, and win/loss
  counts. Endpoint `GET /api/analytics/r-distribution` + "📊 R-MULTIPLE DISTRIBUTION" card.

## [2.46.0] — 2026-08-19 · W3.6 replay tape practice

MINOR: Replay Freeze + **Grade against the tape**. Commit a chart read at
the last visible bar; the server walks the hidden forward window (default
16 bars, clamp 4–64) and grades what actually happened. Ladder fills reuse
`data.paper_trading.exit_event` (stop-first). Desk-agreement keys stay
desk-only; tape lives in a sibling `tape` block. Coaching memory only —
never writes `paper_trades` / scans / graduation / the risk gate.

- **Grader** — `brain/practice.py`: `walk_tape` / `score_tape` /
  `submit_tape_attempt`. no-trade → ATR stand-aside; buy/sell without a
  ladder → signed ATR close move; buy/sell with a ladder → `exit_event`.
- **Dashboard** — Chart PRACTICE card: Freeze, tape banner, Grade against
  the tape. Review tab paints the sibling tape card.
- **API** — `POST /api/practice/tape`. Client cannot supply the future.
  Fail-closed validation. MCP `practice_scorecard` 1.14.0 mentions the
  tape sibling.

Honest: no browser in this sandbox. Proven with Flask client + Node JS
harness + `python -m py_compile`. Tape ≠ paper evidence. P22 still needs
real signers.

## [2.45.0] — 2026-08-19 · W4.2 Ubuntu PC is the Hub; one research agent

MINOR: the always-on Ubuntu PC is now an explicit Hub role, not a second
agent. `sky-agent.service` joins the Hub unit catalog and reads the same
`/etc/sky/sky.env` as the dashboard. The 🧠 Agent tab shows **THIS PC —
24/7 HUB ROLE**. No threshold moved. No order path. No second PC-use agent.

- **Decision** — `docs/UBUNTU_PC_ROLE.md` + `docs/KEPT_IDEAS.md`. Use one
  research agent. Park scoring-tune / EDGAR-as-strategy / second AutoGPT.
- **Hub FHS** — `UNITS` includes `sky-agent.service` + timer; `hub role`;
  `hub status` / `hub doctor` report the agent; generated env carries poll
  keys; first-night + Debian prerm include the unit.
- **Dashboard** — Hub role card, `GET /api/hub/role` + `/api/hub/status`,
  Command Center `hub_role`.
- **Packaging** — `sky_agent*` in the wheel find list (missed in 2.44.0).

Honest: this sandbox cannot enable systemd on a live host. P11/P22 remain
human/host work.

## [2.44.0] — 2026-08-19 · W4.1 Agent dashboard tab + report archive

MINOR: the 24/7 research daemon is now a clickable **🧠 Agent** tab. Health,
daily report, hypotheses, regime log and SEC rows share the existing
`/api/sky-agent/*` payloads. Archive writes one `intelligence_reports` row
and never feeds the risk gate or graduation. Recommendations stay
WATCH / CONSIDER / WAIT / AVOID. No threshold moved. No order path.

- **Dashboard** — new tab + quick-bar button; Command Center cards for
  `sky-agent health|status|report|collect`; daemon stays terminal-only.
- **`POST /api/sky-agent/report`** — audited archive via
  `sky_agent.daily_report.archive_daily_report`.
- **Packaging** — `sky_agent*` included in the wheel find list.

Honest: scoring still needs live days before any weight change. EDGAR event
studies were not built — they do not move the paper graduation bar.

## [2.43.0] — 2026-08-19 · W3.5 multi-chart comparison views

- Added an optional four-up multi-chart workspace to the Chart tab.
- Compares the selected symbol/timeframe with a nearby timeframe plus BTCUSDT
  and ETHUSDT reference views; charts are independently fetched from `/api/chart`.
- Synchronizes zoom and pan across tiles while keeping candles, prices and
  signals separate. The view is explicitly comparison-only and never combines
  or changes desk decisions, practice scoring, risk, paper, or graduation.
- Responsive 2×2 layout collapses to one column on narrow screens.
- Existing single-chart overlays, replay, live streaming and drawings remain
  the default path.


All notable changes to **CryptoBrain / SKY** are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

> **Note:** this changelog was created on 2026-08-11. Pre-v2.0.0 history
> lives in the `MERGE_NOTES.md` provenance document. The `pyproject.toml`
> `version` is the source of truth; this file documents what shipped.

---

## [2.42.0] — 2026-08-19 · W3.4 practice mode — commit your read, the desk answers, the score remembers

MINOR: the trader can now practise reading the chart *before* peeking at the
Signal desk: commit a read (bias → final call → entry/stop/target ladder,
optional confidence + note) and the server freezes the desk's read at that
exact moment, scores the agreement deterministically with visible components,
and remembers it. The Review tab gains a PRACTICE CALIBRATION mirror:
agreement rates, component means, the weakest link, one coaching takeaway,
recent attempts. Coaching memory only — practice rows are never read by the
live book, the risk gate, calibration, or graduation; agreement with the desk
is study, not evidence; the graduation bar is quoted, never moved.

- **`brain/practice.py`** — one computation, many surfaces:
  `desk_read_from_payload()` (freezes action/bias/ladder/regime/ATR from the
  live engine payload), `validate_user_read()` (fail-closed vocabularies;
  a half-plan — entry without stop — is rejected, not scored), `score_attempt()`
  (bias 35 / final call 35 / ladder 30 with proximity-vs-ATR, stop-side and
  ≥1.5R floor checks; no-ladder reads renorm over 70; grade A–E identical to
  the weekly bands), `practice_scorecard()` (windowed agreement rates,
  component means, weakest link → deterministic coaching, honest empty state),
  `format_practice_scorecard()`.
- **`practice_attempts` table** — per-attempt store (user read, frozen desk
  read, score). Double-submit guard: an identical read inside 2 minutes
  returns the original attempt — history is never inflated.
- **Surfaces (invariant #10)** — `python main.py practice [--days N] [--json]`;
  `GET /api/practice` + audited `POST /api/practice` (400 fail-closed on bad
  vocabulary; 502 and *nothing recorded* when the engine read is unavailable;
  `save=False` — a practice read never enters the scans queue); dashboard
  **📊 Chart tab ✍ PRACTICE card** (form + reveal: desk pill vs your call,
  component table) and **🗓 Review tab PRACTICE CALIBRATION card**; root MCP
  `practice_scorecard` (server 1.13.0) + SDK `cryptobrain_practice`; Command
  Center "Practice calibration" card.
- **Tests +36 (1177 → 1213 passed / 1 skipped)** —
  `tests/test_practice.py` (30: extraction, fail-closed validation, every
  score component and renorm path, dedupe, scorecard aggregation + honest
  empties, the standing invariant that practice rows never reach the live
  book / weekly review / `paper_progress()`, HTTP happy/400/502 paths, `save=False`
  proof, CLI) and `tests/test_practice_js.py` (6 jsdom: POST capture, reveal
  paint, duplicate note, rejected-read reason, scorecard weakest-link paint,
  honest empty).

---

MINOR: the weekly trader review is now a first-class page instead of a plain
`<pre>` dump of `agent weekly-review` (HANDOVER Priority 2), the daily ritual
remembers what you ticked today (Priority 3.1), and the journal-first gate
holds the next approval while a decided real trade is unjournaled
(Priority 3.3). Strictly tighter on the human only: no threshold moved, the
risk gate is untouched, no order path exists. Canonical live book only
(simulator + research excluded); every judgement NET of costs.

- **`brain/weekly.py`** — `weekly_review(db)`: this week vs all time
  (E_net, win rate, PF, totals), equity curve (reuses `business_metrics` so
  the page cannot disagree with the Risk center), net-R distribution buckets,
  violations with the repeating-mistake and emotion breakdowns, per-setup
  graduation tracker naming the exact missing evidence, one deterministic
  next practice task, and an advisory grade with visible components. The bar
  (+0.50R / 55% / PF 1.5 / compliance 90%) is quoted, never moved.
  `missing_journals(db)` is the journal-first gate population (same
  fail-closed P12.14 discipline rows).
- **Surfaces, one computation (invariant #10)** — `python main.py weekly
  [--days N] [--json] [--export PATH]`; `GET /api/weekly` + `/api/weekly/export`
  (JSON attachment); dashboard **🗓 Review tab** (stats, task card, ritual,
  equity chart, R-distribution, discipline card, tracker table, export);
  root MCP `weekly_review` (server 1.12.0) + SDK `cryptobrain_weekly`;
  `WeeklyReviewAgent` now archives the full review payload inside
  `agent_runs`; Command Center "Weekly trader review" card.
- **W3.2 daily ritual with memory** — `brain/ritual.py` + `ritual_checks`
  table: the four loop-health steps persist per UTC day; a new day starts
  empty by construction; `GET/POST /api/ritual` (unknown step names fail
  closed; ticks are audited and explicitly not permission).
- **W3.3 journal-first approval gate** — `python main.py approve` and
  `POST /api/review` hold APPROVED decisions while decided real trades are
  unjournaled: a commitment waits until the last one is processed. Escape:
  `--acknowledge-journal` / `acknowledge_journal: true` (audited). Rejects,
  closes and skips are never held; simulator and research debt never holds;
  `--force` overrides the risk gate only, not the journal gate.
- **Tests** — +37: `tests/test_weekly_review.py` (15: window math, source
  isolation, R-distribution, task ladder, grade, agent payload, MCP tool,
  text format), `tests/test_ritual.py` (17: persistence, day isolation,
  unknown names, API roundtrip, journal gate web+CLI, approvals never held
  once journaled/by rejects/by sim+research debt), `tests/test_weekly_js.py`
  (5: panel painting, ritual POST+repaint, acknowledge/cancel flows, honest
  empty book). Suite 1140 → **1177 passed / 1 skipped** (+37).

Honest limits: verified with the node/jsdom harness, the Flask test client
and curl against a running dev server; no real browser exists in this
sandbox. The weekly-review *agent* summary line is unchanged (payload grew).
The practice task is advisory coaching text — it blocks nothing by itself.

## [2.40.0] — 2026-08-18 · P22.3 signing + clean-target drill contracts

MINOR: trusted-signing and physical install/upgrade/rollback work is now a
fail-closed catalog with operator evidence, not a claim from Linux CI. No
threshold moved and no exchange-order path was added.

- **Drills** — `ops/release_drills.py` publishes six checklists (Debian repo
  sign, Authenticode, apksigner, Ubuntu clean VM, Windows 11 clean target,
  Android physical target).
- **CLI** — `python main.py release drills|check` and Command Center cards.
  Evidence JSON must include every required field; sandbox/CI completion
  claims are rejected; `p22_complete` stays false without a full evidence dir.
- Honest limitation: this checkout still produced no signed installer.

## [2.39.0] — 2026-08-18 · P22.2 native companion projects

MINOR: real Windows (.NET 8 / WebView2) and Android (Gradle / Kotlin) project
trees replace recipe-only folders. Static lint inventories them and refuses
order paths, signing material and a true live-execution flag. No threshold
moved and no exchange-order path was added.

- **Windows** — `packaging/windows/SkyCompanion/` SDK-style WinForms + WebView2
  client. HTTPS (loopback HTTP only), Credential Manager target, hard-coded
  `LiveExchangeExecution = false`.
- **Android** — `packaging/android/SkyCompanion/` Kotlin app, Keystore contract,
  biometric re-check gate, `sky://` deep links, cleartext refused.
- **Lint** — `ops/native_projects.py` and `python main.py companion lint`.
  Physical install/upgrade/rollback drills remain pending. Unsigned.

## [2.38.0] — 2026-08-18 · P22.1 release-operations foundation

MINOR: release outputs are now inspectable, channelled and diagnosable without
pretending this Linux checkout can sign or install native clients. No threshold
moved and no exchange-order path was added.

- **Release metadata** — `ops/release.py` + `packaging/build_release.py` emit
  sorted SHA-256 checksums, a version/channel/API compatibility manifest,
  SPDX 2.3 SBOM and dependency/license inventory. Channels are the closed
  vocabulary `stable|beta`; metadata cannot claim `signed=true` without a
  detached verifier record.
- **Private diagnostics** — `python main.py hub diagnostics` writes a mode-0600
  support bundle with one recursively redacted JSON snapshot. Database,
  market store, environment, raw logs and secrets are excluded.
- **CI foundation spec** — `ci/release.workflow.yml` defines API/client/release
  contracts across Ubuntu and Windows, clean-runner Debian install/backup/
  remove smoke, metadata/SBOM generation and `pip-audit`. PR CI receives no
  signing secrets. Arena's GitHub App cannot activate workflow files; a repo
  admin must review/copy it to `.github/workflows/release.yml`.
- **Operations** — `docs/RELEASE_OPERATIONS.md` defines stable/beta promotion,
  isolated Debian/Windows/Android signing, signature verification, support,
  incident and rollback paths.
- **Debian correctness** — direct builds now resolve `${misc:Depends}`, derive
  the current version, carry a maintainer, create the package runtime on a
  clean host, and remove generated venv/caches with `/opt/sky` while preserving
  `/etc/sky` + `/var/lib/sky` on ordinary uninstall.
- **Tests** — `tests/test_release_ops.py` pins channels, checksums, SBOM,
  redaction, private bundles, signing readiness and workflow/runbook safety.

Honest limitation: this is P22.1, not P22 completion. P20/P21 contain native
client contracts and recipes, not native projects; no signed `.deb`, `.exe`,
`.msix`, `.apk` or `.aab` was produced. Clean physical target drills and
trusted signing remain release-environment work.

---

## [2.37.0] — 2026-08-18 · P21 Android companion contract

MINOR: the Hub can pair an Android companion over `/api/v1` without
duplicating the engine. No signed `.apk` is claimed. No threshold moved,
no exchange-order path.

- **Android client contract** — `ops/android_companion.py`: HTTPS-only Hub
  URL rules + configured-host allowlist (`host_allowed`), Keystore-backed
  token storage (guarded file fallback is test-only), a declarative
  **biometric re-check policy** (`biometric_policy`, `requires_biometric`)
  for operator mutations, **online-only mutations** (`connection_snapshot`
  never queues a paper approval offline), and a **push/deep-link contract**
  (`sky://record/<signal|risk|paper|journal|dashboard>[/<id>]`). Reuses the
  P20 pairing + version negotiation with `client=sky-android`.
- **CLI** — `python main.py companion spec|validate-url|status --platform
  android` and `python main.py hub pair --platform android`.
- **Packaging** — unsigned recipe `packaging/android/README.md` (signing is
  P22).
- **Tests** — `tests/test_android_companion.py` (16 tests). Full suite:
  1115 passed, 1 skipped.
- Contract: `docs/HANDOVER_2026-08-18_P21.md`.

Honest: no signed APK, no Android device/emulator install drill in this
sandbox; the module describes the client contract the native shell implements.

---

## [2.36.0] — 2026-08-18 · P20 Windows companion contract

MINOR: the Hub can pair a Windows companion over `/api/v1` without
duplicating the engine. No signed `.exe` is claimed. No threshold moved,
no exchange-order path.

- **Pairing** — one-time 8-character codes (`pairing_codes`), 10-minute
  TTL, hashed, single use. `POST /api/v1/pair` (public redeem) and
  `POST /api/v1/pair/code` (operator mint + QR JSON).
- **Client contract** — `ops/windows_companion.py`: HTTPS-only remotes,
  compatibility check, Credential Manager / refuse world-readable token
  files, tray snapshot, idempotent mutation headers.
- **CLI** — `python main.py hub pair`, `python main.py companion spec|status|validate-url`.
- **Packaging** — unsigned recipe `packaging/windows/README.md` (signing is P22).
- **Tests** — `tests/test_windows_companion.py`.
- Contract: `docs/HANDOVER_2026-08-18_P20.md`.

Honest: no Windows 11 install, no signed binary in this sandbox.

---

## [2.35.0] — 2026-08-18 · P19 Ubuntu Hub package

MINOR: first production-install path for a single Ubuntu Hub. No threshold
moved, no exchange-order path, uninstall keeps user data unless `--purge`.

- **Hub CLI** — `python main.py hub setup|status|logs|backup|restore|doctor|uninstall`
  (`ops/hub.py`). FHS roots `/opt/sky`, `/etc/sky`, `/var/lib/sky`; tests
  override with `SKY_HUB_PREFIX`.
- **Backup/restore** — SQLite backup API + redacted env + optional Parquet
  store; archives `0600`; 14-day retention; restore refuses overwrite unless asked.
- **Hardened systemd** — `ops/systemd/sky-{dashboard,paper,scan,backup}`
  (loopback gunicorn, `NoNewPrivileges`, `ProtectSystem=strict`, `User=sky`).
- **TLS examples** — `ops/proxy/Caddyfile` and `nginx-sky.conf`; API `no-store`.
- **Debian packaging** — `packaging/debian/*`, `/usr/bin/sky`,
  `packaging/build_deb.sh` (unsigned artifact; signing is P22).
- **Command Center** — Hub status / doctor / backup buttons.
- **Tests** — `tests/test_hub.py`. Contract: `docs/HANDOVER_2026-08-18_P19.md`.

- **First night** — `docs/HOME_HUB_FIRST_NIGHT.md`, `bash ops/first_night.sh`,
  `python main.py hub first-night` (home-PC 24h checklist; no trade keys).

Honest: no signed apt repo, no clean-VM install drill in this sandbox.

---

## [2.34.0] — 2026-08-18 · P18.4 PWA foundation — installable, offline-safe shell

MINOR: the desk is now installable (Chrome/Edge desktop + Android) and honest offline. No threshold moved, no order path exists, nothing here writes to the learning store, the paper book or the risk gate. This is a delivery shell over existing behaviour.

- **Manifest + icons** — `web/static/manifest.json` (name SKY, `start_url /?source=pwa`, `display standalone`, `theme #070b14`, 192/512 any + 512 maskable + 180 apple, 3 shortcuts) + project-owned PNGs under `web/static/icons/`. No CDN.
- **Service worker** — `web/static/sw.js` (`sky-shell-v2.34.0`) precaches **shell only** (`/`, `/offline.html`, manifest, chart lib, icons). **Never** caches `/api/*`, auth, `/api/chart/stream` or `/api/v1/jobs/*/events` (bare `return` → network-only, so private JSON never enters CacheStorage). Navigation is network-first → offline fallback; `/static/*` is stale-while-revalidate. Served at `/sw.js` with `Service-Worker-Allowed: /` + `Cache-Control: no-cache`.
- **Offline shell** — `web/static/offline.html` always-available precached page: *You are offline — cached shell only; Mutations disabled; API/auth/SSE are never cached — network-only.* Shows `sky:lastUpdated`, connection, SW state, actions.
- **Dashboard wiring** — `<link rel="manifest">`, `theme-color`, `apple-touch-icon`, sticky `#offlineBanner` (⚠️ Offline — showing cached shell. Data may be stale. Mutations disabled.) + `#installBanner` (📲 Install SKY + 7-day snooze), `640px` compact mode for daily ritual/risk/paper/approvals/journal, `beforeinstallprompt`/`appinstalled`, `online/offline` → `body.offline` + disable mutation buttons, `serviceWorker.register('/sw.js', {scope:'/'})` with update toast, `SKY_push` stub + `SKY_compact()` helper. Kept `node --check` clean (no `\n` literal inside Python string).
- **Routes & gate** — `GET /sw.js`, `/manifest.json`, `/offline.html`, `/offline` are public before auth (`_auth_gate` exempt) so installability works even when auth is enabled.
- **Docs & tests** — `docs/HANDOVER_2026-08-18_P18_4.md`, `docs/CHATGPT_6IDEA_TRIAGE_2026-08-18.md` (6-idea Take/Park/Reject, no code). Suite: **1063 passed / 1 skipped** (+10 `tests/test_pwa.py`: manifest/icons/sw safety/never-cache/offline/HTML links/routes/headers/version/`node --check`).

---

## [2.33.0] — 2026-08-17 · W2 complete: live chart streaming + drawing tools

MINOR: the chart workspace streams the newest bar instead of waiting for a
manual reload, and the trader can draw on the chart. Display and annotation
only — no threshold moved, no exchange-order path (none exists in SKY), and
nothing here writes to the learning store, the paper book or the risk gate.

- **Live candle streaming** — `web/live_stream.py` + `GET /api/chart/stream`
  push the newest bar over server-sent events; the browser calls
  `series.update()` in place, so zoom, overlays, zones and drawings survive.
  Every frame states whether the feed is live, waiting, stale (unchanged for
  more than 2 × the timeframe) or erroring, and the UI labels disconnects — a
  silent feed is never presented as a quiet market. A failing source produces
  an error frame and a capped backoff instead of dropping the connection; the
  poll cadence is clamped to 2–15 s so one tab cannot hammer the source. The
  stream follows the selected symbol/timeframe and yields to replay mode.
- **Drawing tools** — trendlines (two clicks), horizontal rays (one click) and
  boxes (two corners), with undo, clear, a MY DRAWINGS list with per-item
  delete, and "📎 Attach to journal note". Marks snap to the nearest loaded
  bar and persist in `localStorage` per symbol + timeframe; corrupt storage is
  discarded rather than trusted.
- **Fixed: the dashboard's inline script was invalid JavaScript in a real
  browser.** `HTML` is a plain (non-raw) Python string, so a `'\n'` literal in
  the P18.3 job-log line became a real newline inside a JS string —
  `SyntaxError` — disabling the *entire* script. Every existing JS check read
  the file text, never the evaluated template, so nothing caught it. Fixed,
  and both the test suite and CI now parse the script Flask actually serves.
- Contract: `docs/HANDOVER_2026-08-17_W2_part2.md`. Suite: 1053 passed /
  1 skipped (+23).

---

## [2.32.0] — 2026-08-17 · W1 guided evidence build

MINOR: the Evidence tab now turns the P18.3 four-step background job into a
working guided flow instead of a defaults-only button. This release changes
measurement UX and job parameters only; it does not move a trading threshold,
claim profitability, or add exchange execution.

- **One coherent series** — choose asset, timeframe, market, history range,
  backtest bars and simulator rounds in the Evidence tab. The validated values
  flow into Backfill → Backtest → Simulator → Scorecard; unknown, invalid and
  unbounded values fail before a job row is persisted.
- **Inline progress** — step/phase, a real 0–4 progress bar and the streamed log
  remain in the Evidence tab. An active evidence run is restored after reload;
  users no longer have to open Command center to see it.
- **Projected gap** — recent successful job logs provide the observed aggregate
  backtest/paper additions per simulator round. SKY shows approximately how
  many rounds remain, labels the estimate as non-guaranteed, says “unknown”
  before any observed pace exists, and says “stalled” when deduped rounds add
  no unique evidence.
- **Honest result** — insufficient samples remain “incomplete.” Once sample
  targets are met, non-positive net expectancy is reported plainly as “no
  positive net edge”; the UI explicitly warns against parameter-tuning merely
  to turn the result green. A positive sample result still does not bypass the
  separate graduation, discipline or risk gates.
- **Tests** — composite parameter propagation/refusal, projection math and
  no-edge reporting are covered in Python; the Node/jsdom harness clicks the
  real guided flow and verifies the selected values, inline stream and result.

---

## [2.31.0] — 2026-08-17 · P18.3 background job manager + streaming (SSE)

MINOR: long commands no longer run inside one blocking POST. They move behind a
**persisted background-job queue** with status, progress, cancel and a streamed
log, so a browser close cannot kill a run and progress survives reload/restart.
No signal, risk, paper, graduation or execution behavior changed; the job layer
runs the *same* allow-listed commands the Command Center already ran, never a
shell string, and adds no exchange-order path (none exists anywhere in SKY).

- **`web/jobs.py`** — a `JobManager` (submit/get/list/tail/cancel/events) and a
  single in-process worker; `jobs` table in `data/database.py`, log files under
  `data/job_logs/` (gitignored). Allow-listed kinds: `backfill`, `backtest`,
  `simulator`, `scorecard`, `derivatives_collect`, `cross_collect`, plus the
  composite `evidence` (Backfill → Backtest → Simulator → Scorecard).
- **Deduplication** — `params_hash = sha256(kind + canonical params)`; a
  duplicate click while a job is live returns the existing run instead of
  starting a second one. A finished job is legitimately re-runnable.
- **Cancel** — queued jobs cancel outright; running jobs get a cancel request
  (SIGTERM→SIGKILL); terminal jobs refuse.
- **Restart safety** — orphaned `running` rows are adopted at boot and marked
  `interrupted` (with a note to resubmit), never silently re-run.
- **SSE** — `GET /api/v1/jobs/<job_id>/events` streams full state snapshots
  (`event: job`), one terminal frame then close; reconnect resumes from the
  persisted state.
- **v1 contract** — `GET/POST /api/v1/jobs`, `GET /api/v1/jobs/<id>`,
  `POST /api/v1/jobs/<id>/cancel`, `GET /api/v1/jobs/<id>/events`; new typed
  error codes `JOB_NOT_FOUND` and `JOB_NOT_CANCELLABLE`; routes declared in
  `apiv1.NATIVE_ROUTES` so the role gate and the published catalog stay in sync
  (path templates like `/jobs/<job_id>` now match). Submit = operator,
  list/get/stream = viewer.
- **UI** — Command center gained a Background-jobs panel (status badges, cancel,
  live streamed output); slow `🟠` commands submit jobs instead of blocking;
  the Evidence tab gained a one-click “Build my evidence” button.
- **Tests** — `tests/test_jobs.py` (24 tests): persistence + worker,
  allow-list/validation refusal, dedup, cancel, restart adoption, idle-worker
  blocking (no DB polling), the v1 envelope + typed codes, the operator/viewer
  role split, SSE framing, route catalog.

> **Fixed this release (CI timeout):** the worker originally polled the `jobs`
> table on a fixed interval when idle. Because every `make_app()` constructs a
> `JobManager`, the test suite leaked one polling thread per app — each
> re-running the schema DDL against its (soon-deleted) `tmp_path` database —
> enough to blow CI's 10-minute budget. The worker now blocks on an event and
> wakes only on submit/cancel; a regression test pins zero DB opens while idle.

---

## [2.30.0] — 2026-08-17 · P18.2 stable application API (`/api/v1`)

MINOR: the workstation now publishes **one documented contract** that the
browser, the future Windows `.exe` and the future Android `.apk` can all speak.
No signal, risk, paper, graduation or execution behavior changed; no threshold
moved. `/api/v1` is a *contract over existing behavior*, not a second engine.

- **One envelope.** Every `/api/v1` response is
  `{ok, data, error{code,message,details}, meta{api_version, server_version,
  request_id, ts}}` — success or failure, no exceptions. Legacy `/api/*`
  endpoints keep their historical shapes so the shipped dashboard does not
  break mid-migration (pinned by a regression test).
- **Typed error codes.** `web/api_v1.py::ErrorCode` is a closed vocabulary
  (`UNAUTHENTICATED`, `FORBIDDEN`, `CSRF`, `VALIDATION_FAILED`, `NOT_FOUND`,
  `RISK_GATE_CLOSED`, `LIFECYCLE_INVALID`, `IDEMPOTENCY_KEY_REUSED`,
  `CLIENT_TOO_OLD`, …). Clients branch on `error.code`; `error.message` is for
  humans and may be reworded without it being a breaking change. **No client
  parses terminal text.** The desk's deliberate refusals keep their own codes:
  a closed risk gate is `RISK_GATE_CLOSED` (409) carrying the structured
  `blocked_by` reasons, not a generic bad-request.
- **Compatibility negotiation.** `GET /api/v1/version` is public — a client
  must be able to discover the range *before* it can authenticate — and
  publishes `api_version` plus `min_client_version`/`max_client_version`. A
  client declaring `X-SKY-Client-Version` outside the range receives
  `CLIENT_TOO_OLD`/`CLIENT_TOO_NEW` with an upgrade message. The check runs
  **before** authentication, so an out-of-date app never shows the user a
  spurious "wrong password".
- **Idempotency keys.** `review`, `journal`, `paper/run` and `trader-state`
  accept `Idempotency-Key`. The first call executes and its rendered response
  is persisted (`idempotency_keys` table, 24h TTL, scoped per user+endpoint);
  a retry replays that exact response with `meta.idempotent_replay=true`
  instead of re-applying. A retried approval therefore cannot double-apply —
  pinned by a test asserting exactly one `decisions` row after four identical
  calls, with a no-key control proving the endpoint is not merely harmless to
  repeat. Reusing one key for a *different* body is `IDEMPOTENCY_KEY_REUSED`
  (409) rather than a silently wrong cached answer, and a too-short key is
  refused instead of ignored (a client that thinks it has retry safety and
  does not is the dangerous case).
- **Device registration/revocation** as a first-class contract:
  `GET/POST /api/v1/devices`, `POST /api/v1/devices/revoke`, plus
  `/api/v1/me`, `/api/v1/audit` and a machine-readable `/api/v1/routes`
  catalog. Raw tokens are never listed back; a revoked token stops working
  immediately.
- **Honest capability advertisement.** `/api/v1/version` reports
  `live_exchange_execution: false`, so a companion client can discover that
  SKY cannot place an order instead of shipping a Trade button that can never
  work.
- **Security is inherited, not re-implemented.** The P18.1 `before_request`
  gate already covers `/api/`, so v1 is authenticated, role-checked and
  CSRF-protected by the same code path; refusals are simply rendered in the v1
  envelope. Mutating v1 routes take their minimum role from the declared route
  table, and an *undeclared* mutating route defaults to `operator` — a
  forgotten declaration fails closed. `tests/test_api_v1.py` re-asserts every
  P18.1 invariant against the new surface: unauthenticated cannot read or
  mutate, a viewer-scoped token cannot approve/reject/close or mint an
  operator token, and **an operator still cannot bypass the risk gate**
  (force-approve remains disabled).
- **UI:** a System-tab card renders the negotiated version range, the
  capability flags (including the honest ✗ for live execution) and the full
  route catalog on demand — the contract is clickable, not documentation-only.
- Fixed while building: `_unwrap` preferred a `jsonify` Response's default
  200 over the real status in `return jsonify(...), 400`, which would have
  turned every legacy 4xx into a mislabeled `INTERNAL`.

Verification: `tests/test_api_v1.py` (59 new tests) and 4 new dashboard-JS
tests; full suite **982 passed / 1 skipped**, with the same three pre-existing
environmental failures (`mcp` package absent, no outbound network). Contract:
`docs/HANDOVER_2026-08-17_P18_2.md`.

---

## [2.29.2] — 2026-08-17 · Canonical production-install roadmap

PATCH planning checkpoint: merged the delivered P1–P17 AI-anatomy,
Agent-Reach, data/validation, teaching, sentiment, and Trading Workstation plans
with the owner's requested Ubuntu/Windows/Android production direction. No
runtime, signal, risk, paper, API, authentication, or packaging behavior is
claimed by this documentation release.

- Added root `ROADMAP.md` as the active P1–P22 source of truth. Older roadmap
  files remain detailed delivered/backlog records and now point to it instead
  of starting competing phase sequences.
- Chose one-authority topology: an always-on Ubuntu SKY Hub owns database,
  collectors/workers, risk gate, evidence, and audit history; browser/PWA,
  Windows `.exe`, and Android `.apk` begin as companion clients.
- Defined P18 security and platform foundation (owner auth, viewer/operator
  roles, CSRF, scoped/revocable device tokens, audit, versioned `/api/v1`,
  idempotent mutations, persisted allow-listed jobs and SSE, responsive PWA).
- Defined P19 signed Ubuntu package and operations; P20 signed Windows
  companion; P21 signed Android companion; P22 CI, signing, checksums, SBOM,
  monitoring, backups, upgrades, rollback, and support diagnostics.
- Merged the unfinished web-trader items as W1–W4 instead of dropping them:
  guided evidence, chart/replay, trader development, and reliability/mobile
  UX now build on the secure P18 boundary.
- Reconciled `TODO.md`, `README.md`, `ARCHITECTURE.md`, `BLUEPRINT.md`,
  `HANDOVER.md`, and `SESSION_STATE.md`. Next code is P18.1 authentication and
  authorization—not an installer wrapper around an unauthenticated local app.
- Deliberately left `.env.example`, runtime dependencies, `main.py`, MCP, and
  packaging ignores unchanged: configuration/dependencies are added only when
  executable P18+ code reads/uses them.

Current truth remains explicit: source installation and hardened Ubuntu service
pieces exist; signed `.deb`, `.exe`, and `.apk` releases do not. Packaging does
not add live exchange execution or move any graduation threshold. Four durable
handoff contracts pin the merged phases, platform topology, honest artifact
status, and PD1–PD8 decisions; full suite: **909 passed / 1 skipped**.

---

## [2.29.1] — 2026-08-17 · Needle 2 architecture decision

PATCH: reviewed the proposed Cactus Needle / `SKY-NODE` local trading-tool
router against the current repository and upstream Needle 2 documentation.
No runtime, model, signal, risk, or execution behavior changed.

- Added `docs/NEEDLE_REVIEW.md` with decisions **N1–N8**. The useful role is
  preserved as a conditional **external read-only MCP client** for a concrete
  offline/privacy/edge-device constraint; it is not P0/P1 infrastructure, a
  strategy brain, a calculator, or an authorization layer.
- Recorded that SKY already owns the proposed typed boundary in
  `mcp_server.ALLOWED_TOOLS` and `ai/mcp_server.py::TOOLS`; a target of 30–50
  tools would expand ambiguity and permission surface rather than add an
  architectural layer.
- Defined the only acceptable future pilot: pinned package/model/engine
  provenance, a deduplicated sealed SKY-domain call corpus, exact tool and
  argument metrics, resource measurements on target hardware, zero forbidden-
  action false accepts, fail-closed confidence routing, and shadow mode.
- Added architecture invariant #14: model confidence may select call /
  clarify / escalate / abstain, but can never approve, mutate, open the risk
  gate, count toward graduation, or reach an exchange.
- Updated the infrastructure and TODO memory plus handoff contract tests so a
  future session does not install `cactus-needle` merely to duplicate MCP.

The real canonical paper-to-graduation loop remains the active priority. No
threshold moved; root MCP remains read-only; SKY still contains no exchange
order code.

---

## [2.29.0] — 2026-08-16 · P16 prove the colour: sentiment-conditioned expectancy

MINOR: the colour is no longer a belief — it is measured. Every graded plan
and every paper trade now carries the sentiment colour the strip painted at
signal time, and the scorecard splits outcomes by it.

- **P16.1 colour buckets** (`engine/sentiment.py`) — `bucket(score)` maps the
  composite score to the exact bins the strip paints: DEEP GREEN / GREEN /
  SLATE / RED / DEEP RED (±65 deep, ±10 coloured, else slate), same
  thresholds as the labels so the legend and the measurement can never
  disagree.
- **P16.2 offline mirror** — `compute_historical()` scores sentiment from
  bar-slice inputs only (engine bull−bear scores, trend × ADX, signal action;
  renormalised over the 0.65 available weight). Funding/news/fear&greed/MTF
  are live-time inputs and are deliberately excluded — the walk can only use
  what it could see at that bar.
- **P16.3 walk clock** — `SentimentClock` walks the backtest chronologically
  and tags every plan with the colour reading at its exact bar: bucket,
  score, persistence, and the same depth formula the dashboard paints.
  Persistence accrues bar-time; flips and neutral readings reset it, exactly
  like the live strip.
- **P16.4 persisted colour** — `backtest_results`, `paper_trades` and `scans`
  gain `sentiment_bucket/sentiment_score/sentiment_intensity` (plus
  persistence on graded rows) via idempotent migration; `save_scan` stores
  the payload's sentiment block on every scan path (CLI, web, MCP), and the
  paper runner carries the signal-time colour onto the book.
- **P16.5 scorecard splits** — `by_sentiment` (the five colour buckets +
  UNKNOWN for pre-P16 rows, which are never silently re-labelled) and
  `by_sentiment_depth` (DEEP vs FRESH vs SLATE — the deepening hypothesis in
  its own split: does time-in-condition add edge?). Same block on the CLI,
  the dashboard STRATEGY SCORECARD card, and MCP. The backtest report also
  prints `by sentiment colour`.
- **P16.6 tests** — bucketing boundaries, historical-score renormalisation,
  clock accrual/reset semantics, backtester tagging on a deterministic walk,
  DB persistence + scorecard splits, legacy-row UNKNOWN handling
  (`tests/test_sentiment_validation.py`).

---

## [2.28.0] — 2026-08-16 · P15 market-sentiment colour engine: one colour is the market

MINOR: the desk reads the market's condition from ONE colour. Bullish paints
green — and the longer the same bullish sentiment holds, the deeper the green
gets; bearish paints red and deepens to strong red the longer it holds;
neutral is slate (no colour = no trade). A neutral reading resets the clock,
and the clock survives dashboard restarts because history is persisted.

- **P15.1 sentiment engine** (`engine/sentiment.py`) — composite score in
  [-100, +100] blending what the brain already computes: engine bull−bear
  scores (50%), MTF alignment (20%), trend × ADX strength (10%), funding
  crowding (5%), news sentiment tally (5%), fear & greed (5%), signal action
  × confidence (5%). Every input is weighted and exposed as `parts` so the
  colour is always explainable.
- **P15.2 time duration = colour depth** — `depth = strength × (0.6 +
  0.4 × persistence)`; persistence reaches 1.0 after 180 minutes of the same
  direction. Fresh strong readings paint bright; only time in the same
  condition paints deep (green → deep green, red → strong red). Gaps longer
  than 15 min don't count as persistence.
- **P15.3 persisted history** (`data/database.py::sentiment_history`) — one
  row per symbol/timeframe/minute, deduped so a 30s auto-refresh can never
  double-count the clock; `engine/sentiment.py::current_sentiment` computes →
  records → measures duration in one call, never raising into the scan path.
- **P15.4 dashboard colour surfaces** — fixed left-edge mood bar (the colour
  on every tab), a sticky SENTIMENT strip above the dashboard (label, score,
  held-for duration, colour depth, needle on the red→slate→green scale), and
  a full-width MARKET SENTIMENT card on Overview with the weighted-input
  table, sparkline of recent readings, and the colour legend. `GET
  /api/sentiment?symbol=&tf=` exposes the same block as JSON; the scan
  payload now carries `sentiment` for every symbol/timeframe. A payload
  without the block still renders via a client-side estimate.
- **P15.5 tests** — `tests/test_sentiment.py` (scoring, duration caps,
  direction-break resets, colour deepening, DB persistence) and new
  dashboard-JS harnesses that pin the strip/mood-bar colour wiring for
  bullish, bearish, neutral, and fallback payloads.

---

## [2.27.0] — 2026-08-16 · P14 operate the loop: daily ritual + one loop-health number

MINOR: the project-review answer. Success is operating the paper→graduation
loop, not another indicator. One composed number, four surfaces, no new cook.

- **P14.1 loop health** (`brain/agent.py::loop_health`) — composes
  `desk_status()` + `readiness_strip()` + `paper_progress()` (canonical live
  book; simulator excluded). Answers: how many real paper trades, what is
  net expectancy, how each primary setup is doing, is the graduation bar
  moving. Ritual: doctor --strip → daily → risk → act + journal prompt.
- **P14.2 daily CLI** — `python main.py daily` (alias `loop-health`).
  `--json` dumps the payload; `--brief` optionally adds the morning briefing.
  Exit 0 (a report, not a gate).
- **P14.3 same number everywhere** — `GET /api/loop-health` (never 500),
  root MCP `loop_health` (SERVER_VERSION 1.11.0), SDK `cryptobrain_loop`,
  `agent ask "how is the loop?"`, dashboard LOOP HEALTH card.
- **P14.4 P13 web follow-up** — KEY LEVELS A/B/C card, POSITION MANAGER on
  LIVE SIGNAL / pending / coach, coach JS joins `five_levels` as `list[str]`.

No thresholds moved. No order placed. Micro-live still blocked.
Suite green: **815 pass / 1 skip** (+8).

---

## [2.26.0] — 2026-08-16 · P13 the desk teaches: five-question coach, A/B/C key levels, position-manager card

MINOR: the first build of **P13**, the decision-support phase. It adopts the
four ideas that survived the external ChatGPT desk-review
(`docs/TRADING_DESK_CHATGPT_REVIEW.md`) without leaving the main road — no new
data sources, no new indicators, no new risk surface. Three code additions +
one documented invariant:

- **P13.1 five-question coach** (`brain/coach.py::five_levels`) — the coach now
  answers the professional ladder *Observation → Interpretation → Opportunity
  → Decision → Action* in plain English, with the per-setup measured
  expectancy from the learning loop (`_setup_evidence`) when the DB has
  samples, and an honest "no graded samples yet" otherwise. Wired into
  `python main.py coach`.
- **P13.2 A/B/C key-level ranking** (`brain/trading_intelligence.py::rank_key_levels`) —
  the desk report now ships `key_levels`: A = liquidity & major structure
  (sweeps, pools, equal highs/lows, swings), B = decision zones (order blocks,
  plan trigger/entry), C = reference levels (FVGs, VWAP, POC, stop, TPs),
  sorted by distance from price and capped per tier — no invented levels.
- **P13.3 approval-time position-manager card** (`main.py cmd_approve`) — before
  you click approve, the CLI prints HOLD / REDUCE / TRAIL / EXIT guidance for
  that exact plan, built by `brain/coach.py::management_checklist`.
- **P13.4 no-martingale invariant** — BLUEPRINT.md Golden Rule 6 and the
  playbooks module docstring: risk budget immutable, trading-DCA/martingale
  forbidden, only Step-4 *investment* accumulation allowed. Already true in
  code; now a stated invariant.

No thresholds moved. Suite green: **807 pass / 1 skip** (+10).

## [2.25.0] — 2026-08-16 · P12.18 the net anchor at the hard limits

MINOR: finish what P12.8 started. P12.6 restated the desk's numbers net of
costs and P12.8 set the doctrine — *a measurement only matters where something
acts on it* — then walked the net anchor into the two decision sites it found
(`multiplier_from_score()`, `setup_proven()`). It stopped short of the **hard
risk limits** in decision B6, which act harder than anything else in the
system: they are the desk's stop-loss on itself.

### The gap

`closed_pnl()` (daily/weekly limits), `drawdown()` (the ladder) and
`brain/metrics.py` (the business scorecard's equity, expectancy, profit
factor, win rate and streaks) all judged **gross** `rr_achieved`.

This bites hardest on the live paper book, because `close_paper_trade()`
writes `rr_achieved` only — **every live row has `rr_net IS NULL`**. Costs for
those rows existed solely as a compute-on-read step (`_net_outcome()`, already
used by the Monte Carlo surfaces) that the limits never took.

Measured with the repo's own cost model:

| Surface | Gross reading | Net reality |
|---|---|---|
| Daily limit, 8 × −0.4R | −0.80% → **open** | −1.09% → past the 1.0% limit |
| Weekly limit, 16 × −0.4R | −1.60% → **open** | −2.19% → past the 2.0% limit |
| Drawdown, 32 × −0.5R | 4.00% → `normal` | 5.18% → `reduce_risk` |
| Scorecard, 6 × +1.5R / 8 × −1.0R | **+0.071R (an edge)** | **−0.076R (a losing book)** |

The loss limits failed **open**: a desk past its limit once fees were paid
read comfortably inside it and kept trading.

### Fixed

- `data.costs.net_r_of_row()` is the single definition of a row's net R:
  stored `rr_net` wins, otherwise costs are computed from the row's own
  levels, symbol and holding time; a row with no gross R contributes 0.0.
  It lives beside the cost model so the risk gate, scorecard and analytics
  cannot drift apart (invariant #10).
- `closed_pnl()`, `drawdown()`, `_equity_curve()` and `_metrics()` all read it.
  A **win is now a net win** — a trade that cleared its target but not its
  fees is no longer counted as a winner.
- `brain.analytics._net_outcome()` delegates to the shared helper.
- `closed_pnl()` additionally reports `gross_r_sum`, `gross_pct` and `cost_r`,
  and `status_text()` prints the gross figure and cost drag beside the net
  percentage, so the number can never be mistaken for a gross read.

### Unchanged

Every threshold (`MAX_DAILY_LOSS_PCT`, `MAX_WEEKLY_LOSS_PCT`, the ladder rungs,
the graduation bar) is untouched — only the number compared against them is now
the honest one. A **cost-free book (`rr_net == rr_achieved`) behaves exactly as
before**, pinned by controls in every group. P12.11–P12.17 source isolation,
XAU research-only status and the no-order-placement contract are unaffected.

### Verification

- `tests/test_net_limits.py` — 14 new regressions.
- `ops/probes/p12_18_netlimits_probe.py` — reproduction harness; all six cases
  (A–F) behave as specified, exit 0.
- Four pre-existing tests pinned gross arithmetic and were updated to
  cost-neutral fixtures (`rr_net == rr_achieved`) so they keep testing what
  they were written to test — source isolation and date arithmetic — rather
  than being silently rewritten by the cost model.
- The P12.14–P12.17 probes still exit 0; full suite **797 passed, 1 skipped**;
  compileall and `pip check` pass.

---

## [2.24.1] — 2026-08-16 · P12.17 week-boundary risk-gate crash

PATCH: fix a latent `ValueError` that took the **entire risk gate** offline for
roughly one day in ten.

### The bug

`brain.risk_gate._week_start_utc()` computed Monday 00:00 UTC as:

```python
start = start.replace(day=start.day - start.weekday())   # Monday
```

`datetime.replace()` cannot cross a month boundary. Whenever the current week
began in the previous month, `start.day - start.weekday()` was zero or
negative and the call raised `ValueError: day is out of range for month`. On a
Monday-start week that is **every week spanning a month end — 38 days of
2026**, including 1 January (whose week begins in the previous *year*).

The weekly loss limit is one of the two hard limits in decision B6, so this was
never cosmetic. On those dates `daily_weekly()`, `drawdown()`'s caller
`evaluate()`, `status_text()` and every downstream surface raised instead of
answering, and each caller's behaviour depended on whether it happened to sit
inside a `try`:

- `main.py approve` propagated the `ValueError` at the human instead of
  returning a decision;
- the paper runner failed closed but recorded the nonsense reason
  `"day is out of range for month"` against the scan rather than a risk reason;
- `brain.immune.check_risk_system()` — the diagnostic whose entire job is to
  notice a broken risk system — had **no** `except` around the gate, so it
  raised and took `run_health_check()` down with it, reporting nothing at all.

A gate that raises is neither open nor closed, which is the most dangerous
state a risk control can occupy.

### Fixed

- `_week_start_utc()` subtracts the weekday as a `timedelta`, which crosses
  month and year boundaries correctly. Verified by an exhaustive sweep of
  every date from 2024 through 2029 (6,576 datetimes): always the correct
  Monday, never a crash.
- `check_risk_system()` now catches an unanswerable gate and reports
  `CRITICAL` with the underlying error, so a broken risk system surfaces as a
  loud diagnostic instead of a stack trace. `run_health_check()` keeps
  reporting its other checks.

### Unchanged

Every threshold and limit, `_day_start_utc()`, the drawdown ladder, the
graduation bar, P12.11–P12.16 source isolation, XAU research-only status, and
the no-order-placement contract. Losses that fall in the previous-month part of
the current week still count toward the weekly limit — pinned by a regression.

### Verification

- `tests/test_week_boundary.py` — 19 new regressions.
- `ops/probes/p12_17_weekstart_probe.py` — reproduction harness; all six cases
  (A–F) behave as specified, exit 0.
- The P12.14/P12.15/P12.16 probes still exit 0; full suite **783 passed, 1
  skipped**; compileall and `pip check` pass.

---

## [2.24.0] — 2026-08-16 · P12.16 open-book source isolation

MINOR: the source boundary reaches the **open** book. P12.11 → P12.15 walked
provenance through every surface that reads *decided* paper trades —
calibration and setup-proof, the global graduation gate, the discipline
criterion, then every live risk control and the scorecard execution metric —
but stopped at the closed book. `open_exposure()` and `active_paper_trades()`
still selected `status IN ('WAITING_ENTRY','OPEN')` with **no** `sim_key`
filter and **no** `source_key` filter, so the positions the desk was told it
was carrying pooled research imports and simulator orphans into live exposure.

### The gap (measured on `731119d`, all six cases reproduced)

- **The portfolio veto failed CLOSED.** One open `dukascopy:spot:bid` row in
  BTCUSDT filled a slot in the live crypto risk bucket, so
  `portfolio_veto(db, "BTCUSDT", "BUY")` refused a real live trade with
  "correlated exposure" against a book that was flat. Research must neither
  unlock nor block (P12.13); here it blocked.
- **The bucket risk cap failed CLOSED** the same way: two research positions
  read `n_open=2 / planned_risk_pct=1.0`, exhausting
  `CRYPTO_BUCKET_MAX_TRADES` and `MAX_CRYPTO_EXPOSURE_RISK_PCT`.
- **Interrupted simulator runs leaked live exposure.** The simulator inserts
  its samples `status='OPEN'` and closes them in the same pass, so a crash
  left `sim_key IS NOT NULL` orphans that read as live positions permanently
  and held real risk slots.
- **The paper runner polled research and simulator rows as live work.**
  `active_paper_trades()` handed them to a runner that fetches candles from the
  *canonical live* client, so a Dukascopy XAU setup could be priced off Binance
  candles and then opened, closed and journaled onto the live book.
- **Reported exposure overstated the book:** a desk carrying one live position
  reported six across the CLI, the agent briefing, the watchdog agent and the
  dashboard.

### Fixed

- `SignalDB.live_open_rows()` is now the single definition of the live *open*
  book — active (`WAITING_ENTRY`/`OPEN`), `sim_key IS NULL`, canonical-live
  (`COALESCE(source_key,'')=''`, legacy NULL rows kept) — the open-side twin
  of P12.15's `live_book_rows()`.
- `open_exposure()` restricts its paper-trade half to that population via the
  new `_open_book_clause()` helper; its approved-scan half is unchanged, since
  a scan awaiting enrolment has no provenance yet and is a live intention.
- `active_paper_trades()` defaults to the live open book, so the runner polls
  only positions it can legitimately price. `include_all_sources=True`
  restores the unfiltered read for maintenance/inspection callers.
- The watchdog agent reads `live_open_rows()` instead of raw SQL, so simulator
  orphans no longer raise stale-entry alerts about phantom desk positions.
- `paper_trade_stats()` keeps its broad inventory totals (they are how a
  reviewer sees what the store holds) and adds `live_open`; the CLI paper
  summary and `agent ask` print the live count whenever it differs.

### Unchanged

Every threshold and cap (`CRYPTO_BUCKET_MAX_TRADES`,
`MAX_CRYPTO_EXPOSURE_RISK_PCT`, the loss limits, the drawdown ladder, the
graduation bar), the decided-book surfaces from P12.11–P12.15, the broad paper
inventory and journal reports, the source-key algebra, XAU research-only
status, and the no-order-placement contract.

### Verification

- `tests/test_openbook_isolation.py` — 14 new regressions.
- `ops/probes/p12_16_openbook_probe.py` — reproduction harness; all six cases
  (A–F) behave as specified, exit 0.
- The P12.14 and P12.15 probes still exit 0; full suite **764 passed, 1
  skipped**; compileall and `pip check` pass.

---

## [2.23.4] — 2026-08-16 · P12.15 execution-metric follow-up

PATCH: finish the P12.15 live-book boundary inside the business scorecard.
P12.15 already isolated its P&L, equity, risk, MC and MAE/MFE populations, but
its nested `execution` field still read the broad `violation_rate()` journal
report. Simulator and research journals could therefore move a discipline
number shown beside an otherwise canonical-live scorecard.

### Added / Fixed

- `brain.journal.live_execution_stats()` computes the scorecard execution
  block over decided, non-simulator, canonical-live paper trades only,
  including legacy NULL provenance rows.
- `business_metrics()` now reads that source-correct block. Its existing
  `n`/`violations`/`violation_rate` journaled-entry keys remain compatible;
  eligible, journaled, missing-journal, compliant and source fields expose the
  population behind the number.
- `format_metrics()` reports missing live journals instead of hiding them.
- Two regressions prove research/simulator journals cannot move the live
  execution metric and missing canonical journals remain visible.
- The broad `violation_rate()` report, `graduation_discipline()`, all
  thresholds, source-key algebra, XAU status and no-order-placement contract
  are unchanged.

### Reconciled

- Updated the durable session, TODO, architecture, roadmap, README and
  operations documentation with the merged PR #38 state and the ordered next
  work: real-host XAU evidence, canonical P11 paper proof, then TODO-8 admin
  verification. This checkout still cannot claim real-host evidence.

### Verification

- Full suite: **750 passed, 1 skipped** (+2).
- Compileall, `pip check`, wheel gate and P12.14/P12.15 probes pass.

---

## [2.23.3] — 2026-08-16 · P12.15 live-book source isolation

PATCH: the live *risk controls* are now isolated to the canonical live book
the way P12.13/P12.14 isolated the graduation gate. Every one of them read
`decided_paper_rows(exclude_sim=True)` with no provenance filter — the
P12.11 source boundary never reached them — so a research book (e.g.
`dukascopy:spot:bid`) pooled straight into the daily/weekly loss limits, the
drawdown ladder, the Kelly advisory, the Monte Carlo ruin/equity reads,
MAE/MFE review and the business scorecard. Measured on `fdfc9f4`: 5 real
canonical losses today (−1.25%, past the student 1.0% daily limit) plus 6
research wins read `+7R / not blocked` — the loss limit failed **open**; a
24-loss canonical streak (6.0% drawdown, `reduce_risk`) interleaved with
research wins read `0.25% / normal`; and 8 research-only losses **blocked** a
live desk that had not traded at all. No threshold changed; every control is
strictly truer to the book it protects.

### Added

- `SignalDB.live_book_rows()` — the single definition of the live paper
  book: decided (`TP_HIT`/`STOP_LOSS`), non-simulator (`sim_key IS NULL`),
  canonical-live (`COALESCE(source_key,'')=''`, legacy NULL rows included).
  One computation, many surfaces (invariant #10).
- `engine.hidden_alpha.kelly_from_rows()` — Kelly advisory computed from the
  live book's actual trade rows, judged **net of costs** where `rr_net` is
  recorded (P12.8, gross fallback). A decided book with no net winners
  stands aside at 0.0% instead of pleading "insufficient evidence"; an empty
  book suggests nothing. Advisory only — nothing auto-executes on it.
- Probe harness `ops/probes/p12_15_livebook_probe.py` — six executable
  cases (A–F) proving each failure mode closed and the control book
  unchanged; exits non-zero on any regression.
- `tests/test_livebook_isolation.py` — 12 regressions pinning every live
  control to `live_book_rows()` and the honest canonical book to its exact
  pre-P12.15 numbers.

### Fixed

- Daily/weekly loss limits (`brain.risk_gate.closed_pnl`) fail closed:
  research wins can no longer offset real canonical losses past the limit,
  and research losses can no longer trip a limit the live book never hit.
- Drawdown ladder (`brain.risk_gate.drawdown`): research wins can no longer
  refill a real losing streak before it reaches `reduce_risk` /
  `stop_and_review`, and research losses cannot deepen a drawdown the desk
  never took.
- The Kelly advisory was silently dead on any populated book:
  `risk_gate.evaluate()` and `trading_intelligence` fed raw `paper_trades`
  rows into `kelly_from_progress()`, which expects `paper_progress()`
  aggregates — `KeyError('wins')` was swallowed by a blanket `except` into a
  permanent `{"note": "unavailable"}`, so the dashboard Kelly card never
  rendered with data. Both call sites now use `kelly_from_rows()` over
  `live_book_rows()`.
- `brain.analytics.monte_carlo_ruin_table` / `monte_carlo_equity` /
  `mae_mfe_summary` and `brain.metrics.business_metrics` / `_equity_curve`
  read the live book only: a research series can neither flatter nor spoil
  the desk's survivability, review or business numbers.

### Unchanged

- Every threshold and cap: the loss limits, the drawdown ladder rungs, the
  Kelly clamp (`KELLY_MAX_RISK_PCT`), the graduation bar.
- `decided_paper_rows()` keeps its exact signature and behaviour for
  explicit callers; the scorecard's research surfaces
  (`rows_from_paper_db(..., source_key=…)`, `by_source`) still inspect any
  series on demand.
- P12.11 source-key algebra, P12.13/P12.14 graduation isolation, XAU
  research-only status, and the no-order-placement contract.

### Verification

- Full suite **748 passed / 1 skipped** (+12); probe harness exits 0 with
  all six cases behaving as specified; `compileall`, `pip check` and the
  v2.23.3 wheel gate pass.

---

## [2.23.2] — 2026-08-16 · P12.14 graduation discipline isolation

PATCH: the discipline half of the graduation gate is now isolated the way
P12.13 isolated the performance half. Compliance was computed from
`violation_rate(db)`, which reads every `journal_entries` row with no join to
`paper_trades` and no provenance filter, so the 90% criterion could pass
without a real, fully journaled canonical paper book. The threshold, the
performance criteria, the source-key algebra and the no-order-placement
contract are unchanged; the gate is strictly narrower.

### Added

- `brain.journal.graduation_discipline(db)` — the single discipline
  computation. Reads decided (`TP_HIT`/`STOP_LOSS`), non-simulator
  (`sim_key IS NULL`), canonical-live (`COALESCE(source_key,'')=''`, legacy
  NULL rows included) paper trades LEFT JOINed to their journal answer, and
  reports `eligible`, `journaled`, `missing_journals`, `violations`,
  `compliant`, `compliance`, `source_key`, `source`.
- `SignalDB.discipline_rows()` — the eligible-population query behind it.
- `brain.journal.describe_discipline()` and a `discipline` line on
  `desk` / `format_graduation()` / the dashboard desk card, so a passing or
  failing criterion can be audited without a second query.

### Fixed

- Simulator journals can no longer satisfy graduation compliance: a machine
  grind that auto-writes `followed_rules=1` now yields `eligible=0`,
  `compliance=None` (unproven) instead of a 100% pass.
- Non-canonical research journals can no longer move canonical compliance
  (previously 19 clean `dukascopy:spot:bid` entries outvoted the one real
  canonical trade that broke the rules: 0.95 PASS instead of 0.0).
- `followed_rules=None` counts as a missing journal, not as compliance.
- Missing journals fail **closed**: `compliance = compliant / eligible`, so
  30 decided real trades with 1 journaled reads 0.033, not 1.0.
- `graduation_status(..., discipline=...)` treats the payload as
  authoritative and echoes it under `graduation["discipline"]`; the CLI
  simulator gate, `agent ask`, `graduation_report()` and `desk_status()`
  (desk, `/api/desk`, dashboard, MCP) all read that one computation.

### Unchanged

- `GRADUATION_CRITERIA["compliance"] = 0.90` and every performance criterion.
- The general journal report (`violation_rate()` / `journal_stats()`) keeps
  feeding `/api/risk`, `/api/learning`, `business_metrics()` and the journal
  CLI over every recorded entry.
- XAU stays research-only; nothing places an order.

Reproduction: `ops/probes/p12_14_discipline_probe.py`; contract:
`docs/HANDOVER_2026-08-16_P12_14.md`. Suite: **736 pass / 1 skip** (+10).

---

## [2.23.1] — 2026-08-16 · P12.13 graduation source isolation

PATCH: close the last source-provenance leak in the permission path. P12.11
separated calibration and setup proof, but global graduation still pooled
research and canonical outcomes. Thresholds are unchanged; the gate is now
strictly narrower.

### Fixed

- `data.simulator.paper_progress()` filters both backtest and paper outcomes to
  canonical Binance spot (`COALESCE(source_key, '') = ''`). Legacy NULL rows
  remain included by the P12.11 compatibility contract.
- Progress rows now expose their source, and `grind_verdict()` /
  `graduation_status()` reject explicit non-canonical evidence even if every
  count and performance criterion passes.
- Research wins can no longer unlock live graduation; research losses can no
  longer block it. Research books remain visible via source-filtered scorecard
  surfaces.
- Added three regression tests covering bid-only/Bybit isolation in both
  directions, legacy NULL compatibility, and the direct evaluator veto.

### Corrected

- Closed stale TODO-7 instructions: root `.github/workflows/ci.yml` already
  contains both the offline suite and wheel gate; GitHub Actions run
  `31907327643` passed both jobs on merged P12.12/`main` at `5345e9e`.
- Updated the handoff to record PR #35 as merged and this session's actual
  branch/base instead of the predecessor branch and pre-merge commit.
- Removed the obsolete nested `docs/.github/workflows/ci.yml` job-spec copy.
- Kept TODO-8 as an unverified admin action: the GitHub integration receives
  HTTP 403 when reading branch protection, so no protection claim is made.

### Verification

- Full offline suite: **726 passed, 1 skipped**.
- Compileall, dependency check, and v2.23.1 wheel duplicate-entry gate pass.
- No graduation threshold, XAU promotion status, or order-placement
  capability changed; source eligibility is strictly tighter.

---

## [2.23.0] — 2026-08-16 · P12.12: PAXG-vs-XAU promotion-evidence dossier

MINOR: add the missing read-only measurement between separately stored Binance
PAXG and Dukascopy XAU histories. This is an evidence build, not micro-live:
the repository graduation gate is still closed and no explicit approval has
been given.

### Added

- `data/gold_basis.py`:
  - reads `binance/spot/PAXGUSDT` and `dukascopy/spot/XAUUSD` independently;
  - rejects ambiguous/missing Dukascopy bid-or-ask provenance;
  - aligns exact UTC candle-open timestamps only, with no resampling,
    interpolation, forward fill, calendar synthesis, or history pooling;
  - reports overlap coverage, USD/percent/bps basis distribution, median/MAD,
    price/return correlation, tracking error, and a SHA-256 fingerprint of the
    aligned observations;
  - fails closed when overlap is below the declared minimum.
- Sealed-envelope inspection verifies that the latest payload:
  - matches the expected XAU symbol and timeframe;
  - matches its envelope fingerprint;
  - uses the current unchanged graduation criteria;
  - clears train, validation, sealed-OOS, and recent windows;
  - exposes history and reseal counts for human review.
- `python main.py xau-evidence [--tf 15m] [--bars 12000]
  [--min-overlap 100] [--json]` builds one promotion dossier from the two
  evidence records. There is deliberately no approve/promote option.
- `docs/XAU_PROMOTION_EVIDENCE.md` records the real-data-host procedure,
  exact-alignment contract, quote-currency caveat, and promotion gates.
- `tests/test_gold_basis.py` covers alignment, metrics, coverage, provenance,
  seals, source/criteria mismatch, separate store keys, CLI failure on an
  empty checkout, and the non-promotion contract.

### Safety contract

Every dossier remains `RESEARCH_ONLY`. Even when basis measurement and sealed
OOS pass, the command reports `human_approval=OPEN`, `xau_tradeable=false`, and
`micro_live_unlocked=false`. Synthetic fixtures verify mechanics only; they are
not real basis or OOS evidence. Micro-live still requires the unchanged global
graduation bar and a separate explicit user approval.

### Verification

- P12.12 + validation + handoff focus: **54 passed**.
- Full suite: **723 passed, 1 skipped** (MCP extra installed).
- Compileall and dependency checks pass; v2.23.0 wheel builds with no duplicate
  entries.
- Clean-checkout CLI: no matched rows, seal `MISSING`, approval `OPEN`,
  tradeable/micro-live false, exit 1 — no evidence manufactured.

---

## [2.22.0] — 2026-08-16 · P12.11: source provenance in saved keys (Dukascopy blocker #3)

MINOR: make the price series a graded row came from part of its identity, so
two different markets can never pool into one calibration entry. Closes the
**last** of the three blockers recorded against the Dukascopy XAU research
book — all three are now closed.

### The problem
Every decided row was filed under `plan_type` or `plan_type::regime` and
nothing else. A row graded on Binance BTCUSDT spot candles and a row graded on
a bid-only Dukascopy XAUUSD import landed in the **same** calibration entry,
so a research backtest on a venue the desk does not trade could move the
confidence multiplier applied to live signals. The only protection was a
human remembering not to type `--save`.

Measured on a seeded book (300 rows per series): the live entry alone scores
`E +0.46R → net +0.29R`, multiplier `×1.07`; pooling a `+3.58R` bid-only gold
research book into the same key inflated that number. They are now two
entries, and the live one is byte-identical to a live-only run.

### Added
- **`data/provenance.py`** — the source-key algebra. `source_key()`,
  `parse_source_key()`, `normalize()`, `is_canonical()`, `is_one_sided()`,
  `describe_source()`, `split_profile_key()`, `provenance_of_frame()`.
  A source key is `exchange:market[:price_type]`, and the canonical live
  series (Binance spot, two-sided) is deliberately the **empty string**.
- **Provenance columns** — `exchange`, `market`, `price_type`, `source_key` on
  `backtest_results` and `paper_trades`; `source_key` on `calibration`. All
  added by idempotent migration.
- **`SignalDB.source_inventory()`** — decided-row counts per source series
  across both books, with `mixed` / `canonical_only` / `one_sided` flags.
- **Scorecard `by_source` split + `sources` inventory** — a pooled book is
  reported as pooled, and one-sided series are flagged research-only.
- **`--source-key` / `?source_key=` / MCP `source_key`** — score one series:
  `live`, `exchange:market[:bid|ask]`, or `all` (default).
- **`docs/SOURCE_PROVENANCE.md`** — the full design note.

### Changed
- **`brain/calibrator.profile_key()`** takes a source key and appends
  `@source` for non-canonical series only, so **every pre-existing key is
  byte-identical**. `build_profile()` groups by source and marks one-sided
  entries `research_only`.
- **`engine/calibration_hook.apply_calibration()`** — the live path resolves
  **canonical keys only**, narrowing `plan_type::regime` → `plan_type` within
  one source and never falling back across sources. A research entry's boost
  *and* its filter are both unreachable from a live scan.
- **`brain/risk_gate.setup_proven()`** counts evidence on one series
  (default: live) and can never call a one-sided series proven.
- **`data/store.StoreClient`** stamps provenance on the frame; the simulator
  and `backtest --save` propagate it to every stored row.
- **`python main.py learn`** lists the source series in the learning store.
- MCP server `1.9.0 → 1.10.0`.

### Unblocked
- `--save` on a Dukascopy XAU backtest is now **permitted**: its rows land in
  their own calibration keys and cannot recalibrate the live PAXG proxy.
  Promotion of that series remains a separate, human-approved decision.

### Safety direction
Strictly additive and strictly tighter. Canonical keys, legacy NULL-provenance
rows (which *are* the canonical series), crypto output and the graduation bar
are all unchanged; the change can only *withdraw* trust from a research series,
never grant it. No existing test was modified.

### Tests
+23 in `tests/test_provenance.py` — key algebra, persistence, the
pooling-regression proof, live-isolation of both boost and filter, legacy
compatibility, the proven gate, and scorecard reporting/filtering.
Suite: **681 → 704 pass / 1 skip**.

---

## [2.21.0] — 2026-08-15 · P12.10: XAU bid/ask cost model (Dukascopy blocker #2)

MINOR: teach `data/costs.py` that gold instruments trade on spot markets with
spread-based costs, not crypto-perp taker fees and funding. Closes blocker #2
of the three recorded against the Dukascopy XAU research book.

### The problem
`calculate_trade_cost()` used a default `CostModel()` with `market="perp"`,
taker fees (0.05%/side) and funding — appropriate for crypto perps but not
for spot gold. A bid-only XAUUSD backtest was costed with crypto assumptions,
giving a misleading cost picture. The existing `SPREADS["XAUUSD"]` entry
existed but was never auto-selected.

### Added
- **`cost_model_for_symbol()`** — symbol-based cost model resolver. When no
  explicit `CostModel` is passed, gold instruments (symbols starting with
  `XAU` or `GOLD`) get a spot-market model with zero funding, a small ECN
  broker commission (`DEFAULT_GOLD_COMMISSION_PCT = 0.005%` per side), and
  spread as the primary cost via the existing `SPREADS` dict. Everything
  else stays on the crypto-perp default.
- **`is_gold_symbol()`** — prefix-based gold detection.
- **`GOLD_SYMBOL_PREFIXES`** — `("XAU", "GOLD")`.
- **`DEFAULT_GOLD_COMMISSION_PCT`** — 0.005% per side, aligned with common
  ECN spot-gold brokers (~$5 per $100k notional).
- **Auto-detection** in `calculate_trade_cost()` — when `cost_model` is
  `None`, the function now calls `cost_model_for_symbol(symbol)` so every
  XAUUSD call automatically uses gold-specific costs. An explicit
  `cost_model` argument still overrides auto-detection.

### Safety
- **Opt-in by symbol, never by guess.** Only symbols with an XAU or GOLD
  prefix get the gold model. BTCUSDT, ETHUSDT, PAXGUSDT (tokenized gold)
  keep the crypto-perp default unchanged.
- **Explicit model always wins.** Passing a `CostModel` argument disables
  auto-detection, preserving the existing test contracts and any caller
  that wants to override.
- **Numbers are unchanged for crypto.** BTC/ETH costs are byte-identical to
  the pre-2.21.0 behaviour.
- **No new dependency, no surface change.** The model is internal to
  `data/costs.py`; the cost-calculation pipeline (`_evaluate()` in the
  backtester, `trade_stats()` in the scorecard) receives the corrected costs
  without any import or signature changes.
- Full suite: **681 passed, 1 skipped** (+10 in `tests/test_costs.py`).

### Documentation
- `docs/DUKASCOPY_XAU_ADAPTER.md`: blocker #2 (bid/ask cost model) marked
  **closed**. Two of three blockers now closed; one remains (calibration-key
  source provenance).
- Module docstring updated to describe the P12.10 gold cost model.

---

## [2.20.0] — 2026-08-15 · P12.9 market calendars: scheduled closure is not a gap

MINOR: teach the data layer that some venues close. Closes blocker #1 of the
three recorded against the v2.19.0 Dukascopy XAU research book.

### The problem
Every quality check in SKY assumed a 24/7 market, so "the venue was shut" and
"our collection broke" were the same event. A correct, complete week of spot
gold contains ~53 hours of scheduled closure — read as a 30%+ gap fraction and
an unusably stale feed, which **quarantined a healthy series** and rolled the
whole desk to *not ready*.

### Added
- **`data/calendar.py`** — a `MarketCalendar` protocol with two implementations:
  `crypto-24x7` (always open) and `xau-otc`, the DST-aware OTC gold week
  (Sun 18:00 ET open, Fri 17:00 ET close, 17:00–18:00 ET daily break, 1 Jan and
  25 Dec closed), resolved through stdlib `zoneinfo`.
- Trading-time counting helpers: `expected_bars()`, `open_bars_between()`,
  `closed_bar_count()`, `split_by_session()`, `calendar_for()`, `get_calendar()`.
- **CLI `python main.py calendar`** — is the venue open at an instant, and how
  much of a stored series' span was scheduled closure (`--series`), with
  `--calendar`, `--at`, `--root` and `--json`.
- `docs/MARKET_CALENDAR.md`.

### Changed
- `data/gaps.detect_gaps()` takes an optional `calendar`: a span that is
  entirely a scheduled closure is not a gap, and a partial one counts only the
  OPENs the venue owed.
- `data/quality.checks_on_frame()` takes an optional `calendar`; on a session
  venue `expected` and `age_mult` are measured in **trading bars** (a shut
  market cannot age a series) and the health dict carries `calendar`,
  `market_open` and `closed_bars`.
- `series_health()` / `series_item()` resolve the calendar from the series
  identity, so the readiness pillar inherits it; `verdict_for()` reports
  `market closed — clean` instead of a false alarm and says `trading bars`.
- `backfill_from_csv()` reports `calendar` and `closed_session_bars`, and its
  `gaps_found` no longer counts the gold weekend; `backfill --from-csv` prints
  the calendar and a calendar-aware `gaps_remaining`.

### Safety
- **Opt-in by venue, never by guess.** Only `dukascopy` + an XAU symbol gets the
  gold week. Unknown venues, unknown symbols and Binance `PAXGUSDT` (a genuine
  24/7 token proxy) all keep the crypto calendar, so a wrong calendar can never
  hide a real gap.
- **Crypto numbers are unchanged** — `detect_gaps(f, tf)` equals
  `detect_gaps(f, tf, CRYPTO)`, and the pre-P12.9 branch runs whenever
  `always_open` is true.
- **Real failures still fail**: a hole inside a session, a series stale during
  open hours, and corrupt OHLC all still quarantine.
- This does not open the risk gate. Dukascopy XAU stays research-only until
  bid/ask spread + XAU net costs and calibration-key source provenance land.
- Full suite: **671 passed, 1 skipped** (+35 in `tests/test_calendar.py`);
  wheel gate builds `cryptobrain-2.20.0-py3-none-any.whl` with no duplicates.

---

## [2.19.0] — 2026-08-15 · optional Dukascopy XAU research adapter

MINOR: adapt the useful acquisition boundary from `dukascopy-node` without
adding a Node runtime dependency or a second data/strategy architecture.

### Added
- `backfill --from-csv ... --csv-source dukascopy --price-type bid|ask`
  accepts the documented dukascopy-node OHLC CSV shape
  (`timestamp,open,high,low,close,volume`) through SKY's existing SHA pin,
  sanity, dedupe, gap, normalization, and Parquet boundaries.
- Canonical candles carry `price_type`; old partitions are additively coerced
  on read and upgraded on their next write.
- Dukascopy imports are isolated as `dukascopy/spot/XAUUSD` with
  `source=dukascopy_csv`; they cannot overwrite or masquerade as Binance/PAXG.
- Store-backed `backtest` and `simulator` accept `--exchange`, matching the
  existing validate/scorecard/quality venue selection.
- `docs/DUKASCOPY_XAU_ADAPTER.md` records the pinned acquisition/import flow
  and the gates still required before saved calibration: XAU market calendar,
  bid/ask spread costs, and source provenance in learning keys.

### Safety
- Binance remains canonical for BTC/ETH. Existing live XAU/PAXG behavior is
  unchanged. Dukascopy is acquisition-only and research-only.
- Tick ingestion, ML prediction, new strategy families, and automatic source
  pooling were deliberately not added.
- Full suite: **636 passed, 1 skipped**.

---

## [2.18.1] — 2026-08-15 · expectancy-anchor class audit

PATCH: close the remaining simulator path after P12.8's net-anchor fix.

### Fixed
- **`data/simulator.py` → `grind_verdict()`** now recomputes the micro-live
  sample proof from counts and **net expectancy** instead of trusting a
  caller-supplied/stale `proven` flag. Its gap explanation also compares
  `E_net`, so a gross-positive/net-negative setup no longer reports the
  contradictory `all targets met` while remaining blocked.
- **`paper_progress()`** now falls back from net to gross only on `None`.
  Exact-zero net expectancy, net wins, and net win/loss R are valid measured
  values; truthiness fallback previously replaced zero with gross and could
  flip the sign of the proof.
- The simulator grind table now labels and displays `E_NET` beside its
  net-derived `PROVEN` marker.

### Audit and verification
- `docs/EXPECTANCY_ANCHOR_AUDIT_2026-08-15.md` inventories every executable
  expectancy comparison against zero or a threshold and records its anchor.
- Added regressions for a stale `proven=True` on a cost-flipped setup and for
  exact-zero net values. Suite: **633 passed, 1 skipped**.
- The real-store `backtest --save` + `learn` rerun remains operationally
  pending because this checkout contains neither gitignored `data/store/**`
  nor `data/cryptobrain.db`; no demo data was substituted.

---

## [2.18.0] — 2026-08-15 · branch `arena/01a00490-sky`

MINOR bump: **P12.8 — the net anchor: decisions judge costs, not just reports.**

P12.6 made every *measurement* net of costs. P12.8 closes the gap it left
behind: the two places that **act** on a measurement were still reading the
**gross** number, so the desk could measure honestly and then decide on the
wrong figure.

### Fixed
- **`data/strategy_score.py` → `multiplier_from_score()`** anchored its sign
  on `E_gross`. Measured consequence: a setup at **`E_gross = +0.055R` /
  `E_net = −0.118R`** — profitable before fees, losing money after them —
  received multiplier **×1.008**, i.e. the engine *raised* confidence on a
  setup that loses money. The anchor is now `expectancy_net` when known
  (gross only as a fallback when costs cannot be computed), so the same
  setup now scores **×0.982** — dampened, never boosted.
- **`brain/calibrator.py`** — `build_profile()` passes the net expectancy to
  the multiplier, and the `CALIBRATE_FILTER` negative-expectancy filter now
  judges the net number too.
- **`brain/risk_gate.py` → `setup_proven()`** — the A6/B10 proven gate called
  a setup "proven" on gross expectancy. It now requires positive expectancy
  **net of costs** wherever the net column is populated. Sample floors
  (100 backtest / 20 paper) are unchanged. The block message now names the
  failing condition instead of only reprinting sample counts, so a
  net-expectancy rejection no longer reads as a bug.

### Added
- **`data/database.py` → `setup_stats()`** also returns
  `backtest_expectancy_net` / `paper_expectancy_net` (average of the stored
  `rr_net` column), or `None` when no net values exist for that setup — the
  caller falls back to gross rather than guessing.
- `setup_proven()` reports `proven_on: "net" | "gross"` so every surface can
  state which number the verdict used.
- `tests/test_net_anchor.py` — 11 tests: the cost-flipped regression case,
  the monotonicity property (the net anchor can only lower a multiplier,
  never raise one), gross fallback when costs are unknown, clamps, and the
  proven gate refusing a setup that is positive gross and negative net.

### Notes
- This is **strictly tighter**, never looser: it can only dampen a
  multiplier or withdraw a "proven". The graduation bar is untouched.
- Suite **620 → 631 pass / 1 skip** (+11). Versions `config.py` /
  `pyproject.toml` **2.17.0 → 2.18.0**.

---

## [2.17.0] — 2026-08-15 · branch `arena/01a0046d-sky`

MINOR bump: **P12.7 — Monte Carlo risk-of-ruin table.**

The scorecard says whether the book is profitable net of costs; P12.7 adds
*how much size the live book can survive*. It resamples the decided
paper-trade outcomes (NET of costs) and sweeps position size to expose
expected maximum drawdown, ruin probability, longest losing streak and
median time-to-recovery — all from one computation in
`brain/analytics.py` and surfaced everywhere the desk already looks
(invariant #10).

### Added
- **`brain/analytics.py` → `monte_carlo_ruin_table()`** — resamples net
  realised R outcomes (costs included; `data.costs.calculate_trade_cost`
  fills missing `rr_net` values) and returns:
  - per risk-% row: expected DD %, ruin probability, prob final equity
    below start, terminal median/p5/p95, median longest loss streak,
    median/mean time-to-recovery (trades);
  - historical block: actual longest losing streak, median/max TTR, and
    max drawdown from the observed net sequence.
- **CLI** — `python main.py monte [--risk-pcts ...] [--ruin-threshold 50]
  [--samples N] [--seed N] [--json]` prints the boxed table; `python
  main.py risk` now points the user to it.
- **HTTP** — `GET /api/monte` and the `monte` key embedded in `GET
  /api/risk`.
- **MCP** — root `mcp_server.py` risk tool embeds `ruin_table`;
  `ai/mcp_server.py` adds `cryptobrain_monte` tool alongside
  `cryptobrain_risk` (also augmented with `ruin_table`).
- **Dashboard** — Risk gate card renders the Monte Carlo sweep table plus
  historical streak / TTR / drawdown when data is available.
- Tests: `tests/test_monte_carlo.py` — empty book, structure, drawdown
  scaling with size, seed determinism, historical streak, sim-sample
  exclusion, direct `rows=` input. Suite **613 → 620 pass / 1 skip** (+7).

### Changed
- `config.py` and `pyproject.toml`: `VERSION` **2.16.0 → 2.17.0**.
- Root MCP server version: **1.8.0 → 1.9.0**.
- `tests/test_mcp_server.py`: `cryptobrain_monte` added to `TOOL_NAMES`.

---

## [2.16.0] — 2026-08-15 · branch `arena/01a00446-sky`

MINOR bump: **P12.5 — Strategy Score on the calibrator.**

The scorecard (P12.3/P12.6) reports the numbers, P12.4 judges the curve's
robustness, and the calibrator (`brain/calibrator.py`) turns a setup's
observed expectancy into a confidence multiplier. Before P12.5 the
calibrator trusted gross expectancy alone — a fragile, weakly-sampled or
cost-doomed curve could earn a full boost. P12.5 closes that: the audits'
formula (`docs/FREQTRADE_REVIEW.md` F25, `docs/BACKTRADER_REVIEW.md` BT12)

    Score = E_R × Stability × SampleConfidence − DD/complexity penalties

lands on the calibrator as a 0–100 **strategy score** per calibration key,
computed NET of costs (P12.6) over the same decided rows the scorecard and
P12.4 read (invariant #10 — one computation, many surfaces).

### Added
- **`data/strategy_score.py`** — pure `strategy_score(rows, …)` with four
  multiplicative components, composited as a **weighted geometric mean**
  (the "×" is literal — zero on any axis zeroes the score):
  - **e_r** (35%) — P12.4's `edge_score` verbatim: net expectancy vs the
    bar, shape-discounted on WR/PF misses;
  - **sample_quality** (35%) — **P12.4's `backtest_quality_score()` in
    full** (curve robustness + sample confidence + plateau when a sweep
    exists) — the audits' "Stability × SampleConfidence", read, never
    reimplemented;
  - **regime_fit** (15%) — base `plan_type` key: sample-weighted fraction
    of regimes with positive E_net (a one-regime edge is real, but the
    base key cannot know which regime is next); `plan_type::regime` key:
    the regime's E_net vs the setup's all-regime E_net (100 = ≥1.5×
    stronger here, 66.7 = average, 0 = no edge in this regime);
  - **execution** (15%) — share of the gross edge that survives the P12.6
    cost model: `1 − avg_cost_r / avg_gross_r` (modelled fees+spread+
    funding until micro-live records real fills).
  - Bands: ≥80 robust, ≥60 acceptable, ≥40 borderline, else fragile.
  - Empty books degrade to `score: None` with a reason.
- **`multiplier_from_score()`** — the calibrator's new trust dial:
  `mult = clamp(1 + E_gross × gain × trust, min, max)` with
  `trust = clamp(score/50, 0.6, 1.5)`. Score 50 = the pre-P12.5 formula;
  a robust edge is trusted up to 1.5×; a fragile or net-negative book is
  shrunk to the 0.6 floor. The sign anchor stays the observed gross
  expectancy, so a losing setup is always dampened or filtered.
- **`brain/calibrator.py`** — `build_profile` now pulls the key's decided
  rows (`_decided_rows_by_key`, reusing the scorecard's row adapters),
  computes the strategy score per key, and persists it. Profile entries
  gain `strategy_score`, `strategy_band`, `strategy_components`, and
  `expectancy_net`; `describe()` prints the score.
- **Surfaces (invariant #10):**
  - CLI `python main.py learn` — `describe()` shows `score N/100 band`
    per entry; `--json` dumps the full profile incl. components.
  - `GET /api/learning` — calibration entries carry the stored
    `strategy_score` / `strategy_band` (same block as the CLI).
  - Dashboard `LEARNING` card — new `Score` column, band-coloured, with a
    P12.5 legend line.
- **DB** — additive migration: `calibration.strategy_score REAL` +
  `calibration.strategy_band TEXT` (idempotent `_add`, no data loss);
  `save_calibration` / `load_calibration` round-trip the new fields.
- Tests: 15 new (`tests/test_strategy_score.py`) — empty-book degradation,
  strong vs zero-edge books, determinism, the literal-zero multiplication,
  regime-fit (base/regime keys), cost-survival, the multiplier trust dial,
  `build_profile` integration (score > 0 → boosted; net-negative → 0 /
  fragile / dampened), the min_n gate, DB round-trip, row grouping.
  Suite **598 → 613 pass / 1 skip** (+15).

Also fixed: `config.VERSION` was still 2.14.0 after P12.4's 2.15.0 bump —
both `config.py` and `pyproject.toml` are now **2.16.0** in step.

No trading orders or private credentials added (invariant #1 preserved).
Next on the ladder: **P12.7 — Monte Carlo ruin / worst streak /
risk-of-ruin table** (`risk% × expected DD × ruin probability` on the
existing resampler), then micro-live.

---

## [2.15.0] — 2026-08-15 · branch `arena/01a00431-sky`

MINOR bump: **P12.4 — Backtest Quality Score 0–100.**

The scorecard answers *"is this book profitable net of costs, with honest
overlap-corrected uncertainty?"* — P12.4 answers the second question a
desk must ask before trusting a curve: **"is this book robust, or did it
win by luck?"** A composite 0–100 so a fragile high-PnL curve cannot look
like a pass, scoring the now-real net-of-costs, overlap-corrected data
(per `docs/FREQTRADE_REVIEW.md` F5 and `docs/BACKTRADER_REVIEW.md` BT5):

    Score = E_net × stability × sample-confidence − DD/concentration
            penalties, with the parameter-plateau test as a cap

### Added
- **`data/quality_score.py`** — pure `backtest_quality_score(rows, …)`
  with four weighted components (edge 35%, robustness 35%, sample 20%,
  plateau 10%; renormalised when plateau evidence is absent):
  - **edge** — net expectancy vs the bar (+0.50R → 50, 2× bar → 100),
    discounted ×0.85 per miss when win rate ≤ 55% or PF < 1.5 (the bar
    requires all three conditions, so the score cannot pass on E alone);
  - **robustness** — fragility of the cumulative net-R curve:
    top-5 wins' share of gross wins (one lucky 5-trade streak must not
    BE the edge), max-drawdown ÷ |total R| (giving back half the profit
    is fragile), and chronological segment consistency (profits must
    persist across time, not arrive in one burst);
  - **sample** — N_eff vs min_decided (overlap-corrected) and where the
    95% CI of E_net sits relative to break-even (significance, not mean);
  - **plateau** — the BT5 parameter-plateau test: re-grade the stored
    series over `min_confidence ± 5`; a setup that only wins at one
    isolated parameter point **caps the total at 50** (a fit, not an
    edge). Plateaus < 50 also flag `plateau_cap`.
  - Bands: ≥80 robust, ≥60 acceptable, ≥40 borderline, else fragile.
  - Empty books degrade to `quality: None` with a reason — silence is
    not an edge.
- **`run_quality_sweep()`** — store-only plateau sweep (like the locked
  P12.1 protocol): `python main.py quality` re-grades the stored series
  at min_confidence ± 5 (clamped [40, 90], deduplicated, base point
  guaranteed), scores the base book against that evidence, and prints the
  boxed block. `grade_fn` is injectable so CI stays offline.
- **Surfaces (invariant #10, one computation everywhere):**
  - CLI `python main.py scorecard --quality` embeds the block (edge /
    robustness / sample; plateau n/a without the re-grade sweep);
    new `python main.py quality` runs the full plateau sweep.
  - `GET /api/scorecard?quality=1` and the `STRATEGY SCORECARD`
    dashboard card show the quality block.
  - MCP `scorecard` tool gained a `quality` argument; `SERVER_VERSION`
    1.7.0 → **1.8.0**.
- Tests: 25 new (`tests/test_quality_score.py`) — edge mapping & shape
  discount, concentration / drawdown / segment arithmetic, sample
  sufficiency & CI significance, the BT5 isolated-peak cap (= 50.0),
  plateau not-testable degradation, sweep dedupe / error propagation,
  scorecard embedding determinism, printer paths.
  Suite **573 → 598 pass / 1 skip** (+25).

No trading orders or private credentials added (invariant #1 preserved).
Next on the ladder: **P12.5 strategy score on the calibrator**
(`E_R × sample-quality × regime-fit × execution`), then P12.7 Monte Carlo
ruin.

---

## [2.14.0] — 2026-08-15 · branch `arena/01a00417-sky`

MINOR bump: **P12.3.3 — effective sample size in the scorecard.**
A walk-forward grade steps `step` bars and follows each plan over
`horizon_bars` future bars, so consecutive samples overlap heavily — a
24h horizon on 15m bars graded at step 3 shares 96/3 ≈ 32 windows, so
"384 decided" was really ~12 independent observations. The scorecard now
reports the honest independent sample size `N_eff = N / overlap`
(`overlap = horizon_bars / step`) alongside the raw trade count, and
widens every standard error and 95% confidence interval with
`SE = σ / √N_eff` instead of `σ / √N`. The graduation-bar *floor* is
unchanged for now (`min_decided` still reads raw N); the report flags
`n_eff_below_min_decided` so the desk can see when the overlap-corrected
sample is thin — the floor revisit is the next decision, not this one.

### Added
- **`overlap_factor()` / `effective_sample_size()`** in `data/scorecard.py`
  — per-row window-overlap factor (`horizon_bars / step` for walk-forward
  backtest rows; 1.0 for paper trades, which are real non-overlapping
  positions; 1.0 when horizon/timeframe/step are unrecorded, rather than
  inventing a divisor).
- **`step` column** on `backtest_results` (additive migration + save path)
  so the scorecard computes the overlap factor exactly instead of assuming
  the default; `python main.py backtest --save` records it.
- **`n_eff`, `overlap`, `expectancy_se`, `expectancy_ci95`,
  `expectancy_net_se`, `expectancy_net_ci95`** on every scorecard stats
  block (overall and each split), threaded through `trade_stats()`,
  `_split()`, `conditioned_splits()`, `build_scorecard()`,
  `scorecard_from_db()`, and `scorecard_from_store()`.
- **CLI** `python main.py scorecard --step` now applies to the stored-book
  path too (overlap correction); the printed block shows
  `(~N_eff independent, overlap ×K)` and the net 95% CI, plus a warning
  when `N_eff < min_decided`.
- Tests: 6 new (`test_overlap_factor_*`, `test_effective_sample_size_*`,
  `test_trade_stats_reports_honest_n_eff_and_widens_ci`,
  `test_build_scorecard_flags_n_eff_below_min_decided`,
  `test_backtest_rows_roundtrip_step_and_horizon`).
  Suite **567 → 573 pass / 1 skip** (+6).

No trading orders or private credentials added (invariant #1 preserved).
Next on the ladder: **P12.4 backtest quality score** (now scoring something
real), then P12.5, then P12.7 Monte Carlo ruin.

---

## [2.13.0] — 2026-08-15 · branch `arena/01a003f9-sky`

MINOR bump: **P12.6 — fees-first `E_net` & conditioned expectancy.**
Costs are now integrated into every performance measurement in SKY:
`E_net = E_gross − fees − slip − funding`, where every term is scaled
into R units per trade. Fees + spread lead the cost calculation (at
measured median stop distances of 0.823%, a 0.10% round-trip taker fee
costs **0.1215R**, ~40× funding at typical 1.8h holds). Funding is joined
as-of-T from stored derivatives series (or default 0.01%/8h). The
graduation bar is enforced **NET of costs** ($E_{\text{net}} \ge +0.50\text{R}$,
$WR_{\text{net}} > 55\%$, $PF_{\text{net}} \ge 1.5$), turning previously
cosmetic gross numbers into actionable trading evidence.

### Added
- **`data/costs.py`** — `CostModel` and `calculate_trade_cost()`,
  `get_funding_rate_as_of_t()`, supporting taker/maker/spot fee
  schedules, spread & slippage, and direction-aware funding (long pays
  positive funding, short receives positive funding credit).
- **Grader & Database Net R** — `GradedPlan` and `backtest_results` /
  `paper_trades` tables gained `rr_net`, `fee_r`, `slip_r`, `funding_r`,
  and `cost_r` columns through additive migrations.
- **Scorecard Net Metrics & Conditioned Splits** — `trade_stats()` and
  `build_scorecard()` report both gross and net metrics (`expectancy_net`,
  `win_rate_net`, `pf_net`, `total_r_net`, `max_drawdown_r_net`,
  `sharpe_net`, `sortino_net`, `calmar_net`, `cost_r`, `fee_r`,
  `slip_r`, `funding_r`), and conditioned splits by funding regime
  and CVD order flow (`--conditioned`).
- **Surfaces** — CLI `python main.py scorecard [--no-costs] [--maker] [--conditioned]`,
  HTTP `GET /api/scorecard`, MCP `scorecard` tool (v1.6.0), and the
  dashboard learning card showing cost drag and net expectancy.
- Tests: `tests/test_costs.py` (12 new tests) + scorecard net metric &
  conditioned split tests (3 new tests). Suite **552 → 567 pass / 1 skip** (+15).

No trading orders or private credentials added (invariant #1 strictly preserved).
Next on the ladder: **P12.3.3 effective sample size**.

---

## [2.12.0] — 2026-08-14 · branch `arena/01a00034-sky`

MINOR bump: **P12.3.2 — real market data.** The first real market data
ever entered the project: Binance spot BTCUSDT 1m, 2025-01-01 →
2026-04-30, 696,960 bars, from Binance's official public archive
(`data.binance.vision`), sha256-pinned and verified on import. P11,
P12.1 and P12.3 were re-run on it and the published numbers moved —
down, as `docs/PATH_TO_REAL_MONEY.md` predicted. The graduation bar was
not touched; the sealed protocol now fails every window on real data.

### Added
- **`data/backfill.py::backfill_from_csv`** — offline CSV import through
  the same adapter boundary as the REST backfill (validate → sort →
  `normalise_klines` → `CandleStore.write`). Idempotent by the store's
  upsert PK; reports duplicates, sanity-dropped rows, misalignment and
  gaps; `--csv-sha256` pins provenance and refuses mismatches.
- **`data/store.py::StoreClient`** — `klines()`-shaped reader over the
  Parquet store, so the offline walkers run on stored real candles.
- **CLI** — `backfill --from-csv PATH [--csv-sha256 HEX] [--rollup]`;
  `backtest --source store --market spot [--step N]`;
  `simulator --source store --market spot`; `scorecard --since/--until`
  (epoch-ms or YYYY-MM-DD) so one book can hold several data eras.
- **`docs/REAL_DATA_RUN_2026-08-14.md`** — provenance, repro commands,
  and the side-by-side synthetic-vs-real numbers.
- Tests: `tests/test_backfill_csv.py` (11) + scorecard era-filter tests
  (2). Suite **539 → 552 pass / 1 skip** (+13).

### Measured (the milestone's deliverable)
- **P12.1 sealed protocol, first real run** (12,000 real 15m bars, 1h
  primary): train −0.452R, val −0.251R, **oos −0.101R**, recent −0.429R
  — FAIL on every window (seal `1223819609d75213`).
- **P12.3 scorecard, first real run** (24,215 decided): +0.180R / 32.2%
  WR / PF 1.266 all-horizon; per horizon 1h −0.326R, 4h −0.032R,
  **24h +0.400R gross** (≈ +0.28R net at measured taker costs — below
  the restated +0.50R net bar). **Breakout Buy −0.630R** (6,062
  decided, negative at every horizon) — real-data confirmation of the
  prune case.
- **P11 grind, first real run**: +8,300 backtest + 494 paper samples;
  gate still closed (+0.348R / 36.8% WR / PF 1.55 / compliance 100%).

No strategy, risk-gate, graduation-bar, OOS-seal, order, or dependency
behavior changed. P12.6 (costs) is next on the ladder.

---

## [2.11.1] — 2026-08-14 · branch `arena/019fffe5-sky`

PATCH bump: **the two graders now agree on an ambiguous candle**, plus
`docs/PATH_TO_REAL_MONEY.md` — a measured audit against the project's
actual aim, and a proposed reordering of the P12 ladder.

### Fixed
- **`data/backtester.py::_evaluate()` — same-bar SL/TP ties graded 3R too
  generously.** When one candle touches both the stop and the target the
  ordering is undecidable from bar data. `data/paper_trading.py::exit_event`
  has always resolved this conservatively (stop wins, `ambiguous: True`),
  and `docs/BACKTRADER_REVIEW.md` §7.1 cites that written-down rule as a
  reason SKY needs no second engine. The backtester did **not** implement
  it: the first-touch comparison used a strict `<`, so on a tie
  (`first_sl == first_tp1`) control fell through to the take-profit branch
  and the candle was graded `PARTIAL_WIN +2.0R` where the paper trader
  graded `STOP_LOSS -1.0R`. Now `<=`, so the stop wins the tie on both
  sides of the book and the two graders can never disagree again.
  - Measured no-op on current data: **0 ties across 3,263 decided
    synthetic trades** (5 seeds). Random-walk candles are too small to
    span a 1R stop and a 2R target in one bar, which is exactly why this
    survived undetected. Real wick/liquidation candles hit it routinely,
    so the fix lands *before* real data rather than after.
  - **Expect measured expectancy to fall once real data arrives.** That
    fall is the correction, not a regression.

### Added
- **`GradedPlan.ambiguous_bar`** — in-memory diagnostic flag, `True` when
  the outcome was resolved by the conservative rule rather than observed
  ordering. Not persisted; on real data its rate tells you how much of a
  book rests on that assumption.
- **`docs/PATH_TO_REAL_MONEY.md`** — audit of the repo against the aim,
  with every figure measured at commit `342c66b`, not estimated:
  1. **No real market data has ever entered the project** — 0 `.parquet`
     files, 0 `paper_trades` rows; all 1,049 graded rows come from a
     seeded Gaussian random walk with no autocorrelation, fat tails,
     regime persistence or stop-hunt structure.
  2. **Costs are absent** (`EXECUTION_MODEL` defaults to `"none"`).
     Median stop distance is **0.823% of entry**, so a taker round trip
     costs **0.121R**: P12.3's +0.341R gross is ≈ **+0.22R net**. At the
     measured 1.8h median hold, **fees are ~40× funding** — which
     reverses P12.6's current emphasis.
  3. The same-bar disagreement fixed above.
  4. **Sample counts are inflated ~30×** — `step=3` against a 96-bar
     horizon overlaps ~32 neighbours, so 384 decided ≈ 12 independent.
- **5 regression tests** (`tests/test_backtester.py`) pinning the tie-break
  on both sides, asserting the backtester and paper trader return the
  identical verdict on identical input, and proving unambiguous candles
  are untouched.

### Changed
- **P12 ladder reordered** (`TODO.md`, `AI_ANATOMY_ROADMAP.md`,
  `docs/DATA_INFRASTRUCTURE_ROADMAP.md`). P12.4 would have scored a
  fiction — a robustness grade over a gross, cost-free number measured on
  a random walk. New order: **P12.3.1** tie-break (this release) →
  **P12.3.2 real data** → **P12.6 pulled forward, fees-first** →
  **P12.3.3 effective sample size** → P12.4 / P12.5 → micro-live last.
- **Graduation bar restated as net, not loosened.** The intent was always
  a real, tradeable +0.50R; measuring it gross quietly made it ~40%
  easier. The thresholds themselves (≥ +0.50R, > 55% WR, PF ≥ 1.5) are
  unchanged and remain enforced gross until P12.6 lands `E_net`.

### Unchanged
No signal, risk, execution, OOS-seal, order or dependency behavior. No
new dependency. F1–F8 and BT1–BT8 stay decided; still one grader.
Suite **534 → 539 pass / 1 skip**.

---

## [2.11.0] — 2026-08-14 · branch `arena/019fffe5-sky`

MINOR bump: **P12.3 — the boxed strategy scorecard**. One command, one
block: long/short, regime, session, Sharpe/Sortino/Calmar and holding
time over outcomes the grader already decided. This is a **report layer**
— it re-reads stored results and never re-grades, never re-optimises, and
never loosens the graduation bar.

### Added
- **`data/scorecard.py`** (new) — the P12.3 report engine:
  - `build_scorecard()` assembles one block from decided rows: overall
    stats plus `by_side`, `by_regime`, `by_session`, `by_setup` splits.
  - `trade_stats()` — expectancy, win rate, PF, avg win/loss, total R,
    max drawdown, win/loss streaks, best/worst, Sharpe, Sortino, Calmar,
    average/median holding time and how many trades were actually timed.
  - Row adapters, one honest shape per source: `rows_from_graded()`
    (in-memory `GradedPlan`s, single horizon), `rows_from_backtest_db()`
    (stored `backtest_results`), `rows_from_paper_db()` (the live paper
    book; holding time measured as `closed_ts - opened_ts`).
  - `scorecard_from_db()` (`backtest` | `paper` | `all`) and
    `scorecard_from_store()`; `print_scorecard()` renders the boxed block.
  - `session_of_hour()` / `session_of_ts()` bucket trades into
    asia / london / newyork from the existing `config` session windows.
- **CLI** — `python main.py scorecard` with `--source db|backtest|paper|store`,
  `--symbol`, `--tf`, `--min-decided`, `--exclude-sim`, `--json` and the
  backtest knobs. An empty book prints an actionable refusal and exits 1.
- **Web** — `GET /api/scorecard` and a `STRATEGY SCORECARD` dashboard card
  rendering the same block; the endpoint never 500s.
- **MCP** — read-only `scorecard` tool (`SERVER_VERSION` 1.4.0 → 1.5.0),
  so an agent reads the identical report the CLI prints.
- **Holding time is now recorded at grading time**: `GradedPlan` carries
  `holding_bars` / `holding_hours` (`None` while `OPEN`), both persisted by
  `save_backtest_rows()` into new `backtest_results` columns.

### Changed
- `data/database.py` — `backtest_results` gains `holding_bars` and
  `holding_hours`, added by the existing additive `_migrate()` path; rows
  written before this release read back as `NULL` and are reported as
  "not recorded" rather than silently counted as zero.
- `tests/test_web_api.py` — the `client` fixture now patches
  `config.DB_PATH` as well as the environment variable. `setenv` alone is
  read too late once `config` is imported, so these endpoint tests could
  reach the developer's real database; they are now genuinely isolated.

### Deliberately not done
- **No annualised Sharpe.** Scaling by `sqrt(trades_per_year)` on
  overlapping walk-forward samples inflated Sharpe from 0.27 to 36.7 in
  testing. The report states `span_days` and `trades_per_day` and labels
  every ratio per-trade.
- **No second grader, no new engine, no new dependency.**
  `data/backtester.py` remains the only grader (BT3/BT7).
- **The graduation bar is unchanged** (≥ +0.50R, > 55% WR, PF ≥ 1.5). The
  scorecard prints a verdict; it does not grant permission.

### Tests
- `tests/test_scorecard.py` (new, 37) — metric arithmetic, drawdown,
  streaks, session bucketing, split partitioning, DB adapters, sim-sample
  exclusion, PASS/FAIL/INSUFFICIENT_DATA verdicts, purity, and both CLI
  paths. `tests/test_web_api.py` +4, `tests/test_backtester.py` +1
  (holding-time contract), `tests/test_mcp_stdio.py` / `test_dashboard_js.py`
  inventories updated.
- Suite **492 → 534 pass / 1 skip**.

---

## [2.10.0] — 2026-08-13 · branch `arena/019ffb14-sky`

MINOR bump: **P12.2 — lookahead validation**. The validation engine
now has a deterministic, offline source guard for explicit future-peeking
row shifts, covered by the existing CI unit form. This is a research-integrity
check only: it does not change signal logic, grading semantics, the sealed
OOS protocol, or the graduation bar.

### Added
- **`data/validation.py`** — P12.2 AST scanner:
  - `scan_lookahead()` scans first-party `engine/`, `brain/`, and `data/`
    Python sources (or caller-supplied paths) and fails closed on
    `shift(-n)`, `shift(-1)`, and `shift(periods=-n)` style row offsets.
  - Source locations, offending expression, syntax/read errors, and a
    stable `PASS`/`FAIL` JSON report are returned; comments/docstrings are
    not executed or falsely reported.
  - `assert_no_lookahead()` provides the unit/CI assertion form;
    recursive-state analysis remains a later extension, as specified by
    P12.2's `(+ recursive later)` scope.
  - `print_lookahead()` renders the boxed `LOOKAHEAD VALIDATION — P12.2`
    report.
- **CLI** — `python main.py validate lookahead` (and `--json`; repeatable
  `--path` for a focused file/directory scan). The existing store-backed
  `python main.py validate` protocol is unchanged.
- **Tests** — four offline guards in `tests/test_validation.py`: the
  first-party source tree passes, a deliberately leaking `shift(-n)` /
  `shift(periods=-n)` feature fails, a causal `shift(1)` plus a
  docstring mention passes, and the CLI returns PASS/FAIL exit codes.
- **CI** — the existing `.github/workflows/ci.yml` offline pytest job
  runs the P12.2 unit form as part of the complete suite.

### Changed
- Version **2.9.0 → 2.10.0** (`config.py`, `pyproject.toml`).
- P12 status docs now mark P12.2 shipped and P12.3 as next; no recursive
  analysis is claimed early.

---

## [2.9.0] — 2026-08-13 · branch `arena/019ffafa-sky`

MINOR bump: **P12.1 — the SKY Quant Validation Engine's locked
walk-forward protocol (train / val / OOS / recent)** on our own
backtester + store. Report-only: nothing here places orders or feeds
`learn`.

### Added
- **`data/validation.py`** — the first P12 milestone
  ([`docs/FREQTRADE_REVIEW.md`](docs/FREQTRADE_REVIEW.md) §8 F5/F6,
  [`docs/BACKTRADER_REVIEW.md`](docs/BACKTRADER_REVIEW.md) §8 BT5/BT6):
  - `walk_forward_windows()` — chronologically locked, contiguous
    four-way split of the analyzed range. The engine warm-up belongs
    to no window; train absorbs the rounding remainder; bad fractions
    or a too-short series raise `ValidationWindowError`.
  - `bucket_by_window()` — a plan counts toward the window its
    **signal bar** (timestamp) belongs to; exits never re-bucket it.
  - `window_stats()` / `meets_bar()` — decided-trade statistics
    including profit factor, checked against the **live graduation
    bar** (`data.simulator.GRADUATION_CRITERIA` — E ≥ +0.50R,
    WR > 55%, PF ≥ 1.5) plus a per-window decided floor.
  - `protocol_verdict()` — the P12.1 done-when: a setup **cannot
    pass on the training window alone** (`FAIL`); passing requires
    train AND val; the sealed OOS/recent windows can only confirm
    (`PASS`) or warn (`PASS_WITH_WARNINGS`); too few samples is
    `INSUFFICIENT_DATA`, never a pass.
  - Sealed envelope (BT6): identical runs **reuse the stored seal**
    instead of silently re-deriving OOS; a config-fingerprint
    mismatch never reuses an old seal; `--reseal` re-opens it and
    the re-opening is appended to the seal history with a timestamp.
  - `run_validation()` / `run_validation_on_store()` — one
    walk-forward pass over the frame / stored Parquet series
    (P10.11's path), then per-window and per-setup verdicts.
  - `print_verdict()` — the boxed protocol report.
- **CLI `python main.py validate`** — store-only by design (four
  locked windows need history only the store can provide; a live
  500-candle fetch cannot hold them). Flags: `--exchange/--market/
  --bars/--step/--min-bars/--min-conf/--min-decided/--horizons/
  --train/--val/--oos/--recent/--json/--store-root/--seal-dir/
  --reseal`. Exit code 1 on error, 0 on a run.
- **`tests/test_validation.py`** — 17 offline tests: split tiling /
  fraction and length rejection, signal-bar bucketing, bar checks
  (including "silence is not an edge"), train-only FAIL,
  PASS_WITH_WARNINGS, INSUFFICIENT_DATA, seal round-trip +
  fingerprint gate + reseal history, end-to-end protocol run with
  seal reuse/reseal, and a guard test that `VALIDATION_CRITERIA`
  stays identical to `GRADUATION_CRITERIA`.
- **P11 gate unchanged** — still honestly closed (+0.263R / 34.1% /
  PF 1.40, below the ≥ +0.50R / > 55% / ≥ 1.5 bar). P12.1 does not
  loosen it; it adds the research-grade protocol around it.

### Changed
- Version **2.8.0 → 2.9.0** (`config.py`, `pyproject.toml`).
- Dashboard banner lists `validate`.
- Docs reconciliation: TODO-13 / SESSION_STATE / AI_ANATOMY_ROADMAP /
  FREQTRADE_REVIEW §8 / BACKTRADER_REVIEW §8 / README / ARCHITECTURE.

---

## [2.8.0 — P10.8–P10.12 addendum] · PR #18 — 2026-08-13

> Retroactive entry, added in the 2.9.0 session's reconciliation pass:
> PR #18 shipped five more P10 milestones without a changelog entry or
> version bump (`config.VERSION` stayed 2.8.0). Recorded here so the
> gap is closed.

### Added (PR #18)
- **P10.8** — vendored `lightweight-charts.standalone.js`;
  `renderLightweightChart()` (candlestick + histogram volume pane,
  `addHistogramSeries`); `/api/candles` feed.
- **P10.9** — market-tab cards `FUTURES — OPEN INTEREST & FUNDING`
  and `FLOW — CVD & VOLUME DELTA`, reading from `market_context` and
  the feature snapshot.
- **P10.10** — `data/ws_client.py`: public Binance WebSocket streams
  (`!forceOrder@arr` + klines), reconnect/backoff, graceful stop,
  offline-safe `DEMO_EVENT_STREAM`, singleton `get_client()`;
  `reconnect_state()` / `accumulation_stats()` feed the readiness
  strip and feature store. No `websockets` runtime dependency.
- **P10.11** — `data/backtester.py::run_backtest_on_store()` reads
  `CandleStore.read()` instead of a live fetch; honest error for
  missing/short series.
- **P10.12** — `data/feature_store.py`: `build_feature_table()`
  (price + derivatives + hidden_alpha + regime; 22 `FEATURE_COLUMNS`),
  `save_feature_table()` / `read_feature_table()`; one derived row
  per `(symbol, timeframe, ts)`.
- **P11 gate unchanged** — honestly closed (+0.263R / 34.1% /
  PF 1.40).

---

## [2.8.0] — 2026-08-13 · branch `arena/019ffab2-sky`

MINOR bump: **P10.7 — cross-exchange premium/discount + funding spread
as a stored series.** The live health probe is the same function
(generalised, not rewritten). Inputs only — no strategy, risk-gate, or
engine behaviour change.

### Added
- **`data/cross_exchange.py`** — Layer-4 series layer.
  - Venue registry (KuCoin + OKX + Bybit) + `snapshot_prices()` — the
    **single** probe health, preflight, and the collector all call.
    Output contract unchanged (`price` / `deviation_pct` / `flag`).
  - `snapshot_funding()` — public funding rates vs a Binance
    reference; kept separate so a missing funding endpoint cannot
    change the price-probe contract.
  - `CrossExchangeStore` — partitioned Parquet under
    `data/store/cross/**` (gitignored), same normalised row shape and
    upsert PK as P10.4. Metrics: `price`, `premium_pct`,
    `funding_rate`, `funding_spread`. Snapshot timestamps floor to
    15m (price) / 8h (funding).
  - `derive_premium()` = `(other / ref − 1) × 100` on common `ts`
    (zero-ref dropped). `derive_funding_spread()` = `other − ref`.
  - `FakeVenueTransport` + `DEMO_MODE=1` stay fully offline.
  - `CrossExchangeCollector` — derive Binance-vs-Bybit premium from
    the candle store, page Bybit funding history, persist one live/fake
    probe snapshot. Resumable, idempotent (a completed re-run adds
    zero rows).
- **`BybitClient.funding_history()`** — `GET /v5/market/funding/history`
  (`category=linear`). XAU / no perp → empty frame; transport fail →
  `None`.
- **CLI** — `python main.py cross collect|status` (`--since/--until/
  --no-snapshot/--dry-run/--json/--root`).
- **Tests** — `tests/test_cross_exchange.py` (20 offline) + 2 Bybit
  funding-page tests. The agent probe test now mocks Bybit V5
  `result.list` as well as KuCoin/OKX.

### Changed
- `brain/agent.py:_cross_exchange_probe` is a thin wrapper around
  `snapshot_prices`. `_CROSS_EXCHANGES` re-exports `VENUES`.
- Version 2.7.2 → **2.8.0** (`config.py`, `pyproject.toml`).
- Suite **449 → 471 pass / 1 skip** (+22), fully offline.

### Notes
- Health still skips the live probe in `DEMO_MODE`; the collector
  still writes offline via `FakeVenueTransport` / `SampleClient`.
- Store first. Do not turn a premium or a funding spread into a
  trading rule until the data proves it.

---

## [2.7.2] — 2026-08-13 · branch `arena/019ffa8d-sky`

PATCH bump: **Backtrader recommendation reviewed and rejected**.
Docs + contract tests only. No engine, risk-gate, or strategy
behaviour change. The desk is not rebuilt around a third-party
backtester, and the repo is not reset (considered, refused — second
time in a day).

### Added
- **`docs/BACKTRADER_REVIEW.md`** — keep/cut of a 22-section ChatGPT
  Backtrader audit against the live SKY desk. Decisions **BT1–BT8**:
  no `backtrader` dependency / vendored engine / adapter (BT1);
  no Cerebro rewrite (BT2); no second grader — “two fill semantics =
  two truths” (BT3, BT7); no entry parameter search (BT4, consistent
  with F3); the audit’s research discipline **confirms the F-named
  P12** and extends four done-whens — boxed strategy scorecard with
  Sharpe/Sortino/Calmar + session/L-S (P12.3), parameter-plateau test
  (P12.4), net-of-costs `E_net = E_gross − fees − slip − funding` with
  funding joined as-of-T (P12.6), risk-of-ruin table / worst-streak /
  recovery on the MC resampler (P12.7); sealed final-OOS (BT6 = F6);
  **no repo reset** (BT8).
- Contract tests in `tests/test_handoff_memory.py` so a future session
  cannot quietly add a second backtest engine or re-open BT1–BT8.

### Changed
- `TODO.md` — Backtrader added to out-of-scope; TODO-13 / P12
  definitions extended per BT5; next *code* is still **P10.7**.
- `SESSION_STATE.md`, `ARCHITECTURE.md` (invariant #13 extended),
  `AI_ANATOMY_ROADMAP.md`, `docs/DATA_INFRASTRUCTURE_ROADMAP.md`,
  `docs/INFRASTRUCTURE_LAYERS.md`, `PROFESSIONAL_PLAN_DECISIONS.md`,
  `BLUEPRINT.md`, `SKILL.md`, `README.md` — BT1–BT8 recorded.
- Version 2.7.1 → **2.7.2** (`config.py`, `pyproject.toml`).
- Suite **445 → 449 pass / 1 skip** (+4), fully offline.

---

## [2.7.1] — 2026-08-13 · branch `arena/019ffa5d-sky`

PATCH bump: **Freqtrade recommendation reviewed and rejected**,
reconciled onto merged P10.6 (PR #14). Docs + contract tests only.
No engine, risk-gate, or strategy behaviour change. The desk is not
rebuilt around a bot.

### Added
- **`docs/FREQTRADE_REVIEW.md`** — keep/cut of a 31-section ChatGPT
  Freqtrade audit against the live SKY desk. Decisions **F1–F8**:
  Freqtrade / Hyperopt / FreqAI out; strategy-catalog expansion out;
  repo reset out; the useful research-integrity ideas become **P12**
  (walk-forward / OOS / lookahead / quality score / strategy score /
  conditioned expectancy / MC ruin) on *our* backtester after P10.11.
- **TODO-13 / P12** — SKY Quant Validation Engine, parked until
  P10.11. Next *code* is **P10.7** (P10.6 Bybit already on `main`).
- **Invariant #13** in `ARCHITECTURE.md`: SKY is the brain, not a
  trading bot.
- Contract tests in `tests/test_handoff_memory.py` so a future
  session cannot quietly re-adopt Freqtrade.

### Changed
- Reconciled onto `origin/main` @ `e233580` (PR #14 / P10.6) so PR #15
  can merge: both the Bybit adapter and the F1–F8 decisions are kept.
- `TODO.md`, `SESSION_STATE.md`, `AI_ANATOMY_ROADMAP.md`,
  `docs/DATA_INFRASTRUCTURE_ROADMAP.md`, `docs/INFRASTRUCTURE_LAYERS.md`,
  `PROFESSIONAL_PLAN_DECISIONS.md`, `BLUEPRINT.md`, `SKILL.md`,
  `README.md` — F1–F8 recorded; next code pointed at P10.7.
- Version 2.7.0 → **2.7.1** (`config.py`, `pyproject.toml`).
- Suite **441 → 445 pass / 1 skip** (+4), fully offline.

---

## [Unreleased] — PR #14 · branch `arena/019ff9cf-sky` (merged as 2.7.0)

**Two parts, two PRs.** (1) Parallel-session reconciliation: this
session built its own P10.2 backfill on a base that predated PR #11
(P10.2 + P10.3) and PR #12 (P10.2 hardening + P10.4); on discovery the
repo rule won — never duplicate completed components — so PR #13
(merged by the operator) adopts the reviewed implementation wholesale,
keeping the session's genuinely new value as **3 edge-case tests** in
`tests/test_backfill.py` (empty-first-page termination, start-past-end
no-op, mid-history-hole termination without duplicates), and records
the lesson for future sessions: **fetch and diff `origin/main` before
finishing any session** — parallel Arena sessions merge while you work.
(2) **P10.5** (v2.6.0) rode PR #13; **P10.6** (v2.7.0) goes out as
PR #14 — see its entry below. Suite ends at **441 pass / 1 skip**.

---

## [2.7.0] — 2026-08-13 · branch `arena/019ff9cf-sky`

MINOR bump: **P10.6 — Bybit adapter behind the same normalised schema**.
The second venue pages through the exact same backfill machinery: one
`Candle` record, one meaning, regardless of exchange.

### Added
- **`data/bybit_client.py`** — read-only Bybit V5 public market-data
  transport (no keys, ever):
  - `klines_page()` implements the P10.2 `PageResult` contract
    (data + HTTP status + headers), so the hardened backfill treats
    Bybit pages identically to Binance pages — resumable, idempotent,
    rate-limit aware, geo-block aware.
  - Venue quirks stay at the boundary: V5 categories (`spot`/`linear`),
    V5 interval codes (`1m→"1"` … `1d→"D"`), newest-first response rows
    reversed to ascending `ts`, string rows parsed to float, `turnover`
    carried as `quote_volume`, `retCode 10006` mapped to HTTP 429
    (backoff engages), other non-zero retCodes to 400, HTTP 403/451
    passed through for the backfill's immediate geo-block abort.
  - XAUUSD has no Bybit perp → honest empty result (same rule as Binance).
  - `klines()` convenience wrapper (with `market=`) so the `--repair`
    path works unchanged.
- **`main.py backfill`** — `--exchange binance|bybit`; live Bybit runs
  route to `BybitClient`, DEMO_MODE stays on the offline demo fetcher
  (synthetic series labelled with the requested exchange, same
  convention the Binance demo already used).
- **Tests** — `tests/test_bybit.py`: 17 offline tests. The milestone's
  proof: `_assert_adapter_contract()` runs the **identical assertions**
  against `BinanceClient` and `BybitClient` (page shape, ascending ts,
  float OHLCV, perp/spot routing, status contract), plus V5-specific
  parsing/routing tests, bybit series partition separation from
  binance, idempotent re-run, and the offline CLI end-to-end.

### Changed
- `data/backfill.py` — geo-block message is venue-neutral ("the venue
  blocked this request"); module history notes the transport is now an
  interface (any `klines_page` client), not a class.
- Suite: **424 → 441 pass / 1 skip** (+17), fully offline.

---

## [2.6.0] — 2026-08-13 · branch `arena/019ff9cf-sky`

MINOR bump: **P10.5 — data-quality pillar wired into the readiness
strip**. SKY now answers *"can I trust my own stored market history?"*
with the same one-line verdict it already gives for channels, immune
system, and risk gate. Corrupt or unusably stale data **quarantines**
the desk — `ready` goes False — because the engine prefers silence to a
signal built on corrupt data.

### Added
- **`data/quality.py`** — per-series market-data checks:
  - `checks_on_frame()` — staleness (timeframe-scaled: ≤3×step fresh,
    ≤30×step lagging, older = unusable), gaps in the recent window
    (reuses P10.3 `detect_gaps`), price sanity (non-positive OHLC,
    high below body, low above body), volume sanity (negative = corrupt,
    zero-volume-with-range = suspicious), ts ordering (defensive).
  - `verdict_for()` — maps health onto the readiness ladder with an
    explicit `quarantined` flag.
  - `series_health()` / `series_item()` — read a stored series through
    the real store boundary and produce a pillar item.
- **`CandleStore.list_series()`** — enumerate stored series so the
  pillar inspects every series without knowing keys up front.
- **`brain/agent.py`** — fourth pillar `_data_pillar()` in
  `readiness_strip()`; exception-isolated like the other three; an
  empty store is honest `degraded` with the backfill hint, a
  quarantined series rolls the strip to `down` (`ready: false`).
- **`mcp_server.py`** — `readiness` tool description updated to four
  pillars; `SERVER_VERSION` 1.3.0 → 1.4.0.
- **Tests** — `tests/test_quality.py`: 18 offline tests (fresh/lagging/
  stale ladder, gap bands, negative-close / inverted-high / inverted-low
  / negative-volume / non-monotonic-ts quarantine, zero-volume suspicion,
  corrupt fixture written through the real store ⇒ quarantine, healthy
  series, `list_series`, empty-store degraded, quarantine ⇒
  `ready: false` integration, pillar exception isolation). Pinned
  pillar-set assertions updated across `test_agent`, `test_web_api`,
  `test_mcp_stdio`, `test_channels`, `test_dashboard_js`.

### Changed
- `main.py` doctor help, `web/app.py` strip comments, `SKILL.md` /
  `README.md` / `TODO.md` pillar descriptions — all say **four** pillars.
- Suite: **406 → 424 pass / 1 skip** (+18), fully offline.

---

## [2.5.0] — 2026-08-13 · branch `arena/019ff948-sky`

MINOR bump: **P10.4 — derivatives as time series**. Funding, open
interest, mark, index and basis are now persisted into the Parquet store
(the roadmap's Layer 2) instead of existing only as one live snapshot;
the `liquidations()` 24h-stats proxy is renamed honestly. Inputs only —
no strategy, risk-gate, or engine behaviour change.

### Added
- **`data/derivatives.py`** — the Layer-2 series layer.
  - `DerivativesStore` — partitioned Parquet store under
    `data/store/derivatives/**` (gitignored) with the normalised row shape
    `(ts, exchange, market, symbol, metric, value, ingested_at)` and upsert
    PK `(exchange, market, symbol, metric, ts)`.
  - `derive_basis()` — basis = mark − index at timestamps where both are
    known (accepts raw fetch frames or canonical store frames).
  - `BinanceDerivativesTransport` — adapter over the new client endpoints
    with retry/backoff and geo-block awareness; `FakeDerivativesTransport`
    — deterministic offline stand-in with fault injection.
  - `DerivativesCollector` — resumable per metric (re-runs continue at the
    last stored timestamp), idempotent (upsert PK → a completed re-run
    adds zero rows), pages with rate-limit courtesy, derives basis from
    the stored mark/index after each run.
- **`data/binance_client.py`** — derivatives history endpoints:
  `funding_rate_history()` (`/fapi/v1/fundingRate`), `open_interest_history()`
  (`/futures/data/openInterestHist`), `mark_price_klines()` and
  `index_price_klines()` (`/fapi/v1/markPriceKlines` + `/fapi/v1/indexPriceKlines`),
  `premium_index()` (current mark/index/basis snapshot).
- **`liquidations()` renamed honestly** → `liquidation_stats_proxy()`: the
  roadmap's P10.4 done-when ("proxy renamed honestly"). Real forced-order
  data cannot be backfilled (WS `!forceOrder@arr` only); the method's
  docstring now says so and no misleading alias remains.
- **CLI** — `python main.py derivatives collect --symbol BTCUSDT`
  (paginated history into the store; `--since/--until/--metrics/--dry-run/
  --json`) and `python main.py derivatives status` (per-metric counts +
  UTC span).
- **Tests** — `tests/test_derivatives.py`: 20 offline tests (schema/store,
  upsert, metric isolation, basis derivation + join semantics, fake
  transport shape, collect-all, idempotent re-run, resume, metric
  selection, basis ⇒ mark+index, dry-run, XAU rejection, unknown metric,
  transient-fault retry, honest-rename assertion). `SampleClient` gained
  the four demo history methods so `DEMO_MODE=1` stays fully offline.

### Changed
- Version 2.4.1 → 2.5.0 (`config.py`, `pyproject.toml`).
- `docs/DATA_INFRASTRUCTURE_ROADMAP.md`, `TODO.md`, `SESSION_STATE.md` —
  P10.4 marked shipped; next milestone P10.5 (quality pillar).

### Notes
- Tests **383 → 403 pass / 1 skip** (+20), fully offline.
- The sandbox has no network egress; the real derivatives fetch runs on a
  Binance-reachable machine:
  `python main.py derivatives collect --symbol BTCUSDT` (resumes on re-run;
  inspect with `python main.py derivatives status`).

---

## [2.4.1] — 2026-08-13 · branch `arena/019ff948-sky`

PATCH bump: **P10.2 hardening** — fixes two real defects in the P10.2
first cut (2.4.0) so the data-independence layer cannot silently corrupt
itself. Inputs only; no strategy, risk-gate, or engine behaviour change.

### Fixed
- **Perp backfill was storing spot candles labelled `market=perp`.**
  The first cut paged `/api/v3/klines` (spot) for every market. The
  default transport now routes `market="perp"` through `/fapi/v1/klines`
  (`BinanceClient.klines_page()`, geo-friendly mirror first) so the
  roadmap's primary series is actually perp. Spot candles are never
  labelled perp; XAUUSD (no perp market) fails with an honest message
  instead of writing mislabelled data.

### Added
- `data/binance_client.py` — `klines_page()`: one raw 1000-candle page
  for `spot` or `perp`, returning a `PageResult` with rate-limit headers
  and HTTP status. Header-aware `_get_with_headers` /
  `_get_first_host_with_headers`; existing `klines()` behaviour unchanged
  (routes through the same seam).
- `data/store.py` — `normalise_klines()` honours an input `closed`
  column (forming candles stay out of history; default remains closed).
- **Real rate-limit handling** in `data/backfill.py` (the 2.4.0 cut only
  slept `sleep_s` between pages):
  - exponential backoff on 429/network errors (`backoff_attempts` /
    `backoff_base`),
  - pacing on Binance's `x-mbx-remaining-weight` header (low budget →
    extra sleep; exhausted → longer),
  - immediate abort on geo-blocks (403/451) instead of hammering a wall,
  - `max_requests` cap (default 5000 on the CLI; 0 = unlimited) — an
    interrupted run resumes where it stopped,
  - forming-tail-candle rule: `ts + timeframe ≤ now` is the definition of
    closed; the still-forming candle is skipped and picked up next run.
- CLI — `backfill` gains `--since`/`--until` (epoch ms, ISO date, or `90d`
  style), `--max-requests`, `--dry-run`; output shows hardening stats
  (rate-limit stalls, retries, forming skipped) and a
  "✓ idempotent re-run — zero rows added" line. New `python main.py store`
  command inspects the store (count, UTC span, year/month partitions).
- `tests/test_backfill.py` — 2.4.0's 7 tests retained; +13 hardening tests
  (perp routing, forming-candle drop + top-up, 429 backoff + exhaustion,
  network-error retry, geo-block abort, weight-header pacing,
  max-requests cap + resume, dry-run, ts parsing).

### Changed
- Version 2.4.0 → 2.4.1 (`config.py`, `pyproject.toml`).
- `.gitignore` — `data/store_demo/` (explicit demo sandbox for `store --demo`).
- `docs/DATA_INFRASTRUCTURE_ROADMAP.md`, `TODO.md`, `SESSION_STATE.md` —
  P10.2 marked hardened; P10.3 marked shipped; next milestone P10.4.

### Notes
- Tests **368 → 383 pass / 1 skip** (+15: 13 hardening + 1 store closed-column
  + 1 unbounded-backfill regression), fully offline.
- The sandbox has no network egress; the real perp fetch runs on a
  Binance-reachable machine:
  `python main.py backfill --symbol BTCUSDT --market perp --tf 1m`.

---

## [2.4.0] — 2026-08-12 · branch `arena/019ff5b1-sky`

MINOR bump: **P10.2** (Binance paginated REST backfill) + **P10.3**
(gap detection, repair, 1m→higher-TF aggregation). Inputs only — no
strategy, risk-gate, or engine behaviour change.

### Added
- **`data/backfill.py`** — resumable, rate-limit-aware REST backfill.
  Pages through `klines` (Binance cap 1000), writes via
  `CandleStore.write()` / `normalise_klines()`. Resume cursor is
  `last_stored_ts + step`. A re-run of the same range adds **zero**
  unique rows. `DEMO_MODE=1` uses `SampleClient` (offline).
- **`data/gaps.py`** — `detect_gaps()`, `repair_gaps()`,
  `aggregate_ohlcv()`, `rollup()`. Incomplete trailing buckets are
  dropped (same rule as unclosed candles). Rollups tagged
  `source=aggregated`.
- **`python main.py backfill`** — `--repair` / `--rollup` / `--json`.
- **`tests/test_backfill.py`** + **`tests/test_gaps.py`** — 13 offline
  tests (paging, idempotent re-run, resume, sleep courtesy, CLI,
  synthetic holes, 5m OHLC match, incomplete-bucket drop, 2-day rollup).

### Changed
- `data/sample_client.py` — `klines()` honours `start_time`/`end_time`
  so DEMO pagination works.
- `config.py` + `pyproject.toml` — version **2.3.0 → 2.4.0**.

### Notes
- Tests **355 → 368 pass / 1 skip** (+13).
- Next milestone: **P10.4** — derivatives as time series.

---

## [Unreleased]

### Added — planning only, no runtime change
- **`docs/DATA_INFRASTRUCTURE_ROADMAP.md`** — P10, the market-data
  independence phase: collect BTC data from free/public exchange APIs,
  store it ourselves (normalised schema + Parquet), and let the engine
  reason over stored evidence instead of a 500-candle amnesiac fetch.
  12 independently shippable milestones (P10.1 → P10.12).

  Reconciles a user-supplied plan against what SKY already has. Seven
  corrections recorded so a future session doesn't re-litigate them:
  analytics are ~80% already built in `engine/`; SQLite + Parquet
  instead of PostgreSQL + Redis (SKY is single-process by invariant);
  Lightweight Charts standalone instead of React/Next.js; no FastAPI
  (Flask already serves `/api/*`); no Docker (`ops/systemd/` deploys);
  liquidations cannot be backfilled (WS-only, accumulates from day one)
  and today's `liquidations()` is a 24h-stats proxy; reuse the existing
  `_cross_exchange_probe()` rather than writing a second one.
- `tests/test_handoff_memory.py` — two tests guarding the P10 plan's
  load-bearing constraints (milestone ladder, credential-free posture,
  `DEMO_MODE`, and the rejected-dependency list).

### Changed
- `TODO.md` — records the project aim explicitly (decision
  independence ✅ / data independence ❌), adds **TODO-12 (P10)**, and
  moves Dify/LibreChat behind P10 as well as the graduation gate.
- `AI_ANATOMY_ROADMAP.md` — new P10–P12 phase table.
- `docs/INFRASTRUCTURE_LAYERS.md` — order of work now
  `P11 → P10 → Dify → LibreChat`.
- `.gitignore` — `data/store/**` excluded ahead of P10.1.

### Planned
- TODO-12 (P10): data infrastructure. Next major milestone.
- TODO-7: human pastes the wheel-gate job into
  `.github/workflows/ci.yml` (the spec currently sits inert at
  `docs/.github/workflows/ci.yml` — nested under `docs/`, so GitHub
  never runs it).
- TODO-8: human protects `main` (require PR). Token gets 403.

---

## [2.4.0] — 2026-08-13 · branch `arena/019ff948-sky`

MINOR bump: **P10.2 — Binance paginated REST backfill**, the second
shippable milestone of P10 (data independence). Reuses the existing
`BinanceClient` transport, pages 1m history into the P10.1 store, and is
resumable + rate-limit aware; a completed re-run adds **zero rows**
(the milestone's done-when, proven offline). No strategy, risk-gate, or
engine behaviour changed — this fills the input-side storage layer.

### Added
- **`data/backfill.py`** — `BinanceBackfiller`: paginated, resumable,
  rate-limit-aware OHLCV backfill.
  - Resumes at the last stored candle + 1 timeframe; an interrupted run
    (`--max-requests` cap, network drop, Ctrl+C) continues where it stopped.
  - Idempotent: the store's upsert PK makes re-runs and `--since` repairs
    add zero rows by construction.
  - Rate-limit aware: paced `--interval` between pages, exponential backoff
    on 429/network errors, extra sleep when Binance's
    `x-mbx-remaining-weight` header reports a low budget, immediate abort on
    geo-blocks (403/451) — nothing is hammered and nothing is half-written.
  - Forming-candle safety: a candle is only closed when
    `ts + timeframe ≤ now`; the still-forming tail is skipped and picked up
    by the next run once closed (incremental top-up).
  - `FakePagedTransport` — deterministic offline stand-in (fault/weight
    injection) so the milestone is fully testable with zero network, and
    `DEMO_MODE=1` runs into the gitignored `data/store_demo/` root.
- **`data/binance_client.py`** — `klines_page()`: one raw 1000-candle page
  for `spot` (`/api/v3/klines`, geo-friendly mirror first) or `perp`
  (`/fapi/v1/klines`), returning a `PageResult` with rate-limit headers and
  HTTP status. Existing `klines()` behaviour unchanged (routes through the
  same seam). Header-aware `_get_with_headers` /
  `_get_first_host_with_headers` helpers added; `_get` semantics preserved.
- **`data/store.py`** — `normalise_klines()` honours an input `closed`
  column (forming candles marked by the backfill stay out of history;
  default remains closed).
- **CLI** — `python main.py backfill` (paged fetch into the Parquet store;
  `--symbol/--market/--tf/--since/--until/--page-size/--interval/--max-requests/
  --dry-run/--demo/--json`) and `python main.py store` (count, UTC span,
  year/month partitions, `--json`).
- **Tests** — `tests/test_backfill.py`: 21 offline tests (fresh backfill,
  re-run zero-rows, resume, `--since` repair, dry-run, forming-candle skip
  + top-up, 429 backoff, geo-block abort, weight-header pacing,
  max-requests cap + resume, input validation, ts parsing). Plus a
  `closed`-column test in `tests/test_store.py` and the XAU routing test
  updated to the new transport seam.

### Changed
- Version 2.3.0 → 2.4.0 (`config.py`, `pyproject.toml`).
- `.gitignore` — `data/store_demo/` (DEMO_MODE backfill sandbox).
- `docs/DATA_INFRASTRUCTURE_ROADMAP.md`, `TODO.md`, `SESSION_STATE.md` —
  P10.2 marked shipped; next milestone P10.3 (gaps + aggregation).

---

## [2.3.0] — 2026-08-12 · branch `arena/019ff579-sky`

MINOR bump: **P10.1 — normalised Candle schema + Parquet store**, the
first shippable milestone of P10 (data independence). No strategy,
risk-gate, or engine behaviour changes — this adds the input-side storage
layer the rest of P10 feeds.

### Added
- **`data/store.py`** — `CandleStore`: partitioned Parquet candle store.
  - Normalised `Candle` schema (the roadmap §4 fields): `ts` (UTC epoch-ms
    candle OPEN, inclusive), `exchange`, `market`, `symbol`, `timeframe`,
    `open/high/low/close/volume/quote_volume`, `trades`, `closed`,
    `source`, `ingested_at`.
  - Upsert primary key `(exchange, market, symbol, timeframe, ts)` — the
    duplicate-row class of bug is prevented by construction.
  - `normalise_klines()` — the single adapter boundary; exchange-specific
    shapes never reach the analytics layer.
  - `coerce_candle_frame()` / `empty_frame()` — canonical schema + dtypes.
  - Hive-style partitioning `data/store/parquet/candles/exchange=…/market=…
    /symbol=…/timeframe=…/year=…/month=…/part-000.parquet` — one month, one
    file; `data/store/**` stays gitignored.
  - Safety rule enforced: an **unclosed** candle (`closed=False`) is never
    persisted into immutable history.
  - `read()` returns deduplicated rows ordered by `ts` ascending, with
    optional `start_ts`/`end_ts` filtering; `count()` / `series()` helpers.
- **`tests/test_store.py`** — 13 offline, deterministic tests: schema +
  dtypes, upsert dedup (last write wins), out-of-order input returned
  sorted, duplicate-ts collapse, unclosed-candle drop, year/month partition
  boundary, range filtering, empty-read, series isolation, normalise/coerce.
- `pyarrow` runtime dep (`requirements.txt` + `pyproject.toml`).

### Changed
- `docs/DATA_INFRASTRUCTURE_ROADMAP.md` — status header updated; P10.1
  marked shipped.
- `config.py` + `pyproject.toml` — version 2.2.1 → **2.3.0**.

### Notes
- Tests **342 → 355 pass / 1 skip** (+13). `DEMO_MODE=1` suite stays green;
  the store is fully offline.
- Next milestone: **P10.2** — Binance paginated REST backfill (resumable,
  rate-limit aware) reusing `data/binance_client.py`, writing via
  `CandleStore.write()`.

---

## [2.2.1] — 2026-08-12 · branch `arena/019ff530-sky`

PATCH bump: TODO-11 (P11) paper-book proof — first grind + a real
engine bug the graduation report revealed.

### Fixed — sell-side R sign inversion (the graduation report's reveal)
`data/backtester.py::_evaluate()` computed a **SELL** win's realized R
as `(tp - entry) / risk`. For a short, `tp < entry`, so every sell
`FULL_WIN` / `PARTIAL_WIN` was recorded with **negative** R — sell-side
expectancy, win-R and profit factor were systematically destroyed.
Before the fix the primary family's sell setups measured −1.6R…−1.9R;
after the fix the same data shows Sell Pullback **+0.540R** and FVG
Retest Sell **+0.636R** (Sweep Reversal Sell is honestly breakeven at
−0.033R on synthetic data — no edge, gate correctly stays closed).
The paper runner already used `abs()` correctly; only the backtester
was wrong. Regression tests: `test_evaluate_sell_win_full` (+2.0R),
`test_evaluate_sell_win_partial` (+1.0R).

### Added — TODO-11 grind + journal loop
- **Simulator journals every closed paper sample.** `_persist_paper_samples`
  now records a journal entry per closed simulator paper trade with
  `followed_rules=1` (mechanical execution of the engine's own plan) and a
  transparent note. The graduation gate's `compliance` criterion
  (1 − journal violation rate) stopped being `None` — it now reads
  **100.0%** from real journal rows. `tests/test_simulator.py`
  `test_simulate_round_journals_closed_paper_samples`.
- **Precise graduation-gap reporting.** `graduation_status()` exposes
  `sample_gaps` (the grind_verdict missing list); `python main.py desk`
  now says `samples counts short` / `samples expectancy short` instead of
  the blanket `samples short`, and the PAPER_GRIND advice names the exact
  primary setup + missing item (e.g. "Sweep Reversal Sell sample proof
  (positive expectancy)"). `brain/agent._sample_proof_word()`.

### Changed
- `config.VERSION` 2.2.0 → **2.2.1**; `pyproject.toml` to match.
- First real grind ran on the sandbox's offline sample/synthetic data:
  **38,439 decided primary-family samples** (all four setups ≥ 100
  backtest / ≥ 20 paper unique samples), `learn` produced a full
  per-setup × regime calibration profile (proven setups boosted
  ×1.1–1.2, losing Breakout Buy dampened ×0.83), and the desk line
  moved from "samples short · 0 decided" to "expectancy short ·
  38,439 decided". The blueprint graduation gate remains honestly
  CLOSED (family expectancy +0.263R < +0.50R, win rate 34.1% < 55%,
  PF 1.40 < 1.50) — as designed until the edge clears the bar.

### Known characteristics (documented, not bugs)
- FVG Retest Buy/Sell carry thousands of backtest samples but **0 paper
  samples**: the simulator takes one paper sample per window (the
  highest-confidence plan), so setups that rarely win the confidence
  contest are starved of paper proof. Outside the primary family today;
  noted for a future collection-strategy decision.

---

## [2.2.0] — 2026-08-12 · branch `arena/019ff4c3-sky`

MINOR bump: new readiness surface across CLI, HTTP, MCP, and dashboard.

### Added — TODO-1.bis combined doctor strip

One verdict answering "can I trust the desk right now?", rolled up
**worst-first** across the three readiness pillars the desk already
reported separately:

| Pillar | Source of truth | Levels |
|---|---|---|
| `channels` | `brain.channels.probe_all()` | ok / degraded / down |
| `immune` | `brain.immune.run_health_check()` | ok / degraded / down |
| `risk_gate` | the gate inside `desk_status()` | ok / degraded / blocked |

Rollup ladder: `ok < degraded < blocked < down`. The strip never
invents a fourth source of truth — every pillar reads the same library
function the CLI, MCP, and dashboard already read, so no surface can
drift from another.

- **`brain/agent.readiness_strip()`** + `format_readiness_strip()`.
  Each pillar is exception-isolated: a crashing probe degrades that
  pillar to `down` instead of failing the whole strip.
- **`python main.py doctor --strip`** (`--json` for the machine blob).
  Plain `doctor` now leads with the strip before the per-channel
  detail; `doctor --json` gained a `readiness` key.
- **`GET /api/readiness`** — never 500s; degrades to
  `{ok: false, level: "down", error: …}`.
- **MCP `readiness` tool** — `SERVER_VERSION` 1.2.0 → 1.3.0
  (13 read-only tools). Deny list unchanged.
- **Dashboard readiness strip** above every tab (`loadReadiness()`),
  colour-coded by level with one chip per pillar and the current desk
  advice. Lives outside `#app`, so it resolves before the first scan
  does; refreshes on the 5-minute diagnostic cadence, not the 30s
  scan tick.

### Changed
- `config.VERSION` 2.1.0 → **2.2.0**; `pyproject.toml` to match.

### Test count
- 324 → **337 pass / 1 skip** (+13). 0 regressions.

New coverage: pillar rollup order, closed-gate → `blocked`, crashing
probe isolation, `/api/readiness` shape + never-500, node-executed
dashboard render of the strip (verdict, chips, error payload), and
the three new CLI paths.

### Prior unreleased entries folded in
- `docs/INFRASTRUCTURE_LAYERS.md` — SKY-only map of OpenHands / Dify /
  LibreChat. Study patterns; never vendor. Dify after graduation;
  LibreChat last.
- `tests/test_handoff_memory.py` — SESSION_STATE / TODO / layers-doc
  contract so a dead Arena session cannot ship a rotting handoff.

---

## [2.1.0] — 2026-08-12 · branch `arena/019ff483-sky`

MINOR bump: new CLI command, new MCP tool, installable package.

### Added — TODO-4 desk_status advisory
- **`brain/agent.desk_status()`** — one-call snapshot aggregating
  the risk gate, today's/week's P&L, business scorecard, graduation
  gate, next scheduled autonomous agent, and a single
  "what would a professional do right now?" action.
- **`brain/agents.next_scheduled_agent()`** — cadence-based pick
  from `agent_runs` (morning_brief 24h / watchdog 4h /
  paper_reviewer 24h / weekly_review 168h). Never starts an agent.
- **`python main.py desk`** (`--json` for the machine blob).
- **MCP `desk_status` tool** — `SERVER_VERSION` 1.1.0 → 1.2.0
  (12 read-only tools). Deny list unchanged.
- **`GET /api/desk`** + dashboard "DESK STATUS" card on the System
  tab (`loadDesk()`, 5-minute diagnostic refresh).
- **`ask("what should I do?")`** routes to the same snapshot.

Advice is priority-ordered and capital-first:
`CLEAR_STATE → STAND_ASIDE → REVIEW_QUEUE → JOURNAL → PAPER_GRIND → SCAN`.

### Added — TODO-3 wheel-gate (D4 = yes)
- **`pyproject.toml`** — package `cryptobrain` 2.1.0, console script
  `cryptobrain = main:main`.
- **`cryptobrain/__init__.py`** — `import cryptobrain` facade
  (`__version__` from `config.VERSION`).
- **`ci/wheel_gate.py`** — build the wheel, reject duplicate zip
  entries, optional `--install` smoke test
  (`import cryptobrain` + `cryptobrain doctor --json`).
- **`wheel-gate` job** in `.github/workflows/ci.yml`.
- **`tests/test_wheel_gate.py`**.

### Changed
- `config.VERSION` 2.0.0 → **2.1.0**.
- `main.main()` now accepts an optional `argv` list (wheel-gate
  smoke-test contract; `python main.py …` unchanged).
- D1–D5 in `ROADMAP_AGENT_REACH_UPGRADE.md` §4 recorded as decided
  (recommended defaults). D5 URL documented in `docs/agent_install.md`.

### Test count
- 306 → **320 pass / 1 skip** (+14). 0 regressions.

### Pushed
- Branch `arena/019ff483-sky` → `origin`.

---

## [2.0.4] — 2026-08-11 · branch `arena/019ff045-sky`

### Added — PR #5 conflict resolution (this session)

PR #5 (`feat(agent-surface): P7+P8+P9 — SKILL, channels, MCP
capability endpoints`) was `CONFLICTING` because `main` was
independently updated (commit `0940452` modern-dashboard) while the
P7/P8/P9 work was in flight. This session resolves the conflicts.

**main.py** (4 conflict hunks):
- Kept BOTH sides' additions: branch's `cmd_doctor / channels /
  skill` AND main's `cmd_preflight` + the preflight gate in
  `cmd_paper --watch`.
- Default banner updated to list all new commands.

**web/app.py** (3 conflict hunks):
- Took main's full modern tabbed dashboard wholesale (the branch's
  old `html += card(...)` block was obsolete; main's tabbed
  architecture IS the design).
- Re-applied the branch's `loadChannels()` JS function.
- Re-added the `/api/channels` and `/api/doctor` Flask endpoints
  (main did not have them — they were a P8 deliverable on the
  branch).
- Added the CHANNELS card to the system tab.
- Added a 5-minute diagnostic auto-refresh (channels + mcp),
  distinct from the existing 30s scan tick.

### Test count
- 285 → **306 pass / 1 skip** (+21 from main's modern-dashboard work
  including `tests/test_preflight.py`).
- 0 regressions on the branch side.

### Live verification
After resolving the conflicts, started `python main.py web` and
hit every new endpoint via curl:
- `/` → 200
- `/api/health` → 200
- `/api/channels` → 200 (returns proper JSON with 4 channels)
- `/api/doctor` → 200
- `/api/mcp` → 200

### PR status
PR #5 went from `CONFLICTING` to `MERGEABLE`. Reviewer can now merge.

### Pushed
- Branch `arena/019ff045-sky` → `origin`. No new PR (PR #5 already
  exists).

---

## [2.0.3] — 2026-08-11 · branch `arena/019ff045-sky`

### Added — P9 MCP capability endpoints (TODO-2 complete)

`mcp_server.py` (the zero-dep stdio JSON-RPC server) now exposes 5
new read-only tools, bringing the total from 6 to 11:

| Tool | Wraps | What you get |
|---|---|---|
| `channels` | `brain.channels.list_channels(as_json=True)` | Ordered-backend registry (cryptodada / discord / news / llm) — same data the dashboard "CHANNELS" card and `python main.py channels --json` return |
| `correlation` | `engine.correlation.fetch_report` | Measured BTC/ETH/GOLD rolling correlation matrix + ETH/BTC beta |
| `hidden_chart_read` | `engine.hidden_alpha.hidden_alpha_report` | HMM latent regime + CVD order flow + Bayesian Kelly for one symbol |
| `hidden_analytics_mae` | `brain.analytics.mae_mfe_summary` | MAE/MFE summary per setup from the paper-trade DB |
| `hidden_analytics_mc` | `brain.analytics.monte_carlo_equity` | Monte Carlo equity + drawdown distribution from realized paper outcomes |

### Changed
- `mcp_server.py:SERVER_VERSION` bumped `1.0.0 → 1.1.0` (capability
  surface expansion).
- `mcp_server.py` docstring now explicitly names the deny list
  (`approve | reject | execute | close | place_order | sign |
  withdraw | transfer`) so the invariant is self-documenting.
- `SKILL.md` tool table updated: 5 rows that previously had `—` in
  the MCP column now list the new tool name.
- `tests/test_mcp_stdio.py:ROOT_TOOLS` extended to 11 names.

### Tests
- 6 new tests in `tests/test_mcp_stdio.py`:
  - `test_root_mcp_channels_tool`
  - `test_root_mcp_correlation_tool`
  - `test_root_mcp_hidden_chart_read_tool`
  - `test_root_mcp_hidden_analytics_mae_tool`
  - `test_root_mcp_hidden_analytics_mc_tool`
  - `test_root_mcp_deny_list_still_enforced` — checks 8 forbidden
    names both in `tools/list` AND by direct call
- Test count: 289 → **295 pass / 1 skip** (0 regressions).

### Self-reflection (in-session)
- The previous session's end-of-session `SESSION_STATE.md` update
  recorded new SHAs but left two pre-existing inconsistencies
  unrepaired (a `<new-sha>` placeholder and a stale "P8 dashboard
  panel pending" status line). The refined rule: when updating
  `SESSION_STATE.md`, do a full-document reconciliation pass — not
  just append new sections.
- TODO-2 followed the **library-function-not-subprocess** design
  pattern. The existing tools (`ask`, `risk`, `health`, etc.) all
  call library functions directly, not `cmd_*` functions via
  subprocess; the new tools follow the same pattern. This keeps the
  surface consistent and avoids the overhead of a process per call.

### Pushed
- Branch `arena/019ff045-sky` → `origin`. No PR opened.

---

## [2.0.2] — 2026-08-11 · branch `arena/019ff045-sky`

### Added — P8 dashboard "Channels" panel (TODO-1 complete)
- **`GET /api/channels`** in `web/app.py` — JSON endpoint wrapping
  `brain.channels.probe_all()`. Exception-isolated (a broken probe
  in one channel cannot crash the endpoint); goes through
  `_sanitize_for_json` to preserve the numpy-leak fix from
  `MERGE_NOTES.md`. Returns `{channels: {name: {status, active,
  backends: [...]}, ...}}`.
- **`GET /api/doctor`** — JSON-wrapped text report. Same output
  as `python main.py doctor`; the dashboard panel could call it
  but uses `/api/channels` directly for the structured view.
- **Dashboard HTML: new "CHANNELS — ordered-backend registry (P8)"
  full-width card.** Renders a status pill row (one per channel:
  `cryptodada / discord / news / llm`) plus a per-channel table
  with `configured / ok / detail / (active)` columns. Visual design
  matches the existing `MCP SERVER` card.
- **JS: `loadChannels()`** — fetches `/api/channels`, renders the
  card. Wired into the post-render init block.
- **Separate 5-minute auto-refresh for diagnostic panels** (channels
  + MCP), distinct from the 30s signal-scan tick. Channels are
  diagnostic state, not signal state, so a slower cadence is
  correct.
- **4 new tests** in `tests/test_web_api.py`:
  `test_channels_endpoint_returns_registry`,
  `test_channels_endpoint_is_json_serializable_under_numpy_leak`,
  `test_channels_endpoint_isolates_probe_exceptions`,
  `test_doctor_endpoint_returns_text_report`.

### Test count
- 285 → **289 pass / 1 skip** (0 regressions).

### Self-reflection (in-session)
This session caught a stale handoff: the previous session's
`SESSION_STATE.md` said "Last commit: b0fe82f" but the actual HEAD
was already `498d753` (the docs commit). The handoff memory went
stale inside the same chat. The lesson: **update SESSION_STATE.md
at the START of every session, not just at the end.** This entry
is the first to be documented with the rule.

### Pushed
- Branch `arena/019ff045-sky` → `origin`. No PR opened.

---

## [2.0.1] — 2026-08-11 · branch `arena/019ff045-sky`

### Added — Agent-Reach-inspired surface (P7 + P8 code layer)
- **`SKILL.md`** at repo root — the 155-line agent-facing skill file
  that any AI agent (Claude, Cursor, Arena, MCP client) can read to
  learn the tool surface, the safety contract, and the citation
  pattern. Mirrors the Agent-Reach pattern of "one URL the agent
  reads."
- **`ROADMAP_AGENT_REACH_UPGRADE.md`** — the P7/P8/P9 plan with
  per-phase risk + rollback + definition-of-done + D1–D5 decision
  list. Honest about what is *adopted* (operational patterns) and
  what is *not adopted* (web scraping, social logins, audio
  transcription, third-party CLIs).
- **`docs/agent_install.md`** — the one-pager an agent fetches when
  told "install CryptoBrain."
- **`brain/channels.py`** — the ordered-backend router. Four channels
  (`cryptodada`, `discord`, `news`, `llm`), each with a primary →
  fallback chain ending in an always-available tail (`none` or
  `rule_based`). Probes are exception-isolated so a broken channel
  can't crash `doctor`.
- **`python main.py doctor`** — the non-mutating readiness report
  (channels layer + immune system).
- **`python main.py channels`** — compact per-source backend
  registry listing.
- **`python main.py skill`** — print / install / uninstall the
  `SKILL.md` (default inspect-only; `--system` required for
  `$HOME` writes).
- **`tests/test_channels.py`** — 27 new tests covering registry
  shape, probe isolation, fallback ordering, each source's "off"
  state, SKILL.md content contract, every new CLI subcommand
  including the `--install` / `--system` / `--dry-run` safety
  postures.

### Changed
- **`main.py`** — three new subcommands (`cmd_doctor`, `cmd_channels`,
  `cmd_skill`); default banner updated. +184 lines, additive only.
- **`AI_ANATOMY_ROADMAP.md`** — short P7/P8/P9 summary table linked
  to the new planning document. +34 lines, additive only.

### Test count
- 258 pass / 1 skip → **285 pass / 1 skip**. 0 regressions.

### Pushed
- Branch `arena/019ff045-sky` → `origin`. No PR opened (user
  explicitly chose Option B: branch only).

### Notes
- Inspired by [`Panniantong/Agent-Reach`](https://github.com/Panniantong/Agent-Reach)
  (v1.5.0, 70.5k★, MIT). Operational patterns adopted; web-scraping
  surface explicitly not adopted per
  `ROADMAP_AGENT_REACH_UPGRADE.md` §5.

---

## [2.0.0] — 2026-08-10 · commits `35ad758…99ace0d`

### Added — Consolidated production build (merged Cloudslover/AI + cloudshome/AI)
- **Engine layer (`Cloudslover/AI` @ `ea50e54`):**
  - Hidden-alpha quant: Markov-smoothed HMM latent regimes
    (Bull/Bear/Range/Expansion).
  - CVD order flow: absorption & exhaustion detection.
  - Bayesian fractional Kelly sizing (`NEGATIVE_EDGE_STAND_ASIDE`).
  - 8D state fingerprint + historical similarity search.
  - Realistic spread/slippage execution model (`EXECUTION_MODEL=simple`).
  - Monte Carlo equity + drawdown distribution.
- **Anatomy layer (`cloudshome/AI` @ `ba7a35c`):**
  - `brain/library.py` + `brain/ask.py` — RAG knowledge index +
    grounded Q&A with strict citations.
  - `brain/brief.py` — cross-asset morning brief + post-trade
    reviews (MAE/MFE + rule-compliance headline).
  - `brain/agents.py` — autonomous desk agents (morning brief,
    watchdog, paper reviewer, weekly review), audit-logged to
    `agent_runs`.
  - `brain/immune.py` — system diagnostics (staleness, DB integrity,
    risk gates, behavioral flags, calibration drift).
  - `mcp_server.py` — **zero-dependency** stdio JSON-RPC 2.0
    server.
  - `AI_ANATOMY_ROADMAP.md` — architecture/status tracker.
- **`engine/correlation.py`** + `python main.py correlation` —
  measured rolling BTC/ETH/GOLD correlation matrix and ETH/BTC
  beta, with explicit check of the static "BTC+ETH = one bucket"
  portfolio rule.
- **CLI parity with `AI_ANATOMY_ROADMAP.md`:** top-level `ask` (RAG
  library with citations), `postreview <scan_id>`, and
  `agent watchdog | paper-reviewer | weekly-review` (autonomous
  agents, audit-logged).
- **Tests:** 38 test modules. `tests/test_correlation.py`,
  `tests/test_mcp_stdio.py` (root MCP server: handshake, tool
  permission map, trader-state round-trip, health check),
  `tests/test_web_api.py` — Flask endpoint regression tests.

### Changed
- **Grafted modules:** `ai/llm_brain.py`, `brain/metrics.py`,
  `brain/risk_gate.py`, `data/database.py`. See `MERGE_NOTES.md` §2
  for the file-level decisions.
- **Production bug fix:** `/api/scan` and `/api/intelligence`
  returned HTTP 500 ("Object of type bool is not JSON serializable")
  whenever numpy scalars from the quant layer leaked into the
  payload. All engine endpoints now pass through `_sanitize_for_json`.

### Test count
- Pre-merge: 171 / 258 / 0 across the two sources (per source READMEs).
- Post-merge: **258 pass, 1 skip, 100% offline** (`DEMO_MODE=1
  python -m pytest tests/ -q`).

### Pushed
- Branches `arena/019febaf-sky` and `arena/019fefc9-sky` → `main`
  via PRs #1–#4 (all merged). The CI workflow file was renamed to
  `.github/workflows/ci.yml` (commit `8b16923`) to activate it —
  but see TODO-7 for the manual activation step.

### Notes
- Canonical consolidated repo:
  [`https://github.com/Azimshawon/SKY`](https://github.com/Azimshawon/SKY).
- Both upstream repos remain as read-only history sources.

---

## Pre-2.0.0 history

The pre-2.0.0 history lives in the two source repositories:

- [`Cloudslover/AI`](https://github.com/Cloudslover/AI) — engine +
  professional mode (hidden-alpha quant layer, execution model,
  analytics, risk gate).
- [`cloudshome/AI`](https://github.com/cloudshome/AI) — AI anatomy
  layer (RAG library, ask, brief, agents, immune, MCP).

File-level provenance of the merge is in
[`MERGE_NOTES.md`](./MERGE_NOTES.md).

---

## Versioning policy

- **MAJOR** bump for breaking changes to the engine JSON contract
  (`output/signal_schema.py`) or the MCP `tools/list` interface.
- **MINOR** bump for additive, backwards-compatible features (new
  CLI subcommands, new brain modules, new MCP tools, new
  dashboard panels).
- **PATCH** bump for bug fixes, test additions, documentation,
  refactors with no API change.

The current `pyproject.toml` (when added — see TODO-3) will be the
source of truth for the version number; this changelog is the
source of truth for *what* shipped.
