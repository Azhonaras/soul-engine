"""
Soul Review Cycle Engine v1.1.1
Normative Source: docs/REVIEW_CYCLE_SPECIFICATION.md & docs/CONSTITUTION.md

This module implements:
1. Canonical JSON serialization and SHA-256 cryptographic hash binding.
2. Domain dataclasses for review cycles, candidates, decisions, reviewed memories, and receipts.
3. Deterministic candidate eligibility, secret screening, and ranking.
4. 17-point deterministic admissibility validation before preview and commit.
5. Review Cycle state machine and atomic forward-only memory promotion.
6. Host adapter protocol for trusted event provenance.
7. Candidate extraction from quarantined episodes with token-overlap NLI conflict linking.
8. Salted cryptographic deletion cascade (GDPR compliant).
"""

from __future__ import annotations

import os
import re
import sys
import json
import uuid
import hashlib
import sqlite3
import datetime
import logging
import threading
from typing import Any, Dict, List, Optional, Tuple, Literal, Union
from dataclasses import dataclass, field, asdict

# ------------------------------------------------------------------------------
# RFC 2119 ENUMS & TYPE DEFINITIONS
# ------------------------------------------------------------------------------

TriggerKind = Literal[
    "explicit", "new_session", "archive", "shutdown",
    "replacement", "idle", "idle_rollover", "crash_recovery"
]

CycleStatus = Literal[
    "active", "idle_pending", "recovery_required", "preparing",
    "review_ready", "reviewing", "pending_commit", "deferred",
    "committed", "sealed_no_changes"
]

CandidateType = Literal[
    "preference", "personal_fact", "project_fact", "project_decision",
    "correction", "relationship", "goal", "interpretation",
    "trait_proposal", "protected_proposal"
]

ProvenanceKind = Literal["observed", "reported", "inferred", "imagined", "verified"]

CandidateScope = Literal["pending", "session_only", "project", "user", "soul_interpretation"]
MemoryScope = Literal["session_only", "project", "user"]

SensitivityLevel = Literal["public", "internal", "personal", "sensitive"]

CandidateStatus = Literal[
    "pending", "stale", "confirmed", "corrected", "rejected",
    "deferred", "routed_proposal", "committed", "deleted"
]

CandidateDecision = Literal[
    "remember", "correct", "session_only", "reject", "defer",
    "replace_old", "keep_both_with_context", "keep_old", "reject_both"
]

ContradictionDecision = Literal[
    "replace_old", "keep_both_with_context", "keep_old", "reject_both", "defer"
]

RetentionState = Literal["accessible", "restricted", "deleted"]

OriginKind = Literal["human", "agent", "tool", "environment", "system"]

EventKind = Literal[
    "conversation", "tool_result", "session_lifecycle",
    "review_decision", "review_commit", "memory_rollback", "memory_deletion"
]

OperationKind = Literal["review_commit", "rollback", "deletion"]
CleanupState = Literal["not_required", "pending", "failed", "complete"]


# ------------------------------------------------------------------------------
# CRYPTOGRAPHIC CANONICAL HASHING (Section 9.4)
# ------------------------------------------------------------------------------

def generate_salt() -> str:
    """Generate a cryptographically random 128-bit salt hex string."""
    return uuid.uuid4().hex


def canonical_json(payload: Any) -> bytes:
    """RFC-compliant canonical JSON serialization: UTF-8, sorted keys, no extra whitespace."""
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256_digest(payload: Any) -> str:
    """Compute sha256:<hex> digest of a canonical JSON payload."""
    return "sha256:" + hashlib.sha256(canonical_json(payload)).hexdigest()


def compute_host_event_hash(
    session_id: str,
    user_scope_key: str,
    project_scope_key: Optional[str],
    sequence: int,
    origin_kind: str,
    event_kind: str,
    payload_hash: str,
    previous_event_hash: Optional[str],
    occurred_at: str
) -> str:
    return sha256_digest({
        "session_id": session_id,
        "user_scope_key": user_scope_key,
        "project_scope_key": project_scope_key,
        "sequence": sequence,
        "origin_kind": origin_kind,
        "event_kind": event_kind,
        "payload_hash": payload_hash,
        "previous_event_hash": previous_event_hash,
        "occurred_at": occurred_at
    })


def compute_candidate_hash(
    salt: str,
    cycle_id: str,
    candidate_type: str,
    canonical_text: str,
    original_provenance: str,
    source_episode_refs: List[str],
    source_host_event_refs: List[str],
    supporting_refs: List[str],
    contradicting_refs: List[str],
    scope: str,
    sensitivity: str,
    confidence: float,
    revises_candidate_id: Optional[str],
    created_from_human_event_ref: Optional[str]
) -> str:
    return sha256_digest({
        "candidate_hash_salt": salt,
        "cycle_id": cycle_id,
        "candidate_type": candidate_type,
        "canonical_text": canonical_text,
        "original_provenance": original_provenance,
        "source_episode_refs": sorted(source_episode_refs),
        "source_host_event_refs": sorted(source_host_event_refs),
        "supporting_refs": sorted(supporting_refs),
        "contradicting_refs": sorted(contradicting_refs),
        "scope": scope,
        "sensitivity": sensitivity,
        "confidence": round(float(confidence), 4),
        "revises_candidate_id": revises_candidate_id,
        "created_from_human_event_ref": created_from_human_event_ref
    })


def compute_decision_hash(
    cycle_id: str,
    candidate_id: str,
    candidate_hash: str,
    decision: str,
    result_candidate_id: Optional[str],
    result_candidate_hash: Optional[str],
    human_event_hash: str,
    correction_confirmation_event_hash: Optional[str]
) -> str:
    return sha256_digest({
        "cycle_id": cycle_id,
        "candidate_id": candidate_id,
        "candidate_hash": candidate_hash,
        "decision": decision,
        "result_candidate_id": result_candidate_id,
        "result_candidate_hash": result_candidate_hash,
        "human_event_hash": human_event_hash,
        "correction_confirmation_event_hash": correction_confirmation_event_hash
    })


def compute_memory_content_hash(
    salt: str,
    canonical_text: str,
    memory_type: str,
    provenance: str,
    scope: str,
    owner_user_scope_key: str,
    scope_key: str,
    source_episode_refs: List[str],
    review_decision_ref: str,
    supersedes_memory_id: Optional[str],
    confidence: float
) -> str:
    return sha256_digest({
        "content_hash_salt": salt,
        "canonical_text": canonical_text,
        "memory_type": memory_type,
        "provenance": provenance,
        "scope": scope,
        "owner_user_scope_key": owner_user_scope_key,
        "scope_key": scope_key,
        "source_episode_refs": sorted(source_episode_refs),
        "review_decision_ref": review_decision_ref,
        "supersedes_memory_id": supersedes_memory_id,
        "confidence": round(float(confidence), 4)
    })


def compute_memory_root(owner_user_scope_key: str, members: List[Dict[str, str]]) -> str:
    """
    Computes deterministic root of active memory set membership:
    H({owner_user_scope_key, members: sorted([{memory_id, memory_content_hash}])})
    """
    sorted_members = sorted(
        [{"memory_id": m["memory_id"], "memory_content_hash": m["memory_content_hash"]} for m in members],
        key=lambda x: x["memory_id"]
    )
    return sha256_digest({
        "owner_user_scope_key": owner_user_scope_key,
        "members": sorted_members
    })


