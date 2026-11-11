"""Bounded native service readiness checks; a probe timeout is not a service crash."""
import subprocess
import time


def wait_for_command(command, *, service_running, total_timeout=120,
                     probe_timeout=10, poll_interval=1, record=None):
    if min(total_timeout, probe_timeout, poll_interval) <= 0:
        raise ValueError('Readiness deadlines and poll interval must be positive')
    started = time.monotonic()
    deadline = started + total_timeout
    attempt = 0
    while True:
        if not service_running():
            raise RuntimeError('Service exited during readiness checks; inspect service logs')
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('Service readiness exceeded its total deadline')
        attempt += 1
        probe_started = time.monotonic()
        try:
            result = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    timeout=min(probe_timeout, remaining))
            status = 'ready' if result.returncode == 0 else 'not_ready'
            code = result.returncode
        except subprocess.TimeoutExpired:
            status, code = 'probe_timeout', None
        if record is not None:
            record({'attempt': attempt, 'status': status, 'returncode': code,
                    'probe_seconds': time.monotonic() - probe_started,
                    'elapsed_seconds': time.monotonic() - started})
        if not service_running():
            raise RuntimeError('Service exited during readiness checks; inspect service logs')
        if code == 0:
            if time.monotonic() > deadline:
                raise TimeoutError('Service readiness exceeded its total deadline')
            return
        # pg_isready: 1 rejecting connections, 2 no response, 3 invalid invocation.
        # Do not conceal a broken command as a transient startup delay.
        if code not in (None, 1, 2):
            raise RuntimeError(f'Readiness command failed with exit code {code}')
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('Service readiness exceeded its total deadline')
        time.sleep(min(poll_interval, remaining))
