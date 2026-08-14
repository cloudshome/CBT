# REAL_DATA_RUN — 2026-08-14 · P12.3.2 · SKY's first real market data

> **What this is:** the first time real market data has ever entered this
> project, and the first honest re-run of P11 / P12.1 / P12.3 on it.
> **What it is not:** a green light. The graduation gate is still closed,
> and it now has a real-data reason to be.
>
> Companion documents: `docs/PATH_TO_REAL_MONEY.md` (the audit that
> reordered the ladder to put this milestone next) and
> `SESSION_STATE.md` (the session record). Every number below was
> produced by the commands shown, on this repo, this day.

---

## 1. What shipped (the machinery, all offline)

The sandbox that runs these sessions **cannot reach any exchange**
(verified: Binance/Binance Vision/Bybit/OKX/Kraken/Coinbase/Coingecko/
CryptoCompare/Yahoo all reset the TLS handshake; PyPI and GitHub are the
only egress). So the transport was substituted honestly, and everything
downstream — the store, the rollups, the grader, the protocol, the
scorecard — is the exact code the project already trusts.

- **`data/backfill.py::backfill_from_csv`** — imports a local
  Binance-style OHLCV CSV (Vision 6-column or raw 12-column klines,
  plain or gzipped) through the same adapter boundary as the REST
  backfill: validate → sort → `normalise_klines()` → `CandleStore.write()`.
  A re-run adds zero rows (store upsert PK). Reports rows read/added,
  duplicate timestamps, sanity-dropped rows, misaligned timestamps,
  gaps (same detector P10.3 uses), span, and the file's sha256.
- **`--csv-sha256` provenance pin** — the import refuses to write
  anything unless the decompressed file matches the published digest.
- **`data/store.py::StoreClient`** — a `klines()`-shaped reader over the
  Parquet store, so the offline walkers run on stored real candles
  exactly as they run on a live client.
- **CLI** — `python main.py backfill --from-csv PATH [--csv-sha256 HEX]
  [--rollup]`; `backtest --source store --market spot` (with `--step`);
  `simulator --source store --market spot`; `scorecard --since/--until`
  (epoch-ms or YYYY-MM-DD) so one book can hold several data eras
  without mixing them.
- **Tests** — `tests/test_backfill_csv.py` (11 new, all offline):
  schema, idempotence, gzip, headerless klines, pin enforced, duplicates
  and gaps reported, insane rows dropped-and-counted, StoreClient
  cursors, CLI round-trip + pin refusal. Suite **539 → 552 pass / 1
  skip** (+13 with the scorecard era tests).

---

## 2. The data — what it is and how it was verified

| item | value |
|---|---|
| market | Binance **spot** BTCUSDT, 1m candles |
| window | 2025-01-01 00:00 UTC → 2026-04-29 23:59 UTC (484 days, 696,960 bars) |
| original source | `data.binance.vision` — Binance's official public market-data archive (`binance_spot_public_archive`) |
| transport into this sandbox | git clone of `github.com/j-greig/insomnia-hype-data` @ commit `9791d85` (PyPI/GitHub are the only reachable hosts here) |
| sha256 (uncompressed CSV) | `c4ad60296d9c13b77886fd916795ff38e7f605b387c64c82bcda9f0464b934b7` — **verified on import**, matches the dataset's own manifest |
| gaps / duplicates / sanity | **0 gaps, 0 duplicates, 0 rows dropped** (report below) |
| store series | `data/store/parquet/candles/exchange=binance/market=spot/symbol=BTCUSDT/timeframe=1m` (+ P10.3 rollups to 5m/15m/1h/4h/1d, source=`csv`/`aggregated`) |

The P10.5 quality pillar reads the 1m series as `down` — *history too
stale* — which is correct and expected: this is a **frozen archive
window**, not a live feed, and the pillar's staleness check protects the
live readiness strip. It has no bearing on walk-forward research over a
closed window.

Import report (verbatim):

```
csv import  binance/spot/BTCUSDT/1m
  sha256 c4ad6029…b934b7  ✓ pin verified
  rows read 696,960  added 696,960  (store now 696,960)
  span 484.0 days  gaps 0  gaps_remaining 0
  rollup: {'master_bars': 696960, 'added': {'5m': 139392, '15m': 46464,
           '1h': 11616, '4h': 2904, '1d': 484}}
```

---

## 3. P12.1 — the sealed protocol, first real run

```
python main.py validate --exchange binance --market spot \
    --symbol BTCUSDT --tf 15m --bars 12000
```

12,000 most-recent 15m bars (2025-12-27 → 2026-04-29, ≈4 months),
train/val/oos/recent = 60/15/15/10, step 3, primary horizon 1h,
sealed OOS. Seal: `data/store/validation/binance_spot_BTCUSDT_15m.json`,
fingerprint `1223819609d75213`, never resealed.

| window | signals | decided | WR | expectancy | PF | bar |
|---|---|---|---|---|---|---|
| train | 6,545 | 878 | 16.5% | **−0.452R** | 0.459 | ✗ |
| val | 1,696 | 203 | 23.2% | **−0.251R** | 0.673 | ✗ |
| oos | 1,709 | 268 | 27.2% | **−0.101R** | 0.862 | ✗ |
| recent | 1,113 | 156 | 18.6% | **−0.429R** | 0.472 | ✗ |

**Verdict: FAIL on every window.** The primary (1h) horizon loses money
on real data everywhere, including the sealed out-of-sample window.

For comparison, the last published synthetic protocol headline was
**+0.341R gross** (P12.3, random-walk data). The fall is the correction
`docs/PATH_TO_REAL_MONEY.md` §1 predicted — not a regression, and it was
expected to arrive exactly here.

---

## 4. P12.3 — the scorecard, first real run

