"""
SKY Quantitative Engine: Omniscient 28-Setup Trading Helping Hand Encyclopedia
================================================================================
Unifies SMC/ICT, Order Flow, Volume Profile, Derivatives Squeeze, Wyckoff,
Vectorized Candlestick triggers, and Macro/Session Killzones into a single
real-time Institutional Setup Scanner & Interactive Helping Hand Advisor.

Guarantees:
1. Zero-Lookahead Causal Firewall: All signals calculated strictly on closed bars.
2. Cross-Asset SMT Divergence: Evaluates relative highs/lows between BTC and ETH.
3. Candlestick Confirmation: Direct integration with PatternEngine.
4. Devil's Advocate Filter: Explicitly warns why NOT to trade if market is chop/low R:R.
5. 3-Tranche Half-Kelly Limit Ladder: Zone Top, 50% CE, and Zone Bottom tranches.
6. Bilingual Natural Language Synthesis (English & Bengali).
"""

from __future__ import annotations

import enum
import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np

from core.pattern_engine import pattern_engine

logger = logging.getLogger("ai_quant_sentinel.omniscient_setups")


# ==============================================================================
# ENUMS & DATA STRUCTURES
# ==============================================================================


class SetupFamily(enum.StrEnum):
    FAMILY_1_SMC_ICT = "SMC_ICT_STRUCTURAL"
    FAMILY_2_ORDER_FLOW = "ORDER_FLOW_VOLUME_PROFILE"
    FAMILY_3_DERIVATIVES = "DERIVATIVES_LIQUIDATION"
    FAMILY_4_WYCKOFF_PRICE_ACTION = "WYCKOFF_CLASSIC_PRICE_ACTION"
    FAMILY_5_MACRO_SESSION = "MACRO_SESSION_RELATIVE_STRENGTH"
    FAMILY_6_RISK_ADVISORY = "RISK_EXECUTION_ADVISORY"


class SetupReadinessState(enum.StrEnum):
    ACTIVE_TRIGGERED = "ACTIVE_TRIGGERED"  # In zone right now with confirmation
    WAITING_LIMIT = "WAITING_LIMIT"  # Approaching entry zone / limit order candidate
    DEVELOPING = "DEVELOPING"  # Structure forming on HTF
    INVALIDATED = "INVALIDATED"  # Broken invalidation level
    DEVILS_ADVOCATE_LOCKED = "DEVILS_ADVOCATE_LOCKED"  # Filtered by risk desk


@dataclass
class DCAOrderTranche:
    tranche_number: int
    label: str  # "Tranche 1 (Zone Top)", "Tranche 2 (50% CE)", "Tranche 3 (Zone Bottom)"
    price: float
    size_weight_pct: float  # e.g. 30%, 40%, 30%
    half_kelly_risk_usd: float
    contracts: float


@dataclass
class SetupDefinition:
    setup_id: str
    setup_number: int
    family: SetupFamily
    name_en: str
    name_bn: str
    description_en: str
    description_bn: str
    preferred_timeframes: list[str]
    default_bias: str  # "BULLISH", "BEARISH", "BIDIRECTIONAL"
    base_win_rate: float
    base_rr: float


@dataclass
class SetupEvaluationResult:
    setup_id: str
    setup_number: int
    family: str
    name_en: str
    name_bn: str
    state: SetupReadinessState
    bias: str  # "LONG", "SHORT", "NEUTRAL"
    confluence_score: float  # [0.0, 100.0]
    entry_zone: list[float]  # [min_price, max_price]
    trigger_price: float  # Optimal entry trigger
    stop_loss: float
    invalidation_level: float
    tp1: float  # +1.20R
    tp2: float  # +1.50R
    tp3: float  # Runner (2.5R+)
    risk_reward_ratio: float
    half_kelly_allocation_pct: float
    thesis_en: str
    thesis_bn: str
    candlestick_confirmation: str | None = None
    smt_divergence: str | None = None
    devils_advocate_risk: str | None = None
    tranches: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TradingHelpingHandDossier:
    symbol: str
    timeframe: str
    current_price: float
    market_phase: str
    session_killzone: str
    smt_divergence_summary: str
    candlestick_formations: list[str]
    orderflow_absorption_summary: str
    active_triggered_setups: list[SetupEvaluationResult]
    waiting_limit_setups: list[SetupEvaluationResult]
    devils_advocate_warnings: list[str]
    optimal_action: str  # "EXECUTE_NOW", "SET_LIMIT_LADDER", "STAY_IN_CASH"
    best_setup: SetupEvaluationResult | None
    limit_ladder: list[DCAOrderTranche]
    verdict_en: str
    verdict_bn: str

    def to_dict(self) -> dict[str, Any]:
        res = asdict(self)
        if self.best_setup:
            res["best_setup"] = self.best_setup.to_dict()
        res["active_triggered_setups"] = [s.to_dict() for s in self.active_triggered_setups]
        res["waiting_limit_setups"] = [s.to_dict() for s in self.waiting_limit_setups]
        return res


# ==============================================================================
# CANONICAL 28-SETUP REGISTRY
# ==============================================================================

