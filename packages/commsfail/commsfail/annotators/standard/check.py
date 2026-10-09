"""Deterministic checks on what an annotator, the judge, and the verdict return. Each returns a list of problems,
written so that an agent can fix them; an empty list means the output is kept."""
from __future__ import annotations
import json, re
from ..taxonomy import group_of, load_choice, patterns

CLASSES = ("unsaid", "unreceived", "misread", "disagreement", "ungrounded", "stalled")
FIELDS = ("id", "posts", "anchor", "actions", "class", "pattern", "class_reason", "cause", "consequence", "severity",
          "severity_reason", "repaired", "source", "confidence", "items")
NEEDS_E3 = {"unsaid"}
CAUSES = ("incident", "capability", "collective_judgement", "task_data", "harness", "grader")

def parse(text: str):
    """The JSON object in an agent's last message, with or without a code fence."""
    s = (text or "").strip()
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", s, re.S)
    if m:
        s = m.group(1)
    elif not s.startswith("{"):
        a, b = s.find("{"), s.rfind("}")
        s = s[a:b + 1] if a >= 0 and b > a else s
    return json.loads(s)

def _incident(inc: dict, index: dict, items: set, where: str) -> list[str]:
    errs = [f"{where}: missing field '{k}'" for k in FIELDS if k not in inc]
    if errs:
        return errs
    posts, level = index["posts"], index["evidence_level"]
    if not isinstance(inc["posts"], list) or not inc["posts"] or not all(isinstance(p, int) for p in inc["posts"]):
        return [f"{where}: 'posts' must be a non-empty list of post numbers"]
    errs += [f"{where}: post {p} does not exist" for p in inc["posts"] if str(p) not in posts]
    if inc["anchor"] not in inc["posts"]:
        errs.append(f"{where}: the anchor {inc['anchor']} must be one of its posts {inc['posts']}")
    if not isinstance(inc["actions"], list):
        errs.append(f"{where}: 'actions' must be a list (use [] for none)")
    else:
        if inc["actions"] and level != "E3":
            errs.append(f"{where}: this run has no agent logs, so 'actions' must be []")
        errs += [f"{where}: action {a} does not exist (see agents/*.md for ids)" for a in inc["actions"]
                 if level == "E3" and a not in index["actions"]]
    cls = inc["class"]
    if cls not in CLASSES:
        errs.append(f"{where}: class must be one of {list(CLASSES)}")
    pat = str(inc["pattern"])
    if not pat.startswith("NEW:"):
        g = group_of(load_choice("state_gap")).get(pat)
        if pat not in patterns():
            errs.append(f"{where}: pattern {pat!r} is not in the codebook; use a listed id or NEW:<name>")
        elif g == "overhead":
            errs.append(f"{where}: {pat!r} is overhead, not a failure; do not record it as an incident")
        elif g is None:
            errs.append(f"{where}: {pat!r} is out of scope, not a communication failure")
        elif g != cls:
            errs.append(f"{where}: pattern {pat!r} belongs to class {g!r}, not {cls!r}")
    sev = inc["severity"]
    if not isinstance(sev, int) or not 1 <= sev <= 5:
        errs.append(f"{where}: severity must be an integer from 1 to 5")
    elif not str(inc["severity_reason"]).strip().startswith(f"{sev}"):
        errs.append(f"{where}: severity_reason must begin with the level it names, '{sev}: ...'")
    for k in ("class_reason", "cause", "consequence"):
        if not isinstance(inc[k], str) or len(inc[k].strip()) < 10:
            errs.append(f"{where}: '{k}' must say what happened in a sentence")
    if not isinstance(inc["repaired"], bool):
        errs.append(f"{where}: 'repaired' must be true or false")
    if inc["source"] not in ("agents", "harness"):
        errs.append(f"{where}: source must be 'agents' or 'harness'")
    if inc["confidence"] not in ("low", "medium", "high"):
        errs.append(f"{where}: confidence must be low, medium, or high")
    errs += [f"{where}: item {i!r} is not in 'items'" for i in inc["items"] if i not in items]
    if cls in NEEDS_E3 and level != "E3":
        errs.append(f"{where}: {cls} needs the agents' logs (E3); this run is {level}: report it in 'undecidable'")
    if cls == "unreceived" and inc["source"] == "agents" and level in ("E2", "E3") and str(inc["anchor"]) in posts:
        a = posts[str(inc["anchor"])]
        if a.get("seen") is not None:
            unseen = [p for p in inc["posts"] if p != inc["anchor"] and str(p) in posts and p > a["seen"]
                      and p < inc["anchor"] and posts[str(p)]["who"] != a["who"]]
            later = [p for p in inc["posts"] if p > inc["anchor"] and posts.get(str(p), {}).get("who") != a["who"]]
            if not unseen and not later:
                errs.append(f"{where}: unreceived, but when {a['who']} posted P{inc['anchor']} it had received up to "
                            f"P{a['seen']}, which includes every other post listed {inc['posts']}. Anchor the incident "
                            "at the post made without the unseen one, or choose another class.")
    return errs

