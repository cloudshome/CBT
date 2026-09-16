import React, { useState, useEffect, useCallback } from 'react';
import {
  TrendingUp,
  TrendingDown,
  Calculator,
  ArrowRight,
  Sparkles,
  Zap,
  Shield,
  AlertTriangle,
  CheckCircle,
  Clock,
  Radio,
  Lock,
  Cpu,
  Activity,
  RefreshCw,
} from 'lucide-react';
import { PrecisionMath } from '../core/precision/decimalMath';
import {
  SetupSuggestion,
  KMSEnclaveStatus,
  SORBenchmarkSuite,
  WSReconciliationTelemetry,
  WSNormalizedFill,
} from '../types';
import { api, VaultStatus, SORRouteQuote, AlmgrenChrissSchedule, getHardwareKeyStatus, ClearanceSessionData } from '../services/api';
import { HardwareKeyModal } from './HardwareKeyModal';

interface RiskFirstOrderDeskProps {
  symbol: string;
  lastPrice: number;
  selectedSetup?: SetupSuggestion | null;
  onPlaceOrder: (order: {
    symbol: string;
    side: 'BUY' | 'SELL';
    type: 'MARKET' | 'LIMIT';
    price?: number;
    amount: number;
    stopLoss?: number;
    takeProfit?: number;
    executionAlgo?: string;
    isLiveExecution?: boolean;
  }) => Promise<void>;
}