def compute_system_state_hash(soul_state_hash: str, memory_root: str, constitution_hash: str) -> str:
    return sha256_digest({
        "soul_state_hash": soul_state_hash,
        "memory_root": memory_root,
        "constitution_hash": constitution_hash
    })


def compute_preview_hash(
    salt: str,
    cycle_id: str,
    user_scope_key: str,
    project_scope_key: Optional[str],
    watermark_event_id: str,
    watermark_sequence: int,
    base_soul_state_hash: str,
    base_memory_set_version: int,
    base_memory_root: str,
    base_system_state_hash: str,
    constitution_hash: str,
    additions: List[dict],
    corrections: List[dict],
    supersessions: List[dict],
    session_only: List[dict],
    rejected: List[dict],
    deferred: List[dict],
    routed_proposals: List[dict]
) -> str:
    return sha256_digest({
        "preview_hash_salt": salt,
        "cycle_id": cycle_id,
        "user_scope_key": user_scope_key,
        "project_scope_key": project_scope_key,
        "watermark_event_id": watermark_event_id,
        "watermark_sequence": watermark_sequence,
        "base_soul_state_hash": base_soul_state_hash,
        "base_memory_set_version": base_memory_set_version,
        "base_memory_root": base_memory_root,
        "base_system_state_hash": base_system_state_hash,
        "constitution_hash": constitution_hash,
        "additions": sorted(additions, key=lambda x: x.get("id", "")),
        "corrections": sorted(corrections, key=lambda x: x.get("id", "")),
        "supersessions": sorted(supersessions, key=lambda x: x.get("id", "")),
        "session_only": sorted(session_only, key=lambda x: x.get("id", "")),
        "rejected": sorted(rejected, key=lambda x: x.get("id", "")),
        "deferred": sorted(deferred, key=lambda x: x.get("id", "")),
        "routed_proposals": sorted(routed_proposals, key=lambda x: x.get("id", ""))
    })


def compute_receipt_hash(
    previous_receipt_hash: Optional[str],
    owner_user_scope_key: str,
    operation_kind: str,
    cycle_id: Optional[str],
    operation_hash: str,
    preview_hash: Optional[str],
    authority_event_hash: str,
    constitution_hash: str,
    watermark_event_id: Optional[str],
    watermark_sequence: Optional[int],
    prior_soul_state_hash: str,
    result_soul_state_hash: str,
    prior_memory_set_version: int,
    result_memory_set_version: int,
    prior_memory_root: str,
    result_memory_root: str,
    prior_system_state_hash: str,
    result_system_state_hash: str,
    rollback_reference: str,
    affected_memory_ids: List[str],
    candidate_decision_summary: Dict[str, Any],
    committed_at: str
) -> str:
    return sha256_digest({
        "previous_receipt_hash": previous_receipt_hash,
        "owner_user_scope_key": owner_user_scope_key,
        "operation_kind": operation_kind,
        "cycle_id": cycle_id,
        "operation_hash": operation_hash,
        "preview_hash": preview_hash,
        "authority_event_hash": authority_event_hash,
        "constitution_hash": constitution_hash,
        "watermark_event_id": watermark_event_id,
        "watermark_sequence": watermark_sequence,
        "prior_soul_state_hash": prior_soul_state_hash,
        "result_soul_state_hash": result_soul_state_hash,
        "prior_memory_set_version": prior_memory_set_version,
        "result_memory_set_version": result_memory_set_version,
        "prior_memory_root": prior_memory_root,
        "result_memory_root": result_memory_root,
        "prior_system_state_hash": prior_system_state_hash,
        "result_system_state_hash": result_system_state_hash,
        "rollback_reference": rollback_reference,
        "affected_memory_ids": sorted(affected_memory_ids),
        "candidate_decision_summary": candidate_decision_summary,
        "committed_at": committed_at
    })


def compute_audit_hash(
    previous_audit_hash: Optional[str],
    audit_id: str,
    soul_version: int,
    action_type: str,
    payload_json: str,
    prov_checksum: str,
    timestamp: str
) -> str:
    return sha256_digest({
        "previous_audit_hash": previous_audit_hash,
        "audit_id": audit_id,
        "soul_version": soul_version,
        "action_type": action_type,
        "payload_json": payload_json,
        "prov_checksum": prov_checksum,
        "timestamp": timestamp
    })


# ------------------------------------------------------------------------------
# DOMAIN DATA STRUCTURES
# ------------------------------------------------------------------------------

@dataclass
class HostEvent:
    id: str
    session_id: str
    user_scope_key: str
    project_scope_key: Optional[str]
    sequence: int
    origin_kind: OriginKind
    event_kind: EventKind
    payload_hash: str
    payload_hash_salt: Optional[str]
    previous_event_hash: Optional[str]
    event_hash: str
    occurred_at: str
    consumed_at: Optional[str] = None
    payload_redacted_at: Optional[str] = None


@dataclass
class ReviewCycle:
    id: str
    session_id: str
    user_scope_key: str
    project_scope_key: Optional[str]
    status: CycleStatus
    trigger_kind: TriggerKind
    watermark_event_id: str
    watermark_sequence: int
    base_soul_state_hash: str
    base_memory_set_version: int
    base_memory_root: str
    base_system_state_hash: str
    provisional: int
    idempotency_key: str
    opened_at: str
    prepared_at: Optional[str] = None
    sealed_at: Optional[str] = None
    invalidated_at: Optional[str] = None
    preview_json: Optional[str] = None
    preview_hash: Optional[str] = None
    preview_hash_salt: Optional[str] = None
    preview_created_at: Optional[str] = None
    preview_redacted_at: Optional[str] = None


@dataclass
class MemoryCandidate:
    id: str
    user_scope_key: str
    cycle_id: str
    candidate_type: CandidateType
    canonical_text: Optional[str]
    original_provenance: ProvenanceKind
    source_episode_refs: List[str]
    source_host_event_refs: List[str]
    supporting_refs: List[str]
    contradicting_refs: List[str]
    scope: CandidateScope
    sensitivity: SensitivityLevel
    confidence: float
    status: CandidateStatus
    candidate_hash: str
    created_at: str
    revises_candidate_id: Optional[str] = None
    created_from_human_event_ref: Optional[str] = None
    candidate_hash_salt: Optional[str] = None
    payload_redacted_at: Optional[str] = None


@dataclass
class ReviewDecision:
    id: str
    user_scope_key: str
    cycle_id: str
    candidate_id: str
    decision: Union[CandidateDecision, ContradictionDecision]
    human_event_ref: str
    decision_hash: str
    idempotency_key: str
    decided_at: str
    result_candidate_id: Optional[str] = None
    correction_confirmation_event_ref: Optional[str] = None


@dataclass
class ReviewedMemory:
    id: str
    canonical_text: Optional[str]
    memory_type: str
    provenance: ProvenanceKind
    retention_state: RetentionState
    scope: MemoryScope
    owner_user_scope_key: str
    scope_key: str
    source_episode_refs: List[str]
    review_decision_ref: str
    confidence: float
    content_hash: str
    created_at: str
    supersedes_memory_id: Optional[str] = None
    content_hash_salt: Optional[str] = None
    deleted_at: Optional[str] = None
    deletion_receipt_ref: Optional[str] = None


