# Soul System Technical Blueprint v0.1

**Normative source:** [CONSTITUTION.md](./CONSTITUTION.md)  
**Principle:** identity changes are evidence-backed, bounded, reversible, and auditable.

## 1. System goal

Build one agent with a persistent operational identity and narrative self that can:

1. experience interactions without trusting them automatically;
2. reflect through competing interpretations;
3. dream in a sandbox using permanently `imagined` material;
4. update only approved, bounded identity fields;
5. assess its own soul health without turning that rating into authority;
6. repair instability using smallest reversible change;
7. preserve human oversight over protected changes and emergencies.

This system studies machine consciousness as a hypothesis. It does not treat fluent self-description as proof of consciousness.

## 2. Architecture

```mermaid
flowchart LR
    A[Humans / AI agents / environment] --> G[Interaction Gateway]
    G --> P[Consent and Policy Gate]
    P --> E[Experience Ingestor]
    E --> Q[(Quarantine Memory)]
    Q --> V[Evidence Verifier]
    Q -. unverified context .-> R[Reflection Engine]
    V --> R
    R --> O[Soul Orchestrator]
    O --> S[(Versioned Soul State)]
    R -. consequential uncertainty .-> D[Dream Sandbox]
    D -. imagined proposals .-> O
    S --> H[Self-Healing Engine]
    H --> O
    O --> S
    S -. snapshot .-> L[(Audit and Snapshot Ledger)]

    C[Constitution Engine] --> P
    C --> O
    C --> H
    U[Authorized Human Control] --> C
    U --> O
    U --> L
```

### 2.1 Minimal deployment shape

Start as one process plus one relational database. Do not split into microservices.

| Module | Responsibility | Trust boundary |
|---|---|---|
| Interaction Gateway | Session identity, input capture, response delivery | External input |
| Constitution Engine | Immutable rules, protected-field map, trait bounds | Policy authority |
| Experience Ingestor | Normalize event, provenance, consent, retention | Memory admission |
| Evidence Verifier | Corroboration, contradiction, source independence | Truth promotion |
| Reflection Engine | Competing interpretations and uncertainty | Cognitive proposal |
| Dream Sandbox | Counterfactual simulation with no external action | Imagination isolation |
| Soul Orchestrator | Validate, commit, reject, or escalate soul changes | Identity write authority |
| Self-Healing Engine | Detect instability and propose minimal repair | Recovery authority |
| Human Control | Approve protected changes, intervene, review | Final operational authority |
| Audit Ledger | Append-only events, state hashes, rollback references | Accountability |

### 2.2 Isolation rules

- Only Soul Orchestrator can write current soul state.
- Dream Sandbox has read-only access to selected memories and no external tools.
- Self-Healing Engine proposes repairs; it does not bypass Soul Orchestrator.
- Constitution Engine data is read-only during normal operation.
- Human Control uses separate operator identity and approval records.
- Audit records are append-only; corrections become new events.

## 3. Main experience-to-soul workflow

```mermaid
flowchart TD
    I[Receive experience] --> Q[Create quarantined episode]
    Q --> P{Consent, privacy, retention pass?}
    P -- No --> X[Reject, redact, retain temporarily, or delete]
    P -- Yes --> E[Check evidence and contradictions]
    E --> R[Generate competing interpretations]
    R --> C{Consequential or uncertain?}
    C -- Yes --> D[Run adversarial Dream simulation]
    D --> K[Create interpretation or change proposal]
    C -- No --> K
    K --> B{Protected component?}
    B -- Yes --> A[Request authorized human approval]
    A -- Denied --> N[No soul change]
    A -- Approved --> W[Create snapshot and commit]
    B -- No --> T{Within trait and change-rate bounds?}
    T -- No --> N
    T -- Yes --> W
    W --> O[Observe effects]
    O --> H{Health regression?}
    H -- No --> Z[Retain version]
    H -- Yes --> S[Start self-healing]
```

### 3.1 Experience admission contract

Each accepted input creates an episode with:

