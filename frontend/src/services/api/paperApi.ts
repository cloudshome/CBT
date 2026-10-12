/**
 * frontend/src/services/api/paperApi.ts
 * ====================================
 * Paper Trading & Position Execution Client API
 */

import { authFetch, BASE_URL } from './client';
import { handleResponse } from './utils';
import {
  PaperTrade,
  PaperPositionsResponse,
  PaperDeskOverviewResponse,
  RiskConfig,
} from '../../types';

export const paperApi = {
  /**
   * POST /api/paper/trade - Execute simulated paper trade
   */
  async placePaperTrade(trade: {
    symbol: string;
    side: 'BUY' | 'SELL';
    entryPrice: number;
    sl: number;
    tp: number;
    size?: number;
  }): Promise<{ message: string; trade: PaperTrade }> {
    const res = await authFetch(`${BASE_URL}/api/paper/trade`, {
      method: 'POST',
      body: JSON.stringify(trade),
    });
    return handleResponse<{ message: string; trade: PaperTrade }>(res);
  },

  /**
   * GET /api/paper/positions - Retrieve all active paper trading positions
   */
  async getPaperPositions(): Promise<PaperPositionsResponse> {
    const res = await authFetch(`${BASE_URL}/api/paper/positions`);
    const data = await handleResponse<any>(res);
    const positions = Array.isArray(data?.positions) ? data.positions : Array.isArray(data) ? data : [];
    return {
      positions,
      count: typeof data?.count === 'number' ? data.count : positions.length,
    };
  },

  /**
   * GET /api/paper/desk-overview - Desk overview metrics
   */
  async getPaperDeskOverview(): Promise<PaperDeskOverviewResponse> {
    const res = await authFetch(`${BASE_URL}/api/paper/desk-overview`);
    return handleResponse<PaperDeskOverviewResponse>(res);
  },

  /**
   * POST /api/paper/close - Close an open paper trade position
   */
  async closePaperPosition(
    tradeId: string,
    exitPrice?: number
  ): Promise<{ message: string; trade: PaperTrade }> {
    const res = await authFetch(`${BASE_URL}/api/paper/close`, {
      method: 'POST',
      body: JSON.stringify({ tradeId, exitPrice }),
    });
    return handleResponse<{ message: string; trade: PaperTrade }>(res);
  },

  /**
   * GET /api/paper/config - Retrieve institutional risk configuration
   */
  async getRiskConfig(): Promise<RiskConfig> {
    const res = await authFetch(`${BASE_URL}/api/paper/config`);
    return handleResponse<RiskConfig>(res);
  },

  /**
   * PUT /api/paper/config - Update institutional risk configuration
   */
  async updateRiskConfig(config: Partial<RiskConfig>): Promise<RiskConfig> {
    const res = await authFetch(`${BASE_URL}/api/paper/config`, {
      method: 'PUT',
      body: JSON.stringify(config),
    });
    return handleResponse<RiskConfig>(res);
  },
};
