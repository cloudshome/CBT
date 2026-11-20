import React, { useState, useEffect, useCallback } from 'react';
import {
  ShieldCheck,
  RefreshCw,
  Play,
  TrendingUp,
  TrendingDown,
  AlertTriangle,
  Clock,
  Layers,
  CheckCircle2,
} from 'lucide-react';

interface AssetMetrics {
  symbol: string;
  price: number;
  ema_200: number;
  ema_status: string;
  donchian_h48: number;
  donchian_l24: number;
  atr_14: number;
  stop_loss: number;
  momentum_30d_pct: number;
  vol_20d_ann_pct: number;
}

interface TodayDeskSnapshot {
  timestamp_utc: string;
  data_source: string;
  data_age_hours: number;
  stale_data_warning: boolean;
  regime_label: string;
  action_verdict: string;
  assets: Record<string, AssetMetrics>;
  s1_weights: Record<string, number>;
  s2_weights: Record<string, number>;
  p2_rp_weights: Record<string, number>;
  gross_exposure: number;
  account_equity: number;
  dollar_allocations: Record<string, number>;
  days_to_rebalance: number;
  capital_mode: string;
  real_capital_enabled: boolean;
  details?: string;
  error_reason?: string;
}

interface ShadowPosition {
  units: number;
  avg_entry_price: number;
  last_price: number;
  market_value_usd: number;
  target_weight: number;
}

interface ShadowScorecard {
  days_tracked: number;
  target_forward_days: number;
  equity_usd: number;
  total_return_pct: number;
  bnh_return_pct: number;
  alpha_vs_bnh_pct: number;
  max_drawdown_pct: number;
  live_sharpe: number | null;
  total_fills: number;
  avg_slippage_bps: number;
  avg_spread_bps: number;
  total_fees_usd: number;
  current_regime: string;
  positions: Record<string, ShadowPosition>;
  capital_mode: string;
  real_capital_enabled: boolean;
}

interface ShadowBar {
  bar_ts_utc: number;
  equity_usd: number;
  bnh_equity_usd: number;
  gross_exposure: number;
  regime_label: string;
}

interface ShadowFill {
  bar_ts_utc: number;
  symbol: string;
  side: string;
  units: number;
  signal_close_price: number;
  live_exec_price: number;
  spread_bps: number;
  slippage_bps: number;
  fee_usd: number;
  notional_usd: number;
  reason: string;
}

interface P2ShadowDeskProps {
  onNotify?: (type: 'success' | 'error' | 'info' | 'warning', title: string, message: string) => void;
}

