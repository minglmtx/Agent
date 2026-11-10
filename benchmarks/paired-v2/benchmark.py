"""Frozen 60-task, paired evaluation; no model-score-based retries or selection."""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tarfile
import time
import zipfile

ROOT = Path(__file__).resolve().parent

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic(path, value):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')
    temp.replace(path)


def evaluate(work, task, visible_zip, local):
    directory = local / 'evaluation'
    directory.mkdir()
    solution = work / task['solution']
    if not solution.is_file() or solution.is_symlink():
        return dict(passed=False, status='missing_or_symlink_solution')
    shutil.copyfile(solution, directory / task['solution'])
    with zipfile.ZipFile(visible_zip) as archive:
        for name in task['tests']:
            (directory / name).write_bytes(archive.read(task['slug'] + '/' + name))
    try:
        p = subprocess.run([sys.executable, str(ROOT / 'evaluate_child.py'), str(directory)],
                           capture_output=True, text=True, timeout=30)
        (local / 'evaluation.stdout').write_text(p.stdout)
        (local / 'evaluation.stderr').write_text(p.stderr)
        result = json.loads(p.stdout.splitlines()[-1]) if p.returncode == 0 else {}
        if task.get('expected_tests') is not None and result.get('tests') != task['expected_tests']:
            result['successful'] = False
            result['test_count_mismatch'] = True
        result.update(status='evaluated' if result else 'evaluator_error', returncode=p.returncode,
                      passed=bool(result.get('successful') and result.get('tests', 0) and result.get('skipped') == 0))
        return result
    except subprocess.TimeoutExpired:
        return dict(passed=False, status='evaluation_timeout')


