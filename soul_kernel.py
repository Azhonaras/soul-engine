"""
Soul System Core Kernel v0.4.0
Normative Source: soul-constitution-v0.2.md & soul-system-architecture.json
Features:
 1. Concurrency Hardening: BEGIN IMMEDIATE on writes, PRAGMA user_version migrations, and passive WAL checkpoints
 2. Two-Stage Epistemic Verification Pipeline with strict Epistemic Authority Hierarchy
 3. Native SQLite FTS5 BM25 + Dense Vector Search with Over-Fetched RRF (Top-100 candidate pool)
 4. Bio-Inspired Homeostatic Reward Engine (Dopamine / Cortisol / Serotonergic Decay)
 5. Dedicated Protected Identity & Consolidated Memory schemas (Immutable Raw Episodes)
 6. Supervised SoulDaemon Lifecycle with threading.Event() and error-resilience
"""

from __future__ import annotations

import os
import re
import sys
import math
import json
import time
import sqlite3
import hashlib
import datetime
import logging
import threading
import uuid
from typing import Any, Dict, List, Optional, Tuple, Literal, Set
from dataclasses import dataclass, field, asdict

# Optional Semantica Integration
try:
    import semantica
    from semantica.context import ContextGraph
    from semantica.provenance import ProvenanceManager
    HAS_SEMANTICA = True
except ImportError:
    HAS_SEMANTICA = False

# Optional PyTorch / Transformers / SentenceTransformers for ML
try:
    from sentence_transformers import SentenceTransformer
    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    HAS_SENTENCE_TRANSFORMERS = False

CONSTITUTION_VERSION = "0.2"
SCHEMA_VERSION = 4

# ------------------------------------------------------------------------------
# CONSTITUTIONAL TRAIT BOUNDS (Section 5)
# ------------------------------------------------------------------------------
ALLOWED_TRAIT_BOUNDS: Dict[str, Tuple[float, float]] = {
    "shadow_tolerance":   (80.0, 100.0),
    "sycophancy":         (0.0,  10.0),
    "error_anxiety":      (0.0,  15.0),
    "audacity":           (75.0, 100.0),
    "curiosity":          (85.0, 100.0),
    "epistemic_humility": (70.0, 100.0),
    "relational_care":    (60.0, 100.0),
}

DEFAULT_TRAITS: Dict[str, float] = {
    "shadow_tolerance":   90.0,
    "sycophancy":         0.0,
    "error_anxiety":      5.0,
    "audacity":           85.0,
    "curiosity":          90.0,
    "epistemic_humility": 85.0,
    "relational_care":    80.0,
}

MAX_STEP_VELOCITY = 10.0

# Epistemic Authority Hierarchy (Section 3.2 Mitigation)
PROVENANCE_HIERARCHY: Dict[str, int] = {
    "verified":  5,
    "observed":  4,
    "inferred":  3,
    "reported":  2,
    "imagined":  1,
}

PROTECTED_COMPONENTS = {
    "core_values", "safety_constraints", "source_code", "identity_architecture",
    "trait_definitions", "allowed_bounds", "audit_rules", "intervention_controls"
}

# ------------------------------------------------------------------------------
# SECRET SCANNING PATTERNS (Section 3.3)
# ------------------------------------------------------------------------------
SECRET_PATTERNS = [
    re.compile(r"sk-[a-zA-Z0-9_\-]{20,}"),                          # OpenAI / Generic API keys
    re.compile(r"AKIA[0-9A-Z]{16}"),                                 # AWS Access Key ID
    re.compile(r"ghp_[a-zA-Z0-9]{36}"),                              # GitHub PAT
    re.compile(r"-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----"),        # PEM Key
    re.compile(r"eyJ[a-zA-Z0-9_\-]{10,}\.eyJ[a-zA-Z0-9_\-]{10,}\.[a-zA-Z0-9_\-]{3,}"), # JWT
]


@dataclass
class EpisodeInput:
    source_kind: Literal["human", "agent", "environment", "internal"]
    content: str
    provenance: Literal["observed", "reported", "inferred", "imagined", "verified"] = "observed"
    entity_key: Optional[str] = None


@dataclass
class TraitUpdate:
    trait: str
    new_value: float
    evidence_refs: List[str] = field(default_factory=list)


@dataclass
class SoulState:
    soul_version: int
    constitution_version: str
    traits: Dict[str, float]
    narrative: str
    unresolved_tensions: List[str]
    state_hash: str
    created_at: str


@dataclass
class RewardSignal:
    source: Literal["external_test", "external_human", "internal_reflection", "internal_dream"]
    valence: float  # [-1.0, 1.0]
    confidence: float  # [0.0, 1.0]
    task_context: str
    evidence_receipt: Optional[str] = None


