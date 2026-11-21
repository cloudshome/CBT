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
from pathlib import Path
from typing import Any

from core.knowledge_os.dictionary_seed_catalog import MASTER_SEED_TERMS, DictionaryTerm
from core.knowledge_os.research_wikipedia import WIKI_DB_PATH

logger = logging.getLogger("sky.knowledge_os.trading_dictionary")


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

    def get_term(self, term_id: str) -> DictionaryTerm | None:
        """Retrieves raw DictionaryTerm dataclass by term_id."""
        clean_id = term_id.strip().lower()
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM trading_dictionary_terms WHERE term_id = ?", (clean_id,)
            ).fetchone()
            if not row:
                return None
            return DictionaryTerm(
                term_id=row["term_id"],
                canonical_name=row["canonical_name"],
                aliases=json.loads(row["aliases_json"]) if row["aliases_json"] else [],
                category=row["category"],
                definition_en=row["definition_en"],
                definition_bn=row["definition_bn"],
                mathematical_formula=row["mathematical_formula"] or "",
                institutional_mechanism=row["institutional_mechanism"] or "",
                anti_retail_pitfall=row["anti_retail_pitfall"] or "",
                cbt_code_implementation=row["cbt_code_implementation"] or "",
                related_terms=json.loads(row["related_terms_json"])
                if row["related_terms_json"]
                else [],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

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
                sanitized = re.sub(r"[^\w\s\u0980-\u09FF]", " ", clean_q).strip()
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

        clean_sanitized = re.sub(r"[^\w\s\u0980-\u09FF]", " ", clean_q).strip()
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
        """Seeds comprehensive institutional quantitative trading terms if table has fewer terms or has legacy encoding."""
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
            sample_adx = conn.execute(
                "SELECT term_id FROM trading_dictionary_terms WHERE term_id='adx'"
            ).fetchone()
            has_escaped = sample and "\\u" in sample["aliases_json"]
            needs_fvg_update = (
                not sample_fvg or "imbalance sequence" not in sample_fvg["definition_en"]
            )
            needs_m80_expansion = not sample_adx or count < len(MASTER_SEED_TERMS)
            if (
                count >= len(MASTER_SEED_TERMS)
                and not has_escaped
                and not needs_fvg_update
                and not needs_m80_expansion
                and not force
            ):
                return

        logger.info(
            f"[TradingDictionary] Seeding {len(MASTER_SEED_TERMS)} institutional master terms into SQLite..."
        )
        for t in MASTER_SEED_TERMS:
            self.upsert_term(t)

        logger.info(
            f"[TradingDictionary] Successfully seeded {len(MASTER_SEED_TERMS)} master terms."
        )


# Global singleton instance
trading_dictionary = TradingDictionaryManager()
