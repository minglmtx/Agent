"""Reviewed public wording over an unchanged repository-navigation predicate.

The original admission is checked in full, never edited or relabelled. This
adapter retains normal repository observation and integrity checks and requires
a separate attempt for the new public goal. It grants no training admission.
"""
from copy import deepcopy
import hashlib
from pathlib import Path

from . import site_navigation_rules as navigation
from .public_completion_runtime import _pinned, _plain, feedback
from .source_revision_binding import binding, fingerprint, local_path, require_source_binding
from .gitlab_repository import verify_repository_reference
from .io_utils import atomic_write_json

VERSION = 'reviewed-public-navigation-revision-v1'
FIELD = 'public_navigation_revision'
FEEDBACK_VERSIONS = (VERSION,)
AUTHORIZED_TARGET_WRITES = False

def _expected(original, task_id, goal, urls, review_pin):
    spec = original.get('completion', {}).get('repository', {})
    if (original.get('domain') != 'gitlab' or spec.get('kind') != 'blob'
            or not spec.get('visible_section') or FIELD in original
            or 'public_completion' in original or 'admission_result' in original
            or original.get('task_text_changed') is not False):
        raise ValueError('An original native repository document/section contract is required')
    value = deepcopy(original)
    value.update(task_id=task_id, goal=goal, original_goal=original['goal'],
        task_text_changed=True, recorded_start_urls=deepcopy(urls),
        goal_revision={'version':VERSION,'original_goal':original['goal'],'derived_goal':goal,
            'reason':'Make the reviewed local document completion requirement public.',
            'equivalent_to_original_evaluation':False})
    value[FIELD]={'version':VERSION,'original_contract':deepcopy(original),'scope_review':deepcopy(review_pin)}
    return value

def enabled(contract):
    if FIELD not in contract: return False
    spec=contract[FIELD]
    if not isinstance(spec,dict) or set(spec)!={'version','original_contract','scope_review'} or spec['version']!=VERSION:
        raise ValueError('Exact reviewed navigation revision required')
    original=spec['original_contract']
    if (_plain(contract)!=_expected(original,contract.get('task_id'),contract.get('goal'),contract.get('recorded_start_urls'),spec['scope_review'])
            or contract['task_id']==original['task_id'] or contract['goal']==original['goal']
            or contract.get('eligible_for_training') is not False
            or any(contract.get(k) is True for k in ('normal_gate_passed','training_admitted'))):
        raise ValueError('Only the reviewed public wording and source mapping may change')
    binding(contract)
    return True

def _review(contract):
    enabled(contract); spec=contract[FIELD]; report=_pinned(spec['scope_review'])
    matches=[r for r in report['records'] if r['source_task_id']==contract['source_task_id']]
    if len(matches)!=1: raise ValueError('One independently reviewed source required')
    row=matches[0]
    if (row.get('task_contract')!=spec['original_contract'] or row.get('proposed_public_goal')!=contract['goal']
            or row.get('start_path')!=contract['start_path'] or row.get('actual_prompt_and_trajectory_read') is not True
            or row.get('new_actor_required_for_definition') is not True
            or row.get('original_benchmark_equivalence_claimed') is not False):
        raise ValueError('Public wording must match the independently reviewed definition')

def make_contract(original, inventory, review_pin, *, goal, task_id):
    original=_plain(original)
    if (inventory.get('task_id')!=original.get('source_task_id') or inventory.get('goal')!=original['goal']
            or inventory.get('domain')!=original['domain'] or inventory.get('source_trace_ids')!=original['source_trace_ids']
            or inventory.get('heldout_quarantine') is not False
            or list(map(local_path,inventory.get('recorded_start_urls',[])))!=original['recorded_start_paths']):
        raise ValueError('Original source, starts, traces and split must match')
    candidate=_expected(original,task_id,goal,inventory['recorded_start_urls'],review_pin)
    _review(candidate)
    return candidate

def _hash(module): return hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()

