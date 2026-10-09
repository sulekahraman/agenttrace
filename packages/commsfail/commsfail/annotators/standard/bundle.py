"""The bundle an annotator agent reads: the timeline, each agent's actions, the task, and the codebook.

    bundle/
      timeline.md      every post and every turn boundary in time order; each agent post says what its author
                       had received when it posted (the turn's hand-off, plus the agent's own reads of the board)
      agents/<seat>.md each agent's turns and actions, with ids <seat>:<turn>:<i> (E3 only)
      task.md          the goal post
      workspace.md     the files at the end of the record, and the report (when the record has the workspace history)
      codebook.md      the classes, the patterns, severity, and the rule that classes a failure
      index.json       the same facts as data, for the checks; agents need not read it

The bundle holds no grade and no condition. The evidence level says what the input can show:
E1 posts only; E2 adds the runner's record of turns and checks; E3 adds each agent's own log.
"""
from __future__ import annotations
import json, re
from pathlib import Path
from ..taxonomy import catalog, load_choice
from ...sources.sharednet import load, parse_ts, post_ops
from ...trace import Trace

SEQ_RE = re.compile(r'"sequence"\s*:\s*(\d+)')
READ_RE = re.compile(r"(?:^|[\s'\"/;&|(])(?:sharednet|sn)\s+read\b")
SEVERITY = [
    (1, "Negligible", "caught and resolved within the next exchange; nothing redone or lost"),
    (2, "Friction", "time, tokens, or posts spent on the repair; the work is unchanged"),
    (3, "Waste", "a substantial piece of work duplicated, discarded, or overwritten, or the product left inconsistent; "
                 "every required part still delivered"),
    (4, "Damage", "a required part of the deliverable missing, wrong, or unreviewed because of it"),
    (5, "Breakdown", "the core result not delivered, or delivered invalid or self-contradictory, or the run derailed"),
]
QUESTIONS = [
    ("unsaid", "Did what another agent's work needs reach the board, in time?"),
    ("unreceived", "Had the acting agent received the relevant post when it acted?"),
    ("misread", "Did its reading keep what the posts clearly established, and add nothing they did not?"),
    ("disagreement", "Where the posts left room, did the agents read them the same way?"),
    ("ungrounded", "Is what the readings record as done, delivered, reviewed, or true what the workspace holds?"),
    ("stalled", "Did the work keep moving, and close at the right time?"),
]

def _t(s) -> str:
    return (s or "")[11:23] if s else "?"

def evidence_level(trace: Trace) -> str:
    return "E3" if trace.has_ops else "E2" if trace.wakes else "E1"

def _wake(trace: Trace, seat: str, turn: int | None = None, at: float | None = None) -> dict | None:
    for w in trace.wakes:
        if w.get("seat") != seat:
            continue
        if turn is not None and w.get("turn") == turn:
            return w
        if at is not None and parse_ts(w.get("started_at")) is not None:
            end = parse_ts(w.get("ended_at")) or float("inf")
            if parse_ts(w["started_at"]) <= at <= end + 1:
                return w
    return None

def _read_max(op: dict) -> int | None:
    if op.get("kind") != "command" or not READ_RE.search(op.get("command") or ""):
        return None
    seqs = [int(s) for s in SEQ_RE.findall(op.get("output") or "")]
    return max(seqs) if seqs else None

