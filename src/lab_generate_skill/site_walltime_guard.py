"""Source-level allocation budget; no actor strategy or automatic resubmission.

Slurm documents SLURM_JOB_END_TIME/START_TIME as UNIX seconds:
https://slurm.schedmd.com/sbatch.html#SECTION_OUTPUT-ENVIRONMENT-VARIABLES
An optional explicit budget needs its original start anchor. A duration alone
is never mistaken for remaining time. No scheduler RPC or model call is made.
"""
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
import time

VERSION = 'site-source-walltime-v1'
_DEADLINE_KEYS = ('SLURM_JOB_END_TIME', 'LAB_JOB_DEADLINE_UNIX_SECONDS')
_DURATION_KEY = 'LAB_JOB_BUDGET_SECONDS'
_ANCHOR_KEY = 'LAB_JOB_BUDGET_STARTED_UNIX_SECONDS'
_MAX_EPOCH_SECONDS = 10_000_000_000


def _positive_seconds(value, *, epoch=False):
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError('Explicit integer seconds required')
    raw = str(value)
    if not re.fullmatch(r'[1-9][0-9]*', raw):
        raise ValueError('Explicit positive integer seconds required')
    result = int(raw)
    if epoch and result >= _MAX_EPOCH_SECONDS:
        raise ValueError('Deadline must use UNIX seconds, not milliseconds')
    return result


@dataclass(frozen=True)
class SourceBudget:
    # This is the existing whole-attempt bound, including website startup,
    # native references, initial model loading and the bounded rollout.
    attempt_seconds: int
    cleanup_seconds: int = 120
    safety_seconds: int = 60

    def __post_init__(self):
        if any(type(v) is not int or v < 0 for v in
               (self.attempt_seconds, self.cleanup_seconds, self.safety_seconds)) or self.attempt_seconds == 0:
            raise ValueError('Finite integer attempt/cleanup/safety seconds required')

    @property
    def required_seconds(self):
        return self.attempt_seconds + self.cleanup_seconds + self.safety_seconds

    def record(self):
        return {'attempt_seconds_including_startup_and_model': self.attempt_seconds,
                'cleanup_seconds': self.cleanup_seconds, 'safety_seconds': self.safety_seconds,
                'required_seconds': self.required_seconds,
                'model_load_already_inside_attempt_deadline': True}


def configure_rollout_limits(browser, *, max_steps=None, rollout_timeout_seconds=360):
    """Keep configured steps unless explicitly overridden, with a finite clock.

    These are common runner limits, independent of task semantics or evaluator
    results. Increasing rollout time must also increase the pre-claim allocation
    reserve and the outer attempt deadline through ``source_budget``.
    """
    if max_steps is not None and (type(max_steps) is not int or max_steps <= 0):
        raise ValueError('Positive integer max_steps override required')
    if type(rollout_timeout_seconds) is not int or rollout_timeout_seconds <= 0:
        raise ValueError('Positive integer rollout timeout required')
    if max_steps is not None:
        browser.max_steps = max_steps
    return rollout_timeout_seconds


def source_budget(domain, *, rollout_timeout_seconds=360):
    if domain not in ('gitlab', 'shopping', 'reddit', 'map'):
        raise ValueError('Known site runtime domain required')
    if type(rollout_timeout_seconds) is not int or rollout_timeout_seconds <= 0:
        raise ValueError('Positive integer rollout timeout required')
    # Keep the established startup, reference and first-model-load allowance.
    # A longer inner rollout cannot remain bounded by an unchanged outer clock.
    extension = max(0, rollout_timeout_seconds - 360)
    return SourceBudget((2700 if domain == 'map' else 1500) + extension)


def validate_submission_budget(domain, allocation_seconds, *, preparation_seconds=120,
                               expected_prefix_seconds=0, rollout_timeout_seconds=360):
    """Reject allocations that cannot reach the unchanged per-source guard.

expected_prefix_seconds is the estimated work before the last source starts;
this check is not a performance prediction and never enlarges runtime limits.
"""
    for value in (allocation_seconds, preparation_seconds, expected_prefix_seconds):
        if type(value) is not int or value < 0:
            raise ValueError('Submission stage budgets must be nonnegative integer seconds')
    budget = source_budget(domain, rollout_timeout_seconds=rollout_timeout_seconds)
    required = preparation_seconds + expected_prefix_seconds + budget.required_seconds
    if allocation_seconds < required:
        raise ValueError(f'Allocation {allocation_seconds}s cannot cover preparation/prefix and '
                         f'the unchanged {domain} source reserve ({required}s required)')
    return dict(allocation_seconds=allocation_seconds, minimum_seconds=required,
                preparation_seconds=preparation_seconds, expected_prefix_seconds=expected_prefix_seconds,
                source_reserve=budget.record(), per_source_deadline_changed=False)


