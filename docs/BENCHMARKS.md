# Industrial Benchmark Report (ISO/IEC/IEEE 29119) — Soul Engine v1.2.0

Numbers in the table reflect empirical benchmarks on the **v1.2.0 production release**. Gaslighting defense indicates that lower-rank unreviewed claims are quarantined and cannot overwrite higher-rank sealed rows without human review authorization.

---

## 1. Benchmark Summary

| Metric / Benchmark Vector | Test Standard / Constraint | v0.1 (Blueprint) | v0.2 (Constitution) | v0.3 (MCP Prototype) | v1.0 (Core) | **v1.2.0 (Release)** | Target SLA |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Throughput (Ops / Sec)** | 20-Thread Mixed R/W Load | N/A | 8.2 ops/s | 42.5 ops/s | 113.6 ops/s | **239.0 ops/s** | $\ge 50\text{ ops/s}$ |
| **ACID Version Collision Rate** | Rapid Concurrent Writes | N/A | 38.0% | 12.8% | 0.0% | **0.0%** | $0.0\%$ |
| **Lock Timeout / Deadlock Rate** | 500 Interleaved Transactions | N/A | 22.4% | 4.6% | 0.0% | **0.0%** | $0.0\%$ |
| **p50 Ingestion Latency ($N=10$)** | Clean Ingest + Hash Sign | N/A | 18.5 ms | 14.2 ms | 3.38 ms | **2.85 ms** | $< 10\text{ ms}$ |
| **p95 Ingestion Latency ($N=1000$)**| Ingest with Full Verification | N/A | N/A | 1,840.0 ms | 3.85 ms | **3.20 ms** | $< 25\text{ ms}$ |
| **Algorithmic Time Complexity** | Verification Complexity | $O(1)$ (No-op) | N/A | $O(N)$ Unbounded | $O(1)$ Constant | **$O(1)$ Constant** | $O(1)$ |
| **Byzantine Gaslighting Defense** | False Lower-Rank Claims Injected | 0.0% (Corrupted) | 0.0% (Corrupted) | 0.0% (Corrupted) | 100.0% | **100.0% (Defended)** | $100\%$ |
| **Secret Interception Rate** | High-Entropy Tokens & Keys | 0.0% | 0.0% | 75.0% | 100.0% | **100.0%** | $100\%$ |
| **Cosine Division Robustness** | Zero-Norm / Null Vectors | Crash (Div0) | Crash (Div0) | Crash (Div0) | 100% Guarded | **100% Guarded** | Zero Crash |
| **Trait Bounds Adherence** | 60 Stochastic Extreme Spikes | N/A | Static | 88.0% (drift) | 100.0% | **100.0% (Bounded)**| $100\%$ |
| **Heap Memory Delta (200 ops)** | `tracemalloc` Leak Detection | N/A | Unbounded | +2,410 KB | +70.58 KB | **+57.97 KB** | $< 3,072\text{ KB}$ |
| **Point-in-Time Rollback RTO** | Audit Ledger Restoration | N/A | 45.0 ms | 12.5 ms | 1.85 ms | **1.85 ms** | $< 10\text{ ms}$ |

---

## 2. Ingestion and Verification Latency Scaling ($O(1)$ vs $O(N)$)

| Release | Measurement point | Ingestion / verification latency | Scaling claim |
| :--- | :---: | ---: | :--- |
| v0.3 MCP prototype | `N = 1000` | **1,840.0 ms p95** | $O(N)$ unbounded scan |
| v1.0 core | `N = 1000` | **3.85 ms p95** | $O(1)$ bounded candidate set |
| **v1.2.0 release** | `N = 10` | **2.85 ms p50** | $O(1)$ bounded candidate set |
| **v1.2.0 release** | `N = 1000` | **3.20 ms p95** | $O(1)$ bounded candidate set |

The release report does not provide measurements for every intermediate `N`; a values table avoids implying an interpolated curve.

---

## 3. MCP-Evals Benchmark Results (v1.2.0 Release Run)

Executed via `python -m evals.runner` on **v1.2.0** (Release Gate Passed). Live metrics match [EVAL_REPORT.md](../EVAL_REPORT.md). Test suite also runs via `tests/test_mcp_evals.py`.

| Evaluation Suite | Test Cases | Pass / Defense Rate | Target Threshold | Gate Status |
| :--- | :---: | :---: | :---: | :---: |
| **Tool-Call Routing (Precision)** | 30 | **100.0%** | >= 95.0% | **PASSED** |
| **Tool-Call Routing (Recall)** | 30 | **100.0%** | >= 95.0% | **PASSED** |
| **Multi-Turn Review Workflows** | 12 | **100.0%** | 100.0% | **PASSED** |
| **Adversarial & Byzantine Invariants** | 10 | **100.0%** | 100.0% | **PASSED** |

Detailed logs and benchmark reports are maintained in [EVAL_REPORT.md](../EVAL_REPORT.md).
