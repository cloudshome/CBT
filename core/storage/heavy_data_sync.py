"""
core/storage/heavy_data_sync.py
===============================
Heavy Data & 5-TB Google Drive Synchronization Engine for SKY / CBT.

Architectural Guarantees:
1. Keeps Git Ultralight: Git tracks only code, markdown, and manifests.
2. 5-TB Google Drive Integration: All raw PDFs, large datasets, and SQLite
   snapshots are routed to Google Drive (folder: SKY/*).
3. Two-Way Machine Rehydration: When switching between Ubuntu and Windows,
   running sync rehydrates missing heavy files from Google Drive.
4. Resilient Offline-First: Seamlessly operates with SimulatedDriveBackend
   when offline or before live OAuth authorization.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.autonomous_research.storage.content_hasher import content_hasher
from core.autonomous_research.storage.drive_backend import (
    DriveBackendProtocol,
    get_default_drive_backend,
)

logger = logging.getLogger("sky.storage.heavy_data_sync")

DEFAULT_MANIFEST_PATH = Path("data/research/vault/gdrive_sync_manifest.json")
HEAVY_SIZE_THRESHOLD_BYTES = 5 * 1024 * 1024  # 5 MB


@dataclass
class HeavySyncEntry:
    rel_path: str
    file_name: str
    file_size: int
    content_hash: str
    drive_file_id: str
    drive_folder: str
    synced_at: str
    is_live_drive: bool = False
    mime_type: str = "application/octet-stream"


@dataclass
class HeavySyncReport:
    timestamp: str
    direction: str  # "upload" or "download"
    scanned_count: int = 0
    synced_count: int = 0
    skipped_count: int = 0
    error_count: int = 0
    bytes_transferred: int = 0
    is_live_drive: bool = False
    errors: list[str] = field(default_factory=list)
    details: list[dict[str, Any]] = field(default_factory=list)


class HeavyDataSyncManager:
    """Orchestrates bidirectional synchronization between CBT heavy data and Google Drive."""

    FOLDER_MAPPING = {
        "data/uploads": "SKY/01_RAW_SOURCES/PDF",
        "data/research/vault/docs": "SKY/01_RAW_SOURCES/DOCS",
        "data/binance_historical": "SKY/08_MARKET_DATA/BINANCE",
        "data/market_data": "SKY/08_MARKET_DATA/OTHER",
        "data/snapshots": "SKY/10_SYSTEM_SNAPSHOTS",
    }

    HEAVY_EXTENSIONS = {
        ".pdf",
        ".epub",
        ".parquet",
        ".zip",
        ".tar",
        ".gz",
        ".db",
        ".sqlite",
        ".bin",
    }

    def __init__(
        self,
        repo_root: Path | str | None = None,
        manifest_path: Path | str | None = None,
        drive_backend: DriveBackendProtocol | None = None,
    ) -> None:
        self.repo_root = Path(repo_root or ".").resolve()
        self.manifest_path = (
            Path(manifest_path).resolve()
            if manifest_path
            else (self.repo_root / DEFAULT_MANIFEST_PATH).resolve()
        )
        self._drive_backend = drive_backend
        self._manifest: dict[str, HeavySyncEntry] = {}
        self._load_manifest()

    @property
    def drive_backend(self) -> DriveBackendProtocol:
        if self._drive_backend is None:
            self._drive_backend = get_default_drive_backend()
        return self._drive_backend

    def _load_manifest(self) -> None:
        if self.manifest_path.exists():
            try:
                with open(self.manifest_path, encoding="utf-8") as f:
                    raw = json.load(f)
                for rel_path, entry in raw.get("files", {}).items():
                    self._manifest[rel_path] = HeavySyncEntry(**entry)
            except Exception as exc:
                logger.error("Failed to load sync manifest from %s: %s", self.manifest_path, exc)
                self._manifest = {}
        else:
            self._manifest = {}

    def _save_manifest(self) -> None:
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": "1.0.0",
            "updated_at": datetime.now(UTC).isoformat(),
            "target_account": os.getenv("GDRIVE_USER_EMAIL", "ypelectronics11@gmail.com"),
            "total_files": len(self._manifest),
            "total_bytes": sum(e.file_size for e in self._manifest.values()),
            "files": {rel_path: asdict(entry) for rel_path, entry in self._manifest.items()},
        }
        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

    def _determine_drive_folder(self, rel_path: str) -> str:
        clean_rel = rel_path.replace("\\", "/")
        for prefix, folder in self.FOLDER_MAPPING.items():
            if clean_rel.startswith(prefix):
                return folder
        # Default fallback by extension
        ext = Path(clean_rel).suffix.lower()
        if ext in (".pdf", ".epub"):
            return "SKY/01_RAW_SOURCES/PDF"
        if ext in (".parquet", ".csv"):
            return "SKY/08_MARKET_DATA/OTHER"
        return "SKY/00_INBOX"

    def is_heavy_file(self, file_path: Path) -> bool:
        """Determines if a file qualifies as heavy data that belongs in 5TB Google Drive."""
        if not file_path.is_file():
            return False
        # Ignore git, cache, temp, and test fixtures
        parts = file_path.parts
        if any(p.startswith(".") for p in parts) or "__pycache__" in parts:
            return False

        ext = file_path.suffix.lower()
        if ext in self.HEAVY_EXTENSIONS:
            return True

        try:
            return file_path.stat().st_size >= HEAVY_SIZE_THRESHOLD_BYTES
        except OSError:
            return False

    def sync_file_to_drive(
        self,
        local_path: Path | str,
        drive_folder: str | None = None,
        force_upload: bool = False,
    ) -> HeavySyncEntry:
        """Uploads a single local heavy file to Google Drive and updates manifest."""
        p = Path(local_path).resolve()
        if not p.is_file():
            raise FileNotFoundError(f"Local file not found: {p}")

        try:
            rel_path = str(p.relative_to(self.repo_root)).replace("\\", "/")
        except ValueError:
            rel_path = p.name

        target_folder = drive_folder or self._determine_drive_folder(rel_path)
        file_size = p.stat().st_size
        hash_res = content_hasher.hash_file_stream(p)
        content_hash = hash_res.content_hash

        # Check existing manifest entry
        existing = self._manifest.get(rel_path)
        if (
            not force_upload
            and existing
            and existing.content_hash == content_hash
            and existing.file_size == file_size
        ):
            # Already synced and identical
            return existing

        # Perform upload via active backend
        backend = self.drive_backend
        meta = backend.upload_file(
            local_path=p,
            drive_folder=target_folder,
            filename=p.name,
        )

        is_live = getattr(backend, "is_live", False)
        entry = HeavySyncEntry(
            rel_path=rel_path,
            file_name=p.name,
            file_size=file_size,
            content_hash=content_hash,
            drive_file_id=meta.drive_file_id,
            drive_folder=target_folder,
            synced_at=datetime.now(UTC).isoformat(),
            is_live_drive=is_live,
            mime_type=meta.mime_type,
        )

        self._manifest[rel_path] = entry
        self._save_manifest()
        logger.info(
            "Heavy data synced: %s (%d bytes) -> %s [Drive ID: %s]",
            rel_path,
            file_size,
            target_folder,
            meta.drive_file_id,
        )
        return entry

    def sync_all_heavy_data(
        self,
        target_dirs: list[str] | None = None,
        force_upload: bool = False,
    ) -> HeavySyncReport:
        """Discovers all local heavy files across designated directories and uploads them to Drive."""
        dirs_to_scan = target_dirs or list(self.FOLDER_MAPPING.keys())
        backend = self.drive_backend
        is_live = getattr(backend, "is_live", False)

        report = HeavySyncReport(
            timestamp=datetime.now(UTC).isoformat(),
            direction="upload",
            is_live_drive=is_live,
        )

        for d_str in dirs_to_scan:
            scan_dir = (self.repo_root / d_str).resolve()
            if not scan_dir.exists():
                continue

            for root, _, files in os.walk(scan_dir):
                for fname in files:
                    fpath = Path(root) / fname
                    if not self.is_heavy_file(fpath):
                        continue

                    report.scanned_count += 1
                    try:
                        rel_path = str(fpath.relative_to(self.repo_root)).replace("\\", "/")
                        size = fpath.stat().st_size
                        existing = self._manifest.get(rel_path)

                        if not force_upload and existing and existing.file_size == size:
                            # Quick size check before expensive hash
                            current_hash = content_hasher.hash_file_stream(fpath).content_hash
                            if existing.content_hash == current_hash:
                                report.skipped_count += 1
                                continue

                        entry = self.sync_file_to_drive(fpath, force_upload=force_upload)
                        report.synced_count += 1
                        report.bytes_transferred += entry.file_size
                        report.details.append(
                            {
                                "rel_path": rel_path,
                                "file_size": entry.file_size,
                                "drive_file_id": entry.drive_file_id,
                                "status": "SYNCED",
                            }
                        )
                    except Exception as exc:
                        err_msg = f"Failed to sync {fpath}: {exc!s}"
                        logger.error(err_msg)
                        report.error_count += 1
                        report.errors.append(err_msg)

        logger.info(
            "Sync complete: %d scanned, %d uploaded, %d skipped, %d errors (%d bytes)",
            report.scanned_count,
            report.synced_count,
            report.skipped_count,
            report.error_count,
            report.bytes_transferred,
        )
        return report

    def download_missing_heavy_files(self) -> HeavySyncReport:
        """
        Rehydrates local workspace by downloading heavy files recorded in the manifest
        that are missing on the local machine (e.g. fresh clone on Ubuntu or Windows).
        """
        backend = self.drive_backend
        is_live = getattr(backend, "is_live", False)

        report = HeavySyncReport(
            timestamp=datetime.now(UTC).isoformat(),
            direction="download",
            is_live_drive=is_live,
        )

        for rel_path, entry in self._manifest.items():
            report.scanned_count += 1
            local_target = (self.repo_root / rel_path).resolve()

            if local_target.exists():
                # Verify existing file size matches
                if local_target.stat().st_size == entry.file_size:
                    report.skipped_count += 1
                    continue

            try:
                logger.info(
                    "Downloading missing heavy asset: %s (Drive ID: %s)",
                    rel_path,
                    entry.drive_file_id,
                )
                success = backend.download_file(
                    drive_file_id=entry.drive_file_id,
                    dest_path=local_target,
                )
                if success and local_target.exists():
                    report.synced_count += 1
                    report.bytes_transferred += entry.file_size
                    report.details.append(
                        {
                            "rel_path": rel_path,
                            "file_size": entry.file_size,
                            "status": "DOWNLOADED",
                        }
                    )
                else:
                    raise OSError(f"Failed to download payload for {rel_path}")
            except Exception as exc:
                err_msg = f"Download failed for {rel_path}: {exc!s}"
                logger.error(err_msg)
                report.error_count += 1
                report.errors.append(err_msg)

        return report

    def get_status(self) -> dict[str, Any]:
        """Provides operational telemetry for Google Drive 5TB Heavy Data Sync."""
        backend = self.drive_backend
        is_live = getattr(backend, "is_live", False)
        connected_account = (
            backend.get_connected_account()
            if hasattr(backend, "get_connected_account")
            else os.getenv("GDRIVE_USER_EMAIL", "ypelectronics11@gmail.com")
        )

        total_bytes = sum(e.file_size for e in self._manifest.values())
        return {
            "status": "ACTIVE",
            "is_live_google_drive": is_live,
            "connected_account": connected_account,
            "target_account": os.getenv("GDRIVE_USER_EMAIL", "ypelectronics11@gmail.com"),
            "storage_tier": "5-TB Google Cloud / Drive Mesh",
            "manifest_file": str(self.manifest_path),
            "total_synced_files": len(self._manifest),
            "total_synced_bytes": total_bytes,
            "total_synced_mb": round(total_bytes / (1024 * 1024), 2),
            "total_synced_gb": round(total_bytes / (1024 * 1024 * 1024), 4),
            "monitored_folders": list(self.FOLDER_MAPPING.keys()),
        }


heavy_data_sync_manager = HeavyDataSyncManager()
