## P12.6 — Fees-First `E_net` & Conditioned Expectancy

### Summary
This milestone implements **P12.6** (fees-first net expectancy & conditioned scorecard) on top of the real market data shipped in P12.3.2 (PR #22).

Costs are now fully integrated into every performance measurement across the desk:
$$E_{\text{net}} = E_{\text{gross}} − \text{fees} − \text{slip} − \text{funding}$$
where every component is expressed in **R units per trade** scaled to the planned 1R stop distance ($|entry - sl| / entry$).

### Core Mathematical Rationale (`docs/PATH_TO_REAL_MONEY.md` §2)
1. **Fees + spread lead the cost calculation**: At measured BTC median stop distance (0.823% of entry), a standard taker round-trip fee (0.05%/side = 0.10% total) costs **0.1215R** per trade (~35% of gross expectancy).
2. **Fees ≫ funding at short horizons**: At the measured 1.8h median hold, funding is ~0.0027R; **fees are ~45× funding**.
3. **Funding as-of-T**: Direction-aware funding rate is joined from stored derivatives series (`data/derivatives.py`) as of signal timestamp $T$ (long pays positive funding, short receives funding credit; spot has 0 funding).
4. **Net Graduation Bar**: The bar ($E \ge +0.50\text{R}, WR > 55\%, PF \ge 1.5$) is restated and enforced **NET of costs** on all surfaces.

### What Changed
- **`data/costs.py`** (new): `CostModel`, `calculate_trade_cost()`, and `get_funding_rate_as_of_t()`.
- **`data/backtester.py`**: `GradedPlan` and `_evaluate()` attach `rr_net`, `fee_r`, `slip_r`, `funding_r`, `cost_r`. `_aggregate()` calculates gross and net metrics.
- **`data/database.py`**: Additive migrations add `rr_net`, `fee_r`, `slip_r`, `funding_r`, `cost_r` to `backtest_results` and `paper_trades`.
- **`data/scorecard.py`**: `trade_stats()` and `build_scorecard()` compute gross and net metrics (`expectancy_net`, `win_rate_net`, `pf_net`, `total_r_net`, `max_drawdown_r_net`, `sharpe_net`, `sortino_net`, `calmar_net`, `cost_r`, `fee_r`, `slip_r`, `funding_r`), and conditioned splits by funding regime and CVD order flow (`--conditioned`).
- **`data/validation.py` & `data/simulator.py`**: `meets_bar()` and `graduation_status()` evaluate against the net bar.
- **Surfaces**: CLI `python main.py scorecard [--no-costs] [--maker] [--conditioned] [--json]`, HTTP `GET /api/scorecard`, MCP `scorecard` tool (v1.6.0), dashboard learning card.
- **Tests**: `tests/test_costs.py` (12 tests) + scorecard net & conditioned tests (3 tests). Suite **552 → 567 passed / 1 skipped** (+15). Version **2.12.0 → 2.13.0**.

### Measured on Real BTCUSDT 15m Data
- Headline: expectancy **+0.001R gross → −0.369R net** (cost drag −0.370R: fee 0.262R, slip 0.105R, funding 0.004R).
- `Sell Pullback` (+0.974R net, PF 3.99 net) and `FVG Retest Sell` (+1.161R net, PF 6.43 net) survive net.
- `Breakout Buy` (−0.904R net, PF 0.225 net) confirmed as heavy drag.

### Next on the Ladder
**P12.3.3 — Effective sample size in the scorecard** (divide walk-forward trade counts by window overlap factor ~30× to report honest independent sample sizes and widen confidence intervals).
