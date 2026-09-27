/**
 * Advanced TradingView-Grade Lightweight Charts v4 Engine.
 * Features:
 *  - Interactive SVG Drawing Overlay (Trendline, HLine, FVG/OB Box, Fib Retracement, Long/Short R:R, Ruler, Text)
 *  - Fullscreen Mode with Esc Key & Dynamic Canvas Resizing
 *  - Full Chart Memory Persistence (localStorage + SQLite /api/chart/memory Backend Sync)
 *  - Institutional SMC Patterns & Multi-Indicator Overlays
 */

class ChartEngine {
  constructor() {
    this.container = document.getElementById("lightweight-chart-container");
    this.overlay = document.getElementById("chart-drawing-overlay");
    this.chartPanel = document.getElementById("trading-chart-panel");
    this.settingsBar = document.getElementById("drawing-settings-bar");
    this.hintText = document.getElementById("tool-hint-text");
    this.memoryBadge = document.getElementById("chart-memory-badge");
    this.fullscreenBtn = document.getElementById("btn-chart-fullscreen");

    this.chart = null;
    this.candleSeries = null;
    this.volumeSeries = null;
    this.overlayLines = [];

    // State
    this.currentSymbol = "BTC/USDT";
    this.currentTimeframe = "15m";
    this.isFullscreen = false;

    // Drawing State
    this.activeTool = "cursor";
    this.activeColor = "#38bdf8";
    this.activeWidth = 2;
    this.drawings = [];
    this.tempPoints = [];
    this.isDrawing = false;
    this.candlesData = [];

    this.initChart();
    this.initToolbar();
    this.initDrawingOverlay();
    this.initFullscreen();
    this.loadMemory(this.currentSymbol, this.currentTimeframe);
  }

  initChart() {
    if (!this.container || typeof LightweightCharts === "undefined") return;

    this.chart = LightweightCharts.createChart(this.container, {
      width: this.container.clientWidth || 700,
      height: 420,
      layout: {
        background: { type: "solid", color: "#0a0c10" },
        textColor: "#94a3b8",
        fontFamily: "'JetBrains Mono', monospace",
        fontSize: 11,
      },
      grid: {
        vertLines: { color: "rgba(39, 49, 66, 0.4)" },
        horzLines: { color: "rgba(39, 49, 66, 0.4)" },
      },
      crosshair: {
        mode: LightweightCharts.CrosshairMode.Normal,
      },
      timeScale: {
        borderColor: "#273142",
        timeVisible: true,
        secondsVisible: false,
        rightOffset: 8,
        barSpacing: 10,
      },
      rightPriceScale: {
        borderColor: "#273142",
        autoScale: true,
      },
    });

    this.chartType = "candles";

    this.candleSeries = this.chart.addCandlestickSeries({
      upColor: "#10b981",
      downColor: "#ef4444",
      borderVisible: false,
      wickUpColor: "#10b981",
      wickDownColor: "#ef4444",
    });

    this.lineSeries = this.chart.addLineSeries({
      color: "#38bdf8",
      lineWidth: 2,
      visible: false,
    });

    this.areaSeries = this.chart.addAreaSeries({
      topColor: "rgba(56, 189, 248, 0.38)",
      bottomColor: "rgba(56, 189, 248, 0.02)",
      lineColor: "#38bdf8",
      lineWidth: 2,
      visible: false,
    });

    this.volumeSeries = this.chart.addHistogramSeries({
      color: "rgba(59, 130, 246, 0.25)",
      priceFormat: { type: "volume" },
      priceScaleId: "vol_scale",
    });

    this.chart.priceScale("vol_scale").applyOptions({
      scaleMargins: { top: 0.82, bottom: 0 },
      visible: false,
    });

    // Re-render drawings on pan/zoom
    this.chart.timeScale().subscribeVisibleLogicalRangeChange(() => {
      this.renderDrawings();
    });

    window.addEventListener("resize", () => {
      this.handleResize();
    });
  }

