"""
core/intelligence/crawler/adapters/__init__.py
==============================================
Domain-specific intelligence adapters for Milestone 30-B.
"""

from core.intelligence.crawler.adapters.academic_adapter import AcademicPaperAdapter
from core.intelligence.crawler.adapters.macro_adapter import MacroCentralBankAdapter
from core.intelligence.crawler.adapters.news_wire_adapter import NewsWireAdapter
from core.intelligence.crawler.adapters.onchain_adapter import OnChainAdapter
from core.intelligence.crawler.adapters.sec_edgar_adapter import SecEdgarAdapter

__all__ = [
    "AcademicPaperAdapter",
    "MacroCentralBankAdapter",
    "NewsWireAdapter",
    "OnChainAdapter",
    "SecEdgarAdapter",
]
