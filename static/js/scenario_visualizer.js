/**
 * Competing Probabilistic Scenario Visualizer & Invalidation Watcher.
 */
class ScenarioVisualizer {
  constructor() {
    this.container = document.getElementById("scenario-container");
    this.invalConditionEl = document.getElementById("inval-condition-text");
    this.consensusPEl = document.getElementById("sim-consensus-p");
    this.uncertaintySpreadEl = document.getElementById("sim-uncertainty-spread");
    this.medianTargetEl = document.getElementById("sim-median-target");
  }

  updateScenarios(dist) {
    if (!dist || !dist.scenarios) return;

    const rows = dist.scenarios.map((s, idx) => {
      const colorClass = idx === 0 ? "bar-green" : (idx === 1 ? "bar-blue" : "bar-red");
      const pct = (s.probability * 100).toFixed(0);
      return `
        <div class="scenario-row">
          <span class="scen-name">${s.name}</span>
          <div class="progress-bar"><div class="bar-fill ${colorClass}" style="width: ${pct}%"></div></div>
          <span class="scen-pct">${pct}% ($${s.target_price?.toLocaleString()})</span>
        </div>
      `;
    }).join("");

    const barsContainer = this.container?.querySelector(".scenario-bars");
    if (barsContainer) {
      barsContainer.innerHTML = rows;
    }

    const domScenario = dist.scenarios.find((s) => s.scenario_id === dist.dominant_scenario_id) || dist.scenarios[0];
    if (this.invalConditionEl && domScenario) {
      this.invalConditionEl.innerText = domScenario.invalidation_condition;
    }
  }

  updateSimulation(sim) {
    if (!sim) return;
    if (this.consensusPEl) this.consensusPEl.innerText = `${(sim.p_tp_before_sl * 100).toFixed(1)}%`;
    if (this.uncertaintySpreadEl) this.uncertaintySpreadEl.innerText = `±${(sim.tp_sl_uncertainty_spread * 100).toFixed(1)}%`;
    if (this.medianTargetEl && sim.p50_median_path?.length) {
      const finalTarget = sim.p50_median_path[sim.p50_median_path.length - 1];
      this.medianTargetEl.innerText = `$${finalTarget.toLocaleString()}`;
    }
  }
}

window.scenarioVisualizer = new ScenarioVisualizer();
