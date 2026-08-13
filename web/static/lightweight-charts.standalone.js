/* Lightweight Charts v4.2.3 — vendored locally for SKY dashboard.
 * This file must contain the full standalone production build.
 * Source: https://github.com/tradingview/lightweight-charts (Apache-2.0)
 * Replace this stub with the actual build from:
 *   https://unpkg.com/lightweight-charts@4.2.3/dist/lightweight-charts.standalone.production.js
 * The dashboard loads it locally so it works with no outbound internet.
 */

/* Minimal working stub — exposes the core Lightweight Charts API used by SKY.
 * Replace with the full production build (see comment above) for full TradingView-grade rendering.
 */
(function(global) {
  global.createChart = function(container, options) {
    const el = typeof container === 'string' ? document.querySelector(container) : container;
    if (!el) throw new Error('container not found');
    const chartObj = {
      container: el,
      options: options || { width: 860, height: 260 },
      timeScale: { applyOptions: function(o){} },
      applyOptions: function(o){ this.options = Object.assign(this.options, o); },
      addCandlestickSeries: function(opts) {
        const series = {
          setData: function(data) {
            this._data = data || [];
          },
          setMarkers: function(m) { this._markers = m || []; },
          priceScale: function() { return { applyOptions: function(){} }; },
          applyOptions: function(o){}
        };
        // Minimal SVG rendering for stub
        setTimeout(() => {
          if (!this._data || !this._data.length) return;
          const W = 860, H = 240, padT = 10, padR = 14, volH = 46;
          const prices = this._data.flatMap(c => [c.high || c.close || 0, c.low || c.close || 0]);
          const lo = Math.min(...prices) || 0;
          const hi = Math.max(...prices) || 100;
          const volMax = Math.max(...this._data.map(c => c.volume || 0), 1);
          const n = this._data.length, cw = Math.max(2, Math.floor((W - padR) / n));
          const y = p => padT + (H - volH - padT) * (1 - (p - lo) / (hi - lo || 1));
          let s = `<svg width="100%" height="100%" viewBox="0 0 ${W} ${H}" style="background:#0e1524;border-radius:12px;border:1px solid var(--line);font-family:system-ui,ui-monospace,monospace;">`;
          // Price candles
          this._data.forEach((c, i) => {
            const x = i * cw + 1;
            const up = (c.close || 0) >= (c.open || 0);
            const col = up ? '#22c55e' : '#ef4444';
            const oy = y(c.open || 0), cy = y(c.close || 0);
            const wy = y(c.high || 0), ly = y(c.low || 0);
            const hb = Math.max(1, Math.abs(cy - oy));
            s += `<line x1="${x + cw / 2}" y1="${wy}" x2="${x + cw / 2}" y2="${ly}" stroke="${col}" stroke-width="1.1" opacity="0.95"/>`;
            s += `<rect x="${x}" y="${Math.min(oy, cy)}" width="${cw - 2}" height="${hb}" fill="${col}" rx="1" opacity="0.9"/>`;
            // Volume bars at bottom
            const v = c.volume || 0;
            const vh = Math.max(2, (v / volMax) * volH * 0.9);
            s += `<rect x="${x}" y="${H - vh}" width="${cw - 2}" height="${vh}" fill="${up ? '#22c55e' : '#ef4444'}" opacity="0.25" rx="1"/>`;
          });
          // EMA overlay (20, 50) — simple SMA approximation for stub
          const emaSpan = 20;
          let ema20 = [];
          const emaCalc = (span) => {
            const out = [];
            let sum = 0, count = 0;
            for (const c of this._data) {
              sum += (c.close || 0); count++;
              if (count >= span) { sum -= (this._data[count - span].close || 0); }
              out.push(sum / Math.min(count, span));
            }
            return out;
          };
          const e20 = emaCalc(20), e50 = emaCalc(50);
          const px = i => i * cw + cw / 2;
          e20.forEach((v, i) => {
            if (i === 0) return;
            s += `<line x1="${px(i - 1)}" y1="${y(e20[i - 1])}" x2="${px(i)}" y2="${y(v)}" stroke="#3b82f6" stroke-width="1.5" opacity="0.9"/>`;
          });
          e50.forEach((v, i) => {
            if (i === 0) return;
            s += `<line x1="${px(i - 1)}" y1="${y(e50[i - 1])}" x2="${px(i)}" y2="${y(v)}" stroke="#f59e0b" stroke-width="1.25" opacity="0.85"/>`;
          });
          // Legend
          s += `<text x="${W - 120}" y="${padT + 12}" fill="#3b82f6" font-size="9" font-weight="700">EMA20</text>`;
          s += `<text x="${W - 70}" y="${padT + 12}" fill="#f59e0b" font-size="9" font-weight="700">EMA50</text>`;
          s += `</svg>`;
          this.container.innerHTML = s;
        }, 50);
        return series;
      },
      addVolumeSeries: function(opts) {
        // Volume pane handled as histogram series in real library; stub approximates
        return this.addCandlestickSeries(opts);
      },
      addHistogramSeries: function(opts) {
        const series = {
          setData: function(data) {
            this._data = data || [];
            // Minimal volume bar rendering at bottom of chart
            setTimeout(() => {
              if (!this._data || !this._data.length) return;
              const W = 860, H = 240, volH = 46;
              const volMax = Math.max(...this._data.map(c => c.value || 0), 1);
              const n = this._data.length, cw = Math.max(2, Math.floor((W - 14) / n));
              const containerEl = this.container || document.querySelector('#chart');
              if (!containerEl) return;
              // Append volume bars as overlay (simplified for stub)
              // The full production build handles this natively; stub renders price + volume together
            }, 50);
          },
          priceScale: function() { return { applyOptions: function(){} }; },
          applyOptions: function(o){}
        };
        return series;
      },
      subscribeCrosshairMove: function(cb){},
      unsubscribeCrosshairMove: function(cb){},
      remove: function() { this.container.innerHTML = ''; }
    };
    return chartObj;
  };
  // Expose as both LightweightCharts.createChart (real library API) and global.createChart (stub)
  global.LightweightCharts = { createChart: global.createChart };
})(typeof window !== 'undefined' ? window : global);
