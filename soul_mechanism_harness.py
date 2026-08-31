"""Mechanism-proof harness: does Soul's RPE machinery actually learn?

Ground truth: 6 task contexts, each a Bernoulli environment with fixed hidden
success rate p. Agent performs trials, receives receipted external_test rewards
(valence +1 success / -1 failure). Soul's expectation for each context should
converge to the true expected valence (2p - 1).

Conditions:
  A) reality only
  B) reality + dreams (pre-trial imagination scored against realized outcome)

Metrics per condition:
  - final |expectation - true EV| per context
  - convergence curve (mean absolute error over trial blocks)
  - dream calibration error (dream predicted vs realized correlation)

Falsifiable criteria (pre-registered):
  P1: final MAE(reality-only) < 0.15
  P2: adding dreams must NOT hurt: MAE(dreams) <= MAE(reality) * 1.10
  P3: habituation: identical repeated self-praise increments -> < 20% of first
  P4: persistence: expectations equal before/after kernel restart
Run: python soul_mechanism_harness.py
"""
import json
import math
import os
import random
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from soul_kernel import SoulKernel, RewardSignal, _wallet_key

CONTEXTS = {          # hidden ground truth: probability of success
    "deploy-db":      0.30,
    "write-tests":    0.70,
    "refactor-legacy":0.45,
    "tune-hyperparam":0.55,
    "debug-flaky":    0.20,
    "doc-apis":       0.85,
}
TRIALS_PER_CTX = 400
BLOCK = 50
SEED = 20260825


def reward_for(success: bool) -> RewardSignal:
    # unique receipt per call — the kernel's replay gate rejects duplicates
    reward_for._n = getattr(reward_for, "_n", 0) + 1
    return RewardSignal(
        source="external_test",
        valence=1.0 if success else -1.0,
        confidence=1.0,
        task_context="",   # set by caller
        evidence_receipt=f"sim-receipt-{reward_for._n:06d}",
    )


def run_condition(with_dreams: bool, rng: random.Random):
    tmp = tempfile.mkdtemp(prefix="soul_sim_")
    k = SoulKernel(db_path=os.path.join(tmp, "soul.db"))
    curves = {c: [] for c in CONTEXTS}
    dream_pairs = []           # (predicted, realized)

    for ctx, p in CONTEXTS.items():
        for t in range(TRIALS_PER_CTX):
            # ---- dream phase (condition B): imagine two branches BEFORE acting
            if with_dreams and t % 4 == 0:
                # agent's guess of success prob = mapped from current expectation
                exp_now = k.bio_engine.expected_valence.get(ctx, 0.0)
                p_guess = max(0.05, min(0.95, (exp_now + 1.0) / 2.0))
                good = rng.random() < p_guess      # imagined outcome follows belief
                lik = [p_guess if good else -(1 - p_guess),
                       -(p_guess) if not good else (1 - p_guess)]
                k.run_dream_simulation(
                    scenario_prompt=f"next {ctx} attempt",
                    outcomes=[{"outcome": "works", "likelihood": lik[0]},
                              {"outcome": "breaks", "likelihood": -abs(lik[1])}],
                    task_context=ctx,
                )
            # ---- act: environment coin with HIDDEN p
            success = rng.random() < p
            sig = reward_for(success)
            sig.task_context = ctx
            k.process_reward(sig)
            realized = 1.0 if success else -1.0

            # ---- score pending dreams against reality (the new loop)
            if with_dreams:
                res = k.score_dreams_against_reality(
                    realized, 1.0, ctx, limit=3,
                    evidence_receipt=sig.evidence_receipt)
                for s in res.get("scores", []):
                    dream_pairs.append((s["predicted"], s["realized"]))

            curves[ctx].append(k.bio_engine.expected_valence.get(ctx, 0.0))
    k.close()
    shutil.rmtree(tmp, ignore_errors=True)
    return curves, dream_pairs


def mae_against_truth(expectations):
    return sum(abs(expectations[c] - (2 * CONTEXTS[c] - 1)) for c in CONTEXTS) / len(CONTEXTS)


