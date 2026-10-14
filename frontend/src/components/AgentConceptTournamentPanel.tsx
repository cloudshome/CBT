import React, { useState, useEffect, useCallback } from 'react';
import {
  Trophy,
  Swords,
  Play,
  RefreshCw,
  Bot,
} from 'lucide-react';
import { paperApi } from '../services/api/paperApi';

interface LeaderboardEntry {
  rank: number;
  agent_id: string;
  name: string;
  archetype: string;
  style: string;
  primary_concept_id: string;
  primary_concept_name: string;
  win_rate: number;
  nominal_trades: number;
  net_expectancy_r: number;
  sharpe_ratio: number;
  max_drawdown_r: number;
  profit_factor: number;
  tournament_score: number;
  lifecycle_status: string;
  is_paper_active: boolean;
}

interface ArenaData {
  status: string;
  last_updated: string | null;
  market_regime: string;
  total_agents: number;
  leaderboard: LeaderboardEntry[];
  winning_agent: string | null;
  promoted_concepts: string[];
  demoted_concepts: string[];
  paper_trades_deployed: number;
}

export const AgentConceptTournamentPanel: React.FC = () => {
  const [data, setData] = useState<ArenaData | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [runningRound, setRunningRound] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const fetchLeaderboard = useCallback(async () => {
    try {
      const res = await paperApi.getArenaLeaderboard();
      setData(res);
      setError(null);
    } catch (err: any) {
      console.error('Failed to load arena leaderboard:', err);
      setError('Could not load tournament leaderboard');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchLeaderboard();
    const interval = setInterval(fetchLeaderboard, 15000); // 15s refresh
    return () => clearInterval(interval);
  }, [fetchLeaderboard]);

  const handleRunRound = async () => {
    if (runningRound) return;
    setRunningRound(true);
    try {
      await paperApi.triggerArenaTournament({
        bars_count: 350,
        deploy_to_paper: false,
        symbol: 'BTC/USDT',
      });
      await fetchLeaderboard();
    } catch (err: any) {
      console.error('Failed to run tournament round:', err);
      setError(err?.message || 'Failed running round');
    } finally {
      setRunningRound(false);
    }
  };

  const getRankBadge = (rank: number) => {
    if (rank === 1) {
      return (
        <span className="w-6 h-6 rounded-full bg-amber-500/20 text-amber-400 border border-amber-500/40 flex items-center justify-center font-bold text-xs shadow-sm">
          🥇
        </span>
      );
    }
    if (rank === 2) {
      return (
        <span className="w-6 h-6 rounded-full bg-slate-400/20 text-slate-300 border border-slate-400/40 flex items-center justify-center font-bold text-xs shadow-sm">
          🥈
        </span>
      );
    }
    if (rank === 3) {
      return (
        <span className="w-6 h-6 rounded-full bg-amber-700/20 text-amber-600 border border-amber-700/40 flex items-center justify-center font-bold text-xs shadow-sm">
          🥉
        </span>
      );
    }
    return (
      <span className="w-6 h-6 rounded-full bg-slate-800 text-slate-400 flex items-center justify-center font-mono text-xs">
        #{rank}
      </span>
    );
  };

  return (
    <div className="bg-[#090d16] border border-[#1e293b] rounded-xl p-4 shadow-xl flex flex-col gap-4 font-sans">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#1e293b] pb-3">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-amber-400 shadow-sm">
            <Trophy className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-mono font-bold text-white tracking-wide flex items-center gap-2">
                MASTERMIND AGENT CONCEPT TOURNAMENT
              </h2>
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-sky-500/10 text-sky-400 font-mono border border-sky-500/30 font-bold flex items-center gap-1">
                <Swords className="w-3 h-3" />
                60+ CONCEPTS
              </span>
            </div>
            <p className="text-xs text-slate-400 font-mono">
              Competitive Empirical Battleground: 5 Autonomous Personas Competing to Falsify, Promote &amp; Trade Concepts
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={handleRunRound}
            disabled={runningRound}
            className="px-3 py-1.5 rounded-lg bg-amber-500 hover:bg-amber-400 text-slate-950 font-mono text-xs font-bold flex items-center gap-1.5 transition-all shadow-md disabled:opacity-50"
          >
            {runningRound ? (
              <RefreshCw className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Play className="w-3.5 h-3.5 fill-current" />
            )}
            <span>{runningRound ? 'Simulating Tournament...' : 'Run Tournament Round'}</span>
          </button>
          <button
            onClick={fetchLeaderboard}
            disabled={loading}
            className="p-1.5 rounded-lg bg-[#0d1424] border border-[#1e293b] text-slate-300 hover:text-white transition-all disabled:opacity-50"
            title="Refresh Leaderboard"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-amber-400' : ''}`} />
          </button>
        </div>
      </div>

      {/* Overview Banner */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="bg-[#0d1424] border border-[#1e293b] rounded-lg p-2.5 flex flex-col justify-between">
          <span className="text-[10px] font-mono text-slate-400">ACTIVE REGIME</span>
          <div className="text-sm font-mono font-bold text-emerald-400 mt-1 flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
            {data?.market_regime || 'BULL_TRENDING'}
          </div>
        </div>
        <div className="bg-[#0d1424] border border-[#1e293b] rounded-lg p-2.5 flex flex-col justify-between">
          <span className="text-[10px] font-mono text-slate-400">TOURNAMENT LEADER</span>
          <div className="text-sm font-mono font-bold text-amber-400 mt-1 truncate">
            {data?.leaderboard?.[0]?.name || 'Evaluating...'}
          </div>
        </div>
        <div className="bg-[#0d1424] border border-[#1e293b] rounded-lg p-2.5 flex flex-col justify-between">
          <span className="text-[10px] font-mono text-slate-400">PAPER DEPLOYED</span>
          <div className="text-sm font-mono font-bold text-sky-400 mt-1">
            {data?.paper_trades_deployed ? `${data.paper_trades_deployed} Live Position` : 'Monitoring'}
          </div>
        </div>
        <div className="bg-[#0d1424] border border-[#1e293b] rounded-lg p-2.5 flex flex-col justify-between">
          <span className="text-[10px] font-mono text-slate-400">LAST EVALUATION</span>
          <div className="text-xs font-mono text-slate-300 mt-1 truncate">
            {data?.last_updated ? new Date(data.last_updated).toLocaleTimeString() : 'Fresh'}
          </div>
        </div>
      </div>

      {error && (
        <div className="text-xs text-rose-400 font-mono bg-rose-500/10 border border-rose-500/30 rounded p-2">
          {error}
        </div>
      )}

      {/* Leaderboard Table */}
      <div className="overflow-x-auto border border-[#1e293b] rounded-lg">
        <table className="w-full text-left text-xs font-mono border-collapse">
          <thead>
            <tr className="bg-[#0d1424] text-slate-400 border-b border-[#1e293b]">
              <th className="py-2.5 px-3 font-semibold">RANK</th>
              <th className="py-2.5 px-3 font-semibold">AGENT PERSONA</th>
              <th className="py-2.5 px-3 font-semibold">TESTED CONCEPT</th>
              <th className="py-2.5 px-3 font-semibold text-right">WIN RATE</th>
              <th className="py-2.5 px-3 font-semibold text-right">NET EXPECTANCY</th>
              <th className="py-2.5 px-3 font-semibold text-right">SHARPE</th>
              <th className="py-2.5 px-3 font-semibold text-right">MAX DD</th>
              <th className="py-2.5 px-3 font-semibold text-right">SCORE</th>
              <th className="py-2.5 px-3 font-semibold text-center">GATE STATUS</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#1e293b]">
            {data?.leaderboard && data.leaderboard.length > 0 ? (
              data.leaderboard.map((entry) => (
                <tr
                  key={entry.agent_id}
                  className={`hover:bg-[#131c31] transition-colors ${
                    entry.rank === 1 ? 'bg-amber-500/5' : ''
                  }`}
                >
                  <td className="py-2.5 px-3 whitespace-nowrap">
                    {getRankBadge(entry.rank)}
                  </td>
                  <td className="py-2.5 px-3 whitespace-nowrap">
                    <div className="flex items-center gap-2">
                      <div className="w-7 h-7 rounded bg-slate-800 border border-slate-700 flex items-center justify-center text-slate-300">
                        <Bot className="w-4 h-4 text-sky-400" />
                      </div>
                      <div>
                        <div className="font-bold text-white flex items-center gap-1.5">
                          {entry.name}
                          {entry.rank === 1 && (
                            <span className="text-[10px] px-1.5 py-0.2 rounded bg-amber-500/20 text-amber-300 font-bold border border-amber-500/40">
                              ARENA LEADER
                            </span>
                          )}
                        </div>
                        <div className="text-[10px] text-slate-500">
                          {entry.archetype} ({entry.style})
                        </div>
                      </div>
                    </div>
                  </td>
                  <td className="py-2.5 px-3 whitespace-nowrap">
                    <span className="text-slate-300 font-semibold">{entry.primary_concept_name}</span>
                    <span className="text-[10px] text-slate-500 ml-1.5 font-mono">[{entry.primary_concept_id}]</span>
                  </td>
                  <td className="py-2.5 px-3 text-right whitespace-nowrap">
                    <span
                      className={`font-bold ${
                        entry.win_rate >= 50 ? 'text-emerald-400' : 'text-slate-400'
                      }`}
                    >
                      {entry.win_rate.toFixed(1)}%
                    </span>
                    <span className="text-[10px] text-slate-500 ml-1">({entry.nominal_trades}T)</span>
                  </td>
                  <td className="py-2.5 px-3 text-right whitespace-nowrap">
                    <span
                      className={`font-bold ${
                        entry.net_expectancy_r > 0 ? 'text-emerald-400' : 'text-rose-400'
                      }`}
                    >
                      {entry.net_expectancy_r > 0 ? '+' : ''}
                      {entry.net_expectancy_r.toFixed(2)}R
                    </span>
                  </td>
                  <td className="py-2.5 px-3 text-right whitespace-nowrap text-slate-300">
                    {entry.sharpe_ratio.toFixed(2)}
                  </td>
                  <td className="py-2.5 px-3 text-right whitespace-nowrap text-rose-400">
                    -{entry.max_drawdown_r.toFixed(2)}R
                  </td>
                  <td className="py-2.5 px-3 text-right whitespace-nowrap font-bold">
                    <span
                      className={
                        entry.tournament_score > 0 ? 'text-amber-400' : 'text-slate-500'
                      }
                    >
                      {entry.tournament_score > 0 ? '+' : ''}
                      {entry.tournament_score.toFixed(1)}
                    </span>
                  </td>
                  <td className="py-2.5 px-3 text-center whitespace-nowrap">
                    <span
                      className={`px-2 py-0.5 rounded text-[10px] font-bold border ${
                        entry.lifecycle_status === 'PAPER_QUALIFIED'
                          ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                          : 'bg-slate-800 text-slate-400 border-slate-700'
                      }`}
                    >
                      {entry.lifecycle_status}
                    </span>
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={9} className="py-6 text-center text-slate-500">
                  {loading ? 'Initializing Agent Concept Tournament...' : 'No tournament records available.'}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};

