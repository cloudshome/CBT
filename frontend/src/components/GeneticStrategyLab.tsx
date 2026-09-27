import React, { useState, useEffect, useCallback } from 'react';
import { api } from '../services/api';
import {
  Dna,
  Play,
  Award,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  Sliders,
  ShieldCheck,
} from 'lucide-react';

interface StrategyGenome {
  genome_id: string;
  generation: number;
  smc_swing_left_bars: number;
  smc_swing_right_bars: number;
  fvg_threshold_ticks: number;
  atr_multiplier_stop: number;
  target_rr_ratio: number;
  half_kelly_fraction: number;
  bull_regime_weight: number;
  bear_regime_weight: number;
  range_regime_weight: number;
  vol_expansion_weight: number;
}

interface OptimizationResult {
  optimization_id: string;
  symbol: string;
  timeframe: string;
  total_generations: number;
  population_size: number;
  best_genome: StrategyGenome;
  best_fitness: number;
  in_sample_sharpe: number;
  cpcv_out_of_sample_sharpe: number;
  deflated_sharpe_ratio: number;
  whites_reality_check_p_value: number;
  is_statistically_significant: boolean;
  fitness_history: number[];
}

interface GeneticStrategyLabProps {
  symbol: string;
  timeframe?: string;
  onDeployGenome?: (genome: StrategyGenome) => void;
}

