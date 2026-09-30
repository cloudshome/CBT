import { OHLCVCandle, SupportedTimeframe } from '../types/candles';

export class BybitApiError extends Error {
  public statusCode?: number;

  constructor(message: string, statusCode?: number) {
    super(message);
    this.name = 'BybitApiError';
    this.statusCode = statusCode;
  }
}

const DEFAULT_BYBIT_API_URL = 'https://api.bybit.com/v5';

/**
 * Maps normalized timeframe to Bybit interval parameter
 */
export function mapTimeframeToBybitInterval(timeframe: SupportedTimeframe): string {
  switch (timeframe) {
    case '5m':
      return '5';
    case '15m':
      return '15';
    case '1h':
      return '60';
    case '4h':
      return '240';
    case '1d':
      return 'D';
    default:
      return '15';
  }
}

/**
 * Fetches candlestick data from Bybit V5 Public REST API
 */
export async function fetchBybitCandles(
  symbol: string,
  interval: SupportedTimeframe,
  limit: number,
  baseUrl = process.env.BYBIT_API_URL || DEFAULT_BYBIT_API_URL
): Promise<OHLCVCandle[]> {
  const apiSymbol = symbol.toUpperCase() === 'XAUUSDT' ? 'PAXGUSDT' : symbol;
  const bybitInterval = mapTimeframeToBybitInterval(interval);
  const url = new URL(`${baseUrl}/market/kline`);
  url.searchParams.set('category', 'spot');
  url.searchParams.set('symbol', apiSymbol);
  url.searchParams.set('interval', bybitInterval);
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
    throw new BybitApiError(`Network error fetching from Bybit: ${errorMsg}`);
  }

  if (!response.ok) {
    let errorDetail = '';
    try {
      const errJson = (await response.json()) as { retMsg?: string; msg?: string };
      errorDetail = errJson.retMsg || errJson.msg || JSON.stringify(errJson);
    } catch {
      errorDetail = await response.text().catch(() => '');
    }
    throw new BybitApiError(
      `Bybit API responded with status ${response.status}: ${errorDetail}`,
      response.status
    );
  }

  const rawData: unknown = await response.json();
  const bybitResponse = rawData as {
    retCode?: number;
    retMsg?: string;
    result?: {
      list?: Array<Array<string | number>>;
    };
  };

  if (bybitResponse.retCode !== 0 || !bybitResponse.result?.list) {
    throw new BybitApiError(
      `Bybit API error code ${bybitResponse.retCode}: ${bybitResponse.retMsg || 'Invalid response structure'}`
    );
  }

  const rawList = bybitResponse.result.list;

  // Bybit returns klines in DESCENDING order (newest first).
  // Reverse to ensure ASCENDING chronological order [ts, o, h, l, c, v].
  const candles: OHLCVCandle[] = rawList
    .slice()
    .reverse()
    .map((kline) => [
      Number(kline[0]),
      parseFloat(String(kline[1])),
      parseFloat(String(kline[2])),
      parseFloat(String(kline[3])),
      parseFloat(String(kline[4])),
      parseFloat(String(kline[5])),
    ]);

  return candles;
}
