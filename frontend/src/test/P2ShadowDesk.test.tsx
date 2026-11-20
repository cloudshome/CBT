import { describe, it, expect, vi, beforeEach } from 'vitest';
import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { P2ShadowDesk } from '../components/P2ShadowDesk';

const mockTodayData = {
  timestamp_utc: '2026-11-20T12:00:00Z',
  data_source: 'LIVE_BINANCE',
  data_age_hours: 1.2,
  stale_data_warning: false,
  regime_label: 'MIXED',
  action_verdict: 'ACT',
  capital_mode: 'TIER_0_PAPER',
  real_capital_enabled: false,
  gross_exposure: 0.5,
  account_equity: 10000.0,
  days_to_rebalance: 3.5,
  s1_weights: { BTCUSDT: 0.25, ETHUSDT: 0.25, SOLUSDT: 0.0, PAXGUSDT: 0.0, CASH: 0.5 },
  s2_weights: { BTCUSDT: 0.25, ETHUSDT: 0.25, SOLUSDT: 0.0, PAXGUSDT: 0.0, CASH: 0.5 },
  p2_rp_weights: { BTCUSDT: 0.25, ETHUSDT: 0.25, SOLUSDT: 0.0, PAXGUSDT: 0.0, CASH: 0.5 },
  dollar_allocations: { BTCUSDT: 2500.0, ETHUSDT: 2500.0, SOLUSDT: 0.0, PAXGUSDT: 0.0, CASH: 5000.0 },
  assets: {
    BTCUSDT: {
      symbol: 'BTCUSDT',
      price: 92150.0,
      ema_200: 88500.0,
      ema_status: 'ABOVE',
      donchian_h48: 93000.0,
      donchian_l24: 87000.0,
      atr_14: 1200.0,
      stop_loss: 87000.0,
      momentum_30d_pct: 12.5,
      vol_20d_ann_pct: 45.2,
    },
    ETHUSDT: {
      symbol: 'ETHUSDT',
      price: 3350.0,
      ema_200: 3100.0,
      ema_status: 'ABOVE',
      donchian_h48: 3400.0,
      donchian_l24: 3000.0,
      atr_14: 65.0,
      stop_loss: 3000.0,
      momentum_30d_pct: 8.2,
      vol_20d_ann_pct: 55.4,
    },
    SOLUSDT: {
      symbol: 'SOLUSDT',
      price: 185.0,
      ema_200: 195.0,
      ema_status: 'BELOW',
      donchian_h48: 210.0,
      donchian_l24: 175.0,
      atr_14: 7.5,
      stop_loss: 175.0,
      momentum_30d_pct: -4.1,
      vol_20d_ann_pct: 72.1,
    },
    PAXGUSDT: {
      symbol: 'PAXGUSDT',
      price: 2680.0,
      ema_200: 2650.0,
      ema_status: 'ABOVE',
      donchian_h48: 2700.0,
      donchian_l24: 2640.0,
      atr_14: 18.0,
      stop_loss: 2640.0,
      momentum_30d_pct: 1.8,
      vol_20d_ann_pct: 14.5,
    },
  },
};

const mockShadowScorecard = {
  capital_mode: 'TIER_0_PAPER',
  real_capital_enabled: false,
  days_tracked: 14.5,
  target_forward_days: 60,
  equity_usd: 10420.5,
  total_return_pct: 4.21,
  bnh_return_pct: -1.5,
  alpha_vs_bnh_pct: 5.71,
  max_drawdown_pct: 3.42,
  live_sharpe: 2.15,
  total_fills: 12,
  avg_slippage_bps: 1.8,
  avg_spread_bps: 2.4,
  total_fees_usd: 8.5,
  current_regime: 'MIXED',
  positions: {
    BTCUSDT: {
      units: 0.0271,
      avg_entry_price: 92000.0,
      last_price: 92150.0,
      market_value_usd: 2497.26,
      target_weight: 0.25,
    },
    ETHUSDT: {
      units: 0.746,
      avg_entry_price: 3340.0,
      last_price: 3350.0,
      market_value_usd: 2499.1,
      target_weight: 0.25,
    },
  },
};

const mockShadowHistory = {
  capital_mode: 'TIER_0_PAPER',
  real_capital_enabled: false,
  bars: [
    {
      bar_ts_utc: '2026-11-19T00:00:00Z',
      equity_usd: 10000.0,
      bnh_equity_usd: 10000.0,
      gross_exposure: 0.5,
      regime_label: 'MIXED',
    },
    {
      bar_ts_utc: '2026-11-19T04:00:00Z',
      equity_usd: 10080.0,
      bnh_equity_usd: 9980.0,
      gross_exposure: 0.5,
      regime_label: 'MIXED',
    },
    {
      bar_ts_utc: '2026-11-19T08:00:00Z',
      equity_usd: 10150.0,
      bnh_equity_usd: 9920.0,
      gross_exposure: 0.5,
      regime_label: 'MIXED',
    },
  ],
  fills: [
    {
      bar_ts_utc: '2026-11-19T00:00:00Z',
      symbol: 'BTCUSDT',
      side: 'BUY',
      units: 0.027,
      signal_close_price: 92000.0,
      live_exec_price: 92015.0,
      spread_bps: 1.5,
      slippage_bps: 1.6,
      fee_usd: 2.48,
      notional_usd: 2484.0,
      reason: 'S1_ENTRY_BREAKOUT',
    },
  ],
};

