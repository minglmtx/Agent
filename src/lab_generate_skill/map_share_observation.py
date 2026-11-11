"""Passive share-task hooks and isolated terminal artifact readback.

No task admission or actor action here. A proof-bound adapter supplies the
candidate and baseline; readback never reuses actor cookies or modifies it.
"""
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
import html
import time
from .io_utils import atomic_write_json as save
from .map_candidate_start import InitialStartHooks
from .map_metadata_query import initial_view
from .map_route_initialization_binding import initial_url_state
from .map_route import read_route
from .map_share_terminal import FAMILIES,output_value,declared_artifact,evaluate_share
from .map_share_artifact_checks import _Embed
from .map_share_roundtrip import warm_reopened_tiles
from .map_typed_information_share import read_share_state
from .browser_request_policy import install_local_network_policy

READER='() => window.__labShareState()'


def reopen_artifact(site,family,value,reference,directory):
    """Native HTTP/frame readback after termination in a new anonymous context.

    Actor HTML is parsed, never executed: only the already validated iframe URL
    and declared dimensions enter a newly constructed minimal iframe document.
    """
    if not declared_artifact(family,value,reference,site.url):
        raise ValueError('Do not navigate an undeclared artifact')
    from browsergym.core import _get_global_playwright
    row=dict(requested=value)
    browser=_get_global_playwright().chromium.launch(headless=True)
    context=browser.new_context(viewport=dict(width=1280,height=720),locale='en-US')
    install_local_network_policy(context,site.allowed_netlocs)
    try:
        page=context.new_page();page.set_default_timeout(15000)
        observed=[]
        def response(r):
            if r.request.is_navigation_request():observed.append((r.url,r.status))
        context.on('response',response)
        target=value
        if family=='map_embed':
            parser=_Embed();parser.feed(value);parser.close();target=parser.iframes[0]['src']
            response=page.goto(site.url+'/',wait_until='domcontentloaded',timeout=30000)
            if response is None or response.status!=200:raise ValueError('Native embed holder is unavailable')
            markup='<iframe src="'+html.escape(target,quote=True)+'" width="'+str(reference['width'])+'" height="'+str(reference['height'])+'" style="border:0"></iframe>'
            page.set_content(markup,wait_until='load',timeout=30000)
            frame=page.locator('iframe').element_handle().content_frame()
            if frame is None:raise ValueError('Native embed frame unavailable')
            statuses=[status for url,status in observed if url==target]
            row['http_status']=statuses[-1]if statuses else None
        else:
            response=page.goto(target,wait_until='domcontentloaded',timeout=30000)
            row['http_status']=response.status if response else None;frame=page
        row['url']=frame.url
        if row['http_status']!=200:return row
        if family in ('route_link','short_route_link'):
            frame.wait_for_function("() => document.querySelectorAll('#sidebar_content tr.turn').length>0 && !jQuery.active",timeout=30000)
            row['state']=read_route(frame)
        else:
            frame.wait_for_function("() => typeof window.__labShareState==='function'",timeout=15000)
            row['tile_readiness']=warm_reopened_tiles(frame,site.tile_url,Path(directory)/'share-artifact-tile-readiness.json',seconds=120)
            row['state']=frame.evaluate(READER)
        row['separate_anonymous_context']=True
        return row
    finally:
        context.close();browser.close()


