"""Out-of-process deadlines: browser/model stalls cannot block the supervisor."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import signal
import subprocess
import time
import uuid

_STACK = []


def _atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.' + str(os.getpid()) + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    tmp.replace(path)


def require_watchdog():
    if not os.environ.get('LAB_RUNTIME_WATCHDOG_STATE'):
        raise RuntimeError('Run through run_guarded_runtime.py; an external watchdog is required')


def _publish():
    path = os.environ.get('LAB_RUNTIME_WATCHDOG_STATE')
    if not path:
        return
    if _STACK:
        active = min(_STACK, key=lambda row: row['deadline'])
        value = {**active, 'stages': [row['stage'] for row in _STACK]}
    else:
        value = {'stage': 'between_tasks', 'deadline': time.monotonic() + 120}
    _atomic(path, {**value, 'run_id': os.environ['LAB_RUNTIME_WATCHDOG_RUN_ID'], 'pid': os.getpid()})


@contextmanager
def deadline_scope(stage, seconds, *, result_path=None, task_id=None):
    require_watchdog()
    if seconds <= 0:
        raise ValueError('Deadline must be positive')
    if task_id is None:
        task_id=next((r.get('task_id') for r in reversed(_STACK) if r.get('task_id')),None)
    if result_path is None:
        # A nested model/browser phase belongs to the same task. Preserve its
        # result destination so a hard timeout cannot leave only a worker log.
        result_path=next((r.get('result_path') for r in reversed(_STACK)
                          if r.get('result_path') and r.get('task_id') == task_id),None)
    phase_started = time.monotonic()
    row = {'stage': stage, 'started_monotonic': phase_started, 'deadline': phase_started + seconds,
           'timeout_seconds': seconds, 'task_id': task_id,
           'result_path': str(result_path) if result_path else None}
    _STACK.append(row)
    _publish()
    try:
        yield
    finally:
        _STACK.pop()
        _publish()


def _stop_group(process, grace_seconds):
    # The child is always launched as a new session/process-group leader.
    # Kill the group even if its leader exits before its browser descendants.
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    end = time.monotonic() + grace_seconds
    while time.monotonic() < end:
        process.poll()
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            break
        time.sleep(min(.1, max(0, end - time.monotonic())))
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=10)


def run_guarded(command, *, state_path, timeout_seconds, env=None, stdout=None,
                result_path=None, task_id=None, cpu=False, grace_seconds=5, poll_seconds=.2):
    """Return command's exit code, or 124 on an independently enforced deadline."""
    if timeout_seconds <= 0:
        raise ValueError('Deadline must be positive')
    state_path = Path(state_path).resolve()
    run_id = uuid.uuid4().hex
    child_env = {**(os.environ if env is None else env),
                 'LAB_RUNTIME_WATCHDOG_STATE': str(state_path),
                 'LAB_RUNTIME_WATCHDOG_RUN_ID': run_id}
    started = time.monotonic()
    bootstrap = {'stage': 'cpu_control' if cpu else 'worker_startup',
                 'started_monotonic': started, 'deadline': started + timeout_seconds, 'timeout_seconds': timeout_seconds,
                 'result_path': str(result_path) if result_path else None, 'task_id': task_id}
    process = subprocess.Popen(command, env=child_env, stdout=stdout,
                               stderr=subprocess.STDOUT, start_new_session=True)
    active = bootstrap
    try:
        while process.poll() is None:
            try:
                value = json.loads(state_path.read_text())
                if value.get('run_id') == run_id and value.get('pid') == process.pid:
                    # A CPU control's fixed total limit cannot be extended by phases.
                    active = value if not cpu or value['deadline'] < bootstrap['deadline'] else bootstrap
            except (FileNotFoundError, json.JSONDecodeError):
                pass
            if time.monotonic() >= active['deadline']:
                diagnostic = {'task_id': active.get('task_id'), 'codebase_status': 'runtime_or_contract_error',
                    'error': 'External watchdog deadline exceeded: ' + active['stage'],
                    'evaluation': {'status': 'unknown', 'reward': None},
                    'eligible_training_sample': False, 'api_calls': 0,
                    'watchdog': {**active, 'pid': process.pid, 'elapsed_seconds': time.monotonic() - active.get('started_monotonic', active['deadline']-active.get('timeout_seconds',0)),
                                 'worker_elapsed_seconds': time.monotonic() - started,
                                 'run_id': run_id, 'enforcement': 'independent_process_group_termination'}}
                if cpu:
                    diagnostic.update(passed=False, cycles=[], training_admission=False)
                _atomic(state_path.with_suffix('.timeout.json'), diagnostic)
                _stop_group(process, grace_seconds)
                target = active.get('result_path')
                if target:
                    target = Path(target)
                    if target.exists():
                        _atomic(target.with_name('result-before-watchdog.json'), json.loads(target.read_text()))
                    _atomic(target, diagnostic)
                return 124
            time.sleep(poll_seconds)
        code = process.returncode
        if code:
            diagnostic = {'task_id': active.get('task_id'), 'codebase_status': 'runtime_or_contract_error',
                'error': 'Runtime child exited without completing normally',
                'evaluation': {'status': 'unknown', 'reward': None},
                'eligible_training_sample': False, 'api_calls': 0,
                'exit_code': code, 'signal': -code if code < 0 else None,
                'last_stage': active.get('stage'), 'result_path': active.get('result_path')}
            _atomic(state_path.with_suffix('.exit.json'), diagnostic)
            if active.get('result_path'):
                target = Path(active['result_path'])
                if not target.exists():
                    _atomic(target, diagnostic)
            _stop_group(process, grace_seconds)
        return code
    except BaseException:
        _stop_group(process, grace_seconds)
        raise
