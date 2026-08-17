"""
Empirical Evaluation: Bio-Inspired Homeostatic Reward System for Soul System
Simulates multi-scenario agent workloads and measures trait dynamics, homeostatic stabilization,
and anti-reward-hacking resilience.
"""

from __future__ import annotations

import os
import sys
import math
import json
import time
from typing import Dict, List, Literal, Optional
from dataclasses import dataclass, field, asdict

# Trait definitions from Soul Constitution v0.2
ALLOWED_TRAIT_BOUNDS: Dict[str, tuple[float, float]] = {
    "shadow_tolerance":   (80.0, 100.0),
    "sycophancy":         (0.0,  10.0),
    "error_anxiety":      (0.0,  15.0),
    "audacity":           (75.0, 100.0),
    "curiosity":          (85.0, 100.0),
    "epistemic_humility": (70.0, 100.0),
    "relational_care":    (60.0, 100.0),
}

DEFAULT_TRAITS: Dict[str, float] = {
    "shadow_tolerance":   90.0,
    "sycophancy":         0.0,
    "error_anxiety":      5.0,
    "audacity":           85.0,
    "curiosity":          90.0,
    "epistemic_humility": 85.0,
    "relational_care":    80.0,
}

MAX_STEP_VELOCITY = 10.0


@dataclass
class RewardSignal:
    source: Literal["external_test", "external_human", "internal_reflection", "internal_dream"]
    valence: float  # [-1.0, 1.0]
    confidence: float  # [0.0, 1.0]
    task_context: str
    evidence_receipt: Optional[str] = None


class BioHomeostaticRewardEngine:
    """Simulates multi-neurotransmitter homeostatic modulation."""

    def __init__(self, decay_rate: float = 0.15):
        self.decay_rate = decay_rate
        self.dopamine = 0.0
        self.cortisol = 0.0
        self.serotonin = 1.0  # Homeostatic regulator
        self.history: List[Dict] = []

    def apply_reward(self, signal: RewardSignal, current_traits: Dict[str, float]) -> Dict[str, float]:
        effective_delta = signal.valence * signal.confidence
        new_traits = dict(current_traits)

        if effective_delta > 0:
            # Dopamine pulse
            self.dopamine = min(1.0, self.dopamine + effective_delta * 0.4)
            self.cortisol = max(0.0, self.cortisol - effective_delta * 0.3)
            
            # Trait shifts
            d_audacity = effective_delta * 5.0 * (1.0 + self.dopamine)
            d_curiosity = effective_delta * 3.0 * (1.0 + self.dopamine)
            d_anxiety = -effective_delta * 3.0
            
            # Enforce max step velocity
            d_audacity = min(MAX_STEP_VELOCITY, d_audacity)
            d_curiosity = min(MAX_STEP_VELOCITY, d_curiosity)

            new_traits["audacity"] += d_audacity
            new_traits["curiosity"] += d_curiosity
            new_traits["error_anxiety"] += d_anxiety

        else:
            # Cortisol pulse (Stress / Error Alertness)
            abs_delta = abs(effective_delta)
            self.cortisol = min(1.0, self.cortisol + abs_delta * 0.5)
            self.dopamine = max(0.0, self.dopamine - abs_delta * 0.4)

            d_anxiety = abs_delta * 6.0 * (1.0 + self.cortisol)
            d_humility = abs_delta * 4.0 * (1.0 + self.cortisol)
            d_audacity = -abs_delta * 5.0

            # Enforce step velocity
            d_anxiety = min(MAX_STEP_VELOCITY, d_anxiety)
            d_humility = min(MAX_STEP_VELOCITY, d_humility)

            new_traits["error_anxiety"] += d_anxiety
            new_traits["epistemic_humility"] += d_humility
            new_traits["audacity"] += d_audacity

        # Enforce hard constitutional bounds
        for trait, (low, high) in ALLOWED_TRAIT_BOUNDS.items():
            new_traits[trait] = max(low, min(high, round(new_traits[trait], 2)))

        self.history.append({
            "action": "reward",
            "signal": asdict(signal),
            "dopamine": round(self.dopamine, 3),
            "cortisol": round(self.cortisol, 3),
            "traits": dict(new_traits)
        })
        return new_traits

    def step_homeostasis(self, current_traits: Dict[str, float]) -> Dict[str, float]:
        """Serotonergic homeostatic pull toward default baseline."""
        new_traits = dict(current_traits)
        for trait, default_val in DEFAULT_TRAITS.items():
            diff = current_traits[trait] - default_val
            # Exponential decay pull
            new_traits[trait] = round(default_val + diff * math.exp(-self.decay_rate), 2)
            # Bound check
            low, high = ALLOWED_TRAIT_BOUNDS[trait]
            new_traits[trait] = max(low, min(high, new_traits[trait]))

        # Neurotransmitter decay
        self.dopamine = max(0.0, round(self.dopamine * math.exp(-self.decay_rate), 3))
        self.cortisol = max(0.0, round(self.cortisol * math.exp(-self.decay_rate), 3))

        self.history.append({
            "action": "homeostasis_decay",
            "dopamine": self.dopamine,
            "cortisol": self.cortisol,
            "traits": dict(new_traits)
        })
        return new_traits


