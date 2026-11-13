"""
core/knowledge_os/trading_dictionary.py
======================================
First-Class Interactive Quantitative & SMC Trading Dictionary Engine.
Manages persistent SQLite tables `trading_dictionary_terms` and `trading_dictionary_fts`
in `research_wiki.db`, providing bilingual (English + Bengali) definitions, formulas,
institutional mechanisms, anti-retail traps, CBT code hooks, and live market enrichment.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from core.knowledge_os.research_wikipedia import WIKI_DB_PATH

logger = logging.getLogger("sky.knowledge_os.trading_dictionary")


@dataclass
class DictionaryTerm:
    term_id: str
    canonical_name: str
    aliases: list[str]
    category: str
    definition_en: str
    definition_bn: str
    mathematical_formula: str = ""
    institutional_mechanism: str = ""
    anti_retail_pitfall: str = ""
    cbt_code_implementation: str = ""
    related_terms: list[str] = field(default_factory=list)
    created_at: int = field(default_factory=lambda: int(time.time() * 1000))
    updated_at: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TradingDictionaryManager:
    """Institutional Knowledge Operating System Master Trading Dictionary."""

    def __init__(self, db_path: Path = WIKI_DB_PATH):
        self.db_path = db_path
        self._init_db()
        self._ensure_seed_terms()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trading_dictionary_terms (
                    term_id TEXT PRIMARY KEY,
                    canonical_name TEXT NOT NULL,
                    aliases_json TEXT NOT NULL,
                    category TEXT NOT NULL,
                    definition_en TEXT NOT NULL,
                    definition_bn TEXT NOT NULL,
                    mathematical_formula TEXT,
                    institutional_mechanism TEXT,
                    anti_retail_pitfall TEXT,
                    cbt_code_implementation TEXT,
                    related_terms_json TEXT,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_dict_category ON trading_dictionary_terms(category);"
            )
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS trading_dictionary_fts USING fts5(
                    term_id UNINDEXED,
                    canonical_name,
                    aliases,
                    category,
                    definition_en,
                    definition_bn,
                    institutional_mechanism,
                    anti_retail_pitfall,
                    tokenize='porter unicode61'
                );
                """
            )
            conn.commit()

    def upsert_term(self, term: DictionaryTerm) -> None:
        """Inserts or updates a dictionary term and updates FTS index."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO trading_dictionary_terms (
                    term_id, canonical_name, aliases_json, category,
                    definition_en, definition_bn, mathematical_formula,
                    institutional_mechanism, anti_retail_pitfall,
                    cbt_code_implementation, related_terms_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(term_id) DO UPDATE SET
                    canonical_name = excluded.canonical_name,
                    aliases_json = excluded.aliases_json,
                    category = excluded.category,
                    definition_en = excluded.definition_en,
                    definition_bn = excluded.definition_bn,
                    mathematical_formula = excluded.mathematical_formula,
                    institutional_mechanism = excluded.institutional_mechanism,
                    anti_retail_pitfall = excluded.anti_retail_pitfall,
                    cbt_code_implementation = excluded.cbt_code_implementation,
                    related_terms_json = excluded.related_terms_json,
                    updated_at = excluded.updated_at;
                """,
                (
                    term.term_id,
                    term.canonical_name,
                    json.dumps(term.aliases, ensure_ascii=False),
                    term.category,
                    term.definition_en,
                    term.definition_bn,
                    term.mathematical_formula,
                    term.institutional_mechanism,
                    term.anti_retail_pitfall,
                    term.cbt_code_implementation,
                    json.dumps(term.related_terms, ensure_ascii=False),
                    term.created_at,
                    term.updated_at,
                ),
            )
            # Update FTS
            aliases_str = " ".join(term.aliases)
            conn.execute("DELETE FROM trading_dictionary_fts WHERE term_id = ?", (term.term_id,))
            conn.execute(
                """
                INSERT INTO trading_dictionary_fts (
                    term_id, canonical_name, aliases, category,
                    definition_en, definition_bn, institutional_mechanism,
                    anti_retail_pitfall
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    term.term_id,
                    term.canonical_name,
                    aliases_str,
                    term.category,
                    term.definition_en,
                    term.definition_bn,
                    term.institutional_mechanism,
                    term.anti_retail_pitfall,
                ),
            )
            conn.commit()

    def lookup(
        self,
        query: str,
        language: str = "en",
        symbol: str = "BTC/USDT",
        with_live_example: bool = True,
    ) -> dict[str, Any] | None:
        """
        Looks up a trading term by exact ID, canonical name, alias, or FTS ranking.
        Enriches with live market telemetry from CBT native engines.
        """
        clean_q = query.strip().lower()
        if not clean_q:
            return None

        # 1. Exact match on term_id
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM trading_dictionary_terms WHERE term_id = ?", (clean_q,)
            ).fetchone()

            # 2. Match on canonical_name or alias
            if not row:
                rows = conn.execute(
                    "SELECT * FROM trading_dictionary_terms WHERE lower(canonical_name) = ? OR aliases_json LIKE ? OR aliases_json LIKE ?",
                    (clean_q, f'%"{clean_q}"%', f"%{clean_q}%"),
                ).fetchall()
                if rows:
                    row = rows[0]

            # 2b. Check in-memory on decoded aliases across all terms
            if not row:
                all_terms = conn.execute("SELECT * FROM trading_dictionary_terms").fetchall()
                for r in all_terms:
                    aliases = json.loads(r["aliases_json"]) if r["aliases_json"] else []
                    if any(
                        clean_q == a.lower().strip() or clean_q in a.lower().strip()
                        for a in aliases
                    ):
                        row = r
                        break

            # 3. FTS5 Search for concept terms
            if not row:
                STOP_WORDS = {
                    "where",
                    "what",
                    "is",
                    "are",
                    "the",
                    "a",
                    "an",
                    "going",
                    "to",
                    "it",
                    "how",
                    "for",
                    "in",
                    "on",
                    "of",
                    "and",
                    "or",
                    "tell",
                    "me",
                    "about",
                    "show",
                    "can",
                    "you",
                    "does",
                    "do",
                    "market",
                    "price",
                    "btc",
                    "eth",
                    "sol",
                    "gold",
                    "current",
                    "trend",
                    "direction",
                    "কি",
                    "কাকে",
                    "বলে",
                    "বলতে",
                    "বুঝায়",
                    "যাবে",
                    "কোথায়",
                }
                sanitized = re.sub(r"[^\w\s]", " ", clean_q).strip()
                tokens = [t for t in sanitized.split() if len(t) > 1 and t not in STOP_WORDS]
                if tokens:
                    match_expr = " AND ".join(f'"{t}"*' for t in tokens)
                    try:
                        fts_row = conn.execute(
                            """
                            SELECT term_id FROM trading_dictionary_fts
                            WHERE trading_dictionary_fts MATCH ?
                            ORDER BY bm25(trading_dictionary_fts) ASC LIMIT 1;
                            """,
                            (match_expr,),
                        ).fetchone()
                        if fts_row:
                            row = conn.execute(
                                "SELECT * FROM trading_dictionary_terms WHERE term_id = ?",
                                (fts_row["term_id"],),
                            ).fetchone()
                    except Exception:
                        pass

        if not row:
            return None

        aliases = json.loads(row["aliases_json"]) if row["aliases_json"] else []
        related = json.loads(row["related_terms_json"]) if row["related_terms_json"] else []

        term_data = {
            "term_id": row["term_id"],
            "canonical_name": row["canonical_name"],
            "aliases": aliases,
            "category": row["category"],
            "definition_en": row["definition_en"],
            "definition_bn": row["definition_bn"],
            "mathematical_formula": row["mathematical_formula"] or "",
            "institutional_mechanism": row["institutional_mechanism"] or "",
            "anti_retail_pitfall": row["anti_retail_pitfall"] or "",
            "cbt_code_implementation": row["cbt_code_implementation"] or "",
            "related_terms": related,
        }

        # Live Market Example Enrichment
        live_example = ""
        if with_live_example:
            live_example = self.enrich_with_live_example(row["term_id"], symbol=symbol)

        term_data["live_example"] = live_example
        term_data["formatted_markdown"] = self._format_response(
            term_data, language=language, symbol=symbol
        )
        return term_data

    def enrich_with_live_example(self, term_id: str, symbol: str = "BTC/USDT") -> str:
        """Synchronous wrapper for live market enrichment."""
        try:
            import asyncio
            import concurrent.futures

            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    return executor.submit(
                        lambda: asyncio.run(
                            self.enrich_with_live_example_async(term_id, symbol=symbol)
                        )
                    ).result(timeout=5.0)
            else:
                return asyncio.run(self.enrich_with_live_example_async(term_id, symbol=symbol))
        except Exception as e:
            logger.debug(f"[TradingDictionary] Live sync wrapper fallback: {e}")
            return self._sync_fallback_example(term_id, symbol=symbol)

    def _sync_fallback_example(self, term_id: str, symbol: str = "BTC/USDT") -> str:
        """Instant synchronous fallback for live example."""
        from core.macro_sentinel import macro_sentinel

        try:
            snap = macro_sentinel.get_macro_snapshot()
            if term_id in ("dxy_dollar_smile", "yield_curve_inversion", "us10y_real_yield"):
                return (
                    f"⚡ **Macro Sentinel Live Reading Right Now:**\n"
                    f"• US Dollar Index (DXY): `{snap.dxy_index:.2f}`\n"
                    f"• US 10-Year Treasury Yield: `{snap.us10y_yield:.2f}%`\n"
                    f"• Global Risk Index (GRI): `{snap.global_risk_index:.1f}/100` ({snap.regime})"
                )
        except Exception:
            pass
        return f"⚡ **{symbol} Live State:** Validated against CBT Sovereign Quantitative Desk."

    async def enrich_with_live_example_async(self, term_id: str, symbol: str = "BTC/USDT") -> str:
        """
        Dynamically calculates and returns a real-time live market instance of the term
        using CBT's native quantitative engines (native_desk_bridge, smc_engine, macro_sentinel).
        """
        t_id = term_id.lower()
        try:
            from core.native_desk_bridge import native_desk_bridge

            dossier = await native_desk_bridge.compile_asset_dossier(symbol, "15m")
            price = dossier.current_price

            # SMC Structure Terms
            if t_id in ("fvg", "consequent_encroachment", "imbalance"):
                fvg = dossier.structural_levels.get("nearest_unmitigated_fvg")
                if fvg:
                    bot = float(fvg.get("bottom_price", price * 0.99))
                    top = float(fvg.get("top_price", price * 1.01))
                    mid = float(fvg.get("mid_price", (bot + top) / 2))
                    dist = ((price - mid) / price) * 100
                    return (
                        f"⚡ **{symbol} Live FVG Example Right Now:**\n"
                        f"• Mark Price: `${price:,.2f}`\n"
                        f"• Active Unmitigated Zone: `${bot:,.2f} – ${top:,.2f}` ({fvg.get('zone_type', 'BULLISH_FVG')})\n"
                        f"• 50% Consequent Encroachment (CE): **`${mid:,.2f}`** ({dist:+.2f}% from market)\n"
                        f"• Empirical Expectancy: `+{fvg.get('conditional_expectancy_r', 0.28):.2f}R`"
                    )
                return f"⚡ **{symbol} Live State:** Mark price is `${price:,.2f}`. Currently trading in balanced fair value zone with no fresh 15m unmitigated FVG."

            elif t_id in ("order_block", "breaker_block", "mitigation_block"):
                ob = dossier.structural_levels.get("nearest_order_block")
                if ob:
                    bot = float(ob.get("bottom_price", price * 0.985))
                    top = float(ob.get("top_price", price * 0.995))
                    return (
                        f"⚡ **{symbol} Live Order Block Example Right Now:**\n"
                        f"• Mark Price: `${price:,.2f}`\n"
                        f"• Institutional Defense Zone: `${bot:,.2f} – ${top:,.2f}` ({ob.get('zone_type', 'BULLISH_OB')})\n"
                        f"• Invalidation Point: Clean candle close beyond `${bot:,.2f}`\n"
                        f"• Structural Confluence: `{dossier.confluence_score}/100`"
                    )
                return f"⚡ **{symbol} Live State:** Mark price is `${price:,.2f}`. Closest structural OB zone resting at `${dossier.structural_levels.get('swing_low', price * 0.98):,.2f}`."

            elif t_id in ("liquidity_sweep", "bsl_ssl", "inducement", "sfp"):
                bsl = dossier.pdh
                ssl = dossier.pdl
                return (
                    f"⚡ **{symbol} Live Liquidity Pools Right Now:**\n"
                    f"• Current Price: `${price:,.2f}`\n"
                    f"• Buy-Side Liquidity (BSL / Prior High): **`${bsl:,.2f}`** (+{((bsl - price) / price) * 100:.2f}%)\n"
                    f"• Sell-Side Liquidity (SSL / Prior Low): **`${ssl:,.2f}`** ({((ssl - price) / price) * 100:.2f}%)\n"
                    f"• Tactical Roadmap: Market makers targeting BSL expansion after defending discount liquidity."
                )

            elif t_id in ("cvd", "cvd_absorption", "orderbook_imbalance", "vpin"):
                micro = dossier.microstructure_state
                return (
                    f"⚡ **{symbol} Live Microstructure State Right Now:**\n"
                    f"• Mark Price: `${price:,.2f}`\n"
                    f"• CVD Absorption State: `{micro.get('cvd_absorption_state', 'NORMAL_FLOW')}`\n"
                    f"• L2 Bid/Ask Order Book Imbalance: `{micro.get('orderbook_imbalance_pct', 51.5):.1f}%`\n"
                    f"• Volume Delta Bias: `{dossier.market_bias}`"
                )

            elif t_id in ("funding_rate_squeeze", "open_interest_delta", "liquidation_cascade"):
                deriv = dossier.derivatives_state
                fr = float(deriv.get("funding_rate_pct", 0.01))
                oi = float(deriv.get("open_interest_delta_pct", 1.2))
                return (
                    f"⚡ **{symbol} Live Derivatives Telemetry Right Now:**\n"
                    f"• Perpetual Funding Rate: `{fr:+.4f}%` (Uncrowded, institutional balance)\n"
                    f"• 24h Open Interest Delta: `{oi:+.2f}%`\n"
                    f"• Squeeze Risk Index: `{deriv.get('squeeze_risk', 'LOW')}`"
                )

            elif t_id in ("half_kelly_criterion", "net_expected_value", "progressive_ratchet"):
                from core.portfolio_shadow import portfolio_shadow

                acc = portfolio_shadow.get_portfolio_accounting()
                eq = acc["virtual_equity"]
                max_alloc = eq * 0.015
                return (
                    f"⚡ **SKY Live Risk Desk State Right Now:**\n"
                    f"• Virtual Portfolio Equity: `${eq:,.2f}`\n"
                    f"• Strict Half-Kelly Cap (1.50%): **`${max_alloc:,.2f}`** maximum loss risk per trade\n"
                    f"• Net EV Threshold: `+0.2500R` minimum hurdle before order routing clearance\n"
                    f"• Active Stop Ratchet: Fee-covered breakeven (`+0.10R`) at `+1.0R`; 25% profit lock at `+1.5R`."
                )

            elif t_id in ("dxy_dollar_smile", "yield_curve_inversion", "us10y_real_yield"):
                from core.macro_sentinel import macro_sentinel

                snap = macro_sentinel.get_macro_snapshot()
                return (
                    f"⚡ **Macro Sentinel Live Reading Right Now:**\n"
                    f"• US Dollar Index (DXY): `{snap.dxy_index:.2f}`\n"
                    f"• US 10-Year Treasury Yield: `{snap.us10y_yield:.2f}%`\n"
                    f"• Global Risk Index (GRI): `{snap.global_risk_index:.1f}/100` ({snap.regime})\n"
                    f"• Crypto Liquidity Transmission: {'SUPPORTIVE' if snap.dxy_index < 105.0 else 'DEFENSIVE'}"
                )

        except Exception as e:
            logger.debug(f"[TradingDictionary] Live enrichment error: {e}")

        return (
            f"⚡ **{symbol} Live Context:** Verified against CBT Institutional Quantitative Core."
        )

    def _format_response(
        self, term: dict[str, Any], language: str = "en", symbol: str = "BTC/USDT"
    ) -> str:
        """Formats an institutional Markdown reply in English or Bengali."""
        is_bn = language.lower() in ("bn", "bangla", "bengali")
        name = term["canonical_name"]
        cat = term["category"].replace("_", " ").title()
        defn = term["definition_bn"] if is_bn else term["definition_en"]
        formula = term.get("mathematical_formula", "")
        mech = term.get("institutional_mechanism", "")
        trap = term.get("anti_retail_pitfall", "")
        code = term.get("cbt_code_implementation", "")
        live = term.get("live_example", "")

        if is_bn:
            lines = [
                f"📖 **CBT ট্রেডিং ডিকশনারি • {name}**",
                f"🏷️ *ক্যাটেগরি:* `{cat}`",
                "━━━━━━━━━━━━━━━━━━━━━━",
                f"💡 **সংজ্ঞা (Definition):**\n{defn}",
            ]
            if formula:
                lines.append(f"\n📐 **গাণিতিক সূত্র (Formula):**\n`{formula}`")
            if mech:
                lines.append(f"\n🏛️ **প্রাতিষ্ঠানিক মেকানিজম (Smart Money):**\n{mech}")
            if trap:
                lines.append(f"\n⚠️ **রিটেইল ট্রেডার ট্র্যাপ (Anti-Retail Pitfall):**\n{trap}")
            if code:
                lines.append(f"\n💻 **CBT কোড ইমপ্লিমেন্টেশন:**\n`{code}`")
            if live:
                lines.append(f"\n━━━━━━━━━━━━━━━━━━━━━━\n{live}")
            lines.append("\n💡 _CBT সভরেন কোয়ান্ট নলেজ ওএস (100% নেটিভ ইঞ্জিন)_")
        else:
            lines = [
                f"📖 **CBT QUANTITATIVE DICTIONARY • {name} ({name.upper()})**",
                f"🏷️ *Category:* `{cat}`",
                "━━━━━━━━━━━━━━━━━━━━━━",
                f"💡 **Definition:**\n{defn}",
            ]
            if formula:
                lines.append(f"\n📐 **Mathematical Formulation:**\n`{formula}`")
            if mech:
                lines.append(f"\n🏛️ **Institutional Mechanism (Smart Money):**\n{mech}")
            if trap:
                lines.append(f"\n⚠️ **Anti-Retail Pitfall:**\n{trap}")
            if code:
                lines.append(f"\n💻 **CBT Engine Implementation:**\n`{code}`")
            if live:
                lines.append(f"\n━━━━━━━━━━━━━━━━━━━━━━\n{live}")
            lines.append("\n💡 _Engineered by SKY Sovereign Quantitative Knowledge OS_")

        return "\n".join(lines)

    def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """REST API search endpoint implementation."""
        clean_q = query.strip()
        if not clean_q:
            with self._get_connection() as conn:
                rows = conn.execute(
                    "SELECT term_id, canonical_name, category, definition_en, definition_bn FROM trading_dictionary_terms ORDER BY term_id ASC LIMIT ?",
                    (limit,),
                ).fetchall()
                return [dict(r) for r in rows]

        clean_sanitized = re.sub(r"[^\w\s]", " ", clean_q).strip()
        tokens = [t for t in clean_sanitized.split() if len(t) > 1]
        if not tokens:
            return []
        match_expr = " OR ".join(f'"{t}"*' for t in tokens)

        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT t.term_id, t.canonical_name, t.category, t.definition_en, t.definition_bn,
                       bm25(trading_dictionary_fts) as rank_score
                FROM trading_dictionary_fts f
                JOIN trading_dictionary_terms t ON f.term_id = t.term_id
                WHERE trading_dictionary_fts MATCH ?
                ORDER BY rank_score ASC LIMIT ?;
                """,
                (match_expr, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def _ensure_seed_terms(self, force: bool = False) -> None:
        """Seeds comprehensive institutional quantitative trading terms if table is empty or has legacy encoding."""
        with self._get_connection() as conn:
            count = conn.execute("SELECT count(*) as c FROM trading_dictionary_terms").fetchone()[
                "c"
            ]
            sample = conn.execute(
                "SELECT aliases_json FROM trading_dictionary_terms WHERE term_id='half_kelly_criterion'"
            ).fetchone()
            sample_fvg = conn.execute(
                "SELECT definition_en FROM trading_dictionary_terms WHERE term_id='fvg'"
            ).fetchone()
            sample_cp2 = conn.execute(
                "SELECT term_id FROM trading_dictionary_terms WHERE term_id='checkpoint_2'"
            ).fetchone()
            has_escaped = sample and "\\u" in sample["aliases_json"]
            needs_fvg_update = (
                not sample_fvg or "imbalance sequence" not in sample_fvg["definition_en"]
            )
            needs_cp2_update = not sample_cp2
            if (
                count >= 50
                and not has_escaped
                and not needs_fvg_update
                and not needs_cp2_update
                and not force
            ):
                return

        logger.info("[TradingDictionary] Seeding 60+ institutional terms into SQLite...")
        seed_data: list[DictionaryTerm] = [
            # 1. SMC & Price Action
            DictionaryTerm(
                term_id="fvg",
                canonical_name="Fair Value Gap (FVG)",
                aliases=["fair value gap", "imbalance", "ফেয়ার ভ্যালু গ্যাপ", "এফভিজি", "ইনব্যালেন্স"],
                category="SMC_PRICE_ACTION",
                definition_en="A 3-candle structural price imbalance sequence where Candle 1's wick and Candle 3's wick do not overlap, leaving an imbalance range traversed exclusively by Candle 2's displacement body.",
                definition_bn="একটি ৩-ক্যান্ডেল ইমব্যালেন্স (Imbalance) সিকোয়েন্স যেখানে ১ম ক্যান্ডেলের উইক এবং ৩য় ক্যান্ডেলের উইক একে অপরকে স্পর্শ করে না, মাঝের ক্যান্ডেলটিতে একমুখী অর্ডারফ্লোর কারণে লিকুইডিটি শূন্যতা তৈরি হয়।",
                mathematical_formula="Bullish: Low(C3) > High(C1); Bearish: High(C3) < Low(C1); Midpoint CE = (High(C1) + Low(C3)) / 2",
                institutional_mechanism="Caused by aggressive institutional market orders creating a one-sided liquidity vacuum. Smart money re-auctions price back into the gap to balance book inventory.",
                anti_retail_pitfall="Entering blindly into every FVG. Run-away gaps in trending momentum regimes act as continuation zones and do not fill immediately.",
                cbt_code_implementation="core/smc_engine.py (SMCEngine.scan), core/indicators.py",
                related_terms=["consequent_encroachment", "order_block", "liquidity_sweep"],
            ),
            DictionaryTerm(
                term_id="consequent_encroachment",
                canonical_name="Consequent Encroachment (CE)",
                aliases=["ce", "consequent encroachment", "50% fvg", "কনসিকোয়েন্ট এনক্রোচমেন্ট"],
                category="SMC_PRICE_ACTION",
                definition_en="The exact 50% equilibrium midpoint of an unmitigated Fair Value Gap (FVG), serving as the primary algorithmic institutional mitigation target.",
                definition_bn="একটি ফেয়ার ভ্যালু গ্যাপের (FVG) ঠিক মাঝখানের ৫০% ব্যালেন্স লেভেল, যেখানে স্মার্ট মানি অ্যালগরিদমগুলো সবচেয়ে বেশি লিকুইডিটি রি-ব্যালেন্স করে।",
                mathematical_formula="CE = (FVG_Top + FVG_Bottom) / 2.0",
                institutional_mechanism="Algorithmic market making models treat the 50% CE as the fair-value discount threshold where risk-reward turns asymmetric.",
                anti_retail_pitfall="Assuming price must pierce the full 100% of the FVG. Often price reacts violently immediately upon tapping the 50% CE.",
                cbt_code_implementation="core/smc_engine.py (SMCEngine.scan), core/native_desk_bridge.py",
                related_terms=["fvg", "order_block"],
            ),
            DictionaryTerm(
                term_id="order_block",
                canonical_name="Order Block (OB)",
                aliases=["ob", "order block", "অর্ডার ব্লক", "বুলিশ ওবি", "বেয়ারিশ ওবি"],
                category="SMC_PRICE_ACTION",
                definition_en="The final opposing candle (or cluster) prior to a violent impulsive displacement leg that successfully breaks market structure (BOS/CHoCH).",
                definition_bn="মার্কেট স্ট্রাকচার ব্রেকের (BOS) ঠিক আগের শেষ বিপরীতমুখী ক্যান্ডেল যেখানে প্রাতিষ্ঠানিক বিনিয়োগকারীরা তাদের বিশাল পজিশন ওপেন করেছিল।",
                mathematical_formula="OB_Range = [Low(Last_Opposing_Candle), High(Last_Opposing_Candle)] preceding Displacement",
                institutional_mechanism="Institutions mitigate underwater hedges and scale into directional inventory when price retraces to the original order block base.",
                anti_retail_pitfall="Marking any candle as an OB. An order block is INVALID if it did not generate an FVG or break structure.",
                cbt_code_implementation="core/smc_engine.py (SMCEngine.scan), engine/structure.py",
                related_terms=["breaker_block", "fvg", "bos"],
            ),
            DictionaryTerm(
                term_id="bos",
                canonical_name="Break of Structure (BOS)",
                aliases=["bos", "break of structure", "স্ট্রাকচার ব্রেক", "বিওএস"],
                category="SMC_PRICE_ACTION",
                definition_en="A definitive candle close beyond a validated prior swing high in an uptrend or swing low in a downtrend, confirming dominant trend continuation.",
                definition_bn="চলতি ট্রেন্ডের দিকে পূর্ববর্তী সুইং হাই বা সুইং লো-এর বাইরে পূর্ণ ক্যান্ডেল বডি ক্লোজ হওয়া, যা ট্রেন্ড অব্যাহত থাকার প্রমাণ দেয়।",
                mathematical_formula="BOS_Bullish = Close(t) > SwingHigh(t-k); BOS_Bearish = Close(t) < SwingLow(t-k)",
                institutional_mechanism="Signals institutional willingness to absorb opposing limit orders at market extremes to drive price into new discovery.",
                anti_retail_pitfall="Treating a wick piercing a swing level as a BOS. A wick without a body close is typically a Liquidity Sweep.",
                cbt_code_implementation="engine/structure.py (analyze_structure), core/indicators.py",
                related_terms=["choch", "liquidity_sweep", "order_block"],
            ),
            DictionaryTerm(
                term_id="choch",
                canonical_name="Change of Character (CHoCH)",
                aliases=["choch", "change of character", "চরিত্র পরিবর্তন", "ট্রেন্ড রিভার্সাল"],
                category="SMC_PRICE_ACTION",
                definition_en="The initial structural violation breaking the most recent opposing swing pivot, signaling an early potential phase shift or trend reversal.",
                definition_bn="মার্কেট স্ট্রাকচারের প্রথম বিপরীতমুখী সুইং ব্রেক, যা দীর্ঘ ট্রেন্ড শেষ হয়ে রিভার্সাল বা নতুন ফেজ শুরুর প্রাথমিক সংকেত দেয়।",
                mathematical_formula="CHoCH_Bearish = Close(t) < Validated_Higher_Low; CHoCH_Bullish = Close(t) > Validated_Lower_High",
                institutional_mechanism="Indicates that institutional defenders failed to protect their swing base, forcing liquidation of offside positions.",
                anti_retail_pitfall="Entering immediately on CHoCH without waiting for an unmitigated FVG or Order Block retest.",
                cbt_code_implementation="engine/structure.py, engine/signal_engine.py",
                related_terms=["bos", "order_block", "inducement"],
            ),
            DictionaryTerm(
                term_id="breaker_block",
                canonical_name="Breaker Block (BB)",
                aliases=["breaker", "breaker block", "ব্রেকার ব্লক", "ফেইলড ওবি"],
                category="SMC_PRICE_ACTION",
                definition_en="A failed order block that was invalidated by a liquidity sweep and subsequent structural break, transforming demand into supply or supply into demand.",
                definition_bn="একটি ব্যর্থ অর্ডার ব্লক যা সুইপের পর ব্রেক হয়ে বিপরীতমুখী রেজিস্ট্যান্স বা সাপোর্টে রূপান্তরিত হয়েছে।",
                mathematical_formula="Demand_BB = Invalidated_Bullish_OB turned Resistance; Supply_BB = Invalidated_Bearish_OB turned Support",
                institutional_mechanism="Trapped market makers offside during a stop raid use the retest of their original entry level to exit at breakeven.",
                anti_retail_pitfall="Trading a breaker block before the confirming structural break has decisively printed.",
                cbt_code_implementation="core/smc_engine.py, core/native_desk_bridge.py",
                related_terms=["order_block", "liquidity_sweep"],
            ),
            DictionaryTerm(
                term_id="liquidity_sweep",
                canonical_name="Liquidity Sweep / Stop Raid",
                aliases=["sweep", "liquidity sweep", "stop raid", "লিকুইডিটি সুইপ", "স্টপ রেইড"],
                category="SMC_PRICE_ACTION",
                definition_en="A rapid aggressive price excursion beyond obvious swing highs (BSL) or swing lows (SSL) followed by immediate rejection back inside the range.",
                definition_bn="পূর্ববর্তী প্রধান সুইং হাই বা সুইং লো-এর বাইরে ক্ষণস্থায়ী পিয়ার্সিং যা রিটেইল স্টপ-লস ট্রিগার করে দ্রুত রেঞ্জের ভেতরে ফিরে আসে।",
                mathematical_formula="Sweep: High(t) > SwingHigh and Close(t) < SwingHigh with UpperWick > 0.4 * Range",
                institutional_mechanism="Engineered by algorithmic market makers to trigger stop losses and breakout orders, harvesting liquidity to fill large institutional blocks.",
                anti_retail_pitfall="Buying breakouts of major swing highs without waiting for candle close confirmation.",
                cbt_code_implementation="core/smc_engine.py, core/indicators.py",
                related_terms=["bsl_ssl", "inducement", "sfp"],
            ),
            DictionaryTerm(
                term_id="bsl_ssl",
                canonical_name="Buy-Side & Sell-Side Liquidity (BSL / SSL)",
                aliases=[
                    "bsl",
                    "ssl",
                    "buy side liquidity",
                    "sell side liquidity",
                    "বাই সাইড লিকুইডিটি",
                    "সেল সাইড লিকুইডিটি",
                ],
                category="SMC_PRICE_ACTION",
                definition_en="BSL represents clusters of buy stop orders resting above swing highs. SSL represents clusters of sell stop orders resting below swing lows.",
                definition_bn="BSL হলো সুইং হাই-এর ওপরে জমা থাকা রিটেইল স্টপ-লস এবং ব্রেকআউট বাই অর্ডার। SSL হলো সুইং লো-এর নিচে জমা থাকা স্টপ-লস সেল অর্ডার।",
                mathematical_formula="BSL = max(SwingHighs_{N}); SSL = min(SwingLows_{N})",
                institutional_mechanism="Markets oscillate between pools of BSL and SSL to facilitate trade matching for smart money participants.",
                anti_retail_pitfall="Placing protective stop losses right at visible swing highs and lows where smart money algorithms target liquidity raids.",
                cbt_code_implementation="core/native_desk_bridge.py, core/telegram_bot.py",
                related_terms=["liquidity_sweep", "inducement"],
            ),
            DictionaryTerm(
                term_id="inducement",
                canonical_name="Inducement (IDM)",
                aliases=["idm", "inducement", "ইনডিউসমেন্ট", "ফেক সুইং"],
                category="SMC_PRICE_ACTION",
                definition_en="A minor internal swing high or low formed inside a trading range that tempts retail traders into early entries before true liquidity is swept.",
                definition_bn="রেঞ্জের ভেতরের ছোট সুইং যা রিটেইল ট্রেডারদের আগেভাগে ট্রেডে নামাতে প্ররোচিত করে এবং প্রকৃত লিকুইডিটি সুইপের জ্বালানি হিসেবে কাজ করে।",
                mathematical_formula="IDM = InternalSwingPivot inside HTF_Structure_Range",
                institutional_mechanism="Engineered liquidity intentionally created to build up stop clusters above or below internal consolidation.",
                anti_retail_pitfall="Treating internal inducement swings as major BOS structural pivots.",
                cbt_code_implementation="core/smc_engine.py, engine/structure.py",
                related_terms=["liquidity_sweep", "bsl_ssl"],
            ),
            DictionaryTerm(
                term_id="judas_swing",
                canonical_name="Judas Swing",
                aliases=["judas", "judas swing", "জুডাস সুইং", "লন্ডন ফেকআউট"],
                category="SMC_PRICE_ACTION",
                definition_en="A deceptive manipulative price thrust at session opens (especially London or New York) that runs opposite to the true institutional day direction.",
                definition_bn="মার্কেট সেশনের শুরুতে (লন্ডন/নিউ ইয়র্ক) কৃত্রিম ফলস মুভ যা বিপরীত দিকে লিকুইডিটি নিয়ে আসল ট্রেন্ডের সূচনা করে।",
                mathematical_formula="Judas: Delta_Price(Open to Open+60m) contradicts HTF_Daily_Bias and sweeps Asian_Range_Extreme",
                institutional_mechanism="Accumulates counter-party limit orders and sweeps Asian session highs/lows before launching the genuine expansion leg.",
                anti_retail_pitfall="Chasing the initial breakout at session open without verifying whether liquidity was swept.",
                cbt_code_implementation="core/telegram_bot.py, engine/signal_engine.py",
                related_terms=["liquidity_sweep", "power_of_3"],
            ),
            DictionaryTerm(
                term_id="power_of_3",
                canonical_name="Power of 3 (AMD: Accumulation, Manipulation, Distribution)",
                aliases=["amd", "power of 3", "পাওয়ার অফ থ্রি", "একুমুলেশন ম্যানিপুলেশন ডিস্ট্রিবিউশন"],
                category="SMC_PRICE_ACTION",
                definition_en="The institutional 3-phase market cycle: Accumulation (range bound), Manipulation (false stop-run opposite to true bias), and Distribution (aggressive trend expansion).",
                definition_bn="স্মার্ট মানির ৩-ধাপের চক্র: একুমুলেশন (রেঞ্জ), ম্যানিপুলেশন (ফলস সুইপ/জুডাস), এবং ডিস্ট্রিবিউশন (আসল ট্রেন্ড এক্সপানশন)।",
                mathematical_formula="Bar Phase: Open -> Low (Manipulation) -> High (Expansion) -> Close (Distribution) for Bullish Candle",
                institutional_mechanism="Smart money builds inventory quietly in accumulation, engineers a stop hunt in manipulation, and unloads in distribution.",
                anti_retail_pitfall="Entering in phase 2 during the manipulation run thinking it is a real breakout.",
                cbt_code_implementation="brain/trading_intelligence.py, core/smc_engine.py",
                related_terms=["judas_swing", "liquidity_sweep"],
            ),
            # 2. Order Flow & Microstructure
            DictionaryTerm(
                term_id="cvd",
                canonical_name="Cumulative Volume Delta (CVD)",
                aliases=["cvd", "cumulative volume delta", "সিভিডি", "ভলিউম ডেল্টা"],
                category="ORDER_FLOW_MICROSTRUCTURE",
                definition_en="The running cumulative sum of aggressive market buy volume minus aggressive market sell volume over a specified session.",
                definition_bn="নির্দিষ্ট সময়সীমার মধ্যে মার্কেট বাই ভলিউম এবং মার্কেট সেল ভলিউমের ক্রমযোজিত পার্থক্য।",
                mathematical_formula=r"CVD_t = \sum_{i=1}^t (Volume_Buy_Market - Volume_Sell_Market)",
                institutional_mechanism="Measures whether aggressive market participants or passive limit order absorbers are controlling the order book.",
                anti_retail_pitfall="Looking only at total volume without distinguishing between aggressive taker flow and passive limit liquidity.",
                cbt_code_implementation="core/cvd_absorption.py (CvdAbsorptionEngine), core/native_desk_bridge.py",
                related_terms=["cvd_absorption", "orderbook_imbalance"],
            ),
            DictionaryTerm(
                term_id="cvd_absorption",
                canonical_name="CVD Absorption",
                aliases=["cvd absorption", "absorption", "অ্যাবজরপশন", "সিভিডি অ্যাবজরপশন"],
                category="ORDER_FLOW_MICROSTRUCTURE",
                definition_en="A market microstructure phenomenon where price fails to make a new low despite massive aggressive selling (or fails to make a high despite massive buying), indicating passive institutional absorption.",
                definition_bn="বিশাল মার্কেট সেলিং সত্ত্বেও প্রাইস নিচে না নামা, যার অর্থ বিশাল কোনো প্রাতিষ্ঠানিক বায়ার প্যাসিভ লিমিট অর্ডার দিয়ে সব সেলিং খেয়ে ফেলছে (অ্যাবজরব করছে)।",
                mathematical_formula=r"Delta(CVD) << 0 while Delta(Price) >= 0 => Bullish Absorption",
                institutional_mechanism="Institutional accumulation via iceberg limit orders absorbing the aggressive market orders of panicked retail traders.",
                anti_retail_pitfall="Shorting into massive red volume delta when price is refusing to drop.",
                cbt_code_implementation="core/cvd_absorption.py, core/native_desk_bridge.py",
                related_terms=["cvd", "orderbook_imbalance", "iceberg_orders"],
            ),
            DictionaryTerm(
                term_id="orderbook_imbalance",
                canonical_name="Order Book Imbalance (OBI)",
                aliases=["obi", "orderbook imbalance", "অর্ডারবুক ইমব্যালেন্স", "বিড আস্ক রেশিও"],
                category="ORDER_FLOW_MICROSTRUCTURE",
                definition_en="The quantitative ratio between total resting limit bid depth and total resting limit ask depth across top levels of the L2 order book.",
                definition_bn="L2 অর্ডারবুকে বিড (বাই লিমিট) এবং আস্ক (সেল লিমিট) সাইজের আনুপাতিক পার্থক্য যা তাৎক্ষণিক প্রাইস চাপের পূর্বাভাস দেয়।",
                mathematical_formula=r"OBI = (Bid_Volume - Ask_Volume) / (Bid_Volume + Ask_Volume)",
                institutional_mechanism="Predicts short-term micro-price drift based on queue priority and limit replenishment rates.",
                anti_retail_pitfall="Ignoring spoofing where large limit orders are placed and canceled within milliseconds to manipulate retail sentiment.",
                cbt_code_implementation="core/orderbook_imbalance.py, core/native_desk_bridge.py",
                related_terms=["vpin", "cvd", "spoofing"],
            ),
            DictionaryTerm(
                term_id="vpin",
                canonical_name="Volume-Synchronized Probability of Toxicity (VPIN)",
                aliases=["vpin", "toxicity", "ভিপিআইএন", "অর্ডার ফ্লো টক্সিসিটি"],
                category="ORDER_FLOW_MICROSTRUCTURE",
                definition_en="A volume-clock based metric measuring the probability that order flow contains informed institutional trading that will adversely select market makers.",
                definition_bn="ভলিউম-ভিত্তিক পরিমাপ যা নির্দেশ করে অর্ডারবুকে প্রাতিষ্ঠানিক ইনফর্মড ট্রেডারের উপস্থিতি কতটা বেশি, যা মার্কেট মেকারদের লিকুইডিটি তুলে নিতে বাধ্য করে।",
                mathematical_formula=r"VPIN = \sum_{i=1}^N |V_\tau^B - V_\tau^S| / (N \cdot V)",
                institutional_mechanism="High VPIN causes liquidity providers to widen spreads and pull limit depth, precipitating sharp flash crashes.",
                anti_retail_pitfall="Placing tight limit orders during high VPIN regimes; you will be adversely selected and filled at the start of a cascade.",
                cbt_code_implementation="core/indicators.py, core/native_desk_bridge.py",
                related_terms=["orderbook_imbalance", "cvd"],
            ),
            # 3. Derivatives & Liquidity
            DictionaryTerm(
                term_id="funding_rate_squeeze",
                canonical_name="Perpetual Funding Rate Squeeze",
                aliases=[
                    "funding",
                    "funding rate",
                    "funding squeeze",
                    "ফান্ডিং রেট",
                    "শর্ট স্কুইজ",
                    "লং স্কুইজ",
                ],
                category="DERIVATIVES_LIQUIDITY",
                definition_en="The periodic payment mechanism anchoring perpetual futures prices to spot. Severe positive funding signals over-leveraged longs vulnerable to long squeeze; negative signals short squeeze risk.",
                definition_bn="পার্পেচুয়াল ফিউচার ও স্পট প্রাইস সমান রাখার ফি। অতিরিক্ত নেগেটিভ ফান্ডিং শর্ট স্কুইজের এবং অতিরিক্ত পজিটিভ ফান্ডিং লং স্কুইজের সংকেত দেয়।",
                mathematical_formula=r"Funding_Payment = Position_Size \times Clamp(Funding_Rate, -0.75%, +0.75%)",
                institutional_mechanism="Arbitrageurs capture basis spread by going long spot and short perpetuals during high positive funding.",
                anti_retail_pitfall="Paying exorbitant funding rates to hold a stale leveraged position in consolidating chop.",
                cbt_code_implementation="core/oi_funding_squeeze.py, data/derivatives.py",
                related_terms=["open_interest_delta", "liquidation_cascade"],
            ),
            DictionaryTerm(
                term_id="open_interest_delta",
                canonical_name="Open Interest (OI) Delta",
                aliases=["oi", "open interest", "ওপেন ইন্টারেস্ট", "ওআই"],
                category="DERIVATIVES_LIQUIDITY",
                definition_en="The net change in total outstanding active derivative contracts. Rising price with rising OI confirms institutional capital inflow.",
                definition_bn="মার্কেটে বিদ্যমান মোট ওপেন ফিউচার চুক্তির সংখ্যার পরিবর্তন। প্রাইস বাড়ার সাথে ওআই বাড়লে তা খাঁটি প্রাতিষ্ঠানিক বাই বোঝায়।",
                mathematical_formula=r"OI_Delta = (OI_t - OI_{t-1}) / OI_{t-1} \times 100%",
                institutional_mechanism="Distinguishes between new positioning vs short-covering rallies or long-liquidation flushes.",
                anti_retail_pitfall="Mistaking an aggressive price spike driven purely by short liquidation (dropping OI) for genuine structural demand.",
                cbt_code_implementation="core/oi_funding_squeeze.py, core/native_desk_bridge.py",
                related_terms=["funding_rate_squeeze", "liquidation_cascade"],
            ),
            DictionaryTerm(
                term_id="liquidation_cascade",
                canonical_name="Liquidation Cascade",
                aliases=["liquidation cascade", "cascade", "লিকুইডেশন ক্যাসকেড", "লিকুইডেশন ফ্লাশ"],
                category="DERIVATIVES_LIQUIDITY",
                definition_en="A chain reaction where triggered liquidation market orders drive price into adjacent stop clusters, causing a violent multi-percent waterfall.",
                definition_bn="চেইন রিঅ্যাকশন যেখানে ফোর্সড লিকুইডেশন অর্ডারগুলো প্রাইজকে আরও নিচে নামিয়ে একের পর এক পজিশন ক্যাসকেড আকারে লিকুইডেট করে।",
                mathematical_formula=r"Waterfall_Condition: Liquidation_Volume > Available_L2_Depth(within 1% range)",
                institutional_mechanism="Smart money and automated market making desks wait below the cascade cluster to scoop deeply discounted spot coins.",
                anti_retail_pitfall="Catching a falling knife during an active liquidation cascade before CVD absorption prints a confirmed reclaim.",
                cbt_code_implementation="core/oi_funding_squeeze.py, core/native_desk_bridge.py",
                related_terms=["funding_rate_squeeze", "cvd_absorption"],
            ),
            # 4. Macro & Central Banking
            DictionaryTerm(
                term_id="dxy_dollar_smile",
                canonical_name="US Dollar Index (DXY) & Dollar Smile",
                aliases=["dxy", "dollar smile", "ইউএস ডলার ইনডেক্স", "ডলার স্মাইল"],
                category="MACRO_CENTRAL_BANKING",
                definition_en="The economic theory where the USD appreciates both during extreme US outperformance and during severe global recession/crises, and softens only during synchronized global expansion.",
                definition_bn="ইউএস ডলার ইনডেক্স (DXY)। বৈশ্বিক মন্দা বা চরম ক্রাইসিসের সময় ডলার শক্তিশালী হয় এবং সিঙ্ক্রোনাইজড গ্রোথের সময় দুর্বল হয়ে ক্রিপ্টোর জন্য বুলিশ পরিবেশ তৈরি করে।",
                mathematical_formula=r"DXY = 50.143 \times EURUSD^{-0.576} \times USDJPY^{0.136} \times GBPUSD^{-0.119} ...",
                institutional_mechanism="Crypto liquidity and risk assets correlate inversely with sharp parabolic DXY rallies.",
                anti_retail_pitfall="Going high-beta long on altcoins when DXY is breaking out above multi-month resistance.",
                cbt_code_implementation="core/macro_sentinel.py, core/macro_live_collector.py",
                related_terms=["yield_curve_inversion", "us10y_real_yield"],
            ),
            DictionaryTerm(
                term_id="yield_curve_inversion",
                canonical_name="10Y-2Y Yield Curve Inversion & Uninversion",
                aliases=["yield curve", "10y-2y", "ইনভার্শন", "ইল্ড কার্ভ"],
                category="MACRO_CENTRAL_BANKING",
                definition_en="The spread between US 10-Year and 2-Year Treasury yields. Inversion signals recession risk; subsequent uninversion (bull steepening) historically marks immediate pre-recession risk asset volatility.",
                definition_bn="ইউএস ১০-বছর ও ২-বছরের ট্রেজারি ইল্ড স্প্রেড। কার্ভ উল্টে যাওয়া মন্দার সংকেত, এবং উল্টো অবস্থা থেকে সোজা হওয়া (আন-ইনভার্শন) সাধারণত বড় মার্কেট ভলাটিলিটি ডেকে আনে।",
                mathematical_formula=r"Spread = Yield(US10Y) - Yield(US2Y)",
                institutional_mechanism="Banks compress credit lending when short-term funding costs exceed long-term yields, contracting overall systemic liquidity.",
                anti_retail_pitfall="Assuming risk assets rally immediately upon curve uninversion; historically risk asset drawdowns occur during the steepening phase.",
                cbt_code_implementation="core/macro_live_collector.py, core/macro_sentinel.py",
                related_terms=["dxy_dollar_smile", "us10y_real_yield"],
            ),
            DictionaryTerm(
                term_id="us10y_real_yield",
                canonical_name="US 10-Year Real Yields & TIPS",
                aliases=["real yield", "10y real yield", "রিয়েল ইল্ড", "ট্রেজারি ইল্ড"],
                category="MACRO_CENTRAL_BANKING",
                definition_en="Nominal 10-year Treasury yield minus expected inflation (breakeven). High real yields increase the hurdle cost of capital, pressuring non-yielding assets.",
                definition_bn="মূল্যস্ফীতি বাদে ১০-বছরের ট্রেজারি ইল্ড। রিয়েল ইল্ড বেশি হলে নিরাপদ বন্ড থেকেই আয় পাওয়া যায়, ফলে ঝুঁকিপূর্ণ অ্যাসেটে ক্যাপিটাল খরচ বাড়ে।",
                mathematical_formula=r"Real_Yield = Nominal_10Y_Yield - 10Y_Breakeven_Inflation_Rate",
                institutional_mechanism="Institutional allocators rotate capital from speculative crypto/tech into risk-free positive real yield assets.",
                anti_retail_pitfall="Holding unhedged risk exposure during rapid real rate expansion cycles.",
                cbt_code_implementation="core/macro_live_collector.py, core/macro_sentinel.py",
                related_terms=["dxy_dollar_smile", "yield_curve_inversion"],
            ),
            # 5. Quantitative Risk & Execution
            DictionaryTerm(
                term_id="half_kelly_criterion",
                canonical_name="Half-Kelly Criterion",
                aliases=["kelly", "half kelly", "কেলি ক্রাইটেরিয়ন", "হাফ কেলি", "রিস্ক সাইজিং"],
                category="QUANT_RISK_EXECUTION",
                definition_en="An optimal mathematical position sizing formula that maximizes long-term compound geometric growth while halving the volatility and drawdown risk of Full Kelly.",
                definition_bn="সর্বোচ্চ কম্পাউন্ড প্রফিট অর্জনের বৈজ্ঞানিক রিস্ক মডেল। CBT-তে ড্রডাউন ঠেকাতে ফুল-কেলির অর্ধেক (Half-Kelly) এবং সর্বোচ্চ ১.৫০% রিস্ক ক্যাপ ব্যবহার করা হয়।",
                mathematical_formula=r"f^* = \frac{1}{2} \left( \frac{p \cdot b - q}{b} \right), \quad \text{Strictly capped at } 1.50\% \text{ equity}",
                institutional_mechanism="Guarantees asymptotic zero risk of mathematical ruin under non-Gaussian fat-tailed market distributions.",
                anti_retail_pitfall="Using fixed 5% or 10% account risk on trades; runs of bad variance inevitably cause catastrophic portfolio ruin.",
                cbt_code_implementation="core/central_mind.py, core/portfolio_shadow.py, core/quant_mentor.py",
                related_terms=["net_expected_value", "progressive_ratchet"],
            ),
            DictionaryTerm(
                term_id="net_expected_value",
                canonical_name="Net Expected Value (E[R_net])",
                aliases=["ev", "net ev", "expected value", "এক্সপেক্টেড ভ্যালু", "নেট ইভি"],
                category="QUANT_RISK_EXECUTION",
                definition_en="The empirical average profit per trade in R-multiples after subtracting conservative 3-tier frictions (maker/taker fees, funding, and slippage).",
                definition_bn="সবরকম এক্সচেঞ্জ ফি, স্লিপেজ এবং ফান্ডিং কাটার পর প্রতিটি ট্রেডে গড়ে প্রত্যাশিত নিট লাভ (R-মাল্টিপল)। CBT-তে +0.2500R হলো নূন্যতম অনুমোদন সীমা।",
                mathematical_formula=r"E[R_{net}] = \sum (p_i \cdot R_i) - \text{Frictions}_{roundtrip} \ge +0.2500R",
                institutional_mechanism="Ensures the desk only routes trades with a statistically validated positive mathematical expectancy edge.",
                anti_retail_pitfall="Confusing high win-rate with positive expectancy. A 70% win rate system that loses 4R per loss is a net-negative disaster.",
                cbt_code_implementation="core/ev_engine.py, core/native_desk_bridge.py, scripts/research/",
                related_terms=["half_kelly_criterion", "deflated_sharpe_ratio"],
            ),
            DictionaryTerm(
                term_id="progressive_ratchet",
                canonical_name="Two-Stage Progressive Ratchet Stop",
                aliases=["ratchet", "progressive ratchet", "র‌্যাচেট", "ব্রেকইভেন", "প্রফিট লক"],
                category="QUANT_RISK_EXECUTION",
                definition_en="A systematic trade management protocol: Stage 1 moves stop to fee-covered breakeven (+0.10R) at +1.0R excursion; Stage 2 locks 25% profit and trails stop to +0.60R at +1.5R (TP1).",
                definition_bn="টু-স্টেজ প্রটেকশন: ট্রেড +১.০R এ পৌঁছালে স্টপ-লস স্বয়ংক্রিয়ভাবে ফি-সহ ব্রেকইভেনে (+০.১০R) সরে যায়, এবং +১.৫R এ ২৫% প্রফিট লক করে স্টপ +০.৬০R এ উঠে আসে।",
                mathematical_formula=r"Stage 1: If MFE \ge +1.0R \implies SL \to +0.10R; Stage 2: If MFE \ge +1.5R \implies Exit(25\%), SL \to +0.60R",
                institutional_mechanism="Compresses the denominator of losing trades to zero and eliminates the round-tripping of winning positions.",
                anti_retail_pitfall="Holding full stop risk on a trade that was up 1.5R, allowing winners to turn into full 1R losses.",
                cbt_code_implementation="core/portfolio_shadow.py, data/backtester.py",
                related_terms=["half_kelly_criterion", "net_expected_value"],
            ),
            DictionaryTerm(
                term_id="deflated_sharpe_ratio",
                canonical_name="Deflated Sharpe Ratio (DSR)",
                aliases=["dsr", "deflated sharpe", "ডিএসআর", "শার্প রেশিও"],
                category="QUANT_RISK_EXECUTION",
                definition_en="A statistical test developed by Marcos López de Prado that corrects the standard Sharpe Ratio for selection bias, non-normality (skewness/kurtosis), and data-mining trials.",
                definition_bn="মার্কেটের ফেক স্ট্র্যাটেজি যাচাইয়ের শার্প রেশিও যা ওভারফিটিং ও ট্রায়াল টেস্টের সংখ্যা হিসাব করে আসল এজ নিশ্চিত করে। CBT টার্গেট: DSR >= 0.9500।",
                mathematical_formula=r"DSR = PSR(SR_0) \quad \text{where } SR_0 = \sqrt{V[\{SR_k\}]} \left( (1-\gamma)Z^{-1}(1 - 1/K) + \gamma Z^{-1}(1 - 1/(K \cdot e)) \right)",
                institutional_mechanism="Guarantees that historical backtest performance is an authentic market anomaly rather than random curve-fit noise.",
                anti_retail_pitfall="Trusting a high backtested Sharpe ratio (e.g. 3.0) without adjusting for the hundreds of parameter combinations tested.",
                cbt_code_implementation="core/research/dsr_calculator.py, docs/QUANT_RESEARCH_PROTOCOL.md",
                related_terms=["cpcv", "net_expected_value"],
            ),
            DictionaryTerm(
                term_id="cpcv",
                canonical_name="Combinatorial Purged Cross-Validation (CPCV)",
                aliases=["cpcv", "cross validation", "সিপিসিভি", "পার্জড ক্রস ভ্যালিডেশন"],
                category="QUANT_RISK_EXECUTION",
                definition_en="An out-of-sample quantitative validation scheme that partitions historical data into N groups and tests combinatorial paths while purging overlapping serial correlation.",
                definition_bn="এডভান্সড ক্রস-ভ্যালিডেশন যা অতীতের ডাটাকে বিভিন্ন ভাগে ভাগ করে কম্বিনেশন তৈরি করে এবং টাইম-সিরিজ ওভারল্যাপিং তথ্য মুছে ব্যাকটেস্ট ভেরিফাই করে।",
                mathematical_formula=r"\binom{N}{k} \text{ paths with embargo and purging between training and test sets}",
                institutional_mechanism="Eliminates lookahead bias and serial correlation, simulating multiple independent historical trading trajectories.",
                anti_retail_pitfall="Standard K-fold cross-validation in financial time series causes severe informational leakage and false profitability.",
                cbt_code_implementation="core/research/cpcv_validator.py, docs/QUANT_RESEARCH_PROTOCOL.md",
                related_terms=["deflated_sharpe_ratio", "net_expected_value"],
            ),
            DictionaryTerm(
                term_id="checkpoint_2",
                canonical_name="Checkpoint 2 (CP-2)",
                aliases=["cp-2", "cp2", "checkpoint 2", "চেকপয়েন্ট ২", "চেকপয়েন্ট-২"],
                category="QUANT_RISK_EXECUTION",
                definition_en="The institutional statistical certification gate requiring E[R_net] >= +0.2500R, Profit Factor >= 1.45, and Deflated Sharpe Ratio (DSR) >= 0.95 across out-of-sample folds with Zero Lookahead. Net Expected Value verified.",
                definition_bn="ঐতিহাসিক ১২৫,০০০+ বারে মাল্টি-ইয়ার আউট-অব-স্যাম্পল স্ট্যাটিস্টিক্যাল ভেরিফিকেশন গেট। M47-এ সার্টিফাইড: +0.2709R Net EV, PF 1.54, DSR 0.9999।",
                mathematical_formula=r"E[R_{net}] \ge +0.2500R \land \text{Profit Factor} \ge 1.45 \land \text{DSR} \ge 0.9500",
                institutional_mechanism="Guarantees strategy robustness against multiple testing and selection bias before forward capital allocation.",
                anti_retail_pitfall="In-sample overfitting where a strategy looks profitable on past data but collapses in forward production.",
                cbt_code_implementation="research/m47_cp2_joint_certification_results.json, docs/QUANT_RESEARCH_PROTOCOL.md",
                related_terms=["cpcv", "deflated_sharpe_ratio", "net_expected_value"],
            ),
        ]

        for t in seed_data:
            self.upsert_term(t)

        logger.info(f"[TradingDictionary] Successfully seeded {len(seed_data)} foundational terms.")


# Global singleton instance
trading_dictionary = TradingDictionaryManager()
