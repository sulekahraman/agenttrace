"""commsfail command line.

    commsfail analyse <src> [--annotator regex_v1] [--source sharednet] [--markdown] [-o out.json]
    commsfail trace <src> [--source sharednet] [--full]   what a source holds, before you annotate it
    commsfail annotators                                  the registered annotators, built in and plugins
    commsfail sources                                     the registered sources
    commsfail schema <annotator>                          an annotator's output schema
    commsfail taxonomy [<choice> | <annotator>]           the taxonomy choices, or one of them, resolved
    commsfail validate <record.json>                      check a record; exit 1 if it does not conform
    commsfail new <name>                                  copy example_kickstart to a new annotator (run it in the repository root)
    commsfail audit export|compare|finalize|codebook      human annotation: blind export, kappa, adjudication, gold

With the default source, <src> is a goal-run record folder, a room.ndjson, a table export, a saved share JSON,
or a share link. ``analyse`` writes a record (the annotator's output in an envelope) and exits 2 when the
output does not conform to the annotator's own schema.
"""
from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path
from . import __version__
from . import audit
from .annotators import (choices, get_annotator, load_choice, make_record, origin, registry, schema_of, taxonomy_of,
                         validate_output, validate_record)
from .annotators.base import NAME_RE
from .sources import DEFAULT, get_source, sources
from .sources.sharednet import summary

def _first_line(doc) -> str:
    lines = (doc or "").strip().splitlines()
    return lines[0] if lines else ""

KICKSTART = Path(__file__).resolve().parent / "annotators" / "example_kickstart"
KICKSTART_NOTE = re.compile(r"<!-- kickstart -->.*?<!-- /kickstart -->\n*", re.S)

def scaffold(name: str, root: Path) -> list[Path]:
    """Copy example_kickstart to commsfail/annotators/<name>/ and its test to tests/annotators/test_<name>.py."""
    if not NAME_RE.match(name):
        raise SystemExit("the name must be 2 to 41 characters: lowercase letters, digits and _, starting with a letter")
    pkg = root / "commsfail" / "annotators"
    if not pkg.is_dir():
        raise SystemExit(f"{pkg} not found: run `commsfail new` in the root of a commsfail checkout")
    dest, test = pkg / name, root / "tests" / "annotators" / f"test_{name}.py"
    for p in (dest, test):
        if p.exists():
            raise SystemExit(f"{p} exists already")
    cls = "".join(w[:1].upper() + w[1:] for w in name.split("_"))
    fill = lambda s: s.replace("ExampleKickstart", cls).replace("example_kickstart", name)
    dest.mkdir(parents=True)
    test.parent.mkdir(parents=True, exist_ok=True)
    made = []
    for src, dst in [(KICKSTART / f, dest / f) for f in ("__init__.py", "schema.json", "README.md")] + \
                    [(KICKSTART / "test_example_kickstart.py.txt", test)]:
        text = src.read_text(encoding="utf-8")
        if dst.name == "README.md":
            text = KICKSTART_NOTE.sub("", text)
        dst.write_text(fill(text), encoding="utf-8")
        made.append(dst)
    return made

