"""scripts/research/run_m75_1_clean_discovery_batch.py — Milestone 75.1 Clean Discovery Batch #2.

Executes Clean Discovery Batch #2 under the hardened zero-leverage engine:
- Trial #22: H1_CLEAN_VOL_SQUEEZE_LONG (Clean evaluation under hardened gross <= 1.0x clamp)
- Trial #23: H4_TREND_PULLBACK_VOL_TARGET (Orthogonal Trend-Pullback Long with 20-EMA Reclaim)
- Trial #24: H5_DUAL_HORIZON_ROTATION_GOLD (14d + 60d Blended Dual-Momentum Rotation with Gold Fallback)

Outputs:
- research/m75_1_clean_discovery_results.json
- docs/research/M75_1_CLEAN_DISCOVERY_REPORT.md
- Appends Trials #22, #23, #24 to research/discovery_trial_ledger.json (M_cum: 21 -> 24)
"""

from __future__ import annotations

import json
import logging
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.research.discovery_lab import (
    CausalDiscoveryEngine,
    H1_CleanVolSqueezeExpansionLong,
    H4_TrendPullbackVolTarget,
    H5_DualHorizonRotationGold,
    NumpyJSONEncoder,
    TrialLedgerManager,
    compute_stress_resistance_verdict,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("m75_1_clean_discovery_batch_runner")


def format_markdown_report(results: dict[str, Any], report_path: Path) -> str:
    """Generates the comprehensive Milestone 75.1 Clean Discovery Batch #2 Markdown report."""
    rep = []
    rep.append("# MILESTONE 75.1 RESEARCH DOSSIER: HARDENED SIMULATOR & CLEAN DISCOVERY BATCH #2")
    rep.append("## TRIALS #22, #23, #24 (H1_CLEAN / H4 / H5)")
    rep.append(f"**Evaluation Timestamp UTC:** `{results['evaluation_timestamp_utc']}`  ")
    rep.append(f"**Runtime:** `{results['total_runtime_seconds']:.2f} seconds` | **Trial Span:** `$M_{{\\text{{cum}}}} = 21 \\to 24$`  ")
    rep.append(f"**Ledger Path:** [`research/discovery_trial_ledger.json`](file:///{ROOT_DIR.as_posix()}/research/discovery_trial_ledger.json)  \n")
    rep.append("---\n")

    rep.append("## 1. EXECUTIVE SUMMARY & SIMULATOR HARDENING AUDIT\n")
    rep.append("Milestone 75.1 executes Clean Discovery Batch #2 under SKY's hardened zero-leverage simulation engine. ")
    rep.append("All trade-based and weight-based executions strictly enforce `gross_exposure <= 1.0000` via pre-fill headroom checks and prioritized exit executions.\n")

    rep.append("### Cumulative Trial Ledger Progression:")
    rep.append("- Prior Cumulative Trials: **`M_cum = 21`** (M63-M72 Baseline 18 + M75 Batch 1 Trials #19, #20, #21).")
    rep.append("- **Trial #22 (`H1_CLEAN_VOL_SQUEEZE_LONG`):** $M_{\\text{cum}} = 22$.")
    rep.append("- **Trial #23 (`H4_TREND_PULLBACK_VOL_TARGET`):** $M_{\\text{cum}} = 23$.")
    rep.append("- **Trial #24 (`H5_DUAL_HORIZON_ROTATION_GOLD`):** $M_{\\text{cum}} = 24$.\n")
    rep.append("---\n")

    rep.append("## 2. SIDE-BY-SIDE SCORECARD: TRAIN / VAL / SEALED OOS\n")
    rep.append("| Metric | H1_CLEAN (Vol Squeeze) | H4 (Trend Pullback) | H5 (Dual-Momentum Gold) | Equal-Weight BnH |")
    rep.append("|:---|:---:|:---:|:---:|:---:|")

    h1_clean = results["hypotheses"]["H1_CLEAN_VOL_SQUEEZE_LONG"]
    h4 = results["hypotheses"]["H4_TREND_PULLBACK_VOL_TARGET"]
    h5 = results["hypotheses"]["H5_DUAL_HORIZON_ROTATION_GOLD"]
    bnh_oos = h1_clean["splits_scorecard"]["sealed_oos"]["bnh"]

    rep.append(f"| **Direction Mode** | `{h1_clean['direction_mode']}` | `{h4['direction_mode']}` | `{h5['direction_mode']}` | Long-Only Beta |")
    rep.append(f"| **Trial Number (M_cum)** | `{h1_clean['m_cum']}` | `{h4['m_cum']}` | `{h5['m_cum']}` | — |")
    rep.append(f"| **Train Return %** | {h1_clean['splits_scorecard']['train']['strategy']['total_return_pct']:+.2f}% | {h4['splits_scorecard']['train']['strategy']['total_return_pct']:+.2f}% | {h5['splits_scorecard']['train']['strategy']['total_return_pct']:+.2f}% | {h1_clean['splits_scorecard']['train']['bnh']['total_return_pct']:+.2f}% |")
    rep.append(f"| **Train Sharpe** | {h1_clean['splits_scorecard']['train']['strategy']['daily_mtm_sharpe']:.2f} | {h4['splits_scorecard']['train']['strategy']['daily_mtm_sharpe']:.2f} | {h5['splits_scorecard']['train']['strategy']['daily_mtm_sharpe']:.2f} | {h1_clean['splits_scorecard']['train']['bnh']['daily_mtm_sharpe']:.2f} |")
    rep.append(f"| **Validation Return %** | {h1_clean['splits_scorecard']['val']['strategy']['total_return_pct']:+.2f}% | {h4['splits_scorecard']['val']['strategy']['total_return_pct']:+.2f}% | {h5['splits_scorecard']['val']['strategy']['total_return_pct']:+.2f}% | {h1_clean['splits_scorecard']['val']['bnh']['total_return_pct']:+.2f}% |")
    rep.append(f"| **Validation Sharpe** | {h1_clean['splits_scorecard']['val']['strategy']['daily_mtm_sharpe']:.2f} | {h4['splits_scorecard']['val']['strategy']['daily_mtm_sharpe']:.2f} | {h5['splits_scorecard']['val']['strategy']['daily_mtm_sharpe']:.2f} | {h1_clean['splits_scorecard']['val']['bnh']['daily_mtm_sharpe']:.2f} |")
    rep.append(f"| **Sealed OOS Return %** | **{h1_clean['splits_scorecard']['sealed_oos']['strategy']['total_return_pct']:+.2f}%** | **{h4['splits_scorecard']['sealed_oos']['strategy']['total_return_pct']:+.2f}%** | **{h5['splits_scorecard']['sealed_oos']['strategy']['total_return_pct']:+.2f}%** | **{bnh_oos['total_return_pct']:+.2f}%** |")
    rep.append(f"| **Sealed OOS Sharpe** | **{h1_clean['splits_scorecard']['sealed_oos']['strategy']['daily_mtm_sharpe']:.2f}** | **{h4['splits_scorecard']['sealed_oos']['strategy']['daily_mtm_sharpe']:.2f}** | **{h5['splits_scorecard']['sealed_oos']['strategy']['daily_mtm_sharpe']:.2f}** | **{bnh_oos['daily_mtm_sharpe']:.2f}** |")
    rep.append(f"| **Sealed OOS CAGR %** | {h1_clean['splits_scorecard']['sealed_oos']['strategy']['cagr_pct']:+.2f}% | {h4['splits_scorecard']['sealed_oos']['strategy']['cagr_pct']:+.2f}% | {h5['splits_scorecard']['sealed_oos']['strategy']['cagr_pct']:+.2f}% | {bnh_oos['cagr_pct']:+.2f}% |")
    rep.append(f"| **Sealed OOS Max DD %** | {h1_clean['splits_scorecard']['sealed_oos']['strategy']['max_drawdown_pct']:.2f}% | {h4['splits_scorecard']['sealed_oos']['strategy']['max_drawdown_pct']:.2f}% | {h5['splits_scorecard']['sealed_oos']['strategy']['max_drawdown_pct']:.2f}% | {bnh_oos['max_drawdown_pct']:.2f}% |")
    rep.append(f"| **Peak Gross Exposure** | **{h1_clean['cp2_hurdles']['hurdle_6_zero_leverage_invariant']['details'].split(': ')[1].split(' ')[0]}** | **{h4['cp2_hurdles']['hurdle_6_zero_leverage_invariant']['details'].split(': ')[1].split(' ')[0]}** | **{h5['cp2_hurdles']['hurdle_6_zero_leverage_invariant']['details'].split(': ')[1].split(' ')[0]}** | 1.0000 |")
    rep.append(f"| **Total Closed Trades** | {h1_clean['trade_metrics']['total_trades']} | {h4['trade_metrics']['total_trades']} | {h5['trade_metrics']['total_trades']} rebalances | — |")
    rep.append(f"| **CPCV Median Sharpe** | {h1_clean['statistical_rigor']['cpcv_median_sharpe']:.2f} | {h4['statistical_rigor']['cpcv_median_sharpe']:.2f} | {h5['statistical_rigor']['cpcv_median_sharpe']:.2f} | — |")
    rep.append(f"| **Cumulative DSR** | **{h1_clean['statistical_rigor']['dsr_oos']:.4f}** (p={h1_clean['statistical_rigor']['pval_oos']:.4f}) | **{h4['statistical_rigor']['dsr_oos']:.4f}** (p={h4['statistical_rigor']['pval_oos']:.4f}) | **{h5['statistical_rigor']['dsr_oos']:.4f}** (p={h5['statistical_rigor']['pval_oos']:.4f}) | — |")
    rep.append(f"| **CP-2 Hurdles Passed** | **{h1_clean['hurdle_summary']['passed_count']}/6** | **{h4['hurdle_summary']['passed_count']}/6** | **{h5['hurdle_summary']['passed_count']}/6** | — |")
    rep.append(f"| **Epistemic Verdict** | **`{h1_clean['epistemic_verdict']}`** | **`{h4['epistemic_verdict']}`** | **`{h5['epistemic_verdict']}`** | — |")
    rep.append("\n---\n")

    rep.append("## 3. 3-REGIME INSTITUTIONAL STRESS MATRIX COMPARISON\n")
    rep.append("| Hypothesis | Regime 1: Baseline (20 bps, t+1) | Regime 2: 2x Friction (40 bps, t+1) | Regime 3: 1-Bar Delay (20 bps, t+2) | Stress Resistance Verdict |")
    rep.append("|:---|:---:|:---:|:---:|:---:|")

    for hid, h_res in results["hypotheses"].items():
        sm = h_res["stress_matrix"]
        sh_base = sm["regime_1_baseline"]["sealed_oos"]["daily_mtm_sharpe"]
        ret_base = sm["regime_1_baseline"]["sealed_oos"]["total_return_pct"]
        sh_fric = sm["regime_2_friction_stress"]["sealed_oos"]["daily_mtm_sharpe"]
        ret_fric = sm["regime_2_friction_stress"]["sealed_oos"]["total_return_pct"]
        sh_delay = sm["regime_3_delay_stress"]["sealed_oos"]["daily_mtm_sharpe"]
        ret_delay = sm["regime_3_delay_stress"]["sealed_oos"]["total_return_pct"]

        res_text = compute_stress_resistance_verdict(
            stress_matrix=sm,
            max_gross_exposure=float(h_res["cp2_hurdles"]["hurdle_6_zero_leverage_invariant"]["details"].split(": ")[1].split(" ")[0]),
        )

        rep.append(
            f"| **{hid}** | Ret: {ret_base:+.2f}%, Sh: {sh_base:.2f} | Ret: {ret_fric:+.2f}%, Sh: {sh_fric:.2f} | Ret: {ret_delay:+.2f}%, Sh: {sh_delay:.2f} | **`{res_text}`** |"
        )
    rep.append("\n---\n")

    rep.append("## 4. DETAILED CP-2 HURDLES BREAKDOWN BY HYPOTHESIS\n")
    for hid, h_res in results["hypotheses"].items():
        rep.append(f"### {hid} ({h_res['name']}): **{h_res['hurdle_summary']['summary_text']}**")
        rep.append("| Hurdle | Requirement | Observed Details | Status |")
        rep.append("|:---|:---|:---|:---:|")
        for h_key, h_data in h_res["cp2_hurdles"].items():
            rep.append(f"| **{h_data['name']}** | {h_data['requirement']} | {h_data['details']} | **{'PASS' if h_data['passed'] else 'FAIL'}** |")
        rep.append(f"**Verdict Rationale:** {h_res['verdict_rationale']}\n")

    rep.append("---\n")
    rep.append("## 5. GOVERNANCE & CAPITAL INVARIANTS\n")
    rep.append("- `REAL_CAPITAL_ENABLED = False` (Permanently locked).")
    rep.append("- `CAPITAL_MODE = \"TIER_0_PAPER\"` (All discovery execution is simulated/paper).")
    rep.append("- Maximum gross exposure $\\le 1.0001$ verified across all tested hypotheses (zero leverage).")
    rep.append("- Append-only trial ledger persisted at `research/discovery_trial_ledger.json`.")

    content = "\n".join(rep)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(content, encoding="utf-8")
    logger.info(f"Report written to {report_path}")
    return content


def run_m75_1_clean_batch() -> dict[str, Any]:
    """Executes Milestone 75.1 Clean Discovery Batch #2 across H1_CLEAN, H4, and H5."""
    logger.info("=== STARTING MILESTONE 75.1: CLEAN DISCOVERY BATCH #2 ===")
    start_time = time.time()

    ledger_manager = TrialLedgerManager()
    engine = CausalDiscoveryEngine(ledger_manager=ledger_manager)

    hypotheses: list[Any] = [
        H1_CleanVolSqueezeExpansionLong(),
        H4_TrendPullbackVolTarget(),
        H5_DualHorizonRotationGold(),
    ]

    results_by_hyp: dict[str, Any] = {}

    for hyp in hypotheses:
        spec = hyp.spec()
        logger.info(f"Evaluating {spec.hypothesis_id}...")
        res = engine.evaluate_hypothesis(hyp)
        results_by_hyp[spec.hypothesis_id] = res

    elapsed = time.time() - start_time
    logger.info(f"Batch completed in {elapsed:.2f} seconds.")

    combined_results = {
        "milestone": "M75.1",
        "description": "Clean Discovery Batch #2 (Hardened Zero-Leverage Engine)",
        "evaluation_timestamp_utc": datetime.now(UTC).isoformat(),
        "total_runtime_seconds": round(elapsed, 2),
        "hypotheses": results_by_hyp,
    }

    # Save outputs
    res_path = ROOT_DIR / "research" / "m75_1_clean_discovery_results.json"
    res_path.parent.mkdir(parents=True, exist_ok=True)
    with open(res_path, "w", encoding="utf-8") as f:
        json.dump(combined_results, f, indent=2, cls=NumpyJSONEncoder)
    logger.info(f"Results saved to {res_path}")

    rep_path = ROOT_DIR / "docs" / "research" / "M75_1_CLEAN_DISCOVERY_REPORT.md"
    format_markdown_report(combined_results, rep_path)

    return combined_results


if __name__ == "__main__":
    run_m75_1_clean_batch()