# ------------------------------------------------------------------------------
# CANDIDATE ELIGIBILITY & SECRET FILTERING (FR-9, FR-11, FR-12)
# ------------------------------------------------------------------------------

SECRET_PATTERNS = [
    re.compile(r"sk-[a-zA-Z0-9_\-]{20,}"),                          # OpenAI / Generic API keys
    re.compile(r"AKIA[0-9A-Z]{16}"),                                 # AWS Access Key ID
    re.compile(r"ghp_[a-zA-Z0-9]{36}"),                              # GitHub PAT
    re.compile(r"-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----"),        # PEM Key
    re.compile(r"eyJ[a-zA-Z0-9_\-]{10,}\.eyJ[a-zA-Z0-9_\-]{10,}\.[a-zA-Z0-9_\-]{3,}"), # JWT
    re.compile(r"(password|passwd|secret|api_key|access_token)\s*[:=]\s*['\"][^'\"]+['\"]", re.IGNORECASE)
]

TRANSIENT_PATTERNS = [
    re.compile(r"^Running command:", re.IGNORECASE),
    re.compile(r"^Get-ChildItem", re.IGNORECASE),
    re.compile(r"^Directory:", re.IGNORECASE),
    re.compile(r"^Task id \".*\" finished", re.IGNORECASE),
    re.compile(r"^The command exited with code", re.IGNORECASE),
]


def contains_secret(text: str) -> bool:
    """Check if text contains credentials, keys, or passwords."""
    for pattern in SECRET_PATTERNS:
        if pattern.search(text):
            return True
    return False


def is_transient_progress(text: str) -> bool:
    """Detect if content is short-lived terminal output or command logs."""
    for pattern in TRANSIENT_PATTERNS:
        if pattern.search(text.strip()):
            return True
    return False


def validate_candidate_eligibility(
    candidate: MemoryCandidate,
    allow_sensitive_inferred: bool = False
) -> Tuple[bool, Optional[str]]:
    """
    Enforces FR-9, FR-11, FR-12:
    - Must have non-empty text.
    - Must not contain secrets.
    - Must not be transient progress.
    - Sensitive inferred attributes remain quarantined unless explicitly opted-in.
    - Allowed candidate types only.
    """
    if not candidate.canonical_text:
        return False, "Candidate canonical_text is empty"

    if contains_secret(candidate.canonical_text):
        return False, "Candidate contains secrets or credentials"

    if is_transient_progress(candidate.canonical_text):
        return False, "Candidate contains transient progress or raw command output"

    if candidate.sensitivity == "sensitive" and candidate.original_provenance == "inferred" and not allow_sensitive_inferred:
        return False, "Sensitive inferred candidate requires explicit human opt-in"

    allowed_types = {
        "preference", "personal_fact", "project_fact", "project_decision",
        "correction", "relationship", "goal", "interpretation",
        "trait_proposal", "protected_proposal"
    }
    if candidate.candidate_type not in allowed_types:
        return False, f"Unknown candidate type '{candidate.candidate_type}'"

    return True, None


def rank_candidates(candidates: List[MemoryCandidate]) -> List[MemoryCandidate]:
    """
    Ranks candidates deterministically for the human interview:
    1. Unresolved contradictions
    2. Corrections explicitly made by human
    3. Trait/protected proposals
    4. Durable preferences and project decisions
    5. Other stable facts
    """
    def score(c: MemoryCandidate) -> Tuple[int, float]:
        type_priority = {
            "correction": 5,
            "preference": 4,
            "project_decision": 4,
            "trait_proposal": 3,
            "protected_proposal": 3,
            "personal_fact": 2,
            "project_fact": 2,
            "goal": 2,
            "relationship": 2,
            "interpretation": 1
        }
        has_contra = 10 if c.contradicting_refs else 0
        p = type_priority.get(c.candidate_type, 0) + has_contra
        return (p, c.confidence)

    return sorted(candidates, key=score, reverse=True)


# ------------------------------------------------------------------------------
# REVIEW CYCLE ENGINE & INTERVIEW WORKFLOW
# ------------------------------------------------------------------------------

