"""Staged optional MapData-XHR adapter; native exports/downloads stay untouched.

The browser's original failed map400 is preserved. Successful exact native
children supply a clearly marked adapted XML envelope to the unchanged browse
loader/renderer. No checkbox, map center, zoom, warning confirmation or task
parameters are changed by this transport. It grants no normal admission.
"""
from pathlib import Path
import hashlib,json,time
from urllib.parse import parse_qs,urlsplit
from .map_native_bbox_batch import Response,CAP_ERROR,NativeBatchError,fetch_complete,child_api_path,digest,VERSION
from .io_utils import atomic_write_json
import threading
from .map_native_bbox_async import BackgroundNativeMap

class NativeMapDataBatchTransport:
    def __init__(self,page,site_origin,directory,*,seconds=60,public_snapshot=None):
        if not 0<seconds<=300:raise ValueError('Bounded unchanged-per-request absolute deadline required')
        self.page=page;self.origin=site_origin;self.out=Path(directory)
        self.out.mkdir(mode=0o700,exist_ok=False)
        o=urlsplit(site_origin)
        if o.scheme not in('http','https')or not o.netloc or o.username or o.password or o.path not in('','/')or o.query or o.fragment:raise ValueError('Exact local native origin required')
        self.origin_key=(o.scheme,o.netloc);self.seconds=seconds;self.snapshot=public_snapshot
        self.records=[];self.observations=[];self._handler=self._receive;self.closed=False;self.lock=threading.RLock()
        self.background=BackgroundNativeMap(self)
        self.page.route('**/api/0.6/map?*',self._handler)

    def _save(self):
        with self.lock:atomic_write_json(self.out/'native-batch-transport.json',{'version':VERSION,'requests':self.records,'native_original_errors_retained':True,'export_download_adapter':False,'actor_strategy_changed':False,'task_admitted':False,'native_fetch_outside_playwright_callback':True,'page_snapshot_outside_playwright_callback':True,'public_observations':self.observations})

    def _receive(self,route):
        request=route.request;u=urlsplit(request.url)
        # MapData's installed $.ajax is XHR. Export/form/download document
        # requests keep the original native endpoint, status and artifact.
        if request.method!='GET'or request.resource_type!='xhr'or(u.scheme,u.netloc)!=self.origin_key or u.path!='/api/0.6/map'or u.fragment:
            route.continue_();return
        query=parse_qs(u.query,keep_blank_values=True)
        if set(query)!={'bbox'}or len(query['bbox'])!=1:
            route.continue_();return
        start=time.monotonic();deadline=start+self.seconds
        record={'request_url':request.url,'requested_bbox_strings':query['bbox'][0].split(','),'request_method':'GET','resource_type':'xhr',
                'status':'queued_native_batch','snapshot_at_actual_request':None,
                'request_snapshot_not_collected_in_route_callback':True,
                'request_metadata_source':'actual_native_request_url_and_bbox',
                'native_original_http_status':None,'native_cap_changed':False,'native_original_bbox_or_view_changed':False,
                'download_created':False,'task_admitted':False}
        with self.lock:self.records.append(record);number=len(self.records)-1
        directory=self.out/('request-'+str(number));directory.mkdir()
        try:
            target=self.background.register(number,record,directory,deadline)
            headers={k:v for k,v in request.headers.items()if k.lower()not in('referer','cookie','authorization','proxy-authorization')}
            headers['referer']=''
            # No fetch, future.result, join or complete XML construction occurs
            # in this callback. Chromium's real XHR waits on the HTTP handler.
            route.continue_(url=target,headers=headers)
        except Exception as exc:
            record.update(status='batch_transport_unknown',failure_type=type(exc).__name__,
                ledger=getattr(exc,'ledger',None),failure_category=getattr(exc,'reason_code','transport_or_browser_error'))
            try:route.abort('failed')
            except Exception as transport:record['native_abort_failure_type']=type(transport).__name__
        finally:
            with self.lock:record['playwright_callback_seconds']=time.monotonic()-start;self._save()

    def observe_public_state(self,value,*,event='observation'):
        """Full surface is collected by the ordinary observation, not an XHR hook.

        A rendered MapData surface can contain tens of thousands of SVG paths.
        Never walk that DOM while a Playwright click is waiting for the route
        callback. Preserve the full later observation separately, with honest
        time semantics; it is not the browser state at the instant of request.
        """
        if self.closed:raise ValueError('Closed native transport cannot receive a new observation')
        index=len(self.observations)
        filename='public-observation-'+str(index)+'.json'
        destination=self.out/filename
        if destination.exists():raise ValueError('Full observation artifact is immutable')
        # Normal observation has already read the page. This write performs no
        # additional Playwright evaluate and the large full surface is not
        # embedded/re-written into every request/transport checkpoint.
        atomic_write_json(destination,value)
        data=destination.read_bytes()
        row={'event':event,'timing_semantics':'after_normal_page_observation',
             'not_request_instant_snapshot':True,'file':filename,
             'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
        with self.lock:
            row['native_request_indexes_seen']=list(range(len(self.records)))
            self.observations.append(row)
            for request in self.records:
                if 'first_later_public_observation' not in request:
                    request['first_later_public_observation']=dict(row)
            self._save()
        return row

    def settle_pending(self):
        """Pump only already registered native XHRs before terminal capture.

        Each request keeps its original registration deadline. No request,
        browser action, chosen bbox or payload is created or retried here.
        Chromium stays alive while its actual pending response is delivered.
        """
        if self.closed:raise ValueError('Closed native transport cannot settle')
        began=time.monotonic()
        with self.background.lock:
            jobs=[job for job in self.background.jobs.values() if not job['record'].get('background_handler_finished')]
        index=sum(1 for _ in self.out.glob('terminal-pending-settle-*.json'))
        path=self.out/('terminal-pending-settle-'+str(index)+'.json')
        details={'version':'native-map-terminal-existing-pending-v1',
            'registered_requests':len(jobs),'actual_request_indexes':[],
            'new_requests_created':False,'actor_action_created':False,
            'native_scope_or_cap_changed':False,'original_deadlines_extended':False}
        try:
            while True:
                with self.lock:
                    pending=[job for job in jobs if not job['record'].get('background_handler_finished')]
                    deadlines=[job['deadline']for job in jobs]
                    details['actual_request_indexes']=[self.records.index(job['record'])for job in jobs]
                if not pending:break
                deadline=min(job['deadline']for job in pending)
                remaining=deadline-time.monotonic()
                if remaining<=0:raise TimeoutError('Original pending native batch deadline expired before terminal capture')
                # wait_for_timeout runs Playwright's real event pump; a Python
                # sleep or thread join would block renderer/response callbacks.
                self.page.wait_for_timeout(min(50,remaining*1000))
            if jobs:
                # Full socket delivery is not proof that the current native
                # jQuery renderer has consumed it. Wait only its public loader,
                # using the same original request deadline; no expected result.
                remaining=min(deadlines)-time.monotonic()
                if remaining<=0:raise TimeoutError('Original native renderer deadline expired before terminal capture')
                self.page.wait_for_function("() => !window.jQuery || jQuery.active === 0",timeout=remaining*1000)
            details.update(passed=True,seconds=time.monotonic()-began,
                request_statuses=[job['record'].get('status')for job in jobs])
            return details
        except BaseException as error:
            from .runtime_diagnostics import failure_diagnostic
            details.update(passed=False,seconds=time.monotonic()-began,
                diagnostic=failure_diagnostic(error,'terminal_existing_native_request_settle'))
            raise
        finally:atomic_write_json(path,details)

    def close(self):
        if self.closed:return
        failure=None
        try:self.page.unroute('**/api/0.6/map?*',self._handler)
        except BaseException as error:failure=error
        finally:
            try:self.background.close()
            except BaseException as error:
                if failure is None:failure=error
            self.closed=True;self._save()
        if failure is not None:raise failure
