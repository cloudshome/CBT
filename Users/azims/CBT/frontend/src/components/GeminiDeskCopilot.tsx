import React, { useState } from 'react';
import { Bot, Sparkles, Send, RefreshCw, AlertTriangle } from 'lucide-react';
import { DeskBriefResponse } from '../types';
import { LoadingSkeleton } from './LoadingSkeleton';

interface GeminiDeskCopilotProps {
  symbol: string;
  timeframe: string;
  brief: DeskBriefResponse | null;
  loadingBrief: boolean;
  onRefreshBrief: () => void;
  onAskDesk: (query: string) => Promise<string>;
}

export const GeminiDeskCopilot: React.FC<GeminiDeskCopilotProps> = ({
  symbol,
  timeframe,
  brief,
  loadingBrief,
  onRefreshBrief,
  onAskDesk,
}) => {
  const [query, setQuery] = useState('');
  const [asking, setAsking] = useState(false);
  const [chatLog, setChatLog] = useState<{ query: string; answer: string; time: string }[]>([]);

  const handleAsk = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim() || asking) return;

    const userQ = query.trim();
    setQuery('');
    setAsking(true);

    try {
      const answer = await onAskDesk(userQ);
      setChatLog((prev) => [
        {
          query: userQ,
          answer,
          time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
        },
        ...prev,
      ]);
    } finally {
      setAsking(false);
    }
  };

  const biasColor =
    brief?.bias === 'BULLISH'
      ? 'bg-terminal-green/20 border-terminal-green text-terminal-green'
      : brief?.bias === 'BEARISH'
      ? 'bg-terminal-red/20 border-terminal-red text-terminal-red'
      : 'bg-terminal-amber/20 border-terminal-amber text-terminal-amber';

  return (
    <div className="bg-background-card border border-border rounded-lg p-4 shadow-lg flex flex-col h-full space-y-4">
      {/* Copilot Header */}
      <div className="flex items-center justify-between pb-3 border-b border-border">
        <div className="flex items-center gap-2">
          <div className="p-1 rounded bg-terminal-cyan/10 border border-terminal-cyan/30 text-terminal-cyan">
            <Bot className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-xs font-mono font-bold text-white flex items-center gap-1.5">
              GEMINI DESK INTELLIGENCE
            </h3>
            <p className="text-[10px] font-mono text-slate-400">
              Grounded Institutional Copilot
            </p>
          </div>
        </div>

        <button
          onClick={onRefreshBrief}
          disabled={loadingBrief}
          title="Regenerate AI Brief"
          className="flex items-center gap-1 text-[11px] font-mono px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 disabled:opacity-50 transition-all"
        >
          <RefreshCw className={`w-3 h-3 ${loadingBrief ? 'animate-spin text-terminal-cyan' : ''}`} />
          <span>Refresh Brief</span>
        </button>
      </div>

      {/* AI Market Brief Section */}
      <div className="space-y-3">
        {loadingBrief ? (
          <div className="space-y-2">
            <LoadingSkeleton className="h-6 w-1/3" />
            <LoadingSkeleton className="h-16 w-full" />
            <LoadingSkeleton className="h-12 w-full" />
          </div>
        ) : brief ? (
          <div className="space-y-3">
            {/* Bias Banner */}
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-mono text-slate-400">DESK DIRECTIONAL BIAS:</span>
              <span className={`px-2.5 py-0.5 rounded text-xs font-mono font-bold border ${biasColor}`}>
                {brief.bias}
              </span>
            </div>

            {/* Executive Summary */}
            <div className="bg-background p-3 rounded border border-border text-xs leading-relaxed text-slate-200">
              <div className="flex items-center gap-1.5 text-[10px] font-mono text-terminal-cyan mb-1 font-bold">
                <Sparkles className="w-3 h-3" /> EXECUTIVE SUMMARY
              </div>
              <p>{brief.executiveSummary}</p>
            </div>

            {/* Key Levels Grid */}
            <div className="grid grid-cols-3 gap-2 text-xs font-mono">
              <div className="bg-background p-2 rounded border border-border">
                <span className="text-[9px] text-terminal-green font-bold block">SUPPORT</span>
                <span className="text-white text-[11px]">
                  {brief.keyLevels.support?.length ? brief.keyLevels.support.join(', ') : 'N/A'}
                </span>
              </div>
              <div className="bg-background p-2 rounded border border-border">
                <span className="text-[9px] text-terminal-red font-bold block">RESISTANCE</span>
                <span className="text-white text-[11px]">
                  {brief.keyLevels.resistance?.length ? brief.keyLevels.resistance.join(', ') : 'N/A'}
                </span>
              </div>
              <div className="bg-background p-2 rounded border border-border">
                <span className="text-[9px] text-terminal-amber font-bold block">INVALIDATION</span>
                <span className="text-white text-[11px]">
                  {brief.keyLevels.invalidation ? `$${brief.keyLevels.invalidation}` : 'N/A'}
                </span>
              </div>
            </div>

            {/* Risk Assessment */}
            <div className="bg-[#191316] p-2.5 rounded border border-terminal-red/30 flex items-start gap-2 text-xs text-rose-200">
              <AlertTriangle className="w-4 h-4 text-terminal-red shrink-0 mt-0.5" />
              <div>
                <span className="text-[10px] font-mono font-bold text-terminal-red block">RISK ASSESSMENT</span>
                <p className="text-[11px] leading-snug">{brief.riskAssessment}</p>
              </div>
            </div>
          </div>
        ) : (
          <div className="bg-background p-4 rounded border border-border text-center font-mono text-xs text-slate-400">
            Click "Refresh Brief" to generate Gemini market intelligence for {symbol}.
          </div>
        )}
      </div>

      {/* Interactive Desk Q&A Widget */}
      <div className="border-t border-border pt-3 flex flex-col flex-1">
        <div className="text-[11px] font-mono text-slate-400 mb-2 flex items-center justify-between">
          <span>ASK DESK COPILOT</span>
          <span className="text-[9px] text-terminal-cyan">GROUNDED IN LIVE TELEMETRY</span>
        </div>

        {/* Q&A Conversation Feed */}
        <div className="flex-1 overflow-y-auto max-h-[160px] space-y-2 pr-1 mb-3">
          {chatLog.length === 0 ? (
            <div className="text-[11px] font-mono text-slate-500 italic p-2 text-center">
              Ask about market structure, RSI momentum, or trade setups...
            </div>
          ) : (
            chatLog.map((c, i) => (
              <div key={i} className="bg-background p-2.5 rounded border border-border space-y-1 text-xs">
                <div className="flex items-center justify-between text-[10px] font-mono text-slate-400">
                  <span className="font-bold text-terminal-cyan">&gt; {c.query}</span>
                  <span className="text-slate-500">{c.time}</span>
                </div>
                <div className="text-slate-200 text-[11px] leading-relaxed pt-0.5 border-t border-border/40">
                  {c.answer}
                </div>
              </div>
            ))
          )}
        </div>

        {/* Query Input Box */}
        <form onSubmit={handleAsk} className="flex gap-2">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={`Ask desk about ${symbol} (${timeframe})...`}
            className="flex-1 bg-background border border-border rounded px-3 py-1.5 text-xs text-white placeholder-slate-500 font-mono focus:border-terminal-cyan focus:outline-none"
            disabled={asking}
          />
          <button
            type="submit"
            disabled={asking || !query.trim()}
            className="px-3 py-1.5 rounded bg-terminal-cyan/20 border border-terminal-cyan/40 text-terminal-cyan hover:bg-terminal-cyan/30 text-xs font-mono font-bold flex items-center gap-1 disabled:opacity-50 transition-all"
          >
            <Send className={`w-3.5 h-3.5 ${asking ? 'animate-pulse' : ''}`} />
            <span>{asking ? 'THINKING...' : 'ASK'}</span>
          </button>
        </form>
      </div>
    </div>
  );
};
