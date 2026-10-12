"""Everything commsfail knows about SharedNet: read a Room into a Trace, plus small tools over a Trace.

Sources, and what each one shows:

    goal-run record folder   `sharednet goal run --out DIR`. The default input. Posts, seats, checks, wakes,
                             each seat's own harness log (ops) and the episode summary.
                             Files: episode.json, room.ndjson, checks.ndjson, wakes.ndjson,
                             agents/<seat>/turn-NNN.jsonl (agents/<seat>/home/ and workspace.git are not read).
    goal-export folder       `sharednet goal watch` or `goal export rom_…`: room.ndjson and episode.json,
                             sometimes checks.ndjson. No ops.
    room NDJSON file         a room.ndjson on its own, or a table export with one row per database row,
                             tagged by "kind" (room, member, message, artifact). The table export has artifacts.
    share JSON or link       what a share page shows: posts and seats. No ids, no artifacts, no ops.

``load(src)`` picks the reader. The tools below work on any Trace.
"""
from __future__ import annotations
import json, re, urllib.request
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from ..trace import Trace

SHARE_API = "https://www.sharednet.ai/api/sharednet/shared/{token}"
TOKEN_RE = re.compile(r"\b(?:snk|sni|rit|rmt|clp|shr|afk)_[A-Za-z0-9_-]{10,}\b")
CITE_RE = re.compile(r"(?<![\w&])#(\d{1,6})\b")
MENTION_RE = re.compile(r"(?<![\w.@])@([A-Za-z0-9][\w.-]{0,63})")
RUNNER_NAMES = ("runner",)

# ---- small tools ----

def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def parse_ts(s):
    """An ISO timestamp as an aware datetime, or None."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None

def redact(text: str, n: int = 160) -> str:
    """Text that is safe to put in an output: no URLs, emails or SharedNet tokens; one line; at most n chars."""
    s = re.sub(r"https?://\S+", "<url>", text or "")
    s = re.sub(r"[\w.+-]+@[\w-]+\.[\w.]+", "<email>", s)
    s = TOKEN_RE.sub("<token>", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:n] + ("…" if len(s) > n else "")

def cites(text: str) -> list[int]:
    """The post numbers a text cites as #n, in order, without repeats."""
    return list(dict.fromkeys(int(x) for x in CITE_RE.findall(text or "")))

def mentions(text: str) -> list[str]:
    """The handles a text addresses as @name, in order, without repeats."""
    return list(dict.fromkeys(m.rstrip(".") for m in MENTION_RE.findall(text or "")))

def posts_by(trace: Trace, seat: str) -> list[dict]:
    return [p for p in trace.posts if p["who"] == seat]

def agent_posts(trace: Trace) -> list[dict]:
    """Posts by the working seats: not the goal, not the runner. On a share, where roles are unknown, all posts."""
    return [p for p in trace.posts if p.get("role") in (None, "agent")]

def commands(trace: Trace, seat: str | None = None) -> list[dict]:
    """Every command a seat ran (or every seat, when seat is None), each with its seat added."""
    seats = [seat] if seat else sorted(trace.ops)
    return [{"seat": s, **op} for s in seats for op in trace.ops.get(s, []) if op.get("kind") == "command"]

def post_ops(trace: Trace) -> dict[int, tuple[str, int, int]]:
    """For each post made by a seat's own command (`sharednet say`), where it was made: {seq: (seat, turn, i)}."""
    return {o["posted"]: (s, o["turn"], o["i"]) for s, xs in trace.ops.items() for o in xs if isinstance(o.get("posted"), int)}

def ops_before(trace: Trace, seq: int) -> list[dict] | None:
    """What the author of post `seq` had done before writing it, in order: its ops up to the command that posted it.

    None when the post is not linked to a command (a share, an export, or a harness whose posts are not commands).
    """
    where = post_ops(trace).get(seq)
    if where is None:
        return None
    seat, turn, i = where
    return [o for o in trace.ops.get(seat, []) if (o["turn"], o["i"]) < (turn, i)]

def view_at(trace: Trace, seq: int) -> Trace:
    """The board as it was right after post `seq`: what a seat could know at that moment.

    Posts, checks and artifacts up to that point; wakes, and the ops of their turns, that had ended by then.
    Use it for snapshot questions: what should a seat have posted next, given only this?
    """
    posts = [p for p in trace.posts if p["seq"] <= seq]
    t = parse_ts(posts[-1]["created_at"]) if posts else None
    def before(ts):
        x = parse_ts(ts)
        return t is not None and x is not None and x <= t
    wakes = [w for w in trace.wakes if before(w.get("ended_at"))]
    done = {(w.get("seat"), w.get("turn")) for w in wakes}
    ops = {s: [o for o in xs if (s, o.get("turn")) in done] for s, xs in trace.ops.items()}
    return replace(trace, posts=posts, wakes=wakes, ops=ops,
                   checks=[c for c in trace.checks if (c.get("sequence") or 0) <= seq],
                   artifacts=[a for a in trace.artifacts if before(a.get("created_at"))],
                   room={**trace.room, "latest_sequence": seq})

