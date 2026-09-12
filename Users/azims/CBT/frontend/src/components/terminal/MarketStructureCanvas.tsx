import React, { useState } from 'react';
import {
  BarChart3,
  Flame,
  Target,
  Eye,
  EyeOff,
  Maximize2,
  Minimize2,
} from 'lucide-react';
import { TradingViewChart } from '../../core/engine/TradingViewChart';
import {
  OHLCVCandle,
  FVGItem,
  OrderBlockItem,
  SupportedTimeframe,
  VolumeProfileData,
  LiquidationMapData,
  StyleSignalPlan,
} from '../../types';

interface MarketStructureCanvasProps {
  symbol: string;
  timeframe: SupportedTimeframe;
  candles: OHLCVCandle[];
  fvgs: FVGItem[];
  orderBlocks: OrderBlockItem[];
  volumeProfile: VolumeProfileData;
  liquidationMap: LiquidationMapData;
  selectedSignalPlan?: StyleSignalPlan | null;
  currentPrice: number;
  fib05Equilibrium: number;
  currentZone: 'PREMIUM' | 'DISCOUNT';
  onTimeframeChange: (tf: SupportedTimeframe) => void;
  loading: boolean;
}

export const MarketStructureCanvas: React.FC<MarketStructureCanvasProps> = ({
  symbol,
  timeframe,
  candles,
  fvgs,
  orderBlocks,
  volumeProfile,
  liquidationMap,
  selectedSignalPlan,
  currentPrice,
  fib05Equilibrium,
  currentZone,
  onTimeframeChange,
  loading,
}) => {
  // Layer visibility toggles
  const [showSMC, setShowSMC] = useState(true);
  const [showVolumeProfile, setShowVolumeProfile] = useState(true);
  const [showLiquidity, setShowLiquidity] = useState(true);
  const [showLiquidationMap, setShowLiquidationMap] = useState(true);
  const [showExecutionLadder, setShowExecutionLadder] = useState(true);
  const [isExpanded, setIsExpanded] = useState(false);

  // Derive Buy-Side & Sell-Side Liquidity Pool Estimates
  const buySideLiquidityPrice = Number((currentPrice * 1.018).toFixed(2));
  const sellSideLiquidityPrice = Number((currentPrice * 0.982).toFixed(2));

  return (
    <div className={`flex flex-col bg-[#070a13] border border-[#1e293b] rounded-lg overflow-hidden transition-all ${
      isExpanded ? 'fixed inset-3 z-50 shadow-2xl bg-[#070a13]' : 'relative'
    }`}>
      {/* Top Controls & Layer Visibility Toolbar */}
      <div className="flex flex-wrap items-center justify-between px-3 py-1.5 bg-[#0b101c] border-b border-[#1e293b] text-xs font-mono select-none gap-2">
        <div className="flex items-center gap-2">
          <BarChart3 size={14} className="text-cyan-400" />
          <span className="font-bold text-white text-[11px] tracking-wider">
            PRIMARY MARKET STRUCTURE CANVAS
          </span>
          <span className="px-1.5 py-0.2 rounded bg-cyan-950/60 border border-cyan-500/30 text-cyan-300 text-[10px]">
            {symbol} • {timeframe.toUpperCase()}
          </span>
        </div>

        {/* Intelligence Layer Toggles */}
        <div className="flex flex-wrap items-center gap-1.5 text-[10px]">
          <button
            onClick={() => setShowSMC(!showSMC)}
            className={`flex items-center gap-1 px-2 py-0.5 rounded border transition-all ${
              showSMC
                ? 'bg-cyan-950/80 border-cyan-500/50 text-cyan-300 font-bold'
                : 'bg-slate-900/60 border-slate-800 text-slate-500'
            }`}
          >
            {showSMC ? <Eye size={10} /> : <EyeOff size={10} />}
            <span>SMC / OB</span>
          </button>

          <button
            onClick={() => setShowVolumeProfile(!showVolumeProfile)}
            className={`flex items-center gap-1 px-2 py-0.5 rounded border transition-all ${
              showVolumeProfile
                ? 'bg-indigo-950/80 border-indigo-500/50 text-indigo-300 font-bold'
                : 'bg-slate-900/60 border-slate-800 text-slate-500'
            }`}
          >
            {showVolumeProfile ? <Eye size={10} /> : <EyeOff size={10} />}
            <span>Volume Profile</span>
          </button>

          <button
            onClick={() => setShowLiquidity(!showLiquidity)}
            className={`flex items-center gap-1 px-2 py-0.5 rounded border transition-all ${
              showLiquidity
                ? 'bg-emerald-950/80 border-emerald-500/50 text-emerald-300 font-bold'
                : 'bg-slate-900/60 border-slate-800 text-slate-500'
            }`}
          >
            {showLiquidity ? <Eye size={10} /> : <EyeOff size={10} />}
            <span>Liquidity Pools</span>
          </button>

          <button
            onClick={() => setShowLiquidationMap(!showLiquidationMap)}
            className={`flex items-center gap-1 px-2 py-0.5 rounded border transition-all ${
              showLiquidationMap
                ? 'bg-amber-950/80 border-amber-500/50 text-amber-300 font-bold'
                : 'bg-slate-900/60 border-slate-800 text-slate-500'
            }`}
          >
            {showLiquidationMap ? <Eye size={10} /> : <EyeOff size={10} />}
            <span>Liquidation Map</span>
          </button>

          <button
            onClick={() => setShowExecutionLadder(!showExecutionLadder)}
            className={`flex items-center gap-1 px-2 py-0.5 rounded border transition-all ${
              showExecutionLadder
                ? 'bg-purple-950/80 border-purple-500/50 text-purple-300 font-bold'
                : 'bg-slate-900/60 border-slate-800 text-slate-500'
            }`}
          >
            {showExecutionLadder ? <Eye size={10} /> : <EyeOff size={10} />}
            <span>Ladder Overlay</span>
          </button>

          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="p-1 rounded bg-[#0e1628] border border-[#1e293b] text-slate-400 hover:text-white transition-colors"
            title={isExpanded ? 'Restore' : 'Maximize Chart'}
          >
            {isExpanded ? <Minimize2 size={12} /> : <Maximize2 size={12} />}
          </button>
        </div>
      </div>

      {/* Liquidity Streamer Bar (Buy-side above, Sell-side below) */}
      {showLiquidity && (
        <div className="flex items-center justify-between px-3 py-1 bg-[#090d18] border-b border-[#1e293b]/60 text-[10px] font-mono select-none">
          <div className="flex items-center gap-2">
            <span className="text-amber-400 font-semibold">BUY-SIDE LIQUIDITY:</span>
            <span className="text-white font-bold">${buySideLiquidityPrice.toLocaleString()}</span>
            <span className="px-1.5 py-0.2 rounded bg-amber-950/70 border border-amber-500/30 text-amber-300 text-[9px]">
              +1.8% (Resting Buy Stops)
            </span>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1.5">
              <span className="text-slate-500">EQUILIBRIUM (0.5 FIB):</span>
              <span className="text-slate-300 font-semibold">${fib05Equilibrium.toLocaleString()}</span>
            </div>
            <span className={`px-1.5 py-0.2 rounded font-bold text-[9px] ${
              currentZone === 'DISCOUNT' ? 'bg-emerald-950 text-emerald-400 border border-emerald-500/40' : 'bg-rose-950 text-rose-400 border border-rose-500/40'
            }`}>
              {currentZone} ZONE
            </span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-emerald-400 font-semibold">SELL-SIDE LIQUIDITY:</span>
            <span className="text-white font-bold">${sellSideLiquidityPrice.toLocaleString()}</span>
            <span className="px-1.5 py-0.2 rounded bg-emerald-950/70 border border-emerald-500/30 text-emerald-300 text-[9px]">
              -1.8% (Resting Sell Stops)
            </span>
          </div>
        </div>
      )}

      {/* Main Canvas Workspace with Lightweight Charts and Side Intelligence Panels */}
      <div className="relative flex-1 min-h-[480px] bg-[#050811] flex flex-row">
        {/* Center: TradingView Interactive Canvas */}
        <div className="flex-1 relative">
          <TradingViewChart
            symbol={symbol}
            timeframe={timeframe}
            candles={candles}
            fvgs={showSMC ? fvgs : []}
            orderBlocks={showSMC ? orderBlocks : []}
            onTimeframeChange={onTimeframeChange}
            loading={loading}
          />

          {/* Execution Ladder Floating HUD Overlay */}
          {showExecutionLadder && selectedSignalPlan && (
            <div className="absolute top-3 left-3 bg-[#0a0f1e]/90 border border-indigo-500/40 backdrop-blur-md rounded-lg p-2.5 text-xs font-mono shadow-xl z-20 max-w-[260px] select-none">
              <div className="flex items-center justify-between pb-1.5 mb-1.5 border-b border-indigo-500/30">
                <div className="flex items-center gap-1.5">
                  <Target size={12} className="text-indigo-400" />
                  <span className="font-bold text-white text-[10px] tracking-wider">
                    {selectedSignalPlan.style} {selectedSignalPlan.side}
                  </span>
                </div>
                <span className="text-emerald-400 font-bold text-[10px]">
                  R:R {selectedSignalPlan.riskRewardRatio}:1
                </span>
              </div>

              {/* Vertical Execution Ladder */}
              <div className="space-y-1 text-[10px]">
                <div className="flex justify-between items-center text-emerald-400">
                  <span>TP3 (+6.2R):</span>
                  <span className="font-bold">${selectedSignalPlan.tp3.toLocaleString()}</span>
                </div>
                <div className="flex justify-between items-center text-emerald-400">
                  <span>TP2 (+3.1R):</span>
                  <span className="font-bold">${selectedSignalPlan.tp2.toLocaleString()}</span>
                </div>
                <div className="flex justify-between items-center text-emerald-300">
                  <span>TP1 (+1.5R):</span>
                  <span className="font-bold">${selectedSignalPlan.tp1.toLocaleString()}</span>
                </div>

                <div className="my-1 py-0.5 px-1.5 bg-indigo-950/80 border border-indigo-500/50 rounded flex justify-between items-center text-white font-bold">
                  <span>ENTRY ZONE:</span>
                  <span>${selectedSignalPlan.entryZone[0].toLocaleString()} – ${selectedSignalPlan.entryZone[1].toLocaleString()}</span>
                </div>

                <div className="flex justify-between items-center text-rose-400">
                  <span>STOP LOSS:</span>
                  <span className="font-bold">${selectedSignalPlan.stopLoss.toLocaleString()}</span>
                </div>
                <div className="flex justify-between items-center text-rose-500 text-[9px]">
                  <span>INVALIDATION:</span>
                  <span className="font-bold">${selectedSignalPlan.invalidationPrice.toLocaleString()}</span>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Right Sidebar Overlay: Volume Profile & Liquidation Map Strip */}
        <div className="w-[180px] hidden md:flex flex-col border-l border-[#1e293b] bg-[#070b16] select-none text-xs font-mono">
          {/* Volume Profile Section */}
          {showVolumeProfile && (
            <div className="p-2 border-b border-[#1e293b] flex flex-col">
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-[10px] font-bold text-indigo-400 flex items-center gap-1">
                  <BarChart3 size={11} /> VOLUME PROFILE
                </span>
                <span className="text-[9px] text-slate-500">70% VA</span>
              </div>
              <div className="space-y-1 text-[10px]">
                <div className="flex justify-between text-slate-400">
                  <span>VAH:</span>
                  <span className="text-white font-bold">${volumeProfile.vah.toLocaleString()}</span>
                </div>
                <div className="flex justify-between text-amber-300 font-bold bg-amber-950/30 px-1 py-0.5 rounded border border-amber-500/30">
                  <span>VPOC:</span>
                  <span>${volumeProfile.vpoc.toLocaleString()}</span>
                </div>
                <div className="flex justify-between text-slate-400">
                  <span>VAL:</span>
                  <span className="text-white font-bold">${volumeProfile.val.toLocaleString()}</span>
                </div>
              </div>

              {/* Volume Distribution Mini-Bars */}
              <div className="mt-2 space-y-0.5">
                {volumeProfile.bins.slice(0, 10).map((bin, i) => (
                  <div key={i} className="flex items-center gap-1 text-[8px]">
                    <span className="w-10 text-slate-500 text-right truncate">${bin.price}</span>
                    <div className="flex-1 h-1.5 rounded-sm bg-slate-900 overflow-hidden">
                      <div
                        className={`h-full ${bin.isPOC ? 'bg-amber-400' : bin.isValueArea ? 'bg-indigo-500' : 'bg-slate-700'}`}
                        style={{ width: `${Math.min(100, bin.percentage * 8)}%` }}
                      ></div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Liquidation Map Section */}
          {showLiquidationMap && (
            <div className="p-2 flex-1 flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-[10px] font-bold text-amber-400 flex items-center gap-1">
                    <Flame size={11} /> LIQUIDATIONS
                  </span>
                  <span className="text-[9px] text-slate-500">DERIVATIVES</span>
                </div>

                {/* Short Liquidations Above */}
                <div className="space-y-1 mb-2">
                  <span className="text-[8px] text-slate-500 uppercase tracking-wider block">Short Squeeze Targets</span>
                  {liquidationMap.shortClusters.map((c, i) => (
                    <div key={i} className="p-1 rounded bg-rose-950/30 border border-rose-800/40 text-[9px] space-y-0.5">
                      <div className="flex justify-between text-rose-300 font-bold">
                        <span>${c.priceLevel.toLocaleString()}</span>
                        <span>+{c.distancePct}%</span>
                      </div>
                      <div className="flex justify-between text-slate-400 text-[8px]">
                        <span>Est: ${(c.estimatedVolumeUsd / 1e6).toFixed(1)}M</span>
                        <span className="text-amber-400">{c.leverageTier}</span>
                      </div>
                    </div>
                  ))}
                </div>

                {/* Long Liquidations Below */}
                <div className="space-y-1">
                  <span className="text-[8px] text-slate-500 uppercase tracking-wider block">Long Flush Floors</span>
                  {liquidationMap.longClusters.map((c, i) => (
                    <div key={i} className="p-1 rounded bg-emerald-950/30 border border-emerald-800/40 text-[9px] space-y-0.5">
                      <div className="flex justify-between text-emerald-300 font-bold">
                        <span>${c.priceLevel.toLocaleString()}</span>
                        <span>{c.distancePct}%</span>
                      </div>
                      <div className="flex justify-between text-slate-400 text-[8px]">
                        <span>Est: ${(c.estimatedVolumeUsd / 1e6).toFixed(1)}M</span>
                        <span className="text-cyan-400">{c.leverageTier}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Status Note */}
              <div className="pt-2 mt-2 border-t border-[#1e293b]/70 text-[8px] text-slate-500 text-center">
                Synchronized Derivatives Map
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
