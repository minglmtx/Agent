"""Bounded source preparation with durable, fail-closed process outcomes.

This helper does not retry, infer native success or fabricate missing reviews.
Shared runtime/selection validation stays in prepare.py before this collector.
"""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time
import traceback


def pin(path):
    path = Path(path).resolve()
    return dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def _close_group(child):
    # Each worker owns its session, so timeout cleanup cannot kill siblings.
    signals = []
    for number in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(child.pid, number)
            signals.append(number.name)
        except ProcessLookupError:
            pass
        if number == signal.SIGTERM:
            try:
                child.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                pass
    return dict(signals=signals, returncode=child.wait(timeout=5),
                process_waited=True, owned_process_group=child.pid)


def run_source_process(spec, started):
    """Launch once and return a row even when launch, timeout or review fails."""
    began = time.monotonic()
    source, result_path = spec['source'], Path(spec['review_path'])
    log_path = Path(spec['log_path'])
    row = dict(source_task_id=source['source_task_id'], returncode=None,
               status='unknown', source_passed=False, review=None, output=None,
               error=None, review_error=None, missing_evidence=[],
               process_started=False, process_attempts=0, automatic_retry=False,
               timeout_seconds=spec['timeout_seconds'],
               start_offset_seconds=began-started)
    child = None
    try:
        Path(spec['work_directory']).mkdir(parents=True, exist_ok=False)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open('xb') as stream:
            row['process_attempts'] = 1
            child = subprocess.Popen(spec['command'], env=spec['env'],
                                     cwd=spec['cwd'], stdout=stream,
                                     stderr=subprocess.STDOUT, start_new_session=True)
            row['process_started'] = True
            row['returncode'] = child.wait(timeout=spec['timeout_seconds'])
        if row['returncode'] != 0:
            row['error'] = dict(type='ChildProcessError',
                                message='Binding subprocess exited without success',
                                returncode=row['returncode'])
    except Exception as exc:
        row['error'] = dict(type=type(exc).__name__, message=str(exc),
                            traceback=traceback.format_exc())
        if isinstance(exc, subprocess.TimeoutExpired):
            row['error']['timeout_seconds'] = exc.timeout
        if isinstance(exc, OSError):
            row['error'].update(errno=exc.errno, filename=exc.filename)
        if child is not None:
            try:
                row['termination'] = _close_group(child)
                row['returncode'] = row['termination']['returncode']
            except Exception as close_exc:
                row['termination'] = dict(confirmed=False, error=dict(
                    type=type(close_exc).__name__, message=str(close_exc)))
    # Keep original output and even an unsuccessful/malformed review; never
    # synthesize a binding-review.json for an incomplete subprocess.
    try:
        row['output'] = pin(log_path)
    except OSError as exc:
        row['missing_evidence'].append('process_output')
        row['output_error'] = dict(type=type(exc).__name__, message=str(exc))
    try:
        row['review'] = pin(result_path)
        value = json.loads(result_path.read_text())
        if not isinstance(value, dict):
            raise ValueError('Binding review must be an object')
        if value.get('source') != source or value.get('plan') != spec['plan']:
            raise ValueError('Binding review belongs to another source or plan')
        if value.get('runtime_capsule') != spec['capsule']:
            raise ValueError('Binding review capsule differs from prepared runtime')
        if value.get('passed') is not True:
            raise ValueError('Binding review did not pass')
        if row['error'] is None and row['returncode'] == 0 and not row['missing_evidence']:
            row.update(status='passed', source_passed=True)
    except Exception as exc:
        row['review_error'] = dict(type=type(exc).__name__, message=str(exc),
                                   traceback=traceback.format_exc())
        row['missing_evidence'].append('passed_source_binding')
        if isinstance(exc, FileNotFoundError):
            row['missing_evidence'].append('binding_review_file')
    row['end_offset_seconds'] = time.monotonic()-started
    outcome = Path(spec['outcome_path'])
    try:
        outcome.parent.mkdir(parents=True, exist_ok=True)
        with outcome.open('x') as stream:
            json.dump(row, stream, indent=2)
            stream.write('\n')
        row['process_outcome'] = pin(outcome)
    except Exception as exc:
        # A failed diagnostic write must never turn the source into ready.
        row.update(status='unknown', source_passed=False)
        row['outcome_error'] = dict(type=type(exc).__name__, message=str(exc))
    return row


def collect_sources(specs, *, max_workers=3, started=None):
    started = time.monotonic() if started is None else started
    if max_workers < 1:
        raise ValueError('Positive source process limit required')
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        return list(pool.map(lambda spec: run_source_process(spec, started), specs))


def require_binding_result(proof, source, plan_ref, capsule_ref, read_pin):
    """Common precondition used by both initial and build source gates."""
    if (proof.get('source_task_id') != source['source_task_id']
            or proof.get('status') != 'passed' or proof.get('source_passed') is not True
            or proof.get('returncode') != 0 or proof.get('error') is not None
            or proof.get('review_error') is not None or proof.get('outcome_error') is not None
            or proof.get('missing_evidence') or not proof.get('review')
            or not proof.get('output') or not proof.get('process_outcome')):
        raise ValueError('Source binding is unknown or unsuccessful; initial/build prohibited')
    outcome = read_pin(proof['process_outcome'])
    expected = {key:value for key,value in proof.items() if key != 'process_outcome'}
    if outcome != expected:
        raise ValueError('Source process outcome differs from preparation aggregate')
    if pin(proof['output']['path']) != proof['output']:
        raise ValueError('Source process output changed')
    binding = read_pin(proof['review'])
    if (binding.get('passed') is not True or binding.get('source') != source
            or binding.get('plan') != plan_ref or binding.get('runtime_capsule') != capsule_ref):
        raise ValueError('Source native binding, plan or capsule changed')
    return binding
