"""The annotation pipeline without a model: the bundle, the checks, agreement, and the retry loop with a fake runner."""
import json
from pathlib import Path
import pytest
from commsfail.annotators.standard import annotate, build_bundle, check_annotation, check_judged, check_sweep
from commsfail.annotators.standard.agree import compare

GOAL_RUN = str(Path(__file__).resolve().parent / "fixtures" / "goal_run")

def _inc(**kw):
    base = {"id": "I1", "posts": [3, 4], "anchor": 4, "actions": [], "class": "unreceived", "pattern": "crossed_posts",
            "class_reason": "1 holds; 2 fails: codex-3 had not received P2", "cause": "no read during the turn",
            "consequence": "two claims on pywc.py", "severity": 2, "severity_reason": "2: time spent on the repair",
            "repaired": False, "source": "agents", "confidence": "high", "items": ["W1"]}
    return {**base, **kw}

def _ann(*incs):
    return {"items": [{"id": "W1", "name": "pywc.py"}], "incidents": list(incs), "undecidable": []}

def _swept(ann, index):
    """The annotation with a sweep entry for every agent post, naming the incidents that include it."""
    agent = sorted(int(s) for s, p in index["posts"].items() if p["role"] == "agent")
    return {**ann, "sweep": [{"post": p, "incidents": [i["id"] for i in ann["incidents"] if p in i["posts"]],
                              "note": "checked"} for p in agent]}

@pytest.fixture
def index(tmp_path):
    return build_bundle(GOAL_RUN, tmp_path / "bundle")

def test_the_bundle_holds_the_timeline_the_agents_and_no_grade(index, tmp_path):
    b = tmp_path / "bundle"
    assert sorted(p.name for p in b.iterdir()) == ["agents", "codebook.md", "index.json", "task.md", "timeline.md"]
    assert index["evidence_level"] == "E3" and len(index["posts"]) == 12 and index["actions"]
    assert "had received up to" in (b / "timeline.md").read_text()
    assert not any("score" in p.name for p in b.rglob("*"))

@pytest.mark.parametrize("change,msg", [
    (dict(anchor=9), "must be one of its posts"),
    (dict(posts=[3, 99], anchor=3), "post 99 does not exist"),
    (dict(pattern="D1"), "belongs to class 'ungrounded'"),
    (dict(pattern="HB"), "is overhead"),
    (dict(pattern="anchoring"), "out of scope"),
    (dict(severity=4), "must begin with the level it names"),
    (dict(severity=7, severity_reason="7: x"), "integer from 1 to 5"),
    (dict(actions=["codex-9:1:0"]), "does not exist"),
    (dict(source="nobody"), "source must be"),
    (dict(items=["W9"]), "not in 'items'"),
])
def test_the_checks_name_what_is_wrong(index, change, msg):
    errs = check_annotation(_ann(_inc(**change)), index)
    assert any(msg in e for e in errs), errs

def test_a_valid_incident_passes(index):
    assert check_annotation(_ann(_inc()), index) == []

def test_unreceived_must_involve_an_unseen_post(index):
    seen = index["posts"]["4"]["seen"]
    seen_posts = [p for p in range(2, 4) if p <= (seen or 0)]
    if seen_posts:          # an incident whose other posts were all received is refused
        errs = check_annotation(_ann(_inc(posts=[seen_posts[0], 4])), index)
        assert any("had received up to" in e for e in errs)

def test_a_full_sweep_passes_and_may_note_the_goal(index):
    ann = _swept(_ann(_inc()), index)
    assert check_sweep(ann, index) == []
    assert check_sweep({**ann, "sweep": ann["sweep"] + [{"post": 1, "incidents": [], "note": "the goal"}]}, index) == []

