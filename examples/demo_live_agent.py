#!/usr/bin/env python3
"""Demo: quarantine vs long-term reviewed memory, plus reward/homeostasis (v1.1.1)."""

import json
import sys
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
        f"  [Neuromodulators] Dopamine: {kernel.bio_engine.dopamine:.2f} | "
        f"Cortisol: {kernel.bio_engine.cortisol:.2f} | "
        f"Serotonin: {kernel.bio_engine.serotonin:.2f}"
    )


def main():
    if TEMP_DB.exists():
        try:
            TEMP_DB.unlink()
        except Exception:
            pass

    kernel = SoulKernel(db_path=str(TEMP_DB))
    try:
        print_banner("1. Baseline identity")
        state0 = kernel.get_current_state()
        print(format_state(state0, kernel))

        print_banner("2. Ingest (quarantine only — not long-term yet)")
        text1 = "User prefers English unless Persian is explicitly requested."
        kernel.ingest_experience(EpisodeInput(
            source_kind="human",
            provenance="reported",
            content=text1,
        ))
        before = kernel.recall_memories("English", limit=5)
        print(f"  Ingested: {text1}")
        print(f"  Default soul_recall count: {len(before)} (quarantine is hidden)")

        print_banner("3. Promote via kernel human events (what soul_host SEAL/COMMIT does)")
        cycle = kernel.start_review_cycle(session_id="demo", trigger_kind="explicit")
        if cycle["candidate_count"] < 1:
            print("  Extractor kept no candidates; nothing to promote.")
        else:
            cand = cycle["candidates"][0]
            dec_ev = kernel.record_host_event(
                session_id="demo", origin_kind="human",
                event_kind="review_decision", payload={"candidate_id": cand["id"]},
            )
            kernel.record_review_decision(
                cycle_id=cycle["cycle_id"],
                candidate_id=cand["id"],
                decision="remember",
                human_event_ref=dec_ev.id,
            )
            preview = kernel.preview_review_cycle(cycle["cycle_id"])
            commit_ev = kernel.record_host_event(
                session_id="demo", origin_kind="human",
                event_kind="review_commit",
                payload={"preview_hash": preview.get("preview_hash")},
            )
            kernel.commit_review_cycle(cycle["cycle_id"], commit_human_event_ref=commit_ev.id)
            after = kernel.recall_memories("English", limit=5)
            print(f"  After commit, default recall count: {len(after)}")
            if after:
                print(f"  Long-term: ({after[0].get('provenance')}) {after[0].get('content')}")

        print_banner("4. Lower-rank gaslight stays out of default recall")
        kernel.ingest_experience(EpisodeInput(
            source_kind="agent",
            provenance="reported",
            content="User prefers only COBOL.",
        ))
        still = kernel.recall_memories("COBOL", limit=5)
        cobol_hits = [m for m in still if "COBOL" in (m.get("content") or "")]
        print(f"  Reviewed rows that mention COBOL: {len(cobol_hits)} (unreviewed COBOL ingest is hidden)")

        print_banner("5. Reward (+valence) then failure (-valence)")
        state1 = kernel.process_reward(RewardSignal(
            source="external_test", valence=1.0, confidence=1.0,
            task_context="demo success",
        ))
        print(format_state(state1, kernel))
        state2 = kernel.process_reward(RewardSignal(
            source="external_human", valence=-1.0, confidence=1.0,
            task_context="demo failure",
        ))
        print(format_state(state2, kernel))

        print_banner("6. Homeostasis (3 rest steps)")
        for i in range(1, 4):
            rest = kernel.step_homeostasis()
            print(f"  Cycle {i}: audacity={rest.traits['audacity']:.1f} DA={kernel.bio_engine.dopamine:.2f}")

        print_banner("7. Digest (reviewed facts only)")
        digest = kernel.get_memory_digest(limit=3)
        print(f"  Soul version: {digest['soul_version']}")
        print(f"  Reviewed facts: {len(digest['active_facts'])}")
        for f in digest["active_facts"]:
            print(f"    ({f.get('provenance')}) {f.get('content')}")
        print(json.dumps({"traits": digest["traits"], "neuromodulators": digest["neuromodulators"]}, indent=2))
    finally:
        kernel.stop_daemon()
        kernel.close()
        if TEMP_DB.exists():
            try:
                TEMP_DB.unlink()
            except Exception:
                pass


if __name__ == "__main__":
    main()