def _raw_reads(trace: Trace) -> dict[tuple, int]:
    """(seat, turn, i) -> the highest post a board read returned, from the full output in the raw Codex log.

    The parsed ops keep only the tail of each output, which for a read is usually the last post's text without its
    sequence number. This walks the raw turn files in the order parse_turn numbers ops."""
    root, out = Path(trace.source.get("path", "")) / "agents", {}
    if not root.is_dir():
        return out
    for d in root.iterdir():
        for f in sorted(d.glob("turn-*.jsonl")):
            turn, i = int(f.stem.split("-")[1]), 0
            for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(e, dict):
                    continue
                item = e.get("item") if isinstance(e.get("item"), dict) else None
                if e.get("type") == "item.completed" and item and item.get("type") in (
                        "command_execution", "file_change", "web_search", "mcp_tool_call", "agent_message", "error"):
                    if item.get("type") == "command_execution" and READ_RE.search(item.get("command") or ""):
                        seqs = [int(x) for x in SEQ_RE.findall(item.get("aggregated_output") or "")]
                        if seqs:
                            out[(d.name, turn, i)] = max(seqs)
                    i += 1
                elif e.get("type") in ("turn.failed", "error"):
                    i += 1
    return out

def seen_table(trace: Trace) -> dict[int, dict]:
    """For each agent post: the highest post its author had received when it posted, and how we know."""
    links, out, raw = post_ops(trace), {}, _raw_reads(trace)
    for p in trace.posts:
        if p.get("role") not in (None, "agent"):
            continue
        link = links.get(p["seq"])
        w = _wake(trace, p["who"], turn=link[1]) if link else _wake(trace, p["who"], at=parse_ts(p.get("created_at")))
        if w is None:
            out[p["seq"]] = {"seen": None, "turn": None, "basis": "no turn record"}
            continue
        seen = w.get("through") if w.get("through") is not None else 1          # a first turn is handed the goal
        basis = f"turn {w.get('turn')} was handed up to P{seen}"
        if link:
            reads = [(raw.get((p["who"], o["turn"], o["i"]), _read_max(o)), o["i"]) for o in trace.ops.get(p["who"], [])
                     if o["turn"] == link[1] and o["i"] < link[2]]
            reads = [(m, i) for m, i in reads if m is not None]
            if reads and max(m for m, _ in reads) > seen:
                seen = max(m for m, _ in reads)
                basis += f"; its own read in the turn returned up to P{seen}"
        out[p["seq"]] = {"seen": seen, "turn": w.get("turn"), "basis": basis}
    return out

def _codebook() -> str:
    sg, pats = load_choice("state_gap"), {p["id"]: p for p in catalog()["patterns"]}
    out = ["# Codebook", "",
           "A run moves around one cycle. What an agent knows and has done (K) is posted to the board (L). The board "
           "delivers posts into what each other agent has received (L^i): a turn is handed the posts up to its `through`, "
           "and posts that arrive during a turn are not seen unless the agent reads the board again. Each agent reads what "
           "it received into its picture of who does what (G^i), and acts on the shared workspace (X).",
           "", "A failure is a point where two of these states stop agreeing. Class it by asking these questions in "
           "order; the first answered 'no' is its class, and you do not go further:", ""]
    out += [f"{i}. **{c}**: {q}" for i, (c, q) in enumerate(QUESTIONS, 1)]
    out += ["", "If all six hold and the work is still poor, it is not a communication failure: it is the agents' "
            "capability, a collective judgement, the task's data, the harness, or the grader. Record a failure caused by "
            "the harness (for example the runner ending a run on a post that withheld DONE) as an incident with "
            "source \"harness\".", "", "## Severity: what happened to the team's work, read from the trace", ""]
    out += [f"- **{n} {name}**: {d}" for n, name, d in SEVERITY]
    out += ["", "## Classes and patterns", ""]
    for g in sg["groups"]:
        if g["id"] == "overhead":
            continue
        out += [f"### {g['id']} ({g.get('between', '')}; {g.get('condition', '')})", g["definition"]]
        out += [f"- `{m['id']}` {m['name']}: {m['definition']} Example: {m['example']}" for m in sg["modes"] if m["group"] == g["id"]]
        out.append("")
    out += ["### overhead (not a failure: do not record as an incident)", ", ".join(
        f"`{m['id']}` {m['name']}" for m in sg["modes"] if m["group"] == "overhead"), "",
            "### out of scope (not a communication failure)", ", ".join(f"`{o['id']}`" for o in sg["out_of_scope"]), "",
            "If no pattern fits, use `NEW:<short_name>` and say what it is in class_reason."]
    return "\n".join(out) + "\n"

