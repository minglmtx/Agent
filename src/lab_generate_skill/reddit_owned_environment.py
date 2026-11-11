"""Own a declared native environment through scoring and episode restoration.

The original hook still captures and judges the terminal state. Browser close
does not restore the environment before that judgment. The ordinary episode
boundary, including exceptions, verifies restoration before its checkpoint.
"""
from contextlib import contextmanager
from pathlib import Path


RESTORED = ('passed', 'original_full_state_restored', 'full13_and_all_auxiliary_verified',
            'temporary_augmented_snapshot_removed', 'original_snapshot_reinstalled')


class OwnedNativeHooks:
    def __init__(self, contract, proof, directory, *, runtime, environment_type, owners, judgments):
        runtime.require_admission(contract, proof)
        self.contract, self.proof = contract, proof
        self.directory = Path(directory)
        self.runtime, self.environment_type = runtime, environment_type
        self.owners, self.judgments = owners, judgments
        self.delegate = self.owner = self.site = None
        self.owner_verified = False
        # A reused task ID must not overlap an unfinished previous lifetime.
        if any(h.contract['task_id'] == contract['task_id'] and not h.owner_verified for h in owners):
            raise ValueError('A native environment for this task is still active')
        owners.append(self)

    def prepare(self, site, username):
        if self.owner is not None:
            raise ValueError('A native task environment can only be prepared once')
        self.site = site
        self.owner = self.environment_type(site, username, self.directory/'normal-native-environment')
        try:
            self.owner.enter_for_hook()
            self.delegate = self.runtime.NativeWikiHomeHooks(
                self.contract, self.proof, self.owner, self.directory)
            self.delegate.prepare(site, username)
        except BaseException:
            self.finish_owner()
            raise

    def __getattr__(self, name):
        delegate = self.__dict__.get('delegate')
        if delegate is None:
            raise AttributeError(name)
        return getattr(delegate, name)

    def score_terminal(self, *args, **kwargs):
        if self.delegate is None or self.owner_verified:
            raise ValueError('An active prepared environment is required for terminal scoring')
        judgment, integrity = self.delegate.score_terminal(*args, **kwargs)
        self.judgments.append((judgment, self.runtime))
        return judgment, integrity

    def finish_owner(self):
        if self.owner is None:
            return False
        if not self.owner.closed:
            self.owner.__exit__(None, None, None)
        receipt = self.owner.close_receipt or {}
        self.owner_verified = all(receipt.get(key) is True for key in RESTORED)
        return self.owner_verified


@contextmanager
def ordinary_owner_scope(dispatch, worker_module, runner, owners, judgments):
    """Restore every owner inside SiteWorker.episode, even on runtime failure.

    Patch the runner's factory and the owning module together. Reject a borrowed
    already-created SiteWorker, whose episode method would bypass this scope.
    No action, observation, task goal, terminal predicate or reward is changed.
    """
    prior_worker, prior_runner_worker = worker_module.SiteWorker, runner.SiteWorker
    prior_integrity, prior_feedback = dispatch.terminal_integrity, dispatch.feedback

    def integrity(contract, **kwargs):
        result = prior_integrity(contract, **kwargs)
        active = [h for h in owners if h.contract['task_id'] == contract['task_id']]
        if not active:
            return result
        if len(active) != 1:
            raise ValueError('A task has multiple native environment owners')
        return active[0].finish_owner() and result

    def feedback(judgment):
        # The original Wiki judge has no version field. Dispatch only its actual
        # object, not any unrelated unversioned or copied judgment.
        matches = [module for value, module in judgments if judgment is value]
        if matches:
            return matches[-1].feedback(judgment)
        return prior_feedback(judgment)

    class ScopedWorker(prior_worker):
        @contextmanager
        def episode(self, *args, **kwargs):
            with super().episode(*args, **kwargs) as site:
                try:
                    yield site
                finally:
                    try:
                        for hook in list(owners):
                            if hook.site is site and not hook.finish_owner():
                                raise RuntimeError('Original native owner restoration is unverified')
                    finally:
                        owners[:] = [h for h in owners if h.site is not site or not h.owner_verified]

    dispatch.terminal_integrity, dispatch.feedback = integrity, feedback
    worker_module.SiteWorker = runner.SiteWorker = ScopedWorker
    try:
        yield
    finally:
        try:
            for hook in list(owners):
                if hook.owner is not None and not hook.finish_owner():
                    raise RuntimeError('Original native owner restoration is unverified')
        finally:
            worker_module.SiteWorker, runner.SiteWorker = prior_worker, prior_runner_worker
            dispatch.terminal_integrity, dispatch.feedback = prior_integrity, prior_feedback
            owners.clear()
            judgments.clear()
