"""Typed native turn-by-turn readout from a pinned route, without actor-path rules."""
import re
from .map_route import backend_reference, read_route, route_checks, route_path
from .site_query_rules import reference_fingerprint

FIELDS={'steps':'record_set'}
RECORD_FIELDS={'steps':{'number':'integer','instruction':'string'}}


def parse_steps(rows):
    if not isinstance(rows,list) or not rows:raise ValueError('Missing native directions')
    records=[]
    for index,row in enumerate(rows,1):
        if not isinstance(row,str):raise ValueError('Invalid native direction row')
        # Native table has icon, numbered instruction, displayed distance.
        match=re.fullmatch(r'\s*(\d+)\. ([^\t\n]+)\t([^\t\n]*)',row)
        if not match or int(match[1])!=index:raise ValueError('Missing or nonsequential native direction row')
        instruction=' '.join(match[2].split());distance=match[3].strip()
        if not instruction or (distance and not re.fullmatch(r'\d+(?:\.\d+)?\s*(?:km|m)',distance)):
            raise ValueError('Malformed instruction or native distance')
        records.append({'number':index,'instruction':instruction})
    return {'steps':records}


def validate(q):
    if q.get('family')!='map_route_steps' or q.get('fields')!=FIELDS or q.get('record_fields')!=RECORD_FIELDS:
        raise ValueError('Explicit numbered native direction schema required')
    spec=q.get('route',{})
    if len(spec.get('alternatives',[]))!=1 or len(spec.get('pair',[]))!=2:
        raise ValueError('One explicit route and transport mode required')
    ref=spec['alternatives'][0]
    if q.get('reference_path')!=route_path(spec['pair'],ref['profile']):
        raise ValueError('Route readout reference path mismatch')
    parse_steps(ref['native']['rows'])


def reference(site,q):
    validate(q);spec=q['route'];ref=spec['alternatives'][0]
    live=backend_reference(site,spec['pair'],ref['profile'])
    if live!=ref['backend']:raise ValueError('Pinned route changed')
    return {'object_id':'map-route-steps:'+reference_fingerprint({'pair':spec['pair'],'profile':ref['profile']}),
            'values':parse_steps(ref['native']['rows']),
            'evidence':{'route_backend':reference_fingerprint(live),'rendered_rows':reference_fingerprint(ref['native']['rows'])}}


def ui_values(page,q,*,evidence=None):
    from urllib.parse import urlsplit
    from .browser_page_wait import READY,probe_args
    validate(q);origin=urlsplit(page.url);spec=q['route']
    page.goto(origin.scheme+'://'+origin.netloc+q['reference_path'],wait_until='domcontentloaded',timeout=60000)
    page.wait_for_function("() => document.querySelectorAll('#sidebar_content tr.turn').length > 0",timeout=30000)
    page.wait_for_function(READY,arg=probe_args('map'),timeout=8000,polling=100)
    observed=read_route(page)
    if not all(route_checks(spec,observed,page.url).values()):raise ValueError('Wrong or incomplete rendered route')
    values=parse_steps(observed['rows'])
    if evidence is not None:evidence.append({'url':page.url,'native':observed,'values':values})
    return values
