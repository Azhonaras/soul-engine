---
name: seacom
description: >
  SEACOM is SEAL AND COMMIT. Use when the human types /seacom, SEACOM,
  seacom, or SEAL AND COMMIT, or when they pick on an open Review plan.
  Interview if needed, then soul_review_chat_commit. Not ordinary coding.
  Not tty soul_host.
disable-model-invocation: true
metadata:
  hermes:
    tags: [soul, memory, mcp, review]
    category: soul
---

# SEACOM (SEAL AND COMMIT)

Cursor slash command: **`/seacom`**. Interview if needed, then `soul_review_chat_commit` after this run’s picks. Also the explicit slash for leftover pending items. Not required after they already picked on a Review plan.

Also accepted as typed text: `SEACOM`, `SEAL AND COMMIT`.

The review **interview** also starts when a subject is finished, when a piece of work is done, and before starting a plan (soul-session), if quarantine is non-empty. Starting the cycle is not a commit. Completing this run’s Review plan picks **is** the commit — same as this command.

Idle, “bye”, and wrap-up do not commit. Do not invent picks.

## Do

1. `soul_remember` any durable outcome from this chat that is not yet an episode (test results, decisions, facts the human would want later). Agent `source_kind`. Then start review.
2. `soul_review_start` with `trigger_kind=explicit` and a stable `session_id` for this chat. Do not use `shutdown` or `idle`.
3. If `candidate_count` is 0, skip the interview (no empty ceremony). One short “nothing to review” is enough on this command.
4. Ask **exactly one** candidate at a time. At most **five** this run; leave the rest pending.
5. Present a **Review plan** (not a bare 1–5 dump). Heading `Review plan`. Number the queue (canonical_text, max 5 listed) and mark the current item **now**.
   **Cursor:** you MUST call the structured question picker (`AskQuestion`) with those options as clickable cards — same shape as plan/interview option lists. Do not use a markdown list as the only UI.
   Other hosts: use their native picker if they have one; otherwise a numbered plan of actions.
   Under **now**, options:
   1. **remember** — keep this text as written
   2. **correct** — they send the replacement text; store their exact wording
   3. **session_only** — this chat only, not long-term
   4. **reject** — drop it
   5. **defer** — ask later
   Contradictions (if `contradicting_refs` is non-empty):
   1. replace_old  2. keep_both_with_context  3. keep_old  4. reject_both  5. defer
   Still one item per wait.
6. Wait. Do not invent answers.
7. Write `review_packet.json` (only candidates you asked).
8. After this run’s picks (remember / correct / session_only / reject, or a contradiction set), call `soul_review_chat_commit` with that packet. Then say it is in long-term memory. Do not wait for a second slash. `defer` is not approval for that item.

## Do not

- Call `soul_review_chat_commit` on idle/bye, or before they have picked, or when only starting the cycle.
- Call `soul_review_stage_decision` / `soul_review_commit` with a `soul_host_event` you minted.
- Run `soul_host seal` yourself.
- Skip the interview when candidates exist.
- Promote dream/`imagined` output as fact.
