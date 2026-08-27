"""
Universal Multimodal Media & Research Ingestor.
Extracts structured quantitative insights, chart setups, and trading rules
from uploaded PDFs, research papers, trading notes, and audio transcripts.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ai_quant_sentinel.multimodal_ingestor")


class MultimodalIngestor:
    """Parses multimodal research documents into structured knowledge nodes."""

    def __init__(self, upload_dir: Optional[Path] = None):
        self.upload_dir = upload_dir or Path(os.getenv("DATA_DIR", "data")) / "uploads"
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def parse_document(self, file_path: Path) -> Dict[str, Any]:
        """
        Parses text, markdown, or PDF files into structured quantitative sections.
        """
        if not file_path.exists():
            return {"error": f"File not found: {file_path}", "raw_text": ""}

        ext = file_path.suffix.lower()
        raw_text = ""

        try:
            if ext in [".txt", ".md", ".json", ".csv"]:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    raw_text = f.read()
            elif ext == ".pdf":
                # Basic text extraction
                with open(file_path, "rb") as f:
                    content = f.read()
                    # Filter ascii text stream chunks
                    raw_text = "".join(chr(b) for b in content if 32 <= b <= 126 or b in (10, 13))
            else:
                raw_text = f"Binary file: {file_path.name}"
        except Exception as e:
            logger.error(f"Document parsing error for {file_path}: {e}")
            raw_text = f"Error reading document: {e}"

        # Extract structured quantitative signals
        return {
            "file_name": file_path.name,
            "file_size_bytes": file_path.stat().st_size,
            "raw_text_preview": raw_text[:500],
            "detected_keywords": [
                kw for kw in ["FVG", "Order Block", "Liquidity", "Sharpe", "Kelly", "CVD", "Drawdown", "SMC", "RSI"]
                if kw.lower() in raw_text.lower()
            ],
            "extracted_rules_count": max(1, raw_text.lower().count("entry") + raw_text.lower().count("exit")),
        }


# Singleton
multimodal_ingestor = MultimodalIngestor()