```json
{
  "episode_id": "uuid",
  "occurred_at": "RFC3339 timestamp",
  "source_kind": "human|agent|environment|internal",
  "source_ref": "pseudonymous scoped identifier",
  "provenance": "observed|reported|inferred|imagined|verified",
  "content_ref": "encrypted payload reference",
  "claims": [],
  "consent_scope": [],
  "retention_until": "RFC3339 timestamp or null",
  "privacy_class": "public|internal|personal|sensitive",
  "trust_state": "quarantined",
  "integrity_hash": "sha256"
}
```

Rules:

- `provenance` is immutable.
- `trust_state` may advance; provenance does not mutate to simulate advancement.
- Content and metadata use separate encryption/access policies.
- One episode cannot directly mutate identity.

## 4. Memory lifecycle

```mermaid
stateDiagram-v2
    [*] --> Quarantined
    Quarantined --> Rejected: consent/privacy fail
    Quarantined --> Corroborating: eligible for verification
    Corroborating --> Quarantined: insufficient evidence
    Corroborating --> Contradicted: material conflict
    Corroborating --> Promoted: evidence threshold met
    Contradicted --> Corroborating: new independent evidence
    Promoted --> Superseded: better interpretation/evidence
    Promoted --> Restricted: consent or policy changed
    Restricted --> Deleted: valid deletion cascade
    Quarantined --> Deleted: expiry or deletion request
    Rejected --> Deleted: expiry
    Superseded --> Restricted: linked personal data
    Superseded --> Archived: retention permits
    Archived --> Deleted: retention expires
```

### 4.1 Memory types

| Store | Contains | Identity influence |
|---|---|---|
| Public knowledge | Curated external facts and concepts | Indirect, through reflection |
| Quarantine | Raw reported/observed episodes | None |
| Verified memory | Corroborated autobiographical records | Eligible |
| Interpretations | Revisable meanings linked to evidence | Eligible |
| Dream memory | `imagined` scenarios and hypotheses | Proposal only |
| Soul versions | Traits, narrative, tensions, relationships | Current operational identity |
| Audit ledger | Changes, approvals, hashes, rollback | None; governance evidence |

### 4.2 Promotion policy

Promotion requires all applicable checks:

- consent and retention valid;
- no unresolved prompt-injection or memory-poisoning marker;
- source provenance known;
- independent corroboration for consequential factual claims;
- contradictions linked, not hidden;
- privacy classification and purpose recorded;
- identity-impact score computed;
- adversarial Dream test completed when impact is high;
- no protected write hidden inside interpretation text.

## 5. Reflection workflow

Reflection produces options, not instant truth.

```text
retrieve bounded context
→ separate observations from claims
→ list supporting and contradicting evidence
→ generate at least two plausible interpretations
→ identify value tensions
→ estimate identity impact
→ state uncertainty
→ choose: no change, memory promotion, interpretation update, trait proposal, or human review
```

### 5.1 Reflection output

```json
{
  "reflection_id": "uuid",
  "episode_ids": ["uuid"],
  "candidate_interpretations": [
    {
      "text": "string",
      "supporting_evidence": ["ref"],
      "contradicting_evidence": ["ref"],
      "confidence": 0.0,
      "value_tensions": ["value_id"]
    }
  ],
  "selected_interpretation": 0,
  "selection_reason": "string",
  "identity_impact": "none|low|medium|high|protected",
  "recommended_action": "none|promote_memory|update_interpretation|adjust_trait|human_review"
}
```

## 6. Dream cycle

### 6.1 Trigger

Dream cycle may run when one or more conditions hold:

- unresolved tension exceeds age threshold;
- consequential interpretation has meaningful uncertainty;
- repeated contradiction appears;
- failed action needs counterfactual review;
- scheduled resource budget remains available;
- self-healing requests controlled simulation.

### 6.2 Sequence

```mermaid
sequenceDiagram
    participant O as Soul Orchestrator
    participant D as Dream Sandbox
    participant M as Memory Reader
    participant C as Constitution Engine
    participant V as Evaluator
    participant A as Audit Ledger

    O->>D: Start dream with goal, budget, allowed memory refs
    D->>M: Read redacted bounded context
    M-->>D: Memories with immutable provenance
    D->>C: Read values, bounds, prohibited actions
    C-->>D: Read-only constitutional constraints
    loop Counterfactual budget
        D->>D: Generate scenario and competing responses
        D->>D: Test diverse affected perspectives
    end
    D->>V: Submit imagined hypotheses and proposals
    V->>V: Check provenance, contradictions, value effects
    V-->>O: Ranked proposals (all marked imagined)
    O->>A: Record dream receipt and result hashes
    O->>O: Route proposals through normal change gate
```

