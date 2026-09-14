import React, { useState, useEffect, useCallback } from 'react';
import { Header } from './components/Header';
import { TradingViewChart } from './core/engine/TradingViewChart';
import { CVDSubChart } from './components/CVDSubChart';
import { InstitutionalAlphaHUD } from './components/InstitutionalAlphaHUD';
import { OBIFlowMeter } from './components/OBIFlowMeter';
import { SKYIntelligenceHUD } from './components/SKYIntelligenceHUD';
import { WatchlistVirtualTracker } from './components/WatchlistVirtualTracker';
import { OrderBookVisualizer } from './components/OrderBookVisualizer';
import { RiskFirstOrderDesk } from './components/RiskFirstOrderDesk';
import { MTFPanel } from './components/MTFPanel';
import { SMCScanPanel } from './components/SMCScanPanel';
import { PaperTradingPanel } from './components/PaperTradingPanel';
import { DedicatedPaperTradingDesk } from './components/DedicatedPaperTradingDesk';
import { GeminiDeskCopilot } from './components/GeminiDeskCopilot';
import { SKYIntelligencePanel } from './components/SKYIntelligencePanel';
import { HedgeFundBrainSuite } from './components/HedgeFundBrainSuite';
import { AssetDossierDock } from './components/AssetDossierDock';
import { MicrostructurePanel } from './components/MicrostructurePanel';
import { MacroNetworkRadar } from './components/MacroNetworkRadar';
import { GeneticStrategyLab } from './components/GeneticStrategyLab';
import { AutonomousAuditorHUD } from './components/AutonomousAuditorHUD';
import { ShadowBurnInHUD } from './components/ShadowBurnInHUD';
import { ResearchIngestLab } from './components/ResearchIngestLab';
import { CollectiveCoreDashboard } from './components/CollectiveCoreDashboard';
import { VolatilitySurfaceDesk } from './components/VolatilitySurfaceDesk';
import { ArbitrageRadar } from './components/ArbitrageRadar';
import { MBODepthTerminal } from './components/MBODepthTerminal';
import { LiveLaunchpadDesk } from './components/LiveLaunchpadDesk';
import { InstitutionalMasterTerminal } from './components/terminal/InstitutionalMasterTerminal';
import { ToastContainer } from './components/ToastContainer';
import { marketProvider, TickerData } from './data/providers/marketProvider';
import {
  SupportedTimeframe,
  OHLCVCandle,
  IndicatorPoint,
  FVGItem,
  OrderBlockItem,
  SetupSuggestion,
  PaperTrade,
  RiskConfig,
  DeskBriefResponse,
  ToastMessage,
  SKYIntelligenceResponse,
  InstitutionalAlphaResponse,
  CVDSeriesData,
  OBIData,
} from './types';
import { api, ApiError } from './services/api';
import { notificationService } from './services/notificationService';
import {
  Layers,
  ShieldCheck,
  Cpu,
  BarChart2,
  Scale,
  Sparkles,
  Zap,
  Brain,
  Server,
  Activity,
} from 'lucide-react';

