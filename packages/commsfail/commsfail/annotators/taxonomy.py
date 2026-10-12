"""Taxonomies: one catalog of failure patterns, and several ways to group them. Annotators pick one.

Everything lives in ``taxonomy-choices/`` next to this file, and nothing is defined twice:

    patterns.json        every failure pattern, once: id, name, kind, a definition a person can label with,
                         an example, its MAST counterparts
    <choice>.json        one way to group the patterns: its classes ("groups"), which class each pattern is
                         in ("modes"), and, for a complete choice, which patterns it leaves out and why

An annotator names a choice, ``taxonomy = "state_gap"``, and reports pattern ids. Because every choice
groups the same patterns, one set of labels reads under any choice: ``regroup`` moves counts across.

A choice marked ``complete`` must place every pattern of the catalog, in a class or in ``out_of_scope``.
That is how "is the taxonomy complete?" becomes a test: a new pattern has to be placed in every complete
choice before the tests pass.

The second half of this module helps annotators whose output is ``comms-failure/analysis.v1`` (regex_v1's
format): the output lists every mode of the annotator's taxonomy, present or not.
"""
from __future__ import annotations
import json
from functools import lru_cache
from pathlib import Path
from ..trace import Trace

CHOICES_DIR = Path(__file__).resolve().parent / "taxonomy-choices"
KINDS = ("missing", "wrong", "timing", "excess")

def _read(name: str) -> dict:
    return json.loads((CHOICES_DIR / f"{name}.json").read_text(encoding="utf-8"))

@lru_cache(maxsize=None)
def catalog() -> dict:
    """patterns.json: every pattern, once."""
    return _read("patterns")

def patterns() -> dict[str, dict]:
    return {p["id"]: p for p in catalog()["patterns"]}

def choices() -> list[str]:
    """The names of the taxonomy choices."""
    return sorted(p.stem for p in CHOICES_DIR.glob("*.json") if p.stem != "patterns")

@lru_cache(maxsize=None)
def load_choice(name: str) -> dict:
    """A choice, resolved: its groups, and each of its modes as the catalog defines it, with its group."""
    if name not in choices():
        raise KeyError(f"no taxonomy choice {name!r}; the choices are {choices()}")
    raw, pats = _read(name), patterns()
    modes = []
    for pid, place in raw["modes"].items():
        extra = {"group": place} if isinstance(place, str) else dict(place)
        modes.append({**pats[pid], **extra})
    return {"id": raw["id"], "version": raw["version"], "description": raw["description"],
            "complete": raw.get("complete", False), "groups": raw["groups"], "modes": modes,
            "out_of_scope": [{"id": k, "reason": v} for k, v in raw.get("out_of_scope", {}).items()]}

def taxonomy_of(annotator) -> dict | None:
    """The annotator's taxonomy, resolved, or None. ``taxonomy`` is a choice name, or a resolved dict."""
    cls = annotator if isinstance(annotator, type) else type(annotator)
    t = getattr(cls, "taxonomy", None)
    return t if isinstance(t, dict) or t is None else load_choice(t)

def mode_ids(taxonomy: dict) -> list[str]:
    return [m["id"] for m in taxonomy["modes"]]

def group_of(taxonomy: dict) -> dict[str, str]:
    """pattern id -> the group it is in, under this taxonomy."""
    return {m["id"]: m.get("group") for m in taxonomy["modes"]}

def regroup(counts: dict[str, int], choice: str) -> dict[str, int]:
    """Pattern counts, summed by the classes of another choice. Patterns it leaves out are summed under None."""
    groups, out = group_of(load_choice(choice)), {}
    for pid, n in counts.items():
        g = groups.get(pid)
        out[g] = out.get(g, 0) + n
    return out

def check_catalog(cat: dict) -> list[str]:
    errs, seen = [], set()
    for p in cat.get("patterns", []):
        pid = p.get("id")
        errs += [f"pattern {pid!r} needs a non-empty string '{k}'" for k in ("id", "name", "definition", "example")
                 if not isinstance(p.get(k), str) or not p[k]]
        if p.get("kind") not in KINDS:
            errs.append(f"pattern {pid!r}: 'kind' must be one of {KINDS}")
        if pid in seen:
            errs.append(f"pattern {pid!r} is defined twice")
        seen.add(pid)
    return errs or ([] if seen else ["the catalog has no patterns"])

