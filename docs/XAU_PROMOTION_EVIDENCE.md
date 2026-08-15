# XAU promotion evidence: PAXG-vs-XAU basis dossier

**Status: P12.12 shipped — research-only evidence tooling.**

Saving Dukascopy XAU candles makes gold evidence **separable**, not tradeable.
The `xau-evidence` command closes one missing measurement capability: it compares
separately stored Binance spot `PAXGUSDT` and Dukascopy spot `XAUUSD`, then reads
the existing Dukascopy sealed-validation envelope. It does not promote either
series, modify calibration, record approval, or place orders.

## Run on the real-data host

Both series must exist at the same timeframe under their own canonical store
coordinates:

- `binance / spot / PAXGUSDT / <tf>`
- `dukascopy / spot / XAUUSD / <tf>`

First run the unchanged locked protocol over the stored Dukascopy series:

```bash
python main.py validate \
  --exchange dukascopy --market spot --symbol XAUUSD --tf 15m \
  --bars 12000 --step 3 --min-decided 30
```

Do not use `--reseal` to improve an OOS number. Reseals are recorded in the
envelope history and are review evidence, not a tuning loop.

Then build the dossier:

```bash
python main.py xau-evidence --tf 15m --bars 12000 --min-overlap 100
python main.py xau-evidence --tf 15m --bars 12000 --min-overlap 100 --json \
  > xau-evidence.json
```

For an alternate store or seal location:

```bash
python main.py xau-evidence \
  --store-root /path/to/store \
  --seal-dir /path/to/store/validation \
  --tf 15m --json
```

This repository checkout has no real store. A clean-checkout run must report no
matched data and exit non-zero; synthetic fixtures test mechanics only and are
not basis or sealed-OOS evidence.

## Measurement contract

The comparison is intentionally strict:

1. Each source is read independently from its own store key.
2. Invalid/non-positive closes are excluded and counted.
3. Duplicate timestamps are audited; the store's last canonical row wins.
4. The series are joined on **exact UTC candle-open timestamp** only.
5. There is no resampling, forward fill, interpolation, or calendar synthesis.
6. Basis is measured as
   `(PAXGUSDT close - XAUUSD close) / XAUUSD close`.
7. The report includes USD, percent, and basis-point distributions, robust
   median/MAD statistics, exact-overlap coverage, correlations, tracking error,
   and a SHA-256 fingerprint of the aligned observations.

`PAXGUSDT` is quoted in USDT while `XAUUSD` is quoted in USD, so the observed
spread also contains any USDT/USD quote-currency basis. Dukascopy CSV candles
are one-sided (`bid` or `ask`); mixed price sides fail closed because their
provenance is ambiguous. One-sided evidence remains research evidence.

## Promotion gates

The dossier reports these independently:

| Requirement | How it is established | Does this command approve it? |
|---|---|---|
| PAXG-vs-XAU basis measured | Minimum exact-time overlap is present | Measurement only |
| Sealed OOS clears unchanged bar | Latest envelope matches the requested seal key, XAU symbol/timeframe, its root/payload fingerprint, and the exact current criteria; train, validation, sealed OOS, recent, and the combined verdict all pass | Inspection only |
| Explicit human approval | A human reviews basis magnitude, provenance, seal history, and operational suitability | **Never** |

Even when the first two requirements pass, output remains:

- `status = RESEARCH_ONLY`
- `human_approval = OPEN`
- `xau_tradeable = false`
- `micro_live_unlocked = false`

There is deliberately no `--approve`, `--promote`, or order-placement option.
Micro-live still requires the repository-wide graduation bar to be open and an
explicit user instruction after review; `xau-evidence` satisfies neither by
itself.
