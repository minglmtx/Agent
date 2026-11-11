"""Worker-local Shopping/Reddit snapshot reuse; no running-DB copies.

Initial extraction/configuration is the installed content adapter. Its actual
native launch commands are captured and replayed after stopped-service restore.
The baseline contains every writable file, not selected protected SQL rows.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

import psutil
from lab_generate_skill.content_site import IsolatedContentSite
from lab_generate_skill.site_state_snapshot import SiteStateSnapshot


class ReusableContentSite(IsolatedContentSite):
    def __init__(self, root, logs, domain, **kwargs):
        super().__init__(root, logs, domain, **kwargs)
        self.reuse_state = True; self.generation = 0; self.events = []
        self.stopped = True; self.known_processes = []; self.recipes = []
        self._record_recipes = True
        self._service_log_append = True

    def event(self, phase, started, **extra):
        row = {'phase': phase, 'generation': self.generation,
               'seconds': time.monotonic() - started, **extra}
        self.events.append(row)
        from .io_utils import append_jsonl
        append_jsonl(self.logs/'snapshot-reuse-events.jsonl',[row],durable=False)
        return row

    def launch(self, name, args, extra=None):
        if self._record_recipes:
            if any(r['name'] == name for r in self.recipes):
                raise ValueError('Duplicate native website startup service')
            self.recipes.append({'name': name, 'args': list(args),
                                 'extra': list(extra) if extra is not None else None})
        super().launch(name, args, extra=extra)
        self.stopped = False

    def __enter__(self):
        entered = super().__enter__()
        try:
            expected = {'postgres','php-fpm','nginx'} if self.domain=='reddit' else {'mysql','redis','elasticsearch','php-fpm','nginx'}
            if entered is not self or {r['name'] for r in self.recipes} != expected:
                raise ValueError('Exact installed native website services required')
            # Installed startup already restores Go-Browse's trusted task user.
            # The configured native cold state is saved only after every DB/web
            # process is stopped. No selected row/function is synthesized.
            self.stop_services()
            self._remove_stopped_native_endpoints()
            self.baseline_temp = tempfile.TemporaryDirectory(prefix=self.domain+'-baseline-', dir=os.environ['TMPDIR'])
            self.snapshot = SiteStateSnapshot(self.state, Path(self.baseline_temp.name) / 'state',
                services_stopped=lambda: self.stopped and not self.live_process_ids(), restore_strategy='clone')
            started = time.monotonic(); saved = self.snapshot.save()
            self.event('baseline_save', started, original_snapshot=saved,
                       full_writable_state=True, running_database_copied=False)
            self._record_recipes = False; self.start_services()
            return self
        except BaseException:
            self.__exit__(None, None, None); raise

    def live_process_ids(self):
        result = []
        tracked = list(self.known_processes)
        for process in self.processes:
            try:
                native = psutil.Process(process.pid)
                tracked.extend(native.children(recursive=True)); tracked.append(native)
            except psutil.NoSuchProcess:
                pass
        for process in tracked:
            try:
                if process.is_running() and process.status() != psutil.STATUS_ZOMBIE:
                    result.append(process.pid)
            except psutil.NoSuchProcess:
                pass
        return sorted(set(result))

    def stop_services(self):
        started = time.monotonic(); tracked = list(self.known_processes)
        for process in self.processes:
            try:
                native = psutil.Process(process.pid)
                tracked.extend(native.children(recursive=True)); tracked.append(native)
            except psutil.NoSuchProcess:
                pass
        for process in reversed(self.processes):
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=15)
                except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=10)
        unique = {p.pid: p for p in tracked}
        alive = []
        for process in unique.values():
            try:
                if process.is_running() and process.status() != psutil.STATUS_ZOMBIE:
                    alive.append(process)
            except psutil.NoSuchProcess:
                pass
        for process in alive:
            try: process.terminate()
            except psutil.NoSuchProcess: pass
        _, alive = psutil.wait_procs(alive, timeout=5)
        for process in alive:
            try: process.kill()
            except psutil.NoSuchProcess: pass
        _, alive = psutil.wait_procs(alive, timeout=5)
        self.known_processes = alive
        if alive:
            self.event('services_stop_failed', started, remaining_process_ids=sorted(p.pid for p in alive))
            raise RuntimeError('Website native descendants remain; refusing state snapshot/restore')
        self.processes = []; self.stopped = True
        for handle in self.handles: handle.close()
        self.handles = []
        self.event('services_stop', started, remaining_process_ids=[])

    def start_services(self):
        if not self.stopped or self.live_process_ids():
            raise RuntimeError('Cannot restore/start website services while original services remain')
        started = time.monotonic()
        for recipe in self.recipes:
            self.launch(recipe['name'], recipe['args'], extra=recipe['extra'])
            if recipe['name'] == 'mysql':
                self.wait_command(['mysqladmin','--socket=/state/run/mysql.sock','ping'],120)
            elif recipe['name'] == 'elasticsearch':
                self.wait_http('http://127.0.0.1:'+str(self.ports.ports[3])+'/_cluster/health',120)
            elif recipe['name'] == 'postgres':
                self.wait_command(['pg_isready', '-h', '/state/run', '-p', str(self.db_port),
                                   '-U', 'postmill', '-d', 'postmill'], 120)
        self.wait_http(self.url + '/', 180)
        self.event('services_ready', started,
                   actual_native_launch_recipe_sha256=hashlib.sha256(json.dumps(self.recipes, sort_keys=True).encode()).hexdigest())

    def _remove_stopped_native_endpoints(self):
        if not self.stopped or self.live_process_ids():
            raise RuntimeError('Runtime endpoints can only be cleared after complete native shutdown')
        names = ['run/php.sock','run/php.pid','run/nginx.pid']
        if self.domain=='reddit':
            names += ['run/.s.PGSQL.'+str(self.db_port),'run/.s.PGSQL.'+str(self.db_port)+'.lock','postgres/postmaster.pid']
        else:
            names += ['run/mysql.sock','run/mysql.sock.lock','run/mysql.pid']
        removed = []
        for name in names:
            path = self.state / name
            if path.is_symlink():
                raise ValueError('Native runtime endpoint must not be an external symlink')
            if path.exists() or path.is_socket():
                if not path.is_file() and not path.is_socket():
                    raise ValueError('Unexpected native runtime endpoint object')
                path.unlink(); removed.append(name)
        self.events.append({'phase': 'stopped_native_runtime_endpoints',
                            'generation': self.generation, 'removed_relative_paths': removed,
                            'session_files_deleted': False})

    def reset_state(self):
        if not hasattr(self, 'snapshot'):
            raise RuntimeError('No completed full offline website baseline')
        started = time.monotonic(); self.stop_services()
        restored = self.snapshot.restore(); self.generation += 1
        # These receipts describe the previous writable state, not the reusable
        # service configuration. A restored baseline needs a fresh initializer.
        for name in ('native_payment_stage', 'native_payment_stage_receipt'):
            self.__dict__.pop(name, None)
        self._remove_stopped_native_endpoints()
        self.start_services()
        return self.event('reset_total', started, restore=restored,
                          full_writable_state=True, native_services_restarted=True)

    def __exit__(self, *args):
        # Preserve the installed content adapter's native logs/ports/state
        # cleanup after strict descendant shutdown. Failed stop never allows
        # deleting or restoring a writable state still used by a process.
        try:
            owner = getattr(self, 'report_ui_owner', None)
            if owner is not None:
                receipt = owner.close()
                listeners = ('report_listener', 'other_local_listener')
                if (not isinstance(receipt, dict)
                        or receipt.get('report_listener_stopped') is not True
                        or any(not isinstance(receipt.get(name), dict)
                               or any(receipt[name].get(key) is not True for key in
                                      ('stopped', 'request_threads_joined',
                                       'server_cleared', 'thread_cleared'))
                               for name in listeners)):
                    raise RuntimeError('Owned report listener cleanup was not verified')
                from .io_utils import atomic_write_json
                atomic_write_json(self.logs/'report-listener-cleanup.json', receipt)
        finally:
            # Stop native descendants even if listener cleanup fails. In that
            # case the exception skips state deletion and port release below.
            self.stop_services()
        try:
            super().__exit__(*args)
        finally:
            if hasattr(self, 'baseline_temp'):
                self.baseline_temp.cleanup()
