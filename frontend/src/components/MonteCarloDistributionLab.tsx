import React, { useState, useMemo } from 'react';
import {
  BarChart2,
  Compass,
  HelpCircle,
  Play,
  RotateCw,
  ShieldAlert,
  Sparkles,
  TrendingDown,
  TrendingUp,
} from 'lucide-react';
import { MonteCarloStressReport, MonteCarloTrajectoryResult } from '../types';
import { api } from '../services/api';

interface MonteCarloDistributionLabProps {
  symbol?: string;
  timeframe?: string;
  initialReport?: MonteCarloStressReport | null;
  onSimulationComplete?: (report: MonteCarloStressReport) => void;
}

export const MonteCarloDistributionLab: React.FC<MonteCarloDistributionLabProps> = ({
  symbol = 'BTC/USDT',
  timeframe = '15m',
  initialReport = null,
  onSimulationComplete,
}) => {
  // Configurable Simulation Parameters (defaults match Hunid Capital Film 031: $100k, 8% return, 18% vol, 5Y, 10k paths)
  const [initialCapital, setInitialCapital] = useState<number>(100000);
  const [horizonYears, setHorizonYears] = useState<number>(5.0);
  const [expectedReturn, setExpectedReturn] = useState<number>(0.08); // 8% annual drift
  const [volatility, setVolatility] = useState<number>(0.18); // 18% annual vol
  const [numPaths, setNumPaths] = useState<number>(10000);
  const [running, setRunning] = useState<boolean>(false);
  const [report, setReport] = useState<MonteCarloStressReport | null>(initialReport);

  // Path Archetype Visibility Toggles
  const [showSmoothWinner, setShowSmoothWinner] = useState<boolean>(true);
  const [showChoppySurvivor, setShowChoppySurvivor] = useState<boolean>(true);
  const [showDeepDrawdown, setShowDeepDrawdown] = useState<boolean>(true);
  const [showBelowStart, setShowBelowStart] = useState<boolean>(true);

  // Hover Tooltip State
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  const trajectory: MonteCarloTrajectoryResult | undefined = report?.trajectory;

  // Run Simulation Handler
  const handleRunSimulation = async (autoCalibrate: boolean = false) => {
    setRunning(true);
    try {
      const res = await api.runMonteCarloStressTest(symbol as any, timeframe as any, {
        initialCapital,
        annualReturn: expectedReturn,
        annualVolatility: volatility,
        horizonYears,
        numPaths,
        steps: horizonYears <= 1.0 ? 30 : 60,
        autoCalibrate,
      });

      if (autoCalibrate && res.calibrated_annual_return !== undefined && res.calibrated_annual_volatility !== undefined) {
        setExpectedReturn(res.calibrated_annual_return);
        setVolatility(res.calibrated_annual_volatility);
      }

      setReport(res);
      if (onSimulationComplete) {
        onSimulationComplete(res);
      }
    } catch (err) {
      console.error('Failed to run Monte Carlo trajectory simulation:', err);
    } finally {
      setRunning(false);
    }
  };

  // SVG Chart Geometry Calculations
  const chartGeometry = useMemo(() => {
    if (!trajectory || !trajectory.steps || trajectory.steps.length === 0) {
      return null;
    }

    const steps = trajectory.steps;
    const width = 900;
    const height = 360;
    const padding = { top: 30, right: 40, bottom: 40, left: 75 };
    const innerWidth = width - padding.left - padding.right;
    const innerHeight = height - padding.top - padding.bottom;

    // Find min and max value across all percentiles and paths
    let minVal = initialCapital * 0.4;
    let maxVal = initialCapital * 1.6;

    steps.forEach((s) => {
      minVal = Math.min(minVal, s.p5, s.below_start, s.deep_drawdown);
      maxVal = Math.max(maxVal, s.p95, s.smooth_winner, s.choppy_survivor);
    });

    // Add 10% breathing room
    const range = maxVal - minVal;
    minVal = Math.max(0, minVal - range * 0.05);
    maxVal = maxVal + range * 0.08;

    const getX = (index: number) => padding.left + (index / (steps.length - 1)) * innerWidth;
    const getY = (val: number) => padding.top + innerHeight - ((val - minVal) / (maxVal - minVal)) * innerHeight;

    // Build SVG Area Path for 90% confidence band (p5 to p95)
    let area90 = `M ${getX(0)} ${getY(steps[0].p95)}`;
    for (let i = 1; i < steps.length; i++) {
      area90 += ` L ${getX(i)} ${getY(steps[i].p95)}`;
    }
    for (let i = steps.length - 1; i >= 0; i--) {
      area90 += ` L ${getX(i)} ${getY(steps[i].p5)}`;
    }
    area90 += ' Z';

    // Build SVG Area Path for 50% confidence band (p25 to p75)
    let area50 = `M ${getX(0)} ${getY(steps[0].p75)}`;
    for (let i = 1; i < steps.length; i++) {
      area50 += ` L ${getX(i)} ${getY(steps[i].p75)}`;
    }
    for (let i = steps.length - 1; i >= 0; i--) {
      area50 += ` L ${getX(i)} ${getY(steps[i].p25)}`;
    }
    area50 += ' Z';

    // Build Polyline Points
    const makeLine = (key: 'p50' | 'smooth_winner' | 'choppy_survivor' | 'deep_drawdown' | 'below_start') => {
      return steps.map((s, idx) => `${getX(idx)},${getY(s[key])}`).join(' ');
    };

    // Horizontal baseline for starting capital
    const baselineY = getY(initialCapital);

    // Y-Axis Grid Ticks (5 ticks)
    const yTicks = [0, 0.25, 0.5, 0.75, 1.0].map((t) => {
      const val = minVal + t * (maxVal - minVal);
      return { val, y: getY(val) };
    });

    // X-Axis Labels (up to 7 intervals)
    const xInterval = Math.max(1, Math.floor(steps.length / 6));
    const xLabels = steps
      .map((s, idx) => ({ step: s.step, label: s.time_label, x: getX(idx), index: idx }))
      .filter((_, idx) => idx % xInterval === 0 || idx === steps.length - 1);

    return {
      width,
      height,
      padding,
      innerWidth,
      innerHeight,
      minVal,
      maxVal,
      getX,
      getY,
      area90,
      area50,
      baselineY,
      p50Line: makeLine('p50'),
      smoothLine: makeLine('smooth_winner'),
      choppyLine: makeLine('choppy_survivor'),
      deepDdLine: makeLine('deep_drawdown'),
      belowStartLine: makeLine('below_start'),
      yTicks,
      xLabels,
      steps,
    };
  }, [trajectory, initialCapital]);

  const activeStep = hoveredIndex !== null && chartGeometry ? chartGeometry.steps[hoveredIndex] : null;

  return (
    <div className="flex flex-col gap-4 w-full bg-[#070b14] border border-[#1e293b] rounded-xl p-4 text-slate-200 font-sans shadow-2xl">
      {/* ========================================================================= */}
      {/* 1. HEADER & CINEMATIC TITLE */}
      {/* ========================================================================= */}
      <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-3 pb-3 border-b border-slate-800/80">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-indigo-500/20 to-cyan-500/20 border border-cyan-500/40 flex items-center justify-center text-cyan-400 shadow-md shadow-cyan-500/10">
            <Compass size={22} className="animate-pulse" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-base font-bold font-mono tracking-wide text-white">
                A Forecast Is Not a Future • Monte Carlo Distribution Lab
              </h3>
              <span className="text-[10px] px-2 py-0.5 rounded bg-cyan-950/80 text-cyan-400 font-mono border border-cyan-800">
                10,000 PATHS (GBM)
              </span>
            </div>
            <p className="text-xs text-slate-400 font-mono mt-0.5">
              <span>Geometric Brownian Motion</span>
              <span className="mx-1.5">•</span>
              <span className="text-emerald-400">Percentile Fan Bands</span>
              <span className="mx-1.5">•</span>
              <span>4 Realized Path Archetypes</span>
            </p>
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-2 self-stretch md:self-auto">
          <button
            onClick={() => handleRunSimulation(true)}
            disabled={running}
            title="Auto-calibrate drift (μ) and volatility (σ) directly from live ticker data"
            className="flex items-center gap-1.5 px-3 py-1.5 bg-[#0f172a] hover:bg-slate-800 border border-slate-700 text-slate-300 rounded font-mono text-xs transition-all disabled:opacity-50"
          >
            <Sparkles size={13} className="text-amber-400" />
            <span>Calibrate from Live {symbol}</span>
          </button>

          <button
            onClick={() => handleRunSimulation(false)}
            disabled={running}
            className="flex items-center gap-2 px-4 py-1.5 bg-gradient-to-r from-cyan-600 to-indigo-600 hover:from-cyan-500 hover:to-indigo-500 text-white rounded font-mono text-xs font-bold shadow-lg shadow-cyan-500/20 transition-all disabled:opacity-50"
          >
            {running ? <RotateCw size={14} className="animate-spin" /> : <Play size={14} />}
            <span>{running ? 'Simulating 10,000 Paths...' : 'Simulate 10,000 Futures'}</span>
          </button>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* 2. PARAMETERS CONTROL PANEL (Inputs modeled after Hunid Capital Film 031) */}
      {/* ========================================================================= */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 bg-[#0a0f1d] border border-slate-800/80 p-3 rounded-lg text-xs font-mono">
        {/* Initial Capital */}
        <div className="flex flex-col gap-1">
          <label className="text-[10px] text-slate-400 uppercase">Starting Capital ($)</label>
          <div className="flex items-center gap-1">
            {[10000, 50000, 100000].map((amt) => (
              <button
                key={amt}
                onClick={() => setInitialCapital(amt)}
                className={`px-1.5 py-0.5 rounded text-[10px] transition-all ${
                  initialCapital === amt
                    ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/50 font-bold'
                    : 'bg-slate-800/60 text-slate-400 hover:text-slate-200'
                }`}
              >
                ${amt >= 1000 ? `${amt / 1000}k` : amt}
              </button>
            ))}
          </div>
          <input
            type="number"
            value={initialCapital}
            onChange={(e) => setInitialCapital(Number(e.target.value) || 10000)}
            className="bg-[#050811] border border-slate-700 rounded px-2 py-1 text-slate-200 focus:border-cyan-500 outline-none text-xs"
          />
        </div>

        {/* Expected Drift (mu) */}
        <div className="flex flex-col gap-1">
          <div className="flex items-center justify-between">
            <label className="text-[10px] text-slate-400 uppercase">Expected Return (μ)</label>
            <span className="text-emerald-400 font-bold">{(expectedReturn * 100).toFixed(1)}% / yr</span>
          </div>
          <input
            type="range"
            min="-0.20"
            max="0.80"
            step="0.01"
            value={expectedReturn}
            onChange={(e) => setExpectedReturn(parseFloat(e.target.value))}
            className="accent-cyan-400 cursor-pointer"
          />
          <div className="flex justify-between text-[9px] text-slate-500">
            <span>-20%</span>
            <span>+30%</span>
            <span>+80%</span>
          </div>
        </div>

        {/* Annual Volatility (sigma) */}
        <div className="flex flex-col gap-1">
          <div className="flex items-center justify-between">
            <label className="text-[10px] text-slate-400 uppercase">Volatility (σ)</label>
            <span className="text-amber-400 font-bold">{(volatility * 100).toFixed(1)}% / yr</span>
          </div>
          <input
            type="range"
            min="0.05"
            max="1.20"
            step="0.01"
            value={volatility}
            onChange={(e) => setVolatility(parseFloat(e.target.value))}
            className="accent-amber-400 cursor-pointer"
          />
          <div className="flex justify-between text-[9px] text-slate-500">
            <span>5% (Calm)</span>
            <span>60% (Crypto)</span>
            <span>120% (Meme)</span>
          </div>
        </div>

        {/* Time Horizon */}
        <div className="flex flex-col gap-1">
          <label className="text-[10px] text-slate-400 uppercase">Time Horizon</label>
          <div className="grid grid-cols-4 gap-1">
            {[
              { label: '6M', val: 0.5 },
              { label: '1Y', val: 1.0 },
              { label: '3Y', val: 3.0 },
              { label: '5Y', val: 5.0 },
            ].map((h) => (
              <button
                key={h.label}
                onClick={() => setHorizonYears(h.val)}
                className={`py-1 rounded text-[10px] transition-all text-center ${
                  horizonYears === h.val
                    ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/50 font-bold'
                    : 'bg-slate-800/60 text-slate-400 hover:text-slate-200'
                }`}
              >
                {h.label}
              </button>
            ))}
          </div>
          <span className="text-[10px] text-slate-500 text-center mt-0.5">
            {horizonYears * 12} Monthly Simulation Steps
          </span>
        </div>

        {/* Number of Paths */}
        <div className="flex flex-col gap-1">
          <label className="text-[10px] text-slate-400 uppercase">Simulated Realizations</label>
          <div className="flex items-center gap-1 mt-1">
            {[1000, 5000, 10000].map((p) => (
              <button
                key={p}
                onClick={() => setNumPaths(p)}
                className={`flex-1 py-1 rounded text-[10px] transition-all text-center ${
                  numPaths === p
                    ? 'bg-indigo-500/20 text-indigo-300 border border-indigo-500/50 font-bold'
                    : 'bg-slate-800/60 text-slate-400 hover:text-slate-200'
                }`}
              >
                {p >= 1000 ? `${p / 1000}k` : p}
              </button>
            ))}
          </div>
          <span className="text-[10px] text-slate-500 text-center mt-0.5">
            Vectorized NumPy Kernel
          </span>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* 3. INTERACTIVE PERCENTILE FAN CHART (CONE OF UNCERTAINTY) */}
      {/* ========================================================================= */}
      <div className="relative w-full bg-[#060913] border border-slate-800 rounded-lg p-2 overflow-hidden shadow-inner">
        {/* Toggleable Legend Bar */}
        <div className="flex flex-wrap items-center justify-between gap-2 px-3 py-1.5 border-b border-slate-800/60 font-mono text-xs">
          <div className="flex items-center gap-3">
            <span className="text-slate-400 text-[11px] font-semibold">Percentile Bands:</span>
            <span className="flex items-center gap-1.5 text-cyan-400 text-[10px]">
              <span className="w-3 h-2 rounded-sm bg-cyan-500/10 border border-cyan-500/30"></span>
              90% Range (P5–P95)
            </span>
            <span className="flex items-center gap-1.5 text-indigo-400 text-[10px]">
              <span className="w-3 h-2 rounded-sm bg-indigo-500/20 border border-indigo-500/40"></span>
              50% Range (P25–P75)
            </span>
            <span className="flex items-center gap-1.5 text-white text-[10px] font-bold">
              <span className="w-3 h-0.5 bg-white"></span>
              Median Path (P50)
            </span>
          </div>

          {/* 4 Representative Path Toggles */}
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowSmoothWinner(!showSmoothWinner)}
              className={`flex items-center gap-1 px-2 py-0.5 rounded text-[10px] border transition-all ${
                showSmoothWinner
                  ? 'bg-emerald-500/15 border-emerald-500/40 text-emerald-300'
                  : 'bg-transparent border-slate-800 text-slate-500 line-through'
              }`}
            >
              <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
              Smooth Winner
            </button>

            <button
              onClick={() => setShowChoppySurvivor(!showChoppySurvivor)}
              className={`flex items-center gap-1 px-2 py-0.5 rounded text-[10px] border transition-all ${
                showChoppySurvivor
                  ? 'bg-purple-500/15 border-purple-500/40 text-purple-300'
                  : 'bg-transparent border-slate-800 text-slate-500 line-through'
              }`}
            >
              <span className="w-2 h-2 rounded-full bg-purple-400"></span>
              Choppy Survivor
            </button>

            <button
              onClick={() => setShowDeepDrawdown(!showDeepDrawdown)}
              className={`flex items-center gap-1 px-2 py-0.5 rounded text-[10px] border transition-all ${
                showDeepDrawdown
                  ? 'bg-amber-500/15 border-amber-500/40 text-amber-300'
                  : 'bg-transparent border-slate-800 text-slate-500 line-through'
              }`}
            >
              <span className="w-2 h-2 rounded-full bg-amber-400"></span>
              Deep Drawdown
            </button>

            <button
              onClick={() => setShowBelowStart(!showBelowStart)}
              className={`flex items-center gap-1 px-2 py-0.5 rounded text-[10px] border transition-all ${
                showBelowStart
                  ? 'bg-rose-500/15 border-rose-500/40 text-rose-300'
                  : 'bg-transparent border-slate-800 text-slate-500 line-through'
              }`}
            >
              <span className="w-2 h-2 rounded-full bg-rose-400"></span>
              Below Start (Ruin)
            </button>
          </div>
        </div>

        {/* SVG Drawing Canvas */}
        {chartGeometry ? (
          <div className="relative w-full h-[360px]">
            <svg
              viewBox={`0 0 ${chartGeometry.width} ${chartGeometry.height}`}
              className="w-full h-full select-none cursor-crosshair"
              onMouseLeave={() => setHoveredIndex(null)}
              onMouseMove={(e) => {
                const rect = e.currentTarget.getBoundingClientRect();
                const mouseX = ((e.clientX - rect.left) / rect.width) * chartGeometry.width;
                const innerX = mouseX - chartGeometry.padding.left;
                if (innerX >= 0 && innerX <= chartGeometry.innerWidth) {
                  const stepFrac = innerX / chartGeometry.innerWidth;
                  const idx = Math.round(stepFrac * (chartGeometry.steps.length - 1));
                  setHoveredIndex(Math.max(0, Math.min(chartGeometry.steps.length - 1, idx)));
                }
              }}
            >
              <defs>
                {/* 90% Confidence Interval Gradient */}
                <linearGradient id="gradient90" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#06b6d4" stopOpacity="0.12" />
                  <stop offset="50%" stopColor="#3b82f6" stopOpacity="0.06" />
                  <stop offset="100%" stopColor="#06b6d4" stopOpacity="0.12" />
                </linearGradient>

                {/* 50% Confidence Interval Gradient */}
                <linearGradient id="gradient50" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#6366f1" stopOpacity="0.25" />
                  <stop offset="100%" stopColor="#6366f1" stopOpacity="0.10" />
                </linearGradient>
              </defs>

              {/* Horizontal Grid Lines */}
              {chartGeometry.yTicks.map((t, idx) => (
                <g key={idx}>
                  <line
                    x1={chartGeometry.padding.left}
                    y1={t.y}
                    x2={chartGeometry.width - chartGeometry.padding.right}
                    y2={t.y}
                    stroke="#1e293b"
                    strokeDasharray="3 3"
                    strokeWidth="1"
                  />
                  <text
                    x={chartGeometry.padding.left - 8}
                    y={t.y + 4}
                    textAnchor="end"
                    fill="#64748b"
                    fontSize="10"
                    fontFamily="monospace"
                  >
                    ${t.val >= 1000 ? `${(t.val / 1000).toFixed(0)}k` : t.val.toFixed(0)}
                  </text>
                </g>
              ))}

              {/* Starting Capital Baseline Reference */}
              <line
                x1={chartGeometry.padding.left}
                y1={chartGeometry.baselineY}
                x2={chartGeometry.width - chartGeometry.padding.right}
                y2={chartGeometry.baselineY}
                stroke="#64748b"
                strokeDasharray="4 4"
                strokeWidth="1.5"
                opacity="0.7"
              />
              <text
                x={chartGeometry.width - chartGeometry.padding.right - 5}
                y={chartGeometry.baselineY - 6}
                textAnchor="end"
                fill="#94a3b8"
                fontSize="9"
                fontFamily="monospace"
              >
                Capital Baseline: ${initialCapital.toLocaleString()}
              </text>

              {/* Shaded Confidence Fans */}
              <path d={chartGeometry.area90} fill="url(#gradient90)" />
              <path d={chartGeometry.area50} fill="url(#gradient50)" />

              {/* Boundary Lines for Bands */}
              <polyline
                points={chartGeometry.steps.map((s, idx) => `${chartGeometry.getX(idx)},${chartGeometry.getY(s.p95)}`).join(' ')}
                fill="none"
                stroke="#06b6d4"
                strokeWidth="1"
                strokeOpacity="0.4"
                strokeDasharray="2 2"
              />
              <polyline
                points={chartGeometry.steps.map((s, idx) => `${chartGeometry.getX(idx)},${chartGeometry.getY(s.p5)}`).join(' ')}
                fill="none"
                stroke="#06b6d4"
                strokeWidth="1"
                strokeOpacity="0.4"
                strokeDasharray="2 2"
              />

              {/* Median Path (P50) */}
              <polyline
                points={chartGeometry.p50Line}
                fill="none"
                stroke="#38bdf8"
                strokeWidth="2.5"
                strokeLinecap="round"
                className="drop-shadow-[0_0_8px_rgba(56,189,248,0.5)]"
              />

              {/* 4 Representative Realized Paths */}
              {showSmoothWinner && (
                <polyline
                  points={chartGeometry.smoothLine}
                  fill="none"
                  stroke="#10b981"
                  strokeWidth="2"
                  strokeLinecap="round"
                  className="drop-shadow-[0_0_6px_rgba(16,185,129,0.5)]"
                />
              )}

              {showChoppySurvivor && (
                <polyline
                  points={chartGeometry.choppyLine}
                  fill="none"
                  stroke="#c084fc"
                  strokeWidth="1.8"
                  strokeDasharray="4 2"
                  strokeLinecap="round"
                />
              )}

              {showDeepDrawdown && (
                <polyline
                  points={chartGeometry.deepDdLine}
                  fill="none"
                  stroke="#f59e0b"
                  strokeWidth="1.8"
                  strokeDasharray="2 2"
                  strokeLinecap="round"
                />
              )}

              {showBelowStart && (
                <polyline
                  points={chartGeometry.belowStartLine}
                  fill="none"
                  stroke="#f43f5e"
                  strokeWidth="2"
                  strokeLinecap="round"
                  className="drop-shadow-[0_0_6px_rgba(244,63,94,0.5)]"
                />
              )}

              {/* X-Axis Tick Labels */}
              {chartGeometry.xLabels.map((lbl, idx) => (
                <g key={idx}>
                  <line
                    x1={lbl.x}
                    y1={chartGeometry.height - chartGeometry.padding.bottom}
                    x2={lbl.x}
                    y2={chartGeometry.height - chartGeometry.padding.bottom + 5}
                    stroke="#475569"
                    strokeWidth="1"
                  />
                  <text
                    x={lbl.x}
                    y={chartGeometry.height - chartGeometry.padding.bottom + 18}
                    textAnchor="middle"
                    fill="#64748b"
                    fontSize="10"
                    fontFamily="monospace"
                  >
                    {lbl.label}
                  </text>
                </g>
              ))}

              {/* Interactive Crosshair Cursor */}
              {hoveredIndex !== null && (
                <g>
                  <line
                    x1={chartGeometry.getX(hoveredIndex)}
                    y1={chartGeometry.padding.top}
                    x2={chartGeometry.getX(hoveredIndex)}
                    y2={chartGeometry.height - chartGeometry.padding.bottom}
                    stroke="#94a3b8"
                    strokeDasharray="3 3"
                    strokeWidth="1"
                  />
                  <circle
                    cx={chartGeometry.getX(hoveredIndex)}
                    cy={chartGeometry.getY(chartGeometry.steps[hoveredIndex].p50)}
                    r="4"
                    fill="#38bdf8"
                    stroke="#ffffff"
                    strokeWidth="2"
                  />
                </g>
              )}
            </svg>

            {/* Hover Tooltip Overlay */}
            {activeStep && (
              <div
                className="absolute z-10 pointer-events-none bg-[#090e1a]/95 border border-slate-700 p-2.5 rounded shadow-2xl font-mono text-[11px] backdrop-blur-sm"
                style={{
                  left: Math.min(
                    chartGeometry.width - 240,
                    Math.max(chartGeometry.padding.left + 10, chartGeometry.getX(hoveredIndex!) - 100)
                  ),
                  top: 20,
                }}
              >
                <div className="font-bold text-white border-b border-slate-800 pb-1 mb-1.5 flex items-center justify-between">
                  <span>Horizon Step: {activeStep.time_label}</span>
                  <span className="text-cyan-400">Step #{activeStep.step}</span>
                </div>
                <div className="space-y-0.5">
                  <div className="flex justify-between text-slate-300">
                    <span className="text-slate-400">Median (P50):</span>
                    <span className="font-bold text-cyan-300">${activeStep.p50.toLocaleString()}</span>
                  </div>
                  <div className="flex justify-between text-slate-400">
                    <span>90% Range (P5–P95):</span>
                    <span>${activeStep.p5.toLocaleString()} – ${activeStep.p95.toLocaleString()}</span>
                  </div>
                  <div className="flex justify-between text-slate-400">
                    <span>50% Range (P25–P75):</span>
                    <span>${activeStep.p25.toLocaleString()} – ${activeStep.p75.toLocaleString()}</span>
                  </div>
                  <div className="border-t border-slate-800/80 pt-1 mt-1 flex justify-between text-emerald-400">
                    <span>Smooth Winner:</span>
                    <span>${activeStep.smooth_winner.toLocaleString()}</span>
                  </div>
                  <div className="flex justify-between text-purple-400">
                    <span>Choppy Survivor:</span>
                    <span>${activeStep.choppy_survivor.toLocaleString()}</span>
                  </div>
                  <div className="flex justify-between text-amber-400">
                    <span>Deep Drawdown:</span>
                    <span>${activeStep.deep_drawdown.toLocaleString()}</span>
                  </div>
                  <div className="flex justify-between text-rose-400">
                    <span>Below Start (Ruin):</span>
                    <span>${activeStep.below_start.toLocaleString()}</span>
                  </div>
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="w-full h-[320px] flex flex-col items-center justify-center gap-3 text-slate-400">
            <Compass size={40} className="text-slate-600 animate-pulse" />
            <p className="font-mono text-xs">No simulation data loaded. Click below to run 10,000 Monte Carlo paths.</p>
            <button
              onClick={() => handleRunSimulation(false)}
              className="px-4 py-2 bg-cyan-600/30 hover:bg-cyan-600/50 text-cyan-300 border border-cyan-500/40 rounded font-mono text-xs font-bold"
            >
              Run 10,000-Path Monte Carlo Simulation
            </button>
          </div>
        )}
      </div>

      {/* ========================================================================= */}
      {/* 4. STATISTICAL OUTCOMES & RISK PROBABILITY CARDS */}
      {/* ========================================================================= */}
      {trajectory && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 font-mono">
          {/* P(Ruin) Card */}
          <div className="bg-[#090e1d] border border-slate-800 p-3 rounded-lg flex flex-col">
            <div className="flex items-center justify-between text-slate-400 text-[10px] uppercase">
              <span>Probability of Ruin (≥20% DD)</span>
              <ShieldAlert size={14} className={trajectory.probability_of_ruin < 0.01 ? 'text-emerald-400' : 'text-rose-400'} />
            </div>
            <div className="text-xl font-bold mt-1">
              <span className={trajectory.probability_of_ruin < 0.01 ? 'text-emerald-400' : 'text-rose-400'}>
                {(trajectory.probability_of_ruin * 100).toFixed(2)}%
              </span>
            </div>
            <span className="text-[10px] text-slate-500 mt-0.5">
              {trajectory.probability_of_ruin < 0.01 ? 'Constitutional Risk Clearance: PASSED' : 'High Ruin Risk Breach'}
            </span>
          </div>

          {/* Probability of Loss Card */}
          <div className="bg-[#090e1d] border border-slate-800 p-3 rounded-lg flex flex-col">
            <div className="flex items-center justify-between text-slate-400 text-[10px] uppercase">
              <span>Probability of Net Loss</span>
              <TrendingDown size={14} className="text-amber-400" />
            </div>
            <div className="text-xl font-bold text-amber-400 mt-1">
              {(trajectory.probability_of_loss * 100).toFixed(1)}%
            </div>
            <span className="text-[10px] text-slate-500 mt-0.5">
              Paths ending below ${initialCapital.toLocaleString()}
            </span>
          </div>

          {/* Median Terminal Value */}
          <div className="bg-[#090e1d] border border-slate-800 p-3 rounded-lg flex flex-col">
            <div className="flex items-center justify-between text-slate-400 text-[10px] uppercase">
              <span>Median Terminal Equity (P50)</span>
              <TrendingUp size={14} className="text-cyan-400" />
            </div>
            <div className="text-xl font-bold text-cyan-400 mt-1">
              ${trajectory.p50_terminal.toLocaleString()}
            </div>
            <span className="text-[10px] text-slate-500 mt-0.5">
              90% CI: [${trajectory.p5_terminal.toLocaleString()} – ${trajectory.p95_terminal.toLocaleString()}]
            </span>
          </div>

          {/* Drawdown Profile */}
          <div className="bg-[#090e1d] border border-slate-800 p-3 rounded-lg flex flex-col">
            <div className="flex items-center justify-between text-slate-400 text-[10px] uppercase">
              <span>Drawdown Profile (P50 / P95)</span>
              <BarChart2 size={14} className="text-indigo-400" />
            </div>
            <div className="text-xl font-bold text-slate-200 mt-1">
              {trajectory.median_max_drawdown_pct.toFixed(1)}% /{' '}
              <span className="text-rose-400">{trajectory.worst_case_max_drawdown_pct.toFixed(1)}%</span>
            </div>
            <span className="text-[10px] text-slate-500 mt-0.5">
              Worst-case tail (95th percentile max drawdown)
            </span>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 5. THE SCIENCE OF RISK: EPISTEMIC TEACHING & TAKEAWAYS */}
      {/* ========================================================================= */}
      <div className="bg-[#080d19] border border-slate-800 p-3.5 rounded-lg flex flex-col md:flex-row items-start gap-3 text-xs text-slate-300">
        <div className="p-2 rounded bg-indigo-500/10 border border-indigo-500/30 text-indigo-400 shrink-0">
          <HelpCircle size={20} />
        </div>
        <div className="flex flex-col gap-1">
          <span className="font-bold text-slate-100 flex items-center gap-1.5 font-mono">
            <span>Epistemic Principle: A Forecast Is Not a Future (Hunid Capital Film 031)</span>
          </span>
          <p className="text-slate-400 leading-relaxed text-[11px]">
            A single historical backtest or forecast number hides the vast distribution of alternative realities.
            In 10,000 geometric Brownian motion realizations from identical parameters ($\mu={expectedReturn*100}\%$, $\sigma={volatility*100}\%$),
            realizations diverge drastically: smooth compounders, high-volatility survivors, deep drawdowns, and ruin paths.
            Quantitative survival requires sizing for the <strong>lower tail dispersion</strong> rather than assuming the average path.
          </p>
        </div>
      </div>
    </div>
  );
};
