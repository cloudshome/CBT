"""
core/knowledge_os/universal_ingestor.py
======================================
Institutional Universal Research Ingestion Engine for CBT / SKY Knowledge OS.

Constitutional Mandates:
1. Link Persistence Invariant: Every accepted URL MUST immediately create a durable
   source record in `research_sources`. No downstream network, parsing, or LLM failure
   can delete or discard it.
2. Zero Hallucination: If media is login-walled, DRM-protected, or blocked (e.g. Facebook,
   private reels), mark `ACCESS_BLOCKED`. Never fabricate transcripts or assertions.
3. Decoupled Architecture:
   URL -> SOURCE -> ARTIFACTS -> CLAIMS -> EVIDENCE -> WIKI ARTICLE
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
import urllib.parse
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from core.database import DATA_DIR
from core.knowledge_os.research_wikipedia import (
    WIKI_DB_PATH,
    EpistemicClaim,
    WikiArticle,
    research_wikipedia_engine,
)
from core.knowledge_os.transcription import (
    gemini_audio_provider,
    social_video_extractor,
)

logger = logging.getLogger("sky.universal_ingestor")


@dataclass
class RealLifeSummary:
    """Actionable, practical real-life summary for traders and researchers."""

    core_concept_bn: str
    practical_market_impact: str
    actionable_guidance: str
    hype_vs_reality: str
    risk_warning: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_markdown(self) -> str:
        return (
            "## 🎯 বাস্তব জীবনের বাস্তবসম্মত সারসংক্ষেপ (Real-Life Practical Summary)\n"
            f"- **সহজ বাংলায় মূল কথা:** {self.core_concept_bn}\n"
            f"- **মার্কেট ও ক্রিপ্টোতে বাস্তব প্রভাব:** {self.practical_market_impact}\n"
            f"- **একজন ট্রেডার বা গবেষকের জন্য বাস্তব করণীয়:** {self.actionable_guidance}\n"
            f"- **হাইপ বনাম বাস্তবতা চেক:** {self.hype_vs_reality}\n"
            f"- **ঝুঁকি ও সতর্কতা:** {self.risk_warning}\n"
        )


class SourceType(str, Enum):
    WEB_ARTICLE = "WEB_ARTICLE"
    PDF = "PDF"
    JOURNAL_PAPER = "JOURNAL_PAPER"
    YOUTUBE_VIDEO = "YOUTUBE_VIDEO"
    FACEBOOK_VIDEO = "FACEBOOK_VIDEO"
    FACEBOOK_REEL = "FACEBOOK_REEL"
    INSTAGRAM_REEL = "INSTAGRAM_REEL"
    X_POST = "X_POST"
    X_THREAD = "X_THREAD"
    REDDIT = "REDDIT"
    BLOG = "BLOG"
    NEWS = "NEWS"
    GITHUB = "GITHUB"
    ARXIV = "ARXIV"
    TRADINGVIEW = "TRADINGVIEW"
    SEC_DOCUMENT = "SEC_DOCUMENT"
    GOVERNMENT_DATA = "GOVERNMENT_DATA"
    AUDIO = "AUDIO"
    VIDEO = "VIDEO"
    UNKNOWN_URL = "UNKNOWN_URL"


class AccessStatus(str, Enum):
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    ACCESS_BLOCKED = "ACCESS_BLOCKED"
    FAILED = "FAILED"


class ExtractionStatus(str, Enum):
    PENDING = "PENDING"
    EXTRACTED = "EXTRACTED"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


@dataclass
class ResearchSourceRecord:
    source_id: str
    original_url: str
    canonical_url: str
    source_domain: str
    source_type: str
    access_status: str
    extraction_status: str
    title: str = ""
    author_or_creator: str = ""
    publication_date: str = ""
    content_hash: str = ""
    raw_metadata: dict[str, Any] = field(default_factory=dict)
    failure_reason: str = ""
    retry_count: int = 0
    wiki_article_id: str = ""
    created_at: int = field(default_factory=lambda: int(time.time() * 1000))
    updated_at: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


@dataclass
class UniversalIngestionResult:
    source: ResearchSourceRecord
    wiki_article: WikiArticle | None
    artifacts: list[dict[str, Any]]
    claims: list[EpistemicClaim]
    status: str  # SUCCESS, PARTIAL, BLOCKED, FAILED
    message: str
    real_life_summary: RealLifeSummary | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source.to_dict(),
            "wiki_article": self.wiki_article.to_dict() if self.wiki_article else None,
            "artifacts_count": len(self.artifacts),
            "claims_count": len(self.claims),
            "status": self.status,
            "message": self.message,
            "real_life_summary": self.real_life_summary.to_dict() if self.real_life_summary else None,
        }


class UniversalIngestor:
    """
    Coordinates end-to-end ingestion under the Link Persistence Invariant.
    """

    def __init__(self, db_path: Path = WIKI_DB_PATH):
        self.db_path = db_path
        self._ensure_tables()

    def _get_connection(self):
        return research_wikipedia_engine._get_connection()

    def _ensure_tables(self) -> None:
        """Initializes relational tables in research_wiki.db."""
        with self._get_connection() as conn:
            # 1. research_sources
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS research_sources (
                    source_id TEXT PRIMARY KEY,
                    original_url TEXT NOT NULL,
                    canonical_url TEXT,
                    source_domain TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    access_status TEXT NOT NULL,
                    extraction_status TEXT NOT NULL,
                    title TEXT,
                    author_or_creator TEXT,
                    publication_date TEXT,
                    content_hash TEXT,
                    raw_metadata_json TEXT,
                    failure_reason TEXT,
                    retry_count INTEGER DEFAULT 0,
                    wiki_article_id TEXT,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sources_url ON research_sources(original_url);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sources_created ON research_sources(created_at DESC);"
            )

            # 2. research_artifacts
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS research_artifacts (
                    artifact_id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    artifact_type TEXT NOT NULL,
                    content_text TEXT,
                    content_json TEXT,
                    file_path TEXT,
                    file_hash TEXT,
                    created_at INTEGER NOT NULL,
                    FOREIGN KEY (source_id) REFERENCES research_sources(source_id)
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_artifacts_source ON research_artifacts(source_id);"
            )

            # 3. research_claims
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS research_claims (
                    claim_id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    wiki_article_id TEXT,
                    speaker_claim TEXT NOT NULL,
                    claim_type TEXT NOT NULL,
                    speaker TEXT,
                    timestamp_marker TEXT,
                    time_period TEXT,
                    confidence_score REAL NOT NULL,
                    verification_status TEXT NOT NULL,
                    cross_verification_evidence TEXT,
                    empirical_dataset_reference TEXT,
                    created_at INTEGER NOT NULL
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_claims_source ON research_claims(source_id);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_claims_type ON research_claims(claim_type);"
            )

            # 4. research_evidence
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS research_evidence (
                    evidence_id TEXT PRIMARY KEY,
                    claim_id TEXT NOT NULL,
                    evidence_type TEXT NOT NULL,
                    source_reference TEXT NOT NULL,
                    citation_text TEXT NOT NULL,
                    data_ledger TEXT,
                    confidence REAL NOT NULL,
                    created_at INTEGER NOT NULL
                );
                """
            )

            # 5. research_theses
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS research_theses (
                    thesis_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    asset_class TEXT NOT NULL,
                    status TEXT NOT NULL,
                    supporting_claims_count INTEGER DEFAULT 0,
                    contradicting_claims_count INTEGER DEFAULT 0,
                    confidence_score REAL NOT NULL,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                """
            )
            conn.commit()

    def detect_source_type(self, url: str) -> SourceType:
        """Deterministically classifies source URL into specific SourceType."""
        u = url.lower().strip()
        parsed = urllib.parse.urlparse(u)
        domain = parsed.netloc.lower()

        if "facebook.com" in domain or "fb.watch" in domain:
            if "/reel/" in u or "/r/" in u:
                return SourceType.FACEBOOK_REEL
            return SourceType.FACEBOOK_VIDEO
        elif "instagram.com" in domain:
            return SourceType.INSTAGRAM_REEL
        elif "youtube.com" in domain or "youtu.be" in domain:
            return SourceType.YOUTUBE_VIDEO
        elif "twitter.com" in domain or "x.com" in domain:
            return SourceType.X_POST
        elif "arxiv.org" in domain:
            return SourceType.ARXIV
        elif "github.com" in domain:
            return SourceType.GITHUB
        elif "tradingview.com" in domain:
            return SourceType.TRADINGVIEW
        elif "reddit.com" in domain:
            return SourceType.REDDIT
        elif "sec.gov" in domain:
            return SourceType.SEC_DOCUMENT
        elif u.endswith(".pdf") or "pdf" in parsed.path.lower():
            return SourceType.PDF
        elif any(news in domain for news in ("bloomberg", "reuters", "coindesk", "cointelegraph", "ft.com", "wsj.com")):
            return SourceType.NEWS
        elif any(sub in domain for sub in ("substack.com", "medium.com")):
            return SourceType.BLOG
        return SourceType.WEB_ARTICLE

    def canonicalize_url(self, raw_url: str) -> tuple[str, str]:
        """Normalizes URL and extracts clean domain."""
        url = raw_url.strip()
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"
        parsed = urllib.parse.urlparse(url)
        clean_url = urllib.parse.urlunparse((
            parsed.scheme,
            parsed.netloc.lower(),
            parsed.path,
            "",
            parsed.query,
            ""
        ))
        return clean_url, parsed.netloc.lower()

    def generate_source_id(self, url: str) -> str:
        url_hash = hashlib.sha256(url.encode()).hexdigest()[:12]
        return f"src_{time.strftime('%Y%m%d')}_{url_hash}"

    def persist_source_record(self, record: ResearchSourceRecord) -> None:
        """Atomic upsert of source identity ensuring link persistence."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO research_sources (
                    source_id, original_url, canonical_url, source_domain, source_type,
                    access_status, extraction_status, title, author_or_creator,
                    publication_date, content_hash, raw_metadata_json, failure_reason,
                    retry_count, wiki_article_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_id) DO UPDATE SET
                    access_status = excluded.access_status,
                    extraction_status = excluded.extraction_status,
                    title = COALESCE(NULLIF(excluded.title, ''), research_sources.title),
                    author_or_creator = COALESCE(NULLIF(excluded.author_or_creator, ''), research_sources.author_or_creator),
                    publication_date = COALESCE(NULLIF(excluded.publication_date, ''), research_sources.publication_date),
                    content_hash = COALESCE(NULLIF(excluded.content_hash, ''), research_sources.content_hash),
                    raw_metadata_json = excluded.raw_metadata_json,
                    failure_reason = excluded.failure_reason,
                    wiki_article_id = COALESCE(NULLIF(excluded.wiki_article_id, ''), research_sources.wiki_article_id),
                    updated_at = excluded.updated_at;
                """,
                (
                    record.source_id,
                    record.original_url,
                    record.canonical_url,
                    record.source_domain,
                    record.source_type,
                    record.access_status,
                    record.extraction_status,
                    record.title,
                    record.author_or_creator,
                    record.publication_date,
                    record.content_hash,
                    json.dumps(record.raw_metadata),
                    record.failure_reason,
                    record.retry_count,
                    record.wiki_article_id,
                    record.created_at,
                    record.updated_at,
                ),
            )
            conn.commit()

    def save_artifact(
        self,
        source_id: str,
        artifact_type: str,
        content_text: str = "",
        content_json: dict | None = None,
        file_path: str = "",
    ) -> str:
        art_id = f"art_{uuid.uuid4().hex[:10]}"
        now = int(time.time() * 1000)
        f_hash = hashlib.sha256(content_text.encode("utf-8", errors="replace")).hexdigest() if content_text else ""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO research_artifacts (
                    artifact_id, source_id, artifact_type, content_text,
                    content_json, file_path, file_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    art_id,
                    source_id,
                    artifact_type,
                    content_text,
                    json.dumps(content_json or {}),
                    file_path,
                    f_hash,
                    now,
                ),
            )
            conn.commit()
        return art_id

    def ingest_url(
        self,
        url: str,
        options: dict[str, Any] | None = None,
    ) -> UniversalIngestionResult:
        """
        Master Ingestion Entrypoint implementing the Link Persistence Invariant.
        """
        opts = options or {}
        custom_title = opts.get("title", "")
        custom_category = opts.get("category", "")
        custom_author = opts.get("author", "")

        canonical_url, domain = self.canonicalize_url(url)
        source_type = self.detect_source_type(canonical_url)
        source_id = self.generate_source_id(canonical_url)

        # ---------------------------------------------------------------------
        # STEP 1: CONSTITUTIONAL INVARIANT — ATOMIC PRE-REGISTRATION
        # ---------------------------------------------------------------------
        now_ms = int(time.time() * 1000)
        source_rec = ResearchSourceRecord(
            source_id=source_id,
            original_url=url,
            canonical_url=canonical_url,
            source_domain=domain,
            source_type=source_type.value,
            access_status=AccessStatus.PARTIAL.value,
            extraction_status=ExtractionStatus.PENDING.value,
            title=custom_title,
            author_or_creator=custom_author,
            created_at=now_ms,
            updated_at=now_ms,
        )
        self.persist_source_record(source_rec)
        logger.info(f"[Link Guarantee] Pre-registered source {source_id} for {canonical_url}")

        artifacts: list[dict[str, Any]] = []
        claims: list[EpistemicClaim] = []
        wiki_article: WikiArticle | None = None
        real_life_summary: RealLifeSummary | None = None

        # ---------------------------------------------------------------------
        # STEP 2: DISPATCH EXTRACTION BY SOURCE TYPE
        # ---------------------------------------------------------------------
        try:
            # Case A: Facebook / Instagram Social Video
            if source_type in (SourceType.FACEBOOK_VIDEO, SourceType.FACEBOOK_REEL, SourceType.INSTAGRAM_REEL):
                source_rec, wiki_article, artifacts, claims, real_life_summary = self._process_facebook_or_social_video(
                    source_rec, opts
                )

            # Case B: YouTube Video
            elif source_type == SourceType.YOUTUBE_VIDEO:
                source_rec, wiki_article, artifacts, claims, real_life_summary = self._process_youtube_video(
                    source_rec, opts
                )

            # Case C: Web Articles, ArXiv, GitHub, TradingView, Generic Web
            else:
                source_rec, wiki_article, artifacts, claims, real_life_summary = self._process_web_document(
                    source_rec, opts
                )

        except Exception as exc:
            logger.error(f"Ingestion pipeline failure for {canonical_url}: {exc}", exc_info=True)
            source_rec.access_status = AccessStatus.FAILED.value
            source_rec.extraction_status = ExtractionStatus.FAILED.value
            source_rec.failure_reason = f"Internal ingestion error: {str(exc)}"
            source_rec.updated_at = int(time.time() * 1000)

            # Guarantee Wiki Placeholder exists even on hard exception
            wiki_article, real_life_summary = self._create_or_update_wiki_record(
                source_rec=source_rec,
                executive_summary=f"Automated ingestion encountered an unhandled exception: {str(exc)}. Source record preserved under Link Guarantee.",
                claims=[],
                raw_text="",
            )

        # ---------------------------------------------------------------------
        # STEP 3: FINAL STATE COMMIT
        # ---------------------------------------------------------------------
        if wiki_article:
            source_rec.wiki_article_id = wiki_article.article_id

        self.persist_source_record(source_rec)

        status_verdict = source_rec.access_status
        msg = (
            f"Successfully ingested and verified in Research Wiki ({wiki_article.article_id if wiki_article else 'NO_ID'})"
            if status_verdict == AccessStatus.SUCCESS.value
            else f"Source preserved under Link Guarantee (Status: {status_verdict}, Reason: {source_rec.failure_reason or 'Partial extraction'})"
        )

        return UniversalIngestionResult(
            source=source_rec,
            wiki_article=wiki_article,
            artifacts=artifacts,
            claims=claims,
            status=status_verdict,
            message=msg,
            real_life_summary=real_life_summary,
        )

    def _process_facebook_or_social_video(
        self,
        source_rec: ResearchSourceRecord,
        opts: dict[str, Any],
    ) -> tuple[ResearchSourceRecord, WikiArticle, list[dict[str, Any]], list[EpistemicClaim], RealLifeSummary]:
        """
        Handles Facebook / Instagram reels & videos with yt-dlp audio extraction,
        Gemini cloud transcription, and OpenGraph metadata fallback.
        Constitutional Invariant: Never hallucinate missing audio or fabricate transcripts.
        """
        artifacts: list[dict[str, Any]] = []
        claims: list[EpistemicClaim] = []

        url = source_rec.canonical_url
        logger.info(f"Processing social video: {url}")

        title_found = opts.get("title", "")
        author_found = opts.get("author", "")
        raw_text = ""
        exec_summary = ""

        # Step 1: Attempt Phase 3 Audio Extraction via yt-dlp
        audio_extracted, audio_path, audio_meta = social_video_extractor.extract_audio(url, timeout=30)
        if audio_extracted and audio_path and audio_path.exists():
            art_id = self.save_artifact(
                source_id=source_rec.source_id,
                artifact_type="AUDIO",
                file_path=str(audio_path),
                content_json=audio_meta,
            )
            artifacts.append({"artifact_id": art_id, "type": "AUDIO"})
            title_found = title_found or audio_meta.get("title", "")
            author_found = author_found or audio_meta.get("uploader", "")

            # Transcribe via Gemini Audio Provider
            transcript_res = gemini_audio_provider.transcribe_audio(audio_path)
            if transcript_res.success and transcript_res.text:
                art_tr_id = self.save_artifact(
                    source_id=source_rec.source_id,
                    artifact_type="TRANSCRIPT",
                    content_text=transcript_res.text,
                    content_json={"provider": transcript_res.provider, "language": transcript_res.language},
                )
                artifacts.append({"artifact_id": art_tr_id, "type": "TRANSCRIPT"})
                source_rec.access_status = AccessStatus.SUCCESS.value
                source_rec.extraction_status = ExtractionStatus.EXTRACTED.value
                raw_text = transcript_res.text
                exec_summary = (
                    f"Spoken audio extracted & transcribed via Gemini ({transcript_res.language}). "
                    f"Content length: {len(raw_text)} chars."
                )

                # Decompose sentences into claims
                for i, seg in enumerate(raw_text.split(". ")[:8]):
                    seg_clean = seg.strip()
                    if len(seg_clean) > 20:
                        claims.append(
                            EpistemicClaim(
                                claim_id=f"C-{i+1:02d}",
                                speaker_claim=seg_clean[:180],
                                epistemic_status="HYPOTHESIS",
                                cross_verification_evidence="Extracted from spoken audio stream.",
                                confidence_score=0.70,
                                empirical_dataset_reference=source_rec.source_domain,
                            )
                        )
                source_rec.title = title_found or f"Social Video Intelligence [{source_rec.source_id}]"
                source_rec.author_or_creator = author_found or "Social Media Creator"
                wiki_article, real_life_summary = self._create_or_update_wiki_record(
                    source_rec=source_rec,
                    executive_summary=exec_summary,
                    claims=claims,
                    raw_text=raw_text,
                )
                return source_rec, wiki_article, artifacts, claims, real_life_summary

        # Step 2: Fallback to OpenGraph and HTML Metadata
        og_description = ""
        is_blocked = False
        block_reason = ""

        try:
            from core.url_extractor import url_extractor

            fetch_res = url_extractor.extract(url)
            if fetch_res.get("success"):
                title_found = title_found or fetch_res.get("title", "")
                author_found = author_found or fetch_res.get("author_creator", "")
                og_description = fetch_res.get("summary", "") or fetch_res.get("text_content", "")
            else:
                is_blocked = True
                block_reason = fetch_res.get("error", "Access restricted / login wall")
        except Exception as e:
            is_blocked = True
            block_reason = str(e)

        # Check if authentication / login wall prevented full media extraction
        if not og_description or len(og_description.strip()) < 30 or "login" in og_description.lower():
            is_blocked = True
            block_reason = (
                "Facebook login wall / private video restriction prevents direct unauthenticated media download. "
                "OpenGraph metadata extracted where available."
            )

        source_rec.title = title_found or f"Facebook Video Intelligence [{source_rec.source_id}]"
        source_rec.author_or_creator = author_found or "Facebook Creator"
        source_rec.raw_metadata = {
            "source_type": source_rec.source_type,
            "domain": source_rec.source_domain,
            "og_description": og_description[:500] if og_description else "",
            "media_probe": "yt-dlp / metadata inspected",
        }

        # Store metadata artifact
        art_id = self.save_artifact(
            source_id=source_rec.source_id,
            artifact_type="METADATA",
            content_text=og_description or "Social media video metadata placeholder",
            content_json=source_rec.raw_metadata,
        )
        artifacts.append({"artifact_id": art_id, "type": "METADATA"})

        if is_blocked:
            source_rec.access_status = AccessStatus.ACCESS_BLOCKED.value
            source_rec.extraction_status = ExtractionStatus.BLOCKED.value
            source_rec.failure_reason = block_reason

            exec_summary = (
                f"**Source Identity Preserved:** Video from `{source_rec.source_domain}`.\n\n"
                f"⚠️ **Access Status: ACCESS_BLOCKED**\n"
                f"• **Reason:** {block_reason}\n"
                f"• **Resolution:** Source record and Wiki entry permanently created under the Link Persistence Invariant. "
                f"User can attach a local audio/transcript file to `{source_rec.source_id}` to trigger complete epistemic analysis without losing provenance."
            )

            # Minimal placeholder claims to explain status
            claims.append(
                EpistemicClaim(
                    claim_id="C-01",
                    speaker_claim=f"Video media at {url} requires authorized access or manual transcript upload.",
                    epistemic_status="UNVERIFIED",
                    cross_verification_evidence="Direct automated media download restricted by platform policy.",
                    confidence_score=0.10,
                    empirical_dataset_reference="Platform Access Control Ledger",
                )
            )
        else:
            source_rec.access_status = AccessStatus.PARTIAL.value
            source_rec.extraction_status = ExtractionStatus.EXTRACTED.value
            exec_summary = f"Metadata extraction succeeded for social video. Summary: {og_description[:300]}"

        # Generate & Persist Wiki Article and RealLifeSummary
        wiki_article, real_life_summary = self._create_or_update_wiki_record(
            source_rec=source_rec,
            executive_summary=exec_summary,
            claims=claims,
            raw_text=og_description,
        )

        return source_rec, wiki_article, artifacts, claims, real_life_summary

    def _process_youtube_video(
        self,
        source_rec: ResearchSourceRecord,
        opts: dict[str, Any],
    ) -> tuple[ResearchSourceRecord, WikiArticle, list[dict[str, Any]], list[EpistemicClaim], RealLifeSummary]:
        """Handles YouTube video transcripts and audio extraction fallback."""
        artifacts: list[dict[str, Any]] = []
        claims: list[EpistemicClaim] = []
        from core.youtube_extractor import youtube_extractor

        yt_res = youtube_extractor.extract_full_video_research(source_rec.canonical_url)

        if yt_res.get("success"):
            source_rec.title = opts.get("title") or yt_res.get("title") or source_rec.title
            source_rec.author_or_creator = (
                opts.get("author") or yt_res.get("author_creator") or source_rec.author_or_creator
            )
            source_rec.access_status = AccessStatus.SUCCESS.value
            source_rec.extraction_status = ExtractionStatus.EXTRACTED.value
            raw_body = yt_res.get("full_transcript") or yt_res.get("description", "")

            # Save raw transcript artifact
            art_id = self.save_artifact(
                source_id=source_rec.source_id,
                artifact_type="TRANSCRIPT",
                content_text=raw_body,
                content_json={"duration": yt_res.get("duration_formatted", "")},
            )
            artifacts.append({"artifact_id": art_id, "type": "TRANSCRIPT"})

            hype = yt_res.get("hype_markers", [])
            segments = yt_res.get("segments", [])
            for i, seg in enumerate(segments[:8]):
                seg_text = seg.get("text", "").strip()
                if len(seg_text) < 15:
                    continue
                is_hype = any(hk.lower() in seg_text.lower() for hk in hype)
                claims.append(
                    EpistemicClaim(
                        claim_id=f"C-{i+1:02d}",
                        speaker_claim=seg_text[:180],
                        epistemic_status="NARRATIVE" if is_hype else "HYPOTHESIS",
                        cross_verification_evidence="Extracted from spoken video transcript; awaiting quantitative backtest.",
                        confidence_score=0.45 if is_hype else 0.75,
                        empirical_dataset_reference="YouTube Spoken Transcript Ledger",
                    )
                )

            exec_summary = (
                f"Full spoken video transcript extracted for '{source_rec.title}' by {source_rec.author_or_creator}. "
                f"Decomposed into {len(claims)} verifiable claims."
            )
        else:
            # Fallback to direct audio download and transcription via Gemini
            audio_extracted, audio_path, audio_meta = social_video_extractor.extract_audio(
                source_rec.canonical_url, timeout=30
            )
            if audio_extracted and audio_path and audio_path.exists():
                art_id = self.save_artifact(
                    source_id=source_rec.source_id,
                    artifact_type="AUDIO",
                    file_path=str(audio_path),
                    content_json=audio_meta,
                )
                artifacts.append({"artifact_id": art_id, "type": "AUDIO"})
                transcript_res = gemini_audio_provider.transcribe_audio(audio_path)
                if transcript_res.success and transcript_res.text:
                    art_tr_id = self.save_artifact(
                        source_id=source_rec.source_id,
                        artifact_type="TRANSCRIPT",
                        content_text=transcript_res.text,
                        content_json={"provider": transcript_res.provider},
                    )
                    artifacts.append({"artifact_id": art_tr_id, "type": "TRANSCRIPT"})
                    source_rec.access_status = AccessStatus.SUCCESS.value
                    source_rec.extraction_status = ExtractionStatus.EXTRACTED.value
                    raw_body = transcript_res.text
                    exec_summary = f"Spoken YouTube audio transcribed via Gemini ({len(raw_body)} chars)."
                    for i, seg in enumerate(raw_body.split(". ")[:8]):
                        s_c = seg.strip()
                        if len(s_c) > 20:
                            claims.append(
                                EpistemicClaim(
                                    claim_id=f"C-{i+1:02d}",
                                    speaker_claim=s_c[:180],
                                    epistemic_status="HYPOTHESIS",
                                    cross_verification_evidence="Transcribed from spoken YouTube audio stream.",
                                    confidence_score=0.75,
                                    empirical_dataset_reference="YouTube Audio Ledger",
                                )
                            )
                else:
                    source_rec.access_status = AccessStatus.PARTIAL.value
                    source_rec.extraction_status = ExtractionStatus.PARTIAL.value
                    source_rec.failure_reason = f"Audio downloaded, transcription failed: {transcript_res.error}"
                    raw_body = ""
                    exec_summary = f"Audio extracted from YouTube; transcription pending ({transcript_res.error})."
            else:
                source_rec.access_status = AccessStatus.PARTIAL.value
                source_rec.extraction_status = ExtractionStatus.FAILED.value
                source_rec.failure_reason = yt_res.get(
                    "error", "Transcript and audio extraction unavailable"
                )
                raw_body = ""
                exec_summary = f"YouTube video metadata registered. Transcript was not accessible: {source_rec.failure_reason}."

        wiki_article, real_life_summary = self._create_or_update_wiki_record(
            source_rec=source_rec,
            executive_summary=exec_summary,
            claims=claims,
            raw_text=raw_body,
        )
        return source_rec, wiki_article, artifacts, claims, real_life_summary

    def _process_web_document(
        self,
        source_rec: ResearchSourceRecord,
        opts: dict[str, Any],
    ) -> tuple[ResearchSourceRecord, WikiArticle, list[dict[str, Any]], list[EpistemicClaim], RealLifeSummary]:
        """Handles generic articles, ArXiv, GitHub, and financial blogs."""
        artifacts: list[dict[str, Any]] = []
        claims: list[EpistemicClaim] = []
        from core.url_extractor import url_extractor

        url_res = url_extractor.extract(source_rec.canonical_url)

        if url_res.get("success"):
            source_rec.title = opts.get("title") or url_res.get("title") or source_rec.title
            source_rec.author_or_creator = (
                opts.get("author") or url_res.get("author_creator") or source_rec.author_or_creator
            )
            source_rec.access_status = AccessStatus.SUCCESS.value
            source_rec.extraction_status = ExtractionStatus.EXTRACTED.value
            raw_body = url_res.get("text_content") or ""

            art_id = self.save_artifact(
                source_id=source_rec.source_id,
                artifact_type="RAW_TEXT",
                content_text=raw_body,
                content_json={"summary": url_res.get("summary", "")},
            )
            artifacts.append({"artifact_id": art_id, "type": "RAW_TEXT"})

            # Parse key claim paragraphs
            paragraphs = [p.strip() for p in raw_body.split("\n") if len(p.strip()) > 40]
            for i, p in enumerate(paragraphs[:8]):
                claims.append(
                    EpistemicClaim(
                        claim_id=f"C-{i+1:02d}",
                        speaker_claim=p[:200],
                        epistemic_status=(
                            "FACT"
                            if any(
                                w in p.lower()
                                for w in ("data shows", "percent", "recorded", "according to")
                            )
                            else "HYPOTHESIS"
                        ),
                        cross_verification_evidence="Synthesized from primary document text.",
                        confidence_score=0.80,
                        empirical_dataset_reference=source_rec.source_domain,
                    )
                )

            exec_summary = (
                url_res.get("summary")
                or f"Research article from {source_rec.source_domain}. Content extracted: {len(raw_body)} characters."
            )
        else:
            source_rec.access_status = (
                AccessStatus.ACCESS_BLOCKED.value
                if "403" in url_res.get("error", "") or "blocked" in url_res.get("error", "").lower()
                else AccessStatus.PARTIAL.value
            )
            source_rec.extraction_status = ExtractionStatus.FAILED.value
            source_rec.failure_reason = url_res.get("error", "Extraction failed")
            raw_body = ""
            exec_summary = (
                f"Web resource preserved under Link Guarantee. Fetch error: {source_rec.failure_reason}."
            )

        wiki_article, real_life_summary = self._create_or_update_wiki_record(
            source_rec=source_rec,
            executive_summary=exec_summary,
            claims=claims,
            raw_text=raw_body,
        )
        return source_rec, wiki_article, artifacts, claims, real_life_summary

    def _synthesize_real_life_summary(
        self,
        source_rec: ResearchSourceRecord,
        executive_summary: str,
        claims: list[EpistemicClaim],
        raw_text: str,
    ) -> RealLifeSummary:
        """
        Synthesizes an actionable, real-life Bengali summary with 5 core perspectives:
        1. সহজ বাংলায় মূল বক্তব্য (Core takeaway)
        2. মার্কেট ও ক্রিপ্টোতে বাস্তব প্রভাব (Market impact)
        3. একজন ট্রেডার বা গবেষকের জন্য বাস্তব করণীয় (Actionable guidance)
        4. হাইপ বনাম বাস্তবতা চেক (Hype vs reality check)
        5. ঝুঁকি ও সতর্কতা (Risk warning)
        """
        # Step 1: Try Gemini API if key is available
        api_key = os.getenv("GEMINI_API_KEY", "")
        if api_key and (raw_text or executive_summary):
            try:
                import requests

                content_for_llm = raw_text[:3000] if raw_text else executive_summary[:1500]
                prompt = (
                    "You are the Senior Quantitative Analyst and Pedagogical Mentor of CBT. "
                    "Analyze the following research content and provide a practical 'Real-Life Summary' (বাস্তব জীবনের সারসংক্ষেপ) in Bengali. "
                    "You must return ONLY a valid JSON object with the following exact keys:\n"
                    "{\n"
                    '  "core_concept_bn": "সহজ বাংলায় মূল বক্তব্য (১-২ বাক্যে মূল থিম)",\n'
                    '  "practical_market_impact": "মার্কেট ও ক্রিপ্টোতে বাস্তব প্রভাব (লিকুইডিটি, প্রাইস বা সেন্টিমেন্টে কী প্রভাব পড়বে)",\n'
                    '  "actionable_guidance": "একজন ট্রেডার বা গবেষকের জন্য বাস্তব করণীয় (কী দেখতে হবে, কী কৌশল অবলম্বন করা উচিত)",\n'
                    '  "hype_vs_reality": "হাইপ বনাম বাস্তবতা চেক (সোশ্যাল মিডিয়ার অতিরিক্ত আশা বনাম বাস্তব পরিসংখ্যান)",\n'
                    '  "risk_warning": "ঝুঁকি ও সতর্কতা (ক্যাপিটাল রিক্স, লিকুইডেশন, বা সম্ভাব্য ক্ষতি)"\n'
                    "}\n\n"
                    f"Content Title: {source_rec.title}\n"
                    f"Source: {source_rec.source_domain} ({source_rec.source_type})\n"
                    f"Content:\n{content_for_llm}"
                )
                payload = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.2, "response_mime_type": "application/json"},
                }
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
                resp = requests.post(url, json=payload, timeout=20.0)
                if resp.status_code == 200:
                    data = resp.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        text_resp = "".join(p.get("text", "") for p in parts)
                        parsed = json.loads(text_resp)
                        if all(
                            k in parsed
                            for k in (
                                "core_concept_bn",
                                "practical_market_impact",
                                "actionable_guidance",
                                "hype_vs_reality",
                                "risk_warning",
                            )
                        ):
                            return RealLifeSummary(
                                core_concept_bn=parsed["core_concept_bn"].strip(),
                                practical_market_impact=parsed["practical_market_impact"].strip(),
                                actionable_guidance=parsed["actionable_guidance"].strip(),
                                hype_vs_reality=parsed["hype_vs_reality"].strip(),
                                risk_warning=parsed["risk_warning"].strip(),
                            )
            except Exception as e:
                logger.debug(f"Gemini RealLifeSummary synthesis fallback: {e}")

        # Step 2: High-Quality Deterministic Domain-Aware Synthesis Fallback
        text_corpus = f"{source_rec.title} {executive_summary} {raw_text}".lower()
        is_blocked = source_rec.access_status == AccessStatus.ACCESS_BLOCKED.value

        is_crypto = any(
            k in text_corpus
            for k in ("btc", "bitcoin", "eth", "ethereum", "sol", "crypto", "token", "altcoin")
        )
        is_macro = any(
            k in text_corpus
            for k in ("fed", "fomc", "rate", "inflation", "cpi", "liquidity", "recession", "gdp")
        )
        is_smc = any(
            k in text_corpus
            for k in ("fvg", "liquidity sweep", "order block", "orderflow", "cvd", "structure", "smc")
        )

        num_facts = sum(1 for c in claims if c.epistemic_status == "FACT")
        num_hype = sum(1 for c in claims if c.epistemic_status in ("NARRATIVE", "UNVERIFIED"))

        if is_blocked:
            core_bn = (
                f"উৎসটি ({source_rec.source_domain}) প্ল্যাটফর্মের লগইন রিকোয়ারমেন্ট বা প্রাইভেসি পলিসির কারণে সম্পূর্ণ মিডিয়া স্ট্রিম সরাসরি পড়তে দেয়নি। "
                f"তবে সোর্স রেকর্ড `{source_rec.source_id}` অপরিবর্তনযোগ্যভাবে উইকি ডেটাবেজে সংরক্ষিত রয়েছে।"
            )
            impact_bn = (
                "অন-চেইন ডেটা ও সরাসরি ভেরিফিকেশন ছাড়া সোশ্যাল মিডিয়া ভিডিওর তথ্যে তাৎক্ষণিক মার্কেটে কোনো প্রমাণিত মৌলিক প্রভাব নেই; এটি প্রধানত রিটেইল সেন্টিমেন্ট তৈরি করতে পারে।"
            )
            guidance_bn = (
                f"সোর্স আইডি `{source_rec.source_id}`-তে লোকাল অডিও বা ট্রান্সক্রিপ্ট টেক্সট আপলোড করে পূর্ণাঙ্গ এনালাইসিস চালান। কোনো অবস্থাতেই যাচাই ছাড়া এই কন্টেন্ট দেখে ট্রেডিং সিদ্ধান্ত নেবেন না।"
            )
            hype_bn = (
                "সোশ্যাল মিডিয়ায় শেয়ার করা ভিডিওগুলোতে প্রায়ই অতিরঞ্জিত মুনাফার দাবি থাকে। সিবিটি এভিডেন্স ইঞ্জিনে টেস্ট না করা পর্যন্ত এটিকে খাঁটি হাইপ হিসেবে বিবেচনা করুন।"
            )
            risk_bn = (
                "অযাচাইকৃত সোশ্যাল সিগন্যাল বা হাইপে ট্রেড করলে হাই লিভারেজে সম্পূর্ণ অ্যাকাউন্ট লিকুইডেশনের চরম ঝুঁকি থাকে।"
            )
        elif is_crypto or is_smc:
            entity_label = "বিটকয়েন ও ক্রিপ্টোকারেন্সি" if is_crypto else "স্মার্ট মানি ও মার্কেট স্ট্রাকচার"
            core_bn = (
                f"এই গবেষণাপত্রে {entity_label} সম্পর্কিত ট্রেন্ড, লিকুইডিটি ফ্লো এবং মূল্যের গতিবিধি বিশ্লেষণ করা হয়েছে ({source_rec.title or 'Research Entry'})।"
            )
            impact_bn = (
                f"মার্কেটে তাৎক্ষণিক ভোলাটিলিটি বা অর্ডারবুকের ডেপথ পরিবর্তনের সম্ভাবনা রয়েছে। {f'{num_facts}টি ফ্যাক্ট ও {num_hype}টি ন্যারেটিভ শনাক্ত করা হয়েছে।' if claims else 'মার্কেট স্ট্রাকচার পরীক্ষা সাপেক্ষ।'}"
            )
            guidance_bn = (
                "হাফ-কেলি (Half-Kelly) পজিশন সাইজিং মেনে চলুন। ক্যান্ডেল ক্লোজ হওয়ার আগে এবং সিভিডি (CVD) কনফার্মেশন ছাড়া কোনো রিভার্সাল বা ব্রেকআউটে এন্ট্রি নেবেন না।"
            )
            hype_bn = (
                "যদি কোনো কন্টেন্টে ১০০% উইন রেট বা গ্যারান্টিড প্রফিটের দাবি থাকে, তবে তা পরিসংখ্যানগতভাবে অসম্ভব। কেবল হিস্টোরিক্যাল ব্যাকটেস্ট ও আউট-অফ-স্যাম্পল রেজাল্টকেই বিশ্বাস করুন।"
            )
            risk_bn = (
                "ম্যাক্রো ইভেন্ট (CPI, FOMC) চলাকালীন স্প্রেড বড় হতে পারে এবং স্টপ-হান্ট হতে পারে। সর্বোচ্চ ২.৫% ইকুইটি রিক্সের বেশি কোনো অবস্থাতে এক্সপোজ করবেন না।"
            )
        elif is_macro:
            core_bn = (
                f"এটি ম্যাক্রো-ইকোনমিক ফ্যাক্টর এবং আর্থিক তারল্য সংক্রান্ত বিশ্লেষণ ({source_rec.title or 'Macro Dossier'})।"
            )
            impact_bn = (
                "কেন্দ্রীয় ব্যাংকের নীতি ও বৈশ্বিক লিকুইডিটি পরিবর্তনের সরাসরি প্রভাব ক্রিপ্টো ও গ্লোবাল ইক্যুইটি মার্কেটে পরিলক্ষিত হতে পারে।"
            )
            guidance_bn = (
                "ম্যাক্রো ডেটা রিলিজের পর ইমপ্যাক্ট ফিল্টারে সারপ্রাইজ ডেল্টা (Surprise Delta) যাচাই করুন এবং উইকি ডাটাবেজে অন্যান্য পলিসির সাথে ক্রস-রেফারেন্স করুন।"
            )
            hype_bn = (
                "সংবাদমাধ্যমের তাৎক্ষণিক হেডলাইন অনেক সময় মার্কেট রিয়েকশনের সাথে মেলে না; প্রাতিষ্ঠানিক ফ্লো দেখতে FED ব্যালেন্স শিট ও নেট লিকুইডিটি ট্র্যাক করুন।"
            )
            risk_bn = (
                "ম্যাক্রো শকে আকস্মিক লিকুইডিটি ক্রাঞ্চ দেখা দিলে অল্টকয়েনগুলোতে বড় ড্রডাউন হতে পারে।"
            )
        else:
            core_bn = (
                f"উৎস থেকে প্রাপ্ত তথ্য পর্যালোচনা: {source_rec.title or 'Research Entry'}। ডকুমেন্টে মোট {len(claims)}টি যাচাইযোগ্য দাবি অন্তর্ভুক্ত রয়েছে।"
            )
            impact_bn = (
                "কন্টেন্টটি থিওরিটিক্যাল বা স্ট্র্যাটেজিক বুদ্ধিমত্তা বৃদ্ধি করে; সরাসরি মার্কেট এক্সিকিউশনের পূর্বে এটিকে সিবিটি রিসার্চ ল্যাবে ব্যাকটেস্ট করা প্রয়োজন।"
            )
            guidance_bn = (
                "ধারণাগুলোকে অ্যালগরিদমিক নিয়মে রূপান্তর করুন এবং `/test` কমান্ড দিয়ে সিমুলেটেড ওয়াক-ফরোয়ার্ড ভ্যালিডেশন সম্পন্ন করুন।"
            )
            hype_bn = (
                f"উৎসটিতে {num_hype}টি ন্যারেটিভ রয়েছে যা এখনো অন-মার্কেট ডেটায় প্রমাণিত নয়; কেবল {num_facts}টি দাবি সরাসরি তথ্যের সাথে সঙ্গতিপূর্ণ।"
            )
            risk_bn = (
                "তত্ত্ব বা কাগজের রিসার্চ সবসময় লাইভ মার্কেটের স্লিপেজ ও ফি-র সাথে মেলে না। ৩-টায়ার কস্ট মডেলিং ছাড়া ক্যাপিটাল ঝুঁকিতে ফেলা যাবে না।"
            )

        return RealLifeSummary(
            core_concept_bn=core_bn,
            practical_market_impact=impact_bn,
            actionable_guidance=guidance_bn,
            hype_vs_reality=hype_bn,
            risk_warning=risk_bn,
        )

    def _create_or_update_wiki_record(
        self,
        source_rec: ResearchSourceRecord,
        executive_summary: str,
        claims: list[EpistemicClaim],
        raw_text: str,
        real_life_summary: RealLifeSummary | None = None,
    ) -> tuple[WikiArticle, RealLifeSummary]:
        """
        Creates or updates a permanent Wiki article referencing the source identity.
        Persists claims into the relational `research_claims` table as well.
        Synthesizes and embeds the actionable RealLifeSummary.
        """
        now = int(time.time() * 1000)
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", (source_rec.title or "research").lower()).strip("_")[:28]
        article_id = f"wiki_{int(time.time())}_{slug or uuid.uuid4().hex[:6]}"
        provenance_id = f"[SRC-{source_rec.source_id.upper()}]"

        # Synthesize real-life summary if not provided
        if not real_life_summary:
            real_life_summary = self._synthesize_real_life_summary(
                source_rec=source_rec,
                executive_summary=executive_summary,
                claims=claims,
                raw_text=raw_text,
            )

        # Persist RealLifeSummary artifact
        self.save_artifact(
            source_id=source_rec.source_id,
            artifact_type="REAL_LIFE_SUMMARY",
            content_text=real_life_summary.to_markdown(),
            content_json=real_life_summary.to_dict(),
        )

        # Compute verification score
        if claims:
            verified_count = sum(1 for c in claims if c.epistemic_status in ("FACT", "HYPOTHESIS"))
            score = round((verified_count / len(claims)) * 100.0, 1)
        else:
            score = 10.0 if source_rec.access_status == AccessStatus.ACCESS_BLOCKED.value else 50.0

        markdown_content = f"""# {source_rec.title or 'Research Intelligence Entry'}

