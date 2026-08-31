# Changelog

## 1.2.0 — 2026-08-26 (merge of the two 1.1.x lines)

Combines the 1.1.3U learning loop with the plan-wallet multi-agent solver
subsystem from the 1.1.2-beta branch. This is the release line going forward.

### Fixed (2026-08-26 external audit, round 2 — 15 findings)
- **Review commit/preview mismatch**: `remember` + `session_only` scope no
  longer silently dropped at commit; scope now honored exactly as previewed.
- **dream_trust corruption**: legit `0.0` trust (fully distrusted context) no
  longer coerced to `0.5` on restart (`float(v or 0.5)` bug).
- **Receipt replay gate**: `external_test` rewards require an unredeemed,
  well-formed evidence receipt (≥8 chars, `[A-Za-z0-9_-]`); duplicates and
  forgeries rejected at the kernel boundary.
- **`soul_dream_score` gated**: dream scoring requires a redeemed receipt;
  auto-fire path passes the triggering receipt through; MCP schema extended.
- **Order-dependent contradiction verdict** replaced with deterministic
  precedence: sealed/reviewed contradictions win; otherwise worst case.
- **`correct` decision now supersedes** the wrong fact it corrects (same
  supersession rule as `remember`), instead of leaving both live.
- MCP `soul_reward`: non-numeric valence/confidence returns structured
  rejection instead of crashing the tool call.
- `record_human_decision`: human event must match the cycle's user scope and
  session; function now takes the review lock (race-safe).
- `invalidate_provisional_cycle` refuses non-provisional or already-terminal
  cycles instead of blindly deferring them.
- Duplicate `_bump_wallet` definition removed (first shadowed copy deleted).
- Recall FTS stage now queries the table matching the doc list actually built
  (reviewed vs episodes) instead of wasting a guaranteed-empty bm25 query.
- Quarantine/raw recall scan capped (`max(limit*20, 2000)`) — unbounded
  episode loads impossible on large DBs.
- Protected identity update returns post-write state, not stale pre-write.
- Redundant `except (ImportError, Exception)` tuples narrowed to `ImportError`.
- Packaging drift fixed: setup.py is now a PEP 621 shim (metadata lives in
  pyproject.toml only); setuptools floor widened to `>=77,<84`; dead goose
  YAML target dropped from installer; "22 Active MCP Tools" → 23 in
  installer + README comparison table; archived doc header updated.
- New regression file `tests/test_round2_regressions.py` (8 tests).

### Known limitation (disclosed, design-level — deferred to 1.3)
- Chat-facing helpers (`apply_chat_review`, `_chat_human_event`, heal/
  rollback wrappers) mint `origin_kind="human"` events on behalf of the
  trusted host app. The kernel cannot verify humanness; enforced two-party
  approval needs host-side gating or externally-minted events (1.3 design).

### Added (from 1.1.2-beta, ported)
- **Plan-scoped solver wallets**: `plan_id` + `agent_id` + `task_id` keying;
  per-plan dopamine/cortisol overlay wallets isolated between concurrent
  agents and plans (`_wallet_key`, `_bump_wallet`, `_pick_wallet`).
- **Per-plan FIFO trimming** (`_trim_working`): one plan's overflow never
  evicts another live plan's traces.
- **`close_plan=true`**: single SQLite txn quarantines compact per-agent
  fail/succeed traces (`_solver_identity_texts`) and drops that plan's
  overlay; crash-safe (atomicity regression-tested). Other plans untouched.
- **In-plan recall policy**: recall caps read the session wallet when one is
  live, not identity bio; digest exposes scoped `session_neuromodulators`.
- **Idle self-score refusal**: `internal_*` rewards require an open plan or a
  live overlay — idle dopamine farming refused outright.
- Legacy single-overlay blobs auto-migrate to wallet store on first read.
- 12 subsystem tests ported into `bugfixes/test_bugfixes.py`.
- MCP surface: `soul_solver_step` / `soul_reward` / `soul_recall` /
  `soul_digest` schemas expose the new plan/agent params (verified via
  `tools/list` smoke test); matching `schemas/*.json` files updated.

### Kept from 1.1.3U (unchanged)
- Robbins-Monro RPE expectations with restart persistence (`rpe_expectations`),
- dream-RPE scoring + per-context trust modulation,
- NaN/inf rejection at all reward trust boundaries,
- mechanism harness P1-P4 criteria.

### Verification at merge time
- Full suite: 133 tests OK (`python -m unittest discover -s tests`
  includes the 65-test `bugfixes.test_bugfixes` via re-export shim).
