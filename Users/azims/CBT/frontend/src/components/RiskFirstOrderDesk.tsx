import React, { useState, useEffect } from 'react';
import { TrendingUp, TrendingDown, Calculator, ArrowRight } from 'lucide-react';
import { PrecisionMath } from '../core/precision/decimalMath';
import { SetupSuggestion } from '../types';

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
  }) => Promise<void>;
}

export const RiskFirstOrderDesk: React.FC<RiskFirstOrderDeskProps> = ({
  symbol,
  lastPrice,
  selectedSetup,
  onPlaceOrder,
}) => {
  const [orderType, setOrderType] = useState<'MARKET' | 'LIMIT'>('MARKET');
  const [side, setSide] = useState<'BUY' | 'SELL'>('BUY');
  const [accountEquity] = useState<number>(10000);
  const [riskPct, setRiskPct] = useState<number>(0.01); // 1% risk
  const [entryPrice, setEntryPrice] = useState<number>(lastPrice || 0);
  const [stopLoss, setStopLoss] = useState<number>(0);
  const [takeProfit, setTakeProfit] = useState<number>(0);
  const [leverage, setLeverage] = useState<number>(10);
  const [submitting, setSubmitting] = useState(false);

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
      });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="bg-panel border border-border rounded-lg p-3 flex flex-col h-full font-mono text-xs select-none">
      {/* Header */}
      <div className="flex items-center justify-between pb-2 border-b border-border/80">
        <div className="flex items-center gap-1.5 text-slate-300 font-bold">
          <Calculator className="w-3.5 h-3.5 text-terminal-cyan" />
          <span>RISK-FIRST ORDER DESK</span>
        </div>
        <span className="text-[10px] text-slate-400 bg-slate-900 px-1.5 py-0.5 rounded border border-border">
          EQUITY: ${accountEquity.toLocaleString()}
        </span>
      </div>

      {/* Side Toggle: BUY / SELL */}
      <div className="grid grid-cols-2 gap-1.5 my-2">
        <button
          type="button"
          onClick={() => {
            setSide('BUY');
            if (lastPrice > 0) {
              setStopLoss(lastPrice * 0.985);
              setTakeProfit(lastPrice * 1.045);
            }
          }}
          className={`py-1.5 rounded font-bold transition flex items-center justify-center gap-1 ${
            side === 'BUY'
              ? 'bg-terminal-green text-slate-950 shadow-lg'
              : 'bg-slate-900 text-slate-400 border border-border hover:text-slate-200'
          }`}
        >
          <TrendingUp className="w-3.5 h-3.5" />
          <span>LONG / BUY</span>
        </button>

        <button
          type="button"
          onClick={() => {
            setSide('SELL');
            if (lastPrice > 0) {
              setStopLoss(lastPrice * 1.015);
              setTakeProfit(lastPrice * 0.955);
            }
          }}
          className={`py-1.5 rounded font-bold transition flex items-center justify-center gap-1 ${
            side === 'SELL'
              ? 'bg-terminal-red text-slate-950 shadow-lg'
              : 'bg-slate-900 text-slate-400 border border-border hover:text-slate-200'
          }`}
        >
          <TrendingDown className="w-3.5 h-3.5" />
          <span>SHORT / SELL</span>
        </button>
      </div>

      <form onSubmit={handleSubmit} className="flex flex-col gap-2 flex-1 justify-between">
        <div className="flex flex-col gap-2">
          {/* Order Type & Risk % */}
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-[10px] text-slate-400">Order Type</label>
              <select
                value={orderType}
                onChange={(e) => setOrderType(e.target.value as 'MARKET' | 'LIMIT')}
                className="w-full bg-slate-900 border border-border rounded px-2 py-1 text-slate-200 text-xs mt-0.5"
              >
                <option value="MARKET">Market</option>
                <option value="LIMIT">Limit</option>
              </select>
            </div>

            <div>
              <label className="text-[10px] text-slate-400">Risk % per Trade</label>
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
          </div>
        </div>

        {/* Submit Execution Button */}
        <button
          type="submit"
          disabled={submitting || positionSizeBase <= 0}
          className={`w-full py-2 rounded font-bold text-slate-950 mt-2 transition flex items-center justify-center gap-1.5 ${
            side === 'BUY' ? 'bg-terminal-green hover:bg-emerald-400' : 'bg-terminal-red hover:bg-rose-400'
          } disabled:opacity-50 disabled:cursor-not-allowed`}
        >
          <span>{side === 'BUY' ? 'EXECUTE LONG' : 'EXECUTE SHORT'}</span>
          <ArrowRight className="w-4 h-4" />
        </button>
      </form>
    </div>
  );
};
