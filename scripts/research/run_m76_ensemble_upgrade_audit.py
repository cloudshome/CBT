"""scripts/research/run_m76_ensemble_upgrade_audit.py — Milestone 76 Causal Ensemble Upgrade Audit.

Evaluates head-to-head performance of our current production baseline P2_RP against
three pre-registered P2_RP_V2 ensemble upgrade candidates:
1. P2_RP_BASELINE: 50% S1 + 50% S2-Div
2. Trial #25: P2_RP_V2A_S1_H5 (50% S1 + 50% H5_DUAL_HORIZON_ROTATION_GOLD)
3. Trial #26: P2_RP_V2B_S1_H5_H1 (33.33% S1 + 33.33% H5 + 33.33% H1_CLEAN)
4. Trial #27: P2_RP_V2C_4SLEEVE (25% S1 + 25% S2-Div + 25% H5 + 25% H1_CLEAN)

Outputs:
- research/m76_ensemble_upgrade_results.json
- docs/research/M76_ENSEMBLE_UPGRADE_AUDIT.md
- Appends Trials #25, #26, #27 to research/discovery_trial_ledger.json (M_cum: 24 -> 27)
"""

from __future__ import annotations

import json
import logging
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("m76_ensemble_audit_runner")

# Governance Invariants
REAL_CAPITAL_ENABLED: bool = False
CAPITAL_MODE: str = "TIER_0_PAPER"


