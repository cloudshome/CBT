"""
Cryptographic Strategy Manifest Generator
=========================================
Binds canonical strategy specifications to concrete executable python functions,
environment dependencies, and git commit identity.
"""

import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.research.strategy_fingerprint import StrategyCryptographicFingerprint

# Executable strategy functions
def h3_signal_logic(row):
    return (row["oi_pct_chg_1h"] <= -0.040) and (row["close"] < (row["open"] - 0.8 * row["atr_14"]))


def h5_signal_logic(row):
    return (row["bb_width"] <= row["bb_width_q20"]) and (row["oi_pct_chg_24h"] >= 0.030) and (row["close"] < row["bb_lower"])


def main():
    h3_cfg = {
        "strategy_id": "H3_OI_FLUSH_CAPITULATION_LONG_BTC",
        "asset": "BTCUSDT",
        "timeframe": "1h",
        "direction": "LONG",
        "signal_rules": "oi_pct_chg_1h <= -0.040 AND close < open - 0.8 * atr_14",
        "execution": "Next bar open (t+1)",
        "stop_loss_r": 1.0,
        "take_profit_r": 2.0,
        "risk_unit": "1.5 * atr_14",
        "max_hold_bars": 24,
        "frictions": "Taker entry 0.04%, Maker exit 0.02%, Slippage 0.01%, Spread 0.01%, 8h funding settlement payments"
    }

    h5_cfg = {
        "strategy_id": "H5_OI_COMPRESSION_BREAKDOWN_SHORT_ETH",
        "asset": "ETHUSDT",
        "timeframe": "1h",
        "direction": "SHORT",
        "signal_rules": "bb_width <= bb_width_q20 (90d lowest 20th percentile) AND oi_pct_chg_24h >= 0.030 AND close < bb_lower",
        "execution": "Next bar open (t+1)",
        "stop_loss_r": 1.0,
        "take_profit_r": 2.5,
        "risk_unit": "1.5 * atr_14",
        "max_hold_bars": 72,
        "frictions": "Taker entry 0.04%, Maker exit 0.02%, Slippage 0.01%, Spread 0.01%, 8h funding settlement payments"
    }

    fp_h3 = StrategyCryptographicFingerprint(
        strategy_id="H3_OI_FLUSH_CAPITULATION_LONG_BTC",
        canonical_config=h3_cfg,
        executable_logic=h3_signal_logic,
        data_schema_version="v1.0-binance-derivatives-hourly",
        feature_schema_version="v1.0-oi_pct_chg_1h-atr_14"
    )

    fp_h5 = StrategyCryptographicFingerprint(
        strategy_id="H5_OI_COMPRESSION_BREAKDOWN_SHORT_ETH",
        canonical_config=h5_cfg,
        executable_logic=h5_signal_logic,
        data_schema_version="v1.0-binance-derivatives-hourly",
        feature_schema_version="v1.0-bb_width_q20-oi_pct_chg_24h"
    )

    manifest = {
        "manifest_version": "M38-CRYPTOGRAPHIC-STRATEGY-MANIFEST-V2",
        "binding_specification": "Cryptographically binds metadata configuration, executable AST/source code, environment dependencies, and git commit.",
        "candidates": {
            "H3_BTC": fp_h3.to_dict(),
            "H5_ETH": fp_h5.to_dict()
        }
    }

    out_path = ROOT_DIR / "research" / "m38_hypothesis_manifest.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"Manifest written to {out_path}")
    print(f"H3 Composite Fingerprint: {fp_h3.composite_fingerprint}")
    print(f"H5 Composite Fingerprint: {fp_h5.composite_fingerprint}")


if __name__ == "__main__":
    main()