describe('P2ShadowDesk Component', () => {
  beforeEach(() => {
    vi.restoreAllMocks();

    global.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/api/desk/today')) {
        return Promise.resolve({
          ok: true,
          json: async () => mockTodayData,
        });
      }
      if (url.includes('/api/desk/shadow/history')) {
        return Promise.resolve({
          ok: true,
          json: async () => mockShadowHistory,
        });
      }
      if (url.includes('/api/desk/shadow/run')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            cycle: { status: 'COMPLETED', fills: 1 },
            scorecard: mockShadowScorecard,
            capital_mode: 'TIER_0_PAPER',
            real_capital_enabled: false,
          }),
        });
      }
      if (url.includes('/api/desk/shadow')) {
        return Promise.resolve({
          ok: true,
          json: async () => mockShadowScorecard,
        });
      }
      return Promise.reject(new Error(`Unhandled url: ${url}`));
    });
  });

  it('renders P2_RP Shadow Desk and constitutional safety pill', async () => {
    render(<P2ShadowDesk />);

    await waitFor(() => {
      expect(screen.getByText(/P2_RP RISK-PARITY SHADOW DESK/i)).toBeInTheDocument();
    });

    expect(
      screen.getByText(/TIER_0_PAPER · REAL CAPITAL DISABLED/i)
    ).toBeInTheDocument();
    expect(screen.getByText('MIXED')).toBeInTheDocument();
    expect(screen.getByText('ACT')).toBeInTheDocument();
  });

  it('renders KPI metrics and allocations correctly', async () => {
    render(<P2ShadowDesk />);

    await waitFor(() => {
      expect(screen.getByText(/\$10,420\.50/i)).toBeInTheDocument();
    });

    // Check Alpha (+5.71%)
    expect(screen.getByText(/\+5\.71%/i)).toBeInTheDocument();

    // Check 60-Day Forward Proof Tracker (14.5 / 60d)
    expect(screen.getByText(/14\.5 \/ 60d/i)).toBeInTheDocument();
    expect(screen.getByText(/-3\.42%/i)).toBeInTheDocument();

    // Check Slippage
    expect(screen.getByText(/1\.80 bps/i)).toBeInTheDocument();
    expect(screen.getByText(/12 Fills/i)).toBeInTheDocument();

    // Check Gross Exposure
    expect(screen.getByText(/50\.0% Gross/i)).toBeInTheDocument();

    // Check symbols in allocation table
    expect(screen.getAllByText('BTCUSDT').length).toBeGreaterThan(0);
    expect(screen.getAllByText('ETHUSDT').length).toBeGreaterThan(0);
    expect(screen.getAllByText('SOLUSDT').length).toBeGreaterThan(0);
    expect(screen.getAllByText('PAXGUSDT').length).toBeGreaterThan(0);
  });

  it('supports English to Bengali language toggle', async () => {
    render(<P2ShadowDesk />);

    await waitFor(() => {
      expect(screen.getByText(/P2_RP RISK-PARITY SHADOW DESK/i)).toBeInTheDocument();
    });

    // Click language toggle button
    const bnBtn = screen.getByRole('button', { name: /বাংলা/i });
    fireEvent.click(bnBtn);

    // Bengali text should now be visible
    expect(
      screen.getByText(/P2_RP রিস্ক-প্যারিটি শ্যাডো ডেস্ক/i)
    ).toBeInTheDocument();
    expect(screen.getByText(/TIER_0_PAPER · কোন আসল মূলধন নয়/i)).toBeInTheDocument();
    expect(screen.getByText(/শ্যাডো পোর্টফোলিও ইকুইটি/i)).toBeInTheDocument();
  });

  it('renders fail-closed banner when action_verdict is WAIT_STALE_DATA', async () => {
    global.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/api/desk/today')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            ...mockTodayData,
            action_verdict: 'WAIT_STALE_DATA',
            data_age_hours: 8.5,
            stale_data_warning: true,
          }),
        });
      }
      if (url.includes('/api/desk/shadow/history')) {
        return Promise.resolve({
          ok: true,
          json: async () => mockShadowHistory,
        });
      }
      if (url.includes('/api/desk/shadow')) {
        return Promise.resolve({
          ok: true,
          json: async () => mockShadowScorecard,
        });
      }
      return Promise.reject(new Error(`Unhandled url: ${url}`));
    });

    render(<P2ShadowDesk />);

    await waitFor(() => {
      expect(
        screen.getByText(/FAIL-CLOSED ACTIVE/i)
      ).toBeInTheDocument();
    });
  });

  it('allows triggering 4h shadow cycle manually', async () => {
    const notifyMock = vi.fn();
    render(<P2ShadowDesk onNotify={notifyMock} />);

    await waitFor(() => {
      expect(screen.getByText(/Run 4h Shadow Cycle/i)).toBeInTheDocument();
    });

    const runBtn = screen.getByRole('button', { name: /Run 4h Shadow Cycle/i });
    fireEvent.click(runBtn);

    await waitFor(() => {
      expect(notifyMock).toHaveBeenCalledWith(
        'success',
        'Shadow Cycle Executed',
        expect.stringMatching(/Shadow Cycle: COMPLETED \(1 fills executed under TIER_0_PAPER\)/i)
      );
    });
  });
});
