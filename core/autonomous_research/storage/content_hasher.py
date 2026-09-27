"""
core/autonomous_research/storage/content_hasher.py
==================================================
Cryptographic streaming content hashing and MIME detection for SKY 15-TB Engine.
Enforces Invariant 33 (Large File Handling & Memory Boundedness):
Streaming 64 KB chunks ensure zero multi-gigabyte RAM buffering.
"""

from __future__ import annotations

import hashlib
import mimetypes
import re
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, ClassVar


@dataclass(frozen=True)
class ContentHashResult:
    content_hash: str
    file_size: int
    mime_type: str
    chunk_count: int


class ContentHasher:
    """Provides streaming cryptographic SHA-256 calculation and content identification."""

    DEFAULT_CHUNK_SIZE: int = 64 * 1024  # 64 KB chunks

    # Magic byte signatures for common high-value research mediums
    MAGIC_SIGNATURES: ClassVar[list[tuple[bytes, str]]] = [
        (b"%PDF", "application/pdf"),
        (b"\x89PNG\r\n\x1a\n", "image/png"),
        (b"\xff\xd8\xff", "image/jpeg"),
        (b"GIF87a", "image/gif"),
        (b"GIF89a", "image/gif"),
        (b"PK\x03\x04", "application/zip"),
        (b"\x1f\x8b\x08", "application/gzip"),
        (b"RIFF", "audio/wav"),
        (b"\x00\x00\x00\x18ftypmp42", "video/mp4"),
        (b"\x00\x00\x00 ftypisom", "video/mp4"),
        (b"\x1aE\xdf\xa3", "video/webm"),
    ]

    @classmethod
    def hash_file_stream(
        cls, file_path: Path | str, chunk_size: int = DEFAULT_CHUNK_SIZE
    ) -> ContentHashResult:
        """
        Streams a local file in bounded chunks, computing SHA-256 and detecting MIME.
        Never buffers the entire file in RAM.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Cannot hash non-existent file: {path}")

        hasher = hashlib.sha256()
        total_bytes = 0
        chunk_count = 0
        header_sample = b""

        with open(path, "rb") as f:
            while chunk := f.read(chunk_size):
                if chunk_count == 0:
                    header_sample = chunk[:64]
                hasher.update(chunk)
                total_bytes += len(chunk)
                chunk_count += 1

        mime = cls.detect_mime(path.name, sample=header_sample)
        return ContentHashResult(
            content_hash=hasher.hexdigest(),
            file_size=total_bytes,
            mime_type=mime,
            chunk_count=chunk_count,
        )

    @classmethod
    def hash_bytes(cls, data: bytes, filename: str = "document.bin") -> ContentHashResult:
        """Hashes an in-memory byte buffer and returns ContentHashResult."""
        hasher = hashlib.sha256(data)
        mime = cls.detect_mime(filename, sample=data[:64])
        return ContentHashResult(
            content_hash=hasher.hexdigest(),
            file_size=len(data),
            mime_type=mime,
            chunk_count=1,
        )

    @classmethod
    def hash_stream(
        cls, stream: BinaryIO, filename: str = "stream.bin", chunk_size: int = DEFAULT_CHUNK_SIZE
    ) -> ContentHashResult:
        """Hashes an open binary stream in chunks until EOF."""
        hasher = hashlib.sha256()
        total_bytes = 0
        chunk_count = 0
        header_sample = b""

        while chunk := stream.read(chunk_size):
            if chunk_count == 0:
                header_sample = chunk[:64]
            hasher.update(chunk)
            total_bytes += len(chunk)
            chunk_count += 1

        mime = cls.detect_mime(filename, sample=header_sample)
        return ContentHashResult(
            content_hash=hasher.hexdigest(),
            file_size=total_bytes,
            mime_type=mime,
            chunk_count=chunk_count,
        )

    @classmethod
    def detect_mime(cls, filename: str, sample: bytes | None = None) -> str:
        """Detects MIME type using magic header bytes, falling back to extension."""
        if sample:
            for magic, mime in cls.MAGIC_SIGNATURES:
                if sample.startswith(magic):
                    return mime

        # Extension-based detection
        ext = Path(filename).suffix.lower()
        if ext in [".py", ".pine", ".mq4", ".mq5"]:
            return "text/x-code"
        elif ext in [".csv"]:
            return "text/csv"
        elif ext in [".json"]:
            return "application/json"
        elif ext in [".md", ".txt"]:
            return "text/plain"
        elif ext in [".parquet"]:
            return "application/x-parquet"

        guessed, _ = mimetypes.guess_type(filename)
        return guessed or "application/octet-stream"

    @classmethod
    def sanitize_filename(cls, filename: str) -> str:
        """Sanitizes filename for cross-platform filesystem and cloud storage safety."""
        clean = re.sub(r'[\\/*?:"<>|]', "_", filename)
        clean = re.sub(r"\s+", "_", clean)
        return clean.strip("._") or "unnamed_source"

    @classmethod
    def format_bytes(cls, num_bytes: int) -> str:
        """Human-readable byte size."""
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if abs(num_bytes) < 1024.0:
                return f"{num_bytes:3.1f} {unit}"
            num_bytes /= 1024.0
        return f"{num_bytes:.1f} PB"


content_hasher = ContentHasher()
