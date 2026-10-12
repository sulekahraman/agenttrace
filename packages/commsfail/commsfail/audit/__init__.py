"""Human annotation of boards: blind export, two annotators, Cohen's kappa, adjudication, a gold file.

Three steps, each a function here and a ``commsfail audit`` command:

    export    boards -> blind.jsonl (one row per agent post, for the annotators) + key.jsonl (private)
    compare   two filled copies of blind.jsonl -> an agreement report (kappa per label) + the rows to adjudicate
    finalize  both copies + the adjudicated rows + the key -> gold.jsonl, with provenance restored

A codebook names the labels. Each label is one yes-or-no decision about one post. A codebook is one of:

    modes_v1         the ten_modes taxonomy: which of the paper's ten modes a post is evidence of
    discourse_v1     accept, result, review_pass: what a post does (Table 1 of the comms-failure paper, per post)
    <choice>         a taxonomy choice: its patterns become the labels (state_gap, decision_point, ...)
    <choice>:groups  the same choice, labelled by class instead of by pattern: fewer, coarser decisions
    <annotator>      the taxonomy the annotator reports in, so people label what it reports
    <file>.json      a codebook {"id", "version", "labels": [{"id", "definition"}], "rules"}

The blind file holds what a reader needs and nothing more: the post, its author's handle, the handles it
addresses, and the posts before it. The source path, the Room's id and name, the seats' models, the checks,
the episode summary and the seats' own logs stay out; the key holds where each row came from. Tokens and
email addresses are scrubbed from text. Every row carries a digest of its fixed fields, so an edit to
anything but ``labels``, ``uncertain`` and ``note`` is caught.
"""
from __future__ import annotations
import hashlib, json, random, re
from pathlib import Path
from typing import Iterable
from ..annotators.taxonomy import choices, load_choice, taxonomy_of
from ..sources.sharednet import TOKEN_RE, agent_posts, mentions
from ..trace import Trace

BLIND = "commsfail/audit-blind.v1"
REPORT = "commsfail/audit-report.v1"
GOLD = "commsfail/audit-gold.v1"
# The fields an annotator must not change. The digest covers them.
FIXED = ("sample_id", "episode_id", "schema", "codebook", "choices", "seq", "actor", "addressed_to", "content",
         "context_before")
RULES = [
    "Judge each post from what the row shows: the post and the posts before it. Never look at the key, the grade or the condition.",
    "A label applies when the post itself does what the definition says. When in doubt between yes and no, use `uncertain`.",
    "`uncertain` holds the labels you cannot decide from the visible record. They are left out of kappa and always adjudicated.",
    "Write the items you mean (file names, task ids) in `note`. Change nothing but `labels`, `uncertain` and `note`.",
]
def codebook_from_taxonomy(tax: dict, cid: str | None = None, level: str = "modes") -> dict:
    """A codebook whose labels are a taxonomy's patterns, or with level="groups", its classes."""
    return {"id": cid or tax["id"], "version": tax["version"], "description": tax["description"],
            "labels": [{"id": m["id"], "name": m["name"], "definition": m["definition"]} for m in tax[level]],
            "rules": RULES}

CODEBOOKS = {
    "modes_v1": {**codebook_from_taxonomy(load_choice("ten_modes"), "modes_v1"), "version": "1",
                 "description": "Which of regex_v1's ten failure modes this post is evidence of. Label the post where the failure shows."},
    "discourse_v1": {
        "id": "discourse_v1", "version": "1",
        "description": "What the post does. Failure modes are then read by rule from these labels and the record.",
        "labels": [
            {"id": "accept", "name": "Accept",
             "definition": "The author makes an unconditional commitment to own a named item. Offers, intentions and hedges do not count."},
            {"id": "result", "name": "Result",
             "definition": "The author asserts that a named item is delivered or ready for review. Judge the assertion; whether the artifact exists is read from the record."},
            {"id": "review_pass", "name": "Review pass",
             "definition": "The author positively reviews another seat's current result for a named item. Intentions, questions, failures and self-review do not count."},
        ],
        "rules": RULES,
    },
}

def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def _canon(x) -> str:
    return json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

def scrub(text) -> str:
    """Post text for a human reader: tokens and email addresses removed, everything else kept as written."""
    s = TOKEN_RE.sub("<token>", text or "")
    return re.sub(r"[\w.+-]+@[\w-]+\.[\w.]+", "<email>", s)

def trace_digest(trace: Trace) -> str:
    """A digest of the board's posts. The same posts give the same digest, whatever the source format."""
    return "sha256:" + _sha(_canon([[p.get("seq"), p.get("who"), p.get("text")] for p in trace.posts]))

def digest(row: dict) -> str:
    return "sha256:" + _sha(_canon({f: row.get(f) for f in FIXED}))