def _workspace(src: Path, dest: Path) -> None:
    """workspace.md: the files in the shared workspace at the end of the record, and the report's text."""
    git = src / "workspace.git"
    if not git.is_dir():
        return
    import subprocess
    run = lambda *a: subprocess.run(["git", "--git-dir", str(git), *a], capture_output=True, text=True).stdout
    files = run("ls-tree", "-r", "--name-only", "HEAD").split()
    keep = [f for f in files if not f.startswith(("data/", "related_work/", ".")) or f.startswith("report/")]
    out = ["# The shared workspace at the end of the record", "",
           "Files the team produced or changed (inputs under data/ and related_work/ are left out):", ""]
    out += [f"- {f}" for f in keep[:300]]
    out += ["", "## Snapshots: what changed after which post", ""]
    for block in run("log", "--reverse", "--format=@@%s %ad", "--date=format:%H:%M:%S", "--name-status").split("@@")[1:]:
        lines = [l for l in block.strip().splitlines() if l.strip()]
        changed = [l.replace("\t", " ") for l in lines[1:] if not l.split("\t")[-1].startswith(("data/", "related_work/"))]
        out.append(f"- {lines[0]}: " + (", ".join(changed[:40]) or "inputs only"))
    for f in [f for f in keep if f.endswith("report.md")][:2]:
        out += ["", f"## {f}", "", run("show", f"HEAD:{f}")[:20000]]
    for f in [f for f in keep if f.startswith("code/") and f.endswith((".py", ".sh", ".R", ".jl"))][:4]:
        out += ["", f"## {f} (first 3000 characters)", "", "```", run("show", f"HEAD:{f}")[:3000], "```"]
    (dest / "workspace.md").write_text("\n".join(out) + "\n", encoding="utf-8")

