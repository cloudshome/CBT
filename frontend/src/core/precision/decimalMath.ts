import Decimal from 'decimal.js';

// Configure high-precision decimal configuration (30 significant digits, standard rounding)
Decimal.set({ precision: 30, rounding: Decimal.ROUND_HALF_UP });

export const PrecisionMath = {
  /**
   * Adds two numbers with exact decimal arithmetic.
   */
  add(a: number | string, b: number | string): number {
    return new Decimal(a).plus(b).toNumber();
  },

  /**
   * Subtracts b from a.
   */
  sub(a: number | string, b: number | string): number {
    return new Decimal(a).minus(b).toNumber();
  },

  /**
   * Multiplies a and b.
   */
  mul(a: number | string, b: number | string): number {
    return new Decimal(a).times(b).toNumber();
  },

  /**
   * Divides a by b safely avoiding division by zero.
   */
  div(a: number | string, b: number | string): number {
    const decB = new Decimal(b);
    if (decB.isZero()) return 0;
    return new Decimal(a).dividedBy(decB).toNumber();
  },

  /**
   * Calculates position sizing based on strict account risk.
   * size_base = (equity * risk_pct) / abs(entry - stop_loss)
   */
  calculatePositionSize(
    equity: number,
    riskPct: number,
    entryPrice: number,
    stopLoss: number
  ): {
    riskAmountUsd: number;
    positionSizeBase: number;
    positionSizeQuote: number;
    stopDistancePct: number;
  } {
    if (entryPrice <= 0 || stopLoss <= 0 || equity <= 0) {
      return { riskAmountUsd: 0, positionSizeBase: 0, positionSizeQuote: 0, stopDistancePct: 0 };
    }

    const eq = new Decimal(equity);
    const rPct = new Decimal(riskPct);
    const entry = new Decimal(entryPrice);
    const sl = new Decimal(stopLoss);

    const riskAmount = eq.times(rPct);
    const stopDistance = entry.minus(sl).abs();

    if (stopDistance.isZero()) {
      return { riskAmountUsd: riskAmount.toNumber(), positionSizeBase: 0, positionSizeQuote: 0, stopDistancePct: 0 };
    }

    const sizeBase = riskAmount.dividedBy(stopDistance);
    const sizeQuote = sizeBase.times(entry);
    const stopDistPct = stopDistance.dividedBy(entry).times(100);

    return {
      riskAmountUsd: Number(riskAmount.toFixed(2)),
      positionSizeBase: Number(sizeBase.toFixed(6)),
      positionSizeQuote: Number(sizeQuote.toFixed(2)),
      stopDistancePct: Number(stopDistPct.toFixed(2)),
    };
  },

  /**
   * Calculates isolated margin liquidation price for Long/Short with leverage.
   */
  calculateLiquidationPrice(
    entryPrice: number,
    side: 'LONG' | 'SHORT',
    leverage: number,
    maintenanceMarginRate = 0.005
  ): number {
    if (entryPrice <= 0 || leverage <= 0) return 0;

    const entry = new Decimal(entryPrice);
    const lev = new Decimal(leverage);
    const mmr = new Decimal(maintenanceMarginRate);

    // Initial Margin Rate = 1 / Leverage
    const imr = new Decimal(1).dividedBy(lev);

    if (side === 'LONG') {
      // Long Liq = Entry * (1 - IMR + MMR)
      const factor = new Decimal(1).minus(imr).plus(mmr);
      return Math.max(0, entry.times(factor).toNumber());
    } else {
      // Short Liq = Entry * (1 + IMR - MMR)
      const factor = new Decimal(1).plus(imr).minus(mmr);
      return entry.times(factor).toNumber();
    }
  },

  /**
   * Formats crypto prices with appropriate decimal places according to asset value.
   */
  formatPrice(price: number): string {
    if (price >= 1000) return price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    if (price >= 1) return price.toFixed(4);
    return price.toFixed(6);
  },
};
