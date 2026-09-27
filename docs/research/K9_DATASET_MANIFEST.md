# Milestone K9: Canonical Research Dataset Manifest

**Manifest Version:** `K9_DATASET_V1.0`  
**Storage Directory:** `data/research/datasets/`  
**Master Manifest File:** `data/research/datasets/manifest_k9.json`  
**Schema Hash:** `f3e6322b86147a25a98f8cf384abe683cd6edbe19717b91666a48ab0bdc23370`  
**Generated At:** `2026-09-19T11:23:51+06:00`  

---

## 1. Canonical Frozen Datasets

The following 9 canonical datasets are immutably frozen for Milestone K9 research tournaments. Any mutation of candle contents changes the SHA-256 content hash and triggers a `DatasetCorruptionError`.

| Dataset ID | Asset | Timeframe | Bars | Start Timestamp (UTC) | End Timestamp (UTC) | Status | Content Hash (SHA-256) |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---|
| `K9_BTCUSDT_15m_464d2ff4` | `BTC` | `15m` | 9,008 | `1787430600000` | `1789794900000` | `VALID` | `464d2ff49c68ddf1be418ef7a56f937a46ee9a82c6cbed2e663016aa4e026fd3` |
| `K9_BTCUSDT_1h_17250393` | `BTC` | `1h` | 658 | `1787428800000` | `1789794000000` | `VALID` | `17250393debc51befff643df3190383cfcc26b4a79ca7b0b8484a86bae42cb8a` |
| `K9_BTCUSDT_4h_5ee3b6a8` | `BTC` | `4h` | 165 | `1787428800000` | `1789790400000` | `VALID` | `5ee3b6a826f039cc02474efb3f8eff2032a54218324bdac74827521dd00ff100` |
| `K9_ETHUSDT_15m_1fb09fb3` | `ETH` | `15m` | 7,179 | `1787790134561` | `1789794900000` | `DEGRADED` | `1fb09fb3792015093126be12ef84a1d471556959b85c138daecbcaea6a96e579` |
| `K9_ETHUSDT_1h_41c0c757` | `ETH` | `1h` | 267 | `1787788800000` | `1789794000000` | `DEGRADED` | `41c0c75796c9f28c2e6f4244cb019ad7788414457e5e3d7bbbe47a835c60e363` |
| `K9_ETHUSDT_4h_8e1a6bb7` | `ETH` | `4h` | 74 | `1787798400000` | `1789790400000` | `DEGRADED` | `8e1a6bb731a541604a11f26fdb1b702ec9472e3a8f0ad56277dbfeebfe0a8cbb` |
| `K9_SOLUSDT_15m_a016fbed` | `SOL` | `15m` | 9,008 | `1787430600000` | `1789794900000` | `VALID` | `a016fbeda1298642a8b843322d713c7da0d69188d3e91dbeec749ff85289945c` |
| `K9_SOLUSDT_1h_942a3153` | `SOL` | `1h` | 658 | `1787428800000` | `1789794000000` | `VALID` | `942a3153eb2bb1a5b81fcae1d9d95f6efdf568444a95610ec8ca4e60655d9d7f` |
| `K9_SOLUSDT_4h_a09673a1` | `SOL` | `4h` | 165 | `1787428800000` | `1789790400000` | `VALID` | `a09673a19e5c46e31b658d55c70b8159b35cf818965ae763842c13d80a1ae152` |

---

## 2. Integrity Verification Protocol

Integrity is validated via `DatasetFreezeManager.verify_dataset_integrity(dataset_id)`:
1. Re-computes the row-by-row formatted SHA-256 fingerprint:
   $$\text{Hash} = \text{SHA256}\left( \sum_{i=1}^N \text{timestamp}_i : \text{open}_i : \text{high}_i : \text{low}_i : \text{close}_i : \text{volume}_i \right)$$
2. Compares against the registered content hash in `data/research/datasets/manifest_k9.json`.
3. Verifies schema structure matches canonical 6-tuple definition.
4. Confirms monotonic ascending timestamps ($t_i > t_{i-1}$) and valid OHLCV geometry ($h_i \ge \max(o_i, c_i)$, $l_i \le \min(o_i, c_i)$, $v_i \ge 0$).

---

## 3. Data Provenance & Cleaning Rules
- **Binance Spot Continuous OHLCV:** Extracted from historical sqlite ledger `data/market_data.db`.
- **Resampling:** Multi-timeframe series (1h, 4h) are constructed by strict chronological rollups of continuous 15m intervals to guarantee boundary alignment across timeframes.
- **Missing Interval Tolerance:** Datasets with $> 5\%$ missing intervals are automatically tagged as `DEGRADED` and logged in the manifest notes. Datasets with timestamp inversions or duplicate entries are classified as `INVALID` and rejected from freeze.