- Harness: P1 MAE 0.057 / P2 dreams-help ratio 0.82 / P3 habituation pass /
  P4 persistence pass.
- Adversarial probes on merged surfaces: NaN via internal wallet path,
  corrupt store blob, legacy migration, 20+20-thread asymmetric wallet
  isolation, close_plan cross-plan safety — all pass.
- Evals gate extended to cover the plan-wallet subsystem: `wf_11`
  (wallet lifecycle: scoped steps, isolation, close_plan atomicity,
  sibling-plan survival) and `wf_12` (idle internal refusal, overlay-only
  self-score, identity untouched). Mutation-tested: disabling the kernel's
  idle-reward gate flips the runner verdict to FAILED — the gate is real.

## 1.1.3U — 2026-08-25 (upgrade over 1.1.3-beta)

Learning-loop release: the reward system becomes a convergent predictor and
dreams become a measurable learning mechanism. No schema-breaking changes;
`rpe_expectations` and `dream_simulations` columns are added lazily.

### Added
- **`soul_dream_score` MCP tool** (23 tools total): scores pending imagined
  outcomes against a realized result; emits per-dream `dream_rpe`. Auto-fires
  on negative `external_test` rewards.
- **`score_dreams_against_reality()`** kernel API: dream-RPE computation,
  trust EWMA update, audit entry (`dream_scored`).
- **Persistent RPE expectations**: new `rpe_expectations` table
  (`context_key`, `expected_value`, `updates`). Expectations and Robbins-Monro
  visit counts survive process restarts.
- **Robbins-Monro learning-rate schedule**: `alpha_n = alpha0 / (1 + 0.08 n)`
  per context. Constant-alpha TD leaves irreducible noise
  (`sigma * sqrt(alpha/(2-alpha))`); diminishing rates converge to ground truth.
- **Dream-trust modulation**: scored dreams update a per-context trust EWMA
  (`trust:<ctx>` rows). Trust scales the learning rate applied to REAL outcomes
  only (`alpha_eff = alpha0 * (0.5 + 0.5 * tau)`); imagined content never writes
  expectations directly (provenance hierarchy preserved).
- **Mechanism harness** `soul_mechanism_harness.py`: synthetic environment with
  hidden success rates; pre-registered pass/fail criteria P1-P4.
- **Adversarial regression tests** in `tests/test_dream_rpe_loop.py`
  (NaN/inf rejection, likelihood clamping, habituation curve).

### Changed
- Internal rewards (`internal_reflection`, `internal_dream`) are now RPE-gated:
  repeated identical self-signals habituate; dopamine ceiling 0.3 (overlay only).
- Dream branches accept optional signed `likelihood` in [-1, 1]; non-finite
  values excluded from prediction mean, out-of-range values clamped.
- Tool-count guard updated 22 -> 23 (`bugfixes/test_bugfixes.py`,
  README, ARCHITECTURE doc index).
- Version strings: `1.1.3` / `1.1.3-beta` -> `1.1.3U` across kernel, MCP server,
  review engine, installer, packaging, docs.

### Evidence (harness run, seed 20260825)
| Criterion | Target | Result |
|---|---|---|
| P1 expectation convergence (reality-only MAE) | < 0.15 | **0.057** |
| P2 dreams do not hurt learning | ratio <= 1.10 | **0.82** (dreams help: 0.047) |
| P3 self-praise habituation | last/first increment < 0.20 | **0.193** |
| P4 restart persistence of expectations | exact match | pass |

Seed robustness: MAE 0.053-0.070 across seeds 1001-1003. Full suite:
114 tests OK (`python -m unittest discover -s tests`).

### Academic anchors
- Schultz et al. 1998: dopamine = reward prediction error.
- Rescorla-Wagner: delta-rule habituation of repeated rewards.
- Robbins-Monro / Sutton & Barto: diminishing alpha for stochastic approximation.
- arXiv:2403.07979 (Overfitted Brain hypothesis): dreaming as replay improves
  generalization — implemented here as dream-vs-reality scoring.
- arXiv:2605.21384 (SpecBench): reward hacking — mitigated via internal-signal
  RPE gating + ceilings.

### Security hardening (same release)
- NaN/inf valence or confidence rejected at all three reward paths
  (`ValueError`) — previously NaN passed Python `min/max` clamps and poisoned
  neuromodulator state.
- Non-finite dream likelihoods excluded from prediction means.

### Upgrade notes
- Existing DBs: tables/columns created lazily on next boot; no migration step.
- `SOUL_ENGINE_VERSION` is now `"1.1.3U"`; `tests/test_unit.py` asserts it.
