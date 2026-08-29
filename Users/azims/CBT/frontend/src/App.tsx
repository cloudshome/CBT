import React, { useState, useEffect, useCallback } from 'react';
import { Header } from './components/Header';
import { CandleChart } from './components/CandleChart';
import { MTFPanel } from './components/MTFPanel';
import { SMCScanPanel } from './components/SMCScanPanel';
import { PaperTradingPanel } from './components/PaperTradingPanel';
import { GeminiDeskCopilot } from './components/GeminiDeskCopilot';
import { SKYIntelligencePanel } from './components/SKYIntelligencePanel';
import { ToastContainer } from './components/ToastContainer';
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
} from './types';
import { api, ApiError } from './services/api';
import { notificationService } from './services/notificationService';

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

  // SKY Quantitative Intelligence State
  const [skyData, setSkyData] = useState<SKYIntelligenceResponse | null>(null);

  // Gemini Intelligence State
  const [brief, setBrief] = useState<DeskBriefResponse | null>(null);
  const [loadingBrief, setLoadingBrief] = useState<boolean>(false);

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

  // 1. Fetch Market Data & Indicators
  const fetchMarketData = useCallback(async () => {
    setLoadingMarket(true);
    try {
      const [candlesRes, mtfRes, scanRes, skyRes] = await Promise.all([
        api.getCandles(symbol, timeframe, 100),
        api.getMTF(symbol, timeframe, 'ema,rsi'),
        api.getSMCScan(symbol, timeframe, 100),
        api.getSKYIntelligence(symbol, timeframe, 100).catch(() => null),
      ]);

      setCandles(candlesRes.candles || []);
      setEMA(mtfRes.indicators.ema || []);
      setRSI(mtfRes.indicators.rsi || []);
      setFVGs(scanRes.fvg || []);
      setOrderBlocks(scanRes.order_blocks || []);
      setSetups(scanRes.setup_suggestions || []);
      if (skyRes) {
        setSkyData(skyRes);
      }

      if (scanRes.stats) {
        setStats({
          lastPrice: scanRes.stats.lastPrice,
          highPrice: scanRes.stats.highPrice,
          lowPrice: scanRes.stats.lowPrice,
          trend: scanRes.stats.trend,
        });
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

      // Trigger Web Push Notification for fresh AI Brief
      if (res && res.executiveSummary) {
        notificationService.notifyMarketBriefAlert(symbol, res.bias, res.executiveSummary);
      }
    } catch (err: unknown) {
      console.warn('AI Brief error:', err);
    } finally {
      setLoadingBrief(false);
    }
  }, [symbol, timeframe]);

  // 4. Place Paper Trade
  const handlePlaceTrade = async (trade: {
    symbol: string;
    side: 'BUY' | 'SELL';
    entryPrice: number;
    sl: number;
    tp: number;
    size: number;
  }) => {
    try {
      const res = await api.placePaperTrade(trade);
      addToast(
        'success',
        'Order Executed (201)',
        `Simulated ${res.trade.side} order for ${res.trade.symbol} placed at $${res.trade.entryPrice.toFixed(2)}.`
      );
      await fetchPositions();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.statusCode === 403) {
          addToast('error', 'Risk Gate Rejection (403)', err.message);
          // Trigger Web Push notification for Risk Gate rejection alert
          notificationService.notifyRiskGateAlert(
            `Simulated ${trade.side} trade rejected`,
            err.message
          );
        } else if (err.statusCode === 429) {
          addToast('warning', 'Rate Limit Exceeded (429)', 'Please wait before placing another order.');
        } else {
          addToast('error', `Order Error (${err.statusCode})`, err.message);
        }
      } else {
        const msg = err instanceof Error ? err.message : 'Trade failed';
        addToast('error', 'Order Placement Failed', msg);
      }
      throw err;
    }
  };

  // 5. Ask Desk Copilot
  const handleAskDesk = async (query: string): Promise<string> => {
    try {
      const res = await api.askDesk(query, {
        symbol,
        timeframe,
        lastPrice: stats.lastPrice,
        trend: stats.trend,
        rsi: rsi.length > 0 ? rsi[rsi.length - 1].value : undefined,
        ema: ema.length > 0 ? ema[ema.length - 1].value : undefined,
        setups,
      });
      return res.answer;
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Query failed';
      addToast('error', 'Copilot Query Error', msg);
      throw err;
    }
  };

  // Initial and reactive data loader
  useEffect(() => {
    fetchMarketData();
    fetchPositions();
    fetchDeskBrief();
  }, [fetchMarketData, fetchPositions, fetchDeskBrief]);

  // 30s background telemetry polling
  useEffect(() => {
    const interval = setInterval(() => {
      fetchMarketData();
      fetchPositions();
    }, 30000);
    return () => clearInterval(interval);
  }, [fetchMarketData, fetchPositions]);

  return (
    <div className="min-h-screen bg-background text-slate-200 flex flex-col">
      {/* Top Header Navigation */}
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
          fetchMarketData();
          fetchPositions();
          fetchDeskBrief();
        }}
        notificationsEnabled={notificationsEnabled}
        onToggleNotifications={handleToggleNotifications}
      />

      {/* Main Terminal Body */}
      <main className="flex-1 p-4 max-w-[1800px] w-full mx-auto grid grid-cols-1 xl:grid-cols-12 gap-4">
        {/* Left Column (8 cols): Chart + Indicators + Setups */}
        <div className="xl:col-span-8 flex flex-col gap-4">
          {/* Main Candlestick Chart */}
          <div className="h-[460px]">
            <CandleChart
              symbol={symbol}
              candles={candles}
              fvgs={fvgs}
              orderBlocks={orderBlocks}
              ema={ema}
              loading={loadingMarket}
            />
          </div>

          {/* SKY Professional Market Intelligence Panel */}
          <SKYIntelligencePanel
            data={skyData}
            loading={loadingMarket}
            onDeploySetup={(setup) => setSelectedSetup(setup)}
          />

          {/* Lower Grid: MTF Indicators & SMC Setups */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="min-h-[260px]">
              <MTFPanel
                symbol={symbol}
                timeframe={timeframe}
                lastPrice={stats.lastPrice}
                ema={ema}
                rsi={rsi}
                trend={stats.trend}
                loading={loadingMarket}
              />
            </div>
            <div className="min-h-[260px]">
              <SMCScanPanel
                fvgs={fvgs}
                orderBlocks={orderBlocks}
                setups={setups}
                onSelectSetup={(setup) => setSelectedSetup(setup)}
                loading={loadingMarket}
              />
            </div>
          </div>
        </div>

        {/* Right Column (4 cols): Paper Trading Desk & Gemini Copilot */}
        <div className="xl:col-span-4 flex flex-col gap-4">
          {/* Gemini Desk Intelligence Copilot */}
          <div className="flex-1 min-h-[380px]">
            <GeminiDeskCopilot
              symbol={symbol}
              timeframe={timeframe}
              brief={brief}
              loadingBrief={loadingBrief}
              onRefreshBrief={fetchDeskBrief}
              onAskDesk={handleAskDesk}
            />
          </div>

          {/* Paper Trading Desk */}
          <div className="min-h-[360px]">
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
              loading={loadingMarket}
            />
          </div>
        </div>
      </main>

      {/* Floating Global Toast Notifications */}
      <ToastContainer toasts={toasts} onDismiss={dismissToast} />
    </div>
  );
};

export default App;
