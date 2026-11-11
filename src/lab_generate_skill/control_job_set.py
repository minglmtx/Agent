"""Join exact CPU-control job attestations without changing the one-job gate."""
import re

TERMINAL = frozenset({
    'COMPLETED', 'FAILED', 'CANCELLED', 'TIMEOUT', 'OUT_OF_MEMORY',
    'NODE_FAIL', 'PREEMPTED',
})
_JOB = re.compile(r'[1-9][0-9]*(?:_(?:0|[1-9][0-9]*))?')


def control_job_ids(value):
    """Accept one exact ID or a comma-separated, nonoverlapping set of IDs."""
    if not isinstance(value, str) or not value:
        raise ValueError('Exact control job IDs required')
    jobs = tuple(value.split(','))
    if any(_JOB.fullmatch(job) is None for job in jobs):
        raise ValueError('Use exact Slurm job IDs, separated by commas')
    if len(set(jobs)) != len(jobs):
        raise ValueError('Duplicate control job IDs')
    roots = {job for job in jobs if '_' not in job}
    if any(job.split('_')[0] in roots for job in jobs if '_' in job):
        raise ValueError('Do not count an array root and its child twice')
    return jobs


def terminal_control_states(value, terminal_query):
    """Query every job through the existing authoritative terminal check.

    The caller supplies the existing terminal_jobs function, which checks both
    sacct and a successful complete user squeue snapshot. Missing, live or
    unavailable state remains an error; this helper never substitutes a lock,
    receipt, cached state, successful sibling, or presumed job completion.
    """
    jobs = control_job_ids(value)
    result = {}
    for job in jobs:
        states = terminal_query(job)
        if not isinstance(states, dict) or not states:
            raise ValueError('Missing authoritative control job state: ' + job)
        for exact, state in states.items():
            if not isinstance(exact, str) or not (exact == job or exact.startswith(job + '_')):
                raise ValueError('Control state belongs to a different job')
            if state not in TERMINAL:
                raise ValueError('Control job is not terminal: ' + job)
            if exact in result and result[exact] != state:
                raise ValueError('Contradictory control job state')
            result[exact] = state
    return result