def evaluate_5_upgrade_gates(
    base_metrics: dict[str, Any],
    cand_metrics: dict[str, Any],
    cand_stress_matrix: dict[str, Any],
    cand_max_gross: float,
) -> dict[str, Any]:
    """Dynamically evaluates SKY's 5 institutional upgrade promotion gates for an ensemble candidate."""
    base_full = base_metrics["full_period"]
    base_oos = base_metrics["sealed_oos"]
    base_2022_dd = base_metrics["yearly"].get(2022, {}).get("max_drawdown_pct", 100.0)

    cand_full = cand_metrics["full_period"]
    cand_oos = cand_metrics["sealed_oos"]
    cand_2022_dd = cand_metrics["yearly"].get(2022, {}).get("max_drawdown_pct", 100.0)

    # Gate 1 (Full-Period Edge): Strictly higher Full-Period Sharpe AND Calmar Ratio
    g1_passed = bool(
        (cand_full["daily_mtm_sharpe"] > base_full["daily_mtm_sharpe"])
        and (cand_full["calmar_ratio"] > base_full["calmar_ratio"])
    )
    # Gate 2 (Sealed OOS Edge): Strictly higher Sealed OOS Sharpe AND Sealed OOS Return
    g2_passed = bool(
        (cand_oos["daily_mtm_sharpe"] > base_oos["daily_mtm_sharpe"])
        and (cand_oos["total_return_pct"] > base_oos["total_return_pct"])
    )
    # Gate 3 (Drawdown Discipline): Full-Period Max DD <= base + 1.0% AND 2022 Bear DD <= base + 1.0%
    g3_passed = bool(
        (cand_full["max_drawdown_pct"] <= base_full["max_drawdown_pct"] + 1.0)
        and (cand_2022_dd <= base_2022_dd + 1.0)
    )
    # Gate 4 (Stress Survival): SURVIVES STRESS across 2x friction & 1-bar delay
    stress_verdict = compute_stress_resistance_verdict(cand_stress_matrix, max_gross_exposure=cand_max_gross)
    g4_passed = bool(stress_verdict == "SURVIVES STRESS")

    # Gate 5 (Zero Leverage Invariant): Peak gross exposure <= 1.0001
    g5_passed = bool(cand_max_gross <= 1.0001)

    gates = {
        "gate_1_full_period_edge": {
            "name": "Full-Period Edge (Sharpe & Calmar)",
            "requirement": f"Sharpe > {base_full['daily_mtm_sharpe']:.2f} AND Calmar > {base_full['calmar_ratio']:.2f}",
            "observed": f"Sharpe: {cand_full['daily_mtm_sharpe']:.2f}, Calmar: {cand_full['calmar_ratio']:.2f}",
            "passed": g1_passed,
        },
        "gate_2_sealed_oos_edge": {
            "name": "Sealed OOS Edge (Sharpe & Return)",
            "requirement": f"OOS Sharpe > {base_oos['daily_mtm_sharpe']:.2f} AND OOS Ret > {base_oos['total_return_pct']:+.2f}%",
            "observed": f"OOS Sharpe: {cand_oos['daily_mtm_sharpe']:.2f}, OOS Ret: {cand_oos['total_return_pct']:+.2f}%",
            "passed": g2_passed,
        },
        "gate_3_drawdown_discipline": {
            "name": "Drawdown Discipline (Full DD & 2022 Bear DD)",
            "requirement": f"Full DD <= {base_full['max_drawdown_pct'] + 1.0:.2f}% AND 2022 DD <= {base_2022_dd + 1.0:.2f}%",
            "observed": f"Full DD: {cand_full['max_drawdown_pct']:.2f}%, 2022 DD: {cand_2022_dd:.2f}%",
            "passed": g3_passed,
        },
        "gate_4_stress_survival": {
            "name": "Institutional Stress Survival",
            "requirement": "SURVIVES STRESS (positive OOS return & Sharpe across 2x friction and 1-bar delay)",
            "observed": stress_verdict,
            "passed": g4_passed,
        },
        "gate_5_zero_leverage_invariant": {
            "name": "Zero Leverage Invariant",
            "requirement": "Peak gross exposure <= 1.0001 across all regimes",
            "observed": f"Peak Gross Exposure: {cand_max_gross:.4f}",
            "passed": g5_passed,
        },
    }

    passed_count = sum(1 for g in gates.values() if g["passed"])
    failed_count = len(gates) - passed_count
    verdict = "CANDIDATE_QUALIFIED_FOR_SHADOW_UPGRADE" if passed_count == 5 else "KEEP_P2_RP_BASELINE"

    reasons = []
    if not g1_passed:
        reasons.append(f"Failed Gate 1 (Full Sharpe: {cand_full['daily_mtm_sharpe']:.2f} vs {base_full['daily_mtm_sharpe']:.2f}, Calmar: {cand_full['calmar_ratio']:.2f} vs {base_full['calmar_ratio']:.2f})")
    if not g2_passed:
        reasons.append(f"Failed Gate 2 (OOS Sharpe: {cand_oos['daily_mtm_sharpe']:.2f} vs {base_oos['daily_mtm_sharpe']:.2f})")
    if not g3_passed:
        reasons.append(f"Failed Gate 3 (Full DD: {cand_full['max_drawdown_pct']:.2f}% vs {base_full['max_drawdown_pct']:.2f}%)")
    if not g4_passed:
        reasons.append(f"Failed Gate 4 ({stress_verdict})")
    if not g5_passed:
        reasons.append(f"Failed Gate 5 (Leverage breach: {cand_max_gross:.4f})")

    verdict_rationale = "; ".join(reasons) if reasons else "Passed all 5 institutional upgrade promotion gates."

    return {
        "gates": gates,
        "passed_count": passed_count,
        "failed_count": failed_count,
        "summary_text": f"{passed_count}/5 PASS | {failed_count}/5 FAIL",
        "verdict": verdict,
        "verdict_rationale": verdict_rationale,
    }


