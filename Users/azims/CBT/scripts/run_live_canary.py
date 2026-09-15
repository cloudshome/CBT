#!/usr/bin/env python3
"""
scripts/run_live_canary.py
==========================
Interactive CLI tool for executing real-money micro-notional canary orders ($10 - $25 USD).

Safety & Governance Controls:
1. Microstructure Symbol Feasibility Check (stepSize, minQty, minNotional).
2. Complete 7-Gate Preflight Clearance (including Capital Governor & Withdrawal Prohibition).
3. Hardened 2-Phase Confirmation for LIVE execution:
   - Phase 1: Explicit phrase "EXECUTE LIVE CANARY".
   - Phase 2: Randomly generated 6-digit confirmation code.
4. Monotonic transit and fill timing measuring exchange ACK against 500ms SLA.
5. Automatic ambiguous timeout reconciliation (never blind retry).
"""

from __future__ import annotations

import asyncio
import random
import sys
from pathlib import Path

# Add repo root to python path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.auth.credential_vault import credential_vault  # noqa: E402
from core.execution.live_canary_runner import CanaryRunRequest, live_canary_runner  # noqa: E402
from core.execution.live_gatekeeper import live_gatekeeper  # noqa: E402
from core.execution.symbol_constraints import symbol_constraint_engine  # noqa: E402


def print_banner():
    print("\n" + "╔" + "═" * 60 + "╗")
    print("║   🛡️ CBT LIVE EXCHANGE MICRO-CANARY OPERATOR DESK         ║")
    print("║   Milestone 21.4 / Phase 22 Production Burn-In             ║")
    print("╚" + "═" * 60 + "╝")


