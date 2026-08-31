"""
Soul System Model Context Protocol (MCP) Server v1.2.0
Normative Source: docs/CONSTITUTION.md & docs/REVIEW_CYCLE_SPECIFICATION.md
"""

from __future__ import annotations

import os
import sys
import json
import logging
from typing import Any, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from soul_kernel import SoulKernel, EpisodeInput, TraitUpdate, RewardSignal, SOUL_ENGINE_VERSION

logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [soul-mcp] %(levelname)s %(message)s"
)
log = logging.getLogger("soul_mcp_server")

_kernel: Optional[SoulKernel] = None
_MCP_ORIGINS = {"agent", "tool", "environment", "system"}


def get_kernel() -> SoulKernel:
    global _kernel
    if _kernel is None:
        db_path = os.environ.get("SOUL_DB_PATH", os.path.join(os.path.expanduser("~"), ".soul", "soul.db"))
        _kernel = SoulKernel(db_path=db_path)
        log.info("Initialized Soul Kernel %s at %s", SOUL_ENGINE_VERSION, db_path)

        if os.environ.get("SOUL_DAEMON_ENABLED", "true").lower() in ("true", "1", "yes"):
            _kernel.start_daemon(dream_interval=300, heal_interval=600, homeostasis_interval=60)
            log.info("Started background SoulDaemon supervisor.")
    return _kernel


def _require_human_event(event_id) -> Optional[str]:
    if not isinstance(event_id, str) or not event_id.strip():
        return "human_event_ref is required and must be a host event with origin_kind=human"
    with get_kernel()._get_conn() as conn:
        row = conn.execute(
            "SELECT origin_kind FROM host_events WHERE id = ?;",
            (event_id.strip(),),
        ).fetchone()
    if not row or row[0] != "human":
        return "human_event_ref must be an existing host event with origin_kind=human"
    return None


# ==============================================================================
# MCP TOOL HANDLERS
# ==============================================================================

def _mcp_source_kind(raw) -> str:
    requested = raw.strip().lower() if isinstance(raw, str) else "agent"
    if requested == "human":
        log.warning("Coerced MCP soul_remember source_kind='human' to agent; models cannot self-attest human origin")
        return "agent"
    if requested in {"agent", "environment", "internal"}:
        return requested
    return "agent"


def _mcp_provenance(raw) -> str:
    requested = raw.strip().lower() if isinstance(raw, str) else "observed"
    if requested == "verified":
        log.warning("Coerced MCP soul_remember provenance='verified' to observed; models cannot self-assign verified provenance")
        return "observed"
    if requested in {"observed", "reported", "inferred", "imagined"}:
        return requested
    return "observed"


def _tool_soul_remember(args: dict) -> dict:
    content = args.get("content", "")
    if not content:
        return {"error": "content parameter is required"}
    try:
        ep_input = EpisodeInput(
            source_kind=_mcp_source_kind(args.get("source_kind", "agent")),
            provenance=_mcp_provenance(args.get("provenance", "observed")),
            content=content,
            entity_key=args.get("entity_key"),
            occurred_at=args.get("occurred_at"),
            source_ref=args.get("source_ref"),
            medium=args.get("medium"),
            privacy_class=args.get("privacy_class"),
            content_ref=args.get("content_ref"),
            percept_json=args.get("percept_json"),
            session_id=_chat_session(args) or None,
        )
        res = get_kernel().ingest_experience(ep_input)
        return {"status": "success", "result": res}
    except Exception as extra:
        return {"status": "rejected", "error": str(extra)}


def _tool_soul_get_identity(args: dict) -> dict:
    try:
        state = get_kernel().get_current_state()
        kernel = get_kernel()
        return {
            "soul_version": state.soul_version,
            "constitution_version": state.constitution_version,
            "traits": state.traits,
            "neuromodulators": {
                "dopamine": kernel.bio_engine.dopamine,
                "cortisol": kernel.bio_engine.cortisol,
                "serotonin": kernel.bio_engine.serotonin
            },
            "narrative": state.narrative,
            "unresolved_tensions": state.unresolved_tensions,
            "state_hash": state.state_hash,
            "created_at": state.created_at
        }
    except Exception as exc:
        return {"error": str(exc)}


def _tool_soul_recall(args: dict) -> dict:
    try:
        query = args.get("query", "")
        limit = int(args.get("limit", 5))
        search_mode = args.get("search_mode", "rrf_hybrid")
        memories = get_kernel().recall_memories(
            query=query,
            limit=limit,
            search_mode=search_mode,
            plan_id=str(args.get("plan_id") or "").strip(),
            agent_id=str(args.get("agent_id") or "").strip(),
        )
        return {"status": "success", "search_mode": search_mode, "count": len(memories), "memories": memories}
    except Exception as exc:
        return {"error": str(exc)}


def _tool_soul_digest(args: dict) -> dict:
    try:
        raw = args.get("limit")
        digest = get_kernel().get_memory_digest(
            limit=int(raw) if raw is not None else None,
            plan_id=str(args.get("plan_id") or "").strip(),
            agent_id=str(args.get("agent_id") or "").strip(),
        )
        return {"status": "success", "digest": digest}
    except Exception as exc:
        return {"error": str(exc)}


def _tool_soul_verify(args: dict) -> dict:
    ep_id = args.get("episode_id")
    if not ep_id:
        return {"error": "episode_id parameter is required"}
    try:
        res = get_kernel().verify_experience(episode_id=ep_id)
        return {"status": "success", "result": res}
    except Exception as exc:
        return {"error": str(exc)}