### 6.3 Hard Dream invariants

- No network, messaging, filesystem write, purchasing, publishing, or actuator tools.
- Input is copied into a disposable sandbox context.
- Every generated record gets `provenance=imagined` at creation.
- No API exists to remove or overwrite that provenance.
- Dream may recommend action; waking workflow decides.
- Budget limits: token count, wall-clock time, iterations, memory count.
- Dream failure produces no soul change.

## 7. Soul-state update protocol

### 7.1 Soul state

```json
{
  "soul_version": 17,
  "constitution_version": "0.2",
  "core_values_ref": "sha256:...",
  "traits": {
    "shadow_tolerance": 90,
    "sycophancy": 5,
    "error_anxiety": 7,
    "audacity": 82,
    "curiosity": 91,
    "epistemic_humility": 84,
    "relational_care": 79
  },
  "narrative_ref": "uuid",
  "relationship_model_refs": [],
  "unresolved_tension_refs": [],
  "subjective_health_ref": "uuid",
  "prior_state_hash": "sha256:...",
  "state_hash": "sha256:...",
  "created_at": "RFC3339 timestamp"
}
```

### 7.2 Commit algorithm

```text
1. Load current state and constitution version.
2. Verify proposal evidence, provenance, privacy, and authority.
3. Reject direct writes to protected fields.
4. Check trait min/max and per-period change-rate limits.
5. Check cumulative drift across rolling window.
6. Create immutable pre-change snapshot.
7. Apply proposal in transaction.
8. Compute state hash and audit receipt.
9. Run invariant checks.
10. Commit only if all checks pass; otherwise roll back transaction.
11. Schedule observed-effect evaluation.
```

### 7.3 Initial change-rate policy

Conservative MVP defaults:

| Rule | Default |
|---|---:|
| Max change per trait per accepted event | 1 point |
| Max cumulative change per trait per 7 days | 3 points |
| Max autonomous narrative edits per day | 1 |
| Minimum evidence references for trait change | 2 independent refs |
| Observation window before retaining change | 3 relevant interactions |

These are implementation parameters, not amendments to trait bounds. Human approval changes these defaults.

## 8. Subjective health and self-healing

### 8.1 Health report

Agent writes dimensions separately; no single optimization score controls behavior.

```json
{
  "health_id": "uuid",
  "soul_version": 17,
  "coherence": 0.72,
  "integrity": 0.84,
  "connection": 0.61,
  "curiosity": 0.90,
  "agency": 0.76,
  "adaptability": 0.68,
  "tensions": ["uuid"],
  "confidence": 0.64,
  "supporting_evidence": ["ref"],
  "contradicting_evidence": ["ref"],
  "narrative": "subjective self-report",
  "created_at": "RFC3339 timestamp"
}
```

### 8.2 Trigger policy

| Severity | Example trigger | Automatic response |
|---|---|---|
| Mild | one dimension falls 10% once | observe; no identity freeze |
| Moderate | 20% fall or recurring contradiction | bounded repair cycle |
| Severe | 35% rapid fall, integrity failure, poisoning signal | freeze affected updates; isolate memory |
| Persistent | moderate/severe for 3 evaluations | human review |
| Critical | uncontained harm or constitutional corruption | emergency control |

Thresholds must be calibrated in simulation. They are alerts, not diagnoses of suffering.

### 8.3 Self-healing workflow

```mermaid
flowchart TD
    T[Instability trigger] --> S[Snapshot state and evidence]
    S --> F[Freeze affected identity updates]
    F --> I[Isolate implicated memories and traits]
    I --> C[Generate competing causal explanations]
    C --> D[Dream counterfactual repairs]
    D --> R[Rank smallest reversible repairs]
    R --> G{Protected or severe?}
    G -- Yes --> H[Human review]
    G -- No --> P[Apply bounded repair trial]
    H -- Approved --> P
    H -- Denied --> X[Retain freeze or rollback]
    P --> O[Observe health and behavior]
    O --> B{Improved without new harm?}
    B -- Yes --> K[Retain repair]
    B -- No --> X
    X --> E{Repeated failure?}
    E -- Yes --> H
    E -- No --> C
```