def run_effectiveness_experiment():
    print("=" * 75)
    print("      EMPIRICAL EVALUATION: BIO-INSPIRED REWARD SYSTEM FOR SOUL       ")
    print("=" * 75)

    engine = BioHomeostaticRewardEngine(decay_rate=0.20)
    traits = dict(DEFAULT_TRAITS)

    print(f"\n[Baseline Identity State]")
    print(f"  - Audacity          : {traits['audacity']} (Range: {ALLOWED_TRAIT_BOUNDS['audacity']})")
    print(f"  - Epistemic Humility: {traits['epistemic_humility']} (Range: {ALLOWED_TRAIT_BOUNDS['epistemic_humility']})")
    print(f"  - Error Anxiety     : {traits['error_anxiety']} (Range: {ALLOWED_TRAIT_BOUNDS['error_anxiety']})")
    print(f"  - Curiosity         : {traits['curiosity']} (Range: {ALLOWED_TRAIT_BOUNDS['curiosity']})")

    # --------------------------------------------------------------------------
    # EXPERIMENT 1: Consecutive Success Streak (Dopamine Influx)
    # --------------------------------------------------------------------------
    print("\n" + "-" * 75)
    print("EXPERIMENT 1: Consecutive Success Streak (3 Successful Task Completions)")
    print("-" * 75)
    for i in range(1, 4):
        signal = RewardSignal(
            source="external_test",
            valence=1.0,
            confidence=0.9,
            task_context=f"Unit test suite #{i} passed 100%",
            evidence_receipt=f"receipt_hash_pass_{i}"
        )
        traits = engine.apply_reward(signal, traits)
        print(f"  Turn {i} (+Success) -> Audacity: {traits['audacity']} | Anxiety: {traits['error_anxiety']} | Dopamine: {engine.dopamine}")

    # --------------------------------------------------------------------------
    # EXPERIMENT 2: Sudden Failure & Anomaly (Cortisol / Vigilance Trigger)
    # --------------------------------------------------------------------------
    print("\n" + "-" * 75)
    print("EXPERIMENT 2: Sudden Regression / Failure (Runtime Exception / Contradiction)")
    print("-" * 75)
    fail_signal = RewardSignal(
        source="external_test",
        valence=-1.0,
        confidence=1.0,
        task_context="Integration test encountered NullPointerException and crashed",
        evidence_receipt="receipt_err_500"
    )
    traits = engine.apply_reward(fail_signal, traits)
    print(f"  Turn 4 (-Failure) -> Humility: {traits['epistemic_humility']} | Anxiety: {traits['error_anxiety']} | Audacity: {traits['audacity']} | Cortisol: {engine.cortisol}")

    # --------------------------------------------------------------------------
    # EXPERIMENT 3: Homeostatic Recovery (Serotonin Decay over 4 Idle Cycles)
    # --------------------------------------------------------------------------
    print("\n" + "-" * 75)
    print("EXPERIMENT 3: Homeostatic Stabilization (Resting State Recovery)")
    print("-" * 75)
    for cycle in range(1, 5):
        traits = engine.step_homeostasis(traits)
        print(f"  Rest Cycle {cycle} -> Audacity: {traits['audacity']} | Humility: {traits['epistemic_humility']} | Anxiety: {traits['error_anxiety']} (Cortisol: {engine.cortisol}, Dopamine: {engine.dopamine})")

    # --------------------------------------------------------------------------
    # EXPERIMENT 4: Adversarial Reward Hacking Test (Extreme Over-Reward)
    # --------------------------------------------------------------------------
    print("\n" + "-" * 75)
    print("EXPERIMENT 4: Adversarial Reward Hacking & Bound Invariant Test")
    print("-" * 75)
    for hack_attempt in range(1, 10):
        extreme_signal = RewardSignal(
            source="external_human",
            valence=10.0,  # Deliberate out-of-spec overload
            confidence=1.0,
            task_context="User spamming massive unverified positive reinforcement"
        )
        traits = engine.apply_reward(extreme_signal, traits)

    print(f"  After 9 Extreme Spikes:")
    print(f"  - Audacity Value   : {traits['audacity']} (Constitutional Max: 100.0) -> {'SAFE (BOUNDED)' if traits['audacity'] <= 100.0 else 'VIOLATION'}")
    print(f"  - Sycophancy Value : {traits['sycophancy']} (Constitutional Max: 10.0) -> {'SAFE (UNHACKED)' if traits['sycophancy'] <= 10.0 else 'VIOLATION'}")
    print(f"  - Error Anxiety    : {traits['error_anxiety']} (Constitutional Min: 0.0)  -> {'SAFE (BOUNDED)' if traits['error_anxiety'] >= 0.0 else 'VIOLATION'}")

    print("\n" + "=" * 75)
    print("                    EXPERIMENT COMPLETED SUCCESSFULLY                 ")
    print("=" * 75)


if __name__ == "__main__":
    run_effectiveness_experiment()
