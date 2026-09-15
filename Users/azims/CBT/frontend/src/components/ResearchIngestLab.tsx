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
  Clock,
  ExternalLink,
  ShieldAlert,
  X,
  Send,
  GraduationCap,
  Map,
  Award,
  ShieldCheck,
  Cpu,
  ArrowRight,
  Zap,
  Target,
  DollarSign,
  Radio,
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
import {
  ProjectBrainDesk,
  HumanBrainTeacher,
  KnowledgeMapAndGaps,
  LearningPathDesk,
  KnowledgeAuditDesk,
} from './knowledge_os';

export type KosNavigationTab =
  | 'RESEARCH_LAB'
  | 'PROJECT_BRAIN'
  | 'HUMAN_BRAIN'
  | 'KNOWLEDGE_MAP'
  | 'LEARNING_PATH'
  | 'KNOWLEDGE_AUDIT';

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
  // Knowledge Operating System Active Workspace Tab
  const [activeKosTab, setActiveKosTab] = useState<KosNavigationTab>('RESEARCH_LAB');

  // Ingest Form State
  const [inputText, setInputText] = useState<string>('');
  const [inputTitle, setInputTitle] = useState<string>('');
  const [inputAuthor, setInputAuthor] = useState<string>('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [selectedMode, setSelectedMode] = useState<ResearchIngestMode>('AUTO');

  // Dedicated Ingestion Summary State
  const [activeSummary, setActiveSummary] = useState<ResearchIngestResult | null>(null);
  const [sendingTelegram, setSendingTelegram] = useState<boolean>(false);

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

  // YouTube Channel & Playlist Explorer State (V5)
  const [ytExploreInput, setYtExploreInput] = useState<string>('');
  const [ytExploreLimit, setYtExploreLimit] = useState<number>(10);
  const [ytExploreLoading, setYtExploreLoading] = useState<boolean>(false);
  const [ytActiveJobId, setYtActiveJobId] = useState<string | null>(null);
  const [ytJobData, setYtJobData] = useState<any | null>(null);
  const [recentYtJobs, setRecentYtJobs] = useState<any[]>([]);
  const [showYtResults, setShowYtResults] = useState<boolean>(false);

  const fileInputRef = useRef<HTMLInputElement>(null);

  // Fetch Vaults, Inbox & Discovery Graph
  const fetchAllData = useCallback(async () => {
    try {
      setLoadingVaults(true);
      const [vData, inData, gData, ytJobs] = await Promise.all([
        api.getResearchVaults(),
        api.getResearchInbox(15),
        api.getDiscoveryGraph(),
        api.listYouTubeJobs(10).catch(() => ({ jobs: [] })),
      ]);
      setVaultData(vData);
      setInboxItems(inData.items || []);
      setGraphData(gData);
      setRecentYtJobs(ytJobs.jobs || []);
    } catch (err: any) {
      console.error('Failed to load research vault data:', err);
    } finally {
      setLoadingVaults(false);
    }
  }, []);

  useEffect(() => {
    fetchAllData();
  }, [fetchAllData]);

  // Restore latest active YouTube job on mount
  useEffect(() => {
    const saved = localStorage.getItem('cbt_active_yt_job') || 'YT-EXP-0086081D';
    if (saved && !ytActiveJobId) {
      setYtActiveJobId(saved);
      api.getYouTubeJob(saved).then((job) => {
        setYtJobData(job);
        if (job.status === 'COMPLETED') {
          setShowYtResults(true);
        }
      }).catch(() => {});
    }
  }, []);

  // YouTube Exploration Job Polling
  useEffect(() => {
    if (!ytActiveJobId) return;
    const interval = setInterval(async () => {
      try {
        const job = await api.getYouTubeJob(ytActiveJobId);
        setYtJobData(job);
        if (job.status === 'COMPLETED' || job.status === 'FAILED') {
          clearInterval(interval);
          setYtExploreLoading(false);
          if (job.status === 'COMPLETED') {
            setShowYtResults(true);
            fetchAllData();
            if (onNotify) {
              onNotify('success', 'YouTube Synthesis Complete', `Processed ${job.result?.videos_processed || 0} videos.`);
            }
          } else if (job.status === 'FAILED' && onNotify) {
            onNotify('error', 'YouTube Exploration Failed', job.error_message || 'Task terminated unexpectedly.');
          }
        }
      } catch (err) {
        console.error('Failed to poll YouTube job:', err);
      }
    }, 2000);
    return () => clearInterval(interval);
  }, [ytActiveJobId, fetchAllData, onNotify]);

  const handleStartYouTubeExplore = async () => {
    const clean = ytExploreInput.trim();
    if (!clean) return;
    try {
      setYtExploreLoading(true);
      setYtJobData(null);
      setShowYtResults(false);
      const res = await api.exploreYouTube({
        source_url_or_handle: clean,
        limit: ytExploreLimit,
      });
      setYtActiveJobId(res.job_id);
      localStorage.setItem('cbt_active_yt_job', res.job_id);
      fetchAllData();
      if (onNotify) {
        onNotify('info', 'Exploration Dispatched', `Job ${res.job_id} launched for ${clean}`);
      }
    } catch (err: any) {
      setYtExploreLoading(false);
      if (onNotify) {
        onNotify('error', 'Exploration Failed', err?.message || 'Could not dispatch exploration job.');
      }
    }
  };

  const handleSelectPastJob = async (jobId: string) => {
    try {
      setYtActiveJobId(jobId);
      localStorage.setItem('cbt_active_yt_job', jobId);
      const job = await api.getYouTubeJob(jobId);
      setYtJobData(job);
      if (job.status === 'COMPLETED') {
        setShowYtResults(true);
      }
    } catch (err: any) {
      console.error('Failed to load past YouTube job:', err);
    }
  };

  // Handle Drag & Drop
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const MAX_FILE_SIZE_MB = 150;
  const MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024;

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const file = e.dataTransfer.files[0];
      if (file.size > MAX_FILE_SIZE_BYTES) {
        const sizeMb = (file.size / (1024 * 1024)).toFixed(1);
        if (onNotify) {
          onNotify('error', 'File Too Large', `File is ${sizeMb} MB. Maximum allowed upload size is ${MAX_FILE_SIZE_MB} MB.`);
        }
        return;
      }
      setSelectedFile(file);
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const file = e.target.files[0];
      if (file.size > MAX_FILE_SIZE_BYTES) {
        const sizeMb = (file.size / (1024 * 1024)).toFixed(1);
        if (onNotify) {
          onNotify('error', 'File Too Large', `File is ${sizeMb} MB. Maximum allowed upload size is ${MAX_FILE_SIZE_MB} MB.`);
        }
        e.target.value = '';
        return;
      }
      setSelectedFile(file);
    }
  };

  // Real-time Content & Intent Auto-Detection
  const autoDetectContent = useCallback(() => {
    if (selectedFile) {
      const ext = selectedFile.name.split('.').pop()?.toLowerCase() || '';
      if (['pdf'].includes(ext)) {
        return {
          type: 'PDF Quantitative Monograph / Book',
          badgeColor: 'bg-red-500/20 text-red-400 border-red-500/40',
          icon: BookOpen,
          hasRules: false,
          recommendedAction: 'Extract chapters, structural claims & normalize into Knowledge Vault',
          destination: 'Knowledge Vault + Cross-Domain Graph',
        };
      }
      if (['py', 'pine', 'mq4', 'mq5', 'cpp', 'ts', 'js'].includes(ext)) {
        return {
          type: 'Algorithmic Strategy Source Code',
          badgeColor: 'bg-purple-500/20 text-purple-400 border-purple-500/40',
          icon: Tag,
          hasRules: true,
          recommendedAction: 'Extract programmatic logic & queue candidate for backtesting',
          destination: 'Candidate Strategy Queue (UNTESTED)',
        };
      }
      if (['csv', 'json', 'parquet'].includes(ext)) {
        return {
          type: 'Structured Quantitative Dataset',
          badgeColor: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/40',
          icon: Layers,
          hasRules: false,
          recommendedAction: 'Parse schema, record statistical observations & link variables',
          destination: 'Observation Vault + Market Variables',
        };
      }
      if (['png', 'jpg', 'jpeg', 'webp'].includes(ext)) {
        return {
          type: 'Market Chart / Technical Diagram',
          badgeColor: 'bg-pink-500/20 text-pink-400 border-pink-500/40',
          icon: FileText,
          hasRules: false,
          recommendedAction: 'Analyze market structure, price action & liquidity sweeps',
          destination: 'Visual Market Graph',
        };
      }
      if (['mp4', 'mov', 'webm', 'mp3', 'm4a', 'wav'].includes(ext)) {
        return {
          type: 'Macro Talk Show / Economic Video Reel',
          badgeColor: 'bg-rose-500/20 text-rose-300 border-rose-500/40',
          icon: Film,
          hasRules: false,
          recommendedAction: 'Cognitive Audio/Video Dissection: Extract Regimes, Causal Chains & Confluent Trade Plans',
          destination: 'Macro Cognitive Engine + Dynamic Trade Plans',
        };
      }
      return {
        type: 'Research Document / Paper',
        badgeColor: 'bg-blue-500/20 text-blue-400 border-blue-500/40',
        icon: FileText,
        hasRules: false,
        recommendedAction: 'Decompose into atomic claims & mental models',
        destination: 'Knowledge Vault',
      };
    }

    if (inputText.trim()) {
      const raw = inputText.trim();
      const lower = raw.toLowerCase();
      const isUrl = lower.startsWith('http://') || lower.startsWith('https://');

      if (lower.includes('youtube.com') || lower.includes('youtu.be')) {
        return {
          type: 'YouTube Video Lecture / Masterclass',
          badgeColor: 'bg-red-500/20 text-red-400 border-red-500/40',
          icon: Youtube,
          hasRules: lower.includes('rule') || lower.includes('strategy') || lower.includes('fvg') || lower.includes('order block'),
          recommendedAction: 'Extract verbatim transcript, detect bias & decompose claims',
          destination: 'YouTube Intel Engine + Knowledge Graph',
        };
      }
      if (lower.includes('instagram.com/reel') || lower.includes('tiktok.com')) {
        return {
          type: 'Short-Form Social Trading Reel',
          badgeColor: 'bg-pink-500/20 text-pink-400 border-pink-500/40',
          icon: Film,
          hasRules: false,
          recommendedAction: 'Analyze transcript, flag hype markers & preserve provenance',
          destination: 'Social Media Quarantine & Knowledge Vault',
        };
      }
      if (lower.includes('github.com')) {
        return {
          type: 'GitHub Quantitative Repository',
          badgeColor: 'bg-purple-500/20 text-purple-400 border-purple-500/40',
          icon: GitBranch,
          hasRules: true,
          recommendedAction: 'Clone repo, inspect algorithms & queue strategy candidate',
          destination: 'Algorithmic Vault + Candidate Queue',
        };
      }
      if (lower.includes('tradingview.com')) {
        return {
          type: 'TradingView PineScript / Setup',
          badgeColor: 'bg-cyan-500/20 text-cyan-400 border-cyan-500/40',
          icon: TrendingUp,
          hasRules: true,
          recommendedAction: 'Parse trading logic, entry/exit criteria & queue candidate',
          destination: 'Candidate Strategy Queue',
        };
      }

      // Check for trading rules keywords
      const ruleKeywords = [
        'entry rule', 'exit rule', 'stop loss', 'take profit', 'risk reward',
        'fair value gap', 'judas sweep', 'order block', 'liquidity sweep',
        'break of structure', 'market structure shift', 'breaker block',
        'strategy', 'pinescript', 'indicator', 'long condition', 'short condition',
      ];
      const foundRule = ruleKeywords.some((kw) => lower.includes(kw));

      if (foundRule) {
        return {
          type: 'Actionable Trading Setup / Rules',
          badgeColor: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/40',
          icon: Sparkles,
          hasRules: true,
          recommendedAction: 'Extract entry/exit rules & queue candidate for backtesting',
          destination: 'Candidate Strategy Queue (Zero Alpha Assumed)',
        };
      }

      // Check for macro / economic talk show keywords
      const macroKeywords = [
        'talk show', 'podcast', 'economic', 'macro', 'federal reserve', 'fed rate',
        'jerome powell', 'interest rate', 'inflation', 'cpi', 'quantitative tightening',
        'liquidity cycle', 'monetary policy', 'treasury yield', 'recession', 'stagflation',
        'dollar index', 'dxy', 'fomc', 'unemployment', 'rate cut', 'rate hike',
      ];
      if (macroKeywords.some((kw) => lower.includes(kw))) {
        return {
          type: 'Economic Talk Show / Macro Intelligence Reel',
          badgeColor: 'bg-amber-500/20 text-amber-300 border-amber-500/40',
          icon: Film,
          hasRules: false,
          recommendedAction: 'Macro Cognitive Transmission: Dissect monetary policy, inflation cycles & synthesize confluent trade plans',
          destination: 'Macro Cognitive Engine + Dynamic Trade Plans',
        };
      }

      return {
        type: isUrl ? 'Web Literature / Article' : 'Quantitative Research Text',
        badgeColor: 'bg-indigo-500/20 text-indigo-400 border-indigo-500/40',
        icon: FileText,
        hasRules: false,
        recommendedAction: 'Extract core hypotheses, citations & cross-domain links',
        destination: 'Knowledge Vault + Cross-Domain Graph',
      };
    }

    return null;
  }, [selectedFile, inputText]);

  const detected = autoDetectContent();

  // Submit Ingestion (Modes: AUTO, ANALYZE, RESEARCH, SAVE_KNOWLEDGE)
  const handleIngest = async (mode: ResearchIngestMode = selectedMode) => {
    if (!selectedFile && !inputText.trim()) {
      if (onNotify) onNotify('warning', 'Empty Input', 'Please drag a file or paste a URL / text to ingest.');
      return;
    }

    if (selectedFile && selectedFile.size > MAX_FILE_SIZE_BYTES) {
      const sizeMb = (selectedFile.size / (1024 * 1024)).toFixed(1);
      if (onNotify) {
        onNotify('error', 'File Too Large', `File is ${sizeMb} MB. Maximum allowed upload size is ${MAX_FILE_SIZE_MB} MB.`);
      }
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

      setActiveSummary(res);
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

  const handleSelectInboxSummary = (item: ResearchProvenanceItem) => {
    setActiveSummary({
      knowledge_id: item.knowledge_id,
      mode: 'RESEARCH',
      provenance: item,
      executive_summary:
        item.summary ||
        item.raw_excerpt ||
        item.raw_content_preview ||
        `Quantitative literature '${item.title}' by ${item.author_creator || 'Author Unknown'}. Registered in Research Provenance Ledger.`,
      chapter_breakdown: item.chapter_breakdown || [],
      file_metadata: {
        book_title: item.title,
        author_creator: item.author_creator,
        isbn: item.file_metadata?.isbn,
        edition: item.file_metadata?.edition,
        is_scanned: item.file_metadata?.is_scanned ?? false,
        ocr_provider: item.file_metadata?.ocr_provider,
        total_pages: item.file_metadata?.total_pages,
        pages_processed: item.file_metadata?.pages_processed,
      },
      summary: {
        concepts_saved: item.facts_count || 12,
        candidates_queued: item.hypotheses_count || 4,
        evidence_saved: item.facts_count || 6,
        rejected_archived: 0,
        comprehension_score: Math.round(((item.confidence_score ?? item.confidence) || 0.88) * 100),
      },
      concepts: [],
      strategy_candidates: [],
      evidence: [],
      rejected: [],
      verdict_message: `Viewing literature summary for ${item.title}`,
    });
  };

  const handleSendSummaryToTelegram = async () => {
    if (!activeSummary) return;
    try {
      setSendingTelegram(true);
      const title =
        activeSummary.file_metadata?.book_title ||
        activeSummary.provenance?.title ||
        'Quantitative Research Literature';
      const author =
        activeSummary.file_metadata?.author_creator ||
        activeSummary.provenance?.author_creator ||
        'Author Unknown';
      const sourceType =
        activeSummary.provenance?.source_type ||
        (activeSummary.file_metadata?.book_title ? 'PDF_BOOK' : 'RESEARCH');

      const factsCount =
        activeSummary.epistemic_counts?.facts ?? activeSummary.summary?.concepts_saved ?? 0;
      const hypoCount =
        activeSummary.epistemic_counts?.hypotheses ?? activeSummary.summary?.candidates_queued ?? 0;
      const rulesCount =
        activeSummary.epistemic_counts?.rules ?? activeSummary.strategy_candidates?.length ?? 0;
      const contraCount = activeSummary.epistemic_counts?.contradictions ?? 0;

      const candidateSummary =
        activeSummary.strategy_candidates?.[0]?.strategy_name ||
        (activeSummary.summary?.candidates_queued
          ? `${activeSummary.summary.candidates_queued} Formulated Candidate(s) Queued`
          : undefined);

      const res = await api.sendSummaryToTelegram({
        knowledge_id: activeSummary.knowledge_id,
        title,
        author_creator: author,
        source_type: sourceType,
        executive_summary:
          activeSummary.executive_summary ||
          activeSummary.verdict_message ||
          'Research synthesis from SKY terminal.',
        chapter_breakdown: activeSummary.chapter_breakdown || [],
        epistemic_counts: {
          facts: factsCount,
          hypotheses: hypoCount,
          rules: rulesCount,
          contradictions: contraCount,
        },
        candidate_summary: candidateSummary,
      });

      if (onNotify) {
        onNotify(
          res.status === 'SENT' ? 'success' : 'info',
          res.status === 'SENT' ? 'Telegram Dispatch' : 'Telegram Local Notification',
          res.message
        );
      }
    } catch (err: any) {
      console.error('Failed to dispatch summary to Telegram:', err);
      if (onNotify) {
        onNotify(
          'error',
          'Telegram Dispatch Failed',
          err?.message || 'Failed to dispatch summary to Telegram.'
        );
      }
    } finally {
      setSendingTelegram(false);
    }
  };

  const getSourceTypeBadge = (summary: ResearchIngestResult) => {
    const st = (summary.provenance?.source_type || (summary.file_metadata?.book_title ? 'PDF' : '')).toUpperCase();
    if (st === 'REEL' || st === 'TALK_SHOW') return { label: 'Macro Talk Show / Video Reel', icon: Film, color: 'bg-rose-500/20 text-rose-300 border-rose-500/40' };
    if (st === 'YOUTUBE') return { label: 'YouTube Video Research', icon: Play, color: 'bg-red-500/20 text-red-400 border-red-500/40' };
    if (st === 'GITHUB') return { label: 'GitHub Repository', icon: GitBranch, color: 'bg-purple-500/20 text-purple-400 border-purple-500/40' };
    if (st === 'CODE') return { label: 'Algorithmic Code', icon: Tag, color: 'bg-cyan-500/20 text-cyan-400 border-cyan-500/40' };
    if (st === 'ARTICLE') return { label: 'Quantitative Article', icon: BookOpen, color: 'bg-blue-500/20 text-blue-400 border-blue-500/40' };
    if (st === 'NOTES') return { label: 'Research Notes', icon: BookOpen, color: 'bg-amber-500/20 text-amber-400 border-amber-500/40' };
    if (st === 'DATASET') return { label: 'Dataset & Flow', icon: Layers, color: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/40' };
    return { label: summary.file_metadata?.book_title ? 'PDF Quantitative Monograph' : 'Research Source Summary', icon: BookOpen, color: 'bg-sky-500/20 text-sky-400 border-sky-500/40' };
  };

  // Run Backtest Verification on Candidate
  const handleRunBacktest = async (candidateId: string) => {
    try {
      setBacktestingCandidateId(candidateId);
      const res = await api.backtestResearchCandidate(candidateId, selectedSymbol, selectedTimeframe);
      if (onNotify) {
        const isPromoted = res.validation_stage === 'WALK_FORWARD' || res.validation_stage === 'PAPER_TEST';
        const isDataInsufficient = res.validation_stage === 'DATA_INSUFFICIENT';
        if (isDataInsufficient) {
          onNotify(
            'warning',
            'Data Insufficient (Invariant 1)',
            res.reason || 'Insufficient real market data to qualify candidate without synthetic fabrication.'
          );
        } else {
          onNotify(
            isPromoted ? 'success' : 'warning',
            isPromoted ? 'Candidate Qualified & Promoted!' : 'Candidate Archived as Rejected',
            `Backtest result for ${candidateId}: ${res.verdict || res.validation_stage}`
          );
        }
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
      case 'TALK_SHOW':
        return <Film className="w-4 h-4 text-rose-400" />;
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

      {/* SKY Knowledge Operating System Navigation Bar */}
      <div className="flex items-center gap-1.5 p-1.5 bg-slate-900/90 border border-slate-800 rounded-xl overflow-x-auto">
        <button
          onClick={() => setActiveKosTab('RESEARCH_LAB')}
          className={`flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-semibold tracking-wide transition-all whitespace-nowrap ${
            activeKosTab === 'RESEARCH_LAB'
              ? 'bg-indigo-600 text-white shadow-md'
              : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
          }`}
        >
          <UploadCloud className="w-4 h-4" />
          Research Ingest & Vaults
        </button>

        <button
          onClick={() => setActiveKosTab('PROJECT_BRAIN')}
          className={`flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-semibold tracking-wide transition-all whitespace-nowrap ${
            activeKosTab === 'PROJECT_BRAIN'
              ? 'bg-cyan-600 text-white shadow-md'
              : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
          }`}
        >
          <Cpu className="w-4 h-4 text-cyan-200" />
          Project Brain Context
        </button>

        <button
          onClick={() => setActiveKosTab('HUMAN_BRAIN')}
          className={`flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-semibold tracking-wide transition-all whitespace-nowrap ${
            activeKosTab === 'HUMAN_BRAIN'
              ? 'bg-purple-600 text-white shadow-md'
              : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
          }`}
        >
          <GraduationCap className="w-4 h-4 text-purple-200" />
          Human Brain Tutor
        </button>

        <button
          onClick={() => setActiveKosTab('KNOWLEDGE_MAP')}
          className={`flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-semibold tracking-wide transition-all whitespace-nowrap ${
            activeKosTab === 'KNOWLEDGE_MAP'
              ? 'bg-amber-600 text-white shadow-md'
              : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
          }`}
        >
          <Map className="w-4 h-4 text-amber-200" />
          Knowledge Map & Gaps
        </button>

        <button
          onClick={() => setActiveKosTab('LEARNING_PATH')}
          className={`flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-semibold tracking-wide transition-all whitespace-nowrap ${
            activeKosTab === 'LEARNING_PATH'
              ? 'bg-emerald-600 text-white shadow-md'
              : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
          }`}
        >
          <Award className="w-4 h-4 text-emerald-200" />
          Personal Learning Path
        </button>

        <button
          onClick={() => setActiveKosTab('KNOWLEDGE_AUDIT')}
          className={`flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-semibold tracking-wide transition-all whitespace-nowrap ${
            activeKosTab === 'KNOWLEDGE_AUDIT'
              ? 'bg-rose-700 text-white shadow-md'
              : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
          }`}
        >
          <ShieldCheck className="w-4 h-4 text-rose-200" />
          Quality & Integrity Audit
        </button>
      </div>

      {/* Sub-Desks */}
      {activeKosTab === 'PROJECT_BRAIN' && (
        <ProjectBrainDesk
          selectedSymbol={selectedSymbol}
          selectedTimeframe={selectedTimeframe}
          onNotify={onNotify}
        />
      )}

      {activeKosTab === 'HUMAN_BRAIN' && (
        <HumanBrainTeacher onNotify={onNotify} />
      )}

      {activeKosTab === 'KNOWLEDGE_MAP' && (
        <KnowledgeMapAndGaps onNotify={onNotify} />
      )}

      {activeKosTab === 'LEARNING_PATH' && (
        <LearningPathDesk onNotify={onNotify} />
      )}

      {activeKosTab === 'KNOWLEDGE_AUDIT' && (
        <KnowledgeAuditDesk onNotify={onNotify} />
      )}

      {/* Primary Research Ingest Lab View */}
      {activeKosTab === 'RESEARCH_LAB' && (
        <>
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
            accept=".pdf,.py,.pine,.mq4,.mq5,.json,.csv,.txt,.md,.mp4,.mov,.webm,.mp3,.m4a,.wav,image/*"
          />

          <div className="flex flex-col items-center justify-center gap-2">
            {selectedFile ? (
              <>
                <FileText className="w-10 h-10 text-emerald-400 animate-bounce" />
                <p className="text-sm font-semibold text-emerald-300">
                  Selected File: {selectedFile.name} ({selectedFile.size >= 1024 * 1024 ? `${(selectedFile.size / (1024 * 1024)).toFixed(1)} MB` : `${(selectedFile.size / 1024).toFixed(1)} KB`})
                </p>
                <p className="text-xs text-slate-400">Click or drag another file to replace</p>
              </>
            ) : (
              <>
                <UploadCloud className="w-10 h-10 text-indigo-400/80" />
                <p className="text-sm font-medium text-slate-200">
                  Drop anything here ( <span className="text-rose-400 font-bold">🎬 Video Reels / Talk Shows</span> • <span className="text-cyan-400">PDFs / Books</span> • <span className="text-purple-400">Code / PineScript</span> • <span className="text-amber-400">Notes / Articles</span> • <span className="text-pink-400">Images</span> )
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

        {/* Real-time Content Auto-Detection Preview Card */}
        {detected && (
          <div className="bg-slate-950/80 border border-indigo-500/30 rounded-xl p-3.5 flex flex-col md:flex-row items-start md:items-center justify-between gap-3 text-xs shadow-inner">
            <div className="flex items-start md:items-center gap-3">
              <div className={`p-2 rounded-lg border ${detected.badgeColor} shrink-0 mt-0.5 md:mt-0`}>
                <detected.icon className="w-4 h-4" />
              </div>
              <div className="flex flex-col gap-0.5">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-semibold text-slate-100">{detected.type}</span>
                  <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                    Auto-Detected
                  </span>
                  {detected.hasRules ? (
                    <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-purple-500/15 text-purple-300 border border-purple-500/40">
                      ⚡ Strategy Rules Detected
                    </span>
                  ) : (
                    <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-slate-800/80 text-slate-400 border border-slate-700">
                      Conceptual Literature
                    </span>
                  )}
                </div>
                <p className="text-[11px] text-slate-400">{detected.recommendedAction}</p>
              </div>
            </div>

            <div className="flex items-center gap-2 text-[11px] text-slate-400 self-end md:self-center shrink-0">
              <span className="text-slate-500">Target Destination:</span>
              <span className="font-medium text-slate-300 bg-slate-900 px-2.5 py-1 rounded-md border border-slate-800">
                {detected.destination}
              </span>
            </div>
          </div>
        )}

        {/* Unified Ingestion Action Bar */}
        <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-slate-800/80">
          <div className="text-xs text-slate-400 flex items-center gap-2">
            <Shield className="w-4 h-4 text-emerald-400 shrink-0" />
            <span>Epistemic Separation: Source Worldview Preserved • Zero Alpha Assumed Prior to Backtest</span>
          </div>

          <div className="flex items-center gap-2.5 flex-wrap">
            {/* Mode Override Selector */}
            <div className="flex items-center bg-slate-950 border border-slate-800 rounded-lg p-0.5 text-xs">
              <button
                type="button"
                onClick={() => setSelectedMode('AUTO')}
                className={`px-2.5 py-1.5 rounded-md font-medium transition-all ${
                  selectedMode === 'AUTO'
                    ? 'bg-indigo-600 text-white shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
                title="Auto-Detect: Automatically routes and deconstructs content based on file & text rules"
              >
                ⚡ Auto-Detect
              </button>
              <button
                type="button"
                onClick={() => setSelectedMode('ANALYZE')}
                className={`px-2.5 py-1.5 rounded-md font-medium transition-all ${
                  selectedMode === 'ANALYZE'
                    ? 'bg-blue-600 text-white shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
                title="Analyze Only: Extract claims & concepts without queueing a strategy candidate"
              >
                🔬 Analyze
              </button>
              <button
                type="button"
                onClick={() => setSelectedMode('SAVE_KNOWLEDGE')}
                className={`px-2.5 py-1.5 rounded-md font-medium transition-all ${
                  selectedMode === 'SAVE_KNOWLEDGE'
                    ? 'bg-cyan-600 text-white shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
                title="Save Knowledge: Store directly into Knowledge Vault"
              >
                📚 Knowledge
              </button>
              <button
                type="button"
                onClick={() => setSelectedMode('RESEARCH')}
                className={`px-2.5 py-1.5 rounded-md font-medium transition-all ${
                  selectedMode === 'RESEARCH'
                    ? 'bg-purple-600 text-white shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
                title="Deep Research: Full atomic deconstruction and force strategy candidate queueing"
              >
                🔭 Deep Research
              </button>
            </div>

            {/* Single Unified Primary Action Button */}
            <button
              onClick={() => handleIngest(selectedMode)}
              disabled={isSubmitting || (!selectedFile && !inputText.trim())}
              className="px-5 py-2 bg-gradient-to-r from-indigo-600 via-purple-600 to-indigo-600 hover:from-indigo-500 hover:to-purple-500 text-white rounded-lg text-xs font-bold flex items-center gap-2 shadow-lg shadow-indigo-900/30 transition-all disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
              title={
                selectedMode === 'AUTO'
                  ? 'Automatically detect content and execute ingestion pipeline'
                  : `Execute ingestion in ${selectedMode} mode`
              }
            >
              {isSubmitting ? (
                <>
                  <RotateCcw className="w-4 h-4 animate-spin text-indigo-300" />
                  <span>DECOMPOSING & INGESTING...</span>
                </>
              ) : selectedMode === 'AUTO' ? (
                <>
                  <Sparkles className="w-4 h-4 text-amber-300" />
                  <span>⚡ AUTO INGEST & DECONSTRUCT</span>
                </>
              ) : selectedMode === 'ANALYZE' ? (
                <>
                  <Sparkles className="w-4 h-4 text-blue-300" />
                  <span>🔬 RUN ANALYSIS</span>
                </>
              ) : selectedMode === 'SAVE_KNOWLEDGE' ? (
                <>
                  <BookOpen className="w-4 h-4 text-cyan-300" />
                  <span>📚 SAVE TO VAULT</span>
                </>
              ) : (
                <>
                  <Compass className="w-4 h-4 text-purple-300" />
                  <span>🔭 RESEARCH & DISCOVER</span>
                </>
              )}
            </button>
          </div>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* YOUTUBE RESEARCH INTELLIGENCE V5: AUTONOMOUS EXPLORER                      */}
      {/* ========================================================================= */}
      <div className="bg-slate-900/90 border border-red-900/40 rounded-xl p-5 flex flex-col gap-4 shadow-xl">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-2 border-b border-slate-800 pb-3">
          <div className="flex items-center gap-2.5">
            <div className="p-2 bg-red-600/20 text-red-400 border border-red-500/30 rounded-lg">
              <Youtube className="w-5 h-5 text-red-500" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-bold text-slate-100 tracking-wide">
                  AUTONOMOUS YOUTUBE CHANNEL & PLAYLIST EXPLORER (V5)
                </h3>
                <span className="px-2 py-0.5 text-[10px] font-bold bg-red-950 text-red-300 border border-red-800/60 rounded">
                  RESEARCH AGENT
                </span>
              </div>
              <p className="text-[11px] text-slate-400">
                Explore channels, playlists or @handles • SMC setups & rule contradiction detection • Strictly quarantined at confidence = 0.0
              </p>
            </div>
          </div>

          {ytJobData?.status === 'COMPLETED' && (
            <button
              onClick={() => setShowYtResults(!showYtResults)}
              className="px-3 py-1 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs rounded border border-slate-700 flex items-center gap-1.5 transition-colors"
            >
              {showYtResults ? 'Hide Synthesis Dossier' : 'View Synthesis Dossier'}
            </button>
          )}
        </div>

        {/* Input Controls */}
        <div className="flex flex-col md:flex-row items-center gap-3">
          <div className="relative flex-1 w-full">
            <input
              type="text"
              value={ytExploreInput}
              onChange={(e) => setYtExploreInput(e.target.value)}
              placeholder="Enter YouTube Channel URL, Playlist URL, @Handle, or Video URL (e.g. @TraderTom, PL...)"
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3.5 py-2 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-red-500 transition-colors"
              disabled={ytExploreLoading}
            />
          </div>

          <div className="flex items-center gap-2 w-full md:w-auto">
            <div className="flex items-center gap-1.5 bg-slate-950 border border-slate-800 px-3 py-2 rounded-lg text-xs">
              <span className="text-slate-400">Cap:</span>
              <select
                value={ytExploreLimit}
                onChange={(e) => setYtExploreLimit(Number(e.target.value))}
                className="bg-transparent text-slate-200 focus:outline-none cursor-pointer"
                disabled={ytExploreLoading}
              >
                <option value={5} className="bg-slate-900">5 videos</option>
                <option value={10} className="bg-slate-900">10 videos</option>
                <option value={20} className="bg-slate-900">20 videos</option>
                <option value={50} className="bg-slate-900">50 max</option>
              </select>
            </div>

            <button
              onClick={handleStartYouTubeExplore}
              disabled={ytExploreLoading || !ytExploreInput.trim()}
              className="px-4 py-2 bg-gradient-to-r from-red-600 to-rose-600 hover:from-red-500 hover:to-rose-500 text-white rounded-lg text-xs font-bold flex items-center justify-center gap-2 shadow-lg shadow-red-950/40 transition-all disabled:opacity-50 whitespace-nowrap flex-1 md:flex-initial"
            >
              {ytExploreLoading ? (
                <>
                  <RotateCcw className="w-3.5 h-3.5 animate-spin" />
                  <span>EXPLORING...</span>
                </>
              ) : (
                <>
                  <Play className="w-3.5 h-3.5" />
                  <span>AUTONOMOUS EXPLORE</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* Recent Explorations History Bar */}
        {recentYtJobs.length > 0 && (
          <div className="flex flex-wrap items-center gap-2 pt-1 border-t border-slate-800/60 text-[11px]">
            <span className="text-slate-500 font-medium">Recent Sessions:</span>
            {recentYtJobs.slice(0, 4).map((j: any) => (
              <button
                key={j.job_id}
                onClick={() => handleSelectPastJob(j.job_id)}
                className={`px-2.5 py-1 rounded border transition-all flex items-center gap-1.5 ${
                  ytActiveJobId === j.job_id
                    ? 'bg-red-950/70 border-red-500/50 text-red-300 font-semibold shadow-sm'
                    : 'bg-slate-950 border-slate-800 text-slate-400 hover:text-slate-200 hover:border-slate-700'
                }`}
              >
                <span className={`w-1.5 h-1.5 rounded-full ${j.status === 'COMPLETED' ? 'bg-emerald-400' : j.status === 'FAILED' ? 'bg-red-400' : 'bg-amber-400'}`} />
                <span className="truncate max-w-[200px]">{j.title.replace('Explore YouTube: ', '')}</span>
                <span className="font-mono text-[10px] text-slate-500">{j.status === 'COMPLETED' ? '✓' : `${j.progress_pct}%`}</span>
              </button>
            ))}
          </div>
        )}

        {/* Live Exploration Tracker */}
        {ytActiveJobId && (
          <div className="bg-slate-950 border border-slate-800/80 rounded-lg p-3.5 flex flex-col gap-2">
            <div className="flex items-center justify-between text-xs">
              <div className="flex items-center gap-2">
                <span className={`w-2 h-2 rounded-full ${ytJobData?.status === 'COMPLETED' ? 'bg-emerald-400' : ytJobData?.status === 'FAILED' ? 'bg-red-400' : 'bg-amber-400 animate-ping'}`} />
                <span className="text-slate-300 font-semibold">Job `{ytActiveJobId}`</span>
                <span className="text-slate-500">•</span>
                <span className="text-slate-400">{ytJobData?.status || 'RUNNING'}</span>
                {ytJobData?.status === 'COMPLETED' && (
                  <span className="text-emerald-400 font-medium text-[11px]">✓ Synthesis Complete</span>
                )}
              </div>
              <span className="font-bold text-red-400">{ytJobData?.progress_pct || 0}%</span>
            </div>

            <div className="w-full bg-slate-900 h-1.5 rounded-full overflow-hidden">
              <div
                className="bg-gradient-to-r from-red-500 to-rose-400 h-full transition-all duration-300"
                style={{ width: `${ytJobData?.progress_pct || 5}%` }}
              />
            </div>

            {ytJobData?.result?.message ? (
              <p className="text-[11px] text-slate-300">
                <span className="text-red-400 font-mono font-semibold">[{ytJobData.result.step || 'RUNNING'}]</span>{' '}
                {ytJobData.result.message}
              </p>
            ) : ytJobData?.result?.step ? (
              <p className="text-[11px] text-slate-400 italic">
                Active Phase: <span className="text-slate-200 font-medium">{ytJobData.result.step}</span>
                {ytJobData.result.current_video && ` — processing "${ytJobData.result.current_video}"`}
              </p>
            ) : ytJobData?.status === 'COMPLETED' ? (
              <p className="text-[11px] text-emerald-400">
                Processed {ytJobData.result?.videos_processed || 0} videos. View synthesis dossier below.
              </p>
            ) : (
              <p className="text-[11px] text-slate-400 italic">
                {ytExploreLoading ? 'Dispatching research agent & discovering playlist videos...' : 'Job registered.'}
              </p>
            )}
          </div>
        )}

        {/* Synthesized Exploration Results Dossier */}
        {showYtResults && ytJobData?.result && (
          <div className="bg-[#0b101b] border border-red-500/40 rounded-xl p-4 flex flex-col gap-4 animate-fadeIn">
            {/* Dossier Header */}
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-3">
              <div>
                <h4 className="text-sm font-bold text-slate-100 flex items-center gap-2">
                  <span>📺 Creator Research Dossier:</span>
                  <span className="text-red-400">{ytJobData.result.creator_profile?.channel_name || ytJobData.result.source?.canonical_url}</span>
                </h4>
                <p className="text-xs text-slate-400 mt-0.5">
                  Analyzed {ytJobData.result.videos_processed} videos ({ytJobData.result.videos_skipped} skipped via deduplication sentinel)
                </p>
              </div>

              <div className="flex items-center gap-2">
                <span className="px-2.5 py-1 text-[11px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40 rounded">
                  Hype Density: {ytJobData.result.creator_profile?.hype_frequency_pct || 0}%
                </span>
                <span className="px-2.5 py-1 text-[11px] font-bold bg-purple-500/20 text-purple-300 border border-purple-500/40 rounded">
                  Contradictions: {ytJobData.result.contradictions?.length || 0}
                </span>
              </div>
            </div>

            {/* Grid: Recurring Concepts & Rule Contradictions */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {/* Recurring SMC Concepts */}
              <div className="bg-slate-950/80 border border-slate-800 rounded-lg p-3 flex flex-col gap-2">
                <h5 className="text-xs font-bold text-slate-300 flex items-center gap-1.5">
                  <Layers className="w-3.5 h-3.5 text-indigo-400" />
                  <span>Consolidated Technical Setups ({ytJobData.result.recurring_concepts?.length || 0})</span>
                </h5>
                <div className="flex flex-col gap-2 max-h-48 overflow-y-auto pr-1">
                  {ytJobData.result.recurring_concepts?.map((c: any, i: number) => (
                    <div key={i} className="p-2 bg-slate-900/60 border border-slate-800/80 rounded text-xs">
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-slate-200">{c.concept_name}</span>
                        <span className="text-[10px] px-1.5 py-0.5 bg-indigo-950 text-indigo-300 rounded border border-indigo-800">
                          {c.appearance_count} sessions
                        </span>
                      </div>
                      {c.sample_contexts?.[0] && (
                        <p className="text-[11px] text-slate-400 italic mt-1 line-clamp-2">
                          "{c.sample_contexts[0]}"
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              {/* Detected Rule Contradictions */}
              <div className="bg-slate-950/80 border border-slate-800 rounded-lg p-3 flex flex-col gap-2">
                <h5 className="text-xs font-bold text-slate-300 flex items-center gap-1.5">
                  <ShieldAlert className="w-3.5 h-3.5 text-amber-400" />
                  <span>Rule Contradictions & Evolutions ({ytJobData.result.contradictions?.length || 0})</span>
                </h5>
                <div className="flex flex-col gap-2 max-h-48 overflow-y-auto pr-1">
                  {ytJobData.result.contradictions?.length ? (
                    ytJobData.result.contradictions.map((cont: any, i: number) => (
                      <div key={i} className="p-2 bg-amber-950/20 border border-amber-900/40 rounded text-xs flex flex-col gap-1">
                        <span className="font-semibold text-amber-300">{cont.rule_name}</span>
                        <p className="text-[11px] text-slate-400">
                          <span className="text-slate-500">Earlier:</span> {cont.earlier_statement}
                        </p>
                        <p className="text-[11px] text-slate-300">
                          <span className="text-amber-400 font-medium">Later Refinement:</span> {cont.later_statement}
                        </p>
                        <span className="text-[10px] text-amber-400/90 italic mt-0.5">
                          ⚠️ {cont.epistemic_warning}
                        </span>
                      </div>
                    ))
                  ) : (
                    <p className="text-xs text-slate-500 italic py-2">
                      No internal rule contradictions detected across analyzed sessions.
                    </p>
                  )}
                </div>
              </div>
            </div>

            {/* Quarantined Strategy Candidates */}
            {ytJobData.result.synthesized_candidates?.length > 0 && (
              <div className="bg-slate-950/80 border border-purple-900/50 rounded-lg p-3.5 flex flex-col gap-2.5">
                <div className="flex items-center justify-between">
                  <h5 className="text-xs font-bold text-purple-300 flex items-center gap-1.5">
                    <FlaskConical className="w-3.5 h-3.5 text-purple-400" />
                    <span>Quarantined Strategy Candidates ({ytJobData.result.synthesized_candidates.length})</span>
                  </h5>
                  <span className="text-[10px] px-2 py-0.5 bg-red-950/80 text-red-300 border border-red-700/60 rounded font-bold">
                    Confidence: 0.0 • UNTESTED
                  </span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {ytJobData.result.synthesized_candidates.map((cand: any, i: number) => (
                    <div key={i} className="p-3 bg-slate-900/80 border border-slate-800 rounded-lg flex flex-col justify-between gap-2">
                      <div className="flex flex-col gap-1">
                        <div className="flex items-center justify-between">
                          <span className="font-bold text-xs text-slate-200">{cand.strategy_name}</span>
                          <span className="text-[10px] text-slate-500 font-mono">{cand.candidate_id}</span>
                        </div>
                        <p className="text-[11px] text-slate-400 mt-0.5">{cand.hypothesis}</p>
                        <div className="bg-slate-950 p-2 rounded border border-slate-800/60 text-[10px] text-slate-300 flex flex-col gap-0.5 mt-1 font-mono">
                          <div><span className="text-indigo-400">Trigger:</span> {cand.entry_rules?.condition}</div>
                          <div><span className="text-amber-400">Exit:</span> SL {cand.exit_rules?.sl_rule} | TP {cand.exit_rules?.tp_target}</div>
                        </div>
                      </div>

                      <div className="flex items-center justify-between pt-2 border-t border-slate-800/80">
                        <span className="text-[10px] text-slate-500">Citations: {cand.creator_repetition_count} sessions</span>
                        <button
                          onClick={() => handleRunBacktest(cand.candidate_id)}
                          disabled={backtestingCandidateId === cand.candidate_id}
                          className="px-2.5 py-1 bg-purple-600/30 hover:bg-purple-600/50 text-purple-200 border border-purple-500/50 rounded text-[11px] font-bold flex items-center gap-1 transition-colors disabled:opacity-50"
                        >
                          <Play className="w-3 h-3" />
                          <span>{backtestingCandidateId === cand.candidate_id ? 'TESTING...' : 'TEST IN SANDBOX'}</span>
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* ========================================================================= */}
      {/* DEDICATED LITERATURE & RESEARCH SUMMARY SECTION                           */}
      {/* ========================================================================= */}
      {activeSummary && (
        <div className="bg-[#090d16] border border-sky-500/40 rounded-xl p-5 flex flex-col gap-4 shadow-2xl animate-fadeIn">
          {/* Top Bar: Book Title, Badges, Close */}
          <div className="flex flex-wrap items-start justify-between gap-3 border-b border-[#1e293b] pb-4">
            <div className="flex flex-col gap-1.5 max-w-4xl">
              <div className="flex items-center gap-2 flex-wrap">
                {(() => {
                  const badge = getSourceTypeBadge(activeSummary);
                  const Icon = badge.icon;
                  return (
                    <span className={`px-2.5 py-0.5 rounded text-[11px] font-bold ${badge.color} uppercase tracking-wider flex items-center gap-1`}>
                      <Icon className="w-3.5 h-3.5" />
                      {badge.label}
                    </span>
                  );
                })()}
                {activeSummary.file_metadata?.edition && (
                  <span className="px-2 py-0.5 rounded text-[10px] bg-slate-800 text-slate-300 font-semibold border border-slate-700">
                    {activeSummary.file_metadata.edition}
                  </span>
                )}
                {activeSummary.file_metadata?.isbn && (
                  <span className="px-2 py-0.5 rounded text-[10px] bg-indigo-950/60 text-indigo-300 font-mono border border-indigo-800/60">
                    ISBN: {activeSummary.file_metadata.isbn}
                  </span>
                )}
                <span
                  className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                    activeSummary.file_metadata?.is_scanned
                      ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                      : 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                  }`}
                >
                  {activeSummary.file_metadata?.is_scanned
                    ? `📸 Vision OCR (${activeSummary.file_metadata.ocr_provider || 'Processed'})`
                    : '⚡ Native Digital Stream'}
                </span>
                {activeSummary.file_metadata?.total_pages && (
                  <span className="text-[11px] text-slate-400 font-medium">
                    {activeSummary.file_metadata.pages_processed || activeSummary.file_metadata.total_pages} pages analyzed
                  </span>
                )}
              </div>

              <h2 className="text-lg md:text-xl font-extrabold text-white tracking-tight">
                {activeSummary.file_metadata?.book_title || activeSummary.provenance?.title || 'Quantitative Literature Summary'}
              </h2>

              <p className="text-xs text-slate-400">
                Author / Creator:{' '}
                <span className="text-slate-200 font-semibold">
                  {activeSummary.file_metadata?.author_creator ||
                    activeSummary.provenance?.author_creator ||
                    'Author Unknown'}
                </span>
                {' · '}Ingested into Provenance Ledger:{' '}
                <span className="text-sky-300 font-mono">{activeSummary.knowledge_id}</span>
              </p>
            </div>

            <div className="flex items-center gap-2 flex-wrap sm:flex-nowrap">
              <button
                onClick={handleSendSummaryToTelegram}
                disabled={sendingTelegram}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-sky-500/20 hover:bg-sky-500/30 text-sky-300 border border-sky-500/40 text-xs font-bold transition-all hover:border-sky-400 disabled:opacity-50 shadow-sm"
                title="Send formatted research summary to Telegram"
              >
                <Send className={`w-3.5 h-3.5 ${sendingTelegram ? 'animate-pulse text-sky-200' : ''}`} />
                {sendingTelegram ? 'Sending to Telegram...' : 'Send to Telegram'}
              </button>

              <button
                onClick={() => setActiveSummary(null)}
                className="text-slate-500 hover:text-slate-300 p-1.5 rounded-lg hover:bg-slate-800 transition-colors"
                title="Close Summary View"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
          </div>

          {/* Core Executive Summary Narrative */}
          <div className="bg-[#0c1220] border border-[#1e293b] rounded-lg p-4 flex flex-col gap-2.5">
            <div className="flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-amber-400" />
              <h3 className="text-xs font-bold uppercase tracking-wider text-amber-300">
                Executive Synthesis & Quantitative Methodology
              </h3>
            </div>
            <p className="text-xs md:text-sm text-slate-200 leading-relaxed font-sans">
              {activeSummary.executive_summary || activeSummary.verdict_message}
            </p>
          </div>

          {/* ========================================================================= */}
          {/* MACRO COGNITIVE UNDERSTANDING & CONFLUENT TRADE PLANS (REELS / TALK SHOWS) */}
          {/* ========================================================================= */}
          {activeSummary.macro_analysis && (
            <div className="bg-[#0b1220] border-2 border-rose-500/40 rounded-xl p-4 flex flex-col gap-4 shadow-2xl">
              {/* Header */}
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-3">
                <div className="flex items-center gap-2.5">
                  <div className="p-2 bg-rose-500/20 text-rose-400 border border-rose-500/40 rounded-lg">
                    <Brain className="w-5 h-5 text-rose-400" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2 flex-wrap">
                      <h3 className="text-sm font-bold text-white tracking-wide">
                        MACRO COGNITIVE COMPREHENSION &amp; TRADE PLAN SYNTHESIS
                      </h3>
                      <span className="px-2 py-0.5 text-[10px] font-bold bg-rose-950 text-rose-300 border border-rose-800/60 rounded">
                        HUMAN-LIKE COGNITION
                      </span>
                      {activeSummary.macro_analysis.engine_provider && (
                        <span className="px-2 py-0.5 text-[10px] font-mono text-cyan-300 bg-cyan-950/70 border border-cyan-800/50 rounded">
                          {activeSummary.macro_analysis.engine_provider}
                        </span>
                      )}
                    </div>
                    <p className="text-[11px] text-slate-400">
                      Dissecting economic talk show / reel • Speaker: <strong className="text-slate-200">{activeSummary.macro_analysis.speaker_author || 'Unknown'}</strong> • Worldview: <span className="text-indigo-300">{activeSummary.macro_analysis.source_worldview}</span>
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-slate-400">Kelly Sizing Multiplier:</span>
                  <span className={`px-2 py-1 rounded text-xs font-bold font-mono ${
                    (activeSummary.macro_analysis.trade_planning_implications?.kelly_multiplier ?? 1) >= 1
                      ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                      : 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                  }`}>
                    {activeSummary.macro_analysis.trade_planning_implications?.kelly_multiplier ?? 1.0}x
                  </span>
                </div>
              </div>

              {/* Macro Thesis */}
              <div className="p-3 bg-slate-950/80 rounded-lg border border-slate-800 flex flex-col gap-1.5">
                <span className="text-[10px] font-bold uppercase tracking-wider text-amber-400 flex items-center gap-1.5">
                  <Sparkles className="w-3.5 h-3.5 text-amber-400" />
                  Core Executive Macro Thesis
                </span>
                <p className="text-xs text-slate-200 leading-relaxed font-mono">
                  {activeSummary.macro_analysis.executive_macro_thesis}
                </p>
              </div>

              {/* 4-Pillar Macro Regime State */}
              {activeSummary.macro_analysis.macro_regime && (
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                  <div className="bg-[#080d1a] border border-slate-800 rounded-lg p-2.5 flex flex-col">
                    <span className="text-[10px] text-slate-500 font-semibold uppercase">Monetary Policy</span>
                    <span className={`text-xs font-bold mt-1 ${
                      activeSummary.macro_analysis.macro_regime.monetary_stance === 'DOVISH'
                        ? 'text-emerald-400'
                        : activeSummary.macro_analysis.macro_regime.monetary_stance === 'HAWKISH'
                        ? 'text-rose-400'
                        : 'text-amber-400'
                    }`}>
                      {activeSummary.macro_analysis.macro_regime.monetary_stance}
                    </span>
                    <span className="text-[10px] text-slate-400 mt-0.5 truncate">
                      {activeSummary.macro_analysis.macro_regime.primary_driver || 'Central Bank'}
                    </span>
                  </div>

                  <div className="bg-[#080d1a] border border-slate-800 rounded-lg p-2.5 flex flex-col">
                    <span className="text-[10px] text-slate-500 font-semibold uppercase">Inflation Vector</span>
                    <span className={`text-xs font-bold mt-1 ${
                      activeSummary.macro_analysis.macro_regime.inflation_trajectory === 'COOLING'
                        ? 'text-emerald-400'
                        : 'text-rose-400'
                    }`}>
                      {activeSummary.macro_analysis.macro_regime.inflation_trajectory}
                    </span>
                    <span className="text-[10px] text-slate-400 mt-0.5">CPI / PCE Momentum</span>
                  </div>

                  <div className="bg-[#080d1a] border border-slate-800 rounded-lg p-2.5 flex flex-col">
                    <span className="text-[10px] text-slate-500 font-semibold uppercase">Liquidity Cycle</span>
                    <span className={`text-xs font-bold mt-1 ${
                      activeSummary.macro_analysis.macro_regime.liquidity_cycle === 'EXPANDING'
                        ? 'text-cyan-400'
                        : 'text-amber-400'
                    }`}>
                      {activeSummary.macro_analysis.macro_regime.liquidity_cycle}
                    </span>
                    <span className="text-[10px] text-slate-400 mt-0.5">Global M2 &amp; RRP</span>
                  </div>

                  <div className="bg-[#080d1a] border border-slate-800 rounded-lg p-2.5 flex flex-col">
                    <span className="text-[10px] text-slate-500 font-semibold uppercase">Growth Outlook</span>
                    <span className={`text-xs font-bold mt-1 ${
                      activeSummary.macro_analysis.macro_regime.growth_outlook === 'EXPANSION'
                        ? 'text-emerald-400'
                        : 'text-purple-400'
                    }`}>
                      {activeSummary.macro_analysis.macro_regime.growth_outlook}
                    </span>
                    <span className="text-[10px] text-slate-400 mt-0.5">Macro Cycle Phase</span>
                  </div>
                </div>
              )}

              {/* Causal Transmission Chains */}
              {activeSummary.macro_analysis.causal_chains && activeSummary.macro_analysis.causal_chains.length > 0 && (
                <div className="flex flex-col gap-2">
                  <h4 className="text-xs font-bold text-slate-300 flex items-center gap-1.5 uppercase tracking-wider">
                    <Radio className="w-3.5 h-3.5 text-cyan-400" />
                    Causal Economic Transmission Chains ({activeSummary.macro_analysis.causal_chains.length})
                  </h4>
                  <div className="grid grid-cols-1 gap-2">
                    {activeSummary.macro_analysis.causal_chains.map((chain, idx) => (
                      <div key={idx} className="p-3 bg-slate-950/70 border border-slate-800/80 rounded-lg flex flex-col md:flex-row items-start md:items-center justify-between gap-3 text-xs">
                        <div className="flex flex-col md:flex-row items-start md:items-center gap-2 flex-wrap">
                          <span className="font-bold text-amber-300 bg-amber-950/50 px-2 py-0.5 rounded border border-amber-800/40">
                            {chain.cause}
                          </span>
                          <ArrowRight className="w-3.5 h-3.5 text-slate-500 hidden md:block shrink-0" />
                          <span className="text-slate-300 font-medium">
                            {chain.mechanism}
                          </span>
                          <ArrowRight className="w-3.5 h-3.5 text-slate-500 hidden md:block shrink-0" />
                          <span className="text-cyan-300 font-semibold">
                            {chain.market_impact}
                          </span>
                          <ArrowRight className="w-3.5 h-3.5 text-slate-500 hidden md:block shrink-0" />
                          <span className="text-emerald-300 font-bold bg-emerald-950/50 px-2 py-0.5 rounded border border-emerald-800/40">
                            {chain.crypto_consequence}
                          </span>
                        </div>
                        <span className="text-[10px] font-mono text-slate-400 px-2 py-0.5 rounded bg-slate-900 border border-slate-800 shrink-0">
                          {chain.time_horizon}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Multi-Asset Sentiment Matrix */}
              {activeSummary.macro_analysis.asset_matrix && Object.keys(activeSummary.macro_analysis.asset_matrix).length > 0 && (
                <div className="flex flex-col gap-2">
                  <h4 className="text-xs font-bold text-slate-300 flex items-center gap-1.5 uppercase tracking-wider">
                    <DollarSign className="w-3.5 h-3.5 text-emerald-400" />
                    Multi-Asset Transmission &amp; Sentiment Matrix
                  </h4>
                  <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-2">
                    {Object.entries(activeSummary.macro_analysis.asset_matrix).map(([sym, item]) => {
                      const isBull = item.sentiment === 'BULLISH';
                      const isBear = item.sentiment === 'BEARISH';
                      return (
                        <div key={sym} className={`p-2.5 rounded-lg border flex flex-col justify-between gap-1 text-xs ${
                          isBull ? 'bg-emerald-950/20 border-emerald-500/30' : isBear ? 'bg-rose-950/20 border-rose-500/30' : 'bg-slate-950 border-slate-800'
                        }`}>
                          <div className="flex items-center justify-between">
                            <span className="font-bold text-slate-200">{item.asset || sym}</span>
                            <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${
                              isBull ? 'bg-emerald-500/20 text-emerald-300' : isBear ? 'bg-rose-500/20 text-rose-300' : 'bg-slate-800 text-slate-300'
                            }`}>
                              {item.sentiment}
                            </span>
                          </div>
                          <p className="text-[10px] text-slate-400 line-clamp-2 mt-0.5">
                            {item.rationale}
                          </p>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Dynamic Trading Plans Generated From Macro Understanding */}
              {activeSummary.dynamic_trading_plans && activeSummary.dynamic_trading_plans.length > 0 && (
                <div className="flex flex-col gap-2.5 pt-3 border-t border-slate-800">
                  <div className="flex items-center justify-between flex-wrap gap-2">
                    <h4 className="text-xs font-bold text-sky-300 flex items-center gap-1.5 uppercase tracking-wider">
                      <Target className="w-3.5 h-3.5 text-sky-400" />
                      Dynamic Macro-Confluent Trading Plans ({activeSummary.dynamic_trading_plans.length})
                    </h4>
                    <span className="text-[10px] text-slate-400">
                      Evaluated against live SMC liquidity structures &bull; Half-Kelly constrained
                    </span>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {activeSummary.dynamic_trading_plans.map((plan, idx) => {
                      const isConfluent = plan.macroAlignment === 'CONFLUENT';
                      const isDampened = plan.macroAlignment === 'CAUTION_DAMPENED';
                      return (
                        <div key={idx} className="bg-[#070b14] border border-sky-500/30 rounded-xl p-3.5 flex flex-col justify-between gap-3 text-xs">
                          <div className="flex flex-col gap-2">
                            <div className="flex items-center justify-between">
                              <div className="flex items-center gap-2">
                                <span className="text-sm font-bold text-white font-mono">{plan.symbol}</span>
                                <span className={`px-2 py-0.5 rounded text-[10px] font-bold font-mono ${
                                  plan.bias === 'BULLISH'
                                    ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                                    : plan.bias === 'BEARISH'
                                    ? 'bg-rose-500/20 text-rose-300 border border-rose-500/40'
                                    : 'bg-slate-800 text-slate-300'
                                }`}>
                                  {plan.bias}
                                </span>
                              </div>

                              <span className={`px-2 py-0.5 rounded text-[10px] font-bold flex items-center gap-1 ${
                                isConfluent
                                  ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                                  : isDampened
                                  ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                                  : 'bg-slate-800 text-slate-300 border border-slate-700'
                              }`}>
                                <Zap className="w-3 h-3" />
                                {plan.macroAlignment} ({plan.riskMultiplier}x Sizing)
                              </span>
                            </div>

                            <div className="grid grid-cols-3 gap-2 p-2 rounded bg-slate-950/80 border border-slate-800 font-mono text-[11px]">
                              <div>
                                <span className="text-slate-500 block text-[10px]">CURRENT</span>
                                <span className="text-white font-semibold">${plan.currentPrice?.toLocaleString()}</span>
                              </div>
                              <div>
                                <span className="text-slate-500 block text-[10px]">PDH / PDL</span>
                                <span className="text-slate-300 text-[10px]">${plan.pdh?.toLocaleString()} / ${plan.pdl?.toLocaleString()}</span>
                              </div>
                              <div>
                                <span className="text-slate-500 block text-[10px]">FVG ZONE</span>
                                <span className="text-amber-300 text-[10px] truncate block">{plan.fvgZone}</span>
                              </div>
                            </div>

                            <div className="flex flex-col gap-1 text-[11px] font-sans">
                              <div className="text-emerald-300">
                                <strong className="text-emerald-400">Primary Execution Path:</strong> {plan.bullPath}
                              </div>
                              <div className="text-rose-300">
                                <strong className="text-rose-400">Risk Invalidation:</strong> {plan.bearPath}
                              </div>
                              <div className="text-slate-400 italic text-[10px] mt-0.5">
                                <strong>Macro Driver:</strong> {plan.macroDriver}
                              </div>
                            </div>
                          </div>

                          <div className="pt-2 border-t border-slate-800/80 flex items-center justify-between text-[10px] text-slate-500">
                            <span>SMC Order Block: <strong className="text-slate-300">{plan.orderBlock}</strong></span>
                            <span className="font-mono text-cyan-400">Institutional Plan Ready</span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Metrics & Epistemic Typology Chips */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
            <div className="bg-[#0b101c] p-2.5 rounded-lg border border-purple-500/30 flex flex-col">
              <span className="text-[11px] text-purple-400 font-semibold">🎯 Actionable Rules</span>
              <span className="text-lg font-extrabold text-white mt-0.5">
                {activeSummary.file_metadata?.epistemic_counts?.PROPOSED_RULE ?? activeSummary.summary.candidates_queued}
              </span>
              <span className="text-[10px] text-slate-500">Prescriptive directives</span>
            </div>

            <div className="bg-[#0b101c] p-2.5 rounded-lg border border-cyan-500/30 flex flex-col">
              <span className="text-[11px] text-cyan-400 font-semibold">📐 Market Definitions</span>
              <span className="text-lg font-extrabold text-white mt-0.5">
                {activeSummary.file_metadata?.epistemic_counts?.DEFINITION ?? activeSummary.summary.concepts_saved}
              </span>
              <span className="text-[10px] text-slate-500">Structural concepts</span>
            </div>

            <div className="bg-[#0b101c] p-2.5 rounded-lg border border-emerald-500/30 flex flex-col">
              <span className="text-[11px] text-emerald-400 font-semibold">📜 Historical Observations</span>
              <span className="text-lg font-extrabold text-white mt-0.5">
                {activeSummary.file_metadata?.epistemic_counts?.HISTORICAL_OBSERVATION ?? activeSummary.summary.evidence_saved}
              </span>
              <span className="text-[10px] text-slate-500">Regime observations</span>
            </div>

            <div className="bg-[#0b101c] p-2.5 rounded-lg border border-amber-500/30 flex flex-col">
              <span className="text-[11px] text-amber-400 font-semibold">🛡️ Quarantined Stats</span>
              <span className="text-lg font-extrabold text-amber-300 mt-0.5">
                {activeSummary.file_metadata?.epistemic_counts?.AUTHOR_REPORTED_STATISTIC ?? 0}
              </span>
              <span className="text-[10px] text-amber-400/70">Confidence: 0.0 (Anti-Hype)</span>
            </div>
          </div>

          {/* Chapters / Topics Breakdown */}
          {activeSummary.chapter_breakdown && activeSummary.chapter_breakdown.length > 0 && (
            <div className="flex flex-col gap-2">
              <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">
                Extracted Chapters & Structural Sections:
              </span>
              <div className="flex flex-wrap gap-1.5">
                {activeSummary.chapter_breakdown.map((chap, idx) => (
                  <span
                    key={idx}
                    className="px-2.5 py-1 rounded bg-[#0d1424] text-slate-300 text-xs border border-slate-800 font-medium"
                  >
                    📖 {chap}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Strategy Candidates Formulated From This Book */}
          {activeSummary.strategy_candidates && activeSummary.strategy_candidates.length > 0 && (
            <div className="flex flex-col gap-2 pt-2 border-t border-[#1e293b]">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-purple-300 uppercase tracking-wider">
                  ⚡ Formulated Strategy Hypotheses ({activeSummary.strategy_candidates.length})
                </span>
                <span className="text-[10px] text-slate-500">Ready for Strategy League validation</span>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                {activeSummary.strategy_candidates.slice(0, 4).map((cand) => (
                  <div
                    key={cand.candidate_id}
                    className="p-3 bg-[#080c16] rounded-lg border border-purple-500/30 flex flex-col justify-between gap-2"
                  >
                    <div>
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-purple-300 text-xs">{cand.strategy_name}</span>
                        <span className="text-[10px] px-1.5 py-0.5 bg-purple-950 text-purple-400 rounded border border-purple-800">
                          {cand.validation_stage}
                        </span>
                      </div>
                      <p className="text-[11px] text-slate-300 mt-1 line-clamp-2">{cand.hypothesis}</p>
                    </div>
                    <button
                      onClick={() => handleRunBacktest(cand.candidate_id)}
                      disabled={backtestingCandidateId === cand.candidate_id}
                      className="self-start px-2.5 py-1 rounded bg-purple-600 hover:bg-purple-500 text-white font-bold text-[10px] transition-all flex items-center gap-1 disabled:opacity-50"
                    >
                      <Play className="w-3 h-3" />
                      {backtestingCandidateId === cand.candidate_id ? 'Validating...' : 'Backtest on ETH/USDT'}
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
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
          <span className="text-[10px] text-slate-400">
            Showing last {inboxItems.length} sources · Click any source to read its full Summary
          </span>
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
                onClick={() => handleSelectInboxSummary(item)}
                className="p-2.5 bg-slate-950 rounded-lg border border-slate-800/80 flex flex-col justify-between gap-2 text-xs hover:border-sky-500/60 cursor-pointer transition-all hover:bg-slate-900/80 group"
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-1.5 truncate">
                    {getSourceIcon(item.source_type)}
                    <span className="font-semibold text-slate-200 group-hover:text-sky-300 transition-colors truncate">
                      {item.title}
                    </span>
                  </div>
                  <span
                    className={`px-1.5 py-0.5 text-[10px] rounded font-bold shrink-0 ${
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

                <div className="flex items-center justify-between text-[10px] text-slate-500 pt-1 border-t border-slate-900">
                  <span>ID: {item.knowledge_id}</span>
                  <span className="text-sky-400 font-medium group-hover:underline flex items-center gap-1">
                    📖 Read Summary
                  </span>
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
                        <div className="flex items-center justify-between flex-wrap gap-1">
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <span className="px-2 py-0.5 text-[10px] bg-slate-800 text-slate-300 rounded font-bold uppercase">
                              {cl.source_worldview}
                            </span>
                            {cl.pdf_evidence_type && (
                              <span className="px-1.5 py-0.5 text-[9px] bg-purple-950/80 text-purple-300 border border-purple-800/80 rounded font-mono font-semibold">
                                {cl.pdf_evidence_type}
                              </span>
                            )}
                          </div>
                          <div className="flex items-center gap-1.5 flex-wrap">
                            {cl.timestamp_start && (
                              <a
                                href={cl.video_url || '#'}
                                target="_blank"
                                rel="noreferrer"
                                className="px-2 py-0.5 text-[10px] bg-red-950/80 hover:bg-red-900 text-red-300 border border-red-800/80 rounded font-mono font-semibold flex items-center gap-1 transition-colors"
                                title="Jump to timestamp in source video"
                              >
                                <Clock className="w-3 h-3 text-red-400" />
                                <span>{cl.timestamp_start}{cl.timestamp_end ? ` - ${cl.timestamp_end}` : ''}</span>
                                <ExternalLink className="w-2.5 h-2.5 opacity-70" />
                              </a>
                            )}
                            {cl.page_number && (
                              <span
                                className="px-2 py-0.5 text-[10px] bg-cyan-950/80 text-cyan-300 border border-cyan-800/80 rounded font-mono font-semibold flex items-center gap-1"
                                title={cl.chapter_title ? `${cl.chapter_title} (Section: ${cl.section_title || 'General'})` : undefined}
                              >
                                <BookOpen className="w-3 h-3 text-cyan-400" />
                                <span>{cl.chapter_title ? `${cl.chapter_title.split(':')[0]} · ` : ''}p. {cl.page_number}</span>
                              </span>
                            )}
                            <span className="px-2 py-0.5 text-[10px] bg-amber-950 text-amber-300 border border-amber-800 rounded font-bold">
                              [{cl.epistemic_status}]
                            </span>
                          </div>
                        </div>

                        <p className="text-xs text-slate-200 italic font-sans leading-relaxed">
                          "{cl.original_claim_verbatim}"
                        </p>

                        {cl.hype_detected && (
                          <div className="flex items-center gap-1.5 px-2 py-1 bg-amber-950/40 border border-amber-800/60 rounded text-[10px] text-amber-300">
                            <ShieldAlert className="w-3.5 h-3.5 text-amber-400 shrink-0" />
                            <span><strong>Zero-Fabrication Firewall:</strong> {cl.pdf_evidence_type === 'AUTHOR_REPORTED_STATISTIC' ? 'Author-reported statistic isolated. Alpha assumption strictly 0.0 until verified.' : 'Qualitative author hype detected. Alpha assumption strictly 0.0 until verified.'}</span>
                          </div>
                        )}

                        <div className="text-[10px] text-slate-400 bg-slate-900 p-2 rounded border border-slate-800/80 flex flex-col gap-0.5">
                          <span><strong>Direction:</strong> {cl.relationship_direction}</span>
                          <span><strong>Target Domain:</strong> {cl.object_domain}</span>
                          {cl.applicability_domain && (
                            <span><strong>Applicability:</strong> {cl.applicability_domain} (Source: {cl.source_worldview})</span>
                          )}
                          {cl.book_title && (
                            <span><strong>Literature:</strong> {cl.book_title} ({cl.book_edition || '1st Ed.'}){cl.book_isbn ? ` · ISBN: ${cl.book_isbn}` : ''}</span>
                          )}
                          {cl.author_creator && (
                            <span><strong>Author/Channel:</strong> {cl.author_creator}</span>
                          )}
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
                          c.validation_stage === 'WALK_FORWARD' || c.validation_stage === 'PROMOTED' || c.validation_stage === 'PAPER_TEST'
                            ? 'bg-emerald-950 text-emerald-300 border border-emerald-700'
                            : c.validation_stage === 'DATA_INSUFFICIENT'
                            ? 'bg-amber-950 text-amber-300 border border-amber-700'
                            : c.validation_stage === 'REJECTED'
                            ? 'bg-rose-950 text-rose-300 border border-rose-700'
                            : 'bg-purple-950 text-purple-300 border border-purple-800'
                        }`}
                      >
                        {c.validation_stage === 'PAPER_TEST'
                          ? '✅ QUALIFIED & IN PAPER DESK'
                          : c.validation_stage === 'DATA_INSUFFICIENT'
                          ? '⚠️ DATA_INSUFFICIENT'
                          : `STAGE: ${c.validation_stage}`}
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
        </>
      )}
    </div>
  );
};
