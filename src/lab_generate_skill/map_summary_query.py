"""Private route-summary references using the native OSM display convention.

The actor receives only the original goal and typed answer fields. Native
route references and control URLs are used exclusively by the evaluator.
"""
import math
import re
from decimal import Decimal, ROUND_HALF_UP
from .map_route import backend_reference,read_route,route_checks
from .site_query_rules import reference_fingerprint


def native_display_values(backend):
    distance=backend['distance'];duration=backend['duration']
    if any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) or x<0 for x in (distance,duration)):
        raise ValueError('Invalid native route summary')
    # Native directions.js formatDistance / formatTime. Preserve displayed
    # precision, not the more precise private routing-engine values.
    if distance<1000:km=Decimal(math.floor(distance+0.5))/1000
    elif distance<10000:km=Decimal.from_float(distance/1000).quantize(Decimal('0.1'),rounding=ROUND_HALF_UP)
    else:km=Decimal(math.floor(distance/1000+0.5))
    return {'distance_km':str(km),'duration_minutes':math.floor(duration/60+0.5)}


def parse_display_values(summary):
    matches=re.findall(r'\bDistance:\s*(\d+(?:\.\d+)?)\s*(km|m)\.\s*Time:\s*(\d+):([0-5]\d)\.',summary)
    if len(matches)!=1:raise ValueError('Missing or ambiguous native distance/time summary')
    number,unit,hours,minutes=matches[0]
    return {'distance_km':str(Decimal(number)/(1000 if unit=='m' else 1)),
            'duration_minutes':int(hours)*60+int(minutes)}


def validate_query(query):
    if query.get('family')!='map_route_summary' or not query.get('routes') or not query.get('fields'):
        raise ValueError('Unsupported map summary query')
    used={}
    for item in query['routes']:
        spec=item['route']
        if len(spec['alternatives'])!=1 or not item['outputs']:
            raise ValueError('A summary reference must identify one explicit route mode')
        for output,metric in item['outputs'].items():
            if output in used or metric not in ('distance_km','duration_minutes'):
                raise ValueError('Unknown or duplicate summary output')
            used[output]='decimal' if metric=='distance_km' else 'integer'
    if used!=query['fields']:raise ValueError('Summary outputs do not match public answer schema')


def reference(site,query):
    validate_query(query);values={};objects=[]
    for item in query['routes']:
        spec=item['route'];ref=spec['alternatives'][0]
        live=backend_reference(site,spec['pair'],ref['profile'])
        if live!=ref['backend']:raise ValueError('Pinned routing reference changed')
        displayed=native_display_values(live)
        values.update({out:displayed[key] for out,key in item['outputs'].items()})
        objects.append({'pair':spec['pair'],'profile':ref['profile'],'backend':reference_fingerprint(live)})
    return {'object_id':'map-route-summary:'+reference_fingerprint(objects),'values':values,
            'evidence':{'native_routes':objects,'reference_precision':'native English displayed summary'}}


def ui_values(page,query,*,evidence=None):
    """CPU control only: independently navigate and read each required route."""
    from urllib.parse import urlsplit
    from .map_route import route_path
    validate_query(query);origin=urlsplit(page.url);origin=origin.scheme+'://'+origin.netloc;values={}
    for item in query['routes']:
        spec=item['route'];ref=spec['alternatives'][0]
        page.goto(origin+route_path(spec['pair'],ref['profile']),wait_until='domcontentloaded',timeout=60000)
        page.wait_for_function("() => document.querySelectorAll('#sidebar_content tr.turn').length > 0",timeout=30000)
        from .browser_page_wait import READY,probe_args
        page.wait_for_function(READY,arg=probe_args('map'),timeout=8000,polling=100)
        state=read_route(page)
        if not all(route_checks(spec,state,page.url).values()):raise ValueError('Rendered summary belongs to an incorrect or incomplete native route')
        observed=parse_display_values(state['summary'])
        if evidence is not None:evidence.append({'url':page.url,'native':state,'displayed_values':observed})
        values.update({out:observed[key] for out,key in item['outputs'].items()})
    return values
