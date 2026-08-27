/**
 * Master Frontend Controller & WebSocket Multiplexer.
 */
class AppController {
  constructor() {
    this.currentSymbol = "BTC/USDT";
    this.currentTimeframe = "15m";
    this.ws = null;

    this.initElements();
    this.bindEvents();
    this.connectWebSocket();
    this.loadInitialData();
  }

  initElements() {
    this.assetSelector = document.getElementById("asset-selector");
    this.tfButtons = document.querySelectorAll(".tf-btn");
    this.tabButtons = document.querySelectorAll(".tab-btn");
    this.tabViews = document.querySelectorAll(".tab-view");

    this.copilotInput = document.getElementById("copilot-input");
    this.copilotSendBtn = document.getElementById("copilot-send-btn");
    this.chatHistory = document.getElementById("mini-chat-history");

    this.btnRunBacktest = document.getElementById("btn-run-backtest");
    this.btnRunWalkForward = document.getElementById("btn-run-walk-forward");
    this.btnRunStressTest = document.getElementById("btn-run-stress-test");
    this.labOutput = document.getElementById("lab-results-output");
  }

  bindEvents() {
    // Asset change
    if (this.assetSelector) {
      this.assetSelector.addEventListener("change", (e) => {
        this.currentSymbol = e.target.value;
        const symLabel = document.getElementById("chart-symbol-label");
        if (symLabel) symLabel.innerText = this.currentSymbol;
        if (window.chartEngine) window.chartEngine.loadMemory(this.currentSymbol, this.currentTimeframe);
        this.refreshActiveView();
      });
    }

    // Timeframe change
    this.tfButtons.forEach((btn) => {
      btn.addEventListener("click", () => {
        this.tfButtons.forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        this.currentTimeframe = btn.getAttribute("data-tf") || "15m";
        if (window.chartEngine) window.chartEngine.loadMemory(this.currentSymbol, this.currentTimeframe);
        this.refreshActiveView();
      });
    });

    // SMC Indicator Toggles & Memory Persistence
    ["toggle-fvg", "toggle-ob", "toggle-sweeps", "toggle-cvd"].forEach((id) => {
      const el = document.getElementById(id);
      if (el) {
        el.addEventListener("change", () => {
          if (this.lastSmcPatterns && window.chartEngine) {
            window.chartEngine.drawSMCOverlays(this.lastSmcPatterns);
          }
          if (window.chartEngine) {
            window.chartEngine.saveMemory();
          }
        });
      }
    });

    // Tab switching
    this.tabButtons.forEach((btn) => {
      btn.addEventListener("click", () => {
        const targetTab = btn.getAttribute("data-tab");
        this.tabButtons.forEach((b) => b.classList.remove("active"));
        this.tabViews.forEach((v) => v.classList.remove("active"));

        btn.classList.add("active");
        document.getElementById(targetTab)?.classList.add("active");

        if (targetTab === "tab-ledger" && window.predictionLedgerTab) {
          window.predictionLedgerTab.refresh();
        } else if (targetTab === "tab-league" && window.strategyLeagueTab) {
          window.strategyLeagueTab.refresh();
        } else if (targetTab === "tab-health" && window.systemHealthTab) {
          window.systemHealthTab.refresh();
        }
      });
    });

    // Copilot Chat
    if (this.copilotSendBtn) {
      this.copilotSendBtn.addEventListener("click", () => this.sendCopilotMessage());
    }
    if (this.copilotInput) {
      this.copilotInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") this.sendCopilotMessage();
      });
    }

    // Research Lab Buttons
    if (this.btnRunBacktest) {
      this.btnRunBacktest.addEventListener("click", () => this.runLabTest("/api/lab/backtest"));
    }
    if (this.btnRunWalkForward) {
      this.btnRunWalkForward.addEventListener("click", () => this.runLabTest("/api/lab/walk-forward"));
    }
    if (this.btnRunStressTest) {
      this.btnRunStressTest.addEventListener("click", () => this.runLabTest("/api/lab/stress-test"));
    }
  }

  connectWebSocket() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws/terminal`;

    try {
      this.ws = new WebSocket(wsUrl);

      this.ws.onopen = () => {
        console.log("WebSocket connected to /ws/terminal");
      };

      this.ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if (msg.type === "TELEMETRY_TICK" && msg.symbol === this.currentSymbol) {
          const priceEl = document.getElementById("chart-price-live");
          if (priceEl) priceEl.innerText = `$${msg.current_price?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
          if (window.chartEngine) window.chartEngine.updateTick(msg.current_price, msg.timestamp);
          if (window.orderBookVisualizer) window.orderBookVisualizer.update(msg.current_price);
          if (window.macroTicker) window.macroTicker.update(msg.macro_vitals);
        } else if (msg.type === "POSITION_EVENT") {
          if (window.livePositionsDock) window.livePositionsDock.refresh();
        }
      };

      this.ws.onclose = () => {
        setTimeout(() => this.connectWebSocket(), 2000);
      };
    } catch (e) {
      console.warn("WebSocket fallback:", e);
    }

    // High-Reliability Live Ticker Poller (Every 2s)
    setInterval(async () => {
      try {
        const res = await fetch(`/api/market/ticker?symbol=${encodeURIComponent(this.currentSymbol)}`);
        const data = await res.json();
        if (data && data.price) {
          const priceEl = document.getElementById("chart-price-live");
          if (priceEl) priceEl.innerText = `$${data.price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
          if (window.chartEngine) window.chartEngine.updateTick(data.price, data.timestamp);
          if (window.orderBookVisualizer) window.orderBookVisualizer.update(data.price);
        }
      } catch (e) {
        // Fallback quiet
      }
    }, 2000);
  }

  async loadInitialData() {
    await this.refreshActiveView();
    if (window.livePositionsDock) window.livePositionsDock.refresh();
  }

  async refreshActiveView() {
    try {
      // 1. Fetch Candles
      const cRes = await fetch(`/api/market/candles?symbol=${encodeURIComponent(this.currentSymbol)}&timeframe=${this.currentTimeframe}&limit=100`);
      const cData = await cRes.json();
      if (window.chartEngine) window.chartEngine.setCandles(cData.candles);

      // 2. Fetch SMC Scans & Formations
      const smcRes = await fetch(`/api/smc/scan?symbol=${encodeURIComponent(this.currentSymbol)}&timeframe=${this.currentTimeframe}`);
      const smcData = await smcRes.json();
      this.lastSmcPatterns = smcData.smc_patterns;
      if (window.chartEngine) window.chartEngine.drawSMCOverlays(smcData.smc_patterns);
      const regLabel = document.getElementById("chart-regime-label");
      if (regLabel) regLabel.innerText = smcData.regime || "TRENDING_BULL";

      // 3. Fetch Dossier & Council Decision
      const dosRes = await fetch(`/api/market/dossier?symbol=${encodeURIComponent(this.currentSymbol)}`);
      const dosData = await dosRes.json();

      const decRes = await fetch(`/api/decision/council?symbol=${encodeURIComponent(this.currentSymbol)}`);
      const decData = await decRes.json();
      if (window.evidenceDossier) window.evidenceDossier.update(dosData, decData);

      // 4. Fetch Scenarios & Path Simulation
      const scenRes = await fetch(`/api/scenarios?symbol=${encodeURIComponent(this.currentSymbol)}`);
      const scenData = await scenRes.json();
      if (window.scenarioVisualizer) window.scenarioVisualizer.updateScenarios(scenData);

      const simRes = await fetch(`/api/path-simulation?symbol=${encodeURIComponent(this.currentSymbol)}`);
      const simData = await simRes.json();
      if (window.scenarioVisualizer) window.scenarioVisualizer.updateSimulation(simData);

      // 5. Fetch Macro Snapshot
      const macroRes = await fetch("/api/market/macro");
      const macroData = await macroRes.json();
      if (window.macroTicker) window.macroTicker.update(macroData);

      // 6. Update Order Panel Calculations
      if (window.orderPanel) window.orderPanel.recalculate();
    } catch (e) {
      console.error("Error refreshing active view:", e);
    }
  }

  async sendCopilotMessage() {
    const text = this.copilotInput?.value.trim();
    if (!text) return;

    this.appendChatMessage(text, "user");
    if (this.copilotInput) this.copilotInput.value = "";

    // Check if it's a natural language trade command (English/Bangla/Banglish)
    if (/^(buy|sell|long|short|entered|kinlam|bechlam|ami)/i.test(text) || /(buy|sell|long|short|kinlam|bechlam)/i.test(text)) {
      try {
        const cmdRes = await fetch("/api/command/parse", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ command_text: text }),
        });
        const cmdData = await cmdRes.json();
        if (cmdData.is_valid_command) {
          this.appendChatMessage(cmdData.message, "bot");
          if (window.livePositionsDock) {
            window.livePositionsDock.refresh();
          }
          return;
        }
      } catch (e) {
        console.error(e);
      }
    }

    // Standard Q&A
    try {
      const res = await fetch("/api/desk/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: text,
          symbol: this.currentSymbol,
          timeframe: this.currentTimeframe,
        }),
      });
      const data = await res.json();
      this.appendChatMessage(data.reply, "bot");
    } catch (e) {
      this.appendChatMessage("Desk intelligence encountered communication error.", "bot");
    }
  }

  appendChatMessage(msg, sender) {
    if (!this.chatHistory) return;
    const msgEl = document.createElement("div");
    msgEl.className = `chat-msg ${sender === "user" ? "user-msg" : "bot-msg"}`;
    msgEl.style.marginTop = "6px";
    msgEl.style.color = sender === "user" ? "var(--accent-blue)" : "var(--text-main)";
    msgEl.innerHTML = `<strong>${sender === "user" ? "You: " : "AI: "}</strong>${msg.replace(/\n/g, "<br>")}`;
    this.chatHistory.appendChild(msgEl);
    this.chatHistory.scrollTop = this.chatHistory.scrollHeight;
  }

  async runLabTest(endpoint) {
    if (this.labOutput) {
      this.labOutput.innerHTML = `<p style="color:var(--accent-blue);">Executing statistical simulation across 300 historical bars...</p>`;
    }
    try {
      const res = await fetch(`${endpoint}?symbol=${encodeURIComponent(this.currentSymbol)}&timeframe=${this.currentTimeframe}`, {
        method: "POST",
      });
      const data = await res.json();
      if (this.labOutput) {
        this.labOutput.innerHTML = `<pre style="background:var(--bg-panel); padding:12px; border-radius:6px; overflow-x:auto; font-family:'JetBrains Mono'; font-size:11px;">${JSON.stringify(data, null, 2)}</pre>`;
      }
    } catch (e) {
      if (this.labOutput) {
        this.labOutput.innerHTML = `<p style="color:var(--accent-red);">Test execution failed: ${e.message}</p>`;
      }
    }
  }
}

document.addEventListener("DOMContentLoaded", () => {
  window.appController = new AppController();
});