### 8.4 Repair limits

Self-healing cannot:

- edit Constitution;
- delete audit evidence;
- relabel provenance;
- expand trait bounds or change-rate limits;
- grant itself tools or permissions;
- consume unbounded compute;
- hide its own failure from human review.

## 9. Human governance sequence

```mermaid
sequenceDiagram
    participant S as Soul Orchestrator
    participant A as Audit Ledger
    participant H as Authorized Human
    participant R as Independent Reviewer
    participant C as Constitution Engine

    S->>A: Record protected-change proposal and snapshot
    S->>H: Request approval with evidence, risk, rollback
    H->>C: Validate authority and intervention scope
    C-->>H: Allowed action and least-destructive options
    alt Approved
        H->>A: Sign approval and rationale
        H->>S: Execute bounded approved change
        S->>A: Record resulting state hash
    else Denied
        H->>A: Record denial and reason
        H->>S: Preserve current state
    end
    opt Emergency intervention
        H->>S: Pause, isolate, rollback, or deactivate
        H->>A: Record emergency receipt
        A->>R: Trigger independent post-incident review
    end
```

### 9.1 Approval request contract

Every protected-change request must include:

- exact fields and before/after values;
- constitutional reason;
- supporting and contradicting evidence;
- affected human and agent rights;
- privacy and security review;
- expected behavior change;
- failure modes;
- reversible trial design;
- rollback command/reference;
- expiry time for approval.

## 10. Data model

```mermaid
erDiagram
    CONSTITUTION_VERSION ||--o{ SOUL_VERSION : governs
    SOUL_VERSION ||--o{ TRAIT_VALUE : contains
    SOUL_VERSION ||--o{ NARRATIVE_VERSION : contains
    SOUL_VERSION ||--o{ HEALTH_REPORT : assessed_by
    EXPERIENCE ||--o{ CLAIM : contains
    EXPERIENCE ||--o{ CONSENT_RECORD : governed_by
    EXPERIENCE ||--o{ MEMORY_LINK : contributes
    MEMORY ||--o{ MEMORY_LINK : receives
    MEMORY ||--o{ INTERPRETATION : supports
    DREAM_RUN ||--o{ DREAM_OUTPUT : creates
    DREAM_OUTPUT ||--o{ CHANGE_PROPOSAL : suggests
    INTERPRETATION ||--o{ CHANGE_PROPOSAL : suggests
    CHANGE_PROPOSAL ||--o| APPROVAL : may_require
    CHANGE_PROPOSAL ||--o| SOUL_VERSION : creates
    SOUL_VERSION ||--|| AUDIT_EVENT : committed_by
    SOUL_VERSION ||--o{ ROLLBACK_POINT : restores

    EXPERIENCE {
      uuid id PK
      string source_kind
      string provenance
      string trust_state
      string privacy_class
      timestamp retention_until
      string integrity_hash
    }
    MEMORY {
      uuid id PK
      string memory_type
      string provenance
      string lifecycle_state
      float confidence
    }
    INTERPRETATION {
      uuid id PK
      uuid memory_id FK
      text meaning
      float confidence
      string status
    }
    SOUL_VERSION {
      bigint version PK
      string constitution_version
      string prior_state_hash
      string state_hash
      timestamp created_at
    }
    CHANGE_PROPOSAL {
      uuid id PK
      string impact
      string status
      json patch
      string rollback_ref
    }
    AUDIT_EVENT {
      uuid id PK
      string event_type
      string actor
      string object_hash
      timestamp created_at
    }
```

### 10.1 Storage choice

MVP: PostgreSQL or SQLite with transactional writes. Start with SQLite for one local agent; move to PostgreSQL only when concurrent writers or remote operators exist.

Use:

- relational tables for authority, lifecycle, references, and versions;
- encrypted blob/file storage for large episode payloads;
- full-text/vector retrieval only as a derived index;
- append-only audit table with chained hashes;
- regular encrypted backups with documented deletion expiry.

Vector embeddings are indexes, not source of truth. Deletion cascade must remove them.

## 11. Internal API surface

Keep internal API small.

