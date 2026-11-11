"""Bounded warming of native tiles requested by an initial public viewport.

No future target, evaluator reference, browser action or synthetic map content.
mod_tile may return 404 while a cold render continues; only a real native PNG
counts as ready. Used by capability controls, initial-view preparation and
terminal place capture after a native tile readiness timeout.
"""
from concurrent.futures import ThreadPoolExecutor,wait,FIRST_COMPLETED
import hashlib,re,time,urllib.request,urllib.error
from urllib.parse import urlsplit
from .io_utils import atomic_write_json


def requires_initial_tiles(contract):
    """Public capability needs rendered initial tiles, independent of task ID."""
    if contract.get('surface', {}).get('kind') in ('named_png', 'initial_png'):
        # The first PNG observation requires real initial viewport tiles.
        # Reuse bounded native startup warming; never warm the export target.
        return True
    if contract.get('candidate_completion', {}).get('family') == 'base_layer_comparison':
        # Comparing two rendered styles requires the initial Standard view to
        # exist before the first decision. A renderer socket/sample tile alone
        # does not establish readiness for this viewport.
        return True
    if contract.get('map_zoom'):
        return True
    if contract.get('map_geolocation') and urlsplit(contract['start_path']).path=='/':
        return True
    return bool(contract.get('map_native_facts') and
                contract.get('protocol',{}).get('kind') in
                ('current_view_share','initial_where_is_this'))


def tile_path(value):
    if not isinstance(value,str):raise ValueError('Native tile path required')
    m=re.fullmatch(r'/tile/(\d+)/(\d+)/(\d+)\.png',value)
    if not m:raise ValueError('Unsupported tile path')
    z,x,y=map(int,m.groups())
    if not 0<=z<=20 or not 0<=x<2**z or not 0<=y<2**z:raise ValueError('Tile coordinates outside native range')
    return value


def warm_tiles(base,paths,report,*,seconds=180):
    origin=urlsplit(base)
    if origin.scheme!='http' or origin.hostname!='127.0.0.1' or not origin.port or origin.username or origin.password or origin.path or origin.query or origin.fragment:
        raise ValueError('Only the current private native tile service is allowed')
    paths=list(dict.fromkeys(tile_path(p) for p in paths))
    if not paths or len(paths)>128:raise ValueError('Missing or excessive current viewport tiles')
    start=time.monotonic();end=start+seconds;records={}
    def fetch(path):
        attempts=[]
        while time.monotonic()<end:
            began=time.monotonic()
            try:
                with urllib.request.urlopen(base+path,timeout=min(35,max(.1,end-began))) as response:data=response.read()
                if not data.startswith(b'\x89PNG\r\n\x1a\n'):raise ValueError('Native tile response is not a PNG')
                return {'ready':True,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),
                        'seconds':time.monotonic()-start,'cold_responses':attempts}
            except urllib.error.HTTPError as exc:
                attempts.append({'status':exc.code,'seconds':time.monotonic()-began})
                if exc.code!=404:raise
                # A cached missing/invalid tile must not cause a hot retry loop.
                time.sleep(min(.1,max(0,end-time.monotonic())))
        return {'ready':False,'seconds':time.monotonic()-start,'cold_responses':attempts}
    with ThreadPoolExecutor(max_workers=min(8,len(paths))) as pool:
        pending={pool.submit(fetch,path):path for path in paths}
        while pending:
            finished,_=wait(pending,timeout=5,return_when=FIRST_COMPLETED)
            for f in finished:
                path=pending.pop(f)
                try:records[path]=f.result()
                except Exception as exc:records[path]={'ready':False,'error_type':type(exc).__name__}
            atomic_write_json(report,{'ready':len(records)==len(paths) and all(r['ready'] for r in records.values()),
                'requested_tiles':len(paths),'completed_tiles':len(records),'seconds':time.monotonic()-start,
                'records':records,'actor_actions_added':0,'task_reference_used':False})
    if not all(r['ready'] for r in records.values()):raise TimeoutError('Initial native tile rendering did not complete in its startup budget')
    return records


