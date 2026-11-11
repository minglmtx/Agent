"""Owned native media + local UI profile for reviewed Reddit sources.

The exact original modules have provenance-sensitive imports. Load their pinned
closure privately so the existing native-image and local-UI profiles can coexist
without replacing modules in sys.modules. This is not a task plugin loader.
"""
import builtins
from contextlib import contextmanager
import hashlib
from pathlib import Path
from types import ModuleType

VERSION = 'reddit-initialized-media-local-owner-v1'
FILES = frozenset({
    'reddit_public_artifact_candidate.py', 'reddit_local_service_candidate.py',
    'reddit_candidate_ui.py', 'reddit_native_feed_reference.py',
    'reddit_extension_lifecycle.py', 'reddit_local_read_hooks.py',
    'reddit_local_post_candidate.py', 'reddit_rss_subscription_hooks.py',
    'reddit_local_cpu_driver.py', 'reddit_media_lifecycle.py',
})
RUNTIME_MODULES = {Path(name).stem for name in FILES} - {'reddit_local_cpu_driver'}


class MediaLocalProfile:
    def __init__(self, directory, pins):
        self.directory = Path(directory).resolve()
        if set(pins) != FILES:
            raise ValueError('Complete fixed media/local executable closure required')
        self.pins = dict(pins)
        self.modules, self.workers, self.holders = {}, [], []
        self.closed = self.running = False
        self.require_current()
        self.binding = (VERSION, tuple(sorted(self.pins.items())))

    def require_current(self):
        if self.closed:
            raise ValueError('Media/local profile is closed')
        for name, digest in self.pins.items():
            path = self.directory / name
            if (path.is_symlink() or not path.is_file()
                    or hashlib.sha256(path.read_bytes()).hexdigest() != digest):
                raise ValueError('Media/local dependency changed: ' + name)

    def _import(self, name, globals=None, locals=None, fromlist=(), level=0):
        if level == 0 and name in RUNTIME_MODULES:
            return self.module(name)
        if level == 0 and name == 'reddit_local_cpu_driver':
            raise ValueError('CPU control entry is not an ordinary runtime import')
        return builtins.__import__(name, globals, locals, fromlist, level)

    def module(self, name):
        if self.closed or name not in RUNTIME_MODULES:
            raise ValueError('Unknown or closed media/local runtime module')
        if name in self.modules:
            return self.modules[name]
        path = self.directory / (name + '.py')
        raw = path.read_bytes()
        if path.is_symlink() or hashlib.sha256(raw).hexdigest() != self.pins[path.name]:
            raise ValueError('Native implementation differs from pinned producer')
        module = ModuleType(name)
        module.__file__, module.__package__ = str(path), ''
        module.__dict__['__builtins__'] = {**vars(builtins), '__import__': self._import}
        self.modules[name] = module
        try:
            exec(compile(raw, str(path), 'exec'), module.__dict__)
        except BaseException:
            self.modules.pop(name, None)
            raise
        return module

    def prepare(self, site):
        self.require_current()
        media = self.module('reddit_media_lifecycle')
        extension = self.module('reddit_extension_lifecycle')
        owner = getattr(site, 'native_media_owner', None)
        ui = getattr(site, 'local_ui_extension', None)
        if owner is not None and (type(owner) is not media.MediaLifecycle or owner.site is not site):
            raise ValueError('Cannot borrow a different native media profile')
        if ui is not None and (type(ui) is not extension.ExtensionLifecycle or ui.site is not site):
            raise ValueError('Cannot borrow a different local UI profile')
        media.ensure_media(site)
        if ui is not None:
            snapshot = self.module('reddit_candidate_ui').complete_sidecar_snapshot(ui.directory)
            if snapshot != ui.original_sidecar:
                raise RuntimeError('Restored local UI state differs from its baseline')

    def finish(self, site):
        media = self.module('reddit_media_lifecycle')
        owner = getattr(site, 'native_media_owner', None)
        if owner is None:
            # Failed initialization still must join any created listener.
            return media.stop_local_ui(site)
        if type(owner) is not media.MediaLifecycle or owner.site is not site:
            raise ValueError('Cannot close another native media owner')
        receipt = owner.close()
        if not media.listener_cleanup_verified(receipt):
            raise RuntimeError('Local requests must join before reset/site shutdown')
        return receipt

    @contextmanager
    def runner_scope(self, runner, holder=None):
        self.require_current()
        if self.running:
            raise RuntimeError('Overlapping runner scopes are not allowed')
        self.running = True
        previous = runner.SiteWorker

        def factory(*args, **kwargs):
            delegate = previous(*args, **kwargs)
            if delegate.domain != 'reddit':
                delegate.close()
                raise ValueError('Native media/local profile is Reddit-only')
            worker = ProfileWorker(delegate, self)
            self.workers.append(worker)
            return worker

        runner.SiteWorker = factory
        if holder is not None and not any(h is holder for h in self.holders):
            self.holders.append(holder)
        try:
            yield ProfileBackend(holder, self) if holder is not None else None
        finally:
            runner.SiteWorker = previous
            self.running = False

    def close(self):
        if self.closed:
            return
        if self.running:
            raise RuntimeError('Exit the runner before closing its profile')
        errors = []
        try:
            for worker in reversed(self.workers):
                try:
                    worker.close()
                except BaseException as error:
                    errors.append(error)
            for holder in self.holders:
                if any(holder.sites is w for w in self.workers):
                    holder.sites, holder.site_binding = None, None
                    if errors:
                        holder.closed = True
        finally:
            self.closed = True
            self.modules.clear()
        if errors:
            raise RuntimeError('Media/local worker cleanup failed') from errors[0]


