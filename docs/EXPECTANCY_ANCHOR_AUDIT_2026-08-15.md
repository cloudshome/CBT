# Expectancy anchor audit — 2026-08-15

## Scope

Post-P12.8 sweep of every executable comparison between expectancy and zero
or a graduation threshold. The question was not whether a report *shows*
gross expectancy, but whether any decision can act on gross when net-of-costs
expectancy is available.

The sweep used repository-wide text search plus a Python AST pass over every
non-test Python comparison containing `expectancy`/`expect`.

## Decision inventory

| Decision site | Threshold | Authoritative value | Result |
|---|---:|---|---|
| `brain.calibrator.build_profile` filter | `CALIBRATE_FILTER_THRESHOLD` | `expectancy_net`, gross only if net is absent | correct |
| `brain.calibrator.build_profile` proven flag | `> 0` | same net-first anchor | correct |
| `data.strategy_score.multiplier_from_score` confidence direction | sign around zero | `expectancy_net`, gross only if net is absent | correct |
| `brain.risk_gate.setup_proven` trade permission | backtest and paper `> 0` | each book's net expectancy, gross only if net is absent | correct |
| `data.simulator.paper_progress` proven flag | `> 0` | combined net expectancy | correct |
| `data.simulator.grind_verdict` micro-live sample proof | `> 0` | combined net expectancy, recomputed from evidence | **fixed in this audit** |
| `data.simulator.graduation_status` graduation bar | `>= +0.50R` | combined net expectancy | correct |
| `data.validation.meets_bar` validation bar | configured bar | net metrics where present | correct |
| `data.quality_score.plateau_score` robust-neighbour count | `> 0` | `expectancy_net` | correct |

## Findings fixed

1. `grind_verdict()` rejected on the net-derived `proven` flag but explained
   the failure by comparing **gross** expectancy to zero. A cost-flipped setup
   could therefore report `all targets met` while keeping micro-live closed.
   The function now recomputes proof from sample counts and `E_net`, so a stale
   caller-supplied `proven=True` cannot override the net book.
2. `paper_progress()` used truthiness fallback (`net or gross`) in several
   aggregates. Exact zero is a valid net result, not missing data; replacing it
   with a positive gross value could flip the proof's sign. Fallback is now
   strictly `None`-only for expectancy, net wins, and net win/loss R.
3. The simulator progress table displayed gross expectancy beside a
   net-derived `PROVEN` marker. It now labels and displays `E_NET`.

## Non-decisions

Dashboard colour/sign formatting, documentation strings, query examples, and
coach/library narrative are reporting or retrieval surfaces; they do not open
the risk gate, boost calibration, or graduate the desk. Gross remains visible
there only when explicitly labelled or shown beside net.

## Regression proof

- A gross-positive/net-negative row with a stale `proven=True` remains blocked
  and reports `positive net expectancy` as missing.
- An exact `E_net = 0.0` / `wins_net = 0` row remains zero and unproven rather
  than falling back to its positive gross values.
- Full suite: **633 passed, 1 skipped**.

## Operational rerun status

The requested real-store recalibration could not be performed in this checkout:
`data/store/**` and `data/cryptobrain.db` are gitignored runtime data, and neither
is present. `python main.py store --market spot --symbol BTCUSDT --tf 15m --json`
reports no candles. On the host holding those artifacts, run:

```bash
python main.py backtest --source store --market spot --symbol BTCUSDT \
  --tf 15m --bars 12000 --step 3 --save
python main.py learn
python main.py scorecard --source db --symbol BTCUSDT --quality
```

Do not treat a fresh demo/live 500-bar fetch as a substitute for the real store.