def warm_initial_view(context,site,path,report):
    target=urlsplit(path)
    if target.scheme or target.netloc or target.path not in ('/','/search','/directions') or not re.search(r'(?:^|&)map=\d+/[-\d.]+/[-\d.]+(?:&|$)',target.fragment):
        raise ValueError('This capability probe warms explicit local initial map views only')
    page=context.new_page()
    try:
        page.goto(site.url+path,wait_until='domcontentloaded',timeout=60000)
        from .map_view import wait_native_view
        wait_native_view(page,path)
        page.wait_for_function("() => document.querySelector('#long_input')?.value && document.querySelectorAll('img.leaflet-tile').length>0",timeout=30000)
        urls=page.locator('img.leaflet-tile').evaluate_all('es=>es.filter(e=>e.getClientRects().length).map(e=>e.src)')
        origin=urlsplit(site.tile_url);paths=[]
        for url in urls:
            u=urlsplit(url)
            if (u.scheme,u.netloc)!=(origin.scheme,origin.netloc) or u.query or u.fragment:
                raise ValueError('Current viewport uses an undeclared tile provider')
            paths.append(tile_path(u.path))
        return warm_tiles(site.tile_url,paths,report)
    finally:page.close()


def warm_current_view(page,site,report,*,seconds=180):
    """Retry only the currently displayed native tiles, including terminal capture.

    Does not navigate, pan, zoom, reload the document, or read a task target.
    No model decision or task-specific action is inserted.
    """
    from .map_view import read_map_view
    before=read_map_view(page)
    urls=page.locator('img.leaflet-tile').evaluate_all(
        'es=>es.filter(e=>e.getClientRects().length).map(e=>e.src)')
    origin=urlsplit(site.tile_url);paths=[]
    for url in urls:
        u=urlsplit(url)
        if (u.scheme,u.netloc)!=(origin.scheme,origin.netloc) or u.query or u.fragment:
            raise ValueError('Current viewport uses an undeclared tile provider')
        paths.append(tile_path(u.path))
    records=warm_tiles(site.tile_url,paths,report,seconds=seconds)
    after=read_map_view(page)
    if any(before.get(k)!=after.get(k) for k in ('native_geo_uri','native_long_link')):
        raise ValueError('Map moved during current-view rendering')
    # mod_tile's earlier 404 may have already fired Leaflet's tileerror. Once
    # native rendering is ready, retry that same image URL without reloading
    # the page or resetting unrelated forms and controls.
    retried=page.locator('img.leaflet-tile').evaluate_all('''(es, urls) => {
        let n=0;
        for(const e of es) if(urls.includes(e.src) && e.complete && e.naturalWidth===0) {
            e.src=e.src; n++;
        }
        return n;
    }''',urls)
    page.wait_for_function('''urls => {
        const es=[...document.querySelectorAll('img.leaflet-tile')].filter(e=>urls.includes(e.src));
        return es.length>0 && es.every(e=>e.complete && e.naturalWidth>0);
    }''',arg=urls,timeout=15000)
    return {'requested_tiles':len(records),'retried_failed_images':retried,
            'page_reload':False,'actor_actions_added':0,'task_reference_used':False,
            'before':before,'after':read_map_view(page)}


def warm_browser_initial_view(site,path,report):
    """Use BrowserGym's manager while keeping warmup browser state separate.

    BrowserGym deliberately retains its global sync Playwright manager after an
    episode. Starting another sync manager then raises an asyncio-loop error.
    Own and close only the disposable warmup browser, never BrowserGym's manager.
    """
    from browsergym.core import _get_global_playwright
    from .browser_request_policy import install_local_network_policy
    pw=_get_global_playwright()
    browser=pw.chromium.launch(headless=True)
    try:
        context=browser.new_context(viewport={'width':1280,'height':720})
        install_local_network_policy(context,site.allowed_netlocs)
        return warm_initial_view(context,site,path,report)
    finally:
        browser.close()
