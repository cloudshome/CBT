# W3.5 part 2 — 2×2 multi-chart: synchronized crosshair — v2.48.0

**Shipped:** 2026-08-20 · branch `arena/01a01dbf-sky` · version **2.48.0**

---

## Summary

Completes the W2/W3.5 workstation backlog item "multi-chart layout (2×2)
with a synchronized crosshair across assets". The v2.43.0 scaffold already
shipped the four-up grid and zoom/pan sync; this release adds the missing
**crosshair sync**, per-browser sync toggles, honest empty-slot states, four
distinct default slots, and a timestamp-normalisation fix.

No threshold moved. No exchange order path exists. The multi-chart view
remains a comparison aid only — it never combines signals, never writes to
the desk, and never feeds calibration, the risk gate, or graduation.

---

## Delivered Components

### 1. Synchronized crosshair (the W3.5 remainder)

`web/app.py` (Chart tab JS, single served template):

- `multiSyncCrosshairTo(src, param)` — the new one-way broadcast. The source
  chart converts the pointer's pixel y back into a price via the vendored
  Lightweight Charts v4.2.3 `series.coordinateToPrice()` (falling back to the
  hovered bar's close when the engine cannot), then calls
  `chart.setCrosshairPosition(price, time, series)` on every other pane.
  When the pointer leaves the pane (`param.time` is undefined) the others get
  `clearCrosshairPosition()` — never an error.
- Re-entrancy guard `_multiCrosshair` (same pattern as `_multiSync` for zoom):
  programmatic `setCrosshairPosition` fires the target's own
  `subscribeCrosshairMove`, so the guard keeps the broadcast one-way.
- Multi-chart panes now set `crosshair: { mode: 0 }` (Normal) with the same
  line colours as the main workspace panes, so magnet snapping cannot fight
  the sync.

### 2. Per-browser sync toggles

- Control bar chips **"Zoom sync"** and **"Crosshair sync"** (checkboxes),
  on by default, persisted as `sky.multiSyncZoom` / `sky.multiSyncCrosshair`
  in localStorage. Toggles act immediately without reloading the charts;
  turning crosshair sync off clears all crosshairs.

### 3. Four distinct default slots (2×2 actually full)

- The old defaults collapsed to **three** panes whenever the primary symbol
  was BTCUSDT (`BTCUSDT 15m, BTCUSDT 1h, BTCUSDT 1h, ETHUSDT 1h` → dedupe
  dropped the duplicate). `multiDefaults()` now selects four distinct views:
  the primary series on two timeframes, then two other markets on the alt
  timeframe (BTCUSDT default → `BTCUSDT 15m, BTCUSDT 1h, ETHUSDT 1h,
  XAUUSD 1h`). Saved slots still override defaults; the dedupe and the
  symbol/timeframe allow-lists stay as safety nets.

### 4. Honest empty slots

- A slot whose feed failed or whose pair is unsupported now paints an
  explicit `no candles for SYMBOL TF — <error>` message instead of an empty
  chart that could be read as a quiet market.

### 5. Timestamp normalisation fix (silent 1970 dates)

- `multiCandleData()` was feeding `/api/chart` epoch-**seconds** into
  `new Date(...)`, which interprets the number as milliseconds — every
  multi-chart pane painted January 1970 dates. It now normalises like the
  backend (`_epoch_seconds`): seconds pass through, ms/µs are divided down,
  non-numeric values go through `Date` parsing. The single-chart workspace
  was unaffected (it hands `d.candles` straight to the engine).

### 6. Served-script trap cleanup

- `urlBase64ToUint8Array()` (VAPID push) contained `replace(/\-/g, '+')`
  inside the non-raw `HTML` Python string. Python ate the backslash
  (DeprecationWarning today; `/-/g` and `/\-/g` are the same regex, so it
  worked — but it was exactly the eaten-escape class the template notes
  forbid). Now written as `replace(/-/g, '+')`: identical served output,
  no warning, no future SyntaxError risk.

---

## Verification

- **5 new regressions** in `tests/test_workstation_js.py` (jsdom-style Node
  harness with an extended Lightweight Charts mock that records
  `subscribeCrosshairMove` / `setCrosshairPosition` / `clearCrosshairPosition`
  and logical-range propagation):
  - 2×2 grid renders four charts; one pointer moves all crosshairs to the
    same bar time + pointer price; leaving the pane clears the others; the
    sync toggle stops propagation.
  - Zoom sync toggle stops pan propagation without a reload.
  - A failed feed renders an explicit empty slot, not a blank chart.
  - Defaults are four distinct slots; duplicate saves collapse; invalid
    saved slots fall back to their defaults.
  - `multiCandleData` keeps seconds, divides ms, parses date strings.
- Full suite: **1282 passed, 1 skipped** (v2.48.0; +5 over v2.47.0's 1277).
- `ci/wheel_gate.py` builds `cryptobrain-2.48.0-py3-none-any.whl` with no
  duplicate entries.
- Live smoke: `DEMO_MODE=1 python main.py web --host 127.0.0.1 --port 8051`
  served HTTP 200; `/api/chart` returned 60 candles for each default slot
  (`BTCUSDT 15m`, `BTCUSDT 1h`, `ETHUSDT 1h`, `XAUUSD 1h`); the evaluated
  served `<script>` passes `node --check`.
- Honest: no browser in this sandbox — the crosshair wiring is proven with
  the Node harness + the vendored LC v4.2.3 API surface, not with a real
  pointer. The remote-bind guard correctly refused `--host 0.0.0.0` without
  an owner account (P18.1 behaviour preserved, not bypassed).

---

## Versioning

- `config.py` `VERSION` and `pyproject.toml` `version`: **2.47.0 → 2.48.0**
  (MINOR: user-visible chart feature + defect fix).

## Not touched (unchanged contracts)

- `/api/chart` payload shape; `web/chart_data.py`; SSE live stream; replay
  tape; drawings; the single-chart workspace; auth; the risk gate; any CLI.