def _tool_soul_reflect(args: dict) -> dict:
    try:
        res = get_kernel().reflect_and_resolve(interpretations=args.get("interpretations"))
        return {"status": "success", "reflection": res}
    except Exception as exc:
        return {"error": str(exc)}


def _tool_soul_dream(args: dict) -> dict:
    try:
        res = get_kernel().run_dream_simulation(
            scenario_prompt=args.get("scenario_prompt") or "",
            outcomes=args.get("outcomes"),
            task_context=args.get("task_context") or "",
        )
        return {"status": "success", "simulation": res}
    except Exception as exc:
        return {"error": str(exc)}


def _tool_soul_dream_score(args: dict) -> dict:
    """Score pending imagined outcomes against a realized external result."""
    try:
        res = get_kernel().score_dreams_against_reality(
            realized_valence=float(args.get("realized_valence", 0.0)),
            confidence=float(args.get("confidence", 1.0)),
            task_context=str(args.get("task_context") or ""),
            limit=int(args.get("limit", 5)),
            evidence_receipt=str(args.get("evidence_receipt") or ""),
        )
        return {"status": "success", **res}
    except Exception as exc:
        return {"error": str(exc)}


def _tool_soul_update_trait(args: dict) -> dict:
    trait = args.get("trait", "")
    new_value = args.get("new_value")
    if not trait or new_value is None:
        return {"error": "trait and new_value parameters are required"}
    try:
        update = TraitUpdate(
            trait=trait,
            new_value=float(new_value),
            evidence_refs=args.get("evidence_refs", [])
        )
        if args.get("is_human_approved"):
            log.warning("Ignored MCP is_human_approved=true; agent tools cannot self-attest human approval")
        new_state = get_kernel().update_trait(update, is_human_approved=False)
        return {
            "status": "committed",
            "soul_version": new_state.soul_version,
            "updated_traits": new_state.traits,
            "state_hash": new_state.state_hash
        }
    except Exception as exc:
        return {"status": "rejected", "error": str(exc)}


def _tool_soul_reward(args: dict) -> dict:
    try:
        source = args.get("source", "external_test")
        valence = float(args.get("valence", 0.0))
        confidence = float(args.get("confidence", 1.0))
    except (TypeError, ValueError):
        return {"status": "rejected", "error": "valence/confidence must be numbers"}
    task_context = args.get("task_context", "General interaction")
    evidence_receipt = args.get("evidence_receipt")
    review_receipt = args.get("review_receipt")

    try:
        signal = RewardSignal(
            source=source,
            valence=max(-1.0, min(1.0, valence)),
            confidence=max(0.0, min(1.0, confidence)),
            task_context=task_context,
            evidence_receipt=evidence_receipt,
            review_receipt=review_receipt,
        )
        new_state = get_kernel().process_reward(
            signal,
            session_id=_chat_session(args),
            plan_id=str(args.get("plan_id") or "").strip(),
            agent_id=str(args.get("agent_id") or "").strip(),
            task_id=str(args.get("task_id") or "").strip(),
        )
        kernel = get_kernel()
        overlay_only = signal.source in ("internal_reflection", "internal_dream")
        if overlay_only:
            sess = kernel.get_memory_digest(
                plan_id=str(args.get("plan_id") or "").strip(),
                agent_id=str(args.get("agent_id") or "").strip(),
            )["session_neuromodulators"]
            nm = {
                "dopamine": sess["dopamine"],
                "cortisol": sess["cortisol"],
                "serotonin": sess["serotonin"],
            }
        else:
            nm = {
                "dopamine": kernel.bio_engine.dopamine,
                "cortisol": kernel.bio_engine.cortisol,
                "serotonin": kernel.bio_engine.serotonin,
            }
        return {
            "status": "overlay_only" if overlay_only else "reward_processed",
            "soul_version": new_state.soul_version,
            "updated_traits": new_state.traits,
            "wrote_identity": not overlay_only,
            "neuromodulators": nm
        }
    except Exception as exc:
        return {"status": "rejected", "error": str(exc)}


def _tool_soul_solver_step(args: dict) -> dict:
    try:
        left = args.get("options_left")
        if left is not None and not isinstance(left, list):
            return {"status": "rejected", "error": "options_left must be an array"}
        res = get_kernel().record_solver_step(
            tool=str(args.get("tool") or ""),
            method=str(args.get("method") or ""),
            outcome=str(args.get("outcome") or ""),
            receipt=str(args.get("receipt") or ""),
            session_id=_chat_session(args),
            plan_id=str(args.get("plan_id") or "").strip(),
            agent_id=str(args.get("agent_id") or "").strip(),
            task_id=str(args.get("task_id") or "").strip(),
            close_plan=bool(args.get("close_plan") or False),
            error=args.get("error"),
            options_left=left,
        )
        return {"status": "success", "result": res}
    except Exception as exc:
        return {"status": "rejected", "error": str(exc)}


def _chat_session(args: dict) -> str:
    sid = args.get("session_id")
    return sid.strip() if isinstance(sid, str) and sid.strip() else ""


