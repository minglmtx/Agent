"""Pinned native layout alternatives for current-area History navigation.

Do not broaden geographic tolerance. The default center and independently
replayed sidebar center are two finite, versioned alternatives at the same zoom.
"""
import hashlib
import json
import math
from pathlib import Path
from urllib.parse import urlsplit,parse_qs


def view(state):
    values=parse_qs(urlsplit(state['history']['native_long_link']).fragment).get('map',[])
    if len(values)!=1:raise ValueError('Missing unambiguous native view')
    parts=list(map(float,values[0].split('/')))
    if len(parts)!=3 or not all(math.isfinite(x)for x in parts):raise ValueError('Invalid native view')
    return parts


def matches(a,b):
    return a[0]==b[0] and abs(a[1]-b[1])<=.001 and abs(a[2]-b[2])<=.001


def verified_views(probe):
    """Check two independent native click/direct/wrong-region control records."""
    probe=Path(probe);cycles=[];evidence=[]
    for i in range(2):
        root=probe/str(i)/'probe';result_path=root/'result.json';states_path=root/'states.json'
        result=json.loads(result_path.read_text());states=json.loads(states_path.read_text())
        if result.get('passed')is not True or not result.get('initial_fingerprint')or result['initial_fingerprint']!=result.get('final_fingerprint'):
            raise ValueError('Independent native replay or state integrity failed')
        click=states['native_click'];direct=states['direct'];wrong=states['wrong_area']
        initial=view(click['initial']);after=view(click['final']);canonical=view(direct['final'])
        old_layout=click['initial']['layout'];new_layout=click['final']['layout']
        if not matches(initial,canonical)or initial[0]!=after[0]or abs(initial[1]-after[1])>.001:
            raise ValueError('Replay changed more than native horizontal layout')
        if old_layout['direction']!='ltr' or new_layout['direction']!='ltr' or old_layout['viewport']!=new_layout['viewport']:
            raise ValueError('Unverified layout direction or viewport')
        removed=old_layout['map']['width']-new_layout['map']['width']
        shift=(after[2]-initial[2])*256*2**initial[0]/360
        if removed<=0 or abs(shift-removed/2)>1 or new_layout['map']['x']-old_layout['map']['x']!=removed:
            raise ValueError('Native movement does not match sidebar layout within one projected pixel')
        for case in (click,direct,wrong):
            if not all(case['evaluation'].get(k)is True for k in ('native_public_list_identity','native_list_finished_loading','native_history_area_loaded')):
                raise ValueError('Native history did not load for all controls')
        if any(matches(view(wrong['final']),v)for v in (initial,after)):
            raise ValueError('Wrong-area control did not exercise a distinct geographic area')
        source=Path(result['native_layout_source']['file'])
        if hashlib.sha256(source.read_bytes()).hexdigest()!=result['native_layout_source']['sha256']:
            raise ValueError('Native layout implementation changed')
        cycles.append({'views':[canonical,after],'viewport':old_layout['viewport'],
                       'fingerprint':result['initial_fingerprint'],'layout_source':result['native_layout_source']})
        evidence.extend({'file':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}for p in (result_path,states_path))
    if cycles[0]!=cycles[1]:raise ValueError('Native history layout differs across independent resets')
    return {'version':'native-history-sidebar-v1',**cycles[0],'proof_directory':str(probe),'evidence':evidence}


def verify_reference(spec):
    reference=spec.get('native_area_reference')
    if not reference:return
    if not spec.get('initial_map')or reference!=verified_views(reference['proof_directory']):
        raise ValueError('Native area reference is stale or unverified')
    if not matches(spec['initial_map'],reference['views'][0]):raise ValueError('Area reference belongs to another task start')


def area_matches(spec,actual):
    candidates=[spec['initial_map']]
    reference=spec.get('native_area_reference')
    if reference:
        if reference.get('version')!='native-history-sidebar-v1' or len(reference.get('views',[]))!=2 or not matches(spec['initial_map'],reference['views'][0]):
            raise ValueError('Invalid calibrated history area reference')
        candidates=reference['views']
    return any(matches(actual,expected)for expected in candidates)
