"""example_kickstart: open questions and bare claims, as a starting point. Replace annotate() with your method.

``commsfail new <name>`` copies this folder. Keep three rules: the same trace gives the same output,
annotate() uses no network, and every excerpt of post text goes through redact().

The shape to keep: your method finds *signals*; each signal is evidence of one *pattern* from the catalog in
taxonomy-choices/patterns.json; the *taxonomy* you name puts each pattern in a class. Change the taxonomy by
changing one line, and the same findings are read in other classes.
"""
from __future__ import annotations
import re
from commsfail.annotators.taxonomy import group_of, taxonomy_of
from commsfail.sources.sharednet import agent_posts, cites, redact
from commsfail.trace import Trace

# signal -> (the catalog pattern it is evidence for, the sentence a reader would write in the margin)
SIGNALS = {
    "open_question": ("B1", "asks a question that no later post answers or cites"),
    "bare_claim":    ("D1", "says it is done or passes, and names no file, item or post a reader could check"),
}
DONE_RE = re.compile(r"\b(?:done|finished|complete[d]?|pass(?:es|ed)?|ready)\b", re.I)
# something a reader could check: a backticked item, a file name, or a post number
CHECKABLE_RE = re.compile(r"`[^`]+`|\b[\w./-]+\.\w{1,5}\b|#\d+")

class ExampleKickstart:
    """Open questions and bare claims, read in the state_gap taxonomy. Replace this line with yours."""
    name = "example_kickstart"
    version = "0.1.0"
    schema = "schema.json"
    taxonomy = "state_gap"

    def modes_in(self, output: dict) -> list[str]:
        return [f["mode"] for f in output["findings"]]

    def annotate(self, trace: Trace) -> dict:
        tax = taxonomy_of(self)
        groups = group_of(tax)
        posts = agent_posts(trace)
        answered = set()
        for p in posts:
            if p.get("reply_to"):
                answered.add(p["reply_to"])
            answered.update(cites(p["text"]))
        found = []
        for p in posts:
            text = p["text"].rstrip()
            if text.endswith("?") and p["seq"] not in answered:
                found.append(("open_question", p))
            if DONE_RE.search(text) and not CHECKABLE_RE.search(text):
                found.append(("bare_claim", p))
        rows = [{"seq": p["seq"], "who": p["who"], "signal": signal, "mode": SIGNALS[signal][0],
                 "group": groups[SIGNALS[signal][0]], "excerpt": redact(p["text"]), "why": SIGNALS[signal][1]}
                for signal, p in found if SIGNALS[signal][0] in groups]
        by_group = {}
        for r in rows:
            by_group[r["group"]] = by_group.get(r["group"], 0) + 1
        return {"taxonomy": f"{tax['id']}@{tax['version']}", "findings": rows,
                "counts": {"posts": len(posts), "findings": len(rows), "by_group": by_group}}

    def markdown(self, output: dict) -> str:
        c = output["counts"]
        lines = [f"{c['findings']} finding(s) in {c['posts']} posts, in {output['taxonomy']}: "
                 + (", ".join(f"{g} {n}" for g, n in sorted(c["by_group"].items())) or "none"), ""]
        lines += [f"- #{f['seq']} {f['who']} {f['signal']} → {f['mode']} ({f['group']}): {f['excerpt']}" for f in output["findings"]]
        return "\n".join(lines)

ANNOTATOR = ExampleKickstart
