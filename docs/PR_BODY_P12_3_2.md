## P12.3.2 — real market data (first real data ever in SKY)

Branched from `main` @ `f403ed4` (PR #21). 0 regressions. Suite **539 → 552 pass / 1 skip** (+13). Version **2.11.1 → 2.12.0**.

### What shipped

- **`data/backfill.py::backfill_from_csv`** — offline CSV import through the same adapter boundary as the REST backfill (validate → sort → `normalise_klines` → `CandleStore.write`). Idempotent; reports duplicates / sanity drops / misalignment / gaps; **`--csv-sha256` provenance pin refuses mismatches**.
- **`data/store.py::StoreClient`** — `klines()`-shaped reader over the Parquet store; `backtest --source store --market spot [--step N]`, `simulator --source store --market spot`.
- **`scorecard --since/--until`** — era filters (epoch-ms or YYYY-MM-DD) so one book can hold synthetic and real rows without mixing.
- **`docs/REAL_DATA_RUN_2026-08-14.md`** — provenance, repro commands, side-by-side numbers.
- Tests: `tests/test_backfill_csv.py` (11) + scorecard era tests (2), all offline.

### The data

Real Binance **spot** BTCUSDT 1m, **2025-01-01 → 2026-04-30** (696,960 bars, 0 gaps), from Binance's official public archive (`data.binance.vision`), transported via `github.com/j-greig/insomnia-hype-data` @ `9791d85` (the sandbox's only egress); **sha256 verified against the dataset's own manifest** (`c4ad6029…b934b7`). Rolled up to 15m with SKY's own P10.3.

### First real runs (all reproducible)

| run | result |
|---|---|
| **P12.1 sealed protocol** (12,000 real 15m bars, 1h primary, seal `1223819609d75213`) | **FAIL every window**: train −0.452R · val −0.251R · **oos −0.101R** · recent −0.429R |
| **P12.3 scorecard** (24,215 decided) | all-horizon +0.180R / 32.2% WR / PF 1.266 · per horizon: 1h **−0.326R**, 4h −0.032R, **24h +0.400R gross** (≈ +0.28R net — below the restated +0.50R net bar) · **Breakout Buy −0.630R** (6,062 decided, negative at every horizon) |
| **P11 grind** (+8,300 backtest / +494 paper real samples) | gate **still closed**: +0.348R / 36.8% WR / PF 1.55 / compliance 100% |

**The honest reading:** the fall `docs/PATH_TO_REAL_MONEY.md` predicted has arrived. The engine is negative at its locked primary horizon on real data in every window, including the sealed OOS. Nothing was re-tuned in response — no horizon change, no bar change, no strategy change. The graduation bar was not touched.

**Invariants held:** no exchange order surface, no Freqtrade/Hyperopt/FreqAI/Backtrader, one grader (`data/backtester.py`), no strategy-module catalog, no recursive lookahead work, one PR not self-merged.

**Next on the ladder:** P12.6 — fees-first `E_net` becomes the number the gate reads (bar already restated +0.50R net), then P12.3.3 effective sample size.
