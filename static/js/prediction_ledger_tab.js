/**
 * Prediction Ledger Table & Probability Calibration Scorecard.
 */
class PredictionLedgerTab {
  constructor() {
    this.tableBody = document.getElementById("prediction-ledger-body");
    this.chartCanvas = document.getElementById("calibration-canvas");
    this.brierBadge = document.getElementById("brier-score-badge");
    this.btnRefresh = document.getElementById("btn-refresh-ledger");
    this.chart = null;

    if (this.btnRefresh) {
      this.btnRefresh.addEventListener("click", () => this.refresh());
    }
  }

  async refresh() {
    try {
      const res = await fetch("/api/prediction/ledger?limit=25");
      const data = await res.json();
      this.renderTable(data.records || []);

      const symbol = document.getElementById("asset-selector")?.value || "BTC/USDT";
      const calRes = await fetch(`/api/prediction/calibration?symbol=${encodeURIComponent(symbol)}`);
      const calData = await calRes.json();
      this.renderCalibrationChart(calData);
    } catch (e) {
      console.error("Failed loading prediction ledger:", e);
    }
  }

  renderTable(records) {
    if (!this.tableBody) return;
    if (records.length === 0) {
      this.tableBody.innerHTML = `<tr><td colspan="9" class="text-center">No predictions logged yet. Predictions freeze automatically upon analysis.</td></tr>`;
      return;
    }

    this.tableBody.innerHTML = records.map((r) => {
      const dt = new Date(r.timestamp).toLocaleString();
      const statusClass = r.is_verified ? (r.outcome_1h === "WIN" ? "tag-green" : "tag-red") : "tag-blue";
      const statusLabel = r.is_verified ? r.outcome_1h : "PENDING_RESOLUTION";
      return `
        <tr>
          <td><code>${r.prediction_id}</code></td>
          <td>${dt}</td>
          <td><strong>${r.symbol}</strong> (${r.timeframe})</td>
          <td>${(r.confidence * 100).toFixed(0)}%</td>
          <td>${r.outcome_5m || "—"}</td>
          <td>${r.outcome_1h || "—"}</td>
          <td>${r.outcome_4h || "—"}</td>
          <td>${r.brier_score !== null ? r.brier_score.toFixed(4) : "—"}</td>
          <td><span class="badge-tag ${statusClass}">${statusLabel}</span></td>
        </tr>
      `;
    }).join("");
  }

  renderCalibrationChart(calData) {
    if (!this.chartCanvas || typeof Chart === "undefined" || !calData) return;

    if (this.brierBadge) {
      this.brierBadge.innerText = `Brier Score: ${calData.brier_score.toFixed(3)} (${calData.is_well_calibrated ? "Well-Calibrated" : "Miscalibrated"})`;
      this.brierBadge.className = `badge-tag ${calData.is_well_calibrated ? "tag-green" : "tag-yellow"}`;
    }

    const bins = calData.reliability_bins || [];
    const labels = bins.map((b) => `${(b.bin_center * 100).toFixed(0)}%`);
    const observed = bins.map((b) => b.observed_frequency * 100);
    const perfect = bins.map((b) => b.bin_center * 100);

    if (this.chart) {
      this.chart.destroy();
    }

    this.chart = new Chart(this.chartCanvas, {
      type: "line",
      data: {
        labels: labels,
        datasets: [
          {
            label: "Observed Realized Frequency",
            data: observed,
            borderColor: "#10b981",
            backgroundColor: "rgba(16, 185, 129, 0.2)",
            borderWidth: 2,
            pointRadius: 4,
          },
          {
            label: "Perfect Calibration (Diagonal)",
            data: perfect,
            borderColor: "rgba(148, 163, 184, 0.5)",
            borderDash: [5, 5],
            borderWidth: 1.5,
            pointRadius: 0,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { labels: { color: "#94a3b8", font: { family: "'JetBrains Mono'" } } },
        },
        scales: {
          x: {
            title: { display: true, text: "Forecast Probability", color: "#64748b" },
            ticks: { color: "#94a3b8" },
            grid: { color: "rgba(39, 49, 66, 0.4)" },
          },
          y: {
            title: { display: true, text: "Empirical Win Rate (%)", color: "#64748b" },
            ticks: { color: "#94a3b8" },
            grid: { color: "rgba(39, 49, 66, 0.4)" },
            min: 0,
            max: 100,
          },
        },
      },
    });
  }
}

window.predictionLedgerTab = new PredictionLedgerTab();
