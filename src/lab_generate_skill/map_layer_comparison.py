"""Private observed-layer history; never infer comparison from a final checkbox."""
from copy import deepcopy
import hashlib,io,json,math,re,time,urllib.request
from pathlib import Path
from urllib.parse import urlsplit
from PIL import Image
from .map_frozen_provider_runtime import covered_area,same_view
from .map_provider_terminal import evaluate_provider_terminal
from .map_provider_observation import ProviderObservationHooks,READER
from .map_route import read_route
from .io_utils import atomic_write_json

VERSION='map-observed-layer-comparison-v1'
from .map_provider_contract import PROVIDER_CODES,validate_comparison as validate_spec


def standard_checks(initial,state,origin,response_hashes,reference_hashes):
    checks=dict(native_requested_layer=False,same_initial_area=False,loaded_genuine_tiles=False,complete_visible_coverage=False)
    try:
        checks['same_initial_area']=same_view(initial,state)
        active=state['active']
        if len(active)!=1 or active[0]['code']!='M':return checks
        layer=active[0];checks['native_requested_layer']=layer['template']==origin+'/tile/{z}/{x}/{y}.png'
        rects=[];valid=True;count=0
        for tile in layer['tiles']:
            a,b,c,d=tile['rect']
            if not tile['current'] or c<=a or d<=b:continue
            count+=1;coords=tile['coords'];z,x,y=(coords[k]for k in ('z','x','y'))
            expected=origin+f'/tile/{z}/{x}/{y}.png'
            okay=(all(type(v)is int for v in (z,x,y))and 0<=z<=20 and 0<=x<2**z and 0<=y<2**z
                and tile['src']==expected and tile['loaded']is True and isinstance(reference_hashes.get(expected),str)
                and re.fullmatch(r'[0-9a-f]{64}',reference_hashes[expected])is not None
                and response_hashes.get(expected)==reference_hashes[expected])
            valid=valid and okay
            if okay:rects.append(tile['rect'])
        checks['loaded_genuine_tiles']=count>0 and valid
        width,height=state['size']['x'],state['size']['y']
        checks['complete_visible_coverage']=(all(type(v)in(int,float)and math.isfinite(v)and v>0 for v in (width,height))
            and covered_area(rects,width,height)>=width*height-1)
    except (KeyError,TypeError,ValueError,OverflowError):pass
    return checks


def route_matches(initial,current):
    keys=('origin','destination','engine','rows')
    return (isinstance(initial,dict)and isinstance(current,dict)and initial.get('route_visible')is True
        and initial.get('loading')is False and bool(initial.get('rows'))
        and current.get('route_visible')is True and current.get('loading')is False
        and all(k in initial and k in current and current[k]==initial[k]for k in keys))


