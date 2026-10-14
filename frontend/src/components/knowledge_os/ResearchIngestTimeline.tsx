import React, { useState, useEffect, useCallback } from 'react';
import {
  FileText,
  Calendar,
  Search,
  Download,
  ExternalLink,
  ShieldCheck,
  AlertCircle,
  HelpCircle,
  Copy,
  Check,
  BookOpen,
  Filter,
  Clock,
  Hash,
  RefreshCw,
  FileCode,
  Globe,
  Video,
} from 'lucide-react';
import { api } from '../../services/api';
import { WikiTimelineItem } from '../../types';

interface ResearchIngestTimelineProps {
  onSelectArticle?: (articleId: string) => void;
  selectedDate?: string | null;
  onClearDateFilter?: () => void;
}

export const ResearchIngestTimeline: React.FC<ResearchIngestTimelineProps> = ({
  onSelectArticle,
  selectedDate,
  onClearDateFilter,
}) => {
  const [timelineItems, setTimelineItems] = useState<WikiTimelineItem[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [selectedType, setSelectedType] = useState<string>('ALL');
  const [copiedHash, setCopiedHash] = useState<string | null>(null);

  const loadTimeline = useCallback(async () => {
    try {
      setIsLoading(true);
      const res = await api.getWikiTimeline({
        limit: 100,
        source_type: selectedType !== 'ALL' ? selectedType : undefined,
        search: searchQuery.trim() || undefined,
        date: selectedDate || undefined,
      });
      setTimelineItems(res.timeline || []);
      setTotalCount(res.total_count || 0);
    } catch (err) {
      console.error('Failed to load research timeline:', err);
    } finally {
      setIsLoading(false);
    }
  }, [selectedType, searchQuery, selectedDate]);

  useEffect(() => {
    loadTimeline();
  }, [loadTimeline]);

  const handleCopyHash = (hash: string) => {
    if (!hash) return;
    navigator.clipboard.writeText(hash);
    setCopiedHash(hash);
    setTimeout(() => setCopiedHash(null), 2000);
  };

  const getSourceIcon = (type: string) => {
    switch (type.toUpperCase()) {
      case 'PDF':
      case 'PDF_DOCUMENT':
        return <FileText className="w-4 h-4 text-rose-400" />;
      case 'YOUTUBE':
      case 'YOUTUBE_VIDEO':
        return <Video className="w-4 h-4 text-red-500" />;
      case 'CODE_FILE':
        return <FileCode className="w-4 h-4 text-emerald-400" />;
      default:
        return <Globe className="w-4 h-4 text-cyan-400" />;
    }
  };

  return (
    <div className="flex flex-col h-full bg-slate-950 text-slate-100 p-6 space-y-6 overflow-y-auto">
      {/* Top Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-800 pb-5">
        <div>
          <div className="flex items-center gap-2">
            <Clock className="w-6 h-6 text-cyan-400" />
            <h2 className="text-xl font-bold tracking-tight text-white">
              Research Ingestion Chronology & Vault Registry
            </h2>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Deterministic timestamped provenance ledger tracking all uploaded research papers, PDFs, claims, and verified theses.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => loadTimeline()}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-slate-800 hover:bg-slate-700 text-xs text-slate-200 transition"
            title="Refresh Timeline"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
          <div className="px-3 py-1 rounded bg-cyan-950/60 border border-cyan-800/50 text-cyan-300 text-xs font-mono font-semibold">
            {totalCount} Ingested Sources
          </div>
        </div>
      </div>

      {/* Date Filter Alert Banner */}
      {selectedDate && (
        <div className="flex items-center justify-between px-4 py-2.5 rounded-lg bg-cyan-950/40 border border-cyan-800/60 text-xs text-cyan-200">
          <div className="flex items-center gap-2">
            <Calendar className="w-4 h-4 text-cyan-400" />
            <span>
              Filtered by Calendar Date: <strong className="font-mono text-white">{selectedDate}</strong>
            </span>
          </div>
          {onClearDateFilter && (
            <button
              onClick={onClearDateFilter}
              className="px-2 py-0.5 rounded bg-cyan-900/50 hover:bg-cyan-800 text-cyan-300 text-xs font-medium transition"
            >
              Clear Filter
            </button>
          )}
        </div>
      )}

      {/* Search and Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[280px]">
          <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-500" />
          <input
            type="text"
            placeholder="Search papers by title, author, filename, or SHA-256 hash..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-9 pr-4 py-2 bg-slate-900/80 border border-slate-800 rounded-lg text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500/50 transition"
          />
        </div>

        <div className="flex items-center gap-2">
          <Filter className="w-3.5 h-3.5 text-slate-400" />
          <select
            value={selectedType}
            onChange={(e) => setSelectedType(e.target.value)}
            className="bg-slate-900 border border-slate-800 text-slate-300 text-xs rounded-lg px-3 py-2 focus:outline-none focus:border-cyan-500/50"
          >
            <option value="ALL">All Source Types</option>
            <option value="PDF">PDF Documents</option>
            <option value="WEB_ARTICLE">Web Articles</option>
            <option value="YOUTUBE_VIDEO">YouTube Transcripts</option>
            <option value="RESEARCH_NOTE">Research Notes</option>
          </select>
        </div>
      </div>

      {/* Table Container */}
      <div className="border border-slate-800/80 rounded-xl overflow-hidden bg-slate-900/40 backdrop-blur-sm">
        {isLoading ? (
          <div className="p-12 text-center text-slate-400 flex flex-col items-center gap-3">
            <RefreshCw className="w-6 h-6 animate-spin text-cyan-400" />
            <p className="text-xs">Loading institutional research records...</p>
          </div>
        ) : timelineItems.length === 0 ? (
          <div className="p-12 text-center text-slate-400 space-y-2">
            <FileText className="w-8 h-8 text-slate-600 mx-auto" />
            <h4 className="text-sm font-semibold text-slate-300">No Research Documents Found</h4>
            <p className="text-xs text-slate-500 max-w-md mx-auto">
              {searchQuery || selectedDate
                ? 'Try adjusting your search query or calendar date filter.'
                : 'Upload PDFs in the Drop Zone or import from Ubuntu via "python scripts/sync_research_vault.py --import".'}
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-slate-800 bg-slate-900/90 text-slate-400 uppercase text-[10px] tracking-wider font-semibold">
                  <th className="py-3 px-4">Date / Time (UTC)</th>
                  <th className="py-3 px-4">Document Title & Source</th>
                  <th className="py-3 px-4">Author / Origin</th>
                  <th className="py-3 px-4">Cryptographic Hash</th>
                  <th className="py-3 px-4">Epistemic Claims Breakdown</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/50">
                {timelineItems.map((item) => (
                  <tr
                    key={item.source_id}
                    className="hover:bg-slate-800/30 transition-colors group"
                  >
                    {/* Timestamp */}
                    <td className="py-3.5 px-4 whitespace-nowrap text-slate-300 font-mono text-[11px]">
                      <div className="flex items-center gap-1.5">
                        <Calendar className="w-3 h-3 text-slate-500" />
                        <span>{item.created_at_formatted || 'N/A'}</span>
                      </div>
                    </td>

                    {/* Title & File details */}
                    <td className="py-3.5 px-4 max-w-sm">
                      <div className="flex items-start gap-2.5">
                        <div className="mt-0.5 p-1 rounded bg-slate-800/80 border border-slate-700/60">
                          {getSourceIcon(item.source_type)}
                        </div>
                        <div className="min-w-0">
                          <p className="font-semibold text-slate-100 truncate hover:text-cyan-300 transition" title={item.title}>
                            {item.title}
                          </p>
                          <div className="flex items-center gap-2 mt-0.5 text-[10px] text-slate-400">
                            <span className="uppercase px-1.5 py-0.2 rounded bg-slate-800 text-slate-300 font-mono">
                              {item.source_type}
                            </span>
                            {item.is_file && item.file_size_mb && item.file_size_mb > 0 && (
                              <span className="font-mono text-slate-400">
                                {item.file_size_mb} MB
                              </span>
                            )}
                            {item.wiki_category && (
                              <span className="text-slate-500 truncate max-w-[120px]">
                                • {item.wiki_category}
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    </td>

                    {/* Author */}
                    <td className="py-3.5 px-4 text-slate-300">
                      <span className="truncate block max-w-[150px]" title={item.author_or_creator}>
                        {item.author_or_creator || 'Institutional Lab'}
                      </span>
                    </td>

                    {/* Hash */}
                    <td className="py-3.5 px-4 whitespace-nowrap">
                      {item.content_hash ? (
                        <button
                          onClick={() => handleCopyHash(item.content_hash)}
                          className="flex items-center gap-1 font-mono text-[11px] text-slate-400 hover:text-cyan-300 bg-slate-900 border border-slate-800 px-2 py-0.5 rounded transition"
                          title="Click to copy SHA-256 hash"
                        >
                          <Hash className="w-2.5 h-2.5 text-slate-500" />
                          <span>{item.content_hash.slice(0, 10)}...</span>
                          {copiedHash === item.content_hash ? (
                            <Check className="w-3 h-3 text-emerald-400" />
                          ) : (
                            <Copy className="w-3 h-3 text-slate-500" />
                          )}
                        </button>
                      ) : (
                        <span className="text-slate-600 font-mono text-[10px]">UNHASHED</span>
                      )}
                    </td>

                    {/* Claims Breakdown */}
                    <td className="py-3.5 px-4 whitespace-nowrap">
                      <div className="flex items-center gap-1.5">
                        <span
                          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-mono font-medium bg-emerald-950/60 border border-emerald-800/40 text-emerald-300"
                          title="Empirically Verified Facts"
                        >
                          <ShieldCheck className="w-2.5 h-2.5" />
                          {item.facts_count} Facts
                        </span>
                        <span
                          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-mono font-medium bg-amber-950/60 border border-amber-800/40 text-amber-300"
                          title="Hypotheses Requiring Validation"
                        >
                          <HelpCircle className="w-2.5 h-2.5" />
                          {item.hypotheses_count} Hypo
                        </span>
                        {item.contradictions_count > 0 && (
                          <span
                            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-mono font-medium bg-rose-950/60 border border-rose-800/40 text-rose-300"
                            title="Dialectical Contradictions"
                          >
                            <AlertCircle className="w-2.5 h-2.5" />
                            {item.contradictions_count}
                          </span>
                        )}
                      </div>
                    </td>

                    {/* Actions */}
                    <td className="py-3.5 px-4 whitespace-nowrap text-right space-x-2">
                      {item.download_url && (
                        <a
                          href={item.download_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium border border-slate-700 transition"
                          title="View / Download Original PDF"
                        >
                          <Download className="w-3 h-3 text-cyan-400" />
                          <span>PDF</span>
                        </a>
                      )}

                      {item.wiki_article_id && onSelectArticle ? (
                        <button
                          onClick={() => onSelectArticle(item.wiki_article_id!)}
                          className="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-cyan-950 hover:bg-cyan-900 text-cyan-200 text-xs font-medium border border-cyan-800/60 transition"
                          title="Open Formatted Wikipedia Article"
                        >
                          <BookOpen className="w-3 h-3 text-cyan-400" />
                          <span>Article</span>
                        </button>
                      ) : item.original_url && item.original_url.startsWith('http') ? (
                        <a
                          href={item.original_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs transition"
                        >
                          <ExternalLink className="w-3 h-3" />
                          <span>Link</span>
                        </a>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
