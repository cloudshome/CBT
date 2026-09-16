import React, { useState, useMemo, useRef } from 'react';
import { Layers, Eye, EyeOff, BarChart2 } from 'lucide-react';
import { OHLCVCandle, FVGItem, OrderBlockItem, IndicatorPoint } from '../types';

interface CandleChartProps {
  symbol: string;
  candles: OHLCVCandle[];
  fvgs?: FVGItem[];
  orderBlocks?: OrderBlockItem[];
  ema?: IndicatorPoint[];
  loading?: boolean;
}

export const CandleChart: React.FC<CandleChartProps> = ({
  symbol,
  candles,
  fvgs = [],
  orderBlocks = [],
  ema = [],
  loading = false,
}) => {
  const [showFVG, setShowFVG] = useState(true);
  const [showOB, setShowOB] = useState(true);
  const [showEMA, setShowEMA] = useState(true);
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  const containerRef = useRef<HTMLDivElement>(null);

  // Chart dimensions & scaling calculations
  const chartHeight = 360;
  const volumeHeight = 70;
  const svgHeight = chartHeight + volumeHeight;
  const svgWidth = 800; // viewBox coordinate space

  const candleData = useMemo(() => {
    if (!candles || candles.length === 0) return [];
    // Take recent 60 candles for crisp display
    const slice = candles.slice(-60);
    return slice.map(([ts, o, h, l, c, v], i) => ({
      index: i,
      timestamp: ts,
      open: o,
      high: h,
      low: l,
      close: c,
      volume: v,
      isGreen: c >= o,
    }));
  }, [candles]);

  const { minPrice, maxPrice, maxVolume } = useMemo(() => {
    if (candleData.length === 0) return { minPrice: 0, maxPrice: 1, maxVolume: 1 };

    let min = Infinity;
    let max = -Infinity;
    let maxVol = 0;

    candleData.forEach((c) => {
      if (c.low < min) min = c.low;
      if (c.high > max) max = c.high;
      if (c.volume > maxVol) maxVol = c.volume;
    });

    const padding = (max - min) * 0.08 || 1;
    return {
      minPrice: min - padding,
      maxPrice: max + padding,
      maxVolume: maxVol > 0 ? maxVol : 1,
    };
  }, [candleData]);

  // Coordinate conversion helpers
  const getX = (index: number) => {
    const spacing = svgWidth / (candleData.length || 1);
    return index * spacing + spacing / 2;
  };

  const getY = (price: number) => {
    if (maxPrice === minPrice) return chartHeight / 2;
    const ratio = (price - minPrice) / (maxPrice - minPrice);
    return chartHeight - ratio * chartHeight;
  };

  const getVolY = (vol: number) => {
    const ratio = vol / maxVolume;
    return svgHeight - ratio * volumeHeight;
  };

  const activeCandle = hoverIndex !== null && candleData[hoverIndex] ? candleData[hoverIndex] : candleData[candleData.length - 1];

  // Build EMA polyline points
  const emaPoints = useMemo(() => {
    if (!showEMA || !ema || ema.length === 0 || candleData.length === 0) return '';
    const points: string[] = [];
    const candleTsMap = new Map(candleData.map((c) => [c.timestamp, c.index]));

    ema.forEach((pt) => {
      if (candleTsMap.has(pt.timestamp)) {
        const idx = candleTsMap.get(pt.timestamp)!;
        const x = getX(idx);
        const y = getY(pt.value);
        points.push(`${x},${y}`);
      }
    });

    return points.join(' ');
  }, [showEMA, ema, candleData, maxPrice, minPrice]);

  return (
    <div className="bg-background-card border border-border rounded-lg p-4 flex flex-col h-full shadow-lg">
      {/* Chart Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3 pb-3 border-b border-border">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 text-xs font-mono font-bold text-slate-200">
            <BarChart2 className="w-4 h-4 text-terminal-cyan" />
            <span>{symbol} CANDLESTICK &amp; SMC ENGINE</span>
          </div>

          {activeCandle && (
            <div className="hidden sm:flex items-center gap-3 text-[11px] font-mono text-slate-400">
              <span>O: <span className={activeCandle.isGreen ? 'text-terminal-green' : 'text-terminal-red'}>{activeCandle.open.toFixed(2)}</span></span>
              <span>H: <span className={activeCandle.isGreen ? 'text-terminal-green' : 'text-terminal-red'}>{activeCandle.high.toFixed(2)}</span></span>
              <span>L: <span className={activeCandle.isGreen ? 'text-terminal-green' : 'text-terminal-red'}>{activeCandle.low.toFixed(2)}</span></span>
              <span>C: <span className={activeCandle.isGreen ? 'text-terminal-green' : 'text-terminal-red'}>{activeCandle.close.toFixed(2)}</span></span>
              <span>Vol: <span className="text-slate-300">{activeCandle.volume.toFixed(1)}</span></span>
            </div>
          )}
        </div>

        {/* Overlay Toggles */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowFVG(!showFVG)}
            className={`px-2 py-1 rounded text-[11px] font-mono flex items-center gap-1 border transition-all ${
              showFVG
                ? 'bg-terminal-cyan/10 border-terminal-cyan/40 text-terminal-cyan'
                : 'bg-background border-border text-slate-500'
            }`}
          >
            {showFVG ? <Eye className="w-3 h-3" /> : <EyeOff className="w-3 h-3" />}
            <span>FVG ({fvgs.length})</span>
          </button>

          <button
            onClick={() => setShowOB(!showOB)}
            className={`px-2 py-1 rounded text-[11px] font-mono flex items-center gap-1 border transition-all ${
              showOB
                ? 'bg-terminal-purple/10 border-terminal-purple/40 text-terminal-purple'
                : 'bg-background border-border text-slate-500'
            }`}
          >
            {showOB ? <Eye className="w-3 h-3" /> : <EyeOff className="w-3 h-3" />}
            <span>OB ({orderBlocks.length})</span>
          </button>

          <button
            onClick={() => setShowEMA(!showEMA)}
            className={`px-2 py-1 rounded text-[11px] font-mono flex items-center gap-1 border transition-all ${
              showEMA
                ? 'bg-terminal-amber/10 border-terminal-amber/40 text-terminal-amber'
                : 'bg-background border-border text-slate-500'
            }`}
          >
            <Layers className="w-3 h-3" />
            <span>EMA(14)</span>
          </button>
        </div>
      </div>

      {/* SVG Canvas Area */}
      <div
        ref={containerRef}
        className="relative flex-1 min-h-[360px] w-full bg-[#080B10] rounded border border-border/50 overflow-hidden select-none cursor-crosshair"
        onMouseLeave={() => setHoverIndex(null)}
        onMouseMove={(e) => {
          if (!containerRef.current || candleData.length === 0) return;
          const rect = containerRef.current.getBoundingClientRect();
          const relX = e.clientX - rect.left;
          const pct = Math.max(0, Math.min(1, relX / rect.width));
          const idx = Math.floor(pct * candleData.length);
          setHoverIndex(Math.min(idx, candleData.length - 1));
        }}
      >
        {loading ? (
          <div className="absolute inset-0 flex items-center justify-center bg-background/80 z-20">
            <div className="flex flex-col items-center gap-2 font-mono text-xs text-terminal-cyan">
              <div className="w-6 h-6 border-2 border-terminal-cyan border-t-transparent rounded-full animate-spin" />
              <span>STREAMING TELEMETRY...</span>
            </div>
          </div>
        ) : candleData.length === 0 ? (
          <div className="absolute inset-0 flex items-center justify-center font-mono text-xs text-slate-500">
            No candlestick data available.
          </div>
        ) : (
          <svg
            viewBox={`0 0 ${svgWidth} ${svgHeight}`}
            className="w-full h-full"
            preserveAspectRatio="none"
          >
            <defs>
              <linearGradient id="bullishFvgGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#00FF9D" stopOpacity="0.25" />
                <stop offset="100%" stopColor="#00FF9D" stopOpacity="0.05" />
              </linearGradient>
              <linearGradient id="bearishFvgGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#FF3B69" stopOpacity="0.25" />
                <stop offset="100%" stopColor="#FF3B69" stopOpacity="0.05" />
              </linearGradient>
            </defs>

            {/* Price Grid Lines */}
            {[0.25, 0.5, 0.75].map((p, i) => {
              const y = chartHeight * p;
              const price = maxPrice - p * (maxPrice - minPrice);
              return (
                <g key={i}>
                  <line
                    x1="0"
                    y1={y}
                    x2={svgWidth}
                    y2={y}
                    stroke="#161F2E"
                    strokeDasharray="4 4"
                    strokeWidth="1"
                  />
                  <text
                    x={svgWidth - 6}
                    y={y - 4}
                    fill="#4A5568"
                    fontSize="10"
                    fontFamily="monospace"
                    textAnchor="end"
                  >
                    {price.toFixed(2)}
                  </text>
                </g>
              );
            })}

            {/* FVG Overlay Zones */}
            {showFVG &&
              (fvgs || []).map((fvg, idx) => {
                if (!fvg) return null;
                const rawZone = fvg.price_zone || ((fvg as any).bottom_price != null && (fvg as any).top_price != null ? [(fvg as any).bottom_price, (fvg as any).top_price] : null);
                if (!rawZone || !Array.isArray(rawZone) || rawZone.length < 2) return null;
                const pBot = Number(rawZone[0]);
                const pTop = Number(rawZone[1]);
                if (isNaN(pBot) || isNaN(pTop)) return null;

                const y1 = getY(Math.max(pBot, pTop));
                const y2 = getY(Math.min(pBot, pTop));
                const rectHeight = Math.max(2, Math.abs(y2 - y1));
                const topY = Math.min(y1, y2);
                const isBullish = fvg.type === 'bullish';

                return (
                  <g key={`fvg-${idx}`}>
                    <rect
                      x="0"
                      y={topY}
                      width={svgWidth}
                      height={rectHeight}
                      fill={isBullish ? 'url(#bullishFvgGrad)' : 'url(#bearishFvgGrad)'}
                      stroke={isBullish ? '#00FF9D' : '#FF3B69'}
                      strokeWidth="0.8"
                      strokeDasharray="3 3"
                      opacity={fvg.mitigated ? 0.35 : 0.85}
                    />
                    <text
                      x="12"
                      y={topY + 12}
                      fill={isBullish ? '#00FF9D' : '#FF3B69'}
                      fontSize="9"
                      fontFamily="monospace"
                      fontWeight="bold"
                      opacity="0.8"
                    >
                      {(fvg.type || 'fvg').toUpperCase()} FVG [{pBot} - {pTop}]{' '}
                      {fvg.mitigated ? '(MITIGATED)' : '(ACTIVE)'}
                    </text>
                  </g>
                );
              })}

            {/* Order Block Overlay Zones */}
            {showOB &&
              (orderBlocks || []).map((ob, idx) => {
                if (!ob) return null;
                const rawZone = ob.price_zone || ((ob as any).bottom_price != null && (ob as any).top_price != null ? [(ob as any).bottom_price, (ob as any).top_price] : null);
                if (!rawZone || !Array.isArray(rawZone) || rawZone.length < 2) return null;
                const pBot = Number(rawZone[0]);
                const pTop = Number(rawZone[1]);
                if (isNaN(pBot) || isNaN(pTop)) return null;

                const y1 = getY(Math.max(pBot, pTop));
                const y2 = getY(Math.min(pBot, pTop));
                const rectHeight = Math.max(2, Math.abs(y2 - y1));
                const topY = Math.min(y1, y2);
                const isBullish = ob.type === 'bullish';

                return (
                  <g key={`ob-${idx}`}>
                    <rect
                      x="0"
                      y={topY}
                      width={svgWidth}
                      height={rectHeight}
                      fill={isBullish ? 'rgba(0, 240, 255, 0.12)' : 'rgba(176, 38, 255, 0.12)'}
                      stroke={isBullish ? '#00F0FF' : '#B026FF'}
                      strokeWidth="1"
                      opacity={ob.mitigated ? 0.3 : 0.75}
                    />
                    <text
                      x={svgWidth - 140}
                      y={topY + 12}
                      fill={isBullish ? '#00F0FF' : '#B026FF'}
                      fontSize="9"
                      fontFamily="monospace"
                      fontWeight="bold"
                    >
                      {(ob.type || 'ob').toUpperCase()} OB [{pBot}]
                    </text>
                  </g>
                );
              })}

            {/* Volume Separator */}
            <line
              x1="0"
              y1={chartHeight}
              x2={svgWidth}
              y2={chartHeight}
              stroke="#232B3E"
              strokeWidth="1"
            />

            {/* Volume Bars */}
            {candleData.map((c) => {
              const x = getX(c.index);
              const barWidth = Math.max(2, svgWidth / candleData.length - 2);
              const volY = getVolY(c.volume);
              const barH = svgHeight - volY;

              return (
                <rect
                  key={`vol-${c.index}`}
                  x={x - barWidth / 2}
                  y={volY}
                  width={barWidth}
                  height={barH}
                  fill={c.isGreen ? '#00FF9D' : '#FF3B69'}
                  opacity={hoverIndex === c.index ? 0.9 : 0.3}
                />
              );
            })}

            {/* Candlesticks */}
            {candleData.map((c) => {
              const x = getX(c.index);
              const openY = getY(c.open);
              const closeY = getY(c.close);
              const highY = getY(c.high);
              const lowY = getY(c.low);

              const candleTop = Math.min(openY, closeY);
              const candleHeight = Math.max(1.5, Math.abs(closeY - openY));
              const candleWidth = Math.max(3, svgWidth / candleData.length - 3);
              const color = c.isGreen ? '#00FF9D' : '#FF3B69';

              return (
                <g key={`candle-${c.index}`}>
                  {/* High / Low Wick */}
                  <line
                    x1={x}
                    y1={highY}
                    x2={x}
                    y2={lowY}
                    stroke={color}
                    strokeWidth="1.2"
                  />
                  {/* Open / Close Body */}
                  <rect
                    x={x - candleWidth / 2}
                    y={candleTop}
                    width={candleWidth}
                    height={candleHeight}
                    fill={c.isGreen ? '#00FF9D' : '#FF3B69'}
                    stroke={color}
                    strokeWidth="0.5"
                    rx="0.5"
                  />
                </g>
              );
            })}

            {/* EMA Line Overlay */}
            {emaPoints && (
              <polyline
                fill="none"
                stroke="#FFB800"
                strokeWidth="1.5"
                points={emaPoints}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            )}

            {/* Hover Crosshair */}
            {hoverIndex !== null && candleData[hoverIndex] && (
              <g>
                <line
                  x1={getX(hoverIndex)}
                  y1="0"
                  x2={getX(hoverIndex)}
                  y2={svgHeight}
                  stroke="#00F0FF"
                  strokeWidth="1"
                  strokeDasharray="2 2"
                />
                <line
                  x1="0"
                  y1={getY(candleData[hoverIndex].close)}
                  x2={svgWidth}
                  y2={getY(candleData[hoverIndex].close)}
                  stroke="#00F0FF"
                  strokeWidth="1"
                  strokeDasharray="2 2"
                />
                {/* Price tag on axis */}
                <rect
                  x={svgWidth - 65}
                  y={getY(candleData[hoverIndex].close) - 10}
                  width="60"
                  height="20"
                  fill="#00F0FF"
                  rx="2"
                />
                <text
                  x={svgWidth - 35}
                  y={getY(candleData[hoverIndex].close) + 4}
                  fill="#0B0E14"
                  fontSize="10"
                  fontWeight="bold"
                  fontFamily="monospace"
                  textAnchor="middle"
                >
                  {candleData[hoverIndex].close.toFixed(2)}
                </text>
              </g>
            )}
          </svg>
        )}
      </div>
    </div>
  );
};