@pytest.mark.parametrize("change,msg", [
    (lambda s: s[1:], "is missing; look at every agent post"),
    (lambda s: s + s[:1], "appears more than once"),
    (lambda s: s + [{"post": 99, "incidents": [], "note": "no such post"}], "post 99 does not exist"),
    (lambda s: [{**e, "incidents": ["I9"]} if e["post"] == 3 else e for e in s], "names incident I9, which does not exist"),
    (lambda s: [{**e, "incidents": []} if e["post"] == 4 else e for e in s], "the sweep entry for post 4 must name I1"),
    (lambda s: [{**e, "incidents": ["I1"]} if e["post"] == 7 else e for e in s], "but I1's posts do not include it"),
    (lambda s: [{**e, "note": ""} for e in s], "needs a 'note'"),
])
def test_the_sweep_checks_name_what_is_wrong(index, change, msg):
    ann = _swept(_ann(_inc()), index)
    errs = check_sweep({**ann, "sweep": change(ann["sweep"])}, index)
    assert any(msg in e for e in errs), errs

def test_the_judge_accounts_for_every_annotator_incident(index):
    a, b = _ann(_inc()), _ann(_inc(id="I1"), _inc(id="I2", posts=[7], anchor=7))
    final = {**_ann({**_inc(), "decision": "agreed", "from": ["A:I1", "B:I1"], "judge_reason": "same failure"}), "rejected": []}
    assert any("neither kept nor rejected: ['B:I2']" in e for e in check_judged(final, index, a, b))
    final["rejected"] = [{"from": "B:I2", "reason": "not a gap"}]
    assert check_judged(final, index, a, b) == []

def test_agreement_matches_by_anchor_or_posts():
    a = _ann(_inc(), _inc(id="I2", posts=[7, 8], anchor=8, severity=3, severity_reason="3: x"))
    b = _ann(_inc(severity=3, severity_reason="3: x"), _inc(id="I2", posts=[10], anchor=10))
    r = compare(a, b)
    assert r["incidents"]["matched"] == 1 and r["incident_f1"] == 0.5 and r["unmatched"] == {"A": ["I2"], "B": ["I2"]}

def test_the_pipeline_retries_until_the_checks_pass(tmp_path):
    calls = []
    good = _swept(_ann(_inc()), build_bundle(GOAL_RUN, tmp_path / "ix"))
    def fake(workdir, prompt, tag):
        calls.append(tag)
        if tag.startswith("judge"):
            return json.dumps({**_ann({**_inc(), "decision": "agreed", "from": ["A:I1", "B:I1"], "judge_reason": "same"}),
                               "rejected": []})
        if tag.endswith("-0"):
            return "not json at all"                       # the first attempt fails the checks
        assert "failed these checks" in prompt             # the retry carries the reasons
        return "```json\n" + json.dumps(good) + "\n```"
    rec = annotate(GOAL_RUN, tmp_path / "out", fake, retries=2)
    assert rec["schema"] == "commsfail/annotation.v1" and len(rec["incidents"]) == 1
    assert rec["process"]["attempts"] == {"A": 2, "B": 2, "judge": 1} and rec["agreement"]["incident_f1"] == 1.0
    assert (tmp_path / "out" / "attempts" / "A-0.reply.txt").read_text() == "not json at all"

def test_the_timeline_says_how_the_runner_ends_a_run(index, tmp_path):
    head = (tmp_path / "bundle" / "timeline.md").read_text().split("\n\n")[1]
    assert "How the run ends: at the first of said DONE; check bash check.sh" in head
    assert 'contains "DONE" anywhere' in head and "every turn still running is cut" in head

def test_workspace_md_holds_the_teams_files_the_snapshots_and_the_report(tmp_path):
    import shutil, subprocess
    src = tmp_path / "run"; shutil.copytree(GOAL_RUN, src)
    work = tmp_path / "work"; work.mkdir()
    git = lambda *a: subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=work, check=True,
                                    capture_output=True)
    git("init", "-q")
    for name, text in [("data/in.csv", "a,b\n"), ("code/run.py", "print('hi')\n"), ("report/report.md", "# Findings\n")]:
        (work / name).parent.mkdir(exist_ok=True); (work / name).write_text(text)
        git("add", "-A"); git("commit", "-q", "-m", f"after P{len(name)}")
    git("clone", "-q", "--bare", str(work), str(src / "workspace.git"))
    build_bundle(str(src), tmp_path / "bundle")
    ws = (tmp_path / "bundle" / "workspace.md").read_text()
    assert "- code/run.py" in ws and "- data/in.csv" not in ws
    assert "## Snapshots" in ws and "# Findings" in ws and "print('hi')" in ws

