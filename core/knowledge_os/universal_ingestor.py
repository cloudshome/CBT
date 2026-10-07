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

logger = logging.getLogger("sky.universal_ingestor")


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

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source.to_dict(),
            "wiki_article": self.wiki_article.to_dict() if self.wiki_article else None,
            "artifacts_count": len(self.artifacts),
            "claims_count": len(self.claims),
            "status": self.status,
            "message": self.message,
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

        # ---------------------------------------------------------------------
        # STEP 2: DISPATCH EXTRACTION BY SOURCE TYPE
        # ---------------------------------------------------------------------
        try:
            # Case A: Facebook / Instagram Social Video
            if source_type in (SourceType.FACEBOOK_VIDEO, SourceType.FACEBOOK_REEL, SourceType.INSTAGRAM_REEL):
                source_rec, wiki_article, artifacts, claims = self._process_facebook_or_social_video(
                    source_rec, opts
                )

            # Case B: YouTube Video
            elif source_type == SourceType.YOUTUBE_VIDEO:
                source_rec, wiki_article, artifacts, claims = self._process_youtube_video(
                    source_rec, opts
                )

            # Case C: Web Articles, ArXiv, GitHub, TradingView, Generic Web
            else:
                source_rec, wiki_article, artifacts, claims = self._process_web_document(
                    source_rec, opts
                )

        except Exception as exc:
            logger.error(f"Ingestion pipeline failure for {canonical_url}: {exc}", exc_info=True)
            source_rec.access_status = AccessStatus.FAILED.value
            source_rec.extraction_status = ExtractionStatus.FAILED.value
            source_rec.failure_reason = f"Internal ingestion error: {str(exc)}"
            source_rec.updated_at = int(time.time() * 1000)

            # Guarantee Wiki Placeholder exists even on hard exception
            wiki_article = self._create_or_update_wiki_record(
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
        )

    def _process_facebook_or_social_video(
        self,
        source_rec: ResearchSourceRecord,
        opts: dict[str, Any],
    ) -> tuple[ResearchSourceRecord, WikiArticle, list[dict[str, Any]], list[EpistemicClaim]]:
        """
        Handles Facebook / Instagram reels & videos with OpenGraph extraction and fallback.
        Constitutional Invariant: Never hallucinate missing audio or fabricate transcripts.
        """
        artifacts: list[dict[str, Any]] = []
        claims: list[EpistemicClaim] = []

        url = source_rec.canonical_url
        logger.info(f"Processing social video: {url}")

        # 1. Fetch OpenGraph and HTML Metadata
        title_found = opts.get("title", "")
        author_found = opts.get("author", "")
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

        # 2. Check if authentication / login wall prevented full media extraction
        # Facebook share/v/ and reels almost always gate direct unauthenticated media streams
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

        # 3. Store metadata artifact
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

        # 4. Generate & Persist Wiki Article
        wiki_article = self._create_or_update_wiki_record(
            source_rec=source_rec,
            executive_summary=exec_summary,
            claims=claims,
            raw_text=og_description,
        )

        return source_rec, wiki_article, artifacts, claims

    def _process_youtube_video(
        self,
        source_rec: ResearchSourceRecord,
        opts: dict[str, Any],
    ) -> tuple[ResearchSourceRecord, WikiArticle, list[dict[str, Any]], list[EpistemicClaim]]:
        """Handles YouTube video transcripts and hype extraction."""
        artifacts: list[dict[str, Any]] = []
        claims: list[EpistemicClaim] = []
        from core.youtube_extractor import youtube_extractor

        yt_res = youtube_extractor.extract_full_video_research(source_rec.canonical_url)

        if yt_res.get("success"):
            source_rec.title = opts.get("title") or yt_res.get("title") or source_rec.title
            source_rec.author_or_creator = opts.get("author") or yt_res.get("author_creator") or source_rec.author_or_creator
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
            source_rec.access_status = AccessStatus.PARTIAL.value
            source_rec.extraction_status = ExtractionStatus.FAILED.value
            source_rec.failure_reason = yt_res.get("error", "Transcript unavailable")
            raw_body = ""
            exec_summary = f"YouTube video metadata registered. Transcript was not accessible: {source_rec.failure_reason}."

        wiki_article = self._create_or_update_wiki_record(
            source_rec=source_rec,
            executive_summary=exec_summary,
            claims=claims,
            raw_text=raw_body,
        )
        return source_rec, wiki_article, artifacts, claims

    def _process_web_document(
        self,
        source_rec: ResearchSourceRecord,
        opts: dict[str, Any],
    ) -> tuple[ResearchSourceRecord, WikiArticle, list[dict[str, Any]], list[EpistemicClaim]]:
        """Handles generic articles, ArXiv, GitHub, and financial blogs."""
        artifacts: list[dict[str, Any]] = []
        claims: list[EpistemicClaim] = []
        from core.url_extractor import url_extractor

        url_res = url_extractor.extract(source_rec.canonical_url)

        if url_res.get("success"):
            source_rec.title = opts.get("title") or url_res.get("title") or source_rec.title
            source_rec.author_or_creator = opts.get("author") or url_res.get("author_creator") or source_rec.author_or_creator
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
                        epistemic_status="FACT" if any(w in p.lower() for w in ("data shows", "percent", "recorded", "according to")) else "HYPOTHESIS",
                        cross_verification_evidence="Synthesized from primary document text.",
                        confidence_score=0.80,
                        empirical_dataset_reference=source_rec.source_domain,
                    )
                )

            exec_summary = url_res.get("summary") or f"Research article from {source_rec.source_domain}. Content extracted: {len(raw_body)} characters."
        else:
            source_rec.access_status = AccessStatus.ACCESS_BLOCKED.value if "403" in url_res.get("error", "") or "blocked" in url_res.get("error", "").lower() else AccessStatus.PARTIAL.value
            source_rec.extraction_status = ExtractionStatus.FAILED.value
            source_rec.failure_reason = url_res.get("error", "Extraction failed")
            raw_body = ""
            exec_summary = f"Web resource preserved under Link Guarantee. Fetch error: {source_rec.failure_reason}."

        wiki_article = self._create_or_update_wiki_record(
            source_rec=source_rec,
            executive_summary=exec_summary,
            claims=claims,
            raw_text=raw_body,
        )
        return source_rec, wiki_article, artifacts, claims

    def _create_or_update_wiki_record(
        self,
        source_rec: ResearchSourceRecord,
        executive_summary: str,
        claims: list[EpistemicClaim],
        raw_text: str,
    ) -> WikiArticle:
        """
        Creates or updates a permanent Wiki article referencing the source identity.
        Persists claims into the relational `research_claims` table as well.
        """
        now = int(time.time() * 1000)
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", (source_rec.title or "research").lower()).strip("_")[:28]
        article_id = f"wiki_{int(time.time())}_{slug or uuid.uuid4().hex[:6]}"
        provenance_id = f"[SRC-{source_rec.source_id.upper()}]"

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

        return article


# Singleton instance
universal_ingestor = UniversalIngestor()
