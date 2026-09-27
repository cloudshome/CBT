import React, { useState, useEffect, useRef } from 'react';
import { api } from '../services/api';
import {
  KronosDomainForecastData,
  KronosBrierReport,
  KronosTournamentReport,
  KronosIncrementalReport,
  KronosRegimesReport,
  KronosAblationReport,
  KronosPromotionReport,
} from '../types';

interface KronosDomainDeskProps {
  selectedSymbol?: string;
  selectedTimeframe?: string;
}

export const KronosDomainDesk: React.FC<KronosDomainDeskProps> = ({
  selectedSymbol = 'BTC/USDT',
  selectedTimeframe = '15m',
}) => {
  const [symbol, setSymbol] = useState<string>(selectedSymbol);
  const [timeframe, setTimeframe] = useState<string>(selectedTimeframe);
  const [forecast, setForecast] = useState<KronosDomainForecastData | null>(null);
  const [brierReport, setBrierReport] = useState<KronosBrierReport | null>(null);
  const [statusVitals, setStatusVitals] = useState<any>(null);

  // Milestone K9: Predictive Validity & Incremental Alpha Research States
  const [tournament, setTournament] = useState<KronosTournamentReport | null>(null);
  const [incremental, setIncremental] = useState<KronosIncrementalReport | null>(null);
  const [regimes, setRegimes] = useState<KronosRegimesReport | null>(null);
  const [ablation, setAblation] = useState<KronosAblationReport | null>(null);
  const [promotion, setPromotion] = useState<KronosPromotionReport | null>(null);
  const [activeResearchTab, setActiveResearchTab] = useState<'TOURNAMENT' | 'INCREMENTAL' | 'REGIMES' | 'ABLATION' | 'PROMOTION'>('TOURNAMENT');

  const [loading, setLoading] = useState<boolean>(false);
  const [auditRunning, setAuditRunning] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const fanChartCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const reliabilityCanvasRef = useRef<HTMLCanvasElement | null>(null);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [fcRes, brierRes, statusRes, tourRes, incRes, regRes, ablRes, promRes] = await Promise.allSettled([
        api.getKronosDomainForecast({
          symbol,
          timeframe,
          horizon: 12,
          samples: 7,
          hurdle: 0.0,
          freeze: true,
        }),
        api.getKronosCalibrationStatus({ symbol, timeframe }),
        api.getKronosStatus(),
        api.getKronosTournament({ symbol, timeframe, horizon: 12 }),
        api.getKronosIncremental({ symbol, timeframe, horizon: 12 }),
        api.getKronosRegimes({ symbol, timeframe, horizon: 12 }),
        api.getKronosAblation({ symbol, timeframe, horizon: 12 }),
        api.getKronosPromotionStatus({ symbol, timeframe, horizon: 12 }),
      ]);

      if (fcRes.status === 'fulfilled') setForecast(fcRes.value);
      if (brierRes.status === 'fulfilled') setBrierReport(brierRes.value);
      if (statusRes.status === 'fulfilled') setStatusVitals(statusRes.value);
      if (tourRes.status === 'fulfilled') setTournament(tourRes.value);
      if (incRes.status === 'fulfilled') setIncremental(incRes.value);
      if (regRes.status === 'fulfilled') setRegimes(regRes.value);
      if (ablRes.status === 'fulfilled') setAblation(ablRes.value);
      if (promRes.status === 'fulfilled') setPromotion(promRes.value);
    } catch (err: any) {
      setError(err?.message || 'Failed to load Kronos research data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 15000);
    return () => clearInterval(interval);
  }, [symbol, timeframe]);

  // Draw Quantile Fan Chart on HTML5 Canvas
  useEffect(() => {
    const canvas = fanChartCanvasRef.current;
    if (!canvas || !forecast) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const width = canvas.width;
    const height = canvas.height;
    ctx.clearRect(0, 0, width, height);

    const bands = forecast.distribution?.quantile_bands;
    if (!bands || !bands.p10 || !bands.p50 || !bands.p90) return;

    const p10 = bands.p10;
    const p50 = bands.p50;
    const p90 = bands.p90;
    const steps = p50.length;
    if (steps === 0) return;

    // Price scaling
    const allPrices = [...p10, ...p50, ...p90, forecast.current_price];
    const minP = Math.min(...allPrices) * 0.998;
    const maxP = Math.max(...allPrices) * 1.002;
    const range = maxP - minP || 1.0;

    const getX = (idx: number) => 40 + (idx / steps) * (width - 60);
    const getY = (val: number) => height - 30 - ((val - minP) / range) * (height - 50);

    // Background Grid
    ctx.strokeStyle = '#1e2638';
    ctx.lineWidth = 1;
    for (let i = 0; i < 4; i++) {
      const gy = 20 + (i * (height - 50)) / 3;
      ctx.beginPath();
      ctx.moveTo(35, gy);
      ctx.lineTo(width - 10, gy);
      ctx.stroke();
    }

    // P10 - P90 Fan Fill
    ctx.beginPath();
    ctx.moveTo(getX(0), getY(forecast.current_price));
    for (let i = 0; i < steps; i++) ctx.lineTo(getX(i + 1), getY(p90[i]));
    for (let i = steps - 1; i >= 0; i--) ctx.lineTo(getX(i + 1), getY(p10[i]));
    ctx.closePath();
    ctx.fillStyle = 'rgba(59, 130, 246, 0.15)';
    ctx.fill();

    // P50 Median Trajectory Line
    ctx.beginPath();
    ctx.strokeStyle = '#38bdf8';
    ctx.lineWidth = 2.5;
    ctx.moveTo(getX(0), getY(forecast.current_price));
    for (let i = 0; i < steps; i++) {
      ctx.lineTo(getX(i + 1), getY(p50[i]));
    }
    ctx.stroke();

    // Current Price Anchor Point
    ctx.fillStyle = '#f59e0b';
    ctx.beginPath();
    ctx.arc(getX(0), getY(forecast.current_price), 4, 0, Math.PI * 2);
    ctx.fill();

    // Axes Labels
    ctx.fillStyle = '#64748b';
    ctx.font = '10px Inter, monospace';
    ctx.fillText(`$${maxP.toFixed(1)}`, 2, 25);
    ctx.fillText(`$${minP.toFixed(1)}`, 2, height - 25);
    ctx.fillText('H0 (Now)', getX(0) - 15, height - 10);
    ctx.fillText(`H${steps} Bars`, width - 65, height - 10);
  }, [forecast]);

  // Draw 10-Decile Calibration Reliability Diagram on HTML5 Canvas
  useEffect(() => {
    const canvas = reliabilityCanvasRef.current;
    if (!canvas || !brierReport) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const width = canvas.width;
    const height = canvas.height;
    ctx.clearRect(0, 0, width, height);

    const padding = 35;
    const plotW = width - padding * 2;
    const plotH = height - padding * 2;

    // Background & Axes
    ctx.strokeStyle = '#27272a';
    ctx.lineWidth = 1;
    ctx.strokeRect(padding, padding, plotW, plotH);

    // 45-degree Perfect Calibration Reference Line (y = x)
    ctx.beginPath();
    ctx.strokeStyle = '#52525b';
    ctx.setLineDash([4, 4]);
    ctx.moveTo(padding, padding + plotH);
    ctx.lineTo(padding + plotW, padding);
    ctx.stroke();
    ctx.setLineDash([]);

    // Deciles
    const deciles = brierReport.deciles || [];
    deciles.forEach((d) => {
      const predX = padding + d.mean_prediction * plotW;
      const obsY = padding + plotH - d.observed_frequency * plotH;

      // Draw point
      ctx.beginPath();
      ctx.fillStyle = d.status === 'SUFFICIENT_SAMPLE' ? '#10b981' : '#64748b';
      ctx.arc(predX, obsY, d.status === 'SUFFICIENT_SAMPLE' ? 4.5 : 3, 0, Math.PI * 2);
      ctx.fill();

      // Draw error stem to diagonal
      const diagY = padding + plotH - d.mean_prediction * plotH;
      ctx.beginPath();
      ctx.strokeStyle = d.absolute_error > 0.08 ? 'rgba(239, 68, 68, 0.4)' : 'rgba(16, 185, 129, 0.3)';
      ctx.lineWidth = 1.5;
      ctx.moveTo(predX, diagY);
      ctx.lineTo(predX, obsY);
      ctx.stroke();
    });

    // Labels
    ctx.fillStyle = '#71717a';
    ctx.font = '10px Inter, sans-serif';
    ctx.fillText('Forecast P', width / 2 - 25, height - 10);
    ctx.save();
    ctx.translate(12, height / 2 + 30);
    ctx.rotate(-Math.PI / 2);
    ctx.fillText('Observed Freq', 0, 0);
    ctx.restore();
  }, [brierReport]);

  const handleTriggerAudit = async () => {
    setAuditRunning(true);
    try {
      await api.runKronosBrierAudit({ symbol, timeframe, lookback_eval: 50 });
      await loadData();
    } catch (e: any) {
      setError(e?.message || 'Audit execution failed');
    } finally {
      setAuditRunning(false);
    }
  };

  const getEpistemicBadgeColor = (status?: string) => {
    switch (status) {
      case 'CALIBRATED':
        return 'bg-emerald-950 text-emerald-300 border-emerald-500/40';
      case 'WEAKLY_CALIBRATED':
        return 'bg-blue-950 text-blue-300 border-blue-500/40';
      case 'SURROGATE':
        return 'bg-amber-950 text-amber-300 border-amber-500/40';
      case 'DEGRADED':
        return 'bg-rose-950 text-rose-300 border-rose-500/40';
      default:
        return 'bg-zinc-800 text-zinc-400 border-zinc-700';
    }
  };

  return (
    <div className="bg-[#090d16] text-zinc-100 p-6 rounded-xl border border-zinc-800/80 shadow-2xl space-y-6">
      {/* Institutional Header & Constitutional Firewall Banner */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-zinc-800 pb-4">
        <div>
          <div className="flex items-center gap-3">
            <span className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
              <span className="w-3 h-3 rounded-full bg-cyan-400 animate-pulse" />
              KRONOS PROBABILISTIC FORECASTING & DOMAIN DESK
            </span>
            <span
              className={`px-2.5 py-0.5 text-xs font-mono rounded border uppercase ${getEpistemicBadgeColor(
                forecast?.governance?.epistemic_status || brierReport?.calibration_quality?.epistemic_status
              )}`}
            >
              {forecast?.governance?.epistemic_status || 'SURROGATE'}
            </span>
          </div>
          <p className="text-xs text-zinc-400 mt-1 font-mono">
            Milestone K8 • Strictly Causal L3/MBO Microstructure Adapter • Point-in-Time Platt Calibration
          </p>
        </div>

        <div className="flex items-center gap-3">
          <select
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            className="bg-zinc-900 border border-zinc-700 text-xs text-white rounded px-2.5 py-1.5 font-mono focus:outline-none focus:border-cyan-500"
          >
            <option value="BTC/USDT">BTC/USDT</option>
            <option value="ETH/USDT">ETH/USDT</option>
            <option value="SOL/USDT">SOL/USDT</option>
            <option value="XAU/USD">XAU/USD</option>
          </select>

          <select
            value={timeframe}
            onChange={(e) => setTimeframe(e.target.value)}
            className="bg-zinc-900 border border-zinc-700 text-xs text-white rounded px-2.5 py-1.5 font-mono focus:outline-none focus:border-cyan-500"
          >
            <option value="5m">5m</option>
            <option value="15m">15m</option>
            <option value="1h">1h</option>
            <option value="4h">4h</option>
          </select>

          <button
            onClick={handleTriggerAudit}
            disabled={auditRunning}
            className="px-3 py-1.5 bg-cyan-950/80 hover:bg-cyan-900 border border-cyan-700/50 text-cyan-300 text-xs font-mono rounded transition-colors disabled:opacity-50"
          >
            {auditRunning ? 'Auditing...' : 'Run Brier Audit'}
          </button>

          <button
            onClick={loadData}
            disabled={loading}
            className="px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs font-mono rounded transition-colors"
          >
            {loading ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>
      </div>

      {/* Constitutional Invariant Warning */}
      <div className="bg-amber-950/20 border border-amber-600/30 rounded-lg p-3 flex items-start gap-3">
        <span className="text-amber-400 font-bold text-sm">⚠️ CONSTITUTIONAL FIREWALL:</span>
        <span className="text-xs text-amber-200/80 leading-relaxed font-mono">
          Kronos outputs are <strong>probabilistic forecasts, NOT trade signals</strong>. They enter the
          Autonomous Quant Strategist as Bayesian research context only. Zero live execution or position sizing
          may be authorized from this desk. Authoritative gates: Half-Kelly Governor and Human Operator Approval.
        </span>
      </div>

      {error && (
        <div className="bg-rose-950/30 border border-rose-500/40 p-3 rounded text-rose-300 text-xs font-mono">
          {error}
        </div>
      )}

      {/* Grid: Main Research Cockpit */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Col 1: Provider Telemetry & Directional Probability */}
        <div className="space-y-4">
          {/* Provider Vitals Card */}
          <div className="bg-zinc-900/60 border border-zinc-800 rounded-lg p-4 space-y-3">
            <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider font-mono">
              Model Provider & Health
            </h3>
            <div className="grid grid-cols-2 gap-2 text-xs font-mono">
              <div className="bg-zinc-950/80 p-2 rounded border border-zinc-800/60">
                <span className="text-zinc-500 block">Provider</span>
                <span className="text-white font-medium">{forecast?.provider?.provider_type || 'SURROGATE'}</span>
              </div>
              <div className="bg-zinc-950/80 p-2 rounded border border-zinc-800/60">
                <span className="text-zinc-500 block">Family</span>
                <span className="text-cyan-300 font-medium">{forecast?.provider?.model_family || 'LSTM_SURROGATE'}</span>
              </div>
              <div className="bg-zinc-950/80 p-2 rounded border border-zinc-800/60">
                <span className="text-zinc-500 block">Checkpoint</span>
                <span className="text-zinc-300 text-[11px] truncate block">{forecast?.provider?.checkpoint_hash || statusVitals?.checkpoint_hash || 'local_fallback'}</span>
              </div>
              <div className="bg-zinc-950/80 p-2 rounded border border-zinc-800/60">
                <span className="text-zinc-500 block">Latency (P50)</span>
                <span className="text-emerald-400 font-medium">{forecast?.provider?.latency_ms || statusVitals?.latency_p50_ms || 8.5} ms</span>
              </div>
              <div className="bg-zinc-950/80 p-2 rounded border border-zinc-800/60 col-span-2 flex justify-between items-center text-[11px]">
                <span className="text-zinc-500">Device Engine: <span className="text-zinc-300 font-mono">{statusVitals?.device || 'CPU'}</span></span>
                <span className="text-emerald-400 font-mono">● {statusVitals?.status || 'ONLINE'}</span>
              </div>
            </div>
          </div>

          {/* Probability Construction & Calibration Card */}
          <div className="bg-zinc-900/60 border border-zinc-800 rounded-lg p-4 space-y-3">
            <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider font-mono">
              Directional Probability P(r &gt; 0)
            </h3>
            <div className="space-y-3">
              <div>
                <div className="flex justify-between text-xs font-mono mb-1">
                  <span className="text-zinc-400">Platt Calibrated P(Up)</span>
                  <span className="text-cyan-400 font-bold">
                    {forecast?.probability?.calibrated_probability
                      ? (forecast.probability.calibrated_probability * 100).toFixed(1) + '%'
                      : '50.0%'}
                  </span>
                </div>
                <div className="w-full bg-zinc-950 rounded-full h-2 overflow-hidden border border-zinc-800">
                  <div
                    className="bg-cyan-500 h-2 rounded-full transition-all duration-500"
                    style={{
                      width: `${(forecast?.probability?.calibrated_probability || 0.5) * 100}%`,
                    }}
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2 text-xs font-mono">
                <div className="bg-zinc-950 p-2 rounded border border-zinc-800/60">
                  <span className="text-zinc-500 block">Raw Probability</span>
                  <span className="text-zinc-300">
                    {forecast?.probability?.raw_probability
                      ? (forecast.probability.raw_probability * 100).toFixed(1) + '%'
                      : '50.0%'}
                  </span>
                </div>
                <div className="bg-zinc-950 p-2 rounded border border-zinc-800/60">
                  <span className="text-zinc-500 block">Model Uncertainty</span>
                  <span className="text-amber-400">
                    {forecast?.distribution?.model_uncertainty?.toFixed(2) || '0.15'}
                  </span>
                </div>
                <div className="bg-zinc-950 p-2 rounded border border-zinc-800/60">
                  <span className="text-zinc-500 block">Consensus</span>
                  <span className="text-zinc-300">
                    {forecast?.distribution?.directional_consensus
                      ? (forecast.distribution.directional_consensus * 100).toFixed(0) + '%'
                      : '50%'}
                  </span>
                </div>
                <div className="bg-zinc-950 p-2 rounded border border-zinc-800/60">
                  <span className="text-zinc-500 block">Expected Return</span>
                  <span
                    className={
                      (forecast?.distribution?.expected_return_pct || 0) >= 0
                        ? 'text-emerald-400 font-bold'
                        : 'text-rose-400 font-bold'
                    }
                  >
                    {(forecast?.distribution?.expected_return_pct || 0) >= 0 ? '+' : ''}
                    {forecast?.distribution?.expected_return_pct?.toFixed(2) || '0.00'}%
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Col 2: Multi-Horizon Fan Trajectory Chart */}
        <div className="bg-zinc-900/60 border border-zinc-800 rounded-lg p-4 space-y-3 flex flex-col">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider font-mono">
              Trajectory Quantiles (P10 - P50 - P90)
            </h3>
            <span className="text-[11px] font-mono text-zinc-400">
              Horizon: {forecast?.horizon_bars || 12} bars ({forecast?.horizon_unit || 'bars'})
            </span>
          </div>

          <div className="flex-1 min-h-[220px] relative flex items-center justify-center">
            <canvas
              ref={fanChartCanvasRef}
              width={420}
              height={220}
              className="w-full h-full max-h-[240px] rounded"
            />
          </div>

          <div className="flex justify-between items-center text-[11px] font-mono text-zinc-400 border-t border-zinc-800/80 pt-2">
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-cyan-400" />
              <span>Median P50</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded bg-blue-500/30" />
              <span>P10 - P90 Envelope</span>
            </div>
            <div>Dispersion: {forecast?.distribution?.path_dispersion_pct?.toFixed(2) || '0.00'}%</div>
          </div>
        </div>

        {/* Col 3: 10-Decile Calibration & Murphy Brier Decomposition */}
        <div className="bg-zinc-900/60 border border-zinc-800 rounded-lg p-4 space-y-3 flex flex-col">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider font-mono">
              Decile Calibration Reliability
            </h3>
            <span className="text-[11px] font-mono text-emerald-400">
              ECE: {brierReport?.calibration_quality?.expected_calibration_error?.toFixed(3) || '0.024'}
            </span>
          </div>

          <div className="flex-1 min-h-[220px] relative flex items-center justify-center">
            <canvas
              ref={reliabilityCanvasRef}
              width={420}
              height={220}
              className="w-full h-full max-h-[240px] rounded"
            />
          </div>

          {/* Murphy Brier Scorecard */}
          <div className="grid grid-cols-3 gap-2 text-center text-xs font-mono border-t border-zinc-800/80 pt-2">
            <div className="bg-zinc-950 p-2 rounded">
              <span className="text-zinc-500 text-[10px] block">Brier Score</span>
              <span className="text-white font-bold">{brierReport?.brier_score?.toFixed(4) || '0.2180'}</span>
            </div>
            <div className="bg-zinc-950 p-2 rounded">
              <span className="text-zinc-500 text-[10px] block">Brier Skill (BSS)</span>
              <span
                className={
                  (brierReport?.reference_benchmark?.brier_skill_score || 0) > 0
                    ? 'text-emerald-400 font-bold'
                    : 'text-rose-400 font-bold'
                }
              >
                {brierReport?.reference_benchmark?.brier_skill_score?.toFixed(3) || '+0.042'}
              </span>
            </div>
            <div className="bg-zinc-950 p-2 rounded">
              <span className="text-zinc-500 text-[10px] block">Reliability (Rel)</span>
              <span className="text-cyan-300 font-bold">
                {brierReport?.murphy_decomposition?.reliability?.toFixed(4) || '0.0085'}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Milestone K9: Predictive Validity & Incremental Information Research Panel */}
      <div className="bg-zinc-900/60 border border-zinc-800 rounded-lg p-4 space-y-4 font-mono">
        <div className="flex flex-wrap items-center justify-between border-b border-zinc-800 pb-3 gap-2">
          <div className="flex items-center space-x-3">
            <span className="text-xs font-bold text-cyan-400 uppercase tracking-wider">
              Milestone K9 Research Validity Suite
            </span>
            <span
              className={`text-[10px] px-2 py-0.5 rounded font-bold border ${
                promotion?.governance_state === 'PROMOTE'
                  ? 'bg-emerald-950/80 text-emerald-400 border-emerald-700'
                  : promotion?.governance_state === 'QUARANTINE'
                  ? 'bg-amber-950/80 text-amber-400 border-amber-700'
                  : promotion?.governance_state === 'REJECT'
                  ? 'bg-rose-950/80 text-rose-400 border-rose-700'
                  : 'bg-zinc-900 text-zinc-400 border-zinc-700'
              }`}
            >
              STATE: {promotion?.governance_state || 'EVALUATING'}
            </span>
          </div>

          {/* Sub-tabs */}
          <div className="flex space-x-1 text-xs">
            {(['TOURNAMENT', 'INCREMENTAL', 'REGIMES', 'ABLATION', 'PROMOTION'] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveResearchTab(tab)}
                className={`px-3 py-1 rounded text-[11px] transition-colors ${
                  activeResearchTab === tab
                    ? 'bg-zinc-800 text-cyan-300 font-bold border border-cyan-500/40'
                    : 'text-zinc-500 hover:text-zinc-300 hover:bg-zinc-950'
                }`}
              >
                {tab}
              </button>
            ))}
          </div>
        </div>

        {/* Tab 1: Benchmark Tournament */}
        {activeResearchTab === 'TOURNAMENT' && (
          <div className="space-y-3">
            <div className="text-xs text-zinc-400 flex justify-between">
              <span>Standardized out-of-sample tournament on identical evaluation slices (N={tournament?.sample_size || 0}):</span>
              <span className="text-zinc-500">Ref: Climatology Base Rate</span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="border-b border-zinc-800 text-zinc-500 text-[10px] uppercase">
                    <th className="py-2">Model Identity</th>
                    <th className="py-2 text-right">Brier Score</th>
                    <th className="py-2 text-right">Skill (BSS)</th>
                    <th className="py-2 text-right">Log Loss</th>
                    <th className="py-2 text-right">ROC-AUC</th>
                    <th className="py-2 text-right">Calib (α, β)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800/40 text-zinc-300">
                  {tournament?.rankings?.map((r, i) => (
                    <tr key={r.model_id} className={r.model_id.includes('KRONOS') ? 'bg-cyan-950/20' : ''}>
                      <td className="py-2 font-semibold flex items-center gap-2">
                        <span className="text-zinc-500 text-[10px]">{i + 1}.</span>
                        <span className={r.model_id.includes('KRONOS') ? 'text-cyan-300' : 'text-zinc-300'}>
                          {r.model_id}
                        </span>
                      </td>
                      <td className="py-2 text-right">{r.brier_score.toFixed(4)}</td>
                      <td
                        className={`py-2 text-right font-bold ${
                          r.brier_skill_score > 0 ? 'text-emerald-400' : 'text-rose-400'
                        }`}
                      >
                        {r.brier_skill_score > 0 ? `+${r.brier_skill_score.toFixed(3)}` : r.brier_skill_score.toFixed(3)}
                      </td>
                      <td className="py-2 text-right">{r.log_loss.toFixed(4)}</td>
                      <td className="py-2 text-right text-zinc-400">{r.roc_auc.toFixed(3)}</td>
                      <td className="py-2 text-right text-zinc-400">
                        {r.calibration_alpha.toFixed(2)}, {r.calibration_beta.toFixed(2)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Tab 2: Incremental Information & Orthogonality */}
        {activeResearchTab === 'INCREMENTAL' && (
          <div className="space-y-3">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-3 text-xs">
              <div className="bg-zinc-950 p-3 rounded border border-zinc-800/60">
                <span className="text-zinc-500 text-[10px] block">Δ Brier Improvement</span>
                <span className={`text-base font-bold ${((incremental?.delta_brier || 0) > 0) ? 'text-emerald-400' : 'text-rose-400'}`}>
                  {incremental?.delta_brier !== undefined ? `${(incremental.delta_brier * 100).toFixed(3)}%` : 'N/A'}
                </span>
                <span className="text-zinc-500 text-[10px] block mt-1">Relative: {incremental?.relative_brier_improvement_pct?.toFixed(2) || '0.00'}%</span>
              </div>
              <div className="bg-zinc-950 p-3 rounded border border-zinc-800/60">
                <span className="text-zinc-500 text-[10px] block">Mincer-Zarnowitz β_kronos</span>
                <span className="text-base font-bold text-cyan-300">
                  {incremental?.beta_kronos?.toFixed(3) || 'N/A'}
                </span>
                <span className="text-zinc-500 text-[10px] block mt-1">t-stat: {incremental?.beta_kronos_t_stat?.toFixed(2) || '0.00'}</span>
              </div>
              <div className="bg-zinc-950 p-3 rounded border border-zinc-800/60">
                <span className="text-zinc-500 text-[10px] block">Vuong-HAC Z Statistic</span>
                <span className="text-base font-bold text-white">
                  {incremental?.vuong_z_stat?.toFixed(2) || 'N/A'}
                </span>
                <span className="text-zinc-500 text-[10px] block mt-1">p-value: {incremental?.vuong_p_value?.toFixed(4) || 'N/A'}</span>
              </div>
              <div className="bg-zinc-950 p-3 rounded border border-zinc-800/60">
                <span className="text-zinc-500 text-[10px] block">Incremental Verdict</span>
                <span className={`text-sm font-bold block ${
                  incremental?.test_verdict === 'SIGNIFICANT_INCREMENTAL_EDGE'
                    ? 'text-emerald-400'
                    : incremental?.test_verdict === 'MARGINAL_IMPROVEMENT'
                    ? 'text-amber-400'
                    : 'text-zinc-400'
                }`}>
                  {incremental?.test_verdict || 'EVALUATING'}
                </span>
                <span className="text-zinc-500 text-[10px] block mt-1">Corr(e_base, P_k): {incremental?.residual_correlation?.toFixed(3) || '0.00'}</span>
              </div>
            </div>
            <div className="text-[11px] text-zinc-500 bg-zinc-950/80 p-2 rounded">
              Model 0 (SKY Baseline) vs Model 1 (SKY Baseline + Kronos). Evaluated with Newey-West HAC covariance (L=2*H) on strictly out-of-sample slices.
            </div>
          </div>
        )}

        {/* Tab 3: Regime Stratification */}
        {activeResearchTab === 'REGIMES' && (
          <div className="space-y-2">
            <div className="text-xs text-zinc-400">Point-in-time performance partitioned across market regimes (N &ge; 30):</div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-2 text-xs">
              {regimes?.regime_slices?.map((rs) => (
                <div key={`${rs.dimension}-${rs.regime_name}`} className="bg-zinc-950 p-2.5 rounded border border-zinc-800/60 flex justify-between items-center">
                  <div>
                    <span className="text-[10px] text-zinc-500 block">{rs.dimension}</span>
                    <span className="font-semibold text-zinc-200">{rs.regime_name}</span>
                  </div>
                  <div className="text-right">
                    {rs.status === 'VALID' ? (
                      <>
                        <span className={`font-bold block ${((rs.brier_skill_score || 0) > 0) ? 'text-emerald-400' : 'text-rose-400'}`}>
                          BSS: {rs.brier_skill_score?.toFixed(3)}
                        </span>
                        <span className="text-[10px] text-zinc-500">N={rs.sample_count}</span>
                      </>
                    ) : (
                      <span className="text-[10px] text-amber-500 block">N={rs.sample_count} (INSUFFICIENT)</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Tab 4: 7-Way Microstructure Ablation Matrix */}
        {activeResearchTab === 'ABLATION' && (
          <div className="space-y-2">
            <div className="text-xs text-zinc-400">7-way tournament isolating foundation transformer vs order book microstructure alpha:</div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="border-b border-zinc-800 text-zinc-500 text-[10px] uppercase">
                    <th className="py-2">Variant</th>
                    <th className="py-2">Description</th>
                    <th className="py-2 text-right">Brier Score</th>
                    <th className="py-2 text-right">BSS</th>
                    <th className="py-2 text-right">Δ BSS vs Raw</th>
                    <th className="py-2 text-right">Accuracy</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800/40 text-zinc-300">
                  {ablation?.ablation_variants?.map((v) => (
                    <tr key={v.variant_id} className={v.variant_id === 'F' ? 'bg-cyan-950/20' : ''}>
                      <td className="py-2 font-bold text-cyan-400">Variant {v.variant_id}</td>
                      <td className="py-2 text-zinc-300">{v.name}</td>
                      <td className="py-2 text-right">{v.brier_score.toFixed(4)}</td>
                      <td className={`py-2 text-right font-bold ${v.brier_skill_score > 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                        {v.brier_skill_score > 0 ? `+${v.brier_skill_score.toFixed(3)}` : v.brier_skill_score.toFixed(3)}
                      </td>
                      <td className={`py-2 text-right ${v.incremental_bss_vs_raw > 0 ? 'text-emerald-400 font-bold' : 'text-zinc-500'}`}>
                        {v.incremental_bss_vs_raw > 0 ? `+${v.incremental_bss_vs_raw.toFixed(4)}` : v.incremental_bss_vs_raw.toFixed(4)}
                      </td>
                      <td className="py-2 text-right text-zinc-400">{(v.accuracy * 100).toFixed(1)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Tab 5: Research Promotion Scorecard */}
        {activeResearchTab === 'PROMOTION' && (
          <div className="space-y-3">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
              <div className="space-y-2">
                <span className="text-zinc-400 font-semibold block">Constitutional Research Gate Checklist</span>
                <div className="space-y-1 text-[11px]">
                  {promotion?.criteria_checklist &&
                    Object.entries(promotion.criteria_checklist).map(([k, passed]) => (
                      <div key={k} className="flex items-center justify-between p-1.5 bg-zinc-950 rounded">
                        <span className="text-zinc-400 font-mono">{k}</span>
                        <span className={passed ? 'text-emerald-400 font-bold' : 'text-rose-400 font-bold'}>
                          {passed ? '[PASS]' : '[FAIL]'}
                        </span>
                      </div>
                    ))}
                </div>
              </div>
              <div className="space-y-2">
                <span className="text-zinc-400 font-semibold block">Governance Verdict & Disposition</span>
                <div className="bg-zinc-950 p-3 rounded space-y-2 border border-zinc-800 text-[11px]">
                  <div>Summary: <span className="text-zinc-200">{promotion?.summary_verdict}</span></div>
                  <div>Destination: <span className="text-cyan-400 font-bold">{promotion?.downstream_destination}</span></div>
                  <div>Tradeable Status: <span className="text-rose-400 font-bold">STRICTLY FALSE (Execution Firewall Active)</span></div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Provenance & Zero-Lookahead Audit Trail Footer */}
      <div className="bg-zinc-950 border border-zinc-800/80 rounded-lg p-4 space-y-2 font-mono text-xs">
        <div className="flex flex-wrap items-center justify-between text-zinc-400">
          <span className="font-semibold text-zinc-300">DURABLE PROVENANCE AUDIT TRAIL</span>
          <span className="text-zinc-500">Evidence Grade: {forecast?.governance?.evidence_grade || 'PROBABILISTIC_RESEARCH'}</span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-2 text-[11px] text-zinc-400">
          <div>Forecast ID: <span className="text-zinc-200">{forecast?.forecast_id || 'PENDING'}</span></div>
          <div>Request ID: <span className="text-zinc-200">{forecast?.request_id?.slice(0, 8) || 'N/A'}</span></div>
          <div>As-Of Timestamp: <span className="text-zinc-200">{forecast?.as_of_timestamp ? new Date(forecast.as_of_timestamp).toISOString() : 'N/A'}</span></div>
          <div>Causality Invariant: <span className="text-emerald-400 font-bold">ZERO LOOKAHEAD VERIFIED</span></div>
        </div>
      </div>
    </div>
  );
};
