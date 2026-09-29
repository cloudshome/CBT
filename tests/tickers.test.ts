import request from 'supertest';
import { app } from '../src/server';

describe('GET /api/tickers', () => {
  it('should return live market tickers for BTCUSDT, ETHUSDT, PAXGUSDT, and XAUUSDT', async () => {
    const res = await request(app).get('/api/tickers?symbols=BTCUSDT,ETHUSDT,PAXGUSDT,XAUUSDT');
    expect(res.status).toBe(200);
    expect(res.body).toHaveProperty('tickers');
    expect(Array.isArray(res.body.tickers)).toBe(true);

    const btc = res.body.tickers.find((t: { symbol: string }) => t.symbol === 'BTCUSDT');
    const eth = res.body.tickers.find((t: { symbol: string }) => t.symbol === 'ETHUSDT');
    const paxg = res.body.tickers.find((t: { symbol: string }) => t.symbol === 'PAXGUSDT');

    expect(btc).toBeDefined();
    expect(btc.price).toBeGreaterThan(0);
    expect(typeof btc.change24h).toBe('number');

    expect(eth).toBeDefined();
    expect(eth.price).toBeGreaterThan(0);

    expect(paxg).toBeDefined();
    expect(paxg.price).toBeGreaterThan(0);
    expect(paxg.isGold).toBe(true);
  });
});
