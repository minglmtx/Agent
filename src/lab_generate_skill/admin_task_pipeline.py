"""Prepare the next private Admin task while the actor uses the current one.

Each task gets its own complete cold initialization, including its declared
fixture. Background workers never activate BrowserGym's global URL settings.
The foreground still verifies the task's admission state before inference.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import time
from .alternating_sites import require_independent_sites


class AdminTaskPipeline:
    def __init__(self,task_ids,factory,*,instances=2):
        if instances not in (1,2) or type(instances)is not int:raise ValueError('One or two instances required')
        self.tasks=list(task_ids)
        if len(set(self.tasks))!=len(self.tasks):raise ValueError('Duplicate task preparation')
        self.factory=factory;self.instances=instances;self.executor=None
        self.pending={};self.live={};self.index=0;self.active=False;self.closed=False;self.events=[]

    @property
    def failed(self):
        return any(f.done() and not f.cancelled() and f.exception() is not None for f in self.pending.values())

    def _prepare(self,index,old=None):
        started=time.monotonic();site=None
        try:
            if old is not None:old.__exit__(None,None,None)
            site=self.factory(self.tasks[index])
            if site.activate_environment:
                raise ValueError('Background Admin sites must not activate global environment')
            site=site.__enter__()
            self.events.append({'phase':'prepare','task_id':self.tasks[index],
                                'seconds':time.monotonic()-started,'success':True})
            return site
        except BaseException:
            self.events.append({'phase':'prepare','task_id':self.tasks[index],
                                'seconds':time.monotonic()-started,'success':False})
            raise

    def __enter__(self):
        if self.closed or self.executor is not None:raise RuntimeError('Pipeline already started/closed')
        self.executor=ThreadPoolExecutor(max_workers=self.instances,thread_name_prefix='admin-prepare')
        try:
            if self.tasks:
                # Finish the first seed creation before a second private clone.
                self.live[0]=self._prepare(0)
                if self.instances==2 and len(self.tasks)>1:
                    self.pending[1]=self.executor.submit(self._prepare,1)
            return self
        except BaseException:self.close();raise

    @contextmanager
    def episode(self,task_id):
        if self.closed or self.active or self.index>=len(self.tasks) or task_id!=self.tasks[self.index]:
            raise RuntimeError('Admin tasks must follow the prepared order exactly once')
        if self.failed:raise RuntimeError('Background Admin preparation failed; stop worker')
        index=self.index;began=time.monotonic()
        future=self.pending.get(index)
        if future is not None:
            self.live[index]=future.result();del self.pending[index]
        site=self.live[index]
        for other_index,other in self.live.items():
            if other_index!=index:require_independent_sites(site,other)
        for other_index,other in self.pending.items():
            if other.done() and not other.cancelled():require_independent_sites(site,other.result())
        self.events.append({'phase':'foreground_wait','task_id':task_id,'seconds':time.monotonic()-began})
        self.active=True
        try:
            with site.activate():yield site
        finally:
            self.active=False;self.index+=1
            del self.live[index]
            next_index=index+self.instances
            if next_index<len(self.tasks) and not self.failed:
                try:self.pending[next_index]=self.executor.submit(self._prepare,next_index,site)
                except BaseException:
                    site.__exit__(None,None,None);raise
            else:site.__exit__(None,None,None)

    def close(self):
        if self.active:raise RuntimeError('Finish the active browser before closing sites')
        if self.closed:return
        self.closed=True;errors=[]
        if self.executor:self.executor.shutdown(wait=True,cancel_futures=False)
        sites=list(self.live.values())
        for future in self.pending.values():
            if future.cancelled():continue
            try:sites.append(future.result())
            except BaseException as error:errors.append(error)
        self.pending.clear();self.live.clear()
        for site in sites:
            try:site.__exit__(None,None,None)
            except BaseException as error:errors.append(error)
        if errors:raise RuntimeError('Admin preparation/cleanup failed') from errors[0]

    def __exit__(self,*args):self.close()
