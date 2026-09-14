#!/usr/bin/env python3
"""
scripts/configure_vault.py
==========================
Interactive CLI utility to securely encrypt and store exchange credentials
(API Key & Secret Key) into the CBT AES-256-GCM Credential Vault.

Security Invariants:
- Inputs are masked (typing hidden via getpass) so secrets are not echoed on screen.
- Plaintext secrets are encrypted in-memory and never written to unencrypted logs or disk.
- Automatically initializes the database schema if not present.
"""

from __future__ import annotations

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


def main():
    print("=" * 65)
    print(" 🔐 CBT CRYPTO BRAIN TERMINAL — AES-256 CREDENTIAL VAULT")
    print("=" * 65)
    print("This tool encrypts exchange API credentials into the local vault.")
    print("Plaintext keys are NEVER stored on disk in plaintext or logged.\n")

    # 1. Exchange Selection
    print("Select Exchange:")
    print("  [1] BINANCE (Spot & Margin)")
    print("  [2] BYBIT (Linear Perpetuals & Unified)")
    choice_exch = input("Enter selection [1/2, default: 1]: ").strip()
    exchange = "BYBIT" if choice_exch == "2" else "BINANCE"

    # 2. Environment Selection
    print("\nSelect Environment:")
    print("  [1] TESTNET (Simulated Demo Trading — Zero Real Money)")
    print("  [2] PRODUCTION (Live Exchange Trading)")
    choice_env = input("Enter selection [1/2, default: 1]: ").strip()
    environment = "PRODUCTION" if choice_env == "2" else "TESTNET"

    print(f"\nConfiguring {exchange} [{environment}]:")

    # 3. Secure Key Inputs (getpass hides typing)
    api_key = getpass.getpass("Enter API Key (input hidden, paste & press Enter): ").strip()
    if not api_key:
        print("❌ Error: API Key cannot be empty.")
        sys.exit(1)

    api_secret = getpass.getpass("Enter Secret Key (input hidden, paste & press Enter): ").strip()
    if not api_secret:
        print("❌ Error: Secret Key cannot be empty.")
        sys.exit(1)

    passphrase = None
    if exchange == "BYBIT" or "passphrase" in input("Optional: Does this key require an API Passphrase? (y/N): ").lower():
        passphrase_input = getpass.getpass("Enter Passphrase (optional, or press Enter to skip): ").strip()
        if passphrase_input:
            passphrase = passphrase_input

    # 4. Store Credential in Vault
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

        print("\n" + "—" * 65)
        print("✅ SUCCESS: Credential successfully encrypted with AES-256-GCM!")
        print(f"   Exchange:    {exchange}")
        print(f"   Environment: {environment}")
        print(f"   Masked Key:  {mask_secret(api_key)}")
        print(f"   Has Secret:  {'YES (AES-256 Encrypted)' if api_secret else 'NO'}")
        print("   Status:      ACTIVE")
        print("—" * 65)
        print("The Live Launchpad and Gatekeeper can now access this connection.\n")
    except Exception as exc:  # noqa: BLE001
        print(f"\n❌ Failed to store credential in vault: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
