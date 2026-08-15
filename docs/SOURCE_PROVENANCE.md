# Source provenance in saved keys (P12.11)

> **Status:** shipped in v2.22.0.
> **Closes:** Dukascopy blocker #3 — *"source provenance reaches saved
> backtest/calibration keys"* ([`DUKASCOPY_XAU_ADAPTER.md`](DUKASCOPY_XAU_ADAPTER.md)).
> **Module:** [`data/provenance.py`](../data/provenance.py).

## The problem

The learning loop had one dimension too few.

Every decided row — backtest or paper — was filed under
`plan_type` or `plan_type::regime` and **nothing else**. The price series that
produced the row was not part of its identity. So these two rows:

| row | series | what it is |
|---|---|---|
| `Buy Pullback::TRENDING_BULL` | Binance BTCUSDT spot candles | the live book the desk trades |
| `Buy Pullback::TRENDING_BULL` | Dukascopy XAUUSD **bid-only** m1 import | a research series, one side of the spread, on a venue we do not trade |

…were **the same calibration entry**. Their outcomes averaged together, and
the resulting multiplier was applied to live signals.

That is not a hypothetical. Measured on a seeded book of 300 rows per series:

```
live series only        Buy Pullback::TRENDING_BULL   E +0.46R → net +0.29R   ×1.07
research book pooled in (before P12.11: one entry, inflated by +3.58R rows)
```

A bid-only gold research backtest could raise the confidence the engine
applies to a live BTC trade. This is why `docs/DUKASCOPY_XAU_ADAPTER.md`
prohibited `--save` outright: the *only* protection was a human remembering
not to type a flag.

## The fix

Provenance becomes part of the key.

### The source key

Three facts decide whether two price series are the same market:

```
exchange    binance | bybit | dukascopy | …    who printed the price
market      spot | perp                        which book
price_type  (blank) | bid | ask                which side of the spread
```

They compose into a **source key**:

```python
source_key()                                 # ''                    canonical live series
source_key("binance", "spot")                # ''                    canonical live series
source_key("binance", "perp")                # 'binance:perp'
source_key("dukascopy", "spot", "bid")       # 'dukascopy:spot:bid'
```

**The canonical live series is the empty string.** This is the load-bearing
design decision: it makes P12.11 strictly additive.

* Every calibration key SKY has ever written is byte-identical after the change.
* Every legacy row whose provenance columns are `NULL` reads as the canonical
  series — because that is what all pre-P12.11 history actually *is*, not a
  guess.
* Live scans resolve canonical keys, so their behaviour is unchanged.

### The calibration key

```
Buy Pullback                                   plan type only
Buy Pullback::TRENDING_BULL                    + regime            (B3)
Buy Pullback::TRENDING_BULL@dukascopy:spot:bid + source            (P12.11)
```

The `@source` suffix appears **only** for non-canonical series.

### What each layer does

| layer | behaviour |
|---|---|
| `data/store.py` | `StoreClient` stamps `exchange` / `market` onto the frame's `attrs` |
| `data/backtester.py` | `run_backtest_on_store()` reports the graded series' provenance, read off the frame |
| `data/database.py` | `backtest_results` / `paper_trades` gain `exchange`, `market`, `price_type`, `source_key`; `calibration` gains `source_key`; all idempotently migrated |
| `data/simulator.py` | grind samples carry the provenance of the frame they were walked on |
| `data/scorecard.py` | rows carry `source_key`; reports gain a `by_source` split and a `sources` inventory |
| `brain/calibrator.py` | groups by source; a one-sided series is never `proven` |
| `engine/calibration_hook.py` | the **live** path resolves canonical keys only |
| `brain/risk_gate.py` | `setup_proven()` counts evidence on **one** series (default: live) |

## Guarantees

1. **A research series cannot move live confidence.** `apply_calibration()`
   narrows from `plan_type::regime` to `plan_type` *within one source* and
   never falls back across sources. A `…@dukascopy:spot:bid` entry is simply
   not found on a live scan — neither its boost **nor its filter**.
2. **A research series cannot prove a setup.** `setup_proven()` counts samples
   for the canonical series by default, and any bid/ask-only series is marked
   `research_only` and forced `proven: False` — a one-sided price is not an
   executable round trip, however good its expectancy looks.
3. **Pooling is never silent.** A scorecard built from more than one series
   reports `sources.mixed: true`, splits the block `by_source`, and warns that
   the headline number is a blend.
4. **Strictly additive.** Canonical keys, legacy NULL rows, crypto output and
   the graduation bar are all unchanged. The suite went 681 → 704 with no
   existing test modified.

## Using it

```bash
# Score only the live series
python main.py scorecard --source backtest --source-key live

# Score only the XAU research import
python main.py scorecard --source backtest --source-key dukascopy:spot:bid

# Pool everything (default) — the report names the mix and flags one-sided data
python main.py scorecard --source backtest

# See which series the learning store holds
python main.py learn
```

Saving a research backtest now states where it landed:

```
Saved 1240 graded plans to the signal database (run 20260816_101500).
Filed under source 'dukascopy:spot:bid' (dukascopy spot bid-only) —
a separate calibration key from the live series.
This series is one-sided (not an executable round trip): research evidence
only, never 'proven'.
```

Other surfaces:

* **HTTP** — `GET /api/scorecard?source_key=live|dukascopy:spot:bid|all`;
  `GET /api/learning` returns a `sources` inventory.
* **MCP** — `scorecard` takes `source_key` (server 1.10.0).

## What this does *not* do

* It does not make Dukascopy XAU tradeable evidence. It makes the evidence
  **separable**, which is the precondition for judging it.
* It does not merge or convert series. Cross-source pooling remains
  prohibited (`DUKASCOPY_XAU_ADAPTER.md` §6).
* It does not touch the graduation bar. `≥ +0.50R` net, `> 55%` WR, `PF ≥ 1.5`
  are unchanged, and the remaining acceptance-gate items (PAXG-vs-XAU basis,
  sealed-OOS results, human approval) are still open.

`--save` on a Dukascopy XAU backtest is now **permitted** — its rows land in
their own keys and cannot recalibrate the live proxy. Promotion of that series
to canonical research status remains a separate, human-approved decision.
