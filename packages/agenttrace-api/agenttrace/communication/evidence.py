from __future__ import annotations

import hashlib
import json
from pathlib import Path

from commsfail import Trace
from commsfail.annotators.standard.bundle import READ_RE
from commsfail.sources.sharednet import SAY_RE, is_board_command, parse_ts, post_ops

TEXT_LIMIT = 8000
INPUT_LIMIT = 240000


def digest(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def read_sequences(output: str) -> list[int] | None:
    try:
        value = json.loads(output)
    except ValueError:
        return None
    items = value.get("items", value.get("messages")) if isinstance(value, dict) else value
    if not isinstance(items, list) or any(
        not isinstance(item, dict) or type(item.get("sequence")) is not int or item["sequence"] <= 0
        for item in items
    ):
        return None
    return sorted({item["sequence"] for item in items})


def build_evidence(trace: Trace, raw_root: Path | None = None) -> dict:
    """Freeze evidence; only an explicitly allowlisted source may supply raw files."""
    events = []
    wakes = {(w["seat"], w["turn"]): w for w in trace.wakes if "seat" in w and "turn" in w}
    links = post_ops(trace)
    raw = {}
    raw_complete = {}
    if raw_root is not None:
        root = raw_root.resolve()
        for file in sorted(root.glob("agents/*/turn-*.jsonl")):
            if not file.resolve().is_relative_to(root):
                raise ValueError("Execution log escapes the allowlisted source.")
            turn = int(file.stem.split("-")[1])
            seat = file.parent.name
            rows = [json.loads(line) for line in file.read_text(encoding="utf-8").split("\n") if line.strip()]
            if any(not isinstance(row, dict) for row in rows):
                raise ValueError(f"Invalid execution event in {file.name}.")
            completed = []
            starts = {}
            for order, row in enumerate(rows):
                item = row.get("item")
                if row.get("type") == "item.started" and isinstance(item, dict):
                    starts[item.get("id")] = (order, row.get("timestamp"))
                if row.get("type") == "item.completed" and isinstance(item, dict):
                    if item.get("type") in (
                        "command_execution", "file_change", "web_search", "mcp_tool_call", "agent_message", "error",
                    ):
                        completed.append((item, order, starts.get(item.get("id")), row.get("timestamp")))
                elif row.get("type") in ("turn.failed", "error"):
                    completed.append(({"type": "error"}, order, None, row.get("timestamp")))
            for i, (item, order, start, end) in enumerate(completed):
                raw[(seat, turn, i)] = {
                    "item": item, "order": order, "start_order": start[0] if start else None,
                    "started_at": start[1] if start else None, "completed_at": end,
                }
            raw_complete[(seat, turn)] = any(row.get("type") == "turn.completed" for row in rows)

    for seat, ops in trace.ops.items():
        for op in ops:
            key = (seat, op["turn"], op["i"])
            source = raw.get(key)
            item = source["item"] if source else {}
            source_kind = {
                "command_execution": "command", "file_change": "file_change", "web_search": "web_search",
                "mcp_tool_call": "tool", "agent_message": "message", "error": "error",
            }.get(item.get("type"))
            if source and (
                source_kind != op["kind"]
                or (op["kind"] == "command" and item.get("command") != op.get("command"))
                or (op["kind"] == "command" and (item.get("aggregated_output") or "")[-500:] != op.get("output", ""))
                or (op["kind"] == "file_change" and item.get("type") != "file_change")
            ):
                raise ValueError("Raw execution log no longer matches the ingested operation.")
            output = item.get("aggregated_output", op.get("output", "")) or ""
            command = op.get("command", "")
            sequences = read_sequences(output) if op["kind"] == "command" and READ_RE.search(command) else None
            wake = wakes.get((seat, op["turn"]), {})
            events.append({
                "id": f"action:{seat}:{op['turn']}:{op['i']}", "kind": op["kind"],
                "actor": seat, "turn": op["turn"], "index": op["i"],
                "timestamp": source["started_at"] if source else None,
                "completed_at": source["completed_at"] if source else None,
                "turn_started_at": wake.get("started_at"),
                "order": source["order"] if source else None,
                "start_order": source["start_order"] if source else None,
                "raw": source is not None, "received_sequences": sequences,
                "unresolved_receipt_channel": op["kind"] == "tool" or (
                    is_board_command(command) and not (READ_RE.search(command) or SAY_RE.search(command))
                ) or bool(READ_RE.search(command) and sequences is None),
                "text": json.dumps({
                    "command": command, "output": output, "exit_code": op.get("exit_code"),
                    "paths": op.get("paths", []), "text": op.get("text", ""),
                    "tool": op.get("name"), "query": op.get("query"),
                    "details": item if op["kind"] != "command" else None,
                }, ensure_ascii=False),
            })
    actions = {event["id"]: event for event in events}
    for post in trace.posts:
        link = links.get(post["seq"])
        action = actions.get(f"action:{link[0]}:{link[1]}:{link[2]}") if link else None
        events.append({
            "id": f"post:{post['seq']}", "kind": "post", "actor": post["who"],
            "sequence": post["seq"], "timestamp": post.get("created_at"),
            "role": post.get("role"), "text": post.get("text", ""),
            "operation": action["id"] if action else None,
        })
    for (seat, turn), wake in sorted(wakes.items()):
        events.append({
            "id": f"wake:{seat}:{turn}", "kind": "wake", "actor": seat, "turn": turn,
            "timestamp": wake.get("started_at"), "text": json.dumps(wake, ensure_ascii=False),
        })
    for index, artifact in enumerate(trace.artifacts):
        events.append({
            "id": f"artifact:{index}", "kind": "artifact", "actor": artifact.get("by"),
            "timestamp": artifact.get("created_at"), "text": json.dumps(artifact, ensure_ascii=False),
        })
    ended = trace.episode.get("ended_by") or {}
    events.append({
        "id": "run:boundary", "kind": "boundary", "actor": None, "timestamp": None,
        "text": json.dumps({
            "state": trace.room.get("state"), "goal": trace.episode.get("goal"),
            "ended_by": {key: ended.get(key) for key in ("trigger", "at", "seat")},
        }, ensure_ascii=False),
    })
    actors = sorted({
        post["who"] for post in trace.posts if post.get("role") in (None, "agent")
    } | set(trace.ops) | {seat["handle"] for seat in trace.seats if seat.get("handle")})
    coverage = {
        "agents": actors, "agents_with_logs": sorted(seat for seat, ops in trace.ops.items() if ops),
        "raw_turns": len(raw_complete), "completed_raw_turns": sum(raw_complete.values()),
        "missing_raw_turns": [
            f"{seat}:{turn}" for seat, turn in sorted(set(wakes) | {(a["actor"], a["turn"]) for a in actions.values()})
            if not raw_complete.get((seat, turn))
        ],
        "run_closed": trace.room.get("state") == "closed",
        "wake_records": len(trace.wakes), "raw_outputs": bool(raw),
        "full_model_inputs": False, "workspace_history": False,
        "action_timestamps": bool(actions) and all(event["timestamp"] for event in actions.values()),
        "checks": len(trace.checks),
        "workspace_source_available": bool(raw_root and (raw_root / "workspace.git").exists()),
    }
    for event in events:
        operation = actions.get(event.get("operation")) if event.get("operation") else event if event["id"] in actions else None
        if operation is None:
            continue
        seat, turn = operation["actor"], operation["turn"]
        wake = wakes.get((seat, turn), {})
        known = set()
        overlapping = False
        unknown_channel = False
        for read in actions.values():
            if read["actor"] != seat or read["turn"] > turn:
                continue
            if read["unresolved_receipt_channel"]:
                unknown_channel = True
            if read["received_sequences"] is None:
                continue
            if read["turn"] < turn:
                known.update(read["received_sequences"])
                continue
            if operation["start_order"] is not None and read["order"] is not None:
                if read["order"] < operation["start_order"]:
                    known.update(read["received_sequences"])
                elif read["start_order"] is None or read["start_order"] < operation["order"]:
                    overlapping = True
        event["receipt"] = {
            "known_received": sorted(known),
            "initial_upper_bound": max([
                w["through"] for (actor, number), w in wakes.items()
                if actor == seat and number <= turn and type(w.get("through")) is int
            ], default=None) if type(wake.get("through")) is int else None,
            "absence_checkable": (
                bool(raw_complete.get((seat, turn))) and not overlapping and not unknown_channel
                and all(action["raw"] for action in actions.values() if action["actor"] == seat and action["turn"] <= turn)
                and all(raw_complete.get((seat, number)) for (actor, number) in wakes if actor == seat and number <= turn)
            ),
        }
    if raw_root is not None:
        from .capture import enrich, load_capture
        capture = load_capture(raw_root, trace)
        if capture is not None:
            enrich(events, coverage, capture, raw)
    bundle = {"schema": "agenttrace/communication-evidence.v1", "coverage": coverage, "events": events}
    bundle["sha256"] = digest(bundle)
    return bundle


def model_evidence(bundle: dict) -> dict:
    remaining = INPUT_LIMIT
    events = []
    truncated = []
    omitted = []
    # Messages precede tool detail so long command output cannot hide the conversation.
    priorities = {"post": 0, "wake": 0, "boundary": 0, "input": 1, "delivery": 1, "workspace": 1}
    ordered = sorted(bundle["events"], key=lambda event: (
        priorities.get(event["kind"], 3 if event["kind"] == "detail" else 2),
    ))
    for event in ordered:
        if remaining <= 0:
            omitted.append(event["id"])
            continue
        count = min(TEXT_LIMIT, remaining)
        text = event["text"][:count]
        if len(text) < len(event["text"]):
            truncated.append(event["id"])
        events.append({**event, "text": text})
        remaining -= len(text)
    return {
        "schema": bundle["schema"], "sha256": bundle["sha256"],
        "coverage": {
            **bundle["coverage"], "total_events": len(bundle["events"]), "supplied_events": len(events),
            "truncated_events": truncated, "omitted_events": omitted,
            "text_limit": TEXT_LIMIT, "input_text_limit": INPUT_LIMIT,
        },
        "events": events,
    }


def receipt_status(bundle: dict, post_id: str, dependent_id: str) -> str:
    by_id = {event["id"]: event for event in bundle["events"]}
    post, dependent = by_id[post_id], by_id[dependent_id]
    receipt = dependent.get("receipt", {})
    sequence = post.get("sequence")
    if sequence in receipt.get("known_received", []):
        return "received"
    upper = receipt.get("initial_upper_bound")
    published = parse_ts(post.get("timestamp"))
    operation = by_id.get(dependent.get("operation"), dependent)
    cutoff = parse_ts(operation.get("timestamp") or operation.get("turn_started_at"))
    if receipt.get("source") == "validated_recorded_prompts_and_tool_outputs":
        if (receipt.get("capture_complete") and not receipt.get("uncertain_channel") and published and cutoff
                and published.tzinfo and cutoff.tzinfo and published <= cutoff):
            return "not_received"
        return "unknown"
    if (type(upper) is int and type(sequence) is int and sequence > upper
            and receipt.get("absence_checkable") and published and cutoff
            and published.tzinfo and cutoff.tzinfo and published <= cutoff):
        return "not_received"
    return "unknown"