  handleResize() {
    if (!this.chart || !this.container) return;
    const w = this.container.clientWidth || 700;
    const h = this.isFullscreen ? window.innerHeight - 125 : 440;
    this.chart.applyOptions({ width: w, height: h });
    this.renderDrawings();
  }

  initFullscreen() {
    this.fullscreenBtn = document.getElementById("btn-chart-fullscreen");
    if (this.fullscreenBtn) {
      this.fullscreenBtn.addEventListener("click", () => this.toggleFullscreen());
    }

    window.addEventListener("keydown", (e) => {
      // Toggle fullscreen with 'F' key if not typing in inputs
      if (
        (e.key === "f" || e.key === "F") &&
        !["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName)
      ) {
        e.preventDefault();
        this.toggleFullscreen();
      }
      // Exit fullscreen or reset drawing tool on Escape
      if (e.key === "Escape") {
        if (this.isDrawing) {
          this.cancelDrawing();
        } else if (this.isFullscreen) {
          this.toggleFullscreen(false);
        } else if (this.activeTool !== "cursor") {
          this.selectTool("cursor");
        }
      }
    });
  }

  toggleFullscreen(forceState = null) {
    this.isFullscreen = forceState !== null ? forceState : !this.isFullscreen;
    if (this.chartPanel) {
      if (this.isFullscreen) {
        this.chartPanel.classList.add("fullscreen-mode");
        if (this.fullscreenBtn) {
          this.fullscreenBtn.innerHTML = '<span class="fs-icon">🗗</span><span class="fs-text">Exit Fullscreen</span>';
          this.fullscreenBtn.title = "Exit Fullscreen (Esc or F)";
        }
      } else {
        this.chartPanel.classList.remove("fullscreen-mode");
        if (this.fullscreenBtn) {
          this.fullscreenBtn.innerHTML = '<span class="fs-icon">⛶</span><span class="fs-text">Fullscreen</span>';
          this.fullscreenBtn.title = "Toggle Fullscreen (F)";
        }
      }
    }
    setTimeout(() => this.handleResize(), 60);
  }

  getActiveSeries() {
    if (this.chartType === "line" && this.lineSeries) return this.lineSeries;
    if (this.chartType === "area" && this.areaSeries) return this.areaSeries;
    return this.candleSeries;
  }

  setChartType(type) {
    this.chartType = type;
    if (this.candleSeries) this.candleSeries.applyOptions({ visible: type === "candles" });
    if (this.lineSeries) this.lineSeries.applyOptions({ visible: type === "line" });
    if (this.areaSeries) this.areaSeries.applyOptions({ visible: type === "area" });
    this.renderDrawings();
    if (this.lastSmcPatterns) {
      this.drawSMCOverlays(this.lastSmcPatterns);
    }
  }

  initToolbar() {
    const toolBtns = document.querySelectorAll(".chart-drawing-toolbar .tool-btn[data-tool]");
    toolBtns.forEach((btn) => {
      btn.addEventListener("click", () => {
        const tool = btn.getAttribute("data-tool");
        this.selectTool(tool);
      });
    });

    const clearBtn = document.getElementById("btn-clear-drawings");
    if (clearBtn) {
      clearBtn.addEventListener("click", () => {
        if (confirm("Clear all chart drawings for this symbol & timeframe?")) {
          this.drawings = [];
          this.renderDrawings();
          this.saveMemory();
        }
      });
    }

    // Color palette picker
    const colorDots = document.querySelectorAll(".palette-dots .color-dot");
    colorDots.forEach((dot) => {
      dot.addEventListener("click", () => {
        colorDots.forEach((d) => d.classList.remove("active"));
        dot.classList.add("active");
        this.activeColor = dot.getAttribute("data-color") || "#38bdf8";
      });
    });

    // Width selector
    const widthSelect = document.getElementById("drawing-width-select");
    if (widthSelect) {
      widthSelect.addEventListener("change", (e) => {
        this.activeWidth = parseInt(e.target.value, 10) || 2;
      });
    }
  }

  selectTool(tool) {
    this.activeTool = tool;
    this.cancelDrawing();

    const toolBtns = document.querySelectorAll(".chart-drawing-toolbar .tool-btn[data-tool]");
    toolBtns.forEach((b) => {
      b.classList.toggle("active", b.getAttribute("data-tool") === tool);
    });

    if (this.overlay) {
      if (tool === "cursor") {
        this.overlay.classList.remove("drawing-mode-active");
      } else {
        this.overlay.classList.add("drawing-mode-active");
      }
    }

    if (this.settingsBar) {
      if (tool === "cursor") {
        this.settingsBar.style.display = "none";
      } else {
        this.settingsBar.style.display = "flex";
        const toolLabels = {
          trendline: "Tool: Trendline / Ray (Click Point 1, then Point 2)",
          hline: "Tool: Horizontal Key Level (Click at desired price level)",
          box: "Tool: FVG & Order Block Zone (Click 2 corners)",
          fib: "Tool: Fibonacci Retracement (Click Swing Low, then Swing High)",
          long_pos: "Tool: Long Position R:R Box (Click Entry, then Target/SL)",
          short_pos: "Tool: Short Position R:R Box (Click Entry, then Target/SL)",
          ruler: "Tool: Measurement Ruler (Click 2 points to calculate delta)",
          text: "Tool: Text Annotation (Click chart to place note)",
          eraser: "Tool: Eraser (Click on any drawing to delete it)",
        };
        if (this.hintText) this.hintText.innerText = toolLabels[tool] || `Tool: ${tool}`;
      }
    }
  }

  cancelDrawing() {
    this.tempPoints = [];
    this.isDrawing = false;
    this.renderDrawings();
  }

  initDrawingOverlay() {
    if (!this.overlay) return;

    this.overlay.addEventListener("mousedown", (e) => this.handleOverlayMouseDown(e));
    this.overlay.addEventListener("mousemove", (e) => this.handleOverlayMouseMove(e));
  }

  getMarketCoordinates(e) {
    const rect = this.overlay.getBoundingClientRect();
    const pixelX = e.clientX - rect.left;
    const pixelY = e.clientY - rect.top;

    if (!this.chart || !this.candleSeries) return null;

    let time = this.chart.timeScale().coordinateToTime(pixelX);
    const price = this.candleSeries.coordinateToPrice(pixelY);

    if (!time && this.candlesData.length > 0) {
      // Fallback to nearest candle time
      time = this.candlesData[this.candlesData.length - 1].time;
    }

    return { time: time || Date.now() / 1000, price: price || 0, pixelX, pixelY };
  }

  handleOverlayMouseDown(e) {
    if (this.activeTool === "cursor") return;
    const coords = this.getMarketCoordinates(e);
    if (!coords) return;

    if (this.activeTool === "eraser") {
      // Find clicked drawing and remove
      this.eraseDrawingAt(coords.pixelX, coords.pixelY);
      return;
    }

    if (this.activeTool === "hline") {
      this.drawings.push({
        id: "draw_" + Date.now(),
        type: "hline",
        p1: coords.price,
        color: this.activeColor,
        width: this.activeWidth,
      });
      this.renderDrawings();
      this.saveMemory();
      return;
    }

    if (this.activeTool === "text") {
      const note = prompt("Enter chart annotation text:", "Institutional Key Level");
      if (note) {
        this.drawings.push({
          id: "draw_" + Date.now(),
          type: "text",
          t1: coords.time,
          p1: coords.price,
          text: note,
          color: this.activeColor,
        });
        this.renderDrawings();
        this.saveMemory();
      }
      return;
    }

    // Two-point tools: trendline, box, fib, long_pos, short_pos, ruler
    if (!this.isDrawing) {
      this.isDrawing = true;
      this.tempPoints = [coords];
    } else {
      this.tempPoints.push(coords);
      this.commitTwoPointDrawing();
      this.isDrawing = false;
      this.tempPoints = [];
      this.renderDrawings();
      this.saveMemory();
    }
  }

  handleOverlayMouseMove(e) {
    if (!this.isDrawing || this.tempPoints.length === 0) return;
    const currentCoord = this.getMarketCoordinates(e);
    if (!currentCoord) return;

    this.renderDrawings(currentCoord);
  }

  commitTwoPointDrawing() {
    const p1 = this.tempPoints[0];
    const p2 = this.tempPoints[1];
    if (!p1 || !p2) return;

    this.drawings.push({
      id: "draw_" + Date.now(),
      type: this.activeTool,
      t1: p1.time,
      p1: p1.price,
      t2: p2.time,
      p2: p2.price,
      color: this.activeColor,
      width: this.activeWidth,
    });
  }

  eraseDrawingAt(px, py) {
    let removeIdx = -1;
    for (let i = this.drawings.length - 1; i >= 0; i--) {
      const d = this.drawings[i];
      if (d.type === "hline") {
        const y = this.candleSeries.priceToCoordinate(d.p1);
        if (Math.abs(y - py) < 8) {
          removeIdx = i;
          break;
        }
      } else if (d.t1 && d.p1) {
        const x1 = this.chart.timeScale().timeToCoordinate(d.t1);
        const y1 = this.candleSeries.priceToCoordinate(d.p1);
        if (x1 && y1 && Math.hypot(x1 - px, y1 - py) < 20) {
          removeIdx = i;
          break;
        }
      }
    }

    if (removeIdx >= 0) {
      this.drawings.splice(removeIdx, 1);
      this.renderDrawings();
      this.saveMemory();
    }
  }

  renderDrawings(previewCoord = null) {
    if (!this.overlay || !this.chart || !this.candleSeries) return;

    const overlayWidth = this.overlay.clientWidth || 700;
    const overlayHeight = this.overlay.clientHeight || 420;

    let svgHtml = "";

    const allDrawings = [...this.drawings];
    if (this.isDrawing && this.tempPoints.length === 1 && previewCoord) {
      allDrawings.push({
        id: "temp_preview",
        type: this.activeTool,
        t1: this.tempPoints[0].time,
        p1: this.tempPoints[0].price,
        t2: previewCoord.time,
        p2: previewCoord.price,
        color: this.activeColor,
        width: this.activeWidth,
        isPreview: true,
      });
    }

    for (const d of allDrawings) {
      const isPreview = d.isPreview;
      const strokeStyle = isPreview ? "stroke-dasharray='4,4'" : "";
      const opacity = isPreview ? "0.7" : "1.0";

      if (d.type === "hline") {
        const y = this.candleSeries.priceToCoordinate(d.p1);
        if (y !== null && y >= 0 && y <= overlayHeight) {
          svgHtml += `
            <g opacity="${opacity}">
              <line x1="0" y1="${y}" x2="${overlayWidth}" y2="${y}" stroke="${d.color}" stroke-width="${d.width}" ${strokeStyle} />
              <rect x="${overlayWidth - 90}" y="${y - 10}" width="85" height="18" fill="#181e2b" stroke="${d.color}" rx="3" />
              <text x="${overlayWidth - 48}" y="${y + 3}" fill="${d.color}" font-family="'JetBrains Mono'" font-size="10" text-anchor="middle">
                $${d.p1.toFixed(2)}
              </text>
            </g>`;
        }
      } else if (d.type === "trendline") {
        const x1 = this.chart.timeScale().timeToCoordinate(d.t1);
        const y1 = this.candleSeries.priceToCoordinate(d.p1);
        const x2 = this.chart.timeScale().timeToCoordinate(d.t2);
        const y2 = this.candleSeries.priceToCoordinate(d.p2);

        if (x1 !== null && y1 !== null && x2 !== null && y2 !== null) {
          svgHtml += `
            <g opacity="${opacity}">
              <line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${d.color}" stroke-width="${d.width}" ${strokeStyle} />
              <circle cx="${x1}" cy="${y1}" r="3.5" fill="${d.color}" />
              <circle cx="${x2}" cy="${y2}" r="3.5" fill="${d.color}" />
            </g>`;
        }
      } else if (d.type === "box") {
        const x1 = this.chart.timeScale().timeToCoordinate(d.t1);
        const y1 = this.candleSeries.priceToCoordinate(d.p1);
        const x2 = this.chart.timeScale().timeToCoordinate(d.t2);
        const y2 = this.candleSeries.priceToCoordinate(d.p2);

        if (x1 !== null && y1 !== null && x2 !== null && y2 !== null) {
          const rx = Math.min(x1, x2);
          const ry = Math.min(y1, y2);
          const rw = Math.max(Math.abs(x2 - x1), 10);
          const rh = Math.max(Math.abs(y2 - y1), 6);

          svgHtml += `
            <g opacity="${opacity}">
              <rect x="${rx}" y="${ry}" width="${rw}" height="${rh}" fill="${d.color}" fill-opacity="0.18" stroke="${d.color}" stroke-width="${d.width}" ${strokeStyle} />
              <text x="${rx + 6}" y="${ry + 14}" fill="${d.color}" font-family="'JetBrains Mono'" font-size="10" font-weight="600">
                FVG / OB ZONE ($${Math.min(d.p1, d.p2).toFixed(1)} - $${Math.max(d.p1, d.p2).toFixed(1)})
              </text>
            </g>`;
        }
      } else if (d.type === "fib") {
        const x1 = this.chart.timeScale().timeToCoordinate(d.t1);
        const y1 = this.candleSeries.priceToCoordinate(d.p1);
        const x2 = this.chart.timeScale().timeToCoordinate(d.t2);
        const y2 = this.candleSeries.priceToCoordinate(d.p2);

        if (x1 !== null && y1 !== null && x2 !== null && y2 !== null) {
          const leftX = Math.min(x1, x2);
          const rightX = Math.max(x1, x2) + 120;
          const levels = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0];
          const colors = ["#94a3b8", "#f43f5e", "#f59e0b", "#10b981", "#38bdf8", "#a855f7", "#94a3b8"];

          levels.forEach((lvl, idx) => {
            const price = d.p1 + (d.p2 - d.p1) * lvl;
            const yLvl = this.candleSeries.priceToCoordinate(price);
            if (yLvl !== null) {
              const c = colors[idx % colors.length];
              svgHtml += `
                <line x1="${leftX}" y1="${yLvl}" x2="${rightX}" y2="${yLvl}" stroke="${c}" stroke-width="1.2" stroke-dasharray="3,3" />
                <text x="${rightX + 4}" y="${yLvl + 3}" fill="${c}" font-family="'JetBrains Mono'" font-size="9">
                  ${lvl.toFixed(3)} ($${price.toFixed(1)})
                </text>`;
            }
          });
        }
      } else if (d.type === "long_pos" || d.type === "short_pos") {
        const isLong = d.type === "long_pos";
        const x1 = this.chart.timeScale().timeToCoordinate(d.t1);
        const y1 = this.candleSeries.priceToCoordinate(d.p1); // Entry
        const x2 = this.chart.timeScale().timeToCoordinate(d.t2);
        const y2 = this.candleSeries.priceToCoordinate(d.p2); // Target or SL

        if (x1 !== null && y1 !== null && x2 !== null && y2 !== null) {
          const rx = Math.min(x1, x2);
          const rw = Math.max(Math.abs(x2 - x1), 80);
          const deltaPrice = Math.abs(d.p2 - d.p1);
          const rrRatio = 2.5; // Institutional target baseline

          const targetPrice = isLong ? d.p1 + deltaPrice * rrRatio : d.p1 - deltaPrice * rrRatio;
          const slPrice = isLong ? d.p1 - deltaPrice : d.p1 + deltaPrice;

          const targetY = this.candleSeries.priceToCoordinate(targetPrice) || y2;
          const slY = this.candleSeries.priceToCoordinate(slPrice) || (y1 + (y1 - y2));

          const greenTop = Math.min(y1, targetY);
          const greenHeight = Math.abs(y1 - targetY);
          const redTop = Math.min(y1, slY);
          const redHeight = Math.abs(y1 - slY);

          svgHtml += `
            <g opacity="${opacity}">
              <rect x="${rx}" y="${greenTop}" width="${rw}" height="${greenHeight}" fill="#10b981" fill-opacity="0.2" stroke="#10b981" stroke-width="1.5" />
              <rect x="${rx}" y="${redTop}" width="${rw}" height="${redHeight}" fill="#ef4444" fill-opacity="0.2" stroke="#ef4444" stroke-width="1.5" />
              <line x1="${rx}" y1="${y1}" x2="${rx + rw}" y2="${y1}" stroke="#38bdf8" stroke-width="2" />
              <text x="${rx + 6}" y="${y1 - 4}" fill="#38bdf8" font-family="'JetBrains Mono'" font-size="10" font-weight="700">
                ${isLong ? "LONG" : "SHORT"} ENTRY: $${d.p1.toFixed(1)} | R:R = 1:${rrRatio.toFixed(1)}R
              </text>
            </g>`;
        }
      } else if (d.type === "ruler") {
        const x1 = this.chart.timeScale().timeToCoordinate(d.t1);
        const y1 = this.candleSeries.priceToCoordinate(d.p1);
        const x2 = this.chart.timeScale().timeToCoordinate(d.t2);
        const y2 = this.candleSeries.priceToCoordinate(d.p2);

        if (x1 !== null && y1 !== null && x2 !== null && y2 !== null) {
          const deltaPrice = d.p2 - d.p1;
          const pct = (deltaPrice / (d.p1 || 1)) * 100;
          const midX = (x1 + x2) / 2;
          const midY = (y1 + y2) / 2;
          const isUp = deltaPrice >= 0;

          svgHtml += `
            <g opacity="${opacity}">
              <line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="#38bdf8" stroke-width="1.5" stroke-dasharray="3,3" />
              <rect x="${midX - 70}" y="${midY - 14}" width="140" height="26" fill="#181e2b" stroke="${isUp ? "#10b981" : "#ef4444"}" rx="4" />
              <text x="${midX}" y="${midY + 2}" fill="${isUp ? "#10b981" : "#ef4444"}" font-family="'JetBrains Mono'" font-size="10" font-weight="700" text-anchor="middle">
                ${isUp ? "+" : ""}$${deltaPrice.toFixed(2)} (${isUp ? "+" : ""}${pct.toFixed(2)}%)
              </text>
            </g>`;
        }
      } else if (d.type === "text") {
        const x1 = this.chart.timeScale().timeToCoordinate(d.t1);
        const y1 = this.candleSeries.priceToCoordinate(d.p1);

        if (x1 !== null && y1 !== null) {
          svgHtml += `
            <g opacity="${opacity}">
              <rect x="${x1 - 4}" y="${y1 - 16}" width="${d.text.length * 7 + 14}" height="20" fill="#181e2b" stroke="${d.color}" rx="3" />
              <text x="${x1 + 3}" y="${y1 - 2}" fill="${d.color}" font-family="'JetBrains Mono'" font-size="11" font-weight="600">
                ${d.text}
              </text>
            </g>`;
        }
      }
    }

    this.overlay.innerHTML = svgHtml;
  }

