"""Behaviour of example_kickstart: which posts it points at, which signal, and why. Replace these expectations with yours."""
from pathlib import Path
from commsfail.annotators import registry
from commsfail.sources import sharednet

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

def _found(out):
    return [(f["seq"], f["signal"], f["mode"], f["group"]) for f in out["findings"]]

def test_example_kickstart_on_the_synthetic_room(synthetic_trace):
    out = registry()["example_kickstart"]().annotate(synthetic_trace)
    assert _found(out) == [
        (2, "open_question", "B1", "disagreement"),     # B asks for the tests to be run; nobody answers or cites it
        (11, "open_question", "B1", "disagreement"),    # "maybe someone could take `cli.ts`?" is left hanging
    ]

def test_example_kickstart_on_the_goal_run_sample():
    out = registry()["example_kickstart"]().annotate(sharednet.load(str(FIXTURES / "goal_run")))
    assert _found(out) == [
        (6, "open_question", "B1", "disagreement"),     # codex-2 asks codex-1 about an empty file; codex-1 never answers
        (10, "bare_claim", "D1", "ungrounded"),         # codex-1 says DONE and names nothing a reader could check
    ]
    assert out["counts"]["by_group"] == {"disagreement": 1, "ungrounded": 1}

def test_example_kickstart_on_the_share_sample():
    out = registry()["example_kickstart"]().annotate(sharednet.load(str(FIXTURES / "share.json")))
    assert _found(out) == []                            # #2's question is answered by #3, which cites it; #4 names `cli.py`