def evaluate(spec,*,initial,terminal,page,site_origin,frames,server,response_hashes,
             standard_origin,standard_references,initial_route=None,terminal_route=None,
             integrity=True,runtime_error=None,capture_error=None,observed_codes=None):
    validate_spec(spec);checks={}
    def result(status,reason):return dict(version=VERSION,status=status,reward={'success':1.,'failure':0.,'unknown':None}[status],checks=checks,reason=reason)
    if runtime_error or capture_error or integrity is not True:return result('unknown','Runtime or complete private capture is unavailable.')
    if not isinstance(page,dict)or type(page.get('http_status'))is not int:return result('unknown','Final document capture is incomplete.')
    status=page['http_status']
    if status<200 or status>=500:return result('unknown','Final document transport failed.')
    if any(type(page.get(k))is not bool for k in ('login_page','error_page'))or not isinstance(page.get('url'),str):return result('unknown','Final document health is incomplete.')
    actual,expected=urlsplit(page['url']),urlsplit(site_origin)
    checks['valid_final_map_document']=(200<=status<300 and not page['login_page']and not page['error_page']and(actual.scheme,actual.netloc)==(expected.scheme,expected.netloc))
    if not checks['valid_final_map_document']:return result('failure','Final page is outside the valid map environment.')
    if not isinstance(terminal,dict)or not isinstance(initial,dict)or not isinstance(frames,list):return result('unknown','Native map history is unavailable.')
    def verify(frame):
        if not isinstance(frame,dict):return None,False
        state=frame.get('state');route=frame.get('route')
        hashes=frame.get('response_sha256',response_hashes)
        if not isinstance(state,dict)or len(state.get('active',[]))!=1:return None,False
        code=state['active'][0].get('code')
        if code=='M':passed=all(standard_checks(initial,state,standard_origin,hashes,standard_references).values())
        elif code==PROVIDER_CODES[spec['provider']]:
            judgment=evaluate_provider_terminal(dict(spec,family='base_layer'),initial=initial,terminal=state,page=page,site_origin=site_origin,
                server=server,response_hashes=hashes,initial_route=initial_route,terminal_route=route,integrity=True)
            passed=judgment['status']=='success'
        else:return code,False
        if spec['retain_initial_route']:passed=passed and route_matches(initial_route,route)
        return code,passed
    final_code,final_good=verify(dict(state=terminal,route=terminal_route))
    try:checks['same_initial_area']=same_view(initial,terminal)
    except (KeyError,ValueError,TypeError):return result('unknown','Malformed final native view.')
    checks['requested_final_layer']=final_code in spec['required_codes']
    if not checks['same_initial_area']or not checks['requested_final_layer']:return result('failure','Final area or layer does not meet the public goal.')
    if spec['retain_initial_route']:
        checks['route_retained']=route_matches(initial_route,terminal_route)
        if not checks['route_retained']:return result('failure','Initial route is absent or changed.')
    if not final_good:return result('unknown','Final selected layer lacks verified native image coverage.')
    verified={code for frame in frames for code,passed in [verify(frame)]if passed}
    for code in spec['required_codes']:checks['observed_loaded_layer_'+code]=code in verified
    if any(code not in verified for code in (observed_codes or [])if code in spec['required_codes']):
        return result('unknown','A requested layer was selected but its actual loading could not be verified.')
    if spec['completion_boundary']=='view_both_declared_layers_then_select_target_same_initial_area':
        checks['selected_public_target_layer']=final_code==PROVIDER_CODES[spec['provider']]
        if not checks['selected_public_target_layer']:
            return result('failure','The public target layer is not active at termination.')
    if not all(checks.values()):return result('failure','Both requested layers were not observed loaded at the declared view.')
    return result('success','Both declared layers were genuinely loaded at the same initial view and required route.')