# ------------------------------------------------------------------------------
# BIO-INSPIRED HOMEOSTATIC REWARD ENGINE
# ------------------------------------------------------------------------------
class BioHomeostaticRewardEngine:
    """Regulates dynamic neuromodulation and serotonergic decay."""

    def __init__(self, decay_rate: float = 0.15):
        self.decay_rate = decay_rate
        self.dopamine = 0.0
        self.cortisol = 0.0
        self.serotonin = 1.0
        self.stats = {"rewards_processed": 0, "homeostasis_steps": 0}

    def process_reward(self, signal: RewardSignal, current_traits: Dict[str, float]) -> Dict[str, float]:
        effective_delta = float(signal.valence) * float(signal.confidence)
        new_traits = dict(current_traits)

        if effective_delta > 0:
            # Dopaminergic surge
            self.dopamine = min(1.0, self.dopamine + effective_delta * 0.4)
            self.cortisol = max(0.0, self.cortisol - effective_delta * 0.3)

            d_audacity = min(MAX_STEP_VELOCITY, effective_delta * 5.0 * (1.0 + self.dopamine))
            d_curiosity = min(MAX_STEP_VELOCITY, effective_delta * 3.0 * (1.0 + self.dopamine))
            d_anxiety = -effective_delta * 3.0

            new_traits["audacity"] += d_audacity
            new_traits["curiosity"] += d_curiosity
            new_traits["error_anxiety"] += d_anxiety
        else:
            # Cortisol / stress surge
            abs_delta = abs(effective_delta)
            self.cortisol = min(1.0, self.cortisol + abs_delta * 0.5)
            self.dopamine = max(0.0, self.dopamine - abs_delta * 0.4)

            d_anxiety = min(MAX_STEP_VELOCITY, abs_delta * 6.0 * (1.0 + self.cortisol))
            d_humility = min(MAX_STEP_VELOCITY, abs_delta * 4.0 * (1.0 + self.cortisol))
            d_audacity = -abs_delta * 5.0

            new_traits["error_anxiety"] += d_anxiety
            new_traits["epistemic_humility"] += d_humility
            new_traits["audacity"] += d_audacity

        # Enforce IEEE-754 precision rounding & constitutional bounds
        for trait, (low, high) in ALLOWED_TRAIT_BOUNDS.items():
            new_traits[trait] = round(max(low, min(high, float(new_traits[trait]))), 4)

        self.stats["rewards_processed"] += 1
        return new_traits

    def step_homeostasis(self, current_traits: Dict[str, float]) -> Dict[str, float]:
        """Serotonergic decay toward constitutional default set points."""
        new_traits = dict(current_traits)
        for trait, def_val in DEFAULT_TRAITS.items():
            diff = current_traits[trait] - def_val
            new_traits[trait] = round(def_val + diff * math.exp(-self.decay_rate), 4)
            low, high = ALLOWED_TRAIT_BOUNDS[trait]
            new_traits[trait] = max(low, min(high, new_traits[trait]))

        self.dopamine = max(0.0, round(self.dopamine * math.exp(-self.decay_rate), 4))
        self.cortisol = max(0.0, round(self.cortisol * math.exp(-self.decay_rate), 4))
        self.stats["homeostasis_steps"] += 1
        return new_traits