def _tool_soul_rollback(args: dict) -> dict:
    target_ver = args.get("target_version")
    reason = args.get("reason", "Operator manual rollback")
    if not target_ver:
        return {"error": "target_version parameter is required"}
    session_id = _chat_session(args)
    if not session_id and not args.get("human_event_ref"):
        return {
            "status": "failed",
            "error": "soul_rollback requires session_id (chat path) or human_event_ref with origin_kind=human (Tier 2 destructive operation).",
            "requires_out_of_band": True,
            "command": f"soul-host rollback {target_ver}",
        }
    if session_id and not args.get("human_event_ref"):
        try:
            new_state = get_kernel().apply_chat_identity_rollback(session_id, int(target_ver), reason=reason)
            return {
                "status": "rolled_back",
                "soul_version": new_state.soul_version,
                "restored_traits": new_state.traits,
                "state_hash": new_state.state_hash,
            }
        except PermissionError as exc:
            return {
                "status": "rejected",
                "error": str(exc),
                "requires_out_of_band": True,
                "command": f"soul-host rollback {target_ver}",
            }
        except Exception as exc:
            return {"status": "failed", "error": str(exc)}
    gate = _require_human_event(args.get("human_event_ref"))
    if gate:
        return {
            "status": "failed",
            "error": gate,
            "requires_out_of_band": True,
            "command": f"soul-host rollback {target_ver}",
        }
    try:
        new_state = get_kernel().rollback_to_version(int(target_ver), operator_reason=reason)
        return {
            "status": "rolled_back",
            "soul_version": new_state.soul_version,
            "restored_traits": new_state.traits,
            "state_hash": new_state.state_hash,
        }
    except Exception as exc:
        return {"status": "failed", "error": str(exc)}


def _tool_soul_heal(args: dict) -> dict:
    level = int(args.get("level", 1))
    reason = args.get("reason", "Automated health repair")
    session_id = _chat_session(args)
    if not session_id and not args.get("human_event_ref"):
        return {
            "status": "failed",
            "error": "soul_heal requires session_id (chat level 1) or human_event_ref with origin_kind=human (Tier 2 levels 2/3)",
            "requires_out_of_band": True,
            "command": f"soul-host heal --level {level}",
        }
    if level == 1:
        try:
            if session_id:
                res = get_kernel().apply_chat_heal(session_id, level=level, reason=reason)
            else:
                res = get_kernel().heal_soul_state(level=level, reason=reason)
            return {"status": "success", "healing_result": res}
        except Exception as exc:
            return {"error": str(exc)}
    else:
        if session_id and not args.get("human_event_ref"):
            try:
                res = get_kernel().apply_chat_heal(session_id, level=level, reason=reason)
                return {"status": "success", "healing_result": res}
            except PermissionError as exc:
                return {
                    "status": "rejected",
                    "error": str(exc),
                    "requires_out_of_band": True,
                    "command": f"soul-host heal --level {level}",
                }
            except Exception as exc:
                return {"error": str(exc)}
        gate = _require_human_event(args.get("human_event_ref"))
        if gate:
            return {
                "status": "failed",
                "error": gate,
                "requires_out_of_band": True,
                "command": f"soul-host heal --level {level}",
            }
        try:
            res = get_kernel().heal_soul_state(level=level, reason=reason)
            return {"status": "success", "healing_result": res}
        except Exception as exc:
            return {"error": str(exc)}


def _tool_soul_daemon_status(args: dict) -> dict:
    try:
        kernel = get_kernel()
        daemon = kernel.daemon_worker
        if daemon:
            return {
                "running": daemon.running,
                "dream_interval_seconds": daemon.dream_interval,
                "heal_interval_seconds": daemon.heal_interval,
                "homeostasis_interval_seconds": daemon.homeostasis_interval,
                "dream_due": bool(daemon.stats.get("dream_due")),
                "heal_due": bool(daemon.stats.get("heal_due")),
                "neuromodulators": {
                    "dopamine": kernel.bio_engine.dopamine,
                    "cortisol": kernel.bio_engine.cortisol,
                    "serotonin": kernel.bio_engine.serotonin
                },
                "statistics": daemon.stats
            }
        return {"running": False, "message": "SoulDaemon is currently disabled or stopped."}
    except Exception as exc:
        return {"error": str(exc)}


def _tool_soul_host_event(args: dict) -> dict:
    session_id = args.get("session_id")
    if not session_id:
        return {"error": "session_id parameter is required"}
    try:
        requested_origin = args.get("origin_kind", "agent")
        requested_norm = (
            requested_origin.strip().lower().replace("\x00", "")
            if isinstance(requested_origin, str) else ""
        )
        origin_kind = requested_norm if requested_norm in _MCP_ORIGINS else "agent"
        if requested_norm == "human":
            log.warning(
                "Coerced MCP soul_host_event origin_kind=%r to agent; models cannot self-attest human origin",
                requested_origin,
            )
        ev = get_kernel().record_host_event(
            session_id=session_id,
            user_scope_key=args.get("user_scope_key", "default_user"),
            project_scope_key=args.get("project_scope_key"),
            origin_kind=origin_kind,
            event_kind=args.get("event_kind", "conversation"),
            payload=args.get("payload", "")
        )
        return {"status": "success", "event_id": ev.id, "event_hash": ev.event_hash, "sequence": ev.sequence}
    except Exception as exc:
        return {"error": str(exc)}


def _tool_soul_review_start(args: dict) -> dict:
    session_id = args.get("session_id")
    if not session_id:
        return {"error": "session_id parameter is required"}
    try:
        res = get_kernel().start_review_cycle(
            session_id=session_id,
            user_scope_key=args.get("user_scope_key", "default_user"),
            project_scope_key=args.get("project_scope_key"),
            trigger_kind=args.get("trigger_kind", "explicit")
        )
        return {"status": "success", "review_cycle": res}
    except Exception as exc:
        return {"error": str(exc)}


