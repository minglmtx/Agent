"""Bounded private SELECT transport reusing one native read-only psql process.

Queries and fingerprint algorithms remain the caller's. This is never an actor
tool; native statement_timeout remains 20 seconds, as in site_database.
"""
import hashlib
import json
import os
import secrets
import select
import selectors
import signal
import subprocess
import time


class ReadSessionError(RuntimeError):
    def __init__(self, stage, *, code=None, stderr=b''):
        self.record = {'stage': stage, 'returncode': code,
                       'stderr_bytes': len(stderr),
                       'stderr_sha256': hashlib.sha256(stderr).hexdigest()}
        super().__init__('Native read-only database session failed: ' + stage)


class GitlabReadSession:
    """One transaction at READ COMMITTED, one fresh snapshot per SELECT.

The existing per-query transaction also uses READ COMMITTED. Reusing the
connection retains the same query-level visibility and 20-second SQL timeout.
No data, authentication metadata, or database settings are written.
"""
    MAX_REPLY_BYTES = 8 * 1024 * 1024
    MAX_QUERY_BYTES = 64 * 1024
    MAX_STDERR_BYTES = 64 * 1024

    def __init__(self, site, *, response_seconds=40):
        if site.domain != 'gitlab' or not isinstance(site.base, list) or not site.base:
            raise ValueError('Actual GitLab native command prefix required')
        if not 0 < response_seconds <= 40:
            raise ValueError('Native response deadline must not exceed existing 40 seconds')
        self.site = site
        self.response_seconds = response_seconds
        self.process = None
        self.poller = None
        self.stdout = bytearray()
        self.stderr = bytearray()
        self.token = secrets.token_hex(24)
        self.queries = 0
        self.query_seconds = []
        self.closed = False
        self.ready = False

    def _fail(self, stage):
        raise ReadSessionError(stage, code=self.process.poll() if self.process else None,
                               stderr=bytes(self.stderr))

    def _send(self, data, deadline):
        fd = self.process.stdin.fileno()
        while data:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self._fail('request_timeout')
            if self.process.poll() is not None:
                self._fail('process_exited')
            if not select.select([], [fd], [], remaining)[1]:
                self._fail('request_timeout')
            try:
                count = os.write(fd, data)
            except (BrokenPipeError, OSError):
                self._fail('request_pipe_closed')
            data = data[count:]

    def _receive(self, deadline):
        # PostgreSQL json_agg may contain physical newlines between row objects.
        # psql -0 terminates unaligned records with NUL, which JSON cannot contain raw.
        while True:
            if b'\x00' in self.stdout:
                raw, _, extra = self.stdout.partition(b'\x00')
                self.stdout = bytearray(extra)
                if not raw.strip():
                    continue
                try:
                    value = json.loads(raw)
                except (ValueError, UnicodeError):
                    self._fail('invalid_response_json')
                if not isinstance(value, dict) or value.get('token') != self.token:
                    self._fail('response_identity_mismatch')
                return value
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self._fail('response_timeout')
            events = self.poller.select(remaining)
            if not events:
                self._fail('response_timeout')
            for key, _ in events:
                try:
                    chunk = os.read(key.fd, 65536)
                except BlockingIOError:
                    continue
                if not chunk:
                    self.poller.unregister(key.fd)
                    if key.data == 'stdout':
                        self._fail('incomplete_response')
                    continue
                if key.data == 'stdout':
                    self.stdout.extend(chunk)
                    if len(self.stdout) > self.MAX_REPLY_BYTES:
                        self._fail('response_size_exceeded')
                else:
                    self.stderr.extend(chunk)
                    if len(self.stderr) > self.MAX_STDERR_BYTES:
                        self._fail('stderr_size_exceeded')

    def __enter__(self):
        if self.process is not None or self.closed:
            raise ValueError('Read sessions cannot be reused or restarted')
        command = self.site.base + ['/opt/gitlab/embedded/bin/psql',
            '-h', '/var/opt/gitlab/postgresql', '-U', 'gitlab', '-d', 'gitlabhq_production',
            '-X', '-q', '-A', '-t', '-0', '-v', 'ON_ERROR_STOP=1']
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, start_new_session=True)
        self.poller = selectors.DefaultSelector()
        for stream, kind in [(self.process.stdout, 'stdout'), (self.process.stderr, 'stderr')]:
            os.set_blocking(stream.fileno(), False)
            self.poller.register(stream.fileno(), selectors.EVENT_READ, kind)
        os.set_blocking(self.process.stdin.fileno(), False)
        try:
            deadline = time.monotonic() + self.response_seconds
            sql = ("BEGIN READ ONLY;\nSET LOCAL statement_timeout='20s';\n"
                   "SELECT json_build_object('token','" + self.token + "','ready',true);\n")
            self._send(sql.encode(), deadline)
            if self._receive(deadline) != {'token': self.token, 'ready': True}:
                self._fail('invalid_startup_receipt')
            self.ready = True
            return self
        except BaseException:
            self.close(abort=True)
            raise

    def select_rows(self, site, sql):
        if site is not self.site or not self.ready or self.closed:
            raise ValueError('SELECT requires the actual live source-local native session')
        if (not isinstance(sql, str) or not sql.startswith('SELECT ')
                or any(c in sql for c in (';', '\n', '\r', '\\', '\x00'))
                or len(sql.encode()) > self.MAX_QUERY_BYTES):
            raise ValueError('One bounded generated fingerprint SELECT required')
        sequence = self.queries
        query = ("SELECT json_build_object('token','" + self.token + "','sequence',"
                 + str(sequence) + ",'rows',COALESCE(json_agg(q),'[]'::json)) FROM (" + sql + ") q;\n")
        started = time.monotonic()
        try:
            deadline = started + self.response_seconds
            self._send(query.encode(), deadline)
            value = self._receive(deadline)
            if (set(value) != {'token', 'sequence', 'rows'} or type(value['sequence']) is not int
                    or value['sequence'] != sequence or not isinstance(value['rows'], list)
                    or any(not isinstance(row, dict) for row in value['rows'])):
                self._fail('invalid_query_receipt')
            self.queries += 1
            self.query_seconds.append(time.monotonic() - started)
            return value['rows']
        except BaseException:
            self.close(abort=True)
            raise

    def close(self, *, abort=False):
        if self.closed:
            return
        self.closed = True
        if self.process is None:
            return
        original_abort = abort
        cleanup_failed = False
        try:
            if not abort and self.process.poll() is None:
                try:
                    self._send(b'ROLLBACK;\n\\q\n', time.monotonic() + 2)
                    self.process.wait(timeout=2)
                except (ReadSessionError, subprocess.TimeoutExpired):
                    abort = True
                    cleanup_failed = True
            if abort or self.process.poll() is None:
                try:
                    os.killpg(self.process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                self.process.wait(timeout=3)
        finally:
            if self.poller is not None:
                self.poller.close()
            for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
                stream.close()
            self.ready = False
        if not original_abort and cleanup_failed:
            self._fail('transaction_close_timeout')
        if not abort and self.process.returncode != 0:
            self._fail('transaction_close_failed')

    def __exit__(self, kind, error, trace):
        self.close(abort=kind is not None)
