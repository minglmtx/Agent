"""Source-bound native facts through the shared terminal-only read lifecycle.

The finite reading/share schemas are declared local interpretations. Complete
original failed allocations stay failed; only fully controlled passed sources
from two independent, protected, reset and torn-down factories can be admitted.
"""
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlsplit
import json,re
import hashlib
from . import map_native_facts_normal as facts
from . import map_named_facts_binding as named
from . import map_local_view_facts as local_view

VERSION='map-native-facts-common-dispatch-v1'
MARKER={'version':VERSION}
LIFECYCLE=('protected_state_unchanged','clean_reset_verified','dirty_reuse_refused','cold_teardown_completed')

def enabled(contract):return isinstance(contract.get('map_native_facts'),dict)

def validate(contract):
    if(not enabled(contract)or contract['map_native_facts']!=MARKER or contract.get('domain')!='map'
       or (contract.get('task_id')!=contract.get('source_task_id') and not contract.get('goal_revision'))or contract.get('heldout_quarantine')is not False
       or contract.get('training_eligible')is not False or contract.get('normal_admitted')is not False
       or contract.get('protocol',{}).get('kind')not in set(facts.DOCS)|{'current_view_share','any_native_place_search'}|named.KINDS|local_view.KINDS
       or any(contract.get(k)for k in('query','map_native_route','map_native_layer','map_export','map_zoom','map_geolocation'))):
        raise ValueError('One declared original native fact/readout lifecycle required')
    if contract.get('goal_revision'):
        from .map_local_coverage_goal_revision import validate as validate_revision
        validate_revision(contract)
    if contract['protocol']['kind']in named.KINDS:named.validate(contract)
    if contract['protocol']['kind']in local_view.KINDS:local_view.validate(contract)
    return facts.source_binding(contract)

def reference_semantics(proof):
    value={k:deepcopy(proof[k])for k in('source_binding_sha256','documents','native_records','initial_view_identity','native_artifacts','reverse_full_record')if k in proof}
    for doc in value.get('documents',{}).values():
        origin=urlsplit(doc['url']).netloc
        for obj,key in[(doc,'url')]+[(link,'href')for link in doc['links']]:
            url=urlsplit(obj[key])
            if url.hostname=='127.0.0.1'and url.netloc==origin:
                obj[key]=url.path+('?' +url.query if url.query else'')+('#'+url.fragment if url.fragment else'')
    return value

def require_admission(contract,proof):
    binding=validate(contract);facts.require_candidate(contract,proof)
    if contract['protocol']['kind']in named.KINDS:named.require_reference(contract,proof)
    if contract['protocol']['kind']in local_view.KINDS:local_view.require_reference(contract,proof)
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
           or any(type(actual.get(k))is not int or actual[k]!=0 for k in('actor_attempts','api_calls','task_admissions'))):
            raise ValueError('Actual complete cold lifecycle/source count/reset/protection changed')
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
        if contract['protocol']['kind']in named.KINDS:named.require_reference(contract,private)
        if contract['protocol']['kind']in local_view.KINDS:local_view.require_reference(contract,private)
    return binding

def require_original_binding(contract,original,inventory):
    validate(contract)
    if contract.get('goal_revision'):
        from .map_local_coverage_goal_revision import require_original_binding as require_revision_binding
        return require_revision_binding(contract, original, inventory)
    if{k:v for k,v in contract.items()if k!='admission_result'}!=original:raise ValueError('Controlled original native fact definition changed')
    def path(value):
        u=urlsplit(value);return u.path+('?' +u.query if u.query else'')+('#'+u.fragment if u.fragment else'')
    starts=[path(v)for v in inventory.get('recorded_start_urls',[])]
    revision=contract.get('initialization_revision',{})
    if(inventory.get('task_id')!=contract['source_task_id']or inventory.get('domain')!='map'
       or inventory.get('heldout_quarantine')is not False or inventory.get('goal')!=contract['goal']
       or inventory.get('source_trace_ids')!=contract['source_trace_ids']or starts!=contract['original_recorded_starts']
       or contract['start_path']not in starts or revision.get('selected_start')!=contract['start_path']
       or revision.get('original_canonical_start')!=starts[0]
       or revision.get('published_trace_id')not in contract['source_trace_ids']
       or revision.get('provenance_not_our_actor_result')is not True
       or revision.get('provenance_not_later_published_action')is not True
       or revision.get('publisher_start_state_verified')is not False or revision.get('equivalence_claim')is not False):
        raise ValueError('Authoritative original goal/traces/split/published first-start changed')

def fields(contract):
    validate(contract);kind=contract['protocol']['kind']
    if kind in local_view.KINDS:return local_view.fields(contract)
    if kind in named.KINDS:return ['latitude','longitude']if kind=='named_place_coordinates'else[]
    return sorted(facts.DOCS[kind]['fields'])if kind in facts.DOCS else[]if kind=='any_native_place_search'else['share_link']