class LayerComparisonHooks(ProviderObservationHooks):
    def __init__(self,candidate,directory,**kwargs):
        validate_spec(candidate['candidate_completion']);super().__init__(candidate,directory,**kwargs)
        self.frames={};self.standard_references={};self.comparison_error=None;self.observation_count=0;self.observed_codes=set()

    def _response(self,response):
        super()._response(response)
        if self.scored or not self.attached:return
        u,o=urlsplit(response.url),urlsplit(self.site.tile_url)
        if (u.scheme,u.netloc)!=(o.scheme,o.netloc)or not re.fullmatch(r'/tile/\d+/\d+/\d+\.png',u.path)or u.query or u.fragment:return
        try:
            if response.status!=200:raise ValueError('Native standard tile failed')
            self.responses[response.url]=hashlib.sha256(response.body()).hexdigest();self.response_errors.discard(response.url)
        except Exception:self.responses.pop(response.url,None);self.response_errors.add(response.url)

    def _standard_reference(self,state):
        until=time.monotonic()+20
        for tile in state['active'][0]['tiles']:
            if not tile['current']or not tile['loaded']:continue
            a,b,c,d=tile['rect']
            if c<=a or d<=b:continue
            coords=tile['coords'];z,x,y=(coords[k]for k in ('z','x','y'))
            if not(all(type(v)is int for v in (z,x,y))and 0<=z<=20 and 0<=x<2**z and 0<=y<2**z):raise ValueError('Native tile coordinate invalid')
            url=self.site.tile_url+f'/tile/{z}/{x}/{y}.png'
            if tile['src']!=url:raise ValueError('Standard layer uses undeclared transport')
            if url in self.standard_references:continue
            if len(self.standard_references)>=128 or time.monotonic()>=until:raise ValueError('Bounded independent standard reference budget exceeded')
            with urllib.request.urlopen(url,timeout=min(10,max(1,until-time.monotonic())))as response:
                if response.status!=200 or response.geturl()!=url or response.headers.get_content_type()!='image/png':raise ValueError('Native standard reference response invalid')
                body=response.read(2*1024*1024+1)
            if len(body)>2*1024*1024:raise ValueError('Native tile exceeds bound')
            with Image.open(io.BytesIO(body))as image:
                if image.format!='PNG'or image.size!=(256,256):raise ValueError('Native reference must be a full tile')
                image.load()
            digest=hashlib.sha256(body).hexdigest();self.standard_references[url]=digest
            folder=self.directory/'standard-reference';folder.mkdir(exist_ok=True)
            target=folder/(digest+'.png')
            if not target.exists():target.write_bytes(body)
        atomic_write_json(self.directory/'standard-reference.json',self.standard_references)

    def record(self,page):
        self._bound_page(page)
        if self.initial is None:raise ValueError('Initial view missing')
        self.observation_count+=1
        try:
            state=page.evaluate(READER)
            if not state or len(state['active'])!=1 or not same_view(self.initial,state):return
            code=state['active'][0]['code']
            if code not in self.c['candidate_completion']['required_codes']:return
            self.observed_codes.add(code)
            # Only explicitly pending tiles justify a bounded wait. No clicks,
            # navigation or private layer suggestions are supplied to the actor.
            until=time.monotonic()+5
            while any(t['current']and(not t['loaded']or t['src']not in self.responses)and t['src']not in self.response_errors for t in state['active'][0]['tiles']):
                if time.monotonic()>=until:break
                page.wait_for_timeout(50);state=page.evaluate(READER)
                if not state or len(state['active'])!=1 or state['active'][0]['code']!=code:return
            route=read_route(page)if self.c['candidate_completion']['retain_initial_route']else None
            if code=='M':
                self._standard_reference(state);okay=all(standard_checks(self.initial,state,self.site.tile_url,self.responses,self.standard_references).values())
            else:
                from .map_frozen_provider_runtime import provider_checks
                okay=all(provider_checks(self.initial,state,self.c['candidate_completion']['provider'],self.server,self.responses).values())
            if self.c['candidate_completion']['retain_initial_route']:okay=okay and route_matches(self.initial_route,route)
            if okay and code not in self.frames:
                urls={tile['src']for tile in state['active'][0]['tiles']if tile['current']}
                self.frames[code]=dict(state=state,route=route,observation_number=self.observation_count,
                    response_sha256={url:self.responses[url]for url in urls if url in self.responses})
                atomic_write_json(self.directory/'comparison-history.json',list(self.frames.values()))
        except Exception as exc:self.comparison_error=type(exc).__name__+': '+str(exc)

    def capture_terminal(self,page,terminal):
        self.record(page);super().capture_terminal(page,terminal)

    def score_terminal(self,site,terminal,*,runtime_error=None):
        if site is not self.site or self.scored or self.terminal is None or terminal!=self.terminal:raise ValueError('One bound final score required')
        self.scored=True;integrity=False
        try:
            site.provider_environment.require_owned();site.reset_guard.require_unchanged()
            integrity=site.fingerprint()==self.baseline and site.native_provider_binding==self.binding
        except Exception:pass
        judgment=evaluate(self.c['candidate_completion'],initial=self.initial,terminal=self.native_terminal,page=terminal,site_origin=site.url,
            frames=list(self.frames.values()),server=self.server,response_hashes=self.responses,standard_origin=site.tile_url,standard_references=self.standard_references,
            initial_route=self.initial_route,terminal_route=self.terminal_route,integrity=integrity,runtime_error=runtime_error,capture_error=self.comparison_error or self.capture_error,observed_codes=sorted(self.observed_codes))
        self.events.append('score_terminal')
        atomic_write_json(self.directory/'comparison-terminal.json',dict(events=self.events,baseline=self.baseline,environment_binding=self.binding,initial=self.initial,observed_codes=sorted(self.observed_codes),terminal=terminal,native_terminal=self.native_terminal,terminal_route=self.terminal_route,initial_route=self.initial_route,frames=list(self.frames.values()),standard_origin=site.tile_url,response_sha256=self.responses,standard_reference_sha256=self.standard_references,integrity=integrity,judgment=judgment,observation_count=self.observation_count))
        return judgment,integrity
