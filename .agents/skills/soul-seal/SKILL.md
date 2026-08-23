---
name: soul-seal
description: >
  When the human types SEAL (or runs /soul-seal in a client that has slash
  skills), interview them to approve Soul quarantined memories. Same interview.
  Not a second command. Not for ordinary coding.
metadata:
  hermes:
    tags: [soul, memory, mcp, review]
    category: soul
---

# Soul SEAL (human memory approval)

**Trigger:** the human types **SEAL** in this chat. That is the product gesture in every harness (Claude, Hermes, Antigravity, Cursor, Pi, and any other MCP / Agent Skills client).

`/soul-seal` (or the client’s skill slash) is the same interview if this skill is installed. It is not a different command. There is no `/Soul_Seal`.

Idle, “bye”, and wrap-up do not commit. You do not approve memories yourself. MCP cannot mint `origin_kind=human`.

## Do

1. `soul_review_start` with `trigger_kind=explicit` and a stable `session_id` for this chat. Do not use `shutdown` or `idle`.
2. If there are no candidates, say so and stop.
3. Ask **exactly one** candidate at a time. At most **five** this run; leave the rest pending.
4. Show the candidate text, then these **choices** (numbered). If the client has a picker UI, use it for the same five. The human picks a number/name **or edits the wording** (that is `correct`).
   1. **remember** — keep this text as written
   2. **correct** — they send the replacement text; store their exact wording
   3. **session_only** — this chat only, not long-term
   4. **reject** — drop it
   5. **defer** — ask later
   Contradictions (if `contradicting_refs` is non-empty), same picker:
   1. replace_old  2. keep_both_with_context  3. keep_old  4. reject_both  5. defer
5. Wait. Do not invent answers.
6. Write `review_packet.json` in the workspace (only the candidates you asked):

```json
{
  "session_id": "<same session_id>",
  "cycle_id": "<cycle id>",
  "decisions": [
    {"candidate_id": "<id>", "decision": "remember"}
  ]
}
```

For `correct`, include `"corrected_text": "<their exact wording>"`.

7. Tell the human to run this **in their own terminal** (not you):

`py -3 -m soul_host seal review_packet.json`

They type `SEAL` (one human event per decision), read the preview, then type `COMMIT`.

## Do not

- Call `soul_review_stage_decision` or `soul_review_commit` with a host event you created via `soul_host_event`.
- Run `soul_host seal` yourself.
- Skip the interview and dump a packet of guesses.
- Promote dream/`imagined` output as fact.

No candidates after start → skipped: seal, add when there is something to remember.