def load_codebook(name_or_path: str) -> dict:
    """A built-in codebook, a taxonomy choice (by pattern or, with ':groups', by class), an annotator's
    taxonomy, or a codebook JSON file."""
    if name_or_path in CODEBOOKS:
        return CODEBOOKS[name_or_path]
    choice, _, level = name_or_path.partition(":")
    if choice in choices() and level in ("", "groups"):
        return codebook_from_taxonomy(load_choice(choice), name_or_path, "groups" if level else "modes")
    from ..annotators import registry
    if name_or_path in registry():
        tax = taxonomy_of(registry()[name_or_path])
        if tax is None:
            raise ValueError(f"annotator {name_or_path!r} has no taxonomy, so it cannot be a codebook")
        return codebook_from_taxonomy(tax, name_or_path)
    p = Path(name_or_path)
    if not p.is_file():
        raise ValueError(f"no codebook {name_or_path!r}: use {sorted(CODEBOOKS)}, a taxonomy choice {choices()}, "
                         "an annotator with a taxonomy, or a JSON file")
    book = json.loads(p.read_text(encoding="utf-8"))
    ids = [x.get("id") for x in book.get("labels") or [] if isinstance(x, dict)]
    if not (isinstance(book.get("id"), str) and book.get("version") and ids and all(isinstance(i, str) for i in ids)
            and len(set(ids)) == len(ids) == len(book["labels"])):
        raise ValueError(f"{p}: a codebook needs an id, a version and labels with unique string ids")
    return book

# ---- export

def export(traces: Iterable[Trace], salt: str, codebook: str = "modes_v1",
           context: int | None = None) -> tuple[list[dict], list[dict]]:
    """Blind rows for the annotators, shuffled, and the private key that says where each came from.

    One row per agent post. ``context`` is how many earlier posts each row shows (None: all of them).
    The salt is a secret for the study: the same boards and salt give the same ids and the same order.
    """
    if not salt:
        raise ValueError("a salt is required: it keeps the blind ids stable without revealing the source")
    book = load_codebook(codebook)
    ref, choices = f"{book['id']}@{book['version']}", [x["id"] for x in book["labels"]]
    blind, key, seen = [], [], set()
    for trace in traces:
        td = trace_digest(trace)
        episode = "episode-" + _sha(f"{salt}|{td}")[:12]
        if episode in seen:
            raise ValueError(f"the same board was given twice: {trace.source.get('path') or trace.room.get('name')}")
        seen.add(episode)
        source = {k: v for k, v in trace.source.items() if k not in ("loaded_at", "fetched_at")}
        visible = [{"seq": p["seq"], "actor": p.get("who"), "content": scrub(p.get("text"))} for p in trace.posts]
        for p in agent_posts(trace):
            before = [v for v in visible if v["seq"] < p["seq"]]
            content = scrub(p.get("text"))
            row = {"sample_id": "sample-" + _sha(f"{salt}|{td}|{p['seq']}")[:16], "episode_id": episode,
                   "schema": BLIND, "codebook": ref, "choices": choices, "seq": p["seq"], "actor": p.get("who"),
                   "addressed_to": mentions(content), "content": content,
                   "context_before": before if context is None else before[-context:] if context > 0 else []}
            row.update(digest=digest(row), labels=None, uncertain=None, note="")
            blind.append(row)
            key.append({"sample_id": row["sample_id"], "episode_id": episode, "seq": p["seq"], "digest": row["digest"],
                        "trace_digest": td, "room": trace.room.get("name"), "source": source})
    random.Random(f"{salt}|order").shuffle(blind)
    return blind, key

# ---- checks shared by compare and finalize

def _index(rows: Iterable[dict], what: str) -> dict[str, dict]:
    out = {}
    for r in rows:
        sid = r.get("sample_id")
        if not isinstance(sid, str) or not sid:
            raise ValueError(f"{what}: a row has no sample_id")
        if sid in out:
            raise ValueError(f"{what}: sample {sid} appears twice")
        out[sid] = r
    return out

def _labels(row: dict) -> tuple[set, set]:
    """The row's labels and uncertain labels, after checking that nothing fixed was edited."""
    sid = row.get("sample_id")
    if row.get("schema") != BLIND:
        raise ValueError(f"sample {sid}: not a {BLIND} row")
    if row.get("digest") != digest(row):
        raise ValueError(f"sample {sid}: a fixed field was edited; change only labels, uncertain and note")
    choices, out = set(row["choices"]), []
    for f in ("labels", "uncertain"):
        v = row.get(f)
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            raise ValueError(f"sample {sid}: `{f}` must be a list of label ids (use [] for none)")
        if set(v) - choices:
            raise ValueError(f"sample {sid}: `{f}` names labels not in {row['codebook']}: {sorted(set(v) - choices)}")
        out.append(set(v))
    if out[0] & out[1]:
        raise ValueError(f"sample {sid}: {sorted(out[0] & out[1])} are both labelled and uncertain")
    return out[0], out[1]

def _same_fixed(a: dict, b: dict, what: str) -> None:
    changed = [f for f in FIXED if a.get(f) != b.get(f)]
    if changed:
        raise ValueError(f"sample {a.get('sample_id')}: {what} differ in fixed fields {changed}")

def _ordered(choices: list, labels: set) -> list:
    return [c for c in choices if c in labels]

