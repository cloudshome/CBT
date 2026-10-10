import React from 'react';
import {
  ShieldCheck,
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
  const pubDate = new Date(article.created_at).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
  const rigorScore = article.verification_score || 0;
  const claimsCount = article.key_claims?.length || article.claims_count || 0;

  return (
    <aside className="w-full lg:w-80 border border-[#a2a9b1] dark:border-[#384252] bg-[#f8f9fa] dark:bg-[#18202e] text-[#202122] dark:text-[#eaecf0] shadow-sm rounded-none text-xs font-sans leading-normal mb-4 lg:mb-0 shrink-0">
      {/* Wikipedia Infobox Title Banner */}
      <div className="bg-[#eaecf0] dark:bg-[#202b3d] border-b border-[#a2a9b1] dark:border-[#384252] px-3 py-2 text-center">
        <h4 className="font-serif font-bold text-sm tracking-normal text-[#101418] dark:text-white">
          {article.title}
        </h4>
        <div className="text-[10px] text-[#54595d] dark:text-[#9aa0a6] uppercase tracking-wider font-mono mt-0.5">
          {article.category}
        </div>
      </div>

      {/* Epistemic Status Ribbon */}
      <div className="p-2.5 border-b border-[#c8ccd1] dark:border-[#2e3846] bg-[#f1f3f5] dark:bg-[#1b2434] text-center">
        <div className="text-[10px] uppercase font-semibold text-[#54595d] dark:text-[#9aa0a6] mb-1">
          Epistemic Verification
        </div>
        <span
          className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded text-[11px] font-bold border ${
            rigorScore >= 70
              ? 'bg-[#e6f4ea] text-[#137333] border-[#ceead6] dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-700/50'
              : 'bg-[#fef7e0] text-[#b06000] border-[#feefc3] dark:bg-amber-950/40 dark:text-amber-300 dark:border-amber-700/50'
          }`}
        >
          <ShieldCheck size={13} />
          {rigorScore >= 70 ? 'EVIDENCE VERIFIED' : 'HYPOTHESIS QUALIFIED'}
        </span>
      </div>

      {/* Wikipedia Key-Value Metadata Table */}
      <table className="w-full border-collapse text-[11px]">
        <tbody>
          <tr className="border-b border-[#eaecf0] dark:border-[#253041]">
            <th className="w-1/3 py-2 px-3 text-left font-semibold text-[#54595d] dark:text-[#9aa0a6] bg-[#f8f9fa] dark:bg-[#151c28] border-r border-[#eaecf0] dark:border-[#253041] align-top">
              Attributed to
            </th>
            <td className="py-2 px-3 text-[#202122] dark:text-[#e2e8f0] font-medium align-top">
              {author}
            </td>
          </tr>

          <tr className="border-b border-[#eaecf0] dark:border-[#253041]">
            <th className="py-2 px-3 text-left font-semibold text-[#54595d] dark:text-[#9aa0a6] bg-[#f8f9fa] dark:bg-[#151c28] border-r border-[#eaecf0] dark:border-[#253041] align-top">
              Domain
            </th>
            <td className="py-2 px-3 text-[#202122] dark:text-[#e2e8f0] font-mono text-[10px] align-top">
              {domain}
            </td>
          </tr>

          <tr className="border-b border-[#eaecf0] dark:border-[#253041]">
            <th className="py-2 px-3 text-left font-semibold text-[#54595d] dark:text-[#9aa0a6] bg-[#f8f9fa] dark:bg-[#151c28] border-r border-[#eaecf0] dark:border-[#253041] align-top">
              Recorded
            </th>
            <td className="py-2 px-3 text-[#202122] dark:text-[#e2e8f0] align-top">
              {pubDate}
            </td>
          </tr>

          <tr className="border-b border-[#eaecf0] dark:border-[#253041]">
            <th className="py-2 px-3 text-left font-semibold text-[#54595d] dark:text-[#9aa0a6] bg-[#f8f9fa] dark:bg-[#151c28] border-r border-[#eaecf0] dark:border-[#253041] align-top">
              Evidence Rigor
            </th>
            <td className="py-2 px-3 font-bold align-top">
              <span className={rigorScore >= 70 ? 'text-[#188038] dark:text-emerald-400' : 'text-[#b06000] dark:text-amber-400'}>
                {rigorScore.toFixed(0)}%
              </span>
            </td>
          </tr>

          <tr className="border-b border-[#eaecf0] dark:border-[#253041]">
            <th className="py-2 px-3 text-left font-semibold text-[#54595d] dark:text-[#9aa0a6] bg-[#f8f9fa] dark:bg-[#151c28] border-r border-[#eaecf0] dark:border-[#253041] align-top">
              Claims Extracted
            </th>
            <td className="py-2 px-3 text-[#3366cc] dark:text-cyan-400 font-bold align-top">
              {claimsCount}
            </td>
          </tr>

          {source?.source_id && (
            <tr className="border-b border-[#eaecf0] dark:border-[#253041]">
              <th className="py-2 px-3 text-left font-semibold text-[#54595d] dark:text-[#9aa0a6] bg-[#f8f9fa] dark:bg-[#151c28] border-r border-[#eaecf0] dark:border-[#253041] align-top">
                Ledger ID
              </th>
              <td className="py-2 px-3 font-mono text-[9px] text-[#54595d] dark:text-slate-400 select-all break-all align-top">
                {source.source_id}
              </td>
            </tr>
          )}
        </tbody>
      </table>

      {/* Specialized Category Schema Section */}
      {(() => {
        const catUpper = (article.category || '').toUpperCase();
        const tagsUpper = (article.tags || []).map((t) => t.toUpperCase()).join(' ');

        if (catUpper.includes('REGIME') || catUpper.includes('MACRO') || tagsUpper.includes('REGIME') || catUpper.includes('GEOPOLITICS')) {
          return (
            <div className="border-t border-[#a2a9b1] dark:border-[#384252] bg-[#f1f3f5] dark:bg-[#172233] p-2.5 space-y-1 text-[11px]">
              <div className="font-semibold text-[#202122] dark:text-[#c4d1e2] border-b border-[#c8ccd1] dark:border-[#2e3b4e] pb-1 mb-1.5 flex items-center gap-1">
                <span>🏛️</span>
                <span>Macro Regime Specification</span>
              </div>
              <div className="flex justify-between py-0.5">
                <span className="text-[#54595d] dark:text-slate-400 font-medium">Regime Class:</span>
                <span className="font-semibold text-[#0b0080] dark:text-indigo-300">Expansionary / Hegemonic</span>
              </div>
              <div className="flex justify-between py-0.5">
                <span className="text-[#54595d] dark:text-slate-400 font-medium">Volatility Cluster:</span>
                <span className="text-[#202122] dark:text-slate-200">Clustered Vol (GARCH)</span>
              </div>
              <div className="flex justify-between py-0.5">
                <span className="text-[#54595d] dark:text-slate-400 font-medium">Liquidity State:</span>
                <span className="text-[#137333] dark:text-emerald-400 font-semibold">Accommodative</span>
              </div>
            </div>
          );
        }

        if (catUpper.includes('STRUCTURE') || catUpper.includes('FACTOR') || tagsUpper.includes('FACTOR') || tagsUpper.includes('ALPHA')) {
          return (
            <div className="border-t border-[#a2a9b1] dark:border-[#384252] bg-[#f1f3f5] dark:bg-[#172233] p-2.5 space-y-1 text-[11px]">
              <div className="font-semibold text-[#202122] dark:text-[#c4d1e2] border-b border-[#c8ccd1] dark:border-[#2e3b4e] pb-1 mb-1.5 flex items-center gap-1">
                <span>📐</span>
                <span>Alpha Factor Specification</span>
              </div>
              <div className="flex justify-between py-0.5">
                <span className="text-[#54595d] dark:text-slate-400 font-medium">Factor Family:</span>
                <span className="font-semibold text-[#0b0080] dark:text-cyan-300">Microstructure / Orderflow</span>
              </div>
              <div className="flex justify-between py-0.5">
                <span className="text-[#54595d] dark:text-slate-400 font-medium">Decay Half-Life:</span>
                <span className="text-[#202122] dark:text-slate-200">~15m - 4h</span>
              </div>
              <div className="flex justify-between py-0.5">
                <span className="text-[#54595d] dark:text-slate-400 font-medium">Capacity Tier:</span>
                <span className="text-[#137333] dark:text-emerald-400 font-semibold">Institutional ($50M+)</span>
              </div>
            </div>
          );
        }

        if (catUpper.includes('CRYPTO') || catUpper.includes('SETTLEMENT') || tagsUpper.includes('PROTOCOL')) {
          return (
            <div className="border-t border-[#a2a9b1] dark:border-[#384252] bg-[#f1f3f5] dark:bg-[#172233] p-2.5 space-y-1 text-[11px]">
              <div className="font-semibold text-[#202122] dark:text-[#c4d1e2] border-b border-[#c8ccd1] dark:border-[#2e3b4e] pb-1 mb-1.5 flex items-center gap-1">
                <span>⚡</span>
                <span>Protocol & Settlement Specification</span>
              </div>
              <div className="flex justify-between py-0.5">
                <span className="text-[#54595d] dark:text-slate-400 font-medium">Settlement Layer:</span>
                <span className="font-semibold text-[#0b0080] dark:text-purple-300">L1 / L2 Rollup</span>
              </div>
              <div className="flex justify-between py-0.5">
                <span className="text-[#54595d] dark:text-slate-400 font-medium">Finality Class:</span>
                <span className="text-[#202122] dark:text-slate-200">Deterministic</span>
              </div>
              <div className="flex justify-between py-0.5">
                <span className="text-[#54595d] dark:text-slate-400 font-medium">Custody Audit:</span>
                <span className="text-[#137333] dark:text-emerald-400 font-semibold">Zero-Rehypothecation</span>
              </div>
            </div>
          );
        }

        return (
          <div className="border-t border-[#a2a9b1] dark:border-[#384252] bg-[#f1f3f5] dark:bg-[#172233] p-2.5 space-y-1 text-[11px]">
            <div className="font-semibold text-[#202122] dark:text-[#c4d1e2] border-b border-[#c8ccd1] dark:border-[#2e3b4e] pb-1 mb-1.5 flex items-center gap-1">
              <span>📊</span>
              <span>Quantitative Profile</span>
            </div>
            <div className="flex justify-between py-0.5">
              <span className="text-[#54595d] dark:text-slate-400 font-medium">Audit Framework:</span>
              <span className="text-[#202122] dark:text-slate-200">Epistemic Taxonomy (L2)</span>
            </div>
            <div className="flex justify-between py-0.5">
              <span className="text-[#54595d] dark:text-slate-400 font-medium">Falsifiability:</span>
              <span className="text-[#137333] dark:text-emerald-400 font-semibold">CPCV Testable</span>
            </div>
          </div>
        );
      })()}

      {/* External Original Link */}
      {article.source_url && (
        <div className="p-2 border-t border-[#c8ccd1] dark:border-[#2e3846] bg-[#eaecf0] dark:bg-[#1b2536] text-center">
          <a
            href={article.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-[11px] text-[#3366cc] dark:text-[#6fa8dc] hover:underline font-medium"
          >
            <ExternalLink size={11} /> View Primary Source
          </a>
        </div>
      )}
    </aside>
  );
};
