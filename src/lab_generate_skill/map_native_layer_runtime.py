"""Optional normal local-layer lifecycle; no actor actions or private answers.

A controls-only CPU entry can test the real factory/session using reviewed
native evidence. It cannot produce an actor admission. Normal inference also
requires two cold BrowserGym/no-op cycles covering all seven original sources.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

from . import map_native_layer_completion as layers
from . import map_local_surface_controls as surface
from . import map_native_request_bounds as artifact
from .io_utils import atomic_write_json

VERSION='map-native-layer-normal-runtime-v1'
PROOF_VERSION='map-native-layer-normal-evidence-v1'
SOURCE_IDS=('18bb8f41188fd7da8001','1c5c6925760778e6bbb5','4791902089d0ca6ecab7',
 '57941f7d5cbd99c5acd8','6791c6f3e4b6b6963094','ef2552bf69bb38768b61','b9101b71aacd51b61f6e')


def enabled(contract):return isinstance(contract.get('map_native_layer'),dict)


def validate(contract):
    if (not enabled(contract)or contract.get('domain')!='map'
        or contract.get('task_id')!=contract.get('source_task_id')
        or contract['source_task_id']not in SOURCE_IDS
        or contract.get('heldout_quarantine')is not False
        or contract.get('eligible_for_training')is not False
        or not contract.get('recorded_start_paths')
        or contract['start_path']!=contract['recorded_start_paths'][0]
        or contract['map_native_layer']!={'version':VERSION,'native_batch_seconds':300}):
        raise ValueError('Exact original development layer binding with bounded native transport required')
    scope=contract.get('completion');expected=layers.proposed_scope(contract['goal'])
    if (not isinstance(scope,dict)or any(scope.get(k)!=v for k,v in expected.items())
        or type(scope.get('retain_original_native_route'))is not bool
        or scope['retain_original_native_route']is not (contract['source_task_id']==SOURCE_IDS[-1])):
        raise ValueError('Original reviewed seven local layer scopes required')
    if any(contract.get(k) for k in ('map_export','query','map_geolocation','map_zoom')):
        raise ValueError('Mixed Map action/evaluation families forbidden')
    return scope


def require_original_binding(contract, original_contract, source):
    validate(contract)
    if {k:v for k,v in contract.items()if k!='admission_result'}!=original_contract:
        raise ValueError('Original layer contract changed after controls')
    def path(url):
        u=urlsplit(url);return u.path+('?' +u.query if u.query else '')+('#'+u.fragment if u.fragment else '')
    if (source.get('task_id')!=contract['source_task_id']or source.get('domain')!='map'
        or source.get('goal')!=contract['goal']or source.get('heldout_quarantine')is not False
        or source.get('source_trace_ids')!=contract['source_trace_ids']
        or [path(u)for u in source['recorded_start_urls']]!=contract['recorded_start_paths']):
        raise ValueError('Original layer goal/starts/traces/split differ from authoritative inventory')


def require_native_controls(contract, proof):
    """Raw two-cold controls under the reviewed evaluator; no normal claim."""
    validate(contract)
    if (proof.get('version')!=PROOF_VERSION or proof.get('native_node_cap')!=50000
        or proof.get('source_ids')!=list(SOURCE_IDS)
        or any(type(proof.get(k))is not int or proof[k]!=0 for k in ('actor_attempts','api_calls','task_admissions'))
        or proof.get('normal_bindings_written')is not False
        or proof.get('old_failed_native_results_preserved')is not True):
        raise ValueError('All seven original native sources and zero-model provenance required')
    cycles=proof.get('native_cycles')
    if not isinstance(cycles,list)or len(cycles)!=2:raise ValueError('Two complete native cold cycles required')
    matched=[]
    for cycle in cycles:
        if (cycle.get('initial_fingerprint')!=cycle.get('final_fingerprint')
            or not isinstance(cycle.get('initial_fingerprint'),str)or len(cycle['initial_fingerprint'])!=64
            or any(cycle.get(k)is not True for k in ('protected_state_unchanged','clean_reset_verified','dirty_reuse_refused'))
            or [r.get('source_task_id')for r in cycle.get('sources',[])]!=list(SOURCE_IDS)):
            raise ValueError('Complete seven-source native cold protection/reset evidence required')
        for row in cycle['sources']:
            if (not isinstance(row.get('checks'),dict)or not row['checks']or any(v is not True for v in row['checks'].values())
                or row.get('reference_signature')!=surface.digest(row.get('reference'))
                or not row.get('raw_evidence_file_sha256')or row.get('source_evidence_recomputed_under_current_evaluator')is not True):
                raise ValueError('Actual source controls/reference and preserved raw provenance required')
        row=next(r for r in cycle['sources']if r['source_task_id']==contract['source_task_id'])
        if (row['original_goal']!=contract['goal']or row['original_first_start']!=contract['start_path']
            or row['source_trace_ids']!=contract['source_trace_ids']):
            raise ValueError('Native controls differ from the exact original source')
        matched.append(row)
    if cycles[0]['initial_fingerprint']!=cycles[1]['initial_fingerprint']or matched[0]['reference_signature']!=matched[1]['reference_signature']:
        raise ValueError('Independent native baselines or source references differ')
    return {'baseline':cycles[0]['initial_fingerprint'],'reference':deepcopy(matched[0]['reference'])}


def _normal_factory_guard(cycle,baseline):
    if (not isinstance(cycle.get('fresh_factory_id'),str)or len(cycle['fresh_factory_id'])!=64
        or cycle.get('initial_fingerprint')!=baseline or cycle.get('final_fingerprint')!=baseline
        or any(cycle.get(k)is not True for k in ('protected_state_unchanged','clean_reset_verified','dirty_reuse_refused','cold_teardown_completed'))):
        raise ValueError('Actual normal factory/reset cycles unavailable')


def composite_source_provenance(factory,source):
    return {'job_id':factory['job_id'],'job_state':factory['job_state'],
        'factory_id':factory['cycle']['fresh_factory_id'],'factory_role':factory['role'],
        'source_row_sha256':surface.digest(source),'receipt_sha256':factory['receipt_sha256'],
        'raw_archive_sha256':factory['raw_archive_sha256'],
        'member_manifest_sha256':factory['member_manifest_sha256']}



def _passed_cold_in_failed_allocation(factory,baseline,index):
    """Explicit real passed cycle; never relabel the failed allocation.

    The producer independently verifies actual sacct state and every raw member.
    These full receipt/allocation objects retain the failed sibling, including
    its complete lifecycle. This branch accepts only a source-complete cold
    exit0 from the original two-cold allocation, never a partial or timed-out
    cycle. A diagnostic/control candidate is not execution evidence.
    """
    b=factory.get('passed_cold_from_failed_allocation')
    if not isinstance(b,dict)or b.get('version')!='actual-complete-cold-from-failed-two-cold-allocation-v1':
        raise ValueError('Explicit completed-cold/failed-allocation binding required')
    receipt=b.get('passed_cycle_receipt');sibling=b.get('failed_sibling_receipt');allocation=b.get('allocation')
    if (not isinstance(receipt,dict)or not isinstance(sibling,dict)or not isinstance(allocation,dict)
        or b.get('actual_whole_job_state')!='FAILED'or b.get('actual_whole_job_exit_code')!='2:0'
        or b.get('actual_job_id')!=factory['job_id']or allocation.get('job_id')!=factory['job_id']
        or allocation.get('single_real_slurm_job')is not True or allocation.get('independent_factory_cycles')!=2
        or allocation.get('actor_attempts')!=0 or allocation.get('api_calls')!=0
        or allocation.get('cycle_exit_codes')!=([0,2]if index==0 else[2,0])
        or receipt.get('exit_code')!=0 or receipt.get('result',{}).get('passed')is not True
        or receipt.get('result',{}).get('cycle')!=factory['cycle']
        or sibling.get('exit_code')!=2 or sibling.get('result',{}).get('passed')is not False
        or b.get('allocation_content_sha256')!=surface.digest(allocation)
        or b.get('passed_receipt_content_sha256')!=surface.digest(receipt)
        or b.get('failed_sibling_receipt_content_sha256')!=surface.digest(sibling)
        or b.get('passed_cycle_receipt_sha256')!=factory['receipt_sha256']
        or receipt.get('archive_sha256')!=factory['raw_archive_sha256']
        or receipt.get('member_manifest_sha256')!=factory['member_manifest_sha256']):
        raise ValueError('Failed allocation is not bound to its true complete passed cold')
    for key in ('allocation_file_sha256','failed_sibling_receipt_file_sha256'):
        v=b.get(key)
        if not isinstance(v,str)or len(v)!=64 or any(c not in '0123456789abcdef'for c in v):
            raise ValueError('Complete original failed-allocation raw file hashes required')
    sibling_cycle=sibling['result'].get('cycle',{})
    _normal_factory_guard(sibling_cycle,baseline)
    if (sibling_cycle.get('cycle')!=1-index
        or sibling_cycle.get('fresh_factory_id')==factory['cycle']['fresh_factory_id']
        or sibling_cycle.get('manifest_source_ids')!=list(SOURCE_IDS)
        or sibling_cycle.get('executed_source_ids')!=[SOURCE_IDS[-1]]or sibling_cycle.get('repair_subset')is not True
        or [r.get('source_task_id')for r in sibling_cycle.get('sources',[])]!=[SOURCE_IDS[-1]]
        or sibling_cycle['sources'][0].get('normal_candidate_passed')is not False
        or any(type(sibling_cycle.get(k))is not int or sibling_cycle[k]!=0 for k in('actor_attempts','api_calls','task_admissions'))):
        raise ValueError('Original unknown sibling and its independent full lifecycle must be retained')
    execution=factory.get('execution_binding')
    expected=('src/lab_generate_skill/map_native_bbox_reference.py','src/lab_generate_skill/map_native_layer_runtime.py',
              'src/lab_generate_skill/map_query_site.py','src/lab_generate_skill/map_native_renderer_index.py',
              'src/lab_generate_skill/map_native_bbox_async.py','src/lab_generate_skill/map_native_bbox_transport.py',
              'scripts/map_native_served_refresh.py','scripts/probe_map_native_layer_normal.py',
              'scripts/run_map_native_layer_repair_guard.py')
    # The actual overlay inventory is supplied verbatim by the producer. The
    # module list is not inferred from source-success labels.
    if (not isinstance(execution,dict)or not isinstance(execution.get('code_files_sha256'),dict)
        or set(execution['code_files_sha256'])!=set(expected)
        or any(not isinstance(v,str)or len(v)!=64 or any(c not in '0123456789abcdef'for c in v)
            for v in execution['code_files_sha256'].values())
        or any(not isinstance(execution.get(k),str)or len(execution[k])!=64
            or any(c not in '0123456789abcdef'for c in execution[k])for k in('original_packet_sha256','runtime_control_overlay_sha256'))):
        raise ValueError('Exact frozen runtime/control packet execution binding required')
    return True


def require_composite_cycle(cycle,baseline,index):
    """Bind passed sources to actual factories even when another source failed.

    The old FAILED job remains FAILED. Both the old and repair factories must
    independently prove complete protected-state/reset/teardown lifecycles.
    A source is reused only from its own passed immutable source-row evidence.
    """
    if (cycle.get('cycle')!=index or cycle.get('status')!='normal_source_composite_passed'
        or cycle.get('composed_source_evidence')is not True
        or cycle.get('initial_fingerprint')!=baseline or cycle.get('final_fingerprint')!=baseline
        or any(cycle.get(k)is not True for k in ('protected_state_unchanged','clean_reset_verified','dirty_reuse_refused','cold_teardown_completed'))
        or any(type(cycle.get(k))is not int or cycle[k]!=0 for k in('actor_attempts','api_calls','task_admissions'))):
        raise ValueError('Explicit protected source-composite lifecycle required')
    factories=cycle.get('factory_evidence')
    if not isinstance(factories,list)or len(factories)!=2:raise ValueError('Actual old and repair cold factory evidence required')
    for i,factory in enumerate(factories):
        if (factory.get('role')!=('passed_six_from_failed_full_cycle','final_source_repair_subset')[i]
            or (i==0 and factory.get('job_state')!='FAILED')
            or (i==1 and factory.get('job_state')not in('COMPLETED','FAILED'))
            or not isinstance(factory.get('job_id'),str)or not factory['job_id'].isdigit()
            or any(not isinstance(factory.get(k),str)or len(factory[k])!=64
                or any(c not in '0123456789abcdef'for c in factory[k])
                for k in('receipt_sha256','raw_archive_sha256','member_manifest_sha256','cycle_sha256'))):
            raise ValueError('Exact source-level real job/archive provenance required')
        actual=factory.get('cycle')
        if not isinstance(actual,dict)or surface.digest(actual)!=factory['cycle_sha256']or actual.get('cycle')!=index:
            raise ValueError('Source factory cycle hash changed')
        _normal_factory_guard(actual,baseline)
        if i==1 and factory['job_state']=='FAILED':_passed_cold_in_failed_allocation(factory,baseline,index)
        elif factory.get('passed_cold_from_failed_allocation')is not None:
            raise ValueError('Failed-allocation branch cannot relabel a completed job')
        if any(type(actual.get(k))is not int or actual[k]!=0 for k in('actor_attempts','api_calls','task_admissions')):
            raise ValueError('Model/API/claim activity cannot be composed as CPU controls')
    old,repair=[factory['cycle']for factory in factories]
    if (old.get('status')!='normal_control_unknown'
        or [r.get('source_task_id')for r in old.get('sources',[])]!=list(SOURCE_IDS)
        or any(r.get('normal_candidate_passed')is not True for r in old['sources'][:-1])
        or old['sources'][-1].get('normal_candidate_passed')is not False
        or repair.get('status')!='normal_single_cold_repair_subset_passed'
        or repair.get('manifest_source_ids')!=list(SOURCE_IDS)
        or repair.get('executed_source_ids')!=[SOURCE_IDS[-1]]or repair.get('repair_subset')is not True
        or [r.get('source_task_id')for r in repair.get('sources',[])]!=[SOURCE_IDS[-1]]
        or repair['sources'][0].get('normal_candidate_passed')is not True
        or factories[0]['job_id']==factories[1]['job_id']
        or old['fresh_factory_id']==repair['fresh_factory_id']):
        raise ValueError('Only the six actual passed sources and final successful repair may compose')
    rows=cycle.get('sources')
    if not isinstance(rows,list)or [r.get('source_task_id')for r in rows]!=list(SOURCE_IDS):
        raise ValueError('Complete original source-composite scope required')
    for i,row in enumerate(rows):
        factory=factories[1 if i==len(SOURCE_IDS)-1 else 0]
        actual=factory['cycle']['sources'][0 if i==len(SOURCE_IDS)-1 else i]
        if ({k:v for k,v in row.items()if k!='normal_control_provenance'}!=actual
            or row.get('normal_control_provenance')!=composite_source_provenance(factory,actual)):
            raise ValueError('Composed source row/hash/provenance differs from its actual passed control')
    return {row['source_task_id']:row['normal_control_provenance']['factory_id']for row in rows}


def require_admission(contract, proof):
    native=require_native_controls(contract,proof)
    if proof.get('normal_runtime_preinference_gate_source_ids')!=list(SOURCE_IDS):
        raise ValueError('Actual normal runtime proof for all seven original sources required')
    cycles=proof.get('normal_cycles')
    if not isinstance(cycles,list)or len(cycles)!=2:raise ValueError('Two actual cold normal BrowserGym cycles required')
    identities={source:set()for source in SOURCE_IDS}
    for index,cycle in enumerate(cycles):
        if cycle.get('composed_source_evidence')is True:
            source_factories=require_composite_cycle(cycle,native['baseline'],index)
        else:
            _normal_factory_guard(cycle,native['baseline'])
            if [r.get('source_task_id')for r in cycle.get('sources',[])]!=list(SOURCE_IDS):
                raise ValueError('Actual complete normal source scope unavailable')
            source_factories={source:cycle['fresh_factory_id']for source in SOURCE_IDS}
        for source,identity in source_factories.items():identities[source].add(identity)
        for row in cycle['sources']:
            expected=next(r for r in proof['native_cycles'][0]['sources']if r['source_task_id']==row['source_task_id'])
            if any(row.get(k)!=expected[k]for k in('original_goal','original_first_start','source_trace_ids')):
                raise ValueError('Actual normal controls changed original goal/start/traces')
            if (row.get('actual_normal_make_session')is not True or row.get('actual_factory_prepare_completed')is not True
                or row.get('normal_noop_judgment')!={'status':'failure','reward':0.0}
                or row.get('initial_ax_nonempty')is not True or row.get('original_first_start_preserved')is not True
                or row.get('native_full_state_preserved')is not True
                or row.get('normal_candidate_passed')is not True
                or set(row.get('normal_controls',{}))!={'catalog_only_rejected','active_open_panel_passed','active_closed_panel_passed','actual_leaflet_active_with_panel_hidden','unchecked_rejected','wrong_document_rejected','login_rejected','404_rejected'}
                or any(v is not True for v in row['normal_controls'].values())):
                raise ValueError('Actual normal source reset/AX/no-op evidence required')
            if (row['source_task_id']==SOURCE_IDS[-1]
                and row.get('native_renderer_membership_index_verified')is not True):
                raise ValueError('Full MapData normal source needs the actually served indexed native renderer')
    repairs=[cycle['factory_evidence'][1]for cycle in cycles if cycle.get('composed_source_evidence')is True]
    if any(r.get('passed_cold_from_failed_allocation')is not None for r in repairs):
        if len(repairs)!=2 or any(not isinstance(r.get('execution_binding'),dict)for r in repairs):
            raise ValueError('Both last-source cold executions must retain full exact code binding')
        if repairs[0]['execution_binding']!=repairs[1]['execution_binding']:
            raise ValueError('Last-source cold environment/runtime/control packet SHA changed')
    if any(len(value)!=2 for value in identities.values()):raise ValueError('Each source needs two independent cold normal factories')
    return native


from contextlib import contextmanager
from contextvars import ContextVar
_reviewed_profiles = ContextVar('reviewed_map_native_layer_profiles', default=None)

@contextmanager
def reviewed_source_profiles(entries):
    """Private registry binding; task text cannot enable a website extension."""
    if _reviewed_profiles.get() is not None:
        raise ValueError('A reviewed Map environment scope is already active')
    frozen = {}
    for contract, use_layers in entries:
        source = contract.get('source_task_id')
        if (not isinstance(source, str) or not source or source in frozen
                or contract.get('domain') != 'map' or type(use_layers) is not bool):
            raise ValueError('Distinct exact Map environment bindings required')
        frozen[source] = (deepcopy({k:v for k,v in contract.items() if k != 'admission_result'}), use_layers)
    if not frozen:
        raise ValueError('Nonempty reviewed Map environment scope required')
    token = _reviewed_profiles.set(frozen)
    try:
        yield
    finally:
        _reviewed_profiles.reset(token)

def profile_for_contracts(rows,domain):
    bindings = _reviewed_profiles.get() or {}
    selected = [c.get('source_task_id') in bindings for c in rows]
    if any(selected):
        if domain != 'map' or not all(selected):
            raise ValueError('Reviewed Map environment sources require a dedicated manifest')
        values = set()
        for c in rows:
            expected, use_layers = bindings[c['source_task_id']]
            if {k:v for k,v in c.items() if k != 'admission_result'} != expected:
                raise ValueError('Reviewed Map environment contract changed')
            values.add(use_layers)
        if len(values) != 1:
            raise ValueError('Separate native-layer and ordinary Map profiles')
        return values.pop()
    active=[enabled(c)for c in rows]
    if not any(active):return False
    if domain!='map'or not all(active):raise ValueError('Dedicated native layer manifest required')
    for c in rows:validate(c)
    return True


MAP_CONSTRUCTOR = """  var map = new L.OSM.Map("map", {
    zoomControl: false,
    layerControl: false,
    contextmenu: true,
    worldCopyJump: true
  });"""
MEMBERSHIP_READER = """
  Object.defineProperty(window, "__labNativeLayerState", {
    configurable: false, writable: false,
    value: function () {
      return {"Map Data": map.hasLayer(map.dataLayer),
              "Map Notes": map.hasLayer(map.noteLayer)};
    }
  });
