import React, { useState } from 'react';
import {
  Award,
  History,
  Radar,
  Info,
} from 'lucide-react';
import { InstitutionalConfluenceData, ScorecardFactorWeight } from '../../types';

interface InstitutionalConfluenceRadarProps {
  confluence: InstitutionalConfluenceData;
}

export const InstitutionalConfluenceRadar: React.FC<InstitutionalConfluenceRadarProps> = ({
  confluence,
}) => {
  const [activeFactor, setActiveFactor] = useState<ScorecardFactorWeight | null>(null);

  const { qualityScore, qualityBadge, factorWeights, confluenceRadar, qualityScoreHistory } = confluence;

  // SVG Radar Coordinates Calculation
  // 6 Axes: Structure, Trend, Flow, Macro, RiskReward, Derivatives
  const axes = [
    { label: 'STRUCTURE', value: confluenceRadar.structure, angle: 0 },
    { label: 'TREND', value: confluenceRadar.trend, angle: 60 },
    { label: 'FLOW', value: confluenceRadar.flow, angle: 120 },
    { label: 'MACRO', value: confluenceRadar.macro, angle: 180 },
    { label: 'R:R', value: confluenceRadar.riskReward, angle: 240 },
    { label: 'DERIVATIVES', value: confluenceRadar.derivatives, angle: 300 },
  ];

  const center = 75;
  const radius = 55;

  const points = axes.map((a) => {
    const rad = (a.angle - 90) * (Math.PI / 180);
    const r = (a.value / 100) * radius;
    const x = center + r * Math.cos(rad);
    const y = center + r * Math.sin(rad);
    return `${x},${y}`;
  }).join(' ');

  const gridLevels = [0.33, 0.66, 1.0];

  return (
    <div className="w-full bg-[#080c16] border border-[#1e293b] rounded-lg p-3 text-xs font-mono text-slate-300 flex flex-col justify-between select-none">
      {/* Header: Institutional Score & Badge */}
      <div className="flex items-center justify-between pb-2 mb-2 border-b border-[#1e293b]">
        <div className="flex items-center gap-2">
          <Award size={14} className="text-amber-400" />
          <span className="font-bold text-white text-[11px] tracking-wider">
            INSTITUTIONAL CONFLUENCE RADAR
          </span>
        </div>
        <span className="text-[10px] text-slate-500">
          10-Factor Weighted Evidence Matrix
        </span>
      </div>

      {/* Top Section: Radial Score Gauge + Confluence Radar + History Sparkline */}
      <div className="grid grid-cols-1 md:grid-cols-12 gap-3 items-center mb-3">
        {/* Quality Score Dial & Badge (4 cols) */}
        <div className="md:col-span-4 bg-[#0c1222] border border-[#1e293b] rounded-lg p-3 flex flex-col items-center justify-center text-center relative overflow-hidden">
          <div className="text-[9px] text-slate-500 uppercase tracking-widest mb-1">
            TRADE QUALITY SCORE
          </div>

          <div className="relative flex items-center justify-center my-1">
            <svg className="w-24 h-24 transform -rotate-90">
              <circle
                cx="48"
                cy="48"
                r="38"
                stroke="currentColor"
                strokeWidth="6"
                className="text-slate-800 fill-none"
              />
              <circle
                cx="48"
                cy="48"
                r="38"
                stroke="currentColor"
                strokeWidth="6"
                strokeDasharray={`${2 * Math.PI * 38}`}
                strokeDashoffset={`${2 * Math.PI * 38 * (1 - qualityScore / 100)}`}
                strokeLinecap="round"
                className={`fill-none transition-all duration-700 ${
                  qualityScore >= 85
                    ? 'text-emerald-400'
                    : qualityScore >= 70
                    ? 'text-cyan-400'
                    : qualityScore >= 55
                    ? 'text-amber-400'
                    : 'text-rose-500'
                }`}
              />
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-2xl font-black text-white">{qualityScore}</span>
              <span className="text-[10px] text-slate-400">/ 100</span>
            </div>
          </div>

          <div className="flex items-center gap-2 mt-1">
            <span className={`px-2.5 py-0.5 rounded font-black text-[12px] border ${
              qualityBadge === 'A+'
                ? 'bg-emerald-950/80 border-emerald-500/50 text-emerald-400 shadow-sm shadow-emerald-500/20'
                : qualityBadge === 'A'
                ? 'bg-cyan-950/80 border-cyan-500/50 text-cyan-400 shadow-sm shadow-cyan-500/20'
                : qualityBadge === 'B'
                ? 'bg-amber-950/80 border-amber-500/50 text-amber-400'
                : 'bg-rose-950/80 border-rose-500/50 text-rose-400'
            }`}>
              GRADE: {qualityBadge}
            </span>
          </div>
          <span className="text-[9px] text-slate-500 mt-1">
            {qualityScore >= 80 ? 'Institutional Edge Confirmed' : 'Selective Edge Caution'}
          </span>
        </div>

        {/* Radar Visualization (4 cols) */}
        <div className="md:col-span-4 bg-[#0c1222] border border-[#1e293b] rounded-lg p-2 flex flex-col items-center justify-center">
          <div className="text-[9px] text-slate-500 uppercase tracking-wider mb-1 flex items-center gap-1">
            <Radar size={11} className="text-cyan-400" /> CONFLUENCE RADAR
          </div>
          <svg className="w-36 h-36" viewBox="0 0 150 150">
            {/* Background grid concentric polygons */}
            {gridLevels.map((lvl, i) => (
              <polygon
                key={i}
                points={axes.map((a) => {
                  const rad = (a.angle - 90) * (Math.PI / 180);
                  const r = lvl * radius;
                  return `${center + r * Math.cos(rad)},${center + r * Math.sin(rad)}`;
                }).join(' ')}
                fill="none"
                stroke="#1e293b"
                strokeWidth="1"
              />
            ))}

            {/* Radar Spoke Lines */}
            {axes.map((a, i) => {
              const rad = (a.angle - 90) * (Math.PI / 180);
              const x2 = center + radius * Math.cos(rad);
              const y2 = center + radius * Math.sin(rad);
              return <line key={i} x1={center} y1={center} x2={x2} y2={y2} stroke="#1e293b" strokeWidth="1" />;
            })}

            {/* Filled Polygon for Confluence Score */}
            <polygon
              points={points}
              fill="rgba(6, 182, 212, 0.25)"
              stroke="#06b6d4"
              strokeWidth="1.5"
            />

            {/* Data Point Dots */}
            {axes.map((a, i) => {
              const rad = (a.angle - 90) * (Math.PI / 180);
              const r = (a.value / 100) * radius;
              const x = center + r * Math.cos(rad);
              const y = center + r * Math.sin(rad);
              return <circle key={i} cx={x} cy={y} r="2.5" fill="#38bdf8" />;
            })}
          </svg>
        </div>

        {/* Score History Sparkline (4 cols) */}
        <div className="md:col-span-4 bg-[#0c1222] border border-[#1e293b] rounded-lg p-3 flex flex-col justify-between h-full">
          <div>
            <div className="flex items-center justify-between text-[9px] text-slate-500 uppercase tracking-wider mb-2">
              <span className="flex items-center gap-1">
                <History size={11} className="text-indigo-400" /> DRIFT MONITOR
              </span>
              <span>LAST 20 EVALS</span>
            </div>

            {/* Sparkline Bar Chart */}
            <div className="flex items-end justify-between gap-1 h-14 bg-[#070b16] p-1.5 rounded border border-[#1e293b]/70">
              {qualityScoreHistory.map((val, idx) => (
                <div
                  key={idx}
                  className="flex-1 flex flex-col items-center justify-end h-full"
                  title={`Eval #${idx + 1}: ${val}/100`}
                >
                  <div
                    className={`w-full rounded-t-sm transition-all ${
                      val >= 85
                        ? 'bg-emerald-400'
                        : val >= 70
                        ? 'bg-cyan-400'
                        : val >= 55
                        ? 'bg-amber-400'
                        : 'bg-rose-500'
                    }`}
                    style={{ height: `${(val / 100) * 100}%` }}
                  ></div>
                </div>
              ))}
            </div>
          </div>

          <div className="mt-2 text-[9px] text-slate-400 flex items-center justify-between border-t border-[#1e293b]/70 pt-1.5">
            <span>Model Edge: Stable (+0.43R)</span>
            <span className="text-emerald-400 font-bold">Passed Hurdle</span>
          </div>
        </div>
      </div>

      {/* 10-Factor Weighted Breakdown Matrix */}
      <div className="bg-[#0b101c] border border-[#1e293b] rounded-lg p-2.5">
        <div className="flex items-center justify-between mb-2 text-[10px] text-slate-400">
          <span className="font-bold text-white uppercase tracking-wider">
            10-Factor Scoring Fingerprint
          </span>
          <span>Click any factor to inspect quantitative rationale</span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {factorWeights.map((f) => {
            const pct = (f.score / f.max) * 100;
            const isSelected = activeFactor?.name === f.name;
            return (
              <div
                key={f.name}
                onClick={() => setActiveFactor(isSelected ? null : f)}
                className={`p-1.5 rounded border transition-all cursor-pointer ${
                  isSelected
                    ? 'border-cyan-400 bg-cyan-950/40 shadow-sm'
                    : 'border-[#1e293b] bg-[#0c1222] hover:border-slate-700'
                }`}
              >
                <div className="flex items-center justify-between text-[10px] mb-1">
                  <div className="flex items-center gap-1.5">
                    <span className="font-semibold text-slate-200">{f.name}</span>
                    <span className="text-[9px] text-slate-500 font-mono">({f.weightPct}%)</span>
                  </div>
                  <span className={`font-bold ${pct >= 85 ? 'text-emerald-400' : pct >= 65 ? 'text-cyan-400' : 'text-amber-400'}`}>
                    {f.score} / {f.max}
                  </span>
                </div>

                {/* Progress Bar */}
                <div className="w-full h-1.5 rounded-full bg-slate-900 overflow-hidden">
                  <div
                    className={`h-full transition-all duration-500 ${
                      pct >= 85
                        ? 'bg-emerald-400'
                        : pct >= 65
                        ? 'bg-cyan-400'
                        : 'bg-amber-400'
                    }`}
                    style={{ width: `${pct}%` }}
                  ></div>
                </div>

                {/* Plain-English Rationale on Selected/Hover */}
                {isSelected && (
                  <div className="mt-1.5 pt-1.5 border-t border-cyan-500/30 text-[9px] text-cyan-200 flex items-start gap-1">
                    <Info size={11} className="shrink-0 mt-0.5 text-cyan-400" />
                    <span>{f.rationale}</span>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
