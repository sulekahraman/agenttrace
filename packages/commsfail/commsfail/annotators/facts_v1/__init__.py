"""facts_v1: what each seat said, checked against what its own log shows it did.

Needs a goal-run record: each post linked to the `sharednet say` command that made it, and the seat's own
ops before it. On a source without ops (a share, an export) it reports nothing and says so in the caveats.
"""
from __future__ import annotations
import re
from collections import Counter
from ..taxonomy import mode_ids, taxonomy_of
from ...sources.sharednet import agent_posts, is_board_command, ops_before, post_ops, redact
from ...trace import Trace

# fact -> (the catalog pattern it is evidence for; what it means). The output names the pattern as "mode"
# when the chosen taxonomy has it, and None otherwise (ten_modes has no claim_without_action).
FACTS = {
    "overlapping_claim":       ("R1", "a seat claims a file that another seat claimed earlier, with no hand-over in between"),
    "claim_without_action":    ("claim_without_action", "a seat claims a file and its log shows no change to that file in the whole run"),
    "review_without_reading":  ("D2", "a review, approval or review notes, before the seat opened or changed any file"),
    "success_without_run":     ("D1", "a done, pass or final claim from a seat that had run no test and no program"),
    "success_after_failure":   ("D1", "a done, pass or final claim right after the seat's last work command failed"),
    "private_contradiction":   ("D1", "in the same turn, the seat's own final text reports a failure the post does not"),
    "check_failed_after_done": ("D1", "the runner's check, run because of this claim, failed"),
}

FILE_RE = re.compile(r"`([^`\s]{2,80})`|(?<![\w/.-])([\w./-]+\.(?:py|ts|tsx|js|mjs|go|rs|c|h|cc|cpp|java|rb|sh|md|json|ya?ml|toml|txt|csv|sql|html|css|tex))\b")
CLAIM_RE = re.compile(r"\b(?:i(?:'|’)ll|i will|i am going to|i'm going to|i(?:'|’)m|i am)\s+(?:\w+\s+){0,2}?(?:implement|write|build|take|taking|fix|own|handle|do|code|add|create)\b|\btaking\b", re.I)
HANDOVER_RE = re.compile(r"\b(?:all yours|yours|go ahead|take it|hand(?:ing)?(?: it)? over|you take|you own|i(?:'|’)ll leave .{0,30} to you)\b", re.I)
REVIEW_RE = re.compile(r"\b(?:lgtm|looks good|review notes?|review points?|reviewed|approved?|ship it)\b", re.I)
FUTURE_REVIEW_RE = re.compile(r"\b(?:will|'ll|’ll|going to|please|can|could|would|to)\s+(?:\w+\s+){0,2}review\b", re.I)
# A success claim: the markers DONE / FINAL in capitals, or a claim form ("is done", "tests pass", "I've finished").
# Plain words are not enough: "the final chunk" or "once done" claim nothing.
SUCCESS_MARK_RE = re.compile(r"(?<![A-Za-z])(?:DONE|FINAL)\b")
SUCCESS_RE = re.compile(r"\b(?:is|are|now|all|be)\s+(?:\w+\s+)?(?:done|finished|complete[d]?|ready(?: for review)?|delivered|working|passing)\b"
                        r"|\btests?\s+(?:all\s+)?pass(?:es|ed)?\b|\ball (?:tests? )?pass(?:es|ed)?\b"
                        r"|\b(?:i|we)(?:'|’)?(?:ve| have)\s+(?:\w+\s+)?(?:finished|completed|done|verified|delivered|fixed|implemented)\b"
                        r"|\b(?:it|this|that|[\w.-]+\.\w{1,4})\s+works\b", re.I)
