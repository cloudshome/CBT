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
  Compass,
  Download,
  Inbox,
  CheckCircle2,
  XCircle,
} from 'lucide-react';
import { api } from '../../services/api';
import {
  WikiArticleSummary,
  WikiArticleDetail,
  ResearchSourceData,
} from '../../types';
import { WikiInfobox } from './WikiInfobox';
import { WikiLink } from './WikiLinkHover';


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
  const [activeSource, setActiveSource] = useState<ResearchSourceData | null>(null);
  const [isLoadingList, setIsLoadingList] = useState<boolean>(true);
  const [isLoadingArticle, setIsLoadingArticle] = useState<boolean>(false);

  // Filter & Search state
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [selectedCategory, setSelectedCategory] = useState<string>('ALL');

  // Open Web Search Agent State
  const [isWebSearching, setIsWebSearching] = useState<boolean>(false);
  const [webCandidates, setWebCandidates] = useState<Array<any>>([]);
  const [showWebResults, setShowWebResults] = useState<boolean>(false);
  const [isIngestingCandidate, setIsIngestingCandidate] = useState<string | null>(null);

  // Ingest Form state
  const [inputUrlOrText, setInputUrlOrText] = useState<string>('');
  const [inputTitle, setInputTitle] = useState<string>('');
  const [isIngesting, setIsIngesting] = useState<boolean>(false);
  const [isCopied, setIsCopied] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState<'ARTICLE' | 'MARKDOWN' | 'PROVENANCE'>('ARTICLE');

  // Human-in-the-Loop Triage Inbox State (Phase 4)
  const [showTriageDrawer, setShowTriageDrawer] = useState<boolean>(false);
  const [triageItems, setTriageItems] = useState<Array<any>>([]);
  const [isLoadingTriage, setIsLoadingTriage] = useState<boolean>(false);
  const [isProcessingTriage, setIsProcessingTriage] = useState<string | null>(null);

  // Strategy Bridge State (Phase 4)
  const [isBridgingClaim, setIsBridgingClaim] = useState<string | null>(null);

  // Dialectical Contradictions State (Phase 3)
  const [contradictions, setContradictions] = useState<Array<any>>([]);

  // Load triage inbox
  const loadTriageInbox = useCallback(async () => {
    try {
      setIsLoadingTriage(true);
      const res = await api.getWikiTriageInbox('STAGING');
      setTriageItems(res.items || []);
    } catch (err: any) {
      console.warn('Could not load triage inbox:', err);
    } finally {
      setIsLoadingTriage(false);
    }
  }, []);

  // Load tracked contradictions
  const loadContradictions = useCallback(async () => {
    try {
      const res = await api.getWikiContradictions(selectedArticleId || undefined);
      setContradictions(res.contradictions || []);
    } catch (err: any) {
      console.warn('Could not load contradictions:', err);
    }
  }, [selectedArticleId]);

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
    loadTriageInbox();
  }, [loadArticles, loadTriageInbox]);

  // Load selected article details & contradictions
  useEffect(() => {
    if (!selectedArticleId) {
      setActiveArticle(null);
      setActiveSource(null);
      return;
    }
    const fetchDetail = async () => {
      try {
        setIsLoadingArticle(true);
        const res = await api.getWikiArticle(selectedArticleId);
        setActiveArticle(res.article);
        setActiveSource(res.source || null);
        loadContradictions();
      } catch (err: any) {
        onNotify?.('error', 'Article Load Error', err.message || 'Could not load article detail.');
      } finally {
        setIsLoadingArticle(false);
      }
    };
    fetchDetail();
  }, [selectedArticleId, loadContradictions, onNotify]);

  // Handle Triage candidate approval and merge
  const handleMergeTriageItem = async (itemId: string) => {
    try {
      setIsProcessingTriage(itemId);
      const res = await api.mergeWikiTriageItem(itemId);
      onNotify?.('success', 'Candidate Approved & Merged', `"${res.article.title}" published to Research Wikipedia.`);
      await loadArticles();
      await loadTriageInbox();
      if (res.article?.article_id) {
        setSelectedArticleId(res.article.article_id);
        setShowTriageDrawer(false);
      }
    } catch (err: any) {
      onNotify?.('error', 'Merge Failed', err.message || 'Could not merge candidate.');
    } finally {
      setIsProcessingTriage(null);
    }
  };

  // Handle Triage candidate rejection
  const handleRejectTriageItem = async (itemId: string) => {
    try {
      setIsProcessingTriage(itemId);
      await api.updateWikiTriageStatus(itemId, 'REJECTED');
      onNotify?.('info', 'Candidate Rejected', 'Candidate marked as rejected in triage ledger.');
      await loadTriageInbox();
    } catch (err: any) {
      onNotify?.('error', 'Update Failed', err.message || 'Could not reject candidate.');
    } finally {
      setIsProcessingTriage(null);
    }
  };

  // Handle Bridging Hypothesis to Strategy Desk (Phase 4)
  const handleBridgeToStrategy = async (claimId: string) => {
    try {
      setIsBridgingClaim(claimId);
      const res = await api.synthesizeStrategyFromClaim(claimId, 'BTC/USDT', '15m');
      onNotify?.(
        'success',
        'Hypothesis Staged to Backtest Queue',
        `Strategy candidate "${res.candidate?.strategy_name || claimId}" synthesized for closed-bar CPCV walk-forward validation.`
      );
    } catch (err: any) {
      onNotify?.('error', 'Bridge Synthesis Failed', err.message || 'Could not synthesize strategy candidate.');
    } finally {
      setIsBridgingClaim(null);
    }
  };

  // Handle Command Bar input (Phase 5)
  const handleCommandBarKeyDown = async (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key !== 'Enter') return;
    const val = searchQuery.trim();
    if (!val.startsWith('/')) return;

    e.preventDefault();
    const parts = val.split(' ');
    const cmd = parts[0].toLowerCase();
    const param = parts.slice(1).join(' ').trim();

    if (cmd === '/triage') {
      setShowTriageDrawer(true);
      await loadTriageInbox();
      setSearchQuery('');
    } else if (cmd === '/cycle') {
      const topic = param || 'Quantitative Market Structure';
      setSearchQuery('');
      try {
        setIsWebSearching(true);
        onNotify?.('info', 'Research Cycle Launched', `5-Worker bounded cycle started for "${topic}"...`);
        const res = await api.executeResearchCycle(topic, undefined, 3);
        onNotify?.('success', 'Research Cycle Finished', `Extracted ${res.claims_count} claims (${res.duration_ms}ms). Verdict: ${res.critic_verdict}. Staged to Triage Inbox.`);
        await loadTriageInbox();
        setShowTriageDrawer(true);
      } catch (err: any) {
        onNotify?.('error', 'Research Cycle Failed', err.message || 'Error executing cycle.');
      } finally {
        setIsWebSearching(false);
      }
    } else if (cmd === '/wiki') {
      setSearchQuery(param);
    } else if (cmd === '/clear') {
      setSearchQuery('');
      setSelectedCategory('ALL');
    } else if (cmd === '/help') {
      onNotify?.('info', 'Command Bar Shortcuts', 'Available commands: /wiki <term>, /cycle <topic>, /triage, /clear, /help');
    }
  };

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

  // Handle Open Web Discovery
  const handleOpenWebSearch = async () => {
    const q = searchQuery.trim() || inputUrlOrText.trim();
    if (!q) {
      onNotify?.('warning', 'Search Query Required', 'Please enter a search topic in the search box.');
      return;
    }
    try {
      setIsWebSearching(true);
      setShowWebResults(true);
      const res = await api.discoverWebIntelligence(q, selectedCategory === 'ALL' ? 'Quantitative Market Structure' : selectedCategory, 5);
      setWebCandidates(res.candidates || []);
      onNotify?.('info', 'Web Intelligence Discovered', `Found ${res.total_found} research candidates across open web.`);
    } catch (err: any) {
      onNotify?.('error', 'Web Search Failed', err.message || 'Could not query search providers.');
    } finally {
      setIsWebSearching(false);
    }
  };

  // Handle Candidate Auto-Ingest into Wiki
  const handleAutoIngestCandidate = async (candidateUrl: string, title?: string) => {
    try {
      setIsIngestingCandidate(candidateUrl);
      const res = await api.autoIngestWebCandidate(candidateUrl, selectedCategory === 'ALL' ? 'Macro Geopolitics & Hegemony' : selectedCategory, title);
      if (res.status === 'REJECTED_SECURITY_OR_NETWORK') {
        onNotify?.('error', 'Security Blocked', res.error || 'URL violates SSRF boundaries.');
      } else {
        onNotify?.('success', 'Candidate Ingested', `"${res.title || 'Source'}" safely added to Research Wikipedia.`);
        await loadArticles();
        if (res.wiki_article_id) {
          setSelectedArticleId(res.wiki_article_id);
          setShowWebResults(false);
        }
      }
    } catch (err: any) {
      onNotify?.('error', 'Ingest Failed', err.message || 'Failed to ingest web source.');
    } finally {
      setIsIngestingCandidate(null);
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
  const getStatusBadge = (status: string) => {
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
              onClick={() => {
                setShowTriageDrawer(true);
                loadTriageInbox();
              }}
              className="px-3 py-1.5 rounded bg-amber-500/10 hover:bg-amber-500/20 text-xs text-amber-300 flex items-center gap-1.5 border border-amber-500/30 transition cursor-pointer shadow-sm"
              title="Review staged web intelligence candidates"
            >
              <Inbox size={13} />
              <span>Triage Inbox ({triageItems.length})</span>
            </button>
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

          {/* Search box & Open Web Search Action */}
          <div className="p-3 border-b border-slate-800/80 space-y-2">
            <div className="relative">
              <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={handleCommandBarKeyDown}
                placeholder="Search entries or command: /wiki, /cycle, /triage, /help..."
                className="w-full bg-slate-900 border border-slate-800 rounded pl-8 pr-3 py-1.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500/80 transition"
              />
            </div>
            <button
              onClick={handleOpenWebSearch}
              disabled={isWebSearching}
              className="w-full py-1.5 px-2 rounded bg-gradient-to-r from-cyan-950 to-indigo-950 hover:from-cyan-900 hover:to-indigo-900 border border-cyan-500/30 text-cyan-300 hover:text-white text-[11px] font-semibold flex items-center justify-center gap-1.5 transition cursor-pointer shadow-sm"
            >
              <Compass size={13} className={isWebSearching ? 'animate-spin text-cyan-400' : 'text-cyan-400'} />
              <span>{isWebSearching ? 'Searching Open Web...' : 'Search Open Web (AI Agent)'}</span>
            </button>
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

              {/* Open Web Search Discovery Drawer */}
              {showWebResults && (
                <div className="bg-[#0b1220] border border-cyan-500/40 rounded-lg p-4 space-y-3 mb-6 shadow-2xl animate-in fade-in duration-200">
                  <div className="flex items-center justify-between pb-2 border-b border-cyan-500/20">
                    <div className="flex items-center gap-2">
                      <Compass size={18} className="text-cyan-400" />
                      <h3 className="font-bold text-white text-xs tracking-wider">
                        AUTONOMOUS WEB INTELLIGENCE CANDIDATES ({webCandidates.length})
                      </h3>
                    </div>
                    <button
                      onClick={() => setShowWebResults(false)}
                      className="text-slate-400 hover:text-white text-xs px-2 py-0.5 rounded hover:bg-slate-800 transition"
                    >
                      Close
                    </button>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {webCandidates.map((cand) => (
                      <div
                        key={cand.candidate_id}
                        className="bg-slate-900/80 border border-slate-800 p-3 rounded-lg flex flex-col justify-between gap-2 hover:border-cyan-500/40 transition"
                      >
                        <div>
                          <div className="flex items-center justify-between text-[10px] text-cyan-400 mb-1">
                            <span className="font-semibold uppercase truncate max-w-[150px]">{cand.source_domain}</span>
                            <span className="text-slate-500">{cand.provider}</span>
                          </div>
                          <h4 className="font-bold text-slate-100 text-xs line-clamp-2 leading-relaxed">
                            {cand.title}
                          </h4>
                          <p className="text-[11px] text-slate-400 line-clamp-2 mt-1">
                            {cand.snippet}
                          </p>
                        </div>
                        <div className="flex items-center justify-between pt-2 border-t border-slate-800/80">
                          <a
                            href={cand.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-[10px] text-slate-400 hover:text-cyan-300 flex items-center gap-1"
                          >
                            <ExternalLink size={11} /> Open
                          </a>
                          <button
                            onClick={() => handleAutoIngestCandidate(cand.url, cand.title)}
                            disabled={isIngestingCandidate === cand.url}
                            className="px-2.5 py-1 rounded bg-gradient-to-r from-cyan-600 to-indigo-600 hover:from-cyan-500 hover:to-indigo-500 text-white text-[11px] font-bold flex items-center gap-1 transition cursor-pointer disabled:opacity-50"
                          >
                            <Download size={11} />
                            <span>{isIngestingCandidate === cand.url ? 'Ingesting...' : 'Ingest to Wiki'}</span>
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {activeTab === 'ARTICLE' && (
                <div className="flex flex-col-reverse lg:flex-row gap-6 items-start">
                  {/* Left Column: Encyclopedic Content & Claims */}
                  <div className="flex-1 w-full space-y-6">
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


                  {/* Rigor Score & Source Guarantee Ribbon */}
                  <div className="p-3.5 rounded-lg bg-gradient-to-r from-indigo-950/40 via-purple-950/30 to-slate-900 border border-indigo-500/30 flex flex-wrap items-center justify-between gap-3">
                    <div className="flex items-center gap-3">
                      <div className="p-2 rounded bg-indigo-500/20 text-indigo-400 border border-indigo-500/30">
                        <ShieldCheck size={20} />
                      </div>
                      <div>
                        <div className="text-xs font-bold text-white flex items-center gap-2">
                          <span>Epistemic Verification Score: {activeArticle.verification_score.toFixed(1)}%</span>
                          {activeSource && (
                            <span className={`text-[10px] px-2 py-0.5 rounded font-mono font-bold ${
                              activeSource.access_status === 'SUCCESS'
                                ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                                : activeSource.access_status === 'PARTIAL'
                                ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                                : 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
                            }`}>
                              {activeSource.access_status === 'SUCCESS' ? '🟢 100% EXTRACTED' : activeSource.access_status === 'PARTIAL' ? '🟡 PARTIAL ACCESS' : '⚠️ ACCESS BLOCKED (SAVED)'}
                            </span>
                          )}
                        </div>
                        <div className="text-[11px] text-slate-400">
                          {activeArticle.key_claims.filter(c => c.epistemic_status === 'FACT').length} empirically verified facts,{' '}
                          {activeArticle.key_claims.filter(c => c.epistemic_status === 'HYPOTHESIS').length} forward hypotheses,{' '}
                          {activeArticle.contradictions_detected.length} contradictions detected.
                        </div>
                      </div>
                    </div>

                    <div className="text-[11px] px-2.5 py-1 rounded bg-slate-950/70 text-indigo-300 border border-indigo-500/20 flex items-center gap-1.5 font-mono">
                      <span>🔒 Zero Link Loss Guaranteed</span>
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

                  {/* Real-Life Practical Summary (Bengali 5-Point Guide) */}
                  {activeSource?.real_life_summary && (
                    <div className="bg-gradient-to-br from-indigo-950/40 via-slate-900/80 to-purple-950/30 p-4 rounded-lg border border-indigo-500/30 space-y-3">
                      <div className="flex items-center justify-between pb-2 border-b border-indigo-500/20">
                        <h3 className="text-xs font-bold text-indigo-300 flex items-center gap-1.5">
                          <Sparkles size={14} className="text-amber-400" />
                          <span>বাস্তব জীবনের সারসংক্ষেপ (5-Point Practical Guide)</span>
                        </h3>
                        <span className="text-[10px] px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 font-mono">
                          Bengali Actionable Intelligence
                        </span>
                      </div>

                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
                        <div className="p-3 rounded bg-slate-950/60 border border-slate-800">
                          <div className="text-[11px] font-bold text-amber-300 mb-1 flex items-center gap-1">
                            <span>🎯</span> সহজ ভাষায় মূল কথা:
                          </div>
                          <p className="text-slate-200 leading-relaxed">
                            {activeSource.real_life_summary.core_concept_bn}
                          </p>
                        </div>

                        <div className="p-3 rounded bg-slate-950/60 border border-slate-800">
                          <div className="text-[11px] font-bold text-cyan-300 mb-1 flex items-center gap-1">
                            <span>📈</span> বাস্তব মার্কেট প্রভাব:
                          </div>
                          <p className="text-slate-200 leading-relaxed">
                            {activeSource.real_life_summary.practical_market_impact}
                          </p>
                        </div>

                        <div className="p-3 rounded bg-slate-950/60 border border-slate-800">
                          <div className="text-[11px] font-bold text-emerald-300 mb-1 flex items-center gap-1">
                            <span>🛠️</span> ট্রেডার হিসেবে আপনার কী করণীয়:
                          </div>
                          <p className="text-slate-200 leading-relaxed">
                            {activeSource.real_life_summary.actionable_guidance}
                          </p>
                        </div>

                        <div className="p-3 rounded bg-slate-950/60 border border-slate-800">
                          <div className="text-[11px] font-bold text-rose-300 mb-1 flex items-center gap-1">
                            <span>⚠️</span> প্রধান ঝুঁকি ও সতর্কতা:
                          </div>
                          <p className="text-slate-200 leading-relaxed">
                            {activeSource.real_life_summary.risk_warning}
                          </p>
                        </div>
                      </div>

                      {activeSource.real_life_summary.real_world_analogy && (
                        <div className="p-2.5 rounded bg-slate-950/80 border border-indigo-500/20 text-[11px]">
                          <span className="font-bold text-purple-300">💡 বাস্তব জীবনের অ্যানালজি: </span>
                          <span className="text-slate-300 italic">{activeSource.real_life_summary.real_world_analogy}</span>
                        </div>
                      )}
                    </div>
                  )}

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
                            <th className="py-2.5 px-3 w-28 text-right">Action</th>
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
                              <td className="py-3 px-3 align-top text-right">
                                {claim.epistemic_status === 'HYPOTHESIS' && (
                                  <button
                                    onClick={() => handleBridgeToStrategy(claim.claim_id)}
                                    disabled={isBridgingClaim === claim.claim_id}
                                    className="px-2 py-1 rounded bg-indigo-600/30 hover:bg-indigo-600/50 text-indigo-300 hover:text-white border border-indigo-500/40 text-[10px] font-mono flex items-center gap-1 transition ml-auto disabled:opacity-50"
                                    title="Bridge falsifiable thesis into Strategy Desk"
                                  >
                                    <TrendingUp size={11} />
                                    <span>{isBridgingClaim === claim.claim_id ? 'Bridging...' : 'Bridge Alpha'}</span>
                                  </button>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  {/* Section 3: Dialectical Contradictions & Filters */}
                  {(activeArticle.contradictions_detected.length > 0 || contradictions.length > 0) && (
                    <div className="bg-rose-950/20 border border-rose-500/30 p-4 rounded-lg space-y-3">
                      <div className="flex items-center justify-between pb-1 border-b border-rose-500/20">
                        <h3 className="text-xs font-bold uppercase tracking-wider text-rose-400 flex items-center gap-1.5">
                          <AlertTriangle size={14} />
                          <span>III. Dialectical Contradictions & Hype Filters ({activeArticle.contradictions_detected.length + contradictions.length})</span>
                        </h3>
                        <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-rose-500/20 text-rose-300 border border-rose-500/30">
                          Dialectical Tracking Active
                        </span>
                      </div>
                      
                      {activeArticle.contradictions_detected.length > 0 && (
                        <ul className="space-y-1.5 text-xs text-rose-200">
                          {activeArticle.contradictions_detected.map((c, i) => (
                            <li key={i} className="flex items-start gap-2 bg-rose-950/30 p-2 rounded border border-rose-500/20">
                              <span className="text-rose-400 font-bold">•</span>
                              <span className="leading-relaxed">{c}</span>
                            </li>
                          ))}
                        </ul>
                      )}

                      {contradictions.length > 0 && (
                        <div className="space-y-1.5 pt-1">
                          <span className="text-[10px] font-mono text-slate-400 uppercase tracking-wider block">
                            Cross-Article Contradiction Ledger:
                          </span>
                          {contradictions.map((ct) => (
                            <div key={ct.contradiction_id} className="p-2 rounded bg-slate-900/60 border border-rose-500/30 text-xs flex items-start justify-between gap-2">
                              <div>
                                <div className="text-[10px] text-slate-400 font-mono">
                                  {ct.claim_a_id} vs {ct.claim_b_id}
                                </div>
                                <p className="text-slate-200 mt-0.5">{ct.contradiction_nature}</p>
                              </div>
                              <span className={`text-[10px] px-2 py-0.5 rounded font-mono font-bold shrink-0 ${
                                ct.resolution_status === 'RESOLVED'
                                  ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                                  : 'bg-rose-500/20 text-rose-400 border border-rose-500/30'
                              }`}>
                                {ct.resolution_status}
                              </span>
                            </div>
                          ))}
                        </div>
                      )}
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

                  {/* Section 5: Connected Wiki Topics with Bidirectional WikiLink */}
                  <div className="bg-slate-900/40 p-4 rounded-lg border border-slate-800 space-y-2">
                    <h3 className="text-xs font-bold uppercase tracking-wider text-indigo-300 flex items-center gap-1.5">
                      <Layers size={14} />
                      <span>V. Connected Wiki Dossiers ([[WikiLinks]])</span>
                    </h3>
                    <div className="flex flex-wrap gap-2 pt-1">
                      {activeArticle.wikilinks.map((wl, i) => {
                        const cleanTerm = wl.replace(/\[\[|\]\]/g, '').split('|')[0].trim();
                        const matched = articles.find(
                          (a) =>
                            a.title.toLowerCase().includes(cleanTerm.toLowerCase()) ||
                            cleanTerm.toLowerCase().includes(a.title.toLowerCase())
                        );
                        return (
                          <span
                            key={i}
                            className="px-2.5 py-1 rounded bg-indigo-500/10 border border-indigo-500/30 text-xs font-mono flex items-center gap-1.5"
                          >
                            <Bookmark size={11} className="text-indigo-400" />
                            <WikiLink
                              term={wl}
                              articleId={matched?.article_id}
                              summary={matched?.executive_summary}
                              onNavigate={(artId) => setSelectedArticleId(artId)}
                            />
                          </span>
                        );
                      })}
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
                  </div>

                  {/* Right Column: Wikipedia Infobox */}
                  <WikiInfobox article={activeArticle} source={activeSource} />
                </div>
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
                    {activeSource && (
                      <>
                        <div className="p-3 rounded bg-slate-950 border border-slate-800">
                          <span className="text-slate-500 block mb-1">Raw Source ID:</span>
                          <span className="text-emerald-400 font-bold select-all">{activeSource.source_id}</span>
                        </div>
                        <div className="p-3 rounded bg-slate-950 border border-slate-800">
                          <span className="text-slate-500 block mb-1">Access & Extraction Status:</span>
                          <span className="text-white select-all">{activeSource.access_status} / {activeSource.extraction_status}</span>
                        </div>
                        <div className="p-3 rounded bg-slate-950 border border-slate-800 sm:col-span-2">
                          <span className="text-slate-500 block mb-1">Canonical URL & Provenance Invariant:</span>
                          <span className="text-indigo-300 select-all break-all">{activeSource.canonical_url || activeSource.original_url}</span>
                          <div className="mt-1 text-[10px] text-emerald-400">✓ Invariant: Zero Link Loss Guaranteed in research_sources</div>
                        </div>
                      </>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* 3. Human-in-the-Loop Triage Inbox Drawer (Phase 4) */}
      {showTriageDrawer && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex justify-end animate-in fade-in duration-150">
          <div className="w-full max-w-2xl bg-[#0b1220] border-l border-slate-800 h-full flex flex-col shadow-2xl">
            {/* Triage Drawer Header */}
            <div className="p-4 bg-slate-900 border-b border-slate-800 flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded bg-amber-500/20 text-amber-400 border border-amber-500/30">
                  <Inbox size={18} />
                </div>
                <div>
                  <h3 className="font-bold text-white text-sm flex items-center gap-2">
                    <span>Research Triage Inbox</span>
                    <span className="text-[10px] px-2 py-0.5 rounded font-mono font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30">
                      STAGING ({triageItems.length})
                    </span>
                  </h3>
                  <p className="text-[11px] text-slate-400">
                    Human-in-the-loop gate: Inspect extracted candidates before publishing into permanent Research Wikipedia.
                  </p>
                </div>
              </div>
              <button
                onClick={() => setShowTriageDrawer(false)}
                className="text-slate-400 hover:text-white text-xs px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 transition"
              >
                Close
              </button>
            </div>

            {/* Triage Candidates List */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {isLoadingTriage ? (
                <div className="flex flex-col items-center justify-center p-12 text-slate-500 gap-2">
                  <RefreshCw size={20} className="animate-spin text-amber-400" />
                  <span className="text-xs">Loading triage candidates...</span>
                </div>
              ) : triageItems.length === 0 ? (
                <div className="flex flex-col items-center justify-center p-12 text-slate-500 gap-2 text-center">
                  <CheckCircle2 size={32} className="text-emerald-500 mb-1" />
                  <h4 className="text-sm font-bold text-slate-300">Triage Inbox is Clear</h4>
                  <p className="text-xs text-slate-500 max-w-xs">
                    All candidates have been reviewed or merged. Run a new research cycle with <code className="text-cyan-400 font-mono">/cycle &lt;topic&gt;</code> to discover more.
                  </p>
                </div>
              ) : (
                triageItems.map((item) => (
                  <div
                    key={item.item_id}
                    className="p-4 rounded-lg bg-slate-900/80 border border-slate-800 space-y-3 hover:border-amber-500/40 transition"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <div className="flex items-center gap-2 text-[10px] font-mono text-cyan-400 mb-1">
                          <span className="uppercase font-semibold">{item.source_domain}</span>
                          <span>•</span>
                          <span className="text-slate-400">{item.proposed_category}</span>
                        </div>
                        <h4 className="font-bold text-white text-sm leading-snug">
                          {item.candidate_title}
                        </h4>
                      </div>
                      <span className="px-2 py-0.5 text-[10px] font-mono font-bold rounded bg-amber-500/10 text-amber-400 border border-amber-500/30">
                        {item.status}
                      </span>
                    </div>

                    <p className="text-xs text-slate-300 leading-relaxed bg-slate-950/60 p-2.5 rounded border border-slate-800/80">
                      {item.candidate_summary}
                    </p>

                    {item.extracted_claims && item.extracted_claims.length > 0 && (
                      <div className="space-y-1.5">
                        <span className="text-[10px] font-mono uppercase text-slate-400">
                          Extracted Claims ({item.extracted_claims.length}):
                        </span>
                        <div className="space-y-1">
                          {item.extracted_claims.slice(0, 3).map((cl: any, idx: number) => (
                            <div
                              key={idx}
                              className="text-[11px] p-1.5 rounded bg-slate-950/40 border border-slate-800/60 flex items-start gap-1.5 text-slate-300"
                            >
                              <span className="text-amber-400 font-bold">•</span>
                              <span className="line-clamp-2">{cl.claim || cl.speaker_claim}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    <div className="flex items-center justify-between pt-2 border-t border-slate-800">
                      <a
                        href={item.source_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs text-cyan-400 hover:text-cyan-300 flex items-center gap-1 font-mono"
                      >
                        <ExternalLink size={12} /> Inspect Source
                      </a>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => handleRejectTriageItem(item.item_id)}
                          disabled={isProcessingTriage === item.item_id}
                          className="px-3 py-1.5 rounded bg-rose-950/40 hover:bg-rose-900/50 text-rose-300 border border-rose-500/30 text-xs font-semibold flex items-center gap-1 transition cursor-pointer disabled:opacity-50"
                        >
                          <XCircle size={13} />
                          <span>Reject</span>
                        </button>
                        <button
                          onClick={() => handleMergeTriageItem(item.item_id)}
                          disabled={isProcessingTriage === item.item_id}
                          className="px-3 py-1.5 rounded bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white text-xs font-bold flex items-center gap-1.5 transition cursor-pointer disabled:opacity-50 shadow-md shadow-emerald-900/40"
                        >
                          <CheckCircle2 size={13} />
                          <span>{isProcessingTriage === item.item_id ? 'Merging...' : 'Approve & Merge'}</span>
                        </button>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
