/**
 * Institutional Binance Pro L2 Order Book Depth Visualizer & Microstructure Tape.
 */
class OrderBookVisualizer {
  constructor() {
    this.container = document.getElementById("orderbook-depth");
    this.lastPrice = null;
  }

  update(midPrice, spreadBps = 1.2) {
    if (!this.container || !midPrice) return;

    const p = midPrice;
    const isGold = p < 5000;
    const step = isGold ? 0.35 : 12.5;
    const priceDecimals = isGold ? 2 : 2;
    const sizeDecimals = isGold ? 2 : 4;

    const priceChangeDir = this.lastPrice ? (p >= this.lastPrice ? "up" : "down") : "up";
    this.lastPrice = p;

    // Generate 6 depth levels for asks
    let askCumulative = 0;
    const asks = [];
    for (let i = 1; i <= 6; i++) {
      const askPrice = p + step * i;
      const size = Number((Math.random() * (isGold ? 15 : 2.5) + (isGold ? 5 : 0.8)).toFixed(sizeDecimals));
      askCumulative += size;
      asks.push({ price: askPrice, size, total: Number(askCumulative.toFixed(sizeDecimals)) });
    }

    // Generate 6 depth levels for bids
    let bidCumulative = 0;
    const bids = [];
    for (let i = 1; i <= 6; i++) {
      const bidPrice = p - step * i;
      const size = Number((Math.random() * (isGold ? 15 : 2.5) + (isGold ? 5 : 0.8)).toFixed(sizeDecimals));
      bidCumulative += size;
      bids.push({ price: bidPrice, size, total: Number(bidCumulative.toFixed(sizeDecimals)) });
    }

    const maxTotal = Math.max(askCumulative, bidCumulative);

    let html = '<div class="ob-table-body">';

    // Asks displayed top to bottom (highest price to lowest ask)
    [...asks].reverse().forEach((a) => {
      const depthPct = Math.min(100, Math.round((a.total / maxTotal) * 100));
      html += `
        <div class="ob-row ask" style="background: linear-gradient(to left, rgba(239, 68, 68, 0.16) ${depthPct}%, transparent ${depthPct}%);">
          <span class="ob-cell price">${a.price.toFixed(priceDecimals)}</span>
          <span class="ob-cell size">${a.size.toFixed(sizeDecimals)}</span>
          <span class="ob-cell total">${a.total.toFixed(sizeDecimals)}</span>
        </div>`;
    });

    // Middle ticker row
    const spreadVal = (asks[0].price - bids[0].price).toFixed(2);
    const arrow = priceChangeDir === "up" ? "▲" : "▼";
    const dirClass = priceChangeDir === "up" ? "price-up" : "price-down";

    html += `
      <div class="ob-mid-bar ${dirClass}">
        <div class="mid-price-tag">
          <span class="trend-arrow">${arrow}</span>
          <span class="main-p">$${p.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
        </div>
        <div class="mid-spread-tag">Spread $${spreadVal} (${spreadBps.toFixed(1)} bps)</div>
      </div>
    `;

    // Bids displayed highest bid to lowest bid
    bids.forEach((b) => {
      const depthPct = Math.min(100, Math.round((b.total / maxTotal) * 100));
      html += `
        <div class="ob-row bid" style="background: linear-gradient(to left, rgba(16, 185, 129, 0.16) ${depthPct}%, transparent ${depthPct}%);">
          <span class="ob-cell price">${b.price.toFixed(priceDecimals)}</span>
          <span class="ob-cell size">${b.size.toFixed(sizeDecimals)}</span>
          <span class="ob-cell total">${b.total.toFixed(sizeDecimals)}</span>
        </div>`;
    });

    html += "</div>";
    this.container.innerHTML = html;
  }

  updateWithDepth(depthData) {
    if (!this.container || !depthData) return;
    const asksRaw = depthData.asks || [];
    const bidsRaw = depthData.bids || [];

    if (asksRaw.length === 0 || bidsRaw.length === 0) {
      if (depthData.price) this.update(depthData.price);
      return;
    }

    const asks = asksRaw.slice(0, 6);
    const bids = bidsRaw.slice(0, 6);

    const midPrice = (asks[0].price + bids[0].price) / 2;
    const isGold = midPrice < 5000;
    const priceDecimals = isGold ? 2 : 2;
    const sizeDecimals = isGold ? 2 : 4;

    const priceChangeDir = this.lastPrice ? (midPrice >= this.lastPrice ? "up" : "down") : "up";
    this.lastPrice = midPrice;

    // Calculate cumulative totals
    let askCumulative = 0;
    const asksWithTotal = asks.map((a) => {
      askCumulative += a.size;
      return { price: a.price, size: a.size, total: Number(askCumulative.toFixed(sizeDecimals)) };
    });

    let bidCumulative = 0;
    const bidsWithTotal = bids.map((b) => {
      bidCumulative += b.size;
      return { price: b.price, size: b.size, total: Number(bidCumulative.toFixed(sizeDecimals)) };
    });

    const maxTotal = Math.max(askCumulative, bidCumulative) || 1;

    let html = '<div class="ob-table-body">';

    // Asks displayed top to bottom (highest price to lowest ask)
    [...asksWithTotal].reverse().forEach((a) => {
      const depthPct = Math.min(100, Math.round((a.total / maxTotal) * 100));
      html += `
        <div class="ob-row ask" style="background: linear-gradient(to left, rgba(239, 68, 68, 0.16) ${depthPct}%, transparent ${depthPct}%);">
          <span class="ob-cell price">${a.price.toFixed(priceDecimals)}</span>
          <span class="ob-cell size">${a.size.toFixed(sizeDecimals)}</span>
          <span class="ob-cell total">${a.total.toFixed(sizeDecimals)}</span>
        </div>`;
    });

    // Middle ticker row
    const spreadVal = (asks[0].price - bids[0].price).toFixed(2);
    const spreadBps = ((asks[0].price - bids[0].price) / midPrice) * 10000;
    const arrow = priceChangeDir === "up" ? "▲" : "▼";
    const dirClass = priceChangeDir === "up" ? "price-up" : "price-down";

    html += `
      <div class="ob-mid-bar ${dirClass}">
        <div class="mid-price-tag">
          <span class="trend-arrow">${arrow}</span>
          <span class="main-p">$${midPrice.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
        </div>
        <div class="mid-spread-tag">Spread $${spreadVal} (${spreadBps.toFixed(1)} bps)</div>
      </div>
    `;

    // Bids displayed highest bid to lowest bid
    bidsWithTotal.forEach((b) => {
      const depthPct = Math.min(100, Math.round((b.total / maxTotal) * 100));
      html += `
        <div class="ob-row bid" style="background: linear-gradient(to left, rgba(16, 185, 129, 0.16) ${depthPct}%, transparent ${depthPct}%);">
          <span class="ob-cell price">${b.price.toFixed(priceDecimals)}</span>
          <span class="ob-cell size">${b.size.toFixed(sizeDecimals)}</span>
          <span class="ob-cell total">${b.total.toFixed(sizeDecimals)}</span>
        </div>`;
    });

    html += "</div>";
    this.container.innerHTML = html;
  }
}

window.orderBookVisualizer = new OrderBookVisualizer();
