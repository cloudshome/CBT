import {
  Candle,
  DetectionResult,
  FVGItem,
  OrderBlockItem,
  SwingPoint,
  BreakOfStructure,
  StrictQuantOutput,
  SetupSuggestion,
} from "../types";

/**
 * Normalizes various raw candle inputs into typed Candle objects
 */
export function parseAndNormalizeCandles(input: unknown): Candle[] {
  if (!input) return [];

  let rawList: unknown[] = [];
  if (Array.isArray(input)) {
    rawList = input;
  } else if (typeof input === "string") {
    try {
      const parsed = JSON.parse(input);
      if (Array.isArray(parsed)) {
        rawList = parsed;
      } else if (parsed && Array.isArray(parsed.candles)) {
        rawList = parsed.candles;
      }
    } catch {
      return [];
    }
  }

  const candles: Candle[] = [];

  for (let i = 0; i < rawList.length; i++) {
    const item = rawList[i];
    if (Array.isArray(item) && item.length >= 5) {
      const [ts, o, h, l, c, v] = item;
      const timestamp = Number(ts);
      const open = parseFloat(String(o));
      const high = parseFloat(String(h));
      const low = parseFloat(String(l));
      const close = parseFloat(String(c));
      const volume = v !== undefined ? parseFloat(String(v)) : 0;

      if (!isNaN(timestamp) && !isNaN(open) && !isNaN(high) && !isNaN(low) && !isNaN(close)) {
        candles.push({
          timestamp,
          open,
          high: Math.max(open, high, low, close),
          low: Math.min(open, high, low, close),
          close,
          volume: isNaN(volume) ? 0 : volume,
          index: 0,
        });
      }
    } else if (typeof item === "object" && item !== null) {
      const obj = item as Record<string, unknown>;
      const timestamp = Number(obj.timestamp || obj.time || obj.t || obj.openTime || 0);
      const open = parseFloat(String(obj.open || obj.o));
      const high = parseFloat(String(obj.high || obj.h));
      const low = parseFloat(String(obj.low || obj.l));
      const close = parseFloat(String(obj.close || obj.c));
      const volume = parseFloat(String(obj.volume || obj.v || obj.vol || 0));

      if (!isNaN(timestamp) && !isNaN(open) && !isNaN(high) && !isNaN(low) && !isNaN(close)) {
        candles.push({
          timestamp: timestamp || i * 15 * 60 * 1000,
          open,
          high: Math.max(open, high, low, close),
          low: Math.min(open, high, low, close),
          close,
          volume: isNaN(volume) ? 0 : volume,
          index: 0,
        });
      }
    }
  }

  // Sort chronologically by timestamp
  candles.sort((a, b) => a.timestamp - b.timestamp);

  // Assign index
  candles.forEach((c, idx) => {
    c.index = idx;
  });

  return candles;
}

/**
 * Calculates Average True Range (ATR)
 */
function calculateATR(candles: Candle[], period = 14): number[] {
  const atrs: number[] = new Array(candles.length).fill(0);
  if (candles.length === 0) return atrs;

  const trs: number[] = [];
  for (let i = 0; i < candles.length; i++) {
    if (i === 0) {
      trs.push(candles[i].high - candles[i].low);
    } else {
      const prevClose = candles[i - 1].close;
      const tr = Math.max(
        candles[i].high - candles[i].low,
        Math.abs(candles[i].high - prevClose),
        Math.abs(candles[i].low - prevClose)
      );
      trs.push(tr);
    }
  }

  let sum = 0;
  for (let i = 0; i < candles.length; i++) {
    sum += trs[i];
    if (i >= period) {
      sum -= trs[i - period];
      atrs[i] = sum / period;
    } else {
      atrs[i] = sum / (i + 1);
    }
  }

  return atrs;
}

/**
 * Finds Swing Highs and Swing Lows
 */
