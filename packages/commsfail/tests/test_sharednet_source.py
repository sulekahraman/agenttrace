"""The SharedNet source: each reader fills the Trace it can, and the tools work on any Trace."""
import json
from commsfail.sources import sharednet as sn

def test_goal_run_record(goal_run):
    t = goal_run
    assert t.source["kind"] == "goal-run" and t.source["room_id"] == "rom_fixture0001"
    assert [s["handle"] for s in t.seats] == ["codex-1", "codex-2", "codex-3"]
    assert t.seats[0]["model"] == "gpt-6-luna" and t.seats[0]["member_id"] == "i_fx1"
    assert [p["seq"] for p in t.posts] == list(range(1, 13))
    assert t.posts[0]["role"] == "goal" and {p["role"] for p in t.posts[1:]} == {"agent"}
    assert t.posts[3]["who"] == "codex-3"
    assert t.room["state"] == "closed" and t.room["latest_sequence"] == 12 and t.room["name"] == "goal_run"
    assert t.episode["ended_by"]["trigger"] == "after 45m"
    assert len(t.checks) == 1 and t.checks[0]["passed"] is False
    assert len(t.wakes) == 7 and t.has_ops and not t.has_record

def test_ops_from_the_codex_stream(goal_run):
    ops = goal_run.ops["codex-1"]
    assert {o["turn"] for o in ops} == {1, 2}
    pytest_run = [o for o in ops if o["kind"] == "command" and "pytest" in o["command"]]
    assert pytest_run[0]["exit_code"] == 1 and "1 failed" in pytest_run[0]["output"]
    assert [o["paths"] for o in ops if o["kind"] == "file_change"] == [["/workspace/pywc.py"]]
    assert any(o["kind"] == "message" and "still fails" in o["text"] for o in ops)
    cmds = sn.commands(goal_run, "codex-3")
    assert [c["exit_code"] for c in cmds if c["command"] == "cat compile.sh"] == [1]
    assert all(c["seat"] == "codex-3" for c in cmds)

def test_claude_code_stream():
    lines = [json.dumps(x) for x in [
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "running tests"},
                                                      {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "pytest -q"}},
                                                      {"type": "tool_use", "id": "t2", "name": "Edit", "input": {"file_path": "a.py"}}]}},
        {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "is_error": True}]}},
        "not json"]]
    ops = sn.parse_turn(lines, "claude-code", 3)
    assert [o["kind"] for o in ops] == ["message", "command", "file_change"]
    assert ops[1]["exit_code"] == 1 and ops[1]["turn"] == 3 and "id" not in ops[1]
    assert ops[2]["paths"] == ["a.py"]

def test_view_at(goal_run):
    v = sn.view_at(goal_run, 7)
    assert [p["seq"] for p in v.posts] == list(range(1, 8)) and v.room["latest_sequence"] == 7
    assert {(w["seat"], w["turn"]) for w in v.wakes} == {("codex-1", 1), ("codex-2", 1)}   # codex-3 turn 1 ends after #7
    assert set(o["turn"] for o in v.ops["codex-1"]) == {1} and v.ops["codex-3"] == []
    assert v.checks == [] and len(goal_run.posts) == 12                                    # the original is unchanged

def test_share_file():
    t = sn.load("tests/fixtures/share.json")
    assert t.source["kind"] == "share-file" and not t.has_ops and not t.has_record
    assert [p["who"] for p in t.posts] == ["planner", "coder", "planner", "coder"]
    assert t.posts[2]["reply_to"] == 2 and all(p["role"] is None for p in t.posts)