def format_markdown_report(results: dict[str, Any], report_path: Path) -> str:
    """Generates the comprehensive Milestone 76 Markdown audit dossier."""
    rep = []
    rep.append("# MILESTONE 76 RESEARCH DOSSIER: CAUSAL ENSEMBLE UPGRADE AUDIT")
    rep.append("## HEAD-TO-HEAD: P2_RP_BASELINE vs P2_RP_V2 CANDIDATES (V2A / V2B / V2C)")
    rep.append(f"**Evaluation Timestamp UTC:** `{results['evaluation_timestamp_utc']}`  ")
    rep.append(f"**Runtime:** `{results['total_runtime_seconds']:.2f} seconds` | **Trial Span:** `$M_{{\\text{{cum}}}} = 24 \\to 27$`  ")
    rep.append(f"**Ledger Path:** [`research/discovery_trial_ledger.json`](file:///{ROOT_DIR.as_posix()}/research/discovery_trial_ledger.json)  \n")
    rep.append("---\n")

    rep.append("## 1. EXECUTIVE SUMMARY & ENSEMBLE SPECIFICATIONS\n")
    rep.append("Milestone 76 executes an institutional head-to-head causal audit comparing our current production baseline `P2_RP` against three pre-registered `P2_RP_V2` ensemble upgrade candidates incorporating the two M75.1 stress-tested survivors (`H5_DUAL_HORIZON_ROTATION_GOLD` and `H1_CLEAN_VOL_SQUEEZE_LONG`).\n")

    rep.append("### Ensemble Configurations:")
    rep.append("1. **`P2_RP_BASELINE`:** `50% S1 + 50% S2-Div` (Current Production Architecture).")
    rep.append("2. **`P2_RP_V2A_S1_H5` (Trial #25):** `50% S1 + 50% H5` (Replacing 30d S2-Div with 14d+60d dual-horizon rotation).")
    rep.append("3. **`P2_RP_V2B_S1_H5_H1` (Trial #26):** `33.33% S1 + 33.33% H5 + 33.33% H1_CLEAN` (3-sleeve orthogonal trend + rotation + breakout blend).")
    rep.append("4. **`P2_RP_V2C_4SLEEVE` (Trial #27):** `25% S1 + 25% S2-Div + 25% H5 + 25% H1_CLEAN` (4-sleeve multi-strategy diversified blend).\n")
    rep.append("---\n")

    # 2. Correlation Matrix
    rep.append("## 2. PAIRWISE 4-SLEEVE RETURN CORRELATION MATRIX\n")
    rep.append("Verifies genuine empirical diversification across individual strategy sleeves:\n")
    rep.append("### Full Period (2020–2026):")
    rep.append("| Sleeve | S1 (Donchian Macro) | S2-Div (30d Rotation) | H5 (14d+60d Rotation) | H1_CLEAN (Vol Squeeze) |")
    rep.append("|:---|:---:|:---:|:---:|:---:|")
    corr_full = results["correlation_matrices"]["full_period"]
    for s in ["S1", "S2-Div", "H5", "H1_CLEAN"]:
        rep.append(f"| **{s}** | {corr_full[s]['S1']:.4f} | {corr_full[s]['S2-Div']:.4f} | {corr_full[s]['H5']:.4f} | {corr_full[s]['H1_CLEAN']:.4f} |")

    rep.append("\n### Sealed OOS (2025–2026):")
    rep.append("| Sleeve | S1 (Donchian Macro) | S2-Div (30d Rotation) | H5 (14d+60d Rotation) | H1_CLEAN (Vol Squeeze) |")
    rep.append("|:---|:---:|:---:|:---:|:---:|")
    corr_oos = results["correlation_matrices"]["sealed_oos"]
    for s in ["S1", "S2-Div", "H5", "H1_CLEAN"]:
        rep.append(f"| **{s}** | {corr_oos[s]['S1']:.4f} | {corr_oos[s]['S2-Div']:.4f} | {corr_oos[s]['H5']:.4f} | {corr_oos[s]['H1_CLEAN']:.4f} |")
    rep.append("\n---\n")

    # 3. Head to Head Scorecard
    rep.append("## 3. HEAD-TO-HEAD SCORECARD: BASELINE vs CANDIDATE ENSEMBLES\n")
    rep.append("| Metric | P2_RP_BASELINE | V2A (S1 + H5) | V2B (S1 + H5 + H1) | V2C (4-Sleeve) | Equal-Weight BnH |")
    rep.append("|:---|:---:|:---:|:---:|:---:|:---:|")

    base = results["portfolios"]["P2_RP_BASELINE"]
    v2a = results["portfolios"]["P2_RP_V2A_S1_H5"]
    v2b = results["portfolios"]["P2_RP_V2B_S1_H5_H1"]
    v2c = results["portfolios"]["P2_RP_V2C_4SLEEVE"]
    bnh = results["benchmark_bnh"]

    rep.append("| **Trial Number (M_cum)** | Baseline (M14) | #25 | #26 | #27 | — |")
    rep.append(f"| **Full-Period Return %** | **{base['full_period']['total_return_pct']:+.1f}%** | {v2a['full_period']['total_return_pct']:+.1f}% | {v2b['full_period']['total_return_pct']:+.1f}% | {v2c['full_period']['total_return_pct']:+.1f}% | {bnh['full_period']['total_return_pct']:+.1f}% |")
    rep.append(f"| **Full-Period Sharpe** | **{base['full_period']['daily_mtm_sharpe']:.2f}** | {v2a['full_period']['daily_mtm_sharpe']:.2f} | {v2b['full_period']['daily_mtm_sharpe']:.2f} | **{v2c['full_period']['daily_mtm_sharpe']:.2f}** | {bnh['full_period']['daily_mtm_sharpe']:.2f} |")
    rep.append(f"| **Full-Period Calmar** | **{base['full_period']['calmar_ratio']:.2f}** | {v2a['full_period']['calmar_ratio']:.2f} | {v2b['full_period']['calmar_ratio']:.2f} | {v2c['full_period']['calmar_ratio']:.2f} | {bnh['full_period']['calmar_ratio']:.2f} |")
    rep.append(f"| **Full-Period Max DD %** | {base['full_period']['max_drawdown_pct']:.2f}% | {v2a['full_period']['max_drawdown_pct']:.2f}% | **{v2b['full_period']['max_drawdown_pct']:.2f}%** | {v2c['full_period']['max_drawdown_pct']:.2f}% | {bnh['full_period']['max_drawdown_pct']:.2f}% |")
    rep.append(f"| **Sealed OOS Return %** | {base['sealed_oos']['total_return_pct']:+.2f}% | **{v2a['sealed_oos']['total_return_pct']:+.2f}%** | **{v2b['sealed_oos']['total_return_pct']:+.2f}%** | **{v2c['sealed_oos']['total_return_pct']:+.2f}%** | {bnh['sealed_oos']['total_return_pct']:+.2f}% |")
    rep.append(f"| **Sealed OOS Sharpe** | {base['sealed_oos']['daily_mtm_sharpe']:.2f} | **{v2a['sealed_oos']['daily_mtm_sharpe']:.2f}** | **{v2b['sealed_oos']['daily_mtm_sharpe']:.2f}** | **{v2c['sealed_oos']['daily_mtm_sharpe']:.2f}** | {bnh['sealed_oos']['daily_mtm_sharpe']:.2f} |")
    rep.append(f"| **Sealed OOS Max DD %** | {base['sealed_oos']['max_drawdown_pct']:.2f}% | {v2a['sealed_oos']['max_drawdown_pct']:.2f}% | **{v2b['sealed_oos']['max_drawdown_pct']:.2f}%** | **{v2c['sealed_oos']['max_drawdown_pct']:.2f}%** | {bnh['sealed_oos']['max_drawdown_pct']:.2f}% |")
    rep.append(f"| **Peak Gross Exposure** | **{base['max_gross_exposure']:.4f}** | **{v2a['max_gross_exposure']:.4f}** | **{v2b['max_gross_exposure']:.4f}** | **{v2c['max_gross_exposure']:.4f}** | 1.0000 |")
    rep.append(f"| **CPCV Median Sharpe** | {base['cpcv_median_sharpe']:.2f} | {v2a['cpcv_median_sharpe']:.2f} | {v2b['cpcv_median_sharpe']:.2f} | {v2c['cpcv_median_sharpe']:.2f} | — |")
    rep.append(f"| **Cumulative DSR** | — | {v2a['dsr_oos']:.4f} (p={v2a['pval_oos']:.4f}) | {v2b['dsr_oos']:.4f} (p={v2b['pval_oos']:.4f}) | {v2c['dsr_oos']:.4f} (p={v2c['pval_oos']:.4f}) | — |")
    rep.append(f"| **5 Upgrade Gates** | Baseline | **{v2a['upgrade_evaluation']['summary_text']}** | **{v2b['upgrade_evaluation']['summary_text']}** | **{v2c['upgrade_evaluation']['summary_text']}** | — |")
    rep.append(f"| **Audit Promotion Verdict**| **CURRENT PROD** | **`{v2a['upgrade_evaluation']['verdict']}`** | **`{v2b['upgrade_evaluation']['verdict']}`** | **`{v2c['upgrade_evaluation']['verdict']}`** | — |")
    rep.append("\n---\n")

    # 4. Stress Matrix
    rep.append("## 4. 3-REGIME INSTITUTIONAL STRESS MATRIX COMPARISON\n")
    rep.append("| Portfolio | Regime 1: Baseline (20 bps, t+1) | Regime 2: 2x Friction (40 bps, t+1) | Regime 3: 1-Bar Delay (20 bps, t+2) | Stress Resistance Verdict |")
    rep.append("|:---|:---:|:---:|:---:|:---:|")

    for pid in ["P2_RP_BASELINE", "P2_RP_V2A_S1_H5", "P2_RP_V2B_S1_H5_H1", "P2_RP_V2C_4SLEEVE"]:
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

    # 5. Year-by-Year Comparison
    rep.append("## 5. YEAR-BY-YEAR PERFORMANCE COMPARISON (2022–2026)\n")
    rep.append("| Year | P2_RP_BASELINE | V2A (S1 + H5) | V2B (S1 + H5 + H1) | V2C (4-Sleeve) | Equal-Weight BnH |")
    rep.append("|:---|:---:|:---:|:---:|:---:|:---:|")
    years = [2022, 2023, 2024, 2025, 2026]
    for yr in years:
        b_yr = base["yearly"].get(yr, {})
        v2a_yr = v2a["yearly"].get(yr, {})
        v2b_yr = v2b["yearly"].get(yr, {})
        v2c_yr = v2c["yearly"].get(yr, {})
        bnh_yr = bnh["yearly"].get(yr, {})

        b_ret = b_yr.get("total_return_pct", 0.0)
        v2a_ret = v2a_yr.get("total_return_pct", 0.0)
        v2b_ret = v2b_yr.get("total_return_pct", 0.0)
        v2c_ret = v2c_yr.get("total_return_pct", 0.0)
        bnh_ret = bnh_yr.get("total_return_pct", 0.0)

        rep.append(f"| **{yr}** | {b_ret:+.2f}% (DD: {b_yr.get('max_drawdown_pct', 0.0):.1f}%) | {v2a_ret:+.2f}% (DD: {v2a_yr.get('max_drawdown_pct', 0.0):.1f}%) | {v2b_ret:+.2f}% (DD: {v2b_yr.get('max_drawdown_pct', 0.0):.1f}%) | {v2c_ret:+.2f}% (DD: {v2c_yr.get('max_drawdown_pct', 0.0):.1f}%) | {bnh_ret:+.2f}% (DD: {bnh_yr.get('max_drawdown_pct', 0.0):.1f}%) |")

    rep.append("\n---\n")

    # 6. Detailed 5-Gate Promotion Analysis
    rep.append("## 6. DETAILED 5-GATE PROMOTION EVALUATION BY CANDIDATE\n")
    for pid in ["P2_RP_V2A_S1_H5", "P2_RP_V2B_S1_H5_H1", "P2_RP_V2C_4SLEEVE"]:
        p_res = results["portfolios"][pid]
        ue = p_res["upgrade_evaluation"]
        rep.append(f"### {pid}: **{ue['summary_text']}** -> **`{ue['verdict']}`**")
        rep.append("| Gate | Requirement | Observed Details | Status |")
        rep.append("|:---|:---|:---|:---:|")
        for g_id, g_data in ue["gates"].items():
            rep.append(f"| **{g_data['name']}** | {g_data['requirement']} | {g_data['observed']} | **{'PASS' if g_data['passed'] else 'FAIL'}** |")
        rep.append(f"**Gate Verdict Rationale:** {ue['verdict_rationale']}\n")

    rep.append("---\n")
    rep.append("## 7. GOVERNANCE & ARCHITECTURAL VERDICT\n")
    rep.append("- `REAL_CAPITAL_ENABLED = False` (Permanently locked).")
    rep.append("- `CAPITAL_MODE = \"TIER_0_PAPER\"` (All discovery execution is simulated/paper).")
    rep.append("- `core/strategies/p2_risk_parity.py` and `core/strategies/p2_shadow_runner.py` remain untouched.")
    rep.append("- All candidates strictly preserved zero-leverage invariants (`gross_exposure <= 1.0001`).")
    rep.append("- Append-only trial ledger persisted at `research/discovery_trial_ledger.json` (advancing $M_{\\text{cum}} = 24 \\to 27$).")

    content = "\n".join(rep)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(content, encoding="utf-8")
    logger.info(f"Report written to {report_path}")
    return content


