import React, { useEffect, useRef, useState, useCallback, memo } from 'react';
import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  AreaSeries,
  IChartApi,
  ISeriesApi,
  CandlestickData,
  HistogramData,
  LineData,
  AreaData,
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
  Activity,
  Magnet,
  Camera,
  CandlestickChart,
  LineChart as LineChartIcon,
  LucideIcon,
  Clock,
} from 'lucide-react';
import { OHLCVCandle, FVGItem, OrderBlockItem, SKYSetupData, SupportedTimeframe } from '../../types';
import { DrawingObject, WorkspacePersistence } from '../persistence/workspaceDB';
import { indicatorClient } from '../workers/indicatorClient';
import { api } from '../../services/api';

export type DrawingToolType =
  | 'CURSOR'
  | 'TREND_LINE'
  | 'HORIZONTAL_RAY'
  | 'VERTICAL_LINE'
  | 'RECTANGLE'
  | 'FIB_RETRACEMENT'
  | 'LONG_POSITION'
  | 'SHORT_POSITION';

export type ChartTypeMode = 'CANDLES' | 'LINE' | 'AREA';

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

const TIMEFRAMES_EXTENDED: SupportedTimeframe[] = [
  '1m',
  '3m',
  '5m',
  '15m',
  '1h',
  '4h',
  '1d',
];

const TIME_RANGES = ['1D', '5D', '1M', '3M', '6M', 'YTD', '1Y', 'ALL'] as const;

