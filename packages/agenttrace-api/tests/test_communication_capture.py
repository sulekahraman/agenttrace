import hashlib
import json
import subprocess
from datetime import datetime

import pytest
from commsfail.sources.sharednet import parse_turn

from agenttrace.communication.capture import received
from agenttrace.communication.evidence import build_evidence, model_evidence, receipt_status
from test_communication import synthetic_record


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False))


def save_lines(path, values):
    path.write_text("\n".join(json.dumps(value, ensure_ascii=False) for value in values) + "\n")


def capture_record(root, *, hidden_read=False):
    trace = synthetic_record(root)
    room = [
        {"sequence": post["seq"], "id": f"msg_{post['seq']}", "content": post["text"],
         "created_at": post["created_at"], "sender": {"name": post["who"]}}
        for post in trace.posts
    ]
    save_lines(root / "room.ndjson", room)
    save_lines(root / "wakes.ndjson", trace.wakes)
    save(root / "episode.json", {
        **trace.episode, "agents": [{"name": seat["handle"], "driver": "codex"} for seat in trace.seats],
    })
    inputs, actions = [], []
    for agent in ("alpha", "beta"):
        session = []
        for wake in (wake for wake in trace.wakes if wake["seat"] == agent):
            turn = wake["turn"]
            turn_id = f"{agent}-{turn}"
            input_id = f"{agent}/turn-{turn:03d}"
            at = f"2026-10-15T00:00:0{2 if turn == 1 else 5}"
            session.append({"type": "event_msg", "timestamp": at + ".000Z",
                            "payload": {"type": "task_started", "turn_id": turn_id}})
            prompt = "Opening instructions." if agent == "beta" else "Use red."
            prompt_at = at + ".001Z"
            session.append({"type": "response_item", "timestamp": prompt_at, "payload": {
                "type": "message", "role": "user", "content": [{"text": prompt}],
            }})
            prompts = [{"role": "user", "at": prompt_at, "text": prompt,
                        "sha256": hashlib.sha256(prompt.encode()).hexdigest(), "chars": len(prompt)}]
            inputs.append({
                "input_id": input_id, "agent": agent, "turn": turn, "turn_id": turn_id,
                "started_at": at + ".000Z", "prompts": prompts,
                "delivered_in_prompt": [
                    {"sequence": 1, "message_id": "msg_1", "content_sha256": hashlib.sha256(b"Use red.").hexdigest()}
                ] if agent == "alpha" else [],
                "room_reads": [],
            })
            path = root / f"agents/{agent}/turn-{turn:03d}.jsonl"
            raw = [json.loads(line) for line in path.read_text().split("\n")]
            completed = [row["item"] for row in raw if row["type"] == "item.completed"]
            for index, item in enumerate(completed):
                if "sharednet read" in item["command"]:
                    sequence = 1 if turn == 1 else 3
                    output = json.dumps({"items": [room[sequence - 1]]})
                    item["aggregated_output"] = output
                    for row in raw:
                        if row.get("item", {}).get("id") == item["id"]:
                            row["item"]["aggregated_output"] = output
                output = item["aggregated_output"]
                call_id = f"call-{agent}-{turn}-{index}"
                native_id = f"native-{agent}-{turn}-{index}"
                start = at + f".{index * 100 + 20:03d}Z"
                end = at + f".{index * 100 + 50:03d}Z"
                call_start = at + f".{index * 100 + 10:03d}Z"
                call_end = at + f".{index * 100 + 60:03d}Z"
                if hidden_read and agent == "beta" and turn == 1 and index == 0:
                    call_end = at + ".040Z"
                visible = "" if hidden_read and agent == "beta" and turn == 1 and index == 0 else output
                session.extend([
                    {"type": "response_item", "timestamp": call_start, "payload": {
                        "type": "function_call", "call_id": call_id, "name": "exec",
                    }},
                    {"type": "event_msg", "timestamp": end, "payload": {
                        "type": "item_completed", "turn_id": turn_id,
                        "started_at_ms": round(datetime.fromisoformat(start.replace("Z", "+00:00")).timestamp() * 1000),
                        "completed_at_ms": round(datetime.fromisoformat(end.replace("Z", "+00:00")).timestamp() * 1000),
                        "item": {"id": native_id, "type": "CommandExecution", "command": item["command"],
                                 "aggregated_output": output, "exit_code": 0},
                    }},
                    {"type": "response_item", "timestamp": call_end, "payload": {
                        "type": "function_call_output", "call_id": call_id, "output": visible,
                    }},
                ])
                actions.append({
                    "agent": agent, "turn": turn, "turn_id": turn_id, "input_id": input_id,
                    "action_id": native_id, "call_id": call_id, "type": "CommandExecution",
                    "command": item["command"], "output_sha256": hashlib.sha256(output.encode()).hexdigest(),
                    "started_at": start, "completed_at": end, "exit_code": 0,
                    **({"room_read": {}} if "sharednet read" in item["command"] else {}),
                })
            save_lines(path, raw)
            parsed = parse_turn(path.read_text().split("\n"), "codex", turn)
            previous = [op for op in trace.ops[agent] if op["turn"] == turn]
            for op, old in zip(parsed, previous):
                if "posted" in old:
                    op["posted"] = old["posted"]
            trace.ops[agent] = [op for op in trace.ops[agent] if op["turn"] != turn] + parsed
            session.append({"type": "event_msg", "timestamp": at + ".999Z", "payload": {
                "type": "task_complete", "turn_id": turn_id,
            }})
        save_lines(root / f"agents/{agent}/session.jsonl", session)
    save_lines(root / "inputs.jsonl", inputs)
    save_lines(root / "actions.jsonl", actions)
    directory = root / "workspace.git"
    worktree = root / "worktree"
    worktree.mkdir()
    (worktree / "result.txt").write_text("red\n")
    def git(*args):
        return subprocess.run(
            ["git", f"--git-dir={directory}", f"--work-tree={worktree}", *args],
            check=True, capture_output=True,
        ).stdout.decode().strip()
    subprocess.run(["git", "init", "--bare", str(directory)], check=True, capture_output=True)
    git("add", "result.txt")
    git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", "start")
    commit, tree, at = git("show", "-s", "--format=%H %T %cI", "HEAD").split()
    snapshot = {"commit": commit, "tree": tree, "at": at, "label": "start"}
    blob = git("rev-parse", "HEAD:result.txt")
    save(root / "workspace.json", {
        "baseline": snapshot, "final": snapshot, "snapshots": [snapshot],
        "final_files": [{"path": "result.txt", "git_blob": blob, "sha256": hashlib.sha256(b"red\n").hexdigest()}],
    })
    return trace


