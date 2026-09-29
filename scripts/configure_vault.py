#!/usr/bin/env python3
"""
scripts/configure_vault.py
==========================
Interactive CLI utility to securely manage exchange credentials in the CBT AES-256-GCM Vault:
1. Store / Update credentials (AES-256-GCM AEAD encrypted)
2. Multi-tier verification probe (connectivity -> auth -> positive withdrawal prohibition)
3. List configured credentials (strictly masked)
4. Revoke credential (immediate database, capability cache, and connector session flush)

Security Invariants:
- Inputs are masked via getpass. Plaintext keys are never echoed or written to disk.
- Withdrawal permissions must be positively verified as DISABLED.
"""

from __future__ import annotations

import asyncio
import getpass
import sys
from pathlib import Path

# Add repo root to python path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.auth.credential_vault import (  # noqa: E402
    ExchangeCredential,
    credential_vault,
    mask_secret,
)


def print_banner():
    print("\n" + "=" * 68)
    print(" 🔐 CBT CRYPTO BRAIN TERMINAL — AES-256 CREDENTIAL SECURITY DESK")
    print("=" * 68)


def store_credential_flow():
    print("\n--- [1] STORE / UPDATE EXCHANGE CREDENTIAL ---")
    print("Select Exchange:")
    print("  [1] BINANCE (Spot & Margin)")
    print("  [2] BYBIT (Linear Perpetuals & Unified)")
    choice_exch = input("Enter selection [1/2, default: 1]: ").strip()
    exchange = "BYBIT" if choice_exch == "2" else "BINANCE"

    print("\nSelect Environment:")
    print("  [1] TESTNET (Simulated Demo Trading — Zero Real Money)")
    print("  [2] PRODUCTION (Live Exchange Trading)")
    choice_env = input("Enter selection [1/2, default: 1]: ").strip()
    environment = "PRODUCTION" if choice_env == "2" else "TESTNET"

    print(f"\nConfiguring {exchange} [{environment}]:")

    api_key = getpass.getpass("Enter API Key (input hidden, paste & press Enter): ").strip()
    if not api_key:
        print("❌ Error: API Key cannot be empty.")
        return

    api_secret = getpass.getpass("Enter Secret Key (input hidden, paste & press Enter): ").strip()
    if not api_secret:
        print("❌ Error: Secret Key cannot be empty.")
        return

    passphrase = None
    if exchange == "BYBIT" or "y" in input("Optional: Does this key require an API Passphrase? (y/N): ").lower():
        passphrase_input = getpass.getpass("Enter Passphrase (optional, or press Enter to skip): ").strip()
        if passphrase_input:
            passphrase = passphrase_input

    try:
        cred = ExchangeCredential(
            exchange=exchange,
            environment=environment,
            api_key=api_key,
            api_secret=api_secret,
            passphrase=passphrase,
            is_active=True,
        )
        credential_vault.store_credential(cred)

        print("\n" + "—" * 68)
        print("✅ SUCCESS: Credential successfully encrypted with AES-256-GCM!")
        print(f"   Exchange:    {exchange}")
        print(f"   Environment: {environment}")
        print(f"   Masked Key:  {mask_secret(api_key)}")
        print(f"   Has Secret:  {'YES (AES-256 Encrypted)' if api_secret else 'NO'}")
        print("   Status:      ACTIVE")
        print("—" * 68)

        # Prompt for immediate verification probe
        probe_choice = input("\nRun live permission probe now to verify withdrawal prohibition? [Y/n]: ").strip().lower()
        if probe_choice in ("", "y", "yes"):
            verify_credential_flow(exchange, environment)

    except Exception as exc:  # noqa: BLE001
        print(f"\n❌ Failed to store credential in vault: {exc}")