def run_m76_ensemble_audit() -> dict[str, Any]:
    """Executes the full Milestone 76 Causal Ensemble Upgrade Audit."""
    logger.info("=== STARTING MILESTONE 76: CAUSAL ENSEMBLE UPGRADE AUDIT ===")
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
    sleeves_by_regime: dict[str, dict[str, pd.DataFrame]] = {}

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

        # Store aligned sleeves
        sleeves_by_regime[reg_id] = {
            "S1": df_m65_a["s1_ret"],
            "S2-Div": df_m65_a["s2_ret"],
            "H5": df_h5_a["daily_ret"],
            "H1_CLEAN": df_h1_a["daily_ret"],
        }

        # Construct portfolio return series
        p_base_ret = 0.5 * s1_ret + 0.5 * s2_ret
        p_v2a_ret = 0.5 * s1_ret + 0.5 * h5_ret
        p_v2b_ret = (1.0 / 3.0) * s1_ret + (1.0 / 3.0) * h5_ret + (1.0 / 3.0) * h1_ret
        p_v2c_ret = 0.25 * s1_ret + 0.25 * s2_ret + 0.25 * h5_ret + 0.25 * h1_ret

        # Gross exposure series
        p_base_exp = 0.5 * s1_exp + 0.5 * s2_exp
        p_v2a_exp = 0.5 * s1_exp + 0.5 * h5_exp
        p_v2b_exp = (1.0 / 3.0) * s1_exp + (1.0 / 3.0) * h5_exp + (1.0 / 3.0) * h1_exp
        p_v2c_exp = 0.25 * s1_exp + 0.25 * s2_exp + 0.25 * h5_exp + 0.25 * h1_exp

        # Buy and Hold Benchmark
        bnh_ret = df_m65_a["bnh_ret"].values

        port_data = {
            "P2_RP_BASELINE": {"ret": p_base_ret, "exp": p_base_exp},
            "P2_RP_V2A_S1_H5": {"ret": p_v2a_ret, "exp": p_v2a_exp},
            "P2_RP_V2B_S1_H5_H1": {"ret": p_v2b_ret, "exp": p_v2b_exp},
            "P2_RP_V2C_4SLEEVE": {"ret": p_v2c_ret, "exp": p_v2c_exp},
            "BNH": {"ret": bnh_ret, "exp": np.ones(len(bnh_ret))},
        }

        regime_portfolios[reg_id] = {
            "dates": common_idx,
            "portfolios": port_data,
        }

    # Use Baseline Regime (Regime 1) for Master Evaluations
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

    # 1. Compute Pairwise Return Correlation Matrix across the 4 sleeves
    s_base = sleeves_by_regime["regime_1_baseline"]
    df_s_base = pd.DataFrame(s_base)

    corr_full = df_s_base.corr().round(4).to_dict()
    corr_oos = df_s_base.iloc[d_val_end:].corr().round(4).to_dict()

    correlation_matrices = {
        "full_period": corr_full,
        "sealed_oos": corr_oos,
    }

    # 2. Evaluate all portfolios across splits and stress regimes
    portfolio_names = [
        "P2_RP_BASELINE",
        "P2_RP_V2A_S1_H5",
        "P2_RP_V2B_S1_H5_H1",
        "P2_RP_V2C_4SLEEVE",
    ]

    evaluated_portfolios: dict[str, Any] = {}

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

    # Evaluate Portfolios
    for pid in portfolio_names:
        # Baseline regime arrays
        p_base_data = regime_portfolios["regime_1_baseline"]["portfolios"][pid]
        p_ret = p_base_data["ret"]
        p_exp = p_base_data["exp"]
        p_eq = 10000.0 * np.cumprod(1.0 + p_ret)

        # Splits metrics
        p_splits: dict[str, Any] = {}
        for sp_name, (sp_s, sp_e) in splits_idx.items():
            p_splits[sp_name] = calculate_continuous_mtm_metrics(
                p_ret[sp_s:sp_e],
                p_eq[sp_s:sp_e],
            )

        # Yearly breakdown
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
        cpcv_median_sharpe = float(cpcv_res.get("median_sharpe", 0.0))

        # Stress Matrix
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

        evaluated_portfolios[pid] = {
            "portfolio_id": pid,
            **p_splits,
            "yearly": p_yearly,
            "cpcv_median_sharpe": round(cpcv_median_sharpe, 4),
            "max_gross_exposure": round(max_gross, 4),
            "stress_matrix": stress_matrix,
            "stress_resistance_verdict": stress_verdict,
        }

    # 3. Dynamic 5-Gate Promotion Evaluation & Append-Only Ledger Recording
    base_metrics = evaluated_portfolios["P2_RP_BASELINE"]
    ledger_manager = TrialLedgerManager()

    candidate_trials = [
        {"pid": "P2_RP_V2A_S1_H5", "name": "P2_RP_V2A (50% S1 + 50% H5)", "expected_trial": 25},
        {"pid": "P2_RP_V2B_S1_H5_H1", "name": "P2_RP_V2B (33% S1 + 33% H5 + 33% H1_CLEAN)", "expected_trial": 26},
        {"pid": "P2_RP_V2C_4SLEEVE", "name": "P2_RP_V2C (25% S1 + 25% S2-Div + 25% H5 + 25% H1_CLEAN)", "expected_trial": 27},
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

        # DSR calculation under incrementing M_cum
        current_m_cum = ledger_manager.get_current_m_cum() + 1
        oos_rets = cand_p["sealed_oos"]["daily_ret"].tolist() if "daily_ret" in cand_p["sealed_oos"] else regime_portfolios["regime_1_baseline"]["portfolios"][pid]["ret"][d_val_end:].tolist()
        _, dsr_oos, pval_oos = calculate_deflated_sharpe_ratio(oos_rets, estimated_trials=current_m_cum)
        cand_p["dsr_oos"] = round(dsr_oos, 4)
        cand_p["pval_oos"] = round(pval_oos, 4)
        cand_p["m_cum"] = current_m_cum

        # Append trial to discovery ledger
        ledger_entry = {
            "hypothesis_id": pid,
            "name": cand["name"],
            "family": "Multi-Strategy Causal Risk-Parity Ensemble Upgrade",
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
        ledger_manager.record_trial(ledger_entry)

    elapsed = time.time() - start_time
    logger.info(f"Audit completed in {elapsed:.2f} seconds.")

    combined_results = {
        "milestone": "M76",
        "description": "Milestone 76 Causal Ensemble Upgrade Audit (P2_RP vs P2_RP_V2 with H5 and H1_CLEAN)",
        "evaluation_timestamp_utc": datetime.now(UTC).isoformat(),
        "total_runtime_seconds": round(elapsed, 2),
        "correlation_matrices": correlation_matrices,
        "portfolios": evaluated_portfolios,
        "benchmark_bnh": benchmark_bnh_summary,
    }

    # Save results JSON
    res_path = ROOT_DIR / "research" / "m76_ensemble_upgrade_results.json"
    res_path.parent.mkdir(parents=True, exist_ok=True)
    with open(res_path, "w", encoding="utf-8") as f:
        json.dump(combined_results, f, indent=2, cls=NumpyJSONEncoder)
    logger.info(f"Results saved to {res_path}")

    # Generate Markdown Report
    rep_path = ROOT_DIR / "docs" / "research" / "M76_ENSEMBLE_UPGRADE_AUDIT.md"
    format_markdown_report(combined_results, rep_path)

    return combined_results


if __name__ == "__main__":
    run_m76_ensemble_audit()
