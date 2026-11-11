"""Candidate public scope for six local overlay tasks; old judgments stay immutable.

The original contract drives native controls, initialization and evaluation.
This explicit derivative is not an Actor admission and cannot reuse an old
Actor attempt as an execution of the new public goal.
"""
from copy import deepcopy
import hashlib,json
from . import map_native_layer_runtime as native
VERSION='map-local-overlay-public-scope-v1'
SOURCES=frozenset(native.SOURCE_IDS[:-1])

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def make_candidate(original):
    native.validate(original)
    if original['source_task_id'] not in SOURCES:raise ValueError('Only six generic layer sources may be revised')
    base=deepcopy(original);base.pop('admission_result',None)
    scope=base['completion']
    if scope['kind']!='generic_local_layer_transition' or scope['allowed_local_overlay_labels']!=['Map Notes','Map Data']:
        raise ValueError('Exact reviewed local overlay alternatives required')
    goal=('For this local task, change the map by enabling either Map Notes or Map Data. '
          'These are the two supported overlays for this task; other base-map styles are outside its local scope. '
          'The chosen overlay must actually be active. A successfully loaded empty overlay is acceptable. '
          'The Layers panel may be open or closed when you finish.')
    if scope['preserve_original_area']:goal+=' Keep the original map area in view.'
    identity=digest({'original':base,'public_goal':goal,'version':VERSION})
    return dict(version=VERSION,source_task_id=base['source_task_id'],task_id=base['source_task_id']+'--local-overlay-scope-'+identity[:12],
                domain='map',goal=goal,original_goal=base['goal'],start_path=base['start_path'],
                original_contract=base,original_contract_sha256=digest(base),
                is_explicit_derivative=True,original_evaluation_equivalence=False,
                actor_permission=False,training_admitted=False,new_public_input_validation_required=True,
                historical_actor_result_reusable_as_new_execution=False)

def validate(candidate):
    if not isinstance(candidate,dict) or candidate!=make_candidate(candidate.get('original_contract',{})):
        raise ValueError('Candidate public scope or immutable original contract changed')
    return candidate['original_contract']

def verify_reusable_native_controls(candidate,proof):
    original=validate(candidate)
    evidence=native.require_admission(original,proof)
    return dict(passed=True,source_task_id=candidate['source_task_id'],
                original_contract_sha256=digest(original),native_baseline=evidence['baseline'],
                reuse_scope='original native completion, initialization, reset and control evidence only',
                new_public_input_validated=False,actor_permission=False,training_admitted=False)
