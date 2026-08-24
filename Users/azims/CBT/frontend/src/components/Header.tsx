import React from 'react';
import { RefreshCw, Activity, Zap, TrendingUp, TrendingDown, BellOff, BellRing } from 'lucide-react';
import { SupportedTimeframe } from '../types';

interface HeaderProps {
  symbol: string;
  onSymbolChange: (symbol: string) => void;
  timeframe: SupportedTimeframe;
  onTimeframeChange: (tf: SupportedTimeframe) => void;
  lastPrice: number;
  highPrice: number;
  lowPrice: number;
  trend: string;
  loading: boolean;
  onRefresh: () => void;
  notificationsEnabled: boolean;
  onToggleNotifications: () => void;
}

const POPULAR_SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'AVAXUSDT'];
const TIMEFRAMES: SupportedTimeframe[] = ['5m', '15m', '1h', '4h', '1d'];

export const Header: React.FC<HeaderProps> = ({
  symbol,
  onSymbolChange,
  timeframe,
  onTimeframeChange,
  lastPrice,
  highPrice,
  lowPrice,
  trend,
  loading,
  onRefresh,
  notificationsEnabled,
  onToggleNotifications,
}) => {
  const isBullish = trend.toLowerCase().includes('bullish');
  const isBearish = trend.toLowerCase().includes('bearish');

  return (
    <header className="border-b border-border bg-background-subtle/80 backdrop-blur sticky top-0 z-40 px-4 py-3">
      <div className="max-w-[1800px] mx-auto flex flex-wrap items-center justify-between gap-4">
        {/* Left: Brand & System Badge */}
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded bg-terminal-cyan/10 border border-terminal-cyan/40 flex items-center justify-center text-terminal-cyan font-mono font-bold shadow-sm glow-cyan">
              CTB
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-base font-bold tracking-wider text-white font-mono flex items-center gap-1.5">
                  CRYPTO BRAIN TERMINAL
                </h1>
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 font-mono border border-slate-700">
                  PWA-ACTIVE
                </span>
              </div>
              <p className="text-[11px] text-slate-400 font-mono">
                Institutional Quant Desk &amp; Gemini Intelligence
              </p>
            </div>
          </div>

          <div className="hidden lg:flex items-center gap-1.5 px-2.5 py-1 rounded bg-[#0D1520] border border-terminal-cyan/20 text-terminal-cyan text-xs font-mono">
            <Activity className="w-3.5 h-3.5 animate-pulse text-terminal-cyan" />
            <span>DESK ENGINE ACTIVE</span>
          </div>
        </div>

        {/* Center: Symbol & Timeframe Selectors */}
        <div className="flex flex-wrap items-center gap-3">
          {/* Symbol Selector */}
          <div className="flex items-center bg-background-card border border-border rounded p-0.5">
            {POPULAR_SYMBOLS.map((sym) => (
              <button
                key={sym}
                onClick={() => onSymbolChange(sym)}
                className={`px-2.5 py-1 text-xs font-mono font-medium rounded transition-all ${
                  symbol === sym
                    ? 'bg-terminal-cyan/20 text-terminal-cyan border border-terminal-cyan/40 shadow-sm'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-background-hover'
                }`}
              >
                {sym.replace('USDT', '')}
              </button>
            ))}
          </div>

          {/* Timeframe Switcher */}
          <div className="flex items-center bg-background-card border border-border rounded p-0.5">
            {TIMEFRAMES.map((tf) => (
              <button
                key={tf}
                onClick={() => onTimeframeChange(tf)}
                className={`px-2 py-1 text-xs font-mono font-medium rounded transition-all ${
                  timeframe === tf
                    ? 'bg-slate-700 text-white shadow-sm'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-background-hover'
                }`}
              >
                {tf}
              </button>
            ))}
          </div>
        </div>

        {/* Right: Telemetry Metrics & Actions */}
        <div className="flex items-center gap-3">
          {/* Real-time Telemetry */}
          <div className="flex items-center gap-4 bg-background-card border border-border px-3 py-1.5 rounded">
            <div>
              <div className="text-[10px] text-slate-500 font-mono uppercase">MARK PRICE</div>
              <div className="text-sm font-mono font-bold text-white">
                ${lastPrice > 0 ? lastPrice.toLocaleString(undefined, { minimumFractionDigits: 2 }) : '---'}
              </div>
            </div>

            <div className="h-6 w-[1px] bg-border" />

            <div className="hidden sm:block">
              <div className="text-[10px] text-slate-500 font-mono uppercase">SESSION HIGH / LOW</div>
              <div className="text-xs font-mono text-slate-300">
                <span className="text-terminal-green">${highPrice.toLocaleString()}</span> /{' '}
                <span className="text-terminal-red">${lowPrice.toLocaleString()}</span>
              </div>
            </div>

            <div className="h-6 w-[1px] bg-border hidden sm:block" />

            <div className="hidden md:flex items-center gap-1.5">
              {isBullish ? (
                <TrendingUp className="w-4 h-4 text-terminal-green" />
              ) : isBearish ? (
                <TrendingDown className="w-4 h-4 text-terminal-red" />
              ) : (
                <Zap className="w-4 h-4 text-terminal-amber" />
              )}
              <span
                className={`text-xs font-mono font-medium ${
                  isBullish
                    ? 'text-terminal-green'
                    : isBearish
                    ? 'text-terminal-red'
                    : 'text-terminal-amber'
                }`}
              >
                {trend.split(' ')[0] || 'NEUTRAL'}
              </span>
            </div>
          </div>

          {/* Web Push Notification Toggle */}
          <button
            onClick={onToggleNotifications}
            title={notificationsEnabled ? 'Push Notifications Enabled (Click to disable)' : 'Enable Push Notifications'}
            className={`p-2 rounded border transition-all flex items-center gap-1 text-xs font-mono ${
              notificationsEnabled
                ? 'bg-terminal-cyan/10 border-terminal-cyan/40 text-terminal-cyan shadow-sm glow-cyan'
                : 'bg-background-card border-border text-slate-400 hover:text-slate-200 hover:border-border-active'
            }`}
          >
            {notificationsEnabled ? (
              <>
                <BellRing className="w-4 h-4 text-terminal-cyan" />
                <span className="hidden sm:inline text-[11px]">ALERTS ON</span>
              </>
            ) : (
              <>
                <BellOff className="w-4 h-4" />
                <span className="hidden sm:inline text-[11px]">ALERTS OFF</span>
              </>
            )}
          </button>

          {/* Refresh Button */}
          <button
            onClick={onRefresh}
            disabled={loading}
            title="Refresh Market Telemetry"
            className="p-2 rounded bg-background-card border border-border hover:border-border-active text-slate-300 hover:text-white transition-all disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin text-terminal-cyan' : ''}`} />
          </button>
        </div>
      </div>
    </header>
  );
};
