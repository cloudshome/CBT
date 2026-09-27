# SKY Distributed Collective Core (SDCC) Architecture Specification

**Status:** Authoritative Architectural Doctrine
**Version:** 1.0.0
**Target Subsystems:** SKY Research Lab, Paper Trading, Knowledge Vaults, Storage Tiers

---

## 1. The Core Doctrine

### 1.1 The Machine is NOT the Source of Truth
No single machine owns the canonical state of SKY. Neither `HOME-01` nor `OFFICE-01` is an authoritative database server.

Instead:
```
                    COLLECTIVE EVENTS (Class A)
                               +
                    KNOWLEDGE OBJECTS (Class B)
                               +
                    CONTENT ARTIFACTS (Class C)
                               +
                    CRYPTO PROVENANCE
                               │
                     Deterministic Reducers
                               │
                 ┌─────────────┴─────────────┐
                 │                           │
              HOME-01                    OFFICE-01
           Materialized                Materialized
            Projection                  Projection
```

Every local database (`brain_memory.db`, `trading_logs.db`, `experiment_store.db`) is an expendable **materialized projection** derived from the append-only event stream.

---

## 2. Four Fundamental Data Classes

| Class | Type | Nature | Mutability | Storage Location |
| :--- | :--- | :--- | :--- | :--- |
| **Class A** | Immutable Events | Atomic occurrences (`PAPER_*`, `RESEARCH_*`, `CLAIM_*`) | Append-Only, Never Mutated | `data/collective/events/local/*.jsonl` |
| **Class B** | Knowledge Objects | Claims, concepts, hypotheses, evidence, autopsies | Versioned, Non-destructive | Materialized in `brain_memory.db` |
| **Class C** | Artifacts | PDFs, code, models, CSVs, datasets, charts | Content-Addressed `SHA-256` | `data/artifacts/objects/ab/cd/<hash>` |
| **Class D** | Materialized State | Portfolios, balances, positions, vector indexes | Deterministically Rebuildable | Local SQLite & Vector Indexes |

---

## 3. Storage Tiers

```
┌─────────────────────────────────────────────────────────────┐
│ Tier 1: Hot Local Storage                                  │
│ - SQLite databases (WAL mode)                              │
│ - Local vector index, caches, active paper portfolio        │
│ - Node-local events (events-000001.jsonl)                   │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ Tier 2: Collective Synchronization Layer                   │
│ - Outbox / Inbox sync packages                             │
│ - Signed manifests, receipts, vector checkpoints            │
│ - Syncthing or filesystem transport                         │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ Tier 3: Cold Google Drive Archive                          │
│ - Compressed event archives (zst/gz)                        │
│ - Immutable artifact snapshots                              │
│ - Full disaster recovery packages & manifests               │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. Node Identity & Event Invariants

1. **Permanent Node Identity**: Every node generates an immutable `node_identity.json` with an Ed25519 public/private keypair. The identity survives software updates.
2. **Globally Unique Event ID**:
   ```
   event_id = <node_id>:<sequence:012d>:<hash_prefix_8>
   Example: HOME-01:000000018421:8a72f9c1
   ```
3. **Canonical Event Envelope**: Every event carries schema version, protocol version, timestamps, causal links (`causation_id`, `correlation_id`), canonical payload, provenance, and SHA-256 integrity hashes.
4. **Weakest-Link Evidence Integrity**: Evidence grade (`FABRICATED` < `SIMULATED` < `IMPUTED` < `EMPIRICAL`) is preserved. An AI agent or synchronization step cannot artificially elevate evidence status.
5. **Deterministic Convergence**:
   $$\text{State} = \text{Reduce}(\text{CausalOrder}(\text{AllValidEvents}))$$
   Given the same set of events, every node arrives at the identical state regardless of delivery order.