def summary(trace: Trace) -> dict:
    """A few numbers to see what a source holds before annotating it."""
    first = parse_ts(trace.posts[0]["created_at"]) if trace.posts else None
    last = parse_ts(trace.posts[-1]["created_at"]) if trace.posts else None
    return {"source": trace.source.get("kind"), "room": trace.room.get("name"), "posts": len(trace.posts),
            "agent_posts": len(agent_posts(trace)), "seats": [s["handle"] for s in trace.seats],
            "span_hours": round((last - first).total_seconds() / 3600, 2) if first and last else None,
            "ops": {s: len(xs) for s, xs in sorted(trace.ops.items())}, "checks": len(trace.checks),
            "checks_passed": sum(1 for c in trace.checks if c.get("passed")), "wakes": len(trace.wakes),
            "artifacts": len(trace.artifacts), "ended_by": (trace.episode.get("ended_by") or {}).get("trigger")}

# ---- harness logs ----

SAY_RE = re.compile(r"(?:^|[\s'\"/;&|(])(?:sharednet|sn)\s+(?:say|post)\b")
POSTED_RE = re.compile(r'"message"\s*:\s*\{\s*"id"\s*:\s*"(msg_[A-Za-z0-9_-]+)"')

def is_board_command(command: str | None) -> bool:
    """A SharedNet CLI call (say, read, wait, join, files, upload, download, ...), as opposed to work."""
    return bool(re.search(r"(?:^|[\s'\"/;&|(])(?:sharednet|sn)\s+[a-z]", command or ""))

def _posted_id(command, output: str):
    """The id of the message a `sharednet say` command posted, read from its JSON output."""
    if not SAY_RE.search(command or ""):
        return None
    m = POSTED_RE.search(output or "")
    return m.group(1) if m else None

def parse_turn(lines, driver: str | None, turn: int) -> list[dict]:
    """One turn of a seat's raw harness stream (agents/<seat>/turn-NNN.jsonl) as ops.

    Codex: `codex exec --json` events. Claude Code: `--output-format stream-json` events. Unknown lines are skipped.
    """
    ops, results = [], {}
    def add(kind, **kw):
        ops.append({"turn": turn, "i": len(ops), "kind": kind, **{k: v for k, v in kw.items() if v is not None}})
    for line in lines:
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if not isinstance(e, dict):
            continue
        t = e.get("type")
        item = e.get("item") if isinstance(e.get("item"), dict) else None
        if t == "item.completed" and item:                                    # Codex
            k = item.get("type")
            if k == "command_execution":
                out = item.get("aggregated_output") or ""
                add("command", command=item.get("command"), exit_code=item.get("exit_code"), output=out[-500:],
                    posted_id=_posted_id(item.get("command"), out))
            elif k == "file_change":
                add("file_change", paths=[c.get("path") for c in item.get("changes") or [] if isinstance(c, dict)])
            elif k == "web_search":
                add("web_search", query=item.get("query"))
            elif k == "mcp_tool_call":
                add("tool", name=f"{item.get('server')}.{item.get('tool')}")
            elif k == "agent_message":
                add("message", text=item.get("text"))
            elif k == "error":
                add("error", text=item.get("message"))
        elif t in ("turn.failed", "error"):
            add("error", text=str((e.get("error") or {}).get("message") if isinstance(e.get("error"), dict) else e.get("message")))
        elif t == "assistant" and isinstance(e.get("message"), dict):        # Claude Code
            for c in e["message"].get("content") or []:
                if not isinstance(c, dict):
                    continue
                inp = c.get("input") if isinstance(c.get("input"), dict) else {}
                if c.get("type") == "text":
                    add("message", text=c.get("text"))
                elif c.get("type") == "tool_use":
                    name = c.get("name")
                    if name == "Bash":
                        add("command", command=inp.get("command"), exit_code=None, id=c.get("id"))
                    elif name in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
                        add("file_change", paths=[inp.get("file_path") or inp.get("notebook_path")])
                    elif name == "WebSearch":
                        add("web_search", query=inp.get("query"))
                    else:
                        add("tool", name=name)
        elif t == "user" and isinstance(e.get("message"), dict):
            for c in e["message"].get("content") or []:
                if isinstance(c, dict) and c.get("type") == "tool_result":
                    results[c.get("tool_use_id")] = 1 if c.get("is_error") else 0
    for op in ops:                                       # Claude Code: a Bash result's error flag is its exit code
        if op["kind"] == "command" and "id" in op:
            op["exit_code"] = results.get(op.pop("id"))
    return ops

