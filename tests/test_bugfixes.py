"""Runnable checks for the 2026-08-23 audit bugfixes."""

from __future__ import annotations

import gc
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from soul_kernel import (
    SoulKernel, EpisodeInput, RewardSignal, TraitUpdate,
    _hrrl_trait_scale, DEFAULT_TRAITS,
)
from soul_mcp_server import _handle_jsonrpc
import soul_mcp_server
from install import register_mcp_config


def _output_review_receipt(kernel, session_id, content="sealed output for identity reward"):
    kernel.ingest_experience(EpisodeInput(source_kind="agent", content=content))
    cycle = kernel.start_review_cycle(session_id=session_id)
    out = kernel.apply_chat_review(
        session_id=session_id,
        cycle_id=cycle["cycle_id"],
        decisions=[{"candidate_id": cycle["candidates"][0]["id"], "decision": "remember"}],
    )
    return out["receipt"]["receipt_id"]


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

        chat_heal = _mcp("soul_heal", {"level": 1, "session_id": "chat_heal_sess", "reason": "seacom-style"})
        self.assertEqual(chat_heal.get("status"), "success")

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
        with self.kernel._get_conn() as conn:
            n = conn.execute(
                "SELECT COUNT(*) FROM reviewed_memories WHERE scope = 'session_only';"
            ).fetchone()[0]
        self.assertEqual(n, 1)
        self.assertFalse(any(
            "session only" in (m.get("content") or "").lower()
            for m in self.kernel.recall_memories(limit=20)
        ))
        self.assertFalse(any(
            "session only" in (m.get("content") or "").lower()
            for m in self.kernel.get_memory_digest(limit=20)["active_facts"]
        ))

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
        self.assertIn("soul_digest", ins)
        self.assertIn("soul_review_chat_commit", ins)
        self.assertIn("COMMIT", ins)
        self.assertIn("/seacom", ins)
        self.assertIn("soul_remember", ins)
        self.assertIn("when a piece of work is done", ins)
        self.assertIn("before starting a plan", ins)
        self.assertIn("subject is finished", ins)
        self.assertIn("skip the interview", ins)
        self.assertIn("Review plan", ins)
        self.assertIn("picks on the Review plan", ins)
        self.assertIn("picker", ins)
        session = (ROOT / ".cursor" / "rules" / "soul-session.mdc").read_text(encoding="utf-8")
        self.assertIn("when a piece of work is done", session)
        self.assertIn("before starting a plan", session)
        self.assertIn("skip the interview", session)
        self.assertIn("Review plan", session)
        self.assertIn("AskQuestion", session)
        self.assertTrue(any("/seacom" in line for line in self.kernel.get_memory_digest()["behavior"]))
        self.assertNotIn("grill", ins.lower())
        self.assertTrue((ROOT / "skills" / "soul-seal" / "SKILL.md").is_file())
        self.assertTrue((ROOT / "skills" / "seacom" / "SKILL.md").is_file())
        self.assertTrue((ROOT / ".claude" / "skills" / "soul-seal" / "SKILL.md").is_file())
        from install import seal_skill_user_dirs
        dirs = [str(p).replace("\\", "/") for p in seal_skill_user_dirs()]
        self.assertTrue(any("/.gemini/config/skills/soul-seal" in d for d in dirs))
        self.assertTrue(any("/.pi/agent/skills/soul-seal" in d for d in dirs))
        self.assertTrue(any("/.agents/skills/soul-seal" in d for d in dirs))
        self.assertTrue((ROOT / ".agents" / "skills" / "soul-seal" / "SKILL.md").is_file())

    def test_mcp_remember_cannot_claim_human(self):
        res = _mcp("soul_remember", {"content": "A quarantined note", "source_kind": "human"})
        self.assertEqual(res["status"], "success")
        ep_id = res["result"]["episode_id"]
        with self.kernel._get_conn() as conn:
            kind = conn.execute("SELECT source_kind FROM episodes WHERE id = ?;", (ep_id,)).fetchone()[0]
        self.assertEqual(kind, "agent")

    def test_chat_commit_replay_and_defer_only(self):
        self.kernel.ingest_experience(EpisodeInput(source_kind="agent", content="Defer me please"))
        cycle = self.kernel.start_review_cycle(session_id="bf_defer")
        cand = cycle["candidates"][0]["id"]
        deferred = self.kernel.apply_chat_review(
            session_id="bf_defer",
            cycle_id=cycle["cycle_id"],
            decisions=[{"candidate_id": cand, "decision": "defer"}],
        )
        self.assertEqual(deferred.get("status"), "deferred")
        self.assertIsNone(deferred.get("receipt"))
        status = self.kernel.review_engine.get_cycle_by_id(cycle["cycle_id"]).status
        self.assertNotEqual(status, "committed")

    def test_nli_python_vs_cobol_is_contradiction(self):
        ent, contra = self.kernel.nli_engine.predict(
            "This repository is written in Python",
            "This repository is written in COBOL",
        )
        self.assertGreaterEqual(contra, 0.6)
        self.assertGreater(contra, ent)

    def test_installer_registers_module_form_and_tool_count(self):
        from install import write_tool_schemas
        from soul_mcp_server import TOOLS
        cfg = Path(self.temp_dir.name) / "mcp.json"
        register_mcp_config(cfg, ROOT / "soul_mcp_server.py", Path(self.db_path), sys.executable, use_module=True)
        data = json.loads(cfg.read_text(encoding="utf-8"))
        self.assertEqual(data["mcpServers"]["soul"]["args"], ["-m", "soul_mcp_server"])
        self.assertEqual(len(TOOLS), 23)
        schema_dir = Path(self.temp_dir.name) / "schemas"
        self.assertEqual(write_tool_schemas(schema_dir), 23)
        self.assertTrue((schema_dir / "soul_review_chat_commit.json").is_file())
        self.assertTrue((schema_dir / "soul_solver_step.json").is_file())
        heal = json.loads((schema_dir / "soul_heal.json").read_text(encoding="utf-8"))
        self.assertIn("session_id", heal["parameters"]["properties"])
        self.assertNotIn("human_event_ref", heal["parameters"].get("required", []))
        remember = json.loads((schema_dir / "soul_remember.json").read_text(encoding="utf-8"))
        self.assertEqual(remember["parameters"]["properties"]["source_kind"]["default"], "agent")
        self.assertNotIn("human", remember["parameters"]["properties"]["source_kind"]["enum"])

    def test_preview_refuses_committed_cycle(self):
        self.kernel.ingest_experience(EpisodeInput(source_kind="human", content="Commit then preview must fail"))
        started = self.kernel.start_review_cycle(session_id="bf_prev")
        out = self.kernel.apply_chat_review(
            session_id="bf_prev",
            cycle_id=started["cycle_id"],
            decisions=[{
                "candidate_id": started["candidates"][0]["id"],
                "decision": "remember",
            }],
        )
        with self.assertRaises(ValueError):
            self.kernel.preview_review_cycle(out["receipt"]["cycle_id"])

    def test_host_seal_replay_does_not_double_promote(self):
        self.kernel.ingest_experience(EpisodeInput(source_kind="human", content="Seal once only"))
        cycle = self.kernel.start_review_cycle(session_id="bf_seal2")
        packet_path = os.path.join(self.temp_dir.name, "replay_packet.json")
        Path(packet_path).write_text(json.dumps({
            "session_id": "bf_seal2",
            "cycle_id": cycle["cycle_id"],
            "decisions": [{"candidate_id": cycle["candidates"][0]["id"], "decision": "remember"}],
        }), encoding="utf-8")
        self.kernel.close()
        self.kernel = None
        from soul_host import seal_packet
        first = seal_packet(packet_path, require_tty=False)
        self.assertEqual(first["status"], "committed")
        with self.assertRaises(ValueError):
            seal_packet(packet_path, require_tty=False)

    def test_delete_redacts_fts_candidates_and_preview(self):
        secret = "Sensitive user secret address: 99 Oak Lane"
        self.kernel.ingest_experience(EpisodeInput(source_kind="human", content=secret))
        human = self.kernel.record_host_event(session_id="bf_del", origin_kind="human", payload="start")
        cycle = self.kernel.start_review_cycle(session_id="bf_del")
        self.kernel.record_review_decision(cycle["cycle_id"], cycle["candidates"][0]["id"], "remember", human.id)
        preview = self.kernel.preview_review_cycle(cycle["cycle_id"])
        self.assertIn("Oak Lane", json.dumps(preview))
        mem_id = self.kernel.commit_review_cycle(
            cycle["cycle_id"],
            self.kernel.record_host_event(session_id="bf_del", origin_kind="human", payload="commit").id,
        )["affected_memories"][0]
        del_ev = self.kernel.record_host_event(session_id="bf_del", origin_kind="human", payload="delete")
        self.kernel.delete_reviewed_memory(memory_id=mem_id, human_event_ref=del_ev.id)
        with self.kernel._get_conn() as conn:
            fts = " ".join(r[0] or "" for r in conn.execute("SELECT content FROM episodes_fts;"))
            self.assertNotIn("Oak Lane", fts)
            texts = [r[0] for r in conn.execute("SELECT canonical_text FROM memory_candidates;")]
            self.assertTrue(texts)
            self.assertTrue(all(t == "[REDACTED]" for t in texts))
            previews = [r[0] or "" for r in conn.execute("SELECT preview_json FROM review_cycles;")]
            self.assertTrue(all("Oak Lane" not in p for p in previews))

    def test_entity_key_fills_contradicting_refs_without_sql_patch(self):
        ek = "pref.theme"
        self.kernel.ingest_experience(EpisodeInput(
            source_kind="human", content="User prefers Dark Mode", entity_key=ek,
        ))
        h1 = self.kernel.record_host_event(session_id="bf_ek", origin_kind="human", payload="s1")
        c1 = self.kernel.start_review_cycle(session_id="bf_ek")
        self.kernel.record_review_decision(c1["cycle_id"], c1["candidates"][0]["id"], "remember", h1.id)
        self.kernel.preview_review_cycle(c1["cycle_id"])
        old_id = self.kernel.commit_review_cycle(
            c1["cycle_id"],
            self.kernel.record_host_event(session_id="bf_ek", origin_kind="human", payload="c1").id,
        )["affected_memories"][0]
        self.kernel.ingest_experience(EpisodeInput(
            source_kind="human", content="User prefers Light Mode", entity_key=ek,
        ))
        c2 = self.kernel.start_review_cycle(session_id="bf_ek2")
        refs = c2["candidates"][0]["contradicting_refs"]
        self.assertIn(old_id, refs)
        h2 = self.kernel.record_host_event(session_id="bf_ek2", origin_kind="human", payload="s2")
        self.kernel.record_review_decision(c2["cycle_id"], c2["candidates"][0]["id"], "replace_old", h2.id)
        self.kernel.preview_review_cycle(c2["cycle_id"])
        self.kernel.commit_review_cycle(
            c2["cycle_id"],
            self.kernel.record_host_event(session_id="bf_ek2", origin_kind="human", payload="c2").id,
        )
        active = self.kernel.list_active_reviewed_memories()
        self.assertEqual(len(active), 1)
        self.assertIn("Light Mode", active[0]["canonical_text"])

    def test_defer_reappears_then_remember_replaces_decision(self):
        self.kernel.ingest_experience(EpisodeInput(source_kind="agent", content="Defer then remember me"))
        cycle = self.kernel.start_review_cycle(session_id="bf_def2")
        cand = cycle["candidates"][0]["id"]
        self.kernel.apply_chat_review(
            session_id="bf_def2",
            cycle_id=cycle["cycle_id"],
            decisions=[{"candidate_id": cand, "decision": "defer"}],
        )
        again = self.kernel.start_review_cycle(session_id="bf_def2")
        self.assertGreater(again["candidate_count"], 0)
        self.assertEqual(again["candidates"][0]["id"], cand)
        committed = self.kernel.apply_chat_review(
            session_id="bf_def2",
            cycle_id=cycle["cycle_id"],
            decisions=[{"candidate_id": cand, "decision": "remember"}],
        )
        self.assertIsNotNone(committed.get("receipt"))
        self.assertTrue(any("Defer then remember" in (m.get("content") or "") for m in self.kernel.recall_memories(limit=10)))

    def test_commit_rejects_event_before_preview(self):
        stale = self.kernel.record_host_event(session_id="bf_old", origin_kind="human", payload="too early")
        self.kernel.ingest_experience(EpisodeInput(source_kind="human", content="Needs a later commit event"))
        human = self.kernel.record_host_event(session_id="bf_old", origin_kind="human", payload="start")
        cycle = self.kernel.start_review_cycle(session_id="bf_old")
        self.kernel.record_review_decision(cycle["cycle_id"], cycle["candidates"][0]["id"], "remember", human.id)
        self.kernel.preview_review_cycle(cycle["cycle_id"])
        with self.assertRaises(ValueError):
            self.kernel.commit_review_cycle(cycle["cycle_id"], stale.id)

    def test_chat_commit_rejects_wrong_session(self):
        self.kernel.ingest_experience(EpisodeInput(source_kind="human", content="Bound to one chat"))
        cycle = self.kernel.start_review_cycle(session_id="bf_bind")
        with self.assertRaises(ValueError):
            self.kernel.apply_chat_review(
                session_id="someone-else",
                cycle_id=cycle["cycle_id"],
                decisions=[{"candidate_id": cycle["candidates"][0]["id"], "decision": "remember"}],
            )

    def test_heal_l3_freezes_ingest_until_l2(self):
        self.kernel.heal_soul_state(level=3, reason="freeze")
        with self.assertRaises(PermissionError):
            self.kernel.ingest_experience(EpisodeInput(source_kind="human", content="blocked while frozen"))
        self.kernel.heal_soul_state(level=2, reason="unfreeze")
        out = self.kernel.ingest_experience(EpisodeInput(source_kind="human", content="allowed after L2"))
        self.assertEqual(out["status"], "quarantined")

    def test_reflect_clears_digest_flag_without_identity_write(self):
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
        self.assertTrue(self.kernel.get_memory_digest()["reflect_due"])
        ver = self.kernel.get_current_state().soul_version
        self.kernel.reflect_and_resolve(interpretations=[
            {"hypothesis": "The later observed move supersedes the Seattle fact.", "action": "supersede_stale_memories"},
            {"hypothesis": "Both can be true across time if dated.", "action": "retain_both_with_qualifiers"},
        ])
        self.assertEqual(self.kernel.get_current_state().soul_version, ver)
        self.assertFalse(self.kernel.get_memory_digest()["reflect_due"])

    def test_password_assignment_is_rejected(self):
        with self.assertRaises(ValueError):
            self.kernel.ingest_experience(EpisodeInput(
                source_kind="human", content='login password="hunter2"',
            ))

    def test_installer_skips_non_json_mcp_file(self):
        cfg = Path(self.temp_dir.name) / "mcp.json"
        raw = '{"mcpServers": {}}\n// keep this comment\n'
        cfg.write_text(raw, encoding="utf-8")
        register_mcp_config(cfg, ROOT / "soul_mcp_server.py", Path(self.db_path), sys.executable)
        self.assertEqual(cfg.read_text(encoding="utf-8"), raw)

    def test_mcp_heal_without_session_sets_isError(self):
        res = soul_mcp_server._handle_jsonrpc({
            "jsonrpc": "2.0",
            "id": 9,
            "method": "tools/call",
            "params": {"name": "soul_heal", "arguments": {"level": 1}},
        })
        self.assertTrue(res["result"]["isError"])
        body = json.loads(res["result"]["content"][0]["text"])
        self.assertTrue(body.get("error"))

    def test_mcp_rejects_non_object_params(self):
        res = soul_mcp_server._handle_jsonrpc({
            "jsonrpc": "2.0", "id": 8, "method": "ping", "params": [],
        })
        self.assertEqual(res["error"]["code"], -32602)

    def test_ingest_does_not_supersede_sealed_source_episode(self):
        first = self.kernel.ingest_experience(EpisodeInput(
            source_kind="human", content="Theme is dark", entity_key="ui.theme",
        ))
        h = self.kernel.record_host_event(session_id="bf_sup", origin_kind="human", payload="s")
        c = self.kernel.start_review_cycle(session_id="bf_sup")
        self.kernel.record_review_decision(c["cycle_id"], c["candidates"][0]["id"], "remember", h.id)
        self.kernel.preview_review_cycle(c["cycle_id"])
        self.kernel.commit_review_cycle(
            c["cycle_id"],
            self.kernel.record_host_event(session_id="bf_sup", origin_kind="human", payload="c").id,
        )
        self.kernel.ingest_experience(EpisodeInput(
            source_kind="human", content="Theme is light", entity_key="ui.theme",
        ))
        with self.kernel._get_conn() as conn:
            ts = conn.execute(
                "SELECT trust_state FROM episodes WHERE id = ?;", (first["episode_id"],)
            ).fetchone()[0]
        self.assertNotEqual(ts, "superseded")

    def test_verify_checks_sealed_memories(self):
        self.kernel.ingest_experience(EpisodeInput(
            source_kind="human", content="This repository is written in Python",
        ))
        h = self.kernel.record_host_event(session_id="bf_ver", origin_kind="human", payload="s")
        c = self.kernel.start_review_cycle(session_id="bf_ver")
        self.kernel.record_review_decision(c["cycle_id"], c["candidates"][0]["id"], "remember", h.id)
        self.kernel.preview_review_cycle(c["cycle_id"])
        self.kernel.commit_review_cycle(
            c["cycle_id"],
            self.kernel.record_host_event(session_id="bf_ver", origin_kind="human", payload="c").id,
        )
        later = self.kernel.ingest_experience(EpisodeInput(
            source_kind="human", content="This repository is written in COBOL",
        ))
        out = self.kernel.verify_experience(later["episode_id"])
        self.assertTrue(out.get("contradicting_refs"))
        self.assertEqual(out["trust_state"], "contradicted")
        self.assertFalse(out.get("superseded_refs"))
        self.assertEqual(self.kernel.get_current_state().soul_version, 1)
        self.assertTrue(self.kernel.get_memory_digest()["reflect_due"])

    def test_reject_both_drops_old_active_memory(self):
        self.kernel.ingest_experience(EpisodeInput(
            source_kind="human", content="User prefers Dark Mode", entity_key="pref.theme",
        ))
        h1 = self.kernel.record_host_event(session_id="bf_rboth", origin_kind="human", payload="s1")
        c1 = self.kernel.start_review_cycle(session_id="bf_rboth")
        self.kernel.record_review_decision(c1["cycle_id"], c1["candidates"][0]["id"], "remember", h1.id)
        self.kernel.preview_review_cycle(c1["cycle_id"])
        self.kernel.commit_review_cycle(
            c1["cycle_id"],
            self.kernel.record_host_event(session_id="bf_rboth", origin_kind="human", payload="c1").id,
        )
        self.kernel.ingest_experience(EpisodeInput(
            source_kind="human", content="User prefers Light Mode", entity_key="pref.theme",
        ))
        h2 = self.kernel.record_host_event(session_id="bf_rboth2", origin_kind="human", payload="s2")
        c2 = self.kernel.start_review_cycle(session_id="bf_rboth2")
        self.kernel.record_review_decision(c2["cycle_id"], c2["candidates"][0]["id"], "reject_both", h2.id)
        self.kernel.preview_review_cycle(c2["cycle_id"])
        self.kernel.commit_review_cycle(
            c2["cycle_id"],
            self.kernel.record_host_event(session_id="bf_rboth2", origin_kind="human", payload="c2").id,
        )
        self.assertEqual(self.kernel.list_active_reviewed_memories(), [])

    def test_commit_rejects_stale_preview_after_new_decision(self):
        self.kernel.ingest_experience(EpisodeInput(source_kind="human", content="Preview must bind decisions"))
        human = self.kernel.record_host_event(session_id="bf_bind2", origin_kind="human", payload="s")
        cycle = self.kernel.start_review_cycle(session_id="bf_bind2")
        cand = cycle["candidates"][0]["id"]
        self.kernel.record_review_decision(cycle["cycle_id"], cand, "remember", human.id)
        self.kernel.preview_review_cycle(cycle["cycle_id"])
        self.kernel.record_review_decision(cycle["cycle_id"], cand, "reject", human.id)
        with self.assertRaises(ValueError):
            self.kernel.commit_review_cycle(
                cycle["cycle_id"],
                self.kernel.record_host_event(session_id="bf_bind2", origin_kind="human", payload="c").id,
            )

    def test_mcp_reward_requires_schema_fields(self):
        res = soul_mcp_server._handle_jsonrpc({
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "soul_reward", "arguments": {}},
        })
        self.assertTrue(res["result"]["isError"])

    def test_mcp_rejects_non_object_arguments(self):
        res = soul_mcp_server._handle_jsonrpc({
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "soul_digest", "arguments": []},
        })
        self.assertEqual(res["error"]["code"], -32602)

    def test_solver_step_does_not_write_identity_or_episodes(self):
        before_ver = self.kernel.get_current_state().soul_version
        with self.kernel._get_conn() as conn:
            before_eps = conn.execute("SELECT COUNT(*) FROM episodes;").fetchone()[0]
        self.kernel.record_solver_step(
            tool="pytest", method="run", outcome="fail", receipt="t1", error="boom",
        )
        self.kernel.record_solver_step(
            tool="pytest", method="fix", outcome="succeed", receipt="t2",
        )
        self.assertEqual(self.kernel.get_current_state().soul_version, before_ver)
        with self.kernel._get_conn() as conn:
            after_eps = conn.execute("SELECT COUNT(*) FROM episodes;").fetchone()[0]
        self.assertEqual(after_eps, before_eps)
        digest = self.kernel.get_memory_digest()
        self.assertEqual(len(digest["working"]), 2)
        self.assertEqual(digest["working"][0]["outcome"], "fail")
        self.assertEqual(digest["working"][1]["outcome"], "succeed")
        facts = " ".join((m.get("content") or "") for m in digest["active_facts"])
        self.assertNotIn("boom", facts)
        self.assertGreater(digest["session_neuromodulators"]["dopamine"], 0)
        self.assertEqual(digest["neuromodulators"]["dopamine"], 0.0)
        missing = _mcp("soul_solver_step", {"tool": "x", "method": "y", "outcome": "fail"})
        self.assertTrue(missing.get("rpc_error") or missing.get("error") or missing.get("status") == "rejected")
        self.kernel.record_solver_step(
            tool="grep", method="symbol", outcome="dead_end", receipt="t3", options_left=[],
        )
        self.assertTrue(self.kernel.get_memory_digest()["dream_due"])

    def test_unknown_decision_does_not_consume_episode(self):
        self.kernel.ingest_experience(EpisodeInput(source_kind="human", content="Must not be stamped by typo"))
        human = self.kernel.record_host_event(session_id="bf_typo", origin_kind="human", payload="s")
        cycle = self.kernel.start_review_cycle(session_id="bf_typo")
        cand = cycle["candidates"][0]["id"]
        with self.assertRaises(ValueError):
            self.kernel.record_review_decision(cycle["cycle_id"], cand, "yes", human.id)
        with self.kernel._get_conn() as conn:
            stamped = conn.execute(
                "SELECT COUNT(*) FROM episodes WHERE review_cycle_id IS NOT NULL;"
            ).fetchone()[0]
            decided = conn.execute("SELECT COUNT(*) FROM review_decisions;").fetchone()[0]
        self.assertEqual(stamped, 0)
        self.assertEqual(decided, 0)

    def test_decision_rejects_candidate_from_other_cycle(self):
        self.kernel.ingest_experience(EpisodeInput(source_kind="human", content="Cycle A only fact"))
        ca = self.kernel.start_review_cycle(session_id="bf_cross_a")
        self.kernel.ingest_experience(EpisodeInput(source_kind="human", content="Cycle B only fact"))
        cb = self.kernel.start_review_cycle(session_id="bf_cross_b")
        human = self.kernel.record_host_event(session_id="bf_cross_a", origin_kind="human", payload="s")
        other = next(c for c in cb["candidates"] if "Cycle B" in (c.get("canonical_text") or ""))
        with self.assertRaises(ValueError):
            self.kernel.record_review_decision(ca["cycle_id"], other["id"], "remember", human.id)

    def test_receipt_stores_live_tip_not_stale_cycle_base(self):
        self.kernel.ingest_experience(EpisodeInput(source_kind="human", content="Alpha fact unique-audit-aaa"))
        ca = self.kernel.start_review_cycle(session_id="bf_tip_a")
        self.kernel.ingest_experience(EpisodeInput(source_kind="human", content="Beta fact unique-audit-bbb"))
        cb = self.kernel.start_review_cycle(session_id="bf_tip_b")
        beta = next(c for c in cb["candidates"] if "Beta fact" in (c.get("canonical_text") or ""))
        self.kernel.apply_chat_review(
            session_id="bf_tip_b",
            cycle_id=cb["cycle_id"],
            decisions=[{"candidate_id": beta["id"], "decision": "remember"}],
        )
        alpha = next(c for c in ca["candidates"] if "Alpha fact" in (c.get("canonical_text") or ""))
        rec = self.kernel.apply_chat_review(
            session_id="bf_tip_a",
            cycle_id=ca["cycle_id"],
            decisions=[{"candidate_id": alpha["id"], "decision": "remember"}],
        )
        with self.kernel._get_conn() as conn:
            row = conn.execute(
                "SELECT prior_memory_set_version, rollback_reference FROM memory_change_receipts WHERE cycle_id=?;",
                (ca["cycle_id"],),
            ).fetchone()
        prior = rec["receipt"]["memory_set_version"] - 1
        self.assertEqual(row[0], prior)
        self.assertEqual(row[1], str(prior))
        self.assertGreater(prior, ca["base_memory_set_version"])

    def test_heal_rejects_invalid_level(self):
        with self.assertRaises(ValueError):
            self.kernel.heal_soul_state(level=4, reason="not a level")
        with self.assertRaises(ValueError):
            self.kernel.heal_soul_state(level=0, reason="not a level")

    def test_solver_step_rejects_secrets(self):
        with self.assertRaises(ValueError):
            self.kernel.record_solver_step(
                tool="curl", method="auth", outcome="fail",
                receipt="r1", error='login password="hunter2"',
            )
        self.assertEqual(self.kernel.get_memory_digest()["working"], [])

    def test_post_watermark_episode_is_not_extracted(self):
        opened = self.kernel.review_engine.open_or_get_cycle(session_id="bf_wm")
        self.kernel.ingest_experience(EpisodeInput(source_kind="human", content="Arrived after cycle opened"))
        cands = self.kernel.review_engine.extract_candidates_from_episodes(opened.id)
        self.assertEqual(len(cands), 0)

    def test_rollback_restores_tensions_flag(self):
        self.kernel._set_flag("unresolved_tensions", json.dumps(["live-tension"]))
        self.kernel.process_reward(RewardSignal(
            source="external_test", valence=0.2, confidence=1.0, task_context="bump version",
            evidence_receipt="rollback_tensions",
        ))
        self.kernel._set_flag("unresolved_tensions", json.dumps(["after-reward"]))
        self.assertEqual(self.kernel.get_current_state().unresolved_tensions, ["after-reward"])
        self.kernel.rollback_to_version(1, operator_reason="restore tensions")
        self.assertEqual(self.kernel.get_current_state().unresolved_tensions, [])

    def test_delete_cascade_uses_json_each_not_substring(self):
        self.kernel.ingest_experience(EpisodeInput(source_kind="human", content="Delete me unique-gdpr-aaa"))
        started = self.kernel.start_review_cycle(session_id="bf_gdpr")
        committed = self.kernel.apply_chat_review(
            session_id="bf_gdpr",
            cycle_id=started["cycle_id"],
            decisions=[{"candidate_id": started["candidates"][0]["id"], "decision": "remember"}],
        )
        mem_id = committed["receipt"]["promoted_memory_ids"][0]
        with self.kernel._get_conn() as conn:
            ep_id = conn.execute(
                "SELECT j.value FROM reviewed_memories r, json_each(r.source_episode_refs_json) j WHERE r.id=?;",
                (mem_id,),
            ).fetchone()[0]
            decoy = ep_id + "_decoy"
            conn.execute(
                """INSERT INTO memory_candidates (
                    id, user_scope_key, cycle_id, candidate_type, canonical_text,
                    original_provenance, source_episode_refs_json, source_host_event_refs_json,
                    supporting_refs_json, contradicting_refs_json, scope, sensitivity,
                    confidence, status, candidate_hash, created_at
                ) VALUES (?, 'default_user', 'cyc_decoy', 'project_fact', 'keep this decoy',
                    'observed', ?, '[]', '[]', '[]', 'user', 'internal', 0.5, 'pending', 'hash', ?);""",
                ("mcand_decoy", json.dumps([decoy]), "2026-01-01T00:00:00+00:00"),
            )
            conn.commit()
        human = self.kernel.record_host_event(session_id="bf_gdpr", origin_kind="human", payload="del")
        self.kernel.delete_reviewed_memory(mem_id, human.id)
        with self.kernel._get_conn() as conn:
            text = conn.execute(
                "SELECT canonical_text FROM memory_candidates WHERE id='mcand_decoy';"
            ).fetchone()[0]
        self.assertEqual(text, "keep this decoy")

    def test_l3_blocks_reward_and_trait(self):
        self.kernel.heal_soul_state(level=3, reason="freeze identity")
        with self.assertRaises(PermissionError):
            self.kernel.process_reward(RewardSignal(
                source="external_test", valence=0.5, confidence=1.0, task_context="blocked",
                evidence_receipt="blocked_l3",
            ))
        with self.assertRaises(PermissionError):
            self.kernel.update_trait(TraitUpdate(trait="audacity", new_value=86.0, evidence_refs=["a", "b"]))
        self.kernel.heal_soul_state(level=2, reason="unfreeze")
        after = self.kernel.process_reward(RewardSignal(
            source="external_test", valence=0.1, confidence=1.0, task_context="allowed after L2",
            evidence_receipt="after_l2",
        ))
        self.assertGreater(after.soul_version, 1)

    def test_imagined_provenance_stays_out_of_default_recall(self):
        self.kernel.ingest_experience(EpisodeInput(
            source_kind="agent", provenance="imagined",
            content="Imagined only unique-dream-fact-zzz",
        ))
        cycle = self.kernel.start_review_cycle(session_id="bf_img")
        self.kernel.apply_chat_review(
            session_id="bf_img",
            cycle_id=cycle["cycle_id"],
            decisions=[{"candidate_id": cycle["candidates"][0]["id"], "decision": "remember"}],
        )
        blob = " ".join((m.get("content") or "") for m in self.kernel.recall_memories(limit=20))
        self.assertNotIn("unique-dream-fact-zzz", blob)
        facts = " ".join((m.get("content") or "") for m in self.kernel.get_memory_digest(limit=20)["active_facts"])
        self.assertNotIn("unique-dream-fact-zzz", facts)

    def test_internal_reward_is_overlay_only(self):
        before = self.kernel.get_current_state()
        # 1.2.0 gate: internal self-score requires an open plan (or live overlay)
        with self.assertRaises(ValueError):
            self.kernel.process_reward(RewardSignal(
                source="internal_reflection", valence=1.0, confidence=1.0, task_context="think",
            ))
        after = self.kernel.process_reward(RewardSignal(
            source="internal_reflection", valence=1.0, confidence=1.0, task_context="think",
            plan_id="p-overlay-test",
        ))
        self.assertEqual(after.soul_version, before.soul_version)
        digest = self.kernel.get_memory_digest(plan_id="p-overlay-test")
        self.assertGreater(digest["session_neuromodulators"]["dopamine"], 0.0)
        self.assertEqual(self.kernel.bio_engine.dopamine, 0.0)

    def test_external_test_reward_requires_receipt(self):
        with self.assertRaises(ValueError):
            self.kernel.process_reward(RewardSignal(
                source="external_test", valence=0.5, confidence=1.0, task_context="no receipt",
            ))

    def test_trait_change_rate_needs_two_refs_and_caps_delta(self):
        with self.assertRaises(ValueError):
            self.kernel.update_trait(TraitUpdate(trait="audacity", new_value=86.0, evidence_refs=["one"]))
        with self.assertRaises(ValueError):
            self.kernel.update_trait(TraitUpdate(trait="epistemic_humility", new_value=100.0, evidence_refs=["a", "b"]))
        ok = self.kernel.update_trait(TraitUpdate(trait="audacity", new_value=90.0, evidence_refs=["a", "b"]))
        self.assertEqual(ok.traits["audacity"], 90.0)

    def test_daemon_does_not_heal_identity(self):
        before = self.kernel.get_current_state().soul_version
        self.kernel._set_heal_due(False)
        rid = _output_review_receipt(self.kernel, "bf_heal")
        self.kernel.process_reward(RewardSignal(
            source="external_human", valence=-1.0, confidence=1.0, task_context="stress",
            review_receipt=rid,
        ), session_id="bf_heal")
        self.kernel.start_daemon(dream_interval=30, heal_interval=1, homeostasis_interval=30)
        time.sleep(1.4)
        self.assertGreaterEqual(self.kernel.daemon_worker.stats["heals_run"], 1)
        self.assertTrue(self.kernel.get_memory_digest()["heal_due"])
        self.assertEqual(self.kernel.get_current_state().soul_version, before + 1)
        self.kernel.stop_daemon()

    def test_boot_recover_skips_fresh_active_cycle(self):
        self.kernel.record_host_event(session_id="bf_boot", origin_kind="human", payload="start")
        cycle = self.kernel.review_engine.open_or_get_cycle(session_id="bf_boot")
        db = self.db_path
        self.kernel.close()
        self.kernel = SoulKernel(db_path=db)
        live = self.kernel.review_engine.get_cycle_by_id(cycle.id)
        self.assertEqual(live.status, "active")
        recovered = self.kernel.recover_unsealed_cycles()
        self.assertIn(cycle.id, recovered)
        self.assertEqual(self.kernel.review_engine.get_cycle_by_id(cycle.id).status, "recovery_required")

    def test_correction_payload_must_match_text(self):
        self.kernel.ingest_experience(EpisodeInput(source_kind="human", content="Wrong spelling of colour"))
        human = self.kernel.record_host_event(session_id="bf_corr", origin_kind="human", payload="start")
        started = self.kernel.start_review_cycle(session_id="bf_corr")
        bad = self.kernel.record_host_event(
            session_id="bf_corr", origin_kind="human", payload={"corrected_text": "not the correction"},
        )
        with self.assertRaises(ValueError):
            self.kernel.record_review_decision(
                cycle_id=started["cycle_id"],
                candidate_id=started["candidates"][0]["id"],
                decision="correct",
                human_event_ref=human.id,
                corrected_text="Correct spelling of color",
                correction_confirmation_event_ref=bad.id,
            )
        committed = self.kernel.apply_chat_review(
            session_id="bf_corr",
            cycle_id=started["cycle_id"],
            decisions=[{
                "candidate_id": started["candidates"][0]["id"],
                "decision": "correct",
                "corrected_text": "Correct spelling of color",
            }],
        )
        self.assertEqual(committed["receipt"]["status"], "committed")

    def test_delete_nulls_episode_embedding_and_percept(self):
        self.kernel.ingest_experience(EpisodeInput(
            source_kind="human",
            content="Unique gdpr embedding wipe zzz",
            percept_json={"claims": ["desk is oak"]},
        ))
        started = self.kernel.start_review_cycle(session_id="bf_emb")
        committed = self.kernel.apply_chat_review(
            session_id="bf_emb",
            cycle_id=started["cycle_id"],
            decisions=[{"candidate_id": started["candidates"][0]["id"], "decision": "remember"}],
        )
        mem_id = committed["receipt"]["promoted_memory_ids"][0]
        with self.kernel._get_conn() as conn:
            ep_id = conn.execute(
                "SELECT j.value FROM reviewed_memories r, json_each(r.source_episode_refs_json) j WHERE r.id=?;",
                (mem_id,),
            ).fetchone()[0]
        human = self.kernel.record_host_event(session_id="bf_emb", origin_kind="human", payload="del")
        self.kernel.delete_reviewed_memory(mem_id, human.id)
        with self.kernel._get_conn() as conn:
            row = conn.execute(
                "SELECT content, embedding_json, percept_json FROM episodes WHERE id=?;",
                (ep_id,),
            ).fetchone()
        self.assertEqual(row[0], "[REDACTED]")
        self.assertIsNone(row[1])
        self.assertIsNone(row[2])

    def test_recovery_required_cycle_is_reused(self):
        self.kernel.record_host_event(session_id="bf_reuse", origin_kind="human", payload="start")
        cycle = self.kernel.review_engine.open_or_get_cycle(session_id="bf_reuse")
        self.kernel.recover_unsealed_cycles()
        self.assertEqual(self.kernel.review_engine.get_cycle_by_id(cycle.id).status, "recovery_required")
        reused = self.kernel.review_engine.open_or_get_cycle(session_id="bf_reuse")
        self.assertEqual(reused.id, cycle.id)
        self.assertEqual(reused.status, "active")

    def test_solver_flags_and_health_cannot_authorize(self):
        digest0 = self.kernel.get_memory_digest()
        self.assertFalse(digest0["solver_active"])
        self.assertFalse(digest0["remember_due"])
        self.assertIsNone(digest0["dead_end"])
        self.assertFalse(digest0["health"]["authorizes_identity"])
        self.assertFalse(digest0["health"]["authorizes_freeze"])
        self.kernel.record_solver_step(
            tool="edit", method="patch", outcome="succeed", receipt="r-ok",
        )
        digest = self.kernel.get_memory_digest()
        self.assertTrue(digest["solver_active"])
        self.assertTrue(digest["remember_due"])
        self.kernel.ingest_experience(EpisodeInput(source_kind="agent", content="Distilled lesson unique-zzz"))
        self.assertFalse(self.kernel.get_memory_digest()["remember_due"])
        self.kernel.record_solver_step(
            tool="search", method="web", outcome="dead_end", receipt="r-dead", options_left=[],
        )
        dead = self.kernel.get_memory_digest()
        self.assertIsNotNone(dead["dead_end"])
        self.assertEqual(dead["dead_end"]["tool"], "search")
        self.assertTrue(dead["dream_due"])

    def test_human_reward_requires_output_review_receipt(self):
        with self.assertRaises(ValueError):
            self.kernel.process_reward(RewardSignal(
                source="external_human", valence=0.5, confidence=1.0, task_context="no receipt",
            ), session_id="bf_human")
        rid = _output_review_receipt(self.kernel, "bf_human")
        with self.assertRaises(ValueError):
            self.kernel.process_reward(RewardSignal(
                source="external_human", valence=0.5, confidence=1.0, task_context="wrong session",
                review_receipt=rid,
            ), session_id="bf_human_other")
        ok = self.kernel.process_reward(RewardSignal(
            source="external_human", valence=0.2, confidence=1.0, task_context="ok",
            review_receipt=rid,
        ), session_id="bf_human")
        self.assertGreater(ok.soul_version, 1)

    def test_solver_refuses_pending_review_for_session(self):
        self.kernel.ingest_experience(EpisodeInput(source_kind="agent", content="pending before solver unique-sss"))
        cycle = self.kernel.start_review_cycle(session_id="bf_pending")
        self.assertGreaterEqual(cycle["candidate_count"], 1)
        with self.assertRaises(ValueError):
            self.kernel.record_solver_step(
                tool="edit", method="patch", outcome="succeed", receipt="blocked",
                session_id="bf_pending",
            )
        self.kernel.record_solver_step(
            tool="edit", method="patch", outcome="succeed", receipt="empty-session-ok",
        )

    def test_negative_external_test_sets_dream_due(self):
        self.assertFalse(self.kernel.get_memory_digest()["dream_due"])
        self.kernel.process_reward(RewardSignal(
            source="external_test", valence=-1.0, confidence=1.0, task_context="failed suite",
            evidence_receipt="fail_suite",
        ))
        self.assertTrue(self.kernel.get_memory_digest()["dream_due"])

    def test_eils_recall_caps_and_dream_budget(self):
        for batch in range(2):
            for i in range(5):
                self.kernel.ingest_experience(EpisodeInput(
                    source_kind="agent",
                    content=f"EILS recall fixture fact {batch}-{i} unique-eee",
                ))
            sid = f"bf_eils_{batch}"
            cycle = self.kernel.start_review_cycle(session_id=sid)
            self.assertEqual(cycle["candidate_count"], 5)
            self.kernel.apply_chat_review(
                session_id=sid,
                cycle_id=cycle["cycle_id"],
                decisions=[{"candidate_id": c["id"], "decision": "remember"} for c in cycle["candidates"]],
            )
        self.assertEqual(len(self.kernel.recall_memories(query="", limit=10)), 5)
        self.kernel.process_reward(RewardSignal(
            source="external_test", valence=1.0, confidence=1.0, task_context="pass 1",
            evidence_receipt="eils_da_1",
        ))
        self.kernel.process_reward(RewardSignal(
            source="external_test", valence=1.0, confidence=1.0, task_context="pass 2",
            evidence_receipt="eils_da_2",
        ))
        self.assertGreaterEqual(self.kernel.bio_engine.dopamine, 0.5)
        self.assertEqual(len(self.kernel.recall_memories(query="", limit=10)), 8)
        self.kernel.process_reward(RewardSignal(
            source="external_test", valence=-1.0, confidence=1.0, task_context="fail",
            evidence_receipt="eils_co_01",
        ))
        self.assertGreaterEqual(self.kernel.bio_engine.cortisol, 0.5)
        self.assertEqual(len(self.kernel.recall_memories(query="", limit=10)), 3)
        pkt = self.kernel.run_dream_simulation("EILS recall fixture")
        self.assertLessEqual(pkt["budget"]["used_chars"], pkt["budget"]["max_chars"])
        self.assertGreater(pkt["budget"]["used_chars"], 0)
        fact_ids = {f.get("memory_id") for f in pkt.get("reviewed_facts") or []}
        ana_ids = {a.get("memory_id") for a in pkt.get("analogical_cases") or []}
        self.assertFalse(fact_ids & ana_ids)

    # ---- plan-wallet subsystem ----

    def test_solver_wallets_isolated_by_agent_and_close_plan(self):
        self.kernel.record_solver_step(
            tool="pytest", method="run", outcome="fail", receipt="c1",
            plan_id="p1", agent_id="child-a", task_id="t-fail",
        )
        self.kernel.record_solver_step(
            tool="pytest", method="run", outcome="succeed", receipt="c2",
            plan_id="p1", agent_id="child-b", task_id="t-ok",
        )
        da = self.kernel.get_memory_digest(plan_id="p1", agent_id="child-a")
        db = self.kernel.get_memory_digest(plan_id="p1", agent_id="child-b")
        self.assertGreater(
            da["session_neuromodulators"]["cortisol"],
            db["session_neuromodulators"]["cortisol"],
        )
        self.assertGreater(
            db["session_neuromodulators"]["dopamine"],
            da["session_neuromodulators"]["dopamine"],
        )
        self.assertEqual(len(da["working"]), 1)
        self.assertEqual(da["working"][0]["agent_id"], "child-a")
        self.assertEqual(da["working"][0]["task_id"], "t-fail")
        parent = self.kernel.get_memory_digest(plan_id="p1")
        self.assertEqual(len(parent["working"]), 2)
        closed = self.kernel.record_solver_step(
            tool="plan", method="done", outcome="succeed", receipt="done",
            plan_id="p1", close_plan=True,
        )
        self.assertTrue(closed["plan_closed"])
        self.assertTrue(closed["wrote_episode"])
        self.assertFalse(closed["wrote_identity"])
        self.assertGreaterEqual(len(closed["episode_ids"]), 2)
        after = self.kernel.get_memory_digest(plan_id="p1")
        self.assertEqual(after["working"], [])
        self.assertEqual(after["session_neuromodulators"]["dopamine"], 0.0)
        self.assertEqual(after["session_neuromodulators"]["cortisol"], 0.0)
        self.assertFalse(after["solver_active"])
        blob = " ".join(
            (row[0] or "")
            for row in self.kernel._get_conn().execute(
                "SELECT content FROM episodes WHERE deleted_at IS NULL;"
            )
        )
        self.assertIn("pytest/run", blob)
        self.assertIn("child-a", blob)
        self.assertIn("fail", blob)
        facts = " ".join((m.get("content") or "") for m in after["active_facts"])
        self.assertNotIn("pytest/run", facts)

    def test_in_plan_recall_uses_overlay_not_identity(self):
        for batch in range(2):
            for i in range(5):
                self.kernel.ingest_experience(EpisodeInput(
                    source_kind="agent",
                    content=f"Overlay recall fixture {batch}-{i} unique-ovl",
                ))
            sid = f"bf_ovl_{batch}"
            cycle = self.kernel.start_review_cycle(session_id=sid)
            self.kernel.apply_chat_review(
                session_id=sid,
                cycle_id=cycle["cycle_id"],
                decisions=[{"candidate_id": c["id"], "decision": "remember"} for c in cycle["candidates"]],
            )
        self.kernel.process_reward(RewardSignal(
            source="external_test", valence=1.0, confidence=1.0, task_context="id-da-a",
            evidence_receipt="ovl_da_1",
        ))
        self.kernel.process_reward(RewardSignal(
            source="external_test", valence=1.0, confidence=1.0, task_context="id-da-b",
            evidence_receipt="ovl_da_2",
        ))
        self.assertGreaterEqual(self.kernel.bio_engine.dopamine, 0.5)
        self.assertEqual(len(self.kernel.recall_memories(query="", limit=10)), 8)
        for i in range(4):
            self.kernel.record_solver_step(
                tool="pytest", method="run", outcome="fail", receipt=f"ovl-f{i}",
                plan_id="eils-plan", agent_id="child",
            )
        scoped = self.kernel.get_memory_digest(plan_id="eils-plan", agent_id="child")
        self.assertGreaterEqual(scoped["session_neuromodulators"]["cortisol"], 0.5)
        self.assertGreaterEqual(self.kernel.bio_engine.dopamine, 0.5)
        self.assertEqual(len(scoped["active_facts"]), 3)
        self.assertEqual(
            len(self.kernel.recall_memories(
                query="", limit=10, plan_id="eils-plan", agent_id="child",
            )),
            3,
        )
        self.assertEqual(len(self.kernel.recall_memories(query="", limit=10)), 3)
        self.kernel.record_solver_step(
            tool="plan", method="done", outcome="succeed", receipt="ovl-end",
            plan_id="eils-plan", close_plan=True,
        )
        self.assertEqual(len(self.kernel.recall_memories(query="", limit=10)), 8)

    def test_hrrl_shrinks_identity_trait_step_far_from_setpoint(self):
        self.assertEqual(_hrrl_trait_scale(DEFAULT_TRAITS), 1.0)
        far = dict(DEFAULT_TRAITS)
        far["audacity"] = 100.0
        far["curiosity"] = 100.0
        far["error_anxiety"] = 15.0
        self.assertLess(_hrrl_trait_scale(far), 1.0)
        self.kernel.update_trait(TraitUpdate(
            trait="audacity", new_value=90.0, evidence_refs=["hrrl-a", "hrrl-b"],
        ))
        scale = _hrrl_trait_scale(self.kernel.get_current_state().traits)
        self.assertLess(scale, 1.0)
        a0 = self.kernel.get_current_state().traits["audacity"]
        self.kernel.process_reward(RewardSignal(
            source="external_test", valence=1.0, confidence=1.0,
            task_context="hrrl-unique-ctx", evidence_receipt="hrrl_ctx_1",
        ))
        self.assertAlmostEqual(
            self.kernel.get_current_state().traits["audacity"],
            min(100.0, a0 + 7.0 * scale),
            places=3,
        )

    def test_close_plan_keeps_overlay_if_ingest_blocked(self):
        self.kernel.record_solver_step(
            tool="pytest", method="run", outcome="fail", receipt="fz1",
            plan_id="p-fz",
        )
        digest = self.kernel.get_memory_digest(plan_id="p-fz")
        co0 = digest["session_neuromodulators"]["cortisol"]
        self.kernel.heal_soul_state(level=3, reason="test freeze")
        with self.assertRaises(PermissionError):
            self.kernel.record_solver_step(
                tool="plan", method="done", outcome="succeed", receipt="fz-end",
                plan_id="p-fz", close_plan=True,
            )
        digest = self.kernel.get_memory_digest(plan_id="p-fz")
        self.assertTrue(digest["solver_active"])
        self.assertAlmostEqual(digest["session_neuromodulators"]["cortisol"], co0, places=4)
        self.kernel.heal_soul_state(level=2, reason="unfreeze")

    def test_close_plan_crash_before_commit_does_not_leave_trace(self):
        self.kernel.record_solver_step(
            tool="pytest", method="run", outcome="fail", receipt="atom1",
            plan_id="p-atom",
        )
        orig = self.kernel._write_solver_store

        def boom(conn, store):
            raise RuntimeError("simulated crash")

        self.kernel._write_solver_store = boom
        with self.assertRaises(RuntimeError):
            self.kernel.record_solver_step(
                tool="plan", method="done", outcome="succeed", receipt="atom-end",
                plan_id="p-atom", close_plan=True,
            )
        self.kernel._write_solver_store = orig
        n = self.kernel._get_conn().execute(
            "SELECT COUNT(*) FROM episodes WHERE content LIKE '%Solver identity trace%' AND content LIKE '%p-atom%';"
        ).fetchone()[0]
        self.assertEqual(n, 0)
        digest = self.kernel.get_memory_digest(plan_id="p-atom")
        self.assertTrue(digest["solver_active"])
        self.assertIn("atom1", [s["receipt"] for s in digest["working"]])
        closed = self.kernel.record_solver_step(
            tool="plan", method="done", outcome="succeed", receipt="atom-end2",
            plan_id="p-atom", close_plan=True,
        )
        self.assertTrue(closed["wrote_episode"])
        n2 = self.kernel._get_conn().execute(
            "SELECT COUNT(*) FROM episodes WHERE content LIKE '%Solver identity trace%' AND content LIKE '%p-atom%';"
        ).fetchone()[0]
        self.assertEqual(n2, 1)

    def test_trim_does_not_evict_other_plan_before_close(self):
        from soul_kernel import SOLVER_WORKING_MAX
        for i in range(SOLVER_WORKING_MAX - 1):
            self.kernel.record_solver_step(
                tool="keep", method="run", outcome="fail", receipt=f"k{i}",
                plan_id="keep",
            )
        self.kernel.record_solver_step(
            tool="noise", method="x", outcome="fail", receipt="n1",
            plan_id="noise",
        )
        self.assertIn(
            "k0",
            [s["receipt"] for s in self.kernel.get_memory_digest(plan_id="keep")["working"]],
        )
        closed = self.kernel.record_solver_step(
            tool="plan", method="done", outcome="succeed", receipt="k-end",
            plan_id="keep", close_plan=True,
        )
        self.assertTrue(closed["wrote_episode"])
        blob = " ".join(
            (row[0] or "")
            for row in self.kernel._get_conn().execute(
                "SELECT content FROM episodes WHERE deleted_at IS NULL;"
            )
        )
        self.assertIn("receipt=k0", blob)

    def test_mcp_internal_reward_returns_overlay_neuromodulators(self):
        out = _mcp("soul_reward", {
            "source": "internal_reflection",
            "valence": 1.0,
            "confidence": 1.0,
            "task_context": "mcp overlay",
            "plan_id": "p-mcp",
            "agent_id": "child",
        })
        self.assertEqual(out.get("status"), "overlay_only")
        self.assertFalse(out.get("wrote_identity"))
        self.assertGreater(out["neuromodulators"]["dopamine"], 0.0)
        self.assertEqual(self.kernel.bio_engine.dopamine, 0.0)

    def test_host_event_default_origin_is_agent(self):
        ev = self.kernel.record_host_event(session_id="bf_default_origin", payload="ping")
        self.assertEqual(ev.origin_kind, "agent")

    def test_start_review_rejects_blank_session_id(self):
        with self.assertRaises(ValueError):
            self.kernel.start_review_cycle(session_id="")
        with self.assertRaises(ValueError):
            self.kernel.start_review_cycle(session_id="   ")

    def test_mcp_solver_step_schema_receipt_and_close_plan(self):
        listed = soul_mcp_server._handle_jsonrpc({
            "jsonrpc": "2.0", "id": 20, "method": "tools/list", "params": {},
        })
        tools = {t["name"]: t for t in listed["result"]["tools"]}
        self.assertIn("soul_solver_step", tools)
        self.assertIn("soul_review_chat_commit", tools)
        self.assertIn("close_plan", tools["soul_solver_step"]["inputSchema"]["properties"])
        missing = _mcp("soul_solver_step", {"tool": "x", "method": "y", "outcome": "fail"})
        self.assertIn("receipt", str(missing.get("error") or missing).lower())
        ok = _mcp("soul_solver_step", {
            "tool": "pytest", "method": "run", "outcome": "fail", "receipt": "mcp-t1",
            "plan_id": "p-jsonrpc",
        })
        self.assertEqual(ok.get("status"), "success")
        self.assertFalse(ok["result"]["wrote_identity"])
        closed = _mcp("soul_solver_step", {
            "tool": "plan", "method": "done", "outcome": "succeed", "receipt": "mcp-end",
            "plan_id": "p-jsonrpc", "close_plan": True,
        })
        self.assertEqual(closed.get("status"), "success")
        self.assertTrue(closed["result"]["wrote_episode"])
        self.assertFalse(closed["result"]["wrote_identity"])

    def test_mcp_chat_commit_requires_session_cycle_decisions(self):
        missing_sid = _mcp("soul_review_chat_commit", {
            "cycle_id": "rc_x",
            "decisions": [{"candidate_id": "c", "decision": "remember"}],
        })
        self.assertIn("session_id", str(missing_sid.get("error") or "").lower())
        missing_cid = _mcp("soul_review_chat_commit", {
            "session_id": "s",
            "decisions": [{"candidate_id": "c", "decision": "remember"}],
        })
        self.assertIn("cycle_id", str(missing_cid.get("error") or "").lower())
        missing_dec = _mcp("soul_review_chat_commit", {"session_id": "s", "cycle_id": "rc_x"})
        self.assertIn("decisions", str(missing_dec.get("error") or "").lower())

    def test_solver_step_without_close_plan_does_not_write_episodes(self):
        before_ver = self.kernel.get_current_state().soul_version
        with self.kernel._get_conn() as conn:
            before_eps = conn.execute("SELECT COUNT(*) FROM episodes;").fetchone()[0]
        self.kernel.record_solver_step(
            tool="pytest", method="run", outcome="fail", receipt="t1", error="boom",
        )
        self.kernel.record_solver_step(
            tool="pytest", method="fix", outcome="succeed", receipt="t2",
        )
        self.assertEqual(self.kernel.get_current_state().soul_version, before_ver)
        with self.kernel._get_conn() as conn:
            after_eps = conn.execute("SELECT COUNT(*) FROM episodes;").fetchone()[0]
        self.assertEqual(after_eps, before_eps)
        digest = self.kernel.get_memory_digest()
        self.assertEqual(len(digest["working"]), 2)
        self.assertEqual(digest["working"][0]["outcome"], "fail")
        self.assertEqual(digest["working"][1]["outcome"], "succeed")
        facts = " ".join((m.get("content") or "") for m in digest["active_facts"])
        self.assertNotIn("boom", facts)
        self.assertGreater(digest["session_neuromodulators"]["dopamine"], 0)
        self.assertEqual(digest["neuromodulators"]["dopamine"], 0.0)
        missing = _mcp("soul_solver_step", {"tool": "x", "method": "y", "outcome": "fail"})
        self.assertTrue(missing.get("rpc_error") or missing.get("error") or missing.get("status") == "rejected")
        self.kernel.record_solver_step(
            tool="grep", method="symbol", outcome="dead_end", receipt="t3", options_left=[],
        )
        self.assertTrue(self.kernel.get_memory_digest()["dream_due"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