def run_one(task, variant, settings, index):
    run_id = f"{index:03d}-{variant}-{task['slug']}"
    persistent = Path(settings['output'])
    receipt = persistent / (run_id + '.json')
    if receipt.exists():
        raise RuntimeError(f'refuse automatic repeat of existing run: {run_id}')
    local = Path(settings['temporary']) / run_id
    local.mkdir()
    work = local / 'workspace'
    work.mkdir()
    before = {}
    with zipfile.ZipFile(settings['visible_zip']) as archive:
        prefix = task['slug'] + '/'
        for name in archive.namelist():
            if name.startswith(prefix) and not name.endswith('/'):
                relative = Path(name[len(prefix):])
                if relative.is_absolute() or '..' in relative.parts:
                    raise ValueError('unsafe archive member')
                target = work / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(name))
                before[str(relative)] = sha(target)
    prompt = (work / 'TASK.txt').read_text()
    config = dict(task=task['id'], variant=variant, source_python=settings[variant],
                  workspace=str(work), output=str(local), tokenizer=settings['model'],
                  endpoint=settings['endpoint'], prompt=prompt)
    (local / 'config.json').write_text(json.dumps(config))
    result = dict(run_id=run_id, task=task['id'], slug=task['slug'], band=task['band'], variant=variant,
                  status='started', started=time.time(), job=os.environ.get('SLURM_JOB_ID'))
    atomic(receipt, result)
    started = time.monotonic()
    try:
        with (local / 'agent.log').open('w') as log:
            p = subprocess.Popen([sys.executable, str(ROOT / 'worker.py'), str(local / 'config.json')],
                                 stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                returncode = p.wait(timeout=600)
                status = 'returned'
            except subprocess.TimeoutExpired:
                os.killpg(p.pid, signal.SIGTERM)
                try: p.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    os.killpg(p.pid, signal.SIGKILL)
                    p.wait()
                returncode, status = p.returncode, 'worker_timeout'
        elapsed = time.monotonic()-started
        changed = []
        for name, digest in before.items():
            target = work / name
            if name != task['solution'] and (not target.is_file() or target.is_symlink() or sha(target) != digest):
                changed.append(name)
        extra = sorted(str(p.relative_to(work)) for p in work.rglob('*') if p.is_file() and str(p.relative_to(work)) not in before
                       and '__pycache__' not in p.parts)
        evaluation = evaluate(work, task, settings['visible_zip'], local)
        metadata_path = local / 'model.json'
        metadata = json.loads(metadata_path.read_text()) if metadata_path.exists() else {}
        ledger_path = local / 'requests.jsonl'
        ledger = [json.loads(s) for s in ledger_path.read_text().splitlines()] if ledger_path.exists() else []
        usage = [r['usage'] for r in ledger if r.get('usage')]
        tool_path = local / 'tools.jsonl'
        tool_rows = [json.loads(s) for s in tool_path.read_text().splitlines()] if tool_path.exists() else []
        result.update(status=status, returncode=returncode, agent_seconds=elapsed, model=metadata,
                      evaluation=evaluation, protected_files_changed=changed, extra_files=extra,
                      passed=bool(evaluation['passed'] and not changed and not extra),
                      agent_completed=(returncode == 0 and metadata.get('status') == 'returned'),
                      model_requests=sum(r['event'] == 'dispatch' for r in ledger),
                      summary_requests=sum(r['event'] == 'dispatch' and not r['request'].get('stream') for r in ledger),
                      request_errors=sum(r['event'] in ('error', 'unknown') for r in ledger),
                      prompt_tokens=sum(u['prompt_tokens'] for u in usage),
                      completion_tokens=sum(u['completion_tokens'] for u in usage),
                      tool_calls=sum(r['event'] == 'start' for r in tool_rows))
    except BaseException as exc:
        import traceback
        result.update(status='harness_error', error=repr(exc), traceback=traceback.format_exc(), passed=False)
    finally:
        result['total_seconds'] = time.monotonic()-started
        atomic(local / 'result.json', result)
        archive = persistent / (run_id + '.tar.gz')
        with tarfile.open(str(archive) + '.part', 'w:gz') as tar:
            tar.add(local, arcname=run_id, recursive=True)
        Path(str(archive) + '.part').replace(archive)
        result['archive_sha256'] = sha(archive)
        atomic(receipt, result)
        shutil.rmtree(local)
    print(json.dumps({k: result.get(k) for k in ('run_id', 'status', 'passed', 'agent_seconds', 'prompt_tokens', 'completion_tokens')}), flush=True)
    return result


def aggregate(rows):
    result = {'runs': len(rows), 'variants': {}, 'paired': {}, 'paid_api_calls': 0}
    import statistics
    for variant in ('baseline', 'modified'):
        group = [r for r in rows if r['variant'] == variant]
        result['variants'][variant] = dict(n=len(group), passed=sum(bool(r.get('passed')) for r in group),
            input_tokens=sum(r.get('prompt_tokens', 0) for r in group), output_tokens=sum(r.get('completion_tokens', 0) for r in group),
            median_seconds=statistics.median(r.get('agent_seconds', 0) for r in group) if group else None,
            compaction_events=sum(len(r.get('model', {}).get('compaction_events', [])) for r in group),
            summary_requests=sum(r.get('summary_requests', 0) for r in group),
            request_errors=sum(r.get('request_errors', 0) for r in group),
            worker_errors=sum(r.get('returncode', -1) != 0 for r in group))
    grouped = {}
    for row in rows:
        grouped.setdefault(row['task'], {})[row['variant']] = row.get('passed', False)
    result['paired'] = dict(both_pass=0, baseline_only=0, modified_only=0, both_fail=0, incomplete=0)
    for pair in grouped.values():
        if len(pair) != 2:
            key = 'incomplete'
        elif pair['baseline'] and pair['modified']:
            key = 'both_pass'
        elif pair['baseline']:
            key = 'baseline_only'
        elif pair['modified']:
            key = 'modified_only'
        else:
            key = 'both_fail'
        result['paired'][key] += 1
    return result


def main(settings):
    output = Path(settings['output'])
    output.mkdir(exist_ok=False)
    tasks = json.loads(Path(settings['manifest']).read_text())['tasks']
    fixtures = json.loads(Path(settings['manifest']).with_name('fixture-validation.json').read_text())
    expected = {r['id']: r['reference']['tests'] for r in fixtures['rows']}
    for task in tasks:
        task['expected_tests'] = expected[task['id']]
    # Fixed round-robin difficulty order; alternate which variant starts each pair.
    bands = [[t for t in tasks if t['band'] == b] for b in ('easy', 'medium', 'hard')]
    ordered = [band[i] for i in range(max(map(len, bands))) for band in bands if i < len(band)]
    schedule = [(task, variant, settings, 2*i+j) for i, task in enumerate(ordered)
                for j, variant in enumerate(('baseline', 'modified') if i % 2 == 0 else ('modified', 'baseline'))]
    atomic(output / 'schedule.json', [{'index': i, 'task': t['id'], 'variant': v} for t, v, _, i in schedule])
    rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        pending = [executor.submit(run_one, *args) for args in schedule]
        for future in concurrent.futures.as_completed(pending):
            rows.append(future.result())
            atomic(output / 'summary.json', aggregate(rows))
    atomic(output / 'summary.json', aggregate(rows))
    return 0 if len(rows) == 120 else 2

if __name__ == '__main__':
    raise SystemExit(main(json.loads(Path(sys.argv[1]).read_text())))
