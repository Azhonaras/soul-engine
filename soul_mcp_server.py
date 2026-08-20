"""
Soul System Model Context Protocol (MCP) Server v1.0.0
Normative Source: soul-constitution-v0.2.md & soul-system-architecture.json
"""

from __future__ import annotations

import os
import sys
import json
import logging
from typing import Any, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from soul_kernel import SoulKernel, EpisodeInput, TraitUpdate, RewardSignal

logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [soul-mcp] %(levelname)s %(message)s"
)
log = logging.getLogger("soul_mcp_server")

_kernel: Optional[SoulKernel] = None


def get_kernel() -> SoulKernel:
    global _kernel
    if _kernel is None:
        db_path = os.environ.get("SOUL_DB_PATH", os.path.join(os.path.expanduser("~"), ".soul", "soul.db"))
        _kernel = SoulKernel(db_path=db_path)
        log.info("Initialized Soul Kernel v1.0.0 at %s", db_path)

        if os.environ.get("SOUL_DAEMON_ENABLED", "true").lower() in ("true", "1", "yes"):
            _kernel.start_daemon(dream_interval=300, heal_interval=600, homeostasis_interval=60)
            log.info("Started background SoulDaemon supervisor.")
    return _kernel


# ==============================================================================
# MCP TOOL HANDLERS
# ==============================================================================

def _tool_soul_remember(args: dict) -> dict:
    content = args.get("content", "")
    if not content:
        return {"error": "content parameter is required"}
    try:
        ep_input = EpisodeInput(
            source_kind=args.get("source_kind", "human"),
            provenance=args.get("provenance", "observed"),
            content=content,
            entity_key=args.get("entity_key")
        )
        res = get_kernel().ingest_experience(ep_input)
        return {"status": "success", "result": res}
    except Exception as exc:
        return {"status": "rejected", "error": str(exc)}


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
        memories = get_kernel().recall_memories(query=query, limit=limit, search_mode=search_mode)
        return {"status": "success", "search_mode": search_mode, "count": len(memories), "memories": memories}
    except Exception as exc:
        return {"error": str(exc)}


def _tool_soul_digest(args: dict) -> dict:
    try:
        limit = int(args.get("limit", 5))
        digest = get_kernel().get_memory_digest(limit=limit)
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
        res = get_kernel().reflect_and_resolve()
        return {"status": "success", "reflection": res}
    except Exception as exc:
        return {"error": str(exc)}


def _tool_soul_dream(args: dict) -> dict:
    prompt = args.get("scenario_prompt", "")
    if not prompt:
        return {"error": "scenario_prompt parameter is required"}
    try:
        res = get_kernel().run_dream_simulation(scenario_prompt=prompt)
        return {"status": "success", "simulation": res}
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
        is_human = args.get("is_human_approved", False)
        new_state = get_kernel().update_trait(update, is_human_approved=is_human)
        return {
            "status": "committed",
            "soul_version": new_state.soul_version,
            "updated_traits": new_state.traits,
            "state_hash": new_state.state_hash
        }
    except Exception as exc:
        return {"status": "rejected", "error": str(exc)}


def _tool_soul_reward(args: dict) -> dict:
    source = args.get("source", "external_test")
    valence = float(args.get("valence", 0.0))
    confidence = float(args.get("confidence", 1.0))
    task_context = args.get("task_context", "General interaction")
    evidence_receipt = args.get("evidence_receipt")

    try:
        signal = RewardSignal(
            source=source,
            valence=max(-1.0, min(1.0, valence)),
            confidence=max(0.0, min(1.0, confidence)),
            task_context=task_context,
            evidence_receipt=evidence_receipt
        )
        new_state = get_kernel().process_reward(signal)
        kernel = get_kernel()
        return {
            "status": "reward_processed",
            "soul_version": new_state.soul_version,
            "updated_traits": new_state.traits,
            "neuromodulators": {
                "dopamine": kernel.bio_engine.dopamine,
                "cortisol": kernel.bio_engine.cortisol,
                "serotonin": kernel.bio_engine.serotonin
            }
        }
    except Exception as exc:
        return {"status": "rejected", "error": str(exc)}


def _tool_soul_rollback(args: dict) -> dict:
    target_ver = args.get("target_version")
    reason = args.get("reason", "Operator manual rollback")
    if not target_ver:
        return {"error": "target_version parameter is required"}
    try:
        new_state = get_kernel().rollback_to_version(int(target_ver), operator_reason=reason)
        return {
            "status": "rolled_back",
            "soul_version": new_state.soul_version,
            "restored_traits": new_state.traits,
            "state_hash": new_state.state_hash
        }
    except Exception as exc:
        return {"status": "failed", "error": str(exc)}


def _tool_soul_heal(args: dict) -> dict:
    level = int(args.get("level", 1))
    reason = args.get("reason", "Automated health repair")
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


# ==============================================================================
# TOOL REGISTRY
# ==============================================================================

