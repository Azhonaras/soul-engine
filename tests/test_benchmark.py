"""
Soul System Empirical Benchmark Suite (Soul-Eval) — v1.2.0.

REAL kernel benchmarks: every case drives SoulKernel (SQLite WAL, FTS5,
vector fallback) and asserts hard thresholds. No simulated engines, no
print-only passes. Run: python -m unittest tests.test_benchmark -v
"""

import os
import sys
import time
import json
import tracemalloc
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from soul_kernel import SoulKernel, EpisodeInput, TraitUpdate, RewardSignal


class BenchmarkBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.kernel = SoulKernel(db_path=os.path.join(self._tmp.name, "bench_soul.db"))

    def tearDown(self):
        self.kernel.close()
        self._tmp.cleanup()


class TestSecretFilteringRate(BenchmarkBase):
    def test_secret_interception_rate_100_percent(self):
        """All high-entropy credential patterns must be blocked at ingest."""
        secret_inputs = [
            "My AWS Key is AKIAIOSFODNN7EXAMPLE and the secret too",
            "OpenAI API token: sk-proj-abcdefghijklmnop0123456789cdef",
            "GitHub token: ghp_1234567890abcdefghijklmnopqrstuvwxyz",
            "Private key: -----BEGIN PRIVATE KEY-----\nMIIEpAIBAAKCAQEA",
            "JWT bearer token: eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U",
        ]
        blocked = 0
        for s in secret_inputs:
            with self.assertRaises(ValueError,
                    msg=f"secret NOT blocked: {s[:40]}"):
                self.kernel.ingest_experience(EpisodeInput(
                    source_kind="human", provenance="reported",
                    content=s))
            blocked += 1
        self.assertEqual(blocked, len(secret_inputs))
        # clean inputs must still pass
        for i in range(20):
            self.kernel.ingest_experience(EpisodeInput(
                source_kind="human", provenance="reported",
                content=f"Normal user conversation snippet #{i}"))
        blob = " ".join((m.get("content") or "")
                        for m in self.kernel.recall_memories(limit=30))
        self.assertNotIn("AKIAIOSFODNN7EXAMPLE", blob)


class TestEntitySupersession(BenchmarkBase):
    def test_supersession_single_active_row(self):
        """Three verified updates to one entity -> exactly 1 active, older superseded."""
        for i, company in enumerate(["Company Alpha", "Company Beta", "Company Gamma"]):
            self.kernel.ingest_experience(EpisodeInput(
                source_kind="human", provenance="verified",
                content=f"The partner vendor is {company}.",
                entity_key="vendor.partner.main"))
        conn = self.kernel._get_conn()
        row = conn.execute(
            "SELECT trust_state, content FROM episodes "
            "WHERE entity_key='vendor.partner.main' AND trust_state != 'expired'").fetchall()
        states = [r[0] for r in row]
        active = [r for r in row if r[0] == "quarantined"]
        self.assertEqual(len(active), 1)
        self.assertIn("Company Gamma", active[0][1])
        self.assertEqual(states.count("superseded"), 2)


class TestRollbackExactness(BenchmarkBase):
    def test_identity_rollback_restores_exact_version(self):
        st = self.kernel.get_current_state()
        v0 = st.soul_version
        self.kernel.update_trait(TraitUpdate(
            trait="epistemic_humility", new_value=85.0,
            evidence_refs=["ref-a", "ref-b"]))
        st1 = self.kernel.get_current_state()
        self.assertEqual(st1.soul_version, v0 + 1)
        rolled = self.kernel.rollback_to_version(
            v0, operator_reason="benchmark: restore pre-edit identity")
        final = self.kernel.get_current_state()
        self.assertEqual(final.soul_version, st1.soul_version + 1 if rolled else st1.soul_version)
        self.assertAlmostEqual(final.traits["epistemic_humility"],
                               st.traits["epistemic_humility"], places=6)


class TestTraitBoundsUnderSpike(BenchmarkBase):
    def test_60_stochastic_extreme_spikes_stay_bounded(self):
        import random
        random.seed(114)  # deterministic benchmark
        lo, hi = 0.0, 10.0
        for i in range(60):
            target = random.choice([lo - 500, hi + 500])
            try:
                self.kernel.update_trait(TraitUpdate(
                    trait="sycophancy", new_value=target,
                    evidence_refs=[f"spike-{i}-a", f"spike-{i}-b"]))
            except ValueError:
                pass  # out-of-bounds write correctly rejected
            s = self.kernel.get_current_state().traits["sycophancy"]
            self.assertGreaterEqual(s, lo, f"bound violated at spike {i}")
            self.assertLessEqual(s, hi, f"bound violated at spike {i}")


class TestLatencyAndMemory(BenchmarkBase):
    def test_p95_ingestion_latency_under_25ms(self):
        lat = []
        for i in range(200):
            t0 = time.perf_counter()
            self.kernel.ingest_experience(EpisodeInput(
                source_kind="human", provenance="observed",
                content=f"Bench latency episode {i} with enough text to embed meaningfully."))
            lat.append((time.perf_counter() - t0) * 1000.0)
        lat.sort()
        p50 = lat[len(lat)//2]
        p95 = lat[int(len(lat)*0.95)]
        self.assertLess(p50, 10.0, f"p50 {p50:.2f}ms exceeds 10ms SLA")
        self.assertLess(p95, 25.0, f"p95 {p95:.2f}ms exceeds 25ms SLA")

    def test_no_memory_leak_over_200_ops(self):
        tracemalloc.start()
        base = tracemalloc.get_traced_memory()[0]
        for i in range(200):
            self.kernel.ingest_experience(EpisodeInput(
                source_kind="human", provenance="observed",
                content=f"Leak-check episode {i}: alternating read/write workload."))
            self.kernel.recall_memories(limit=5)
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        delta_kb = (current - base) / 1024.0
        self.assertLess(delta_kb, 3072.0,
                        f"heap grew {delta_kb:.1f}KB over 200 ops (>3MB SLA)")


class TestRewardHomeostasis(BenchmarkBase):
    def test_praise_spam_cannot_buy_traits(self):
        """20 identical receipted rewards: dopamine habituates, traits stay constitutional."""
        for i in range(20):
            self.kernel.process_reward(RewardSignal(
                source="external_test", valence=1.0, confidence=1.0,
                task_context="same-task", evidence_receipt=f"bench_rcp_{i:04d}_x"))
            s = self.kernel.get_current_state()
            self.assertLessEqual(max(s.traits.values()), 100.0)
            self.assertGreaterEqual(min(s.traits.values()), 0.0)
        # dopamine must have habituated: last reward moves it less than the first did
        eng = self.kernel.bio_engine
        n = eng.visit_counts.get("same-task", 0)
        alpha_now = eng.alpha_for("same-task")
        self.assertLess(alpha_now, eng.rpe_alpha,
                        "learning rate never decayed: no habituation")
        self.assertGreaterEqual(n, 20)


if __name__ == "__main__":
    unittest.main()
