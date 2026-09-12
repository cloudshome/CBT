# SDCC Disaster Recovery & Offline Rejoin Specification

**Status:** Authoritative Recovery Protocol
**Document:** `docs/architecture/SDCC_RECOVERY.md`

---

## 1. Offline Node Rejoin Procedure

When a node has been disconnected for hours, weeks, or months (e.g. `HOME-01` offline for 30 days while `OFFICE-01` and other nodes continued active research):

```
1. NODE STARTUP
   ├── Load permanent node_id from data/collective/node/node_identity.json
   ├── Validate schema version & protocol version compatibility
   └── Initialize local SQLite projections (brain_memory.db, trading_logs.db)

2. DISCOVER PEER MANIFESTS
   ├── Read incoming manifests from data/collective/inbox/
   └── Load local vector checkpoint (vector_checkpoint.json)

3. CALCULATION OF DELTAS
   ├── Identify missing events locally from each known node: [checkpoint(peer) + 1 .. manifest(peer).last_sequence]
   └── Package local events generated while offline into outbox for peers

4. IMPORT MISSING PEER EVENTS
   ├── Stream event chunks into received event store
   ├── Verify cryptographic signatures and SHA-256 hashes
   └── Quarantine any corrupted or mismatched items

5. RECONCILIATION & PROJECTION REPLAY
   ├── Deterministic topological sort of all valid events
   ├── Replay events through domain reducers
   └── Verify projection checksums

6. GENERATE SYNC RECEIPTS & ADVANCE CHECKPOINTS
   └── Status switches from SYNCING to ONLINE
```

---

## 2. Disaster Recovery from Google Drive Cold Storage

If a workstation suffers total disk loss:
1. **Bootstrap Fresh Node Identity** or restore node identity backup.
2. **Download Archive Manifest** from Google Drive (`SKY-COLLECTIVE/archive/manifests/latest_recovery_manifest.json`).
3. **Pull Compressed Event Segments**:
   - `SKY-COLLECTIVE/archive/events/*.jsonl.gz`
4. **Replay Full History**:
   ```bash
   python main.py collective rebuild --from-archive
   ```
5. **Verify State Integrity**:
   - Reconstructed databases match known canonical hash snapshots.
