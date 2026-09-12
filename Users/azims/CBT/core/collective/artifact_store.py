"""
core/collective/artifact_store.py
=================================
Content-addressed, deduplicated artifact storage for SDCC.
Section 4 & 20: Identity is SHA256(content). Layout: objects/ab/cd/<sha256>.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from core.autonomous_research.storage.content_hasher import content_hasher

logger = logging.getLogger("sky.collective.artifact_store")


@dataclass
class ArtifactMetadata:
    content_hash: str
    original_name: str
    file_size: int
    source_node: str
    registered_at: str
    mime_type: str = "application/octet-stream"
    references: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ArtifactStore:
    """Manages immutable, content-addressed files under data/artifacts/."""

    def __init__(self, base_dir: Path | None = None):
        self.base_dir = base_dir or Path(os.getenv("DATA_DIR", "data")) / "artifacts"
        self.objects_dir = self.base_dir / "objects"
        self.manifests_dir = self.base_dir / "manifests"
        self.quarantine_dir = self.base_dir / "quarantine"
        self.index_file = self.manifests_dir / "artifact_index.json"

        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        self.objects_dir.mkdir(parents=True, exist_ok=True)
        self.manifests_dir.mkdir(parents=True, exist_ok=True)
        self.quarantine_dir.mkdir(parents=True, exist_ok=True)
        if not self.index_file.exists():
            self._save_index({})

    def _load_index(self) -> dict[str, dict[str, Any]]:
        try:
            with open(self.index_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_index(self, data: dict[str, Any]) -> None:
        with open(self.index_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)

    def _get_object_path(self, content_hash: str) -> Path:
        """Computes hierarchical path: objects/ab/cd/<hash>."""
        prefix1 = content_hash[:2]
        prefix2 = content_hash[2:4]
        target_dir = self.objects_dir / prefix1 / prefix2
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir / content_hash

    def store_bytes(
        self,
        content: bytes,
        original_name: str,
        source_node: str,
        reference_id: str | None = None,
    ) -> str:
        """Stores raw bytes, hashes, deduplicates, and returns content_hash."""
        content_hash = hashlib.sha256(content).hexdigest()
        obj_path = self._get_object_path(content_hash)

        if not obj_path.exists():
            with open(obj_path, "wb") as f:
                f.write(content)
            logger.info(f"Stored new content-addressed artifact {content_hash[:12]} ({original_name})")
        else:
            logger.debug(f"Artifact {content_hash[:12]} already present; deduplicated.")

        # Update index
        index = self._load_index()
        meta_dict = index.get(content_hash)
        if not meta_dict:
            import datetime
            meta = ArtifactMetadata(
                content_hash=content_hash,
                original_name=original_name,
                file_size=len(content),
                source_node=source_node,
                registered_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                references=[reference_id] if reference_id else [],
            )
            index[content_hash] = meta.to_dict()
        else:
            if reference_id and reference_id not in meta_dict["references"]:
                meta_dict["references"].append(reference_id)
            index[content_hash] = meta_dict

        self._save_index(index)
        return content_hash

    def store_file(
        self,
        file_path: Path,
        source_node: str,
        reference_id: str | None = None,
    ) -> str:
        """Reads file, computes SHA-256, and stores in objects."""
        if not file_path.exists():
            raise FileNotFoundError(f"Source file {file_path} not found")
        with open(file_path, "rb") as f:
            content = f.read()
        return self.store_bytes(
            content=content,
            original_name=file_path.name,
            source_node=source_node,
            reference_id=reference_id,
        )

    def get_artifact_path(self, content_hash: str) -> Path | None:
        """Returns path to artifact if valid on disk."""
        obj_path = self._get_object_path(content_hash)
        if obj_path.exists():
            return obj_path
        return None

    def verify_artifact(self, content_hash: str) -> bool:
        """Verifies that the object exists on disk and matches its SHA-256 digest."""
        path = self.get_artifact_path(content_hash)
        if not path or not path.exists():
            return False
        with open(path, "rb") as f:
            actual = hashlib.sha256(f.read()).hexdigest()
        return actual == content_hash

    def garbage_collect(self) -> int:
        """
        Removes unreferenced artifacts per Section 52:
        Only garbage collect when reference_count == 0. Returns count of collected artifacts.
        """
        index = self._load_index()
        collected = 0
        to_delete = []

        for content_hash, meta in index.items():
            if not meta.get("references"):
                obj_path = self._get_object_path(content_hash)
                if obj_path.exists():
                    obj_path.unlink()
                to_delete.append(content_hash)
                collected += 1

        for h in to_delete:
            del index[h]

        if collected > 0:
            self._save_index(index)
            logger.info(f"Garbage collected {collected} unreferenced artifacts.")
        return collected


artifact_store = ArtifactStore()