def _tool_soul_review_status(args: dict) -> dict:
    session_id = args.get("session_id")
    if not session_id:
        return {"error": "session_id parameter is required"}
    try:
        status = get_kernel().get_review_status(session_id=session_id)
        if not status:
            return {"status": "no_cycle_found"}
        return {"status": "success", "review_status": status}
    except Exception as exc:
        return {"error": str(exc)}


def _tool_soul_review_stage_decision(args: dict) -> dict:
    cycle_id = args.get("cycle_id")
    candidate_id = args.get("candidate_id")
    decision = args.get("decision")
    human_event_ref = args.get("human_event_ref")
    if not cycle_id or not candidate_id or not decision or not human_event_ref:
        return {"error": "cycle_id, candidate_id, decision, and human_event_ref are required"}
    try:
        res = get_kernel().record_review_decision(
            cycle_id=cycle_id,
            candidate_id=candidate_id,
            decision=decision,
            human_event_ref=human_event_ref,
            user_scope_key=args.get("user_scope_key", "default_user"),
            corrected_text=args.get("corrected_text"),
            correction_confirmation_event_ref=args.get("correction_confirmation_event_ref")
        )
        return {"status": "success", "decision_record": res}
    except Exception as exc:
        return {"status": "rejected", "error": str(exc)}


def _tool_soul_review_preview(args: dict) -> dict:
    cycle_id = args.get("cycle_id")
    if not cycle_id:
        return {"error": "cycle_id parameter is required"}
    try:
        preview = get_kernel().preview_review_cycle(cycle_id=cycle_id)
        return {"status": "success", "preview": preview}
    except Exception as exc:
        return {"status": "rejected", "error": str(exc)}


def _tool_soul_review_commit(args: dict) -> dict:
    cycle_id = args.get("cycle_id")
    commit_human_event_ref = args.get("commit_human_event_ref")
    if not cycle_id or not commit_human_event_ref:
        return {"error": "cycle_id and commit_human_event_ref are required"}
    try:
        receipt = get_kernel().commit_review_cycle(
            cycle_id=cycle_id,
            commit_human_event_ref=commit_human_event_ref
        )
        return {"status": "success", "receipt": receipt}
    except Exception as exc:
        return {"status": "rejected", "error": str(exc)}


def _tool_soul_review_chat_commit(args: dict) -> dict:
    cycle_id = args.get("cycle_id")
    session_id = args.get("session_id")
    decisions = args.get("decisions")
    if not cycle_id or not session_id or not decisions:
        return {"error": "session_id, cycle_id, and decisions are required"}
    try:
        res = get_kernel().apply_chat_review(
            session_id=session_id,
            cycle_id=cycle_id,
            decisions=decisions,
            user_scope_key=args.get("user_scope_key", "default_user"),
            project_scope_key=args.get("project_scope_key"),
        )
        return {"status": res.get("status") or "committed", "result": res}
    except Exception as extra:
        return {"status": "rejected", "error": str(extra)}


def _tool_soul_memory_rollback(args: dict) -> dict:
    target_version = args.get("target_version")
    human_event_ref = args.get("human_event_ref")
    session_id = _chat_session(args)
    if target_version is None:
        return {"error": "target_version is required"}
    if session_id and not human_event_ref:
        try:
            res = get_kernel().apply_chat_memory_rollback(
                session_id,
                int(target_version),
                user_scope_key=args.get("user_scope_key", "default_user"),
            )
            return {"status": "success", "rollback_result": res}
        except PermissionError as exc:
            return {
                "status": "rejected",
                "error": str(exc),
                "requires_out_of_band": True,
                "command": f"soul-host rollback-memory {target_version}",
            }
        except Exception as exc:
            return {"status": "rejected", "error": str(exc)}
    if not human_event_ref:
        return {
            "status": "rejected",
            "error": "Memory rollback requires out-of-band human authorization.",
            "requires_out_of_band": True,
            "command": f"soul-host rollback-memory {target_version}",
        }
    try:
        res = get_kernel().rollback_reviewed_memory_set(
            target_version=int(target_version),
            human_event_ref=human_event_ref,
            user_scope_key=args.get("user_scope_key", "default_user")
        )
        return {"status": "success", "rollback_result": res}
    except Exception as exc:
        return {"status": "rejected", "error": str(exc)}


def _tool_soul_memory_delete(args: dict) -> dict:
    memory_id = args.get("memory_id")
    human_event_ref = args.get("human_event_ref")
    session_id = _chat_session(args)
    if not memory_id:
        return {"error": "memory_id is required"}
    if session_id and not human_event_ref:
        try:
            res = get_kernel().apply_chat_memory_delete(
                session_id,
                memory_id,
                user_scope_key=args.get("user_scope_key", "default_user"),
            )
            return {"status": "success", "deletion_result": res}
        except PermissionError as exc:
            return {
                "status": "rejected",
                "error": str(exc),
                "requires_out_of_band": True,
                "command": f"soul-host delete-memory {memory_id}",
            }
        except Exception as exc:
            return {"status": "rejected", "error": str(exc)}
    if not human_event_ref:
        return {
            "status": "rejected",
            "error": "Memory deletion requires out-of-band human authorization.",
            "requires_out_of_band": True,
            "command": f"soul-host delete-memory {memory_id}",
        }
    try:
        res = get_kernel().delete_reviewed_memory(
            memory_id=memory_id,
            human_event_ref=human_event_ref,
            user_scope_key=args.get("user_scope_key", "default_user")
        )
        return {"status": "success", "deletion_result": res}
    except Exception as exc:
        return {"status": "rejected", "error": str(exc)}


