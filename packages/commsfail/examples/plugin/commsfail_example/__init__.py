"""A minimal commsfail plugin: one annotator and one source, for a transcript format commsfail does not know.

Install it next to commsfail. Both appear in the CLI through the entry points in pyproject.toml.
Copy this directory to start a plugin of your own.
"""
from __future__ import annotations
import json
from pathlib import Path
from commsfail import Trace
from commsfail.sources.sharednet import redact

class ExampleV1:
    """Says whether the board ends on an open question. A placeholder for your method, not a method."""
    name = "example_v1"
    version = "0.1.0"
    schema = "schema.json"                  # next to this file; shipped as package data

    def annotate(self, trace: Trace) -> dict:
        last = trace.posts[-1] if trace.posts else None
        ends = bool(last and last["text"].rstrip().endswith("?"))
        return {"ends_on_question": ends,
                "last": {"seq": last["seq"], "who": last["who"], "excerpt": redact(last["text"])} if last else None}

def load_chat_jsonl(path: str) -> Trace:
    """One JSON object per line: {"turn": 3, "speaker": "planner", "text": "...", "t": "2026-...", "model": "..."}."""
    p = Path(path)
    posts, seats = [], {}
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        row = json.loads(line)
        who = row.get("speaker") or "?"
        seats.setdefault(who, {"handle": who, "label": None, "driver": None, "model": row.get("model"),
                               "joined_at": None, "principal": None, "member_id": None})
        posts.append({"seq": int(row.get("turn", i + 1)), "who": who, "text": row.get("text") or "",
                      "created_at": row.get("t"), "reply_to": None, "type": "message", "role": "agent"})
    posts.sort(key=lambda x: x["seq"])
    return Trace(room={"id": None, "name": p.stem, "created_at": posts[0]["created_at"] if posts else None,
                       "latest_sequence": posts[-1]["seq"] if posts else 0, "state": None},
                 seats=list(seats.values()), posts=posts, source={"kind": "chat-jsonl", "path": str(p)})
