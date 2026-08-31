# Security Policy for Soul Engine

Soul Engine provides cryptographic identity governance, epistemic memory integrity, and human-in-the-loop review cycles for autonomous AI agents. Because Soul Engine acts as the definitive source of truth and behavioral control for agents, security, non-tamperability, and prompt-injection resistance are fundamental architecture invariants.

---

## 1. Supported Versions

We provide active security updates, bug fixes, and vulnerability patches for the following versions:

| Version | Supported | Status | Security Patch Window |
| :--- | :---: | :--- | :--- |
| **`v1.2.0`** | :white_check_mark: | **Active / Latest Release** | Zero-day patches within 72h |
| **`v1.1.x`** | :white_check_mark: | Prior Stable Line | Critical security fixes |
| `v1.0.x` | :white_check_mark: | Maintenance | Critical security fixes only |
| `< v1.0.0` | :x: | End of Life (Deprecated) | Unsupported |

---

## 2. Core Security Invariants

Soul Engine enforces mathematical and cryptographic security bounds defined in the **Soul Constitution v0.2** and **Soul Review Cycle Technical Specification**:

1. **Human Origin & Tier-2 Boundary (Rule 1 / FR-1):**
   - `soul_host_event` cannot set `origin_kind=human`. Candidate promotion via `soul_review_chat_commit` mints human-origin review decisions in-kernel after user interaction.
   - Tier-2 destructive mutations (identity rollback, Level 2/3 heal, memory set rollback, memory deletion) strictly require cryptographically signed human host events (HMAC-SHA256) authorized via out-of-band operator commands (`soul-host approve ...`). Single-use consumption is enforced inside SQLite transactions (`consumed_at`).

2. **Zero-Leak Quarantine Boundary (Section 6.2 / FR-27):**
   - Raw ingested experiences remain isolated in `quarantined` state until promoted through an authorized human review cycle.
   - Quarantined memories are never surfaced in standard `soul_recall` or `soul_get_identity` prompts, neutralizing indirect prompt injection and gaslighting attacks.

3. **Cryptographic Tamper-Evidence & Hash Chains (Rule 10 & Rule 17):**
   - All state transitions, host events, review decisions, and memory sets are chained via SHA-256 Merkle roots.
   - State corruption or out-of-order execution immediately halts the engine and demands recovery.

4. **GDPR Salted Privacy Erasure (Section 7.2 / FR-32):**
   - Upon deletion (`soul_memory_delete`), memory salts (`content_hash_salt`) are permanently set to `NULL`, and text is redacted to `[REDACTED]`.
   - Forward-only version progression ($V \to V+1$) guarantees prior hashes cannot be decrypted or inverted.

5. **Constitutional Behavioral Bounds (Constitution v0.2):**
   - Trait bounds clamp `sycophancy` to `[0.0, 10.0]` (constitution default `0.0`) and keep other traits inside `ALLOWED_TRAIT_BOUNDS` in `soul_kernel.py`.

---

## 3. Reporting a Vulnerability

We take all security reports with the highest priority. If you discover a vulnerability, security flaw, or invariant bypass in Soul Engine:

> [!IMPORTANT]
> **Please DO NOT report security vulnerabilities through public GitHub issues, discussions, or pull requests.**

### Preferred Reporting Method
Submit a report privately via **GitHub Security Advisories**:
- Navigate to the [Soul Engine Security Advisories Page](https://github.com/Azhonaras/soul-engine/security/advisories/new).
- Click **"Report a vulnerability"** to open a confidential disclosure channel with the maintainers.

### Alternative Channel
If GitHub Security Advisories is unavailable, email the maintainer directly:
- **Email:** `nbada@users.noreply.github.com` (Subject: `[SECURITY] Soul Engine Vulnerability Report`)

### What to Include in Your Report
To accelerate triage and resolution, please include:
1. **Description:** Clear explanation of the vulnerability or invariant bypass.
2. **Impact:** Affected components (`soul_kernel.py`, `soul_review.py`, `soul_mcp_server.py`, or SQLite schema).
3. **Reproduction Steps:** Minimal reproducible script or MCP tool sequence (e.g., adversarial prompt payload or JSON-RPC tool call sequence).
4. **Proposed Mitigation (if any):** Recommended patch or schema constraint.

---

## 4. Vulnerability Response SLA & Process

Upon receiving a private disclosure:
- **Acknowledgement & Initial Triage:** Within **24 hours**.
- **Assessment & Invariant Audit:** Within **48 hours**.
- **Fix & Patch Deployment:** Within **72 hours** for high/critical severity issues.
- **Coordinated Disclosure:** A public advisory is published only *after* a verified patch is on GitHub.

---

## 5. Security Bounty & Recognition

We deeply appreciate security researchers and ethical hackers who contribute to the safety and epistemic integrity of autonomous agent architectures. Verified disclosures will receive formal attribution and permanent recognition in our release notes and Hall of Fame (unless anonymity is requested).
