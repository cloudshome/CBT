# W2 (part 2) — chart workstation: live streaming + drawing tools

**Shipped:** 2026-08-17 · branch `arena/01a01103-sky` · version **2.33.0**
**Builds on:** W2 part 1 (zone overlays + replay), W1 evidence flow, P18.3 jobs/SSE
**Next code:** P18.4 — the mobile-responsive, installable PWA.

---

## 0. One-paragraph summary

W2 is finished. The chart workspace can now **stream the newest bar** instead of
waiting for a human to press *↻ Reload chart*, and the trader can **draw on the
chart** — trendlines, horizontal rays and boxes — with the marks persisted per
symbol + timeframe and attachable to a journal entry. While proving the streaming
path end to end, the new "check the *served* script" test caught a **pre-existing
bug that broke the entire dashboard in a real browser** (see §4); that is fixed
here too. No threshold moved, no order path exists anywhere in SKY, and nothing in
this build writes to the learning store, the paper book or the risk gate.

---

## 1. What the roadmap asked for

From `HANDOVER.md` §"Next session — start here":

> 1. **Live streaming** — push candle updates over SSE/WebSocket from
>    `data/ws_client.py` and call `series.update()` instead of redrawing.
>    Preserve reconnect semantics and label stale/disconnected data honestly.
> 2. **Drawing tools** — trendlines, horizontal rays and boxes placed with the
>    mouse, persisted per symbol/timeframe (localStorage to start), and
>    attachable to the scan record.

Both ship. §5 states precisely where each one stops.

---

## 2. What was built

### 2.1 `web/live_stream.py` (new, stdlib + the existing candle source)

A generator of `text/event-stream` frames for one symbol/timeframe.

- **`candle_events(fetch, symbol, tf, …)`** polls the *same* candle source
  `/api/chart` already uses and yields a full snapshot of the newest bar. The
  clock, the sleep and the source are injected, so the tests drive it with no
  network and no real timer.
- **Every frame carries a state**, because the dangerous failure mode of a live
  chart is a dead feed that still looks alive:
  - `candle` / `live` — the bar changed; the browser calls `series.update()`;
  - `status` / `waiting` — source healthy, bar unchanged, with its age;
  - `status` / `stale` — unchanged for longer than 2 × the timeframe
    (floor 90 s); the UI says so in amber;
  - `status` / `error` — the source raised; the message is forwarded verbatim.
- **A failing source never ends the stream.** It emits an `error` frame and
  backs off (doubling, capped at 30 s), so a transient hiccup does not force the
  browser to reconnect. Every frame is a complete snapshot with an `id:`, so a
  reconnect resumes correctly — there is no server-side cursor to lose.
- **Cadence is bounded**: `poll_interval(tf) = clamp(tf/6, 2 s, 15 s)`. A client
  may request a different cadence but never a faster one than the 2 s floor, so
  one browser tab cannot become a load generator against the market source.

### 2.2 `GET /api/chart/stream?symbol=&tf=[&frames=&interval=]`

`text/event-stream`, `Cache-Control: no-cache`, `X-Accel-Buffering: no`. It
inherits the P18.1 auth gate like every other `/api/*` route (a regression test
in `tests/test_auth.py` pins the 401 for an anonymous client). `frames` bounds
the stream for tests and scripts; the dashboard omits it and streams until the
tab closes.

### 2.3 Live toggle in the chart workspace (`web/app.py`)

- **◉ Live / ■ Stop live** button in the chart toolbar plus a permanent status
  line under it. The status line is never silent: *off*, *connecting*,
  *● LIVE … N updates this session*, *⚠ STALE — no new data for Ns … treat it as
  unknown, not as a quiet market*, *⚠ FEED ERROR — <reason>*, or
  *⚠ DISCONNECTED — reconnecting*.
- A streamed bar calls **`series.update(bar)`** on the existing candlestick
  series — the chart is not rebuilt, so zoom, overlays, zones and drawings all
  survive. `_chartData.candles` is updated in step, so a later reload, replay or
  drawing-time snap agrees with what is on screen.
- **Frames for another symbol/timeframe are dropped**, and an *older* bar can
  never rewrite history.
- The stream **follows the selected series** (changing symbol/timeframe closes
  the old stream and opens the right one) and **yields to replay** (starting
  playback stops the stream; the two can never share the pane).

### 2.4 Drawing tools (`web/app.py`)

- **╱ Trend** (two clicks), **─ Ray** (one click, horizontal to the last bar),
  **▭ Box** (two corners), plus **⌫ Undo** and **🗑 Clear**. The status line
  coaches each step ("now click the second point").
- Clicks are read through Lightweight Charts' `subscribeClick`, converted with
  `series.coordinateToPrice` / `timeScale().coordinateToTime`, and **snapped to
  the nearest loaded bar** so a drawing sits on the chart's own time scale.
- **Persistence** is `localStorage` under `sky.drawings.v1.<SYMBOL>.<TF>`, so
  drawings return on reload and never leak between series. Storage is treated as
  hostile input: malformed entries are dropped and an unsafe `id` is replaced
  before it can reach the DOM.
