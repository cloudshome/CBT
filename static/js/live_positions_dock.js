class LivePositionsDock {
  constructor() {
    this.tableBody = document.getElementById("shadow-positions-body");
    this.heatLabel = document.getElementById("portfolio-heat-label");
    this.btnReset = document.getElementById("btn-reset-positions");

    if (this.btnReset) {
      this.btnReset.addEventListener("click", () => this.resetPositions());
    }
  }

  async refresh() {
    try {
      const res = await fetch("/api/shadow/positions");
      const data = await res.json();
      this.renderTable(data.open_positions || [], data.history || []);
    } catch (e) {
      console.error("Failed loading shadow positions:", e);
    }
  }

  async closePosition(posId) {
    if (!confirm(`Are you sure you want to close position ${posId}?`)) return;
    try {
      const res = await fetch("/api/shadow/close", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ position_id: posId }),
      });
      const data = await res.json();
      if (data.status === "SUCCESS") {
        this.refresh();
      }
    } catch (e) {
      console.error("Failed to close position:", e);
    }
  }

  async resetPositions() {
    if (!confirm("Clear all shadow positions and reset trade ledger?")) return;
    try {
      const res = await fetch("/api/shadow/reset", { method: "POST" });
      const data = await res.json();
      if (data.status === "SUCCESS") {
        this.refresh();
      }
    } catch (e) {
      console.error("Failed to reset positions:", e);
    }
  }

  renderTable(openPositions, history) {
    if (!this.tableBody) return;

    // Calculate dynamic portfolio heat
    let totalRiskUsd = 0;
    openPositions.forEach((p) => {
      const riskPerUnit = Math.abs(p.entry_price - p.stop_loss);
      totalRiskUsd += riskPerUnit * p.size;
    });
    const equity = parseFloat(document.getElementById("dock-equity")?.value || "100000");
    const heatPct = (totalRiskUsd / equity) * 100;
    if (this.heatLabel) {
      this.heatLabel.innerText = `Total Heat: ${heatPct.toFixed(2)}% / 6.0% Max`;
      this.heatLabel.style.color = heatPct > 6.0 ? "var(--accent-red)" : (heatPct > 3.0 ? "var(--accent-yellow)" : "var(--text-main)");
    }

    if (openPositions.length === 0 && history.length === 0) {
      this.tableBody.innerHTML = `<tr><td colspan="11" class="text-center" style="padding:18px; color:var(--text-dim);">No active shadow positions. Execute order above to mirror.</td></tr>`;
      return;
    }

    const allRows = [...openPositions, ...history.slice(0, 15)];
    this.tableBody.innerHTML = allRows.map((pos) => {
      const isLong = pos.direction === "LONG";
      const pnl = pos.status === "OPEN" ? pos.unrealized_pnl : pos.realized_pnl;
      const pnlColor = pnl >= 0 ? "var(--accent-green)" : "var(--accent-red)";
      const sideClass = isLong ? "tag-green" : "tag-red";
      const beBadge = pos.breakeven_triggered ? `<span class="badge-tag tag-purple">✓ Breakeven (+1.5R)</span>` : `<span style="color:var(--text-dim)">Trailing active</span>`;
      
      const actionCell = pos.status === "OPEN"
        ? `<button class="btn-small" style="background:var(--accent-red); padding:3px 8px; font-size:10px;" onclick="window.livePositionsDock.closePosition('${pos.position_id}')">Close</button>`
        : `<span class="badge-tag ${pos.status === 'CLOSED' ? 'tag-green' : 'tag-red'}">${pos.status}</span>`;

      return `
        <tr>
          <td><code title="${pos.position_id}">${pos.position_id.substring(0, 16)}...</code></td>
          <td><strong>${pos.symbol}</strong></td>
          <td><span class="badge-tag ${sideClass}">${pos.direction}</span></td>
          <td>${pos.size}</td>
          <td>$${pos.entry_price?.toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
          <td>$${pos.current_price?.toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
          <td>$${pos.stop_loss?.toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
          <td>$${pos.take_profit?.toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
          <td style="color: ${pnlColor}; font-weight:700;">${pnl >= 0 ? "+" : ""}$${pnl?.toFixed(2)}</td>
          <td>${beBadge}</td>
          <td>${actionCell}</td>
        </tr>
      `;
    }).join("");
  }
}

window.livePositionsDock = new LivePositionsDock();
