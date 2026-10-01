import React, { useState, useEffect, useCallback } from 'react';
import {
  Server,
  RefreshCw,
  ShieldCheck,
  ShieldAlert,
  Database,
  GitMerge,
  CheckCircle2,
} from 'lucide-react';
import { authFetch } from '../services/api';

interface NodeInfo {
  node_id: string;
  status: string;
  public_key_hex?: string;
  highest_known_sequence?: number;
  last_seen_at?: string;
  is_self?: boolean;
}

interface CollectiveStatus {
  node_id: string;
  status: string;
  protocol_version: number;
  schema_version: number;
  total_events: number;
  local_sequence: number;
  known_peers_count: number;
  unresolved_conflicts: number;
  quarantined_events: number;
  vector_clock: Record<string, number>;
}

interface ConflictItem {
  conflict_id: string;
  conflict_type: string;
  detected_at: string;
  source_node: string;
  target_entity_id?: string;
  resolved: boolean;
}

export const CollectiveCoreDashboard: React.FC = () => {
  const [status, setStatus] = useState<CollectiveStatus | null>(null);
  const [nodes, setNodes] = useState<{ local_node: NodeInfo; peer_nodes: NodeInfo[] } | null>(null);
  const [conflicts, setConflicts] = useState<ConflictItem[]>([]);
  const [knowledge, setKnowledge] = useState<any | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const [resStatus, resNodes, resConflicts, resKnowledge] = await Promise.all([
        authFetch('/api/collective/status').then((r: Response) => (r.ok ? r.json() : null)).catch(() => null),
        authFetch('/api/collective/nodes').then((r: Response) => (r.ok ? r.json() : null)).catch(() => null),
        authFetch('/api/collective/conflicts').then((r: Response) => (r.ok ? r.json() : null)).catch(() => null),
        authFetch('/api/collective/knowledge').then((r: Response) => (r.ok ? r.json() : null)).catch(() => null),
      ]);

      if (resStatus && !resStatus.message) setStatus(resStatus);
      if (resNodes && !resNodes.message) {
        setNodes({
          local_node: resNodes.local_node,
          peer_nodes: Array.isArray(resNodes.peer_nodes) ? resNodes.peer_nodes : [],
        });
      }
      if (resConflicts && Array.isArray(resConflicts.conflicts)) {
        setConflicts(resConflicts.conflicts);
      } else {
        setConflicts([]);
      }
      if (resKnowledge && !resKnowledge.message) setKnowledge(resKnowledge);
    } catch (err) {
      console.error('Error loading collective status:', err);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 8000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const handleSync = async () => {
    setLoading(true);
    setActionMessage('Initiating cluster synchronization...');
    try {
      const res = await authFetch('/api/collective/sync', { method: 'POST' });
      const data = await res.json();
      setActionMessage(`Sync complete: ${data.receipts?.length || 0} receipts generated.`);
      await fetchData();
    } catch (err: any) {
      setActionMessage(`Sync failed: ${err.message}`);
    } finally {
      setLoading(false);
      setTimeout(() => setActionMessage(null), 5000);
    }
  };

  const handleVerify = async () => {
    setLoading(true);
    setActionMessage('Verifying cryptographic event hashes...');
    try {
      const res = await authFetch('/api/collective/verify', { method: 'POST' });
      const data = await res.json();
      setActionMessage(`Verification ${data.status}: ${data.total_events_checked} checked, ${data.corrupt_events_count} corrupt.`);
    } catch (err: any) {
      setActionMessage(`Verification failed: ${err.message}`);
    } finally {
      setLoading(false);
      setTimeout(() => setActionMessage(null), 5000);
    }
  };

  const handleRebuild = async () => {
    setLoading(true);
    setActionMessage('Rebuilding local projections from canonical events...');
    try {
      const res = await authFetch('/api/collective/rebuild', { method: 'POST' });
      const data = await res.json();
      setActionMessage(`Rebuild complete: State hash ${data.state_hash?.slice(0, 12)} (${data.events_reduced} events reduced).`);
      await fetchData();
    } catch (err: any) {
      setActionMessage(`Rebuild failed: ${err.message}`);
    } finally {
      setLoading(false);
      setTimeout(() => setActionMessage(null), 5000);
    }
  };

  return (
    <div className="flex flex-col h-full bg-[#0b0e14] text-slate-200 p-4 space-y-4 overflow-y-auto">
      {/* Header & Controls */}
      <div className="flex flex-wrap items-center justify-between border-b border-slate-800 pb-3 gap-2">
        <div className="flex items-center space-x-3">
          <div className="p-2 bg-indigo-500/10 border border-indigo-500/20 rounded-lg text-indigo-400">
            <Server className="w-5 h-5" />
          </div>
          <div>
            <h1 className="text-lg font-bold tracking-wide text-white flex items-center gap-2">
              SKY Distributed Collective Core (SDCC)
              <span className="px-2 py-0.5 text-xs bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 rounded font-mono">
                v{status?.protocol_version || 1}.0 PROTOCOL
              </span>
            </h1>
            <p className="text-xs text-slate-400 font-mono">
              Offline-First Multi-PC Brain • Node: <span className="text-indigo-300 font-semibold">{status?.node_id || 'LOCAL'}</span>
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-2">
          {actionMessage && (
            <span className="text-xs text-amber-300 bg-amber-500/10 border border-amber-500/20 px-2 py-1 rounded animate-pulse">
              {actionMessage}
            </span>
          )}
          <button
            onClick={handleSync}
            disabled={loading}
            className="flex items-center space-x-1.5 px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded text-xs font-semibold shadow transition"
          >
            <GitMerge className="w-3.5 h-3.5" />
            <span>Sync Now</span>
          </button>
          <button
            onClick={handleVerify}
            disabled={loading}
            className="flex items-center space-x-1.5 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 disabled:opacity-50 text-slate-200 rounded text-xs border border-slate-700 transition"
          >
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
            <span>Verify Hashes</span>
          </button>
          <button
            onClick={handleRebuild}
            disabled={loading}
            className="flex items-center space-x-1.5 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 disabled:opacity-50 text-slate-200 rounded text-xs border border-slate-700 transition"
          >
            <RefreshCw className="w-3.5 h-3.5 text-cyan-400" />
            <span>Rebuild Projections</span>
          </button>
        </div>
      </div>

      {/* Top Telemetry KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
        <div className="bg-[#121722] border border-slate-800/80 rounded-lg p-3">
          <div className="text-[11px] text-slate-400 font-medium">Cluster Nodes</div>
          <div className="text-xl font-bold text-white mt-1">
            {(nodes?.peer_nodes?.length || 0) + 1}
            <span className="text-xs text-slate-500 font-normal ml-1">nodes</span>
          </div>
          <div className="text-[10px] text-emerald-400 mt-1 flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping" />
            All synced
          </div>
        </div>

        <div className="bg-[#121722] border border-slate-800/80 rounded-lg p-3">
          <div className="text-[11px] text-slate-400 font-medium">Total Canonical Events</div>
          <div className="text-xl font-bold text-indigo-400 mt-1">
            {(status?.total_events ?? 0).toLocaleString()}
          </div>
          <div className="text-[10px] text-slate-500 mt-1">Append-only ledger</div>
        </div>

        <div className="bg-[#121722] border border-slate-800/80 rounded-lg p-3">
          <div className="text-[11px] text-slate-400 font-medium">Local Sequence</div>
          <div className="text-xl font-bold text-cyan-400 mt-1">
            #{status?.local_sequence || 0}
          </div>
          <div className="text-[10px] text-slate-500 mt-1">Node Monotonic Head</div>
        </div>

        <div className="bg-[#121722] border border-slate-800/80 rounded-lg p-3">
          <div className="text-[11px] text-slate-400 font-medium">Active Conflicts</div>
          <div className="text-xl font-bold text-amber-400 mt-1">
            {status?.unresolved_conflicts || 0}
          </div>
          <div className="text-[10px] text-slate-500 mt-1">Preserved in conflict sets</div>
        </div>

        <div className="bg-[#121722] border border-slate-800/80 rounded-lg p-3">
          <div className="text-[11px] text-slate-400 font-medium">Quarantine Queue</div>
          <div className="text-xl font-bold text-rose-400 mt-1">
            {status?.quarantined_events || 0}
          </div>
          <div className="text-[10px] text-slate-500 mt-1">Tamper/hash violations</div>
        </div>

        <div className="bg-[#121722] border border-slate-800/80 rounded-lg p-3">
          <div className="text-[11px] text-slate-400 font-medium">State Hash</div>
          <div className="text-xs font-mono text-emerald-300 truncate mt-2" title={knowledge?.state_hash}>
            {knowledge?.state_hash ? knowledge.state_hash.slice(0, 14) + '...' : 'READY'}
          </div>
          <div className="text-[10px] text-slate-500 mt-1">Deterministic projection</div>
        </div>
      </div>

      {/* Main Grid: Nodes & Collective Memory */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 flex-1">
        {/* Left Column: Cluster Nodes */}
        <div className="bg-[#121722] border border-slate-800/80 rounded-lg p-3 flex flex-col space-y-3">
          <div className="flex items-center justify-between border-b border-slate-800 pb-2">
            <span className="text-xs font-bold text-slate-300 flex items-center gap-1.5">
              <Server className="w-3.5 h-3.5 text-indigo-400" />
              Node Topography
            </span>
            <span className="text-[10px] text-slate-500 font-mono">
              Vector Clock: {JSON.stringify(status?.vector_clock || {})}
            </span>
          </div>

          <div className="space-y-2 overflow-y-auto max-h-[300px]">
            {/* Local Node Card */}
            {nodes?.local_node && (
              <div className="bg-[#181f2e] border border-indigo-500/30 rounded p-2.5">
                <div className="flex items-center justify-between">
                  <span className="font-bold text-xs text-white flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-emerald-400" />
                    {nodes.local_node.node_id} (THIS NODE)
                  </span>
                  <span className="text-[10px] font-mono bg-indigo-500/20 text-indigo-300 px-1.5 py-0.5 rounded">
                    ONLINE
                  </span>
                </div>
                <div className="text-[11px] text-slate-400 mt-1">
                  Public Key: <span className="font-mono text-[10px] text-slate-300">{nodes.local_node.public_key_hex?.slice(0, 16)}...</span>
                </div>
                <div className="text-[11px] text-slate-400">
                  Monotonic Sequence: <span className="font-mono text-cyan-300">#{nodes.local_node.highest_known_sequence}</span>
                </div>
              </div>
            )}

            {/* Peer Nodes */}
            {(nodes?.peer_nodes || []).map((peer) => (
              <div key={peer.node_id} className="bg-[#181f2e]/60 border border-slate-800 rounded p-2.5">
                <div className="flex items-center justify-between">
                  <span className="font-bold text-xs text-slate-200 flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-cyan-400" />
                    {peer.node_id}
                  </span>
                  <span className="text-[10px] font-mono bg-slate-800 text-slate-300 px-1.5 py-0.5 rounded">
                    {peer.status}
                  </span>
                </div>
                <div className="text-[11px] text-slate-400 mt-1">
                  Highest Imported: <span className="font-mono text-cyan-300">#{peer.highest_known_sequence || 0}</span>
                </div>
                <div className="text-[10px] text-slate-500">
                  Last Seen: {peer.last_seen_at}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Center Column: Collective Knowledge Memory */}
        <div className="bg-[#121722] border border-slate-800/80 rounded-lg p-3 flex flex-col space-y-3">
          <div className="flex items-center justify-between border-b border-slate-800 pb-2">
            <span className="text-xs font-bold text-slate-300 flex items-center gap-1.5">
              <Database className="w-3.5 h-3.5 text-cyan-400" />
              Collective Knowledge Vault
            </span>
            <span className="text-[10px] text-slate-500 font-mono">Non-Destructive Memory</span>
          </div>

          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="bg-[#181f2e] p-2 rounded border border-slate-800/80">
              <span className="text-slate-400 text-[11px]">Research Sources</span>
              <div className="text-base font-bold text-white mt-0.5">
                {Object.keys(knowledge?.sources || {}).length}
              </div>
            </div>
            <div className="bg-[#181f2e] p-2 rounded border border-slate-800/80">
              <span className="text-slate-400 text-[11px]">Extracted Claims</span>
              <div className="text-base font-bold text-indigo-400 mt-0.5">
                {Object.keys(knowledge?.claims || {}).length}
              </div>
            </div>
            <div className="bg-[#181f2e] p-2 rounded border border-slate-800/80">
              <span className="text-slate-400 text-[11px]">Empirical Evidence</span>
              <div className="text-base font-bold text-emerald-400 mt-0.5">
                {Object.keys(knowledge?.evidence || {}).length}
              </div>
            </div>
            <div className="bg-[#181f2e] p-2 rounded border border-slate-800/80">
              <span className="text-slate-400 text-[11px]">Active Hypotheses</span>
              <div className="text-base font-bold text-amber-400 mt-0.5">
                {Object.keys(knowledge?.hypotheses || {}).length}
              </div>
            </div>
          </div>

          <div className="border-t border-slate-800/80 pt-2">
            <span className="text-[11px] font-semibold text-slate-400">Contributions by Node:</span>
            <div className="mt-1.5 space-y-1">
              {Object.entries(knowledge?.contributions_by_node || {}).map(([n, count]: any) => (
                <div key={n} className="flex items-center justify-between text-xs bg-[#181f2e]/40 px-2 py-1 rounded">
                  <span className="text-slate-300 font-mono">{n}</span>
                  <span className="text-cyan-300 font-bold">{count} contributions</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Right Column: Conflict & Quarantine Center */}
        <div className="bg-[#121722] border border-slate-800/80 rounded-lg p-3 flex flex-col space-y-3">
          <div className="flex items-center justify-between border-b border-slate-800 pb-2">
            <span className="text-xs font-bold text-slate-300 flex items-center gap-1.5">
              <ShieldAlert className="w-3.5 h-3.5 text-amber-400" />
              Conflict Center & Zero Data Loss
            </span>
            <span className="text-[10px] text-slate-500 font-mono">{(conflicts || []).length} recorded</span>
          </div>

          <div className="space-y-2 overflow-y-auto max-h-[300px]">
            {(conflicts || []).length === 0 ? (
              <div className="p-4 text-center text-xs text-slate-500">
                <CheckCircle2 className="w-6 h-6 text-emerald-500/50 mx-auto mb-1" />
                No active conflicts. All peer contributions reconciled cleanly.
              </div>
            ) : (
              (conflicts || []).map((c) => (
                <div key={c.conflict_id} className="bg-[#181f2e] border border-amber-500/20 rounded p-2 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-amber-300">{c.conflict_type}</span>
                    <span className="text-[10px] font-mono text-slate-500">{c.source_node}</span>
                  </div>
                  <div className="text-[11px] text-slate-400 mt-1">ID: {c.conflict_id}</div>
                  <div className="text-[10px] text-slate-500 mt-0.5">Detected: {c.detected_at}</div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