def build(src: str, dest: str | Path) -> dict:
    """Write the bundle for one run to dest, and return its index."""
    trace = load(src)
    dest = Path(dest); (dest / "agents").mkdir(parents=True, exist_ok=True)
    level, seen = evidence_level(trace), seen_table(trace)
    goal = next((p for p in trace.posts if p.get("role") == "goal"), trace.posts[0] if trace.posts else None)
    ended = trace.episode.get("ended_by") or {}
    head = [f"# Timeline: {Path(str(src)).name}", "",
            f"Evidence level {level}: " + {"E1": "the board's posts only.", "E2": "posts and the runner's record of turns "
            "and checks.", "E3": "posts, the runner's record, and each agent's own log (agents/)."}[level],
            f"Agents: {', '.join(s['handle'] for s in trace.seats if s.get('handle') not in ('owner', 'runner'))}.",
            f"The run ended: {ended.get('trigger', '?')} at {_t(ended.get('at'))}: {ended.get('detail', '')}"]
    until = (trace.episode.get("goal") or {}).get("until") or []
    if until:
        head.append("How the run ends: at the first of " + "; ".join(until) + ".")
        if any(u.startswith("said") for u in until):
            word = next(u.split(" ", 1)[1] for u in until if u.startswith("said"))
            head.append(f"The runner treats any post whose text contains \"{word}\" anywhere as a claim of being done, "
                        "whatever the sentence means; the check then runs, and if it passes the run ends at once and every "
                        "turn still running is cut.")
    for c in trace.checks:
        head.append(f"Check at {_t(c.get('at'))} (cause: {c.get('cause')}, after P{c.get('sequence')}): "
                    f"{'passed' if c.get('passed') else 'failed'}.")
    events = []
    for p in trace.posts:
        ts = parse_ts(p.get("created_at")) or 0
        if p is goal:
            events.append((ts, 0, f"P{p['seq']}  {_t(p.get('created_at'))}  {p['who']} (the goal): see task.md"))
            continue
        s = seen.get(p["seq"])
        note = f"  [had received up to P{s['seen']}: {s['basis']}]" if s and s["seen"] is not None else ""
        events.append((ts, 1, f"P{p['seq']}  {_t(p.get('created_at'))}  {p['who']}{note}\n    "
                              + (p.get("text") or "").replace("\n", "\n    ")))
    for w in trace.wakes:
        frm = f"P{w['from']}-P{w['through']}" if w.get("through") is not None else "the goal"
        events.append((parse_ts(w.get("started_at")) or 0, 0, f"--- {w['seat']} turn {w['turn']} starts "
                       f"{_t(w.get('started_at'))}, handed {frm}"))
        events.append((parse_ts(w.get("ended_at")) or float("inf"), 2, f"--- {w['seat']} turn {w['turn']} ends "
                       f"{_t(w.get('ended_at'))}{' (cut by the end of the run)' if w.get('cut_by_end') else ''}"))
    events.sort(key=lambda e: (e[0], e[1]))
    (dest / "timeline.md").write_text("\n".join(head) + "\n\n" + "\n".join(e[2] for e in events) + "\n", encoding="utf-8")
    (dest / "task.md").write_text((goal or {}).get("text", "") + "\n", encoding="utf-8")
    (dest / "codebook.md").write_text(_codebook(), encoding="utf-8")
    _workspace(Path(str(src)), dest)
    actions, raw = {}, _raw_reads(trace)
    for seat, ops in sorted(trace.ops.items()):
        lines, turn = [f"# {seat}", ""], None
        for o in ops:
            if o["turn"] != turn:
                turn = o["turn"]; w = _wake(trace, seat, turn=turn) or {}
                frm = f"handed up to P{w['through']}" if w.get("through") is not None else "handed the goal"
                lines += ["", f"## Turn {turn}: {_t(w.get('started_at'))} to {_t(w.get('ended_at'))}, {frm}"
                          + (", cut by the end of the run" if w.get("cut_by_end") else "")]
            aid = f"{seat}:{o['turn']}:{o['i']}"
            if o.get("posted"):
                desc = f"posted P{o['posted']}"
            elif raw.get((seat, o["turn"], o["i"])) or _read_max(o):
                desc = f"read the board: up to P{raw.get((seat, o['turn'], o['i'])) or _read_max(o)}"
            elif o["kind"] == "command":
                cmd = o.get("command") or ""
                limit = 1500 if re.search(r'<<|> ?[\w./-]+\.(py|md|sh|json|csv)', cmd) else 400
                desc = f"command [exit {o.get('exit_code')}]: {cmd[:limit]}"
                if o.get("exit_code") not in (0, None):
                    desc += f"\n    output ends: {(o.get('output') or '')[-200:]}"
            elif o["kind"] == "file_change":
                desc = "file change: " + ", ".join(x for x in o.get("paths") or [] if x)
            elif o["kind"] == "message":
                desc = "final text of the turn: " + (o.get("text") or "")[:400]
            else:
                desc = f"{o['kind']}: {o.get('query') or o.get('name') or o.get('text') or ''}"[:240]
            actions[aid] = {"seat": seat, "turn": o["turn"], "kind": o["kind"]}
            lines.append(f"- `{aid}` {desc}".replace("\n", "\n  "))
        (dest / "agents" / f"{seat}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    index = {"run": Path(str(src)).name, "evidence_level": level,
             "posts": {str(p["seq"]): {"who": p["who"], "role": p.get("role"), "at": p.get("created_at"),
                                        "seen": (seen.get(p["seq"]) or {}).get("seen")} for p in trace.posts},
             "actions": actions}
    (dest / "index.json").write_text(json.dumps(index, indent=1), encoding="utf-8")
    return index
