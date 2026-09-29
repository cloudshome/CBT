import React from 'react';
import { TrendingUp, TrendingDown, Eye, Sparkles } from 'lucide-react';
import { SKYIntelligenceResponse } from '../types';

interface SKYIntelligenceHUDProps {
  data?: SKYIntelligenceResponse | null;
  loading?: boolean;
  onRefresh?: () => void;
}

export const SKYIntelligenceHUD: React.FC<SKYIntelligenceHUDProps> = ({
  data,
  loading = false,
  onRefresh,
}) => {
  const action = data?.decision || 'NO_TRADE';
  const regime = data?.explanation_dossier?.regime || 'Consolidation / Calibration';
  const netEv = data?.net_ev_r ?? 0;
  const kelly = data?.kelly_fraction ?? 0;
  const confidence = Math.round(data?.setup_qualified?.confluence_score || (action !== 'NO_TRADE' ? 82 : 45));
  const bias = action === 'LONG' ? 'BULLISH' : action === 'SHORT' ? 'BEARISH' : 'NEUTRAL';

  const isLong = action === 'LONG';
  const isShort = action === 'SHORT';
  const isWatch = action === 'WATCH';

  const badgeColor = isLong
    ? 'bg-terminal-green/20 text-terminal-green border-terminal-green/50'
    : isShort
    ? 'bg-terminal-red/20 text-terminal-red border-terminal-red/50'
    : isWatch
    ? 'bg-amber-500/20 text-amber-400 border-amber-500/50'
    : 'bg-slate-800 text-slate-400 border-slate-700';

  return (
    <div className="bg-[#090d16]/95 backdrop-blur border border-border rounded-lg p-2.5 flex flex-wrap items-center justify-between gap-3 font-mono text-xs shadow-xl select-none">
      {/* Left: Engine Identity & Master Action Badge */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1.5 text-slate-200 font-bold">
          <Sparkles className="w-4 h-4 text-terminal-cyan animate-pulse" />
          <span className="tracking-wide">SKY QUANT HUD</span>
        </div>

        {/* Master Signal Badge */}
        <div className={`px-2.5 py-0.5 rounded-full border text-xs font-bold flex items-center gap-1.5 ${badgeColor}`}>
          {isLong ? <TrendingUp className="w-3.5 h-3.5" /> : isShort ? <TrendingDown className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
          <span>{action}</span>
        </div>
      </div>

      {/* Center: Key Mathematical Telemetry */}
      <div className="flex items-center gap-4 text-[11px] text-slate-300">
        <div className="flex items-center gap-1">
          <span className="text-slate-500">Regime:</span>
          <span className="font-semibold text-slate-200">{regime}</span>
        </div>

        <div className="flex items-center gap-1">
          <span className="text-slate-500">Bias:</span>
          <span className={`font-bold ${bias === 'BULLISH' ? 'text-terminal-green' : bias === 'BEARISH' ? 'text-terminal-red' : 'text-slate-400'}`}>
            {bias}
          </span>
        </div>

        <div className="flex items-center gap-1">
          <span className="text-slate-500">Net EV:</span>
          <span className={`font-bold ${netEv >= 0.25 ? 'text-terminal-green' : 'text-slate-400'}`}>
            {netEv.toFixed(2)}R
          </span>
        </div>

        <div className="flex items-center gap-1">
          <span className="text-slate-500">Kelly:</span>
          <span className="font-semibold text-slate-200">{(kelly * 100).toFixed(1)}%</span>
        </div>

        <div className="flex items-center gap-1">
          <span className="text-slate-500">Confidence:</span>
          <div className="w-12 bg-slate-800 rounded-full h-2 overflow-hidden">
            <div
              className="bg-terminal-cyan h-full rounded-full transition-all"
              style={{ width: `${Math.min(100, confidence)}%` }}
            />
          </div>
          <span className="text-slate-200 font-bold">{confidence}%</span>
        </div>
      </div>

      {/* Right: 30s Auto-poll indicator */}
      <div className="flex items-center gap-2">
        <span className="text-[10px] text-slate-500 flex items-center gap-1">
          <span className="w-1.5 h-1.5 rounded-full bg-terminal-green animate-ping" />
          <span>30S FEED</span>
        </span>
        {onRefresh && (
          <button
            onClick={onRefresh}
            disabled={loading}
            className="px-2 py-0.5 rounded bg-slate-900 border border-border hover:bg-slate-800 text-[10px] text-slate-300 transition"
          >
            {loading ? 'SYNCING...' : 'REFRESH'}
          </button>
        )}
      </div>
    </div>
  );
};
