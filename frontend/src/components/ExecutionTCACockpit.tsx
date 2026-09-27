import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Activity,
  Shield,
  ShieldAlert,
  ShieldCheck,
  CheckCircle2,
  RefreshCw,
  Clock,
  Zap,
  PieChart,
  BarChart2,
  AlertOctagon,
  Flame,
  Scale,
  X,
} from 'lucide-react';
import {
  api,
  TCASummary,
  TCARecord,
  DeltaExposureSummary,
  BasisFundingMetric,
  ProposedHedgeOrder,
  CollateralReport,
  SORFailoverStatus,
} from '../services/api';

interface ExecutionTCACockpitProps {
  symbol?: string;
  onNotify?: (type: 'success' | 'error' | 'warning' | 'info', title: string, message: string) => void;
}

export const ExecutionTCACockpit: React.FC<ExecutionTCACockpitProps> = ({
  symbol = 'BTCUSDT',
  onNotify,
}) => {
  const [loading, setLoading] = useState<boolean>(true);
  const [lastRefreshed, setLastRefreshed] = useState<Date>(new Date());

  // Data States
  const [tcaSummary, setTcaSummary] = useState<TCASummary | null>(null);
  const [tcaRecords, setTcaRecords] = useState<TCARecord[]>([]);
  const [deltaExposure, setDeltaExposure] = useState<DeltaExposureSummary | null>(null);
  const [basisMetric, setBasisMetric] = useState<BasisFundingMetric | null>(null);
  const [proposedHedge, setProposedHedge] = useState<ProposedHedgeOrder | null>(null);
  const [collateralReport, setCollateralReport] = useState<CollateralReport | null>(null);
  const [sorStatus, setSorStatus] = useState<SORFailoverStatus | null>(null);

  // Modal & Confirmation States
  const [showHedgeModal, setShowHedgeModal] = useState<boolean>(false);
  const [hedgeConfirmationInput, setHedgeConfirmationInput] = useState<string>('');
  const [executingHedge, setExecutingHedge] = useState<boolean>(false);

  const [showAbortModal, setShowAbortModal] = useState<boolean>(false);
  const [abortingSlicers, setAbortingSlicers] = useState<boolean>(false);

  const [showFlattenModal, setShowFlattenModal] = useState<boolean>(false);
  const [flattenConfirmationInput, setFlattenConfirmationInput] = useState<string>('');
  const [flatteningDelta, setFlatteningDelta] = useState<boolean>(false);

  const [activeTab, setActiveTab] = useState<'TCA_WATERFALL' | 'COLLATERAL_MATRIX' | 'DELTA_HEDGER' | 'SOR_FAILOVER'>('TCA_WATERFALL');

  const onNotifyRef = useRef(onNotify);
  useEffect(() => {
    onNotifyRef.current = onNotify;
  }, [onNotify]);

  // Load all Phase 23 Telemetry
  const fetchAllData = useCallback(async () => {
    setLoading(true);
    try {
      const baseAsset = symbol.replace(/USDT|USD|BUSD/i, '') || 'BTC';
      const [tcaSumRes, tcaRecsRes, deltaRes, collatRes, sorRes] = await Promise.all([
        api.getTCASummary(symbol).catch(() => null),
        api.getTCARecords(20).catch(() => null),
        api.getDeltaExposure(baseAsset).catch(() => null),
        api.getCollateralReport().catch(() => null),
        api.getSORFailoverStatus(symbol).catch(() => null),
      ]);

      if (tcaSumRes?.summary) setTcaSummary(tcaSumRes.summary);
      if (tcaRecsRes?.records) setTcaRecords(tcaRecsRes.records);
      if (deltaRes?.exposure) {
        setDeltaExposure(deltaRes.exposure);
        if (deltaRes.basis_metric) setBasisMetric(deltaRes.basis_metric);

        // If delta tolerance is breached, generate a proposed hedge
        if (deltaRes.exposure.tolerance_breached) {
          const prop = await api.proposeDeltaHedge({
            asset: baseAsset,
            reference_price: deltaRes.basis_metric?.spot_price || 65000.0,
          }).catch(() => null);
          if (prop?.proposed_hedge) {
            setProposedHedge(prop.proposed_hedge);
          }
        } else {
          setProposedHedge(null);
        }
      }
      if (collatRes?.collateral_report) setCollateralReport(collatRes.collateral_report);
      if (sorRes) setSorStatus(sorRes);

      setLastRefreshed(new Date());
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Telemetry sync failure';
      onNotifyRef.current?.('error', 'Execution Cockpit Sync Error', msg);
    } finally {
      setLoading(false);
    }
  }, [symbol]);

  useEffect(() => {
    fetchAllData();
    const timer = setInterval(fetchAllData, 10000);
    return () => clearInterval(timer);
  }, [fetchAllData]);

  // Trigger Hedge Execution
  const handleExecuteHedge = async () => {
    if (!proposedHedge) return;
    if (hedgeConfirmationInput !== 'EXECUTE_AUTHORIZED_HEDGE') {
      onNotifyRef.current?.('warning', 'Confirmation Mismatch', 'Must type EXECUTE_AUTHORIZED_HEDGE exactly.');
      return;
    }

    setExecutingHedge(true);
    try {
      const res = await api.executeAuthorizedHedge({
        hedge_id: proposedHedge.hedge_id,
        confirmation_phrase: hedgeConfirmationInput,
        environment: 'PRODUCTION',
      });

      if (res.status === 'AUTHORIZED') {
        onNotifyRef.current?.('success', 'Delta Hedge Authorized', `Hedge ${proposedHedge.hedge_id} dispatched through risk gate.`);
        setShowHedgeModal(false);
        setHedgeConfirmationInput('');
        fetchAllData();
      } else {
        onNotifyRef.current?.('error', 'Risk Gate Blocked Hedge', res.reasons?.join('; ') || 'Blocked by risk desk.');
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Execution error';
      onNotifyRef.current?.('error', 'Hedge Execution Failed', msg);
    } finally {
      setExecutingHedge(false);
    }
  };

  // Trigger Abort Slicers
  const handleAbortSlicers = async () => {
    setAbortingSlicers(true);
    try {
      const res = await api.abortActiveSlicers();
      onNotifyRef.current?.('warning', 'Active Slicers Aborted', res.message);
      setShowAbortModal(false);
      fetchAllData();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Abort failed';
      onNotifyRef.current?.('error', 'Abort Slicers Failed', msg);
    } finally {
      setAbortingSlicers(false);
    }
  };

  // Trigger Flatten Delta
  const handleFlattenDelta = async () => {
    if (flattenConfirmationInput !== 'FLATTEN_DELTA_CONFIRMED') {
      onNotifyRef.current?.('warning', 'Confirmation Mismatch', 'Must type FLATTEN_DELTA_CONFIRMED exactly.');
      return;
    }

    setFlatteningDelta(true);
    try {
      const baseAsset = symbol.replace(/USDT|USD|BUSD/i, '') || 'BTC';
      const res = await api.emergencyFlattenDelta(baseAsset, flattenConfirmationInput);
      onNotifyRef.current?.('success', 'Delta Flatten Dispatched', res.message);
      setShowFlattenModal(false);
      setFlattenConfirmationInput('');
      fetchAllData();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Flatten failed';
      onNotifyRef.current?.('error', 'Flatten Delta Failed', msg);
    } finally {
      setFlatteningDelta(false);
    }
  };

  // Render Markout Curve Visualization
  const renderMarkoutBar = (label: string, bps: number | null) => {
    if (bps === null || bps === undefined) {
      return (
        <div className="flex flex-col items-center flex-1 bg-slate-900/60 p-2 rounded border border-slate-800">
          <span className="text-[10px] text-slate-500 font-mono">{label}</span>
          <span className="text-xs text-slate-600 font-mono mt-1">N/A</span>
        </div>
      );
    }

    const isAdverse = bps > 0;
    const barHeight = Math.min(Math.abs(bps) * 4 + 6, 48);

    return (
      <div className="flex flex-col items-center flex-1 bg-slate-900/60 p-2 rounded border border-slate-800">
        <span className="text-[10px] text-slate-400 font-mono">{label}</span>
        <div className="h-14 flex items-center justify-center my-1 w-full">
          <div
            style={{ height: `${barHeight}px` }}
            className={`w-6 rounded transition-all flex items-center justify-center text-[9px] font-bold font-mono ${
              isAdverse ? 'bg-rose-500/80 text-white' : 'bg-emerald-500/80 text-slate-950'
            }`}
          >
            {bps > 0 ? `+${bps.toFixed(1)}` : bps.toFixed(1)}
          </div>
        </div>
        <span className={`text-[10px] font-mono font-bold ${isAdverse ? 'text-rose-400' : 'text-emerald-400'}`}>
          {isAdverse ? 'Adverse' : 'Favorable'}
        </span>
      </div>
    );
  };

  return (
    <div className="flex flex-col gap-3 font-sans text-slate-200">
      {/* Top Header & Emergency Bar */}
      <div className="flex flex-wrap items-center justify-between gap-2 p-3 bg-[#0B0E14] border border-[#1e293b] rounded-lg shadow-lg">
        <div className="flex items-center gap-2.5">
          <div className="p-2 bg-gradient-to-br from-sky-500 to-indigo-600 rounded-lg text-white shadow-md shadow-sky-500/20">
            <Activity size={18} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-bold tracking-wide uppercase text-white font-mono">
                Phase 23: Execution, TCA & Delta Hedging Cockpit
              </h2>
              <span className="px-2 py-0.5 text-[10px] font-bold font-mono rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
                GOVERNOR PRIMACY ACTIVE
              </span>
            </div>
            <p className="text-[11px] text-slate-400">
              Perold (1988) Implementation Shortfall • Signed Markouts • Multi-Venue Delta • Collateral Safety
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={fetchAllData}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-mono font-bold rounded bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition-all"
          >
            <RefreshCw size={13} className={loading ? 'animate-spin text-sky-400' : ''} />
            <span>Sync ({lastRefreshed.toLocaleTimeString()})</span>
          </button>

          {/* Emergency Actions */}
          <button
            onClick={() => setShowAbortModal(true)}
            className="flex items-center gap-1 px-3 py-1.5 text-xs font-mono font-bold rounded bg-amber-600/20 hover:bg-amber-600/30 text-amber-300 border border-amber-500/40 transition-all"
          >
            <AlertOctagon size={13} />
            <span>Abort Slicers</span>
          </button>

          <button
            onClick={() => setShowFlattenModal(true)}
            className="flex items-center gap-1 px-3 py-1.5 text-xs font-mono font-bold rounded bg-rose-600/20 hover:bg-rose-600/30 text-rose-300 border border-rose-500/40 transition-all"
          >
            <Flame size={13} />
            <span>Emergency Flatten Delta</span>
          </button>
        </div>
      </div>

      {/* Navigation Sub-Tabs */}
      <div className="flex items-center gap-1 p-1 bg-[#090d16] border border-[#1e293b] rounded-lg text-xs font-mono">
        <button
          onClick={() => setActiveTab('TCA_WATERFALL')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded transition-all ${
            activeTab === 'TCA_WATERFALL'
              ? 'bg-sky-500 text-white font-bold shadow'
              : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          <BarChart2 size={13} />
          <span>1. TCA Waterfall & Markouts</span>
        </button>

        <button
          onClick={() => setActiveTab('DELTA_HEDGER')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded transition-all ${
            activeTab === 'DELTA_HEDGER'
              ? 'bg-sky-500 text-white font-bold shadow'
              : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          <Scale size={13} />
          <span>2. Delta & Basis Hedger</span>
          {deltaExposure?.tolerance_breached && (
            <span className="px-1.5 py-0.2 bg-rose-500 text-white text-[9px] font-bold rounded-full animate-pulse">
              BREACH
            </span>
          )}
        </button>

        <button
          onClick={() => setActiveTab('COLLATERAL_MATRIX')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded transition-all ${
            activeTab === 'COLLATERAL_MATRIX'
              ? 'bg-sky-500 text-white font-bold shadow'
              : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          <Shield size={13} />
          <span>3. Collateral Governor Matrix</span>
          {collateralReport?.systemic_risk_state !== 'NORMAL' && (
            <span className="px-1.5 py-0.2 bg-amber-500 text-slate-950 text-[9px] font-bold rounded-full">
              {collateralReport?.systemic_risk_state || 'ALERT'}
            </span>
          )}
        </button>

        <button
          onClick={() => setActiveTab('SOR_FAILOVER')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded transition-all ${
            activeTab === 'SOR_FAILOVER'
              ? 'bg-sky-500 text-white font-bold shadow'
              : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          <Zap size={13} />
          <span>4. SOR Failover & VPIN Radar</span>
          {sorStatus?.vpin_circuit_breaker.is_paused && (
            <span className="px-1.5 py-0.2 bg-rose-500 text-white text-[9px] font-bold rounded-full animate-pulse">
              VPIN PAUSED
            </span>
          )}
        </button>
      </div>

      {/* TAB 1: TCA WATERFALL & MARKOUTS */}
      {activeTab === 'TCA_WATERFALL' && (
        <div className="flex flex-col gap-3">
          {/* Top KPIs */}
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-2">
            <div className="p-3 bg-[#0B0E14] border border-[#1e293b] rounded-lg">
              <span className="text-[10px] text-slate-400 font-mono uppercase">Total Executions</span>
              <div className="text-lg font-bold font-mono text-white mt-1">
                {tcaSummary?.total_executions || 0}
              </div>
              <span className="text-[10px] text-slate-500">
                ${(tcaSummary?.total_notional_usd || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })} Notional
              </span>
            </div>

            <div className="p-3 bg-[#0B0E14] border border-[#1e293b] rounded-lg">
              <span className="text-[10px] text-slate-400 font-mono uppercase">Mean Shortfall (IS)</span>
              <div className={`text-lg font-bold font-mono mt-1 ${
                (tcaSummary?.mean_implementation_shortfall_bps || 0) > 0 ? 'text-rose-400' : 'text-emerald-400'
              }`}>
                {(tcaSummary?.mean_implementation_shortfall_bps || 0).toFixed(2)} bps
              </div>
              <span className="text-[10px] text-slate-500">
                {(tcaSummary?.mean_implementation_shortfall_bps || 0) > 0 ? 'Adverse Cost' : 'Price Improvement'}
              </span>
            </div>

            <div className="p-3 bg-[#0B0E14] border border-[#1e293b] rounded-lg">
              <span className="text-[10px] text-slate-400 font-mono uppercase">Mean Slippage</span>
              <div className="text-lg font-bold font-mono text-white mt-1">
                {(tcaSummary?.mean_slippage_bps || 0).toFixed(2)} bps
              </div>
              <span className="text-[10px] text-slate-500">vs Arrival Mid</span>
            </div>

            <div className="p-3 bg-[#0B0E14] border border-[#1e293b] rounded-lg">
              <span className="text-[10px] text-slate-400 font-mono uppercase">Market Impact</span>
              <div className="text-lg font-bold font-mono text-amber-400 mt-1">
                {(tcaSummary?.mean_market_impact_bps || 0).toFixed(2)} bps
              </div>
              <span className="text-[10px] text-slate-500">Orderbook Push</span>
            </div>

            <div className="p-3 bg-[#0B0E14] border border-[#1e293b] rounded-lg">
              <span className="text-[10px] text-slate-400 font-mono uppercase">Mean Fee Paid</span>
              <div className="text-lg font-bold font-mono text-slate-300 mt-1">
                {(tcaSummary?.mean_fee_bps || 0).toFixed(2)} bps
              </div>
              <span className="text-[10px] text-slate-500">Exchange Friction</span>
            </div>

            <div className="p-3 bg-[#0B0E14] border border-[#1e293b] rounded-lg">
              <span className="text-[10px] text-slate-400 font-mono uppercase">Flow Quality</span>
              <div className="flex items-center gap-2 mt-1">
                <span className="text-sm font-bold font-mono text-emerald-400">
                  +{tcaSummary?.price_improvement_count || 0}
                </span>
                <span className="text-xs text-slate-600">/</span>
                <span className="text-sm font-bold font-mono text-rose-400">
                  -{tcaSummary?.adverse_selection_count || 0}
                </span>
              </div>
              <span className="text-[10px] text-slate-500">Imprv vs Adverse</span>
            </div>
          </div>

          {/* Waterfall Decomposition & Markout Profile */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            {/* Implementation Shortfall Waterfall */}
            <div className="p-4 bg-[#0B0E14] border border-[#1e293b] rounded-lg">
              <div className="flex items-center justify-between pb-2 border-b border-slate-800">
                <div className="flex items-center gap-2">
                  <PieChart size={15} className="text-sky-400" />
                  <h3 className="text-xs font-bold font-mono uppercase text-white">
                    Perold Implementation Shortfall Waterfall
                  </h3>
                </div>
                <span className="text-[10px] font-mono text-slate-400">
                  Signed: (+) Cost / (-) Gain
                </span>
              </div>

              <div className="flex flex-col gap-2.5 mt-3">
                <div className="flex items-center justify-between text-xs font-mono">
                  <span className="text-slate-400">1. Delay Cost (Decision &rarr; Arrival)</span>
                  <span className={(tcaSummary?.mean_delay_cost_bps || 0) > 0 ? 'text-rose-400' : 'text-emerald-400'}>
                    {(tcaSummary?.mean_delay_cost_bps || 0).toFixed(2)} bps
                  </span>
                </div>
                <div className="w-full bg-slate-900 rounded-full h-1.5 overflow-hidden">
                  <div
                    style={{ width: `${Math.min(Math.abs(tcaSummary?.mean_delay_cost_bps || 0) * 10, 100)}%` }}
                    className={`h-full ${ (tcaSummary?.mean_delay_cost_bps || 0) > 0 ? 'bg-rose-500' : 'bg-emerald-500'}`}
                  />
                </div>

                <div className="flex items-center justify-between text-xs font-mono">
                  <span className="text-slate-400">2. Spread Cost (Half-Spread Crossing)</span>
                  <span className="text-amber-400 font-bold">
                    {(tcaSummary?.mean_spread_cost_bps || 0).toFixed(2)} bps
                  </span>
                </div>
                <div className="w-full bg-slate-900 rounded-full h-1.5 overflow-hidden">
                  <div
                    style={{ width: `${Math.min(Math.abs(tcaSummary?.mean_spread_cost_bps || 0) * 10, 100)}%` }}
                    className="h-full bg-amber-500"
                  />
                </div>

                <div className="flex items-center justify-between text-xs font-mono">
                  <span className="text-slate-400">3. Market Impact (Arrival &rarr; VWAP)</span>
                  <span className={(tcaSummary?.mean_market_impact_bps || 0) > 0 ? 'text-rose-400' : 'text-emerald-400'}>
                    {(tcaSummary?.mean_market_impact_bps || 0).toFixed(2)} bps
                  </span>
                </div>
                <div className="w-full bg-slate-900 rounded-full h-1.5 overflow-hidden">
                  <div
                    style={{ width: `${Math.min(Math.abs(tcaSummary?.mean_market_impact_bps || 0) * 10, 100)}%` }}
                    className="h-full bg-indigo-500"
                  />
                </div>

                <div className="flex items-center justify-between text-xs font-mono">
                  <span className="text-slate-400">4. Direct Exchange Fees & Commissions</span>
                  <span className="text-slate-300">
                    {(tcaSummary?.mean_fee_bps || 0).toFixed(2)} bps
                  </span>
                </div>
                <div className="w-full bg-slate-900 rounded-full h-1.5 overflow-hidden">
                  <div
                    style={{ width: `${Math.min(Math.abs(tcaSummary?.mean_fee_bps || 0) * 10, 100)}%` }}
                    className="h-full bg-slate-500"
                  />
                </div>

                <div className="pt-2 mt-2 border-t border-slate-800 flex items-center justify-between font-mono font-bold text-sm">
                  <span className="text-white">Total Implementation Shortfall</span>
                  <span className={(tcaSummary?.mean_implementation_shortfall_bps || 0) > 0 ? 'text-rose-400' : 'text-emerald-400'}>
                    {(tcaSummary?.mean_implementation_shortfall_bps || 0).toFixed(2)} bps
                  </span>
                </div>
              </div>
            </div>

            {/* Asynchronous Post-Trade Markout Curve */}
            <div className="p-4 bg-[#0B0E14] border border-[#1e293b] rounded-lg flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between pb-2 border-b border-slate-800">
                  <div className="flex items-center gap-2">
                    <Clock size={15} className="text-sky-400" />
                    <h3 className="text-xs font-bold font-mono uppercase text-white">
                      Asynchronous Post-Trade Markout Curve
                    </h3>
                  </div>
                  <span className="text-[10px] font-mono text-slate-400">
                    5 Horizons (1s &rarr; 300s)
                  </span>
                </div>

                <div className="flex items-end justify-between gap-2 mt-4">
                  {renderMarkoutBar('1s', tcaSummary?.markout_1s_bps ?? null)}
                  {renderMarkoutBar('5s', tcaSummary?.markout_5s_bps ?? null)}
                  {renderMarkoutBar('30s', tcaSummary?.markout_30s_bps ?? null)}
                  {renderMarkoutBar('60s', tcaSummary?.markout_60s_bps ?? null)}
                  {renderMarkoutBar('300s', tcaSummary?.markout_300s_bps ?? null)}
                </div>
              </div>

              <div className="p-2.5 bg-slate-900/50 rounded border border-slate-800 text-[11px] text-slate-400 mt-4 leading-relaxed">
                <span className="text-sky-400 font-bold">Markout Interpretation:</span> Positive markouts indicate the asset price moved against the fill post-execution (adverse selection/toxic flow). Negative markouts indicate price improvement or favorable passive execution.
              </div>
            </div>
          </div>

          {/* Recent TCA Records Table */}
          <div className="p-4 bg-[#0B0E14] border border-[#1e293b] rounded-lg">
            <div className="flex items-center justify-between pb-2 border-b border-slate-800">
              <h3 className="text-xs font-bold font-mono uppercase text-white">
                Recent Durable TCA Executions ({tcaRecords.length})
              </h3>
              <span className="text-[10px] font-mono text-slate-400">
                Persisted in SQLite Ledger
              </span>
            </div>

            <div className="overflow-x-auto mt-3">
              <table className="w-full text-left text-xs font-mono">
                <thead>
                  <tr className="border-b border-slate-800 text-slate-400 text-[11px]">
                    <th className="pb-2">Execution ID</th>
                    <th className="pb-2">Pair / Venue</th>
                    <th className="pb-2">Side</th>
                    <th className="pb-2">Filled Qty</th>
                    <th className="pb-2">Exec VWAP</th>
                    <th className="pb-2">IS (bps)</th>
                    <th className="pb-2">Impact (bps)</th>
                    <th className="pb-2">1s Markout</th>
                    <th className="pb-2">60s Markout</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/50">
                  {tcaRecords.length === 0 ? (
                    <tr>
                      <td colSpan={9} className="py-4 text-center text-slate-500">
                        No TCA execution records recorded yet.
                      </td>
                    </tr>
                  ) : (
                    tcaRecords.map((rec) => (
                      <tr key={rec.execution_id} className="hover:bg-slate-900/40 transition-colors">
                        <td className="py-2 text-slate-300 font-bold">{rec.execution_id.slice(0, 10)}...</td>
                        <td className="py-2 text-slate-400">
                          {rec.symbol} <span className="text-[10px] text-sky-400">({rec.venue})</span>
                        </td>
                        <td className="py-2">
                          <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                            rec.side === 'BUY' ? 'bg-emerald-500/10 text-emerald-400' : 'bg-rose-500/10 text-rose-400'
                          }`}>
                            {rec.side}
                          </span>
                        </td>
                        <td className="py-2 text-slate-300">{rec.filled_qty.toFixed(4)}</td>
                        <td className="py-2 text-slate-200">${rec.executed_vwap.toFixed(2)}</td>
                        <td className={`py-2 font-bold ${rec.total_cost_bps > 0 ? 'text-rose-400' : 'text-emerald-400'}`}>
                          {rec.total_cost_bps.toFixed(2)}
                        </td>
                        <td className="py-2 text-amber-400">{rec.market_impact_bps.toFixed(2)}</td>
                        <td className="py-2 text-slate-400">
                          {rec.markout_1s_bps !== null ? `${rec.markout_1s_bps.toFixed(1)} bps` : '-'}
                        </td>
                        <td className="py-2 text-slate-400">
                          {rec.markout_60s_bps !== null ? `${rec.markout_60s_bps.toFixed(1)} bps` : '-'}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: DELTA & BASIS HEDGER */}
      {activeTab === 'DELTA_HEDGER' && (
        <div className="flex flex-col gap-3">
          {/* Net Delta Overview Cards */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {/* Consolidated Net Delta Card */}
            <div className={`p-4 rounded-lg border ${
              deltaExposure?.tolerance_breached
                ? 'bg-rose-950/20 border-rose-500/50'
                : 'bg-[#0B0E14] border-[#1e293b]'
            }`}>
              <div className="flex items-center justify-between pb-2 border-b border-slate-800">
                <span className="text-xs font-bold font-mono uppercase text-slate-400">
                  Consolidated Net Delta (&Delta; Net)
                </span>
                <span className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold ${
                  deltaExposure?.tolerance_breached
                    ? 'bg-rose-500 text-white animate-pulse'
                    : 'bg-emerald-500/10 text-emerald-400'
                }`}>
                  {deltaExposure?.tolerance_breached ? 'TOLERANCE BREACH' : 'NEUTRAL / IN-BAND'}
                </span>
              </div>

              <div className="mt-3">
                <div className="text-2xl font-bold font-mono text-white">
                  {(deltaExposure?.net_delta_qty || 0) > 0 ? `+${(deltaExposure?.net_delta_qty || 0).toFixed(4)}` : (deltaExposure?.net_delta_qty || 0).toFixed(4)}{' '}
                  <span className="text-sm text-sky-400">{deltaExposure?.asset || 'BTC'}</span>
                </div>
                <div className="text-sm font-mono text-slate-400 mt-1">
                  ${(deltaExposure?.net_delta_usd || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })} USD
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2 mt-4 pt-3 border-t border-slate-800/80 text-xs font-mono">
                <div>
                  <span className="text-slate-500 text-[10px]">Total Long Notional</span>
                  <div className="text-emerald-400 font-bold">
                    ${(deltaExposure?.total_long_usd || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}
                  </div>
                </div>
                <div>
                  <span className="text-slate-500 text-[10px]">Total Short Notional</span>
                  <div className="text-rose-400 font-bold">
                    ${(deltaExposure?.total_short_usd || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}
                  </div>
                </div>
              </div>
            </div>

            {/* Basis & Funding Carry Metric */}
            <div className="p-4 bg-[#0B0E14] border border-[#1e293b] rounded-lg">
              <div className="flex items-center justify-between pb-2 border-b border-slate-800">
                <span className="text-xs font-bold font-mono uppercase text-slate-400">
                  Spot-Perp Basis & Carry
                </span>
                <span className="text-[10px] font-mono text-sky-400">
                  {basisMetric?.venue || 'BINANCE'}
                </span>
              </div>

              <div className="flex flex-col gap-2 mt-3 text-xs font-mono">
                <div className="flex items-center justify-between">
                  <span className="text-slate-400">Spot / Perp Price</span>
                  <span className="text-white font-bold">
                    ${(basisMetric?.spot_price || 0).toFixed(2)} / ${(basisMetric?.perp_price || 0).toFixed(2)}
                  </span>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-slate-400">Basis Spread</span>
                  <span className={(basisMetric?.basis_bps || 0) >= 0 ? 'text-emerald-400 font-bold' : 'text-rose-400 font-bold'}>
                    {(basisMetric?.basis_bps || 0).toFixed(2)} bps ({(basisMetric?.annualized_basis_pct || 0).toFixed(2)}% p.a.)
                  </span>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-slate-400">8h Funding Rate</span>
                  <span className="text-amber-400 font-bold">
                    {((basisMetric?.funding_rate || 0) * 100).toFixed(4)}% ({(basisMetric?.annualized_funding_pct || 0).toFixed(2)}% p.a.)
                  </span>
                </div>

                <div className="pt-2 mt-1 border-t border-slate-800 flex items-center justify-between font-bold">
                  <span className="text-slate-300">Net Carry APR</span>
                  <span className="text-emerald-400 text-sm">
                    {(basisMetric?.net_carry_apr_pct || 0).toFixed(2)}% APR
                  </span>
                </div>
              </div>
            </div>

            {/* Risk Invariants & Constitutional Primacy */}
            <div className="p-4 bg-[#0B0E14] border border-[#1e293b] rounded-lg flex flex-col justify-between">
              <div>
                <div className="flex items-center gap-2 pb-2 border-b border-slate-800">
                  <ShieldCheck size={15} className="text-emerald-400" />
                  <span className="text-xs font-bold font-mono uppercase text-white">
                    Hedger Risk Guardrails
                  </span>
                </div>

                <div className="flex flex-col gap-2 mt-3 text-xs font-mono">
                  <div className="flex items-center justify-between">
                    <span className="text-slate-400">Tolerance Band</span>
                    <span className="text-white font-bold">&plusmn;0.05 BTC ($3,250)</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-slate-400">Single-Trade Cap</span>
                    <span className="text-white font-bold">1.5% Portfolio Equity</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-slate-400">Kill Switch Bypass</span>
                    <span className="text-rose-400 font-bold">STRICT ZERO-BYPASS</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-slate-400">Timeout Protocol</span>
                    <span className="text-amber-400 font-bold">Fail-Closed / No Blind Retry</span>
                  </div>
                </div>
              </div>

              <span className="text-[10px] text-slate-500 mt-2">
                Hedger operates strictly as a Risk Governor, not an alpha generation vehicle.
              </span>
            </div>
          </div>

          {/* Active / Proposed Hedge Action Card */}
          {proposedHedge ? (
            <div className="p-4 bg-gradient-to-r from-sky-950/30 to-indigo-950/30 border border-sky-500/40 rounded-lg">
              <div className="flex items-center justify-between pb-2 border-b border-sky-500/20">
                <div className="flex items-center gap-2">
                  <Zap size={15} className="text-sky-400 animate-pulse" />
                  <h3 className="text-xs font-bold font-mono uppercase text-white">
                    Active Hedge Proposal Ready for Authorization
                  </h3>
                </div>
                <span className="text-xs font-mono text-amber-400 font-bold">
                  State: {proposedHedge.state}
                </span>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mt-3 font-mono text-xs">
                <div>
                  <span className="text-slate-400 text-[10px]">Target Instrument</span>
                  <div className="text-white font-bold text-sm">
                    {proposedHedge.target_symbol} ({proposedHedge.target_venue})
                  </div>
                </div>
                <div>
                  <span className="text-slate-400 text-[10px]">Action Required</span>
                  <div className={`font-bold text-sm ${proposedHedge.side === 'BUY' ? 'text-emerald-400' : 'text-rose-400'}`}>
                    {proposedHedge.side} {proposedHedge.hedge_qty.toFixed(4)} {proposedHedge.asset}
                  </div>
                </div>
                <div>
                  <span className="text-slate-400 text-[10px]">Target Notional</span>
                  <div className="text-white font-bold text-sm">
                    ${proposedHedge.notional_usd.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                  </div>
                </div>
                <div>
                  <span className="text-slate-400 text-[10px]">Urgency / Instrument</span>
                  <div className="text-amber-400 font-bold text-sm">
                    {proposedHedge.urgency} ({proposedHedge.instrument_type})
                  </div>
                </div>
                <div className="flex items-center">
                  <button
                    onClick={() => setShowHedgeModal(true)}
                    className="w-full py-2 px-3 bg-sky-500 hover:bg-sky-400 text-white font-bold rounded shadow-md shadow-sky-500/30 transition-all text-center"
                  >
                    Authorize Hedge Order
                  </button>
                </div>
              </div>
            </div>
          ) : (
            <div className="p-4 bg-[#0B0E14] border border-[#1e293b] rounded-lg text-center text-xs font-mono text-slate-400 py-6">
              <CheckCircle2 size={24} className="text-emerald-400 mx-auto mb-2" />
              Net portfolio delta is within constitutional tolerance limits (&plusmn;0.05 BTC). No hedge order required.
            </div>
          )}
        </div>
      )}

      {/* TAB 3: COLLATERAL GOVERNOR MATRIX */}
      {activeTab === 'COLLATERAL_MATRIX' && (
        <div className="flex flex-col gap-3">
          {/* Systemic Collateral Status Banner */}
          <div className={`p-4 rounded-lg border flex items-center justify-between ${
            collateralReport?.systemic_risk_state === 'NORMAL'
              ? 'bg-emerald-950/20 border-emerald-500/30'
              : collateralReport?.systemic_risk_state === 'CAUTION'
              ? 'bg-amber-950/20 border-amber-500/30'
              : 'bg-rose-950/20 border-rose-500/50'
          }`}>
            <div className="flex items-center gap-3">
              <ShieldAlert size={24} className={
                collateralReport?.systemic_risk_state === 'NORMAL' ? 'text-emerald-400' : 'text-amber-400'
              } />
              <div>
                <h3 className="text-sm font-bold font-mono uppercase text-white">
                  Systemic Collateral State: {collateralReport?.systemic_risk_state || 'NORMAL'}
                </h3>
                <p className="text-xs text-slate-400 font-mono mt-0.5">
                  Total System Equity: ${(collateralReport?.total_equity_usd || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })} • Aggregate Margin Ratio: {((collateralReport?.aggregate_margin_ratio || 0) * 100).toFixed(1)}%
                </p>
              </div>
            </div>

            <div className="text-right font-mono text-xs">
              <span className={`px-2.5 py-1 rounded font-bold ${
                collateralReport?.freshness_ok ? 'bg-emerald-500/10 text-emerald-400' : 'bg-rose-500 text-white'
              }`}>
                {collateralReport?.freshness_ok ? 'TELEMETRY FRESH (<30s)' : 'TELEMETRY STALE / FAIL-CLOSED'}
              </span>
            </div>
          </div>

          {/* Venue Speedometers / Cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {collateralReport && Object.entries(collateralReport.venues).map(([venueName, snap]) => {
              const utilPct = snap.margin_utilization_ratio * 100;
              const isCaution = utilPct >= 65.0;
              const isDanger = utilPct >= 80.0 || snap.liquidation_buffer_ratio < 2.5;

              return (
                <div key={venueName} className="p-4 bg-[#0B0E14] border border-[#1e293b] rounded-lg">
                  <div className="flex items-center justify-between pb-2 border-b border-slate-800">
                    <span className="text-sm font-bold font-mono text-white uppercase">{venueName} Margin Desk</span>
                    <span className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold ${
                      snap.risk_state === 'NORMAL'
                        ? 'bg-emerald-500/10 text-emerald-400'
                        : snap.risk_state === 'CAUTION'
                        ? 'bg-amber-500/20 text-amber-300'
                        : 'bg-rose-500 text-white animate-pulse'
                    }`}>
                      {snap.risk_state}
                    </span>
                  </div>

                  {/* Utilization Meter */}
                  <div className="mt-3">
                    <div className="flex items-center justify-between text-xs font-mono">
                      <span className="text-slate-400">Margin Utilization</span>
                      <span className={`font-bold ${isDanger ? 'text-rose-400' : isCaution ? 'text-amber-400' : 'text-emerald-400'}`}>
                        {utilPct.toFixed(1)}%
                      </span>
                    </div>
                    <div className="w-full bg-slate-900 rounded-full h-2 mt-1.5 overflow-hidden">
                      <div
                        style={{ width: `${Math.min(utilPct, 100)}%` }}
                        className={`h-full ${isDanger ? 'bg-rose-500' : isCaution ? 'bg-amber-500' : 'bg-emerald-500'}`}
                      />
                    </div>
                  </div>

                  {/* Liquidation Buffer & Metrics */}
                  <div className="grid grid-cols-2 gap-2 mt-4 text-xs font-mono">
                    <div className="p-2 bg-slate-900/60 rounded border border-slate-800">
                      <span className="text-[10px] text-slate-500">Liquidation Buffer</span>
                      <div className={`text-sm font-bold mt-0.5 ${snap.liquidation_buffer_ratio < 2.5 ? 'text-rose-400' : 'text-slate-200'}`}>
                        {snap.liquidation_buffer_ratio.toFixed(2)}x Maint
                      </div>
                    </div>

                    <div className="p-2 bg-slate-900/60 rounded border border-slate-800">
                      <span className="text-[10px] text-slate-500">Available Balance</span>
                      <div className="text-sm font-bold text-white mt-0.5">
                        ${snap.available_balance_usd.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                      </div>
                    </div>

                    <div className="p-2 bg-slate-900/60 rounded border border-slate-800">
                      <span className="text-[10px] text-slate-500">Total Equity</span>
                      <div className="text-sm font-bold text-white mt-0.5">
                        ${snap.total_equity_usd.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                      </div>
                    </div>

                    <div className="p-2 bg-slate-900/60 rounded border border-slate-800">
                      <span className="text-[10px] text-slate-500">Telemetry Age</span>
                      <div className="text-sm font-bold text-slate-400 mt-0.5">
                        {snap.data_age_seconds.toFixed(1)}s ago
                      </div>
                    </div>
                  </div>

                  <div className="mt-3 pt-2 border-t border-slate-800/80 text-[11px] text-slate-500">
                    Governor rule: Recommendations & risk gating only. Zero automated fund transfer authority.
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* TAB 4: SOR FAILOVER & VPIN RADAR */}
      {activeTab === 'SOR_FAILOVER' && (
        <div className="flex flex-col gap-3">
          {/* VPIN Circuit Breaker Radar */}
          <div className={`p-4 rounded-lg border flex items-center justify-between ${
            sorStatus?.vpin_circuit_breaker.is_paused
              ? 'bg-rose-950/20 border-rose-500/50'
              : 'bg-[#0B0E14] border-[#1e293b]'
          }`}>
            <div className="flex items-center gap-3">
              <Zap size={24} className={sorStatus?.vpin_circuit_breaker.is_paused ? 'text-rose-400 animate-pulse' : 'text-sky-400'} />
              <div>
                <h3 className="text-sm font-bold font-mono uppercase text-white">
                  VPIN Flow Toxicity Circuit Breaker
                </h3>
                <p className="text-xs text-slate-400 font-mono mt-0.5">
                  {sorStatus?.vpin_circuit_breaker.reason || 'Normal liquidity conditions detected. Slicers nominal.'}
                </p>
              </div>
            </div>

            <div className="font-mono text-xs">
              <span className={`px-2.5 py-1 rounded font-bold ${
                sorStatus?.vpin_circuit_breaker.is_paused
                  ? 'bg-rose-500 text-white animate-pulse'
                  : 'bg-emerald-500/10 text-emerald-400'
              }`}>
                {sorStatus?.vpin_circuit_breaker.is_paused ? 'CIRCUIT BREAKER ENGAGED (VPIN >= 0.70)' : 'LIQUIDITY HEALTHY'}
              </span>
            </div>
          </div>

          {/* Venue Degradation & Failover Table */}
          <div className="p-4 bg-[#0B0E14] border border-[#1e293b] rounded-lg">
            <div className="flex items-center justify-between pb-2 border-b border-slate-800">
              <h3 className="text-xs font-bold font-mono uppercase text-white">
                Venue Latency & Degradation Matrix
              </h3>
              <span className="text-[10px] font-mono text-slate-400">
                Auto-failover threshold: ACK &gt; 1,000ms or 3 consecutive failures
              </span>
            </div>

            <div className="overflow-x-auto mt-3">
              <table className="w-full text-left text-xs font-mono">
                <thead>
                  <tr className="border-b border-slate-800 text-slate-400 text-[11px]">
                    <th className="pb-2">Venue</th>
                    <th className="pb-2">Avg ACK Latency</th>
                    <th className="pb-2">Consecutive Failures</th>
                    <th className="pb-2">Degradation Status</th>
                    <th className="pb-2">Active Routing</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/50">
                  {sorStatus && Object.entries(sorStatus.venues).map(([vName, vStat]) => (
                    <tr key={vName} className="hover:bg-slate-900/40 transition-colors">
                      <td className="py-2 text-white font-bold">{vName}</td>
                      <td className="py-2">
                        <span className={`font-bold ${vStat.avg_ack_latency_ms > 1000 ? 'text-rose-400' : 'text-slate-300'}`}>
                          {vStat.avg_ack_latency_ms.toFixed(1)} ms
                        </span>
                      </td>
                      <td className="py-2 text-slate-400">{vStat.consecutive_failures}</td>
                      <td className="py-2">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                          vStat.is_degraded ? 'bg-amber-500/20 text-amber-300' : 'bg-emerald-500/10 text-emerald-400'
                        }`}>
                          {vStat.is_degraded ? 'DEGRADED' : 'OPTIMAL'}
                        </span>
                      </td>
                      <td className="py-2">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                          vStat.is_active ? 'bg-sky-500/10 text-sky-400' : 'bg-slate-800 text-slate-500'
                        }`}>
                          {vStat.is_active ? 'ROUTING ENABLED' : 'ROUTING PAUSED'}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="p-3 bg-slate-900/50 rounded border border-slate-800 text-[11px] text-slate-400 mt-4 leading-relaxed font-mono">
              <span className="text-amber-400 font-bold">Failover Safety Guarantee:</span> If a slice route experiences latency degradation, remaining open quantity is re-verified via position reconciliation before rerouting to secondary venues. Zero duplicate slicing under any race condition.
            </div>
          </div>
        </div>
      )}

      {/* MODAL 1: TWO-PHASE HEDGE EXECUTION */}
      {showHedgeModal && proposedHedge && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
          <div className="bg-[#0B0E14] border border-sky-500/40 rounded-xl max-w-md w-full p-5 shadow-2xl font-mono text-xs">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <div className="flex items-center gap-2">
                <ShieldCheck size={18} className="text-sky-400" />
                <h3 className="text-sm font-bold text-white uppercase">Authorize Delta Hedge</h3>
              </div>
              <button
                onClick={() => setShowHedgeModal(false)}
                className="text-slate-500 hover:text-white"
              >
                <X size={16} />
              </button>
            </div>

            <div className="my-4 space-y-2">
              <p className="text-slate-300">
                You are about to dispatch a delta-neutralizing order through the constitutional risk chain:
              </p>
              <div className="p-3 bg-slate-900 rounded border border-slate-800 space-y-1">
                <div><span className="text-slate-500">Symbol:</span> <span className="text-white font-bold">{proposedHedge.target_symbol} ({proposedHedge.target_venue})</span></div>
                <div><span className="text-slate-500">Action:</span> <span className="text-sky-400 font-bold">{proposedHedge.side} {proposedHedge.hedge_qty.toFixed(4)}</span></div>
                <div><span className="text-slate-500">Notional:</span> <span className="text-white font-bold">${proposedHedge.notional_usd.toFixed(2)}</span></div>
              </div>

              <div className="pt-2">
                <label className="text-[11px] text-slate-400 block mb-1">
                  Type <span className="text-sky-400 font-bold">EXECUTE_AUTHORIZED_HEDGE</span> to confirm:
                </label>
                <input
                  type="text"
                  value={hedgeConfirmationInput}
                  onChange={(e) => setHedgeConfirmationInput(e.target.value)}
                  placeholder="EXECUTE_AUTHORIZED_HEDGE"
                  className="w-full p-2 bg-slate-950 border border-slate-700 rounded text-white font-mono focus:border-sky-500 focus:outline-none"
                />
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-800">
              <button
                onClick={() => setShowHedgeModal(false)}
                className="px-3 py-1.5 rounded bg-slate-800 text-slate-300 hover:bg-slate-700 font-bold"
              >
                Cancel
              </button>
              <button
                onClick={handleExecuteHedge}
                disabled={executingHedge || hedgeConfirmationInput !== 'EXECUTE_AUTHORIZED_HEDGE'}
                className="px-4 py-1.5 rounded bg-sky-500 hover:bg-sky-400 text-white font-bold disabled:opacity-50 transition-all"
              >
                {executingHedge ? 'Validating Risk...' : 'Confirm Authorization'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* MODAL 2: ABORT SLICERS */}
      {showAbortModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
          <div className="bg-[#0B0E14] border border-amber-500/40 rounded-xl max-w-md w-full p-5 shadow-2xl font-mono text-xs">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <div className="flex items-center gap-2">
                <AlertOctagon size={18} className="text-amber-400" />
                <h3 className="text-sm font-bold text-white uppercase">Abort Active Slicers</h3>
              </div>
              <button
                onClick={() => setShowAbortModal(false)}
                className="text-slate-500 hover:text-white"
              >
                <X size={16} />
              </button>
            </div>

            <p className="my-4 text-slate-300 leading-relaxed">
              This will immediately cancel all pending discretionary TWAP/VWAP child slices across all active venues.
              <br /><br />
              <span className="text-emerald-400 font-bold">Safe Guardrail:</span> All existing stop-loss and take-profit brackets will remain strictly active.
            </p>

            <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-800">
              <button
                onClick={() => setShowAbortModal(false)}
                className="px-3 py-1.5 rounded bg-slate-800 text-slate-300 hover:bg-slate-700 font-bold"
              >
                Cancel
              </button>
              <button
                onClick={handleAbortSlicers}
                disabled={abortingSlicers}
                className="px-4 py-1.5 rounded bg-amber-600 hover:bg-amber-500 text-white font-bold disabled:opacity-50 transition-all"
              >
                {abortingSlicers ? 'Aborting...' : 'Halt Slicers Now'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* MODAL 3: EMERGENCY FLATTEN DELTA */}
      {showFlattenModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
          <div className="bg-[#0B0E14] border border-rose-500/40 rounded-xl max-w-md w-full p-5 shadow-2xl font-mono text-xs">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <div className="flex items-center gap-2">
                <Flame size={18} className="text-rose-400" />
                <h3 className="text-sm font-bold text-white uppercase">Emergency Flatten Delta</h3>
              </div>
              <button
                onClick={() => setShowFlattenModal(false)}
                className="text-slate-500 hover:text-white"
              >
                <X size={16} />
              </button>
            </div>

            <div className="my-4 space-y-3">
              <p className="text-slate-300 leading-relaxed">
                This triggers an immediate delta-neutralizing order to drive consolidated net exposure to zero.
                <br /><br />
                <span className="text-amber-400 font-bold">Important Distinction:</span> Unlike Panic Close (which liquidates the entire account portfolio), Delta Flattening only neutralizes directional exposure.
              </p>

              <div>
                <label className="text-[11px] text-slate-400 block mb-1">
                  Type <span className="text-rose-400 font-bold">FLATTEN_DELTA_CONFIRMED</span> to proceed:
                </label>
                <input
                  type="text"
                  value={flattenConfirmationInput}
                  onChange={(e) => setFlattenConfirmationInput(e.target.value)}
                  placeholder="FLATTEN_DELTA_CONFIRMED"
                  className="w-full p-2 bg-slate-950 border border-slate-700 rounded text-white font-mono focus:border-rose-500 focus:outline-none"
                />
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-800">
              <button
                onClick={() => setShowFlattenModal(false)}
                className="px-3 py-1.5 rounded bg-slate-800 text-slate-300 hover:bg-slate-700 font-bold"
              >
                Cancel
              </button>
              <button
                onClick={handleFlattenDelta}
                disabled={flatteningDelta || flattenConfirmationInput !== 'FLATTEN_DELTA_CONFIRMED'}
                className="px-4 py-1.5 rounded bg-rose-600 hover:bg-rose-500 text-white font-bold disabled:opacity-50 transition-all"
              >
                {flatteningDelta ? 'Dispatching...' : 'Dispatch Delta Flatten'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
