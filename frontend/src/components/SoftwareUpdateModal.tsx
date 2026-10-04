import React, { useState, useEffect } from 'react';
import {
  DownloadCloud,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  X,
  GitBranch,
  ShieldCheck,
  Package,
  ExternalLink,
} from 'lucide-react';
import {
  checkSoftwareUpdate,
  applySoftwareUpdate,
  SoftwareUpdateStatus,
} from '../services/api';

interface SoftwareUpdateModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const SoftwareUpdateModal: React.FC<SoftwareUpdateModalProps> = ({ isOpen, onClose }) => {
  const [checking, setChecking] = useState(false);
  const [updating, setUpdating] = useState(false);
  const [updateStatus, setUpdateStatus] = useState<SoftwareUpdateStatus | null>(null);
  const [updateResult, setUpdateResult] = useState<{ success: boolean; message: string; new_commit?: string } | null>(null);

  const fetchUpdateCheck = async () => {
    setChecking(true);
    try {
      const status = await checkSoftwareUpdate();
      setUpdateStatus(status);
    } catch (err: any) {
      console.error('Failed to check software update:', err);
    } finally {
      setChecking(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      fetchUpdateCheck();
      setUpdateResult(null);
    }
  }, [isOpen]);

  const handleApplyUpdate = async () => {
    setUpdating(true);
    setUpdateResult(null);
    try {
      const res = await applySoftwareUpdate();
      setUpdateResult(res);
      if (res.success) {
        setTimeout(() => {
          window.location.reload();
        }, 3000);
      }
    } catch (err: any) {
      setUpdateResult({
        success: false,
        message: err.message || 'Failed to apply software update.',
      });
    } finally {
      setUpdating(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4">
      <div className="w-full max-w-lg bg-zinc-950 border border-zinc-800 rounded-xl shadow-2xl overflow-hidden flex flex-col">
        {/* Modal Header */}
        <div className="px-5 py-4 bg-zinc-900/60 border-b border-zinc-800 flex items-center justify-between">
          <div className="flex items-center space-x-2.5">
            <DownloadCloud className="w-5 h-5 text-amber-400" />
            <h2 className="text-sm font-bold text-zinc-100 tracking-wide uppercase">
              CBT Software Updater
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-zinc-500 hover:text-zinc-300 transition"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-6 space-y-5 text-zinc-300 text-xs">
          {checking ? (
            <div className="py-8 flex flex-col items-center justify-center space-y-3">
              <RefreshCw className="w-6 h-6 text-amber-400 animate-spin" />
              <p className="text-zinc-400">Checking git remote origin for software updates...</p>
            </div>
          ) : updateStatus ? (
            <div className="space-y-4">
              {/* Status Header */}
              <div className="flex items-center justify-between p-3.5 bg-zinc-900/50 rounded-lg border border-zinc-800">
                <div className="flex items-center space-x-2">
                  {updateStatus.git_managed ? (
                    <GitBranch className="w-4 h-4 text-zinc-400" />
                  ) : (
                    <Package className="w-4 h-4 text-amber-400" />
                  )}
                  <span className="font-mono text-zinc-200">
                    {updateStatus.git_managed
                      ? `Branch: ${updateStatus.branch}`
                      : 'Environment: Standalone Desktop Binary'}
                  </span>
                </div>
                <div className="font-mono text-[11px] text-zinc-400">
                  {updateStatus.git_managed ? (
                    <>HEAD: <span className="text-amber-400">{updateStatus.current_commit}</span></>
                  ) : (
                    <span className="text-emerald-400 font-semibold">{updateStatus.current_commit || 'v4.0.0'}</span>
                  )}
                </div>
              </div>

              {updateStatus.update_available ? (
                <div className="space-y-3">
                  <div className="p-3 bg-amber-400/10 border border-amber-400/20 rounded-lg flex items-start space-x-2.5 text-amber-300">
                    <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
                    <div>
                      <span className="font-bold">
                        {updateStatus.commits_behind} New Commit(s) Available!
                      </span>
                      <p className="text-[11px] text-amber-200/80 mt-0.5">
                        Latest Remote: {updateStatus.remote_commit}
                      </p>
                    </div>
                  </div>

                  {/* Changelog list */}
                  {updateStatus.changelog && updateStatus.changelog.length > 0 && (
                    <div>
                      <span className="text-[11px] font-semibold text-zinc-400 block mb-1.5 uppercase">
                        Incoming Changes:
                      </span>
                      <div className="max-h-40 overflow-y-auto space-y-1.5 p-2 bg-zinc-900/40 rounded border border-zinc-800 font-mono text-[11px]">
                        {updateStatus.changelog.map((c, idx) => (
                          <div key={idx} className="flex items-start space-x-2 text-zinc-300">
                            <span className="text-amber-400 shrink-0">{c.hash}</span>
                            <span className="truncate">{c.message}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  <div className="flex items-center space-x-2 text-[11px] text-zinc-400 bg-zinc-900/30 p-2.5 rounded border border-zinc-800/60">
                    <ShieldCheck className="w-4 h-4 text-emerald-400 shrink-0" />
                    <span>
                      Automatic pre-update snapshot backup will be created in <code className="text-zinc-300">backups/updates/</code> before pull.
                    </span>
                  </div>
                </div>
              ) : !updateStatus.git_managed ? (
                <div className="py-4 text-center space-y-2.5">
                  <Package className="w-8 h-8 text-amber-400 mx-auto" />
                  <p className="text-zinc-200 font-medium text-sm">Standalone Desktop Installation</p>
                  <p className="text-zinc-400 text-[11px] max-w-sm mx-auto leading-relaxed">
                    {updateStatus.message ||
                      'This installation runs as a compiled standalone desktop binary. Git-based auto-pull applies when running directly from the source repository.'}
                  </p>
                  <p className="text-zinc-500 text-[11px] font-mono">
                    Build: {updateStatus.current_commit || 'v4.0.0 (Production)'}
                  </p>
                  <div className="pt-2">
                    <a
                      href="https://github.com/Azimshawon/SKY/releases"
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center space-x-1.5 px-3 py-1.5 bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 border border-amber-500/30 rounded-lg text-xs transition"
                    >
                      <span>Check GitHub Releases</span>
                      <ExternalLink className="w-3.5 h-3.5" />
                    </a>
                  </div>
                </div>
              ) : (
                <div className="py-4 text-center space-y-2">
                  <CheckCircle2 className="w-8 h-8 text-emerald-400 mx-auto" />
                  <p className="text-zinc-200 font-medium">Your CBT installation is fully up to date.</p>
                  <p className="text-zinc-500 text-[11px]">Commit: {updateStatus.current_commit}</p>
                </div>
              )}

              {/* Update Result Alert */}
              {updateResult && (
                <div
                  className={`p-3 rounded-lg border text-xs flex items-center space-x-2 ${
                    updateResult.success
                      ? 'bg-emerald-950/40 border-emerald-800 text-emerald-300'
                      : 'bg-rose-950/40 border-rose-800 text-rose-300'
                  }`}
                >
                  {updateResult.success ? (
                    <CheckCircle2 className="w-4 h-4 shrink-0" />
                  ) : (
                    <AlertTriangle className="w-4 h-4 shrink-0" />
                  )}
                  <span>{updateResult.message}</span>
                </div>
              )}
            </div>
          ) : (
            <div className="py-4 text-center text-zinc-500">
              Unable to connect to software update service.
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="px-5 py-3.5 bg-zinc-900/60 border-t border-zinc-800 flex items-center justify-between">
          <button
            type="button"
            onClick={fetchUpdateCheck}
            disabled={checking || updating}
            className="px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 disabled:opacity-40 rounded text-xs text-zinc-300 flex items-center space-x-1.5 transition"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${checking ? 'animate-spin text-amber-400' : ''}`} />
            <span>Check Again</span>
          </button>

          <div className="flex items-center space-x-2">
            <button
              type="button"
              onClick={onClose}
              disabled={updating}
              className="px-3.5 py-1.5 text-xs text-zinc-400 hover:text-zinc-200 transition"
            >
              Close
            </button>
            {updateStatus?.update_available && (
              <button
                type="button"
                onClick={handleApplyUpdate}
                disabled={updating}
                className="px-4 py-1.5 bg-amber-400 hover:bg-amber-300 disabled:opacity-40 text-zinc-950 rounded text-xs font-bold flex items-center space-x-1.5 transition shadow"
              >
                {updating ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    <span>Updating...</span>
                  </>
                ) : (
                  <>
                    <DownloadCloud className="w-3.5 h-3.5" />
                    <span>Install & Restart</span>
                  </>
                )}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
