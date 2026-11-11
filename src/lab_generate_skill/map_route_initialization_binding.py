"""Explicit training start revisions, never an original-evaluation equivalence.

Goals and endpoint requirements remain unchanged. An initial route must come
from independently identified named places or the exact first recorded page.
Only the common source mapping changes; this module executes no browser action.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import parse_qs, urlsplit

from .map_route_normal_capture import exact_pair, fingerprint, point
from .source_revision_binding import binding, local_path, require_source_binding

VERSION = 'map-declared-initial-route-training-v1'
KINDS = {'recorded-initial-route-alias-v1', 'goal-named-initial-route-v1'}
ENGINES = {'fossgis_osrm_car':'car', 'fossgis_osrm_bike':'bike', 'fossgis_osrm_foot':'foot'}


def initial_url_state(path):
    parsed = urlsplit(path)
    values = parse_qs(parsed.query, keep_blank_values=True)
    if (parsed.scheme or parsed.netloc or parsed.path != '/directions'
            or set(values) != {'engine','route'}
            or any(len(v)!=1 for v in values.values())
            or values['engine'][0] not in ENGINES):
        raise ValueError('Explicit local initial route and native engine required')
    parts = values['route'][0].split(';')
    if len(parts)!=2:
        raise ValueError('Two complete initial endpoints required')
    pair = [[str(v) for v in point(part.split(','))] for part in parts]
    if pair[0]==pair[1]:
        raise ValueError('Initial route endpoints must be distinct')
    return pair, ENGINES[values['engine'][0]]


def recorded_first_start(source):
    revision = source['initialization_revision']
    locator = revision.get('published_source_locator', {})
    if (revision.get('version')!='recorded-initial-route-alias-v1'
            or locator.get('trace_id') not in source['source_trace_ids']
            or type(locator.get('byte_offset'))is not int or locator['byte_offset']<0
            or type(locator.get('byte_length'))is not int or locator['byte_length']<=0):
        raise ValueError('Exact original trace locator required')
    with Path(locator['source_file']).open('rb') as stream:
        stream.seek(locator['byte_offset'])
        raw = stream.read(locator['byte_length'])
    if hashlib.sha256(raw).hexdigest()!=locator.get('line_sha256'):
        raise ValueError('Original recorded first-page evidence changed')
    trace = json.loads(raw)
    if (trace.get('trace_id')!=locator['trace_id'] or trace.get('domain')!='map'
            or trace.get('task_instruction')!=source['goal']):
        raise ValueError('Recorded trace is not the bound original task')
    message = trace.get('messages',[{}])[0]
    if message.get('role')!='user' or message.get('turn')!=0:
        raise ValueError('The first recorded observation is required, not a later action')
    observation = json.loads(message['content'])
    first_line = observation['axtree'].splitlines()[0]
    match = re.search(r"\burl='([^']+)'", first_line)
    if not match or match[1]!=revision.get('published_first_observed_url'):
        raise ValueError('Exact first recorded AX document URL required')
    path = local_path(match[1])
    if path!=revision.get('selected_start'):
        raise ValueError('Selected start differs from the original first recorded document')
    return path


def source_definition(c):
    mapping = c.get('training_initialization')
    if not isinstance(mapping,dict) or mapping.get('version')!=VERSION:
        raise ValueError('Explicit training initialization mapping required')
    source = mapping.get('source_route_definition')
    if (not isinstance(source,dict) or 'training_initialization' in source
            or fingerprint(source)!=mapping.get('source_route_definition_sha256')):
        raise ValueError('Complete unchanged source route definition required')
    return source


def validate(c):
    source = source_definition(c)
    mapping = c['training_initialization']
    revision = source.get('initialization_revision') or {}
    if (revision.get('version') not in KINDS or revision.get('equivalence_claim') is not False
            or source.get('task_text_revision') is not None
            or c.get('task_id')!=c['source_task_id']+'--initial-route-v1'
            or c.get('is_explicit_derivative') is not True
            or c.get('original_evaluation_equivalence') is not False
            or c.get('goal')!=source.get('goal') or c.get('original_goal')!=source.get('goal')
            or c.get('task_text_revision') is not None):
        raise ValueError('Only a documented initial-state revision with unchanged goal is supported')
    binding(c)
    if (revision.get('original_start')!=c['recorded_start_paths'][0]
            or c.get('source_task_id')!=source.get('source_task_id')
            or any(c.get(k)!=source.get(k) for k in (
                'source_trace_ids','original_binding_sha256','endpoint_request','allowed_modes',
                'completion_kind','optimization_scope'))):
        raise ValueError('Source identity, original route goal or completion semantics changed')
    pair, mode = initial_url_state(c['start_path'])
    if not exact_pair(pair,mapping.get('initial_pair')) or mode!=mapping.get('initial_mode') or mode not in c['allowed_modes']:
        raise ValueError('Initial URL differs from the declared native pair/mode')
    expected = dict(revision, selected_start=c['start_path'], binding_version=VERSION)
    if c.get('initialization_revision')!=expected:
        raise ValueError('Initialization provenance was rewritten')
    if revision['version']=='recorded-initial-route-alias-v1':
        if c['start_path']!=recorded_first_start(source):
            raise ValueError('Recorded initialization must preserve the exact first page')
        if source['endpoint_request'].get('kind')!='exact_points' or not exact_pair(pair,source['endpoint_request'].get('pair')):
            raise ValueError('Recorded initial pair differs from the task route')
    elif source['endpoint_request'].get('kind')!='reverse_named_initial_route':
        raise ValueError('Named route initialization requires the original reversal request')
    return mapping


def validate_initial_spec(c, spec, named_endpoint_evidence=None):
    mapping = validate(c)
    if not isinstance(spec,dict) or not exact_pair(spec.get('pair'),mapping['initial_pair']):
        raise ValueError('Actual independently rendered initial-route reference required')
    alternatives = spec.get('alternatives')
    if (not isinstance(alternatives,list) or not alternatives
            or any(r.get('profile')!=mapping['initial_mode'] or not r.get('backend') or not r.get('native') for r in alternatives)):
        raise ValueError('Initial engine, full backend response and native rendered state required')
    if c['endpoint_request']['kind']=='reverse_named_initial_route':
        from .map_route_reference_variants import declared_pairs
        targets = declared_pairs(c,named_endpoint_evidence)
        if len(targets)!=1 or not exact_pair(list(reversed(targets[0])),mapping['initial_pair']):
            raise ValueError('Named initial route must match the independently identified original places')
    return mapping


def require_initial_reference(c, proof):
    mapping = validate_initial_spec(c,proof.get('initial_rendered_route_spec'),proof.get('named_endpoint_evidence'))
    from .map_route_normal_capture import complete_route
    ref = proof.get('initial_native_reference')
    if (not isinstance(ref,dict) or ref.get('independent_native_read') is not True
            or not re.fullmatch(r'[0-9a-f]{64}',str(ref.get('native_reference_receipt_sha256','')))
            or ref.get('profile')!=mapping['initial_mode']
            or not exact_pair(ref.get('pair'),mapping['initial_pair'])
            or ref.get('native_body_sha256')!=fingerprint(ref.get('native_body'))
            or ref.get('scope',{}).get('allowed_modes')!=[mapping['initial_mode']]
            or not exact_pair(ref['scope'].get('pinned_request_pair'),mapping['initial_pair'])):
        raise ValueError('Complete independent initial native route response required')
    body=complete_route(ref['native_body'])
    if any(alt['backend']!=body for alt in proof['initial_rendered_route_spec']['alternatives']):
        raise ValueError('Rendered initial reference differs from its independent native response')
    return mapping


def bind_initial_route(source, inventory, initial_route_spec, *, named_endpoint_evidence=None):
    revision = source.get('initialization_revision') or {}
    if revision.get('version') not in KINDS:
        raise ValueError('No complete declared initial-state repair exists for this source')
    c = deepcopy(source)
    if revision['version']=='recorded-initial-route-alias-v1':
        start = recorded_first_start(source)
    else:
        from .map_route import route_path
        from .map_route_reference_variants import declared_pairs
        targets = declared_pairs(source,named_endpoint_evidence)
        if len(targets)!=1:
            raise ValueError('Ambiguous initial named choices require a separate explicit protocol')
        pair = list(reversed(targets[0]))
        modes = {r['profile'] for r in initial_route_spec.get('alternatives',[])}
        if len(modes)!=1:
            raise ValueError('One independently rendered initial engine required')
        start = route_path(pair,next(iter(modes)))
    pair, mode = initial_url_state(start)
    c.update(task_id=source['source_task_id']+'--initial-route-v1', domain='map',
             goal=source['goal'], original_goal=source['goal'], task_text_changed=False,
             recorded_start_urls=deepcopy(inventory['recorded_start_urls']),
             recorded_start_paths=list(map(local_path,inventory['recorded_start_urls'])),
             start_path=start, is_explicit_derivative=True, original_evaluation_equivalence=False,
             heldout_quarantine=False, eligible_for_training=False, normal_admitted=False,
             map_native_route={'version':'map-native-route-common-dispatch-v1'})
    c['start_revision']={'version':VERSION,'original_start':c['recorded_start_paths'][0],
                         'derived_start':start,'reason':'Explicit initial native route needed by the unchanged task.',
                         'equivalent_to_original_evaluation':False}
    c['training_initialization']={'version':VERSION,'source_route_definition':deepcopy(source),
                                  'source_route_definition_sha256':fingerprint(source),
                                  'initial_pair':pair,'initial_mode':mode}
    c['initialization_revision']=dict(revision,selected_start=start,binding_version=VERSION)
    require_source_binding(c,c,inventory,domain='map')
    validate_initial_spec(c,initial_route_spec,named_endpoint_evidence)
    return c


def require_original_binding(c, original, inventory):
    validate(c)
    return require_source_binding(c,original,inventory,domain='map')
