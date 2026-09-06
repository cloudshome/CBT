"""
core/pdf_extractor.py
=====================
SKY Institutional PDF Book & Literature Research Intelligence Extractor.

Constitutional Mandate (Article I, Section 1.5):
- Treats PDF books and monographs as first-class, structured research sources.
- Preserves full hierarchical provenance: Book -> Edition -> Chapter -> Section -> Page -> Paragraph.
- 7-Tier Epistemic Typology:
  * DEFINITION: Conceptual and mathematical definitions.
  * AUTHOR_REPORTED_STATISTIC: Unverified author claims of win rates or Sharpe (strictly confidence = 0.0).
  * PROPOSED_RULE: Prescriptive execution directives (entry, exit, stop loss).
  * HISTORICAL_OBSERVATION: Descriptive accounts of empirical market events.
  * REPORTED_RESEARCH: Citations to external academic literature.
  * UNVERIFIED_CLAIM: Author's qualitative opinion or hypothesis.
  * SKY_EMPIRICAL_RESULT: Internal backtest results.
- Crypto Relevance Matrix:
  * Distinguishes Source Domain from Applicability Domain (e.g. traditional equity market structure applicable to BTC/USDT).
  * Categorizes: CRYPTO_DIRECT, MARKET_GENERAL, TRADING_GENERAL, MACRO, PSYCHOLOGY, RISK, STATISTICS, IRRELEVANT.
"""

from __future__ import annotations

import io
import logging
import os
from pathlib import Path
import re
from typing import Any, List, Optional, Tuple

import pypdf

logger = logging.getLogger("ai_quant_sentinel.pdf_extractor")

# Regex for ISBN identification (ISBN-10 or ISBN-13)
ISBN_REGEX = re.compile(
    r"(?:ISBN(?:-1[03])?:?\s*)?(?=[0-9X]{10}|(?=(?:[0-9]+[-\s]){3})[-0-9X]{13}|97[89][0-9]{10}|(?=(?:[0-9]+[-\s]){4})[-0-9]{17})(?:97[89][-\s]?)?[0-9]{1,5}[-\s]?[0-9]+[-\s]?[0-9]+[-\s]?[0-9X]",
    re.IGNORECASE,
)

# Regex for edition identification
EDITION_REGEX = re.compile(
    r"\b([1-9](?:st|nd|rd|th)?\s+Edition|Revised\s+Edition|First\s+Edition|Second\s+Edition|Third\s+Edition|Fourth\s+Edition|Fifth\s+Edition)\b",
    re.IGNORECASE,
)

# Regex for chapter headings in text
CHAPTER_REGEX = re.compile(
    r"^(?:CHAPTER|Chapter)\s+([0-9IVXLCDM]+|[A-Za-z]+)[:\s\.\-]+([^\n\r]+)",
    re.MULTILINE,
)

# Regex for section headings in text
SECTION_REGEX = re.compile(
    r"^(?:SECTION|Section|[0-9]+\.[0-9]+)\s+[:\s\.\-]?([^\n\r]+)",
    re.MULTILINE,
)

# Epistemic typology classification patterns
PATTERNS_AUTHOR_STATISTIC = [
    r"\b\d+%\s*(?:win\s*rate|accuracy|profitable|success\s*rate)\b",
    r"\bsharpe(?:\s*ratio)?\s*(?:of\s*)?\d+\.?\d*\b",
    r"\bprofit\s*factor\s*(?:of\s*)?\d+\.?\d*\b",
    r"\b\d+:\d+\s*(?:risk\s*reward|risk\s*to\s*reward)\b",
    r"\baverage\s*gain\s*of\s*\d+%\b",
    r"\bmaximum\s*drawdown\s*of\s*(?:only\s*)?\d+%\b",
]

PATTERNS_PROPOSED_RULE = [
    r"\b(?:if|when|whenever)\s+(?:price|market|candle|bar|rsi|macd|ema|ma|fvg|liquidity|volume|buy-side|sell-side)\s+(?:closes|crosses|sweeps|breaks|enters|touches|exceeds)\b",
    r"\b(?:enter|exit|open|close|buy|sell|short|long|go\s*long|go\s*short)(?:\s+(?:a\s+)?(?:long|short)?\s*position)?\s+(?:at|when|if|once|immediately|with)\b",
    r"\b(?:place\s+(?:a\s+)?stop\s*loss|stop\s*loss\s+(?:is\s+)?placed)\s+(?:at|above|below|\d+\s+ticks\s+below|\d+\s+ticks\s+above)\b",
    r"\btake\s+profit\s+(?:at|target)\b",
    r"\brisk\s+(?:strictly\s*)?\d+%\s+(?:per\s+trade|of\s+equity)\b",
]

