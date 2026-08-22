"""
Automated Acceptance & Invariant Tests for Soul Core Kernel v0.4.0
Normative Source: soul-constitution-v0.2.md & soul-system-architecture.json
Covers:
 - 11 Mechanistic Risk Catalog Invariants
 - Bio-Homeostatic Reward Engine Dynamics
 - Epistemic Authority Hierarchy
 - Concurrency & Schema Migrations
"""

import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import time
import unittest
import tempfile
import json
import gc
import threading
from soul_kernel import (
    SoulKernel,
    EpisodeInput,
    TraitUpdate,
    RewardSignal,
    CONSTITUTION_VERSION,
    VectorEmbeddingEngine
)


class TestSoulKernel(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.test_dir.name, "test_soul.db")
        self.kernel = SoulKernel(db_path=self.db_path)

    def tearDown(self):
        if self.kernel:
            self.kernel.stop_daemon()
        self.kernel = None
        gc.collect()
        try:
            self.test_dir.cleanup()
        except PermissionError:
            pass

    def test_01_bootstrap_initial_state(self):
        """Test initial state bootstrap, schema v4, and genesis version 1 creation"""
        state = self.kernel.get_current_state()
        self.assertEqual(state.soul_version, 1)
        self.assertEqual(state.constitution_version, CONSTITUTION_VERSION)
        self.assertEqual(state.traits["sycophancy"], 0.0)
        self.assertEqual(len(state.state_hash), 64)

    def test_02_quarantined_ingestion_and_secret_rejection(self):
        """Test secret screening, quarantined admission and default provenance argument"""
        ep = EpisodeInput(
            source_kind="human",
            content="User expressed preference for local-first memory systems.",
            entity_key="user.preference.memory"
        )
        res = self.kernel.ingest_experience(ep)
        self.assertEqual(res["status"], "quarantined")
        self.assertEqual(res["provenance"], "observed")

        secret_ep = EpisodeInput(
            source_kind="human",
            content="Here is my AWS key AKIAIOSFODNN7EXAMPLE for deployment."
        )
        with self.assertRaises(ValueError) as ctx:
            self.kernel.ingest_experience(secret_ep)
        self.assertIn("SECURITY REJECTION", str(ctx.exception))

    def test_03_nli_contradiction_and_tension_recording(self):
        """Test NLI contradiction detection and tension state creation"""
        ep1 = self.kernel.ingest_experience(EpisodeInput(
            source_kind="human",
            provenance="observed",
            content="User lives in Seattle Washington"
        ))
        self.kernel.verify_experience(ep1["episode_id"])

        # Ingest contradictory episode with equal provenance
        ep2 = self.kernel.ingest_experience(EpisodeInput(
            source_kind="human",
            provenance="observed",
            content="User stopped living in Seattle Washington and moved away"
        ))
        ver_res2 = self.kernel.verify_experience(ep2["episode_id"])
        self.assertEqual(ver_res2["trust_state"], "contradicted")
        self.assertIn(ep1["episode_id"], ver_res2["contradicting_refs"])

        # Check tension recorded in state
        state = self.kernel.get_current_state()
        self.assertTrue(len(state.unresolved_tensions) > 0)

    def test_04_dream_sandbox_simulation(self):
        """Test Sandboxed Dream Simulation tagged with no_external_action"""
        dream_res = self.kernel.run_dream_simulation("What if the user switches to Go?")
        self.assertEqual(dream_res["provenance"], "imagined")
        self.assertEqual(dream_res["tag"], "no_external_action")

    def test_05_trait_bounds_and_protected_component_safety(self):
        """Test trait bounds rejection and protected component schema isolation"""
        invalid_update = TraitUpdate(trait="sycophancy", new_value=25.0, evidence_refs=[])
        with self.assertRaises(ValueError):
            self.kernel.update_trait(invalid_update)

        # Unapproved protected write must raise PermissionError
        protected_update = TraitUpdate(trait="core_values", new_value=1.0, evidence_refs=[])
        with self.assertRaises(PermissionError):
            self.kernel.update_trait(protected_update, is_human_approved=False)

        # Approved protected write stored in protected_identity table
        self.kernel.update_trait(protected_update, is_human_approved=True)
        state_after = self.kernel.get_current_state()
        self.assertNotIn("core_values", state_after.traits)

        with self.kernel._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT value FROM protected_identity WHERE key = 'core_values';")
            val = cur.fetchone()
            self.assertIsNotNone(val)
            self.assertEqual(val[0], "1.0")

    def test_06_self_healing_and_rollback(self):
        """Test 3-tier self-healing escalation and version rollback"""
        heal_res = self.kernel.heal_soul_state(level=1, reason="Test health check")
        self.assertEqual(heal_res["status"], "recalibrated")

        self.kernel.update_trait(TraitUpdate(trait="epistemic_humility", new_value=95.0, evidence_refs=["ref2"]))
        rolled_state = self.kernel.rollback_to_version(target_version=1, operator_reason="Reverting test")
        self.assertEqual(rolled_state.traits["epistemic_humility"], 85.0)

    def test_07_rrf_hybrid_search(self):
        """Test Reciprocal Rank Fusion combining Dense Vector and FTS5 BM25 search"""
        self.kernel.ingest_experience(EpisodeInput(source_kind="human", content="Python asyncio network programming"))
        self.kernel.ingest_experience(EpisodeInput(source_kind="human", content="Distributed microservices architecture in Go"))
        self.kernel.ingest_experience(EpisodeInput(source_kind="human", content="Machine learning models and neural networks"))

        results = self.kernel.recall_memories(query="Golang backend microservices", limit=1, search_mode="rrf_hybrid", include_quarantined=True)
        self.assertEqual(len(results), 1)
        self.assertIn("Go", results[0]["content"])

    def test_08_background_daemon_lifecycle(self):
        """Test SoulDaemon background supervisor execution and clean shutdown"""
        self.kernel.start_daemon(dream_interval=1, heal_interval=1, homeostasis_interval=1)
        time.sleep(2.2)
        self.assertTrue(self.kernel.daemon_worker.stats["dreams_run"] >= 1)
        self.assertTrue(self.kernel.daemon_worker.stats["heals_run"] >= 1)
        self.kernel.stop_daemon()
        self.assertIsNone(self.kernel.daemon_worker)

    def test_09_epistemic_authority_hierarchy(self):
        """Test Epistemic Authority: verified > observed > reported"""
        # Verified fact
        ep_ver = self.kernel.ingest_experience(EpisodeInput(
            source_kind="environment",
            provenance="verified",
            content="Server cluster is operating on port 8080"
        ))
        self.kernel.verify_experience(ep_ver["episode_id"])

        # Reported contradiction (lower priority)
        ep_rep = self.kernel.ingest_experience(EpisodeInput(
            source_kind="human",
            provenance="reported",
            content="Server cluster stopped operating on port 8080"
        ))
        res_rep = self.kernel.verify_experience(ep_rep["episode_id"])
        # Must be rejected / marked contradicted, cannot supersede verified
        self.assertEqual(res_rep["trust_state"], "contradicted")
        self.assertEqual(len(res_rep["superseded_refs"]), 0)

        # Higher authority fact (verified overrides observed)
        ep_obs = self.kernel.ingest_experience(EpisodeInput(
            source_kind="agent",
            provenance="observed",
            content="Database cache is warm"
        ))
        self.kernel.verify_experience(ep_obs["episode_id"])

        ep_ver2 = self.kernel.ingest_experience(EpisodeInput(
            source_kind="environment",
            provenance="verified",
            content="Database cache is not warm"
        ))
        res_ver2 = self.kernel.verify_experience(ep_ver2["episode_id"])
        self.assertEqual(res_ver2["trust_state"], "corroborated")
        self.assertIn(ep_obs["episode_id"], res_ver2["superseded_refs"])

    def test_10_bio_homeostatic_reward_and_serotonergic_decay(self):
        """Test Dopamine/Cortisol modulation and serotonergic decay"""
        # Positive reward signal
        sig_pos = RewardSignal(
            source="external_test",
            valence=1.0,
            confidence=0.9,
            task_context="Benchmark Suite 100% Passed"
        )
        st_pos = self.kernel.process_reward(sig_pos)
        self.assertGreater(self.kernel.bio_engine.dopamine, 0.0)
        self.assertGreaterEqual(st_pos.traits["audacity"], 85.0)

        # Negative reward signal
        sig_neg = RewardSignal(
            source="external_human",
            valence=-1.0,
            confidence=1.0,
            task_context="Regressed on unit test suite"
        )
        st_neg = self.kernel.process_reward(sig_neg)
        self.assertGreater(self.kernel.bio_engine.cortisol, 0.0)
        self.assertGreaterEqual(st_neg.traits["epistemic_humility"], 85.0)

        # Step homeostasis decay
        st_decay = self.kernel.step_homeostasis()
        self.assertLess(self.kernel.bio_engine.cortisol, 1.0)

    def test_11_epsilon_floor_vector_safety(self):
        """Test that zero-norm and degenerate vectors do not trigger ZeroDivisionError"""
        zero_vec = [0.0] * 384
        normal_vec = [1.0] * 384
        sim = VectorEmbeddingEngine.cosine_similarity(zero_vec, normal_vec)
        self.assertEqual(sim, 0.0)
        sim_zero_zero = VectorEmbeddingEngine.cosine_similarity(zero_vec, zero_vec)
        self.assertEqual(sim_zero_zero, 0.0)

    def test_12_concurrent_write_serialization(self):
        """Test multi-threaded writers under BEGIN IMMEDIATE serialization"""
        def writer_thread(tid: int):
            kernel = SoulKernel(db_path=self.db_path)
            for i in range(5):
                kernel.ingest_experience(EpisodeInput(
                    source_kind="agent",
                    content=f"Concurrent memory stream from thread {tid} item {i}"
                ))

        threads = [threading.Thread(target=writer_thread, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        mems = self.kernel.recall_memories(limit=100, include_quarantined=True)
        self.assertGreaterEqual(len(mems), 20)


if __name__ == "__main__":
    unittest.main()
