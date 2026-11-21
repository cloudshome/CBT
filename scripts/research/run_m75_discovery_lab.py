"""scripts/research/run_m75_discovery_lab.py — Milestone 75 Strategy Discovery Lab Benchmark.

Executes the first pre-registered 3-hypothesis causal batch:
- H1: Volatility Compression -> Expansion Breakout (Long-Only)
- H2: Market-Neutral Cross-Asset Relative-Value Momentum Pair
- H3: Capitulation Flush & Leverage-Exhaustion Rebound (Long-Only)

Outputs:
- research/m75_discovery_lab_results.json
- research/discovery_trial_ledger.json (advancing M_cum strictly from 18 to 21)
- docs/research/M75_DISCOVERY_LAB_REPORT.md
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
    BASELINE_M_CUM,
    CausalDiscoveryEngine,
    H1_VolSqueezeExpansionLong,
    H2_CrossAssetRvPair,
    H3_PostCrashLiqRebound,
    NumpyJSONEncoder,
    TrialLedgerManager,
    compute_stress_resistance_verdict,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("m75_discovery_lab_runner")


def format_markdown_report(results: dict[str, Any], report_path: Path) -> str:
    """Generates the comprehensive Milestone 75 Markdown report."""
    rep = []
    rep.append("# MILESTONE 75 RESEARCH DOSSIER: UNIFIED HISTORICAL STRATEGY DISCOVERY LAB")
    rep.append("## FIRST 3-HYPOTHESIS CAUSAL BATCH (H1 / H2 / H3)")
    rep.append(f"**Evaluation Timestamp UTC:** `{results['evaluation_timestamp_utc']}`  ")
    rep.append(f"**Runtime:** `{results['total_runtime_seconds']:.2f} seconds` | **Trial Span:** `$M_{{\\text{{cum}}}} = 18 \\to 21$`  ")
    rep.append(f"**Ledger Path:** [`research/discovery_trial_ledger.json`](file:///{ROOT_DIR.as_posix()}/research/discovery_trial_ledger.json)  \n")
    rep.append("---\n")

    rep.append("## 1. EXECUTIVE SUMMARY & MULTIPLE-TESTING TRIAL INTEGRITY\n")
    rep.append("Milestone 75 establishes SKY's institutional **Unified Historical Strategy Discovery Lab** (`core/research/discovery_lab.py`). ")
    rep.append("To protect against lookahead bias, parameter mining, and $p$-hacking, all hypotheses undergo rigorous pre-registration, failure-memory screening, 3-regime cost stress simulation, and deflated Sharpe multiple-testing penalties where $M_{\\text{cum}}$ strictly accumulates.\n")

    rep.append("### Cumulative Trial Ledger Progression:")
    rep.append("- Baseline Cumulative Trials: **`M_cum = 18`** (M63 Family 1–4, M64 Synthesis, M65 Risk Parity, M67 Funding Carry, M72 S4 Asymmetric Shorting).")
    rep.append("- **H1 (`H1_VOL_SQUEEZE_EXPANSION_LONG`):** Trial index **19** ($M_{\\text{cum}} = 19$).")
    rep.append("- **H2 (`H2_CROSS_ASSET_RV_PAIR`):** Trial index **20** ($M_{\\text{cum}} = 20$).")
    rep.append("- **H3 (`H3_POST_CRASH_LIQ_REBOUND`):** Trial index **21** ($M_{\\text{cum}} = 21$).\n")
    rep.append("---\n")

    rep.append("## 2. SIDE-BY-SIDE SCORECARD: TRAIN / VAL / SEALED OOS\n")
    rep.append("| Metric | H1 (Vol Squeeze Breakout) | H2 (Cross-Asset RV Pair) | H3 (Post-Crash Liq Rebound) | Equal-Weight BnH |")
    rep.append("|:---|:---:|:---:|:---:|:---:|")

    h1 = results["hypotheses"]["H1_VOL_SQUEEZE_EXPANSION_LONG"]
    h2 = results["hypotheses"]["H2_CROSS_ASSET_RV_PAIR"]
    h3 = results["hypotheses"]["H3_POST_CRASH_LIQ_REBOUND"]
    bnh_oos = h1["splits_scorecard"]["sealed_oos"]["bnh"]

    rep.append(f"| **Direction Mode** | `{h1['direction_mode']}` | `{h2['direction_mode']}` | `{h3['direction_mode']}` | Long-Only Beta |")
    rep.append(f"| **Trial Number (M_cum)** | `{h1['m_cum']}` | `{h2['m_cum']}` | `{h3['m_cum']}` | — |")
    rep.append(f"| **Train Return %** | {h1['splits_scorecard']['train']['strategy']['total_return_pct']:+.2f}% | {h2['splits_scorecard']['train']['strategy']['total_return_pct']:+.2f}% | {h3['splits_scorecard']['train']['strategy']['total_return_pct']:+.2f}% | {h1['splits_scorecard']['train']['bnh']['total_return_pct']:+.2f}% |")
    rep.append(f"| **Train Sharpe** | {h1['splits_scorecard']['train']['strategy']['daily_mtm_sharpe']:.2f} | {h2['splits_scorecard']['train']['strategy']['daily_mtm_sharpe']:.2f} | {h3['splits_scorecard']['train']['strategy']['daily_mtm_sharpe']:.2f} | {h1['splits_scorecard']['train']['bnh']['daily_mtm_sharpe']:.2f} |")
    rep.append(f"| **Validation Return %** | {h1['splits_scorecard']['val']['strategy']['total_return_pct']:+.2f}% | {h2['splits_scorecard']['val']['strategy']['total_return_pct']:+.2f}% | {h3['splits_scorecard']['val']['strategy']['total_return_pct']:+.2f}% | {h1['splits_scorecard']['val']['bnh']['total_return_pct']:+.2f}% |")
    rep.append(f"| **Validation Sharpe** | {h1['splits_scorecard']['val']['strategy']['daily_mtm_sharpe']:.2f} | {h2['splits_scorecard']['val']['strategy']['daily_mtm_sharpe']:.2f} | {h3['splits_scorecard']['val']['strategy']['daily_mtm_sharpe']:.2f} | {h1['splits_scorecard']['val']['bnh']['daily_mtm_sharpe']:.2f} |")
    rep.append(f"| **Sealed OOS Return %** | **{h1['splits_scorecard']['sealed_oos']['strategy']['total_return_pct']:+.2f}%** | **{h2['splits_scorecard']['sealed_oos']['strategy']['total_return_pct']:+.2f}%** | **{h3['splits_scorecard']['sealed_oos']['strategy']['total_return_pct']:+.2f}%** | **{bnh_oos['total_return_pct']:+.2f}%** |")
    rep.append(f"| **Sealed OOS Sharpe** | **{h1['splits_scorecard']['sealed_oos']['strategy']['daily_mtm_sharpe']:.2f}** | **{h2['splits_scorecard']['sealed_oos']['strategy']['daily_mtm_sharpe']:.2f}** | **{h3['splits_scorecard']['sealed_oos']['strategy']['daily_mtm_sharpe']:.2f}** | **{bnh_oos['daily_mtm_sharpe']:.2f}** |")
    rep.append(f"| **Sealed OOS CAGR %** | {h1['splits_scorecard']['sealed_oos']['strategy']['cagr_pct']:+.2f}% | {h2['splits_scorecard']['sealed_oos']['strategy']['cagr_pct']:+.2f}% | {h3['splits_scorecard']['sealed_oos']['strategy']['cagr_pct']:+.2f}% | {bnh_oos['cagr_pct']:+.2f}% |")
    rep.append(f"| **Sealed OOS Max DD %** | {h1['splits_scorecard']['sealed_oos']['strategy']['max_drawdown_pct']:.2f}% | {h2['splits_scorecard']['sealed_oos']['strategy']['max_drawdown_pct']:.2f}% | {h3['splits_scorecard']['sealed_oos']['strategy']['max_drawdown_pct']:.2f}% | {bnh_oos['max_drawdown_pct']:.2f}% |")
    rep.append(f"| **Win Rate %** | {h1['trade_metrics']['win_rate_pct']:.1f}% | — (Pair) | {h3['trade_metrics']['win_rate_pct']:.1f}% | — |")
    rep.append(f"| **Profit Factor** | {h1['trade_metrics']['profit_factor']:.2f} | — (Pair) | {h3['trade_metrics']['profit_factor']:.2f} | — |")
    rep.append(f"| **Total Closed Trades** | {h1['trade_metrics']['total_trades']} | {h2['trade_metrics']['total_trades']} rebalances | {h3['trade_metrics']['total_trades']} | — |")
    rep.append(f"| **CPCV Median Sharpe** | {h1['statistical_rigor']['cpcv_median_sharpe']:.2f} | {h2['statistical_rigor']['cpcv_median_sharpe']:.2f} | {h3['statistical_rigor']['cpcv_median_sharpe']:.2f} | — |")
    rep.append(f"| **Cumulative DSR** | **{h1['statistical_rigor']['dsr_oos']:.4f}** (p={h1['statistical_rigor']['pval_oos']:.4f}) | **{h2['statistical_rigor']['dsr_oos']:.4f}** (p={h2['statistical_rigor']['pval_oos']:.4f}) | **{h3['statistical_rigor']['dsr_oos']:.4f}** (p={h3['statistical_rigor']['pval_oos']:.4f}) | — |")
    rep.append(f"| **CP-2 Hurdles Passed** | **{h1['hurdle_summary']['passed_count']}/6** | **{h2['hurdle_summary']['passed_count']}/6** | **{h3['hurdle_summary']['passed_count']}/6** | — |")
    rep.append(f"| **Epistemic Verdict** | **`{h1['epistemic_verdict']}`** | **`{h2['epistemic_verdict']}`** | **`{h3['epistemic_verdict']}`** | — |")
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
            max_gross_exposure=h_res.get("cp2_hurdles", {}).get("hurdle_6_zero_leverage_invariant", {}).get("max_gross_exposure", 1.0),
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


def run_m75_benchmark() -> dict[str, Any]:
    """Executes the full Milestone 75 Discovery Lab Benchmark across H1, H2, and H3."""
    logger.info("=== STARTING MILESTONE 75: UNIFIED HISTORICAL STRATEGY DISCOVERY LAB ===")
    start_time = time.time()

    ledger_manager = TrialLedgerManager()
    engine = CausalDiscoveryEngine(ledger_manager=ledger_manager)

    hypotheses: list[Any] = [
        H1_VolSqueezeExpansionLong(),
        H2_CrossAssetRvPair(),
        H3_PostCrashLiqRebound(),
    ]

    results_by_hyp: dict[str, Any] = {}

    for hyp in hypotheses:
        spec = hyp.spec()
        logger.info(f"Evaluating {spec.hypothesis_id}...")
        res = engine.evaluate_hypothesis(hyp)
        results_by_hyp[spec.hypothesis_id] = res

    elapsed = time.time() - start_time
    logger.info(f"Milestone 75 benchmark completed in {elapsed:.2f} seconds.")

    final_payload = {
        "milestone": "M75",
        "evaluation_timestamp_utc": datetime.now(UTC).isoformat(),
        "total_runtime_seconds": round(elapsed, 2),
        "baseline_m_cum": BASELINE_M_CUM,
        "final_m_cum": ledger_manager.get_current_m_cum(),
        "hypotheses": results_by_hyp,
    }

    # Persist JSON output
    out_json = ROOT_DIR / "research" / "m75_discovery_lab_results.json"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(final_payload, f, indent=2, cls=NumpyJSONEncoder)
    logger.info(f"Results written to {out_json}")

    # Generate Markdown Report
    out_md = ROOT_DIR / "docs" / "research" / "M75_DISCOVERY_LAB_REPORT.md"
    format_markdown_report(final_payload, out_md)

    # Console Scorecard
    print("\n" + "=" * 80)
    print("MILESTONE 75: STRATEGY DISCOVERY LAB SCORECARD (M_cum = 18 -> 21)")
    print("=" * 80)
    for hid, res in results_by_hyp.items():
        sh_oos = res["splits_scorecard"]["sealed_oos"]["strategy"]["daily_mtm_sharpe"]
        ret_oos = res["splits_scorecard"]["sealed_oos"]["strategy"]["total_return_pct"]
        dd_oos = res["splits_scorecard"]["sealed_oos"]["strategy"]["max_drawdown_pct"]
        dsr = res["statistical_rigor"]["dsr_oos"]
        passed = res["hurdle_summary"]["passed_count"]
        verdict = res["epistemic_verdict"]
        m_cum = res["m_cum"]

        print(f"[*] {hid} (Trial #{m_cum}):")
        print(f"    - Sealed OOS Return : {ret_oos:+.2f}% | Sharpe: {sh_oos:.2f} | Max DD: {dd_oos:.2f}%")
        print(f"    - Cumulative DSR    : {dsr:.4f} (p={res['statistical_rigor']['pval_oos']:.4f})")
        print(f"    - CP-2 Hurdles      : {passed}/6 PASS")
        print(f"    - Epistemic Verdict : {verdict}")
        print(f"    - Rationale         : {res['verdict_rationale']}")
        print("-" * 80)

    return final_payload


if __name__ == "__main__":
    run_m75_benchmark()
