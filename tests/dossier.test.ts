import request from 'supertest';
import { app } from '../src/server';

describe('GET /api/institutional/dossier', () => {
  it('should return complete 8-pillar dossier for BTCUSDT', async () => {
    const res = await request(app).get('/api/institutional/dossier?symbol=BTCUSDT');
    expect(res.status).toBe(200);
    expect(res.body).toHaveProperty('composite_health_score');
    expect(res.body).toHaveProperty('macro_bias');
    expect(res.body).toHaveProperty('pillar_1_institutional_flows');
    expect(res.body).toHaveProperty('pillar_2_derivatives_options');
    expect(res.body).toHaveProperty('pillar_3_valuation_cost_basis');
    expect(res.body).toHaveProperty('pillar_4_stablecoin_velocity');
    expect(res.body).toHaveProperty('pillar_5_seasonality_cyclical_dna');
    expect(res.body).toHaveProperty('pillar_6_macro_liquidity_beta');
    expect(res.body).toHaveProperty('pillar_7_volatility_profile');
    expect(res.body).toHaveProperty('pillar_8_physical_supply_shock');
    expect(res.body).toHaveProperty('pillar_z_scores');
    expect(Array.isArray(res.body.pillar_z_scores)).toBe(true);
    expect(res.body.pillar_z_scores.length).toBe(8);
    expect(res.body).toHaveProperty('actionable_quant_verdict');
  });

  it('should return complete 8-pillar dossier for Gold (PAXGUSDT)', async () => {
    const res = await request(app).get('/api/institutional/dossier?symbol=PAXGUSDT');
    expect(res.status).toBe(200);
    expect(res.body.symbol).toBe('PAXGUSDT');
    expect(res.body.pillar_1_institutional_flows.sovereign_central_bank_net_tons_quarterly).toBeGreaterThan(0);
    expect(res.body.pillar_8_physical_supply_shock.comex_registered_vault_delta_pct).toBeLessThan(0);
  });
});
