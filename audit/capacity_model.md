# System Capacity Models & Multi-Horizon Scenarios

## 1. Capacity Modeling Methodology

Current storage (28.09 MB) and memory (196.8 MB) represent the **INITIAL SYSTEM STATE**, not long-term capacity.

To determine physical limits over extended operational horizons, four empirical stress scenarios were constructed using measured row footprints (138.5 B/candle, 1.84 KB/vector, 50 MB max log):

```
Scenario Profiles:
├── Scenario A: Normal Trading (3 Core Assets, 6 Timeframes, 1 Research Monograph/Month)
├── Scenario B: Heavy Market Activity (10 Assets, 6 Timeframes, Volatile Market Structure)
├── Scenario C: Intensive Research Desk (3 Assets + 5 Books/Week + 20 YouTube Videos/Day)
└── Scenario D: Combined Maximum Stress (50 Assets + 100 YouTube Videos/Day + High-Frequency Research)
```

---

## 2. Multi-Horizon Growth Forecast Matrix

### Scenario A — Normal Trading (Current Baseline)
- **Parameters:** BTC/USDT, ETH/USDT, XAU/USD; 6 timeframes; 1 research book/month; 5 YouTube videos/month.
- **Daily Ingestion:** 5,565 candle rows/day (~0.77 MB/day) + ~0.05 MB research data.
- **Monthly Ingestion:** ~24.6 MB/month.

| Horizon | Market DB (MB) | Brain Memory DB (MB) | Trading Logs DB (MB) | Vector Store (MB) | Logs (MB) | Uploads (MB) | Total Disk Footprint | Remaining Free Disk (27.1 GB Host) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Current** | 3.64 MB | 0.51 MB | 0.69 MB | 0.18 MB | 4.8 MB | 18.06 MB | **27.88 MB** | 27.07 GB (99.9%) |
| **1 Month** | 26.76 MB | 1.20 MB | 2.50 MB | 0.45 MB | 15.0 MB | 28.06 MB | **73.97 MB** | 27.03 GB (99.7%) |
| **3 Months** | 73.01 MB | 2.50 MB | 6.00 MB | 1.00 MB | 35.0 MB | 48.06 MB | **165.57 MB** | 26.93 GB (99.4%) |
| **6 Months** | 142.38 MB | 4.50 MB | 11.50 MB | 1.80 MB | 50.0 MB (Capped) | 78.06 MB | **288.24 MB** | 26.81 GB (98.9%) |
| **1 Year** | 284.96 MB | 8.50 MB | 22.00 MB | 3.40 MB | 50.0 MB (Capped) | 138.06 MB | **506.92 MB (~0.51 GB)** | 26.59 GB (98.1%) |

> **Scenario A Verdict:** Completely stable. Requires only ~507 MB after 1 full year.

---

### Scenario B — Heavy Market Activity (Multi-Asset Expansion)
- **Parameters:** 10 active perpetual assets; 6 timeframes; 18,550 candles/day (~2.57 MB/day); higher audit event frequency.
- **Monthly Ingestion:** ~85 MB/month.

| Horizon | Market DB (MB) | Brain Memory DB (MB) | Trading Logs DB (MB) | Vector Store (MB) | Logs (MB) | Total Disk Footprint | Remaining Free Disk |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **1 Month** | 80.74 MB | 1.50 MB | 8.00 MB | 0.50 MB | 25.0 MB | **133.80 MB** | 26.97 GB |
| **3 Months** | 234.94 MB | 3.50 MB | 22.00 MB | 1.20 MB | 50.0 MB | **359.70 MB** | 26.74 GB |
| **6 Months** | 466.24 MB | 6.50 MB | 42.00 MB | 2.20 MB | 50.0 MB | **645.00 MB** | 26.45 GB |
| **1 Year** | 928.84 MB | 12.50 MB | 82.00 MB | 4.20 MB | 50.0 MB | **1,215.60 MB (~1.22 GB)** | 25.88 GB |

> **Scenario B Verdict:** Safe. 1.22 GB after 1 year on a 27.1 GB drive.

---

### Scenario C — Intensive Research Desk Workload
- **Parameters:** 3 assets + 5 research monographs/week (~50 MB raw uploads/week) + 20 YouTube videos/day (~100 KB transcripts/day + ~240 vectors/day).
- **Monthly Ingestion:** ~23 MB market data + ~215 MB uploads + ~15 MB vectors + ~25 MB brain memory = **~278 MB/month**.

| Horizon | Market DB (MB) | Brain Memory DB (MB) | Vector Store (MB) | Uploads (MB) | Total Disk Footprint | Remaining Free Disk |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **1 Month** | 26.76 MB | 25.0 MB | 15.0 MB | 233 MB | **350 MB** | 26.75 GB |
| **3 Months** | 73.01 MB | 72.0 MB | 45.0 MB | 663 MB | **903 MB** | 26.20 GB |
| **6 Months** | 142.38 MB | 142.0 MB | 90.0 MB | 1,308 MB | **1,732 MB (~1.73 GB)** | 25.37 GB |
| **1 Year** | 284.96 MB | 280.0 MB | 180.0 MB | 2,598 MB | **3,393 MB (~3.39 GB)** | 23.71 GB |

> **Scenario C Verdict:** Disk remains within bounds (~3.4 GB/yr), BUT the Vector Store reaches 100,000 vectors where $O(N^2)$ write amplification and $O(N)$ linear search latency will cripple the system.

---

### Scenario D — Combined Maximum Stress (Institutional Limit)
- **Parameters:** 50 assets + 100 YouTube videos/day + 10 monographs/week + continuous backtests.
- **Daily Ingestion:** ~12.85 MB market data + ~14 MB uploads + ~9 MB vectors/memory = **~35.85 MB/day**.
- **Monthly Ingestion:** **~1.08 GB/month**.
- **Annual Ingestion:** **~13.1 GB/year**.

| Horizon | Total Disk Footprint | Remaining Free Disk (27.1 GB Host) | Bottleneck Reached |
| :--- | :--- | :--- | :--- |
| **1 Month** | **1.11 GB** | 25.99 GB | Vector store rewrite latency > 200 ms |
| **3 Months** | **3.27 GB** | 23.83 GB | Vector store rewrite latency > 800 ms |
| **6 Months** | **6.51 GB** | 20.59 GB | Memory exhaustion in Python BoW store |
| **1 Year** | **13.10 GB** | 14.00 GB | Disk at 50% capacity; SQLite locking |
| **2.1 Years** | **27.10 GB** | **0.00 GB (DISK EXHAUSTION)** | **TOTAL SYSTEM COLLAPSE** |

---

## 3. The First Resource SKY Will Run Out Of

### Forensic Answer:
Under scaled research and market ingestion, SKY will **NOT** run out of host CPU or physical disk first.
**SKY WILL EXHAUST PYTHON PROCESS RAM AND DISK WRITE I/O CAPACITY FIRST**, specifically in the `SemanticVectorStore`:
1. Every new vector requires rewriting the entire `vectors.json` to disk ($O(N^2)$ write amplification).
2. At 50,000 vectors, inserting a single document blocks for > 500 ms while rewriting a 100 MB JSON file.
3. Simultaneously, Python's heap will expand to hold all vectors, texts, and metadata in RAM, triggering Windows memory paging on an 8 GB RAM host.
