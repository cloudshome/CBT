"""
Initialize Production Shadow Prediction Ledger
==============================================
Populates the append-only shadow ledger with initial precommit records using
the new tamper-evident hash-chained schema and verifies cryptographic integrity.
"""

import sys
from pathlib import Path

ROOT_DIR = Path("C:/Users/azims/CBT")
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.research.shadow_ledger import ShadowLedgerEngine

def main():
    ledger_path = ROOT_DIR / "research" / "m38_shadow_prediction_ledger.jsonl"
    
    # Overwrite the old single-line stub with the new production engine
    if ledger_path.exists():
        ledger_path.unlink()
        
    engine = ShadowLedgerEngine(ledger_path)
    
    # Precommit an initial prospective baseline shadow record for H3 (BTC)
    p_h3 = engine.precommit_prediction(
        strategy_id="H3_OI_FLUSH_CAPITULATION_LONG_BTC",
        strategy_fingerprint="16ddd3cc8c8290c204c29fc74223f64d016afd08927862ab76cb303193563deb",
        symbol="BTCUSDT",
        timeframe="1h",
        direction="LONG",
        entry_price=81682.10,
        stop_loss_price=79540.00,
        take_profit_price=85966.30,
        risk_unit_usd=2142.10,
        max_hold_bars=24,
        timestamp_utc="2026-11-05T08:00:00Z",
        idempotency_key="GENESIS_SHADOW_H3_BTC_20261105_080000"
    )
    
    # Precommit an initial prospective baseline shadow record for H5 (ETH)
    p_h5 = engine.precommit_prediction(
        strategy_id="H5_OI_COMPRESSION_BREAKDOWN_SHORT_ETH",
        strategy_fingerprint="fb269fa3bfe884e236c55a3719341868a19428e5e91d754e5e657eabe6b09c01",
        symbol="ETHUSDT",
        timeframe="1h",
        direction="SHORT",
        entry_price=2840.50,
        stop_loss_price=2925.00,
        take_profit_price=2629.25,
        risk_unit_usd=84.50,
        max_hold_bars=72,
        timestamp_utc="2026-11-05T08:00:00Z",
        idempotency_key="GENESIS_SHADOW_H5_ETH_20261105_080000"
    )
    
    is_valid, msg, count = engine.verify_ledger_integrity()
    print(f"Shadow Ledger Initialized. Verification: {is_valid} ({msg}), Records: {count}")
    summary = engine.export_summary()
    print("Summary:", summary)

if __name__ == "__main__":
    main()