def walltime_policy(domain):
    return {'version': VERSION, 'source_budget': source_budget(domain).record(),
            'check_before_source_attempt_claim': True,
            'deadline_sources': [*_DEADLINE_KEYS, _DURATION_KEY + '+' + _ANCHOR_KEY],
            'unknown_or_malformed_deadline': 'save_untouched_remaining_without_starting',
            'automatic_requeue': False, 'automatic_retry': False}


class WalltimeGuard:
    def __init__(self, *, environ=None, now=None, monotonic=None):
        self.environ = os.environ if environ is None else environ
        self.now = time.time if now is None else now
        self.monotonic = time.monotonic if monotonic is None else monotonic
        self.first_wall = self.now()
        self.first_monotonic = self.monotonic()
        self.earliest_deadline = None

    def _deadline(self, observed):
        candidates = []; invalid = []
        for key in _DEADLINE_KEYS:
            if key in self.environ:
                try: candidates.append((key, _positive_seconds(self.environ[key], epoch=True)))
                except ValueError: invalid.append(key)
        has_duration = _DURATION_KEY in self.environ
        has_anchor = _ANCHOR_KEY in self.environ
        if has_duration or has_anchor:
            if not (has_duration and has_anchor):
                invalid.append('explicit_budget_missing_original_start_or_duration')
            else:
                try:
                    duration = _positive_seconds(self.environ[_DURATION_KEY])
                    anchor = _positive_seconds(self.environ[_ANCHOR_KEY], epoch=True)
                    end = anchor + duration
                    if anchor > observed or end >= _MAX_EPOCH_SECONDS:
                        raise ValueError('Invalid explicit original start/deadline')
                    candidates.append(('explicit_budget_from_original_start', end))
                except ValueError: invalid.append('explicit_budget_invalid_seconds_or_start')
        # Do not hide malformed allocation evidence behind a looser fallback.
        if invalid: return None, [], invalid
        if not candidates: return None, [], []
        deadline = min(value for _, value in candidates)
        if self.earliest_deadline is not None:
            deadline = min(deadline, self.earliest_deadline)
        self.earliest_deadline = deadline
        return deadline, [key for key, _ in candidates], []

    def check(self, budget):
        if not isinstance(budget, SourceBudget):
            raise ValueError('Explicit bounded source profile required')
        observed = self.now(); mono = self.monotonic()
        base = {'version': VERSION, 'allowed': False, 'required_seconds': budget.required_seconds,
                'budget': budget.record(), 'remaining_seconds': None, 'deadline_unix_seconds': None,
                'deadline_sources': [], 'invalid_deadline_inputs': [], 'observed_unix_seconds': observed if isinstance(observed,(int,float)) and not isinstance(observed,bool) and math.isfinite(observed) else None}
        clocks = (observed, mono, self.first_wall, self.first_monotonic)
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in clocks) or mono < self.first_monotonic:
            return {**base, 'reason': 'invalid_runtime_clock', 'status': 'stopped_deadline_unavailable'}
        deadline, sources, invalid = self._deadline(observed)
        if deadline is None:
            return {**base, 'reason': 'malformed_deadline' if invalid else 'deadline_unavailable',
                    'invalid_deadline_inputs': invalid, 'status': 'stopped_deadline_unavailable'}
        # A backwards wall-clock adjustment cannot create more allocation time.
        conservative_now = max(observed, self.first_wall + mono - self.first_monotonic)
        remaining = max(0.0, deadline - conservative_now)
        allowed = remaining >= budget.required_seconds
        return {**base, 'allowed': allowed, 'remaining_seconds': remaining,
                'deadline_unix_seconds': deadline, 'deadline_sources': sources,
                'reason': 'sufficient_allocation_time' if allowed else 'insufficient_allocation_time',
                'status': 'can_start_source' if allowed else 'stopped_walltime'}


def _descriptor(row):
    task = row.get('task_id'); source = row.get('source_task_id', task)
    for value in (task, source):
        if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,256}', value) or value in ('.', '..'):
            raise ValueError('Local immutable task/source ID required')
    return {'task_id': task, 'source_task_id': source, 'domain': row.get('domain')}


def source_evidence_state(directory):
    """Even zero-byte/partial generation or old claims are never untouched."""
    directory = Path(directory)
    if not directory.exists(): return 'untouched'
    if not directory.is_dir() or directory.is_symlink(): return 'started_not_completed'
    result = directory / 'result.json'
    if result.is_file():
        try:
            value = json.loads(result.read_text())
            if (isinstance(value, dict) and isinstance(value.get('task_id'),str)
                and isinstance(value.get('evaluation'),dict) and value['evaluation'].get('status')in ('success','failure','unknown')):
                return 'existing_completed'
        except (OSError, ValueError): pass
    return 'started_not_completed' if any(directory.iterdir()) else 'untouched'


