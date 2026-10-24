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
  ExternalLink,
  Eye,
  Zap,
  Bot,
  Crosshair,
  Flame,
} from 'lucide-react';
import { api } from '../services/api';
import { PairVenueLinks } from './PairVenueLinks';

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
  timing_stage?: string;
  reward_to_risk?: number;
  distance_to_invalidation_pct?: number;
  tradingview_url?: string;
  binance_url?: string;
  bybit_url?: string;
  has_active_specialist?: boolean;
}

export interface MastermindSwarmDeskProps {
  onSelectSymbol?: (symbol: string) => void;
  onPrepareTrade?: (opp: OpportunityRecord) => void;
  addToast?: (type: 'success' | 'error' | 'info' | 'warning', title: string, message: string) => void;
}

export const MastermindSwarmDesk: React.FC<MastermindSwarmDeskProps> = ({
  onSelectSymbol,
  onPrepareTrade,
  addToast,
}) => {
  const [status, setStatus] = useState<SwarmStatus | null>(null);
  const [decisions, setDecisions] = useState<DecisionRecord[]>([]);
  const [opportunities, setOpportunities] = useState<OpportunityRecord[]>([]);
  const [selectedCategory, setSelectedCategory] = useState<string>('ALL');
  const [screenerHealth, setScreenerHealth] = useState<any>(null);
  const [radarDesk, setRadarDesk] = useState<any>(null);
  const [executingOpp, setExecutingOpp] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [deployingSymbol, setDeployingSymbol] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
    try {
      setRefreshing(true);
      const [sRes, dRes, oppRes, deskRes] = await Promise.allSettled([
        api.getMastermindStatus(),
        api.getMastermindDecisions(30),
        api.getMastermindOpportunitySignals(),
        api.getMultiDeskSummary(),
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
      if (deskRes.status === 'fulfilled' && deskRes.value?.alpha_radar_desk) {
        setRadarDesk(deskRes.value.alpha_radar_desk);
      }

      if (oppRes.status === 'fulfilled' && oppRes.value?.opportunities) {
        setOpportunities(oppRes.value.opportunities);
        setScreenerHealth(oppRes.value.health);
        hasSuccess = true;
      } else {
        // Fallback to screener opportunities if signals endpoint fails
        try {
          const fallbackOpp = await api.getMarketOpportunities();
          if (fallbackOpp?.opportunities) {
            setOpportunities(fallbackOpp.opportunities);
            setScreenerHealth(fallbackOpp.health);
            hasSuccess = true;
          }
        } catch {
          // ignore fallback error
        }
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

  const handleDeploySpecialist = async (opp: OpportunityRecord) => {
    try {
      setDeployingSymbol(opp.symbol);
      const res = await api.deployMastermindSpecialist({
        symbol: opp.symbol,
        category: opp.opportunity_category,
        direction: opp.recommended_direction,
        invalidation_level: opp.invalidation_level,
        primary_rationale: opp.primary_rationale,
        market_attention_score: opp.market_attention_score,
        timing_stage: opp.timing_stage,
      });

      if (res?.status === 'DEPLOYED') {
        addToast?.('success', 'Swarm Node Deployed', `Deployed Dynamic Specialist Node for ${opp.symbol}`);
        setOpportunities((prev) =>
          prev.map((o) => (o.symbol === opp.symbol ? { ...o, has_active_specialist: true } : o))
        );
        fetchData();
      }
    } catch (err: unknown) {
      console.error('Failed to deploy specialist:', err);
      addToast?.('error', 'Deployment Failed', `Failed to deploy specialist for ${opp.symbol}`);
    } finally {
      setDeployingSymbol(null);
    }
  };

  const handleExecuteRadarTrade = async (opp: OpportunityRecord) => {
    if (opp.quote_volume_24h_usd < 20_000_000) {
      addToast?.('warning', 'Low Liquidity Protection', `${opp.symbol} 24h volume ($${(opp.quote_volume_24h_usd/1e6).toFixed(1)}M) is below the $20M minimum liquidity hurdle.`);
      return;
    }
    try {
      setExecutingOpp(opp.symbol);
      const isShort = opp.opportunity_category === 'BLOW_OFF_EXHAUSTION' || opp.opportunity_category === 'BEARISH_CONTINUATION';
      const direction = isShort ? 'SHORT' : 'LONG';
      const cur_px = opp.current_price;
      let sl = opp.invalidation_level || 0;
      if (direction === 'LONG') {
        if (sl <= 0 || sl >= cur_px || (cur_px - sl) / cur_px > 0.08) sl = cur_px * 0.965;
      } else {
        if (sl <= 0 || sl <= cur_px || (sl - cur_px) / cur_px > 0.08) sl = cur_px * 1.035;
      }
      const stop_dist = Math.abs(cur_px - sl);
      const size = stop_dist > 0 ? Number((20.0 / stop_dist).toFixed(4)) : 1;
      const tp = direction === 'LONG' ? cur_px + stop_dist * 2.2 : cur_px - stop_dist * 2.2;

      const candidate = {
        symbol: opp.symbol,
        direction,
        category: opp.opportunity_category,
        entry_price: cur_px,
        stop_loss: sl,
        take_profit: tp,
        size,
        risk_usd: 20.0,
        volume_24h_usd: opp.quote_volume_24h_usd,
        thesis: `Alpha Radar [${opp.opportunity_category}]: 1-Click execution on $2,000 Alpha Book.`,
      };

      const res = await api.executeRadarAlphaCandidate(candidate);
      if (res?.position_id) {
        addToast?.('success', 'Alpha Desk Execution', `Deployed ${direction} ${opp.symbol} on $2,000 Book (Risk: $20.00). ID: ${res.position_id}`);
        fetchData();
      }
    } catch (err: any) {
      addToast?.('error', 'Execution Error', err?.message || 'Could not place trade on $2,000 Alpha Desk.');
    } finally {
      setExecutingOpp(null);
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
                <span className="text-slate-500">Venue:</span>
                <PairVenueLinks symbol={spec.symbol} size="xs" isFutures={true} />
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

        {/* Alpha Radar Satellite Desk ($2,000 Isolated Book) Status Card */}
        <div className="bg-gradient-to-r from-cyan-950/40 via-slate-900/60 to-purple-950/40 border border-cyan-800/40 rounded-lg p-3 flex flex-wrap items-center justify-between gap-3 shadow-md">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center text-cyan-400 font-bold text-xs">
              $2K
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold text-white tracking-wide">ALPHA RADAR SATELLITE DESK</span>
                <span className="text-[9px] bg-cyan-900/60 text-cyan-300 border border-cyan-700/50 px-1.5 py-0.2 rounded font-mono font-semibold">
                  ISOLATED BOOK
                </span>
              </div>
              <p className="text-[10px] text-slate-400">
                Dedicated $2,000 allocation for 700+ Coin Discovery. Sized strictly at $20 (1.0%) risk per trade. Completely isolated from the $10,000 Main Desk.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-4 text-xs font-mono">
            <div>
              <span className="text-[9px] text-slate-500 uppercase block">ALLOCATED</span>
              <span className="font-bold text-slate-200">${radarDesk?.allocated_capital_usd?.toLocaleString() || '2,000.00'}</span>
            </div>
            <div className="h-6 w-[1px] bg-slate-800" />
            <div>
              <span className="text-[9px] text-slate-500 uppercase block">LIVE EQUITY</span>
              <span className="font-bold text-cyan-300">${radarDesk?.virtual_equity_usd ? radarDesk.virtual_equity_usd.toFixed(2) : '2,000.00'}</span>
            </div>
            <div className="h-6 w-[1px] bg-slate-800" />
            <div>
              <span className="text-[9px] text-slate-500 uppercase block">ACTIVE POSITIONS</span>
              <span className="font-bold text-amber-400">{radarDesk?.open_positions_count ?? 0} / 2</span>
            </div>
            <div className="h-6 w-[1px] bg-slate-800" />
            <div>
              <span className="text-[9px] text-slate-500 uppercase block">MIN VOLUME</span>
              <span className="font-semibold text-emerald-400">≥ $20M</span>
            </div>
          </div>
        </div>

        {/* Filter Tabs */}
        <div className="flex flex-wrap items-center gap-1.5 pt-1">
          {[
            { id: 'ALL', label: 'All Qualified', count: opportunities.length },
            {
              id: 'PRE_BREAKOUT_COMPRESSION',
              label: '⏳ Pre-Breakout Long',
              count: opportunities.filter((o) => o.opportunity_category === 'PRE_BREAKOUT_COMPRESSION').length,
            },
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
            {
              id: 'BEARISH_CONTINUATION',
              label: '📉 Breakdown Shorts',
              count: opportunities.filter((o) => o.opportunity_category === 'BEARISH_CONTINUATION').length,
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
                <th className="py-2 px-3">Direction & Stage</th>
                <th className="py-2 px-3">Price / 24h Change</th>
                <th className="py-2 px-3">24h Vol / RVOL</th>
                <th className="py-2 px-3">Spread & Risk</th>
                <th className="py-2 px-3">Market Attention</th>
                <th className="py-2 px-3">Category & Rationale</th>
                <th className="py-2 px-3">Invalidation</th>
                <th className="py-2 px-3 text-right">Direct Links & Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#1e293b]/60">
              {opportunities.filter((o) => selectedCategory === 'ALL' || o.opportunity_category === selectedCategory).length === 0 ? (
                <tr>
                  <td colSpan={10} className="py-8 text-center text-slate-500 text-xs">
                    {loading ? 'Discovering active market opportunities...' : 'No opportunities matching selected category.'}
                  </td>
                </tr>
              ) : (
                opportunities
                  .filter((o) => selectedCategory === 'ALL' || o.opportunity_category === selectedCategory)
                  .slice(0, 20)
                  .map((opp) => (
                    <tr key={opp.symbol} className="hover:bg-[#131b2e] transition-colors">
                      <td className="py-2.5 px-3 whitespace-nowrap">
                        <div className="flex flex-col gap-1.5">
                          <div className="flex items-center gap-1.5">
                            <button
                              onClick={() => onSelectSymbol?.(opp.symbol.replace('/', ''))}
                              className="font-bold text-white text-xs hover:text-cyan-400 hover:underline transition-colors flex items-center gap-1 text-left"
                              title="Click to load into CBT Cockpit Chart"
                            >
                              <span>{opp.symbol}</span>
                              <Crosshair size={11} className="text-slate-500 hover:text-cyan-400" />
                            </button>
                            <span className="text-[9px] bg-slate-800 text-slate-400 px-1 py-0.5 rounded font-mono">
                              {opp.base_asset}
                            </span>
                            <a
                              href={
                                opp.tradingview_url ||
                                `https://www.tradingview.com/chart/?symbol=BINANCE:${opp.symbol.replace('/', '')}${
                                  opp.futures_eligible ? '.P' : ''
                                }`
                              }
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-cyan-400 hover:text-cyan-300 transition-colors p-0.5"
                              title="Open TradingView Chart in new tab"
                            >
                              <ExternalLink size={11} />
                            </a>
                          </div>

                          {/* 1-Click Direct Venue Badges right in Column 1 */}
                          <PairVenueLinks symbol={opp.symbol} size="xs" isFutures={opp.futures_eligible} />
                        </div>
                      </td>

                      <td className="py-2.5 px-3 whitespace-nowrap">
                        <div className="flex items-center gap-1">
                          {opp.spot_eligible && (
                            <a
                              href={opp.binance_url || `https://www.binance.com/en/trade/${opp.base_asset}_USDT`}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-[9px] bg-blue-500/10 hover:bg-blue-500/20 text-blue-400 hover:text-blue-300 border border-blue-500/30 px-1.5 py-0.5 rounded font-semibold transition-all inline-flex items-center gap-0.5"
                              title="Open Binance Spot Market"
                            >
                              <span>SPOT</span>
                              <ExternalLink size={8} />
                            </a>
                          )}
                          {opp.futures_eligible && (
                            <a
                              href={opp.binance_url || `https://www.binance.com/en/futures/${opp.base_asset}USDT`}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-[9px] bg-purple-500/10 hover:bg-purple-500/20 text-purple-400 hover:text-purple-300 border border-purple-500/30 px-1.5 py-0.5 rounded font-semibold transition-all inline-flex items-center gap-0.5"
                              title="Open Binance Futures Market"
                            >
                              <span>FUTURES</span>
                              <ExternalLink size={8} />
                            </a>
                          )}
                        </div>
                      </td>

                      <td className="py-2.5 px-3 whitespace-nowrap">
                        <div className="flex flex-col gap-1 items-start">
                          {opp.recommended_direction === 'LONG' ? (
                            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 rounded text-[9px] font-bold">
                              <TrendingUp size={10} /> LONG
                            </span>
                          ) : opp.recommended_direction === 'SHORT' ? (
                            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 bg-rose-500/10 text-rose-400 border border-rose-500/30 rounded text-[9px] font-bold">
                              <TrendingDown size={10} /> SHORT
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 bg-amber-500/10 text-amber-400 border border-amber-500/30 rounded text-[9px] font-bold">
                              <Activity size={10} /> WATCH
                            </span>
                          )}
                          <span
                            className={`inline-flex items-center px-1.5 py-0.2 rounded text-[8px] font-bold uppercase tracking-wider ${
                              opp.timing_stage === 'PRE_SPIKE'
                                ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/30'
                                : opp.timing_stage === 'EARLY'
                                ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                                : opp.timing_stage === 'EXHAUSTED'
                                ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                                : 'bg-slate-800 text-slate-300 border border-slate-700'
                            }`}
                          >
                            {opp.timing_stage || 'ACTIVE'}
                          </span>
                        </div>
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

                      <td className="py-2.5 px-3 whitespace-nowrap">
                        <div className="flex flex-col">
                          <span className="text-[11px] font-mono text-slate-300">
                            {opp.estimated_spread_bps.toFixed(1)} bps
                          </span>
                          <span className="text-[10px] text-slate-500 font-mono">
                            Dist: {opp.distance_to_invalidation_pct ? `${opp.distance_to_invalidation_pct.toFixed(1)}%` : '—'}
                          </span>
                        </div>
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

                      <td className="py-2.5 px-3 whitespace-nowrap text-right">
                        <div className="flex items-center justify-end gap-1.5">
                          {/* TradingView Chart Link */}
                          <a
                            href={
                              opp.tradingview_url ||
                              `https://www.tradingview.com/chart/?symbol=BINANCE:${opp.symbol.replace('/', '')}${
                                opp.futures_eligible ? '.P' : ''
                              }`
                            }
                            target="_blank"
                            rel="noopener noreferrer"
                            className="px-2 py-1 bg-[#1e293b] hover:bg-[#334155] text-cyan-300 hover:text-cyan-200 border border-slate-700 hover:border-cyan-500/40 rounded text-[10px] font-bold flex items-center gap-1 transition-all shadow-sm"
                            title="Open TradingView Chart in new tab"
                          >
                            <ExternalLink size={10} />
                            <span>TV</span>
                          </a>

                          {/* Binance Exchange Market Link */}
                          <a
                            href={
                              opp.binance_url ||
                              (opp.futures_eligible
                                ? `https://www.binance.com/en/futures/${opp.base_asset}USDT`
                                : `https://www.binance.com/en/trade/${opp.base_asset}_USDT`)
                            }
                            target="_blank"
                            rel="noopener noreferrer"
                            className="px-2 py-1 bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 hover:text-amber-200 border border-amber-500/30 rounded text-[10px] font-bold flex items-center gap-1 transition-all shadow-sm"
                            title="Open Binance Exchange in new tab"
                          >
                            <ExternalLink size={10} />
                            <span>Binance</span>
                          </a>

                          {/* Bybit Secondary Venue Link */}
                          <a
                            href={opp.bybit_url || `https://www.bybit.com/trade/usdt/${opp.base_asset}USDT`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="px-1.5 py-1 bg-slate-900 hover:bg-slate-800 text-slate-300 hover:text-white border border-slate-700 rounded text-[10px] font-semibold flex items-center gap-1 transition-all"
                            title="Open Bybit Market in new tab"
                          >
                            <ExternalLink size={10} />
                            <span>Bybit</span>
                          </a>

                          {/* Cockpit Load Action */}
                          <button
                            onClick={() => onSelectSymbol?.(opp.symbol.replace('/', ''))}
                            className="px-2 py-1 bg-sky-500/10 hover:bg-sky-500/20 text-sky-400 border border-sky-500/30 rounded text-[10px] font-bold flex items-center gap-1 transition-all"
                            title="Load pair into CBT Cockpit Chart"
                          >
                            <Eye size={10} />
                            <span>Cockpit</span>
                          </button>

                          {/* Pre-fill Trade Ticket */}
                          <button
                            onClick={() => onPrepareTrade?.(opp)}
                            className="px-2 py-1 bg-purple-500/10 hover:bg-purple-500/20 text-purple-400 border border-purple-500/30 rounded text-[10px] font-bold flex items-center gap-1 transition-all"
                            title="Pre-fill Risk-First Trade Ticket"
                          >
                            <Zap size={10} />
                            <span>Ticket</span>
                          </button>

                          {/* Deploy Dynamic Specialist */}
                          <button
                            onClick={() => handleDeploySpecialist(opp)}
                            disabled={deployingSymbol === opp.symbol || opp.has_active_specialist}
                            className={`px-2 py-1 rounded text-[10px] font-bold flex items-center gap-1 transition-all border ${
                              opp.has_active_specialist
                                ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40 cursor-default'
                                : 'bg-indigo-500/10 hover:bg-indigo-500/20 text-indigo-400 border-indigo-500/30'
                            }`}
                            title={
                              opp.has_active_specialist
                                ? 'Specialist Active in Swarm'
                                : 'Deploy Dynamic Specialist Node into Swarm'
                            }
                          >
                            <Bot size={10} className={deployingSymbol === opp.symbol ? 'animate-spin' : ''} />
                            <span>{opp.has_active_specialist ? 'Active' : 'Deploy'}</span>
                          </button>

                          {/* 1-Click Alpha Radar Desk Trade ($2,000 Book) */}
                          <button
                            onClick={() => handleExecuteRadarTrade(opp)}
                            disabled={
                              executingOpp === opp.symbol ||
                              (radarDesk ? radarDesk.open_positions_count >= 2 : false) ||
                              !opp.futures_eligible
                            }
                            className={`px-2 py-1 rounded text-[10px] font-bold flex items-center gap-1 transition-all border ${
                              !opp.futures_eligible
                                ? 'bg-slate-800/40 text-slate-600 border-slate-700/50 cursor-not-allowed'
                                : (radarDesk ? radarDesk.open_positions_count >= 2 : false)
                                ? 'bg-amber-950/20 text-amber-500/60 border-amber-800/30 cursor-not-allowed'
                                : 'bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border-amber-500/50 hover:shadow-sm hover:shadow-amber-500/20'
                            }`}
                            title={
                              !opp.futures_eligible
                                ? 'Not eligible for Binance Futures'
                                : (radarDesk ? radarDesk.open_positions_count >= 2 : false)
                                ? 'Radar Desk Full (Max 2 concurrent positions)'
                                : `Execute 1-Click Alpha Radar Trade ($20 Risk / $2,000 Book)`
                            }
                          >
                            <Flame size={10} className={executingOpp === opp.symbol ? 'animate-spin' : ''} />
                            <span>{executingOpp === opp.symbol ? 'Trading...' : '⚡ $2K Trade'}</span>
                          </button>
                        </div>
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
                      <div className="flex items-center gap-2">
                        <span>{dec.symbol}</span>
                        <PairVenueLinks symbol={dec.symbol} size="xs" isFutures={true} />
                      </div>
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