def public_goal(contract):
    validate(contract)
    if contract['protocol']['kind']in local_view.KINDS:return local_view.public_goal(contract)
    if contract['protocol']['kind']in facts.DOCS:return facts.public_goal(contract)
    if contract['protocol']['kind']=='any_native_place_search':return contract['goal']
    if contract['protocol']['kind']in named.KINDS:
        kind=contract['protocol']['kind'];declaration=named.validate(contract)
        if kind=='initial_where_is_this':return contract['goal']+' The location referent is the actual original native map center; device geolocation is not part of this local protocol.'
        policy=declaration['identity_policy'];target=declaration['query']
        text=contract['goal']+' For this local protocol, '+target+' means the geographical place described by '+json.dumps({k:policy[k]for k in ('names','state','country_code')if k in policy},ensure_ascii=False)+'.'
        if kind=='named_place_coordinates':text+=' Return a JSON object containing exactly latitude and longitude, the complete native place coordinates.'
        return text
    return contract['goal']+'\nResponse format: finish with a JSON object containing exactly share_link, the actual native local Share link for the original current map view. External delivery is not required by this local artifact protocol.'

def feedback(judgment):
    checks=[]
    for name,passed in judgment.get('checks',{}).items():
        row={'name':name,'passed':passed}
        if passed is None:
            row.update(evaluation_status='not_evaluated',reason=judgment.get('unevaluated_checks',{}).get(name,
                'Insufficient observation evidence to evaluate this check.'))
        checks.append(row)
    result={'status':judgment['status'],'reward':judgment['reward'],'checks':checks,
            'private_expected_values_provided':False,'action_sequence_provided':False}
    if judgment.get('reason')is not None:result['reason']=judgment['reason']
    return result

class NativeFactsReadHooks:
    def __init__(self,contract,proof,directory):
        require_admission(contract,proof)
        self.contract=deepcopy(contract);self.proof=deepcopy(proof)
        self.core=facts.FactsTimeline(contract,Path(directory)/'native-facts')
        self.site=None;self.context=None;self.trace_provided=False;self.scored=False;self.answer=None

    def prepare(self,site,username):
        if(username is not None or self.site is not None or site.domain!='map'
           or site.with_geographic_baseline is not True or site.track_changes is not True
           or site.fingerprint()!=self.proof['full_native_baseline']):
            raise ValueError('Original anonymous full native Map factory required')
        site.reset_guard.require_unchanged();self.site=site;self.core.site=site

    def attach(self,context):
        if self.site is None or self.context is not None:raise ValueError('Native facts prepare precedes one actual context attach')
        self.core.attach(context);self.context=context

    def observe_initial(self,page):
        if self.context is None or page.context is not self.context:raise ValueError('Actual original page must belong to attached normal context')
        self.core.observe_initial(page)

    def record(self,page,*,event='observation'):
        if event!='observation':raise ValueError('Only normal issued observations are recordable')
        return self.core.record(page,event='issued_observation')

    def capture_terminal(self,page,terminal):self.core.capture_terminal(page,terminal)

    def provide_trace(self,trace):
        if not isinstance(trace,dict)or self.trace_provided or self.scored:raise ValueError('One completed source trace precedes terminal scoring')
        from .admin_pilot import final_answer
        self.answer=final_answer(trace);self.trace_provided=True

    def score_terminal(self,site,terminal,*,runtime_error=None):
        if site is not self.site or self.scored or not self.trace_provided:raise ValueError('One actual terminal judge follows the completed source trace')
        self.scored=True;integrity=False
        try:
            site.reset_guard.require_unchanged();integrity=site.fingerprint()==self.proof['full_native_baseline']
            judgment=facts.judge(self.contract,self.proof,self.core,terminal,self.answer,site_origin=site.url)if integrity and runtime_error is None else None
        except Exception as error:
            from .io_utils import atomic_write_json
            from .runtime_diagnostics import failure_diagnostic
            atomic_write_json(self.core.directory/'native-facts-protection-error.json',failure_diagnostic(error,'native_facts_terminal_protection'))
            judgment=None
        if judgment is None:judgment={'version':facts.VERSION,'status':'unknown','reward':None,
          'checks':{'complete_native_protection_certified':integrity},'reason':'Full native fact protection/reference or runtime unavailable'}
        return judgment,integrity

    def close(self):self.core.close()


def answer_field_spec(contract):
    """Types come from the finite public document protocol, never its answers."""
    validate(contract)
    kind = contract['protocol']['kind']
    if kind == 'named_place_coordinates':
        return {'latitude': 'number', 'longitude': 'number'}
    if kind in facts.DOCS:
        return {name: facts.DOCS[kind]['fields'][name] for name in fields(contract)}
    return {name: 'string' for name in fields(contract)}

