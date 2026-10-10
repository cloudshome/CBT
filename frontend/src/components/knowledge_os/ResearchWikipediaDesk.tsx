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
    <div className="flex flex-col h-full bg-[#f8f9fa] dark:bg-[#0e131d] text-[#202122] dark:text-[#eaecf0] rounded-lg border border-[#a2a9b1] dark:border-[#222e42] overflow-hidden shadow-2xl font-sans">
      {/* 1. Wikipedia Top Utility Header & Ingest Strip */}
      <div className="bg-[#eaecf0] dark:bg-[#141b29] border-b border-[#a2a9b1] dark:border-[#222e42] px-4 py-3">
        <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-3 mb-3">
          <div className="flex items-center gap-3">
            {/* Wikipedia Globe Icon Badge */}
            <div className="w-10 h-10 rounded border border-[#a2a9b1] dark:border-[#384252] bg-white dark:bg-[#18202e] flex items-center justify-center text-[#202122] dark:text-white shadow-xs font-serif font-black text-xl">
              W
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-xl font-serif font-normal text-[#000000] dark:text-white tracking-normal flex items-center gap-2">
                  <span>SKY Research Wikipedia</span>
                </h2>
                <span className="text-[10px] px-2 py-0.5 font-sans font-semibold rounded bg-[#eaf3ff] dark:bg-blue-950/60 text-[#3366cc] dark:text-[#6fa8dc] border border-[#a2a9b1] dark:border-[#2b3c58]">
                  The Free Quantitative Knowledge Base
                </span>
              </div>
              <p className="text-[11px] text-[#54595d] dark:text-[#9aa0a6] font-sans mt-0.5">
                From CBT, the free institutional knowledge repository. All claims cross-verified with causal firewalls.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => {
                setShowTriageDrawer(true);
                loadTriageInbox();
              }}
              className="px-3 py-1.5 rounded border border-[#f0c36d] bg-[#fef7e0] hover:bg-[#feefc3] text-[#7c4a00] dark:bg-amber-950/40 dark:text-amber-200 dark:border-amber-700/60 text-xs font-sans font-medium flex items-center gap-1.5 transition cursor-pointer shadow-xs"
              title="Review staged web intelligence candidates"
            >
              <Inbox size={13} />
              <span>Triage Inbox ({triageItems.length})</span>
            </button>
            <button
              onClick={loadArticles}
              className="px-3 py-1.5 rounded border border-[#c8ccd1] dark:border-[#384252] bg-white dark:bg-[#1e2738] hover:bg-[#f8f9fa] dark:hover:bg-[#253043] text-xs text-[#202122] dark:text-slate-200 flex items-center gap-1.5 transition font-sans shadow-xs"
              title="Refresh articles"
            >
              <RefreshCw size={13} className={isLoadingList ? 'animate-spin' : ''} />
              <span>Refresh</span>
            </button>
          </div>
        </div>

        {/* Quick-Drop URL Ingestion Input (Wikipedia Search Bar Style) */}
        <form onSubmit={handleIngest} className="flex flex-col sm:flex-row gap-2 bg-white dark:bg-[#0c111a] p-2 rounded border border-[#a2a9b1] dark:border-[#28354b] shadow-inner">
          <div className="relative flex-1">
            <Link2 size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#3366cc] dark:text-[#6fa8dc]" />
            <input
              type="text"
              value={inputUrlOrText}
              onChange={(e) => setInputUrlOrText(e.target.value)}
              placeholder="Paste any URL (YouTube, PDF, Substack, Bloomberg, X) or raw text to create or update an encyclopedia article..."
              className="w-full bg-[#f8f9fa] dark:bg-[#151c28] border border-[#c8ccd1] dark:border-[#38455c] rounded pl-9 pr-3 py-1.5 text-xs text-[#202122] dark:text-white placeholder-[#72777d] dark:placeholder-slate-500 focus:outline-none focus:border-[#3366cc] dark:focus:border-blue-400 font-sans transition"
            />
          </div>
          <div className="w-full sm:w-60">
            <input
              type="text"
              value={inputTitle}
              onChange={(e) => setInputTitle(e.target.value)}
              placeholder="Article title (optional)..."
              className="w-full bg-[#f8f9fa] dark:bg-[#151c28] border border-[#c8ccd1] dark:border-[#38455c] rounded px-3 py-1.5 text-xs text-[#202122] dark:text-white placeholder-[#72777d] dark:placeholder-slate-500 focus:outline-none focus:border-[#3366cc] font-sans transition"
            />
          </div>
          <button
            type="submit"
            disabled={isIngesting || !inputUrlOrText.trim()}
            className="px-4 py-1.5 rounded bg-[#3366cc] hover:bg-[#2a4b8d] disabled:opacity-50 text-white text-xs font-sans font-medium flex items-center justify-center gap-1.5 shadow-sm transition cursor-pointer"
          >
            {isIngesting ? (
              <>
                <RefreshCw size={13} className="animate-spin" />
                <span>Verifying...</span>
              </>
            ) : (
              <>
                <Plus size={14} />
                <span>Publish to Wikipedia</span>
              </>
            )}
          </button>
        </form>
      </div>

      {/* 2. Main Split View: Left Articles Index vs Right Article Reader */}
      <div className="flex-1 flex flex-col md:flex-row min-h-0 overflow-hidden">
        {/* Left Column: Article Browser (Wikipedia Navigation Sidebar style) */}
        <div className="w-full md:w-80 lg:w-96 border-r border-[#a2a9b1] dark:border-[#222e42] bg-[#f8f9fa] dark:bg-[#111722] flex flex-col min-h-0">
          {/* Category selector */}
          <div className="p-2.5 border-b border-[#c8ccd1] dark:border-[#222e42] flex gap-1.5 overflow-x-auto no-scrollbar bg-[#eaecf0]/50 dark:bg-[#141b28]">
            {CATEGORIES.map((cat) => (
              <button
                key={cat}
                onClick={() => setSelectedCategory(cat)}
                className={`px-2.5 py-1 rounded text-[11px] font-sans whitespace-nowrap transition ${
                  selectedCategory === cat
                    ? 'bg-[#3366cc] text-white font-semibold shadow-xs'
                    : 'bg-white dark:bg-[#1a2332] text-[#54595d] dark:text-slate-300 hover:text-[#202122] dark:hover:text-white hover:bg-[#f1f3f5] border border-[#c8ccd1] dark:border-[#2c394d]'
                }`}
              >
                {cat === 'ALL' ? 'All Portals' : cat.split(' ')[0]}
              </button>
            ))}
          </div>

          {/* Search box & Open Web Search Action */}
          <div className="p-3 border-b border-[#c8ccd1] dark:border-[#222e42] space-y-2 bg-white dark:bg-[#0f141e]">
            <div className="relative">
              <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[#72777d]" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={handleCommandBarKeyDown}
                placeholder="Search Wikipedia (or: /wiki, /cycle, /triage)..."
                className="w-full bg-[#f8f9fa] dark:bg-[#151c28] border border-[#a2a9b1] dark:border-[#2e3b50] rounded pl-8 pr-3 py-1.5 text-xs text-[#202122] dark:text-white placeholder-[#72777d] focus:outline-none focus:border-[#3366cc] transition font-sans"
              />
            </div>
            <button
              onClick={handleOpenWebSearch}
              disabled={isWebSearching}
              className="w-full py-1.5 px-2 rounded bg-[#eaf3ff] dark:bg-[#15233c] hover:bg-[#d5e7ff] dark:hover:bg-[#1d3154] border border-[#a2a9b1] dark:border-[#2d436b] text-[#3366cc] dark:text-[#7bb3ef] hover:text-[#0b0080] text-[11px] font-sans font-semibold flex items-center justify-center gap-1.5 transition cursor-pointer shadow-xs"
            >
              <Compass size={13} className={isWebSearching ? 'animate-spin text-[#3366cc]' : 'text-[#3366cc] dark:text-[#7bb3ef]'} />
              <span>{isWebSearching ? 'Agent Searching Web...' : 'Open Web Search Agent'}</span>
            </button>
          </div>

          {/* Articles list */}
          <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
            {isLoadingList ? (
              <div className="p-8 text-center text-xs text-[#54595d] dark:text-slate-400 flex flex-col items-center gap-2">
                <RefreshCw size={18} className="animate-spin text-[#3366cc]" />
                <span>Loading Wikipedia index...</span>
              </div>
            ) : articles.length === 0 ? (
              <div className="p-8 text-center text-xs text-[#54595d] dark:text-slate-400">
                <BookOpen size={24} className="mx-auto mb-2 text-[#72777d]" />
                <p>No encyclopedia articles found.</p>
                <p className="text-[11px] text-[#72777d] mt-1">Paste a link above to publish the first article!</p>
              </div>
            ) : (
              articles.map((item) => {
                const isSelected = item.article_id === selectedArticleId;
                return (
                  <div
                    key={item.article_id}
                    onClick={() => setSelectedArticleId(item.article_id)}
                    className={`p-2.5 rounded border cursor-pointer transition flex flex-col gap-1 ${
                      isSelected
                        ? 'bg-white dark:bg-[#192334] border-[#3366cc] dark:border-blue-500 shadow-sm ring-1 ring-[#3366cc]/30'
                        : 'bg-white/80 dark:bg-[#131a26] border-[#c8ccd1] dark:border-[#243044] hover:bg-white dark:hover:bg-[#18202d] hover:border-[#a2a9b1]'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-1.5">
                        {getSourceIcon(item.source_type)}
                        <span className="text-[10px] font-mono text-[#54595d] dark:text-slate-400 uppercase tracking-wider">
                          {item.source_type.replace('_', ' ')}
                        </span>
                      </div>
                      <span className="px-1.5 py-0.2 text-[10px] font-mono font-bold rounded bg-[#e6f4ea] text-[#137333] border border-[#ceead6] dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-700/40">
                        {item.verification_score.toFixed(0)}% Rigor
                      </span>
                    </div>

                    <h4 className={`text-xs font-serif font-bold line-clamp-2 leading-tight ${isSelected ? 'text-[#0b0080] dark:text-blue-300' : 'text-[#202122] dark:text-slate-100'}`}>
                      {item.title}
                    </h4>

                    <p className="text-[11px] text-[#54595d] dark:text-slate-400 line-clamp-2 leading-normal font-sans">
                      {item.executive_summary}
                    </p>

                    <div className="flex items-center justify-between text-[10px] text-[#72777d] dark:text-slate-500 pt-1 border-t border-[#eaecf0] dark:border-[#222e40] font-mono">
                      <span>{item.provenance_id}</span>
                      <span>{item.claims_count} claims</span>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Right Column: Wikipedia Article Reader */}
        <div className="flex-1 bg-white dark:bg-[#0c1018] text-[#202122] dark:text-[#eaecf0] flex flex-col min-h-0 overflow-y-auto">
          {isLoadingArticle ? (
            <div className="flex-1 flex flex-col items-center justify-center p-12 text-[#54595d] dark:text-slate-400 gap-3">
              <RefreshCw size={24} className="animate-spin text-[#3366cc]" />
              <span className="text-xs font-sans">Fetching encyclopedia article...</span>
            </div>
          ) : !activeArticle ? (
            <div className="flex-1 flex flex-col items-center justify-center p-12 text-[#54595d] dark:text-slate-400 gap-2">
              <BookOpen size={36} className="text-[#a2a9b1] mb-1" />
              <h3 className="text-base font-serif font-bold text-[#202122] dark:text-white">Welcome to SKY Research Wikipedia</h3>
              <p className="text-xs text-[#54595d] dark:text-slate-400 max-w-sm text-center font-sans">
                Select an article from the left directory or enter a URL above to explore verified claims, macro regimes, and dialectical contradictions.
              </p>
            </div>
          ) : (
            <div className="p-6 max-w-5xl mx-auto w-full space-y-5 font-sans">
              {/* Wikipedia Tab Navigation Bar (Article / Talk / Read / Edit / View history) */}
              <div className="flex flex-wrap items-center justify-between gap-3 pb-2 border-b border-[#a2a9b1] dark:border-[#2d3a4e]">
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => setActiveTab('ARTICLE')}
                    className={`px-3 py-1.5 border-b-2 text-xs font-sans font-medium transition ${
                      activeTab === 'ARTICLE'
                        ? 'border-[#3366cc] text-[#0b0080] dark:text-blue-300 font-bold'
                        : 'border-transparent text-[#54595d] dark:text-slate-400 hover:text-[#202122] dark:hover:text-white'
                    }`}
                  >
                    Article
                  </button>
                  <button
                    onClick={() => setActiveTab('MARKDOWN')}
                    className={`px-3 py-1.5 border-b-2 text-xs font-sans font-medium transition ${
                      activeTab === 'MARKDOWN'
                        ? 'border-[#3366cc] text-[#0b0080] dark:text-blue-300 font-bold'
                        : 'border-transparent text-[#54595d] dark:text-slate-400 hover:text-[#202122] dark:hover:text-white'
                    }`}
                  >
                    Raw Source / Wikitext
                  </button>
                  <button
                    onClick={() => setActiveTab('PROVENANCE')}
                    className={`px-3 py-1.5 border-b-2 text-xs font-sans font-medium transition ${
                      activeTab === 'PROVENANCE'
                        ? 'border-[#3366cc] text-[#0b0080] dark:text-blue-300 font-bold'
                        : 'border-transparent text-[#54595d] dark:text-slate-400 hover:text-[#202122] dark:hover:text-white'
                    }`}
                  >
                    View History & Provenance
                  </button>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={handleReverify}
                    className="px-2.5 py-1 rounded bg-[#f8f9fa] dark:bg-[#182130] hover:bg-[#eaecf0] dark:hover:bg-[#202b3d] text-[#202122] dark:text-slate-300 text-xs border border-[#c8ccd1] dark:border-[#38455c] flex items-center gap-1.5 transition shadow-xs"
                    title="Re-run fact checking audit against latest datasets"
                  >
                    <RefreshCw size={12} />
                    <span>Re-verify</span>
                  </button>

                  <button
                    onClick={handleCopyMarkdown}
                    className="px-2.5 py-1 rounded bg-[#f8f9fa] dark:bg-[#182130] hover:bg-[#eaecf0] dark:hover:bg-[#202b3d] text-[#202122] dark:text-slate-300 text-xs border border-[#c8ccd1] dark:border-[#38455c] flex items-center gap-1.5 transition shadow-xs"
                    title="Export article wikitext"
                  >
                    {isCopied ? <Check size={12} className="text-[#137333]" /> : <Copy size={12} />}
                    <span>{isCopied ? 'Copied' : 'Download Wikitext'}</span>
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
                <div className="flex flex-col-reverse lg:flex-row gap-6 items-start font-sans">
                  {/* Left Column: Encyclopedic Content & Claims */}
                  <div className="flex-1 w-full space-y-5">
                    {/* Wikipedia Main Article Header */}
                    <div className="border-b border-[#a2a9b1] dark:border-[#2d3a4e] pb-2">
                      <div className="flex flex-wrap items-center gap-2 mb-1 text-[11px] font-sans">
                        <span className="font-mono text-[#54595d] dark:text-[#9aa0a6]">
                          Article provenance: <strong className="text-[#3366cc] dark:text-[#6fa8dc]">{activeArticle.provenance_id}</strong>
                        </span>
                        <span>•</span>
                        <span className="text-[#54595d] dark:text-[#9aa0a6]">
                          Portal: <strong>{activeArticle.category}</strong>
                        </span>
                        <span>•</span>
                        <span className="text-[#54595d] dark:text-[#9aa0a6]">
                          Last edited: {new Date(activeArticle.updated_at).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })}
                        </span>
                      </div>

                      <h1 className="text-3xl font-serif font-normal text-[#000000] dark:text-white tracking-normal leading-tight">
                        {activeArticle.title}
                      </h1>

                      <div className="text-xs text-[#54595d] dark:text-[#9aa0a6] mt-1 italic font-serif">
                        From CBT Research Wikipedia, the free institutional quantitative encyclopedia
                      </div>
                    </div>

                    {/* Wikipedia Lead / Epistemic Notice Hatnote */}
                    <div className="p-3 rounded border border-[#c8ccd1] dark:border-[#2c3a50] bg-[#f8f9fa] dark:bg-[#131b26] flex flex-wrap items-center justify-between gap-3 text-xs">
                      <div className="flex items-center gap-2.5">
                        <div className="p-1.5 rounded bg-[#e6f4ea] dark:bg-emerald-950/40 text-[#137333] dark:text-emerald-300 border border-[#ceead6] dark:border-emerald-700/40">
                          <ShieldCheck size={16} />
                        </div>
                        <div>
                          <div className="font-semibold text-[#202122] dark:text-white flex items-center gap-2">
                            <span>Epistemic Reliability Index: {activeArticle.verification_score.toFixed(1)}%</span>
                            {activeSource && (
                              <span className={`text-[10px] px-2 py-0.2 rounded font-mono font-bold ${
                                activeSource.access_status === 'SUCCESS'
                                  ? 'bg-[#e6f4ea] text-[#137333] border border-[#ceead6] dark:bg-emerald-950/40 dark:text-emerald-300'
                                  : 'bg-[#fef7e0] text-[#b06000] border border-[#feefc3]'
                              }`}>
                                {activeSource.access_status === 'SUCCESS' ? 'Verified Extraction' : 'Partial Archive'}
                              </span>
                            )}
                          </div>
                          <div className="text-[11px] text-[#54595d] dark:text-slate-400 mt-0.5">
                            Causal firewall active: {activeArticle.key_claims.filter(c => c.epistemic_status === 'FACT').length} empirical facts,{' '}
                            {activeArticle.key_claims.filter(c => c.epistemic_status === 'HYPOTHESIS').length} falsifiable hypotheses,{' '}
                            {activeArticle.contradictions_detected.length} contradictions logged.
                          </div>
                        </div>
                      </div>

                      <div className="text-[10px] text-[#54595d] dark:text-slate-400 font-mono">
                        Invariant: Zero Link Loss
                      </div>
                    </div>

                    {/* Section 1: Abstract & Lead Paragraph */}
                    <section className="space-y-2">
                      <h2 className="text-lg font-serif font-bold text-[#000000] dark:text-white border-b border-[#a2a9b1] dark:border-[#2d3a4e] pb-1 flex items-center gap-2">
                        <span>1. Abstract &amp; Background</span>
                      </h2>
                      <p className="text-xs text-[#202122] dark:text-[#eaecf0] leading-relaxed font-sans text-justify">
                        {activeArticle.executive_summary}
                      </p>
                    </section>

                    {/* Bengali Practical Guide Notice Box (Wikipedia Callout style) */}
                    {activeSource?.real_life_summary && (
                      <div className="border border-[#a2a9b1] dark:border-[#2f3e54] bg-[#f8f9fa] dark:bg-[#121924] p-3.5 space-y-2.5">
                        <div className="flex items-center justify-between pb-1.5 border-b border-[#c8ccd1] dark:border-[#243044]">
                          <h3 className="text-xs font-serif font-bold text-[#0b0080] dark:text-blue-300 flex items-center gap-1.5">
                            <Sparkles size={14} className="text-[#b06000] dark:text-amber-400" />
                            <span>ব্যবহারিক প্রয়োগ নির্দেশিকা (Bengali 5-Point Practical Guide)</span>
                          </h3>
                          <span className="text-[10px] text-[#54595d] dark:text-slate-400 font-mono">
                            Human Intelligence Bridge
                          </span>
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5 text-xs">
                          <div className="p-2.5 bg-white dark:bg-[#18212e] border border-[#eaecf0] dark:border-[#253246]">
                            <div className="text-[11px] font-bold text-[#b06000] dark:text-amber-300 mb-0.5">
                              🎯 সহজ ভাষায় মূল কথা:
                            </div>
                            <p className="text-[#202122] dark:text-[#eaecf0] leading-relaxed text-[11px]">
                              {activeSource.real_life_summary.core_concept_bn}
                            </p>
                          </div>

                          <div className="p-2.5 bg-white dark:bg-[#18212e] border border-[#eaecf0] dark:border-[#253246]">
                            <div className="text-[11px] font-bold text-[#137333] dark:text-emerald-300 mb-0.5">
                              📈 মার্কেট প্রভাব:
                            </div>
                            <p className="text-[#202122] dark:text-[#eaecf0] leading-relaxed text-[11px]">
                              {activeSource.real_life_summary.practical_market_impact}
                            </p>
                          </div>

                          <div className="p-2.5 bg-white dark:bg-[#18212e] border border-[#eaecf0] dark:border-[#253246]">
                            <div className="text-[11px] font-bold text-[#3366cc] dark:text-blue-300 mb-0.5">
                              🛠️ ট্রেডার হিসেবে করণীয়:
                            </div>
                            <p className="text-[#202122] dark:text-[#eaecf0] leading-relaxed text-[11px]">
                              {activeSource.real_life_summary.actionable_guidance}
                            </p>
                          </div>

                          <div className="p-2.5 bg-white dark:bg-[#18212e] border border-[#eaecf0] dark:border-[#253246]">
                            <div className="text-[11px] font-bold text-[#b3261e] dark:text-rose-300 mb-0.5">
                              ⚠️ প্রধান ঝুঁকি ও সতর্কতা:
                            </div>
                            <p className="text-[#202122] dark:text-[#eaecf0] leading-relaxed text-[11px]">
                              {activeSource.real_life_summary.risk_warning}
                            </p>
                          </div>
                        </div>

                        {activeSource.real_life_summary.real_world_analogy && (
                          <div className="p-2 bg-white dark:bg-[#18212e] border border-[#eaecf0] dark:border-[#253246] text-[11px]">
                            <span className="font-bold text-[#54595d] dark:text-slate-300">বাস্তব অ্যানালজি: </span>
                            <span className="italic text-[#202122] dark:text-slate-200">{activeSource.real_life_summary.real_world_analogy}</span>
                          </div>
                        )}
                      </div>
                    )}

                    {/* Section 2: Epistemic Claim Verification Matrix */}
                    <section className="space-y-2">
                      <h2 className="text-lg font-serif font-bold text-[#000000] dark:text-white border-b border-[#a2a9b1] dark:border-[#2d3a4e] pb-1 flex items-center justify-between">
                        <span>2. Epistemic Claim Verification Matrix</span>
                        <span className="text-xs font-sans font-normal text-[#54595d] dark:text-slate-400">
                          Section 2.0
                        </span>
                      </h2>

                      <div className="border border-[#a2a9b1] dark:border-[#2d3a4e] overflow-x-auto">
                        <table className="w-full text-left text-xs border-collapse">
                          <thead className="bg-[#eaecf0] dark:bg-[#17212f] text-[#202122] dark:text-slate-200 border-b border-[#a2a9b1] dark:border-[#2d3a4e]">
                            <tr>
                              <th className="py-2 px-3 w-16 border-r border-[#c8ccd1] dark:border-[#2a374a] font-semibold">ID</th>
                              <th className="py-2 px-3 border-r border-[#c8ccd1] dark:border-[#2a374a] font-semibold">Source Assertion</th>
                              <th className="py-2 px-3 w-28 border-r border-[#c8ccd1] dark:border-[#2a374a] font-semibold">Taxonomy</th>
                              <th className="py-2 px-3 border-r border-[#c8ccd1] dark:border-[#2a374a] font-semibold">Empirical Finding</th>
                              <th className="py-2 px-3 w-24 text-right font-semibold">Action</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-[#eaecf0] dark:divide-[#202a3a] bg-white dark:bg-[#0f141e]">
                            {activeArticle.key_claims.map((claim) => (
                              <tr key={claim.claim_id} className="hover:bg-[#f8f9fa] dark:hover:bg-[#161f2c] transition">
                                <td className="py-2.5 px-3 font-mono text-[11px] text-[#54595d] dark:text-slate-400 border-r border-[#eaecf0] dark:border-[#202a3a] align-top">
                                  {claim.claim_id}
                                </td>
                                <td className="py-2.5 px-3 text-[#202122] dark:text-[#eaecf0] border-r border-[#eaecf0] dark:border-[#202a3a] align-top font-serif leading-relaxed">
                                  "{claim.speaker_claim}"
                                </td>
                                <td className="py-2.5 px-3 border-r border-[#eaecf0] dark:border-[#202a3a] align-top">
                                  {getStatusBadge(claim.epistemic_status)}
                                </td>
                                <td className="py-2.5 px-3 text-[#333] dark:text-slate-300 border-r border-[#eaecf0] dark:border-[#202a3a] align-top leading-relaxed text-[11px]">
                                  <p>{claim.cross_verification_evidence}</p>
                                  {claim.empirical_dataset_reference && (
                                    <span className="block mt-1 text-[10px] text-[#54595d] dark:text-slate-400 font-mono">
                                      Ref: {claim.empirical_dataset_reference}
                                    </span>
                                  )}
                                </td>
                                <td className="py-2.5 px-3 align-top text-right">
                                  {claim.epistemic_status === 'HYPOTHESIS' && (
                                    <button
                                      onClick={() => handleBridgeToStrategy(claim.claim_id)}
                                      disabled={isBridgingClaim === claim.claim_id}
                                      className="px-2 py-1 rounded bg-[#eaf3ff] dark:bg-blue-950/60 hover:bg-[#d5e7ff] text-[#3366cc] dark:text-blue-300 border border-[#a2a9b1] dark:border-blue-700/50 text-[10px] font-sans font-medium flex items-center gap-1 transition ml-auto disabled:opacity-50"
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
                    </section>

                    {/* Section 3: Dialectical Contradictions & Filters */}
                    {(activeArticle.contradictions_detected.length > 0 || contradictions.length > 0) && (
                      <section className="space-y-2">
                        <h2 className="text-lg font-serif font-bold text-[#b3261e] dark:text-rose-400 border-b border-[#a2a9b1] dark:border-[#2d3a4e] pb-1 flex items-center justify-between">
                          <span className="flex items-center gap-1.5">
                            <AlertTriangle size={16} />
                            <span>3. Dialectical Contradictions &amp; Dispute Ledger</span>
                          </span>
                          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-[#fce8e6] text-[#b3261e] border border-[#fad2cf] dark:bg-rose-950/40 dark:text-rose-300">
                            Active Dialectic
                          </span>
                        </h2>
                        
                        {activeArticle.contradictions_detected.length > 0 && (
                          <ul className="space-y-1.5 text-xs text-[#202122] dark:text-rose-200">
                            {activeArticle.contradictions_detected.map((c, i) => (
                              <li key={i} className="flex items-start gap-2 bg-[#fdf2f2] dark:bg-rose-950/30 p-2.5 border border-[#fad2cf] dark:border-rose-900/50">
                                <span className="text-[#b3261e] dark:text-rose-400 font-bold">•</span>
                                <span className="leading-relaxed">{c}</span>
                              </li>
                            ))}
                          </ul>
                        )}

                        {contradictions.length > 0 && (
                          <div className="space-y-1.5 pt-1">
                            <span className="text-[10px] font-mono text-[#54595d] dark:text-slate-400 uppercase tracking-wider block">
                              Cross-Article Discrepancies:
                            </span>
                            {contradictions.map((ct) => (
                              <div key={ct.contradiction_id} className="p-2 bg-white dark:bg-[#151c27] border border-[#c8ccd1] dark:border-[#2a3648] text-xs flex items-start justify-between gap-2">
                                <div>
                                  <div className="text-[10px] text-[#54595d] dark:text-slate-400 font-mono">
                                    {ct.claim_a_id} vs {ct.claim_b_id}
                                  </div>
                                  <p className="text-[#202122] dark:text-slate-200 mt-0.5">{ct.contradiction_nature}</p>
                                </div>
                                <span className="text-[10px] px-2 py-0.5 rounded font-mono font-bold shrink-0 bg-[#e6f4ea] text-[#137333] border border-[#ceead6] dark:bg-emerald-950/40 dark:text-emerald-300">
                                  {ct.resolution_status}
                                </span>
                              </div>
                            ))}
                          </div>
                        )}
                      </section>
                    )}

                    {/* Section 4: Macro Regime & Capital Allocation Implications */}
                    <section className="space-y-2">
                      <h2 className="text-lg font-serif font-bold text-[#000000] dark:text-white border-b border-[#a2a9b1] dark:border-[#2d3a4e] pb-1 flex items-center gap-2">
                        <span>4. Macro Regime &amp; Market Implications</span>
                      </h2>
                      <p className="text-xs text-[#202122] dark:text-[#eaecf0] leading-relaxed whitespace-pre-line font-sans">
                        {activeArticle.macro_regime_implications}
                      </p>
                    </section>

                    {/* Section 5: See also / Connected Wiki Topics */}
                    <section className="space-y-2">
                      <h2 className="text-lg font-serif font-bold text-[#000000] dark:text-white border-b border-[#a2a9b1] dark:border-[#2d3a4e] pb-1 flex items-center gap-2">
                        <span>5. See also ([[WikiLinks]])</span>
                      </h2>
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
                              className="px-2.5 py-1 rounded bg-[#eaecf0] dark:bg-[#1a2332] border border-[#c8ccd1] dark:border-[#2a3648] text-xs font-sans flex items-center gap-1.5"
                            >
                              <Bookmark size={11} className="text-[#3366cc] dark:text-[#6fa8dc]" />
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
                    </section>

                    {/* Wikipedia Category & Portal Footer Bar */}
                    <div className="p-2.5 border border-[#a2a9b1] dark:border-[#2c3a50] bg-[#f8f9fa] dark:bg-[#131b26] text-[11px] font-sans flex flex-wrap items-center gap-2">
                      <span className="font-bold text-[#54595d] dark:text-slate-400">Categories:</span>
                      <span className="text-[#3366cc] dark:text-[#6fa8dc] hover:underline cursor-pointer">{activeArticle.category}</span>
                      <span>•</span>
                      {activeArticle.tags.map((tag, i) => (
                        <span key={i} className="text-[#3366cc] dark:text-[#6fa8dc] hover:underline cursor-pointer">
                          {tag}
                        </span>
                      ))}
                    </div>
                  </div>

                  {/* Right Column: Authentic Wikipedia Infobox */}
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
