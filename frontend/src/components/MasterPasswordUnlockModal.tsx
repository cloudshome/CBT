import React, { useState } from 'react';
import { Lock, Eye, EyeOff, RefreshCw, AlertTriangle, ArrowRight, ShieldCheck } from 'lucide-react';
import { verifyMasterPassword } from '../services/api';

interface MasterPasswordUnlockModalProps {
  onUnlock: () => void;
}

export const MasterPasswordUnlockModal: React.FC<MasterPasswordUnlockModalProps> = ({ onUnlock }) => {
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleUnlock = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!password.trim()) {
      setError('Please enter your master vault password.');
      return;
    }

    setLoading(true);
    setError('');

    try {
      const res = await verifyMasterPassword(password);
      if (res.valid) {
        onUnlock();
      } else {
        setError(res.message || 'Incorrect password.');
      }
    } catch (err: any) {
      setError(err.message || 'Incorrect master password. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 backdrop-blur-md p-4 animate-in fade-in duration-200">
      <div className="w-full max-w-md bg-zinc-950 border border-zinc-800 rounded-2xl shadow-2xl overflow-hidden flex flex-col">
        {/* Top Header */}
        <div className="px-6 py-4 bg-zinc-900/60 border-b border-zinc-800/80 flex items-center justify-between">
          <div className="flex items-center space-x-2.5">
            <div className="p-1.5 rounded-lg bg-amber-400/10 border border-amber-400/20 text-amber-400">
              <ShieldCheck className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <span className="font-bold text-xs tracking-wider text-zinc-100 uppercase">
                  Crypto Brain Terminal
                </span>
                <span className="text-[10px] bg-amber-400/10 text-amber-400 border border-amber-400/20 px-1.5 py-0.2 rounded font-mono">
                  v4.0.0
                </span>
              </div>
              <p className="text-[11px] text-zinc-400">Institutional Session Security</p>
            </div>
          </div>
        </div>

        {/* Form Body */}
        <form onSubmit={handleUnlock} className="p-6 space-y-5">
          <div className="text-center space-y-1.5 pt-2">
            <div className="w-12 h-12 rounded-full bg-amber-400/10 border border-amber-400/20 flex items-center justify-center mx-auto text-amber-400 mb-3">
              <Lock className="w-6 h-6" />
            </div>
            <h2 className="text-lg font-bold text-zinc-100">Unlock Terminal</h2>
            <p className="text-xs text-zinc-400">
              Enter your master vault password to unlock your workspace.
            </p>
          </div>

          <div className="space-y-2">
            <label className="block text-xs font-semibold text-zinc-300">
              Master Vault Password
            </label>
            <div className="relative">
              <input
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => {
                  setPassword(e.target.value);
                  if (error) setError('');
                }}
                autoFocus
                placeholder="Enter master password..."
                className="w-full px-3.5 py-2.5 bg-zinc-900/80 border border-zinc-800 rounded-lg text-sm text-zinc-100 focus:outline-none focus:border-amber-400 font-mono pr-10"
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

          {error && (
            <div className="flex items-center space-x-2 text-rose-400 text-xs bg-rose-950/30 p-2.5 rounded-lg border border-rose-900/50">
              <AlertTriangle className="w-4 h-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <button
            type="submit"
            disabled={loading || !password.trim()}
            className="w-full py-2.5 bg-gradient-to-r from-amber-400 to-amber-500 hover:from-amber-300 hover:to-amber-400 disabled:opacity-40 text-zinc-950 rounded-lg text-xs font-bold flex items-center justify-center space-x-1.5 shadow-md shadow-amber-400/20 transition"
          >
            {loading ? (
              <RefreshCw className="w-4 h-4 animate-spin" />
            ) : (
              <>
                <span>Unlock CBT</span>
                <ArrowRight className="w-4 h-4" />
              </>
            )}
          </button>
        </form>
      </div>
    </div>
  );
};
