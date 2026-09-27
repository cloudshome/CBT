import request from 'supertest';
import { createApp } from '../src/server';
import { defaultRateLimiter } from '../src/middleware/rateLimit';

// Mock the market data service to return deterministic candles
jest.mock('../src/services/marketDataService', () => {
  const original = jest.requireActual('../src/services/marketDataService');
  return {
    ...original,
    fetchCandlesWithFallback: jest.fn(async () => {
      const now = Date.now();
      const candles = [];
      let p = 88000;
      for (let i = 0; i < 50; i++) {
        const o = p;
        const c = p + 25;
        candles.push([now - (50 - i) * 900000, o, o + 50, o - 30, c, 500]);
        p = c;
      }
      return { candles, source: 'binance' };
    }),
  };
});

describe('Institutional Master Terminal Routes (/api/terminal)', () => {
  const app = createApp();

  beforeEach(() => {
    defaultRateLimiter.reset();
  });

  it('GET /api/terminal/telemetry returns complete 8-level cockpit hierarchy', async () => {
    const res = await request(app).get('/api/terminal/telemetry?symbol=BTCUSDT&timeframe=15m');
    expect(res.status).toBe(200);

    // Level 0: System
    expect(res.body).toHaveProperty('system');
    expect(res.body.system).toHaveProperty('service', 'CTB-INSTITUTIONAL-COCKPIT');
    expect(res.body.system.riskPerimeter).toHaveProperty('status', 'ARMED');

    // Level 1: Market & Structure
    expect(res.body).toHaveProperty('market');
    expect(res.body.market.mtfMatrix).toHaveLength(9);
    expect(res.body.market.regime).toHaveProperty('classification');
    expect(res.body.market.marketDecision).toHaveProperty('primaryAction');
    expect(res.body.market.volumeProfile).toHaveProperty('vpoc');
    expect(res.body.market.volumeProfile).toHaveProperty('vah');
    expect(res.body.market.volumeProfile).toHaveProperty('val');
    expect(res.body.market.liquidationMap.shortClusters.length).toBeGreaterThan(0);
    expect(res.body.market.liquidationMap.longClusters.length).toBeGreaterThan(0);

    // Level 2: Order Flow & CVD
    expect(res.body).toHaveProperty('orderFlow');
    expect(res.body.orderFlow).toHaveProperty('currentCvd');
    expect(res.body.orderFlow.divergenceAlert).toHaveProperty('title');
    expect(res.body.orderFlow.derivativesVitals).toHaveProperty('openInterestUsd');
    expect(res.body.orderFlow.derivativesVitals.liquidityWalls.length).toBeGreaterThan(0);

    // Level 3: Confluence & 10-Factor Scorecard
    expect(res.body).toHaveProperty('confluence');
    expect(res.body.confluence).toHaveProperty('qualityScore');
    expect(res.body.confluence).toHaveProperty('qualityBadge');
    expect(res.body.confluence.factorWeights).toHaveLength(10);

    // Verify weights sum strictly to 100%
    const totalWeight = res.body.confluence.factorWeights.reduce(
      (sum: number, f: { weightPct: number }) => sum + f.weightPct,
      0
    );
    expect(totalWeight).toBe(100);

    // Level 4: 5-Style Signal Plans
    expect(res.body.styleSignals).toHaveLength(5);
    const styles = res.body.styleSignals.map((s: { style: string }) => s.style);
    expect(styles).toEqual(expect.arrayContaining(['SCALP', 'DAY', 'SWING', 'MOMENTUM', 'POSITION']));

    // Level 5: Execution Blotter & Risk
    expect(res.body).toHaveProperty('executionAndRisk');
    expect(res.body.executionAndRisk).toHaveProperty('equityUsd');
    expect(res.body.executionAndRisk).toHaveProperty('winRatePct');
    expect(res.body.executionAndRisk.calibrationLab.length).toBeGreaterThan(0);

    // Level 6: Macro, Dominance, Prediction Markets & On-Chain
    expect(res.body).toHaveProperty('macroAndContext');
    expect(res.body.macroAndContext.fearAndGreed).toHaveProperty('score');
    expect(res.body.macroAndContext.marketDominance).toHaveProperty('btcD');
    expect(res.body.macroAndContext.crossAssetCorrelation.assets).toEqual(
      expect.arrayContaining(['BTC', 'SPX', 'NDX', 'DXY', 'GOLD'])
    );
    expect(res.body.macroAndContext.polymarketIntelligence.length).toBeGreaterThan(0);

    // Level 7: Learning & AI Coach
    expect(res.body).toHaveProperty('learningAndCoach');
    expect(res.body.learningAndCoach).toHaveProperty('currentThesis');
    expect(res.body.learningAndCoach.whyNotTradeEngine).toHaveProperty('isTradingAllowed');
    expect(res.body.learningAndCoach.preTradeGateChecklist).toHaveLength(10);

    // Provenance
    expect(res.body).toHaveProperty('provenance');
    expect(res.body.provenance.nodes.length).toBeGreaterThan(0);
  });

  it('POST /api/terminal/approval-action updates signal lifecycle correctly', async () => {
    // 1. Approve
    const approveRes = await request(app)
      .post('/api/terminal/approval-action')
      .send({ signalId: 'SIG-BTC-SWING-01', action: 'APPROVE', notes: 'Approved via blotter test' });
    expect(approveRes.status).toBe(200);
    expect(approveRes.body).toHaveProperty('success', true);
    expect(approveRes.body).toHaveProperty('newState', 'APPROVED');

    // 2. Execute
    const execRes = await request(app)
      .post('/api/terminal/approval-action')
      .send({ signalId: 'SIG-BTC-SWING-01', action: 'EXECUTE' });
    expect(execRes.status).toBe(200);
    expect(execRes.body).toHaveProperty('newState', 'EXECUTED');

    // 3. Close
    const closeRes = await request(app)
      .post('/api/terminal/approval-action')
      .send({ signalId: 'SIG-BTC-SWING-01', action: 'CLOSE' });
    expect(closeRes.status).toBe(200);
    expect(closeRes.body).toHaveProperty('newState', 'CLOSED');

    // 4. Bad request checks
    const badRes = await request(app)
      .post('/api/terminal/approval-action')
      .send({ signalId: 'INVALID-ID', action: 'APPROVE' });
    expect(badRes.status).toBe(404);
  });

  it('GET /api/terminal/glossary returns glossary items and supports search', async () => {
    const resAll = await request(app).get('/api/terminal/glossary');
    expect(resAll.status).toBe(200);
    expect(resAll.body.totalCount).toBeGreaterThanOrEqual(10);

    const resFiltered = await request(app).get('/api/terminal/glossary?q=BOS');
    expect(resFiltered.status).toBe(200);
    expect(resFiltered.body.items.length).toBeGreaterThanOrEqual(1);
    expect(resFiltered.body.items[0].term).toContain('BOS');
  });

  it('GET /api/terminal/provenance returns structured evidence audit chain', async () => {
    const res = await request(app).get('/api/terminal/provenance?thesisId=TEST-1');
    expect(res.status).toBe(200);
    expect(res.body).toHaveProperty('thesisId', 'TEST-1');
    expect(res.body).toHaveProperty('verdict');
    expect(res.body.nodes.length).toBeGreaterThanOrEqual(5);
  });

  it('GET /api/terminal/replay returns historical snapshot data', async () => {
    const res = await request(app).get('/api/terminal/replay?offset=T-30m');
    expect(res.status).toBe(200);
    expect(res.body).toHaveProperty('offset', 'T-30m');
    expect(res.body).toHaveProperty('replayPrice');
    expect(res.body).toHaveProperty('replayScore');
    expect(res.body).toHaveProperty('whatChanged');
  });
});
