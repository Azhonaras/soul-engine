"""Trusted host for Soul human origin. Interactive tty only — agents cannot mint human events via this CLI."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _db_path() -> str:
    return os.environ.get("SOUL_DB_PATH", str(Path.home() / ".soul" / "soul.db"))


def _kernel():
    from soul_kernel import SoulKernel
    return SoulKernel(db_path=_db_path())


def _prompt(expected: str, *, require_tty: bool) -> None:
    if not require_tty:
        return
    if not sys.stdin.isatty():
        raise PermissionError(
            "soul_host needs an interactive terminal. An agent cannot run this for you."
        )
    if input().strip() != expected:
        raise SystemExit("aborted")


def _record_decisions(kernel, packet: dict) -> list[str]:
    session_id = packet["session_id"]
    cycle_id = packet["cycle_id"]
    event_ids = []
    for item in packet.get("decisions") or []:
        decide_ev = kernel.record_host_event(
            session_id=session_id,
            origin_kind="human",
            event_kind="review_decision",
            payload=item,
        )
        confirm_ref = None
        if item.get("decision") in ("correct", "keep_both_with_context"):
            confirm_ev = kernel.record_host_event(
                session_id=session_id,
                origin_kind="human",
                event_kind="review_decision",
                payload={"confirmed_text": item.get("corrected_text")},
            )
            confirm_ref = confirm_ev.id
        kernel.record_review_decision(
            cycle_id=cycle_id,
            candidate_id=item["candidate_id"],
            decision=item["decision"],
            human_event_ref=decide_ev.id,
            corrected_text=item.get("corrected_text"),
            correction_confirmation_event_ref=confirm_ref,
        )
        event_ids.append(decide_ev.id)
    return event_ids


def seal_packet(packet_path: str, *, require_tty: bool = True) -> dict:
    """SEAL records one human event per decision; COMMIT is a second human event bound to the preview.

    MCP soul_review_commit stays available for every harness. This CLI only mints origin_kind=human
    (and may commit itself). Tests pass require_tty=False to skip the prompts.
    """
    packet = json.loads(Path(packet_path).read_text(encoding="utf-8"))
    if require_tty:
        print(json.dumps(packet, indent=2))
        print("Type SEAL to record one human decision event per candidate (does not commit).")
    _prompt("SEAL", require_tty=require_tty)

    kernel = _kernel()
    try:
        decision_events = _record_decisions(kernel, packet)
        preview = kernel.preview_review_cycle(packet["cycle_id"])
        if require_tty:
            print(json.dumps(preview, indent=2, default=str))
            print("Type COMMIT to promote this exact preview (or call MCP soul_review_commit with a human event).")
        _prompt("COMMIT", require_tty=require_tty)
        commit_ev = kernel.record_host_event(
            session_id=packet["session_id"],
            origin_kind="human",
            event_kind="review_commit",
            payload={"cycle_id": packet["cycle_id"], "preview_hash": preview.get("preview_hash")},
        )
        receipt = kernel.commit_review_cycle(packet["cycle_id"], commit_human_event_ref=commit_ev.id)
        return {
            "status": "committed",
            "receipt": receipt,
            "preview": preview,
            "decision_events": decision_events,
            "commit_event": commit_ev.id,
        }
    finally:
        kernel.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="soul_host", description="Mint real origin_kind=human events (tty only).")
    sub = parser.add_subparsers(dest="cmd", required=True)
    seal = sub.add_parser("seal", help="SEAL decisions then COMMIT preview from a review packet")
    seal.add_argument("packet", help="JSON review packet (e.g. review_packet.json)")
    args = parser.parse_args(argv)
    if args.cmd == "seal":
        try:
            result = seal_packet(args.packet, require_tty=True)
        except Exception as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
