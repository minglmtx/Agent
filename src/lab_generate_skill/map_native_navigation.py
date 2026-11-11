"""Original-start native Map home/upload/export navigation completion adapter.

This scores only finite public page/form/view conditions. It does not claim a
GPS upload, image export, named-feature edits, delivery or full tile coverage.
Prior capability references are private baselines, never ordinary admission.
"""
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from .map_local_capabilities import navigation_checks,geo_triplet,same_center,local_target,wait_current_native_view
from .map_view import read_map_view
from .map_panel import read_map_panel
from .visible_form import read_visible_forms

VERSION='native-map-navigation-v1'
KINDS={'home':('/',r'OpenStreetMap'),'upload_form':('/traces/new',r'^Upload GPS Trace$'),
       'export_area':('/export',r'^Export$')}
FEEDBACK={'native_map_ready':'The native map view is available.',
    'native_map_displayed':'The native map is displayed.',
    'native_map_settled':'The native map is no longer initializing.',
    'original_area_preserved':'The final map view preserves the initial task area.'}


def validate(spec):
    if not isinstance(spec,dict) or set(spec)!= {'version','kind','initial_area','reference_evidence'} or spec['version']!=VERSION or spec['kind']not in KINDS:
        raise ValueError('Explicit native Map navigation specification required')
    center=spec['initial_area']
    if (spec['kind']=='export_area') != (center is not None):
        raise ValueError('Only named-area Export binds its actual initial native area')
    if center is not None:
        if (not isinstance(center,list) or len(center)!=3 or type(center[0])is not int or
            not 1<=center[0]<=30 or any(type(v)not in (int,float)for v in center[1:])):
            raise ValueError('Numeric settled initial geographic reference required')
        from .map_metadata_query import native_geo_uri
        native_geo_uri(*center)
    refs=spec['reference_evidence']
    if not isinstance(refs,list) or len(refs)!=2 or any(not isinstance(r,dict)or set(r)!={'file','sha256'}or
       not isinstance(r['file'],str)or not isinstance(r['sha256'],str)or not re.fullmatch('[0-9a-f]{64}',r['sha256'])for r in refs)or len({str(Path(r['file']).resolve())for r in refs})!=2:
        raise ValueError('Two independent native original-source references required')
    return spec


def verify_reference(contract):
    spec=validate(contract['completion']['map_native_navigation'])
    for ref in spec['reference_evidence']:
        path=Path(ref['file'])
        if hashlib.sha256(path.read_bytes()).hexdigest()!=ref['sha256']:
            raise RuntimeError('Native Map navigation reference changed')
        row=json.loads(path.read_text())
        if (row.get('source_task_id')!=contract['source_task_id'] or row.get('goal')!=contract['goal']or
            row.get('start_path')!=contract['start_path']or row.get('passed')is not True or
            row.get('initialization_protocol')!='fresh_document_exact_original_start' or
            not all(row.get('controls',{}).get(key,{}).get('passed')is True for key in
                    ('no_op','positive','wrong_object','login_page','error_page'))):
            raise RuntimeError('Native reference is not this original complete source capability')
        if spec['initial_area']is not None and not same_center(spec['initial_area'],geo_triplet(row.get('initial_native_view'))):
            raise RuntimeError('Named area differs from actual settled original initial view')
        pages=row['controls']['positive']['pages']
        if len(pages)!=1:
            raise RuntimeError('Navigation reference must have one actual final native page')
        origin=urlsplit(pages[0]['url']);site_origin=origin.scheme+'://'+origin.netloc
        if not all(navigation_checks(spec['kind'],pages[0],site_origin,expected_center=spec['initial_area']).values()):
            raise RuntimeError('Native navigation reference does not satisfy its declared completion')
    return True


def base_contract(contract):
    return {**contract,'completion':{k:v for k,v in contract['completion'].items()if k!='map_native_navigation'}}


