"""
Automated Acceptance & Invariant Tests for Soul Core Kernel v1.2.0 (schema 9)
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
import datetime
from soul_kernel import (
    SoulKernel,
    EpisodeInput,
    TraitUpdate,
    RewardSignal,
    CONSTITUTION_VERSION,
    SOUL_ENGINE_VERSION,
    SCHEMA_VERSION,
    PERCEPT_JSON_MAX_CHARS,
    VectorEmbeddingEngine
)


def _output_review_receipt(kernel, session_id, content="sealed output for identity reward"):
    kernel.ingest_experience(EpisodeInput(source_kind="agent", content=content))
    cycle = kernel.start_review_cycle(session_id=session_id)
    out = kernel.apply_chat_review(
        session_id=session_id,
        cycle_id=cycle["cycle_id"],
        decisions=[{"candidate_id": cycle["candidates"][0]["id"], "decision": "remember"}],
    )
    return out["receipt"]["receipt_id"]


class TestSoulKernel(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.test_dir.name, "test_soul.db")
        self.kernel = SoulKernel(db_path=self.db_path)

    def tearDown(self):
        if self.kernel:
            self.kernel.close()
        self.kernel = None
        gc.collect()
        try:
            self.test_dir.cleanup()
        except PermissionError:
            pass

    def test_01_bootstrap_initial_state(self):
        """Test initial state bootstrap, schema 9, and genesis version 1 creation"""
        state = self.kernel.get_current_state()
        self.assertEqual(SOUL_ENGINE_VERSION, "1.2.0")
        self.assertEqual(SCHEMA_VERSION, 9)
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
        self.assertTrue(self.kernel.get_memory_digest()["dream_due"])

    def test_04_dream_sandbox_simulation(self):
        """Two-phase dream: context packet, then agent-written imagined outcomes."""
        ctx = self.kernel.run_dream_simulation("What if the user switches to Go?")
        self.assertEqual(ctx["status"], "needs_thought")
        self.assertIn("budget", ctx)
        self.assertIn("used_chars", ctx["budget"])
        self.assertLessEqual(ctx["budget"]["used_chars"], ctx["budget"]["max_chars"])
        fact_ids = {f.get("memory_id") for f in ctx.get("reviewed_facts") or []}
        ana_ids = {a.get("memory_id") for a in ctx.get("analogical_cases") or []}
        self.assertFalse(fact_ids & ana_ids)
        with self.assertRaises(ValueError):
            self.kernel.run_dream_simulation(
                "What if the user switches to Go?",
                outcomes=[
                    "Simulated hypothetical result for: 'What if the user switches to Go?' under constitutional bounds.",
                    "Something else",
                ],
            )
        dream_res = self.kernel.run_dream_simulation(
            "What if the user switches to Go?",
            outcomes=[
                "They keep Python because the repo already ships 3.9 CI.",
                "They rewrite hot paths in Go and keep Python for MCP.",
            ],
        )
        self.assertEqual(dream_res["status"], "recorded")
        self.assertEqual(dream_res["provenance"], "imagined")
        self.assertEqual(dream_res["tag"], "no_external_action")
        self.assertEqual(len(dream_res["outcomes"]), 2)

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

        self.kernel.update_trait(TraitUpdate(trait="epistemic_humility", new_value=95.0, evidence_refs=["ref2", "ref2b"]))
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
        """Daemon heals when drifted; timer does not set dream_due without tension or dead_end."""
        rid = _output_review_receipt(self.kernel, "sess_daemon")
        self.kernel.process_reward(RewardSignal(
            source="external_human",
            valence=-1.0,
            confidence=1.0,
            task_context="force cortisol so heal has work",
            review_receipt=rid,
        ), session_id="sess_daemon")
        self.kernel.start_daemon(dream_interval=1, heal_interval=1, homeostasis_interval=1)
        time.sleep(2.2)
        stats = self.kernel.daemon_worker.stats
        self.assertFalse(stats["dream_due"])
        self.assertEqual(stats["dreams_run"], 0)
        self.assertGreaterEqual(stats["heals_run"], 1)
        self.assertTrue(stats["heal_due"])
        with self.kernel._get_conn() as conn:
            n = conn.execute("SELECT COUNT(*) FROM dream_simulations;").fetchone()[0]
        self.assertEqual(n, 0)
        digest = self.kernel.get_memory_digest()
        self.assertFalse(digest["dream_due"])
        self.assertTrue(digest["heal_due"])
        self.assertTrue(digest["behavior"])
        self.kernel.run_dream_simulation(
            "agent thought",
            outcomes=["Keep the current approach.", "Try the sharper alternative."],
        )
        self.assertFalse(self.kernel.daemon_worker.stats["dream_due"])
        self.kernel.stop_daemon()
        self.assertIsNone(self.kernel.daemon_worker)

    def test_08b_digest_behavior_without_daemon(self):
        digest = self.kernel.get_memory_digest()
        self.assertIn("behavior", digest)
        self.assertFalse(digest["dream_due"])
        self.assertFalse(digest["heal_due"])
        self.assertFalse(digest["reflect_due"])
        self.assertTrue(any("flatter" in line.lower() or "sycophancy" in line.lower() or "Obey sealed" in line for line in digest["behavior"]))

    def test_08d_dream_due_survives_restart(self):
        """dream_due is SQLite-backed; a new kernel on the same db sees it until outcomes record."""
        self.kernel._set_dream_due(True)
        db = self.db_path
        self.kernel.close()
        self.kernel = SoulKernel(db_path=db)
        self.assertTrue(self.kernel.get_memory_digest()["dream_due"])
        self.kernel.run_dream_simulation(
            "restart persist",
            outcomes=["Keep the flag until thought is recorded.", "Clear it after two imagined branches."],
        )
        self.kernel.close()
        self.kernel = SoulKernel(db_path=db)
        self.assertFalse(self.kernel.get_memory_digest()["dream_due"])

    def test_08c_reflect_empty_or_agent_written(self):
        empty = self.kernel.reflect_and_resolve()
        self.assertEqual(empty["status"], "empty")
        self.assertEqual(empty["interpretations"], [])
        ep1 = self.kernel.ingest_experience(EpisodeInput(
            source_kind="human", provenance="verified",
            content="User lives in Seattle Washington",
        ))
        self.kernel.verify_experience(ep1["episode_id"])
        ep2 = self.kernel.ingest_experience(EpisodeInput(
            source_kind="human", provenance="observed",
            content="User stopped living in Seattle Washington and moved away",
        ))
        self.kernel.verify_experience(ep2["episode_id"])
        pending = self.kernel.reflect_and_resolve()
        self.assertEqual(pending["status"], "needs_thought")
        self.assertTrue(pending["tensions_analyzed"])
        with self.assertRaises(ValueError):
            self.kernel.reflect_and_resolve(interpretations=[
                {"hypothesis": "User preference evolution detected.", "action": "none"},
            ])
        ver = self.kernel.get_current_state().soul_version
        recorded = self.kernel.reflect_and_resolve(interpretations=[
            {"hypothesis": "The later observed move supersedes the Seattle fact.", "action": "supersede_stale_memories"},
            {"hypothesis": "Both can be true across time if dated.", "action": "retain_both_with_qualifiers"},
        ])
        self.assertEqual(recorded["status"], "recorded")
        self.assertIn("supersede", recorded["recommended_action"])
        self.assertEqual(self.kernel.get_current_state().soul_version, ver)

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
            task_context="Benchmark Suite 100% Passed",
            evidence_receipt="bench_suite_100",
        )
        st_pos = self.kernel.process_reward(sig_pos)
        self.assertGreater(self.kernel.bio_engine.dopamine, 0.0)
        self.assertGreaterEqual(st_pos.traits["audacity"], 85.0)

        # Negative reward signal
        rid = _output_review_receipt(self.kernel, "sess_bio")
        sig_neg = RewardSignal(
            source="external_human",
            valence=-1.0,
            confidence=1.0,
            task_context="Regressed on unit test suite",
            review_receipt=rid,
        )
        st_neg = self.kernel.process_reward(sig_neg, session_id="sess_bio")
        self.assertGreater(self.kernel.bio_engine.cortisol, 0.0)
        self.assertGreaterEqual(st_neg.traits["epistemic_humility"], 85.0)

        # Step homeostasis decay
        st_decay = self.kernel.step_homeostasis()
        self.assertLess(self.kernel.bio_engine.cortisol, 1.0)
        self.assertEqual(
            self.kernel.bio_engine.serotonin,
            round(1.0 - max(self.kernel.bio_engine.dopamine, self.kernel.bio_engine.cortisol), 4),
        )
        da, co, se = (
            self.kernel.bio_engine.dopamine,
            self.kernel.bio_engine.cortisol,
            self.kernel.bio_engine.serotonin,
        )
        self.assertGreater(da + co, 0.0)
        db = self.db_path
        self.kernel.close()
        self.kernel = SoulKernel(db_path=db)
        self.assertEqual(self.kernel.bio_engine.dopamine, da)
        self.assertEqual(self.kernel.bio_engine.cortisol, co)
        self.assertEqual(self.kernel.bio_engine.serotonin, se)
        with self.kernel._get_conn() as conn:
            row = conn.execute(
                "SELECT dopamine, cortisol, serotonin FROM neuromodulators ORDER BY soul_version DESC LIMIT 1;"
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], da)
        self.assertEqual(row[1], co)
        self.assertEqual(row[2], se)

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
            try:
                for i in range(5):
                    kernel.ingest_experience(EpisodeInput(
                        source_kind="agent",
                        content=f"Concurrent memory stream from thread {tid} item {i}"
                    ))
            finally:
                kernel.close()

        threads = [threading.Thread(target=writer_thread, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        mems = self.kernel.recall_memories(limit=100, include_quarantined=True)
        self.assertGreaterEqual(len(mems), 20)

    def test_13_percept_admission_stays_quarantined(self):
        """Schema 8 percepts stay quarantined; digest/recall omit them; verify uses claims."""
        ep = self.kernel.ingest_experience(EpisodeInput(
            source_kind="human",
            content="User sent a photo of their desk.",
            medium="image",
            privacy_class="personal",
            source_ref="chat:desk-photo",
            content_ref="local://desk.jpg",
            percept_json={"claims": ["The desk is wooden."], "caption": "oak desk"},
        ))
        self.assertEqual(ep["status"], "quarantined")
        with self.kernel._get_conn() as conn:
            row = conn.execute(
                "SELECT medium, privacy_class, content_ref, percept_json, occurred_at, created_at FROM episodes WHERE id = ?;",
                (ep["episode_id"],),
            ).fetchone()
        self.assertEqual(row[0], "image")
        self.assertEqual(row[1], "personal")
        self.assertEqual(row[2], "local://desk.jpg")
        self.assertIn("wooden", row[3])
        self.assertEqual(row[4], row[5])
        digest_blob = json.dumps(self.kernel.get_memory_digest())
        self.assertNotIn("local://desk.jpg", digest_blob)
        self.assertNotIn("oak desk", digest_blob)
        self.assertEqual(self.kernel.recall_memories(query="desk", limit=5), [])
        raw = self.kernel.recall_memories(query="desk", limit=5, include_quarantined=True)
        self.assertTrue(raw)
        self.assertNotIn("percept_json", raw[0])
        self.assertNotIn("content_ref", raw[0])
        with self.assertRaises(ValueError):
            self.kernel.ingest_experience(EpisodeInput(
                source_kind="agent",
                content="huge percept",
                percept_json="x" * (PERCEPT_JSON_MAX_CHARS + 1),
            ))
        seattle = self.kernel.ingest_experience(EpisodeInput(
            source_kind="human",
            provenance="verified",
            content="User lives in Seattle Washington",
        ))
        self.kernel.verify_experience(seattle["episode_id"])
        travel = self.kernel.ingest_experience(EpisodeInput(
            source_kind="human",
            content="User travel notes",
            percept_json={"claims": ["User stopped living in Seattle Washington and moved away"]},
        ))
        ver = self.kernel.verify_experience(travel["episode_id"])
        self.assertEqual(ver["trust_state"], "contradicted")
        self.assertIn(seattle["episode_id"], ver["contradicting_refs"])

    def test_14_dream_packet_and_structured_branches(self):
        """Dream packet exposes load_bearing/analogical_cases; structured branches stay imagined."""
        ctx = self.kernel.run_dream_simulation("What if percepts leak into digest?")
        self.assertEqual(ctx["status"], "needs_thought")
        self.assertIn("load_bearing", ctx)
        self.assertIn("analogical_cases", ctx)
        self.assertIn("narrative", ctx)
        rec = self.kernel.run_dream_simulation(
            "What if percepts leak into digest?",
            outcomes=[
                {
                    "variable_flipped": "percepts_in_digest",
                    "outcome": "Recall still omits unreviewed percepts.",
                    "name": "quarantine_holds",
                    "likelihood": 0.7,
                },
                {
                    "hypothesis": "digest_leak",
                    "text": "Digest starts echoing image captions as facts.",
                    "severity": "high",
                },
            ],
        )
        self.assertEqual(rec["status"], "recorded")
        self.assertEqual(rec["provenance"], "imagined")
        self.assertEqual(len(rec["branches"]), 2)
        self.assertEqual(rec["branches"][0]["variable_flipped"], "percepts_in_digest")
        self.assertEqual(self.kernel.get_current_state().soul_version, 1)
        digest = self.kernel.get_memory_digest()
        facts = json.dumps(digest["active_facts"])
        self.assertNotIn("percepts_in_digest", facts)
        self.assertNotIn("Digest starts echoing", facts)
        self.assertEqual(digest["last_imagined"]["provenance"], "imagined")
        self.assertEqual(digest["last_imagined"]["dream_id"], rec["dream_id"])

    def test_15_quarantine_expiry_spares_sealed(self):
        """Expired unreviewed episodes leave extract/recall; sealed reviewed_memories stay."""
        sealed = self.kernel.ingest_experience(EpisodeInput(
            source_kind="human", provenance="observed", content="User prefers oolong tea"
        ))
        self.kernel.record_host_event(session_id="sess_expiry", origin_kind="human", payload="start")
        cycle = self.kernel.start_review_cycle(session_id="sess_expiry")
        self.kernel.apply_chat_review(
            session_id="sess_expiry",
            cycle_id=cycle["cycle_id"],
            decisions=[{"candidate_id": cycle["candidates"][0]["id"], "decision": "remember"}],
        )
        junk = self.kernel.ingest_experience(EpisodeInput(
            source_kind="agent", provenance="observed", content="Unreviewed junk that should age out"
        ))
        past = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=31)).isoformat()
        with self.kernel._get_conn() as conn:
            conn.execute(
                "UPDATE episodes SET retention_until = ? WHERE id IN (?, ?);",
                (past, sealed["episode_id"], junk["episode_id"]),
            )
            conn.commit()
        swept = self.kernel.expire_quarantine()
        self.assertGreaterEqual(swept["expired_count"], 1)
        with self.kernel._get_conn() as conn:
            sealed_state = conn.execute(
                "SELECT trust_state FROM episodes WHERE id = ?;", (sealed["episode_id"],)
            ).fetchone()[0]
            junk_state = conn.execute(
                "SELECT trust_state FROM episodes WHERE id = ?;", (junk["episode_id"],)
            ).fetchone()[0]
            live = conn.execute(
                "SELECT COUNT(*) FROM reviewed_memories WHERE deleted_at IS NULL AND retention_state = 'accessible';"
            ).fetchone()[0]
        self.assertNotEqual(sealed_state, "expired")
        self.assertEqual(junk_state, "expired")
        self.assertGreaterEqual(live, 1)
        facts = self.kernel.recall_memories(query="oolong", limit=5)
        self.assertTrue(any("oolong" in (f.get("content") or "") for f in facts))
        quarantined = self.kernel.recall_memories(query="junk", limit=10, include_quarantined=True)
        self.assertFalse(any("age out" in (f.get("content") or "") for f in quarantined))
        self.kernel.record_host_event(session_id="sess_expiry_2", origin_kind="human", payload="start2")
        later = self.kernel.start_review_cycle(session_id="sess_expiry_2")
        texts = [c["canonical_text"] for c in later["candidates"]]
        self.assertFalse(any("age out" in t for t in texts))
        digest = self.kernel.get_memory_digest()
        self.assertIn("expired_count", digest)
        self.assertTrue(any("oolong" in (f.get("content") or "") for f in digest["active_facts"]))

    def test_16_trait_drift_log_is_not_recall(self):
        """Reward/heal/update append drift rows; recall does not treat them as facts."""
        before = self.kernel.get_current_state().traits["audacity"]
        self.kernel.update_trait(TraitUpdate(trait="audacity", new_value=min(100.0, before + 5.0), evidence_refs=["drift-a", "drift-b"]))
        self.kernel.process_reward(RewardSignal(
            source="external_test", valence=1.0, confidence=1.0, task_context="drift log",
            evidence_receipt="drift_log_receipt",
        ))
        drifted = self.kernel.get_current_state()
        self.kernel.heal_soul_state(level=1, reason="drift-log check")
        with self.kernel._get_conn() as conn:
            rows = conn.execute(
                "SELECT trait, source FROM trait_drift_log ORDER BY id;"
            ).fetchall()
        sources = {r[1] for r in rows}
        self.assertIn("update", sources)
        self.assertIn("reward", sources)
        self.assertIn("heal", sources)
        digest_blob = json.dumps(self.kernel.get_memory_digest())
        self.assertNotIn("trait_drift_log", digest_blob)
        self.assertEqual(self.kernel.recall_memories(query="drift log", limit=5), [])


if __name__ == "__main__":
    unittest.main()