def test_each_container_has_its_own_name_and_the_box_caps(tmp_path, monkeypatch):
    from commsfail.annotators.standard import pipeline
    cmds = []
    def fake_run(cmd, **kw):
        cmds.append(cmd)
        (tmp_path / "attempts" / "A-0" / "last.txt").write_text("{}")     # where the container writes its reply
        return type("R", (), {"stderr": "", "returncode": 0})()
    monkeypatch.setattr(pipeline.subprocess, "run", fake_run)
    (tmp_path / "b").mkdir()
    runner = pipeline.DockerCodex(auth=tmp_path / "auth.json")
    runner(tmp_path / "b", "p", "A-0"); runner(tmp_path / "b", "p", "A-0")   # same tag, same second
    names = [c[c.index("--name") + 1] for c in cmds]
    assert names[0] != names[1] and all(n.startswith("xisen-annotate-A-0-") for n in names)
    assert {"--rm", "--cpus", "--memory", "--user"} <= set(cmds[0]) and any(a.endswith(":/bundle:ro") for a in cmds[0])


def test_nonempty_output_is_rejected_without_touching_it(tmp_path):
    out = tmp_path / 'out'
    out.mkdir()
    (out / 'sentinel').write_text('keep me')
    with pytest.raises(ValueError, match='empty'):
        annotate(GOAL_RUN, out, lambda *args: '{}', retries=0)
    assert list(out.iterdir()) == [out / 'sentinel']
    assert (out / 'sentinel').read_text() == 'keep me'


def test_invalid_verdict_exhaustion_cannot_produce_success(tmp_path):
    good = _swept(_ann(), build_bundle(GOAL_RUN, tmp_path / 'ix'))
    grade = tmp_path / 'score.json'
    grade.write_text('{"items": []}')
    def runner(workdir, prompt, tag):
        if tag.startswith('verdict'):
            return '{}'
        return json.dumps({**good, 'rejected': []})
    out = tmp_path / 'out'
    with pytest.raises(RuntimeError, match='verdict'):
        annotate(GOAL_RUN, out, runner, grade=str(grade), retries=1)
    assert not (out / 'annotation.json').exists()
    assert not (out / 'verdict.json').exists()
    assert (out / 'attempts' / 'verdict-1.reply.txt').exists()


def test_docker_timeout_removes_container_before_retry(tmp_path, monkeypatch):
    import subprocess
    from commsfail.annotators.standard import pipeline
    calls = []
    def process(cmd, **kwargs):
        calls.append(cmd)
        if cmd[:2] == ['docker', 'run']:
            raise subprocess.TimeoutExpired(cmd, 1)
        return subprocess.CompletedProcess(cmd, 0)
    monkeypatch.setattr(pipeline.subprocess, 'run', process)
    with pytest.raises(subprocess.TimeoutExpired):
        pipeline.DockerCodex(auth=tmp_path / 'auth.json')(tmp_path / 'bundle', 'prompt', 'A-0')
    name = calls[0][calls[0].index('--name') + 1]
    assert ['docker', 'rm', '-f', name] in calls


def test_verdict_incident_causes_must_reference_real_incidents():
    from commsfail.annotators.standard.check import verdict
    obj = {'items': [{'index': 0, 'causes': [{'kind': 'incident', 'incidents': [None]}]}],
           'explains_score': 'yes', 'summary': 'Invalid reference.'}
    assert verdict(obj, {'incidents': []}, {'items': [{'index': 0, 'score': 0}]})
