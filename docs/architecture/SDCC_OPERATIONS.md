# SDCC Operations & CLI Runbook

**Status:** Authoritative Operational Guide
**Document:** `docs/architecture/SDCC_OPERATIONS.md`

---

## 1. CLI Commands Reference

All collective management commands are executed via the master CLI entrypoint:

```bash
python main.py collective <subcommand> [options]
```

### 1.1 `init`
Initializes local node identity, directory structure, and event tables.
```bash
python main.py collective init [--node-id HOME-01]
```

### 1.2 `status`
Displays live status of the local node, connected peers, checkpoints, event counts, conflicts, and quarantine queues.
```bash
python main.py collective status [--json]
```

### 1.3 `sync`
Executes an immediate synchronization cycle against available transport inboxes/outboxes.
```bash
python main.py collective sync [--mode AUTO|MANUAL|DRY_RUN]
```

### 1.4 `verify`
Performs comprehensive cryptographic and sequence integrity validation across all local and received events.
```bash
python main.py collective verify
```

### 1.5 `rebuild`
Replays all canonical events from disk and deterministically reconstructs local SQLite materialized projections (`brain_memory.db` and `trading_logs.db`).
```bash
python main.py collective rebuild [--force]
```

### 1.6 `reconcile`
Runs domain-specific reconciliation to detect knowledge contradictions or paper trading collisions.
```bash
python main.py collective reconcile
```

### 1.7 `conflicts`
Lists all active, resolved, and quarantined conflicts.
```bash
python main.py collective conflicts [--filter UNRESOLVED]
```

### 1.8 `nodes`
Lists all known nodes in the collective network, their last contact, and vector clock positions.
```bash
python main.py collective nodes
```

### 1.9 `export`
Packages local events and manifests into an immutable sync package ready for transport.
```bash
python main.py collective export [--dest-dir <path>]
```

### 1.10 `import`
Imports and validates an external sync package from a specified directory or archive.
```bash
python main.py collective import --package <path>
```

---

## 2. Directory Layout Runbook

```
data/
└── collective/
    ├── node/
    │   └── node_identity.json          # Node ID, public/private keys
    ├── events/
    │   ├── local/                      # Local append-only event segments
    │   ├── received/                   # Events imported from peer nodes
    │   ├── quarantined/                # Failed/tampered events
    │   └── compacted/                  # Snapshot compaction records
    ├── outbox/                         # Sync packages exported for peers
    ├── inbox/                          # Sync packages received from peers
    ├── manifests/                      # Signed manifests
    ├── checkpoints/
    │   └── vector_checkpoint.json      # Vector clock checkpoint per node
    ├── conflicts/                      # Unresolved and audited conflict sets
    └── receipts/                       # Cryptographic sync receipts
```
