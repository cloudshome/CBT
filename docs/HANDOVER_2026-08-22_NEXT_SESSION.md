# Next-session handover — SKY pipeline (2026-08-22, v2.58.0)

> **Contract for the next session**
> **Branch:** `p13.6-compare-ladder` (PR #… opened from this branch)
> **Base:** `main` @ `0fb30b0` (P13.5, v2.57.0)
> **Suite:** 1393 passed / 1 skipped (Node 22 + `mcp` installed)
> **Wheel gate:** OK (`cryptobrain-2.58.0-py3-none-any.whl`)

---

## What this pipeline shipped (13 commits, all on the PR branch)

### 1. P13.6 — Paper + compare ladder (`c587685`, v2.58.0)
- `edge-validate --ladder` pairs the decisive-window verdict with the
  canonical live paper book (P11) in one report:
  Backtest (whole walk) → OOS + recent (decisive) → Paper (canonical live),
  all net of costs, empty rungs render `n/a` (never an invented number).
- `engine/edge_validation.py`: `paper_stats_from_rows` (aggregates
  `SignalDB.live_book_rows()`), `compare_ladder` + `_ladder_note` (honest
  degradation Δ / hold / keep-grinding-P11 / thin-OOS notes),
  `format_compare_ladder`, `paper_rows=` on `edge_validate_report`
  (pre-P13.6 invocations byte-identical).
- `main.py edge-validate --ladder` reads `db.live_book_rows()` (empty DB →
  honest n/a rung). JSON output carries the `ladder` object.
- **P13.1 monotonicity closed:** `--execution slip` proven strictly
  worse-or-equal to `none` on real graded output (per-trade `rr_achieved`/
  `rr_net` + per-window aggregate tests).
- Version lockstep 2.58.0 (config.VERSION = pyproject = sky-shell-v).
- 16 ladder tests + 2 monotonicity tests in
  `tests/test_edge_validation_ladder.py` / `test_edge_validation.py`.

### 2. Refactor lane — both maintainability debts CLOSED
- **`main.py`: 3,437 → 992 lines.** New `cli/` package:
  - `cli/common.py` — `_client/_sym/_symbols/_source_key_arg/_load_calibration/run_scan`
  - `cli/validation.py` — cmd_backtest/validate/edge_validate/xau_evidence/monte
  - `cli/daily.py` (28 cmds), `cli/paper.py` (10), `cli/analytics.py` (3),
    `cli/market.py` (7), `cli/system.py` (8)
  - `main` keeps: launcher bootstrap, argparse, re-exports.
- **`web/app.py`: 10,083 → 347 lines.** New `web/` modules:
  - `web/payload.py` — scan-payload pipeline (10 helpers + state)
  - `web/static/terminal.html` — the 7k-line terminal template (loaded at
    import; 8 test helpers updated to read the file)
  - `web/routes_auth|scan|paper|chart|system|v1.py` — all 100 route handlers,
    each exporting `register(app, ctx)` (closure-capture; handler bodies
    byte-identical, verified per domain)
  - `make_app` now holds only: auth/CSRF closures, the before-request gate,
    the shell pages, and the register calls.
- All moves verified byte-identical; suite green after every step; wheel
  gate green. ROADMAP §19 + TODO updated.

### Known environment notes
- Full suite needs **Node ≥ 21** (served JS references the global
  `navigator`) + `pip install mcp cryptography`. Managed node is v20 → 113
  pre-existing JS-harness failures (also on pristine main). Node 22
  provisioned at `../node-v22.17.0-linux-x64/bin` (prepend to PATH).
- git identity: `-c user.name="arena-ai-coding-agent[bot]" -c
  user.email="298482267+arena-ai-coding-agent[bot]@users.noreply.github.com"`
  (matches repo history; no global config touched).
- Clone requires the owner's PAT (fine-grained, contents read); token was
  stripped from the remote URL after clone.

---

## Next session jobs (in priority order)

### 1. Merge/land the PR (owner decision)
The PR from `p13.6-compare-ladder` is ready. Owner merges (or requests
changes). After merge, rebase any new work on `main`.

### 2. Lane A — P11 real paper proof on the real-data Hub (the money path)
Needs the real-data host (real store DB with canonical-live paper trades).
- Run `python main.py edge-validate --source store --tf 15m --bars 2000
  --monte --ladder` on real BTC data.
- The paper rung fills only from decided canonical-live trades (simulator
  rows never count — P12.13). Watch the ladder's degradation Δ as P11
  grinds.
- Re-verify verdict thresholds (`min_decided=30`, `regime_min_decided=10`,
  `positive_regime_frac=0.5`) on real data; the graduation bar is unchanged
  and still closed.

### 3. XAU sealed evidence (`xau-evidence`)
Needs real Dukascopy/binance data: `python main.py xau-evidence` builds the
basis dossier (binance spot PAXG vs dukascopy spot XAU) + sealed-OOS review.
Read-only; never records approval or unlocks micro-live.

### 4. P22 — trusted-signer drills
Needs real Windows/Android/Ubuntu hosts (W4.2 always-on Hub):
- `companion` / `hub` status on each host, systemd unit states,
- signer drills (open signer, sign a real message, restart, sign again).

### 5. Terminal visual QA on a real browser
The dashboard ships a lot of surface; on the real-data host, open the
terminal in Chrome and QA: auth setup flow, scan/sentiment/intelligence
cards, paper monitor, review queue (approve/reject), trade terminal confirm
→ desk path → paper position, practice tape, weekly review, PWA install +
offline page + push test.

---

## Honest boundaries (unchanged)
- The ladder is a comparison surface — it never approves, never moves a
  threshold, never unlocks micro-live, never places an order.
- The graduation gate and default `backtest` stay on `EXECUTION_MODEL=none`.
- No threshold moved; no order path; no off-platform transactions.