# ==============================================================================
# TOOL REGISTRY
# ==============================================================================

TOOLS = [
    {
        "name": "soul_remember",
        "description": "Quarantine a note. MCP cannot set source_kind=human.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content":     {"type": "string", "description": "Memory text or interaction content"},
                "source_kind": {"type": "string", "enum": ["agent", "environment", "internal"], "default": "agent"},
                "provenance":  {"type": "string", "enum": ["observed", "reported", "inferred", "imagined"], "default": "observed"},
                "entity_key":  {"type": "string", "description": "Optional entity key for single-current-value facts"},
                "occurred_at": {"type": "string", "description": "When the percept occurred (RFC3339). Defaults to created_at."},
                "source_ref":  {"type": "string", "description": "Pseudonymous source identifier"},
                "medium":      {"type": "string", "enum": ["text", "image", "audio", "video", "document", "sensor", "mixed"]},
                "privacy_class": {"type": "string", "enum": ["public", "internal", "personal", "sensitive"]},
                "content_ref": {"type": "string", "description": "Pointer to payload; blobs are not stored"},
                "percept_json": {"description": "Optional percept payload (object or JSON string). claims are NLI'd on verify. Max ~16k chars."},
                "session_id": {"type": "string"}
            },
            "required": ["content"]
        },
        "_handler": _tool_soul_remember
    },
    {
        "name": "soul_get_identity",
        "description": "Retrieve Soul's current operational identity state, bounded trait values, narrative, and state hash.",
        "inputSchema": {"type": "object", "properties": {}},
        "_handler": _tool_soul_get_identity
    },
    {
        "name": "soul_recall",
        "description": "Search reviewed (long-term) memory via RRF hybrid, dense/hash vector, or BM25. Unreviewed quarantine is omitted.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query":       {"type": "string", "description": "Search query"},
                "limit":       {"type": "integer", "default": 5},
                "search_mode": {"type": "string", "enum": ["rrf_hybrid", "dense", "bm25"], "default": "rrf_hybrid"},
                "plan_id":     {"type": "string", "description": "Optional: apply in-plan recall cap from this overlay"},
                "agent_id":    {"type": "string", "description": "Optional: sub-agent wallet for the in-plan cap"}
            }
        },
        "_handler": _tool_soul_recall
    },
    {
        "name": "soul_digest",
        "description": "Session start: traits, behavior orders, due flags, this-plan working traces, session overlay, and newest reviewed facts. Follow behavior. Unreviewed episodes omitted.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit":    {"type": "integer", "default": 5},
                "plan_id":  {"type": "string", "description": "Optional: this-plan working + overlay"},
                "agent_id": {"type": "string", "description": "Optional: this sub-agent overlay and traces"}
            }
        },
        "_handler": _tool_soul_digest
    },
    {
        "name": "soul_verify",
        "description": "Token-overlap NLI heuristic plus epistemic rank (not a transformer).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "episode_id": {"type": "string", "description": "Episode ID to verify"}
            },
            "required": ["episode_id"]
        },
        "_handler": _tool_soul_verify
    },
    {
        "name": "soul_reflect",
        "description": "If no tensions: empty. Else first call returns evidence; second call stores agent interpretations. Does not write identity.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "interpretations": {
                    "type": "array",
                    "description": "Agent-written hypotheses. Omit on the first call.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "hypothesis": {"type": "string"},
                            "confidence": {"type": "number"},
                            "action": {"type": "string"}
                        }
                    }
                }
            }
        },
        "_handler": _tool_soul_reflect
    },
    {
        "name": "soul_dream",
        "description": "First call returns a context packet (needs_thought). Second call records >=2 imagined outcomes. Does not write identity.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "scenario_prompt": {"type": "string", "description": "Hypothetical scenario"},
                "task_context": {"type": "string", "description": "Task bucket used for RPE expectation matching (e.g. 'deploy-db-migration'). Same key later scores dreams against reality."},
                "outcomes": {
                    "type": "array",
                    "description": "At least two imagined outcomes (strings or branch objects). Omit to receive the context packet. Branch objects may carry 'likelihood' (-1..1, signed predicted valence) so reality scoring can compute a dream-RPE.",
                    "items": {
                        "anyOf": [
                            {"type": "string"},
                            {
                                "type": "object",
                                "properties": {
                                    "variable_flipped": {"type": "string"},
                                    "hypothesis": {"type": "string"},
                                    "outcome": {"type": "string"},
                                    "text": {"type": "string"},
                                    "name": {"type": "string"},
                                    "likelihood": {"type": "number"},
                                    "severity": {"type": "string"}
                                }
                            }
                        ]
                    }
                }
            }
        },
        "_handler": _tool_soul_dream
    },
    {
        "name": "soul_dream_score",
        "description": "Close the dream loop: score pending imagined outcomes against the realized result (dream-RPE), updating persistent expectations at half weight. Auto-fires on negative receipted external_test rewards. Requires evidence_receipt of a redeemed external_test reward for this task_context — unbacked scoring is refused.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "realized_valence": {"type": "number", "description": "Actual outcome valence in [-1, 1]"},
                "confidence": {"type": "number", "description": "Confidence in [0, 1], default 1.0"},
                "task_context": {"type": "string", "description": "Context bucket; falls back to each dream's stored task_context"},
                "limit": {"type": "integer", "description": "Max unscored dreams to score, default 5"},
                "evidence_receipt": {"type": "string", "description": "Required: evidence_receipt of a redeemed external_test reward matching this task_context"}
            },
            "required": ["realized_valence", "evidence_receipt"]
        },
        "_handler": _tool_soul_dream_score
    },
    {
        "name": "soul_solver_step",
        "description": "Record a receipted solver fail/succeed/dead_end. Refuses if this session has pending review candidates. Session overlay only.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tool": {"type": "string", "description": "What was invoked (test runner, edit, grep, sub-agent, …)"},
                "method": {"type": "string", "description": "How it was used"},
                "outcome": {"type": "string", "enum": ["fail", "succeed", "dead_end"]},
                "receipt": {"type": "string", "description": "Test id, command exit, or check id. Required."},
                "error": {"type": "string"},
                "options_left": {"type": "array", "items": {"type": "string"}},
                "session_id": {"type": "string"},
                "plan_id": {"type": "string"},
                "agent_id": {"type": "string", "description": "Sub-agent id; parent omits or uses empty"},
                "task_id": {"type": "string", "description": "Optional task grouping inside a plan"},
                "close_plan": {"type": "boolean", "description": "Quarantine compact traces for this plan_id, then drop overlay. Not soul_states."}
            },
            "required": ["tool", "method", "outcome", "receipt"]
        },
        "_handler": _tool_soul_solver_step
    },
    {
        "name": "soul_reward",
        "description": "Identity reward: external_test needs evidence_receipt; external_human needs session_id and output-review review_receipt. internal_* are in-plan self-score (overlay only; requires plan_id or a live solver overlay; idle calls refused).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source":           {"type": "string", "enum": ["external_test", "external_human", "internal_reflection", "internal_dream"]},
                "valence":          {"type": "number", "description": "Reward valence between -1.0 (failure/criticism) and 1.0 (success/praise)"},
                "confidence":       {"type": "number", "description": "Confidence of signal [0.0 to 1.0]"},
                "task_context":     {"type": "string", "description": "Brief context of what task succeeded or failed"},
                "evidence_receipt": {"type": "string", "description": "Required for external_test: benchmark run ID or test log receipt"},
                "review_receipt":   {"type": "string", "description": "Required for external_human: review_commit receipt from output review"},
                "session_id":       {"type": "string", "description": "Required for external_human: this chat session id"},
                "plan_id":          {"type": "string", "description": "In-plan self-score: this plan. Omit only if a solver overlay or working buffer is already live."},
                "agent_id":         {"type": "string", "description": "Sub-agent id for in-plan self-score wallets"},
                "task_id":          {"type": "string", "description": "Optional task grouping inside a plan"}
            },
            "required": ["source", "valence", "task_context"]
        },
        "_handler": _tool_soul_reward
    },
    {
        "name": "soul_update_trait",
        "description": "Propose an update to a bounded control trait parameter (e.g. sycophancy, audacity, epistemic_humility). Autonomous writes need >=2 evidence_refs, |Δ|<=10, 7-day |Δ| sum<=30.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "trait":              {"type": "string"},
                "new_value":          {"type": "number"},
                "evidence_refs":      {"type": "array", "items": {"type": "string"}}
            },
            "required": ["trait", "new_value"]
        },
        "_handler": _tool_soul_update_trait
    },
    {
        "name": "soul_rollback",
        "description": "Revert the soul state and active identity traits to a previous exact version. This is a Tier 2 destructive operation requiring soul_host approval. Out-of-band authorization command: 'soul-host rollback <version>'.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target_version":  {"type": "integer", "description": "Target identity version number to revert to"},
                "session_id":      {"type": "string", "description": "Chat session identifier for chat-authorized rollback"},
                "reason":          {"type": "string", "default": "Operator manual rollback"}
            },
            "required": ["target_version"]
        },
        "_handler": _tool_soul_rollback
    },
    {
        "name": "soul_heal",
        "description": "Trigger automated state repair for the soul engine (level 1=routine recalibration, 2=rollback, 3=reset). Levels >= 2 are Tier 2 destructive operations requiring soul_host approval.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "level":           {"type": "integer", "default": 1, "description": "Healing level (1=homeostasis recalibration, 2=rollback, 3=quarantine freeze)"},
                "session_id":      {"type": "string", "description": "Chat session identifier for chat-authorized level 1 heal"},
                "reason":          {"type": "string", "default": "Automated health repair"}
            }
        },
        "_handler": _tool_soul_heal
    },
    {
        "name": "soul_daemon_status",
        "description": "Inspect status, execution counters, and intervals of the background SoulDaemon supervisor.",
        "inputSchema": {"type": "object", "properties": {}},
        "_handler": _tool_soul_daemon_status
    },
    {
        "name": "soul_host_event",
        "description": "Append an authentic host event (conversation, tool result, lifecycle) to the tamper-evident log. MCP callers cannot set origin_kind=human.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id":        {"type": "string", "description": "Host session ID"},
                "user_scope_key":    {"type": "string", "default": "default_user"},
                "project_scope_key": {"type": "string"},
                "origin_kind":       {"type": "string", "enum": ["agent", "tool", "environment", "system"], "default": "agent"},
                "event_kind":        {"type": "string", "enum": ["conversation", "tool_result", "session_lifecycle", "review_decision", "review_commit", "memory_rollback", "memory_deletion"], "default": "conversation"},
                "payload":           {"type": ["string", "object"]}
            },
            "required": ["session_id"]
        },
        "_handler": _tool_soul_host_event
    },
    {
        "name": "soul_review_start",
        "description": "Open a Soul Review Cycle (watermark + extract). Call when a subject is finished, when a piece of work is done, and before starting a plan if quarantine is non-empty; also when the human types SEAL or /seacom. trigger_kind=explicit. Interview as a Review plan with several options, one item at a time. Starting the cycle is not a commit. After this run's Review plan picks, call soul_review_chat_commit.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id":        {"type": "string"},
                "user_scope_key":    {"type": "string", "default": "default_user"},
                "project_scope_key": {"type": "string"},
                "trigger_kind":      {"type": "string", "enum": ["explicit", "new_session", "archive", "shutdown", "replacement", "idle"], "default": "explicit"}
            },
            "required": ["session_id"]
        },
        "_handler": _tool_soul_review_start
    },
    {
        "name": "soul_review_status",
        "description": "Get current review cycle status, pending memory candidates, and preview hash.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"}
            },
            "required": ["session_id"]
        },
        "_handler": _tool_soul_review_status
    },
    {
        "name": "soul_review_stage_decision",
        "description": "Stage a human review decision (remember, correct, session_only, reject, defer, replace_old).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cycle_id":                           {"type": "string"},
                "candidate_id":                       {"type": "string"},
                "decision":                           {"type": "string", "enum": ["remember", "correct", "session_only", "reject", "defer", "replace_old", "keep_both_with_context", "keep_old", "reject_both"]},
                "human_event_ref":                    {"type": "string", "description": "Host event ID establishing human origin"},
                "user_scope_key":                     {"type": "string", "default": "default_user"},
                "corrected_text":                     {"type": "string"},
                "correction_confirmation_event_ref":  {"type": "string"}
            },
            "required": ["cycle_id", "candidate_id", "decision", "human_event_ref"]
        },
        "_handler": _tool_soul_review_stage_decision
    },
    {
        "name": "soul_review_preview",
        "description": "Run 12-point deterministic validation and generate atomic review preview diff with SHA-256 hash.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cycle_id": {"type": "string"}
            },
            "required": ["cycle_id"]
        },
        "_handler": _tool_soul_review_preview
    },
    {
        "name": "soul_review_commit",
        "description": "Enforce pre-commit checks 13-17 and atomically promote memories into active set with cryptographic receipt.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cycle_id":               {"type": "string"},
                "commit_human_event_ref": {"type": "string", "description": "Human host event ID approving the preview hash"}
            },
            "required": ["cycle_id", "commit_human_event_ref"]
        },
        "_handler": _tool_soul_review_commit
    },
    {
        "name": "soul_review_chat_commit",
        "description": "Promote after this run's Review plan picks (remember / correct / session_only / reject), or when they typed /seacom, SEAL AND COMMIT, or COMMIT. Do not call at cycle start with no picks, or on idle/bye.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "cycle_id": {"type": "string"},
                "user_scope_key": {"type": "string", "default": "default_user"},
                "project_scope_key": {"type": "string"},
                "decisions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "candidate_id": {"type": "string"},
                            "decision": {
                                "type": "string",
                                "enum": [
                                    "remember", "correct", "session_only", "reject", "defer",
                                    "replace_old", "keep_both_with_context", "keep_old", "reject_both"
                                ]
                            },
                            "corrected_text": {"type": "string"}
                        },
                        "required": ["candidate_id", "decision"]
                    }
                }
            },
            "required": ["session_id", "cycle_id", "decisions"]
        },
        "_handler": _tool_soul_review_chat_commit
    },
    {
        "name": "soul_memory_rollback",
        "description": "Execute forward-only rollback of active reviewed memory set to target version with audit receipt. Destructive operation requiring out-of-band authorization via 'soul-host rollback-memory <version>'.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target_version":  {"type": "integer", "description": "Target memory set version number"},
                "session_id":      {"type": "string", "description": "Chat session identifier for chat-authorized rollback"},
                "user_scope_key":  {"type": "string", "default": "default_user"}
            },
            "required": ["target_version"]
        },
        "_handler": _tool_soul_memory_rollback
    },
    {
        "name": "soul_memory_delete",
        "description": "Permanently delete a reviewed memory and cascade delete all its provenance history (GDPR right to be forgotten). Destructive operation requiring out-of-band authorization via 'soul-host delete-memory <id>'.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "memory_id":       {"type": "string", "description": "Unique identifier of the reviewed memory to delete"},
                "session_id":      {"type": "string", "description": "Chat session identifier for chat-authorized deletion"},
                "user_scope_key":  {"type": "string", "default": "default_user"}
            },
            "required": ["memory_id"]
        },
        "_handler": _tool_soul_memory_delete
    }
]


