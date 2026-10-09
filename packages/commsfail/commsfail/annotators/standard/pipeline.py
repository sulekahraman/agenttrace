"""The annotation pipeline: bundle, two annotator agents, the judge, then the verdict.

    run/bundle/        what the annotators read (no grade)
    run/A.json B.json  the two annotations, each after its checks passed
    run/agreement.json how far A and B agree
    run/final.json     the judge's record
    run/verdict.json   after the grade: the cause of every lost item
    run/annotation.json everything above in one record, with how many attempts each step took
    run/attempts/      every prompt and every raw reply, kept for audit

A step's reply is parsed and checked; a reply that fails is sent back with the reasons, at most `retries` times.
The agents run through a `runner`: a function (workdir, prompt, tag) -> the agent's last message. `DockerCodex`
runs Codex in a container whose only writable mount is its own output folder.
"""
from __future__ import annotations
import json, os, shutil, subprocess, time, uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from . import agree, bundle, check

PROMPTS = Path(__file__).resolve().parent / "prompts"
SCHEMA = "commsfail/annotation.v1"

class DockerCodex:
    """Codex CLI in a container: the bundle read-only, nothing else of the host but its own output folder."""
    def __init__(self, image="commsfail-agent-annotator:0.1", model="gpt-6-luna", effort=None,
                 auth=Path.home() / ".codex" / "auth.json", cpus="1", memory="2g", timeout=1800):
        self.image, self.model, self.effort, self.auth = image, model, effort, Path(auth)
        self.cpus, self.memory, self.timeout = cpus, memory, timeout

    def __call__(self, workdir: Path, prompt: str, tag: str) -> str:
        out = workdir.parent / "attempts" / tag
        home = out / "codex-home"
        home.mkdir(parents=True, exist_ok=True)
        (home / "config.toml").write_text(f'model = "{self.model}"\n'
                                          + (f'model_reasoning_effort = "{self.effort}"\n' if self.effort else ""))
        name = f"xisen-annotate-{tag}-{uuid.uuid4().hex[:8]}"     # unique: runs started in the same second collide
        cmd = ["docker", "run", "--rm", "-i", "--name", name, "--cpus", self.cpus, "--memory", self.memory,
               "--user", f"{os.getuid()}:{os.getgid()}", "-e", "HOME=/tmp", "-e", "CODEX_HOME=/codex",
               "-v", f"{home}:/codex", "-v", f"{self.auth}:/codex/auth.json",
               "-v", f"{workdir.resolve()}:/bundle:ro", "-v", f"{out.resolve()}:/out", self.image,
               "codex", "exec", "-m", self.model, "--dangerously-bypass-approvals-and-sandbox",
               "-c", 'web_search="disabled"', "-C", "/bundle", "--skip-git-repo-check", "-o", "/out/last.txt", "-"]
        try:
            r = subprocess.run(cmd, input=prompt, text=True, capture_output=True, timeout=self.timeout)
        except subprocess.TimeoutExpired:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=30)
            raise
        (out / "stderr.txt").write_text(r.stderr[-20000:], encoding="utf-8")
        last = out / "last.txt"
        if not last.exists():
            raise RuntimeError(f"codex wrote no reply (exit {r.returncode}): {r.stderr[-400:]}")
        return last.read_text(encoding="utf-8")

def _step(runner, workdir: Path, prompt: str, validate, tag: str, retries: int) -> tuple[dict | None, list]:
    attempts, ask = [], prompt
    log = workdir.parent / "attempts"
    log.mkdir(exist_ok=True)
    for k in range(retries + 1):
        t0 = time.time()
        try:
            text = runner(workdir, ask, f"{tag}-{k}")
        except Exception as e:                                     # a run that crashed counts as a failed attempt
            attempts.append({"attempt": k, "seconds": round(time.time() - t0), "errors": [f"runner failed: {e}"]})
            continue
        (log / f"{tag}-{k}.prompt.md").write_text(ask, encoding="utf-8")
        (log / f"{tag}-{k}.reply.txt").write_text(text, encoding="utf-8")
        try:
            out = check.parse(text)
            errs = validate(out)
        except (ValueError, TypeError, KeyError, AttributeError) as e:
            out, errs = None, [f"the reply is not one valid JSON object of the required shape: {e}"]
        attempts.append({"attempt": k, "seconds": round(time.time() - t0), "errors": errs})
        if not errs:
            return out, attempts
        ask = (prompt + "\n\n## Your previous reply failed these checks\n" + "\n".join(f"- {e}" for e in errs[:40])
               + "\n\nYour previous reply was:\n" + text[:60000] + "\n\nReturn the corrected, complete JSON object only.")
    return None, attempts

