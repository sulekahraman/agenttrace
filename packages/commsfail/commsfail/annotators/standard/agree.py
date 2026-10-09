"""Agreement between two annotations of the same run.

Two incidents are the same failure when they share their anchor, or at least half of their posts (Jaccard >= 0.5).
On those pairs we report how often the class agrees (Cohen's kappa) and how close the severities are (quadratic
weighted kappa). Incident F1 counts a pair only when the class agrees too.
"""
from __future__ import annotations
from collections import Counter

def _jaccard(a, b) -> float:
    a, b = set(a), set(b)
    return len(a & b) / len(a | b) if a | b else 0.0

def match(a: list[dict], b: list[dict]) -> list[tuple[dict, dict]]:
    """Greedy one-to-one pairs, best overlap first."""
    cands = []
    for x in a:
        for y in b:
            j = _jaccard(x["posts"], y["posts"])
            if x["anchor"] == y["anchor"] or j >= 0.5:
                cands.append((1.0 + j if x["anchor"] == y["anchor"] else j, x["id"], y["id"], x, y))
    pairs, used_a, used_b = [], set(), set()
    for _, ia, ib, x, y in sorted(cands, key=lambda c: -c[0]):
        if ia not in used_a and ib not in used_b:
            pairs.append((x, y)); used_a.add(ia); used_b.add(ib)
    return pairs

def _kappa(pairs, weights=None, cats=None) -> float | None:
    if not pairs:
        return None
    cats = cats or sorted({v for p in pairs for v in p})
    n = len(pairs)
    w = weights or (lambda i, j: 0.0 if i == j else 1.0)
    pa, pb = Counter(x for x, _ in pairs), Counter(y for _, y in pairs)
    obs = sum(w(x, y) for x, y in pairs) / n
    exp = sum(pa[i] * pb[j] * w(i, j) for i in cats for j in cats) / (n * n)
    return None if exp == 0 else round(1 - obs / exp, 3)

def compare(a: dict, b: dict) -> dict:
    ia, ib = a["incidents"], b["incidents"]
    pairs = match(ia, ib)
    same = [(x, y) for x, y in pairs if x["class"] == y["class"]]
    f1 = round(2 * len(same) / (len(ia) + len(ib)), 3) if ia or ib else None
    return {
        "incidents": {"A": len(ia), "B": len(ib), "matched": len(pairs), "matched_same_class": len(same)},
        "incident_f1": f1,
        "class_kappa": _kappa([(x["class"], y["class"]) for x, y in pairs]),
        "severity_weighted_kappa": _kappa([(x["severity"], y["severity"]) for x, y in pairs],
                                          weights=lambda i, j: (i - j) ** 2 / 16, cats=[1, 2, 3, 4, 5]),
        "severity_mean": {"A": round(sum(i["severity"] for i in ia) / len(ia), 2) if ia else None,
                          "B": round(sum(i["severity"] for i in ib) / len(ib), 2) if ib else None},
        "pairs": [{"A": x["id"], "B": y["id"], "class": [x["class"], y["class"]], "severity": [x["severity"], y["severity"]],
                   "anchor": [x["anchor"], y["anchor"]]} for x, y in pairs],
        "unmatched": {"A": [x["id"] for x in ia if x["id"] not in {p[0]["id"] for p in pairs}],
                      "B": [y["id"] for y in ib if y["id"] not in {p[1]["id"] for p in pairs}]},
    }