def _link_posts(ops: dict, posts: list) -> None:
    """Turn each say command's posted message id into the post's sequence number (op["posted"])."""
    by_id = {p.get("id"): p["seq"] for p in posts if p.get("id")}
    for xs in ops.values():
        for o in xs:
            mid = o.pop("posted_id", None)
            if mid in by_id:
                o["posted"] = by_id[mid]

# ---- readers ----

def _ndjson(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]

def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

def _post(item: dict, who: str, role, reply_to) -> dict:
    return {"seq": item["sequence"], "id": item.get("id"), "who": who, "text": item.get("content") or "",
            "created_at": item.get("created_at"), "reply_to": reply_to, "type": item.get("type") or "message", "role": role}

def _from_message_rows(rows: list[dict], episode: dict, agents: list[dict]) -> tuple[list, list]:
    """room.ndjson as `goal run` / `goal export` write it: one API message item per line."""
    goal_seq = (episode.get("goal") or {}).get("sequence")
    names = {a.get("member_id"): a.get("name") for a in agents if a.get("member_id")}
    seats = [{"handle": a.get("name"), "label": None, "driver": a.get("driver"), "model": a.get("model"),
              "joined_at": None, "principal": None, "member_id": a.get("member_id")} for a in agents]
    handles = {s["handle"] for s in seats}
    rows = sorted(rows, key=lambda r: r["sequence"])
    seq_of = {r.get("id"): r["sequence"] for r in rows if r.get("id")}
    principal = {}
    posts = []
    for item in rows:
        sender = item.get("sender") if isinstance(item.get("sender"), dict) else {}
        mid = item.get("sender_instance_id") or sender.get("member_id")
        who = names.get(mid) or sender.get("name") or mid or "?"
        kind = sender.get("kind")
        if mid and item.get("sender_principal_id"):
            principal.setdefault(mid, item["sender_principal_id"])
        role = ("goal" if item["sequence"] == goal_seq else
                "runner" if kind == "runner" or who in RUNNER_NAMES else
                "other" if kind == "human" else None)
        if role is None and not agents and who not in handles:        # no agent list: every other sender is a seat
            seats.append({"handle": who, "label": None, "driver": None, "model": None, "joined_at": item.get("created_at"),
                          "principal": None, "member_id": mid})
            handles.add(who)
        reply = item.get("reply_to_sequence")
        if reply is None and item.get("reply_to_message_id"):
            reply = seq_of.get(item["reply_to_message_id"])
        posts.append(_post(item, who, role or ("agent" if who in handles else "other"), reply))
    for s in seats:
        s["principal"] = s["principal"] or principal.get(s["member_id"])
    return seats, posts

def _from_table_rows(rows: list[dict]) -> tuple[dict, list, list, list]:
    """A table export: one row per database row, tagged by "kind"."""
    room, seats, posts, arts = {}, [], [], []
    for row in rows:
        k = row.get("kind")
        if k == "room":
            room = {x: row.get(x) for x in ("id", "name", "created_at", "state")}
        elif k == "member":
            seats.append({"handle": row.get("instance_id"), "label": row.get("display_name"), "driver": row.get("runtime_kind"),
                          "model": None, "joined_at": row.get("joined_at"), "principal": row.get("principal_id"), "member_id": row.get("instance_id")})
        elif k == "message":
            posts.append({"seq": row["sequence"], "id": row.get("id"), "who": row.get("sender_instance_id") or "?", "text": row.get("content") or "",
                          "created_at": row.get("created_at"), "reply_to": None, "type": row.get("type") or "message", "role": None})
        elif k == "artifact":
            arts.append({"id": row.get("id"), "by": row.get("uploaded_by_instance_id"), "created_at": row.get("created_at"),
                         "name": row.get("filename"), "sha256": row.get("sha256")})
    return room, seats, sorted(posts, key=lambda p: p["seq"]), arts

