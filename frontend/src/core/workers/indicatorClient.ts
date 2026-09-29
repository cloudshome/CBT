import {
  WorkerCandle,
  IndicatorRequestMessage,
  IndicatorResponseMessage,
  IndicatorPointResult,
} from './indicatorWorker';

class IndicatorClient {
  private worker: Worker | null = null;
  private pendingRequests = new Map<string, (res: IndicatorResponseMessage) => void>();

  constructor() {
    this.initWorker();
  }

  private initWorker() {
    if (typeof window !== 'undefined' && typeof Worker !== 'undefined') {
      try {
        // Vite supports inline web worker instantiation via new URL with import.meta.url
        this.worker = new Worker(
          new URL('./indicatorWorker.ts', import.meta.url),
          { type: 'module' }
        );

        this.worker.onmessage = (event: MessageEvent<IndicatorResponseMessage>) => {
          const { id } = event.data;
          const resolve = this.pendingRequests.get(id);
          if (resolve) {
            resolve(event.data);
            this.pendingRequests.delete(id);
          }
        };

        this.worker.onerror = (err) => {
          console.warn('Indicator Web Worker error:', err);
        };
      } catch (e) {
        console.warn('Web Worker initialization failed, using inline fallback:', e);
        this.worker = null;
      }
    }
  }

  /**
   * Computes indicators using the background Web Worker with automatic resolution.
   */
  public calculateIndicators(
    candles: WorkerCandle[],
    options: {
      emaPeriods?: number[];
      rsiPeriod?: number;
      atrPeriod?: number;
      bollingerPeriod?: number;
      bollingerStdDev?: number;
      vwap?: boolean;
    }
  ): Promise<IndicatorResponseMessage> {
    const id = Math.random().toString(36).substring(2, 9);

    if (this.worker) {
      return new Promise((resolve) => {
        this.pendingRequests.set(id, resolve);
        const req: IndicatorRequestMessage = {
          id,
          candles,
          indicators: options,
        };
        this.worker!.postMessage(req);
      });
    }

    // Inline fallback if worker not available
    return Promise.resolve(this.computeInline(id, candles, options));
  }

  private computeInline(
    id: string,
    candles: WorkerCandle[],
    options: {
      emaPeriods?: number[];
      rsiPeriod?: number;
      atrPeriod?: number;
      bollingerPeriod?: number;
      bollingerStdDev?: number;
      vwap?: boolean;
    }
  ): IndicatorResponseMessage {
    const emaMap: Record<number, IndicatorPointResult[]> = {};
    if (options.emaPeriods) {
      for (const p of options.emaPeriods) {
        emaMap[p] = this.computeSimpleEMA(candles, p);
      }
    }

    return {
      id,
      ema: emaMap,
      rsi: [],
      atr: [],
      bollingerBands: { upper: [], middle: [], lower: [] },
      vwap: { vwap: [], upper1s: [], lower1s: [], upper2s: [], lower2s: [] },
    };
  }

  private computeSimpleEMA(candles: WorkerCandle[], period: number): IndicatorPointResult[] {
    if (candles.length < period) return [];
    const k = 2 / (period + 1);
    const results: IndicatorPointResult[] = [];
    let sum = 0;
    for (let i = 0; i < period; i++) sum += candles[i].close;
    let prev = sum / period;
    results.push({ time: Math.floor(candles[period - 1].timestamp / 1000), value: Number(prev.toFixed(4)) });

    for (let i = period; i < candles.length; i++) {
      const cur = (candles[i].close - prev) * k + prev;
      results.push({ time: Math.floor(candles[i].timestamp / 1000), value: Number(cur.toFixed(4)) });
      prev = cur;
    }
    return results;
  }
}

export const indicatorClient = new IndicatorClient();
