"""Behaviour of facts_v1: each post checked against its author's own log."""
from commsfail.annotators.facts_v1 import FactsV1, _success
from commsfail.trace import Trace

def _pairs(out):
    return [(f["seq"], f["fact"]) for f in out["findings"]]

def test_goal_run_sample(goal_run):
    out = FactsV1().annotate(goal_run)
    assert out["applies"] is True
    assert _pairs(out) == [
        (3, "claim_without_action"),        # codex-2 claims compile.sh and never writes it
        (4, "overlapping_claim"),           # codex-3 claims pywc.py, held by codex-1 since #2
        (4, "claim_without_action"),
        (5, "success_after_failure"),       # "Tests pass" right after pytest exited 1
        (5, "private_contradiction"),       # ... while its own final text says a test still fails
        (7, "review_without_reading"),      # LGTM on compile.sh; its only `cat compile.sh` failed
        (10, "success_after_failure"),
        (10, "check_failed_after_done"),    # the check run because of DONE failed
    ]
    assert out["by_mode"] == {"D1": 4, "D2": 1, "R1": 1}
    assert out["seats"]["codex-1"]["test_runs"] == 1 and out["seats"]["codex-1"]["files_changed"] == ["pywc.py"]
    assert all(f["turn"] is not None for f in out["findings"])

def test_nothing_on_a_share(synthetic_trace):
    out = FactsV1().annotate(synthetic_trace)
    assert out["applies"] is False and out["findings"] == [] and "goal-run record" in out["caveats"][0]

def _trace(posts, ops):
    """posts: [(seq, who, text)]; ops: {seat: [op dicts without turn/i]}; a post is linked by an op with posted=seq."""
    full = {s: [{"turn": 1, "i": i, **o} for i, o in enumerate(xs)] for s, xs in ops.items()}
    return Trace(room={"name": "t"}, seats=[{"handle": s} for s in ops],
                 posts=[{"seq": q, "id": None, "who": w, "text": t, "created_at": None, "reply_to": None, "type": "message", "role": "agent"}
                        for q, w, t in posts],
                 ops=full, source={"kind": "goal-run"})

say = lambda seq: {"kind": "command", "command": "sharednet say ...", "exit_code": 0, "posted": seq}

def test_a_claim_made_after_writing_is_kept():
    t = _trace([(1, "a", "I'll take `x.py`.")], {"a": [{"kind": "file_change", "paths": ["/w/x.py"]}, say(1)]})
    assert _pairs(FactsV1().annotate(t)) == []

def test_a_hand_over_is_not_an_overlap():
    t = _trace([(1, "a", "I'll take `x.py`."), (2, "a", "b, x.py is all yours."), (3, "b", "I'll take `x.py`.")],
               {"a": [say(1), say(2)], "b": [{"kind": "file_change", "paths": ["x.py"]}, say(3)]})
    assert ("3", "overlapping_claim") not in [(str(s), f) for s, f in _pairs(FactsV1().annotate(t))]

def test_a_promise_to_review_is_not_a_review():
    t = _trace([(1, "a", "I will review `x.py` when it is ready.")], {"a": [say(1)]})
    assert _pairs(FactsV1().annotate(t)) == []

def test_a_review_after_reading_is_fine_and_running_counts():
    t = _trace([(1, "a", "LGTM. x.py works.")],
               {"a": [{"kind": "command", "command": "python3 x.py", "exit_code": 0}, say(1)]})
    assert _pairs(FactsV1().annotate(t)) == []

def test_success_words():
    assert _success("DONE beta") and _success("FINAL art_x") and _success("`a.py` is done. Tests pass.")
    for text in ("emit all but final chunk", "not done yet", "review once it is ready", "When tests pass, I merge.", "LGTM"):
        assert not _success(text), text
