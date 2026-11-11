"""Offline worker-local persistent-state baseline; never snapshot a running DB.

The adapter must stop every service before save/restore. Browser resets are a
separate operation. No hard links: changing a working file must not alter baseline.
"""
import os
import tempfile
import shutil
from pathlib import Path
import subprocess
import time


class SiteStateSnapshot:
    def __init__(self, state, baseline, *, services_stopped, restore_strategy="checksum"):
        if restore_strategy not in ("checksum", "clone"):raise ValueError("Unknown restore strategy")
        self.restore_strategy = restore_strategy
        self.state = Path(state)
        self.baseline = Path(baseline)
        self.services_stopped = services_stopped
        self.saved = False
        self._prepared = None
        self._baseline_bytes = None
        self._paths()

    def _paths(self):
        if self.state.is_symlink() or self.baseline.is_symlink():
            raise ValueError('Snapshot roots must not be symlinks')
        state, baseline = self.state.resolve(), self.baseline.resolve()
        if state == baseline or state in baseline.parents or baseline in state.parents:
            raise ValueError('Baseline and working state must be separate trees')
        if not self.state.is_dir():
            raise ValueError('Missing working state directory')

    def _offline(self):
        self._paths()
        if not self.services_stopped():
            raise RuntimeError('Persistent-state snapshot requires stopped services')

    def save(self):
        self._offline()
        if self.saved or self.baseline.exists():
            raise RuntimeError('Refusing to replace an existing baseline')
        start = time.monotonic()
        # CoW when supported; otherwise independent ordinary copies. Never cp -l.
        subprocess.run(['cp', '-a', '--reflink=auto', '--', str(self.state), str(self.baseline)],
                       check=True, timeout=600)
        self.saved = True
        return {'seconds': time.monotonic()-start, 'copy_policy': 'reflink_auto_or_full_copy'}

    def restore(self):
        self._offline()
        if not self.saved or not self.baseline.is_dir():
            raise RuntimeError('No completed baseline')
        if self.restore_strategy == 'clone':
            return self._restore_clone()
        start = time.monotonic()
        # Check contents, not only timestamps: equal-size edits must be restored.
        args = ['rsync', '-a', '--no-owner', '--no-group', '--checksum', '--delete']
        subprocess.run(args + ['--', str(self.baseline)+'/', str(self.state)+'/'],
                       check=True, timeout=600)
        diff = subprocess.run(args + ['--dry-run', '--itemize-changes', '--',
                                     str(self.baseline)+'/', str(self.state)+'/'],
                              check=True, timeout=600, capture_output=True, text=True)
        if diff.stdout.strip():
            raise RuntimeError('Persistent-state restore verification failed: '+diff.stdout[:1000])
        return {'seconds': time.monotonic()-start, 'verified': True, 'restore_complete': True,
                'verification': 'offline checksum, paths, symlinks and metadata',
                'scope': 'all files in the adapter private writable state'}

    def _restore_clone(self):
        # All services are stopped. Build a separate independent copy first;
        # failed copying must leave the previous working state untouched.
        start = time.monotonic()
        if self._prepared is not None:
            return self._restore_prepared(start)
        with tempfile.TemporaryDirectory(prefix='site-restore-', dir=self.state.parent) as work:
            work = Path(work); ready = work/'ready'; old = work/'old'
            subprocess.run(['cp', '-a', '--reflink=auto', '--', str(self.baseline), str(ready)],
                           check=True, timeout=600)
            copy_seconds = time.monotonic()-start
            self.state.rename(old)
            try:
                ready.rename(self.state)
            except BaseException:
                old.rename(self.state)
                raise
            cleanup_start = time.monotonic()
            shutil.rmtree(old)
            cleanup_seconds = time.monotonic()-cleanup_start
        return {'seconds':time.monotonic()-start, 'restore_complete':True,
                'verified':False, 'verification':'Independent copy completed; semantic reset controls required separately',
                'strategy':'clone', 'copy_seconds':copy_seconds,'cleanup_seconds':cleanup_seconds,
                'scope':'All files in adapter private writable state; no timestamp-based skipping'}

    def prepare_restore(self):
        """Prepare ONE independent copy of the immutable baseline, not live state.

        May overlap service startup/rollout. Activation still requires all service
        processes to stop. No baseline refresh, hardlinks or skipped reset checks.
        Insufficient scratch space simply retains synchronous restoration.
        """
        self._paths()
        if self.restore_strategy != 'clone' or not self.saved:
            raise RuntimeError('Prefetch requires a completed clone baseline')
        if self._prepared is not None:
            return {'status': 'already_preparing'}
        if self._baseline_bytes is None:
            usage = subprocess.run(['du', '-sx', '-B1', '--', str(self.baseline)],
                                   check=True, timeout=60, capture_output=True, text=True)
            self._baseline_bytes = int(usage.stdout.split()[0])
        required = int(self._baseline_bytes * 1.1) + 128 * 1024**2
        if shutil.disk_usage(self.state.parent).free < required:
            return {'status': 'skipped_insufficient_space', 'required_bytes': required}
        work = tempfile.TemporaryDirectory(prefix='site-prefetch-', dir=self.state.parent)
        try:
            process = subprocess.Popen(['cp', '-a', '--reflink=auto', '--',
                str(self.baseline), str(Path(work.name)/'ready')],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except BaseException:
            work.cleanup()
            raise
        self._prepared = (work, process, time.monotonic())
        return {'status': 'preparing', 'required_bytes': required}

    def close(self):
        """Cancel an unused copy before deleting baseline or working directories."""
        prepared, self._prepared = self._prepared, None
        if prepared is None:
            return
        work, process, _ = prepared
        try:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        finally:
            work.cleanup()

    def _restore_prepared(self, started):
        work, process, launched = self._prepared
        ready = Path(work.name)/'ready'
        old = Path(work.name)/'old'
        try:
            # Bound unfinished copies, without rejecting copies that completed
            # while a long rollout was running.
            code = process.poll()
            if code is None:
                code = process.wait(timeout=max(0.01, 600-(time.monotonic()-launched)))
            if code != 0:
                raise RuntimeError('Prefetched snapshot copy failed (exit %s); state not replaced' % code)
            if not ready.is_dir() or ready.is_symlink():
                raise RuntimeError('Prefetched snapshot is missing or invalid')
            wait_seconds = time.monotonic()-started
            self.state.rename(old)
            try:
                ready.rename(self.state)
            except BaseException:
                old.rename(self.state)
                raise
            cleanup_start = time.monotonic()
            shutil.rmtree(old)
            return {'seconds': time.monotonic()-started, 'restore_complete': True,
                'verified': False, 'strategy': 'clone_prefetched',
                'verification': 'Independent copy completed; semantic reset controls required separately',
                'copy_wait_seconds': wait_seconds,
                'cleanup_seconds': time.monotonic()-cleanup_start,
                'scope': 'All files in adapter private writable state; no timestamp-based skipping'}
        finally:
            self.close()