def require_admission(contract, proof):
    _review(contract); original=contract[FIELD]['original_contract']
    if (proof.get('version')!=VERSION or proof.get('candidate_fingerprint')!=fingerprint(contract)
            or proof.get('original_fingerprint')!=fingerprint(original)
            or proof.get('runtime_sha256')!=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
            or proof.get('native_runtime_sha256')!=_hash(navigation)
            or type(proof.get('actor_attempts')) is not int or proof['actor_attempts']!=0
            or type(proof.get('api_calls')) is not int or proof['api_calls']!=0
            or proof.get('training_admitted') is not False):
        raise ValueError('Exact current revision qualification required')
    retained=_pinned(proof['original_proof'])
    navigation.require_admission(deepcopy(original),retained)
    return retained

def make_proof(contract, original_proof_pin):
    _review(contract)
    proof={'version':VERSION,'candidate_fingerprint':fingerprint(contract),
        'original_fingerprint':fingerprint(contract[FIELD]['original_contract']),
        'runtime_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'native_runtime_sha256':_hash(navigation),'original_proof':deepcopy(original_proof_pin),
        'actor_attempts':0,'api_calls':0,'training_admitted':False}
    require_admission(contract,proof)
    return proof

def require_original_binding(contract, original, inventory):
    enabled(contract)
    return require_source_binding(contract,original,inventory,domain='gitlab')

def public_goal(contract): enabled(contract); return contract['goal']
def fields(contract): enabled(contract); return []

class NativeReadHooks:
    def __init__(self,contract,proof,directory):
        retained=require_admission(contract,proof)
        self.contract=deepcopy(contract); self.original=deepcopy(contract[FIELD]['original_contract'])
        self.directory=Path(directory); self.expected=retained['cycles'][0]['initial_fingerprint']
        self.site=None; self.context=None; self.captured=None; self.scored=False; self.capture_started=None

    def prepare(self,site,username):
        if self.site is not None or site.domain!='gitlab': raise ValueError('One original GitLab instance required')
        self.site=site; self.before=site.fingerprint()
        if self.before!=self.expected: raise RuntimeError('Initial selected state differs from original controls')
        self.reference=verify_repository_reference(site,self.original['completion']['repository'])

    def attach(self,context):
        if self.site is None or self.context is not None: raise ValueError('One prepared browser context required')
        self.context=context

    def observe_initial(self,page):
        if page.context is not self.context: raise ValueError('Original browser context required')

    def capture_terminal(self,page,terminal):
        if self.capture_started is not None or self.scored or page.context is not self.context or terminal.get('url')!=page.url:
            raise ValueError('One bound terminal capture required')
        self.capture_started=deepcopy(terminal)

    def finalize_terminal_capture(self,page,terminal):
        # The normal runner reads native details once, after its initial hook.
        # Freeze that exact result before the browser closes.
        if (self.capture_started is None or self.captured is not None or self.scored
                or page.context is not self.context or page.url!=terminal.get('url')
                or any(terminal.get(k)!=v for k,v in self.capture_started.items())
                or not isinstance(terminal.get('repository'),dict)):
            raise ValueError('Complete unchanged terminal document and repository capture required')
        self.captured=deepcopy(terminal)

    def score_terminal(self,site,terminal,*,runtime_error=None):
        if site is not self.site or self.scored: raise ValueError('One terminal score on the bound instance required')
        self.scored=True
        from .document_observation import attach_last_request
        expected,_=attach_last_request(self.captured,self.directory,family='repository')
        if runtime_error or self.captured is None or terminal!=expected:
            result={'status':'unknown','reward':None,'checks':{},'reason':'Missing valid terminal capture or runtime error'}
            integrity=False
        else:
            after=site.fingerprint(); reference=verify_repository_reference(site,self.original['completion']['repository'])
            integrity=after==self.before and reference==self.reference
            result=navigation.evaluate_navigation(self.original,terminal,site_origin=site.url)
            atomic_write_json(self.directory/'public-navigation-protection.json',{
                'before':self.before,'after':after,'reference_before':self.reference,'reference_after':reference,'integrity':integrity})
            if not integrity: result=dict(result,status='unknown',reward=None,reason='Protected state or reference changed')
        result=dict(result,native_version=result.get('version'),version=VERSION)
        atomic_write_json(self.directory/'public-navigation-receipt.json',{
            'task_id':self.contract['task_id'],'source_task_id':self.contract['source_task_id'],
            'public_goal':self.contract['goal'],'evaluation':result,'integrity':integrity})
        return result,integrity

    def close(self): pass  # No independent process, connection or action source.
