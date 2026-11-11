"""Reuse sealed short-route native controls and the ordinary worker lifecycle."""
from copy import deepcopy
import json
from pathlib import Path
from urllib.parse import urlsplit
from .account_review_catalog import AccountReviewCatalog
from .source_revision_binding import binding
from .provider_review_catalog import digest
from .map_share_terminal import evaluate_share
from .map_candidate_start import validate_initial

DEPENDENCIES=('site_worker','native_goal_dispatch','map_query_site','map_short_route',
    'map_reset_guard','map_candidate_start','map_view','map_route','map_share_observation',
    'map_share_terminal','map_share_artifact_checks','map_share_roundtrip','frozen_share_actor_adapter')


class ShortRouteReviewCatalog(AccountReviewCatalog):
    def __init__(self,config,*,project):
        self.closed=False;self.files={};self.sources={};self.descriptors={};self.config=deepcopy(config)
        cfg=self.read(config['contracts']);plan=self.read(config['ordinary_plan'])
        members=self.read(config['ordinary_runtime_members']);native_cfg=self.read(config['native_contracts'])
        if (plan['files']['contracts.json']!=config['contracts']['sha256']
                or plan['files']['runtime-members.json']!=config['ordinary_runtime_members']['sha256']):
            raise ValueError('Exact exercised ordinary inputs required')
        for pin in cfg['evidence_pins']:self.read(pin,json_value=False)
        for name in DEPENDENCIES:
            rel='src/lab_generate_skill/'+name+'.py'
            self.read(dict(path=str(Path(project)/rel),sha256=members[rel]['sha256']),json_value=False)
        rel='scripts/run_site_navigation_once.py'
        if config.get('runner_profile_repair'):
            fix=config['runner_profile_repair']
            if fix['original']['sha256']!=members[rel]['sha256']:
                raise ValueError('Runner repair original differs from exercised CPU runtime')
            original=self.read(fix['original'],json_value=False)
            current=self.read(dict(path=str(Path(project)/rel),sha256=fix['repaired_sha256']),json_value=False)
            from .runner_profile_repair import verify_runner_patch
            verify_runner_patch(original,current)
        else:
            self.read(dict(path=str(Path(project)/rel),sha256=members[rel]['sha256']),json_value=False)
        raw=self.archive(config['ordinary_archive'],config['ordinary_index'])
        native=self.archive(config['native_archive'],config['native_index'])
        report=json.loads(raw['report.json']);native_report=json.loads(native['report.json'])
        if (report.get('passed')is not True or report.get('worker_closed')is not True
                or report.get('actor_attempts')!=0 or report['final_fingerprint']!=cfg['baseline']
                or native_report.get('site_closed')is not True or native_report.get('actor_attempts')!=0):
            raise ValueError('Closed native and ordinary workers plus reset evidence required')
        self.baseline=cfg['baseline']
        if len(cfg['tasks'])!=len(report['sources']):raise ValueError('Ordinary source coverage differs')
        for c in cfg['tasks']:
            sid=c['source_task_id'];binding(c)
            if c.get('split')!='train'or c.get('heldout_quarantine')or c['candidate_completion']['family']!='short_route_link':
                raise ValueError('Training compact-route source required')
            original=next(x for x in native_cfg['tasks']if x['source_task_id']==sid)
            if binding(original)!=binding(c):raise ValueError('Original goal/start changed since native controls')
            row=json.loads(raw[f'sources/{sid}/result.json'])
            if (row.get('passed')is not True or row['initial_fingerprint']!=self.baseline
                    or row['final_fingerprint']!=self.baseline):raise ValueError('Source reset or guard failed')
            reference=None
            for name,expected in (('noop','failure'),('positive','success')):
                initial=json.loads(raw[f'sources/{sid}/{name}/share-initial.json'])
                terminal=json.loads(raw[f'sources/{sid}/{name}/share-terminal.json'])
                start=initial['original_start'];u=urlsplit(start['url']);origin=u.scheme+'://'+u.netloc
                validate_initial(c,origin,start['url'],start['view'],start['route'])
                if terminal['reference']!=initial['reference']or terminal['integrity']is not True:
                    raise ValueError('Reference or native integrity changed')
                if terminal['events']!=['prepare','attach','observe_initial','capture_terminal','close','provide_trace','score_terminal']:
                    raise ValueError('Incomplete ordinary lifecycle')
                j=evaluate_share(c['candidate_completion'],reference=terminal['reference'],answer=terminal['answer'],
                    page=terminal['terminal'],origin=origin,tile_origin=origin,reopened=terminal['reopened'],integrity=True)
                if j!=terminal['judgment']or j['status']!=expected:raise ValueError('Ordinary raw judgment differs')
                reference=initial['reference']
            initial=json.loads(native[f'{sid}/initial.json']);u=urlsplit(initial['url']);origin=u.scheme+'://'+u.netloc
            if initial['route']['rows']!=reference['route']['rows']:raise ValueError('Native initial directions changed')
            for name,expected in (('correct','success'),('viewport_only','failure'),('reversed','failure'),('wrong_mode','failure')):
                case=json.loads(native[f'{sid}/{name}.json'])
                j=evaluate_share(c['candidate_completion'],reference=reference,answer=json.dumps({'share_link':case['url']}),
                    page={},origin=origin,tile_origin=origin,reopened=dict(requested=case['url'],url=case['resolved'],
                    http_status=case['http_status'],state=case['route']))
                if j['status']!=expected:raise ValueError('Native route control differs')
            if json.loads(native[f'{sid}/malformed.json'])['status']!=400:raise ValueError('Malformed token accepted')
            descriptor=dict(version='reviewed-short-route-source-v1',source_task_id=sid,
                candidate_sha256=digest(json.dumps(c,sort_keys=True,separators=(',',':')).encode()),
                native_archive_sha256=config['native_archive']['sha256'],ordinary_archive_sha256=config['ordinary_archive']['sha256'])
            admission=dict(version='native-short-route-normal-admission-v1',passed=True,source_task_id=sid,
                native_artifact_controls_verified=True,ordinary_lifecycle_verified=True,reset_verified=True,baseline=self.baseline)
            self.sources[sid]=dict(candidate=deepcopy(c),admission=admission,baseline=self.baseline)
            self.descriptors[sid]=descriptor
        self.require_current()
