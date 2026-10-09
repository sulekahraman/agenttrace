"""Batch acceptance and restart behavior, with only the model process replaced."""
import json
import threading
from pathlib import Path
from types import SimpleNamespace
import pytest
from commsfail.annotators.standard import batch


def completed(out, run):
    out.mkdir(parents=True, exist_ok=True)
    objects = {
        'bundle/index.json': {'run': run, 'evidence_level': 'E3', 'posts': {}, 'actions': {}},
        'A.json': {'items': [], 'incidents': [], 'undecidable': [], 'sweep': []},
        'B.json': {'items': [], 'incidents': [], 'undecidable': [], 'sweep': []},
        'final.json': {'items': [], 'incidents': [], 'undecidable': [], 'rejected': []},
        'agreement.json': {'incidents': {'A': 0, 'B': 0, 'matched': 0, 'matched_same_class': 0},
                           'incident_f1': None, 'class_kappa': None, 'severity_weighted_kappa': None,
                           'severity_mean': {'A': None, 'B': None}, 'pairs': [], 'unmatched': {'A': [], 'B': []}},
        'in-verdict/grade.json': {'items': []},
        'verdict.json': {'items': [], 'explains_score': 'no', 'summary': 'No lost items.'},
    }
    objects['annotation.json'] = {'schema': 'commsfail/annotation.v1', 'run': run, 'evidence_level': 'E3',
                                  **objects['final.json'], 'verdict': objects['verdict.json']}
    objects['annotation.json']['agreement'] = {k: v for k, v in objects['agreement.json'].items()
                                               if k not in ('pairs', 'unmatched')}
    objects['annotation.json']['process'] = {
        'runner': 'test', 'attempts': {k: 1 for k in ('A', 'B', 'judge', 'verdict')},
        'steps': {k: [{'attempt': 0, 'seconds': 0, 'errors': []}] for k in ('A', 'B', 'judge', 'verdict')}}
    for name, obj in objects.items():
        p = out / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(obj))


@pytest.mark.parametrize('damage', ['none', 'missing', 'malformed', 'run', 'evidence', 'null', 'empty', 'component'])
def test_acceptance_rejects_incomplete_or_mismatched_records(tmp_path, damage):
    completed(tmp_path, 'run')
    p = tmp_path / 'annotation.json'
    if damage == 'missing':
        (tmp_path / 'A.json').unlink()
    elif damage == 'malformed':
        p.write_text('{')
    elif damage == 'component':
        (tmp_path / 'verdict.json').write_text('{}')
    elif damage != 'none':
        obj = json.loads(p.read_text())
        if damage == 'empty':
            obj = {}
        else:
            key, value = {'run': ('run', 'wrong'), 'evidence': ('evidence_level', 'E2'), 'null': ('verdict', None)}[damage]
            obj[key] = value
        p.write_text(json.dumps(obj))
    assert bool(batch.validate_completed(tmp_path, 'run')) == (damage != 'none')


def test_batch_runs_two_cases_preserves_failure_and_resumes(tmp_path, monkeypatch):
    src, out = tmp_path / 'src', tmp_path / 'out'
    names = [f'research__task__n{n}__r1' for n in range(1, 5)]
    for name in names:
        (src / name).mkdir(parents=True)
        (src / name / 'score.json').write_text('{"items": []}')
    barrier = threading.Barrier(2)
    fail = {names[2]}
    def process(cmd, stdout, stderr, **kwargs):
        run = Path(cmd[cmd.index('annotate') + 1]).name
        dest = Path(cmd[cmd.index('--out') + 1])
        assert cmd[cmd.index('--effort') + 1] == 'high'
        if run in names[1:3]:
            barrier.wait(timeout=5)
        stdout.write('ran ' + run)
        if run in fail:
            dest.mkdir(parents=True)
            (dest / 'partial').write_text('preserve')
            return SimpleNamespace(returncode=1)
        completed(dest, run)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(batch.subprocess, 'run', process)
    summary = batch.run_batch(src, out)
    assert summary['completed'] == 2 and summary['failed'] == 1 and summary['selected'] == 3
    assert not (out / names[0]).exists()
    assert json.loads((out / 'summary.json').read_text()) == summary
    assert 'ran' in (out / 'logs' / (names[2] + '.log')).read_text()
    fail.clear()
    barrier = threading.Barrier(1)
    summary = batch.run_batch(src, out)
    assert summary['completed'] == 3 and summary['failed'] == 0
    assert sum(r['status'] == 'skipped' for r in summary['records']) == 2
    assert [p.read_text() for p in (out / 'failed-attempts').rglob('partial')] == ['preserve']
    with pytest.raises(ValueError, match='configuration'):
        batch.run_batch(src, out, effort='low')


def test_empty_selection_and_cli_failure_are_nonzero(tmp_path, monkeypatch):
    from commsfail.cli import main
    with pytest.raises(ValueError, match='matched'):
        batch.run_batch(tmp_path, tmp_path / 'out')
    monkeypatch.setattr(batch, 'run_batch', lambda *a, **kw: {'failed': 1, 'completed': 0})
    assert main(['annotate-batch', str(tmp_path), '--out', str(tmp_path / 'out')]) == 1


@pytest.mark.parametrize('field', ['agreement', 'process'])
def test_acceptance_requires_audit_metadata(tmp_path, field):
    completed(tmp_path, 'run')
    p = tmp_path / 'annotation.json'
    rec = json.loads(p.read_text())
    rec.pop(field, None)
    p.write_text(json.dumps(rec))
    assert batch.validate_completed(tmp_path, 'run')


def test_annotate_child_inherits_batch_lock(tmp_path, monkeypatch):
    import os
    import sys
    src, out = tmp_path / 'src', tmp_path / 'out'
    run = src / 'research__task__n2__r1'
    run.mkdir(parents=True)
    (run / 'score.json').write_text('{"items": []}')
    real_run = batch.subprocess.run
    def process(cmd, **kwargs):
        # The real child must retain the lock descriptor if its coordinator dies.
        fd = kwargs.get('pass_fds', (-1,))[0]
        result = real_run([sys.executable, '-c', 'import os,sys; os.fstat(int(sys.argv[1]))', str(fd)], **kwargs)
        completed(out / run.name, run.name)
        return result
    monkeypatch.setattr(batch.subprocess, 'run', process)
    assert batch.run_batch(src, out)['failed'] == 0