const I18N = {
  en: {
    deskTitle: "P2_RP RISK-PARITY SHADOW DESK",
    subtitle: "24/7 Live Paper Trading Cockpit · Audited S1 (Donchian-48) + S2-Div (7d Dual Momentum)",
    safetyPill: "TIER_0_PAPER · REAL CAPITAL DISABLED",
    dataAge: "Data Age",
    staleWarning: "STALE DATA (>6h)",
    failClosedBanner: "FAIL-CLOSED ACTIVE: Market data stale or missing. New capital allocation locked at 0%.",
    equityInput: "Account Equity ($)",
    refresh: "Refresh",
    runCycle: "Run 4h Shadow Cycle",
    runningCycle: "Running...",
    regime: "Regime",
    verdict: "Verdict",
    kpiEquityTitle: "Shadow Portfolio Equity",
    kpiEquitySub: "Live Alpha vs. Equal-Weight BnH",
    kpiTrackerTitle: "60-Day Forward Proof Tracker",
    kpiTrackerDays: "days forward",
    kpiTrackerMaxDD: "Max Drawdown",
    kpiTrackerSharpe: "Live Sharpe",
    kpiSlippageTitle: "Real Slippage vs. Model",
    kpiSlippageAvg: "Avg Slippage (vs. 20 bps model)",
    kpiSlippageSpread: "Avg Spread",
    kpiSlippageFills: "Total Fills",
    kpiSlippageFees: "Total Fees Paid",
    kpiExposureTitle: "Risk-Parity Allocation",
    kpiExposureGross: "Gross Exposure",
    kpiExposureRebal: "Next Rebalance in",
    kpiExposureCap: "Zero-Leverage Cap (≤ 1.0x)",
    tableTitle: "4-Asset Live Allocation & Tactical Signals",
    colAsset: "Asset",
    colPrice: "Live Price",
    colEma: "EMA-200",
    colStop: "Donchian-48 SL",
    colMom: "30d Momentum",
    colVol: "20d Ann. Vol",
    colTgtWeight: "Target Weight",
    colTgtDollar: "Target ($)",
    colShadowUnits: "Shadow Position",
    allocBarTitle: "Combined Portfolio Allocation Split",
    cash: "CASH",
    chartTitle: "Forward Equity Curve: P2_RP Shadow vs. Equal-Weight BnH",
    chartEmpty: "Collecting 4h forward bars... (Cycles log automatically at every candle close)",
    chartP2Legend: "P2_RP Shadow Equity",
    chartBnhLegend: "Equal-Weight BnH Equity",
    fillsTitle: "Recent Live Execution Fills (Top-of-Book Telemetry)",
    fillsEmpty: "No shadow fills recorded yet. Standing by for next rebalance or breakout trigger.",
    colTime: "Time (UTC)",
    colSide: "Side",
    colSignalClose: "Signal Close",
    colLiveFill: "Live Exec",
    colSlippage: "Slippage",
    colFee: "Fee ($)",
    colReason: "Reason",
  },
  bn: {
    deskTitle: "P2_RP রিস্ক-প্যারিটি শ্যাডো ডেস্ক",
    subtitle: "২৪/৭ লাইভ পেপার ট্রেডিং ককপিট · অডিটেড S1 (Donchian-48) + S2-Div (7d Dual Momentum)",
    safetyPill: "TIER_0_PAPER · কোন আসল মূলধন নয়",
    dataAge: "ডেটার বয়স",
    staleWarning: "পুরনো ডেটা (>৬ ঘণ্টা)",
    failClosedBanner: "ফেল-ক্লোজড সক্রিয়: মার্কেট ডেটা অনুপস্থিত বা পুরনো। নতুন ট্রেড অ্যালটমেন্ট ০% এ লক করা।",
    equityInput: "অ্যাকাউন্ট মূলধন ($)",
    refresh: "রিফ্রেশ",
    runCycle: "৪ ঘণ্টার শ্যাডো সাইকেল চালান",
    runningCycle: "সাইকেল চলছে...",
    regime: "রেজিম",
    verdict: "সিদ্ধান্ত",
    kpiEquityTitle: "শ্যাডো পোর্টফোলিও ইকুইটি",
    kpiEquitySub: "লাইভ আলফা বনাম BnH বেঞ্চমার্ক",
    kpiTrackerTitle: "৬০-দিনের ফরোয়ার্ড ট্র্যাকার",
    kpiTrackerDays: "দিন অতিক্রান্ত",
    kpiTrackerMaxDD: "সর্বোচ্চ ড্রডাউন",
    kpiTrackerSharpe: "লাইভ শার্প",
    kpiSlippageTitle: "রিয়েল স্লিপেজ বনাম মডেল",
    kpiSlippageAvg: "গড় স্লিপেজ (মডেল: ২০ bps)",
    kpiSlippageSpread: "গড় স্প্রেড",
    kpiSlippageFills: "মোট ফিল সংখ্যা",
    kpiSlippageFees: "মোট ফি খরচ",
    kpiExposureTitle: "রিস্ক-প্যারিটি এক্সপোজার",
    kpiExposureGross: "মোট এক্সপোজার",
    kpiExposureRebal: "পরবর্তী রিব্যালান্স বাকি",
    kpiExposureCap: "জিরো-লেভারেজ ক্যাপ (≤ ১.০x)",
    tableTitle: "৪-অ্যাসেট লাইভ অ্যালটমেন্ট ও সিগন্যাল মেট্রিক্স",
    colAsset: "অ্যাসেট",
    colPrice: "লাইভ মূল্য",
    colEma: "EMA-200",
    colStop: "ডনচিয়ান-৪৮ SL",
    colMom: "৩০ দিনের মোমেন্টাম",
    colVol: "২০ দিনের ভোলাটিলিটি",
    colTgtWeight: "টার্গেট অনুপাত",
    colTgtDollar: "টার্গেট ($)",
    colShadowUnits: "শ্যাডো পজিশন",
    allocBarTitle: "পোর্টফোলিও অ্যালটমেন্ট বিভাজন",
    cash: "নগদ (CASH)",
    chartTitle: "ফরোয়ার্ড ইকুইটি কার্ভ: P2_RP শ্যাডো বনাম BnH",
    chartEmpty: "৪ ঘণ্টার ফরোয়ার্ড বার সংগ্রহ করা হচ্ছে... (প্রতি ক্যান্ডেল ক্লোজে স্বয়ংক্রিয়ভাবে লগ হয়)",
    chartP2Legend: "P2_RP শ্যাডো ইকুইটি",
    chartBnhLegend: "Equal-Weight BnH ইকুইটি",
    fillsTitle: "সাম্প্রতিক লাইভ ফিল বিবরণ (টপ-অব-বুক টেলিমেট্রি)",
    fillsEmpty: "এখনো কোন ফিল সম্পন্ন হয়নি। পরবর্তী রিব্যালান্স বা ব্রেকআউট ট্রিগারের অপেক্ষায়।",
    colTime: "সময় (UTC)",
    colSide: "বাই/সেল",
    colSignalClose: "সিগন্যাল মূল্য",
    colLiveFill: "লাইভ ফিল",
    colSlippage: "স্লিপেজ",
    colFee: "ফি ($)",
    colReason: "কারণ",
  },
};

