import React from 'react';
import { ShieldCheck, Activity, TrendingUp, TrendingDown, Eye, AlertCircle, ArrowRight } from 'lucide-react';
import { SKYIntelligenceResponse, SetupSuggestion } from '../types';
import { LoadingSkeleton } from './LoadingSkeleton';

interface SKYIntelligencePanelProps {
  data?: SKYIntelligenceResponse | null;
  loading?: boolean;
  onDeploySetup?: (setup: SetupSuggestion) => void;
}

export const SKYIntelligencePanel: React.FC<SKYIntelligencePanelProps> = ({
  data,
  loading = false,
  onDeploySetup,
}) => {
  if (loading || !data) {
    return (
      <div className="bg-background-card border border-border rounded-lg p-4 shadow-lg flex flex-col gap-3">
        <div className="flex items-center justify-between pb-3 border-b border-border">
          <LoadingSkeleton className="h-4 w-40" />
          <LoadingSkeleton className="h-4 w-20" />
        </div>
        <LoadingSkeleton className="h-16 w-full" />
        <LoadingSkeleton className="h-24 w-full" />
      </div>
    );
  }

  const { decision, net_ev_r, kelly_fraction, explanation_dossier, vwap, setups = [], no_trade_reason } = data;

  const decisionBg =
    decision === 'LONG'
      ? 'bg-terminal-green/10 text-terminal-green border-terminal-green/40'
      : decision === 'SHORT'
      ? 'bg-terminal-red/10 text-terminal-red border-terminal-red/40'
      : decision === 'WATCH'
      ? 'bg-amber-500/10 text-amber-400 border-amber-500/40'
      : 'bg-slate-800/60 text-slate-400 border-slate-700';

  return (
    <div className="bg-background-card border border-border rounded-lg p-4 shadow-lg flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-center justify-between pb-3 border-b border-border">
        <div className="flex items-center gap-2">
          <ShieldCheck className="w-4 h-4 text-terminal-cyan" />
          <h3 className="text-xs font-mono font-bold text-slate-200 uppercase tracking-wider">
            SKY QUANTITATIVE INTELLIGENCE
          </h3>
        </div>
        <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-terminal-cyan/10 text-terminal-cyan border border-terminal-cyan/30">
          CANONICAL 17-PHASE
        </span>
      </div>

      {/* Decision Master Card */}
      <div className={`p-3 rounded border flex flex-col md:flex-row md:items-center justify-between gap-3 ${decisionBg}`}>
        <div className="flex items-center gap-3">
          {decision === 'LONG' && <TrendingUp className="w-6 h-6 text-terminal-green" />}
          {decision === 'SHORT' && <TrendingDown className="w-6 h-6 text-terminal-red" />}
          {decision === 'WATCH' && <Eye className="w-6 h-6 text-amber-400" />}
          {decision === 'NO_TRADE' && <AlertCircle className="w-6 h-6 text-slate-400" />}
          <div>
            <div className="text-[10px] font-mono text-slate-400 uppercase">MASTER DECISION ENGINE</div>
            <div className="text-sm font-mono font-bold tracking-wide">{decision}</div>
          </div>
        </div>

        <div className="flex items-center gap-4 text-xs font-mono">
          <div>
            <span className="text-[10px] text-slate-400 block">NET EV</span>
            <span className="font-bold text-slate-200">+{net_ev_r.toFixed(2)}R</span>
          </div>
          <div>
            <span className="text-[10px] text-slate-400 block">KELLY RISK</span>
            <span className="font-bold text-slate-200">{(kelly_fraction * 100).toFixed(2)}%</span>
          </div>
          <div>
            <span className="text-[10px] text-slate-400 block">REGIME</span>
            <span className="font-bold text-slate-200">{explanation_dossier.regime || 'RANGE'}</span>
          </div>
        </div>
      </div>

      {/* Rationale & No-Trade Barrier */}
      {no_trade_reason && (
        <div className="text-[11px] font-mono bg-slate-900/80 p-2.5 rounded border border-slate-800 text-slate-400 flex items-start gap-2">
          <AlertCircle className="w-3.5 h-3.5 text-amber-400 shrink-0 mt-0.5" />
          <span>
            <strong className="text-slate-300">Evidence Barrier: </strong>
            {no_trade_reason}
          </span>
        </div>
      )}

      {/* VWAP Engine Metrics Card */}
      {vwap && vwap.vwap > 0 && (
        <div className="bg-background p-3 rounded border border-border flex flex-col gap-2">
          <div className="flex items-center justify-between text-[11px] font-mono">
            <div className="flex items-center gap-1.5 text-slate-300 font-bold">
              <Activity className="w-3.5 h-3.5 text-terminal-purple" />
              <span>PHASE 8: VWAP &amp; SIGMA BANDS</span>
            </div>
            <span className={`text-[10px] px-1.5 py-0.5 rounded ${vwap.is_reclaiming ? 'bg-terminal-green/20 text-terminal-green' : 'bg-slate-800 text-slate-400'}`}>
              {vwap.is_reclaiming ? 'RECLAIMING' : `${vwap.deviation_sigmas > 0 ? '+' : ''}${vwap.deviation_sigmas}σ DEVIATION`}
            </span>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-center text-xs font-mono pt-1">
            <div className="bg-background-card p-1.5 rounded border border-border/60">
              <div className="text-[9px] text-slate-400">SESSION VWAP</div>
              <div className="font-bold text-slate-200">${vwap.vwap.toLocaleString()}</div>
            </div>
            <div className="bg-background-card p-1.5 rounded border border-border/60">
              <div className="text-[9px] text-slate-400">+2.0σ UPPER</div>
              <div className="font-bold text-terminal-red">${vwap.upper_band_2sigma.toLocaleString()}</div>
            </div>
            <div className="bg-background-card p-1.5 rounded border border-border/60">
              <div className="text-[9px] text-slate-400">-2.0σ LOWER</div>
              <div className="font-bold text-terminal-green">${vwap.lower_band_2sigma.toLocaleString()}</div>
            </div>
            <div className="bg-background-card p-1.5 rounded border border-border/60">
              <div className="text-[9px] text-slate-400">MEAN REV PROB</div>
              <div className="font-bold text-terminal-cyan">{(vwap.mean_reversion_prob * 100).toFixed(0)}%</div>
            </div>
          </div>
        </div>
      )}

      {/* Setups List */}
      <div className="flex flex-col gap-2">
        <div className="text-[11px] font-mono text-slate-400 font-bold uppercase">
          DETECTED INSTITUTIONAL SETUPS ({setups.length})
        </div>

        {setups.length === 0 ? (
          <div className="text-[11px] font-mono text-slate-500 py-3 text-center bg-background rounded border border-border/60">
            No institutional SMC setups currently meeting the 1.8R hurdle.
          </div>
        ) : (
          <div className="space-y-2">
            {setups.map((setup, idx) => {
              const isBull = setup.direction === 'LONG';
              return (
                <div
                  key={`${setup.setup_type}-${idx}`}
                  className="bg-background p-2.5 rounded border border-border flex flex-col md:flex-row md:items-center justify-between gap-2"
                >
                  <div className="flex flex-col gap-0.5">
                    <div className="flex items-center gap-2">
                      <span
                        className={`text-[9px] font-mono font-bold px-1.5 py-0.5 rounded ${
                          isBull ? 'bg-terminal-green/20 text-terminal-green' : 'bg-terminal-red/20 text-terminal-red'
                        }`}
                      >
                        {setup.direction}
                      </span>
                      <span className="text-xs font-mono font-bold text-slate-200">
                        {setup.setup_type.replace(/_/g, ' ')}
                      </span>
                      {setup.is_qualified && (
                        <span className="text-[9px] font-mono text-terminal-cyan border border-terminal-cyan/30 px-1 rounded">
                          QUALIFIED
                        </span>
                      )}
                    </div>
                    <div className="text-[10px] font-mono text-slate-400">{setup.explanation_text}</div>
                  </div>

                  <div className="flex items-center gap-3 shrink-0">
                    <div className="text-right text-[10px] font-mono">
                      <span className="text-slate-400 block">
                        R:R <strong className="text-slate-200">{setup.risk_reward_ratio}R</strong>
                      </span>
                      <span className="text-slate-500">
                        Win Rate {(setup.historical_win_rate * 100).toFixed(0)}%
                      </span>
                    </div>

                    {onDeploySetup && (
                      <button
                        onClick={() =>
                          onDeploySetup({
                            type: setup.direction === 'LONG' ? 'LONG' : 'SHORT',
                            bias: setup.direction,
                            trigger: setup.setup_type,
                            entry: setup.entry_price,
                            stopLoss: setup.invalidation_sl,
                            takeProfit: setup.target_tp,
                            riskRewardRatio: setup.risk_reward_ratio,
                          })
                        }
                        className="px-2.5 py-1 text-[10px] font-mono font-bold rounded bg-terminal-cyan/10 hover:bg-terminal-cyan/20 text-terminal-cyan border border-terminal-cyan/30 transition flex items-center gap-1"
                      >
                        DEPLOY <ArrowRight className="w-3 h-3" />
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
