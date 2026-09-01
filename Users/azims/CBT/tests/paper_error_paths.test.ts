import request from 'supertest';
import { app } from '../src/server';
import { prisma } from '../src/db/prisma';
import { defaultRateLimiter } from '../src/middleware/rateLimit';

describe('Paper Trading Error Paths & Edge Cases (P1 Coverage)', () => {
  beforeAll(async () => {
    await prisma.$connect();
  });

  beforeEach(async () => {
    await prisma.paperTrade.deleteMany({});
    await prisma.riskConfig.deleteMany({});

    // Seed standard risk config
    await prisma.riskConfig.create({
      data: {
        accountBalance: 100000.0,
        maxDrawdown: 0.1,
        maxOpenTrades: 3,
        dailyLossLimit: 0.05,
        maxRiskPerTrade: 0.02,
      },
    });

    defaultRateLimiter.reset();
  });

  afterAll(async () => {
    await prisma.paperTrade.deleteMany({});
    await prisma.riskConfig.deleteMany({});
    await prisma.$disconnect();
  });

  describe('Reconciliation Endpoint Input & Edge Cases', () => {
    it('should return 400 if prices object is missing or null', async () => {
      const res = await request(app).post('/api/paper/reconcile').send({});
      expect(res.status).toBe(400);
      expect(res.body.error).toContain('Missing or invalid prices object');
    });

    it('should return 400 if prices parameter is not an object', async () => {
      const res = await request(app).post('/api/paper/reconcile').send({ prices: 'invalid_string' });
      expect(res.status).toBe(400);
      expect(res.body.error).toContain('Missing or invalid prices object');
    });

    it('should automatically close BUY trade when current price hits SL', async () => {
      const trade = await prisma.paperTrade.create({
        data: {
          symbol: 'ETHUSDT',
          side: 'BUY',
          entryPrice: 3000,
          sl: 2900,
          tp: 3300,
          size: 2.0,
          status: 'OPEN',
        },
      });

      const res = await request(app).post('/api/paper/reconcile').send({
        prices: { ETHUSDT: 2850 }, // Price below SL
      });

      expect(res.status).toBe(200);
      const updated = await prisma.paperTrade.findUnique({ where: { id: trade.id } });
      expect(updated?.status).toBe('CLOSED');
      expect(updated?.pnl).toBeLessThan(0);
    });

    it('should automatically close SHORT trade when current price hits TP', async () => {
      const trade = await prisma.paperTrade.create({
        data: {
          symbol: 'SOLUSDT',
          side: 'SELL',
          entryPrice: 150,
          sl: 160,
          tp: 130,
          size: 10.0,
          status: 'OPEN',
        },
      });

      const res = await request(app).post('/api/paper/reconcile').send({
        prices: { SOLUSDT: 125 }, // Price below TP for short
      });

      expect(res.status).toBe(200);
      const updated = await prisma.paperTrade.findUnique({ where: { id: trade.id } });
      expect(updated?.status).toBe('CLOSED');
      expect(updated?.pnl).toBeGreaterThan(0);
    });

    it('should leave trade OPEN when current price is between SL and TP', async () => {
      const trade = await prisma.paperTrade.create({
        data: {
          symbol: 'BTCUSDT',
          side: 'BUY',
          entryPrice: 65000,
          sl: 64000,
          tp: 68000,
          size: 1.0,
          status: 'OPEN',
        },
      });

      const res = await request(app).post('/api/paper/reconcile').send({
        prices: { BTCUSDT: 66000 },
      });

      expect(res.status).toBe(200);
      const updated = await prisma.paperTrade.findUnique({ where: { id: trade.id } });
      expect(updated?.status).toBe('OPEN');
    });
  });

  describe('Positions & Config Queries', () => {
    it('should retrieve empty positions list when no open trades exist', async () => {
      const res = await request(app).get('/api/paper/positions');
      expect(res.status).toBe(200);
      expect(res.body.positions).toEqual([]);
      expect(res.body.count).toBe(0);
    });

    it('should return fallback default risk config if none seeded', async () => {
      await prisma.riskConfig.deleteMany({});
      const res = await request(app).get('/api/paper/config');
      expect(res.status).toBe(200);
      expect(res.body.config).toHaveProperty('accountBalance', 100000);
    });
  });
});
