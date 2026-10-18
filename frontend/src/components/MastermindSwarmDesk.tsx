import React, { useState, useEffect } from 'react';
import {
  Cpu,
  RefreshCw,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  TrendingUp,
  TrendingDown,
  Layers,
  Terminal,
  Radar,
  Activity,
} from 'lucide-react';
import { api } from '../services/api';

interface SpecialistInfo {
  specialist_id: string;
  symbol: string;
  archetype: string;
}

interface DecisionRecord {
  decision_id: string;
  proposal_id: string;
  specialist_id: string;
  symbol: string;
  direction: string;
  is_approved: number;
  rejection_reason: string | null;
  approved_notional_usd: number;
  confidence_score: number;
  expected_value_r: number;
  portfolio_equity_usd: number;
  timestamp_ms: number;
}

interface SwarmStatus {
  status: string;
  account_equity_usd: number;
  total_realized_pnl: number;
  open_positions_count: number;
  specialists_count: number;
  specialists: SpecialistInfo[];
}

export interface OpportunityRecord {
  symbol: string;
  base_asset: string;
  quote_asset: string;
  spot_eligible: boolean;
  futures_eligible: boolean;
  current_price: number;
  price_change_24h_pct: number;
  quote_volume_24h_usd: number;
  trade_count_24h: number;
  estimated_spread_bps: number;
  relative_volume_ratio: number;
  market_attention_score: number;
  trade_quality_score: number;
  attention_state: string;
  opportunity_category: string;
  recommended_venue: string;
  recommended_direction: string;
  primary_rationale: string;
  invalidation_level: number | null;
  observation_timestamp_ms: number;
}

