"""Finite genuine GPS resources for a document-start activation task.

Resource coordinates are environment availability, never a synthetic map start
or proof that the overlay was enabled. Existing viewport families are unchanged.
"""
from copy import deepcopy
from .map_route_normal_capture import fingerprint
from .source_revision_binding import binding

SOURCE='24334e2ab58fffd2515a'
FAMILY='gps_overlay_enabled'
RESOURCE_SCOPE='gps-document-finite-native-tiles-v1'
SPEC=dict(family=FAMILY,code='G',track_presence_required=False,all_visible_tiles_required=False,
    request_failures_are_empty_results=False,provider='gps',required_code='G',
    completion_boundary='enabled_settled_gps_layer_with_genuine_current_response',
    retain_initial_area=False,retain_initial_route=False)

def validate_spec(spec):
    if spec!=SPEC:raise ValueError('Exact GPS enabled/document completion boundary required')

def task_binding(candidate, providers):
    validate_spec(candidate.get('candidate_completion'))
    if (candidate.get('source_task_id')!=SOURCE or candidate.get('start_path')!='/traces'
            or candidate.get('domain')!='map' or candidate.get('split')!='train'
            or candidate.get('heldout_quarantine')is not False
            or candidate.get('validation_scope')!='native-gps-document-enabled-v187'
            or candidate.get('is_explicit_derivative')is not True
            or candidate.get('original_evaluation_equivalence')is not False):
        raise ValueError('Exact original GPS document source and explicit revision required')
    if set(providers)!= {'gps'} or providers['gps'].get('genuine_provider_bytes')is not True:
        raise ValueError('Only genuine GPS tiles may supply document profile resources')
    files=providers['gps']['files']
    if not files or len(files)>4096:raise ValueError('Bounded nonempty native GPS resource set required')
    return dict(source_task_id=SOURCE,source_binding_sha256=fingerprint(binding(candidate)),
        start_path='/traces',provider='gps',completion_sha256=fingerprint(SPEC),
        resource_scope=RESOURCE_SCOPE,available_tile_keys=sorted(files),
        initial_map_view_implied=False)

def build_document_resources(candidate, genuine_resources):
    value=deepcopy(genuine_resources)
    if value.get('version')!='map-provider-resources-v1' or value.get('native_admitted')is not False:
        raise ValueError('An unadmitted genuine-resource manifest is required')
    value['source_tasks']=[task_binding(candidate,value['providers'])]
    value.pop('native_initial_views',None)
    value['resource_scope']=RESOURCE_SCOPE
    value['coverage']='Finite genuine GPS tile coordinates only; /traces is a document start, not a map viewport. Missing resources remain unavailable, never empty.'
    return value

def require_document_resources(manifest,candidates):
    if len(candidates)!=1 or manifest.get('resource_scope')!=RESOURCE_SCOPE:
        raise ValueError('One distinct GPS document resource profile required')
    expected=task_binding(candidates[0],manifest['providers'])
    if manifest.get('source_tasks')!=[expected] or manifest.get('native_initial_views'):
        raise ValueError('GPS source/start/goal/completion/resource set changed')
    return True