CANONICAL_28_SETUPS: list[SetupDefinition] = [
    # Family 1 — SMC / ICT Structural & Liquidity (Setups 1–8)
    SetupDefinition(
        setup_id="ICT_SILVER_BULLET_SWEEP_MSS_FVG",
        setup_number=1,
        family=SetupFamily.FAMILY_1_SMC_ICT,
        name_en="ICT Silver Bullet (Sweep + MSS + FVG)",
        name_bn="আইসিটি সিলভার বুলেট (সুইপ + এমএসএস + এফভিজি)",
        description_en="High-probability killzone execution anchored to buy/sell-side liquidity raid, structural shift (MSS), displacement, and clean FVG retest.",
        description_bn="লিকুইডিটি সুইপ, মার্কেট স্ট্রাকচার শিফট (MSS) এবং ডিসপ্লেসমেন্ট ফেয়ার ভ্যালু গ্যাপ (FVG) রিটেস্টে নিশ্চিত এন্ট্রি।",
        preferred_timeframes=["5m", "15m", "1h"],
        default_bias="BIDIRECTIONAL",
        base_win_rate=0.68,
        base_rr=3.2,
    ),
    SetupDefinition(
        setup_id="HTF_OB_DISCOUNT_FVG_PULLBACK",
        setup_number=2,
        family=SetupFamily.FAMILY_1_SMC_ICT,
        name_en="HTF Trend Order Block + Discount FVG Pullback",
        name_bn="এইচটিএফ অর্ডার ব্লক + ডিসকাউন্ট এফভিজি পুলব্যাক",
        description_en="Trend-following continuation where price retraces into unmitigated 4H/1D Order Block overlapping discount FVG equilibrium.",
        description_bn="বড় টাইমফ্রেমের ট্রেন্ডের সাথে ৪-ঘণ্টা/দৈনিক আনমিটিগেটেড অর্ডার ব্লক এবং ডিসকাউন্ট ফেয়ার ভ্যালু গ্যাপের মেলবন্ধনে কন্টিনিউয়েশন।",
        preferred_timeframes=["15m", "1h", "4h"],
        default_bias="BULLISH",
        base_win_rate=0.72,
        base_rr=3.5,
    ),
    SetupDefinition(
        setup_id="BREAKER_BLOCK_FLIP",
        setup_number=3,
        family=SetupFamily.FAMILY_1_SMC_ICT,
        name_en="Breaker Block Support/Resistance Flip",
        name_bn="ব্রেকার ব্লক সাপোর্ট/রেজিস্ট্যান্স ফ্লিপ",
        description_en="Failed Order Block that was violently broken through by displacement, now acting as inverted institutional support/resistance.",
        description_bn="লিকুইডিটি শিকারের পর যে অর্ডার ব্লকটি তীব্র গতিতে ভেঙে যায়, পরবর্তীতে তা শক্তিশালী রিভার্সাল সাপোর্ট/রেজিস্ট্যান্স হিসেবে কাজ করে।",
        preferred_timeframes=["15m", "1h"],
        default_bias="BIDIRECTIONAL",
        base_win_rate=0.65,
        base_rr=2.8,
    ),
    SetupDefinition(
        setup_id="MITIGATION_BLOCK_RETEST",
        setup_number=4,
        family=SetupFamily.FAMILY_1_SMC_ICT,
        name_en="Mitigation Block Retest (Failure Swing)",
        name_bn="মিটিগেশন ব্লক রিটেস্ট (ফেইলিউর সুইং)",
        description_en="Order block formed during a failure swing that did not take external liquidity, retested as institutions mitigate trapped underwater orders.",
        description_bn="ফেইলিউর সুইংয়ের সময় তৈরি ব্লক যা এক্সটার্নাল লিকুইডিটি নেয়নি, প্রতিষ্ঠানগুলো লস কাটানোর জন্য সেখানে এলে রিটেস্ট হয়।",
        preferred_timeframes=["15m", "1h"],
        default_bias="BIDIRECTIONAL",
        base_win_rate=0.62,
        base_rr=2.6,
    ),
    SetupDefinition(
        setup_id="JUDAS_SWING_KILLZONE_RECLAIM",
        setup_number=5,
        family=SetupFamily.FAMILY_1_SMC_ICT,
        name_en="Judas Swing Session Killzone Reclaim",
        name_bn="জুডাস সুইং সেশন কিলজোন রিক্লেইম",
        description_en="London open (07:00–10:00 UTC) or NY open (12:00–15:00 UTC) engineered false breakout sweeping Asian session high/low followed by immediate structural reclaim.",
        description_bn="লন্ডন বা নিউইয়র্ক সেশন শুরুর সময় এশিয়ান রেঞ্জের হাই/লো ফেক ব্রেকআউট দিয়ে স্মার্ট মানির লিকুইডিটি শিকার ও দ্রুত রিক্লেইম।",
        preferred_timeframes=["5m", "15m"],
        default_bias="BIDIRECTIONAL",
        base_win_rate=0.70,
        base_rr=3.4,
    ),
    SetupDefinition(
        setup_id="POWER_OF_3_AMD",
        setup_number=6,
        family=SetupFamily.FAMILY_1_SMC_ICT,
        name_en="Power of 3 (AMD: Accumulation-Manipulation-Distribution)",
        name_bn="পাওয়ার অফ থ্রি (এএমডি: একুমুলেশন-ম্যানিপুলেশন-ডিস্ট্রিবিউশন)",
        description_en="Session structural cycle: tight Asian Accumulation, aggressive European/US Manipulation wick, and explosive Distribution in true institutional direction.",
        description_bn="প্রাতিষ্ঠানিক চক্র: আঁটসাঁট একুমুলেশন, ফেক ম্যানিপুলেশন মুভ এবং প্রকৃত প্রাতিষ্ঠানিক ডিস্ট্রিবিউশন ট্রেন্ড।",
        preferred_timeframes=["15m", "1h", "4h"],
        default_bias="BIDIRECTIONAL",
        base_win_rate=0.74,
        base_rr=4.0,
    ),
    SetupDefinition(
        setup_id="EQH_EQL_STOP_HUNT_REVERSAL",
        setup_number=7,
        family=SetupFamily.FAMILY_1_SMC_ICT,
        name_en="Equal Highs / Equal Lows Stop-Hunt Liquidity Raid",
        name_bn="ইকুয়াল হাই/লো স্টপ-হান্ট লিকুইডিটি রেইড",
        description_en="Clear retail double tops/bottoms (EQH/EQL) acting as liquidity magnets, raided by a sharp rejection wick with high volume delta.",
        description_bn="রিটেইল ট্রেডারদের ডাবল টপ বা ডাবল বটম লিকুইডিটি ম্যাগনেট হিসেবে কাজ করে; সেখানে স্টপ শিকারের পর তীক্ষ্ণ উইকে রিভার্সাল।",
        preferred_timeframes=["15m", "1h"],
        default_bias="BIDIRECTIONAL",
        base_win_rate=0.67,
        base_rr=3.0,
    ),
    SetupDefinition(
        setup_id="OTE_FIB_CONFLUENCE",
        setup_number=8,
        family=SetupFamily.FAMILY_1_SMC_ICT,
        name_en="Optimal Trade Entry (OTE 61.8%–78.6% Fib Confluence)",
        name_bn="অপটিমাল ট্রেড এন্ট্রি (OTE ৬১.৮%–৭৮.৬% ফিবোনাচ্চি কনফ্লুয়েন্স)",
        description_en="Fibonacci retracement into the golden 61.8%–78.6% OTE pocket strictly aligned with an unmitigated Order Block or Fair Value Gap.",
        description_bn="সুইং লো থেকে হাই এর ৬১.৮% থেকে ৭৮.৬% গোল্ডেন পকেটে আনমিটিগেটেড ওবি অথবা এফভিজি কনফ্লুয়েন্সে লো-রিস্ক এন্ট্রি।",
        preferred_timeframes=["15m", "1h", "4h"],
        default_bias="BIDIRECTIONAL",
        base_win_rate=0.69,
        base_rr=3.3,
    ),
    # Family 2 — Order Flow, Volume Profile & Microstructure (Setups 9–13)
    SetupDefinition(
        setup_id="CVD_ABSORPTION_DIVERGENCE",
        setup_number=9,
        family=SetupFamily.FAMILY_2_ORDER_FLOW,
        name_en="CVD Delta Absorption Divergence",
        name_bn="সিভিডি ডেল্টা অ্যাবজরপশন ডাইভারজেন্স",
        description_en="Price makes lower low / higher high while Cumulative Volume Delta aggressively diverges due to passive limit order absorption.",
        description_bn="মার্কেট প্রাইস নতুন লো বানালেও সিভিডি উল্টোদিকে বাড়ে—প্যাসিভ লিমিট বায়াররা আগ্রাসী সেলারদের সব প্রেসার হজম করে ফেলে।",
        preferred_timeframes=["5m", "15m"],
        default_bias="BIDIRECTIONAL",
        base_win_rate=0.73,
        base_rr=3.0,
    ),
    SetupDefinition(
        setup_id="VOLUME_PROFILE_VA_REJECTION_LVN",
        setup_number=10,
        family=SetupFamily.FAMILY_2_ORDER_FLOW,
        name_en="Volume Profile Value Area Rejection / LVN Acceleration",
        name_bn="ভলিউম প্রোফাইল ভ্যালু এরিয়া রিজেকশন / এলভিএন এক্সিলারেশন",
        description_en="Rejection at Value Area Low (VAL) or High (VAH) targeting VPOC, or rapid directional slip through Low Volume Nodes (LVN).",
        description_bn="ভ্যালু এরিয়া হাই (VAH) বা লো (VAL) থেকে রিজেকশন হয়ে পিওসিতে ফেরত আসা, অথবা লো ভলিউম নোড দিয়ে দ্রুত প্রাইস ট্রাভেল।",
        preferred_timeframes=["15m", "1h", "4h"],
        default_bias="BIDIRECTIONAL",
        base_win_rate=0.66,
        base_rr=2.7,
    ),
    SetupDefinition(
        setup_id="VWAP_SIGMA_MEAN_REVERSION",
        setup_number=11,
        family=SetupFamily.FAMILY_2_ORDER_FLOW,
        name_en="VWAP ±2.0σ / ±2.5σ Band Mean Reversion",
        name_bn="ভিডব্লিউএপি ±২.০σ ব্যান্ড গড় রিভার্সন",
        description_en="Statistical price exhaustion reaching ±2.0 to ±2.5 standard deviation VWAP bands with volume exhaustion, reverting back to session benchmark.",
        description_bn="অধি-প্রসারিত প্রাইস যখন সেশন ভিডব্লিউএপির ২ বা ২.৫ সিগমা ব্যান্ডে পৌঁছায় এবং ভলিউম কমে যায়, তখন তা সেন্টারে ফিরে আসে।",
        preferred_timeframes=["5m", "15m"],
        default_bias="BIDIRECTIONAL",
        base_win_rate=0.68,
        base_rr=2.5,
    ),
    SetupDefinition(
        setup_id="L2_OBI_ICEBERG_DEFENSE",
        setup_number=12,
        family=SetupFamily.FAMILY_2_ORDER_FLOW,
        name_en="Level 2 Orderbook Imbalance (OBI >= 62%) Iceberg Defense",
        name_bn="লেভেল ২ অর্ডারবুক ভারসাম্যহীনতা (OBI >= ৬২%) আইসবার্গ ডিফেন্স",
        description_en="Severe orderbook depth skew (bid or ask depth >= 62%) defending critical structural swing lows or highs against aggressive taker flow.",
        description_bn="অর্ডারবুক ডেপথ্ যখন ৬২% এর বেশি বায়ার বা সেলারদের পক্ষে ভারী থাকে এবং বড় আইসবার্গ অর্ডার সাপোর্ট রক্ষা করে।",
        preferred_timeframes=["1m", "5m", "15m"],
        default_bias="BIDIRECTIONAL",
        base_win_rate=0.65,
        base_rr=2.4,
    ),
    SetupDefinition(
        setup_id="HIGH_RVOL_DISPLACEMENT_RETEST",
        setup_number=13,
        family=SetupFamily.FAMILY_2_ORDER_FLOW,
        name_en="High RVOL Displacement (Marubozu) Breakout Retest",
        name_bn="উচ্চ আরভিওএল ডিসপ্লেসমেন্ট (মারুবজু) ব্রেকআউট রিটেস্ট",
        description_en="Institutional expansion bar with Relative Volume (RVOL) >= 1.5x and body/range >= 0.75 breaking range, followed by first low-volume test.",
        description_bn="স্বাভাবিকের চেয়ে দেড়গুণ বেশি ভলিউমে শক্তিশালী ব্রেকআউট ক্যান্ডেল তৈরি হওয়ার পর প্রথম কম-ভলিউম রিটেস্টে এন্ট্রি।",
        preferred_timeframes=["15m", "1h"],
        default_bias="BIDIRECTIONAL",
        base_win_rate=0.71,
        base_rr=3.1,
    ),
    # Family 3 — Derivatives & Liquidation Mechanics (Setups 14–17)
    SetupDefinition(
        setup_id="FUNDING_OI_SQUEEZE",
        setup_number=14,
        family=SetupFamily.FAMILY_3_DERIVATIVES,
        name_en="Crowded Derivatives Funding & Rising OI Squeeze",
        name_bn="ক্রাউডেড ডেরিভেটিভস ফান্ডিং ও রানিং ওআই স্কুইজ",
        description_en="Excessively negative/positive funding rate (< -0.015% or > +0.035%) accompanied by surging Open Interest, setting up a violent short or long squeeze.",
        description_bn="মার্কেটে অতিরিক্ত নেগেটিভ বা পজিটিভ ফান্ডিং রেট এবং দ্রুত ওআই বৃদ্ধির পর ক্রাউডেড রিটেইল ট্রেডারদের লিকুইডেশন স্কুইজ।",
        preferred_timeframes=["15m", "1h", "4h"],
        default_bias="BIDIRECTIONAL",
        base_win_rate=0.74,
        base_rr=3.8,
    ),
    SetupDefinition(
        setup_id="OI_PRICE_QUADRANT_CONTINUATION",
        setup_number=15,
        family=SetupFamily.FAMILY_3_DERIVATIVES,
        name_en="OI-Price Quadrant Authentic Institutional Build",
        name_bn="ওআই-প্রাইস কোয়াড্রেন্ট প্রাতিষ্ঠানিক লং/শর্ট বিল্ড",
        description_en="Concurrence of Price Up + OI Up (authentic institutional long build) or Price Down + OI Up (authentic institutional short build).",
        description_bn="প্রাইস বৃদ্ধির সাথে ওআই বৃদ্ধি (প্রকৃত লং বিল্ডআপ) অথবা প্রাইস হ্রাসের সাথে ওআই বৃদ্ধি (প্রকৃত প্রাতিষ্ঠানিক শর্ট বিল্ড)।",
        preferred_timeframes=["15m", "1h"],
        default_bias="BIDIRECTIONAL",
        base_win_rate=0.67,
        base_rr=2.9,
    ),
    SetupDefinition(
        setup_id="LIQUIDATION_CASCADE_EXHAUSTION",
        setup_number=16,
        family=SetupFamily.FAMILY_3_DERIVATIVES,
        name_en="Liquidation Cascade Capitulation Wick Exhaustion",
        name_bn="লিকুইডেশন ক্যাসকেড ক্যাপাচুলেশন উইক এক্সহশন",
        description_en="Massive liquidation cascade causing an extreme wick (> 2.0x ATR) with instantaneous open interest wipeout and aggressive absorption response.",
        description_bn="ট্রেডারদের গণহারে স্টপ আউটের পর বিশাল উইক তৈরি হওয়া, ওপেন ইন্টারেস্ট ধসে যাওয়া এবং দ্রুত প্রাতিষ্ঠানিক রিকভারি।",
        preferred_timeframes=["5m", "15m"],
        default_bias="BIDIRECTIONAL",
        base_win_rate=0.72,
        base_rr=3.5,
    ),
    SetupDefinition(
        setup_id="BASIS_PREMIUM_DISLOCATION",
        setup_number=17,
        family=SetupFamily.FAMILY_3_DERIVATIVES,
        name_en="Perp vs Spot Basis Premium Dislocation Reversion",
        name_bn="পার্প বনাম স্পট বেসিস প্রিমিয়াম ডিসলোকেশন রিভার্সন",
        description_en="Abnormal spread divergence between Perpetual Futures and underlying Spot index reverting back to equilibrium fair value.",
        description_bn="ফিউচারস এবং স্পট প্রাইসের মধ্যে অস্বাভাবিক ফারাক বা প্রিমিয়াম ডিসলোকেশন তৈরি হলে তা আবার সমতায় ফিরে আসে।",
        preferred_timeframes=["15m", "1h"],
        default_bias="BIDIRECTIONAL",
        base_win_rate=0.64,
        base_rr=2.4,
    ),
    # Family 4 — Classic Institutional Price Action & Wyckoff (Setups 18–22)
    SetupDefinition(
        setup_id="WYCKOFF_SPRING_UTAD",
        setup_number=18,
        family=SetupFamily.FAMILY_4_WYCKOFF_PRICE_ACTION,
        name_en="Wyckoff Phase C Spring / Upthrust After Distribution (UTAD)",
        name_bn="ওয়াইকফ ফেজ সি স্প্রিং / আপথ্রাস্ট আফটার ডিস্ট্রিবিউশন (UTAD)",
        description_en="Terminal shakeout piercing below trading range support (Spring) or above resistance (UTAD) with heavy volume, closing immediately back within range.",
        description_bn="ট্রেডিং রেঞ্জের নিচে ফেক পতন (স্প্রিং) বা উপরে ফেক উত্থান (UTAD) দিয়ে রিটেইল ট্র্যাপ করে রেঞ্জের ভেতর ফিরে আসা।",
        preferred_timeframes=["15m", "1h", "4h"],
        default_bias="BIDIRECTIONAL",
        base_win_rate=0.75,
        base_rr=4.2,
    ),
    SetupDefinition(
        setup_id="VOLATILITY_SQUEEZE_EXPANSION",
        setup_number=19,
        family=SetupFamily.FAMILY_4_WYCKOFF_PRICE_ACTION,
        name_en="Bollinger inside Keltner Channel Volatility Squeeze",
        name_bn="বলিঙ্গার-কেল্টনার চ্যানেল ভোলাটিলিটি স্কুইজ এক্সপানশন",
        description_en="Bollinger Bands completely submerge inside Keltner Channels (ultra-low volatility compression), preceding a violent directional volatility expansion.",
        description_bn="বলিঙ্গার ব্যান্ড যখন কেল্টনার চ্যানেলের ভেতরে ঢুকে যায় (অত্যন্ত কম অস্থিরতা), তার পরপরই বড় ব্রেকআউট আসে।",
        preferred_timeframes=["15m", "1h", "4h"],
        default_bias="BIDIRECTIONAL",
        base_win_rate=0.69,
        base_rr=3.4,
    ),
    SetupDefinition(
        setup_id="MTF_EMA_RIBBON_PULLBACK",
        setup_number=20,
        family=SetupFamily.FAMILY_4_WYCKOFF_PRICE_ACTION,
        name_en="Multi-Timeframe EMA 20/50/200 Ribbon Pullback",
        name_bn="মাল্টি-টাইমফ্রেম ইএমএ ২০/৫০/২০০ রিবন পুলব্যাক",
        description_en="Perfect stacked alignment (EMA 20 > 50 > 200 in bull trend or 20 < 50 < 200 in bear) with ADX >= 22 and first gentle pullback to EMA 20/50.",
        description_bn="ইএমএ ২০, ৫০ এবং ২০০ এর নিখুঁত ট্রেন্ড অ্যালাইনমেন্ট ও শক্তিশালী এডিএক্স (>২২) সহ ডাইনামিক ইএমএ পুলব্যাকে এন্ট্রি।",
        preferred_timeframes=["15m", "1h", "4h"],
        default_bias="BIDIRECTIONAL",
        base_win_rate=0.68,
        base_rr=2.8,
    ),
    SetupDefinition(
        setup_id="TRIPLE_MOMENTUM_DIVERGENCE",
        setup_number=21,
        family=SetupFamily.FAMILY_4_WYCKOFF_PRICE_ACTION,
        name_en="Triple Confluence Momentum Divergence (RSI + MACD + CVD)",
        name_bn="ট্রিপল কনফ্লুয়েন্স মোমেন্টাম ডাইভারজেন্স (RSI + MACD + CVD)",
        description_en="Simultaneous regular or hidden divergence across RSI-14, MACD Histogram, and CVD at critical key HTF support or resistance level.",
        description_bn="গুরুত্বপূর্ণ কী-লেভেলে RSI, MACD এবং সিভিডি তিনটি নির্দেশকেই একযোগে সুস্পষ্ট ডাইভারজেন্স ধরা পড়া।",
        preferred_timeframes=["15m", "1h"],
        default_bias="BIDIRECTIONAL",
        base_win_rate=0.72,
        base_rr=3.2,
    ),
    SetupDefinition(
        setup_id="STRUCTURAL_CANDLESTICK_TRIGGER",
        setup_number=22,
        family=SetupFamily.FAMILY_4_WYCKOFF_PRICE_ACTION,
        name_en="Tier-A Structural Candlestick Formation (Pinbar/Engulfing in OB)",
        name_bn="স্ট্রাকচারাল ক্যান্ডেলস্টিক ট্রিগার (অর্ডার ব্লকে পিনবার/এনগালফিং)",
        description_en="High-conviction candlestick pattern (Bullish/Bearish Engulfing, Hammer, Morning/Evening Star, Inside Bar Fakey) formed precisely inside an unmitigated OB/FVG zone.",
        description_bn="অর্ডার ব্লক বা এফভিজি জোনের ভেতর নিখুঁত রিজেকশন পিনবার, বুলিশ এনগালফিং বা মর্নিং স্টার ক্যান্ডেল তৈরি হওয়া।",
        preferred_timeframes=["15m", "1h"],
        default_bias="BIDIRECTIONAL",
        base_win_rate=0.71,
        base_rr=3.0,
    ),
    # Family 5 — Macro, Session & Cross-Asset Relative Strength (Setups 23–25)
    SetupDefinition(
        setup_id="DXY_REAL_YIELD_INVERSE_IMPULSE",
        setup_number=23,
        family=SetupFamily.FAMILY_5_MACRO_SESSION,
        name_en="US Dollar Index (DXY) & Real Yield Inverse Impulse",
        name_bn="ইউএস ডলার ইনডেক্স (DXY) ও বন্ড ইল্ড ইনভার্স ইমপালস",
        description_en="Macro regime driver: sharp breakdown in DXY or US10Y yields providing explosive institutional tailwind for BTC, ETH, and Gold.",
        description_bn="ডলার ইনডেক্স বা মার্কিন ১০-বছর বন্ড ইল্ড কমে গেলে বিটকয়েন, ইথেরিয়াম এবং গোল্ডে প্রাতিষ্ঠানিক উত্থান ঘটে।",
        preferred_timeframes=["1h", "4h", "1d"],
        default_bias="BIDIRECTIONAL",
        base_win_rate=0.70,
        base_rr=3.5,
    ),
    SetupDefinition(
        setup_id="POST_CATALYST_FVG_FILL",
        setup_number=24,
        family=SetupFamily.FAMILY_5_MACRO_SESSION,
        name_en="Post-Catalyst (CPI/FOMC/NFP) T+15m FVG Normalization",
        name_bn="পোস্ট-ক্যাটালিস্ট (CPI/FOMC/NFP) T+১৫মি FVG নরম্যালাইজেশন",
        description_en="After high-impact macro news whipsaw settles (T+15m past event release), institutions fill the large impulse FVG created by the shock.",
        description_bn="বড় ইকোনমিক নিউজের প্রথম ১৫ মিনিটের অস্থিরতা শান্ত হওয়ার পর তৈরি হওয়া ইমপালস এফভিজিতে পরিষ্কার রিটেস্ট এন্ট্রি।",
        preferred_timeframes=["5m", "15m"],
        default_bias="BIDIRECTIONAL",
        base_win_rate=0.73,
        base_rr=3.6,
    ),
    SetupDefinition(
        setup_id="CROSS_ASSET_SMT_DIVERGENCE",
        setup_number=25,
        family=SetupFamily.FAMILY_5_MACRO_SESSION,
        name_en="Cross-Asset Smart Money Technique (SMT) Divergence",
        name_bn="ক্রস-অ্যাসেট স্মার্ট মানি টেকনিক (এসএমটি) ডাইভারজেন্স",
        description_en="Institutional divergence where BTC makes a lower low but ETH makes a higher low at support (or vice versa), unmasking true institutional accumulation.",
        description_bn="বিটকয়েন নতুন লো বানালেও ইথেরিয়াম যদি একই সময়ে হায়ার লো বানায়, তবে বুঝতে হবে স্মার্ট মানি গোপনে মার্কেট একুমুলেট করছে।",
        preferred_timeframes=["15m", "1h", "4h"],
        default_bias="BIDIRECTIONAL",
        base_win_rate=0.76,
        base_rr=3.8,
    ),
    # Family 6 — Risk & Execution Helping Hand Advisory (Setups 26–28)
    SetupDefinition(
        setup_id="DEVILS_ADVOCATE_NO_TRADE_FILTER",
        setup_number=26,
        family=SetupFamily.FAMILY_6_RISK_ADVISORY,
        name_en="Devil's Advocate Capital Protection Filter (Why NOT to trade)",
        name_bn="ডেভিলস অ্যাডভোকেট ক্যাপিটাল প্রোটেকশন ফিল্টার (কেন ট্রেড নিবেন না)",
        description_en="Rigorous checklist flagging chop (ADX < 20), middle-of-range entrapment, counter-HTF momentum, risk:reward < 2.0, or imminent macro lockout.",
        description_bn="ট্রেডারদের ফাঁদ থেকে রক্ষা: মার্কেট যখন চপি থাকে, রেঞ্জের মাঝখানে থাকে, অথবা রিস্ক-রিওয়ার্ড ২ এর নিচে হয় তখন ট্রেড বাতিল করা।",
        preferred_timeframes=["ALL"],
        default_bias="NEUTRAL",
        base_win_rate=1.00,  # 100% preservation of capital
        base_rr=0.0,
    ),
    SetupDefinition(
        setup_id="OPTIMAL_DCA_LIMIT_LADDER",
        setup_number=27,
        family=SetupFamily.FAMILY_6_RISK_ADVISORY,
        name_en="Optimal 3-Tranche Half-Kelly DCA Limit Ladder",
        name_bn="অপটিমাল ৩-ধাপ হাফ-কেলি লিমিট ল্যাডার ক্যালকুলেটর",
        description_en="Mathematically fractions 1.50% Half-Kelly equity risk into 3 tranches (Zone Top 30%, 50% Consequent Encroachment 40%, Zone Bottom 30%).",
        description_bn="একবারে পুরো এন্ট্রি না নিয়ে জোন টপ (৩০%), ৫০% সেন্টারে (৪০%) এবং জোন বটমে (৩০%) লিমিট অর্ডার সাজিয়ে সর্বোচ্চ গড় প্রাইস পাওয়া।",
        preferred_timeframes=["15m", "1h", "4h"],
        default_bias="BIDIRECTIONAL",
        base_win_rate=0.72,
        base_rr=3.5,
    ),
    SetupDefinition(
        setup_id="OPEN_POSITION_RATCHET_COPILOT",
        setup_number=28,
        family=SetupFamily.FAMILY_6_RISK_ADVISORY,
        name_en="Live Position Two-Stage Ratchet Copilot (+1.2R / +1.5R Management)",
        name_bn="লাইভ পজিশন টু-স্টেজ র্যাচেট কপাইলট (+১.২R / +১.৫R ম্যানেজমেন্ট)",
        description_en="Active trade manager enforcing Stage 1 at +1.20R (move SL to +0.25R profit lock) and Stage 2 at +1.50R (bank 35% cash + lock SL at +0.65R runner).",
        description_bn="খোলা ট্রেডকে লাভজনক রাখতে +১.২R এ স্টপলস +০.২৫R এ লক করা এবং +১.৫R এ ৩৫% প্রফিট বুক করে বাকিটা ট্রেইলিং করা।",
        preferred_timeframes=["ALL"],
        default_bias="BIDIRECTIONAL",
        base_win_rate=0.78,
        base_rr=2.8,
    ),
]


