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

Before submitting a pull request, ensure all test suites pass:

```bash
# 1. Run core unit tests
python tests/test_unit.py

# 2. Run industrial concurrency & Byzantine defense test suite
python tests/test_industry_grade.py

# 3. Run bio-homeostatic neuromodulation simulation
python tests/test_bio_reward.py

# 4. Run latency & benchmark suite
python tests/test_benchmark.py
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
4. **Secret scrubbing**:
   Never persist high-entropy API keys (AWS, Stripe, JWT, DB passwords) to disk without masking.

---

## Pull request guidelines

1. Create a feature branch: `git checkout -b feature/your-feature-name`.
2. Commit your changes with clear, descriptive commit messages.
3. Push to your fork and submit a Pull Request against `main`.
4. Ensure CI tests pass across all target environments.

---

## Contributors & attribution

* **Azhonaras (NBada)** — Architecture, Epistemic Framework, & Lead Author
* **Antigravity (UPI)** — Co-designer, Implementation & Verification Assistant (Google DeepMind)
* **Soul Open Source Community** — Contributions, Feedback & Testing