def _audit(a) -> int:
    if a.step == "codebook":
        if not a.name:
            for name, book in audit.CODEBOOKS.items():
                print(f"{name:<18} {len(book['labels']):>2} labels  {book['description']}")
            for name in choices():
                t = load_choice(name)
                print(f"{name:<18} {len(t['modes']):>2} labels  the patterns of the {name} taxonomy; "
                      f"{name}:groups for its {len(t['groups'])} classes")
            return 0
        print(json.dumps(audit.load_codebook(a.name), ensure_ascii=False, indent=1)); return 0
    if a.step == "export":
        load = get_source(a.source)
        blind, key = audit.export((load(s) for s in a.src), a.salt, a.codebook, a.context)
        audit.write_jsonl(a.out, blind); audit.write_jsonl(a.key, key)
        boards = len({r["episode_id"] for r in blind})
        print(f"wrote {len(blind)} rows from {boards} board{'s' * (boards != 1)} to {a.out}; the key, {a.key}, stays with you")
        return 0
    if a.step == "compare":
        report, todo = audit.compare(audit.read_jsonl(a.a), audit.read_jsonl(a.b))
        Path(a.report).parent.mkdir(parents=True, exist_ok=True)
        Path(a.report).write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
        audit.write_jsonl(a.adjudicate, todo)
        print(f"{report['samples']} rows, exact agreement {report['exact_agreement']}, {len(todo)} to adjudicate "
              f"in {a.adjudicate}; kappa per label in {a.report}")
        return 0
    gold = audit.finalize(audit.read_jsonl(a.a), audit.read_jsonl(a.b),
                          audit.read_jsonl(a.adjudicated) if a.adjudicated else [], audit.read_jsonl(a.key))
    audit.write_jsonl(a.out, gold)
    print(f"wrote {len(gold)} gold rows, {sum(r['adjudicated'] for r in gold)} of them adjudicated, to {a.out}")
    return 0

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="commsfail", description="communication-failure analysis of multi-agent message boards")
    ap.add_argument("--version", action="version", version=f"commsfail {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)
    an = sub.add_parser("analyse", help="annotate one board and print (or write) the record")
    an.add_argument("src", help="for the sharednet source: a record folder, room.ndjson, share.json, or a share link")
    an.add_argument("--annotator", default="regex_v1", help="a registered annotator (default: regex_v1)")
    an.add_argument("--source", default=DEFAULT, help=f"a registered source (default: {DEFAULT})")
    an.add_argument("--markdown", action="store_true", help="print the annotator's short view instead of the record")
    an.add_argument("-o", "--out", help="write to this file instead of stdout")
    tr = sub.add_parser("trace", help="show what a source holds")
    tr.add_argument("src"); tr.add_argument("--source", default=DEFAULT)
    tr.add_argument("--full", action="store_true", help="print the whole Trace as JSON, not a summary")
    sub.add_parser("annotators", help="list registered annotators")
    sub.add_parser("sources", help="list registered sources")
    sc = sub.add_parser("schema", help="print an annotator's output schema"); sc.add_argument("annotator")
    tx = sub.add_parser("taxonomy", help="list the taxonomy choices, or print one (by choice or annotator)")
    tx.add_argument("name", nargs="?")
    va = sub.add_parser("validate", help="check a record file"); va.add_argument("file")
    nw = sub.add_parser("new", help="start a new annotator: a copy of example_kickstart")
    nw.add_argument("name"); nw.add_argument("--root", default=".", help="the repository root (default: .)")
    au = sub.add_parser("audit", help="human annotation: blind export, compare (kappa), finalize (gold)")
    steps = au.add_subparsers(dest="step", required=True)
    ex = steps.add_parser("export", help="boards -> a blind file for the annotators and a private key")
    ex.add_argument("src", nargs="+", help="one or more sources, as for analyse")
    ex.add_argument("--source", default=DEFAULT)
    ex.add_argument("--codebook", default="modes_v1", help="a built-in codebook or a codebook JSON file (default: modes_v1)")
    ex.add_argument("--salt", required=True, help="a secret for the study: stable blind ids that do not reveal the source")
    ex.add_argument("--context", type=int, help="how many earlier posts each row shows (default: all)")
    ex.add_argument("--out", required=True, help="the blind file, for the annotators")
    ex.add_argument("--key", required=True, help="the private key: never give it to an annotator")
    cp = steps.add_parser("compare", help="two filled blind files -> kappa per label, and the rows to adjudicate")
    cp.add_argument("a"); cp.add_argument("b")
    cp.add_argument("--report", required=True); cp.add_argument("--adjudicate", required=True, help="where to write the rows to adjudicate")
    fi = steps.add_parser("finalize", help="both files, the adjudicated rows and the key -> gold labels")
    fi.add_argument("a"); fi.add_argument("b")
    fi.add_argument("--adjudicated", help="the adjudicated rows (leave out when compare found none)")
    fi.add_argument("--key", required=True); fi.add_argument("--out", required=True)
    an2 = sub.add_parser("annotate", help="annotate failure incidents with two agents and a judge (annotation.v1)")
    an2.add_argument("src", help="a goal-run record folder (agents/ inside it are the agents' logs)")
    an2.add_argument("--out", required=True, help="the folder for the bundle, the annotations, and the record")
    an2.add_argument("--grade", help="the run's grade (score.json); with it, the verdict step runs after the judge")
    an2.add_argument("--model", default="gpt-6-luna"); an2.add_argument("--effort", default=None)
    an2.add_argument("--image", default="commsfail-agent-annotator:0.1")
    an2.add_argument("--retries", type=int, default=3)
    ab = sub.add_parser("annotate-batch", help="run and resume graded E3 incident annotations")
    ab.add_argument("src_root")
    ab.add_argument("--out", required=True)
    ab.add_argument("--pattern", default="research__*__n[234]__r1")
    ab.add_argument("--workers", type=int, default=2)
    ab.add_argument("--model", default="gpt-6-luna")
    ab.add_argument("--effort", default="high")
    ab.add_argument("--image", default="commsfail-agent-annotator:0.1")
    ab.add_argument("--retries", type=int, default=3)
    cb = steps.add_parser("codebook", help="list the built-in codebooks, or print one")
    cb.add_argument("name", nargs="?")
    a = ap.parse_args(argv)

    if a.cmd == "annotators":
        from .annotators.standard.pipeline import SCHEMA
        print(f"{'standard':<18} {'1':<8} {'builtin pipeline':<24} {SCHEMA:<32} "
              "state_gap@1      use annotate / annotate-batch")
        for name, cls in sorted(registry().items()):
            tax = taxonomy_of(cls)
            tax = f"{tax['id']}@{tax['version']}" if tax else "-"
            print(f"{name:<18} {str(getattr(cls, 'version', '?')):<8} {origin(cls):<24} {schema_of(cls).get('$id', '?'):<32} "
                  f"{tax:<18} {_first_line(cls.__doc__)}")
        return 0
    if a.cmd == "sources":
        for name, fn in sorted(sources().items()):
            where = "builtin" if fn.__module__.startswith("commsfail.") else fn.__module__
            print(f"{name:<14} {where:<24} {_first_line(fn.__doc__)}")
        return 0
    if a.cmd == "schema":
        print(json.dumps(schema_of(get_annotator(a.annotator)), indent=2)); return 0
    if a.cmd == "taxonomy":
        if not a.name:
            for name in choices():
                t = load_choice(name)
                print(f"{name:<16} {len(t['groups']):>2} classes {len(t['modes']):>3} patterns  "
                      f"{'complete' if t['complete'] else 'partial ':<9} {_first_line(t['description'])}")
            return 0
        tax = load_choice(a.name) if a.name in choices() else taxonomy_of(get_annotator(a.name))
        if tax is None:
            print(f"{a.name} has no taxonomy", file=sys.stderr); return 1
        print(json.dumps(tax, ensure_ascii=False, indent=2)); return 0
    if a.cmd == "validate":
        with open(a.file, encoding="utf-8") as f:
            errs = validate_record(json.load(f))
        print("\n".join(errs) if errs else "ok"); return 1 if errs else 0
    if a.cmd == "new":
        made = scaffold(a.name, Path(a.root))
        print("made:\n  " + "\n  ".join(str(p) for p in made))
        print(f"next: run pytest (the copy passes as it is), then make it yours: pick a taxonomy and write your "
              f"method in {made[0].name}, then {made[1].name}, {made[2].name} and {made[3].name}")
        return 0
    if a.cmd == "annotate-batch":
        from .annotators.standard.batch import run_batch
        try:
            result = run_batch(a.src_root, a.out, a.pattern, a.workers, a.model, a.effort, a.image, a.retries)
        except (ValueError, OSError) as exc:
            print(f"commsfail annotate-batch: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result, indent=2))
        return 1 if result["failed"] else 0
    if a.cmd == "annotate":
        from .annotators.standard import DockerCodex, annotate
        rec = annotate(a.src, a.out, DockerCodex(image=a.image, model=a.model, effort=a.effort), grade=a.grade,
                       retries=a.retries)
        ag = rec["agreement"]
        print(f"{len(rec['incidents'])} incidents ({len(rec['rejected'])} rejected); A/B incident F1 "
              f"{ag['incident_f1']}, class kappa {ag['class_kappa']}, severity kappa {ag['severity_weighted_kappa']}; "
              f"attempts {rec['process']['attempts']}; wrote {a.out}/annotation.json")
        return 0
    if a.cmd == "audit":
        try:
            return _audit(a)
        except ValueError as e:
            print(f"commsfail audit {a.step}: {e}", file=sys.stderr); return 1

    trace = get_source(a.source)(a.src)
    if a.cmd == "trace":
        print(json.dumps(trace.to_dict() if a.full else summary(trace), ensure_ascii=False, indent=1)); return 0
    ann = get_annotator(a.annotator)
    output = ann.annotate(trace)
    errs = validate_output(ann, output)
    if errs:
        print(f"{ann.name} output does not conform to its schema:\n  " + "\n  ".join(errs[:20]), file=sys.stderr); return 2
    if a.markdown:
        if not callable(getattr(ann, "markdown", None)):
            print(f"{ann.name} has no markdown view; leave out --markdown", file=sys.stderr); return 1
        text = ann.markdown(output)
    else:
        text = json.dumps(make_record(ann, trace, output), ensure_ascii=False, indent=1)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print(f"wrote {a.out}")
    else:
        print(text)
    return 0

if __name__ == "__main__":
    sys.exit(main())
