import React from 'react';
import { Compass, Gauge, TrendingUp, TrendingDown } from 'lucide-react';
import { IndicatorPoint } from '../types';
import { LoadingSkeleton } from './LoadingSkeleton';

interface MTFPanelProps {
  symbol: string;
  timeframe: string;
  lastPrice: number;
  ema?: IndicatorPoint[];
  rsi?: IndicatorPoint[];
  trend: string;
  loading?: boolean;
}

export const MTFPanel: React.FC<MTFPanelProps> = ({
  symbol,
  timeframe,
  lastPrice,
  ema = [],
  rsi = [],
  trend,
  loading = false,
}) => {
  const latestEMA = ema.length > 0 ? ema[ema.length - 1].value : undefined;
  const latestRSI = rsi.length > 0 ? rsi[rsi.length - 1].value : undefined;

  const isEmaBullish = latestEMA !== undefined && lastPrice >= latestEMA;
  const isRsiOverbought = latestRSI !== undefined && latestRSI >= 70;
  const isRsiOversold = latestRSI !== undefined && latestRSI <= 30;

  return (
    <div className="bg-background-card border border-border rounded-lg p-4 shadow-lg flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between pb-3 mb-3 border-b border-border">
        <div className="flex items-center gap-2">
          <Compass className="w-4 h-4 text-terminal-cyan" />
          <h3 className="text-xs font-mono font-bold text-slate-200 uppercase">
            MTF INDICATORS &amp; CONFLUENCE
          </h3>
        </div>
        <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700">
          {timeframe} BASIS
        </span>
      </div>

      {loading ? (
        <div className="space-y-3">
          <LoadingSkeleton className="h-12 w-full" />
          <LoadingSkeleton className="h-12 w-full" />
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 flex-1">
          {/* EMA(14) Metric */}
          <div className="bg-background p-3 rounded border border-border flex flex-col justify-between">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-mono text-slate-400">EMA(14) TREND</span>
              {isEmaBullish ? (
                <span className="flex items-center gap-1 text-[10px] font-mono text-terminal-green font-bold">
                  <TrendingUp className="w-3 h-3" /> ABOVE EMA
                </span>
              ) : (
                <span className="flex items-center gap-1 text-[10px] font-mono text-terminal-red font-bold">
                  <TrendingDown className="w-3 h-3" /> BELOW EMA
                </span>
              )}
            </div>

            <div className="mt-2 flex items-baseline justify-between">
              <span className="text-lg font-mono font-bold text-white">
                ${latestEMA ? latestEMA.toFixed(2) : '---'}
              </span>
              <span className="text-[10px] font-mono text-slate-500">
                {latestEMA && lastPrice
                  ? `${(((lastPrice - latestEMA) / latestEMA) * 100).toFixed(2)}% diff`
                  : ''}
              </span>
            </div>

            <div className="w-full bg-slate-800 h-1.5 rounded-full mt-2 overflow-hidden">
              <div
                className={`h-full ${isEmaBullish ? 'bg-terminal-green' : 'bg-terminal-red'}`}
                style={{ width: isEmaBullish ? '75%' : '25%' }}
              />
            </div>
          </div>

          {/* RSI(14) Metric */}
          <div className="bg-background p-3 rounded border border-border flex flex-col justify-between">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-mono text-slate-400">WILDER RSI(14)</span>
              <span
                className={`flex items-center gap-1 text-[10px] font-mono font-bold ${
                  isRsiOverbought
                    ? 'text-terminal-red'
                    : isRsiOversold
                    ? 'text-terminal-green'
                    : 'text-terminal-amber'
                }`}
              >
                <Gauge className="w-3 h-3" />
                {isRsiOverbought ? 'OVERBOUGHT' : isRsiOversold ? 'OVERSOLD' : 'NEUTRAL'}
              </span>
            </div>

            <div className="mt-2 flex items-baseline justify-between">
              <span
                className={`text-lg font-mono font-bold ${
                  isRsiOverbought
                    ? 'text-terminal-red'
                    : isRsiOversold
                    ? 'text-terminal-green'
                    : 'text-terminal-amber'
                }`}
              >
                {latestRSI ? latestRSI.toFixed(1) : '---'}
              </span>
              <span className="text-[10px] font-mono text-slate-500">30 / 70 BANDS</span>
            </div>

            <div className="w-full bg-slate-800 h-1.5 rounded-full mt-2 overflow-hidden relative">
              <div
                className={`h-full transition-all duration-500 ${
                  isRsiOverbought
                    ? 'bg-terminal-red'
                    : isRsiOversold
                    ? 'bg-terminal-green'
                    : 'bg-terminal-amber'
                }`}
                style={{ width: `${Math.min(100, Math.max(0, latestRSI || 50))}%` }}
              />
            </div>
          </div>

          {/* Confluence Trend Overview */}
          <div className="sm:col-span-2 bg-[#0D121B] p-2.5 rounded border border-terminal-cyan/20 flex items-center justify-between">
            <div className="flex items-center gap-2 text-xs font-mono">
              <span className="text-slate-400">STRUCTURAL BIAS:</span>
              <span className="text-terminal-cyan font-bold">{trend}</span>
            </div>
            <div className="text-[10px] font-mono text-slate-500">
              {symbol} {timeframe}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