def check_choice(raw: dict, pats: dict | None = None) -> list[str]:
    """Problems with a raw choice file: unknown patterns or groups, and, for a complete choice, any pattern of
    the catalog it does not place."""
    pats = patterns() if pats is None else pats
    errs = [f"the choice needs a non-empty string '{k}'" for k in ("id", "version", "description")
            if not isinstance(raw.get(k), str) or not raw[k]]
    gids = [g.get("id") for g in raw.get("groups", [])]
    for g in raw.get("groups", []):
        errs += [f"group {g.get('id')!r} needs a non-empty string '{k}'" for k in ("id", "name", "definition")
                 if not isinstance(g.get(k), str) or not g[k]]
    if len(set(gids)) != len(gids):
        errs.append("group ids must be unique")
    modes, out = raw.get("modes", {}), raw.get("out_of_scope", {})
    if not modes:
        errs.append("'modes' must place at least one pattern")
    for pid, place in modes.items():
        if pid not in pats:
            errs.append(f"{pid!r} is not a pattern of the catalog; define it in patterns.json first")
        g = place if isinstance(place, str) else (place or {}).get("group")
        if g not in gids:
            errs.append(f"{pid!r} is placed in group {g!r}, which 'groups' does not define")
    errs += [f"{pid!r} is out of scope but not a pattern of the catalog" for pid in out if pid not in pats]
    errs += [f"{pid!r} is both placed and out of scope" for pid in set(modes) & set(out)]
    if raw.get("complete"):
        missing = sorted(set(pats) - set(modes) - set(out))
        if missing:
            errs.append(f"a complete choice must place every pattern; not placed: {missing}")
    return errs

def check_taxonomy(tax) -> list[str]:
    """Problems with a resolved taxonomy, such as one given inline by a plugin."""
    if not isinstance(tax, dict):
        return ["a taxonomy must be a JSON object"]
    errs = [f"the taxonomy needs a non-empty string '{k}'" for k in ("id", "version") if not isinstance(tax.get(k), str) or not tax[k]]
    modes = tax.get("modes")
    if not isinstance(modes, list) or not modes or not all(isinstance(m, dict) for m in modes):
        return errs + ["'modes' must be a non-empty list of objects"]
    ids = [m.get("id") for m in modes]
    if len(set(ids)) != len(ids):
        errs.append("mode ids must be unique")
    gids = {g.get("id") for g in tax.get("groups", [])}
    for m in modes:
        errs += [f"mode {m.get('id')!r} needs a non-empty string '{k}'" for k in ("id", "name", "definition")
                 if not isinstance(m.get(k), str) or not m[k]]
        if m.get("group") is not None and m["group"] not in gids:
            errs.append(f"mode {m.get('id')!r} is in group {m['group']!r}, which 'groups' does not define")
    return errs

# ---- helpers for annotators whose output is analysis.v1

ANALYSIS_SCHEMA = "comms-failure/analysis.v1"
SEVERITIES = ("none", "low", "medium", "high", "unknown")
LAYERS = ("naming", "view", "check", "none")

def empty_annotation() -> dict:
    """The slots a human annotation pass fills: labels, facts, what was uncertain, who annotated."""
    return {"labels": {"accept": {}, "result": {}, "review_pass": {}},
            "facts": {"delivered": {}, "acted": {}, "passed": {}},
            "uncertain": [], "annotators": [], "adjudicated": False}

def base_analysis(trace: Trace, annotator) -> dict:
    """An analysis.v1 output with every mode of the annotator's taxonomy absent. Fill metrics, items and the
    modes you have evidence for."""
    return {
        "schema": ANALYSIS_SCHEMA,
        "source": {**trace.source, "annotator": f"{annotator.name}@{annotator.version}"},
        "room": {"name": trace.room.get("name"), "created_at": trace.room.get("created_at"),
                 "latest_sequence": trace.room.get("latest_sequence"), "seats": trace.seats},
        "metrics": {"posts": len(trace.posts), "seats": len(trace.seats), "asks": 0, "asks_unanswered": 0, "claims": 0,
                    "re_claims": 0, "heartbeat_posts": 0, "heartbeat_share": 0.0, "open_items_at_end": 0, "last_post_kind": "other"},
        "items": {},
        "modes": [{"id": m["id"], "name": m["name"], "group": m.get("group"), "present": False, "severity": "none",
                   "count": 0, "confidence": 0.0, "removed_by": m.get("removed_by", "none"), "evidence": []}
                  for m in taxonomy_of(annotator)["modes"]],
        "annotation": empty_annotation(),
        "caveats": [],
    }

def set_mode(analysis: dict, mid: str, *, evidence: list, severity: str, confidence: float, count: int | None = None) -> None:
    """Fill one mode. Evidence rows are {seq, who, excerpt, why}; at most 25 are kept."""
    for x in analysis["modes"]:
        if x["id"] == mid:
            x.update({"present": bool(evidence) or (count or 0) > 0, "severity": severity, "confidence": confidence,
                      "count": len(evidence) if count is None else count, "evidence": evidence[:25]})
            return
    raise KeyError(mid)

def severity_for(rate: float, high: float, medium: float, low: float) -> str:
    return "high" if rate >= high else "medium" if rate >= medium else "low" if rate >= low else "none"
