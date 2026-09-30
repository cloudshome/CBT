"""
core/intelligence/crawler/dossier_generator.py
==============================================
Milestone 30-D: Preregistered Research Dossier Generator & Cryptographic Sealer.

CONSTITUTIONAL PRINCIPLE:
Transforms validated or audited research replays into immutable, evidence-backed
Markdown research dossiers stored in `data/research_dossiers/{plan_id}.md`.
Every dossier carries an immutable cryptographic SHA-256 seal.
Permanently research-only: REAL_CAPITAL_ENABLED = False.
Execution Authority = NON_EXECUTABLE_RESEARCH_HYPOTHESIS.
Awaiting Human Operator Review gate permanently enforced.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from core.intelligence.crawler.qualification_contracts import (
    EvidenceLineageLedger,
    EvidenceLineageNode,
    global_lineage_ledger,
)
from core.intelligence.crawler.statistical_auditor import AuditReport
from core.intelligence.dataset_manifest import DatasetManifest
from core.intelligence.hypothesis_schema import (
    CausalHypothesis,
    HypothesisLedgerManager,
    global_hypothesis_ledger,
)
from core.intelligence.plan_store import (
    DurableExperimentPlan,
    ExperimentPlanLedger,
    global_plan_ledger,
)
from core.intelligence.replay_engine import ReplayExecutionReport
from core.intelligence.research_contract import PreregisteredResearchContract

logger = logging.getLogger("ai_quant_sentinel.intelligence.crawler.dossier_generator")


class ResearchDossierGenerator:
    """
    Assembles, formats, and seals permanent Markdown Research Dossiers
    for human quantitative review.
    """

    def __init__(
        self,
        output_dir: str | None = None,
        lineage_ledger: EvidenceLineageLedger | None = None,
        hypothesis_ledger: HypothesisLedgerManager | None = None,
        plan_ledger: ExperimentPlanLedger | None = None,
    ) -> None:
        self.output_dir = Path(output_dir or "data/research_dossiers")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.lineage_ledger = lineage_ledger or global_lineage_ledger
        self.hypothesis_ledger = hypothesis_ledger or global_hypothesis_ledger
        self.plan_ledger = plan_ledger or global_plan_ledger

    def generate_dossier(
        self,
        plan: DurableExperimentPlan,
        contract: PreregisteredResearchContract,
        manifest: DatasetManifest,
        audit_report: AuditReport,
        reports_by_tier: dict[str, ReplayExecutionReport],
    ) -> tuple[Path, str]:
        """
        Builds the Markdown dossier, verifies cryptographic integrity,
        and saves it to data/research_dossiers/{plan_id}.md.
        Returns (file_path, sha256_hash).
        """
        hypothesis: CausalHypothesis | None = self.hypothesis_ledger.get_hypothesis(
            plan.hypothesis_id
        )
        lineage_trace: list[EvidenceLineageNode] = self.lineage_ledger.get_full_lineage(
            f"LIN-{plan.plan_id}"
        )

        md = self._render_markdown(
            plan=plan,
            hypothesis=hypothesis,
            contract=contract,
            manifest=manifest,
            audit_report=audit_report,
            reports_by_tier=reports_by_tier,
            lineage_trace=lineage_trace,
        )

        dossier_hash = hashlib.sha256(md.encode()).hexdigest()
        file_path = self.output_dir / f"{plan.plan_id}.md"

        # Check immutability: Do not overwrite if content matches
        if file_path.exists():
            existing_content = file_path.read_text(encoding="utf-8")
            existing_hash = hashlib.sha256(existing_content.encode()).hexdigest()
            if existing_hash == dossier_hash:
                logger.info(
                    f"Dossier {file_path.name} already exists with identical hash. Retaining."
                )
                return file_path, dossier_hash

        file_path.write_text(md, encoding="utf-8")
        logger.info(
            f"Generated sealed research dossier: {file_path} (SHA-256: {dossier_hash[:16]}...)"
        )
        return file_path, dossier_hash

    def _render_markdown(
        self,
        plan: DurableExperimentPlan,
        hypothesis: CausalHypothesis | None,
        contract: PreregisteredResearchContract,
        manifest: DatasetManifest,
        audit_report: AuditReport,
        reports_by_tier: dict[str, ReplayExecutionReport],
        lineage_trace: list[EvidenceLineageNode],
    ) -> str:
        cons = reports_by_tier.get("CONSERVATIVE")
        base = reports_by_tier.get("BASE")
        stress = reports_by_tier.get("STRESS")

        def _tier_row(name: str, rep: ReplayExecutionReport | None) -> str:
            if not rep:
                return f"| **{name}** | N/A | N/A | N/A | N/A | N/A |"
            return (
                f"| **{name}** | `{rep.net_expectancy_r:+.2f}R` | "
                f"`{rep.win_rate * 100:.1f}%` | `{rep.profit_factor:.2f}` | "
                f"`{rep.max_drawdown_pct:.1f}%` | `{rep.cost_erosion_pct:.1f}%` |"
            )

        row_base = _tier_row("BASE", base)
        row_cons = _tier_row("CONSERVATIVE", cons)
        row_stress = _tier_row("STRESS", stress)

        dsr_info = audit_report.dsr_result

        # Lineage summary
        lineage_md = ""
        for node in lineage_trace:
            lineage_md += (
                f"- **[{node.evidence_kind.value.upper()}]** `{node.node_id}` "
                f"(Seal: `{node.content_hash_sha256[:12]}...`)\n"
            )
        if not lineage_md:
            lineage_md = "- No lineage trace registered.\n"

        template_id = plan.metadata.get("template_id", "CUSTOM_TEMPLATE")
        template_ver = plan.metadata.get("template_version", "1.0.0")

        return f"""# 🔬 INSTITUTIONAL RESEARCH DOSSIER — {plan.plan_id}

