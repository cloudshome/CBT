import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import {
  Activity,
  Layers,
  Flame,
  RefreshCw,
  ShieldAlert,
  Info,
  TrendingUp,
  Clock,
} from 'lucide-react';
import {
  getHeatmapSnapshot,
  HeatmapSnapshotResponse,
  HeatmapWallItem,
} from '../services/api';
import { marketProvider, OrderBookDepth } from '../data/providers/marketProvider';

interface OrderBookHeatmapDeskProps {
  currentSymbol?: string;
  onNotify?: (type: 'success' | 'error' | 'warning' | 'info', title: string, message: string) => void;
}

type PaletteType = 'OBSIDIAN_NEON' | 'INFERNO' | 'CYBERPUNK_CYAN';

interface ColorStop {
  stop: number; // 0.0 to 1.0
  r: number;
  g: number;
  b: number;
}

const PALETTES: Record<PaletteType, { name: string; stops: ColorStop[] }> = {
  OBSIDIAN_NEON: {
    name: 'Obsidian Neon',
    stops: [
      { stop: 0.0, r: 7, g: 10, b: 18 },      // Dark void
      { stop: 0.2, r: 30, g: 27, b: 75 },     // Indigo
      { stop: 0.5, r: 2, g: 132, b: 199 },    // Sky cyan
      { stop: 0.8, r: 234, g: 179, b: 8 },    // Amber
      { stop: 1.0, r: 244, g: 63, b: 94 },    // Neon Rose
    ],
  },
  INFERNO: {
    name: 'Inferno',
    stops: [
      { stop: 0.0, r: 0, g: 0, b: 4 },
      { stop: 0.25, r: 87, g: 16, b: 110 },
      { stop: 0.5, r: 187, g: 55, b: 84 },
      { stop: 0.75, r: 249, g: 142, b: 9 },
      { stop: 1.0, r: 252, g: 255, b: 164 },
    ],
  },
  CYBERPUNK_CYAN: {
    name: 'Cyberpunk Cyan',
    stops: [
      { stop: 0.0, r: 5, g: 8, b: 17 },
      { stop: 0.25, r: 15, g: 41, b: 66 },
      { stop: 0.6, r: 6, g: 182, b: 212 },
      { stop: 0.85, r: 16, g: 185, b: 129 },
      { stop: 1.0, r: 168, g: 85, b: 247 },
    ],
  },
};

function interpolateColor(stops: ColorStop[], t: number): [number, number, number] {
  const clampedT = Math.max(0, Math.min(1, t));
  for (let i = 0; i < stops.length - 1; i++) {
    const s0 = stops[i];
    const s1 = stops[i + 1];
    if (clampedT >= s0.stop && clampedT <= s1.stop) {
      const range = s1.stop - s0.stop;
      const factor = range > 0 ? (clampedT - s0.stop) / range : 0;
      return [
        Math.round(s0.r + (s1.r - s0.r) * factor),
        Math.round(s0.g + (s1.g - s0.g) * factor),
        Math.round(s0.b + (s1.b - s0.b) * factor),
      ];
    }
  }
  const last = stops[stops.length - 1];
  return [last.r, last.g, last.b];
}

const SUPPORTED_SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'PAXG/USDT'];