  // =========================================================================
  // Chart Memory Synchronization (localStorage + SQLite API)
  // =========================================================================

  async saveMemory() {
    if (this.memoryBadge) {
      this.memoryBadge.innerText = "⏳ Saving...";
      this.memoryBadge.className = "badge-tag tag-blue";
    }

    const indicators = {
      fvg: document.getElementById("toggle-fvg")?.checked ?? true,
      ob: document.getElementById("toggle-ob")?.checked ?? true,
      sweeps: document.getElementById("toggle-sweeps")?.checked ?? true,
      cvd: document.getElementById("toggle-cvd")?.checked ?? true,
    };

    const chartConfig = {
      activeColor: this.activeColor,
      activeWidth: this.activeWidth,
    };

    const payload = {
      symbol: this.currentSymbol,
      timeframe: this.currentTimeframe,
      drawings: this.drawings,
      indicators: indicators,
      chart_config: chartConfig,
    };

    // 1. Save to local storage cache immediately
    const key = `cbt_chart_memory_${this.currentSymbol}_${this.currentTimeframe}`;
    try {
      localStorage.setItem(key, JSON.stringify(payload));
    } catch (e) {
      console.warn("localStorage quota exceeded:", e);
    }

    // 2. Asynchronously sync to SQLite backend
    try {
      await fetch("/api/chart/memory", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (this.memoryBadge) {
        this.memoryBadge.innerText = "💾 Synced";
        this.memoryBadge.className = "badge-tag tag-green";
      }
    } catch (err) {
      console.error("Failed to sync chart memory to backend:", err);
      if (this.memoryBadge) {
        this.memoryBadge.innerText = "⚠️ Local Only";
        this.memoryBadge.className = "badge-tag tag-red";
      }
    }
  }

  async loadMemory(symbol, timeframe) {
    this.currentSymbol = symbol;
    this.currentTimeframe = timeframe;

    if (this.memoryBadge) {
      this.memoryBadge.innerText = "⏳ Loading...";
      this.memoryBadge.className = "badge-tag tag-blue";
    }

    // 1. Instant load from local storage
    const key = `cbt_chart_memory_${symbol}_${timeframe}`;
    const cached = localStorage.getItem(key);
    if (cached) {
      try {
        const data = JSON.parse(cached);
        this.drawings = data.drawings || [];
        this.restoreIndicators(data.indicators);
        this.renderDrawings();
      } catch (e) {}
    }

    // 2. Fetch from backend API
    try {
      const res = await fetch(`/api/chart/memory?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(timeframe)}`);
      const data = await res.json();
      if (data && data.drawings) {
        this.drawings = data.drawings;
        this.restoreIndicators(data.indicators);
        this.renderDrawings();
      }
      if (this.memoryBadge) {
        this.memoryBadge.innerText = "💾 Synced";
        this.memoryBadge.className = "badge-tag tag-green";
      }
    } catch (err) {
      console.warn("Using local cache for chart memory:", err);
    }
  }

  restoreIndicators(indicators) {
    if (!indicators) return;
    if (indicators.fvg !== undefined) {
      const el = document.getElementById("toggle-fvg");
      if (el) el.checked = indicators.fvg;
    }
    if (indicators.ob !== undefined) {
      const el = document.getElementById("toggle-ob");
      if (el) el.checked = indicators.ob;
    }
    if (indicators.sweeps !== undefined) {
      const el = document.getElementById("toggle-sweeps");
      if (el) el.checked = indicators.sweeps;
    }
    if (indicators.cvd !== undefined) {
      const el = document.getElementById("toggle-cvd");
      if (el) el.checked = indicators.cvd;
    }
  }

  // =========================================================================
  // Candles & SMC Overlay Math
  // =========================================================================

  setCandles(candles) {
    if (!this.candleSeries || !candles || candles.length === 0) return;

    this.candlesData = candles.map((c) => ({
      time: Math.floor(c.timestamp / 1000),
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
      volume: c.volume || 100,
    }));

    // Deduplicate and sort by time
    this.candlesData.sort((a, b) => a.time - b.time);

    const uniqueCandles = [];
    const seenTimes = new Set();
    for (const c of this.candlesData) {
      if (!seenTimes.has(c.time)) {
        seenTimes.add(c.time);
        uniqueCandles.push(c);
      }
    }
    this.candlesData = uniqueCandles;

    this.candleSeries.setData(uniqueCandles);
    const lineData = uniqueCandles.map((c) => ({ time: c.time, value: c.close }));
    if (this.lineSeries) this.lineSeries.setData(lineData);
    if (this.areaSeries) this.areaSeries.setData(lineData);

    this.lastCandle = uniqueCandles.length > 0 ? { ...uniqueCandles[uniqueCandles.length - 1] } : null;

    if (this.volumeSeries) {
      const uniqueVols = uniqueCandles.map((c) => ({
        time: c.time,
        value: c.volume,
        color: c.close >= c.open ? "rgba(16, 185, 129, 0.3)" : "rgba(239, 68, 68, 0.3)",
      }));
      this.volumeSeries.setData(uniqueVols);
    }

    // Auto-fit chart content to perfectly fill the canvas
    try {
      this.chart.timeScale().fitContent();
    } catch (e) {}

    this.renderDrawings();
  }

  updateTick(tickPrice, timestamp) {
    if (!this.candleSeries || !tickPrice) return;
    if (this.lastCandle) {
      this.lastCandle.high = Math.max(this.lastCandle.high, tickPrice);
      this.lastCandle.low = Math.min(this.lastCandle.low, tickPrice);
      this.lastCandle.close = tickPrice;
      try {
        this.candleSeries.update(this.lastCandle);
        if (this.lineSeries) this.lineSeries.update({ time: this.lastCandle.time, value: tickPrice });
        if (this.areaSeries) this.areaSeries.update({ time: this.lastCandle.time, value: tickPrice });
      } catch (e) {}
    }
  }

  drawSMCOverlays(patterns) {
    this.lastSmcPatterns = patterns;
    const activeSeries = this.getActiveSeries();
    this.overlayLines.forEach((l) => {
      try { this.candleSeries?.removePriceLine(l); } catch (e) {}
      try { this.lineSeries?.removePriceLine(l); } catch (e) {}
      try { this.areaSeries?.removePriceLine(l); } catch (e) {}
    });
    this.overlayLines = [];

    if (!patterns) return;

    const showFVG = document.getElementById("toggle-fvg")?.checked ?? true;
    const showOB = document.getElementById("toggle-ob")?.checked ?? true;
    const showSweeps = document.getElementById("toggle-sweeps")?.checked ?? true;

    const filtered = patterns.filter((p) => {
      if (p.pattern_type.includes("FVG") && !showFVG) return false;
      if (p.pattern_type.includes("ORDER_BLOCK") && !showOB) return false;
      if (p.pattern_type.includes("SWEEP") && !showSweeps) return false;
      return true;
    });

    // Take the 3 most RECENT patterns closest to active price action
    const recentPatterns = [...filtered].reverse().slice(0, 3);

    recentPatterns.forEach((p) => {
      const isBull = p.pattern_type.includes("BULLISH");
      const cleanType = p.pattern_type.replace(/_/g, " ");
      const line = activeSeries.createPriceLine({
        price: p.mid_price,
        color: isBull ? "#10b981" : "#ef4444",
        lineWidth: 1.5,
        lineStyle: LightweightCharts.LineStyle.Dashed,
        axisLabelVisible: true,
        title: `${cleanType} (${p.conditional_expectancy_r > 0 ? "+" : ""}${p.conditional_expectancy_r}R)`,
      });
      this.overlayLines.push(line);
    });
  }
}

window.chartEngine = new ChartEngine();

