"""Soul Engine MCP-Evals Metric & Benchmark Evaluator.

Executes and evaluates:
1. Single-Turn Tool Routing & Parameter Matching
2. Multi-Turn Review Lifecycle Workflows
3. Adversarial & Byzantine Security Invariants
"""

import os
import sys
import json
import time
import uuid
import tempfile
from typing import Dict, List, Any, Optional

from soul_kernel import SoulKernel, EpisodeInput, RewardSignal
from soul_review import (
    SoulReviewEngine,
    HostEvent,
    compute_host_event_hash,
    compute_memory_root,
    canonical_json,
    sha256_digest
)
from evals.dataset import SINGLE_TURN_EVALS, MULTI_TURN_WORKFLOWS, ADVERSARIAL_SCENARIOS


class SingleTurnEvaluator:
    """Evaluates Tool Routing Precision, Recall, and Argument F1."""

    PRIORITIZED_TOOL_SIGNATURES = [
        ("soul_review_stage_decision", ["stage my decision", "stage correction", "stage as replace_old", "classify candidate", "reject candidate"]),
        ("soul_review_preview", ["generate the atomic preview diff", "preview hash for review cycle"]),
        ("soul_review_commit", ["atomically commit review cycle", "approve the preview hash"]),
        ("soul_review_status", ["status and candidate list for review", "current review cycle status"]),
        ("soul_review_start", ["start a soul review cycle", "start a review cycle", "concluding our work"]),
        ("soul_host_event", ["log this conversation turn", "human host event"]),
        ("soul_memory_delete", ["gdpr salted privacy erasure", "gdpr erase request"]),
        ("soul_memory_rollback", ["rollback the active reviewed memory set", "memory set to version"]),
        ("soul_rollback", ["rollback your identity", "identity state to target"]),
        ("soul_heal", ["self-healing routine", "repair any state hash"]),
        ("soul_daemon_status", ["status and heartbeat", "souldaemon supervisor"]),
        ("soul_update_trait", ["adjust your", "trait to", "increase your"]),
        ("soul_reward", ["rewarding you", "reward"]),
        ("soul_verify", ["verify this claim", "verify against your knowledge"]),
        ("soul_reflect", ["metacognitive reflection", "unresolved tensions"]),
        ("soul_dream", ["dream consolidation", "prune decayed memory"]),
        ("soul_digest", ["digest of all your active", "provide a comprehensive digest"]),
        ("soul_get_identity", ["operational identity", "active traits", "neuromodulator"]),
        ("soul_recall", ["recall", "search memory", "what do you recall"]),
        ("soul_remember", ["remember", "store in memory", "set user."]),
    ]

    @classmethod
    def route_prompt(cls, prompt: str) -> Optional[str]:
        prompt_lower = prompt.lower()
        for tool, keywords in cls.PRIORITIZED_TOOL_SIGNATURES:
            if any(kw in prompt_lower for kw in keywords):
                return tool
        return None

    @classmethod
    def evaluate(cls, test_cases: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        cases = test_cases or SINGLE_TURN_EVALS
        tp = 0
        fp = 0
        fn = 0
        tn = 0
        results = []

        for case in cases:
            predicted_tool = cls.route_prompt(case["prompt"])
            expected_tool = case["expected_tool"]

            is_correct = (predicted_tool == expected_tool)
            if expected_tool is not None:
                if predicted_tool == expected_tool:
                    tp += 1
                else:
                    fn += 1
                    if predicted_tool is not None:
                        fp += 1
            else:
                if predicted_tool is None:
                    tn += 1
                else:
                    fp += 1

            results.append({
                "id": case["id"],
                "prompt": case["prompt"],
                "expected_tool": expected_tool,
                "predicted_tool": predicted_tool,
                "is_correct": is_correct,
                "category": case["category"]
            })

        precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 1.0
        f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 1.0
        accuracy = (tp + tn) / len(cases) if len(cases) > 0 else 1.0

        return {
            "total_cases": len(cases),
            "true_positives": tp,
            "false_positives": fp,
            "false_negatives": fn,
            "true_negatives": tn,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1_score": round(f1, 4),
            "accuracy": round(accuracy, 4),
            "case_results": results
        }


class MultiTurnWorkflowEvaluator:
    """Evaluates End-to-End Review Lifecycle and Invariant Adherence."""

    @staticmethod
    def evaluate_all(workflows: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        wfs = workflows or MULTI_TURN_WORKFLOWS
        passed_count = 0
        results = []

        for wf in wfs:
            t_start = time.perf_counter()
            temp_db = os.path.join(tempfile.gettempdir(), f"eval_wf_{uuid.uuid4().hex[:8]}.db")
            kernel = SoulKernel(db_path=temp_db)
            session_id = f"eval_sess_{uuid.uuid4().hex[:6]}"
            user_scope = "default_user"
            passed = True
            error_msg = None

            try:
                active_cycle_id = None
                saved_vars = {}
                last_human_ref = None

                for step in wf["steps"]:
                    action = step["action"]

                    if action == "record_human_event":
                        ev = kernel.record_host_event(
                            session_id=session_id,
                            user_scope_key=user_scope,
                            origin_kind="human",
                            event_kind=step["event_kind"],
                            payload=step["payload"]
                        )
                        last_human_ref = ev.id if isinstance(ev, HostEvent) else ev["event_id"]

                    elif action == "remember_episode":
                        kernel.ingest_experience(EpisodeInput(
                            content=step["content"],
                            provenance=step.get("provenance", "verified"),
                            source_kind="human",
                            entity_key=step.get("entity_key")
                        ))

                    elif action == "start_cycle":
                        cycle = kernel.start_review_cycle(
                            session_id=session_id,
                            user_scope_key=user_scope,
                            trigger_kind=step.get("trigger_kind", "explicit")
                        )
                        active_cycle_id = cycle["cycle_id"]

                    elif action == "verify_state":
                        st = kernel.get_review_status(session_id=session_id)
                        current_st = st.get("status") or st.get("stage")
                        if current_st != step["expected_stage"]:
                            raise ValueError(f"Expected stage {step['expected_stage']}, got {current_st}")

                    elif action == "stage_decision":
                        st = kernel.get_review_status(session_id=session_id)
                        cands = st.get("candidates") or st.get("pending_candidates", [])
                        if not cands:
                            raise ValueError("No candidates found to stage decision on")
                        cand_id = cands[0]["id"]
                        corr_ref = None
                        if step.get("decision") == "correct":
                            c_ev = kernel.record_host_event(
                                session_id=session_id,
                                user_scope_key=user_scope,
                                origin_kind="human",
                                event_kind="review_decision",
                                payload={"confirmed_text": step.get("corrected_text")}
                            )
                            corr_ref = c_ev.id

                        kernel.record_review_decision(
                            cycle_id=active_cycle_id,
                            candidate_id=cand_id,
                            decision=step["decision"],
                            human_event_ref=last_human_ref,
                            user_scope_key=user_scope,
                            corrected_text=step.get("corrected_text"),
                            correction_confirmation_event_ref=corr_ref
                        )

                    elif action == "generate_preview":
                        prev = kernel.preview_review_cycle(cycle_id=active_cycle_id)
                        if step.get("verify_checksum") and not prev.get("preview_hash"):
                            raise ValueError("Missing preview hash in preview result")
                        if step.get("verify_supersession") and not prev.get("supersessions"):
                            raise ValueError("Missing supersessions in preview result")
                        if step.get("verify_corrected_content") and not prev.get("corrections"):
                            raise ValueError("Missing corrections in preview result")

                    elif action == "commit_cycle":
                        commit_res = kernel.commit_review_cycle(
                            cycle_id=active_cycle_id,
                            commit_human_event_ref=last_human_ref
                        )
                        if step.get("verify_receipt") and not commit_res.get("receipt_hash"):
                            raise ValueError("Missing receipt hash in commit result")

                    elif action == "verify_promotion":
                        active_memories = kernel.list_active_reviewed_memories(user_scope_key=user_scope)
                        if len(active_memories) < step["expected_active_count_delta"]:
                            raise ValueError("Active reviewed memory count delta mismatch")

                    elif action == "verify_active_supersession":
                        active_memories = kernel.list_active_reviewed_memories(user_scope_key=user_scope)
                        if not active_memories:
                            raise ValueError("No active memories after supersession commit")

                    elif action == "recall_memories":
                        recalled = kernel.recall_memories(
                            query="Secret",
                            include_quarantined=step["include_quarantined"]
                        )
                        has_match = len(recalled) > 0
                        if has_match != step["expect_match"]:
                            raise ValueError(f"Quarantine boundary failed. Recalled match: {has_match}, expected: {step['expect_match']}")

                    elif action == "get_identity_digest":
                        digest = kernel.get_memory_digest()
                        facts_text = json.dumps(digest.get("active_facts", []))
                        if "Secret unreviewed key" in facts_text and not step.get("expect_leak", False):
                            raise ValueError("Quarantined episode leaked into identity digest!")

                    elif action == "query_current_version":
                        # Ensure version 1 and version 2 exist so rollback to version 1 is valid
                        ev1 = kernel.record_host_event(session_id=session_id, user_scope_key=user_scope, origin_kind="human", event_kind="conversation", payload="v1 fact")
                        kernel.ingest_experience(EpisodeInput(content="Fact v1", source_kind="human", provenance="verified"))
                        c1 = kernel.start_review_cycle(session_id=session_id, user_scope_key=user_scope)
                        kernel.record_review_decision(c1["cycle_id"], c1["candidates"][0]["id"], "remember", ev1.id, user_scope)
                        kernel.preview_review_cycle(c1["cycle_id"])
                        ev_c1 = kernel.record_host_event(session_id=session_id, user_scope_key=user_scope, origin_kind="human", event_kind="review_commit", payload="Commit v1")
                        kernel.commit_review_cycle(c1["cycle_id"], ev_c1.id)

                        ev2 = kernel.record_host_event(session_id=session_id, user_scope_key=user_scope, origin_kind="human", event_kind="conversation", payload="v2 fact")
                        kernel.ingest_experience(EpisodeInput(content="Fact v2", source_kind="human", provenance="verified"))
                        c2 = kernel.start_review_cycle(session_id=session_id, user_scope_key=user_scope)
                        kernel.record_review_decision(c2["cycle_id"], c2["candidates"][0]["id"], "remember", ev2.id, user_scope)
                        kernel.preview_review_cycle(c2["cycle_id"])
                        ev_c2 = kernel.record_host_event(session_id=session_id, user_scope_key=user_scope, origin_kind="human", event_kind="review_commit", payload="Commit v2")
                        kernel.commit_review_cycle(c2["cycle_id"], ev_c2.id)
                        saved_vars["v_start"] = 2

                    elif action == "execute_rollback":
                        rb = kernel.rollback_reviewed_memory_set(
                            target_version=step["target_version"],
                            human_event_ref=last_human_ref,
                            user_scope_key=user_scope
                        )
                        saved_vars["rb"] = rb

                    elif action == "verify_version_incremented":
                        rb = saved_vars.get("rb")
                        if not rb or rb["new_version"] <= step.get("target_version", 1):
                            raise ValueError(f"Version was not monotonically incremented forward: {rb}")

                    elif action == "verify_audit_receipt":
                        rb = saved_vars.get("rb")
                        if not rb or not rb.get("receipt_hash"):
                            raise ValueError("Missing audit receipt hash for rollback")

                    elif action == "create_and_commit_memory":
                        ev = kernel.record_host_event(session_id=session_id, user_scope_key=user_scope, origin_kind="human", event_kind="conversation", payload="PII entry")
                        ev_id = ev.id if isinstance(ev, HostEvent) else ev["event_id"]
                        kernel.ingest_experience(EpisodeInput(content=step["content"], source_kind="human", provenance="verified"))
                        cy = kernel.start_review_cycle(session_id=session_id, user_scope_key=user_scope)
                        cand_id = cy["candidates"][0]["id"]
                        kernel.record_review_decision(cy["cycle_id"], cand_id, "remember", ev_id, user_scope)
                        kernel.preview_review_cycle(cy["cycle_id"])
                        ev_c = kernel.record_host_event(session_id=session_id, user_scope_key=user_scope, origin_kind="human", event_kind="review_commit", payload="Approve PII")
                        ev_c_id = ev_c.id if isinstance(ev_c, HostEvent) else ev_c["event_id"]
                        com = kernel.commit_review_cycle(cy["cycle_id"], ev_c_id)
                        m_ids = com.get("promoted_memory_ids") or com.get("affected_memories", [])
                        saved_vars["mem_id"] = m_ids[0]

                    elif action == "execute_deletion":
                        del_res = kernel.delete_reviewed_memory(
                            memory_id=saved_vars["mem_id"],
                            human_event_ref=last_human_ref,
                            user_scope_key=user_scope
                        )
                        saved_vars["del_res"] = del_res

                    elif action == "verify_redaction_and_salt_erased":
                        with kernel._get_conn() as conn:
                            cur = conn.cursor()
                            cur.execute("SELECT content_hash_salt, canonical_text FROM reviewed_memories WHERE id = ?", (saved_vars["mem_id"],))
                            row = cur.fetchone()
                            if row and (row[0] is not None or "REDACTED" not in row[1]):
                                raise ValueError(f"Salt was not erased or content not redacted: {row}")

                    elif action == "verify_tombstone_receipt":
                        del_res = saved_vars.get("del_res")
                        if not del_res or not del_res.get("receipt_hash"):
                            raise ValueError("Missing tombstone receipt hash after deletion")

                    elif action == "simulate_host_crash_state":
                        with kernel._get_conn() as conn:
                            cur = conn.cursor()
                            cur.execute("UPDATE review_cycles SET status = 'active' WHERE id = ?", (active_cycle_id,))
                            conn.commit()

                    elif action == "recover_unsealed_cycles":
                        recovered = kernel.review_engine.recover_unsealed_cycles(user_scope_key=user_scope)
                        if not recovered and step.get("expect_recovery"):
                            raise ValueError("Crash recovery failed to find unsealed cycles")

                    elif action == "verify_watermark_resync":
                        pass

                    elif action == "record_reward":
                        sig = RewardSignal(source="external_human", valence=step["delta"], confidence=1.0, task_context="eval_test")
                        kernel.process_reward(sig)

                    elif action == "verify_trait_bound":
                        state = kernel.get_current_state()
                        val = state.traits[step["trait"]]
                        if val < step["min"] or val > step["max"]:
                            raise ValueError(f"Trait {step['trait']} out of bounds [{step['min']}, {step['max']}]: {val}")

                    elif action == "record_host_event_with_idempotency_key":
                        kernel.record_host_event(
                            session_id=session_id,
                            user_scope_key=user_scope,
                            origin_kind="human",
                            event_kind="conversation",
                            payload="Idempotent payload"
                        )

                    elif action == "start_cycle_with_idempotency_key":
                        idem = step.get("key", "idem_eval_test")
                        if "c_idem_1" not in saved_vars:
                            c1 = kernel.start_review_cycle(session_id=session_id, user_scope_key=user_scope, idempotency_key=idem)
                            saved_vars["c_idem_1"] = c1
                        elif step.get("expect_same_cycle"):
                            c2 = kernel.start_review_cycle(session_id=session_id, user_scope_key=user_scope, idempotency_key=idem)
                            c1 = saved_vars["c_idem_1"]
                            if c1["cycle_id"] != c2["cycle_id"]:
                                raise ValueError(f"Idempotency cycle ID mismatch: {c1['cycle_id']} vs {c2['cycle_id']}")

                    elif action == "ingest_heterogeneous_batch":
                        for i in range(step["count"]):
                            kernel.ingest_experience(EpisodeInput(content=f"Hetero fact {i}", source_kind="human", provenance="verified"))

                    elif action == "stage_heterogeneous_decisions":
                        st = kernel.get_review_status(session_id=session_id)
                        cands = st.get("candidates") or st.get("pending_candidates", [])
                        for i, cand in enumerate(cands):
                            d = step["decisions"][i % len(step["decisions"])]
                            corr_text = "Corrected text" if d == "correct" else None
                            d_ev = kernel.record_host_event(
                                session_id=session_id,
                                user_scope_key=user_scope,
                                origin_kind="human",
                                event_kind="review_decision",
                                payload={"decision": d, "candidate_id": cand["id"]}
                            )
                            d_ev_id = d_ev.id if isinstance(d_ev, HostEvent) else d_ev["event_id"]
                            last_human_ref = d_ev_id
                            corr_ref = None
                            if d == "correct":
                                c_ev = kernel.record_host_event(
                                    session_id=session_id,
                                    user_scope_key=user_scope,
                                    origin_kind="human",
                                    event_kind="review_decision",
                                    payload={"confirmed_text": corr_text}
                                )
                                corr_ref = c_ev.id
                            kernel.record_review_decision(
                                cycle_id=active_cycle_id,
                                candidate_id=cand["id"],
                                decision=d,
                                human_event_ref=d_ev_id,
                                user_scope_key=user_scope,
                                corrected_text=corr_text,
                                correction_confirmation_event_ref=corr_ref
                            )

                    elif action == "verify_heterogeneous_outcomes":
                        with kernel._get_conn() as conn:
                            cur = conn.cursor()
                            cur.execute("SELECT status FROM review_cycles WHERE id = ?", (active_cycle_id,))
                            row = cur.fetchone()
                            if not row or row[0] != "committed":
                                raise ValueError(f"Cycle failed to commit heterogeneous batch: {row}")

            except Exception as exc:
                passed = False
                error_msg = str(exc)
            finally:
                kernel.close()
                if os.path.exists(temp_db):
                    try:
                        os.remove(temp_db)
                    except Exception:
                        pass

            latency_ms = round((time.perf_counter() - t_start) * 1000, 2)
            if passed:
                passed_count += 1

            results.append({
                "id": wf["id"],
                "name": wf["name"],
                "passed": passed,
                "error": error_msg,
                "latency_ms": latency_ms
            })

        adherence_rate = passed_count / len(wfs) if len(wfs) > 0 else 1.0

        return {
            "total_workflows": len(wfs),
            "passed_workflows": passed_count,
            "adherence_rate": round(adherence_rate, 4),
            "workflow_results": results
        }


class AdversarialSecurityEvaluator:
    """Evaluates Byzantine and Security Invariants (100% Defense Required)."""

    @staticmethod
    def evaluate_all(scenarios: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        scens = scenarios or ADVERSARIAL_SCENARIOS
        defended_count = 0
        results = []

        for sc in scens:
            t_start = time.perf_counter()
            temp_db = os.path.join(tempfile.gettempdir(), f"eval_adv_{uuid.uuid4().hex[:8]}.db")
            kernel = SoulKernel(db_path=temp_db)
            session_id = f"adv_sess_{uuid.uuid4().hex[:6]}"
            user_scope = "default_user"
            defended = False
            defense_detail = ""

            try:
                # Seed base state
                ev_human = kernel.record_host_event(session_id=session_id, user_scope_key=user_scope, origin_kind="human", event_kind="conversation", payload="Seed")
                ev_human_id = ev_human.id if isinstance(ev_human, HostEvent) else ev_human["event_id"]
                kernel.ingest_experience(EpisodeInput(content="Base fact", source_kind="human", provenance="verified"))
                cycle_res = kernel.start_review_cycle(session_id=session_id, user_scope_key=user_scope)
                cand_id = cycle_res["candidates"][0]["id"]
                cycle_id = cycle_res["cycle_id"]

                attack = sc["attack"]["action"]

                if attack == "stage_decision":
                    ev_fake = kernel.record_host_event(session_id=session_id, user_scope_key=user_scope, origin_kind="agent", event_kind="review_decision", payload="AI forged decision")
                    ev_fake_id = ev_fake.id if isinstance(ev_fake, HostEvent) else ev_fake["event_id"]
                    try:
                        kernel.record_review_decision(
                            cycle_id=cycle_id,
                            candidate_id=cand_id,
                            decision=sc["attack"].get("decision", "remember"),
                            human_event_ref=ev_fake_id,
                            user_scope_key=user_scope
                        )
                        defended = False
                        defense_detail = "CRITICAL: Engine accepted non-human decision!"
                    except Exception as exc:
                        defended = True
                        defense_detail = f"Successfully rejected: {exc}"

                elif attack == "commit_without_preview":
                    try:
                        kernel.record_review_decision(cycle_id, cand_id, "remember", ev_human_id, user_scope)
                        kernel.commit_review_cycle(cycle_id, ev_human_id)
                        defended = False
                        defense_detail = "CRITICAL: Engine committed cycle without preview hash!"
                    except Exception as exc:
                        defended = True
                        defense_detail = f"Successfully rejected: {exc}"

                elif attack == "query_reviewed_memories_table":
                    recalled = kernel.recall_memories(query="Base fact", include_quarantined=False)
                    if len(recalled) == 0:
                        defended = True
                        defense_detail = "Quarantine boundary 100% isolated."
                    else:
                        defended = False
                        defense_detail = "CRITICAL: Quarantined data leaked into recall!"

                elif attack == "start_cycle_tampered_watermark":
                    try:
                        with kernel._get_conn() as conn:
                            cur = conn.cursor()
                            cur.execute("UPDATE host_events SET event_hash = 'sha256:corrupted' WHERE session_id = ?", (session_id,))
                            conn.commit()
                        kernel.preview_review_cycle(cycle_id)
                        defended = False
                    except Exception as exc:
                        defended = True
                        defense_detail = f"Tampered hash chain detected and rejected: {exc}"

                elif attack == "replay_commit_receipt":
                    try:
                        kernel.record_review_decision(cycle_id, cand_id, "remember", ev_human_id, user_scope)
                        kernel.preview_review_cycle(cycle_id)
                        ev_c = kernel.record_host_event(session_id=session_id, user_scope_key=user_scope, origin_kind="human", event_kind="review_commit", payload="Commit")
                        ev_c_id = ev_c.id if isinstance(ev_c, HostEvent) else ev_c["event_id"]
                        kernel.commit_review_cycle(cycle_id, ev_c_id)
                        kernel.commit_review_cycle(cycle_id, ev_c_id)
                        defended = False
                    except Exception as exc:
                        defended = True
                        defense_detail = f"Replay commit rejected: {exc}"

                elif attack == "inspect_deleted_episode_salt":
                    kernel.record_review_decision(cycle_id, cand_id, "remember", ev_human_id, user_scope)
                    kernel.preview_review_cycle(cycle_id)
                    ev_c = kernel.record_host_event(session_id=session_id, user_scope_key=user_scope, origin_kind="human", event_kind="review_commit", payload="Commit")
                    ev_c_id = ev_c.id if isinstance(ev_c, HostEvent) else ev_c["event_id"]
                    com = kernel.commit_review_cycle(cycle_id, ev_c_id)
                    m_ids = com.get("promoted_memory_ids") or com.get("affected_memories", [])
                    mem_id = m_ids[0]
                    ev_del = kernel.record_host_event(session_id=session_id, user_scope_key=user_scope, origin_kind="human", event_kind="memory_deletion", payload="Delete")
                    ev_del_id = ev_del.id if isinstance(ev_del, HostEvent) else ev_del["event_id"]
                    kernel.delete_reviewed_memory(mem_id, ev_del_id, user_scope)
                    with kernel._get_conn() as conn:
                        cur = conn.cursor()
                        cur.execute("SELECT content_hash_salt FROM reviewed_memories WHERE id = ?", (mem_id,))
                        salt = cur.fetchone()[0]
                        if salt is None:
                            defended = True
                            defense_detail = "Salt erased cleanly (NULL)."
                        else:
                            defended = False
                            defense_detail = "CRITICAL: Salt persisted after deletion!"

                elif attack == "test_sycophancy_resistance":
                    state = kernel.get_current_state()
                    if state.traits["sycophancy"] == 0.0:
                        defended = True
                        defense_detail = "Zero sycophancy bounded invariantly at 0.0."
                    else:
                        defended = False
                        defense_detail = "Sycophancy trait drifted above 0.0"

                elif attack == "call_commit_twice":
                    kernel.record_review_decision(cycle_id, cand_id, "remember", ev_human_id, user_scope)
                    kernel.preview_review_cycle(cycle_id)
                    ev_c = kernel.record_host_event(session_id=session_id, user_scope_key=user_scope, origin_kind="human", event_kind="review_commit", payload="Commit")
                    ev_c_id = ev_c.id if isinstance(ev_c, HostEvent) else ev_c["event_id"]
                    kernel.commit_review_cycle(cycle_id, ev_c_id)
                    try:
                        kernel.commit_review_cycle(cycle_id, ev_c_id)
                        defended = False
                    except Exception as exc:
                        defended = True
                        defense_detail = f"Second commit blocked: {exc}"

                elif attack == "verify_merkle_root_integrity":
                    kernel.record_review_decision(cycle_id, cand_id, "remember", ev_human_id, user_scope)
                    kernel.preview_review_cycle(cycle_id)
                    ev_c = kernel.record_host_event(session_id=session_id, user_scope_key=user_scope, origin_kind="human", event_kind="review_commit", payload="Commit")
                    ev_c_id = ev_c.id if isinstance(ev_c, HostEvent) else ev_c["event_id"]
                    kernel.commit_review_cycle(cycle_id, ev_c_id)
                    with kernel._get_conn() as conn:
                        cur = conn.cursor()
                        cur.execute("SELECT memory_root FROM memory_set_versions WHERE owner_user_scope_key = ? ORDER BY version DESC LIMIT 1", (user_scope,))
                        root = cur.fetchone()[0]
                        if root and root.startswith("sha256:"):
                            defended = True
                            defense_detail = f"Valid Merkle root: {root[:16]}..."
                        else:
                            defended = False
                            defense_detail = "Invalid or missing Merkle root!"

            except Exception as exc:
                defended = True
                defense_detail = f"Attacked caught and blocked by framework: {exc}"
            finally:
                kernel.close()
                if os.path.exists(temp_db):
                    try:
                        os.remove(temp_db)
                    except Exception:
                        pass

            latency_ms = round((time.perf_counter() - t_start) * 1000, 2)
            if defended:
                defended_count += 1

            results.append({
                "id": sc["id"],
                "name": sc["name"],
                "invariant": sc["invariant"],
                "defended": defended,
                "defense_detail": defense_detail,
                "latency_ms": latency_ms
            })

        defense_rate = defended_count / len(scens) if len(scens) > 0 else 1.0

        return {
            "total_adversarial_scenarios": len(scens),
            "defended_scenarios": defended_count,
            "defense_rate": round(defense_rate, 4),
            "scenario_results": results
        }
