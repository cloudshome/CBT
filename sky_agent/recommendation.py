"""sky_agent.recommendation — evidence-backed suggestion builder.

Outputs: WATCH / WAIT / CONSIDER / AVOID (never BUY NOW) with explicit
FACT vs INTERPRETATION vs HYPOTHESIS tags and an invalidation condition.
Reuses SKY's desk report shape where possible.
"""

from __future__ import annotations

from typing import Any

RECOMMENDATIONS = ("WATCH", "WAIT", "CONSIDER", "AVOID")
CONFIDENCE_LEVELS = ("LOW", "MEDIUM", "HIGH")
RISK_STATUS = ("PASS", "FAIL", "UNKNOWN")


def build_recommendation(
    *,
    asset: str,
    timeframe: str,
    regime: str,
    detected: str,
    evidence: list[str],
    expectancy_R: float | None,
    sample_n: int | None,
    risk_status: str,
    confidence: str,
    kind: str = "HYPOTHESIS",
    invalidation: str = "",
    sources: list[str] | None = None,
) -> dict[str, Any]:
    """Build the canonical suggestion payload (plain dict, JSON-serialisable)."""
    if risk_status not in RISK_STATUS:
        risk_status = "UNKNOWN"
    if confidence not in CONFIDENCE_LEVELS:
        confidence = "LOW"

    # Decision rule: positive expectancy + PASS + sufficient sample → CONSIDER; otherwise WATCH/WAIT/AVOID
    if risk_status == "FAIL":
        rec = "AVOID"
    elif (
        expectancy_R is not None
        and expectancy_R > 0.2
        and (sample_n or 0) >= 100
        and risk_status == "PASS"
    ):
        rec = "CONSIDER"
    elif expectancy_R is not None and expectancy_R <= 0:
        rec = "AVOID"
    elif regime in ("RANGING", "LIQUIDITY_TRAP_CHOP"):
        rec = "WAIT"
    else:
        rec = "WATCH"

    return {
        "asset": asset,
        "timeframe": timeframe,
        "regime": regime,
        "detected": detected,
        "evidence": evidence,
        "expectancy_R": expectancy_R,
        "sample_n": sample_n,
        "risk_status": risk_status,
        "confidence": confidence,
        "kind": kind,  # FACT / INTERPRETATION / HYPOTHESIS
        "recommendation": rec,
        "reason": "; ".join(evidence)[:500] if evidence else "",
        "invalidation": invalidation,
        "sources": sources or [],
    }


def format_alert(rec: dict[str, Any]) -> str:
    """Human-readable alert block for Telegram/Discord."""
    lines = [
        "SKY ALERT",
        "",
        f"Asset: {rec.get('asset')}  Timeframe: {rec.get('timeframe')}",
        f"Regime: {rec.get('regime')}",
        f"Detected: {rec.get('detected')}",
        "",
        "Evidence:",
    ]
    for e in rec.get("evidence", [])[:6]:
        lines.append(f"  • {e}")
    lines += [
        f"Expectancy: {rec.get('expectancy_R')}R  Sample: N={rec.get('sample_n')}",
        f"Risk: {rec.get('risk_status')}  Confidence: {rec.get('confidence')}  Kind: {rec.get('kind')}",
        f"Recommendation: {rec.get('recommendation')}",
        f"Reason: {rec.get('reason')}",
        f"Invalidation: {rec.get('invalidation')}",
        f"Sources: {', '.join(rec.get('sources', [])[:3])}",
    ]
    return "\n".join(lines)