def fingerprint(contract):
    from .site_navigation_rules import contract_fingerprint
    validate(contract['completion']['map_native_navigation'])
    payload={'generic_contract':contract_fingerprint(base_contract(contract)),
             'native_navigation':contract['completion']['map_native_navigation']}
    return hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()


def read_terminal(page):
    """Read the actual public terminal condition; never pan to an expected area."""
    path=urlsplit(page.url).path
    state={'url':page.url}
    if path in ('/','/export'):
        state['native_view']=read_map_view(page)
        state['readiness_timed_out']=False
        if state['native_view'].get('map_visible') is True:
            from playwright.sync_api import TimeoutError as BrowserTimeout
            try:
                state['native_view']=wait_current_native_view(page,timeout=15000)
            except BrowserTimeout as exc:
                state['native_view']=exc.last_native_view
                state['readiness_timed_out']=True
                state['native_readiness']=exc.last_native_readiness
        state['url']=page.url
        if path=='/export':state['map_panel']=read_map_panel(page)
    elif path=='/traces/new':
        state['visible_forms']=read_visible_forms(page)
    return state


def terminal_checks(spec,state,page,site_origin):
    validate(spec)
    if not isinstance(state,dict) or state.get('url')!=page.get('url'):
        raise ValueError('Native navigation capture does not match actual terminal page')
    checks=navigation_checks(spec['kind'],{**page,**state},site_origin,expected_center=spec['initial_area'])
    if spec['kind'] in ('home','export_area'):
        view=state.get('native_view')
        if not isinstance(view,dict):raise ValueError('Actual native map view was not captured')
        checks['native_map_displayed']=view.get('map_visible')is True
        if type(state.get('readiness_timed_out')) is not bool:
            raise ValueError('Native current-view observation status missing')
        checks['native_map_settled']=state['readiness_timed_out']is False
    return checks


def evaluate(contract,page,*,site_origin):
    from .site_navigation_rules import evaluate_navigation
    result=evaluate_navigation(base_contract(contract),page,site_origin=site_origin)
    if result['status']!='success':return result
    try:
        checks=terminal_checks(contract['completion']['map_native_navigation'],page.get('map_native_navigation'),page,site_origin)
    except (ValueError,TypeError,KeyError):
        return {**result,'status':'unknown','reward':None,'reason':'Native terminal condition was not captured consistently.'}
    if checks.get('native_map_settled')is False and checks.get('native_map_displayed')is True:
        return {**result,'checks':{**result['checks'],**checks},'status':'unknown','reward':None,'reason':'Native map still initializing at termination.'}
    passed=all(checks.values())
    return {**result,'checks':{**result['checks'],**checks},'status':'success'if passed else'failure','reward':float(passed)}


def control_names(spec):
    validate(spec)
    return ('hidden_native_map',)if spec['kind']=='home'else('hidden_native_form',)if spec['kind']=='upload_form'else('hidden_native_form','wrong_native_area')


def control_admission(contract,cases,*,site_origin):
    from .site_navigation_rules import control_admission as generic
    result=generic(base_contract(contract),cases,site_origin=site_origin)
    required={'positive':'success','restored_positive':'success',
       **{name:'failure'for name in ('initial_no_op','wrong_target','404','login')+control_names(contract['completion']['map_native_navigation'])}}
    if any(name not in cases for name in required):return {**result,'passed':False,'status':'missing_native_controls','checks':{}}
    judgments={name:evaluate(contract,page,site_origin=site_origin)for name,page in cases.items()}
    passed=result['passed']and all(judgments[name]['status']==expected for name,expected in required.items())
    return {**result,'passed':passed,'status':'passed'if passed else'native_contract_or_control_mismatch',
       'checks':{name:row['status']for name,row in judgments.items()}}


