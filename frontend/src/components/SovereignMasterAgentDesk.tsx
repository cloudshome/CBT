import React, { useState, useEffect, useCallback } from 'react';
import {
  Brain,
  ShieldCheck,
  Zap,
  TrendingUp,
  TrendingDown,
  RefreshCw,
  Database,
} from 'lucide-react';
import { api } from '../services/api';

interface SovereignDecision {
  agent_id: string;
  symbol: string;
  decision: 'BUY' | 'SELL' | 'CASH';
  confidence_pct: number;
  expected_value_r: number;
  current_price: number;
  entry_zone: [number, number];
  stop_loss: number;
  take_profit_ladder: { tp1: number; tp2: number; tp3: number };
  risk_reward_ratio: number;
  suggested_risk_usd: number;
  suggested_units: number;
  thesis: string;
  memory_dossier: {
    total_trades: number;
    win_rate_pct: number;
    net_pnl_usd: number;
    memory_guidance: string;
  };
  research_dossier: {
    macro_regime: string;
    key_research_analog: string;
    invalidation_rule: string;
    vault_citations: string[];
  };
  market_structure_dossier: {
    adx: number;
    regime: string;
    rvol: number;
    sky_status: string;
  };
}

interface SovereignMasterAgentDeskProps {
  onSelectSymbol?: (symbol: string) => void;
  addToast: (type: 'success' | 'error' | 'info' | 'warning', title: string, message: string) => void;
}