class ProfileBackend:
    """Share model weights; give the website pool an exact profile binding."""
    def __init__(self, holder, profile):
        object.__setattr__(self, '_holder', holder)
        object.__setattr__(self, '_profile', profile)

    def __getattr__(self, name):
        return getattr(self._holder, name)

    def __setattr__(self, name, value):
        setattr(self._holder, name, value)

    def acquire_sites(self, binding, factory):
        result = self._holder.acquire_sites((self._profile.binding, binding), factory)
        if not isinstance(result, ProfileWorker) or result.profile is not self._profile:
            raise ValueError('Media/local runner requires its owned website pool')
        return result


class ProfileWorker:
    """Clean local listeners before the ordinary worker starts a background reset."""
    def __init__(self, delegate, profile):
        self.delegate, self.profile = delegate, profile
        self.sites, self.closed, self.failure = [], False, None

    def __getattr__(self, name):
        return getattr(self.delegate, name)

    @property
    def failed(self):
        return self.failure is not None or self.delegate.failed

    @contextmanager
    def episode(self, *args, **kwargs):
        if self.closed or self.failed:
            raise RuntimeError('Media/local worker is closed or failed')
        acquired = False
        try:
            with self.delegate.episode(*args, **kwargs) as site:
                acquired = True
                if not any(old is site for old in self.sites):
                    self.sites.append(site)
                try:
                    try:
                        self.profile.prepare(site)
                    except BaseException as error:
                        self.failure = error
                        raise
                    yield site
                finally:
                    try:
                        self.profile.finish(site)
                    except BaseException as error:
                        self.failure = error
                        raise
        except BaseException as error:
            # A failed single-site reset also invalidates the worker. The base
            # worker closes that site, but must not silently recreate it here.
            if not acquired:
                self.failure = error
            raise

    def close(self):
        if self.closed:
            return
        if self.delegate.in_use:
            raise RuntimeError('Finish the browser episode before closing the worker')
        errors = []
        # A pending reset owns the site's services/config. Join it before UI
        # cleanup; never race teardown against background snapshot restoration.
        pair = self.delegate.pair
        if pair is not None:
            for future in list(pair.pending.values()):
                try:
                    future.result()
                except BaseException as error:
                    errors.append(error)
        try:
            for site in self.sites:
                try:
                    self.profile.finish(site)
                except BaseException as error:
                    errors.append(error)
        finally:
            try:
                self.delegate.close()
            except BaseException as error:
                errors.append(error)
            self.closed = True
        if errors:
            self.failure = errors[0]
            raise RuntimeError('Native profile cleanup failed') from errors[0]
