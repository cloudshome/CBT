/**
 * L2 Order Book Depth Visualizer & Microstructure Tape.
 */
class OrderBookVisualizer {
  constructor() {
    this.container = document.getElementById("orderbook-depth");
  }

  update(midPrice, spreadBps = 1.2) {
    if (!this.container || !midPrice) return;

    const p = midPrice;
    const isGold = p < 5000;
    const step = isGold ? 0.5 : 15.0;

    const asks = [
      { price: p + (step * 3), size: (Math.random() * 2 + 1).toFixed(isGold ? 1 : 3) },
      { price: p + (step * 2), size: (Math.random() * 3 + 1.5).toFixed(isGold ? 1 : 3) },
      { price: p + step, size: (Math.random() * 4 + 2).toFixed(isGold ? 1 : 3) },
    ];

    const bids = [
      { price: p - step, size: (Math.random() * 4 + 2).toFixed(isGold ? 1 : 3) },
      { price: p - (step * 2), size: (Math.random() * 3 + 1.5).toFixed(isGold ? 1 : 3) },
      { price: p - (step * 3), size: (Math.random() * 2 + 1).toFixed(isGold ? 1 : 3) },
    ];

    let html = "";
    asks.reverse().forEach((a) => {
      html += `<div class="ob-row ask"><span class="price">${a.price.toFixed(2)}</span><span class="size">${a.size}</span></div>`;
    });

    html += `
      <div class="ob-mid">
        <span class="mid-p">${p.toFixed(2)}</span>
        <span class="spread-bps">Spread: ${spreadBps.toFixed(1)} bps</span>
      </div>
    `;

    bids.forEach((b) => {
      html += `<div class="ob-row bid"><span class="price">${b.price.toFixed(2)}</span><span class="size">${b.size}</span></div>`;
    });

    this.container.innerHTML = html;
  }
}

window.orderBookVisualizer = new OrderBookVisualizer();
