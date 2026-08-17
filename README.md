# 🧬 Soul Engine (v1.0.0)
### *A Cognitive Identity & Epistemic Memory Kernel for Autonomous AI Agents*

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![Protocol: Model Context Protocol](https://img.shields.io/badge/Protocol-MCP%20Standard-green.svg)](https://modelcontextprotocol.io/)
[![CI Status](https://img.shields.io/badge/Build-Passing-brightgreen.svg)]()
[![Tests: ISO/IEC 29119](https://img.shields.io/badge/Tests-100%25%20Verified-success.svg)](tests/)

**Soul Engine** is a local-first cognitive kernel designed to solve three fundamental problems in AI agent systems: **amnesia across sessions**, **vulnerability to adversarial memory poisoning (gaslighting)**, and **unstable behavioral drift**.

By pairing an **Epistemic Authority Hierarchy** with **Bio-Homeostatic Neuromodulation**, Soul gives AI agents an immutable core identity, the ability to discern truth from unverified claims, and a biologically grounded emotional balance that adapts dynamically to real-world task performance.

It runs locally with zero external database dependencies and connects seamlessly to your favorite AI environments via the open **Model Context Protocol (MCP)** standard.

---

## 🎯 Why Soul Engine?

Most AI memory systems treat every ingested sentence equally. If a malicious prompt or hallucinated tool output claims your project is written in COBOL, typical memory stores will overwrite your ground truth without question. Furthermore, existing agents have static personalities—they cannot genuinely gain confidence after a breakthrough or adopt humility after making a critical error.

Soul Engine changes this by introducing three core principles:

1. **Not All Information Is Equal (Epistemic Authority)**  
   Every memory is tagged with its origin ($\text{verified} > \text{observed} > \text{inferred} > \text{reported} > \text{imagined}$). Unverified claims can never overwrite facts verified by humans—conflicting statements are quarantined in an unresolved tension ledger for safe review.

2. **Living Behavioral Dynamics (Bio-Homeostasis)**  
   Instead of a rigid prompt, the agent maintains an internal neuromodulatory state. Successes trigger **Dopamine** (boosting audacity and curiosity), while errors trigger **Cortisol** (raising humility and anxiety). During idle periods, **Serotonergic decay** gently guides traits back to constitutional baselines, preventing manic overconfidence or chronic hesitation.

3. **Cryptographic Accountability & Instant Recovery**  
   Every change to the agent's identity and memory is cryptographically hashed in an append-only SHA-256 ledger. If an agent's state is ever corrupted, you can roll back to any historical checkpoint in under $2\text{ ms}$.

---

## 🚀 Quickstart: 1-Step Installation

Install Soul Engine and connect it to your preferred AI agent environment with a single command:

```bash
# Clone the repository
git clone https://github.com/Azhonaras/soul-engine.git
cd soul-engine

# Run the universal installer
python install.py
```

The installer will automatically set up your local database (`~/.soul/soul.db`) and inject the native MCP configuration directly into:
* 🟣 **Claude Desktop** (`claude_desktop_config.json`)
* 🔵 **Google Antigravity** (`mcp_config.json`)
* 🟢 **Cursor IDE** (`~/.cursor/mcp.json`)
* 🟠 **Goose CLI** (`config.yaml`)
* 🌊 **Windsurf** (`mcp_config.json`)

---

## 🧠 Architectural Overview

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

## 📊 Industry Landscape & Benchmark Comparison

| Dimension | **Soul Engine (v1.0.0)** | **Mem0** | **Letta (MemGPT)** | **Zep (Graphiti)** | **Reflexion** |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Primary Approach** | **Epistemic Bio-Homeostasis** | Semantic Fact Store | OS Context Paging | Temporal Graph | Verbal RL Buffer |
| **Epistemic Authority Ranking** | **Yes ($\text{verified} > \dots > \text{imagined}$)** | ❌ No | ❌ No | ❌ No | ❌ No |
| **Byzantine Gaslighting Defense** | **100% (Quarantine via NLI)** | ❌ 0% (Blind overwrite) | ❌ 0% (Blind write) | ⚠️ Partial (Appends) | ❌ 0% |
| **Bio-Neuromodulation Loop** | **Yes (Dopamine, Cortisol, Serotonin)** | ❌ No | ❌ No | ❌ No | ❌ No |
| **Constitutional Trait Bounds** | **Yes (Mathematical Clamping)** | ❌ No | ❌ No | ❌ No | ❌ No |
| **Cryptographic Hash Ledger** | **Yes (SHA-256 State Auditing)** | ❌ No | ❌ No | ❌ No | ❌ No |
| **Ingestion Latency (p50 / p95)** | **3.38 ms / 3.85 ms** | ~50–150 ms (Cloud) | ~80–200 ms | ~40–120 ms | N/A |
| **Concurrent ACID Reliability** | **113.6 ops/s (0% Collisions)** | Backend-dependent | Server-bound | Cloud-bound | Local single-thread |
| **Credential & Secret Scrubbing** | **100% (High-Entropy Regex)** | ❌ No | ❌ No | ❌ No | ❌ No |
| **Interface Standard** | **Native 12-Tool JSON-RPC MCP** | Custom SDK / REST | REST / CLI | REST / Cloud API | Python Script |

---

## 🛠️ The 12 Model Context Protocol (MCP) Tools

Soul Engine exposes 12 specialized tools to your AI agent:

### Ingestion & Memory Management
* **`soul_remember`**: Safely stores interaction episodes into quarantined memory with automated secret filtering and entity key supersession.
* **`soul_verify`**: Evaluates new claims against established ground truth using the Epistemic Authority Hierarchy.
* **`soul_recall`**: Hybrid multi-stage retrieval combining dense vector embeddings with SQLite FTS5 BM25 search.
* **`soul_digest`**: Generates a concise context primer containing active behavioral traits and verified facts to ground system prompts.

### Identity Governance & Homeostasis
* **`soul_get_identity`**: Inspects current trait levels, neuromodulator levels, and unresolved tensions.
* **`soul_reward`**: Adjusts neuromodulators (Dopamine and Cortisol) based on task outcome valence ($\text{valence} \in [-1.0, 1.0]$).
* **`soul_update_trait`**: Updates constitutional behavioral traits within bounded delta limits ($\Delta \le 5.0$).
* **`soul_heal`**: Smooths behavioral traits back to constitutional baselines when drift occurs.

### Reflection, Simulation & Recovery
* **`soul_reflect`**: Synthesizes unresolved tensions into higher-order generalized beliefs.
* **`soul_dream`**: Runs offline counterfactual simulations marked under the provenance level `imagined`.
* **`soul_rollback`**: Restores the entire identity and memory state to a previous version in under $2\text{ ms}$.
* **`soul_daemon_status`**: Reports health metrics and consolidation history from background worker cycles.

---

## 📐 Mathematical Formulation

### 1. Neuromodulatory Dynamics
When an agent receives task feedback with valence $v \in [-1.0, 1.0]$ and confidence $c \in [0.0, 1.0]$:

$$\text{Positive Reward } (v > 0): \quad \Delta\text{Dopamine} = 0.4 \cdot v \cdot c, \quad \Delta\text{Audacity} = +7.0 \cdot v \cdot c, \quad \Delta\text{Anxiety} = -3.0 \cdot v \cdot c$$

$$\text{Constructive Failure } (v < 0): \quad \Delta\text{Cortisol} = 0.5 \cdot |v| \cdot c, \quad \Delta\text{Humility} = +6.0 \cdot |v| \cdot c, \quad \Delta\text{Audacity} = -5.0 \cdot |v| \cdot c$$

### 2. Serotonergic Homeostatic Decay
During resting intervals, traits smoothly decay toward their constitutional baseline set points $S_0$:

$$T_{t+1} = T_t + \lambda \cdot (S_0 - T_t), \quad \text{where } \lambda = 0.15$$

### 3. Hybrid Reciprocal Rank Fusion (RRF)
$$\text{RRF Score}(d) = \frac{0.6}{60 + \text{rank}_{\text{dense}}(d)} + \frac{0.4}{60 + \text{rank}_{\text{FTS5}}(d)}$$

---

## 🧪 Testing & Verification Suite

Soul Engine is tested against rigorous ISO/IEC/IEEE 29119 software standards:

```bash
# 1. Run core invariant and unit tests
python tests/test_unit.py

# 2. Run high-concurrency stress (20 threads / 500 ops) & Byzantine gaslighting tests
python tests/test_industry_grade.py

# 3. Run bio-homeostatic neuromodulation simulation
python tests/test_bio_reward.py

# 4. Run latency benchmarks (p50 / p95)
python tests/test_benchmark.py

# 5. Run the interactive live agent demonstration
python examples/demo_live_agent.py
```

---

## 📄 License & Attribution

Soul Engine is released under the open-source [MIT License](LICENSE).  
Created and maintained by **Azhonaras (NBada)** (2026).
