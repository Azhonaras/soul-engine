# Contributing to Soul Engine

Thank you for your interest in contributing to Soul Engine. We welcome contributions from developers, researchers, and engineers.

---

## Development setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/Azhonaras/soul-engine.git
   cd soul-engine
   ```

2. **Create a virtual environment:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install development dependencies:**
   ```bash
   pip install -r requirements-dev.txt
   pip install -e .
   ```

---

## Running tests and verification

Before submitting a pull request, ensure the suite passes (same command as CI):

```bash
python -m unittest discover -s tests

# mechanism harness (pre-registered P1-P4 criteria)
python soul_mechanism_harness.py
```

---

## Architectural invariants to preserve

When contributing code to `soul_kernel.py` or `soul_mcp_server.py`, you must preserve these core invariants:

1. **Epistemic Authority Hierarchy**:
   $$\text{verified} (5) > \text{observed} (4) > \text{inferred} (3) > \text{reported} (2) > \text{imagined} (1)$$
   A lower-authority provenance must never silently overwrite higher-authority ground truth.
2. **ACID transaction isolation**:
   All database writes must execute under `BEGIN IMMEDIATE;` to guarantee zero version race condition collisions.
3. **Neuromodulatory clamping**:
   All traits must strictly adhere to their constitutional bounds $[min, max]$ defined in the Genesis Constitution.
3b. **Finite-number trust boundary**:
   All reward valences, confidences, and dream likelihoods must be `math.isfinite`-checked *before* clamping (`min/max` do not reject NaN). Out-of-range likelihoods clamp to [-1, 1]; non-finite ones are excluded from means, never averaged in.
3c. **RPE expectation integrity**:
   Expectations update via the Robbins-Monro rate (`alpha_for(ctx)`), never a constant alpha; visit counts persist in `rpe_expectations.updates`. Imagined content never writes expectations — dreams touch only the trust EWMA.
4. Preserve human origin: MCP cannot mint `origin_kind=human`. Interview starts at work-done / subject-finished / before-plan (Review plan). Completing this run’s picks promotes (`soul_review_chat_commit`). `/seacom` for leftover pending. Optional tty: `soul_host` (`SEAL` then `COMMIT`). Heal, rollback, and delete in chat pass `session_id`.

---

## Pull request guidelines

1. Create a feature branch: `git checkout -b feature/your-feature-name`.
2. Commit your changes with clear, descriptive commit messages.
3. Push to your fork and submit a Pull Request against `main`.
4. Ensure CI tests pass across all target environments.

---

## Contributors & attribution

* **Azhonaras (Navid Badami)**: Creator, Lead Architect & Maintainer
* **Antigravity (UPI)**: Co-author & Verification Assistant (v1.1.0)
* **Soul Open Source Community**: Contributions, Feedback & Testing
