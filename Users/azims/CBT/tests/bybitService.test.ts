import {
  fetchBybitCandles,
  mapTimeframeToBybitInterval,
  BybitApiError,
} from '../src/services/bybitService';
import { SupportedTimeframe } from '../src/types/candles';

describe('Bybit Service Unit Tests (P0 Coverage)', () => {
  const originalFetch = global.fetch;

  afterEach(() => {
    global.fetch = originalFetch;
    jest.restoreAllMocks();
  });

  describe('mapTimeframeToBybitInterval', () => {
    it('should map standard timeframes accurately', () => {
      expect(mapTimeframeToBybitInterval('5m')).toBe('5');
      expect(mapTimeframeToBybitInterval('15m')).toBe('15');
      expect(mapTimeframeToBybitInterval('1h')).toBe('60');
      expect(mapTimeframeToBybitInterval('4h')).toBe('240');
      expect(mapTimeframeToBybitInterval('1d')).toBe('D');
    });

    it('should fallback to 15 for unknown timeframe', () => {
      expect(mapTimeframeToBybitInterval('unknown' as SupportedTimeframe)).toBe('15');
    });
  });

  describe('fetchBybitCandles', () => {
    it('should fetch and format candles in chronological ascending order', async () => {
      const mockBybitResponse = {
        retCode: 0,
        retMsg: 'OK',
        result: {
          list: [
            ['2000', '102.0', '105.0', '101.0', '104.0', '50.0'], // Newer (timestamp 2000)
            ['1000', '100.0', '103.0', '99.0', '102.0', '40.0'],  // Older (timestamp 1000)
          ],
        },
      };

      global.fetch = jest.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => mockBybitResponse,
      } as unknown as Response);

      const candles = await fetchBybitCandles('BTCUSDT', '15m', 2);
      expect(candles).toHaveLength(2);
      // Ascending check: index 0 should be timestamp 1000, index 1 should be 2000
      expect(candles[0][0]).toBe(1000);
      expect(candles[0][1]).toBe(100.0);
      expect(candles[1][0]).toBe(2000);
      expect(candles[1][1]).toBe(102.0);
    });

    it('should map XAUUSDT to PAXGUSDT for spot market queries', async () => {
      let requestedUrl = '';
      global.fetch = jest.fn().mockImplementation((url: string) => {
        requestedUrl = url;
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({
            retCode: 0,
            result: { list: [['1000', '2600.0', '2610.0', '2590.0', '2605.0', '10.0']] },
          }),
        } as unknown as Response);
      });

      const candles = await fetchBybitCandles('XAUUSDT', '1h', 1);
      expect(requestedUrl).toContain('symbol=PAXGUSDT');
      expect(candles).toHaveLength(1);
    });

    it('should throw BybitApiError on network failure', async () => {
      global.fetch = jest.fn().mockRejectedValue(new Error('Connection timed out'));

      await expect(fetchBybitCandles('BTCUSDT', '15m', 10)).rejects.toThrow(BybitApiError);
      await expect(fetchBybitCandles('BTCUSDT', '15m', 10)).rejects.toThrow(
        /Network error fetching from Bybit: Connection timed out/
      );
    });

    it('should handle non-200 HTTP response with JSON error detail', async () => {
      global.fetch = jest.fn().mockResolvedValue({
        ok: false,
        status: 400,
        json: async () => ({ retMsg: 'Invalid symbol specified' }),
      } as unknown as Response);

      await expect(fetchBybitCandles('INVALID', '15m', 10)).rejects.toThrow(
        /Bybit API responded with status 400: Invalid symbol specified/
      );
    });

    it('should handle non-200 HTTP response with text fallback error detail', async () => {
      global.fetch = jest.fn().mockResolvedValue({
        ok: false,
        status: 502,
        json: async () => {
          throw new Error('Not JSON');
        },
        text: async () => 'Bad Gateway upstream error',
      } as unknown as Response);

      await expect(fetchBybitCandles('BTCUSDT', '15m', 10)).rejects.toThrow(
        /Bybit API responded with status 502: Bad Gateway upstream error/
      );
    });

    it('should throw BybitApiError if Bybit retCode is non-zero', async () => {
      global.fetch = jest.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          retCode: 10001,
          retMsg: 'Parameter error: symbol not supported',
          result: {},
        }),
      } as unknown as Response);

      await expect(fetchBybitCandles('BADSYM', '15m', 5)).rejects.toThrow(
        /Bybit API error code 10001: Parameter error: symbol not supported/
      );
    });

    it('should throw BybitApiError if result list is missing', async () => {
      global.fetch = jest.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          retCode: 0,
          retMsg: '',
          result: {},
        }),
      } as unknown as Response);

      await expect(fetchBybitCandles('BTCUSDT', '15m', 5)).rejects.toThrow(
        /Invalid response structure/
      );
    });
  });
});