TOOLS = [
    {
        "name": "soul_remember",
        "description": "Store interaction into Quarantine Memory with credential screening & entity key supersession.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content":     {"type": "string", "description": "Memory text or interaction content"},
                "source_kind": {"type": "string", "enum": ["human", "agent", "environment", "internal"], "default": "human"},
                "provenance":  {"type": "string", "enum": ["observed", "reported", "inferred", "imagined", "verified"], "default": "observed"},
                "entity_key":  {"type": "string", "description": "Optional entity key for single-current-value facts"}
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
        "description": "Search and retrieve active memories via Reciprocal Rank Fusion (RRF) Hybrid, Dense Vector, or BM25 search.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query":       {"type": "string", "description": "Search query"},
                "limit":       {"type": "integer", "default": 5},
                "search_mode": {"type": "string", "enum": ["rrf_hybrid", "dense", "bm25"], "default": "rrf_hybrid"}
            }
        },
        "_handler": _tool_soul_recall
    },
    {
        "name": "soul_digest",
        "description": "Fetch a single compact summary block of core active facts and trait values.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 5}
            }
        },
        "_handler": _tool_soul_digest
    },
    {
        "name": "soul_verify",
        "description": "Evidence Verifier: Evaluate memory entailment/contradiction with Epistemic Authority Hierarchy.",
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
        "description": "Reflection Engine: Analyze unresolved tensions and generate candidate interpretations.",
        "inputSchema": {"type": "object", "properties": {}},
        "_handler": _tool_soul_reflect
    },
    {
        "name": "soul_dream",
        "description": "Dream Sandbox: Run a sandboxed scenario simulation tagged strictly with 'no_external_action'.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "scenario_prompt": {"type": "string", "description": "Hypothetical scenario to simulate"}
            },
            "required": ["scenario_prompt"]
        },
        "_handler": _tool_soul_dream
    },
    {
        "name": "soul_reward",
        "description": "Bio-Inspired Homeostatic Reward: Modulate dopamine/cortisol dynamics and dynamic trait adjustments.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source":           {"type": "string", "enum": ["external_test", "external_human", "internal_reflection", "internal_dream"]},
                "valence":          {"type": "number", "description": "Reward valence between -1.0 (failure/criticism) and 1.0 (success/praise)"},
                "confidence":       {"type": "number", "description": "Confidence of signal [0.0 to 1.0]"},
                "task_context":     {"type": "string", "description": "Brief context of what task succeeded or failed"},
                "evidence_receipt": {"type": "string", "description": "Optional benchmark run ID or test log receipt"}
            },
            "required": ["source", "valence", "task_context"]
        },
        "_handler": _tool_soul_reward
    },
    {
        "name": "soul_update_trait",
        "description": "Propose an update to a bounded control trait parameter (e.g. sycophancy, audacity, epistemic_humility).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "trait":              {"type": "string"},
                "new_value":          {"type": "number"},
                "evidence_refs":      {"type": "array", "items": {"type": "string"}},
                "is_human_approved":  {"type": "boolean"}
            },
            "required": ["trait", "new_value"]
        },
        "_handler": _tool_soul_update_trait
    },
    {
        "name": "soul_rollback",
        "description": "Rollback Soul identity state to a verified prior version without deleting audit trail history.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target_version": {"type": "integer"},
                "reason":         {"type": "string"}
            },
            "required": ["target_version"]
        },
        "_handler": _tool_soul_rollback
    },
    {
        "name": "soul_heal",
        "description": "Self-Healing Engine: Execute 3-tier repair escalation (Level 1: Recalibrate, Level 2: Soft Rollback, Level 3: Quarantine Freeze).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "level":  {"type": "integer", "enum": [1, 2, 3]},
                "reason": {"type": "string"}
            },
            "required": ["level"]
        },
        "_handler": _tool_soul_heal
    },
    {
        "name": "soul_daemon_status",
        "description": "Inspect status, execution counters, and intervals of the background SoulDaemon supervisor.",
        "inputSchema": {"type": "object", "properties": {}},
        "_handler": _tool_soul_daemon_status
    }
]


# ==============================================================================
# JSON-RPC / MCP STDIO SERVER HANDLER
# ==============================================================================

SERVER_INFO = {"name": "soul-mcp-server", "version": "1.0.0"}
CAPABILITIES = {"tools": {"listChanged": False}}


def _handle_jsonrpc(req: dict) -> Optional[dict]:
    method = req.get("method", "")
    params = req.get("params") or {}
    req_id = req.get("id")

    def ok(res):
        return {"jsonrpc": "2.0", "id": req_id, "result": res}

    def err(code, msg):
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": msg}}

    if req_id is None and method.startswith("notifications/"):
        return None

    if method == "initialize":
        return ok({"protocolVersion": "2024-11-05", "capabilities": CAPABILITIES, "serverInfo": SERVER_INFO})

    if method == "notifications/initialized":
        return None

    if method == "ping":
        return ok({})

    if method == "tools/list":
        tools_out = [{"name": t["name"], "description": t["description"], "inputSchema": t["inputSchema"]} for t in TOOLS]
        return ok({"tools": tools_out})

    if method == "tools/call":
        name = params.get("name", "")
        arguments = params.get("arguments") or {}
        handler = next((t["_handler"] for t in TOOLS if t["name"] == name), None)
        if handler is None:
            return err(-32601, f"Unknown tool: {name}")
        try:
            res = handler(arguments)
            return ok({"content": [{"type": "text", "text": json.dumps(res, indent=2)}]})
        except Exception as exc:
            log.exception("Tool %s raised exception", name)
            return err(-32603, str(exc))

    return err(-32601, f"Method not found: {method}")


def main():
    log.info("Starting Soul MCP Server v1.0.0 on stdio...")
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

    if _kernel:
        _kernel.stop_daemon()


if __name__ == "__main__":
    main()
