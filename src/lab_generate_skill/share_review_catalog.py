"""Bind reviewed native sharing controls to an unchanged ordinary runtime.

No control or actor is run here. Source-specific artifacts remain private to
terminal scoring; public output schemas contain field names and types only.
"""
from copy import deepcopy
import json
from pathlib import Path
from .route_review_catalog import RouteReviewCatalog
from .provider_review_catalog import digest
from .source_revision_binding import binding

DEPENDENCIES = ('site_worker', 'map_query_site', 'map_reset_guard',
    'map_candidate_start', 'map_view', 'map_route', 'map_route_initialization_binding',
    'map_share_terminal', 'map_share_observation', 'map_share_artifact_checks',
    'map_share_roundtrip', 'map_typed_information_share', 'browser_request_policy')
CONTROLS = {
    'share_panel_navigation': {'panel_absent':False,'native_panel_open':True,'unusable_visible_control':False},
    'route_link': {'correct_route':True,'view_only':False,'reversed_endpoints':False,'wrong_mode':False},
    'view_link': {'original_view_roundtrip':True,'wrong_view_roundtrip':False},
    'map_embed': {'native_embed_roundtrip':True,'wrong_dimensions':False,'wrong_area':False},
}


class ShareReviewCatalog(RouteReviewCatalog):
    """Reuse the pinned-file reader/lifetime guard, not route admission rules."""
    def __init__(self, config, *, project):
        self.closed=False; self.files={}; self.sources={}; self.descriptors={}
        self.config=deepcopy(config)
        contracts=self.read(config['contracts']); normal=self.read(config['normal_review'])
        plan=self.read(config['normal_plan']); members=self.read(config['normal_runtime_members'])
        starts=self.read(config['start_review'])
        if (normal.get('passed')is not True or starts.get('passed')is not True
                or normal.get('actor_attempts')!=0 or starts.get('actor_attempts')!=0
                or plan['files']['contracts.json']!=config['contracts']['sha256']
                or plan['files']['runtime-members.json']!=config['normal_runtime_members']['sha256']
                or normal['baseline']!=contracts['baseline']):
            raise ValueError('Complete original share lifecycle evidence required')
        pins={r['path']:r['sha256']for r in contracts['evidence_pins']}
        for record in [config['start_review'],*config['native_reviews']]:
            if pins.get(record['path'])!=record['sha256']:
                raise ValueError('Share evidence differs from exercised ordinary inputs')
        for pin in contracts['evidence_pins']:self.read(pin,json_value=False)
        for pin in config['raw_evidence_pins']:self.read(pin,json_value=False)
        native=[self.read(pin)for pin in config['native_reviews']]
        raw={r['path']:r['sha256']for r in config['raw_evidence_pins']}
        if raw.get(normal['archive'])!=normal['archive_sha256']:
            raise ValueError('Ordinary raw evidence is not pinned')
        for r in native:
            if r['archive_sha256']not in raw.values():raise ValueError('Native raw evidence is not pinned')
        for name in DEPENDENCIES:
            rel='src/lab_generate_skill/'+name+'.py'
            self.read(dict(path=str(Path(project)/rel),sha256=members[rel]['sha256']),json_value=False)
        rel='scripts/run_site_navigation_once.py'
        self.read(dict(path=str(Path(project)/rel),sha256=members[rel]['sha256']),json_value=False)
        self.baseline=contracts['baseline']; cold=starts['cold_workers']
        if len(cold)!=2 or cold[0]['factory_id']==cold[1]['factory_id']:
            raise ValueError('Two independent cold-start factories required')
        root=Path(config['start_review']['path']).parent/'results'
        for f in cold:
            if raw.get(str(root/f['cold']/'diagnostics.tgz'))!=f['archive_sha256']:
                raise ValueError('Cold-start archive missing')
        ids=[c['source_task_id']for c in contracts['tasks']]
        if not ids or len(ids)!=len(set(ids)) or set(ids)!={r['source_task_id']for r in normal['sources']}:
            raise ValueError('Ordinary sharing source coverage changed')
        for c in contracts['tasks']:
            sid=c['source_task_id']; family=c['candidate_completion']['family']; binding(c)
            if c.get('split')!='train' or c.get('heldout_quarantine') or family not in CONTROLS:
                raise ValueError('Explicit training share source required')
            row=next(r for r in normal['sources']if r['source_task_id']==sid)
            if (row.get('passed')is not True or row['task_id']!=c['task_id']
                    or row['controls']!=[dict(control='noop',status='failure'),dict(control='positive',status='success')]):
                raise ValueError('Ordinary noop and positive controls required')
            original_pin=config['native_records'][sid]; original=self.read(original_pin)
            matched=False
            for review in native:
                sources=review['sources']
                entry=sources.get(sid)if isinstance(sources,dict)else next((r for r in sources if r['source_task_id']==sid),None)
                if entry and entry.get('passed')is True and entry.get('sha256',entry.get('source_sha256'))==original_pin['sha256']:
                    matched=True
            if (not matched or original.get('passed')is not True or original['source_task_id']!=sid
                    or original['task_id']!=c['task_id'] or set(original['controls'])!=set(CONTROLS[family])):
                raise ValueError('Reviewed artifact controls required for exact source')
            for name,expected in CONTROLS[family].items():
                ctrl=original['controls'][name]
                if ctrl.get('expected')is not expected or ctrl.get('actual')is not expected:
                    raise ValueError('Artifact control did not pass')
            expected_paths={str(root/f['cold']/'sources'/(sid+'.json'))for f in cold}
            records=config['start_records'][sid]
            if len(records)!=2 or {r['path']for r in records}!=expected_paths:
                raise ValueError('Both original cold-start records required')
            for f in cold:
                if sid not in f['sources']:raise ValueError('Source absent from cold review')
            for pin in records:
                start=self.read(pin)
                if (start.get('passed')is not True or start['source_task_id']!=sid
                        or start['task_id']!=c['task_id'] or start['goal']!=c['goal']
                        or start['start_path']!=c['start_path']
                        or start['initial_fingerprint']!=self.baseline or start['final_fingerprint']!=self.baseline
                        or start['lifecycle']!=['attach','observe_initial','capture_terminal','close']):
                    raise ValueError('Original start/reset binding changed')
            self.descriptors[sid]=dict(version='reviewed-native-share-source-v1',source_task_id=sid,
                candidate_sha256=digest(json.dumps(c,sort_keys=True,separators=(',',':')).encode()),
                normal_review_sha256=config['normal_review']['sha256'],
                native_source_sha256=original_pin['sha256'],start_review_sha256=config['start_review']['sha256'])
            admission=dict(version='native-share-normal-admission-v1',passed=True,source_task_id=sid,
                baseline=self.baseline,two_cold_environment_verified=True,
                ordinary_lifecycle_verified=True,native_artifact_controls_verified=True)
            self.sources[sid]=dict(candidate=deepcopy(c),baseline=self.baseline,admission=admission)
        self.require_current()
