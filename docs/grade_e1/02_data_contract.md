# Grade-E1 Data Contract & Provenance Verification

**Document Version:** 1.0.0  
**Certified Date:** 2026-09-19  
**Manifest Authority:** `data/research/datasets/manifest_k9.json`  
**Epistemic Evidence Grade:** `GRADE-E1: OHLCV_APPROXIMATION`  

---

## 1. Dataset Provenance & Cryptographic Verification Audit

All 9 frozen research datasets have been audited and cryptographically verified using SHA-256 content hashes. Zero mutations, data leaks, or unrecorded alterations have occurred.

| Dataset ID | Asset | Timeframe | Venue | Row Count | Status | SHA-256 Content Hash (Prefix) |
|---|---|---|---|---|---|---|
| `K9_BTCUSDT_15m_464d2ff4` | BTC | 15m | Binance Spot | 9,008 | `VALID` | `464d2ff49c68ddf1...` |
| `K9_BTCUSDT_1h_17250393` | BTC | 1h | Binance Spot | 658 | `VALID` | `17250393debc51be...` |
| `K9_BTCUSDT_4h_5ee3b6a8` | BTC | 4h | Binance Spot | 165 | `VALID` | `5ee3b6a826f039cc...` |
| `K9_ETHUSDT_15m_1fb09fb3` | ETH | 15m | Binance Spot | 7,179 | `DEGRADED` (12 gaps) | `1fb09fb3e9376df8...` |
| `K9_ETHUSDT_1h_41c0c757` | ETH | 1h | Binance Spot | 267 | `DEGRADED` (8 gaps) | `41c0c757bc42ebdb...` |
| `K9_ETHUSDT_4h_8e1a6bb7` | ETH | 4h | Binance Spot | 74 | `DEGRADED` (6 gaps) | `8e1a6bb74d4ebb71...` |
| `K9_SOLUSDT_15m_a016fbed` | SOL | 15m | Binance Spot | 9,008 | `VALID` | `a016fbed193916ad...` |
| `K9_SOLUSDT_1h_942a3153` | SOL | 1h | Binance Spot | 658 | `VALID` | `942a3153863ffc8e...` |
| `K9_SOLUSDT_4h_a09673a1` | SOL | 4h | Binance Spot | 165 | `VALID` | `a09673a198354383...` |

---

## 2. Schema Specification & Invariant Constraints

Each candle bar strictly adheres to the canonical schema:
```json
{
  "timestamp": 1787428800000,
  "open": 77298.16,
  "high": 77408.00,
  "low": 77258.00,
  "close": 77311.69,
  "volume": 163.00694
}
```

### Invariants:
1. **Monotonicity:** $t_{k} > t_{k-1}$ for all sequential bars.
2. **Price Consistency:** $\text{Low} \le \min(\text{Open}, \text{Close}) \le \max(\text{Open}, \text{Close}) \le \text{High}$.
3. **Strict Positivity:** $\text{Open}, \text{High}, \text{Low}, \text{Close} > 0$ and $\text{Volume} \ge 0$.
4. **Finite Values:** Zero `NaN`, `Inf`, or `null` values permitted.

---

## 3. Epistemic Limitation & Sufficiency Certification

### Formal Epistemic Bounds:
1. **Candle Resolution Only:** These datasets record aggregate interval bars (15m, 1h, 4h). They do not contain individual tick-level orders, trades, or quote arrivals.
2. **No L2 Order Book Depth:** Order book queue depths, cancellation rates, and multi-level liquidity are not observed.
3. **Queue Model Approximation:** Any queue simulation running against these datasets must be explicitly designated:
   $$\text{Classification} = \text{GRADE-E1: OHLCV\_APPROXIMATION}$$
4. **Anti-Hallucination Invariant:** Under no circumstances will Grade-E1 claim, document, or serialize results as `EMPIRICAL_L2_REPLAY`. If an L2 replay is requested, the system must return a status of `DATA_INSUFFICIENT` for L2 while executing the scientifically bounded `OHLCV_APPROXIMATION` model.

---

## 4. Handling of Degraded Datasets (ETH/USDT)

The ETH/USDT datasets contain documented missing intervals due to historical upstream collection gaps:
- When replaying through missing intervals, the market replay engine will flag `GAP_DETECTED`.
- No lookahead interpolation or synthetic smoothing across gap boundaries will be permitted.
- Fills or orders active during a gap transition will be invalidated with status `CANCELLED_DUE_TO_DATA_GAP`.
- Performance statistics will report gap-conditioned metrics separately to prevent distortion.
