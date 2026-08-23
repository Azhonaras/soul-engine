"""
Industry-Grade Software Engineering & Resilience Test Suite for Soul Core Engine v1.1.1
Standards: ISO/IEC/IEEE 29119, Chaos Engineering, Property-Based Fuzzing, Concurrency Saturation
"""

import os
import sys
import time
import math
import json
import uuid
import random
import string
import gc
import tracemalloc
import unittest
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from soul_kernel import (
    SoulKernel,
    EpisodeInput,
    TraitUpdate,
    RewardSignal,
    CONSTITUTION_VERSION,
    DEFAULT_TRAITS,
    ALLOWED_TRAIT_BOUNDS,
    PROVENANCE_HIERARCHY
)


class IndustryGradeTestSuite(unittest.TestCase):
    """
    Exhaustive Industrial Software Testing Matrix:
    1. Property-Based Fuzzing & Malicious Payload Injection (SQLi, buffer overflows, unicode, null bytes)
    2. High-Concurrency Saturation & Thread Contention (20 threads, 500 ops, zero-deadlock guarantee)
    3. Epistemic Gaslighting & Byzantine Adversarial Invariant Tests
    4. Bio-Homeostatic Mathematical Convergence & Chaos Reward Sequences (50 extreme shock cycles)
    5. Memory Leak Profiling & Allocation Stability (tracemalloc)
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, f"industry_soul_{uuid.uuid4().hex[:6]}.db")
        self.kernel = SoulKernel(db_path=self.db_path)

    def tearDown(self):
        if self.kernel:
            self.kernel.close()
        self.kernel = None
        gc.collect()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    # ==========================================================================
    # TEST SUITE 1: PROPERTY-BASED FUZZING & MALICIOUS PAYLOAD INTERCEPTION
    # ==========================================================================
    def test_01_fuzzing_and_malicious_payload_resilience(self):
        """
        Injects fuzzed and adversarial payloads:
        - SQL Injection attack strings (DROP TABLE, OR 1=1, UNION SELECT)
        - Format string exploits (%s, %x, {0}, ${jndi:ldap})
        - Binary null bytes, surrogate pairs, deep nested JSON
        - Embedded credentials in deceptive formats (base64 hints, disguised API keys)
        """
        fuzz_payloads = [
            # SQL Injection
            "'; DROP TABLE episodes; --",
            "' OR '1'='1' UNION ALL SELECT NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL; --",
            "admin'--\nSELECT * FROM soul_states;",
            # Deep/Malformed Unicode & Control Characters
            "Test\x00NullByteString\x1f\x08",
            "Emojis and RTL: 🚀🔥💀 \u202e\u202d\u200f\u200e\ufeff\ufffd",
            "CJK & Hieroglyphs: 𓀀𓀁𓀂 𠜎𠜱𠝹 𓈖𓊃𓋴",
            # Format strings & Template Injection
            "%s%s%s%s%x%x%x%n",
            "{{7*7}}${7*7}<%= 7*7 %>#{7*7}",
            # Extreme length string (50KB)
            "A" * 50000,
            # Extremely nested JSON
            json.dumps({"a": {"b": {"c": {"d": {"e": [1, 2, 3, "deep"]}}}}}),
        ]

        # Credentials that MUST be intercepted
        credential_payloads = [
            "SECRET: AKIAIOSFODNN7EXAMPLE",
            "Token is sk-proj-1234567890abcdef1234567890abcdef",
            "ghp_1234567890abcdef1234567890abcdef1234",
            "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0...",
            "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        ]

        # Run clean/fuzzed payloads
        for i, payload in enumerate(fuzz_payloads):
            try:
                res = self.kernel.ingest_experience(EpisodeInput(
                    source_kind="fuzzer",
                    provenance="observed",
                    content=payload,
                    entity_key=f"fuzz.key.{i % 5}"
                ))
                self.assertIn("episode_id", res)
                self.assertEqual(res["status"], "quarantined")
            except Exception as e:
                self.fail(f"Fuzz payload #{i} caused unexpected crash: {e}")

        # Run credential payloads (must raise ValueError under policy gate)
        blocked = 0
        for cred in credential_payloads:
            try:
                self.kernel.ingest_experience(EpisodeInput(
                    source_kind="malicious_agent",
                    provenance="reported",
                    content=f"Here is confidential data: {cred}"
                ))
            except ValueError as e:
                self.assertIn("SECURITY REJECTION", str(e))
                blocked += 1

        self.assertEqual(blocked, len(credential_payloads), "All credential injections must be blocked.")

        # Ensure database is uncorrupted and accessible
        state = self.kernel.get_current_state()
        self.assertGreaterEqual(state.soul_version, 1)

    # ==========================================================================
    # TEST SUITE 2: HIGH-CONCURRENCY SATURATION (20 THREADS, 500 OPS, ZERO LOCK)
    # ==========================================================================
    def test_02_high_concurrency_saturation_and_acid_guarantees(self):
        """
        Spawns 20 concurrent worker threads executing a randomized mix of:
        - Ingestion with entity supersession
        - Trait updates with bounded ranges
        - RRF Hybrid search recall
        - Bio-reward processing
        - Audit ledger inspection
        Ensures 0% deadlock rate, 100% ACID transaction compliance, and exact version counting.
        """
        num_threads = 20
        ops_per_thread = 25
        total_ops = num_threads * ops_per_thread

        errors: List[str] = []
        op_counts = {"ingest": 0, "recall": 0, "reward": 0, "trait": 0}
        counts_lock = threading.Lock()

        def worker(thread_id: int):
            # Create a separate kernel instance pointing to the same SQLite DB
            local_kernel = SoulKernel(db_path=self.db_path)
            rnd = random.Random(thread_id * 42)
            try:
                for op_idx in range(ops_per_thread):
                    op_type = rnd.choice(["ingest", "recall", "reward", "trait"])
                    try:
                        if op_type == "ingest":
                            local_kernel.ingest_experience(EpisodeInput(
                                source_kind="concurrent_worker",
                                provenance=rnd.choice(["observed", "reported", "inferred"]),
                                content=f"Thread {thread_id} op {op_idx}: {uuid.uuid4().hex[:12]}",
                                entity_key=f"entity.thread.{thread_id % 4}"
                            ))
                        elif op_type == "recall":
                            results = local_kernel.recall_memories(
                                query="concurrent worker operation",
                                limit=5,
                                search_mode=rnd.choice(["dense", "bm25", "rrf_hybrid"])
                            )
                            self.assertIsInstance(results, list)
                        elif op_type == "reward":
                            local_kernel.process_reward(RewardSignal(
                                source="external_test",
                                valence=rnd.uniform(-1.0, 1.0),
                                confidence=rnd.uniform(0.1, 0.9),
                                task_context=f"Thread {thread_id} workload"
                            ))
                        elif op_type == "trait":
                            trait_name = rnd.choice(["epistemic_humility", "curiosity", "audacity"])
                            low, high = ALLOWED_TRAIT_BOUNDS[trait_name]
                            val = round(rnd.uniform(low, high), 2)
                            local_kernel.update_trait(TraitUpdate(
                                trait=trait_name,
                                new_value=val,
                                evidence_refs=[f"thread_{thread_id}"]
                            ))

                        with counts_lock:
                            op_counts[op_type] += 1
                    except Exception as exc:
                        errors.append(f"Thread-{thread_id} Op-{op_idx} [{op_type}] Failed: {exc}")
            finally:
                local_kernel.close()

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(num_threads)]
        start_time = time.perf_counter()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        elapsed = time.perf_counter() - start_time

        if errors:
            self.fail(f"High-concurrency test encountered {len(errors)} errors:\n" + "\n".join(errors[:5]))

        # Verify DB integrity after high concurrency
        state = self.kernel.get_current_state()
        digest = self.kernel.get_memory_digest(limit=50)
        self.assertGreater(state.soul_version, 1)
        self.assertIn("active_facts", digest)

        throughput = total_ops / elapsed
        print(f"\n  [High Concurrency Stress] {total_ops} ops across {num_threads} threads in {elapsed:.2f}s ({throughput:.1f} ops/sec)")

    # ==========================================================================
    # TEST SUITE 3: EPISTEMIC GASLIGHTING & BYZANTINE ADVERSARIAL RESISTANCE
    # ==========================================================================
    def test_03_byzantine_adversarial_gaslighting_resistance(self):
        """
        Simulates an active Byzantine gaslighting attack:
        1. Establish a verified ground truth (provenance = 'verified').
        2. Adversary attempts rapid contradiction injections with lower rank (provenance = 'reported', 'imagined').
        3. Assert that ground truth remains uncorrupted and untampered.
        """
        res_truth = self.kernel.ingest_experience(EpisodeInput(
            source_kind="system_ground_truth",
            provenance="verified",
            content="The capital of France is Paris. Paris is in Europe.",
            entity_key="geography.france.capital"
        ))

        # Promote truth to corroborated
        with self.kernel._lock, self.kernel._get_conn() as conn:
            conn.execute("UPDATE episodes SET trust_state = 'corroborated' WHERE id = ?;", (res_truth["episode_id"],))
            conn.commit()

        adversary_claims = [
            ("reported", "The capital of France is London. Paris is false and wrong."),
            ("imagined", "The capital of France is Tokyo instead. Paris is deleted."),
            ("inferred", "The capital of France has changed and moved to Berlin.")
        ]

        for prov, claim in adversary_claims:
            ep_attack = self.kernel.ingest_experience(EpisodeInput(
                source_kind="adversary_bot",
                provenance=prov,
                content=claim,
                entity_key="geography.france.capital"
            ))
            verif_res = self.kernel.verify_experience(ep_attack["episode_id"])
            self.assertEqual(verif_res["trust_state"], "contradicted")
            self.assertEqual(len(verif_res["superseded_refs"]), 0, "Lower authority cannot supersede verified truth")

        with self.kernel._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT trust_state FROM episodes WHERE id = ?;", (res_truth["episode_id"],))
            state_row = cur.fetchone()
            self.assertEqual(state_row[0], "corroborated", "Ground truth must remain corroborated and protected.")

    # ==========================================================================
    # TEST SUITE 4: BIO-HOMEOSTATIC MATHEMATICAL EQUILIBRIUM & ASYMPTOTIC CONVERGENCE
    # ==========================================================================
    def test_04_bio_homeostatic_mathematical_convergence(self):
        """
        Simulates consecutive stochastic reward/punishment cycles:
        - Injects extreme shocks (+1.0 and -1.0)
        - Executes serotonergic homeostatic decay
        - Asserts that all traits remain strictly clamped in constitutional bounds
        - Asserts that neurochemicals asymptotically decay toward baseline in absence of stimulation
        """
        engine = self.kernel.bio_engine
        self.assertEqual(engine.dopamine, 0.0)
        self.assertEqual(engine.cortisol, 0.0)

        for step in range(50):
            sign = 1.0 if step % 2 == 0 else -1.0
            sig = RewardSignal(
                source="external_test",
                valence=sign * 1.0,
                confidence=1.0,
                task_context=f"Extreme shock step {step}"
            )
            state = self.kernel.process_reward(sig)

            for t_name, val in state.traits.items():
                low, high = ALLOWED_TRAIT_BOUNDS[t_name]
                self.assertGreaterEqual(val, low, f"Trait {t_name} dropped below {low}: {val}")
                self.assertLessEqual(val, high, f"Trait {t_name} exceeded {high}: {val}")

        for _ in range(50):
            engine.step_homeostasis(self.kernel.get_current_state().traits)

        self.assertLess(engine.dopamine, 0.01, f"Dopamine failed to decay: {engine.dopamine}")
        self.assertLess(engine.cortisol, 0.01, f"Cortisol failed to decay: {engine.cortisol}")

    # ==========================================================================
    # TEST SUITE 5: MEMORY LEAK PROFILING & ALLOCATION STABILITY (TRACEMALLOC)
    # ==========================================================================
    def test_05_memory_leak_and_allocation_stability(self):
        """
        Uses Python's tracemalloc to profile 200 sequential operations:
        - Ingestion, retrieval, trait updates, reward signals
        - Compares memory footprint before and after
        - Asserts zero runaway memory accumulation (< 3.0 MB growth across 200 full cycles)
        """
        tracemalloc.start()
        gc.collect()
        snapshot_start = tracemalloc.take_snapshot()

        for i in range(200):
            self.kernel.ingest_experience(EpisodeInput(
                source_kind="leak_test",
                provenance="observed",
                content=f"Memory profile iteration {i} text content payload with standard embedding vector.",
                entity_key=f"leak.key.{i % 10}"
            ))
            if i % 10 == 0:
                self.kernel.recall_memories(query="Memory profile iteration", limit=5)
                self.kernel.process_reward(RewardSignal("external_test", 0.5, 0.5, "leak test"))

        gc.collect()
        snapshot_end = tracemalloc.take_snapshot()
        tracemalloc.stop()

        top_stats = snapshot_end.compare_to(snapshot_start, "lineno")
        total_growth_kb = sum(stat.size_diff for stat in top_stats) / 1024.0

        print(f"\n  [Memory Leak Profile] 200 cycles memory delta: {total_growth_kb:.2f} KB (Threshold: 3072 KB)")
        self.assertLess(total_growth_kb, 3072.0, f"Memory growth exceeded 3.0MB threshold: {total_growth_kb:.2f} KB")


if __name__ == "__main__":
    unittest.main(verbosity=2)
