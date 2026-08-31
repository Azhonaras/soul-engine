"""v1.2.0 audit round-2 regression tests (2026-08-26): one test per fix."""

from __future__ import annotations

import inspect
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from soul_kernel import SoulKernel, EpisodeInput, RewardSignal, TraitUpdate
from soul_mcp_server import _handle_jsonrpc


def _mcp(name: str, arguments: dict, req_id: int = 1) -> dict:
    res = _handle_jsonrpc({
        "jsonrpc": "2.0", "id": req_id,
        "method": "tools/call", "params": {"name": name, "arguments": arguments},
    })
    try:
        return json.loads(res["result"]["content"][0]["text"])
    except Exception:
        return res


import json  # noqa: E402


class Round2Regression(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="soul_r2_")

    def _kernel(self, name):
        k = SoulKernel(db_path=os.path.join(self.tmp, name))
        self.addCleanup(k.close)
        return k

    def test_a2_dream_trust_zero_survives_restart(self):
        k = self._kernel("a2.db")
        k.get_current_state()  # ensure genesis row exists (else _persist_bio no-ops)
        k.bio_engine.dream_trust["ctx0"] = 0.0
        with k._get_conn() as conn:
            k._persist_bio(conn)
        k.close()
        k2 = SoulKernel(db_path=os.path.join(self.tmp, "a2.db"))
        self.addCleanup(k2.close)
        self.assertEqual(k2.bio_engine.dream_trust.get("ctx0"), 0.0,
                         "legit 0.0 trust corrupted to default on reload")

    def test_a3_external_test_receipt_replay_rejected(self):
        k = self._kernel("a3.db")
        sig = RewardSignal(source="external_test", valence=0.5, confidence=0.5,
                           task_context="replay-ctx", evidence_receipt="rcp_replay_01")
        k.process_reward(sig)
        with self.assertRaises(ValueError):
            k.process_reward(RewardSignal(
                source="external_test", valence=0.5, confidence=0.5,
                task_context="replay-ctx", evidence_receipt="rcp_replay_01"))

    def test_a3b_external_test_short_or_punctuated_receipt_rejected(self):
        k = self._kernel("a3b.db")
        for bad in ("x!y", "ab"):
            with self.assertRaises(ValueError):
                k.process_reward(RewardSignal(
                    source="external_test", valence=0.5, confidence=0.5,
                    task_context="fmt-ctx", evidence_receipt=bad))

    def test_a4_dream_score_requires_redeemed_receipt(self):
        k = self._kernel("a4.db")
        k.run_dream_simulation(scenario_prompt="s", outcomes=[
            {"outcome": "a", "likelihood": 0.6},
            {"outcome": "b", "likelihood": -0.8}], task_context="gate-ctx")
        with self.assertRaises(ValueError):
            k.score_dreams_against_reality(-1.0, 1.0, "gate-ctx")  # no receipt
        with self.assertRaises(ValueError):
            k.score_dreams_against_reality(-1.0, 1.0, "gate-ctx",
                                           evidence_receipt="rcp_never_seen")  # unredeemed
        rid = "rcp_gate_ctx_ok"
        k.process_reward(RewardSignal(source="external_test", valence=0.05,
                                      confidence=0.5, task_context="gate-ctx",
                                      evidence_receipt=rid))
        res = k.score_dreams_against_reality(-1.0, 1.0, "gate-ctx",
                                             evidence_receipt=rid)
        self.assertEqual(res["status"], "scored")

    def test_a7_mcp_reward_non_numeric_valence_is_rejected_not_crash(self):
        out = _mcp("soul_reward", {"source": "external_test", "valence": "abc",
                                   "task_context": "t"})
        self.assertEqual(out.get("status"), "rejected")

    def test_a9_invalidate_refuses_non_provisional_and_terminal_cycles(self):
        k = self._kernel("a9.db")
        with self.assertRaises(ValueError):
            k.invalidate_provisional_cycle("mcycle_missing")

    def test_a10_single_bump_wallet_definition(self):
        import soul_kernel as sk
        src = inspect.getsource(sk)
        self.assertEqual(src.count("def _bump_wallet"), 1)

    def test_a12_quarantine_recall_returns_hits(self):
        k = self._kernel("a12.db")
        for i in range(30):
            k.ingest_experience(EpisodeInput(
                source_kind="agent", content=f"bulk episode {i} zebra"))
        hits = k.recall_memories("zebra", include_quarantined=True)
        self.assertTrue(hits)

    def test_nit1_install_tool_split(self):
        import install
        import soul_mcp_server
        inst_src = inspect.getsource(install)
        self.assertIn("23 Active MCP Tools (14 Core + 9 Review Cycle)", inst_src)
        self.assertEqual(len(soul_mcp_server.TOOLS), 23)

    def test_nit2_exact_receipt_matching_no_substring_collision(self):
        k = self._kernel("nit2.db")
        k.run_dream_simulation(scenario_prompt="sub", outcomes=[
            {"outcome": "hit", "likelihood": 0.5},
            {"outcome": "miss", "likelihood": -0.5}], task_context="sub-ctx")
        k.process_reward(RewardSignal(
            source="external_test", valence=0.5, confidence=0.5,
            task_context="sub-ctx", evidence_receipt="rcp_long_receipt_123"))
        # rcp_long_receipt is a prefix/substring of rcp_long_receipt_123, but NOT exact match
        with self.assertRaises(ValueError):
            k.score_dreams_against_reality(0.5, 0.5, "sub-ctx", evidence_receipt="rcp_long_receipt")
        # exact match succeeds
        res = k.score_dreams_against_reality(0.5, 0.5, "sub-ctx", evidence_receipt="rcp_long_receipt_123")
        self.assertEqual(res["status"], "scored")

    def test_layer1_tier1_chat_review_succeeds(self):
        k = self._kernel("t1.db")
        k.ingest_experience(EpisodeInput(source_kind="agent", content="Fact: python is dynamic"))
        c = k.start_review_cycle(session_id="chat_s1", trigger_kind="explicit")
        cands = c.get("candidates") or []
        self.assertTrue(len(cands) > 0)
        cid = cands[0]["id"]
        res = k.apply_chat_review(
            session_id="chat_s1",
            cycle_id=c["cycle_id"],
            decisions=[{"candidate_id": cid, "decision": "remember"}],
        )
        self.assertIn("receipt", res)
        self.assertEqual(res["receipt"]["cycle_id"], c["cycle_id"])

    def test_layer1_tier2_destructive_chat_rejected(self):
        k = self._kernel("t2_reject.db")
        with self.assertRaises(PermissionError):
            k.apply_chat_memory_rollback("chat_s1", target_version=1)
        with self.assertRaises(PermissionError):
            k.apply_chat_memory_delete("chat_s1", memory_id="mem_fake")
        with self.assertRaises(PermissionError):
            k.apply_chat_identity_rollback("chat_s1", target_version=1)
        with self.assertRaises(PermissionError):
            k.apply_chat_heal("chat_s1", level=2)
        # Level 1 heal is Tier 1 (safe homeostatic recalibration) and succeeds
        heal_res = k.apply_chat_heal("chat_s1", level=1)
        self.assertIn("status", heal_res)

    def test_layer1_tier2_authorized_host_event_succeeds(self):
        k = self._kernel("t2_host.db")
        k.ingest_experience(EpisodeInput(source_kind="agent", content="Fact to delete"))
        c = k.start_review_cycle(session_id="chat_s2", trigger_kind="explicit")
        cid = c["candidates"][0]["id"]
        res = k.apply_chat_review(
            session_id="chat_s2",
            cycle_id=c["cycle_id"],
            decisions=[{"candidate_id": cid, "decision": "remember"}],
        )
        memories = k.list_active_reviewed_memories()
        self.assertEqual(len(memories), 1)
        target_mem = memories[0]["memory_id"]

        # Directly calling with a real human host event succeeds
        del_ev = k.record_host_event(
            session_id="out_of_band_host",
            origin_kind="human",
            event_kind="memory_deletion",
            payload={"memory_id": target_mem},
        )
        del_res = k.delete_reviewed_memory(memory_id=target_mem, human_event_ref=del_ev.id)
        self.assertEqual(del_res["status"], "deleted")
        self.assertEqual(len(k.list_active_reviewed_memories()), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