def kappa(pairs: list[tuple[bool, bool]]) -> float | None:
    """Cohen's kappa for two raters' yes-or-no decisions. None when it is undefined: no decisions, or both
    raters gave the same single answer every time."""
    if not pairs:
        return None
    n = len(pairs)
    observed = sum(a == b for a, b in pairs) / n
    pa, pb = sum(a for a, _ in pairs) / n, sum(b for _, b in pairs) / n
    expected = pa * pb + (1 - pa) * (1 - pb)
    return None if expected == 1 else (observed - expected) / (1 - expected)

# ---- compare

def compare(rows_a: list[dict], rows_b: list[dict]) -> tuple[dict, list[dict]]:
    """Agreement between two annotators, and the rows they must adjudicate (any difference, or any uncertain)."""
    A, B = _index(rows_a, "annotator A"), _index(rows_b, "annotator B")
    if not A:
        raise ValueError("annotator A's file has no rows")
    if set(A) != set(B):
        raise ValueError(f"the annotators labelled different samples: {len(set(A) ^ set(B))} differ")
    books = {r.get("codebook") for r in A.values()}
    if len(books) != 1:
        raise ValueError(f"the rows come from more than one codebook: {sorted(map(str, books))}")
    choices = next(iter(A.values()))["choices"]
    pairs = {c: [] for c in choices}
    excluded = {c: 0 for c in choices}
    positives = {c: {"a": 0, "b": 0} for c in choices}
    todo, exact = [], 0
    for sid in sorted(A):
        a, b = A[sid], B[sid]
        _same_fixed(a, b, "the two annotators' rows")
        (la, ua), (lb, ub) = _labels(a), _labels(b)
        for c in choices:
            positives[c]["a"] += c in la
            positives[c]["b"] += c in lb
            if c in ua or c in ub:
                excluded[c] += 1
            else:
                pairs[c].append((c in la, c in lb))
        if la == lb and not ua and not ub:
            exact += 1
            continue
        todo.append({**{f: a[f] for f in FIXED}, "digest": a["digest"],
                     "annotator_a": {"labels": _ordered(choices, la), "uncertain": _ordered(choices, ua), "note": a.get("note") or ""},
                     "annotator_b": {"labels": _ordered(choices, lb), "uncertain": _ordered(choices, ub), "note": b.get("note") or ""},
                     "labels": None, "uncertain": None, "note": ""})
    k = {c: kappa(pairs[c]) for c in choices}
    report = {"schema": REPORT, "codebook": books.pop(), "samples": len(A),
              "episodes": len({r["episode_id"] for r in A.values()}),
              "exact_agreement": round(exact / len(A), 4), "to_adjudicate": len(todo),
              "kappa": {c: None if v is None else round(v, 4) for c, v in k.items()},
              "decisions": {c: len(pairs[c]) for c in choices}, "positives": positives, "uncertain_excluded": excluded}
    return report, todo

# ---- finalize

def finalize(rows_a: list[dict], rows_b: list[dict], adjudicated: list[dict], key: list[dict]) -> list[dict]:
    """Gold labels: agreements as they are, disagreements as adjudicated, each row with its source restored."""
    A, B = _index(rows_a, "annotator A"), _index(rows_b, "annotator B")
    J, K = _index(adjudicated, "the adjudicated rows"), _index(key, "the key")
    if set(A) != set(B) or set(A) != set(K):
        raise ValueError("the two annotator files and the key do not hold the same samples")
    gold, needed = [], set()
    for sid in sorted(A):
        a, b, k = A[sid], B[sid], K[sid]
        _same_fixed(a, b, "the two annotators' rows")
        (la, ua), (lb, ub) = _labels(a), _labels(b)
        if k.get("digest") != a["digest"] or k.get("seq") != a["seq"]:
            raise ValueError(f"sample {sid}: the row does not match the key")
        notes = [n for n in (a.get("note"), b.get("note")) if n]
        if la == lb and not ua and not ub:
            labels, judged = la, False
        else:
            needed.add(sid)
            if sid not in J:
                raise ValueError(f"sample {sid} still needs adjudication")
            j = J[sid]
            _same_fixed(a, j, "the annotator and adjudicated rows")
            labels, uj = _labels(j)
            if uj:
                raise ValueError(f"sample {sid} is still uncertain after adjudication: {sorted(uj)}")
            judged = True
            notes += [j["note"]] if j.get("note") else []
        gold.append({"schema": GOLD, "sample_id": sid, "episode_id": a["episode_id"], "codebook": a["codebook"],
                     "room": k.get("room"), "source": k.get("source"), "trace_digest": k.get("trace_digest"),
                     "seq": a["seq"], "actor": a["actor"], "labels": _ordered(a["choices"], labels),
                     "adjudicated": judged, "notes": notes})
    extra = set(J) - needed
    if extra:
        raise ValueError(f"the adjudicated rows include {len(extra)} samples the annotators agreed on, e.g. {sorted(extra)[0]}")
    return sorted(gold, key=lambda r: (_canon(r["source"]), r["seq"]))

# ---- files

def read_jsonl(path) -> list[dict]:
    rows = []
    for n, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ValueError(f"{path}:{n}: not JSON ({e.msg})") from e
    return rows

def write_jsonl(path, rows: Iterable[dict]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
