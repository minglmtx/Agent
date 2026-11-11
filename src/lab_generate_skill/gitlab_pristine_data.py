"""Process-local, never-started GitLab data extracted from the immutable image.

The cache is never mounted into a running container. Each deployment gets an
independent copy before port/account configuration. Failed copies are not reused.
No cache is shared across jobs, processes or changed image identities.
"""
import os
from pathlib import Path
import subprocess
import tempfile
import time

import psutil


_CACHES = {}
EXTRACT = '''set -e
echo copying_gitlab_data
cp -a /var/opt/gitlab /state/data
echo copying_optvar
cp -a /opt/gitlab/var /state/optvar
echo setting_private_permissions
chmod -R u+rwX /state/data /state/optvar
echo extraction_complete
'''


def run_copy(command, *, log, timeout=600):
    """Bound the copy and reap its children before deleting partial state.

    Keep the parent's process group so the outer watchdog can still stop the
    entire job. Do not print env, database contents, or authentication settings.
    """
    with Path(log).open('ab') as output:
        process = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT)
        try:
            code = process.wait(timeout=timeout)
            if code:
                raise subprocess.CalledProcessError(code, command)
        except BaseException:
            try:
                parent = psutil.Process(process.pid)
                tracked = parent.children(recursive=True) + [parent]
            except psutil.NoSuchProcess:
                tracked = []
            for child in reversed(tracked):
                try:
                    child.terminate()
                except psutil.NoSuchProcess:
                    pass
            _, alive = psutil.wait_procs(tracked, timeout=3)
            for child in alive:
                try:
                    child.kill()
                except psutil.NoSuchProcess:
                    pass
            _, alive = psutil.wait_procs(alive, timeout=3)
            process.wait(timeout=5)
            if alive:
                raise RuntimeError('Copy descendants remain alive; job cleanup required')
            raise


def image_identity(image):
    image = Path(image).resolve(strict=True)
    s = image.stat()
    return (str(image), s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)


def populate(image, state, *, tmpdir, log):
    """Copy pristine files into a new empty state, with no hard links."""
    image, state, tmpdir = Path(image), Path(state), Path(tmpdir)
    if state.is_symlink() or not state.is_dir() or any(state.iterdir()):
        raise ValueError('A new empty private state directory is required')
    before = image_identity(image)
    key = (os.getpid(), str(tmpdir.resolve()), before)
    started = time.monotonic()
    cache = _CACHES.get(key)
    hit = cache is not None
    if cache is None:
        cache = tempfile.TemporaryDirectory(prefix='gitlab-pristine-', dir=tmpdir)
        try:
            command = ['apptainer', 'exec', '--cleanenv', '--containall', '--no-home',
                       '--no-mount', 'bind-paths,hostfs,cwd', '--pwd', '/',
                       '--bind', cache.name + ':/state', str(image), 'sh', '-c', EXTRACT]
            run_copy(command, log=log)
            if image_identity(image) != before:
                raise RuntimeError('Image changed during pristine extraction')
            if not all((Path(cache.name)/name).is_dir() for name in ('data', 'optvar')):
                raise RuntimeError('Pristine extraction incomplete')
        except BaseException:
            cache.cleanup()
            raise
        _CACHES[key] = cache
    extract_seconds = time.monotonic() - started
    copy_started = time.monotonic()
    # Template never receives service writes; ordinary files cannot be hardlinked
    # to a mutable instance. cp -a preserves native symlinks and metadata.
    run_copy(['cp', '-a', '--reflink=auto', '--', cache.name + '/.', str(state) + '/'], log=log)
    if image_identity(image) != before:
        raise RuntimeError('Image changed while creating private state')
    (state/'log').mkdir(exist_ok=True)
    return {'strategy': 'process_pristine_clone_v1', 'cache_hit': hit,
            'extract_seconds': extract_seconds, 'clone_seconds': time.monotonic()-copy_started,
            'copy_policy': 'reflink_auto_or_full_copy', 'template_started': False}