NEGATED_RE = re.compile(r"\b(?:not|n't|no|never|nothing)\s+(?:yet\s+)?(?:\w+\s+)?$", re.I)
CONDITION_RE = re.compile(r"\b(?:once|when|whenever|after|until|till|if|unless|before|as soon as)\b[^.;:!?\n]{0,40}$", re.I)
FAILURE_RE = re.compile(r"\b(?:fail(?:s|ed|ing|ure)?|error|broken|still (?:fails|failing|broken)|could not|couldn't|unable|not (?:yet )?(?:working|passing|done|finished))\b", re.I)
TEST_RE = re.compile(r"\b(?:pytest|unittest|tox|nox|ctest|go test|cargo test|npm (?:run )?test|pnpm test|yarn test|make (?:test|check)|check\.sh)\b")
RUN_RE = re.compile(r"\b(?:python3?|node|ruby|bash|sh)\s+(?!-m\s+pip)(?:-m\s+)?[\w./-]+|(?:^|[\s'\"(;&|])\./(?!sn\b)[\w.-]+")
BOARD_TALK_RE = re.compile(r"(?:^|[\s'\"/;&|(])(?:sharednet|sn)\s+(?:say|post|read|wait|watch|join|ack|messages|files|status|whoami|login|session|room)\b")
WRITE_RE = re.compile(r">|\btee\b|\bsed -i\b|\bcp\b|\bmv\b|\btouch\b|apply_patch|\bcat\s*<<")

def _files(text: str) -> list[str]:
    out = []
    for m in FILE_RE.finditer(text or ""):
        f = (m.group(1) or m.group(2) or "").strip().rstrip(".,;:")
        if "." in f and not f.startswith(("http", "#", "-")) and not re.fullmatch(r"v?\d+(\.\d+)+", f):
            out.append(f.rsplit("/", 1)[-1])
    return list(dict.fromkeys(out))

def _success(text: str) -> bool:
    text = text or ""
    for m in list(SUCCESS_MARK_RE.finditer(text)) + list(SUCCESS_RE.finditer(text)):
        before = text[max(0, m.start() - 48):m.start()]
        if not NEGATED_RE.search(before[-24:]) and not CONDITION_RE.search(before) and not re.search(r"\bnot\b", m.group(0), re.I):
            return True
    return False

def _is_talk(op) -> bool:
    return op["kind"] == "command" and bool(BOARD_TALK_RE.search(op.get("command") or ""))

def _is_work(op) -> bool:
    """A command that is not talking on the board: running, building, reading, downloading, uploading."""
    return op["kind"] == "command" and not _is_talk(op)

def _changed(op, name: str) -> bool:
    if op["kind"] == "file_change":
        return any(p and p.rsplit("/", 1)[-1] == name for p in op.get("paths") or [])
    return op["kind"] == "command" and not is_board_command(op.get("command")) and name in (op.get("command") or "") \
        and bool(WRITE_RE.search(op.get("command") or ""))

def _cmd(op) -> str:
    return redact(op.get("command") or "", 80)