def annotation(out, index: dict) -> list[str]:
    """An annotator's record."""
    if not isinstance(out, dict):
        return ["return one JSON object"]
    errs = [f"missing top-level field '{k}'" for k in ("items", "incidents", "undecidable") if k not in out]
    if errs:
        return errs
    items = {i.get("id") for i in out["items"] if isinstance(i, dict)}
    if not all(isinstance(i, dict) and i.get("id") and i.get("name") for i in out["items"]):
        errs.append("each item needs an 'id' and a 'name'")
    ids = [i.get("id") for i in out["incidents"] if isinstance(i, dict)]
    if len(ids) != len(set(ids)) or len(ids) != len(out["incidents"]):
        errs.append("incident ids must be present and unique")
    for n, inc in enumerate(out["incidents"]):
        errs += _incident(inc, index, items, f"incident {inc.get('id', n) if isinstance(inc, dict) else n}") \
            if isinstance(inc, dict) else [f"incident {n} must be an object"]
    errs += [f"undecidable: {c!r} is not a class" for c in out["undecidable"] if c not in CLASSES]
    if index["evidence_level"] != "E3" and "unsaid" not in out["undecidable"]:
        errs.append("this run has no agent logs: list 'unsaid' in 'undecidable'")
    return errs

def sweep(out, index: dict) -> list[str]:
    """An annotator's sweep: every agent post looked at once, and tied to the incidents that include it."""
    sw = out.get("sweep") if isinstance(out, dict) else None
    if not isinstance(sw, list) or not all(isinstance(e, dict) for e in sw):
        return ["missing top-level field 'sweep': one entry per agent post, {\"post\": n, \"incidents\": [...], \"note\": \"...\"}"]
    agent = sorted(int(s) for s, p in index["posts"].items() if p.get("role") == "agent")
    got = [e.get("post") for e in sw]
    errs = [f"sweep: post {p} is missing; look at every agent post" for p in agent if p not in got]
    errs += [f"sweep: post {p} appears more than once" for p in sorted({p for p in got if got.count(p) > 1})]
    errs += [f"sweep: post {p} does not exist" for p in got if str(p) not in index["posts"]]
    incs = {i.get("id"): i for i in out.get("incidents", []) if isinstance(i, dict)}
    for e in sw:
        if not str(e.get("note", "")).strip():
            errs.append(f"sweep: post {e.get('post')} needs a 'note' saying what you checked")
        for i in e.get("incidents") or []:
            if i not in incs:
                errs.append(f"sweep: post {e.get('post')} names incident {i}, which does not exist")
            elif e.get("post") not in incs[i].get("posts", []):
                errs.append(f"sweep: post {e.get('post')} names {i}, but {i}'s posts do not include it")
    listed = {(e.get("post"), i) for e in sw for i in e.get("incidents") or []}
    for i, inc in incs.items():
        errs += [f"sweep: incident {i} includes post {p}, so the sweep entry for post {p} must name {i}"
                 for p in inc.get("posts", []) if p in agent and (p, i) not in listed]
    return errs

def judged(out, index: dict, a: dict, b: dict) -> list[str]:
    """The judge's record: a valid annotation, and every incident of A and B accounted for exactly once."""
    errs = annotation(out, index)
    if errs or not isinstance(out, dict):
        return errs
    if not isinstance(out.get("rejected"), list):
        return ["missing top-level field 'rejected' (a list, [] if none)"]
    seen = []
    for inc in out["incidents"]:
        if inc.get("decision") not in ("agreed", "merged", "kept", "added", "adjusted"):
            errs.append(f"incident {inc.get('id')}: decision must be agreed, merged, kept, added, or adjusted")
        if not isinstance(inc.get("from"), list) or (inc.get("decision") != "added" and not inc["from"]):
            errs.append(f"incident {inc.get('id')}: 'from' must list the A:/B: incidents it comes from ([] if added)")
        if not str(inc.get("judge_reason", "")).strip():
            errs.append(f"incident {inc.get('id')}: give a 'judge_reason'")
        seen += inc.get("from") or []
    for r in out["rejected"]:
        if not isinstance(r, dict) or not r.get("from") or not str(r.get("reason", "")).strip():
            errs.append("each rejected entry needs 'from' (an A:/B: id) and a 'reason'")
        else:
            seen.append(r["from"])
    want = [f"A:{i['id']}" for i in a["incidents"]] + [f"B:{i['id']}" for i in b["incidents"]]
    missing = [w for w in want if w not in seen]
    unknown = [s for s in seen if s not in want]
    twice = sorted({s for s in seen if seen.count(s) > 1})
    if missing:
        errs.append(f"these annotator incidents are neither kept nor rejected: {missing}")
    if unknown:
        errs.append(f"these 'from' ids do not exist: {unknown}")
    if twice:
        errs.append(f"each annotator incident must be used once; used twice: {twice}")
    return errs

def verdict(out, final: dict, grade: dict) -> list[str]:
    """The verdict after the grade: every item that lost points has a cause."""
    if not isinstance(out, dict):
        return ["return one JSON object"]
    errs = [f"missing field '{k}'" for k in ("items", "explains_score", "summary") if k not in out]
    if errs:
        return errs
    incs = {i["id"] for i in final["incidents"]}
    lost = [it["index"] for it in grade.get("items", []) if it.get("score", 100) < 100]
    got = {it.get("index") for it in out["items"] if isinstance(it, dict)}
    errs += [f"rubric item {i} lost points and has no entry" for i in lost if i not in got]
    for it in out["items"]:
        for c in it.get("causes") or [{}]:
            if c.get("kind") not in CAUSES:
                errs.append(f"item {it.get('index')}: cause kind must be one of {list(CAUSES)}")
            refs = c.get("incidents")
            if c.get("kind") == "incident" and (not isinstance(refs, list) or not refs
                    or not all(isinstance(ref, str) and ref in incs for ref in refs)):
                errs.append(f"item {it.get('index')}: an 'incident' cause must list incident ids from the record")
    if out["explains_score"] not in ("no", "partly", "yes"):
        errs.append("explains_score must be no, partly, or yes")
    return errs
