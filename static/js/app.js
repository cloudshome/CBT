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

    // Timeframe change handlers (both sidebar .tf-btn and top-bar .tv-tf-btn)
    const handleTimeframeChange = (tf) => {
      this.currentTimeframe = tf;
      document.querySelectorAll(".tf-btn, .tv-tf-btn").forEach((b) => {
        const btnTf = b.getAttribute("data-tf");
        b.classList.toggle("active", btnTf === tf);
      });
      if (window.chartEngine) window.chartEngine.loadMemory(this.currentSymbol, this.currentTimeframe);
      this.refreshActiveView();
    };

    document.querySelectorAll(".tf-btn, .tv-tf-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const tf = btn.getAttribute("data-tf") || "15m";
        handleTimeframeChange(tf);
      });
    });

    // Chart Type (Candles, Line, Area)
    document.querySelectorAll(".tv-type-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".tv-type-btn").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        const type = btn.getAttribute("data-type") || "candles";
        if (window.chartEngine) window.chartEngine.setChartType(type);
      });
    });

    // SMC Indicator Pills (1-click toggles)
    document.querySelectorAll(".tv-indicator-pill").forEach((pill) => {
      pill.addEventListener("click", () => {
        const targetId = pill.getAttribute("data-target");
        const checkbox = document.getElementById(targetId);
        if (checkbox) {
          checkbox.checked = !checkbox.checked;
          pill.classList.toggle("active", checkbox.checked);
          if (this.lastSmcPatterns && window.chartEngine) {
            window.chartEngine.drawSMCOverlays(this.lastSmcPatterns);
          }
          if (window.chartEngine) {
            window.chartEngine.saveMemory();
          }
        }
      });
    });

    // Underlying Checkboxes fallback listener
    ["toggle-fvg", "toggle-ob", "toggle-sweeps", "toggle-cvd"].forEach((id) => {
      const el = document.getElementById(id);
      if (el) {
        el.addEventListener("change", () => {
          const pill = document.querySelector(`.tv-indicator-pill[data-target="${id}"]`);
          if (pill) pill.classList.toggle("active", el.checked);
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

    // High-Reliability Live Ticker & Order Book Poller (Every 2s)
    setInterval(async () => {
      try {
        const res = await fetch(`/api/market/ticker?symbol=${encodeURIComponent(this.currentSymbol)}`);
        const data = await res.json();
        if (data && data.price) {
          const priceEl = document.getElementById("chart-price-live");
          if (priceEl) priceEl.innerText = `$${data.price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
          if (window.chartEngine) window.chartEngine.updateTick(data.price, data.timestamp);
        }
        const obRes = await fetch(`/api/market/orderbook?symbol=${encodeURIComponent(this.currentSymbol)}&limit=10`);
        const obData = await obRes.json();
        if (window.orderBookVisualizer && obData && obData.asks && obData.asks.length > 0) {
          window.orderBookVisualizer.updateWithDepth(obData);
        } else if (window.orderBookVisualizer && data && data.price) {
          window.orderBookVisualizer.update(data.price);
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
      // 1. Fetch Deep Historical Candles (up to 500 bars)
      const candleLimit = ["1d", "4h", "1h"].includes(this.currentTimeframe) ? 500 : 300;
      const cRes = await fetch(`/api/market/candles?symbol=${encodeURIComponent(this.currentSymbol)}&timeframe=${this.currentTimeframe}&limit=${candleLimit}`);
      const cData = await cRes.json();
      if (window.chartEngine) window.chartEngine.setCandles(cData.candles);

      // 1.1 Fetch Real L2 Order Book Depth & Provider Health
      try {
        const obRes = await fetch(`/api/market/orderbook?symbol=${encodeURIComponent(this.currentSymbol)}&limit=10`);
        const obData = await obRes.json();
        if (window.orderBookVisualizer && obData && obData.asks && obData.asks.length > 0) {
          window.orderBookVisualizer.updateWithDepth(obData);
        }
        const provRes = await fetch("/api/market/providers");
        const provData = await provRes.json();
        const obTag = document.getElementById("ob-exchange-tag");
        if (obTag && provData.active_provider) {
          obTag.innerText = `${provData.active_provider} 0.1`;
        }
      } catch (e) {}

      // Compute 24h Market Stats (Binance Pro Header)
      if (cData.candles && cData.candles.length > 0) {
        const candles = cData.candles;
        const last = candles[candles.length - 1];
        const first = candles[0];
        
        let high24 = -Infinity;
        let low24 = Infinity;
        let vol24 = 0;
        
        candles.forEach((c) => {
          if (c.high > high24) high24 = c.high;
          if (c.low < low24) low24 = c.low;
          vol24 += (c.volume || 0);
        });
        
        const changePct = first.open ? ((last.close - first.open) / first.open) * 100 : 0;
        const isUp = changePct >= 0;
        
        const chgEl = document.getElementById("chart-24h-change");
        if (chgEl) {
          chgEl.innerText = `${isUp ? "+" : ""}${changePct.toFixed(2)}%`;
          chgEl.className = `price-change-pill ${isUp ? "tag-green" : "tag-red"}`;
        }
        
        const hEl = document.getElementById("stat-24h-high");
        if (hEl && high24 !== -Infinity) hEl.innerText = `$${high24.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
        
        const lEl = document.getElementById("stat-24h-low");
        if (lEl && low24 !== Infinity) lEl.innerText = `$${low24.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
        
        const vEl = document.getElementById("stat-24h-vol");
        if (vEl) {
          const symBase = this.currentSymbol.split("/")[0] || "BTC";
          vEl.innerText = `${vol24.toLocaleString(undefined, { maximumFractionDigits: 0 })} ${symBase}`;
        }

        const priceEl = document.getElementById("chart-price-live");
        if (priceEl && last.close) {
          priceEl.innerText = `$${last.close.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
        }
      }

      // 2. Fetch SMC Scans & Formations
      const smcRes = await fetch(`/api/smc/scan?symbol=${encodeURIComponent(this.currentSymbol)}&timeframe=${this.currentTimeframe}`);
      const smcData = await smcRes.json();
      this.lastSmcPatterns = smcData.smc_patterns;
      if (window.chartEngine) window.chartEngine.drawSMCOverlays(smcData.smc_patterns);
      const regLabel = document.getElementById("chart-regime-label");
      if (regLabel) {
        regLabel.innerText = smcData.regime || "TRENDING_BULL";
        regLabel.title = `Regime: ${smcData.regime || "TRENDING_BULL"}`;
      }

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
