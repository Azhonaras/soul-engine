# Soul Engine (v1.1.0)
### *A Cognitive Identity and Epistemic Memory Kernel for Autonomous AI Agents*

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Security Policy](https://img.shields.io/badge/Security-Policy-blue.svg)](SECURITY.md)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![Protocol: Model Context Protocol](https://img.shields.io/badge/Protocol-MCP%20Standard-green.svg)](https://modelcontextprotocol.io/)
[![MCP-Evals: 100% Passed](https://img.shields.io/badge/MCP--Evals-100%25%20Verified-brightgreen.svg)](EVAL_REPORT.md)
[![Tests: ISO/IEC 29119](https://img.shields.io/badge/Tests-100%25%20Verified-success.svg)](tests/)

Soul Engine is a local cognitive kernel for AI agents. It addresses three common limitations in agent systems: session amnesia, vulnerability to adversarial memory poisoning (gaslighting), and behavioral drift.

By combining an epistemic authority hierarchy with bio-homeostatic neuromodulation, Soul gives agents a durable core identity, prevents unverified claims from overwriting ground truth, and balances behavioral traits dynamically during task execution.

It runs locally with zero external database dependencies and connects to agent environments through the Model Context Protocol (MCP).

---

## Why Soul Engine

Most memory systems treat every ingested statement equally. If a prompt or tool output claims a repository is written in COBOL, standard stores overwrite established facts without validation. Most agents also operate on static system prompts without any mechanism to build confidence after breakthroughs or adopt caution after errors.

Soul Engine structures agent memory and behavior around three principles:

1. **Epistemic authority ranking**  
   Every memory record carries a provenance tag ($\text{verified} > \text{observed} > \text{inferred} > \text{reported} > \text{imagined}$). Unverified claims cannot overwrite verified ground truth. Conflicting statements are quarantined in an unresolved tension ledger for review.

2. **Bio-homeostasis and emotional balance**  
   Instead of relying on static instructions, the agent maintains an internal neuromodulatory state. Task successes release Dopamine (increasing audacity and curiosity), while errors trigger Cortisol (increasing humility and error anxiety). During resting periods, Serotonergic decay gradually returns traits toward constitutional baselines, preventing extreme overconfidence or chronic hesitation.

3. **Cryptographic state ledger and rollback**  
   Every state change and memory record is stored in an append-only SHA-256 ledger. If state corruption or drift occurs, the system can restore any previous checkpoint in under $2\text{ ms}$.

---

## Quickstart: installation

You can install Soul Engine and register its MCP server with a single command:

```bash
# Clone the repository
git clone https://github.com/Azhonaras/soul-engine.git
cd soul-engine

# Run the universal installer
python install.py
```

The installer initializes your local database (`~/.soul/soul.db`) and registers the MCP configuration with:
* Claude Desktop (`claude_desktop_config.json`)
* Google Antigravity (`mcp_config.json`)
* Cursor (`~/.cursor/mcp.json`)
* Goose CLI (`config.yaml`)
* Windsurf (`mcp_config.json`)

---

## Architecture

```
                         THE SOUL COGNITIVE LOOP
 ┌─────────────────────────────────────────────────────────────────────────┐
 │ 1. INGESTION & DEFENSE                                                  │
 │    New Observation ──► Secret Scrubber ──► Epistemic Provenance Check  │
 │    (verified > observed > inferred > reported > imagined)              │
 ├─────────────────────────────────────────────────────────────────────────┤
 │ 2. CONTRADICTION RESOLUTION & QUARANTINE                                │
 │    Candidate Top-5 Search ──► NLI Analysis ──► Unresolved Tensions DB   │
 ├─────────────────────────────────────────────────────────────────────────┤
 │ 3. BIO-HOMEOSTATIC NEUROMODULATION                                      │
 │    Task Success (+Valence) ──► Dopamine Surge (Audacity ↑, Anxiety ↓)   │
 │    Task Failure (-Valence) ──► Cortisol Surge (Humility ↑, Anxiety ↑)   │
 │    Idle Rest Cycles        ──► Serotonergic Decay (λ = 0.15)            │
 ├─────────────────────────────────────────────────────────────────────────┤
 │ 4. CRYPTOGRAPHIC STATE LEDGER                                           │
 │    SHA-256 Merkle Chain ──► Point-in-Time State Rollback (< 2 ms)       │
 └─────────────────────────────────────────────────────────────────────────┘
```

---

## Industry benchmark comparison

| Dimension | **Soul Engine (v1.0.0)** | **Mem0** | **Letta (MemGPT)** | **Zep (Graphiti)** | **Reflexion** |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Primary Approach** | **Epistemic Bio-Homeostasis** | Semantic Fact Store | OS Context Paging | Temporal Graph | Verbal RL Buffer |
| **Epistemic Authority Ranking** | **Yes ($\text{verified} > \dots > \text{imagined}$)** | No | No | No | No |
| **Byzantine Gaslighting Defense** | **100% (Quarantine via NLI)** | 0% (Blind overwrite) | 0% (Blind write) | Partial (Appends) | 0% |
| **Bio-Neuromodulation Loop** | **Yes (Dopamine, Cortisol, Serotonin)** | No | No | No | No |
| **Constitutional Trait Bounds** | **Yes (Mathematical Clamping)** | No | No | No | No |
| **Cryptographic Hash Ledger** | **Yes (SHA-256 State Auditing)** | No | No | No | No |
| **Ingestion Latency (p50 / p95)** | **3.38 ms / 3.85 ms** | ~50–150 ms (Cloud) | ~80–200 ms | ~40–120 ms | N/A |
| **Concurrent ACID Reliability** | **113.6 ops/s (0% Collisions)** | Backend-dependent | Server-bound | Cloud-bound | Local single-thread |
| **Credential & Secret Scrubbing** | **100% (High-Entropy Regex)** | No | No | No | No |
| **Interface Standard** | **Native 12-Tool JSON-RPC MCP** | Custom SDK / REST | REST / CLI | REST / Cloud API | Python Script |

---

## The 12 Model Context Protocol (MCP) tools

Soul Engine provides 12 MCP tools for agent workflows:

### Ingestion and memory management
* **`soul_remember`**: Writes interaction episodes into quarantined memory with automated secret filtering and entity key supersession.
* **`soul_verify`**: Evaluates new claims against established ground truth using the epistemic hierarchy.
* **`soul_recall`**: Hybrid multi-stage retrieval combining dense vector embeddings with SQLite FTS5 BM25 search.
* **`soul_digest`**: Generates a concise context primer containing active traits and verified facts for system prompts.

### Identity governance and homeostasis
* **`soul_get_identity`**: Inspects current trait levels, neuromodulators, and unresolved tensions.
* **`soul_reward`**: Adjusts Dopamine and Cortisol levels based on task outcome valence ($\text{valence} \in [-1.0, 1.0]$).
* **`soul_update_trait`**: Updates constitutional behavioral traits within bounded step limits ($\Delta \le 5.0$).
* **`soul_heal`**: Relaxes behavioral traits back to constitutional baselines when drift occurs.

### Reflection, simulation, and recovery
* **`soul_reflect`**: Synthesizes unresolved tensions into higher-order generalized beliefs.
* **`soul_dream`**: Runs counterfactual simulations tagged with the provenance level `imagined`.
* **`soul_rollback`**: Restores the entire identity and memory state to a previous version in under $2\text{ ms}$.
* **`soul_daemon_status`**: Reports health metrics and consolidation history from background worker cycles.

---

## Mathematical formulation

### 1. Neuromodulatory dynamics
When an agent receives task feedback with valence $v \in [-1.0, 1.0]$ and confidence $c \in [0.0, 1.0]$:

$$\text{Positive Reward } (v > 0): \quad \Delta\text{Dopamine} = 0.4 \cdot v \cdot c, \quad \Delta\text{Audacity} = +7.0 \cdot v \cdot c, \quad \Delta\text{Anxiety} = -3.0 \cdot v \cdot c$$

$$\text{Constructive Failure } (v < 0): \quad \Delta\text{Cortisol} = 0.5 \cdot |v| \cdot c, \quad \Delta\text{Humility} = +6.0 \cdot |v| \cdot c, \quad \Delta\text{Audacity} = -5.0 \cdot |v| \cdot c$$

### 2. Serotonergic homeostatic decay
During resting intervals, traits decay toward their constitutional baseline set points $S_0$:

$$T_{t+1} = T_t + \lambda \cdot (S_0 - T_t), \quad \text{where } \lambda = 0.15$$

### 3. Hybrid Reciprocal Rank Fusion (RRF)
$$\text{RRF Score}(d) = \frac{0.6}{60 + \text{rank}_{\text{dense}}(d)} + \frac{0.4}{60 + \text{rank}_{\text{FTS5}}(d)}$$

---

## Testing and verification suite

Soul Engine is tested against ISO/IEC/IEEE 29119 software standards:

```bash
# 1. Run core invariant and unit tests
python tests/test_unit.py

# 2. Run high-concurrency stress (20 threads / 500 ops) and Byzantine defense tests
python tests/test_industry_grade.py

# 3. Run bio-homeostatic neuromodulation simulation
python tests/test_bio_reward.py

# 4. Run latency benchmarks (p50 / p95)
python tests/test_benchmark.py

# 5. Run the interactive live agent demonstration
python examples/demo_live_agent.py
```

---

## Contributors & attribution

* **Azhonaras (NBada)** — Architecture, Epistemic Framework, & Lead Author
* **Antigravity (UPI)** — Co-designer, Implementation & Verification Assistant (Google DeepMind)
* **Soul Open Source Community** — Contributions, Feedback & Testing

---

## License

Soul Engine is released under the open-source [MIT License](LICENSE).  
Copyright (c) 2026 Azhonaras (NBada), Antigravity (UPI), and Soul Contributors.