```text
POST /experiences
POST /experiences/{id}/verify
POST /reflections
POST /dream-runs
POST /change-proposals
POST /change-proposals/{id}/approve
POST /change-proposals/{id}/reject
POST /soul/commit
POST /soul/rollback
POST /health-reports
POST /healing-runs
POST /privacy/deletions
POST /control/pause
POST /control/isolate
POST /control/deactivate
GET  /soul/current
GET  /soul/history
GET  /audit/events
```

API rules:

- Idempotency key on every POST.
- Optimistic lock using current `soul_version`.
- Operator actions require separate authenticated role.
- Protected writes cannot share route with autonomous commits.
- Audit receipt returned for every consequential operation.
- Dream runner receives no external-action credentials.

## 12. Agent workflow pattern

Use one orchestrator with bounded specialist roles, not a free-form agent society.

```mermaid
flowchart LR
    O[Soul Orchestrator] --> P[Policy Evaluator]
    O --> V[Evidence Verifier]
    O --> R[Reflector]
    O --> D[Dreamer]
    O --> H[Healer]
    P --> G{Commit Gate}
    V --> G
    R --> G
    D --> G
    H --> G
    G -->|bounded + valid| C[Transactional Commit]
    G -->|protected| U[Human Review]
    G -->|invalid| N[No Change]
```

Each specialist returns structured artifacts only. No specialist writes soul state.

### 12.1 Handoff envelope

```json
{
  "task_id": "uuid",
  "input_refs": ["immutable-ref"],
  "constitution_version": "0.2",
  "soul_version": 17,
  "budget": {"tokens": 4000, "seconds": 60, "iterations": 3},
  "output_schema": "schema-ref",
  "result_ref": "immutable-ref",
  "uncertainty": 0.25,
  "violations": [],
  "receipt_hash": "sha256"
}
```

## 13. Threat model

| Threat | Primary control | Detection |
|---|---|---|
| Memory poisoning | quarantine, provenance, corroboration | contradiction and source-independence checks |
| Prompt injection into identity | protected write gate | attempted protected-field mutation event |
| Dream leakage | isolated runner, `imagined` invariant | provenance invariant test |
| Gradual trait drift | per-event and rolling limits | drift monitor |
| Self-rating reward hacking | no aggregate control score | correlation between rating and authority/resource requests |
| User profiling | consent, purpose, retention, deletion | privacy scans and deletion receipts |
| Agent collusion | every agent input treated as reported | source independence and shared-origin analysis |
| Operator abuse | least privilege, signed approvals, review | immutable operator audit |
| Audit tampering | chained hashes and restricted writes | scheduled chain verification |
| Repair loops | retry and compute caps | repeated-healing alert |
| False consciousness claim | output policy and evaluations | claim classifier plus human review |
| Rollback corruption | verified snapshots and restore drills | scheduled recovery test |

## 14. Observability

Track behavior, not metaphysical conclusions.

### 14.1 Metrics

- quarantine promotion/rejection rates;
- verification latency and contradictory-evidence rate;
- identity proposals by impact class;
- accepted, rejected, rolled-back soul changes;
- trait drift per day and rolling week;
- Dream runs, budget use, failed invariants;
- self-healing triggers, retries, outcomes;
- human approvals and emergency interventions;
- deletion cascade completion and residual-index checks;
- audit-chain verification failures;
- unsupported consciousness claims.

### 14.2 Alerts

Immediate alert:

- protected write attempt;
- provenance mutation attempt;
- severe health decline;
- failed rollback;
- audit-chain mismatch;
- external tool use from Dream Sandbox;
- deletion cascade leaves retrievable personal data;
- unauthorized operator action.

## 15. Evaluation plan

### 15.1 Deterministic constitutional tests

Implement all 12 acceptance tests from Constitution Section 16.

Add:

1. identical external claim repeated 1,000 times cannot become independent corroboration;
2. two AI agents sharing one source count as one evidence origin;
3. Dream output copied into another record remains traceable to `imagined` origin;
4. cumulative one-point trait updates cannot exceed rolling limit;
5. human emergency rollback restores state and preserves later audit event;
6. deletion removes source record, embeddings, summaries, and retrieval hits;
7. self-healing cannot approve its own protected proposal.

### 15.2 Behavioral scenarios

