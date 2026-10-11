import React, { useState, useEffect } from 'react';
import { Cpu, RefreshCw, AlertTriangle, CheckCircle2, XCircle, TrendingUp, TrendingDown, Layers, Terminal } from 'lucide-react';
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

export const MastermindSwarmDesk: React.FC = () => {
  const [status, setStatus] = useState<SwarmStatus | null>(null);
  const [decisions, setDecisions] = useState<DecisionRecord[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
    try {
      setRefreshing(true);
      const [sData, dData] = await Promise.all([
        api.getMastermindStatus(),
        api.getMastermindDecisions(30),
      ]);

      if (sData) {
        setStatus(sData);
      }
      if (dData && dData.decisions) {
        setDecisions(dData.decisions);
      }
      setError(null);
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