function findSwingPoints(candles: Candle[], leftStrength = 2, rightStrength = 2): SwingPoint[] {
  const swings: SwingPoint[] = [];
  const n = candles.length;

  for (let i = leftStrength; i < n - rightStrength; i++) {
    const currentHigh = candles[i].high;
    const currentLow = candles[i].low;

    // Check Swing High
    let isSwingHigh = true;
    for (let l = 1; l <= leftStrength; l++) {
      if (candles[i - l].high >= currentHigh) {
        isSwingHigh = false;
        break;
      }
    }
    if (isSwingHigh) {
      for (let r = 1; r <= rightStrength; r++) {
        if (candles[i + r].high >= currentHigh) {
          isSwingHigh = false;
          break;
        }
      }
    }

    if (isSwingHigh) {
      swings.push({
        type: "high",
        price: currentHigh,
        candleIndex: i,
        timestamp: candles[i].timestamp,
      });
    }

    // Check Swing Low
    let isSwingLow = true;
    for (let l = 1; l <= leftStrength; l++) {
      if (candles[i - l].low <= currentLow) {
        isSwingLow = false;
        break;
      }
    }
    if (isSwingLow) {
      for (let r = 1; r <= rightStrength; r++) {
        if (candles[i + r].low <= currentLow) {
          isSwingLow = false;
          break;
        }
      }
    }

    if (isSwingLow) {
      swings.push({
        type: "low",
        price: currentLow,
        candleIndex: i,
        timestamp: candles[i].timestamp,
      });
    }
  }

  return swings;
}

/**
 * Main Quantitative Engine to detect Fair Value Gaps and Order Blocks
 */
