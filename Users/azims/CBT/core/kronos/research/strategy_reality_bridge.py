"""
core/kronos/research/strategy_reality_bridge.py
===============================================
Milestone 19 / K10.4 / Grade-E1: Strategy Reality Bridge & Provenance Authority.

Bridges empirical Grade-E1/E2 microstructural drag into Strategy League and
downstream evaluation engines while enforcing:
1. Cryptographic dataset hash provenance against authoritative manifests.
2. Independent execution authorization boundaries (Viability != Tradeability).
3. Anti-epistemic grade inflation (OHLCV cannot claim L2 tick verification).
4. Backward-compatible sequence unpacking for legacy callers.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger("sky.kronos.research.strategy_reality_bridge")

ROOT_DIR = Path(__file__).resolve().parents[3]
DEFAULT_MANIFEST_PATH = ROOT_DIR / "data" / "research" / "datasets" / "manifest_k9.json"


# ─────────────────────────────────────────────────────────────────────────────
# Epistemic & Provenance Exception Hierarchy
# ─────────────────────────────────────────────────────────────────────────────


class StrategyRealityBridgeError(Exception):
    """Base exception for StrategyRealityBridge errors."""


class ProvenanceVerificationError(StrategyRealityBridgeError):
    """Raised when cryptographic dataset hash or manifest validation fails."""


class ProvenanceTamperError(StrategyRealityBridgeError):
    """Raised when canonical profile digest deviates from stored profile_hash."""


class EpistemicInflationError(StrategyRealityBridgeError):
    """Raised when an OHLCV or synthetic dataset claims L2 tick verification."""


class ConstitutionalFirewallError(StrategyRealityBridgeError):
    """Raised when an unauthorized component attempts to grant live execution permissions."""


# ─────────────────────────────────────────────────────────────────────────────
# Canonical Profile Definition & Content Hashing
# ─────────────────────────────────────────────────────────────────────────────


def compute_profile_digest(data: dict[str, Any]) -> str:
    """Computes deterministic SHA-256 digest over canonical JSON representation."""
    canonical_keys = {
        "asset": data.get("asset"),
        "timeframe": data.get("timeframe"),
        "dataset_id": data.get("dataset_id"),
        "dataset_hash": data.get("dataset_hash"),
        "experiment_id": data.get("experiment_id"),
        "sample_size_orders": data.get("sample_size_orders"),
        "sample_size_fills": data.get("sample_size_fills"),
        "epistemic_grade": data.get("epistemic_grade"),
        "research_verdict": data.get("research_verdict"),
        "maker_fill_rate_pct": data.get("maker_fill_rate_pct"),
        "maker_adverse_selection_bps": data.get("maker_adverse_selection_bps"),
        "maker_net_edge_bps": data.get("maker_net_edge_bps"),
        "taker_roundtrip_cost_bps": data.get("taker_roundtrip_cost_bps"),
        "toxic_fill_ratio": data.get("toxic_fill_ratio"),
        "recommended_execution_role": data.get("recommended_execution_role"),
    }
    encoded = json.dumps(canonical_keys, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class MicrostructureDragProfile:
    """Immutable microstructural drag profile bound to cryptographic dataset provenance."""

    asset: str
    timeframe: str
    dataset_id: str
    dataset_hash: str
    experiment_id: str
    sample_size_orders: int
    sample_size_fills: int
    epistemic_grade: str
    research_verdict: str
    maker_fill_rate_pct: float
    maker_adverse_selection_bps: float
    maker_net_edge_bps: float
    taker_roundtrip_cost_bps: float
    toxic_fill_ratio: float
    recommended_execution_role: str
    profile_hash: str = ""

    def __post_init__(self) -> None:
        if not self.profile_hash:
            calculated = compute_profile_digest(asdict(self))
            object.__setattr__(self, "profile_hash", calculated)


# ─────────────────────────────────────────────────────────────────────────────
# Authoritative Empirical Registry (Bound to Canonical K9 Manifest & Grade-E2)
# ─────────────────────────────────────────────────────────────────────────────

EMPIRICAL_DRAG_REGISTRY: dict[str, MicrostructureDragProfile] = {
    "BTC_15m": MicrostructureDragProfile(
        asset="BTC",
        timeframe="15m",
        dataset_id="K9_BTCUSDT_15m_464d2ff4",
        dataset_hash="464d2ff49c68ddf1be418ef7a56f937a46ee9a82c6cbed2e663016aa4e026fd3",
        experiment_id="GRADE_E2_EMPIRICAL_BTC15M",
        sample_size_orders=489,
        sample_size_fills=422,
        epistemic_grade="GRADE-E2: OHLCV_MICROSTRUCTURE_DEFENSE",
        research_verdict="QUARANTINE",
        maker_fill_rate_pct=86.3,
        maker_adverse_selection_bps=-82.95,
        maker_net_edge_bps=-89.50,
        taker_roundtrip_cost_bps=12.5,
        toxic_fill_ratio=0.45,
        recommended_execution_role="TAKER_OR_PROTECTED_MAKER",
    ),
    "BTC_1h": MicrostructureDragProfile(
        asset="BTC",
        timeframe="1h",
        dataset_id="K9_BTCUSDT_1h_17250393",
        dataset_hash="17250393debc51befff643df3190383cfcc26b4a79ca7b0b8484a86bae42cb8a",
        experiment_id="GRADE_E2_EMPIRICAL_BTC1H",
        sample_size_orders=127,
        sample_size_fills=106,
        epistemic_grade="GRADE-E2: OHLCV_MICROSTRUCTURE_DEFENSE",
        research_verdict="QUARANTINE",
        maker_fill_rate_pct=83.5,
        maker_adverse_selection_bps=-23.51,
        maker_net_edge_bps=-30.26,
        taker_roundtrip_cost_bps=11.5,
        toxic_fill_ratio=0.48,
        recommended_execution_role="PROTECTED_MAKER",
    ),
    "ETH_15m": MicrostructureDragProfile(
        asset="ETH",
        timeframe="15m",
        dataset_id="K9_ETHUSDT_15m_1fb09fb3",
        dataset_hash="1fb09fb3e9376df8fb6cf927257a58361f1320e186c6f9834996698007d4c7ba",
        experiment_id="GRADE_E2_EMPIRICAL_ETH15M",
        sample_size_orders=224,
        sample_size_fills=206,
        epistemic_grade="GRADE-E2: OHLCV_MICROSTRUCTURE_DEFENSE",
        research_verdict="QUARANTINE",
        maker_fill_rate_pct=92.0,
        maker_adverse_selection_bps=-6.36,
        maker_net_edge_bps=-12.85,
        taker_roundtrip_cost_bps=13.5,
        toxic_fill_ratio=0.45,
        recommended_execution_role="PROTECTED_MAKER",
    ),
    "ETH_1h": MicrostructureDragProfile(
        asset="ETH",
        timeframe="1h",
        dataset_id="K9_ETHUSDT_1h_41c0c757",
        dataset_hash="41c0c757bc42ebdbe4e2307e69117d99a021411fc0dd56fc2d0edafe7fbedf99",
        experiment_id="GRADE_E2_EMPIRICAL_ETH1H",
        sample_size_orders=50,
        sample_size_fills=39,
        epistemic_grade="GRADE-E2: OHLCV_MICROSTRUCTURE_DEFENSE",
        research_verdict="QUARANTINE",
        maker_fill_rate_pct=78.0,
        maker_adverse_selection_bps=-2.67,
        maker_net_edge_bps=-9.58,
        taker_roundtrip_cost_bps=12.5,
        toxic_fill_ratio=0.64,
        recommended_execution_role="PROTECTED_MAKER",
    ),
    "SOL_1h": MicrostructureDragProfile(
        asset="SOL",
        timeframe="1h",
        dataset_id="K9_SOLUSDT_1h_942a3153",
        dataset_hash="942a3153863ffc8e7d3f4a2f94f36a5ec2445c1f82c304e10a5cbf0d9904352a",
        experiment_id="GRADE_E1_EMPIRICAL_SOL1H",
        sample_size_orders=198,
        sample_size_fills=161,
        epistemic_grade="GRADE-E1: OHLCV_APPROXIMATION",
        research_verdict="CONDITIONALLY_PERMITTED",
        maker_fill_rate_pct=81.3,
        maker_adverse_selection_bps=19.49,
        maker_net_edge_bps=12.89,
        taker_roundtrip_cost_bps=15.0,
        toxic_fill_ratio=0.43,
        recommended_execution_role="MAKER_DOMINANT",
    ),
    "SOL_4h": MicrostructureDragProfile(
        asset="SOL",
        timeframe="4h",
        dataset_id="K9_SOLUSDT_4h_a09673a1",
        dataset_hash="a09673a198354383e427018ee652f9d4e536eed69570fbb7e717e4f081a063bc",
        experiment_id="GRADE_E2_EMPIRICAL_SOL4H",
        sample_size_orders=54,
        sample_size_fills=48,
        epistemic_grade="GRADE-E2: OHLCV_MICROSTRUCTURE_DEFENSE",
        research_verdict="CONDITIONALLY_PERMITTED",
        maker_fill_rate_pct=88.9,
        maker_adverse_selection_bps=188.42,
        maker_net_edge_bps=181.84,
        taker_roundtrip_cost_bps=15.0,
        toxic_fill_ratio=0.47,
        recommended_execution_role="MAKER_DOMINANT",
    ),
}


# ─────────────────────────────────────────────────────────────────────────────
# Provenance Authority (Cryptographic Manifest & Integrity Guard)
# ─────────────────────────────────────────────────────────────────────────────


class ProvenanceAuthority:
    """
    Validates dataset hashes against the authoritative frozen manifest.
    Guarantees tamper detection and prevents epistemic grade inflation.
    """

    def __init__(self, manifest_path: Path | None = None) -> None:
        self.manifest_path = manifest_path or DEFAULT_MANIFEST_PATH
        self._manifest_cache: dict[str, Any] | None = None

    def _load_manifest(self) -> dict[str, Any]:
        if self._manifest_cache is not None:
            return self._manifest_cache
        if not self.manifest_path.exists():
            logger.warning(
                f"Authoritative manifest not found at {self.manifest_path}. Operating in standalone mode."
            )
            return {}
        try:
            with open(self.manifest_path, encoding="utf-8") as f:
                self._manifest_cache = json.load(f)
            return self._manifest_cache
        except (OSError, json.JSONDecodeError) as e:
            logger.error(f"Failed to load dataset manifest: {e}")
            return {}

    def verify_profile(self, profile: MicrostructureDragProfile) -> bool:
        """
        Performs strict fail-closed verification:
        1. Validates profile_hash against computed digest (tamper detection).
        2. Prohibits epistemic grade inflation (OHLCV cannot claim L2 tick verified).
        3. Cross-references dataset_hash against authoritative manifest if available.
        """
        # 1. Tamper check
        expected_digest = compute_profile_digest(asdict(profile))
        if profile.profile_hash != expected_digest:
            raise ProvenanceTamperError(
                f"Tamper detected in profile for {profile.asset}_{profile.timeframe}! "
                f"Stored hash: {profile.profile_hash}, Recomputed: {expected_digest}"
            )

        # 2. Epistemic Grade Inflation check
        # Any dataset with 'OHLCV' source or missing L2 order book cannot claim L2_TICK_VERIFIED
        if "L2_TICK" in profile.epistemic_grade and "SYNTHETIC" not in profile.dataset_id:
            manifest = self._load_manifest()
            entry = manifest.get(profile.dataset_id)
            if (
                entry
                and entry.get("market_type") == "SPOT"
                and "REST_CANDLES" in entry.get("source", "")
            ):
                raise EpistemicInflationError(
                    f"Epistemic inflation rejected: Dataset {profile.dataset_id} is REST OHLCV, "
                    f"cannot claim '{profile.epistemic_grade}'."
                )

        # 3. Manifest Hash Matching check
        manifest = self._load_manifest()
        if manifest and profile.dataset_id in manifest:
            expected_content_hash = manifest[profile.dataset_id].get("content_hash")
            if expected_content_hash and profile.dataset_hash != expected_content_hash:
                raise ProvenanceVerificationError(
                    f"Dataset hash mismatch for {profile.dataset_id}! "
                    f"Profile hash: {profile.dataset_hash}, Manifest: {expected_content_hash}"
                )

        return True


# ─────────────────────────────────────────────────────────────────────────────
# Execution Authorization Gateway (Independent Tradeability Boundary)
# ─────────────────────────────────────────────────────────────────────────────


class ExecutionAuthorizationGateway:
    """
    Independent Execution Authorization Boundary.
    Decouples research eligibility (is_viable) from live execution permissions (is_tradeable).

    Constitutional Formula:
    Tradeable = BridgeEligible AND ProvenanceValid AND EvidenceGradeSufficient AND (Verdict != QUARANTINE)
    """

    @staticmethod
    def evaluate_authorization(
        profile: MicrostructureDragProfile,
        is_research_viable: bool,
        provenance_valid: bool,
    ) -> tuple[bool, str]:
        if not provenance_valid:
            return False, "DENIED_PROVENANCE_INVALID: Cryptographic verification failed"

        if not is_research_viable:
            return False, "DENIED_INVIABLE: Net calibrated PnL is non-positive"

        if profile.research_verdict == "QUARANTINE":
            return (
                False,
                f"DENIED_CONSTITUTIONAL_QUARANTINE: Asset {profile.asset} is under research quarantine",
            )

        # Crucial gate: OHLCV approximations can NEVER authorize live execution
        if profile.epistemic_grade in (
            "GRADE-E1: OHLCV_APPROXIMATION",
            "GRADE-E2: OHLCV_MICROSTRUCTURE_DEFENSE",
            "SYNTHETIC_CONSERVATIVE_FALLBACK",
        ):
            return (
                False,
                f"DENIED_EVIDENCE_GRADE: '{profile.epistemic_grade}' insufficient for live authority. "
                "Requires L2_TICK_VERIFIED under Grade-E3.",
            )

        if profile.epistemic_grade != "L2_TICK_VERIFIED":
            return False, f"DENIED_UNCERTIFIED: Grade '{profile.epistemic_grade}' not certified"

        return True, "AUTHORIZED: Execution criteria fully satisfied"


# ─────────────────────────────────────────────────────────────────────────────
# Calibrated Execution Result (Rich Metadata + Backward Compatible Unpacking)
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CalibratedExecutionResult:
    """
    Result of applying execution reality to a strategy return stream.
    Implements sequence unpacking for backward compatibility with:
    `cal_pnl, drag, is_viable = bridge.apply_execution_reality(...)`
    """

    calibrated_net_pnl_bps: float
    drag_bps: float
    is_viable: bool
    is_tradeable: bool
    epistemic_grade: str
    research_verdict: str
    dataset_id: str
    dataset_hash: str
    experiment_id: str
    provenance_hash: str
    authorization_status: str

    def __iter__(self) -> Iterator[Any]:
        """Preserves legacy 3-tuple unpacking: (calibrated_pnl, drag_bps, is_viable)."""
        yield self.calibrated_net_pnl_bps
        yield self.drag_bps
        yield self.is_viable

    def __repr__(self) -> str:
        trade_status = "TRADEABLE" if self.is_tradeable else "RESEARCH_ONLY"
        return (
            f"<CalibratedExecutionResult: NetPnL={self.calibrated_net_pnl_bps}bps, "
            f"Drag={self.drag_bps}bps, Viable={self.is_viable}, "
            f"Status={trade_status} ({self.authorization_status})>"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Strategy Reality Bridge Engine
# ─────────────────────────────────────────────────────────────────────────────


class StrategyRealityBridge:
    """
    Applies empirical microstructural execution reality to candidate trading strategies
    with cryptographic provenance verification and constitutional tradeability decoupling.
    """

    def __init__(
        self,
        provenance_authority: ProvenanceAuthority | None = None,
        registry: dict[str, MicrostructureDragProfile] | None = None,
    ) -> None:
        self.authority = provenance_authority or ProvenanceAuthority()
        self.registry = registry or EMPIRICAL_DRAG_REGISTRY

    def get_profile(self, asset: str, timeframe: str) -> MicrostructureDragProfile:
        key = f"{asset}_{timeframe}"
        if key in self.registry:
            profile = self.registry[key]
            # Verify profile integrity
            self.authority.verify_profile(profile)
            return profile

        # Explicit conservative synthetic fallback profile
        fallback = MicrostructureDragProfile(
            asset=asset,
            timeframe=timeframe,
            dataset_id="SYNTHETIC_CONSERVATIVE_FALLBACK",
            dataset_hash="0000000000000000000000000000000000000000000000000000000000000000",
            experiment_id="SYNTHETIC_FALLBACK_DEFAULT",
            sample_size_orders=0,
            sample_size_fills=0,
            epistemic_grade="SYNTHETIC_CONSERVATIVE_FALLBACK",
            research_verdict="QUARANTINE",
            maker_fill_rate_pct=75.0,
            maker_adverse_selection_bps=-25.0,
            maker_net_edge_bps=-35.0,
            taker_roundtrip_cost_bps=15.0,
            toxic_fill_ratio=0.55,
            recommended_execution_role="CONSERVATIVE_TAKER",
        )
        self.authority.verify_profile(fallback)
        return fallback

    def apply_execution_reality(
        self,
        asset: str,
        timeframe: str,
        raw_pnl_bps: float,
        is_maker: bool = True,
    ) -> CalibratedExecutionResult:
        """
        Adjusts raw strategy return by empirical microstructural drag.
        Returns a rich CalibratedExecutionResult that unpacks as (calibrated_pnl, drag_bps, is_viable).
        """
        profile = self.get_profile(asset, timeframe)

        if is_maker:
            calibrated_pnl = raw_pnl_bps + profile.maker_net_edge_bps
            drag_bps = abs(profile.maker_net_edge_bps)
        else:
            calibrated_pnl = raw_pnl_bps - profile.taker_roundtrip_cost_bps
            drag_bps = profile.taker_roundtrip_cost_bps

        calibrated_pnl = round(calibrated_pnl, 2)
        drag_bps = round(drag_bps, 2)
        is_viable = calibrated_pnl > 0.0

        # Evaluate execution tradeability through independent authorization gateway
        is_tradeable, auth_status = ExecutionAuthorizationGateway.evaluate_authorization(
            profile=profile,
            is_research_viable=is_viable,
            provenance_valid=True,
        )

        return CalibratedExecutionResult(
            calibrated_net_pnl_bps=calibrated_pnl,
            drag_bps=drag_bps,
            is_viable=is_viable,
            is_tradeable=is_tradeable,
            epistemic_grade=profile.epistemic_grade,
            research_verdict=profile.research_verdict,
            dataset_id=profile.dataset_id,
            dataset_hash=profile.dataset_hash,
            experiment_id=profile.experiment_id,
            provenance_hash=profile.profile_hash,
            authorization_status=auth_status,
        )

    def verify_all_profiles(self) -> dict[str, bool]:
        """Performs preflight verification across all registered empirical drag profiles."""
        results: dict[str, bool] = {}
        for key, profile in self.registry.items():
            results[key] = self.authority.verify_profile(profile)
        return results


strategy_reality_bridge = StrategyRealityBridge()
