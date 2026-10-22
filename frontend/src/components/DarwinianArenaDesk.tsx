import React, { useState, useEffect, useCallback } from 'react';
import {
  ShieldCheck,
  TrendingUp,
  TrendingDown,
  RefreshCw,
  ExternalLink,
  Flame,
  Activity,
  Layers,
  Info,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Clock,
  BarChart2,
  Sliders,
  Send,
} from 'lucide-react';
import {
  getArenaLeaderboard,
  getTemporalBtcForecast,
  getTemporalLaws,
  evaluateTemporalCondition,
  ArenaLeaderboardSnapshot,
  ArenaSpecialist,
  TemporalForecast,
  PriceActionLaw,
} from '../services/api';

interface DarwinianArenaDeskProps {
  onSelectSymbol?: (symbol: string) => void;
  addToast?: (type: 'info' | 'success' | 'warning' | 'error', title: string, message: string) => void;
}

export const DarwinianArenaDesk: React.FC<DarwinianArenaDeskProps> = ({
  onSelectSymbol,
  addToast,
}) => {
  // Navigation & Tabs
  const [activeTab, setActiveTab] = useState<'TOURNAMENT' | 'TEMPORAL' | 'SCENARIO'>('TOURNAMENT');

  // State
  const [leaderboard, setLeaderboard] = useState<ArenaLeaderboardSnapshot | null>(null);
  const [forecasts, setForecasts] = useState<TemporalForecast[]>([]);
  const [laws, setLaws] = useState<PriceActionLaw[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [autoRefresh, setAutoRefresh] = useState<boolean>(true);

  // Scenario Query State
  const [scenarioInput, setScenarioInput] = useState<string>('15m return >= +0.40% with RVOL >= 1.5x');
  const [scenarioHorizon, setScenarioHorizon] = useState<string>('15m');
  const [scenarioResult, setScenarioResult] = useState<any | null>(null);
  const [scenarioEvaluating, setScenarioEvaluating] = useState<boolean>(false);

  // Data Fetching
  const fetchAllData = useCallback(async () => {
    try {
      const [lbData, fcData, lawsData] = await Promise.all([
        getArenaLeaderboard().catch(() => null),
        getTemporalBtcForecast().catch(() => []),
        getTemporalLaws().catch(() => []),
      ]);

      if (lbData) setLeaderboard(lbData);
      if (fcData) setForecasts(fcData);
      if (lawsData) setLaws(lawsData);
    } catch (err: any) {
      console.error('Failed to refresh Arena / Temporal data:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAllData();
  }, [fetchAllData]);

  // Auto-refresh interval (every 10 seconds)
  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(() => {
      fetchAllData();
    }, 10000);
    return () => clearInterval(interval);
  }, [autoRefresh, fetchAllData]);

  // Handle Scenario Evaluation
  const handleEvaluateScenario = async () => {
    if (!scenarioInput.trim()) return;
    setScenarioEvaluating(true);
    try {
      const res = await evaluateTemporalCondition({
        condition_expr: scenarioInput,
        target_horizon: scenarioHorizon,
        symbol: 'BTC/USDT',
      });
      setScenarioResult(res);
      addToast?.('success', 'Scenario Evaluated', `Assessed across ${res.sample_size || 0} sample candles.`);
    } catch (err: any) {
      addToast?.('error', 'Evaluation Failed', err.message || 'Could not parse scenario condition.');
    } finally {
      setScenarioEvaluating(false);
    }
  };

  // Status Styling Helpers
  const getStatusBadge = (status: ArenaSpecialist['status']) => {
    switch (status) {
      case 'SURVIVING':
        return (
          <span className="px-2 py-0.5 text-[11px] font-mono font-bold rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 flex items-center gap-1 shadow-sm shadow-emerald-500/20">
            <CheckCircle2 size={12} />
            SURVIVING
          </span>
        );
      case 'PROBATION':
        return (
          <span className="px-2 py-0.5 text-[11px] font-mono font-bold rounded bg-amber-500/10 text-amber-400 border border-amber-500/30 flex items-center gap-1 shadow-sm shadow-amber-500/20 animate-pulse">
            <AlertTriangle size={12} />
            PROBATION (0.5x Sizing)
          </span>
        );
      case 'QUARANTINED':
      case 'REJECTED':
        return (
          <span className="px-2 py-0.5 text-[11px] font-mono font-bold rounded bg-rose-500/10 text-rose-400 border border-rose-500/30 flex items-center gap-1 shadow-sm shadow-rose-500/20">
            <XCircle size={12} />
            QUARANTINED (VETOED)
          </span>
        );
      case 'PAPER_QUALIFIED':
        return (
          <span className="px-2 py-0.5 text-[11px] font-mono font-bold rounded bg-cyan-500/10 text-cyan-400 border border-cyan-500/30 flex items-center gap-1 shadow-sm shadow-cyan-500/20">
            <Flame size={12} />
            QUALIFIED
          </span>
        );
      default:
        return null;
    }
  };

  return (
    <div className="flex-1 w-full max-w-[1920px] mx-auto p-4 flex flex-col gap-4 text-slate-200">
      {/* ========================================================================= */}
      {/* 1. INSTITUTIONAL HEADER & METRICS BAR */}
      {/* ========================================================================= */}
      <div className="bg-[#090d16] border border-[#1e293b] rounded-xl p-4 shadow-xl flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-indigo-500/20 to-cyan-500/20 border border-cyan-500/40 flex items-center justify-center text-cyan-400 shadow-lg shadow-cyan-500/10">
            <Flame size={26} className="text-cyan-400 animate-pulse" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-bold font-mono tracking-wider text-white">
                DARWINIAN SPECIALIST RESEARCH ARENA
              </h2>
              <span className="text-[10px] px-2 py-0.5 rounded bg-cyan-950/80 text-cyan-400 font-mono border border-cyan-800">
                MILESTONE 21/22 ACTIVE
              </span>
            </div>
            <p className="text-xs text-slate-400 font-mono flex items-center gap-2 mt-0.5">
              <span>10 Isolated Sandboxes ($100 each)</span>
              <span>•</span>
              <span className="text-emerald-400">Zero Desk Contamination</span>
              <span>•</span>
              <span>Temporal Mathematical Law Discovery</span>
            </p>
          </div>
        </div>

        {/* Global Key Vitals */}
        <div className="flex flex-wrap items-center gap-3 w-full md:w-auto">
          <div className="bg-[#0f172a] border border-[#1e293b] rounded-lg px-3 py-2">
            <div className="text-[10px] text-slate-400 font-mono uppercase">Arena Total Equity</div>
            <div className="text-sm font-bold font-mono text-cyan-400">
              ${leaderboard?.total_arena_equity_usd.toFixed(2) || '1,000.00'}
              <span className="text-[10px] text-slate-500 ml-1">/ $1,000.00</span>
            </div>
          </div>

          <div className="bg-[#0f172a] border border-[#1e293b] rounded-lg px-3 py-2">
            <div className="text-[10px] text-slate-400 font-mono uppercase">Surviving Specialists</div>
            <div className="text-sm font-bold font-mono text-emerald-400 flex items-center gap-1.5">
              <ShieldCheck size={14} />
              <span>{leaderboard?.active_specialists_count || 10} / 10</span>
            </div>
          </div>

          <div className="bg-[#0f172a] border border-[#1e293b] rounded-lg px-3 py-2">
            <div className="text-[10px] text-slate-400 font-mono uppercase">Master Desk Boundary</div>
            <div className="text-sm font-bold font-mono text-slate-300">
              $10,000.00 <span className="text-[10px] text-emerald-500 font-normal">(ISOLATED)</span>
            </div>
          </div>

          <div className="flex items-center gap-2 ml-auto">
            <button
              onClick={() => setAutoRefresh(!autoRefresh)}
              className={`px-3 py-2 rounded-lg text-xs font-mono border transition-all flex items-center gap-1.5 ${
                autoRefresh
                  ? 'bg-emerald-950/40 border-emerald-500/40 text-emerald-400'
                  : 'bg-slate-900 border-slate-700 text-slate-400'
              }`}
            >
              <Activity size={13} className={autoRefresh ? 'animate-pulse' : ''} />
              <span>{autoRefresh ? 'LIVE (10s)' : 'PAUSED'}</span>
            </button>

            <button
              onClick={fetchAllData}
              disabled={loading}
              className="p-2 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-700 text-slate-300 transition-all"
              title="Manual Refresh"
            >
              <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            </button>
          </div>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* 2. SUB-NAVIGATION TABS */}
      {/* ========================================================================= */}
      <div className="flex items-center border-b border-[#1e293b] gap-2 pb-1 text-xs font-mono">
        <button
          onClick={() => setActiveTab('TOURNAMENT')}
          className={`flex items-center gap-2 px-4 py-2 rounded-t-lg font-bold border-b-2 transition-all ${
            activeTab === 'TOURNAMENT'
              ? 'border-cyan-400 text-cyan-400 bg-[#0f172a]'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <Layers size={14} />
          <span>10-Coin Specialists Tournament</span>
          <span className="px-1.5 py-0.2 rounded bg-cyan-900/60 text-cyan-300 text-[10px]">10</span>
        </button>

        <button
          onClick={() => setActiveTab('TEMPORAL')}
          className={`flex items-center gap-2 px-4 py-2 rounded-t-lg font-bold border-b-2 transition-all ${
            activeTab === 'TEMPORAL'
              ? 'border-indigo-400 text-indigo-400 bg-[#0f172a]'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <Clock size={14} />
          <span>Temporal Price-Action Forecasts</span>
          <span className="px-1.5 py-0.2 rounded bg-indigo-900/60 text-indigo-300 text-[10px]">BTC</span>
        </button>

        <button
          onClick={() => setActiveTab('SCENARIO')}
          className={`flex items-center gap-2 px-4 py-2 rounded-t-lg font-bold border-b-2 transition-all ${
            activeTab === 'SCENARIO'
              ? 'border-purple-400 text-purple-400 bg-[#0f172a]'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <Sliders size={14} />
          <span>Mathematical Law &amp; Scenario Miner</span>
          <span className="px-1.5 py-0.2 rounded bg-purple-900/60 text-purple-300 text-[10px]">FDR Gated</span>
        </button>
      </div>

      {/* ========================================================================= */}
      {/* 3. TAB 1: 10-COIN SPECIALIST TOURNAMENT GRID */}
      {/* ========================================================================= */}
      {activeTab === 'TOURNAMENT' && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-5 gap-4">
          {leaderboard?.specialists.map((spec) => {
            const hasPosition = spec.open_position !== null;
            const alphaColor =
              spec.alpha_vs_benchmark_pct > 0
                ? 'text-emerald-400'
                : spec.alpha_vs_benchmark_pct < 0
                ? 'text-rose-400'
                : 'text-slate-400';

            return (
              <div
                key={spec.specialist_id}
                className={`bg-[#090d16] border rounded-xl p-4 flex flex-col justify-between transition-all hover:border-cyan-500/50 shadow-lg ${
                  hasPosition ? 'border-cyan-500/40 bg-gradient-to-b from-[#0d1627] to-[#090d16]' : 'border-[#1e293b]'
                }`}
              >
                {/* Specialist Top Info */}
                <div>
                  <div className="flex items-center justify-between gap-2 mb-2">
                    <div className="flex items-center gap-2">
                      <span className="text-base font-bold font-mono text-white tracking-wide">
                        {spec.symbol.replace('/USDT', '')}
                      </span>
                      <span className="text-[10px] text-slate-500 font-mono">/USDT</span>
                    </div>
                    {getStatusBadge(spec.status)}
                  </div>

                  <div className="text-[11px] font-mono text-cyan-400/80 mb-3 truncate" title={spec.active_strategy_id}>
                    Strategy: {spec.active_strategy_id.replace('concept_', '').replace('_v1', '')}
                  </div>

                  {/* Benchmark & Equity Comparison */}
                  <div className="bg-[#0f172a] border border-[#1e293b] rounded-lg p-2.5 mb-3 space-y-1.5 text-xs font-mono">
                    <div className="flex justify-between items-center">
                      <span className="text-slate-400 text-[11px]">Sandbox Equity:</span>
                      <span className="font-bold text-white">${spec.current_equity_usd.toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-slate-400 text-[11px]">Live Price:</span>
                      <span className="text-slate-300">
                        ${spec.benchmark_current_price !== null ? spec.benchmark_current_price.toLocaleString() : '---'}
                      </span>
                    </div>
                    <div className="flex justify-between items-center border-t border-[#1e293b] pt-1 mt-1">
                      <span className="text-slate-400 text-[11px]">Alpha vs B&amp;H:</span>
                      <span className={`font-bold ${alphaColor}`}>
                        {spec.alpha_vs_benchmark_pct > 0 ? '+' : ''}
                        {spec.alpha_vs_benchmark_pct.toFixed(2)}%
                      </span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-slate-400 text-[11px]">Max Drawdown:</span>
                      <span className={spec.max_drawdown_pct >= 10.0 ? 'text-amber-400 font-bold' : 'text-slate-400'}>
                        {spec.max_drawdown_pct.toFixed(2)}%
                      </span>
                    </div>
                  </div>

                  {/* Drawdown Risk Gate Progress Bar */}
                  <div className="mb-3">
                    <div className="flex justify-between text-[10px] font-mono text-slate-500 mb-1">
                      <span>Risk Bar (10% Prob / 20% Quaran)</span>
                      <span>{spec.max_drawdown_pct.toFixed(1)}%</span>
                    </div>
                    <div className="w-full bg-slate-900 h-1.5 rounded-full overflow-hidden border border-slate-800">
                      <div
                        className={`h-full transition-all ${
                          spec.max_drawdown_pct >= 20.0
                            ? 'bg-rose-500'
                            : spec.max_drawdown_pct >= 10.0
                            ? 'bg-amber-500'
                            : 'bg-cyan-500'
                        }`}
                        style={{ width: `${Math.min(spec.max_drawdown_pct * 5, 100)}%` }}
                      />
                    </div>
                  </div>

                  {/* Active Simulated Position Details */}
                  {hasPosition && spec.open_position ? (
                    <div className="bg-[#0b1320] border border-cyan-500/30 rounded-lg p-2.5 mb-3 text-xs font-mono space-y-1">
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] text-cyan-400 font-bold uppercase tracking-wider flex items-center gap-1">
                          <Activity size={11} className="animate-pulse" />
                          ACTIVE {spec.open_position.direction}
                        </span>
                        <span
                          className={`text-xs font-bold ${
                            spec.unrealized_pnl_usd >= 0 ? 'text-emerald-400' : 'text-rose-400'
                          }`}
                        >
                          {spec.unrealized_pnl_usd >= 0 ? '+' : ''}${spec.unrealized_pnl_usd.toFixed(3)}
                        </span>
                      </div>
                      <div className="flex justify-between text-[11px] text-slate-400">
                        <span>Entry: ${spec.open_position.entry_price.toLocaleString()}</span>
                        <span>Size: ${spec.open_position.notional_usd.toFixed(1)}</span>
                      </div>
                      <div className="flex justify-between text-[10px] text-slate-500">
                        <span>SL: ${spec.open_position.stop_loss.toLocaleString()}</span>
                        <span>TP: ${spec.open_position.take_profit.toLocaleString()}</span>
                      </div>
                    </div>
                  ) : (
                    <div className="bg-[#0f172a]/50 border border-dashed border-[#1e293b] rounded-lg p-3 text-center mb-3">
                      <span className="text-[11px] font-mono text-slate-500 flex items-center justify-center gap-1.5">
                        <Info size={12} />
                        Position Flat (Scanning Setup)
                      </span>
                    </div>
                  )}
                </div>

                {/* Footer Actions */}
                <div className="border-t border-[#1e293b] pt-3 flex items-center justify-between gap-2">
                  <div className="text-[10px] font-mono text-slate-500">
                    Trades: {spec.total_trades} (W:{spec.winning_trades} / L:{spec.losing_trades})
                  </div>
                  <button
                    onClick={() => {
                      const cleanSym = spec.symbol.replace('/', '').toUpperCase();
                      onSelectSymbol?.(cleanSym);
                      addToast?.('info', 'Cockpit Switched', `Loaded ${cleanSym} into active Terminal.`);
                    }}
                    className="px-2.5 py-1 rounded bg-[#0f172a] hover:bg-cyan-950 border border-slate-700 hover:border-cyan-500/40 text-[11px] font-mono text-cyan-300 transition-all flex items-center gap-1"
                  >
                    <span>Terminal</span>
                    <ExternalLink size={10} />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* ========================================================================= */}
      {/* 4. TAB 2: TEMPORAL PRICE-ACTION INTELLIGENCE (BTC HORIZONS) */}
      {/* ========================================================================= */}
      {activeTab === 'TEMPORAL' && (
        <div className="flex flex-col gap-4">
          <div className="bg-[#090d16] border border-[#1e293b] rounded-xl p-4">
            <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-2 mb-4">
              <div>
                <h3 className="text-sm font-bold font-mono text-white flex items-center gap-2">
                  <Clock size={16} className="text-indigo-400" />
                  BTC/USDT MULTI-HORIZON PUMP / DUMP / CHOP PROBABILITY FORECAST
                </h3>
                <p className="text-xs text-slate-400 font-mono mt-0.5">
                  Calibrated via Epistemic Barrier Model &amp; Non-Linear Price Action Features (Zero Lookahead)
                </p>
              </div>
              <span className="text-xs font-mono text-indigo-400 bg-indigo-950/40 border border-indigo-800 px-2.5 py-1 rounded">
                Model: temporal_v1.0.0
              </span>
            </div>

            {/* Forecast Horizons Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
              {forecasts.map((fc) => (
                <div
                  key={fc.forecast_id}
                  className="bg-[#0f172a] border border-[#1e293b] rounded-xl p-4 flex flex-col justify-between"
                >
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-base font-bold font-mono text-white">{fc.horizon} Horizon</span>
                      <span className="text-xs font-mono text-slate-400">
                        Move Threshold: ±{fc.movement_threshold_pct}%
                      </span>
                    </div>

                    {/* Probability Bars */}
                    <div className="space-y-2 mb-4">
                      <div>
                        <div className="flex justify-between text-xs font-mono mb-1">
                          <span className="text-emerald-400 font-bold flex items-center gap-1">
                            <TrendingUp size={12} /> PUMP Prob
                          </span>
                          <span className="text-emerald-400 font-bold">{(fc.prob_pump * 100).toFixed(1)}%</span>
                        </div>
                        <div className="w-full bg-slate-900 h-2 rounded-full overflow-hidden">
                          <div className="h-full bg-emerald-500 rounded-full" style={{ width: `${fc.prob_pump * 100}%` }} />
                        </div>
                      </div>

                      <div>
                        <div className="flex justify-between text-xs font-mono mb-1">
                          <span className="text-rose-400 font-bold flex items-center gap-1">
                            <TrendingDown size={12} /> DUMP Prob
                          </span>
                          <span className="text-rose-400 font-bold">{(fc.prob_dump * 100).toFixed(1)}%</span>
                        </div>
                        <div className="w-full bg-slate-900 h-2 rounded-full overflow-hidden">
                          <div className="h-full bg-rose-500 rounded-full" style={{ width: `${fc.prob_dump * 100}%` }} />
                        </div>
                      </div>

                      <div>
                        <div className="flex justify-between text-xs font-mono mb-1">
                          <span className="text-slate-400 flex items-center gap-1">
                            <Activity size={12} /> CHOP / RANGE
                          </span>
                          <span className="text-slate-400">{(fc.prob_range * 100).toFixed(1)}%</span>
                        </div>
                        <div className="w-full bg-slate-900 h-2 rounded-full overflow-hidden">
                          <div className="h-full bg-slate-600 rounded-full" style={{ width: `${fc.prob_range * 100}%` }} />
                        </div>
                      </div>
                    </div>

                    {/* Barrier Hit Probabilities */}
                    <div className="bg-[#0b1120] border border-[#1e293b] rounded-lg p-2.5 text-[11px] font-mono space-y-1 mb-3">
                      <div className="flex justify-between text-slate-300">
                        <span>Hit Upper Barrier 1st:</span>
                        <span className="text-emerald-400 font-bold">
                          {(fc.prob_hit_upper_barrier_first * 100).toFixed(1)}%
                        </span>
                      </div>
                      <div className="flex justify-between text-slate-300">
                        <span>Hit Lower Barrier 1st:</span>
                        <span className="text-rose-400 font-bold">
                          {(fc.prob_hit_lower_barrier_first * 100).toFixed(1)}%
                        </span>
                      </div>
                      <div className="flex justify-between text-slate-400 border-t border-[#1e293b] pt-1 mt-1">
                        <span>Neither Barrier Hit:</span>
                        <span>{(fc.prob_neither_barrier_hit * 100).toFixed(1)}%</span>
                      </div>
                    </div>
                  </div>

                  <div className="text-[10px] font-mono text-slate-500 flex justify-between">
                    <span>Uncertainty: {fc.epistemic_uncertainty.toFixed(2)}</span>
                    <span>Ref: ${fc.reference_price.toLocaleString()}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 5. TAB 3: MATHEMATICAL LAWS & SCENARIO MINER */}
      {/* ========================================================================= */}
      {activeTab === 'SCENARIO' && (
        <div className="flex flex-col gap-4">
          {/* Interactive Scenario Evaluator */}
          <div className="bg-[#090d16] border border-[#1e293b] rounded-xl p-4">
            <h3 className="text-sm font-bold font-mono text-white flex items-center gap-2 mb-1">
              <Sliders size={16} className="text-purple-400" />
              INTERACTIVE PRICE-ACTION SCENARIO MINER
            </h3>
            <p className="text-xs text-slate-400 font-mono mb-4">
              Enter any market condition expression to test historical conditional lift and FDR-adjusted significance.
            </p>

            <div className="flex flex-col md:flex-row items-center gap-3 mb-4">
              <input
                type="text"
                value={scenarioInput}
                onChange={(e) => setScenarioInput(e.target.value)}
                placeholder="e.g. 15m return >= +0.40% with RVOL >= 1.5x"
                className="flex-1 w-full bg-[#0f172a] border border-[#1e293b] focus:border-purple-500/50 rounded-lg px-3.5 py-2 text-xs font-mono text-white outline-none"
              />

              <select
                value={scenarioHorizon}
                onChange={(e) => setScenarioHorizon(e.target.value)}
                className="bg-[#0f172a] border border-[#1e293b] rounded-lg px-3 py-2 text-xs font-mono text-slate-200 outline-none"
              >
                <option value="15m">15m Horizon</option>
                <option value="30m">30m Horizon</option>
                <option value="1h">1h Horizon</option>
                <option value="2h">2h Horizon</option>
              </select>

              <button
                onClick={handleEvaluateScenario}
                disabled={scenarioEvaluating}
                className="px-4 py-2 rounded-lg bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white text-xs font-mono font-bold transition-all shadow-md shadow-purple-600/20 flex items-center gap-2"
              >
                <Send size={13} className={scenarioEvaluating ? 'animate-spin' : ''} />
                <span>{scenarioEvaluating ? 'Evaluating...' : 'Test Hypothesis'}</span>
              </button>
            </div>

            {/* Scenario Evaluation Results Box */}
            {scenarioResult && (
              <div className="bg-[#0b1320] border border-purple-500/30 rounded-xl p-4 font-mono text-xs space-y-2">
                <div className="flex items-center justify-between border-b border-[#1e293b] pb-2">
                  <span className="font-bold text-white flex items-center gap-2">
                    <CheckCircle2 size={14} className="text-emerald-400" />
                    Hypothesis Result: {scenarioResult.status || 'EVALUATED'}
                  </span>
                  <span className="text-[11px] text-purple-400">
                    Neff: {scenarioResult.effective_sample_size?.toFixed(1) || '0'}
                  </span>
                </div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 pt-1">
                  <div>
                    <span className="text-slate-500 text-[11px] block">Conditional Pump Rate:</span>
                    <span className="text-sm font-bold text-emerald-400">
                      {scenarioResult.conditional_pump_pct?.toFixed(1) || '0.0'}%
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500 text-[11px] block">Historical Lift:</span>
                    <span className="text-sm font-bold text-cyan-400">
                      {scenarioResult.lift?.toFixed(2) || '1.00'}x
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500 text-[11px] block">Adjusted p-value (FDR):</span>
                    <span className="text-sm font-bold text-slate-200">
                      {scenarioResult.adjusted_p_value_fdr?.toFixed(4) || '1.0000'}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500 text-[11px] block">Out-of-Sample BSS:</span>
                    <span
                      className={`text-sm font-bold ${
                        (scenarioResult.brier_skill_score || 0) > 0 ? 'text-emerald-400' : 'text-rose-400'
                      }`}
                    >
                      {scenarioResult.brier_skill_score?.toFixed(3) || '0.000'}
                    </span>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Mathematical Price-Action Laws Discovered */}
          <div className="bg-[#090d16] border border-[#1e293b] rounded-xl p-4">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-sm font-bold font-mono text-white flex items-center gap-2">
                  <BarChart2 size={16} className="text-cyan-400" />
                  MATHEMATICAL PRICE-ACTION LAWS INVENTORY
                </h3>
                <p className="text-xs text-slate-400 font-mono mt-0.5">
                  Governed by Benjamini-Hochberg False Discovery Rate &amp; Walk-Forward Brier Skill Score
                </p>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left font-mono text-xs">
                <thead>
                  <tr className="border-b border-[#1e293b] text-slate-500 text-[11px]">
                    <th className="py-2.5 px-3">Law ID / Name</th>
                    <th className="py-2.5 px-3">Condition Rule</th>
                    <th className="py-2.5 px-3">Horizon</th>
                    <th className="py-2.5 px-3">Train Lift</th>
                    <th className="py-2.5 px-3">Test Lift</th>
                    <th className="py-2.5 px-3">FDR p-val</th>
                    <th className="py-2.5 px-3">Net Expectancy</th>
                    <th className="py-2.5 px-3">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#1e293b]/50">
                  {laws.map((law) => {
                    const statusClass =
                      law.status === 'VALIDATED'
                        ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                        : law.status === 'REJECTED'
                        ? 'bg-rose-500/10 text-rose-400 border-rose-500/30'
                        : 'bg-amber-500/10 text-amber-400 border-amber-500/30';

                    return (
                      <tr key={law.law_id} className="hover:bg-[#0f172a]/50 transition-colors">
                        <td className="py-2.5 px-3 font-bold text-white">
                          <div>{law.name}</div>
                          <div className="text-[10px] text-slate-500 font-normal">{law.law_id}</div>
                        </td>
                        <td className="py-2.5 px-3 text-slate-300 max-w-xs truncate" title={law.description}>
                          {law.description}
                        </td>
                        <td className="py-2.5 px-3 text-cyan-400">{law.target_horizon}</td>
                        <td className="py-2.5 px-3 text-slate-300">{law.lift_train.toFixed(2)}x</td>
                        <td className="py-2.5 px-3 text-slate-300">{law.lift_test.toFixed(2)}x</td>
                        <td className="py-2.5 px-3 text-slate-300">{law.adjusted_p_value_fdr.toFixed(3)}</td>
                        <td
                          className={`py-2.5 px-3 font-bold ${
                            law.net_expectancy_r_base > 0 ? 'text-emerald-400' : 'text-rose-400'
                          }`}
                        >
                          {law.net_expectancy_r_base.toFixed(2)}R
                        </td>
                        <td className="py-2.5 px-3">
                          <span
                            className={`px-2 py-0.5 text-[10px] rounded border font-bold ${statusClass}`}
                            title={law.rejection_reason || ''}
                          >
                            {law.status}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