export const GeneticStrategyLab: React.FC<GeneticStrategyLabProps> = ({
  symbol,
  timeframe = '15m',
  onDeployGenome,
}) => {
  const [result, setResult] = useState<OptimizationResult | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [runningEvolution, setRunningEvolution] = useState<boolean>(false);
  const [generations, setGenerations] = useState<number>(4);
  const [populationSize, setPopulationSize] = useState<number>(15);
  const [error, setError] = useState<string | null>(null);

  const fetchResults = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await api.getGeneticOptimizationResults(symbol);
      setResult(res);
    } catch (err: any) {
      setError(err?.message || 'Failed to fetch optimization results');
    } finally {
      setLoading(false);
    }
  }, [symbol]);

  useEffect(() => {
    fetchResults();
  }, [fetchResults]);

  const handleRunEvolution = async () => {
    try {
      setRunningEvolution(true);
      setError(null);
      const res = await api.runGeneticOptimization({
        symbol,
        timeframe,
        generations,
        population_size: populationSize,
      });
      setResult(res);
    } catch (err: any) {
      setError(err?.message || 'Genetic optimization failed');
    } finally {
      setRunningEvolution(false);
    }
  };

  return (
    <div className="bg-[#090d16] border border-[#1e293b] rounded-xl p-4 flex flex-col gap-4 text-xs font-mono select-none">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-[#1e293b] pb-3">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-purple-500/10 border border-purple-500/30 text-purple-400">
            <Dna size={16} />
          </div>
          <div>
            <h3 className="font-bold text-slate-100 text-sm tracking-wide flex items-center gap-2">
              Walk-Forward Genetic Strategy Optimizer & WRC Permutation Lab
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-purple-500/20 text-purple-300 font-semibold border border-purple-500/40">
                FRONTIER 3
              </span>
            </h3>
            <p className="text-[11px] text-slate-400">
              CPCV Purged Cross-Validation, Deflated Sharpe Ratio (DSR) &amp; White's Reality Check (p &lt; 0.05)
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={fetchResults}
            disabled={loading || runningEvolution}
            className="flex items-center gap-1 px-2 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded border border-slate-700 transition-all active:scale-95 disabled:opacity-50"
          >
            <RefreshCw size={11} className={loading ? 'animate-spin text-purple-400' : ''} />
            <span>Fetch</span>
          </button>

          <button
            onClick={handleRunEvolution}
            disabled={runningEvolution}
            className="flex items-center gap-1.5 px-3 py-1 bg-purple-600 hover:bg-purple-500 text-white font-bold rounded shadow-sm shadow-purple-600/30 transition-all active:scale-95 disabled:opacity-50"
          >
            {runningEvolution ? (
              <>
                <RefreshCw size={12} className="animate-spin" />
                <span>Evolving Population...</span>
              </>
            ) : (
              <>
                <Play size={12} />
                <span>Run Genetic Evolution</span>
              </>
            )}
          </button>
        </div>
      </div>

      {error ? (
        <div className="p-3 bg-rose-500/10 border border-rose-500/30 rounded-lg text-rose-300 flex items-center gap-2">
          <AlertTriangle size={14} />
          <span>{error}</span>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Column 1: Genetic Hyperparameter Controls & Fitness History */}
          <div className="bg-[#0c1220] border border-[#1e293b] rounded-lg p-3 flex flex-col gap-3 justify-between">
            <div>
              <div className="flex items-center justify-between border-b border-slate-800 pb-1.5 mb-2.5">
                <span className="text-slate-300 font-bold flex items-center gap-1.5">
                  <Sliders size={13} className="text-purple-400" />
                  Evolution Parameters
                </span>
                <span className="text-[10px] text-slate-400">Search Bounds</span>
              </div>

              <div className="grid grid-cols-2 gap-2 mb-3">
                <div className="p-2 bg-slate-900/60 rounded border border-slate-800 flex flex-col">
                  <span className="text-slate-400 text-[10px]">Generations</span>
                  <input
                    type="number"
                    min={2}
                    max={10}
                    value={generations}
                    onChange={(e) => setGenerations(Number(e.target.value))}
                    className="bg-transparent text-sm font-bold text-purple-300 outline-none"
                  />
                </div>

                <div className="p-2 bg-slate-900/60 rounded border border-slate-800 flex flex-col">
                  <span className="text-slate-400 text-[10px]">Population Size</span>
                  <input
                    type="number"
                    min={6}
                    max={30}
                    value={populationSize}
                    onChange={(e) => setPopulationSize(Number(e.target.value))}
                    className="bg-transparent text-sm font-bold text-purple-300 outline-none"
                  />
                </div>
              </div>

              {/* Fitness Progression Curve */}
              <div className="flex flex-col gap-1">
                <span className="text-[10px] text-slate-400 font-semibold">
                  Fitness Progression (Across Generations):
                </span>
                <div className="flex items-end gap-1 h-16 bg-slate-900/50 p-1.5 rounded border border-slate-800/80">
                  {result?.fitness_history && result.fitness_history.length > 0 ? (
                    result.fitness_history.map((fit, idx) => {
                      const maxFit = Math.max(...result.fitness_history, 1.0);
                      const heightPercent = Math.max(15, (fit / maxFit) * 100);
                      return (
                        <div key={idx} className="flex-1 flex flex-col items-center gap-0.5 h-full justify-end">
                          <div
                            className="w-full bg-purple-500 hover:bg-purple-400 rounded-t transition-all"
                            style={{ height: `${heightPercent}%` }}
                            title={`Gen ${idx + 1}: ${fit.toFixed(3)}`}
                          />
                          <span className="text-[8px] text-slate-500">G{idx + 1}</span>
                        </div>
                      );
                    })
                  ) : (
                    <div className="w-full h-full flex items-center justify-center text-[10px] text-slate-500">
                      No evolutionary history yet
                    </div>
                  )}
                </div>
              </div>
            </div>

            <div className="p-2 bg-slate-900/30 rounded border border-slate-800/40 text-[10px] text-slate-400">
              💡 Causal firewall ensures zero lookahead bias with CPCV embargoes between trade holding periods.
            </div>
          </div>

          {/* Column 2: Best Evolved Genome Specification */}
          <div className="bg-[#0c1220] border border-[#1e293b] rounded-lg p-3 flex flex-col gap-2.5 justify-between">
            <div>
              <div className="flex items-center justify-between border-b border-slate-800 pb-1.5 mb-2">
                <span className="text-slate-300 font-bold flex items-center gap-1.5">
                  <Award size={13} className="text-purple-400" />
                  Elite Strategy Genome
                </span>
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-purple-500/10 text-purple-300 border border-purple-500/30 font-semibold">
                  {result?.best_genome?.genome_id || 'DEFAULT'}
                </span>
              </div>

              {result?.best_genome && (
                <div className="grid grid-cols-2 gap-2 text-[10px]">
                  <div className="p-1.5 bg-slate-900/50 rounded border border-slate-800">
                    <span className="text-slate-400">Swing Window:</span>
                    <div className="font-bold text-slate-200">
                      L{result.best_genome.smc_swing_left_bars} / R{result.best_genome.smc_swing_right_bars}
                    </div>
                  </div>

                  <div className="p-1.5 bg-slate-900/50 rounded border border-slate-800">
                    <span className="text-slate-400">FVG Threshold:</span>
                    <div className="font-bold text-slate-200">
                      {result.best_genome.fvg_threshold_ticks} ticks
                    </div>
                  </div>

                  <div className="p-1.5 bg-slate-900/50 rounded border border-slate-800">
                    <span className="text-slate-400">ATR Stop Multiplier:</span>
                    <div className="font-bold text-slate-200">
                      {result.best_genome.atr_multiplier_stop.toFixed(2)}x
                    </div>
                  </div>

                  <div className="p-1.5 bg-slate-900/50 rounded border border-slate-800">
                    <span className="text-slate-400">Target Risk:Reward:</span>
                    <div className="font-bold text-emerald-400">
                      1:{result.best_genome.target_rr_ratio.toFixed(2)}
                    </div>
                  </div>

                  <div className="p-1.5 bg-slate-900/50 rounded border border-slate-800">
                    <span className="text-slate-400">Half-Kelly Fraction:</span>
                    <div className="font-bold text-amber-400">
                      {(result.best_genome.half_kelly_fraction * 100).toFixed(1)}%
                    </div>
                  </div>

                  <div className="p-1.5 bg-slate-900/50 rounded border border-slate-800">
                    <span className="text-slate-400">Bull/Bear Bias:</span>
                    <div className="font-bold text-slate-200">
                      {result.best_genome.bull_regime_weight.toFixed(1)} / {result.best_genome.bear_regime_weight.toFixed(1)}
                    </div>
                  </div>
                </div>
              )}
            </div>

            {onDeployGenome && result?.best_genome && (
              <button
                onClick={() => onDeployGenome(result.best_genome)}
                className="w-full py-1.5 bg-purple-500/20 hover:bg-purple-500/30 text-purple-300 border border-purple-500/40 rounded font-bold transition-all text-center"
              >
                Deploy Genome to Order Desk
              </button>
            )}
          </div>

          {/* Column 3: Out-of-Sample Statistical Verification & WRC Scorecard */}
          <div className="bg-[#0c1220] border border-[#1e293b] rounded-lg p-3 flex flex-col gap-2.5 justify-between">
            <div>
              <div className="flex items-center justify-between border-b border-slate-800 pb-1.5 mb-2">
                <span className="text-slate-300 font-bold flex items-center gap-1.5">
                  <ShieldCheck size={13} className="text-emerald-400" />
                  Statistical Significance Scorecard
                </span>
                <span
                  className={`text-[9px] px-1.5 py-0.5 rounded border font-semibold ${
                    result?.is_statistically_significant
                      ? 'bg-emerald-500/10 text-emerald-300 border-emerald-500/40'
                      : 'bg-amber-500/10 text-amber-300 border-amber-500/40'
                  }`}
                >
                  {result?.is_statistically_significant ? 'AUTHENTIC ALPHA' : 'PENDING POWER'}
                </span>
              </div>

              <div className="flex flex-col gap-2">
                <div className="p-2 bg-slate-900/60 rounded border border-slate-800 flex justify-between items-center">
                  <span className="text-slate-400">In-Sample Sharpe Ratio:</span>
                  <span className="text-slate-200 font-bold text-sm">
                    {result?.in_sample_sharpe ? result.in_sample_sharpe.toFixed(2) : '--'}
                  </span>
                </div>

                <div className="p-2 bg-slate-900/60 rounded border border-slate-800 flex justify-between items-center">
                  <span className="text-slate-400">CPCV Out-of-Sample Sharpe:</span>
                  <span className="text-emerald-400 font-bold text-sm">
                    {result?.cpcv_out_of_sample_sharpe ? result.cpcv_out_of_sample_sharpe.toFixed(2) : '--'}
                  </span>
                </div>

                <div className="p-2 bg-slate-900/60 rounded border border-slate-800 flex justify-between items-center">
                  <span className="text-slate-400">Deflated Sharpe Ratio (DSR):</span>
                  <span
                    className={`font-bold text-sm ${
                      (result?.deflated_sharpe_ratio ?? 0) >= 0.85 ? 'text-emerald-400' : 'text-amber-400'
                    }`}
                  >
                    {result?.deflated_sharpe_ratio ? (result.deflated_sharpe_ratio * 100).toFixed(1) + '%' : '--'}
                  </span>
                </div>

                <div className="p-2 bg-slate-900/60 rounded border border-slate-800 flex justify-between items-center">
                  <span className="text-slate-400">White's Reality Check (WRC):</span>
                  <span
                    className={`font-bold text-sm ${
                      (result?.whites_reality_check_p_value ?? 1.0) < 0.05 ? 'text-emerald-400' : 'text-amber-400'
                    }`}
                  >
                    {result?.whites_reality_check_p_value !== undefined
                      ? `p = ${result.whites_reality_check_p_value.toFixed(3)}`
                      : '--'}
                  </span>
                </div>
              </div>
            </div>

            <div className="text-[10px] text-slate-500 border-t border-slate-800 pt-2 flex items-center gap-1">
              <CheckCircle2 size={11} className="text-emerald-400" />
              <span>300+ Monte Carlo return permutations verify edge against data snooping.</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default GeneticStrategyLab;
