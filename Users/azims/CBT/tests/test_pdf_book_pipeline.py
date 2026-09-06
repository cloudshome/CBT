"""
tests/test_pdf_book_pipeline.py
================================
Comprehensive Verification Suite for the 10/10 PDF Book Ingestion Pipeline.

Validates the Book Research Architecture (Article I, Section 1.5):
1. 7-Tier Epistemic Typology Classification:
   - DEFINITION
   - AUTHOR_REPORTED_STATISTIC (win rate, Sharpe, payoff)
   - PROPOSED_RULE (actionable trading rule)
   - HISTORICAL_OBSERVATION (dated empirical market event)
   - REPORTED_RESEARCH (academic citations)
   - UNVERIFIED_CLAIM (qualitative author hypothesis)
2. Crypto Relevance Matrix:
   - Source Domain != Applicability Domain
   - CRYPTO_DIRECT, MARKET_GENERAL, TRADING_GENERAL, MACRO, RISK, PSYCHOLOGY, STATISTICS
3. ISBN, Title, Author, Edition detection from front matter.
4. Page-aware and Chapter-aware spatial provenance (Book -> Edition -> Chapter -> Section -> Page -> Paragraph).
5. Anti-Hype Statistic Quarantine:
   - Author reported statistics stored with confidence = 0.0 (zero assumed alpha).
6. End-to-end UniversalIngestor integration and SQLite research_claims persistence.
"""

from __future__ import annotations

import io
from pathlib import Path
import tempfile
import pytest

from core.database import db_manager
from core.knowledge_graph_engine import knowledge_graph_engine
from core.pdf_extractor import (
    PDFBookExtractor,
    pdf_book_extractor,
)
from core.universal_ingestor import universal_ingestor


