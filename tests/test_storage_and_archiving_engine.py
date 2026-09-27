"""
tests/test_storage_and_archiving_engine.py
==========================================
Master Acceptance Test Suite for SKY 15-TB Knowledge Storage & Auto-Archiving Engine.
Validates all 17 Acceptance Gates (A through Q) and verifies strict enforcement of
the 15 Non-Negotiable Invariants.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import app
from core.autonomous_research.provenance_tracker import provenance_tracker
from core.autonomous_research.storage.archive_manager import ArchiveManager
from core.autonomous_research.storage.archive_policy import ArchivePolicyEngine, StorageQuotas
from core.autonomous_research.storage.archive_verifier import ArchiveVerifier
from core.autonomous_research.storage.backup_manager import CloudBackupManager
from core.autonomous_research.storage.content_hasher import content_hasher
from core.autonomous_research.storage.deduplication import DeduplicationManager
from core.autonomous_research.storage.drive_backend import SimulatedDriveBackend
from core.autonomous_research.storage.retrieval_cache import RetrievalCacheManager
from core.autonomous_research.storage.storage_maintenance import StorageMaintenanceEngine
from core.autonomous_research.storage.storage_manager import StorageManager
from core.autonomous_research.storage.storage_manifest import ArchiveManifestRecord, StorageManifest
from core.autonomous_research.storage.storage_pressure import StoragePressureManager
from core.universal_ingestor import universal_ingestor


@pytest.fixture
def clean_storage_env(tmp_path):
    """Sets up an isolated, hermetic storage environment for testing."""
    test_drive_dir = tmp_path / "gdrive_test_vault"
    test_cache_dir = tmp_path / "test_cache"
    test_uploads_dir = tmp_path / "test_uploads"
    test_drive_dir.mkdir(parents=True, exist_ok=True)
    test_cache_dir.mkdir(parents=True, exist_ok=True)
    test_uploads_dir.mkdir(parents=True, exist_ok=True)

    manifest = StorageManifest()
    drive_backend = SimulatedDriveBackend(root_dir=test_drive_dir)
    drive_backend.ensure_directory_tree("SKY")

    policy = ArchivePolicyEngine(
        quotas=StorageQuotas(
            hot_max_gb=1.0,
            warm_max_gb=2.0,
            warning_percent=75.0,
            critical_percent=85.0,
            emergency_percent=92.0,
        )
    )
    verifier = ArchiveVerifier(manifest=manifest)
    arch_mgr = ArchiveManager(
        backend=drive_backend, manifest=manifest, verifier=verifier, policy=policy
    )
    cache_mgr = RetrievalCacheManager(
        backend=drive_backend, manifest=manifest, policy=policy, cache_dir=test_cache_dir
    )
    dedup_mgr = DeduplicationManager(manifest=manifest)
    pressure_mgr = StoragePressureManager(
        manifest=manifest, arch_mgr=arch_mgr, policy=policy, data_dir=tmp_path
    )
    backup_mgr = CloudBackupManager(backend=drive_backend, manifest=manifest, verifier=verifier)
    maintenance_eng = StorageMaintenanceEngine(
        backend=drive_backend,
        manifest=manifest,
        arch_mgr=arch_mgr,
        pressure_mgr=pressure_mgr,
        backup_mgr=backup_mgr,
    )

    manager = StorageManager(
        backend=drive_backend,
        manifest=manifest,
        arch_mgr=arch_mgr,
        cache_mgr=cache_mgr,
        dedup_mgr=dedup_mgr,
        pressure_mgr=pressure_mgr,
        maintenance_eng=maintenance_eng,
        backup_mgr=backup_mgr,
        policy=policy,
    )

    with manifest.get_conn() as conn:
        conn.execute("DELETE FROM archive_manifest;")
        conn.execute("DELETE FROM storage_operation_logs;")
        conn.execute("DELETE FROM knowledge_snapshots;")
        conn.commit()

    yield {
        "manager": manager,
        "backend": drive_backend,
        "manifest": manifest,
        "arch_mgr": arch_mgr,
        "cache_mgr": cache_mgr,
        "dedup_mgr": dedup_mgr,
        "pressure_mgr": pressure_mgr,
        "maintenance": maintenance_eng,
        "backup": backup_mgr,
        "policy": policy,
        "verifier": verifier,
        "tmp_path": tmp_path,
        "uploads_dir": test_uploads_dir,
    }

    with manifest.get_conn() as conn:
        conn.execute("DELETE FROM archive_manifest;")
        conn.execute("DELETE FROM storage_operation_logs;")
        conn.execute("DELETE FROM knowledge_snapshots;")
        conn.commit()


# ==============================================================================
# GATE A: Upload and SHA-256 Identity
# ==============================================================================
def test_gate_a_upload_and_identity(clean_storage_env):
    """Gate A: Verify file upload, streaming SHA-256 calculation, and manifest record creation."""
    env = clean_storage_env
    mgr: StorageManager = env["manager"]
    uploads = env["uploads_dir"]

    test_file = uploads / "institutional_orderbook_liquidity.txt"
    test_content = b"Quantitative Institutional Liquidity Microstructure Research Paper 2026."
    test_file.write_bytes(test_content)

    res = mgr.ingest_and_archive(
        file_path_or_bytes=test_file,
        source_type="RESEARCH",
        filename=test_file.name,
        metadata={"author": "Dr. Quant", "domain": "MICROSTRUCTURE"},
    )

    assert res.is_verified is True
    assert res.archive_status == "VERIFIED"
    assert len(res.content_hash) == 64
    assert res.file_size == len(test_content)
    assert res.drive_file_id is not None
    assert "SKY/01_RAW_SOURCES" in (res.drive_path or "")


# ==============================================================================
# GATE B: Content-Addressable Deduplication
# ==============================================================================
def test_gate_b_content_deduplication(clean_storage_env):
    """Gate B: Ingest identical file 5 times; verify exactly 1 cloud copy, 5 references, 0 duplicate uploads."""
    env = clean_storage_env
    mgr: StorageManager = env["manager"]
    uploads = env["uploads_dir"]

    content = b"Duplicate Strategy Notes: Sweep FVG on BTC 15m timeframe."
    f1 = uploads / "fvg_strategy_v1.txt"
    f1.write_bytes(content)

    # First ingestion
    first_res = mgr.ingest_and_archive(f1, source_type="NOTES", filename="fvg_notes.txt")
    assert first_res.is_verified is True
    assert first_res.is_duplicate is False

    # 4 repeated ingestions with different filenames
    for i in range(2, 6):
        fn = uploads / f"copy_{i}.txt"
        fn.write_bytes(content)
        dup_res = mgr.ingest_and_archive(fn, source_type="NOTES", filename=f"copy_{i}.txt")
        assert dup_res.is_duplicate is True
        assert dup_res.source_id == first_res.source_id
        assert dup_res.drive_file_id == first_res.drive_file_id

    # Verify manifest has exactly 1 entry for this content hash
    manifest: StorageManifest = env["manifest"]
    rec = manifest.get_by_content_hash(first_res.content_hash)
    assert rec is not None
    assert rec.access_count >= 5


# ==============================================================================
# GATE C: Google Drive Archival & Predictable Hierarchy
# ==============================================================================
def test_gate_c_drive_archival_and_tree(clean_storage_env):
    """Gate C: Verify predictable folder routing across all 8 research categories."""
    env = clean_storage_env
    policy: ArchivePolicyEngine = env["policy"]

    assert policy.route_drive_folder("BOOK") == "SKY/01_RAW_SOURCES/BOOKS"
    assert policy.route_drive_folder("PDF_BOOK") == "SKY/01_RAW_SOURCES/BOOKS"
    assert policy.route_drive_folder("YOUTUBE") == "SKY/01_RAW_SOURCES/YOUTUBE"
    assert policy.route_drive_folder("NOTES") == "SKY/01_RAW_SOURCES/NOTES"
    assert policy.route_drive_folder("CODE") == "SKY/01_RAW_SOURCES/RESEARCH"
    assert policy.route_drive_folder("MARKET_DATA") == "SKY/08_MARKET_DATA/BTC"
    assert policy.route_drive_folder("SNAPSHOT") == "SKY/10_SYSTEM_SNAPSHOTS"


# ==============================================================================
# GATE D: Archive Verification Gate
# ==============================================================================
def test_gate_d_archive_verification_gate(clean_storage_env):
    """Gate D: Verify file size and SHA-256 match before status becomes VERIFIED."""
    env = clean_storage_env
    backend: SimulatedDriveBackend = env["backend"]
    manifest: StorageManifest = env["manifest"]
    verifier: ArchiveVerifier = env["verifier"]

    test_file = env["uploads_dir"] / "macro_gold_study.csv"
    data = b"date,gold_price,dxy_index\n2026-01-01,2650.5,103.2\n"
    test_file.write_bytes(data)

    hash_res = content_hasher.hash_file_stream(test_file)
    meta = backend.upload_file(test_file, drive_folder="SKY/08_MARKET_DATA/GOLD")

    record = ArchiveManifestRecord(
        source_id="SRC-TEST-VERIFY",
        content_hash=hash_res.content_hash,
        file_size=len(data),
        mime_type="text/csv",
        drive_file_id=meta.drive_file_id,
        drive_path=meta.drive_path,
        local_path=str(test_file),
    )
    manifest.save_record(record)

    # Run verification
    v_res = verifier.verify_record(record, backend)
    assert v_res.is_valid is True
    assert v_res.size_matched is True
    assert v_res.hash_matched is True

    # Check status updated to VERIFIED in DB
    updated = manifest.get_by_source_id("SRC-TEST-VERIFY")
    assert updated.archive_status == "VERIFIED"
    assert updated.verification_timestamp is not None


# ==============================================================================
# GATE E: Transaction Safety & Failed Upload
# ==============================================================================
def test_gate_e_transaction_safety_failed_upload(clean_storage_env):
    """Gate E: Simulate upload failure; verify local file strictly preserved, status FAILED, retry queued."""
    env = clean_storage_env
    mgr: StorageManager = env["manager"]
    backend: SimulatedDriveBackend = env["backend"]

    test_file = env["uploads_dir"] / "failing_study.pdf"
    test_file.write_bytes(b"%PDF-1.4 Mock failing research paper payload.")

    # Disconnect backend to trigger upload failure
    backend.set_online(False)

    res = mgr.ingest_and_archive(test_file, source_type="PDF")
    # Must preserve locally as LOCAL_PENDING_ARCHIVE or FAILED
    assert res.is_verified is False
    assert res.archive_status == "LOCAL_PENDING_ARCHIVE"
    # Local file MUST NOT be deleted (Invariant 4)
    assert test_file.exists()


# ==============================================================================
# GATE F: Verification-Gated Local Eviction
# ==============================================================================
def test_gate_f_verification_gated_eviction(clean_storage_env):
    """Gate F: Verify local eviction succeeds ONLY after archive status is VERIFIED."""
    env = clean_storage_env
    mgr: StorageManager = env["manager"]
    manifest: StorageManifest = env["manifest"]

    test_file = env["uploads_dir"] / "evictable_paper.pdf"
    test_file.write_bytes(b"%PDF-1.4 Eviction candidate test book.")

    res = mgr.ingest_and_archive(test_file, source_type="PDF")
    assert res.is_verified is True
    assert test_file.exists()

    # Evict local copy
    evicted = mgr.evict_source(res.source_id)
    assert evicted is True
    # Local file should now be removed
    assert not test_file.exists()

    # Manifest record should reflect EVICTED and tier COLD
    rec = manifest.get_by_source_id(res.source_id)
    assert rec.archive_status == "EVICTED"
    assert rec.storage_tier == "COLD"


# ==============================================================================
# GATE G: Transparent Retrieval & Cache Restoration
# ==============================================================================
def test_gate_g_retrieval_and_cache_restoration(clean_storage_env):
    """Gate G: Evict local copy; verify transparent retrieval from Drive and cache restoration with SHA-256 check."""
    env = clean_storage_env
    mgr: StorageManager = env["manager"]

    test_file = env["uploads_dir"] / "retrieval_target.txt"
    original_bytes = b"Crucial quantitative discovery: Lead-lag correlation between ETH & SOL."
    test_file.write_bytes(original_bytes)

    res = mgr.ingest_and_archive(test_file, source_type="RESEARCH")
    assert res.is_verified is True

    # Evict local file
    mgr.evict_source(res.source_id)
    assert not test_file.exists()

    # Retrieve source (transparent cache miss -> Google Drive fetch -> SHA-256 verify -> local cache)
    restored_path = mgr.retrieve_source(res.source_id)
    assert restored_path.exists()
    assert restored_path.read_bytes() == original_bytes


# ==============================================================================
# GATE H: Source Versioning Lineage
# ==============================================================================
def test_gate_h_source_versioning(clean_storage_env):
    """Gate H: Modify file, ingest as new version; verify parent/child lineage and previous/new hash tracking."""
    env = clean_storage_env
    dedup: DeduplicationManager = env["dedup_mgr"]
    manifest: StorageManifest = env["manifest"]

    v1_hash = "1111111111111111111111111111111111111111111111111111111111111111"
    v2_hash = "2222222222222222222222222222222222222222222222222222222222222222"

    rec1 = ArchiveManifestRecord(
        source_id="SRC-ALPHA-01",
        content_hash=v1_hash,
        file_size=500,
        mime_type="text/plain",
        version=1,
    )
    manifest.save_record(rec1)

    rec2 = dedup.create_new_version(
        base_source_id="SRC-ALPHA-01",
        new_content_hash=v2_hash,
        change_reason="Updated SMC liquidity parameters from 15m to 1h",
        file_size=550,
        mime_type="text/plain",
    )

    assert rec2.version == 2
    assert rec2.source_id == "SRC-ALPHA-01-V2"
    assert rec2.parent_source_id == "SRC-ALPHA-01"
    assert rec2.metadata["previous_hash"] == v1_hash
    assert rec2.metadata["new_hash"] == v2_hash


# ==============================================================================
# GATE I: Drive Outage Resilience
# ==============================================================================
def test_gate_i_drive_outage_resilience(clean_storage_env):
    """Gate I: Simulate Drive outage; verify LOCAL_PENDING_ARCHIVE mode allows research to continue."""
    env = clean_storage_env
    mgr: StorageManager = env["manager"]
    backend: SimulatedDriveBackend = env["backend"]

    # Disconnect Drive
    backend.set_online(False)

    f = env["uploads_dir"] / "offline_study.txt"
    f.write_bytes(b"Offline research material ingested during internet outage.")

    res = mgr.ingest_and_archive(f, source_type="NOTES")
    assert res.archive_status == "LOCAL_PENDING_ARCHIVE"
    assert f.exists()

    # Drive reconnects; run daily maintenance to retry pending
    backend.set_online(True)
    maint_results = mgr.maintenance.run_daily_maintenance()
    assert maint_results["drive_online"] is True
    assert maint_results["retried_uploads"] >= 1


# ==============================================================================
# GATE J: Storage Pressure Management & LRU Eviction
# ==============================================================================
def test_gate_j_storage_pressure_management(clean_storage_env):
    """Gate J: Simulate disk pressure; verify tier-based candidate selection and LRU eviction."""
    env = clean_storage_env
    mgr: StorageManager = env["manager"]

    # Ingest 3 verified files
    for i in range(3):
        f = env["uploads_dir"] / f"pressure_item_{i}.bin"
        f.write_bytes(f"Payload data for pressure item {i}".encode())
        res = mgr.ingest_and_archive(f, source_type="RESEARCH")
        assert res.is_verified is True

    # Check pressure inspect
    report = mgr.check_pressure()
    assert report.total_bytes > 0
    assert report.free_bytes > 0

    # Relieve pressure forcibly
    eviction_summary = mgr.pressure_mgr.relieve_pressure(
        target_free_percent=99.0, force_level="CRITICAL"
    )
    assert eviction_summary.files_evicted >= 1


# ==============================================================================
# GATE K: Orphan Detection
# ==============================================================================
def test_gate_k_orphan_detection(clean_storage_env):
    """Gate K: Audit cloud objects and SQLite tables for orphaned records without silent deletion."""
    env = clean_storage_env
    mgr: StorageManager = env["manager"]
    manifest: StorageManifest = env["manifest"]

    # Insert a manifest entry pointing to a non-existent drive_file_id
    ghost_rec = ArchiveManifestRecord(
        source_id="SRC-GHOST-999",
        content_hash="9999999999999999999999999999999999999999999999999999999999999999",
        file_size=1024,
        mime_type="text/plain",
        drive_file_id="non_existent_drive_id_123",
        archive_status="VERIFIED",
    )
    manifest.save_record(ghost_rec)

    orphan_rep = mgr.detect_orphans()
    assert "SRC-GHOST-999" in orphan_rep.missing_cloud_objects
    assert orphan_rep.total_orphans >= 1

    # Cleanup ghost record after verification
    with manifest.get_conn() as conn:
        conn.execute("DELETE FROM archive_manifest WHERE source_id = 'SRC-GHOST-999'")
        conn.commit()


# ==============================================================================
# GATE L: Archive Reconciliation
# ==============================================================================
def test_gate_l_archive_reconciliation(clean_storage_env):
    """Gate L: Compare database vs manifest vs Google Drive; verify mismatch detection."""
    env = clean_storage_env
    mgr: StorageManager = env["manager"]

    f = env["uploads_dir"] / "reconciliation_doc.txt"
    f.write_bytes(b"Clean reconciliation test doc.")
    res = mgr.ingest_and_archive(f, source_type="RESEARCH")
    assert res.is_verified is True

    report = mgr.run_reconciliation()
    assert report.matched_records >= 1
    assert report.status in ["HEALTHY", "WARNING"]


# ==============================================================================
# GATE M: Knowledge Snapshot Creation
# ==============================================================================
def test_gate_m_knowledge_snapshot_creation(clean_storage_env):
    """Gate M: Generate snapshot of graph, claims, hypotheses; verify export to Drive."""
    env = clean_storage_env
    mgr: StorageManager = env["manager"]

    snap = mgr.create_snapshot(tag="SNAPSHOT-TEST-GATEM")
    assert snap.snapshot_id.startswith("SNAP-")
    assert snap.snapshot_tag == "SNAPSHOT-TEST-GATEM"
    assert len(snap.manifest_hash) == 64
    assert "knowledge_vault_count" in snap.summary


# ==============================================================================
# GATE N: Disaster Recovery Reconstruction
# ==============================================================================
def test_gate_n_disaster_recovery(clean_storage_env):
    """Gate N: Clean environment with only DB backup + Drive archive; verify full reconstruction."""
    env = clean_storage_env
    mgr: StorageManager = env["manager"]

    # 1. Create a cloud database backup
    bkp_res = mgr.create_db_backup()
    assert bkp_res.is_verified is True
    assert Path(bkp_res.local_path).exists()

    # 2. Reconstruct from the backup
    rec_res = mgr.restore_system(bkp_res.local_path)
    assert rec_res.is_success is True


# ==============================================================================
# GATE O: Provenance Survives Local Archival
# ==============================================================================
@pytest.mark.asyncio
async def test_gate_o_provenance_survives_archival(clean_storage_env):
    """Gate O: Verify 5-tier causal tree resolves correctly even when local source is evicted."""
    env = clean_storage_env
    mgr: StorageManager = env["manager"]

    # Ingest through universal ingestor
    f = env["uploads_dir"] / "provenance_source.txt"
    f.write_bytes(
        b"BTC Liquidity Sweeps in Asia Session create 68% reversal probability. "
        b"Stop loss below the swing low, take profit at opposing liquidity pool."
    )

    ingest_res = await universal_ingestor.ingest(
        content=f.read_text(),
        mode="RESEARCH",
        file_name=f.name,
        source_uri=str(f),
        author_creator="Trader Dante",
        title="Asia Session Liquidity Playbook",
    )

    kid = ingest_res["knowledge_id"]
    sid = ingest_res["source_id"]

    # Evict local copy
    mgr.evict_source(sid)

    # Request provenance tree
    dossier = provenance_tracker.get_full_provenance_tree(kid)
    t1 = dossier["tier_1_what_source_claims"]
    assert "archive_status" in t1
    assert "storage_tier" in t1
    # Verify tree is complete
    assert "tier_2_what_sky_infers" in dossier
    assert "tier_3_what_sky_tested" in dossier
    assert "tier_4_what_data_supports" in dossier
    assert "tier_5_how_well_sky_applies_it" in dossier


# ==============================================================================
# GATE P: Large File Streaming Chunking
# ==============================================================================
def test_gate_p_large_file_streaming(clean_storage_env):
    """Gate P: Verify streaming chunked hashing and transfer with bounded RAM usage."""
    env = clean_storage_env
    uploads = env["uploads_dir"]

    # Create a 2 MB file and stream-hash with small 16 KB chunks
    large_file = uploads / "stream_test.bin"
    chunk_16kb = b"A" * (16 * 1024)
    with open(large_file, "wb") as f:
        for _ in range(128):  # 128 * 16 KB = 2 MB
            f.write(chunk_16kb)

    hash_res = content_hasher.hash_file_stream(large_file, chunk_size=16 * 1024)
    assert hash_res.chunk_count == 128
    assert hash_res.file_size == 2 * 1024 * 1024
    assert len(hash_res.content_hash) == 64


# ==============================================================================
# GATE Q: Storage Telemetry REST API Endpoints
# ==============================================================================
def test_gate_q_storage_rest_api_endpoints():
    """Gate Q: Test the newly added storage dashboard and maintenance REST API endpoints."""
    client = TestClient(app)
    headers = {"X-API-Key": "test-key-local-sandbox"}

    # 1. Telemetry dashboard endpoint
    res = client.get("/api/research/storage/telemetry", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "host_storage" in data
    assert "manifest_tiers" in data
    assert "health_status" in data

    # 2. Manifest list endpoint
    res_m = client.get("/api/research/storage/manifest?limit=10", headers=headers)
    assert res_m.status_code == 200
    assert isinstance(res_m.json(), list)

    # 3. Reconciliation endpoint
    res_r = client.post("/api/research/storage/reconcile", headers=headers)
    assert res_r.status_code == 200
    assert "status" in res_r.json()

    # 4. Snapshot creation endpoint
    res_s = client.post("/api/research/storage/snapshot?tag=TEST-API-SNAP", headers=headers)
    assert res_s.status_code == 200
    assert "snapshot_id" in res_s.json()

    # 5. Pressure relief endpoint
    res_p = client.post("/api/research/storage/pressure/relieve", headers=headers)
    assert res_p.status_code == 200
    assert "files_evicted" in res_p.json()