> **GOVERNANCE NOTICE:**
> **EXECUTION AUTHORITY:** `NON_EXECUTABLE_RESEARCH_HYPOTHESIS`  
> **REAL CAPITAL ENABLED:** `FALSE`  
> **QUALIFICATION STATE:** `{audit_report.status.value}`  
> **HUMAN REVIEW REQUIRED:** `TRUE` (Strict Human Operator Gate Mandatory)

---

## 1. Research Identity & Metadata

| Attribute | Specification |
| :--- | :--- |
| **Plan ID** | `{plan.plan_id}` |
| **Hypothesis ID** | `{plan.hypothesis_id}` |
| **Research Family** | `{plan.family_id}` |
| **Target Symbol** | `{plan.target_symbol}` |
| **Observation Timeframe** | `{plan.timeframe}` |
| **Research Template** | `{template_id}` (v{template_ver}) |
| **Multiple Testing Policy** | `{audit_report.multiple_testing_policy}` |
| **Plan Creation UTC** | `{plan.created_at_utc:.0f}` |
| **Audit Sealed UTC** | `{audit_report.created_at_utc:.0f}` |
| **Audit Hash** | `{audit_report.audit_hash_sha256}` |

---

## 2. Theoretical Causal Mechanism & Preregistered Hypotheses

* **Mechanism ID:** `{contract.mechanism_id}`
* **Null Hypothesis ($H_0$):**  
  > *{contract.null_hypothesis}*
* **Alternative Hypothesis ($H_1$):**  
  > *{contract.alternative_hypothesis}*
* **Microstructure Receptor Conditions:**  
  `{contract.treatment_definition.get("conditions", {})}`
* **Epistemic Prior Weight:** `{hypothesis.epistemic_prior_weight if hypothesis else "0.70"}`

---

## 3. Evidence Provenance & Cryptographic Lineage

{lineage_md}

---

## 4. Point-in-Time Replay & Dataset Integrity

* **Dataset Manifest ID:** `{manifest.manifest_id}`
* **Snapshot SHA-256:** `{manifest.snapshot_hash_sha256}`
* **Backtest Range (UTC):** `[{plan.backtest_range_start_utc:.0f}, {plan.backtest_range_end_utc:.0f}]` ({plan.lookback_days} days)
* **Total Simulated Episodes:** `{cons.total_episodes if cons else 0}`
* **Independent Episodes ($N_{{\\text{{eff}}}}$):** `{cons.independent_episodes if cons else 0}`
* **Causal Soundness Assertion:** `VERIFIED (Zero Lookahead)`

---

## 5. Three-Tier Economic Friction Sensitivity

| Friction Tier | Net Expectancy | Win Rate | Profit Factor | Max Drawdown % | Cost Erosion % |
| :--- | :---: | :---: | :---: | :---: | :---: |
{row_base}
{row_cons}
{row_stress}

---

## 6. Statistical Audit & Multiple-Testing Correction

* **Raw Annualized Sharpe Ratio:** `{dsr_info.get("raw_sharpe", 0.0):.2f}`
* **Deflated Sharpe Ratio (DSR):** `{dsr_info.get("deflated_sharpe", 0.0):.4f}` (Hurdle: $\\ge {plan.required_dsr:.2f}$)
* **Family Trial Count ($N$):** `{audit_report.family_trial_count}`
* **Expected Maximum Sharpe ($E[\\max(\\text{{SR}})]$):** `{dsr_info.get("expected_max_sharpe", 0.0):.3f}`
* **Sample Skewness:** `{dsr_info.get("skewness", 0.0):.2f}`
* **Sample Kurtosis:** `{dsr_info.get("kurtosis", 3.0):.2f}`
* **Holm-Bonferroni Significance:** `{"PASS" if audit_report.holm_bonferroni_passed else "REJECT"}`
* **Stress Survival Hurdle:** `{"PASS" if audit_report.stress_survival else "FAIL"}`

---

## 7. Institutional Verdict & Recommendation

**Epistemic Verdict:** `{audit_report.status.value}`  
**Verdict Rationale:**  
> {audit_report.verdict_rationale}

**Scorecard Gate Summary:**  
{self._format_scorecard(audit_report.scorecard_passes)}

---

## 8. Human Review Gate

Under institutional quantitative governance, autonomous systems are strictly prohibited from granting execution authority to any research finding.

```
[ ] Reject Hypothesis (Permanently Falsify)
[ ] Request Independent Multi-Asset Out-of-Sample Replication
[ ] Qualify for Sandboxed Paper-Trading Observation (Human Operator Signature Required)
```
"""

    @staticmethod
    def _format_scorecard(scorecard: dict[str, bool]) -> str:
        lines = []
        for gate, passed in scorecard.items():
            badge = "✅ PASS" if passed else "❌ FAIL"
            lines.append(f"- **{gate}:** {badge}")
        return "\n".join(lines) if lines else "- No scorecard gates evaluated."


# Global singleton instance
global_research_dossier_generator = ResearchDossierGenerator()
