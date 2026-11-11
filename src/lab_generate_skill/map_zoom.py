"""Terminal native map zoom checks, separated from public actor observations.

Supports relative zoom operations only. Export readiness, geography-specific
street detail, map scale answers and external providers are separate contracts.
"""
from urllib.parse import urlsplit
from .map_view import native_zoom, zoom_checks
from .site_navigation_rules import valid_initial_page
from .site_query_rules import reference_fingerprint

VERSION='map-relative-zoom-v1'
ADMISSION_VERSION='map-relative-zoom-admission-v1'


def validate(c):
    s=c.get('map_zoom')
    if c.get('domain')!='map' or not isinstance(s,dict) or set(s)!={'direction'} or s['direction'] not in ('in','out','change'):
        raise ValueError('Explicit relative map zoom required')
    u=urlsplit(c['start_path'])
    if u.scheme or u.netloc or u.path not in ('/','/search','/directions') or not u.fragment:
        raise ValueError('An explicit local initial map view is required')


def fingerprint(c):
    return reference_fingerprint({k:c.get(k) for k in ('task_id','source_task_id','domain','goal','start_path','map_zoom','heldout_quarantine','start_revision','goal_revision')})


def expected_controls(c):
    validate(c)
    out={k:'failure' for k in ('no_op','url_only','share_input_only','404','login')}
    if c['map_zoom']['direction']!='change':out['opposite_direction']='failure'
    return out|{'positive':'success'}


def evaluate(c,page,initial,final,*,site_origin,runtime_error=None):
    validate(c)
    def unknown(reason):return {'version':VERSION,'status':'unknown','reward':None,'checks':{},'reason':reason}
    if runtime_error:return unknown('Environment or inference error')
    if not isinstance(page,dict) or type(page.get('http_status')) is not int or not 200<=page['http_status']<500:
        return unknown('Missing terminal page or transport/server error')
    try:native_zoom(initial)
    except (ValueError,TypeError):return unknown('Missing or inconsistent initial native map state')
    if not isinstance(final,dict) or type(final.get('map_visible')) is not bool:
        return unknown('Missing terminal native map capture')
    checks={'page_valid':valid_initial_page(page,site_origin=site_origin),'map_view_present':final['map_visible']}
    if all(checks.values()):
        try:checks.update(zoom_checks(c['map_zoom']['direction'],initial,final))
        except (ValueError,TypeError):return unknown('Inconsistent terminal native map signals')
    passed=all(checks.values())
    return {'version':VERSION,'status':'success' if passed else 'failure','reward':float(passed),'checks':checks,'reason':None}


def feedback(j):
    descriptions={'page_valid':'The final document is a valid page on the task website.',
        'map_view_present':'The native map is visible.',
        'map_tiles_present':'The map has rendered native tiles.',
        'requested_zoom_change':'The final native zoom changed in the direction requested by the task.'}
    return {'status':j['status'],'reward':j['reward'],'reason':j.get('reason'),
        'checks':[{'name':k,'passed':v,'condition':descriptions[k]} for k,v in j['checks'].items()],
        'action_sequence_provided':False,'reference_values_provided':False}


def require_admission(c,proof):
    validate(c)
    if c.get('heldout_quarantine') or proof.get('admission_version')!=ADMISSION_VERSION or proof.get('contract_fingerprint')!=fingerprint(c):
        raise ValueError('Quarantined or stale map zoom admission')
    cycles=proof.get('cycles',[])
    if not proof.get('passed') or len(cycles)!=2 or proof.get('reset_mode')!='independent_full_geographic_deployments':
        raise ValueError('Two independent full native deployments required')
    for r in cycles:
        native_zoom(r.get('initial_view'))
        if not r.get('passed') or r.get('checks')!=expected_controls(c) or not r.get('full_reset_verified'):
            raise ValueError('Incomplete native zoom controls/reset')
        if not r.get('initial_fingerprint') or r['initial_fingerprint']!=r.get('final_fingerprint'):
            raise ValueError('Map baseline changed')
    if cycles[0]['initial_fingerprint']!=cycles[1]['initial_fingerprint'] or cycles[0]['initial_view']['native_geo_uri']!=cycles[1]['initial_view']['native_geo_uri']:
        raise ValueError('Independent initial map baselines disagree')
