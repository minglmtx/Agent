"""Bounded attempt-owned Rails reader; no cached answers or cross-reset reuse."""
from pathlib import Path
import json
import os
import selectors
import shutil
import signal
import subprocess
import tempfile
import time

from .io_utils import atomic_write_json


class ReferenceSession:
    REFERENCE_SOURCE = 'gitlab_subscription_runtime.rb'

    def __init__(self, site, directory, *, startup_seconds=120, request_seconds=45):
        from .runtime_watchdog import require_watchdog
        require_watchdog()
        if site.domain != 'gitlab' or not os.environ.get('SLURM_JOB_ID'):
            raise ValueError('Allocated isolated GitLab required')
        self.site = site
        self.generation = site.generation
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.timeout = request_seconds
        self.sequence = 0
        self.buffer = b''
        self.closed = False
        self.process = None
        self.selector = selectors.DefaultSelector()
        self.temp = tempfile.TemporaryDirectory(prefix='native-feed-session-', dir=site.state)
        self.folder = Path(self.temp.name)
        self.folder.chmod(0o700)
        self.log = (self.directory/'private-reader-process.log').open('wb')
        (self.directory/'private-reader-process.log').chmod(0o600)
        for source, name in [(self.REFERENCE_SOURCE,'reference.rb'),
                             ('gitlab_subscription_session.rb','worker.rb')]:
            shutil.copyfile(Path(__file__).with_name(source), self.folder/name)
        path = '/state/'+self.folder.name
        command = ['bash','/state/service.sh','gitlab-rails','env','RAILS_ENV=production',
                   '/opt/gitlab/embedded/bin/bundle','exec',
                   '/opt/gitlab/embedded/service/gitlab-rails/bin/rails','runner','-e','production',
                   path+'/worker.rb',path]
        self.started = time.monotonic()
        self.readings = []
        try:
            self._operation()
            self.process = subprocess.Popen(site.base+command, stdin=subprocess.PIPE,
                                            stdout=subprocess.PIPE, stderr=self.log, start_new_session=True)
            site.processes.append(self.process)
            self.selector.register(self.process.stdout, selectors.EVENT_READ)
            self._message(b'LAB_FEED_SESSION_READY', startup_seconds, exact=True)
            self.startup_seconds = time.monotonic()-self.started
        except BaseException:
            self.close()
            raise

    def _operation(self):
        if self.closed or self.site.generation != self.generation:
            raise ValueError('Native reader cannot cross an environment reset')
        self.site._operation_serial += 1
        self.site._reset_ticket = None

    def _message(self, prefix, timeout, *, exact=False):
        deadline = time.monotonic()+timeout
        while True:
            while b'\n' in self.buffer:
                line, self.buffer = self.buffer.split(b'\n',1)
                self.log.write(line+b'\n'); self.log.flush()
                if line.startswith(b'LAB_FEED_SESSION_ERROR='):
                    raise ValueError('Native read-only finder failed; inspect private reader log')
                if (line == prefix if exact else line.startswith(prefix)):
                    return None if exact else json.loads(line[len(prefix):])
            remaining = deadline-time.monotonic()
            if remaining <= 0 or not self.selector.select(remaining):
                raise TimeoutError('Native reference reader exceeded its stage budget')
            data = os.read(self.process.stdout.fileno(),65536)
            if not data:
                raise RuntimeError('Native reference reader exited without a complete response')
            self.buffer += data
            if len(self.buffer) > 32*1024*1024:
                raise ValueError('Native reference response exceeds bounded protocol capacity')

    def read(self, request, destination):
        self._operation()
        started = time.monotonic()
        try:
            self.sequence += 1
            path = self.folder/'input.json'
            atomic_write_json(path,request); path.chmod(0o600)
            self.process.stdin.write((json.dumps({'request_id':self.sequence})+'\n').encode())
            self.process.stdin.flush()
            response = self._message(b'LAB_FEED_SESSION_RESULT=',self.timeout)
            if (set(response) != {'request_id','reference'} or response['request_id'] != self.sequence
                    or not isinstance(response['reference'],dict)):
                raise ValueError('Native response is out of sequence or malformed')
            value = response['reference']
            value['seconds'] = time.monotonic()-started
            destination = Path(destination)
            atomic_write_json(destination,value); destination.chmod(0o600)
            self.readings.append({'sequence':self.sequence,'seconds':value['seconds']})
            return value
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.closed:
            return
        self.closed = True
        forced = False
        try:
            if self.process is not None:
                if self.process.stdin is not None:
                    try:self.process.stdin.close()
                    except BrokenPipeError:pass
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    forced = True
                    os.killpg(self.process.pid,signal.SIGTERM)
                    try:self.process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(self.process.pid,signal.SIGKILL)
                        self.process.wait(timeout=5)
                self.process.stdout.close()
        finally:
            self.selector.close()
            self.log.close()
            self.temp.cleanup()
            atomic_write_json(self.directory/'reader-lifecycle.json',{
                'version':'attempt-owned-native-read-session-v1',
                'generation':self.generation,'startup_seconds':getattr(self,'startup_seconds',None),
                'requests':self.readings,'process_exited':self.process is None or self.process.poll() is not None,
                'returncode':None if self.process is None else self.process.returncode,
                'forced_stop':forced,'private_directory_removed':not self.folder.exists(),
                'closed':True,'api_calls':0})

    def __enter__(self):return self
    def __exit__(self,*args):self.close()