export const MastermindSwarmDesk: React.FC = () => {
  const [status, setStatus] = useState<SwarmStatus | null>(null);
  const [decisions, setDecisions] = useState<DecisionRecord[]>([]);
  const [opportunities, setOpportunities] = useState<OpportunityRecord[]>([]);
  const [selectedCategory, setSelectedCategory] = useState<string>('ALL');
  const [screenerHealth, setScreenerHealth] = useState<any>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
    try {
      setRefreshing(true);
      const [sRes, dRes, oppRes] = await Promise.allSettled([
        api.getMastermindStatus(),
        api.getMastermindDecisions(30),
        api.getMarketOpportunities(),
      ]);

      let hasSuccess = false;

      if (sRes.status === 'fulfilled' && sRes.value) {
        setStatus(sRes.value);
        hasSuccess = true;
      }
      if (dRes.status === 'fulfilled' && dRes.value?.decisions) {
        setDecisions(dRes.value.decisions);
        hasSuccess = true;
      }
      if (oppRes.status === 'fulfilled' && oppRes.value?.opportunities) {
        setOpportunities(oppRes.value.opportunities);
        setScreenerHealth(oppRes.value.health);
        hasSuccess = true;
      }

      if (hasSuccess) {
        setError(null);
      } else {
        setError('Could not connect to Mastermind Swarm API.');
      }
    } catch (err: unknown) {
      console.error('Failed to load Mastermind swarm data:', err);
      setError('Could not connect to Mastermind Swarm API.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10000); // 10s auto-refresh
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="max-w-[1920px] w-full mx-auto p-4 flex flex-col gap-4 font-mono text-slate-200">
      {/* Top Banner: Mastermind Council HUD */}
      <div className="bg-[#0b0e17] border border-[#1e293b] rounded-lg p-4 flex flex-wrap items-center justify-between gap-4 shadow-lg shadow-black/40">
        <div className="flex items-center gap-3">
          <div className="p-2.5 bg-gradient-to-tr from-indigo-500/20 to-purple-500/20 border border-purple-500/30 rounded-lg text-purple-400">
            <Cpu size={24} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-lg font-bold text-white tracking-wide">
                MASTERMIND ARBITER COUNCIL & SPECIALIST SWARM
              </h1>
              <span className="px-2 py-0.5 text-[10px] bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 rounded font-semibold">
                DARWINIAN 1-COIN LEAGUE
              </span>
            </div>
            <p className="text-xs text-slate-400">
              Autonomous asset specialists proposal council governed strictly by Half-Kelly & Daily Drawdown limits.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-6">
          <div className="text-right">
            <div className="text-[10px] text-slate-400">PORTFOLIO VIRTUAL EQUITY</div>
            <div className="text-base font-bold text-cyan-400">
              ${status?.account_equity_usd ? status.account_equity_usd.toLocaleString(undefined, { minimumFractionDigits: 2 }) : '10,000.00'}
            </div>
          </div>
          <div className="text-right">
            <div className="text-[10px] text-slate-400">ACTIVE SPECIALISTS</div>
            <div className="text-base font-bold text-purple-400">
              {status?.specialists_count ?? 5} Swarm Nodes
            </div>
          </div>
          <div className="text-right">
            <div className="text-[10px] text-slate-400">SHADOW POSITIONS</div>
            <div className="text-base font-bold text-amber-400">
              {status?.open_positions_count ?? 0} Open
            </div>
          </div>

          <button
            onClick={fetchData}
            disabled={refreshing}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-[#1e293b] hover:bg-[#334155] border border-slate-700 rounded text-xs text-slate-200 transition-all font-semibold"
          >
            <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />
            <span>Sync</span>
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 text-red-400 text-xs flex items-center gap-2">
          <AlertTriangle size={16} />
          <span>{error}</span>
        </div>
      )}

      {/* Specialist Arena Grid */}
      <div>
        <h2 className="text-xs font-bold text-slate-400 tracking-wider mb-2 flex items-center gap-2">
          <Layers size={14} className="text-cyan-400" />
          ACTIVE SPECIALIST ARENA (CANDIDATE GENERATORS)
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-3">
          {status?.specialists.map((spec) => (
            <div
              key={spec.specialist_id}
              className="bg-[#0f1422] border border-[#1e293b] rounded-lg p-3.5 flex flex-col justify-between hover:border-slate-700 transition-all shadow-sm"
            >
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-bold text-white bg-slate-800/80 px-2 py-0.5 rounded border border-slate-700">
                    {spec.symbol}
                  </span>
                  <span className="flex items-center gap-1 text-[10px] text-emerald-400">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                    ACTIVE
                  </span>
                </div>
                <div className="text-[11px] font-bold text-purple-300 mb-1">{spec.specialist_id}</div>
                <div className="text-[10px] text-slate-400 leading-relaxed mb-3">
                  {spec.archetype.replace(/_/g, ' ')}
                </div>
              </div>

              <div className="pt-2 border-t border-slate-800/60 flex items-center justify-between text-[10px]">
                <span className="text-slate-500">Allocation:</span>
                <span className="text-slate-300 font-semibold">Half-Kelly Dynamic</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* DYNAMIC MARKET OPPORTUNITY RADAR (700+ PAIRS AUTO-DISCOVERY) */}
      <div className="bg-[#0b0e17] border border-[#1e293b] rounded-lg p-4 flex flex-col gap-3 shadow-lg shadow-black/40">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#1e293b] pb-3">
          <div className="flex items-center gap-2.5">
            <Radar size={16} className="text-cyan-400" />
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-xs font-bold text-white tracking-wider">
                  DYNAMIC MARKET OPPORTUNITY RADAR (700+ COIN DISCOVERY)
                </h2>
                <span className="text-[9px] bg-cyan-950 text-cyan-400 border border-cyan-800/60 px-1.5 py-0.2 rounded font-semibold">
                  LIVE 24H SCAN
                </span>
              </div>
              <p className="text-[10px] text-slate-400 mt-0.5">
                Continuously screens Binance Spot & Futures for abnormal volume inflow (RVOL ≥ 1.5x), breakouts, oversold reclaims, and exhaustion reversals.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {screenerHealth && (
              <span className="text-[10px] text-slate-400 bg-slate-900 px-2 py-1 rounded border border-slate-800">
                Scanned: <span className="text-slate-200 font-bold">{screenerHealth.total_spot_pairs_scanned} Spot / {screenerHealth.total_futures_pairs_scanned} Futures</span>
              </span>
            )}
            <button
              onClick={() => {
                setRefreshing(true);
                api.getMarketOpportunities(undefined, true).then((res) => {
                  if (res?.opportunities) {
                    setOpportunities(res.opportunities);
                    setScreenerHealth(res.health);
                  }
                  setRefreshing(false);
                });
              }}
              disabled={refreshing}
              className="flex items-center gap-1 px-2 py-1 bg-slate-800 hover:bg-slate-700 text-slate-200 text-[10px] font-bold rounded border border-slate-700 transition-colors"
            >
              <RefreshCw size={11} className={refreshing ? 'animate-spin text-cyan-400' : 'text-slate-400'} />
              {refreshing ? 'Scanning...' : 'Scan Now'}
            </button>
          </div>
        </div>

        {/* Filter Tabs */}
        <div className="flex flex-wrap items-center gap-1.5 pt-1">
          {[
            { id: 'ALL', label: 'All Qualified', count: opportunities.length },
            {
              id: 'EMERGING_MOMENTUM',
              label: '🚀 Momentum Gainers',
              count: opportunities.filter((o) => o.opportunity_category === 'EMERGING_MOMENTUM').length,
            },
            {
              id: 'CONFIRMED_BREAKOUT',
              label: '⚡ Breakouts',
              count: opportunities.filter((o) => o.opportunity_category === 'CONFIRMED_BREAKOUT').length,
            },
            {
              id: 'CAPITULATION_RECOVERY',
              label: '🛡️ Oversold Reclaims',
              count: opportunities.filter((o) => o.opportunity_category === 'CAPITULATION_RECOVERY').length,
            },
            {
              id: 'BLOW_OFF_EXHAUSTION',
              label: '🔻 Exhaustion Shorts',
              count: opportunities.filter((o) => o.opportunity_category === 'BLOW_OFF_EXHAUSTION').length,
            },
          ].map((tab) => {
            const isSelected = selectedCategory === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setSelectedCategory(tab.id)}
                className={`px-2.5 py-1 rounded text-[10px] font-bold transition-all flex items-center gap-1.5 ${
                  isSelected
                    ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-sm'
                    : 'bg-slate-900/60 text-slate-400 hover:text-slate-200 border border-slate-800'
                }`}
              >
                <span>{tab.label}</span>
                <span
                  className={`px-1 py-0.2 rounded text-[9px] ${
                    isSelected ? 'bg-cyan-400/20 text-cyan-200' : 'bg-slate-800 text-slate-400'
                  }`}
                >
                  {tab.count}
                </span>
              </button>
            );
          })}
        </div>

        {/* Opportunities Table */}
        <div className="overflow-x-auto mt-1 border border-slate-800/80 rounded-lg">
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="border-b border-[#1e293b] bg-slate-950/60 text-slate-400 text-[10px] uppercase">
                <th className="py-2 px-3">Symbol / Base</th>
                <th className="py-2 px-3">Venues</th>
                <th className="py-2 px-3">Direction</th>
                <th className="py-2 px-3">Price / 24h Change</th>
                <th className="py-2 px-3">24h Vol / RVOL</th>
                <th className="py-2 px-3">Spread</th>
                <th className="py-2 px-3">Market Attention</th>
                <th className="py-2 px-3">Category & Rationale</th>
                <th className="py-2 px-3">Invalidation</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#1e293b]/60">
              {opportunities.filter((o) => selectedCategory === 'ALL' || o.opportunity_category === selectedCategory).length === 0 ? (
                <tr>
                  <td colSpan={9} className="py-8 text-center text-slate-500 text-xs">
                    {loading ? 'Discovering active market opportunities...' : 'No opportunities matching selected category.'}
                  </td>
                </tr>
              ) : (
                opportunities
                  .filter((o) => selectedCategory === 'ALL' || o.opportunity_category === selectedCategory)
                  .slice(0, 15)
                  .map((opp) => (
                    <tr key={opp.symbol} className="hover:bg-[#131b2e] transition-colors">
                      <td className="py-2.5 px-3 whitespace-nowrap">
                        <div className="flex items-center gap-1.5">
                          <span className="font-bold text-white text-xs">{opp.symbol}</span>
                          <span className="text-[9px] bg-slate-800 text-slate-400 px-1 py-0.5 rounded font-mono">
                            {opp.base_asset}
                          </span>
                        </div>
                      </td>

                      <td className="py-2.5 px-3 whitespace-nowrap">
                        <div className="flex items-center gap-1">
                          {opp.spot_eligible && (
                            <span className="text-[9px] bg-blue-500/10 text-blue-400 border border-blue-500/30 px-1.5 py-0.2 rounded font-semibold">
                              SPOT
                            </span>
                          )}
                          {opp.futures_eligible && (
                            <span className="text-[9px] bg-purple-500/10 text-purple-400 border border-purple-500/30 px-1.5 py-0.2 rounded font-semibold">
                              FUTURES
                            </span>
                          )}
                        </div>
                      </td>

                      <td className="py-2.5 px-3 whitespace-nowrap">
                        {opp.recommended_direction === 'LONG' ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 rounded text-[10px] font-bold">
                            <TrendingUp size={11} /> LONG
                          </span>
                        ) : opp.recommended_direction === 'SHORT' ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-rose-500/10 text-rose-400 border border-rose-500/30 rounded text-[10px] font-bold">
                            <TrendingDown size={11} /> SHORT
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-amber-500/10 text-amber-400 border border-amber-500/30 rounded text-[10px] font-bold">
                            <Activity size={11} /> WATCH
                          </span>
                        )}
                      </td>

                      <td className="py-2.5 px-3 whitespace-nowrap">
                        <div className="flex flex-col">
                          <span className="font-mono text-xs font-semibold text-slate-200">
                            ${opp.current_price >= 1 ? opp.current_price.toFixed(opp.current_price >= 1000 ? 2 : 4) : opp.current_price.toFixed(6)}
                          </span>
                          <span
                            className={`text-[10px] font-bold font-mono ${
                              opp.price_change_24h_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'
                            }`}
                          >
                            {opp.price_change_24h_pct >= 0 ? `+${opp.price_change_24h_pct.toFixed(2)}%` : `${opp.price_change_24h_pct.toFixed(2)}%`}
                          </span>
                        </div>
                      </td>

                      <td className="py-2.5 px-3 whitespace-nowrap">
                        <div className="flex flex-col">
                          <span className="font-mono text-[11px] text-slate-300 font-semibold">
                            ${(opp.quote_volume_24h_usd / 1e6).toFixed(1)}M
                          </span>
                          <span className="text-[10px] text-cyan-400 font-mono">
                            {opp.relative_volume_ratio.toFixed(1)}x RVOL
                          </span>
                        </div>
                      </td>

                      <td className="py-2.5 px-3 whitespace-nowrap text-[11px] font-mono text-slate-300">
                        {opp.estimated_spread_bps.toFixed(1)} bps
                      </td>

                      <td className="py-2.5 px-3 whitespace-nowrap">
                        <div className="flex flex-col gap-1 w-20">
                          <div className="flex items-center justify-between text-[10px]">
                            <span className="font-bold text-amber-400">{opp.market_attention_score}</span>
                            <span className="text-slate-500 text-[9px]">/ 100</span>
                          </div>
                          <div className="w-full bg-slate-800 rounded-full h-1.5 overflow-hidden">
                            <div
                              className="bg-gradient-to-r from-cyan-500 to-amber-400 h-1.5 rounded-full"
                              style={{ width: `${Math.min(opp.market_attention_score, 100)}%` }}
                            ></div>
                          </div>
                        </div>
                      </td>

                      <td className="py-2.5 px-3 text-[11px] text-slate-300 max-w-sm truncate" title={opp.primary_rationale}>
                        <div className="flex items-center gap-1.5">
                          <span className="text-[9px] bg-slate-800 px-1 py-0.2 rounded text-slate-400 font-mono">
                            {opp.opportunity_category.replace(/_/g, ' ')}
                          </span>
                          <span className="truncate">{opp.primary_rationale}</span>
                        </div>
                      </td>

                      <td className="py-2.5 px-3 whitespace-nowrap font-mono text-[11px] text-rose-300">
                        {opp.invalidation_level ? `$${opp.invalidation_level >= 1 ? opp.invalidation_level.toFixed(opp.invalidation_level >= 1000 ? 2 : 4) : opp.invalidation_level.toFixed(6)}` : '—'}
                      </td>
                    </tr>
                  ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Central Arbiter Decision Ledger */}
      <div className="bg-[#0b0e17] border border-[#1e293b] rounded-lg p-4 flex flex-col gap-3 shadow-lg shadow-black/40">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Terminal size={16} className="text-cyan-400" />
            <h2 className="text-xs font-bold text-white tracking-wider">
              CENTRAL ARBITER DECISION & AUDIT LEDGER (LAST 30 PROPOSALS)
            </h2>
          </div>
          <span className="text-[10px] text-slate-400">
            Immutable SQLite records (`mastermind_decisions`)
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="border-b border-[#1e293b] text-slate-400 text-[10px] uppercase">
                <th className="py-2 px-3">Time</th>
                <th className="py-2 px-3">Specialist</th>
                <th className="py-2 px-3">Symbol</th>
                <th className="py-2 px-3">Direction</th>
                <th className="py-2 px-3">Status</th>
                <th className="py-2 px-3">Confidence</th>
                <th className="py-2 px-3">Expected EV</th>
                <th className="py-2 px-3">Approved Size</th>
                <th className="py-2 px-3">Arbiter Rationale / Rejection Reason</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#1e293b]/60">
              {decisions.length === 0 ? (
                <tr>
                  <td colSpan={9} className="py-8 text-center text-slate-500 text-xs">
                    {loading ? 'Polling Mastermind Arbiter Council...' : 'No candidate proposals submitted yet.'}
                  </td>
                </tr>
              ) : (
                decisions.map((dec) => (
                  <tr key={dec.decision_id} className="hover:bg-[#131b2e] transition-colors">
                    <td className="py-2.5 px-3 text-slate-400 text-[11px] whitespace-nowrap">
                      {new Date(dec.timestamp_ms).toLocaleTimeString()}
                    </td>
                    <td className="py-2.5 px-3 text-slate-300 font-medium whitespace-nowrap">
                      {dec.specialist_id}
                    </td>
                    <td className="py-2.5 px-3 font-bold text-white whitespace-nowrap">
                      {dec.symbol}
                    </td>
                    <td className="py-2.5 px-3 whitespace-nowrap">
                      {dec.direction === 'LONG' ? (
                        <span className="flex items-center gap-1 text-emerald-400 font-bold">
                          <TrendingUp size={12} /> LONG
                        </span>
                      ) : dec.direction === 'SHORT' ? (
                        <span className="flex items-center gap-1 text-rose-400 font-bold">
                          <TrendingDown size={12} /> SHORT
                        </span>
                      ) : (
                        <span className="text-slate-500 font-medium">NEUTRAL</span>
                      )}
                    </td>
                    <td className="py-2.5 px-3 whitespace-nowrap">
                      {dec.is_approved === 1 ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 rounded text-[10px] font-bold">
                          <CheckCircle2 size={12} /> APPROVED
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-rose-500/10 text-rose-400 border border-rose-500/30 rounded text-[10px] font-bold">
                          <XCircle size={12} /> REJECTED
                        </span>
                      )}
                    </td>
                    <td className="py-2.5 px-3 text-slate-300 font-semibold whitespace-nowrap">
                      {(dec.confidence_score * 100).toFixed(0)}%
                    </td>
                    <td className="py-2.5 px-3 text-cyan-400 font-bold whitespace-nowrap">
                      {dec.expected_value_r > 0 ? `+${dec.expected_value_r.toFixed(2)}R` : `${dec.expected_value_r.toFixed(2)}R`}
                    </td>
                    <td className="py-2.5 px-3 text-emerald-400 font-bold whitespace-nowrap">
                      {dec.approved_notional_usd > 0 ? `$${dec.approved_notional_usd.toFixed(2)}` : '$0.00'}
                    </td>
                    <td className="py-2.5 px-3 text-slate-400 text-[11px] max-w-xs truncate" title={dec.rejection_reason || 'Passed all deterministic risk gates'}>
                      {dec.rejection_reason || 'Passed Risk Gates (Half-Kelly & Drawdown OK)'}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
