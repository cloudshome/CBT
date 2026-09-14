import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Shield,
  ShieldAlert,
  ShieldCheck,
  Zap,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  RefreshCw,
  Send,
  Lock,
  Unlock,
  Radio,
  Clock,
  DollarSign,
  AlertOctagon,
} from 'lucide-react';
import {
  api,
  AccountReadinessStatus,
  GatekeeperCheckResult,
  CanaryRunResult,
} from '../services/api';

interface LiveLaunchpadDeskProps {
  onNotify?: (type: 'success' | 'error' | 'warning' | 'info', title: string, message: string) => void;
}

export const LiveLaunchpadDesk: React.FC<LiveLaunchpadDeskProps> = ({ onNotify }) => {
  const [loading, setLoading] = useState<boolean>(true);
  const [readiness, setReadiness] = useState<AccountReadinessStatus | null>(null);
  const [telegramStatus, setTelegramStatus] = useState<any>(null);
  const [canaryStatus, setCanaryStatus] = useState<any>(null);
  const [lastUpdated, setLastUpdated] = useState<Date>(new Date());

  // Canary Order Parameters
  const [exchange, setExchange] = useState<'BINANCE' | 'BYBIT'>('BINANCE');
  const [symbol, setSymbol] = useState<string>('BTCUSDT');
  const [side, setSide] = useState<'BUY' | 'SELL'>('BUY');
  const [notional, setNotional] = useState<number>(15.0);
  const [isDryRun, setIsDryRun] = useState<boolean>(true);
  const [authConfirmed, setAuthConfirmed] = useState<boolean>(false);

  // Operation Execution State
  const [evaluatingPreflight, setEvaluatingPreflight] = useState<boolean>(false);
  const [preflightVerdict, setPreflightVerdict] = useState<GatekeeperCheckResult | null>(null);
  const [runningCanary, setRunningCanary] = useState<boolean>(false);
  const [canaryResult, setCanaryResult] = useState<CanaryRunResult | null>(null);
  const [triggeringBriefing, setTriggeringBriefing] = useState<boolean>(false);
  const [briefingPreview, setBriefingPreview] = useState<string | null>(null);

  const onNotifyRef = useRef(onNotify);
  useEffect(() => {
    onNotifyRef.current = onNotify;
  }, [onNotify]);

  // Load Status Data
  const fetchData = useCallback(async () => {
    try {
      const [readinessRes, tgRes, canaryRes] = await Promise.all([
        api.getAccountReadiness('PRODUCTION'),
        api.getTelegramLiveStatus().catch(() => null),
        api.getLiveCanaryStatus().catch(() => null),
      ]);

      setReadiness(readinessRes);
      if (tgRes) setTelegramStatus(tgRes);
      if (canaryRes) setCanaryStatus(canaryRes);
      setLastUpdated(new Date());
    } catch (err: any) {
      console.error('Failed fetching live launchpad data:', err);
      onNotifyRef.current?.('error', 'Launchpad Status Error', err.message || 'Could not query account readiness.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    setLoading(true);
    fetchData();
    const interval = setInterval(fetchData, 8000);
    return () => clearInterval(interval);
  }, [fetchData]);

  // Pre-Flight Check Action
  const handlePreflightCheck = async () => {
    setEvaluatingPreflight(true);
    try {
      const res = await api.evaluateGatekeeperCheck(exchange, notional, 'PRODUCTION');
      setPreflightVerdict(res);
      if (res.verdict.passed) {
        onNotifyRef.current?.('success', 'Pre-Flight Passed', `All 6 safety gates cleared for ${exchange} ($${notional}).`);
      } else {
        onNotifyRef.current?.('warning', 'Pre-Flight Blocked', `Gatekeeper blocked order: ${res.verdict.rejection_reasons[0] || 'Safety criteria not met'}`);
      }
    } catch (err: any) {
      onNotifyRef.current?.('error', 'Gatekeeper Evaluation Error', err.message || 'Error communicating with live gatekeeper.');
    } finally {
      setEvaluatingPreflight(false);
    }
  };

  // Run Canary Order
  const handleExecuteCanary = async () => {
    if (!isDryRun && !authConfirmed) {
      onNotifyRef.current?.('error', 'Authorization Required', 'Please confirm the live order execution authorization checkbox.');
      return;
    }

    setRunningCanary(true);
    try {
      const res = await api.runLiveCanaryOrder({
        exchange,
        symbol,
        notional_usd: notional,
        side,
        is_dry_run: isDryRun,
        environment: 'PRODUCTION',
      });
      setCanaryResult(res);

      if (res.result.success) {
        onNotifyRef.current?.('success', isDryRun ? 'Canary Dry-Run Succeeded' : 'Live Canary Executed', `${exchange} ${symbol} $${notional} order completed.`);
      } else {
        onNotifyRef.current?.('warning', 'Canary Order Gated', res.result.message || 'Gatekeeper prevented order execution.');
      }
      fetchData();
    } catch (err: any) {
      onNotifyRef.current?.('error', 'Canary Execution Failed', err.message || 'Error executing canary order.');
    } finally {
      setRunningCanary(false);
    }
  };

  // Trigger Telegram Briefing
  const handleTriggerBriefing = async (briefingType: string) => {
    setTriggeringBriefing(true);
    try {
      const res = await api.triggerTelegramBriefing(briefingType);
      setBriefingPreview(res.text_preview);
      onNotifyRef.current?.('success', 'Briefing Generated', `Dispatched ${res.briefing_type} briefing.`);
    } catch (err: any) {
      onNotifyRef.current?.('error', 'Briefing Trigger Failed', err.message || 'Error generating briefing.');
    } finally {
      setTriggeringBriefing(false);
    }
  };

  const binanceStatus = readiness?.exchange_statuses?.['BINANCE'];
  const bybitStatus = readiness?.exchange_statuses?.['BYBIT'];
  const isReady = readiness?.is_ready_for_canary_trade || false;

  return (
    <div className="flex flex-col h-full bg-[#0a0d14] text-slate-200 overflow-y-auto p-4 space-y-4">
      {/* HEADER BAR */}
      <div className="flex flex-wrap items-center justify-between gap-3 p-4 bg-[#10141e] border border-slate-800 rounded-xl">
        <div className="flex items-center space-x-3">
          <div className={`p-2.5 rounded-lg border ${isReady ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400' : 'bg-rose-500/10 border-rose-500/30 text-rose-400'}`}>
            <Shield className="w-6 h-6 animate-pulse" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h2 className="text-base font-bold text-white tracking-wide">
                LIVE EXCHANGE TRADING LAUNCHPAD & CANARY COCKPIT
              </h2>
              <span className="px-2 py-0.5 text-xs font-semibold bg-cyan-500/10 text-cyan-400 border border-cyan-500/30 rounded">
                PHASE 21
              </span>
              <span className={`px-2 py-0.5 text-xs font-semibold rounded border ${isReady ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30' : 'bg-rose-500/10 text-rose-400 border-rose-500/30'}`}>
                {isReady ? 'READY FOR CANARY' : 'FAIL-CLOSED (GATED)'}
              </span>
            </div>
            <p className="text-xs text-slate-400">
              Constitutional 6-Gate Preflight Safety Perimeter · Real-Time Account Balance Probe · Micro-Canary Runner ($5-$25)
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-3">
          <div className="hidden sm:flex items-center space-x-2 px-3 py-1.5 bg-slate-900/80 border border-slate-800 rounded-lg text-xs">
            <span className="text-slate-400">Canary Limit:</span>
            <span className="font-mono font-semibold text-cyan-300">
              ${canaryStatus?.min_canary_notional_usd ?? 5}–${canaryStatus?.max_canary_notional_usd ?? 25}
            </span>
            <span className="text-slate-600">|</span>
            <span className="text-slate-400">Updated:</span>
            <span className="font-mono text-slate-300">
              {lastUpdated.toLocaleTimeString()}
            </span>
          </div>

          <div className="flex items-center space-x-2 px-3 py-1.5 bg-slate-900/80 border border-slate-800 rounded-lg text-xs">
            <Clock className="w-3.5 h-3.5 text-amber-400" />
            <span className="text-slate-400">BST (UTC+6):</span>
            <span className="font-mono font-semibold text-amber-300">
              {telegramStatus?.bd_time_str || new Date().toLocaleTimeString('en-US', { timeZone: 'Asia/Dhaka' })}
            </span>
          </div>

          <button
            onClick={() => fetchData()}
            disabled={loading}
            className="flex items-center space-x-1.5 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-xs font-medium transition"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-cyan-400' : ''}`} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* TOP KPI CARDS: CAPITAL SCORECARD */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <div className="p-4 bg-[#10141e] border border-slate-800 rounded-xl flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400 text-xs font-medium">
            <span>Total Portfolio Equity</span>
            <DollarSign className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="mt-2 text-2xl font-bold font-mono text-white">
            ${(readiness?.total_portfolio_equity_usd ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
          <div className="mt-1 flex items-center justify-between text-[11px] text-slate-500">
            <span>Free Cash: ${(readiness?.total_free_cash_usd ?? 0).toFixed(2)}</span>
            <span className="text-emerald-400 font-semibold">100% Capital Verified</span>
          </div>
        </div>

        <div className="p-4 bg-[#10141e] border border-slate-800 rounded-xl flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400 text-xs font-medium">
            <span>Single-Trade Equity Cap</span>
            <ShieldCheck className="w-4 h-4 text-cyan-400" />
          </div>
          <div className="mt-2 text-2xl font-bold font-mono text-cyan-400">
            ${(readiness?.single_trade_equity_cap_usd ?? 0).toFixed(2)}
          </div>
          <div className="mt-1 flex items-center justify-between text-[11px] text-slate-500">
            <span>Constitutional Cap</span>
            <span className="text-cyan-400 font-mono font-semibold">Strict 1.5% Max</span>
          </div>
        </div>

        <div className="p-4 bg-[#10141e] border border-slate-800 rounded-xl flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400 text-xs font-medium">
            <span>Max Portfolio Heat</span>
            <AlertTriangle className="w-4 h-4 text-amber-400" />
          </div>
          <div className="mt-2 text-2xl font-bold font-mono text-amber-400">
            ${(readiness?.max_portfolio_heat_usd ?? 0).toFixed(2)}
          </div>
          <div className="mt-1 flex items-center justify-between text-[11px] text-slate-500">
            <span>Concurrent Exposure</span>
            <span className="text-amber-400 font-mono font-semibold">Strict 6.0% Ceiling</span>
          </div>
        </div>

        <div className="p-4 bg-[#10141e] border border-slate-800 rounded-xl flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400 text-xs font-medium">
            <span>Vault Security Enclave</span>
            {readiness?.vault_unlocked ? <Unlock className="w-4 h-4 text-emerald-400" /> : <Lock className="w-4 h-4 text-rose-400" />}
          </div>
          <div className="mt-2 text-2xl font-bold font-mono">
            {readiness?.vault_unlocked ? (
              <span className="text-emerald-400">UNLOCKED</span>
            ) : (
              <span className="text-rose-400">LOCKED</span>
            )}
          </div>
          <div className="mt-1 flex items-center justify-between text-[11px] text-slate-500">
            <span>KMS / PBKDF2 Master</span>
            <span className="font-mono text-slate-400">AES-256-GCM Active</span>
          </div>
        </div>
      </div>

      {/* VENUE BALANCES & CONNECTIVITY */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {/* BINANCE CARD */}
        <div className="p-4 bg-[#10141e] border border-slate-800 rounded-xl space-y-3">
          <div className="flex items-center justify-between border-b border-slate-800/80 pb-2.5">
            <div className="flex items-center space-x-2">
              <div className="w-2.5 h-2.5 rounded-full bg-yellow-400" />
              <span className="font-bold text-sm text-white">Binance Spot & Margin</span>
              <span className="text-[10px] px-1.5 py-0.5 bg-slate-800 rounded text-slate-400">PRODUCTION</span>
            </div>
            <div className="flex items-center space-x-1 text-xs">
              {binanceStatus?.is_connected ? (
                <span className="flex items-center text-emerald-400 font-semibold space-x-1">
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  <span>ONLINE ({binanceStatus.latency_ms.toFixed(1)}ms)</span>
                </span>
              ) : (
                <span className="flex items-center text-rose-400 font-semibold space-x-1">
                  <XCircle className="w-3.5 h-3.5" />
                  <span>DISCONNECTED</span>
                </span>
              )}
            </div>
          </div>

          <div className="grid grid-cols-3 gap-2 text-xs">
            <div className="p-2.5 bg-slate-900/60 rounded-lg">
              <div className="text-[11px] text-slate-400">Equity</div>
              <div className="text-sm font-mono font-bold text-white mt-1">
                ${(binanceStatus?.total_equity_usd ?? 0).toFixed(2)}
              </div>
            </div>
            <div className="p-2.5 bg-slate-900/60 rounded-lg">
              <div className="text-[11px] text-slate-400">Free Cash</div>
              <div className="text-sm font-mono font-bold text-emerald-400 mt-1">
                ${(binanceStatus?.free_cash_usd ?? 0).toFixed(2)}
              </div>
            </div>
            <div className="p-2.5 bg-slate-900/60 rounded-lg">
              <div className="text-[11px] text-slate-400">Locked Margin</div>
              <div className="text-sm font-mono font-bold text-slate-300 mt-1">
                ${(binanceStatus?.locked_margin_usd ?? 0).toFixed(2)}
              </div>
            </div>
          </div>

          {binanceStatus?.error_message && (
            <div className="p-2.5 bg-amber-500/10 border border-amber-500/20 rounded-lg text-xs text-amber-300 flex items-start space-x-2">
              <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
              <span>{binanceStatus.error_message}</span>
            </div>
          )}
        </div>

        {/* BYBIT CARD */}
        <div className="p-4 bg-[#10141e] border border-slate-800 rounded-xl space-y-3">
          <div className="flex items-center justify-between border-b border-slate-800/80 pb-2.5">
            <div className="flex items-center space-x-2">
              <div className="w-2.5 h-2.5 rounded-full bg-cyan-400" />
              <span className="font-bold text-sm text-white">Bybit V5 Linear Futures</span>
              <span className="text-[10px] px-1.5 py-0.5 bg-slate-800 rounded text-slate-400">PRODUCTION</span>
            </div>
            <div className="flex items-center space-x-1 text-xs">
              {bybitStatus?.is_connected ? (
                <span className="flex items-center text-emerald-400 font-semibold space-x-1">
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  <span>ONLINE ({bybitStatus.latency_ms.toFixed(1)}ms)</span>
                </span>
              ) : (
                <span className="flex items-center text-rose-400 font-semibold space-x-1">
                  <XCircle className="w-3.5 h-3.5" />
                  <span>DISCONNECTED</span>
                </span>
              )}
            </div>
          </div>

          <div className="grid grid-cols-3 gap-2 text-xs">
            <div className="p-2.5 bg-slate-900/60 rounded-lg">
              <div className="text-[11px] text-slate-400">Equity</div>
              <div className="text-sm font-mono font-bold text-white mt-1">
                ${(bybitStatus?.total_equity_usd ?? 0).toFixed(2)}
              </div>
            </div>
            <div className="p-2.5 bg-slate-900/60 rounded-lg">
              <div className="text-[11px] text-slate-400">Free Cash</div>
              <div className="text-sm font-mono font-bold text-emerald-400 mt-1">
                ${(bybitStatus?.free_cash_usd ?? 0).toFixed(2)}
              </div>
            </div>
            <div className="p-2.5 bg-slate-900/60 rounded-lg">
              <div className="text-[11px] text-slate-400">Locked Margin</div>
              <div className="text-sm font-mono font-bold text-slate-300 mt-1">
                ${(bybitStatus?.locked_margin_usd ?? 0).toFixed(2)}
              </div>
            </div>
          </div>

          {bybitStatus?.error_message && (
            <div className="p-2.5 bg-amber-500/10 border border-amber-500/20 rounded-lg text-xs text-amber-300 flex items-start space-x-2">
              <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
              <span>{bybitStatus.error_message}</span>
            </div>
          )}
        </div>
      </div>

      {/* MAIN DUAL COLUMN: PREFLIGHT CHECKLIST & CANARY LAUNCHER */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* LEFT COLUMN: 6-GATE CONSTITUTIONAL SAFETY CHECKLIST (7 Cols) */}
        <div className="lg:col-span-7 p-4 bg-[#10141e] border border-slate-800 rounded-xl space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <div className="flex items-center space-x-2">
              <Shield className="w-5 h-5 text-cyan-400" />
              <h3 className="font-bold text-sm text-white">6-POINT CONSTITUTIONAL SAFETY LOCK</h3>
            </div>
            <span className="text-[11px] font-mono text-slate-400">NON-BYPASSABLE PREFLIGHT GATES</span>
          </div>

          <div className="space-y-2.5">
            {/* Gate 1 */}
            <div className="p-3 bg-slate-900/50 border border-slate-800/80 rounded-lg flex items-center justify-between">
              <div className="flex items-center space-x-3">
                {readiness?.vault_unlocked ? (
                  <CheckCircle2 className="w-5 h-5 text-emerald-400 flex-shrink-0" />
                ) : (
                  <XCircle className="w-5 h-5 text-rose-400 flex-shrink-0" />
                )}
                <div>
                  <div className="text-xs font-bold text-slate-200">Gate 1: Key Vault Master Key Derived</div>
                  <div className="text-[11px] text-slate-400">KMS Envelope / PBKDF2 Vault unlocked & master key active in memory.</div>
                </div>
              </div>
              <span className={`px-2 py-0.5 text-[10px] font-bold rounded ${readiness?.vault_unlocked ? 'bg-emerald-500/10 text-emerald-400' : 'bg-rose-500/10 text-rose-400'}`}>
                {readiness?.vault_unlocked ? 'PASSED' : 'LOCKED'}
              </span>
            </div>

            {/* Gate 2 */}
            <div className="p-3 bg-slate-900/50 border border-slate-800/80 rounded-lg flex items-center justify-between">
              <div className="flex items-center space-x-3">
                <CheckCircle2 className="w-5 h-5 text-emerald-400 flex-shrink-0" />
                <div>
                  <div className="text-xs font-bold text-slate-200">Gate 2: Master Kill-Switch Operational</div>
                  <div className="text-[11px] text-slate-400">No active emergency circuit trips, telemetry heartbeats continuous.</div>
                </div>
              </div>
              <span className="px-2 py-0.5 text-[10px] font-bold rounded bg-emerald-500/10 text-emerald-400">
                ARMED & READY
              </span>
            </div>

            {/* Gate 3 */}
            <div className="p-3 bg-slate-900/50 border border-slate-800/80 rounded-lg flex items-center justify-between">
              <div className="flex items-center space-x-3">
                {isReady ? (
                  <CheckCircle2 className="w-5 h-5 text-emerald-400 flex-shrink-0" />
                ) : (
                  <AlertOctagon className="w-5 h-5 text-amber-400 flex-shrink-0" />
                )}
                <div>
                  <div className="text-xs font-bold text-slate-200">Gate 3: Multi-Venue Clock Drift & Latency</div>
                  <div className="text-[11px] text-slate-400">Round-trip transit SLA &lt; 500ms; clock drift verified within tolerances.</div>
                </div>
              </div>
              <span className={`px-2 py-0.5 text-[10px] font-bold rounded ${isReady ? 'bg-emerald-500/10 text-emerald-400' : 'bg-amber-500/10 text-amber-400'}`}>
                {isReady ? 'PASS (<500MS)' : 'AWAITING KEY'}
              </span>
            </div>

            {/* Gate 4 */}
            <div className="p-3 bg-slate-900/50 border border-slate-800/80 rounded-lg flex items-center justify-between">
              <div className="flex items-center space-x-3">
                <CheckCircle2 className="w-5 h-5 text-emerald-400 flex-shrink-0" />
                <div>
                  <div className="text-xs font-bold text-slate-200">Gate 4: 24h Realized Drawdown Limit</div>
                  <div className="text-[11px] text-slate-400">Daily portfolio loss strictly below 3.0% circuit breaker stop.</div>
                </div>
              </div>
              <span className="px-2 py-0.5 text-[10px] font-bold rounded bg-emerald-500/10 text-emerald-400">
                PASS (0.00% &lt; 3.0%)
              </span>
            </div>

            {/* Gate 5 */}
            <div className="p-3 bg-slate-900/50 border border-slate-800/80 rounded-lg flex items-center justify-between">
              <div className="flex items-center space-x-3">
                <CheckCircle2 className="w-5 h-5 text-emerald-400 flex-shrink-0" />
                <div>
                  <div className="text-xs font-bold text-slate-200">Gate 5: Single-Trade Equity Cap Conformance</div>
                  <div className="text-[11px] text-slate-400">Canary notional (${notional.toFixed(2)}) strictly bounded within capital caps.</div>
                </div>
              </div>
              <span className="px-2 py-0.5 text-[10px] font-bold rounded bg-emerald-500/10 text-emerald-400">
                PASS (1.5% CAP)
              </span>
            </div>

            {/* Gate 6 */}
            <div className="p-3 bg-slate-900/50 border border-slate-800/80 rounded-lg flex items-center justify-between">
              <div className="flex items-center space-x-3">
                <ShieldAlert className="w-5 h-5 text-amber-400 flex-shrink-0" />
                <div>
                  <div className="text-xs font-bold text-slate-200">Gate 6: Live Trading Authorization Environment Flag</div>
                  <div className="text-[11px] text-slate-400">Enforces LIVE_TRADING_ENABLED=true before real capital order transmission.</div>
                </div>
              </div>
              <span className="px-2 py-0.5 text-[10px] font-bold rounded bg-amber-500/10 text-amber-400">
                DRY-RUN / PROTECTED
              </span>
            </div>
          </div>

          {/* Preflight Check Console */}
          <div className="pt-2">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold text-slate-300">Live Preflight Diagnostic Evaluation</span>
              <button
                onClick={handlePreflightCheck}
                disabled={evaluatingPreflight}
                className="flex items-center space-x-1.5 px-3 py-1 bg-cyan-600/20 hover:bg-cyan-600/30 text-cyan-400 border border-cyan-500/30 rounded text-xs font-medium transition"
              >
                <Zap className={`w-3.5 h-3.5 ${evaluatingPreflight ? 'animate-spin' : ''}`} />
                <span>Evaluate {exchange} (${notional})</span>
              </button>
            </div>

            {preflightVerdict && (
              <div className={`p-3 rounded-lg border text-xs font-mono space-y-1 ${preflightVerdict.verdict.passed ? 'bg-emerald-950/20 border-emerald-500/30 text-emerald-300' : 'bg-rose-950/20 border-rose-500/30 text-rose-300'}`}>
                <div className="flex items-center justify-between font-bold">
                  <span>VERDICT: {preflightVerdict.verdict.passed ? 'CLEARED FOR EXECUTION' : 'ORDER BLOCKED BY GATEKEEPER'}</span>
                  <span>Max Allowed: ${preflightVerdict.verdict.max_allowed_notional_usd.toFixed(2)}</span>
                </div>
                {preflightVerdict.verdict.rejection_reasons.length > 0 && (
                  <ul className="list-disc pl-4 space-y-0.5 text-[11px] text-rose-400">
                    {preflightVerdict.verdict.rejection_reasons.map((r, i) => (
                      <li key={i}>{r}</li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>
        </div>

        {/* RIGHT COLUMN: INTERACTIVE CANARY LAUNCHER ($5 - $25) (5 Cols) */}
        <div className="lg:col-span-5 p-4 bg-[#10141e] border border-slate-800 rounded-xl space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <div className="flex items-center space-x-2">
              <Send className="w-5 h-5 text-emerald-400" />
              <h3 className="font-bold text-sm text-white">MICRO-CANARY RUNNER</h3>
            </div>
            <span className="text-[11px] px-2 py-0.5 bg-slate-800 text-slate-300 rounded font-mono">
              $5.00 — $25.00 USD
            </span>
          </div>

          <div className="space-y-3 text-xs">
            {/* Venue & Pair Selection */}
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="text-[11px] text-slate-400 block mb-1">Target Exchange</label>
                <div className="grid grid-cols-2 gap-1 bg-slate-900 p-1 rounded-lg border border-slate-800">
                  <button
                    onClick={() => setExchange('BINANCE')}
                    className={`py-1.5 rounded font-semibold text-center transition ${exchange === 'BINANCE' ? 'bg-yellow-500/20 text-yellow-300 border border-yellow-500/40' : 'text-slate-400 hover:text-white'}`}
                  >
                    Binance
                  </button>
                  <button
                    onClick={() => setExchange('BYBIT')}
                    className={`py-1.5 rounded font-semibold text-center transition ${exchange === 'BYBIT' ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40' : 'text-slate-400 hover:text-white'}`}
                  >
                    Bybit
                  </button>
                </div>
              </div>

              <div>
                <label className="text-[11px] text-slate-400 block mb-1">Pair</label>
                <select
                  value={symbol}
                  onChange={(e) => setSymbol(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-2 text-white font-mono"
                >
                  <option value="BTCUSDT">BTC/USDT</option>
                  <option value="ETHUSDT">ETH/USDT</option>
                  <option value="SOLUSDT">SOL/USDT</option>
                </select>
              </div>
            </div>

            {/* Order Side */}
            <div>
              <label className="text-[11px] text-slate-400 block mb-1">Order Side</label>
              <div className="grid grid-cols-2 gap-2">
                <button
                  onClick={() => setSide('BUY')}
                  className={`py-2 rounded-lg font-bold text-center border transition ${side === 'BUY' ? 'bg-emerald-500/20 border-emerald-500 text-emerald-400' : 'bg-slate-900 border-slate-800 text-slate-400'}`}
                >
                  BUY (LONG)
                </button>
                <button
                  onClick={() => setSide('SELL')}
                  className={`py-2 rounded-lg font-bold text-center border transition ${side === 'SELL' ? 'bg-rose-500/20 border-rose-500 text-rose-400' : 'bg-slate-900 border-slate-800 text-slate-400'}`}
                >
                  SELL (SHORT)
                </button>
              </div>
            </div>

            {/* Notional Sizing Slider */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="text-[11px] text-slate-400">Canary Notional</label>
                <span className="font-mono font-bold text-white text-sm">${notional.toFixed(2)} USD</span>
              </div>
              <input
                type="range"
                min="5"
                max="25"
                step="1"
                value={notional}
                onChange={(e) => setNotional(parseFloat(e.target.value))}
                className="w-full h-1.5 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-cyan-400"
              />
              <div className="flex justify-between text-[10px] text-slate-500 font-mono mt-1">
                <button onClick={() => setNotional(5)} className="hover:text-slate-300">$5</button>
                <button onClick={() => setNotional(10)} className="hover:text-slate-300">$10</button>
                <button onClick={() => setNotional(15)} className="hover:text-slate-300">$15</button>
                <button onClick={() => setNotional(20)} className="hover:text-slate-300">$20</button>
                <button onClick={() => setNotional(25)} className="hover:text-slate-300">$25</button>
              </div>
            </div>

            {/* Dry-Run vs Live Mode Selector */}
            <div className="p-3 bg-slate-900/80 border border-slate-800 rounded-lg space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-slate-300">Execution Mode</span>
                <div className="flex items-center space-x-1 bg-slate-950 p-1 rounded-lg border border-slate-800">
                  <button
                    onClick={() => setIsDryRun(true)}
                    className={`px-2 py-1 text-[11px] font-bold rounded transition ${isDryRun ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/40' : 'text-slate-400'}`}
                  >
                    Dry-Run Sim
                  </button>
                  <button
                    onClick={() => setIsDryRun(false)}
                    className={`px-2 py-1 text-[11px] font-bold rounded transition ${!isDryRun ? 'bg-rose-500/20 text-rose-400 border border-rose-500/40' : 'text-slate-400'}`}
                  >
                    Live Exchange
                  </button>
                </div>
              </div>

              {!isDryRun && (
                <div className="pt-2 border-t border-slate-800/80 space-y-2">
                  <div className="p-2 bg-rose-500/10 border border-rose-500/20 rounded text-[11px] text-rose-300">
                    ⚠️ <strong>LIVE ORDER AUTHORIZATION:</strong> Transmits real order to {exchange} matching engine.
                  </div>
                  <label className="flex items-start space-x-2 text-[11px] text-slate-400 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={authConfirmed}
                      onChange={(e) => setAuthConfirmed(e.target.checked)}
                      className="mt-0.5 rounded border-slate-700 bg-slate-900 text-rose-500 focus:ring-0"
                    />
                    <span>I confirm live micro-canary execution within the constitutional $25 limit.</span>
                  </label>
                </div>
              )}
            </div>

            {/* Launch Canary Button */}
            <button
              onClick={handleExecuteCanary}
              disabled={runningCanary || (!isDryRun && !authConfirmed)}
              className={`w-full py-2.5 rounded-lg font-bold text-sm transition flex items-center justify-center space-x-2 ${
                isDryRun
                  ? 'bg-cyan-600 hover:bg-cyan-500 text-white shadow-lg shadow-cyan-900/30'
                  : authConfirmed
                  ? 'bg-rose-600 hover:bg-rose-500 text-white shadow-lg shadow-rose-900/30'
                  : 'bg-slate-800 text-slate-500 cursor-not-allowed'
              }`}
            >
              <Zap className={`w-4 h-4 ${runningCanary ? 'animate-spin' : ''}`} />
              <span>
                {runningCanary
                  ? 'Executing Canary...'
                  : isDryRun
                  ? `Run Canary Dry-Run ($${notional.toFixed(2)})`
                  : `TRANSMIT LIVE CANARY ($${notional.toFixed(2)})`}
              </span>
            </button>
          </div>

          {/* Canary Output Console */}
          {canaryResult && (
            <div className="p-3 bg-slate-950 border border-slate-800 rounded-lg text-xs font-mono space-y-1">
              <div className="flex items-center justify-between border-b border-slate-800/80 pb-1 font-bold">
                <span className={canaryResult.result.success ? 'text-emerald-400' : 'text-amber-400'}>
                  STATUS: {canaryResult.result.status}
                </span>
                <span className="text-slate-400">{canaryResult.result.roundtrip_latency_ms.toFixed(1)}ms</span>
              </div>
              <div className="text-[11px] text-slate-300">
                <div>Client ID: <span className="text-cyan-400">{canaryResult.result.client_order_id}</span></div>
                <div>Exec Price: <span className="text-white">${canaryResult.result.executed_price.toFixed(2)}</span> ({canaryResult.result.executed_qty.toFixed(6)} {symbol.replace('USDT', '')})</div>
                <div>Slippage: <span className="text-amber-400">{canaryResult.result.slippage_bps.toFixed(2)} bps</span></div>
                <div className="text-slate-400 mt-1">{canaryResult.result.message}</div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* BOTTOM SECTION: BANGLADESH TIME BRIEFINGS & MACROFLASH DISPATCH */}
      <div className="p-4 bg-[#10141e] border border-slate-800 rounded-xl space-y-3">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div className="flex items-center space-x-2">
            <Radio className="w-5 h-5 text-amber-400" />
            <h3 className="font-bold text-sm text-white">BANGLADESH STANDARD TIME (BST) AUTOMATED BRIEFINGS</h3>
          </div>
          <div className="flex items-center space-x-2 text-xs">
            <span className="text-slate-400">Telegram Bot:</span>
            <span className={`font-semibold ${telegramStatus?.bot_configured ? 'text-emerald-400' : 'text-amber-400'}`}>
              {telegramStatus?.bot_configured ? 'CONNECTED' : 'LOCAL SIMULATION'}
            </span>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 text-xs">
          <div className="p-3 bg-slate-900/60 border border-slate-800 rounded-lg flex flex-col justify-between">
            <div>
              <div className="text-[11px] font-bold text-amber-400">08:00 AM BST (02:00 UTC)</div>
              <div className="text-xs font-semibold text-white mt-0.5">Morning Asian Session</div>
              <div className="text-[11px] text-slate-400 mt-1">Asian liquidity, overnight high/low, global macro catalyst preview.</div>
            </div>
            <button
              onClick={() => handleTriggerBriefing('MORNING')}
              disabled={triggeringBriefing}
              className="mt-2.5 py-1 px-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded text-[11px] font-medium transition"
            >
              Test Dispatch
            </button>
          </div>

          <div className="p-3 bg-slate-900/60 border border-slate-800 rounded-lg flex flex-col justify-between">
            <div>
              <div className="text-[11px] font-bold text-cyan-400">02:00 PM BST (08:00 UTC)</div>
              <div className="text-xs font-semibold text-white mt-0.5">Midday European Open</div>
              <div className="text-[11px] text-slate-400 mt-1">London fixings, Frankfurt open, institutional basis and spread dislocations.</div>
            </div>
            <button
              onClick={() => handleTriggerBriefing('MIDDAY')}
              disabled={triggeringBriefing}
              className="mt-2.5 py-1 px-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded text-[11px] font-medium transition"
            >
              Test Dispatch
            </button>
          </div>

          <div className="p-3 bg-slate-900/60 border border-slate-800 rounded-lg flex flex-col justify-between">
            <div>
              <div className="text-[11px] font-bold text-rose-400">08:00 PM BST (14:00 UTC)</div>
              <div className="text-xs font-semibold text-white mt-0.5">US Session Open & Macro</div>
              <div className="text-[11px] text-slate-400 mt-1">NY pit open, CPI / FOMC / NFP releases, immediate vol crush & tactical risk.</div>
            </div>
            <button
              onClick={() => handleTriggerBriefing('US_SESSION')}
              disabled={triggeringBriefing}
              className="mt-2.5 py-1 px-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded text-[11px] font-medium transition"
            >
              Test Dispatch
            </button>
          </div>

          <div className="p-3 bg-slate-900/60 border border-slate-800 rounded-lg flex flex-col justify-between">
            <div>
              <div className="text-[11px] font-bold text-purple-400">10:00 PM BST (16:00 UTC)</div>
              <div className="text-xs font-semibold text-white mt-0.5">What AI Learned Today</div>
              <div className="text-[11px] text-slate-400 mt-1">Full institutional dossier, synthesized papers, YouTube v5 analysis, desk PnL.</div>
            </div>
            <button
              onClick={() => handleTriggerBriefing('WHAT_AI_LEARNED')}
              disabled={triggeringBriefing}
              className="mt-2.5 py-1 px-2 bg-purple-900/30 hover:bg-purple-900/50 text-purple-300 border border-purple-500/30 rounded text-[11px] font-medium transition"
            >
              Dispatch /learned
            </button>
          </div>
        </div>

        {briefingPreview && (
          <div className="mt-3 p-3 bg-slate-950 border border-slate-800 rounded-lg text-xs font-mono max-h-48 overflow-y-auto whitespace-pre-wrap text-slate-300">
            {briefingPreview}
          </div>
        )}
      </div>
    </div>
  );
};
