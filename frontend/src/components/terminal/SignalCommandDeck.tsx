import React from 'react';
import {
  Compass,
  ShieldCheck,
  Send,
  Target,
  Sliders,
  AlertTriangle,
  CheckCircle2,
  Clock,
} from 'lucide-react';
import { StyleSignalPlan, SignalExecutionState } from '../../types';

interface SignalCommandDeckProps {
  signals: StyleSignalPlan[];
  selectedStyle: StyleSignalPlan['style'];
  currentPrice?: number;
  onSelectStyle: (style: StyleSignalPlan['style']) => void;
  onSubmitToApproval: (signal: StyleSignalPlan) => void;
  directionFilter?: 'AUTO' | 'LONG' | 'SHORT';
  onDirectionFilterChange?: (dir: 'AUTO' | 'LONG' | 'SHORT') => void;
}

export const SignalCommandDeck: React.FC<SignalCommandDeckProps> = ({
  signals,
  selectedStyle,
  currentPrice,
  onSelectStyle,
  onSubmitToApproval,
  directionFilter = 'AUTO',
  onDirectionFilterChange,
}) => {
  const baseSignal = signals.find((s) => s.style === selectedStyle) || signals[0];
  const currentSignal = React.useMemo(() => {
    if (!baseSignal) return baseSignal;
    if (directionFilter === 'LONG') {
      return baseSignal.longPlan || baseSignal;
    }
    if (directionFilter === 'SHORT') {
      return baseSignal.shortPlan || baseSignal;
    }
    return baseSignal;
  }, [baseSignal, directionFilter]);

  const formatDuration = (secs: number) => {
    const mins = Math.floor(secs / 60);
    const s = secs % 60;
    return `${mins}m ${s}s`;
  };

  // Derive execution state relative to currentPrice if provided
  const curP = currentPrice ?? (currentSignal ? (currentSignal.entryZone[0] + currentSignal.entryZone[1]) / 2 : 0);
  const isSignalLong = currentSignal?.side === 'LONG';
  const eLow = currentSignal ? Math.min(currentSignal.entryZone[0], currentSignal.entryZone[1]) : 0;
  const eHigh = currentSignal ? Math.max(currentSignal.entryZone[0], currentSignal.entryZone[1]) : 0;

  let liveState: SignalExecutionState =
    currentSignal?.executionState || 'IN_ZONE';

  if (currentSignal && currentPrice !== undefined) {
    if (isSignalLong) {
      if (curP <= currentSignal.stopLoss || curP <= currentSignal.invalidationPrice) {
        liveState = 'INVALIDATED';
      } else if (curP < eLow) {
        liveState = 'AWAITING_RECLAIM';
      } else if (curP > eHigh) {
        liveState = 'WAITING_PULLBACK';
      } else {
        liveState = currentSignal.executionState || 'IN_ZONE';
      }
    } else {
      if (curP >= currentSignal.stopLoss || curP >= currentSignal.invalidationPrice) {
        liveState = 'INVALIDATED';
      } else if (curP > eHigh) {
        liveState = 'AWAITING_RECLAIM';
      } else if (curP < eLow) {
        liveState = 'WAITING_PULLBACK';
      } else {
        liveState = currentSignal.executionState || 'IN_ZONE';
      }
    }
  }

  const isInZone = liveState === 'IN_ZONE' || liveState === 'IN_ZONE_CONFIRMED' || liveState === 'IN_ZONE_AWAITING_ABSORPTION';

  const diffFromEntryLow = Number((eLow - curP).toFixed(2));
  const diffFromEntryHigh = Number((curP - eHigh).toFixed(2));

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

        {/* Direction Toggle & 5-Style Tabs */}
        <div className="flex items-center gap-2 flex-wrap">
          {/* 3-State Direction Pill Toggle (AUTO | LONG | SHORT) */}
          <div className="flex items-center bg-[#0d1322] border border-[#1e293b] rounded p-0.5 text-[10px]">
            {(['AUTO', 'LONG', 'SHORT'] as const).map((dir) => (
              <button
                key={dir}
                onClick={() => onDirectionFilterChange?.(dir)}
                className={`px-2 py-0.5 rounded font-bold tracking-wider transition-all ${
                  (directionFilter || 'AUTO') === dir
                    ? dir === 'LONG'
                      ? 'bg-emerald-500 text-slate-950 font-black shadow-sm'
                      : dir === 'SHORT'
                      ? 'bg-rose-500 text-white font-black shadow-sm'
                      : 'bg-cyan-500 text-slate-950 font-black shadow-sm'
                    : 'text-slate-400 hover:text-white'
                }`}
                title={`Filter setup direction by ${dir}`}
              >
                {dir}
              </button>
            ))}
          </div>

          {/* 5-Style Tabs */}
          <div className="flex items-center bg-[#0d1322] border border-[#1e293b] rounded p-0.5 text-[10px]">
            {signals.map((sig) => {
              const activePlan = directionFilter === 'LONG' ? (sig.longPlan || sig) : (directionFilter === 'SHORT' ? (sig.shortPlan || sig) : sig);
              return (
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
                    activePlan.side === 'LONG' ? 'bg-emerald-950 text-emerald-400' : 'bg-rose-950 text-rose-400'
                  }`}>
                    {activePlan.side}
                  </span>
                </button>
              );
            })}
          </div>
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
                  {currentSignal.entryTriggerState === 'IN_ZONE_CONFIRMED' && (
                    <span className="px-1.5 py-0.2 rounded text-[9px] font-bold bg-emerald-950 text-emerald-300 border border-emerald-500/60 flex items-center gap-1 animate-pulse">
                      ⚡ ORDERFLOW CONFIRMED
                    </span>
                  )}
                  {currentSignal.entryTriggerState === 'IN_ZONE_AWAITING_ABSORPTION' && (
                    <span className="px-1.5 py-0.2 rounded text-[9px] font-bold bg-cyan-950 text-cyan-300 border border-cyan-500/50 flex items-center gap-1">
                      ⏳ CVD PENDING
                    </span>
                  )}
                  {liveState === 'AWAITING_RECLAIM' && (
                    <span className="px-1.5 py-0.2 rounded text-[9px] font-bold bg-amber-950 text-amber-300 border border-amber-500/50 flex items-center gap-1 animate-pulse">
                      <AlertTriangle size={9} /> {isSignalLong ? 'BELOW ENTRY' : 'ABOVE ENTRY'}
                    </span>
                  )}
                  {liveState === 'IN_ZONE' && !currentSignal.entryTriggerState && (
                    <span className="px-1.5 py-0.2 rounded text-[9px] font-bold bg-emerald-950 text-emerald-300 border border-emerald-500/50 flex items-center gap-1">
                      <CheckCircle2 size={9} /> IN ZONE
                    </span>
                  )}
                  {liveState === 'WAITING_PULLBACK' && (
                    <span className="px-1.5 py-0.2 rounded text-[9px] font-bold bg-cyan-950 text-cyan-300 border border-cyan-500/50 flex items-center gap-1">
                      <Clock size={9} /> PULLBACK PENDING
                    </span>
                  )}
                  {liveState === 'INVALIDATED' && (
                    <span className="px-1.5 py-0.2 rounded text-[9px] font-bold bg-rose-950 text-rose-300 border border-rose-500/50">
                      ⛔ INVALIDATED
                    </span>
                  )}
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

              {/* Omniscient Confluence Badges */}
              {(currentSignal.candlestickConfirmation || currentSignal.smtDivergence) && (
                <div className="flex flex-wrap items-center gap-1.5 mb-2.5">
                  {currentSignal.candlestickConfirmation && (
                    <span className="px-2 py-0.5 rounded text-[10px] bg-amber-950/70 text-amber-300 border border-amber-500/40 font-mono">
                      🕯️ {currentSignal.candlestickConfirmation}
                    </span>
                  )}
                  {currentSignal.smtDivergence && (
                    <span className="px-2 py-0.5 rounded text-[10px] bg-purple-950/70 text-purple-300 border border-purple-500/40 font-mono">
                      🔄 {currentSignal.smtDivergence}
                    </span>
                  )}
                </div>
              )}

              {/* Vertical Execution Ladder */}
              <div className="space-y-1.5 text-[10px]">
                {isSignalLong ? (
                  <>
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

                    {/* Live Market Price if Above Entry Zone (Waiting for Pullback) */}
                    {liveState === 'WAITING_PULLBACK' && currentPrice !== undefined && (
                      <div className="p-1.5 rounded bg-cyan-950/40 border border-cyan-500/50 flex justify-between items-center text-cyan-300 font-bold text-[9px]">
                        <span className="flex items-center gap-1">
                          <span className="inline-block w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse"></span>
                          LIVE MARKET PRICE:
                        </span>
                        <span>${curP.toLocaleString()} (+${diffFromEntryHigh.toLocaleString()} above entry zone)</span>
                      </div>
                    )}

                    {/* Entry Zone */}
                    <div className={`p-2 rounded border text-white font-bold my-1 ${
                      isInZone
                        ? 'bg-emerald-950/70 border-emerald-500 shadow-sm shadow-emerald-500/30'
                        : 'bg-indigo-950/40 border-indigo-500/50'
                    }`}>
                      <div className="flex justify-between items-center">
                        <div className="flex items-center gap-1.5">
                          <Target size={13} className={isInZone ? 'text-emerald-400' : 'text-cyan-400'} />
                          <span>OPTIMAL ENTRY ZONE:</span>
                        </div>
                        <div className="flex items-center gap-1.5">
                          {currentSignal.zoneOrigin && (
                            <span className="text-[7.5px] uppercase tracking-wider px-1 py-0.2 rounded bg-indigo-900/60 border border-indigo-500/40 text-cyan-300 font-mono">
                              {currentSignal.zoneOrigin}
                            </span>
                          )}
                          <span className="text-cyan-300 font-mono">
                            ${currentSignal.entryZone[0].toLocaleString()} – ${currentSignal.entryZone[1].toLocaleString()}
                          </span>
                        </div>
                      </div>
                      {isInZone && currentPrice !== undefined && (
                        <div className="text-[9px] text-emerald-300 font-normal pt-1 mt-1 border-t border-emerald-500/30 flex justify-between items-center">
                          <span>● LIVE TICK IN ZONE:</span>
                          <span className="font-bold text-white">${curP.toLocaleString()}</span>
                        </div>
                      )}
                    </div>

                    {/* Live Market Price if Below Entry Zone (Awaiting Reclaim Warning) */}
                    {liveState === 'AWAITING_RECLAIM' && currentPrice !== undefined && (
                      <div className="p-2 rounded bg-amber-950/70 border border-amber-500/70 text-amber-300 shadow-md">
                        <div className="flex justify-between items-center font-bold">
                          <span className="flex items-center gap-1 text-white">
                            <span className="inline-block w-2 h-2 rounded-full bg-amber-400 animate-pulse"></span>
                            LIVE MARKET PRICE:
                          </span>
                          <span className="text-white font-extrabold text-[11px]">${curP.toLocaleString()}</span>
                          <span className="text-amber-400 font-mono">
                            (-${diffFromEntryLow.toLocaleString()} below entry)
                          </span>
                        </div>
                        <div className="text-[9px] text-amber-200 mt-1.5 pt-1.5 border-t border-amber-500/30 flex items-center gap-1.5">
                          <AlertTriangle size={12} className="text-amber-400 shrink-0" />
                          <span>
                            Market price has broken below optimal entry. Do NOT market buy into drawdown. Awaiting candle close above ${eLow.toLocaleString()} to confirm reclaim.
                          </span>
                        </div>
                      </div>
                    )}

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
                  </>
                ) : (
                  <>
                    {/* Short Setup Ladder */}
                    <div className="flex justify-between items-center p-1 rounded bg-slate-900/60 border border-slate-800 text-slate-400 text-[9px]">
                      <span>STRUCTURAL INVALIDATION:</span>
                      <span className="font-bold text-rose-400">${currentSignal.invalidationPrice.toLocaleString()}</span>
                    </div>
                    <div className="flex justify-between items-center p-1.5 rounded bg-rose-950/20 border border-rose-500/30 text-rose-300">
                      <span className="font-semibold">STOP LOSS:</span>
                      <span className="font-bold text-white">${currentSignal.stopLoss.toLocaleString()}</span>
                      <span className="text-rose-400 font-mono">-1.0R</span>
                    </div>

                    {/* Live Market Price if Above Entry Zone (Short Awaiting Rejection Warning) */}
                    {liveState === 'AWAITING_RECLAIM' && currentPrice !== undefined && (
                      <div className="p-2 rounded bg-amber-950/70 border border-amber-500/70 text-amber-300 shadow-md">
                        <div className="flex justify-between items-center font-bold">
                          <span className="flex items-center gap-1 text-white">
                            <span className="inline-block w-2 h-2 rounded-full bg-amber-400 animate-pulse"></span>
                            LIVE MARKET PRICE:
                          </span>
                          <span className="text-white font-extrabold text-[11px]">${curP.toLocaleString()}</span>
                          <span className="text-amber-400 font-mono">
                            (+${diffFromEntryHigh.toLocaleString()} above entry)
                          </span>
                        </div>
                        <div className="text-[9px] text-amber-200 mt-1.5 pt-1.5 border-t border-amber-500/30 flex items-center gap-1.5">
                          <AlertTriangle size={12} className="text-amber-400 shrink-0" />
                          <span>
                            Market price has expanded above short entry. Do NOT market-sell into rally. Awaiting rejection below ${eHigh.toLocaleString()} before entry.
                          </span>
                        </div>
                      </div>
                    )}

                    {/* Entry Zone */}
                    <div className={`p-2 rounded border text-white font-bold my-1 ${
                      isInZone
                        ? 'bg-emerald-950/70 border-emerald-500 shadow-sm shadow-emerald-500/30'
                        : 'bg-indigo-950/40 border-indigo-500/50'
                    }`}>
                      <div className="flex justify-between items-center">
                        <div className="flex items-center gap-1.5">
                          <Target size={13} className={isInZone ? 'text-emerald-400' : 'text-cyan-400'} />
                          <span>OPTIMAL ENTRY ZONE:</span>
                        </div>
                        <div className="flex items-center gap-1.5">
                          {currentSignal.zoneOrigin && (
                            <span className="text-[7.5px] uppercase tracking-wider px-1 py-0.2 rounded bg-indigo-900/60 border border-indigo-500/40 text-rose-300 font-mono">
                              {currentSignal.zoneOrigin}
                            </span>
                          )}
                          <span className="text-cyan-300 font-mono">
                            ${currentSignal.entryZone[0].toLocaleString()} – ${currentSignal.entryZone[1].toLocaleString()}
                          </span>
                        </div>
                      </div>
                      {isInZone && currentPrice !== undefined && (
                        <div className="text-[9px] text-emerald-300 font-normal pt-1 mt-1 border-t border-emerald-500/30 flex justify-between items-center">
                          <span>● LIVE TICK IN ZONE:</span>
                          <span className="font-bold text-white">${curP.toLocaleString()}</span>
                        </div>
                      )}
                    </div>

                    {/* Live Market Price if Below Entry Zone (Short Waiting for Pullback Up) */}
                    {liveState === 'WAITING_PULLBACK' && currentPrice !== undefined && (
                      <div className="p-1.5 rounded bg-cyan-950/40 border border-cyan-500/50 flex justify-between items-center text-cyan-300 font-bold text-[9px]">
                        <span className="flex items-center gap-1">
                          <span className="inline-block w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse"></span>
                          LIVE MARKET PRICE:
                        </span>
                        <span>${curP.toLocaleString()} (-${diffFromEntryLow.toLocaleString()} below entry zone)</span>
                      </div>
                    )}

                    {/* Take Profits */}
                    <div className="flex justify-between items-center p-1.5 rounded bg-emerald-950/20 border border-emerald-500/30 text-emerald-300">
                      <span className="font-semibold">TP1 (Local Structure Pivot):</span>
                      <span className="font-bold text-white">${currentSignal.tp1.toLocaleString()}</span>
                      <span className="text-emerald-400 font-mono">+1.5R</span>
                    </div>
                    <div className="flex justify-between items-center p-1.5 rounded bg-emerald-950/20 border border-emerald-500/30 text-emerald-300">
                      <span className="font-semibold">TP2 (Macro Liquidity Pool):</span>
                      <span className="font-bold text-white">${currentSignal.tp2.toLocaleString()}</span>
                      <span className="text-emerald-400 font-mono">+3.1R</span>
                    </div>
                    <div className="flex justify-between items-center p-1.5 rounded bg-emerald-950/20 border border-emerald-500/30 text-emerald-300">
                      <span className="font-semibold">TP3 (Moonbag Target):</span>
                      <span className="font-bold text-white">${currentSignal.tp3.toLocaleString()}</span>
                      <span className="text-emerald-400 font-mono">+6.2R</span>
                    </div>
                  </>
                )}
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
            {liveState === 'AWAITING_RECLAIM' && (
              <div className="mb-2 p-1.5 rounded bg-amber-950/60 border border-amber-500/50 text-[10px] text-amber-300 flex items-center gap-1.5">
                <AlertTriangle size={12} className="text-amber-400 shrink-0" />
                <span>Queueing this trade will require structural reclaim confirmation before order dispatch.</span>
              </div>
            )}
            {liveState === 'INVALIDATED' && (
              <div className="mb-2 p-1.5 rounded bg-rose-950/60 border border-rose-500/50 text-[10px] text-rose-300 flex items-center gap-1.5">
                <AlertTriangle size={12} className="text-rose-400 shrink-0" />
                <span>Setup breached stop loss / invalidation. Submission blocked by risk gate.</span>
              </div>
            )}
            <button
              onClick={() => onSubmitToApproval(currentSignal)}
              disabled={liveState === 'INVALIDATED'}
              className={`w-full py-2 px-3 rounded font-bold text-xs flex items-center justify-center gap-2 shadow-md transition-all active:scale-[0.99] ${
                liveState === 'INVALIDATED'
                  ? 'bg-slate-800 text-slate-500 cursor-not-allowed border border-slate-700'
                  : liveState === 'AWAITING_RECLAIM'
                  ? 'bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 text-slate-950 shadow-amber-500/20'
                  : 'bg-gradient-to-r from-cyan-500 to-indigo-600 hover:from-cyan-400 hover:to-indigo-500 text-slate-950 shadow-cyan-500/20'
              }`}
            >
              <Send size={13} />
              <span>
                {liveState === 'INVALIDATED'
                  ? 'SETUP INVALIDATED (STOP BREACHED)'
                  : liveState === 'AWAITING_RECLAIM'
                  ? 'SUBMIT CONDITIONAL RECLAIM TO BLOTTER'
                  : 'SUBMIT TO HUMAN APPROVAL BLOTTER'}
              </span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
