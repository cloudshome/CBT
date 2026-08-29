import React, { useEffect, useRef, useState, useCallback } from 'react';
import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  IChartApi,
  ISeriesApi,
  CandlestickData,
  HistogramData,
  LineData,
  ColorType,
  CrosshairMode,
  Time,
} from 'lightweight-charts';
import {
  Maximize2,
  Minimize2,
  ArrowRight,
  Sparkles,
} from 'lucide-react';
import { OHLCVCandle, FVGItem, OrderBlockItem, SKYSetupData } from '../../types';
import { DrawingObject, WorkspacePersistence } from '../persistence/workspaceDB';
import { indicatorClient } from '../workers/indicatorClient';

export type DrawingToolType =
  | 'CURSOR'
  | 'TREND_LINE'
  | 'HORIZONTAL_RAY'
  | 'VERTICAL_LINE'
  | 'RECTANGLE'
  | 'FIB_RETRACEMENT'
  | 'LONG_POSITION'
  | 'SHORT_POSITION';

interface TradingViewChartProps {
  symbol: string;
  timeframe: string;
  candles: OHLCVCandle[];
  fvgs?: FVGItem[];
  orderBlocks?: OrderBlockItem[];
  skySetups?: SKYSetupData[];
  liveCandle?: OHLCVCandle | null;
  onDeploySetup?: (setup: any) => void;
  loading?: boolean;
}

