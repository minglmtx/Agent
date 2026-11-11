"""Submit independent stages without waiting; preserve ambiguous submissions.

This only prepares metadata and calls sbatch. Workers retain responsibility for
qualification, input hashes, resource checks, isolated state, and model policy.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _save(path, data):
    fd, tmp = tempfile.mkstemp(prefix='.submission-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _validate_constraint(value):
    """Accept one feature or a bounded homogeneous AND/OR feature list.

    This deliberately excludes Slurm's grouped, counted, and mixed expressions;
    callers must not rely on implicit operator precedence for node selection.
    """
    feature = r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}'
    if (not isinstance(value, str) or len(value) > 512
            or not re.fullmatch(feature + r'(?:&' + feature + r'){0,7}|'
                                + feature + r'(?:\|' + feature + r'){0,7}', value)):
        raise ValueError('Constraint must be a feature or at most 8 features joined only by & or only by |')


def validate_plan(plan):
    if plan.get('version') not in ('stage-submission-v1', 'stage-submission-v2'):
        raise ValueError('Unknown submission plan version')
    rows = plan.get('stages', [])
    if not rows:
        raise ValueError('No stages')
    external = plan.get('external_jobs', {})
    for name, row in external.items():
        if not re.fullmatch(r'[a-z][a-z0-9_-]*', name) or not re.fullmatch(r'[0-9]+', row.get('job_id', '')):
            raise ValueError('Invalid external stage or job id')
        ref = row['submission']
        path = Path(ref['path'])
        if not path.is_absolute() or digest(path) != ref['sha256']:
            raise ValueError('External submission receipt changed')
        receipt = json.loads(path.read_text())
        if str(receipt.get('job_id')) != row['job_id']:
            raise ValueError('External job id differs from its actual submission receipt')
    by_id = {}
    for row in rows:
        name = row['id']
        if not re.fullmatch(r'[a-z][a-z0-9_-]*', name) or name in by_id or name in external:
            raise ValueError('Invalid or repeated stage id')
        by_id[name] = row
        execution = row.get('execution')
        typed = 'execution' in row or plan['version'] == 'stage-submission-v2'
        if typed and execution not in ('cpu', 'gpu'):
            raise ValueError('Declare execution as cpu or gpu')
        pin = row['script']
        path = Path(pin['path'])
        if not path.is_absolute() or digest(path) != pin['sha256']:
            raise ValueError('Batch script changed: ' + name)
        for line in path.read_text().splitlines():
            if re.match(r'^\s*#(?:PBS|BSUB)', line):
                raise ValueError('Compatibility scheduler directives are not supported')
            directive = re.match(r'^\s*#(?:SBATCH|SLURM)(.*)$', line)
            if directive:
                if typed:
                    raise ValueError('Typed stages must declare all scheduler resources in the plan')
                for token in shlex.split(directive.group(1), comments=True):
                    option = token.split('=', 1)[0]
                    if token.startswith('-') and not token.startswith('--'):
                        raise ValueError('Use full long SBATCH options; scheduling belongs in the plan')
                    if option.startswith('--') and any(full.startswith(option) for full in ('--array', '--dependency')):
                        raise ValueError('Array and dependency directives must be declared in the plan')
        for ref in row.get('inputs', []):
            if not Path(ref['path']).is_absolute() or digest(ref['path']) != ref['sha256']:
                raise ValueError('Stage input changed: ' + name)
        if (not isinstance(row.get('args', []), list)
                or not all(isinstance(x, str) and '\x00' not in x for x in row.get('args', []))):
            raise ValueError('Stage arguments must be strings')
        resources = row['resources']
        if typed:
            if set(resources) - {'cpus', 'partition', 'time', 'gres', 'memory', 'exclude', 'constraint'}:
                raise ValueError('Unknown typed resource field')
            if execution == 'cpu' and 'gres' in resources:
                raise ValueError('CPU execution cannot request GRES')
            if execution == 'gpu' and (not isinstance(resources.get('gres'), str)
                    or not re.fullmatch(r'gpu(?::[A-Za-z0-9_.-]+)?:[1-9][0-9]*', resources['gres'])):
                raise ValueError('GPU execution requires explicit gpu[:type]:count GRES')
        if 'constraint' in resources:
            _validate_constraint(resources['constraint'])
        if (type(resources.get('cpus')) is not int or resources['cpus'] < 1
                or not resources.get('partition') or not resources.get('time')):
            raise ValueError('Explicit CPU, partition, and time limits required')
        isolation = row.get('state_isolation')
        if isolation not in ('read_only', 'single_instance', 'per_array_task'):
            raise ValueError('Declare state isolation')
        array = row.get('array')
        if array is not None:
            ids, limit = array['indices'], array['max_parallel']
            if (not ids or any(type(i) is not int or i < 0 for i in ids)
                    or len(set(ids)) != len(ids) or type(limit) is not int
                    or not 1 <= limit <= len(ids)):
                raise ValueError('Invalid array or concurrency limit')
            if limit > 1 and isolation == 'single_instance':
                raise ValueError('Concurrent array cannot share a writable instance')
        if isolation != 'read_only' and not row.get('exclusive_scopes'):
            raise ValueError('Declare writable state scopes')
        scopes = row.get('exclusive_scopes', [])
        if (not isinstance(scopes, list) or any(not isinstance(s, str) or not s for s in scopes)
                or len(set(scopes)) != len(scopes)):
            raise ValueError('Repeated state scope')
    for row in rows:
        dependencies = row.get('after', [])
        if not isinstance(dependencies, list):
            raise ValueError('Stage dependencies must be a list')
        targets = set()
        parent_kinds = {}
        for dep in dependencies:
            if (not isinstance(dep, dict) or set(dep) - {'stage', 'condition', 'array_index'}
                    or not isinstance(dep.get('stage'), str)
                    or dep.get('stage') not in by_id and dep.get('stage') not in external
                    or dep.get('condition') not in ('afterok', 'afterany')):
                raise ValueError('Unknown dependency or condition')
            parent = dep['stage']
            element = 'array_index' in dep
            if element:
                array = by_id.get(parent, {}).get('array')
                index = dep['array_index']
                if array is None or type(index) is not int or index not in array['indices']:
                    raise ValueError('Array element dependency requires a declared predecessor index')
            target = (parent, dep.get('array_index'))
            if target in targets or parent in parent_kinds and parent_kinds[parent] != element:
                raise ValueError('Duplicate or conflicting stage dependency')
            targets.add(target)
            parent_kinds[parent] = element
    pending = dict(by_id)
    # A known parent job id is enough to submit its dependents, but an element
    # dependency does not prove that the entire parent array has finished.
    ordered, completed_ancestors = [], {name: set() for name in external}
    while pending:
        ready = []
        for name, row in pending.items():
            dependencies = row.get('after', [])
            if all(dep['stage'] in completed_ancestors for dep in dependencies):
                ready.append(name)
        if not ready:
            raise ValueError('Cyclic stage dependencies')
        for name in ready:
            row = pending.pop(name)
            dependencies = row.get('after', [])
            whole_parents = {dep['stage'] for dep in dependencies if 'array_index' not in dep}
            completed_ancestors[name] = whole_parents | set().union(
                *(completed_ancestors[dep['stage']] for dep in dependencies))
            ordered.append(row)
    for i, row in enumerate(ordered):
        scopes = set(row.get('exclusive_scopes', []))
        for other in ordered[i + 1:]:
            if scopes.intersection(other.get('exclusive_scopes', [])):
                if row['id'] not in completed_ancestors[other['id']]:
                    raise ValueError('Independent stages share writable state')
    return ordered


def sbatch_command(stage, submitted):
    resources = stage['resources']
    args = ['sbatch', '--parsable', '--export=NONE', '--kill-on-invalid-dep=yes',
            '--job-name=' + stage['id'], '--partition=' + resources['partition'],
            '--cpus-per-task=' + str(resources['cpus']), '--time=' + resources['time']]
    for field, option in [('gres', 'gres'), ('memory', 'mem'), ('exclude', 'exclude'),
                          ('constraint', 'constraint')]:
        if resources.get(field):
            args.append('--' + option + '=' + str(resources[field]))
    array = stage.get('array')
    if array:
        args.append('--array=' + ','.join(map(str, array['indices'])) + '%' + str(array['max_parallel']))
    dependencies = [dep['condition'] + ':' + submitted[dep['stage']]['job_id']
                    + ('_' + str(dep['array_index']) if 'array_index' in dep else '')
                    for dep in stage.get('after', [])]
    if dependencies:
        args.append('--dependency=' + ','.join(dependencies))
    if stage.get('output'):
        args.append('--output=' + stage['output'])
    return args + [stage['script']['path'], *stage.get('args', [])]


def submit_plan(plan_path, receipt_path, *, run=subprocess.run):
    """Resume known submissions only; never retry a request with no durable id.

    The small submission calls are sequential, but there is no job-status query
    or execution barrier: independent jobs become runnable immediately. Existing
    receipts are reused even for failed jobs; rebuilding failed work is explicit.
    """
    plan_path, receipt_path = Path(plan_path), Path(receipt_path)
    raw = plan_path.read_bytes()
    plan_hash = hashlib.sha256(raw).hexdigest()
    plan = json.loads(raw)
    ordered = validate_plan(plan)
    external = {name: dict(status='submitted', job_id=row['job_id'])
                for name, row in plan.get('external_jobs', {}).items()}
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    with receipt_path.with_suffix(receipt_path.suffix + '.lock').open('a') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        if receipt_path.exists():
            receipt = json.loads(receipt_path.read_text())
            if receipt['plan_sha256'] != plan_hash:
                raise ValueError('Submission plan differs from existing receipt')
        else:
            receipt = dict(version='stage-submission-receipt-v1', plan=str(plan_path),
                           plan_sha256=plan_hash, stages={}, complete=False,
                           external_jobs=plan.get('external_jobs', {}))
        for stage in ordered:
            name = stage['id']
            previous = receipt['stages'].get(name)
            if previous:
                # An uncertain branch does not prevent independent branches from
                # being submitted, but neither it nor its dependents are retried.
                if previous.get('status') == 'submitted' and not re.fullmatch(r'[0-9]+', previous.get('job_id', '')):
                    raise ValueError('Invalid recorded job id: ' + name)
                continue
            available = {**external, **receipt['stages']}
            if any(available.get(dep['stage'], {}).get('status') != 'submitted'
                   for dep in stage.get('after', [])):
                continue
            command = sbatch_command(stage, available)
            record = dict(status='submitting', command=command)
            receipt['stages'][name] = record
            _save(receipt_path, receipt)
            # A timeout or malformed response may still have created a Slurm job.
            # Preserve the uncertain state rather than silently resubmitting it.
            try:
                # SBATCH_* changes submission options before --export is applied
                # to the job. Only the explicit plan may define scheduling.
                env = {k: v for k, v in os.environ.items() if not k.startswith('SBATCH_')}
                result = run(command, capture_output=True, text=True, timeout=60, check=False, env=env)
                if result.returncode != 0:
                    raise RuntimeError('sbatch failed: ' + result.stderr.strip())
                response = result.stdout.strip()
                if not re.fullmatch(r'[0-9]+(?:;[A-Za-z0-9_.-]+)?', response):
                    raise RuntimeError('Unrecognized sbatch response')
            except Exception as exc:
                record.update(status='uncertain', error=str(exc))
                _save(receipt_path, receipt)
                continue
            record.update(status='submitted', job_id=response.split(';')[0], response=response)
            _save(receipt_path, receipt)
        receipt['complete'] = all(receipt['stages'].get(s['id'], {}).get('status') == 'submitted'
                                  for s in ordered)
        receipt['unsubmitted_stages'] = [s['id'] for s in ordered if s['id'] not in receipt['stages']]
        _save(receipt_path, receipt)
        return receipt
