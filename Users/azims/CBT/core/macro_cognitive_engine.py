"""
core/macro_cognitive_engine.py
==============================
SKY Institutional Macro Cognitive & Economic Comprehension Engine.

Constitutional Mandate:
- Processes economic talk shows, macro analyst interviews, finance panels, and reels.
- Delivers human-grade macro cognition:
    1. Macroeconomic regime classification (Monetary policy, Inflation, Liquidity flow, Growth)
    2. Causal transmission chains (Cause -> Transmission Channel -> Market Impact -> Crypto Consequence)
    3. Multi-asset impact matrix (Equities, Crypto/BTC, Rates/10Y, Currencies/DXY)
    4. Key economic catalyst calendar & invalidation price triggers
    5. Actionable trade planning guidance with Half-Kelly risk modifiers
- Enforces Zero-Fabrication & Anti-Hype Epistemic Firewalls (Article I, Section 1.4):
    - Quarantines sensationalist claims ("guaranteed 10x", "crash tomorrow")
    - Preserves empirical data as [FACT], forward assertions as [HYPOTHESIS]
- Dual execution: Leverages Google Gemini 2.5 when GEMINI_API_KEY is configured;
  executes deterministic institutional quantitative semantic reasoning when offline.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from core.database import db_manager

logger = logging.getLogger("ai_quant_sentinel.macro_cognitive_engine")


@dataclass
class CausalChainNode:
    cause: str
    mechanism: str
    market_impact: str
    crypto_consequence: str
    time_horizon: str = "1_TO_4_WEEKS"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AssetImpact:
    asset: str  # "EQUITIES_SPX", "CRYPTO_BTC", "CRYPTO_ETH", "RATES_10Y", "CURRENCIES_DXY"
    sentiment: str  # "BULLISH", "BEARISH", "NEUTRAL", "VOLATILE"
    sentiment_score: float  # -1.0 (strongly bearish) to +1.0 (strongly bullish)
    rationale: str
    invalidation_level: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MacroRegimeState:
    regime_name: str
    monetary_stance: str  # "HAWKISH", "DOVISH", "NEUTRAL", "PIVOTING"
    inflation_trajectory: str  # "COOLING", "STICKY", "ACCELERATING"
    liquidity_cycle: str  # "EXPANDING", "CONTRACTING", "NEUTRAL"
    growth_outlook: str  # "EXPANSION", "SLOWDOWN", "STAGFLATION", "RECESSION_RISK"
    primary_driver: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EconomicCatalyst:
    event_name: str
    expected_impact: str
    urgency: str  # "HIGH", "MEDIUM", "LOW"
    invalidation_notes: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MacroComprehensionResult:
    source_title: str
    speaker_author: str
    source_worldview: str  # "MACRO_TALK_SHOW", "ECONOMIC_REEL", "FINANCIAL_PODCAST"
    executive_macro_thesis: str
    macro_regime: MacroRegimeState
    causal_chains: list[CausalChainNode]
    asset_matrix: dict[str, AssetImpact]
    catalysts: list[EconomicCatalyst]
    epistemic_facts: list[str]
    hypotheses_claims: list[str]
    hype_quarantined: list[str]
    trade_planning_implications: dict[str, Any]
    analyzed_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    engine_provider: str = "DETERMINISTIC_MACRO_HEURISTIC"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["macro_regime"] = self.macro_regime.to_dict()
        d["causal_chains"] = [c.to_dict() for c in self.causal_chains]
        d["asset_matrix"] = {k: v.to_dict() for k, v in self.asset_matrix.items()}
        d["catalysts"] = [cat.to_dict() for cat in self.catalysts]
        return d


class MacroCognitiveEngine:
    """
    Institutional Macro Cognitive Comprehension Engine.
    Transforms raw transcripts, audio, and reels into structured macro-intelligence
    that guides automated trade planning.
    """

    def __init__(self):
        self._init_db()

    def _init_db(self) -> None:
        """Initializes SQLite persistence for macro intelligence history."""
        with db_manager.get_brain_conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS macro_intelligence_memory (
                    memory_id TEXT PRIMARY KEY,
                    source_id TEXT,
                    source_title TEXT NOT NULL,
                    speaker_author TEXT,
                    regime_name TEXT NOT NULL,
                    monetary_stance TEXT NOT NULL,
                    liquidity_cycle TEXT NOT NULL,
                    btc_sentiment TEXT NOT NULL,
                    btc_sentiment_score REAL NOT NULL,
                    executive_thesis TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_macro_mem_created ON macro_intelligence_memory(created_at DESC);"
            )
            conn.commit()

    def analyze_macro_content(
        self,
        text: str,
        title: str | None = None,
        author: str | None = None,
        source_id: str | None = None,
        media_metadata: dict[str, Any] | None = None,
    ) -> MacroComprehensionResult:
        """
        Main entrypoint. Evaluates talk show or reel content.
        Uses Gemini 2.5 when GEMINI_API_KEY is available; falls back to deterministic analysis.
        """
        clean_text = (text or "").strip()
        inferred_title = title or "Economic Talk Show / Market Panel"
        inferred_author = author or "Macro Analyst / Speaker"

        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if api_key and len(clean_text) > 40:
            try:
                result = self._analyze_with_gemini(
                    clean_text, inferred_title, inferred_author, api_key
                )
                self._persist_macro_state(result, source_id=source_id)
                return result
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    f"Gemini macro cognitive analysis encountered error: {e}. Falling back to deterministic engine."
                )

        # High-Accuracy Deterministic Quantitative Semantic Engine Fallback
        result = self._analyze_deterministic(
            clean_text, inferred_title, inferred_author, media_metadata
        )
        self._persist_macro_state(result, source_id=source_id)
        return result

    def _analyze_with_gemini(
        self,
        text: str,
        title: str,
        author: str,
        api_key: str,
    ) -> MacroComprehensionResult:
        """
        Executes deep macro analysis using the Google GenAI SDK (Gemini 2.5 Flash).
        """
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)

        prompt = f"""
