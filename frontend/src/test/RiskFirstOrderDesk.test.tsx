import { describe, it, expect, vi } from 'vitest';
import React from 'react';
import { render, screen } from '@testing-library/react';
import { RiskFirstOrderDesk } from '../components/RiskFirstOrderDesk';

// Mock dependencies
vi.mock('../services/api', () => ({
  api: {
    getRiskConfig: vi.fn().mockResolvedValue({
      accountBalance: 100000,
      maxDrawdown: 0.1,
      maxOpenTrades: 3,
      dailyLossLimit: 0.05,
      maxRiskPerTrade: 0.02,
    }),
    requestSORQuote: vi.fn().mockResolvedValue({
      targetSymbol: 'BTCUSDT',
      requiredAmount: 0.1,
      totalNetExecuted: 0.1,
      blendedAveragePrice: 65000,
      estimatedSlippageBps: 2.5,
      estimatedFeeUsd: 1.5,
      childOrders: [],
    }),
    getKMSStatus: vi.fn().mockResolvedValue({
      enclave_initialized: true,
      hardware_backed: false,
    }),
    getVaultStatus: vi.fn().mockResolvedValue({
      vault_locked: false,
      kill_switch_active: false,
    }),
    getWSReconciliationTelemetry: vi.fn().mockResolvedValue({
      telemetry: {},
    }),
    getWSReconciliationRecent: vi.fn().mockResolvedValue({
      recent_fills: [],
    }),
    getSORBenchmarks: vi.fn().mockResolvedValue({
      benchmark: null,
    }),
    getKronosAdvisory: vi.fn().mockResolvedValue(null),
  },
  getHardwareKeyStatus: vi.fn().mockResolvedValue({
    connected: false,
    keyType: 'NONE',
  }),
}));

describe('RiskFirstOrderDesk Component', () => {
  it('renders order desk with default inputs and symbol', () => {
    const handlePlaceOrder = vi.fn();
    render(
      <RiskFirstOrderDesk
        symbol="BTCUSDT"
        lastPrice={65000}
        selectedSetup={null}
        onPlaceOrder={handlePlaceOrder}
      />
    );

    // Verify desk heading / action elements render
    expect(screen.getByText(/Risk-First Order Desk/i)).toBeInTheDocument();
    expect(screen.getAllByText(/LONG/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/SHORT/i).length).toBeGreaterThan(0);
  });

  it('renders execution algorithms and risk controls correctly', () => {
    const handlePlaceOrder = vi.fn();
    render(
      <RiskFirstOrderDesk
        symbol="ETHUSDT"
        lastPrice={3500}
        selectedSetup={null}
        onPlaceOrder={handlePlaceOrder}
      />
    );

    // Verify algorithms exist
    expect(screen.getByText(/TWAP/i)).toBeInTheDocument();
    expect(screen.getByText(/VWAP/i)).toBeInTheDocument();
  });
});
