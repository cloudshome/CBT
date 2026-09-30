import React from 'react';
import {
  Compass,
  ShieldCheck,
  Send,
  Target,
  Sliders,
} from 'lucide-react';
import { StyleSignalPlan } from '../../types';

interface SignalCommandDeckProps {
  signals: StyleSignalPlan[];
  selectedStyle: StyleSignalPlan['style'];
  onSelectStyle: (style: StyleSignalPlan['style']) => void;
  onSubmitToApproval: (signal: StyleSignalPlan) => void;
}

export const SignalCommandDeck: React.FC<SignalCommandDeckProps> = ({
  signals,
  selectedStyle,
  onSelectStyle,
  onSubmitToApproval,
}) => {
  const currentSignal = signals.find((s) => s.style === selectedStyle) || signals[0];

  const formatDuration = (secs: number) => {
    const mins = Math.floor(secs / 60);
    const s = secs % 60;
    return `${mins}m ${s}s`;
  };

  return (
    <div className="w-full bg-[#080c16] border border-[#1e293b] rounded-lg p-3 text-xs font-mono text-slate-300 select-none">
      {/* Title & 5-Style Horizontal Switcher */}
      <div className="flex flex-wrap items-center justify-between pb-2.5 mb-3 border-b border-[#1e293b] gap-2">
        <div className="flex items-center gap-2">
          <Compass size={14} className="text-cyan-400" />
          <span className="font-bold text-white text-[11px] tracking-wider">
            SIGNAL COMMAND DECK (5 TRADING HORIZONS)
          </span>
        </div>

        {/* 5-Style Tabs */}
        <div className="flex items-center bg-[#0d1322] border border-[#1e293b] rounded p-0.5 text-[10px]">
          {signals.map((sig) => (
            <button
              key={sig.style}
              onClick={() => onSelectStyle(sig.style)}
              className={`px-3 py-1 rounded font-semibold transition-all flex items-center gap-1.5 ${
                selectedStyle === sig.style
                  ? 'bg-cyan-500 text-slate-950 font-bold shadow-sm shadow-cyan-500/20'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <span>{sig.style}</span>
              <span className={`text-[8px] px-1 py-0.2 rounded font-bold ${
                sig.side === 'LONG' ? 'bg-emerald-950 text-emerald-400' : 'bg-rose-950 text-rose-400'
              }`}>
                {sig.side}
              </span>
            </button>
          ))}
        </div>
      </div>

      {/* Selected Style Detail Card */}
      {currentSignal && (
        <div className="grid grid-cols-1 xl:grid-cols-12 gap-3 items-stretch">
          {/* Left: Thesis, Execution Ladder & Target Levels (7 cols) */}
          <div className="xl:col-span-7 bg-[#0c1222] border border-[#1e293b] rounded-lg p-3 flex flex-col justify-between">
            <div>
              {/* Header Badge */}
              <div className="flex items-center justify-between pb-2 mb-2 border-b border-[#1e293b]/70">
                <div className="flex items-center gap-2">
                  <span className={`px-2 py-0.5 rounded font-black text-[12px] ${
                    currentSignal.side === 'LONG'
                      ? 'bg-emerald-500 text-slate-950 font-black'
                      : 'bg-rose-500 text-white font-black'
                  }`}>
                    {currentSignal.style} {currentSignal.side}
                  </span>
                  <span className="text-[10px] text-slate-400 font-mono">
                    Timeframe: {currentSignal.timeframe}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-slate-400">Score:</span>
                  <span className="font-bold text-white text-[11px] px-1.5 py-0.2 rounded bg-cyan-950 border border-cyan-500/30 text-cyan-300">
                    {currentSignal.score} / 100
                  </span>
                  <span className="text-emerald-400 font-bold text-[11px]">
                    R:R {currentSignal.riskRewardRatio}:1
                  </span>
                </div>
              </div>

              {/* Thesis Statement */}
              <p className="text-[11px] text-slate-300 leading-relaxed mb-3">
                <span className="font-bold text-cyan-400">THESIS: </span>
                {currentSignal.thesis}
              </p>

              {/* Vertical Execution Ladder */}
              <div className="space-y-1.5 text-[10px]">
                {/* Take Profit Ladder */}
                <div className="flex justify-between items-center p-1.5 rounded bg-emerald-950/20 border border-emerald-500/30 text-emerald-300">
                  <span className="font-semibold">TP3 (Moonbag Target):</span>
                  <span className="font-bold text-white">${currentSignal.tp3.toLocaleString()}</span>
                  <span className="text-emerald-400 font-mono">+6.2R</span>
                </div>
                <div className="flex justify-between items-center p-1.5 rounded bg-emerald-950/20 border border-emerald-500/30 text-emerald-300">
                  <span className="font-semibold">TP2 (Macro Resistance):</span>
                  <span className="font-bold text-white">${currentSignal.tp2.toLocaleString()}</span>
                  <span className="text-emerald-400 font-mono">+3.1R</span>
                </div>
                <div className="flex justify-between items-center p-1.5 rounded bg-emerald-950/20 border border-emerald-500/30 text-emerald-300">
                  <span className="font-semibold">TP1 (Local Structure Pivot):</span>
                  <span className="font-bold text-white">${currentSignal.tp1.toLocaleString()}</span>
                  <span className="text-emerald-400 font-mono">+1.5R</span>
                </div>

                {/* Entry Zone */}
                <div className="flex justify-between items-center p-2 rounded bg-indigo-950/40 border border-indigo-500/50 text-white font-bold my-1">
                  <div className="flex items-center gap-1.5">
                    <Target size={13} className="text-cyan-400" />
                    <span>OPTIMAL ENTRY ZONE:</span>
                  </div>
                  <span className="text-cyan-300 font-mono">
                    ${currentSignal.entryZone[0].toLocaleString()} – ${currentSignal.entryZone[1].toLocaleString()}
                  </span>
                </div>

                {/* Stop Loss & Invalidation */}
                <div className="flex justify-between items-center p-1.5 rounded bg-rose-950/20 border border-rose-500/30 text-rose-300">
                  <span className="font-semibold">STOP LOSS:</span>
                  <span className="font-bold text-white">${currentSignal.stopLoss.toLocaleString()}</span>
                  <span className="text-rose-400 font-mono">-1.0R</span>
                </div>
                <div className="flex justify-between items-center p-1 rounded bg-slate-900/60 border border-slate-800 text-slate-400 text-[9px]">
                  <span>STRUCTURAL INVALIDATION:</span>
                  <span className="font-bold text-rose-400">${currentSignal.invalidationPrice.toLocaleString()}</span>
                </div>
              </div>
            </div>
          </div>

          {/* Right: Sizing, Whipsaw Guard & Approval Action (5 cols) */}
          <div className="xl:col-span-5 bg-[#0c1222] border border-[#1e293b] rounded-lg p-3 flex flex-col justify-between">
            <div>
              {/* Half-Kelly Sizing Box */}
              <div className="pb-2 mb-2 border-b border-[#1e293b]/70">
                <div className="flex items-center justify-between text-[10px] text-slate-400 mb-1.5">
                  <span className="font-bold text-white uppercase tracking-wider flex items-center gap-1">
                    <Sliders size={11} className="text-cyan-400" /> Position Sizing &amp; Risk
                  </span>
                  <span className="text-cyan-400 font-mono font-bold">
                    Half-Kelly: {currentSignal.halfKellyMultiplier}x
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-2 text-[10px]">
                  <div className="p-1.5 rounded bg-[#090e1c] border border-[#1e293b]">
                    <span className="text-slate-500 text-[9px] block">SUGGESTED RISK</span>
                    <span className="font-bold text-emerald-400 text-[11px]">
                      {currentSignal.suggestedRiskPct}% of Equity
                    </span>
                  </div>
                  <div className="p-1.5 rounded bg-[#090e1c] border border-[#1e293b]">
                    <span className="text-slate-500 text-[9px] block">NOTIONAL CAPITAL</span>
                    <span className="font-bold text-white text-[11px]">
                      ${currentSignal.notionalUsd.toLocaleString()} USD
                    </span>
                  </div>
                </div>
              </div>

              {/* State Memory & Whipsaw Guard */}
              <div className="p-2 rounded bg-[#090e1c] border border-[#1e293b] space-y-1.5 text-[10px] mb-3">
                <div className="flex items-center justify-between text-[9px] text-slate-400 font-bold uppercase tracking-wider pb-1 border-b border-[#1e293b]/70">
                  <span className="flex items-center gap-1 text-emerald-400">
                    <ShieldCheck size={11} /> Whipsaw Guard Telemetry
                  </span>
                  <span className="text-cyan-400">STABLE</span>
                </div>

                <div className="flex justify-between">
                  <span className="text-slate-400">Stable Since:</span>
                  <span className="font-bold text-white">{formatDuration(currentSignal.stableDurationSecs)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Reaffirmations Counter:</span>
                  <span className="font-bold text-emerald-400">{currentSignal.reaffirmsCount} consecutive bars</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Cooldown Guard:</span>
                  <span className="font-bold text-cyan-400">
                    {currentSignal.cooldownRemainingSecs === 0 ? 'Clear (Ready to Deploy)' : `${currentSignal.cooldownRemainingSecs}s active`}
                  </span>
                </div>
              </div>
            </div>

            {/* Submit to Approval Blotter Action Button */}
            <button
              onClick={() => onSubmitToApproval(currentSignal)}
              className="w-full py-2 px-3 rounded font-bold text-xs flex items-center justify-center gap-2 bg-gradient-to-r from-cyan-500 to-indigo-600 hover:from-cyan-400 hover:to-indigo-500 text-slate-950 shadow-md shadow-cyan-500/20 transition-all active:scale-[0.99]"
            >
              <Send size={13} />
              <span>SUBMIT TO HUMAN APPROVAL BLOTTER</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