async def run_canary_cli():
    print_banner()

    # 1. Exchange Selection
    print("\n[Step 1] Select Exchange Venue:")
    print("  [1] BINANCE (Spot)")
    print("  [2] BYBIT (Spot / Unified)")
    exch_choice = input("Enter choice [1/2, default: 1]: ").strip()
    exchange = "BYBIT" if exch_choice == "2" else "BINANCE"

    # 2. Environment Selection
    print("\n[Step 2] Select Execution Environment:")
    print("  [1] TESTNET (Simulated Network Exchange — Zero Real Capital)")
    print("  [2] PRODUCTION (REAL-MONEY EXCHANGE MATCHING ENGINE)")
    env_choice = input("Enter choice [1/2, default: 1]: ").strip()
    environment = "PRODUCTION" if env_choice == "2" else "TESTNET"

    # 3. Symbol Selection
    print("\n[Step 3] Select Instrument:")
    print("  [1] BTC/USDT")
    print("  [2] ETH/USDT")
    print("  [3] SOL/USDT")
    sym_choice = input("Enter choice [1-3, default: 1]: ").strip()
    if sym_choice == "2":
        symbol = "ETH/USDT"
        ref_price = 3500.0
    elif sym_choice == "3":
        symbol = "SOL/USDT"
        ref_price = 150.0
    else:
        symbol = "BTC/USDT"
        ref_price = 65000.0

    # 4. Order Parameters
    side = "BUY"
    print("\n[Step 4] Micro-Notional Size:")
    print("  Permitted Canary Envelope: $5.00 – $25.00 USD (Target: $10.00)")
    notional_str = input("Enter notional USD [default: 10.0]: ").strip()
    notional = float(notional_str) if notional_str else 10.0

    # 5. Feasibility Evaluation
    feasibility = symbol_constraint_engine.evaluate_order_feasibility(
        exchange=exchange,
        symbol=symbol,
        requested_notional_usd=notional,
        reference_price=ref_price,
    )
    if not feasibility.is_feasible:
        print(f"\n❌ FEASIBILITY REJECTED: {feasibility.rejection_reason}")
        print("Order sizing cannot satisfy exchange filters. Aborting.")
        return

    # 6. Pre-Flight 7-Gate Safety Evaluation
    print(f"\nEvaluating 7-Gate Preflight Clearance for {exchange} [{environment}]...")
    verdict = await live_gatekeeper.evaluate_order_clearance(
        exchange=exchange,
        order_notional_usd=feasibility.final_notional_usd,
        environment=environment,
        strategy_id="STRAT_SMC_INSTITUTIONAL",
        entry_price=feasibility.effective_price,
        stop_loss_price=feasibility.effective_price * 0.985,  # 1.5% SL
    )

    print("\n" + "-" * 62)
    print(" 📋 7-GATE CONSTITUTIONAL PRE-FLIGHT SCORECARD")
    print("-" * 62)
    for check_name, passed in verdict.checks.items():
        icon = "✅" if passed else "❌"
        print(f"  {icon} {check_name:<36}: {'PASSED' if passed else 'BLOCKED'}")
    print("-" * 62)

    if not verdict.passed:
        print("\n❌ PREFLIGHT GATES BLOCKED:")
        for r in verdict.rejection_reasons:
            print(f"  - {r}")
        if environment == "PRODUCTION":
            print("\nAborting. Real capital will NOT be hazarded.")
            return

    # 7. Execution Mode (Dry-Run vs Real-Money)
    print("\n[Step 5] Execution Mode:")
    print("  [1] SAFE DRY-RUN (Simulates execution, tests timing, zero exchange orders)")
    if environment == "PRODUCTION" and verdict.passed:
        print("  [2] LIVE REAL-MONEY EXECUTION (TRANSMITS ORDER TO MATCHING ENGINE)")
        mode_choice = input("Enter choice [1/2, default: 1]: ").strip()
        is_dry_run = mode_choice != "2"
    else:
        print("  (Live execution requires all 7 gates passed in PRODUCTION mode)")
        is_dry_run = True

    # 8. Hardened 2-Phase Confirmation for Real-Money Orders
    if not is_dry_run:
        est_max_loss = round(feasibility.final_notional_usd * 0.015, 2)
        print("\n" + "╔" + "═" * 58 + "╗")
        print("║       🚨 LIVE REAL-MONEY CAPITAL EXECUTION INTENT        ║")
        print("╠" + "═" * 58 + "╣")
        print(f"║ Exchange:       {exchange:<40} ║")
        print(f"║ Environment:    {environment:<40} ║")
        print(f"║ Symbol:         {symbol:<40} ║")
        print(f"║ Side:           {side:<40} ║")
        print(f"║ Final Notional: ${feasibility.final_notional_usd:<39.2f} ║")
        print(f"║ Feasible Qty:   {feasibility.feasible_qty:<40} ║")
        print(f"║ Est Max Loss:   ${est_max_loss:<39.2f} ║")
        print(f"║ Capital Tier:   {'TIER_1_CANARY':<40} ║")
        print(f"║ Withdrawal:     {'DISABLED (CERTIFIED SAFE)':<40} ║")
        print(f"║ Preflight:      {'7/7 ALL GATES CLEARED':<40} ║")
        print("╚" + "═" * 58 + "╝")

        # Phase 1: Explicit confirmation phrase
        print("\n[CONFIRMATION PHASE 1/2]")
        phrase = input("Type 'EXECUTE LIVE CANARY' to proceed: ").strip()
        if phrase != "EXECUTE LIVE CANARY":
            print("❌ Confirmation phrase mismatch. Execution aborted.")
            return

        # Phase 2: Dynamic 6-digit confirmation code
        conf_code = f"{random.randint(100000, 999999)}"
        print("\n[CONFIRMATION PHASE 2/2]")
        print(f"SECURITY CODE: {conf_code}")
        entered_code = input(f"Enter code {conf_code} to authorize order dispatch: ").strip()
        if entered_code != conf_code:
            print("❌ Security code mismatch. Execution aborted.")
            return

    # 9. Execute Canary Order
    print(f"\nDispatching canary order (Dry-Run: {is_dry_run})...")
    req = CanaryRunRequest(
        exchange=exchange,
        symbol=symbol,
        notional_usd=feasibility.final_notional_usd,
        side=side,
        order_type="LIMIT",
        price=feasibility.effective_price,
        stop_loss_price=feasibility.effective_price * 0.985,
        environment=environment,
        is_dry_run=is_dry_run,
        strategy_id="STRAT_SMC_INSTITUTIONAL",
    )

    result = await live_canary_runner.execute_canary_order(req)

    print("\n" + "=" * 62)
    print(f" 🎯 CANARY EXECUTION RECEIPT: {result.status}")
    print("=" * 62)
    print(f"   Execution ID:      {result.canary_execution_id}")
    print(f"   Client Order ID:   {result.client_order_id}")
    print(f"   Exchange Order ID: {result.exchange_order_id or 'N/A'}")
    print(f"   Executed Qty:      {result.executed_qty}")
    print(f"   Executed Price:    ${result.executed_price:.2f}")
    print(f"   Final Notional:    ${result.notional_usd:.2f}")
    print(f"   Dispatch -> ACK:   {result.dispatch_to_ack_latency_ms:.1f}ms {'(✅ <500ms SLA)' if not result.ack_latency_sla_breached else '(⚠️ SLA BREACH)'}")
    print(f"   ACK -> Fill:       {result.ack_to_fill_latency_ms:.1f}ms")
    print(f"   Total Duration:    {result.total_roundtrip_ms:.1f}ms")
    print(f"   Monotonic Timings: {result.dispatch_monotonic_ns}ns -> {result.ack_monotonic_ns}ns -> {result.fill_monotonic_ns}ns")
    print(f"   UTC Dispatch Time: {result.dispatch_wall_time_utc}")
    print(f"   Reconciliation ID: {result.reconciliation_id or 'N/A'}")
    print(f"   Message:           {result.message}")
    print("=" * 62 + "\n")


if __name__ == "__main__":
    asyncio.run(run_canary_cli())