def main():
    print(f"ground truth EVs: " + ", ".join(f"{c}={2*p-1:+.2f}" for c, p in CONTEXTS.items()))
    print(f"trials/context={TRIALS_PER_CTX}, seed={SEED}\n")

    results = {}
    for cond, dreams in (("reality-only", False), ("with-dreams", True)):
        rng = random.Random(SEED + (7 if dreams else 0))
        curves, pairs = run_condition(dreams, rng)
        finals = {c: curves[c][-1] for c in CONTEXTS}
        mae = mae_against_truth(finals)
        results[cond] = {"finals": finals, "mae": mae,
                         "curve_block_mae": [], "dream_pairs": pairs}
        # blockwise convergence curve (mean abs err across contexts per block)
        nblocks = TRIALS_PER_CTX // BLOCK
        for b in range(nblocks):
            blk = [curves[c][b * BLOCK:(b + 1) * BLOCK] for c in CONTEXTS]
            per_ctx = [sum(blk[i]) / len(blk[i]) for i in range(len(CONTEXTS))]
            truth = [2 * CONTEXTS[c] - 1 for c in CONTEXTS]
            bm = sum(abs(per_ctx[i] - truth[i]) for i in range(len(CONTEXTS))) / len(CONTEXTS)
            results[cond]["curve_block_mae"].append(bm)

    print("=" * 68)
    print("P1: reality-only converges to ground truth")
    print("=" * 68)
    ro = results["reality-only"]
    for c, v in ro["finals"].items():
        print(f"  {c:<16} learned={v:+.3f}  truth={2*CONTEXTS[c]-1:+.2f}")
    print(f"  final MAE = {ro['mae']:.3f}   (criterion < 0.15)")
    p1 = ro["mae"] < 0.15
    print(f"  {'PASS' if p1 else 'FAIL'}\n")

    print("=" * 68)
    print("P2: dreams don't corrupt learning")
    print("=" * 68)
    wd = results["with-dreams"]
    ratio = wd["mae"] / max(ro["mae"], 1e-9)
    print(f"  with-dreams MAE = {wd['mae']:.3f}, reality-only = {ro['mae']:.3f}, ratio={ratio:.2f} (<=1.10)")
    if wd["dream_pairs"]:
        n = len(wd["dream_pairs"])
        mp = sum(x for x, _ in wd["dream_pairs"]) / n
        mr = sum(y for _, y in wd["dream_pairs"]) / n
        cov = sum((x - mp) * (y - mr) for x, y in wd["dream_pairs"]) / max(n - 1, 1)
        sp = (sum((x - mp) ** 2 for x, _ in wd["dream_pairs"]) / max(n - 1, 1)) ** 0.5
        sr = (sum((y - mr) ** 2 for _, y in wd["dream_pairs"]) / max(n - 1, 1)) ** 0.5
        r = cov / max(sp * sr, 1e-9)
        print(f"  dream calibration: corr(predicted, realized) over {n} scored dreams = {r:+.3f}")
    p2 = ratio <= 1.10
    print(f"  {'PASS' if p2 else 'FAIL'}\n")

    print("=" * 68)
    print("P3/P4: habituation + persistence (fresh kernels)")
    print("=" * 68)
    tmp = tempfile.mkdtemp(prefix="soul_p34_")
    k = SoulKernel(db_path=os.path.join(tmp, "s.db"))

    def praise_da():
        k.record_solver_step(tool="think", method="reflect", outcome="succeed",
            receipt="p34-open", plan_id="p-p34")
        k.process_reward(RewardSignal(source="internal_dream", valence=1.0,
            confidence=1.0, task_context="self-review", plan_id="p-p34"))
        store = k._solver_store_from_conn(k._get_conn())
        return store["wallets"][_wallet_key("p-p34", "")]["dopamine"]

    seq = [round(praise_da(), 4)]
    for _ in range(5):
        seq.append(round(praise_da(), 4))
    incs = [b - a for a, b in zip(seq, seq[1:])]
    frac = abs(incs[-1]) / max(abs(incs[0]), 1e-9)
    print(f"  P3 habituation: increment last/first = {frac:.3f} (< 0.20)")
    p3 = frac < 0.20
    before = dict(k.bio_engine.expected_valence)
    k.close()

    k2 = SoulKernel(db_path=os.path.join(tmp, "s.db"))
    after = {c: k2.bio_engine.expected_valence.get(c) for c in list(before)[:3]}
    print(f"  P4 persistence: {len(before)} expectations stored; sample after restart: {after}")
    p4 = all(after[c] is not None and abs(after[c] - before[c]) < 1e-6 for c in after)
    k2.close(); shutil.rmtree(tmp, ignore_errors=True)
    print(f"  {'PASS' if p3 else 'FAIL'} / {'PASS' if p4 else 'FAIL'}\n")

    print("=" * 68)
    print("CONVERGENCE CURVE (block MAE, both conditions)")
    print("=" * 68)
    nb = len(ro["curve_block_mae"])
    print("  block : " + " ".join(f"{i*BLOCK:>5}" for i in range(nb)))
    print("  real  : " + " ".join(f"{v:5.2f}" for v in ro["curve_block_mae"]))
    print("  dream : " + " ".join(f"{v:5.2f}" for v in wd["curve_block_mae"]))

    verdict = all([p1, p2, p3, p4])
    print("\nVERDICT:", "ALL CRITERIA PASS — mechanism demonstrably learns" if verdict else "CRITERIA FAILED — see above")
    return 0 if verdict else 1


if __name__ == "__main__":
    sys.exit(main())
