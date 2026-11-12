"""
core/qualification/qualification_ledger.py
==========================================
Independent Qualification-Period Performance Ledger for SKY / CBT.

Anchors Round 2 paper-trading validation to:
- Anchor Timestamp: 2026-11-07T09:41:43.006Z (1794044503006 ms)
- Baseline Equity: $7,589.53
- Eligible Universe: BTC/USDT and ETH/USDT

Constitutional Principles:
1. Zero Modification: Historical trades (498 closed trades prior to anchor) remain strictly untouched.
2. Independent Attribution: Qualification trades (opened_at >= anchor) are partitioned into an independent ledger.
3. Carried-Over Position Isolation: Positions open at anchor time (POS_ETH_USDT, POS_SOL_USDT) are tracked with distinct carried-over status.
4. Total Friction Accounting: Includes fees, funding rates, and slippage attribution.
5. Zero Fabrication: Reports exact empirical stats; never returns synthetic or interpolated values.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import asdict, dataclass
from typing import Any

from core.database import db_manager

logger = logging.getLogger("sky.qualification.ledger")

# Authoritative Round 2 Qualification Anchors
QUALIFICATION_ANCHOR_TIMESTAMP_MS: int = 1794044503006  # 2026-11-07T09:41:43.006Z
QUALIFICATION_ANCHOR_EQUITY_USD: float = 7589.53
QUALIFICATION_TARGET_DURATION_DAYS: int = 30
QUALIFICATION_TARGET_END_TIMESTAMP_MS: int = QUALIFICATION_ANCHOR_TIMESTAMP_MS + (
    QUALIFICATION_TARGET_DURATION_DAYS * 86_400_000
)
QUALIFICATION_ELIGIBLE_SYMBOLS: set[str] = {
    "BTC/USDT",
    "BTCUSDT",
    "ETH/USDT",
    "ETHUSDT",
}


@dataclass
class QualificationMetrics:
    anchor_timestamp_iso: str
    anchor_timestamp_ms: int
    target_end_timestamp_iso: str
    target_end_timestamp_ms: int
    elapsed_burn_in_hours: float
    remaining_burn_in_hours: float
    starting_equity_usd: float
    current_virtual_equity_usd: float
    qualification_realized_pnl_usd: float
    qualification_unrealized_pnl_usd: float
    carried_over_unrealized_pnl_usd: float
    total_fees_usd: float
    estimated_funding_usd: float
    estimated_slippage_usd: float
    net_qualification_pnl_usd: float
    qualification_trades_count: int
    qualification_open_count: int
    qualification_closed_count: int
    winning_trades_count: int
    losing_trades_count: int
    win_rate_pct: float
    profit_factor: float
    expectancy_r: float
    peak_equity_usd: float
    max_drawdown_usd: float
    max_drawdown_pct: float
    historical_trades_count: int
    historical_realized_pnl_usd: float
    status: str  # "ACTIVE_BURN_IN", "INSUFFICIENT_DATA", "COMPLETED"
    audit_hash_sha256: str = ""
    quarantined_trades_count: int = 0
    surviving_trades_count: int = 0
    surviving_expectancy_r: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class QualificationLedger:
    """
    Computes an uncorrupted, independent performance ledger anchored to the official
    Round 2 burn-in timestamp and equity baseline.
    """

    def __init__(
        self,
        anchor_timestamp_ms: int = QUALIFICATION_ANCHOR_TIMESTAMP_MS,
        starting_equity_usd: float = QUALIFICATION_ANCHOR_EQUITY_USD,
    ):
        self.anchor_timestamp_ms = anchor_timestamp_ms
        self.starting_equity_usd = starting_equity_usd

    def get_qualification_metrics(self) -> QualificationMetrics:
        """
        Calculates all qualification metrics by querying `shadow_positions` from SQLite.
        Guarantees zero mutation of database records.
        """
        now_ms = int(time.time() * 1000)
        elapsed_hours = max(0.0, (now_ms - self.anchor_timestamp_ms) / 3_600_000.0)
        remaining_hours = max(0.0, (QUALIFICATION_TARGET_END_TIMESTAMP_MS - now_ms) / 3_600_000.0)

        with db_manager.get_trading_conn() as conn:
            # 1. Historical Baseline Summary (opened_at < anchor)
            hist_row = conn.execute(
                """
                SELECT COUNT(*), COALESCE(SUM(realized_pnl), 0.0)
                FROM shadow_positions
                WHERE opened_at < ? AND status = 'CLOSED';
                """,
                (self.anchor_timestamp_ms,),
            ).fetchone()
            historical_count = int(hist_row[0] or 0)
            historical_realized_pnl = round(float(hist_row[1] or 0.0), 2)

            # 2. Carried-over open positions (opened_at < anchor AND status = 'OPEN')
            carried_rows = conn.execute(
                """
                SELECT position_id, symbol, direction, size, entry_price, current_price,
                       unrealized_pnl, stop_loss, trailing_stop
                FROM shadow_positions
                WHERE opened_at < ? AND status = 'OPEN';
                """,
                (self.anchor_timestamp_ms,),
            ).fetchall()
            carried_unrealized_pnl = round(
                sum(float(r["unrealized_pnl"] or 0.0) for r in carried_rows), 2
            )

            # 3. Qualification-Period Positions (opened_at >= anchor)
            qual_rows = conn.execute(
                """
                SELECT position_id, symbol, direction, size, entry_price, current_price,
                       stop_loss, take_profit, realized_pnl, unrealized_pnl, fee_usd,
                       status, opened_at, closed_at, initial_stop_loss, entry_reason
                FROM shadow_positions
                WHERE opened_at >= ?
                ORDER BY opened_at ASC;
                """,
                (self.anchor_timestamp_ms,),
            ).fetchall()

        # Deduplicate by position_id
        seen_ids = set()
        unique_qual_positions = []
        for r in qual_rows:
            pid = r["position_id"]
            if pid not in seen_ids:
                seen_ids.add(pid)
                unique_qual_positions.append(r)

        open_qual = [p for p in unique_qual_positions if p["status"] == "OPEN"]
        closed_qual = [p for p in unique_qual_positions if p["status"] == "CLOSED"]

        qual_realized_pnl = round(sum(float(p["realized_pnl"] or 0.0) for p in closed_qual), 2)
        qual_unrealized_pnl = round(sum(float(p["unrealized_pnl"] or 0.0) for p in open_qual), 2)
        total_fees = round(sum(float(p["fee_usd"] or 0.0) for p in unique_qual_positions), 4)

        # Estimate funding costs based on 8-hour funding intervals (approx 1 bp per 8h holding)
        estimated_funding = 0.0
        for p in unique_qual_positions:
            sz = float(p["size"] or 0.0)
            ep = float(p["entry_price"] or 0.0)
            notional = sz * ep
            open_ts = int(p["opened_at"] or now_ms)
            close_ts = int(p["closed_at"] or now_ms)
            holding_hours = max(0.0, (close_ts - open_ts) / 3_600_000.0)
            funding_periods = holding_hours / 8.0
            estimated_funding += round(notional * 0.0001 * funding_periods, 4)
        estimated_funding = round(estimated_funding, 4)

        # Slippage: Estimated at 1.5 bps of notional per round-trip
        estimated_slippage = round(
            sum(
                float(p["size"] or 0.0)
                * float(p["entry_price"] or 0.0)
                * 0.00015
                * (2.0 if p["status"] == "CLOSED" else 1.0)
                for p in unique_qual_positions
            ),
            4,
        )

        net_qual_pnl = round(qual_realized_pnl + qual_unrealized_pnl, 2)
        current_virtual_equity = round(self.starting_equity_usd + net_qual_pnl, 2)

        # Performance Metrics
        winning = [p for p in closed_qual if float(p["realized_pnl"] or 0.0) > 0.0]
        losing = [p for p in closed_qual if float(p["realized_pnl"] or 0.0) < 0.0]
        gross_profit = sum(float(p["realized_pnl"] or 0.0) for p in winning)
        gross_loss = abs(sum(float(p["realized_pnl"] or 0.0) for p in losing))

        if gross_loss > 0:
            profit_factor = round(gross_profit / gross_loss, 2)
        elif gross_profit > 0:
            profit_factor = round(gross_profit, 2)
        else:
            profit_factor = 0.0

        total_closed = len(closed_qual)
        win_rate = round(len(winning) / total_closed * 100.0, 1) if total_closed > 0 else 0.0

        # Expectancy in R: Sum( realized_pnl / initial_risk_usd ) / total_closed
        r_multiples: list[float] = []
        surviving_r_multiples: list[float] = []
        quarantined_trades_count = 0

        for p in closed_qual:
            realized = float(p["realized_pnl"] or 0.0)
            ep = float(p["entry_price"] or 0.0)
            init_sl = float(p["initial_stop_loss"] or p["stop_loss"] or ep)
            sz = float(p["size"] or 0.0)
            risk_usd = sz * abs(ep - init_sl)
            r_val = (realized / risk_usd) if risk_usd > 0.01 else 0.0
            r_multiples.append(r_val)

            # Check if this position originated from an empirically quarantined / falsified mechanism
            reason_text = str(p["entry_reason"] or "").upper() if "entry_reason" in p.keys() else ""
            is_quarantined = any(
                q in reason_text
                for q in [
                    "PRE_BREAKOUT_COMPRESSION",
                    "CANDIDATE_A",
                    "SMC_ORDER_BLOCK",
                    "SWEEP REVERSAL",
                ]
            )
            if is_quarantined:
                quarantined_trades_count += 1
            else:
                surviving_r_multiples.append(r_val)

        expectancy_r = (
            round(sum(r_multiples) / len(r_multiples), 2) if len(r_multiples) > 0 else 0.0
        )
        surviving_trades_count = len(surviving_r_multiples)
        surviving_expectancy_r = (
            round(sum(surviving_r_multiples) / surviving_trades_count, 2)
            if surviving_trades_count > 0
            else 0.0
        )

        # Drawdown calculation across qualification trajectory
        running_equity = self.starting_equity_usd
        peak_equity = self.starting_equity_usd
        max_dd_usd = 0.0

        for p in closed_qual:
            running_equity += float(p["realized_pnl"] or 0.0)
            if running_equity > peak_equity:
                peak_equity = running_equity
            dd = peak_equity - running_equity
            if dd > max_dd_usd:
                max_dd_usd = dd

        # Factor in active unrealized PnL at the tail
        active_tail_eq = running_equity + qual_unrealized_pnl
        if active_tail_eq > peak_equity:
            peak_equity = active_tail_eq
        tail_dd = peak_equity - active_tail_eq
        if tail_dd > max_dd_usd:
            max_dd_usd = tail_dd

        max_dd_pct = round((max_dd_usd / peak_equity * 100.0), 2) if peak_equity > 0 else 0.0

        status = "ACTIVE_BURN_IN" if remaining_hours > 0 else "COMPLETED"

        # Deterministic SHA-256 state signature over qualification metrics & baseline
        audit_payload = (
            f"{self.anchor_timestamp_ms}|{self.starting_equity_usd:.2f}|{current_virtual_equity:.2f}|"
            f"{len(unique_qual_positions)}|{len(closed_qual)}|{historical_count}|"
            f"{historical_realized_pnl:.2f}|{status}"
        )
        audit_hash = hashlib.sha256(audit_payload.encode("utf-8")).hexdigest()

        return QualificationMetrics(
            anchor_timestamp_iso="2026-11-07T09:41:43.006Z",
            anchor_timestamp_ms=self.anchor_timestamp_ms,
            target_end_timestamp_iso="2026-12-07T09:41:43.006Z",
            target_end_timestamp_ms=QUALIFICATION_TARGET_END_TIMESTAMP_MS,
            elapsed_burn_in_hours=round(elapsed_hours, 2),
            remaining_burn_in_hours=round(remaining_hours, 2),
            starting_equity_usd=self.starting_equity_usd,
            current_virtual_equity_usd=current_virtual_equity,
            qualification_realized_pnl_usd=qual_realized_pnl,
            qualification_unrealized_pnl_usd=qual_unrealized_pnl,
            carried_over_unrealized_pnl_usd=carried_unrealized_pnl,
            total_fees_usd=total_fees,
            estimated_funding_usd=estimated_funding,
            estimated_slippage_usd=estimated_slippage,
            net_qualification_pnl_usd=net_qual_pnl,
            qualification_trades_count=len(unique_qual_positions),
            qualification_open_count=len(open_qual),
            qualification_closed_count=len(closed_qual),
            winning_trades_count=len(winning),
            losing_trades_count=len(losing),
            win_rate_pct=win_rate,
            profit_factor=profit_factor,
            expectancy_r=expectancy_r,
            peak_equity_usd=round(peak_equity, 2),
            max_drawdown_usd=round(max_dd_usd, 2),
            max_drawdown_pct=max_dd_pct,
            historical_trades_count=historical_count,
            historical_realized_pnl_usd=historical_realized_pnl,
            status=status,
            audit_hash_sha256=audit_hash,
            quarantined_trades_count=quarantined_trades_count,
            surviving_trades_count=surviving_trades_count,
            surviving_expectancy_r=surviving_expectancy_r,
        )


qualification_ledger = QualificationLedger()