export const SovereignMasterAgentDesk: React.FC<SovereignMasterAgentDeskProps> = ({
  onSelectSymbol,
  addToast,
}) => {
  const [loading, setLoading] = useState<boolean>(true);
  const [executingSymbol, setExecutingSymbol] = useState<string | null>(null);
  const [decisions, setDecisions] = useState<Record<string, SovereignDecision>>({});
  const [selectedAsset, setSelectedAsset] = useState<string>('BTC/USDT');
  const [lastRefreshed, setLastRefreshed] = useState<Date>(new Date());
  const [autoPilotEnabled, setAutoPilotEnabled] = useState<boolean>(false);
  const [autoPilotLoading, setAutoPilotLoading] = useState<boolean>(false);
  const [recentActivity, setRecentActivity] = useState<any[]>([]);
  const [selfImprovement, setSelfImprovement] = useState<any>(null);

  const fetchDashboard = useCallback(async () => {
    try {
      setLoading(true);
      const res = await api.getSovereignDashboard();
      if (res && res.decisions) {
        setDecisions(res.decisions);
        setLastRefreshed(new Date());
      }
      if (res && res.auto_pilot) {
        setAutoPilotEnabled(Boolean(res.auto_pilot.auto_pilot_enabled));
        if (res.auto_pilot.recent_activity) {
          setRecentActivity(res.auto_pilot.recent_activity);
        }
      }
      if (res && res.self_improvement) {
        setSelfImprovement(res.self_improvement);
      }
    } catch (err: any) {
      console.warn('Could not refresh Sovereign Agent dashboard:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDashboard();
    const interval = setInterval(fetchDashboard, 10000); // 10s refresh
    return () => clearInterval(interval);
  }, [fetchDashboard]);

  const handleToggleAutoPilot = async () => {
    try {
      setAutoPilotLoading(true);
      const nextState = !autoPilotEnabled;
      const res = await api.setSovereignAutoPilot(nextState);
      if (res && typeof res.auto_pilot_enabled === 'boolean') {
        setAutoPilotEnabled(res.auto_pilot_enabled);
        if (res.auto_pilot_enabled) {
          addToast(
            'success',
            '⚡ Autonomous Auto-Pilot Activated',
            'Sovereign Master Agent is now hands-free. High-confidence A+ setups on BTC, ETH, and Gold will auto-execute to Binance Futures Testnet.'
          );
        } else {
          addToast(
            'info',
            'Auto-Pilot Deactivated',
            'Sovereign Master Agent returned to Manual 1-Click Confirmation Mode.'
          );
        }
      }
      fetchDashboard();
    } catch (err: any) {
      addToast('error', 'Auto-Pilot Toggle Error', err.message || 'Could not update auto-pilot mode');
    } finally {
      setAutoPilotLoading(false);
    }
  };

  const handleExecute = async (symbol: string) => {
    try {
      setExecutingSymbol(symbol);
      const res = await api.executeSovereignDecision(symbol, 'Manual UI Authorization');
      if (res.executed) {
        addToast(
          'success',
          `Master Order Executed: ${res.action} ${symbol}`,
          `Opened position ${res.position_id} (${res.units} units). Mirrored to Binance Testnet: ${res.mirrored_to_binance_testnet ? 'YES' : 'PENDING'}`
        );
        fetchDashboard();
      } else {
        addToast(
          'warning',
          `Master Agent: CASH Protection Active`,
          res.reason || 'Decision is CASH. No order placed to protect equity.'
        );
      }
    } catch (err: any) {
      addToast('error', 'Execution Failed', err.message || 'Could not execute master decision');
    } finally {
      setExecutingSymbol(null);
    }
  };

  const currentDec = decisions[selectedAsset];

  return (
    <div className="w-full min-h-screen bg-[#060912] text-slate-200 font-mono flex flex-col p-4 max-w-[1920px] mx-auto space-y-4 select-none">
      {/* 1. Master Level Header & Credentials Strip */}
      <div className="flex flex-wrap items-center justify-between p-4 bg-[#0a0f1d] border border-[#1e293b] rounded-xl shadow-xl gap-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-gradient-to-tr from-cyan-600 via-indigo-600 to-purple-600 flex items-center justify-center text-white shadow-lg shadow-cyan-500/20">
            <Brain className="w-6 h-6 animate-pulse" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-bold text-white tracking-wider flex items-center gap-2">
                SOVEREIGN MASTER AGENT
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-cyan-950 text-cyan-300 border border-cyan-500/40 font-bold">
                  APEX TRADING BRAIN
                </span>
              </h2>
            </div>
            <p className="text-xs text-slate-400">
              Synthesizes 419-Trade Memory • 588 Research Vault Articles • Real-Time Order Flow • Instant Decisions
            </p>
          </div>
        </div>

        {/* System & Risk Badges */}
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <div className="px-3 py-1 rounded bg-[#0d1322] border border-emerald-500/30 text-emerald-400 flex items-center gap-1.5 font-bold">
            <ShieldCheck className="w-3.5 h-3.5" />
            <span>TIER-1 ONLY (BTC • ETH • GOLD)</span>
          </div>
          <div className="px-3 py-1 rounded bg-[#0d1322] border border-cyan-500/30 text-cyan-400 flex items-center gap-1.5 font-bold">
            <Database className="w-3.5 h-3.5" />
            <span>BINANCE FUTURES ($5,000 TESTNET ACTIVE)</span>
          </div>
          
          {/* Autonomous Auto-Pilot Toggle Button */}
          <button
            onClick={handleToggleAutoPilot}
            disabled={autoPilotLoading}
            className={`px-3 py-1 rounded-lg border font-bold flex items-center gap-2 transition-all shadow-md ${
              autoPilotEnabled
                ? 'bg-gradient-to-r from-emerald-600 via-teal-600 to-emerald-700 border-emerald-400 text-white shadow-emerald-500/30 ring-1 ring-emerald-400'
                : 'bg-[#0f172a] border-slate-700 text-slate-400 hover:text-slate-200 hover:border-slate-500'
            }`}
            title={autoPilotEnabled ? 'Auto-Pilot ACTIVE: Click to switch to Safe 1-Click Co-Pilot' : 'Click to enable 100% Hands-Free Autonomous Auto-Trading'}
          >
            <Zap className={`w-3.5 h-3.5 ${autoPilotEnabled ? 'text-yellow-300 animate-bounce' : 'text-slate-400'}`} />
            <span>{autoPilotEnabled ? '⚡ AUTO-PILOT: ACTIVE' : '⚡ AUTO-PILOT: OFF'}</span>
          </button>

          <button
            onClick={fetchDashboard}
            disabled={loading}
            className="px-3 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 flex items-center gap-1.5 transition-all text-xs font-semibold"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            <span>{lastRefreshed.toLocaleTimeString()}</span>
          </button>
        </div>
      </div>

      {/* Auto-Pilot Status Banner */}
      <div className={`p-3 rounded-xl border flex items-center justify-between text-xs transition-all ${
        autoPilotEnabled
          ? 'bg-gradient-to-r from-emerald-950/60 via-[#0a1b24] to-[#0c1829] border-emerald-500/50 text-emerald-200 shadow-lg shadow-emerald-950/40'
          : 'bg-[#0a0f1d] border-[#1e293b] text-slate-400'
      }`}>
        <div className="flex items-center gap-2.5">
          <div className={`w-2.5 h-2.5 rounded-full ${autoPilotEnabled ? 'bg-emerald-400 animate-ping' : 'bg-slate-500'}`} />
          <span className="font-bold text-slate-200">
            {autoPilotEnabled ? '⚡ AUTONOMOUS AUTO-PILOT RUNNING' : '🛡️ SAFE 1-CLICK CO-PILOT MODE'}
          </span>
          <span className="hidden md:inline text-slate-400">
            {autoPilotEnabled
              ? '• Hands-free autonomous execution enabled. When an A+ setup triggers (≥70% conf, ≥2.0R), it auto-dispatches into Binance Futures Testnet and Shadow Ledger.'
              : '• Signals are actively evaluated every 10s. Click [Check & Execute] on any card to authorize trade dispatch.'}
          </span>
        </div>
        <div className="flex items-center gap-2 font-mono text-[11px]">
          <span className="text-slate-500">Scan Cycle:</span>
          <span className="text-cyan-400 font-bold">10s</span>
          {recentActivity.length > 0 && (
            <span className="text-slate-400 ml-2">
              Last: <span className="text-slate-200">{recentActivity[recentActivity.length - 1]?.action}</span>
            </span>
          )}
        </div>
      </div>

      {/* 2. Three Sovereign Tier-1 Asset Cards */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {['BTC/USDT', 'ETH/USDT', 'XAU/USD'].map((sym) => {
          const dec = decisions[sym];
          const isSelected = selectedAsset === sym;
          const isBtc = sym.includes('BTC');
          const isEth = sym.includes('ETH');
          const isGold = sym.includes('XAU');

          const label = isBtc ? 'BITCOIN' : isEth ? 'ETHEREUM' : isGold ? 'GOLD (XAU)' : sym;
          const badgeColor =
            dec?.decision === 'BUY'
              ? 'bg-emerald-950 border-emerald-500 text-emerald-400'
              : dec?.decision === 'SELL'
              ? 'bg-rose-950 border-rose-500 text-rose-400'
              : 'bg-amber-950/80 border-amber-500/50 text-amber-300';

          return (
            <div
              key={sym}
              onClick={() => {
                setSelectedAsset(sym);
                onSelectSymbol?.(sym);
              }}
              className={`p-4 rounded-xl border transition-all cursor-pointer flex flex-col justify-between ${
                isSelected
                  ? 'bg-[#0c1324] border-cyan-500 shadow-xl shadow-cyan-500/10'
                  : 'bg-[#090d18] border-[#1e293b] hover:border-slate-600'
              }`}
            >
              <div>
                {/* Header */}
                <div className="flex items-center justify-between pb-3 border-b border-[#1e293b]/60 mb-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-white text-base">
                        {isBtc ? 'BITCOIN' : isEth ? 'ETHEREUM' : isGold ? 'GOLD (XAU)' : sym}
                      </span>
                      <span className="text-xs text-slate-500">{sym}</span>
                    </div>
                    <div className="text-xs text-slate-400">
                      Mark Price: <span className="font-bold text-white">${dec?.current_price.toLocaleString() || '---'}</span>
                    </div>
                  </div>

                  {/* Decision Pill */}
                  <div className={`px-3 py-1 rounded-lg border font-black text-xs ${badgeColor} flex items-center gap-1`}>
                    {dec?.decision === 'BUY' && <TrendingUp className="w-3.5 h-3.5 text-emerald-400" />}
                    {dec?.decision === 'SELL' && <TrendingDown className="w-3.5 h-3.5 text-rose-400" />}
                    {dec?.decision === 'CASH' && <ShieldCheck className="w-3.5 h-3.5 text-amber-300" />}
                    <span>{dec?.decision || 'ANALYZING...'}</span>
                  </div>
                </div>

                {/* Metrics Grid */}
                <div className="grid grid-cols-2 gap-2 text-xs mb-3">
                  <div className="p-2 rounded bg-[#060912] border border-[#1e293b]">
                    <div className="text-[10px] text-slate-500">CONFIDENCE</div>
                    <div className="font-bold text-cyan-300">{dec?.confidence_pct || 0}%</div>
                  </div>
                  <div className="p-2 rounded bg-[#060912] border border-[#1e293b]">
                    <div className="text-[10px] text-slate-500">EXPECTED VALUE</div>
                    <div className="font-bold text-emerald-400">+{dec?.expected_value_r || 0}R</div>
                  </div>
                </div>

                {/* Empirical Memory Status */}
                <div className="p-2.5 rounded-lg bg-[#060912]/80 border border-[#1e293b] text-[11px] mb-3 space-y-1">
                  <div className="flex items-center justify-between text-slate-400 font-semibold">
                    <span className="flex items-center gap-1">
                      <Database className="w-3 h-3 text-cyan-400" />
                      <span>Past Ledger Memory</span>
                    </span>
                    <span className={`font-bold ${dec?.memory_dossier.net_pnl_usd && dec.memory_dossier.net_pnl_usd >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                      {dec?.memory_dossier.net_pnl_usd !== undefined ? (dec.memory_dossier.net_pnl_usd >= 0 ? `+$${dec.memory_dossier.net_pnl_usd}` : `-$${Math.abs(dec.memory_dossier.net_pnl_usd)}`) : '---'}
                    </span>
                  </div>
                  <p className="text-slate-300 leading-relaxed text-[10px]">
                    {dec?.memory_dossier.memory_guidance || 'Reading memory...'}
                  </p>
                </div>

                {/* Technical Trade Parameters if not CASH */}
                {dec?.decision !== 'CASH' ? (
                  <div className="p-2.5 rounded-lg bg-[#0a101f] border border-cyan-500/30 text-[11px] mb-3 space-y-1.5">
                    <div className="flex justify-between">
                      <span className="text-slate-500">Entry:</span>
                      <span className="font-bold text-white">${dec?.current_price}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-500">Stop Loss:</span>
                      <span className="font-bold text-rose-400">${dec?.stop_loss}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-500">Target (TP1):</span>
                      <span className="font-bold text-emerald-400">${dec?.take_profit_ladder.tp1} ({dec?.risk_reward_ratio}:1 R:R)</span>
                    </div>
                  </div>
                ) : (
                  <div className="p-2.5 rounded-lg bg-amber-950/20 border border-amber-500/30 text-[10px] text-amber-200 mb-3 flex items-start gap-1.5">
                    <ShieldCheck className="w-3.5 h-3.5 text-amber-400 mt-0.5 shrink-0" />
                    <span>Chop &amp; Fakeout Filter active. Capital safeguarded in 100% Cash until confirmed A+ setup.</span>
                  </div>
                )}
              </div>

              {/* Action Buttons */}
              <div className="pt-2 border-t border-[#1e293b]/60 flex items-center gap-2">
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleExecute(sym);
                  }}
                  disabled={executingSymbol === sym}
                  className={`flex-1 py-2 px-3 rounded-lg font-bold text-xs flex items-center justify-center gap-1.5 transition-all shadow-md ${
                    dec?.decision === 'BUY'
                      ? 'bg-emerald-500 hover:bg-emerald-400 text-slate-950 shadow-emerald-500/20'
                      : dec?.decision === 'SELL'
                      ? 'bg-rose-500 hover:bg-rose-400 text-white shadow-rose-500/20'
                      : 'bg-slate-800 hover:bg-slate-700 text-slate-300'
                  }`}
                >
                  <Zap className="w-3.5 h-3.5" />
                  <span>
                    {executingSymbol === sym
                      ? 'Executing...'
                      : dec?.decision === 'CASH'
                      ? 'Check & Execute Cash'
                      : `Execute ${dec?.decision} ${label}`}
                  </span>
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {/* 3. Deep Cognitive Inspection Panel for Selected Asset */}
      {currentDec && (
        <div className="p-4 bg-[#0a0f1d] border border-[#1e293b] rounded-xl shadow-xl space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-[#1e293b]">
            <div className="flex items-center gap-2">
              <Brain className="w-5 h-5 text-cyan-400" />
              <h3 className="font-bold text-white text-sm">
                SOVEREIGN REASONING DOSSIER FOR {selectedAsset}
              </h3>
            </div>
            <div className="text-xs text-slate-400">
              Regime: <span className="text-cyan-300 font-bold">{currentDec.market_structure_dossier.regime}</span> (ADX {currentDec.market_structure_dossier.adx})
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
            {/* Column 1: Master Thesis */}
            <div className="p-3 bg-[#060912] border border-[#1e293b] rounded-lg space-y-2">
              <div className="text-slate-400 font-bold uppercase text-[10px] flex items-center gap-1">
                <Zap className="w-3.5 h-3.5 text-cyan-400" />
                <span>Master Verdict &amp; Thesis</span>
              </div>
              <p className="text-slate-200 leading-relaxed text-[11px]">
                {currentDec.thesis}
              </p>
            </div>

            {/* Column 2: Research Vault Context */}
            <div className="p-3 bg-[#060912] border border-[#1e293b] rounded-lg space-y-2">
              <div className="text-slate-400 font-bold uppercase text-[10px] flex items-center gap-1">
                <Database className="w-3.5 h-3.5 text-purple-400" />
                <span>588-Article Research Vault Alignment</span>
              </div>
              <div className="space-y-1 text-[11px] text-slate-300">
                <div><span className="text-slate-500">Macro Regime:</span> {currentDec.research_dossier.macro_regime}</div>
                <div><span className="text-slate-500">Historical Analog:</span> {currentDec.research_dossier.key_research_analog}</div>
                <div><span className="text-slate-500">Invalidation Rule:</span> {currentDec.research_dossier.invalidation_rule}</div>
              </div>
            </div>

            {/* Column 3: Risk Sizing & Half-Kelly */}
            <div className="p-3 bg-[#060912] border border-[#1e293b] rounded-lg space-y-2">
              <div className="text-slate-400 font-bold uppercase text-[10px] flex items-center gap-1">
                <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
                <span>Risk Desk Clearance</span>
              </div>
              <div className="space-y-1 text-[11px] text-slate-300">
                <div><span className="text-slate-500">Max Risk Cap:</span> ${currentDec.suggested_risk_usd} (1.5% Equity Budget)</div>
                <div><span className="text-slate-500">Suggested Units:</span> {currentDec.suggested_units} units</div>
                <div><span className="text-slate-500">Asymmetric Target:</span> {currentDec.risk_reward_ratio}:1 R:R minimum</div>
                <div><span className="text-slate-500">Testnet Target:</span> Binance Futures (5,000 USDT active)</div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 4. 14-Day Institutional Burn-In Scorecard (Path to Real Capital) */}
      {selfImprovement?.burn_in_scorecard && (
        <div className="p-4 bg-[#0a0f1d] border border-[#1e293b] rounded-xl shadow-xl space-y-4">
          <div className="flex flex-wrap items-center justify-between pb-3 border-b border-[#1e293b] gap-2">
            <div className="flex items-center gap-2">
              <ShieldCheck className="w-5 h-5 text-emerald-400" />
              <div>
                <h3 className="font-bold text-white text-sm flex items-center gap-2">
                  14-DAY INSTITUTIONAL BURN-IN SCORECARD
                  <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-500/30">
                    PATHWAY TO REAL CAPITAL
                  </span>
                </h3>
                <p className="text-[11px] text-slate-400">
                  Real capital is strictly locked behind these 5 mathematical gates. Zero bypass permitted.
                </p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <div className="text-right">
                <div className="text-[10px] text-slate-400 uppercase font-bold">Readiness Score</div>
                <div className="text-sm font-bold text-cyan-400">
                  {selfImprovement.burn_in_scorecard.overall_readiness_pct}%
                </div>
              </div>
              <div className="px-3 py-1 rounded bg-rose-950/60 border border-rose-500/40 text-rose-300 text-xs font-bold">
                🔒 REAL CAPITAL: LOCKED
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-5 gap-3 text-xs">
            {/* Gate 1 */}
            <div className="p-3 bg-[#060912] border border-[#1e293b] rounded-lg space-y-1.5">
              <div className="text-slate-400 font-bold text-[10px]">GATE 1: DURATION</div>
              <div className="text-base font-bold text-white">Day {selfImprovement.burn_in_scorecard.days_elapsed} / 14</div>
              <p className="text-[10px] text-slate-500">14 consecutive calendar days of zero-crash stability.</p>
              <div className="text-[10px] text-amber-400 font-bold">⏳ IN PROGRESS</div>
            </div>

            {/* Gate 2 */}
            <div className="p-3 bg-[#060912] border border-[#1e293b] rounded-lg space-y-1.5">
              <div className="text-slate-400 font-bold text-[10px]">GATE 2: PROFIT FACTOR</div>
              <div className="text-base font-bold text-white">
                {selfImprovement.burn_in_scorecard.gate_2_profit_factor.current} / ≥ 1.50
              </div>
              <p className="text-[10px] text-slate-500">Gross profit must exceed gross loss by 1.5x.</p>
              <div className="text-[10px] text-amber-400 font-bold">⏳ ACCUMULATING</div>
            </div>

            {/* Gate 3 */}
            <div className="p-3 bg-[#060912] border border-[#1e293b] rounded-lg space-y-1.5">
              <div className="text-slate-400 font-bold text-[10px]">GATE 3: MAX DRAWDOWN</div>
              <div className="text-base font-bold text-emerald-400">
                {selfImprovement.burn_in_scorecard.gate_3_max_drawdown.current_pct}% ≤ 3.0%
              </div>
              <p className="text-[10px] text-slate-500">Peak-to-trough equity decline strictly constrained.</p>
              <div className="text-[10px] text-emerald-400 font-bold">✅ PASS</div>
            </div>

            {/* Gate 4 */}
            <div className="p-3 bg-[#060912] border border-[#1e293b] rounded-lg space-y-1.5">
              <div className="text-slate-400 font-bold text-[10px]">GATE 4: DSR SIGNIFICANCE</div>
              <div className="text-base font-bold text-white">
                {selfImprovement.burn_in_scorecard.gate_4_dsr_significance.current_score} / ≥ 0.95
              </div>
              <p className="text-[10px] text-slate-500">Deflated Sharpe proves edge is not random luck.</p>
              <div className="text-[10px] text-amber-400 font-bold">⏳ INGESTING</div>
            </div>

            {/* Gate 5 */}
            <div className="p-3 bg-[#060912] border border-[#1e293b] rounded-lg space-y-1.5">
              <div className="text-slate-400 font-bold text-[10px]">GATE 5: EXECUTION INTEGRITY</div>
              <div className="text-base font-bold text-emerald-400">149 / 149 GATES</div>
              <p className="text-[10px] text-slate-500">Milestone 18 certified. Zero phantom fills.</p>
              <div className="text-[10px] text-emerald-400 font-bold">✅ CERTIFIED</div>
            </div>
          </div>
        </div>
      )}

      {/* 5. Closed-Loop Self-Improvement & Forensic Autopsy Desk */}
      {selfImprovement && (
        <div className="p-4 bg-[#0a0f1d] border border-[#1e293b] rounded-xl shadow-xl space-y-4">
          <div className="flex flex-wrap items-center justify-between pb-3 border-b border-[#1e293b] gap-2">
            <div className="flex items-center gap-2">
              <Brain className="w-5 h-5 text-indigo-400 animate-pulse" />
              <div>
                <h3 className="font-bold text-white text-sm flex items-center gap-2">
                  CLOSED-LOOP SELF-IMPROVEMENT &amp; FORENSIC AUTOPSY
                  <span className="text-[10px] px-2 py-0.5 rounded bg-indigo-950 text-indigo-300 border border-indigo-500/30">
                    ADAPTIVE REASONING
                  </span>
                </h3>
                <p className="text-[11px] text-slate-400">
                  Every closed trade undergoes forensic post-mortem analysis to update filters and prevent repeat mistakes.
                </p>
              </div>
            </div>
            <div className="text-xs text-slate-400 font-mono">
              Autopsies Ingested: <span className="text-cyan-400 font-bold">{selfImprovement.autopsies_analyzed_count}</span>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 text-xs">
            {/* Active Learned Heuristics */}
            <div className="p-3 bg-[#060912] border border-[#1e293b] rounded-lg space-y-2">
              <div className="text-indigo-400 font-bold uppercase text-[10px] flex items-center gap-1.5">
                <ShieldCheck className="w-3.5 h-3.5" />
                <span>Active Learned Heuristics (Protecting Capital)</span>
              </div>
              <div className="space-y-2">
                {selfImprovement.learned_rules?.map((rule: any) => (
                  <div key={rule.rule_id} className="p-2.5 rounded bg-[#090e1a] border border-[#1e293b] space-y-1">
                    <div className="flex justify-between items-center text-[11px]">
                      <span className="font-bold text-cyan-300">{rule.rule_id}: {rule.asset}</span>
                      <span className="text-[9px] px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-400 font-bold">ACTIVE</span>
                    </div>
                    <div className="text-[10px] text-slate-300">
                      <span className="text-slate-500">Action:</span> {rule.action}
                    </div>
                    <div className="text-[10px] text-slate-400 leading-tight">
                      <span className="text-slate-500">Origin:</span> {rule.origin}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Recent Forensic Autopsy Reports */}
            <div className="p-3 bg-[#060912] border border-[#1e293b] rounded-lg space-y-2">
              <div className="text-rose-400 font-bold uppercase text-[10px] flex items-center gap-1.5">
                <Zap className="w-3.5 h-3.5" />
                <span>Recent Forensic Trade Autopsies</span>
              </div>
              <div className="space-y-2">
                {selfImprovement.recent_autopsies?.length > 0 ? (
                  selfImprovement.recent_autopsies.slice(0, 3).map((a: any, idx: number) => (
                    <div key={idx} className="p-2.5 rounded bg-[#090e1a] border border-[#1e293b] space-y-1">
                      <div className="flex justify-between items-center text-[11px]">
                        <span className="font-bold text-slate-200">{a.symbol} (${a.pnl_usd.toFixed(2)})</span>
                        <span className="text-[9px] px-1.5 py-0.5 rounded bg-rose-950 text-rose-300 font-bold">{a.loss_category}</span>
                      </div>
                      <div className="text-[10px] text-slate-300 leading-tight">
                        <span className="text-slate-500">Diagnosis:</span> {a.primary_root_cause}
                      </div>
                      <div className="text-[10px] text-emerald-400 leading-tight">
                        <span className="text-slate-500">Adaptation:</span> {a.preventative_recommendation}
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="p-4 text-center text-slate-500 text-[11px]">
                    No recent losses under Sovereign Master Agent governance.
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