## Source Dossier
- **Original URL:** [{source_rec.original_url}]({source_rec.original_url})
- **Source ID:** `{source_rec.source_id}`
- **Source Type:** `{source_rec.source_type}`
- **Author / Speaker:** `{source_rec.author_or_creator or 'Unknown'}`
- **Access Status:** `{source_rec.access_status}`
- **Extraction Status:** `{source_rec.extraction_status}`
- **Provenance ID:** `{provenance_id}`

## Executive Summary
{executive_summary}

{real_life_summary.to_markdown()}

## Key Epistemic Claims
| Claim ID | Speaker Claim | Epistemic Status | Confidence | Empirical Dataset |
|:---|:---|:---:|:---:|:---|
"""
        for c in claims:
            markdown_content += f"| `{c.claim_id}` | {c.speaker_claim} | **{c.epistemic_status}** | {c.confidence_score:.2f} | {c.empirical_dataset_reference} |\n"

        if source_rec.failure_reason:
            markdown_content += f"\n## Ingestion Diagnostics & Access Limitations\n- **Diagnostic Details:** {source_rec.failure_reason}\n- **Resolution:** Attach clean transcript or audio payload directly to `{source_rec.source_id}`.\n"

        markdown_content += f"\n## Related Concepts\n- [[Macro Geopolitics]]\n- [[CBT Intelligence]]\n- [[Liquidity Analysis]]\n"

        article = WikiArticle(
            article_id=article_id,
            title=source_rec.title or "Research Intelligence Entry",
            category="Macro Intelligence & Research",
            source_url=source_rec.original_url,
            source_type=source_rec.source_type,
            provenance_id=provenance_id,
            author_or_speaker=source_rec.author_or_creator,
            executive_summary=executive_summary,
            key_claims=claims,
            wikilinks=["[[Macro Geopolitics]]", "[[CBT Intelligence]]"],
            tags=["ResearchLab", source_rec.source_type.lower(), source_rec.access_status.lower()],
            contradictions_detected=[],
            macro_regime_implications="Empirical candidate recorded under Link Persistence Invariant.",
            full_markdown_content=markdown_content,
            verification_score=score,
            created_at=now,
            updated_at=now,
        )

        # 1. Save Wiki article to SQLite & Markdown files
        research_wikipedia_engine.save_article(article)

        # 2. Persist claims relationally in research_claims
        with self._get_connection() as conn:
            for c in claims:
                conn.execute(
                    """
                    INSERT INTO research_claims (
                        claim_id, source_id, wiki_article_id, speaker_claim,
                        claim_type, speaker, timestamp_marker, time_period,
                        confidence_score, verification_status, cross_verification_evidence,
                        empirical_dataset_reference, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(claim_id) DO UPDATE SET
                        verification_status = excluded.verification_status,
                        confidence_score = excluded.confidence_score;
                    """,
                    (
                        f"{source_rec.source_id}_{c.claim_id}",
                        source_rec.source_id,
                        article.article_id,
                        c.speaker_claim,
                        c.epistemic_status,
                        source_rec.author_or_creator,
                        "",
                        "",
                        c.confidence_score,
                        c.epistemic_status,
                        c.cross_verification_evidence,
                        c.empirical_dataset_reference,
                        now,
                    ),
                )
            conn.commit()

        # 3. Post-Ingestion Epistemic Verification & Knowledge Graph Extraction
        try:
            from core.knowledge_os.claim_verifier import claim_verifier
            from core.knowledge_os.knowledge_graph import knowledge_graph_engine
            from core.knowledge_os.thesis_engine import thesis_engine

            # Extract entities from source text & summary
            entities = knowledge_graph_engine.extract_entities_from_text(
                f"{source_rec.title} {executive_summary} {raw_text[:1000]}"
            )
            # Create co-occurrence relations between detected entities
            if len(entities) >= 2:
                for i in range(len(entities) - 1):
                    knowledge_graph_engine.add_relation(
                        source_name_or_id=entities[i].entity_id,
                        target_name_or_id=entities[i + 1].entity_id,
                        relation_type="INFLUENCES",
                        weight=0.75,
                        source_id=source_rec.source_id,
                        description=f"Co-occurred in {source_rec.title}",
                    )

            # Verify claims and cluster to institutional theses
            for c in claims:
                full_cid = f"{source_rec.source_id}_{c.claim_id}"
                claim_verifier.verify_claim(full_cid)
                thesis_engine.auto_cluster_claim_to_theses(full_cid, c.speaker_claim)
        except Exception as e:
            logger.debug(f"Post-ingestion epistemic graph hook error (non-fatal): {e}")

        return article, real_life_summary


# Singleton instance
universal_ingestor = UniversalIngestor()
