import request from 'supertest';
import { app } from '../src/server';
import { prisma } from '../src/db/prisma';
import { defaultRateLimiter } from '../src/middleware/rateLimit';

describe('Paper Trading & Risk Gate Endpoints (/api/paper)', () => {
  beforeAll(async () => {
    await prisma.$connect();
  });

  beforeEach(async () => {
    await prisma.paperTrade.deleteMany({});
    await prisma.riskConfig.deleteMany({});

    // Seed standard $100k account risk config
    await prisma.riskConfig.create({
      data: {
        accountBalance: 100000.0,
        maxDrawdown: 0.1,
        maxOpenTrades: 3,
        dailyLossLimit: 0.05,
        maxRiskPerTrade: 0.02, // $2,000 max risk
      },
    });

    defaultRateLimiter.reset();
  });

  afterAll(async () => {
    await prisma.paperTrade.deleteMany({});
    await prisma.riskConfig.deleteMany({});
    await prisma.$disconnect();
  });

  describe('Input & Directional Validation', () => {
    it('should return 400 if required fields are missing', async () => {
      const res = await request(app).post('/api/paper/trade').send({
        symbol: 'BTCUSDT',
        side: 'BUY',
      });
      expect(res.status).toBe(400);
      expect(res.body).toHaveProperty('error');
    });

    it('should return 400 if side is invalid', async () => {
      const res = await request(app).post('/api/paper/trade').send({
        symbol: 'BTCUSDT',
        side: 'HOLD',
        entryPrice: 65000,
        sl: 64000,
        tp: 67000,
      });
      expect(res.status).toBe(400);
      expect(res.body.error).toContain('Invalid side');
    });

    it('should return 400 for BUY if SL is above entry or TP is below entry', async () => {
      const res = await request(app).post('/api/paper/trade').send({
        symbol: 'BTCUSDT',
        side: 'BUY',
        entryPrice: 65000,
        sl: 66000, // Invalid: above entry
        tp: 67000,
      });
      expect(res.status).toBe(400);
      expect(res.body.error).toContain('Stop Loss must be below Entry Price');
    });

    it('should return 400 for SELL if SL is below entry or TP is above entry', async () => {
      const res = await request(app).post('/api/paper/trade').send({
        symbol: 'BTCUSDT',
        side: 'SELL',
        entryPrice: 65000,
        sl: 64000, // Invalid: below entry
        tp: 62000,
      });
      expect(res.status).toBe(400);
      expect(res.body.error).toContain('Stop Loss must be above Entry Price');
    });
  });

  describe('Risk Gate Enforcement (Rule 1: Max Open Trades)', () => {
    it('should reject trades with 403 Forbidden when max open trades limit (3) is reached', async () => {
      // Seed 3 open trades
      await prisma.paperTrade.createMany({
        data: [
          { symbol: 'BTCUSDT', side: 'BUY', entryPrice: 65000, sl: 64500, tp: 67000, size: 1.0, status: 'OPEN' },
          { symbol: 'ETHUSDT', side: 'BUY', entryPrice: 3500, sl: 3450, tp: 3700, size: 10.0, status: 'OPEN' },
          { symbol: 'SOLUSDT', side: 'BUY', entryPrice: 150, sl: 145, tp: 165, size: 50.0, status: 'OPEN' },
        ],
      });

      // Attempt 4th trade with low risk
      const res = await request(app).post('/api/paper/trade').send({
        symbol: 'BNBUSDT',
        side: 'BUY',
        entryPrice: 600,
        sl: 595,
        tp: 620,
        size: 10.0, // Risk: $50
      });

      expect(res.status).toBe(403);
      expect(res.body.error).toContain('Maximum open trades limit reached');
      expect(res.body.currentOpenTrades).toBe(3);
    });
  });

  describe('Risk Gate Enforcement (Rule 2: Max 2% Account Risk)', () => {
    it('should reject trade with 403 Forbidden if trade dollar risk exceeds 2% ($2,000)', async () => {
      // Account balance: $100,000 -> Max allowed risk: $2,000
      // Trade: Entry 65,000, SL 62,000 (distance $3,000) with size 1.0 -> Risk = $3,000
      const res = await request(app).post('/api/paper/trade').send({
        symbol: 'BTCUSDT',
        side: 'BUY',
        entryPrice: 65000,
        sl: 62000,
        tp: 72000,
        size: 1.0,
      });

      expect(res.status).toBe(403);
      expect(res.body.error).toContain('Trade risk ($3000.00) exceeds maximum allowable risk of 2% ($2000.00)');
      expect(res.body.tradeRisk).toBe(3000);
      expect(res.body.maxAllowedRisk).toBe(2000);
    });

    it('should allow trade when trade risk is within 2% limit ($2,000)', async () => {
      // Trade: Entry 65,000, SL 64,000 (distance $1,000) with size 1.0 -> Risk = $1,000 <= $2,000
      const res = await request(app).post('/api/paper/trade').send({
        symbol: 'BTCUSDT',
        side: 'BUY',
        entryPrice: 65000,
        sl: 64000,
        tp: 68000,
        size: 1.0,
      });

      expect(res.status).toBe(201);
      expect(res.body.message).toContain('Paper trade executed successfully');
      expect(res.body.trade).toHaveProperty('id');
      expect(res.body.trade.symbol).toBe('BTCUSDT');
      expect(res.body.trade.status).toBe('OPEN');
    });
  });

  describe('Risk Gate Enforcement (Rule 3: Daily Loss Limit)', () => {
    it('should reject trade with 403 when daily realized losses hit 5% ($5,000)', async () => {
      // Seed a closed loss of -$5,500 today
      await prisma.paperTrade.create({
        data: {
          symbol: 'BTCUSDT',
          side: 'BUY',
          entryPrice: 65000,
          sl: 64000,
          tp: 68000,
          size: 5.5,
          status: 'CLOSED',
          exitPrice: 64000,
          pnl: -5500.0,
          closedAt: new Date(),
        },
      });

      const res = await request(app).post('/api/paper/trade').send({
        symbol: 'ETHUSDT',
        side: 'BUY',
        entryPrice: 3500,
        sl: 3450,
        tp: 3700,
        size: 1.0,
      });

      expect(res.status).toBe(403);
      expect(res.body.error).toContain('Daily loss limit reached');
    });
  });

  describe('GET /api/paper/positions', () => {
    it('should return list of all active open positions', async () => {
      await prisma.paperTrade.create({
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

      const res = await request(app).get('/api/paper/positions');
      expect(res.status).toBe(200);
      expect(res.body.count).toBe(1);
      expect(res.body.positions[0].symbol).toBe('BTCUSDT');
      expect(res.body.positions[0].status).toBe('OPEN');
    });
  });

  describe('POST /api/paper/reconcile', () => {
    it('should automatically close long position hitting take profit', async () => {
      await prisma.paperTrade.create({
        data: {
          symbol: 'BTCUSDT',
          side: 'LONG',
          entryPrice: 65000,
          sl: 64000,
          tp: 68000,
          size: 1.5,
          status: 'OPEN',
        },
      });

      const res = await request(app)
        .post('/api/paper/reconcile')
        .send({ prices: { BTCUSDT: 68500 } });

      expect(res.status).toBe(200);
      expect(res.body.result.closedCount).toBe(1);
      expect(res.body.result.closedTrades[0].reason).toBe('TAKE_PROFIT');
      expect(res.body.result.closedTrades[0].pnl).toBe((68500 - 65000) * 1.5);

      const updated = await prisma.paperTrade.findFirst({ where: { symbol: 'BTCUSDT' } });
      expect(updated?.status).toBe('CLOSED');
      expect(updated?.exitPrice).toBe(68500);
    });

    it('should automatically close short position hitting stop loss', async () => {
      await prisma.paperTrade.create({
        data: {
          symbol: 'ETHUSDT',
          side: 'SHORT',
          entryPrice: 3500,
          sl: 3600,
          tp: 3300,
          size: 2.0,
          status: 'OPEN',
        },
      });

      const res = await request(app)
        .post('/api/paper/reconcile')
        .send({ prices: { ETHUSDT: 3650 } });

      expect(res.status).toBe(200);
      expect(res.body.result.closedCount).toBe(1);
      expect(res.body.result.closedTrades[0].reason).toBe('STOP_LOSS');
      expect(res.body.result.closedTrades[0].pnl).toBe((3500 - 3650) * 2.0);
    });
  });
});

