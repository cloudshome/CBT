# SDCC Synchronization Protocol Specification

**Status:** Authoritative Protocol Specification
**Protocol Version:** 1
**Document:** `docs/architecture/SDCC_PROTOCOL.md`

---

## 1. Synchronization Lifecycle

Synchronization executes through 13 sequential, fail-closed stages:

```
[1. DISCOVER] ─────────────► [2. AUTHENTICATE]
                                    │
                                    ▼
[4. DIFFERENCE DETECTION] ◄─ [3. MANIFEST EXCHANGE]
       │
       ▼
[5. TRANSFER EVENTS] ──────► [6. VERIFY HASHES]
                                    │
       ┌────────────────────────────┴───────────────────────────┐
       ▼                                                        ▼
[7. QUARANTINE INVALID]                               [8. IMPORT VALID EVENTS]
                                                                │
                                                                ▼
[11. REBUILD PROJECTIONS] ◄─ [10. RECONCILE] ◄──────── [9. DEDUPLICATE]
       │
       ▼
[12. GENERATE RECEIPT] ────► [13. UPDATE CHECKPOINT]
```

### Stage 1: Discover
Nodes discover peer sync packages located in transport inboxes (`data/collective/inbox/<peer_node_id>/`).

### Stage 2: Authenticate
The receiver validates the peer's `node_id`, public key registry, and cryptographic signature on the peer's `manifest.json`.

### Stage 3: Manifest Exchange
Each node shares its current `manifest.json` describing:
- First sequence, last sequence, and total event count per node.
- Vector clock of known nodes.
- SHA-256 digest of event package content.
- Knowledge head hash.

### Stage 4: Difference Detection
Using local `VectorCheckpoint` (`data/collective/checkpoints/vector_checkpoint.json`), the receiver computes the exact missing sequence range:
$$\text{Missing}(N) = [\text{Checkpoint}(N) + 1, \text{Manifest}(N).\text{last\_sequence}]$$

### Stage 5: Transfer Missing Events
Only event records within the missing sequence range are packaged and extracted from the sync package.

### Stage 6: Verify Hashes
For each received event:
1. `payload_sha256 == SHA256(canonical_json(payload))`
2. `event_sha256 == SHA256(canonical_json(envelope_without_integrity))`

### Stage 7: Quarantine Invalid Data
Any event with a mismatched hash, unknown format, or unsupported schema is quarantined to `data/collective/events/quarantined/` with a timestamped incident report. It never touches canonical state.

### Stage 8: Import Valid Events
Valid events are persisted to the local append-only store under `data/collective/events/received/<source_node_id>/`.

### Stage 9: Deduplicate
Events whose `event_id` already exists in the local ledger are verified for hash identity and marked duplicate without re-processing.

### Stage 10: Reconcile
Domain reconciliation engines inspect new events for paper trading collisions or knowledge contradictions.

### Stage 11: Rebuild Projections
Deterministic reducers update local materialized tables in `brain_memory.db` and `trading_logs.db`.

### Stage 12: Generate Receipt
An auditable `SyncReceipt` is written recording counts of received, imported, duplicate, and quarantined events.

### Stage 13: Update Checkpoint
The local vector clock checkpoint is updated to reflect the new highest contiguous sequence imported from the peer.