export const OrderBookHeatmapDesk: React.FC<OrderBookHeatmapDeskProps> = ({
  currentSymbol = 'BTC/USDT',
  onNotify,
}) => {
  const [symbol, setSymbol] = useState<string>(
    SUPPORTED_SYMBOLS.includes(currentSymbol) ? currentSymbol : 'BTC/USDT'
  );
  const [windowFrames, setWindowFrames] = useState<number>(300);
  const [priceBinsCount] = useState<number>(80);
  const [palette, setPalette] = useState<PaletteType>('OBSIDIAN_NEON');
  const [showPricePath, setShowPricePath] = useState<boolean>(true);
  const [showWalls, setShowWalls] = useState<boolean>(true);
  const [showLiquidations, setShowLiquidations] = useState<boolean>(true);
  const [loading, setLoading] = useState<boolean>(true);
  const [liveStreamConnected, setLiveStreamConnected] = useState<boolean>(false);

  // Live order book for right-side DOM ladder
  const [liveDepth, setLiveDepth] = useState<OrderBookDepth | null>(null);

  // Heatmap snapshot reference (managed via ref to decouple render loop from React state)
  const snapshotDataRef = useRef<HeatmapSnapshotResponse | null>(null);
  const [activeSnapshot, setActiveSnapshot] = useState<HeatmapSnapshotResponse | null>(null);

  // Canvas References
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  // Tooltip & Mouse state
  const [hoverInfo, setHoverInfo] = useState<{
    x: number;
    y: number;
    timeStr: string;
    price: number;
    density: number;
    wall?: HeatmapWallItem;
  } | null>(null);

  // -------------------------------------------------------------------------
  // 1. Data Fetching & Subscription Lifecycle
  // -------------------------------------------------------------------------

  const fetchSnapshot = useCallback(async () => {
    try {
      setLoading(true);
      const data = await getHeatmapSnapshot(symbol, windowFrames, priceBinsCount);
      snapshotDataRef.current = data;
      setActiveSnapshot(data);
    } catch (err) {
      if (onNotify) {
        onNotify('error', 'Heatmap Error', 'Failed to retrieve order book heatmap snapshot');
      }
    } finally {
      setLoading(false);
    }
  }, [symbol, windowFrames, priceBinsCount, onNotify]);

  useEffect(() => {
    fetchSnapshot();
  }, [fetchSnapshot]);

  // Periodic background refresh for resting wall state transitions
  useEffect(() => {
    const timer = setInterval(() => {
      getHeatmapSnapshot(symbol, windowFrames, priceBinsCount)
        .then((data) => {
          snapshotDataRef.current = data;
          setActiveSnapshot(data);
        })
        .catch(() => {});
    }, 4000);
    return () => clearInterval(timer);
  }, [symbol, windowFrames, priceBinsCount]);

  // Connect to live market depth stream for the right-margin DOM ladder
  useEffect(() => {
    const unsub = marketProvider.subscribeOrderBook(symbol, (depth) => {
      setLiveDepth(depth);
      setLiveStreamConnected(true);
    });

    return () => {
      unsub();
      setLiveStreamConnected(false);
    };
  }, [symbol]);

  // -------------------------------------------------------------------------
  // 2. High-Performance Canvas Rendering Loop (Zero-Shake)
  // -------------------------------------------------------------------------

  const renderCanvas = useCallback(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const rect = container.getBoundingClientRect();
    const width = rect.width;
    const height = rect.height;

    // Handle high-DPI scaling
    if (canvas.width !== width * dpr || canvas.height !== height * dpr) {
      canvas.width = width * dpr;
      canvas.height = height * dpr;
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
    }

    ctx.save();
    ctx.scale(dpr, dpr);

    // Clear background
    ctx.fillStyle = '#060910';
    ctx.fillRect(0, 0, width, height);

    const snapshot = snapshotDataRef.current;
    if (!snapshot || !snapshot.heatmap || snapshot.heatmap.density_matrix.length === 0) {
      ctx.fillStyle = '#64748b';
      ctx.font = '12px JetBrains Mono, monospace';
      ctx.textAlign = 'center';
      ctx.fillText('INITIALIZING HIGH-FREQUENCY LIQUIDITY BUFFER...', width / 2, height / 2);
      ctx.restore();
      return;
    }

    const { density_matrix, price_bins, mid_price_path, timestamps } = snapshot.heatmap;
    const numFrames = density_matrix.length;
    const numBins = price_bins.length;

    if (numFrames === 0 || numBins === 0) {
      ctx.restore();
      return;
    }

    const minPrice = price_bins[0];
    const maxPrice = price_bins[numBins - 1];
    const priceRange = maxPrice - minPrice || 1;

    // Margins for price axis & timestamps
    const marginLeft = 8;
    const marginRight = 65; // space for price labels
    const marginBottom = 22; // space for timestamp labels
    const marginTop = 12;

    const plotWidth = width - marginLeft - marginRight;
    const plotHeight = height - marginTop - marginBottom;

    // A. Render Heatmap Density Matrix
    const colWidth = plotWidth / numFrames;
    const rowHeight = plotHeight / numBins;
    const paletteStops = PALETTES[palette].stops;

    for (let f = 0; f < numFrames; f++) {
      const x = marginLeft + f * colWidth;
      const frameDensity = density_matrix[f];

      for (let b = 0; b < numBins; b++) {
        const intensity = frameDensity[b]; // 0 to 100
        if (intensity <= 0) continue;

        // Invert Y axis: lowest price at bottom
        const y = marginTop + (numBins - 1 - b) * rowHeight;
        const [r, g, bColor] = interpolateColor(paletteStops, intensity / 100.0);

        ctx.fillStyle = `rgb(${r}, ${g}, ${bColor})`;
        ctx.fillRect(Math.floor(x), Math.floor(y), Math.ceil(colWidth), Math.ceil(rowHeight));
      }
    }

    // B. Render Mid-Price Trajectory Line
    if (showPricePath && mid_price_path.length > 0) {
      ctx.beginPath();
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 1.5;
      ctx.shadowColor = '#38bdf8';
      ctx.shadowBlur = 4;

      for (let f = 0; f < mid_price_path.length; f++) {
        const p = mid_price_path[f];
        const x = marginLeft + f * colWidth + colWidth / 2;
        const y = marginTop + plotHeight - ((p - minPrice) / priceRange) * plotHeight;

        if (f === 0) {
          ctx.moveTo(x, y);
        } else {
          ctx.lineTo(x, y);
        }
      }
      ctx.stroke();
      ctx.shadowBlur = 0;

      // Current Price Dot at right edge
      const lastP = mid_price_path[mid_price_path.length - 1];
      const lastX = marginLeft + (mid_price_path.length - 1) * colWidth + colWidth / 2;
      const lastY = marginTop + plotHeight - ((lastP - minPrice) / priceRange) * plotHeight;

      ctx.fillStyle = '#38bdf8';
      ctx.beginPath();
      ctx.arc(lastX, lastY, 3.5, 0, Math.PI * 2);
      ctx.fill();
    }

    // C. Render Active Resting Walls
    if (showWalls && snapshot.walls && snapshot.walls.active_walls) {
      for (const wall of snapshot.walls.active_walls) {
        if (wall.price < minPrice || wall.price > maxPrice) continue;

        const y = marginTop + plotHeight - ((wall.price - minPrice) / priceRange) * plotHeight;
        const isBid = wall.side === 'BID';

        ctx.strokeStyle = isBid ? 'rgba(16, 185, 129, 0.85)' : 'rgba(244, 63, 94, 0.85)';
        ctx.lineWidth = wall.persistence_score > 0.7 ? 2 : 1;
        ctx.setLineDash([4, 2]);

        ctx.beginPath();
        ctx.moveTo(marginLeft, y);
        ctx.lineTo(marginLeft + plotWidth, y);
        ctx.stroke();
        ctx.setLineDash([]);

        // Wall Size Label at right edge
        ctx.fillStyle = isBid ? '#10b981' : '#f43f5e';
        ctx.font = '9px JetBrains Mono, monospace';
        ctx.textAlign = 'right';
        ctx.fillText(
          `${wall.side} ${wall.price.toFixed(1)} (${(wall.notional_usd / 1000).toFixed(0)}k)`,
          marginLeft + plotWidth - 4,
          y - 3
        );
      }
    }

    // D. Render Estimated Liquidation Cascade Bands
    if (showLiquidations && snapshot.liquidations && snapshot.liquidations.bands) {
      for (const band of snapshot.liquidations.bands) {
        if (band.price < minPrice || band.price > maxPrice) continue;

        const y = marginTop + plotHeight - ((band.price - minPrice) / priceRange) * plotHeight;
        const isLong = band.side === 'LONG_LIQUIDATION';

        ctx.strokeStyle = isLong ? 'rgba(234, 179, 8, 0.7)' : 'rgba(168, 85, 247, 0.7)';
        ctx.lineWidth = 1;
        ctx.setLineDash([2, 4]);

        ctx.beginPath();
        ctx.moveTo(marginLeft, y);
        ctx.lineTo(marginLeft + plotWidth, y);
        ctx.stroke();
        ctx.setLineDash([]);

        // Liquidation Tag
        ctx.fillStyle = isLong ? '#eab308' : '#c084fc';
        ctx.font = '8px JetBrains Mono, monospace';
        ctx.textAlign = 'left';
        ctx.fillText(
          `${band.leverage_tier}x LIQ ${band.price.toFixed(1)} (EST)`,
          marginLeft + 6,
          y - 2
        );
      }
    }

    // E. Price Axis Labels (Right Margin)
    ctx.fillStyle = '#94a3b8';
    ctx.font = '10px JetBrains Mono, monospace';
    ctx.textAlign = 'left';

    const numTicks = 8;
    for (let i = 0; i <= numTicks; i++) {
      const p = minPrice + (i / numTicks) * priceRange;
      const y = marginTop + plotHeight - (i / numTicks) * plotHeight;
      ctx.fillText(p.toFixed(1), marginLeft + plotWidth + 6, y + 3);

      // Grid guideline
      ctx.strokeStyle = 'rgba(30, 41, 59, 0.35)';
      ctx.beginPath();
      ctx.moveTo(marginLeft, y);
      ctx.lineTo(marginLeft + plotWidth, y);
      ctx.stroke();
    }

    // F. Timestamp Axis Labels (Bottom Margin)
    if (timestamps && timestamps.length > 0) {
      ctx.fillStyle = '#64748b';
      ctx.font = '9px JetBrains Mono, monospace';
      ctx.textAlign = 'center';

      const timeStep = Math.max(1, Math.floor(numFrames / 5));
      for (let i = 0; i < numFrames; i += timeStep) {
        const x = marginLeft + i * colWidth;
        const d = new Date(timestamps[i]);
        const timeStr = `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}:${d.getSeconds().toString().padStart(2, '0')}`;
        ctx.fillText(timeStr, x, height - 6);
      }
    }

    ctx.restore();
  }, [palette, showPricePath, showWalls, showLiquidations]);

  useEffect(() => {
    renderCanvas();
  }, [renderCanvas, activeSnapshot]);

  // -------------------------------------------------------------------------
  // 3. Mouse Interaction & Tooltip
  // -------------------------------------------------------------------------

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    const snapshot = snapshotDataRef.current;
    if (!canvas || !snapshot || !snapshot.heatmap) return;

    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    const { density_matrix, price_bins, timestamps } = snapshot.heatmap;
    const numFrames = density_matrix.length;
    const numBins = price_bins.length;

    const marginLeft = 8;
    const marginRight = 65;
    const marginBottom = 22;
    const marginTop = 12;

    const plotWidth = rect.width - marginLeft - marginRight;
    const plotHeight = rect.height - marginTop - marginBottom;

    if (x < marginLeft || x > marginLeft + plotWidth || y < marginTop || y > marginTop + plotHeight) {
      setHoverInfo(null);
      return;
    }

    const colWidth = plotWidth / numFrames;
    const frameIdx = Math.min(numFrames - 1, Math.max(0, Math.floor((x - marginLeft) / colWidth)));
    const binIdx = Math.min(
      numBins - 1,
      Math.max(0, Math.floor((marginTop + plotHeight - y) / (plotHeight / numBins)))
    );

    const price = price_bins[binIdx];
    const density = density_matrix[frameIdx][binIdx] || 0;
    const ts = timestamps[frameIdx];
    const timeStr = new Date(ts).toLocaleTimeString();

    // Check if hovering near a resting wall
    const nearbyWall = snapshot.walls.active_walls.find(
      (w) => Math.abs(w.price - price) / price < 0.001
    );

    setHoverInfo({
      x,
      y,
      timeStr,
      price,
      density,
      wall: nearbyWall,
    });
  };

  const handleMouseLeave = () => {
    setHoverInfo(null);
  };

  // -------------------------------------------------------------------------
  // 4. Metrics & Scorecard Calculations
  // -------------------------------------------------------------------------

  const totalBidWallUsd = useMemo(() => {
    if (!activeSnapshot?.walls?.active_walls) return 0;
    return activeSnapshot.walls.active_walls
      .filter((w) => w.side === 'BID')
      .reduce((acc, w) => acc + w.notional_usd, 0);
  }, [activeSnapshot]);

  const totalAskWallUsd = useMemo(() => {
    if (!activeSnapshot?.walls?.active_walls) return 0;
    return activeSnapshot.walls.active_walls
      .filter((w) => w.side === 'ASK')
      .reduce((acc, w) => acc + w.notional_usd, 0);
  }, [activeSnapshot]);

  const wallImbalanceRatio = useMemo(() => {
    const total = totalBidWallUsd + totalAskWallUsd;
    if (total === 0) return 0;
    return ((totalBidWallUsd - totalAskWallUsd) / total) * 100;
  }, [totalBidWallUsd, totalAskWallUsd]);

  return (
    <div className="flex flex-col gap-3 font-mono text-xs text-slate-200">
      {/* Top Header & Interactive Cockpit Controls */}
      <div className="flex flex-wrap items-center justify-between gap-2 p-2.5 bg-[#090d16] border border-[#1e293b] rounded-lg">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <Flame className="w-4 h-4 text-amber-500 animate-pulse" />
            <span className="font-bold text-sm text-slate-100 tracking-wider">
              ORDER BOOK HEATMAP & RESTING WALL SENTINEL
            </span>
          </div>

          <div className="flex items-center gap-1.5 ml-2">
            {SUPPORTED_SYMBOLS.map((sym) => (
              <button
                key={sym}
                onClick={() => setSymbol(sym)}
                className={`px-2 py-0.5 rounded text-[11px] font-semibold transition-all ${
                  symbol === sym
                    ? 'bg-amber-500 text-slate-950 shadow-sm shadow-amber-500/30'
                    : 'bg-[#131b2e] text-slate-400 hover:text-slate-200'
                }`}
              >
                {sym}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-1 text-[11px] bg-[#0c1322] px-2 py-0.5 rounded border border-[#1e293b]">
            <span className="text-slate-400">Stream:</span>
            {liveStreamConnected ? (
              <span className="text-emerald-400 flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping" />
                LIVE WS
              </span>
            ) : (
              <span className="text-amber-400">POLLING</span>
            )}
          </div>
        </div>

        {/* Display & Overlay Toggles */}
        <div className="flex items-center gap-2">
          {/* Palette Selector */}
          <select
            value={palette}
            onChange={(e) => setPalette(e.target.value as PaletteType)}
            className="bg-[#131b2e] border border-[#1e293b] rounded px-2 py-0.5 text-[11px] text-slate-300 focus:outline-none"
          >
            <option value="OBSIDIAN_NEON">Obsidian Neon</option>
            <option value="INFERNO">Inferno</option>
            <option value="CYBERPUNK_CYAN">Cyberpunk Cyan</option>
          </select>

          {/* Window Frames */}
          <select
            value={windowFrames}
            onChange={(e) => setWindowFrames(Number(e.target.value))}
            className="bg-[#131b2e] border border-[#1e293b] rounded px-2 py-0.5 text-[11px] text-slate-300 focus:outline-none"
          >
            <option value={100}>100 Frames (~1.5m)</option>
            <option value={300}>300 Frames (~5m)</option>
            <option value={600}>600 Frames (~10m)</option>
          </select>

          {/* Toggles */}
          <button
            onClick={() => setShowPricePath(!showPricePath)}
            className={`px-2 py-0.5 rounded text-[10px] border transition-all ${
              showPricePath
                ? 'bg-sky-500/20 border-sky-500/50 text-sky-300'
                : 'bg-[#131b2e] border-[#1e293b] text-slate-500'
            }`}
          >
            Price
          </button>
          <button
            onClick={() => setShowWalls(!showWalls)}
            className={`px-2 py-0.5 rounded text-[10px] border transition-all ${
              showWalls
                ? 'bg-emerald-500/20 border-emerald-500/50 text-emerald-300'
                : 'bg-[#131b2e] border-[#1e293b] text-slate-500'
            }`}
          >
            Walls
          </button>
          <button
            onClick={() => setShowLiquidations(!showLiquidations)}
            className={`px-2 py-0.5 rounded text-[10px] border transition-all ${
              showLiquidations
                ? 'bg-purple-500/20 border-purple-500/50 text-purple-300'
                : 'bg-[#131b2e] border-[#1e293b] text-slate-500'
            }`}
          >
            Liquidations (Est)
          </button>

          <button
            onClick={fetchSnapshot}
            disabled={loading}
            className="p-1 text-slate-400 hover:text-slate-200 bg-[#131b2e] border border-[#1e293b] rounded"
            title="Refresh Heatmap"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Main Content Area: Heatmap Canvas + Live DOM Ladder */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-3">
        {/* Left/Center: Heatmap Canvas Viewport (9 cols) */}
        <div
          ref={containerRef}
          className="xl:col-span-9 relative h-[480px] bg-[#060910] border border-[#1e293b] rounded-lg overflow-hidden flex flex-col"
        >
          <canvas
            ref={canvasRef}
            onMouseMove={handleMouseMove}
            onMouseLeave={handleMouseLeave}
            className="w-full h-full cursor-crosshair block"
          />

          {/* Floating Hover Tooltip */}
          {hoverInfo && (
            <div
              className="absolute pointer-events-none z-20 bg-[#0c1322]/95 border border-[#38bdf8]/40 p-2 rounded shadow-xl text-[11px] backdrop-blur-sm"
              style={{
                left: Math.min(hoverInfo.x + 12, (containerRef.current?.clientWidth || 500) - 180),
                top: Math.max(10, hoverInfo.y - 50),
              }}
            >
              <div className="text-slate-400 text-[10px]">{hoverInfo.timeStr}</div>
              <div className="text-sky-300 font-bold">Price: ${hoverInfo.price.toFixed(1)}</div>
              <div className="text-slate-300">Density: {hoverInfo.density}%</div>
              {hoverInfo.wall && (
                <div className="mt-1 pt-1 border-t border-slate-700/50 text-[10px]">
                  <span
                    className={`font-bold ${
                      hoverInfo.wall.side === 'BID' ? 'text-emerald-400' : 'text-rose-400'
                    }`}
                  >
                    {hoverInfo.wall.side} Wall:
                  </span>{' '}
                  {hoverInfo.wall.current_size.toFixed(2)} (${(hoverInfo.wall.notional_usd / 1000).toFixed(0)}k)
                  <div className="text-amber-400">
                    Persistence: {(hoverInfo.wall.persistence_score * 100).toFixed(0)}% ({hoverInfo.wall.status})
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Right Margin: Live Micro DOM Ladder (3 cols) */}
        <div className="xl:col-span-3 flex flex-col h-[480px] bg-[#090d16] border border-[#1e293b] rounded-lg overflow-hidden p-2">
          <div className="flex items-center justify-between pb-1.5 border-b border-[#1e293b] text-[11px] font-bold text-slate-300">
            <span className="flex items-center gap-1">
              <Layers className="w-3.5 h-3.5 text-cyan-400" />
              L2 DOM LADDER
            </span>
            <span className="text-[10px] text-slate-500 font-normal">REAL-TIME</span>
          </div>

          {/* Asks (Desc - Top to Bottom) */}
          <div className="flex-1 overflow-hidden flex flex-col justify-end py-1 text-[11px]">
            {liveDepth?.asks?.slice(0, 10).reverse().map((ask, idx) => {
              const maxAsk = Math.max(...(liveDepth.asks?.map((a) => a.size) || [1]));
              const pct = Math.min(100, (ask.size / maxAsk) * 100);
              return (
                <div
                  key={`ask-${idx}`}
                  className="relative flex items-center justify-between px-1 py-0.5 hover:bg-rose-500/10 transition-colors"
                >
                  <div
                    className="absolute right-0 top-0 bottom-0 bg-rose-500/15 pointer-events-none"
                    style={{ width: `${pct}%` }}
                  />
                  <span className="text-rose-400 font-semibold z-10">{ask.price.toFixed(1)}</span>
                  <span className="text-slate-300 z-10">{ask.size.toFixed(3)}</span>
                </div>
              );
            })}
          </div>

          {/* Spread Bar */}
          <div className="my-1 py-1 px-2 bg-[#131b2e] border-y border-[#1e293b] flex items-center justify-between text-[10px]">
            <span className="text-slate-400 font-bold">
              MID: ${(
                ((liveDepth?.asks[0]?.price || 0) + (liveDepth?.bids[0]?.price || 0)) / 2 ||
                activeSnapshot?.heatmap?.current_mid || 0
              ).toFixed(1)}
            </span>
            <span className="text-amber-400">
              SPREAD: ${(
                (liveDepth?.asks[0]?.price || 0) - (liveDepth?.bids[0]?.price || 0) || 0
              ).toFixed(2)}
            </span>
          </div>

          {/* Bids (Top to Bottom) */}
          <div className="flex-1 overflow-hidden flex flex-col py-1 text-[11px]">
            {liveDepth?.bids?.slice(0, 10).map((bid, idx) => {
              const maxBid = Math.max(...(liveDepth.bids?.map((b) => b.size) || [1]));
              const pct = Math.min(100, (bid.size / maxBid) * 100);
              return (
                <div
                  key={`bid-${idx}`}
                  className="relative flex items-center justify-between px-1 py-0.5 hover:bg-emerald-500/10 transition-colors"
                >
                  <div
                    className="absolute right-0 top-0 bottom-0 bg-emerald-500/15 pointer-events-none"
                    style={{ width: `${pct}%` }}
                  />
                  <span className="text-emerald-400 font-semibold z-10">{bid.price.toFixed(1)}</span>
                  <span className="text-slate-300 z-10">{bid.size.toFixed(3)}</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Bottom Telemetry & Resting Wall Intelligence Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-2.5">
        <div className="p-2.5 bg-[#090d16] border border-[#1e293b] rounded-lg">
          <div className="text-[10px] text-slate-400 flex items-center gap-1">
            <TrendingUp className="w-3 h-3 text-emerald-400" />
            BID RESTING LIQUIDITY
          </div>
          <div className="text-base font-bold text-emerald-400 mt-1">
            ${(totalBidWallUsd / 1000000).toFixed(2)}M
          </div>
          <div className="text-[10px] text-slate-500 mt-0.5">Across active resting walls</div>
        </div>

        <div className="p-2.5 bg-[#090d16] border border-[#1e293b] rounded-lg">
          <div className="text-[10px] text-slate-400 flex items-center gap-1">
            <TrendingUp className="w-3 h-3 text-rose-400 rotate-180" />
            ASK RESTING LIQUIDITY
          </div>
          <div className="text-base font-bold text-rose-400 mt-1">
            ${(totalAskWallUsd / 1000000).toFixed(2)}M
          </div>
          <div className="text-[10px] text-slate-500 mt-0.5">Across active resting walls</div>
        </div>

        <div className="p-2.5 bg-[#090d16] border border-[#1e293b] rounded-lg">
          <div className="text-[10px] text-slate-400 flex items-center gap-1">
            <Activity className="w-3 h-3 text-cyan-400" />
            WALL IMBALANCE RATIO
          </div>
          <div
            className={`text-base font-bold mt-1 ${
              wallImbalanceRatio > 0 ? 'text-emerald-400' : 'text-rose-400'
            }`}
          >
            {wallImbalanceRatio > 0 ? '+' : ''}
            {wallImbalanceRatio.toFixed(1)}%
          </div>
          <div className="text-[10px] text-slate-500 mt-0.5">
            {wallImbalanceRatio > 20
              ? 'Bids dominate (Support)'
              : wallImbalanceRatio < -20
              ? 'Asks dominate (Resistance)'
              : 'Neutral balanced book'}
          </div>
        </div>

        <div className="p-2.5 bg-[#090d16] border border-[#1e293b] rounded-lg">
          <div className="text-[10px] text-slate-400 flex items-center gap-1">
            <Clock className="w-3 h-3 text-amber-400" />
            BUFFER VITALS
          </div>
          <div className="text-base font-bold text-amber-400 mt-1">
            {activeSnapshot?.heatmap?.window_frames || 0} / 600 Frames
          </div>
          <div className="text-[10px] text-slate-500 mt-0.5">
            Ingested: {activeSnapshot?.metrics?.frames_ingested || 0} | Swept: {activeSnapshot?.metrics?.walls_swept || 0}
          </div>
        </div>
      </div>

      {/* Active Resting Walls Table */}
      <div className="p-3 bg-[#090d16] border border-[#1e293b] rounded-lg">
        <div className="flex items-center justify-between pb-2 border-b border-[#1e293b]">
          <span className="font-bold text-slate-200 flex items-center gap-1.5">
            <ShieldAlert className="w-3.5 h-3.5 text-amber-400" />
            DETECTED INSTITUTIONAL RESTING WALLS ({activeSnapshot?.walls?.active_walls?.length || 0})
          </span>
          <span className="text-[10px] text-slate-500">
            Threshold: &ge; 2.5&times; median depth &bull; Persistence &ge; 3 frames
          </span>
        </div>

        {activeSnapshot?.walls?.active_walls && activeSnapshot.walls.active_walls.length > 0 ? (
          <div className="overflow-x-auto mt-2">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="text-slate-400 border-b border-slate-800 text-[10px]">
                  <th className="py-1 px-2">SIDE</th>
                  <th className="py-1 px-2">PRICE</th>
                  <th className="py-1 px-2">SIZE</th>
                  <th className="py-1 px-2">NOTIONAL USD</th>
                  <th className="py-1 px-2">DIST FROM MID</th>
                  <th className="py-1 px-2">AGE</th>
                  <th className="py-1 px-2">PERSISTENCE</th>
                  <th className="py-1 px-2">STATUS</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 text-[11px]">
                {activeSnapshot.walls.active_walls.map((wall) => (
                  <tr key={wall.wall_id} className="hover:bg-slate-800/30 transition-colors">
                    <td className="py-1.5 px-2 font-bold">
                      <span
                        className={`px-1.5 py-0.5 rounded text-[10px] ${
                          wall.side === 'BID'
                            ? 'bg-emerald-500/20 text-emerald-300'
                            : 'bg-rose-500/20 text-rose-300'
                        }`}
                      >
                        {wall.side}
                      </span>
                    </td>
                    <td className="py-1.5 px-2 font-bold text-slate-200">
                      ${wall.price.toFixed(1)}
                    </td>
                    <td className="py-1.5 px-2">{wall.current_size.toFixed(2)}</td>
                    <td className="py-1.5 px-2 text-slate-300">
                      ${(wall.notional_usd / 1000).toFixed(0)}k
                    </td>
                    <td className="py-1.5 px-2 text-slate-400">
                      {wall.distance_from_mid_bps.toFixed(0)} bps
                    </td>
                    <td className="py-1.5 px-2 text-slate-400">{wall.age_seconds.toFixed(0)}s</td>
                    <td className="py-1.5 px-2">
                      <div className="flex items-center gap-1.5">
                        <div className="w-12 h-1.5 bg-slate-800 rounded-full overflow-hidden">
                          <div
                            className={`h-full ${
                              wall.persistence_score > 0.7
                                ? 'bg-emerald-400'
                                : wall.persistence_score > 0.4
                                ? 'bg-amber-400'
                                : 'bg-rose-400'
                            }`}
                            style={{ width: `${wall.persistence_score * 100}%` }}
                          />
                        </div>
                        <span className="text-[10px]">{(wall.persistence_score * 100).toFixed(0)}%</span>
                      </div>
                    </td>
                    <td className="py-1.5 px-2">
                      <span className="text-[10px] px-1.5 py-0.5 bg-slate-800 rounded text-slate-300">
                        {wall.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="py-6 text-center text-slate-500 text-[11px]">
            No large resting walls currently exceeding threshold ({symbol}). Book depth is balanced.
          </div>
        )}
      </div>

      {/* Epistemic Protocol & Quant Disclaimer Banner */}
      <div className="p-2 bg-[#090d16] border border-[#1e293b] rounded text-[10px] text-slate-500 flex items-start gap-2">
        <Info className="w-3.5 h-3.5 text-sky-400 shrink-0 mt-0.5" />
        <div>
          <strong className="text-slate-400">DATA PROVENANCE & EPISTEMIC PROTOCOL:</strong> Order book depth snapshots represent aggregated Level 2 (L2) market-depth prices. All liquidation trigger bands are <span className="text-purple-400">model-derived estimates (EST)</span> based on perpetual derivative leverage assumptions (25x, 50x, 100x MMR), not exchange-confirmed order queues. Spot markets have no native forced liquidation mechanisms.
        </div>
      </div>
    </div>
  );
};
