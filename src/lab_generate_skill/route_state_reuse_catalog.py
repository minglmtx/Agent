"""Route admission with explicit reuse of identical cold starting-state evidence.

The functional controls and ordinary lifecycle still belong to the current
source. Only cold environment preparation can be shared across public goals.
"""
from copy import deepcopy
import json
from pathlib import Path
from .route_review_catalog import RouteReviewCatalog, DEPENDENCIES
from .provider_review_catalog import digest
from .source_revision_binding import binding


def require_same_start(candidate, record, baseline, verified_source):
    """Never relabel another source's test as execution of this candidate."""
    if (record.get('passed')is not True or record['source_task_id']!=verified_source
            or record['start_path']!=candidate['start_path']
            or record['initial_fingerprint']!=baseline or record['final_fingerprint']!=baseline
            or record['lifecycle']!=['attach','observe_initial','capture_terminal','close']):
        raise ValueError('Shared cold preparation has a different initial state or reset')


class RouteStateReuseCatalog(RouteReviewCatalog):
    def __init__(self,config,*,project):
        self.closed=False;self.files={};self.sources={};self.descriptors={};self.config=deepcopy(config)
        contracts=self.read(config['contracts']);normal=self.read(config['normal_review'])
        plan=self.read(config['normal_plan']);members=self.read(config['normal_runtime_members'])
        native=self.read(config['native_review']);starts=self.read(config['start_review'])
        reference=self.read(config['reference_review'])
        if (not all(r.get('passed')is True for r in (normal,native,starts))
                or normal.get('actor_attempts')!=0 or starts.get('actor_attempts')!=0
                or plan['files']['contracts.json']!=config['contracts']['sha256']
                or plan['files']['runtime-members.json']!=config['normal_runtime_members']['sha256']
                or normal['baseline']!=contracts['baseline']):
            raise ValueError('Reviewed current-source ordinary route controls required')
        expected={r['path']:r['sha256']for r in contracts['evidence_pins']}
        for key in ('native_review','start_review'):
            if expected.get(config[key]['path'])!=config[key]['sha256']:
                raise ValueError('Original native/reset review was not used by ordinary controls')
        for pin in contracts['evidence_pins']:self.read(pin,json_value=False)
        for pin in config['raw_evidence_pins']:self.read(pin,json_value=False)
        raw={r['path']:r['sha256']for r in config['raw_evidence_pins']}
        if raw.get(normal['archive'])!=normal['archive_sha256'] or native['archive_sha256']not in raw.values():
            raise ValueError('Reviewed raw control archives required')
        if reference['archive_sha256']!=native['archive_sha256']:
            raise ValueError('Reference variant review belongs to different native controls')
        for name in DEPENDENCIES:
            rel='src/lab_generate_skill/'+name+'.py'
            self.read(dict(path=str(Path(project)/rel),sha256=members[rel]['sha256']),json_value=False)
        rel='scripts/run_site_navigation_once.py'
        self.read(dict(path=str(Path(project)/rel),sha256=members[rel]['sha256']),json_value=False)
        self.baseline=contracts['baseline'];cold=starts['cold_workers'];root=Path(config['start_review']['path']).parent/'results'
        if len(cold)!=2 or cold[0]['factory_id']==cold[1]['factory_id']:
            raise ValueError('Two independent cold factories required')
        for f in cold:
            if raw.get(str(root/f['cold']/'diagnostics.tgz'))!=f['archive_sha256']:
                raise ValueError('Cold raw archive not pinned')
        if len(contracts['tasks'])!=1 or len(normal['sources'])!=1:
            raise ValueError('One explicitly reviewed endpoint-replacement source required')
        row=contracts['tasks'][0];c=row['candidate'];refs=row['references'];sid=c['source_task_id'];binding(c)
        if c.get('split')!='train' or c.get('heldout_quarantine') or c['candidate_completion']['family']!='displayed_route':
            raise ValueError('Exact non-heldout route source required')
        if c['candidate_completion'].get('endpoint_request',{}).get('kind')!='replace_one_endpoint':
            raise ValueError('Reviewed replacement semantics required')
        nr=normal['sources'][0]
        expected_controls=[dict(control='noop',status='failure')]+[dict(control='positive-'+str(i),status='success')for i in range(len(refs))]
        if not refs or nr.get('passed')is not True or nr['source_task_id']!=sid or nr['task_id']!=c['task_id']or nr['controls']!=expected_controls:
            raise ValueError('Current source ordinary lifecycle/all reference alternatives not verified')
        required={(i,k):('success'if k=='correct_native_route'else'failure')for i in range(len(refs))for k in ('correct_native_route','unsubmitted_wrong_endpoint','reversed_endpoints','wrong_transport','destination_not_replaced')}
        actual={(r['variant'],r['control']):r['status']for r in reference['controls']}
        if (native['source_task_id']!=sid or reference['source_task_id']!=sid
                or native['native_variants']!=len(refs) or actual!=required
                or len(reference['controls'])!=len(required)
                or any(r['expected_success']is not r['actual_success']for r in native['controls'])):
            raise ValueError('Complete native endpoint replacement controls required')
        verified_source=config['cold_initial_source']
        if verified_source not in reference['same_start_as_verified_sources']or reference['start_path']!=c['start_path']:
            raise ValueError('Initial-state reuse was not explicitly reviewed')
        records=config['start_records']
        paths={str(root/f['cold']/'sources'/(verified_source+'.json'))for f in cold}
        if len(records)!=2 or {r['path']for r in records}!=paths or any(verified_source not in f['sources']for f in cold):
            raise ValueError('Actual shared cold-source records required')
        for pin in records:require_same_start(c,self.read(pin),self.baseline,verified_source)
        desc=dict(version='reviewed-route-with-shared-initial-state-v1',source_task_id=sid,
            candidate_sha256=digest(json.dumps(c,sort_keys=True,separators=(',',':')).encode()),
            normal_review_sha256=config['normal_review']['sha256'],reference_review_sha256=config['reference_review']['sha256'],
            start_review_sha256=config['start_review']['sha256'],cold_initial_source=verified_source)
        admission=dict(version='native-route-normal-admission-v1',passed=True,source_task_id=sid,baseline=self.baseline,
            two_cold_environment_verified=True,ordinary_lifecycle_verified=True,all_route_alternatives_verified=True,
            cold_initial_source=verified_source,cold_task_execution_reused=False,
            reused_scope='Identical declared initial URL and full baseline/reset only; current source owns ordinary and functional controls.')
        self.sources[sid]=dict(candidate=deepcopy(c),references=deepcopy(refs),baseline=self.baseline,admission=admission)
        self.descriptors[sid]=desc;self.require_current()