export const P2ShadowDesk: React.FC<P2ShadowDeskProps> = ({ onNotify }) => {
  const [lang, setLang] = useState<'en' | 'bn'>('en');
  const [equityInput, setEquityInput] = useState<number>(10000);
  const [loading, setLoading] = useState<boolean>(true);
  const [runningCycle, setRunningCycle] = useState<boolean>(false);
  const [snapshot, setSnapshot] = useState<TodayDeskSnapshot | null>(null);
  const [scorecard, setScorecard] = useState<ShadowScorecard | null>(null);
  const [bars, setBars] = useState<ShadowBar[]>([]);
  const [fills, setFills] = useState<ShadowFill[]>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const t = I18N[lang];

  const fetchDeskData = useCallback(async () => {
    setLoading(true);
    setErrorMessage(null);
    try {
      // 1. Fetch Today's Desk Snapshot
      const snapRes = await fetch(`/api/desk/today?equity=${equityInput}&source=auto`);
      if (snapRes.ok) {
        const snapData = await snapRes.json();
        setSnapshot(snapData);
      } else {
        setErrorMessage('Failed to load Today desk snapshot');
      }

      // 2. Fetch Shadow Scorecard
      const scoreRes = await fetch('/api/desk/shadow');
      if (scoreRes.ok) {
        const scoreData = await scoreRes.json();
        setScorecard(scoreData);
      }

      // 3. Fetch Shadow History (bars & fills)
      const histRes = await fetch('/api/desk/shadow/history?limit_bars=360&limit_fills=50');
      if (histRes.ok) {
        const histData = await histRes.json();
        setBars(histData.bars || []);
        setFills(histData.fills || []);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Network error loading shadow desk';
      setErrorMessage(msg);
      if (onNotify) {
        onNotify('error', 'Shadow Desk Error', msg);
      }
    } finally {
      setLoading(false);
    }
  }, [equityInput, onNotify]);

  useEffect(() => {
    fetchDeskData();
  }, [fetchDeskData]);

  const handleRunCycle = async () => {
    setRunningCycle(true);
    try {
      const res = await fetch('/api/desk/shadow/run?source=live', { method: 'POST' });
      const data = await res.json();
      if (res.ok) {
        const status = data.cycle?.status || 'COMPLETED';
        const fillCount = data.cycle?.fills || 0;
        const msg = `Shadow Cycle: ${status} (${fillCount} fills executed under TIER_0_PAPER)`;
        if (onNotify) {
          onNotify(status === 'ALREADY_PROCESSED' ? 'info' : 'success', 'Shadow Cycle Executed', msg);
        }
        await fetchDeskData();
      } else {
        throw new Error(data.detail || 'Failed to trigger shadow cycle');
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Shadow cycle execution failed';
      if (onNotify) {
        onNotify('error', 'Cycle Trigger Error', msg);
      }
    } finally {
      setRunningCycle(false);
    }
  };

  // Helper color logic for regime & verdict
  const getRegimeColor = (regime?: string) => {
    switch (regime) {
      case 'RISK_ON':
        return 'bg-emerald-500/20 text-emerald-400 border-emerald-500/40';
      case 'MIXED':
        return 'bg-amber-500/20 text-amber-400 border-amber-500/40';
      case 'BEAR_SHIELD':
      default:
        return 'bg-sky-500/20 text-sky-400 border-sky-500/40';
    }
  };

  const getVerdictColor = (verdict?: string) => {
    switch (verdict) {
      case 'ACT':
        return 'bg-emerald-600 text-white border-emerald-500 font-bold';
      case 'HOLD':
        return 'bg-slate-700 text-slate-200 border-slate-600';
      case 'WAIT_STALE_DATA':
        return 'bg-rose-600 text-white border-rose-500 font-bold';
      case 'BEAR_SHIELD':
      default:
        return 'bg-sky-700 text-white border-sky-600';
    }
  };

  const assetsList = snapshot?.assets ? Object.values(snapshot.assets) : [];
  const p2Weights = snapshot?.p2_rp_weights || {};
  const cashWeight = p2Weights['CASH'] ?? Math.max(0, 1 - (snapshot?.gross_exposure || 0));

  return (
    <div className="max-w-[1920px] w-full mx-auto px-4 py-4 space-y-4 font-mono text-slate-200">
      {/* 1. TOP STATUS BAR (1-Second Clarity) */}
      <div className="bg-[#090d16] border border-[#1e293b] rounded-lg p-3 flex flex-wrap items-center justify-between gap-3 shadow-md">
        <div className="flex flex-wrap items-center gap-3">
          <div>
            <div className="flex items-center gap-2">
              <ShieldCheck className="w-5 h-5 text-emerald-400" />
              <h2 className="text-base font-bold tracking-wide text-white">{t.deskTitle}</h2>
            </div>
            <p className="text-[11px] text-slate-400 hidden sm:block">{t.subtitle}</p>
          </div>

          {/* Regime Badge */}
          <div className={`px-2.5 py-1 rounded text-xs font-bold border ${getRegimeColor(snapshot?.regime_label)}`}>
            {snapshot?.regime_label || 'BEAR_SHIELD'}
          </div>

          {/* Verdict Badge */}
          <div className={`px-2.5 py-1 rounded text-xs border ${getVerdictColor(snapshot?.action_verdict)}`}>
            {snapshot?.action_verdict || 'HOLD'}
          </div>

          {/* Permanent Safety Pill */}
          <div className="px-2.5 py-1 rounded text-xs font-bold bg-[#0d1520] border border-emerald-500/30 text-emerald-400">
            {t.safetyPill}
          </div>

          {/* Data Freshness Badge */}
          <div
            className={`px-2.5 py-1 rounded text-xs border flex items-center gap-1.5 ${
              snapshot?.stale_data_warning || (snapshot?.data_age_hours || 0) > 6.0
                ? 'bg-amber-950/40 border-amber-500/40 text-amber-300'
                : 'bg-slate-900 border-slate-700 text-slate-300'
            }`}
          >
            <Clock className="w-3.5 h-3.5" />
            <span>
              {t.dataAge}: {(snapshot?.data_age_hours || 0).toFixed(1)}h
            </span>
          </div>
        </div>

        {/* Controls */}
        <div className="flex items-center gap-2">
          {/* Language Toggle */}
          <div className="flex items-center bg-[#131b2e] border border-[#23324d] rounded p-0.5 text-xs">
            <button
              onClick={() => setLang('en')}
              className={`px-2 py-0.5 rounded transition-all ${
                lang === 'en' ? 'bg-sky-500 text-white font-bold' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              EN
            </button>
            <button
              onClick={() => setLang('bn')}
              className={`px-2 py-0.5 rounded transition-all ${
                lang === 'bn' ? 'bg-emerald-600 text-white font-bold' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              বাংলা
            </button>
          </div>

          {/* Equity Input */}
          <div className="hidden md:flex items-center gap-1 bg-[#131b2e] border border-[#23324d] rounded px-2 py-1 text-xs">
            <span className="text-slate-400">$</span>
            <input
              type="number"
              value={equityInput}
              onChange={(e) => setEquityInput(Number(e.target.value) || 10000)}
              className="bg-transparent w-20 text-white font-bold focus:outline-none"
              title={t.equityInput}
            />
          </div>

          {/* Refresh Button */}
          <button
            onClick={fetchDeskData}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs bg-slate-800 hover:bg-slate-700 border border-slate-600 text-white transition-all disabled:opacity-50"
            title={t.refresh}
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            <span className="hidden sm:inline">{t.refresh}</span>
          </button>

          {/* Run Cycle Button */}
          <button
            onClick={handleRunCycle}
            disabled={runningCycle}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs bg-emerald-600 hover:bg-emerald-500 border border-emerald-400 text-white font-bold transition-all disabled:opacity-50 shadow-sm"
            title={t.runCycle}
          >
            <Play className={`w-3.5 h-3.5 ${runningCycle ? 'animate-spin' : ''}`} />
            <span>{runningCycle ? t.runningCycle : t.runCycle}</span>
          </button>
        </div>
      </div>

      {/* FAIL-CLOSED BANNER (If Stale or Error) */}
      {(snapshot?.action_verdict === 'WAIT_STALE_DATA' || snapshot?.stale_data_warning || errorMessage) && (
        <div className="bg-rose-950/40 border border-rose-500/50 rounded-lg p-3 flex items-start gap-2.5 text-rose-200 text-xs">
          <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
          <div>
            <div className="font-bold">{t.failClosedBanner}</div>
            <div className="text-rose-300/80 text-[11px] mt-0.5">
              {errorMessage || snapshot?.error_reason || snapshot?.details || 'Zero synthetic fills permitted.'}
            </div>
          </div>
        </div>
      )}

      {/* 2. ROW 1: 4 CALM EXECUTIVE KPI CARDS */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {/* Card 1: Shadow Equity & Live Alpha */}
        <div className="bg-[#0b101b] border border-[#1e293b] rounded-lg p-3.5 flex flex-col justify-between">
          <div className="text-[11px] text-slate-400 flex items-center justify-between">
            <span>{t.kpiEquityTitle}</span>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-emerald-400 border border-slate-700">
              P2_RP
            </span>
          </div>
          <div className="mt-2">
            <div className="text-2xl font-bold text-white">
              ${(scorecard?.equity_usd ?? snapshot?.account_equity ?? 10000).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </div>
            <div className="flex items-center gap-2 mt-1 text-xs">
              <span className={`font-bold flex items-center gap-0.5 ${(scorecard?.alpha_vs_bnh_pct ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                {(scorecard?.alpha_vs_bnh_pct ?? 0) >= 0 ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                {(scorecard?.alpha_vs_bnh_pct ?? 0) >= 0 ? '+' : ''}{(scorecard?.alpha_vs_bnh_pct ?? 0).toFixed(2)}%
              </span>
              <span className="text-[11px] text-slate-400">
                P2: {(scorecard?.total_return_pct ?? 0) >= 0 ? '+' : ''}{(scorecard?.total_return_pct ?? 0).toFixed(2)}% | BnH: {(scorecard?.bnh_return_pct ?? 0) >= 0 ? '+' : ''}{(scorecard?.bnh_return_pct ?? 0).toFixed(2)}%
              </span>
            </div>
          </div>
          <div className="mt-2 pt-2 border-t border-slate-800/80 text-[10px] text-slate-400 truncate">
            {t.kpiEquitySub}
          </div>
        </div>

        {/* Card 2: 60-Day Forward Proof Tracker */}
        <div className="bg-[#0b101b] border border-[#1e293b] rounded-lg p-3.5 flex flex-col justify-between">
          <div className="text-[11px] text-slate-400 flex items-center justify-between">
            <span>{t.kpiTrackerTitle}</span>
            <span className="text-white font-bold">
              {(scorecard?.days_tracked ?? 0).toFixed(1)} / {scorecard?.target_forward_days ?? 60}d
            </span>
          </div>
          <div className="mt-2 space-y-1.5">
            {/* Progress Bar */}
            <div className="w-full bg-slate-800 rounded-full h-2 overflow-hidden border border-slate-700">
              <div
                className="bg-emerald-500 h-full rounded-full transition-all duration-500"
                style={{ width: `${Math.min(100, ((scorecard?.days_tracked ?? 0) / (scorecard?.target_forward_days ?? 60)) * 100)}%` }}
              />
            </div>
            <div className="flex items-center justify-between text-xs pt-1">
              <span className="text-slate-400">{t.kpiTrackerMaxDD}:</span>
              <span className="text-rose-400 font-bold">
                -{(scorecard?.max_drawdown_pct ?? 0).toFixed(2)}%
              </span>
            </div>
          </div>
          <div className="mt-2 pt-2 border-t border-slate-800/80 flex items-center justify-between text-[11px]">
            <span className="text-slate-400">{t.kpiTrackerSharpe}:</span>
            <span className="font-bold text-sky-400">
              {scorecard?.live_sharpe !== null && scorecard?.live_sharpe !== undefined ? scorecard.live_sharpe.toFixed(2) : (lang === 'bn' ? 'N/A (<১৪ দিন)' : 'N/A (<14d)')}
            </span>
          </div>
        </div>

        {/* Card 3: Real Slippage vs Model */}
        <div className="bg-[#0b101b] border border-[#1e293b] rounded-lg p-3.5 flex flex-col justify-between">
          <div className="text-[11px] text-slate-400 flex items-center justify-between">
            <span>{t.kpiSlippageTitle}</span>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-sky-300 border border-slate-700">
              {(scorecard?.total_fills ?? 0)} Fills
            </span>
          </div>
          <div className="mt-2">
            <div className="text-xl font-bold text-white flex items-baseline gap-1.5">
              <span>{(scorecard?.avg_slippage_bps ?? 0).toFixed(2)} bps</span>
              <span className="text-xs text-slate-400 font-normal">vs. 20.0 bps model</span>
            </div>
            <div className="flex items-center justify-between text-xs mt-1 text-slate-400">
              <span>{t.kpiSlippageSpread}: <strong className="text-slate-300">{(scorecard?.avg_spread_bps ?? 0).toFixed(2)} bps</strong></span>
              <span>{t.kpiSlippageFees}: <strong className="text-slate-300">${(scorecard?.total_fees_usd ?? 0).toFixed(2)}</strong></span>
            </div>
          </div>
          <div className="mt-2 pt-2 border-t border-slate-800/80 text-[10px] text-slate-400 truncate">
            {t.kpiSlippageAvg}
          </div>
        </div>

        {/* Card 4: Risk-Parity Allocation & Cadence */}
        <div className="bg-[#0b101b] border border-[#1e293b] rounded-lg p-3.5 flex flex-col justify-between">
          <div className="text-[11px] text-slate-400 flex items-center justify-between">
            <span>{t.kpiExposureTitle}</span>
            <span className="text-emerald-400 font-bold">
              {((snapshot?.gross_exposure || 0) * 100).toFixed(1)}% Gross
            </span>
          </div>
          <div className="mt-2 space-y-1.5">
            {/* Gross Exposure Bar */}
            <div className="w-full bg-slate-800 rounded-full h-2 overflow-hidden border border-slate-700">
              <div
                className="bg-sky-500 h-full rounded-full transition-all duration-500"
                style={{ width: `${Math.min(100, (snapshot?.gross_exposure || 0) * 100)}%` }}
              />
            </div>
            <div className="flex items-center justify-between text-xs pt-1">
              <span className="text-slate-400">{t.kpiExposureRebal}:</span>
              <span className="text-white font-bold">
                {(snapshot?.days_to_rebalance || 0).toFixed(1)}d
              </span>
            </div>
          </div>
          <div className="mt-2 pt-2 border-t border-slate-800/80 text-[10px] text-emerald-400 truncate">
            ✓ {t.kpiExposureCap}
          </div>
        </div>
      </div>

      {/* 3. ROW 2: 4-ASSET LIVE ALLOCATION & SIGNAL TABLE */}
      <div className="bg-[#090d16] border border-[#1e293b] rounded-lg p-4 space-y-3 shadow-md">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-bold text-white flex items-center gap-2">
            <Layers className="w-4 h-4 text-sky-400" />
            <span>{t.tableTitle}</span>
          </h3>
          <div className="text-xs text-slate-400">
            Strategy: S1 Donchian-48 (1% Risk) + S2-Div Top-2 Dual Momentum (15% Vol Target)
          </div>
        </div>

        {/* Horizontal Stacked Allocation Bar */}
        <div className="space-y-1.5 bg-[#0e1422] border border-[#1e293b] rounded p-2.5">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>{t.allocBarTitle}</span>
            <span className="text-slate-300 font-bold">
              Gross: {((snapshot?.gross_exposure || 0) * 100).toFixed(1)}% | Cash: {(cashWeight * 100).toFixed(1)}%
            </span>
          </div>
          <div className="w-full h-3 rounded bg-slate-800 overflow-hidden flex border border-slate-700">
            {['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'PAXGUSDT'].map((sym) => {
              const w = p2Weights[sym] || 0;
              if (w <= 0.0001) return null;
              const color =
                sym === 'BTCUSDT'
                  ? 'bg-amber-500'
                  : sym === 'ETHUSDT'
                  ? 'bg-blue-500'
                  : sym === 'SOLUSDT'
                  ? 'bg-purple-500'
                  : 'bg-yellow-400';
              return (
                <div
                  key={sym}
                  className={`${color} h-full transition-all duration-300`}
                  style={{ width: `${w * 100}%` }}
                  title={`${sym}: ${(w * 100).toFixed(1)}%`}
                />
              );
            })}
            {cashWeight > 0.0001 && (
              <div
                className="bg-emerald-600 h-full transition-all duration-300"
                style={{ width: `${cashWeight * 100}%` }}
                title={`CASH: ${(cashWeight * 100).toFixed(1)}%`}
              />
            )}
          </div>
          <div className="flex flex-wrap items-center gap-3 text-[11px] text-slate-400 pt-0.5">
            <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full bg-amber-500 inline-block" /> BTC ({((p2Weights['BTCUSDT'] || 0) * 100).toFixed(1)}%)</span>
            <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full bg-blue-500 inline-block" /> ETH ({((p2Weights['ETHUSDT'] || 0) * 100).toFixed(1)}%)</span>
            <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full bg-purple-500 inline-block" /> SOL ({((p2Weights['SOLUSDT'] || 0) * 100).toFixed(1)}%)</span>
            <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full bg-yellow-400 inline-block" /> PAXG ({((p2Weights['PAXGUSDT'] || 0) * 100).toFixed(1)}%)</span>
            <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full bg-emerald-600 inline-block" /> {t.cash} ({(cashWeight * 100).toFixed(1)}%)</span>
          </div>
        </div>

        {/* 4-Asset + Cash Table */}
        <div className="overflow-x-auto">
          <table className="w-full text-xs text-left">
            <thead className="bg-[#0b101c] text-slate-400 uppercase text-[10px] tracking-wider border-b border-[#1e293b]">
              <tr>
                <th className="py-2.5 px-3">{t.colAsset}</th>
                <th className="py-2.5 px-3">{t.colPrice}</th>
                <th className="py-2.5 px-3">{t.colEma}</th>
                <th className="py-2.5 px-3">{t.colStop}</th>
                <th className="py-2.5 px-3">{t.colMom}</th>
                <th className="py-2.5 px-3">{t.colVol}</th>
                <th className="py-2.5 px-3">{t.colTgtWeight}</th>
                <th className="py-2.5 px-3">{t.colTgtDollar}</th>
                <th className="py-2.5 px-3">{t.colShadowUnits}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#1e293b]/60">
              {assetsList.map((asset) => {
                const targetW = p2Weights[asset.symbol] || 0;
                const targetD = (snapshot?.dollar_allocations && snapshot.dollar_allocations[asset.symbol]) || ((snapshot?.account_equity || 10000) * targetW);
                const pos = scorecard?.positions && scorecard.positions[asset.symbol];
                const isAboveEma = asset.ema_status === 'ABOVE';

                return (
                  <tr key={asset.symbol} className="hover:bg-slate-900/50 transition-colors">
                    <td className="py-2.5 px-3 font-bold text-white flex items-center gap-1.5">
                      <span>{asset.symbol}</span>
                    </td>
                    <td className="py-2.5 px-3 text-slate-200">
                      ${asset.price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </td>
                    <td className="py-2.5 px-3">
                      <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${isAboveEma ? 'bg-emerald-500/20 text-emerald-400' : 'bg-rose-500/20 text-rose-400'}`}>
                        {asset.ema_status} (${asset.ema_200.toFixed(1)})
                      </span>
                    </td>
                    <td className="py-2.5 px-3 text-amber-300">
                      ${asset.stop_loss.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </td>
                    <td className="py-2.5 px-3 font-medium">
                      <span className={asset.momentum_30d_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
                        {asset.momentum_30d_pct >= 0 ? '+' : ''}{asset.momentum_30d_pct.toFixed(2)}%
                      </span>
                    </td>
                    <td className="py-2.5 px-3 text-slate-300">
                      {(asset.vol_20d_ann_pct ?? 0).toFixed(1)}%
                    </td>
                    <td className="py-2.5 px-3 font-bold text-white">
                      {(targetW * 100).toFixed(1)}%
                    </td>
                    <td className="py-2.5 px-3 text-emerald-400 font-bold">
                      ${targetD.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </td>
                    <td className="py-2.5 px-3 text-slate-300">
                      {pos ? `${pos.units.toFixed(4)} units ($${pos.market_value_usd.toFixed(2)})` : '0.0000 units ($0.00)'}
                    </td>
                  </tr>
                );
              })}
              {/* CASH ROW */}
              <tr className="bg-[#0b101c]/50 font-bold text-slate-300">
                <td className="py-2.5 px-3 text-emerald-400">CASH</td>
                <td className="py-2.5 px-3">$1.00</td>
                <td className="py-2.5 px-3 text-slate-500">—</td>
                <td className="py-2.5 px-3 text-slate-500">—</td>
                <td className="py-2.5 px-3 text-slate-500">0.00%</td>
                <td className="py-2.5 px-3 text-slate-500">0.0%</td>
                <td className="py-2.5 px-3 text-white">{(cashWeight * 100).toFixed(1)}%</td>
                <td className="py-2.5 px-3 text-emerald-400">
                  ${((snapshot?.account_equity || 10000) * cashWeight).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </td>
                <td className="py-2.5 px-3 text-slate-400">
                  ${((snapshot?.account_equity || 10000) * cashWeight).toFixed(2)} USD
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* 4. ROW 3: LIVE FORWARD EQUITY CURVE & RECENT SHADOW FILLS */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* Left Column (7 cols): Responsive SVG Dual-Line Chart */}
        <div className="lg:col-span-7 bg-[#090d16] border border-[#1e293b] rounded-lg p-4 space-y-3 shadow-md flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-emerald-400" />
              <span>{t.chartTitle}</span>
            </h3>
            <div className="flex items-center gap-3 text-xs">
              <span className="flex items-center gap-1.5 text-emerald-400">
                <span className="w-3 h-0.5 bg-emerald-400 inline-block" /> {t.chartP2Legend}
              </span>
              <span className="flex items-center gap-1.5 text-sky-400">
                <span className="w-3 h-0.5 bg-sky-400 border-t border-dashed border-sky-400 inline-block" /> {t.chartBnhLegend}
              </span>
            </div>
          </div>

          {/* SVG Dual-Line Chart Container */}
          <div className="w-full min-h-[220px] flex items-center justify-center bg-[#070a12] border border-[#1b253b] rounded p-2">
            {bars.length < 2 ? (
              <div className="text-center py-12 px-4 space-y-2">
                <Clock className="w-8 h-8 text-slate-500 mx-auto" />
                <p className="text-xs text-slate-400 max-w-md">{t.chartEmpty}</p>
                <span className="text-[10px] text-slate-500 block">
                  Current Bar Count: {bars.length} / 2 required for live curve rendering.
                </span>
              </div>
            ) : (
              <svg viewBox="0 0 800 220" className="w-full h-52">
                {(() => {
                  const paddingX = 45;
                  const paddingY = 25;
                  const chartW = 800 - paddingX * 2;
                  const chartH = 220 - paddingY * 2;

                  const allEqs = bars.map((b) => b.equity_usd);
                  const allBnh = bars.map((b) => b.bnh_equity_usd);
                  const minVal = Math.min(...allEqs, ...allBnh) * 0.998;
                  const maxVal = Math.max(...allEqs, ...allBnh) * 1.002;
                  const valSpan = Math.max(1, maxVal - minVal);

                  const getX = (idx: number) => paddingX + (idx / (bars.length - 1)) * chartW;
                  const getY = (val: number) => paddingY + chartH - ((val - minVal) / valSpan) * chartH;

                  const p2Points = bars.map((b, i) => `${getX(i)},${getY(b.equity_usd)}`).join(' ');
                  const bnhPoints = bars.map((b, i) => `${getX(i)},${getY(b.bnh_equity_usd)}`).join(' ');

                  const startTs = new Date(bars[0].bar_ts_utc).toISOString().substring(5, 10);
                  const endTs = new Date(bars[bars.length - 1].bar_ts_utc).toISOString().substring(5, 10);

                  return (
                    <g>
                      {/* Grid Lines */}
                      <line x1={paddingX} y1={paddingY} x2={paddingX + chartW} y2={paddingY} stroke="#1e293b" strokeDasharray="3 3" />
                      <line x1={paddingX} y1={paddingY + chartH / 2} x2={paddingX + chartW} y2={paddingY + chartH / 2} stroke="#1e293b" strokeDasharray="3 3" />
                      <line x1={paddingX} y1={paddingY + chartH} x2={paddingX + chartW} y2={paddingY + chartH} stroke="#1e293b" />

                      {/* Y-axis Labels */}
                      <text x={paddingX - 6} y={paddingY + 4} fill="#64748b" fontSize="9" textAnchor="end">
                        ${maxVal.toFixed(0)}
                      </text>
                      <text x={paddingX - 6} y={paddingY + chartH} fill="#64748b" fontSize="9" textAnchor="end">
                        ${minVal.toFixed(0)}
                      </text>

                      {/* X-axis Labels */}
                      <text x={paddingX} y={220 - 6} fill="#64748b" fontSize="9" textAnchor="start">
                        {startTs}
                      </text>
                      <text x={paddingX + chartW} y={220 - 6} fill="#64748b" fontSize="9" textAnchor="end">
                        {endTs}
                      </text>

                      {/* BnH Line (Dashed Sky) */}
                      <polyline fill="none" stroke="#38bdf8" strokeWidth="1.5" strokeDasharray="4 3" points={bnhPoints} />

                      {/* P2_RP Line (Solid Emerald) */}
                      <polyline fill="none" stroke="#10b981" strokeWidth="2.5" points={p2Points} />
                    </g>
                  );
                })()}
              </svg>
            )}
          </div>
        </div>

        {/* Right Column (5 cols): Recent Shadow Fills Table */}
        <div className="lg:col-span-5 bg-[#090d16] border border-[#1e293b] rounded-lg p-4 space-y-3 shadow-md flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-sky-400" />
              <span>{t.fillsTitle}</span>
            </h3>
            <span className="text-[11px] text-slate-400">{fills.length} recent</span>
          </div>

          <div className="overflow-x-auto min-h-[220px] max-h-[260px] overflow-y-auto">
            {fills.length === 0 ? (
              <div className="text-center py-12 px-4 space-y-1.5">
                <CheckCircle2 className="w-7 h-7 text-slate-500 mx-auto" />
                <p className="text-xs text-slate-400">{t.fillsEmpty}</p>
              </div>
            ) : (
              <table className="w-full text-left text-xs">
                <thead className="bg-[#0b101c] text-slate-400 uppercase text-[10px] tracking-wider sticky top-0 border-b border-[#1e293b]">
                  <tr>
                    <th className="py-2 px-2">{t.colTime}</th>
                    <th className="py-2 px-2">{t.colSide}</th>
                    <th className="py-2 px-2">{t.colAsset}</th>
                    <th className="py-2 px-2">{t.colLiveFill}</th>
                    <th className="py-2 px-2">{t.colSlippage}</th>
                    <th className="py-2 px-2">{t.colFee}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#1e293b]/50">
                  {fills.map((fill, idx) => {
                    const isBuy = fill.side === 'BUY';
                    const timeStr = new Date(fill.bar_ts_utc).toISOString().substring(11, 16);
                    return (
                      <tr key={idx} className="hover:bg-slate-900/50">
                        <td className="py-1.5 px-2 text-slate-400 text-[11px]">{timeStr}</td>
                        <td className="py-1.5 px-2 font-bold">
                          <span className={`px-1.5 py-0.5 rounded text-[10px] ${isBuy ? 'bg-emerald-500/20 text-emerald-400' : 'bg-rose-500/20 text-rose-400'}`}>
                            {fill.side}
                          </span>
                        </td>
                        <td className="py-1.5 px-2 text-white font-medium">{fill.symbol}</td>
                        <td className="py-1.5 px-2 text-slate-200">
                          ${fill.live_exec_price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                        </td>
                        <td className="py-1.5 px-2 text-sky-300">
                          {fill.slippage_bps.toFixed(1)} bps
                        </td>
                        <td className="py-1.5 px-2 text-slate-400">
                          ${fill.fee_usd.toFixed(2)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
