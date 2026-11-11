"""Separate source-bound native finite History/layer/store candidate.

The complete existing facts whole-cold lifecycle predicate is preserved below;
new source/reference/control predicates live in separate modules. CPU-only
measurement constructors cannot grant ordinary inference admission.
"""
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
import json,re,hashlib
from . import map_history_layer_normal as facts
from .map_native_identity_declarations import POLICIES,POLICY_SHA
from .source_revision_binding import require_source_binding
from .map_identity_policy_scope import require_compatible_policy
VERSION=facts.VERSION
MARKER={'version':VERSION}
LIFECYCLE=('protected_state_unchanged','clean_reset_verified','dirty_reuse_refused','cold_teardown_completed')
def enabled(c):return isinstance(c.get('map_history_layer'),dict)
def validate(c):
 if (not enabled(c)or c['map_history_layer']!=MARKER or c.get('domain')!='map'
     or c.get('task_id')!=c.get('source_task_id')or c.get('goal')!=c.get('original_goal')
     or c.get('heldout_quarantine')is not False or c.get('task_text_changed')is not False
     or c.get('training_eligible')is not False or c.get('normal_admitted')is not False
     or c.get('protocol',{}).get('kind')not in facts.KINDS
     or any(c.get(k)for k in ('query','map_native_facts','map_native_route','map_native_layer','map_export','map_zoom','map_geolocation','goal_revision','start_revision'))):
  raise ValueError('One explicit finite local source lifecycle with unchanged original goal/start required')
 q=c['protocol'];d=q.get('public_interpretation')
 if not isinstance(d,str)or not d.strip()or q.get('version')!=VERSION or q.get('original_benchmark_equivalence')is not False:raise ValueError('Explicit versioned public finite task interpretation required')
 if q['kind']in ('named_history','native_store_exists'):
  name='New York City'if q['kind']=='named_history'else'Manhattan'
  if q.get('query')!=name or not require_compatible_policy(q.get('identity_policy_sha256'),[name]) or q.get('identity_policy')!=POLICIES[name]:raise ValueError('Exact native semantic policy required')
  if q['kind']=='native_store_exists'and(q.get('name')!='New York'or q.get('shop')!='convenience'or q.get('absence_policy')!='unknown_without_complete_scoped_negative_evidence'):raise ValueError('Complete native positive existence scope required')
 else:
  from .map_native_layer_completion import proposed_scope
  expected=proposed_scope(c['goal']);expected['retain_original_native_route']=True
  if q.get('completion')!=expected:raise ValueError('Original general local layer completion unchanged')
  u=urlsplit(c['start_path']);args=parse_qs(u.query)
  from .map_route_normal_capture import point
  pair=[[str(v)for v in point(x.split(','))]for x in args.get('route',[''])[0].split(';')]
  if u.path!='/directions'or args.get('engine')!=['fossgis_osrm_car']or len(pair)!=2 or q.get('original_route_pair')!=pair:raise ValueError('Exact original native route initialization required')
 return facts.source_binding(c)
def require_original_binding(c,original,inventory):
 validate(c);require_source_binding(c,original,inventory,domain='map');return True
def reference_semantics(p):return facts.reference_semantics(p)
def require_candidate(c,proof):
 """Strict composite source gate; does not reinterpret failed allocations."""
 if(c.get('heldout_quarantine')is not False or proof.get('passed')is not True
     or proof.get('source_binding_sha256')!=facts.fingerprint(facts.source_binding(c))):raise ValueError('Source normal proof changed/failed/heldout')
 cycles=proof.get('cycles')
 if not isinstance(cycles,list)or len(cycles)!=2 or [r.get('cycle')for r in cycles]!=[0,1]:raise ValueError('Two actual independent cycles required')
 factories=set();baselines=[];semantic=[]
 for row in cycles:
  if(not row.get('factory_id')or not row.get('job_identity')or row.get('normal_candidate_passed')is not True
     or row.get('cold_teardown_completed')is not True or row.get('protected_state_unchanged')is not True
     or row.get('clean_reset_verified')is not True or row.get('dirty_reuse_refused')is not True
     or row.get('actor_attempts')!=0 or row.get('api_calls')!=0 or row.get('source_binding_sha256')!=proof['source_binding_sha256']
     or row.get('checks')!=facts.required_controls(c)or not row.get('baseline')or not row.get('reference_semantics_sha256')):
   raise ValueError('Full source/normal controls/baseline/reset/protection/teardown proof required')
  factories.add(row['factory_id']);baselines.append(row['baseline']);semantic.append(row['reference_semantics_sha256'])
 if len(factories)!=2 or baselines[0]!=baselines[1]or semantic[0]!=semantic[1]:raise ValueError('Independent normal factories, baseline, full semantic reference must agree')
 facts.require_reference(c,proof)
 return True