# ==============================================================================
# JSON-RPC / MCP STDIO SERVER HANDLER
# ==============================================================================

SERVER_INFO = {"name": "soul-mcp-server", "version": SOUL_ENGINE_VERSION}
CAPABILITIES = {
    "tools": {"listChanged": False},
}
_client_capabilities: Dict[str, Any] = {}

# Every MCP client gets this. Review starts at work-done; picks on the Review plan commit.
INSTRUCTIONS = (
    "At session start call soul_digest and follow digest.behavior. "
    "If digest.dream_due, call soul_dream once for a context packet, then again with >=2 imagined outcomes. "
    "If digest.heal_due, Level 1 heal is chat-authorized; Level 2/3 requires 'soul-host approve heal'. "
    "If digest.remember_due, call soul_remember for a distilled lesson — not soul_reward. "
    "If digest.solver_active, obey digest.working; do not retry a failed (tool, method) pair. "
    "If pending review candidates exist for this chat, do not call soul_solver_step until the Review plan is picked. "
    "If digest.dead_end is set, run two-phase soul_dream. "
    "If digest.reflect_due, call soul_reflect the same way with interpretations. "
    "Call soul_remember for durable outcomes (test results, decisions, facts worth keeping). "
    "Call soul_solver_step for receipted fail/succeed/dead_end during a plan — not soul_remember, not soul_reward. "
    "soul_reward writes identity only for external_test with evidence_receipt, or external_human with this chat session_id and review_receipt from output review; internal_reflection/internal_dream are session overlay. "
    "Start human review (soul_review_start, session_id=this chat, trigger_kind=explicit) when a subject is finished, when a piece of work is done, and before starting a plan, if quarantine has candidates; interview one at a time (max 5). "
    "If 0 candidates, skip the interview (no empty ceremony). Starting review is not a commit. "
    "Present a Review plan with the host native question/plan picker when the host has one (clickable options: remember / correct / session_only / reject / defer). A markdown numbered list is fallback only if the host has no picker. One item per wait. "
    "picks on the Review plan commit: when they pick remember / correct / session_only / reject (or a contradiction set), after this run's picks call soul_review_chat_commit immediately — same as /seacom / COMMIT. "
    "defer is not approval for that item. Do not wait for a second slash. "
    "User command /seacom (also SEACOM, SEAL AND COMMIT) promotes leftover pending items the same way. "
    "SEAL or /soul-seal starts the interview; completing this run's picks is the commit. "
    "Idle/bye do not commit. "
    "For DELETE / ROLLBACK / HEAL L2+, run 'soul-host approve' (or instruct the human to run soul_host CLI) instead of passing session_id in-band. "
    "soul_host_event still cannot set origin_kind=human. Do not run soul_host yourself."
)


