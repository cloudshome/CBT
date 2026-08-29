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
  MousePointer,
  TrendingUp,
  Minus,
  SeparatorVertical,
  Square,
  Hash,
  ArrowUpCircle,
  ArrowDownCircle,
  Trash2,
  LucideIcon,
} from 'lucide-react';
import { OHLCVCandle, FVGItem, OrderBlockItem, SKYSetupData, SupportedTimeframe } from '../../types';
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
  timeframe: SupportedTimeframe;
  candles: OHLCVCandle[];
  fvgs?: FVGItem[];
  orderBlocks?: OrderBlockItem[];
  skySetups?: SKYSetupData[];
  liveCandle?: OHLCVCandle | null;
  onDeploySetup?: (setup: any) => void;
  onTimeframeChange?: (tf: SupportedTimeframe) => void;
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
  onDeploySetup,
  onTimeframeChange,
}) => {
  const chartWrapperRef = useRef<HTMLDivElement>(null);
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const drawingCanvasRef = useRef<HTMLCanvasElement>(null);

  // Core Chart Instance References
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null);
  const emaSeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
  const vwapSeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
  const upper1sRef = useRef<ISeriesApi<'Line'> | null>(null);
  const lower1sRef = useRef<ISeriesApi<'Line'> | null>(null);
  const upper2sRef = useRef<ISeriesApi<'Line'> | null>(null);
  const lower2sRef = useRef<ISeriesApi<'Line'> | null>(null);

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
  const [showMultiSigma, setShowMultiSigma] = useState(true);
  const [showSMCZones, setShowSMCZones] = useState(true);
  const [showJudasZones, setShowJudasZones] = useState(true);

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

  const timeframes: SupportedTimeframe[] = ['1m', '3m', '5m', '15m', '1h', '4h', '1d'];

  // Handle True Browser Fullscreen Toggle
  const toggleFullscreen = useCallback(async () => {
    const el = chartWrapperRef.current;
    if (!el) return;

    try {
      if (!document.fullscreenElement) {
        await el.requestFullscreen();
        setIsFullscreen(true);
      } else {
        await document.exitFullscreen();
        setIsFullscreen(false);
      }
    } catch {
      setIsFullscreen((prev) => !prev);
    }
  }, []);

  // Listen for fullscreen change event
  useEffect(() => {
    const handleFullscreenChange = () => {
      const isFull = !!document.fullscreenElement;
      setIsFullscreen(isFull);
      setTimeout(() => {
        if (chartContainerRef.current && chartRef.current) {
          const w = chartContainerRef.current.clientWidth;
          const h = chartContainerRef.current.clientHeight || (isFull ? window.innerHeight - 80 : 440);
          chartRef.current.resize(w, h);
          updateCanvasDimensions();
          drawCanvasOverlays();
        }
      }, 50);
    };

    document.addEventListener('fullscreenchange', handleFullscreenChange);
    return () => document.removeEventListener('fullscreenchange', handleFullscreenChange);
  }, []);

  // 1. Initialize Lightweight Charts v5 Instance
  useEffect(() => {
    if (!chartContainerRef.current) return;

    const container = chartContainerRef.current;
    container.innerHTML = '';

    const initialHeight = isFullscreen ? window.innerHeight - 80 : 440;
    const initialWidth = container.clientWidth || 800;

    const chart = createChart(container, {
      width: initialWidth,
      height: initialHeight,
      layout: {
        background: { type: ColorType.Solid, color: '#080b11' },
        textColor: '#94a3b8',
        fontSize: 11,
        fontFamily: "'JetBrains Mono', monospace",
      },
      grid: {
        vertLines: { color: 'rgba(255, 255, 255, 0.03)' },
        horzLines: { color: 'rgba(255, 255, 255, 0.03)' },
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
        borderColor: 'rgba(51, 65, 85, 0.5)',
        timeVisible: true,
        secondsVisible: false,
        rightOffset: 12,
        barSpacing: 9,
        minBarSpacing: 2,
      },
      rightPriceScale: {
        borderColor: 'rgba(51, 65, 85, 0.5)',
        scaleMargins: {
          top: 0.08,
          bottom: 0.2,
        },
        autoScale: true,
      },
    });

    // Neon Candlestick Series
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#00f0a8',
      downColor: '#ff3b69',
      borderUpColor: '#00f0a8',
      borderDownColor: '#ff3b69',
      wickUpColor: '#00f0a8',
      wickDownColor: '#ff3b69',
    });

    // Volume Histogram Series
    const volumeSeries = chart.addSeries(HistogramSeries, {
      color: 'rgba(56, 189, 248, 0.3)',
      priceFormat: { type: 'volume' },
      priceScaleId: '',
    });
    volumeSeries.priceScale().applyOptions({
      scaleMargins: {
        top: 0.82,
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
      color: '#c084fc',
      lineWidth: 2,
      crosshairMarkerVisible: false,
      lastValueVisible: false,
      priceLineVisible: false,
    });

    // Multi-Sigma VWAP Bands
    const upper1s = chart.addSeries(LineSeries, {
      color: 'rgba(129, 140, 248, 0.65)',
      lineWidth: 1,
      lineStyle: 2,
      crosshairMarkerVisible: false,
      lastValueVisible: false,
      priceLineVisible: false,
    });
    const lower1s = chart.addSeries(LineSeries, {
      color: 'rgba(129, 140, 248, 0.65)',
      lineWidth: 1,
      lineStyle: 2,
      crosshairMarkerVisible: false,
      lastValueVisible: false,
      priceLineVisible: false,
    });
    const upper2s = chart.addSeries(LineSeries, {
      color: 'rgba(244, 63, 94, 0.65)',
      lineWidth: 1,
      lineStyle: 2,
      crosshairMarkerVisible: false,
      lastValueVisible: false,
      priceLineVisible: false,
    });
    const lower2s = chart.addSeries(LineSeries, {
      color: 'rgba(244, 63, 94, 0.65)',
      lineWidth: 1,
      lineStyle: 2,
      crosshairMarkerVisible: false,
      lastValueVisible: false,
      priceLineVisible: false,
    });

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;
    volumeSeriesRef.current = volumeSeries;
    emaSeriesRef.current = emaSeries;
    vwapSeriesRef.current = vwapSeries;
    upper1sRef.current = upper1s;
    lower1sRef.current = lower1s;
    upper2sRef.current = upper2s;
    lower2sRef.current = lower2s;

    // Load initial candles if available
    if (candles && candles.length > 0) {
      const formattedCandles: CandlestickData[] = [];
      const formattedVolume: HistogramData[] = [];
      let prevTime = -1;

      const sorted = [...candles]
        .filter((c) => Array.isArray(c) && c.length >= 5 && !isNaN(c[0]) && !isNaN(c[4]) && c[4] > 0)
        .sort((a, b) => a[0] - b[0]);

      for (const c of sorted) {
        const t = Math.floor(c[0] / 1000);
        if (t > prevTime) {
          formattedCandles.push({
            time: t as Time,
            open: c[1],
            high: c[2],
            low: c[3],
            close: c[4],
          });
          formattedVolume.push({
            time: t as Time,
            value: c[5] || 0,
            color: c[4] >= c[1] ? 'rgba(0, 240, 168, 0.4)' : 'rgba(255, 59, 105, 0.4)',
          });
          prevTime = t;
        }
      }

      if (formattedCandles.length > 0) {
        candleSeries.setData(formattedCandles);
        volumeSeries.setData(formattedVolume);
        chart.timeScale().fitContent();
      }
    }

    // Crosshair move handler
    chart.subscribeCrosshairMove((param) => {
      if (!param || !param.time || !param.seriesData) {
        setCrosshairData(null);
        return;
      }

      const cData = param.seriesData.get(candleSeries) as CandlestickData;
      const vData = param.seriesData.get(volumeSeries) as HistogramData;

      if (cData) {
        const o = cData.open;
        const c = cData.close;
        const h = cData.high;
        const l = cData.low;
        const change = ((c - o) / o) * 100;
        const timeStr = typeof param.time === 'number'
          ? new Date(param.time * 1000).toLocaleString()
          : String(param.time);

        setCrosshairData({
          time: timeStr,
          open: o,
          high: h,
          low: l,
          close: c,
          volume: vData?.value || 0,
          changePct: change,
        });
      }
    });

    // Detect user historical pan to lock edge following
    chart.timeScale().subscribeVisibleLogicalRangeChange((range) => {
      if (!range) return;
      const barsInfo = candleSeries.barsInLogicalRange(range);
      if (barsInfo && barsInfo.barsAfter !== undefined) {
        if (barsInfo.barsAfter > 2) {
          setIsHistoricalPan(true);
        } else {
          setIsHistoricalPan(false);
          setUnreadTicks(0);
        }
      }
    });

    // Resize observer
    const handleResize = () => {
      if (chartContainerRef.current && chartRef.current) {
        const w = chartContainerRef.current.clientWidth;
        const h = chartContainerRef.current.clientHeight || (isFullscreen ? window.innerHeight - 80 : 440);
        chartRef.current.resize(w, h);
        updateCanvasDimensions();
        drawCanvasOverlays();
      }
    };

    window.addEventListener('resize', handleResize);
    const resizeObserver = new ResizeObserver(handleResize);
    resizeObserver.observe(container);

    // Initial resize trigger
    setTimeout(handleResize, 100);

    return () => {
      window.removeEventListener('resize', handleResize);
      resizeObserver.disconnect();
      chart.remove();
      chartRef.current = null;
    };
  }, [isFullscreen]);

  // 2. Load Persisted Drawings from IndexedDB
  useEffect(() => {
    let isMounted = true;
    WorkspacePersistence.loadDrawings(symbol).then((stored: DrawingObject[]) => {
      if (isMounted) setDrawings(stored);
    });
    return () => { isMounted = false; };
  }, [symbol]);

  // 3. Ingest Candlestick Data & Offload Indicators to Web Worker
  useEffect(() => {
    if (!candleSeriesRef.current || !candles || candles.length === 0) return;

    const formattedCandles: CandlestickData[] = [];
    const formattedVolume: HistogramData[] = [];
    let prevTime = -1;

    const sorted = [...candles]
      .filter((c) => Array.isArray(c) && c.length >= 5 && !isNaN(c[0]) && !isNaN(c[4]) && c[4] > 0)
      .sort((a, b) => a[0] - b[0]);

    for (const c of sorted) {
      const t = Math.floor(c[0] / 1000);
      if (t > prevTime) {
        formattedCandles.push({
          time: t as Time,
          open: c[1],
          high: c[2],
          low: c[3],
          close: c[4],
        });
        formattedVolume.push({
          time: t as Time,
          value: c[5] || 0,
          color: c[4] >= c[1] ? 'rgba(0, 240, 168, 0.4)' : 'rgba(255, 59, 105, 0.4)',
        });
        prevTime = t;
      }
    }

    if (formattedCandles.length > 0) {
      candleSeriesRef.current.setData(formattedCandles);
      volumeSeriesRef.current?.setData(formattedVolume);
    }

    const workerCandles = candles.map((c) => ({
      timestamp: c[0],
      open: c[1],
      high: c[2],
      low: c[3],
      close: c[4],
      volume: c[5],
    }));

    // Offload indicators to Web Worker
    indicatorClient.calculateIndicators(workerCandles, {
      emaPeriods: [20],
      vwap: true,
    }).then((res) => {
      if (emaSeriesRef.current && showEMA && res.ema && res.ema[20]) {
        const emaData: LineData[] = res.ema[20].map((p: { time: number; value: number }) => ({
          time: p.time as Time,
          value: p.value,
        }));
        emaSeriesRef.current.setData(emaData);
      }

      if (vwapSeriesRef.current && showVWAP && res.vwap) {
        const vwapData: LineData[] = res.vwap.vwap.map((p: { time: number; value: number }) => ({
          time: p.time as Time,
          value: p.value,
        }));
        vwapSeriesRef.current.setData(vwapData);

        if (showMultiSigma) {
          const u1Data: LineData[] = res.vwap.upper1s.map((p: { time: number; value: number }) => ({
            time: p.time as Time,
            value: p.value,
          }));
          const l1Data: LineData[] = res.vwap.lower1s.map((p: { time: number; value: number }) => ({
            time: p.time as Time,
            value: p.value,
          }));
          const u2Data: LineData[] = res.vwap.upper2s.map((p: { time: number; value: number }) => ({
            time: p.time as Time,
            value: p.value,
          }));
          const l2Data: LineData[] = res.vwap.lower2s.map((p: { time: number; value: number }) => ({
            time: p.time as Time,
            value: p.value,
          }));

          upper1sRef.current?.setData(u1Data);
          lower1sRef.current?.setData(l1Data);
          upper2sRef.current?.setData(u2Data);
          lower2sRef.current?.setData(l2Data);
        }
      }
    });

    if (!isHistoricalPan) {
      chartRef.current?.timeScale().scrollToRealTime();
    }
  }, [candles, showEMA, showVWAP, showMultiSigma, isHistoricalPan]);

  // 4. Live Tick Micro-Batching with RAF
  useEffect(() => {
    if (!liveCandle || !candleSeriesRef.current) return;

    const bar: CandlestickData = {
      time: Math.floor(liveCandle[0] / 1000) as Time,
      open: liveCandle[1],
      high: liveCandle[2],
      low: liveCandle[3],
      close: liveCandle[4],
    };

    window.requestAnimationFrame(() => {
      candleSeriesRef.current?.update(bar);
      volumeSeriesRef.current?.update({
        time: Math.floor(liveCandle[0] / 1000) as Time,
        value: liveCandle[5],
        color: liveCandle[4] >= liveCandle[1] ? 'rgba(0, 240, 168, 0.4)' : 'rgba(255, 59, 105, 0.4)',
      });

      if (isHistoricalPan) {
        setUnreadTicks((prev) => prev + 1);
      }
    });
  }, [liveCandle, isHistoricalPan]);

  // 5. Canvas Mathematical Drawing & Overlay Engine
  const updateCanvasDimensions = () => {
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

    // 1. Draw Judas Swing Session Killzones
    if (showJudasZones && candles.length > 0) {
      const sessionRanges: Array<{ name: string; startH: number; endH: number; color: string; fill: string }> = [
        { name: 'LONDON KILLZONE (07:00-09:00 UTC)', startH: 7, endH: 9, color: '#38bdf8', fill: 'rgba(56, 189, 248, 0.05)' },
        { name: 'NY KILLZONE (13:00-15:00 UTC)', startH: 13, endH: 15, color: '#f59e0b', fill: 'rgba(245, 158, 11, 0.05)' },
      ];

      candles.forEach((c) => {
        const dt = new Date(c[0]);
        const utcHour = dt.getUTCHours();
        const utcMin = dt.getUTCMinutes();
        const timeDec = utcHour + utcMin / 60;

        sessionRanges.forEach((s) => {
          if (timeDec >= s.startH && timeDec < s.endH) {
            const x = chart.timeScale().timeToCoordinate(Math.floor(c[0] / 1000) as Time);
            if (x !== null && x > 0 && x < canvas.width) {
              ctx.fillStyle = s.fill;
              ctx.fillRect(x - 5, 0, 10, canvas.height);
            }
          }
        });
      });
    }

    // 2. Draw SMC Order Blocks & FVGs
    if (showSMCZones) {
      orderBlocks.forEach((ob) => {
        const yTop = series.priceToCoordinate(ob.price_zone[1]);
        const yBot = series.priceToCoordinate(ob.price_zone[0]);
        if (yTop !== null && yBot !== null) {
          const height = Math.abs(yBot - yTop);
          ctx.fillStyle = ob.type === 'bullish' ? 'rgba(0, 240, 168, 0.12)' : 'rgba(255, 59, 105, 0.12)';
          ctx.strokeStyle = ob.type === 'bullish' ? '#00f0a8' : '#ff3b69';
          ctx.lineWidth = 1;
          ctx.fillRect(0, Math.min(yTop, yBot), canvas.width, height);
          ctx.strokeRect(0, Math.min(yTop, yBot), canvas.width, height);
        }
      });

      fvgs.forEach((fvg) => {
        if (fvg.mitigated) return;
        const yTop = series.priceToCoordinate(fvg.price_zone[1]);
        const yBot = series.priceToCoordinate(fvg.price_zone[0]);
        if (yTop !== null && yBot !== null) {
          const height = Math.abs(yBot - yTop);
          ctx.fillStyle = fvg.type === 'bullish' ? 'rgba(0, 240, 168, 0.08)' : 'rgba(255, 59, 105, 0.08)';
          ctx.strokeStyle = fvg.type === 'bullish' ? 'rgba(0, 240, 168, 0.4)' : 'rgba(255, 59, 105, 0.4)';
          ctx.fillRect(0, Math.min(yTop, yBot), canvas.width, height);
          ctx.strokeRect(0, Math.min(yTop, yBot), canvas.width, height);
        }
      });
    }

    // 3. Draw User Drawings
    drawings.forEach((drawing) => {
      if (drawing.points.length < 2 && drawing.type !== 'HORIZONTAL_RAY' && drawing.type !== 'VERTICAL_LINE') return;

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
        ctx.font = 'bold 10px monospace';
        ctx.fillText(`$${p1.price.toFixed(2)}`, canvas.width - 70, y1 - 4);
      } else if (drawing.type === 'VERTICAL_LINE') {
        ctx.beginPath();
        ctx.moveTo(x1, 0);
        ctx.lineTo(x1, canvas.height);
        ctx.stroke();
        ctx.font = 'bold 10px monospace';
        ctx.fillText(new Date(p1.timestamp).toLocaleTimeString(), x1 + 4, 20);
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
          const priceLvl = p1.price + (p2.price - p1.price) * lvl;
          ctx.beginPath();
          ctx.moveTo(Math.min(x1, x2), yLvl);
          ctx.lineTo(canvas.width, yLvl);
          ctx.stroke();
          ctx.fillText(`Fib ${(lvl * 100).toFixed(1)}% ($${priceLvl.toFixed(2)})`, Math.min(x1, x2) + 5, yLvl - 3);
        });
      } else if ((drawing.type === 'LONG_POSITION' || drawing.type === 'SHORT_POSITION') && x2 !== null && y2 !== null) {
        const isLong = drawing.type === 'LONG_POSITION';
        const entryY = y1;
        const slY = y2;
        const riskH = Math.abs(slY - entryY);
        const tpY = isLong ? entryY - (2.5 * riskH) : entryY + (2.5 * riskH);
        const width = Math.max(Math.abs(x2 - x1), 140);

        // SL Zone (Red)
        ctx.fillStyle = 'rgba(255, 59, 105, 0.25)';
        ctx.strokeStyle = '#ff3b69';
        ctx.fillRect(x1, Math.min(entryY, slY), width, Math.abs(slY - entryY));
        ctx.strokeRect(x1, Math.min(entryY, slY), width, Math.abs(slY - entryY));

        // TP Zone (Green)
        ctx.fillStyle = 'rgba(0, 240, 168, 0.25)';
        ctx.strokeStyle = '#00f0a8';
        ctx.fillRect(x1, Math.min(entryY, tpY), width, Math.abs(tpY - entryY));
        ctx.strokeRect(x1, Math.min(entryY, tpY), width, Math.abs(tpY - entryY));

        // R:R Badge
        ctx.fillStyle = '#0f172a';
        ctx.fillRect(x1 + 6, entryY - 10, 80, 20);
        ctx.strokeRect(x1 + 6, entryY - 10, 80, 20);
        ctx.fillStyle = isLong ? '#00f0a8' : '#ff3b69';
        ctx.font = 'bold 11px monospace';
        ctx.fillText(`R:R 2.50`, x1 + 14, entryY + 4);
      }

      ctx.restore();
    });

    // 4. Draw SKY Signal Markers
    if (skySetups && skySetups.length > 0) {
      skySetups.forEach((setup) => {
        const isBull = setup.direction === 'LONG';
        const x = chart.timeScale().timeToCoordinate(Math.floor(setup.timestamp / 1000) as Time);
        const y = series.priceToCoordinate(setup.entry_price);
        if (x === null || y === null) return;

        ctx.save();
        ctx.fillStyle = isBull ? '#00f0a8' : '#ff3b69';
        ctx.strokeStyle = isBull ? '#00f0a8' : '#ff3b69';
        ctx.lineWidth = 2;

        const arrowY = isBull ? y + 25 : y - 25;
        ctx.beginPath();
        ctx.moveTo(x, arrowY);
        ctx.lineTo(x, y + (isBull ? 8 : -8));
        ctx.stroke();

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

        const label = `${setup.setup_type.replace(/SETUP_/g, '')} ${setup.risk_reward_ratio}R`;
        ctx.font = 'bold 10px monospace';
        const textWidth = ctx.measureText(label).width;
        const boxX = x - textWidth / 2 - 4;
        const boxY = isBull ? arrowY + 4 : arrowY - 16;

        ctx.fillStyle = '#0f172a';
        ctx.fillRect(boxX, boxY, textWidth + 8, 14);
        ctx.strokeRect(boxX, boxY, textWidth + 8, 14);

        ctx.fillStyle = isBull ? '#00f0a8' : '#ff3b69';
        ctx.fillText(label, boxX + 4, boxY + 11);

        ctx.restore();
      });
    }
  }, [candles, showSMCZones, showJudasZones, drawings, skySetups]);

  useEffect(() => {
    updateCanvasDimensions();
    drawCanvasOverlays();
  }, [drawings, drawCanvasOverlays]);

  const handleCanvasMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (activeTool === 'CURSOR' || !chartRef.current || !candleSeriesRef.current) return;

    const rect = drawingCanvasRef.current?.getBoundingClientRect();
    if (!rect) return;

    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    const timeCoord = chartRef.current.timeScale().coordinateToTime(x);
    const priceCoord = candleSeriesRef.current.coordinateToPrice(y);

    if (timeCoord === null || priceCoord === null) return;

    const ts = typeof timeCoord === 'number' ? timeCoord * 1000 : Date.now();
    const newPoints = [...activeDrawingPoints, { timestamp: ts, price: priceCoord }];

    if (activeTool === 'HORIZONTAL_RAY' || activeTool === 'VERTICAL_LINE' || newPoints.length >= 2) {
      const newDrawing: DrawingObject = {
        id: `draw_${Date.now()}`,
        symbol,
        timeframe,
        type: activeTool,
        points: newPoints,
        color: activeTool === 'LONG_POSITION' ? '#00f0a8' : activeTool === 'SHORT_POSITION' ? '#ff3b69' : '#38bdf8',
        lineWidth: 2,
        createdAt: Date.now(),
      };

      const updated = [...drawings, newDrawing];
      setDrawings(updated);
      WorkspacePersistence.saveDrawing(newDrawing);

      // Auto-deploy position tools into order desk if handler provided
      if ((activeTool === 'LONG_POSITION' || activeTool === 'SHORT_POSITION') && onDeploySetup && newPoints.length >= 2) {
        const entry = newPoints[0].price;
        const sl = newPoints[1].price;
        const isLong = activeTool === 'LONG_POSITION';
        const risk = Math.abs(entry - sl);
        const tp = isLong ? entry + 2.5 * risk : entry - 2.5 * risk;
        onDeploySetup({
          type: isLong ? 'LONG' : 'SHORT',
          entry,
          stopLoss: sl,
          takeProfit: tp,
          confidence: 85,
        });
      }

      setActiveDrawingPoints([]);
      setActiveTool('CURSOR');
    } else {
      setActiveDrawingPoints(newPoints);
    }
  };

  const handleClearDrawings = () => {
    drawings.forEach((d) => WorkspacePersistence.deleteDrawing(d.id));
    setDrawings([]);
    setActiveDrawingPoints([]);
    setActiveTool('CURSOR');
  };

  // Drawing Tools Configuration for Vertical Toolbar
  const drawingTools: Array<{ id: DrawingToolType; label: string; icon: LucideIcon }> = [
    { id: 'CURSOR', label: 'Pointer / Crosshair', icon: MousePointer },
    { id: 'TREND_LINE', label: 'Trend Line', icon: TrendingUp },
    { id: 'HORIZONTAL_RAY', label: 'Horizontal Ray / Level', icon: Minus },
    { id: 'VERTICAL_LINE', label: 'Vertical Line / Time', icon: SeparatorVertical },
    { id: 'RECTANGLE', label: 'Order Block Box', icon: Square },
    { id: 'FIB_RETRACEMENT', label: 'Fibonacci Retracement', icon: Hash },
    { id: 'LONG_POSITION', label: 'Long Position R:R Tool', icon: ArrowUpCircle },
    { id: 'SHORT_POSITION', label: 'Short Position R:R Tool', icon: ArrowDownCircle },
  ];

  return (
    <div
      ref={chartWrapperRef}
      className={`relative flex flex-col bg-[#080b11] border border-[#1e293b] rounded-t-lg overflow-hidden select-none transition-all duration-300 ${
        isFullscreen ? 'fixed inset-0 z-50 rounded-none w-screen h-screen' : 'w-full'
      }`}
    >
      {/* Top Header & Chart Toolbar */}
      <div className="flex flex-wrap items-center justify-between px-3 py-2 bg-[#0d121d] border-b border-[#1e293b] text-xs z-10 gap-2">
        {/* Left: Symbol, Price, Timeframes */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5">
            <span className="font-bold text-slate-100 text-sm">{symbol}</span>
            <span className="px-1.5 py-0.5 text-[10px] font-semibold bg-sky-500/10 text-sky-400 border border-sky-500/20 rounded">
              PERP
            </span>
          </div>

          {/* Timeframe Selector Buttons */}
          <div className="flex items-center bg-[#080b11] border border-slate-800 rounded p-0.5">
            {timeframes.map((tf) => (
              <button
                key={tf}
                onClick={() => onTimeframeChange && onTimeframeChange(tf)}
                className={`px-2 py-0.5 rounded text-[11px] font-mono font-medium transition-all ${
                  timeframe === tf
                    ? 'bg-sky-500 text-white font-bold shadow-sm'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
                }`}
              >
                {tf.toUpperCase()}
              </button>
            ))}
          </div>

          {/* Real-time OHLC Readout with stable container */}
          <div className="hidden lg:flex items-center gap-2 font-mono text-[11px] text-slate-400 min-w-[280px]">
            {crosshairData ? (
              <>
                <span>O <strong className="text-slate-200">${crosshairData.open.toFixed(2)}</strong></span>
                <span>H <strong className="text-slate-200">${crosshairData.high.toFixed(2)}</strong></span>
                <span>L <strong className="text-slate-200">${crosshairData.low.toFixed(2)}</strong></span>
                <span>C <strong className="text-slate-200">${crosshairData.close.toFixed(2)}</strong></span>
                <span className={crosshairData.changePct >= 0 ? 'text-[#00f0a8]' : 'text-[#ff3b69]'}>
                  {crosshairData.changePct >= 0 ? '+' : ''}{crosshairData.changePct.toFixed(2)}%
                </span>
              </>
            ) : (
              <span className="text-slate-600 text-[10px]">Hover chart for OHLC metrics</span>
            )}
          </div>
        </div>

        {/* Right: Technical Toggles, Fullscreen & Controls */}
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1 bg-[#080b11] border border-slate-800 rounded p-0.5">
            <button
              onClick={() => setShowEMA(!showEMA)}
              className={`px-1.5 py-0.5 rounded text-[10px] font-mono transition-colors ${
                showEMA ? 'bg-sky-500/20 text-sky-400 border border-sky-500/30' : 'text-slate-500'
              }`}
              title="EMA 20"
            >
              EMA
            </button>
            <button
              onClick={() => setShowVWAP(!showVWAP)}
              className={`px-1.5 py-0.5 rounded text-[10px] font-mono transition-colors ${
                showVWAP ? 'bg-purple-500/20 text-purple-400 border border-purple-500/30' : 'text-slate-500'
              }`}
              title="Session VWAP"
            >
              VWAP
            </button>
            <button
              onClick={() => setShowMultiSigma(!showMultiSigma)}
              className={`px-1.5 py-0.5 rounded text-[10px] font-mono transition-colors ${
                showMultiSigma ? 'bg-indigo-500/20 text-indigo-400 border border-indigo-500/30' : 'text-slate-500'
              }`}
              title="VWAP Multi-Sigma Bands"
            >
              ±σ
            </button>
            <button
              onClick={() => setShowSMCZones(!showSMCZones)}
              className={`px-1.5 py-0.5 rounded text-[10px] font-mono transition-colors ${
                showSMCZones ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' : 'text-slate-500'
              }`}
              title="SMC Zones & FVGs"
            >
              SMC
            </button>
            <button
              onClick={() => setShowJudasZones(!showJudasZones)}
              className={`px-1.5 py-0.5 rounded text-[10px] font-mono transition-colors ${
                showJudasZones ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30' : 'text-slate-500'
              }`}
              title="Judas Swing Session Killzones"
            >
              JUDAS
            </button>
          </div>

          <button
            onClick={toggleFullscreen}
            className={`p-1.5 rounded transition-all flex items-center gap-1 font-mono text-[11px] ${
              isFullscreen
                ? 'bg-rose-500/20 text-rose-400 border border-rose-500/40 hover:bg-rose-500/30'
                : 'bg-slate-800/80 text-slate-300 hover:bg-slate-700 hover:text-white border border-slate-700'
            }`}
            title={isFullscreen ? 'Exit Full Screen (ESC)' : 'Full Screen'}
          >
            {isFullscreen ? <Minimize2 size={13} /> : <Maximize2 size={13} />}
            <span className="hidden sm:inline">{isFullscreen ? 'EXIT' : 'FULLSCREEN'}</span>
          </button>
        </div>
      </div>

      {/* Main Chart Canvas Area with Left Vertical Drawing Toolbar */}
      <div className="relative flex flex-row flex-1 w-full overflow-hidden">
        {/* Left Vertical Drawing Toolbar (TradingView Dock) */}
        <div className="flex flex-col items-center justify-between py-2 px-1 bg-[#090d16] border-r border-[#1e293b] z-20 gap-1 select-none">
          <div className="flex flex-col items-center gap-1">
            {drawingTools.map((tool) => {
              const IconComponent = tool.icon;
              const isSelected = activeTool === tool.id;
              return (
                <button
                  key={tool.id}
                  onClick={() => {
                    setActiveTool(tool.id);
                    setActiveDrawingPoints([]);
                  }}
                  className={`p-2 rounded transition-all group relative ${
                    isSelected
                      ? 'bg-sky-500 text-white shadow-md shadow-sky-500/30'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
                  }`}
                  title={tool.label}
                >
                  <IconComponent size={15} />
                  {/* Hover Tooltip */}
                  <span className="absolute left-full ml-2 px-2 py-1 bg-slate-900 border border-slate-700 text-[10px] font-mono text-slate-200 rounded whitespace-nowrap opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity z-50 shadow-xl">
                    {tool.label}
                  </span>
                </button>
              );
            })}
          </div>

          {/* Delete All Drawings Button */}
          {drawings.length > 0 && (
            <div className="flex flex-col items-center border-t border-[#1e293b] pt-1">
              <button
                onClick={handleClearDrawings}
                className="p-2 rounded text-rose-400 hover:bg-rose-500/20 hover:text-rose-300 transition-colors relative group"
                title={`Clear drawings (${drawings.length})`}
              >
                <Trash2 size={15} />
                <span className="absolute left-full ml-2 px-2 py-1 bg-slate-900 border border-rose-500/30 text-[10px] font-mono text-rose-300 rounded whitespace-nowrap opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity z-50 shadow-xl">
                  Clear {drawings.length} Drawings
                </span>
              </button>
            </div>
          )}
        </div>

        {/* Lightweight Charts Render Target + Overlay Canvas */}
        <div className={`relative flex-1 ${isFullscreen ? 'h-[calc(100vh-140px)]' : 'h-[440px] min-h-[440px]'}`}>
          <div ref={chartContainerRef} className="absolute inset-0 w-full h-full" />

          <canvas
            ref={drawingCanvasRef}
            onMouseDown={handleCanvasMouseDown}
            className={`absolute inset-0 w-full h-full ${
              activeTool !== 'CURSOR' ? 'pointer-events-auto cursor-crosshair' : 'pointer-events-none cursor-default'
            }`}
          />

          {isHistoricalPan && (
            <button
              onClick={() => {
                chartRef.current?.timeScale().scrollToRealTime();
                setIsHistoricalPan(false);
                setUnreadTicks(0);
              }}
              className="absolute bottom-6 right-16 z-20 flex items-center gap-2 px-3 py-1.5 bg-sky-500/90 hover:bg-sky-500 text-white text-xs font-mono font-semibold rounded-full shadow-lg shadow-sky-500/25 border border-sky-400 backdrop-blur-sm transition-all transform hover:scale-105 animate-pulse"
            >
              <span>Go to Latest</span>
              {unreadTicks > 0 && (
                <span className="px-1.5 py-0.2 bg-black/40 text-[10px] rounded-full">
                  +{unreadTicks}
                </span>
              )}
              <ArrowRight size={13} />
            </button>
          )}

          {activeTool !== 'CURSOR' && (
            <div className="absolute top-3 left-1/2 -translate-x-1/2 z-20 flex items-center gap-2 px-3 py-1 bg-sky-950/90 border border-sky-500/50 rounded-full text-xs font-mono text-sky-300 shadow-xl backdrop-blur-md">
              <Sparkles size={13} className="animate-spin text-sky-400" />
              <span>Click on chart to place {activeTool.replace(/_/g, ' ')}</span>
              <button
                onClick={() => {
                  setActiveTool('CURSOR');
                  setActiveDrawingPoints([]);
                }}
                className="ml-2 px-1.5 py-0.5 bg-rose-500/20 text-rose-400 rounded text-[10px] hover:bg-rose-500/40"
              >
                Cancel
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