def verify_credential_flow(default_exchange: str | None = None, default_env: str | None = None):
    print("\n--- [2] MULTI-TIER CREDENTIAL VERIFICATION PROBE ---")
    if not default_exchange:
        print("Select Exchange:")
        print("  [1] BINANCE")
        print("  [2] BYBIT")
        choice_exch = input("Enter selection [1/2, default: 1]: ").strip()
        exchange = "BYBIT" if choice_exch == "2" else "BINANCE"
    else:
        exchange = default_exchange

    if not default_env:
        print("Select Environment:")
        print("  [1] TESTNET")
        print("  [2] PRODUCTION")
        choice_env = input("Enter selection [1/2, default: 1]: ").strip()
        environment = "PRODUCTION" if choice_env == "2" else "TESTNET"
    else:
        environment = default_env

    print(f"\nDispatching multi-tier probe for {exchange} [{environment}]...")
    try:
        res = asyncio.run(credential_vault.verify_credential_connectivity(exchange, environment))

        print("\n" + "—" * 68)
        print(f" 🔍 PROBE REPORT: {exchange} [{environment}]")
        print("—" * 68)
        print(f"   API Key:            {res.masked_api_key}")
        print(f"   Authentication:     {'✅ PASSED' if res.authenticated else '❌ FAILED'}")
        print(f"   Spot Trading:       {'✅ ENABLED' if res.trading_enabled else '❌ DISABLED'}")
        print(f"   Withdrawals:        {'🛡️ DISABLED (SAFE)' if not res.withdrawal_enabled else '🚨 ENABLED (SECURITY VIOLATION)'}")
        print(f"   Ping Latency:       {res.connectivity_latency_ms:.1f}ms")
        print(f"   Account Latency:    {res.account_latency_ms:.1f}ms")
        print(f"   Permission Latency: {res.permission_latency_ms:.1f}ms")
        print(f"   Total Round-Trip:   {res.total_latency_ms:.1f}ms")
        print(f"   Overall Verdict:    {res.status}")
        print(f"   Details:            {res.message}")
        print("—" * 68)

        if res.status == "PASS":
            print("✅ KEY CERTIFIED FOR LIVE MICRO-CANARY EXECUTION.\n")
        else:
            print(f"⚠️ KEY NOT ELIGIBLE FOR LIVE TRADING: {res.message}\n")

    except Exception as exc:  # noqa: BLE001
        print(f"❌ Probe execution error: {exc}")


def list_credentials_flow():
    print("\n--- [3] CONFIGURED VAULT CREDENTIALS (MASKED) ---")
    creds = credential_vault.list_credentials()
    if not creds:
        print("No exchange credentials found in vault.")
        return

    print(f"{'EXCHANGE':<12} {'ENVIRONMENT':<12} {'MASKED KEY':<20} {'SECRET':<10} {'STATUS':<10}")
    print("-" * 68)
    for c in creds:
        has_sec = "YES" if c.get("has_secret") else "NO"
        stat = "ACTIVE" if c.get("is_active") else "INACTIVE"
        print(f"{c['exchange']:<12} {c['environment']:<12} {c['masked_api_key']:<20} {has_sec:<10} {stat:<10}")
    print("-" * 68)


def revoke_credential_flow():
    print("\n--- [4] REVOKE / DELETE CREDENTIAL ---")
    print("Select Exchange:")
    print("  [1] BINANCE")
    print("  [2] BYBIT")
    choice_exch = input("Enter selection [1/2, default: 1]: ").strip()
    exchange = "BYBIT" if choice_exch == "2" else "BINANCE"

    print("Select Environment:")
    print("  [1] TESTNET")
    print("  [2] PRODUCTION")
    choice_env = input("Enter selection [1/2, default: 1]: ").strip()
    environment = "PRODUCTION" if choice_env == "2" else "TESTNET"

    confirm = input(f"Are you sure you want to REVOKE credentials for {exchange} [{environment}]? (yes/NO): ").strip().lower()
    if confirm == "yes":
        deleted = credential_vault.revoke_credential(exchange, environment)
        if deleted:
            print(f"✅ SUCCESS: Credential for {exchange} [{environment}] revoked. Capability caches flushed.")
        else:
            print(f"ℹ️ No credential found for {exchange} [{environment}].")
    else:
        print("Revocation cancelled.")


def main():
    while True:
        print_banner()
        print("Select Action:")
        print("  [1] Store / Update API Credential (AES-256-GCM)")
        print("  [2] Verify Credential Connectivity & Withdrawal Prohibition")
        print("  [3] List Configured Credentials (Masked)")
        print("  [4] Revoke / Delete Credential")
        print("  [5] Exit")
        choice = input("\nEnter choice [1-5]: ").strip()

        if choice == "1":
            store_credential_flow()
        elif choice == "2":
            verify_credential_flow()
        elif choice == "3":
            list_credentials_flow()
        elif choice == "4":
            revoke_credential_flow()
        elif choice in ("5", "q", "exit"):
            print("\nExiting Credential Vault Desk. Stay safe.\n")
            sys.exit(0)
        else:
            print("Invalid selection. Try again.")


if __name__ == "__main__":
    main()
