# Milestone 19: JIT Execution Hotpath Latency Benchmark

**Target Metric:** Sub-millisecond routing cycle (< 250 us)  
**Iterations:** 5,000 per engine  
**Timing Precision:** Nanoseconds (`time.perf_counter_ns()`)  

## 1. Smart Order Router (SOR) Depth Walking Latency

| Metric | Latency (us) | Latency (ms) | Target Status |
|---|---|---|---|
| **Median (p50)** | 543.00 us | 0.5430 ms | FAIL (< 250 us) |
| **90th Percentile (p90)** | 1180.87 us | 1.1809 ms | FAIL |
| **99th Percentile (p99)** | 2796.41 us | 2.7964 ms | FAIL (< 1 ms) |
| **99.9th Percentile (p999)** | 4935.90 us | 4.9359 ms | - |
| **Mean** | 722.79 us | 0.7228 ms | FAIL |
| **Max** | 8402.40 us | 8.4024 ms | - |

## 2. Almgren-Chriss Slicer Optimization Latency

| Metric | Latency (us) | Latency (ms) | Target Status |
|---|---|---|---|
| **Median (p50)** | 35.70 us | 0.0357 ms | PASS (< 250 us) |
| **90th Percentile (p90)** | 71.31 us | 0.0713 ms | PASS |
| **99th Percentile (p99)** | 116.42 us | 0.1164 ms | PASS (< 1 ms) |
| **99.9th Percentile (p999)** | 849.60 us | 0.8496 ms | - |
| **Mean** | 45.10 us | 0.0451 ms | PASS |
| **Max** | 2329.30 us | 2.3293 ms | - |
