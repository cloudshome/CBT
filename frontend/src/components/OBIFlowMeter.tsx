import React from 'react';
import { OBIData } from '../types';
import { ArrowUpRight, ArrowDownRight, Scale } from 'lucide-react';

interface OBIFlowMeterProps {
  data?: OBIData | null;
}

export const OBIFlowMeter: React.FC<OBIFlowMeterProps> = ({ data }) => {
  if (!data) {
    return (
      <div className="bg-[#0b0f19] border border-[#1e293b] rounded-lg p-3 text-xs font-mono text-slate-500 flex items-center justify-center">
        <span>Awaiting L2 Order Book Depth Stream...</span>
      </div>
    );
  }

  const obiPct = data.obi_score * 100;
  const isBidHeavy = data.obi_score > 0;
  const vpinPct = data.flow_toxicity_vpin * 100;
  const isToxic = data.flow_toxicity_vpin > 0.65;

  return (
    <div className="bg-[#080b11] border border-[#1e293b] rounded-lg p-3 space-y-2.5 font-mono text-xs select-none">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-800 pb-2">
        <div className="flex items-center gap-1.5 text-slate-200 font-bold">
          <Scale size={14} className="text-sky-400" />
          <span>L2 Depth Imbalance (OBI) & VPIN</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span
            className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
              isToxic
                ? 'bg-rose-500/20 text-rose-400 border border-rose-500/40 animate-pulse'
                : isBidHeavy
                ? 'bg-[#00f0a8]/10 text-[#00f0a8] border border-[#00f0a8]/30'
                : 'bg-[#ff3b69]/10 text-[#ff3b69] border border-[#ff3b69]/30'
            }`}
          >
            {data.regime.replace(/_/g, ' ')}
          </span>
        </div>
      </div>

      {/* OBI Bid vs Ask Depth Meter */}
      <div className="space-y-1">
        <div className="flex justify-between text-[10px] text-slate-400">
          <span>Bid Pressure (${(data.bid_depth_total_usd / 1000).toFixed(0)}k)</span>
          <span className="font-bold text-slate-200">
            {obiPct > 0 ? `+${obiPct.toFixed(1)}%` : `${obiPct.toFixed(1)}%`}
          </span>
          <span>Ask Pressure (${(data.ask_depth_total_usd / 1000).toFixed(0)}k)</span>
        </div>

        {/* Bidirectional Depth Bar */}
        <div className="h-2 w-full bg-slate-800/80 rounded-full overflow-hidden flex relative">
          <div className="absolute left-1/2 top-0 bottom-0 w-0.5 bg-slate-600 z-10" />
          <div
            className="h-full bg-[#00f0a8] transition-all duration-300 ml-auto"
            style={{ width: `${Math.max(0, Math.min(50, 50 + obiPct / 2))}%` }}
          />
          <div
            className="h-full bg-[#ff3b69] transition-all duration-300 mr-auto"
            style={{ width: `${Math.max(0, Math.min(50, 50 - obiPct / 2))}%` }}
          />
        </div>
      </div>

      {/* VPIN Flow Toxicity & Microprice */}
      <div className="grid grid-cols-2 gap-2 pt-1">
        {/* Flow Toxicity (VPIN) */}
        <div className="bg-[#0d121d] border border-slate-800 rounded p-2 space-y-1">
          <div className="flex items-center justify-between text-[10px] text-slate-400">
            <span>VPIN Flow Toxicity</span>
            <span
              className={`font-bold ${
                vpinPct > 65 ? 'text-[#ff3b69]' : vpinPct > 45 ? 'text-amber-400' : 'text-[#00f0a8]'
              }`}
            >
              {vpinPct.toFixed(1)}%
            </span>
          </div>
          <div className="h-1.5 w-full bg-slate-800 rounded-full overflow-hidden">
            <div
              className={`h-full transition-all duration-300 ${
                vpinPct > 65 ? 'bg-[#ff3b69]' : vpinPct > 45 ? 'bg-amber-400' : 'bg-[#00f0a8]'
              }`}
              style={{ width: `${Math.min(100, vpinPct)}%` }}
            />
          </div>
        </div>

        {/* Microprice Skew */}
        <div className="bg-[#0d121d] border border-slate-800 rounded p-2 flex flex-col justify-between">
          <span className="text-[10px] text-slate-400">Microprice Shift</span>
          <div className="flex items-center gap-1 font-bold text-slate-200">
            {data.micro_price_shift >= 0 ? (
              <ArrowUpRight size={13} className="text-[#00f0a8]" />
            ) : (
              <ArrowDownRight size={13} className="text-[#ff3b69]" />
            )}
            <span>
              {data.micro_price_shift >= 0 ? '+' : ''}${data.micro_price_shift.toFixed(2)}
            </span>
          </div>
        </div>
      </div>

      {/* Narrative Readout */}
      <p className="text-[10px] text-slate-400 leading-relaxed border-t border-slate-800/60 pt-1.5">
        {data.narrative}
      </p>
    </div>
  );
};
