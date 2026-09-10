"""
core/knowledge_os/knowledge_audit.py
====================================
Knowledge Quality & Provenance Integrity Audit Engine for SKY Knowledge OS.

Executes 7 systematic integrity checks across brain_memory.db:
1. Orphaned Claims: Claims lacking a valid parent source node.
2. Missing Spatial Provenance: Book claims lacking page/chapter coordinates.
3. Duplicate Concepts: Redundant ontology nodes that should be clustered.
4. Active Contradiction Density: Ratio of unresolved clashes to total claims.
5. Unsupported Promotions: Knowledge marked EMPIRICALLY_SUPPORTED without evidence records.
6. Broken Graph Edges: Edges referencing non-existent source/target IDs.
7. Failed Ingestion Jobs: Stalled or failed book ingestion records.

Produces authoritative status: PASS / WARN / FAIL.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from core.database import db_manager
from core.knowledge_graph_engine import knowledge_graph_engine
from core.provenance_engine import provenance_engine

logger = logging.getLogger("ai_quant_sentinel.knowledge_os.knowledge_audit")


@dataclass
class AuditCheckResult:
    check_name: str
    status: str  # PASS, WARN, FAIL
    count: int
    details: str
    remediation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class KnowledgeAuditReport:
    audit_id: str
    overall_status: str  # PASS, WARN, FAIL
    summary: str
    checks: list[AuditCheckResult]
    total_sources: int
    total_claims: int
    total_evidence: int
    total_autopsies: int
    created_at: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["checks"] = [c.to_dict() for c in self.checks]
        return d


class KnowledgeQualityAuditEngine:
    """Audits database integrity, provenance validity, and epistemic sanity."""

    def __init__(self):
        pass

    def run_audit(self) -> KnowledgeAuditReport:
        """Executes full diagnostic suite on the canonical knowledge base."""
        knowledge_graph_engine._init_graph_tables()
        provenance_engine._init_tables()

        audit_id = f"AUDIT_{int(time.time())}_{uuid.uuid4().hex[:4].upper()}"
        checks: list[AuditCheckResult] = []
        fail_count = 0
        warn_count = 0

        with db_manager.get_brain_conn() as conn:
            total_sources = conn.execute("SELECT COUNT(*) FROM research_provenance_sources;").fetchone()[0]
            total_claims = conn.execute("SELECT COUNT(*) FROM research_claims;").fetchone()[0]
            total_evidence = conn.execute("SELECT COUNT(*) FROM evidence_vault;").fetchone()[0]
            total_autopsies = conn.execute("SELECT COUNT(*) FROM rejected_claims_vault;").fetchone()[0]

            # CHECK 1: Orphaned claims
            orphans = conn.execute(
                """
                SELECT COUNT(*) FROM research_claims c
                LEFT JOIN research_provenance_sources s ON c.source_id = s.source_id
                WHERE s.source_id IS NULL;
                """
            ).fetchone()[0]
            if orphans > 0:
                checks.append(
                    AuditCheckResult(
                        check_name="Orphaned Claims",
                        status="FAIL",
                        count=orphans,
                        details=f"{orphans} claims point to non-existent source IDs.",
                        remediation="Prune orphaned claims or reconnect to parent provenance records.",
                    )
                )
                fail_count += 1
            else:
                checks.append(
                    AuditCheckResult(
                        check_name="Orphaned Claims",
                        status="PASS",
                        count=0,
                        details="All atomic claims are strictly anchored to valid source provenance nodes.",
                        remediation="No action required.",
                    )
                )

            # CHECK 2: Spatial Provenance Completeness
            missing_page = conn.execute(
                """
                SELECT COUNT(*) FROM research_claims
                WHERE (book_title IS NOT NULL AND book_title != '') AND (page_number IS NULL OR page_number <= 0);
                """
            ).fetchone()[0]
            if missing_page > 0:
                checks.append(
                    AuditCheckResult(
                        check_name="Spatial Provenance",
                        status="WARN",
                        count=missing_page,
                        details=f"{missing_page} book claims lack exact page number coordinates.",
                        remediation="Re-run streaming ingestion with page-aware extraction enabled.",
                    )
                )
                warn_count += 1
            else:
                checks.append(
                    AuditCheckResult(
                        check_name="Spatial Provenance",
                        status="PASS",
                        count=0,
                        details="100% of book claims retain exact page-level provenance.",
                        remediation="No action required.",
                    )
                )

            # CHECK 3: Duplicate Concepts
            dup_concepts = conn.execute(
                """
                SELECT COUNT(*) FROM (
                    SELECT LOWER(title) FROM research_concepts
                    GROUP BY LOWER(title) HAVING COUNT(*) > 1
                );
                """
            ).fetchone()[0]
            if dup_concepts > 0:
                checks.append(
                    AuditCheckResult(
                        check_name="Duplicate Concepts",
                        status="WARN",
                        count=dup_concepts,
                        details=f"{dup_concepts} concept clusters have duplicate titles in the ontology.",
                        remediation="Merge duplicate concepts and link synchronic graph edges.",
                    )
                )
                warn_count += 1
            else:
                checks.append(
                    AuditCheckResult(
                        check_name="Duplicate Concepts",
                        status="PASS",
                        count=0,
                        details="No duplicate concepts detected in ontology.",
                        remediation="No action required.",
                    )
                )

            # CHECK 4: Active Contradiction Density
            has_conflicts = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_conflicts';"
            ).fetchone()
            unresolved_conflicts = (
                conn.execute(
                    "SELECT COUNT(*) FROM research_conflicts WHERE status = 'UNRESOLVED';"
                ).fetchone()[0]
                if has_conflicts
                else 0
            )
            if unresolved_conflicts > 10:
                checks.append(
                    AuditCheckResult(
                        check_name="Active Contradictions",
                        status="WARN",
                        count=unresolved_conflicts,
                        details=f"{unresolved_conflicts} unresolved literature contradictions detected.",
                        remediation="Formulate resolving hypotheses in the Hypothesis Queue to test opposing claims.",
                    )
                )
                warn_count += 1
            else:
                checks.append(
                    AuditCheckResult(
                        check_name="Active Contradictions",
                        status="PASS",
                        count=unresolved_conflicts,
                        details=(
                            f"{unresolved_conflicts} contradictions recorded and bounded."
                            if unresolved_conflicts > 0
                            else "No unresolved literature contradictions recorded."
                        ),
                        remediation="No action required.",
                    )
                )

            # CHECK 5: Unsupported Promotions (Invariant: No empirical support without evidence)
            unsupported_promotions = conn.execute(
                """
                SELECT COUNT(*) FROM research_claims c
                LEFT JOIN evidence_vault e ON c.claim_id = e.knowledge_id OR c.source_id = e.knowledge_id
                WHERE c.epistemic_status = 'EMPIRICALLY_SUPPORTED' AND e.evidence_id IS NULL;
                """
            ).fetchone()[0]
            if unsupported_promotions > 0:
                checks.append(
                    AuditCheckResult(
                        check_name="Unsupported Promotions",
                        status="FAIL",
                        count=unsupported_promotions,
                        details=f"{unsupported_promotions} claims marked EMPIRICALLY_SUPPORTED without verified evidence.",
                        remediation="Demote unverified claims back to UNVERIFIED or attach backtest results.",
                    )
                )
                fail_count += 1
            else:
                checks.append(
                    AuditCheckResult(
                        check_name="Unsupported Promotions",
                        status="PASS",
                        count=0,
                        details="All EMPIRICALLY_SUPPORTED claims possess verified evidence in Evidence Vault.",
                        remediation="No action required.",
                    )
                )

            # CHECK 5: Broken Graph Edges
            broken_edges = conn.execute(
                """
                SELECT COUNT(*) FROM knowledge_graph_edges e
                LEFT JOIN research_claims rc1 ON e.source_node_id = rc1.claim_id
                LEFT JOIN research_concepts rk1 ON e.source_node_id = rk1.concept_id
                LEFT JOIN research_variables rv1 ON e.source_node_id = rv1.variable_id
                LEFT JOIN research_observations ro1 ON e.source_node_id = ro1.observation_id
                LEFT JOIN research_provenance_sources rs1 ON e.source_node_id = rs1.source_id

                LEFT JOIN research_claims rc2 ON e.target_node_id = rc2.claim_id
                LEFT JOIN research_concepts rk2 ON e.target_node_id = rk2.concept_id
                LEFT JOIN research_variables rv2 ON e.target_node_id = rv2.variable_id
                LEFT JOIN research_observations ro2 ON e.target_node_id = ro2.observation_id
                LEFT JOIN research_provenance_sources rs2 ON e.target_node_id = rs2.source_id

                WHERE (rc1.claim_id IS NULL AND rk1.concept_id IS NULL AND rv1.variable_id IS NULL AND ro1.observation_id IS NULL AND rs1.source_id IS NULL)
                   OR (rc2.claim_id IS NULL AND rk2.concept_id IS NULL AND rv2.variable_id IS NULL AND ro2.observation_id IS NULL AND rs2.source_id IS NULL);
                """
            ).fetchone()[0]
            if broken_edges > 0:
                checks.append(
                    AuditCheckResult(
                        check_name="Graph Edge Integrity",
                        status="WARN",
                        count=broken_edges,
                        details=f"{broken_edges} graph edges point to missing source or target nodes.",
                        remediation="Prune dangling relationship edges.",
                    )
                )
                warn_count += 1
            else:
                checks.append(
                    AuditCheckResult(
                        check_name="Graph Edge Integrity",
                        status="PASS",
                        count=0,
                        details="All knowledge graph edges link to valid nodes.",
                        remediation="No action required.",
                    )
                )

            # CHECK 6: Ingestion Failures
            failed_jobs = conn.execute(
                "SELECT COUNT(*) FROM book_ingestion_jobs WHERE status = 'FAILED';"
            ).fetchone()[0]
            if failed_jobs > 0:
                checks.append(
                    AuditCheckResult(
                        check_name="Book Ingestion Health",
                        status="WARN",
                        count=failed_jobs,
                        details=f"{failed_jobs} book ingestion jobs failed or crashed.",
                        remediation="Inspect error logs and resume ingestion from last checkpoint.",
                    )
                )
                warn_count += 1
            else:
                checks.append(
                    AuditCheckResult(
                        check_name="Book Ingestion Health",
                        status="PASS",
                        count=0,
                        details="All book ingestion jobs completed or active without unhandled failures.",
                        remediation="No action required.",
                    )
                )

            # Overall Status
            if fail_count > 0:
                overall_status = "FAIL"
                summary = f"CRITICAL: {fail_count} integrity violations detected. Correct immediately before strategy promotion."
            elif warn_count > 0:
                overall_status = "WARN"
                summary = f"ACCEPTABLE WITH WARNINGS: {warn_count} minor hygiene issues identified."
            else:
                overall_status = "PASS"
                summary = "EXCELLENT: All 7 knowledge integrity and provenance invariants pass with zero defects."

            report = KnowledgeAuditReport(
                audit_id=audit_id,
                overall_status=overall_status,
                summary=summary,
                checks=checks,
                total_sources=total_sources,
                total_claims=total_claims,
                total_evidence=total_evidence,
                total_autopsies=total_autopsies,
            )

            # Persist into knowledge_audits table
            conn.execute(
                """
                INSERT INTO knowledge_audits (
                    audit_id, status, summary, checks_json, created_at
                ) VALUES (?, ?, ?, ?, ?);
                """,
                (
                    audit_id,
                    overall_status,
                    summary,
                    json.dumps([c.to_dict() for c in checks]),
                    report.created_at,
                ),
            )
            conn.commit()

        return report


# Singleton
knowledge_audit_engine = KnowledgeQualityAuditEngine()