PATTERNS_DEFINITION = [
    r"\b(?:is\s+defined\s+as|by\s+definition|we\s+define|definition:)\b",
    r"\b(?:is\s+a\s+measure\s+of|represents\s+the\s+ratio\s+of|the\s+formula\s+for)\b",
    r"\b(?:is\s+termed|is\s+known\s+as|refers\s+to\s+the\s+concept\s+of)\b",
]

PATTERNS_HISTORICAL = [
    r"\b(?:in\s+(?:19\d\d|20\d\d)|during\s+the\s+(?:crash|panic|crisis|bubble|rally|session|bear\s*market|bull\s*market))\b",
    r"\b(?:historically|historical\s+data\s+shows|in\s+the\s+panic\s+of)\b",
    r"\b(?:between\s+\d{4}\s+and\s+\d{4}|from\s+\d{4}\s+to\s+\d{4})\b",
]

PATTERNS_RESEARCH = [
    r"\b(?:et\s+al\.|journal\s+of|working\s+paper|published\s+in|econometrica)\b",
    r"\b(?:research\s+by|study\s+by|according\s+to\s+[A-Za-z]+\s*\(\d{4}\))",
    r"\b(?:empirically\s+tested\s+by|peer-reviewed|academic\s+literature)\b",
]

REGEX_STATISTIC = re.compile("|".join(PATTERNS_AUTHOR_STATISTIC), re.IGNORECASE)
REGEX_RULE = re.compile("|".join(PATTERNS_PROPOSED_RULE), re.IGNORECASE)
REGEX_DEFINITION = re.compile("|".join(PATTERNS_DEFINITION), re.IGNORECASE)
REGEX_HISTORICAL = re.compile("|".join(PATTERNS_HISTORICAL), re.IGNORECASE)
REGEX_RESEARCH = re.compile("|".join(PATTERNS_RESEARCH), re.IGNORECASE)

# Crypto Relevance Keywords
CRYPTO_DIRECT_KEYWORDS = [
    "bitcoin", "btc", "ethereum", "eth", "crypto", "cryptocurrency", "blockchain",
    "satoshi", "perpetual", "funding rate", "binance", "bybit", "solana", "altcoin"
]
MARKET_GENERAL_KEYWORDS = [
    "market structure", "order flow", "orderbook", "liquidity", "bid-ask", "spread",
    "fvg", "fair value gap", "order block", "slippage", "depth", "imbalance", "sweep",
    "limit order", "market order", "absorption", "delta", "cvd", "vpin"
]
TRADING_GENERAL_KEYWORDS = [
    "trendline", "moving average", "rsi", "macd", "support and resistance", "breakout",
    "pullback", "candlestick", "reversal", "bollinger", "stochastic", "momentum"
]
MACRO_KEYWORDS = [
    "federal reserve", "central bank", "interest rate", "inflation", "cpi", "m2", "yield curve",
    "quantitative easing", "treasury", "dxy", "dollar index", "sovereign", "macroeconomic"
]
PSYCHOLOGY_KEYWORDS = [
    "discipline", "emotion", "fomo", "fear", "greed", "cognitive bias", "psychology",
    "overtrading", "revenge trading", "mental state", "patience"
]
RISK_KEYWORDS = [
    "position size", "position sizing", "kelly criterion", "half-kelly", "value at risk",
    "var", "drawdown", "risk of ruin", "money management", "stop loss", "leverage"
]
STATISTICS_KEYWORDS = [
    "probability distribution", "fat tail", "kurtosis", "skewness", "stationarity",
    "cointegration", "hypothesis test", "p-value", "monte carlo", "variance", "standard deviation"
]


