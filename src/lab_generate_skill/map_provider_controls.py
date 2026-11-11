"""Native provider controls shared by component and full worker validation."""
import hashlib
import io
import time
from PIL import Image
from .map_frozen_provider_runtime import provider_checks
from .map_route import read_route
from .browser_request_policy import install_local_network_policy
from .runtime_watchdog import deadline_scope
from .runtime_diagnostics import failure_diagnostic
from .map_local_surface_controls import read_surface


def exercise_provider(browser,site,server,c,deadline_path):
    start=time.monotonic();rows={};contexts=[]
    record=dict(source_task_id=c['source_task_id'],task_id=c['task_id'],
        start_path=c['start_path'],controls=rows,passed=False)
    blank=io.BytesIO();Image.new('RGBA',(256,256),(0,0,0,0)).save(blank,format='PNG')
    try:
        with deadline_scope('provider_source',180,result_path=deadline_path,task_id=c['source_task_id']):
            provider=c['candidate_completion']['provider']
            def new_page(fault=None):
                ctx=browser.new_context(viewport={'width':1280,'height':720}); contexts.append(ctx)
                install_local_network_policy(ctx,site.allowed_netlocs)
                if fault=='blank': ctx.route(server.url+'/tiles/**',lambda route:route.fulfill(status=200,content_type='image/png',body=blank.getvalue()))
                if fault=='blocked': ctx.route(server.url+'/tiles/**',lambda route:route.abort())
                page=ctx.new_page(); page.set_default_timeout(10000); hashes={}
                def response(r):
                    if r.url.startswith(server.url+'/tiles/') and r.status==200:
                        try: hashes[r.url]=hashlib.sha256(r.body()).hexdigest()
                        except Exception: hashes[r.url]='body_unavailable'
                page.on('response',response)
                page.goto(site.url+c['start_path'],wait_until='load',timeout=60000)
                page.wait_for_function("() => typeof window.__labFrozenProviderState==='function' && window.__labFrozenProviderState().active.length===1",timeout=15000)
                if c['candidate_completion']['retain_initial_route']:
                    page.wait_for_function("() => document.querySelectorAll('#sidebar_content tr.turn').length>0 && !jQuery.active",timeout=30000)
                return page, hashes
            def state(page): return page.evaluate('() => window.__labFrozenProviderState()')
            def select(page,label):
                if not page.locator('.layers-ui').is_visible(): page.locator('.control-layers .control-button').click()
                # Native CSS hides the radio; the visible label bubbles
                # its click to the original list-item layer handler.
                # Do not force a click or modify Leaflet state in JS.
                target=page.locator('.base-layers label').filter(has_text=label)
                if target.count()!=1 or target.inner_text().strip()!=label:
                    raise ValueError('Unique exact native provider label required')
                target.click()
                if not target.locator('input[type=radio]').is_checked():
                    raise ValueError('Native layer selection did not update radio state')
            page,hashes=new_page(); initial=state(page); route=read_route(page)
            if [x['code'] for x in initial['active']]!=['M']: raise ValueError('Expected initial Standard layer')
            record['initial']=initial; record['initial_route']=route
            if c['candidate_completion']['retain_initial_route']:
                from .map_route_initialization_binding import initial_url_state
                from .map_route import parse_point, pair_equal, LABELS
                pair,mode=initial_url_state(c['start_path'])
                expected_pair=[[float(v)for v in point]for point in pair]
                if (not route['route_visible'] or route['loading'] or not route['rows'] or
                    route['engine']!=LABELS[mode] or not pair_equal(
                        [parse_point(route['origin']),parse_point(route['destination'])],expected_pair)):
                    raise ValueError('Initial route differs from declared start')
            else:
                from .map_metadata_query import initial_view
                from .map_local_capabilities import same_center
                if not same_center(initial_view(c['start_path']),
                        (initial['zoom'],initial['center']['lat'],initial['center']['lng'])):
                    raise ValueError('Initial geographic view differs from declared start')
            page.locator('.control-layers .control-button').click()
            def save(name,page,hashes,expected):
                terminal=state(page); checks=provider_checks(initial,terminal,provider,server,hashes)
                current=None
                if c['candidate_completion']['retain_initial_route']:
                    current=read_route(page)
                    checks['route_retained']=current['route_visible'] and all(current[k]==route[k] for k in ('origin','destination','engine','rows'))
                actual=all(checks.values()); rows[name]=dict(checks=checks,expected=expected,actual=actual,
                    terminal=terminal,response_sha256=dict(hashes),url=page.url)
                if current is not None:rows[name]['terminal_route']=current
                if actual is not expected: raise ValueError('Native provider control mismatch: '+name)
            save('catalog_only',page,hashes,False)
            select(page,'Humanitarian' if provider=='hot' else 'Satellite')
            until=time.monotonic()+30
            while not all(provider_checks(initial,state(page),provider,server,hashes).values()) and time.monotonic()<until:
                page.wait_for_timeout(100)
            save('genuine_loaded_provider',page,hashes,True)
            select(page,'Standard'); save('wrong_provider',page,hashes,False)
            for fault in ('blank','blocked'):
                other,other_hashes=new_page(fault)
                select(other,'Humanitarian' if provider=='hot' else 'Satellite')
                other.wait_for_timeout(1000)
                save(fault,other,other_hashes,False)
            record['passed']=True
    except Exception as error:
        record['diagnostic']=failure_diagnostic(error,'native_provider_source')
        if contexts and contexts[0].pages:
            try:record['failure_surface']=read_surface(contexts[0].pages[0])
            except Exception as capture_error:record['failure_surface_error']=failure_diagnostic(capture_error,'surface_capture')
    finally:
        for ctx in contexts:ctx.close()
        record['seconds']=time.monotonic()-start
    return record
