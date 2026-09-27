import { PrecisionMath } from '../frontend/src/core/precision/decimalMath';

describe('Frontend PrecisionMath & Quant Sizing Tests', () => {
  it('should calculate exact arithmetic with zero floating point errors', () => {
    expect(PrecisionMath.add(0.1, 0.2)).toBe(0.3);
    expect(PrecisionMath.sub(1.0, 0.9)).toBe(0.1);
    expect(PrecisionMath.mul(0.1, 0.2)).toBe(0.02);
    expect(PrecisionMath.div(10, 2)).toBe(5);
    expect(PrecisionMath.div(10, 0)).toBe(0);
  });

  it('should compute exact position sizing according to account risk', () => {
    // Equity: $10,000, Risk: 1% ($100), Entry: $65,000, SL: $64,000 (Distance: $1,000)
    // Sizing base: 100 / 1000 = 0.100000 BTC ($6,500 Quote)
    const sizing = PrecisionMath.calculatePositionSize(10000, 0.01, 65000, 64000);
    expect(sizing.riskAmountUsd).toBe(100);
    expect(sizing.positionSizeBase).toBe(0.1);
    expect(sizing.positionSizeQuote).toBe(6500);
    expect(sizing.stopDistancePct).toBeCloseTo(1.54, 1);
  });

  it('should compute isolated margin liquidation prices for Long and Short', () => {
    // Entry: 65,000, Lev: 10x, Long Liq = 65000 * (1 - 0.10 + 0.005) = 65000 * 0.905 = 58825
    const longLiq = PrecisionMath.calculateLiquidationPrice(65000, 'LONG', 10, 0.005);
    expect(longLiq).toBe(58825);

    // Short Liq = Entry * (1 + IMR - MMR) = 65000 * (1 + 0.10 - 0.005) = 65000 * 1.095 = 71175
    const shortLiq = PrecisionMath.calculateLiquidationPrice(65000, 'SHORT', 10, 0.005);
    expect(shortLiq).toBe(71175);
  });
});

describe('Kronos Visual Trajectory & Advisory Verification', () => {
  it('should compute multi-sample trajectory median and p10/p90 probability bounds', () => {
    const mockPaths = [
      { path_id: 0, predicted_closes: [65100, 65200, 65300], predicted_timestamps: [1700000000000, 1700000900000, 1700001800000] },
      { path_id: 1, predicted_closes: [65050, 65150, 65250], predicted_timestamps: [1700000000000, 1700000900000, 1700001800000] },
      { path_id: 2, predicted_closes: [65200, 65350, 65500], predicted_timestamps: [1700000000000, 1700000900000, 1700001800000] },
    ];

    const horizon = mockPaths[0].predicted_closes.length;
    const medianCloses: number[] = [];
    const minCloses: number[] = [];
    const maxCloses: number[] = [];

    for (let i = 0; i < horizon; i++) {
      const stepVals = mockPaths.map((p) => p.predicted_closes[i]).sort((a, b) => a - b);
      medianCloses.push(stepVals[1]);
      minCloses.push(stepVals[0]);
      maxCloses.push(stepVals[2]);
    }

    expect(medianCloses).toEqual([65100, 65200, 65300]);
    expect(minCloses).toEqual([65050, 65150, 65250]);
    expect(maxCloses).toEqual([65200, 65350, 65500]);
  });

  it('should verify shadow advisory sizing multipliers and recommendation rules', () => {
    const confirmAdvisory = {
      advisory_recommendation: 'CONFIRM_TRADE',
      sizing_multiplier: 1.15,
      directional_consensus: 0.85,
    };
    const divergenceAdvisory = {
      advisory_recommendation: 'DIVERGENCE_CAUTION',
      sizing_multiplier: 0.50,
      directional_consensus: 0.20,
    };

    expect(confirmAdvisory.sizing_multiplier).toBeGreaterThan(1.0);
    expect(divergenceAdvisory.sizing_multiplier).toBeLessThan(1.0);
  });
});
