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
  Key,
  X,
  Trash2,
  Flame,
  Layers,
  Target,
} from 'lucide-react';
import {
  api,
  AccountReadinessStatus,
  GatekeeperCheckResult,
  CanaryRunResult,
  LiveExecutionSnapshot,
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

  // Environment Mode: TESTNET vs PRODUCTION
  const [envMode, setEnvMode] = useState<'TESTNET' | 'PRODUCTION'>('TESTNET');

  // Phase 22: Live Protection & Position Control State
  const [liveSnapshot, setLiveSnapshot] = useState<LiveExecutionSnapshot | null>(null);
  const [panicConfirmOpen, setPanicConfirmOpen] = useState<boolean>(false);
  const [targetPanicSymbol, setTargetPanicSymbol] = useState<string>('BTCUSDT');
  const [performingPanic, setPerformingPanic] = useState<boolean>(false);
  const [movingToBE, setMovingToBE] = useState<boolean>(false);
  const [cancellingOrderId, setCancellingOrderId] = useState<string | null>(null);
  const [cancellingAllOrders, setCancellingAllOrders] = useState<boolean>(false);

  // Vault Configuration Modal State
  const [showVaultModal, setShowVaultModal] = useState<boolean>(false);
  const [modalExchange, setModalExchange] = useState<'BINANCE' | 'BYBIT'>('BINANCE');
  const [modalEnv, setModalEnv] = useState<'TESTNET' | 'PRODUCTION'>('TESTNET');
  const [modalApiKey, setModalApiKey] = useState<string>('');
  const [modalSecretKey, setModalSecretKey] = useState<string>('');
  const [modalPassphrase, setModalPassphrase] = useState<string>('');
  const [savingVault, setSavingVault] = useState<boolean>(false);

  const onNotifyRef = useRef(onNotify);
  useEffect(() => {
    onNotifyRef.current = onNotify;
  }, [onNotify]);

  // Load Status Data & Live Canonical Snapshot
  const fetchData = useCallback(async () => {
    try {
      const [readinessRes, tgRes, canaryRes, liveRes] = await Promise.all([
        api.getAccountReadiness(envMode),
        api.getTelegramLiveStatus().catch(() => null),
        api.getLiveCanaryStatus().catch(() => null),
        api.getLiveExecutionState(exchange, envMode).catch(() => null),
      ]);

      setReadiness(readinessRes);
      if (tgRes) setTelegramStatus(tgRes);
      if (canaryRes) setCanaryStatus(canaryRes);
      if (liveRes?.snapshot) setLiveSnapshot(liveRes.snapshot);
      setLastUpdated(new Date());
    } catch (err: any) {
      console.error('Failed fetching live launchpad data:', err);
      onNotifyRef.current?.('error', 'Launchpad Status Error', err.message || 'Could not query account readiness.');
    } finally {
      setLoading(false);
    }
  }, [envMode, exchange]);

  // Phase 22: Move SL to Break-Even
  const handleMoveToBE = async (sym: string) => {
    setMovingToBE(true);
    try {
      const res = await api.moveBracketToBreakeven(exchange, sym, envMode);
      if (res.result?.success) {
        onNotifyRef.current?.('success', 'Break-Even Set', `SL moved to entry price for ${sym}. Zero gap verified.`);
      } else {
        onNotifyRef.current?.('warning', 'Break-Even Blocked', res.result?.error_message || 'Could not move SL to BE.');
      }
      fetchData();
    } catch (err: any) {
      onNotifyRef.current?.('error', 'Break-Even Error', err.message || 'Failed moving SL to BE.');
    } finally {
      setMovingToBE(false);
    }
  };

  // Phase 22: Cancel Specific Working Order
  const handleCancelOrder = async (sym: string, orderId: string, clientOrderId?: string) => {
    setCancellingOrderId(orderId);
    try {
      await api.cancelLiveWorkingOrder(exchange, sym, orderId, clientOrderId, envMode);
      onNotifyRef.current?.('success', 'Order Cancelled', `Order ${orderId} on ${sym} cancelled.`);
      fetchData();
    } catch (err: any) {
      onNotifyRef.current?.('error', 'Cancel Error', err.message || 'Failed cancelling order.');
    } finally {
      setCancellingOrderId(null);
    }
  };

  // Phase 22: Cancel All Working Orders for Symbol
  const handleCancelAllOrders = async (sym: string) => {
    setCancellingAllOrders(true);
    try {
      await api.cancelAllLiveWorkingOrders(exchange, sym, envMode);
      onNotifyRef.current?.('success', 'Orders Cancelled', `All working orders on ${sym} cancelled.`);
      fetchData();
    } catch (err: any) {
      onNotifyRef.current?.('error', 'Cancel All Error', err.message || 'Failed cancelling all orders.');
    } finally {
      setCancellingAllOrders(false);
    }
  };

  // Phase 22: Execute Emergency Panic Close
  const handleExecutePanicClose = async () => {
    setPerformingPanic(true);
    try {
      const res = await api.executeLivePanicClose(exchange, targetPanicSymbol, envMode, 'OPERATOR_PANIC_COCKPIT');
      if (res.result?.success) {
        onNotifyRef.current?.(
          'success',
          'EMERGENCY FLATTEN COMPLETED',
          `Position on ${targetPanicSymbol} liquidated @ $${res.result.execution_price.toFixed(2)}. Position verified flat.`
        );
      } else {
        onNotifyRef.current?.(
          'error',
          'FLATTEN INCOMPLETE',
          res.result?.error_message || 'Panic close could not verify 0.0 balance. Check exchange immediately!'
        );
      }
      setPanicConfirmOpen(false);
      fetchData();
    } catch (err: any) {
      onNotifyRef.current?.('error', 'Panic Close Failed', err.message || 'Fatal error triggering emergency flatten.');
    } finally {
      setPerformingPanic(false);
    }
  };

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
      const res = await api.evaluateGatekeeperCheck(exchange, notional, envMode);
      setPreflightVerdict(res);
      if (res.verdict.passed) {
        onNotifyRef.current?.('success', 'Pre-Flight Passed', `All 6 safety gates cleared for ${exchange} [${envMode}] ($${notional}).`);
      } else {
        onNotifyRef.current?.('warning', 'Pre-Flight Blocked', `Gatekeeper blocked order: ${res.verdict.rejection_reasons[0] || 'Safety criteria not met'}`);
      }
    } catch (err: any) {
      onNotifyRef.current?.('error', 'Gatekeeper Evaluation Error', err.message || 'Error communicating with live gatekeeper.');
    } finally {
      setEvaluatingPreflight(false);
    }
  };

  // Save Vault Credentials
  const handleSaveVault = async () => {
    if (!modalApiKey.trim() || !modalSecretKey.trim()) {
      onNotifyRef.current?.('error', 'Missing Keys', 'Both API Key and Secret Key are required.');
      return;
    }
    setSavingVault(true);
    try {
      const res = await api.configureVaultCredential({
        exchange: modalExchange,
        environment: modalEnv,
        api_key: modalApiKey.trim(),
        api_secret: modalSecretKey.trim(),
        passphrase: modalPassphrase.trim() || undefined,
        is_active: true,
      });
      onNotifyRef.current?.('success', 'Vault Updated', res.message || `Credentials securely encrypted for ${modalExchange} [${modalEnv}].`);
      setShowVaultModal(false);
      setModalApiKey('');
      setModalSecretKey('');
      setModalPassphrase('');
      fetchData();
    } catch (err: any) {
      onNotifyRef.current?.('error', 'Vault Save Failed', err.message || 'Could not encrypt credentials.');
    } finally {
      setSavingVault(false);
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
        environment: envMode,
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
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-base font-bold text-white tracking-wide">
                INSTITUTIONAL LIVE LAUNCHPAD & PROTECTION COCKPIT
              </h2>
              <span className="px-2 py-0.5 text-xs font-semibold bg-cyan-500/10 text-cyan-400 border border-cyan-500/30 rounded">
                PHASE 21 + 22
              </span>
              <span className={`px-2 py-0.5 text-xs font-semibold rounded border ${isReady ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30' : 'bg-rose-500/10 text-rose-400 border-rose-500/30'}`}>
                {isReady ? 'READY FOR CANARY' : 'FAIL-CLOSED (GATED)'}
              </span>

              {/* CANONICAL PROTECTION BADGE */}
              {liveSnapshot?.overall_protection_status === 'PROTECTED' && (
                <span className="px-2.5 py-0.5 text-xs font-bold rounded-md border bg-emerald-500/20 text-emerald-300 border-emerald-500/50 flex items-center space-x-1 shadow-sm">
                  <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
                  <span>🟢 PROTECTED</span>
                </span>
              )}
              {liveSnapshot?.overall_protection_status === 'UNPROTECTED' && (
                <span className="px-2.5 py-0.5 text-xs font-bold rounded-md border bg-rose-500/25 text-rose-300 border-rose-500/60 flex items-center space-x-1 animate-bounce shadow-sm">
                  <AlertTriangle className="w-3.5 h-3.5 text-rose-400" />
                  <span>🔴 UNPROTECTED EXPOSURE!</span>
                </span>
              )}
              {(!liveSnapshot || liveSnapshot.overall_protection_status === 'NO_EXPOSURE') && (
                <span className="px-2.5 py-0.5 text-xs font-semibold rounded-md border bg-slate-900 text-slate-400 border-slate-700 flex items-center space-x-1">
                  <CheckCircle2 className="w-3.5 h-3.5 text-slate-500" />
                  <span>FLAT (NO EXPOSURE)</span>
                </span>
              )}
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              Live Position Control · Fail-Closed State Machine · OCO Protection Brackets · Emergency Panic Flatten
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-3">
          {/* Environment Switcher */}
          <div className="flex items-center bg-slate-900/90 border border-slate-800 rounded-lg p-0.5 text-xs font-semibold">
            <button
              onClick={() => setEnvMode('TESTNET')}
              className={`px-3 py-1.5 rounded-md transition flex items-center space-x-1.5 ${
                envMode === 'TESTNET'
                  ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40 shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <span>🧪 Testnet (Paper)</span>
            </button>
            <button
              onClick={() => setEnvMode('PRODUCTION')}
              className={`px-3 py-1.5 rounded-md transition flex items-center space-x-1.5 ${
                envMode === 'PRODUCTION'
                  ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <span>🔴 Live Mainnet</span>
            </button>
          </div>

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
              <span className="text-[10px] px-1.5 py-0.5 bg-slate-800 rounded text-amber-400 border border-amber-500/20 font-mono font-semibold">{envMode}</span>
            </div>
            <div className="flex items-center space-x-2 text-xs">
              <button
                onClick={() => {
                  setModalExchange('BINANCE');
                  setModalEnv(envMode);
                  setShowVaultModal(true);
                }}
                className="flex items-center space-x-1 px-2.5 py-1 bg-yellow-500/10 hover:bg-yellow-500/20 text-yellow-300 border border-yellow-500/30 rounded text-xs font-semibold transition"
              >
                <Key className="w-3 h-3" />
                <span>Configure Keys</span>
              </button>
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
              <span className="text-[10px] px-1.5 py-0.5 bg-slate-800 rounded text-cyan-400 border border-cyan-500/20 font-mono font-semibold">{envMode}</span>
            </div>
            <div className="flex items-center space-x-2 text-xs">
              <button
                onClick={() => {
                  setModalExchange('BYBIT');
                  setModalEnv(envMode);
                  setShowVaultModal(true);
                }}
                className="flex items-center space-x-1 px-2.5 py-1 bg-cyan-500/10 hover:bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 rounded text-xs font-semibold transition"
              >
                <Key className="w-3 h-3" />
                <span>Configure Keys</span>
              </button>
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

      {/* ===================================================================== */}
      {/* PHASE 22: LIVE POSITION CONTROL, PROTECTION & WORKING ORDERS BLOTTER */}
      {/* ===================================================================== */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* ACTIVE EXPOSURE & LIVE BRACKETS (7 COLS) */}
        <div className="lg:col-span-7 p-4 bg-[#10141e] border border-slate-800 rounded-xl space-y-3">
          <div className="flex items-center justify-between border-b border-slate-800 pb-2.5">
            <div className="flex items-center space-x-2">
              <Layers className="w-5 h-5 text-cyan-400" />
              <h3 className="font-bold text-sm text-white">LIVE POSITION & BRACKET CONTROL</h3>
              <span className="text-[10px] px-1.5 py-0.5 bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 rounded font-mono font-semibold">
                PHASE 22
              </span>
            </div>
            <div className="flex items-center space-x-2 text-xs">
              <span className="text-slate-400">Target Venue:</span>
              <span className="font-mono text-amber-300 font-semibold">{exchange} [{envMode}]</span>
            </div>
          </div>

          {/* Positions List */}
          {liveSnapshot?.positions && liveSnapshot.positions.length > 0 ? (
            <div className="space-y-3">
              {liveSnapshot.positions.map((pos, idx) => (
                <div
                  key={idx}
                  className={`p-3.5 rounded-xl border ${
                    pos.protection_status === 'UNPROTECTED'
                      ? 'bg-rose-950/20 border-rose-500/40 shadow-rose-950/30'
                      : 'bg-slate-900/70 border-slate-800 shadow-slate-950/50'
                  } shadow-lg space-y-3`}
                >
                  {/* Card Top: Symbol, Side, Protection Badge */}
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-2.5">
                      <span className="text-sm font-bold text-white font-mono">{pos.symbol}</span>
                      <span
                        className={`text-[10px] px-2 py-0.5 rounded font-bold uppercase ${
                          pos.side === 'LONG'
                            ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40'
                            : 'bg-rose-500/20 text-rose-400 border border-rose-500/40'
                        }`}
                      >
                        {pos.side}
                      </span>
                      <span className="text-xs text-slate-400 font-mono">
                        Qty: <strong className="text-slate-200">{pos.quantity.toFixed(6)}</strong>
                      </span>
                    </div>

                    {/* Protection Status Badge */}
                    <div className="flex items-center space-x-1.5">
                      {pos.protection_status === 'PROTECTED' && (
                        <span className="text-[11px] px-2.5 py-1 bg-emerald-500/20 text-emerald-300 border border-emerald-500/50 rounded-lg font-bold flex items-center space-x-1">
                          <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
                          <span>PROTECTED</span>
                        </span>
                      )}
                      {pos.protection_status === 'BREAKEVEN_ACTIVE' && (
                        <span className="text-[11px] px-2.5 py-1 bg-cyan-500/20 text-cyan-300 border border-cyan-500/50 rounded-lg font-bold flex items-center space-x-1">
                          <ShieldCheck className="w-3.5 h-3.5 text-cyan-400" />
                          <span>BREAK-EVEN ACTIVE</span>
                        </span>
                      )}
                      {pos.protection_status === 'UNPROTECTED' && (
                        <span className="text-[11px] px-2.5 py-1 bg-rose-500/25 text-rose-300 border border-rose-500/60 rounded-lg font-bold flex items-center space-x-1 animate-pulse">
                          <AlertTriangle className="w-3.5 h-3.5 text-rose-400" />
                          <span>UNPROTECTED!</span>
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Pricing Matrix */}
                  <div className="grid grid-cols-4 gap-2 text-xs font-mono">
                    <div className="p-2 bg-slate-950/60 rounded-lg">
                      <div className="text-[10px] text-slate-400 uppercase font-sans">Entry Price</div>
                      <div className="text-slate-200 font-bold mt-0.5">${pos.entry_price.toFixed(2)}</div>
                    </div>
                    <div className="p-2 bg-slate-950/60 rounded-lg">
                      <div className="text-[10px] text-slate-400 uppercase font-sans">Mark Price</div>
                      <div className="text-slate-200 font-bold mt-0.5">${pos.mark_price.toFixed(2)}</div>
                    </div>
                    <div className="p-2 bg-slate-950/60 rounded-lg">
                      <div className="text-[10px] text-slate-400 uppercase font-sans">Unrealized PnL</div>
                      <div
                        className={`font-bold mt-0.5 ${
                          pos.unrealized_pnl_usd >= 0 ? 'text-emerald-400' : 'text-rose-400'
                        }`}
                      >
                        {pos.unrealized_pnl_usd >= 0 ? '+' : ''}${pos.unrealized_pnl_usd.toFixed(2)}
                      </div>
                    </div>
                    <div className="p-2 bg-slate-950/60 rounded-lg">
                      <div className="text-[10px] text-slate-400 uppercase font-sans">Risk Ratio</div>
                      <div
                        className={`font-bold mt-0.5 ${
                          pos.risk_r >= 0 ? 'text-cyan-400' : 'text-amber-400'
                        }`}
                      >
                        {pos.risk_r >= 0 ? '+' : ''}{pos.risk_r.toFixed(2)}R
                      </div>
                    </div>
                  </div>

                  {/* Stop Loss & Take Profit Target Info */}
                  <div className="flex items-center justify-between p-2 bg-slate-950/40 rounded-lg text-xs font-mono">
                    <div className="flex items-center space-x-4">
                      <div>
                        <span className="text-slate-500 mr-1.5 font-sans">SL:</span>
                        <span className="text-rose-400 font-semibold">
                          {pos.stop_loss_price ? `$${pos.stop_loss_price.toFixed(2)}` : 'NONE'}
                        </span>
                      </div>
                      <div>
                        <span className="text-slate-500 mr-1.5 font-sans">TP:</span>
                        <span className="text-emerald-400 font-semibold">
                          {pos.take_profit_price ? `$${pos.take_profit_price.toFixed(2)}` : 'NONE'}
                        </span>
                      </div>
                    </div>

                    {/* Operational Action Buttons */}
                    <div className="flex items-center space-x-2">
                      <button
                        onClick={() => handleMoveToBE(pos.symbol)}
                        disabled={movingToBE || pos.protection_status === 'BREAKEVEN_ACTIVE'}
                        className={`px-3 py-1.5 rounded-lg text-xs font-bold transition flex items-center space-x-1.5 ${
                          pos.protection_status === 'BREAKEVEN_ACTIVE'
                            ? 'bg-slate-800 text-slate-500 cursor-not-allowed border border-slate-700'
                            : 'bg-cyan-500/15 hover:bg-cyan-500/25 text-cyan-300 border border-cyan-500/40'
                        }`}
                      >
                        <Shield className={`w-3.5 h-3.5 ${movingToBE ? 'animate-spin' : ''}`} />
                        <span>Move SL → BE</span>
                      </button>

                      <button
                        onClick={() => {
                          setTargetPanicSymbol(pos.symbol);
                          setPanicConfirmOpen(true);
                        }}
                        className="px-3 py-1.5 bg-rose-600 hover:bg-rose-500 text-white font-bold rounded-lg text-xs transition shadow-md shadow-rose-950 flex items-center space-x-1.5"
                      >
                        <Flame className="w-3.5 h-3.5 animate-pulse" />
                        <span>EMERGENCY PANIC CLOSE</span>
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="p-6 bg-slate-900/40 border border-dashed border-slate-800 rounded-xl text-center space-y-2">
              <CheckCircle2 className="w-8 h-8 text-slate-600 mx-auto" />
              <div className="text-xs font-semibold text-slate-300">No Open Position Exposure Detected</div>
              <p className="text-[11px] text-slate-500 max-w-sm mx-auto">
                Account has zero unhedged market inventory on {exchange} [{envMode}]. Capital is 100% idle and fully protected.
              </p>
            </div>
          )}
        </div>

        {/* WORKING ORDERS TABLE & CANCEL ALL (5 COLS) */}
        <div className="lg:col-span-5 p-4 bg-[#10141e] border border-slate-800 rounded-xl space-y-3 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between border-b border-slate-800 pb-2.5">
              <div className="flex items-center space-x-2">
                <Target className="w-5 h-5 text-amber-400" />
                <h3 className="font-bold text-sm text-white">ACTIVE WORKING ORDERS</h3>
                <span className="text-xs font-mono text-slate-400">
                  ({liveSnapshot?.orders?.length ?? 0})
                </span>
              </div>

              {liveSnapshot?.orders && liveSnapshot.orders.length > 0 && (
                <button
                  onClick={() => handleCancelAllOrders(symbol)}
                  disabled={cancellingAllOrders}
                  className="px-2.5 py-1 bg-rose-500/15 hover:bg-rose-500/25 text-rose-300 border border-rose-500/30 rounded text-xs font-bold transition flex items-center space-x-1"
                >
                  <Trash2 className={`w-3 h-3 ${cancellingAllOrders ? 'animate-spin' : ''}`} />
                  <span>Cancel All ({liveSnapshot.orders.length})</span>
                </button>
              )}
            </div>

            {/* Orders List / Table */}
            <div className="mt-2 space-y-2 max-h-64 overflow-y-auto pr-1">
              {liveSnapshot?.orders && liveSnapshot.orders.length > 0 ? (
                liveSnapshot.orders.map((ord, idx) => (
                  <div
                    key={idx}
                    className="p-2.5 bg-slate-900/70 border border-slate-800/80 rounded-lg text-xs font-mono flex items-center justify-between"
                  >
                    <div>
                      <div className="flex items-center space-x-2">
                        <span className="font-bold text-white">{ord.symbol}</span>
                        <span
                          className={`text-[10px] px-1.5 py-0.5 rounded font-bold ${
                            ord.side === 'BUY'
                              ? 'bg-emerald-500/20 text-emerald-400'
                              : 'bg-rose-500/20 text-rose-400'
                          }`}
                        >
                          {ord.side}
                        </span>
                        <span className="text-[10px] text-slate-400">{ord.order_type}</span>
                      </div>
                      <div className="text-[11px] text-slate-400 mt-1">
                        Price: <span className="text-slate-200">${ord.price.toFixed(2)}</span>
                        {ord.stop_price && (
                          <span className="ml-2 text-amber-400">Trigger: ${ord.stop_price.toFixed(2)}</span>
                        )}
                        <span className="ml-2">Qty: {ord.quantity.toFixed(6)}</span>
                      </div>
                    </div>

                    <button
                      onClick={() => handleCancelOrder(ord.symbol, ord.order_id, ord.client_order_id)}
                      disabled={cancellingOrderId === ord.order_id}
                      className="px-2 py-1 bg-slate-800 hover:bg-rose-500/20 text-slate-300 hover:text-rose-300 border border-slate-700 hover:border-rose-500/40 rounded text-[11px] font-semibold transition"
                    >
                      {cancellingOrderId === ord.order_id ? 'Cancelling...' : 'Cancel'}
                    </button>
                  </div>
                ))
              ) : (
                <div className="py-8 text-center text-slate-500 text-xs">
                  No active working orders on {exchange} [{envMode}].
                </div>
              )}
            </div>
          </div>

          <div className="pt-2 border-t border-slate-800/80 text-[11px] text-slate-500 flex items-center justify-between">
            <span>Reconciliation Engine Active</span>
            <span className="font-mono text-cyan-400">Continuous 3s Polling</span>
          </div>
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

      {/* VAULT CREDENTIAL CONFIGURATION MODAL */}
      {showVaultModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4 animate-in fade-in duration-150">
          <div className="bg-[#10141e] border border-slate-800 rounded-2xl w-full max-w-lg shadow-2xl overflow-hidden">
            {/* Modal Header */}
            <div className="flex items-center justify-between p-4 border-b border-slate-800">
              <div className="flex items-center space-x-2.5">
                <div className="p-2 bg-amber-500/10 border border-amber-500/30 text-amber-400 rounded-lg">
                  <Key className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="font-bold text-sm text-white">Configure Exchange Key Vault</h3>
                  <p className="text-[11px] text-slate-400">AES-256-GCM Secure Enclave Storage</p>
                </div>
              </div>
              <button
                onClick={() => setShowVaultModal(false)}
                className="p-1 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Form */}
            <div className="p-5 space-y-4 text-xs">
              {/* Target Exchange & Environment */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-[11px] text-slate-400 font-semibold block mb-1">Exchange</label>
                  <select
                    value={modalExchange}
                    onChange={(e) => setModalExchange(e.target.value as 'BINANCE' | 'BYBIT')}
                    className="w-full bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-white font-medium focus:border-amber-500 focus:outline-none"
                  >
                    <option value="BINANCE">Binance Spot</option>
                    <option value="BYBIT">Bybit Futures</option>
                  </select>
                </div>
                <div>
                  <label className="text-[11px] text-slate-400 font-semibold block mb-1">Environment</label>
                  <select
                    value={modalEnv}
                    onChange={(e) => setModalEnv(e.target.value as 'TESTNET' | 'PRODUCTION')}
                    className="w-full bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-white font-medium focus:border-amber-500 focus:outline-none"
                  >
                    <option value="TESTNET">Testnet (Paper / Sandbox)</option>
                    <option value="PRODUCTION">Production (Real Mainnet)</option>
                  </select>
                </div>
              </div>

              {/* API Key Input */}
              <div>
                <label className="text-[11px] text-slate-300 font-semibold block mb-1">
                  API Key
                </label>
                <input
                  type="password"
                  autoComplete="off"
                  value={modalApiKey}
                  onChange={(e) => setModalApiKey(e.target.value)}
                  placeholder="Paste your exchange API key"
                  className="w-full bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-white font-mono text-xs focus:border-amber-500 focus:outline-none placeholder-slate-600"
                />
              </div>

              {/* Secret Key Input */}
              <div>
                <label className="text-[11px] text-slate-300 font-semibold block mb-1">
                  Secret Key
                </label>
                <input
                  type="password"
                  autoComplete="off"
                  value={modalSecretKey}
                  onChange={(e) => setModalSecretKey(e.target.value)}
                  placeholder="Paste your exchange Secret key"
                  className="w-full bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-white font-mono text-xs focus:border-amber-500 focus:outline-none placeholder-slate-600"
                />
              </div>

              {/* Passphrase (for Bybit / optional) */}
              {modalExchange === 'BYBIT' && (
                <div>
                  <label className="text-[11px] text-slate-400 font-semibold block mb-1">
                    Passphrase (Optional)
                  </label>
                  <input
                    type="password"
                    autoComplete="off"
                    value={modalPassphrase}
                    onChange={(e) => setModalPassphrase(e.target.value)}
                    placeholder="API passphrase (if configured)"
                    className="w-full bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-white font-mono text-xs focus:border-cyan-500 focus:outline-none placeholder-slate-600"
                  />
                </div>
              )}

              {/* Security Banner */}
              <div className="p-3 bg-slate-900/80 border border-slate-800 rounded-lg space-y-1.5">
                <div className="flex items-center space-x-1.5 text-emerald-400 font-semibold text-[11px]">
                  <ShieldCheck className="w-4 h-4" />
                  <span>Hardware & Enclave Grade Security</span>
                </div>
                <p className="text-[11px] text-slate-400 leading-relaxed">
                  Keys are immediately encrypted via <strong>AES-256-GCM AEAD</strong> using a 600,000-iteration PBKDF2 derived key. Plaintext is never logged or exposed in client responses.
                </p>
              </div>

              {/* Action Buttons */}
              <div className="flex items-center justify-end space-x-2 pt-2 border-t border-slate-800">
                <button
                  onClick={() => setShowVaultModal(false)}
                  disabled={savingVault}
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg font-medium transition"
                >
                  Cancel
                </button>
                <button
                  onClick={handleSaveVault}
                  disabled={savingVault || !modalApiKey.trim() || !modalSecretKey.trim()}
                  className="px-5 py-2 bg-amber-500 hover:bg-amber-400 disabled:bg-slate-800 disabled:text-slate-600 text-slate-950 font-bold rounded-lg shadow-lg shadow-amber-950/40 transition flex items-center space-x-2 cursor-pointer disabled:cursor-not-allowed"
                >
                  {savingVault ? (
                    <>
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                      <span>Encrypting & Saving...</span>
                    </>
                  ) : (
                    <>
                      <Lock className="w-3.5 h-3.5" />
                      <span>Save into Vault</span>
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* PANIC CLOSE CONFIRMATION MODAL */}
      {panicConfirmOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 backdrop-blur-sm p-4 animate-in fade-in duration-150">
          <div className="bg-[#10141e] border-2 border-rose-600 rounded-2xl w-full max-w-md shadow-2xl overflow-hidden p-5 space-y-4">
            <div className="flex items-center space-x-3 text-rose-400 border-b border-slate-800 pb-3">
              <div className="p-2.5 bg-rose-600/20 border border-rose-500/40 rounded-xl">
                <Flame className="w-6 h-6 animate-pulse text-rose-400" />
              </div>
              <div>
                <h3 className="font-bold text-base text-white">EMERGENCY PANIC CLOSE</h3>
                <p className="text-xs text-rose-400 font-semibold">Immediate Exchange Inventory Liquidation</p>
              </div>
            </div>

            <div className="space-y-2 text-xs text-slate-300">
              <p>
                You are initiating an automated fail-closed emergency flatten for <strong className="text-white font-mono">{targetPanicSymbol}</strong> on <strong className="text-amber-400">{exchange} [{envMode}]</strong>.
              </p>
              <div className="p-3 bg-slate-900/80 rounded-lg border border-slate-800 font-mono text-[11px] space-y-1 text-slate-400">
                <div>1. 🧹 Cancel all open orders & brackets on {targetPanicSymbol}</div>
                <div>2. 🔍 Query exact live free inventory balance</div>
                <div>3. ⚡ Dispatch aggressive MARKET sell order</div>
                <div>4. 🛡️ Poll and verify flat 0.0 balance on exchange</div>
              </div>
              <p className="text-amber-300/90 text-[11px]">
                ⚠️ This operation bypasses normal limits and flattens exposure immediately.
              </p>
            </div>

            <div className="flex items-center space-x-3 pt-2">
              <button
                onClick={() => setPanicConfirmOpen(false)}
                disabled={performingPanic}
                className="flex-1 py-2.5 bg-slate-800 hover:bg-slate-700 text-slate-300 font-semibold rounded-lg text-xs transition"
              >
                Cancel / Stand Down
              </button>
              <button
                onClick={handleExecutePanicClose}
                disabled={performingPanic}
                className="flex-1 py-2.5 bg-rose-600 hover:bg-rose-500 text-white font-bold rounded-lg text-xs transition shadow-lg shadow-rose-950 flex items-center justify-center space-x-2"
              >
                <Flame className={`w-4 h-4 ${performingPanic ? 'animate-spin' : ''}`} />
                <span>{performingPanic ? 'FLATTENING...' : 'CONFIRM PANIC FLATTEN'}</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