def require_admission(contract,proof):
    from .site_navigation_rules import require_admission as generic,contract_fingerprint
    verify_reference(contract)
    if proof.get('contract_fingerprint')!=fingerprint(contract):raise ValueError('Native Map normal proof not bound to original task/start/reference')
    generic(base_contract(contract),{**proof,'contract_fingerprint':contract_fingerprint(base_contract(contract))})
    expected={'positive':'success','restored_positive':'success',
       **{name:'failure'for name in ('initial_no_op','wrong_target','404','login')+control_names(contract['completion']['map_native_navigation'])}}
    if not all(any(row.get('task_id')==contract['task_id']and row.get('native_reference_verified')is True and
        row.get('original_initial_view_verified')is True and all(row.get('checks',{}).get(k)==v for k,v in expected.items())
        for row in cycle.get('tasks',[]))for cycle in proof.get('cycles',[])):
        raise ValueError('Native Map requires full normal original-start visibility/area controls in both deployments')


def normal_controls(browser,site,contract,capture_current):
    """Use actual native links/forms privately; never an actor policy."""
    from .browser_request_policy import install_local_network_policy
    from .map_editor_navigation import authenticate
    from .map_view import wait_native_view
    from probe_map_local_capabilities import follow,visit
    spec=validate(contract['completion']['map_native_navigation']);verify_reference(contract)
    ctx=browser.new_context(viewport={'width':1280,'height':720},locale='en-US',extra_http_headers={'Accept-Language':'en-US'})
    install_local_network_policy(ctx,site.allowed_netlocs)
    cases={};details={'native_reference_verified':True,'original_initial_view_verified':False}
    def snapshot(page,response=None):
        native=read_terminal(page)
        return {**capture_current(page,'map',response=response),'map_native_navigation':native}
    try:
        page=ctx.new_page();page.set_default_timeout(15000)
        if spec['kind']=='upload_form':authenticate(page,site)
        status=visit(page,site,contract['start_path'])
        original=urlsplit(contract['start_path'])
        if original.path in ('/','/directions','/search'):
            initial=wait_native_view(page,contract['start_path'])
            details['initial_native_view']=initial
            if spec['initial_area']is not None and not same_center(spec['initial_area'],geo_triplet(initial)):
                raise RuntimeError('Original initial area differs from independent native references')
        details['original_initial_view_verified']=True
        cases['initial_no_op']=snapshot(page)
        if spec['kind']=='upload_form':
            follow(page,site,'/traces')
        _,native=follow(page,site,KINDS[spec['kind']][0])
        details['private_observed_native_target']=native
        cases['positive']=snapshot(page)
        selector='#map'if spec['kind']=='home'else'#new_trace'if spec['kind']=='upload_form'else'form.export_form'
        if spec['kind']=='upload_form':
            selector='form:has(input[name="trace[gpx_file]"])'
        page.locator(selector).evaluate("e=>e.style.display='none'")
        name='hidden_native_map'if spec['kind']=='home'else'hidden_native_form'
        cases[name]=snapshot(page)
        page.locator(selector).evaluate("e=>e.style.display=''")
        cases['restored_positive']=snapshot(page)
        if spec['kind']=='export_area':
            other=ctx.new_page();z,lat,lon=spec['initial_area'];lat=lat-2 if lat>=0 else lat+2
            start='/#map='+ '/'.join(map(str,(z,lat,lon)))
            visit(other,site,start);wait_native_view(other,start);follow(other,site,'/export')
            cases['wrong_native_area']=snapshot(other);other.close()
        for name,path in (('wrong_target',contract['wrong_target_path']),('404','/__map_native_control_not_found__')):
            other=ctx.new_page();visit(other,site,path);cases[name]=snapshot(other);other.close()
        anonymous=browser.new_context(viewport={'width':1280,'height':720},locale='en-US')
        try:
            install_local_network_policy(anonymous,site.allowed_netlocs)
            other=anonymous.new_page();visit(other,site,'/login');cases['login']=snapshot(other)
        finally:
            anonymous.close()
    finally:
        ctx.close()
    return cases,details