"""


def frontend_source(name, original):
    """Pinned UI refresh plus a passive, immutable real Leaflet state reader.

    The reader changes no event, layer, document, view or action. It supplies
    only two actual membership booleans to the private terminal evaluator.
    """
    from .map_native_layer_refresh import patch_source
    patched=patch_source(name,original)
    if name=='index.js':
        if patched.count(MAP_CONSTRUCTOR)!=1:raise ValueError('Pinned actual Map constructor missing')
        patched=patched.replace(MAP_CONSTRUCTOR,MAP_CONSTRUCTOR+MEMBERSHIP_READER)
    return patched


def apply_frontend_refresh(app,logs):
    """Three pinned source refreshes and passive state reader on local copy."""
    from .map_native_layer_refresh import PINNED,patch_source,VERSION as refresh_version
    record={'version':refresh_version,'node_local_copy_only':True,'sources':{},
        'native_events_preserved':True,'mapdata_features_removed':0,'task_or_action_policy_changed':False,
        'read_only_actual_leaflet_membership':True}
    for name in PINNED:
        p=Path(app)/'app/assets/javascripts'/name;before=p.read_bytes();p.write_text(frontend_source(name,before.decode()))
        record['sources'][name]={'original_sha256':hashlib.sha256(before).hexdigest(),'patched_sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
    atomic_write_json(Path(logs)/'native-layer-refresh-patch.json',record)
    return record


def full_original_bbox_retained(current,original):
    """A closed sidebar may enlarge its native view, but cannot narrow it."""
    from decimal import Decimal
    try:
        w,s,e,n=map(Decimal,artifact.bbox(current));a,b,c,d=map(Decimal,artifact.bbox(original))
        return w<=a and s<=b and e>=c and n>=d
    except(ValueError,TypeError):return False


def feedback(judgment):
    return {'status':judgment['status'],'reward':judgment['reward'],
        'checks':[{'name':key,'passed':value}for key,value in judgment.get('checks',{}).items()],
        'private_expected_values_provided':False,'action_sequence_provided':False}


class NativeLayerHooks:
    def __init__(self,contract,proof,directory,*,controls_only=False):
        self.contract=deepcopy(contract);self.scope=validate(contract);self.directory=Path(directory)
        self.native=(require_native_controls if controls_only else require_admission)(contract,proof)
        self.controls_only=controls_only;self.site=None;self.initial=None;self.baseline=None;self.initial_route=None
        self.current=None;self.transport=None;self.notes=[];self.served=None;self.served_record=None;self.page=None;self.closed=False
        self.notes_handler=None;self.faults=[];self.data_reference_cache={}
        self.installed_native_sha256=deepcopy(proof.get('installed_native_sha256',{}))

    def prepare(self,site):
        if self.site is not None:raise ValueError('One source-local layer preparation required')
        if (site.domain!='map'or getattr(site,'native_layer_refresh',False)is not True
            or not site.with_geographic_baseline or not site.track_changes
            or site.fingerprint()!=self.native['baseline']):
            raise ValueError('Actual full native Map baseline and startup UI patch required')
        site.reset_guard.require_unchanged();self.site=site
        if len(self.installed_native_sha256)!=11:raise ValueError('Complete pinned native API/renderer/settings source set required')
        for name,expected in self.installed_native_sha256.items():
            path=Path(name)
            source_root=site.root/'datasets/webarena-map-frontend/openstreetmap-website'
            if not path.is_relative_to(source_root)or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
                raise ValueError('Original native API/50K cap/frontend source changed')
        record=json.loads((site.logs/'native-layer-refresh-patch.json').read_text())
        if record.get('mapdata_features_removed')!=0 or record.get('node_local_copy_only')is not True or record.get('read_only_actual_leaflet_membership')is not True:
            raise ValueError('Native layer startup patch receipt missing')
        from .map_native_renderer_index import require_exact_private_source
        self.renderer_source=site.state/'frontend/app/vendor/assets/leaflet/leaflet.osm.js'
        original_renderer=site.root/'datasets/webarena-map-frontend/openstreetmap-website/vendor/assets/leaflet/leaflet.osm.js'
        self.renderer_record=require_exact_private_source(
            original_renderer.read_text(),self.renderer_source.read_text(),site.tile_url)
        atomic_write_json(self.directory/'native-layer-prepare.json',{'prepared':True,'original_source':self.contract['source_task_id'],
            'baseline':self.native['baseline'],'original_cap':50000,'controls_only':self.controls_only,'actor_policy_changed':False,
            'renderer_membership_index':self.renderer_record})

    def attach(self,page,site_origin):
        if self.site is None or self.page is not None or site_origin!=self.site.url:raise ValueError('Prepared native source before its normal first navigation required')
        self.page=page
        from .map_native_bbox_transport import NativeMapDataBatchTransport
        from map_native_served_refresh import ServedRefresh
        self.served=ServedRefresh(page,self.site.root/'datasets/webarena-map-frontend/openstreetmap-website/app/assets/javascripts',self.directory,
            renderer_source=self.renderer_source)
        self.transport=NativeMapDataBatchTransport(page,site_origin,self.directory/'native-layer-data-transport',
            seconds=self.contract['map_native_layer']['native_batch_seconds'])
        origin=urlsplit(site_origin)
        def receive(response):
            p=urlsplit(response.url);request=response.request
            if ((p.scheme,p.netloc)!=(origin.scheme,origin.netloc)or p.path!='/api/0.6/notes.json'
                or request.method!='GET'or request.resource_type!='xhr'):return
            row={'url':response.url,'method':request.method,'resource_type':request.resource_type,
                'http_status':response.status,'content_type':response.headers.get('content-type','')}
            self.notes.append(row)
            try:
                body=response.body();path=self.directory/('native-layer-notes-'+str(len(self.notes))+'.json')
                path.write_bytes(body);row.update(payload_file=path.name,sha256=hashlib.sha256(body).hexdigest(),bytes=len(body))
            except Exception as error:
                row['capture_error']=type(error).__name__;self.faults.append({'stage':'native_notes_capture','type':type(error).__name__})
            atomic_write_json(self.directory/'native-layer-notes-responses.json',self.notes)
        self.notes_handler=receive;page.on('response',receive)

    def observe_initial(self,page):
        from .map_view import wait_native_view
        from .map_route import read_route
        u,s=urlsplit(page.url),urlsplit(self.contract['start_path'])
        if u.path!=s.path or u.query!=s.query:raise ValueError('Original normal first document changed')
        if s.path in('/','/search','/directions'):wait_native_view(page,self.contract['start_path'])
        self.initial=layers.read_layer_surface(page)
        if self.scope['retain_original_native_route']:self.initial_route=read_route(page)
        self.record(page,event='initial')
        atomic_write_json(self.directory/'native-layer-initial.json',{'surface':self.initial,'original_start_path':self.contract['start_path'],'route':self.initial_route})

    def record(self,page,*,event='observation'):
        value=layers.read_layer_surface(page);self.current=value
        if self.transport is not None:self.transport.observe_public_state(value,event=event)
        if self.baseline is None and value.get('map_visible')is True:
            rows=surface.label_rows(value,'overlays')
            chosen={r['label']:r for r in rows if r['label']in self.scope['allowed_local_overlay_labels']}
            if set(chosen)==set(self.scope['allowed_local_overlay_labels'])and all(r['checked']is False for r in chosen.values()):self.baseline=deepcopy(value)
        # A /traces source may reach the actual map only through actor navigation.
        # Do not replace that original start or open a layer panel for the model.
        if self.served_record is None and value.get('map_visible')is True:
            self.served_record=self.served.verify()
            atomic_write_json(self.directory/'native-layer-actually-served.json',self.served_record)
        return value

    def terminal(self,page,terminal):
        from .map_route import read_route
        if self.transport is not None:self.transport.settle_pending()
        self.record(page,event='terminal');terminal['map_native_layer']=self.current
        terminal['map_native_layer_route']=read_route(page)if self.scope['retain_original_native_route']else None
        atomic_write_json(self.directory/'native-layer-terminal.json',{'surface':self.current,'route':terminal['map_native_layer_route']})

    def close(self):
        if self.closed:return
        try:
            if self.notes_handler is not None:self.page.remove_listener('response',self.notes_handler)
            if self.served is not None:self.served.detach()
        finally:
            if self.transport is not None:self.transport.close()
            self.closed=True

    def evaluate(self,site,terminal,*,runtime_error=None):
        def unknown(reason):return {'version':VERSION,'status':'unknown','reward':None,'checks':{},'reason':reason}
        if runtime_error or self.faults:return unknown('Native layer runtime or response capture incomplete')
        if self.initial is None:return unknown('Original normal reset was not observed')
        try:site.reset_guard.require_unchanged()
        except Exception:return unknown('Complete native persistent baseline changed during layer task')
        current=(terminal or {}).get('map_native_layer',{});baseline=self.baseline or self.initial
        original_point=None
        try:_,lat,lon=surface.native_view(self.initial);original_point=[lat,lon]
        except ValueError:pass
        common={'original_area_point':original_point,'initial_route':self.initial_route,
            'terminal_route':(terminal or {}).get('map_native_layer_route')}
        responses=[]
        for row in self.notes:
            if row.get('payload_file'):responses.append({'notes_record':row,'notes_body':(self.directory/row['payload_file']).read_bytes()})
        if self.transport is not None:
            from .map_native_bbox_reference import capture_full_reference,compare_database_union,compare_database_native_200
            for index,row in enumerate(self.transport.records):
                status=row.get('status')
                if status=='batch_transport_unknown':return unknown('Full native MapData transport incomplete')
                if status not in('native_children_complete_adapted_envelope','native_response_unchanged'):continue
                if status=='native_response_unchanged'and row.get('native_original_http_status')!=200:continue
                bounds=row['requested_bbox_strings']
                # The explicit route/MapData task must retain its original full
                # bbox. A smaller model-chosen window cannot bypass the 50K cap.
                if self.scope['kind']=='native_map_data'and not full_original_bbox_retained(bounds,self.native['reference']['bbox']):continue
                try:
                    path=row['envelope']if status=='native_children_complete_adapted_envelope'else row['native_original_body_file']
                    body=(self.transport.out/path).read_bytes()
                    key=(index,hashlib.sha256(body).hexdigest(),surface.digest(row))
                    cached=self.data_reference_cache.get(key)
                    if cached is not None:
                        responses.append(cached);continue
                    database=capture_full_reference(site,bounds,self.directory,'layer-final-'+str(index))
                    if status=='native_children_complete_adapted_envelope':
                        responses.append({'data_transport':row['batch'],'data_body':body,'data_comparison':compare_database_union(body,bounds,database)})
                    else:
                        meta={'url':row['request_url'],'method':'GET','resource_type':'xhr','http_status':200,'content_type':row['native_original_content_type']}
                        responses.append({'data_record':meta,'data_body':body,'data_comparison':compare_database_native_200(body,bounds,database)})
                    self.data_reference_cache[key]=responses[-1]
                except Exception as error:
                    from .runtime_diagnostics import failure_diagnostic
                    atomic_write_json(self.directory/('layer-final-'+str(index)+'-reference-error.json'),
                        failure_diagnostic(error,'independent_native_full_bbox_reference'))
                    return unknown('Independent complete native bbox reference unavailable')
        judgments=[]
        for response in responses or [{}]:
            checks=layers.layer_transition_checks(self.scope,baseline,current,site.url,require_native_membership=True,**common,**response)
            checks['actual_reviewed_frontend_served']=self.served_record is not None if current.get('map_visible')is True else False
            healthy=type((terminal or {}).get('http_status'))is int and 200<=(terminal or {})['http_status']<300 and (terminal or {}).get('error_page')is False and (terminal or {}).get('login_page')is False
            checks['valid_terminal_document']=bool(healthy)
            result={'version':VERSION,'status':'success'if all(v is True for v in checks.values())else'failure',
                'reward':1.0 if all(v is True for v in checks.values())else 0.0,'checks':checks}
            judgments.append(result)
        return next((j for j in reversed(judgments)if j['status']=='success'),judgments[-1])
