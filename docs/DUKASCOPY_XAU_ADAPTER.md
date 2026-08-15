# Dukascopy XAUUSD adapter

## Decision

Use [`dukascopy-node`](https://github.com/Leo4815162342/dukascopy-node) only as
an **optional external acquisition worker** for historical spot-gold candles.
Do not vendor it, make Node.js a SKY runtime dependency, use it as a trading
brain, or replace Binance as the canonical BTC/ETH execution dataset.

The useful fit is narrow:

- **BTC/ETH:** Binance spot/perp remains canonical. Dukascopy crypto may be a
  later robustness comparison, never silently pooled with Binance.
- **XAUUSD historical research:** Dukascopy is a materially better underlying
  than the live Binance `PAXGUSDT` proxy.
- **Live XAU:** unchanged for now. The existing PAXG proxy remains explicit;
  imported Dukascopy history does not pretend to be a live feed.

## Why this is a small adapter, not a “data factory” rewrite

SKY already has most of the proposed factory:

- canonical UTC candle schema and partitioned Parquet store (`data/store.py`);
- provenance, dedupe/upsert, gap and sanity checks;
- 1m rollups, feature store, structure/indicator/regime engines;
- walk-forward validation, sealed OOS, scorecard, net-cost expectancy;
- independent risk gate and paper lifecycle.

Creating parallel `data/raw`, `normalized`, `candles`, and `data_factory`
trees would duplicate those layers and create two truths. The adapter therefore
enters through the existing boundary:

```text
dukascopy-node CSV
        ↓
backfill --from-csv --csv-source dukascopy
        ↓
parse + SHA-256 pin + sanity + dedupe + gap report
        ↓
normalise_klines
        ↓
CandleStore: dukascopy/spot/XAUUSD/<timeframe>
        ↓
existing validate / backtest / scorecard / quality tools
```

## Acquire outside SKY

Pin the external tool version and request UTC epoch timestamps, volume, and an
explicit price side. Start with native **m1 candles**, not ticks:

```bash
npx -y dukascopy-node@1.50.0 \
  --instrument xauusd \
  --date-from 2020-01-01 --date-to 2026-08-01 \
  --timeframe m1 --format csv \
  --price-type bid --utc-offset 0 --volumes --flats \
  --directory ./download --file-name xauusd_2020_2026_m1_bid \
  --retries 3 --retry-on-empty

sha256sum ./download/xauusd_2020_2026_m1_bid.csv
```

The exact output name is controlled above; inspect the file before import. It
must have the documented shape:

```text
timestamp,open,high,low,close,volume
<UTC epoch ms>,...
```

Do not use `--date-format` or `--time-zone`: the SKY adapter deliberately
accepts numeric UTC epoch milliseconds to remove timezone ambiguity.

## Import into SKY

```bash
python main.py backfill \
  --from-csv ./download/xauusd_2020_2026_m1_bid.csv \
  --csv-source dukascopy --price-type bid \
  --symbol XAUUSD --tf 1m \
  --csv-sha256 <DECOMPRESSED_FILE_SHA256> \
  --rollup

python main.py store \
  --exchange dukascopy --market spot --symbol XAUUSD --tf 15m
```

The importer stores:

- `exchange=dukascopy`
- `market=spot`
- `symbol=XAUUSD`
- `source=dukascopy_csv`
- `price_type=bid|ask`

This series cannot overwrite or masquerade as Binance/PAXG because venue is
part of the store primary key.

## Research commands

```bash
python main.py validate \
  --exchange dukascopy --market spot --symbol XAUUSD --tf 15m --bars 12000

python main.py backtest \
  --source store --exchange dukascopy --market spot \
  --symbol XAUUSD --tf 15m --bars 12000 --step 3

python main.py scorecard \
  --source store --exchange dukascopy --market spot \
  --symbol XAUUSD --tf 15m --bars 12000 --quality

python main.py quality \
  --exchange dukascopy --market spot \
  --symbol XAUUSD --tf 15m --bars 12000
```

Do **not** add `--save` until the book is reviewed. Saving mixes graded rows
into the learning database by symbol; source-series provenance is not yet a
calibration dimension. A Dukascopy XAU backtest must not silently recalibrate
the live PAXG proxy.

## Important limitations before calibration or micro-live

1. **Bid is not an executable round trip.** A bid-only OHLC backtest lacks the
   ask-side entry/exit spread. The existing generic cost model is not evidence
   of Dukascopy/XAU execution costs. The importer refuses to mix bid and ask in
   one store series; parallel bid/ask storage and an as-of spread model are a
   later schema milestone. Until then, configure and validate a conservative
   gold-specific cost assumption outside any graduation claim.
2. **Market calendar.** The current crypto-first gap/readiness logic assumes a
   continuous market. XAU's scheduled weekend/session closures can appear as
   gaps. Acquisition with `--flats` reduces false gaps, but a proper XAU market
   calendar is still required before treating readiness as authoritative.
3. **Volume semantics.** Dukascopy volume is feed/tick volume in configurable
   units, not Binance base-asset volume. Never compare the raw magnitude across
   those venues without normalization.
4. **No tick ingestion yet.** SKY intentionally starts with m1 OHLCV. Tick data
   only becomes worthwhile with bid/ask spread, tick-count, and microstructure
   aggregation plus dedicated storage/quality rules. Feeding raw ticks into the
   current candle engine would add complexity without a validated target.
5. **Availability is not integrity.** Empty files, retries, gaps, timestamp
   alignment, OHLC sanity, SHA provenance, and expected row counts must all be
   checked. The adapter refuses malformed data and does not repair values.
6. **No cross-source pooling.** Compare Dukascopy XAU and PAXG as separate
   robustness books. Do not concatenate them into one price history.

## Acceptance gate for a later “canonical XAU” promotion

Dukascopy history may replace PAXG as the canonical **research** series only
after:

- a market-calendar-aware quality check is green;
- bid/ask spread and XAU-specific costs are modeled net of costs;
- source provenance reaches saved backtest/calibration keys;
- PAXG-vs-XAU basis/deviation is measured, not assumed;
- walk-forward train/validation/sealed-OOS results clear the unchanged bar;
- a human explicitly approves the progression decision.

Until then this adapter expands research data; it does not open the risk gate.
