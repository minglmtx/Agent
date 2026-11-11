"""Two independent sites; reset one while an actor uses the other.

The actor and browser stay on their normal foreground thread. Only service
stop/restore/start runs in the background. Factories must create independent
states and ports; no context, cookies, database or task state is copied across.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Lock
import time
from urllib.parse import urlsplit


def require_independent_sites(a, b):
    def roots(site):
        values=[site.state]
        if getattr(site,'logs',None) is not None:values.append(site.logs)
        snapshot=getattr(site,'snapshot',None)
        if snapshot is not None:values.append(snapshot.baseline)
        return [p.resolve() for p in values]
    if a is b or any(x==y or x in y.parents or y in x.parents
                     for x in roots(a) for y in roots(b)):
        raise ValueError('Alternating sites have overlapping mutable state, logs or baselines')
    def endpoint(site):
        u=urlsplit(site.url)
        return u.scheme,u.hostname,u.port
    pa=set(getattr(getattr(a,'ports',None),'ports',()))
    pb=set(getattr(getattr(b,'ports',None),'ports',()))
    if endpoint(a)==endpoint(b) or pa & pb:
        raise ValueError('Alternating sites share a service endpoint')
    a_pids={p.pid for p in getattr(a,'processes',getattr(a,'active',()))}
    b_pids={p.pid for p in getattr(b,'processes',getattr(b,'active',()))}
    if a_pids & b_pids:raise ValueError('Alternating sites share service processes')


class AlternatingSites:
    def __init__(self, factory, *, recreate_on=()):
        self.recreate_on=recreate_on
        self.factory=factory;self.sites=[];self.pending={};self.executor=None
        self.index=0;self.in_use=False;self.closed=False;self.events=[]
        self._failure=None;self._failure_lock=Lock()

    @property
    def failed(self):
        with self._failure_lock:return self._failure is not None

    @property
    def failure(self):
        with self._failure_lock:return self._failure

    def _reset(self,slot):
        started=time.monotonic();success=False
        try:
            try:
                result=self.sites[slot].reset_state()
            except self.recreate_on:
                # A declared state-change guard requests a fresh private site;
                # arbitrary reset errors are never hidden by a cold restart.
                self.sites[slot].__exit__(None,None,None)
                replacement=self.factory(slot).__enter__()
                self.sites[slot]=replacement
                require_independent_sites(replacement,self.sites[1-slot])
                result={'cold_recreated_after_state_change':True}
            success=True
            return result
        except BaseException as error:
            with self._failure_lock:
                if self._failure is None:self._failure=error
            raise
        finally:
            self.events.append({'phase':'background_reset','slot':slot,'seconds':time.monotonic()-started,'success':success})

    def _require_healthy(self):
        # Called under the failure lock at foreground acquisition boundaries.
        if self._failure is not None:
            raise RuntimeError('Site pool is poisoned by a failed reset') from self._failure

    def __enter__(self):
        try:
            for index in range(2):self.sites.append(self.factory(index).__enter__())
            a,b=self.sites
            require_independent_sites(a,b)
            self.executor=ThreadPoolExecutor(max_workers=2,thread_name_prefix='site-reset')
            return self
        except BaseException:
            self.close();raise

    @contextmanager
    def episode(self, *, reuse=True):
        if self.closed or self.in_use or self.executor is None:
            raise RuntimeError('One active foreground episode is required')
        with self._failure_lock:self._require_healthy()
        slot=self.index%2;start=time.monotonic()
        self.in_use=True;ready=False
        try:
            pending=self.pending.get(slot)
            if pending is not None:
                pending.result()
                del self.pending[slot]
            with self._failure_lock:
                self._require_healthy()
                ready=True
            self.events.append({'episode':self.index,'slot':slot,'ready_wait_seconds':time.monotonic()-start})
            # No automatic retry or switch after a failed reset.
            yield self.sites[slot]
        finally:
            self.in_use=False
            if ready:self.index+=1
            if ready and reuse and not self.closed:
                with self._failure_lock:
                    if self._failure is None:
                        try:self.pending[slot]=self.executor.submit(self._reset,slot)
                        except BaseException as error:
                            self._failure=error;raise

    def close(self):
        if self.in_use:raise RuntimeError('Close the active browser/episode before the pool')
        if self.closed:return
        self.closed=True
        errors=[]
        if self.executor:
            try:self.executor.shutdown(wait=True,cancel_futures=True)
            except BaseException as error:errors.append(error)
            for future in self.pending.values():
                if future.cancelled():continue
                try:future.result()
                except BaseException as error:errors.append(error)
        self.pending.clear()
        for site in reversed(self.sites):
            try:site.__exit__(None,None,None)
            except BaseException as error:errors.append(error)
        failure=self.failure
        if failure is not None:raise RuntimeError('Site reset/cleanup failed') from failure
        if errors:raise RuntimeError('Site reset/cleanup failed') from errors[0]

    def __exit__(self,*args):self.close()
