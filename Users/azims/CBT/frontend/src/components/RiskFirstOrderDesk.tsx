import React, { useState, useEffect } from 'react';
import { TrendingUp, TrendingDown, Calculator, ArrowRight, Sparkles, Zap } from 'lucide-react';
import { PrecisionMath } from '../core/precision/decimalMath';
import { SetupSuggestion } from '../types';
import { api } from '../services/api';

interface RiskFirstOrderDeskProps {
  symbol: string;
  lastPrice: number;
  selectedSetup?: SetupSuggestion | null;
  onPlaceOrder: (order: {
    symbol: string;
    side: 'BUY' | 'SELL';
    type: 'MARKET' | 'LIMIT';
    price?: number;
    amount: number;
    stopLoss?: number;
    takeProfit?: number;
    executionAlgo?: string;
  }) => Promise<void>;
}

export const RiskFirstOrderDesk: React.FC<RiskFirstOrderDeskProps> = ({
  symbol,
  lastPrice,
  selectedSetup,
  onPlaceOrder,
}) => {
  const [orderType, setOrderType] = useState<'MARKET' | 'LIMIT'>('MARKET');
  const [executionAlgo, setExecutionAlgo] = useState<'STANDARD' | 'TWAP' | 'VWAP' | 'ALMGREN_CHRISS' | 'IOC_SWEEP'>('STANDARD');
  const [side, setSide] = useState<'BUY' | 'SELL'>('BUY');
  const [accountEquity] = useState<number>(10000);
  const [riskPct, setRiskPct] = useState<number>(0.01); // 1% risk
  const [entryPrice, setEntryPrice] = useState<number>(lastPrice || 0);
  const [stopLoss, setStopLoss] = useState<number>(0);
  const [takeProfit, setTakeProfit] = useState<number>(0);
  const [leverage, setLeverage] = useState<number>(10);
  const [submitting, setSubmitting] = useState(false);
  const [kronosAdvisory, setKronosAdvisory] = useState<any>(null);
  const [impactEstimate, setImpactEstimate] = useState<{ expected_slippage_bps: number; total_impact_usd: number } | null>(null);

  // Kronos Advisory Shadow Ingestion
  useEffect(() => {
    let isMounted = true;
    const cleanSym = symbol.replace('/', '').toUpperCase();
    api.getKronosAdvisory({
      symbol: cleanSym,
      timeframe: '15m',
      sky_decision: side === 'BUY' ? 'LONG' : 'SHORT',
    }).then((res) => {
      if (isMounted && res) setKronosAdvisory(res);
    }).catch(() => {});
    return () => { isMounted = false; };
  }, [symbol, side]);

  // Sync with selected setup if provided
  useEffect(() => {
    if (selectedSetup) {
      setSide(selectedSetup.type === 'LONG' ? 'BUY' : 'SELL');
      setEntryPrice(selectedSetup.entry || lastPrice);
      setStopLoss(selectedSetup.stopLoss || 0);
      setTakeProfit(selectedSetup.takeProfit || 0);
    } else if (lastPrice > 0 && entryPrice === 0) {
      setEntryPrice(lastPrice);
      setStopLoss(side === 'BUY' ? lastPrice * 0.985 : lastPrice * 1.015);
      setTakeProfit(side === 'BUY' ? lastPrice * 1.045 : lastPrice * 0.955);
    }
  }, [selectedSetup, lastPrice]);

  // Compute exact position size & liquidation price using fixed-point math
  const { riskAmountUsd, positionSizeBase, positionSizeQuote, stopDistancePct } =
    PrecisionMath.calculatePositionSize(
      accountEquity,
      riskPct,
      entryPrice > 0 ? entryPrice : lastPrice,
      stopLoss
    );

  const liquidationPrice = PrecisionMath.calculateLiquidationPrice(
    entryPrice > 0 ? entryPrice : lastPrice,
    side === 'BUY' ? 'LONG' : 'SHORT',
    leverage
  );

  const riskRewardRatio =
    stopLoss > 0 && takeProfit > 0 && entryPrice > 0
      ? Math.abs((takeProfit - entryPrice) / (entryPrice - stopLoss)).toFixed(2)
      : '0.00';

  // Simulate market impact when size changes
  useEffect(() => {
    if (positionSizeBase > 0 && (entryPrice > 0 || lastPrice > 0)) {
      api.simulateMarketImpact({
        order_size: positionSizeBase,
        order_side: side,
        symbol: symbol,
        mid_price: entryPrice > 0 ? entryPrice : lastPrice,
        urgency: executionAlgo === 'IOC_SWEEP' ? 'HIGH' : executionAlgo === 'STANDARD' ? 'MEDIUM' : 'LOW',
      }).then((res) => {
        if (res) {
          setImpactEstimate({
            expected_slippage_bps: res.expected_slippage_bps || 1.5,
            total_impact_usd: res.total_impact_usd || 0.12,
          });
        }
      }).catch(() => {
        setImpactEstimate(null);
      });
    }
  }, [positionSizeBase, side, symbol, entryPrice, lastPrice, executionAlgo]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (positionSizeBase <= 0) return;

    setSubmitting(true);
    try {
      await onPlaceOrder({
        symbol,
        side,
        type: orderType,
        price: orderType === 'LIMIT' ? entryPrice : undefined,
        amount: positionSizeBase,
        stopLoss: stopLoss > 0 ? stopLoss : undefined,
        takeProfit: takeProfit > 0 ? takeProfit : undefined,
        executionAlgo: executionAlgo !== 'STANDARD' ? executionAlgo : undefined,
      });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="bg-surface border border-border rounded-lg p-3.5 flex flex-col gap-3 text-slate-200 font-mono select-none">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border pb-2">
        <div className="flex items-center gap-1.5">
          <Calculator className="w-4 h-4 text-terminal-cyan" />
          <span className="font-bold text-xs tracking-wider text-slate-100 uppercase">
            Institutional Risk Desk & Smart Execution
          </span>
        </div>
        <span className="text-[10px] text-slate-400">Equity: ${accountEquity.toLocaleString()}</span>
      </div>

      {/* Kronos Neural Advisory Shadow Pill (Non-blocking) */}
      {kronosAdvisory && kronosAdvisory.advisory_signal && (
        <div className="p-2 rounded bg-indigo-950/40 border border-indigo-500/30 flex items-center justify-between text-[10px]">
          <div className="flex items-center gap-1.5">
            <Sparkles className="w-3.5 h-3.5 text-indigo-400 animate-pulse" />
            <span className="text-slate-300 font-semibold">Kronos Advisory:</span>
            <span className={`px-1.5 py-0.5 rounded font-bold ${
              kronosAdvisory.advisory_signal === 'CONFIRM_TRADE'
                ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                : kronosAdvisory.advisory_signal === 'DIVERGENCE_CAUTION'
                ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                : 'bg-slate-700/50 text-slate-300'
            }`}>
              {kronosAdvisory.advisory_signal}
            </span>
          </div>
          <div className="text-indigo-300 font-mono">
            Size Multiplier: <span className="font-bold">{kronosAdvisory.sizing_multiplier}x</span>
          </div>
        </div>
      )}

      {/* Form Controls */}
      <form onSubmit={handleSubmit} className="flex flex-col gap-2.5">
        {/* Long/Short Selection */}
        <div className="grid grid-cols-2 gap-1.5 p-0.5 bg-slate-900 rounded border border-border">
          <button
            type="button"
            onClick={() => setSide('BUY')}
            className={`py-1.5 text-xs font-bold rounded transition flex items-center justify-center gap-1 ${
              side === 'BUY' ? 'bg-terminal-green text-slate-950 shadow' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <TrendingUp className="w-3.5 h-3.5" />
            <span>LONG (BUY)</span>
          </button>

          <button
            type="button"
            onClick={() => setSide('SELL')}
            className={`py-1.5 text-xs font-bold rounded transition flex items-center justify-center gap-1 ${
              side === 'SELL' ? 'bg-terminal-red text-slate-950 shadow' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <TrendingDown className="w-3.5 h-3.5" />
            <span>SHORT (SELL)</span>
          </button>
        </div>

        {/* Order Type & Slicing Algo Row */}
        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className="text-[10px] text-slate-400">Order Routing Type</label>
            <div className="grid grid-cols-2 gap-1 mt-0.5">
              <button
                type="button"
                onClick={() => setOrderType('MARKET')}
                className={`py-1 text-xs rounded border transition ${
                  orderType === 'MARKET' ? 'bg-slate-800 border-terminal-cyan text-terminal-cyan font-bold' : 'border-border text-slate-400'
                }`}
              >
                Market
              </button>
              <button
                type="button"
                onClick={() => setOrderType('LIMIT')}
                className={`py-1 text-xs rounded border transition ${
                  orderType === 'LIMIT' ? 'bg-slate-800 border-terminal-cyan text-terminal-cyan font-bold' : 'border-border text-slate-400'
                }`}
              >
                Limit
              </button>
            </div>
          </div>

          <div>
            <label className="text-[10px] text-slate-400 flex items-center gap-1">
              <Zap className="w-3 h-3 text-amber-400" />
              <span>Execution Algo (SOR)</span>
            </label>
            <select
              value={executionAlgo}
              onChange={(e: any) => setExecutionAlgo(e.target.value)}
              className="w-full bg-slate-900 border border-border rounded px-2 py-1 text-amber-300 font-bold text-xs mt-0.5"
            >
              <option value="STANDARD">Standard Direct</option>
              <option value="TWAP">TWAP Slicer (Random Jitter)</option>
              <option value="VWAP">VWAP Curve Matching</option>
              <option value="ALMGREN_CHRISS">Almgren-Chriss Optimal</option>
              <option value="IOC_SWEEP">Aggressive IOC Sweep</option>
            </select>
          </div>
        </div>

        {/* Risk Budget Input */}
        <div>
          <label className="text-[10px] text-slate-400">Risk Allocation (% of Equity)</label>
          <select
            value={riskPct}
            onChange={(e) => setRiskPct(parseFloat(e.target.value))}
            className="w-full bg-slate-900 border border-border rounded px-2 py-1 text-terminal-cyan font-bold text-xs mt-0.5"
          >
            <option value={0.005}>0.5% (${(accountEquity * 0.005).toFixed(0)})</option>
            <option value={0.01}>1.0% (${(accountEquity * 0.01).toFixed(0)})</option>
            <option value={0.02}>2.0% (${(accountEquity * 0.02).toFixed(0)})</option>
            <option value={0.03}>3.0% (${(accountEquity * 0.03).toFixed(0)})</option>
          </select>
        </div>

        {/* Entry & Stop Loss */}
        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className="text-[10px] text-slate-400">Entry Price ($)</label>
            <input
              type="number"
              step="any"
              value={entryPrice > 0 ? Number(entryPrice.toFixed(2)) : lastPrice > 0 ? Number(lastPrice.toFixed(2)) : ''}
              onChange={(e) => setEntryPrice(parseFloat(e.target.value) || 0)}
              disabled={orderType === 'MARKET'}
              className="w-full bg-slate-900 border border-border rounded px-2 py-1 text-slate-200 text-xs mt-0.5 disabled:opacity-50"
            />
          </div>

          <div>
            <label className="text-[10px] text-slate-400">Stop Loss ($)</label>
            <input
              type="number"
              step="any"
              value={stopLoss > 0 ? Number(stopLoss.toFixed(2)) : ''}
              onChange={(e) => setStopLoss(parseFloat(e.target.value) || 0)}
              className="w-full bg-slate-900 border border-terminal-red/50 rounded px-2 py-1 text-terminal-red font-bold text-xs mt-0.5"
            />
          </div>
        </div>

        {/* Take Profit & Leverage */}
        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className="text-[10px] text-slate-400">Take Profit ($)</label>
            <input
              type="number"
              step="any"
              value={takeProfit > 0 ? Number(takeProfit.toFixed(2)) : ''}
              onChange={(e) => setTakeProfit(parseFloat(e.target.value) || 0)}
              className="w-full bg-slate-900 border border-terminal-green/50 rounded px-2 py-1 text-terminal-green font-bold text-xs mt-0.5"
            />
          </div>

          <div>
            <label className="text-[10px] text-slate-400">Leverage: {leverage}x</label>
            <input
              type="range"
              min="1"
              max="50"
              value={leverage}
              onChange={(e) => setLeverage(parseInt(e.target.value, 10))}
              className="w-full mt-2 accent-terminal-cyan cursor-pointer"
            />
          </div>
        </div>

        {/* Dynamic Computed Risk Matrix */}
        <div className="p-2 rounded bg-slate-900/90 border border-border/80 flex flex-col gap-1 text-[11px] mt-1">
          <div className="flex justify-between">
            <span className="text-slate-400">Calculated Size:</span>
            <span className="text-slate-200 font-bold">
              {positionSizeBase.toFixed(4)} {symbol.replace(/USDT|USD/g, '')} (${positionSizeQuote.toFixed(2)})
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-400">Risk Amount:</span>
            <span className="text-terminal-red font-bold">${riskAmountUsd.toFixed(2)} ({stopDistancePct}%)</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-400">Expected R:R:</span>
            <span className="text-terminal-cyan font-bold">{riskRewardRatio}R</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-400">Est. Liquidation:</span>
            <span className="text-amber-400 font-semibold">${liquidationPrice.toFixed(2)}</span>
          </div>
          {impactEstimate && (
            <div className="flex justify-between border-t border-slate-800 pt-1 text-[10px]">
              <span className="text-slate-400">Est. Market Impact:</span>
              <span className="text-amber-300 font-mono">
                {impactEstimate.expected_slippage_bps.toFixed(1)} bps (${impactEstimate.total_impact_usd.toFixed(2)})
              </span>
            </div>
          )}
        </div>

        {/* Submit Execution Button */}
        <button
          type="submit"
          disabled={submitting || positionSizeBase <= 0}
          className={`w-full py-2 rounded font-bold text-slate-950 mt-2 transition flex items-center justify-center gap-1.5 ${
            side === 'BUY' ? 'bg-terminal-green hover:bg-emerald-400' : 'bg-terminal-red hover:bg-rose-400'
          } disabled:opacity-50 disabled:cursor-not-allowed`}
        >
          <span>{side === 'BUY' ? `EXECUTE LONG (${executionAlgo})` : `EXECUTE SHORT (${executionAlgo})`}</span>
          <ArrowRight className="w-4 h-4" />
        </button>
      </form>
    </div>
  );
};

export default RiskFirstOrderDesk;
