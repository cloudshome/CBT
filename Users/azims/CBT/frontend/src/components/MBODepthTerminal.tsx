import React, { useState, useEffect, useCallback } from 'react';
import {
  Activity,
  Calculator,
  Clock,
  Coins,
  Eye,
  Layers,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
} from 'lucide-react';
import {
  api,
  MBODepthResponse,
  MBOIcebergItem,
  MBOQueueEstimate,
  MBOToxicityData,
} from '../services/api';

interface MBODepthTerminalProps {
  currentSymbol?: string;
  onNotify?: (type: 'success' | 'error' | 'warning' | 'info', title: string, message: string) => void;
}

const SUPPORTED_SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT'];

export const MBODepthTerminal: React.FC<MBODepthTerminalProps> = ({
  currentSymbol = 'BTCUSDT',
  onNotify,
}) => {
  const [symbol, setSymbol] = useState<string>(
    SUPPORTED_SYMBOLS.find(s => s === currentSymbol.replace('/', '').toUpperCase()) || 'BTCUSDT'
  );
  const [venue, setVenue] = useState<string>('BINANCE_SPOT');
  const [loading, setLoading] = useState<boolean>(true);
  const [depthData, setDepthData] = useState<MBODepthResponse | null>(null);
  const [icebergs, setIcebergs] = useState<MBOIcebergItem[]>([]);
  const [toxicity, setToxicity] = useState<MBOToxicityData | null>(null);

  // Queue Calculator Inputs
  const [calcSide, setCalcSide] = useState<'BID' | 'ASK'>('BID');
  const [calcPrice, setCalcPrice] = useState<number>(65000);
  const [calcQty, setCalcQty] = useState<number>(0.5);
  const [queueEstimate, setQueueEstimate] = useState<MBOQueueEstimate | null>(null);
  const [loadingEstimate, setLoadingEstimate] = useState<boolean>(false);
  const [lastUpdated, setLastUpdated] = useState<Date>(new Date());

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const [depthRes, iceRes, toxRes] = await Promise.all([
        api.getMBODepth(symbol, venue),
        api.getMBOIcebergs(symbol),
        api.getMBOToxicity(symbol, venue),
      ]);

      setDepthData(depthRes);
      setIcebergs(iceRes.icebergs || []);
      setToxicity(toxRes.toxicity);
      setLastUpdated(new Date());

      // Auto-set calc price if needed
      if (depthRes.bids.length > 0 && calcSide === 'BID') {
        setCalcPrice(depthRes.bids[0].price);
      } else if (depthRes.asks.length > 0 && calcSide === 'ASK') {
        setCalcPrice(depthRes.asks[0].price);
      }
    } catch (err: any) {
      console.error('Failed fetching MBO depth data:', err);
      onNotify?.('error', 'MBO Depth Error', err.message || 'Could not connect to L3 MBO stream.');
    } finally {
      setLoading(false);
    }
  }, [symbol, venue, onNotify]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 8000); // 8s auto-refresh
    return () => clearInterval(interval);
  }, [fetchData]);

  // Run queue estimate calculation
  const calculateQueue = useCallback(async () => {
    try {
      setLoadingEstimate(true);
      const res = await api.getMBOQueueEstimate(symbol, venue, calcSide, calcPrice, calcQty);
      setQueueEstimate(res.estimate);
    } catch (err: any) {
      onNotify?.('warning', 'Queue Calc Failed', err.message || 'Error computing queue position.');
    } finally {
      setLoadingEstimate(false);
    }
  }, [symbol, venue, calcSide, calcPrice, calcQty, onNotify]);

  useEffect(() => {
    if (depthData) {
      calculateQueue();
    }
  }, [depthData, calcSide, calcPrice, calcQty]);

  return (
    <div className="flex flex-col h-full bg-[#0a0d14] text-slate-200 overflow-y-auto p-4 space-y-4 font-sans">
      {/* HEADER CONTROLS */}
      <div className="flex flex-wrap items-center justify-between gap-3 p-4 bg-[#10141e] border border-slate-800 rounded-xl">
        <div className="flex items-center space-x-3">
          <div className="p-2.5 bg-cyan-500/10 border border-cyan-500/30 rounded-lg text-cyan-400">
            <Layers className="w-6 h-6 animate-pulse" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h1 className="text-lg font-bold tracking-wide text-white">
                L3 MARKET BY ORDER (MBO) LIQUIDITY DEPTH RECONSTRUCTION
              </h1>
              <span className="px-2 py-0.5 text-xs font-mono font-bold bg-cyan-500/10 text-cyan-400 border border-cyan-500/30 rounded">
                TASK 20.2 • L3 RECONSTRUCTION
              </span>
              <span className="px-2 py-0.5 text-xs font-mono bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 rounded flex items-center space-x-1">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                <span>FIFO QUEUE ACTIVE</span>
              </span>
              <span className="text-[10px] font-mono text-slate-500 flex items-center space-x-1">
                <Clock className="w-3 h-3" />
                <span>{lastUpdated.toLocaleTimeString()}</span>
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              Discrete Order Queues • Queue Priority & Fill Probabilities • Algorithmic Iceberg Detection • Flow Toxicity
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-3">
          {/* SYMBOL SELECTOR */}
          <div className="flex items-center bg-[#0d111a] border border-slate-800 rounded-lg p-1">
            {SUPPORTED_SYMBOLS.map(sym => (
              <button
                key={sym}
                onClick={() => setSymbol(sym)}
                className={`px-3 py-1.5 text-xs font-mono font-semibold rounded-md transition-colors ${
                  symbol === sym
                    ? 'bg-cyan-600 text-white shadow-sm'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
                }`}
              >
                {sym}
              </button>
            ))}
          </div>

          {/* VENUE SELECTOR */}
          <select
            value={venue}
            onChange={e => setVenue(e.target.value)}
            className="bg-[#0d111a] border border-slate-800 text-xs font-mono text-slate-300 rounded-lg px-2.5 py-1.5 outline-none focus:border-cyan-500"
          >
            <option value="BINANCE_SPOT">Binance Spot</option>
            <option value="BINANCE_PERP">Binance Perp</option>
            <option value="BYBIT_LINEAR">Bybit Linear</option>
          </select>

          <button
            onClick={fetchData}
            disabled={loading}
            className="flex items-center space-x-1.5 px-3 py-1.5 text-xs font-mono bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg transition-colors border border-slate-700"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            <span>Sync</span>
          </button>
        </div>
      </div>

      {/* TOP KPI CARDS */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
        {/* CARD 1: TOTAL DEPTH */}
        <div className="p-3.5 bg-[#10141e] border border-slate-800 rounded-xl">
          <div className="flex items-center justify-between text-xs text-slate-400 mb-1.5">
            <span className="flex items-center space-x-1.5">
              <Coins className="w-3.5 h-3.5 text-cyan-400" />
              <span>Visible Book Depth</span>
            </span>
            <span className="text-[10px] font-mono text-slate-500">L3 Top 15</span>
          </div>
          <div className="flex items-baseline justify-between">
            <div className="text-xl font-bold font-mono text-white">
              ${(((depthData?.total_bid_depth_usd || 0) + (depthData?.total_ask_depth_usd || 0)) / 1000).toFixed(1)}k
            </div>
            <div className="text-xs font-mono text-emerald-400">
              Bid: ${( (depthData?.total_bid_depth_usd || 0) / 1000).toFixed(1)}k
            </div>
          </div>
          <div className="text-[11px] text-slate-400 mt-1 flex justify-between">
            <span>Imbalance: {( (depthData?.microstructure_imbalance || 0) * 100).toFixed(1)}%</span>
            <span className="text-rose-400">Ask: ${( (depthData?.total_ask_depth_usd || 0) / 1000).toFixed(1)}k</span>
          </div>
        </div>

        {/* CARD 2: FLOW TOXICITY & VPIN */}
        <div className="p-3.5 bg-[#10141e] border border-slate-800 rounded-xl">
          <div className="flex items-center justify-between text-xs text-slate-400 mb-1.5">
            <span className="flex items-center space-x-1.5">
              <Activity className="w-3.5 h-3.5 text-amber-400" />
              <span>Microstructure Toxicity</span>
            </span>
            <span className={`text-[10px] font-mono font-bold px-1.5 py-0.2 rounded ${
              toxicity?.toxicity_regime === 'TOXIC'
                ? 'bg-rose-500/20 text-rose-400 border border-rose-500/30'
                : toxicity?.toxicity_regime === 'ELEVATED'
                ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                : 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
            }`}>
              {toxicity?.toxicity_regime || 'LOW'}
            </span>
          </div>
          <div className="text-xl font-bold font-mono text-amber-400">
            VPIN: {toxicity?.vpin_mbo.toFixed(3) || '0.245'}
          </div>
          <div className="text-[11px] text-slate-400 mt-1 flex justify-between">
            <span>Cancel/Trade: {toxicity?.cancel_to_trade_ratio.toFixed(2) || '1.40'}x</span>
            <span>Sweep: ${((toxicity?.depletion_velocity_usd_per_sec || 0) / 1000).toFixed(1)}k/s</span>
          </div>
        </div>

        {/* CARD 3: ICEBERG RADAR */}
        <div className="p-3.5 bg-[#10141e] border border-slate-800 rounded-xl">
          <div className="flex items-center justify-between text-xs text-slate-400 mb-1.5">
            <span className="flex items-center space-x-1.5">
              <Eye className="w-3.5 h-3.5 text-purple-400" />
              <span>Iceberg Reload Walls</span>
            </span>
            <span className="text-[10px] font-mono text-slate-500">Active</span>
          </div>
          <div className="text-xl font-bold font-mono text-purple-400">
            {icebergs.length} Detected
          </div>
          <div className="text-[11px] text-slate-400 mt-1">
            {icebergs.length > 0 ? (
              <span className="text-slate-300">
                Largest: {icebergs[0].price} ({icebergs[0].total_estimated_size.toFixed(2)} est.)
              </span>
            ) : (
              <span className="text-slate-500">No hidden reload walls detected</span>
            )}
          </div>
        </div>

        {/* CARD 4: ADVERSE SELECTION BIAS */}
        <div className="p-3.5 bg-[#10141e] border border-slate-800 rounded-xl">
          <div className="flex items-center justify-between text-xs text-slate-400 mb-1.5">
            <span className="flex items-center space-x-1.5">
              <ShieldAlert className="w-3.5 h-3.5 text-rose-400" />
              <span>Adverse Selection Bias</span>
            </span>
            <span className="text-[10px] font-mono text-slate-500">Expected Drift</span>
          </div>
          <div className="text-xl font-bold font-mono text-rose-400">
            {toxicity?.adverse_selection_bias_bps.toFixed(1) || '1.2'} bps
          </div>
          <div className="text-[11px] text-slate-400 mt-1">
            Mean Order Lifetime: {toxicity?.mean_order_lifetime_ms.toFixed(0) || '320'}ms
          </div>
        </div>
      </div>

      {/* MAIN TWO-COLUMN WORKBENCH */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* LEFT COLUMN (7 cols): RECONSTRUCTED DISCRETE L3 DEPTH LADDER */}
        <div className="lg:col-span-7 bg-[#10141e] border border-slate-800 rounded-xl p-4 flex flex-col space-y-3">
          <div className="flex items-center justify-between border-b border-slate-800 pb-2">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-200 flex items-center space-x-2">
              <Layers className="w-4 h-4 text-cyan-400" />
              <span>Discrete Order Queue Reconstruction</span>
            </span>
            <span className="text-xs font-mono text-slate-400">
              Top 10 Levels (Price-Time Priority)
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs font-mono">
            {/* BIDS LADDER */}
            <div className="space-y-1.5">
              <div className="text-[11px] font-bold text-emerald-400 uppercase tracking-wider mb-1 flex justify-between border-b border-slate-800/80 pb-1">
                <span>Bid Orders (Queue)</span>
                <span>Price</span>
                <span>Total Qty</span>
              </div>
              {depthData?.bids.slice(0, 10).map((bid, idx) => (
                <div
                  key={`bid-${bid.price}`}
                  onClick={() => {
                    setCalcSide('BID');
                    setCalcPrice(bid.price);
                  }}
                  className={`p-2 rounded-lg border transition-all cursor-pointer ${
                    calcPrice === bid.price && calcSide === 'BID'
                      ? 'bg-emerald-500/20 border-emerald-500/50 shadow'
                      : 'bg-[#0d111a] border-slate-800/80 hover:border-emerald-500/30'
                  }`}
                >
                  <div className="flex items-center justify-between font-bold">
                    <span className="text-slate-400 text-[10px]">
                      #{idx + 1} ({bid.order_count} ords)
                    </span>
                    <span className="text-emerald-400">{bid.price.toFixed(2)}</span>
                    <span className="text-white">{bid.total_size.toFixed(4)}</span>
                  </div>
                  {/* Discrete Orders Breakdown */}
                  <div className="flex items-center space-x-1 mt-1 overflow-x-hidden">
                    {bid.orders.map((ord, oIdx) => (
                      <div
                        key={ord.order_id}
                        title={`Order: ${ord.order_id} | Qty: ${ord.size} | Priority: #${ord.priority_index}`}
                        className={`h-1.5 rounded-sm flex-1 ${
                          oIdx === 0 ? 'bg-emerald-400' : 'bg-emerald-600/70'
                        }`}
                      />
                    ))}
                  </div>
                </div>
              ))}
            </div>

            {/* ASKS LADDER */}
            <div className="space-y-1.5">
              <div className="text-[11px] font-bold text-rose-400 uppercase tracking-wider mb-1 flex justify-between border-b border-slate-800/80 pb-1">
                <span>Price</span>
                <span>Ask Orders (Queue)</span>
                <span>Total Qty</span>
              </div>
              {depthData?.asks.slice(0, 10).map((ask, idx) => (
                <div
                  key={`ask-${ask.price}`}
                  onClick={() => {
                    setCalcSide('ASK');
                    setCalcPrice(ask.price);
                  }}
                  className={`p-2 rounded-lg border transition-all cursor-pointer ${
                    calcPrice === ask.price && calcSide === 'ASK'
                      ? 'bg-rose-500/20 border-rose-500/50 shadow'
                      : 'bg-[#0d111a] border-slate-800/80 hover:border-rose-500/30'
                  }`}
                >
                  <div className="flex items-center justify-between font-bold">
                    <span className="text-rose-400">{ask.price.toFixed(2)}</span>
                    <span className="text-slate-400 text-[10px]">
                      #{idx + 1} ({ask.order_count} ords)
                    </span>
                    <span className="text-white">{ask.total_size.toFixed(4)}</span>
                  </div>
                  {/* Discrete Orders Breakdown */}
                  <div className="flex items-center space-x-1 mt-1 overflow-x-hidden">
                    {ask.orders.map((ord, oIdx) => (
                      <div
                        key={ord.order_id}
                        title={`Order: ${ord.order_id} | Qty: ${ord.size} | Priority: #${ord.priority_index}`}
                        className={`h-1.5 rounded-sm flex-1 ${
                          oIdx === 0 ? 'bg-rose-400' : 'bg-rose-600/70'
                        }`}
                      />
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* RIGHT COLUMN (5 cols): QUEUE PRIORITY & FILL PROBABILITY CALCULATOR */}
        <div className="lg:col-span-5 bg-[#10141e] border border-slate-800 rounded-xl p-4 flex flex-col space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-2">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-200 flex items-center space-x-2">
              <Calculator className="w-4 h-4 text-cyan-400" />
              <span>Queue Priority & Fill Simulator</span>
            </span>
            <span className="text-xs font-mono text-cyan-400">
              {loadingEstimate ? 'Solving...' : 'Active Simulation'}
            </span>
          </div>

          {/* CALCULATOR CONTROLS */}
          <div className="grid grid-cols-3 gap-2 bg-[#0d111a] p-2.5 rounded-lg border border-slate-800">
            <div>
              <label className="text-[10px] text-slate-400 font-mono">Side</label>
              <div className="flex space-x-1 mt-1">
                <button
                  onClick={() => setCalcSide('BID')}
                  className={`flex-1 py-1 text-xs font-bold font-mono rounded ${
                    calcSide === 'BID'
                      ? 'bg-emerald-600 text-white'
                      : 'bg-slate-800 text-slate-400'
                  }`}
                >
                  BID
                </button>
                <button
                  onClick={() => setCalcSide('ASK')}
                  className={`flex-1 py-1 text-xs font-bold font-mono rounded ${
                    calcSide === 'ASK'
                      ? 'bg-rose-600 text-white'
                      : 'bg-slate-800 text-slate-400'
                  }`}
                >
                  ASK
                </button>
              </div>
            </div>

            <div>
              <label className="text-[10px] text-slate-400 font-mono">Price</label>
              <input
                type="number"
                step="0.1"
                value={calcPrice}
                onChange={e => setCalcPrice(parseFloat(e.target.value) || 0)}
                className="w-full bg-[#10141e] border border-slate-700 rounded px-2 py-1 text-xs font-mono text-white mt-1 outline-none"
              />
            </div>

            <div>
              <label className="text-[10px] text-slate-400 font-mono">Size</label>
              <input
                type="number"
                step="0.01"
                value={calcQty}
                onChange={e => setCalcQty(parseFloat(e.target.value) || 0.1)}
                className="w-full bg-[#10141e] border border-slate-700 rounded px-2 py-1 text-xs font-mono text-white mt-1 outline-none"
              />
            </div>
          </div>

          {/* QUEUE RESULTS CARD */}
          {queueEstimate && (
            <div className="space-y-3 font-mono text-xs">
              <div className="p-3 bg-[#0d111a] border border-slate-800 rounded-lg space-y-2">
                <div className="flex justify-between items-center text-slate-400 text-xs">
                  <span>Relative Queue Position:</span>
                  <span className="font-bold text-white text-sm">
                    {queueEstimate.relative_queue_position_pct}%
                  </span>
                </div>
                {/* Visual Position Progress Bar */}
                <div className="w-full bg-slate-800 h-2 rounded-full overflow-hidden">
                  <div
                    className="bg-cyan-500 h-full rounded-full transition-all"
                    style={{ width: `${Math.min(100, queueEstimate.relative_queue_position_pct)}%` }}
                  />
                </div>
                <div className="flex justify-between text-[11px] text-slate-400">
                  <span>Queue Ahead: {queueEstimate.queue_ahead_qty} ({queueEstimate.queue_ahead_orders} ords)</span>
                  <span>Behind: {queueEstimate.queue_behind_qty}</span>
                </div>
              </div>

              {/* ESTIMATED WAIT TIME & DEPLETION */}
              <div className="grid grid-cols-2 gap-2">
                <div className="p-2.5 bg-[#0d111a] border border-slate-800 rounded-lg">
                  <div className="text-slate-400 text-[10px]">Expected Wait Time</div>
                  <div className="text-cyan-400 text-base font-bold mt-0.5">
                    {queueEstimate.expected_wait_seconds}s
                  </div>
                </div>
                <div className="p-2.5 bg-[#0d111a] border border-slate-800 rounded-lg">
                  <div className="text-slate-400 text-[10px]">Depletion Rate</div>
                  <div className="text-white text-base font-bold mt-0.5">
                    {queueEstimate.estimated_depletion_rate_qty_per_sec}/s
                  </div>
                </div>
              </div>

              {/* MULTI-HORIZON FILL PROBABILITY BARS */}
              <div className="p-3 bg-[#0d111a] border border-slate-800 rounded-lg space-y-2">
                <span className="text-[11px] font-bold text-slate-300 uppercase tracking-wider">
                  Fill Probability Horizons
                </span>
                
                {/* 30s */}
                <div className="space-y-1">
                  <div className="flex justify-between text-[11px]">
                    <span className="text-slate-400">30 Seconds:</span>
                    <span className="text-emerald-400 font-bold">
                      {(queueEstimate.fill_probability_30s * 100).toFixed(1)}%
                    </span>
                  </div>
                  <div className="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden">
                    <div
                      className="bg-emerald-500 h-full rounded-full"
                      style={{ width: `${queueEstimate.fill_probability_30s * 100}%` }}
                    />
                  </div>
                </div>

                {/* 60s */}
                <div className="space-y-1">
                  <div className="flex justify-between text-[11px]">
                    <span className="text-slate-400">60 Seconds:</span>
                    <span className="text-cyan-400 font-bold">
                      {(queueEstimate.fill_probability_60s * 100).toFixed(1)}%
                    </span>
                  </div>
                  <div className="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden">
                    <div
                      className="bg-cyan-500 h-full rounded-full"
                      style={{ width: `${queueEstimate.fill_probability_60s * 100}%` }}
                    />
                  </div>
                </div>

                {/* 300s */}
                <div className="space-y-1">
                  <div className="flex justify-between text-[11px]">
                    <span className="text-slate-400">300 Seconds (5m):</span>
                    <span className="text-purple-400 font-bold">
                      {(queueEstimate.fill_probability_300s * 100).toFixed(1)}%
                    </span>
                  </div>
                  <div className="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden">
                    <div
                      className="bg-purple-500 h-full rounded-full"
                      style={{ width: `${queueEstimate.fill_probability_300s * 100}%` }}
                    />
                  </div>
                </div>
              </div>

              {/* ADVERSE SELECTION ADVICE */}
              <div className={`p-2.5 rounded-lg border flex items-center space-x-2.5 ${
                queueEstimate.adverse_selection_risk_score > 0.6
                  ? 'bg-rose-500/10 border-rose-500/30 text-rose-300'
                  : 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
              }`}>
                <ShieldCheck className="w-4 h-4 flex-shrink-0" />
                <div className="text-[11px]">
                  Adverse Selection Risk: <span className="font-bold">{(queueEstimate.adverse_selection_risk_score * 100).toFixed(0)}%</span>
                  {queueEstimate.adverse_selection_risk_score > 0.6
                    ? ' — High toxic fill hazard. Recommend aggressive taker route or wide offset.'
                    : ' — Favorable passive queue placement. Maker fee capture favored.'}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* DETECTED ICEBERG ORDERS TABLE */}
      <div className="bg-[#10141e] border border-slate-800 rounded-xl p-4 flex flex-col space-y-3">
        <div className="flex items-center justify-between border-b border-slate-800 pb-2">
          <span className="text-xs font-bold uppercase tracking-wider text-slate-200 flex items-center space-x-2">
            <Eye className="w-4 h-4 text-purple-400" />
            <span>Active Institutional Iceberg Orders</span>
          </span>
          <span className="text-xs font-mono text-purple-400">
            {icebergs.length} Identified Hidden Walls
          </span>
        </div>

        {icebergs.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs font-mono">
              <thead className="bg-[#0d111a] text-slate-400 border-b border-slate-800">
                <tr>
                  <th className="p-2.5">Iceberg ID</th>
                  <th className="p-2.5">Side</th>
                  <th className="p-2.5">Price</th>
                  <th className="p-2.5">Displayed Size</th>
                  <th className="p-2.5">Cum. Executed</th>
                  <th className="p-2.5">Est. Hidden Qty</th>
                  <th className="p-2.5">Total Size</th>
                  <th className="p-2.5">Confidence</th>
                  <th className="p-2.5">Reloads</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {icebergs.map(ice => (
                  <tr key={ice.iceberg_id} className="hover:bg-slate-800/30">
                    <td className="p-2.5 text-slate-300 font-bold">{ice.iceberg_id.slice(0, 18)}...</td>
                    <td className="p-2.5">
                      <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                        ice.side === 'BID'
                          ? 'bg-emerald-500/20 text-emerald-400'
                          : 'bg-rose-500/20 text-rose-400'
                      }`}>
                        {ice.side}
                      </span>
                    </td>
                    <td className="p-2.5 text-white font-bold">{ice.price.toFixed(2)}</td>
                    <td className="p-2.5 text-slate-300">{ice.initial_displayed_size.toFixed(4)}</td>
                    <td className="p-2.5 text-cyan-400">{ice.cumulative_executed_size.toFixed(4)}</td>
                    <td className="p-2.5 text-purple-400 font-bold">{ice.estimated_total_hidden_qty.toFixed(4)}</td>
                    <td className="p-2.5 text-amber-400">{ice.total_estimated_size.toFixed(4)}</td>
                    <td className="p-2.5">
                      <span className="text-emerald-400 font-bold">
                        {(ice.confidence_score * 100).toFixed(0)}%
                      </span>
                    </td>
                    <td className="p-2.5 text-slate-300">{ice.reload_count}x</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="p-6 text-center text-slate-500 font-mono text-xs">
            Scanning multi-venue order execution streams for algorithmic reload signatures...
          </div>
        )}
      </div>
    </div>
  );
};