def test_table_export_and_bare_room_ndjson(tmp_path):
    rows = [{"kind": "room", "id": "rom_x", "name": "r", "created_at": "2026-09-20T10:00:00Z"},
            {"kind": "member", "instance_id": "i_A", "principal_id": "p_1", "runtime_kind": "codex", "joined_at": "2026-09-20T10:00:00Z", "display_name": "A"},
            {"kind": "message", "sequence": 2, "sender_instance_id": "i_A", "content": "second", "created_at": "2026-09-20T10:02:00Z"},
            {"kind": "message", "sequence": 1, "sender_instance_id": "i_A", "content": "first", "created_at": "2026-09-20T10:01:00Z"},
            {"kind": "artifact", "id": "art_1", "uploaded_by_instance_id": "i_A", "created_at": "2026-09-20T10:03:00Z", "filename": "a.txt", "sha256": "00"}]
    p = tmp_path / "export.ndjson"; p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    t = sn.load(str(p))
    assert t.source["kind"] == "export" and t.has_record and [x["seq"] for x in t.posts] == [1, 2]
    assert t.seats[0]["principal"] == "p_1" and t.artifacts[0]["by"] == "i_A"
    bare = tmp_path / "room.ndjson"
    bare.write_text("".join(json.dumps(r) + "\n" for r in [
        {"sequence": 1, "content": "hi", "sender": {"member_id": "i_a", "name": "a"}, "created_at": "2026-09-20T10:00:00Z"},
        {"sequence": 2, "content": "fail", "sender": {"member_id": "i_r", "name": "runner"}, "created_at": "2026-09-20T10:01:00Z"}]))
    b = sn.load(str(bare))
    assert b.source["kind"] == "room-ndjson" and [s["handle"] for s in b.seats] == ["a"] and b.posts[1]["role"] == "runner"

def test_text_tools():
    assert sn.cites("re #12 and #3, not &#39; and again #12") == [12, 3]
    assert sn.mentions("@codex-1 and @codex-2. mail a@b.com") == ["codex-1", "codex-2"]
    r = sn.redact("see https://x.ai/j/shr_ABCDEFGHIJKL and shr_ABCDEFGHIJKLMN from me@x.org", 200)
    assert "shr_" not in r and "<url>" in r and "<token>" in r and "<email>" in r

def test_summary(goal_run):
    s = sn.summary(goal_run)
    assert s["posts"] == 12 and s["agent_posts"] == 11 and s["ended_by"] == "after 45m"
    assert s["checks"] == 1 and s["checks_passed"] == 0 and s["ops"]["codex-2"] > 0

def test_real_row_shape(goal_run):
    t = goal_run
    assert t.posts[10]["reply_to"] == 8                      # reply_to_message_id, mapped to a sequence
    assert [s["principal"] for s in t.seats] == ["p_fx1", "p_fx2", "p_fx3"]
    assert t.posts[4]["id"] == "msg_fixture0005"

def test_posts_are_linked_to_the_commands_that_made_them(goal_run):
    links = sn.post_ops(goal_run)
    assert sorted(links) == list(range(2, 13))               # every agent post; not the goal
    assert links[5] == ("codex-1", 1, 3)
    before = sn.ops_before(goal_run, 5)
    assert [o["kind"] for o in before] == ["file_change", "command", "command"]
    assert before[-1]["command"] == "python3 -m pytest -q" and before[-1]["exit_code"] == 1
    assert sn.ops_before(goal_run, 1) is None                # the goal was not posted by a seat's command
    assert not any("posted_id" in o for xs in goal_run.ops.values() for o in xs)

def test_board_commands():
    assert sn.is_board_command("/bin/zsh -lc './sn say \"hi\"'") and sn.is_board_command("sharednet read --last 30")
    assert not sn.is_board_command("python3 -m pytest -q") and not sn.is_board_command("cat snippets.txt")

def test_sender_kinds(tmp_path):
    rows = [{"id": "m1", "sequence": 1, "content": "goal", "sender": {"member_id": "i_o", "kind": "instance", "name": None}},
            {"id": "m2", "sequence": 2, "content": "check failed", "sender": {"member_id": "i_r", "kind": "runner", "name": "goal"}},
            {"id": "m3", "sequence": 3, "content": "owner here", "sender": {"member_id": "i_h", "kind": "human", "name": "Xisen"}},
            {"id": "m4", "sequence": 4, "content": "ok", "sender": {"member_id": "i_a", "kind": "guest", "name": "a"}, "reply_to_message_id": "m3"}]
    p = tmp_path / "room.ndjson"; p.write_text("".join(json.dumps(r) + "\n" for r in rows))
    t = sn.load(str(p))
    assert [q["role"] for q in t.posts] == ["agent", "runner", "other", "agent"] and t.posts[3]["reply_to"] == 3