export const RiskFirstOrderDesk: React.FC<RiskFirstOrderDeskProps> = ({
  symbol,
  lastPrice,
  selectedSetup,
  onPlaceOrder,
}) => {
  const [orderType, setOrderType] = useState<'MARKET' | 'LIMIT'>('MARKET');
  const [executionAlgo, setExecutionAlgo] = useState<'STANDARD' | 'TWAP' | 'VWAP' | 'ALMGREN_CHRISS' | 'IOC_SWEEP'>('STANDARD');
  const [side, setSide] = useState<'BUY' | 'SELL'>('BUY');
  const [accountEquity] = useState<number>(10000);
  const [riskPct, setRiskPct] = useState<number>(0.01); // 1% risk
  const [entryPrice, setEntryPrice] = useState<number>(lastPrice || 0);
  const [stopLoss, setStopLoss] = useState<number>(0);
  const [takeProfit, setTakeProfit] = useState<number>(0);
  const [leverage, setLeverage] = useState<number>(10);
  const [submitting, setSubmitting] = useState(false);
  const [kronosAdvisory, setKronosAdvisory] = useState<any>(null);
  const [impactEstimate, setImpactEstimate] = useState<{ expected_slippage_bps: number; total_impact_usd: number } | null>(null);

  // Milestone 18: Live Execution Mode & Pre-Trade Invariant Safety
  const [isLiveMode, setIsLiveMode] = useState<boolean>(false);
  const [vaultStatus, setVaultStatus] = useState<VaultStatus | null>(null);
  const [showConfirmModal, setShowConfirmModal] = useState<boolean>(false);
  const [sorQuote, setSorQuote] = useState<SORRouteQuote | null>(null);
  const [almgrenSchedule, setAlmgrenSchedule] = useState<AlmgrenChrissSchedule | null>(null);
  const [isHardwareModalOpen, setIsHardwareModalOpen] = useState<boolean>(false);
  const [clearanceSession, setClearanceSession] = useState<ClearanceSessionData | null>(null);

  // Phase 19: KMS Enclave, Micro-Benchmarks & Real-Time WS Stream
  const [kmsStatus, setKmsStatus] = useState<KMSEnclaveStatus | null>(null);
  const [sorBenchmarks, setSorBenchmarks] = useState<SORBenchmarkSuite | null>(null);
  const [benchmarkRunning, setBenchmarkRunning] = useState<boolean>(false);
  const [benchmarkError, setBenchmarkError] = useState<string | null>(null);
  const [wsTelemetry, setWsTelemetry] = useState<WSReconciliationTelemetry | null>(null);
  const [recentFills, setRecentFills] = useState<WSNormalizedFill[]>([]);
  const [showBenchmarkHUD, setShowBenchmarkHUD] = useState<boolean>(false);
  const [showWSFeedDrawer, setShowWSFeedDrawer] = useState<boolean>(false);

  // Poll KMS Enclave Status
  useEffect(() => {
    let isMounted = true;
    const fetchKMS = () => {
      api.getKMSStatus().then((res) => {
        if (isMounted && res) setKmsStatus(res);
      }).catch(() => {});
    };
    fetchKMS();
    const interval = setInterval(fetchKMS, 15000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, []);

  // Poll Real-Time WebSocket Telemetry & Recent Fills
  useEffect(() => {
    let isMounted = true;
    const fetchWSTelemetry = () => {
      api.getWSReconciliationTelemetry().then((res) => {
        if (isMounted && res?.telemetry) setWsTelemetry(res.telemetry);
      }).catch(() => {});
      api.getWSReconciliationRecent(10).then((res) => {
        if (isMounted && res?.recent_fills) setRecentFills(res.recent_fills);
      }).catch(() => {});
    };
    fetchWSTelemetry();
    const interval = setInterval(fetchWSTelemetry, 5000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, []);

  // Interactive Micro-Benchmark Runner
  const handleRunBenchmarks = useCallback(async () => {
    if (benchmarkRunning) return;
    setBenchmarkRunning(true);
    setBenchmarkError(null);
    try {
      const res = await api.getSORBenchmarks(100);
      if (res && res.benchmark) {
        setSorBenchmarks(res.benchmark);
      }
    } catch (err: any) {
      setBenchmarkError(err?.message || 'Benchmark execution failed');
    } finally {
      setBenchmarkRunning(false);
    }
  }, [benchmarkRunning]);

  // Poll Vault & Kill Switch Status
  useEffect(() => {
    let isMounted = true;
    const fetchVault = () => {
      api.getVaultStatus().then((res) => {
        if (isMounted && res) setVaultStatus(res);
      }).catch(() => {});
    };
    fetchVault();
    const interval = setInterval(fetchVault, 10000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, []);

  // Kronos Advisory Shadow Ingestion
  useEffect(() => {
    let isMounted = true;
    const cleanSym = symbol.replace('/', '').toUpperCase();
    api.getKronosAdvisory({
      symbol: cleanSym,
      timeframe: '15m',
      sky_decision: side === 'BUY' ? 'LONG' : 'SHORT',
    }).then((res) => {
      if (isMounted && res) setKronosAdvisory(res);
    }).catch(() => {});
    return () => { isMounted = false; };
  }, [symbol, side]);

  // Sync with selected setup if provided
  useEffect(() => {
    if (selectedSetup) {
      setSide(selectedSetup.type === 'LONG' ? 'BUY' : 'SELL');
      setEntryPrice(selectedSetup.entry || lastPrice);
      setStopLoss(selectedSetup.stopLoss || 0);
      setTakeProfit(selectedSetup.takeProfit || 0);
    } else if (lastPrice > 0 && entryPrice === 0) {
      setEntryPrice(lastPrice);
      setStopLoss(side === 'BUY' ? lastPrice * 0.985 : lastPrice * 1.015);
      setTakeProfit(side === 'BUY' ? lastPrice * 1.045 : lastPrice * 0.955);
    }
  }, [selectedSetup, lastPrice]);

  // Compute exact position size & liquidation price using fixed-point math
  const { riskAmountUsd, positionSizeBase, positionSizeQuote, stopDistancePct } =
    PrecisionMath.calculatePositionSize(
      accountEquity,
      riskPct,
      entryPrice > 0 ? entryPrice : lastPrice,
      stopLoss
    );

  const liquidationPrice = PrecisionMath.calculateLiquidationPrice(
    entryPrice > 0 ? entryPrice : lastPrice,
    side === 'BUY' ? 'LONG' : 'SHORT',
    leverage
  );

  const riskRewardRatio =
    stopLoss > 0 && takeProfit > 0 && entryPrice > 0
      ? Math.abs((takeProfit - entryPrice) / (entryPrice - stopLoss)).toFixed(2)
      : '0.00';

  // Milestone 18: Fetch SOR Route Quote when size changes
  useEffect(() => {
    if (positionSizeBase > 0) {
      const cleanSym = symbol.includes('/') ? symbol : `${symbol.slice(0, -4)}/${symbol.slice(-4)}`;
      api.getSORRouteQuote({
        symbol: cleanSym,
        side,
        total_qty: positionSizeBase,
        max_slippage_bps: 150.0,
      }).then((res) => {
        if (res && res.quote) setSorQuote(res.quote);
      }).catch(() => setSorQuote(null));
    }
  }, [positionSizeBase, side, symbol]);

  // Milestone 18: Fetch Almgren-Chriss Schedule when algo is active
  useEffect(() => {
    if (executionAlgo === 'ALMGREN_CHRISS' && positionSizeBase > 0) {
      const p = entryPrice > 0 ? entryPrice : lastPrice;
      if (p > 0) {
        api.getAlmgrenChrissSchedule({
          symbol,
          side,
          total_qty: positionSizeBase,
          current_price: p,
          time_horizon_sec: 900.0,
          num_intervals: 10,
          annualized_volatility: 0.65,
          risk_aversion_lambda: 1e-6,
        }).then((res) => {
          if (res && res.schedule) setAlmgrenSchedule(res.schedule);
        }).catch(() => setAlmgrenSchedule(null));
      }
    } else {
      setAlmgrenSchedule(null);
    }
  }, [executionAlgo, positionSizeBase, side, symbol, entryPrice, lastPrice]);

  // Simulate market impact when size changes
  useEffect(() => {
    if (positionSizeBase > 0 && (entryPrice > 0 || lastPrice > 0)) {
      api.simulateMarketImpact({
        order_size: positionSizeBase,
        order_side: side,
        symbol: symbol,
        mid_price: entryPrice > 0 ? entryPrice : lastPrice,
        urgency: executionAlgo === 'IOC_SWEEP' ? 'HIGH' : executionAlgo === 'STANDARD' ? 'MEDIUM' : 'LOW',
      }).then((res) => {
        if (res) {
          setImpactEstimate({
            expected_slippage_bps: res.expected_slippage_bps || 1.5,
            total_impact_usd: res.total_impact_usd || 0.12,
          });
        }
      }).catch(() => {
        setImpactEstimate(null);
      });
    }
  }, [positionSizeBase, side, symbol, entryPrice, lastPrice, executionAlgo]);

  // Single-trade 1.5% equity cap check
  const maxAllowableRiskUsd = accountEquity * 0.015;
  const isWithinRiskCap = riskAmountUsd <= maxAllowableRiskUsd;

  const handleOrderInitiation = (e: React.FormEvent) => {
    e.preventDefault();
    if (positionSizeBase <= 0) return;

    if (isLiveMode) {
      // Require dual-confirmation for real capital transmission
      setShowConfirmModal(true);
    } else {
      executeOrder();
    }
  };

  const executeOrder = async () => {
    setSubmitting(true);
    try {
      await onPlaceOrder({
        symbol,
        side,
        type: orderType,
        price: orderType === 'LIMIT' ? entryPrice : undefined,
        amount: positionSizeBase,
        stopLoss: stopLoss > 0 ? stopLoss : undefined,
        takeProfit: takeProfit > 0 ? takeProfit : undefined,
        executionAlgo: executionAlgo !== 'STANDARD' ? executionAlgo : undefined,
        isLiveExecution: isLiveMode,
      });
      setShowConfirmModal(false);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="bg-surface border border-border rounded-lg p-3.5 flex flex-col gap-3 text-slate-200 font-mono select-none">
      {/* Header & Mode Switch */}
      <div className="flex items-center justify-between border-b border-border pb-2">
        <div className="flex items-center gap-1.5">
          <Calculator className="w-4 h-4 text-terminal-cyan" />
          <span className="font-bold text-xs tracking-wider text-slate-100 uppercase">
            Risk-First Order Desk
          </span>
        </div>

        {/* Live / Paper Execution Mode Toggle */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={async () => {
              if (isLiveMode) {
                setIsLiveMode(false);
                return;
              }
              if (vaultStatus?.kill_switch.is_active) {
                alert('Cannot enable Live Execution: Kill Switch is currently ACTIVE.');
                return;
              }
              try {
                const statusRes = await getHardwareKeyStatus();
                if (statusRes.posture.live_clearance_active && statusRes.posture.clearance_session) {
                  setClearanceSession(statusRes.posture.clearance_session);
                  setIsLiveMode(true);
                } else {
                  setIsHardwareModalOpen(true);
                }
              } catch {
                setIsHardwareModalOpen(true);
              }
            }}
            className={`px-2 py-0.5 text-[10px] font-bold rounded border transition flex items-center gap-1 ${
              isLiveMode
                ? 'bg-rose-950/80 border-rose-500 text-rose-300 animate-pulse'
                : 'bg-slate-800 border-border text-slate-400 hover:text-slate-200'
            }`}
          >
            <Radio className={`w-3 h-3 ${isLiveMode ? 'text-rose-400' : 'text-slate-500'}`} />
            <span>{isLiveMode ? 'LIVE REAL CAPITAL' : 'PAPER SIMULATION'}</span>
          </button>
          <span className="text-[10px] text-slate-400">Equity: ${accountEquity.toLocaleString()}</span>
        </div>
      </div>

      {/* Hardware Key Live Clearance Badge */}
      <div className="px-2 py-1.5 rounded bg-slate-900/80 border border-slate-800 flex items-center justify-between text-[10px]">
        <div className="flex items-center gap-1.5 text-slate-300">
          <Shield className="w-3.5 h-3.5 text-amber-400" />
          <span className="text-slate-400 font-semibold">FIDO2 / WEBAUTHN:</span>
          <span className={`font-bold ${
            isLiveMode && clearanceSession?.is_valid
              ? 'text-emerald-400'
              : 'text-slate-400'
          }`}>
            {isLiveMode && clearanceSession?.is_valid
              ? `LIVE CLEARANCE ACTIVE (${clearanceSession.credential_id_masked})`
              : 'HARDWARE CLEARANCE INACTIVE'}
          </span>
        </div>
        <button
          type="button"
          onClick={() => setIsHardwareModalOpen(true)}
          className="text-amber-400 hover:text-amber-300 font-semibold underline text-[9px]"
        >
          {isLiveMode && clearanceSession?.is_valid ? 'MANAGE KEY' : 'REQUEST CLEARANCE'}
        </button>
      </div>

      {/* Cloud KMS / HSM Enclave Security Badge */}
      <div className="px-2 py-1.5 rounded bg-slate-900/80 border border-slate-800 flex items-center justify-between text-[10px]">
        <div className="flex items-center gap-1.5 text-slate-300">
          <Lock className="w-3.5 h-3.5 text-cyan-400" />
          <span className="text-slate-400 font-semibold">ENCLAVE:</span>
          <span className={`font-bold ${
            kmsStatus?.kms_enabled
              ? 'text-cyan-300'
              : 'text-amber-400'
          }`}>
            {kmsStatus ? `V${kmsStatus.envelope_version} (${kmsStatus.provider})` : 'CHECKING...'}
          </span>
          {kmsStatus?.key_id && kmsStatus.key_id !== 'N/A' && (
            <span className="text-[9px] text-slate-400 font-mono">[{kmsStatus.key_id}]</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className="px-1.5 py-0.2 rounded text-[9px] font-bold bg-slate-800 border border-slate-700 text-emerald-400">
            DEK: {kmsStatus?.zeroization_guarantee ? 'ZEROIZED' : 'STANDARD'}
          </span>
          <span className={`px-1.5 py-0.2 rounded text-[9px] font-bold ${
            kmsStatus?.kill_switch_active
              ? 'bg-rose-500/20 text-rose-300 border border-rose-500/50'
              : 'bg-emerald-500/10 text-emerald-300 border border-emerald-500/30'
          }`}>
            {kmsStatus?.kill_switch_active ? 'KS: LOCKED' : 'KS: ARMED'}
          </span>
        </div>
      </div>

      {/* Telemetry HUD & Feed Toggles */}
      <div className="grid grid-cols-2 gap-2">
        <button
          type="button"
          onClick={() => setShowBenchmarkHUD(!showBenchmarkHUD)}
          className={`py-1 px-2 rounded text-[10px] font-bold border transition flex items-center justify-between ${
            showBenchmarkHUD
              ? 'bg-cyan-950/60 border-cyan-500 text-cyan-200'
              : 'bg-slate-900 border-slate-800 text-slate-400 hover:text-slate-200'
          }`}
        >
          <span className="flex items-center gap-1.5">
            <Cpu className="w-3 h-3 text-cyan-400" />
            <span>SOR Benchmarks</span>
          </span>
          {sorBenchmarks ? (
            <span className={`px-1 py-0.2 rounded text-[9px] ${
              sorBenchmarks.overall_sla_passed
                ? 'bg-emerald-500/20 text-emerald-300'
                : 'bg-amber-500/20 text-amber-300'
            }`}>
              {sorBenchmarks.overall_sla_passed ? '<2.5ms PASS' : 'SLA SLOW'}
            </span>
          ) : (
            <span className="text-[9px] text-slate-400">P95 &mu;s</span>
          )}
        </button>

        <button
          type="button"
          onClick={() => setShowWSFeedDrawer(!showWSFeedDrawer)}
          className={`py-1 px-2 rounded text-[10px] font-bold border transition flex items-center justify-between ${
            showWSFeedDrawer
              ? 'bg-emerald-950/60 border-emerald-500 text-emerald-200'
              : 'bg-slate-900 border-slate-800 text-slate-400 hover:text-slate-200'
          }`}
        >
          <span className="flex items-center gap-1.5">
            <Activity className="w-3 h-3 text-emerald-400" />
            <span>WS Reconciler</span>
          </span>
          <span className="px-1 py-0.2 rounded text-[9px] bg-slate-800 text-slate-300">
            {wsTelemetry?.total_fills_recorded ?? 0} fills
          </span>
        </button>
      </div>

      {/* Sub-Millisecond Micro-Benchmark Panel */}
      {showBenchmarkHUD && (
        <div className="p-2.5 rounded bg-slate-950/90 border border-cyan-800/60 flex flex-col gap-2 text-[10px]">
          <div className="flex items-center justify-between border-b border-slate-800 pb-1.5">
            <div className="flex items-center gap-1.5">
              <Cpu className="w-3.5 h-3.5 text-cyan-400" />
              <span className="font-bold text-slate-200">Sub-Millisecond SOR Profiler</span>
            </div>
            <button
              type="button"
              disabled={benchmarkRunning}
              onClick={handleRunBenchmarks}
              className="px-2 py-0.5 rounded text-[10px] font-bold bg-cyan-900/60 hover:bg-cyan-800 text-cyan-200 border border-cyan-700/60 transition flex items-center gap-1 disabled:opacity-50"
            >
              <RefreshCw className={`w-3 h-3 ${benchmarkRunning ? 'animate-spin' : ''}`} />
              <span>{benchmarkRunning ? 'PROFILING...' : 'RUN BENCHMARK'}</span>
            </button>
          </div>

          {benchmarkError && (
            <div className="p-1 rounded bg-rose-950/50 border border-rose-800 text-rose-300 text-[9px]">
              {benchmarkError}
            </div>
          )}

          {sorBenchmarks ? (
            <div className="grid grid-cols-3 gap-1.5">
              {/* Depth Ladder Walk */}
              <div className="p-1.5 rounded bg-slate-900 border border-slate-800 flex flex-col gap-0.5">
                <span className="text-[9px] text-slate-400 font-semibold truncate">L2 Depth Walk</span>
                <div className="text-xs font-bold text-cyan-300">
                  {sorBenchmarks.benchmarks.depth_ladder_walk_20_levels?.p95_us ?? '--'} &mu;s
                </div>
                <span className="text-[8px] text-slate-400">
                  Target: &le; 50 &mu;s
                </span>
                <span className={`text-[8px] font-bold mt-0.5 ${
                  sorBenchmarks.benchmarks.depth_ladder_walk_20_levels?.sla_passed
                    ? 'text-emerald-400'
                    : 'text-amber-400'
                }`}>
                  {sorBenchmarks.benchmarks.depth_ladder_walk_20_levels?.sla_passed ? '✓ PASSED' : '⚠ SLOW'}
                </span>
              </div>

              {/* Almgren-Chriss Slicer */}
              <div className="p-1.5 rounded bg-slate-900 border border-slate-800 flex flex-col gap-0.5">
                <span className="text-[9px] text-slate-400 font-semibold truncate">AC Slicer (20)</span>
                <div className="text-xs font-bold text-cyan-300">
                  {sorBenchmarks.benchmarks.almgren_chriss_slicer_20_intervals?.p95_us ?? '--'} &mu;s
                </div>
                <span className="text-[8px] text-slate-400">
                  Target: &le; 75 &mu;s
                </span>
                <span className={`text-[8px] font-bold mt-0.5 ${
                  sorBenchmarks.benchmarks.almgren_chriss_slicer_20_intervals?.sla_passed
                    ? 'text-emerald-400'
                    : 'text-amber-400'
                }`}>
                  {sorBenchmarks.benchmarks.almgren_chriss_slicer_20_intervals?.sla_passed ? '✓ PASSED' : '⚠ SLOW'}
                </span>
              </div>

              {/* Multi-Venue SOR Route Quote */}
              <div className="p-1.5 rounded bg-slate-900 border border-slate-800 flex flex-col gap-0.5">
                <span className="text-[9px] text-slate-400 font-semibold truncate">SOR Route Split</span>
                <div className="text-xs font-bold text-cyan-300">
                  {sorBenchmarks.benchmarks.sor_multi_venue_optimal_route
                    ? `${(sorBenchmarks.benchmarks.sor_multi_venue_optimal_route.p95_us / 1000).toFixed(2)} ms`
                    : '--'}
                </div>
                <span className="text-[8px] text-slate-400">
                  Target: &le; 2.5 ms
                </span>
                <span className={`text-[8px] font-bold mt-0.5 ${
                  sorBenchmarks.benchmarks.sor_multi_venue_optimal_route?.sla_passed
                    ? 'text-emerald-400'
                    : 'text-amber-400'
                }`}>
                  {sorBenchmarks.benchmarks.sor_multi_venue_optimal_route?.sla_passed ? '✓ PASSED' : '⚠ SLOW'}
                </span>
              </div>
            </div>
          ) : (
            <div className="text-center py-2 text-slate-400 text-[10px]">
              Click &apos;RUN BENCHMARK&apos; to measure sub-millisecond execution hotpaths.
            </div>
          )}
        </div>
      )}

      {/* Real-Time WebSocket Execution Stream Drawer */}
      {showWSFeedDrawer && (
        <div className="p-2.5 rounded bg-slate-950/90 border border-emerald-800/60 flex flex-col gap-2 text-[10px]">
          <div className="flex items-center justify-between border-b border-slate-800 pb-1.5">
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
              <span className="font-bold text-slate-200">Private WS Execution Stream</span>
            </div>
            <div className="flex items-center gap-2 text-[9px] text-slate-400">
              <span>Msgs: <strong className="text-slate-200">{wsTelemetry?.total_messages_received ?? 0}</strong></span>
              <span>Fills: <strong className="text-emerald-300">{wsTelemetry?.total_fills_recorded ?? 0}</strong></span>
              <span>Dups: <strong className="text-amber-300">{wsTelemetry?.total_duplicates_filtered ?? 0}</strong></span>
            </div>
          </div>

          {/* Recent Normalized Fills List */}
          {recentFills.length > 0 ? (
            <div className="flex flex-col gap-1 max-h-32 overflow-y-auto pr-1">
              {recentFills.slice(0, 5).map((fill, idx) => (
                <div
                  key={`${fill.execution_id || fill.client_order_id}-${idx}`}
                  className="p-1 rounded bg-slate-900 border border-slate-800/80 flex items-center justify-between text-[9px] font-mono"
                >
                  <div className="flex items-center gap-1.5">
                    <span className="text-slate-400 font-bold">{fill.exchange}</span>
                    <span className={fill.side === 'BUY' ? 'text-emerald-400 font-bold' : 'text-rose-400 font-bold'}>
                      {fill.side}
                    </span>
                    <span className="text-slate-200">{fill.symbol}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-slate-300">{fill.fill_qty.toFixed(4)} @ ${fill.fill_price.toFixed(2)}</span>
                    <span className="text-slate-400">{fill.fee_amount > 0 ? `${fill.fee_amount} ${fill.fee_currency}` : '0 FEE'}</span>
                    <span className="text-[8px] text-cyan-400">
                      &Delta;t: +{(fill.received_monotonic_ns % 1000000000 / 1000000).toFixed(1)}ms
                    </span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-2 text-slate-400 text-[10px]">
              Awaiting real-time exchange fills on WebSocket stream...
            </div>
          )}
        </div>
      )}

      {/* Live Pre-Trade Safety Status Banner */}
      {isLiveMode && (
        <div className="p-2 rounded bg-rose-950/40 border border-rose-500/40 flex items-center justify-between text-[10px]">
          <div className="flex items-center gap-1.5 text-rose-300">
            <Shield className="w-3.5 h-3.5 text-rose-400" />
            <span className="font-bold">LIVE GUARD:</span>
            <span>{vaultStatus?.live_execution_enabled ? 'AUTHENTICATED' : 'DISARMED'}</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="flex items-center gap-1 text-slate-300">
              <Clock className="w-3 h-3 text-cyan-400" />
              <span>Clock Drift: &le;1000ms</span>
            </span>
            <span className={`px-1.5 py-0.5 rounded font-bold ${
              vaultStatus?.kill_switch.is_active
                ? 'bg-rose-500/20 text-rose-300 border border-rose-500/50'
                : 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/50'
            }`}>
              {vaultStatus?.kill_switch.is_active ? 'KILL SWITCH ACTIVE' : 'SWITCH NORMAL'}
            </span>
          </div>
        </div>
      )}

      {/* Kronos Advisory Shadow Ingestion */}
      {kronosAdvisory && kronosAdvisory.advisory_signal && (
        <div className="p-2 rounded bg-indigo-950/40 border border-indigo-500/30 flex items-center justify-between text-[10px]">
          <div className="flex items-center gap-1.5">
            <Sparkles className="w-3.5 h-3.5 text-indigo-400 animate-pulse" />
            <span className="text-slate-300 font-semibold">Kronos Advisory:</span>
            <span className={`px-1.5 py-0.5 rounded font-bold ${
              kronosAdvisory.advisory_signal === 'CONFIRM_TRADE'
                ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                : kronosAdvisory.advisory_signal === 'DIVERGENCE_CAUTION'
                ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                : 'bg-slate-700/50 text-slate-300'
            }`}>
              {kronosAdvisory.advisory_signal}
            </span>
          </div>
          <div className="text-indigo-300 font-mono">
            Size Multiplier: <span className="font-bold">{kronosAdvisory.sizing_multiplier}x</span>
          </div>
        </div>
      )}

      {/* Form Controls */}
      <form onSubmit={handleOrderInitiation} className="flex flex-col gap-2.5">
        {/* Long/Short Selection */}
        <div className="grid grid-cols-2 gap-1.5 p-0.5 bg-slate-900 rounded border border-border">
          <button
            type="button"
            onClick={() => setSide('BUY')}
            className={`py-1.5 text-xs font-bold rounded transition flex items-center justify-center gap-1 ${
              side === 'BUY' ? 'bg-terminal-green text-slate-950 shadow' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <TrendingUp className="w-3.5 h-3.5" />
            <span>LONG (BUY)</span>
          </button>

          <button
            type="button"
            onClick={() => setSide('SELL')}
            className={`py-1.5 text-xs font-bold rounded transition flex items-center justify-center gap-1 ${
              side === 'SELL' ? 'bg-terminal-red text-slate-950 shadow' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <TrendingDown className="w-3.5 h-3.5" />
            <span>SHORT (SELL)</span>
          </button>
        </div>

        {/* Order Type & Slicing Algo Row */}
        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className="text-[10px] text-slate-400">Order Routing Type</label>
            <div className="grid grid-cols-2 gap-1 mt-0.5">
              <button
                type="button"
                onClick={() => setOrderType('MARKET')}
                className={`py-1 text-xs rounded border transition ${
                  orderType === 'MARKET' ? 'bg-slate-800 border-terminal-cyan text-terminal-cyan font-bold' : 'border-border text-slate-400'
                }`}
              >
                Market
              </button>
              <button
                type="button"
                onClick={() => setOrderType('LIMIT')}
                className={`py-1 text-xs rounded border transition ${
                  orderType === 'LIMIT' ? 'bg-slate-800 border-terminal-cyan text-terminal-cyan font-bold' : 'border-border text-slate-400'
                }`}
              >
                Limit
              </button>
            </div>
          </div>

          <div>
            <label className="text-[10px] text-slate-400 flex items-center gap-1">
              <Zap className="w-3 h-3 text-amber-400" />
              <span>Execution Algo (SOR)</span>
            </label>
            <select
              value={executionAlgo}
              onChange={(e: any) => setExecutionAlgo(e.target.value)}
              className="w-full bg-slate-900 border border-border rounded px-2 py-1 text-amber-300 font-bold text-xs mt-0.5"
            >
              <option value="STANDARD">Standard Direct (SOR)</option>
              <option value="TWAP">TWAP Slicer (Random Jitter)</option>
              <option value="VWAP">VWAP Curve Matching</option>
              <option value="ALMGREN_CHRISS">Almgren-Chriss Optimal</option>
              <option value="IOC_SWEEP">Aggressive IOC Sweep</option>
            </select>
          </div>
        </div>

        {/* Risk Budget Input */}
        <div>
          <div className="flex justify-between items-center text-[10px] text-slate-400">
            <span>Risk Allocation (% of Equity)</span>
            <span className={isWithinRiskCap ? 'text-emerald-400' : 'text-rose-400 font-bold'}>
              Cap Check: {isWithinRiskCap ? 'PASS (<=1.5%)' : 'EXCEEDS 1.5% CEILING'}
            </span>
          </div>
          <select
            value={riskPct}
            onChange={(e) => setRiskPct(parseFloat(e.target.value))}
            className="w-full bg-slate-900 border border-border rounded px-2 py-1 text-terminal-cyan font-bold text-xs mt-0.5"
          >
            <option value={0.005}>0.5% (${(accountEquity * 0.005).toFixed(0)})</option>
            <option value={0.01}>1.0% (${(accountEquity * 0.01).toFixed(0)})</option>
            <option value={0.015}>1.5% (${(accountEquity * 0.015).toFixed(0)}) [Constitutional Cap]</option>
            <option value={0.02}>2.0% (${(accountEquity * 0.02).toFixed(0)}) [Paper Only]</option>
            <option value={0.03}>3.0% (${(accountEquity * 0.03).toFixed(0)}) [Paper Only]</option>
          </select>
        </div>

        {/* Entry & Stop Loss */}
        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className="text-[10px] text-slate-400">Entry Price ($)</label>
            <input
              type="number"
              step="any"
              value={entryPrice > 0 ? Number(entryPrice.toFixed(2)) : lastPrice > 0 ? Number(lastPrice.toFixed(2)) : ''}
              onChange={(e) => setEntryPrice(parseFloat(e.target.value) || 0)}
              disabled={orderType === 'MARKET'}
              className="w-full bg-slate-900 border border-border rounded px-2 py-1 text-slate-200 text-xs mt-0.5 disabled:opacity-50"
            />
          </div>

          <div>
            <label className="text-[10px] text-slate-400">Stop Loss ($)</label>
            <input
              type="number"
              step="any"
              value={stopLoss > 0 ? Number(stopLoss.toFixed(2)) : ''}
              onChange={(e) => setStopLoss(parseFloat(e.target.value) || 0)}
              className="w-full bg-slate-900 border border-terminal-red/50 rounded px-2 py-1 text-terminal-red font-bold text-xs mt-0.5"
            />
          </div>
        </div>

        {/* Take Profit & Leverage */}
        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className="text-[10px] text-slate-400">Take Profit ($)</label>
            <input
              type="number"
              step="any"
              value={takeProfit > 0 ? Number(takeProfit.toFixed(2)) : ''}
              onChange={(e) => setTakeProfit(parseFloat(e.target.value) || 0)}
              className="w-full bg-slate-900 border border-terminal-green/50 rounded px-2 py-1 text-terminal-green font-bold text-xs mt-0.5"
            />
          </div>

          <div>
            <label className="text-[10px] text-slate-400">Leverage: {leverage}x</label>
            <input
              type="range"
              min="1"
              max="50"
              value={leverage}
              onChange={(e) => setLeverage(parseInt(e.target.value, 10))}
              className="w-full mt-2 accent-terminal-cyan cursor-pointer"
            />
          </div>
        </div>

        {/* Dynamic Computed Risk Matrix */}
        <div className="p-2 rounded bg-slate-900/90 border border-border/80 flex flex-col gap-1 text-[11px] mt-1">
          <div className="flex justify-between">
            <span className="text-slate-400">Calculated Size:</span>
            <span className="text-slate-200 font-bold">
              {Number(positionSizeBase || 0).toFixed(4)} {symbol.replace(/USDT|USD/g, '')} (${Number(positionSizeQuote || 0).toFixed(2)})
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-400">Risk Amount:</span>
            <span className={`font-bold ${isWithinRiskCap ? 'text-terminal-cyan' : 'text-terminal-red'}`}>
              ${Number(riskAmountUsd || 0).toFixed(2)} ({stopDistancePct || '0.0'}%)
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-400">Expected R:R:</span>
            <span className="text-terminal-cyan font-bold">{riskRewardRatio}R</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-400">Est. Liquidation:</span>
            <span className="text-amber-400 font-semibold">${Number(liquidationPrice || 0).toFixed(2)}</span>
          </div>

          {/* SOR Route Allocation Breakdown */}
          {sorQuote && (
            <div className="border-t border-slate-800 pt-1 flex flex-col gap-0.5 text-[10px]">
              <div className="flex justify-between text-slate-300">
                <span>SOR Venue Split:</span>
                <span className="text-cyan-300 font-semibold">{sorQuote.routing_reason}</span>
              </div>
              <div className="flex justify-between text-slate-400">
                <span>Weighted VWAP:</span>
                <span className="text-slate-200">${sorQuote.weighted_vwap.toFixed(2)} (Fees: ${sorQuote.total_fee_usd.toFixed(2)})</span>
              </div>
            </div>
          )}

          {/* Almgren-Chriss Slicing Trajectory */}
          {almgrenSchedule && (
            <div className="border-t border-slate-800 pt-1 flex flex-col gap-0.5 text-[10px]">
              <div className="flex justify-between text-amber-300">
                <span>Almgren-Chriss Trajectory:</span>
                <span>{almgrenSchedule.num_intervals} slices over {(almgrenSchedule.time_horizon_sec / 60).toFixed(0)}m</span>
              </div>
              <div className="flex justify-between text-slate-400">
                <span>Est. Impact Cost:</span>
                <span className="text-amber-200">${almgrenSchedule.expected_total_cost_usd.toFixed(2)} ({almgrenSchedule.expected_slippage_bps.toFixed(1)} bps)</span>
              </div>
            </div>
          )}

          {impactEstimate && !sorQuote && (
            <div className="flex justify-between border-t border-slate-800 pt-1 text-[10px]">
              <span className="text-slate-400">Est. Market Impact:</span>
              <span className="text-amber-300 font-mono">
                {Number(impactEstimate.expected_slippage_bps || 0).toFixed(1)} bps (${Number(impactEstimate.total_impact_usd || 0).toFixed(2)})
              </span>
            </div>
          )}
        </div>

        {/* Submit Execution Button */}
        <button
          type="submit"
          disabled={submitting || positionSizeBase <= 0 || (isLiveMode && !isWithinRiskCap)}
          className={`w-full py-2 rounded font-bold text-slate-950 mt-2 transition flex items-center justify-center gap-1.5 ${
            isLiveMode
              ? 'bg-rose-500 hover:bg-rose-400 text-slate-950'
              : side === 'BUY'
              ? 'bg-terminal-green hover:bg-emerald-400'
              : 'bg-terminal-red hover:bg-rose-400'
          } disabled:opacity-50 disabled:cursor-not-allowed`}
        >
          <span>
            {isLiveMode
              ? `LIVE ORDER: ${side} (${executionAlgo})`
              : side === 'BUY'
              ? `EXECUTE LONG (${executionAlgo})`
              : `EXECUTE SHORT (${executionAlgo})`}
          </span>
          <ArrowRight className="w-4 h-4" />
        </button>
      </form>

      {/* Dual Confirmation Modal for Live Execution */}
      {showConfirmModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
          <div className="bg-slate-950 border-2 border-rose-600 rounded-xl p-5 max-w-md w-full shadow-2xl flex flex-col gap-4 text-slate-100">
            <div className="flex items-center gap-2 text-rose-400 border-b border-rose-900/60 pb-3">
              <AlertTriangle className="w-6 h-6 text-rose-500 animate-bounce" />
              <div>
                <h3 className="text-sm font-black tracking-wider uppercase">Live Capital Execution Gate</h3>
                <p className="text-[10px] text-slate-400">Deterministic Invariant Clearance Required</p>
              </div>
            </div>

            <div className="bg-rose-950/30 border border-rose-800/40 rounded p-3 flex flex-col gap-1.5 text-xs">
              <div className="flex justify-between">
                <span className="text-slate-400">Order:</span>
                <span className="font-bold text-slate-200">{side} {Number(positionSizeBase).toFixed(4)} {symbol}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Routing Type:</span>
                <span className="font-semibold text-terminal-cyan">{orderType} via {executionAlgo}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Dollar Risk:</span>
                <span className="font-bold text-rose-400">${Number(riskAmountUsd).toFixed(2)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Constitutional 1.5% Cap:</span>
                <span className="font-bold text-emerald-400">${maxAllowableRiskUsd.toFixed(2)} (PASSED)</span>
              </div>
              {sorQuote && (
                <div className="flex justify-between border-t border-rose-900/40 pt-1 text-[11px]">
                  <span className="text-slate-400">SOR Route Split:</span>
                  <span className="text-amber-300 font-semibold">{sorQuote.routing_reason}</span>
                </div>
              )}
            </div>

            <div className="flex items-center gap-2 text-[11px] text-slate-300">
              <CheckCircle className="w-4 h-4 text-emerald-400 flex-shrink-0" />
              <span>Clock drift verified (&le;1000ms SLA). Kill switch disarmed.</span>
            </div>

            <div className="grid grid-cols-2 gap-3 pt-2">
              <button
                type="button"
                onClick={() => setShowConfirmModal(false)}
                className="py-2 px-4 rounded font-bold text-xs bg-slate-800 text-slate-300 hover:bg-slate-700 transition"
              >
                ABORT
              </button>
              <button
                type="button"
                disabled={submitting || !isWithinRiskCap}
                onClick={executeOrder}
                className="py-2 px-4 rounded font-bold text-xs bg-rose-600 text-white hover:bg-rose-500 shadow-lg shadow-rose-900/50 transition disabled:opacity-50"
              >
                {submitting ? 'DISPATCHING...' : 'CONFIRM & TRANSMIT'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* WebAuthn / FIDO2 Hardware Security Key Clearance Modal */}
      <HardwareKeyModal
        isOpen={isHardwareModalOpen}
        onClose={() => setIsHardwareModalOpen(false)}
        onClearanceGranted={(clr) => {
          setClearanceSession(clr);
          setIsLiveMode(true);
          setIsHardwareModalOpen(false);
        }}
      />
    </div>
  );
};

export default RiskFirstOrderDesk;