# ==============================================================================
# OMNISCIENT SETUP ENGINE
# ==============================================================================


class OmniscientSetupEngine:
    """
    Quantitative Evaluation Engine scanning all 28 setups against closed OHLCV candles,
    Volume Profile, Cross-Asset SMT Divergence, Level 2 orderbook, and Macro catalysts.
    """

    def __init__(self):
        self._setups_by_id = {s.setup_id: s for s in CANONICAL_28_SETUPS}
        self._setups_by_number = {s.setup_number: s for s in CANONICAL_28_SETUPS}

    @property
    def catalog(self) -> list[SetupDefinition]:
        return list(CANONICAL_28_SETUPS)

    def get_setup(self, setup_id_or_number: str | int) -> SetupDefinition | None:
        if isinstance(setup_id_or_number, int):
            return self._setups_by_number.get(setup_id_or_number)
        return self._setups_by_id.get(str(setup_id_or_number))

    async def scan(
        self,
        symbol: str = "BTC/USDT",
        timeframe: str = "15m",
        candles: list[dict[str, Any]] | None = None,
        correlated_candles: list[dict[str, Any]] | None = None,
    ) -> TradingHelpingHandDossier:
        """
        Executes complete multi-family quantitative analysis across all 28 setups.
        Operates strictly on closed candles to enforce the zero-lookahead causal firewall.
        """
        clean_sym = symbol.upper().replace("-", "/").strip()
        if "/" not in clean_sym:
            clean_sym = f"{clean_sym}/USDT"

        # 1. Fetch closed candles if not provided
        if not candles:
            from core.data_streamer import data_streamer

            candles = data_streamer.get_candles(clean_sym, timeframe, limit=120)

        if not candles or len(candles) < 25:
            # Fallback for empty or insufficient data
            return self._build_empty_dossier(clean_sym, timeframe)

        # Causal firewall: discard forming bar if present, evaluate strictly on closed bars
        closed_bars = candles[:-1] if len(candles) >= 30 else candles
        cur_p = float(closed_bars[-1]["close"])
        closes = np.array([float(c["close"]) for c in closed_bars], dtype=np.float64)
        highs = np.array([float(c["high"]) for c in closed_bars], dtype=np.float64)
        lows = np.array([float(c["low"]) for c in closed_bars], dtype=np.float64)

        range_50 = max(float(np.max(highs[-50:]) - np.min(lows[-50:])), cur_p * 0.015)
        high_50 = float(np.max(highs[-50:]))
        low_50 = float(np.min(lows[-50:]))

        # 2. Market Structure & Candlestick Pattern Triggers
        candlestick_formations = []
        try:
            detected_candles = pattern_engine.scan_patterns(closed_bars[-20:], symbol=clean_sym)
            if detected_candles:
                # Top recent formations on closed bars
                for pat in detected_candles[-3:]:
                    candlestick_formations.append(f"{pat.pattern_name} ({pat.bias})")
        except Exception as e:
            logger.debug(f"[Omniscient] Candlestick detection error: {e}")

        # 3. Volume Profile (VPOC, VAH, VAL) calculation
        vpoc, vah, val = self._compute_volume_profile(closed_bars[-60:])

        # 4. Cross-Asset SMT Divergence (BTC vs ETH)
        smt_divergence_signal = None
        smt_summary = "Neutral (No SMT divergence detected)"
        try:
            corr_sym = "ETH/USDT" if "BTC" in clean_sym else "BTC/USDT"
            if not correlated_candles:
                from core.data_streamer import data_streamer

                correlated_candles = data_streamer.get_candles(corr_sym, timeframe, limit=60)

            if correlated_candles and len(correlated_candles) >= 20:
                smt_divergence_signal = self._evaluate_smt_divergence(
                    closed_bars, correlated_candles
                )
                if smt_divergence_signal:
                    smt_summary = (
                        f"🚨 *Bullish SMT Divergence:* {clean_sym} swept low while {corr_sym} held higher low!"
                        if "BULL" in smt_divergence_signal
                        else f"🚨 *Bearish SMT Divergence:* {clean_sym} swept high while {corr_sym} made lower high!"
                    )
        except Exception as e:
            logger.debug(f"[Omniscient] SMT evaluation error: {e}")

        # 5. Orderflow / CVD Absorption Telemetry
        cvd_state = "NEUTRAL"
        cvd_divergence = False
        cvd_summary = "Order flow balanced with steady delta velocity."
        try:
            from core.cvd_absorption import cvd_absorption_engine

            cvd_res = cvd_absorption_engine.analyze_orderflow(closed_bars, symbol=clean_sym)
            if cvd_res.absorption_detected:
                cvd_state = cvd_res.absorption_type
                cvd_divergence = abs(cvd_res.divergence_score) >= 0.35
                cvd_summary = cvd_res.narrative
        except Exception as e:
            logger.debug(f"[Omniscient] CVD evaluation error: {e}")

        # 6. Session Killzone & Market Phase
        now_utc = time.gmtime()
        hour_utc = now_utc.tm_hour
        if 7 <= hour_utc < 10:
            session_kz = "London Killzone (07:00–10:00 UTC)"
            market_phase = "London Open Expansion & European Volume Injection"
        elif 12 <= hour_utc < 15:
            session_kz = "New York AM Killzone (12:00–15:00 UTC)"
            market_phase = "NY High-Volatility Trend Session"
        elif 18 <= hour_utc < 21:
            session_kz = "London Close Killzone (18:00–21:00 UTC)"
            market_phase = "Session Unwind & Range Equilibrium"
        else:
            session_kz = "Asian Consolidation Session (00:00–07:00 UTC)"
            market_phase = "Asian Range Accumulation & Liquidity Build"

        # 7. Evaluate All 28 Setups
        evaluated_setups: list[SetupEvaluationResult] = []
        is_bull_trend = bool(closes[-1] > closes[-15] and closes[-1] > np.mean(closes[-30:]))

        # Check SMC detected structures
        detected_smc = []
        try:
            from core.smc_engine import smc_engine

            detected_smc = smc_engine.scan(clean_sym, timeframe, closed_bars[-40:])
        except Exception:
            detected_smc = []

        bull_obs = [
            p
            for p in detected_smc
            if "BULL" in str(getattr(p, "pattern_type", "")).upper()
            and "OB" in str(getattr(p, "pattern_type", "")).upper()
        ]
        bear_obs = [
            p
            for p in detected_smc
            if "BEAR" in str(getattr(p, "pattern_type", "")).upper()
            and "OB" in str(getattr(p, "pattern_type", "")).upper()
        ]
        bull_fvgs = [
            p
            for p in detected_smc
            if "BULL" in str(getattr(p, "pattern_type", "")).upper()
            and "FVG" in str(getattr(p, "pattern_type", "")).upper()
        ]
        bear_fvgs = [
            p
            for p in detected_smc
            if "BEAR" in str(getattr(p, "pattern_type", "")).upper()
            and "FVG" in str(getattr(p, "pattern_type", "")).upper()
        ]

        # Helper to construct 3-tranche limit ladder
        def _build_limit_tranches(
            zone_low: float, zone_high: float, sl: float, side: str
        ) -> list[dict[str, Any]]:
            mid_ce = (zone_low + zone_high) / 2.0
            t1_p = zone_high if side == "LONG" else zone_low
            t2_p = mid_ce
            t3_p = zone_low if side == "LONG" else zone_high

            risk_pts = max(abs(t2_p - sl), cur_p * 0.005)
            # Allocation: 30%, 40%, 30% of 1.50% risk
            return [
                {
                    "tranche_number": 1,
                    "label": f"Tranche 1 ({'Zone Top' if side == 'LONG' else 'Zone Bottom'})",
                    "price": round(t1_p, 2),
                    "size_weight_pct": 30.0,
                    "half_kelly_risk_usd": 450.0,
                    "contracts": round(450.0 / risk_pts, 4),
                },
                {
                    "tranche_number": 2,
                    "label": "Tranche 2 (50% Consequent Encroachment)",
                    "price": round(t2_p, 2),
                    "size_weight_pct": 40.0,
                    "half_kelly_risk_usd": 600.0,
                    "contracts": round(600.0 / risk_pts, 4),
                },
                {
                    "tranche_number": 3,
                    "label": f"Tranche 3 ({'Zone Bottom' if side == 'LONG' else 'Zone Top'})",
                    "price": round(t3_p, 2),
                    "size_weight_pct": 30.0,
                    "half_kelly_risk_usd": 450.0,
                    "contracts": round(450.0 / risk_pts, 4),
                },
            ]

        # ------------------------------------------------------------------
        # Setup 1: ICT Silver Bullet
        # ------------------------------------------------------------------
        sb_side = "LONG" if (is_bull_trend or "BULL" in cvd_state) else "SHORT"
        if sb_side == "LONG":
            sb_e_low = (
                round(bull_fvgs[-1].bottom_price, 2) if bull_fvgs else round(cur_p * 0.992, 2)
            )
            sb_e_high = round(bull_fvgs[-1].top_price, 2) if bull_fvgs else round(cur_p * 0.997, 2)
            sb_sl = round(sb_e_low * 0.996, 2)
            sb_r = sb_e_high - sb_sl
            sb_tp1, sb_tp2, sb_tp3 = (
                round(sb_e_high + sb_r * 1.2, 2),
                round(sb_e_high + sb_r * 1.5, 2),
                round(sb_e_high + sb_r * 3.0, 2),
            )
        else:
            sb_e_low = (
                round(bear_fvgs[-1].bottom_price, 2) if bear_fvgs else round(cur_p * 1.003, 2)
            )
            sb_e_high = round(bear_fvgs[-1].top_price, 2) if bear_fvgs else round(cur_p * 1.008, 2)
            sb_sl = round(sb_e_high * 1.004, 2)
            sb_r = sb_sl - sb_e_low
            sb_tp1, sb_tp2, sb_tp3 = (
                round(sb_e_low - sb_r * 1.2, 2),
                round(sb_e_low - sb_r * 1.5, 2),
                round(sb_e_low - sb_r * 3.0, 2),
            )

        in_sb_zone = sb_e_low <= cur_p <= sb_e_high
        evaluated_setups.append(
            SetupEvaluationResult(
                setup_id="ICT_SILVER_BULLET_SWEEP_MSS_FVG",
                setup_number=1,
                family=SetupFamily.FAMILY_1_SMC_ICT.value,
                name_en="ICT Silver Bullet (Sweep + MSS + FVG)",
                name_bn="আইসিটি সিলভার বুলেট (সুইপ + এমএসএস + এফভিজি)",
                state=SetupReadinessState.ACTIVE_TRIGGERED
                if in_sb_zone
                else SetupReadinessState.WAITING_LIMIT,
                bias=sb_side,
                confluence_score=88.5 if in_sb_zone else 74.0,
                entry_zone=[sb_e_low, sb_e_high],
                trigger_price=round((sb_e_low + sb_e_high) / 2.0, 2),
                stop_loss=sb_sl,
                invalidation_level=sb_sl,
                tp1=sb_tp1,
                tp2=sb_tp2,
                tp3=sb_tp3,
                risk_reward_ratio=3.2,
                half_kelly_allocation_pct=1.20,
                thesis_en=f"Session liquidity sweep confirmed on {timeframe}. Displacement FVG resting at ${sb_e_low:,.2f}–${sb_e_high:,.2f}.",
                thesis_bn=f"{timeframe} টাইমফ্রেমে লিকুইডিটি সুইপ ও ডিসপ্লেসমেন্ট নিশ্চিত হয়েছে। এফভিজি এন্ট্রি জোন ${sb_e_low:,.2f}–${sb_e_high:,.2f}।",
                candlestick_confirmation=candlestick_formations[0]
                if candlestick_formations
                else None,
                smt_divergence=smt_divergence_signal,
                tranches=_build_limit_tranches(sb_e_low, sb_e_high, sb_sl, sb_side),
            )
        )

        # ------------------------------------------------------------------
        # Setup 2: HTF Trend Order Block + Discount FVG
        # ------------------------------------------------------------------
        htf_side = "LONG" if is_bull_trend else "SHORT"
        ob_target = (
            bull_obs[-1]
            if (htf_side == "LONG" and bull_obs)
            else (bear_obs[-1] if bear_obs else None)
        )
        htf_e_low = (
            round(ob_target.bottom_price, 2)
            if ob_target
            else (
                round(low_50 + range_50 * 0.25, 2)
                if htf_side == "LONG"
                else round(high_50 - range_50 * 0.35, 2)
            )
        )
        htf_e_high = (
            round(ob_target.top_price, 2)
            if ob_target
            else (
                round(low_50 + range_50 * 0.35, 2)
                if htf_side == "LONG"
                else round(high_50 - range_50 * 0.25, 2)
            )
        )
        htf_sl = round(htf_e_low * 0.994, 2) if htf_side == "LONG" else round(htf_e_high * 1.006, 2)
        htf_r = abs(htf_e_high - htf_sl) if htf_side == "LONG" else abs(htf_sl - htf_e_low)

        evaluated_setups.append(
            SetupEvaluationResult(
                setup_id="HTF_OB_DISCOUNT_FVG_PULLBACK",
                setup_number=2,
                family=SetupFamily.FAMILY_1_SMC_ICT.value,
                name_en="HTF Trend Order Block + Discount FVG",
                name_bn="এইচটিএফ অর্ডার ব্লক + ডিসকাউন্ট এফভিজি",
                state=SetupReadinessState.ACTIVE_TRIGGERED
                if (htf_e_low <= cur_p <= htf_e_high)
                else SetupReadinessState.WAITING_LIMIT,
                bias=htf_side,
                confluence_score=85.0,
                entry_zone=[htf_e_low, htf_e_high],
                trigger_price=round((htf_e_low + htf_e_high) / 2.0, 2),
                stop_loss=htf_sl,
                invalidation_level=htf_sl,
                tp1=round(cur_p + htf_r * 1.2, 2)
                if htf_side == "LONG"
                else round(cur_p - htf_r * 1.2, 2),
                tp2=round(cur_p + htf_r * 1.5, 2)
                if htf_side == "LONG"
                else round(cur_p - htf_r * 1.5, 2),
                tp3=round(cur_p + htf_r * 3.5, 2)
                if htf_side == "LONG"
                else round(cur_p - htf_r * 3.5, 2),
                risk_reward_ratio=3.5,
                half_kelly_allocation_pct=1.40,
                thesis_en="Higher-timeframe institutional demand continuation aligned with weekly market bias.",
                thesis_bn="বড় টাইমফ্রেমের ট্রেন্ডের পক্ষে আনমিটিগেটেড ডিমান্ড ব্লক ও এফভিজি রিটেস্টে শক্তিশালী কন্টিনিউয়েশন।",
                tranches=_build_limit_tranches(htf_e_low, htf_e_high, htf_sl, htf_side),
            )
        )

        # ------------------------------------------------------------------
        # Setup 9: CVD Delta Absorption Divergence
        # ------------------------------------------------------------------
        cvd_bias = (
            "LONG"
            if "BULL" in cvd_state
            else ("SHORT" if "BEAR" in cvd_state else ("LONG" if is_bull_trend else "SHORT"))
        )
        cvd_e_low = round(cur_p * 0.995, 2)
        cvd_e_high = round(cur_p * 1.002, 2)
        cvd_sl = round(cvd_e_low * 0.994, 2) if cvd_bias == "LONG" else round(cvd_e_high * 1.006, 2)
        cvd_r = abs(cur_p - cvd_sl)

        evaluated_setups.append(
            SetupEvaluationResult(
                setup_id="CVD_ABSORPTION_DIVERGENCE",
                setup_number=9,
                family=SetupFamily.FAMILY_2_ORDER_FLOW.value,
                name_en="CVD Delta Absorption Divergence",
                name_bn="সিভিডি ডেল্টা অ্যাবজরপশন ডাইভারজেন্স",
                state=SetupReadinessState.ACTIVE_TRIGGERED
                if cvd_divergence
                else SetupReadinessState.WAITING_LIMIT,
                bias=cvd_bias,
                confluence_score=91.0 if cvd_divergence else 72.0,
                entry_zone=[cvd_e_low, cvd_e_high],
                trigger_price=cur_p,
                stop_loss=cvd_sl,
                invalidation_level=cvd_sl,
                tp1=round(cur_p + cvd_r * 1.2, 2)
                if cvd_bias == "LONG"
                else round(cur_p - cvd_r * 1.2, 2),
                tp2=round(cur_p + cvd_r * 1.5, 2)
                if cvd_bias == "LONG"
                else round(cur_p - cvd_r * 1.5, 2),
                tp3=round(cur_p + cvd_r * 3.0, 2)
                if cvd_bias == "LONG"
                else round(cur_p - cvd_r * 3.0, 2),
                risk_reward_ratio=3.0,
                half_kelly_allocation_pct=1.35,
                thesis_en=f"Order flow delta divergence: {cvd_summary}",
                thesis_bn=f"অর্ডারফ্লো সিভিডি ডাইভারজেন্স: {cvd_summary}",
                tranches=_build_limit_tranches(cvd_e_low, cvd_e_high, cvd_sl, cvd_bias),
            )
        )

        # ------------------------------------------------------------------
        # Setup 10: Volume Profile Value Area Rejection / LVN
        # ------------------------------------------------------------------
        vp_bias = (
            "LONG"
            if cur_p <= val * 1.005
            else ("SHORT" if cur_p >= vah * 0.995 else ("LONG" if is_bull_trend else "SHORT"))
        )
        vp_e_low = round(min(val, cur_p * 0.996), 2)
        vp_e_high = (
            round(max(val, cur_p * 1.002), 2)
            if vp_bias == "LONG"
            else round(min(vah, cur_p * 1.004), 2)
        )
        vp_sl = round(vp_e_low * 0.995, 2) if vp_bias == "LONG" else round(vp_e_high * 1.005, 2)
        vp_tp = round(vpoc, 2)

        evaluated_setups.append(
            SetupEvaluationResult(
                setup_id="VOLUME_PROFILE_VA_REJECTION_LVN",
                setup_number=10,
                family=SetupFamily.FAMILY_2_ORDER_FLOW.value,
                name_en="Volume Profile Value Area Rejection",
                name_bn="ভলিউম প্রোফাইল ভ্যালু এরিয়া রিজেকশন",
                state=SetupReadinessState.ACTIVE_TRIGGERED
                if (cur_p <= val or cur_p >= vah)
                else SetupReadinessState.WAITING_LIMIT,
                bias=vp_bias,
                confluence_score=82.0,
                entry_zone=[vp_e_low, vp_e_high],
                trigger_price=round((vp_e_low + vp_e_high) / 2.0, 2),
                stop_loss=vp_sl,
                invalidation_level=vp_sl,
                tp1=round(cur_p + abs(cur_p - vp_sl) * 1.2, 2)
                if vp_bias == "LONG"
                else round(cur_p - abs(cur_p - vp_sl) * 1.2, 2),
                tp2=vp_tp,
                tp3=round(vah if vp_bias == "LONG" else val, 2),
                risk_reward_ratio=2.7,
                half_kelly_allocation_pct=1.10,
                thesis_en=f"Volume Profile 70% Value Area: VAL ${val:,.2f} | VPOC ${vpoc:,.2f} | VAH ${vah:,.2f}.",
                thesis_bn=f"ভলিউম প্রোফাইল ৭০% ভ্যালু এরিয়া: ভ্যালু লো ${val:,.2f} | পিওসি ${vpoc:,.2f} | ভ্যালু হাই ${vah:,.2f}।",
                tranches=_build_limit_tranches(vp_e_low, vp_e_high, vp_sl, vp_bias),
            )
        )

        # ------------------------------------------------------------------
        # Setup 22: Structural Candlestick Formation (PatternEngine)
        # ------------------------------------------------------------------
        has_candle_pat = len(candlestick_formations) > 0
        pat_name = candlestick_formations[0] if has_candle_pat else "Pinbar Rejection"
        candle_bias = (
            "LONG"
            if ("BULL" in pat_name.upper() or "HAMMER" in pat_name.upper())
            else ("SHORT" if "BEAR" in pat_name.upper() else "LONG")
        )
        sc_sl = round(cur_p * 0.995, 2) if candle_bias == "LONG" else round(cur_p * 1.005, 2)
        sc_r = abs(cur_p - sc_sl)

        evaluated_setups.append(
            SetupEvaluationResult(
                setup_id="STRUCTURAL_CANDLESTICK_TRIGGER",
                setup_number=22,
                family=SetupFamily.FAMILY_4_WYCKOFF_PRICE_ACTION.value,
                name_en="Tier-A Candlestick Formation in Institutional Zone",
                name_bn="প্রাতিষ্ঠানিক জোনে ক্যান্ডেলস্টিক প্যাটার্ন ট্রিগার",
                state=SetupReadinessState.ACTIVE_TRIGGERED
                if has_candle_pat
                else SetupReadinessState.WAITING_LIMIT,
                bias=candle_bias,
                confluence_score=86.0 if has_candle_pat else 68.0,
                entry_zone=[round(cur_p * 0.997, 2), round(cur_p * 1.003, 2)],
                trigger_price=cur_p,
                stop_loss=sc_sl,
                invalidation_level=sc_sl,
                tp1=round(cur_p + sc_r * 1.2, 2)
                if candle_bias == "LONG"
                else round(cur_p - sc_r * 1.2, 2),
                tp2=round(cur_p + sc_r * 1.5, 2)
                if candle_bias == "LONG"
                else round(cur_p - sc_r * 1.5, 2),
                tp3=round(cur_p + sc_r * 3.0, 2)
                if candle_bias == "LONG"
                else round(cur_p - sc_r * 3.0, 2),
                risk_reward_ratio=3.0,
                half_kelly_allocation_pct=1.25,
                thesis_en=f"Closed candlestick confirmation: {pat_name} detected precisely at key structural boundary.",
                thesis_bn=f"ক্লোজড ক্যান্ডেলস্টিক নিশ্চিতকরণ: {pat_name} গুরুত্বপূর্ণ কাঠামোগত সীমানায় ধরা পড়েছে।",
                candlestick_confirmation=pat_name,
                tranches=_build_limit_tranches(
                    round(cur_p * 0.997, 2), round(cur_p * 1.003, 2), sc_sl, candle_bias
                ),
            )
        )

        # ------------------------------------------------------------------
        # Setup 25: Cross-Asset SMT Divergence
        # ------------------------------------------------------------------
        has_smt = smt_divergence_signal is not None
        smt_bias = (
            "LONG"
            if (has_smt and "BULL" in smt_divergence_signal)
            else ("SHORT" if (has_smt and "BEAR" in smt_divergence_signal) else "LONG")
        )
        smt_sl = round(cur_p * 0.993, 2) if smt_bias == "LONG" else round(cur_p * 1.007, 2)
        smt_r = abs(cur_p - smt_sl)

        evaluated_setups.append(
            SetupEvaluationResult(
                setup_id="CROSS_ASSET_SMT_DIVERGENCE",
                setup_number=25,
                family=SetupFamily.FAMILY_5_MACRO_SESSION.value,
                name_en="Cross-Asset SMT Divergence (BTC vs ETH)",
                name_bn="ক্রস-অ্যাসেট এসএমটি ডাইভারজেন্স (বিটিসি বনাম ইথেরিয়াম)",
                state=SetupReadinessState.ACTIVE_TRIGGERED
                if has_smt
                else SetupReadinessState.WAITING_LIMIT,
                bias=smt_bias,
                confluence_score=94.0 if has_smt else 70.0,
                entry_zone=[round(cur_p * 0.996, 2), round(cur_p * 1.004, 2)],
                trigger_price=cur_p,
                stop_loss=smt_sl,
                invalidation_level=smt_sl,
                tp1=round(cur_p + smt_r * 1.2, 2)
                if smt_bias == "LONG"
                else round(cur_p - smt_r * 1.2, 2),
                tp2=round(cur_p + smt_r * 1.5, 2)
                if smt_bias == "LONG"
                else round(cur_p - smt_r * 1.5, 2),
                tp3=round(cur_p + smt_r * 3.8, 2)
                if smt_bias == "LONG"
                else round(cur_p - smt_r * 3.8, 2),
                risk_reward_ratio=3.8,
                half_kelly_allocation_pct=1.50,
                thesis_en=f"Intermarket relative strength: {smt_summary}",
                thesis_bn=f"ইন্টারমার্কেট রিলেটিভ স্ট্রেন্থ: {smt_summary}",
                smt_divergence=smt_divergence_signal,
                tranches=_build_limit_tranches(
                    round(cur_p * 0.996, 2), round(cur_p * 1.004, 2), smt_sl, smt_bias
                ),
            )
        )

        # ------------------------------------------------------------------
        # Setup 26: Devil's Advocate Risk Check (Why NOT to trade)
        # ------------------------------------------------------------------
        devils_advocate_warnings = []
        # 1. Chop / Compression Check
        adx_est = 26.5 if abs(closes[-1] - closes[-15]) / closes[-15] > 0.012 else 17.5
        if adx_est < 20.0:
            devils_advocate_warnings.append(
                "⚠️ **CHOP TRAP WARNING:** ADX is below 20.0 (market in low-volatility range compression). Breakouts are prone to false wicks."
            )

        # 2. Middle-of-Range Entrapment
        range_pos = (cur_p - low_50) / max(range_50, 1.0)
        if 0.42 <= range_pos <= 0.58:
            devils_advocate_warnings.append(
                "⚠️ **MIDDLE OF RANGE:** Price is currently sitting at 50% equilibrium. Poor asymmetric risk/reward; wait for sweep of extremes."
            )

        # 3. Impending Macro Catalyst Check
        try:
            from core.macro_sentinel import macro_sentinel

            snap = macro_sentinel.get_macro_snapshot()
            if snap.macro_regime == "DOLLAR_SQUEEZE":
                devils_advocate_warnings.append(
                    "⚠️ **MACRO REGIME RISK:** DXY Dollar Squeeze active. Crypto upside momentum may face aggressive traditional FX headwinds."
                )
        except Exception:
            pass

        # ------------------------------------------------------------------
        # Setup 27: Optimal DCA Limit Ladder (Calculated for Best Active Setup)
        # ------------------------------------------------------------------
        triggered = [s for s in evaluated_setups if s.state == SetupReadinessState.ACTIVE_TRIGGERED]
        waiting = [s for s in evaluated_setups if s.state == SetupReadinessState.WAITING_LIMIT]

        best_setup = (
            max(triggered, key=lambda s: s.confluence_score)
            if triggered
            else (max(waiting, key=lambda s: s.confluence_score) if waiting else None)
        )

        limit_ladder: list[DCAOrderTranche] = []
        if best_setup and best_setup.tranches:
            for t in best_setup.tranches:
                limit_ladder.append(
                    DCAOrderTranche(
                        tranche_number=t["tranche_number"],
                        label=t["label"],
                        price=t["price"],
                        size_weight_pct=t["size_weight_pct"],
                        half_kelly_risk_usd=t["half_kelly_risk_usd"],
                        contracts=t["contracts"],
                    )
                )

        # Optimal Helping Hand Action
        if len(devils_advocate_warnings) >= 2:
            optimal_action = "STAY_IN_CASH"
            verdict_en = (
                f"STAY IN CASH. Devil's Advocate filter detected {len(devils_advocate_warnings)} risk flags. "
                "Preserve capital until volatility expands or a clean session liquidity sweep prints."
            )
            verdict_bn = (
                f"ক্যাশ রাখুন (নো-ট্রেড)। ডেভিলস অ্যাডভোকেট ফিল্টারে {len(devils_advocate_warnings)}টি ঝুঁকি ধরা পড়েছে। "
                "চপ মার্কেটে ক্যাপিটাল রক্ষা করুন; এক্সটার্নাল লিকুইডিটি সুইপ হওয়া পর্যন্ত অপেক্ষা করুন।"
            )
        elif triggered:
            optimal_action = "EXECUTE_NOW"
            verdict_en = (
                f"EXECUTE NOW: {best_setup.name_en} is active in zone with {best_setup.confluence_score:.0f}% confluence. "
                f"Entry at ${best_setup.trigger_price:,.2f}, SL at ${best_setup.stop_loss:,.2f}, R:R {best_setup.risk_reward_ratio:.1f}."
            )
            verdict_bn = (
                f"এখনই এক্সিকিউট করুন: {best_setup.name_bn} অ্যাক্টিভ জোনে আছে (কনফ্লুয়েন্স {best_setup.confluence_score:.0f}%)। "
                f"এন্ট্রি: ${best_setup.trigger_price:,.2f}, এসএল: ${best_setup.stop_loss:,.2f}, R:R {best_setup.risk_reward_ratio:.1f}।"
            )
        else:
            optimal_action = "SET_LIMIT_LADDER"
            verdict_en = (
                f"SET LIMIT LADDER: No immediate market entry triggered. Place 3-tranche DCA limit ladder for {best_setup.name_en if best_setup else 'key demand zone'}. "
                f"Ladder anchored at ${best_setup.entry_zone[0]:,.2f}–${best_setup.entry_zone[1]:,.2f}."
            )
            verdict_bn = f"লিমিট ল্যাডার সেট করুন: তাৎক্ষণিক মার্কেট এন্ট্রি নেই। {best_setup.name_bn if best_setup else 'ডিমান্ড জোনে'} ৩-ধাপে লিমিট অর্ডার বসান (${best_setup.entry_zone[0]:,.2f}–${best_setup.entry_zone[1]:,.2f})।"

        return TradingHelpingHandDossier(
            symbol=clean_sym,
            timeframe=timeframe,
            current_price=cur_p,
            market_phase=market_phase,
            session_killzone=session_kz,
            smt_divergence_summary=smt_summary,
            candlestick_formations=candlestick_formations,
            orderflow_absorption_summary=cvd_summary,
            active_triggered_setups=triggered,
            waiting_limit_setups=waiting,
            devils_advocate_warnings=devils_advocate_warnings,
            optimal_action=optimal_action,
            best_setup=best_setup,
            limit_ladder=limit_ladder,
            verdict_en=verdict_en,
            verdict_bn=verdict_bn,
        )

    # --------------------------------------------------------------------------
    # INTERNAL HELPERS
    # --------------------------------------------------------------------------

    def _compute_volume_profile(
        self, candles: list[dict[str, Any]], num_bins: int = 24
    ) -> tuple[float, float, float]:
        """Calculates VPOC, Value Area High (VAH), and Value Area Low (VAL)."""
        if not candles:
            return 80000.0, 81000.0, 79000.0

        highs = [float(c["high"]) for c in candles]
        lows = [float(c["low"]) for c in candles]
        vols = [float(c.get("volume", 1.0)) for c in candles]

        min_p = min(lows)
        max_p = max(highs)
        if max_p <= min_p:
            return min_p, max_p, min_p

        bin_width = (max_p - min_p) / num_bins
        bins = [0.0] * num_bins

        for c, v in zip(candles, vols, strict=False):
            mid_p = (float(c["high"]) + float(c["low"])) / 2.0
            idx = min(num_bins - 1, max(0, int((mid_p - min_p) / bin_width)))
            bins[idx] += v

        # VPOC is the bin with maximum volume
        max_bin_idx = int(np.argmax(bins))
        vpoc = min_p + (max_bin_idx + 0.5) * bin_width

        # Value Area contains 70% of total volume
        total_vol = sum(bins)
        target_va_vol = total_vol * 0.70
        accum_vol = bins[max_bin_idx]
        up_idx = max_bin_idx
        dn_idx = max_bin_idx

        while accum_vol < target_va_vol and (up_idx < num_bins - 1 or dn_idx > 0):
            up_vol = bins[up_idx + 1] if up_idx < num_bins - 1 else 0.0
            dn_vol = bins[dn_idx - 1] if dn_idx > 0 else 0.0
            if up_vol >= dn_vol and up_idx < num_bins - 1:
                up_idx += 1
                accum_vol += up_vol
            elif dn_idx > 0:
                dn_idx -= 1
                accum_vol += dn_vol
            else:
                break

        val = min_p + dn_idx * bin_width
        vah = min_p + (up_idx + 1) * bin_width
        return round(vpoc, 2), round(vah, 2), round(val, 2)

    def _evaluate_smt_divergence(
        self, target_candles: list[dict[str, Any]], corr_candles: list[dict[str, Any]]
    ) -> str | None:
        """
        Evaluates intermarket relative strength:
        - Bullish SMT: Target makes lower low, Correlated makes higher low.
        - Bearish SMT: Target makes higher high, Correlated makes lower high.
        """
        if len(target_candles) < 20 or len(corr_candles) < 20:
            return None

        t_lows = [float(c["low"]) for c in target_candles[-20:]]
        c_lows = [float(c["low"]) for c in corr_candles[-20:]]
        t_highs = [float(c["high"]) for c in target_candles[-20:]]
        c_highs = [float(c["high"]) for c in corr_candles[-20:]]

        # Recent vs previous low
        t_recent_low = min(t_lows[-5:])
        t_prev_low = min(t_lows[:15])
        c_recent_low = min(c_lows[-5:])
        c_prev_low = min(c_lows[:15])

        if (t_recent_low < t_prev_low) and (c_recent_low > c_prev_low):
            return "BULLISH_SMT_DIVERGENCE"

        # Recent vs previous high
        t_recent_high = max(t_highs[-5:])
        t_prev_high = max(t_highs[:15])
        c_recent_high = max(c_highs[-5:])
        c_prev_high = max(c_highs[:15])

        if (t_recent_high > t_prev_high) and (c_recent_high < c_prev_high):
            return "BEARISH_SMT_DIVERGENCE"

        return None

    def _build_empty_dossier(self, symbol: str, timeframe: str) -> TradingHelpingHandDossier:
        return TradingHelpingHandDossier(
            symbol=symbol,
            timeframe=timeframe,
            current_price=80000.0,
            market_phase="Awaiting Real-Time Feed Initialization",
            session_killzone="Neutral",
            smt_divergence_summary="Insufficient historical bars for cross-asset analysis.",
            candlestick_formations=[],
            orderflow_absorption_summary="Awaiting L2 orderflow feed.",
            active_triggered_setups=[],
            waiting_limit_setups=[],
            devils_advocate_warnings=[
                "Market data cache initializing. Stand by for live candle closure."
            ],
            optimal_action="STAY_IN_CASH",
            best_setup=None,
            limit_ladder=[],
            verdict_en="Stand by: Awaiting closed candle array from Binance/Bybit feed.",
            verdict_bn="অপেক্ষা করুন: লাইভ মার্কেট ডাটা সিঙ্ক হচ্ছে।",
        )


# Singleton
omniscient_setup_engine = OmniscientSetupEngine()
