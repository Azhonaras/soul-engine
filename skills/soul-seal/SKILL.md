---
name: soul-seal
description: >
  When the human types SEAL or /soul-seal, interview quarantined memories.
  Start-cycle is not a commit. Completing this run's Review plan picks is
  the commit (soul_review_chat_commit). /seacom still promotes leftover
  pending. Not ordinary coding.
metadata:
  hermes:
    tags: [soul, memory, mcp, review]
    category: soul
---

# Soul SEAL (human memory approval)

**Slash:** `/soul-seal` = start the interview. Completing this run’s Review plan picks **is** the commit. **`/seacom`** promotes leftover pending items (see seacom skill).

Also: `SEAL` starts the same interview.

The review **interview** also starts when a subject is finished, when a piece of work is done, and before starting a plan (soul-session), if quarantine is non-empty.

Idle, “bye”, and wrap-up do not commit. You do not invent their picks.

## Do

1. `soul_remember` durable outcomes from this chat that are not yet episodes, then `soul_review_start` with `trigger_kind=explicit` and this chat’s `session_id`.
2. If `candidate_count` is 0, skip the interview (no empty ceremony).
3. Ask **exactly one** candidate at a time. At most **five** this run.
4. Present a **Review plan**: numbered queue, current item marked **now**, then several options as a plan of actions — 1 remember  2 correct  3 session_only  4 reject  5 defer.
   Contradictions: 1 replace_old  2 keep_both_with_context  3 keep_old  4 reject_both  5 defer.
   **Cursor:** MUST use the structured question picker (`AskQuestion`) — clickable cards, not a markdown list as the only UI. Other hosts: native picker if they have one. Still one item per wait.
5. Wait.
6. Write `review_packet.json`.
7. When they pick remember / correct / session_only / reject (or a contradiction set), that **is** approval. After this run’s picks, call `soul_review_chat_commit`. Do not wait for a second slash. `defer` is not approval for that item (leave pending).
8. `/seacom` remains the explicit slash for leftover pending items.

## Do not

- Promote when starting the cycle with no picks, or on idle/bye.
- Mint `origin_kind=human` via `soul_host_event`.
- Run `soul_host seal` yourself.
- Promote dream/`imagined` output as fact.
