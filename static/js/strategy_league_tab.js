/**
 * Strategy Competition League & Quarantine Tier Leaderboard.
 */
class StrategyLeagueTab {
  constructor() {
    this.tableBody = document.getElementById("strategy-league-body");
  }

  async refresh() {
    try {
      const res = await fetch("/api/league/leaderboard");
      const data = await res.json();
      this.renderTable(data.leaderboard || []);
    } catch (e) {
      console.error("Failed loading strategy league:", e);
    }
  }

  renderTable(strategies) {
    if (!this.tableBody) return;

    this.tableBody.innerHTML = strategies.map((s) => {
      const tierLabel = s.quarantine_tier === 4 ? "Tier 4: Production League" :
                        (s.quarantine_tier === 3 ? "Tier 3: Robust Evaluation" :
                        (s.quarantine_tier === 2 ? "Tier 2: Preliminary Validation" : "Tier 1: Smoke Test"));
      const tierBadge = s.quarantine_tier === 4 ? "tag-green" : (s.quarantine_tier === 3 ? "tag-purple" : "tag-blue");

      return `
        <tr>
          <td><code>${s.dna_id}</code></td>
          <td><strong>${s.name}</strong></td>
          <td><span class="badge-tag ${tierBadge}">${tierLabel}</span></td>
          <td>${s.forward_trades_count}</td>
          <td>${(s.historical_win_rate * 100).toFixed(1)}%</td>
          <td><strong>${s.rolling_sharpe_30d?.toFixed(2)}</strong></td>
          <td>${s.rolling_net_ev_30d > 0 ? "+" : ""}${s.rolling_net_ev_30d?.toFixed(2)}R</td>
          <td>${(s.walk_forward_stability * 100).toFixed(0)}%</td>
          <td>${(s.monte_carlo_ruin_prob * 100).toFixed(2)}%</td>
          <td><strong style="color:var(--accent-purple)">${(s.allocation_weight * 100).toFixed(0)}%</strong></td>
        </tr>
      `;
    }).join("");
  }
}

window.strategyLeagueTab = new StrategyLeagueTab();
