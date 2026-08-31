"""
Soul System Core Kernel v1.2.0 (RPE learning loop + plan-wallet multi-agent subsystem)
Normative Source: docs/CONSTITUTION.md & docs/ARCHITECTURE.md
Features:
 1. Concurrency Hardening: BEGIN IMMEDIATE on writes, PRAGMA user_version migrations, and passive WAL checkpoints
 2. Two-Stage Epistemic Verification Pipeline with strict Epistemic Authority Hierarchy
 3. Native SQLite FTS5 BM25 + dense/hash vector search with Over-Fetched RRF (Top-100 candidate pool)
 4. Bio-Inspired Homeostatic Reward Engine (Dopamine / Cortisol / Serotonergic Decay)
 5. Protected identity plus quarantine episodes; long-term is reviewed_memories after commit
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
from typing import Any, Dict, List, Optional, Tuple, Literal
from dataclasses import dataclass, field, asdict

# Optional Semantica Integration (silently isolate stdout for MCP stdio safety)
try:
    _old_stdout = sys.stdout
    sys.stdout = sys.stderr
    try:
        import semantica
        from semantica.context import ContextGraph
        from semantica.provenance import ProvenanceManager
        HAS_SEMANTICA = True
    finally:
        sys.stdout = _old_stdout
except ImportError:
    HAS_SEMANTICA = False

# Optional PyTorch / Transformers / SentenceTransformers for ML
try:
    from sentence_transformers import SentenceTransformer
    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    HAS_SENTENCE_TRANSFORMERS = False

SOUL_ENGINE_VERSION = "1.2.0"
CONSTITUTION_VERSION = "0.2"
SCHEMA_VERSION = 9
QUARANTINE_RETENTION_DAYS = 30  # ponytail: cliff expiry, not importance decay; per-class windows if privacy demands it

from soul_review import (
    SoulReviewEngine,
    sha256_digest,
    compute_memory_root,
    compute_system_state_hash,
    compute_receipt_hash,
    compute_audit_hash,
    contains_secret,
)

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
TRAIT_EVENT_MAX_DELTA = MAX_STEP_VELOCITY
TRAIT_ROLLING_7D_MAX = 30.0
MIN_EVIDENCE_REFS = 2
HOMEOSTASIS_REWARD_GRACE_SEC = 3600
RECOVER_STALE_HOURS = 24
HEAL_DUE_KEY = "heal_due"
REMEMBER_DUE_KEY = "remember_due"
HEALTH_ID_KEY = "health_id"
REWARD_SOURCES = {"external_test", "external_human", "internal_reflection", "internal_dream"}
INTERNAL_REWARD_SOURCES = {"internal_reflection", "internal_dream"}
HEAL_CORTISOL_FLOOR = 0.5
HEAL_TRAIT_DRIFT = 1.0
DA_RECALL_FLOOR = 0.5
RECALL_LIMIT_STRESS = 3
RECALL_LIMIT_DEFAULT = 5
RECALL_LIMIT_HIGH = 8
DREAM_BUDGET_CHARS = 4000
DREAM_MIN_OUTCOMES = 2
DREAM_SNIPPET_CHARS = 240
DREAM_CANNED_PREFIX = "Simulated hypothetical result for:"
DREAM_LOAD_BEARING_MAX = 5
SOLVER_WORKING_KEY = "solver_working"
SOLVER_OVERLAY_KEY = "solver_overlay"
SOLVER_WORKING_MAX = 40  # ponytail: per-plan FIFO. Global bound if many concurrent plans fill daemon_flags.
SOLVER_OUTCOMES = {"fail", "succeed", "dead_end"}
WALLET_SEP = "\x1f"


def _wallet_key(plan_id: str = "", agent_id: str = "") -> str:
    return f"{(plan_id or '').strip()}{WALLET_SEP}{(agent_id or '').strip()}"


def _empty_wallet(
    plan_id: str = "",
    agent_id: str = "",
    session_id: str = "",
    task_id: str = "",
) -> dict:
    return {
        "dopamine": 0.0,
        "cortisol": 0.0,
        "session_id": (session_id or "").strip(),
        "plan_id": (plan_id or "").strip(),
        "agent_id": (agent_id or "").strip(),
        "task_id": (task_id or "").strip(),
    }


def _trim_working(working: List[dict], plan_id: str) -> List[dict]:
    """FIFO only this plan_id. Other live plans keep their traces for close_plan."""
    pid = plan_id or ""
    idxs = [i for i, s in enumerate(working) if (s.get("plan_id") or "") == pid]
    extra = len(idxs) - SOLVER_WORKING_MAX
    if extra <= 0:
        return working
    drop = set(idxs[:extra])
    return [s for i, s in enumerate(working) if i not in drop]


def _bump_wallet(wallet: dict, *, outcome: str = "", delta: float = 0.0) -> dict:
    da = float(wallet.get("dopamine") or 0.0)
    co = float(wallet.get("cortisol") or 0.0)
    negative = outcome in ("fail", "dead_end") or (not outcome and delta < 0)
    mag = 0.15 if outcome else abs(delta) * 0.15
    drop = 0.1 if outcome else abs(delta) * 0.1
    if negative:
        co = min(1.0, co + mag)
        da = max(0.0, da - drop)
    else:
        da = min(1.0, da + mag)
        co = max(0.0, co - drop)
    out = dict(wallet)
    out["dopamine"] = round(da, 4)
    out["cortisol"] = round(co, 4)
    return out


def _solver_identity_texts(plan_id: str, steps: List[dict]) -> List[Tuple[str, str]]:
    """Compact fail/succeed traces queued for output review. Not soul_states."""
    by_agent: Dict[str, List[dict]] = {}
    for step in steps:
        if (step.get("plan_id") or "") != plan_id:
            continue
        by_agent.setdefault(step.get("agent_id") or "", []).append(step)
    texts: List[Tuple[str, str]] = []
    for aid, rows in by_agent.items():
        bits = []
        for step in rows:
            bit = f"{step.get('outcome')} {step.get('tool')}/{step.get('method')} receipt={step.get('receipt')}"
            if step.get("error"):
                bit += f" error={step['error']}"
            if step.get("options_left") is not None:
                bit += f" options_left={step['options_left']}"
            if step.get("task_id"):
                bit += f" task={step['task_id']}"
            bits.append(bit)
        who = aid or "parent"
        label = plan_id or "(default)"
        body = "; ".join(bits)
        if len(body) > 4000:
            body = body[:3997] + "..."
        texts.append((
            aid,
            f"Solver identity trace plan={label} agent={who}: {body}",
        ))
    return texts


def _hrrl_trait_scale(traits: Dict[str, float]) -> float:
    # ponytail: shrink identity trait shove when far from DEFAULT_TRAITS; DA/cortisol stay the error channels
    errs: List[float] = []
    for trait, (low, high) in ALLOWED_TRAIT_BOUNDS.items():
        span = float(high) - float(low)
        if span <= 0:
            continue
        cur = float(traits.get(trait, DEFAULT_TRAITS.get(trait, 0.0)))
        target = float(DEFAULT_TRAITS.get(trait, cur))
        errs.append(abs(cur - target) / span)
    mean_err = sum(errs) / len(errs) if errs else 0.0
    return max(0.25, round(1.0 - mean_err, 4))


PERCEPT_MEDIA = {"text", "image", "audio", "video", "document", "sensor", "mixed"}
PRIVACY_CLASSES = {"public", "internal", "personal", "sensitive"}
PERCEPT_JSON_MAX_CHARS = 16384
REFLECT_CANNED_HYPOTHESES = (
    "User preference evolution detected.",
    "Contextual domain variation.",
)


def retention_until_from_created(created_at: str) -> str:
    raw = (created_at or "").replace("Z", "+00:00")
    try:
        dt = datetime.datetime.fromisoformat(raw)
    except ValueError:
        dt = datetime.datetime.now(datetime.timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return (dt + datetime.timedelta(days=QUARANTINE_RETENTION_DAYS)).isoformat()


def trait_behavior_lines(traits: Dict[str, float], dopamine: float, cortisol: float) -> List[str]:
    """Orders an agent can obey. Digest is not a dashboard."""
    lines = [
        "Obey sealed active_facts; unreviewed episodes are not long-term memory.",
        "Do not mint origin_kind=human via soul_host_event. Type /seacom in this chat. Picks on the Review plan also commit.",
    ]
    if float(traits.get("sycophancy", 0.0)) <= 5.0:
        lines.append("Low sycophancy: do not flatter; contradict bad ideas.")
    else:
        lines.append("Sycophancy is elevated: still prefer truth over comfort.")
    if float(traits.get("error_anxiety", 0.0)) >= 10.0:
        lines.append("High error anxiety: verify before risky edits.")
    if float(traits.get("audacity", 0.0)) >= 92.0:
        lines.append("High audacity: prefer the sharper fix; still respect SEAL.")
    if float(traits.get("epistemic_humility", 0.0)) >= 90.0:
        lines.append("State uncertainty; do not invent facts.")
    if cortisol >= HEAL_CORTISOL_FLOOR:
        lines.append("High cortisol: slow down; do not take extra risk.")
    if dopamine >= 0.5:
        lines.append("High dopamine: do not overclaim success.")
    return lines

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



@dataclass
class EpisodeInput:
    source_kind: Literal["human", "agent", "environment", "internal"]
    content: str
    provenance: Literal["observed", "reported", "inferred", "imagined", "verified"] = "observed"
    entity_key: Optional[str] = None
    occurred_at: Optional[str] = None
    source_ref: Optional[str] = None
    medium: Optional[str] = None
    privacy_class: Optional[str] = None
    content_ref: Optional[str] = None
    percept_json: Optional[Any] = None
    session_id: Optional[str] = None
    host_event_id: Optional[str] = None


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
    review_receipt: Optional[str] = None
    session_id: str = ""
    plan_id: str = ""
    agent_id: str = ""
    task_id: str = ""


# ------------------------------------------------------------------------------
# BIO-INSPIRED HOMEOSTATIC REWARD ENGINE
# ------------------------------------------------------------------------------
class BioHomeostaticRewardEngine:
    """Regulates dynamic neuromodulation and serotonergic decay.

    Neuromodulator surges follow a Reward Prediction Error rule
    (Rescorla-Wagner; Schultz et al. 1998; cf. arXiv:2603.14597 D-MEM):
    dopamine fires on *surprise* (outcome minus expectation), not raw
    valence, so repeated identical rewards habituate instead of compounding.
    """

    def __init__(self, decay_rate: float = 0.15, rpe_alpha: float = 0.3,
                 rpe_alpha_decay: float = 0.08):
        self.decay_rate = decay_rate
        self.rpe_alpha = rpe_alpha  # base per-context expectation learning rate
        # Robbins-Monro schedule: alpha_n = alpha / (1 + n*decay). Constant-alpha
        # TD never converges on a stationary target (residual noise
        # sigma*sqrt(alpha/(2-alpha))); diminishing rates satisfy stochastic-
        # approximation convergence conditions. Visit counts persist via the
        # `updates` column of rpe_expectations.
        self.rpe_alpha_decay = rpe_alpha_decay
        self.dopamine = 0.0
        self.cortisol = 0.0
        # context bucket -> expected valence*confidence (in-memory cache;
        # durable copy lives in the rpe_expectations table via _load_bio)
        self.expected_valence: Dict[str, float] = {}
        # context bucket -> update count for the alpha schedule (persisted in
        # rpe_expectations.updates under 'n:<ctx>' keys)
        self.visit_counts: Dict[str, int] = {}
        # context bucket -> trust in imagination [0,1]; EWMA of dream accuracy,
        # stored under 'trust:<ctx>' keys in rpe_expectations
        self.dream_trust: Dict[str, float] = {}
        self.stats = {"rewards_processed": 0, "homeostasis_steps": 0}

    def alpha_for(self, ctx: str) -> float:
        """Current Robbins-Monro learning rate for a context bucket."""
        n = self.visit_counts.get(ctx, 0)
        return self.rpe_alpha / (1.0 + n * self.rpe_alpha_decay)

    def trust(self, ctx: str) -> float:
        # imagined = lowest provenance tier -> distrust is the default for
        # contexts WITH dream history. Contexts with NO dream evidence are
        # neutral (1.0): absence of imagination must not slow real learning.
        if ctx not in self.dream_trust:
            return 1.0
        return self.dream_trust[ctx]

    @property
    def serotonin(self) -> float:
        return round(1.0 - max(self.dopamine, self.cortisol), 4)

    def process_reward(self, signal: RewardSignal, current_traits: Dict[str, float]) -> Dict[str, float]:
        valence = float(signal.valence)
        confidence = float(signal.confidence)
        if not (math.isfinite(valence) and math.isfinite(confidence)):
            raise ValueError("reward valence/confidence must be finite numbers")
        valence = max(-1.0, min(1.0, valence))
        confidence = max(0.0, min(1.0, confidence))
        effective_delta = valence * confidence

        # --- RPE gating -------------------------------------------------
        ctx = (signal.task_context or "general").strip().lower()[:64]
        prediction = self.expected_valence.get(ctx, 0.0)
        rpe = effective_delta - prediction
        # 1 on first/novel outcome, ->0 as outcome becomes fully predicted
        novelty = min(1.0, abs(rpe) / max(abs(effective_delta), 1e-9))
        alpha_n = self.alpha_for(ctx)
        self.expected_valence[ctx] = round(
            prediction + alpha_n * (effective_delta - prediction), 4
        )
        self.visit_counts[ctx] = self.visit_counts.get(ctx, 0) + 1

        new_traits = dict(current_traits)
        if effective_delta == 0.0 and rpe == 0.0:
            self.stats["rewards_processed"] += 1
            return new_traits

        gate = novelty * _hrrl_trait_scale(current_traits)
        if rpe > 0:
            # Dopaminergic surge gated by positive prediction error
            self.dopamine = min(1.0, self.dopamine + rpe * 0.4)
            self.cortisol = max(0.0, self.cortisol - rpe * 0.3)

            d_audacity = min(MAX_STEP_VELOCITY, effective_delta * 5.0 * (1.0 + self.dopamine))
            d_curiosity = min(MAX_STEP_VELOCITY, effective_delta * 3.0 * (1.0 + self.dopamine))
            d_anxiety = -effective_delta * 3.0

            new_traits["audacity"] += d_audacity * gate
            new_traits["curiosity"] += d_curiosity * gate
            new_traits["error_anxiety"] += d_anxiety * gate
        else:
            # Cortisol / stress surge gated by negative prediction error
            abs_rpe = abs(rpe)
            self.cortisol = min(1.0, self.cortisol + abs_rpe * 0.5)
            self.dopamine = max(0.0, self.dopamine - abs_rpe * 0.4)

            d_anxiety = min(MAX_STEP_VELOCITY, abs(effective_delta) * 6.0 * (1.0 + self.cortisol))
            d_humility = min(MAX_STEP_VELOCITY, abs(effective_delta) * 4.0 * (1.0 + self.cortisol))
            d_audacity = effective_delta * 5.0

            new_traits["error_anxiety"] += d_anxiety * gate
            new_traits["epistemic_humility"] += d_humility * gate
            new_traits["audacity"] += d_audacity * gate

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
    """Dense vectors via sentence-transformers if installed, else a 384-d hash vector."""

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
                vec = self.model.encode(text)
                return vec.tolist() if hasattr(vec, "tolist") else list(vec)
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
    """Token-overlap heuristic (not a trained NLI model). Returns (entailment, contradiction) in [0, 1]."""

    _NEGATION_MARKERS = {
        "not", "never", "no", "longer", "stopped", "changed", "moved",
        "quit", "away", "deleted", "relocated", "false", "wrong", "instead",
        "differ", "contradict",
    }
    _STOPWORDS = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "to", "of", "in", "on", "at", "and", "or", "for", "with", "that",
        "this", "it", "as", "by", "from", "user",
    }

    def predict(self, premise: str, hypothesis: str) -> Tuple[float, float]:
        """Returns (entailment_score, contradiction_score) bounded in [0.0, 1.0]."""
        prem_tokens = set(re.findall(r"\w+", premise.lower()))
        hyp_tokens = set(re.findall(r"\w+", hypothesis.lower()))

        has_negation = bool(
            (hyp_tokens - prem_tokens) & self._NEGATION_MARKERS
            or (prem_tokens - hyp_tokens) & self._NEGATION_MARKERS
        )
        overlap = len(prem_tokens & hyp_tokens) / max(1, len(prem_tokens | hyp_tokens))
        only_prem = (prem_tokens - hyp_tokens) - self._STOPWORDS - self._NEGATION_MARKERS
        only_hyp = (hyp_tokens - prem_tokens) - self._STOPWORDS - self._NEGATION_MARKERS

        if has_negation and overlap > 0.12:
            return (0.1, 0.90)
        # Same sentence frame with different content fillers (Python vs COBOL).
        if overlap > 0.30 and only_prem and only_hyp:
            return (0.1, 0.90)
        if overlap > 0.40:
            return (0.85, 0.05)
        return (0.2, 0.1)


# ------------------------------------------------------------------------------
# CORE ENGINE
# ------------------------------------------------------------------------------
class SoulKernel:
    """Local identity/memory kernel: quarantine, review, neuromodulators, SQLite ledger."""

    def __init__(self, db_path: str = "soul.db"):
        self.db_path = os.path.abspath(db_path)
        parent = os.path.dirname(self.db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        self._local = threading.local()
        self._lock = threading.RLock()  # ponytail: reentrant so record_host_event can nest under cycle open

        self.vector_engine = VectorEmbeddingEngine()
        self.nli_engine = NLIVerifierEngine()
        self.bio_engine = BioHomeostaticRewardEngine()
        self.review_engine = SoulReviewEngine(self)

        self.daemon_worker: Optional[SoulDaemon] = None

        if HAS_SEMANTICA:
            self.graph = ContextGraph()
            self.prov_mgr = ProvenanceManager()
        else:
            self.graph = None
            self.prov_mgr = None

        self._init_sqlite()
        self._bootstrap_genesis_if_needed()
        self._load_bio()
        self.recover_unsealed_cycles(on_boot=True)

    def get_constitution_hash(self) -> str:
        here = os.path.dirname(os.path.abspath(__file__))
        for const_path in (
            os.path.join(here, "docs", "CONSTITUTION.md"),
            os.path.join(sys.prefix, "share", "soul-engine", "docs", "CONSTITUTION.md"),
        ):
            if os.path.exists(const_path):
                with open(const_path, "rb") as f:
                    return "sha256:" + hashlib.sha256(f.read()).hexdigest()
        return "sha256:ea0d6cbf7f4d91f2cc2ce806851cf9b11f78a29ad9a79a9226470ebb41d4f40f"

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA busy_timeout=30000;")
            self._local.conn = conn
        return self._local.conn

    def close_thread_conn(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    def close(self) -> None:
        self.stop_daemon()
        self.close_thread_conn()

    def _load_bio(self) -> None:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT dopamine, cortisol FROM neuromodulators ORDER BY soul_version DESC LIMIT 1;"
            ).fetchone()
            if not row:
                row = conn.execute(
                    "SELECT dopamine, cortisol FROM soul_states ORDER BY version DESC LIMIT 1;"
                ).fetchone()
        if row:
            self.bio_engine.dopamine = float(row[0] or 0.0)
            self.bio_engine.cortisol = float(row[1] or 0.0)
        # Restore persistent RPE expectations + visit counts (TD value memory
        # and Robbins-Monro schedule survive restarts).
        try:
            for k, v, n in conn.execute(
                "SELECT context_key, expected_value, updates FROM rpe_expectations;"
            ).fetchall():
                key = str(k)
                if key.startswith("trust:"):
                    # legit 0.0 = fully distrusted; only None/missing falls back to 0.5
                    self.bio_engine.dream_trust[key[6:]] = float(v) if v is not None else 0.5
                elif key.startswith("n:"):
                    self.bio_engine.visit_counts[key[2:]] = int(n or 0)
                else:
                    self.bio_engine.expected_valence[key] = float(v or 0.0)
        except sqlite3.OperationalError:
            pass  # pre-migration DB: table created lazily on next _init_sqlite run

    def _persist_bio(self, conn: sqlite3.Connection) -> None:
        ver = conn.execute("SELECT MAX(version) FROM soul_states;").fetchone()[0]
        if ver is None:
            return
        da = float(self.bio_engine.dopamine)
        co = float(self.bio_engine.cortisol)
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        try:
            cur = conn.execute(
                "SELECT COUNT(*) FROM rpe_expectations;"
            )
            have_rpe_table = True
        except sqlite3.OperationalError:
            have_rpe_table = False
        if not have_rpe_table:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS rpe_expectations (
                    context_key TEXT PRIMARY KEY,
                    expected_value REAL NOT NULL DEFAULT 0,
                    updates INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                );
            """)
        for k, v in self.bio_engine.expected_valence.items():
            n = self.bio_engine.visit_counts.get(k, 0)
            conn.execute(
                """INSERT INTO rpe_expectations (context_key, expected_value, updates, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(context_key) DO UPDATE SET
                     expected_value = excluded.expected_value,
                     updates = excluded.updates,
                     updated_at = excluded.updated_at;""",
                (str(k)[:64], round(float(v), 6), int(n), now_iso),
            )
        for k, v in self.bio_engine.dream_trust.items():
            conn.execute(
                """INSERT INTO rpe_expectations (context_key, expected_value, updates, updated_at)
                   VALUES (?, ?, 1, ?)
                   ON CONFLICT(context_key) DO UPDATE SET
                     expected_value = excluded.expected_value,
                     updated_at = excluded.updated_at;""",
                ("trust:" + str(k)[:57], round(float(v), 6), now_iso),
            )
        conn.execute(
            """INSERT INTO neuromodulators (soul_version, dopamine, cortisol, serotonin, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(soul_version) DO UPDATE SET
                 dopamine = excluded.dopamine,
                 cortisol = excluded.cortisol,
                 serotonin = excluded.serotonin,
                 updated_at = excluded.updated_at;""",
            (
                ver,
                da,
                co,
                round(1.0 - max(da, co), 4),
                datetime.datetime.now(datetime.timezone.utc).isoformat(),
            ),
        )

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

                # Alter existing tables if needed for Schema v5
                def ensure_col(table: str, col_def: str):
                    cname = col_def.split()[0]
                    cur.execute(f"PRAGMA table_info({table});")
                    existing = {row[1] for row in cur.fetchall()}
                    if cname not in existing:
                        cur.execute(f"ALTER TABLE {table} ADD COLUMN {col_def};")

                ensure_col("episodes", "session_id TEXT")
                ensure_col("episodes", "host_event_id TEXT")
                ensure_col("episodes", "review_cycle_id TEXT")
                ensure_col("episodes", "content_hash_salt TEXT")
                ensure_col("episodes", "deleted_at TEXT")
                ensure_col("episodes", "deletion_receipt_ref TEXT")
                ensure_col("episodes", "occurred_at TEXT")
                ensure_col("episodes", "source_ref TEXT")
                ensure_col("episodes", "medium TEXT")
                ensure_col("episodes", "privacy_class TEXT")
                ensure_col("episodes", "content_ref TEXT")
                ensure_col("episodes", "percept_json TEXT")
                ensure_col("episodes", "retention_until TEXT")

                ensure_col("soul_states", "constitution_hash TEXT")
                ensure_col("soul_states", "prior_state_hash TEXT")
                # v6 leftover columns; v7 source of truth is neuromodulators
                ensure_col("soul_states", "dopamine REAL NOT NULL DEFAULT 0")
                ensure_col("soul_states", "cortisol REAL NOT NULL DEFAULT 0")

                ensure_col("audit_ledger", "previous_audit_hash TEXT")
                ensure_col("audit_ledger", "audit_hash TEXT")

                conn.execute("""
                CREATE TABLE IF NOT EXISTS neuromodulators (
                    soul_version INTEGER PRIMARY KEY,
                    dopamine REAL NOT NULL DEFAULT 0,
                    cortisol REAL NOT NULL DEFAULT 0,
                    serotonin REAL NOT NULL DEFAULT 1,
                    updated_at TEXT NOT NULL
                );
                """)
                copied = conn.execute("SELECT COUNT(*) FROM neuromodulators;").fetchone()[0]
                if copied == 0:
                    conn.execute("""
                    INSERT INTO neuromodulators (soul_version, dopamine, cortisol, serotonin, updated_at)
                    SELECT version,
                           COALESCE(dopamine, 0),
                           COALESCE(cortisol, 0),
                           ROUND(1.0 - MAX(COALESCE(dopamine, 0), COALESCE(cortisol, 0)), 4),
                           created_at
                    FROM soul_states;
                    """)

                # Persistent RPE expectations (Schultz-style TD value memory).
                # ponytail: one JSON blob, not per-context rows — contexts are capped
                # at 64 chars and few dozen in practice; split to a table if it grows.
                ensure_col("dream_simulations", "task_context TEXT NOT NULL DEFAULT ''")
                ensure_col("dream_simulations", "rpe_delta REAL")
                cur.execute("""
                CREATE TABLE IF NOT EXISTS rpe_expectations (
                    context_key TEXT PRIMARY KEY,
                    expected_value REAL NOT NULL DEFAULT 0,
                    updates INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                );
                """)

                # Schema v5 Review Tables
                conn.executescript("""
                CREATE TABLE IF NOT EXISTS host_events (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    user_scope_key TEXT NOT NULL,
                    project_scope_key TEXT,
                    sequence INTEGER NOT NULL,
                    origin_kind TEXT NOT NULL,
                    event_kind TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    payload_hash_salt TEXT,
                    previous_event_hash TEXT,
                    event_hash TEXT NOT NULL UNIQUE,
                    occurred_at TEXT NOT NULL,
                    consumed_at TEXT,
                    payload_redacted_at TEXT,
                    auth_sig TEXT
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_host_events_session_sequence ON host_events(session_id, sequence);
                CREATE INDEX IF NOT EXISTS idx_host_events_user_occurred ON host_events(user_scope_key, occurred_at);

                CREATE TABLE IF NOT EXISTS review_cycles (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    user_scope_key TEXT NOT NULL,
                    project_scope_key TEXT,
                    status TEXT NOT NULL,
                    trigger_kind TEXT NOT NULL,
                    watermark_event_id TEXT NOT NULL,
                    watermark_sequence INTEGER NOT NULL,
                    base_soul_state_hash TEXT NOT NULL,
                    base_memory_set_version INTEGER NOT NULL,
                    base_memory_root TEXT NOT NULL,
                    base_system_state_hash TEXT NOT NULL,
                    provisional INTEGER NOT NULL DEFAULT 0,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    opened_at TEXT NOT NULL,
                    prepared_at TEXT,
                    sealed_at TEXT,
                    invalidated_at TEXT,
                    preview_json TEXT,
                    preview_hash TEXT,
                    preview_hash_salt TEXT,
                    preview_created_at TEXT,
                    preview_redacted_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_review_cycles_session_status ON review_cycles(session_id, status);
                CREATE INDEX IF NOT EXISTS idx_review_cycles_user_opened ON review_cycles(user_scope_key, opened_at);

                CREATE TABLE IF NOT EXISTS memory_candidates (
                    id TEXT PRIMARY KEY,
                    user_scope_key TEXT NOT NULL,
                    cycle_id TEXT NOT NULL,
                    candidate_type TEXT NOT NULL,
                    canonical_text TEXT,
                    original_provenance TEXT NOT NULL,
                    source_episode_refs_json TEXT NOT NULL,
                    source_host_event_refs_json TEXT NOT NULL,
                    supporting_refs_json TEXT NOT NULL,
                    contradicting_refs_json TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    sensitivity TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    status TEXT NOT NULL,
                    candidate_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    revises_candidate_id TEXT,
                    created_from_human_event_ref TEXT,
                    candidate_hash_salt TEXT,
                    payload_redacted_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_candidates_cycle_status ON memory_candidates(cycle_id, status);
                CREATE INDEX IF NOT EXISTS idx_candidates_user_type ON memory_candidates(user_scope_key, candidate_type);

                CREATE TABLE IF NOT EXISTS review_decisions (
                    id TEXT PRIMARY KEY,
                    user_scope_key TEXT NOT NULL,
                    cycle_id TEXT NOT NULL,
                    candidate_id TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    human_event_ref TEXT NOT NULL,
                    decision_hash TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    decided_at TEXT NOT NULL,
                    result_candidate_id TEXT,
                    correction_confirmation_event_ref TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_decisions_cycle_candidate ON review_decisions(cycle_id, candidate_id);
                CREATE INDEX IF NOT EXISTS idx_decisions_human_event ON review_decisions(human_event_ref);

                CREATE TABLE IF NOT EXISTS reviewed_memories (
                    id TEXT PRIMARY KEY,
                    canonical_text TEXT,
                    memory_type TEXT NOT NULL,
                    provenance TEXT NOT NULL,
                    retention_state TEXT NOT NULL DEFAULT 'accessible',
                    scope TEXT NOT NULL,
                    owner_user_scope_key TEXT NOT NULL,
                    scope_key TEXT NOT NULL,
                    source_episode_refs_json TEXT NOT NULL,
                    review_decision_ref TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    content_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    supersedes_memory_id TEXT,
                    content_hash_salt TEXT,
                    deleted_at TEXT,
                    deletion_receipt_ref TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_reviewed_memories_owner_retention ON reviewed_memories(owner_user_scope_key, retention_state);
                CREATE INDEX IF NOT EXISTS idx_reviewed_memories_scope ON reviewed_memories(scope, scope_key);

                CREATE TABLE IF NOT EXISTS memory_set_versions (
                    version INTEGER NOT NULL,
                    owner_user_scope_key TEXT NOT NULL,
                    prior_version INTEGER,
                    prior_memory_root TEXT,
                    memory_root TEXT NOT NULL,
                    cycle_id TEXT,
                    receipt_ref TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (owner_user_scope_key, version)
                );
                CREATE INDEX IF NOT EXISTS idx_memory_set_versions_owner ON memory_set_versions(owner_user_scope_key, version DESC);

                CREATE TABLE IF NOT EXISTS memory_set_members (
                    owner_user_scope_key TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    memory_id TEXT NOT NULL,
                    memory_content_hash TEXT NOT NULL,
                    PRIMARY KEY (owner_user_scope_key, version, memory_id)
                );
                CREATE INDEX IF NOT EXISTS idx_memory_set_members_memory ON memory_set_members(memory_id);

                CREATE TABLE IF NOT EXISTS memory_change_receipts (
                    id TEXT PRIMARY KEY,
                    previous_receipt_hash TEXT,
                    owner_user_scope_key TEXT NOT NULL,
                    operation_kind TEXT NOT NULL,
                    cycle_id TEXT,
                    operation_hash TEXT NOT NULL,
                    preview_hash TEXT,
                    authority_event_hash TEXT NOT NULL,
                    constitution_hash TEXT NOT NULL,
                    watermark_event_id TEXT,
                    watermark_sequence INTEGER,
                    prior_soul_state_hash TEXT NOT NULL,
                    result_soul_state_hash TEXT NOT NULL,
                    prior_memory_set_version INTEGER NOT NULL,
                    result_memory_set_version INTEGER NOT NULL,
                    prior_memory_root TEXT NOT NULL,
                    result_memory_root TEXT NOT NULL,
                    prior_system_state_hash TEXT NOT NULL,
                    result_system_state_hash TEXT NOT NULL,
                    rollback_reference TEXT NOT NULL,
                    affected_memory_ids_json TEXT NOT NULL,
                    candidate_decision_summary_json TEXT NOT NULL,
                    receipt_hash TEXT NOT NULL UNIQUE,
                    committed_at TEXT NOT NULL,
                    cleanup_state TEXT NOT NULL DEFAULT 'not_required',
                    cleanup_completed_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_receipts_owner_committed ON memory_change_receipts(owner_user_scope_key, committed_at DESC);
                CREATE INDEX IF NOT EXISTS idx_receipts_cycle ON memory_change_receipts(cycle_id);
                """)

                # Initialize FTS5 Tables
                try:
                    conn.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS episodes_fts USING fts5(
                        content,
                        episode_id UNINDEXED,
                        tokenize='unicode61'
                    );
                    """)
                    conn.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS reviewed_memories_fts USING fts5(
                        canonical_text,
                        memory_id UNINDEXED,
                        tokenize='unicode61'
                    );
                    """)
                except Exception as exc:
                    logging.warning(f"FTS5 initialization notice: {exc}")

                conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION};")
                conn.commit()

            # Always ensure so existing DBs get additive Phase 4 objects (independent of schema bump).
            conn.execute("""
            CREATE TABLE IF NOT EXISTS daemon_flags (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS trait_drift_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trait TEXT NOT NULL,
                old_value REAL NOT NULL,
                new_value REAL NOT NULL,
                source TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """)
            ep_cols = {row[1] for row in conn.execute("PRAGMA table_info(episodes);")}
            if "retention_until" not in ep_cols:
                conn.execute("ALTER TABLE episodes ADD COLUMN retention_until TEXT;")
            host_cols = {row[1] for row in conn.execute("PRAGMA table_info(host_events);")}
            if "auth_sig" not in host_cols:
                try:
                    conn.execute("ALTER TABLE host_events ADD COLUMN auth_sig TEXT;")
                except sqlite3.OperationalError:
                    pass
            for eid, created in conn.execute(
                "SELECT id, created_at FROM episodes WHERE retention_until IS NULL AND deleted_at IS NULL;"
            ).fetchall():
                conn.execute(
                    "UPDATE episodes SET retention_until = ? WHERE id = ?;",
                    (retention_until_from_created(created), eid),
                )
            try:
                conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS episodes_fts USING fts5(
                    content, episode_id UNINDEXED, tokenize='unicode61'
                );
                """)
                conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS reviewed_memories_fts USING fts5(
                    canonical_text, memory_id UNINDEXED, tokenize='unicode61'
                );
                """)
            except Exception as exc:
                logging.warning(f"FTS5 initialization notice: {exc}")
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
                const_hash = self.get_constitution_hash()

                cur.execute("""
                INSERT INTO soul_states (version, constitution_version, traits_json, narrative, unresolved_tensions_json, state_hash, created_at, constitution_hash, prior_state_hash)
                VALUES (1, ?, ?, ?, ?, ?, ?, ?, NULL);
                """, (CONSTITUTION_VERSION, traits_json, narrative, tensions_json, state_hash, created_at, const_hash))

                self._record_audit(conn, 1, "genesis_bootstrap", {"traits": DEFAULT_TRAITS}, state_hash)
                self._persist_bio(conn)
                conn.commit()

    def _record_audit(self, conn: sqlite3.Connection, version: int, action_type: str, payload: dict, state_hash: str):
        """Append an immutable audit entry with atomic transaction guarantees and hash chain."""
        audit_id = f"audit_{int(datetime.datetime.now().timestamp()*1000)}_{uuid.uuid4().hex[:8]}"
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        payload_str = json.dumps(payload)

        cur = conn.cursor()
        cur.execute("SELECT audit_hash FROM audit_ledger ORDER BY timestamp DESC LIMIT 1;")
        prev_row = cur.fetchone()
        prev_audit_hash = prev_row[0] if (prev_row and prev_row[0]) else None

        prov_checksum = state_hash
        if self.prov_mgr:
            try:
                entry = self.prov_mgr.track_entity(entity_id=audit_id, source="soul_kernel", metadata={"type": "SoulStateChange"})
                prov_checksum = getattr(entry, "checksum", state_hash)
            except Exception:
                prov_checksum = state_hash

        audit_h = compute_audit_hash(
            previous_audit_hash=prev_audit_hash,
            audit_id=audit_id,
            soul_version=version,
            action_type=action_type,
            payload_json=payload_str,
            prov_checksum=prov_checksum,
            timestamp=timestamp
        )

        conn.execute("""
        INSERT INTO audit_ledger (id, soul_version, action_type, payload_json, prov_checksum, timestamp, previous_audit_hash, audit_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """, (audit_id, version, action_type, payload_str, prov_checksum, timestamp, prev_audit_hash, audit_h))

    def _log_trait_drift(
        self,
        conn: sqlite3.Connection,
        source: str,
        old_traits: Dict[str, float],
        new_traits: Dict[str, float],
        *,
        old_da: Optional[float] = None,
        old_co: Optional[float] = None,
    ) -> None:
        # ponytail: append-only; not recall. Forget this log with Agent 26 if it grows.
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        def _row(trait: str, ov: float, nv: float) -> None:
            if float(ov) == float(nv):
                return
            conn.execute(
                "INSERT INTO trait_drift_log (trait, old_value, new_value, source, created_at) VALUES (?, ?, ?, ?, ?);",
                (trait, float(ov), float(nv), source, now),
            )
        for name in ALLOWED_TRAIT_BOUNDS:
            _row(name, float(old_traits.get(name, DEFAULT_TRAITS[name])), float(new_traits.get(name, DEFAULT_TRAITS[name])))
        if old_da is not None:
            _row("dopamine", old_da, self.bio_engine.dopamine)
        if old_co is not None:
            _row("cortisol", old_co, self.bio_engine.cortisol)

    # --------------------------------------------------------------------------
    # MODULE 1 & 2: Policy Gate & Experience Ingestor
    # --------------------------------------------------------------------------
    @staticmethod
    def _encode_percept_json(raw: Any) -> Optional[str]:
        if raw is None or raw == "":
            return None
        text = json.dumps(raw, ensure_ascii=False) if isinstance(raw, (dict, list)) else str(raw)
        if len(text) > PERCEPT_JSON_MAX_CHARS:
            raise ValueError(f"percept_json exceeds {PERCEPT_JSON_MAX_CHARS} chars")
        return text

    @staticmethod
    def _percept_claim_strings(percept_text: Optional[str]) -> List[str]:
        if not percept_text:
            return []
        try:
            obj = json.loads(percept_text)
        except (json.JSONDecodeError, TypeError):
            return []
        claims = obj.get("claims") if isinstance(obj, dict) else None
        out: List[str] = []
        if isinstance(claims, list):
            for c in claims:
                if isinstance(c, str) and c.strip():
                    out.append(c.strip())
                elif isinstance(c, dict):
                    t = c.get("text") or c.get("claim") or c.get("content")
                    if t and str(t).strip():
                        out.append(str(t).strip())
        return out

    def _insert_quarantine_episode(self, conn: sqlite3.Connection, ep: EpisodeInput) -> dict:
        """Insert one quarantined episode on an open write txn. Caller owns BEGIN/COMMIT."""
        percept_text = self._encode_percept_json(ep.percept_json)
        if contains_secret(ep.content) or (percept_text and contains_secret(percept_text)):
            raise ValueError("SECURITY REJECTION: Input contains credentials or private keys. Write blocked under Section 3.3.")
        episode_id = f"ep_{int(datetime.datetime.now().timestamp()*1000)}_{uuid.uuid4().hex[:8]}"
        created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        occurred_at = (ep.occurred_at or "").strip() or created_at
        retention_until = retention_until_from_created(created_at)
        checksum = hashlib.sha256(f"{ep.source_kind}|{ep.provenance}|{ep.content}|{created_at}".encode()).hexdigest()
        embedding_json = json.dumps(self.vector_engine.embed(ep.content))
        cur = conn.cursor()
        cur.execute("""
        INSERT INTO episodes (id, source_kind, provenance, content, entity_key, trust_state, embedding_json, checksum, created_at, occurred_at, source_ref, medium, privacy_class, content_ref, percept_json, retention_until, session_id, host_event_id)
        VALUES (?, ?, ?, ?, ?, 'quarantined', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (episode_id, ep.source_kind, ep.provenance, ep.content, ep.entity_key, embedding_json, checksum, created_at, occurred_at, ep.source_ref, ep.medium, ep.privacy_class, ep.content_ref, percept_text, retention_until, (ep.session_id or "").strip() or None, (ep.host_event_id or "").strip() or None))
        try:
            cur.execute("INSERT INTO episodes_fts (content, episode_id) VALUES (?, ?);", (ep.content, episode_id))
        except Exception:
            pass
        self._write_flag_sql(conn, REMEMBER_DUE_KEY, "0")
        return {
            "episode_id": episode_id,
            "status": "quarantined",
            "provenance": ep.provenance,
            "checksum": checksum,
        }

    def ingest_experience(self, ep: EpisodeInput) -> dict:
        """Screen credentials, generate dense embeddings & store into Quarantine Memory."""
        if ep.medium is not None and ep.medium not in PERCEPT_MEDIA:
            raise ValueError(f"medium must be one of {sorted(PERCEPT_MEDIA)}")
        if ep.privacy_class is not None and ep.privacy_class not in PRIVACY_CLASSES:
            raise ValueError(f"privacy_class must be one of {sorted(PRIVACY_CLASSES)}")
        percept_text = self._encode_percept_json(ep.percept_json)
        if contains_secret(ep.content) or (percept_text and contains_secret(percept_text)):
            raise ValueError("SECURITY REJECTION: Input contains credentials or private keys. Write blocked under Section 3.3.")

        episode_id = f"ep_{int(datetime.datetime.now().timestamp()*1000)}_{uuid.uuid4().hex[:8]}"
        created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        occurred_at = (ep.occurred_at or "").strip() or created_at
        retention_until = retention_until_from_created(created_at)
        checksum = hashlib.sha256(f"{ep.source_kind}|{ep.provenance}|{ep.content}|{created_at}".encode()).hexdigest()

        # Compute embeddings outside SQLite transaction
        embedding_vec = self.vector_engine.embed(ep.content)
        embedding_json = json.dumps(embedding_vec)

        with self._lock, self._get_conn() as conn:
            if self._flag_value_from_conn(conn, "quarantine_frozen") == "1":
                raise PermissionError("quarantine frozen (heal level 3); ingest blocked until L2 rollback")
            conn.execute("BEGIN IMMEDIATE;")
            cur = conn.cursor()
            if ep.entity_key:
                cur.execute(
                    """SELECT id, provenance FROM episodes
                       WHERE entity_key = ? AND trust_state NOT IN ('superseded', 'expired')
                         AND id NOT IN (
                           SELECT j.value FROM reviewed_memories r, json_each(r.source_episode_refs_json) j
                           WHERE r.retention_state = 'accessible' AND r.deleted_at IS NULL
                         );""",
                    (ep.entity_key,),
                )
                existing_entries = cur.fetchall()
                new_prio = PROVENANCE_HIERARCHY.get(ep.provenance, 1)
                for old_id, old_prov in existing_entries:
                    old_prio = PROVENANCE_HIERARCHY.get(old_prov, 1)
                    if new_prio >= old_prio:
                        cur.execute("UPDATE episodes SET trust_state = 'superseded' WHERE id = ?;", (old_id,))

            cur.execute("""
            INSERT INTO episodes (id, source_kind, provenance, content, entity_key, trust_state, embedding_json, checksum, created_at, occurred_at, source_ref, medium, privacy_class, content_ref, percept_json, retention_until, session_id, host_event_id)
            VALUES (?, ?, ?, ?, ?, 'quarantined', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (episode_id, ep.source_kind, ep.provenance, ep.content, ep.entity_key, embedding_json, checksum, created_at, occurred_at, ep.source_ref, ep.medium, ep.privacy_class, ep.content_ref, percept_text, retention_until, (ep.session_id or "").strip() or None, (ep.host_event_id or "").strip() or None))

            # Update FTS5 Index
            try:
                cur.execute("INSERT INTO episodes_fts (content, episode_id) VALUES (?, ?);", (ep.content, episode_id))
            except Exception:
                pass

            self._write_flag_sql(conn, REMEMBER_DUE_KEY, "0")
            conn.commit()
        if self.daemon_worker is not None:
            self.daemon_worker.stats["remember_due"] = False

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
            cur.execute("SELECT content, provenance, entity_key, percept_json FROM episodes WHERE id = ?;", (episode_id,))
            target = cur.fetchone()
            if not target:
                return {"error": f"Episode {episode_id} not found"}
            content, provenance, entity_key, percept_json = target[0], target[1], target[2], target[3]
        claims = self._percept_claim_strings(percept_json)
        hypotheses = [content] + claims
        query_text = " ".join(h for h in hypotheses if h).strip() or content

        # Stage 1: sealed facts plus quarantined episodes (quarantine-only recall skips reviewed_memories)
        sealed = self.recall_memories(query=query_text, limit=5, search_mode="dense", include_quarantined=False)
        quarantined = self.recall_memories(query=query_text, limit=5, search_mode="dense", include_quarantined=True)
        merged: List[dict] = []
        seen_ids = set()
        for cand in list(sealed) + list(quarantined):
            key = cand.get("memory_id") or cand.get("episode_id")
            if not key or key in seen_ids:
                continue
            seen_ids.add(key)
            merged.append(cand)
        candidates = merged

        corroborating = []
        contradicting = []
        new_priority = PROVENANCE_HIERARCHY.get(provenance, 1)

        # Stage 2: Targeted NLI evaluation (episode content plus percept_json.claims)
        for cand in candidates:
            cid = cand.get("episode_id") or cand.get("memory_id")
            if cid == episode_id:
                continue
            entailed = False
            contradicted = False
            for hyp in hypotheses:
                entailment, contradiction = self.nli_engine.predict(premise=cand["content"], hypothesis=hyp)
                if contradiction >= 0.60:
                    contradicted = True
                elif entailment >= 0.60:
                    entailed = True
            if contradicted:
                contradicting.append(cand)
            elif entailed:
                corroborating.append(cid)

        new_state = "corroborated" if corroborating else "quarantined"
        superseded_refs = []
        sealed_hit = False

        if contradicting:
            # Precedence rules, order-independent:
            #   1. any sealed/reviewed contradiction -> contradicted (always)
            #   2. else any same-or-higher-tier contradiction -> contradicted
            #   3. else only lower-tier ones -> corroborated + supersede them
            sealed_hit = any(
                c.get("source_kind") == "reviewed"
                or str(c.get("episode_id") or c.get("memory_id")).startswith("rmem_")
                for c in contradicting)
            lower_refs = [
                c.get("episode_id") or c.get("memory_id") for c in contradicting
                if not (c.get("source_kind") == "reviewed"
                        or str(c.get("episode_id") or c.get("memory_id")).startswith("rmem_"))
                and new_priority > PROVENANCE_HIERARCHY.get(c["provenance"], 1)]
            if sealed_hit:
                new_state = "contradicted"
                superseded_refs = [s for s in lower_refs if str(s).startswith("ep_")]
            elif any(new_priority <= PROVENANCE_HIERARCHY.get(c["provenance"], 1)
                     for c in contradicting):
                new_state = "contradicted"
            else:
                new_state = "corroborated"
                superseded_refs = lower_refs

        with self._lock, self._get_conn() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            conn.execute("UPDATE episodes SET trust_state = ? WHERE id = ?;", (new_state, episode_id))

            for old_id in superseded_refs:
                if str(old_id).startswith("ep_"):
                    conn.execute("UPDATE episodes SET trust_state = 'superseded' WHERE id = ?;", (old_id,))

            if new_state == "contradicted":
                # ponytail: tensions live in daemon_flags so verify cannot mint a soul_states row
                tensions = list(self._tensions_from_conn(conn, []))
                contra_ids = [c.get("episode_id") or c.get("memory_id") for c in contradicting]
                tension_entry = f"Epistemic conflict between episode {episode_id} and refs {contra_ids}"
                if tension_entry not in tensions:
                    tensions.append(tension_entry)
                    self._write_flag_sql(conn, "unresolved_tensions", json.dumps(tensions))
                    self._write_dream_due_sql(conn, True)

            self._persist_bio(conn)
            conn.commit()

        return {
            "episode_id": episode_id,
            "trust_state": new_state,
            "corroborating_refs": corroborating,
            "contradicting_refs": [c.get("episode_id") or c.get("memory_id") for c in contradicting],
            "superseded_refs": superseded_refs
        }

    # --------------------------------------------------------------------------
    # RETRIEVAL API: OVER-FETCHED RECIPROCAL RANK FUSION (RRF) & QUARANTINE ISOLATION
    # --------------------------------------------------------------------------
    def recall_memories(
        self,
        query: str = "",
        limit: int = 5,
        search_mode: str = "rrf_hybrid",
        user_scope_key: str = "default_user",
        include_quarantined: bool = False,
        overlay: Optional[dict] = None,
        plan_id: str = "",
        agent_id: str = "",
        session_id: str = "",
    ):
        # ponytail: EILS caps reviewed recall; quarantine dumps stay uncapped for review/debug
        if include_quarantined:
            limit = max(1, int(limit))
        else:
            limit = self._policy_recall_limit(
                limit, overlay=overlay, plan_id=plan_id, agent_id=agent_id
            )
        eff_session_id = session_id or (overlay.get("session_id") if overlay else "") or ""
        empty = not (query or "").strip()
        with self._get_conn() as conn:
            cur = conn.cursor()
            # 1. Check for active reviewed memories
            if eff_session_id:
                scope_cond = "AND (IFNULL(m.scope, '') != 'session_only' OR (m.scope = 'session_only' AND m.scope_key = ?))"
                rev_params: List[Any] = [user_scope_key, eff_session_id, user_scope_key]
            else:
                scope_cond = "AND IFNULL(m.scope, '') != 'session_only'"
                rev_params: List[Any] = [user_scope_key, user_scope_key]

            rev_sql = f"""
            SELECT m.id, 'reviewed' as source_kind, m.provenance, m.canonical_text, m.scope_key, 'active' as trust_state, m.created_at
            FROM memory_set_members mem
            JOIN reviewed_memories m ON mem.memory_id = m.id
            JOIN memory_set_versions v ON mem.owner_user_scope_key = v.owner_user_scope_key AND mem.version = v.version
            WHERE mem.owner_user_scope_key = ? AND m.retention_state = 'accessible'
              {scope_cond}
              AND IFNULL(m.provenance, '') != 'imagined'
              AND v.version = (SELECT MAX(v2.version) FROM memory_set_versions v2 WHERE v2.owner_user_scope_key = ?)
            ORDER BY m.created_at DESC
            """
            if empty and not include_quarantined:
                rev_sql += " LIMIT ?"
                rev_params.append(limit)
            cur.execute(rev_sql, rev_params)
            rev_rows = cur.fetchall()

            if not include_quarantined:
                doc_list = [
                    {
                        "memory_id": r[0],
                        "source_kind": r[1],
                        "provenance": r[2],
                        "content": r[3],
                        "scope_key": r[4],
                        "trust_state": r[5],
                        "embedding": None,
                        "created_at": r[6]
                    }
                    for r in rev_rows
                ]
            else:
                ep_sql = """
                SELECT id, source_kind, provenance, content, entity_key, trust_state, embedding_json, created_at
                FROM episodes WHERE trust_state NOT IN ('superseded', 'contradicted', 'expired') AND deleted_at IS NULL
                  AND IFNULL(provenance, '') != 'imagined'
                ORDER BY created_at DESC
                """
                # ponytail: hard ceiling so quarantine recall can't load an
                # unbounded episode table into RAM; raise deliberately if needed.
                scan_cap = max(limit * 20, 2000)
                cur.execute(ep_sql + " LIMIT ?", (scan_cap,))
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

        if not doc_list:
            return []

        if not query:
            return doc_list[:limit]

        # 1. Dense Vector Scoring (Top-100 candidate retrieval)
        query_vec = self.vector_engine.embed(query)
        dense_scored = []
        for d in doc_list:
            d_vec = d.get("embedding") or self.vector_engine.embed(d["content"])
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
                    # Match the FTS table to the doc_list actually built above:
                    # reviewed docs come from memory_set_members, quarantined/raw
                    # docs from episodes. Querying the other table yields zero
                    # intersections and silently degrades to the lexical fallback.
                    use_reviewed = bool(doc_list) and "memory_id" in doc_list[0]
                    fts_table = "reviewed_memories_fts" if use_reviewed else "episodes_fts"
                    id_col = "memory_id" if use_reviewed else "episode_id"
                    cur.execute(f"""
                    SELECT {id_col}, bm25({fts_table}) FROM {fts_table}
                    WHERE {fts_table} MATCH ? ORDER BY rank LIMIT 100;
                    """, (clean_q,))
                    fts_hits = {r[0]: r[1] for r in cur.fetchall()}
                    key_fn = (lambda x: x.get("memory_id") or x.get("episode_id"))
                    doc_map = {key_fn(d): d for d in doc_list}
                    fts_ranked = [doc_map[k] for k in fts_hits if k in doc_map]
        except Exception:
            fts_ranked = []

        if not fts_ranked:
            # Fallback simple lexical matching
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
        key_fn = (lambda x: x.get("memory_id") or x.get("episode_id"))

        for rank, d in enumerate(dense_ranked):
            item_key = key_fn(d)
            rrf_scores[item_key] = rrf_scores.get(item_key, 0.0) + (0.6 / (k + rank + 1.0))

        for rank, d in enumerate(fts_ranked):
            item_key = key_fn(d)
            rrf_scores[item_key] = rrf_scores.get(item_key, 0.0) + (0.4 / (k + rank + 1.0))

        doc_lookup = {key_fn(d): d for d in doc_list}
        sorted_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)
        return [doc_lookup[eid] for eid in sorted_ids if eid in doc_lookup][:limit]

    # --------------------------------------------------------------------------
    # SOUL REVIEW CYCLE WORKFLOW METHODS
    # --------------------------------------------------------------------------
    def record_host_event(
        self,
        session_id: str,
        user_scope_key: str = "default_user",
        project_scope_key: Optional[str] = None,
        origin_kind: str = "agent",
        event_kind: str = "conversation",
        payload: Any = "",
        auth_sig: Optional[str] = None,
    ) -> Any:
        return self.review_engine.record_host_event(
            session_id=session_id,
            user_scope_key=user_scope_key,
            project_scope_key=project_scope_key,
            origin_kind=origin_kind,
            event_kind=event_kind,
            payload=payload,
            auth_sig=auth_sig,
        )

    def _get_admin_key(self) -> Optional[str]:
        env_key = os.environ.get("SOUL_ADMIN_KEY")
        if env_key:
            return env_key.strip()
        env_path = os.environ.get("SOUL_ADMIN_KEY_PATH")
        if env_path and os.path.exists(env_path):
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    return f.read().strip()
            except Exception:
                pass
        if hasattr(self, "db_path") and self.db_path and self.db_path != ":memory:":
            db_dir_key = os.path.join(os.path.dirname(os.path.abspath(self.db_path)), "admin.key")
            if os.path.exists(db_dir_key):
                try:
                    with open(db_dir_key, "r", encoding="utf-8") as f:
                        return f.read().strip()
                except Exception:
                    pass
        key_path = os.path.join(os.path.expanduser("~"), ".soul", "admin.key")
        if os.path.exists(key_path):
            try:
                with open(key_path, "r", encoding="utf-8") as f:
                    return f.read().strip()
            except Exception:
                return None
        return None

    def verify_human_event_signature(self, event_id: str) -> bool:
        admin_key = self._get_admin_key()
        require_admin_key = os.environ.get("SOUL_REQUIRE_ADMIN_KEY", "").strip().lower() in ("1", "true", "yes")
        if not admin_key:
            return not require_admin_key
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT session_id, user_scope_key, project_scope_key, event_kind, payload_hash, occurred_at, auth_sig, origin_kind FROM host_events WHERE id = ?;",
                (event_id,)
            ).fetchone()
        if not row:
            return False
        session_id, user_scope_key, project_scope_key, event_kind, payload_hash, occurred_at, auth_sig, origin_kind = row
        if origin_kind != "human":
            return False
        if not auth_sig:
            return False
        import hmac
        from soul_review import compute_human_event_hmac
        expected = compute_human_event_hmac(
            admin_key=admin_key,
            event_id=event_id,
            session_id=session_id,
            user_scope_key=user_scope_key,
            project_scope_key=project_scope_key,
            event_kind=event_kind,
            payload_hash=payload_hash,
            occurred_at=occurred_at,
        )
        return hmac.compare_digest(auth_sig, expected)

    def verify_audit_ledger(self) -> dict:
        """
        Verifies cryptographic integrity of audit_ledger and soul_states chains.
        """
        from soul_review import compute_audit_hash
        with self._get_conn() as conn:
            # 1. Verify audit ledger chain
            audit_rows = conn.execute(
                "SELECT id, soul_version, action_type, payload_json, prov_checksum, timestamp, previous_audit_hash, audit_hash FROM audit_ledger ORDER BY timestamp ASC, id ASC;"
            ).fetchall()
            prev_hash = None
            for row in audit_rows:
                aid, ver, action, p_json, p_chk, ts, p_hash, stored_hash = row
                if p_hash != prev_hash:
                    return {
                        "valid": False,
                        "error": f"Audit hash chain broken at entry id={aid}: expected previous_audit_hash='{prev_hash}', got '{p_hash}'",
                    }
                computed = compute_audit_hash(
                    previous_audit_hash=prev_hash,
                    audit_id=str(aid),
                    soul_version=ver,
                    action_type=action,
                    payload_json=p_json,
                    prov_checksum=p_chk,
                    timestamp=ts,
                )
                if stored_hash != computed:
                    return {
                        "valid": False,
                        "error": f"Audit entry hash mismatch at id={aid}: stored '{stored_hash}', computed '{computed}'",
                    }
                prev_hash = stored_hash

            # 2. Verify soul states hash chain
            state_rows = conn.execute(
                "SELECT version, state_hash, prior_state_hash FROM soul_states ORDER BY version ASC;"
            ).fetchall()
            prev_state_hash = None
            for idx, s_row in enumerate(state_rows):
                s_ver, s_hash, s_prior = s_row
                if idx == 0:
                    prev_state_hash = s_hash
                    continue
                if s_prior and s_prior != prev_state_hash:
                    return {
                        "valid": False,
                        "error": f"Soul state chain broken at version {s_ver}: expected prior_state_hash='{prev_state_hash}', got '{s_prior}'",
                    }
                prev_state_hash = s_hash

        return {
            "valid": True,
            "audit_entries_checked": len(audit_rows),
            "soul_states_checked": len(state_rows),
        }

    def start_review_cycle(
        self,
        session_id: str,
        user_scope_key: str = "default_user",
        project_scope_key: Optional[str] = None,
        trigger_kind: str = "explicit",
        provisional: bool = False,
        idempotency_key: Optional[str] = None
    ) -> dict:
        cycle = self.review_engine.open_or_get_cycle(
            session_id=session_id,
            user_scope_key=user_scope_key,
            project_scope_key=project_scope_key,
            trigger_kind=trigger_kind,
            provisional=provisional,
            idempotency_key=idempotency_key
        )
        candidates = self.review_engine.extract_candidates_from_episodes(
            cycle_id=cycle.id,
            user_scope_key=user_scope_key
        )
        cycle = self.review_engine.get_cycle_by_id(cycle.id) or cycle
        cand_dicts = [asdict(c) for c in candidates]
        return {
            "cycle_id": cycle.id,
            "status": cycle.status,
            "stage": cycle.status,
            "trigger_kind": cycle.trigger_kind,
            "watermark_sequence": cycle.watermark_sequence,
            "base_memory_set_version": cycle.base_memory_set_version,
            "candidate_count": len(candidates),
            "candidates": cand_dicts
        }

    def get_review_status(self, session_id: str) -> Optional[dict]:
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
            SELECT id, status, watermark_sequence, base_memory_set_version, preview_hash
            FROM review_cycles
            WHERE session_id = ? AND status NOT IN ('committed', 'sealed_no_changes', 'invalidated')
            ORDER BY opened_at DESC LIMIT 1;
            """, (session_id,))
            row = cur.fetchone()
            if not row:
                cur.execute("""
                SELECT id, status, watermark_sequence, base_memory_set_version, preview_hash
                FROM review_cycles WHERE session_id = ?
                ORDER BY opened_at DESC LIMIT 1;
                """, (session_id,))
                row = cur.fetchone()
            if not row:
                return None
            cycle_id, status, watermark_seq, base_mem_ver, preview_hash = row
            pending = self.review_engine.get_pending_candidates(cycle_id)
            cand_dicts = [asdict(c) for c in pending]
            return {
                "cycle_id": cycle_id,
                "status": status,
                "stage": status,
                "watermark_sequence": watermark_seq,
                "base_memory_set_version": base_mem_ver,
                "preview_hash": preview_hash,
                "candidate_count": len(pending),
                "candidates": cand_dicts,
                "pending_candidates_count": len(pending),
                "pending_candidates": cand_dicts
            }

    def record_review_decision(
        self,
        cycle_id: str,
        candidate_id: str,
        decision: str,
        human_event_ref: str,
        user_scope_key: str = "default_user",
        corrected_text: Optional[str] = None,
        correction_confirmation_event_ref: Optional[str] = None
    ) -> dict:
        dec = self.review_engine.record_human_decision(
            cycle_id=cycle_id,
            candidate_id=candidate_id,
            decision=decision,
            human_event_ref=human_event_ref,
            user_scope_key=user_scope_key,
            corrected_text=corrected_text,
            correction_confirmation_event_ref=correction_confirmation_event_ref
        )
        return asdict(dec)

    def preview_review_cycle(self, cycle_id: str) -> dict:
        return self.review_engine.generate_cycle_preview(cycle_id=cycle_id)

    def commit_review_cycle(self, cycle_id: str, commit_human_event_ref: str) -> dict:
        return self.review_engine.commit_review_cycle(
            cycle_id=cycle_id,
            commit_human_event_ref=commit_human_event_ref
        )

    def apply_chat_review(
        self,
        session_id: str,
        cycle_id: str,
        decisions: List[dict],
        user_scope_key: str = "default_user",
        project_scope_key: Optional[str] = None,
    ) -> dict:
        # ponytail: MCP can call this without a tty; any caller can promote. soul_host if you need keyboard proof.
        if not session_id or not cycle_id:
            raise ValueError("session_id and cycle_id are required")
        if not isinstance(decisions, list) or not decisions:
            raise ValueError("decisions must be a non-empty list")
        cycle = self.review_engine.get_cycle_by_id(cycle_id)
        if cycle and cycle.session_id and cycle.session_id != session_id:
            raise ValueError("session_id does not match the review cycle")
        if cycle and cycle.status == "committed":
            preview = json.loads(cycle.preview_json) if cycle.preview_json else {}
            return {
                "preview": preview,
                "receipt": self.review_engine._committed_receipt(cycle_id),
                "decisions": [],
            }
        staged = []
        promoting = []
        for item in decisions:
            if not isinstance(item, dict):
                raise ValueError("each decision must be an object")
            cand_id = item.get("candidate_id")
            decision = item.get("decision")
            if not cand_id or not decision:
                raise ValueError("candidate_id and decision are required")
            ev = self.record_host_event(
                session_id=session_id,
                user_scope_key=user_scope_key,
                project_scope_key=project_scope_key,
                origin_kind="human",
                event_kind="review_decision",
                payload=item,
            )
            corr = item.get("corrected_text")
            confirm_ref = None
            if decision == "correct":
                confirm_ev = self.record_host_event(
                    session_id=session_id,
                    user_scope_key=user_scope_key,
                    project_scope_key=project_scope_key,
                    origin_kind="human",
                    event_kind="review_decision",
                    payload={"corrected_text": corr},
                )
                confirm_ref = confirm_ev.id
            staged.append(self.record_review_decision(
                cycle_id=cycle_id,
                candidate_id=cand_id,
                decision=decision,
                human_event_ref=ev.id,
                user_scope_key=user_scope_key,
                corrected_text=corr,
                correction_confirmation_event_ref=confirm_ref,
            ))
            if decision != "defer":
                promoting.append(item)
        if not promoting:
            return {"preview": None, "receipt": None, "decisions": staged, "status": "deferred"}
        preview = self.preview_review_cycle(cycle_id)
        commit_ev = self.record_host_event(
            session_id=session_id,
            user_scope_key=user_scope_key,
            project_scope_key=project_scope_key,
            origin_kind="human",
            event_kind="review_commit",
            payload={"preview_hash": preview.get("preview_hash"), "cycle_id": cycle_id},
        )
        receipt = self.commit_review_cycle(cycle_id, commit_ev.id)
        return {"preview": preview, "receipt": receipt, "decisions": staged}

    def _chat_human_event(
        self,
        session_id: str,
        event_kind: str,
        payload: Any,
        user_scope_key: str = "default_user",
        project_scope_key: Optional[str] = None,
    ):
        if not session_id:
            raise ValueError("session_id is required")

        # Security Policy (Issue #14): Gate destructive Tier 2 operations.
        # Tier 1 (review_commit, review_decision, level-1 heal) is permitted in-band.
        # Tier 2 (destructive state rollback, memory deletion, level>=2 heal) requires out-of-band authorization.
        if event_kind in {"memory_rollback", "memory_deletion", "identity_rollback"}:
            raise PermissionError(
                f"Security Policy: Destructive operation '{event_kind}' cannot be authorized "
                f"in-band via chat session. Requires out-of-band human_event_ref from soul_host."
            )
        if event_kind == "session_lifecycle" and isinstance(payload, dict):
            op = payload.get("op")
            level = payload.get("level", 1)
            if op == "rollback" or (op == "heal" and level >= 2):
                raise PermissionError(
                    f"Security Policy: Destructive operation '{op}' (level={level}) cannot be authorized "
                    f"in-band via chat session. Requires out-of-band human_event_ref from soul_host."
                )

        return self.record_host_event(
            session_id=session_id,
            user_scope_key=user_scope_key,
            project_scope_key=project_scope_key,
            origin_kind="human",
            event_kind=event_kind,
            payload=payload,
        )

    def apply_chat_heal(self, session_id: str, level: int = 1, reason: str = "chat heal") -> dict:
        self._chat_human_event(session_id, "session_lifecycle", {"op": "heal", "level": level, "reason": reason})
        return self.heal_soul_state(level=level, reason=reason)

    def apply_chat_identity_rollback(self, session_id: str, target_version: int, reason: str = "chat rollback"):
        self._chat_human_event(session_id, "session_lifecycle", {"op": "rollback", "target_version": target_version, "reason": reason})
        return self.rollback_to_version(int(target_version), operator_reason=reason)

    def apply_chat_memory_rollback(self, session_id: str, target_version: int, user_scope_key: str = "default_user") -> dict:
        ev = self._chat_human_event(session_id, "memory_rollback", {"target_version": target_version})
        return self.rollback_reviewed_memory_set(
            target_version=int(target_version),
            human_event_ref=ev.id,
            user_scope_key=user_scope_key,
        )

    def apply_chat_memory_delete(self, session_id: str, memory_id: str, user_scope_key: str = "default_user") -> dict:
        ev = self._chat_human_event(session_id, "memory_deletion", {"memory_id": memory_id})
        return self.delete_reviewed_memory(
            memory_id=memory_id,
            human_event_ref=ev.id,
            user_scope_key=user_scope_key,
        )

    def recover_unsealed_cycles(self, user_scope_key: Optional[str] = None, *, on_boot: bool = False) -> List[str]:
        return self.review_engine.recover_unsealed_cycles(user_scope_key=user_scope_key, on_boot=on_boot)

    def invalidate_provisional_cycle(self, cycle_id: str) -> dict:
        return self.review_engine.invalidate_provisional_cycle(cycle_id=cycle_id)

    def list_active_reviewed_memories(
        self,
        user_scope_key: str = "default_user",
        project_scope_key: Optional[str] = None
    ) -> List[dict]:
        return self.review_engine.list_active_reviewed_memories(
            user_scope_key=user_scope_key,
            project_scope_key=project_scope_key
        )

    def rollback_reviewed_memory_set(
        self,
        target_version: int,
        human_event_ref: str,
        user_scope_key: str = "default_user"
    ) -> dict:
        """
        Rollback active memory set to a prior version (Forward-Only Rollback).
        Creates a new version pointing to target_version members and emits a cryptographic receipt.
        """
        with self._lock, self._get_conn() as conn:
            cur = conn.cursor()
            # Verify human authority
            cur.execute(
                "SELECT origin_kind, event_hash, event_kind, user_scope_key, consumed_at FROM host_events WHERE id = ?;",
                (human_event_ref,)
            )
            ev_row = cur.fetchone()
            if not ev_row or ev_row[0] != "human":
                raise PermissionError("Rollback requires human host event authority")
            if ev_row[4]:
                raise PermissionError("Security Policy: Tier-2 authorization event has already been consumed.")
            if ev_row[2] in ("review_decision", "review_commit"):
                raise PermissionError(f"Security Policy: Tier-2 operation rejected. Chat review event kind '{ev_row[2]}' cannot authorize memory rollback.")
            if ev_row[3] and ev_row[3] != user_scope_key:
                raise PermissionError("Security Policy: Scope mismatch for memory rollback.")
            if not self.verify_human_event_signature(human_event_ref):
                raise PermissionError("Security Policy: Tier-2 operation rejected. Invalid or missing signature on human event.")
            auth_event_hash = ev_row[1]

            # Get target version members
            cur.execute("""
            SELECT memory_id, memory_content_hash
            FROM memory_set_members
            WHERE owner_user_scope_key = ? AND version = ?;
            """, (user_scope_key, target_version))
            target_members = cur.fetchall()
            if not target_members and target_version != 0:
                raise ValueError(f"Target memory set version {target_version} does not exist")

            # Get current latest version
            cur.execute("""
            SELECT version, memory_root FROM memory_set_versions
            WHERE owner_user_scope_key = ? ORDER BY version DESC LIMIT 1;
            """, (user_scope_key,))
            latest = cur.fetchone()
            current_ver = latest[0] if latest else 0
            prior_mem_root = latest[1] if latest else compute_memory_root(user_scope_key, [])

            cur.execute("SELECT state_hash FROM soul_states ORDER BY version DESC LIMIT 1;")
            s_row = cur.fetchone()
            soul_state_hash = s_row[0] if s_row else "sha256:0"
            const_hash = self.get_constitution_hash()
            prior_sys_hash = compute_system_state_hash(soul_state_hash, prior_mem_root, const_hash)

            new_ver = current_ver + 1
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            member_dicts = [{"memory_id": m[0], "memory_content_hash": m[1]} for m in target_members]
            new_mem_root = compute_memory_root(user_scope_key, member_dicts)
            new_sys_hash = compute_system_state_hash(soul_state_hash, new_mem_root, const_hash)

            receipt_id = f"rcpt_roll_{int(datetime.datetime.now().timestamp()*1000)}_{uuid.uuid4().hex[:8]}"
            cur.execute("SELECT receipt_hash FROM memory_change_receipts WHERE owner_user_scope_key = ? ORDER BY committed_at DESC LIMIT 1;", (user_scope_key,))
            prev_rcpt = cur.fetchone()
            prev_rcpt_hash = prev_rcpt[0] if prev_rcpt else None

            op_hash = sha256_digest({"action": "rollback", "target_version": target_version})
            receipt_hash = compute_receipt_hash(
                previous_receipt_hash=prev_rcpt_hash,
                owner_user_scope_key=user_scope_key,
                operation_kind="rollback",
                cycle_id=None,
                operation_hash=op_hash,
                preview_hash=None,
                authority_event_hash=auth_event_hash,
                constitution_hash=const_hash,
                watermark_event_id=None,
                watermark_sequence=None,
                prior_soul_state_hash=soul_state_hash,
                result_soul_state_hash=soul_state_hash,
                prior_memory_set_version=current_ver,
                result_memory_set_version=new_ver,
                prior_memory_root=prior_mem_root,
                result_memory_root=new_mem_root,
                prior_system_state_hash=prior_sys_hash,
                result_system_state_hash=new_sys_hash,
                rollback_reference=str(target_version),
                affected_memory_ids=[m[0] for m in target_members],
                candidate_decision_summary={"target_version": target_version},
                committed_at=now_iso
            )

            conn.execute("BEGIN IMMEDIATE;")
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
                receipt_id, prev_rcpt_hash, user_scope_key, "rollback",
                None, op_hash, None, auth_event_hash,
                const_hash, None, None,
                soul_state_hash, soul_state_hash,
                current_ver, new_ver,
                prior_mem_root, new_mem_root,
                prior_sys_hash, new_sys_hash,
                str(target_version), json.dumps([m[0] for m in target_members]),
                json.dumps({"target_version": target_version}), receipt_hash, now_iso
            ))

            cur.execute("""
            INSERT INTO memory_set_versions (
                version, owner_user_scope_key, prior_version, prior_memory_root,
                memory_root, cycle_id, receipt_ref, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """, (new_ver, user_scope_key, current_ver, prior_mem_root, new_mem_root, None, receipt_id, now_iso))

            for m in target_members:
                cur.execute("""
                INSERT INTO memory_set_members (owner_user_scope_key, version, memory_id, memory_content_hash)
                VALUES (?, ?, ?, ?);
                """, (user_scope_key, new_ver, m[0], m[1]))

            cur.execute("UPDATE host_events SET consumed_at = ? WHERE id = ?;", (now_iso, human_event_ref))
            conn.commit()

        return {
            "status": "rolled_back",
            "new_version": new_ver,
            "target_version": target_version,
            "memory_root": new_mem_root,
            "receipt_id": receipt_id,
            "receipt_hash": receipt_hash
        }

    def delete_reviewed_memory(
        self,
        memory_id: str,
        human_event_ref: str,
        user_scope_key: str = "default_user"
    ) -> dict:
        """
        Delete a reviewed memory under Salted Privacy Deletion Cascade (Section 13).
        - Redacts canonical_text to NULL
        - Cascades redaction to source episodes and candidates
        - Increments memory_set_versions excluding the memory
        - Emits cryptographic deletion receipt
        """
        with self._lock, self._get_conn() as conn:
            cur = conn.cursor()
            # Verify human authority
            cur.execute(
                "SELECT origin_kind, event_hash, event_kind, user_scope_key, consumed_at FROM host_events WHERE id = ?;",
                (human_event_ref,)
            )
            ev_row = cur.fetchone()
            if not ev_row or ev_row[0] != "human":
                raise PermissionError("Deletion requires human host event authority")
            if ev_row[4]:
                raise PermissionError("Security Policy: Tier-2 authorization event has already been consumed.")
            if ev_row[2] in ("review_decision", "review_commit"):
                raise PermissionError(f"Security Policy: Tier-2 operation rejected. Chat review event kind '{ev_row[2]}' cannot authorize memory deletion.")
            if ev_row[3] and ev_row[3] != user_scope_key:
                raise PermissionError("Security Policy: Scope mismatch for memory deletion.")
            if not self.verify_human_event_signature(human_event_ref):
                raise PermissionError("Security Policy: Tier-2 operation rejected. Invalid or missing signature on human event.")
            auth_event_hash = ev_row[1]

            # Fetch memory
            cur.execute("""
            SELECT source_episode_refs_json, content_hash, canonical_text
            FROM reviewed_memories
            WHERE id = ? AND owner_user_scope_key = ?;
            """, (memory_id, user_scope_key))
            mem_row = cur.fetchone()
            if not mem_row:
                raise ValueError(f"Memory {memory_id} not found")

            source_eps = json.loads(mem_row[0]) if mem_row[0] else []
            orig_text = mem_row[2] or ""
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            receipt_id = f"rcpt_del_{int(datetime.datetime.now().timestamp()*1000)}_{uuid.uuid4().hex[:8]}"

            # Get current latest version
            cur.execute("""
            SELECT version, memory_root FROM memory_set_versions
            WHERE owner_user_scope_key = ? ORDER BY version DESC LIMIT 1;
            """, (user_scope_key,))
            latest = cur.fetchone()
            current_ver = latest[0] if latest else 0
            prior_mem_root = latest[1] if latest else compute_memory_root(user_scope_key, [])

            # Active members minus memory_id
            cur.execute("""
            SELECT memory_id, memory_content_hash
            FROM memory_set_members
            WHERE owner_user_scope_key = ? AND version = ? AND memory_id != ?;
            """, (user_scope_key, current_ver, memory_id))
            remaining_members = cur.fetchall()

            new_ver = current_ver + 1
            member_dicts = [{"memory_id": m[0], "memory_content_hash": m[1]} for m in remaining_members]
            new_mem_root = compute_memory_root(user_scope_key, member_dicts)

            cur.execute("SELECT state_hash FROM soul_states ORDER BY version DESC LIMIT 1;")
            s_row = cur.fetchone()
            soul_state_hash = s_row[0] if s_row else "sha256:0"
            const_hash = self.get_constitution_hash()
            prior_sys_hash = compute_system_state_hash(soul_state_hash, prior_mem_root, const_hash)
            new_sys_hash = compute_system_state_hash(soul_state_hash, new_mem_root, const_hash)

            cur.execute("SELECT receipt_hash FROM memory_change_receipts WHERE owner_user_scope_key = ? ORDER BY committed_at DESC LIMIT 1;", (user_scope_key,))
            prev_rcpt = cur.fetchone()
            prev_rcpt_hash = prev_rcpt[0] if prev_rcpt else None

            op_hash = sha256_digest({"action": "delete", "memory_id": memory_id})
            receipt_hash = compute_receipt_hash(
                previous_receipt_hash=prev_rcpt_hash,
                owner_user_scope_key=user_scope_key,
                operation_kind="deletion",
                cycle_id=None,
                operation_hash=op_hash,
                preview_hash=None,
                authority_event_hash=auth_event_hash,
                constitution_hash=const_hash,
                watermark_event_id=None,
                watermark_sequence=None,
                prior_soul_state_hash=soul_state_hash,
                result_soul_state_hash=soul_state_hash,
                prior_memory_set_version=current_ver,
                result_memory_set_version=new_ver,
                prior_memory_root=prior_mem_root,
                result_memory_root=new_mem_root,
                prior_system_state_hash=prior_sys_hash,
                result_system_state_hash=new_sys_hash,
                rollback_reference=str(current_ver),
                affected_memory_ids=[memory_id],
                candidate_decision_summary={"deleted_memory_id": memory_id},
                committed_at=now_iso
            )

            conn.execute("BEGIN IMMEDIATE;")
            # 1. Redact reviewed memory and erase salt (GDPR Salted Erasure Section 7.2)
            cur.execute("""
            UPDATE reviewed_memories
            SET canonical_text = '[REDACTED]',
                content_hash_salt = NULL,
                retention_state = 'deleted',
                deleted_at = ?,
                deletion_receipt_ref = ?
            WHERE id = ?;
            """, (now_iso, receipt_id, memory_id))
            cur.execute("DELETE FROM reviewed_memories_fts WHERE memory_id = ?;", (memory_id,))

            # 2. Redact source episodes
            for ep_id in source_eps:
                cur.execute("""
                UPDATE episodes
                SET content = '[REDACTED]',
                    embedding_json = NULL,
                    percept_json = NULL,
                    deleted_at = ?,
                    deletion_receipt_ref = ?
                WHERE id = ?;
                """, (now_iso, receipt_id, ep_id))
                cur.execute("DELETE FROM episodes_fts WHERE episode_id = ?;", (ep_id,))
                cur.execute(
                    """UPDATE memory_candidates SET canonical_text = '[REDACTED]'
                       WHERE id IN (
                         SELECT mc.id FROM memory_candidates mc, json_each(mc.source_episode_refs_json) j
                         WHERE j.value = ?
                       );""",
                    (ep_id,),
                )
            if orig_text:
                cur.execute(
                    "UPDATE memory_candidates SET canonical_text = '[REDACTED]' WHERE canonical_text = ?;",
                    (orig_text,),
                )

            if orig_text:
                for cid, pj in cur.execute(
                    "SELECT id, preview_json FROM review_cycles WHERE preview_json IS NOT NULL;"
                ).fetchall():
                    if orig_text in (pj or ""):
                        cur.execute(
                            "UPDATE review_cycles SET preview_json = ? WHERE id = ?;",
                            (pj.replace(orig_text, "[REDACTED]"), cid),
                        )

            # 3. Insert receipt
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
                receipt_id, prev_rcpt_hash, user_scope_key, "deletion",
                None, op_hash, None, auth_event_hash,
                const_hash, None, None,
                soul_state_hash, soul_state_hash,
                current_ver, new_ver,
                prior_mem_root, new_mem_root,
                prior_sys_hash, new_sys_hash,
                str(current_ver), json.dumps([memory_id]),
                json.dumps({"deleted_memory_id": memory_id}), receipt_hash, now_iso
            ))

            # 4. Insert memory set version & members
            cur.execute("""
            INSERT INTO memory_set_versions (
                version, owner_user_scope_key, prior_version, prior_memory_root,
                memory_root, cycle_id, receipt_ref, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """, (new_ver, user_scope_key, current_ver, prior_mem_root, new_mem_root, None, receipt_id, now_iso))

            for m in remaining_members:
                cur.execute("""
                INSERT INTO memory_set_members (owner_user_scope_key, version, memory_id, memory_content_hash)
                VALUES (?, ?, ?, ?);
                """, (user_scope_key, new_ver, m[0], m[1]))

            cur.execute("UPDATE host_events SET consumed_at = ? WHERE id = ?;", (now_iso, human_event_ref))
            conn.commit()

        return {
            "status": "deleted",
            "memory_id": memory_id,
            "new_version": new_ver,
            "receipt_id": receipt_id,
            "receipt_hash": receipt_hash
        }

    # --------------------------------------------------------------------------
    # MODULE 4 & 5: Reflection & Dream Sandbox
    # --------------------------------------------------------------------------
    @staticmethod
    def _clip_text(text: str, limit: int) -> str:
        text = (text or "").strip()
        if len(text) <= limit:
            return text
        return text[: max(0, limit - 1)] + "…"

    def _tension_evidence(self, tensions: List[str]) -> List[dict]:
        ids: List[str] = []
        for t in tensions:
            ids.extend(re.findall(r"ep_\d+_[0-9a-f]+", t))
        if not ids:
            return []
        uniq = list(dict.fromkeys(ids))
        qmarks = ",".join("?" * len(uniq))
        with self._get_conn() as conn:
            rows = conn.execute(
                f"SELECT id, content, trust_state FROM episodes WHERE id IN ({qmarks});",
                uniq,
            ).fetchall()
        return [
            {"episode_id": r[0], "content": self._clip_text(r[1], DREAM_SNIPPET_CHARS), "trust_state": r[2]}
            for r in rows
        ]

    def _dream_context_packet(self, scenario_prompt: str) -> dict:
        state = self.get_current_state()
        facts = []
        load_bearing: List[dict] = []
        seen: set = set()
        budget = {"used": 0}

        def take(text: str) -> str:
            remain = DREAM_BUDGET_CHARS - budget["used"]
            clipped = self._clip_text(text, min(DREAM_SNIPPET_CHARS, max(0, remain)))
            budget["used"] += len(clipped)
            return clipped

        for t in (state.unresolved_tensions or [])[:DREAM_LOAD_BEARING_MAX]:
            if budget["used"] >= DREAM_BUDGET_CHARS:
                break
            load_bearing.append({
                "kind": "tension",
                "text": take(t),
            })
        region_q = (scenario_prompt or "").strip() or (
            (state.unresolved_tensions or [""])[0]
        )
        for m in self.recall_memories(query=region_q, limit=self._policy_recall_limit()):
            if budget["used"] >= DREAM_BUDGET_CHARS:
                break
            mid = m.get("memory_id") or m.get("episode_id")
            if not mid or mid in seen:
                continue
            seen.add(mid)
            snippet = take(m.get("content") or "")
            facts.append({"memory_id": mid, "content": snippet})
            if len(load_bearing) < DREAM_LOAD_BEARING_MAX:
                item = {"kind": "fact", "id": mid}
                key = m.get("entity_key") or m.get("scope_key")
                if key:
                    item["entity_key"] = key
                load_bearing.append(item)
        analogical = []
        for m in self.recall_memories(query=scenario_prompt or region_q, limit=self._policy_recall_limit()):
            if budget["used"] >= DREAM_BUDGET_CHARS:
                break
            mid = m.get("memory_id") or m.get("episode_id")
            if not mid or mid in seen:
                continue
            seen.add(mid)
            analogical.append({
                "memory_id": mid,
                "content": take(m.get("content") or ""),
            })
        return {
            "status": "needs_thought",
            "scenario_prompt": scenario_prompt,
            "budget": {
                "max_chars": DREAM_BUDGET_CHARS,
                "min_outcomes": DREAM_MIN_OUTCOMES,
                "used_chars": budget["used"],
            },
            "narrative": self._clip_text(state.narrative, DREAM_SNIPPET_CHARS),
            "tensions": state.unresolved_tensions,
            "traits": state.traits,
            "reviewed_facts": facts,
            "load_bearing": load_bearing[:DREAM_LOAD_BEARING_MAX],
            "analogical_cases": analogical,
            "invariants": [
                "no network or actuators",
                "provenance=imagined",
                "does not write identity or reviewed_memories",
            ],
        }

    def reflect_and_resolve(self, interpretations: Optional[List[Any]] = None) -> dict:
        state = self.get_current_state()
        tensions = list(state.unresolved_tensions or [])
        if not tensions:
            return {
                "status": "empty",
                "tensions_analyzed": [],
                "evidence": [],
                "interpretations": [],
                "recommended_action": "none",
            }

        evidence = self._tension_evidence(tensions)
        parsed: List[dict] = []
        for item in interpretations or []:
            if isinstance(item, str) and item.strip():
                parsed.append({"hypothesis": item.strip(), "confidence": 0.5, "action": "none"})
            elif isinstance(item, dict) and str(item.get("hypothesis") or "").strip():
                parsed.append({
                    "hypothesis": str(item["hypothesis"]).strip(),
                    "confidence": float(item.get("confidence", 0.5)),
                    "action": str(item.get("action") or "none"),
                })

        if not parsed:
            return {
                "status": "needs_thought",
                "tensions_analyzed": tensions,
                "evidence": evidence,
                "interpretations": [],
                "recommended_action": None,
            }

        for p in parsed:
            if p["hypothesis"] in REFLECT_CANNED_HYPOTHESES:
                raise ValueError("canned reflection hypothesis rejected")

        recommended = parsed[0].get("action") or "none"
        reflection_id = f"refl_{int(datetime.datetime.now().timestamp()*1000)}_{uuid.uuid4().hex[:8]}"
        created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._lock, self._get_conn() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            conn.execute("""
            INSERT INTO reflections (id, tensions_analyzed_json, interpretations_json, recommended_action, created_at)
            VALUES (?, ?, ?, ?, ?);
            """, (reflection_id, json.dumps(tensions), json.dumps(parsed), recommended, created_at))
            self._write_flag_sql(conn, "unresolved_tensions", json.dumps([]))
            conn.commit()

        return {
            "status": "recorded",
            "reflection_id": reflection_id,
            "tensions_analyzed": tensions,
            "evidence": evidence,
            "interpretations": parsed,
            "recommended_action": recommended,
        }

    def _parse_dream_branches(self, outcomes: Optional[List[Any]]) -> List[dict]:
        branches: List[dict] = []
        for item in outcomes or []:
            if isinstance(item, str) and item.strip():
                branches.append({"outcome": self._clip_text(item, DREAM_BUDGET_CHARS)})
                continue
            if not isinstance(item, dict):
                continue
            text = str(item.get("outcome") or item.get("text") or "").strip()
            if not text:
                continue
            branch: dict = {"outcome": self._clip_text(text, DREAM_BUDGET_CHARS)}
            flipped = item.get("variable_flipped") or item.get("hypothesis")
            if flipped:
                branch["variable_flipped"] = str(flipped).strip()
            if item.get("name"):
                branch["name"] = str(item["name"]).strip()
            if item.get("likelihood") is not None:
                branch["likelihood"] = float(item["likelihood"])
            if item.get("severity") is not None:
                branch["severity"] = str(item["severity"]).strip()
            branches.append(branch)
        return branches

    def run_dream_simulation(
        self,
        scenario_prompt: str = "",
        outcomes: Optional[List[Any]] = None,
        task_context: str = "",
    ) -> dict:
        branches = self._parse_dream_branches(outcomes)
        if not branches:
            return self._dream_context_packet(scenario_prompt)

        if len(branches) < DREAM_MIN_OUTCOMES:
            raise ValueError(f"need at least {DREAM_MIN_OUTCOMES} imagined outcomes")
        per = max(1, DREAM_BUDGET_CHARS // len(branches))
        for b in branches:
            b["outcome"] = self._clip_text(b.get("outcome") or "", per)
        texts = [b["outcome"] for b in branches]
        if any(t.startswith(DREAM_CANNED_PREFIX) for t in texts):
            raise ValueError("canned dream outcome rejected")

        dream_id = f"dream_{int(datetime.datetime.now().timestamp()*1000)}_{uuid.uuid4().hex[:8]}"
        created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        simulated_outcome = json.dumps(branches, ensure_ascii=False)
        ctx = (task_context or "").strip().lower()[:64]

        with self._lock, self._get_conn() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            conn.execute("""
            INSERT INTO dream_simulations (id, scenario_prompt, simulated_outcome, provenance, tag, created_at, task_context, rpe_delta)
            VALUES (?, ?, ?, 'imagined', 'no_external_action', ?, ?, NULL);
            """, (dream_id, scenario_prompt, simulated_outcome, created_at, ctx))
            self._write_dream_due_sql(conn, False)
            conn.commit()
        if self.daemon_worker is not None:
            self.daemon_worker.stats["dream_due"] = False

        return {
            "status": "recorded",
            "dream_id": dream_id,
            "scenario_prompt": scenario_prompt,
            "outcomes": texts,
            "branches": branches,
            "simulated_outcome": simulated_outcome,
            "provenance": "imagined",
            "tag": "no_external_action",
            "task_context": ctx,
        }

    def score_dreams_against_reality(
        self,
        realized_valence: float,
        confidence: float = 1.0,
        task_context: str = "",
        limit: int = 5,
        evidence_receipt: str = "",
    ) -> dict:
        """Close the dream loop (cf. Overfitted Brain hypothesis, arXiv:2403.07979).

        Compares the most recent unscored dreams in a context against the *realized*
        outcome that just arrived via a receipted external signal. Each dream's
        predicted valence (mean branch severity-weighted sign) is differenced against
        reality -> a dream-RPE. The dream-RPE updates the same persistent expectation
        table the bio engine uses, so imagination calibrates prediction like real
        experience does. Dreams stay provenance='imagined' and never touch identity.

        Requires the evidence receipt of a *redeemed* external_test reward in this
        same task context — dream scoring may not be driven by unbacked claims.
        """
        realized = float(realized_valence)
        conf = float(confidence)
        if not (math.isfinite(realized) and math.isfinite(conf)):
            raise ValueError("realized_valence/confidence must be finite numbers")
        realized = max(-1.0, min(1.0, realized))
        conf = max(0.0, min(1.0, conf))
        effective = realized * conf
        ctx = (task_context or "").strip().lower()[:64]

        rid = (evidence_receipt or "").strip()
        if not rid:
            raise ValueError(
                "dream scoring requires evidence_receipt of a redeemed external_test "
                "reward for this task_context")
        with self._lock, self._get_conn() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            anchor = conn.execute(
                """SELECT payload_json FROM audit_ledger
                   WHERE action_type = 'bio_reward' 
                     AND json_extract(payload_json, '$.evidence_receipt') = ?
                   ORDER BY timestamp DESC LIMIT 1;""",
                (rid,),
            ).fetchone()
            if not anchor:
                raise ValueError(
                    f"evidence_receipt {rid!r} does not match any redeemed external_test reward")
            try:
                anchored_ctx = (json.loads(anchor[0]).get("task_context") or "").strip().lower()[:64]
            except Exception:
                anchored_ctx = ""
            if ctx and anchored_ctx and anchored_ctx != ctx:
                raise ValueError(
                    f"receipt context {anchored_ctx!r} != scoring context {ctx!r}")
            conn.rollback()  # read-only probe; close before scoring tx below
            # Context-matched replay: an outcome only scores dreams imagined for
            # the SAME task bucket (or dreams with no bucket). Prevents stale
            # cross-context mis-attribution (found by calibration harness).
            if ctx:
                rows = conn.execute(
                    """SELECT id, simulated_outcome, task_context FROM dream_simulations
                       WHERE provenance = 'imagined' AND rpe_delta IS NULL
                         AND (task_context = ? OR task_context = '')
                       ORDER BY created_at DESC LIMIT ?;""",
                    (ctx, max(1, min(int(limit), 20))),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT id, simulated_outcome, task_context FROM dream_simulations
                       WHERE provenance = 'imagined' AND rpe_delta IS NULL
                       ORDER BY created_at DESC LIMIT ?;""",
                    (max(1, min(int(limit), 20)),),
                ).fetchall()

            scored = []
            for did, blob, row_ctx in rows:
                try:
                    branches = json.loads(blob or "[]")
                except Exception:
                    branches = []
                # Predicted valence: mean of signed branch likelihoods when present,
                # else neutral 0 (unknown prediction -> no calibration pressure).
                # likelihood is signed and clamped to [-1, 1]; NaN/inf treated as
                # missing (excluded from the mean, no calibration pressure).
                preds = []
                for b in branches:
                    if not isinstance(b, dict):
                        continue
                    lk = b.get("likelihood")
                    if isinstance(lk, (int, float)):
                        try:
                            lk = float(lk)
                        except (TypeError, ValueError, OverflowError):
                            continue
                        if math.isfinite(lk):
                            preds.append(max(-1.0, min(1.0, lk)))
                predicted = sum(preds) / len(preds) if preds else 0.0
                dream_rpe = effective - predicted
                eff_ctx = (row_ctx or ctx or "general").strip().lower()[:64]
                scored.append({
                    "dream_id": did,
                    "predicted": round(predicted, 4),
                    "realized": round(effective, 4),
                    "dream_rpe": round(dream_rpe, 4),
                    "task_context": eff_ctx,
                })

            for s in scored:
                conn.execute(
                    "UPDATE dream_simulations SET rpe_delta = ? WHERE id = ?;",
                    (s["dream_rpe"], s["dream_id"]),
                )
            # Trust-weighted deferred learning: each accurate dream pulls the
            # expectation toward ITS OWN prediction (what the dream claimed the
            # world is like), weighted by measured trust in this context's
            # imagination. Dream-RPE itself updates ONLY the trust EWMA — it
            # never injects outcome noise into expectations (harness finding:
            # rpe-based injection = pure variance, no signal).
            # Trust-only learning: imagined evidence NEVER moves expectations
            # directly (provenance hierarchy — imagined is lowest tier). Dreams
            # update only the per-context TRUST score, which then scales the
            # learning rate applied to REAL outcomes for that context:
            #   effective_alpha = rpe_alpha * (0.5 + 0.5 * trust)
            # Accurate dreams -> faster real-world learning; noisy dreams ->
            # slower but never wrong-direction updates. (Harness-derived rule;
            # content-injection variants all failed H1/H2 empirically.)
            by_ctx = {}
            for s in scored:
                by_ctx.setdefault(s["task_context"], []).append(s)
            for key, items in by_ctx.items():
                mean_abs_rpe = sum(abs(i["dream_rpe"]) for i in items) / len(items)
                new_trust = max(0.0, min(1.0, 1.0 - 0.5 * mean_abs_rpe))
                old_trust = self.bio_engine.dream_trust.get(key, 0.2)
                self.bio_engine.dream_trust[key] = round(
                    old_trust + 0.2 * (new_trust - old_trust), 4)

            if scored:
                self._record_audit(
                    conn,
                    int(conn.execute("SELECT COALESCE(MAX(version),1) FROM soul_states;").fetchone()[0]),
                    "dream_scored",
                    {"scored": len(scored), "task_context": ctx},
                    "n/a",
                )
                self._persist_bio(conn)
            conn.commit()

        return {
            "status": "scored" if scored else "nothing_to_score",
            "scored_count": len(scored),
            "scores": scored,
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

        stored = json.loads(row[4])
        return SoulState(
            soul_version=row[0],
            constitution_version=row[1],
            traits=json.loads(row[2]),
            narrative=row[3],
            unresolved_tensions=self._tensions_from_conn(conn, stored),
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
            # Return post-write state so callers see the protected value applied
            return self.get_current_state()

        if update.trait not in ALLOWED_TRAIT_BOUNDS:
            raise ValueError(f"UNKNOWN TRAIT: '{update.trait}' is not a recognized control trait.")

        min_val, max_val = ALLOWED_TRAIT_BOUNDS[update.trait]
        clamped_val = round(max(min_val, min(max_val, float(update.new_value))), 4)
        if not (min_val <= update.new_value <= max_val):
            raise ValueError(f"BOUND REJECTION: Trait '{update.trait}' value {update.new_value} violates bounds [{min_val}, {max_val}]")

        with self._lock, self._get_conn() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            self._raise_if_frozen(conn)
            current = self._get_current_state_from_conn(conn)
            old_val = float(current.traits.get(update.trait, DEFAULT_TRAITS[update.trait]))
            self._assert_trait_change_rate(conn, update.trait, old_val, clamped_val, update.evidence_refs)
            new_version = current.soul_version + 1
            new_traits = dict(current.traits)
            new_traits[update.trait] = clamped_val

            created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
            traits_json = json.dumps(new_traits)
            tensions_json = json.dumps(current.unresolved_tensions)

            raw_payload = f"{new_version}|{CONSTITUTION_VERSION}|{traits_json}|{current.narrative}|{tensions_json}|{created_at}"
            new_hash = hashlib.sha256(raw_payload.encode()).hexdigest()

            const_hash = self.get_constitution_hash()
            conn.execute("""
            INSERT INTO soul_states (version, constitution_version, traits_json, narrative, unresolved_tensions_json, state_hash, created_at, constitution_hash, prior_state_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (new_version, CONSTITUTION_VERSION, traits_json, current.narrative, tensions_json, new_hash, created_at, const_hash, current.state_hash))

            self._record_audit(conn, new_version, "update_trait", {"update": asdict(update)}, new_hash)
            self._log_trait_drift(conn, "update", current.traits, new_traits)
            self._persist_bio(conn)
            conn.commit()

        return self.get_current_state()

    # --------------------------------------------------------------------------
    # BIO-REWARD API
    # --------------------------------------------------------------------------
    def process_reward(
        self,
        signal: RewardSignal,
        session_id: str = "",
        plan_id: str = "",
        agent_id: str = "",
        task_id: str = "",
    ) -> SoulState:
        """Identity wallet only for receipted tests or chat-human signals. Internal sources are in-plan self-score overlay."""
        if signal.source not in REWARD_SOURCES:
            raise ValueError(f"unknown reward source {signal.source!r}")
        if signal.source in INTERNAL_REWARD_SOURCES:
            return self._process_internal_reward(
                signal,
                session_id=session_id,
                plan_id=plan_id,
                agent_id=agent_id,
                task_id=task_id,
            )
        if signal.source == "external_test" and not (signal.evidence_receipt or "").strip():
            raise ValueError("external_test reward requires evidence_receipt")
        if signal.source == "external_human" and not (session_id or "").strip():
            raise ValueError("external_human reward requires session_id")
        with self._lock, self._get_conn() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            self._raise_if_frozen(conn)
            if signal.source == "external_test":
                # Receipts are hash-chain entries: format + replay gate. A bare
                # non-empty string is no longer sufficient to move identity.
                rid = (signal.evidence_receipt or "").strip()
                if len(rid) < 8 or not re.fullmatch(r"[\w:.\-]+", rid):
                    raise ValueError(
                        "evidence_receipt malformed (need >=8 chars of [A-Za-z0-9_:.\\-])")
                dup = conn.execute(
                    """SELECT 1 FROM audit_ledger 
                       WHERE action_type = 'bio_reward' 
                         AND json_extract(payload_json, '$.evidence_receipt') = ? 
                       LIMIT 1;""",
                    (rid,),
                ).fetchone()
                if dup:
                    raise ValueError(f"evidence_receipt {rid!r} already redeemed (replay rejected)")
            if signal.source == "external_human":
                self._assert_output_review_receipt(conn, signal.review_receipt, session_id)
            current = self._get_current_state_from_conn(conn)
            old_da = float(self.bio_engine.dopamine)
            old_co = float(self.bio_engine.cortisol)
            # Trust-modulated learning rate: accurate dreaming in this context
            # speeds up real-outcome learning (up to 2x at trust=1), inaccurate
            # dreaming slows it (down to 0.5x). Expectations themselves are fed
            # ONLY by reality (see score_dreams_against_reality).
            ctx_key = (signal.task_context or "general").strip().lower()[:64]
            saved_alpha = self.bio_engine.rpe_alpha
            self.bio_engine.rpe_alpha = saved_alpha * (
                0.5 + 0.5 * self.bio_engine.trust(ctx_key))
            try:
                new_traits = self.bio_engine.process_reward(signal, current.traits)
            finally:
                self.bio_engine.rpe_alpha = saved_alpha
            new_version = current.soul_version + 1
            created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
            traits_json = json.dumps(new_traits)
            tensions_json = json.dumps(current.unresolved_tensions)

            raw_payload = f"{new_version}|{CONSTITUTION_VERSION}|{traits_json}|{current.narrative}|{tensions_json}|{created_at}"
            new_hash = hashlib.sha256(raw_payload.encode()).hexdigest()

            const_hash = self.get_constitution_hash()
            conn.execute("""
            INSERT INTO soul_states (version, constitution_version, traits_json, narrative, unresolved_tensions_json, state_hash, created_at, constitution_hash, prior_state_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (new_version, CONSTITUTION_VERSION, traits_json, current.narrative, tensions_json, new_hash, created_at, const_hash, current.state_hash))

            self._record_audit(conn, new_version, "bio_reward", asdict(signal), new_hash)
            self._log_trait_drift(conn, "reward", current.traits, new_traits, old_da=old_da, old_co=old_co)
            self._persist_bio(conn)
            if signal.source == "external_test" and float(signal.valence) < 0:
                self._write_dream_due_sql(conn, True)
            conn.commit()

        # Auto-close the dream loop: a receipted negative external outcome scores
        # pending imagined branches against reality (Overfitted-Brain replay,
        # arXiv:2403.07979). Runs OUTSIDE the state lock — scoring opens its own tx.
        if signal.source == "external_test" and float(signal.valence) < 0:
            try:
                self.score_dreams_against_reality(
                    realized_valence=float(signal.valence),
                    confidence=float(signal.confidence),
                    task_context=signal.task_context or "",
                    evidence_receipt=signal.evidence_receipt or "",
                )
            except Exception:
                pass  # ponytail: never let dream scoring break the reward path

        return self.get_current_state()

    def _process_internal_reward(
        self,
        signal: RewardSignal,
        session_id: str = "",
        plan_id: str = "",
        agent_id: str = "",
        task_id: str = "",
    ) -> SoulState:
        valence = float(signal.valence)
        conf = float(signal.confidence)
        if not (math.isfinite(valence) and math.isfinite(conf)):
            raise ValueError("reward valence/confidence must be finite numbers")
        valence = max(-1.0, min(1.0, valence))
        conf = max(0.0, min(1.0, conf))
        delta = valence * conf
        # plan/agent may arrive via kwargs OR embedded in the signal itself
        pid = (plan_id or signal.plan_id or "").strip()
        aid = (agent_id or signal.agent_id or "").strip()
        tid = (task_id or signal.task_id or "").strip()
        sid = (session_id or signal.session_id or "").strip()
        with self._lock, self._get_conn() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            store = self._solver_store_from_conn(conn)
            working = self._solver_working_from_conn(conn)
            # ponytail: in-task self-score; no receipt. Identity still gated. Idle farming blocked.
            if not pid and not store.get("wallets") and not working:
                raise ValueError(
                    "internal self-score only during a plan; pass plan_id or record a solver step first"
                )
            if not pid:
                active = self._pick_wallet(store, "", "")
                pid = active.get("plan_id") or ""
                if not aid:
                    aid = active.get("agent_id") or ""
            key = _wallet_key(pid, aid)
            wallet = store["wallets"].get(key) or _empty_wallet(pid, aid, sid, tid)
            # RPE gate on top of B's wallet bump: repeated identical self-praise habituates.
            ctx = ("internal:" + ((signal.task_context or "general").strip().lower()[:56])).strip()
            prediction = float(self.bio_engine.expected_valence.get(ctx, 0.0))
            rpe = delta - prediction
            alpha_n = self.bio_engine.alpha_for(ctx) * 0.5
            self.bio_engine.expected_valence[ctx] = prediction + alpha_n * rpe
            self.bio_engine.visit_counts[ctx] = self.bio_engine.visit_counts.get(ctx, 0) + 1
            wallet = _bump_wallet(wallet, delta=delta * max(0.0, min(1.0, 0.5 + 0.5 * rpe)))
            wallet["session_id"] = sid or wallet.get("session_id") or ""
            wallet["plan_id"] = pid
            wallet["agent_id"] = aid
            wallet["task_id"] = tid or wallet.get("task_id") or ""
            store["wallets"][key] = wallet
            store["active_key"] = key
            self._write_solver_store(conn, store)
            self._persist_bio(conn)
            conn.commit()
        return self.get_current_state()

    def step_homeostasis(self) -> SoulState:
        """Step serotonergic decay back toward default set points."""
        with self._lock, self._get_conn() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            if self._flag_value_from_conn(conn, "quarantine_frozen") == "1":
                conn.commit()
                return self._get_current_state_from_conn(conn)
            current = self._get_current_state_from_conn(conn)
            cutoff = (
                datetime.datetime.now(datetime.timezone.utc)
                - datetime.timedelta(seconds=HOMEOSTASIS_REWARD_GRACE_SEC)
            ).isoformat()
            recent_reward = conn.execute(
                "SELECT 1 FROM audit_ledger WHERE action_type = 'bio_reward' AND timestamp >= ? LIMIT 1;",
                (cutoff,),
            ).fetchone()
            if recent_reward:
                decay = math.exp(-self.bio_engine.decay_rate)
                self.bio_engine.dopamine = max(0.0, round(self.bio_engine.dopamine * decay, 4))
                self.bio_engine.cortisol = max(0.0, round(self.bio_engine.cortisol * decay, 4))
                self._persist_bio(conn)
                conn.commit()
                return current
            decayed_traits = self.bio_engine.step_homeostasis(current.traits)

            if decayed_traits != current.traits:
                new_version = current.soul_version + 1
                created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
                traits_json = json.dumps(decayed_traits)
                tensions_json = json.dumps(current.unresolved_tensions)

                raw_payload = f"{new_version}|{CONSTITUTION_VERSION}|{traits_json}|{current.narrative}|{tensions_json}|{created_at}"
                new_hash = hashlib.sha256(raw_payload.encode()).hexdigest()

                const_hash = self.get_constitution_hash()
                conn.execute("""
                INSERT INTO soul_states (version, constitution_version, traits_json, narrative, unresolved_tensions_json, state_hash, created_at, constitution_hash, prior_state_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """, (new_version, CONSTITUTION_VERSION, traits_json, current.narrative, tensions_json, new_hash, created_at, const_hash, current.state_hash))

                self._record_audit(conn, new_version, "homeostasis_decay", {"traits": decayed_traits}, new_hash)
            self._persist_bio(conn)
            conn.commit()

        return self.get_current_state()

    # --------------------------------------------------------------------------
    # MODULE 7: Self-Healing Engine & Rollback
    # --------------------------------------------------------------------------
    def heal_soul_state(self, level: int = 1, reason: str = "Automated health repair") -> dict:
        if level not in (1, 2, 3):
            raise ValueError("heal level must be 1, 2, or 3")
        if level == 1:
            with self._lock, self._get_conn() as conn:
                conn.execute("BEGIN IMMEDIATE;")
                self._raise_if_frozen(conn)
                current = self._get_current_state_from_conn(conn)
                new_traits = dict(current.traits)
                for trait, val in current.traits.items():
                    if trait in DEFAULT_TRAITS:
                        new_traits[trait] = round((val + DEFAULT_TRAITS[trait]) / 2.0, 4)
                if new_traits == current.traits:
                    conn.commit()
                    written = 0
                else:
                    new_version = current.soul_version + 1
                    created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
                    traits_json = json.dumps(new_traits)
                    tensions_json = json.dumps(current.unresolved_tensions)
                    raw_payload = f"{new_version}|{CONSTITUTION_VERSION}|{traits_json}|{current.narrative}|{tensions_json}|{created_at}"
                    new_hash = hashlib.sha256(raw_payload.encode()).hexdigest()
                    const_hash = self.get_constitution_hash()
                    conn.execute("""
                    INSERT INTO soul_states (version, constitution_version, traits_json, narrative, unresolved_tensions_json, state_hash, created_at, constitution_hash, prior_state_hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """, (new_version, CONSTITUTION_VERSION, traits_json, current.narrative, tensions_json, new_hash, created_at, const_hash, current.state_hash))
                    self._record_audit(conn, new_version, "heal_level_1", {"reason": reason, "traits": new_traits}, new_hash)
                    self._log_trait_drift(conn, "heal", current.traits, new_traits)
                    self._persist_bio(conn)
                    conn.commit()
                    written = 1
            self._set_heal_due(False)
            return {"level": 1, "status": "recalibrated", "reason": reason, "versions_written": written}

        elif level == 2:
            self._set_flag("quarantine_frozen", "0")
            current = self.get_current_state()
            if current.soul_version > 1:
                new_state = self.rollback_to_version(current.soul_version - 1, operator_reason=reason)
                self._set_heal_due(False)
                return {"level": 2, "status": "rolled_back", "version": new_state.soul_version}
            self._set_heal_due(False)
            return {"level": 2, "status": "already_at_genesis"}

        self._set_flag("quarantine_frozen", "1")
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

            bio = cur.execute(
                "SELECT dopamine, cortisol FROM neuromodulators WHERE soul_version = ?;",
                (target_version,),
            ).fetchone()
            if not bio:
                bio = cur.execute(
                    "SELECT dopamine, cortisol FROM soul_states WHERE version = ?;",
                    (target_version,),
                ).fetchone()

            conn.execute("BEGIN IMMEDIATE;")
            current = self._get_current_state_from_conn(conn)
            new_version = current.soul_version + 1
            created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

            raw_payload = f"{new_version}|{row[0]}|{row[1]}|{row[2]}|{row[3]}|{created_at}"
            new_hash = hashlib.sha256(raw_payload.encode()).hexdigest()

            const_hash = self.get_constitution_hash()
            conn.execute("""
            INSERT INTO soul_states (version, constitution_version, traits_json, narrative, unresolved_tensions_json, state_hash, created_at, constitution_hash, prior_state_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (new_version, row[0], row[1], row[2], row[3], new_hash, created_at, const_hash, current.state_hash))

            self.bio_engine.dopamine = float((bio[0] if bio else 0.0) or 0.0)
            self.bio_engine.cortisol = float((bio[1] if bio else 0.0) or 0.0)
            self._record_audit(conn, new_version, "rollback", {"target_version": target_version, "reason": operator_reason}, new_hash)
            self._write_flag_sql(conn, "unresolved_tensions", row[3] if row[3] else "[]")
            self._persist_bio(conn)
            conn.commit()

        return self.get_current_state()

    def _needs_heal(self) -> bool:
        if self.bio_engine.cortisol >= HEAL_CORTISOL_FLOOR:
            return True
        state = self.get_current_state()
        for name, default in DEFAULT_TRAITS.items():
            if abs(float(state.traits.get(name, default)) - default) >= HEAL_TRAIT_DRIFT:
                return True
        return False

    def _flag_value_from_conn(self, conn: sqlite3.Connection, key: str) -> str:
        row = conn.execute("SELECT value FROM daemon_flags WHERE key = ?;", (key,)).fetchone()
        return row[0] if row else "0"

    def _raise_if_frozen(self, conn: sqlite3.Connection) -> None:
        if self._flag_value_from_conn(conn, "quarantine_frozen") == "1":
            raise PermissionError("quarantine frozen (heal level 3); identity writes blocked until L2 rollback")

    def _assert_trait_change_rate(
        self,
        conn: sqlite3.Connection,
        trait: str,
        old_value: float,
        new_value: float,
        evidence_refs: Optional[List[str]],
    ) -> None:
        refs = [r.strip() for r in (evidence_refs or []) if isinstance(r, str) and r.strip()]
        if len(refs) < MIN_EVIDENCE_REFS:
            raise ValueError(f"autonomous trait update requires at least {MIN_EVIDENCE_REFS} evidence_refs")
        delta = abs(float(new_value) - float(old_value))
        if delta > TRAIT_EVENT_MAX_DELTA:
            raise ValueError(f"per-event trait delta {delta} exceeds {TRAIT_EVENT_MAX_DELTA}")
        cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=7)).isoformat()
        rows = conn.execute(
            """SELECT old_value, new_value FROM trait_drift_log
               WHERE trait = ? AND source = 'update' AND created_at >= ?;""",
            (trait, cutoff),
        ).fetchall()
        rolling = sum(abs(float(r[1]) - float(r[0])) for r in rows) + delta
        if rolling > TRAIT_ROLLING_7D_MAX:
            raise ValueError(f"7-day rolling |Δ| {rolling} exceeds {TRAIT_ROLLING_7D_MAX}")

    def _write_flag_sql(self, conn: sqlite3.Connection, key: str, value: str) -> None:
        conn.execute(
            """INSERT INTO daemon_flags (key, value, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET
                 value = excluded.value,
                 updated_at = excluded.updated_at;""",
            (key, value, datetime.datetime.now(datetime.timezone.utc).isoformat()),
        )

    def _set_flag(self, key: str, value: str) -> None:
        with self._lock, self._get_conn() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            self._write_flag_sql(conn, key, value)
            conn.commit()

    def _tensions_from_conn(self, conn: sqlite3.Connection, fallback: Optional[List[str]] = None) -> List[str]:
        row = conn.execute("SELECT value FROM daemon_flags WHERE key = 'unresolved_tensions';").fetchone()
        if not row:
            return list(fallback or [])
        try:
            data = json.loads(row[0] or "[]")
        except json.JSONDecodeError:
            return list(fallback or [])
        return data if isinstance(data, list) else list(fallback or [])

    def _reflect_due(self, state: SoulState) -> bool:
        return bool(state.unresolved_tensions)

    def _get_dream_due(self) -> bool:
        with self._get_conn() as conn:
            return self._flag_value_from_conn(conn, "dream_due") == "1"

    def _policy_recall_limit(
        self,
        requested: Optional[int] = None,
        overlay: Optional[dict] = None,
        plan_id: str = "",
        agent_id: str = "",
    ) -> int:
        if overlay is not None:
            da = float(overlay.get("dopamine") or 0.0)
            co = float(overlay.get("cortisol") or 0.0)
        else:
            with self._get_conn() as conn:
                store = self._solver_store_from_conn(conn)
            if store.get("wallets"):
                w = self._pick_wallet(store, plan_id, agent_id)
                da = float(w.get("dopamine") or 0.0)
                co = float(w.get("cortisol") or 0.0)
            else:
                da = float(self.bio_engine.dopamine)
                co = float(self.bio_engine.cortisol)
        if co >= HEAL_CORTISOL_FLOOR:
            cap = RECALL_LIMIT_STRESS
        elif da >= DA_RECALL_FLOOR:
            cap = RECALL_LIMIT_HIGH
        else:
            cap = RECALL_LIMIT_DEFAULT
        if requested is None:
            return cap
        return max(1, min(int(requested), cap))

    def _assert_output_review_receipt(
        self, conn: sqlite3.Connection, receipt_id: Optional[str], session_id: str
    ) -> None:
        rid = (receipt_id or "").strip()
        if not rid:
            raise ValueError("external_human reward requires review_receipt from output review")
        row = conn.execute(
            """SELECT r.cycle_id, rc.session_id
               FROM memory_change_receipts r
               LEFT JOIN review_cycles rc ON r.cycle_id = rc.id
               WHERE r.id = ? AND r.operation_kind = 'review_commit';""",
            (rid,),
        ).fetchone()
        if not row:
            raise ValueError("review_receipt is not a committed review_commit")
        sid = (session_id or "").strip()
        if row[1] and sid and row[1] != sid:
            raise ValueError("review_receipt does not belong to this session")

    def _session_has_pending_review(self, conn: sqlite3.Connection, session_id: str) -> bool:
        sid = (session_id or "").strip()
        if not sid:
            return False
        row = conn.execute(
            """SELECT 1 FROM memory_candidates c
               JOIN review_cycles rc ON c.cycle_id = rc.id
               WHERE rc.session_id = ? AND c.status = 'pending'
               LIMIT 1;""",
            (sid,),
        ).fetchone()
        return row is not None

    def _needs_dream_backstop(self) -> bool:
        with self._get_conn() as conn:
            if self._flag_value_from_conn(conn, "dream_due") == "1":
                return False
            state = self._get_current_state_from_conn(conn)
            if state.unresolved_tensions:
                return True
            working = self._solver_working_from_conn(conn)
            return any(s.get("outcome") == "dead_end" for s in working)

    def _write_dream_due_sql(self, conn: sqlite3.Connection, due: bool) -> None:
        self._write_flag_sql(conn, "dream_due", "1" if due else "0")

    def _set_dream_due(self, due: bool) -> None:
        with self._lock, self._get_conn() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            self._write_dream_due_sql(conn, due)
            conn.commit()
        if self.daemon_worker is not None:
            self.daemon_worker.stats["dream_due"] = due

    def _get_heal_due(self) -> bool:
        with self._get_conn() as conn:
            return self._flag_value_from_conn(conn, HEAL_DUE_KEY) == "1"

    def _write_heal_due_sql(self, conn: sqlite3.Connection, due: bool) -> None:
        self._write_flag_sql(conn, HEAL_DUE_KEY, "1" if due else "0")

    def _set_heal_due(self, due: bool) -> None:
        with self._lock, self._get_conn() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            self._write_heal_due_sql(conn, due)
            conn.commit()
        if self.daemon_worker is not None:
            self.daemon_worker.stats["heal_due"] = due

    def _get_remember_due(self) -> bool:
        with self._get_conn() as conn:
            return self._flag_value_from_conn(conn, REMEMBER_DUE_KEY) == "1"

    def _health_report(self, conn: sqlite3.Connection, state: SoulState, frozen: bool) -> dict:
        hid = self._flag_value_from_conn(conn, HEALTH_ID_KEY)
        if not hid or hid == "0":
            hid = f"health_{uuid.uuid4().hex[:16]}"
            self._write_flag_sql(conn, HEALTH_ID_KEY, hid)
        tensions = list(state.unresolved_tensions or [])
        co = float(self.bio_engine.cortisol)
        curiosity = float(state.traits.get("curiosity", DEFAULT_TRAITS["curiosity"]))
        care = float(state.traits.get("relational_care", DEFAULT_TRAITS["relational_care"]))
        audacity = float(state.traits.get("audacity", DEFAULT_TRAITS["audacity"]))
        anxiety = float(state.traits.get("error_anxiety", DEFAULT_TRAITS["error_anxiety"]))
        return {
            "health_id": hid,
            "soul_version": state.soul_version,
            "coherence": round(max(0.0, 1.0 - 0.15 * len(tensions)), 4),
            "integrity": round(0.4 if frozen else max(0.0, 1.0 - co), 4),
            "connection": round(care / 100.0, 4),
            "curiosity": round(curiosity / 100.0, 4),
            "agency": round(audacity / 100.0, 4),
            "adaptability": round(max(0.0, 1.0 - anxiety / 15.0), 4),
            "tensions": tensions,
            "confidence": round(max(0.0, 1.0 - co), 4),
            "narrative": "Subjective self-report. Cannot grant energy or skip SEAL.",
            "authorizes_identity": False,
            "authorizes_freeze": False,
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

    def _dead_end_packet(self, working: List[dict], dream_due: bool) -> Optional[dict]:
        last = next((s for s in reversed(working) if s.get("outcome") == "dead_end"), None)
        if not last:
            return None
        return {
            "tool": last.get("tool"),
            "method": last.get("method"),
            "receipt": last.get("receipt"),
            "options_left": last.get("options_left"),
            "dream_due": dream_due,
        }

    def _read_flag_json(self, conn: sqlite3.Connection, key: str, default: Any) -> Any:
        row = conn.execute("SELECT value FROM daemon_flags WHERE key = ?;", (key,)).fetchone()
        if not row:
            return default
        try:
            return json.loads(row[0])
        except (json.JSONDecodeError, TypeError):
            return default

    def _solver_working_from_conn(self, conn: sqlite3.Connection) -> List[dict]:
        data = self._read_flag_json(conn, SOLVER_WORKING_KEY, [])
        return data if isinstance(data, list) else []

    def _write_solver_store(self, conn: sqlite3.Connection, store: dict) -> None:
        self._write_flag_sql(conn, SOLVER_OVERLAY_KEY, json.dumps({
            "active_key": store.get("active_key") or "",
            "wallets": store.get("wallets") or {},
        }))

    def _solver_store_from_conn(self, conn: sqlite3.Connection) -> dict:
        data = self._read_flag_json(conn, SOLVER_OVERLAY_KEY, {})
        if not isinstance(data, dict):
            return {"active_key": "", "wallets": {}}
        wallets = data.get("wallets")
        if isinstance(wallets, dict):
            return {
                "active_key": data.get("active_key") or "",
                "wallets": wallets,
            }
        if "dopamine" in data or "cortisol" in data:
            wallet = _empty_wallet(
                data.get("plan_id") or "",
                data.get("agent_id") or "",
                data.get("session_id") or "",
                data.get("task_id") or "",
            )
            wallet["dopamine"] = float(data.get("dopamine") or 0.0)
            wallet["cortisol"] = float(data.get("cortisol") or 0.0)
            key = _wallet_key(wallet["plan_id"], wallet["agent_id"])
            return {"active_key": key, "wallets": {key: wallet}}
        return {"active_key": "", "wallets": {}}

    def _pick_wallet(self, store: dict, plan_id: str = "", agent_id: str = "") -> dict:
        wallets = store.get("wallets") or {}
        p = (plan_id or "").strip()
        a = (agent_id or "").strip()
        if p or a:
            key = _wallet_key(p, a)
            if key in wallets:
                return dict(wallets[key])
            if not a and p:
                matches = [w for w in wallets.values() if (w.get("plan_id") or "") == p]
                if matches:
                    active = store.get("active_key") or ""
                    for w in matches:
                        if _wallet_key(w.get("plan_id") or "", w.get("agent_id") or "") == active:
                            return dict(w)
                    return dict(matches[-1])
            return _empty_wallet(p, a)
        key = store.get("active_key") or ""
        if key and key in wallets:
            return dict(wallets[key])
        return _empty_wallet()

    def _filter_working(
        self,
        working: List[dict],
        plan_id: str,
        agent_id: str,
        overlay: dict,
    ) -> List[dict]:
        p = (plan_id or "").strip()
        a = (agent_id or "").strip()
        if p or a:
            return [
                s for s in working
                if (not p or (s.get("plan_id") or "") == p)
                and (not a or (s.get("agent_id") or "") == a)
            ]
        ap = overlay.get("plan_id") or ""
        return [s for s in working if (s.get("plan_id") or "") == ap]

    def _solver_overlay_from_conn(
        self,
        conn: sqlite3.Connection,
        plan_id: str = "",
        agent_id: str = "",
    ) -> dict:
        return self._pick_wallet(self._solver_store_from_conn(conn), plan_id, agent_id)

    def _last_imagined_from_conn(self, conn: sqlite3.Connection) -> Optional[dict]:
        row = conn.execute(
            """SELECT id, scenario_prompt, simulated_outcome, provenance, created_at
               FROM dream_simulations ORDER BY created_at DESC LIMIT 1;"""
        ).fetchone()
        if not row:
            return None
        return {
            "dream_id": row[0],
            "scenario_prompt": self._clip_text(row[1], DREAM_SNIPPET_CHARS),
            "simulated_outcome": self._clip_text(row[2], DREAM_SNIPPET_CHARS),
            "provenance": row[3] or "imagined",
            "created_at": row[4],
        }

    def _solver_unstable(self, working: List[dict], dream_due: bool) -> dict:
        counts: Dict[str, int] = {}
        for step in working:
            if step.get("outcome") not in ("fail", "dead_end"):
                continue
            pair = f"{step.get('tool')}|{step.get('method')}"
            counts[pair] = counts.get(pair, 0) + 1
        retry = max(counts.values(), default=0)
        last = working[-1] if working else {}
        return {
            "retry_same_pair": retry,
            "dead_end_pending_dream": last.get("outcome") == "dead_end" and dream_due,
        }

    def record_solver_step(
        self,
        tool: str,
        method: str,
        outcome: str,
        receipt: str,
        session_id: str = "",
        plan_id: str = "",
        agent_id: str = "",
        task_id: str = "",
        close_plan: bool = False,
        error: Optional[str] = None,
        options_left: Optional[List[str]] = None,
    ) -> dict:
        """Receipted solver trace. Overlay during the plan. close_plan ingest+drop is one SQLite txn."""
        tool = (tool or "").strip()
        method = (method or "").strip()
        receipt = (receipt or "").strip()
        outcome = (outcome or "").strip()
        pid = (plan_id or "").strip()
        aid = (agent_id or "").strip()
        tid = (task_id or "").strip()
        sid = (session_id or "").strip()
        if not tool or not method:
            raise ValueError("tool and method are required")
        if not receipt:
            raise ValueError("receipt required; story-only steps are not paid")
        if outcome not in SOLVER_OUTCOMES:
            raise ValueError(f"outcome must be one of {sorted(SOLVER_OUTCOMES)}")
        secret_blob = " ".join(
            str(x) for x in (tool, method, receipt, error or "", aid, tid)
            if x
        )
        if contains_secret(secret_blob) or (
            options_left and any(contains_secret(str(x)) for x in options_left)
        ):
            raise ValueError("SECURITY REJECTION: solver step contains credentials. Write blocked under Section 3.3.")
        left = list(options_left) if options_left is not None else None
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        plan_closed = False
        snapshot: List[dict] = []
        fire_dream = False
        retry_same = 0
        wallet = _empty_wallet(pid, aid, sid, tid)
        working: List[dict] = []
        episode_ids: List[str] = []
        with self._lock:
            with self._get_conn() as conn:
                conn.execute("BEGIN IMMEDIATE;")
                if self._session_has_pending_review(conn, sid):
                    raise ValueError("pending review candidates; close input review before solver steps")
                working = self._solver_working_from_conn(conn)
                store = self._solver_store_from_conn(conn)
                retry_same = sum(
                    1
                    for s in working
                    if s.get("tool") == tool
                    and s.get("method") == method
                    and (s.get("plan_id") or "") == pid
                    and (s.get("agent_id") or "") == aid
                ) + 1
                step = {
                    "tool": tool,
                    "method": method,
                    "outcome": outcome,
                    "receipt": receipt,
                    "error": (error or "").strip() or None,
                    "options_left": left,
                    "session_id": sid,
                    "plan_id": pid,
                    "agent_id": aid,
                    "task_id": tid,
                    "created_at": now,
                }
                fire_dream = outcome == "dead_end" or (outcome == "fail" and left == [])
                tentative = _trim_working(working + [step], pid)
                if close_plan:
                    snapshot = [s for s in tentative if (s.get("plan_id") or "") == pid]
                    plan_closed = True
                    if snapshot:
                        if self._flag_value_from_conn(conn, "quarantine_frozen") == "1":
                            raise PermissionError(
                                "quarantine frozen (heal level 3); ingest blocked until L2 rollback"
                            )
                        for _aid, text in _solver_identity_texts(pid, snapshot):
                            ingested = self._insert_quarantine_episode(conn, EpisodeInput(
                                source_kind="agent",
                                provenance="observed",
                                content=text,
                                session_id=sid or None,
                            ))
                            if ingested.get("episode_id"):
                                episode_ids.append(ingested["episode_id"])
                    working = [
                        s for s in self._solver_working_from_conn(conn)
                        if (s.get("plan_id") or "") != pid
                    ]
                    store["wallets"] = {
                        k: w for k, w in store["wallets"].items()
                        if (w.get("plan_id") or "") != pid
                    }
                    store["active_key"] = next(iter(store["wallets"]), "")
                    if fire_dream:
                        self._write_dream_due_sql(conn, True)
                    self._write_flag_sql(conn, SOLVER_WORKING_KEY, json.dumps(working))
                    self._write_solver_store(conn, store)
                    conn.commit()
                    wallet = _empty_wallet(pid, aid, sid, tid)
                else:
                    working = tentative
                    key = _wallet_key(pid, aid)
                    wallet = store["wallets"].get(key) or _empty_wallet(pid, aid, sid, tid)
                    wallet = _bump_wallet(wallet, outcome=outcome)
                    wallet["session_id"] = sid or wallet.get("session_id") or ""
                    wallet["plan_id"] = pid
                    wallet["agent_id"] = aid
                    wallet["task_id"] = tid or wallet.get("task_id") or ""
                    store["wallets"][key] = wallet
                    store["active_key"] = key
                    if fire_dream:
                        self._write_dream_due_sql(conn, True)
                    if outcome in ("succeed", "dead_end"):
                        self._write_flag_sql(conn, REMEMBER_DUE_KEY, "1")
                    self._write_flag_sql(conn, SOLVER_WORKING_KEY, json.dumps(working))
                    self._write_solver_store(conn, store)
                    conn.commit()
        da = float(wallet.get("dopamine") or 0.0)
        co = float(wallet.get("cortisol") or 0.0)
        if fire_dream and self.daemon_worker is not None:
            self.daemon_worker.stats["dream_due"] = True
        if episode_ids and self.daemon_worker is not None:
            self.daemon_worker.stats["remember_due"] = False
        elif outcome in ("succeed", "dead_end") and self.daemon_worker is not None:
            self.daemon_worker.stats["remember_due"] = True
        dream_due = self._get_dream_due()
        return {
            "status": "recorded",
            "working_count": len(working),
            "retry_same_pair": retry_same,
            "overlay": {
                **wallet,
                "serotonin": round(1.0 - max(da, co), 4),
            },
            "plan_closed": plan_closed,
            "dream_due": dream_due,
            "remember_due": (
                False if episode_ids
                else (outcome in ("succeed", "dead_end") or self._get_remember_due())
            ),
            "wrote_identity": False,
            "wrote_episode": bool(episode_ids),
            "episode_ids": episode_ids,
        }

    def expire_quarantine(self) -> dict:
        """Cliff-expire unreviewed episodes past retention_until. Never touches reviewed_memories."""
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._lock, self._get_conn() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            cur = conn.execute(
                """
                UPDATE episodes
                SET trust_state = 'expired'
                WHERE deleted_at IS NULL
                  AND trust_state NOT IN ('expired', 'superseded')
                  AND retention_until IS NOT NULL
                  AND retention_until <= ?
                  AND id NOT IN (
                    SELECT j.value
                    FROM reviewed_memories r, json_each(r.source_episode_refs_json) j
                    WHERE r.deleted_at IS NULL
                      AND r.retention_state = 'accessible'
                      AND r.source_episode_refs_json IS NOT NULL
                  )
                """,
                (now,),
            )
            n = cur.rowcount if cur.rowcount is not None and cur.rowcount >= 0 else 0
            conn.commit()
        return {"expired_count": n}

    def get_memory_digest(
        self,
        limit: Optional[int] = None,
        plan_id: str = "",
        agent_id: str = "",
        session_id: str = "",
    ) -> dict:
        expired = self.expire_quarantine()
        state = self.get_current_state()
        dream_due = self._get_dream_due()
        heal_due = self._get_heal_due()
        remember_due = self._get_remember_due()
        if self.daemon_worker is not None:
            self.daemon_worker.stats["dream_due"] = dream_due
            self.daemon_worker.stats["heal_due"] = heal_due
            self.daemon_worker.stats["remember_due"] = remember_due
        with self._lock, self._get_conn() as conn:
            working_all = self._solver_working_from_conn(conn)
            store = self._solver_store_from_conn(conn)
            last_imagined = self._last_imagined_from_conn(conn)
            frozen = self._flag_value_from_conn(conn, "quarantine_frozen") == "1"
            health = self._health_report(conn, state, frozen)
            conn.commit()
        overlay = self._pick_wallet(store, plan_id, agent_id)
        working = self._filter_working(working_all, plan_id, agent_id, overlay)
        policy_overlay = overlay if store.get("wallets") else None
        eff_session_id = session_id or (overlay.get("session_id") if overlay else "") or ""
        memories = self.recall_memories(
            limit=limit,
            overlay=policy_overlay,
            plan_id=plan_id,
            agent_id=agent_id,
            session_id=eff_session_id,
        )
        o_da = float(overlay.get("dopamine") or 0.0)
        o_co = float(overlay.get("cortisol") or 0.0)
        behavior = trait_behavior_lines(
            state.traits, self.bio_engine.dopamine, self.bio_engine.cortisol
        )
        if working:
            behavior.append(
                "Obey digest.working; do not retry a failed (tool, method) pair. Traces are not sealed facts."
            )
        if o_co >= HEAL_CORTISOL_FLOOR:
            behavior.append("High session cortisol: tighter recall this plan; do not take extra risk.")
        if o_da >= DA_RECALL_FLOOR:
            behavior.append("High session dopamine: do not overclaim success this plan.")
        if any(s.get("outcome") == "dead_end" for s in working) and dream_due:
            behavior.append(
                "Dead end: run two-phase soul_dream; do not skip because session cortisol is high."
            )
        if heal_due:
            behavior.append(
                "Heal due: wait for the human to type HEAL, then call soul_heal with session_id. Daemon does not auto-heal identity."
            )
        if remember_due:
            behavior.append(
                "Remember due: soul_remember a distilled lesson. Not soul_reward. Then start review if quarantine is non-empty."
            )
        return {
            "soul_version": state.soul_version,
            "traits": state.traits,
            "neuromodulators": {
                "dopamine": self.bio_engine.dopamine,
                "cortisol": self.bio_engine.cortisol,
                "serotonin": self.bio_engine.serotonin
            },
            "session_neuromodulators": {
                "dopamine": o_da,
                "cortisol": o_co,
                "serotonin": round(1.0 - max(o_da, o_co), 4),
                "session_id": overlay.get("session_id") or "",
                "plan_id": overlay.get("plan_id") or "",
                "agent_id": overlay.get("agent_id") or "",
                "task_id": overlay.get("task_id") or "",
            },
            "behavior": behavior,
            "dream_due": dream_due,
            "heal_due": heal_due,
            "remember_due": remember_due,
            "solver_active": bool(working),
            "reflect_due": self._reflect_due(state),
            "expired_count": expired["expired_count"],
            "active_facts": memories,
            "working": working,
            "dead_end": self._dead_end_packet(working, dream_due),
            "health": health,
            "last_imagined": last_imagined,
            "unstable": self._solver_unstable(working, dream_due),
        }

    def get_identity_digest(self, limit: int = 5) -> dict:
        """Alias for get_memory_digest per soul-review-cycle specification."""
        return self.get_memory_digest(limit=limit)

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
            "heals_skipped": 0,
            "homeostasis_runs": 0,
            "checkpoints_run": 0,
            "error_count": 0,
            "last_error": None,
            "last_dream": None,
            "last_heal": None,
            "dream_due": kernel._get_dream_due(),
            "heal_due": kernel._get_heal_due(),
            "remember_due": kernel._get_remember_due(),
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
        try:
            while not self.stop_event.is_set():
                now = time.time()
                try:
                    if now - last_checkpoint >= 120:
                        with self.kernel._get_conn() as conn:
                            conn.execute("PRAGMA wal_checkpoint(PASSIVE);")
                        self.stats["checkpoints_run"] += 1
                        last_checkpoint = now
                    if now - last_homeostasis >= self.homeostasis_interval:
                        self.kernel.step_homeostasis()
                        self.kernel.expire_quarantine()
                        self.stats["homeostasis_runs"] += 1
                        last_homeostasis = now
                    if now - last_dream >= self.dream_interval:
                        # ponytail: timer is backstop only; tensions / dead_end set dream_due
                        if self.kernel._needs_dream_backstop():
                            self.kernel._set_dream_due(True)
                        self.stats["last_dream"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
                        last_dream = now
                    if now - last_heal >= self.heal_interval:
                        if self.kernel._needs_heal():
                            self.kernel._set_heal_due(True)
                            self.stats["heals_run"] += 1
                            self.stats["last_heal"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
                        else:
                            self.stats["heals_skipped"] += 1
                        last_heal = now
                except Exception as exc:
                    self.stats["error_count"] += 1
                    self.stats["last_error"] = str(exc)
                    logging.error(f"[SoulDaemonSupervisor] Error in maintenance cycle: {exc}", exc_info=True)
                    time.sleep(min(30.0, 2.0 ** min(5, self.stats["error_count"])))
                time.sleep(1)
        finally:
            self.kernel.close_thread_conn()
