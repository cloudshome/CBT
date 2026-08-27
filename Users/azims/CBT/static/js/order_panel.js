/**
 * Order Execution Panel & Conservative Kelly Calculator.
 */
class OrderPanel {
  constructor() {
    this.equityInput = document.getElementById("dock-equity");
    this.kellyRiskLabel = document.getElementById("dock-kelly-risk");
    this.unitsLabel = document.getElementById("dock-units");
    this.entryInput = document.getElementById("order-entry");
    this.slInput = document.getElementById("order-sl");
    this.tpInput = document.getElementById("order-tp");

    this.btnBuy = document.getElementById("btn-dock-buy");
    this.btnSell = document.getElementById("btn-dock-sell");
    this.btnAutoFill = document.getElementById("btn-ai-autofill");

    this.bindEvents();
  }

  bindEvents() {
    if (this.equityInput) {
      this.equityInput.addEventListener("input", () => this.recalculate());
    }
    if (this.entryInput) {
      this.entryInput.addEventListener("input", () => this.recalculate());
    }
    if (this.slInput) {
      this.slInput.addEventListener("input", () => this.recalculate());
    }

    if (this.btnBuy) {
      this.btnBuy.addEventListener("click", () => this.submitOrder("LONG"));
    }
    if (this.btnSell) {
      this.btnSell.addEventListener("click", () => this.submitOrder("SHORT"));
    }
    if (this.btnAutoFill) {
      this.btnAutoFill.addEventListener("click", () => this.autofillSetup());
    }
  }

  async autofillSetup() {
    const symbol = document.getElementById("asset-selector")?.value || "BTC/USDT";
    try {
      const res = await fetch(`/api/scenarios?symbol=${encodeURIComponent(symbol)}`);
      const data = await res.json();
      const domScen = data.scenarios?.find((s) => s.scenario_id === data.dominant_scenario_id) || data.scenarios?.[0];

      if (domScen) {
        const curP = data.current_price;
        const inval = domScen.invalidation_price;
        const target = domScen.target_price;

        if (this.entryInput) this.entryInput.value = curP.toFixed(2);
        if (this.slInput) this.slInput.value = inval.toFixed(2);
        if (this.tpInput) this.tpInput.value = target.toFixed(2);
        this.recalculate();
      }
    } catch (e) {
      console.error("Autofill failed:", e);
    }
  }

  recalculate() {
    const equity = parseFloat(this.equityInput?.value || "100000");
    const entry = parseFloat(this.entryInput?.value || "88500");
    const sl = parseFloat(this.slInput?.value || "87200");

    const riskPerUnit = Math.abs(entry - sl);
    const riskPct = 0.0075; // 0.75% default conservative Kelly fraction
    const riskUsd = equity * riskPct;

    const units = riskPerUnit > 0 ? riskUsd / riskPerUnit : 0;
    const notional = units * entry;

    if (this.kellyRiskLabel) {
      this.kellyRiskLabel.innerText = `${(riskPct * 100).toFixed(2)}% ($${riskUsd.toFixed(2)})`;
    }
    if (this.unitsLabel) {
      this.unitsLabel.innerText = `${units.toFixed(3)} Units ($${notional.toLocaleString(undefined, { maximumFractionDigits: 0 })})`;
    }
  }

  async submitOrder(direction) {
    const symbol = document.getElementById("asset-selector")?.value || "BTC/USDT";
    const entry = parseFloat(this.entryInput?.value || "0");
    const sl = parseFloat(this.slInput?.value || "0");
    const tp = parseFloat(this.tpInput?.value || "0");
    const equity = parseFloat(this.equityInput?.value || "100000");

    if (entry <= 0 || sl <= 0 || tp <= 0) {
      alert("Please specify valid Entry, Stop Loss, and Take Profit levels.");
      return;
    }

    const riskPerUnit = Math.abs(entry - sl);
    const size = (equity * 0.0075) / (riskPerUnit || 1);

    try {
      const resp = await fetch("/api/shadow/trade", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol: symbol,
          direction: direction,
          size: parseFloat(size.toFixed(4)),
          entry_price: entry,
          stop_loss: sl,
          take_profit: tp,
        }),
      });
      const data = await resp.json();
      if (data.status === "SUCCESS") {
        if (window.livePositionsDock) window.livePositionsDock.refresh();
        alert(`Order Executed! Position ID: ${data.position_id}`);
      }
    } catch (e) {
      console.error("Order submission failed:", e);
      alert("Failed to submit order.");
    }
  }
}

window.orderPanel = new OrderPanel();
