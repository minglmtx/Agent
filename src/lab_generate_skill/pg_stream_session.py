"""One bounded psql process per worker, rather than a container per SQL range."""
import os
import select
import signal
import subprocess
import time
import uuid


class PsqlSession:
    def __init__(self, command, error_log):
        self.errors = open(error_log, 'ab')
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=self.errors,
                                        start_new_session=True, bufsize=0)
        self.pending = b''

    def query(self, sql, timeout=120):
        marker = ('done_' + uuid.uuid4().hex).encode()
        if self.process.poll() is not None:
            raise RuntimeError('Native psql process has exited; inspect its stderr log')
        self.process.stdin.write(sql.encode() + b'\n\\echo ' + marker + b'\n')
        self.process.stdin.flush()
        deadline = time.monotonic() + timeout
        lines = []
        while True:
            while b'\n' in self.pending:
                line, self.pending = self.pending.split(b'\n', 1)
                if line.rstrip(b'\r') == marker:
                    return b'\n'.join(lines).decode().strip()
                lines.append(line)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self.close()
                raise TimeoutError('Native range query exceeded its fixed time budget')
            readable, _, _ = select.select([self.process.stdout], [], [], min(remaining, 1))
            if readable:
                data = os.read(self.process.stdout.fileno(), 65536)
                if not data:
                    raise RuntimeError('Native SQL failed before completion; inspect stderr log')
                self.pending += data

    def close(self):
        if self.process.poll() is None:
            os.killpg(self.process.pid, signal.SIGTERM)
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(timeout=5)
        self.errors.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