def create_mock_pdf_bytes(pages_text: list[str]) -> bytes:
    """Generates a valid, parseable multi-page PDF binary stream with text."""
    objects = []
    page_obj_ids = []
    
    # Header
    pdf_buf = io.BytesIO()
    pdf_buf.write(b"%PDF-1.4\n")
    
    # We will build objects dynamically
    # 1: Catalog, 2: Pages tree
    total_pages = len(pages_text)
    kids_refs = []
    
    # Reserve object IDs:
    # 1: Catalog
    # 2: Pages
    # For each page i:
    #   obj 3 + 3*i: Page object
    #   obj 4 + 3*i: Content stream object
    #   obj 5 + 3*i: Font object
    
    font_id = 3 + 3 * total_pages
    
    for i, p_text in enumerate(pages_text):
        page_id = 3 + 3 * i
        content_id = page_id + 1
        page_obj_ids.append(page_id)
        kids_refs.append(f"{page_id} 0 R")
    
    # 1 0 obj: Catalog
    offsets = {}
    offsets[1] = pdf_buf.tell()
    pdf_buf.write(b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n")
    
    # 2 0 obj: Pages
    offsets[2] = pdf_buf.tell()
    kids_str = " ".join(kids_refs)
    pdf_buf.write(f"2 0 obj << /Type /Pages /Kids [{kids_str}] /Count {total_pages} >> endobj\n".encode("utf-8"))
    
    # Pages and Contents
    for i, p_text in enumerate(pages_text):
        page_id = 3 + 3 * i
        content_id = page_id + 1
        
        # Format text stream with simple BT /F1 12 Tf ... ET
        # Escape parentheses
        safe_text = p_text.replace("(", "\\(").replace(")", "\\)").replace("\n", " ")
        stream_content = f"BT /F1 12 Tf 50 700 Td ({safe_text}) Tj ET".encode("utf-8")
        
        offsets[page_id] = pdf_buf.tell()
        pdf_buf.write(f"{page_id} 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {content_id} 0 R /Resources << /Font << /F1 {font_id} 0 R >> >> >> endobj\n".encode("utf-8"))
        
        offsets[content_id] = pdf_buf.tell()
        pdf_buf.write(f"{content_id} 0 obj << /Length {len(stream_content)} >> stream\n".encode("utf-8"))
        pdf_buf.write(stream_content)
        pdf_buf.write(b"\nendstream endobj\n")
    
    # Font Object
    offsets[font_id] = pdf_buf.tell()
    pdf_buf.write(f"{font_id} 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n".encode("utf-8"))
    
    # XREF table
    xref_offset = pdf_buf.tell()
    total_objs = font_id + 1
    pdf_buf.write(f"xref\n0 {total_objs}\n".encode("utf-8"))
    pdf_buf.write(b"0000000000 65535 f \n")
    for obj_i in range(1, total_objs):
        off = offsets.get(obj_i, 0)
        pdf_buf.write(f"{off:010d} 00000 n \n".encode("utf-8"))
    
    # Trailer
    pdf_buf.write(f"trailer << /Size {total_objs} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF".encode("utf-8"))
    return pdf_buf.getvalue()


class TestEpistemicTypologyAndRelevance:
    """Verifies the 7-tier classification and crypto applicability matrix."""

    def test_classify_epistemic_typology(self):
        extractor = PDFBookExtractor()

        # 1. AUTHOR_REPORTED_STATISTIC
        stat_text = "Across 500 historical sample trades, this setup produced a 75% win rate and a profit factor of 2.8."
        assert extractor.classify_epistemic_type(stat_text) == "AUTHOR_REPORTED_STATISTIC"

        # 2. PROPOSED_RULE
        rule_text = "When price sweeps the Asian liquidity pool and closes below the 15-minute EMA, enter short immediately."
        assert extractor.classify_epistemic_type(rule_text) == "PROPOSED_RULE"

        # 3. DEFINITION
        def_text = "The Sharpe ratio is defined as the mathematical ratio of mean excess return to portfolio volatility."
        assert extractor.classify_epistemic_type(def_text) == "DEFINITION"

        # 4. HISTORICAL_OBSERVATION
        hist_text = "During the panic of 2008, order book liquidity evaporated across all major equity exchanges."
        assert extractor.classify_epistemic_type(hist_text) == "HISTORICAL_OBSERVATION"

        # 5. REPORTED_RESEARCH
        research_text = "According to Kyle (1985), institutional informed traders conceal directional flow within noise volume."
        assert extractor.classify_epistemic_type(research_text) == "REPORTED_RESEARCH"

        # 6. UNVERIFIED_CLAIM
        claim_text = "I believe cyclical market rhythm is the ultimate key to conquering trading fear."
        assert extractor.classify_epistemic_type(claim_text) == "UNVERIFIED_CLAIM"

    def test_classify_applicability_domain(self):
        extractor = PDFBookExtractor()

        # Crypto Direct
        assert extractor.classify_applicability_domain("Bitcoin funding rate imbalances trigger short squeezes.") == "CRYPTO_DIRECT"
        assert extractor.classify_applicability_domain("Perpetual swaps on Binance exhibit negative basis.") == "CRYPTO_DIRECT"

        # Market General (Source: traditional equities -> Applicable to Crypto)
        assert extractor.classify_applicability_domain("Order book depth and bid-ask spread determine institutional slippage.") == "MARKET_GENERAL"
        assert extractor.classify_applicability_domain("Fair value gaps represent liquidity voids where institutional absorption occurred.") == "MARKET_GENERAL"

        # Risk Management
        assert extractor.classify_applicability_domain("The Kelly criterion dictates half-kelly fractional sizing to avoid risk of ruin.") == "RISK"

        # Macroeconomics
        assert extractor.classify_applicability_domain("Federal Reserve rate hikes and M2 money supply contractions diminish market liquidity.") == "MACRO"

        # Psychology
        assert extractor.classify_applicability_domain("Revenge trading and cognitive bias destroy trader equity faster than bad edge.") == "PSYCHOLOGY"

        # Statistics
        assert extractor.classify_applicability_domain("Market returns exhibit heavy fat tails and non-Gaussian kurtosis.") == "STATISTICS"


class TestPDFExtractionPipeline:
    """Verifies page-aware parsing, chapter hierarchy, and spatial anchoring."""

    def test_extract_book_with_spatial_anchors(self):
        page_1 = "Trading Market Microstructure. Second Edition. ISBN: 978-0-19-876543-2. Author: Larry Harris."
        page_2 = "Chapter 1: Order Flow and Liquidity Pools. Definition: The bid-ask spread is a measure of liquidity provision cost."
        page_3 = "Chapter 2: Tactical Execution Rules. When price sweeps the prior session high, enter short with a 2 to 1 risk reward ratio. This rule achieved a 68% win rate in historical backtests."

        pdf_bytes = create_mock_pdf_bytes([page_1, page_2, page_3])

        with tempfile.TemporaryDirectory() as tmp_dir:
            pdf_path = Path(tmp_dir) / "microstructure_book.pdf"
            pdf_path.write_bytes(pdf_bytes)

            result = pdf_book_extractor.extract_book_research(pdf_path)

            assert result["success"] is True
            assert result["total_pages"] == 3
            assert result["pages_processed"] == 3
            assert result["is_scanned"] is False
            assert "978-0-19-876543-2" in str(result["isbn"])
            assert "Second Edition" in str(result["edition"])

            claims = result["claims"]
            assert len(claims) >= 2

            # Find author reported statistic
            stat_claims = [c for c in claims if c["pdf_evidence_type"] == "AUTHOR_REPORTED_STATISTIC"]
            assert len(stat_claims) >= 1
            stat_c = stat_claims[0]
            assert stat_c["page_number"] == 3
            assert "Chapter 2" in stat_c["chapter_title"]
            assert stat_c["confidence_score"] == 0.0  # Zero assumed alpha
            assert stat_c["epistemic_status"] == "UNVERIFIED"

            # Find definition claim
            def_claims = [c for c in claims if c["pdf_evidence_type"] == "DEFINITION"]
            assert len(def_claims) >= 1
            def_c = def_claims[0]
            assert def_c["page_number"] == 2
            assert "Chapter 1" in def_c["chapter_title"]


class TestUniversalIngestorBookEndToEnd:
    """Verifies end-to-end PDF ingestion, database persistence, and candidate generation."""

    @pytest.mark.asyncio
    async def test_pdf_book_ingestion_end_to_end(self):
        page_1 = "Quantitative Trading Systems. 1st Edition. ISBN 978-1-2345-6789-0. By Howard Bandy."
        page_2 = "Chapter 3: Edge Quantification. The Sharpe ratio represents the mean excess return over downside risk."
        page_3 = "Chapter 4: Breakout Directives. If market structure breaks the 20-period swing high, buy long immediately. Historical tests report a 70% win rate."

        pdf_bytes = create_mock_pdf_bytes([page_1, page_2, page_3])

        with tempfile.TemporaryDirectory() as tmp_dir:
            pdf_path = Path(tmp_dir) / "quantitative_systems.pdf"
            pdf_path.write_bytes(pdf_bytes)

            # 1. Extract via universal ingestor text extraction
            text_content, metadata = universal_ingestor.extract_text_from_file(pdf_path)
            assert "pdf_research_payload" in metadata
            assert metadata["total_pages"] == 3

            # 2. Ingest into Research Graph
            result = await universal_ingestor.ingest(
                content=text_content,
                mode="RESEARCH",
                file_name=pdf_path.name,
                source_uri=str(pdf_path),
                author_creator=metadata.get("author_creator") or "Howard Bandy",
                title=metadata.get("book_title") or "Quantitative Trading Systems",
                pdf_payload=metadata.get("pdf_research_payload"),
            )

        # 3. Verify Source Metadata
        assert result["source_id"].startswith("S-")
        assert result["source"]["source_type"] == "PDF_BOOK"

        # 4. Verify Claims Structure & Spatial Provenance
        claims = result["claims"]
        assert len(claims) >= 2

        claim_p3 = next((c for c in claims if c["page_number"] == 3), None)
        assert claim_p3 is not None
        assert claim_p3["book_title"] is not None
        assert claim_p3["page_number"] == 3
        assert "Chapter 4" in claim_p3["chapter_title"]
        assert claim_p3["confidence_score"] == 0.0
        assert claim_p3["epistemic_status"] == "UNVERIFIED"

        # 5. Verify Candidate Strategy Formulation (Constitutional Requirement: UNTESTED)
        candidates = result["strategy_candidates"]
        assert len(candidates) >= 1
        cand = candidates[0]
        assert cand["validation_stage"] == "UNTESTED"
        assert cand["zero_alpha_assumption"] is True
        assert len(cand["supporting_claims"]) > 0

        # 6. Verify Database Persistence in brain_memory.db
        with db_manager.get_brain_conn() as conn:
            row = conn.execute(
                "SELECT * FROM research_claims WHERE claim_id = ?",
                (claim_p3["claim_id"],),
            ).fetchone()
            assert row is not None
            assert row["page_number"] == 3
            assert "Chapter 4" in row["chapter_title"]
            assert row["book_title"] is not None
            assert row["confidence_score"] == 0.0
            assert row["epistemic_status"] == "UNVERIFIED"


def test_scanned_pdf_detection():
    """Validates that pages with zero/low digital text streams are flagged as scanned."""
    # Create a 2-page PDF with empty text streams (simulating scanned raster images)
    scanned_pdf_bytes = create_mock_pdf_bytes(["", ""])
    with tempfile.TemporaryDirectory() as tmp_dir:
        pdf_path = Path(tmp_dir) / "scanned_monograph.pdf"
        pdf_path.write_bytes(scanned_pdf_bytes)

        res = pdf_book_extractor.extract_book_research(pdf_path)
        assert res["success"] is True
        assert res["is_scanned"] is True
        assert res["avg_chars_per_page"] < 40.0
        assert res["scanned_pages_ocr_processed"] == 0


def test_vision_ocr_transcription_and_epistemic_pipeline():
    """Validates multimodal vision OCR fallback and subsequent epistemic classification."""
    transcription_sample = (
        "Chapter 3: Institutional Order Flow Dynamics\n\n"
        "If buy-side volume exceeds sell-side by 3.5x at the swing low, "
        "enter long position at market with stop loss placed 10 ticks below the candle wick.\n\n"
        "Historically, the author claims a 78% win rate and 2.4 profit factor."
    )

    def mock_transcriber(image_bytes: bytes, mime_type: str):
        assert len(image_bytes) > 0
        return transcription_sample

    vision_extractor = PDFBookExtractor(vision_transcriber_override=mock_transcriber)

    # 1. Test direct vision extraction
    raw_img = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + b"\x00" * 300
    text, provider = vision_extractor.extract_page_with_vision(raw_img, mime_type="image/png")
    assert text == transcription_sample
    assert provider == "VISION_OVERRIDE"

    # 2. Test epistemic classification on OCR transcribed text
    paragraphs = [p.strip() for p in text.split("\n\n") if len(p.strip()) > 20]
    rule_para = paragraphs[1]
    stat_para = paragraphs[2]

    assert vision_extractor.classify_epistemic_type(rule_para) == "PROPOSED_RULE"
    assert vision_extractor.classify_epistemic_type(stat_para) == "AUTHOR_REPORTED_STATISTIC"
    assert vision_extractor.classify_applicability_domain(rule_para) == "RISK"


def test_offline_vision_ocr_graceful_fallback():
    """Validates that offline environments gracefully handle OCR without crashing."""
    extractor = PDFBookExtractor()
    extractor.api_key = ""  # Force offline
    text, provider = extractor.extract_page_with_vision(b"\x00" * 100)
    assert text == ""
    assert provider == "OFFLINE_FALLBACK"