def test_native_capture_receipt_timing_and_workspace(tmp_path):
    trace = capture_record(tmp_path)
    bundle = build_evidence(trace, tmp_path)
    assert bundle["coverage"]["recorded_inputs"]
    assert bundle["coverage"]["workspace_history"]
    assert not bundle["coverage"]["full_model_inputs"]
    assert not bundle["coverage"]["action_linked_workspace"]
    assert receipt_status(bundle, "post:1", "action:beta:1:1") == "received"
    assert receipt_status(bundle, "post:3", "action:beta:1:1") == "unknown"
    action = next(event for event in bundle["events"] if event["id"] == "action:beta:1:1")
    assert action["native_action_id"] == "native-beta-1-1"
    assert action["timestamp"].endswith(".120Z")
    assert any(event["id"] == "workspace:manifest" for event in bundle["events"])


def test_local_api_ingestion_persists_richer_evidence_without_generation(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from agenttrace.api import create_app

    root = tmp_path / "capture"
    capture_record(root)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    app = create_app(data_dir=tmp_path / "state", source_root=root)
    with TestClient(app) as client:
        response = client.post("/api/traces", json={"source": {"type": "local", "value": "."}})
        assert response.status_code == 200, response.text
        identifier = response.json()["traceId"]
        setup = client.get("/api/communication/setup", params={"trace_id": identifier}).json()
        assert setup["version"] == "0.2.0"
        assert setup["coverage"]["recorded_inputs"]
        assert setup["coverage"]["workspace_history"]
        runs = client.get(f"/api/traces/{identifier}/analyses").json()
        assert len(runs) == 2
        assert all(run["analyzer"]["kind"] == "offline" for run in runs)


def test_native_stdout_is_not_model_receipt(tmp_path):
    bundle = build_evidence(capture_record(tmp_path, hidden_read=True), tmp_path)
    assert receipt_status(bundle, "post:1", "action:beta:1:1") == "not_received"
    read = next(event for event in bundle["events"] if event["id"] == "action:beta:1:0")
    assert read["returned_sequences"] == [1]
    assert read["received_sequences"] == []
    output = next(event for event in bundle["events"] if event["id"] == "tool-output:beta:call-beta-1-0")
    assert '"model_visible_output": ""' in output["text"]


@pytest.mark.parametrize("target,field,value,match", [
    ("inputs.jsonl", "prompts", [], "prompts"),
    ("actions.jsonl", "completed_at", "2026-10-15T00:00:01Z", "timestamps"),
    ("actions.jsonl", "command", "forged command", "command/output"),
])
def test_tampered_capture_is_rejected(tmp_path, target, field, value, match):
    trace = capture_record(tmp_path)
    path = tmp_path / target
    rows = [json.loads(line) for line in path.read_text().split("\n") if line.strip()]
    rows[0][field] = value
    save_lines(path, rows)
    with pytest.raises(ValueError, match=match):
        build_evidence(trace, tmp_path)


def test_partial_capture_and_symlink_escape_fail_explicitly(tmp_path):
    trace = synthetic_record(tmp_path)
    save_lines(tmp_path / "inputs.jsonl", [])
    with pytest.raises(ValueError, match="Incomplete capture"):
        build_evidence(trace, tmp_path)
    (tmp_path / "inputs.jsonl").unlink()
    root = tmp_path / "child"
    root.mkdir()
    (root / "inputs.jsonl").symlink_to(tmp_path / "outside.jsonl")
    with pytest.raises(ValueError, match="escapes"):
        build_evidence(trace, root)


def test_partial_message_object_does_not_establish_receipt():
    room = {1: {"id": "msg_1", "content": "Full message"}}
    assert received('{"sequence":1,"id":"msg_1","content":"Full', room) == []
    assert received('{"sequence":1,"id":"msg_1","content":"Full message"}', room) == [1]
    assert received('{"sequence":1,"id":"msg_1","content":"Wrong message"}', room) == []


def test_capture_checksum_failure_is_explicit(tmp_path):
    trace = capture_record(tmp_path)
    (tmp_path / "SHA256SUMS").write_text("0" * 64 + "  inputs.jsonl\n")
    with pytest.raises(ValueError, match="checksum"):
        build_evidence(trace, tmp_path)


def test_compaction_prevents_nonreceipt_inference(tmp_path):
    trace = capture_record(tmp_path, hidden_read=True)
    path = tmp_path / "agents/beta/session.jsonl"
    with path.open("a") as file:
        file.write(json.dumps({"type": "compacted", "timestamp": "2026-10-15T00:00:02Z", "payload": {}}) + "\n")
    bundle = build_evidence(trace, tmp_path)
    assert receipt_status(bundle, "post:1", "action:beta:1:1") == "unknown"
    assert bundle["coverage"]["capture_compactions"]


@pytest.mark.parametrize("missing", ["task_complete", "function_call_output"])
def test_incomplete_native_capture_prevents_nonreceipt_inference(tmp_path, missing):
    trace = capture_record(tmp_path, hidden_read=True)
    path = tmp_path / "agents/beta/session.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    if missing == "task_complete":
        rows = [row for row in rows if row.get("payload", {}).get("type") != missing]
    else:
        rows.append({"type": "response_item", "timestamp": "2026-10-15T00:00:02Z", "payload": {
            "type": "function_call", "call_id": "unfinished-call",
        }})
    save_lines(path, rows)
    bundle = build_evidence(trace, tmp_path)
    assert receipt_status(bundle, "post:1", "action:beta:1:1") == "unknown"
    key = "incomplete_session_turns" if missing == "task_complete" else "incomplete_tool_calls"
    assert bundle["coverage"][key]
    assert bundle["coverage"]["capture_session_sha256"]["beta"]


def test_missing_referenced_tool_output_fails_explicitly(tmp_path):
    trace = capture_record(tmp_path, hidden_read=True)
    path = tmp_path / "agents/beta/session.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    save_lines(path, [row for row in rows if row.get("payload", {}).get("type") != "function_call_output"])
    with pytest.raises(ValueError, match="tool link"):
        build_evidence(trace, tmp_path)


def test_invalid_workspace_fails_explicitly(tmp_path):
    trace = capture_record(tmp_path)
    path = tmp_path / "workspace.json"
    workspace = json.loads(path.read_text())
    workspace["snapshots"][0]["commit"] = "0" * 40
    save(path, workspace)
    with pytest.raises(ValueError, match="Workspace Git evidence"):
        build_evidence(trace, tmp_path)


def test_evidence_caps_prioritize_core_before_detail(tmp_path, monkeypatch):
    bundle = build_evidence(capture_record(tmp_path), tmp_path)
    from agenttrace.communication import evidence
    core = [event for event in bundle["events"] if event["kind"] != "detail"]
    monkeypatch.setattr(evidence, "TEXT_LIMIT", 100000)
    monkeypatch.setattr(evidence, "INPUT_LIMIT", sum(len(event["text"]) for event in core))
    supplied = model_evidence(bundle)
    assert not {event["id"] for event in core} & set(supplied["coverage"]["omitted_events"])
    assert any(event_id.startswith("detail:") for event_id in supplied["coverage"]["omitted_events"])