class PDFBookExtractor:
    """
    Quantitative PDF Literature & Book Ingestion Engine.
    Implements the 7-tier epistemic typology, spatial page/chapter provenance,
    and crypto relevance mapping.
    """

    def __init__(self, vision_transcriber_override=None):
        self.api_key = os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")
        self.vision_model = os.getenv("GEMINI_VISION_MODEL", "gemini-2.5-flash")
        self.vision_transcriber_override = vision_transcriber_override

    def extract_page_with_vision(
        self,
        image_bytes: bytes,
        mime_type: str = "image/png",
        custom_prompt: str | None = None,
    ) -> tuple[str, str]:
        """
        Multimodal Vision Transcriber for scanned literature pages.
        Uses google-genai SDK if GEMINI_API_KEY is available or vision_transcriber_override.
        Returns: (transcribed_text, provider_name)
        """
        if self.vision_transcriber_override is not None:
            try:
                res = self.vision_transcriber_override(image_bytes, mime_type)
                if res:
                    return str(res).strip(), "VISION_OVERRIDE"
            except Exception as e:
                logger.warning(f"Vision transcriber override failed: {e}")

        if not image_bytes:
            return "", "NONE"

        api_key = self.api_key or os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")
        if api_key:
            try:
                from google import genai
                from google.genai import types

                client = genai.Client(api_key=api_key)
                prompt = custom_prompt or (
                    "You are an institutional quantitative document OCR engine for financial literature. "
                    "Transcribe all text, formulas, numbers, tables, and headings from this scanned monograph page verbatim. "
                    "Preserve paragraphs, mathematical notation, and structure. Do not summarize, add commentary, or omit sections."
                )
                part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
                response = client.models.generate_content(
                    model=self.vision_model,
                    contents=[part, prompt],
                )
                text = (response.text or "").strip()
                if text:
                    return text, "GEMINI_VISION"
            except Exception as e:
                logger.warning(f"Gemini Vision OCR extraction failed: {e}")

        return "", "OFFLINE_FALLBACK"

    def extract_metadata_and_isbn(
        self, reader: pypdf.PdfReader, raw_front_matter: str
    ) -> dict[str, Any]:
        """Extracts ISBN, edition, title, author, and page count."""
        info = reader.metadata or {}
        
        # 1. Title
        raw_title = info.get("/Title") or info.get("title") if isinstance(info, dict) else getattr(info, "title", None)
        title = str(raw_title).strip() if raw_title and len(str(raw_title).strip()) > 2 else None
        
        # 2. Author
        raw_author = info.get("/Author") or info.get("author") if isinstance(info, dict) else getattr(info, "author", None)
        author = str(raw_author).strip() if raw_author and len(str(raw_author).strip()) > 2 else None

        # 3. ISBN scan from front matter / copyright pages
        isbn = None
        isbn_match = ISBN_REGEX.search(raw_front_matter)
        if isbn_match:
            isbn = isbn_match.group(0).strip()

        # 4. Edition scan
        edition = None
        edition_match = EDITION_REGEX.search(raw_front_matter)
        if edition_match:
            edition = edition_match.group(0).strip()

        raw_producer = info.get("/Producer") or info.get("producer") if isinstance(info, dict) else getattr(info, "producer", "")
        producer = str(raw_producer or "")

        raw_creation_date = info.get("/CreationDate") or info.get("creation_date") if isinstance(info, dict) else getattr(info, "creation_date", "")
        creation_date = str(raw_creation_date or "")

        return {
            "title": title or "Untitled Quantitative Literature",
            "author": author or "Author Unknown",
            "isbn": isbn,
            "edition": edition or "1st Edition",
            "total_pages": len(reader.pages),
            "producer": producer,
            "creation_date": creation_date,
        }

    def classify_epistemic_type(self, text: str) -> str:
        """
        Classifies text into one of the 7 constitutional epistemic types:
        1. AUTHOR_REPORTED_STATISTIC (win rate, Sharpe, 0 alpha assumed)
        2. PROPOSED_RULE (actionable trading directive)
        3. DEFINITION (formal math or conceptual rule)
        4. HISTORICAL_OBSERVATION (dated market event)
        5. REPORTED_RESEARCH (academic citation)
        6. UNVERIFIED_CLAIM (author qualitative opinion)
        7. SKY_EMPIRICAL_RESULT (internal test only)
        """
        if REGEX_STATISTIC.search(text):
            return "AUTHOR_REPORTED_STATISTIC"
        elif REGEX_RULE.search(text):
            return "PROPOSED_RULE"
        elif REGEX_DEFINITION.search(text):
            return "DEFINITION"
        elif REGEX_HISTORICAL.search(text):
            return "HISTORICAL_OBSERVATION"
        elif REGEX_RESEARCH.search(text):
            return "REPORTED_RESEARCH"
        return "UNVERIFIED_CLAIM"

    def classify_applicability_domain(self, text: str) -> str:
        """
        Maps source literature domain to market applicability domain:
        Source domain != applicability domain (e.g. traditional equity book applicable to BTC).
        """
        lower = text.lower()
        if any(kw in lower for kw in CRYPTO_DIRECT_KEYWORDS):
            return "CRYPTO_DIRECT"
        elif any(kw in lower for kw in RISK_KEYWORDS):
            return "RISK"
        elif any(kw in lower for kw in MACRO_KEYWORDS):
            return "MACRO"
        elif any(kw in lower for kw in STATISTICS_KEYWORDS):
            return "STATISTICS"
        elif any(kw in lower for kw in PSYCHOLOGY_KEYWORDS):
            return "PSYCHOLOGY"
        elif any(kw in lower for kw in MARKET_GENERAL_KEYWORDS):
            return "MARKET_GENERAL"
        elif any(kw in lower for kw in TRADING_GENERAL_KEYWORDS):
            return "TRADING_GENERAL"
        return "MARKET_GENERAL"

    def extract_toc_outlines(self, reader: pypdf.PdfReader) -> list[dict[str, Any]]:
        """Extracts table of contents bookmarks from PDF outlines if available."""
        toc_items: list[dict[str, Any]] = []
        try:
            outline = reader.outline
            if outline:
                def _traverse(items):
                    for it in items:
                        if isinstance(it, list):
                            _traverse(it)
                        elif hasattr(it, "title"):
                            page_num = 1
                            try:
                                page_num = reader.get_destination_page_number(it) + 1
                            except Exception:
                                pass
                            toc_items.append({
                                "title": str(it.title),
                                "page_number": page_num,
                            })
                _traverse(outline)
        except Exception as e:
            logger.debug(f"Could not extract outline TOC: {e}")

        return toc_items

    def extract_book_research(
        self,
        file_path: Path,
        max_pages: int = 1500,
    ) -> dict[str, Any]:
        """
        Comprehensive PDF Book Extraction Pipeline:
        1. Decodes document streams into page-aware text.
        2. Detects scanned PDFs vs text PDFs.
        3. Identifies ISBN, Edition, Chapter, and Section hierarchy.
        4. Extracts atomic claims partitioned by the 7-tier Epistemic Typology.
        5. Isolates author-reported statistics with 0 assumed alpha.
        6. Maps Crypto Relevance Matrix.
        """
        if not file_path.exists():
            return {"error": f"File not found: {file_path}", "success": False}

        try:
            reader = pypdf.PdfReader(str(file_path))
        except Exception as e:
            logger.error(f"pypdf reader failed for {file_path}: {e}")
            return {"error": f"Corrupted or invalid PDF: {e}", "success": False}

        total_pages = len(reader.pages)
        if total_pages == 0:
            return {"error": "PDF has 0 pages", "success": False}

        # 1. Front matter preview for ISBN & Edition detection (first 10 pages)
        front_matter_texts = []
        for i in range(min(10, total_pages)):
            try:
                t = reader.pages[i].extract_text() or ""
                front_matter_texts.append(t)
            except Exception:
                pass
        raw_front_matter = "\n".join(front_matter_texts)

        meta = self.extract_metadata_and_isbn(reader, raw_front_matter)
        # If reader metadata title is default, check filename
        if meta["title"] == "Untitled Quantitative Literature":
            clean_name = file_path.stem.replace("_", " ").replace("-", " ").title()
            meta["title"] = clean_name

        # 2. Extract TOC outlines
        toc_bookmarks = self.extract_toc_outlines(reader)

        # 3. Process Pages with Page & Chapter Awareness
        pages_processed = min(total_pages, max_pages)
        extracted_pages: list[dict[str, Any]] = []
        raw_full_chars = 0
        current_chapter = "Front Matter"
        current_section = "General"

        extracted_claims: list[dict[str, Any]] = []
        extracted_observations: list[dict[str, Any]] = []
        extracted_concepts: list[dict[str, Any]] = []

        ocr_pages_recovered = 0
        ocr_provider_used = "NONE"

        for page_idx in range(pages_processed):
            page_num = page_idx + 1
            page_obj = reader.pages[page_idx]
            try:
                page_text = page_obj.extract_text() or ""
            except Exception as e:
                logger.debug(f"Error extracting page {page_num}: {e}")
                page_text = ""

            page_is_ocr = False
            # Check if page has insufficient text and has embedded images (scanned PDF page)
            if len(page_text.strip()) < 40:
                page_images = getattr(page_obj, "images", None)
                if page_images and len(page_images) > 0:
                    try:
                        # Find largest image in the page (representing scanned raster)
                        largest_img = max(page_images, key=lambda img: len(getattr(img, "data", b"")))
                        img_bytes = getattr(largest_img, "data", b"")
                        if len(img_bytes) > 256:
                            ext = os.path.splitext(getattr(largest_img, "name", "page.png"))[1].lower()
                            mime = "image/jpeg" if ext in [".jpg", ".jpeg"] else "image/png"
                            ocr_text, prov = self.extract_page_with_vision(img_bytes, mime_type=mime)
                            if ocr_text:
                                page_text = ocr_text
                                page_is_ocr = True
                                ocr_pages_recovered += 1
                                ocr_provider_used = prov
                    except Exception as img_err:
                        logger.debug(f"Could not extract scanned image from page {page_num}: {img_err}")

            raw_full_chars += len(page_text)

            # Check if current page matches a TOC bookmark
            for bm in toc_bookmarks:
                if bm["page_number"] == page_num:
                    current_chapter = bm["title"]

            # Scan text for chapter/section headings
            chap_match = CHAPTER_REGEX.search(page_text)
            if chap_match:
                current_chapter = f"Chapter {chap_match.group(1)}: {chap_match.group(2).strip()}"

            sec_match = SECTION_REGEX.search(page_text)
            if sec_match:
                current_section = sec_match.group(1).strip()

            extracted_pages.append({
                "page_number": page_num,
                "chapter": current_chapter,
                "section": current_section,
                "character_count": len(page_text),
            })

            # Paragraph splitting
            paragraphs = [p.strip() for p in page_text.split("\n\n") if len(p.strip()) > 35]
            for p_idx, para in enumerate(paragraphs):
                # Clean linebreaks within paragraph
                clean_para = " ".join(para.split())
                if len(clean_para) < 40:
                    continue

                # Epistemic classification
                ep_type = self.classify_epistemic_type(clean_para)
                relevance_domain = self.classify_applicability_domain(clean_para)

                # Skip completely administrative/boilerplate text
                if any(w in clean_para.lower() for w in ["all rights reserved", "printed in the united states", "library of congress cataloging", "typeset in"]):
                    continue

                # Only extract paragraphs with substantial trading/quantitative substance
                is_substantive = (
                    ep_type in ["PROPOSED_RULE", "AUTHOR_REPORTED_STATISTIC", "DEFINITION", "HISTORICAL_OBSERVATION", "REPORTED_RESEARCH"]
                    or any(k in clean_para.lower() for k in ["liquidity", "order", "price", "market", "volatility", "risk", "edge", "trade", "trend", "fvg", "drawdown"])
                )

                if is_substantive:
                    # Constitutional Firewall (Article I, Section 1.5):
                    # Author reported statistics MUST NEVER be assumed as positive alpha (confidence = 0.0)
                    confidence = 0.0
                    claim_status = "UNVERIFIED"

                    extracted_claims.append({
                        "verbatim": clean_para[:500],
                        "subject": f"{relevance_domain}: {current_chapter[:35]}",
                        "direction": f"{current_chapter} ──► {relevance_domain} Market Dynamics",
                        "object_domain": relevance_domain,
                        "pdf_evidence_type": ep_type,
                        "epistemic_status": claim_status,
                        "confidence_score": confidence,
                        "book_title": meta["title"],
                        "book_isbn": meta["isbn"],
                        "book_edition": meta["edition"],
                        "chapter_title": current_chapter,
                        "section_title": current_section,
                        "page_number": page_num,
                        "paragraph_index": p_idx + 1,
                        "applicability_domain": relevance_domain,
                        "author_creator": meta["author"],
                        "is_ocr": page_is_ocr,
                    })

                    # Cap maximum claims per page to maintain high signal density
                    if len(extracted_claims) >= 120:
                        break
            if len(extracted_claims) >= 120:
                break

        # Check if scanned PDF (average chars per page < 40 or if OCR was needed)
        avg_chars = raw_full_chars / max(1, pages_processed)
        is_scanned = (avg_chars < 40.0) or (ocr_pages_recovered > 0)

        # Observations from book
        extracted_observations.append({
            "text": f"Literature '{meta['title']}' by {meta['author']} ({meta['edition']}). Parsed {pages_processed} pages across {len(set(p['chapter'] for p in extracted_pages))} chapters.",
            "period": f"Monograph Publication ({meta['creation_date'][:10] or 'Contemporary'})",
            "variables": ["VAR_BTC_RETURNS", "VAR_BTC_REALIZED_VOL"],
        })

        # Concepts from book
        extracted_concepts.append({
            "title": f"Literature Framework: {meta['title']}",
            "domain": "QUANTITATIVE_LITERATURE",
            "description": f"Formal conceptual framework by {meta['author']} addressing {len(extracted_claims)} auditable claims.",
            "tags": ["PDF_Book", "Literature", meta["edition"]],
        })

        # Synthesize Executive Summary Narrative & Chapter Breakdown
        rule_count = sum(1 for c in extracted_claims if c.get("pdf_evidence_type") == "PROPOSED_RULE")
        stat_count = sum(1 for c in extracted_claims if c.get("pdf_evidence_type") == "AUTHOR_REPORTED_STATISTIC")
        def_count = sum(1 for c in extracted_claims if c.get("pdf_evidence_type") == "DEFINITION")
        hist_count = sum(1 for c in extracted_claims if c.get("pdf_evidence_type") == "HISTORICAL_OBSERVATION")
        research_count = sum(1 for c in extracted_claims if c.get("pdf_evidence_type") == "REPORTED_RESEARCH")

        distinct_chaps = sorted(list(set(p['chapter'] for p in extracted_pages if p['chapter'] not in ["Front Matter", "General"])))
        chapter_list = distinct_chaps if distinct_chaps else ["Foundational Market Structure"]

        domains = sorted(list(set(c["applicability_domain"] for c in extracted_claims if c.get("applicability_domain"))))
        domain_list = domains if domains else ["MARKET_GENERAL"]

        exec_summary = (
            f"'{meta['title']}' by {meta['author']} ({meta['edition']}) establishes an institutional quantitative framework "
            f"spanning {pages_processed} analyzed pages across core chapters ({', '.join(chapter_list[:4])}). "
            f"The extraction pipeline decomposed {len(extracted_claims)} auditable atomic claims categorized across {', '.join(domain_list)} domains. "
            f"Extracted {rule_count} actionable execution rules and {def_count} structural definitions for Strategy League validation, "
            f"with {stat_count} author-reported statistics quarantined at confidence 0.0 under Constitutional Article I."
        )

        return {
            "success": True,
            "book_title": meta["title"],
            "author_creator": meta["author"],
            "isbn": meta["isbn"],
            "edition": meta["edition"],
            "total_pages": total_pages,
            "pages_processed": pages_processed,
            "is_scanned": is_scanned,
            "scanned_pages_ocr_processed": ocr_pages_recovered,
            "ocr_provider": ocr_provider_used,
            "avg_chars_per_page": round(avg_chars, 1),
            "toc_bookmarks_count": len(toc_bookmarks),
            "executive_summary": exec_summary,
            "chapter_breakdown": chapter_list,
            "epistemic_counts": {
                "PROPOSED_RULE": rule_count,
                "AUTHOR_REPORTED_STATISTIC": stat_count,
                "DEFINITION": def_count,
                "HISTORICAL_OBSERVATION": hist_count,
                "REPORTED_RESEARCH": research_count,
            },
            "claims": extracted_claims,
            "observations": extracted_observations,
            "concepts": extracted_concepts,
        }


# Master Singleton
pdf_book_extractor = PDFBookExtractor()