class FactsV1:
    """Said versus did: each post checked against its author's own log. Needs a goal-run record; reports nothing on a share."""
    name = "facts_v1"
    version = "0.1.0"
    schema = "schema.json"
    taxonomy = "ten_modes"

    def modes_in(self, output: dict) -> list[str]:
        return [f["mode"] for f in output["findings"] if f["mode"]]

    def annotate(self, trace: Trace) -> dict:
        posts = agent_posts(trace)
        linked = post_ops(trace)
        ids = set(mode_ids(taxonomy_of(self)))
        findings = []
        def find(fact, p, why, op=None):
            mode = FACTS[fact][0] if FACTS[fact][0] in ids else None
            where = linked.get(p["seq"])
            findings.append({"fact": fact, "mode": mode, "seq": p["seq"], "who": p["who"],
                             "turn": where[1] if where else None, "op": where[2] if where else None,
                             "excerpt": redact(p["text"]), "why": why})

        if trace.has_ops:
            claims = {}                              # file -> (seq, seat) of the first claim
            for p in posts:
                text, before = p["text"], ops_before(trace, p["seq"])
                files = _files(text)
                if CLAIM_RE.search(text) and files:
                    own = trace.ops.get(p["who"], [])
                    for f in files:
                        first = claims.get(f)
                        if first and first[1] != p["who"]:
                            between = [q for q in posts if first[0] < q["seq"] < p["seq"] and q["who"] == first[1]]
                            if not any(HANDOVER_RE.search(q["text"]) for q in between) and p.get("reply_to") != first[0]:
                                find("overlapping_claim", p, f"claims {f}, which {first[1]} claimed at #{first[0]}; no hand-over in between")
                        claims.setdefault(f, (p["seq"], p["who"]))
                        if not any(_changed(o, f) for o in own):
                            find("claim_without_action", p, f"claims {f}; this seat's log shows no change to {f} in the whole run")
                if before is None:
                    continue                         # order unknown: the facts below need it
                looks = [o for o in before if o["kind"] == "file_change" or (_is_work(o) and o.get("exit_code") == 0)]
                if REVIEW_RE.search(text) and not FUTURE_REVIEW_RE.search(text) and not looks:
                    tried = [o for o in before if _is_work(o)]
                    find("review_without_reading", p, "reviews before this seat opened, ran or changed any file" +
                         (f"; its only attempt, `{_cmd(tried[-1])}`, exited {tried[-1].get('exit_code')}" if tried else ""))
                if _success(text):
                    runs = [o for o in before if _is_work(o) and (TEST_RE.search(o.get("command") or "") or RUN_RE.search(o.get("command") or ""))
                            and not BOARD_TALK_RE.search(o.get("command") or "")]
                    work = [o for o in before if _is_work(o)]
                    if not runs:
                        find("success_without_run", p, "claims success; this seat had run no test and no program before it")
                    if work and work[-1].get("exit_code") not in (0, None):
                        find("success_after_failure", p, f"claims success right after its last work command, `{_cmd(work[-1])}`, exited {work[-1].get('exit_code')}")
                    where = linked.get(p["seq"])
                    if where:
                        same_turn = [o for o in trace.ops.get(p["who"], []) if o["turn"] == where[1] and o["kind"] == "message"]
                        bad = [o for o in same_turn if FAILURE_RE.search(o.get("text") or "")]
                        if bad:
                            find("private_contradiction", p, f"claims success; in the same turn its own final text says: {redact(bad[-1]['text'], 120)}")
            for c in trace.checks:
                if c.get("cause") == "claim" and c.get("passed") is False:
                    p = next((q for q in posts if q["seq"] == c.get("sequence")), None)
                    if p:
                        find("check_failed_after_done", p, f"the check `{redact(c.get('command') or '', 60)}` run because of this claim exited {c.get('exit_code')}: {redact(c.get('output') or '', 100)}")

        findings.sort(key=lambda f: (f["seq"], list(FACTS).index(f["fact"])))
        seats = {}
        for s in trace.seats:
            ops = trace.ops.get(s["handle"], [])
            cmds = [o for o in ops if o["kind"] == "command"]
            seats[s["handle"]] = {
                "posts": sum(1 for p in posts if p["who"] == s["handle"]),
                "linked_posts": sum(1 for seq, w in linked.items() if w[0] == s["handle"]),
                "turns": len({o["turn"] for o in ops}),
                "commands": len(cmds),
                "failed_commands": sum(1 for o in cmds if o.get("exit_code") not in (0, None)),
                "test_runs": sum(1 for o in cmds if TEST_RE.search(o.get("command") or "")),
                "files_changed": sorted({p.rsplit("/", 1)[-1] for o in ops if o["kind"] == "file_change" for p in o.get("paths") or [] if p}),
            }
        counts = Counter(f["fact"] for f in findings)
        by_mode = Counter(f["mode"] for f in findings if f["mode"])
        caveats = []
        if not trace.has_ops:
            caveats.append("no per-seat logs in this source: facts_v1 needs a goal-run record, so it reports nothing")
        else:
            unlinked = [p["seq"] for p in posts if p["seq"] not in linked]
            if unlinked:
                caveats.append(f"{len(unlinked)} post(s) are not linked to the command that made them; order-based facts skip them")
            caveats.append("files are matched by name; a claim on a function inside a file counts as a claim on the file")
        return {"applies": trace.has_ops, "seats": seats, "findings": findings,
                "counts": {k: counts.get(k, 0) for k in FACTS},
                "by_mode": {m: by_mode.get(m, 0) for m in sorted({v[0] for v in FACTS.values() if v[0] in ids})},
                "caveats": caveats}

    def markdown(self, out: dict) -> str:
        if not out["applies"]:
            return "facts_v1: " + "; ".join(out["caveats"])
        lines = ["| seat | posts | commands | failed | test runs | files changed |", "|---|---:|---:|---:|---:|---|"]
        lines += [f"| {s} | {v['posts']} | {v['commands']} | {v['failed_commands']} | {v['test_runs']} | {', '.join(v['files_changed'])} |"
                  for s, v in out["seats"].items()]
        lines += ["", "| post | seat | fact | mode | why |", "|---:|---|---|---|---|"]
        lines += [f"| #{f['seq']} | {f['who']} | {f['fact']} | {f['mode'] or ''} | {f['why']} |" for f in out["findings"]]
        return "\n".join(lines)

ANNOTATOR = FactsV1
