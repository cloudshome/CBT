import request from 'supertest';
import { app } from '../src/server';
import { prisma } from '../src/db/prisma';
import { defaultRateLimiter } from '../src/middleware/rateLimit';

describe('E2E Desk Order Lifecycle Integration Test (Task K-UI.4)', () => {
  beforeAll(async () => {
    await prisma.$connect();
  });

  beforeEach(async () => {
    await prisma.paperTrade.deleteMany({});
    await prisma.riskConfig.deleteMany({});

    // Seed $50k institutional account
    await prisma.riskConfig.create({
      data: {
        accountBalance: 50000.0,
        maxDrawdown: 0.08,
        maxOpenTrades: 5,
        dailyLossLimit: 0.04,
        maxRiskPerTrade: 0.015,
      },
    });

    defaultRateLimiter.reset();
  });

  afterAll(async () => {
    await prisma.paperTrade.deleteMany({});
    await prisma.riskConfig.deleteMany({});
    await prisma.$disconnect();
  });

  it('should execute full order placement, position tracking, and automated reconciliation lifecycle', async () => {
    // 1. Place a risk-validated Long order on BTCUSDT ($500 risk <= $750 max risk)
    const placeRes = await request(app).post('/api/paper/trade').send({
      symbol: 'BTCUSDT',
      side: 'BUY',
      entryPrice: 65000.0,
      sl: 64000.0,
      tp: 68000.0,
      size: 0.5,
    });

    expect(placeRes.status).toBe(201);
    expect(placeRes.body).toHaveProperty('trade');
    const tradeId = placeRes.body.trade.id;
    expect(placeRes.body.trade.status).toBe('OPEN');
    expect(placeRes.body.trade.symbol).toBe('BTCUSDT');

    // 2. Query open positions list
    const openTradesRes = await request(app).get('/api/paper/positions');
    expect(openTradesRes.status).toBe(200);
    expect(openTradesRes.body.count).toBe(1);
    expect(openTradesRes.body.positions.some((p: any) => p.id === tradeId)).toBe(true);

    // 3. Trigger market tick reconciliation at target price ($68,500 hits take-profit)
    const reconcileRes = await request(app)
      .post('/api/paper/reconcile')
      .send({ prices: { BTCUSDT: 68500.0 } });

    expect(reconcileRes.status).toBe(200);
    expect(reconcileRes.body.result.closedCount).toBe(1);
    expect(reconcileRes.body.result.closedTrades[0].reason).toBe('TAKE_PROFIT');
    expect(reconcileRes.body.result.closedTrades[0].pnl).toBe((68500.0 - 65000.0) * 0.5);

    // 4. Verify no open trades remain
    const postReconcileRes = await request(app).get('/api/paper/positions');
    expect(postReconcileRes.body.count).toBe(0);
  });
});
