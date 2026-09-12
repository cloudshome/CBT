import React, { useState, useEffect } from 'react';
import {
  ShieldAlert,
  Clock,
  Radio,
  AlertTriangle,
  RotateCcw,
} from 'lucide-react';
import { MasterTerminalTelemetry, TerminalDensityMode } from '../../types';

interface SystemCommandStripProps {
  telemetry: MasterTerminalTelemetry | null;
  densityMode: TerminalDensityMode;
  onDensityModeChange: (mode: TerminalDensityMode) => void;
  selectedSymbol: string;
  onSelectSymbol: (sym: string) => void;
  onRefresh: () => void;
  loading: boolean;
}

const INSTRUMENTS = [
  { symbol: 'BTCUSDT', label: 'BTC/USDT', type: 'PERPETUAL' },
  { symbol: 'ETHUSDT', label: 'ETH/USDT', type: 'PERPETUAL' },
  { symbol: 'SOLUSDT', label: 'SOL/USDT', type: 'PERPETUAL' },
  { symbol: 'PAXGUSDT', label: 'GOLD (PAXG)', type: 'SPOT' },
];

export const SystemCommandStrip: React.FC<SystemCommandStripProps> = ({
  telemetry,
  densityMode,
  onDensityModeChange,
  selectedSymbol,
  onSelectSymbol,
  onRefresh,
  loading,
}) => {
  const [clockUtc, setClockUtc] = useState<string>('');
  const [killSwitchArmed, setKillSwitchArmed] = useState<boolean>(false);

  useEffect(() => {
    const updateClock = () => {
      const now = new Date();
      setClockUtc(now.toTimeString().split(' ')[0] + ' UTC');
    };
    updateClock();
    const interval = setInterval(updateClock, 1000);
    return () => clearInterval(interval);
  }, []);

  const sys = telemetry?.system;
  const risk = sys?.riskPerimeter;

  return (
    <div className="w-full bg-[#070a12] border-b border-[#1e293b] px-3 py-2 text-xs font-mono text-slate-300 flex flex-wrap items-center justify-between gap-3 select-none">
      {/* Brand & System Status */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded bg-cyan-500/10 border border-cyan-500/40 flex items-center justify-center text-cyan-400 font-bold text-[11px] shadow-sm shadow-cyan-500/20">
            CTB
          </div>
          <div className="flex flex-col">
            <div className="flex items-center gap-2">
              <span className="font-bold text-white tracking-wider text-[11px]">
                MASTER TERMINAL
              </span>
              <span className="px-1.5 py-0.2 rounded bg-emerald-950/80 border border-emerald-500/30 text-emerald-400 text-[9px] font-bold">
                INSTITUTIONAL COCKPIT
              </span>
            </div>
            <span className="text-[10px] text-slate-500">
              Level 0–7 Decision Matrix
            </span>
          </div>
        </div>

        {/* Instrument Switcher Tabs */}
        <div className="flex items-center bg-[#0d1322] border border-[#1e293b] rounded p-0.5 ml-2">
          {INSTRUMENTS.map((inst) => (
            <button
              key={inst.symbol}
              onClick={() => onSelectSymbol(inst.symbol)}
              className={`px-2.5 py-1 text-[11px] rounded transition-all font-semibold ${
                selectedSymbol === inst.symbol
                  ? 'bg-cyan-500 text-slate-950 shadow-sm shadow-cyan-500/30 font-bold'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              {inst.label}
            </button>
          ))}
        </div>

        {/* Market Session Pill */}
        <div className="hidden xl:flex items-center gap-1.5 px-2 py-1 rounded bg-[#0d1322] border border-[#1e293b] text-slate-400 text-[10px]">
          <Radio size={11} className="text-emerald-400 animate-pulse" />
          <span>SESSION:</span>
          <span className="text-white font-bold">{sys?.activeSession || 'LONDON / NY OVERLAP'}</span>
        </div>
      </div>

      {/* Center: Real-time Telemetry Latencies */}
      <div className="hidden lg:flex items-center gap-3 bg-[#0a0f1d] border border-[#1e293b]/70 rounded px-2.5 py-1 text-[10px]">
        <div className="flex items-center gap-1.5" title="Market Data WebSocket Latency">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
          <span className="text-slate-400">FEED:</span>
          <span className="text-emerald-400 font-bold">{sys?.marketDataLatencyMs ?? 14}ms</span>
        </div>
        <span className="text-slate-700">|</span>
        <div className="flex items-center gap-1.5" title="L2 Order Book Latency">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
          <span className="text-slate-400">BOOK:</span>
          <span className="text-emerald-400 font-bold">{sys?.orderBookLatencyMs ?? 18}ms</span>
        </div>
        <span className="text-slate-700">|</span>
        <div className="flex items-center gap-1.5" title="Derivatives / CVD Engine Latency">
          <span className="w-1.5 h-1.5 rounded-full bg-cyan-400"></span>
          <span className="text-slate-400">FLOW:</span>
          <span className="text-cyan-400 font-bold">{sys?.derivativesLatencyMs ?? 82}ms</span>
        </div>
        <span className="text-slate-700">|</span>
        <div className="flex items-center gap-1.5" title="AI Confluence Engine Latency">
          <span className="w-1.5 h-1.5 rounded-full bg-indigo-400"></span>
          <span className="text-slate-400">AI:</span>
          <span className="text-indigo-400 font-bold">{sys?.aiLatencyMs ?? 420}ms</span>
        </div>
      </div>

      {/* Right: Risk Perimeter, SDCC Mesh Badge & Density Mode Switcher */}
      <div className="flex items-center gap-3">
        {/* SDCC Collective Cluster Badge */}
        <div className="hidden xl:flex items-center gap-1.5 px-2.5 py-1 rounded bg-[#0b1324] border border-cyan-500/30 text-[10px]" title="SDCC Distributed Mesh: Connected to Google Drive Cloud Hub">
          <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse"></span>
          <span className="text-cyan-400 font-bold">OFFICE-01</span>
          <span className="px-1 py-0.2 rounded bg-cyan-950 text-cyan-300 font-semibold text-[9px]">E1 • PRIMARY</span>
          <span className="text-slate-500">|</span>
          <span className="text-emerald-400 font-semibold">☁️ 5TB SYNC</span>
        </div>

        {/* Risk Perimeter Status */}
        <div className="flex items-center gap-2 bg-[#0d1322] border border-[#1e293b] rounded px-2.5 py-1 text-[10px]">
          <ShieldAlert size={12} className="text-emerald-400" />
          <div className="flex items-center gap-2">
            <div>
              <span className="text-slate-400">DAILY: </span>
              <span className="text-amber-400 font-bold">
                {risk?.dailyLossPct ?? 1.25}% / {risk?.maxDailyLossPct ?? 5.0}%
              </span>
            </div>
            <span className="text-slate-700">|</span>
            <div>
              <span className="text-slate-400">OPEN RISK: </span>
              <span className="text-emerald-400 font-bold">
                {risk?.openRiskPct ?? 0.72}%
              </span>
            </div>
          </div>
        </div>

        {/* Kill Switch Toggle */}
        <button
          onClick={() => setKillSwitchArmed(!killSwitchArmed)}
          className={`flex items-center gap-1 px-2.5 py-1 rounded text-[10px] font-bold transition-all border ${
            killSwitchArmed
              ? 'bg-rose-600 text-white border-rose-500 shadow-md shadow-rose-600/30 animate-pulse'
              : 'bg-rose-950/40 text-rose-400 border-rose-800/60 hover:bg-rose-900/50'
          }`}
          title="Emergency Risk Guard: Freezes all new trade executions instantly"
        >
          <AlertTriangle size={11} />
          <span>{killSwitchArmed ? 'KILL SWITCH ARMED' : 'KILL SWITCH: READY'}</span>
        </button>

        {/* Density Mode Switcher (COMMAND | ANALYSIS | REVIEW) */}
        <div className="flex items-center bg-[#0d1322] border border-[#1e293b] rounded p-0.5 text-[10px]">
          <button
            onClick={() => onDensityModeChange('COMMAND')}
            className={`px-2 py-1 rounded font-semibold transition-all ${
              densityMode === 'COMMAND'
                ? 'bg-slate-700 text-white shadow-sm'
                : 'text-slate-400 hover:text-slate-200'
            }`}
            title="Active Trading Cockpit: Max density"
          >
            COMMAND
          </button>
          <button
            onClick={() => onDensityModeChange('ANALYSIS')}
            className={`px-2 py-1 rounded font-semibold transition-all ${
              densityMode === 'ANALYSIS'
                ? 'bg-slate-700 text-white shadow-sm'
                : 'text-slate-400 hover:text-slate-200'
            }`}
            title="Chart & Structure Deep Analysis"
          >
            ANALYSIS
          </button>
          <button
            onClick={() => onDensityModeChange('REVIEW')}
            className={`px-2 py-1 rounded font-semibold transition-all ${
              densityMode === 'REVIEW'
                ? 'bg-slate-700 text-white shadow-sm'
                : 'text-slate-400 hover:text-slate-200'
            }`}
            title="Trade Replay & Performance Calibration"
          >
            REVIEW
          </button>
        </div>

        {/* Refresh & Clock */}
        <div className="flex items-center gap-2 pl-1">
          <button
            onClick={onRefresh}
            disabled={loading}
            className="p-1 rounded bg-[#0d1322] border border-[#1e293b] text-slate-400 hover:text-cyan-400 transition-colors disabled:opacity-50"
            title="Force Telemetry Sync"
          >
            <RotateCcw size={12} className={loading ? 'animate-spin text-cyan-400' : ''} />
          </button>
          <div className="flex items-center gap-1 text-slate-400 text-[10px] pl-1 font-mono">
            <Clock size={11} className="text-slate-500" />
            <span>{clockUtc || '14:00:00 UTC'}</span>
          </div>
        </div>
      </div>
    </div>
  );
};