class ShareObservationHooks(InitialStartHooks):
    def __init__(self,candidate,directory,*,baseline,reopen=reopen_artifact):
        if candidate.get('candidate_completion',{}).get('family')not in FAMILIES:
            raise ValueError('Explicit local share candidate required')
        super().__init__(deepcopy(candidate),None)
        self.directory=Path(directory);self.baseline=baseline;self.reopen=reopen
        self.page=self.reference=self.share=self.terminal_route=self.trace=None
        self.capture_error=None;self.closed=self.scored=False

    def prepare(self,site,username):
        if self.site is not None or username is not None or site.domain!='map':
            raise ValueError('One anonymous private Map preparation required')
        if not all(getattr(site,k,False)for k in ('with_tiles','with_geographic_baseline','track_changes','native_share_observer')):
            raise ValueError('Full guarded Map share-observer profile required')
        if (self.candidate['candidate_completion']['family']=='short_route_link'
                and getattr(site,'short_routes',False) is not True):
            raise ValueError('Validated local compact-route extension required')
        site.reset_guard.require_unchanged()
        if not self.baseline or site.fingerprint()!=self.baseline:raise ValueError('Validated native baseline changed')
        self.site=site;self.events.append('prepare')

    def observe_initial(self,page):
        if self.page is not None:raise ValueError('One initial native page required')
        super().observe_initial(page)
        page.wait_for_function("() => typeof window.__labShareState==='function'",timeout=15000)
        state=page.evaluate(READER);spec=self.candidate['candidate_completion'];family=spec['family']
        reference=dict(source_task_id=self.candidate['source_task_id'],start_path=self.candidate['start_path'],family=family)
        if family in ('share_panel_navigation','route_link','short_route_link'):
            pair,mode=initial_url_state(self.candidate['start_path'])
            reference.update(pair=pair,mode=mode,route=deepcopy(self.initial['route']))
            if not reference['route'].get('route_form_visible'):
                raise ValueError('Share route reference requires actual visible native endpoints')
        else:
            reference['center']=list(initial_view(self.candidate['start_path']))
            if family=='map_embed':
                reference.update(width=spec['width'],height=spec['height'],bbox=[float(v)for v in state['bounds'].split(',')])
        self.reference=reference;self.page=page
        save(self.directory/'share-initial.json',dict(reference=reference,native=state,original_start=self.initial))

    def capture_terminal(self,page,terminal):
        if self.closed or self.scored or page is not self.page:raise ValueError('Bound open actor page required')
        super().capture_terminal(page,terminal)
        if self.candidate['candidate_completion']['family']=='share_panel_navigation':
            try:
                self.share=read_share_state(page);self.terminal_route=read_route(page)
            except Exception as error:self.capture_error=type(error).__name__+': native share capture unavailable'

    def close(self):
        if not self.closed:super().close();self.closed=True

    def provide_trace(self,trace):
        if self.trace is not None or not isinstance(trace,dict)or self.scored:raise ValueError('One completed original trace required')
        from .admin_pilot import final_answer
        self.answer=final_answer(trace);self.trace=trace;self.events.append('provide_trace')

    def score_terminal(self,site,terminal,*,runtime_error=None):
        if site is not self.site or self.scored or not self.closed or self.trace is None or terminal!=self.terminal:
            raise ValueError('One bound terminal score after actor context closure required')
        self.scored=True;self.events.append('score_terminal');integrity=False;roundtrip=None
        try:site.reset_guard.require_unchanged();integrity=site.fingerprint()==self.baseline
        except Exception:pass
        family=self.candidate['candidate_completion']['family']
        if not runtime_error and integrity and not self.capture_error and family!='share_panel_navigation':
            try:value=output_value(family,self.answer)
            except (ValueError,TypeError):value=None
            if value is not None and declared_artifact(family,value,self.reference,site.url):
                try:roundtrip=self.reopen(site,family,value,deepcopy(self.reference),self.directory)
                except Exception as error:roundtrip=dict(requested=value,error=type(error).__name__+': native artifact readback failed')
                # Readback must not persistently mutate the website either.
                try:site.reset_guard.require_unchanged();integrity=site.fingerprint()==self.baseline
                except Exception:integrity=False
        judgment=evaluate_share(self.candidate['candidate_completion'],reference=self.reference,
            answer=self.answer,page=terminal,origin=site.url,tile_origin=site.tile_url,
            share=self.share,terminal_route=self.terminal_route,reopened=roundtrip,
            runtime_error=runtime_error,integrity=integrity,capture_error=self.capture_error)
        save(self.directory/'share-terminal.json',dict(events=self.events,terminal=terminal,
            reference=self.reference,answer=self.answer,share=self.share,terminal_route=self.terminal_route,
            reopened=roundtrip,integrity=integrity,judgment=judgment))
        return judgment,integrity
