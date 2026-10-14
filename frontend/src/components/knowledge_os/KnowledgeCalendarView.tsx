import React, { useState, useEffect, useCallback } from 'react';
import {
  Calendar,
  Clock,
  FileText,
  ShieldCheck,
  HelpCircle,
  RefreshCw,
  ChevronRight,
  BookOpen,
  Layers,
} from 'lucide-react';
import { api } from '../../services/api';
import { WikiCalendarDay, WikiCalendarResponse } from '../../types';

interface KnowledgeCalendarViewProps {
  onSelectDate: (date: string) => void;
  onSelectArticle?: (articleId: string) => void;
}

export const KnowledgeCalendarView: React.FC<KnowledgeCalendarViewProps> = ({
  onSelectDate,
  onSelectArticle,
}) => {
  const [calendarData, setCalendarData] = useState<WikiCalendarResponse | null>(null);
  const [selectedDay, setSelectedDay] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  const loadCalendar = useCallback(async (date?: string) => {
    try {
      setIsLoading(true);
      const res = await api.getWikiCalendar(date);
      setCalendarData(res);
      if (date) {
        setSelectedDay(date);
      } else if (res.daily_activity && res.daily_activity.length > 0 && !selectedDay) {
        // Default to most recent active day
        setSelectedDay(res.daily_activity[0].date);
        // Load details for top day
        const dayRes = await api.getWikiCalendar(res.daily_activity[0].date);
        setCalendarData(dayRes);
      }
    } catch (err) {
      console.error('Failed to load knowledge calendar:', err);
    } finally {
      setIsLoading(false);
    }
  }, [selectedDay]);

  useEffect(() => {
    loadCalendar();
  }, [loadCalendar]);

  const handleDayClick = async (date: string) => {
    setSelectedDay(date);
    try {
      const res = await api.getWikiCalendar(date);
      setCalendarData(res);
    } catch (err) {
      console.error('Failed to load day details:', err);
    }
  };

  // Aggregate totals
  const totalDays = calendarData?.daily_activity?.length || 0;
  const totalSources = calendarData?.daily_activity?.reduce((acc, d) => acc + d.sources_count, 0) || 0;
  const totalArticles = calendarData?.daily_activity?.reduce((acc, d) => acc + d.articles_count, 0) || 0;
  const totalClaims = calendarData?.daily_activity?.reduce((acc, d) => acc + d.claims_count, 0) || 0;
  const totalFacts = calendarData?.daily_activity?.reduce((acc, d) => acc + d.facts_count, 0) || 0;
  const totalHypo = calendarData?.daily_activity?.reduce((acc, d) => acc + d.hypotheses_count, 0) || 0;

  const activeDayItems = calendarData?.target_day_data?.timeline || [];

  return (
    <div className="flex flex-col h-full bg-slate-950 text-slate-100 p-6 space-y-6 overflow-y-auto">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-800 pb-5">
        <div>
          <div className="flex items-center gap-2">
            <Calendar className="w-6 h-6 text-cyan-400" />
            <h2 className="text-xl font-bold tracking-tight text-white">
              Institutional Knowledge Harvest Calendar
            </h2>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Day-by-day activity ledger tracking autonomous agent crawling, research ingest, and epistemic claims discovery.
          </p>
        </div>

        <button
          onClick={() => loadCalendar(selectedDay || undefined)}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-slate-800 hover:bg-slate-700 text-xs text-slate-200 transition self-start md:self-auto"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Metric Cards Banner */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800/80">
          <div className="flex items-center justify-between text-slate-400 text-xs mb-1">
            <span>Active Research Days</span>
            <Clock className="w-4 h-4 text-cyan-400" />
          </div>
          <div className="text-2xl font-bold text-white font-mono">{totalDays}</div>
          <div className="text-[10px] text-slate-500 mt-1">Recorded in Knowledge OS</div>
        </div>

        <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800/80">
          <div className="flex items-center justify-between text-slate-400 text-xs mb-1">
            <span>Ingested Documents</span>
            <FileText className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="text-2xl font-bold text-emerald-400 font-mono">{totalSources}</div>
          <div className="text-[10px] text-slate-500 mt-1">{totalClaims} Claims ({totalArticles} Articles)</div>
        </div>

        <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800/80">
          <div className="flex items-center justify-between text-slate-400 text-xs mb-1">
            <span>Empirical Facts</span>
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="text-2xl font-bold text-emerald-400 font-mono">{totalFacts}</div>
          <div className="text-[10px] text-slate-500 mt-1">Verified with data proof</div>
        </div>

        <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800/80">
          <div className="flex items-center justify-between text-slate-400 text-xs mb-1">
            <span>Research Hypotheses</span>
            <HelpCircle className="w-4 h-4 text-amber-400" />
          </div>
          <div className="text-2xl font-bold text-amber-400 font-mono">{totalHypo}</div>
          <div className="text-[10px] text-slate-500 mt-1">Pending backtest validation</div>
        </div>
      </div>

      {/* Day Cards Grid */}
      <div>
        <h3 className="text-sm font-semibold text-slate-200 mb-3 flex items-center gap-2">
          <Layers className="w-4 h-4 text-cyan-400" />
          <span>Timeline Heatmap (Select a Date)</span>
        </h3>

        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3">
          {calendarData?.daily_activity?.map((day: WikiCalendarDay) => {
            const isSelected = selectedDay === day.date;

            return (
              <button
                key={day.date}
                onClick={() => handleDayClick(day.date)}
                className={`p-3.5 rounded-xl border text-left transition-all relative overflow-hidden group ${
                  isSelected
                    ? 'bg-cyan-950/40 border-cyan-500 shadow-lg shadow-cyan-950/50'
                    : 'bg-slate-900/50 border-slate-800/80 hover:border-slate-700 hover:bg-slate-900'
                }`}
              >
                {isSelected && (
                  <div className="absolute top-0 right-0 w-2 h-2 bg-cyan-400 rounded-bl" />
                )}
                <div className="flex items-center justify-between">
                  <span className={`text-xs font-mono font-bold ${isSelected ? 'text-cyan-300' : 'text-slate-200'}`}>
                    {day.date}
                  </span>
                </div>

                <div className="mt-2.5 space-y-1">
                  <div className="flex items-center justify-between text-[11px]">
                    <span className="text-slate-400">Sources:</span>
                    <span className="font-mono font-semibold text-slate-200">
                      {day.sources_count}
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-[11px]">
                    <span className="text-slate-400">Claims:</span>
                    <span className="font-mono text-cyan-400">
                      {day.claims_count}
                    </span>
                  </div>
                </div>

                <div className="mt-2 pt-2 border-t border-slate-800/60 flex items-center gap-1.5 text-[9px] text-slate-400">
                  <span className="text-emerald-400 font-mono">{day.facts_count}F</span>
                  <span>•</span>
                  <span className="text-amber-400 font-mono">{day.hypotheses_count}H</span>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Selected Day Deep Dive Panel */}
      {selectedDay && (
        <div className="mt-6 border border-slate-800 rounded-xl bg-slate-900/50 p-5 space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800 pb-3">
            <div className="flex items-center gap-2">
              <Calendar className="w-5 h-5 text-cyan-400" />
              <h4 className="text-sm font-bold text-white">
                Intelligence Harvest for <span className="font-mono text-cyan-300">{selectedDay}</span>
              </h4>
              <span className="px-2 py-0.5 rounded bg-slate-800 text-[10px] text-slate-400 font-mono">
                {activeDayItems.length} items
              </span>
            </div>

            <button
              onClick={() => onSelectDate(selectedDay)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-cyan-950 hover:bg-cyan-900 border border-cyan-800/60 text-cyan-200 text-xs font-medium transition"
            >
              <span>Open in Full Ingestion Table</span>
              <ChevronRight className="w-3.5 h-3.5" />
            </button>
          </div>

          {activeDayItems.length === 0 ? (
            <div className="py-8 text-center text-slate-500 text-xs">
              No individual documents recorded for this date.
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {activeDayItems.map((item) => (
                <div
                  key={item.source_id}
                  className="p-3.5 rounded-lg bg-slate-950/60 border border-slate-800/80 hover:border-slate-700 transition space-y-2"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <FileText className="w-4 h-4 text-rose-400 shrink-0" />
                      <p className="font-semibold text-xs text-slate-200 truncate" title={item.title}>
                        {item.title}
                      </p>
                    </div>
                    <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 shrink-0">
                      {item.source_type}
                    </span>
                  </div>

                  <div className="flex items-center justify-between text-[11px] text-slate-400 pt-1">
                    <span className="truncate max-w-[200px]">
                      {item.author_or_creator || 'Institutional Research'}
                    </span>
                    <div className="flex items-center gap-2 font-mono text-[10px]">
                      <span className="text-emerald-400">{item.facts_count} Facts</span>
                      <span className="text-amber-400">{item.hypotheses_count} Hypo</span>
                    </div>
                  </div>

                  {item.wiki_article_id && onSelectArticle && (
                    <div className="pt-2 border-t border-slate-900 flex justify-end">
                      <button
                        onClick={() => onSelectArticle(item.wiki_article_id!)}
                        className="inline-flex items-center gap-1 text-[11px] text-cyan-400 hover:text-cyan-300 font-medium"
                      >
                        <BookOpen className="w-3 h-3" />
                        <span>Read Formatted Wikipedia Article</span>
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
