"""scripts/research/run_m77_portfolio_vol_targeting_audit.py — Milestone 77 Causal Portfolio-Level Vol-Targeting Audit.

Audits whether applying a strictly causal, zero-leverage portfolio-level 15% volatility target
to pre-registered ensemble candidates V2C and V2B enables either to clear all 5/5 identical
Milestone 76 Upgrade Promotion Gates against P2_RP_BASELINE:

Candidates evaluated:
1. P2_RP_BASELINE: 50% S1 + 50% S2-Div (Current Production Architecture)
2. Trial #28: P2_RP_V2C_PVT (25% S1 + 25% S2-Div + 25% H5 + 25% H1_CLEAN + Causal Portfolio Vol Target)
3. Trial #29: P2_RP_V2B_PVT (33.33% S1 + 33.33% H5 + 33.33% H1_CLEAN + Causal Portfolio Vol Target)
4. Equal-Weight Buy-and-Hold Benchmark

Outputs:
- research/m77_portfolio_vol_targeting_results.json
- docs/research/M77_PORTFOLIO_VOL_TARGETING_AUDIT.md
- Appends Trials #28, #29 to research/discovery_trial_ledger.json (M_cum: 27 -> 29)
"""

from __future__ import annotations

import json
import logging
import math
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.quantitative_validation.metrics import calculate_deflated_sharpe_ratio
from core.research.discovery_lab import (
    CausalDiscoveryEngine,
    H1_CleanVolSqueezeExpansionLong,
    H5_DualHorizonRotationGold,
    NumpyJSONEncoder,
    TrialLedgerManager,
    compute_stress_resistance_verdict,
    load_discovery_data,
)
from scripts.research.run_m65_risk_parity_and_stress_test import (
    calculate_continuous_mtm_metrics,
    compute_s1_indicators,
    run_cpcv_analysis,
    run_m65_single_regime_simulation,
)
from scripts.research.run_m76_ensemble_upgrade_audit import evaluate_5_upgrade_gates

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("m77_vol_targeting_audit_runner")

# Governance Invariants
REAL_CAPITAL_ENABLED: bool = False
CAPITAL_MODE: str = "TIER_0_PAPER"