def _workdir(base: Path, name: str, src: Path, extra: dict) -> Path:
    d = base / name
    if d.exists():
        shutil.rmtree(d)
    shutil.copytree(src, d)
    for fname, obj in extra.items():
        (d / fname).write_text(json.dumps(obj, indent=1, ensure_ascii=False), encoding="utf-8")
    return d

def annotate(src: str, out: str | Path, runner, grade: str | None = None, retries: int = 3) -> dict:
    out = Path(out)
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise ValueError(f"output must be an empty directory: {out}")
    out.mkdir(parents=True, exist_ok=True)
    index = bundle.build(src, out / "bundle")
    prompt = lambda name: (PROMPTS / f"{name}.md").read_text(encoding="utf-8")
    steps = {}
    with ThreadPoolExecutor(max_workers=2) as pool:                 # the two annotators work independently
        futs = {k: pool.submit(_step, runner, _workdir(out, f"in-{k}", out / "bundle", {}), prompt("annotator"),
                               lambda o: check.annotation(o, index) or check.sweep(o, index), k, retries) for k in ("A", "B")}
        res = {k: f.result() for k, f in futs.items()}
    for k, (ann, att) in res.items():
        steps[k] = att
        if ann is None:
            raise RuntimeError(f"annotator {k} failed its checks {retries + 1} times; see {out / 'attempts'}")
        (out / f"{k}.json").write_text(json.dumps(ann, indent=1, ensure_ascii=False), encoding="utf-8")
    a, b = res["A"][0], res["B"][0]
    agreement = agree.compare(a, b)
    (out / "agreement.json").write_text(json.dumps(agreement, indent=1), encoding="utf-8")
    final, steps["judge"] = _step(runner, _workdir(out, "in-judge", out / "bundle",
                                                   {"A.json": a, "B.json": b, "agreement.json": agreement}),
                                  prompt("judge"), lambda o: check.judged(o, index, a, b), "judge", retries)
    if final is None:
        raise RuntimeError(f"the judge failed its checks {retries + 1} times; see {out / 'attempts'}")
    (out / "final.json").write_text(json.dumps(final, indent=1, ensure_ascii=False), encoding="utf-8")
    verdict = None
    if grade:
        g = json.loads(Path(grade).read_text(encoding="utf-8"))
        verdict, steps["verdict"] = _step(runner, _workdir(out, "in-verdict", out / "bundle",
                                                           {"final.json": final, "grade.json": g}),
                                          prompt("verdict"), lambda o: check.verdict(o, final, g), "verdict", retries)
        if verdict is None:
            raise RuntimeError(f"the verdict failed its checks {retries + 1} times; see {out / 'attempts'}")
        (out / "verdict.json").write_text(json.dumps(verdict, indent=1, ensure_ascii=False), encoding="utf-8")
    record = {"schema": SCHEMA, "run": index["run"], "evidence_level": index["evidence_level"],
              "items": final["items"], "incidents": final["incidents"], "rejected": final["rejected"],
              "undecidable": final["undecidable"], "verdict": verdict,
              "agreement": {k: v for k, v in agreement.items() if k not in ("pairs", "unmatched")},
              "process": {"attempts": {k: len(v) for k, v in steps.items()}, "steps": steps,
                          "runner": getattr(runner, "model", type(runner).__name__)}}
    (out / "annotation.json").write_text(json.dumps(record, indent=1, ensure_ascii=False), encoding="utf-8")
    return record
