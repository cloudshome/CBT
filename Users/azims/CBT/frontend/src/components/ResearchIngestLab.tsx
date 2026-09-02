import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Brain,
  UploadCloud,
  Link,
  FileText,
  Youtube,
  Github,
  Film,
  Search,
  BookOpen,
  FlaskConical,
  CheckCircle2,
  Trash2,
  Sparkles,
  Shield,
  Activity,
  Play,
  RotateCcw,
  Tag,
  Compass,
  Layers,
  GitBranch,
  TrendingUp,
} from 'lucide-react';
import { api } from '../services/api';
import {
  ResearchProvenanceItem,
  ResearchVaultsResponse,
  ResearchIngestMode,
  ResearchIngestResult,
  DiscoveryGraphResponse,
  CrossDomainDiscoveryItem,
} from '../types';

interface ResearchIngestLabProps {
  onNotify?: (type: 'success' | 'error' | 'info' | 'warning', title: string, msg: string) => void;
  selectedSymbol?: string;
  selectedTimeframe?: string;
}

export const ResearchIngestLab: React.FC<ResearchIngestLabProps> = ({
  onNotify,
  selectedSymbol = 'BTC/USDT',
  selectedTimeframe = '15m',
}) => {
  // Ingest Form State
  const [inputText, setInputText] = useState<string>('');
  const [inputTitle, setInputTitle] = useState<string>('');
  const [inputAuthor, setInputAuthor] = useState<string>('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  // Ingestion Result State
  const [lastResult, setLastResult] = useState<ResearchIngestResult | null>(null);

  // 5 Vault Tabs: KNOWLEDGE, DISCOVERY, CANDIDATES, EVIDENCE, REJECTED
  const [activeVaultTab, setActiveVaultTab] = useState<'KNOWLEDGE' | 'DISCOVERY' | 'CANDIDATES' | 'EVIDENCE' | 'REJECTED'>('DISCOVERY');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [loadingVaults, setLoadingVaults] = useState<boolean>(false);

  // Vault & Graph State
  const [vaultData, setVaultData] = useState<ResearchVaultsResponse | null>(null);
  const [inboxItems, setInboxItems] = useState<ResearchProvenanceItem[]>([]);
  const [graphData, setGraphData] = useState<DiscoveryGraphResponse | null>(null);

  // Action States
  const [backtestingCandidateId, setBacktestingCandidateId] = useState<string | null>(null);
  const [testingHypothesisId, setTestingHypothesisId] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  // Fetch Vaults, Inbox & Discovery Graph
  const fetchAllData = useCallback(async () => {
    try {
      setLoadingVaults(true);
      const [vData, inData, gData] = await Promise.all([
        api.getResearchVaults(),
        api.getResearchInbox(15),
        api.getDiscoveryGraph(),
      ]);
      setVaultData(vData);
      setInboxItems(inData.items || []);
      setGraphData(gData);
    } catch (err: any) {
      console.error('Failed to load research vault data:', err);
    } finally {
      setLoadingVaults(false);
    }
  }, []);

  useEffect(() => {
    fetchAllData();
  }, [fetchAllData]);

  // Handle Drag & Drop
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      setSelectedFile(e.dataTransfer.files[0]);
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      setSelectedFile(e.target.files[0]);
    }
  };

  // Submit Ingestion (Modes: ANALYZE, RESEARCH, SAVE_KNOWLEDGE)
  const handleIngest = async (mode: ResearchIngestMode) => {
    if (!selectedFile && !inputText.trim()) {
      if (onNotify) onNotify('warning', 'Empty Input', 'Please drag a file or paste a URL / text to ingest.');
      return;
    }

    try {
      setIsSubmitting(true);
      let res: ResearchIngestResult;

      if (selectedFile) {
        res = await api.ingestResearchFile({
          file: selectedFile,
          mode,
          author_creator: inputAuthor.trim() || undefined,
          title: inputTitle.trim() || undefined,
        });
      } else {
        res = await api.ingestResearchText({
          content: inputText.trim(),
          mode,
          source_uri: inputText.startsWith('http') ? inputText.trim() : undefined,
          author_creator: inputAuthor.trim() || undefined,
          title: inputTitle.trim() || undefined,
        });
      }

      setLastResult(res);
      setSelectedFile(null);
      setInputText('');
      setInputTitle('');
      setInputAuthor('');

      if (onNotify) {
        onNotify(
          'success',
          `Knowledge Ingested (${res.knowledge_id})`,
          res.verdict_message
        );
      }

      await fetchAllData();
    } catch (err: any) {
      console.error('Ingestion error:', err);
      if (onNotify) onNotify('error', 'Ingestion Failed', err?.message || 'Failed to parse research input.');
    } finally {
      setIsSubmitting(false);
    }
  };

  // Run Backtest Verification on Candidate
  const handleRunBacktest = async (candidateId: string) => {
    try {
      setBacktestingCandidateId(candidateId);
      const res = await api.backtestResearchCandidate(candidateId, selectedSymbol, selectedTimeframe);
      if (onNotify) {
        const isPromoted = res.validation_stage === 'WALK_FORWARD';
        onNotify(
          isPromoted ? 'success' : 'warning',
          isPromoted ? 'Candidate Promoted!' : 'Candidate Rejected',
          `Backtest result for ${candidateId}: ${res.verdict}`
        );
      }
      await fetchAllData();
    } catch (err: any) {
      if (onNotify) onNotify('error', 'Backtest Failed', err?.message || 'Backtest error');
    } finally {
      setBacktestingCandidateId(null);
    }
  };

  // Run Empirical Test on Hypothesis
  const handleRunEmpiricalTest = async (hypothesisId: string) => {
    try {
      setTestingHypothesisId(hypothesisId);
      const res = await api.runHypothesisEmpiricalTest(hypothesisId);
      if (onNotify) {
        const isSupported = res.verdict === 'SUPPORTED';
        onNotify(
          isSupported ? 'success' : 'info',
          `Hypothesis Tested (${hypothesisId})`,
          `Verdict: ${res.verdict} (p-value: ${res.p_value}, Effect: ${res.effect_size})`
        );
      }
      await fetchAllData();
    } catch (err: any) {
      if (onNotify) onNotify('error', 'Empirical Test Failed', err?.message || 'Test error');
    } finally {
      setTestingHypothesisId(null);
    }
  };

  // Create Hypothesis from Cross-Domain Discovery
  const handleCreateHypothesisFromDiscovery = async (discovery: CrossDomainDiscoveryItem) => {
    try {
      await api.createHypothesis({
        title: `Hypothesis: ${discovery.cross_domain_candidate}`,
        null_hypothesis: `H0: ${discovery.target_variable} exhibits zero statistically significant variance relative to baseline.`,
        alt_hypothesis: discovery.proposed_hypothesis,
        independent_variable: discovery.source_worldview + '_PHASE',
        dependent_variable: discovery.target_variable,
        claim_id: discovery.source_claim_id,
        target_symbol: discovery.target_symbol,
        test_method: 'VOLATILITY_EVENT_STUDY',
        control_variables: ['HALVING_CYCLE', 'FUNDING_RATE', 'DXY'],
      });

      if (onNotify) {
        onNotify('success', 'Hypothesis Formulated', `Queued formal hypothesis for ${discovery.target_symbol}`);
      }
      await fetchAllData();
    } catch (err: any) {
      if (onNotify) onNotify('error', 'Failed to Create Hypothesis', err?.message || 'Error');
    }
  };

  const getSourceIcon = (type: string) => {
    switch (type.toUpperCase()) {
      case 'YOUTUBE':
        return <Youtube className="w-4 h-4 text-red-400" />;
      case 'GITHUB':
      case 'CODE':
        return <Github className="w-4 h-4 text-purple-400" />;
      case 'REEL':
        return <Film className="w-4 h-4 text-pink-400" />;
      case 'PDF':
        return <FileText className="w-4 h-4 text-amber-400" />;
      default:
        return <BookOpen className="w-4 h-4 text-cyan-400" />;
    }
  };

  const counts = vaultData?.counts || {
    knowledge_count: 0,
    candidates_count: 0,
    evidence_count: 0,
    rejected_count: 0,
    inbox_total: 0,
  };

  const graphCounts = graphData?.counts || {
    sources_count: 0,
    claims_count: 0,
    concepts_count: 0,
    variables_count: 0,
    observations_count: 0,
    edges_count: 0,
    hypotheses_count: 0,
  };

  return (
    <div className="flex flex-col gap-5 p-4 bg-slate-950 text-slate-100 rounded-xl border border-slate-800 shadow-2xl font-mono">
      {/* Header & Constitutional Doctrine */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-3 pb-3 border-b border-slate-800">
        <div>
          <div className="flex items-center gap-2">
            <Brain className="w-6 h-6 text-indigo-400 animate-pulse" />
            <h2 className="text-xl font-bold tracking-tight text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 via-cyan-400 to-emerald-400">
              SKY KNOWLEDGE & DISCOVERY LAB
            </h2>
            <span className="px-2 py-0.5 text-xs font-semibold bg-indigo-950/80 text-indigo-300 border border-indigo-700/50 rounded-full">
              10/10 Discovery Architecture
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            <span className="text-amber-400 font-semibold">Constitutional Invariant:</span> "Source provides provenance; does not define ontology. Believe nothing without evidence $\to$ Empirically test the interesting hypotheses."
          </p>
        </div>

        {/* Global Vault Metric Counters */}
        <div className="flex items-center gap-2 flex-wrap">
          <div className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-900 border border-slate-800 rounded-lg text-xs">
            <Compass className="w-3.5 h-3.5 text-indigo-400" />
            <span className="text-slate-400">Discovery Graph:</span>
            <span className="font-bold text-indigo-300">{graphCounts.edges_count} Edges</span>
          </div>
          <div className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-900 border border-slate-800 rounded-lg text-xs">
            <BookOpen className="w-3.5 h-3.5 text-cyan-400" />
            <span className="text-slate-400">Knowledge:</span>
            <span className="font-bold text-cyan-300">{counts.knowledge_count}</span>
          </div>
          <div className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-900 border border-slate-800 rounded-lg text-xs">
            <FlaskConical className="w-3.5 h-3.5 text-purple-400" />
            <span className="text-slate-400">Hypotheses:</span>
            <span className="font-bold text-purple-300">{graphCounts.hypotheses_count}</span>
          </div>
          <div className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-900 border border-slate-800 rounded-lg text-xs">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
            <span className="text-slate-400">Evidence:</span>
            <span className="font-bold text-emerald-300">{counts.evidence_count}</span>
          </div>
          <button
            onClick={fetchAllData}
            disabled={loadingVaults}
            className="p-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg transition-colors"
            title="Refresh All Vaults & Graph"
          >
            <RotateCcw className={`w-4 h-4 ${loadingVaults ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* UNIVERSAL INGESTION DROP ZONE */}
      <div className="bg-slate-900/90 border border-indigo-900/50 rounded-xl p-4 flex flex-col gap-4 shadow-inner relative overflow-hidden">
        <div className="absolute top-0 right-0 w-64 h-64 bg-indigo-500/5 rounded-full blur-3xl pointer-events-none" />

        {/* Drag and Drop Box */}
        <div
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
          className={`border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-all ${
            isDragging
              ? 'border-indigo-400 bg-indigo-950/40 scale-[0.99]'
              : selectedFile
              ? 'border-emerald-500/80 bg-emerald-950/20'
              : 'border-slate-700 hover:border-indigo-500/60 bg-slate-950/60 hover:bg-slate-950'
          }`}
        >
          <input
            ref={fileInputRef}
            type="file"
            onChange={handleFileSelect}
            className="hidden"
            accept=".pdf,.py,.pine,.mq4,.mq5,.json,.csv,.txt,.md,image/*"
          />

          <div className="flex flex-col items-center justify-center gap-2">
            {selectedFile ? (
              <>
                <FileText className="w-10 h-10 text-emerald-400 animate-bounce" />
                <p className="text-sm font-semibold text-emerald-300">
                  Selected File: {selectedFile.name} ({(selectedFile.size / 1024).toFixed(1)} KB)
                </p>
                <p className="text-xs text-slate-400">Click or drag another file to replace</p>
              </>
            ) : (
              <>
                <UploadCloud className="w-10 h-10 text-indigo-400/80" />
                <p className="text-sm font-medium text-slate-200">
                  Drop anything here ( <span className="text-cyan-400">PDFs / Books</span> • <span className="text-purple-400">Code / PineScript</span> • <span className="text-amber-400">Notes / Articles</span> • <span className="text-pink-400">Images</span> )
                </p>
                <p className="text-xs text-slate-400">or click to browse your system</p>
              </>
            )}
          </div>
        </div>

        {/* Multi-Line Text / URL Paste Box */}
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <label className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
              <Link className="w-3.5 h-3.5 text-cyan-400" />
              OR Paste ANY URL, YouTube Lesson, Reel, GitHub Repo, PineScript, or Research Notes:
            </label>
            <span className="text-[10px] text-slate-400">
              YouTube • Instagram Reel • GitHub • Web Articles • Trading Books • Raw Transcripts
            </span>
          </div>

          <textarea
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            placeholder="Paste YouTube link, GitHub repo URL, PineScript code snippet, astrology cycle text, or trading lesson notes here..."
            rows={3}
            className="w-full bg-slate-950 border border-slate-800 rounded-lg p-3 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-indigo-500 transition-colors resize-y"
          />

          {/* Optional Meta Tags */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
            <input
              type="text"
              value={inputTitle}
              onChange={(e) => setInputTitle(e.target.value)}
              placeholder="Optional: Resource Title (e.g. Planetary Cycles and Historical Market Volatility)"
              className="bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-slate-200 placeholder-slate-600 focus:outline-none focus:border-indigo-500"
            />
            <input
              type="text"
              value={inputAuthor}
              onChange={(e) => setInputAuthor(e.target.value)}
              placeholder="Optional: Author / Creator (e.g. Ray Dalio, ICT, Quantitative Researcher)"
              className="bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-slate-200 placeholder-slate-600 focus:outline-none focus:border-indigo-500"
            />
          </div>
        </div>

        {/* The 3 Action Ingestion Buttons */}
        <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-slate-800/80">
          <div className="text-xs text-slate-400 flex items-center gap-2">
            <Shield className="w-4 h-4 text-emerald-400" />
            <span>Epistemic Separation: Source Worldview Preserved • Claims Unverified by Default</span>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            <button
              onClick={() => handleIngest('ANALYZE')}
              disabled={isSubmitting}
              className="px-3.5 py-2 bg-blue-600/20 hover:bg-blue-600/30 text-blue-300 border border-blue-500/40 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-all disabled:opacity-50"
              title="Extract claims & concepts without queueing a strategy"
            >
              <Sparkles className="w-4 h-4 text-blue-400" />
              <span>🔬 ANALYZE</span>
            </button>

            <button
              onClick={() => handleIngest('SAVE_KNOWLEDGE')}
              disabled={isSubmitting}
              className="px-3.5 py-2 bg-cyan-600/20 hover:bg-cyan-600/30 text-cyan-300 border border-cyan-500/40 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-all disabled:opacity-50"
              title="Store conceptual knowledge directly into the Knowledge Vault"
            >
              <BookOpen className="w-4 h-4 text-cyan-400" />
              <span>📚 SAVE KNOWLEDGE</span>
            </button>

            <button
              onClick={() => handleIngest('RESEARCH')}
              disabled={isSubmitting}
              className="px-4 py-2 bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white rounded-lg text-xs font-bold flex items-center gap-1.5 shadow-lg shadow-purple-900/30 transition-all disabled:opacity-50"
              title="Deconstruct into atomic atoms and trigger Cross-Domain Discovery Graph"
            >
              <Compass className="w-4 h-4" />
              <span>{isSubmitting ? 'DECOMPOSING...' : '🔭 RESEARCH & DISCOVER'}</span>
            </button>
          </div>
        </div>
      </div>

      {/* RECENT INGESTION RESULT SUMMARY */}
      {lastResult && (
        <div className="bg-slate-900 border border-emerald-900/60 rounded-xl p-4 flex flex-col gap-3 animate-fadeIn">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="w-5 h-5 text-emerald-400" />
              <span className="font-bold text-emerald-300 text-sm">
                Decomposed Successfully — Source ID: {lastResult.knowledge_id}
              </span>
              <span className="px-2 py-0.5 bg-slate-800 text-slate-300 text-[10px] rounded uppercase font-semibold">
                Mode: {lastResult.mode}
              </span>
            </div>
            <span className="text-xs text-slate-400">
              Confidence: <strong className="text-emerald-400">{lastResult.summary.comprehension_score}%</strong>
            </span>
          </div>

          <p className="text-xs text-slate-300">{lastResult.verdict_message}</p>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
            <div className="p-2 bg-slate-950 rounded border border-slate-800">
              <span className="text-slate-400">Atomic Claims:</span>
              <p className="font-bold text-cyan-400 text-base">{lastResult.summary.concepts_saved}</p>
            </div>
            <div className="p-2 bg-slate-950 rounded border border-slate-800">
              <span className="text-slate-400">Candidates Queued:</span>
              <p className="font-bold text-purple-400 text-base">{lastResult.summary.candidates_queued}</p>
            </div>
            <div className="p-2 bg-slate-950 rounded border border-slate-800">
              <span className="text-slate-400">Observations:</span>
              <p className="font-bold text-emerald-400 text-base">{lastResult.summary.evidence_saved}</p>
            </div>
            <div className="p-2 bg-slate-950 rounded border border-slate-800">
              <span className="text-slate-400">Rejected / Autopsies:</span>
              <p className="font-bold text-rose-400 text-base">{lastResult.summary.rejected_archived}</p>
            </div>
          </div>
        </div>
      )}

      {/* RESEARCH INBOX (RECENT INGESTIONS) */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Activity className="w-4 h-4 text-indigo-400" />
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300">
              📨 RESEARCH PROVENANCE INBOX
            </h3>
          </div>
          <span className="text-[10px] text-slate-400">Showing last {inboxItems.length} sources</span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
          {inboxItems.length === 0 ? (
            <div className="col-span-3 text-center py-4 text-xs text-slate-500">
              Inbox is empty. Drop files or paste URLs above to start ingesting research.
            </div>
          ) : (
            inboxItems.slice(0, 6).map((item) => (
              <div
                key={item.knowledge_id}
                className="p-2.5 bg-slate-950 rounded-lg border border-slate-800/80 flex flex-col justify-between gap-1 text-xs hover:border-slate-700 transition-colors"
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-1.5 truncate">
                    {getSourceIcon(item.source_type)}
                    <span className="font-semibold text-slate-200 truncate">{item.title}</span>
                  </div>
                  <span
                    className={`px-1.5 py-0.5 text-[10px] rounded font-bold ${
                      item.status === 'VALIDATED'
                        ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                        : item.status === 'CANDIDATE'
                        ? 'bg-purple-950 text-purple-400 border border-purple-800'
                        : item.status === 'REJECTED'
                        ? 'bg-rose-950 text-rose-400 border border-rose-800'
                        : 'bg-blue-950 text-blue-400 border border-blue-800'
                    }`}
                  >
                    {item.status}
                  </span>
                </div>
                <div className="flex items-center justify-between text-[10px] text-slate-500 mt-1">
                  <span>ID: {item.knowledge_id}</span>
                  <span>{new Date(item.ingested_at).toLocaleDateString()}</span>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* THE 5 VAULT DESTINATIONS TABS */}
      <div className="flex flex-col gap-3">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-2 border-b border-slate-800 pb-2">
          {/* Vault Navigation Tabs */}
          <div className="flex items-center gap-2 flex-wrap">
            <button
              onClick={() => setActiveVaultTab('DISCOVERY')}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold flex items-center gap-1.5 transition-all ${
                activeVaultTab === 'DISCOVERY'
                  ? 'bg-gradient-to-r from-indigo-600 to-purple-600 text-white shadow-lg shadow-indigo-950/60'
                  : 'bg-slate-900 text-slate-400 hover:text-slate-200 border border-slate-800'
              }`}
            >
              <Compass className="w-3.5 h-3.5" />
              <span>🔭 Discovery Graph ({graphCounts.hypotheses_count} Hypotheses)</span>
            </button>

            <button
              onClick={() => setActiveVaultTab('KNOWLEDGE')}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold flex items-center gap-1.5 transition-all ${
                activeVaultTab === 'KNOWLEDGE'
                  ? 'bg-cyan-950 text-cyan-300 border border-cyan-700/60 shadow-lg shadow-cyan-950/40'
                  : 'bg-slate-900 text-slate-400 hover:text-slate-200 border border-slate-800'
              }`}
            >
              <BookOpen className="w-3.5 h-3.5 text-cyan-400" />
              <span>🧠 Knowledge Vault ({counts.knowledge_count})</span>
            </button>

            <button
              onClick={() => setActiveVaultTab('CANDIDATES')}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold flex items-center gap-1.5 transition-all ${
                activeVaultTab === 'CANDIDATES'
                  ? 'bg-purple-950 text-purple-300 border border-purple-700/60 shadow-lg shadow-purple-950/40'
                  : 'bg-slate-900 text-slate-400 hover:text-slate-200 border border-slate-800'
              }`}
            >
              <FlaskConical className="w-3.5 h-3.5 text-purple-400" />
              <span>🧪 Strategy Candidates ({counts.candidates_count})</span>
            </button>

            <button
              onClick={() => setActiveVaultTab('EVIDENCE')}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold flex items-center gap-1.5 transition-all ${
                activeVaultTab === 'EVIDENCE'
                  ? 'bg-emerald-950 text-emerald-300 border border-emerald-700/60 shadow-lg shadow-emerald-950/40'
                  : 'bg-slate-900 text-slate-400 hover:text-slate-200 border border-slate-800'
              }`}
            >
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
              <span>📊 Evidence Vault ({counts.evidence_count})</span>
            </button>

            <button
              onClick={() => setActiveVaultTab('REJECTED')}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold flex items-center gap-1.5 transition-all ${
                activeVaultTab === 'REJECTED'
                  ? 'bg-rose-950 text-rose-300 border border-rose-700/60 shadow-lg shadow-rose-950/40'
                  : 'bg-slate-900 text-slate-400 hover:text-slate-200 border border-slate-800'
              }`}
            >
              <Trash2 className="w-3.5 h-3.5 text-rose-400" />
              <span>🗑️ Autopsy Vault ({counts.rejected_count})</span>
            </button>
          </div>

          {/* Search Filter Box */}
          <div className="relative w-full md:w-64">
            <Search className="w-3.5 h-3.5 absolute left-3 top-2.5 text-slate-500" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Filter nodes / claims..."
              className="w-full bg-slate-900 border border-slate-800 rounded-lg pl-8 pr-3 py-1.5 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-indigo-500"
            />
          </div>
        </div>

        {/* VAULT 5: DISCOVERY GRAPH & HYPOTHESIS TESTING LAB */}
        {activeVaultTab === 'DISCOVERY' && (
          <div className="flex flex-col gap-4 animate-fadeIn">
            {/* Cross-Domain Discovery Stream */}
            <div className="bg-slate-900/90 border border-indigo-900/60 rounded-xl p-4 flex flex-col gap-3 shadow-md">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Compass className="w-4 h-4 text-indigo-400 animate-spin" style={{ animationDuration: '10s' }} />
                  <h3 className="text-xs font-bold uppercase tracking-wider text-indigo-300">
                    🔭 CROSS-DOMAIN DISCOVERY CANDIDATES
                  </h3>
                </div>
                <span className="text-[10px] text-slate-400">
                  Detected Multi-Hop Relationships (Status: 🔵 UNTESTED)
                </span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {(graphData?.discoveries || []).map((disc) => (
                  <div
                    key={disc.discovery_id}
                    className="p-3 bg-slate-950 rounded-xl border border-indigo-900/50 flex flex-col justify-between gap-2.5 hover:border-indigo-600 transition-all shadow-sm"
                  >
                    <div className="flex flex-col gap-1.5">
                      <div className="flex items-center justify-between">
                        <span className="px-2 py-0.5 text-[10px] bg-indigo-950 text-indigo-300 border border-indigo-700/60 rounded font-bold">
                          ORIGIN: {disc.source_worldview}
                        </span>
                        <span className="px-2 py-0.5 text-[10px] bg-blue-950 text-blue-300 border border-blue-800 rounded font-bold">
                          🔵 {disc.status}
                        </span>
                      </div>

                      <h4 className="font-bold text-slate-100 text-xs flex items-center gap-1.5">
                        <GitBranch className="w-3.5 h-3.5 text-cyan-400" />
                        {disc.cross_domain_candidate}
                      </h4>

                      <p className="text-[11px] text-slate-400 leading-relaxed bg-slate-900/70 p-2 rounded border border-slate-800">
                        {disc.proposed_hypothesis}
                      </p>
                    </div>

                    <div className="flex items-center justify-between pt-2 border-t border-slate-800/80">
                      <span className="text-[10px] text-slate-500">Target Symbol: {disc.target_symbol}</span>
                      <button
                        onClick={() => handleCreateHypothesisFromDiscovery(disc)}
                        className="px-2.5 py-1 bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white rounded text-xs font-semibold flex items-center gap-1 transition-all"
                      >
                        <FlaskConical className="w-3 h-3" />
                        <span>FORMULATE HYPOTHESIS</span>
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Formal Hypothesis Queue & Empirical Testing Desk */}
            <div className="bg-slate-900/90 border border-purple-900/60 rounded-xl p-4 flex flex-col gap-3 shadow-md">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <FlaskConical className="w-4 h-4 text-purple-400" />
                  <h3 className="text-xs font-bold uppercase tracking-wider text-purple-300">
                    🧪 FORMAL HYPOTHESIS QUEUE & STATISTICAL TESTING LAB
                  </h3>
                </div>
                <span className="text-[10px] text-slate-400">
                  Evaluates H0 vs H1 on Historical Market Candles
                </span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {(graphData?.hypotheses || []).map((hypo) => (
                  <div
                    key={hypo.hypothesis_id}
                    className="p-3 bg-slate-950 rounded-xl border border-purple-900/40 flex flex-col justify-between gap-2.5 shadow-sm"
                  >
                    <div className="flex flex-col gap-1.5">
                      <div className="flex items-center justify-between">
                        <span
                          className={`px-2 py-0.5 text-[10px] rounded font-bold ${
                            hypo.validation_status === 'SUPPORTED'
                              ? 'bg-emerald-950 text-emerald-300 border border-emerald-700'
                              : hypo.validation_status === 'REJECTED'
                              ? 'bg-rose-950 text-rose-300 border border-rose-700'
                              : hypo.validation_status === 'INCONCLUSIVE'
                              ? 'bg-amber-950 text-amber-300 border border-amber-700'
                              : 'bg-purple-950 text-purple-300 border border-purple-700'
                          }`}
                        >
                          STATUS: {hypo.validation_status}
                        </span>
                        <span className="text-[10px] text-slate-500">ID: {hypo.hypothesis_id}</span>
                      </div>

                      <h4 className="font-bold text-slate-200 text-xs">{hypo.title}</h4>

                      <div className="bg-slate-900 p-2 rounded text-[11px] text-slate-300 flex flex-col gap-1 border border-slate-800">
                        <p><strong className="text-slate-400">H0 (Null):</strong> {hypo.null_hypothesis}</p>
                        <p><strong className="text-purple-300">H1 (Alt):</strong> {hypo.alt_hypothesis}</p>
                      </div>

                      {hypo.test_result_summary && (
                        <p className="text-[10px] text-emerald-300 bg-emerald-950/40 p-2 rounded border border-emerald-800/60 leading-relaxed">
                          {hypo.test_result_summary}
                        </p>
                      )}
                    </div>

                    <div className="flex items-center justify-between pt-2 border-t border-slate-800/80">
                      <span className="text-[10px] text-slate-500">Symbol: {hypo.target_symbol}</span>
                      <button
                        onClick={() => handleRunEmpiricalTest(hypo.hypothesis_id)}
                        disabled={testingHypothesisId === hypo.hypothesis_id}
                        className="px-3 py-1 bg-indigo-600/30 hover:bg-indigo-600/50 text-indigo-200 border border-indigo-500/50 rounded text-xs font-semibold flex items-center gap-1.5 transition-all disabled:opacity-50"
                      >
                        <TrendingUp className={`w-3 h-3 ${testingHypothesisId === hypo.hypothesis_id ? 'animate-spin' : ''}`} />
                        <span>{testingHypothesisId === hypo.hypothesis_id ? 'TESTING...' : 'RUN EMPIRICAL TEST'}</span>
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Atomic Claim Inspector (Preserving Verbatim Source Framing) */}
            <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-4 flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Layers className="w-4 h-4 text-cyan-400" />
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300">
                    🧩 ATOMIC CLAIMS INSPECTOR (PRESERVING SOURCE WORLDVIEW)
                  </h3>
                </div>
                <span className="text-[10px] text-slate-400">All claims are UNVERIFIED until empirically tested</span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {(graphData?.nodes?.claims || [])
                  .filter((cl) =>
                    cl.original_claim_verbatim.toLowerCase().includes(searchQuery.toLowerCase()) ||
                    cl.source_worldview.toLowerCase().includes(searchQuery.toLowerCase())
                  )
                  .map((cl) => (
                    <div
                      key={cl.claim_id}
                      className="p-3 bg-slate-950 rounded-xl border border-slate-800 flex flex-col justify-between gap-2 shadow-sm"
                    >
                      <div className="flex flex-col gap-1.5">
                        <div className="flex items-center justify-between">
                          <span className="px-2 py-0.5 text-[10px] bg-slate-800 text-slate-300 rounded font-bold uppercase">
                            {cl.source_worldview}
                          </span>
                          <span className="px-2 py-0.5 text-[10px] bg-amber-950 text-amber-300 border border-amber-800 rounded font-bold">
                            [{cl.epistemic_status}]
                          </span>
                        </div>

                        <p className="text-xs text-slate-200 italic font-sans leading-relaxed">
                          "{cl.original_claim_verbatim}"
                        </p>

                        <div className="text-[10px] text-slate-400 bg-slate-900 p-2 rounded border border-slate-800/80 flex flex-col gap-0.5">
                          <span><strong>Direction:</strong> {cl.relationship_direction}</span>
                          <span><strong>Target Domain:</strong> {cl.object_domain}</span>
                        </div>
                      </div>

                      <div className="flex items-center justify-between text-[10px] text-slate-500 pt-1 border-t border-slate-800/80">
                        <span>ID: {cl.claim_id}</span>
                        <span>Evidence Type: {cl.evidence_type}</span>
                      </div>
                    </div>
                  ))}
              </div>
            </div>
          </div>
        )}

        {/* VAULT 1: KNOWLEDGE VAULT */}
        {activeVaultTab === 'KNOWLEDGE' && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {(vaultData?.knowledge || [])
              .filter((k) =>
                k.concept_title.toLowerCase().includes(searchQuery.toLowerCase()) ||
                k.structured_explanation.toLowerCase().includes(searchQuery.toLowerCase()) ||
                k.category.toLowerCase().includes(searchQuery.toLowerCase())
              )
              .map((k) => (
                <div
                  key={k.id}
                  className="p-3 bg-slate-900/80 border border-cyan-900/40 rounded-xl flex flex-col justify-between gap-2 shadow-sm hover:border-cyan-700/60 transition-colors"
                >
                  <div className="flex flex-col gap-1">
                    <div className="flex items-center justify-between">
                      <span className="px-2 py-0.5 text-[10px] bg-cyan-950 text-cyan-300 border border-cyan-800 rounded font-bold">
                        {k.category}
                      </span>
                      <span className="text-[10px] text-slate-500">Ref: {k.knowledge_id}</span>
                    </div>
                    <h4 className="font-bold text-slate-200 text-sm mt-1">{k.concept_title}</h4>
                    <p className="text-xs text-slate-400 line-clamp-3 leading-relaxed">
                      {k.structured_explanation}
                    </p>
                  </div>

                  {k.tags && k.tags.length > 0 && (
                    <div className="flex items-center gap-1.5 flex-wrap pt-2 border-t border-slate-800/80">
                      {k.tags.map((t, idx) => (
                        <span key={idx} className="text-[10px] text-slate-400 bg-slate-950 px-1.5 py-0.5 rounded flex items-center gap-1">
                          <Tag className="w-2.5 h-2.5 text-cyan-500" />
                          {t}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
          </div>
        )}

        {/* VAULT 2: STRATEGY CANDIDATES */}
        {activeVaultTab === 'CANDIDATES' && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {(vaultData?.candidates || [])
              .filter((c) =>
                c.strategy_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
                c.hypothesis.toLowerCase().includes(searchQuery.toLowerCase())
              )
              .map((c) => (
                <div
                  key={c.candidate_id}
                  className="p-3 bg-slate-900/80 border border-purple-900/40 rounded-xl flex flex-col justify-between gap-2 shadow-sm hover:border-purple-700/60 transition-colors"
                >
                  <div className="flex flex-col gap-1.5">
                    <div className="flex items-center justify-between">
                      <span
                        className={`px-2 py-0.5 text-[10px] rounded font-bold ${
                          c.validation_stage === 'WALK_FORWARD' || c.validation_stage === 'PROMOTED'
                            ? 'bg-emerald-950 text-emerald-300 border border-emerald-700'
                            : c.validation_stage === 'REJECTED'
                            ? 'bg-rose-950 text-rose-300 border border-rose-700'
                            : 'bg-purple-950 text-purple-300 border border-purple-800'
                        }`}
                      >
                        STAGE: {c.validation_stage}
                      </span>
                      <span className="text-[10px] text-slate-500">ID: {c.candidate_id}</span>
                    </div>

                    <h4 className="font-bold text-slate-200 text-sm">{c.strategy_name}</h4>
                    <p className="text-xs text-slate-400 leading-relaxed">
                      <strong className="text-purple-300">Hypothesis:</strong> {c.hypothesis}
                    </p>

                    {c.backtest_expectancy !== null && c.backtest_expectancy !== undefined && (
                      <div className="grid grid-cols-3 gap-1.5 p-2 bg-slate-950 rounded-lg text-[10px] border border-slate-800">
                        <div>
                          <span className="text-slate-500">Expectancy:</span>
                          <p className="font-bold text-slate-200">{c.backtest_expectancy.toFixed(2)}R</p>
                        </div>
                        <div>
                          <span className="text-slate-500">Sharpe:</span>
                          <p className="font-bold text-slate-200">{c.backtest_sharpe?.toFixed(2) || 'N/A'}</p>
                        </div>
                        <div>
                          <span className="text-slate-500">Win Rate:</span>
                          <p className="font-bold text-slate-200">
                            {c.backtest_win_rate ? (c.backtest_win_rate * 100).toFixed(1) + '%' : 'N/A'}
                          </p>
                        </div>
                      </div>
                    )}
                  </div>

                  <div className="flex items-center justify-between pt-2 border-t border-slate-800/80">
                    <span className="text-[10px] text-slate-500">Timeframe: {c.timeframe}</span>
                    <button
                      onClick={() => handleRunBacktest(c.candidate_id)}
                      disabled={backtestingCandidateId === c.candidate_id}
                      className="px-2.5 py-1 bg-purple-600/30 hover:bg-purple-600/50 text-purple-200 border border-purple-500/50 rounded text-xs font-semibold flex items-center gap-1 transition-all disabled:opacity-50"
                    >
                      <Play className={`w-3 h-3 ${backtestingCandidateId === c.candidate_id ? 'animate-spin' : ''}`} />
                      <span>{backtestingCandidateId === c.candidate_id ? 'TESTING...' : 'RUN BACKTEST'}</span>
                    </button>
                  </div>
                </div>
              ))}
          </div>
        )}

        {/* VAULT 3: EVIDENCE VAULT */}
        {activeVaultTab === 'EVIDENCE' && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {(vaultData?.evidence || [])
              .filter((e) => e.claim_statement.toLowerCase().includes(searchQuery.toLowerCase()))
              .map((e) => (
                <div
                  key={e.evidence_id}
                  className="p-3 bg-slate-900/80 border border-emerald-900/40 rounded-xl flex flex-col justify-between gap-2 shadow-sm"
                >
                  <div className="flex flex-col gap-1.5">
                    <div className="flex items-center justify-between">
                      <span className="px-2 py-0.5 text-[10px] bg-emerald-950 text-emerald-300 border border-emerald-700 rounded font-bold">
                        VERDICT: {e.verdict}
                      </span>
                      <span className="text-[10px] text-slate-500">Ref: {e.knowledge_id}</span>
                    </div>

                    <h4 className="font-bold text-slate-200 text-xs leading-relaxed">
                      "{e.claim_statement}"
                    </h4>

                    <div className="flex items-center gap-3 text-[10px] text-slate-400 mt-1">
                      <span>Sample Size: <strong className="text-slate-200">{e.sample_size} occurrences</strong></span>
                      <span>p-value: <strong className="text-emerald-400">{e.statistical_p_value}</strong></span>
                    </div>
                  </div>
                </div>
              ))}
          </div>
        )}

        {/* VAULT 4: AUTOPSY / REJECTED CLAIMS VAULT */}
        {activeVaultTab === 'REJECTED' && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {(vaultData?.rejected || [])
              .filter((r) =>
                r.rejected_claim.toLowerCase().includes(searchQuery.toLowerCase()) ||
                r.rejection_autopsy.toLowerCase().includes(searchQuery.toLowerCase())
              )
              .map((r) => (
                <div
                  key={r.rejected_id}
                  className="p-3 bg-slate-900/80 border border-rose-900/40 rounded-xl flex flex-col justify-between gap-2 shadow-sm"
                >
                  <div className="flex flex-col gap-1.5">
                    <div className="flex items-center justify-between">
                      <span className="px-2 py-0.5 text-[10px] bg-rose-950 text-rose-300 border border-rose-700 rounded font-bold">
                        REJECTED: {r.failure_reason}
                      </span>
                      <span className="text-[10px] text-slate-500">Ref: {r.knowledge_id}</span>
                    </div>

                    <h4 className="font-bold text-rose-300 text-xs leading-relaxed">
                      ❌ "{r.rejected_claim}"
                    </h4>

                    <p className="text-xs text-slate-400 bg-slate-950 p-2 rounded border border-slate-800 leading-relaxed">
                      <strong className="text-slate-300">Autopsy:</strong> {r.rejection_autopsy}
                    </p>

                    {r.historical_occurrences_tested > 0 && (
                      <span className="text-[10px] text-slate-500">
                        Tested over {r.historical_occurrences_tested.toLocaleString()} historical occurrences
                      </span>
                    )}
                  </div>
                </div>
              ))}
          </div>
        )}
      </div>
    </div>
  );
};
