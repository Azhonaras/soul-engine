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


def _prompt(expected: str, prompt_text: str = "Confirm action?", *, require_tty: bool) -> None:
    if not require_tty:
        return
    if not sys.stdin.isatty():
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            msg = f"{prompt_text}\n\nDo you authorize this action with human origin?"
            result = messagebox.askyesno("Soul Engine Security Authorization", msg, master=root)
            root.destroy()
            if not result:
                raise SystemExit("aborted")
            return
        except Exception as e:
            raise PermissionError(
                "soul_host needs an interactive terminal. GUI fallback failed: " + str(e)
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
                payload={"corrected_text": item.get("corrected_text")},
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
    _prompt("SEAL", prompt_text="SEAL decisions for review packet?", require_tty=require_tty)

    kernel = _kernel()
    try:
        decisions = packet.get("decisions") or []
        if decisions and all(item.get("decision") == "defer" for item in decisions):
            decision_events = _record_decisions(kernel, packet)
            return {
                "status": "deferred",
                "receipt": None,
                "preview": None,
                "decision_events": decision_events,
                "commit_event": None,
            }
        decision_events = _record_decisions(kernel, packet)
        preview = kernel.preview_review_cycle(packet["cycle_id"])
        if require_tty:
            print(json.dumps(preview, indent=2, default=str))
            print("Type COMMIT to promote this exact preview (or call MCP soul_review_commit with a human event).")
        _prompt("COMMIT", prompt_text="COMMIT review cycle preview?", require_tty=require_tty)
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


def rollback_memory_cmd(target_version: int, user_scope_key: str = "default_user", *, require_tty: bool = True) -> dict:
    msg = f"Rollback active reviewed memory set to Version {target_version}?"
    if require_tty:
        print(msg)
        print("Type CONFIRM-ROLLBACK to authorize with human origin:")
    _prompt("CONFIRM-ROLLBACK", prompt_text=msg, require_tty=require_tty)
    kernel = _kernel()
    try:
        ev = kernel.record_host_event(
            session_id=f"host_cli_{os.getpid()}",
            user_scope_key=user_scope_key,
            origin_kind="human",
            event_kind="memory_rollback",
            payload={"target_version": target_version},
        )
        return kernel.rollback_reviewed_memory_set(
            target_version=int(target_version),
            human_event_ref=ev.id,
            user_scope_key=user_scope_key,
        )
    finally:
        kernel.close()


def delete_memory_cmd(memory_id: str, user_scope_key: str = "default_user", *, require_tty: bool = True) -> dict:
    msg = f"Permanently delete reviewed memory {memory_id} (GDPR cascade)?"
    if require_tty:
        print(msg)
        print("Type CONFIRM-DELETE to authorize with human origin:")
    _prompt("CONFIRM-DELETE", prompt_text=msg, require_tty=require_tty)
    kernel = _kernel()
    try:
        ev = kernel.record_host_event(
            session_id=f"host_cli_{os.getpid()}",
            user_scope_key=user_scope_key,
            origin_kind="human",
            event_kind="memory_deletion",
            payload={"memory_id": memory_id},
        )
        return kernel.delete_reviewed_memory(
            memory_id=memory_id,
            human_event_ref=ev.id,
            user_scope_key=user_scope_key,
        )
    finally:
        kernel.close()


def rollback_identity_cmd(target_version: int, reason: str = "Operator manual rollback", *, require_tty: bool = True) -> dict:
    msg = f"Rollback soul identity traits to Version {target_version}?"
    if require_tty:
        print(msg)
        print("Type CONFIRM-IDENTITY-ROLLBACK to authorize with human origin:")
    _prompt("CONFIRM-IDENTITY-ROLLBACK", prompt_text=msg, require_tty=require_tty)
    kernel = _kernel()
    try:
        kernel.record_host_event(
            session_id=f"host_cli_{os.getpid()}",
            origin_kind="human",
            event_kind="session_lifecycle",
            payload={"op": "rollback", "target_version": target_version, "reason": reason},
        )
        st = kernel.rollback_to_version(int(target_version), operator_reason=reason)
        return {"status": "rolled_back", "soul_version": st.soul_version, "traits": st.traits, "state_hash": st.state_hash}
    finally:
        kernel.close()


def heal_cmd(level: int = 1, reason: str = "Operator manual heal", *, require_tty: bool = True) -> dict:
    msg = f"Heal soul state at Level {level} ({reason})?"
    if require_tty:
        print(msg)
        print("Type CONFIRM-HEAL to authorize with human origin:")
    _prompt("CONFIRM-HEAL", prompt_text=msg, require_tty=require_tty)
    kernel = _kernel()
    try:
        kernel.record_host_event(
            session_id=f"host_cli_{os.getpid()}",
            origin_kind="human",
            event_kind="session_lifecycle",
            payload={"op": "heal", "level": level, "reason": reason},
        )
        return kernel.heal_soul_state(level=level, reason=reason)
    finally:
        kernel.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="soul_host", description="Mint real origin_kind=human events (tty only).")
    sub = parser.add_subparsers(dest="cmd", required=True)

    seal = sub.add_parser("seal", help="SEAL decisions then COMMIT preview from a review packet")
    seal.add_argument("packet", help="JSON review packet (e.g. review_packet.json)")

    rb_mem = sub.add_parser("rollback-memory", help="Rollback active reviewed memory set to a target version")
    rb_mem.add_argument("target_version", type=int, help="Target memory set version")
    rb_mem.add_argument("--user-scope", default="default_user", help="User scope key")

    del_mem = sub.add_parser("delete-memory", help="Execute GDPR deletion cascade on a memory")
    del_mem.add_argument("memory_id", help="Target memory ID to erase")
    del_mem.add_argument("--user-scope", default="default_user", help="User scope key")

    rb_id = sub.add_parser("rollback-identity", help="Rollback soul identity version")
    rb_id.add_argument("target_version", type=int, help="Target soul version")
    rb_id.add_argument("--reason", default="Operator manual rollback", help="Reason for rollback")

    hl = sub.add_parser("heal", help="Heal soul state")
    hl.add_argument("--level", type=int, default=1, help="Healing depth level (1, 2, 3)")
    hl.add_argument("--reason", default="Operator manual heal", help="Reason for healing")

    appr = sub.add_parser("approve", help="Approve and execute a Tier-2 destructive operation")
    appr.add_argument("action", choices=["delete-memory", "rollback-memory", "rollback-identity", "heal"], help="Action to approve")
    appr.add_argument("target", nargs="?", default=None, help="Target ID / version / level")
    appr.add_argument("--reason", default="Operator manual approval", help="Reason for action")
    appr.add_argument("--user-scope", default="default_user", help="User scope key")

    args = parser.parse_args(argv)
    try:
        if args.cmd == "seal":
            result = seal_packet(args.packet, require_tty=True)
        elif args.cmd == "rollback-memory":
            result = rollback_memory_cmd(args.target_version, user_scope_key=args.user_scope, require_tty=True)
        elif args.cmd == "delete-memory":
            result = delete_memory_cmd(args.memory_id, user_scope_key=args.user_scope, require_tty=True)
        elif args.cmd == "rollback-identity":
            result = rollback_identity_cmd(args.target_version, reason=args.reason, require_tty=True)
        elif args.cmd == "heal":
            result = heal_cmd(level=args.level, reason=args.reason, require_tty=True)
        elif args.cmd == "approve":
            if args.action == "delete-memory":
                if not args.target:
                    print("error: target memory_id required for delete-memory", file=sys.stderr)
                    return 1
                result = delete_memory_cmd(args.target, user_scope_key=args.user_scope, require_tty=True)
            elif args.action == "rollback-memory":
                if args.target is None:
                    print("error: target version required for rollback-memory", file=sys.stderr)
                    return 1
                result = rollback_memory_cmd(int(args.target), user_scope_key=args.user_scope, require_tty=True)
            elif args.action == "rollback-identity":
                if args.target is None:
                    print("error: target version required for rollback-identity", file=sys.stderr)
                    return 1
                result = rollback_identity_cmd(int(args.target), reason=args.reason, require_tty=True)
            elif args.action == "heal":
                lvl = int(args.target or 1)
                result = heal_cmd(level=lvl, reason=args.reason, require_tty=True)
        else:
            parser.print_help()
            return 1
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
