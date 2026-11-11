"""Reuse frozen weights across manifests without sharing conversations or task state."""

class SharedActorInitializationError(RuntimeError):
    """A shared inference dependency failed before any model generation."""


def require_reusable_result(result):
    """Call after persisting the failed attempt, before claiming another source."""
    error=result.get('error') or {}
    if error.get('type') in ('ModuleNotFoundError','ImportError'):
        raise RuntimeError('Shared inference dependency failure; stopping before further tasks')
    if error.get('type')=='AcceleratorError' and error.get('stage')=='actor_generation':
        raise RuntimeError('Accelerator execution failed; stopping before further tasks on this device')


class SharedActorBackend:
    def __init__(self):
        self.backend = None
        self.binding = None
        self.closed = False
        self.sites = None
        self.site_binding = None
        self.site_generation = 0
        self.site_logs_root = None
        self.more_waves = False
        self.total_tasks = None
        self.service_tasks = None
        self.sites_closed = False

    def acquire(self, binding, factory, *, initializer=None):
        if self.closed:
            raise RuntimeError('Closed actor backend cannot be reused')
        if self.backend is not None:
            if self.binding != binding:
                raise ValueError('Shared actor weights or inference configuration changed')
            return self.backend, False
        backend = None
        try:
            backend = factory()
            if initializer is not None:
                initializer(backend)
        except Exception as exc:
            self.closed = True
            if backend is not None:
                try:
                    backend.close()
                except Exception:
                    pass  # Preserve the initialization failure as the cause.
            raise SharedActorInitializationError('Shared actor initialization failed; stop before further tasks') from exc
        # Publish only fully initialized weights. A failed load can never be
        # reused or retried by the next source in this worker.
        self.binding = binding
        self.backend = backend
        return self.backend, True

    def acquire_sites(self, binding, factory):
        if self.closed:
            raise RuntimeError('Closed worker cannot acquire website services')
        if self.sites is not None and self.sites.failed:
            raise RuntimeError('Failed site pool cannot be reused or replaced')
        if self.sites is not None and self.site_binding != binding:
            old, self.sites = self.sites, None
            try:
                old.close()
            except BaseException:
                self.closed = True
                raise
        if self.sites is None:
            self.sites = factory(self.site_generation)
            self.site_generation += 1
            self.site_binding = binding
        return self.sites

    def close(self):
        self.closed = True
        sites, self.sites = self.sites, None
        backend, self.backend = self.backend, None
        try:
            if sites is not None:
                sites.close()
            self.sites_closed = True
        finally:
            if backend is not None:
                backend.close()

    def __enter__(self):
        if self.closed:
            raise RuntimeError('Closed actor backend cannot be reused')
        return self

    def __exit__(self, *args):
        self.close()


def inference_binding(settings, model_path):
    # max_new_tokens is intentionally task-local: public query answers already
    # use a different output budget. No prompt/history is retained here.
    return (str(model_path.resolve()), tuple((name, getattr(settings, name, None))
            for name in ('temperature', 'top_p', 'dtype', 'device_map',
                         'enable_thinking', 'max_input_tokens')))