def require_admission(contract,proof):
    binding=validate(contract);require_candidate(contract,proof)
    ids=proof.get('full_original_manifest_source_ids');source=contract['source_task_id']
    if(proof.get('source_composition_version')!='actual-native-facts-source-proof-composition-v1'
       or not isinstance(ids,list)or not ids or ids!=sorted(set(ids))or source not in ids
       or not re.fullmatch(r'[0-9a-f]{64}',str(proof.get('full_original_manifest_sha256','')))):
        raise ValueError('Complete original source manifest and composition required')
    baseline=proof.get('full_native_baseline')
    if not re.fullmatch(r'[0-9a-f]{64}',str(baseline)):raise ValueError('Full native protected baseline required')
    semantic=facts.fingerprint(reference_semantics(proof))
    for index,row in enumerate(proof['cycles']):
        actual=row.get('actual_cycle');private=row.get('actual_private_reference');private_raw=row.get('actual_private_reference_raw_json')
        if(not isinstance(actual,dict)or facts.fingerprint(actual)!=row.get('actual_cycle_sha256')
           or actual.get('cycle')!=index or actual.get('source_count')!=len(ids)
           or actual.get('full_original_manifest_source_ids')!=ids
           or actual.get('batch_source_count',len(ids))!=len(actual.get('sources',[]))
           or actual.get('fresh_factory_id')!=row.get('factory_id')
           or actual.get('initial_fingerprint')!=baseline or actual.get('final_fingerprint')!=baseline
           or actual.get('full_lifecycle_passed')is not True or any(actual.get(k)is not True for k in LIFECYCLE)
           or actual.get('same_cold_factory_preserved')is not True or actual.get('owned_native_writers_quiet')is not True
           or any(type(actual.get(k))is not int or actual[k]!=0 for k in('actor_attempts','api_calls','task_admissions'))):
            raise ValueError('Actual complete cold lifecycle/source count/reset/protection changed')
        facts.require_reference(contract,private)
        source_rows=[v for v in actual['sources']if v.get('source_task_id')==source]
        if(len(source_rows)!=1 or source_rows[0].get('normal_candidate_passed')is not True
           or facts.fingerprint(source_rows[0])!=row.get('actual_source_row_sha256')
           or source_rows[0].get('checks')!=row['checks']
           or source_rows[0].get('source_binding_sha256')!=proof['source_binding_sha256']
           or source_rows[0].get('private_reference_semantics_sha256')!=semantic
           or not isinstance(private,dict)or facts.fingerprint(reference_semantics(private))!=semantic
           or not isinstance(private_raw,str)or json.loads(private_raw)!=private
           or hashlib.sha256(private_raw.encode()).hexdigest()!=row.get('actual_private_reference_file_sha256')
           or private.get('two_independent_normal_context_references')is not True
           or private.get('source_binding_sha256')!=proof['source_binding_sha256']
           or private.get('full_native_baseline')!=baseline
           or source_rows[0].get('private_reference_artifact_file_sha256')!=row.get('actual_private_reference_file_sha256')
           or row.get('actual_terminal_control_job_state')not in('COMPLETED','FAILED')
           or row.get('actual_terminal_control_job_exit_code')!=('0:0'if row['actual_terminal_control_job_state']=='COMPLETED'else'2:0')
           or any(type(row.get(k))is not int or row[k]!=0 for k in('actor_attempts','api_calls'))
           or row.get('full_original_manifest_sha256')!=proof['full_original_manifest_sha256']
           or any(not re.fullmatch(r'[0-9a-f]{64}',str(row.get(k,'')))for k in
             ('actual_cycle_receipt_file_sha256','actual_allocation_file_sha256','executed_packet_sha256','raw_archive_sha256','actual_private_reference_file_sha256'))):
            raise ValueError('Exact passed source, full private reference or truthful terminal allocation changed')
    return binding

def fields(c):validate(c);return ['exists','object_path']if c['protocol']['kind']=='native_store_exists'else[]
def public_goal(c):
 validate(c);text=c['goal']+' '+c['protocol']['public_interpretation']
 if c['protocol']['kind']=='native_store_exists':text+=' Finish with a JSON object containing exactly exists (boolean) and object_path (the actual native object path inspected).'
 return text
def feedback(j):return {'status':j['status'],'reward':j['reward'],'checks':[{'name':k,'passed':v}for k,v in j.get('checks',{}).items()],'private_expected_values_provided':False,'action_sequence_provided':False}
def NativeReadHooks(c,p,directory):
 from .history_layer_hooks import FiniteHooks
 require_admission(c,p);return FiniteHooks(c,p,directory,controls_only=False)
