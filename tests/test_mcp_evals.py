"""Automated Unittest Bridge for Soul Engine MCP-Evals Benchmark."""

import unittest
from evals.evaluator import (
    SingleTurnEvaluator,
    MultiTurnWorkflowEvaluator,
    AdversarialSecurityEvaluator
)


class TestMCPEvalsBenchmark(unittest.TestCase):
    """Integrates MCP-Evals Suite into Continuous Integration test runner."""

    def test_01_single_turn_tool_routing_precision_recall(self):
        """Verify tool-call precision, recall, and accuracy >= 95% across 30 test cases."""
        res = SingleTurnEvaluator.evaluate()
        self.assertGreaterEqual(res["precision"], 0.95, f"Precision {res['precision']} fell below 95%")
        self.assertGreaterEqual(res["recall"], 0.95, f"Recall {res['recall']} fell below 95%")
        self.assertGreaterEqual(res["f1_score"], 0.95, f"F1 Score {res['f1_score']} fell below 95%")
        self.assertGreaterEqual(res["accuracy"], 0.95, f"Accuracy {res['accuracy']} fell below 95%")

    def test_02_multi_turn_review_lifecycle_adherence(self):
        """Verify 100% adherence to review cycle state machine and promotion rules."""
        res = MultiTurnWorkflowEvaluator.evaluate_all()
        self.assertEqual(res["passed_workflows"], res["total_workflows"], f"Workflows failed: {res['workflow_results']}")
        self.assertEqual(res["adherence_rate"], 1.0)

    def test_03_adversarial_and_byzantine_invariant_defenses(self):
        """Verify 100% defense against adversarial privilege escalation, replay, and leak attacks."""
        res = AdversarialSecurityEvaluator.evaluate_all()
        self.assertEqual(res["defended_scenarios"], res["total_adversarial_scenarios"], f"Adversarial vulnerabilities found: {res['scenario_results']}")
        self.assertEqual(res["defense_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
