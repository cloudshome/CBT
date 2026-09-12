# SDCC Conflict & Quarantine Taxonomy

**Status:** Authoritative Conflict Policy
**Document:** `docs/architecture/SDCC_CONFLICTS.md`

---

## 1. Zero Silent Data Loss Policy

Under no circumstances may a node:
- Overwrite older data with newer data based solely on timestamps.
- Discard an event because it contradicts existing knowledge.
- Silently merge two differently worded claims that share high semantic similarity.
- Silently drop an event due to a missing sequence or unknown type.

Every anomaly, collision, or contradiction is captured in an immutable conflict record under `data/collective/conflicts/` or quarantined under `data/collective/events/quarantined/`.

---

## 2. The 12 Conflict Categories

| Conflict Code | Category | Cause | Resolution Action |
| :--- | :--- | :--- | :--- |
| `DUPLICATE_EVENT` | Benign Idempotency | Same `event_id` and same `event_sha256` received again | Acknowledge as duplicate in receipt; do not re-process. |
| `EVENT_HASH_MISMATCH` | Integrity Violation | Tampered payload or corrupt bytes | Quarantine event immediately; record incident. |
| `SEQUENCE_GAP` | Transport Gap | Sequence $k$ received when checkpoint is $k - n$ ($n > 1$) | Stage in buffer; request missing sequence range from peer. |
| `ENTITY_ID_COLLISION` | ID Collision | Two distinct events attempt to create same entity ID | Quarantine collision; alert operator. |
| `KNOWLEDGE_SEMANTIC_DUPLICATE` | Epistemic Convergence | Two claims with different wording share semantic concept | Flag as `POSSIBLE_DUPLICATE`; retain both source records. |
| `KNOWLEDGE_CONTRADICTION` | Empirical Contradiction | Node A finds positive EV; Node B finds negative EV | Create `CONFLICT_SET`; preserve both with datasets and regimes. |
| `EXPERIMENT_DIVERGENCE` | Reproducibility Break | Same params and dataset produce diverging metric outcomes | Record `REPRODUCTION_DIVERGENCE`; flag methodology drift. |
| `PAPER_TRADE_COLLISION` | Execution Collision | Two nodes produce same trade ID | Fail closed; isolate trade into quarantine. |
| `SCHEMA_INCOMPATIBILITY` | Version Mismatch | Incoming event schema version > local supported version | Quarantine until migration adapter is applied. |
| `PROVENANCE_MISSING` | Epistemic Violation | Event lacks required origin attribution or dataset hash | Reject from canonical state; quarantine. |
| `ARTIFACT_HASH_MISMATCH` | File Corruption | Transferred artifact bytes do not match expected SHA-256 | Quarantine artifact; request re-transmission. |
| `UNKNOWN_EVENT_TYPE` | Protocol Evolution | Event type not recognized in local registry | Quarantine safely without crashing synchronization engine. |

---

## 3. Handling Knowledge Contradictions

When two nodes present opposing empirical results (e.g. `HOME-01` finds Strategy X profitable during Q1 2026; `OFFICE-01` finds Strategy X negative expectancy during Q2 2026):
1. **Never Overwrite**: Neither claim is deleted or superseded by timestamp.
2. **Conflict Set Creation**: A structured conflict record captures:
   - Claim A & Claim B IDs and verbatim statements
   - Associated dataset hashes and sample sizes
   - Market regimes tested
   - Strategy code commit hashes
   - Date ranges
3. **Research Escalation**: The contradiction becomes an input for research reconciliation (e.g. Regime Transition analysis) rather than a sync failure.