- **MY DRAWINGS** card lists every mark with its price(s) and a ✕ to remove one.
- **📎 Attach to journal note** appends a plain-text summary of the marks to the
  journal note field and opens the Journal tab. The human still picks the trade
  and presses save — nothing is written automatically.

### 2.5 The dashboard-killing bug this build caught and fixed

`HTML` in `web/app.py` is a **plain (non-raw) triple-quoted Python string**. Both
existing JS harnesses (`tests/test_dashboard_js.py`, `tests/test_workstation_js.py`)
and the CI syntax step extracted the script from the **file text**, so they never
saw what Python actually produces. The W1/P18.3 job-log line contained a literal
`'\n'`, which Python turned into a **real newline inside a JS string literal** —
`SyntaxError: Invalid or unexpected token` — killing the *entire* inline script
in any real browser. The dashboard was, in fact, dead on `main`.

- Fixed the line (`String.fromCharCode(10)`, the convention already used
  elsewhere in the file).
- Added **`test_served_script_is_valid_javascript`**, which parses the evaluated
  `web.app.HTML` — what Flask sends — with `node --check`. It runs inside
  `pytest`, so CI already executes it via the existing "Run tests" step.
- **Not applied:** the extra `.github/workflows/ci.yml` step that would also
  `node --check` the served blocks in the dedicated JS syntax job. The Arena
  GitHub App has no `workflows` permission, so the push was rejected and the
  workflow file was left untouched. The pytest guard above covers the same
  failure; a maintainer can optionally mirror it in the workflow by parsing
  `from web.app import HTML` there too.

---

## 3. Tests

Suite: **1053 passed / 1 skipped** (was 1030/1 — **+23**), plus compile,
dashboard-JS syntax (source *and* served), offline engine smoke and the
clean-install wheel gate.

- `tests/test_live_stream.py` (new, 9) — bounded cadence; JSON-safe bar
  conversion; a changed bar → `candle`; an unchanging feed → `waiting` then
  `stale` with its age; a raising source → `error` frames, backoff and the
  stream continues; an empty source is an error, not silence; frame ids.
  Two of them drive the real Flask route.
- `tests/test_workstation_js.py` (+13) — five live-stream tests (update in place
  without rebuilding the chart, honest stale/error/disconnect labels, ignoring
  foreign and older bars, following the selected series, yielding to replay,
  clean stop) and eight drawing tests (place/persist a trendline, ray to the
  last bar and box edges, survive reload and stay scoped per symbol+timeframe,
  undo/clear, remove one, ignore off-pane clicks and refuse to draw during
  replay, survive corrupt storage without XSS, attach to the journal note).
- `tests/test_dashboard_js.py` (+1) — the served-script parser described above.
- `tests/test_workstation.py`, `tests/test_auth.py` — the new controls exist in
  the served HTML; the stream endpoint is behind auth.

The shared JS harness gained a click dispatcher, a `series.update` recorder, a
real in-memory `localStorage` and an `EventSource` stub that tests push frames
into.

---

## 4. Honest flags (per §0a)

- **No real browser was opened** — none is installable in this sandbox. The UI
  was verified through the node harness (real dashboard JS against a stubbed
  chart library), the Flask test client, and a running dev server answering
  `curl` on `/` and `/api/chart/stream`. Pixel-level appearance was not eyeballed.
  The one class of "looks fine in the harness, dead in the browser" bug that
  *can* be caught mechanically is now caught (§2.5).
- **Streaming is server-side polling, not a WebSocket.** The roadmap named
  `data/ws_client.py`; this build reuses the existing REST candle source on a
  2–15 s cadence instead, because that is the source `/api/chart` already
  trusts, it works in `DEMO_MODE` with no network, and it needs no new
  dependency. Upgrading the *source* behind `candle_events` to `ws_client` later
  changes no client code — the SSE contract stays the same. On a 1 m chart the
  worst-case lag to a new bar is ~10 s.
- **In `DEMO_MODE` the sample candles never change**, so the stream reports
  `live` once and then correctly degrades to `waiting` → `stale`. That is the
  honest label for a static source, and it is exactly what the operator should
  see if a real feed dies.
- **Each open stream holds one Flask thread** (the same as the P18.3 job SSE).
  Fine for one operator with a few tabs; a many-client deployment needs a real
  WSGI/ASGI server, which is a P18.5/P19 packaging decision.
- **Drawings are browser-local.** `localStorage` means they do not sync between
  devices and are lost if the browser profile is cleared. Server-side
  persistence was not invented; "attach to journal" is the honest bridge to the
  scan record, and it is a human action.
- **Boxes are drawn as their top and bottom edges** (two 2-point line series),
  like the W2 zone bands, because Lightweight Charts v4 has no rectangle
  primitive. Vertical edges are not drawn.

---

## 5. What is deliberately not here

- **A WebSocket tier for the chart** (see §4) and any live *health* stream.
- **Fibonacci / measured-move / text-annotation tools**, drawing edit-by-drag,
  and multi-colour styling — the three named tools ship; a full drawing suite is
  its own project.
- **Server-side drawing storage or a drawings API** — nothing new is written to
  the database.
- **Any change to signals, thresholds, graduation, the risk gate or paper
  trading.** This build is display and annotation only: it cannot place an
  order (no exchange-order path exists anywhere in SKY) and cannot change what
  the desk decides.