const TradingViewChartComponent: React.FC<TradingViewChartProps> = ({
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

  // Core Chart Instance References (Long-Lived)
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const lineSeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
  const areaSeriesRef = useRef<ISeriesApi<'Area'> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null);
  const emaSeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
  const vwapSeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
  const upper1sRef = useRef<ISeriesApi<'Line'> | null>(null);
  const lower1sRef = useRef<ISeriesApi<'Line'> | null>(null);
  const upper2sRef = useRef<ISeriesApi<'Line'> | null>(null);
  const lower2sRef = useRef<ISeriesApi<'Line'> | null>(null);
  const kronosMedianRef = useRef<ISeriesApi<'Line'> | null>(null);
  const kronosUpperConeRef = useRef<ISeriesApi<'Line'> | null>(null);
  const kronosLowerConeRef = useRef<ISeriesApi<'Line'> | null>(null);

  // Track context for zero-shake data ingestion
  const lastLoadedContextRef = useRef<{
    symbol: string;
    timeframe: string;
    firstTs: number;
    lastTs: number;
    count: number;
  }>({
    symbol: '',
    timeframe: '',
    firstTs: 0,
    lastTs: 0,
    count: 0,
  });

  // Diagnostic & Performance Metrics
  const renderCountRef = useRef(0);
  renderCountRef.current += 1;
  const [showDebugHUD, setShowDebugHUD] = useState(false);
  const [fps, setFps] = useState(60);
  const [updatesPerSec, setUpdatesPerSec] = useState(0);
  const updateCounterRef = useRef(0);

  // Viewport Navigation & Autoscroll Lock State
  const [isHistoricalPan, setIsHistoricalPan] = useState(false);
  const [unreadTicks, setUnreadTicks] = useState(0);
  const [isFullscreen, setIsFullscreen] = useState(false);

  // Chart Style Mode
  const [chartType, setChartType] = useState<ChartTypeMode>('CANDLES');

  // Active Tool & Drawing State
  const [activeTool, setActiveTool] = useState<DrawingToolType>('CURSOR');
  const [drawings, setDrawings] = useState<DrawingObject[]>([]);
  const [activeDrawingPoints, setActiveDrawingPoints] = useState<Array<{ timestamp: number; price: number }>>([]);
  const [previewPoint, setPreviewPoint] = useState<{ timestamp: number; price: number; x: number; y: number } | null>(null);
  const [magnetMode, setMagnetMode] = useState<boolean>(true);

  // Visibility Toggles
  const [showEMA, setShowEMA] = useState(true);
  const [showVWAP, setShowVWAP] = useState(true);
  const [showMultiSigma, setShowMultiSigma] = useState(true);
  const [showSMCZones, setShowSMCZones] = useState(true);
  const [showJudasZones, setShowJudasZones] = useState(true);
  const [showKronos, setShowKronos] = useState(false);
  const [kronosData, setKronosData] = useState<any>(null);

  // Active Range Preset
  const [activeRange, setActiveRange] = useState<string>('ALL');

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

  // Candle Close Countdown
  const [countdown, setCountdown] = useState<string>('');
  const [currentTimeStr, setCurrentTimeStr] = useState<string>('');

  // Clock & Countdown Timer Loop
  useEffect(() => {
    const getIntervalMs = (tf: string): number => {
      switch (tf) {
        case '1m': return 60 * 1000;
        case '3m': return 3 * 60 * 1000;
        case '5m': return 5 * 60 * 1000;
        case '15m': return 15 * 60 * 1000;
        case '1h': return 60 * 60 * 1000;
        case '4h': return 4 * 60 * 60 * 1000;
        case '1d': return 24 * 60 * 60 * 1000;
        default: return 15 * 60 * 1000;
      }
    };

    const timer = setInterval(() => {
      const now = Date.now();
      const intervalMs = getIntervalMs(timeframe);
      const msRemaining = intervalMs - (now % intervalMs);
      const totalSec = Math.floor(msRemaining / 1000);
      const hours = Math.floor(totalSec / 3600);
      const mins = Math.floor((totalSec % 3600) / 60);
      const secs = totalSec % 60;

      if (hours > 0) {
        setCountdown(`${hours}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`);
      } else {
        setCountdown(`${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`);
      }

      setCurrentTimeStr(new Date().toLocaleTimeString());
    }, 1000);

    return () => clearInterval(timer);
  }, [timeframe]);

  // FPS Diagnostics Loop
  useEffect(() => {
    let frameId: number;
    let lastTime = performance.now();
    let frames = 0;

    const measureLoop = (currentTime: number) => {
      frames++;
      if (currentTime - lastTime >= 1000) {
        setFps(Math.round((frames * 1000) / (currentTime - lastTime)));
        setUpdatesPerSec(updateCounterRef.current);
        updateCounterRef.current = 0;
        frames = 0;
        lastTime = currentTime;
      }
      frameId = requestAnimationFrame(measureLoop);
    };

    frameId = requestAnimationFrame(measureLoop);
    return () => cancelAnimationFrame(frameId);
  }, []);

  // Keyboard shortcut (D) to toggle Diagnostic HUD
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() === 'd' && !['INPUT', 'TEXTAREA'].includes((e.target as HTMLElement).tagName)) {
        setShowDebugHUD((prev) => !prev);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // 1. Initialize Long-Lived Lightweight Charts Instance (MOUNT ONCE — Zero Shake)
  useEffect(() => {
    if (!chartContainerRef.current) return;

    const container = chartContainerRef.current;
    container.innerHTML = '';

    const initialHeight = container.clientHeight || 460;
    const initialWidth = container.clientWidth || 800;

    // TradingView Obsidian Theme Palette
    const chart = createChart(container, {
      width: initialWidth,
      height: initialHeight,
      layout: {
        background: { type: ColorType.Solid, color: '#131722' },
        textColor: '#787b86',
        fontSize: 11,
        fontFamily: "-apple-system, BlinkMacSystemFont, 'Trebuchet MS', Roboto, Ubuntu, sans-serif",
      },
      grid: {
        vertLines: { color: '#1e222d', style: 1 },
        horzLines: { color: '#1e222d', style: 1 },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: {
          color: '#758696',
          width: 1,
          style: 3,
          labelBackgroundColor: '#2a2e39',
        },
        horzLine: {
          color: '#758696',
          width: 1,
          style: 3,
          labelBackgroundColor: '#2a2e39',
        },
      },
      timeScale: {
        borderColor: '#2a2e39',
        timeVisible: true,
        secondsVisible: false,
        rightOffset: 15,
        barSpacing: 9,
        minBarSpacing: 2,
      },
      rightPriceScale: {
        borderColor: '#2a2e39',
        scaleMargins: {
          top: 0.08,
          bottom: 0.18,
        },
        autoScale: true,
      },
    });

    // Institutional Candlestick Series (TradingView Emerald & Crimson)
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#089981',
      downColor: '#f23645',
      borderUpColor: '#089981',
      borderDownColor: '#f23645',
      wickUpColor: '#089981',
      wickDownColor: '#f23645',
    });

    // Line & Area Series (for alternative chart views)
    const lineSeries = chart.addSeries(LineSeries, {
      color: '#2962ff',
      lineWidth: 2,
      visible: false,
    });

    const areaSeries = chart.addSeries(AreaSeries, {
      topColor: 'rgba(41, 98, 255, 0.4)',
      bottomColor: 'rgba(41, 98, 255, 0.0)',
      lineColor: '#2962ff',
      lineWidth: 2,
      visible: false,
    });

    // Volume Histogram Series
    const volumeSeries = chart.addSeries(HistogramSeries, {
      color: 'rgba(56, 189, 248, 0.35)',
      priceFormat: { type: 'volume' },
      priceScaleId: '',
    });
    volumeSeries.priceScale().applyOptions({
      scaleMargins: {
        top: 0.82,
        bottom: 0,
      },
    });

    // EMA 20 Line Series (Sky Blue)
    const emaSeries = chart.addSeries(LineSeries, {
      color: '#38bdf8',
      lineWidth: 2,
      crosshairMarkerVisible: false,
      lastValueVisible: false,
      priceLineVisible: false,
    });

    // VWAP Line Series (Violet)
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

    // Kronos Neural Trajectory & Forecast Cone Series
    const kronosMedian = chart.addSeries(LineSeries, {
      color: '#818cf8',
      lineWidth: 2,
      lineStyle: 1,
      crosshairMarkerVisible: true,
      lastValueVisible: true,
      priceLineVisible: false,
      visible: false,
    });
    const kronosUpperCone = chart.addSeries(LineSeries, {
      color: 'rgba(99, 102, 241, 0.5)',
      lineWidth: 1,
      lineStyle: 2,
      crosshairMarkerVisible: false,
      lastValueVisible: false,
      priceLineVisible: false,
      visible: false,
    });
    const kronosLowerCone = chart.addSeries(LineSeries, {
      color: 'rgba(99, 102, 241, 0.5)',
      lineWidth: 1,
      lineStyle: 2,
      crosshairMarkerVisible: false,
      lastValueVisible: false,
      priceLineVisible: false,
      visible: false,
    });

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;
    lineSeriesRef.current = lineSeries;
    areaSeriesRef.current = areaSeries;
    volumeSeriesRef.current = volumeSeries;
    emaSeriesRef.current = emaSeries;
    vwapSeriesRef.current = vwapSeries;
    upper1sRef.current = upper1s;
    lower1sRef.current = lower1s;
    upper2sRef.current = upper2s;
    lower2sRef.current = lower2s;
    kronosMedianRef.current = kronosMedian;
    kronosUpperConeRef.current = kronosUpperCone;
    kronosLowerConeRef.current = kronosLowerCone;

    // Crosshair readout subscription
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

    // Resize observer (smooth resize without destroying chart)
    const handleResize = () => {
      if (chartContainerRef.current && chartRef.current) {
        const w = chartContainerRef.current.clientWidth;
        const h = chartContainerRef.current.clientHeight || 460;
        chartRef.current.resize(w, h);
        updateCanvasDimensions();
        drawCanvasOverlays();
      }
    };

    window.addEventListener('resize', handleResize);
    const resizeObserver = new ResizeObserver(handleResize);
    resizeObserver.observe(container);

    setTimeout(handleResize, 50);

    return () => {
      window.removeEventListener('resize', handleResize);
      resizeObserver.disconnect();
      chart.remove();
      chartRef.current = null;
    };
  }, []);

  // Update chart display series when chartType changes
  useEffect(() => {
    if (!candleSeriesRef.current || !lineSeriesRef.current || !areaSeriesRef.current) return;
    candleSeriesRef.current.applyOptions({ visible: chartType === 'CANDLES' });
    lineSeriesRef.current.applyOptions({ visible: chartType === 'LINE' });
    areaSeriesRef.current.applyOptions({ visible: chartType === 'AREA' });
  }, [chartType]);

  // Handle Fullscreen Toggle
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
          const h = chartContainerRef.current.clientHeight || (isFull ? window.innerHeight - 90 : 460);
          chartRef.current.resize(w, h);
          updateCanvasDimensions();
          drawCanvasOverlays();
        }
      }, 50);
    };

    document.addEventListener('fullscreenchange', handleFullscreenChange);
    return () => document.removeEventListener('fullscreenchange', handleFullscreenChange);
  }, []);

  // 2. Load Persisted Drawings from IndexedDB on Symbol Change
  useEffect(() => {
    let isMounted = true;
    WorkspacePersistence.loadDrawings(symbol).then((stored: DrawingObject[]) => {
      if (isMounted) setDrawings(stored);
    });
    return () => { isMounted = false; };
  }, [symbol]);

  // 3. Zero-Shake Ingestion: Set Data on Symbol/Timeframe/Dataset Change
  useEffect(() => {
    if (!candleSeriesRef.current || !candles || candles.length === 0) return;

    const firstTs = candles[0]?.[0] || 0;
    const lastTs = candles[candles.length - 1]?.[0] || 0;
    const isContextChanged =
      lastLoadedContextRef.current.symbol !== symbol ||
      lastLoadedContextRef.current.timeframe !== timeframe ||
      lastLoadedContextRef.current.firstTs !== firstTs ||
      lastLoadedContextRef.current.lastTs !== lastTs ||
      lastLoadedContextRef.current.count !== candles.length;

    if (isContextChanged) {
      const formattedCandles: CandlestickData[] = [];
      const formattedLine: LineData[] = [];
      const formattedArea: AreaData[] = [];
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
          formattedLine.push({
            time: t as Time,
            value: c[4],
          });
          formattedArea.push({
            time: t as Time,
            value: c[4],
          });
          formattedVolume.push({
            time: t as Time,
            value: c[5] || 0,
            color: c[4] >= c[1] ? 'rgba(8, 153, 129, 0.4)' : 'rgba(242, 54, 69, 0.4)',
          });
          prevTime = t;
        }
      }

      if (formattedCandles.length > 0) {
        candleSeriesRef.current.setData(formattedCandles);
        lineSeriesRef.current?.setData(formattedLine);
        areaSeriesRef.current?.setData(formattedArea);
        volumeSeriesRef.current?.setData(formattedVolume);
        chartRef.current?.timeScale().fitContent();
        lastLoadedContextRef.current = {
          symbol,
          timeframe,
          firstTs,
          lastTs,
          count: formattedCandles.length,
        };
      }
    }

    // Offload indicators to Web Worker asynchronously
    const workerCandles = candles.map((c) => ({
      timestamp: c[0],
      open: c[1],
      high: c[2],
      low: c[3],
      close: c[4],
      volume: c[5],
    }));

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
  }, [candles, symbol, timeframe, showEMA, showVWAP, showMultiSigma]);

  // 3b. Kronos Probabilistic Trajectory Path & Cone Overlay Ingestion
  useEffect(() => {
    if (!showKronos) {
      kronosMedianRef.current?.applyOptions({ visible: false });
      kronosUpperConeRef.current?.applyOptions({ visible: false });
      kronosLowerConeRef.current?.applyOptions({ visible: false });
      setKronosData(null);
      return;
    }

    let isMounted = true;
    const cleanSym = symbol.replace('/', '').toUpperCase();
    api.getKronosForecast({ symbol: cleanSym, timeframe, samples: 5, horizon: 12 })
      .then((res) => {
        if (!isMounted || !res || !res.paths || res.paths.length === 0) return;
        setKronosData(res);

        const sampleCount = res.paths.length;
        const horizon = res.paths[0].predicted_timestamps.length;

        const medianPoints: LineData[] = [];
        const upperPoints: LineData[] = [];
        const lowerPoints: LineData[] = [];

        // Anchor on current last candle
        const lastBar = candles && candles.length > 0 ? candles[candles.length - 1] : null;
        let lastT = 0;
        if (lastBar) {
          lastT = Math.floor(lastBar[0] / 1000);
          const c0 = lastBar[4];
          medianPoints.push({ time: lastT as Time, value: c0 });
          upperPoints.push({ time: lastT as Time, value: c0 });
          lowerPoints.push({ time: lastT as Time, value: c0 });
        }

        const tfSeconds: Record<string, number> = {
          '1m': 60, '3m': 180, '5m': 300, '15m': 900, '30m': 1800, '1h': 3600, '4h': 14400, '1d': 86400
        };
        const stepSec = tfSeconds[timeframe] || 900;

        for (let step = 0; step < horizon; step++) {
          const rawT = Math.floor(res.paths[0].predicted_timestamps[step] / 1000);
          const t = (rawT > lastT ? rawT : lastT + stepSec) as Time;
          lastT = t as number;

          const stepCloses = res.paths.map((p: any) => p.predicted_closes[step]).sort((a: number, b: number) => a - b);
          const medianVal = stepCloses[Math.floor(sampleCount / 2)];
          const lowerVal = stepCloses[0];
          const upperVal = stepCloses[sampleCount - 1];

          medianPoints.push({ time: t, value: medianVal });
          upperPoints.push({ time: t, value: upperVal });
          lowerPoints.push({ time: t, value: lowerVal });
        }

        kronosMedianRef.current?.setData(medianPoints);
        kronosUpperConeRef.current?.setData(upperPoints);
        kronosLowerConeRef.current?.setData(lowerPoints);

        kronosMedianRef.current?.applyOptions({ visible: true });
        kronosUpperConeRef.current?.applyOptions({ visible: true });
        kronosLowerConeRef.current?.applyOptions({ visible: true });
      })
      .catch((err) => {
        console.warn('Kronos forecast fetch failed:', err);
      });

    return () => { isMounted = false; };
  }, [showKronos, symbol, timeframe, candles]);

  // 4. Live Tick Micro-Batching with RAF (Incremental Update — ZERO Full Rerender)
  useEffect(() => {
    if (!liveCandle || !candleSeriesRef.current) return;

    const barTime = Math.floor(liveCandle[0] / 1000) as Time;
    const bar: CandlestickData = {
      time: barTime,
      open: liveCandle[1],
      high: liveCandle[2],
      low: liveCandle[3],
      close: liveCandle[4],
    };

    updateCounterRef.current += 1;

    window.requestAnimationFrame(() => {
      try {
        candleSeriesRef.current?.update(bar);
        lineSeriesRef.current?.update({ time: barTime, value: liveCandle[4] });
        areaSeriesRef.current?.update({ time: barTime, value: liveCandle[4] });
        volumeSeriesRef.current?.update({
          time: barTime,
          value: liveCandle[5] || 0,
          color: liveCandle[4] >= liveCandle[1] ? 'rgba(8, 153, 129, 0.4)' : 'rgba(242, 54, 69, 0.4)',
        });

        if (isHistoricalPan) {
          setUnreadTicks((prev) => prev + 1);
        }
      } catch (err) {
        // Silently skip out-of-order ticks during timeframe/symbol transition
      }
    });
  }, [liveCandle, isHistoricalPan]);

  // Time Range Quick Jump Handler
  const handleSetTimeRange = (range: typeof TIME_RANGES[number]) => {
    setActiveRange(range);
    if (!chartRef.current || !candles || candles.length === 0) return;
    const now = Math.floor(Date.now() / 1000);
    let from = now;
    switch (range) {
      case '1D': from = now - (24 * 3600); break;
      case '5D': from = now - (5 * 24 * 3600); break;
      case '1M': from = now - (30 * 24 * 3600); break;
      case '3M': from = now - (90 * 24 * 3600); break;
      case '6M': from = now - (180 * 24 * 3600); break;
      case 'YTD': {
        const startOfYear = new Date(new Date().getFullYear(), 0, 1).getTime() / 1000;
        from = Math.floor(startOfYear);
        break;
      }
      case '1Y': from = now - (365 * 24 * 3600); break;
      case 'ALL':
        chartRef.current.timeScale().fitContent();
        return;
    }
    chartRef.current.timeScale().setVisibleRange({
      from: from as Time,
      to: now as Time,
    });
  };

  // Snapshot Capture Feature
  const handleTakeSnapshot = () => {
    const chartContainer = chartContainerRef.current;
    if (!chartContainer) return;
    const canvas = chartContainer.querySelector('canvas');
    if (!canvas) return;
    const link = document.createElement('a');
    link.download = `${symbol.replace('/', '_')}_${timeframe}_${Date.now()}.png`;
    link.href = canvas.toDataURL('image/png');
    link.click();
  };

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
      (orderBlocks || []).forEach((ob) => {
        if (!ob) return;
        const rawZone = ob.price_zone || ((ob as any).bottom_price != null && (ob as any).top_price != null ? [(ob as any).bottom_price, (ob as any).top_price] : null);
        if (!rawZone || !Array.isArray(rawZone) || rawZone.length < 2) return;
        const pBot = Number(rawZone[0]);
        const pTop = Number(rawZone[1]);
        if (isNaN(pBot) || isNaN(pTop)) return;

        const yTop = series.priceToCoordinate(Math.max(pBot, pTop));
        const yBot = series.priceToCoordinate(Math.min(pBot, pTop));
        if (yTop !== null && yBot !== null && !isNaN(yTop) && !isNaN(yBot)) {
          const height = Math.max(2, Math.abs(yBot - yTop));
          const topCoord = Math.min(yTop, yBot);
          ctx.fillStyle = ob.type === 'bullish' ? 'rgba(8, 153, 129, 0.14)' : 'rgba(242, 54, 69, 0.14)';
          ctx.strokeStyle = ob.type === 'bullish' ? '#089981' : '#f23645';
          ctx.lineWidth = 1;
          ctx.fillRect(0, topCoord, canvas.width, height);
          ctx.strokeRect(0, topCoord, canvas.width, height);
        }
      });

      (fvgs || []).forEach((fvg) => {
        if (!fvg || fvg.mitigated) return;
        const rawZone = fvg.price_zone || ((fvg as any).bottom_price != null && (fvg as any).top_price != null ? [(fvg as any).bottom_price, (fvg as any).top_price] : null);
        if (!rawZone || !Array.isArray(rawZone) || rawZone.length < 2) return;
        const pBot = Number(rawZone[0]);
        const pTop = Number(rawZone[1]);
        if (isNaN(pBot) || isNaN(pTop)) return;

        const yTop = series.priceToCoordinate(Math.max(pBot, pTop));
        const yBot = series.priceToCoordinate(Math.min(pBot, pTop));
        if (yTop !== null && yBot !== null && !isNaN(yTop) && !isNaN(yBot)) {
          const height = Math.max(2, Math.abs(yBot - yTop));
          const topCoord = Math.min(yTop, yBot);
          ctx.fillStyle = fvg.type === 'bullish' ? 'rgba(8, 153, 129, 0.08)' : 'rgba(242, 54, 69, 0.08)';
          ctx.strokeStyle = fvg.type === 'bullish' ? 'rgba(8, 153, 129, 0.4)' : 'rgba(242, 54, 69, 0.4)';
          ctx.fillRect(0, topCoord, canvas.width, height);
          ctx.strokeRect(0, topCoord, canvas.width, height);
        }
      });
    }

    // 3. Draw User Saved Drawings
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
        ctx.fillStyle = 'rgba(242, 54, 69, 0.25)';
        ctx.strokeStyle = '#f23645';
        ctx.fillRect(x1, Math.min(entryY, slY), width, Math.abs(slY - entryY));
        ctx.strokeRect(x1, Math.min(entryY, slY), width, Math.abs(slY - entryY));

        // TP Zone (Green)
        ctx.fillStyle = 'rgba(8, 153, 129, 0.25)';
        ctx.strokeStyle = '#089981';
        ctx.fillRect(x1, Math.min(entryY, tpY), width, Math.abs(tpY - entryY));
        ctx.strokeRect(x1, Math.min(entryY, tpY), width, Math.abs(tpY - entryY));

        // R:R Badge
        ctx.fillStyle = '#1e222d';
        ctx.fillRect(x1 + 6, entryY - 10, 80, 20);
        ctx.strokeRect(x1 + 6, entryY - 10, 80, 20);
        ctx.fillStyle = isLong ? '#089981' : '#f23645';
        ctx.font = 'bold 11px monospace';
        ctx.fillText(`R:R 2.50`, x1 + 14, entryY + 4);
      }

      ctx.restore();
    });

    // 4. Draw Real-Time Live Rubber-Band Drawing Previews
    if (activeTool !== 'CURSOR' && previewPoint) {
      ctx.save();
      const currX = previewPoint.x;
      const currY = previewPoint.y;

      if (activeDrawingPoints.length === 1) {
        const p1 = activeDrawingPoints[0];
        const x1 = chart.timeScale().timeToCoordinate(Math.floor(p1.timestamp / 1000) as Time) ?? p1.price;
        const y1 = series.priceToCoordinate(p1.price) ?? currY;

        if (x1 !== null && y1 !== null) {
          // Draw start anchor point
          ctx.fillStyle = '#38bdf8';
          ctx.beginPath();
          ctx.arc(x1, y1, 4, 0, 2 * Math.PI);
          ctx.fill();
          ctx.strokeStyle = '#ffffff';
          ctx.lineWidth = 1.5;
          ctx.stroke();

          ctx.strokeStyle = activeTool === 'LONG_POSITION' ? '#089981' : activeTool === 'SHORT_POSITION' ? '#f23645' : '#38bdf8';
          ctx.fillStyle = ctx.strokeStyle;
          ctx.lineWidth = 2;
          ctx.setLineDash([4, 4]);

          if (activeTool === 'TREND_LINE') {
            ctx.beginPath();
            ctx.moveTo(x1, y1);
            ctx.lineTo(currX, currY);
            ctx.stroke();

            ctx.setLineDash([]);
            ctx.beginPath();
            ctx.arc(currX, currY, 3.5, 0, 2 * Math.PI);
            ctx.fill();

            const deltaPct = ((previewPoint.price - p1.price) / p1.price) * 100;
            ctx.font = 'bold 10px monospace';
            ctx.fillText(`${deltaPct >= 0 ? '+' : ''}${deltaPct.toFixed(2)}%`, currX + 8, currY - 6);
          } else if (activeTool === 'RECTANGLE') {
            const w = currX - x1;
            const h = currY - y1;
            ctx.fillStyle = 'rgba(56, 189, 248, 0.18)';
            ctx.fillRect(x1, y1, w, h);
            ctx.strokeRect(x1, y1, w, h);
          } else if (activeTool === 'FIB_RETRACEMENT') {
            const levels = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0];
            const dy = currY - y1;
            levels.forEach((lvl) => {
              const yLvl = y1 + dy * lvl;
              const priceLvl = p1.price + (previewPoint.price - p1.price) * lvl;
              ctx.beginPath();
              ctx.moveTo(Math.min(x1, currX), yLvl);
              ctx.lineTo(canvas.width, yLvl);
              ctx.stroke();
              ctx.fillText(`Fib ${(lvl * 100).toFixed(1)}% ($${priceLvl.toFixed(2)})`, Math.min(x1, currX) + 5, yLvl - 3);
            });
          } else if (activeTool === 'LONG_POSITION' || activeTool === 'SHORT_POSITION') {
            const isLong = activeTool === 'LONG_POSITION';
            const entryY = y1;
            const slY = currY;
            const riskH = Math.abs(slY - entryY);
            const tpY = isLong ? entryY - (2.5 * riskH) : entryY + (2.5 * riskH);
            const width = Math.max(Math.abs(currX - x1), 140);

            ctx.fillStyle = 'rgba(242, 54, 69, 0.25)';
            ctx.strokeStyle = '#f23645';
            ctx.fillRect(x1, Math.min(entryY, slY), width, Math.abs(slY - entryY));
            ctx.strokeRect(x1, Math.min(entryY, slY), width, Math.abs(slY - entryY));

            ctx.fillStyle = 'rgba(8, 153, 129, 0.25)';
            ctx.strokeStyle = '#089981';
            ctx.fillRect(x1, Math.min(entryY, tpY), width, Math.abs(tpY - entryY));
            ctx.strokeRect(x1, Math.min(entryY, tpY), width, Math.abs(tpY - entryY));

            ctx.fillStyle = '#1e222d';
            ctx.fillRect(x1 + 6, entryY - 10, 80, 20);
            ctx.strokeRect(x1 + 6, entryY - 10, 80, 20);
            ctx.fillStyle = isLong ? '#089981' : '#f23645';
            ctx.font = 'bold 11px monospace';
            ctx.fillText(`R:R 2.50`, x1 + 14, entryY + 4);
          }
        }
      } else if (activeDrawingPoints.length === 0) {
        if (activeTool === 'HORIZONTAL_RAY') {
          ctx.strokeStyle = 'rgba(56, 189, 248, 0.7)';
          ctx.lineWidth = 1.5;
          ctx.setLineDash([4, 4]);
          ctx.beginPath();
          ctx.moveTo(0, currY);
          ctx.lineTo(canvas.width, currY);
          ctx.stroke();
          ctx.font = 'bold 10px monospace';
          ctx.fillStyle = '#38bdf8';
          ctx.fillText(`$${previewPoint.price.toFixed(2)}`, canvas.width - 70, currY - 4);
        } else if (activeTool === 'VERTICAL_LINE') {
          ctx.strokeStyle = 'rgba(56, 189, 248, 0.7)';
          ctx.lineWidth = 1.5;
          ctx.setLineDash([4, 4]);
          ctx.beginPath();
          ctx.moveTo(currX, 0);
          ctx.lineTo(currX, canvas.height);
          ctx.stroke();
          ctx.font = 'bold 10px monospace';
          ctx.fillStyle = '#38bdf8';
          ctx.fillText(new Date(previewPoint.timestamp).toLocaleTimeString(), currX + 4, 20);
        }
      }

      ctx.restore();
    }

    // 5. Draw SKY Signal Markers
    if (skySetups && skySetups.length > 0) {
      skySetups.forEach((setup) => {
        const isBull = setup.direction === 'LONG';
        const x = chart.timeScale().timeToCoordinate(Math.floor(setup.timestamp / 1000) as Time);
        const y = series.priceToCoordinate(setup.entry_price);
        if (x === null || y === null) return;

        ctx.save();
        ctx.fillStyle = isBull ? '#089981' : '#f23645';
        ctx.strokeStyle = isBull ? '#089981' : '#f23645';
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

        ctx.fillStyle = '#1e222d';
        ctx.fillRect(boxX, boxY, textWidth + 8, 14);
        ctx.strokeRect(boxX, boxY, textWidth + 8, 14);

        ctx.fillStyle = isBull ? '#089981' : '#f23645';
        ctx.fillText(label, boxX + 4, boxY + 11);

        ctx.restore();
      });
    }
  }, [candles, showSMCZones, showJudasZones, drawings, skySetups, activeTool, activeDrawingPoints, previewPoint]);

  useEffect(() => {
    updateCanvasDimensions();
    drawCanvasOverlays();
  }, [drawings, drawCanvasOverlays, previewPoint]);

  // Coordinate Extrapolation Helper
  const getPointFromEvent = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = drawingCanvasRef.current;
    const chart = chartRef.current;
    const series = candleSeriesRef.current;
    if (!canvas || !chart || !series) return null;

    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    const rawPrice = series.coordinateToPrice(y);
    let price: number = rawPrice !== null ? Number(rawPrice) : (candles[candles.length - 1]?.[4] || 100);

    // Magnet snap to nearest candle High/Low/Open/Close if magnetMode enabled
    if (magnetMode && candles.length > 0) {
      const timeCoord = chart.timeScale().coordinateToTime(x);
      if (timeCoord !== null) {
        const tsMs = typeof timeCoord === 'number' ? timeCoord * 1000 : 0;
        const nearestCandle = candles.find((c) => Math.abs(c[0] - tsMs) < 300000);
        if (nearestCandle) {
          const prices = [nearestCandle[1], nearestCandle[2], nearestCandle[3], nearestCandle[4]];
          let closest = prices[0];
          let minDiff = Math.abs(prices[0] - price);
          prices.forEach((p) => {
            const diff = Math.abs(p - price);
            if (diff < minDiff) {
              minDiff = diff;
              closest = p;
            }
          });
          // Snap if within 1.5% distance
          if (minDiff / price < 0.015) {
            price = closest;
          }
        }
      }
    }

    let ts: number | null = null;
    const timeCoord = chart.timeScale().coordinateToTime(x);
    if (timeCoord !== null) {
      if (typeof timeCoord === 'number') {
        ts = timeCoord * 1000;
      } else if (typeof timeCoord === 'string') {
        ts = new Date(timeCoord).getTime();
      } else if (typeof timeCoord === 'object' && timeCoord !== null && 'year' in timeCoord) {
        ts = new Date(Date.UTC((timeCoord as any).year, (timeCoord as any).month - 1, (timeCoord as any).day)).getTime();
      }
    } else if (candles && candles.length > 0) {
      const logical = chart.timeScale().coordinateToLogical(x);
      if (logical !== null) {
        const step = candles.length > 1 ? (candles[1][0] - candles[0][0]) : 900000;
        const barDiff = logical - (candles.length - 1);
        ts = candles[candles.length - 1][0] + (barDiff * step);
      }
    }

    if (ts === null) ts = Date.now();
    return { x, y, timestamp: ts, price };
  };

  const handleCanvasMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (activeTool === 'CURSOR') {
      if (previewPoint) setPreviewPoint(null);
      return;
    }
    const pt = getPointFromEvent(e);
    if (pt) {
      setPreviewPoint(pt);
    }
  };

  const handleCanvasMouseLeave = () => {
    if (previewPoint) setPreviewPoint(null);
  };

  const handleCanvasMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (activeTool === 'CURSOR') return;

    const pt = getPointFromEvent(e);
    if (!pt) return;

    const newPoints = [...activeDrawingPoints, { timestamp: pt.timestamp, price: pt.price }];

    if (activeTool === 'HORIZONTAL_RAY' || activeTool === 'VERTICAL_LINE') {
      const newDrawing: DrawingObject = {
        id: `draw_${Date.now()}_${Math.random().toString(36).substring(2, 6)}`,
        symbol,
        timeframe,
        type: activeTool,
        points: [newPoints[0], newPoints[0]],
        color: '#38bdf8',
        lineWidth: 2,
        createdAt: Date.now(),
      };

      const updated = [...drawings, newDrawing];
      setDrawings(updated);
      WorkspacePersistence.saveDrawing(newDrawing);
      setActiveDrawingPoints([]);
      setPreviewPoint(null);
      setActiveTool('CURSOR');
      return;
    }

    if (newPoints.length >= 2) {
      const newDrawing: DrawingObject = {
        id: `draw_${Date.now()}_${Math.random().toString(36).substring(2, 6)}`,
        symbol,
        timeframe,
        type: activeTool,
        points: newPoints,
        color: activeTool === 'LONG_POSITION' ? '#089981' : activeTool === 'SHORT_POSITION' ? '#f23645' : '#38bdf8',
        lineWidth: 2,
        createdAt: Date.now(),
      };

      const updated = [...drawings, newDrawing];
      setDrawings(updated);
      WorkspacePersistence.saveDrawing(newDrawing);

      // Auto-deploy position tools into order desk if handler provided
      if ((activeTool === 'LONG_POSITION' || activeTool === 'SHORT_POSITION') && onDeploySetup) {
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
      setPreviewPoint(null);
      setActiveTool('CURSOR');
    } else {
      setActiveDrawingPoints(newPoints);
    }
  };

  const handleClearDrawings = () => {
    drawings.forEach((d) => WorkspacePersistence.deleteDrawing(d.id));
    setDrawings([]);
    setActiveDrawingPoints([]);
    setPreviewPoint(null);
    setActiveTool('CURSOR');
  };

  // Drawing Tools Suite
  const drawingTools: Array<{ id: DrawingToolType; label: string; icon: LucideIcon }> = [
    { id: 'CURSOR', label: 'Crosshair / Cursor', icon: MousePointer },
    { id: 'TREND_LINE', label: 'Trend Line', icon: TrendingUp },
    { id: 'HORIZONTAL_RAY', label: 'Horizontal Ray / Level', icon: Minus },
    { id: 'VERTICAL_LINE', label: 'Vertical Line', icon: SeparatorVertical },
    { id: 'RECTANGLE', label: 'Rectangle / Order Block Zone', icon: Square },
    { id: 'FIB_RETRACEMENT', label: 'Fibonacci Retracement', icon: Hash },
    { id: 'LONG_POSITION', label: 'Long Position R:R Tool', icon: ArrowUpCircle },
    { id: 'SHORT_POSITION', label: 'Short Position R:R Tool', icon: ArrowDownCircle },
  ];

  const lastCandle = candles && candles.length > 0 ? candles[candles.length - 1] : null;
  const getCandleField = (c: unknown, idx: number, fallback = 0): number => {
    if (!c) return fallback;
    if (Array.isArray(c)) return Number(c[idx]) || fallback;
    const keys = ['timestamp', 'open', 'high', 'low', 'close', 'volume'];
    const key = keys[idx];
    return Number((c as Record<string, unknown>)[key]) || fallback;
  };

  const lastPrice = liveCandle ? getCandleField(liveCandle, 4) : (lastCandle ? getCandleField(lastCandle, 4) : 0);
  const openPrice = lastCandle ? getCandleField(lastCandle, 1, lastPrice) : lastPrice;
  const highPrice = lastCandle ? getCandleField(lastCandle, 2, lastPrice) : lastPrice;
  const lowPrice = lastCandle ? getCandleField(lastCandle, 3, lastPrice) : lastPrice;
  const priceChange = (lastPrice || 0) - (openPrice || 0);
  const priceChangePct = openPrice > 0 ? (priceChange / openPrice) * 100 : 0;
  const isUp = priceChange >= 0;

  return (
    <div
      ref={chartWrapperRef}
      className={`relative flex flex-col bg-[#131722] border border-[#2a2e39] rounded-t-lg overflow-hidden select-none transition-all duration-300 font-sans ${
        isFullscreen ? 'fixed inset-0 z-50 rounded-none w-screen h-screen' : 'w-full'
      }`}
    >
      {/* 1. Top Professional Chart Header Toolbar (TradingView Style) */}
      <div className="flex flex-wrap items-center justify-between px-3 py-1.5 bg-[#181c27] border-b border-[#2a2e39] text-xs z-20 gap-2">
        {/* Left Section: Symbol Badge + Search + Timeframes */}
        <div className="flex items-center gap-2">
          {/* Symbol Button */}
          <div className="flex items-center gap-1.5 px-2.5 py-1 bg-[#242936] hover:bg-[#2e3444] border border-[#363c4e] rounded cursor-pointer transition-colors text-slate-100 font-bold font-mono">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            <span>{symbol}</span>
            <span className="text-[10px] text-slate-400 font-normal px-1 rounded bg-[#131722]">PERP</span>
          </div>

          <div className="h-4 w-[1px] bg-[#2a2e39]" />

          {/* Granular Timeframe Strip */}
          <div className="flex items-center gap-0.5">
            {TIMEFRAMES_EXTENDED.map((tf) => (
              <button
                key={tf}
                onClick={() => onTimeframeChange && onTimeframeChange(tf)}
                className={`px-2 py-1 rounded text-[11px] font-mono font-medium transition-colors ${
                  timeframe === tf
                    ? 'bg-[#2962ff] text-white font-bold shadow-sm'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-[#242936]'
                }`}
              >
                {tf}
              </button>
            ))}
          </div>

          <div className="h-4 w-[1px] bg-[#2a2e39]" />

          {/* Chart Type Selector */}
          <div className="flex items-center bg-[#131722] border border-[#2a2e39] rounded p-0.5">
            <button
              onClick={() => setChartType('CANDLES')}
              className={`p-1 rounded ${chartType === 'CANDLES' ? 'bg-[#242936] text-white' : 'text-slate-500 hover:text-slate-300'}`}
              title="Candlesticks"
            >
              <CandlestickChart size={14} />
            </button>
            <button
              onClick={() => setChartType('LINE')}
              className={`p-1 rounded ${chartType === 'LINE' ? 'bg-[#242936] text-white' : 'text-slate-500 hover:text-slate-300'}`}
              title="Line Chart"
            >
              <LineChartIcon size={14} />
            </button>
          </div>
        </div>

        {/* Right Section: Indicators, HUD, Camera, Fullscreen */}
        <div className="flex items-center gap-1.5">
          {/* Indicator Toggles */}
          <div className="flex items-center bg-[#131722] border border-[#2a2e39] rounded p-0.5">
            <button
              onClick={() => setShowEMA(!showEMA)}
              className={`px-2 py-0.5 rounded text-[10px] font-mono transition-colors ${
                showEMA ? 'bg-sky-500/20 text-sky-400 border border-sky-500/30' : 'text-slate-500'
              }`}
              title="EMA 20"
            >
              EMA
            </button>
            <button
              onClick={() => setShowVWAP(!showVWAP)}
              className={`px-2 py-0.5 rounded text-[10px] font-mono transition-colors ${
                showVWAP ? 'bg-purple-500/20 text-purple-400 border border-purple-500/30' : 'text-slate-500'
              }`}
              title="Session VWAP"
            >
              VWAP
            </button>
            <button
              onClick={() => setShowMultiSigma(!showMultiSigma)}
              className={`px-2 py-0.5 rounded text-[10px] font-mono transition-colors ${
                showMultiSigma ? 'bg-indigo-500/20 text-indigo-400 border border-indigo-500/30' : 'text-slate-500'
              }`}
              title="VWAP ±σ Bands"
            >
              ±σ
            </button>
            <button
              onClick={() => setShowSMCZones(!showSMCZones)}
              className={`px-2 py-0.5 rounded text-[10px] font-mono transition-colors ${
                showSMCZones ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' : 'text-slate-500'
              }`}
              title="SMC Order Blocks & FVGs"
            >
              SMC
            </button>
            <button
              onClick={() => setShowJudasZones(!showJudasZones)}
              className={`px-2 py-0.5 rounded text-[10px] font-mono transition-colors ${
                showJudasZones ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30' : 'text-slate-500'
              }`}
              title="Judas Trap Killzones"
            >
              JUDAS
            </button>
            <button
              onClick={() => setShowKronos(!showKronos)}
              className={`px-2 py-0.5 rounded text-[10px] font-mono transition-colors flex items-center gap-1 ${
                showKronos
                  ? 'bg-indigo-500/30 text-indigo-300 border border-indigo-500/50 shadow-sm shadow-indigo-500/20'
                  : 'text-slate-500 hover:text-slate-300'
              }`}
              title="Kronos Neural Probabilistic Forecast Cone"
            >
              <Sparkles size={11} className={showKronos ? 'text-indigo-400 animate-pulse' : ''} />
              <span>KRONOS</span>
            </button>
          </div>

          {showKronos && kronosData?.sky_derived_metrics && (
            <div className="hidden lg:flex items-center gap-2 px-2 py-0.5 bg-indigo-950/40 border border-indigo-500/30 rounded text-[10px] font-mono text-indigo-300 animate-in fade-in duration-200">
              <span>Bias: <strong className={kronosData.sky_derived_metrics.directional_bias === 'BULLISH' ? 'text-emerald-400' : (kronosData.sky_derived_metrics.directional_bias === 'BEARISH' ? 'text-rose-400' : 'text-slate-300')}>{kronosData.sky_derived_metrics.directional_bias || 'NEUTRAL'}</strong></span>
              <span>Exp: <strong>{((Number(kronosData.sky_derived_metrics.expected_return_pct) || 0) * 100).toFixed(2)}%</strong></span>
              <span>Consensus: <strong>{((Number(kronosData.sky_derived_metrics.directional_consensus) || 0) * 100).toFixed(0)}%</strong></span>
            </div>
          )}

          <div className="h-4 w-[1px] bg-[#2a2e39]" />

          {/* Snapshot Button */}
          <button
            onClick={handleTakeSnapshot}
            className="p-1.5 text-slate-400 hover:text-white hover:bg-[#242936] rounded transition-colors"
            title="Take Chart Snapshot (PNG)"
          >
            <Camera size={14} />
          </button>

          {/* Dev HUD Toggle */}
          <button
            onClick={() => setShowDebugHUD(!showDebugHUD)}
            className={`px-1.5 py-1 rounded font-mono text-[10px] flex items-center gap-1 transition-colors ${
              showDebugHUD ? 'bg-purple-500/20 text-purple-300 border border-purple-500/40' : 'text-slate-500 hover:text-slate-300'
            }`}
            title="Dev Diagnostic HUD (D)"
          >
            <Activity size={12} />
            <span>HUD</span>
          </button>

          {/* Fullscreen Button */}
          <button
            onClick={toggleFullscreen}
            className="p-1.5 text-slate-400 hover:text-white hover:bg-[#242936] rounded transition-colors"
            title={isFullscreen ? 'Exit Fullscreen' : 'Fullscreen'}
          >
            {isFullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
          </button>
        </div>
      </div>

      {/* Diagnostic Telemetry Bar */}
      {showDebugHUD && (
        <div className="flex items-center justify-between px-3 py-1 bg-[#090d16] border-b border-purple-500/20 text-[10px] font-mono text-purple-300">
          <div className="flex items-center gap-4">
            <span>FPS: <strong className="text-emerald-400">{fps}</strong></span>
            <span>Chart Updates/s: <strong className="text-cyan-400">{updatesPerSec}</strong></span>
            <span>Renders: <strong className="text-slate-200">{renderCountRef.current}</strong></span>
            <span>WebSocket: <strong className="text-emerald-400">CONNECTED</strong></span>
          </div>
          <span className="text-slate-500 text-[9px]">Zero-Shake Realtime Engine Active</span>
        </div>
      )}

      {/* 2. Main Chart Area + Left Tool Rail */}
      <div className="relative flex flex-row flex-1 w-full overflow-hidden">
        {/* Left Vertical Tool Rail (TradingView Style) */}
        <div className="flex flex-col items-center justify-between py-2 px-1 bg-[#181c27] border-r border-[#2a2e39] z-20 gap-1 select-none">
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
                    setPreviewPoint(null);
                  }}
                  className={`p-2 rounded transition-all group relative ${
                    isSelected
                      ? 'bg-[#2962ff] text-white shadow-md shadow-blue-500/30'
                      : 'text-slate-400 hover:text-slate-100 hover:bg-[#242936]'
                  }`}
                  title={tool.label}
                >
                  <IconComponent size={15} />
                  <span className="absolute left-full ml-2 px-2 py-1 bg-[#1e222d] border border-[#2a2e39] text-[10px] font-mono text-slate-200 rounded whitespace-nowrap opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity z-50 shadow-xl">
                    {tool.label}
                  </span>
                </button>
              );
            })}

            <div className="w-4 h-[1px] bg-[#2a2e39] my-1" />

            {/* Magnet Mode Toggle */}
            <button
              onClick={() => setMagnetMode(!magnetMode)}
              className={`p-2 rounded transition-all group relative ${
                magnetMode
                  ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                  : 'text-slate-500 hover:text-slate-300 hover:bg-[#242936]'
              }`}
              title={magnetMode ? 'Magnet Mode: ON (Snap to High/Low)' : 'Magnet Mode: OFF'}
            >
              <Magnet size={15} />
              <span className="absolute left-full ml-2 px-2 py-1 bg-[#1e222d] border border-[#2a2e39] text-[10px] font-mono text-slate-200 rounded whitespace-nowrap opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity z-50 shadow-xl">
                {magnetMode ? 'Magnet Snap: Active' : 'Magnet Snap: Off'}
              </span>
            </button>
          </div>

          {/* Delete All Drawings Button */}
          {drawings.length > 0 && (
            <div className="flex flex-col items-center border-t border-[#2a2e39] pt-1">
              <button
                onClick={handleClearDrawings}
                className="p-2 rounded text-rose-400 hover:bg-rose-500/20 hover:text-rose-300 transition-colors relative group"
                title={`Clear drawings (${drawings.length})`}
              >
                <Trash2 size={15} />
                <span className="absolute left-full ml-2 px-2 py-1 bg-[#1e222d] border border-rose-500/30 text-[10px] font-mono text-rose-300 rounded whitespace-nowrap opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity z-50 shadow-xl">
                  Clear {drawings.length} Drawings
                </span>
              </button>
            </div>
          )}
        </div>

        {/* Chart Viewport Canvas & Legend Overlays */}
        <div className={`relative flex-1 ${isFullscreen ? 'h-[calc(100vh-140px)]' : 'h-[460px] min-h-[460px]'}`}>
          {/* Top-Left TradingView Dynamic Legend */}
          <div className="absolute top-2 left-3 z-10 pointer-events-none font-sans text-xs select-none">
            <div className="flex items-center gap-2 font-mono">
              <span className="font-bold text-slate-100 text-sm">{symbol}</span>
              <span className="text-slate-400 text-xs">· {timeframe.toUpperCase()} · INSTITUTIONAL PERP</span>
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
            </div>

            {/* OHLC Values */}
            <div className="flex items-center gap-3 font-mono text-[11px] mt-0.5">
              {crosshairData ? (
                <>
                  <span className="text-slate-400">O <strong className="text-slate-200">${Number(crosshairData.open || 0).toFixed(2)}</strong></span>
                  <span className="text-slate-400">H <strong className="text-slate-200">${Number(crosshairData.high || 0).toFixed(2)}</strong></span>
                  <span className="text-slate-400">L <strong className="text-slate-200">${Number(crosshairData.low || 0).toFixed(2)}</strong></span>
                  <span className="text-slate-400">C <strong className="text-slate-200">${Number(crosshairData.close || 0).toFixed(2)}</strong></span>
                  <span className={(crosshairData.changePct || 0) >= 0 ? 'text-[#089981] font-bold' : 'text-[#f23645] font-bold'}>
                    {(crosshairData.changePct || 0) >= 0 ? '+' : ''}{Number(crosshairData.changePct || 0).toFixed(2)}%
                  </span>
                </>
              ) : (
                <>
                  <span className="text-slate-400">O <strong className="text-slate-200">${Number(openPrice || 0).toFixed(2)}</strong></span>
                  <span className="text-slate-400">H <strong className="text-slate-200">${Number(highPrice || 0).toFixed(2)}</strong></span>
                  <span className="text-slate-400">L <strong className="text-slate-200">${Number(lowPrice || 0).toFixed(2)}</strong></span>
                  <span className="text-slate-400">C <strong className="text-slate-200">${Number(lastPrice || 0).toFixed(2)}</strong></span>
                  <span className={isUp ? 'text-[#089981] font-bold' : 'text-[#f23645] font-bold'}>
                    {isUp ? '+' : ''}{Number(priceChangePct || 0).toFixed(2)}%
                  </span>
                </>
              )}
            </div>
          </div>

          {/* Candle Close Countdown Badge (Top Right) */}
          <div className="absolute top-2 right-16 z-10 flex items-center gap-1.5 px-2 py-0.5 bg-[#181c27]/90 border border-[#2a2e39] rounded text-[11px] font-mono text-slate-300 pointer-events-none">
            <Clock size={12} className="text-sky-400" />
            <span>Close: <strong className="text-emerald-400">{countdown}</strong></span>
          </div>

          {/* Chart Target */}
          <div ref={chartContainerRef} className="absolute inset-0 w-full h-full" />

          {/* Mathematical Drawing Overlay Canvas */}
          <canvas
            ref={drawingCanvasRef}
            onMouseDown={handleCanvasMouseDown}
            onMouseMove={handleCanvasMouseMove}
            onMouseLeave={handleCanvasMouseLeave}
            className={`absolute inset-0 w-full h-full ${
              activeTool !== 'CURSOR' ? 'pointer-events-auto cursor-crosshair' : 'pointer-events-none cursor-default'
            }`}
          />

          {/* "Go to Latest" Floating Button */}
          {isHistoricalPan && (
            <button
              onClick={() => {
                chartRef.current?.timeScale().scrollToRealTime();
                setIsHistoricalPan(false);
                setUnreadTicks(0);
              }}
              className="absolute bottom-6 right-16 z-20 flex items-center gap-2 px-3 py-1.5 bg-[#2962ff] hover:bg-[#1e4bd8] text-white text-xs font-mono font-semibold rounded-full shadow-lg shadow-blue-500/25 border border-blue-400 transition-all transform hover:scale-105 animate-pulse"
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

          {/* Active Drawing Tool Step Instruction Banner */}
          {activeTool !== 'CURSOR' && (
            <div className="absolute top-3 left-1/2 -translate-x-1/2 z-20 flex items-center gap-2 px-3 py-1 bg-[#181c27]/95 border border-[#2962ff]/50 rounded-full text-xs font-mono text-sky-300 shadow-xl backdrop-blur-md">
              <Sparkles size={13} className="animate-spin text-sky-400" />
              <span>
                {activeDrawingPoints.length === 0
                  ? `Click on chart to set START point for ${activeTool.replace(/_/g, ' ')}`
                  : `Move cursor & click to set END point for ${activeTool.replace(/_/g, ' ')}`}
              </span>
              <button
                onClick={() => {
                  setActiveTool('CURSOR');
                  setActiveDrawingPoints([]);
                  setPreviewPoint(null);
                }}
                className="ml-2 px-1.5 py-0.5 bg-rose-500/20 text-rose-400 rounded text-[10px] hover:bg-rose-500/40"
              >
                Cancel
              </button>
            </div>
          )}
        </div>
      </div>

      {/* 3. Bottom Time Range & Scale Bar (TradingView Style) */}
      <div className="flex items-center justify-between px-3 py-1 bg-[#181c27] border-t border-[#2a2e39] text-[11px] font-mono text-slate-400 z-10 select-none">
        {/* Left: Time Range Presets */}
        <div className="flex items-center gap-1">
          {TIME_RANGES.map((r) => (
            <button
              key={r}
              onClick={() => handleSetTimeRange(r)}
              className={`px-2 py-0.5 rounded transition-colors ${
                activeRange === r
                  ? 'text-white font-bold bg-[#242936]'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-[#242936]/50'
              }`}
            >
              {r}
            </button>
          ))}
        </div>

        {/* Right: Timezone Clock + Auto/Log/Percent indicators */}
        <div className="flex items-center gap-3">
          <span className="text-slate-500">{currentTimeStr} (UTC+6)</span>
          <div className="flex items-center gap-1 bg-[#131722] border border-[#2a2e39] rounded px-1.5 py-0.5 text-[10px]">
            <span className="text-emerald-400 font-bold">auto</span>
            <span className="text-slate-600">|</span>
            <span className="text-slate-400">log</span>
            <span className="text-slate-600">|</span>
            <span className="text-slate-400">%</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export const TradingViewChart = memo(TradingViewChartComponent);
