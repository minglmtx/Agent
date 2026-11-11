"""Reuse reviewed route controls, original starts and ordinary hook evidence.

Only a frozen bootstrap constructs this catalog. Reviews remain bound to their
inputs and exact tested code; no website or actor result is cached here.
"""
from copy import deepcopy
import json
from pathlib import Path

from .provider_review_catalog import digest, identity
from .source_revision_binding import binding

DEPENDENCIES = ('site_worker', 'map_query_site', 'map_reset_guard', 'map_candidate_start',
    'map_view', 'map_route', 'map_route_normal_capture', 'map_candidate_route_controls',
    'map_candidate_route_observation', 'map_candidate_route_terminal',
    'map_route_native_display', 'map_route_initialization_binding')


class RouteReviewCatalog:
    def __init__(self, config, *, project):
        self.closed=False
        self.files={}
        self.sources={}
        self.descriptors={}
        self.config=deepcopy(config)
        contracts=self.read(config['contracts'])
        normal=self.read(config['normal_review'])
        plan=self.read(config['normal_plan'])
        members=self.read(config['normal_runtime_members'])
        native=self.read(config['native_review'])
        starts=self.read(config['start_review'])
        if (not all(r.get('passed') is True for r in (normal,native,starts))
                or plan['files']['contracts.json']!=config['contracts']['sha256']
                or plan['files']['runtime-members.json']!=config['normal_runtime_members']['sha256']
                or normal.get('actor_attempts')!=0 or starts.get('actor_attempts')!=0):
            raise ValueError('Complete reviewed route evidence chain required')
        expected_pins={r['path']:r['sha256']for r in contracts['evidence_pins']}
        for key in ('native_review','start_review'):
            if expected_pins.get(config[key]['path'])!=config[key]['sha256']:
                raise ValueError('Ordinary controls did not use this source/reset review')
        for pin in contracts['evidence_pins']:
            self.read(pin,json_value=False)
        for pin in config['raw_evidence_pins']:
            self.read(pin,json_value=False)
        for name in DEPENDENCIES:
            rel='src/lab_generate_skill/'+name+'.py'
            self.read(dict(path=str(Path(project)/rel),sha256=members[rel]['sha256']),json_value=False)
        rel='scripts/run_site_navigation_once.py'
        self.read(dict(path=str(Path(project)/rel),sha256=members[rel]['sha256']),json_value=False)
        self.baseline=contracts['baseline']
        if normal['full_batch_seconds']<=0 or normal['controls_recomputed']<1:
            raise ValueError('Ordinary lifecycle review is incomplete')
        cold=starts['cold_workers']
        if len(cold)!=2 or cold[0]['factory_id']==cold[1]['factory_id']:
            raise ValueError('Two distinct cold original-start factories required')
        raw_pins={r['path']:r['sha256']for r in config['raw_evidence_pins']}
        if raw_pins.get(normal['archive'])!=normal['archive_sha256']:
            raise ValueError('Reviewed ordinary raw evidence is not pinned')
        cold_root=Path(config['start_review']['path']).parent/'results'
        for factory in cold:
            if raw_pins.get(str(cold_root/factory['cold']/'diagnostics.tgz'))!=factory['archive_sha256']:
                raise ValueError('Reviewed cold-start raw evidence is not pinned')
        if native['archive_sha256'] not in raw_pins.values():
            raise ValueError('Original functional-control archive is not pinned')
        ids=[row['candidate']['source_task_id']for row in contracts['tasks']]
        if not ids or len(set(ids))!=len(ids) or set(ids)!={r['source_task_id']for r in normal['source_details']}:
            raise ValueError('Normal route source coverage changed')
        if set(ids)!={r['source_task_id']for r in native['sources']}:
            raise ValueError('Native route control source coverage changed')
        for row in contracts['tasks']:
            c=row['candidate'];sid=c['source_task_id'];binding(c)
            if c.get('split')!='train' or c.get('heldout_quarantine') or c['candidate_completion']['family']!='displayed_route':
                raise ValueError('Bound training route source required')
            refs=row['references']
            nr=next(r for r in normal['source_details']if r['source_task_id']==sid)
            original=next(r for r in native['sources']if r['source_task_id']==sid)
            required={(i,name):('success'if name=='correct_native_route'else'failure')
                for i in range(len(refs))for name in ('correct_native_route','unsubmitted_wrong_endpoint','reversed_endpoints','wrong_transport')}
            actual={(r['variant'],r['control']):r['status']for r in original['controls']}
            if (not refs or nr.get('passed')is not True or nr['controls']!=1+len(refs)
                    or original.get('passed')is not True or actual!=required
                    or len(original['controls'])!=len(required)):
                raise ValueError('Each route alternative needs positive and negative controls')
            for factory in cold:
                if sid not in factory['sources']:
                    raise ValueError('Source absent from cold-start evidence')
            required_starts={str(cold_root/factory['cold']/'sources'/(sid+'.json'))for factory in cold}
            if {r['path']for r in config['start_records'][sid]}!=required_starts:
                raise ValueError('Cold source records must belong to both reviewed factories')
            for pin in config['start_records'][sid]:
                start=self.read(pin)
                if (start.get('passed')is not True or start['source_task_id']!=sid
                        or start['task_id']!=c['task_id'] or start['goal']!=c['goal']
                        or start['start_path']!=c['start_path']
                        or start['initial_fingerprint']!=self.baseline
                        or start['final_fingerprint']!=self.baseline
                        or start['lifecycle']!=['attach','observe_initial','capture_terminal','close']):
                    raise ValueError('Source start or reset differs from verified evidence')
            if len(config['start_records'][sid])!=2:
                raise ValueError('Both cold source records required')
            desc=dict(version='reviewed-native-route-source-v1',source_task_id=sid,
                candidate_sha256=digest(json.dumps(c,sort_keys=True,separators=(',',':')).encode()),
                normal_review_sha256=config['normal_review']['sha256'],
                native_review_sha256=config['native_review']['sha256'],
                start_review_sha256=config['start_review']['sha256'])
            admission=dict(version='native-route-normal-admission-v1',passed=True,
                source_task_id=sid,baseline=self.baseline,two_cold_environment_verified=True,
                ordinary_lifecycle_verified=True,all_route_alternatives_verified=True)
            self.sources[sid]=dict(candidate=deepcopy(c),references=deepcopy(refs),
                                  admission=admission,baseline=self.baseline)
            self.descriptors[sid]=desc
        self.require_current()

    def read(self,record,*,json_value=True):
        from .reviewed_evidence_snapshot import evidence_path
        path = evidence_path(self, record)
        if not path.is_absolute():raise ValueError('Absolute frozen evidence path required')
        before=identity(path);raw=path.read_bytes()
        actual=digest(raw)
        if actual!=record['sha256']:
            from .reviewed_code_evolution import accepts
            if not accepts(self,record,path,actual,json_value=json_value):
                raise ValueError('Reviewed route evidence or code changed: '+str(path))
        if identity(path)!=before:
            raise ValueError('Reviewed route evidence changed during read: '+str(path))
        self.files[path]=before
        return json.loads(raw)if json_value else raw

    def require_current(self):
        if self.closed or any(identity(p)!=value for p,value in self.files.items()):
            raise ValueError('Reviewed route proof changed or expired')

    def resolve(self,sid,descriptor):
        self.require_current()
        if sid not in self.sources or descriptor!=self.descriptors[sid]:
            raise ValueError('Exact original route descriptor required')
        from .reviewed_code_evolution import require_source
        require_source(self,sid)
        return deepcopy(self.sources[sid])

    def close(self):
        self.closed=True
        self.sources.clear()
