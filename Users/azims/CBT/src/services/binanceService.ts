import { OHLCVCandle, SupportedTimeframe } from '../types/candles';

export class BinanceApiError extends Error {
  public statusCode?: number;

  constructor(message: string, statusCode?: number) {
    super(message);
    this.name = 'BinanceApiError';
    this.statusCode = statusCode;
  }
}

const DEFAULT_BINANCE_API_URL = 'https://api.binance.com/api/v3';

/**
 * Fetches candlestick data from Binance REST API
 */
export async function fetchBinanceCandles(
  symbol: string,
  interval: SupportedTimeframe,
  limit: number,
  baseUrl = process.env.BINANCE_API_URL || DEFAULT_BINANCE_API_URL
): Promise<OHLCVCandle[]> {
  const apiSymbol = symbol.toUpperCase() === 'XAUUSDT' ? 'PAXGUSDT' : symbol;
  const url = new URL(`${baseUrl}/klines`);
  url.searchParams.set('symbol', apiSymbol);
  url.searchParams.set('interval', interval);
  url.searchParams.set('limit', String(limit));

  let response: Response;
  try {
    response = await fetch(url.toString(), {
      method: 'GET',
      headers: {
        Accept: 'application/json',
      },
      signal: AbortSignal.timeout(8000),
    });
  } catch (error: unknown) {
    const errorMsg = error instanceof Error ? error.message : String(error);
    throw new BinanceApiError(`Network error fetching from Binance: ${errorMsg}`);
  }

  if (!response.ok) {
    let errorDetail = '';
    try {
      const errJson = (await response.json()) as { msg?: string };
      errorDetail = errJson.msg || JSON.stringify(errJson);
    } catch {
      errorDetail = await response.text().catch(() => '');
    }
    throw new BinanceApiError(
      `Binance API responded with status ${response.status}: ${errorDetail}`,
      response.status
    );
  }

  const rawData: unknown = await response.json();
  if (!Array.isArray(rawData)) {
    throw new BinanceApiError('Unexpected response format from Binance API');
  }

  const rawKlines = rawData as Array<Array<string | number>>;
  const candles: OHLCVCandle[] = rawKlines.map((kline) => [
    Number(kline[0]),
    parseFloat(String(kline[1])),
    parseFloat(String(kline[2])),
    parseFloat(String(kline[3])),
    parseFloat(String(kline[4])),
    parseFloat(String(kline[5])),
  ]);

  return candles;
}
