"""Runnable checks for the 2026-08-23 audit bugfixes."""

from __future__ import annotations

import gc
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from soul_kernel import SoulKernel, EpisodeInput
from soul_mcp_server import _handle_jsonrpc
import soul_mcp_server
from install import register_mcp_config


def _mcp(name: str, arguments: dict, req_id: int = 1) -> dict:
    res = _handle_jsonrpc({
        "jsonrpc": "2.0",
        "id": req_id,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    })
    if "error" in res:
        return {"rpc_error": res["error"]}
    return json.loads(res["result"]["content"][0]["text"])


class TestAuditBugfixes(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "bugfix.db")
        self.kernel = SoulKernel(db_path=self.db_path)
        os.environ["SOUL_DB_PATH"] = self.db_path
        soul_mcp_server._kernel = self.kernel

    def tearDown(self):
        if self.kernel:
            self.kernel.close()
        soul_mcp_server._kernel = None
        self.kernel = None
        gc.collect()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_mcp_rollback_and_heal_require_human_event(self):
        rb = _mcp("soul_rollback", {"target_version": 1, "reason": "spoof"})
        self.assertEqual(rb.get("status"), "failed")
        self.assertIn("human", str(rb.get("error", "")).lower())

        fake = _mcp("soul_host_event", {"session_id": "bf_rb", "origin_kind": "human"})
        rb2 = _mcp("soul_rollback", {
            "target_version": 1,
            "human_event_ref": fake["event_id"],
        })
        self.assertEqual(rb2.get("status"), "failed")

        heal = _mcp("soul_heal", {"level": 1})
        self.assertIn("human", str(heal.get("error", "")).lower())

        before = self.kernel.get_current_state().soul_version
        self.kernel.rollback_to_version(1, operator_reason="trusted local API")
        self.assertGreaterEqual(self.kernel.get_current_state().soul_version, before)

    def test_heal_does_not_multiply_identity_versions_at_setpoint(self):
        before = self.kernel.get_current_state().soul_version
        res = self.kernel.heal_soul_state(level=1, reason="noop check")
        after = self.kernel.get_current_state().soul_version
        self.assertEqual(res["status"], "recalibrated")
        self.assertEqual(res.get("versions_written", 0), 0)
        self.assertEqual(after, before)

    def test_session_only_and_keep_both_are_not_preview_noops(self):
        self.kernel.ingest_experience(EpisodeInput(source_kind="human", content="Keep this in session only"))
        human = self.kernel.record_host_event(session_id="bf_so", origin_kind="human", payload="start")
        self.assertEqual(human.event_kind, "conversation")
        cycle = self.kernel.start_review_cycle(session_id="bf_so")
        cand = cycle["candidates"][0]["id"]
        self.kernel.record_review_decision(
            cycle_id=cycle["cycle_id"],
            candidate_id=cand,
            decision="session_only",
            human_event_ref=human.id,
        )
        preview = self.kernel.preview_review_cycle(cycle["cycle_id"])
        self.assertEqual(len(preview["session_only"]), 1)
        self.assertEqual(len(preview["additions"]), 0)
        self.kernel.commit_review_cycle(
            cycle["cycle_id"],
            commit_human_event_ref=self.kernel.record_host_event(
                session_id="bf_so", origin_kind="human", payload="commit"
            ).id,
        )

        self.kernel.ingest_experience(EpisodeInput(source_kind="human", content="Promote via keep_both"))
        human2 = self.kernel.record_host_event(session_id="bf_kb", origin_kind="human", payload="start")
        cycle2 = self.kernel.start_review_cycle(session_id="bf_kb")
        cand2 = cycle2["candidates"][0]["id"]
        self.kernel.record_review_decision(
            cycle_id=cycle2["cycle_id"],
            candidate_id=cand2,
            decision="keep_both_with_context",
            human_event_ref=human2.id,
        )
        self.kernel.preview_review_cycle(cycle2["cycle_id"])
        commit = self.kernel.commit_review_cycle(
            cycle2["cycle_id"],
            commit_human_event_ref=self.kernel.record_host_event(
                session_id="bf_kb", origin_kind="human", payload="commit"
            ).id,
        )
        self.assertGreaterEqual(len(commit["promoted_memory_ids"]), 1)

    def test_seal_packet_commits_without_mcp_human(self):
        self.kernel.ingest_experience(EpisodeInput(source_kind="human", content="User prefers Neovim"))
        cycle = self.kernel.start_review_cycle(session_id="seal_sess", trigger_kind="explicit")
        self.assertGreaterEqual(cycle["candidate_count"], 1)
        packet_path = os.path.join(self.temp_dir.name, "review_packet.json")
        Path(packet_path).write_text(json.dumps({
            "session_id": "seal_sess",
            "cycle_id": cycle["cycle_id"],
            "decisions": [{"candidate_id": cycle["candidates"][0]["id"], "decision": "remember"}],
        }), encoding="utf-8")
        self.kernel.close()
        self.kernel = None
        from soul_host import seal_packet
        out = seal_packet(packet_path, require_tty=False)
        self.assertEqual(out["status"], "committed")
        self.assertEqual(len(out["decision_events"]), 1)
        self.assertTrue(out["commit_event"])
        self.assertNotEqual(out["decision_events"][0], out["commit_event"])
        self.assertGreaterEqual(len(out["receipt"]["promoted_memory_ids"]), 1)

    def test_installer_skips_yaml_goose_config(self):
        yaml_path = Path(self.temp_dir.name) / "config.yaml"
        yaml_path.write_text("provider: goose\n", encoding="utf-8")
        register_mcp_config(yaml_path, ROOT / "soul_mcp_server.py", Path(self.db_path), sys.executable)
        self.assertEqual(yaml_path.read_text(encoding="utf-8"), "provider: goose\n")

    def test_mcp_initialize_tells_every_harness_to_seal(self):
        res = soul_mcp_server._handle_jsonrpc({
            "jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {},
        })
        ins = res["result"]["instructions"]
        self.assertIn("SEAL", ins)
        self.assertNotIn("grill", ins.lower())
        self.assertTrue((ROOT / "skills" / "soul-seal" / "SKILL.md").is_file())
        self.assertTrue((ROOT / ".claude" / "skills" / "soul-seal" / "SKILL.md").is_file())
        from install import seal_skill_user_dirs
        dirs = [str(p).replace("\\", "/") for p in seal_skill_user_dirs()]
        self.assertTrue(any("/.gemini/config/skills/soul-seal" in d for d in dirs))
        self.assertTrue(any("/.pi/agent/skills/soul-seal" in d for d in dirs))
        self.assertTrue(any("/.agents/skills/soul-seal" in d for d in dirs))
        self.assertTrue((ROOT / ".agents" / "skills" / "soul-seal" / "SKILL.md").is_file())


if __name__ == "__main__":
    unittest.main(verbosity=2)