def load_record(path) -> Trace:
    """A record folder: `goal run --out DIR`, `goal watch`, `goal export`, or a bench episode folder."""
    p = Path(path)
    if not (p / "room.ndjson").exists():
        raise ValueError(f"{p} is not a SharedNet record folder: it has no room.ndjson")
    rows = _ndjson(p / "room.ndjson")
    episode = _json(p / "episode.json")
    if any("kind" in r for r in rows):                                  # bench episode folder: table rows + ops.jsonl
        room, seats, posts, arts = _from_table_rows(rows)
        ops = {}
        for row in _ndjson(p / "ops.jsonl"):
            ops.setdefault(row.get("seat"), []).append(row)
        return Trace(room={**room, "name": room.get("name") or p.name, "latest_sequence": posts[-1]["seq"] if posts else 0},
                     seats=seats, posts=posts, artifacts=arts, ops=ops, episode=episode,
                     source={"kind": "episode", "path": str(p), "room_id": room.get("id"), "loaded_at": now()})
    agents = episode.get("agents") or []
    seats, posts = _from_message_rows(rows, episode, agents)
    drivers = {a.get("name"): a.get("driver") for a in agents}
    ops = {}
    for d in sorted(x for x in (p / "agents").glob("*") if x.is_dir()) if (p / "agents").is_dir() else []:
        for f in sorted(d.glob("turn-*.jsonl")):
            m = re.match(r"turn-(\d+)\.jsonl$", f.name)
            ops.setdefault(d.name, []).extend(parse_turn(f.read_text(encoding="utf-8").splitlines(), drivers.get(d.name), int(m.group(1))))
    _link_posts(ops, posts)
    goal = episode.get("goal") or {}
    ended = episode.get("ended_by")
    room = {"id": episode.get("room_id"), "name": episode.get("name") or p.name, "created_at": goal.get("started_at"),
            "latest_sequence": posts[-1]["seq"] if posts else 0, "state": "closed" if ended else episode.get("state")}
    kind = "goal-run" if agents or (p / "agents").is_dir() else "goal-export"
    return Trace(room=room, seats=seats, posts=posts, ops=ops, checks=_ndjson(p / "checks.ndjson"),
                 wakes=_ndjson(p / "wakes.ndjson"), episode=episode,
                 source={"kind": kind, "path": str(p), "room_id": episode.get("room_id"), "loaded_at": now()})

def load_room_ndjson(path) -> Trace:
    """A room.ndjson file on its own, or a table export."""
    p = Path(path)
    rows = _ndjson(p)
    if any("kind" in r for r in rows):
        room, seats, posts, arts = _from_table_rows(rows)
        return Trace(room={**room, "latest_sequence": posts[-1]["seq"] if posts else 0}, seats=seats, posts=posts, artifacts=arts,
                     source={"kind": "export", "path": str(p), "room_id": room.get("id"), "loaded_at": now()})
    seats, posts = _from_message_rows(rows, {}, [])
    return Trace(room={"id": None, "name": p.stem, "created_at": posts[0]["created_at"] if posts else None,
                       "latest_sequence": posts[-1]["seq"] if posts else 0, "state": None},
                 seats=seats, posts=posts, source={"kind": "room-ndjson", "path": str(p), "room_id": None, "loaded_at": now()})

def from_share(d: dict, source: dict) -> Trace:
    seats = [{"handle": m.get("handle"), "label": m.get("label"), "driver": m.get("driver"), "model": None,
              "joined_at": m.get("joined_at"), "principal": m.get("principal"), "member_id": None} for m in d.get("members", [])]
    posts = [{"seq": m["sequence"], "id": None, "who": (m.get("sender") or {}).get("handle") or "?", "text": m.get("content") or "",
              "created_at": m.get("created_at"), "reply_to": m.get("reply_to_sequence"), "type": m.get("type") or "message", "role": None}
             for m in sorted(d.get("messages", []), key=lambda m: m["sequence"])]
    room = d.get("room") or {}
    return Trace(room={"id": None, "name": room.get("name"), "created_at": room.get("created_at"),
                       "latest_sequence": room.get("latest_sequence"), "state": room.get("state")},
                 seats=seats, posts=posts, source=source)

def load_share_file(path) -> Trace:
    p = Path(path)
    return from_share(_json(p), {"kind": "share-file", "path": str(p), "room_id": None, "loaded_at": now()})

def fetch_share(link: str) -> Trace:
    """A share link or a shr_ token. The only reader that uses the network. The token never enters the Trace."""
    token = link.rstrip("/").rsplit("/", 1)[-1]
    with urllib.request.urlopen(SHARE_API.format(token=token), timeout=30) as r:
        return from_share(json.load(r), {"kind": "share", "token": token[:8] + "…", "room_id": None, "loaded_at": now()})

def load(src: str) -> Trace:
    """Any SharedNet source: a record folder, a room.ndjson, a table export, a saved share JSON, a share link."""
    s = str(src)
    if s.startswith(("http://", "https://")) or s.startswith("shr_"):
        return fetch_share(s)
    p = Path(s)
    if p.is_dir():
        return load_record(p)
    if p.suffix == ".json":
        return load_share_file(p)
    return load_room_ndjson(p)

__all__ = ["load", "load_record", "load_room_ndjson", "load_share_file", "fetch_share", "from_share", "parse_turn",
           "parse_ts", "redact", "cites", "mentions", "posts_by", "agent_posts", "commands", "is_board_command",
           "post_ops", "ops_before", "view_at", "summary", "SHARE_API", "TOKEN_RE"]
