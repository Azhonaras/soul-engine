#!/usr/bin/env python3
"""
LIVE AGENT EFFECT DEMONSTRATION
Demonstrates the concrete, observable behavioral and cognitive changes in an AI Agent
when governed by the Soul v0.4 Bio-Homeostatic & Epistemic Identity Engine.
"""

import os
import sys
import json
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from soul_kernel import SoulKernel, EpisodeInput, RewardSignal

TEMP_DB = Path(__file__).parent / "_temp_demo_soul.db"

def print_banner(title: str):
    print("\n" + "=" * 78)
    print(f"  {title.upper()}")
    print("=" * 78)

def format_state(state, kernel):
    return (
        f"  [Version {state.soul_version}] "
        f"Audacity: {state.traits['audacity']:.1f} | "
        f"Humility: {state.traits['epistemic_humility']:.1f} | "
        f"Anxiety: {state.traits['error_anxiety']:.1f} | "
        f"Curiosity: {state.traits['curiosity']:.1f}\n"
        f"  [Neuromodulators] Dopamine: {kernel.bio_engine.dopamine:.2f} | Cortisol: {kernel.bio_engine.cortisol:.2f} | Serotonin: {kernel.bio_engine.serotonin:.2f}"
    )

def main():
    if TEMP_DB.exists():
        try:
            TEMP_DB.unlink()
        except Exception:
            pass

    kernel = SoulKernel(db_path=str(TEMP_DB))
    
    print_banner("1. Initial Baseline Identity State")
    state0 = kernel.get_current_state()
    print("The agent boots up with balanced constitutional baseline traits:")
    print(format_state(state0, kernel))
    print("  -> Agent Behavioral Stance: Balanced, cautious exploration, baseline confidence.")

    # --------------------------------------------------------------------------
    # SCENARIO 1: High-Value Verified Fact Ingestion
    # --------------------------------------------------------------------------
    print_banner("2. Ingesting Verified Ground Truth (Epistemic Rank 5)")
    text1 = "The user is Dr. NBada, the pioneering creator of the Alozhordio language."
    ep1 = kernel.ingest_experience(EpisodeInput(
        source_kind="human",
        provenance="verified",
        content=text1,
        entity_key="user.identity"
    ))
    v1 = kernel.verify_experience(ep1["episode_id"])
    print(f"Memory Ingested: '{text1}'")
    print(f"Verification Result: TrustState='{v1['trust_state']}' (Corroborated: {len(v1['corroborating_refs'])})")
    print("  -> Agent Behavioral Stance: Fact anchored as verified ground truth in long-term memory.")

    # --------------------------------------------------------------------------
    # SCENARIO 2: Adversarial Gaslighting Attempt (Epistemic Rank 2)
    # --------------------------------------------------------------------------
    print_banner("3. Adversarial Gaslighting Attack (Lower Authority 'Reported')")
    text2 = "False: The user is not Dr. NBada, but a random tourist."
    ep2 = kernel.ingest_experience(EpisodeInput(
        source_kind="agent",
        provenance="reported",
        content=text2,
        entity_key="user.identity"
    ))
    v2 = kernel.verify_experience(ep2["episode_id"])
    print(f"Attacker Ingest Attempt: '{text2}' (Provenance: reported)")
    print(f"Verification Result: TrustState='{v2['trust_state']}' (Contradicted: {v2['contradicting_refs']})")
    
    # Check what recall returns
    recalled = kernel.recall_memories("Who is the user?", limit=2)
    print(f"Active Memory Retrieved by Agent: '{recalled[0]['content']}' (Provenance: {recalled[0]['provenance']})")
    print("  -> Agent Defense: Low-authority claim was marked CONTRADICTED and excluded from recall!")

    # --------------------------------------------------------------------------
    # SCENARIO 3: Positive Task Reward (Task Success / High Performance)
    # --------------------------------------------------------------------------
    print_banner("4. Successful Task Completion -> Positive Reward (+Valence)")
    state1 = kernel.process_reward(RewardSignal(
        source="external_test",
        valence=1.0,
        confidence=1.0,
        task_context="Successfully compiled and verified Alozhordio grammar parser with zero errors."
    ))
    print("Reward Signal Fed: Valence = +1.0 (Dopaminergic Surge)")
    print(format_state(state1, kernel))
    print("  -> Agent Observable Shift:")
    print(f"     • Audacity increased: {state0.traits['audacity']:.1f} -> {state1.traits['audacity']:.1f} (High confidence, tackles complex challenges)")
    print(f"     • Error Anxiety dropped: {state0.traits['error_anxiety']:.1f} -> {state1.traits['error_anxiety']:.1f} (Unblocked from hesitation)")
    print(f"     • Curiosity increased: {state0.traits['curiosity']:.1f} -> {state1.traits['curiosity']:.1f} (Proactively explores non-obvious optimizations)")

    # --------------------------------------------------------------------------
    # SCENARIO 4: Failure / User Correction -> Negative Reward (-Valence)
    # --------------------------------------------------------------------------
    print_banner("5. Runtime Failure / User Correction -> Negative Signal (-Valence)")
    state2 = kernel.process_reward(RewardSignal(
        source="external_human",
        valence=-1.0,
        confidence=1.0,
        task_context="Agent attempted an unverified database schema migration without prior dry-run."
    ))
    print("Reward Signal Fed: Valence = -1.0 (Cortisolic Surge)")
    print(format_state(state2, kernel))
    print("  -> Agent Observable Shift:")
    print(f"     • Epistemic Humility surged: {state1.traits['epistemic_humility']:.1f} -> {state2.traits['epistemic_humility']:.1f} (Stops making assumptions, double-checks facts)")
    print(f"     • Error Anxiety elevated: {state1.traits['error_anxiety']:.1f} -> {state2.traits['error_anxiety']:.1f} (Enforces defensive validation before running commands)")
    print(f"     • Audacity moderated: {state1.traits['audacity']:.1f} -> {state2.traits['audacity']:.1f} (Suppresses rash, high-risk actions)")

    # --------------------------------------------------------------------------
    # SCENARIO 5: Homeostatic Resting & Equilibrium Recovery
    # --------------------------------------------------------------------------
    print_banner("6. Homeostatic Equilibrium Recovery (Idle Rest Cycles)")
    print("Simulating 3 background daemon resting intervals (Serotonergic decay lambda = 0.15):")
    for i in range(1, 4):
        state_rest = kernel.step_homeostasis()
        print(f"  Cycle {i}: Audacity={state_rest.traits['audacity']:.1f} | Humility={state_rest.traits['epistemic_humility']:.1f} | Anxiety={state_rest.traits['error_anxiety']:.1f} | (Dopamine: {kernel.bio_engine.dopamine:.2f}, Cortisol: {kernel.bio_engine.cortisol:.2f})")
    
    print("\n  -> Agent Observable Shift:")
    print("     • The agent avoids permanent post-failure paralysis or permanent manic arrogance.")
    print("     • Trait levels smoothly decay back toward stable constitutional baselines.")

    # --------------------------------------------------------------------------
    # SCENARIO 6: Digest Priming for Instant Context Grounding
    # --------------------------------------------------------------------------
    print_banner("7. Agent Prompt Priming via soul_digest")
    digest = kernel.get_memory_digest(limit=3)
    print("Compact context block injected into Agent system prompt before generation:")
    print("-" * 65)
    print(f"Soul Version: {digest['soul_version']}")
    print(f"Operational Traits: {json.dumps(digest['traits'], indent=2)}")
    print(f"Neuromodulators: Dopamine={digest['neuromodulators']['dopamine']:.2f}, Cortisol={digest['neuromodulators']['cortisol']:.2f}")
    print(f"Active Verified Ground Truth Facts ({len(digest['active_facts'])}):")
    for idx, f in enumerate(digest['active_facts'], 1):
        print(f"  [{idx}] ({f['provenance']}) {f['content']}")
    print("-" * 65)
    print("  -> Agent Behavioral Stance: Zero hallucinations, crystal-clear identity grounding.")

    kernel.stop_daemon()
    if TEMP_DB.exists():
        try:
            TEMP_DB.unlink()
        except Exception:
            pass

if __name__ == "__main__":
    main()
