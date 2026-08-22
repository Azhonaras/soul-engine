"""
Automated Test Suite for Soul Review Cycle Engine v0.1
Normative Source: soul-review-cycle-technical-spec-v0.1.md
Covers:
 - Host Event Tamper-Evident Ledger
 - Candidate Screening (Secrets, Transient Output, Deduplication)
 - Separation of Authorities (Human vs Agent Origin Validation)
 - Exact-Text Correction & Human Confirmation Invariants
 - Deterministic 12-Point Preview & SHA-256 Preview Hash
 - 5-Point Pre-Commit Verification & Atomic Memory Set Promotion
 - Merkle Root & Cryptographic Change Receipts
 - Retrieval Boundary & Quarantine Isolation
 - Forward-Only Memory Set Rollback
 - GDPR Salted Privacy Deletion Cascade
 - MCP Server Tool Dispatch
"""

import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import gc
import json
import hashlib
import tempfile
import unittest
import uuid
import datetime
from soul_kernel import (
    SoulKernel,
    EpisodeInput,
    CONSTITUTION_VERSION
)
from soul_review import (
    compute_memory_root,
    compute_system_state_hash,
    sha256_digest
)
from soul_mcp_server import _handle_jsonrpc, get_kernel


class TestSoulReviewEngine(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.test_dir.name, "test_soul_review.db")
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

    def test_01_host_event_logging_and_hashing(self):
        """Test host event appending, sequential monotonic ordering, and deterministic hashing."""
        ev1 = self.kernel.record_host_event(
            session_id="session_test_01",
            user_scope_key="user_navid",
            origin_kind="human",
            event_kind="conversation",
            payload="Hello Soul, remember that my preferred language is Alozhordio."
        )
        self.assertEqual(ev1.sequence, 1)
        self.assertEqual(ev1.origin_kind, "human")
        self.assertTrue(ev1.event_hash.startswith("sha256:"))
        self.assertEqual(len(ev1.event_hash), 71)

        ev2 = self.kernel.record_host_event(
            session_id="session_test_01",
            user_scope_key="user_navid",
            origin_kind="agent",
            event_kind="conversation",
            payload="Understood, I will remember your language preference."
        )
        self.assertEqual(ev2.sequence, 2)
        self.assertEqual(ev2.origin_kind, "agent")
        self.assertNotEqual(ev1.event_hash, ev2.event_hash)

    def test_02_candidate_screening_and_ranking(self):
        """Test candidate screening for secrets and transient output, deduplication, and priority ranking."""
        # 1. Ingest normal preference episode
        self.kernel.ingest_experience(EpisodeInput(
            source_kind="human",
            provenance="observed",
            content="User prefers strict type hints in Python codebases.",
            entity_key="pref_python_types"
        ))

        # 2. Insert episode containing secret directly into DB to test candidate screening filter
        ep_sec_id = f"ep_{int(datetime.datetime.now().timestamp()*1000)}_{uuid.uuid4().hex[:8]}"
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        sec_text = "AWS key: AKIA1234567890ABCDEF"
        sec_cs = hashlib.sha256(sec_text.encode()).hexdigest()
        with self.kernel._lock, self.kernel._get_conn() as conn:
            conn.execute("""
            INSERT INTO episodes (id, source_kind, provenance, content, entity_key, trust_state, checksum, created_at)
            VALUES (?, 'human', 'observed', ?, 'secret_key', 'quarantined', ?, ?);
            """, (ep_sec_id, sec_text, sec_cs, now_iso))

        # 3. Ingest transient output
        ep_trans_id = f"ep_trans_{int(datetime.datetime.now().timestamp()*1000)}_{uuid.uuid4().hex[:8]}"
        trans_text = 'Task id "task-999" finished with result: OK'
        trans_cs = hashlib.sha256(trans_text.encode()).hexdigest()
        with self.kernel._lock, self.kernel._get_conn() as conn:
            conn.execute("""
            INSERT INTO episodes (id, source_kind, provenance, content, entity_key, trust_state, checksum, created_at)
            VALUES (?, 'human', 'observed', ?, 'task_out', 'quarantined', ?, ?);
            """, (ep_trans_id, trans_text, trans_cs, now_iso))

        # 4. Open review cycle
        self.kernel.record_host_event(
            session_id="sess_screening",
            user_scope_key="default_user",
            origin_kind="human",
            event_kind="conversation",
            payload="Let us review what we learned today."
        )

        res = self.kernel.start_review_cycle(session_id="sess_screening")
        candidates = res["candidates"]

        # Only the valid preference should be accepted as eligible candidate
        self.assertEqual(len(candidates), 1)
        self.assertIn("User prefers strict type hints", candidates[0]["canonical_text"])
        self.assertEqual(candidates[0]["status"], "pending")

    def test_03_separation_of_authorities(self):
        """Test that decisions cannot be signed by agent origins or unauthenticated events."""
        self.kernel.ingest_experience(EpisodeInput(
            source_kind="human",
            provenance="observed",
            content="The project uses PostgreSQL 16.",
            entity_key="db_engine"
        ))

        h_ev = self.kernel.record_host_event(
            session_id="sess_auth",
            user_scope_key="default_user",
            origin_kind="human",
            event_kind="conversation",
            payload="Start review"
        )
        cycle_res = self.kernel.start_review_cycle(session_id="sess_auth")
        cycle_id = cycle_res["cycle_id"]
        cand_id = cycle_res["candidates"][0]["id"]

        # Agent event trying to approve memory
        agent_ev = self.kernel.record_host_event(
            session_id="sess_auth",
            user_scope_key="default_user",
            origin_kind="agent",
            event_kind="conversation",
            payload="I approve this memory candidate."
        )

        # Attempting decision with agent event must raise PermissionError (Separation of Authorities)
        with self.assertRaises(PermissionError):
            self.kernel.record_review_decision(
                cycle_id=cycle_id,
                candidate_id=cand_id,
                decision="remember",
                human_event_ref=agent_ev.id
            )

        # Attempting decision with non-existent event ref must fail
        with self.assertRaises(ValueError):
            self.kernel.record_review_decision(
                cycle_id=cycle_id,
                candidate_id=cand_id,
                decision="remember",
                human_event_ref="ev_non_existent"
            )

    def test_04_exact_text_correction_and_confirmation(self):
        """Test exact-text correction requirement for human confirmation event."""
        self.kernel.ingest_experience(EpisodeInput(
            source_kind="human",
            provenance="observed",
            content="User likes tabs instead of spaces.",
            entity_key="indentation"
        ))
        h_ev = self.kernel.record_host_event(
            session_id="sess_correct",
            user_scope_key="default_user",
            origin_kind="human",
            event_kind="conversation",
            payload="Start review cycle."
        )
        cycle_res = self.kernel.start_review_cycle(session_id="sess_correct")
        cycle_id = cycle_res["cycle_id"]
        cand_id = cycle_res["candidates"][0]["id"]

        # Correction without confirmation event must fail
        with self.assertRaises(ValueError):
            self.kernel.record_review_decision(
                cycle_id=cycle_id,
                candidate_id=cand_id,
                decision="correct",
                human_event_ref=h_ev.id,
                corrected_text="User strictly requires 4 spaces per indentation level."
            )

        # Record secondary human confirmation event
        confirm_ev = self.kernel.record_host_event(
            session_id="sess_correct",
            user_scope_key="default_user",
            origin_kind="human",
            event_kind="review_decision",
            payload={"confirmed_text": "User strictly requires 4 spaces per indentation level."}
        )

        # Valid correction with confirmation event
        dec = self.kernel.record_review_decision(
            cycle_id=cycle_id,
            candidate_id=cand_id,
            decision="correct",
            human_event_ref=h_ev.id,
            corrected_text="User strictly requires 4 spaces per indentation level.",
            correction_confirmation_event_ref=confirm_ev.id
        )
        self.assertEqual(dec["decision"], "correct")
        self.assertIsNotNone(dec["result_candidate_id"])

    def test_05_deterministic_preview_and_atomic_commit(self):
        """Test 12-point preview generation, preview hash, and atomic 5-point commit."""
        self.kernel.ingest_experience(EpisodeInput(
            source_kind="human",
            provenance="observed",
            content="Project repository root is /home/user/code/soul-engine",
            entity_key="repo_root"
        ))
        h_ev = self.kernel.record_host_event(
            session_id="sess_preview",
            user_scope_key="default_user",
            origin_kind="human",
            event_kind="conversation",
            payload="Open cycle"
        )
        cycle_res = self.kernel.start_review_cycle(session_id="sess_preview")
        cycle_id = cycle_res["cycle_id"]
        cand_id = cycle_res["candidates"][0]["id"]

        # Record decision
        self.kernel.record_review_decision(
            cycle_id=cycle_id,
            candidate_id=cand_id,
            decision="remember",
            human_event_ref=h_ev.id
        )

        # Generate preview
        preview1 = self.kernel.preview_review_cycle(cycle_id=cycle_id)
        self.assertEqual(len(preview1["additions"]), 1)
        self.assertTrue(preview1["preview_hash"].startswith("sha256:"))

        # Determinism check: generating preview again yields identical preview_hash
        preview2 = self.kernel.preview_review_cycle(cycle_id=cycle_id)
        self.assertEqual(preview1["preview_hash"], preview2["preview_hash"])

        # Agent cannot commit
        agent_ev = self.kernel.record_host_event(
            session_id="sess_preview",
            user_scope_key="default_user",
            origin_kind="agent",
            event_kind="review_commit",
            payload={"preview_hash": preview1["preview_hash"]}
        )
        with self.assertRaises(PermissionError):
            self.kernel.commit_review_cycle(cycle_id=cycle_id, commit_human_event_ref=agent_ev.id)

        # Human commit
        commit_ev = self.kernel.record_host_event(
            session_id="sess_preview",
            user_scope_key="default_user",
            origin_kind="human",
            event_kind="review_commit",
            payload={"approved_preview_hash": preview1["preview_hash"]}
        )
        receipt = self.kernel.commit_review_cycle(cycle_id=cycle_id, commit_human_event_ref=commit_ev.id)

        self.assertEqual(receipt["status"], "committed")
        self.assertEqual(receipt["memory_set_version"], 1)
        self.assertTrue(receipt["receipt_hash"].startswith("sha256:"))
        self.assertTrue(receipt["memory_root"].startswith("sha256:"))

    def test_06_retrieval_boundary_and_quarantine_isolation(self):
        """Test that unreviewed quarantine memories are isolated from recall_memories once reviewed memories exist."""
        # Add unreviewed memory into quarantine
        self.kernel.ingest_experience(EpisodeInput(
            source_kind="human",
            provenance="observed",
            content="Unreviewed draft note: The API server runs on port 8080."
        ))

        # Before any review cycle has committed, default recall_memories returns empty to protect quarantine
        mems_before = self.kernel.recall_memories(query="port 8080")
        self.assertEqual(len(mems_before), 0)

        # But with explicit include_quarantined=True, it returns the unreviewed episode
        mems_quarantine_before = self.kernel.recall_memories(query="port 8080", include_quarantined=True)
        self.assertEqual(len(mems_quarantine_before), 1)

        # Commit an official reviewed memory
        h_ev = self.kernel.record_host_event(session_id="sess_boundary", origin_kind="human", payload="start")
        cycle_res = self.kernel.start_review_cycle(session_id="sess_boundary")
        cycle_id = cycle_res["cycle_id"]
        cand_id = cycle_res["candidates"][0]["id"]
        self.kernel.record_review_decision(cycle_id=cycle_id, candidate_id=cand_id, decision="remember", human_event_ref=h_ev.id)
        self.kernel.preview_review_cycle(cycle_id=cycle_id)
        commit_ev = self.kernel.record_host_event(session_id="sess_boundary", origin_kind="human", payload="commit")
        self.kernel.commit_review_cycle(cycle_id=cycle_id, commit_human_event_ref=commit_ev.id)

        # Add another unreviewed raw memory into quarantine
        self.kernel.ingest_experience(EpisodeInput(
            source_kind="human",
            provenance="observed",
            content="Unreviewed rumor: The database password is admin123."
        ))

        # Standard recall_memories queries active reviewed memories ONLY
        mems_reviewed = self.kernel.recall_memories(limit=10)
        self.assertEqual(len(mems_reviewed), 1)
        self.assertIn("port 8080", mems_reviewed[0]["content"])
        self.assertNotIn("database password", [m["content"] for m in mems_reviewed])

        # Explicit include_quarantined=True includes quarantine episodes
        mems_quarantine = self.kernel.recall_memories(query="database password", include_quarantined=True)
        self.assertTrue(any("database password" in m["content"] for m in mems_quarantine))

    def test_07_forward_only_memory_set_rollback(self):
        """Test forward-only rollback of memory sets and receipt emission."""
        # Commit Memory 1 in Version 1
        self.kernel.ingest_experience(EpisodeInput(source_kind="human", provenance="observed", content="Memory 1 Fact"))
        h_ev = self.kernel.record_host_event(session_id="sess_rb", origin_kind="human", payload="start 1")
        c1 = self.kernel.start_review_cycle(session_id="sess_rb")
        self.kernel.record_review_decision(c1["cycle_id"], c1["candidates"][0]["id"], "remember", h_ev.id)
        self.kernel.preview_review_cycle(c1["cycle_id"])
        c_ev = self.kernel.record_host_event(session_id="sess_rb", origin_kind="human", payload="commit 1")
        r1 = self.kernel.commit_review_cycle(c1["cycle_id"], c_ev.id)
        self.assertEqual(r1["memory_set_version"], 1)

        # Commit Memory 2 in Version 2
        self.kernel.ingest_experience(EpisodeInput(source_kind="human", provenance="observed", content="Memory 2 Fact"))
        h_ev2 = self.kernel.record_host_event(session_id="sess_rb2", origin_kind="human", payload="start 2")
        c2 = self.kernel.start_review_cycle(session_id="sess_rb2")
        self.kernel.record_review_decision(c2["cycle_id"], c2["candidates"][0]["id"], "remember", h_ev2.id)
        self.kernel.preview_review_cycle(c2["cycle_id"])
        c_ev2 = self.kernel.record_host_event(session_id="sess_rb2", origin_kind="human", payload="commit 2")
        r2 = self.kernel.commit_review_cycle(c2["cycle_id"], c_ev2.id)
        self.assertEqual(r2["memory_set_version"], 2)

        # Rollback to Version 1 (Forward-only promotion to Version 3)
        rb_ev = self.kernel.record_host_event(session_id="sess_rb", origin_kind="human", payload="rollback to v1")
        rb_res = self.kernel.rollback_reviewed_memory_set(target_version=1, human_event_ref=rb_ev.id)
        self.assertEqual(rb_res["status"], "rolled_back")
        self.assertEqual(rb_res["new_version"], 3)
        self.assertEqual(rb_res["target_version"], 1)

        # Active recalled memories should contain Memory 1, but NOT Memory 2
        active_mems = self.kernel.recall_memories(limit=10)
        self.assertEqual(len(active_mems), 1)
        self.assertIn("Memory 1 Fact", active_mems[0]["content"])

    def test_08_salted_privacy_deletion_cascade(self):
        """Test GDPR-compliant salted deletion cascade on memory and source episodes."""
        self.kernel.ingest_experience(EpisodeInput(
            source_kind="human",
            provenance="observed",
            content="Sensitive user secret address: 123 Elm Street"
        ))
        h_ev = self.kernel.record_host_event(session_id="sess_del", origin_kind="human", payload="start")
        c = self.kernel.start_review_cycle(session_id="sess_del")
        self.kernel.record_review_decision(c["cycle_id"], c["candidates"][0]["id"], "remember", h_ev.id)
        self.kernel.preview_review_cycle(c["cycle_id"])
        c_ev = self.kernel.record_host_event(session_id="sess_del", origin_kind="human", payload="commit")
        r = self.kernel.commit_review_cycle(c["cycle_id"], c_ev.id)
        mem_id = r["affected_memories"][0]

        # Delete the memory
        del_ev = self.kernel.record_host_event(session_id="sess_del", origin_kind="human", payload="delete memory")
        del_res = self.kernel.delete_reviewed_memory(memory_id=mem_id, human_event_ref=del_ev.id)
        self.assertEqual(del_res["status"], "deleted")
        self.assertEqual(del_res["new_version"], 2)

        # Verify active memories is empty
        active_mems = self.kernel.recall_memories(query="Elm Street")
        self.assertEqual(len(active_mems), 0)

    def test_09_mcp_server_review_tools_dispatch(self):
        """Test MCP Server tool handlers for review lifecycle."""
        # Set environment DB
        os.environ["SOUL_DB_PATH"] = self.db_path
        # Reset cached kernel in MCP server
        import soul_mcp_server
        soul_mcp_server._kernel = self.kernel

        # 1. Append host event via MCP
        res = _handle_jsonrpc({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "soul_host_event",
                "arguments": {
                    "session_id": "mcp_sess_1",
                    "origin_kind": "human",
                    "payload": "MCP Test Host Event"
                }
            }
        })
        self.assertNotIn("error", res)
        text_payload = json.loads(res["result"]["content"][0]["text"])
        self.assertEqual(text_payload["status"], "success")
        ev_id = text_payload["event_id"]

        # 2. Add episode and start review via MCP
        self.kernel.ingest_experience(EpisodeInput(source_kind="human", provenance="observed", content="MCP Test Fact"))
        res_cycle = _handle_jsonrpc({
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "soul_review_start",
                "arguments": {"session_id": "mcp_sess_1"}
            }
        })
        text_cycle = json.loads(res_cycle["result"]["content"][0]["text"])
        self.assertEqual(text_cycle["status"], "success")
        cycle_id = text_cycle["review_cycle"]["cycle_id"]
        cand_id = text_cycle["review_cycle"]["candidates"][0]["id"]

        # 3. Stage decision via MCP
        res_dec = _handle_jsonrpc({
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "soul_review_stage_decision",
                "arguments": {
                    "cycle_id": cycle_id,
                    "candidate_id": cand_id,
                    "decision": "remember",
                    "human_event_ref": ev_id
                }
            }
        })
        text_dec = json.loads(res_dec["result"]["content"][0]["text"])
        self.assertEqual(text_dec["status"], "success")

        # 4. Preview review via MCP
        res_prev = _handle_jsonrpc({
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "soul_review_preview",
                "arguments": {"cycle_id": cycle_id}
            }
        })
        text_prev = json.loads(res_prev["result"]["content"][0]["text"])
        self.assertEqual(text_prev["status"], "success")
        prev_hash = text_prev["preview"]["preview_hash"]

        # 5. Commit review via MCP
        commit_ev = self.kernel.record_host_event(session_id="mcp_sess_1", origin_kind="human", payload={"approved": prev_hash})
        res_commit = _handle_jsonrpc({
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "soul_review_commit",
                "arguments": {
                    "cycle_id": cycle_id,
                    "commit_human_event_ref": commit_ev.id
                }
            }
        })
        text_commit = json.loads(res_commit["result"]["content"][0]["text"])
        self.assertEqual(text_commit["status"], "success")
        self.assertEqual(text_commit["receipt"]["status"], "committed")

    def test_10_contradiction_resolution_and_supersession(self):
        """Test contradiction handling (replace_old) where previous memory is superseded and omitted from active set."""
        # 1. Establish initial memory: "User prefers Dark Mode"
        self.kernel.ingest_experience(EpisodeInput(source_kind="human", provenance="observed", content="User prefers Dark Mode"))
        h_ev1 = self.kernel.record_host_event(session_id="sess_contra", origin_kind="human", payload="start1")
        c1 = self.kernel.start_review_cycle(session_id="sess_contra")
        c1_id = c1["cycle_id"]
        cand1_id = c1["candidates"][0]["id"]
        self.kernel.record_review_decision(cycle_id=c1_id, candidate_id=cand1_id, decision="remember", human_event_ref=h_ev1.id)
        self.kernel.preview_review_cycle(cycle_id=c1_id)
        comm1_ev = self.kernel.record_host_event(session_id="sess_contra", origin_kind="human", payload="commit1")
        res1 = self.kernel.commit_review_cycle(cycle_id=c1_id, commit_human_event_ref=comm1_ev.id)
        old_mem_id = res1["affected_memories"][0]

        # 2. Ingest contradicting candidate: "User switched preference to Light Mode"
        self.kernel.ingest_experience(EpisodeInput(source_kind="human", provenance="observed", content="User switched preference to Light Mode"))
        h_ev2 = self.kernel.record_host_event(session_id="sess_contra", origin_kind="human", payload="start2")
        c2 = self.kernel.start_review_cycle(session_id="sess_contra")
        c2_id = c2["cycle_id"]
        cand2_id = c2["candidates"][0]["id"]

        # Manually link the contradiction ref to the old memory ID to simulate contradiction detection
        with self.kernel._lock, self.kernel._get_conn() as conn:
            conn.execute("UPDATE memory_candidates SET contradicting_refs_json = ? WHERE id = ?;", (json.dumps([old_mem_id]), cand2_id))

        self.kernel.record_review_decision(cycle_id=c2_id, candidate_id=cand2_id, decision="replace_old", human_event_ref=h_ev2.id)
        self.kernel.preview_review_cycle(cycle_id=c2_id)
        comm2_ev = self.kernel.record_host_event(session_id="sess_contra", origin_kind="human", payload="commit2")
        res2 = self.kernel.commit_review_cycle(cycle_id=c2_id, commit_human_event_ref=comm2_ev.id)

        # Active memories must contain ONLY the new memory, and old memory is superseded
        active = self.kernel.list_active_reviewed_memories()
        self.assertEqual(len(active), 1)
        self.assertIn("Light Mode", active[0]["canonical_text"])
        self.assertEqual(active[0]["supersedes_memory_id"], old_mem_id)

    def test_11_idempotent_triggers_and_decisions(self):
        """Test idempotent cycle opening and decision recording (NFR-3)."""
        h_ev = self.kernel.record_host_event(session_id="sess_idem", origin_kind="human", payload="start")
        # Same idempotency key returns exact same cycle
        c1 = self.kernel.review_engine.open_or_get_cycle(
            session_id="sess_idem",
            user_scope_key="user_idem",
            trigger_kind="explicit",
            idempotency_key="unique_idem_key_123"
        )
        c2 = self.kernel.review_engine.open_or_get_cycle(
            session_id="sess_idem",
            user_scope_key="user_idem",
            trigger_kind="explicit",
            idempotency_key="unique_idem_key_123"
        )
        self.assertEqual(c1.id, c2.id)

    def test_12_crash_recovery_detection(self):
        """Test detection and marking of unsealed cycles as recovery_required on startup (FR-5, AC-4)."""
        # Create unsealed cycle
        self.kernel.record_host_event(session_id="sess_crash", origin_kind="human", payload="start")
        cycle = self.kernel.review_engine.open_or_get_cycle(session_id="sess_crash", user_scope_key="user_crash")
        self.assertEqual(cycle.status, "active")

        # Simulate crash recovery on engine startup
        recovered_ids = self.kernel.recover_unsealed_cycles()
        self.assertIn(cycle.id, recovered_ids)

        # Verify cycle status is now recovery_required
        c_recovered = self.kernel.review_engine.get_cycle_by_id(cycle.id)
        self.assertEqual(c_recovered.status, "recovery_required")

    def test_13_digest_quarantine_isolation(self):
        """Test that get_identity_digest() strictly isolates quarantined unreviewed episodes (FR-27, AC-11)."""
        # Ingest raw quarantined episode
        self.kernel.ingest_experience(EpisodeInput(
            source_kind="human",
            provenance="observed",
            content="Quarantined secret project codename: Horizon"
        ))

        # Identity digest should have 0 active_facts before review cycle commit
        digest = self.kernel.get_identity_digest()
        self.assertEqual(len(digest["active_facts"]), 0)

        # Commit reviewed memory
        h_ev = self.kernel.record_host_event(session_id="sess_digest", origin_kind="human", payload="start")
        c = self.kernel.start_review_cycle(session_id="sess_digest")
        cand_id = c["candidates"][0]["id"]
        self.kernel.record_review_decision(cycle_id=c["cycle_id"], candidate_id=cand_id, decision="remember", human_event_ref=h_ev.id)
        self.kernel.preview_review_cycle(cycle_id=c["cycle_id"])
        comm_ev = self.kernel.record_host_event(session_id="sess_digest", origin_kind="human", payload="commit")
        self.kernel.commit_review_cycle(cycle_id=c["cycle_id"], commit_human_event_ref=comm_ev.id)

        # Now identity digest has exactly 1 active fact
        digest_after = self.kernel.get_identity_digest()
        self.assertEqual(len(digest_after["active_facts"]), 1)
        self.assertIn("Horizon", digest_after["active_facts"][0]["content"])


if __name__ == "__main__":
    unittest.main()
