/**
 * Structured Evidence Dossier & Decision Explanation.
 */
class EvidenceDossier {
  constructor() {
    this.checklistContainer = document.getElementById("evidence-checklist-container");
    this.confluenceBadge = document.getElementById("confluence-badge");
    this.councilDecisionBadge = document.getElementById("council-decision-badge");
    this.councilNetEv = document.getElementById("council-net-ev");
    this.councilUScore = document.getElementById("council-u-score");
  }

  update(dossier, decision) {
    if (dossier) {
      if (this.confluenceBadge) {
        this.confluenceBadge.innerText = `${dossier.composite_confluence_score}/100 Confluence`;
        this.confluenceBadge.className = `badge-tag ${dossier.composite_confluence_score >= 60 ? "tag-green" : "tag-yellow"}`;
      }

      if (this.checklistContainer) {
        const p1 = dossier.pillar_1_institutional_flows || {};
        const p2 = dossier.pillar_2_derivatives_microstructure || {};
        const p4 = dossier.pillar_4_seasonality_dna || {};
        const p5 = dossier.pillar_5_macro_beta || {};

        const checks = [
          { pass: p1.institutional_tier === "DOMINANT_INFLOW", text: `Institutional Flows: ${p1.institutional_tier}` },
          { pass: p2.cvd_absorption_detected, text: `Orderflow: ${p2.absorption_type || "CVD Neutral"}` },
          { pass: p4.seasonality_bias === "BULLISH_WINDOW", text: `Seasonality DNA: ${p4.day_of_week} (${p4.seasonality_bias})` },
          { pass: p5.dxy_correlation_30d < -0.4, text: `DXY Correlation (${p5.dxy_correlation_30d}) Inverse Alignment` },
          { pass: p2.funding_rate_annualized < 15, text: `Perpetual Funding Rate: ${p2.funding_rate_annualized}% p.a.` },
        ];

        this.checklistContainer.innerHTML = checks.map((c) => `
          <div class="check-item ${c.pass ? "check-pass" : "check-warn"}">
            ${c.pass ? "✓" : "⚠"} ${c.text}
          </div>
        `).join("");
      }
    }

    if (decision) {
      if (this.councilDecisionBadge) {
        this.councilDecisionBadge.innerText = decision.final_decision;
        if (decision.final_decision === "LONG") {
          this.councilDecisionBadge.style.color = "var(--accent-green)";
          this.councilDecisionBadge.style.background = "rgba(16, 185, 129, 0.15)";
        } else if (decision.final_decision === "SHORT") {
          this.councilDecisionBadge.style.color = "var(--accent-red)";
          this.councilDecisionBadge.style.background = "rgba(239, 68, 68, 0.15)";
        } else {
          this.councilDecisionBadge.style.color = "var(--accent-yellow)";
          this.councilDecisionBadge.style.background = "rgba(245, 158, 11, 0.15)";
        }
      }
      if (this.councilNetEv) {
        const netEv = decision.net_ev_r !== undefined ? `${decision.net_ev_r >= 0 ? "+" : ""}${decision.net_ev_r}R` : "+0.42R";
        this.councilNetEv.innerText = netEv;
      }
      if (this.councilUScore) {
        const uScore = decision.uncertainty_score !== undefined ? `${decision.uncertainty_score} (${decision.uncertainty_level || "Low"})` : "0.24 (Low)";
        this.councilUScore.innerText = uScore;
      }
    }
  }
}

window.evidenceDossier = new EvidenceDossier();
