"""
Semantic Relevance Gate for SKY Intelligence Ingestion.

Suppresses off-topic web noise, advertising, and low-signal chatter.
Requires a quantitative relevance score >= 0.70 against:
- Macroeconomic monetary policy & indicators
- Crypto assets, on-chain dynamics & market microstructure
- Technology equities, semiconductor supply chains & corporate filings
- Quantitative finance, statistical research & Smart Money Concepts (SMC)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from core.intelligence.schema import IntelligenceDomain

# Taxonomy keyword maps per domain
TAXONOMY_PATTERNS: dict[IntelligenceDomain, list[str]] = {
    IntelligenceDomain.MACRO: [
        r"\bfed(eral\s+reserve)?\b",
        r"\bfomc\b",
        r"\binterest\s+rates?\b",
        r"\brate\s+(hike|cut|cuts|pause)\b",
        r"\binflation\b",
        r"\bcpi\b",
        r"\bppi\b",
        r"\bpce\b",
        r"\bgdp\b",
        r"\bunemployment\b",
        r"\bnon-?farm\s+payrolls?\b",
        r"\btreasury(\s+yields?)?\b",
        r"\byield\s+curve\b",
        r"\bdxy\b",
        r"\bdollar\s+index\b",
        r"\bquantitative\s+(easing|tightening)\b",
        r"\bqe\b|\bqt\b",
        r"\bliquidity\b",
        r"\becb\b",
        r"\bboj\b",
        r"\bpboc\b",
        r"\bpowell\b",
        r"\byellen\b",
    ],
    IntelligenceDomain.CRYPTO: [
        r"\bbitcoin\b|\bbtc\b",
        r"\beth(ereum)?\b",
        r"\bsol(ana)?\b",
        r"\bbinance\b|\bbybit\b|\bcoinbase\b",
        r"\bcrypto(currency)?\b",
        r"\bspot\s+etf\b",
        r"\bon-?chain\b",
        r"\bhashrate\b",
        r"\bhalving\b",
        r"\bdefi\b|\bl2\b|\blayer\s*2\b",
        r"\btoken(omics)?\b",
        r"\bliquidation(s)?\b",
        r"\bfunding\s+rate(s)?\b",
        r"\bopen\s+interest\b",
        r"\bstablecoin(s)?\b",
        r"\busdt\b|\busdc\b",
        r"\bsec\b|\bgensler\b",
        r"\bhard\s+fork\b",
        r"\beip-\d+\b",
    ],
    IntelligenceDomain.EQUITIES: [
        r"\bnvda\b|\bnvidia\b",
        r"\baapl\b|\bapple\b",
        r"\bmsft\b|\bmicrosoft\b",
        r"\btsla\b|\btesla\b",
        r"\bgoogl?\b|\balphabet\b",
        r"\bamzn\b|\bamazon\b",
        r"\bmeta\b",
        r"\bsemiconductor(s)?\b|\btsmc\b|\basml\b",
        r"\bearnings(\s+report)?\b",
        r"\bsec\s+10-[kq]\b",
        r"\bguidance\b",
        r"\bcapex\b",
        r"\boperating\s+margin\b",
        r"\bshares?\b|\bequity\b|\bequities\b",
        r"\bs&p\s*500\b|\bspx\b|\bnasdaq\b|\bqqq\b",
    ],
    IntelligenceDomain.QUANT_RESEARCH: [
        r"\bmarket\s+microstructure\b",
        r"\border\s*book\b|\bl2\s+depth\b|\bdepth\s+chart\b",
        r"\border\s+flow(\s+imbalance)?\b|\bobi\b",
        r"\bvpin\b",
        r"\bsmart\s+money(\s+concepts?)?\b|\bsmc\b",
        r"\border\s*block(s)?\b",
        r"\bfair\s+value\s+gap(s)?\b|\bfvg\b",
        r"\bliquidity\s+pool(s)?\b|\bliquidity\s+sweep\b",
        r"\bmitigation\s+block\b",
        r"\bhalf-?kelly\b|\bkelly\s+criterion\b",
        r"\bslippage\b|\balmgren-?chriss\b",
        r"\bvolatility\b|\bgarch\b|\bimplied\s+vol\b|\biv\b",
        r"\bbacktest(ing)?\b|\bwalk-?forward\b",
        r"\bsharpe(\s+ratio)?\b|\bsortino\b|\bmax\s+drawdown\b",
        r"\bcpcv\b|\bdsr\b|\bwrc\b",
    ],
    IntelligenceDomain.SOCIAL: [
        r"\bsentiment\b",
        r"\bfomo\b|\bfud\b",
        r"\bbull(ish)?\b|\bbear(ish)?\b",
        r"\bretail\s+(traders?|flows?)\b",
        r"\btrending\b",
        r"\bnarrative\b",
        r"\bwhale\s+alert\b",
    ],
}

KNOWN_ENTITIES = [
    "BTC",
    "ETH",
    "SOL",
    "BNB",
    "XRP",
    "DOGE",
    "ADA",
    "AVAX",
    "LINK",
    "UNI",
    "NVDA",
    "AAPL",
    "MSFT",
    "TSLA",
    "GOOGL",
    "AMZN",
    "META",
    "TSMC",
    "ASML",
    "FED",
    "FOMC",
    "POWELL",
    "SEC",
    "ECB",
    "BOJ",
    "PBOC",
    "CPI",
    "PCE",
    "DXY",
    "GOLD",
]


@dataclass
class RelevanceVerdict:
    is_relevant: bool
    relevance_score: float
    primary_domain: IntelligenceDomain
    matched_entities: list[str] = field(default_factory=list)
    matched_topics: list[str] = field(default_factory=list)
    rationale: str = ""


class RelevanceGate:
    """
    Evaluates whether an external article, tweet, RSS item, or report meets
    the institutional quantitative relevance threshold (default: 0.70).
    """

    def __init__(self, threshold: float = 0.70) -> None:
        self.threshold = threshold
        self._compiled_taxonomies = {
            domain: [re.compile(p, re.IGNORECASE) for p in patterns]
            for domain, patterns in TAXONOMY_PATTERNS.items()
        }
        self._entity_patterns = [
            (ent, re.compile(rf"\b{re.escape(ent)}\b", re.IGNORECASE)) for ent in KNOWN_ENTITIES
        ]

    def evaluate(self, title: str, content: str) -> RelevanceVerdict:
        """
        Calculates domain relevance and returns a structured verdict.
        """
        combined_text = f"{title}\n{content}"
        if not combined_text.strip():
            return RelevanceVerdict(
                is_relevant=False,
                relevance_score=0.0,
                primary_domain=IntelligenceDomain.MACRO,
                rationale="Empty input text.",
            )

        # 1. Extract entities
        matched_entities: set[str] = set()
        for ent, pat in self._entity_patterns:
            if pat.search(combined_text):
                matched_entities.add(ent)

        # 2. Count pattern matches per domain
        domain_scores: dict[IntelligenceDomain, float] = {}
        matched_topics: list[str] = []

        for domain, patterns in self._compiled_taxonomies.items():
            matches = 0
            for pat in patterns:
                found = pat.findall(combined_text)
                if found:
                    matches += len(found)
                    matched_topics.append(pat.pattern.strip(r"\b"))

            # Base score contribution from matches
            score = min(1.0, (matches * 0.18) + (len(matched_entities) * 0.12))
            domain_scores[domain] = score

        # Determine primary domain
        sorted_domains = sorted(domain_scores.items(), key=lambda x: x[1], reverse=True)
        primary_domain, top_score = sorted_domains[0]

        # Bonus for title match (titles indicate high relevance)
        title_matches = 0
        for pat in self._compiled_taxonomies[primary_domain]:
            if pat.search(title):
                title_matches += 1
        if title_matches > 0:
            top_score = min(1.0, top_score + 0.20)

        # Normalize score
        final_score = round(min(1.0, max(0.0, top_score)), 4)
        is_relevant = final_score >= self.threshold

        rationale = (
            f"Domain: {primary_domain.value}, Score: {final_score:.2f} (Threshold: {self.threshold:.2f}). "
            f"Entities: {list(matched_entities)[:5]}, Matches: {len(matched_topics)}."
        )

        return RelevanceVerdict(
            is_relevant=is_relevant,
            relevance_score=final_score,
            primary_domain=primary_domain,
            matched_entities=sorted(list(matched_entities)),
            matched_topics=sorted(list(set(matched_topics)))[:8],
            rationale=rationale,
        )


# Default global relevance gate
global_relevance_gate = RelevanceGate()
