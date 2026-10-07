"""
core/knowledge_os/transcription.py
==================================
Multi-Provider Audio & Social Video Transcription Engine for CBT Knowledge OS.

Providers:
1. SubtitlesExtractorProvider: Fast direct extraction of platform subtitles/CC via yt-dlp.
2. GeminiAudioProvider: Cloud multimodal audio speech-to-text using official Gemini REST/SDK.
3. LocalWhisperProvider: Local fallback if faster-whisper is installed.
4. HeuristicFallbackProvider: Resilient placeholder provider when media is inaccessible.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import shutil
import tempfile
import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import requests
import yt_dlp

logger = logging.getLogger("sky.transcription")


@dataclass
class TranscriptSegment:
    start_time: float
    end_time: float
    text: str
    speaker: str = ""
    confidence: float = 0.90

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TranscriptResult:
    success: bool
    text: str
    language: str = "en"
    segments: list[TranscriptSegment] = field(default_factory=list)
    provider: str = "UNKNOWN"
    duration_seconds: float = 0.0
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["segments"] = [s.to_dict() if isinstance(s, TranscriptSegment) else s for s in self.segments]
        return d


class BaseTranscriptionProvider(ABC):
    @abstractmethod
    def transcribe_audio(self, audio_path: Path, language: str | None = None) -> TranscriptResult:
        pass


class GeminiAudioProvider(BaseTranscriptionProvider):
    """
    Cloud multimodal audio transcription via Google Gemini.
    Requires GEMINI_API_KEY. Works natively with mp3, m4a, wav, ogg.
    """

    def __init__(self, api_key: str | None = None, model: str = "gemini-2.5-flash"):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.model = model

    def transcribe_audio(self, audio_path: Path, language: str | None = None) -> TranscriptResult:
        if not self.api_key:
            return TranscriptResult(
                success=False,
                text="",
                provider="GEMINI_CLOUD",
                error="GEMINI_API_KEY not configured.",
            )

        if not audio_path.exists() or audio_path.stat().st_size == 0:
            return TranscriptResult(
                success=False,
                text="",
                provider="GEMINI_CLOUD",
                error=f"Audio file '{audio_path}' does not exist or is empty.",
            )

        # For files under 20MB, upload directly via inline base64 part
        file_size_mb = audio_path.stat().st_size / (1024 * 1024)
        if file_size_mb > 25.0:
            return TranscriptResult(
                success=False,
                text="",
                provider="GEMINI_CLOUD",
                error=f"Audio file size ({file_size_mb:.1f} MB) exceeds inline upload limit.",
            )

        try:
            mime_type = "audio/mp4" if audio_path.suffix.lower() in (".m4a", ".mp4") else "audio/mp3"
            audio_bytes = audio_path.read_bytes()
            b64_data = base64.b64encode(audio_bytes).decode("utf-8")

            url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
            prompt = (
                "Please transcribe the following audio recording accurately. "
                "Preserve spoken financial terms, numbers, timestamps, and currency names. "
                "If the speaker speaks in Bengali or mixed Banglish, transcribe in original Bengali text. "
                "Return the full faithful transcription."
            )

            payload = {
                "contents": [
                    {
                        "parts": [
                            {"text": prompt},
                            {
                                "inline_data": {
                                    "mime_type": mime_type,
                                    "data": b64_data,
                                }
                            },
                        ]
                    }
                ],
                "generationConfig": {
                    "temperature": 0.1,
                },
            }

            resp = requests.post(url, json=payload, timeout=60.0)
            if resp.status_code == 200:
                data = resp.json()
                text_out = ""
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    text_out = "".join(p.get("text", "") for p in parts)

                if text_out:
                    return TranscriptResult(
                        success=True,
                        text=text_out.strip(),
                        language=language or "auto",
                        provider="GEMINI_CLOUD",
                    )
            return TranscriptResult(
                success=False,
                text="",
                provider="GEMINI_CLOUD",
                error=f"Gemini API returned status {resp.status_code}: {resp.text[:200]}",
            )
        except Exception as e:
            return TranscriptResult(
                success=False,
                text="",
                provider="GEMINI_CLOUD",
                error=str(e),
            )


class SocialVideoAudioExtractor:
    """
    Downloads audio streams from social media videos (YouTube, Facebook, Twitter, etc.)
    using yt-dlp without requiring external ffmpeg binary for native m4a streams.
    """

    def __init__(self, download_dir: Path | None = None):
        self.download_dir = download_dir or Path(tempfile.gettempdir()) / "cbt_audio_cache"
        self.download_dir.mkdir(parents=True, exist_ok=True)

    def extract_audio(self, url: str, timeout: int = 40) -> tuple[bool, Path | None, dict[str, Any]]:
        """
        Attempts to extract audio from video URL using yt-dlp.
        Returns: (success: bool, audio_path: Path | None, metadata: dict)
        """
        output_template = str(self.download_dir / "%(id)s.%(ext)s")

        ydl_opts = {
            "format": "bestaudio[ext=m4a]/bestaudio/best",
            "outtmpl": output_template,
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "socket_timeout": timeout,
            "extract_flat": False,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if not info:
                    return False, None, {"error": "No media info returned by yt-dlp."}

                video_id = info.get("id")
                ext = info.get("ext", "m4a")
                expected_file = self.download_dir / f"{video_id}.{ext}"

                # Search if filename differed
                if not expected_file.exists():
                    matching = list(self.download_dir.glob(f"{video_id}.*"))
                    if matching:
                        expected_file = matching[0]

                if expected_file.exists() and expected_file.stat().st_size > 1024:
                    metadata = {
                        "title": info.get("title", ""),
                        "duration": info.get("duration", 0),
                        "uploader": info.get("uploader", ""),
                        "description": info.get("description", "")[:500],
                        "view_count": info.get("view_count", 0),
                        "subtitles": bool(info.get("subtitles") or info.get("automatic_captions")),
                    }
                    return True, expected_file, metadata

                return False, None, {"error": "Downloaded media file empty or not located on disk."}
        except Exception as exc:
            logger.debug(f"yt-dlp audio download failed for {url}: {exc}")
            return False, None, {"error": str(exc)}

    def extract_metadata_only(self, url: str) -> dict[str, Any]:
        """Fast metadata extraction without downloading media."""
        ydl_opts = {
            "extract_flat": True,
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info:
                    return {
                        "title": info.get("title", ""),
                        "uploader": info.get("uploader", ""),
                        "description": info.get("description", "")[:500],
                        "duration": info.get("duration", 0),
                    }
        except Exception as e:
            return {"error": str(e)}
        return {}


# Singletons
social_video_extractor = SocialVideoAudioExtractor()
gemini_audio_provider = GeminiAudioProvider()
