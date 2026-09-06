"""
core/youtube/discovery.py
=========================
YouTube V5 Discovery Engine, URL Normalization, and Deduplication Sentinel.
Governed by Section 3, 4, 5, 6, 7 & 8 of the Master Directive:
- Canonicalizes YouTube URLs (single video, playlist, channel, handle).
- Performs lightweight, metadata-only flat extraction via yt-dlp.
- Enforces strict discovery caps (default 10, maximum 50).
- Persists crawl history in SQLite to prevent duplicate processing.
"""

from __future__ import annotations

import logging
import os
import re
import time
import urllib.parse

import yt_dlp

from core.database import db_manager
from core.youtube.models import DiscoveredVideo, YouTubeSource, YouTubeSourceType

logger = logging.getLogger("ai_quant_sentinel.youtube.discovery")

# Constitutional discovery cap: never allow unlimited autonomous crawling
YOUTUBE_MAX_EXPLORE_VIDEOS = int(os.getenv("YOUTUBE_MAX_EXPLORE_VIDEOS", "50"))
DEFAULT_EXPLORE_LIMIT = 10


def format_duration(seconds: int | float) -> str:
    """Formats seconds into readable MM:SS or HH:MM:SS."""
    sec = max(0, int(round(seconds)))
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


class YouTubeDiscoveryEngine:
    """
    Coordinates source normalization, yt-dlp flat discovery, and deduplication.
    """

    def __init__(self):
        self._init_crawl_memory()

    def _init_crawl_memory(self) -> None:
        """Ensures SQLite persistence table for crawl history exists."""
        try:
            with db_manager.get_brain_conn() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS youtube_crawl_history (
                        video_id TEXT PRIMARY KEY,
                        channel_id TEXT,
                        channel_name TEXT,
                        title TEXT,
                        canonical_url TEXT,
                        duration_seconds INTEGER,
                        upload_date TEXT,
                        status TEXT NOT NULL,  -- 'DISCOVERED', 'INGESTED', 'SKIPPED', 'FAILED'
                        discovered_at REAL NOT NULL,
                        ingested_at REAL,
                        content_hash TEXT
                    );
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_yt_crawl_channel ON youtube_crawl_history (channel_id);"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_yt_crawl_status ON youtube_crawl_history (status);"
                )
                conn.commit()
        except Exception as e:  # noqa: BLE001 — defensive fallback
            logger.warning(f"Could not initialize youtube_crawl_history table: {e}")

    def normalize_source(
        self,
        raw_url_or_handle: str,
        limit: int = DEFAULT_EXPLORE_LIMIT,
        sort_by: str = "recent",
        requested_by: str = "operator",
    ) -> YouTubeSource:
        """
        Parses and canonicalizes any YouTube video, playlist, or channel URL/handle.
        """
        raw = raw_url_or_handle.strip()
        safe_limit = max(1, min(limit, YOUTUBE_MAX_EXPLORE_VIDEOS))

        # 1. Handle Channel handles without URL prefix (e.g. "@TraderTom", "TraderTom")
        if raw.startswith("@"):
            handle = raw
            canonical = f"https://www.youtube.com/{handle}/videos"
            return YouTubeSource(
                source_type=YouTubeSourceType.CHANNEL,
                canonical_url=canonical,
                channel_handle=handle,
                requested_limit=safe_limit,
                requested_sort=sort_by,
                requested_by=requested_by,
            )

        # 2. Raw 11-char Video ID
        if re.fullmatch(r"[a-zA-Z0-9_-]{11}", raw):
            canonical = f"https://www.youtube.com/watch?v={raw}"
            return YouTubeSource(
                source_type=YouTubeSourceType.VIDEO,
                canonical_url=canonical,
                video_id=raw,
                requested_limit=1,
                requested_sort=sort_by,
                requested_by=requested_by,
            )

        parsed = urllib.parse.urlparse(raw)
        netloc = parsed.netloc.lower()
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        # 3. Playlists (youtube.com/playlist?list=PL...)
        if "playlist" in path or "list" in qs:
            list_id = qs.get("list", [""])[0]
            if list_id:
                canonical = f"https://www.youtube.com/playlist?list={list_id}"
                return YouTubeSource(
                    source_type=YouTubeSourceType.PLAYLIST,
                    canonical_url=canonical,
                    playlist_id=list_id,
                    requested_limit=safe_limit,
                    requested_sort=sort_by,
                    requested_by=requested_by,
                )

        # 4. Single Videos (watch?v=..., youtu.be/..., shorts/..., live/..., embed/...)
        v_param = qs.get("v", [""])[0]
        if v_param and len(v_param) == 11:
            return YouTubeSource(
                source_type=YouTubeSourceType.VIDEO,
                canonical_url=f"https://www.youtube.com/watch?v={v_param}",
                video_id=v_param,
                requested_limit=1,
                requested_sort=sort_by,
                requested_by=requested_by,
            )

        if "youtu.be" in netloc:
            parts = [p for p in path.split("/") if p]
            if parts and len(parts[0].split("?")[0]) == 11:
                vid = parts[0].split("?")[0]
                return YouTubeSource(
                    source_type=YouTubeSourceType.VIDEO,
                    canonical_url=f"https://www.youtube.com/watch?v={vid}",
                    video_id=vid,
                    requested_limit=1,
                    requested_sort=sort_by,
                    requested_by=requested_by,
                )

        for prefix in ("/shorts/", "/live/", "/embed/"):
            if prefix in path:
                cand = path.split(prefix)[-1].split("/")[0].split("?")[0]
                if len(cand) == 11:
                    return YouTubeSource(
                        source_type=YouTubeSourceType.VIDEO,
                        canonical_url=f"https://www.youtube.com/watch?v={cand}",
                        video_id=cand,
                        requested_limit=1,
                        requested_sort=sort_by,
                        requested_by=requested_by,
                    )

        # 5. Channel URLs (@handle, /channel/UC..., /c/..., /user/...)
        if "@" in path:
            handle = "@" + path.split("@")[-1].split("/")[0]
            canonical = f"https://www.youtube.com/{handle}/videos"
            return YouTubeSource(
                source_type=YouTubeSourceType.CHANNEL,
                canonical_url=canonical,
                channel_handle=handle,
                requested_limit=safe_limit,
                requested_sort=sort_by,
                requested_by=requested_by,
            )

        if "/channel/" in path or "/c/" in path or "/user/" in path:
            # Normalize to include /videos tab for flat extraction
            clean_path = path.rstrip("/")
            if not clean_path.endswith("/videos") and not clean_path.endswith("/playlists"):
                clean_path += "/videos"
            canonical = f"https://www.youtube.com{clean_path}"
            cid = path.split("/channel/")[-1].split("/")[0] if "/channel/" in path else ""
            return YouTubeSource(
                source_type=YouTubeSourceType.CHANNEL,
                canonical_url=canonical,
                channel_id=cid,
                requested_limit=safe_limit,
                requested_sort=sort_by,
                requested_by=requested_by,
            )

        # Fallback: Treat as channel URL with safe limits
        canonical = raw if raw.startswith("http") else f"https://{raw}"
        return YouTubeSource(
            source_type=YouTubeSourceType.CHANNEL,
            canonical_url=canonical,
            requested_limit=safe_limit,
            requested_sort=sort_by,
            requested_by=requested_by,
        )

    def discover_videos(
        self,
        source: YouTubeSource,
        limit_override: int | None = None,
    ) -> list[DiscoveredVideo]:
        """
        Discovers videos using flat extraction (no media downloads).
        Enforces strict limit bounding.
        """
        limit = limit_override or source.requested_limit
        safe_limit = max(1, min(limit, YOUTUBE_MAX_EXPLORE_VIDEOS))

        # Single video optimization
        if source.source_type == YouTubeSourceType.VIDEO and source.video_id:
            return [
                DiscoveredVideo(
                    video_id=source.video_id,
                    canonical_url=source.canonical_url,
                    title=f"YouTube Video ({source.video_id})",
                )
            ]

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extract_flat": "in_playlist",
            "playlist_items": f"1-{safe_limit}",
        }

        discovered: list[DiscoveredVideo] = []

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(source.canonical_url, download=False)
                if not info:
                    return []

                # Capture channel / playlist metadata
                source.channel_name = (
                    info.get("channel") or info.get("uploader") or info.get("title") or ""
                )
                source.channel_id = (
                    info.get("channel_id") or info.get("uploader_id") or source.channel_id
                )

                entries = info.get("entries") or []
                for idx, entry in enumerate(entries):
                    if len(discovered) >= safe_limit:
                        break
                    if not entry:
                        continue

                    vid = entry.get("id")
                    if not vid:
                        continue

                    v_url = f"https://www.youtube.com/watch?v={vid}"
                    title = entry.get("title") or f"YouTube Video ({vid})"
                    channel_name = (
                        entry.get("channel") or entry.get("uploader") or source.channel_name
                    )
                    duration = int(entry.get("duration") or 0)
                    upload_date = str(entry.get("upload_date") or "")
                    views = int(entry.get("view_count") or 0)
                    desc = (entry.get("description") or "")[:500]

                    discovered.append(
                        DiscoveredVideo(
                            video_id=vid,
                            canonical_url=v_url,
                            title=title,
                            channel_id=source.channel_id,
                            channel_name=channel_name,
                            upload_date=upload_date,
                            duration_seconds=duration,
                            duration_formatted=format_duration(duration),
                            view_count=views,
                            description=desc,
                            playlist_position=idx + 1,
                        )
                    )
        except Exception as e:  # noqa: BLE001 — defensive fallback
            logger.warning(f"Flat discovery encountered error for '{source.canonical_url}': {e}")

        # Record discovered items in crawl memory table
        self._record_discovered(discovered)
        return discovered

    def _record_discovered(self, videos: list[DiscoveredVideo]) -> None:
        """Atomically logs discovered videos into SQLite."""
        if not videos:
            return
        try:
            with db_manager.get_brain_conn() as conn:
                for v in videos:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO youtube_crawl_history
                        (video_id, channel_id, channel_name, title, canonical_url, duration_seconds, upload_date, status, discovered_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 'DISCOVERED', ?)
                        """,
                        (
                            v.video_id,
                            v.channel_id,
                            v.channel_name,
                            v.title,
                            v.canonical_url,
                            v.duration_seconds,
                            v.upload_date,
                            v.discovered_at,
                        ),
                    )
                conn.commit()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Failed to record discovered videos in crawl memory: {e}")

    def filter_unprocessed(
        self,
        videos: list[DiscoveredVideo],
        force_refresh: bool = False,
    ) -> tuple[list[DiscoveredVideo], list[DiscoveredVideo]]:
        """
        Separates videos into (new_to_process, already_ingested).
        If force_refresh is True, all videos are returned as new_to_process.
        """
        if force_refresh or not videos:
            return videos, []

        new_videos: list[DiscoveredVideo] = []
        skipped_videos: list[DiscoveredVideo] = []

        try:
            with db_manager.get_brain_conn() as conn:
                ingested_ids = set()
                # Check crawl memory table
                cur = conn.execute(
                    "SELECT video_id FROM youtube_crawl_history WHERE status = 'INGESTED'"
                )
                for r in cur.fetchall():
                    ingested_ids.add(r["video_id"])

                # Also check research_provenance_ledger if initialized
                try:
                    cur_prov = conn.execute(
                        "SELECT source_uri FROM research_provenance_ledger WHERE source_type = 'YOUTUBE'"
                    )
                    for r in cur_prov.fetchall():
                        uri = r["source_uri"] or ""
                        match = re.search(r"watch\?v=([a-zA-Z0-9_-]{11})", uri)
                        if match:
                            ingested_ids.add(match.group(1))
                except Exception:  # noqa: S110,BLE001 — defensive fallback
                    pass

                for v in videos:
                    if v.video_id in ingested_ids:
                        skipped_videos.append(v)
                    else:
                        new_videos.append(v)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Deduplication check error: {e}")
            return videos, []

        return new_videos, skipped_videos

    def mark_video_status(
        self,
        video_id: str,
        status: str,
        content_hash: str = "",
    ) -> None:
        """Updates video ingestion state in crawl memory."""
        now = time.time()
        try:
            with db_manager.get_brain_conn() as conn:
                conn.execute(
                    """
                    INSERT INTO youtube_crawl_history (video_id, status, discovered_at, ingested_at, content_hash)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(video_id) DO UPDATE SET
                        status = excluded.status,
                        ingested_at = excluded.ingested_at,
                        content_hash = excluded.content_hash
                    """,
                    (video_id, status, now, now, content_hash),
                )
                conn.commit()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Could not update video status for {video_id}: {e}")


# Master Discovery Singleton
youtube_discovery = YouTubeDiscoveryEngine()