export function runQuantDetection(candles: Candle[]): DetectionResult {
  if (candles.length < 3) {
    return {
      output: { fvg: [], order_blocks: [] },
      detailedFVGs: [],
      detailedOrderBlocks: [],
      swings: [],
      bosList: [],
      candles,
      stats: {
        totalCandles: candles.length,
        bullishFVGs: 0,
        bearishFVGs: 0,
        unmitigatedFVGs: 0,
        mitigatedFVGs: 0,
        bullishOBs: 0,
        bearishOBs: 0,
        lastPrice: candles[candles.length - 1]?.close || 0,
        highPrice: 0,
        lowPrice: 0,
        trend: "Insufficient Data",
      },
    };
  }

  const detailedFVGs: FVGItem[] = [];
  const detailedOrderBlocks: OrderBlockItem[] = [];
  const atrs = calculateATR(candles);

  // ----------------------------------------------------
  // 1. Detect Fair Value Gaps (FVG)
  // ----------------------------------------------------
  // 3-candle sequence: [C1, C2, C3] where C1=i-2, C2=i-1, C3=i
  for (let i = 2; i < candles.length; i++) {
    const c1 = candles[i - 2];
    const c2 = candles[i - 1];
    const c3 = candles[i];

    // Bullish FVG:
    // C2 is an impulsive green candle (close > open).
    // Gap between low of candle 3 and high of candle 1: C1.high < C3.low
    if (c2.close > c2.open && c1.high < c3.low) {
      const minPrice = roundPrice(c1.high);
      const maxPrice = roundPrice(c3.low);

      if (maxPrice > minPrice) {
        // Mitigation check: check if any subsequent candle enters or fills the gap
        let mitigated = false;
        let mitigationIndex: number | undefined = undefined;
        let mitigationTimestamp: number | undefined = undefined;

        for (let k = i + 1; k < candles.length; k++) {
          if (candles[k].low <= maxPrice) {
            mitigated = true;
            mitigationIndex = k;
            mitigationTimestamp = candles[k].timestamp;
            break;
          }
        }

        const gapSize = maxPrice - minPrice;
        const gapPercent = (gapSize / minPrice) * 100;

        detailedFVGs.push({
          type: "bullish",
          price_zone: [minPrice, maxPrice],
          mitigated,
          candleIndex: i - 1,
          c1Index: i - 2,
          c2Index: i - 1,
          c3Index: i,
          mitigationIndex,
          mitigationTimestamp,
          timestamp: c2.timestamp,
          gapSize: roundPrice(gapSize),
          gapPercent: Number(gapPercent.toFixed(2)),
        });
      }
    }

    // Bearish FVG:
    // C2 is an impulsive red candle (close < open).
    // Gap between high of candle 3 and low of candle 1: C1.low > C3.high
    if (c2.close < c2.open && c1.low > c3.high) {
      const minPrice = roundPrice(c3.high);
      const maxPrice = roundPrice(c1.low);

      if (maxPrice > minPrice) {
        // Mitigation check: check if any subsequent candle enters or fills the gap
        let mitigated = false;
        let mitigationIndex: number | undefined = undefined;
        let mitigationTimestamp: number | undefined = undefined;

        for (let k = i + 1; k < candles.length; k++) {
          if (candles[k].high >= minPrice) {
            mitigated = true;
            mitigationIndex = k;
            mitigationTimestamp = candles[k].timestamp;
            break;
          }
        }

        const gapSize = maxPrice - minPrice;
        const gapPercent = (gapSize / minPrice) * 100;

        detailedFVGs.push({
          type: "bearish",
          price_zone: [minPrice, maxPrice],
          mitigated,
          candleIndex: i - 1,
          c1Index: i - 2,
          c2Index: i - 1,
          c3Index: i,
          mitigationIndex,
          mitigationTimestamp,
          timestamp: c2.timestamp,
          gapSize: roundPrice(gapSize),
          gapPercent: Number(gapPercent.toFixed(2)),
        });
      }
    }
  }

  // ----------------------------------------------------
  // 2. Detect Swings and Break of Structure (BOS) -> Order Blocks (OB)
  // ----------------------------------------------------
  const swings = findSwingPoints(candles, 2, 2);
  const bosList: BreakOfStructure[] = [];

  // Track active swing highs and lows
  let activeSwingHighs = swings.filter((s) => s.type === "high");
  let activeSwingLows = swings.filter((s) => s.type === "low");

  const recordedOBTimestamps = new Set<number>();

  for (let i = 4; i < candles.length; i++) {
    const candle = candles[i];

    // --- Check Bullish BOS (Break of Swing High) ---
    const validSwingHighs = activeSwingHighs.filter((sh) => sh.candleIndex < i - 1);
    for (const sh of validSwingHighs) {
      if (candle.close > sh.price) {
        const body = Math.abs(candle.close - candle.open);
        const atr = atrs[i] || 1;
        const isDisplacement = body >= atr * 0.7 || candle.close > candle.open;

        if (isDisplacement) {
          bosList.push({
            type: "bullish",
            breakPrice: candle.close,
            swingPrice: sh.price,
            candleIndex: i,
            swingIndex: sh.candleIndex,
            timestamp: candle.timestamp,
          });

          // Last bearish candle before the displacement leg
          let obIndex = -1;
          for (let lookback = i - 1; lookback >= Math.max(0, sh.candleIndex - 3); lookback--) {
            if (candles[lookback].close < candles[lookback].open) {
              obIndex = lookback;
              break;
            }
          }

          if (obIndex !== -1) {
            const obCandle = candles[obIndex];
            if (!recordedOBTimestamps.has(obCandle.timestamp)) {
              recordedOBTimestamps.add(obCandle.timestamp);

              const zoneMin = roundPrice(obCandle.low);
              const zoneMax = roundPrice(obCandle.high);

              // Mitigation check
              let obMitigated = false;
              let obMitigationIndex: number | undefined;
              let obMitigationTs: number | undefined;

              for (let k = i + 1; k < candles.length; k++) {
                if (candles[k].low <= zoneMax && candles[k].low >= zoneMin) {
                  obMitigated = true;
                  obMitigationIndex = k;
                  obMitigationTs = candles[k].timestamp;
                  break;
                }
              }

              detailedOrderBlocks.push({
                type: "bullish",
                price_zone: [zoneMin, zoneMax],
                timestamp: obCandle.timestamp,
                candleIndex: obIndex,
                bosIndex: i,
                bosPrice: candle.close,
                mitigated: obMitigated,
                mitigationIndex: obMitigationIndex,
                mitigationTimestamp: obMitigationTs,
                volume: obCandle.volume,
              });
            }
          }

          activeSwingHighs = activeSwingHighs.filter((s) => s.candleIndex !== sh.candleIndex);
          break;
        }
      }
    }

    // --- Check Bearish BOS (Break of Swing Low) ---
    const validSwingLows = activeSwingLows.filter((sl) => sl.candleIndex < i - 1);
    for (const sl of validSwingLows) {
      if (candle.close < sl.price) {
        const body = Math.abs(candle.close - candle.open);
        const atr = atrs[i] || 1;
        const isDisplacement = body >= atr * 0.7 || candle.close < candle.open;

        if (isDisplacement) {
          bosList.push({
            type: "bearish",
            breakPrice: candle.close,
            swingPrice: sl.price,
            candleIndex: i,
            swingIndex: sl.candleIndex,
            timestamp: candle.timestamp,
          });

          // Last bullish candle before the displacement leg
          let obIndex = -1;
          for (let lookback = i - 1; lookback >= Math.max(0, sl.candleIndex - 3); lookback--) {
            if (candles[lookback].close > candles[lookback].open) {
              obIndex = lookback;
              break;
            }
          }

          if (obIndex !== -1) {
            const obCandle = candles[obIndex];
            if (!recordedOBTimestamps.has(obCandle.timestamp)) {
              recordedOBTimestamps.add(obCandle.timestamp);

              const zoneMin = roundPrice(obCandle.low);
              const zoneMax = roundPrice(obCandle.high);

              // Mitigation check
              let obMitigated = false;
              let obMitigationIndex: number | undefined;
              let obMitigationTs: number | undefined;

              for (let k = i + 1; k < candles.length; k++) {
                if (candles[k].high >= zoneMin && candles[k].high <= zoneMax) {
                  obMitigated = true;
                  obMitigationIndex = k;
                  obMitigationTs = candles[k].timestamp;
                  break;
                }
              }

              detailedOrderBlocks.push({
                type: "bearish",
                price_zone: [zoneMin, zoneMax],
                timestamp: obCandle.timestamp,
                candleIndex: obIndex,
                bosIndex: i,
                bosPrice: candle.close,
                mitigated: obMitigated,
                mitigationIndex: obMitigationIndex,
                mitigationTimestamp: obMitigationTs,
                volume: obCandle.volume,
              });
            }
          }

          activeSwingLows = activeSwingLows.filter((s) => s.candleIndex !== sl.candleIndex);
          break;
        }
      }
    }
  }

  // ----------------------------------------------------
  // 3. Build Strict Output Schema
  // ----------------------------------------------------
  const strictOutput: StrictQuantOutput = {
    fvg: detailedFVGs.map((f) => ({
      type: f.type,
      price_zone: f.price_zone,
      mitigated: f.mitigated,
    })),
    order_blocks: detailedOrderBlocks.map((ob) => ({
      type: ob.type,
      price_zone: ob.price_zone,
      timestamp: ob.timestamp,
    })),
  };

  // ----------------------------------------------------
  // 4. Compute High Level Statistics
  // ----------------------------------------------------
  const bullishFVGs = detailedFVGs.filter((f) => f.type === "bullish").length;
  const bearishFVGs = detailedFVGs.filter((f) => f.type === "bearish").length;
  const unmitigatedFVGs = detailedFVGs.filter((f) => !f.mitigated).length;
  const mitigatedFVGs = detailedFVGs.filter((f) => f.mitigated).length;
  const bullishOBs = detailedOrderBlocks.filter((o) => o.type === "bullish").length;
  const bearishOBs = detailedOrderBlocks.filter((o) => o.type === "bearish").length;

  const prices = candles.flatMap((c) => [c.high, c.low]);
  const highPrice = Math.max(...prices);
  const lowPrice = Math.min(...prices);
  const lastPrice = candles[candles.length - 1]?.close || 0;
  const firstPrice = candles[0]?.open || 0;

  const priceDiffPct = firstPrice > 0 ? ((lastPrice - firstPrice) / firstPrice) * 100 : 0;
  let trend = "Consolidation / Range";
  if (priceDiffPct > 1.5 && bullishOBs >= bearishOBs) {
    trend = "Bullish Order Flow & Expansion";
  } else if (priceDiffPct < -1.5 && bearishOBs >= bullishOBs) {
    trend = "Bearish Order Flow & Distribution";
  }

  return {
    output: strictOutput,
    detailedFVGs,
    detailedOrderBlocks,
    swings,
    bosList,
    candles,
    stats: {
      totalCandles: candles.length,
      bullishFVGs,
      bearishFVGs,
      unmitigatedFVGs,
      mitigatedFVGs,
      bullishOBs,
      bearishOBs,
      lastPrice: roundPrice(lastPrice),
      highPrice: roundPrice(highPrice),
      lowPrice: roundPrice(lowPrice),
      trend,
    },
  };
}

