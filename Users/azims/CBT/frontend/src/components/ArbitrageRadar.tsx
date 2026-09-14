import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Activity,
  Clock,
  Coins,
  Cpu,
  FileCheck2,
  Layers,
  Percent,
  RefreshCw,
  Scale,
  ShieldCheck,
  Zap,
} from 'lucide-react';
import {
  api,
  ArbitrageDislocationsResponse,
  ArbitrageHealthResponse,
  ArbitrageOpportunityItem,
  FundingMatrixItem,
  ShadowTradeRecord,
} from '../services/api';

interface ArbitrageRadarProps {
  currentSymbol?: string;
  onNotify?: (type: 'success' | 'error' | 'warning' | 'info', title: string, message: string) => void;
}

const SUPPORTED_SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'PAXGUSDT'];

export const ArbitrageRadar: React.FC<ArbitrageRadarProps> = ({
  currentSymbol = 'BTCUSDT',
  onNotify,
}) => {
  const [symbol, setSymbol] = useState<string>(
    SUPPORTED_SYMBOLS.find(s => s === currentSymbol.replace('/', '').toUpperCase()) || 'BTCUSDT'
  );
  const [loading, setLoading] = useState<boolean>(true);
  const [dislocations, setDislocations] = useState<ArbitrageDislocationsResponse | null>(null);
  const [fundingMatrix, setFundingMatrix] = useState<FundingMatrixItem[]>([]);
  const [opportunities, setOpportunities] = useState<ArbitrageOpportunityItem[]>([]);
  const [history, setHistory] = useState<ShadowTradeRecord[]>([]);
  const [health, setHealth] = useState<ArbitrageHealthResponse | null>(null);
  const [selectedProvenanceId, setSelectedProvenanceId] = useState<string | null>(null);
  const [provenanceData, setProvenanceData] = useState<any | null>(null);
  const [loadingProvenance, setLoadingProvenance] = useState<boolean>(false);
  const [lastUpdated, setLastUpdated] = useState<Date>(new Date());
  const [activeTab, setActiveTab] = useState<'OVERVIEW' | 'FUNDING' | 'BASIS' | 'CAPACITY' | 'SHADOW'>(
    'OVERVIEW'
  );

  const onNotifyRef = useRef(onNotify);
  useEffect(() => {
    onNotifyRef.current = onNotify;
  }, [onNotify]);

  const fetchData = useCallback(async () => {
    try {
      const [dislocRes, fundRes, oppsRes, histRes, healthRes] = await Promise.all([
        api.getArbitrageDislocations(symbol),
        api.getFundingMatrix(symbol),
        api.getArbitrageOpportunities(symbol),
        api.getArbitrageHistory(30),
        api.getArbitrageHealth(),
      ]);

      setDislocations(dislocRes);
      setFundingMatrix(fundRes.matrix || []);
      setOpportunities(oppsRes.opportunities || []);
      setHistory(histRes.shadow_records || []);
      setHealth(healthRes);
      setLastUpdated(new Date());
    } catch (err: any) {
      console.error('Failed fetching arbitrage sentinel data:', err);
      onNotifyRef.current?.('error', 'Arbitrage Sentinel Error', err.message || 'Failed connecting to arbitrage endpoints.');
    } finally {
      setLoading(false);
    }
  }, [symbol]);

  useEffect(() => {
    setLoading(true);
    fetchData();
    const interval = setInterval(fetchData, 10000); // 10s auto-refresh
    return () => clearInterval(interval);
  }, [fetchData]);

  const loadProvenance = async (oppId: string) => {
    try {
      setLoadingProvenance(true);
      setSelectedProvenanceId(oppId);
      const res = await api.getArbitrageProvenance(oppId);
      setProvenanceData(res);
    } catch (err: any) {
      onNotify?.('error', 'Provenance Lookup Failed', err.message || 'Could not load envelope.');
    } finally {
      setLoadingProvenance(false);
    }
  };

  const basis = dislocations?.basis_metrics;
  const bestOpp = opportunities.find(o => o.classification === 'QUALIFIED') || opportunities[0];

  return (
    <div className="flex flex-col h-full bg-[#0a0d14] text-slate-200 overflow-y-auto p-4 space-y-4">
      {/* HEADER CONTROLS */}
      <div className="flex flex-wrap items-center justify-between gap-3 p-4 bg-[#10141e] border border-slate-800 rounded-xl">
        <div className="flex items-center space-x-3">
          <div className="p-2.5 bg-emerald-500/10 border border-emerald-500/30 rounded-lg text-emerald-400">
            <Scale className="w-6 h-6 animate-pulse" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h1 className="text-lg font-bold tracking-wide text-white">
                CROSS-EXCHANGE ARBITRAGE & FUNDING DISLOCATION SENTINEL
              </h1>
              <span className="px-2 py-0.5 text-xs font-mono font-bold bg-amber-500/10 text-amber-400 border border-amber-500/30 rounded">
                TASK 20.1 • RESEARCH ONLY
              </span>
              <span className="px-2 py-0.5 text-xs font-mono bg-indigo-500/10 text-indigo-400 border border-indigo-500/30 rounded">
                EVM_v20.1_PROD
              </span>
              <span className="px-2 py-0.5 text-xs font-mono bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 rounded flex items-center space-x-1">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                <span>{health?.status || 'ONLINE'}</span>
              </span>
              <span className="text-[10px] font-mono text-slate-500 flex items-center space-x-1">
                <Clock className="w-3 h-3" />
                <span>{lastUpdated.toLocaleTimeString()}</span>
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              Deterministic Net-EV • Orderbook VWAP Capacity • Sign-Aware Funding • Immutable Provenance Envelopes
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-3">
          {/* SYMBOL SELECTOR */}
          <div className="flex items-center bg-[#0d111a] border border-slate-800 rounded-lg p-1">
            {SUPPORTED_SYMBOLS.map(sym => (
              <button
                key={sym}
                onClick={() => setSymbol(sym)}
                className={`px-3 py-1.5 text-xs font-mono font-semibold rounded-md transition-colors ${
                  symbol === sym
                    ? 'bg-emerald-600 text-white shadow-sm'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
                }`}
              >
                {sym}
              </button>
            ))}
          </div>

          <button
            onClick={fetchData}
            disabled={loading}
            className="flex items-center space-x-1.5 px-3 py-1.5 text-xs font-mono bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg transition-colors border border-slate-700"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            <span>Sync</span>
          </button>
        </div>
      </div>

      {/* TOP METRIC CARDS */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
        {/* CARD 1: BASIS & Z-SCORE */}
        <div className="p-3.5 bg-[#10141e] border border-slate-800 rounded-xl">
          <div className="flex items-center justify-between text-xs text-slate-400 mb-1.5">
            <span className="flex items-center space-x-1.5">
              <Zap className="w-3.5 h-3.5 text-cyan-400" />
              <span>Spot / Perp Basis</span>
            </span>
            <span
              className={`px-1.5 py-0.5 text-[10px] font-mono rounded ${
                basis?.candidate_trigger
                  ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40 animate-pulse'
                  : 'bg-slate-800 text-slate-300'
              }`}
            >
              {basis?.regime || 'NEUTRAL'}
            </span>
          </div>
          <div className="flex items-baseline justify-between">
            <span className="text-xl font-bold font-mono text-white">
              {basis ? `${basis.raw_basis_bps > 0 ? '+' : ''}${basis.raw_basis_bps.toFixed(1)} bps` : '0.0 bps'}
            </span>
            <span className="text-xs font-mono text-cyan-400">
              Z: {basis ? `${basis.zscore > 0 ? '+' : ''}${basis.zscore.toFixed(2)}σ` : '0.00σ'}
            </span>
          </div>
          <div className="text-[11px] text-slate-500 mt-1 flex justify-between font-mono">
            <span>Spot: ${basis?.spot_price.toLocaleString() || '0'}</span>
            <span>Perp: ${basis?.perp_price.toLocaleString() || '0'}</span>
          </div>
        </div>

        {/* CARD 2: EXECUTABLE SPREAD */}
        <div className="p-3.5 bg-[#10141e] border border-slate-800 rounded-xl">
          <div className="flex items-center justify-between text-xs text-slate-400 mb-1.5">
            <span className="flex items-center space-x-1.5">
              <Scale className="w-3.5 h-3.5 text-emerald-400" />
              <span>Max Executable Edge</span>
            </span>
            <span className="text-[10px] font-mono text-slate-400">Crossing Book</span>
          </div>
          <div className="flex items-baseline justify-between">
            <span className="text-xl font-bold font-mono text-emerald-400">
              {bestOpp?.executable_spread
                ? `+${bestOpp.executable_spread.executable_spread_bps.toFixed(2)} bps`
                : '0.00 bps'}
            </span>
            <span className="text-xs font-mono text-slate-400">
              Theo: {bestOpp?.executable_spread?.theoretical_spread_bps.toFixed(1) || '0.0'} bps
            </span>
          </div>
          <div className="text-[11px] text-slate-500 mt-1 flex justify-between font-mono">
            <span>Buy {bestOpp?.long_venue.replace('_', ' ') || 'A'}</span>
            <span>Sell {bestOpp?.short_venue.replace('_', ' ') || 'B'}</span>
          </div>
        </div>

        {/* CARD 3: NET EV (BASE VS STRESS) */}
        <div className="p-3.5 bg-[#10141e] border border-slate-800 rounded-xl">
          <div className="flex items-center justify-between text-xs text-slate-400 mb-1.5">
            <span className="flex items-center space-x-1.5">
              <Coins className="w-3.5 h-3.5 text-amber-400" />
              <span>Deterministic Net EV</span>
            </span>
            <span className="px-1.5 py-0.5 text-[10px] font-mono bg-blue-500/10 text-blue-400 rounded">
              Base / Stress
            </span>
          </div>
          <div className="flex items-baseline justify-between">
            <span
              className={`text-xl font-bold font-mono ${
                (bestOpp?.multi_scenario_ev?.base_net_ev_usd || 0) > 0
                  ? 'text-emerald-400'
                  : 'text-rose-400'
              }`}
            >
              {bestOpp?.multi_scenario_ev
                ? `${bestOpp.multi_scenario_ev.base_net_ev_usd > 0 ? '+' : ''}$${bestOpp.multi_scenario_ev.base_net_ev_usd.toFixed(2)}`
                : '$0.00'}
            </span>
            <span className="text-xs font-mono text-amber-400">
              Stress: {bestOpp?.multi_scenario_ev?.stress_net_ev_bps.toFixed(1) || '0.0'} bps
            </span>
          </div>
          <div className="text-[11px] text-slate-500 mt-1 flex justify-between font-mono">
            <span>Hurdle: 5.0 bps</span>
            <span>Net Bps: {bestOpp?.multi_scenario_ev?.base_net_ev_bps.toFixed(1) || '0.0'}</span>
          </div>
        </div>

        {/* CARD 4: CAPACITY & STATUS */}
        <div className="p-3.5 bg-[#10141e] border border-slate-800 rounded-xl">
          <div className="flex items-center justify-between text-xs text-slate-400 mb-1.5">
            <span className="flex items-center space-x-1.5">
              <ShieldCheck className="w-3.5 h-3.5 text-indigo-400" />
              <span>Viable Capacity (V*)</span>
            </span>
            <span
              className={`px-1.5 py-0.5 text-[10px] font-mono font-bold rounded ${
                bestOpp?.classification === 'QUALIFIED'
                  ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                  : 'bg-slate-800 text-slate-400'
              }`}
            >
              {bestOpp?.classification || 'OBSERVE'}
            </span>
          </div>
          <div className="flex items-baseline justify-between">
            <span className="text-xl font-bold font-mono text-white">
              ${(bestOpp?.max_viable_notional_usd || 0).toLocaleString()} USD
            </span>
            <span className="text-xs font-mono text-emerald-400">
              Conf: {((bestOpp?.confidence_score || 0) * 100).toFixed(0)}%
            </span>
          </div>
          <div className="text-[11px] text-slate-500 mt-1 flex justify-between font-mono">
            <span>Latency: 24 ms</span>
            <span>Age: {bestOpp?.data_freshness_ms.toFixed(0) || '0'} ms</span>
          </div>
        </div>
      </div>

      {/* NAVIGATION TABS */}
      <div className="flex border-b border-slate-800 space-x-6 text-xs font-mono">
        {(['OVERVIEW', 'FUNDING', 'BASIS', 'CAPACITY', 'SHADOW'] as const).map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`pb-2 transition-colors border-b-2 font-semibold ${
              activeTab === tab
                ? 'border-emerald-500 text-emerald-400'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            {tab === 'OVERVIEW' && '1. Opportunity Matrix'}
            {tab === 'FUNDING' && '2. Funding Rate Matrix'}
            {tab === 'BASIS' && '3. Basis & Z-Score Radar'}
            {tab === 'CAPACITY' && '4. Depth Capacity Curve'}
            {tab === 'SHADOW' && '5. Shadow Execution Ledger'}
          </button>
        ))}
      </div>

      {/* TAB CONTENT: 1. OVERVIEW */}
      {activeTab === 'OVERVIEW' && (
        <div className="space-y-4">
          {/* ACTIVE DISLOCATIONS TABLE */}
          <div className="bg-[#10141e] border border-slate-800 rounded-xl overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-800 flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <Activity className="w-4 h-4 text-emerald-400" />
                <h2 className="text-xs font-bold uppercase tracking-wider text-slate-200">
                  Cross-Exchange Dislocation Blotter ({opportunities.length})
                </h2>
              </div>
              <span className="text-[11px] text-slate-400 font-mono">
                5-State Classification: OBSERVE ➔ CANDIDATE ➔ VALIDATING ➔ VIABLE ➔ QUALIFIED
              </span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs font-mono">
                <thead className="bg-[#0d111a] text-slate-400 border-b border-slate-800">
                  <tr>
                    <th className="py-2.5 px-3">Structure</th>
                    <th className="py-2.5 px-3">Long Leg (Ask)</th>
                    <th className="py-2.5 px-3">Short Leg (Bid)</th>
                    <th className="py-2.5 px-3 text-right">Exec Spread</th>
                    <th className="py-2.5 px-3 text-right">Base Net EV</th>
                    <th className="py-2.5 px-3 text-right">Stress EV</th>
                    <th className="py-2.5 px-3 text-right">Viable Size</th>
                    <th className="py-2.5 px-3 text-center">Status</th>
                    <th className="py-2.5 px-3 text-center">Provenance</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {opportunities.length === 0 ? (
                    <tr>
                      <td colSpan={9} className="py-6 text-center text-slate-500">
                        No active dislocations detected. Order books nominal.
                      </td>
                    </tr>
                  ) : (
                    opportunities.map((opp, idx) => (
                      <tr key={idx} className="hover:bg-slate-800/30 transition-colors">
                        <td className="py-2.5 px-3">
                          <span className="text-slate-200 font-semibold">{opp.opportunity_type}</span>
                          <div className="text-[10px] text-slate-500">
                            Age: {opp.data_freshness_ms.toFixed(0)}ms • {opp.persistence_observations} obs
                          </div>
                        </td>
                        <td className="py-2.5 px-3">
                          <span className="text-emerald-400">{opp.long_venue}</span>
                          <div className="text-[10px] text-slate-400">
                            ${opp.executable_spread?.vwap_long_ask.toLocaleString() || '0'}
                          </div>
                        </td>
                        <td className="py-2.5 px-3">
                          <span className="text-rose-400">{opp.short_venue}</span>
                          <div className="text-[10px] text-slate-400">
                            ${opp.executable_spread?.vwap_short_bid.toLocaleString() || '0'}
                          </div>
                        </td>
                        <td className="py-2.5 px-3 text-right font-semibold text-white">
                          +{opp.executable_spread?.executable_spread_bps.toFixed(2) || '0.00'} bps
                          <div className="text-[10px] text-slate-500">
                            Theo: {opp.executable_spread?.theoretical_spread_bps.toFixed(1)} bps
                          </div>
                        </td>
                        <td className="py-2.5 px-3 text-right font-semibold">
                          <span
                            className={
                              (opp.multi_scenario_ev?.base_net_ev_usd || 0) > 0
                                ? 'text-emerald-400'
                                : 'text-rose-400'
                            }
                          >
                            +${opp.multi_scenario_ev?.base_net_ev_usd.toFixed(2) || '0.00'}
                          </span>
                          <div className="text-[10px] text-slate-400">
                            {opp.multi_scenario_ev?.base_net_ev_bps.toFixed(1) || '0.0'} bps
                          </div>
                        </td>
                        <td className="py-2.5 px-3 text-right text-amber-400 font-mono">
                          {opp.multi_scenario_ev?.stress_net_ev_bps.toFixed(1) || '0.0'} bps
                        </td>
                        <td className="py-2.5 px-3 text-right font-mono text-slate-200">
                          ${opp.max_viable_notional_usd.toLocaleString()}
                        </td>
                        <td className="py-2.5 px-3 text-center">
                          <span
                            className={`px-2 py-0.5 text-[10px] font-bold rounded-full ${
                              opp.classification === 'QUALIFIED'
                                ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40'
                                : opp.classification === 'ECONOMICALLY_VIABLE'
                                ? 'bg-blue-500/20 text-blue-400'
                                : opp.classification === 'VALIDATING'
                                ? 'bg-indigo-500/20 text-indigo-400'
                                : opp.classification === 'CANDIDATE'
                                ? 'bg-amber-500/20 text-amber-400'
                                : opp.classification === 'REJECTED'
                                ? 'bg-rose-500/20 text-rose-400'
                                : 'bg-slate-800 text-slate-400'
                            }`}
                          >
                            {opp.classification}
                          </span>
                          {opp.rejection_code !== 'NONE' && (
                            <div className="text-[9px] text-rose-400 mt-0.5">
                              {opp.rejection_code}
                            </div>
                          )}
                        </td>
                        <td className="py-2.5 px-3 text-center">
                          <button
                            onClick={() => loadProvenance(opp.opportunity_id)}
                            className="p-1 hover:bg-slate-700 text-slate-400 hover:text-emerald-400 rounded transition-colors"
                            title="Inspect Sealed Provenance Envelope"
                          >
                            <FileCheck2 className="w-4 h-4" />
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* NET EV WATERFALL BREAKDOWN (BEST OPPORTUNITY) */}
          {bestOpp?.multi_scenario_ev?.cost_breakdown && (
            <div className="p-4 bg-[#10141e] border border-slate-800 rounded-xl space-y-3">
              <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                <span className="text-xs font-bold uppercase tracking-wider text-slate-200 flex items-center space-x-2">
                  <Coins className="w-4 h-4 text-amber-400" />
                  <span>Deterministic Net-EV Cost Waterfall ({bestOpp.opportunity_id})</span>
                </span>
                <span className="text-[11px] font-mono text-slate-400">
                  Model: {bestOpp.multi_scenario_ev.cost_breakdown.model_version} • Target Notional: $10,000 USD
                </span>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-2 text-center text-xs font-mono">
                <div className="p-2 bg-emerald-500/10 border border-emerald-500/20 rounded-lg">
                  <div className="text-slate-400 text-[10px]">Gross Edge</div>
                  <div className="text-emerald-400 font-bold text-sm mt-0.5">
                    +${(bestOpp.executable_spread?.gross_spread_usd || 0).toFixed(2)}
                  </div>
                </div>
                <div className="p-2 bg-slate-900 border border-slate-800 rounded-lg">
                  <div className="text-slate-400 text-[10px]">Taker Fees</div>
                  <div className="text-rose-400 font-bold text-sm mt-0.5">
                    -$
                    {(
                      bestOpp.multi_scenario_ev.cost_breakdown.entry_fee_long_usd +
                      bestOpp.multi_scenario_ev.cost_breakdown.entry_fee_short_usd +
                      bestOpp.multi_scenario_ev.cost_breakdown.exit_fee_long_usd +
                      bestOpp.multi_scenario_ev.cost_breakdown.exit_fee_short_usd
                    ).toFixed(2)}
                  </div>
                </div>
                <div className="p-2 bg-slate-900 border border-slate-800 rounded-lg">
                  <div className="text-slate-400 text-[10px]">Book Slippage</div>
                  <div className="text-rose-400 font-bold text-sm mt-0.5">
                    -$
                    {(
                      bestOpp.multi_scenario_ev.cost_breakdown.orderbook_slippage_long_usd +
                      bestOpp.multi_scenario_ev.cost_breakdown.orderbook_slippage_short_usd
                    ).toFixed(2)}
                  </div>
                </div>
                <div className="p-2 bg-slate-900 border border-slate-800 rounded-lg">
                  <div className="text-slate-400 text-[10px]">Latency Drift</div>
                  <div className="text-rose-400 font-bold text-sm mt-0.5">
                    -${bestOpp.multi_scenario_ev.cost_breakdown.latency_cost_usd.toFixed(2)}
                  </div>
                </div>
                <div className="p-2 bg-slate-900 border border-slate-800 rounded-lg">
                  <div className="text-slate-400 text-[10px]">Hedge Drift</div>
                  <div className="text-rose-400 font-bold text-sm mt-0.5">
                    -${bestOpp.multi_scenario_ev.cost_breakdown.hedge_cost_usd.toFixed(2)}
                  </div>
                </div>
                <div className="p-2 bg-slate-900 border border-slate-800 rounded-lg">
                  <div className="text-slate-400 text-[10px]">Funding Cashflow</div>
                  <div className="text-cyan-400 font-bold text-sm mt-0.5">
                    {bestOpp.multi_scenario_ev.cost_breakdown.funding_cashflow_usd >= 0 ? '+' : ''}$
                    {bestOpp.multi_scenario_ev.cost_breakdown.funding_cashflow_usd.toFixed(2)}
                  </div>
                </div>
                <div className="p-2 bg-slate-900 border border-slate-800 rounded-lg">
                  <div className="text-slate-400 text-[10px]">Safety Buffer</div>
                  <div className="text-amber-400 font-bold text-sm mt-0.5">
                    -${bestOpp.multi_scenario_ev.cost_breakdown.safety_buffer_usd.toFixed(2)}
                  </div>
                </div>
                <div className="p-2 bg-blue-500/10 border border-blue-500/30 rounded-lg">
                  <div className="text-blue-300 text-[10px]">Final Net EV</div>
                  <div className="text-white font-bold text-sm mt-0.5">
                    +${bestOpp.multi_scenario_ev.base_net_ev_usd.toFixed(2)}
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* TAB CONTENT: 2. FUNDING MATRIX */}
      {activeTab === 'FUNDING' && (
        <div className="bg-[#10141e] border border-slate-800 rounded-xl overflow-hidden space-y-3 p-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-200 flex items-center space-x-2">
              <Percent className="w-4 h-4 text-cyan-400" />
              <span>Cross-Exchange Perpetual Funding Matrix ({fundingMatrix.length} Pairs)</span>
            </span>
            <span className="text-xs text-slate-400 font-mono">
              Sign-Aware Cashflows: Long Leg Pays F, Short Leg Receives F
            </span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs font-mono">
              <thead className="bg-[#0d111a] text-slate-400 border-b border-slate-800">
                <tr>
                  <th className="py-2 px-3">Pair ID</th>
                  <th className="py-2 px-3">Rate A</th>
                  <th className="py-2 px-3">Rate B</th>
                  <th className="py-2 px-3 text-right">Divergence</th>
                  <th className="py-2 px-3 text-right">Annualized APR</th>
                  <th className="py-2 px-3 text-right">Settlement In</th>
                  <th className="py-2 px-3 text-center">Direction</th>
                  <th className="py-2 px-3 text-right">Estimated Capture</th>
                  <th className="py-2 px-3 text-center">Confidence</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {fundingMatrix.length === 0 ? (
                  <tr>
                    <td colSpan={9} className="py-6 text-center text-slate-500">
                      No funding rate feeds available.
                    </td>
                  </tr>
                ) : (
                  fundingMatrix.map((item, idx) => (
                    <tr key={idx} className="hover:bg-slate-800/30 transition-colors">
                      <td className="py-2 px-3 font-semibold text-white">{item.pair_id}</td>
                      <td className="py-2 px-3 text-slate-300">{item.rate_a_pct.toFixed(4)}%</td>
                      <td className="py-2 px-3 text-slate-300">{item.rate_b_pct.toFixed(4)}%</td>
                      <td className="py-2 px-3 text-right text-cyan-400 font-semibold">
                        {item.raw_divergence_bps.toFixed(2)} bps
                      </td>
                      <td className="py-2 px-3 text-right text-emerald-400 font-bold">
                        {item.annualized_divergence_pct.toFixed(2)}%
                      </td>
                      <td className="py-2 px-3 text-right text-slate-400 flex items-center justify-end space-x-1">
                        <Clock className="w-3 h-3 text-slate-500" />
                        <span>{Math.floor(item.time_to_funding_sec / 3600)}h {Math.floor((item.time_to_funding_sec % 3600) / 60)}m</span>
                      </td>
                      <td className="py-2 px-3 text-center text-[10px]">
                        <span className="text-emerald-400">Long {item.proposed_long_leg.split('_')[0]}</span>
                        {' / '}
                        <span className="text-rose-400">Short {item.proposed_short_leg.split('_')[0]}</span>
                      </td>
                      <td className="py-2 px-3 text-right font-bold text-emerald-400">
                        +{item.estimated_capture_bps.toFixed(2)} bps
                      </td>
                      <td className="py-2 px-3 text-center">
                        <span className="px-2 py-0.5 text-[10px] bg-indigo-500/20 text-indigo-300 rounded font-semibold">
                          {(item.confidence * 100).toFixed(0)}%
                        </span>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* TAB CONTENT: 3. BASIS & Z-SCORE RADAR */}
      {activeTab === 'BASIS' && (
        <div className="p-4 bg-[#10141e] border border-slate-800 rounded-xl space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-200 flex items-center space-x-2">
              <Zap className="w-4 h-4 text-cyan-400" />
              <span>Spot vs. Perpetual Basis Anomaly Radar</span>
            </span>
            <span className="text-xs text-amber-400 font-mono">
              3-Sigma (|Z| ≥ 3.0) is strictly a CANDIDATE trigger, not a trade signal
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 font-mono text-xs">
            <div className="p-3.5 bg-slate-900 border border-slate-800 rounded-lg space-y-2">
              <div className="text-slate-400 text-[11px]">Pricing Spread</div>
              <div className="text-2xl font-bold text-white">
                {basis ? `${basis.raw_basis_bps.toFixed(1)} bps` : '0.0 bps'}
              </div>
              <div className="text-slate-500 text-[11px] space-y-0.5">
                <div>Spot Price: ${basis?.spot_price.toLocaleString()} ({basis?.spot_venue})</div>
                <div>Perp Price: ${basis?.perp_price.toLocaleString()} ({basis?.perp_venue})</div>
              </div>
            </div>

            <div className="p-3.5 bg-slate-900 border border-slate-800 rounded-lg space-y-2">
              <div className="text-slate-400 text-[11px]">Rolling Statistics (120-window)</div>
              <div className="text-2xl font-bold text-cyan-400">
                {basis ? `${basis.zscore > 0 ? '+' : ''}${basis.zscore.toFixed(2)}σ` : '0.00σ'}
              </div>
              <div className="text-slate-500 text-[11px] space-y-0.5">
                <div>Rolling Mean (μ): {basis?.rolling_mean_bps.toFixed(2)} bps</div>
                <div>Rolling Std (σ): {basis?.rolling_std_bps.toFixed(2)} bps</div>
              </div>
            </div>

            <div className="p-3.5 bg-slate-900 border border-slate-800 rounded-lg space-y-2">
              <div className="text-slate-400 text-[11px]">Regime & Persistence</div>
              <div className="text-xl font-bold text-amber-400">
                {basis?.regime || 'NEUTRAL'}
              </div>
              <div className="text-slate-500 text-[11px] space-y-0.5">
                <div>Candidate Trigger: {basis?.candidate_trigger ? 'ACTIVE ⚡' : 'NORMAL 🟢'}</div>
                <div>Duration: {(basis?.duration_outside_threshold_ms || 0).toFixed(0)} ms</div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TAB CONTENT: 4. DEPTH CAPACITY CURVE */}
      {activeTab === 'CAPACITY' && bestOpp && (
        <div className="p-4 bg-[#10141e] border border-slate-800 rounded-xl space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-200 flex items-center space-x-2">
              <Layers className="w-4 h-4 text-emerald-400" />
              <span>Liquidity Capacity Curve across Order Book Depth ({bestOpp.opportunity_id})</span>
            </span>
            <span className="text-xs text-slate-400 font-mono">
              Max Viable Size (V*): <strong className="text-emerald-400">${bestOpp.max_viable_notional_usd.toLocaleString()} USD</strong>
            </span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs font-mono">
              <thead className="bg-[#0d111a] text-slate-400 border-b border-slate-800">
                <tr>
                  <th className="py-2.5 px-3">Notional Tier</th>
                  <th className="py-2.5 px-3 text-right">Exec Qty</th>
                  <th className="py-2.5 px-3 text-right">VWAP Long</th>
                  <th className="py-2.5 px-3 text-right">VWAP Short</th>
                  <th className="py-2.5 px-3 text-right">Total Slippage</th>
                  <th className="py-2.5 px-3 text-right">Net EV USD</th>
                  <th className="py-2.5 px-3 text-right">Net EV Bps</th>
                  <th className="py-2.5 px-3 text-center">Viability</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {bestOpp.capacity_tiers.map((tier, idx) => (
                  <tr key={idx} className="hover:bg-slate-800/30 transition-colors">
                    <td className="py-2.5 px-3 font-bold text-white">${tier.notional_usd.toLocaleString()}</td>
                    <td className="py-2.5 px-3 text-right text-slate-300">{tier.executable_qty.toFixed(4)}</td>
                    <td className="py-2.5 px-3 text-right text-emerald-400">${tier.vwap_long.toLocaleString()}</td>
                    <td className="py-2.5 px-3 text-right text-rose-400">${tier.vwap_short.toLocaleString()}</td>
                    <td className="py-2.5 px-3 text-right text-slate-400">{tier.slippage_bps.toFixed(1)} bps</td>
                    <td className="py-2.5 px-3 text-right font-semibold">
                      <span className={tier.net_ev_usd > 0 ? 'text-emerald-400' : 'text-rose-400'}>
                        {tier.net_ev_usd > 0 ? '+' : ''}${tier.net_ev_usd.toFixed(2)}
                      </span>
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono text-slate-300">
                      {tier.net_ev_bps.toFixed(1)} bps
                    </td>
                    <td className="py-2.5 px-3 text-center">
                      <span
                        className={`px-2 py-0.5 text-[10px] font-bold rounded ${
                          tier.viable
                            ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40'
                            : 'bg-rose-500/20 text-rose-400'
                        }`}
                      >
                        {tier.viable ? 'VIABLE' : 'UNVIABLE'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* TAB CONTENT: 5. SHADOW EXECUTION LEDGER */}
      {activeTab === 'SHADOW' && (
        <div className="p-4 bg-[#10141e] border border-slate-800 rounded-xl space-y-3">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-200 flex items-center space-x-2">
              <Cpu className="w-4 h-4 text-indigo-400" />
              <span>Two-Leg Asynchronous Shadow Execution Ledger</span>
            </span>
            <span className="text-xs text-slate-400 font-mono">
              Simulates Partial Fills, Latency Drift & Realized Synthetic P&L
            </span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs font-mono">
              <thead className="bg-[#0d111a] text-slate-400 border-b border-slate-800">
                <tr>
                  <th className="py-2 px-3">Opportunity ID</th>
                  <th className="py-2 px-3">Pair / Legs</th>
                  <th className="py-2 px-3 text-right">Target Notional</th>
                  <th className="py-2 px-3 text-right">Predicted Net EV</th>
                  <th className="py-2 px-3 text-right">Realized Net EV</th>
                  <th className="py-2 px-3 text-right">Model Error</th>
                  <th className="py-2 px-3 text-right">Unhedged Delta</th>
                  <th className="py-2 px-3 text-center">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {history.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="py-6 text-center text-slate-500">
                      No shadow trades recorded yet. Qualified opportunities will simulate execution automatically.
                    </td>
                  </tr>
                ) : (
                  history.map((h, idx) => (
                    <tr key={idx} className="hover:bg-slate-800/30 transition-colors">
                      <td className="py-2 px-3 font-semibold text-white">{h.opportunity_id}</td>
                      <td className="py-2 px-3 text-slate-300">
                        {h.canonical_symbol} ({h.long_venue.split('_')[0]} / {h.short_venue.split('_')[0]})
                      </td>
                      <td className="py-2 px-3 text-right font-mono">${h.target_notional_usd.toLocaleString()}</td>
                      <td className="py-2 px-3 text-right text-emerald-400 font-bold">
                        +${h.predicted_net_ev_usd.toFixed(2)}
                      </td>
                      <td className="py-2 px-3 text-right font-bold text-white">
                        {h.realized_reference_ev_usd !== null
                          ? `${h.realized_reference_ev_usd >= 0 ? '+' : ''}$${h.realized_reference_ev_usd.toFixed(2)}`
                          : 'PENDING'}
                      </td>
                      <td className="py-2 px-3 text-right text-amber-400 font-mono">
                        {h.model_attribution_error_usd !== null ? `$${h.model_attribution_error_usd.toFixed(2)}` : 'N/A'}
                      </td>
                      <td className="py-2 px-3 text-right text-rose-400 font-mono">
                        {h.unhedged_residual_qty.toFixed(4)}
                      </td>
                      <td className="py-2 px-3 text-center">
                        <span className="px-2 py-0.5 text-[10px] font-bold bg-slate-800 text-slate-300 rounded">
                          {h.status}
                        </span>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* PROVENANCE DRILLDOWN MODAL */}
      {selectedProvenanceId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
          <div className="bg-[#10141e] border border-slate-700 rounded-xl w-full max-w-3xl max-h-[85vh] flex flex-col shadow-2xl">
            <div className="px-5 py-4 border-b border-slate-800 flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <FileCheck2 className="w-5 h-5 text-emerald-400" />
                <h3 className="text-sm font-bold text-white">
                  Cryptographic Provenance Envelope Drilldown
                </h3>
              </div>
              <button
                onClick={() => setSelectedProvenanceId(null)}
                className="text-slate-400 hover:text-white text-xs px-2 py-1 bg-slate-800 rounded"
              >
                Close [ESC]
              </button>
            </div>

            <div className="p-5 overflow-y-auto font-mono text-xs space-y-3">
              {loadingProvenance ? (
                <div className="py-8 text-center text-slate-400 flex items-center justify-center space-x-2">
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  <span>Verifying SHA-256 Envelope Digest...</span>
                </div>
              ) : provenanceData ? (
                <div className="space-y-3">
                  <div className="p-3 bg-slate-900 border border-slate-800 rounded-lg flex items-center justify-between">
                    <div>
                      <span className="text-slate-400 text-[10px]">Canonical SHA-256 Digest:</span>
                      <div className="text-emerald-400 font-bold text-xs break-all">
                        {provenanceData.envelope?.canonical_envelope_hash}
                      </div>
                    </div>
                    <span
                      className={`px-2 py-1 text-xs font-bold rounded ${
                        provenanceData.integrity_verified
                          ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40'
                          : 'bg-rose-500/20 text-rose-400'
                      }`}
                    >
                      {provenanceData.integrity_verified ? 'VERIFIED 100%' : 'HASH MISMATCH'}
                    </span>
                  </div>

                  <div className="p-3 bg-[#0d111a] border border-slate-800 rounded-lg overflow-x-auto max-h-96">
                    <pre className="text-slate-300 text-[11px]">
                      {JSON.stringify(provenanceData.envelope, null, 2)}
                    </pre>
                  </div>
                </div>
              ) : (
                <div className="py-6 text-center text-slate-500">Envelope not found.</div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
