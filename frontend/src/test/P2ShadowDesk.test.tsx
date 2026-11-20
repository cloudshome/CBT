import { describe, it, expect, vi, beforeEach } from 'vitest';
import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { P2ShadowDesk } from '../components/P2ShadowDesk';
import { api, ApiError } from '../services/api';

vi.mock('../services/api', () => ({
  api: {
    getTodayDeskSnapshot: vi.fn(),
    getShadowScorecard: vi.fn(),
    getShadowHistory: vi.fn(),
    runShadowCycle: vi.fn(),
  },
  ApiError: class ApiError extends Error {
    statusCode: number;
    details?: unknown;
    constructor(msg: string, status: number, details?: unknown) {
      super(msg);
      this.name = 'ApiError';
      this.statusCode = status;
      this.details = details;
    }
  },
}));

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
  decision_headline_en: 'PROTECTING CAPITAL IN 100% CASH — No asset meets S1 breakout or S2 positive-momentum rules.',
  decision_headline_bn: '১০০% ক্যাশে মূলধন সুরক্ষা — কোন অ্যাসেটেই S1 ব্রেকআউট বা S2 পজিটিভ মোমেন্টাম শর্ত পূরণ হয়নি।',
  next_trade_checklist_en: [
    'PAXGUSDT: Needs 5.2% rally to reclaim EMA-200 ($4,113.18) and 4h close > $4,082.99 (+4.7% away) for S1 breakout.',
    'BTCUSDT: Needs 4.4% rally to reclaim EMA-200 ($81,097.35) and 4h close > $81,953.70 (+5.7% away) for S1 breakout.',
    'ETHUSDT: Needs 7.1% rally to reclaim EMA-200 ($2,426.22) and 4h close > $2,404.00 (+6.6% away) for S1 breakout.',
  ],
  next_trade_checklist_bn: [
    'PAXGUSDT: EMA-200 ($4,113.18) রিক্লেইম করতে 5.2% র‍্যালি এবং S1 ডনচিয়ান-৪৮ ব্রেকআউটের জন্য $4,082.99 (+4.7% দূরে) এর উপরে ৪ ঘণ্টার ক্লোজ প্রয়োজন।',
    'BTCUSDT: EMA-200 ($81,097.35) রিক্লেইম করতে 4.4% র‍্যালি এবং S1 ডনচিয়ান-৪৮ ব্রেকআউটের জন্য $81,953.70 (+5.7% দূরে) এর উপরে ৪ ঘণ্টার ক্লোজ প্রয়োজন।',
    'ETHUSDT: EMA-200 ($2,426.22) রিক্লেইম করতে 7.1% র‍্যালি এবং S1 ডনচিয়ান-৪৮ ব্রেকআউটের জন্য $2,404.00 (+6.6% দূরে) এর উপরে ৪ ঘণ্টার ক্লোজ প্রয়োজন।',
  ],
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
      ema200_price: 88500.0,
      donchian48_high: 93000.0,
      distance_to_ema200_pct: 4.12,
      distance_to_breakout_pct: 0.92,
      s1_status: 'WAITING_BREAKOUT',
      s2_status: 'SELECTED_TOP2',
      waiting_reason_en: 'Waiting: price is above EMA-200 (+4.1%), needs 4h close > $93,000.00 (+0.9% away) for S1 breakout.',
      waiting_reason_bn: 'অপেক্ষমাণ: মূল্য EMA-200 এর উপরে (+4.1%), S1 ব্রেকআউটের জন্য $93,000.00 (+0.9% দূরে) এর উপরে ৪ ঘণ্টার ক্লোজ প্রয়োজন।',
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
      ema200_price: 3100.0,
      donchian48_high: 3400.0,
      distance_to_ema200_pct: 8.06,
      distance_to_breakout_pct: 1.49,
      s1_status: 'WAITING_BREAKOUT',
      s2_status: 'SELECTED_TOP2',
      waiting_reason_en: 'Waiting: price is above EMA-200 (+8.1%), needs 4h close > $3,400.00 (+1.5% away) for S1 breakout.',
      waiting_reason_bn: 'অপেক্ষমাণ: মূল্য EMA-200 এর উপরে (+8.1%), S1 ব্রেকআউটের জন্য $3,400.00 (+1.5% দূরে) এর উপরে ৪ ঘণ্টার ক্লোজ প্রয়োজন।',
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
      ema200_price: 195.0,
      donchian48_high: 210.0,
      distance_to_ema200_pct: -5.13,
      distance_to_breakout_pct: 13.51,
      s1_status: 'WAITING_EMA200',
      s2_status: 'NEGATIVE_MOMENTUM',
      waiting_reason_en: 'Waiting: price is 5.1% below EMA-200 ($195.00) and needs 4h close > $210.00 (+13.5%) to trigger S1; 30d momentum (-4.1%) must turn > 0% for S2.',
      waiting_reason_bn: 'অপেক্ষমাণ: মূল্য EMA-200 ($195.00) এর থেকে 5.1% নিচে এবং S1 সক্রিয় হতে $210.00 (+13.5%) এর উপরে ৪ ঘণ্টার ক্লোজ প্রয়োজন; ৩০ দিনের মোমেন্টাম (-4.1%) S2 এর জন্য > ০% হতে হবে।',
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
      ema200_price: 2650.0,
      donchian48_high: 2700.0,
      distance_to_ema200_pct: 1.13,
      distance_to_breakout_pct: 0.75,
      s1_status: 'WAITING_BREAKOUT',
      s2_status: 'OUTRANKED',
      waiting_reason_en: 'Waiting: price is above EMA-200 (+1.1%), needs 4h close > $2,700.00 (+0.7% away) for S1 breakout.',
      waiting_reason_bn: 'অপেক্ষমাণ: মূল্য EMA-200 এর উপরে (+1.1%), S1 ব্রেকআউটের জন্য $2,700.00 (+0.7% দূরে) এর উপরে ৪ ঘণ্টার ক্লোজ প্রয়োজন।',
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
  positions: {},
};

