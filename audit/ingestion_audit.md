# Research Ingestion, PDF, OCR & YouTube Pipeline Audit

## 1. PDF Literature & Book Ingestion Pipeline (`core/pdf_extractor.py`)

The literature extraction subsystem ingests financial monographs and academic research papers under Constitutional Article I, Section 1.5.

```
PDF Book Ingestion Flow:
Uploaded Monograph (.pdf) -> pypdf Text Stream -> Page/Chapter Headings
       │
       ├── Text present (>= 40 chars/page) -> Direct Segmentation
       │
       └── Scanned page (< 40 chars + image) -> Gemini 2.5 Flash Vision OCR
                                                              │
                                                              ▼
               Epistemic Typology Classifier (7-Tier Quarantine)
                               │
               Atomic Claims [C-XXXXXX] (Confidence strictly = 0.0)
                               │
               Knowledge Graph Nodes & Semantic Vector Store Embeddings
```

### A. Upload Size Constraint vs Book Reality
- **Configured Upload Limit:** **25 MB** (`MAX_FILE_BYTES = 25 * 1024 * 1024` in `core/telegram/media.py`).
- **Physical Test File in Repo:** `data/uploads/Night_Sky_Almanac_Storm_Dunlop_Wil_Tirion_2022.pdf` is **18.06 MB (18,933,571 bytes)**.
- **Audit Assessment:**
  - Standard academic papers (10-50 pages): 1 to 5 MB — **SUPPORTED**.
  - Text-based monographs (300-500 pages): 5 to 15 MB — **SUPPORTED**.
  - High-resolution scanned monographs / image-heavy trading books: Frequently 40 to 120 MB.
  - **LIMIT IDENTIFIED:** Scanned books exceeding 25 MB are **BLOCKED** by the current upload gate.

### B. Storage Amplification Model (1 x 300-Page Research Book)
When a 300-page book (approx. 10 MB PDF) is ingested into CBT:
1. **Raw Source PDF (`data/uploads/`):** **10.0 MB** (Retained permanently).
2. **Extracted Plain Text:** ~600,000 characters $\approx$ **0.6 MB**.
3. **Atomic Claims (`brain_memory.db`):** ~120 substantive claims $\times$ ~800 bytes $\approx$ **0.1 MB**.
4. **Knowledge Graph Nodes & Edges (`brain_memory.db`):** ~40 nodes + ~80 edges $\approx$ **0.05 MB**.
5. **Vector Store Embeddings (`data/vector_store/vectors.json`):** 120 vectors $\times$ 1.84 KB $\approx$ **0.22 MB**.
6. **Cumulative Storage Amplification:** $10.0 + 0.6 + 0.1 + 0.05 + 0.22 = \mathbf{10.97\text{ MB per book}}$.
- **Storage Amplification Ratio:** **~1.1x** (Very low, primarily dominated by the raw PDF file itself).
- **Vulnerability:** Because the raw PDF is never purged, 100 books will consume **~1.1 GB**.

---

## 2. YouTube Autonomous Exploration Pipeline (`core/youtube/`)

The YouTube research discovery agent transforms video channels and playlists into structured research intelligence.

### A. Media Download Verification: Zero Disk Leakage
- **Architectural Verification:**
  - `core/youtube_extractor.py` configures `yt-dlp` with:
    `"skip_download": True, "extract_flat": True, "simulate": True`
  - `core/youtube/deconstruction.py` retrieves text transcripts directly from `YouTubeTranscriptApi`.
- **RESULT: PASS.**
  - **SKY NEVER DOWNLOADS MP4, WEBM, OR RAW AUDIO FILES.**
  - Video and audio bytes are never written to disk.
  - Disk storage is strictly limited to text subtitles, metadata, and extracted claims.

### B. Daily Video Ingestion Scaling Model

| Ingestion Rate | Transcripts / Day | Daily Text DB Growth | Daily Vector Growth | Daily Total Disk | Annual Total Disk |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **10 Videos/Day** | 10 | ~350 KB | ~180 KB | **~0.53 MB/day** | **~0.19 GB/year** |
| **100 Videos/Day** | 100 | ~3.5 MB | ~1.8 MB | **~5.30 MB/day** | **~1.93 GB/year** |
| **1,000 Videos/Day** | 1,000 | ~35.0 MB | ~18.0 MB | **~53.0 MB/day** | **~19.3 GB/year** |
| **10,000 Videos/Day** | 10,000 | ~350.0 MB | ~180.0 MB | **~530.0 MB/day** | **~193.5 GB/year (UNSAFE)** |

- **Safe Operating Limit:** $\le 100\text{ videos/day}$ is completely sustainable on the current 27.1 GB host drive.

---

## 3. Semantic Vector Store Forensics (`core/memory_vault.py`)

The vector database operates as an in-memory Bag-of-Words index with JSON file persistence (`data/vector_store/vectors.json`).

### Empirical Measurement (from live benchmark):
- **Vector Dimensions:** 128-dimensional float32.
- **Disk Footprint per Vector:** **1,838.5 bytes/vector** (Indented ASCII JSON).
- **Write Time per 100 Vectors:** **3.436 seconds** (**34.36 ms per insert**).
- **Search Latency (100 vectors):** **0.657 ms**.

### Vector Scaling Projections

| Vector Count | Raw Floats (RAM) | JSON Disk Size | Sequential Write I/O (Cumulative) | Brute-Force Query Latency | Feasibility Verdict |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1,000 Vectors** | 0.5 MB | **1.84 MB** | ~1.8 GB rewritten | **~6.5 ms** | PASS |
| **10,000 Vectors** | 5.1 MB | **18.38 MB** | ~180 GB rewritten | **~65.7 ms** | WARNING (High Disk I/O) |
| **100,000 Vectors** | 51.2 MB | **183.85 MB** | ~18 TB rewritten | **~657.0 ms** | **FAIL (I/O & Latency)** |
| **1,000,000 Vectors** | 512.0 MB | **1.84 GB** | Unfeasible | **~6.57 seconds** | **CRITICAL FAIL** |

```text
VECTOR STORE CAPACITY VERDICT: FAIL FOR SCALED RESEARCH
The O(N^2) write amplification (rewriting the entire JSON file on every insert)
and O(N) linear query latency will halt research processing beyond 10,000 vectors.
Replacement with SQLite-vec, Chroma, DuckDB, or LanceDB is required before production scale.
```
