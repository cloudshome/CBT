import React, { useState, useEffect, useCallback } from 'react';
import { SystemCommandStrip } from './SystemCommandStrip';
import { MTFHeatmapMatrix } from './MTFHeatmapMatrix';
import { MarketStructureCanvas } from './MarketStructureCanvas';
import { InstitutionalConfluenceRadar } from './InstitutionalConfluenceRadar';
import { OrderFlowCommandCenter } from './OrderFlowCommandCenter';
import { SignalCommandDeck } from './SignalCommandDeck';
import { ExecutionBlotterAndRisk } from './ExecutionBlotterAndRisk';
import { MacroRadarStrip } from './MacroRadarStrip';
import { DecisionMentorAndProvenance } from './DecisionMentorAndProvenance';
import {
  MasterTerminalTelemetry,
  TerminalDensityMode,
  StyleSignalPlan,
  SupportedTimeframe,
  OHLCVCandle,
} from '../../types';
import { api } from '../../services/api';

interface InstitutionalMasterTerminalProps {
  initialSymbol?: string;
  initialTimeframe?: SupportedTimeframe;
  onDeployToOrderDesk?: (setup: any) => void;
  addToast: (type: 'success' | 'error' | 'info' | 'warning', title: string, message: string) => void;
}

export const InstitutionalMasterTerminal: React.FC<InstitutionalMasterTerminalProps> = ({
  initialSymbol = 'BTCUSDT',
  initialTimeframe = '15m',
  onDeployToOrderDesk,
  addToast,
}) => {
  // Navigation & Workspace State (Zero-Shake Invariant: User viewport states preserved)
  const [symbol, setSymbol] = useState<string>(initialSymbol);
  const [timeframe, setTimeframe] = useState<SupportedTimeframe>(initialTimeframe);
  const [densityMode, setDensityMode] = useState<TerminalDensityMode>('COMMAND');
  const [selectedStyle, setSelectedStyle] = useState<StyleSignalPlan['style']>('SWING');

  // Master Telemetry State
  const [telemetry, setTelemetry] = useState<MasterTerminalTelemetry | null>(null);
  const [candles, setCandles] = useState<OHLCVCandle[]>([]);
  const [loading, setLoading] = useState<boolean>(false);

  // 1. Fetch Complete Telemetry Payload
  const fetchTelemetry = useCallback(async () => {
    try {
      const data = await api.getMasterTerminalTelemetry(symbol, timeframe);
      setTelemetry(data);
    } catch (err: unknown) {
      console.warn('Silent telemetry refresh skipped:', err);
    }
  }, [symbol, timeframe]);

  // 2. Initial Full Load
  const fetchInitialData = useCallback(async () => {
    setLoading(true);
    try {
      const [telRes, candleRes] = await Promise.all([
        api.getMasterTerminalTelemetry(symbol, timeframe),
        api.getCandles(symbol, timeframe, 150).catch(() => null),
      ]);
      setTelemetry(telRes);
      if (candleRes?.candles) {
        setCandles(candleRes.candles);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to load master terminal telemetry';
      addToast('error', 'Telemetry Sync Error', msg);
    } finally {
      setLoading(false);
    }
  }, [symbol, timeframe, addToast]);

  useEffect(() => {
    fetchInitialData();
  }, [fetchInitialData]);

  // 3. Zero-Shake Silent Background Telemetry Polling (Every 10s without UI re-mounting)
  useEffect(() => {
    const interval = setInterval(() => {
      fetchTelemetry();
    }, 10000);
    return () => clearInterval(interval);
  }, [fetchTelemetry]);

  // Handle Signal State Transitions in Blotter
  const handleUpdateSignalState = async (
    signalId: string,
    action: 'APPROVE' | 'REJECT' | 'EXECUTE' | 'CLOSE'
  ) => {
    try {
      const res = await api.updateSignalApproval(signalId, action);
      if (res.success) {
        addToast('success', `Signal ${signalId} Updated`, `Transitioned to state: ${res.newState}`);
        fetchTelemetry();
      }
    } catch {
      addToast('error', 'Action Error', 'Failed to update signal blotter');
    }
  };

  // Submit Signal to Approval Queue
  const handleSubmitToApproval = (signal: StyleSignalPlan) => {
    addToast('info', 'Signal Submitted', `Added ${signal.style} ${signal.side} to Human Approval Blotter (Pending).`);
    if (onDeployToOrderDesk) {
      onDeployToOrderDesk({
        type: signal.side,
        entry: signal.entryZone[0],
        stopLoss: signal.stopLoss,
        takeProfit: signal.tp1,
        riskRewardRatio: signal.riskRewardRatio,
      });
    }
  };

  const selectedSignal = telemetry?.styleSignals?.find((s) => s.style === selectedStyle) || telemetry?.styleSignals?.[0];

  return (
    <div className="w-full min-h-screen bg-[#060912] text-slate-200 font-mono flex flex-col select-none">
      {/* Level 0: System Command & Health Strip */}
      <SystemCommandStrip
        telemetry={telemetry}
        densityMode={densityMode}
        onDensityModeChange={setDensityMode}
        selectedSymbol={symbol}
        onSelectSymbol={(sym) => setSymbol(sym)}
        onRefresh={fetchInitialData}
        loading={loading}
      />

      {/* Level 1: Multi-Timeframe Heatmap Matrix Bar */}
      {telemetry && (
        <MTFHeatmapMatrix
          matrix={telemetry.market.mtfMatrix}
          regime={telemetry.market.regime}
          marketDecision={telemetry.market.marketDecision}
          selectedTimeframe={timeframe}
          onSelectTimeframe={(tf) => setTimeframe(tf as SupportedTimeframe)}
        />
      )}

      {/* Main Cockpit Layout based on Density Mode */}
      <div className="p-3 space-y-3 max-w-[1920px] w-full mx-auto flex-1">
        {/* MODE: COMMAND (Active Institutional Trading Cockpit) */}
        {densityMode === 'COMMAND' && telemetry && (
          <>
            {/* Upper Split: Primary Market Canvas (7 cols) + Confluence & Signals (5 cols) */}
            <div className="grid grid-cols-1 xl:grid-cols-12 gap-3 items-stretch">
              {/* Primary Market Structure Canvas */}
              <div className="xl:col-span-7 flex flex-col gap-3">
                <MarketStructureCanvas
                  symbol={symbol}
                  timeframe={timeframe}
                  candles={candles}
                  fvgs={telemetry.market.smcStructures.fvgList}
                  orderBlocks={telemetry.market.smcStructures.orderBlocks}
                  volumeProfile={telemetry.market.volumeProfile}
                  liquidationMap={telemetry.market.liquidationMap}
                  selectedSignalPlan={selectedSignal}
                  currentPrice={telemetry.currentPrice}
                  fib05Equilibrium={telemetry.market.premiumDiscount.fib05Equilibrium}
                  currentZone={telemetry.market.premiumDiscount.currentZone}
                  onTimeframeChange={(newTf) => setTimeframe(newTf)}
                  loading={loading}
                />

                {/* Order Flow & CVD Sub-Center */}
                <OrderFlowCommandCenter
                  orderFlow={telemetry.orderFlow}
                  candles={candles}
                />
              </div>

              {/* Right Column: Institutional Confluence & Signal Command Deck */}
              <div className="xl:col-span-5 flex flex-col gap-3">
                <InstitutionalConfluenceRadar
                  confluence={telemetry.confluence}
                />

                <SignalCommandDeck
                  signals={telemetry.styleSignals}
                  selectedStyle={selectedStyle}
                  onSelectStyle={setSelectedStyle}
                  onSubmitToApproval={handleSubmitToApproval}
                />
              </div>
            </div>

            {/* Level 5: Execution Blotter & Paper Risk */}
            <ExecutionBlotterAndRisk
              portfolio={telemetry.executionAndRisk}
              onUpdateSignalState={handleUpdateSignalState}
            />

            {/* Level 6: Macro, Dominance, Prediction Markets & On-Chain */}
            <MacroRadarStrip
              macro={telemetry.macroAndContext}
            />

            {/* Level 7: AI Decision Mentor, Pre-Trade Gate, 'Why Not Trade?' & Provenance */}
            <DecisionMentorAndProvenance
              coach={telemetry.learningAndCoach}
              provenance={telemetry.provenance}
            />
          </>
        )}

        {/* MODE: ANALYSIS (Full-Width Chart Canvas & Deep Indicator Stacks) */}
        {densityMode === 'ANALYSIS' && telemetry && (
          <>
            <div className="w-full">
              <MarketStructureCanvas
                symbol={symbol}
                timeframe={timeframe}
                candles={candles}
                fvgs={telemetry.market.smcStructures.fvgList}
                orderBlocks={telemetry.market.smcStructures.orderBlocks}
                volumeProfile={telemetry.market.volumeProfile}
                liquidationMap={telemetry.market.liquidationMap}
                selectedSignalPlan={selectedSignal}
                currentPrice={telemetry.currentPrice}
                fib05Equilibrium={telemetry.market.premiumDiscount.fib05Equilibrium}
                currentZone={telemetry.market.premiumDiscount.currentZone}
                onTimeframeChange={(newTf) => setTimeframe(newTf)}
                loading={loading}
              />
            </div>

            <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
              <OrderFlowCommandCenter
                orderFlow={telemetry.orderFlow}
                candles={candles}
              />
              <InstitutionalConfluenceRadar
                confluence={telemetry.confluence}
              />
            </div>

            <MacroRadarStrip
              macro={telemetry.macroAndContext}
            />
          </>
        )}

        {/* MODE: REVIEW (Replay Lab, Strategy Calibration & Performance Autopsies) */}
        {densityMode === 'REVIEW' && telemetry && (
          <>
            <ExecutionBlotterAndRisk
              portfolio={telemetry.executionAndRisk}
              onUpdateSignalState={handleUpdateSignalState}
            />

            <DecisionMentorAndProvenance
              coach={telemetry.learningAndCoach}
              provenance={telemetry.provenance}
            />

            <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
              <InstitutionalConfluenceRadar
                confluence={telemetry.confluence}
              />
              <MacroRadarStrip
                macro={telemetry.macroAndContext}
              />
            </div>
          </>
        )}
      </div>
    </div>
  );
};
