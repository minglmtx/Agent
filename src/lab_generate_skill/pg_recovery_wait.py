"""Bounded PostgreSQL startup with activity evidence, not a silent fixed sleep.

CPU/I/O activity is diagnostic evidence only; readiness must still come from
PostgreSQL. The total budget is never extended by an active process.
"""
import time


def process_activity(pid):
    import psutil
    totals = dict(cpu_seconds=0.0, read_bytes=0, write_bytes=0, process_count=0)
    try:
        parent = psutil.Process(pid)
        processes = [parent, *parent.children(recursive=True)]
    except psutil.NoSuchProcess:
        return totals
    for process in processes:
        try:
            cpu = process.cpu_times()
            io = process.io_counters()
            totals['cpu_seconds'] += cpu.user + cpu.system
            totals['read_bytes'] += io.read_bytes
            totals['write_bytes'] += io.write_bytes
            totals['process_count'] += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return totals


def wait_for_recovery(process, probe, *, stop, report, budget_seconds,
                      idle_seconds=180, activity=None, clock=time.monotonic,
                      sleep=time.sleep, poll_seconds=5):
    if not 1 <= budget_seconds <= 1800 or idle_seconds <= 0 or poll_seconds <= 0:
        raise ValueError('Explicit recovery budget must be between 1 and 1800 seconds')
    activity = activity or (lambda: process_activity(process.pid))
    started = clock(); last_active = started; last_report = float('-inf')
    previous = None; probes = 0
    while True:
        now = clock()
        if stop.is_set():
            raise InterruptedError('PostgreSQL recovery cancelled; original checkpoint retained')
        if process.poll() is not None:
            raise RuntimeError('Recovered PostgreSQL exited before readiness; inspect postgres.log')
        if now - started >= budget_seconds:
            raise TimeoutError(f'PostgreSQL recovery exceeded its {budget_seconds}s total budget')
        current = activity()
        # Polling connections themselves may create transient children. Their
        # count is not recovery progress and must not reset the idle timer.
        signature = tuple(current.get(k, 0) for k in ('cpu_seconds', 'read_bytes', 'write_bytes'))
        if previous is None or signature != previous:
            last_active = now
        previous = signature
        code = probe(); probes += 1
        elapsed = clock() - started
        if elapsed > budget_seconds:
            raise TimeoutError(f'PostgreSQL readiness probe exceeded the {budget_seconds}s total budget')
        row = dict(elapsed_seconds=elapsed, budget_seconds=budget_seconds,
                   idle_seconds=now-last_active, activity=current, readiness_code=code,
                   readiness_probes=probes, process_activity_is_not_recovery_completion=True)
        if code == 0:
            report(dict(row, ready=True))
            return row
        if code not in (1, 2):
            raise RuntimeError(f'Invalid PostgreSQL readiness probe return code: {code}')
        if now - last_active >= idle_seconds:
            report(dict(row, ready=False, stalled=True))
            raise TimeoutError('PostgreSQL recovery has no measured CPU or I/O activity')
        if now - last_report >= 30:
            report(dict(row, ready=False)); last_report = now
        sleep(min(poll_seconds, max(0, budget_seconds-(clock()-started))))
