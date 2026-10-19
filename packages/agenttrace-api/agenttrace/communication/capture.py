"""Validated optional delivery/action/workspace captures from a local run."""
from __future__ import annotations

import hashlib
import json
import re
import shlex
import subprocess
from pathlib import Path

from commsfail.sources.sharednet import parse_ts


def sha(text):
    return hashlib.sha256(text.encode() if isinstance(text, str) else text).hexdigest()


def local(root: Path, path: str) -> Path:
    result = root / path
    if not result.resolve().is_relative_to(root.resolve()):
        raise ValueError("Capture file escapes the allowlisted source.")
    return result


def lines(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").split("\n") if line.strip()]


def output_text(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(part.get("text", "") for part in value if isinstance(part, dict))
    raise ValueError("Unsupported captured tool-output format.")


def received(text, room):
    """Only complete, matching message objects establish receipt."""
    found = set()
    decoder = json.JSONDecoder()
    def visit(value):
        if isinstance(value, list):
            for item in value:
                visit(item)
        elif isinstance(value, dict):
            sequence = value.get("sequence")
            post = room.get(sequence) if type(sequence) is int else None
            if post and value.get("id") == post["id"] and value.get("content") == post["content"]:
                found.add(sequence)
            for item in value.values():
                if isinstance(item, (list, dict)):
                    visit(item)
    for match in re.finditer(r"[\[{]", text):
        try:
            value, _ = decoder.raw_decode(text, match.start())
        except json.JSONDecodeError:
            continue
        visit(value)
    return sorted(found)


def prompt_received(text, room):
    result = set()
    if 1 in room and room[1]["content"].strip() and room[1]["content"].strip() in text:
        result.add(1)
    for start, end in re.findall(r"New in the Room since your last turn \(#(\d+) to #(\d+)\)", text):
        for sequence in range(int(start), int(end) + 1):
            post = room.get(sequence)
            sender = (post.get("sender") or {}) if post else {}
            name = sender.get("name") or sender.get("member_id") or "someone"
            if post and f"#{sequence} {name}: {post['content']}" in text:
                result.add(sequence)
    return sorted(result)


def timestamp(value):
    parsed = parse_ts(value)
    if parsed is None or parsed.tzinfo is None:
        raise ValueError("Captured event requires a timezone-aware timestamp.")
    return parsed


def git(root, *arguments):
    directory = local(root, "workspace.git")
    for file in directory.rglob("*"):
        if file.is_symlink() and not file.resolve().is_relative_to(root.resolve()):
            raise ValueError("Workspace file escapes the allowlisted source.")
    try:
        return subprocess.run(
            ["git", "--no-optional-locks", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null",
             f"--git-dir={directory}", *arguments],
            check=True, capture_output=True,
        ).stdout
    except subprocess.CalledProcessError as error:
        raise ValueError("Workspace Git evidence is incomplete or invalid.") from error


def load_capture(root: Path, trace) -> dict | None:
    names = ("inputs.jsonl", "actions.jsonl", "workspace.json")
    present = [local(root, name).exists() for name in names]
    if not any(present):
        return None
    if not all(present):
        raise ValueError("Incomplete capture: inputs, actions and workspace manifests are all required.")
    checksums = local(root, "SHA256SUMS")
    if checksums.exists():
        for line in checksums.read_text().split("\n"):
            if line.strip():
                expected, name = line.split("  ", 1)
                if sha(local(root, name).read_bytes()) != expected:
                    raise ValueError(f"Capture checksum mismatch: {name}")
        record = local(root, "run.json")
        if record.exists() and json.loads(record.read_text())["artifact"]["sha256"] != sha(checksums.read_bytes()):
            raise ValueError("Capture manifest checksum mismatch.")
    room = {post["sequence"]: post for post in lines(local(root, "room.ndjson"))}
    if len(room) != len(trace.posts) or any(
        post["seq"] not in room or room[post["seq"]]["content"] != post["text"]
        or room[post["seq"]].get("created_at") != post.get("created_at")
        for post in trace.posts
    ):
        raise ValueError("Captured room no longer matches the ingested trace.")
    inputs = lines(local(root, "inputs.jsonl"))
    actions = lines(local(root, "actions.jsonl"))
    input_map = {item["input_id"]: item for item in inputs}
    if len(input_map) != len(inputs):
        raise ValueError("Duplicate captured input IDs.")
    expected_turns = {(wake["seat"], wake["turn"]) for wake in trace.wakes}
    if len(inputs) != len(expected_turns) or {(item["agent"], item["turn"]) for item in inputs} != expected_turns:
        raise ValueError("Captured inputs must cover exactly the recorded wakes.")
    agents = {seat for seat, _ in expected_turns}
    native_actions, calls, turns = {}, {}, {}
    indices = {}
    compactions = []
    completed_turns = set()
    session_hashes = {}
    for agent in sorted(agents):
        session_path = local(root, f"agents/{agent}/session.jsonl")
        session_hashes[agent] = sha(session_path.read_bytes())
        session = lines(session_path)
        turn = None
        for row in session:
            payload = row.get("payload") or {}
            kind = payload.get("type")
            if "compact" in str(row.get("type")) or "compact" in str(kind):
                compactions.append(f"{agent}:{row.get('timestamp')}")
            if row.get("type") == "event_msg" and kind == "task_started":
                turn = payload["turn_id"]
                if (agent, turn) in turns:
                    raise ValueError("Duplicate native turn ID.")
                turns[(agent, turn)] = []
            elif row.get("type") == "event_msg" and kind == "task_complete":
                completed_turns.add((agent, payload["turn_id"]))
            elif row.get("type") == "response_item":
                if kind == "message" and payload.get("role") in ("user", "developer"):
                    text = output_text(payload.get("content"))
                    # Developer preambles can precede task_started.
                    turns.setdefault((agent, turn), []).append({
                        "role": payload["role"], "at": row["timestamp"],
                        "sha256": sha(text), "chars": len(text), "text": text,
                    })
                elif kind in ("function_call", "custom_tool_call"):
                    key = (agent, payload["call_id"])
                    if key in calls:
                        raise ValueError("Duplicate native tool call.")
                    calls[key] = {"turn_id": turn, "started_at": row["timestamp"]}
                elif kind in ("function_call_output", "custom_tool_call_output"):
                    call = calls[(agent, payload["call_id"])]
                    call.update(completed_at=row["timestamp"], text=output_text(payload["output"]))
            elif row.get("type") == "event_msg" and kind == "item_completed":
                item = payload.get("item") or {}
                if item.get("type") in ("CommandExecution", "FileChange", "AgentMessage", "WebSearch", "McpToolCall"):
                    key = (agent, item["id"])
                    if key in native_actions:
                        raise ValueError("Duplicate native action ID.")
                    index_key = (agent, turn)
                    index = indices.get(index_key, 0)
                    indices[index_key] = index + 1
                    native_actions[key] = {**payload, "turn_id": turn, "stream_index": index}
    ledger = {agent: [] for agent in agents}
    for item in inputs:
        key = (item["agent"], item["turn_id"])
        prompts = turns[key]
        if item["turn"] == 1:
            prompts = turns.get((item["agent"], None), []) + prompts
        if prompts != item["prompts"]:
            raise ValueError("Captured prompts do not match the native session.")
        exact = sorted({seq for prompt in prompts for seq in prompt_received(prompt["text"], room)})
        expected = [
            {"sequence": seq, "message_id": room[seq]["id"], "content_sha256": sha(room[seq]["content"])}
            for seq in exact
        ]
        if sorted(item["delivered_in_prompt"], key=lambda ref: ref["sequence"]) != expected:
            raise ValueError("Captured prompt deliveries do not match their content.")
        for prompt in prompts:
            ledger[item["agent"]].append({
                "at": prompt["at"], "sequences": prompt_received(prompt["text"], room),
                "source": f"input:{item['input_id']}", "uncertain": False,
            })
    for (agent, call_id), call in calls.items():
        if "completed_at" not in call:
            continue
        text = call["text"]
        sequences = received(text, room)
        # Partial/truncated message objects cannot justify deterministic nonreceipt.
        partial = set(map(int, re.findall(r'"sequence"\s*:\s*(\d+)', text))) - set(sequences)
        ledger[agent].append({
            "at": call["completed_at"], "sequences": sequences, "source": f"tool-output:{agent}:{call_id}",
            "uncertain": bool(partial) or bool(re.search(r"output.{0,30}truncat", text, re.I)),
        })
    mapped = {}
    for action in actions:
        key = (action["agent"], action["action_id"])
        native = native_actions[key]
        item = native["item"]
        entry = input_map[action["input_id"]]
        if (entry["agent"], entry["turn"], entry["turn_id"]) != (action["agent"], action["turn"], native["turn_id"]):
            raise ValueError("Captured action has an invalid input/turn association.")
        start, end = timestamp(action["started_at"]), timestamp(action["completed_at"])
        if end < start or int(start.timestamp() * 1000) != native["started_at_ms"] or int(end.timestamp() * 1000) != native["completed_at_ms"]:
            # Compare milliseconds with rounding, avoiding floating point underflow.
            if end < start or round(start.timestamp() * 1000) != native["started_at_ms"] or round(end.timestamp() * 1000) != native["completed_at_ms"]:
                raise ValueError("Captured action timestamps do not match native events.")
        if action["type"] != item["type"]:
            raise ValueError("Captured action kind does not match native events.")
        if action["type"] == "CommandExecution":
            command = item["command"] if isinstance(item["command"], str) else " ".join(item["command"])
            output = item.get("aggregated_output") or ""
            if action["command"] != command or action["output_sha256"] != sha(output) or action["exit_code"] != item.get("exit_code"):
                raise ValueError("Captured command/output does not match native events.")
        enclosing = [
            call_id for (agent, call_id), call in calls.items()
            if agent == action["agent"] and call["turn_id"] == action["turn_id"] and "completed_at" in call
            and timestamp(call["started_at"]) <= start <= timestamp(call["completed_at"])
        ]
        if action["call_id"] is not None and action["call_id"] not in enclosing:
            raise ValueError("Captured tool link does not enclose the native action start.")
        mapped[key] = {**action, "native": item, "stream_index": native["stream_index"],
                       "call_link_unique": len(enclosing) == 1}
    if set(mapped) != set(native_actions):
        raise ValueError("Captured action manifest does not cover every native action.")
    workspace = json.loads(local(root, "workspace.json").read_text())
    snapshots = []
    for snapshot in workspace["snapshots"]:
        commit, tree = snapshot["commit"], snapshot["tree"]
        if not re.fullmatch(r"[0-9a-f]{40}", commit) or not re.fullmatch(r"[0-9a-f]{40}", tree):
            raise ValueError("Invalid workspace object ID.")
        actual_tree = git(root, "show", "-s", "--format=%T", commit).decode().strip()
        actual_time = git(root, "show", "-s", "--format=%cI", commit).decode().strip()
        if actual_tree != tree or timestamp(actual_time) != timestamp(snapshot["at"]):
            raise ValueError("Workspace tree does not match its snapshot.")
        diff = git(root, "diff-tree", "--root", "--no-commit-id", "-p", "--no-ext-diff", "--no-textconv", commit, "--").decode(errors="replace")
        snapshots.append({**snapshot, "diff": diff})
    if not snapshots or workspace["baseline"] != workspace["snapshots"][0] or workspace["final"] != workspace["snapshots"][-1]:
        raise ValueError("Workspace baseline/final do not match its snapshots.")
    final_tree = {}
    for line in git(root, "ls-tree", "-r", "-z", workspace["final"]["commit"]).split(b"\0"):
        if line:
            metadata, path = line.split(b"\t", 1)
            _, kind, object_id = metadata.decode().split()
            if kind == "blob":
                final_tree[path.decode()] = object_id
    if final_tree != {item["path"]: item["git_blob"] for item in workspace["final_files"]}:
        raise ValueError("Workspace final file list does not match the final tree.")
    for item in workspace["final_files"]:
        if sha(git(root, "cat-file", "blob", item["git_blob"])) != item["sha256"]:
            raise ValueError("Workspace final file checksum mismatch.")
    return {
        "inputs": inputs, "actions": mapped, "calls": calls, "ledger": ledger, "room": room,
        "snapshots": snapshots, "workspace": workspace, "compactions": compactions,
        "sha256": {name: sha(local(root, name).read_bytes()) for name in names},
        "session_sha256": session_hashes,
        "incomplete_turns": [
            item["input_id"] for item in inputs if (item["agent"], item["turn_id"]) not in completed_turns
        ],
        "incomplete_calls": [f"{agent}:{call_id}" for (agent, call_id), call in calls.items() if "completed_at" not in call],
    }


def enrich(events, coverage, capture, raw):
    by_id = {event["id"]: event for event in events}
    added = []
    if len(capture["actions"]) != sum(event["id"].startswith("action:") for event in events):
        raise ValueError("Native actions do not cover exactly the ingested operations.")

    def text_event(event, value, summary=None):
        full = json.dumps(value, ensure_ascii=False)
        if summary is not None and len(full) > 800:
            detail_id = f"detail:{event['id']}"
            event["text"] = json.dumps({**summary, "full_detail_event": detail_id}, ensure_ascii=False)
            added.append({
                "id": detail_id, "kind": "detail", "actor": event["actor"],
                "timestamp": event["timestamp"], "parent": event["id"], "text": full,
            })
        else:
            event["text"] = full

    for event in events:
        if not event["id"].startswith("action:"):
            continue
        source = raw.get((event["actor"], event["turn"], event["index"]))
        if source is None:
            raise ValueError("Rich action capture requires matching raw turn logs.")
        matches = [
            action for action in capture["actions"].values()
            if action["agent"] == event["actor"] and action["turn"] == event["turn"]
            and action["stream_index"] == event["index"]
        ]
        if len(matches) != 1:
            raise ValueError("Native action stream does not align with the raw turn.")
        action = matches[0]
        native_id = action["action_id"]
        item = source["item"]
        expected_kind = {
            "command_execution": "CommandExecution", "file_change": "FileChange",
            "agent_message": "AgentMessage", "web_search": "WebSearch", "mcp_tool_call": "McpToolCall",
        }.get(item["type"])
        if action["type"] != expected_kind:
            raise ValueError("Native action kind does not align with the raw turn.")
        if expected_kind == "CommandExecution" and (
            shlex.split(item["command"]) != (
                action["native"]["command"] if isinstance(action["native"]["command"], list)
                else shlex.split(action["native"]["command"])
            )
            or item.get("aggregated_output", "") != action["native"].get("aggregated_output", "")
        ):
            raise ValueError("Native command does not align with the raw turn.")
        if expected_kind == "AgentMessage":
            native_text = action["native"].get("text") or output_text(action["native"].get("content", []))
            if item.get("text", "") != native_text:
                raise ValueError("Native agent message does not align with the raw turn.")
        if expected_kind == "FileChange" and (
            {change["path"] for change in item.get("changes", [])}
            != set(action["native"].get("changes", {}))
        ):
            raise ValueError("Native file changes do not align with the raw turn.")
        if action["turn"] != event["turn"]:
            raise ValueError("Native action and raw turn association differ.")
        event.update(
            timestamp=action["started_at"], completed_at=action["completed_at"],
            native_action_id=native_id, input_id=action["input_id"], call_id=action["call_id"],
            call_link="unique_temporal_start_enclosure" if action["call_link_unique"] else "ambiguous",
        )
        value = json.loads(event["text"])
        value.update(
            started_at=event["timestamp"], completed_at=event["completed_at"],
            native_action_id=native_id, input_id=action["input_id"], call_id=action["call_id"],
            call_link=event["call_link"],
        )
        if action["type"] == "FileChange":
            value["native_changes"] = action["native"].get("changes")
        call = capture["calls"].get((event["actor"], action["call_id"]))
        if call and "completed_at" in call:
            value["tool_output_available_at"] = call["completed_at"]
            value["model_visible_output_sha256"] = sha(call["text"])
            value["native_output_after_tool_return"] = timestamp(event["completed_at"]) > timestamp(call["completed_at"])
        if "room_read" in action:
            returned = received(action["native"].get("aggregated_output") or "", capture["room"])
            visible = received(call["text"], capture["room"]) if call and "text" in call and action["call_link_unique"] else None
            event["returned_sequences"] = returned
            event["received_sequences"] = visible
            value["room_read"] = {"returned_sequences": returned, "model_visible_sequences": visible}
            if call and "completed_at" in call:
                output_id = f"tool-output:{event['actor']}:{action['call_id']}"
                if output_id not in by_id:
                    output = {
                        "id": output_id, "kind": "delivery", "actor": event["actor"],
                        "timestamp": call["completed_at"], "turn": event["turn"],
                    }
                    text_event(output, {"model_visible_output": call["text"], "received_sequences": visible}, {
                        "model_visible_output_excerpt": call["text"][:500],
                        "model_visible_output_chars": len(call["text"]), "received_sequences": visible,
                    })
                    added.append(output)
                    by_id[output_id] = output
                value["tool_output_event"] = output_id
        text_event(event, value, {
            **{key: value[key] for key in ("exit_code", "paths", "room_read", "tool_output_event", "native_output_after_tool_return") if key in value},
            "command": value.get("command", "")[:350], "command_chars": len(value.get("command", "")),
            "output": value.get("output", "")[:100], "output_chars": len(value.get("output", "")),
            "text": value.get("text", "")[:200], "text_chars": len(value.get("text", "")),
        })
    for event in events:
        operation = by_id.get(event.get("operation")) if event.get("operation") else event if event["id"].startswith("action:") else None
        if operation is None:
            continue
        cutoff = timestamp(operation["timestamp"])
        prior = [entry for entry in capture["ledger"][operation["actor"]] if timestamp(entry["at"]) <= cutoff]
        event["receipt"] = {
            "known_received": sorted({seq for entry in prior for seq in entry["sequences"]}),
            "capture_complete": not any((
                capture["compactions"], capture["incomplete_turns"], capture["incomplete_calls"],
                coverage["missing_raw_turns"],
            )),
            "uncertain_channel": any(entry["uncertain"] for entry in prior),
            "cutoff": operation["timestamp"], "source": "validated_recorded_prompts_and_tool_outputs",
        }
    for item in capture["inputs"]:
        event = {
            "id": f"input:{item['input_id']}", "kind": "input", "actor": item["agent"],
            "timestamp": item["started_at"], "turn": item["turn"],
        }
        text_event(event, {"prompts": item["prompts"]}, {
            "input_id": item["input_id"], "turn_id": item["turn_id"],
            "delivered_sequences": [ref["sequence"] for ref in item["delivered_in_prompt"]],
            "prompt_sha256": [prompt["sha256"] for prompt in item["prompts"]],
            "note": "Recorded turn-opening messages, not serialized model API requests.",
        })
        added.append(event)
    workspace = capture["workspace"]
    added.append({
        "id": "workspace:manifest", "kind": "workspace", "actor": None, "timestamp": None,
        "text": json.dumps({
            "baseline": workspace["baseline"], "final": workspace["final"],
            "final_files": workspace["final_files"],
            "note": "Snapshots are per room-message batch, NOT per action. Same-second ordering and concurrent shell writers remain uncertain.",
        }, ensure_ascii=False),
    })
    for snapshot in capture["snapshots"]:
        event = {
            "id": f"workspace:{snapshot['commit']}", "kind": "workspace", "actor": None,
            "timestamp": snapshot["at"],
        }
        text_event(event, snapshot, {key: value for key, value in snapshot.items() if key != "diff"} | {
            "diff_excerpt": snapshot["diff"][:600], "diff_chars": len(snapshot["diff"]),
            "note": "Second-resolution batch snapshot; not an action attribution.",
        })
        added.append(event)
    coverage.update(
        recorded_inputs=True, workspace_history=True, action_timestamps=True,
        capture_sha256=capture["sha256"], capture_compactions=capture["compactions"],
        capture_session_sha256=capture["session_sha256"],
        incomplete_session_turns=capture["incomplete_turns"], incomplete_tool_calls=capture["incomplete_calls"],
        action_linked_workspace=False, workspace_snapshots=len(capture["snapshots"]),
        model_request_serialization=False,
    )
    events.extend(added)
