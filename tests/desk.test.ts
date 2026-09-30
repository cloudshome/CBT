import request from 'supertest';
import { app } from '../src/server';
import * as binanceService from '../src/services/binanceService';
import { resetGeminiClient } from '../src/services/geminiService';
import { defaultRateLimiter } from '../src/middleware/rateLimit';
import { OHLCVCandle } from '../src/types/candles';

const mockGenerateContent = jest.fn();

jest.mock('@google/genai', () => {
  return {
    GoogleGenAI: jest.fn().mockImplementation(() => ({
      models: {
        generateContent: mockGenerateContent,
      },
    })),
  };
});

describe('Desk Intelligence Endpoints (/api/desk)', () => {
  const originalEnv = process.env;

  const mockCandles: OHLCVCandle[] = [
    [1000, 100.0, 105.0, 98.0, 102.0, 50.0],
    [2000, 102.0, 104.0, 101.0, 103.0, 45.0],
    [3000, 103.0, 120.0, 102.5, 118.0, 200.0],
    [4000, 118.0, 122.0, 108.0, 121.0, 120.0],
    [5000, 121.0, 125.0, 119.0, 124.0, 110.0],
    [6000, 124.0, 128.0, 122.0, 126.0, 130.0],
    [7000, 126.0, 130.0, 125.0, 129.0, 140.0],
    [8000, 129.0, 135.0, 128.0, 134.0, 180.0],
    [9000, 134.0, 138.0, 132.0, 136.0, 160.0],
    [10000, 136.0, 140.0, 135.0, 139.0, 190.0],
  ];

  beforeEach(() => {
    process.env = { ...originalEnv, GEMINI_API_KEY: 'test-fake-key' };
    resetGeminiClient();
    defaultRateLimiter.reset();
    jest.clearAllMocks();
    jest.spyOn(binanceService, 'fetchBinanceCandles').mockResolvedValue(mockCandles);
  });

  afterAll(() => {
    process.env = originalEnv;
  });

  describe('POST /api/desk/ai-brief', () => {
    it('should return 400 if symbol is missing', async () => {
      const res = await request(app).post('/api/desk/ai-brief').send({});
      expect(res.status).toBe(400);
      expect(res.body).toHaveProperty('error');
    });

    it('should return 400 if timeframe is unsupported', async () => {
      const res = await request(app)
        .post('/api/desk/ai-brief')
        .send({ symbol: 'BTCUSDT', timeframe: '30m' });
      expect(res.status).toBe(400);
      expect(res.body.error).toContain('Invalid timeframe');
    });

    it('should return 200 with structured market brief when Gemini succeeds', async () => {
      mockGenerateContent.mockResolvedValueOnce({
        text: JSON.stringify({
          executiveSummary:
            'BTC is currently in a strong bullish expansion phase with active order flow accumulation above key support.',
          bias: 'BULLISH',
          keyLevels: {
            support: [108.0, 102.5],
            resistance: [140.0, 145.0],
            invalidation: 104.0,
          },
          riskAssessment:
            'Watch for potential liquidity grabs near the 140.0 psychological resistance.',
        }),
      });

      const res = await request(app)
        .post('/api/desk/ai-brief')
        .send({ symbol: 'BTCUSDT', timeframe: '15m' });

      expect(res.status).toBe(200);
      expect(res.body.symbol).toBe('BTCUSDT');
      expect(res.body.timeframe).toBe('15m');
      expect(res.body.bias).toBe('BULLISH');
      expect(res.body.executiveSummary).toContain('bullish expansion');
      expect(res.body.keyLevels.support).toEqual([108.0, 102.5]);
      expect(res.body.metrics).toHaveProperty('lastPrice', 139.0);
      expect(res.body.metrics).toHaveProperty('trend');
    });

    it('should return 503 if GEMINI_API_KEY is missing in environment', async () => {
      process.env.GEMINI_API_KEY = '';
      resetGeminiClient();

      const res = await request(app)
        .post('/api/desk/ai-brief')
        .send({ symbol: 'ETHUSDT' });

      expect(res.status).toBe(503);
      expect(res.body.error).toContain('GEMINI_API_KEY is not configured');
    });

    it('should return 503 if Gemini SDK throws an unhandled error', async () => {
      mockGenerateContent.mockRejectedValueOnce(new Error('Network timeout'));

      const res = await request(app)
        .post('/api/desk/ai-brief')
        .send({ symbol: 'BTCUSDT' });

      expect(res.status).toBe(503);
      expect(res.body.error).toContain('Failed to generate market brief from Gemini');
    });
  });

  describe('POST /api/desk/ask', () => {
    it('should return 400 if query is missing', async () => {
      const res = await request(app).post('/api/desk/ask').send({});
      expect(res.status).toBe(400);
      expect(res.body.error).toContain('Field "query" is required');
    });

    it('should return 200 with answer from Gemini', async () => {
      mockGenerateContent.mockResolvedValueOnce({
        text: 'The 15m RSI is currently sitting at 45.2, indicating neutral momentum with room for upside continuation.',
      });

      const res = await request(app)
        .post('/api/desk/ask')
        .send({
          query: 'What is the current momentum reading for BTC?',
          context: { symbol: 'BTCUSDT', rsi: 45.2 },
        });

      expect(res.status).toBe(200);
      expect(res.body.query).toBe('What is the current momentum reading for BTC?');
      expect(res.body.answer).toContain('RSI is currently sitting at 45.2');
      expect(res.body).toHaveProperty('timestamp');
    });

    it('should return 503 if Gemini API fails during Q&A', async () => {
      mockGenerateContent.mockRejectedValueOnce(new Error('API quota reached'));

      const res = await request(app)
        .post('/api/desk/ask')
        .send({ query: 'Explain the current Order Block.' });

      expect(res.status).toBe(503);
      expect(res.body.error).toContain('Desk query failed');
    });
  });
});
