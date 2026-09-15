import React, { useState, useEffect, useCallback } from 'react';
import {
  Layers,
  ShieldCheck,
  Clock,
  Play,
  RefreshCw,
  Zap,
  ArrowUpRight,
  ArrowDownRight,
  BookOpen,
  Crosshair,
  BarChart3,
  X,
  ShieldAlert,
  Bot,
} from 'lucide-react';
import { PaperDeskOverviewResponse, HalfKellySizingResponse } from '../types';
import { api } from '../services/api';

interface DedicatedPaperTradingDeskProps {
  onClosePosition: (positionId: string) => Promise<void>;
  onDeploySetupToPaper?: (setup: {
    symbol: string;
    side: 'BUY' | 'SELL';
    entryPrice: number;
    sl: number;
    tp: number;
    size?: number;
  }) => Promise<void>;
}

export const DedicatedPaperTradingDesk: React.FC<DedicatedPaperTradingDeskProps> = ({
  onClosePosition,
  onDeploySetupToPaper,
}) => {
  void onDeploySetupToPaper;
  const [data, setData] = useState<PaperDeskOverviewResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [activeTab, setActiveTab] = useState<'ALL' | 'CURRENT' | 'PAST' | 'FUTURE'>('ALL');
  const [closingId, setClosingId] = useState<string | null>(null);
  const [deployingQueueId, setDeployingQueueId] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date>(new Date());

  // Quick custom order modal state
  const [showOrderModal, setShowOrderModal] = useState<boolean>(false);
  const [orderSymbol, setOrderSymbol] = useState<string>('BTC/USDT');
  const [orderSide, setOrderSide] = useState<'BUY' | 'SELL'>('BUY');
  const [orderEntry, setOrderEntry] = useState<string>('77800');
  const [orderSL, setOrderSL] = useState<string>('76800');
  const [orderTP, setOrderTP] = useState<string>('79800');
  const [orderSize, setOrderSize] = useState<string>('1.0');
  const [orderSubmitting, setOrderSubmitting] = useState<boolean>(false);
  const [kellyResult, setKellyResult] = useState<HalfKellySizingResponse | null>(null);
  const [calculatingKelly, setCalculatingKelly] = useState<boolean>(false);
  const [kellyError, setKellyError] = useState<string | null>(null);

  const handleCalculateHalfKelly = async () => {
    const entry = parseFloat(orderEntry);
    const sl = parseFloat(orderSL);
    const tp = parseFloat(orderTP);
    if (!entry || !sl || !tp) {
      setKellyError('Please enter valid Entry, SL, and TP numbers.');
      return;
    }
    setCalculatingKelly(true);
    setKellyError(null);
    try {
      const res = await api.calculateHalfKelly({
        symbol: orderSymbol,
        entryPrice: entry,
        sl: sl,
        tp: tp,
        equity: data?.summary?.virtualEquity || 100000.0,
      });
      setKellyResult(res);
      if (res.hurdle_passed && res.position_size_base > 0) {
        // Auto-suggest the calculated size
        setOrderSize(res.position_size_base.toString());
      }
    } catch (err: any) {
      setKellyError(err?.message || 'Failed to calculate Half-Kelly sizing');
    } finally {
      setCalculatingKelly(false);
    }
  };

  const handleApplyHalfKelly = () => {
    if (kellyResult && kellyResult.position_size_base > 0) {
      setOrderSize(kellyResult.position_size_base.toString());
    }
  };

  const fetchDeskOverview = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.getPaperDeskOverview();
      setData(res);
      setLastUpdated(new Date());
    } catch (err) {
      console.error('Failed to load Paper Desk overview:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDeskOverview();
    const interval = setInterval(fetchDeskOverview, 10000); // 10s auto-refresh
    return () => clearInterval(interval);
  }, [fetchDeskOverview]);

  const handleClose = async (posId: string) => {
    if (closingId) return;
    setClosingId(posId);
    try {
      await onClosePosition(posId);
      await fetchDeskOverview();
    } finally {
      setClosingId(null);
    }
  };

  const handleDeployQueue = async (item: NonNullable<PaperDeskOverviewResponse['futureQueue']>[0]) => {
    setDeployingQueueId(item.queueId);
    try {
      await api.placePaperTrade({
        symbol: item.symbol,
        side: item.direction === 'LONG' ? 'BUY' : 'SELL',
        entryPrice: item.plannedEntry,
        sl: item.stopLoss,
        tp: item.tp1,
        size: 1.0,
      });
      await fetchDeskOverview();
    } catch (err) {
      console.error('Failed to deploy queued setup:', err);
    } finally {
      setDeployingQueueId(null);
    }
  };

  const handleCustomOrderSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setOrderSubmitting(true);
    try {
      await api.placePaperTrade({
        symbol: orderSymbol,
        side: orderSide,
        entryPrice: parseFloat(orderEntry) || 0,
        sl: parseFloat(orderSL) || 0,
        tp: parseFloat(orderTP) || 0,
        size: parseFloat(orderSize) || 1.0,
      });
      setShowOrderModal(false);
      await fetchDeskOverview();
    } catch (err) {
      console.error('Failed to route custom simulated order:', err);
    } finally {
      setOrderSubmitting(false);
    }
  };

  const summary = data?.summary || {
    startingCapital: 10000.0,
    settledCash: 10000.0,
    virtualEquity: 10000.0,
    accountBalance: 10000.0,
    totalRealizedPnl: 0.0,
    totalUnrealizedPnl: 0.0,
    winRatePct: 0.0,
    profitFactor: 0.0,
    openPositionsCount: 0,
    closedPositionsCount: 0,
    activeRiskPct: 0.0,
    maxRiskCapPct: 2.50,
    circuitBreakerStatus: 'NORMAL',
  };

  const currentPositions = data?.current || [];
  const pastHistory = data?.past || [];
  const futureQueue = data?.futureQueue || [];
  const tradingPlans = data?.tradingPlans || [];

  return (
    <div className="flex-1 max-w-[1920px] w-full mx-auto p-4 flex flex-col gap-4 font-sans">
      {/* Top Header & Metrics Banner */}
      <div className="bg-[#090d16] border border-[#1e293b] rounded-xl p-4 shadow-xl flex flex-col gap-4">
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-[#1e293b] pb-3">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-sky-500/10 border border-sky-500/40 flex items-center justify-center text-sky-400 shadow-sm">
              <Layers className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-lg font-mono font-bold text-white tracking-wide">
                  SHADOW PAPER TRADING DESK
                </h1>
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 font-mono border border-emerald-500/30 font-bold flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                  STATE MIND ACTIVE
                </span>
              </div>
              <p className="text-xs text-slate-400 font-mono">
                Three-Horizon Portfolio Radar: Real-Time Practice, Forensic Autopsies &amp; Future Execution Queue
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => setShowOrderModal(true)}
              className="px-3 py-1.5 rounded-lg bg-sky-500 text-white font-mono text-xs font-bold flex items-center gap-1.5 hover:bg-sky-400 transition-all shadow-md"
            >
              <Play className="w-3.5 h-3.5" />
              <span>Simulate New Order</span>
            </button>
            <button
              onClick={fetchDeskOverview}
              disabled={loading}
              className="p-2 rounded-lg bg-[#0d1424] border border-[#1e293b] text-slate-300 hover:text-white hover:border-slate-500 transition-all disabled:opacity-50"
              title="Refresh Desk Telemetry"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin text-sky-400' : ''}`} />
            </button>
            <div className="text-[10px] font-mono text-slate-500 hidden md:block">
              Updated: {lastUpdated.toLocaleTimeString()}
            </div>
          </div>
        </div>

        {/* 6 Key Portfolio KPI Cards */}
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
          {/* Card 1: Virtual Equity Balance */}
          <div className="bg-[#0d1424] border border-[#1e293b] rounded-lg p-3 flex flex-col justify-between">
            <span className="text-[11px] font-mono text-slate-400">VIRTUAL EQUITY</span>
            <div className="text-lg font-mono font-bold text-white mt-1">
              ${(summary.virtualEquity ?? ((summary.settledCash ?? summary.accountBalance) + summary.totalUnrealizedPnl)).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </div>
            <div className="text-[10px] font-mono text-slate-500 mt-1">
              Base: ${(summary.startingCapital ?? 10000).toLocaleString()}
            </div>
          </div>

          {/* Card 2: Unrealized PnL */}
          <div className="bg-[#0d1424] border border-[#1e293b] rounded-lg p-3 flex flex-col justify-between">
            <span className="text-[11px] font-mono text-slate-400">UNREALIZED P&amp;L</span>
            <div className={`text-lg font-mono font-bold mt-1 flex items-center gap-1 ${
              summary.totalUnrealizedPnl >= 0 ? 'text-emerald-400' : 'text-rose-400'
            }`}>
              {summary.totalUnrealizedPnl >= 0 ? <ArrowUpRight size={18} /> : <ArrowDownRight size={18} />}
              {summary.totalUnrealizedPnl >= 0 ? '+' : ''}${summary.totalUnrealizedPnl.toFixed(2)}
            </div>
            <div className="text-[10px] font-mono text-slate-500 mt-1">
              Active across {summary.openPositionsCount} trade(s)
            </div>
          </div>

          {/* Card 3: Realized PnL */}
          <div className="bg-[#0d1424] border border-[#1e293b] rounded-lg p-3 flex flex-col justify-between">
            <span className="text-[11px] font-mono text-slate-400">REALIZED P&amp;L</span>
            <div className={`text-lg font-mono font-bold mt-1 flex items-center gap-1 ${
              summary.totalRealizedPnl >= 0 ? 'text-emerald-400' : 'text-rose-400'
            }`}>
              {summary.totalRealizedPnl >= 0 ? '+' : ''}${summary.totalRealizedPnl.toFixed(2)}
            </div>
            <div className="text-[10px] font-mono text-slate-500 mt-1">
              {summary.closedPositionsCount} closed cycle(s)
            </div>
          </div>

          {/* Card 4: Win Rate & Profit Factor */}
          <div className="bg-[#0d1424] border border-[#1e293b] rounded-lg p-3 flex flex-col justify-between">
            <span className="text-[11px] font-mono text-slate-400">WIN RATE / PF</span>
            <div className="text-lg font-mono font-bold text-sky-400 mt-1">
              {summary.winRatePct}% <span className="text-xs text-slate-400">/ {summary.profitFactor}x</span>
            </div>
            <div className="text-[10px] font-mono text-slate-500 mt-1">
              SMC Qualified Expectancy
            </div>
          </div>

          {/* Card 5: Risk Exposure */}
          <div className="bg-[#0d1424] border border-[#1e293b] rounded-lg p-3 flex flex-col justify-between">
            <span className="text-[11px] font-mono text-slate-400">ACTIVE RISK</span>
            <div className="text-lg font-mono font-bold text-amber-300 mt-1">
              {(summary.activeRiskPct ?? 0).toFixed(2)}%
            </div>
            <div className="text-[10px] font-mono text-slate-500 mt-1">
              Max Cap: {summary.maxRiskCapPct}%
            </div>
          </div>

          {/* Card 6: Circuit Breaker Status */}
          <div className="bg-[#0d1424] border border-[#1e293b] rounded-lg p-3 flex flex-col justify-between">
            <span className="text-[11px] font-mono text-slate-400">CIRCUIT BREAKER</span>
            <div className="text-sm font-mono font-bold text-emerald-400 mt-1 flex items-center gap-1.5">
              <ShieldCheck className="w-4 h-4 text-emerald-400" />
              <span>{summary.circuitBreakerStatus}</span>
            </div>
            <div className="text-[10px] font-mono text-slate-500 mt-1">
              Zero-Bypass Governance
            </div>
          </div>
        </div>
      </div>

      {/* Navigation Sub-Tabs */}
      <div className="flex items-center gap-2 bg-[#090d16] border border-[#1e293b] rounded-xl p-1 text-xs font-mono">
        <button
          onClick={() => setActiveTab('ALL')}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg font-bold transition-all ${
            activeTab === 'ALL'
              ? 'bg-sky-500 text-white shadow-md'
              : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          <BarChart3 className="w-4 h-4" />
          <span>All-in-One Dashboard</span>
        </button>
        <button
          onClick={() => setActiveTab('CURRENT')}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg font-bold transition-all ${
            activeTab === 'CURRENT'
              ? 'bg-sky-500 text-white shadow-md'
              : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
          <span>Current Active Positions ({currentPositions.length})</span>
        </button>
        <button
          onClick={() => setActiveTab('PAST')}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg font-bold transition-all ${
            activeTab === 'PAST'
              ? 'bg-sky-500 text-white shadow-md'
              : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          <Clock className="w-4 h-4" />
          <span>Past Trade History &amp; Autopsies ({pastHistory.length})</span>
        </button>
        <button
          onClick={() => setActiveTab('FUTURE')}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg font-bold transition-all ${
            activeTab === 'FUTURE'
              ? 'bg-sky-500 text-white shadow-md'
              : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          <Crosshair className="w-4 h-4" />
          <span>Future Trade Plans &amp; Setup Queue ({futureQueue.length})</span>
        </button>
      </div>

      {/* ========================================================================= */}
      {/* 1. CURRENT ACTIVE POSITIONS SECTION */}
      {/* ========================================================================= */}
      {(activeTab === 'ALL' || activeTab === 'CURRENT') && (
        <div className="bg-[#090d16] border border-[#1e293b] rounded-xl p-4 shadow-xl flex flex-col gap-3">
          <div className="flex items-center justify-between border-b border-[#1e293b] pb-2.5">
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-ping"></span>
              <h2 className="text-sm font-mono font-bold text-white uppercase tracking-wider">
                CURRENT ACTIVE SHADOW POSITIONS ({currentPositions.length})
              </h2>
            </div>
            <span className="text-xs font-mono text-slate-400">
              Auto-Breakeven at +1.5R | Strict Risk Cap: {summary.maxRiskCapPct}%
            </span>
          </div>

          {/* Portfolio Heat Guard / Risk Gating Banner */}
          {summary.gatingReason && (
            <div className="flex items-start gap-3 p-3 rounded-lg bg-[#141b2d] border border-amber-500/30 text-xs font-mono shadow-md">
              <ShieldAlert className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
              <div className="flex-1">
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <span className="font-bold text-amber-300 tracking-wide flex items-center gap-1.5">
                    PORTFOLIO ALLOCATION & RISK GATING
                  </span>
                  <div className="flex items-center gap-2 text-[11px]">
                    <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
                      Slots: <strong className="text-white">{currentPositions.length}</strong> / {summary.maxOpenPositions ?? 3} Active
                    </span>
                    <span className="px-2 py-0.5 rounded bg-amber-500/10 text-amber-300 border border-amber-500/30 font-bold">
                      {summary.openSlotsRemaining ?? 0} Slot(s) Reserved
                    </span>
                  </div>
                </div>
                <p className="mt-1 text-slate-300 text-[11px] leading-relaxed">
                  {summary.gatingReason}
                </p>
              </div>
            </div>
          )}

          {currentPositions.length === 0 ? (
            <div className="py-12 text-center flex flex-col items-center justify-center gap-2 border border-dashed border-[#1e293b] rounded-lg bg-[#0d1424]/40">
              <Layers className="w-8 h-8 text-slate-600" />
              <div className="text-sm font-mono text-slate-400">No active shadow positions right now.</div>
              <div className="text-xs font-mono text-slate-500">
                Send <code className="text-sky-400">/signal</code> in Telegram or deploy from the Future Queue below.
              </div>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs font-mono">
                <thead className="bg-[#0d1424] text-slate-400 border-b border-[#1e293b]">
                  <tr>
                    <th className="py-2.5 px-3">POSITION &amp; TIME</th>
                    <th className="py-2.5 px-3">ASSET &amp; HORIZON</th>
                    <th className="py-2.5 px-3">SIDE</th>
                    <th className="py-2.5 px-3">SIZE &amp; LEVERAGE</th>
                    <th className="py-2.5 px-3">ENTRY FILL</th>
                    <th className="py-2.5 px-3">CURRENT LIVE</th>
                    <th className="py-2.5 px-3">STOP LOSS</th>
                    <th className="py-2.5 px-3">TAKE PROFIT</th>
                    <th className="py-2.5 px-3">RISK &amp; R:R</th>
                    <th className="py-2.5 px-3 text-right">UNREALIZED P&amp;L</th>
                    <th className="py-2.5 px-3">AUTOMATION</th>
                    <th className="py-2.5 px-3 text-right">ACTION</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#1e293b]">
                  {currentPositions.map((pos) => {
                    const isLong = pos.side === 'BUY';
                    const pnl = pos.pnlUsd;
                    const sign = pnl >= 0 ? '+' : '';
                    const openedTimeStr = pos.openedAt
                      ? new Date(typeof pos.openedAt === 'number' ? pos.openedAt : Number(pos.openedAt)).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
                      : 'Live';
                    return (
                      <React.Fragment key={pos.id}>
                        <tr className="hover:bg-[#0d1424]/60 transition-colors">
                          <td className="py-3 px-3">
                            <div className="text-slate-300 font-bold">#{pos.id.slice(-10)}</div>
                            <div className="text-[10px] text-slate-500 font-mono flex items-center gap-1 mt-0.5">
                              <Clock className="w-3 h-3 text-slate-500" />
                              <span>{openedTimeStr}</span>
                            </div>
                          </td>
                          <td className="py-3 px-3">
                            <div className="flex items-center gap-1.5">
                              <span className="font-bold text-white text-sm">{pos.symbol}</span>
                              {pos.horizon && (
                                <span
                                  className={`px-1.5 py-0.5 rounded text-[9px] font-extrabold border ${
                                    pos.horizon === 'SCALP'
                                      ? 'bg-purple-500/20 text-purple-300 border-purple-500/40'
                                      : pos.horizon === 'DAY'
                                      ? 'bg-sky-500/20 text-sky-300 border-sky-500/40'
                                      : 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
                                  }`}
                                >
                                  {pos.horizon}
                                </span>
                              )}
                            </div>
                            {pos.agentManager && (
                              <div className="text-[10px] text-slate-400 font-mono flex items-center gap-1 mt-0.5">
                                <Bot className="w-3 h-3 text-slate-500" />
                                <span>{pos.agentManager}</span>
                              </div>
                            )}
                          </td>
                          <td className="py-3 px-3">
                            <span
                              className={`px-2 py-0.5 rounded text-[11px] font-bold ${
                                isLong
                                  ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30'
                                  : 'bg-rose-500/10 text-rose-400 border border-rose-500/30'
                              }`}
                            >
                              {isLong ? '🟢 LONG' : '🔴 SHORT'}
                            </span>
                          </td>
                          <td className="py-3 px-3">
                            <div className="text-slate-200 font-bold">{pos.size} contracts</div>
                            {pos.notionalUsd && (
                              <div className="text-[10px] text-slate-400 font-mono">
                                ${pos.notionalUsd.toLocaleString('en-US', { maximumFractionDigits: 0 })} ({pos.effectiveLeverage ?? 1}x lev)
                              </div>
                            )}
                          </td>
                          <td className="py-3 px-3 text-slate-200 font-bold">
                            ${pos.entryPrice.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                          </td>
                          <td className="py-3 px-3 text-white font-bold">
                            ${pos.currentPrice.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                          </td>
                          <td className="py-3 px-3 text-rose-400">
                            ${pos.sl.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                          </td>
                          <td className="py-3 px-3 text-emerald-400">
                            ${pos.tp.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                          </td>
                          <td className="py-3 px-3">
                            {pos.capitalAtRiskUsd !== undefined ? (
                              <div>
                                <span className="text-rose-400 font-bold">-${pos.capitalAtRiskUsd.toFixed(2)}</span>
                                <div className="text-[10px] text-slate-400 font-mono">
                                  {pos.riskOfAccountPct}% eq ({pos.riskRewardRatio})
                                </div>
                              </div>
                            ) : (
                              <span className="text-slate-400 font-mono">-</span>
                            )}
                          </td>
                          <td className="py-3 px-3 text-right font-bold text-sm">
                            <span className={pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
                              {sign}${pnl.toFixed(2)} ({sign}{pos.pnlPct.toFixed(2)}%)
                            </span>
                          </td>
                          <td className="py-3 px-3">
                            {pos.breakevenTriggered ? (
                              <span className="text-[10px] px-2 py-0.5 rounded bg-sky-950 text-sky-300 border border-sky-500/40 font-bold flex items-center gap-1 w-max">
                                <ShieldCheck className="w-3 h-3 text-sky-400" />
                                BREAKEVEN ARMED
                              </span>
                            ) : (
                              <span className="text-[10px] text-slate-400 font-mono">
                                Arming at +1.5R
                              </span>
                            )}
                          </td>
                          <td className="py-3 px-3 text-right">
                            <button
                              onClick={() => handleClose(pos.id)}
                              disabled={closingId === pos.id}
                              className="px-3 py-1 rounded bg-rose-500/20 text-rose-400 border border-rose-500/40 hover:bg-rose-500/30 font-bold text-xs transition-all disabled:opacity-50 shadow-sm"
                            >
                              {closingId === pos.id ? 'CLOSING...' : 'CLOSE TRADE'}
                            </button>
                          </td>
                        </tr>
                        {(pos.thesis || pos.strategyName) && (
                          <tr className="bg-[#0b101d]/80 border-b border-[#1e293b]/70">
                            <td colSpan={12} className="py-2 px-3 text-[11px] font-mono">
                              <div className="flex flex-wrap items-center gap-2 text-slate-300">
                                <span className="px-2 py-0.5 rounded bg-sky-950/80 text-sky-300 border border-sky-800/40 font-bold text-[10px]">
                                  STRATEGY &amp; THESIS
                                </span>
                                <span className="text-slate-200 font-semibold">{pos.strategyName || 'SMC Liquidity Engine'}</span>
                                <span className="text-slate-500">•</span>
                                <span className="text-slate-300 text-[11px] leading-tight">{pos.thesis}</span>
                              </div>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ========================================================================= */}
      {/* 2. FUTURE TRADE PLANS & EXECUTION QUEUE SECTION */}
      {/* ========================================================================= */}
      {(activeTab === 'ALL' || activeTab === 'FUTURE') && (
        <div className="bg-[#090d16] border border-[#1e293b] rounded-xl p-4 shadow-xl flex flex-col gap-4">
          <div className="flex items-center justify-between border-b border-[#1e293b] pb-2.5">
            <div className="flex items-center gap-2">
              <Crosshair className="w-4 h-4 text-sky-400" />
              <h2 className="text-sm font-mono font-bold text-white uppercase tracking-wider">
                FUTURE TRADE PLANS &amp; SETUP EXECUTION QUEUE ({futureQueue.length})
              </h2>
            </div>
            <span className="text-xs font-mono text-slate-400">
              Institutional Entry Conditions &amp; One-Click Shadow Deployment
            </span>
          </div>

          {/* Queue Cards Grid */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {futureQueue.map((item) => {
              const isLong = item.direction === 'LONG';
              const isReady = item.queueStatus === 'READY_TO_DEPLOY';
              return (
                <div
                  key={item.queueId}
                  className="bg-[#0d1424] border border-[#1e293b] hover:border-sky-500/40 transition-all rounded-xl p-4 flex flex-col justify-between gap-3 shadow-md"
                >
                  <div>
                    <div className="flex items-center justify-between gap-2 mb-2">
                      <div className="flex items-center gap-2">
                        <span className="font-mono font-bold text-white text-base">{item.symbol}</span>
                        <span
                          className={`text-[10px] px-1.5 py-0.5 rounded font-bold ${
                            isLong
                              ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30'
                              : 'bg-rose-500/10 text-rose-400 border border-rose-500/30'
                          }`}
                        >
                          {item.direction}
                        </span>
                      </div>
                      <span
                        className={`text-[10px] font-mono px-2 py-0.5 rounded-full font-bold ${
                          isReady
                            ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 animate-pulse'
                            : 'bg-amber-500/10 text-amber-300 border border-amber-500/30'
                        }`}
                      >
                        {item.queueStatus.replace(/_/g, ' ')}
                      </span>
                    </div>

                    <h3 className="text-xs font-mono font-bold text-slate-200">
                      {item.setupName}
                    </h3>
                    <div className="text-[11px] font-mono text-slate-400 mt-1">
                      Archetype: <span className="text-sky-300">{item.archetype}</span>
                    </div>

                    {/* Trigger Condition Box */}
                    <div className="bg-[#070a12] border border-[#1e293b] rounded p-2 mt-2 text-[11px] font-mono">
                      <div className="text-slate-400 font-bold flex items-center gap-1">
                        <Zap className="w-3 h-3 text-amber-400" />
                        TRIGGER CONDITION:
                      </div>
                      <div className="text-amber-200 mt-0.5">{item.triggerCondition}</div>
                    </div>

                    {/* Target Price Metrics */}
                    <div className="grid grid-cols-3 gap-2 mt-3 text-[11px] font-mono bg-[#070a12]/60 p-2 rounded border border-[#1e293b]">
                      <div>
                        <span className="text-slate-500">ENTRY</span>
                        <div className="text-white font-bold">${item.plannedEntry.toLocaleString()}</div>
                      </div>
                      <div>
                        <span className="text-rose-400">SL</span>
                        <div className="text-rose-300 font-bold">${item.stopLoss.toLocaleString()}</div>
                      </div>
                      <div>
                        <span className="text-emerald-400">TP1</span>
                        <div className="text-emerald-300 font-bold">${item.tp1.toLocaleString()}</div>
                      </div>
                    </div>

                    <div className="flex items-center justify-between text-[10px] font-mono text-slate-400 mt-2">
                      <span>R:R: <strong className="text-white">{item.riskReward}</strong></span>
                      <span>Confluence: <strong className="text-sky-300">{item.confluenceScore}/100</strong></span>
                      <span>Half-Kelly: <strong className="text-amber-300">{item.kellyPct}%</strong></span>
                    </div>
                  </div>

                  {/* Deploy Button */}
                  <button
                    onClick={() => handleDeployQueue(item)}
                    disabled={deployingQueueId === item.queueId}
                    className="w-full py-2 rounded-lg bg-sky-500 hover:bg-sky-400 text-white font-mono text-xs font-bold flex items-center justify-center gap-1.5 transition-all shadow-md disabled:opacity-50"
                  >
                    <Play className="w-3.5 h-3.5" />
                    <span>{deployingQueueId === item.queueId ? 'DEPLOYING TO SHADOW...' : 'DEPLOY TO SHADOW DESK'}</span>
                  </button>
                </div>
              );
            })}
          </div>

          {/* Institutional Structural Plans Roadmap */}
          <div className="mt-2 bg-[#0d1424] border border-[#1e293b] rounded-xl p-4 flex flex-col gap-3">
            <div className="flex items-center gap-2 border-b border-[#1e293b] pb-2">
              <BookOpen className="w-4 h-4 text-amber-400" />
              <h3 className="text-xs font-mono font-bold text-white uppercase tracking-wider">
                MULTI-TIMEFRAME STRUCTURAL PLAYBOOKS
              </h3>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {tradingPlans.map((plan, idx) => {
                const isConfluent = plan.macroAlignment === 'CONFLUENT';
                const isDampened = plan.macroAlignment === 'CAUTION_DAMPENED';
                return (
                  <div key={idx} className="bg-[#070a12] border border-[#1e293b] hover:border-sky-500/40 transition-all rounded-lg p-3 text-xs font-mono flex flex-col justify-between gap-2.5 shadow-sm">
                    <div className="flex flex-col gap-2">
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-bold text-white">{plan.symbol}</span>
                          <span className="px-2 py-0.5 rounded bg-sky-950 text-sky-300 border border-sky-500/40 text-[10px] font-bold">
                            {plan.bias}
                          </span>
                        </div>
                        {plan.macroAlignment && (
                          <span className={`px-2 py-0.5 rounded text-[10px] font-bold flex items-center gap-1 ${
                            isConfluent
                              ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                              : isDampened
                              ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                              : 'bg-slate-800 text-slate-300 border border-slate-700'
                          }`}>
                            <Zap className="w-3 h-3" />
                            {plan.macroAlignment} ({plan.riskMultiplier ?? 1.0}x Sizing)
                          </span>
                        )}
                      </div>

                      <div className="text-[11px] text-slate-300">
                        <strong>PDH:</strong> ${plan.pdh?.toLocaleString()} | <strong>PDL:</strong> ${plan.pdl?.toLocaleString()}
                      </div>
                      <div className="text-[11px] text-slate-300">
                        <strong>FVG Zone:</strong> {plan.fvgZone} | <strong>Order Block:</strong> {plan.orderBlock}
                      </div>
                      <div className="text-[11px] text-emerald-300 mt-1">
                        <strong>Primary Path:</strong> {plan.bullPath}
                      </div>
                      <div className="text-[11px] text-rose-300">
                        <strong>Invalidation Path:</strong> {plan.bearPath}
                      </div>
                    </div>

                    {plan.macroDriver && (
                      <div className="pt-2 border-t border-[#1e293b] text-[10px] text-slate-400 italic">
                        <strong className="text-amber-400 not-italic">Macro Catalyst:</strong> {plan.macroDriver}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 3. PAST TRADE HISTORY & FORENSIC AUTOPSIES SECTION */}
      {/* ========================================================================= */}
      {(activeTab === 'ALL' || activeTab === 'PAST') && (
        <div className="bg-[#090d16] border border-[#1e293b] rounded-xl p-4 shadow-xl flex flex-col gap-3">
          <div className="flex items-center justify-between border-b border-[#1e293b] pb-2.5">
            <div className="flex items-center gap-2">
              <Clock className="w-4 h-4 text-slate-400" />
              <h2 className="text-sm font-mono font-bold text-white uppercase tracking-wider">
                PAST TRADE HISTORY &amp; FORENSIC LOSS AUTOPSIES ({pastHistory.length})
              </h2>
            </div>
            <span className="text-xs font-mono text-slate-400">
              11-Taxonomy Forensic Diagnostics &amp; Preventative Rules
            </span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs font-mono">
              <thead className="bg-[#0d1424] text-slate-400 border-b border-[#1e293b]">
                <tr>
                  <th className="py-2.5 px-3">TRADE ID</th>
                  <th className="py-2.5 px-3">ASSET</th>
                  <th className="py-2.5 px-3">SIDE</th>
                  <th className="py-2.5 px-3">ENTRY / EXIT</th>
                  <th className="py-2.5 px-3 text-right">REALIZED P&amp;L</th>
                  <th className="py-2.5 px-3">AUTOPSY CLASSIFICATION</th>
                  <th className="py-2.5 px-3">PRIMARY ROOT CAUSE &amp; RECOMMENDATION</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#1e293b]">
                {pastHistory.map((trade) => {
                  const isProfit = trade.realizedPnlUsd >= 0;
                  const sign = isProfit ? '+' : '';
                  return (
                    <tr key={trade.id} className="hover:bg-[#0d1424]/60 transition-colors">
                      <td className="py-3 px-3 text-slate-400 font-bold">
                        #{trade.id.slice(-10)}
                      </td>
                      <td className="py-3 px-3 font-bold text-white">
                        {trade.symbol}
                      </td>
                      <td className="py-3 px-3">
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                            trade.side === 'BUY'
                              ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30'
                              : 'bg-rose-500/10 text-rose-400 border border-rose-500/30'
                          }`}
                        >
                          {trade.side}
                        </span>
                      </td>
                      <td className="py-3 px-3 text-slate-300">
                        ${trade.entryPrice.toLocaleString()} &rarr; ${trade.exitPrice.toLocaleString()}
                      </td>
                      <td className="py-3 px-3 text-right font-bold text-sm">
                        <span className={isProfit ? 'text-emerald-400' : 'text-rose-400'}>
                          {sign}${trade.realizedPnlUsd.toFixed(2)} ({sign}{trade.realizedPnlPct.toFixed(2)}%)
                        </span>
                      </td>
                      <td className="py-3 px-3">
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-bold border ${
                            isProfit
                              ? 'bg-emerald-950 text-emerald-300 border-emerald-500/40'
                              : 'bg-rose-950 text-rose-300 border-rose-500/40'
                          }`}
                        >
                          {trade.autopsyCategory}
                        </span>
                      </td>
                      <td className="py-3 px-3 max-w-md">
                        <div className="text-slate-200 text-[11px]">{trade.autopsyCause}</div>
                        <div className="text-sky-300 text-[10px] mt-0.5 italic">
                          &rarr; {trade.autopsyRecommendation}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* QUICK CUSTOM ORDER SIMULATION MODAL */}
      {/* ========================================================================= */}
      {showOrderModal && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-[#090d16] border border-[#1e293b] rounded-xl p-5 max-w-md w-full shadow-2xl flex flex-col gap-4 font-mono">
            <div className="flex items-center justify-between border-b border-[#1e293b] pb-2">
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <Play className="w-4 h-4 text-sky-400" />
                ROUTE CUSTOM SIMULATED PRACTICE TRADE
              </h3>
              <button
                onClick={() => setShowOrderModal(false)}
                className="text-slate-400 hover:text-white"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleCustomOrderSubmit} className="flex flex-col gap-3 text-xs">
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setOrderSide('BUY')}
                  className={`flex-1 py-1.5 rounded font-bold transition-all ${
                    orderSide === 'BUY'
                      ? 'bg-emerald-500 text-black'
                      : 'bg-[#0d1424] text-slate-400 border border-[#1e293b]'
                  }`}
                >
                  BUY / LONG
                </button>
                <button
                  type="button"
                  onClick={() => setOrderSide('SELL')}
                  className={`flex-1 py-1.5 rounded font-bold transition-all ${
                    orderSide === 'SELL'
                      ? 'bg-rose-500 text-white'
                      : 'bg-[#0d1424] text-slate-400 border border-[#1e293b]'
                  }`}
                >
                  SELL / SHORT
                </button>
              </div>

              <div>
                <label className="text-slate-400 block mb-1">ASSET SYMBOL</label>
                <input
                  type="text"
                  value={orderSymbol}
                  onChange={(e) => setOrderSymbol(e.target.value.toUpperCase())}
                  className="w-full bg-[#0d1424] border border-[#1e293b] rounded p-2 text-white font-bold"
                  required
                />
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-slate-400 block mb-1">ENTRY PRICE ($)</label>
                  <input
                    type="number"
                    step="any"
                    value={orderEntry}
                    onChange={(e) => setOrderEntry(e.target.value)}
                    className="w-full bg-[#0d1424] border border-[#1e293b] rounded p-2 text-white font-bold"
                    required
                  />
                </div>
                <div>
                  <label className="text-slate-400 block mb-1">POSITION SIZE (UNITS)</label>
                  <input
                    type="number"
                    step="any"
                    value={orderSize}
                    onChange={(e) => setOrderSize(e.target.value)}
                    className="w-full bg-[#0d1424] border border-[#1e293b] rounded p-2 text-white font-bold"
                    required
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-rose-400 block mb-1">STOP LOSS ($)</label>
                  <input
                    type="number"
                    step="any"
                    value={orderSL}
                    onChange={(e) => setOrderSL(e.target.value)}
                    className="w-full bg-[#0d1424] border border-rose-500/40 rounded p-2 text-rose-300 font-bold"
                    required
                  />
                </div>
                <div>
                  <label className="text-emerald-400 block mb-1">TAKE PROFIT ($)</label>
                  <input
                    type="number"
                    step="any"
                    value={orderTP}
                    onChange={(e) => setOrderTP(e.target.value)}
                    className="w-full bg-[#0d1424] border border-emerald-500/40 rounded p-2 text-emerald-300 font-bold"
                    required
                  />
                </div>
              </div>

              {/* Half-Kelly Sizing Panel */}
              <div className="bg-[#0b101d] border border-[#1e293b] rounded-lg p-3 flex flex-col gap-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-sky-400 flex items-center gap-1.5">
                    <Zap className="w-3.5 h-3.5 text-sky-400" />
                    Bayesian Half-Kelly Sizer
                  </span>
                  <button
                    type="button"
                    onClick={handleCalculateHalfKelly}
                    disabled={calculatingKelly}
                    className="px-2.5 py-1 text-[11px] font-bold bg-sky-500/20 hover:bg-sky-500/30 text-sky-300 border border-sky-500/40 rounded transition-all disabled:opacity-50 flex items-center gap-1"
                  >
                    {calculatingKelly ? (
                      <>
                        <RefreshCw className="w-3 h-3 animate-spin" />
                        Calculating...
                      </>
                    ) : (
                      '⚡ Calculate Sizing'
                    )}
                  </button>
                </div>

                {kellyError && (
                  <div className="text-[11px] text-rose-400 bg-rose-500/10 border border-rose-500/30 rounded p-1.5">
                    {kellyError}
                  </div>
                )}

                {kellyResult && (
                  <div className="flex flex-col gap-2 pt-1 border-t border-[#1e293b]">
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] text-slate-400">MATHEMATICAL HURDLE:</span>
                      <span
                        className={`text-[10px] font-bold px-2 py-0.5 rounded ${
                          kellyResult.hurdle_passed
                            ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40'
                            : 'bg-rose-500/20 text-rose-400 border border-rose-500/40'
                        }`}
                      >
                        {kellyResult.hurdle_passed
                          ? `HURDLE PASSED (+${kellyResult.risk_reward_ratio}R)`
                          : 'NEGATIVE EXPECTANCY BLOCKED'}
                      </span>
                    </div>

                    <div className="grid grid-cols-3 gap-2 text-center text-[10px]">
                      <div className="bg-[#070a12] p-1.5 rounded border border-[#1e293b]">
                        <div className="text-slate-500">PAYOFF (R:R)</div>
                        <div className="font-bold text-slate-200">{kellyResult.risk_reward_ratio}R</div>
                      </div>
                      <div className="bg-[#070a12] p-1.5 rounded border border-[#1e293b]">
                        <div className="text-slate-500">HALF-KELLY RISK</div>
                        <div className="font-bold text-sky-400">
                          {(kellyResult.recommended_risk_pct * 100).toFixed(2)}%
                        </div>
                      </div>
                      <div className="bg-[#070a12] p-1.5 rounded border border-[#1e293b]">
                        <div className="text-slate-500">MAX DOLLAR LOSS</div>
                        <div className="font-bold text-amber-400">
                          ${kellyResult.max_dollar_loss.toFixed(2)}
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center justify-between bg-sky-950/20 border border-sky-500/30 rounded p-2 text-xs">
                      <span className="text-sky-300">
                        Recommended: <strong className="text-white">{kellyResult.position_size_base}</strong> units
                      </span>
                      {kellyResult.hurdle_passed && (
                        <button
                          type="button"
                          onClick={handleApplyHalfKelly}
                          className="px-2 py-0.5 text-[10px] font-bold bg-emerald-500/20 text-emerald-300 hover:bg-emerald-500/30 border border-emerald-500/40 rounded transition-all"
                        >
                          Apply to Size
                        </button>
                      )}
                    </div>

                    <div className="text-[10px] text-slate-400 italic">
                      {kellyResult.narrative}
                    </div>
                  </div>
                )}
              </div>

              <div className="bg-[#070a12] border border-sky-500/30 rounded p-2 text-[11px] text-sky-300">
                🛡️ Enforces Half-Kelly risk bounds with auto +1.5R breakeven protection in shadow ledger.
              </div>

              <button
                type="submit"
                disabled={orderSubmitting}
                className="w-full py-2.5 rounded bg-emerald-500 hover:bg-emerald-400 text-black font-bold text-xs transition-all shadow-md disabled:opacity-50 mt-1"
              >
                {orderSubmitting ? 'VALIDATING RISK GATE...' : `ROUTE SIMULATED ${orderSide} ORDER`}
              </button>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
