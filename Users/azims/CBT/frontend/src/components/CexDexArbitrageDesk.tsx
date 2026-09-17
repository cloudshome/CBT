import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Activity,
  AlertTriangle,
  ArrowRightLeft,
  Cpu,
  Layers,
  Percent,
  Play,
  RefreshCw,
  Scale,
  Shield,
  ShieldCheck,
  Zap,
} from 'lucide-react';
import {
  CexDexScanResponse,
  CexDexShadowRecord,
  executeCexDexShadow,
  getCexDexShadowHistory,
  scanCexDexPair,
} from '../services/api';

interface CexDexArbitrageDeskProps {
  currentSymbol?: string;
  onNotify?: (type: 'success' | 'error' | 'warning' | 'info', title: string, message: string) => void;
}

const SUPPORTED_PAIRS = [
  { symbol: 'ETHUSDC', label: 'ETH/USDC (Arbitrum - Uniswap V3)' },
  { symbol: 'SOLUSDC', label: 'SOL/USDC (Solana - Raydium CLMM)' },
];

export const CexDexArbitrageDesk: React.FC<CexDexArbitrageDeskProps> = ({
  currentSymbol = 'ETHUSDC',
  onNotify,
}) => {
  const [selectedSymbol, setSelectedSymbol] = useState<string>(
    SUPPORTED_PAIRS.some((p) => p.symbol === currentSymbol) ? currentSymbol : 'ETHUSDC'
  );
  const [notionalUsd, setNotionalUsd] = useState<number>(10000);
  const [isPrivateRpc, setIsPrivateRpc] = useState<boolean>(true);
  const [scanData, setScanData] = useState<CexDexScanResponse | null>(null);
  const [shadowHistory, setShadowHistory] = useState<CexDexShadowRecord[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [isExecuting, setIsExecuting] = useState<boolean>(false);
  const [lastScanTime, setLastScanTime] = useState<Date>(new Date());

  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  const fetchScan = useCallback(async () => {
    try {
      setLoading(true);
      const [res, hist] = await Promise.all([
        scanCexDexPair(selectedSymbol, notionalUsd, isPrivateRpc),
        getCexDexShadowHistory(15),
      ]);
      setScanData(res);
      setShadowHistory(hist.shadow_records || []);
      setLastScanTime(new Date());
    } catch (err: any) {
      console.error('CEX-DEX scan error:', err);
      onNotify?.('error', 'CEX-DEX Scan Error', err.message || 'Failed connecting to CEX-DEX endpoints.');
    } finally {
      setLoading(false);
    }
  }, [selectedSymbol, notionalUsd, isPrivateRpc, onNotify]);

  useEffect(() => {
    fetchScan();
    const interval = setInterval(fetchScan, 10000); // 10s auto-refresh
    return () => clearInterval(interval);
  }, [fetchScan]);

  const handleExecuteShadow = async () => {
    try {
      setIsExecuting(true);
      const res = await executeCexDexShadow(selectedSymbol, notionalUsd);
      onNotify?.('success', 'Shadow Trade Executed', `Simulated trade ${res.shadow_trade_id} committed to research ledger.`);
      fetchScan();
    } catch (err: any) {
      onNotify?.('error', 'Shadow Execution Failed', err.message || 'Failed executing shadow trade.');
    } finally {
      setIsExecuting(false);
    }
  };

  // Render CLMM Liquidity Density on HTML5 Canvas
  useEffect(() => {
    if (!canvasRef.current || !scanData) return;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const width = canvas.width;
    const height = canvas.height;
    ctx.clearRect(0, 0, width, height);

    // Background grid
    ctx.fillStyle = '#0f172a';
    ctx.fillRect(0, 0, width, height);

    ctx.strokeStyle = '#1e293b';
    ctx.lineWidth = 1;
    for (let x = 0; x < width; x += 40) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, height);
      ctx.stroke();
    }
    for (let y = 0; y < height; y += 30) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(width, y);
      ctx.stroke();
    }

    // Concentrated liquidity curve around spot price
    const spot = scanData.pool_state.spot_price;
    const pa = scanData.carry_metrics.lp_lower_price;
    const pb = scanData.carry_metrics.lp_upper_price;

    const numBins = 40;
    const minP = spot * 0.8;
    const maxP = spot * 1.2;

    const binWidth = width / numBins;
    for (let i = 0; i < numBins; i++) {
      const binPrice = minP + (i / numBins) * (maxP - minP);
      const inRange = binPrice >= pa && binPrice <= pb;

      // Higher density in concentrated range
      const densityFactor = inRange ? 0.75 + 0.2 * Math.sin((i / numBins) * Math.PI) : 0.12;
      const barHeight = densityFactor * (height - 40);

      ctx.fillStyle = inRange ? 'rgba(16, 185, 129, 0.45)' : 'rgba(51, 65, 85, 0.35)';
      ctx.fillRect(i * binWidth, height - barHeight - 20, binWidth - 2, barHeight);

      if (inRange) {
        ctx.strokeStyle = '#10b981';
        ctx.lineWidth = 1;
        ctx.strokeRect(i * binWidth, height - barHeight - 20, binWidth - 2, barHeight);
      }
    }

    // Active spot price line
    const spotX = ((spot - minP) / (maxP - minP)) * width;
    ctx.strokeStyle = '#38bdf8';
    ctx.lineWidth = 2;
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(spotX, 0);
    ctx.lineTo(spotX, height);
    ctx.stroke();
    ctx.setLineDash([]);

    // Spot price label
    ctx.fillStyle = '#38bdf8';
    ctx.font = '10px monospace';
    ctx.fillText(`SPOT: $${spot.toFixed(2)}`, Math.min(spotX + 6, width - 90), 20);

    // Range markers
    const paX = ((pa - minP) / (maxP - minP)) * width;
    const pbX = ((pb - minP) / (maxP - minP)) * width;

    ctx.strokeStyle = '#f59e0b';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(paX, 0);
    ctx.lineTo(paX, height);
    ctx.moveTo(pbX, 0);
    ctx.lineTo(pbX, height);
    ctx.stroke();

    ctx.fillStyle = '#f59e0b';
    ctx.fillText(`Pa: $${pa.toFixed(0)}`, Math.max(paX - 50, 5), height - 6);
    ctx.fillText(`Pb: $${pb.toFixed(0)}`, Math.min(pbX + 5, width - 60), height - 6);
  }, [scanData]);

  const opp = scanData?.opportunity;
  const pool = scanData?.pool_state;
  const cex = scanData?.cex_execution;
  const survival = scanData?.survival_simulation;
  const carry = scanData?.carry_metrics;
  const clf = scanData?.classification;

  return (
    <div className="flex flex-col h-full bg-slate-950 text-slate-100 p-4 space-y-4 overflow-y-auto">
      {/* Top Telemetry & Control Bar */}
      <div className="flex flex-wrap items-center justify-between gap-4 p-3 bg-slate-900 border border-slate-800 rounded-lg">
        <div className="flex items-center space-x-3">
          <div className="p-2 bg-emerald-500/10 border border-emerald-500/30 rounded-md">
            <ArrowRightLeft size={20} className="text-emerald-400" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <span className="font-bold text-base text-slate-100">
                Institutional CEX-DEX Basis & CLMM Arbitrage Desk
              </span>
              <span className="px-2 py-0.5 text-xs font-semibold bg-indigo-500/20 text-indigo-400 border border-indigo-500/40 rounded">
                DEFI FRONTIER
              </span>
              <span className="px-2 py-0.5 text-xs font-semibold bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 rounded">
                WATCH-ONLY ISOLATED
              </span>
            </div>
            <p className="text-xs text-slate-400">
              Exact Q64.96 integer CLMM traversal, 500-scenario Monte Carlo survival, and modeled carry hedging
            </p>
          </div>
        </div>

        {/* Action & Configuration Controls */}
        <div className="flex items-center space-x-3">
          {/* Pair Selector */}
          <select
            value={selectedSymbol}
            onChange={(e) => setSelectedSymbol(e.target.value)}
            className="px-3 py-1.5 bg-slate-800 border border-slate-700 rounded text-xs text-slate-200 focus:outline-none focus:border-emerald-500"
          >
            {SUPPORTED_PAIRS.map((p) => (
              <option key={p.symbol} value={p.symbol}>
                {p.label}
              </option>
            ))}
          </select>

          {/* Notional Size */}
          <div className="flex items-center space-x-1.5 px-2.5 py-1 bg-slate-800 border border-slate-700 rounded text-xs">
            <span className="text-slate-400">Size:</span>
            <span className="font-mono text-emerald-400 font-bold">${notionalUsd.toLocaleString()}</span>
            <input
              type="range"
              min="1000"
              max="100000"
              step="1000"
              value={notionalUsd}
              onChange={(e) => setNotionalUsd(Number(e.target.value))}
              className="w-20 accent-emerald-500 cursor-pointer"
            />
          </div>

          {/* Private RPC Toggle */}
          <button
            onClick={() => setIsPrivateRpc(!isPrivateRpc)}
            className={`flex items-center space-x-1 px-2.5 py-1.5 text-xs font-medium rounded border transition ${
              isPrivateRpc
                ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
                : 'bg-slate-800 text-slate-400 border-slate-700'
            }`}
            title="When active, routes via private relays to eliminate public mempool front-running"
          >
            <Shield size={13} />
            <span>{isPrivateRpc ? 'Private RPC (Protected)' : 'Public Mempool'}</span>
          </button>

          {/* Manual Refresh */}
          <button
            onClick={fetchScan}
            disabled={loading}
            className="flex items-center space-x-1 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded text-xs text-slate-200 transition disabled:opacity-50"
          >
            <RefreshCw size={13} className={loading ? 'animate-spin text-emerald-400' : ''} />
            <span>Scan</span>
          </button>

          {/* Shadow Execution Button */}
          <button
            onClick={handleExecuteShadow}
            disabled={isExecuting}
            className="flex items-center space-x-1 px-3.5 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-slate-950 font-bold rounded text-xs shadow-lg transition disabled:opacity-50"
          >
            <Play size={13} />
            <span>{isExecuting ? 'Simulating...' : 'Shadow Execute'}</span>
          </button>
        </div>
      </div>

      {/* Quorum & Network Health Status Ribbon */}
      {pool && (
        <div className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 bg-slate-900/80 border border-slate-800/80 rounded-md text-xs">
          <div className="flex items-center space-x-4">
            <span className="flex items-center space-x-1 text-slate-400">
              <Cpu size={13} className="text-cyan-400" />
              <span>Chain:</span>
              <strong className="text-slate-200">{pool.chain} ({pool.dex_name})</strong>
            </span>
            <span className="flex items-center space-x-1 text-slate-400">
              <ShieldCheck size={13} className="text-emerald-400" />
              <span>Quorum Consensus:</span>
              <strong className="text-emerald-400 font-mono">
                {pool.quorum.consensus_status} ({pool.quorum.agreeing_node_count}/{pool.quorum.total_node_count} NODES)
              </strong>
            </span>
            <span className="flex items-center space-x-1 text-slate-400">
              <Activity size={13} className="text-indigo-400" />
              <span>Block:</span>
              <strong className="text-slate-200 font-mono">#{pool.quorum.canonical_block_number}</strong>
            </span>
            <span className="flex items-center space-x-1 text-slate-400">
              <Zap size={13} className="text-amber-400" />
              <span>Freshness:</span>
              <strong
                className={`font-mono ${
                  pool.quorum.freshness === 'FRESH'
                    ? 'text-emerald-400'
                    : pool.quorum.freshness === 'AGING'
                    ? 'text-amber-400'
                    : 'text-rose-400'
                }`}
              >
                {pool.quorum.freshness} ({pool.quorum.state_age_ms}ms)
              </strong>
            </span>
          </div>
          <div className="text-slate-500 text-[11px] font-mono">
            Last Updated: {lastScanTime.toLocaleTimeString()}
          </div>
        </div>
      )}

      {/* Main Quantitative Analytics Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Card 1: Concentrated Liquidity Density (CLMM) */}
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-3 flex flex-col space-y-3">
          <div className="flex items-center justify-between border-b border-slate-800 pb-2">
            <div className="flex items-center space-x-2">
              <Layers size={16} className="text-emerald-400" />
              <span className="font-semibold text-sm text-slate-200">CLMM Liquidity Concentration</span>
            </div>
            {pool && (
              <span className="text-[11px] font-mono text-slate-400">
                Fee Tier: {(pool.fee_pips / 100).toFixed(2)} bps
              </span>
            )}
          </div>

          <div className="relative w-full h-44 bg-slate-950 rounded border border-slate-800 overflow-hidden">
            <canvas ref={canvasRef} width={380} height={176} className="w-full h-full block" />
          </div>

          {pool && opp && (
            <div className="grid grid-cols-2 gap-2 text-xs font-mono">
              <div className="p-2 bg-slate-950 border border-slate-800/80 rounded">
                <div className="text-slate-400 text-[10px]">DEX EFFECTIVE PRICE</div>
                <div className="text-emerald-400 font-bold text-sm">${opp.dex_effective_price.toFixed(2)}</div>
                <div className="text-[10px] text-slate-500">
                  Impact: +{opp.dex_marginal_slippage_bps.toFixed(1)} bps
                </div>
              </div>
              <div className="p-2 bg-slate-950 border border-slate-800/80 rounded">
                <div className="text-slate-400 text-[10px]">CURRENT TICK</div>
                <div className="text-cyan-400 font-bold text-sm">#{pool.current_tick}</div>
                <div className="text-[10px] text-slate-500">Active L: {pool.active_liquidity.slice(0, 8)}...</div>
              </div>
            </div>
          )}
        </div>

        {/* Card 2: CEX vs DEX Basis & Multi-Axis Radar */}
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-3 flex flex-col space-y-3">
          <div className="flex items-center justify-between border-b border-slate-800 pb-2">
            <div className="flex items-center space-x-2">
              <Scale size={16} className="text-cyan-400" />
              <span className="font-semibold text-sm text-slate-200">Basis Dislocation & EV Hurdle</span>
            </div>
            {opp && (
              <span
                className={`px-2 py-0.5 text-xs font-bold rounded ${
                  opp.gross_basis_bps >= 15 ? 'bg-emerald-500/20 text-emerald-400' : 'bg-slate-800 text-slate-400'
                }`}
              >
                GROSS: +{opp.gross_basis_bps.toFixed(1)} bps
              </span>
            )}
          </div>

          {/* 6-Axis Multi-Dimensional Badges */}
          {clf && (
            <div className="flex flex-wrap gap-1.5">
              <span
                className={`px-2 py-0.5 text-[10px] font-bold rounded border ${
                  clf.economic === 'PROFITABLE'
                    ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
                    : clf.economic === 'UNCERTAIN'
                    ? 'bg-amber-500/20 text-amber-300 border-amber-500/40'
                    : 'bg-rose-500/20 text-rose-300 border-rose-500/40'
                }`}
              >
                ECON: {clf.economic}
              </span>
              <span className="px-2 py-0.5 text-[10px] font-bold bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 rounded">
                DATA: {clf.data_freshness}
              </span>
              <span className="px-2 py-0.5 text-[10px] font-bold bg-indigo-500/20 text-indigo-300 border border-indigo-500/40 rounded">
                EXEC: {clf.execution}
              </span>
              <span className="px-2 py-0.5 text-[10px] font-bold bg-purple-500/20 text-purple-300 border border-purple-500/40 rounded">
                MEV: {clf.mev}
              </span>
              <span
                className={`px-2 py-0.5 text-[10px] font-bold rounded border ${
                  clf.hedge === 'NEUTRAL'
                    ? 'bg-teal-500/20 text-teal-300 border-teal-500/40'
                    : 'bg-orange-500/20 text-orange-300 border-orange-500/40'
                }`}
              >
                HEDGE: {clf.hedge}
              </span>
            </div>
          )}

          {/* Monte Carlo Survival Waterfall */}
          {survival && opp && (
            <div className="space-y-2 text-xs">
              <div className="p-2.5 bg-slate-950 border border-slate-800 rounded space-y-1.5">
                <div className="text-slate-400 font-medium text-[11px]">
                  500-SCENARIO MONTE CARLO NET EV (GATE 12)
                </div>
                <div className="grid grid-cols-3 gap-2 font-mono text-center">
                  <div className="p-1.5 bg-slate-900 rounded">
                    <div className="text-[10px] text-slate-500">P05 (VaR)</div>
                    <div
                      className={`font-bold ${
                        survival.p05_net_ev >= 0 ? 'text-emerald-400' : 'text-rose-400'
                      }`}
                    >
                      ${survival.p05_net_ev.toFixed(2)}
                    </div>
                  </div>
                  <div className="p-1.5 bg-slate-900 rounded">
                    <div className="text-[10px] text-slate-500">P50 (Median)</div>
                    <div
                      className={`font-bold ${
                        survival.p50_net_ev >= 0 ? 'text-emerald-400' : 'text-rose-400'
                      }`}
                    >
                      ${survival.p50_net_ev.toFixed(2)}
                    </div>
                  </div>
                  <div className="p-1.5 bg-slate-900 rounded">
                    <div className="text-[10px] text-slate-500">P95 (Upside)</div>
                    <div className="text-cyan-400 font-bold">${survival.p95_net_ev.toFixed(2)}</div>
                  </div>
                </div>

                <div className="flex items-center justify-between pt-1 border-t border-slate-800/80 text-[11px]">
                  <span className="text-slate-400">Break-Even Hurdle:</span>
                  <span className="font-mono text-amber-400 font-semibold">
                    {survival.break_even_hurdle_bps.toFixed(1)} bps
                  </span>
                </div>
                <div className="flex items-center justify-between text-[11px]">
                  <span className="text-slate-400">Loss / Revert Prob:</span>
                  <span className="font-mono text-slate-300">
                    {(survival.loss_probability * 100).toFixed(1)}% / {(survival.revert_probability * 100).toFixed(1)}%
                  </span>
                </div>
              </div>

              {cex && (
                <div className="flex items-center justify-between text-[11px] px-1 font-mono text-slate-400">
                  <span>CEX ({cex.venue}) VWAP: <strong className="text-slate-200">${cex.vwap_price.toFixed(2)}</strong></span>
                  <span>Fill: <strong className="text-emerald-400">{(cex.fill_ratio * 100).toFixed(0)}%</strong></span>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Card 3: Modeled Delta-Neutral Carry & Hedging Radar */}
        <div className="bg-slate-900 border border-slate-800 rounded-lg p-3 flex flex-col space-y-3">
          <div className="flex items-center justify-between border-b border-slate-800 pb-2">
            <div className="flex items-center space-x-2">
              <Percent size={16} className="text-amber-400" />
              <span className="font-semibold text-sm text-slate-200">Modeled Delta-Neutral Carry</span>
            </div>
            {carry && (
              <span
                className={`px-2 py-0.5 text-xs font-bold rounded ${
                  carry.is_rebalance_required
                    ? 'bg-rose-500/20 text-rose-400 border border-rose-500/40'
                    : 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40'
                }`}
              >
                {carry.is_rebalance_required ? 'REBALANCE REQUIRED' : 'DELTA NEUTRAL'}
              </span>
            )}
          </div>

          {carry && (
            <div className="space-y-2.5 text-xs">
              <div className="p-2.5 bg-slate-950 border border-slate-800 rounded space-y-2 font-mono">
                <div className="flex items-center justify-between">
                  <span className="text-slate-400">Net Carry APY:</span>
                  <span className="text-emerald-400 font-bold text-sm">
                    {carry.net_carry_apy_percent >= 0 ? '+' : ''}
                    {carry.net_carry_apy_percent.toFixed(1)}%
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-2 text-[11px] pt-1 border-t border-slate-800/80">
                  <div>
                    <span className="text-slate-500">DEX Fee APY:</span>
                    <div className="text-slate-200 font-semibold">+{carry.annualized_fee_apy_percent.toFixed(1)}%</div>
                  </div>
                  <div>
                    <span className="text-slate-500">CEX Funding APY:</span>
                    <div className="text-cyan-400 font-semibold">+{carry.annualized_funding_apy_percent.toFixed(1)}%</div>
                  </div>
                  <div>
                    <span className="text-slate-500">Divergence Loss:</span>
                    <div className="text-rose-400 font-semibold">{carry.divergence_loss_percent.toFixed(1)}%</div>
                  </div>
                  <div>
                    <span className="text-slate-500">Net Delta:</span>
                    <div
                      className={`font-semibold ${
                        Math.abs(carry.net_modeled_delta_base) > 0.05 ? 'text-rose-400' : 'text-emerald-400'
                      }`}
                    >
                      {carry.net_modeled_delta_base > 0 ? '+' : ''}
                      {carry.net_modeled_delta_base.toFixed(3)}
                    </div>
                  </div>
                </div>
              </div>

              {/* Liquidation Sentinel Gauge */}
              <div className="p-2 bg-slate-950 border border-slate-800 rounded space-y-1.5">
                <div className="flex items-center justify-between text-[11px]">
                  <span className="flex items-center space-x-1 text-slate-400">
                    <AlertTriangle size={12} className={carry.liquidation_risk_alert ? 'text-rose-400' : 'text-slate-500'} />
                    <span>CEX Liquidation Buffer:</span>
                  </span>
                  <span
                    className={`font-mono font-bold ${
                      carry.liquidation_risk_alert ? 'text-rose-400' : 'text-emerald-400'
                    }`}
                  >
                    {carry.distance_to_liquidation_percent.toFixed(1)}%
                  </span>
                </div>
                <div className="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden">
                  <div
                    className={`h-full transition-all ${
                      carry.distance_to_liquidation_percent < 15
                        ? 'bg-rose-500'
                        : carry.distance_to_liquidation_percent < 30
                        ? 'bg-amber-500'
                        : 'bg-emerald-500'
                    }`}
                    style={{ width: `${Math.min(100, carry.distance_to_liquidation_percent * 2)}%` }}
                  />
                </div>
                <div className="flex justify-between text-[10px] text-slate-500 font-mono">
                  <span>Liq Price: ${carry.cex_liquidation_price.toFixed(0)}</span>
                  <span>Safety Margin: {carry.liquidation_risk_alert ? 'DANGER' : 'SAFE'}</span>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Bottom Panel: Immutable Research Shadow Ledger Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-lg p-3 flex flex-col space-y-2 flex-1 min-h-[160px]">
        <div className="flex items-center justify-between border-b border-slate-800 pb-2">
          <div className="flex items-center space-x-2">
            <Activity size={16} className="text-indigo-400" />
            <span className="font-semibold text-sm text-slate-200">
              Immutable Research Shadow Ledger (data/cexdex_shadow.db)
            </span>
            <span className="px-2 py-0.5 text-[10px] bg-slate-800 text-slate-400 rounded">
              {shadowHistory.length} Simulated Executions
            </span>
          </div>
          <span className="text-xs text-slate-500">Gate 10: Watch-Only Research Provenance</span>
        </div>

        <div className="overflow-x-auto flex-1">
          <table className="w-full text-left text-xs font-mono">
            <thead>
              <tr className="border-b border-slate-800 text-slate-500 text-[11px]">
                <th className="py-1.5 px-2">SHADOW ID</th>
                <th className="py-1.5 px-2">TIME</th>
                <th className="py-1.5 px-2">PAIR</th>
                <th className="py-1.5 px-2">CHAIN / DEX</th>
                <th className="py-1.5 px-2">DIRECTION</th>
                <th className="py-1.5 px-2">NOTIONAL</th>
                <th className="py-1.5 px-2">GROSS BASIS</th>
                <th className="py-1.5 px-2">P50 NET EV</th>
                <th className="py-1.5 px-2">QUORUM</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/50 text-slate-300">
              {shadowHistory.length === 0 ? (
                <tr>
                  <td colSpan={9} className="py-4 text-center text-slate-500">
                    No simulated shadow trades recorded yet. Click &apos;Shadow Execute&apos; to commit a research entry.
                  </td>
                </tr>
              ) : (
                shadowHistory.map((trade) => (
                  <tr key={trade.shadow_id} className="hover:bg-slate-800/40 transition">
                    <td className="py-1 px-2 text-indigo-400 font-semibold">{trade.shadow_id.slice(0, 16)}...</td>
                    <td className="py-1 px-2 text-slate-400">
                      {new Date(trade.timestamp_ns / 1_000_000).toLocaleTimeString()}
                    </td>
                    <td className="py-1 px-2 font-bold text-slate-200">{trade.symbol}</td>
                    <td className="py-1 px-2 text-slate-400">
                      {trade.chain} ({trade.dex_name})
                    </td>
                    <td className="py-1 px-2 text-emerald-400">{trade.direction}</td>
                    <td className="py-1 px-2">${trade.notional_usd.toLocaleString()}</td>
                    <td className="py-1 px-2 text-cyan-400">+{trade.gross_basis_bps.toFixed(1)} bps</td>
                    <td className="py-1 px-2 font-bold text-emerald-400">${trade.survival_p50_ev.toFixed(2)}</td>
                    <td className="py-1 px-2 text-slate-400">{trade.rpc_consensus_status}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
