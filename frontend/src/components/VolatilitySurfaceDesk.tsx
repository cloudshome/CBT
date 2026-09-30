import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Activity,
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  BarChart3,
  Calendar,
  Layers,
  Percent,
  RefreshCw,
  ShieldAlert,
  TrendingDown,
  TrendingUp,
  Zap,
} from 'lucide-react';
import { api, VolatilitySummaryResponse, VolatilitySurfaceResponse } from '../services/api';

interface VolatilitySurfaceDeskProps {
  currentSymbol?: string;
  onNotify?: (type: 'success' | 'error' | 'warning' | 'info', title: string, message: string) => void;
}

export const VolatilitySurfaceDesk: React.FC<VolatilitySurfaceDeskProps> = ({
  currentSymbol = 'BTC',
  onNotify,
}) => {
  const [symbol, setSymbol] = useState<string>(
    currentSymbol.includes('ETH') ? 'ETH' : 'BTC'
  );
  const [loading, setLoading] = useState<boolean>(true);
  const [summary, setSummary] = useState<VolatilitySummaryResponse | null>(null);
  const [surface, setSurface] = useState<VolatilitySurfaceResponse | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date>(new Date());
  const [activeTab, setActiveTab] = useState<'SUMMARY' | 'SURFACE' | 'SKEW' | 'GEX'>('SUMMARY');

  const onNotifyRef = useRef(onNotify);
  useEffect(() => {
    onNotifyRef.current = onNotify;
  }, [onNotify]);

  const fetchData = useCallback(async () => {
    try {
      const [sumData, surfData] = await Promise.all([
        api.getVolatilitySummary(symbol),
        api.getVolatilitySurface(symbol),
      ]);
      setSummary(sumData);
      setSurface(surfData);
      setLastUpdated(new Date());
    } catch (err: any) {
      console.error('Failed to fetch volatility data:', err);
      onNotifyRef.current?.('error', 'Volatility Feed Error', err.message || 'Failed loading options data.');
    } finally {
      setLoading(false);
    }
  }, [symbol]);

  useEffect(() => {
    setLoading(true);
    fetchData();
    const timer = setInterval(fetchData, 30000); // 30s auto-refresh
    return () => clearInterval(timer);
  }, [fetchData]);

  const skewRegimeBadge = (regime: string) => {
    switch (regime) {
      case 'DEEP_PUT_SKEW':
        return (
          <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-rose-950/80 text-rose-300 border border-rose-800 flex items-center gap-1">
            <ShieldAlert size={12} /> DEEP PUT SKEW (CRASH HEDGE)
          </span>
        );
      case 'MODERATE_PUT_SKEW':
        return (
          <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-amber-950/80 text-amber-300 border border-amber-800 flex items-center gap-1">
            <TrendingDown size={12} /> MODERATE PUT SKEW
          </span>
        );
      case 'CALL_SKEW_PREMIUM':
        return (
          <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-emerald-950/80 text-emerald-300 border border-emerald-800 flex items-center gap-1">
            <TrendingUp size={12} /> CALL PREMIUM (BULL FOMO)
          </span>
        );
      default:
        return (
          <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-slate-800 text-slate-300 border border-slate-700">
            BALANCED SKEW
          </span>
        );
    }
  };

  const termRegimeBadge = (regime: string) => {
    switch (regime) {
      case 'CONTANGO':
        return (
          <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-emerald-950/80 text-emerald-300 border border-emerald-800">
            CONTANGO (NORMAL CALM)
          </span>
        );
      case 'BACKWARDATION':
        return (
          <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-rose-950/80 text-rose-300 border border-rose-800 flex items-center gap-1">
            <AlertTriangle size={12} /> BACKWARDATION (EVENT PANIC)
          </span>
        );
      default:
        return (
          <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-slate-800 text-slate-300 border border-slate-700">
            FLAT TERM STRUCTURE
          </span>
        );
    }
  };

  return (
    <div className="flex flex-col gap-4 text-slate-100 font-sans">
      {/* Top Header Bar */}
      <div className="bg-[#0b111e] border border-slate-800/80 rounded-xl p-4 flex flex-wrap items-center justify-between gap-3 shadow-lg">
        <div className="flex items-center gap-3">
          <div className="p-2.5 bg-indigo-950/60 border border-indigo-700/50 rounded-lg text-indigo-400">
            <Activity className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-bold text-white tracking-wide">
                AUTOMATED VOLATILITY SURFACE &amp; SKEW DESK
              </h2>
              <span className="px-2 py-0.5 text-[10px] font-mono font-semibold bg-indigo-900/50 text-indigo-300 border border-indigo-700/50 rounded">
                TASK 20.3 QUANT MODEL
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              Empirical Deribit Options Chain: 25-Delta Skew, Term Structure Inversion &amp; Net Dealer Gamma (GEX)
            </p>
          </div>
        </div>

        {/* Currency Selector & Controls */}
        <div className="flex items-center gap-2.5">
          <div className="flex items-center bg-slate-900 border border-slate-800 rounded-lg p-1">
            <button
              onClick={() => setSymbol('BTC')}
              className={`px-3 py-1 rounded text-xs font-bold transition-colors ${
                symbol === 'BTC' ? 'bg-amber-500 text-slate-950' : 'text-slate-400 hover:text-white'
              }`}
            >
              BTC Options
            </button>
            <button
              onClick={() => setSymbol('ETH')}
              className={`px-3 py-1 rounded text-xs font-bold transition-colors ${
                symbol === 'ETH' ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-white'
              }`}
            >
              ETH Options
            </button>
          </div>

          <button
            onClick={fetchData}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-lg text-xs text-slate-200 transition-colors disabled:opacity-50"
          >
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
            <span>Refresh</span>
          </button>

          <span className="text-[11px] font-mono text-slate-500 hidden md:block">
            Updated: {lastUpdated.toLocaleTimeString()}
          </span>
        </div>
      </div>

      {/* 5 Primary KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
        {/* Card 1: Underlying Spot Reference */}
        <div className="bg-[#0b111e] border border-slate-800 rounded-lg p-3.5 flex flex-col justify-between">
          <span className="text-[11px] font-mono text-slate-400">UNDERLYING INDEX</span>
          <div className="text-xl font-mono font-bold text-white mt-1">
            ${summary?.underlying_price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) || '---'}
          </div>
          <div className="text-[10px] font-mono text-slate-500 mt-1">
            Active Contracts: <strong className="text-slate-300">{summary?.contracts_count || 0}</strong>
          </div>
        </div>

        {/* Card 2: 25-Delta Skew */}
        <div className="bg-[#0b111e] border border-slate-800 rounded-lg p-3.5 flex flex-col justify-between">
          <span className="text-[11px] font-mono text-slate-400">25-DELTA SKEW</span>
          <div className={`text-xl font-mono font-bold mt-1 flex items-center gap-1 ${
            (summary?.skew.average_skew_25d || 0) >= 0 ? 'text-rose-400' : 'text-emerald-400'
          }`}>
            {(summary?.skew.average_skew_25d || 0) >= 0 ? <ArrowUpRight size={18} /> : <ArrowDownRight size={18} />}
            {((summary?.skew.average_skew_25d || 0) * 100).toFixed(2)}%
          </div>
          <div className="mt-1">
            {skewRegimeBadge(summary?.skew.dominant_regime || 'NEUTRAL_SKEW')}
          </div>
        </div>

        {/* Card 3: Term Structure Slope */}
        <div className="bg-[#0b111e] border border-slate-800 rounded-lg p-3.5 flex flex-col justify-between">
          <span className="text-[11px] font-mono text-slate-400">TERM SLOPE (90D - 7D)</span>
          <div className={`text-xl font-mono font-bold mt-1 ${
            (summary?.term_structure.slope_90d_minus_7d || 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'
          }`}>
            {((summary?.term_structure.slope_90d_minus_7d || 0) * 100).toFixed(2)}%
          </div>
          <div className="mt-1">
            {termRegimeBadge(summary?.term_structure.regime || 'CONTANGO')}
          </div>
        </div>

        {/* Card 4: Net Dealer Gamma (GEX) */}
        <div className="bg-[#0b111e] border border-slate-800 rounded-lg p-3.5 flex flex-col justify-between">
          <span className="text-[11px] font-mono text-slate-400">NET DEALER GEX / 1%</span>
          <div className={`text-xl font-mono font-bold mt-1 ${
            (summary?.gex.net_gamma_usd_per_1pct || 0) >= 0 ? 'text-emerald-300' : 'text-rose-400'
          }`}>
            ${((summary?.gex.net_gamma_usd_per_1pct || 0) / 1e6).toFixed(1)}M
          </div>
          <div className="text-[10px] font-mono text-slate-400 mt-1">
            Max Pain: <strong className="text-amber-300">${summary?.gex.max_pain_strike.toLocaleString() || '---'}</strong>
          </div>
        </div>

        {/* Card 5: Tail-Risk Position Multiplier */}
        <div className="bg-[#0b111e] border border-slate-800 rounded-lg p-3.5 flex flex-col justify-between">
          <span className="text-[11px] font-mono text-slate-400">TAIL-RISK SIZING MULT</span>
          <div className={`text-xl font-mono font-bold mt-1 flex items-center gap-1 ${
            (summary?.tail_risk.tail_risk_multiplier || 1.0) < 0.9 ? 'text-amber-400' : 'text-emerald-400'
          }`}>
            <Zap size={18} />
            {(summary?.tail_risk.tail_risk_multiplier || 1.0).toFixed(2)}x
          </div>
          <div className="text-[10px] font-mono text-slate-500 mt-1">
            Half-Kelly Long Scale Factor
          </div>
        </div>
      </div>

      {/* Sub-Tabs: Summary vs Surface vs Skew Curve vs GEX */}
      <div className="flex items-center gap-2 border-b border-slate-800 pb-2">
        <button
          onClick={() => setActiveTab('SUMMARY')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
            activeTab === 'SUMMARY'
              ? 'bg-indigo-600 text-white shadow'
              : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
          }`}
        >
          <Layers size={14} />
          <span>Institutional Summary</span>
        </button>

        <button
          onClick={() => setActiveTab('SURFACE')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
            activeTab === 'SURFACE'
              ? 'bg-indigo-600 text-white shadow'
              : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
          }`}
        >
          <BarChart3 size={14} />
          <span>2D Volatility Surface Grid</span>
        </button>

        <button
          onClick={() => setActiveTab('SKEW')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
            activeTab === 'SKEW'
              ? 'bg-indigo-600 text-white shadow'
              : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
          }`}
        >
          <Percent size={14} />
          <span>25-Delta Skew by Tenor</span>
        </button>

        <button
          onClick={() => setActiveTab('GEX')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
            activeTab === 'GEX'
              ? 'bg-indigo-600 text-white shadow'
              : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
          }`}
        >
          <Activity size={14} />
          <span>Dealer GEX &amp; Max Pain</span>
        </button>
      </div>

      {/* VIEW 1: INSTITUTIONAL SUMMARY & TERM STRUCTURE */}
      {activeTab === 'SUMMARY' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* Left Panel: Constant-Maturity Term Structure Curve */}
          <div className="bg-[#0b111e] border border-slate-800 rounded-xl p-4 flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <Calendar className="text-indigo-400" size={16} />
                ATM Volatility Term Structure Curve
              </h3>
              <span className="text-xs font-mono text-slate-400">
                Slope: {((summary?.term_structure.slope_90d_minus_7d || 0) * 100).toFixed(2)}%
              </span>
            </div>

            <div className="flex flex-col gap-2 pt-2">
              {summary?.term_structure.curve.map((pt) => (
                <div key={pt.tenor_days} className="flex items-center justify-between p-2.5 bg-slate-900/80 rounded-lg border border-slate-800/80">
                  <span className="text-xs font-mono text-slate-300 font-semibold">
                    {pt.tenor_days}-Day Tenor
                  </span>
                  <div className="flex items-center gap-3">
                    <div className="w-32 bg-slate-800 rounded-full h-2 overflow-hidden hidden sm:block">
                      <div
                        className="bg-indigo-500 h-full rounded-full"
                        style={{ width: `${Math.min(100, Math.max(10, pt.annualized_iv_pct))}%` }}
                      />
                    </div>
                    <span className="text-xs font-mono font-bold text-indigo-300 w-16 text-right">
                      {pt.annualized_iv_pct.toFixed(1)}% IV
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Right Panel: Tail Risk Sentinels & Risk Flags */}
          <div className="bg-[#0b111e] border border-slate-800 rounded-xl p-4 flex flex-col gap-3">
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <ShieldAlert className="text-amber-400" size={16} />
              Derivatives Sentinel Flags &amp; Tail Risk Guidance
            </h3>

            <div className="flex flex-col gap-2 pt-1">
              {summary?.tail_risk.risk_flags.map((flag, idx) => (
                <div
                  key={idx}
                  className={`p-3 rounded-lg border text-xs font-mono flex items-start gap-2 ${
                    flag.includes('BACKWARDATION') || flag.includes('DEEP_PUT')
                      ? 'bg-rose-950/40 border-rose-800/60 text-rose-200'
                      : flag.includes('MODERATE') || flag.includes('NEGATIVE')
                      ? 'bg-amber-950/40 border-amber-800/60 text-amber-200'
                      : 'bg-slate-900/60 border-slate-800 text-slate-300'
                  }`}
                >
                  <span className="font-bold">•</span>
                  <span>{flag}</span>
                </div>
              ))}
            </div>

            <div className="mt-2 p-3 bg-slate-900/90 rounded-lg border border-slate-800 text-xs text-slate-400 leading-relaxed">
              <strong className="text-slate-200">Execution Perimeter Notice:</strong> Volatility surface and skew signals are read-only research indicators. Position sizing scaling is automatically communicated to the Half-Kelly engine to protect capital during options implied crash risk.
            </div>
          </div>
        </div>
      )}

      {/* VIEW 2: 2D VOLATILITY SURFACE MATRIX */}
      {activeTab === 'SURFACE' && surface && (
        <div className="bg-[#0b111e] border border-slate-800 rounded-xl p-4 flex flex-col gap-3 overflow-x-auto">
          <div className="flex items-center justify-between mb-1">
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <Layers className="text-indigo-400" size={16} />
              2D Volatility Surface Matrix (Tenor x Moneyness K/S)
            </h3>
            <span className="text-xs font-mono text-slate-400">
              Values in Annualized IV (%)
            </span>
          </div>

          <table className="w-full text-xs text-center border-collapse">
            <thead>
              <tr className="border-b border-slate-800 bg-slate-900 text-slate-400">
                <th className="p-2 text-left font-mono">Tenor</th>
                {surface.moneyness_levels.map((m) => (
                  <th key={m} className="p-2 font-mono">
                    {(m * 100).toFixed(0)}%
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {surface.surface_matrix.map((row, rIdx) => (
                <tr key={rIdx} className="border-b border-slate-800/60 hover:bg-slate-800/40">
                  <td className="p-2.5 text-left font-mono font-semibold text-slate-300">
                    {surface.tenors_days[rIdx]}d
                  </td>
                  {row.map((iv, cIdx) => {
                    const bgIntensity = Math.min(0.8, Math.max(0.1, (iv - 35) / 50));
                    return (
                      <td
                        key={cIdx}
                        className="p-2.5 font-mono font-bold"
                        style={{
                          backgroundColor: `rgba(99, 102, 241, ${bgIntensity})`,
                          color: iv > 60 ? '#ffffff' : '#e0e7ff',
                        }}
                      >
                        {iv.toFixed(1)}%
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* VIEW 3: 25-DELTA SKEW TABLE */}
      {activeTab === 'SKEW' && summary && (
        <div className="bg-[#0b111e] border border-slate-800 rounded-xl p-4 flex flex-col gap-3 overflow-x-auto">
          <h3 className="text-sm font-bold text-white flex items-center gap-2">
            <Percent className="text-indigo-400" size={16} />
            Constant-Maturity 25-Delta Skew Breakdown
          </h3>

          <table className="w-full text-xs text-left border-collapse">
            <thead>
              <tr className="border-b border-slate-800 bg-slate-900 text-slate-400 font-mono">
                <th className="p-2.5">Tenor</th>
                <th className="p-2.5">ATM Strike</th>
                <th className="p-2.5">ATM IV</th>
                <th className="p-2.5">25d Put Strike</th>
                <th className="p-2.5">25d Put IV</th>
                <th className="p-2.5">25d Call Strike</th>
                <th className="p-2.5">25d Call IV</th>
                <th className="p-2.5">25d Skew (P - C)</th>
                <th className="p-2.5">Regime</th>
              </tr>
            </thead>
            <tbody>
              {summary.skew.tenor_points.map((pt) => (
                <tr key={pt.tenor_days} className="border-b border-slate-800/60 hover:bg-slate-800/40 font-mono">
                  <td className="p-2.5 font-bold text-slate-200">{pt.tenor_days}d</td>
                  <td className="p-2.5 text-slate-300">${pt.atm_strike.toLocaleString()}</td>
                  <td className="p-2.5 text-indigo-300">{(pt.atm_iv * 100).toFixed(1)}%</td>
                  <td className="p-2.5 text-rose-300">${pt.put_25d_strike.toLocaleString()}</td>
                  <td className="p-2.5 text-rose-300">{(pt.put_25d_iv * 100).toFixed(1)}%</td>
                  <td className="p-2.5 text-emerald-300">${pt.call_25d_strike.toLocaleString()}</td>
                  <td className="p-2.5 text-emerald-300">{(pt.call_25d_iv * 100).toFixed(1)}%</td>
                  <td className={`p-2.5 font-bold ${pt.twenty_five_delta_skew >= 0 ? 'text-rose-400' : 'text-emerald-400'}`}>
                    {pt.twenty_five_delta_skew >= 0 ? '+' : ''}{(pt.twenty_five_delta_skew * 100).toFixed(2)}%
                  </td>
                  <td className="p-2.5">{skewRegimeBadge(pt.regime)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* VIEW 4: DEALER GEX & STRIKE PROFILE */}
      {activeTab === 'GEX' && summary && (
        <div className="bg-[#0b111e] border border-slate-800 rounded-xl p-4 flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <Activity className="text-emerald-400" size={16} />
              Options Dealer Gamma Profile &amp; Max Pain Pinning
            </h3>
            <span className="text-xs font-mono text-slate-400">
              Zero Gamma Level: <strong className="text-amber-300">${summary.gex.zero_gamma_strike?.toLocaleString() || 'N/A'}</strong>
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-1">
            <div className="p-3 bg-slate-900 border border-slate-800 rounded-lg">
              <span className="text-xs font-mono text-slate-400">Options Max Pain</span>
              <div className="text-xl font-bold font-mono text-amber-400 mt-1">
                ${summary.gex.max_pain_strike.toLocaleString()}
              </div>
              <p className="text-[11px] text-slate-500 mt-1">
                Strike where total option expiry payout is minimized.
              </p>
            </div>

            <div className="p-3 bg-slate-900 border border-slate-800 rounded-lg">
              <span className="text-xs font-mono text-slate-400">Net Dealer Gamma</span>
              <div className={`text-xl font-bold font-mono mt-1 ${
                summary.gex.net_gamma_usd_per_1pct >= 0 ? 'text-emerald-400' : 'text-rose-400'
              }`}>
                ${(summary.gex.net_gamma_usd_per_1pct / 1e6).toFixed(2)}M / 1%
              </div>
              <p className="text-[11px] text-slate-500 mt-1">
                {summary.gex.regime === 'POSITIVE_PINNING'
                  ? 'Positive GEX: Market makers dampen volatility near strikes.'
                  : 'Negative GEX: Market makers accelerate directional expansion.'}
              </p>
            </div>

            <div className="p-3 bg-slate-900 border border-slate-800 rounded-lg">
              <span className="text-xs font-mono text-slate-400">Zero Gamma Flip</span>
              <div className="text-xl font-bold font-mono text-white mt-1">
                ${summary.gex.zero_gamma_strike?.toLocaleString() || '---'}
              </div>
              <p className="text-[11px] text-slate-500 mt-1">
                Price threshold where volatility regime flips from calm to explosive.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