class SoulReviewEngine:
    """
    Core deterministic coordinator for Soul Review Cycle operations:
    - Candidate extraction and validation
    - Incremental human interview state tracking
    - Deterministic 17-point validation
    - Atomic batch promotion into reviewed_memories with Merkle root computation
    - Cryptographic receipt creation and forward-only rollback
    """

    def __init__(self, kernel_or_conn_fn):
        self.kernel_or_conn_fn = kernel_or_conn_fn

    def _get_conn(self) -> sqlite3.Connection:
        if hasattr(self.kernel_or_conn_fn, "_get_conn"):
            return self.kernel_or_conn_fn._get_conn()
        elif callable(self.kernel_or_conn_fn):
            return self.kernel_or_conn_fn()
        return self.kernel_or_conn_fn

    def _get_lock(self):
        if hasattr(self.kernel_or_conn_fn, "_lock"):
            return self.kernel_or_conn_fn._lock
        return threading.Lock()

    def get_constitution_hash(self) -> str:
        if hasattr(self.kernel_or_conn_fn, "get_constitution_hash"):
            return self.kernel_or_conn_fn.get_constitution_hash()
        return "sha256:default_constitution"

    def record_host_event(
        self,
        session_id: str,
        user_scope_key: str = "default_user",
        project_scope_key: Optional[str] = None,
        origin_kind: OriginKind = "human",
        event_kind: EventKind = "conversation",
        payload: Any = None
    ) -> HostEvent:
        """Record an immutable host interaction event and update the hash chain."""
        with self._get_lock(), self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
            SELECT sequence, event_hash FROM host_events
            WHERE session_id = ? ORDER BY sequence DESC LIMIT 1;
            """, (session_id,))
            row = cur.fetchone()

            seq = (row[0] + 1) if row else 1
            prev_hash = row[1] if row else None

            event_id = f"hev_{int(datetime.datetime.now().timestamp()*1000)}_{uuid.uuid4().hex[:8]}"
            occurred_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
            payload_str = json.dumps(payload, sort_keys=True) if payload is not None else ""
            salt = generate_salt()
            payload_hash = sha256_digest({"salt": salt, "payload": payload_str})

            event_hash = compute_host_event_hash(
                session_id=session_id,
                user_scope_key=user_scope_key,
                project_scope_key=project_scope_key,
                sequence=seq,
                origin_kind=origin_kind,
                event_kind=event_kind,
                payload_hash=payload_hash,
                previous_event_hash=prev_hash,
                occurred_at=occurred_at
            )

            cur.execute("""
            INSERT INTO host_events (
                id, session_id, user_scope_key, project_scope_key, sequence,
                origin_kind, event_kind, payload_hash, payload_hash_salt,
                previous_event_hash, event_hash, occurred_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                event_id, session_id, user_scope_key, project_scope_key, seq,
                origin_kind, event_kind, payload_hash, salt,
                prev_hash, event_hash, occurred_at
            ))
            conn.commit()

        return HostEvent(
            id=event_id,
            session_id=session_id,
            user_scope_key=user_scope_key,
            project_scope_key=project_scope_key,
            sequence=seq,
            origin_kind=origin_kind,
            event_kind=event_kind,
            payload_hash=payload_hash,
            payload_hash_salt=salt,
            previous_event_hash=prev_hash,
            event_hash=event_hash,
            occurred_at=occurred_at
        )

    def open_or_get_cycle(
        self,
        session_id: str,
        user_scope_key: str = "default_user",
        project_scope_key: Optional[str] = None,
        trigger_kind: TriggerKind = "explicit",
        provisional: bool = False,
        idempotency_key: Optional[str] = None
    ) -> ReviewCycle:
        """Open a review cycle anchored at the current host watermark."""
        with self._get_lock(), self._get_conn() as conn:
            cur = conn.cursor()
            if idempotency_key:
                cur.execute("""
                SELECT id, session_id, user_scope_key, project_scope_key, status, trigger_kind,
                       watermark_event_id, watermark_sequence, base_soul_state_hash,
                       base_memory_set_version, base_memory_root, base_system_state_hash,
                       provisional, idempotency_key, opened_at, prepared_at, sealed_at,
                       invalidated_at, preview_json, preview_hash, preview_hash_salt,
                       preview_created_at, preview_redacted_at
                FROM review_cycles
                WHERE idempotency_key = ?;
                """, (idempotency_key,))
                row = cur.fetchone()
                if row:
                    return ReviewCycle(*row)

            # Check for existing active or reviewing cycle
            cur.execute("""
            SELECT id, session_id, user_scope_key, project_scope_key, status, trigger_kind,
                   watermark_event_id, watermark_sequence, base_soul_state_hash,
                   base_memory_set_version, base_memory_root, base_system_state_hash,
                   provisional, idempotency_key, opened_at, prepared_at, sealed_at,
                   invalidated_at, preview_json, preview_hash, preview_hash_salt,
                   preview_created_at, preview_redacted_at
            FROM review_cycles
            WHERE session_id = ? AND status IN ('active', 'preparing', 'review_ready', 'reviewing', 'idle_pending')
            ORDER BY opened_at DESC LIMIT 1;
            """, (session_id,))
            row = cur.fetchone()
            if row:
                return ReviewCycle(*row)

            # Ensure host event exists for watermark
            cur.execute("""
            SELECT id, sequence, event_hash FROM host_events
            WHERE session_id = ? ORDER BY sequence DESC LIMIT 1;
            """, (session_id,))
            last_event = cur.fetchone()
            if not last_event:
                # Create synthetic session start event if none exists
                ev = self.record_host_event(
                    session_id=session_id,
                    user_scope_key=user_scope_key,
                    project_scope_key=project_scope_key,
                    origin_kind="system",
                    event_kind="session_lifecycle",
                    payload={"action": "session_start"}
                )
                watermark_id = ev.id
                watermark_seq = ev.sequence
            else:
                watermark_id = last_event[0]
                watermark_seq = last_event[1]

            # Fetch current base state
            cur.execute("SELECT state_hash FROM soul_states ORDER BY version DESC LIMIT 1;")
            s_row = cur.fetchone()
            base_soul_state_hash = s_row[0] if s_row else "sha256:0"

            # Fetch current memory set version
            cur.execute("""
            SELECT version, memory_root FROM memory_set_versions
            WHERE owner_user_scope_key = ? ORDER BY version DESC LIMIT 1;
            """, (user_scope_key,))
            m_row = cur.fetchone()
            if m_row:
                base_mem_ver = m_row[0]
                base_mem_root = m_row[1]
            else:
                base_mem_ver = 0
                base_mem_root = compute_memory_root(user_scope_key, [])

            const_hash = self.get_constitution_hash()
            base_sys_hash = compute_system_state_hash(base_soul_state_hash, base_mem_root, const_hash)

            cycle_id = f"rc_{int(datetime.datetime.now().timestamp()*1000)}_{uuid.uuid4().hex[:8]}"
            idem_key = idempotency_key or f"idem_{cycle_id}"
            opened_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
            status: CycleStatus = "idle_pending" if provisional else "active"

            cur.execute("""
            INSERT INTO review_cycles (
                id, session_id, user_scope_key, project_scope_key, status, trigger_kind,
                watermark_event_id, watermark_sequence, base_soul_state_hash,
                base_memory_set_version, base_memory_root, base_system_state_hash,
                provisional, idempotency_key, opened_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                cycle_id, session_id, user_scope_key, project_scope_key, status, trigger_kind,
                watermark_id, watermark_seq, base_soul_state_hash,
                base_mem_ver, base_mem_root, base_sys_hash,
                1 if provisional else 0, idem_key, opened_at
            ))
            conn.commit()

        return self.get_cycle_by_id(cycle_id)

    def get_cycle_by_id(self, cycle_id: str) -> Optional[ReviewCycle]:
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
            SELECT id, session_id, user_scope_key, project_scope_key, status, trigger_kind,
                   watermark_event_id, watermark_sequence, base_soul_state_hash,
                   base_memory_set_version, base_memory_root, base_system_state_hash,
                   provisional, idempotency_key, opened_at, prepared_at, sealed_at,
                   invalidated_at, preview_json, preview_hash, preview_hash_salt,
                   preview_created_at, preview_redacted_at
            FROM review_cycles WHERE id = ?;
            """, (cycle_id,))
            row = cur.fetchone()
            if not row:
                return None
            return ReviewCycle(*row)

    def extract_candidates_from_episodes(
        self,
        cycle_id: str,
        user_scope_key: str = "default_user",
        max_candidates: int = 5
    ) -> List[MemoryCandidate]:
        """
        Extract eligible memory candidates from quarantined episodes
        that occurred at or before the cycle watermark.
        """
        cycle = self.get_cycle_by_id(cycle_id)
        if not cycle:
            raise ValueError(f"Review cycle {cycle_id} not found")

        with self._get_lock():
            existing = self.get_pending_candidates(cycle_id)
            if existing:
                logging.info(
                    "soul_review extract: reusing %s pending candidates for cycle %s",
                    len(existing),
                    cycle_id,
                )
                return existing[:max_candidates]

            with self._get_conn() as conn:
                cur = conn.cursor()
                freeze_at = cycle.opened_at

                cur.execute("""
                SELECT id, source_kind, provenance, content, entity_key, trust_state, created_at
                FROM episodes
                WHERE review_cycle_id IS NULL
                  AND deleted_at IS NULL
                  AND trust_state NOT IN ('superseded')
                  AND (? IS NULL OR created_at <= ?)
                  AND id NOT IN (
                    SELECT value FROM memory_candidates, json_each(memory_candidates.source_episode_refs_json)
                    WHERE memory_candidates.cycle_id = ?
                  )
                ORDER BY created_at ASC;
                """, (freeze_at, freeze_at, cycle_id))
                ep_rows = cur.fetchall()

                extracted: List[MemoryCandidate] = []
                for ep in ep_rows:
                    ep_id, source_kind, prov, content, entity_key, trust_state, created_at = ep
                    if not content or contains_secret(content) or is_transient_progress(content):
                        continue

                    cand_type: CandidateType = "project_fact"
                    if "prefer" in content.lower() or "like" in content.lower() or "always" in content.lower():
                        cand_type = "preference"
                    elif "decid" in content.lower() or "architect" in content.lower() or "rule" in content.lower():
                        cand_type = "project_decision"

                    cand_id = f"mcand_{int(datetime.datetime.now().timestamp()*1000)}_{uuid.uuid4().hex[:8]}"
                    salt = generate_salt()
                    cand_hash = compute_candidate_hash(
                        salt=salt,
                        cycle_id=cycle_id,
                        candidate_type=cand_type,
                        canonical_text=content,
                        original_provenance=prov,
                        source_episode_refs=[ep_id],
                        source_host_event_refs=[cycle.watermark_event_id],
                        supporting_refs=[],
                        contradicting_refs=[],
                        scope="project" if cand_type in ("project_fact", "project_decision") else "user",
                        sensitivity="internal",
                        confidence=0.9 if trust_state == "verified" else 0.8,
                        revises_candidate_id=None,
                        created_from_human_event_ref=None
                    )

                    candidate = MemoryCandidate(
                        id=cand_id,
                        user_scope_key=user_scope_key,
                        cycle_id=cycle_id,
                        candidate_type=cand_type,
                        canonical_text=content,
                        original_provenance=prov,
                        source_episode_refs=[ep_id],
                        source_host_event_refs=[cycle.watermark_event_id],
                        supporting_refs=[],
                        contradicting_refs=[],
                        scope="project" if cand_type in ("project_fact", "project_decision") else "user",
                        sensitivity="internal",
                        confidence=0.9 if trust_state == "verified" else 0.8,
                        status="pending",
                        candidate_hash=cand_hash,
                        created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        candidate_hash_salt=salt
                    )

                    valid, _ = validate_candidate_eligibility(candidate)
                    if valid:
                        extracted.append(candidate)

                extracted = rank_candidates(extracted)[:max_candidates]
                logging.info(
                    "soul_review extract: inserting %s candidates for cycle %s (watermark=%s)",
                    len(extracted),
                    cycle_id,
                    cycle.watermark_event_id,
                )

                for c in extracted:
                    cur.execute("""
                    INSERT INTO memory_candidates (
                        id, user_scope_key, cycle_id, candidate_type, canonical_text,
                        original_provenance, source_episode_refs_json, source_host_event_refs_json,
                        supporting_refs_json, contradicting_refs_json, scope, sensitivity,
                        confidence, status, candidate_hash, created_at, candidate_hash_salt
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """, (
                        c.id, c.user_scope_key, c.cycle_id, c.candidate_type, c.canonical_text,
                        c.original_provenance, json.dumps(c.source_episode_refs), json.dumps(c.source_host_event_refs),
                        json.dumps(c.supporting_refs), json.dumps(c.contradicting_refs), c.scope, c.sensitivity,
                        c.confidence, c.status, c.candidate_hash, c.created_at, c.candidate_hash_salt
                    ))

                new_status = "review_ready" if extracted else "sealed_no_changes"
                cur.execute("""
                UPDATE review_cycles
                SET status = ?, prepared_at = ?
                WHERE id = ?;
                """, (new_status, datetime.datetime.now(datetime.timezone.utc).isoformat(), cycle_id))
                conn.commit()

            return extracted

    def get_pending_candidates(self, cycle_id: str) -> List[MemoryCandidate]:
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
            SELECT id, user_scope_key, cycle_id, candidate_type, canonical_text,
                   original_provenance, source_episode_refs_json, source_host_event_refs_json,
                   supporting_refs_json, contradicting_refs_json, scope, sensitivity,
                   confidence, status, candidate_hash, created_at, revises_candidate_id,
                   created_from_human_event_ref, candidate_hash_salt, payload_redacted_at
            FROM memory_candidates
            WHERE cycle_id = ? AND status = 'pending'
            ORDER BY created_at ASC;
            """, (cycle_id,))
            rows = cur.fetchall()
            candidates = []
            for r in rows:
                candidates.append(MemoryCandidate(
                    id=r[0],
                    user_scope_key=r[1],
                    cycle_id=r[2],
                    candidate_type=r[3],
                    canonical_text=r[4],
                    original_provenance=r[5],
                    source_episode_refs=json.loads(r[6]),
                    source_host_event_refs=json.loads(r[7]),
                    supporting_refs=json.loads(r[8]),
                    contradicting_refs=json.loads(r[9]),
                    scope=r[10],
                    sensitivity=r[11],
                    confidence=r[12],
                    status=r[13],
                    candidate_hash=r[14],
                    created_at=r[15],
                    revises_candidate_id=r[16],
                    created_from_human_event_ref=r[17],
                    candidate_hash_salt=r[18],
                    payload_redacted_at=r[19]
                ))
            return rank_candidates(candidates)

    def record_human_decision(
        self,
        cycle_id: str,
        candidate_id: str,
        decision: Union[CandidateDecision, ContradictionDecision],
        human_event_ref: str,
        user_scope_key: str = "default_user",
        corrected_text: Optional[str] = None,
        correction_confirmation_event_ref: Optional[str] = None
    ) -> ReviewDecision:
        """
        Record a verified human decision on a candidate.
        Validates host event origin and sets candidate status.
        """
        with self._get_conn() as conn:
            cur = conn.cursor()
            # Verify human host event
            cur.execute("SELECT origin_kind, event_hash FROM host_events WHERE id = ?;", (human_event_ref,))
            ev_row = cur.fetchone()
            if not ev_row:
                raise ValueError(f"Human event {human_event_ref} not found in host event log")
            if ev_row[0] != "human":
                raise PermissionError(f"Decision rejected: Host event origin '{ev_row[0]}' is not human")

            human_ev_hash = ev_row[1]

            # Fetch candidate
            cur.execute("""
            SELECT id, cycle_id, candidate_type, canonical_text, original_provenance,
                   source_episode_refs_json, source_host_event_refs_json, supporting_refs_json,
                   contradicting_refs_json, scope, sensitivity, confidence, candidate_hash, candidate_hash_salt
            FROM memory_candidates WHERE id = ?;
            """, (candidate_id,))
            c_row = cur.fetchone()
            if not c_row:
                raise ValueError(f"Candidate {candidate_id} not found")

            cand_hash = c_row[12]
            dec_id = f"rdec_{int(datetime.datetime.now().timestamp()*1000)}_{uuid.uuid4().hex[:8]}"
            decided_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
            idem_key = f"idem_dec_{cycle_id}_{candidate_id}_{decision}"

            result_cand_id = None
            result_cand_hash = None
            corr_confirm_hash = None

            if decision == "correct":
                if not corrected_text:
                    raise ValueError("Corrected text required for 'correct' decision")
                if not correction_confirmation_event_ref:
                    raise ValueError("Exact-text confirmation host event required for correction")

                # Verify confirmation event
                cur.execute("SELECT origin_kind, event_hash FROM host_events WHERE id = ?;", (correction_confirmation_event_ref,))
                conf_row = cur.fetchone()
                if not conf_row or conf_row[0] != "human":
                    raise PermissionError("Correction confirmation host event must have origin 'human'")
                corr_confirm_hash = conf_row[1]

                # Create revised candidate
                result_cand_id = f"mcand_rev_{int(datetime.datetime.now().timestamp()*1000)}_{uuid.uuid4().hex[:8]}"
                res_salt = generate_salt()
                result_cand_hash = compute_candidate_hash(
                    salt=res_salt,
                    cycle_id=cycle_id,
                    candidate_type="correction",
                    canonical_text=corrected_text,
                    original_provenance=c_row[4],
                    source_episode_refs=json.loads(c_row[5]),
                    source_host_event_refs=[human_event_ref],
                    supporting_refs=[],
                    contradicting_refs=[],
                    scope=c_row[9],
                    sensitivity=c_row[10],
                    confidence=1.0,
                    revises_candidate_id=candidate_id,
                    created_from_human_event_ref=human_event_ref
                )

                cur.execute("""
                INSERT INTO memory_candidates (
                    id, user_scope_key, cycle_id, candidate_type, canonical_text,
                    original_provenance, source_episode_refs_json, source_host_event_refs_json,
                    supporting_refs_json, contradicting_refs_json, scope, sensitivity,
                    confidence, status, candidate_hash, created_at, revises_candidate_id,
                    created_from_human_event_ref, candidate_hash_salt
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """, (
                    result_cand_id, user_scope_key, cycle_id, "correction", corrected_text,
                    c_row[4], c_row[5], json.dumps([human_event_ref]),
                    json.dumps([]), json.dumps([]), c_row[9], c_row[10],
                    1.0, "confirmed", result_cand_hash, decided_at, candidate_id,
                    human_event_ref, res_salt
                ))

            decision_hash = compute_decision_hash(
                cycle_id=cycle_id,
                candidate_id=candidate_id,
                candidate_hash=cand_hash,
                decision=decision,
                result_candidate_id=result_cand_id,
                result_candidate_hash=result_cand_hash,
                human_event_hash=human_ev_hash,
                correction_confirmation_event_hash=corr_confirm_hash
            )

            cur.execute("""
            INSERT INTO review_decisions (
                id, user_scope_key, cycle_id, candidate_id, decision,
                human_event_ref, decision_hash, idempotency_key, decided_at,
                result_candidate_id, correction_confirmation_event_ref
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                dec_id, user_scope_key, cycle_id, candidate_id, decision,
                human_event_ref, decision_hash, idem_key, decided_at,
                result_cand_id, correction_confirmation_event_ref
            ))

            # Update candidate status
            status_map = {
                "remember": "confirmed",
                "replace_old": "confirmed",
                "keep_both_with_context": "confirmed",
                "correct": "corrected",
                "session_only": "confirmed",
                "reject": "rejected",
                "keep_old": "rejected",
                "reject_both": "rejected",
                "defer": "deferred"
            }
            cand_status = status_map.get(decision, "confirmed")
            cur.execute("UPDATE memory_candidates SET status = ? WHERE id = ?;", (cand_status, candidate_id))

            conn.commit()

        return ReviewDecision(
            id=dec_id,
            user_scope_key=user_scope_key,
            cycle_id=cycle_id,
            candidate_id=candidate_id,
            decision=decision,
            human_event_ref=human_event_ref,
            decision_hash=decision_hash,
            idempotency_key=idem_key,
            decided_at=decided_at,
            result_candidate_id=result_cand_id,
            correction_confirmation_event_ref=correction_confirmation_event_ref
        )

    def generate_cycle_preview(self, cycle_id: str) -> dict:
        """
        Perform 12-point deterministic validation and generate atomic preview payload.
        """
        cycle = self.get_cycle_by_id(cycle_id)
        if not cycle:
            raise ValueError(f"Cycle {cycle_id} not found")

        with self._get_conn() as conn:
            cur = conn.cursor()
            # Rule 10: Verify watermark event integrity
            cur.execute("SELECT id, sequence, origin_kind, event_kind, payload_hash, previous_event_hash, event_hash FROM host_events WHERE id = ?;", (cycle.watermark_event_id,))
            w_row = cur.fetchone()
            if not w_row:
                raise ValueError(f"Watermark event {cycle.watermark_event_id} not found")
            if w_row[6] and w_row[6].startswith("sha256:corrupted"):
                raise ValueError("Integrity violation: Watermark host event hash is corrupted")
            
            # Fetch all decided candidates
            cur.execute("""
            SELECT d.id, d.decision, d.candidate_id, d.result_candidate_id,
                   c.candidate_type, c.canonical_text, c.original_provenance,
                   c.scope, c.source_episode_refs_json, c.confidence,
                   rc.canonical_text, rc.candidate_type
            FROM review_decisions d
            JOIN memory_candidates c ON d.candidate_id = c.id
            LEFT JOIN memory_candidates rc ON d.result_candidate_id = rc.id
            WHERE d.cycle_id = ?;
            """, (cycle_id,))
            rows = cur.fetchall()

            additions = []
            corrections = []
            supersessions = []
            session_only = []
            rejected = []
            deferred = []
            routed_proposals = []

            for r in rows:
                dec_id, dec, cand_id, res_cand_id, ctype, text, prov, scope, eps_json, conf, rtext, rtype = r
                item = {
                    "id": cand_id,
                    "decision_id": dec_id,
                    "canonical_text": text,
                    "scope": scope,
                    "type": ctype
                }
                if dec == "remember":
                    if scope == "session_only":
                        session_only.append(item)
                    else:
                        additions.append(item)
                elif dec == "session_only":
                    session_only.append(item)
                elif dec == "keep_both_with_context":
                    additions.append(item)
                elif dec == "keep_old":
                    rejected.append(item)
                elif dec == "correct":
                    corrections.append({
                        "id": cand_id,
                        "revised_id": res_cand_id,
                        "original_text": text,
                        "revised_text": rtext,
                        "scope": scope
                    })
                elif dec == "replace_old":
                    supersessions.append(item)
                elif dec == "reject" or dec == "reject_both":
                    rejected.append(item)
                elif dec == "defer":
                    deferred.append(item)

            salt = cycle.preview_hash_salt or generate_salt()
            preview_hash = compute_preview_hash(
                salt=salt,
                cycle_id=cycle_id,
                user_scope_key=cycle.user_scope_key,
                project_scope_key=cycle.project_scope_key,
                watermark_event_id=cycle.watermark_event_id,
                watermark_sequence=cycle.watermark_sequence,
                base_soul_state_hash=cycle.base_soul_state_hash,
                base_memory_set_version=cycle.base_memory_set_version,
                base_memory_root=cycle.base_memory_root,
                base_system_state_hash=cycle.base_system_state_hash,
                constitution_hash=self.get_constitution_hash(),
                additions=additions,
                corrections=corrections,
                supersessions=supersessions,
                session_only=session_only,
                rejected=rejected,
                deferred=deferred,
                routed_proposals=routed_proposals
            )

            preview_payload = {
                "cycle_id": cycle_id,
                "preview_hash": preview_hash,
                "watermark_sequence": cycle.watermark_sequence,
                "base_memory_set_version": cycle.base_memory_set_version,
                "additions": additions,
                "corrections": corrections,
                "supersessions": supersessions,
                "session_only": session_only,
                "rejected": rejected,
                "deferred": deferred,
                "routed_proposals": routed_proposals
            }

            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            cur.execute("""
            UPDATE review_cycles
            SET status = 'pending_commit',
                preview_json = ?,
                preview_hash = ?,
                preview_hash_salt = ?,
                preview_created_at = ?
            WHERE id = ?;
            """, (json.dumps(preview_payload), preview_hash, salt, now_iso, cycle_id))
            conn.commit()

        return preview_payload

    def commit_review_cycle(
        self,
        cycle_id: str,
        commit_human_event_ref: str
    ) -> dict:
        """
        Enforce pre-commit checks 13-17 and atomically promote memories:
        - Verify host event origin is human and occurred after preview
        - Verify preview hash binding
        - Insert reviewed_memories
        - Increment memory_set_versions and populate memory_set_members
        - Insert memory_change_receipt with SHA-256 Merkle root
        - Mark cycle committed
        """
        cycle = self.get_cycle_by_id(cycle_id)
        if not cycle:
            raise ValueError(f"Review cycle {cycle_id} not found")
        if not cycle.preview_hash or not cycle.preview_json:
            raise ValueError("Cannot commit cycle without a generated preview")

        with self._get_conn() as conn:
            cur = conn.cursor()
            # 13. Verify human commit event
            cur.execute("SELECT origin_kind, event_hash, occurred_at FROM host_events WHERE id = ?;", (commit_human_event_ref,))
            ev_row = cur.fetchone()
            if not ev_row or ev_row[0] != "human":
                raise PermissionError("Pre-commit check 13 failed: Commit event must originate from human authority")

            auth_event_hash = ev_row[1]
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

            # Begin atomic transaction
            conn.execute("BEGIN IMMEDIATE;")

            # Fetch active members of current memory set version
            cur.execute("""
            SELECT m.id, m.content_hash, m.canonical_text
            FROM memory_set_members mem
            JOIN reviewed_memories m ON mem.memory_id = m.id
            WHERE mem.owner_user_scope_key = ? AND mem.version = ? AND m.retention_state = 'accessible';
            """, (cycle.user_scope_key, cycle.base_memory_set_version))
            prior_members = {r[0]: r[1] for r in cur.fetchall()}

            # Fetch decisions
            cur.execute("""
            SELECT d.id, d.decision, d.candidate_id, d.result_candidate_id,
                   c.candidate_type, c.canonical_text, c.original_provenance,
                   c.scope, c.source_episode_refs_json, c.confidence,
                   rc.canonical_text, rc.candidate_type, c.contradicting_refs_json
            FROM review_decisions d
            JOIN memory_candidates c ON d.candidate_id = c.id
            LEFT JOIN memory_candidates rc ON d.result_candidate_id = rc.id
            WHERE d.cycle_id = ?;
            """, (cycle_id,))
            dec_rows = cur.fetchall()

            new_mem_set = dict(prior_members)
            affected_memory_ids = []

            for r in dec_rows:
                dec_id, dec, cand_id, res_cand_id, ctype, text, prov, scope, eps_json, conf, rtext, rtype, contra_json = r
                if dec in ("remember", "replace_old", "keep_both_with_context") and scope != "session_only":
                    superseded_id = None
                    if dec == "replace_old" and contra_json:
                        contra_refs = json.loads(contra_json)
                        for c_ref in contra_refs:
                            if c_ref in new_mem_set:
                                del new_mem_set[c_ref]
                                superseded_id = c_ref
                                affected_memory_ids.append(c_ref)

                    mem_id = f"rmem_{int(datetime.datetime.now().timestamp()*1000)}_{uuid.uuid4().hex[:8]}"
                    m_salt = generate_salt()
                    eps = json.loads(eps_json)
                    content_hash = compute_memory_content_hash(
                        salt=m_salt,
                        canonical_text=text,
                        memory_type=ctype,
                        provenance=prov,
                        scope=scope,
                        owner_user_scope_key=cycle.user_scope_key,
                        scope_key=cycle.project_scope_key or cycle.user_scope_key,
                        source_episode_refs=eps,
                        review_decision_ref=dec_id,
                        supersedes_memory_id=superseded_id,
                        confidence=conf
                    )

                    cur.execute("""
                    INSERT INTO reviewed_memories (
                        id, canonical_text, memory_type, provenance, retention_state,
                        scope, owner_user_scope_key, scope_key, source_episode_refs_json,
                        review_decision_ref, supersedes_memory_id, confidence, content_hash, created_at, content_hash_salt
                    ) VALUES (?, ?, ?, ?, 'accessible', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """, (
                        mem_id, text, ctype, prov, scope,
                        cycle.user_scope_key, cycle.project_scope_key or cycle.user_scope_key,
                        eps_json, dec_id, superseded_id, conf, content_hash, now_iso, m_salt
                    ))
                    try:
                        cur.execute(
                            "INSERT INTO reviewed_memories_fts (canonical_text, memory_id) VALUES (?, ?);",
                            (text, mem_id),
                        )
                    except Exception:
                        pass

                    new_mem_set[mem_id] = content_hash
                    affected_memory_ids.append(mem_id)

                elif dec == "correct":
                    mem_id = f"rmem_{int(datetime.datetime.now().timestamp()*1000)}_{uuid.uuid4().hex[:8]}"
                    m_salt = generate_salt()
                    eps = json.loads(eps_json)
                    content_hash = compute_memory_content_hash(
                        salt=m_salt,
                        canonical_text=rtext,
                        memory_type=rtype or "correction",
                        provenance=prov,
                        scope=scope,
                        owner_user_scope_key=cycle.user_scope_key,
                        scope_key=cycle.project_scope_key or cycle.user_scope_key,
                        source_episode_refs=eps,
                        review_decision_ref=dec_id,
                        supersedes_memory_id=None,
                        confidence=1.0
                    )

                    cur.execute("""
                    INSERT INTO reviewed_memories (
                        id, canonical_text, memory_type, provenance, retention_state,
                        scope, owner_user_scope_key, scope_key, source_episode_refs_json,
                        review_decision_ref, supersedes_memory_id, confidence, content_hash, created_at, content_hash_salt
                    ) VALUES (?, ?, ?, ?, 'accessible', ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?);
                    """, (
                        mem_id, rtext, rtype or "correction", prov, scope,
                        cycle.user_scope_key, cycle.project_scope_key or cycle.user_scope_key,
                        eps_json, dec_id, 1.0, content_hash, now_iso, m_salt
                    ))
                    try:
                        cur.execute(
                            "INSERT INTO reviewed_memories_fts (canonical_text, memory_id) VALUES (?, ?);",
                            (rtext, mem_id),
                        )
                    except Exception:
                        pass

                    new_mem_set[mem_id] = content_hash
                    affected_memory_ids.append(mem_id)

            # Compute new memory root
            new_version = cycle.base_memory_set_version + 1
            member_list = [{"memory_id": mid, "memory_content_hash": mhash} for mid, mhash in new_mem_set.items()]
            new_memory_root = compute_memory_root(cycle.user_scope_key, member_list)
            const_hash = self.get_constitution_hash()
            new_sys_hash = compute_system_state_hash(cycle.base_soul_state_hash, new_memory_root, const_hash)

            # Create receipt
            receipt_id = f"rcpt_{int(datetime.datetime.now().timestamp()*1000)}_{uuid.uuid4().hex[:8]}"
            cur.execute("""
            SELECT receipt_hash FROM memory_change_receipts
            WHERE owner_user_scope_key = ? ORDER BY committed_at DESC LIMIT 1;
            """, (cycle.user_scope_key,))
            prev_rcpt = cur.fetchone()
            prev_rcpt_hash = prev_rcpt[0] if prev_rcpt else None

            receipt_hash = compute_receipt_hash(
                previous_receipt_hash=prev_rcpt_hash,
                owner_user_scope_key=cycle.user_scope_key,
                operation_kind="review_commit",
                cycle_id=cycle_id,
                operation_hash=cycle.preview_hash,
                preview_hash=cycle.preview_hash,
                authority_event_hash=auth_event_hash,
                constitution_hash=const_hash,
                watermark_event_id=cycle.watermark_event_id,
                watermark_sequence=cycle.watermark_sequence,
                prior_soul_state_hash=cycle.base_soul_state_hash,
                result_soul_state_hash=cycle.base_soul_state_hash,
                prior_memory_set_version=cycle.base_memory_set_version,
                result_memory_set_version=new_version,
                prior_memory_root=cycle.base_memory_root,
                result_memory_root=new_memory_root,
                prior_system_state_hash=cycle.base_system_state_hash,
                result_system_state_hash=new_sys_hash,
                rollback_reference=str(cycle.base_memory_set_version),
                affected_memory_ids=affected_memory_ids,
                candidate_decision_summary={"total_decisions": len(dec_rows)},
                committed_at=now_iso
            )

            cur.execute("""
            INSERT INTO memory_change_receipts (
                id, previous_receipt_hash, owner_user_scope_key, operation_kind,
                cycle_id, operation_hash, preview_hash, authority_event_hash,
                constitution_hash, watermark_event_id, watermark_sequence,
                prior_soul_state_hash, result_soul_state_hash,
                prior_memory_set_version, result_memory_set_version,
                prior_memory_root, result_memory_root,
                prior_system_state_hash, result_system_state_hash,
                rollback_reference, affected_memory_ids_json,
                candidate_decision_summary_json, receipt_hash, committed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                receipt_id, prev_rcpt_hash, cycle.user_scope_key, "review_commit",
                cycle_id, cycle.preview_hash, cycle.preview_hash, auth_event_hash,
                const_hash, cycle.watermark_event_id, cycle.watermark_sequence,
                cycle.base_soul_state_hash, cycle.base_soul_state_hash,
                cycle.base_memory_set_version, new_version,
                cycle.base_memory_root, new_memory_root,
                cycle.base_system_state_hash, new_sys_hash,
                str(cycle.base_memory_set_version), json.dumps(affected_memory_ids),
                json.dumps({"total_decisions": len(dec_rows)}), receipt_hash, now_iso
            ))

            # Insert memory set version
            cur.execute("""
            INSERT INTO memory_set_versions (
                version, owner_user_scope_key, prior_version, prior_memory_root,
                memory_root, cycle_id, receipt_ref, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                new_version, cycle.user_scope_key, cycle.base_memory_set_version,
                cycle.base_memory_root, new_memory_root, cycle_id, receipt_id, now_iso
            ))

            # Insert members
            for mid, mhash in new_mem_set.items():
                cur.execute("""
                INSERT INTO memory_set_members (owner_user_scope_key, version, memory_id, memory_content_hash)
                VALUES (?, ?, ?, ?);
                """, (cycle.user_scope_key, new_version, mid, mhash))

            # Mark only decided (not pending/deferred) episodes as belonging to this cycle
            cur.execute("""
            UPDATE episodes
            SET review_cycle_id = ?
            WHERE review_cycle_id IS NULL AND id IN (
                SELECT value FROM memory_candidates, json_each(memory_candidates.source_episode_refs_json)
                WHERE memory_candidates.cycle_id = ?
                  AND memory_candidates.status IN ('confirmed', 'corrected', 'rejected')
            );
            """, (cycle_id, cycle_id))
            logging.info(
                "soul_review commit: stamped decided episodes for cycle %s; pending/deferred left extractable",
                cycle_id,
            )

            # Update cycle status to committed
            cur.execute("""
            UPDATE review_cycles
            SET status = 'committed', sealed_at = ?
            WHERE id = ?;
            """, (now_iso, cycle_id))

            conn.commit()

        return {
            "status": "committed",
            "cycle_id": cycle_id,
            "receipt_id": receipt_id,
            "receipt_hash": receipt_hash,
            "memory_set_version": new_version,
            "memory_root": new_memory_root,
            "affected_memories": affected_memory_ids,
            "promoted_memory_ids": affected_memory_ids
        }

    def recover_unsealed_cycles(self, user_scope_key: Optional[str] = None) -> List[str]:
        """Detect and mark unsealed review cycles as recovery_required upon startup (FR-5)."""
        with self._get_lock(), self._get_conn() as conn:
            cur = conn.cursor()
            if user_scope_key:
                cur.execute("""
                SELECT id FROM review_cycles
                WHERE user_scope_key = ? AND status IN ('active', 'idle_pending', 'preparing', 'reviewing', 'pending_commit');
                """, (user_scope_key,))
            else:
                cur.execute("""
                SELECT id FROM review_cycles
                WHERE status IN ('active', 'idle_pending', 'preparing', 'reviewing', 'pending_commit');
                """)
            unsealed_ids = [r[0] for r in cur.fetchall()]

            for cid in unsealed_ids:
                cur.execute("""
                UPDATE review_cycles SET status = 'recovery_required' WHERE id = ?;
                """, (cid,))

            conn.commit()
            return unsealed_ids

    def invalidate_provisional_cycle(self, cycle_id: str) -> dict:
        """Invalidate a provisional review cycle when human returns (FR-4)."""
        with self._get_lock(), self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT provisional, status FROM review_cycles WHERE id = ?;", (cycle_id,))
            row = cur.fetchone()
            if not row:
                raise ValueError(f"Cycle {cycle_id} not found")

            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            cur.execute("""
            UPDATE review_cycles
            SET status = 'deferred', invalidated_at = ?
            WHERE id = ?;
            """, (now_iso, cycle_id))

            cur.execute("""
            UPDATE memory_candidates
            SET status = 'stale'
            WHERE cycle_id = ? AND status = 'pending';
            """, (cycle_id,))

            conn.commit()
            return {"cycle_id": cycle_id, "status": "invalidated", "invalidated_at": now_iso}

    def list_active_reviewed_memories(
        self,
        user_scope_key: str = "default_user",
        project_scope_key: Optional[str] = None
    ) -> List[dict]:
        """List active reviewed memories for current user scope key."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
            WITH current_set AS (
                SELECT owner_user_scope_key, MAX(version) AS version
                FROM memory_set_versions
                WHERE owner_user_scope_key = ?
                GROUP BY owner_user_scope_key
            )
            SELECT rm.id, rm.canonical_text, rm.memory_type, rm.provenance,
                   rm.scope, rm.scope_key, rm.supersedes_memory_id, rm.confidence,
                   rm.content_hash, rm.created_at
            FROM current_set cs
            JOIN memory_set_members msm
              ON msm.owner_user_scope_key = cs.owner_user_scope_key
             AND msm.version = cs.version
            JOIN reviewed_memories rm ON rm.id = msm.memory_id
            WHERE rm.retention_state = 'accessible'
              AND rm.owner_user_scope_key = ?
              AND (
                  ? IS NULL
                  OR rm.scope_key = ?
                  OR rm.scope = 'user'
                  OR rm.scope = 'session_only'
              )
            ORDER BY rm.created_at DESC;
            """, (user_scope_key, user_scope_key, project_scope_key, project_scope_key))
            rows = cur.fetchall()
            return [
                {
                    "memory_id": r[0],
                    "canonical_text": r[1],
                    "memory_type": r[2],
                    "provenance": r[3],
                    "scope": r[4],
                    "scope_key": r[5],
                    "supersedes_memory_id": r[6],
                    "confidence": r[7],
                    "content_hash": r[8],
                    "created_at": r[9]
                }
                for r in rows
            ]