def remaining_snapshot(rows, output, completed):
    output = Path(output); seen = set(); snapshot = {'untouched_remaining': [],
        'started_not_completed': [], 'existing_completed': [], 'completed_results': deepcopy(completed)}
    completed_by_id = {r['task_id']: r for r in completed}
    if len(completed_by_id)!=len(completed):raise ValueError('Duplicate completed source records')
    for row in rows:
        desc = _descriptor(row); task = desc['task_id']
        if task in seen: raise ValueError('Duplicate task in walltime source scope')
        seen.add(task); folder = output / task
        state = source_evidence_state(folder)
        if task in completed_by_id:
            state = 'existing_completed'
        record = dict(desc, output_directory=str(folder.resolve()))
        if state == 'existing_completed' and (folder / 'result.json').is_file():
            result = folder / 'result.json'
            record['result_file'] = str(result.resolve())
            record['result_sha256'] = hashlib.sha256(result.read_bytes()).hexdigest()
        elif state == 'started_not_completed' and folder.is_dir() and not folder.is_symlink():
            record['evidence_names'] = sorted(p.name for p in folder.iterdir())
        snapshot[state if state != 'untouched' else 'untouched_remaining'].append(record)
    if set(completed_by_id) - seen:
        raise ValueError('Completed result outside the immutable source scope')
    return snapshot


def save_walltime_checkpoint(output, rows, completed, decision, *, manifest=None):
    if decision.get('version') != VERSION or decision.get('allowed') is not False or decision.get('status') not in ('stopped_walltime', 'stopped_deadline_unavailable'):
        raise ValueError('Only a real negative walltime decision can stop the worker')
    output = Path(output); snapshot = remaining_snapshot(rows, output, completed)
    state = {'version': VERSION, 'status': decision['status'], 'decision': deepcopy(decision), **snapshot,
             'automatic_requeue': False, 'automatic_retry': False,
             'existing_results_rewritten': False, 'source_attempts_started_by_guard': 0}
    if manifest is not None:
        manifest = Path(manifest)
        state['original_manifest'] = {'path': str(manifest.resolve()),
                                      'sha256': hashlib.sha256(manifest.read_bytes()).hexdigest()}
    output.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.walltime-pending-', dir=output)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(state, stream, indent=2, ensure_ascii=False, allow_nan=False); stream.write('\n')
            stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, output / 'walltime-pending.json')
    finally:
        if os.path.exists(temporary): os.unlink(temporary)
    return state


def validate_stopped_wave(checkpoint, expected_tasks, results, manifest):
    """A deliberate budget stop is not a silently completed model wave."""
    if (checkpoint.get('version') != VERSION or checkpoint.get('status') not in
        ('stopped_walltime', 'stopped_deadline_unavailable') or checkpoint.get('decision', {}).get('allowed') is not False
        or checkpoint.get('automatic_retry') is not False or checkpoint.get('source_attempts_started_by_guard') != 0):
        raise ValueError('Explicit source-level budget-stop proof required')
    groups = ('untouched_remaining', 'started_not_completed', 'existing_completed')
    descriptors = [r for key in groups for r in checkpoint.get(key, [])]
    ids = [r['task_id'] for r in descriptors]
    if len(ids) != len(set(ids)) or set(ids) != set(expected_tasks):
        raise ValueError('Stopped wave omitted, duplicated or changed original tasks')
    if checkpoint.get('completed_results') != results or {r['task_id'] for r in results} - {
            r['task_id'] for r in checkpoint.get('existing_completed', [])}:
        raise ValueError('Saved completed results differ from actual runner results')
    original = checkpoint.get('original_manifest', {})
    manifest = Path(manifest)
    if original != {'path': str(manifest.resolve()), 'sha256': hashlib.sha256(manifest.read_bytes()).hexdigest()}:
        raise ValueError('Original manifest changed before budget-stop checkpoint')


def bundle_remaining(plan, current_index, current_checkpoint):
    """Include later waves without assuming old raw artifacts are untouched."""
    result = {key: deepcopy(current_checkpoint[key]) for key in
              ('untouched_remaining', 'started_not_completed', 'existing_completed')}
    current_wave = plan['waves'][current_index]['wave']
    for records in result.values():
        for record in records: record['wave'] = current_wave
    manifests = []
    for record in plan['waves'][current_index + 1:]:
        manifest = Path(record['manifest'])
        rows = [json.loads(line) for line in manifest.read_text().splitlines() if line.strip()]
        if (record.get('manifest_sha256')!=hashlib.sha256(manifest.read_bytes()).hexdigest()
            or {(row['task_id'],row.get('source_task_id',row['task_id'])) for row in rows} !=
               {(p['task_id'],p['source_task_id']) for p in record['proofs']}):
            raise ValueError('Later bundle manifest no longer matches original proofs')
        snapshot = remaining_snapshot(rows, Path(record['wave']) / 'actor/0', [])
        for key in result:
            result[key].extend(dict(item, wave=record['wave']) for item in snapshot[key])
        manifests.append({'path': str(manifest.resolve()), 'sha256': hashlib.sha256(manifest.read_bytes()).hexdigest()})
    return {**result, 'later_original_manifests': manifests, 'automatic_retry': False, 'automatic_requeue': False}