def _handle_jsonrpc(req: dict) -> Optional[dict]:
    if not isinstance(req, dict):
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}}
    method = req.get("method", "")
    req_id = req.get("id")
    raw_params = req.get("params")
    if raw_params is not None and not isinstance(raw_params, dict):
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32602, "message": "params must be an object"}}
    params = raw_params if isinstance(raw_params, dict) else {}

    def ok(res):
        return {"jsonrpc": "2.0", "id": req_id, "result": res}

    def err(code, msg):
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": msg}}

    if req_id is None and method.startswith("notifications/"):
        return None

    if method == "initialize":
        global _client_capabilities
        _client_capabilities = params.get("capabilities") or {}
        return ok({
            "protocolVersion": "2024-11-05",
            "capabilities": CAPABILITIES,
            "serverInfo": SERVER_INFO,
            "instructions": INSTRUCTIONS,
        })

    if method == "notifications/initialized":
        return None

    if method == "ping":
        return ok({})

    if method == "tools/list":
        tools_out = [{"name": t["name"], "description": t["description"], "inputSchema": t["inputSchema"]} for t in TOOLS]
        return ok({"tools": tools_out})

    if method == "tools/call":
        name = params.get("name", "")
        arguments = params.get("arguments")
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            return err(-32602, "arguments must be an object")
        spec = next((t for t in TOOLS if t["name"] == name), None)
        if spec is None:
            return err(-32601, f"Unknown tool: {name}")
        required = (spec.get("inputSchema") or {}).get("required") or []
        missing = [k for k in required if arguments.get(k) in (None, "")]
        if missing:
            return ok({
                "content": [{"type": "text", "text": json.dumps({"error": f"missing required: {', '.join(missing)}"})}],
                "isError": True,
            })
        handler = spec["_handler"]
        try:
            res = handler(arguments)
            is_err = isinstance(res, dict) and bool(res.get("error"))
            return ok({
                "content": [{"type": "text", "text": json.dumps(res, indent=2)}],
                "isError": is_err,
            })
        except Exception as exc:
            log.exception("Tool %s raised exception", name)
            return err(-32603, str(exc))
        finally:
            if _kernel is not None:
                _kernel.close_thread_conn()

    return err(-32601, f"Method not found: {method}")


def main():
    log.info("Starting Soul MCP Server %s on stdio...", SOUL_ENGINE_VERSION)
    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer

    # Trigger initialization
    get_kernel()

    while True:
        try:
            line = stdin.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
            except json.JSONDecodeError as exc:
                resp = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": f"Parse error: {exc}"}}
                stdout.write(json.dumps(resp).encode() + b"\n")
                stdout.flush()
                continue

            resp = _handle_jsonrpc(req)
            if resp is not None:
                stdout.write(json.dumps(resp, ensure_ascii=False).encode() + b"\n")
                stdout.flush()
        except (EOFError, KeyboardInterrupt):
            break
        except Exception as exc:
            log.exception("Unhandled error in MCP loop: %s", exc)
            try:
                rid = None
                try:
                    rid = json.loads(line).get("id")
                except Exception:
                    pass
                resp = {"jsonrpc": "2.0", "id": rid, "error": {"code": -32603, "message": str(exc)}}
                stdout.write(json.dumps(resp).encode() + b"\n")
                stdout.flush()
            except Exception:
                pass

    if _kernel:
        _kernel.close()


if __name__ == "__main__":
    main()
