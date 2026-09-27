import React, { useEffect, useRef } from 'react';
import {
  createChart,
  HistogramSeries,
  LineSeries,
  IChartApi,
  ISeriesApi,
  HistogramData,
  LineData,
  ColorType,
  Time,
} from 'lightweight-charts';
import { OHLCVCandle, CVDSeriesData } from '../types';
import { Activity, Zap } from 'lucide-react';

interface CVDSubChartProps {
  candles: OHLCVCandle[];
  cvdData?: CVDSeriesData | null;
  height?: number;
}

export const CVDSubChart: React.FC<CVDSubChartProps> = ({
  candles,
  cvdData,
  height = 140,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const cvdLineRef = useRef<ISeriesApi<'Line'> | null>(null);
  const deltaHistRef = useRef<ISeriesApi<'Histogram'> | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const container = containerRef.current;
    container.innerHTML = '';

    const chart = createChart(container, {
      width: container.clientWidth,
      height,
      layout: {
        background: { type: ColorType.Solid, color: '#080b11' },
        textColor: '#64748b',
        fontSize: 10,
        fontFamily: "'JetBrains Mono', monospace",
      },
      grid: {
        vertLines: { color: 'rgba(255, 255, 255, 0.02)' },
        horzLines: { color: 'rgba(255, 255, 255, 0.02)' },
      },
      timeScale: {
        visible: false, // Synchronized with main chart
        borderColor: 'rgba(51, 65, 85, 0.3)',
      },
      rightPriceScale: {
        borderColor: 'rgba(51, 65, 85, 0.3)',
        scaleMargins: {
          top: 0.15,
          bottom: 0.15,
        },
      },
    });

    // Delta Histogram
    const deltaHist = chart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' },
    });

    // CVD Cumulative Line
    const cvdLine = chart.addSeries(LineSeries, {
      color: '#38bdf8',
      lineWidth: 2,
      priceLineVisible: false,
    });

    chartRef.current = chart;
    cvdLineRef.current = cvdLine;
    deltaHistRef.current = deltaHist;

    const handleResize = () => {
      if (containerRef.current && chartRef.current) {
        chartRef.current.resize(containerRef.current.clientWidth, height);
      }
    };

    window.addEventListener('resize', handleResize);
    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
      chartRef.current = null;
    };
  }, [height]);

  useEffect(() => {
    if (!candles || candles.length === 0 || !cvdLineRef.current || !deltaHistRef.current) return;

    let cumCVD = 0;
    const lineData: LineData[] = [];
    const histData: HistogramData[] = [];

    candles.forEach((c) => {
      const isGreen = c[4] >= c[1];
      const body = Math.abs(c[4] - c[1]);
      const range = Math.max(c[2] - c[3], 1e-4);
      const deltaRatio = isGreen ? body / range : -(body / range);
      const delta = c[5] * deltaRatio;
      cumCVD += delta;

      const t = Math.floor(c[0] / 1000) as Time;
      lineData.push({ time: t, value: cumCVD });
      histData.push({
        time: t,
        value: delta,
        color: delta >= 0 ? 'rgba(0, 240, 168, 0.5)' : 'rgba(255, 59, 105, 0.5)',
      });
    });

    cvdLineRef.current.setData(lineData);
    deltaHistRef.current.setData(histData);
    chartRef.current?.timeScale().scrollToRealTime();
  }, [candles]);

  return (
    <div className="relative flex flex-col bg-[#080b11] border border-[#1e293b] border-t-0 rounded-b-lg overflow-hidden select-none">
      {/* Sub-chart Header */}
      <div className="flex items-center justify-between px-3 py-1 bg-[#0d121d] border-b border-[#1e293b] text-[11px] font-mono">
        <div className="flex items-center gap-2">
          <Activity size={12} className="text-sky-400" />
          <span className="font-bold text-slate-300">CVD (Orderflow Delta & Absorption)</span>
          {cvdData && (
            <span className="text-slate-500">
              Delta: <strong className={(Number(cvdData.current_cvd) || 0) >= 0 ? 'text-[#00f0a8]' : 'text-[#ff3b69]'}>
                {(Number(cvdData.current_cvd) || 0) > 0 ? '+' : ''}{Number(cvdData.current_cvd || 0).toLocaleString()}
              </strong>
            </span>
          )}
        </div>

        {cvdData?.absorption_detected && (
          <div className="flex items-center gap-1.5 px-2 py-0.5 bg-amber-500/10 border border-amber-500/30 text-amber-300 rounded text-[10px] animate-pulse">
            <Zap size={11} className="text-amber-400" />
            <span>{String(cvdData.absorption_type || 'ABSORPTION').replace(/_/g, ' ')} ({Math.round((Number(cvdData.absorption_score) || 0) * 100)}%)</span>
          </div>
        )}
      </div>

      {/* Render Target */}
      <div ref={containerRef} className="w-full" style={{ height }} />
    </div>
  );
};