```
python main.py backtest --source store --market spot --symbol BTCUSDT \
    --tf 15m --bars 12000 --step 3 --save      # → 33,189 rows, run 20260814_132722
python main.py scorecard --source db --symbol BTCUSDT \
    --since 2025-01-01 --until 2026-04-30
```

All-horizon block (24,215 decided backtest + 494 paper rows, span
123.4d): **+0.180R / 32.2% WR / PF 1.266 — 🔴 FAIL** (bar unchanged).

Per **horizon** (backtest book only) — this is the finding that matters:

| horizon | decided | WR | expectancy (gross) | PF |
|---|---|---|---|---|
| 1h | 2,296 | 20.6% | **−0.326R** | 0.589 |
| 4h | 7,854 | 28.5% | −0.032R | 0.955 |
| 24h | 14,065 | 36.6% | **+0.400R** | 1.632 |

- The engine's plans lose money at the 1h horizon — the protocol's
  locked primary — and are roughly flat at 4h.
- Only the **24h horizon** shows gross-positive expectancy. Before
  anyone gets ideas: (a) the protocol's primary horizon is 1h and the
  protocol is sealed; (b) taker costs measured in
  `docs/PATH_TO_REAL_MONEY.md` §2 are ≈ −0.121R per round trip, so
  +0.400R gross ≈ **+0.28R net** — below the restated +0.50R **net**
  bar; (c) walk-forward samples overlap (~30×; P12.3.3 still pending),
  so 14,065 decided is on the order of a few hundred independent
  outcomes. The 24h number is the one real thing worth a next look —
  it is not a license.

Per **setup** (all horizons): **Breakout Buy −0.630R over 6,062 decided
(10.2% WR, PF 0.298)** — negative at *every* horizon (−0.657R at 1h,
−0.618R at 24h). The scorecard's first job was always pruning, not
reporting (`docs/PATH_TO_REAL_MONEY.md` §6.2); real data now confirms
the deletion case. Buy Pullback (+1.077R, 56.3% WR) and FVG Retest Buy
(+1.130R, 58.3% WR) are the only setups with real gross-positive
expectancy across the window — same caveats as above apply.

---

## 5. P11 — the paper grind, first real run

```
python main.py simulator --source store --market spot --symbols BTCUSDT \
    --tf 15m --bars 6000 --step 3
```

Real-data grind added **8,300 unique backtest samples + 494 paper
samples** (era: 2026-02-16 → 2026-04-29). The graduation gate:

| criterion | value | bar |
|---|---|---|
| expectancy (primary family) | **+0.348R** | ≥ +0.50R ✗ |
| win rate | **36.8%** | > 55% ✗ |
| profit factor | 1.55 | ≥ 1.5 ✓ |
| rule compliance | 100% | ≥ 90% ✓ |

**Gate: still closed.** Sweep Reversal Buy remains the only
sample-proven setup and its real expectancy is **+0.048R** — proof of
nothing. Buy/Sell Pullback and Sweep Reversal Sell still miss their
paper floors. Nothing here is close to graduation, and on real data the
distance is now measurable rather than assumed.

---

## 6. What this means (the aim: a real-money trader)

1. **The synthetic era is over for evidence.** Every future number in
   this repo must be produced against this store (or a newer backfill
   of it). The old synthetic numbers survive only as history.
2. **The engine, as-is, is not an edge at its primary horizon.** It is
   negative on real data in every protocol window. This is the most
   valuable fact the project has ever measured — it was not available
   before today.
3. **Two concrete next steps are data-backed, not speculative:**
   - **Prune Breakout Buy** (decision to be made by the human; the
     evidence is −0.63R / PF 0.30 over 6,062 decided, negative at every
     horizon).
   - **Examine the 24h horizon honestly** — it is the only gross-positive
     cell in the table, and it is still below the net bar. That is the
     single lead worth the next session's attention, ahead of any new
     machinery.
4. **The gate was not touched.** Not loosened, not renegotiated, not
   argued with. It failed on real data the way it should: loudly and
   with the receipts attached.
5. **Costs still aren't in the number** (P12.6) and **sample counts are
   still overlap-inflated** (P12.3.3). Both corrections are now the
   next items on the ladder, and both make the numbers above worse,
   not better.

---

## 7. Repro

```bash
# one-time: get the dataset (any machine; this one uses the GitHub route)
git clone https://github.com/j-greig/insomnia-hype-data /tmp/insomnia-hype-data

# import through SKY's own machinery (idempotent; 0 rows on re-run)
python main.py backfill --from-csv \
    /tmp/insomnia-hype-data/data/market/btc_1m_binance_spot_bulk_2025-01-01_2026-04-30.csv.gz \
    --symbol BTCUSDT --tf 1m --market spot \
    --csv-sha256 c4ad60296d9c13b77886fd916795ff38e7f605b387c64c82bcda9f0464b934b7 \
    --rollup

python main.py store --market spot --symbol BTCUSDT --tf 15m   # inspect
python main.py validate --exchange binance --market spot --symbol BTCUSDT \
    --tf 15m --bars 12000                                      # P12.1 (sealed)
python main.py backtest --source store --market spot --symbol BTCUSDT \
    --tf 15m --bars 12000 --step 3 --save                      # P12.3 rows
python main.py simulator --source store --market spot --symbols BTCUSDT \
    --tf 15m --bars 6000 --step 3                              # P11 grind
python main.py scorecard --source db --symbol BTCUSDT \
    --since 2025-01-01 --until 2026-04-30                      # era-clean block
```

On a machine with exchange egress, prefer the live route instead of the
mirror: `python main.py backfill --symbol BTCUSDT --tf 1m --market spot
--since 2025-01-01` — the import path above exists for offline
reproduction only.
