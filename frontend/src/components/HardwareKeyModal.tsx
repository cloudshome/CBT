import React, { useState, useEffect } from 'react';
import {
  Shield,
  Key,
  Lock,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  X,
  Clock,
  Trash2,
  PlusCircle,
  Fingerprint,
} from 'lucide-react';
import {
  getHardwareKeyStatus,
  getHardwareKeyAuthOptions,
  verifyHardwareKeyAuth,
  getHardwareKeyRegisterOptions,
  verifyHardwareKeyRegister,
  revokeHardwareKeyCredential,
  revokeHardwareKeyClearance,
  HardwareKeyPosture,
  ClearanceSessionData,
} from '../services/api';

interface HardwareKeyModalProps {
  isOpen: boolean;
  onClose: () => void;
  onClearanceGranted?: (clearance: ClearanceSessionData) => void;
  sessionId?: string;
}

// ---------------------------------------------------------------------------
// Base64URL Helpers for WebAuthn in Browser
// ---------------------------------------------------------------------------
function bufferToBase64Url(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function base64UrlToBuffer(base64url: string): ArrayBuffer {
  const padding = '='.repeat((4 - (base64url.length % 4)) % 4);
  const base64 = (base64url + padding).replace(/-/g, '+').replace(/_/g, '/');
  const rawData = atob(base64);
  const outputArray = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray.buffer;
}

export const HardwareKeyModal: React.FC<HardwareKeyModalProps> = ({
  isOpen,
  onClose,
  onClearanceGranted,
  sessionId = 'desktop_session',
}) => {
  const [activeTab, setActiveTab] = useState<'clearance' | 'enrollment'>('clearance');
  const [posture, setPosture] = useState<HardwareKeyPosture | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [authenticating, setAuthenticating] = useState<boolean>(false);
  const [enrolling, setEnrolling] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [newKeyLabel, setNewKeyLabel] = useState<string>('YubiKey / Security Key');
  const [remainingSeconds, setRemainingSeconds] = useState<number>(0);

  const fetchStatus = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await getHardwareKeyStatus(sessionId);
      setPosture(res.posture);
      if (res.posture.clearance_session) {
        setRemainingSeconds(res.posture.clearance_session.remaining_seconds);
      }
    } catch (err: any) {
      setError(err.message || 'Failed to fetch security key status');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      fetchStatus();
      setError(null);
      setSuccessMsg(null);
    }
  }, [isOpen, sessionId]);

  // Countdown timer for active clearance
  useEffect(() => {
    if (remainingSeconds <= 0) return;
    const interval = setInterval(() => {
      setRemainingSeconds((prev) => Math.max(0, prev - 1));
    }, 1000);
    return () => clearInterval(interval);
  }, [remainingSeconds]);

  if (!isOpen) return null;

  // -------------------------------------------------------------------------
  // Action 1: Authenticate Physical Security Key for Live Clearance
  // -------------------------------------------------------------------------
  const handleAuthenticateKey = async () => {
    try {
      setAuthenticating(true);
      setError(null);
      setSuccessMsg(null);

      if (!window.PublicKeyCredential) {
        throw new Error('WebAuthn is not supported in this browser/environment.');
      }

      // 1. Fetch challenge from backend
      const optionsRes = await getHardwareKeyAuthOptions();
      const { challenge_id, options } = optionsRes;

      // 2. Format options for navigator.credentials.get
      const publicKeyOptions: PublicKeyCredentialRequestOptions = {
        challenge: base64UrlToBuffer(options.challenge),
        rpId: options.rpId,
        timeout: options.timeout || 60000,
        userVerification: options.userVerification || 'preferred',
        allowCredentials: (options.allowCredentials || []).map((c: any) => ({
          id: base64UrlToBuffer(c.id),
          type: c.type || 'public-key',
          transports: c.transports,
        })),
      };

      // 3. Prompt user for physical touch
      const assertion = (await navigator.credentials.get({
        publicKey: publicKeyOptions,
      })) as PublicKeyCredential;

      if (!assertion) {
        throw new Error('WebAuthn ceremony was aborted or cancelled.');
      }

      const response = assertion.response as AuthenticatorAssertionResponse;

      // 4. Serialize assertion response
      const credentialPayload = {
        id: assertion.id,
        rawId: bufferToBase64Url(assertion.rawId),
        type: assertion.type,
        response: {
          clientDataJSON: bufferToBase64Url(response.clientDataJSON),
          authenticatorData: bufferToBase64Url(response.authenticatorData),
          signature: bufferToBase64Url(response.signature),
          userHandle: response.userHandle ? bufferToBase64Url(response.userHandle) : null,
        },
      };

      // 5. Verify on backend & issue session-bound clearance
      const verifyRes = await verifyHardwareKeyAuth(
        challenge_id,
        credentialPayload,
        sessionId,
        'default_operator'
      );

      setSuccessMsg('Physical security key verified! Live Execution Clearance granted.');
      setRemainingSeconds(verifyRes.clearance.remaining_seconds);
      await fetchStatus();

      if (onClearanceGranted) {
        onClearanceGranted(verifyRes.clearance);
      }
    } catch (err: any) {
      if (err.name === 'NotAllowedError') {
        setError('Security key touch timed out or was cancelled by user.');
      } else {
        setError(err.message || 'Authentication failed');
      }
    } finally {
      setAuthenticating(false);
    }
  };

  // -------------------------------------------------------------------------
  // Enrollment Ceremony
  // -------------------------------------------------------------------------
  const handleEnrollKey = async () => {
    try {
      setEnrolling(true);
      setError(null);
      setSuccessMsg(null);

      if (!window.PublicKeyCredential) {
        throw new Error('WebAuthn is not supported in this browser/environment.');
      }

      // 1. Fetch registration options
      const optionsRes = await getHardwareKeyRegisterOptions(
        'default_operator',
        'operator',
        'CBT Operator'
      );
      const { challenge_id, options } = optionsRes;

      // 2. Format options for navigator.credentials.create
      const publicKeyOptions: PublicKeyCredentialCreationOptions = {
        challenge: base64UrlToBuffer(options.challenge),
        rp: options.rp,
        user: {
          id: base64UrlToBuffer(options.user.id),
          name: options.user.name,
          displayName: options.user.displayName,
        },
        pubKeyCredParams: options.pubKeyCredParams,
        timeout: options.timeout || 60000,
        authenticatorSelection: options.authenticatorSelection,
        excludeCredentials: (options.excludeCredentials || []).map((c: any) => ({
          id: base64UrlToBuffer(c.id),
          type: c.type || 'public-key',
        })),
      };

      // 3. Prompt user to touch new key
      const credential = (await navigator.credentials.create({
        publicKey: publicKeyOptions,
      })) as PublicKeyCredential;

      if (!credential) {
        throw new Error('Registration ceremony was aborted.');
      }

      const response = credential.response as AuthenticatorAttestationResponse;

      // 4. Serialize attestation
      const credentialPayload = {
        id: credential.id,
        rawId: bufferToBase64Url(credential.rawId),
        type: credential.type,
        response: {
          clientDataJSON: bufferToBase64Url(response.clientDataJSON),
          attestationObject: bufferToBase64Url(response.attestationObject),
          transports: response.getTransports ? response.getTransports() : [],
        },
      };

      // 5. Send to backend for verification & storage in security.db
      await verifyHardwareKeyRegister(
        challenge_id,
        credentialPayload,
        newKeyLabel,
        'default_operator'
      );

      setSuccessMsg(`Security key '${newKeyLabel}' enrolled successfully!`);
      await fetchStatus();
      setActiveTab('clearance');
    } catch (err: any) {
      if (err.name === 'NotAllowedError') {
        setError('Key registration was cancelled or timed out.');
      } else {
        setError(err.message || 'Enrollment failed');
      }
    } finally {
      setEnrolling(false);
    }
  };

  const handleRevokeCredential = async (credentialId: string) => {
    if (!confirm('Are you sure you want to revoke this security key? It will immediately terminate all active clearances.')) {
      return;
    }
    try {
      setLoading(true);
      await revokeHardwareKeyCredential(credentialId, 'OPERATOR_REVOCATION');
      setSuccessMsg('Security key successfully revoked.');
      await fetchStatus();
    } catch (err: any) {
      setError(err.message || 'Failed to revoke key');
    } finally {
      setLoading(false);
    }
  };

  const handleRevokeClearance = async () => {
    try {
      setLoading(true);
      await revokeHardwareKeyClearance(sessionId, undefined, 'OPERATOR_MANUAL_LOCK');
      setSuccessMsg('Live clearance revoked. System returned to Paper mode.');
      await fetchStatus();
    } catch (err: any) {
      setError(err.message || 'Failed to revoke clearance');
    } finally {
      setLoading(false);
    }
  };

  const formatRemaining = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs < 10 ? '0' : ''}${secs}`;
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
      <div className="relative w-full max-w-xl rounded-2xl border border-slate-800 bg-slate-950 p-6 shadow-2xl text-slate-100">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-800/80 pb-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-amber-500/10 text-amber-400 border border-amber-500/20">
              <Shield className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-lg font-bold tracking-tight text-white flex items-center gap-2">
                Human Live Execution Clearance
                <span className="text-xs font-mono font-normal px-2 py-0.5 rounded bg-rose-500/10 text-rose-400 border border-rose-500/20">
                  CLASS H BOUNDARY
                </span>
              </h2>
              <p className="text-xs text-slate-400">
                Physical Hardware Key (WebAuthn / FIDO2) Verification
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-white transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Tab Switcher */}
        <div className="flex border-b border-slate-800/80 mt-4">
          <button
            onClick={() => setActiveTab('clearance')}
            className={`flex items-center gap-2 px-4 py-2.5 text-xs font-semibold border-b-2 transition-all ${
              activeTab === 'clearance'
                ? 'border-amber-400 text-amber-300 bg-amber-500/5'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <Key className="h-3.5 w-3.5" />
            Live Clearance
            {remainingSeconds > 0 && (
              <span className="ml-1.5 px-1.5 py-0.2 rounded bg-emerald-500/20 text-emerald-300 font-mono text-[10px]">
                {formatRemaining(remainingSeconds)}
              </span>
            )}
          </button>
          <button
            onClick={() => setActiveTab('enrollment')}
            className={`flex items-center gap-2 px-4 py-2.5 text-xs font-semibold border-b-2 transition-all ${
              activeTab === 'enrollment'
                ? 'border-amber-400 text-amber-300 bg-amber-500/5'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <PlusCircle className="h-3.5 w-3.5" />
            Manage & Enroll Keys ({posture?.registered_keys_count || 0})
          </button>
        </div>

        {/* Notifications */}
        {error && (
          <div className="mt-4 flex items-start gap-2.5 rounded-lg border border-rose-500/30 bg-rose-950/40 p-3 text-xs text-rose-300">
            <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5 text-rose-400" />
            <span>{error}</span>
          </div>
        )}
        {successMsg && (
          <div className="mt-4 flex items-start gap-2.5 rounded-lg border border-emerald-500/30 bg-emerald-950/40 p-3 text-xs text-emerald-300">
            <CheckCircle2 className="h-4 w-4 shrink-0 mt-0.5 text-emerald-400" />
            <span>{successMsg}</span>
          </div>
        )}

        {/* Body Content */}
        <div className="py-5">
          {activeTab === 'clearance' ? (
            <div className="space-y-5">
              {/* Clearance Status Card */}
              <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div
                      className={`h-3 w-3 rounded-full ${
                        remainingSeconds > 0
                          ? 'bg-emerald-400 animate-pulse ring-4 ring-emerald-500/20'
                          : 'bg-slate-600'
                      }`}
                    />
                    <div>
                      <div className="text-sm font-semibold text-white flex items-center gap-2">
                        {remainingSeconds > 0
                          ? 'Live Execution Clearance Active'
                          : 'No Active Live Clearance'}
                      </div>
                      <div className="text-xs text-slate-400 font-mono mt-0.5">
                        {remainingSeconds > 0
                          ? `Session expires in ${formatRemaining(remainingSeconds)}`
                          : 'Hardware security key tap required to authorize real capital orders'}
                      </div>
                    </div>
                  </div>

                  {remainingSeconds > 0 && (
                    <button
                      onClick={handleRevokeClearance}
                      disabled={loading}
                      className="px-3 py-1.5 rounded-lg bg-rose-500/10 text-rose-400 border border-rose-500/20 text-xs font-medium hover:bg-rose-500/20 transition-all"
                    >
                      Revoke Clearance
                    </button>
                  )}
                </div>
              </div>

              {/* Physical Tap Ceremony Prompt */}
              <div className="flex flex-col items-center justify-center p-6 border border-slate-800/80 rounded-xl bg-slate-900/20 text-center">
                <div className="relative mb-4">
                  {authenticating && (
                    <div className="absolute -inset-2 rounded-full bg-amber-500/20 animate-ping" />
                  )}
                  <div
                    className={`flex h-16 w-16 items-center justify-center rounded-full border transition-all ${
                      authenticating
                        ? 'border-amber-400 bg-amber-500/10 text-amber-300 ring-8 ring-amber-500/10'
                        : 'border-slate-700 bg-slate-800/60 text-slate-300'
                    }`}
                  >
                    {authenticating ? (
                      <Fingerprint className="h-8 w-8 animate-pulse text-amber-400" />
                    ) : (
                      <Key className="h-8 w-8" />
                    )}
                  </div>
                </div>

                <h3 className="text-sm font-bold text-white mb-1">
                  {authenticating ? 'Touch Your Security Key Now' : 'Action 1: Verify Physical Key Possession'}
                </h3>
                <p className="text-xs text-slate-400 max-w-sm mb-5">
                  Insert your YubiKey and tap the golden contact or verify with Windows Hello / platform authenticator.
                </p>

                <button
                  onClick={handleAuthenticateKey}
                  disabled={authenticating || (posture?.registered_keys_count || 0) === 0}
                  className={`w-full max-w-xs flex items-center justify-center gap-2 px-5 py-3 rounded-xl font-semibold text-xs tracking-wide transition-all shadow-lg ${
                    (posture?.registered_keys_count || 0) === 0
                      ? 'bg-slate-800 text-slate-500 cursor-not-allowed border border-slate-700'
                      : authenticating
                      ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40 animate-pulse cursor-wait'
                      : 'bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 text-slate-950 font-bold shadow-amber-500/10 hover:shadow-amber-500/20'
                  }`}
                >
                  {authenticating ? (
                    <>
                      <RefreshCw className="h-4 w-4 animate-spin" />
                      Awaiting Physical Touch...
                    </>
                  ) : (
                    <>
                      <Shield className="h-4 w-4" />
                      Authenticate Security Key
                    </>
                  )}
                </button>

                {(posture?.registered_keys_count || 0) === 0 && (
                  <p className="text-[11px] text-amber-400 mt-2.5">
                    ⚠️ No hardware security keys enrolled yet. Switch to "Manage & Enroll Keys" tab to register your YubiKey.
                  </p>
                )}
              </div>

              {/* Security Invariants Callout */}
              <div className="grid grid-cols-2 gap-3 text-[11px]">
                <div className="p-3 rounded-lg border border-slate-800/80 bg-slate-900/30">
                  <div className="font-semibold text-slate-300 flex items-center gap-1.5 mb-1">
                    <Lock className="h-3 w-3 text-amber-400" />
                    Session Bound
                  </div>
                  <div className="text-slate-400">
                    Live clearance expires automatically after 15 minutes of inactivity.
                  </div>
                </div>
                <div className="p-3 rounded-lg border border-slate-800/80 bg-slate-900/30">
                  <div className="font-semibold text-slate-300 flex items-center gap-1.5 mb-1">
                    <Shield className="h-3 w-3 text-emerald-400" />
                    Zero Risk Bypass
                  </div>
                  <div className="text-slate-400">
                    Orders must still pass 1.5% parent equity cap, daily drawdown, and kill switch.
                  </div>
                </div>
              </div>
            </div>
          ) : (
            /* Enrollment Tab */
            <div className="space-y-5">
              {/* Enrollment Form */}
              <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-4 space-y-3">
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
                  <PlusCircle className="h-3.5 w-3.5 text-amber-400" />
                  Enroll New WebAuthn Authenticator
                </h3>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={newKeyLabel}
                    onChange={(e) => setNewKeyLabel(e.target.value)}
                    placeholder="e.g. Primary YubiKey 5C NFC"
                    className="flex-1 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-white placeholder-slate-500 focus:border-amber-400 focus:outline-none"
                  />
                  <button
                    onClick={handleEnrollKey}
                    disabled={enrolling || !newKeyLabel.trim()}
                    className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-xs transition-all disabled:opacity-50"
                  >
                    {enrolling ? (
                      <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <PlusCircle className="h-3.5 w-3.5" />
                    )}
                    Enroll Key
                  </button>
                </div>
                <p className="text-[11px] text-slate-400">
                  Supports YubiKey (USB/NFC), Windows Hello biometric/PIN, and hardware tokens.
                </p>
              </div>

              {/* Registered Keys List */}
              <div className="space-y-2">
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">
                  Enrolled Hardware Keys ({posture?.credentials?.length || 0})
                </h3>
                {posture?.credentials && posture.credentials.length > 0 ? (
                  <div className="space-y-2 max-h-60 overflow-y-auto">
                    {posture.credentials.map((cred) => (
                      <div
                        key={cred.credential_id}
                        className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900/40 p-3"
                      >
                        <div className="flex items-center gap-3">
                          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-slate-800 text-slate-300">
                            <Key className="h-4 w-4 text-amber-400" />
                          </div>
                          <div>
                            <div className="text-xs font-semibold text-white">{cred.label}</div>
                            <div className="text-[10px] text-slate-400 font-mono">
                              ID: {cred.credential_id_masked} • Counter: {cred.sign_counter} • Added:{' '}
                              {new Date(cred.created_at_ms).toLocaleDateString()}
                            </div>
                          </div>
                        </div>

                        <button
                          onClick={() => handleRevokeCredential(cred.credential_id)}
                          className="p-1.5 text-slate-500 hover:text-rose-400 hover:bg-rose-500/10 rounded transition-colors"
                          title="Revoke Key"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="p-4 text-center text-xs text-slate-500 border border-dashed border-slate-800 rounded-lg">
                    No hardware keys enrolled. Enroll your first security key above to enable Live Trading.
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-slate-800/80 pt-4 text-[11px] text-slate-500">
          <div className="flex items-center gap-1.5">
            <Clock className="h-3.5 w-3.5 text-slate-400" />
            <span>Policy: External Hardware or Platform Authenticator</span>
          </div>
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium transition-all"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