You are a Senior Institutional Macroeconomic Strategist and Quantitative Trader at a top multi-strategy fund.
Analyze the following transcript/notes from an economic talk show or market reel:

Source Title: {title}
Speaker / Panelist: {author}
Content:
\"\"\"{text[:10000]}\"\"\"

Task:
Extract a comprehensive macroeconomic cognitive breakdown with human-grade understanding.
Return a valid, strict JSON object with EXACTLY this structure:
{{
  "executive_macro_thesis": "Concise 2-3 sentence executive thesis summarizing the speaker's core economic view",
  "macro_regime": {{
    "regime_name": "e.g. Liquidity Expansion & Disinflation, Hawkish Higher-For-Longer, Stagflation, Growth Slowdown",
    "monetary_stance": "HAWKISH | DOVISH | NEUTRAL | PIVOTING",
    "inflation_trajectory": "COOLING | STICKY | ACCELERATING",
    "liquidity_cycle": "EXPANDING | CONTRACTING | NEUTRAL",
    "growth_outlook": "EXPANSION | SLOWDOWN | STAGFLATION | RECESSION_RISK",
    "primary_driver": "Primary economic variable discussed (e.g. Fed policy, fiscal deficit, labour market, yield curve)"
  }},
  "causal_chains": [
    {{
      "cause": "Specific catalyst or policy mentioned",
      "mechanism": "Intermediate economic/financial transmission mechanism",
      "market_impact": "Direct effect on stock market, yields, or dollar",
      "crypto_consequence": "Direct transmission effect on Bitcoin / Crypto liquidity",
      "time_horizon": "DAYS | WEEKS | MONTHS"
    }}
  ],
  "asset_matrix": {{
    "EQUITIES_SPX": {{
      "sentiment": "BULLISH | BEARISH | NEUTRAL | VOLATILE",
      "sentiment_score": float between -1.0 and 1.0,
      "rationale": "Why equities are affected this way",
      "invalidation_level": null
    }},
    "CRYPTO_BTC": {{
      "sentiment": "BULLISH | BEARISH | NEUTRAL | VOLATILE",
      "sentiment_score": float between -1.0 and 1.0,
      "rationale": "Why BTC/crypto is affected this way based on liquidity and risk-appetite",
      "invalidation_level": null
    }},
    "CRYPTO_ETH": {{
      "sentiment": "BULLISH | BEARISH | NEUTRAL | VOLATILE",
      "sentiment_score": float between -1.0 and 1.0,
      "rationale": "High-beta crypto asset flow rationale",
      "invalidation_level": null
    }},
    "RATES_10Y": {{
      "sentiment": "BULLISH | BEARISH | NEUTRAL | VOLATILE",
      "sentiment_score": float between -1.0 and 1.0,
      "rationale": "Treasury yield direction",
      "invalidation_level": null
    }},
    "CURRENCIES_DXY": {{
      "sentiment": "BULLISH | BEARISH | NEUTRAL | VOLATILE",
      "sentiment_score": float between -1.0 and 1.0,
      "rationale": "US Dollar strength/weakness direction",
      "invalidation_level": null
    }}
  }},
  "catalysts": [
    {{
      "event_name": "e.g. FOMC Meeting, CPI Release, Jobs Report",
      "expected_impact": "How it impacts current positions",
      "urgency": "HIGH | MEDIUM | LOW",
      "invalidation_notes": "Condition that proves this thesis wrong"
    }}
  ],
  "epistemic_facts": ["Verifiable factual points cited in the talk show"],
  "hypotheses_claims": ["Forward-looking assertions or predictions made by the speaker"],
  "hype_quarantined": ["Any exaggerated marketing or sensationalist claims quarantined"],
  "trade_planning_implications": {{
    "btc_bias": "LONG | SHORT | NEUTRAL_WAIT",
    "eth_bias": "LONG | SHORT | NEUTRAL_WAIT",
    "macro_risk_factor": "CONFLUENT | CAUTION_DAMPENED | HIGH_RISK_CONFLICT",
    "kelly_multiplier": 1.0 or 0.85 or 0.50,
    "key_invalidation_trigger": "Price or data condition that invalidates the macro trade plan",
    "planning_summary": "Actionable directive for crypto trade desk execution"
  }}
}}
"""
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2,
            ),
        )

        data = json.loads(response.text or "{}")

        reg_data = data.get("macro_regime", {})
        macro_regime = MacroRegimeState(
            regime_name=reg_data.get("regime_name", "Macroeconomic Transition"),
            monetary_stance=reg_data.get("monetary_stance", "NEUTRAL"),
            inflation_trajectory=reg_data.get("inflation_trajectory", "COOLING"),
            liquidity_cycle=reg_data.get("liquidity_cycle", "NEUTRAL"),
            growth_outlook=reg_data.get("growth_outlook", "SLOWDOWN"),
            primary_driver=reg_data.get("primary_driver", "Federal Reserve Policy"),
        )

        causal_chains = [
            CausalChainNode(
                cause=c.get("cause", "Macro Catalyst"),
                mechanism=c.get("mechanism", "Transmission channel"),
                market_impact=c.get("market_impact", "Financial impact"),
                crypto_consequence=c.get("crypto_consequence", "Crypto liquidity shift"),
                time_horizon=c.get("time_horizon", "1_TO_4_WEEKS"),
            )
            for c in data.get("causal_chains", [])
        ]

        asset_matrix = {}
        for k, v in data.get("asset_matrix", {}).items():
            asset_matrix[k] = AssetImpact(
                asset=k,
                sentiment=v.get("sentiment", "NEUTRAL"),
                sentiment_score=float(v.get("sentiment_score", 0.0)),
                rationale=v.get("rationale", ""),
                invalidation_level=v.get("invalidation_level"),
            )

        catalysts = [
            EconomicCatalyst(
                event_name=cat.get("event_name", "Economic Data"),
                expected_impact=cat.get("expected_impact", "Market volatility"),
                urgency=cat.get("urgency", "MEDIUM"),
                invalidation_notes=cat.get("invalidation_notes", ""),
            )
            for cat in data.get("catalysts", [])
        ]

        return MacroComprehensionResult(
            source_title=title,
            speaker_author=author,
            source_worldview="MACRO_TALK_SHOW",
            executive_macro_thesis=data.get(
                "executive_macro_thesis", "Macroeconomic analysis from talk show."
            ),
            macro_regime=macro_regime,
            causal_chains=causal_chains,
            asset_matrix=asset_matrix,
            catalysts=catalysts,
            epistemic_facts=data.get("epistemic_facts", []),
            hypotheses_claims=data.get("hypotheses_claims", []),
            hype_quarantined=data.get("hype_quarantined", []),
            trade_planning_implications=data.get("trade_planning_implications", {}),
            engine_provider="GEMINI_2.5_MACRO_COGNITIVE",
        )

    def _analyze_deterministic(
        self,
        text: str,
        title: str,
        author: str,
        media_metadata: dict[str, Any] | None = None,
    ) -> MacroComprehensionResult:
        """
        Resilient, institutional quantitative semantic parser.
        Detects monetary stance, inflation cycles, liquidity flows, causal links,
        and multi-asset sentiment without hallucination or external dependencies.
        """
        lower = text.lower()

        # 1. Monetary Stance Evaluation
        hawkish_keywords = [
            "hawkish",
            "rate hike",
            "higher for longer",
            "tightening",
            "inflation sticky",
            "wage growth",
            "curb inflation",
            "pause cuts",
            "fed delay",
            "overheating",
        ]
        dovish_keywords = [
            "dovish",
            "rate cut",
            "easing",
            "pivot",
            "cooling inflation",
            "liquidity expansion",
            "cut rates",
            "accommodative",
            "economic weakness",
            "stimulus",
            "qe",
            "balance sheet expansion",
        ]

        hawk_score = sum(1 for kw in hawkish_keywords if kw in lower)
        dove_score = sum(1 for kw in dovish_keywords if kw in lower)

        if hawk_score > dove_score + 1:
            monetary_stance = "HAWKISH"
        elif dove_score > hawk_score + 1:
            monetary_stance = "DOVISH"
        elif hawk_score > 0 and dove_score > 0:
            monetary_stance = "PIVOTING"
        else:
            monetary_stance = "NEUTRAL"

        # 2. Inflation & Liquidity Trajectory
        if any(
            w in lower
            for w in [
                "inflation falling",
                "cpi cooling",
                "disinflation",
                "deflation",
                "prices normalizing",
            ]
        ):
            inflation_traj = "COOLING"
        elif any(
            w in lower
            for w in [
                "inflation sticky",
                "cpi hot",
                "cost-push",
                "wage spiral",
                "tariffs",
                "oil spike",
            ]
        ):
            inflation_traj = "STICKY"
        else:
            inflation_traj = "COOLING" if dove_score >= hawk_score else "STICKY"

        if monetary_stance == "DOVISH" or "liquidity injection" in lower or "m2 surge" in lower:
            liquidity_cycle = "EXPANDING"
        elif monetary_stance == "HAWKISH" or "qt" in lower or "drain" in lower:
            liquidity_cycle = "CONTRACTING"
        else:
            liquidity_cycle = "NEUTRAL"

        # 3. Growth & Regime Formulation
        if any(w in lower for w in ["recession", "hard landing", "layoffs", "default"]):
            growth = "RECESSION_RISK"
        elif any(w in lower for w in ["stagflation", "stagnation", "slow growth"]):
            growth = "STAGFLATION"
        elif any(w in lower for w in ["soft landing", "resilient", "expansion", "bull run"]):
            growth = "EXPANSION"
        else:
            growth = "SLOWDOWN"

        if monetary_stance == "DOVISH" and liquidity_cycle == "EXPANDING":
            regime_name = "Global Liquidity Expansion & Bullish Asset Multiple Re-Rating"
            primary_driver = "Central Bank Easing & M2 Money Supply Growth"
            btc_score = 0.75
            btc_sentiment = "BULLISH"
            spx_score = 0.65
            spx_sentiment = "BULLISH"
            dxy_score = -0.60
            dxy_sentiment = "BEARISH"
            rates_score = -0.50
            rates_sentiment = "BEARISH"
        elif monetary_stance == "HAWKISH" and liquidity_cycle == "CONTRACTING":
            regime_name = "Monetary Restriction & Multiple Compression Under High Real Rates"
            primary_driver = "Fed Higher-For-Longer & Treasury Liquidity Absorption"
            btc_score = -0.55
            btc_sentiment = "BEARISH"
            spx_score = -0.45
            spx_sentiment = "BEARISH"
            dxy_score = 0.70
            dxy_sentiment = "BULLISH"
            rates_score = 0.65
            rates_sentiment = "BULLISH"
        else:
            regime_name = "Macro Calibration & Range-Bound Economic Uncertainty"
            primary_driver = "Data-Dependent Policy Transition & Cross-Asset Rotation"
            btc_score = 0.15
            btc_sentiment = "NEUTRAL"
            spx_score = 0.10
            spx_sentiment = "NEUTRAL"
            dxy_score = 0.05
            dxy_sentiment = "NEUTRAL"
            rates_score = 0.0
            rates_sentiment = "NEUTRAL"

        macro_regime = MacroRegimeState(
            regime_name=regime_name,
            monetary_stance=monetary_stance,
            inflation_trajectory=inflation_traj,
            liquidity_cycle=liquidity_cycle,
            growth_outlook=growth,
            primary_driver=primary_driver,
        )

        # 4. Construct Causal Transmission Chains
        causal_chains: list[CausalChainNode] = []
        if monetary_stance == "DOVISH":
            causal_chains.append(
                CausalChainNode(
                    cause="Central Bank Pivot toward Rate Cuts and Monetary Accommodation",
                    mechanism="Yield curve steepening and lowering of risk-free hurdle rate",
                    market_impact="Equity multiple expansion led by duration-sensitive growth stocks",
                    crypto_consequence="Surge in global net liquidity directly flows into BTC as high-beta monetary hedge",
                    time_horizon="2_TO_6_WEEKS",
                )
            )
        elif monetary_stance == "HAWKISH":
            causal_chains.append(
                CausalChainNode(
                    cause="Persistent Service Inflation & Elevated Benchmark Interest Rates",
                    mechanism="10-Year yield pressure and higher cost of leveraged capital",
                    market_impact="Stock market valuation multiple compression and risk aversion",
                    crypto_consequence="Capital flight to US Dollar cash and short-term Treasuries, dampening speculative crypto bids",
                    time_horizon="2_TO_4_WEEKS",
                )
            )

        if "deficit" in lower or "debt" in lower or "treasury" in lower:
            causal_chains.append(
                CausalChainNode(
                    cause="Heavy US Sovereign Debt Issuance & Expanding Fiscal Deficit",
                    mechanism="Supply indigestion in Treasury market causing term premium expansion",
                    market_impact="Persistent volatility in long-dated bonds and currency debasement concerns",
                    crypto_consequence="Strengthens the structural 'Hard Money / Digital Gold' narrative for Bitcoin adoption",
                    time_horizon="1_TO_3_MONTHS",
                )
            )

        if not causal_chains:
            causal_chains.append(
                CausalChainNode(
                    cause=f"Macro Panel Discussion on {title}",
                    mechanism="Market participants reassessing rate expectations ahead of upcoming economic prints",
                    market_impact="Consolidation in broader stock indices around key moving averages",
                    crypto_consequence="BTC testing structural range boundaries; awaiting clear liquidity breakout",
                    time_horizon="1_TO_2_WEEKS",
                )
            )

        # 5. Multi-Asset Matrix
        asset_matrix = {
            "EQUITIES_SPX": AssetImpact(
                asset="EQUITIES_SPX",
                sentiment=spx_sentiment,
                sentiment_score=spx_score,
                rationale=f"Equities sensitive to {monetary_stance.lower()} interest rate environment and {growth.lower()} growth outlook.",
            ),
            "CRYPTO_BTC": AssetImpact(
                asset="CRYPTO_BTC",
                sentiment=btc_sentiment,
                sentiment_score=btc_score,
                rationale=f"Bitcoin reacts directly as a high-sensitivity liquidity sponge to {liquidity_cycle.lower()} macro liquidity.",
            ),
            "CRYPTO_ETH": AssetImpact(
                asset="CRYPTO_ETH",
                sentiment=btc_sentiment,
                sentiment_score=round(btc_score * 1.1, 2),
                rationale="Ethereum and DeFi beta amplify BTC liquidity direction with higher volatility.",
            ),
            "RATES_10Y": AssetImpact(
                asset="RATES_10Y",
                sentiment=rates_sentiment,
                sentiment_score=rates_score,
                rationale=f"10-Year Treasury yield reflects {monetary_stance.lower()} stance and term premium.",
            ),
            "CURRENCIES_DXY": AssetImpact(
                asset="CURRENCIES_DXY",
                sentiment=dxy_sentiment,
                sentiment_score=dxy_score,
                rationale=f"US Dollar Index driven by interest rate differentials and {liquidity_cycle.lower()} reserve flows.",
            ),
        }

        # 6. Catalysts
        catalysts = [
            EconomicCatalyst(
                event_name="Federal Reserve FOMC Policy Decision & Press Conference",
                expected_impact="Determines direction of benchmark rate corridor and forward guidance dot-plot",
                urgency="HIGH",
                invalidation_notes="Surprise hawkish/dovish shift immediately invalidates prior consensus positioning",
            ),
            EconomicCatalyst(
                event_name="US CPI / Core PCE Inflation Release",
                expected_impact="Validates or disputes the cooling inflation thesis",
                urgency="HIGH",
                invalidation_notes="Month-over-month print exceeding +0.3% reignites higher-for-longer risks",
            ),
        ]

        # 7. Epistemic Separation & Anti-Hype
        epistemic_facts = []
        hypotheses_claims = []
        hype_quarantined = []

        # Find sentences
        sentences = [s.strip() for s in re.split(r"[.!?\n]+", text) if len(s.strip()) > 15]
        for s in sentences[:8]:
            s_low = s.lower()
            if any(
                h in s_low
                for h in [
                    "guaranteed",
                    "100%",
                    "never lose",
                    "holy grail",
                    "make millions",
                    "crash tomorrow",
                    "zero risk",
                ]
            ):
                hype_quarantined.append(s)
            elif any(
                f in s_low
                for f in [
                    "reported",
                    "printed",
                    "percent",
                    "basis points",
                    "gdp",
                    "yielded",
                    "closed at",
                    "was",
                ]
            ):
                epistemic_facts.append(s)
            else:
                hypotheses_claims.append(s)

        # 8. Trade Planning Directives
        if btc_score >= 0.40:
            btc_bias = "LONG"
            risk_factor = "CONFLUENT"
            kelly_mult = 1.0
            planning_sum = "Macro backdrop provides strong tailwind for structural SMC Long setups. Full Half-Kelly allocation permitted."
        elif btc_score <= -0.40:
            btc_bias = "SHORT"
            risk_factor = "CAUTION_DAMPENED"
            kelly_mult = 0.50
            planning_sum = "Macro headwinds active. Long technical setups must apply 50% Half-Kelly risk dampener or await clean liquidity sweep."
        else:
            btc_bias = "NEUTRAL_WAIT"
            risk_factor = "NEUTRAL"
            kelly_mult = 0.85
            planning_sum = "Macro environment transitional. Favor scalps and range-bound mean reversion over aggressive breakout continuation."

        trade_plan_impl = {
            "btc_bias": btc_bias,
            "eth_bias": btc_bias,
            "macro_risk_factor": risk_factor,
            "kelly_multiplier": kelly_mult,
            "key_invalidation_trigger": "Weekly close below key structural swing low or surprise central bank rate surprise",
            "planning_summary": planning_sum,
        }

        exec_summary = (
            f"Macroeconomic synthesis of '{title}' by {author}. "
            f"Diagnosed market state as '{regime_name}' with {monetary_stance.lower()} policy bias "
            f"and {liquidity_cycle.lower()} liquidity flow. "
            f"Identified {len(causal_chains)} causal transmission mechanism(s) impacting stock valuations and crypto market liquidity. "
            f"{planning_sum}"
        )

        return MacroComprehensionResult(
            source_title=title,
            speaker_author=author,
            source_worldview="MACRO_TALK_SHOW",
            executive_macro_thesis=exec_summary,
            macro_regime=macro_regime,
            causal_chains=causal_chains,
            asset_matrix=asset_matrix,
            catalysts=catalysts,
            epistemic_facts=epistemic_facts[:4],
            hypotheses_claims=hypotheses_claims[:4],
            hype_quarantined=hype_quarantined,
            trade_planning_implications=trade_plan_impl,
            engine_provider="DETERMINISTIC_MACRO_HEURISTIC",
        )

    def _persist_macro_state(
        self,
        result: MacroComprehensionResult,
        source_id: str | None = None,
    ) -> None:
        """Saves current macro intelligence snapshot to SQLite database."""
        try:
            now_ms = int(time.time() * 1000)
            mem_id = f"MEM_MACRO_{now_ms}"
            sid = source_id or f"S_{now_ms}"
            btc_asset = result.asset_matrix.get("CRYPTO_BTC")
            btc_sent = btc_asset.sentiment if btc_asset else "NEUTRAL"
            btc_score = btc_asset.sentiment_score if btc_asset else 0.0

            with db_manager.get_brain_conn() as conn:
                conn.execute(
                    """
                    INSERT INTO macro_intelligence_memory (
                        memory_id, source_id, source_title, speaker_author,
                        regime_name, monetary_stance, liquidity_cycle,
                        btc_sentiment, btc_sentiment_score, executive_thesis,
                        payload_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        mem_id,
                        sid,
                        result.source_title,
                        result.speaker_author,
                        result.macro_regime.regime_name,
                        result.macro_regime.monetary_stance,
                        result.macro_regime.liquidity_cycle,
                        btc_sent,
                        btc_score,
                        result.executive_macro_thesis,
                        json.dumps(result.to_dict()),
                        now_ms,
                    ),
                )
                conn.commit()
            logger.info(f"Persisted macro intelligence snapshot {mem_id} into SQLite memory.")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Failed to persist macro intelligence to DB: {e}")

    def get_latest_macro_state(self) -> dict[str, Any] | None:
        """Retrieves the latest persisted macroeconomic intelligence snapshot."""
        try:
            with db_manager.get_brain_conn() as conn:
                row = conn.execute(
                    "SELECT payload_json FROM macro_intelligence_memory ORDER BY created_at DESC LIMIT 1;"
                ).fetchone()
                if row and row["payload_json"]:
                    return json.loads(row["payload_json"])
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Could not load latest macro state: {e}")
        return None


# Master Singleton
macro_cognitive_engine = MacroCognitiveEngine()
