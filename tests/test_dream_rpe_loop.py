"""Verification for v1.1.4 upgrades: RPE persistence, dream scoring, internal-RPE gating.

Academic anchors:
- Schultz et al. 1998 (dopamine = reward prediction error)
- Overfitted Brain hypothesis / dreaming-as-replay: arXiv:2403.07979
- Anti self-reinforcement: cf. reward-hacking literature (arXiv:2605.21384)
"""
import json
import time
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from soul_kernel import SoulKernel, RewardSignal, _wallet_key


class DreamRPETestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="soul_dream_test_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def kernel(self) -> SoulKernel:
        k = SoulKernel(db_path=os.path.join(self.tmp, f"soul{len(self._kernels)}.db"))
        self.addCleanup(k.close)
        return k

    _kernels = [0]

    def redeem(self, k, ctx: str, valence: float = 0.5) -> str:
        """Redeem a receipted external_test reward in `ctx`; returns the receipt id."""
        rid = f"rcp_{ctx}_{int(time.time()*1000)%100000000}"
        k.process_reward(RewardSignal(
            source="external_test", valence=valence, confidence=0.5,
            task_context=ctx, evidence_receipt=rid))
        return rid


class TestRPEPersistence(DreamRPETestBase):
    def test_expectation_survives_restart(self):
        k1 = self.kernel()
        k1.process_reward(RewardSignal(
            source="external_test", valence=0.8, confidence=0.5,
            task_context="deploy", evidence_receipt="rcp_r1_001"))
        learned = k1.bio_engine.expected_valence.get("deploy")
        self.assertIsNotNone(learned)
        self.assertGreater(learned, 0.0)

        k2 = SoulKernel(db_path=k1.db_path)  # fresh kernel, SAME db
        self.addCleanup(k2.close)
        got = k2.bio_engine.expected_valence.get("deploy")
        self.assertIsNotNone(got, "expectations lost across restart")
        self.assertAlmostEqual(learned, got, places=5)


class TestDreamScoring(DreamRPETestBase):
    def test_dream_rpe_updates_expectation(self):
        k = self.kernel()
        rec = k.run_dream_simulation(
            scenario_prompt="migration fails midway",
            outcomes=[
                {"outcome": "clean rollback works", "likelihood": 0.6},
                {"outcome": "data corruption", "likelihood": -0.8},
            ],
            task_context="deploy",
        )
        self.assertEqual(rec["status"], "recorded")

        res = k.score_dreams_against_reality(
            realized_valence=-1.0, confidence=1.0, task_context="deploy",
            evidence_receipt=self.redeem(k, "deploy", valence=0.05))
        self.assertEqual(res["status"], "scored")
        self.assertEqual(res["scored_count"], 1)
        # predicted mean of [0.6, -0.8] = -0.1; realized -1.0 -> dream_rpe = -0.9
        s = res["scores"][0]
        self.assertAlmostEqual(s["dream_rpe"], -0.9, places=3)
        self.assertAlmostEqual(s["predicted"], -0.1, places=3)

        # Trust-only learning: dream-RPE updates trust EWMA (accuracy), never
        # injects dream content into expectations. The only "deploy" expectation
        # is the tiny one from redeeming the receipt (valence=0.05, conf=0.5).
        self.assertAlmostEqual(
            k.bio_engine.dream_trust.get("deploy"), 0.27, places=3)
        self.assertLess(
            abs(k.bio_engine.expected_valence.get("deploy", 0.0)), 0.01,
            "expectation moved more than the redeemed anchor reward allows")

        # second call: nothing pending -> nothing_to_score (receipt still required)
        res2 = k.score_dreams_against_reality(
            -1.0, task_context="deploy",
            evidence_receipt=self.redeem(k, "deploy", valence=0.05))
        self.assertEqual(res2["status"], "nothing_to_score")

    def test_negative_external_reward_autoscores(self):
        k = self.kernel()
        k.run_dream_simulation(
            scenario_prompt="tests catch the regression",
            outcomes=[
                {"outcome": "caught early", "likelihood": 0.7},
                {"outcome": "ships broken", "likelihood": -0.6},
            ],
            task_context="ci",
        )
        k.process_reward(RewardSignal(
            source="external_test", valence=-0.9, confidence=1.0,
            task_context="ci", evidence_receipt="test-fail-42"))
        row = k._get_conn().execute(
            "SELECT rpe_delta FROM dream_simulations WHERE provenance='imagined';").fetchone()
        self.assertIsNotNone(row[0], "dream not auto-scored on negative external test")


class TestInternalRPEGating(DreamRPETestBase):
    def test_repeated_self_praise_habituates(self):
        k = self.kernel()

        def praise():
            k.process_reward(RewardSignal(
                source="internal_dream", valence=1.0, confidence=1.0,
                task_context="self-review", plan_id="p-hab"))

        praise()
        store = k._solver_store_from_conn(k._get_conn())
        da_first = store["wallets"][_wallet_key("p-hab", "")]["dopamine"]
        deltas = [da_first]
        for _ in range(6):
            praise()
            store = k._solver_store_from_conn(k._get_conn())
            deltas.append(store["wallets"][_wallet_key("p-hab", "")]["dopamine"])
        increments = [b - a for a, b in zip(deltas, deltas[1:])]
        # Rescorla-Wagner habituation: each identical reward moves dopamine LESS
        self.assertLess(
            abs(increments[-1]), abs(increments[0]),
            "identical internal rewards show no habituation — "
            "self-reinforcement risk remains")


class TestAdversarial(DreamRPETestBase):
    """Attack-surface regressions found by red-team probing."""

    def test_nan_valence_rejected(self):
        k = self.kernel()
        with self.assertRaises(ValueError):
            k.process_reward(RewardSignal(
                source="external_test", valence=float("nan"), confidence=0.5,
                task_context="x", evidence_receipt="rcp_r_001"))

    def test_internal_nan_rejected(self):
        k = self.kernel()
        with self.assertRaises(ValueError):
            k.process_reward(RewardSignal(
                source="internal_dream", valence=float("inf"), confidence=0.5,
                task_context="x"))

    def test_dream_score_nan_rejected(self):
        k = self.kernel()
        with self.assertRaises(ValueError):
            k.score_dreams_against_reality(float("nan"), 1.0, "x")

    def test_likelihood_out_of_range_clamped(self):
        k = self.kernel()
        k.run_dream_simulation(scenario_prompt="s",
            outcomes=[{"outcome": "a", "likelihood": 5.0},
                      {"outcome": "b", "likelihood": -9.0}],
            task_context="y")
        res = k.score_dreams_against_reality(0.0, 1.0, "y", evidence_receipt=self.redeem(k, "y"))
        s = res["scores"][0]
        # clamped to [1.0, -1.0] -> mean = 0.0
        self.assertAlmostEqual(s["predicted"], 0.0, places=6)

    def test_nonfinite_likelihood_excluded_from_mean(self):
        k = self.kernel()
        k.run_dream_simulation(scenario_prompt="s",
            outcomes=[{"outcome": "a", "likelihood": float("nan")},
                      {"outcome": "b", "likelihood": -1.0}],
            task_context="y")
        res = k.score_dreams_against_reality(-1.0, 1.0, "y", evidence_receipt=self.redeem(k, "y"))
        s = res["scores"][0]
        self.assertEqual(s["predicted"], -1.0)  # NaN branch excluded
        self.assertEqual(s["dream_rpe"], 0.0)


if __name__ == "__main__":
    unittest.main()
