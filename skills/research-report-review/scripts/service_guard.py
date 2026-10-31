"""Persist attempts and isolate circuit breakers for external services."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SERVICE_FAILURES = {"TIMEOUT", "PARSE_FAILED", "RATE_LIMIT", "ERROR", "ABANDONED", "AUTH_INVALID"}
MAX_ATTEMPTS = 3
CIRCUIT_THRESHOLD = 2


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_service() -> dict[str, Any]:
    return {
        "circuit": {"state": "CLOSED", "consecutive_service_failures": 0, "opened_reason": ""},
        "operations": {},
    }


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": 1, "services": {}}
    with path.open("r", encoding="utf-8") as stream:
        state = json.load(stream)
    if not isinstance(state, dict) or state.get("schema_version") != 1:
        raise ValueError("service state must use schema_version=1")
    if not isinstance(state.get("services"), dict):
        raise ValueError("service state requires services")
    return state


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(state, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    temporary.replace(path)


def operation_key(object_id: str, operation: str) -> str:
    return f"{object_id}::{operation}"


def mark_service_failure(circuit: dict[str, Any], outcome: str) -> None:
    circuit["consecutive_service_failures"] = int(circuit.get("consecutive_service_failures", 0)) + 1
    threshold = 1 if outcome == "AUTH_INVALID" else CIRCUIT_THRESHOLD
    if circuit["consecutive_service_failures"] >= threshold:
        circuit.update(
            state="OPEN",
            opened_reason=(
                "non-retryable authentication failure"
                if outcome == "AUTH_INVALID"
                else f"{CIRCUIT_THRESHOLD} consecutive service failures; last={outcome}"
            ),
            opened_at=now(),
        )


def settle_abandoned(entry: dict[str, Any], circuit: dict[str, Any]) -> bool:
    if not entry["history"] or entry["history"][-1].get("outcome") != "PENDING":
        return False
    entry["history"][-1].update(
        outcome="ABANDONED",
        detail="previous call did not record a completion before resume",
        finished_at=now(),
    )
    entry["status"] = "BLOCKED" if entry["attempts"] >= MAX_ATTEMPTS else "TODO"
    mark_service_failure(circuit, "ABANDONED")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    commands = parser.add_subparsers(dest="command", required=True)

    start = commands.add_parser("start")
    start.add_argument("--service", required=True)
    start.add_argument("--object-id", required=True)
    start.add_argument("--operation", required=True)
    start.add_argument("--method", required=True)

    finish = commands.add_parser("finish")
    finish.add_argument("--service", required=True)
    finish.add_argument("--object-id", required=True)
    finish.add_argument("--operation", required=True)
    finish.add_argument(
        "--outcome",
        choices=("PASS", "INCOMPLETE", "TIMEOUT", "PARSE_FAILED", "RATE_LIMIT", "ERROR", "AUTH_INVALID"),
        required=True,
    )
    finish.add_argument("--detail", default="")

    reset = commands.add_parser("reset")
    reset.add_argument("--service", required=True)
    reset.add_argument("--reason", required=True)

    status = commands.add_parser("status")
    status.add_argument("--service")

    args = parser.parse_args()
    state = load_state(args.state)

    if args.command == "status":
        payload = state["services"].get(args.service, {}) if args.service else state
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    service = state["services"].setdefault(args.service, new_service())
    circuit = service["circuit"]

    if args.command == "reset":
        circuit.update(
            state="CLOSED",
            consecutive_service_failures=0,
            opened_reason="",
            reset_reason=args.reason,
            reset_at=now(),
        )
        save_state(args.state, state)
        print(json.dumps({"service": args.service, "circuit": "CLOSED", "reason": args.reason}, ensure_ascii=False))
        return

    key = operation_key(args.object_id, args.operation)
    entry = service["operations"].setdefault(
        key,
        {"object_id": args.object_id, "operation": args.operation, "attempts": 0, "status": "TODO", "history": []},
    )

    if args.command == "start":
        abandoned = settle_abandoned(entry, circuit)
        if circuit.get("state") == "OPEN":
            save_state(args.state, state)
            print(json.dumps({"allowed": False, "reason": "SERVICE_CIRCUIT_OPEN", "service": args.service, "abandoned_settled": abandoned}, ensure_ascii=False))
            raise SystemExit(2)
        if entry["attempts"] >= MAX_ATTEMPTS:
            entry["status"] = "BLOCKED"
            save_state(args.state, state)
            print(json.dumps({"allowed": False, "reason": "OPERATION_ATTEMPT_LIMIT", "service": args.service, "object_id": args.object_id, "operation": args.operation}, ensure_ascii=False))
            raise SystemExit(3)
        entry["attempts"] += 1
        entry["status"] = "IN_PROGRESS"
        entry["history"].append({"attempt": entry["attempts"], "method": args.method, "started_at": now(), "outcome": "PENDING"})
        save_state(args.state, state)
        print(json.dumps({"allowed": True, "service": args.service, "object_id": args.object_id, "operation": args.operation, "attempt": entry["attempts"]}, ensure_ascii=False))
        return

    if not entry["history"] or entry["history"][-1].get("outcome") != "PENDING":
        raise ValueError("finish requires a preceding pending start for this service/object/operation")
    entry["history"][-1].update(outcome=args.outcome, detail=args.detail, finished_at=now())

    if args.outcome == "PASS":
        entry["status"] = "PASS"
        circuit["consecutive_service_failures"] = 0
    elif args.outcome in SERVICE_FAILURES:
        entry["status"] = (
            "BLOCKED"
            if args.outcome == "AUTH_INVALID" or entry["attempts"] >= MAX_ATTEMPTS
            else "TODO"
        )
        mark_service_failure(circuit, args.outcome)
    else:
        entry["status"] = "BLOCKED" if entry["attempts"] >= MAX_ATTEMPTS else "TODO"
        circuit["consecutive_service_failures"] = 0

    save_state(args.state, state)
    print(json.dumps({
        "service": args.service,
        "object_id": args.object_id,
        "operation": args.operation,
        "attempts": entry["attempts"],
        "status": entry["status"],
        "circuit": circuit["state"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
