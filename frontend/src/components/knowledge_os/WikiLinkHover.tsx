import React, { useState } from 'react';
import { BookOpen, ShieldCheck } from 'lucide-react';

interface WikiLinkProps {
  term: string;
  articleId?: string;
  summary?: string;
  onNavigate?: (articleId: string) => void;
}

export const WikiLink: React.FC<WikiLinkProps> = ({
  term,
  articleId,
  summary,
  onNavigate,
}) => {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <span
      className="relative inline-block"
      onMouseEnter={() => setIsOpen(true)}
      onMouseLeave={() => setIsOpen(false)}
    >
      <button
        onClick={() => articleId && onNavigate?.(articleId)}
        className="text-cyan-400 hover:text-cyan-300 font-semibold underline decoration-cyan-500/40 hover:decoration-cyan-300 decoration-1 underline-offset-2 transition inline-flex items-center gap-0.5"
      >
        {term}
      </button>

      {/* Wikipedia-Grade Hover Preview Card */}
      {isOpen && (
        <div className="absolute left-0 bottom-full mb-2 w-64 bg-[#0d1527] border border-cyan-500/30 rounded-lg shadow-2xl p-3 z-50 text-xs font-mono text-slate-200 pointer-events-none animate-in fade-in zoom-in-95 duration-150">
          <div className="flex items-center gap-1.5 text-cyan-400 font-bold mb-1 border-b border-[#1e293b] pb-1">
            <BookOpen size={13} />
            <span className="truncate">{term}</span>
          </div>
          <p className="text-[11px] text-slate-300 line-clamp-3 leading-relaxed mb-2">
            {summary || `Cross-verified quantitative concept in SKY Research Wikipedia.`}
          </p>
          <div className="flex items-center justify-between text-[10px] text-slate-400 pt-1 border-t border-[#1e293b]/60">
            <span className="flex items-center gap-1 text-emerald-400">
              <ShieldCheck size={11} /> Evidence Verified
            </span>
            <span className="text-cyan-400 font-semibold">Click to open &rarr;</span>
          </div>
        </div>
      )}
    </span>
  );
};
