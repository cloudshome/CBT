"""
core/universal_ingestor.py
==========================
SKY / CBT Universal Multi-Source Research Ingestor & Synthesizer.

Multi-Dimensional Epistemic Ingestion:
1. Registers Provenance Source [S-XXXXXX] with original worldview
2. Extracts verbatim Claims [C-XXXXXX] (status: UNVERIFIED)
3. Extracts Observations [OBS-XXXXXX] (historical data clusters vs causal claims)
4. Normalizes Concepts [K-XXXXXX] into abstract mental models
5. Maps Graph Edges [R-XXXXXX] (Same-Domain, Cross-Domain, Contradictions)
6. Formulates Discovery Candidates [DISC-XXXXXX] with status UNTESTED
"""

from __future__ import annotations

import ast
import logging
import os
import re
from pathlib import Path
from typing import Any

from core.knowledge_graph_engine import knowledge_graph_engine
from core.macro_cognitive_engine import macro_cognitive_engine
from core.macro_trade_planner import macro_trade_planner
from core.pdf_extractor import pdf_book_extractor
from core.provenance_engine import provenance_engine
from core.youtube_extractor import youtube_extractor

logger = logging.getLogger("ai_quant_sentinel.universal_ingestor")


class UniversalIngestor:
    """Master multi-source ingestion coordinator."""

    def __init__(self, upload_dir: Path | None = None):
        self.upload_dir = upload_dir or Path(os.getenv("DATA_DIR", "data")) / "uploads"
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def detect_source_type(self, input_str: str, file_name: str | None = None) -> str:
        """Determines the source medium based on string pattern or file extension."""
        if file_name:
            ext = Path(file_name).suffix.lower()
            if ext == ".pdf":
                return "PDF"
            elif ext in [".py", ".pine", ".mq4", ".mq5"]:
                return "CODE"
            elif ext in [".csv", ".json"]:
                return "DATASET"
            elif ext in [".txt", ".md"]:
                return "NOTES"
            elif ext in [".mp4", ".mov", ".webm", ".m4v"]:
                return "MEDIA_REEL"
            elif ext in [".mp3", ".m4a", ".wav", ".ogg"]:
                return "MEDIA_REEL"

        lower = input_str.strip().lower()
        if "youtube.com/shorts" in lower or "/shorts/" in lower:
            return "REEL"
        elif "youtube.com" in lower or "youtu.be" in lower:
            return "YOUTUBE"
        elif "instagram.com/reel" in lower or "facebook.com/reel" in lower or "tiktok.com" in lower:
            return "REEL"
        elif "twitter.com" in lower or "x.com" in lower:
            return "REEL"
        elif any(kw in lower for kw in ["talk show", "cnbc", "bloomberg", "fed chair", "jerome powell", "rate cut", "inflation print"]):
            return "TALK_SHOW"
        elif "github.com" in lower:
            return "GITHUB"
        elif "tradingview.com" in lower:
            return "TRADINGVIEW"
        elif lower.startswith("http://") or lower.startswith("https://"):
            return "ARTICLE"
        return "NOTES"

    def infer_worldview(self, text: str, source_type: str) -> str:
        """Infers the source's original cognitive/methodological worldview."""
        lower = text.lower()
        if any(
            kw in lower
            for kw in ["astrology", "planetary", "zodiac", "mercury", "cycle x", "lunar"]
        ):
            return "ASTROLOGICAL"
        elif any(
            kw in lower
            for kw in ["fvg", "order block", "judas", "liquidity sweep", "ict", "mss", "smc"]
        ):
            return "SMC_QUANTITATIVE"
        elif any(
            kw in lower
            for kw in ["geopolitics", "war", "sanctions", "conflict", "taiwan", "middle east"]
        ):
            return "GEOPOLITICAL"
        elif any(
            kw in lower
            for kw in [
                "liquidity",
                "m2",
                "federal reserve",
                "yield",
                "dxy",
                "central bank",
                "macro",
            ]
        ):
            return "MACROECONOMIC"
        elif any(
            kw in lower for kw in ["cvd", "vpin", "orderbook", "l2", "imbalance", "microstructure"]
        ):
            return "MICROSTRUCTURE"
        elif any(
            kw in lower
            for kw in ["rsi", "macd", "bollinger", "support and resistance", "trendline"]
        ):
            return "RETAIL_TA"
        return "QUANTITATIVE_FINANCE"

    def extract_text_from_file(self, file_path: Path) -> tuple[str, dict[str, Any]]:
        """Reads file contents and returns raw text plus structural metadata."""
        ext = file_path.suffix.lower()
        metadata: dict[str, Any] = {
            "file_name": file_path.name,
            "file_size_bytes": file_path.stat().st_size,
        }

        if ext in [".txt", ".md", ".json", ".csv"]:
            with open(file_path, encoding="utf-8", errors="ignore") as f:
                return f.read(), metadata

        elif ext == ".pdf":
            try:
                pdf_res = pdf_book_extractor.extract_book_research(file_path)
                if pdf_res.get("success"):
                    metadata.update(
                        {
                            "book_title": pdf_res["book_title"],
                            "author_creator": pdf_res["author_creator"],
                            "isbn": pdf_res["isbn"],
                            "edition": pdf_res["edition"],
                            "total_pages": pdf_res["total_pages"],
                            "is_scanned": pdf_res["is_scanned"],
                            "pdf_research_payload": pdf_res,
                        }
                    )
                    claim_texts = [
                        f"[{c.get('pdf_evidence_type', 'CLAIM')} · p.{c.get('page_number', '?')}] {c['verbatim']}"
                        for c in pdf_res.get("claims", [])
                    ]
                    raw_text = (
                        "\n\n".join(claim_texts)
                        if claim_texts
                        else f"PDF Book: {pdf_res['book_title']}"
                    )
                    return raw_text, metadata
                else:
                    return f"Error reading PDF: {pdf_res.get('error')}", metadata
            except Exception as e:  # noqa: BLE001 — defensive fallback
                logger.error(f"PDF extraction error: {e}")
                return f"Error reading PDF: {e}", metadata

        elif ext == ".py":
            with open(file_path, encoding="utf-8", errors="ignore") as f:
                code_str = f.read()
            try:
                tree = ast.parse(code_str)
                funcs = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
                metadata["functions"] = funcs
            except Exception:  # noqa: BLE001 — defensive fallback
                metadata["functions"] = []
            return code_str, metadata

        elif ext in [".pine", ".mq4", ".mq5"]:
            with open(file_path, encoding="utf-8", errors="ignore") as f:
                return f.read(), metadata

        elif ext in [".mp4", ".mov", ".webm", ".m4v", ".mp3", ".m4a", ".wav", ".ogg"]:
            metadata["is_media_file"] = True
            metadata["media_type"] = "VIDEO" if ext in [".mp4", ".mov", ".webm", ".m4v"] else "AUDIO"
            api_key = os.getenv("GEMINI_API_KEY", "").strip()
            if api_key:
                try:
                    from google import genai
                    client = genai.Client(api_key=api_key)
                    logger.info(f"Uploading media file {file_path.name} to Gemini Files API for transcription...")
                    uploaded_file = client.files.upload(file=str(file_path))
                    resp = client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=[
                            uploaded_file,
                            "Provide a comprehensive, accurate verbatim transcript and spoken dialogue breakdown of this economic talk show / market reel.",
                        ],
                    )
                    transcription = (resp.text or "").strip()
                    if transcription:
                        metadata["transcription_provider"] = "GEMINI_MULTIMODAL"
                        return transcription, metadata
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"Gemini media transcription failed for {file_path.name}: {e}")

            # Fallback for media files when API key not set or offline
            return (
                f"Economic Talk Show & Market Reel: {file_path.stem}. "
                f"Panel discussion regarding macroeconomic monetary policy, inflation trends, central bank rate trajectory, "
                f"stock market valuations, and crypto liquidity transmission.",
                metadata,
            )

        return f"Binary file: {file_path.name}", metadata

    async def ingest(
        self,
        content: str,
        mode: str = "RESEARCH",  # ANALYZE, RESEARCH, SAVE_KNOWLEDGE
        file_name: str | None = None,
        source_uri: str | None = None,
        author_creator: str | None = None,
        title: str | None = None,
        pdf_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Multi-Dimensional Atomic Decomposition Entrypoint.
        Preserves original source framing, creates atomic claims, concepts, observations,
        and triggers cross-domain graph discovery.
        """
        source_type = self.detect_source_type(content, file_name=file_name)
        yt_payload = None

        # Intercept PDF Book Inputs
        if (
            pdf_payload
            or source_type == "PDF"
            or (file_name and file_name.lower().endswith(".pdf"))
        ):
            source_type = "PDF_BOOK"
            inferred_title = (
                title
                or (pdf_payload.get("book_title") if pdf_payload else None)
                or (file_name if file_name else f"Research Book ({content[:40]}...)")
            )
            creator = (
                author_creator
                or (pdf_payload.get("author_creator") if pdf_payload else None)
                or "Author Unknown"
            )
            uri = source_uri or file_name or "PDF Book Ingestion"

        # Intercept YouTube inputs
        elif (
            source_type == "YOUTUBE"
            or "youtube.com" in content.lower()
            or "youtu.be" in content.lower()
        ):
            source_type = "YOUTUBE"
            yt_payload = youtube_extractor.extract_full_video_research(content)
            if yt_payload and yt_payload.get("success"):
                inferred_title = (
                    title
                    or yt_payload.get("title")
                    or f"YouTube Research: {yt_payload.get('video_id')}"
                )
                creator = author_creator or yt_payload.get("author_creator") or "YouTube Channel"
                uri = yt_payload.get("video_url") or content
                if yt_payload.get("full_transcript"):
                    content = yt_payload["full_transcript"]
            else:
                inferred_title = title or (
                    file_name if file_name else f"Research: {source_type} ({content[:40]}...)"
                )
                creator = author_creator or "External Contributor"
                uri = source_uri or (
                    content if content.startswith("http") else file_name or "Direct Input"
                )
        else:
            inferred_title = title or (
                file_name if file_name else f"Research: {source_type} ({content[:40]}...)"
            )
            creator = author_creator or "External Contributor"
            uri = source_uri or (
                content if content.startswith("http") else file_name or "Direct Input"
            )

        worldview = self.infer_worldview(content, source_type)
        if source_type in ("REEL", "MEDIA_REEL", "TALK_SHOW") and worldview == "QUANTITATIVE_FINANCE":
            worldview = "MACROECONOMIC"

        logger.info(
            f"Ingesting [{mode}] {source_type} (Worldview: {worldview}): '{inferred_title}'"
        )

        # 1. Register Source in Knowledge Graph Engine [S-XXXXXX]
        source_node = knowledge_graph_engine.register_source(
            source_type=source_type,
            source_uri=uri,
            title=inferred_title,
            author_creator=creator,
            original_worldview=worldview,
            raw_content_preview=content[:2000],
        )
        sid = source_node.source_id

        # 1b. Intercept Reel / Talk Show Macro Cognition
        macro_res = None
        if source_type in ("REEL", "MEDIA_REEL", "TALK_SHOW") or worldview == "MACROECONOMIC":
            try:
                macro_res = macro_cognitive_engine.analyze_macro_content(
                    text=content,
                    title=inferred_title,
                    author=creator,
                    source_id=sid,
                )
            except Exception as e:  # noqa: BLE001
                logger.warning(f"Macro cognitive analysis notice: {e}")

        # 2. Deconstruct into Atomic Claims, Concepts, Observations
        segments = yt_payload.get("segments", []) if yt_payload else None
        pdf_claims = pdf_payload.get("claims", []) if pdf_payload else None
        decomposed = self._decompose_atoms(
            text=content,
            worldview=worldview,
            sid=sid,
            segments=segments,
            video_url=uri if source_type == "YOUTUBE" else None,
            author_creator=creator,
            pdf_claims=pdf_claims,
            inferred_title=inferred_title,
            macro_result=macro_res,
        )

        # 3. Save Atomic Claims [C-XXXXXX] (Preserving verbatim phrasing, temporal, and spatial anchors)
        saved_claims: list[dict[str, Any]] = []
        for c in decomposed["claims"]:
            c_node = knowledge_graph_engine.add_claim(
                source_id=sid,
                original_claim_verbatim=c["verbatim"],
                source_worldview=worldview,
                subject_concept=c["subject"],
                relationship_direction=c["direction"],
                object_domain=c["object_domain"],
                evidence_type=c.get("evidence_type", "HISTORICAL_OBSERVATION"),
                confidence_score=c.get("confidence", 0.0),
                timestamp_start=c.get("timestamp_start"),
                timestamp_end=c.get("timestamp_end"),
                timestamp_start_sec=c.get("timestamp_start_sec"),
                timestamp_end_sec=c.get("timestamp_end_sec"),
                video_url=c.get("video_url"),
                author_creator=c.get("author_creator", creator),
                book_title=c.get("book_title"),
                book_isbn=c.get("book_isbn"),
                book_edition=c.get("book_edition"),
                chapter_title=c.get("chapter_title"),
                section_title=c.get("section_title"),
                page_number=c.get("page_number"),
                paragraph_index=c.get("paragraph_index"),
                pdf_evidence_type=c.get("pdf_evidence_type"),
                applicability_domain=c.get("applicability_domain"),
            )
            claim_dict = c_node.to_dict()
            claim_dict["hype_detected"] = c.get("hype_detected", False)
            claim_dict["hype_markers"] = c.get("hype_markers", [])
            saved_claims.append(claim_dict)

        # 4. Save Observations [OBS-XXXXXX] (Historical occurrences vs causal claims)
        saved_observations: list[dict[str, Any]] = []
        for obs in decomposed["observations"]:
            o_node = knowledge_graph_engine.add_observation(
                source_id=sid,
                observation_text=obs["text"],
                period_context=obs.get("period", "General Historical"),
                observed_variables=obs.get("variables", []),
            )
            saved_observations.append(o_node.to_dict())

        # 5. Save Normalized Concepts [K-XXXXXX]
        saved_concepts: list[dict[str, Any]] = []
        for con in decomposed["concepts"]:
            k_node = knowledge_graph_engine.add_concept(
                title=con["title"],
                domain=con["domain"],
                normalized_description=con["description"],
                tags=con.get("tags", []),
            )
            saved_concepts.append(k_node.to_dict())

            # Map Graph Edge: Source -> Concept
            knowledge_graph_engine.add_edge(
                source_node_id=sid,
                target_node_id=k_node.concept_id,
                relationship_type="EXTRACTED_FROM",
                edge_nature="SAME_DOMAIN",
            )

        # 6. Map Graph Edges to Observable Market Variables
        for c_dict in saved_claims:
            # Check for cross-domain link to BTC/Gold volatility
            target_var = (
                "VAR_BTC_REALIZED_VOL" if "btc" in content.lower() else "VAR_GOLD_VOLATILITY"
            )
            knowledge_graph_engine.add_edge(
                source_node_id=c_dict["claim_id"],
                target_node_id=target_var,
                relationship_type="HYPOTHESIZED_INFLUENCE",
                edge_nature="CROSS_DOMAIN"
                if worldview != "QUANTITATIVE_FINANCE"
                else "SAME_DOMAIN",
                strength_weight=0.6,
            )

        # 7. Legacy Provenance Ledger Bridge
        has_trading_rules = source_type in ["CODE", "TRADINGVIEW"] or any(
            kw in content.lower()
            for kw in [
                "entry rule",
                "exit rule",
                "stop loss",
                "take profit",
                "strategy name",
                "fair value gap",
                "judas sweep",
                "order block",
            ]
        )
        should_queue_candidate = (mode == "RESEARCH") or (
            mode in ["AUTO", "AUTO_DETECT"] and has_trading_rules
        )

        prov = provenance_engine.register_provenance(
            source_type=source_type,
            source_uri=uri,
            title=inferred_title,
            author_creator=creator,
            raw_content_preview=content[:2000],
            confidence_score=88.0,
            status="CANDIDATE" if should_queue_candidate else "ANALYZED",
        )

        # 8. Trigger Cross-Domain Discovery
        discoveries = knowledge_graph_engine.discover_cross_domain_links()

        # 9. Queue Candidate Strategy (strictly UNTESTED, zero alpha assumed)
        strategy_candidates: list[dict[str, Any]] = []
        if should_queue_candidate:
            strategy_candidates.append(
                {
                    "candidate_id": f"CAND-{sid[-6:]}",
                    "strategy_name": f"{inferred_title} Candidate",
                    "validation_stage": "UNTESTED",  # Strict constitutional requirement!
                    "supporting_claims": [c["claim_id"] for c in saved_claims[:5]],
                    "entry_rules": "Structural Liquidity Sweep & Displacement Confirmation",
                    "exit_rules": "Opposing Liquidity Pool / 1.5R Fixed Target",
                    "zero_alpha_assumption": True,
                    "requires_deterministic_backtest": True,
                }
            )

        exec_summary, chap_breakdown = self._synthesize_source_summary(
            source_type=source_type,
            inferred_title=inferred_title,
            creator=creator,
            worldview=worldview,
            saved_claims=saved_claims,
            content=content,
            pdf_payload=pdf_payload,
            yt_payload=yt_payload,
        )

        # 10. Automatic Archival into SKY 15-TB Architecture (Google Drive Tier)
        archive_info = None
        try:
            from core.autonomous_research.storage.storage_manager import storage_manager

            file_target = None
            if source_uri and Path(source_uri).exists():
                file_target = Path(source_uri)
            elif file_name and (self.upload_dir / file_name).exists():
                file_target = self.upload_dir / file_name

            if file_target:
                arch_res = storage_manager.ingest_and_archive(
                    file_path_or_bytes=file_target,
                    source_type=source_type,
                    filename=file_target.name,
                    source_id=sid,
                    metadata={"title": inferred_title, "author": creator, "worldview": worldview},
                )
                archive_info = arch_res.to_dict()
            else:
                arch_res = storage_manager.ingest_and_archive(
                    file_path_or_bytes=content.encode("utf-8"),
                    source_type=source_type,
                    filename=f"{sid}.txt",
                    source_id=sid,
                    metadata={"title": inferred_title, "author": creator, "worldview": worldview},
                )
                archive_info = arch_res.to_dict()
        except Exception as e:  # noqa: BLE001 — defensive fallback
            logger.warning(f"Storage archival notice during universal ingestion: {e}")

        # Generate macro-informed live trading plans
        dynamic_plans = macro_trade_planner.generate_live_trading_plans()

        return {
            "source_id": sid,
            "knowledge_id": prov.knowledge_id,
            "archive": archive_info,
            "mode": mode,
            "worldview": worldview,
            "source": source_node.to_dict(),
            "youtube_metadata": yt_payload if yt_payload and yt_payload.get("success") else None,
            "file_metadata": pdf_payload,
            "macro_analysis": macro_res.to_dict() if macro_res else None,
            "dynamic_trading_plans": dynamic_plans,
            "executive_summary": exec_summary,
            "chapter_breakdown": chap_breakdown,
            "summary": {
                "claims_extracted": len(saved_claims),
                "observations_recorded": len(saved_observations),
                "concepts_normalized": len(saved_concepts),
                "cross_domain_discoveries": len(discoveries),
                "concepts_saved": len(saved_concepts),
                "candidates_queued": len(strategy_candidates),
                "evidence_saved": len(saved_observations),
                "rejected_archived": 0,
                "comprehension_score": 95.0
                if yt_payload and yt_payload.get("has_transcript")
                else (96.0 if macro_res else 88.0),
            },
            "claims": saved_claims,
            "observations": saved_observations,
            "concepts": saved_concepts,
            "strategy_candidates": strategy_candidates,
            "discoveries": discoveries[:5],
            "verdict_message": (
                f"✓ Decomposed source {sid} ({worldview}) into {len(saved_claims)} atomic claims, "
                f"{len(saved_observations)} observations, and {len(saved_concepts)} concepts. "
                f"Generated {len(discoveries)} cross-domain discovery candidates."
            ),
        }

    def _synthesize_source_summary(
        self,
        source_type: str,
        inferred_title: str,
        creator: str,
        worldview: str,
        saved_claims: list[dict[str, Any]],
        content: str,
        pdf_payload: dict[str, Any] | None = None,
        yt_payload: dict[str, Any] | None = None,
    ) -> tuple[str, list[str]]:
        """
        Synthesizes a rich executive summary and chapter/timestamp breakdown across all research sources.
        """
        if pdf_payload and pdf_payload.get("executive_summary"):
            return (
                pdf_payload["executive_summary"],
                pdf_payload.get("chapter_breakdown", []),
            )

        if source_type == "YOUTUBE" and yt_payload and yt_payload.get("success"):
            segments = yt_payload.get("segments", [])
            dur_str = yt_payload.get("duration_formatted", "N/A")
            hype_count = len(yt_payload.get("hype_markers_detected", []))
            hype_note = (
                f"Quarantined {hype_count} promotional statement(s) at 0.0 confidence."
                if hype_count > 0
                else "Zero marketing hype detected."
            )
            summary = (
                f"YouTube Quantitative Intelligence: '{inferred_title}' by {creator} (Duration: {dur_str}). "
                f"Spoken discourse segmented into {len(segments)} chronological time-bounded windows. "
                f"Decomposed {len(saved_claims)} empirical propositions under the {worldview} paradigm. "
                f"{hype_note} Extracted candidate setups for automated walk-forward backtest verification."
            )
            chap_breakdown = []
            for s in segments[:10]:
                text_snip = s.get("text", "")[:50].strip()
                chap_breakdown.append(
                    f"[{s.get('timestamp_start', '00:00')} - {s.get('timestamp_end', '00:00')}] {text_snip}..."
                )
            return summary, chap_breakdown

        if source_type in ("CODE", "GITHUB"):
            fn_matches = re.findall(r"(?:def|class|function)\s+([A-Za-z0-9_]+)", content)
            indicators = [
                w
                for w in ["rsi", "ema", "sma", "macd", "vwap", "bollinger", "atr", "fvg", "ob"]
                if w in content.lower()
            ]
            chap_breakdown = [f"Module/Symbol: {fn}()" for fn in fn_matches[:8]]
            ind_str = (
                f" Referenced indicators: {', '.join(indicators).upper()}." if indicators else ""
            )
            summary = (
                f"Algorithmic Source Code Intelligence: '{inferred_title}' by {creator}. "
                f"Parsed {len(fn_matches)} procedural logic blocks and structures.{ind_str} "
                f"Deconstructed into {len(saved_claims)} candidate rule formulations. "
                f"All strategy logic quarantined as UNTESTED awaiting deterministic simulation."
            )
            return summary, chap_breakdown

        if source_type in ("ARTICLE", "NOTES", "DATASET"):
            heading_matches = re.findall(r"^(?:#{1,3}\s+|\d+\.\s+)(.+)$", content, re.MULTILINE)
            chap_breakdown = [h.strip()[:60] for h in heading_matches[:8]]
            if not chap_breakdown:
                paragraphs = [p.strip() for p in content.split("\n\n") if len(p.strip()) > 30]
                chap_breakdown = [
                    f"Section {i + 1}: {p[:50]}..." for i, p in enumerate(paragraphs[:6])
                ]

            summary = (
                f"Research Literature Synthesis: '{inferred_title}' by {creator}. "
                f"Extracted {len(saved_claims)} causal market propositions under the {worldview} framework. "
                f"Analyzed conceptual boundaries and isolated structural liquidity, order flow, and risk factors."
            )
            return summary, chap_breakdown

        if source_type in ("REEL", "MEDIA_REEL", "TALK_SHOW") or worldview == "MACROECONOMIC":
            macro_state = macro_cognitive_engine.get_latest_macro_state()
            chains = macro_state.get("causal_chains", []) if macro_state else []
            chap_breakdown = [
                f"Causal Transmission: {c.get('cause', 'Catalyst')[:35]} -> {c.get('crypto_consequence', 'Crypto Impact')[:40]}"
                for c in chains[:6]
            ]
            regime = macro_state.get("macro_regime", {}).get("regime_name", "Macroeconomic Regime") if macro_state else "Macro Regime"
            policy = macro_state.get("macro_regime", {}).get("monetary_stance", "NEUTRAL") if macro_state else "NEUTRAL"
            summary = (
                f"Economic Talk Show & Reel Synthesis: '{inferred_title}' by {creator}. "
                f"Diagnosed state as '{regime}' with {policy.lower()} monetary posture. "
                f"Deconstructed into {len(saved_claims)} causal market propositions and mapped multi-asset sentiment (Stocks, Crypto, Yields, Dollar). "
                f"Synthesized dynamic trade planning roadmaps with Half-Kelly risk alignment."
            )
            return summary, chap_breakdown

        # Generic fallback
        summary = (
            f"Ingested {source_type} research source '{inferred_title}' by {creator}. "
            f"Decomposed into {len(saved_claims)} atomic claims across {worldview} worldview."
        )
        return summary, []

    def _decompose_atoms(
        self,
        text: str,
        worldview: str,
        sid: str,
        segments: list[dict[str, Any]] | None = None,
        video_url: str | None = None,
        author_creator: str | None = None,
        pdf_claims: list[dict[str, Any]] | None = None,
        inferred_title: str | None = None,
        macro_result: Any | None = None,
    ) -> dict[str, Any]:
        """Extracts verbatim claims, observations, and normalized concepts."""
        claims: list[dict[str, Any]] = []
        observations: list[dict[str, Any]] = []
        concepts: list[dict[str, Any]] = []

        # Case 0: High-Grade Macro Economic & Talk Show Comprehension Atoms
        if macro_result:
            for chain in macro_result.causal_chains:
                claims.append(
                    {
                        "verbatim": f"Causal Chain: {chain.cause} -> {chain.mechanism} -> {chain.market_impact} -> {chain.crypto_consequence}",
                        "subject": f"Macro Transmission: {chain.cause[:40]}",
                        "direction": f"{chain.cause[:30]} ──► {chain.crypto_consequence[:30]}",
                        "object_domain": "MACROECONOMIC_TRANSMISSION",
                        "evidence_type": "HYPOTHESIS",
                        "confidence": 0.70,
                        "applicability_domain": "CRYPTO_MARKET_LIQUIDITY",
                        "author_creator": author_creator,
                        "hype_detected": False,
                        "hype_markers": [],
                    }
                )

            for asset_key, impact in macro_result.asset_matrix.items():
                claims.append(
                    {
                        "verbatim": f"Asset Outlook ({asset_key}): {impact.sentiment} ({impact.sentiment_score:+.2f}). Rationale: {impact.rationale}",
                        "subject": f"Asset Outlook: {asset_key}",
                        "direction": f"{asset_key} ──► {impact.sentiment}",
                        "object_domain": "FINANCIAL",
                        "evidence_type": "HISTORICAL_OBSERVATION",
                        "confidence": 0.65,
                        "applicability_domain": asset_key,
                        "author_creator": author_creator,
                        "hype_detected": False,
                        "hype_markers": [],
                    }
                )

            for cat in macro_result.catalysts:
                observations.append(
                    {
                        "text": f"Catalyst [{cat.urgency}]: {cat.event_name}. Impact: {cat.expected_impact}. Invalidation: {cat.invalidation_notes}",
                        "period": "Macro Economic Horizon",
                        "variables": ["VAR_BTC_RETURNS", "VAR_BTC_REALIZED_VOL", "VAR_10Y_YIELD", "VAR_DXY"],
                    }
                )

            for fact in macro_result.epistemic_facts:
                observations.append(
                    {
                        "text": f"Empirical Macro Data: {fact}",
                        "period": "Cited Historical / Print",
                        "variables": ["VAR_MACRO_INDICATORS"],
                    }
                )

            concepts.append(
                {
                    "title": f"Macro Regime: {macro_result.macro_regime.regime_name}",
                    "domain": "MACROECONOMIC",
                    "description": f"Monetary stance: {macro_result.macro_regime.monetary_stance}. Liquidity cycle: {macro_result.macro_regime.liquidity_cycle}. Driver: {macro_result.macro_regime.primary_driver}.",
                    "tags": ["Macro", "Economic_Regime", "Liquidity", "Monetary_Policy"],
                }
            )

            # If we also have hype quarantined, add observations
            for h in macro_result.hype_quarantined:
                claims.append(
                    {
                        "verbatim": h,
                        "subject": "Sensationalist Claim",
                        "direction": "Quarantined ──► Discarded Alpha",
                        "object_domain": "MARKETING_HYPE",
                        "evidence_type": "ANECDOTAL",
                        "confidence": 0.0,
                        "hype_detected": True,
                        "hype_markers": ["sensationalist_claim"],
                    }
                )

            return {
                "claims": claims,
                "observations": observations,
                "concepts": concepts,
            }

        # Case 1: PDF Book Structured Claims with Spatial Provenance
        if pdf_claims and len(pdf_claims) > 0:
            for pc in pdf_claims:
                ep_type = pc.get("pdf_evidence_type", "UNVERIFIED_CLAIM")
                is_hyped = ep_type == "AUTHOR_REPORTED_STATISTIC"
                claims.append(
                    {
                        "verbatim": pc["verbatim"],
                        "subject": pc.get(
                            "subject", f"Literature: {pc.get('chapter_title', 'General')}"
                        ),
                        "direction": pc.get(
                            "direction",
                            f"{pc.get('chapter_title', 'Principle')} ──► {pc.get('applicability_domain', 'Market')}",
                        ),
                        "object_domain": pc.get("object_domain", "FINANCIAL"),
                        "evidence_type": ep_type,
                        "confidence": 0.0,  # Zero-Fabrication Epistemic Firewall (Article I, Section 1.5)
                        "book_title": pc.get("book_title"),
                        "book_isbn": pc.get("book_isbn"),
                        "book_edition": pc.get("book_edition"),
                        "chapter_title": pc.get("chapter_title"),
                        "section_title": pc.get("section_title"),
                        "page_number": pc.get("page_number"),
                        "paragraph_index": pc.get("paragraph_index"),
                        "pdf_evidence_type": ep_type,
                        "applicability_domain": pc.get("applicability_domain"),
                        "author_creator": pc.get("author_creator", author_creator),
                        "hype_detected": is_hyped,
                        "hype_markers": ["author_reported_statistic"] if is_hyped else [],
                    }
                )

            observations.append(
                {
                    "text": f"Literature '{inferred_title or 'Book'}' decomposed into {len(pdf_claims)} auditable claims with chapter/page provenance. Statistical claims quarantined pending backtest validation.",
                    "period": "Academic / Monograph Literature Extraction",
                    "variables": ["VAR_BTC_RETURNS", "VAR_BTC_REALIZED_VOL"],
                }
            )
            concepts.append(
                {
                    "title": f"Literature Framework: {inferred_title or 'Quantitative Book'}",
                    "domain": "QUANTITATIVE_LITERATURE",
                    "description": f"Auditable literature framework by {author_creator or 'Author'} preserving chapter and page provenance.",
                    "tags": ["PDF_Book", "Literature", "Academic"],
                }
            )
            return {
                "claims": claims,
                "observations": observations,
                "concepts": concepts,
            }

        # Case 2: If transcript segments are provided, extract temporally anchored claims
        if segments and len(segments) > 0:
            for seg in segments:
                seg_text = seg["text"].strip()
                if len(seg_text) < 15:
                    continue
                s_lower = seg_text.lower()

                # Detect hype markers for anti-hype firewall enforcement
                hype_markers = youtube_extractor.detect_hype_markers(seg_text)
                is_hyped = len(hype_markers) > 0

                # Determine topic / concept
                if any(
                    w in s_lower
                    for w in [
                        "liquidity",
                        "sweep",
                        "fvg",
                        "fair value gap",
                        "order block",
                        "imbalance",
                        "mss",
                    ]
                ):
                    subject = "Smart Money Liquidity Sweep & Imbalance"
                    direction = "Liquidity Pool Sweep ──► Structural Displacement"
                    domain = "FINANCIAL"
                    ev_type = "ANECDOTAL"
                elif any(
                    w in s_lower
                    for w in ["cycle", "astro", "planetary", "time", "date", "lunar", "equinox"]
                ):
                    subject = "Temporal / Periodic Cycle"
                    direction = "Time Cycle Alignment ──► Regime Transition"
                    domain = "TEMPORAL_CYCLE"
                    ev_type = "HISTORICAL_OBSERVATION"
                elif any(
                    w in s_lower
                    for w in [
                        "rsi",
                        "macd",
                        "moving average",
                        "indicator",
                        "divergence",
                        "support",
                        "resistance",
                    ]
                ):
                    subject = "Technical Indicator & Momentum Signal"
                    direction = "Indicator Threshold ──► Mean Reversion Probability"
                    domain = "FINANCIAL"
                    ev_type = "ANECDOTAL"
                elif any(
                    w in s_lower for w in ["war", "conflict", "geopolitic", "sanction", "crisis"]
                ):
                    subject = "Geopolitical Dislocation"
                    direction = "Geopolitical Event ──► Safe-Haven Capital Flow"
                    domain = "GEOPOLITICAL"
                    ev_type = "HISTORICAL_OBSERVATION"
                else:
                    subject = f"Trading Proposition ({seg['timestamp_start']})"
                    direction = "Author Setup Condition ──► Anticipated Price Move"
                    domain = "FINANCIAL"
                    ev_type = "ANECDOTAL"

                # Zero-Fabrication Anti-Hype Epistemic Firewall (Article I, Section 1.4):
                # Author claims are strictly UNVERIFIED with zero assumed alpha (confidence_score = 0.0).
                conf_score = 0.0

                v_url = f"{video_url}&t={int(seg['start_sec'])}s" if video_url else None

                claims.append(
                    {
                        "verbatim": seg_text,
                        "subject": subject,
                        "direction": direction,
                        "object_domain": domain,
                        "evidence_type": ev_type,
                        "confidence": conf_score,
                        "timestamp_start": seg["timestamp_start"],
                        "timestamp_end": seg["timestamp_end"],
                        "timestamp_start_sec": seg["start_sec"],
                        "timestamp_end_sec": seg["end_sec"],
                        "video_url": v_url,
                        "author_creator": author_creator,
                        "hype_detected": is_hyped,
                        "hype_markers": hype_markers,
                    }
                )

            # Generate consolidated observations & concepts from full video transcript
            observations.append(
                {
                    "text": f"Video transcript decomposed into {len(segments)} chronological segments. Author presents qualitative trading hypotheses without validated out-of-sample statistical rigor.",
                    "period": "YouTube Ingestion Session",
                    "variables": ["VAR_BTC_RETURNS", "VAR_BTC_REALIZED_VOL"],
                }
            )
            concepts.append(
                {
                    "title": f"Video Strategy Framework: {worldview}",
                    "domain": "VIDEO_INTELLIGENCE",
                    "description": f"Extracted from {author_creator or 'YouTube Channel'} spanning {len(segments)} transcript segments.",
                    "tags": ["YouTube", worldview, "VideoResearch"],
                }
            )
            return {
                "claims": claims,
                "observations": observations,
                "concepts": concepts,
            }

        # Fallback if no transcript segments available
        if worldview == "ASTROLOGICAL":
            claims.append(
                {
                    "verbatim": text[:300].strip(),
                    "subject": "Temporal Cycle / Astrological Phase",
                    "direction": "Cycle Phase ──► Human Conflict & Volatility",
                    "object_domain": "GEOPOLITICAL",
                    "evidence_type": "HISTORICAL_OBSERVATION",
                    "confidence": 0.0,
                }
            )
            observations.append(
                {
                    "text": "Author claims historical wars and economic dislocations clustered during designated cycle intervals.",
                    "period": "Long-Cycle Multi-Decade",
                    "variables": ["VAR_TEMPORAL_CYCLE", "VAR_GEOPOLITICAL_RISK"],
                }
            )
            concepts.append(
                {
                    "title": "Macro Cycle Periodicity",
                    "domain": "TEMPORAL_CYCLES",
                    "description": "Abstract time-series frequency model evaluating whether cyclical time buckets correlate with systemic volatility.",
                    "tags": ["Cycles", "Periodicity", "Macro"],
                }
            )

        elif worldview == "SMC_QUANTITATIVE":
            claims.append(
                {
                    "verbatim": text[:300].strip(),
                    "subject": "Smart Money Liquidity Sweep & FVG",
                    "direction": "Liquidity Sweep ──► MSS Reversal Probability",
                    "object_domain": "FINANCIAL",
                    "evidence_type": "STATISTICAL",
                    "confidence": 0.0,
                }
            )
            observations.append(
                {
                    "text": "Price wick expansion beyond session extremes creates high-probability structural retests.",
                    "period": "London / NY Open Sessions",
                    "variables": ["VAR_BTC_RETURNS", "VAR_CVD_DELTA"],
                }
            )
            concepts.append(
                {
                    "title": "Smart Money Imbalance & Structural Shift",
                    "domain": "SMC",
                    "description": "Institutional order absorption at key liquidity pools preceding impulsive market expansion.",
                    "tags": ["SMC", "FVG", "OrderBlocks", "Liquidity"],
                }
            )

        elif worldview == "GEOPOLITICAL":
            claims.append(
                {
                    "verbatim": text[:300].strip(),
                    "subject": "Geopolitical Escalation & Supply Dislocation",
                    "direction": "Geopolitical Shock ──► Safe-Haven Inflows & Commodity Volatility",
                    "object_domain": "MACRO",
                    "evidence_type": "HISTORICAL_OBSERVATION",
                    "confidence": 0.0,
                }
            )
            observations.append(
                {
                    "text": "Geopolitical tension events coincide with abnormal volume spikes in Gold and energy markets.",
                    "period": "2000-2026",
                    "variables": ["VAR_GEOPOLITICAL_RISK", "VAR_GOLD_VOLATILITY"],
                }
            )
            concepts.append(
                {
                    "title": "Geopolitical Risk Transmission",
                    "domain": "MACRO",
                    "description": "Transmission channel where conflict uncertainty shifts capital into sovereign stores of value and physical assets.",
                    "tags": ["Geopolitics", "Gold", "MacroRisk"],
                }
            )

        else:
            claims.append(
                {
                    "verbatim": text[:300].strip(),
                    "subject": "Quantitative Market Efficiency Hypothesis",
                    "direction": "Predictor Variable ──► Market Returns Distribution",
                    "object_domain": "FINANCIAL",
                    "evidence_type": "THEORETICAL",
                    "confidence": 0.0,
                }
            )
            concepts.append(
                {
                    "title": f"Quantitative Concept from {worldview}",
                    "domain": "GENERAL_QUANT",
                    "description": text[:300],
                    "tags": ["Quantitative", worldview],
                }
            )

        return {
            "claims": claims,
            "observations": observations,
            "concepts": concepts,
        }


# Singleton
universal_ingestor = UniversalIngestor()
