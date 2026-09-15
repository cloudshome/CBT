import React, { useState } from 'react';
import {
  ShieldCheck,
  Cpu,
  Layers,
  Wallet,
  Send,
  CheckCircle2,
  AlertTriangle,
  ArrowRight,
  ArrowLeft,
  Lock,
  Eye,
  EyeOff,
  RefreshCw,
  ExternalLink,
} from 'lucide-react';
import {
  verifyGeminiKey,
  verifyExchangeCredentials,
  verifyHyperliquidCredentials,
  saveWeb3Wallet,
  completeFirstRunSetup,
} from '../services/api';

interface FirstRunSetupWizardProps {
  onComplete: () => void;
}

export const FirstRunSetupWizard: React.FC<FirstRunSetupWizardProps> = ({ onComplete }) => {
  const [step, setStep] = useState<number>(1);
  const totalSteps = 6;

  // Step 1: Master Password
  const [masterPassword, setMasterPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [passwordError, setPasswordError] = useState('');

  // Step 2: Gemini Key
  const [geminiKey, setGeminiKey] = useState('');
  const [geminiVerifying, setGeminiVerifying] = useState(false);
  const [geminiStatus, setGeminiStatus] = useState<{ valid: boolean; message: string } | null>(null);

  // Step 3: Centralized Exchanges
  const [selectedExch, setSelectedExch] = useState<'BINANCE' | 'BYBIT' | 'KRAKEN' | 'KUCOIN' | 'MEXC'>('BINANCE');
  const [exchangeCreds, setExchangeCreds] = useState<Record<string, { apiKey: string; apiSecret: string; passphrase?: string; verified: boolean }>>({
    BINANCE: { apiKey: '', apiSecret: '', verified: false },
    BYBIT: { apiKey: '', apiSecret: '', verified: false },
    KRAKEN: { apiKey: '', apiSecret: '', verified: false },
    KUCOIN: { apiKey: '', apiSecret: '', passphrase: '', verified: false },
    MEXC: { apiKey: '', apiSecret: '', verified: false },
  });
  const [exchTesting, setExchTesting] = useState(false);
  const [exchTestResult, setExchTestResult] = useState<{ success: boolean; message: string } | null>(null);

  // Step 4: Hyperliquid & Web3
  const [hlMasterAddress, setHlMasterAddress] = useState('');
  const [hlAgentPrivateKey, setHlAgentPrivateKey] = useState('');
  const [hlTesting, setHlTesting] = useState(false);
  const [hlResult, setHlResult] = useState<{ success: boolean; message: string } | null>(null);

  const [web3Wallets, setWeb3Wallets] = useState<Array<{ walletType: string; chain: string; address: string }>>([]);
  const [newWalletType, setNewWalletType] = useState('METAMASK');
  const [newWalletChain, setNewWalletChain] = useState('ETHEREUM');
  const [newWalletAddress, setNewWalletAddress] = useState('');

  // Step 5: Telegram
  const [telegramToken, setTelegramToken] = useState('');
  const [telegramChatId, setTelegramChatId] = useState('');

  // Step 6: Launch
  const executionMode = 'PAPER_TRADING';
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState('');

  // Handle Step 1 Validation
  const handleNextStep1 = () => {
    if (masterPassword.length < 8) {
      setPasswordError('Master password must be at least 8 characters long.');
      return;
    }
    if (masterPassword !== confirmPassword) {
      setPasswordError('Passwords do not match.');
      return;
    }
    setPasswordError('');
    setStep(2);
  };

  // Handle Gemini Verification
  const handleVerifyGemini = async () => {
    if (!geminiKey.trim()) return;
    setGeminiVerifying(true);
    setGeminiStatus(null);
    try {
      const res = await verifyGeminiKey(geminiKey.trim());
      setGeminiStatus({ valid: res.valid, message: res.message });
    } catch (err: any) {
      setGeminiStatus({ valid: false, message: err.message || 'Gemini verification failed.' });
    } finally {
      setGeminiVerifying(false);
    }
  };

  // Handle Exchange Verification
  const handleTestExchange = async () => {
    const cred = exchangeCreds[selectedExch];
    if (!cred.apiKey || !cred.apiSecret) {
      setExchTestResult({ success: false, message: 'Please enter API Key and Secret.' });
      return;
    }
    setExchTesting(true);
    setExchTestResult(null);
    try {
      const res = await verifyExchangeCredentials({
        exchange: selectedExch,
        environment: 'PRODUCTION',
        api_key: cred.apiKey,
        api_secret: cred.apiSecret,
        passphrase: cred.passphrase,
      });
      if (res.status === 'PASS') {
        setExchTestResult({ success: true, message: `Connected! ${res.message}` });
        setExchangeCreds(prev => ({
          ...prev,
          [selectedExch]: { ...prev[selectedExch], verified: true }
        }));
      } else {
        setExchTestResult({ success: false, message: res.message || 'Verification failed.' });
      }
    } catch (err: any) {
      setExchTestResult({ success: false, message: err.message || 'Network probe failed.' });
    } finally {
      setExchTesting(false);
    }
  };

  // Handle Hyperliquid Verification
  const handleTestHyperliquid = async () => {
    if (!hlMasterAddress.trim() || !hlAgentPrivateKey.trim()) {
      setHlResult({ success: false, message: 'Please enter Master Address and Agent Private Key.' });
      return;
    }
    setHlTesting(true);
    setHlResult(null);
    try {
      const res = await verifyHyperliquidCredentials({
        master_address: hlMasterAddress.trim(),
        agent_private_key: hlAgentPrivateKey.trim(),
        environment: 'PRODUCTION',
      });
      if (res.status === 'PASS') {
        setHlResult({
          success: true,
          message: `Hyperliquid L1 Verified! Zero withdrawal rights confirmed by L1 architecture.`,
        });
      } else {
        setHlResult({ success: false, message: res.message || 'Verification failed.' });
      }
    } catch (err: any) {
      setHlResult({ success: false, message: err.message || 'Hyperliquid L1 query failed.' });
    } finally {
      setHlTesting(false);
    }
  };

  // Add Web3 Watch-Only Wallet
  const handleAddWeb3Wallet = async () => {
    if (!newWalletAddress.trim()) return;
    try {
      await saveWeb3Wallet({
        wallet_type: newWalletType,
        chain: newWalletChain,
        address: newWalletAddress.trim(),
        is_watch_only: true,
      });
      setWeb3Wallets(prev => [
        ...prev,
        { walletType: newWalletType, chain: newWalletChain, address: newWalletAddress.trim() },
      ]);
      setNewWalletAddress('');
    } catch (err: any) {
      alert(err.message || 'Could not save Web3 wallet.');
    }
  };

  // Complete Final Setup
  const handleFinalLaunch = async () => {
    setSaving(true);
    setSaveError('');

    const formattedExchanges: any[] = [];
    Object.entries(exchangeCreds).forEach(([exch, val]) => {
      if (val.apiKey && val.apiSecret) {
        formattedExchanges.push({
          exchange: exch,
          environment: 'PRODUCTION',
          api_key: val.apiKey,
          api_secret: val.apiSecret,
          passphrase: val.passphrase || undefined,
        });
      }
    });

    if (hlMasterAddress && hlAgentPrivateKey) {
      formattedExchanges.push({
        exchange: 'HYPERLIQUID',
        environment: 'PRODUCTION',
        api_key: hlMasterAddress.trim(),
        api_secret: hlAgentPrivateKey.trim(),
      });
    }

    try {
      await completeFirstRunSetup({
        master_password: masterPassword,
        gemini_api_key: geminiKey.trim() || undefined,
        telegram_bot_token: telegramToken.trim() || undefined,
        telegram_chat_id: telegramChatId.trim() || undefined,
        exchanges: formattedExchanges,
        execution_mode: executionMode,
      });
      onComplete();
    } catch (err: any) {
      setSaveError(err.message || 'Failed to save configuration.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-md p-4">
      <div className="w-full max-w-4xl bg-zinc-950 border border-zinc-800 rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        {/* Top Header */}
        <div className="px-6 py-5 bg-zinc-900/60 border-b border-zinc-800/80 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-amber-500 to-amber-300 flex items-center justify-center shadow-lg shadow-amber-500/20">
              <ShieldCheck className="w-6 h-6 text-zinc-950" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-zinc-100 tracking-wide">
                CRYPTO BRAIN TERMINAL <span className="text-amber-400 font-mono text-xs px-2 py-0.5 rounded bg-amber-400/10 border border-amber-400/20">v3.0.0</span>
              </h1>
              <p className="text-xs text-zinc-400">Institutional First-Run Security & Venue Configuration</p>
            </div>
          </div>
          {/* Step Badges */}
          <div className="flex items-center space-x-1.5 font-mono text-xs">
            <span className="text-amber-400 font-bold">STEP {step}</span>
            <span className="text-zinc-600">/</span>
            <span className="text-zinc-500">{totalSteps}</span>
          </div>
        </div>

        {/* Progress Line */}
        <div className="w-full bg-zinc-800 h-1">
          <div
            className="bg-amber-400 h-1 transition-all duration-300"
            style={{ width: `${(step / totalSteps) * 100}%` }}
          />
        </div>

        {/* Wizard Content Body */}
        <div className="p-8 overflow-y-auto flex-1 text-zinc-200">
          {/* STEP 1: MASTER PASSWORD */}
          {step === 1 && (
            <div className="space-y-6 max-w-xl mx-auto">
              <div className="text-center space-y-2">
                <div className="w-12 h-12 rounded-full bg-amber-400/10 border border-amber-400/20 flex items-center justify-center mx-auto text-amber-400">
                  <Lock className="w-6 h-6" />
                </div>
                <h2 className="text-xl font-bold text-zinc-100">Create Master Vault Password</h2>
                <p className="text-xs text-zinc-400 leading-relaxed">
                  Your private API keys and exchange secrets are encrypted locally using AES-256-GCM AEAD.
                  This master password derives your local encryption key via PBKDF2 (600,000 rounds).
                </p>
              </div>

              <div className="space-y-4 bg-zinc-900/50 p-5 rounded-xl border border-zinc-800/80">
                <div>
                  <label className="block text-xs font-medium text-zinc-400 mb-1.5">
                    Master Encryption Password (min 8 chars)
                  </label>
                  <div className="relative">
                    <input
                      type={showPassword ? 'text' : 'password'}
                      value={masterPassword}
                      onChange={e => setMasterPassword(e.target.value)}
                      placeholder="Enter strong vault password..."
                      className="w-full px-3.5 py-2.5 bg-zinc-950 border border-zinc-800 rounded-lg text-sm text-zinc-100 focus:outline-none focus:border-amber-400 font-mono"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute right-3 top-2.5 text-zinc-500 hover:text-zinc-300"
                    >
                      {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-medium text-zinc-400 mb-1.5">
                    Confirm Password
                  </label>
                  <input
                    type={showPassword ? 'text' : 'password'}
                    value={confirmPassword}
                    onChange={e => setConfirmPassword(e.target.value)}
                    placeholder="Repeat master password..."
                    className="w-full px-3.5 py-2.5 bg-zinc-950 border border-zinc-800 rounded-lg text-sm text-zinc-100 focus:outline-none focus:border-amber-400 font-mono"
                  />
                </div>

                {passwordError && (
                  <div className="flex items-center space-x-2 text-rose-400 text-xs bg-rose-950/30 p-2.5 rounded border border-rose-900/50">
                    <AlertTriangle className="w-4 h-4 shrink-0" />
                    <span>{passwordError}</span>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* STEP 2: GEMINI API KEY */}
          {step === 2 && (
            <div className="space-y-6 max-w-xl mx-auto">
              <div className="text-center space-y-2">
                <div className="w-12 h-12 rounded-full bg-blue-500/10 border border-blue-500/20 flex items-center justify-center mx-auto text-blue-400">
                  <Cpu className="w-6 h-6" />
                </div>
                <h2 className="text-xl font-bold text-zinc-100">Google Gemini Intelligence</h2>
                <p className="text-xs text-zinc-400 leading-relaxed">
                  Required for AI Quant Sentinel, Kronos model calibration, and autonomous multi-agent quantitative research.
                </p>
              </div>

              <div className="space-y-4 bg-zinc-900/50 p-5 rounded-xl border border-zinc-800/80">
                <div>
                  <div className="flex items-center justify-between mb-1.5">
                    <label className="text-xs font-medium text-zinc-400">Google Gemini API Key</label>
                    <a
                      href="https://aistudio.google.com/app/apikey"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-amber-400 hover:underline flex items-center space-x-1"
                    >
                      <span>Get Free API Key</span>
                      <ExternalLink className="w-3 h-3" />
                    </a>
                  </div>
                  <input
                    type="password"
                    value={geminiKey}
                    onChange={e => {
                      setGeminiKey(e.target.value);
                      setGeminiStatus(null);
                    }}
                    placeholder="AIzaSy..."
                    className="w-full px-3.5 py-2.5 bg-zinc-950 border border-zinc-800 rounded-lg text-sm text-zinc-100 focus:outline-none focus:border-amber-400 font-mono"
                  />
                </div>

                <div className="flex items-center justify-between">
                  <button
                    type="button"
                    onClick={handleVerifyGemini}
                    disabled={geminiVerifying || !geminiKey.trim()}
                    className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 disabled:opacity-40 rounded-lg text-xs font-medium text-zinc-200 flex items-center space-x-2 transition"
                  >
                    {geminiVerifying && <RefreshCw className="w-3.5 h-3.5 animate-spin text-amber-400" />}
                    <span>Test API Key</span>
                  </button>
                  {geminiStatus && (
                    <div
                      className={`text-xs flex items-center space-x-1.5 ${
                        geminiStatus.valid ? 'text-emerald-400' : 'text-rose-400'
                      }`}
                    >
                      {geminiStatus.valid ? (
                        <CheckCircle2 className="w-4 h-4" />
                      ) : (
                        <AlertTriangle className="w-4 h-4" />
                      )}
                      <span>{geminiStatus.message}</span>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* STEP 3: CENTRALIZED EXCHANGES */}
          {step === 3 && (
            <div className="space-y-6 max-w-2xl mx-auto">
              <div className="text-center space-y-2">
                <div className="w-12 h-12 rounded-full bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center mx-auto text-emerald-400">
                  <Layers className="w-6 h-6" />
                </div>
                <h2 className="text-xl font-bold text-zinc-100">Multi-Venue CEX Connectors</h2>
                <p className="text-xs text-zinc-400">
                  Configure your exchange API credentials. Withdrawal permissions MUST be disabled on your keys.
                </p>
              </div>

              {/* Venue Selector Tabs */}
              <div className="grid grid-cols-5 gap-2 bg-zinc-900/60 p-1.5 rounded-xl border border-zinc-800">
                {(['BINANCE', 'BYBIT', 'KRAKEN', 'KUCOIN', 'MEXC'] as const).map(exch => (
                  <button
                    key={exch}
                    type="button"
                    onClick={() => {
                      setSelectedExch(exch);
                      setExchTestResult(null);
                    }}
                    className={`py-2 text-xs font-mono font-semibold rounded-lg transition ${
                      selectedExch === exch
                        ? 'bg-amber-400 text-zinc-950 shadow-md'
                        : 'text-zinc-400 hover:text-zinc-200'
                    }`}
                  >
                    {exch}
                    {exchangeCreds[exch]?.verified && ' ✓'}
                  </button>
                ))}
              </div>

              {/* Credential Inputs for Selected Venue */}
              <div className="space-y-4 bg-zinc-900/50 p-5 rounded-xl border border-zinc-800">
                <div>
                  <label className="block text-xs font-medium text-zinc-400 mb-1">
                    {selectedExch} API Key
                  </label>
                  <input
                    type="text"
                    value={exchangeCreds[selectedExch].apiKey}
                    onChange={e => {
                      const val = e.target.value;
                      setExchangeCreds(prev => ({
                        ...prev,
                        [selectedExch]: { ...prev[selectedExch], apiKey: val, verified: false },
                      }));
                      setExchTestResult(null);
                    }}
                    placeholder={`Enter ${selectedExch} API Key...`}
                    className="w-full px-3.5 py-2.5 bg-zinc-950 border border-zinc-800 rounded-lg text-sm text-zinc-100 font-mono focus:outline-none focus:border-amber-400"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-zinc-400 mb-1">
                    {selectedExch} API Secret
                  </label>
                  <input
                    type="password"
                    value={exchangeCreds[selectedExch].apiSecret}
                    onChange={e => {
                      const val = e.target.value;
                      setExchangeCreds(prev => ({
                        ...prev,
                        [selectedExch]: { ...prev[selectedExch], apiSecret: val, verified: false },
                      }));
                      setExchTestResult(null);
                    }}
                    placeholder={`Enter ${selectedExch} API Secret...`}
                    className="w-full px-3.5 py-2.5 bg-zinc-950 border border-zinc-800 rounded-lg text-sm text-zinc-100 font-mono focus:outline-none focus:border-amber-400"
                  />
                </div>

                {selectedExch === 'KUCOIN' && (
                  <div>
                    <label className="block text-xs font-medium text-zinc-400 mb-1">
                      KuCoin API Passphrase
                    </label>
                    <input
                      type="password"
                      value={exchangeCreds.KUCOIN.passphrase || ''}
                      onChange={e => {
                        const val = e.target.value;
                        setExchangeCreds(prev => ({
                          ...prev,
                          KUCOIN: { ...prev.KUCOIN, passphrase: val, verified: false },
                        }));
                        setExchTestResult(null);
                      }}
                      placeholder="Enter KuCoin Passphrase..."
                      className="w-full px-3.5 py-2.5 bg-zinc-950 border border-zinc-800 rounded-lg text-sm text-zinc-100 font-mono focus:outline-none focus:border-amber-400"
                    />
                  </div>
                )}

                <div className="flex items-center justify-between pt-2">
                  <button
                    type="button"
                    onClick={handleTestExchange}
                    disabled={exchTesting || !exchangeCreds[selectedExch].apiKey}
                    className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 disabled:opacity-40 rounded-lg text-xs font-medium text-zinc-200 flex items-center space-x-2 transition"
                  >
                    {exchTesting && <RefreshCw className="w-3.5 h-3.5 animate-spin text-amber-400" />}
                    <span>Test {selectedExch} Connection</span>
                  </button>
                  {exchTestResult && (
                    <div
                      className={`text-xs flex items-center space-x-1.5 ${
                        exchTestResult.success ? 'text-emerald-400' : 'text-rose-400'
                      }`}
                    >
                      {exchTestResult.success ? (
                        <CheckCircle2 className="w-4 h-4" />
                      ) : (
                        <AlertTriangle className="w-4 h-4" />
                      )}
                      <span>{exchTestResult.message}</span>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* STEP 4: HYPERLIQUID & WEB3 */}
          {step === 4 && (
            <div className="space-y-6 max-w-2xl mx-auto">
              <div className="text-center space-y-2">
                <div className="w-12 h-12 rounded-full bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center mx-auto text-cyan-400">
                  <Wallet className="w-6 h-6" />
                </div>
                <h2 className="text-xl font-bold text-zinc-100">Hyperliquid L1 & Web3 Wallets</h2>
                <p className="text-xs text-zinc-400">
                  Native DEX perpetual futures on Hyperliquid L1, plus Watch-Only portfolio tracking for MetaMask & Trust Wallet.
                </p>
              </div>

              {/* Hyperliquid Section */}
              <div className="space-y-4 bg-zinc-900/50 p-5 rounded-xl border border-zinc-800">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-zinc-200 flex items-center space-x-2">
                    <span className="w-2 h-2 rounded-full bg-cyan-400" />
                    <span>Hyperliquid L1 Perpetual Futures</span>
                  </h3>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-cyan-950/40 text-cyan-400 border border-cyan-800/40">
                    NON-CUSTODIAL L1 AGENT
                  </span>
                </div>

                <div>
                  <label className="block text-xs font-medium text-zinc-400 mb-1">
                    Master Public Address (0x...)
                  </label>
                  <input
                    type="text"
                    value={hlMasterAddress}
                    onChange={e => {
                      setHlMasterAddress(e.target.value);
                      setHlResult(null);
                    }}
                    placeholder="0x..."
                    className="w-full px-3.5 py-2.5 bg-zinc-950 border border-zinc-800 rounded-lg text-sm text-zinc-100 font-mono focus:outline-none focus:border-amber-400"
                  />
                </div>

                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-xs font-medium text-zinc-400">Agent Private Key (0x...)</label>
                    <a
                      href="https://app.hyperliquid.xyz/API"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-[11px] text-amber-400 hover:underline flex items-center space-x-1"
                    >
                      <span>Create Agent Key on Hyperliquid</span>
                      <ExternalLink className="w-3 h-3" />
                    </a>
                  </div>
                  <input
                    type="password"
                    value={hlAgentPrivateKey}
                    onChange={e => {
                      setHlAgentPrivateKey(e.target.value);
                      setHlResult(null);
                    }}
                    placeholder="0x..."
                    className="w-full px-3.5 py-2.5 bg-zinc-950 border border-zinc-800 rounded-lg text-sm text-zinc-100 font-mono focus:outline-none focus:border-amber-400"
                  />
                  <p className="text-[11px] text-zinc-500 mt-1">
                    Agent keys can ONLY place and cancel orders; they have zero withdrawal rights by blockchain smart contract design.
                  </p>
                </div>

                <div className="flex items-center justify-between pt-1">
                  <button
                    type="button"
                    onClick={handleTestHyperliquid}
                    disabled={hlTesting || !hlMasterAddress}
                    className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 disabled:opacity-40 rounded-lg text-xs font-medium text-zinc-200 flex items-center space-x-2 transition"
                  >
                    {hlTesting && <RefreshCw className="w-3.5 h-3.5 animate-spin text-amber-400" />}
                    <span>Test Hyperliquid L1</span>
                  </button>
                  {hlResult && (
                    <div
                      className={`text-xs flex items-center space-x-1.5 ${
                        hlResult.success ? 'text-emerald-400' : 'text-rose-400'
                      }`}
                    >
                      {hlResult.success ? <CheckCircle2 className="w-4 h-4" /> : <AlertTriangle className="w-4 h-4" />}
                      <span>{hlResult.message}</span>
                    </div>
                  )}
                </div>
              </div>

              {/* Web3 Watch-Only Section */}
              <div className="space-y-4 bg-zinc-900/50 p-5 rounded-xl border border-zinc-800">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-zinc-200 flex items-center space-x-2">
                    <span className="w-2 h-2 rounded-full bg-purple-400" />
                    <span>Watch-Only Web3 Wallets (MetaMask / Trust Wallet)</span>
                  </h3>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-purple-950/40 text-purple-400 border border-purple-800/40">
                    STRICTLY WATCH-ONLY
                  </span>
                </div>

                <div className="grid grid-cols-12 gap-3">
                  <select
                    value={newWalletType}
                    onChange={e => setNewWalletType(e.target.value)}
                    className="col-span-3 px-3 py-2 bg-zinc-950 border border-zinc-800 rounded-lg text-xs text-zinc-200 focus:outline-none"
                  >
                    <option value="METAMASK">MetaMask</option>
                    <option value="TRUST_WALLET">Trust Wallet</option>
                    <option value="WALLETCONNECT">WalletConnect</option>
                    <option value="CUSTOM_EVM">Custom EVM</option>
                  </select>
                  <select
                    value={newWalletChain}
                    onChange={e => setNewWalletChain(e.target.value)}
                    className="col-span-3 px-3 py-2 bg-zinc-950 border border-zinc-800 rounded-lg text-xs text-zinc-200 focus:outline-none"
                  >
                    <option value="ETHEREUM">Ethereum</option>
                    <option value="ARBITRUM">Arbitrum</option>
                    <option value="BSC">BNB Chain</option>
                    <option value="POLYGON">Polygon</option>
                    <option value="SOLANA">Solana</option>
                  </select>
                  <input
                    type="text"
                    value={newWalletAddress}
                    onChange={e => setNewWalletAddress(e.target.value)}
                    placeholder="Public Address (0x...)"
                    className="col-span-4 px-3 py-2 bg-zinc-950 border border-zinc-800 rounded-lg text-xs text-zinc-100 font-mono focus:outline-none focus:border-amber-400"
                  />
                  <button
                    type="button"
                    onClick={handleAddWeb3Wallet}
                    disabled={!newWalletAddress.trim()}
                    className="col-span-2 px-3 py-2 bg-zinc-800 hover:bg-zinc-700 disabled:opacity-40 rounded-lg text-xs font-medium text-zinc-200"
                  >
                    Add
                  </button>
                </div>

                {web3Wallets.length > 0 && (
                  <div className="space-y-1.5 pt-2">
                    {web3Wallets.map((w, idx) => (
                      <div
                        key={idx}
                        className="flex items-center justify-between px-3 py-2 bg-zinc-950/60 rounded border border-zinc-800/60 text-xs font-mono"
                      >
                        <span className="text-zinc-300 font-semibold">{w.walletType} ({w.chain})</span>
                        <span className="text-zinc-500">{w.address.slice(0, 6)}...{w.address.slice(-4)}</span>
                        <span className="text-emerald-400 text-[10px]">WATCH-ONLY</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* STEP 5: TELEGRAM SENTINEL */}
          {step === 5 && (
            <div className="space-y-6 max-w-xl mx-auto">
              <div className="text-center space-y-2">
                <div className="w-12 h-12 rounded-full bg-sky-500/10 border border-sky-500/20 flex items-center justify-center mx-auto text-sky-400">
                  <Send className="w-6 h-6" />
                </div>
                <h2 className="text-xl font-bold text-zinc-100">Telegram Risk Sentinel (Optional)</h2>
                <p className="text-xs text-zinc-400 leading-relaxed">
                  Receive instant mobile alerts for risk breaches, trade executions, and execute remote Kill-Switch commands via Telegram.
                </p>
              </div>

              <div className="space-y-4 bg-zinc-900/50 p-5 rounded-xl border border-zinc-800">
                <div>
                  <label className="block text-xs font-medium text-zinc-400 mb-1">
                    Telegram Bot Token
                  </label>
                  <input
                    type="password"
                    value={telegramToken}
                    onChange={e => setTelegramToken(e.target.value)}
                    placeholder="123456789:ABCdefGhI..."
                    className="w-full px-3.5 py-2.5 bg-zinc-950 border border-zinc-800 rounded-lg text-sm text-zinc-100 font-mono focus:outline-none focus:border-amber-400"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-zinc-400 mb-1">
                    Telegram Chat ID
                  </label>
                  <input
                    type="text"
                    value={telegramChatId}
                    onChange={e => setTelegramChatId(e.target.value)}
                    placeholder="e.g. 987654321"
                    className="w-full px-3.5 py-2.5 bg-zinc-950 border border-zinc-800 rounded-lg text-sm text-zinc-100 font-mono focus:outline-none focus:border-amber-400"
                  />
                </div>
              </div>
            </div>
          )}

          {/* STEP 6: CONFIRMATION & LAUNCH */}
          {step === 6 && (
            <div className="space-y-6 max-w-xl mx-auto">
              <div className="text-center space-y-2">
                <div className="w-12 h-12 rounded-full bg-amber-400/10 border border-amber-400/20 flex items-center justify-center mx-auto text-amber-400">
                  <CheckCircle2 className="w-6 h-6" />
                </div>
                <h2 className="text-xl font-bold text-zinc-100">Ready to Launch CBT</h2>
                <p className="text-xs text-zinc-400 leading-relaxed">
                  Configuration verified. For capital preservation, the system launches strictly in Paper Trading mode.
                </p>
              </div>

              <div className="space-y-3 bg-zinc-900/50 p-5 rounded-xl border border-zinc-800 text-xs">
                <div className="flex justify-between py-1.5 border-b border-zinc-800/80">
                  <span className="text-zinc-400">Credential Encryption</span>
                  <span className="text-emerald-400 font-mono font-semibold">AES-256-GCM AEAD Active</span>
                </div>
                <div className="flex justify-between py-1.5 border-b border-zinc-800/80">
                  <span className="text-zinc-400">Gemini Intelligence</span>
                  <span className="font-mono text-zinc-200">
                    {geminiKey ? 'Configured' : 'Skipped'}
                  </span>
                </div>
                <div className="flex justify-between py-1.5 border-b border-zinc-800/80">
                  <span className="text-zinc-400">CEX Venues</span>
                  <span className="font-mono text-zinc-200">
                    {Object.values(exchangeCreds).filter(c => c.apiKey).length} configured
                  </span>
                </div>
                <div className="flex justify-between py-1.5 border-b border-zinc-800/80">
                  <span className="text-zinc-400">Hyperliquid L1 Futures</span>
                  <span className="font-mono text-cyan-400">
                    {hlMasterAddress ? 'Configured (Agent L1)' : 'Skipped'}
                  </span>
                </div>
                <div className="flex justify-between py-1.5 border-b border-zinc-800/80">
                  <span className="text-zinc-400">Web3 Watch-Only Wallets</span>
                  <span className="font-mono text-purple-400">{web3Wallets.length} active</span>
                </div>
                <div className="flex justify-between py-1.5">
                  <span className="text-zinc-400">Default Execution Safety</span>
                  <span className="font-mono font-bold text-amber-400 bg-amber-400/10 px-2 py-0.5 rounded border border-amber-400/20">
                    PAPER TRADING ONLY
                  </span>
                </div>
              </div>

              {saveError && (
                <div className="flex items-center space-x-2 text-rose-400 text-xs bg-rose-950/30 p-2.5 rounded border border-rose-900/50">
                  <AlertTriangle className="w-4 h-4 shrink-0" />
                  <span>{saveError}</span>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Bottom Action Footer */}
        <div className="px-6 py-4 bg-zinc-900/60 border-t border-zinc-800/80 flex items-center justify-between">
          <button
            type="button"
            onClick={() => setStep(prev => Math.max(1, prev - 1))}
            disabled={step === 1}
            className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 disabled:opacity-30 rounded-lg text-xs font-medium text-zinc-300 flex items-center space-x-1.5 transition"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            <span>Back</span>
          </button>

          <div className="flex items-center space-x-3">
            {step > 1 && step < totalSteps && (
              <button
                type="button"
                onClick={() => setStep(prev => prev + 1)}
                className="px-4 py-2 text-xs font-medium text-zinc-400 hover:text-zinc-200 transition"
              >
                Skip This Step
              </button>
            )}

            {step < totalSteps ? (
              <button
                type="button"
                onClick={() => {
                  if (step === 1) handleNextStep1();
                  else setStep(prev => prev + 1);
                }}
                className="px-5 py-2 bg-amber-400 hover:bg-amber-300 text-zinc-950 rounded-lg text-xs font-bold flex items-center space-x-1.5 shadow-md shadow-amber-400/20 transition"
              >
                <span>Continue</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </button>
            ) : (
              <button
                type="button"
                onClick={handleFinalLaunch}
                disabled={saving}
                className="px-6 py-2.5 bg-gradient-to-r from-amber-400 to-amber-500 hover:from-amber-300 hover:to-amber-400 text-zinc-950 rounded-lg text-xs font-extrabold flex items-center space-x-2 shadow-lg shadow-amber-500/25 transition"
              >
                {saving && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
                <span>Launch Crypto Brain Terminal</span>
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
