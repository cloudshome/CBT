import React, { useState, useEffect, useCallback } from 'react';
import {
  BookOpen,
  Search,
  Plus,
  ExternalLink,
  ShieldCheck,
  AlertTriangle,
  FileText,
  Video,
  Globe,
  Sparkles,
  RefreshCw,
  Copy,
  Check,
  Link2,
  Layers,
  TrendingUp,
  Bookmark,
} from 'lucide-react';
import { api } from '../../services/api';
import {
  WikiArticleSummary,
  WikiArticleDetail,
  EpistemicStatus,
} from '../../types';

interface ResearchWikipediaDeskProps {
  onNotify?: (type: 'success' | 'error' | 'info' | 'warning', title: string, msg: string) => void;
}

const CATEGORIES = [
  'ALL',
  'Macro Geopolitics & Hegemony',
  'Monetary Policy & Debt Cycles',
  'Quantitative Market Structure',
  'Crypto & Decentralized Settlement',
];

export const ResearchWikipediaDesk: React.FC<ResearchWikipediaDeskProps> = ({ onNotify }) => {
  // Articles state
  const [articles, setArticles] = useState<WikiArticleSummary[]>([]);
  const [selectedArticleId, setSelectedArticleId] = useState<string | null>(null);
  const [activeArticle, setActiveArticle] = useState<WikiArticleDetail | null>(null);
  const [isLoadingList, setIsLoadingList] = useState<boolean>(true);
  const [isLoadingArticle, setIsLoadingArticle] = useState<boolean>(false);

  // Filter & Search state
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [selectedCategory, setSelectedCategory] = useState<string>('ALL');

  // Ingest Form state
  const [inputUrlOrText, setInputUrlOrText] = useState<string>('');
  const [inputTitle, setInputTitle] = useState<string>('');
  const [isIngesting, setIsIngesting] = useState<boolean>(false);
  const [isCopied, setIsCopied] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState<'ARTICLE' | 'MARKDOWN' | 'PROVENANCE'>('ARTICLE');

  // Load article list
  const loadArticles = useCallback(async () => {
    try {
      setIsLoadingList(true);
      const res = await api.getWikiArticles(
        selectedCategory === 'ALL' ? undefined : selectedCategory,
        searchQuery || undefined
      );
      setArticles(res.articles || []);
      if (res.articles && res.articles.length > 0 && !selectedArticleId) {
        setSelectedArticleId(res.articles[0].article_id);
      }
    } catch (err: any) {
      onNotify?.('error', 'Wikipedia Load Failed', err.message || 'Could not load articles.');
    } finally {
      setIsLoadingList(false);
    }
  }, [selectedCategory, searchQuery, selectedArticleId, onNotify]);

  // Initial load
  useEffect(() => {
    loadArticles();
  }, [loadArticles]);

  // Load selected article details
  useEffect(() => {
    if (!selectedArticleId) {
      setActiveArticle(null);
      return;
    }
    const fetchDetail = async () => {
      try {
        setIsLoadingArticle(true);
        const res = await api.getWikiArticle(selectedArticleId);
        setActiveArticle(res.article);
      } catch (err: any) {
        onNotify?.('error', 'Article Load Error', err.message || 'Could not load article detail.');
      } finally {
        setIsLoadingArticle(false);
      }
    };
    fetchDetail();
  }, [selectedArticleId, onNotify]);

  // Handle ingestion of a link or note
  const handleIngest = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!inputUrlOrText.trim()) {
      onNotify?.('warning', 'Missing Input', 'Please paste a URL (Facebook, YouTube, X, web) or note text.');
      return;
    }

    try {
      setIsIngesting(true);
      const res = await api.ingestWikiArticle({
        url_or_text: inputUrlOrText.trim(),
        title: inputTitle.trim() || undefined,
      });

      onNotify?.('success', 'Wiki Article Created', `"${res.article.title}" cross-verified and stored.`);
      setInputUrlOrText('');
      setInputTitle('');
      await loadArticles();
      setSelectedArticleId(res.article.article_id);
    } catch (err: any) {
      onNotify?.('error', 'Ingestion Failed', err.message || 'Could not ingest material.');
    } finally {
      setIsIngesting(false);
    }
  };

  // Handle re-verification
  const handleReverify = async () => {
    if (!selectedArticleId) return;
    try {
      setIsLoadingArticle(true);
      const res = await api.reverifyWikiArticle(selectedArticleId);
      setActiveArticle(res.article);
      onNotify?.('success', 'Epistemic Re-verification Complete', 'Audit benchmark refreshed.');
      await loadArticles();
    } catch (err: any) {
      onNotify?.('error', 'Re-verification Failed', err.message);
    } finally {
      setIsLoadingArticle(false);
    }
  };

  // Copy markdown to clipboard
  const handleCopyMarkdown = () => {
    if (!activeArticle) return;
    navigator.clipboard.writeText(activeArticle.full_markdown_content);
    setIsCopied(true);
    setTimeout(() => setIsCopied(false), 2000);
    onNotify?.('info', 'Copied to Clipboard', 'Full Wikipedia Markdown copied.');
  };

  // Status badge styling
  const getStatusBadge = (status: EpistemicStatus) => {
    switch (status) {
      case 'FACT':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
            <ShieldCheck size={12} /> FACT
          </span>
        );
      case 'HYPOTHESIS':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold bg-blue-500/10 text-blue-400 border border-blue-500/30">
            <Sparkles size={12} /> HYPOTHESIS
          </span>
        );
      case 'CONTRADICTION':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold bg-rose-500/10 text-rose-400 border border-rose-500/30">
            <AlertTriangle size={12} /> CONTRADICTION
          </span>
        );
      case 'NARRATIVE':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/30">
            <BookOpen size={12} /> NARRATIVE
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold bg-slate-500/10 text-slate-400 border border-slate-500/30">
            UNVERIFIED
          </span>
        );
    }
  };

  // Source icon
  const getSourceIcon = (sourceType: string) => {
    if (sourceType.includes('FACEBOOK') || sourceType.includes('VIDEO') || sourceType.includes('REEL')) {
      return <Video size={14} className="text-pink-400" />;
    }
    if (sourceType.includes('YOUTUBE')) {
      return <Video size={14} className="text-red-400" />;
    }
    if (sourceType.includes('PDF')) {
      return <FileText size={14} className="text-amber-400" />;
    }
    return <Globe size={14} className="text-blue-400" />;
  };

  return (
    <div className="flex flex-col h-full bg-slate-950 text-slate-100 rounded-lg border border-slate-800/80 overflow-hidden shadow-2xl">
      {/* 1. Master Top Header & Quick Ingest Bar */}
      <div className="bg-slate-900/90 border-b border-slate-800 p-4">
        <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-3 mb-4">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-lg bg-gradient-to-br from-indigo-500/20 to-purple-500/20 border border-indigo-500/30 text-indigo-400 shadow-inner">
              <BookOpen size={24} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-bold tracking-tight text-white">SKY Research Wikipedia</h2>
                <span className="px-2 py-0.5 text-[10px] font-mono tracking-wider font-semibold rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                  LIVING JOURNAL
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                Permanent cross-verified repository for macro reels, YouTube talks, PDFs, and intelligence feeds. Every claim fact-checked and preserved.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={loadArticles}
              className="px-3 py-1.5 rounded bg-slate-800 hover:bg-slate-700 text-xs text-slate-300 flex items-center gap-1.5 border border-slate-700 transition"
              title="Refresh articles"
            >
              <RefreshCw size={13} className={isLoadingList ? 'animate-spin' : ''} />
              <span>Refresh</span>
            </button>
          </div>
        </div>

        {/* Quick-Drop URL Ingestion Input */}
        <form onSubmit={handleIngest} className="flex flex-col sm:flex-row gap-2 bg-slate-950/80 p-2.5 rounded-lg border border-slate-800 shadow-inner">
          <div className="relative flex-1">
            <Link2 size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-indigo-400" />
            <input
              type="text"
              value={inputUrlOrText}
              onChange={(e) => setInputUrlOrText(e.target.value)}
              placeholder="Paste any link (Facebook Reel, YouTube, X, web article, PDF) or paste research text..."
              className="w-full bg-slate-900 border border-slate-700/80 rounded pl-9 pr-3 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500 font-mono transition"
            />
          </div>
          <div className="w-full sm:w-64">
            <input
              type="text"
              value={inputTitle}
              onChange={(e) => setInputTitle(e.target.value)}
              placeholder="Custom title (optional)..."
              className="w-full bg-slate-900 border border-slate-700/80 rounded px-3 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition"
            />
          </div>
          <button
            type="submit"
            disabled={isIngesting || !inputUrlOrText.trim()}
            className="px-4 py-2 rounded bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 disabled:opacity-50 text-white text-xs font-semibold flex items-center justify-center gap-1.5 shadow-md shadow-indigo-600/20 transition cursor-pointer"
          >
            {isIngesting ? (
              <>
                <RefreshCw size={13} className="animate-spin" />
                <span>Cross-Verifying...</span>
              </>
            ) : (
              <>
                <Plus size={14} />
                <span>Ingest & Store in Wiki</span>
              </>
            )}
          </button>
        </form>
      </div>

      {/* 2. Main Split View: Left Articles Index vs Right Article Reader */}
      <div className="flex-1 flex flex-col md:flex-row min-h-0 overflow-hidden">
        {/* Left Column: Article Browser */}
        <div className="w-full md:w-80 lg:w-96 border-r border-slate-800 bg-slate-950 flex flex-col min-h-0">
          {/* Category selector */}
          <div className="p-3 border-b border-slate-800/80 flex gap-1.5 overflow-x-auto no-scrollbar">
            {CATEGORIES.map((cat) => (
              <button
                key={cat}
                onClick={() => setSelectedCategory(cat)}
                className={`px-2.5 py-1 rounded text-[11px] font-medium whitespace-nowrap transition ${
                  selectedCategory === cat
                    ? 'bg-indigo-600 text-white font-semibold shadow-sm'
                    : 'bg-slate-900 text-slate-400 hover:text-slate-200 hover:bg-slate-800 border border-slate-800'
                }`}
              >
                {cat === 'ALL' ? 'All Entries' : cat.split(' ')[0]}
              </button>
            ))}
          </div>

          {/* Search box */}
          <div className="p-3 border-b border-slate-800/80">
            <div className="relative">
              <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search encyclopedia entries, claims..."
                className="w-full bg-slate-900 border border-slate-800 rounded pl-8 pr-3 py-1.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500/80 transition"
              />
            </div>
          </div>

          {/* Articles list */}
          <div className="flex-1 overflow-y-auto p-2 space-y-2">
            {isLoadingList ? (
              <div className="p-8 text-center text-xs text-slate-500 flex flex-col items-center gap-2">
                <RefreshCw size={18} className="animate-spin text-indigo-400" />
                <span>Loading Wikipedia index...</span>
              </div>
            ) : articles.length === 0 ? (
              <div className="p-8 text-center text-xs text-slate-500">
                <BookOpen size={24} className="mx-auto mb-2 text-slate-600" />
                <p>No articles match your search.</p>
                <p className="text-[11px] text-slate-600 mt-1">Paste a link above to create the first entry!</p>
              </div>
            ) : (
              articles.map((item) => {
                const isSelected = item.article_id === selectedArticleId;
                return (
                  <div
                    key={item.article_id}
                    onClick={() => setSelectedArticleId(item.article_id)}
                    className={`p-3 rounded-lg border cursor-pointer transition flex flex-col gap-1.5 ${
                      isSelected
                        ? 'bg-slate-900/90 border-indigo-500/60 shadow-lg shadow-indigo-950/50'
                        : 'bg-slate-900/40 border-slate-800/80 hover:bg-slate-900/80 hover:border-slate-700'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-1.5">
                        {getSourceIcon(item.source_type)}
                        <span className="text-[10px] font-mono text-slate-400 uppercase tracking-wider">
                          {item.source_type.replace('_', ' ')}
                        </span>
                      </div>
                      <span className="px-1.5 py-0.5 text-[10px] font-mono font-bold rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                        {item.verification_score.toFixed(0)}% Rigor
                      </span>
                    </div>

                    <h4 className={`text-xs font-semibold line-clamp-2 leading-relaxed ${isSelected ? 'text-indigo-200' : 'text-slate-200'}`}>
                      {item.title}
                    </h4>

                    <p className="text-[11px] text-slate-400 line-clamp-2 leading-normal">
                      {item.executive_summary}
                    </p>

                    <div className="flex items-center justify-between text-[10px] text-slate-500 pt-1 border-t border-slate-800/60">
                      <span className="font-mono text-slate-400">{item.provenance_id}</span>
                      <span>{item.claims_count} claims verified</span>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Right Column: Wikipedia Article Reader */}
        <div className="flex-1 bg-slate-950 flex flex-col min-h-0 overflow-y-auto">
          {isLoadingArticle ? (
            <div className="flex-1 flex flex-col items-center justify-center p-12 text-slate-500 gap-3">
              <RefreshCw size={24} className="animate-spin text-indigo-400" />
              <span className="text-xs">Fetching cross-verified research dossier...</span>
            </div>
          ) : !activeArticle ? (
            <div className="flex-1 flex flex-col items-center justify-center p-12 text-slate-500 gap-2">
              <BookOpen size={36} className="text-slate-700 mb-1" />
              <h3 className="text-sm font-bold text-slate-300">Select an Encyclopedia Entry</h3>
              <p className="text-xs text-slate-500 max-w-sm text-center">
                Click any research dossier from the left sidebar or paste a new link above to view verified claims, contradictions, and macro implications.
              </p>
            </div>
          ) : (
            <div className="p-6 max-w-5xl mx-auto w-full space-y-6">
              {/* Article Top Navigation / Action Bar */}
              <div className="flex flex-wrap items-center justify-between gap-3 pb-4 border-b border-slate-800">
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setActiveTab('ARTICLE')}
                    className={`px-3 py-1 rounded text-xs font-medium transition ${
                      activeTab === 'ARTICLE'
                        ? 'bg-indigo-600 text-white font-semibold shadow'
                        : 'text-slate-400 hover:text-white hover:bg-slate-900'
                    }`}
                  >
                    Wikipedia Reader
                  </button>
                  <button
                    onClick={() => setActiveTab('MARKDOWN')}
                    className={`px-3 py-1 rounded text-xs font-medium transition ${
                      activeTab === 'MARKDOWN'
                        ? 'bg-indigo-600 text-white font-semibold shadow'
                        : 'text-slate-400 hover:text-white hover:bg-slate-900'
                    }`}
                  >
                    Raw Markdown
                  </button>
                  <button
                    onClick={() => setActiveTab('PROVENANCE')}
                    className={`px-3 py-1 rounded text-xs font-medium transition ${
                      activeTab === 'PROVENANCE'
                        ? 'bg-indigo-600 text-white font-semibold shadow'
                        : 'text-slate-400 hover:text-white hover:bg-slate-900'
                    }`}
                  >
                    Provenance & Citations
                  </button>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={handleReverify}
                    className="px-2.5 py-1.5 rounded bg-slate-900 hover:bg-slate-800 text-slate-300 text-xs border border-slate-800 flex items-center gap-1.5 transition"
                    title="Re-run fact checking audit against latest datasets"
                  >
                    <RefreshCw size={12} />
                    <span>Re-verify</span>
                  </button>

                  <button
                    onClick={handleCopyMarkdown}
                    className="px-2.5 py-1.5 rounded bg-slate-900 hover:bg-slate-800 text-slate-300 text-xs border border-slate-800 flex items-center gap-1.5 transition"
                    title="Copy full article Markdown for Obsidian / Notion"
                  >
                    {isCopied ? <Check size={12} className="text-emerald-400" /> : <Copy size={12} />}
                    <span>{isCopied ? 'Copied' : 'Export MD'}</span>
                  </button>

                  {activeArticle.source_url && (
                    <a
                      href={activeArticle.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="px-2.5 py-1.5 rounded bg-indigo-600/20 hover:bg-indigo-600/30 text-indigo-300 text-xs border border-indigo-500/30 flex items-center gap-1.5 transition"
                    >
                      <ExternalLink size={12} />
                      <span>Original Source</span>
                    </a>
                  )}
                </div>
              </div>

              {activeTab === 'ARTICLE' && (
                <>
                  {/* Article Title & Provenance Block */}
                  <div>
                    <div className="flex flex-wrap items-center gap-2 mb-2 text-xs">
                      <span className="px-2 py-0.5 rounded font-mono font-bold bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                        {activeArticle.provenance_id}
                      </span>
                      <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 font-medium">
                        {activeArticle.category}
                      </span>
                      <span className="text-slate-500 text-[11px]">
                        Last Verified: {new Date(activeArticle.updated_at).toLocaleString()}
                      </span>
                    </div>

                    <h1 className="text-2xl font-bold text-white tracking-tight leading-snug">
                      {activeArticle.title}
                    </h1>

                    <div className="mt-2 text-xs text-slate-400 flex items-center gap-2">
                      <span>Attributed to: <strong className="text-slate-200">{activeArticle.author_or_speaker}</strong></span>
                      <span>•</span>
                      <span className="flex items-center gap-1">
                        {getSourceIcon(activeArticle.source_type)}
                        <span>{activeArticle.source_type.replace('_', ' ')}</span>
                      </span>
                    </div>
                  </div>

                  {/* Rigor Score Ribbon */}
                  <div className="p-3.5 rounded-lg bg-gradient-to-r from-indigo-950/40 via-purple-950/30 to-slate-900 border border-indigo-500/30 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="p-2 rounded bg-indigo-500/20 text-indigo-400 border border-indigo-500/30">
                        <ShieldCheck size={20} />
                      </div>
                      <div>
                        <div className="text-xs font-bold text-white">Epistemic Verification Score: {activeArticle.verification_score.toFixed(1)}%</div>
                        <div className="text-[11px] text-slate-400">
                          {activeArticle.key_claims.filter(c => c.epistemic_status === 'FACT').length} empirically verified facts,{' '}
                          {activeArticle.key_claims.filter(c => c.epistemic_status === 'HYPOTHESIS').length} forward hypotheses,{' '}
                          {activeArticle.contradictions_detected.length} contradictions detected.
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Section 1: Executive Abstract */}
                  <div className="bg-slate-900/60 p-4 rounded-lg border border-slate-800 space-y-2">
                    <h3 className="text-xs font-bold uppercase tracking-wider text-indigo-300 flex items-center gap-1.5">
                      <BookOpen size={14} />
                      <span>I. Executive Abstract</span>
                    </h3>
                    <p className="text-xs text-slate-300 leading-relaxed">
                      {activeArticle.executive_summary}
                    </p>
                  </div>

                  {/* Section 2: Epistemic Claim Verification Matrix */}
                  <div className="space-y-3">
                    <h3 className="text-xs font-bold uppercase tracking-wider text-indigo-300 flex items-center gap-1.5">
                      <ShieldCheck size={14} />
                      <span>II. Epistemic Claim Verification Matrix</span>
                    </h3>

                    <div className="border border-slate-800 rounded-lg overflow-hidden">
                      <table className="w-full text-left text-xs">
                        <thead className="bg-slate-900 text-slate-400 text-[11px] uppercase font-mono border-b border-slate-800">
                          <tr>
                            <th className="py-2.5 px-3 w-16">ID</th>
                            <th className="py-2.5 px-3">Speaker / Source Claim</th>
                            <th className="py-2.5 px-3 w-32">Status</th>
                            <th className="py-2.5 px-3">Empirical Findings & Cross-Verification</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800/80 bg-slate-950/60">
                          {activeArticle.key_claims.map((claim) => (
                            <tr key={claim.claim_id} className="hover:bg-slate-900/40 transition">
                              <td className="py-3 px-3 font-mono font-bold text-slate-400 align-top">
                                {claim.claim_id}
                              </td>
                              <td className="py-3 px-3 text-slate-200 align-top font-medium leading-relaxed">
                                "{claim.speaker_claim}"
                              </td>
                              <td className="py-3 px-3 align-top">
                                {getStatusBadge(claim.epistemic_status)}
                              </td>
                              <td className="py-3 px-3 text-slate-300 align-top leading-relaxed">
                                <p>{claim.cross_verification_evidence}</p>
                                {claim.empirical_dataset_reference && (
                                  <span className="block mt-1 text-[10px] text-slate-500 font-mono">
                                    Ref: {claim.empirical_dataset_reference}
                                  </span>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  {/* Section 3: Contradictions & Filters */}
                  {activeArticle.contradictions_detected.length > 0 && (
                    <div className="bg-rose-950/20 border border-rose-500/30 p-4 rounded-lg space-y-2">
                      <h3 className="text-xs font-bold uppercase tracking-wider text-rose-400 flex items-center gap-1.5">
                        <AlertTriangle size={14} />
                        <span>III. Epistemic Contradictions & Hype Filters</span>
                      </h3>
                      <ul className="space-y-1 text-xs text-rose-200">
                        {activeArticle.contradictions_detected.map((c, i) => (
                          <li key={i} className="flex items-start gap-2">
                            <span className="text-rose-400">•</span>
                            <span>{c}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Section 4: Macro Implications */}
                  <div className="bg-slate-900/60 p-4 rounded-lg border border-slate-800 space-y-2">
                    <h3 className="text-xs font-bold uppercase tracking-wider text-indigo-300 flex items-center gap-1.5">
                      <TrendingUp size={14} />
                      <span>IV. Macro Regime & Capital Allocation Implications</span>
                    </h3>
                    <p className="text-xs text-slate-300 leading-relaxed whitespace-pre-line">
                      {activeArticle.macro_regime_implications}
                    </p>
                  </div>

                  {/* Section 5: Connected Wiki Topics */}
                  <div className="bg-slate-900/40 p-4 rounded-lg border border-slate-800 space-y-2">
                    <h3 className="text-xs font-bold uppercase tracking-wider text-indigo-300 flex items-center gap-1.5">
                      <Layers size={14} />
                      <span>V. Connected Wiki Dossiers ([[WikiLinks]])</span>
                    </h3>
                    <div className="flex flex-wrap gap-2 pt-1">
                      {activeArticle.wikilinks.map((wl, i) => (
                        <span
                          key={i}
                          onClick={() => setSearchQuery(wl.replace(/\[\[|\]\]/g, ''))}
                          className="px-2.5 py-1 rounded bg-indigo-500/10 hover:bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 text-xs font-mono cursor-pointer transition flex items-center gap-1"
                        >
                          <Bookmark size={11} />
                          {wl}
                        </span>
                      ))}
                    </div>
                  </div>

                  {/* Tags */}
                  <div className="flex flex-wrap gap-1.5 pt-2">
                    {activeArticle.tags.map((tag, i) => (
                      <span key={i} className="px-2 py-0.5 rounded bg-slate-900 text-slate-400 text-[10px] font-mono border border-slate-800">
                        #{tag}
                      </span>
                    ))}
                  </div>
                </>
              )}

              {activeTab === 'MARKDOWN' && (
                <div className="space-y-2">
                  <div className="flex justify-between items-center text-xs text-slate-400">
                    <span>Full Markdown Document (Obsidian & Notion compatible):</span>
                    <button
                      onClick={handleCopyMarkdown}
                      className="px-2.5 py-1 rounded bg-indigo-600 hover:bg-indigo-500 text-white flex items-center gap-1 transition"
                    >
                      {isCopied ? <Check size={12} /> : <Copy size={12} />}
                      <span>{isCopied ? 'Copied' : 'Copy'}</span>
                    </button>
                  </div>
                  <pre className="p-4 rounded-lg bg-slate-900 border border-slate-800 text-slate-200 text-xs font-mono overflow-x-auto whitespace-pre-wrap leading-relaxed max-h-[600px]">
                    {activeArticle.full_markdown_content}
                  </pre>
                </div>
              )}

              {activeTab === 'PROVENANCE' && (
                <div className="bg-slate-900/60 p-4 rounded-lg border border-slate-800 space-y-4 text-xs">
                  <h3 className="font-bold text-white uppercase tracking-wider text-xs">Cryptographic & Provenance Ledger</h3>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-slate-300 font-mono text-[11px]">
                    <div className="p-3 rounded bg-slate-950 border border-slate-800">
                      <span className="text-slate-500 block mb-1">Article ID:</span>
                      <span className="text-white select-all">{activeArticle.article_id}</span>
                    </div>
                    <div className="p-3 rounded bg-slate-950 border border-slate-800">
                      <span className="text-slate-500 block mb-1">Provenance Citation:</span>
                      <span className="text-indigo-400 font-bold select-all">{activeArticle.provenance_id}</span>
                    </div>
                    <div className="p-3 rounded bg-slate-950 border border-slate-800">
                      <span className="text-slate-500 block mb-1">Disk Persistence:</span>
                      <span className="text-slate-300 select-all">data/research_wiki/articles/{activeArticle.article_id}.md</span>
                    </div>
                    <div className="p-3 rounded bg-slate-950 border border-slate-800">
                      <span className="text-slate-500 block mb-1">Database Partition:</span>
                      <span className="text-slate-300 select-all">data/research_wiki.db (wiki_articles)</span>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
