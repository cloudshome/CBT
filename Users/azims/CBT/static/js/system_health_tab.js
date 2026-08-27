/**
 * System Drift, API Health & Governed Hot-Reload Proposals.
 */
class SystemHealthTab {
  constructor() {
    this.driftContainer = document.getElementById("drift-status-container");
    this.apiContainer = document.getElementById("api-vitals-container");
    this.proposalsContainer = document.getElementById("proposals-container");
  }

  async refresh() {
    try {
      const res = await fetch("/api/health");
      const healthData = await res.json();
      this.renderHealth(healthData);

      const propRes = await fetch("/api/governance/proposals");
      const propData = await propRes.json();
      this.renderProposals(propData.proposals || []);
    } catch (e) {
      console.error("Failed loading system health:", e);
    }
  }

  renderHealth(data) {
    if (!data) return;

    // Render Drift Report
    const drift = data.drift_report || {};
    const dims = [drift.data_drift, drift.concept_drift, drift.performance_drift, drift.execution_drift].filter(Boolean);

    if (this.driftContainer) {
      this.driftContainer.innerHTML = dims.map((d) => `
        <div class="drift-row">
          <div>
            <strong>${d.dimension_name}</strong>
            <div style="font-size:10px; color:var(--text-dim);">${d.message}</div>
          </div>
          <div>
            <span class="badge-tag ${d.drift_detected ? "tag-red" : "tag-green"}">${d.drift_detected ? "DRIFT_ALERT" : "NOMINAL"}</span>
          </div>
        </div>
      `).join("");
    }

    // Render API Vitals
    const vitals = data.api_vitals || [];
    if (this.apiContainer) {
      this.apiContainer.innerHTML = vitals.map((v) => `
        <div class="drift-row">
          <div>
            <strong>${v.endpoint_name}</strong>
            <div style="font-size:10px; color:var(--text-dim);">Latency: ${v.current_latency_ms}ms | Rate Limit Usage: ${v.rate_limit_usage_pct}%</div>
          </div>
          <div>
            <span class="badge-tag ${v.status === "HEALTHY" ? "tag-green" : "tag-yellow"}">${v.status}</span>
          </div>
        </div>
      `).join("");
    }
  }

  renderProposals(proposals) {
    if (!this.proposalsContainer) return;

    if (proposals.length === 0) {
      this.proposalsContainer.innerHTML = `<p style="color:var(--text-dim); font-size:11px;">No parameter adaptation proposals awaiting review.</p>`;
      return;
    }

    this.proposalsContainer.innerHTML = proposals.map((p) => `
      <div style="padding:10px; background:var(--bg-panel); border-radius:6px; border:1px solid var(--border-color); display:flex; flex-direction:column; gap:6px;">
        <div style="display:flex; justify-content:space-between; font-weight:700;">
          <span>${p.proposal_id}: ${p.parameter_name}</span>
          <span style="color:var(--accent-purple)">${p.current_value} ➔ ${p.proposed_value}</span>
        </div>
        <div style="font-size:11px; color:var(--text-muted);">${p.rationale}</div>
        <div style="font-size:10px; color:var(--text-dim);">OOS Stability: ${(p.simulated_oos_stability * 100).toFixed(0)}% | Exp. Sharpe Gain: +${p.expected_sharpe_improvement}</div>
        <div style="display:flex; gap:8px; margin-top:4px;">
          <button class="btn-small" style="background:var(--accent-green)" onclick="systemHealthTab.approveProposal('${p.proposal_id}')">✓ Approve & Hot-Reload</button>
          <button class="btn-small" style="background:var(--accent-red)" onclick="systemHealthTab.rejectProposal('${p.proposal_id}')">✗ Reject</button>
        </div>
      </div>
    `).join("");
  }

  async approveProposal(id) {
    try {
      const res = await fetch("/api/governance/approve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ proposal_id: id }),
      });
      const data = await res.json();
      alert(data.message || "Proposal approved.");
      this.refresh();
    } catch (e) {
      alert("Failed to approve proposal.");
    }
  }

  async rejectProposal(id) {
    alert(`Rejected proposal ${id}`);
    this.refresh();
  }
}

window.systemHealthTab = new SystemHealthTab();
