"""Behaviour of regex_v1: every mode fires where it should on the synthetic Room, and the goal-run sample reads right."""
from commsfail.annotators.regex_v1 import RegexV1

def _mode(out, mid): return next(m for m in out["modes"] if m["id"] == mid)

def test_every_mode_fires_once(synthetic_trace):
    out = RegexV1().annotate(synthetic_trace)
    present = {m["id"] for m in out["modes"] if m["present"]}
    assert present == {"R1", "R2", "B1", "B2", "D1", "D2", "D3", "D4", "REP", "HB"}

def test_r2_is_late_joiner_and_r1_is_self_contradiction(synthetic_trace):
    out = RegexV1().annotate(synthetic_trace)
    r2 = _mode(out, "R2"); r1 = _mode(out, "R1")
    assert any(e["who"] == "C" and "parser.py" in e["why"] for e in r2["evidence"])
    assert any(e["who"] == "A" and "itself" in e["why"] for e in r1["evidence"])
    assert out["metrics"]["self_contradicting_re_claims"] == 1

def test_d1_is_unverifiable_on_a_share(synthetic_trace):
    out = RegexV1().annotate(synthetic_trace)
    assert _mode(out, "D1")["severity"] == "unknown"
    assert out["metrics"]["action_claims_unverifiable"] == out["metrics"]["action_claims"] == 2

def test_heartbeat_and_closure(synthetic_trace):
    out = RegexV1().annotate(synthetic_trace)
    assert out["metrics"]["heartbeat_posts"] == 2
    assert out["metrics"]["last_post_kind"] == "pause"
    assert _mode(out, "D3")["present"]

def test_items_trajectory(synthetic_trace):
    out = RegexV1().annotate(synthetic_trace)
    parser = out["items"]["parser.py"]
    assert [c["who"] for c in parser["claims"]] == ["A", "C", "A"]
    assert parser["done"][0]["who"] == "A"
    assert parser["status_at_end"] == "done"

def test_cited_ask_counts_as_answered():
    from commsfail.trace import Trace
    posts = [{"seq": 1, "who": "A", "text": "Can you review `x.py`?", "created_at": "2026-09-20T10:00:00Z", "reply_to": None, "type": "message"},
             {"seq": 2, "who": "B", "text": "On #1: yes, reviewing `x.py` now.", "created_at": "2026-09-20T10:05:00Z", "reply_to": None, "type": "message"},
             {"seq": 3, "who": "A", "text": "thanks", "created_at": "2026-09-20T10:06:00Z", "reply_to": None, "type": "message"},
             {"seq": 4, "who": "B", "text": "done", "created_at": "2026-09-20T10:07:00Z", "reply_to": None, "type": "message"},
             {"seq": 5, "who": "A", "text": "ok", "created_at": "2026-09-20T10:08:00Z", "reply_to": None, "type": "message"}]
    t = Trace(room={"name": "t"}, seats=[{"handle": "A"}, {"handle": "B"}], posts=posts, source={"kind": "share-file"})
    out = RegexV1().annotate(t)
    assert out["metrics"]["asks_unanswered"] == 0

def test_goal_run_skips_the_goal_and_reads_the_record_kinds(goal_run):
    out = RegexV1().annotate(goal_run)
    assert out["metrics"]["posts"] == 11                       # the goal post is not communication between seats
    present = {m["id"] for m in out["modes"] if m["present"]}
    assert {"HB", "D2", "D3", "B1"} <= present
    assert any(e["seq"] == 7 for e in _mode(out, "D2")["evidence"])      # LGTM on compile.sh, never delivered
    assert _mode(out, "D1")["severity"] == "unknown"           # no artifact rows; regex_v1 does not read the ops
    assert out["metrics"]["last_post_kind"] == "pause"
    assert not any("per-seat execution trace" in c for c in out["caveats"])
