# Storage, Disk Growth & Retention Policy Audit

## 1. Physical Storage Breakdown

Current physical storage footprint measured across `c:\Users\azims\CBT\data`:

```
c:\Users\azims\CBT\data/
├── market_data.db       (3.64 MB | 26,296 candles)
├── market_data.db-wal   (45.3 KB active WAL)
├── market_data.db-shm   (32.7 KB shared-memory index)
├── trading_logs.db      (688 KB  | 823 audit/execution rows)
├── brain_memory.db      (512 KB  | 609 concept/claim/node rows)
├── experiment_store.db  (176 KB  | 71 Kronos forecast rows)
├── logs/cbt_terminal.log (4.8 MB  | Strictly hard-capped at 50 MB)
├── uploads/             (18.06 MB | 2 PDF files present)
│   ├── Night_Sky_Almanac_Storm_Dunlop_Wil_Tirion_2022.pdf (18.06 MB)
│   └── tg_1788677109_Liquidation_Map_Trading_Playbook.pdf  (4.8 KB)
└── vector_store/        (0.18 MB | vectors.json in BoW format)
────────────────────────────────────────────────────────────
TOTAL DATA DIRECTORY:    ~28.09 MB
HOST DRIVE C: FREE:      27.1 GB (out of 237 GB)
```

---

## 2. Market Data Capacity Model (Measured Row Footprint)

- **Physical Row Size:** **138.5 bytes per candle** (measured from `candles` table: 3,817,472 bytes / 26,296 rows, including B-tree indexing and page fragmentation).
- **Active Operational Configuration:**
  - 3 Core Asset Symbols: `BTC/USDT`, `ETH/USDT`, `XAU/USD` (PAXG)
  - 6 Active Timeframes: `1m`, `5m`, `15m`, `1h`, `4h`, `1d`
- **Cadence Production per Symbol per Day:**
  - `1m`: 1,440 candles/day
  - `5m`: 288 candles/day
  - `15m`: 96 candles/day
  - `1h`: 24 candles/day
  - `4h`: 6 candles/day
  - `1d`: 1 candle/day
  - **Subtotal per Symbol:** **1,855 candles/day**

### A. Current Configuration (3 Symbols)

| Time Horizon | Candle Rows Generated | Disk Growth (Raw Data) | Disk Growth with SQLite Pages (138.5 B/row) | Cumulative Database Size |
| :--- | :--- | :--- | :--- | :--- |
| **1 Hour** | 232 rows | 18.5 KB | **32.1 KB** | 3.67 MB |
| **24 Hours (1 Day)** | 5,565 rows | 445 KB | **770.8 KB (~0.77 MB)** | 4.41 MB |
| **7 Days (1 Week)** | 38,955 rows | 3.11 MB | **5.40 MB** | 9.04 MB |
| **30 Days (1 Month)** | 166,950 rows | 13.35 MB | **23.12 MB** | 26.76 MB |
| **90 Days (Quarter)** | 500,850 rows | 40.07 MB | **69.37 MB** | 73.01 MB |
| **1 Year (365 Days)** | 2,031,225 rows | 162.50 MB | **281.32 MB (~0.28 GB)** | 284.96 MB |

> **Conclusion for 3 Symbols:** Growth is extremely stable and well within the 27.1 GB host disk capacity.

---

### B. Scaled Institutional Configuration (50 Symbols)

If CBT scales to monitor 50 crypto perpetual and macro symbols across the same 6 timeframes:
- **Rows per Day:** $50 \times 1,855 = \mathbf{92,750\text{ rows/day}}$
- **Daily Storage:** $92,750 \times 138.5\text{ bytes} = \mathbf{12.85\text{ MB/day}}$
- **Monthly Storage (30 Days):** $\mathbf{385.5\text{ MB/month}}$
- **Annual Storage (365 Days):** $\mathbf{4.69\text{ GB/year}}$
- **5-Year Storage:** $\mathbf{23.45\text{ GB}}$ (**Approaching total C: drive free space**).

---

## 3. Log Rotation & Disk Containment Audit

Inspected in [`app.py`](file:///c:/Users/azims/CBT/app.py):

```python
file_handler = RotatingFileHandler(
    log_dir / "cbt_terminal.log",
    maxBytes=10 * 1024 * 1024,  # 10 MB
    backupCount=5,
    encoding="utf-8",
)
```

- **Maximum Python Log Storage:** $10\text{ MB} \times (1 + 5) = \mathbf{60\text{ MB hard ceiling}}$.
- **Node.js Paper Desk Logs:** Emitted to standard output (`stdout`/`stderr`). If executed under PM2/systemd without rotation, unhandled stdout redirection can grow without bound. (Under current Vite/Node spawn, output is transient).
- **Audit Verdict:** **PASS (Python Logging)** / **WARNING (Node unmanaged stdout)**.

---

## 4. Temporary Files & Uploads Vulnerability Forensics

1. **Uploads Directory (`data/uploads/`):**
   - Contains raw PDF files uploaded by operators or Telegram users (currently 18.06 MB present).
   - **RED FLAG:** There is **NO automated retention or TTL cleanup** for `data/uploads/`.
   - If an operator uploads ten 20 MB research books, 200 MB remains permanently on disk.
2. **Temporary Files:**
   - Forensic search across all modules found zero unlinked temporary file leaks.
   - The YouTube pipeline uses `skip_download: True` and `download=False` in `yt-dlp`, ingesting subtitles via the API without downloading MP4 or WAV files.
   - The backup system in `core/brain_backup.py` creates `temp_restore.tar.gz` and explicitly unlinks it in a `finally` block.
3. **SQLite Auto-Vacuum Disabled (`auto_vacuum = 0`):**
   - **CRITICAL STORAGE FLAW:** In all 4 databases, `auto_vacuum` is disabled.
   - When old candle data or audit logs are deleted (`DELETE FROM candles WHERE timestamp < ...`), SQLite marks pages as free on its internal freelist.
   - **The file size on disk NEVER shrinks.**
   - Over months of operation, fragmented free pages will accumulate unless an explicit `VACUUM` command is issued during low-activity maintenance windows.
