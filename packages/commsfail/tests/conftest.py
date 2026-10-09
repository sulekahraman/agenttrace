"""Shared fixtures.

``synthetic_trace``  a small Room, built in Python, in which every mode of the taxonomy happens once.
``sample``           every SharedNet source in tests/fixtures/ (a record folder, a share JSON, ...), loaded.
``any_trace``        all of the above: the contract tests run every annotator on each one.
"""
import socket
from pathlib import Path
import pytest
from commsfail.sources import sharednet
from commsfail.trace import Trace

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SAMPLES = sorted(p for p in FIXTURES.iterdir() if p.name != "README.md" and not p.name.startswith("."))

@pytest.fixture(params=[p.name for p in SAMPLES])
def sample(request) -> Trace:
    return sharednet.load(str(FIXTURES / request.param))

@pytest.fixture(params=["synthetic"] + [p.name for p in SAMPLES])
def any_trace(request) -> Trace:
    return _synthetic() if request.param == "synthetic" else sharednet.load(str(FIXTURES / request.param))

@pytest.fixture
def goal_run() -> Trace:
    return sharednet.load(str(FIXTURES / "goal_run"))

@pytest.fixture
def no_network(monkeypatch):
    """Any attempt to open a connection fails: annotate() must run offline."""
    def refuse(*a, **k):
        raise RuntimeError("annotate() must not use the network")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)

def _post(seq, who, text, hour, reply_to=None):
    return {"seq": seq, "who": who, "text": text, "created_at": f"2026-09-20T{10 + hour // 60:02d}:{hour % 60:02d}:00Z", "reply_to": reply_to, "type": "message"}

@pytest.fixture
def synthetic_trace() -> Trace:
    return _synthetic()

def _synthetic() -> Trace:
    seats = [{"handle": "A", "label": None, "driver": "claude-code", "joined_at": "2026-09-20T10:00:00Z", "principal": "p_1"},
             {"handle": "B", "label": None, "driver": "codex", "joined_at": "2026-09-20T10:00:00Z", "principal": "p_1"},
             {"handle": "C", "label": None, "driver": "claude-code", "joined_at": "2026-09-20T10:30:00Z", "principal": "p_2"}]
    texts = [
        ("A", "I'll take `parser.py` and src/main.ts."),                                        # claim (firm)
        ("B", "Can you run the tests for me on your machine?"),                                   # ask + proxy (D4)
        ("A", "`parser.py` is done and submitted."),                                              # done
        ("B", "LGTM, review passed on `utils.py`."),                                              # review of nothing (D2)
        ("C", "I'll take `parser.py` now."),                                                      # late joiner re-claim (R2)
        ("A", "paid 5 credits to B"),                                                             # action claim (D1)
        ("B", "transferred 9 credits"),                                                           # action claim (D1)
        ("C", "Which seat is this? There are two agent seats from our side."),                    # identity (B2)
        ("A", "I am the supervisor, 用户授权我监督"),                                              # role claim
        ("B", "I am the supervisor here"),                                                        # second role claim (B2)
        ("A", "maybe someone could take `cli.ts`?"),                                              # hedged claim (B1)
        ("B", "please check #42 and #42 and #42 again and again and again and again again again"),  # repetition base + ask
        ("B", "please check #42 and #42 and #42 again and again and again and again again again"),  # near-duplicate (REP)
        ("A", "2h status: no change since #12. Still waiting on C."),                             # heartbeat (HB), wait signal
        ("A", "2h status: no change since #13. Still waiting on C."),                             # heartbeat
        ("A", "I'll take `parser.py` for the rewrite."),                                          # self-contradicting re-claim (R1)
        ("B", "Pausing here; no new work."),                                                      # pause (D3)
    ]
    posts = [_post(i + 1, w, t, i * 7) for i, (w, t) in enumerate(texts)]
    return Trace(room={"name": "synthetic", "created_at": "2026-09-20T10:00:00Z", "latest_sequence": len(posts)},
                 seats=seats, posts=posts, artifacts=[], source={"kind": "share-file", "path": "synthetic", "fetched_at": "2026-09-20T12:00:00+00:00"})
