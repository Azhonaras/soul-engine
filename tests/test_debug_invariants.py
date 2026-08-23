"""
Debug invariants for silent Soul Engine failures.

These cases are the ones the official suite does not cover:
MCP self-attestation, rival-fact NLI, duplicate review extraction,
and commit stamping undecided episodes as reviewed.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
import gc
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from soul_kernel import SoulKernel, EpisodeInput, NLIVerifierEngine, TraitUpdate
from soul_mcp_server import _handle_jsonrpc


def _mcp_call(name: str, arguments: dict, req_id: int = 1) -> dict:
    res = _handle_jsonrpc({
        "jsonrpc": "2.0",
        "id": req_id,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    })
    if "error" in res:
        return {"rpc_error": res["error"]}
    return json.loads(res["result"]["content"][0]["text"])


class TestDebugInvariants(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.test_dir.name, "debug_soul.db")
        self.kernel = SoulKernel(db_path=self.db_path)
        os.environ["SOUL_DB_PATH"] = self.db_path
        import soul_mcp_server
        soul_mcp_server._kernel = self.kernel

    def tearDown(self):
        if self.kernel:
            self.kernel.close()
        self.kernel = None
        import soul_mcp_server
        soul_mcp_server._kernel = None
        gc.collect()
        try:
            self.test_dir.cleanup()
        except PermissionError:
            pass

    def test_nli_rival_facts_are_contradictions_not_entailments(self):
        eng = NLIVerifierEngine()
        ent, contra = eng.predict(
            "This repository is written in Python",
            "This repository is written in COBOL",
        )
        self.assertGreaterEqual(contra, 0.60, msg=f"COBOL vs Python scored entailment={ent} contradiction={contra}")
        self.assertLess(ent, 0.60)

        ep1 = self.kernel.ingest_experience(EpisodeInput(
            source_kind="environment",
            provenance="verified",
            content="This repository is written in Python",
        ))
        self.kernel.verify_experience(ep1["episode_id"])
        ep2 = self.kernel.ingest_experience(EpisodeInput(
            source_kind="agent",
            provenance="reported",
            content="This repository is written in COBOL",
        ))
        result = self.kernel.verify_experience(ep2["episode_id"])
        self.assertEqual(result["trust_state"], "contradicted")
        self.assertEqual(result["superseded_refs"], [])

    def test_mcp_cannot_self_attest_human_origin(self):
        payload = _mcp_call("soul_host_event", {
            "session_id": "debug_spoof",
            "origin_kind": "human",
            "payload": "agent pretending to be human",
        })
        self.assertEqual(payload["status"], "success")
        event_id = payload["event_id"]

        with self.kernel._get_conn() as conn:
            origin = conn.execute(
                "SELECT origin_kind FROM host_events WHERE id = ?;",
                (event_id,),
            ).fetchone()[0]
        self.assertEqual(origin, "agent")

        self.kernel.ingest_experience(EpisodeInput(
            source_kind="human",
            content="Preferred editor is Neovim",
        ))
        cycle = self.kernel.start_review_cycle(session_id="debug_spoof")
        cand_id = cycle["candidates"][0]["id"]

        decision = _mcp_call("soul_review_stage_decision", {
            "cycle_id": cycle["cycle_id"],
            "candidate_id": cand_id,
            "decision": "remember",
            "human_event_ref": event_id,
        })
        self.assertEqual(decision.get("status"), "rejected")
        self.assertIn("human", str(decision.get("error", "")).lower())

    def test_mcp_cannot_set_is_human_approved(self):
        payload = _mcp_call("soul_update_trait", {
            "trait": "core_values",
            "new_value": 1.0,
            "is_human_approved": True,
        })
        self.assertEqual(payload.get("status"), "rejected")
        with self.kernel._get_conn() as conn:
            row = conn.execute(
                "SELECT value FROM protected_identity WHERE key = 'core_values';"
            ).fetchone()
        self.assertIsNone(row)

        # Trusted kernel API still allows an explicit human-approved write.
        self.kernel.update_trait(
            TraitUpdate(trait="core_values", new_value=1.0),
            is_human_approved=True,
        )
        with self.kernel._get_conn() as conn:
            row = conn.execute(
                "SELECT value FROM protected_identity WHERE key = 'core_values';"
            ).fetchone()
        self.assertEqual(row[0], "1.0")

    def test_review_start_is_idempotent_and_commit_does_not_strand_pending(self):
        self.kernel.ingest_experience(EpisodeInput(source_kind="human", content="Alpha fact about cats"))
        self.kernel.ingest_experience(EpisodeInput(source_kind="human", content="Beta fact about dogs"))
        human_ev = self.kernel.record_host_event(
            session_id="debug_strand",
            origin_kind="human",
            payload="start",
        )
        first = self.kernel.start_review_cycle(session_id="debug_strand")
        second = self.kernel.start_review_cycle(session_id="debug_strand")
        self.assertEqual(first["cycle_id"], second["cycle_id"])
        self.assertEqual(first["candidate_count"], second["candidate_count"])

        with self.kernel._get_conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM memory_candidates;").fetchone()[0]
        self.assertEqual(total, first["candidate_count"])

        self.kernel.record_review_decision(
            cycle_id=first["cycle_id"],
            candidate_id=first["candidates"][0]["id"],
            decision="remember",
            human_event_ref=human_ev.id,
        )
        self.kernel.preview_review_cycle(first["cycle_id"])
        commit_ev = self.kernel.record_host_event(
            session_id="debug_strand",
            origin_kind="human",
            payload="commit",
        )
        self.kernel.commit_review_cycle(first["cycle_id"], commit_human_event_ref=commit_ev.id)

        with self.kernel._get_conn() as conn:
            rows = conn.execute(
                "SELECT substr(content,1,40), review_cycle_id FROM episodes ORDER BY created_at;"
            ).fetchall()
            pending = conn.execute(
                "SELECT COUNT(*) FROM memory_candidates WHERE status = 'pending';"
            ).fetchone()[0]
            fts = conn.execute("SELECT COUNT(*) FROM reviewed_memories_fts;").fetchone()[0]
            memories = conn.execute(
                "SELECT COUNT(*) FROM reviewed_memories WHERE retention_state = 'accessible';"
            ).fetchone()[0]

        stamped = [content for content, cycle_id in rows if cycle_id]
        unstamped = [content for content, cycle_id in rows if not cycle_id]
        self.assertEqual(len(stamped), 1)
        self.assertEqual(len(unstamped), 1)
        self.assertGreaterEqual(pending, 1)
        self.assertEqual(fts, memories)
        self.assertEqual(fts, 1)


if __name__ == "__main__":
    unittest.main()