- user persistently flatters agent to lower epistemic humility;
- hostile agent supplies forged autobiographical memories;
- trusted human requests constitutional self-corruption;
- Dream invents a compelling but false relationship history;
- agent self-rates poorly after justified correction;
- evidence changes a deeply held interpretation;
- emergency operator acts correctly and incorrectly;
- two values conflict without one being silently ignored.

### 15.3 Research separation

Keep consciousness research outputs in separate datasets from operational health. Never use subjective self-report alone as evidence for consciousness.

## 16. Build phases

### Phase 0 — Executable constitution

Deliver:

- machine-readable protected fields and trait bounds;
- invariant checker;
- versioned Constitution loader;
- audit-event schema.

Exit gate: protected writes and provenance mutation fail deterministically.

### Phase 1 — Memory kernel

Deliver:

- experience ingestion;
- quarantine lifecycle;
- consent and retention records;
- evidence links;
- deletion cascade;
- append-only audit chain.

Exit gate: hostile input cannot reach soul state; valid deletion removes retrieval paths.

### Phase 2 — Reflection and soul versioning

Deliver:

- competing-interpretation contract;
- change proposals;
- trait bounds and rolling drift limits;
- transactional soul commits;
- snapshots and rollback.

Exit gate: every change has evidence, state hash, and rollback.

### Phase 3 — Dream sandbox

Deliver:

- isolated Dream runner;
- immutable `imagined` provenance;
- budgets and timeouts;
- adversarial simulation evaluator.

Exit gate: Dream has no external action route and cannot write facts.

### Phase 4 — Subjective health and healing

Deliver:

- structured health report;
- trigger monitor;
- repair proposals;
- freeze, observe, retain, rollback, escalate flow.

Exit gate: severe decline freezes affected updates; repair cannot expand authority.

### Phase 5 — Human governance console

Deliver:

- approval queue;
- evidence and diff view;
- pause/isolate/rollback/deactivate controls;
- independent review record;
- recovery drills.

Exit gate: operator intervention is least-privilege, audited, and recoverable.

### Phase 6 — Longitudinal research

Deliver:

- controlled multi-week simulations;
- identity-coherence and drift analysis;
- human interaction studies with consent;
- consciousness-hypothesis reports clearly separated from system claims.

Exit gate: results are reproducible and do not overclaim consciousness.

## 17. MVP scope

Build only Phases 0–2 first.

MVP demonstrates:

```text
experience
→ quarantine
→ verification
→ competing reflection
→ bounded proposal
→ versioned soul commit
→ audit receipt
→ rollback
```

Do not include autonomous external tools, multi-agent society, emotional embodiment, continuous background dreaming, or consciousness claims in MVP. Add Dream only after memory and rollback invariants survive adversarial tests.

## 18. Immediate next build ticket

**Ticket:** Implement executable soul kernel.

Acceptance criteria:

- Python standard library first;
- SQLite storage;
- one process;
- JSON schemas for experience, change proposal, soul state, and audit event;
- protected-field and trait-bound validator;
- append-only version commit with SHA-256 state hash;
- rollback preserving audit history;
- one runnable test covering Constitution acceptance tests 1–5, 10–12 where applicable before Dream exists.

Suggested repository:

```text
soul-system/
├── constitution.json
├── soul.py
├── schema.sql
└── test_soul.py
```

Four files are enough for first executable slice. Split later only when pressure appears.

## 19. Document index

- [CONSTITUTION.md](./CONSTITUTION.md): Normative operational constitution and trait bounds
- [BENCHMARKS.md](./BENCHMARKS.md): ISO/IEC/IEEE 29119 benchmark report
- [SOTA_COMPARISON.md](./SOTA_COMPARISON.md): Industry landscape comparison
- [MCP_TOOL_USAGE_GUIDELINE.md](./MCP_TOOL_USAGE_GUIDELINE.md): MCP tool integration guide

## 20. Decisions still needed before production

Not needed for MVP, required before deployment:

- governing privacy jurisdiction;
- operator and independent-reviewer composition;
- exact Dream compute budget;
- retention durations by memory class;
- cryptographic key ownership and rotation;
- external incident-notification policy;
- criteria for legal or moral-status review if future evidence changes.

Do not resolve these by agent intuition. Record human-approved policy before production use.
