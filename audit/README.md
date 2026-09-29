# SKY / CBT — BOSS-LEVEL CAPACITY, MEMORY & STORAGE AUDIT SUITE

## Overview
This directory contains the forensic, evidence-backed capacity, memory, concurrency, and storage audit for the **SKY / Crypto Brain Terminal (CBT)** institutional quantitative trading and research platform.

Every conclusion in this audit suite is grounded in:
1. Direct source code inspection with exact file paths and line numbers.
2. Live OS process and runtime measurements on Windows 11.
3. Physical SQLite database introspection across all 4 production databases.
4. Empirical benchmark execution (cache latency, commit throughput, WAL concurrency, vector store scaling, task leaks).
5. Mathematical growth projections under 4 operational stress scenarios.

---

## Audit Dossier Index

| Document | Focus Domain | Key Questions Answered |
| :--- | :--- | :--- |
| [`architecture_inventory.md`](file:///c:/Users/azims/CBT/audit/architecture_inventory.md) | Subsystem Inventory | Complete inventory of runtime processes, databases, caches, workers, and WebSockets. |
| [`database_audit.md`](file:///c:/Users/azims/CBT/audit/database_audit.md) | SQLite & WAL Forensics | Database pragmas, page counts, table rows, locking risks, and auto-vacuum status. |
| [`memory_audit.md`](file:///c:/Users/azims/CBT/audit/memory_audit.md) | RAM & Process RSS | Baseline vs peak RAM for FastAPI, Node.js, and Vite; 24h & 7d soak projections. |
| [`storage_audit.md`](file:///c:/Users/azims/CBT/audit/storage_audit.md) | Disk Footprint & Growth | Market data, uploads, vector store, logs, and disk exhaustion timelines. |
| [`cache_audit.md`](file:///c:/Users/azims/CBT/audit/cache_audit.md) | In-Memory TTL Cache | Sub-millisecond latency verification and unbounded stale key retention leaks. |
| [`background_task_audit.md`](file:///c:/Users/azims/CBT/audit/background_task_audit.md) | Asyncio & Job Lifecycles | Task spawning, completion reclamation, Telegram job persistence, and leak tests. |
| [`ingestion_audit.md`](file:///c:/Users/azims/CBT/audit/ingestion_audit.md) | PDF, OCR & YouTube Pipelines | Document size limits, storage amplification, and zero-download YouTube pipelines. |
| [`frontend_memory_audit.md`](file:///c:/Users/azims/CBT/audit/frontend_memory_audit.md) | React, Charts & WebSockets | TradingView chart single-mounting, series updates, Web Worker, and listener cleanup. |
| [`failure_recovery_audit.md`](file:///c:/Users/azims/CBT/audit/failure_recovery_audit.md) | Chaos & Crash Resilience | Backend restarts, SQLite crash recovery, WebSocket reconnections, and low disk. |
| [`capacity_model.md`](file:///c:/Users/azims/CBT/audit/capacity_model.md) | 1-Month to 1-Year Projections | 4 stress scenarios (Normal, Heavy Market, Research Heavy, Combined Maximum). |
| [`benchmark_results.md`](file:///c:/Users/azims/CBT/audit/benchmark_results.md) | Empirical Benchmark Data | Raw statistical tables for cache latency, commit rates, and vector scaling. |
| [`claim_verification.md`](file:///c:/Users/azims/CBT/audit/claim_verification.md) | Claims vs Evidence Matrix | PASS / FAIL / WARNING / UNVERIFIED matrix across all architectural claims. |
| [`FINAL_CAPACITY_REPORT.md`](file:///c:/Users/azims/CBT/audit/FINAL_CAPACITY_REPORT.md) | Master Executive Verdict | Executive summary, 19-domain scorecard, red flags, and the 20 Boss-Level Answers. |

---

## Audit Execution Environment
- **Host Machine:** Windows 11 Home 64-bit (OS Build 26100)
- **Processor:** AMD Ryzen 5 5500U with Radeon Graphics (6 Cores, 12 Threads)
- **System Memory:** 8.28 GB RAM (~2.18 GB free physical memory)
- **Primary Disk:** C: Drive (NVMe SSD, 237 GB total, ~27.1 GB free)
- **Python Runtime:** Python 3.13.3 64-bit (`c:\Users\azims\CBT\.venv\Scripts\python.exe`)
- **Node.js Runtime:** Node.js v20.12.0 (`npm run dev`)
- **Git Commit:** `934ef80` (Clean working tree)
