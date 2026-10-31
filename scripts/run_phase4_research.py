"""
scripts/run_phase4_research.py
==============================
Phase 4 Automated Research Runner:
- Evaluates BTCUSDT and ETHUSDT 1h across full historical periods (2022-2026)
- Implements strict event deduplication (single active trade per strategy)
- Splits into In-Sample (2022-2024) and Chronological Out-of-Sample (2025-2026)
- Tests alternative explanations (removing top 5% winners, fee sensitivity)
- Persists full JSON research artifact to data_samples/phase4_research_experiment.json
"""

import json
import time
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd
import numpy as np

from data.store import CandleStore
from data.backtester import run_backtest


def evaluate_dataset_slice(df_slice, symbol, timeframe, horizon_hours=24.0, fee_multiplier=1.0):
    res = run_backtest(df_slice, symbol=symbol, timeframe=timeframe, horizons=[horizon_hours], min_confidence=55)
    graded = res["graded"]
    
    strategies = [
        "Buy Pullback", "Sell Pullback",
        "FVG Retest Buy", "FVG Retest Sell",
        "Breakout Buy", "Sweep Reversal Buy"
    ]
    
    strat_metrics = {}
    for ptype in strategies:
        plans = [g for g in graded if g.plan_type == ptype and g.horizon_hours == horizon_hours]
        exec_plans = [g for g in plans if g.outcome in ("FULL_WIN", "PARTIAL_WIN", "LOSS")]
        
        if not exec_plans:
            strat_metrics[ptype] = {
                "total_plans": len(plans),
                "executed_plans": 0,
                "dedup_trades": 0,
                "win_rate": None,
                "net_expectancy": 0.0,
                "gross_expectancy": 0.0,
                "profit_factor": None
            }
            continue
            
        exec_plans.sort(key=lambda g: g.ts)
        
        # Deduplication: single active position at a time
        non_ov = []
        cur_exit = -1
        for g in exec_plans:
            hold_ms = int((g.holding_hours or 24.0) * 3600 * 1000)
            if g.ts >= cur_exit:
                non_ov.append(g)
                cur_exit = g.ts + hold_ms
                
        wins = [g for g in non_ov if g.outcome in ("FULL_WIN", "PARTIAL_WIN")]
        losses = [g for g in non_ov if g.outcome == "LOSS"]
        wr = len(wins) / len(non_ov) if non_ov else None
        
        # Calculate R values with fee multiplier
        gross_rs = [g.rr_achieved for g in non_ov]
        net_rs = []
        for g in non_ov:
            cost = getattr(g, "cost_r", 0.0) * fee_multiplier
            net_rs.append(g.rr_achieved - cost)
            
        gross_exp = sum(gross_rs) / len(gross_rs) if gross_rs else 0.0
        net_exp = sum(net_rs) / len(net_rs) if net_rs else 0.0
        
        gross_wins = sum(r for r in gross_rs if r > 0)
        gross_losses = abs(sum(r for r in gross_rs if r < 0))
        pf = round(gross_wins / gross_losses, 2) if gross_losses > 0 else (99.0 if gross_wins > 0 else 0.0)
        
        # Remove top 5% winning outliers for robustness check
        if len(net_rs) >= 20:
            k = max(1, int(len(net_rs) * 0.05))
            net_rs_sorted = sorted(net_rs)
            net_rs_trimmed = net_rs_sorted[:-k]
            net_exp_trimmed = sum(net_rs_trimmed) / len(net_rs_trimmed)
        else:
            net_exp_trimmed = net_exp
            
        strat_metrics[ptype] = {
            "total_plans": len(plans),
            "executed_plans": len(exec_plans),
            "dedup_trades": len(non_ov),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(wr, 3) if wr is not None else None,
            "gross_expectancy": round(gross_exp, 3),
            "net_expectancy": round(net_exp, 3),
            "trimmed_net_expectancy": round(net_exp_trimmed, 3),
            "profit_factor": pf,
            "overlap_ratio": round(len(exec_plans) / max(1, len(non_ov)), 2)
        }
        
    return strat_metrics


def run():
    print("Starting Comprehensive Phase 4 Multi-Year Quantitative Evaluation...")
    store = CandleStore()
    
    # 1. BTCUSDT Evaluation
    df_btc = store.read("binance", "perp", "BTCUSDT", "1h")
    df_btc["dt"] = pd.to_datetime(df_btc["ts"], unit="ms", utc=True)
    
    # In-Sample: 2022-01-01 to 2024-12-31 (3 years)
    btc_is = df_btc[df_btc["dt"].dt.year <= 2024].reset_index(drop=True)
    # Out-of-Sample: 2025-01-01 to 2026-10-14 (~1.8 years)
    btc_oos = df_btc[df_btc["dt"].dt.year >= 2025].reset_index(drop=True)
    
    print(f"BTC In-Sample: {len(btc_is)} bars (2022-2024)")
    print(f"BTC Out-of-Sample: {len(btc_oos)} bars (2025-2026)")
    
    btc_is_results = evaluate_dataset_slice(btc_is, "BTCUSDT", "1h")
    btc_oos_results = evaluate_dataset_slice(btc_oos, "BTCUSDT", "1h")
    btc_stress_cost_results = evaluate_dataset_slice(btc_oos, "BTCUSDT", "1h", fee_multiplier=1.5)
    
    # 2. ETHUSDT Replication
    df_eth = store.read("binance", "perp", "ETHUSDT", "1h")
    df_eth["dt"] = pd.to_datetime(df_eth["ts"], unit="ms", utc=True)
    eth_is = df_eth[df_eth["dt"].dt.year <= 2024].reset_index(drop=True)
    eth_oos = df_eth[df_eth["dt"].dt.year >= 2025].reset_index(drop=True)
    
    print(f"ETH In-Sample: {len(eth_is)} bars")
    print(f"ETH Out-of-Sample: {len(eth_oos)} bars")
    
    eth_is_results = evaluate_dataset_slice(eth_is, "ETHUSDT", "1h")
    eth_oos_results = evaluate_dataset_slice(eth_oos, "ETHUSDT", "1h")
    
    experiment_data = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": "d0bb163eacff8e0c181577a52cb6e17727816cc0",
        "evaluation_protocol": {
            "timeframe": "1h",
            "horizon_hours": 24.0,
            "deduplication": "Single non-overlapping trade at a time per strategy family",
            "costs": "Base: 5 bps taker + 3 bps slip = 8 bps per side; Stress: 12 bps per side; 0.01% / 8h funding",
            "in_sample_span": "2022-01-01 to 2024-12-31 (26,304 bars)",
            "out_of_sample_span": "2025-01-01 to 2026-10-14 (15,636 bars)"
        },
        "btc_in_sample": btc_is_results,
        "btc_out_of_sample": btc_oos_results,
        "btc_oos_stress_costs": btc_stress_cost_results,
        "eth_in_sample": eth_is_results,
        "eth_out_of_sample": eth_oos_results
    }
    
    out_path = Path("data_samples/phase4_research_experiment.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(experiment_data, indent=2))
    print(f"Successfully saved experiment results to {out_path.as_posix()}")


if __name__ == "__main__":
    run()