def apply_portfolio_vol_targeting(
    raw_rets: np.ndarray,
    raw_gross: np.ndarray,
    target_vol: float = 0.15,
    window: int = 20,
    warmup: int = 120,
    deadband: float = 0.03,
    max_concentration: float = 1.50,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Applies strictly causal, zero-leverage portfolio-level 15% volatility targeting.

    Rules:
    1. Zero Lookahead: At bar close t-1, computes trailing 20-day annualized realized vol
       using returns strictly up to t-1: port_vol_20d[t-1] (warmup fallback 0.15 for first 120 bars).
    2. Bear Shield Preservation: If raw_gross[t-1] <= 1e-6, target_scalar = 0.0 (100% Cash).
    3. Zero Leverage & Concentration Caps:
       vol_scalar = target_vol / max(port_vol, 0.04)
       max_no_lev = 1.0 / raw_gross[t-1]
       target_scalar = min(vol_scalar, max_no_lev, max_concentration)
    4. 3% Notional Drift Deadband: Keeps last_scalar unless deviation > 3% or transition to/from zero.
    5. Invariant Zero-Leverage Clamp: At execution bar t, clamps effective_scalar <= 1.0 / raw_gross[t]
       so that scaled_gross[t] strictly never exceeds 1.0000.
    """
    n = len(raw_rets)
    scaled_rets = np.zeros(n)
    scaled_gross = np.zeros(n)
    scalars = np.zeros(n)

    last_scalar = 1.0
    for t in range(n):
        if t == 0:
            rg_0 = raw_gross[0]
            if rg_0 > 1e-6:
                eff_scalar = min(1.0, 1.0 / rg_0, max_concentration)
            else:
                eff_scalar = 0.0
            last_scalar = eff_scalar
            scalars[0] = eff_scalar
            scaled_gross[0] = rg_0 * eff_scalar
            scaled_rets[0] = raw_rets[0] * eff_scalar
            continue

        prev_idx = t - 1
        if prev_idx < warmup:
            port_vol = target_vol
        else:
            w_start = max(0, prev_idx - window + 1)
            w_rets = raw_rets[w_start : prev_idx + 1]
            port_vol = float(np.std(w_rets, ddof=1) * math.sqrt(365.0))
            if np.isnan(port_vol) or port_vol < 1e-6:
                port_vol = target_vol

        rg_prev = raw_gross[prev_idx]
        if rg_prev <= 1e-6:
            target_scalar = 0.0
        else:
            vol_scalar = target_vol / max(port_vol, 0.04)
            max_no_lev = 1.0 / rg_prev
            target_scalar = min(vol_scalar, max_no_lev, max_concentration)

        # 3% notional drift deadband
        if abs(target_scalar - last_scalar) > deadband or target_scalar == 0.0 or last_scalar == 0.0:
            eff_scalar = target_scalar
        else:
            eff_scalar = last_scalar

        # Invariant zero-leverage clamp at bar t
        rg_curr = raw_gross[t]
        if rg_curr > 1e-6:
            eff_scalar = min(eff_scalar, 1.0 / rg_curr, max_concentration)
        else:
            eff_scalar = 0.0

        last_scalar = eff_scalar
        scalars[t] = eff_scalar
        scaled_gross[t] = min(rg_curr * eff_scalar, 1.0)
        scaled_rets[t] = raw_rets[t] * eff_scalar

    return scaled_rets, scaled_gross, scalars


def format_markdown_report(results: dict[str, Any], report_path: Path) -> str:
    """Generates the comprehensive Milestone 77 Markdown audit dossier."""
    rep = []
    rep.append("# MILESTONE 77 RESEARCH DOSSIER: PORTFOLIO-LEVEL 15% VOL-TARGETING AUDIT")
    rep.append("## HEAD-TO-HEAD: P2_RP_BASELINE vs P2_RP_V2C_PVT vs P2_RP_V2B_PVT")
    rep.append(f"**Evaluation Timestamp UTC:** `{results['evaluation_timestamp_utc']}`  ")
    rep.append(f"**Runtime:** `{results['total_runtime_seconds']:.2f} seconds` | **Trial Span:** `$M_{{\\text{{cum}}}} = 27 \\to 29$`  ")
    rep.append(f"**Ledger Path:** [`research/discovery_trial_ledger.json`](file:///{ROOT_DIR.as_posix()}/research/discovery_trial_ledger.json)  \n")
    rep.append("---\n")

    rep.append("## 1. EXECUTIVE SUMMARY & AUDIT OBJECTIVE\n")
    rep.append("Milestone 77 executes a strictly causal, zero-leverage portfolio-level 15% volatility targeting audit on the top two candidate ensembles from Milestone 76 (`P2_RP_V2C_4SLEEVE` and `P2_RP_V2B_S1_H5_H1`). In M76, both ensembles passed 4/5 Upgrade Promotion Gates but narrowly missed Gate 1 Calmar due to `H1_CLEAN` remaining in cash during quiet regimes, which capped peak gross exposure at ~0.83x.\n")
    rep.append("This milestone tests whether dynamically sizing the ensemble's aggregate gross exposure to a 15% volatility target (subject to strict zero-leverage `<= 1.0000`, 1.50x concentration cap, and 3% deadband) enables either candidate to pass all 5/5 Upgrade Promotion Gates.\n")

    rep.append("### Evaluated Architectures:")
    rep.append("1. **`P2_RP_BASELINE`:** `50% S1 + 50% S2-Div` (Current Production Architecture).")
    rep.append("2. **`P2_RP_V2C_PVT` (Trial #28):** `25% S1 + 25% S2-Div + 25% H5 + 25% H1_CLEAN` + Causal Portfolio-Level 15% Vol Target.")
    rep.append("3. **`P2_RP_V2B_PVT` (Trial #29):** `33.33% S1 + 33.33% H5 + 33.33% H1_CLEAN` + Causal Portfolio-Level 15% Vol Target.")
    rep.append("4. **`Equal-Weight BnH`:** Benchmark (25% BTC + 25% ETH + 25% SOL + 25% PAXG).\n")
    rep.append("---\n")

    # Head-to-Head Scorecard
    rep.append("## 2. HEAD-TO-HEAD SCORECARD: BASELINE vs VOL-TARGETED ENSEMBLES\n")
    rep.append("| Metric | P2_RP_BASELINE | P2_RP_V2C_PVT (Trial #28) | P2_RP_V2B_PVT (Trial #29) | Equal-Weight BnH |")
    rep.append("|:---|:---:|:---:|:---:|:---:|")

    base = results["portfolios"]["P2_RP_BASELINE"]
    v2c = results["portfolios"]["P2_RP_V2C_PVT"]
    v2b = results["portfolios"]["P2_RP_V2B_PVT"]
    bnh = results["benchmark_bnh"]

    rep.append("| **Trial Number ($M_{\\text{cum}}$)** | Baseline ($M=14$) | #28 | #29 | — |")
    rep.append(f"| **Full-Period Return %** | {base['full_period']['total_return_pct']:+.1f}% | {v2c['full_period']['total_return_pct']:+.1f}% | **{v2b['full_period']['total_return_pct']:+.1f}%** | {bnh['full_period']['total_return_pct']:+.1f}% |")
    rep.append(f"| **Full-Period CAGR %** | {base['full_period']['cagr_pct']:.2f}% | {v2c['full_period']['cagr_pct']:.2f}% | **{v2b['full_period']['cagr_pct']:.2f}%** | {bnh['full_period']['cagr_pct']:.2f}% |")
    rep.append(f"| **Full-Period Sharpe** | {base['full_period']['daily_mtm_sharpe']:.2f} | {v2c['full_period']['daily_mtm_sharpe']:.2f} | **{v2b['full_period']['daily_mtm_sharpe']:.2f}** | {bnh['full_period']['daily_mtm_sharpe']:.2f} |")
    rep.append(f"| **Full-Period Calmar** | {base['full_period']['calmar_ratio']:.2f} | {v2c['full_period']['calmar_ratio']:.2f} | **{v2b['full_period']['calmar_ratio']:.2f}** | {bnh['full_period']['calmar_ratio']:.2f} |")
    rep.append(f"| **Full-Period Max DD %** | {base['full_period']['max_drawdown_pct']:.2f}% | {v2c['full_period']['max_drawdown_pct']:.2f}% | **{v2b['full_period']['max_drawdown_pct']:.2f}%** | {bnh['full_period']['max_drawdown_pct']:.2f}% |")
    rep.append(f"| **Full-Period Realized Vol %** | {base['full_period']['annualized_vol_pct']:.2f}% | {v2c['full_period']['annualized_vol_pct']:.2f}% | {v2b['full_period']['annualized_vol_pct']:.2f}% | {bnh['full_period']['annualized_vol_pct']:.2f}% |")
    rep.append(f"| **Peak Gross Exposure** | **{base['max_gross_exposure']:.4f}** | **{v2c['max_gross_exposure']:.4f}** | **{v2b['max_gross_exposure']:.4f}** | 1.0000 |")
    rep.append(f"| **Mean Gross Exposure** | {base.get('mean_gross_exposure', 0.50):.4f} | {v2c.get('mean_gross_exposure', 0.0):.4f} | {v2b.get('mean_gross_exposure', 0.0):.4f} | 1.0000 |")
    rep.append(f"| **Sealed OOS Return %** | {base['sealed_oos']['total_return_pct']:+.2f}% | {v2c['sealed_oos']['total_return_pct']:+.2f}% | **{v2b['sealed_oos']['total_return_pct']:+.2f}%** | {bnh['sealed_oos']['total_return_pct']:+.2f}% |")
    rep.append(f"| **Sealed OOS Sharpe** | {base['sealed_oos']['daily_mtm_sharpe']:.2f} | {v2c['sealed_oos']['daily_mtm_sharpe']:.2f} | **{v2b['sealed_oos']['daily_mtm_sharpe']:.2f}** | {bnh['sealed_oos']['daily_mtm_sharpe']:.2f} |")
    rep.append(f"| **Sealed OOS Max DD %** | {base['sealed_oos']['max_drawdown_pct']:.2f}% | {v2c['sealed_oos']['max_drawdown_pct']:.2f}% | **{v2b['sealed_oos']['max_drawdown_pct']:.2f}%** | {bnh['sealed_oos']['max_drawdown_pct']:.2f}% |")
    rep.append(f"| **CPCV Median Sharpe** | {base['cpcv_median_sharpe']:.2f} | {v2c['cpcv_median_sharpe']:.2f} | **{v2b['cpcv_median_sharpe']:.2f}** | — |")
    rep.append(f"| **Cumulative DSR** | — | {v2c['dsr_oos']:.4f} (p={v2c['pval_oos']:.4f}) | **{v2b['dsr_oos']:.4f}** (p={v2b['pval_oos']:.4f}) | — |")
    rep.append(f"| **5 Upgrade Gates** | Baseline | **{v2c['upgrade_evaluation']['summary_text']}** | **{v2b['upgrade_evaluation']['summary_text']}** | — |")
    rep.append(f"| **Audit Promotion Verdict**| **CURRENT PROD** | **`{v2c['upgrade_evaluation']['verdict']}`** | **`{v2b['upgrade_evaluation']['verdict']}`** | — |")
    rep.append("\n---\n")

    # 3-Regime Stress Matrix
    rep.append("## 3. 3-REGIME INSTITUTIONAL STRESS MATRIX COMPARISON\n")
    rep.append("| Portfolio | Regime 1: Baseline (20 bps, t+1) | Regime 2: 2x Friction (40 bps, t+1) | Regime 3: 1-Bar Delay (20 bps, t+2) | Stress Resistance Verdict |")
    rep.append("|:---|:---:|:---:|:---:|:---:|")

    for pid in ["P2_RP_BASELINE", "P2_RP_V2C_PVT", "P2_RP_V2B_PVT"]:
        p_res = results["portfolios"][pid]
        sm = p_res["stress_matrix"]
        sh_base = sm["regime_1_baseline"]["sealed_oos"]["daily_mtm_sharpe"]
        ret_base = sm["regime_1_baseline"]["sealed_oos"]["total_return_pct"]
        sh_fric = sm["regime_2_friction_stress"]["sealed_oos"]["daily_mtm_sharpe"]
        ret_fric = sm["regime_2_friction_stress"]["sealed_oos"]["total_return_pct"]
        sh_delay = sm["regime_3_delay_stress"]["sealed_oos"]["daily_mtm_sharpe"]
        ret_delay = sm["regime_3_delay_stress"]["sealed_oos"]["total_return_pct"]
        s_verd = p_res["stress_resistance_verdict"]

        rep.append(
            f"| **{pid}** | Ret: {ret_base:+.2f}%, Sh: {sh_base:.2f} | Ret: {ret_fric:+.2f}%, Sh: {sh_fric:.2f} | Ret: {ret_delay:+.2f}%, Sh: {sh_delay:.2f} | **`{s_verd}`** |"
        )
    rep.append("\n---\n")

    # Year-by-Year Comparison
    rep.append("## 4. YEAR-BY-YEAR PERFORMANCE COMPARISON (2022–2026)\n")
    rep.append("| Year | P2_RP_BASELINE | P2_RP_V2C_PVT (Trial #28) | P2_RP_V2B_PVT (Trial #29) | Equal-Weight BnH |")
    rep.append("|:---|:---:|:---:|:---:|:---:|")
    years = [2022, 2023, 2024, 2025, 2026]
    for yr in years:
        b_yr = base["yearly"].get(yr, {})
        v2c_yr = v2c["yearly"].get(yr, {})
        v2b_yr = v2b["yearly"].get(yr, {})
        bnh_yr = bnh["yearly"].get(yr, {})

        b_ret = b_yr.get("total_return_pct", 0.0)
        v2c_ret = v2c_yr.get("total_return_pct", 0.0)
        v2b_ret = v2b_yr.get("total_return_pct", 0.0)
        bnh_ret = bnh_yr.get("total_return_pct", 0.0)

        rep.append(
            f"| **{yr}** | {b_ret:+.2f}% (DD: {b_yr.get('max_drawdown_pct', 0.0):.1f}%) | "
            f"{v2c_ret:+.2f}% (DD: {v2c_yr.get('max_drawdown_pct', 0.0):.1f}%) | "
            f"{v2b_ret:+.2f}% (DD: {v2b_yr.get('max_drawdown_pct', 0.0):.1f}%) | "
            f"{bnh_ret:+.2f}% (DD: {bnh_yr.get('max_drawdown_pct', 0.0):.1f}%) |"
        )
    rep.append("\n---\n")

    # Detailed 5-Gate Promotion Evaluation
    rep.append("## 5. DETAILED 5-GATE PROMOTION EVALUATION BY CANDIDATE\n")
    for pid in ["P2_RP_V2C_PVT", "P2_RP_V2B_PVT"]:
        p_res = results["portfolios"][pid]
        ue = p_res["upgrade_evaluation"]
        rep.append(f"### {pid}: **{ue['summary_text']}** -> **`{ue['verdict']}`**")
        rep.append("| Gate | Requirement | Observed Details | Status |")
        rep.append("|:---|:---|:---|:---:|")
        for _g_id, g_data in ue["gates"].items():
            rep.append(f"| **{g_data['name']}** | {g_data['requirement']} | {g_data['observed']} | **{'PASS' if g_data['passed'] else 'FAIL'}** |")
        rep.append(f"**Gate Verdict Rationale:** {ue['verdict_rationale']}\n")

    rep.append("---\n")

    # Volatility Targeting Exposure Analysis
    rep.append("## 6. PORTFOLIO VOLATILITY TARGETING TELEMETRY & MECHANICS\n")
    rep.append("| Metric | P2_RP_BASELINE | P2_RP_V2C_PVT | P2_RP_V2B_PVT |")
    rep.append("|:---|:---:|:---:|:---:|")
    rep.append(f"| **Unscaled Mean Gross Exposure** | {base.get('mean_gross_exposure', 0.50):.4f} | {v2c.get('unscaled_mean_gross', 0.2258):.4f} | {v2b.get('unscaled_mean_gross', 0.1897):.4f} |")
    rep.append(f"| **Scaled Mean Gross Exposure** | {base.get('mean_gross_exposure', 0.50):.4f} | {v2c.get('mean_gross_exposure', 0.0):.4f} | {v2b.get('mean_gross_exposure', 0.0):.4f} |")
    rep.append(f"| **Peak Gross Exposure (Max <= 1.0000)** | {base['max_gross_exposure']:.4f} | {v2c['max_gross_exposure']:.4f} | {v2b['max_gross_exposure']:.4f} |")
    rep.append(f"| **Average Volatility Scalar** | 1.0000 | {v2c.get('mean_scalar', 1.0):.4f} | {v2b.get('mean_scalar', 1.0):.4f} |")
    rep.append(f"| **Zero-Gross Bear Shield Bars (scalar=0.0)** | {base.get('zero_gross_bars', 0)} | {v2c.get('zero_gross_bars', 0)} | {v2b.get('zero_gross_bars', 0)} |")
    rep.append("\n---\n")

    # Governance & Architectural Verdict
    rep.append("## 7. GOVERNANCE & ARCHITECTURAL VERDICT\n")
    rep.append("- `REAL_CAPITAL_ENABLED = False` (Permanently locked).")
    rep.append("- `CAPITAL_MODE = \"TIER_0_PAPER\"` (All discovery execution is simulated/paper).")
    rep.append("- `core/strategies/p2_risk_parity.py` and `core/strategies/p2_shadow_runner.py` remain untouched.")
    rep.append("- Zero parameter tuning, zero grid searches, zero moving goalposts.")
    rep.append("- All candidates strictly preserved zero-leverage invariants (`gross_exposure <= 1.0001`).")
    rep.append("- Append-only trial ledger persisted at `research/discovery_trial_ledger.json` (advancing $M_{\\text{cum}} = 27 \\to 29$).")

    content = "\n".join(rep)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(content, encoding="utf-8")
    logger.info(f"Report written to {report_path}")
    return content


def run_m77_vol_targeting_audit() -> dict[str, Any]:
    """Executes the full Milestone 77 Causal Portfolio Vol-Targeting Audit."""
    logger.info("=== STARTING MILESTONE 77: CAUSAL PORTFOLIO VOL-TARGETING AUDIT ===")
    start_time = time.time()

    data = load_discovery_data(ROOT_DIR)
    sorted_ts = data["sorted_ts"]
    s1_ind = {s: compute_s1_indicators(data["dfs_aligned"][s]) for s in data["all_symbols"]}
    engine = CausalDiscoveryEngine(data_bundle=data)

    regimes = [
        {"id": "regime_1_baseline", "friction_bps": 20.0, "delay": 1, "desc": "Baseline Causal (20 bps, t+1)"},
        {"id": "regime_2_friction_stress", "friction_bps": 40.0, "delay": 1, "desc": "2x Friction Stress (40 bps, t+1)"},
        {"id": "regime_3_delay_stress", "friction_bps": 20.0, "delay": 2, "desc": "1-Bar Delay Stress (20 bps, t+2)"},
    ]

    regime_portfolios: dict[str, dict[str, Any]] = {}
    pvt_diagnostics: dict[str, dict[str, Any]] = {}

    for reg in regimes:
        reg_id = reg["id"]
        f_bps = reg["friction_bps"]
        del_bars = reg["delay"]
        logger.info(f"Simulating {reg['desc']}...")

        # 1. Simulate M65 baseline sleeves (S1, S2-Div, P2_RP baseline)
        m65_res = run_m65_single_regime_simulation(
            data["dfs_aligned"],
            sorted_ts,
            s1_ind,
            friction_bps=f_bps,
            exec_delay_bars=del_bars,
            target_vol=0.15,
        )
        df_m65 = m65_res["df_daily"]

        # 2. Simulate H1_CLEAN
        h1_res = engine.run_single_regime_simulation(
            H1_CleanVolSqueezeExpansionLong(),
            friction_bps=f_bps,
            exec_delay_bars=del_bars,
        )
        df_h1 = h1_res["df_daily"]

        # 3. Simulate H5
        h5_res = engine.run_single_regime_simulation(
            H5_DualHorizonRotationGold(),
            friction_bps=f_bps,
            exec_delay_bars=del_bars,
        )
        df_h5 = h5_res["df_daily"]

        # Align on common calendar dates
        common_idx = df_m65.index.intersection(df_h1.index).intersection(df_h5.index)
        df_m65_a = df_m65.loc[common_idx]
        df_h1_a = df_h1.loc[common_idx]
        df_h5_a = df_h5.loc[common_idx]

        s1_ret = df_m65_a["s1_ret"].values
        s2_ret = df_m65_a["s2_ret"].values
        h1_ret = df_h1_a["daily_ret"].values
        h5_ret = df_h5_a["daily_ret"].values

        s1_exp = df_m65_a["s1_exp"].values
        s2_exp = df_m65_a["s2_exp"].values
        h1_exp = df_h1_a["gross_exposure"].values
        h5_exp = df_h5_a["gross_exposure"].values

        # Baseline P2_RP (50% S1 + 50% S2-Div)
        p_base_ret = 0.5 * s1_ret + 0.5 * s2_ret
        p_base_exp = 0.5 * s1_exp + 0.5 * s2_exp

        # Raw Unscaled Ensembles
        raw_v2c_ret = 0.25 * s1_ret + 0.25 * s2_ret + 0.25 * h5_ret + 0.25 * h1_ret
        raw_v2c_exp = 0.25 * s1_exp + 0.25 * s2_exp + 0.25 * h5_exp + 0.25 * h1_exp

        raw_v2b_ret = (1.0 / 3.0) * s1_ret + (1.0 / 3.0) * h5_ret + (1.0 / 3.0) * h1_ret
        raw_v2b_exp = (1.0 / 3.0) * s1_exp + (1.0 / 3.0) * h5_exp + (1.0 / 3.0) * h1_exp

        # Apply Causal Portfolio-Level 15% Volatility Target
        v2c_pvt_ret, v2c_pvt_exp, v2c_scalars = apply_portfolio_vol_targeting(
            raw_v2c_ret,
            raw_v2c_exp,
            target_vol=0.15,
            window=20,
            warmup=120,
            deadband=0.03,
            max_concentration=1.50,
        )
        v2b_pvt_ret, v2b_pvt_exp, v2b_scalars = apply_portfolio_vol_targeting(
            raw_v2b_ret,
            raw_v2b_exp,
            target_vol=0.15,
            window=20,
            warmup=120,
            deadband=0.03,
            max_concentration=1.50,
        )

        if reg_id == "regime_1_baseline":
            pvt_diagnostics["P2_RP_V2C_PVT"] = {
                "unscaled_mean_gross": float(np.mean(raw_v2c_exp)),
                "unscaled_max_gross": float(np.max(raw_v2c_exp)),
                "mean_gross_exposure": float(np.mean(v2c_pvt_exp)),
                "max_gross_exposure": float(np.max(v2c_pvt_exp)),
                "mean_scalar": float(np.mean(v2c_scalars)),
                "zero_gross_bars": int(np.sum(raw_v2c_exp <= 1e-6)),
            }
            pvt_diagnostics["P2_RP_V2B_PVT"] = {
                "unscaled_mean_gross": float(np.mean(raw_v2b_exp)),
                "unscaled_max_gross": float(np.max(raw_v2b_exp)),
                "mean_gross_exposure": float(np.mean(v2b_pvt_exp)),
                "max_gross_exposure": float(np.max(v2b_pvt_exp)),
                "mean_scalar": float(np.mean(v2b_scalars)),
                "zero_gross_bars": int(np.sum(raw_v2b_exp <= 1e-6)),
            }
            pvt_diagnostics["P2_RP_BASELINE"] = {
                "mean_gross_exposure": float(np.mean(p_base_exp)),
                "max_gross_exposure": float(np.max(p_base_exp)),
                "zero_gross_bars": int(np.sum(p_base_exp <= 1e-6)),
            }

        # Buy and Hold Benchmark
        bnh_ret = df_m65_a["bnh_ret"].values

        port_data = {
            "P2_RP_BASELINE": {"ret": p_base_ret, "exp": p_base_exp},
            "P2_RP_V2C_PVT": {"ret": v2c_pvt_ret, "exp": v2c_pvt_exp, "scalars": v2c_scalars},
            "P2_RP_V2B_PVT": {"ret": v2b_pvt_ret, "exp": v2b_pvt_exp, "scalars": v2b_scalars},
            "BNH": {"ret": bnh_ret, "exp": np.ones(len(bnh_ret))},
        }

        regime_portfolios[reg_id] = {
            "dates": common_idx,
            "portfolios": port_data,
        }

    # Evaluate Portfolios under Baseline Regime (Regime 1)
    dates = regime_portfolios["regime_1_baseline"]["dates"]
    n_days = len(dates)
    d_train_end = int(n_days * 0.50)
    d_val_end = int(n_days * 0.75)

    splits_idx = {
        "train": (0, d_train_end),
        "val": (d_train_end, d_val_end),
        "sealed_oos": (d_val_end, n_days),
        "combined_walk_forward": (d_train_end, n_days),
        "full_period": (0, n_days),
    }

    # Pre-calculate BNH metrics
    bnh_ret_base = regime_portfolios["regime_1_baseline"]["portfolios"]["BNH"]["ret"]
    bnh_eq = 10000.0 * np.cumprod(1.0 + bnh_ret_base)
    bnh_splits: dict[str, Any] = {}
    for sp_name, (sp_s, sp_e) in splits_idx.items():
        bnh_splits[sp_name] = calculate_continuous_mtm_metrics(
            bnh_ret_base[sp_s:sp_e],
            bnh_eq[sp_s:sp_e],
        )
    bnh_yearly: dict[int, Any] = {}
    for yr in [2022, 2023, 2024, 2025, 2026]:
        mask = (dates.year == yr)
        if np.sum(mask) > 5:
            bnh_yearly[yr] = calculate_continuous_mtm_metrics(
                bnh_ret_base[mask],
                bnh_eq[mask],
            )

    benchmark_bnh_summary = {
        **bnh_splits,
        "yearly": bnh_yearly,
    }

    # Evaluate Candidate and Baseline Portfolios
    portfolio_names = [
        "P2_RP_BASELINE",
        "P2_RP_V2C_PVT",
        "P2_RP_V2B_PVT",
    ]

    evaluated_portfolios: dict[str, Any] = {}

    for pid in portfolio_names:
        p_base_data = regime_portfolios["regime_1_baseline"]["portfolios"][pid]
        p_ret = p_base_data["ret"]
        p_exp = p_base_data["exp"]
        p_eq = 10000.0 * np.cumprod(1.0 + p_ret)

        p_splits: dict[str, Any] = {}
        for sp_name, (sp_s, sp_e) in splits_idx.items():
            p_splits[sp_name] = calculate_continuous_mtm_metrics(
                p_ret[sp_s:sp_e],
                p_eq[sp_s:sp_e],
            )

        p_yearly: dict[int, Any] = {}
        for yr in [2022, 2023, 2024, 2025, 2026]:
            mask = (dates.year == yr)
            if np.sum(mask) > 5:
                p_yearly[yr] = calculate_continuous_mtm_metrics(
                    p_ret[mask],
                    p_eq[mask],
                )

        # 15-fold CPCV on Full Period
        cpcv_res = run_cpcv_analysis(pd.Series(p_ret), n_partitions=6, k_test_groups=2)
        cpcv_median_sharpe = float(cpcv_res.get("median_oos_sharpe", cpcv_res.get("median_sharpe", 0.0)))

        # 3-Regime Stress Matrix
        stress_matrix: dict[str, Any] = {}
        for reg in regimes:
            reg_id = reg["id"]
            p_reg_data = regime_portfolios[reg_id]["portfolios"][pid]
            p_reg_ret = p_reg_data["ret"]
            p_reg_eq = 10000.0 * np.cumprod(1.0 + p_reg_ret)
            stress_matrix[reg_id] = {
                "description": reg["desc"],
                "sealed_oos": calculate_continuous_mtm_metrics(
                    p_reg_ret[d_val_end:],
                    p_reg_eq[d_val_end:],
                ),
                "full_period": calculate_continuous_mtm_metrics(
                    p_reg_ret,
                    p_reg_eq,
                ),
            }

        max_gross = float(np.max(p_exp))
        stress_verdict = compute_stress_resistance_verdict(stress_matrix, max_gross_exposure=max_gross)

        diag = pvt_diagnostics.get(pid, {})

        evaluated_portfolios[pid] = {
            "portfolio_id": pid,
            **p_splits,
            "yearly": p_yearly,
            "cpcv_median_sharpe": round(cpcv_median_sharpe, 4),
            "max_gross_exposure": round(max_gross, 4),
            "stress_matrix": stress_matrix,
            "stress_resistance_verdict": stress_verdict,
            **diag,
        }

    # Dynamic 5-Gate Promotion Evaluation & Append-Only Ledger Recording
    base_metrics = evaluated_portfolios["P2_RP_BASELINE"]
    ledger_manager = TrialLedgerManager()

    candidate_trials = [
        {"pid": "P2_RP_V2C_PVT", "name": "P2_RP_V2C_PVT (4-Sleeve + 15% Vol Target)", "expected_trial": 28},
        {"pid": "P2_RP_V2B_PVT", "name": "P2_RP_V2B_PVT (3-Sleeve + 15% Vol Target)", "expected_trial": 29},
    ]

    for cand in candidate_trials:
        pid = cand["pid"]
        cand_p = evaluated_portfolios[pid]
        ue = evaluate_5_upgrade_gates(
            base_metrics=base_metrics,
            cand_metrics=cand_p,
            cand_stress_matrix=cand_p["stress_matrix"],
            cand_max_gross=cand_p["max_gross_exposure"],
        )
        cand_p["upgrade_evaluation"] = ue

        # Idempotent ledger handling: check if hypothesis already recorded
        ledger_data = ledger_manager.load_ledger()
        existing_idx = None
        for i_tr, tr in enumerate(ledger_data.get("trials", [])):
            if tr.get("hypothesis_id") == pid:
                existing_idx = i_tr
                break

        if existing_idx is not None:
            trial_num = int(ledger_data["trials"][existing_idx]["trial_number"])
        else:
            trial_num = int(ledger_manager.get_current_m_cum() + 1)

        # DSR calculation under exact trial count
        oos_rets = cand_p["sealed_oos"]["daily_ret"].tolist() if "daily_ret" in cand_p["sealed_oos"] else regime_portfolios["regime_1_baseline"]["portfolios"][pid]["ret"][d_val_end:].tolist()
        _, dsr_oos, pval_oos = calculate_deflated_sharpe_ratio(oos_rets, estimated_trials=trial_num)
        cand_p["dsr_oos"] = round(dsr_oos, 4)
        cand_p["pval_oos"] = round(pval_oos, 4)
        cand_p["m_cum"] = trial_num

        # Trial entry
        ledger_entry = {
            "hypothesis_id": pid,
            "name": cand["name"],
            "family": "Multi-Strategy Causal Risk-Parity Ensemble Vol-Target Upgrade",
            "direction_mode": "LONG_ONLY_ENSEMBLE",
            "train_sharpe": cand_p["train"]["daily_mtm_sharpe"],
            "val_sharpe": cand_p["val"]["daily_mtm_sharpe"],
            "oos_sharpe": cand_p["sealed_oos"]["daily_mtm_sharpe"],
            "oos_return_pct": cand_p["sealed_oos"]["total_return_pct"],
            "oos_max_dd_pct": cand_p["sealed_oos"]["max_drawdown_pct"],
            "cpcv_median_sharpe": cand_p["cpcv_median_sharpe"],
            "dsr_oos": cand_p["dsr_oos"],
            "dsr_pval": cand_p["pval_oos"],
            "hurdles_passed": ue["passed_count"],
            "hurdles_total": 5,
            "stress_regimes": {
                "baseline_oos_sharpe": cand_p["stress_matrix"]["regime_1_baseline"]["sealed_oos"]["daily_mtm_sharpe"],
                "friction_2x_oos_sharpe": cand_p["stress_matrix"]["regime_2_friction_stress"]["sealed_oos"]["daily_mtm_sharpe"],
                "delay_1bar_oos_sharpe": cand_p["stress_matrix"]["regime_3_delay_stress"]["sealed_oos"]["daily_mtm_sharpe"],
                "stress_resistance_verdict": cand_p["stress_resistance_verdict"],
            },
            "verdict": ue["verdict"],
            "verdict_rationale": ue["verdict_rationale"],
        }

        if existing_idx is not None:
            ledger_entry["m_cum"] = trial_num
            ledger_entry["trial_number"] = trial_num
            ledger_entry["recorded_at_utc"] = ledger_data["trials"][existing_idx].get("recorded_at_utc", datetime.now(UTC).isoformat())
            ledger_data["trials"][existing_idx] = ledger_entry
            ledger_data["last_updated_utc"] = datetime.now(UTC).isoformat()
            ledger_manager.save_ledger(ledger_data)
            logger.info(f"Updated existing trial {pid} at M_cum = {trial_num}")
        else:
            ledger_manager.record_trial(ledger_entry)

    elapsed = time.time() - start_time
    logger.info(f"Audit completed in {elapsed:.2f} seconds.")

    combined_results = {
        "milestone": "M77",
        "description": "Milestone 77 Causal Portfolio-Level 15% Vol-Targeting Audit (V2B and V2C vs P2_RP_BASELINE)",
        "evaluation_timestamp_utc": datetime.now(UTC).isoformat(),
        "total_runtime_seconds": round(elapsed, 2),
        "portfolios": evaluated_portfolios,
        "benchmark_bnh": benchmark_bnh_summary,
    }

    # Save results JSON
    res_path = ROOT_DIR / "research" / "m77_portfolio_vol_targeting_results.json"
    res_path.parent.mkdir(parents=True, exist_ok=True)
    with open(res_path, "w", encoding="utf-8") as f:
        json.dump(combined_results, f, indent=2, cls=NumpyJSONEncoder)
    logger.info(f"Results saved to {res_path}")

    # Generate Markdown Report
    rep_path = ROOT_DIR / "docs" / "research" / "M77_PORTFOLIO_VOL_TARGETING_AUDIT.md"
    format_markdown_report(combined_results, rep_path)

    return combined_results


if __name__ == "__main__":
    run_m77_vol_targeting_audit()
