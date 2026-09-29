/**
 * Global Macro Vital Ticker & Live Clock.
 */
class MacroTicker {
  constructor() {
    this.dxyEl = document.getElementById("val-dxy");
    this.us10yEl = document.getElementById("val-us10y");
    this.goldEl = document.getElementById("val-gold");
    this.wtiEl = document.getElementById("val-wti");
    this.griEl = document.getElementById("val-gri");
    this.clockEl = document.getElementById("system-clock");
    this.initClock();
  }

  initClock() {
    setInterval(() => {
      const now = new Date();
      if (this.clockEl) {
        this.clockEl.innerText = now.toUTCString().split(" ")[4] + " UTC";
      }
    }, 1000);
  }

  update(macro) {
    if (!macro) return;
    const dxy = macro.dxy_price ?? macro.dxy ?? 104.18;
    const dxyChg = macro.dxy_change_pct ?? macro.dxy_chg ?? -0.22;
    const us10y = macro.us10y_yield ?? macro.us10y ?? 4.26;
    const us10yChg = macro.us10y_change_pct ?? macro.us10y_chg ?? -0.04;
    const gold = macro.gold_price ?? macro.gold ?? 2678.50;
    const goldChg = macro.gold_change_pct ?? macro.gold_chg ?? 0.68;
    const wti = macro.wti_price ?? macro.wti ?? 73.80;
    const wtiChg = macro.wti_change_pct ?? macro.wti_chg ?? 0.45;
    const gri = macro.global_risk_index ?? macro.gri ?? 72.4;
    const regime = macro.macro_regime ?? macro.regime ?? (gri >= 60 ? "Risk-On" : "Risk-Off");

    if (this.dxyEl) this.dxyEl.innerText = `${Number(dxy).toFixed(2)} (${Number(dxyChg) >= 0 ? "+" : ""}${Number(dxyChg).toFixed(2)}%)`;
    if (this.us10yEl) this.us10yEl.innerText = `${Number(us10y).toFixed(2)}% (${Number(us10yChg) >= 0 ? "+" : ""}${Number(us10yChg).toFixed(2)})`;
    if (this.goldEl) this.goldEl.innerText = `$${Number(gold).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} (${Number(goldChg) >= 0 ? "+" : ""}${Number(goldChg).toFixed(2)}%)`;
    if (this.wtiEl) this.wtiEl.innerText = `$${Number(wti).toFixed(2)} (${Number(wtiChg) >= 0 ? "+" : ""}${Number(wtiChg).toFixed(2)}%)`;
    if (this.griEl) {
      this.griEl.innerText = `${Number(gri).toFixed(1)}/100 (${regime.replace(/_/g, " ")})`;
      this.griEl.className = `val badge-tag ${Number(gri) >= 60 ? "tag-green" : "tag-yellow"}`;
    }
  }
}

window.macroTicker = new MacroTicker();