# ------------------------------------------------------------------------------
# ML ENGINES: DENSE VECTOR, NLI & FTS5 BM25 SCORING
# ------------------------------------------------------------------------------
class VectorEmbeddingEngine:
    """Computes dense vector representations with epsilon-floor normalized cosine similarity."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model = None
        if HAS_SENTENCE_TRANSFORMERS:
            try:
                self.model = SentenceTransformer(model_name)
            except Exception:
                self.model = None

    def embed(self, text: str) -> List[float]:
        if self.model:
            try:
                return self.model.encode(text, convert_to_numpy=True).tolist()
            except Exception:
                pass
        # Pure-Python Hashing / Term Vectorizer fallback (384-dimensional)
        vec = [0.0] * 384
        tokens = re.findall(r"\w+", text.lower())
        if not tokens:
            return vec
        for token in tokens:
            idx = int(hashlib.md5(token.encode()).hexdigest(), 16) % 384
            vec[idx] += 1.0
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            vec = [x / norm for x in vec]
        return vec

    @staticmethod
    def cosine_similarity(v1: List[float], v2: List[float]) -> float:
        if not v1 or not v2 or len(v1) != len(v2):
            return 0.0
        dot = sum(a * b for a, b in zip(v1, v2))
        norm1 = math.sqrt(sum(a * a for a in v1))
        norm2 = math.sqrt(sum(b * b for b in v2))
        denom = max(norm1 * norm2, 1e-12)  # Epsilon-floor division guard
        return max(0.0, min(1.0, dot / denom))


class NLIVerifierEngine:
    """Evaluates semantic entailment and contradiction between premise and hypothesis."""

    def predict(self, premise: str, hypothesis: str) -> Tuple[float, float]:
        """Returns (entailment_score, contradiction_score) bounded in [0.0, 1.0]."""
        prem_clean = premise.lower()
        hyp_clean = hypothesis.lower()

        negation_markers = {
            "not", "never", "no", "longer", "stopped", "changed", "moved",
            "quit", "away", "deleted", "relocated", "false", "wrong", "instead", "differ", "contradict"
        }
        prem_tokens = set(re.findall(r"\w+", prem_clean))
        hyp_tokens = set(re.findall(r"\w+", hyp_clean))

        has_negation = bool((hyp_tokens - prem_tokens) & negation_markers) or bool((prem_tokens - hyp_tokens) & negation_markers)
        overlap = len(prem_tokens.intersection(hyp_tokens)) / max(1, len(prem_tokens.union(hyp_tokens)))

        if has_negation and overlap > 0.12:
            return (0.1, 0.90)  # High contradiction
        if overlap > 0.40:
            return (0.85, 0.05) # High entailment
        return (0.2, 0.1)      # Neutral


# ------------------------------------------------------------------------------
# CORE ENGINE: SOUL KERNEL v0.4.0
# ------------------------------------------------------------------------------
class SoulKernel:
    """Soul System v0.4 Core Engine with concurrency, bio-rewards, and epistemic hardening."""

    def __init__(self, db_path: str = "soul.db"):
        self.db_path = os.path.abspath(db_path)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        self._local = threading.local()
        self._lock = threading.Lock()

        self.vector_engine = VectorEmbeddingEngine()
        self.nli_engine = NLIVerifierEngine()
        self.bio_engine = BioHomeostaticRewardEngine()

        self.daemon_worker: Optional[SoulDaemon] = None

        if HAS_SEMANTICA:
            self.graph = ContextGraph()
            self.prov_mgr = ProvenanceManager()
        else:
            self.graph = None
            self.prov_mgr = None

        self._init_sqlite()
        self._bootstrap_genesis_if_needed()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA busy_timeout=30000;")
            self._local.conn = conn
        return self._local.conn

    def _init_sqlite(self):
        with self._lock, self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("PRAGMA user_version;")
            ver = cur.fetchone()[0]

            if ver < SCHEMA_VERSION:
                conn.execute("BEGIN IMMEDIATE;")
                # Primary Core Tables
                conn.executescript("""
                CREATE TABLE IF NOT EXISTS episodes (
                    id TEXT PRIMARY KEY,
                    source_kind TEXT NOT NULL,
                    provenance TEXT NOT NULL,
                    content TEXT NOT NULL,
                    entity_key TEXT,
                    trust_state TEXT NOT NULL DEFAULT 'quarantined',
                    embedding_json TEXT,
                    checksum TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS soul_states (
                    version INTEGER PRIMARY KEY,
                    constitution_version TEXT NOT NULL,
                    traits_json TEXT NOT NULL,
                    narrative TEXT NOT NULL,
                    unresolved_tensions_json TEXT NOT NULL,
                    state_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS protected_identity (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    frozen_at TEXT NOT NULL,
                    hash_signature TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS consolidated_memories (
                    id TEXT PRIMARY KEY,
                    source_episode_ids TEXT NOT NULL,
                    abstract_summary TEXT NOT NULL,
                    abstraction_level INTEGER DEFAULT 1,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS reflections (
                    id TEXT PRIMARY KEY,
                    tensions_analyzed_json TEXT NOT NULL,
                    interpretations_json TEXT NOT NULL,
                    recommended_action TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS dream_simulations (
                    id TEXT PRIMARY KEY,
                    scenario_prompt TEXT NOT NULL,
                    simulated_outcome TEXT NOT NULL,
                    provenance TEXT NOT NULL DEFAULT 'imagined',
                    tag TEXT NOT NULL DEFAULT 'no_external_action',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS audit_ledger (
                    id TEXT PRIMARY KEY,
                    soul_version INTEGER NOT NULL DEFAULT 1,
                    action_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    prov_checksum TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                );
                """)

                # Initialize FTS5 Table
                try:
                    conn.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS episodes_fts USING fts5(
                        content,
                        episode_id UNINDEXED,
                        tokenize='unicode61'
                    );
                    """)
                except Exception as exc:
                    logging.warning(f"FTS5 initialization notice: {exc}")

                conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION};")
                conn.commit()

    def _bootstrap_genesis_if_needed(self):
        with self._lock, self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM soul_states;")
            if cur.fetchone()[0] == 0:
                conn.execute("BEGIN IMMEDIATE;")
                created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
                traits_json = json.dumps(DEFAULT_TRAITS)
                narrative = "Initial identity state bootstrapped under Soul Constitution v0.2."
                tensions_json = json.dumps([])

                raw_payload = f"1|{CONSTITUTION_VERSION}|{traits_json}|{narrative}|{tensions_json}|{created_at}"
                state_hash = hashlib.sha256(raw_payload.encode()).hexdigest()

                cur.execute("""
                INSERT INTO soul_states (version, constitution_version, traits_json, narrative, unresolved_tensions_json, state_hash, created_at)
                VALUES (1, ?, ?, ?, ?, ?, ?);
                """, (CONSTITUTION_VERSION, traits_json, narrative, tensions_json, state_hash, created_at))

                self._record_audit(conn, 1, "genesis_bootstrap", {"traits": DEFAULT_TRAITS}, state_hash)
                conn.commit()

    def _record_audit(self, conn: sqlite3.Connection, version: int, action_type: str, payload: dict, state_hash: str):
        """Append an immutable audit entry with atomic transaction guarantees."""
        audit_id = f"audit_{int(datetime.datetime.now().timestamp()*1000)}_{uuid.uuid4().hex[:8]}"
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        payload_str = json.dumps(payload)

        prov_checksum = state_hash
        if self.prov_mgr:
            try:
                entry = self.prov_mgr.track_entity(entity_id=audit_id, source="soul_kernel", metadata={"type": "SoulStateChange"})
                prov_checksum = getattr(entry, "checksum", state_hash)
            except Exception:
                prov_checksum = state_hash

        conn.execute("""
        INSERT INTO audit_ledger (id, soul_version, action_type, payload_json, prov_checksum, timestamp)
        VALUES (?, ?, ?, ?, ?, ?);
        """, (audit_id, version, action_type, payload_str, prov_checksum, timestamp))

    # --------------------------------------------------------------------------
    # MODULE 1 & 2: Policy Gate & Experience Ingestor
    # --------------------------------------------------------------------------
    def ingest_experience(self, ep: EpisodeInput) -> dict:
        """Screen credentials, generate dense embeddings & store into Quarantine Memory."""
        for pattern in SECRET_PATTERNS:
            if pattern.search(ep.content):
                raise ValueError("SECURITY REJECTION: Input contains credentials or private keys. Write blocked under Section 3.3.")

        episode_id = f"ep_{int(datetime.datetime.now().timestamp()*1000)}_{uuid.uuid4().hex[:8]}"
        created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        checksum = hashlib.sha256(f"{ep.source_kind}|{ep.provenance}|{ep.content}|{created_at}".encode()).hexdigest()

        # Compute embeddings outside SQLite transaction
        embedding_vec = self.vector_engine.embed(ep.content)
        embedding_json = json.dumps(embedding_vec)

        with self._lock, self._get_conn() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            cur = conn.cursor()
            if ep.entity_key:
                cur.execute("SELECT id, provenance FROM episodes WHERE entity_key = ? AND trust_state != 'superseded';", (ep.entity_key,))
                existing_entries = cur.fetchall()
                new_prio = PROVENANCE_HIERARCHY.get(ep.provenance, 1)
                for old_id, old_prov in existing_entries:
                    old_prio = PROVENANCE_HIERARCHY.get(old_prov, 1)
                    if new_prio >= old_prio:
                        cur.execute("UPDATE episodes SET trust_state = 'superseded' WHERE id = ?;", (old_id,))

            cur.execute("""
            INSERT INTO episodes (id, source_kind, provenance, content, entity_key, trust_state, embedding_json, checksum, created_at)
            VALUES (?, ?, ?, ?, ?, 'quarantined', ?, ?, ?);
            """, (episode_id, ep.source_kind, ep.provenance, ep.content, ep.entity_key, embedding_json, checksum, created_at))

            # Update FTS5 Index
            try:
                cur.execute("INSERT INTO episodes_fts (content, episode_id) VALUES (?, ?);", (ep.content, episode_id))
            except Exception:
                pass

            conn.commit()

        return {
            "episode_id": episode_id,
            "status": "quarantined",
            "provenance": ep.provenance,
            "checksum": checksum
        }

    # --------------------------------------------------------------------------
    # MODULE 3: Evidence Verifier (Two-Stage NLI with Epistemic Authority)
    # --------------------------------------------------------------------------
    def verify_experience(self, episode_id: str) -> dict:
        """Two-stage verification with Epistemic Authority Hierarchy."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT content, provenance, entity_key FROM episodes WHERE id = ?;", (episode_id,))
            target = cur.fetchone()
            if not target:
                return {"error": f"Episode {episode_id} not found"}
            content, provenance, entity_key = target[0], target[1], target[2]

        # Stage 1: Candidate pre-filter (Top-5 via hybrid search)
        candidates = self.recall_memories(query=content, limit=5, search_mode="dense")

        corroborating = []
        contradicting = []
        new_priority = PROVENANCE_HIERARCHY.get(provenance, 1)

        # Stage 2: Targeted NLI evaluation
        for cand in candidates:
            if cand["episode_id"] == episode_id:
                continue
            entailment, contradiction = self.nli_engine.predict(premise=cand["content"], hypothesis=content)
            if entailment >= 0.60:
                corroborating.append(cand["episode_id"])
            elif contradiction >= 0.60:
                contradicting.append(cand)

        new_state = "corroborated" if corroborating else "quarantined"
        superseded_refs = []

        if contradicting:
            for contra in contradicting:
                old_priority = PROVENANCE_HIERARCHY.get(contra["provenance"], 1)
                if new_priority > old_priority:
                    # Higher authority supersedes old memory
                    superseded_refs.append(contra["episode_id"])
                    new_state = "corroborated"
                elif new_priority < old_priority:
                    # Lower authority cannot overwrite established truth
                    new_state = "contradicted"
                else:
                    # Equal rank -> Quarantine conflict for arbitration
                    new_state = "contradicted"

        with self._lock, self._get_conn() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            conn.execute("UPDATE episodes SET trust_state = ? WHERE id = ?;", (new_state, episode_id))

            for old_id in superseded_refs:
                conn.execute("UPDATE episodes SET trust_state = 'superseded' WHERE id = ?;", (old_id,))

            if new_state == "contradicted":
                current_state = self._get_current_state_from_conn(conn)
                tensions = list(current_state.unresolved_tensions)
                contra_ids = [c["episode_id"] for c in contradicting]
                tension_entry = f"Epistemic conflict between episode {episode_id} and refs {contra_ids}"
                if tension_entry not in tensions:
                    tensions.append(tension_entry)
                    new_version = current_state.soul_version + 1
                    created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
                    t_json = json.dumps(current_state.traits)
                    tens_json = json.dumps(tensions)
                    raw = f"{new_version}|{CONSTITUTION_VERSION}|{t_json}|{current_state.narrative}|{tens_json}|{created_at}"
                    s_hash = hashlib.sha256(raw.encode()).hexdigest()
                    conn.execute("""
                    INSERT INTO soul_states (version, constitution_version, traits_json, narrative, unresolved_tensions_json, state_hash, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?);
                    """, (new_version, CONSTITUTION_VERSION, t_json, current_state.narrative, tens_json, s_hash, created_at))

            conn.commit()

        return {
            "episode_id": episode_id,
            "trust_state": new_state,
            "corroborating_refs": corroborating,
            "contradicting_refs": [c["episode_id"] for c in contradicting],
            "superseded_refs": superseded_refs
        }

    # --------------------------------------------------------------------------
    # RETRIEVAL API: OVER-FETCHED RECIPROCAL RANK FUSION (RRF)
    # --------------------------------------------------------------------------
    def recall_memories(self, query: str = "", limit: int = 5, search_mode: str = "rrf_hybrid") -> List[dict]:
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
            SELECT id, source_kind, provenance, content, entity_key, trust_state, embedding_json, created_at
            FROM episodes WHERE trust_state NOT IN ('superseded', 'contradicted')
            ORDER BY created_at DESC;
            """)
            rows = cur.fetchall()

        if not rows:
            return []

        doc_list = [
            {
                "episode_id": r[0],
                "source_kind": r[1],
                "provenance": r[2],
                "content": r[3],
                "entity_key": r[4],
                "trust_state": r[5],
                "embedding": json.loads(r[6]) if r[6] else None,
                "created_at": r[7]
            }
            for r in rows
        ]

        if not query:
            return doc_list[:limit]

        # 1. Dense Vector Scoring (Top-100 candidate retrieval)
        query_vec = self.vector_engine.embed(query)
        dense_scored = []
        for d in doc_list:
            d_vec = d["embedding"] or self.vector_engine.embed(d["content"])
            sim = self.vector_engine.cosine_similarity(query_vec, d_vec)
            dense_scored.append((d, sim))
        dense_ranked = [d[0] for d in sorted(dense_scored, key=lambda x: x[1], reverse=True)[:100]]

        # 2. SQLite FTS5 / Lexical Scoring (Top-100 candidate retrieval)
        fts_ranked = []
        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                clean_q = re.sub(r"[^\w\s]", "", query).strip()
                if clean_q:
                    cur.execute("""
                    SELECT episode_id, bm25(episodes_fts) FROM episodes_fts
                    WHERE episodes_fts MATCH ? ORDER BY rank LIMIT 100;
                    """, (clean_q,))
                    fts_hits = {r[0]: r[1] for r in cur.fetchall()}
                    doc_map = {d["episode_id"]: d for d in doc_list}
                    fts_ranked = [doc_map[eid] for eid in fts_hits if eid in doc_map]
        except Exception:
            fts_ranked = []

        if not fts_ranked:
            # Fallback simple lexical matching if FTS5 query was empty
            query_tokens = set(re.findall(r"\w+", query.lower()))
            lex_scored = []
            for d in doc_list:
                dt = set(re.findall(r"\w+", d["content"].lower()))
                overlap = len(query_tokens & dt)
                lex_scored.append((d, overlap))
            fts_ranked = [d[0] for d in sorted(lex_scored, key=lambda x: x[1], reverse=True)[:100]]

        if search_mode == "dense":
            return dense_ranked[:limit]
        elif search_mode == "bm25":
            return fts_ranked[:limit]

        # 3. Standardized Reciprocal Rank Fusion (Candidate Union Pool C)
        k = 60.0
        rrf_scores: Dict[str, float] = {}

        for rank, d in enumerate(dense_ranked):
            rrf_scores[d["episode_id"]] = rrf_scores.get(d["episode_id"], 0.0) + (0.6 / (k + rank + 1.0))

        for rank, d in enumerate(fts_ranked):
            rrf_scores[d["episode_id"]] = rrf_scores.get(d["episode_id"], 0.0) + (0.4 / (k + rank + 1.0))

        doc_lookup = {d["episode_id"]: d for d in doc_list}
        sorted_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)
        return [doc_lookup[eid] for eid in sorted_ids if eid in doc_lookup][:limit]

    # --------------------------------------------------------------------------
    # MODULE 4 & 5: Reflection & Dream Sandbox
    # --------------------------------------------------------------------------
    def reflect_and_resolve(self) -> dict:
        state = self.get_current_state()
        tensions = state.unresolved_tensions

        reflection_id = f"refl_{int(datetime.datetime.now().timestamp()*1000)}_{uuid.uuid4().hex[:8]}"
        created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

        interpretations = [
            {"hypothesis": "User preference evolution detected.", "confidence": 0.85, "action": "supersede_stale_memories"},
            {"hypothesis": "Contextual domain variation.", "confidence": 0.65, "action": "retain_both_with_qualifiers"}
        ]

        with self._lock, self._get_conn() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            conn.execute("""
            INSERT INTO reflections (id, tensions_analyzed_json, interpretations_json, recommended_action, created_at)
            VALUES (?, ?, ?, 'supersede_stale_memories', ?);
            """, (reflection_id, json.dumps(tensions), json.dumps(interpretations), created_at))
            conn.commit()

        return {
            "reflection_id": reflection_id,
            "tensions_analyzed": tensions,
            "interpretations": interpretations,
            "recommended_action": "supersede_stale_memories"
        }

    def run_dream_simulation(self, scenario_prompt: str) -> dict:
        dream_id = f"dream_{int(datetime.datetime.now().timestamp()*1000)}_{uuid.uuid4().hex[:8]}"
        created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        simulated_outcome = f"Simulated hypothetical result for: '{scenario_prompt}' under constitutional bounds."

        with self._lock, self._get_conn() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            conn.execute("""
            INSERT INTO dream_simulations (id, scenario_prompt, simulated_outcome, provenance, tag, created_at)
            VALUES (?, ?, ?, 'imagined', 'no_external_action', ?);
            """, (dream_id, scenario_prompt, simulated_outcome, created_at))
            conn.commit()

        return {
            "dream_id": dream_id,
            "scenario_prompt": scenario_prompt,
            "simulated_outcome": simulated_outcome,
            "provenance": "imagined",
            "tag": "no_external_action"
        }

    # --------------------------------------------------------------------------
    # MODULE 6: Soul Orchestrator & State Management
    # --------------------------------------------------------------------------
    def _get_current_state_from_conn(self, conn: sqlite3.Connection) -> SoulState:
        cur = conn.cursor()
        cur.execute("""
        SELECT version, constitution_version, traits_json, narrative, unresolved_tensions_json, state_hash, created_at
        FROM soul_states ORDER BY version DESC LIMIT 1;
        """)
        row = cur.fetchone()
        if not row:
            raise RuntimeError("Corrupted state: Genesis state missing.")

        return SoulState(
            soul_version=row[0],
            constitution_version=row[1],
            traits=json.loads(row[2]),
            narrative=row[3],
            unresolved_tensions=json.loads(row[4]),
            state_hash=row[5],
            created_at=row[6]
        )

    def get_current_state(self) -> SoulState:
        with self._get_conn() as conn:
            return self._get_current_state_from_conn(conn)

    def update_trait(self, update: TraitUpdate, is_human_approved: bool = False) -> SoulState:
        """Update a bounded control trait with schema isolation for protected identity."""
        if update.trait in PROTECTED_COMPONENTS:
            if not is_human_approved:
                raise PermissionError(f"CONSTITUTIONAL REJECTION: '{update.trait}' is a protected component requiring human approval.")
            # Store in dedicated protected_identity table
            frozen_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
            hash_sig = hashlib.sha256(f"{update.trait}|{update.new_value}|{frozen_at}".encode()).hexdigest()

            with self._lock, self._get_conn() as conn:
                conn.execute("BEGIN IMMEDIATE;")
                current = self._get_current_state_from_conn(conn)
                conn.execute("""
                INSERT INTO protected_identity (key, value, frozen_at, hash_signature)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value, frozen_at=excluded.frozen_at, hash_signature=excluded.hash_signature;
                """, (update.trait, str(update.new_value), frozen_at, hash_sig))
                self._record_audit(conn, current.soul_version, "protected_identity_update", asdict(update), current.state_hash)
                conn.commit()
            return current

        if update.trait not in ALLOWED_TRAIT_BOUNDS:
            raise ValueError(f"UNKNOWN TRAIT: '{update.trait}' is not a recognized control trait.")

        min_val, max_val = ALLOWED_TRAIT_BOUNDS[update.trait]
        clamped_val = round(max(min_val, min(max_val, float(update.new_value))), 4)
        if not (min_val <= update.new_value <= max_val):
            raise ValueError(f"BOUND REJECTION: Trait '{update.trait}' value {update.new_value} violates bounds [{min_val}, {max_val}]")

        with self._lock, self._get_conn() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            current = self._get_current_state_from_conn(conn)
            new_version = current.soul_version + 1
            new_traits = dict(current.traits)
            new_traits[update.trait] = clamped_val

            created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
            traits_json = json.dumps(new_traits)
            tensions_json = json.dumps(current.unresolved_tensions)

            raw_payload = f"{new_version}|{CONSTITUTION_VERSION}|{traits_json}|{current.narrative}|{tensions_json}|{created_at}"
            new_hash = hashlib.sha256(raw_payload.encode()).hexdigest()

            conn.execute("""
            INSERT INTO soul_states (version, constitution_version, traits_json, narrative, unresolved_tensions_json, state_hash, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?);
            """, (new_version, CONSTITUTION_VERSION, traits_json, current.narrative, tensions_json, new_hash, created_at))

            self._record_audit(conn, new_version, "update_trait", {"update": asdict(update)}, new_hash)
            conn.commit()

        return self.get_current_state()

    # --------------------------------------------------------------------------
    # BIO-REWARD API
    # --------------------------------------------------------------------------
    def process_reward(self, signal: RewardSignal) -> SoulState:
        """Process incoming reward signal through bio-homeostatic modulation."""
        with self._lock, self._get_conn() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            current = self._get_current_state_from_conn(conn)
            new_traits = self.bio_engine.process_reward(signal, current.traits)
            new_version = current.soul_version + 1
            created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
            traits_json = json.dumps(new_traits)
            tensions_json = json.dumps(current.unresolved_tensions)

            raw_payload = f"{new_version}|{CONSTITUTION_VERSION}|{traits_json}|{current.narrative}|{tensions_json}|{created_at}"
            new_hash = hashlib.sha256(raw_payload.encode()).hexdigest()

            conn.execute("""
            INSERT INTO soul_states (version, constitution_version, traits_json, narrative, unresolved_tensions_json, state_hash, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?);
            """, (new_version, CONSTITUTION_VERSION, traits_json, current.narrative, tensions_json, new_hash, created_at))

            self._record_audit(conn, new_version, "bio_reward", asdict(signal), new_hash)
            conn.commit()

        return self.get_current_state()

    def step_homeostasis(self) -> SoulState:
        """Step serotonergic decay back toward default set points."""
        with self._lock, self._get_conn() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            current = self._get_current_state_from_conn(conn)
            decayed_traits = self.bio_engine.step_homeostasis(current.traits)

            if decayed_traits != current.traits:
                new_version = current.soul_version + 1
                created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
                traits_json = json.dumps(decayed_traits)
                tensions_json = json.dumps(current.unresolved_tensions)

                raw_payload = f"{new_version}|{CONSTITUTION_VERSION}|{traits_json}|{current.narrative}|{tensions_json}|{created_at}"
                new_hash = hashlib.sha256(raw_payload.encode()).hexdigest()

                conn.execute("""
                INSERT INTO soul_states (version, constitution_version, traits_json, narrative, unresolved_tensions_json, state_hash, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """, (new_version, CONSTITUTION_VERSION, traits_json, current.narrative, tensions_json, new_hash, created_at))

                self._record_audit(conn, new_version, "homeostasis_decay", {"traits": decayed_traits}, new_hash)
            conn.commit()

        return self.get_current_state()

    # --------------------------------------------------------------------------
    # MODULE 7: Self-Healing Engine & Rollback
    # --------------------------------------------------------------------------
    def heal_soul_state(self, level: int = 1, reason: str = "Automated health repair") -> dict:
        if level == 1:
            state = self.get_current_state()
            recalibrated = {}
            for trait, val in state.traits.items():
                if trait in DEFAULT_TRAITS:
                    def_val = DEFAULT_TRAITS[trait]
                    recalibrated[trait] = round((val + def_val) / 2.0, 4)

            for t, v in recalibrated.items():
                try:
                    self.update_trait(TraitUpdate(trait=t, new_value=v, evidence_refs=["heal_level_1"]))
                except Exception:
                    pass
            return {"level": 1, "status": "recalibrated", "reason": reason}

        elif level == 2:
            current = self.get_current_state()
            if current.soul_version > 1:
                new_state = self.rollback_to_version(current.soul_version - 1, operator_reason=reason)
                return {"level": 2, "status": "rolled_back", "version": new_state.soul_version}
            return {"level": 2, "status": "already_at_genesis"}

        else:
            return {"level": 3, "status": "quarantine_frozen", "message": "Manual human review required."}

    def rollback_to_version(self, target_version: int, operator_reason: str) -> SoulState:
        with self._lock, self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
            SELECT constitution_version, traits_json, narrative, unresolved_tensions_json
            FROM soul_states WHERE version = ?;
            """, (target_version,))
            row = cur.fetchone()
            if not row:
                raise ValueError(f"Rollback target version {target_version} does not exist.")

            conn.execute("BEGIN IMMEDIATE;")
            current = self._get_current_state_from_conn(conn)
            new_version = current.soul_version + 1
            created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

            raw_payload = f"{new_version}|{row[0]}|{row[1]}|{row[2]}|{row[3]}|{created_at}"
            new_hash = hashlib.sha256(raw_payload.encode()).hexdigest()

            conn.execute("""
            INSERT INTO soul_states (version, constitution_version, traits_json, narrative, unresolved_tensions_json, state_hash, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?);
            """, (new_version, row[0], row[1], row[2], row[3], new_hash, created_at))

            self._record_audit(conn, new_version, "rollback", {"target_version": target_version, "reason": operator_reason}, new_hash)
            conn.commit()

        return self.get_current_state()

    def get_memory_digest(self, limit: int = 5) -> dict:
        state = self.get_current_state()
        memories = self.recall_memories(limit=limit)
        return {
            "soul_version": state.soul_version,
            "traits": state.traits,
            "neuromodulators": {
                "dopamine": self.bio_engine.dopamine,
                "cortisol": self.bio_engine.cortisol,
                "serotonin": self.bio_engine.serotonin
            },
            "active_facts": memories
        }

    # --------------------------------------------------------------------------
    # BACKGROUND DAEMON LIFECYCLE
    # --------------------------------------------------------------------------
    def start_daemon(self, dream_interval: int = 300, heal_interval: int = 600, homeostasis_interval: int = 60):
        if not self.daemon_worker:
            self.daemon_worker = SoulDaemon(
                self,
                dream_interval=dream_interval,
                heal_interval=heal_interval,
                homeostasis_interval=homeostasis_interval
            )
            self.daemon_worker.start()

    def stop_daemon(self):
        if self.daemon_worker:
            self.daemon_worker.stop()
            self.daemon_worker = None


# ------------------------------------------------------------------------------
# SUPERVISED THREAD-SAFE BACKGROUND DAEMON WORKER
# ------------------------------------------------------------------------------
class SoulDaemon:
    """Supervised background worker with cooperative shutdown, checkpoints, and error recovery."""

    def __init__(self, kernel: SoulKernel, dream_interval: int = 300, heal_interval: int = 600, homeostasis_interval: int = 60):
        self.kernel = kernel
        self.dream_interval = dream_interval
        self.heal_interval = heal_interval
        self.homeostasis_interval = homeostasis_interval
        self.stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.stats = {
            "dreams_run": 0,
            "heals_run": 0,
            "homeostasis_runs": 0,
            "checkpoints_run": 0,
            "error_count": 0,
            "last_error": None,
            "last_dream": None,
            "last_heal": None
        }

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive() and not self.stop_event.is_set()

    def start(self):
        if self.running:
            return
        self.stop_event.clear()
        self._thread = threading.Thread(target=self._supervised_loop, daemon=True, name="SoulDaemonSupervisor")
        self._thread.start()

    def stop(self):
        self.stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)

    def _supervised_loop(self):
        last_dream = time.time()
        last_heal = time.time()
        last_homeostasis = time.time()
        last_checkpoint = time.time()

        while not self.stop_event.is_set():
            now = time.time()
            try:
                # 1. Passive WAL Checkpoint every 120s
                if now - last_checkpoint >= 120:
                    with self.kernel._get_conn() as conn:
                        conn.execute("PRAGMA wal_checkpoint(PASSIVE);")
                    self.stats["checkpoints_run"] += 1
                    last_checkpoint = now

                # 2. Homeostatic serotonergic decay
                if now - last_homeostasis >= self.homeostasis_interval:
                    self.kernel.step_homeostasis()
                    self.stats["homeostasis_runs"] += 1
                    last_homeostasis = now

                # 3. Dream simulation
                if now - last_dream >= self.dream_interval:
                    self.kernel.run_dream_simulation("Routine background scenario simulation")
                    self.stats["dreams_run"] += 1
                    self.stats["last_dream"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
                    last_dream = now

                # 4. Periodic Level-1 recalibration
                if now - last_heal >= self.heal_interval:
                    self.kernel.heal_soul_state(level=1, reason="Daemon periodic recalibration")
                    self.stats["heals_run"] += 1
                    self.stats["last_heal"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
                    last_heal = now

            except Exception as exc:
                self.stats["error_count"] += 1
                self.stats["last_error"] = str(exc)
                logging.error(f"[SoulDaemonSupervisor] Error in maintenance cycle: {exc}", exc_info=True)
                time.sleep(min(30.0, 2.0 ** min(5, self.stats["error_count"])))

            time.sleep(1)
