import React from 'react';
import {
  ShieldCheck,
  User,
  Globe,
  Calendar,
  Layers,
  FileCheck,
  ExternalLink,
} from 'lucide-react';
import { WikiArticleDetail, ResearchSourceData } from '../../types';

interface WikiInfoboxProps {
  article: WikiArticleDetail;
  source?: ResearchSourceData | null;
}

export const WikiInfobox: React.FC<WikiInfoboxProps> = ({ article, source }) => {
  const domain = source?.source_domain || 'External Intelligence';
  const author = article.author_or_speaker || 'Quantitative Analyst';
  const pubDate = new Date(article.created_at).toLocaleDateString();
  const rigorScore = article.verification_score || 0;
  const claimsCount = article.key_claims?.length || article.claims_count || 0;

  return (
    <div className="w-full lg:w-72 bg-[#0c1322] border border-[#1e293b] rounded-lg overflow-hidden text-xs font-mono text-slate-300 shadow-xl flex flex-col mb-4 lg:mb-0">
      {/* Infobox Header */}
      <div className="bg-[#131d33] border-b border-[#1e293b] p-3 text-center">
        <h4 className="font-bold text-white text-sm tracking-wide leading-tight">
          {article.title}
        </h4>
        <span className="text-[10px] text-cyan-400 font-semibold uppercase tracking-wider block mt-1">
          {article.category}
        </span>
      </div>

      {/* Primary Verification Badge */}
      <div className="p-3 border-b border-[#1e293b] bg-slate-900/40 flex flex-col items-center gap-1.5 text-center">
        <span className="text-[10px] text-slate-400 uppercase font-semibold">Epistemic Status</span>
        <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded text-[11px] font-bold border bg-emerald-500/10 text-emerald-400 border-emerald-500/30">
          <ShieldCheck size={13} />
          {rigorScore >= 70 ? 'EVIDENCE VERIFIED' : 'HYPOTHESIS QUALIFIED'}
        </span>
      </div>

      {/* Structured Metadata Fields */}
      <div className="p-3 space-y-2 text-[11px]">
        <div className="flex justify-between items-start border-b border-[#1e293b]/60 pb-1.5">
          <span className="text-slate-500 flex items-center gap-1">
            <User size={12} className="text-slate-400" /> Attributed:
          </span>
          <span className="font-semibold text-slate-200 text-right truncate max-w-[130px]">
            {author}
          </span>
        </div>

        <div className="flex justify-between items-start border-b border-[#1e293b]/60 pb-1.5">
          <span className="text-slate-500 flex items-center gap-1">
            <Globe size={12} className="text-slate-400" /> Domain:
          </span>
          <span className="font-semibold text-slate-200 text-right truncate max-w-[130px]">
            {domain}
          </span>
        </div>

        <div className="flex justify-between items-start border-b border-[#1e293b]/60 pb-1.5">
          <span className="text-slate-500 flex items-center gap-1">
            <Calendar size={12} className="text-slate-400" /> Recorded:
          </span>
          <span className="font-semibold text-slate-200 text-right">
            {pubDate}
          </span>
        </div>

        <div className="flex justify-between items-start border-b border-[#1e293b]/60 pb-1.5">
          <span className="text-slate-500 flex items-center gap-1">
            <FileCheck size={12} className="text-slate-400" /> Evidence Rigor:
          </span>
          <span className={`font-bold ${rigorScore >= 70 ? 'text-emerald-400' : 'text-amber-400'}`}>
            {rigorScore.toFixed(0)}%
          </span>
        </div>

        <div className="flex justify-between items-start border-b border-[#1e293b]/60 pb-1.5">
          <span className="text-slate-500 flex items-center gap-1">
            <Layers size={12} className="text-slate-400" /> Claims Extracted:
          </span>
          <span className="font-bold text-cyan-300">
            {claimsCount}
          </span>
        </div>

        {source?.source_id && (
          <div className="flex flex-col gap-0.5 border-b border-[#1e293b]/60 pb-1.5">
            <span className="text-slate-500 text-[10px]">Source Ledger ID:</span>
            <span className="font-mono text-[9px] text-slate-400 break-all select-all">
              {source.source_id}
            </span>
          </div>
        )}
      </div>

      {/* Specialized Category Infobox Schema */}
      {(() => {
        const catUpper = (article.category || '').toUpperCase();
        const tagsUpper = (article.tags || []).map((t) => t.toUpperCase()).join(' ');

        if (catUpper.includes('REGIME') || catUpper.includes('MACRO') || tagsUpper.includes('REGIME') || catUpper.includes('GEOPOLITICS')) {
          return (
            <div className="p-3 border-t border-[#1e293b]/60 bg-indigo-950/20 space-y-1.5 text-[11px]">
              <span className="text-[10px] text-indigo-400 font-bold uppercase tracking-wider block mb-1">
                🏛️ Macro Regime Schema
              </span>
              <div className="flex justify-between">
                <span className="text-slate-500">Regime Class:</span>
                <span className="text-indigo-300 font-semibold">Expansionary / Hegemonic</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Volatility Cluster:</span>
                <span className="text-slate-300">Clustered Vol (GARCH)</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Liquidity State:</span>
                <span className="text-emerald-400 font-semibold">Accommodative</span>
              </div>
            </div>
          );
        }

        if (catUpper.includes('STRUCTURE') || catUpper.includes('FACTOR') || tagsUpper.includes('FACTOR') || tagsUpper.includes('ALPHA')) {
          return (
            <div className="p-3 border-t border-[#1e293b]/60 bg-cyan-950/20 space-y-1.5 text-[11px]">
              <span className="text-[10px] text-cyan-400 font-bold uppercase tracking-wider block mb-1">
                📐 Alpha Factor Schema
              </span>
              <div className="flex justify-between">
                <span className="text-slate-500">Factor Family:</span>
                <span className="text-cyan-300 font-semibold">Microstructure / Orderflow</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Decay Half-Life:</span>
                <span className="text-slate-300">~15m - 4h</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Capacity Tier:</span>
                <span className="text-emerald-400 font-semibold">Institutional ($50M+)</span>
              </div>
            </div>
          );
        }

        if (catUpper.includes('CRYPTO') || catUpper.includes('SETTLEMENT') || tagsUpper.includes('PROTOCOL')) {
          return (
            <div className="p-3 border-t border-[#1e293b]/60 bg-purple-950/20 space-y-1.5 text-[11px]">
              <span className="text-[10px] text-purple-400 font-bold uppercase tracking-wider block mb-1">
                ⚡ Protocol & Settlement Schema
              </span>
              <div className="flex justify-between">
                <span className="text-slate-500">Settlement Layer:</span>
                <span className="text-purple-300 font-semibold">L1 / L2 Rollup</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Finality Class:</span>
                <span className="text-slate-300">Deterministic</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Custody Audit:</span>
                <span className="text-emerald-400 font-semibold">Zero-Rehypothecation</span>
              </div>
            </div>
          );
        }

        return (
          <div className="p-3 border-t border-[#1e293b]/60 bg-slate-900/40 space-y-1.5 text-[11px]">
            <span className="text-[10px] text-slate-400 font-bold uppercase tracking-wider block mb-1">
              📊 Quantitative Profile
            </span>
            <div className="flex justify-between">
              <span className="text-slate-500">Audit Framework:</span>
              <span className="text-slate-300">Epistemic Taxonomy (L2)</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Falsifiability:</span>
              <span className="text-emerald-400 font-semibold">CPCV Testable</span>
            </div>
          </div>
        );
      })()}

      {/* External Original Link */}
      {article.source_url && (
        <div className="p-2.5 bg-[#0a0f1d] border-t border-[#1e293b] text-center">
          <a
            href={article.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 text-[11px] text-cyan-400 hover:text-cyan-300 transition hover:underline"
          >
            <ExternalLink size={12} /> View Primary Source
          </a>
        </div>
      )}
    </div>
  );
};