export const TradingViewChart: React.FC<TradingViewChartProps> = ({
  symbol,
  timeframe,
  candles,
  fvgs = [],
  orderBlocks = [],
  skySetups = [],
  liveCandle = null,
}) => {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const drawingCanvasRef = useRef<HTMLCanvasElement>(null);

  // Core Chart Instance References
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null);
  const emaSeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
  const vwapSeriesRef = useRef<ISeriesApi<'Line'> | null>(null);

  // Viewport Navigation & Autoscroll Lock State
  const [isHistoricalPan, setIsHistoricalPan] = useState(false);
  const [unreadTicks, setUnreadTicks] = useState(0);
  const [isFullscreen, setIsFullscreen] = useState(false);

  // Active Tool & Drawing State
  const [activeTool, setActiveTool] = useState<DrawingToolType>('CURSOR');
  const [drawings, setDrawings] = useState<DrawingObject[]>([]);
  const [activeDrawingPoints, setActiveDrawingPoints] = useState<Array<{ timestamp: number; price: number }>>([]);

  // Visibility Toggles
  const [showEMA, setShowEMA] = useState(true);
  const [showVWAP, setShowVWAP] = useState(true);
  const [showSMCZones, setShowSMCZones] = useState(true);

  // Crosshair HUD
  const [crosshairData, setCrosshairData] = useState<{
    time: string;
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
    changePct: number;
  } | null>(null);

  // 1. Initialize Lightweight Charts v5 Instance
  useEffect(() => {
    if (!chartContainerRef.current) return;

    const container = chartContainerRef.current;
    container.innerHTML = '';

    const chart = createChart(container, {
      width: container.clientWidth,
      height: container.clientHeight || 480,
      layout: {
        background: { type: ColorType.Solid, color: '#090d16' },
        textColor: '#94a3b8',
        fontSize: 11,
        fontFamily: "'JetBrains Mono', monospace",
      },
      grid: {
        vertLines: { color: 'rgba(30, 41, 59, 0.4)' },
        horzLines: { color: 'rgba(30, 41, 59, 0.4)' },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: {
          color: '#38bdf8',
          width: 1,
          style: 3,
          labelBackgroundColor: '#0f172a',
        },
        horzLine: {
          color: '#38bdf8',
          width: 1,
          style: 3,
          labelBackgroundColor: '#0f172a',
        },
      },
      timeScale: {
        borderColor: 'rgba(51, 65, 85, 0.6)',
        timeVisible: true,
        secondsVisible: false,
        rightOffset: 12,
        barSpacing: 8,
        minBarSpacing: 2,
      },
      rightPriceScale: {
        borderColor: 'rgba(51, 65, 85, 0.6)',
        scaleMargins: {
          top: 0.1,
          bottom: 0.22,
        },
        autoScale: true,
      },
    });

    // Candlestick Series
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#10b981',
      downColor: '#ef4444',
      borderUpColor: '#10b981',
      borderDownColor: '#ef4444',
      wickUpColor: '#10b981',
      wickDownColor: '#ef4444',
    });

    // Volume Histogram Series
    const volumeSeries = chart.addSeries(HistogramSeries, {
      color: 'rgba(56, 189, 248, 0.35)',
      priceFormat: { type: 'volume' },
      priceScaleId: '', // Overlay on bottom
    });
    volumeSeries.priceScale().applyOptions({
      scaleMargins: {
        top: 0.8,
        bottom: 0,
      },
    });

    // EMA 20 Line Series
    const emaSeries = chart.addSeries(LineSeries, {
      color: '#38bdf8',
      lineWidth: 2,
      crosshairMarkerVisible: false,
      lastValueVisible: false,
      priceLineVisible: false,
    });

    // VWAP Line Series
    const vwapSeries = chart.addSeries(LineSeries, {
      color: '#a855f7',
      lineWidth: 2,
      crosshairMarkerVisible: false,
      lastValueVisible: false,
      priceLineVisible: false,
    });

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;
    volumeSeriesRef.current = volumeSeries;
    emaSeriesRef.current = emaSeries;
    vwapSeriesRef.current = vwapSeries;

    // Crosshair move handler for real-time HUD
    chart.subscribeCrosshairMove((param) => {
      if (!param || !param.time || !param.seriesData) {
        setCrosshairData(null);
        return;
      }

      const cData = param.seriesData.get(candleSeries) as CandlestickData;
      if (cData) {
        const o = cData.open;
        const h = cData.high;
        const l = cData.low;
        const c = cData.close;
        const chg = o > 0 ? ((c - o) / o) * 100 : 0;
        const timeStr = new Date((param.time as number) * 1000).toLocaleTimeString([], {
          hour: '2-digit',
          minute: '2-digit',
        });

        setCrosshairData({
          time: timeStr,
          open: o,
          high: h,
          low: l,
          close: c,
          volume: 0,
          changePct: chg,
        });
      }
    });

    // Detect user historical panning vs live autoscroll edge
    chart.timeScale().subscribeVisibleLogicalRangeChange((logicalRange) => {
      if (!logicalRange) return;
      const isPast = logicalRange.to < (candles.length - 3);
      setIsHistoricalPan(isPast);
      if (!isPast) setUnreadTicks(0);
      drawCanvasOverlays();
    });

    // Resize observer
    const handleResize = () => {
      if (container && chart) {
        chart.applyOptions({ width: container.clientWidth, height: container.clientHeight });
        resizeDrawingCanvas();
        drawCanvasOverlays();
      }
    };
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
    };
  }, []);

  // 2. Ingest Historical Candles without Viewport Mutability
  useEffect(() => {
    if (!candleSeriesRef.current || !volumeSeriesRef.current || !candles || candles.length === 0) return;

    // Convert to Lightweight Charts format
    const formattedCandles: CandlestickData[] = [];
    const formattedVolume: HistogramData[] = [];

    const sorted = [...candles].sort((a, b) => a[0] - b[0]);

    sorted.forEach(([ts, o, h, l, c, v]) => {
      const time = Math.floor(ts / 1000) as Time;
      formattedCandles.push({
        time,
        open: o,
        high: h,
        low: l,
        close: c,
      });
      formattedVolume.push({
        time,
        value: v,
        color: c >= o ? 'rgba(16, 185, 129, 0.4)' : 'rgba(239, 68, 68, 0.4)',
      });
    });

    candleSeriesRef.current.setData(formattedCandles);
    volumeSeriesRef.current.setData(formattedVolume);

    // Compute Web Worker Indicators off main thread
    const workerCandles = sorted.map(([ts, o, h, l, c, v]) => ({
      timestamp: ts, open: o, high: h, low: l, close: c, volume: v,
    }));

    indicatorClient.calculateIndicators(workerCandles, {
      emaPeriods: [20],
      vwap: true,
    }).then((res) => {
      if (emaSeriesRef.current && showEMA && res.ema[20]) {
        const lineData: LineData[] = res.ema[20].map((pt) => ({
          time: pt.time as Time,
          value: pt.value,
        }));
        emaSeriesRef.current.setData(lineData);
      }
      if (vwapSeriesRef.current && showVWAP && res.vwap.vwap) {
        const vData: LineData[] = res.vwap.vwap.map((pt) => ({
          time: pt.time as Time,
          value: pt.value,
        }));
        vwapSeriesRef.current.setData(vData);
      }
    });

    // Load drawings from IndexedDB
    WorkspacePersistence.loadDrawings(symbol).then((stored) => {
      setDrawings(stored);
      drawCanvasOverlays();
    });
  }, [candles, symbol, showEMA, showVWAP, skySetups]);

  // 3. Real-time Tick Micro-batching via requestAnimationFrame (Zero React Re-render)
  useEffect(() => {
    if (!liveCandle || !candleSeriesRef.current || !volumeSeriesRef.current) return;

    const [ts, o, h, l, c, v] = liveCandle;
    const time = Math.floor(ts / 1000) as Time;

    window.requestAnimationFrame(() => {
      candleSeriesRef.current?.update({
        time,
        open: o,
        high: h,
        low: l,
        close: c,
      });

      volumeSeriesRef.current?.update({
        time,
        value: v,
        color: c >= o ? 'rgba(16, 185, 129, 0.4)' : 'rgba(239, 68, 68, 0.4)',
      });

      if (isHistoricalPan) {
        setUnreadTicks((prev) => prev + 1);
      }
    });
  }, [liveCandle, isHistoricalPan]);

  // 4. Reset Viewport to Latest Edge
  const handleScrollToLatest = () => {
    if (chartRef.current) {
      chartRef.current.timeScale().scrollToRealTime();
      setIsHistoricalPan(false);
      setUnreadTicks(0);
    }
  };

  // 5. Canvas Drawing Engine Overlay & Coordinate Math
  const resizeDrawingCanvas = () => {
    const canvas = drawingCanvasRef.current;
    const container = chartContainerRef.current;
    if (!canvas || !container) return;
    canvas.width = container.clientWidth;
    canvas.height = container.clientHeight;
  };

  const drawCanvasOverlays = useCallback(() => {
    const canvas = drawingCanvasRef.current;
    const chart = chartRef.current;
    const series = candleSeriesRef.current;
    if (!canvas || !chart || !series) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // 1. Draw SMC Order Blocks & FVGs
    if (showSMCZones) {
      // Order Blocks
      orderBlocks.forEach((ob) => {
        const yTop = series.priceToCoordinate(ob.price_zone[1]);
        const yBot = series.priceToCoordinate(ob.price_zone[0]);
        if (yTop !== null && yBot !== null) {
          const height = Math.abs(yBot - yTop);
          ctx.fillStyle = ob.type === 'bullish' ? 'rgba(56, 189, 248, 0.15)' : 'rgba(168, 85, 247, 0.15)';
          ctx.strokeStyle = ob.type === 'bullish' ? '#38bdf8' : '#a855f7';
          ctx.lineWidth = 1;
          ctx.fillRect(0, Math.min(yTop, yBot), canvas.width, height);
          ctx.strokeRect(0, Math.min(yTop, yBot), canvas.width, height);
        }
      });

      // FVGs
      fvgs.forEach((fvg) => {
        if (fvg.mitigated) return;
        const yTop = series.priceToCoordinate(fvg.price_zone[1]);
        const yBot = series.priceToCoordinate(fvg.price_zone[0]);
        if (yTop !== null && yBot !== null) {
          const height = Math.abs(yBot - yTop);
          ctx.fillStyle = fvg.type === 'bullish' ? 'rgba(16, 185, 129, 0.12)' : 'rgba(239, 68, 68, 0.12)';
          ctx.strokeStyle = fvg.type === 'bullish' ? 'rgba(16, 185, 129, 0.4)' : 'rgba(239, 68, 68, 0.4)';
          ctx.fillRect(0, Math.min(yTop, yBot), canvas.width, height);
          ctx.strokeRect(0, Math.min(yTop, yBot), canvas.width, height);
        }
      });
    }

    // 2. Draw User Mathematical Drawings Anchored to [Timestamp, Price]
    drawings.forEach((drawing) => {
      if (drawing.points.length < 2 && drawing.type !== 'HORIZONTAL_RAY') return;

      const p1 = drawing.points[0];
      const p2 = drawing.points[1] || p1;

      const x1 = chart.timeScale().timeToCoordinate(Math.floor(p1.timestamp / 1000) as Time);
      const y1 = series.priceToCoordinate(p1.price);
      const x2 = chart.timeScale().timeToCoordinate(Math.floor(p2.timestamp / 1000) as Time);
      const y2 = series.priceToCoordinate(p2.price);

      if (x1 === null || y1 === null) return;

      ctx.save();
      ctx.strokeStyle = drawing.color || '#38bdf8';
      ctx.fillStyle = drawing.color || '#38bdf8';
      ctx.lineWidth = drawing.lineWidth || 2;

      if (drawing.type === 'TREND_LINE' && x2 !== null && y2 !== null) {
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.stroke();
      } else if (drawing.type === 'HORIZONTAL_RAY') {
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(canvas.width, y1);
        ctx.stroke();
      } else if (drawing.type === 'RECTANGLE' && x2 !== null && y2 !== null) {
        const w = x2 - x1;
        const h = y2 - y1;
        ctx.fillStyle = 'rgba(56, 189, 248, 0.15)';
        ctx.fillRect(x1, y1, w, h);
        ctx.strokeRect(x1, y1, w, h);
      } else if (drawing.type === 'FIB_RETRACEMENT' && x2 !== null && y2 !== null) {
        const levels = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0];
        const dy = y2 - y1;
        levels.forEach((lvl) => {
          const yLvl = y1 + dy * lvl;
          ctx.beginPath();
          ctx.moveTo(Math.min(x1, x2), yLvl);
          ctx.lineTo(canvas.width, yLvl);
          ctx.stroke();
          ctx.fillText(`Fib ${(lvl * 100).toFixed(1)}%`, Math.min(x1, x2) + 5, yLvl - 3);
        });
      } else if ((drawing.type === 'LONG_POSITION' || drawing.type === 'SHORT_POSITION') && x2 !== null && y2 !== null) {
        // Risk/Reward Position Tool
        const isLong = drawing.type === 'LONG_POSITION';
        const entryY = y1;
        const slY = y2;
        const riskH = Math.abs(slY - entryY);
        const tpY = isLong ? entryY - (2.5 * riskH) : entryY + (2.5 * riskH);

        // Stop Loss Box
        ctx.fillStyle = 'rgba(239, 68, 68, 0.2)';
        ctx.fillRect(x1, Math.min(entryY, slY), Math.abs(x2 - x1) || 120, Math.abs(slY - entryY));

        // Target Box
        ctx.fillStyle = 'rgba(16, 185, 129, 0.2)';
        ctx.fillRect(x1, Math.min(entryY, tpY), Math.abs(x2 - x1) || 120, Math.abs(tpY - entryY));
      }

      ctx.restore();
    });

    // 3. Draw SKY Quantitative Signal Markers
    if (skySetups && skySetups.length > 0) {
      skySetups.forEach((setup) => {
        const isBull = setup.direction === 'LONG';
        const x = chart.timeScale().timeToCoordinate(Math.floor(setup.timestamp / 1000) as Time);
        const y = series.priceToCoordinate(setup.entry_price);
        if (x === null || y === null) return;

        ctx.save();
        ctx.fillStyle = isBull ? '#10b981' : '#ef4444';
        ctx.strokeStyle = isBull ? '#10b981' : '#ef4444';
        ctx.lineWidth = 2;

        // Draw Arrow
        const arrowY = isBull ? y + 25 : y - 25;
        ctx.beginPath();
        ctx.moveTo(x, arrowY);
        ctx.lineTo(x, y + (isBull ? 8 : -8));
        ctx.stroke();

        // Arrowhead
        ctx.beginPath();
        if (isBull) {
          ctx.moveTo(x, y + 6);
          ctx.lineTo(x - 5, y + 14);
          ctx.lineTo(x + 5, y + 14);
        } else {
          ctx.moveTo(x, y - 6);
          ctx.lineTo(x - 5, y - 14);
          ctx.lineTo(x + 5, y - 14);
        }
        ctx.closePath();
        ctx.fill();

        // Signal Label Box
        const label = `${setup.setup_type.replace(/SETUP_/g, '')} ${setup.risk_reward_ratio}R`;
        ctx.font = 'bold 10px monospace';
        const textW = ctx.measureText(label).width;
        ctx.fillStyle = 'rgba(15, 23, 42, 0.85)';
        ctx.fillRect(x - textW / 2 - 4, arrowY + (isBull ? 4 : -16), textW + 8, 14);
        ctx.strokeRect(x - textW / 2 - 4, arrowY + (isBull ? 4 : -16), textW + 8, 14);

        ctx.fillStyle = isBull ? '#10b981' : '#ef4444';
        ctx.fillText(label, x - textW / 2, arrowY + (isBull ? 15 : -5));
        ctx.restore();
      });
    }
  }, [drawings, orderBlocks, fvgs, showSMCZones, skySetups]);

  // 6. Interactive Canvas Click Handler for Drawing Creation
  const handleCanvasClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (activeTool === 'CURSOR') return;

    const canvas = drawingCanvasRef.current;
    const chart = chartRef.current;
    const series = candleSeriesRef.current;
    if (!canvas || !chart || !series) return;

    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    const timeCoord = chart.timeScale().coordinateToTime(x);
    const priceCoord = series.coordinateToPrice(y);

    if (!timeCoord || !priceCoord) return;

    const timestamp = (timeCoord as number) * 1000;
    const point = { timestamp, price: priceCoord };

    if (activeTool === 'HORIZONTAL_RAY' || activeTool === 'VERTICAL_LINE') {
      const newDrawing: DrawingObject = {
        id: Math.random().toString(36).substring(2, 9),
        type: activeTool,
        symbol,
        timeframe,
        points: [point],
        createdAt: Date.now(),
      };
      setDrawings((prev) => [...prev, newDrawing]);
      WorkspacePersistence.saveDrawing(newDrawing);
      setActiveTool('CURSOR');
    } else {
      if (activeDrawingPoints.length === 0) {
        setActiveDrawingPoints([point]);
      } else {
        const newDrawing: DrawingObject = {
          id: Math.random().toString(36).substring(2, 9),
          type: activeTool,
          symbol,
          timeframe,
          points: [activeDrawingPoints[0], point],
          createdAt: Date.now(),
        };
        setDrawings((prev) => [...prev, newDrawing]);
        WorkspacePersistence.saveDrawing(newDrawing);
        setActiveDrawingPoints([]);
        setActiveTool('CURSOR');
      }
    }
  };

  return (
    <div
      className={`bg-[#090d16] border border-border rounded-lg shadow-xl flex flex-col relative overflow-hidden ${
        isFullscreen ? 'fixed inset-0 z-50 rounded-none' : 'h-full'
      }`}
    >
      {/* Top TradingView Control Bar */}
      <div className="h-10 border-b border-border/80 px-3 bg-[#0d1322] flex items-center justify-between z-10 select-none">
        {/* Left: Active Tool, Symbol, OHLC HUD */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 text-xs font-mono font-bold text-slate-200">
            <span className="text-terminal-cyan">{symbol}</span>
            <span className="px-1 py-0.5 rounded bg-slate-800 text-slate-400 text-[10px]">{timeframe}</span>
          </div>

          {/* Real-time OHLC Crosshair Readout */}
          {crosshairData ? (
            <div className="hidden lg:flex items-center gap-3 text-[11px] font-mono text-slate-400">
              <span>O: <strong className="text-slate-200">${crosshairData.open.toFixed(2)}</strong></span>
              <span>H: <strong className="text-slate-200">${crosshairData.high.toFixed(2)}</strong></span>
              <span>L: <strong className="text-slate-200">${crosshairData.low.toFixed(2)}</strong></span>
              <span>C: <strong className="text-slate-200">${crosshairData.close.toFixed(2)}</strong></span>
              <span className={crosshairData.changePct >= 0 ? 'text-terminal-green' : 'text-terminal-red'}>
                {crosshairData.changePct >= 0 ? '+' : ''}{crosshairData.changePct.toFixed(2)}%
              </span>
            </div>
          ) : (
            <div className="hidden lg:flex items-center gap-2 text-[10px] font-mono text-slate-500">
              <Sparkles className="w-3 h-3 text-terminal-cyan animate-pulse" />
              <span>TRADINGVIEW 60 FPS ENGINE ONLINE</span>
            </div>
          )}
        </div>

        {/* Right: Indicators, SMC Layer, Tool Selectors, Fullscreen */}
        <div className="flex items-center gap-1.5">
          {/* Drawing Tools Dropdown / Quick Buttons */}
          <div className="flex items-center bg-slate-900 rounded p-0.5 border border-border">
            <button
              onClick={() => setActiveTool(activeTool === 'TREND_LINE' ? 'CURSOR' : 'TREND_LINE')}
              className={`px-2 py-0.5 text-[10px] font-mono rounded ${activeTool === 'TREND_LINE' ? 'bg-terminal-cyan text-slate-950 font-bold' : 'text-slate-400 hover:text-slate-200'}`}
              title="Trend Line"
            >
              Trend
            </button>
            <button
              onClick={() => setActiveTool(activeTool === 'FIB_RETRACEMENT' ? 'CURSOR' : 'FIB_RETRACEMENT')}
              className={`px-2 py-0.5 text-[10px] font-mono rounded ${activeTool === 'FIB_RETRACEMENT' ? 'bg-terminal-cyan text-slate-950 font-bold' : 'text-slate-400 hover:text-slate-200'}`}
              title="Fibonacci Retracement"
            >
              Fib
            </button>
            <button
              onClick={() => setActiveTool(activeTool === 'LONG_POSITION' ? 'CURSOR' : 'LONG_POSITION')}
              className={`px-2 py-0.5 text-[10px] font-mono rounded ${activeTool === 'LONG_POSITION' ? 'bg-terminal-green text-slate-950 font-bold' : 'text-slate-400 hover:text-slate-200'}`}
              title="Long Position Tool"
            >
              Long Tool
            </button>
          </div>

          {/* Indicator Toggles */}
          <button
            onClick={() => setShowEMA(!showEMA)}
            className={`px-2 py-0.5 text-[10px] font-mono rounded border transition ${showEMA ? 'bg-terminal-cyan/15 text-terminal-cyan border-terminal-cyan/40' : 'bg-slate-900 text-slate-500 border-border'}`}
          >
            EMA(20)
          </button>
          <button
            onClick={() => setShowVWAP(!showVWAP)}
            className={`px-2 py-0.5 text-[10px] font-mono rounded border transition ${showVWAP ? 'bg-terminal-purple/15 text-terminal-purple border-terminal-purple/40' : 'bg-slate-900 text-slate-500 border-border'}`}
          >
            VWAP
          </button>
          <button
            onClick={() => setShowSMCZones(!showSMCZones)}
            className={`px-2 py-0.5 text-[10px] font-mono rounded border transition ${showSMCZones ? 'bg-amber-500/15 text-amber-400 border-amber-500/40' : 'bg-slate-900 text-slate-500 border-border'}`}
          >
            SMC Zones
          </button>

          {/* Fullscreen Toggle */}
          <button
            onClick={() => setIsFullscreen(!isFullscreen)}
            className="p-1 rounded bg-slate-900 hover:bg-slate-800 text-slate-400 border border-border ml-1"
          >
            {isFullscreen ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
          </button>
        </div>
      </div>

      {/* Main Chart Body Container */}
      <div className="flex-1 relative w-full h-full min-h-[440px]">
        {/* Lightweight Charts Core Canvas */}
        <div ref={chartContainerRef} className="absolute inset-0 w-full h-full" />

        {/* Double-Buffered Mathematical Overlay Canvas */}
        <canvas
          ref={drawingCanvasRef}
          onClick={handleCanvasClick}
          className={`absolute inset-0 w-full h-full ${activeTool !== 'CURSOR' ? 'cursor-crosshair z-20' : 'pointer-events-none z-10'}`}
        />

        {/* Floating "Go to Latest" Button with Unread Tick Counter */}
        {isHistoricalPan && (
          <button
            onClick={handleScrollToLatest}
            className="absolute bottom-6 right-16 z-30 px-3 py-1.5 rounded-full bg-terminal-cyan text-slate-950 font-mono font-bold text-xs shadow-2xl hover:scale-105 transition flex items-center gap-1.5"
          >
            <span>Go to Latest</span>
            {unreadTicks > 0 && (
              <span className="px-1.5 py-0.2 bg-slate-950 text-terminal-cyan rounded-full text-[10px]">
                +{unreadTicks}
              </span>
            )}
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        )}
      </div>
    </div>
  );
};