export const App: React.FC = () => {
  // Navigation & Market Context State
  const [symbol, setSymbol] = useState<string>('BTCUSDT');
  const [timeframe, setTimeframe] = useState<SupportedTimeframe>('15m');

  // Market Telemetry State
  const [candles, setCandles] = useState<OHLCVCandle[]>([]);
  const [ema, setEMA] = useState<IndicatorPoint[]>([]);
  const [rsi, setRSI] = useState<IndicatorPoint[]>([]);
  const [fvgs, setFVGs] = useState<FVGItem[]>([]);
  const [orderBlocks, setOrderBlocks] = useState<OrderBlockItem[]>([]);
  const [setups, setSetups] = useState<SetupSuggestion[]>([]);
  const [stats, setStats] = useState({
    lastPrice: 0,
    highPrice: 0,
    lowPrice: 0,
    trend: 'Consolidation / Range',
  });

  // Paper Trading & Risk State
  const [positions, setPositions] = useState<PaperTrade[]>([]);
  const [riskConfig, setRiskConfig] = useState<RiskConfig | undefined>();
  const [selectedSetup, setSelectedSetup] = useState<SetupSuggestion | null>(null);

  // High-Velocity Real-time Ticks State
  const [liveCandle, setLiveCandle] = useState<OHLCVCandle | null>(null);

  // Quantitative Intelligence State (SKY & Institutional Alpha)
  const [skyData, setSkyData] = useState<SKYIntelligenceResponse | null>(null);
  const [institutionalAlpha, setInstitutionalAlpha] = useState<InstitutionalAlphaResponse | null>(null);
  const [cvdData, setCvdData] = useState<CVDSeriesData | null>(null);
  const [obiData, setObiData] = useState<OBIData | null>(null);

  // Gemini Intelligence State
  const [brief, setBrief] = useState<DeskBriefResponse | null>(null);
  const [loadingBrief, setLoadingBrief] = useState<boolean>(false);

  // Main Screen View Switcher: Terminal Cockpit vs Master Cockpit vs Dedicated Shadow Paper Trading Desk
  const [activeMainView, setActiveMainView] = useState<'TERMINAL' | 'MASTER_COCKPIT' | 'PAPER_DESK'>('MASTER_COCKPIT');

  // Tab State for Single-Screen Compact Cockpit
  const [activeRightTab, setActiveRightTab] = useState<'ORDER_DESK' | 'ORDER_BOOK' | 'PAPER' | 'AI_DESK'>('ORDER_DESK');
  const [activeBottomTab, setActiveBottomTab] = useState<'DOSSIER' | 'HEDGE_FUND' | 'QUANT' | 'MTF_SMC' | 'FRONTIERS' | 'RESEARCH_LAB' | 'COLLECTIVE' | 'VOLATILITY_SURFACE' | 'ARBITRAGE' | 'MBO_DEPTH' | 'LIVE_LAUNCHPAD'>('DOSSIER');
  const [activeFrontierTab, setActiveFrontierTab] = useState<'MICROSTRUCTURE' | 'MACRO' | 'GENETIC' | 'AUDITOR' | 'BURN_IN' | 'ARBITRAGE_RADAR' | 'MBO_DEPTH'>('MICROSTRUCTURE');
  const [activeHudMode, setActiveHudMode] = useState<'INSTITUTIONAL' | 'SKY' | 'BOTH'>('INSTITUTIONAL');

  // Notifications State
  const [notificationsEnabled, setNotificationsEnabled] = useState<boolean>(
    notificationService.isEnabled()
  );

  // General Loading & UI State
  const [loadingMarket, setLoadingMarket] = useState<boolean>(false);
  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  // Toast notification helper
  const addToast = useCallback((type: ToastMessage['type'], title: string, message: string) => {
    const id = Math.random().toString(36).substring(2, 9);
    setToasts((prev) => [...prev, { id, type, title, message }]);

    // Auto-dismiss after 6 seconds
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 6000);
  }, []);

  const dismissToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  // Toggle Push Notifications
  const handleToggleNotifications = async () => {
    if (notificationsEnabled) {
      notificationService.setEnabled(false);
      setNotificationsEnabled(false);
      addToast('info', 'Push Notifications Muted', 'Alerts disabled for this session.');
    } else {
      const granted = await notificationService.requestPermission();
      if (granted) {
        setNotificationsEnabled(true);
        addToast('success', 'Push Notifications Enabled', 'Instant alerts active for Risk Gate & AI Briefs.');
      } else {
        setNotificationsEnabled(false);
        addToast(
          'warning',
          'Notification Permission Required',
          'Please enable browser notifications in your site permissions.'
        );
      }
    }
  };

  // 1. Initial Market Data & Historical Candles Loading (Initial Mount / Symbol / TF Change)
  const fetchInitialMarketData = useCallback(async () => {
    setLoadingMarket(true);
    try {
      const [candlesRes, mtfRes, scanRes, skyRes, alphaRes, cvdRes, obiRes] = await Promise.all([
        api.getCandles(symbol, timeframe, 1000),
        api.getMTF(symbol, timeframe, 'ema,rsi'),
        api.getSMCScan(symbol, timeframe, 500),
        api.getSKYIntelligence(symbol, timeframe, 500).catch(() => null),
        api.getInstitutionalAlpha(symbol, timeframe, 500).catch(() => null),
        api.getInstitutionalCVD(symbol, timeframe, 1000).catch(() => null),
        api.getOrderBookImbalance(symbol).catch(() => null),
      ]);

      setCandles(candlesRes?.candles || []);
      setEMA(mtfRes?.indicators?.ema || []);
      setRSI(mtfRes?.indicators?.rsi || []);
      setFVGs(scanRes?.fvg || []);
      setOrderBlocks(scanRes?.order_blocks || []);
      setSetups(scanRes?.setup_suggestions || []);
      if (skyRes) setSkyData(skyRes);
      if (alphaRes) setInstitutionalAlpha(alphaRes);
      if (cvdRes) setCvdData(cvdRes);
      if (obiRes) setObiData(obiRes);

      if (scanRes?.stats) {
        setStats({
          lastPrice: scanRes.stats.lastPrice,
          highPrice: scanRes.stats.highPrice,
          lowPrice: scanRes.stats.lowPrice,
          trend: scanRes.stats.trend,
        });
      } else if (candlesRes.candles && candlesRes.candles.length > 0) {
        const lastBar = candlesRes.candles[candlesRes.candles.length - 1];
        const recentCandles = candlesRes.candles.slice(-50);
        setStats((prev) => ({
          ...prev,
          lastPrice: lastBar[4],
          highPrice: Math.max(...recentCandles.map((c) => c[2])),
          lowPrice: Math.min(...recentCandles.map((c) => c[3])),
        }));
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to fetch market data';
      if (err instanceof ApiError && err.statusCode === 429) {
        addToast('warning', 'Rate Limit Exceeded (429)', 'Requests are rate-limited to 60 req/min.');
      } else {
        addToast('error', 'Market Data Error', msg);
      }
    } finally {
      setLoadingMarket(false);
    }
  }, [symbol, timeframe, addToast]);

  // 1B. Silent Background Analytics Polling (Every 30s — Zero Chart Jitter / Zero Loading Flash)
  const fetchBackgroundAnalytics = useCallback(async () => {
    try {
      const [scanRes, skyRes, alphaRes, cvdRes, obiRes] = await Promise.all([
        api.getSMCScan(symbol, timeframe, 500).catch(() => null),
        api.getSKYIntelligence(symbol, timeframe, 500).catch(() => null),
        api.getInstitutionalAlpha(symbol, timeframe, 500).catch(() => null),
        api.getInstitutionalCVD(symbol, timeframe, 1000).catch(() => null),
        api.getOrderBookImbalance(symbol).catch(() => null),
      ]);

      if (scanRes) {
        setFVGs(scanRes.fvg || []);
        setOrderBlocks(scanRes.order_blocks || []);
        setSetups(scanRes.setup_suggestions || []);
      }
      if (skyRes) setSkyData(skyRes);
      if (alphaRes) setInstitutionalAlpha(alphaRes);
      if (cvdRes) setCvdData(cvdRes);
      if (obiRes) setObiData(obiRes);
    } catch (err: unknown) {
      console.warn('Silent background analytics update skipped:', err);
    }
  }, [symbol, timeframe]);

  // 2. Fetch Paper Trading Positions
  const fetchPositions = useCallback(async () => {
    try {
      const [posRes, configRes] = await Promise.all([
        api.getPositions(),
        api.getRiskConfig(),
      ]);
      setPositions(posRes.positions || []);
      if (configRes.config) setRiskConfig(configRes.config);
    } catch (err: unknown) {
      console.warn('Failed to load paper positions:', err);
    }
  }, []);

  // 3. Fetch Gemini Market Brief
  const fetchDeskBrief = useCallback(async () => {
    setLoadingBrief(true);
    try {
      const res = await api.getDeskBrief(symbol, timeframe);
      setBrief(res);
      if (notificationsEnabled) {
        notificationService.notifyMarketBriefAlert(symbol, res.bias, res.executiveSummary);
      }
    } catch (err: unknown) {
      console.warn('Gemini brief fetch error:', err);
    } finally {
      setLoadingBrief(false);
    }
  }, [symbol, timeframe, notificationsEnabled]);

  // 4. Handle Desk Copilot Question
  const handleAskDesk = async (question: string) => {
    const res = await api.askDesk(question, { symbol, timeframe });
    return res.answer;
  };

  // 5. Handle Paper Trade Execution
  const handlePlaceTrade = async (trade: {
    symbol: string;
    side: 'BUY' | 'SELL';
    entryPrice: number;
    sl: number;
    tp: number;
    size: number;
  }): Promise<void> => {
    try {
      await api.placePaperTrade({
        symbol: trade.symbol,
        side: trade.side,
        entryPrice: trade.entryPrice,
        sl: trade.sl,
        tp: trade.tp,
        size: trade.size,
      });

      addToast(
        'success',
        'Simulated Order Filled',
        `Opened ${trade.side} ${trade.size} ${trade.symbol} @ $${trade.entryPrice.toFixed(2)}`
      );
      fetchPositions();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Trade execution failed';
      addToast('error', 'Execution Error', msg);
      if (notificationsEnabled) {
        notificationService.notifyRiskGateAlert('Trade Execution Failed', msg);
      }
    }
  };

  // 5.1 Handle Close Paper Practice Position
  const handleClosePosition = async (positionId: string): Promise<void> => {
    try {
      await api.closePaperPosition(positionId);
      addToast('info', 'Position Closed', `Closed paper position #${positionId}`);
      fetchPositions();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to close position';
      addToast('error', 'Closure Error', msg);
    }
  };

  // 6. Handle Risk-First Order Desk Execution
  const handlePlaceRiskOrder = async (order: {
    symbol: string;
    side: 'BUY' | 'SELL';
    type: 'MARKET' | 'LIMIT';
    price?: number;
    amount: number;
    stopLoss?: number;
    takeProfit?: number;
  }) => {
    try {
      const entry = order.type === 'LIMIT' && order.price ? order.price : stats.lastPrice;
      await api.placePaperTrade({
        symbol: order.symbol,
        side: order.side,
        entryPrice: entry,
        sl: order.stopLoss || 0,
        tp: order.takeProfit || 0,
        size: order.amount,
      });

      addToast(
        'success',
        `${order.type} Order Routed`,
        `Executed ${order.side} ${order.amount.toFixed(4)} ${order.symbol} @ $${entry.toFixed(2)}`
      );
      fetchPositions();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Order placement failed';
      addToast('error', 'Order Routing Error', msg);
    }
  };

  // Initialize Data Ingestion on Mount & Parameter Change
  useEffect(() => {
    fetchInitialMarketData();
    fetchPositions();
    fetchDeskBrief();
  }, [symbol, timeframe]);

  // Synchronize Live Watchlist Ticks directly into Header and Stats
  const handleWatchlistPriceTick = useCallback((tickSymbol: string, price: number, high?: number, low?: number) => {
    const cleanActive = symbol.toUpperCase().replace(/[^A-Z0-9]/g, '');
    const cleanTick = tickSymbol.toUpperCase().replace(/[^A-Z0-9]/g, '');
    if (cleanActive === cleanTick && price > 0) {
      setStats((prev) => ({
        ...prev,
        lastPrice: price,
        highPrice: high && high > 0 ? Math.max(prev.highPrice, high) : prev.highPrice,
        lowPrice: low && low > 0 ? (prev.lowPrice === 0 ? low : Math.min(prev.lowPrice, low)) : prev.lowPrice,
      }));
    }
  }, [symbol]);

  // Sub-Second Real-Time Ticker Stream Synchronization
  useEffect(() => {
    const unsubTicker = marketProvider.subscribeTicker(symbol, (ticker: TickerData) => {
      if (ticker.lastPrice > 0) {
        setStats((prev) => ({
          ...prev,
          lastPrice: ticker.lastPrice,
          highPrice: ticker.high24h > 0 ? ticker.high24h : prev.highPrice,
          lowPrice: ticker.low24h > 0 ? ticker.low24h : prev.lowPrice,
        }));
      }
    });

    return () => unsubTicker();
  }, [symbol]);

  // High-Frequency Real-Time WebSocket Aggregation (Incremental Series Updates)
  useEffect(() => {
    const unsub = marketProvider.subscribeRealtimeCandles(symbol, timeframe, (candle: OHLCVCandle) => {
      setLiveCandle(candle);
      setStats((prev) => ({
        ...prev,
        lastPrice: candle[4],
        highPrice: Math.max(prev.highPrice, candle[2]),
        lowPrice: prev.lowPrice === 0 ? candle[3] : Math.min(prev.lowPrice, candle[3]),
      }));
    });

    return () => unsub();
  }, [symbol, timeframe]);

  // Silent 30-Second Background Analytics Polling (Zero Chart Flickering / Zero Screen Jump)
  useEffect(() => {
    const interval = setInterval(() => {
      fetchBackgroundAnalytics();
      fetchPositions();
    }, 30000);
    return () => clearInterval(interval);
  }, [fetchBackgroundAnalytics, fetchPositions]);

  return (
    <div className="min-h-screen bg-[#05070c] text-slate-100 flex flex-col font-sans antialiased selection:bg-sky-500/30 selection:text-sky-200">
      {/* Institutional Navigation Header */}
      <Header
        symbol={symbol}
        onSymbolChange={(newSym) => {
          setSymbol(newSym);
          setSelectedSetup(null);
        }}
        timeframe={timeframe}
        onTimeframeChange={(newTf) => {
          setTimeframe(newTf);
          setSelectedSetup(null);
        }}
        lastPrice={stats.lastPrice}
        highPrice={stats.highPrice}
        lowPrice={stats.lowPrice}
        trend={stats.trend}
        loading={loadingMarket}
        onRefresh={() => {
          fetchInitialMarketData();
          fetchPositions();
          fetchDeskBrief();
        }}
        notificationsEnabled={notificationsEnabled}
        onToggleNotifications={handleToggleNotifications}
        activeView={activeMainView}
        onViewChange={setActiveMainView}
        openPositionsCount={positions.length}
      />

      {/* Primary View Routing: Dedicated Shadow Paper Desk vs Master Cockpit vs Classic Terminal */}
      {activeMainView === 'PAPER_DESK' ? (
        <DedicatedPaperTradingDesk
          onClosePosition={handleClosePosition}
        />
      ) : activeMainView === 'MASTER_COCKPIT' ? (
        <InstitutionalMasterTerminal
          initialSymbol={symbol}
          initialTimeframe={timeframe}
          onDeployToOrderDesk={(setup) => {
            setSelectedSetup(setup);
            addToast('info', 'Setup Loaded', `Transferred ${setup.type} order to Order Desk.`);
          }}
          addToast={addToast}
        />
      ) : (
        <>
          {/* Institutional Quantitative HUD Control Bar */}
      <div className="max-w-[1920px] w-full mx-auto px-4 pt-2 space-y-1">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1 bg-[#090d16] border border-[#1e293b] rounded-lg p-0.5 text-xs font-mono">
            <button
              onClick={() => setActiveHudMode('INSTITUTIONAL')}
              className={`flex items-center gap-1.5 px-3 py-1 rounded transition-all ${
                activeHudMode === 'INSTITUTIONAL'
                  ? 'bg-sky-500 text-white font-bold shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Cpu size={13} />
              <span>Institutional Alpha HUD</span>
            </button>
            <button
              onClick={() => setActiveHudMode('SKY')}
              className={`flex items-center gap-1.5 px-3 py-1 rounded transition-all ${
                activeHudMode === 'SKY'
                  ? 'bg-sky-500 text-white font-bold shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <ShieldCheck size={13} />
              <span>SKY Quant Radar</span>
            </button>
            <button
              onClick={() => setActiveHudMode('BOTH')}
              className={`flex items-center gap-1.5 px-3 py-1 rounded transition-all ${
                activeHudMode === 'BOTH'
                  ? 'bg-sky-500 text-white font-bold shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Layers size={13} />
              <span>Expand Both</span>
            </button>
          </div>
        </div>

        {/* Rendered HUD Based on Mode */}
        {(activeHudMode === 'INSTITUTIONAL' || activeHudMode === 'BOTH') && (
          <InstitutionalAlphaHUD
            alphaData={institutionalAlpha}
            loading={loadingMarket}
          />
        )}
        {(activeHudMode === 'SKY' || activeHudMode === 'BOTH') && (
          <SKYIntelligenceHUD
            data={skyData}
            loading={loadingMarket}
            onRefresh={fetchBackgroundAnalytics}
          />
        )}
      </div>

      {/* Main Multi-Panel Terminal Layout */}
      <main className="flex-1 p-4 max-w-[1920px] w-full mx-auto grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* Left Column (2 cols): Multi-Symbol Watchlist Tracker */}
        <div className="lg:col-span-2 hidden xl:flex flex-col gap-4 min-h-[500px]">
          <WatchlistVirtualTracker
            currentSymbol={symbol}
            onSelectSymbol={(sym) => {
              setSymbol(sym);
              setSelectedSetup(null);
            }}
            onPriceTick={handleWatchlistPriceTick}
          />
        </div>

        {/* Center Column (7 cols): TradingView Chart, CVD Sub-Chart & Lower Quant Tabs */}
        <div className="lg:col-span-7 xl:col-span-7 flex flex-col gap-3">
          {/* Flagship TradingView Lightweight Charts Engine + CVD Sub-Chart */}
          <div className="flex flex-col rounded-lg overflow-hidden border border-[#1e293b] shadow-2xl bg-[#080b11]">
            <TradingViewChart
              symbol={symbol}
              timeframe={timeframe}
              candles={candles}
              fvgs={fvgs}
              orderBlocks={orderBlocks}
              skySetups={skyData?.setups}
              liveCandle={liveCandle}
              onDeploySetup={(setup) => setSelectedSetup(setup)}
              onTimeframeChange={(newTf) => setTimeframe(newTf)}
              loading={loadingMarket}
            />
            <CVDSubChart
              candles={candles}
              cvdData={cvdData}
              height={120}
            />
          </div>

          {/* Lower Center Intelligence Tabs */}
          <div className="flex flex-col rounded-lg border border-[#1e293b] bg-[#080b11] overflow-hidden">
            <div className="flex items-center justify-between px-3 py-1.5 bg-[#0d121d] border-b border-[#1e293b]">
              <div className="flex flex-wrap items-center gap-1 text-xs font-mono">
                <button
                  onClick={() => setActiveBottomTab('DOSSIER')}
                  className={`flex items-center gap-1.5 px-3 py-1 rounded transition-colors ${
                    activeBottomTab === 'DOSSIER'
                      ? 'bg-amber-500 text-black font-bold shadow-md shadow-amber-500/30'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
                  }`}
                >
                  <Sparkles size={13} className={activeBottomTab === 'DOSSIER' ? 'text-black' : 'text-amber-400'} />
                  <span>8-Pillar Asset Dossier (BTC/ETH/GOLD)</span>
                </button>
                <button
                  onClick={() => setActiveBottomTab('HEDGE_FUND')}
                  className={`flex items-center gap-1.5 px-3 py-1 rounded transition-colors ${
                    activeBottomTab === 'HEDGE_FUND'
                      ? 'bg-purple-600 text-white font-bold shadow-md shadow-purple-600/30'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
                  }`}
                >
                  <Scale size={13} className="text-purple-300" />
                  <span>Hedge-Fund Brain (6 Engines)</span>
                </button>
                <button
                  onClick={() => setActiveBottomTab('QUANT')}
                  className={`flex items-center gap-1.5 px-3 py-1 rounded transition-colors ${
                    activeBottomTab === 'QUANT'
                      ? 'bg-sky-500 text-white font-bold shadow-md shadow-sky-500/30'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
                  }`}
                >
                  <Cpu size={13} />
                  <span>SKY 17-Phase Intelligence</span>
                </button>
                <button
                  onClick={() => setActiveBottomTab('MTF_SMC')}
                  className={`flex items-center gap-1.5 px-3 py-1 rounded transition-colors ${
                    activeBottomTab === 'MTF_SMC'
                      ? 'bg-sky-500 text-white font-bold shadow-md shadow-sky-500/30'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
                  }`}
                >
                  <BarChart2 size={13} />
                  <span>MTF Confluence & SMC Scans</span>
                </button>
                <button
                  onClick={() => setActiveBottomTab('FRONTIERS')}
                  className={`flex items-center gap-1.5 px-3 py-1 rounded transition-colors ${
                    activeBottomTab === 'FRONTIERS'
                      ? 'bg-emerald-500 text-slate-950 font-bold shadow-md shadow-emerald-500/30'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
                  }`}
                >
                  <Zap size={13} className={activeBottomTab === 'FRONTIERS' ? 'text-slate-950' : 'text-emerald-400'} />
                  <span>Frontiers Suite</span>
                </button>
                <button
                  onClick={() => setActiveBottomTab('RESEARCH_LAB')}
                  className={`flex items-center gap-1.5 px-3 py-1 rounded transition-colors ${
                    activeBottomTab === 'RESEARCH_LAB'
                      ? 'bg-gradient-to-r from-indigo-500 to-purple-600 text-white font-bold shadow-md shadow-indigo-500/30'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
                  }`}
                >
                  <Brain size={13} className={activeBottomTab === 'RESEARCH_LAB' ? 'text-white animate-pulse' : 'text-indigo-400'} />
                  <span>🧠 Research Lab</span>
                </button>
                <button
                  onClick={() => setActiveBottomTab('COLLECTIVE')}
                  className={`flex items-center gap-1.5 px-3 py-1 rounded transition-colors ${
                    activeBottomTab === 'COLLECTIVE'
                      ? 'bg-gradient-to-r from-emerald-500 to-teal-600 text-white font-bold shadow-md shadow-emerald-500/30'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
                  }`}
                >
                  <Server size={13} className={activeBottomTab === 'COLLECTIVE' ? 'text-white animate-pulse' : 'text-emerald-400'} />
                  <span>🌐 Collective Core</span>
                </button>
                <button
                  onClick={() => setActiveBottomTab('VOLATILITY_SURFACE')}
                  className={`flex items-center gap-1.5 px-3 py-1 rounded transition-colors ${
                    activeBottomTab === 'VOLATILITY_SURFACE'
                      ? 'bg-gradient-to-r from-amber-500 to-orange-600 text-white font-bold shadow-md shadow-amber-500/30'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
                  }`}
                >
                  <Activity size={13} className={activeBottomTab === 'VOLATILITY_SURFACE' ? 'text-white animate-pulse' : 'text-amber-400'} />
                  <span>⚡ Volatility Surface</span>
                </button>
                <button
                  onClick={() => setActiveBottomTab('ARBITRAGE')}
                  className={`flex items-center gap-1.5 px-3 py-1 rounded transition-colors ${
                    activeBottomTab === 'ARBITRAGE'
                      ? 'bg-gradient-to-r from-amber-500 to-yellow-600 text-slate-950 font-bold shadow-md shadow-amber-500/30'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
                  }`}
                >
                  <Scale size={13} className={activeBottomTab === 'ARBITRAGE' ? 'text-slate-950' : 'text-amber-400'} />
                  <span>⚖️ Arbitrage Radar</span>
                </button>
                <button
                  onClick={() => setActiveBottomTab('MBO_DEPTH')}
                  className={`flex items-center gap-1.5 px-3 py-1 rounded transition-colors ${
                    activeBottomTab === 'MBO_DEPTH'
                      ? 'bg-gradient-to-r from-cyan-500 to-blue-600 text-white font-bold shadow-md shadow-cyan-500/30'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
                  }`}
                >
                  <Layers size={13} className={activeBottomTab === 'MBO_DEPTH' ? 'text-white' : 'text-cyan-400'} />
                  <span>🌊 L3 MBO Depth</span>
                </button>
                <button
                  onClick={() => setActiveBottomTab('LIVE_LAUNCHPAD')}
                  className={`flex items-center gap-1.5 px-3 py-1 rounded transition-colors ${
                    activeBottomTab === 'LIVE_LAUNCHPAD'
                      ? 'bg-gradient-to-r from-emerald-600 via-teal-600 to-cyan-600 text-white font-bold shadow-md shadow-emerald-500/30'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
                  }`}
                >
                  <ShieldCheck size={13} className={activeBottomTab === 'LIVE_LAUNCHPAD' ? 'text-white animate-pulse' : 'text-emerald-400'} />
                  <span>🛡️ Live Launchpad</span>
                </button>
              </div>
            </div>

            <div className="p-3">
              {activeBottomTab === 'DOSSIER' ? (
                <AssetDossierDock
                  currentSymbol={symbol}
                  onSelectSymbol={(sym) => {
                    setSymbol(sym);
                    setSelectedSetup(null);
                  }}
                />
              ) : activeBottomTab === 'HEDGE_FUND' ? (
                <HedgeFundBrainSuite
                  symbol={symbol}
                  timeframe={timeframe}
                  currentPrice={stats.lastPrice}
                  onDeploySetup={(setup) => setSelectedSetup(setup)}
                />
              ) : activeBottomTab === 'QUANT' ? (
                <SKYIntelligencePanel
                  data={skyData}
                  loading={loadingMarket}
                  onDeploySetup={(setup) => setSelectedSetup(setup)}
                />
              ) : activeBottomTab === 'MTF_SMC' ? (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <MTFPanel
                    symbol={symbol}
                    timeframe={timeframe}
                    lastPrice={stats.lastPrice}
                    ema={ema}
                    rsi={rsi}
                    trend={stats.trend}
                    loading={loadingMarket}
                  />
                  <SMCScanPanel
                    fvgs={fvgs}
                    orderBlocks={orderBlocks}
                    setups={setups}
                    onSelectSetup={(setup) => setSelectedSetup(setup)}
                    loading={loadingMarket}
                  />
                </div>
              ) : activeBottomTab === 'FRONTIERS' ? (
                <div className="flex flex-col gap-3">
                  {/* Frontier Sub-Tab Header */}
                  <div className="flex flex-wrap items-center gap-1.5 p-1 bg-[#090d16] border border-[#1e293b] rounded-lg text-xs font-mono">
                    <button
                      onClick={() => setActiveFrontierTab('MICROSTRUCTURE')}
                      className={`px-3 py-1 rounded transition-all ${
                        activeFrontierTab === 'MICROSTRUCTURE'
                          ? 'bg-sky-500 text-white font-bold shadow'
                          : 'text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      1. Microstructure & VPIN
                    </button>
                    <button
                      onClick={() => setActiveFrontierTab('MACRO')}
                      className={`px-3 py-1 rounded transition-all ${
                        activeFrontierTab === 'MACRO'
                          ? 'bg-amber-500 text-slate-950 font-bold shadow'
                          : 'text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      2. Macro Network & Granger
                    </button>
                    <button
                      onClick={() => setActiveFrontierTab('GENETIC')}
                      className={`px-3 py-1 rounded transition-all ${
                        activeFrontierTab === 'GENETIC'
                          ? 'bg-purple-600 text-white font-bold shadow'
                          : 'text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      3. Genetic Optimizer & WRC
                    </button>
                    <button
                      onClick={() => setActiveFrontierTab('AUDITOR')}
                      className={`px-3 py-1 rounded transition-all ${
                        activeFrontierTab === 'AUDITOR'
                          ? 'bg-emerald-500 text-slate-950 font-bold shadow'
                          : 'text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      5. 24/7 Risk Auditor & CUSUM
                    </button>
                    <button
                      onClick={() => setActiveFrontierTab('BURN_IN')}
                      className={`px-3 py-1 rounded transition-all ${
                        activeFrontierTab === 'BURN_IN'
                          ? 'bg-rose-500 text-white font-bold shadow'
                          : 'text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      6. Canary Burn-In (Phase 16)
                    </button>
                    <button
                      onClick={() => setActiveFrontierTab('ARBITRAGE_RADAR')}
                      className={`px-3 py-1 rounded transition-all ${
                        activeFrontierTab === 'ARBITRAGE_RADAR'
                          ? 'bg-amber-500 text-slate-950 font-bold shadow'
                          : 'text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      7. Arbitrage Radar (Task 20.1)
                    </button>
                    <button
                      onClick={() => setActiveFrontierTab('MBO_DEPTH')}
                      className={`px-3 py-1 rounded transition-all ${
                        activeFrontierTab === 'MBO_DEPTH'
                          ? 'bg-cyan-500 text-slate-950 font-bold shadow'
                          : 'text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      8. L3 MBO Depth (Task 20.2)
                    </button>
                  </div>

                  {/* Active Frontier Component */}
                  {activeFrontierTab === 'MICROSTRUCTURE' && (
                    <MicrostructurePanel symbol={symbol} currentPrice={stats.lastPrice} />
                  )}
                  {activeFrontierTab === 'MACRO' && <MacroNetworkRadar />}
                  {activeFrontierTab === 'GENETIC' && (
                    <GeneticStrategyLab
                      symbol={symbol}
                      timeframe={timeframe}
                      onDeployGenome={(genome) => {
                        addToast('info', 'Genome Config Loaded', `Deployed genome ${genome.genome_id} to Order Desk.`);
                      }}
                    />
                  )}
                  {activeFrontierTab === 'AUDITOR' && <AutonomousAuditorHUD />}
                  {activeFrontierTab === 'BURN_IN' && <ShadowBurnInHUD />}
                  {activeFrontierTab === 'ARBITRAGE_RADAR' && (
                    <ArbitrageRadar
                      currentSymbol={symbol}
                      onNotify={(type, title, msg) => addToast(type, title, msg)}
                    />
                  )}
                  {activeFrontierTab === 'MBO_DEPTH' && (
                    <MBODepthTerminal
                      currentSymbol={symbol}
                      onNotify={addToast}
                    />
                  )}
                </div>
              ) : activeBottomTab === 'RESEARCH_LAB' ? (
                <ResearchIngestLab
                  onNotify={addToast}
                  selectedSymbol={symbol}
                  selectedTimeframe={timeframe}
                />
              ) : activeBottomTab === 'VOLATILITY_SURFACE' ? (
                <VolatilitySurfaceDesk
                  currentSymbol={symbol}
                  onNotify={addToast}
                />
              ) : activeBottomTab === 'ARBITRAGE' ? (
                <ArbitrageRadar
                  currentSymbol={symbol}
                  onNotify={addToast}
                />
              ) : activeBottomTab === 'MBO_DEPTH' ? (
                <MBODepthTerminal
                  currentSymbol={symbol}
                  onNotify={addToast}
                />
              ) : activeBottomTab === 'LIVE_LAUNCHPAD' ? (
                <LiveLaunchpadDesk
                  onNotify={addToast}
                />
              ) : (
                <CollectiveCoreDashboard />
              )}
            </div>
          </div>
        </div>

        {/* Right Column (3 cols): Tabbed Execution & Risk Terminal */}
        <div className="lg:col-span-5 xl:col-span-3 flex flex-col gap-3">
          {/* Level-2 Order Book Imbalance & VPIN Flow Meter */}
          <OBIFlowMeter data={obiData} />

          {/* Right Column Institutional Tab Selector */}
          <div className="flex items-center justify-between p-1 bg-[#090d16] border border-[#1e293b] rounded-lg text-xs font-mono">
            <button
              onClick={() => setActiveRightTab('ORDER_DESK')}
              className={`flex-1 py-1 px-2 rounded text-center transition-all ${
                activeRightTab === 'ORDER_DESK'
                  ? 'bg-sky-500 text-white font-bold shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Order Desk
            </button>
            <button
              onClick={() => setActiveRightTab('ORDER_BOOK')}
              className={`flex-1 py-1 px-2 rounded text-center transition-all ${
                activeRightTab === 'ORDER_BOOK'
                  ? 'bg-sky-500 text-white font-bold shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              L2 Book
            </button>
            <button
              onClick={() => setActiveRightTab('PAPER')}
              className={`flex-1 py-1 px-2 rounded text-center transition-all flex items-center justify-center gap-1.5 ${
                activeRightTab === 'PAPER'
                  ? 'bg-sky-500 text-white font-bold shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <span>Positions</span>
              {positions.length > 0 && (
                <span className="px-1.5 py-0.5 bg-emerald-500 text-[#0B0E14] text-[10px] rounded-full font-bold leading-none">
                  {positions.length}
                </span>
              )}
            </button>
            <button
              onClick={() => setActiveRightTab('AI_DESK')}
              className={`flex-1 py-1 px-2 rounded text-center transition-all ${
                activeRightTab === 'AI_DESK'
                  ? 'bg-sky-500 text-white font-bold shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              AI Copilot
            </button>
          </div>

          {/* Active Tabbed Panel Display */}
          {activeRightTab === 'ORDER_DESK' && (
            <div className="rounded-lg overflow-hidden border border-[#1e293b]">
              <RiskFirstOrderDesk
                symbol={symbol}
                lastPrice={stats.lastPrice}
                selectedSetup={selectedSetup}
                onPlaceOrder={handlePlaceRiskOrder}
              />
            </div>
          )}

          {activeRightTab === 'ORDER_BOOK' && (
            <div className="rounded-lg overflow-hidden border border-[#1e293b]">
              <OrderBookVisualizer
                symbol={symbol}
                lastPrice={stats.lastPrice}
              />
            </div>
          )}

          {activeRightTab === 'PAPER' && (
            <div className="rounded-lg overflow-hidden border border-[#1e293b]">
              <PaperTradingPanel
                symbol={symbol}
                lastPrice={stats.lastPrice}
                initialEntry={selectedSetup?.entry}
                initialSL={selectedSetup?.stopLoss}
                initialTP={selectedSetup?.takeProfit}
                initialSide={selectedSetup?.type === 'LONG' ? 'BUY' : selectedSetup?.type === 'SHORT' ? 'SELL' : 'BUY'}
                positions={positions}
                riskConfig={riskConfig}
                onSubmitTrade={handlePlaceTrade}
                onRefreshPositions={fetchPositions}
                onClosePosition={handleClosePosition}
                loading={loadingMarket}
              />
            </div>
          )}

          {activeRightTab === 'AI_DESK' && (
            <div className="rounded-lg overflow-hidden border border-[#1e293b]">
              <GeminiDeskCopilot
                symbol={symbol}
                timeframe={timeframe}
                brief={brief}
                loadingBrief={loadingBrief}
                onRefreshBrief={fetchDeskBrief}
                onAskDesk={handleAskDesk}
              />
            </div>
          )}
        </div>
      </main>
        </>
      )}

      {/* Floating Global Toast Notifications */}
      <ToastContainer toasts={toasts} onDismiss={dismissToast} />
    </div>
  );
};

export default App;