/**
 * Generates actionable trade setup suggestions based on detected SMC structures
 */
export function generateSetups(detection: DetectionResult): SetupSuggestion[] {
  const setups: SetupSuggestion[] = [];
  const { detailedOrderBlocks, detailedFVGs, stats, swings } = detection;
  const { lastPrice, highPrice, lowPrice, trend } = stats;

  const swingHighs = swings.filter((s) => s.type === "high").map((s) => s.price);
  const swingLows = swings.filter((s) => s.type === "low").map((s) => s.price);

  const highestTarget = swingHighs.length > 0 ? Math.max(...swingHighs) : highPrice;
  const lowestTarget = swingLows.length > 0 ? Math.min(...swingLows) : lowPrice;

  // 1. Long setups from unmitigated Bullish Order Blocks or FVGs
  const unmitigatedBullishOB = detailedOrderBlocks
    .filter((ob) => ob.type === "bullish" && !ob.mitigated)
    .sort((a, b) => b.price_zone[1] - a.price_zone[1])[0];

  if (unmitigatedBullishOB) {
    const entry = unmitigatedBullishOB.price_zone[1]; // top of bullish OB
    const stopLoss = roundPrice(unmitigatedBullishOB.price_zone[0] * 0.998); // slightly below bottom
    const takeProfit = highestTarget > entry ? roundPrice(highestTarget) : roundPrice(entry * 1.02);
    const risk = entry - stopLoss;
    const reward = takeProfit - entry;
    const rrr = risk > 0 ? Number((reward / risk).toFixed(2)) : 1.0;

    setups.push({
      type: "LONG",
      bias: trend,
      trigger: `Unmitigated Bullish Order Block at [${unmitigatedBullishOB.price_zone.join(", ")}]`,
      entry,
      stopLoss,
      takeProfit,
      riskRewardRatio: rrr,
    });
  } else {
    // Check unmitigated Bullish FVG
    const unmitigatedBullishFVG = detailedFVGs
      .filter((f) => f.type === "bullish" && !f.mitigated)
      .sort((a, b) => b.price_zone[1] - a.price_zone[1])[0];

    if (unmitigatedBullishFVG) {
      const entry = roundPrice((unmitigatedBullishFVG.price_zone[0] + unmitigatedBullishFVG.price_zone[1]) / 2);
      const stopLoss = roundPrice(unmitigatedBullishFVG.price_zone[0] * 0.998);
      const takeProfit = highestTarget > entry ? roundPrice(highestTarget) : roundPrice(entry * 1.02);
      const risk = entry - stopLoss;
      const reward = takeProfit - entry;
      const rrr = risk > 0 ? Number((reward / risk).toFixed(2)) : 1.0;

      setups.push({
        type: "LONG",
        bias: trend,
        trigger: `Unmitigated Bullish FVG retest at [${unmitigatedBullishFVG.price_zone.join(", ")}]`,
        entry,
        stopLoss,
        takeProfit,
        riskRewardRatio: rrr,
      });
    }
  }

  // 2. Short setups from unmitigated Bearish Order Blocks or FVGs
  const unmitigatedBearishOB = detailedOrderBlocks
    .filter((ob) => ob.type === "bearish" && !ob.mitigated)
    .sort((a, b) => a.price_zone[0] - b.price_zone[0])[0];

  if (unmitigatedBearishOB) {
    const entry = unmitigatedBearishOB.price_zone[0]; // bottom of bearish OB
    const stopLoss = roundPrice(unmitigatedBearishOB.price_zone[1] * 1.002); // slightly above top
    const takeProfit = lowestTarget < entry ? roundPrice(lowestTarget) : roundPrice(entry * 0.98);
    const risk = stopLoss - entry;
    const reward = entry - takeProfit;
    const rrr = risk > 0 ? Number((reward / risk).toFixed(2)) : 1.0;

    setups.push({
      type: "SHORT",
      bias: trend,
      trigger: `Unmitigated Bearish Order Block at [${unmitigatedBearishOB.price_zone.join(", ")}]`,
      entry,
      stopLoss,
      takeProfit,
      riskRewardRatio: rrr,
    });
  } else {
    // Check unmitigated Bearish FVG
    const unmitigatedBearishFVG = detailedFVGs
      .filter((f) => f.type === "bearish" && !f.mitigated)
      .sort((a, b) => a.price_zone[0] - b.price_zone[0])[0];

    if (unmitigatedBearishFVG) {
      const entry = roundPrice((unmitigatedBearishFVG.price_zone[0] + unmitigatedBearishFVG.price_zone[1]) / 2);
      const stopLoss = roundPrice(unmitigatedBearishFVG.price_zone[1] * 1.002);
      const takeProfit = lowestTarget < entry ? roundPrice(lowestTarget) : roundPrice(entry * 0.98);
      const risk = stopLoss - entry;
      const reward = entry - takeProfit;
      const rrr = risk > 0 ? Number((reward / risk).toFixed(2)) : 1.0;

      setups.push({
        type: "SHORT",
        bias: trend,
        trigger: `Unmitigated Bearish FVG retest at [${unmitigatedBearishFVG.price_zone.join(", ")}]`,
        entry,
        stopLoss,
        takeProfit,
        riskRewardRatio: rrr,
      });
    }
  }

  // 3. Fallback generic setup if no unmitigated SMC structures found but candles exist
  if (setups.length === 0 && lastPrice > 0) {
    if (trend.includes("Bullish")) {
      const entry = roundPrice(lastPrice * 0.995);
      const stopLoss = roundPrice(lowPrice > 0 && lowPrice < entry ? lowPrice * 0.998 : entry * 0.985);
      const takeProfit = roundPrice(highPrice > entry ? highPrice : entry * 1.02);
      const risk = entry - stopLoss;
      const reward = takeProfit - entry;
      setups.push({
        type: "LONG",
        bias: trend,
        trigger: "Trend continuation pullback",
        entry,
        stopLoss,
        takeProfit,
        riskRewardRatio: risk > 0 ? Number((reward / risk).toFixed(2)) : 1.5,
      });
    } else {
      const entry = roundPrice(lastPrice * 1.005);
      const stopLoss = roundPrice(highPrice > entry ? highPrice * 1.002 : entry * 1.015);
      const takeProfit = roundPrice(lowPrice > 0 && lowPrice < entry ? lowPrice : entry * 0.98);
      const risk = stopLoss - entry;
      const reward = entry - takeProfit;
      setups.push({
        type: "SHORT",
        bias: trend,
        trigger: "Trend continuation distribution",
        entry,
        stopLoss,
        takeProfit,
        riskRewardRatio: risk > 0 ? Number((reward / risk).toFixed(2)) : 1.5,
      });
    }
  }

  return setups;
}

/**
 * Rounds price to appropriate precision based on magnitude
 */
function roundPrice(val: number): number {
  if (val > 1000) return Number(val.toFixed(2));
  if (val > 10) return Number(val.toFixed(3));
  if (val > 1) return Number(val.toFixed(4));
  return Number(val.toFixed(6));
}
