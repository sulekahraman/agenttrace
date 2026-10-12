"""Resumable graded annotation batches. Completed artifacts are checked before reuse."""
from __future__ import annotations
import fcntl
import json
import subprocess
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from . import agree, check
from .pipeline import SCHEMA


def validate_completed(out, expected_run, require_verdict=True) -> list[str]:
    out = Path(out)
    names = ['annotation.json', 'bundle/index.json', 'A.json', 'B.json', 'final.json', 'agreement.json']
    if require_verdict:
        names += ['verdict.json', 'in-verdict/grade.json']
    data, errors = {}, []
    for name in names:
        try:
            obj = json.loads((out / name).read_text())
            if not isinstance(obj, dict):
                raise ValueError('expected an object')
            data[name] = obj
        except (OSError, ValueError) as exc:
            errors.append(f'{name}: {exc}')
    if errors:
        return errors
    rec, index, final = (data[n] for n in ('annotation.json', 'bundle/index.json', 'final.json'))
    if rec.get('schema') != SCHEMA:
        errors.append('annotation schema mismatch')
    for name, obj in [('annotation', rec), ('bundle', index)]:
        if obj.get('run') != expected_run:
            errors.append(f'{name} run mismatch')
        if obj.get('evidence_level') != 'E3':
            errors.append(f'{name} evidence level must be E3')
    try:
        for key in ('items', 'incidents', 'rejected', 'undecidable'):
            if key not in rec or rec[key] != final.get(key):
                errors.append(f'annotation {key} does not match final')
        a, b = data['A.json'], data['B.json']
        for name, obj in [('A', a), ('B', b)]:
            errors.extend(f'{name}: {e}' for e in check.annotation(obj, index) + check.sweep(obj, index))
        errors.extend(check.judged(final, index, a, b))
        agreement = agree.compare(a, b)
        if data['agreement.json'] != agreement or rec.get('agreement') != {
                k: v for k, v in agreement.items() if k not in ('pairs', 'unmatched')}:
            errors.append('agreement metadata does not match A/B')
        process = rec.get('process', {})
        for stage in ['A', 'B', 'judge'] + (['verdict'] if require_verdict else []):
            attempts = process.get('steps', {}).get(stage)
            if (not isinstance(attempts, list) or not attempts
                    or process.get('attempts', {}).get(stage) != len(attempts)
                    or not isinstance(attempts[-1], dict) or attempts[-1].get('errors') != []):
                errors.append(f'missing or inconsistent process metadata for {stage}')
        if require_verdict:
            verdict = data['verdict.json']
            if rec.get('verdict') != verdict:
                errors.append('annotation verdict does not match verdict.json')
            errors.extend(check.verdict(verdict, final, data['in-verdict/grade.json']))
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        errors.append(f'malformed annotation: {exc}')
    return errors


def _write(path, obj):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(obj, indent=2) + '\n')
    tmp.replace(path)


def run_batch(src_root, out_root, pattern='research__*__n[234]__r1', workers=2,
              model='gpt-6-luna', effort='high', image='commsfail-agent-annotator:0.1', retries=3) -> dict:
    src_root, out_root = Path(src_root).resolve(), Path(out_root).resolve()
    if workers < 1 or retries < 0:
        raise ValueError('workers must be positive and retries nonnegative')
    if '/' in pattern or pattern in ('.', '..'):
        raise ValueError('pattern must select direct child directories')
    runs = sorted(p for p in src_root.glob(pattern) if p.is_dir())
    if not runs:
        raise ValueError('no source records matched')
    if out_root == src_root or out_root in src_root.parents or src_root in out_root.parents:
        raise ValueError('source and output directories must be separate')
    out_root.mkdir(parents=True, exist_ok=True)
    with (out_root / '.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError(f'another batch owns {out_root}') from None
        config = dict(source=str(src_root), pattern=pattern, runs=[p.name for p in runs],
                      model=model, effort=effort, image=image, retries=retries)
        config_path = out_root / 'config.json'
        if config_path.exists() and json.loads(config_path.read_text()) != config:
            raise ValueError('batch configuration changed; choose a fresh output root')
        _write(config_path, config)
        (out_root / 'logs').mkdir(exist_ok=True)
        summary = dict(selected=len(runs), completed=0, failed=0, pending=len(runs), records=[])
        _write(out_root / 'summary.json', summary)

        def one(src):
            dest = out_root / src.name
            try:
                if dest.exists() and not validate_completed(dest, src.name):
                    return dict(run=src.name, status='skipped', errors=[])
                if dest.exists():
                    archive = out_root / 'failed-attempts' / (src.name + '-' + uuid.uuid4().hex[:12])
                    archive.parent.mkdir(exist_ok=True)
                    dest.rename(archive)
                    old_log = out_root / 'logs' / (src.name + '.log')
                    if old_log.exists():
                        old_log.rename(archive / 'process.log')
                cmd = [sys.executable, '-m', 'commsfail.cli', 'annotate', str(src), '--out', str(dest),
                       '--grade', str(src / 'score.json'), '--model', model, '--effort', effort,
                       '--image', image, '--retries', str(retries)]
                with (out_root / 'logs' / (src.name + '.log')).open('w') as log:
                    if not (src / 'score.json').is_file():
                        raise ValueError('missing score.json')
                    result = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, pass_fds=(lock.fileno(),))
                errors = validate_completed(dest, src.name)
                if result.returncode:
                    errors.insert(0, f'annotate exited {result.returncode}')
                return dict(run=src.name, status='failed' if errors else 'completed', errors=errors)
            except Exception as exc:
                return dict(run=src.name, status='failed', errors=[str(exc)])

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(one, src) for src in runs]
            for future in as_completed(futures):
                row = future.result()
                summary['records'].append(row)
                summary['records'].sort(key=lambda r: r['run'])
                summary['failed' if row['status'] == 'failed' else 'completed'] += 1
                summary['pending'] -= 1
                _write(out_root / 'summary.json', summary)
                print(f"{row['run']}: {row['status']} ({summary['completed']}/{len(runs)} complete)", flush=True)
        return summary
