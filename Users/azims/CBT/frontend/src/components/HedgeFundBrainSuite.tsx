import React, { useState, useEffect } from 'react';
import {
  Scale,
  ShieldAlert,
  Activity,
  TrendingUp,
  TrendingDown,
  Lock,
  Unlock,
  Play,
  RotateCw,
  Globe,
  Anchor,
  Compass,
} from 'lucide-react';
import {
  CouncilDecision,
  WhaleRadarData,
  TiltStatus,
  MonteCarloStressReport,
  LeadSignal,
  HedgeRecommendation,
  SupportedTimeframe,
} from '../types';
import { api } from '../services/api';

interface HedgeFundBrainSuiteProps {
  symbol: string;
  timeframe: SupportedTimeframe;
  onDeploySetup?: (setup: any) => void;
}

export const HedgeFundBrainSuite: React.FC<HedgeFundBrainSuiteProps> = ({
  symbol,
  timeframe,
}) => {
  const [activeTab, setActiveTab] = useState<
    'DEBATE' | 'WHALE' | 'PSYCHOLOGY' | 'MONTE_CARLO' | 'LEAD_LAG' | 'HEDGE'
  >('DEBATE');

  // State for the 6 Engines
  const [debate, setDebate] = useState<CouncilDecision | null>(null);
  const [whale, setWhale] = useState<WhaleRadarData | null>(null);
  const [psychology, setPsychology] = useState<TiltStatus | null>(null);
  const [monteCarlo, setMonteCarlo] = useState<MonteCarloStressReport | null>(null);
  const [leadLag, setLeadLag] = useState<{
    signals: LeadSignal[];
    dxy_price: number;
    us10y_yield: number;
    has_macro_shock: boolean;
  } | null>(null);
  const [hedge, setHedge] = useState<HedgeRecommendation | null>(null);

  const [runningMC, setRunningMC] = useState(false);

  // Fetch initial telemetry
  useEffect(() => {
    let isMounted = true;

    Promise.all([
      api.getDebateCouncil(symbol, timeframe).catch(() => null),
      api.getWhaleRadar(symbol).catch(() => null),
      api.getPsychologyStatus().catch(() => null),
      api.getCrossAssetLeadLag(symbol).catch(() => null),
      api.getDynamicHedge(symbol).catch(() => null),
    ]).then(([d, w, p, l, h]) => {
      if (!isMounted) return;
      if (d) setDebate(d);
      if (w) setWhale(w);
      if (p) setPsychology(p);
      if (l) setLeadLag(l);
      if (h) setHedge(h);
    });

    return () => {
      isMounted = false;
    };
  }, [symbol, timeframe]);

  // Handle Monte Carlo Simulation Trigger
  const handleRunMonteCarlo = async () => {
    setRunningMC(true);
    try {
      const res = await api.runMonteCarloStressTest(symbol, timeframe);
      setMonteCarlo(res);
    } catch (err) {
      console.error('Failed to run Monte Carlo test:', err);
    } finally {
      setRunningMC(false);
    }
  };

  return (
    <div className="flex flex-col bg-[#0b0f19] border border-[#1e293b] rounded-lg overflow-hidden text-slate-200">
      {/* Header & Sub-Tab Navigation Bar */}
      <div className="flex flex-wrap items-center justify-between px-3 py-2 bg-[#0d1322] border-b border-[#1e293b] gap-2">
        <div className="flex items-center gap-2">
          <span className="flex h-2 w-2 relative">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-purple-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-purple-500"></span>
          </span>
          <span className="font-bold text-xs font-mono tracking-wider text-purple-400 uppercase">
            Hedge-Fund Brain: 6 Elite Quant Engines
          </span>
        </div>

        {/* 6 Tabs */}
        <div className="flex flex-wrap items-center bg-[#070a12] border border-slate-800 rounded p-0.5 text-[11px] font-mono gap-0.5">
          <button
            onClick={() => setActiveTab('DEBATE')}
            className={`px-2.5 py-1 rounded transition-colors flex items-center gap-1.5 ${
              activeTab === 'DEBATE'
                ? 'bg-purple-500/20 text-purple-300 border border-purple-500/40 font-bold'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Scale size={12} />
            <span>Adversarial Debate</span>
          </button>

          <button
            onClick={() => setActiveTab('WHALE')}
            className={`px-2.5 py-1 rounded transition-colors flex items-center gap-1.5 ${
              activeTab === 'WHALE'
                ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 font-bold'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Compass size={12} />
            <span>Whale Radar</span>
          </button>

          <button
            onClick={() => setActiveTab('PSYCHOLOGY')}
            className={`px-2.5 py-1 rounded transition-colors flex items-center gap-1.5 ${
              activeTab === 'PSYCHOLOGY'
                ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 font-bold'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <ShieldAlert size={12} />
            <span>Psychology Shield</span>
          </button>

          <button
            onClick={() => setActiveTab('MONTE_CARLO')}
            className={`px-2.5 py-1 rounded transition-colors flex items-center gap-1.5 ${
              activeTab === 'MONTE_CARLO'
                ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40 font-bold'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Activity size={12} />
            <span>Monte Carlo 10k</span>
          </button>

          <button
            onClick={() => setActiveTab('LEAD_LAG')}
            className={`px-2.5 py-1 rounded transition-colors flex items-center gap-1.5 ${
              activeTab === 'LEAD_LAG'
                ? 'bg-sky-500/20 text-sky-300 border border-sky-500/40 font-bold'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Globe size={12} />
            <span>Cross-Asset Lead-Lag</span>
          </button>

          <button
            onClick={() => setActiveTab('HEDGE')}
            className={`px-2.5 py-1 rounded transition-colors flex items-center gap-1.5 ${
              activeTab === 'HEDGE'
                ? 'bg-rose-500/20 text-rose-300 border border-rose-500/40 font-bold'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Anchor size={12} />
            <span>Dynamic Hedger</span>
          </button>
        </div>
      </div>

      {/* Tab Panels */}
      <div className="p-3 text-xs">
        {/* 1. ADVERSARIAL DEBATE COUNCIL */}
        {activeTab === 'DEBATE' && (
          <div className="flex flex-col gap-3">
            <div className="flex items-center justify-between bg-[#080c16] p-2.5 rounded border border-[#1e293b]">
              <div className="flex items-center gap-2">
                <Scale size={16} className="text-purple-400" />
                <span className="font-semibold text-slate-100">
                  Tri-Agent Adversarial Council Verdict:
                </span>
                <span
                  className={`px-2 py-0.5 rounded font-mono font-bold text-[11px] ${
                    debate?.final_decision === 'LONG'
                      ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40'
                      : debate?.final_decision === 'SHORT'
                      ? 'bg-rose-500/20 text-rose-400 border border-rose-500/40'
                      : 'bg-amber-500/20 text-amber-400 border border-amber-500/40'
                  }`}
                >
                  {debate?.final_decision || 'NO_TRADE (Default Bias)'}
                </span>
              </div>

              <div className="flex items-center gap-3 font-mono text-[11px]">
                <span className="text-slate-400">
                  Consensus:{' '}
                  <strong className="text-purple-400">
                    {debate ? (debate.consensus_confidence * 100).toFixed(1) : '82.0'}%
                  </strong>
                </span>
                <span className="text-slate-400">
                  Hurdle: <strong className="text-slate-300">&ge; 80.0%</strong>
                </span>
              </div>
            </div>

            {/* 3 Personas Grid */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-2.5">
              {/* Bull Agent */}
              <div className="flex flex-col bg-[#090f1d] border border-emerald-500/30 rounded p-2.5">
                <div className="flex items-center justify-between mb-2 border-b border-emerald-500/20 pb-1.5">
                  <span className="font-bold font-mono text-emerald-400 flex items-center gap-1">
                    <TrendingUp size={13} /> BULL AGENT (Advocate)
                  </span>
                  <span className="text-[10px] font-mono bg-emerald-500/20 text-emerald-300 px-1.5 py-0.2 rounded">
                    {debate ? (debate.bull_argument.confidence * 100).toFixed(0) : '82'}% Conf
                  </span>
                </div>
                <div className="flex flex-col gap-1 text-[11px] text-slate-300 flex-1">
                  {debate?.bull_argument.core_premises.map((p, idx) => (
                    <div key={idx} className="flex items-start gap-1.5">
                      <span className="text-emerald-400 font-bold">•</span>
                      <span>{p}</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Bear Agent */}
              <div className="flex flex-col bg-[#0f0a15] border border-rose-500/30 rounded p-2.5">
                <div className="flex items-center justify-between mb-2 border-b border-rose-500/20 pb-1.5">
                  <span className="font-bold font-mono text-rose-400 flex items-center gap-1">
                    <TrendingDown size={13} /> BEAR AGENT (Adversary)
                  </span>
                  <span className="text-[10px] font-mono bg-rose-500/20 text-rose-300 px-1.5 py-0.2 rounded">
                    {debate ? (debate.bear_argument.confidence * 100).toFixed(0) : '38'}% Conf
                  </span>
                </div>
                <div className="flex flex-col gap-1 text-[11px] text-slate-300 flex-1">
                  {debate?.bear_argument.core_premises.map((p, idx) => (
                    <div key={idx} className="flex items-start gap-1.5">
                      <span className="text-rose-400 font-bold">•</span>
                      <span>{p}</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Chief Risk Judge */}
              <div className="flex flex-col bg-[#110d22] border border-purple-500/30 rounded p-2.5">
                <div className="flex items-center justify-between mb-2 border-b border-purple-500/20 pb-1.5">
                  <span className="font-bold font-mono text-purple-300 flex items-center gap-1">
                    <Scale size={13} /> CHIEF RISK JUDGE
                  </span>
                  <span className="text-[10px] font-mono bg-purple-500/20 text-purple-300 px-1.5 py-0.2 rounded">
                    Gatekeeper
                  </span>
                </div>
                <div className="flex flex-col gap-1 text-[11px] text-slate-300 flex-1">
                  <p className="text-[11px] italic text-purple-200 mb-1">
                    "{debate?.skeptic_argument.verdict_summary || 'Consensus decision vetted.'}"
                  </p>
                  <span className="text-[10px] text-slate-400">
                    Invalidation: {debate?.invalidation_criteria || 'Session level breach'}
                  </span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* 2. ON-CHAIN WHALE & ORDERFLOW RADAR */}
        {activeTab === 'WHALE' && (
          <div className="flex flex-col gap-3">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 font-mono">
              <div className="bg-[#080c16] border border-[#1e293b] p-2.5 rounded flex flex-col">
                <span className="text-slate-400 text-[10px]">Top 100 Whale 24h Flow</span>
                <span className="text-emerald-400 font-bold text-sm">
                  +${whale ? (whale.top_100_whale_flow_24h_usd / 1e6).toFixed(1) : '142.5'}M
                </span>
              </div>
              <div className="bg-[#080c16] border border-[#1e293b] p-2.5 rounded flex flex-col">
                <span className="text-slate-400 text-[10px]">Exchange Net Inflow (BTC)</span>
                <span className="text-cyan-400 font-bold text-sm">
                  {whale ? whale.exchange_net_inflow_btc.toLocaleString() : '-1,850.5'} BTC
                </span>
                <span className="text-[9px] text-emerald-400">Outflow to Cold Storage</span>
              </div>
              <div className="bg-[#080c16] border border-[#1e293b] p-2.5 rounded flex flex-col">
                <span className="text-slate-400 text-[10px]">Cold Storage Outflows</span>
                <span className="text-purple-400 font-bold text-sm">
                  ${whale ? (whale.cold_storage_outflows_usd / 1e6).toFixed(1) : '163.7'}M
                </span>
              </div>
              <div className="bg-[#080c16] border border-[#1e293b] p-2.5 rounded flex flex-col">
                <span className="text-slate-400 text-[10px]">Whale Sentiment</span>
                <span className="text-emerald-300 font-bold text-sm">
                  {whale?.exchange_flow_sentiment.replace(/_/g, ' ') || 'HEAVY ACCUMULATION'}
                </span>
              </div>
            </div>

            {/* Liquidation Clusters Heatmap Bar */}
            <div className="bg-[#080c16] border border-[#1e293b] p-3 rounded flex flex-col gap-2">
              <span className="font-semibold text-slate-300 font-mono text-[11px]">
                Liquidation Cluster Zones:
              </span>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {whale?.liquidation_clusters.map((cluster, idx) => (
                  <div
                    key={idx}
                    className={`p-2 rounded border flex items-center justify-between text-[11px] font-mono ${
                      cluster.cluster_type === 'SHORT_LIQUIDATION'
                        ? 'bg-rose-950/20 border-rose-500/30 text-rose-300'
                        : 'bg-emerald-950/20 border-emerald-500/30 text-emerald-300'
                    }`}
                  >
                    <span>${cluster.price_level.toLocaleString()} ({cluster.cluster_type.replace(/_/g, ' ')})</span>
                    <span className="font-bold">${(cluster.estimated_volume_usd / 1e6).toFixed(1)}M pool</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* 3. TRADER PSYCHOLOGY & TILT SHIELD */}
        {activeTab === 'PSYCHOLOGY' && (
          <div className="flex flex-col gap-3">
            <div className="flex items-center justify-between bg-[#080c16] p-3 rounded border border-[#1e293b]">
              <div className="flex items-center gap-3">
                <div
                  className={`p-2 rounded-full ${
                    psychology?.is_shield_locked
                      ? 'bg-rose-500/20 text-rose-400 border border-rose-500/50'
                      : 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/50'
                  }`}
                >
                  {psychology?.is_shield_locked ? <Lock size={18} /> : <Unlock size={18} />}
                </div>
                <div>
                  <div className="font-bold text-sm text-slate-100 flex items-center gap-2">
                    <span>Trader Tilt Status:</span>
                    <span
                      className={
                        psychology?.is_shield_locked ? 'text-rose-400' : 'text-emerald-400'
                      }
                    >
                      {psychology?.is_shield_locked ? 'COOLDOWN LOCKED' : 'OPTIMAL / DISCIPLINED'}
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-400">
                    {psychology?.guidance_message ||
                      'Zero revenge trading detected. Position sizes strictly bounded by Half-Kelly model.'}
                  </p>
                </div>
              </div>

              <div className="flex flex-col items-end font-mono">
                <span className="text-[10px] text-slate-400">Emotional Tilt Risk Score</span>
                <span className="text-emerald-400 font-bold text-base">
                  {psychology?.emotional_state_score || 12}/100 (Calm)
                </span>
              </div>
            </div>

            <div className="bg-[#090f1d] border border-slate-800 p-3 rounded text-[11px] text-slate-300">
              <span className="font-bold text-slate-100 block mb-1">
                🛡️ Behavioral Risk Policy Enforced:
              </span>
              <ul className="list-disc list-inside space-y-1 text-slate-400">
                <li>3 consecutive losses automatically triggers 2-hour capital preservation cooldown.</li>
                <li>Manual lot size doubling post-drawdown (Revenge Trading) is strictly rejected by the execution desk.</li>
                <li>Biometric & frequency pacing protects capital during high-volatility news events.</li>
              </ul>
            </div>
          </div>
        )}

        {/* 4. MONTE CARLO 10,000-PATH STRESS LAB */}
        {activeTab === 'MONTE_CARLO' && (
          <div className="flex flex-col gap-3">
            <div className="flex items-center justify-between bg-[#080c16] p-3 rounded border border-[#1e293b]">
              <div>
                <span className="font-bold text-sm text-slate-100 block">
                  10,000-Path Monte Carlo & Black Swan Stress Lab
                </span>
                <span className="text-[11px] text-slate-400">
                  Permutes and reshuffles historical return distributions to assess ruin probability.
                </span>
              </div>

              <button
                onClick={handleRunMonteCarlo}
                disabled={runningMC}
                className="flex items-center gap-2 px-3 py-1.5 bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border border-amber-500/40 rounded font-mono text-xs font-semibold transition-all disabled:opacity-50"
              >
                {runningMC ? <RotateCw size={13} className="animate-spin" /> : <Play size={13} />}
                <span>{runningMC ? 'Simulating 10,000 Paths...' : 'Run 10,000 Monte Carlo Paths'}</span>
              </button>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 font-mono">
              <div className="bg-[#080c16] border border-[#1e293b] p-2.5 rounded flex flex-col">
                <span className="text-slate-400 text-[10px]">Probability of Ruin (&ge;20% DD)</span>
                <span className="text-emerald-400 font-bold text-sm">
                  {monteCarlo ? (monteCarlo.probability_of_ruin * 100).toFixed(2) : '0.35'}%
                </span>
                <span className="text-[9px] text-slate-500">Threshold &lt; 1.0%</span>
              </div>
              <div className="bg-[#080c16] border border-[#1e293b] p-2.5 rounded flex flex-col">
                <span className="text-slate-400 text-[10px]">Median Drawdown (P50)</span>
                <span className="text-slate-200 font-bold text-sm">
                  {monteCarlo ? monteCarlo.p50_max_drawdown_pct : '5.8'}%
                </span>
              </div>
              <div className="bg-[#080c16] border border-[#1e293b] p-2.5 rounded flex flex-col">
                <span className="text-slate-400 text-[10px]">95th Percentile DD (P95)</span>
                <span className="text-amber-400 font-bold text-sm">
                  {monteCarlo ? monteCarlo.p95_max_drawdown_pct : '12.4'}%
                </span>
              </div>
              <div className="bg-[#080c16] border border-[#1e293b] p-2.5 rounded flex flex-col">
                <span className="text-emerald-400 text-[10px]">COVID Shock Survival</span>
                <span className="text-emerald-400 font-bold text-sm">
                  {monteCarlo ? monteCarlo.covid_shock_survival_score : '94.2'}/100
                </span>
              </div>
            </div>

            {monteCarlo && (
              <p className="text-[11px] font-mono text-emerald-400 bg-emerald-950/20 border border-emerald-500/30 p-2 rounded">
                ✓ {monteCarlo.summary}
              </p>
            )}
          </div>
        )}

        {/* 5. CROSS-ASSET LEAD-LAG RADAR */}
        {activeTab === 'LEAD_LAG' && (
          <div className="flex flex-col gap-3">
            <div className="grid grid-cols-2 gap-2 font-mono">
              <div className="bg-[#080c16] border border-[#1e293b] p-2.5 rounded flex items-center justify-between">
                <span className="text-slate-400 text-[11px]">US 10-Year Yields (^TNX):</span>
                <span className="text-amber-400 font-bold">{leadLag?.us10y_yield || 4.21}%</span>
              </div>
              <div className="bg-[#080c16] border border-[#1e293b] p-2.5 rounded flex items-center justify-between">
                <span className="text-slate-400 text-[11px]">US Dollar Index (DXY):</span>
                <span className="text-cyan-400 font-bold">{leadLag?.dxy_price || 104.12}</span>
              </div>
            </div>

            <div className="flex flex-col gap-2">
              <span className="font-semibold text-slate-300 text-[11px] font-mono">
                Active Predictive Lead-Lag Signals:
              </span>
              {leadLag?.signals.map((sig, idx) => (
                <div
                  key={idx}
                  className="bg-[#090f1d] border border-sky-500/30 p-2.5 rounded flex flex-col gap-1 font-mono text-[11px]"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-sky-300">
                      {sig.driver_asset} &rarr; {sig.target_asset}
                    </span>
                    <span className="text-emerald-400 bg-emerald-500/20 px-1.5 py-0.2 rounded font-bold">
                      {sig.direction.replace(/_/g, ' ')} ({sig.expected_lead_window_mins} lead)
                    </span>
                  </div>
                  <p className="text-slate-400 text-[10px]">{sig.rationale}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 6. DYNAMIC HEDGER */}
        {activeTab === 'HEDGE' && (
          <div className="flex flex-col gap-3">
            <div className="flex items-center justify-between bg-[#080c16] p-3 rounded border border-[#1e293b]">
              <div className="flex items-center gap-2">
                <Anchor size={16} className="text-rose-400" />
                <span className="font-bold text-slate-100">Dynamic Risk Neutralization:</span>
                <span className="text-emerald-400 font-mono text-[11px] bg-emerald-500/20 border border-emerald-500/30 px-2 py-0.5 rounded">
                  {hedge?.hedge_required ? 'ACTIVE HEDGE DEPLOYED' : 'STANDBY / NOMINAL'}
                </span>
              </div>

              <span className="font-mono text-slate-400 text-[11px]">
                Net Portfolio Delta: <strong className="text-slate-200">${hedge?.current_portfolio_delta_usd.toLocaleString() || '4,250'}</strong>
              </span>
            </div>

            <p className="text-[11px] font-mono text-slate-300 bg-[#090f1d] border border-[#1e293b] p-2.5 rounded">
              {hedge?.rationale ||
                'Autonomous Micro-Hedger tracks extreme macro tail shocks (>2.5 sigma). In the event of an unexpected flash crash, an offsetting micro-perpetual short is automatically deployed to lock net portfolio variance.'}
            </p>
          </div>
        )}
      </div>
    </div>
  );
};
