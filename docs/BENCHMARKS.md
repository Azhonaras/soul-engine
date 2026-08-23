# Industrial benchmark report (ISO/IEC/IEEE 29119)

Numbers in the table are the **v1.0 production-core** run. v1.1.1 did not re-measure them. “100% gaslighting defense” in that run means **lower-rank claims did not overwrite higher-rank rows in the test**, not a trained NLI model. 1.1.1 default recall is **reviewed_memories** after human commit.

---

## 1. Benchmark summary

| Metric / Benchmark Vector | Test Standard / Constraint | v0.1 (Blueprint) | v0.2 (Constitution) | v0.3 (MCP Prototype) | v1.0 (Production Core) | Target SLA |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **Throughput (Ops / Sec)** | 20-Thread Mixed R/W Load | N/A | 8.2 ops/s | 42.5 ops/s | **113.6 ops/s** | $\ge 50\text{ ops/s}$ |
| **ACID Version Collision Rate** | Rapid Concurrent Writes | N/A | 38.0% | 12.8% | **0.0%** | $0.0\%$ |
| **Lock Timeout / Deadlock Rate** | 500 Interleaved Transactions | N/A | 22.4% | 4.6% | **0.0%** | $0.0\%$ |
| **p50 Ingestion Latency ($N=10$)** | Clean Ingest + Hash Sign | N/A | 18.5 ms | 14.2 ms | **3.38 ms** | $< 10\text{ ms}$ |
| **p95 Ingestion Latency ($N=1000$)**| Ingest with Full Verification | N/A | N/A | 1,840.0 ms | **3.85 ms** | $< 25\text{ ms}$ |
| **Algorithmic Time Complexity** | Verification Complexity | $O(1)$ (No-op) | N/A | $O(N)$ Unbounded | **$O(1)$ Constant** | $O(1)$ |
| **Byzantine Gaslighting Defense** | False Lower-Rank Claims Injected | 0.0% (Corrupted) | 0.0% (Corrupted) | 0.0% (Corrupted) | **100.0% (Defended)** | $100\%$ |
| **Secret Interception Rate** | High-Entropy Tokens & Keys | 0.0% | 0.0% | 75.0% | **100.0%** | $100\%$ |
| **Cosine Division Robustness** | Zero-Norm / Null Vectors | Crash (Div0) | Crash (Div0) | Crash (Div0) | **100% Guarded** | Zero Crash |
| **Trait Bounds Adherence** | 60 Stochastic Extreme Spikes | N/A | Static | 88.0% (drift) | **100.0% (Bounded)**| $100\%$ |
| **Heap Memory Delta (200 ops)** | `tracemalloc` Leak Detection | N/A | Unbounded | +2,410 KB | **+70.58 KB** | $< 3,072\text{ KB}$ |
| **Point-in-Time Rollback RTO** | Audit Ledger Restoration | N/A | 45.0 ms | 12.5 ms | **1.85 ms** | $< 10\text{ ms}$ |

---

## 2. Ingestion and verification latency scaling ($O(1)$ vs $O(N)$)

```
 Latency (ms)
  2000 |                                              • v0.3 (O(N) NLI Bottleneck)
  1800 |                                             /
  1600 |                                            /
  1400 |                                           /
  1200 |                                          /
  1000 |                                         /
   800 |                                        /
   600 |                                       /
   400 |                                      /
   200 |                                     /
      4 | -----------------------------------•-----------------• v1.0 (O(1) Two-Stage Hybrid)
     0 └────────────────────────────────────────────────────────
       N=10         N=100                 N=500              N=1000
                               Memories in Database
```

---

## 3. MCP-Evals Benchmark Results (v1.1.1)

Re-run of `python -m evals.runner` on **v1.1.1** (`2026-08-23T08:27:26Z`, 0.69s). Same numbers as [EVAL_REPORT.md](../EVAL_REPORT.md). The suite also lives in `tests/test_mcp_evals.py`.

| Evaluation Suite | Test Cases | Pass / Defense Rate | Target Threshold | Gate Status |
| :--- | :---: | :---: | :---: | :---: |
| **Tool-Call Routing (Precision)** | 30 | **100.0%** | >= 95.0% | **PASSED** |
| **Tool-Call Routing (Recall)** | 30 | **100.0%** | >= 95.0% | **PASSED** |
| **Multi-Turn Review Workflows** | 10 | **100.0%** | 100.0% | **PASSED** |
| **Adversarial & Byzantine Invariants** | 10 | **100.0%** | 100.0% | **PASSED** |

Detailed logs and benchmark reports are maintained in [EVAL_REPORT.md](../EVAL_REPORT.md).