const mockShadowHistory = {
  capital_mode: 'TIER_0_PAPER',
  real_capital_enabled: false,
  bars: [
    {
      bar_ts_utc: 1700000000000,
      equity_usd: 10000.0,
      bnh_equity_usd: 10000.0,
      gross_exposure: 0.5,
      regime_label: 'MIXED',
    },
    {
      bar_ts_utc: 1700014400000,
      equity_usd: 10080.0,
      bnh_equity_usd: 9980.0,
      gross_exposure: 0.5,
      regime_label: 'MIXED',
    },
    {
      bar_ts_utc: 1700028800000,
      equity_usd: 10150.0,
      bnh_equity_usd: 9920.0,
      gross_exposure: 0.5,
      regime_label: 'MIXED',
    },
  ],
  fills: [
    {
      bar_ts_utc: 1700000000000,
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

    vi.mocked(api.getTodayDeskSnapshot).mockResolvedValue(mockTodayData as any);
    vi.mocked(api.getShadowScorecard).mockResolvedValue(mockShadowScorecard as any);
    vi.mocked(api.getShadowHistory).mockResolvedValue(mockShadowHistory as any);
    vi.mocked(api.runShadowCycle).mockResolvedValue({
      cycle: { status: 'COMPLETED', fills: 1 },
      scorecard: mockShadowScorecard as any,
      capital_mode: 'TIER_0_PAPER',
      real_capital_enabled: false,
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

  it('renders Why Waiting & Exact Next Trigger Conditions panel in EN', async () => {
    render(<P2ShadowDesk />);

    await waitFor(() => {
      expect(screen.getByText(/Why Trade \/ Why Waiting & Exact Next Trigger Conditions/i)).toBeInTheDocument();
    });

    // Check Decision Headline
    expect(screen.getByText(/PROTECTING CAPITAL IN 100% CASH/i)).toBeInTheDocument();
    expect(screen.getByText(/100% CASH SHIELD/i)).toBeInTheDocument();

    // Check Top 3 Watchlist checklist items
    expect(screen.getByText(/PAXGUSDT: Needs 5\.2% rally to reclaim EMA-200/i)).toBeInTheDocument();
    expect(screen.getByText(/BTCUSDT: Needs 4\.4% rally to reclaim EMA-200/i)).toBeInTheDocument();
    expect(screen.getByText(/ETHUSDT: Needs 7\.1% rally to reclaim EMA-200/i)).toBeInTheDocument();

    // Check 1-line reason for SOLUSDT
    expect(screen.getByText(/price is 5\.1% below EMA-200/i)).toBeInTheDocument();
  });

  it('supports English to Bengali language toggle including trigger explainer', async () => {
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
    expect(screen.getByText(/ট্রেড সিদ্ধান্ত ও পরবর্তী সুনির্দিষ্ট ট্রিগার শর্তাবলি/i)).toBeInTheDocument();
    expect(screen.getByText(/১০০% ক্যাশে মূলধন সুরক্ষা/i)).toBeInTheDocument();
    expect(screen.getByText(/PAXGUSDT: EMA-200 \(\$4,113\.18\) রিক্লেইম করতে 5\.2% র‍্যালি/i)).toBeInTheDocument();
  });

  it('renders Active Shadow Trades view when active positions exist', async () => {
    vi.mocked(api.getShadowScorecard).mockResolvedValue({
      ...mockShadowScorecard,
      positions: {
        BTCUSDT: {
          units: 0.05,
          avg_entry_price: 90000.0,
          last_price: 92150.0,
          market_value_usd: 4607.5,
          target_weight: 0.25,
        },
      },
    } as any);

    render(<P2ShadowDesk />);

    await waitFor(() => {
      expect(screen.getByText(/ACTIVE SHADOW POSITIONS/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/\+\$107\.50/i)).toBeInTheDocument();
    expect(screen.getByText('ACTIVE')).toBeInTheDocument();
  });

  it('renders fail-closed banner when action_verdict is WAIT_STALE_DATA or API error occurs', async () => {
    vi.mocked(api.getTodayDeskSnapshot).mockResolvedValue({
      ...mockTodayData,
      action_verdict: 'WAIT_STALE_DATA',
      data_age_hours: 8.5,
      stale_data_warning: true,
    } as any);

    render(<P2ShadowDesk />);

    await waitFor(() => {
      expect(
        screen.getByText(/FAIL-CLOSED ACTIVE/i)
      ).toBeInTheDocument();
    });
  });

  it('displays exact HTTP error details when snapshot fetch fails', async () => {
    vi.mocked(api.getTodayDeskSnapshot).mockRejectedValue(
      new ApiError('Backend candle store offline', 503, { detail: 'Service unavailable' })
    );

    render(<P2ShadowDesk />);

    await waitFor(() => {
      expect(
        screen.getByText(/Failed to load Today desk snapshot \(HTTP 503: Backend candle store offline\)/i)
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
