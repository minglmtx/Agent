"""Pinned native GPS controls reused once by the ordinary actor worker."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit
from .account_review_catalog import AccountReviewCatalog
from .comparison_review_catalog import require_source_controls,LIFECYCLE
from .provider_review_catalog import digest
from .source_revision_binding import binding
from .map_provider_resources import checked_archive,validate_tile,require_candidate_resources
from .map_gps_overlay_observation import require_initial_gps
from .map_provider_observation import require_initial
from .map_gps_overlay_terminal import evaluate

DEPENDENCIES=('site_worker','map_query_site','map_reset_guard','map_provider_environment',
    'map_provider_observation','map_provider_terminal','map_provider_contract','map_provider_coverage',
    'map_provider_resources','map_frozen_provider_runtime','map_gps_overlay_observation',
    'map_gps_overlay_terminal','map_candidate_start','map_route','map_view','map_tile_warmup',
    'website_batch_profile','native_goal_dispatch')


def review_source(c,report,raw,bodies):
    sid=c['source_task_id'];row=require_source_controls(report,sid)
    if row['goal']!=c['goal'] or row['start_path']!=c['start_path']:
        raise ValueError('Native controls tested a different public goal or start')
    for control in row['controls']:
        prefix=f"sources/{sid}/{control['kind']}/"
        read=lambda name:json.loads(raw[prefix+name+'.json'])
        initial,base,t,page=(read(n)for n in ('gps-initial','provider-initial','gps-terminal','terminal-page'))
        require_initial_gps(initial['base_initial'],initial['initial'])
        if (initial['initial']!=t['initial'] or initial['actor_actions']!=0
                or initial['reference_phase']!='native_initial_before_actions'
                or t['baseline']!=report['baseline'] or t['integrity']is not True
                or t['capture_error']is not None or t['terminal']!=page
                or t['events']!=LIFECYCLE or read('control')!=control
                or initial['environment_binding']!=report['binding']
                or t['environment_binding']!=report['binding']):
            raise ValueError('Original native lifecycle or state binding differs')
        u,expected=urlsplit(initial['url']),urlsplit(c['start_path'])
        if (u.path,u.query)!=(expected.path,expected.query) or not 200<=read('initial-page-health')['http_status']<300:
            raise ValueError('Original healthy document start required')
        g=t['initial'];document=dict(url=initial['url'],view=dict(map_visible=True,
            native_geo_uri=f"geo:{g['center']['lat']},{g['center']['lng']}?z={g['zoom']}"),route=base['route'])
        require_initial(c,initial['base_initial'],base['route'],initial_document=document)
        server=SimpleNamespace(url=g['template'].split('/tiles/')[0],bodies=bodies)
        args=dict(initial=g,terminal=t['native_terminal'],page=page,site_origin=u.scheme+'://'+u.netloc,
            server=server,response_hashes=t['response_sha256'],integrity=True)
        actual=evaluate(c['candidate_completion'],**args)
        if actual!=t['judgment'] or actual!=control['judgment'] or any(a.get('error')for a in control['actions']):
            raise ValueError('Native GPS control cannot be independently reproduced')
        if control['kind']=='positive':
            missing=evaluate(c['candidate_completion'],**dict(args,response_hashes={}))
            if missing['status']!='unknown' or missing!=control['missing_response_mutation']:
                raise ValueError('Unverified GPS images must not earn reward')
    return row


class GPSReviewCatalog(AccountReviewCatalog):
    def __init__(self,config,*,project):
        self.closed=False;self.files={};self.sources={};self.descriptors={};self.config=deepcopy(config)
        profile=self.read(config['profile']);contracts=self.read(config['contracts'])['tasks']
        if (profile.get('version')!='map-frozen-provider-environment-v1'
                or profile.get('runtime_external_requests')is not False
                or profile.get('original_snapshot_equivalence')is not False
                or profile['contracts']!=config['contracts']):
            raise ValueError('Exact frozen GPS profile required')
        resources=self.read(profile['resources']);require_candidate_resources(resources,contracts)
        if set(resources['providers'])!={'gps'}:raise ValueError('Explicit GPS-only provider profile required')
        archives={}
        for r in resources['sources']:
            self.read(dict(path=r['archive'],sha256=r['sha256']),json_value=False)
            archives[r['sha256']]=checked_archive(r)
        bodies={}
        for key,row in resources['providers']['gps']['files'].items():
            files=archives[row['archive_sha256']];validate_tile('gps',key,row,files)
            bodies['/tiles/gps/'+key]=files[row['member']]
        plan=self.read(config['plan']);members=self.read(config['runtime_members'])
        if (plan['external_pins'].get(config['profile']['path'])!=config['profile']['sha256']
                or plan['files']['runtime-members.json']!=config['runtime_members']['sha256']):
            raise ValueError('Executed GPS profile or code differs')
        for rel in ['src/lab_generate_skill/'+n+'.py'for n in DEPENDENCIES]+['scripts/run_site_navigation_once.py']:
            self.read(dict(path=str(Path(project)/rel),sha256=members[rel]['sha256']),json_value=False)
        raw=self.archive(config['archive'],config['index']);report=json.loads(raw['report.json'])
        self.environment_binding=dict(version=profile['version'],manifest_sha256=config['profile']['sha256'],
            resources_sha256=profile['resources']['sha256'],contracts_sha256=config['contracts']['sha256'])
        if report['binding']!=self.environment_binding:raise ValueError('GPS environment changed')
        cleanup=json.loads(raw['site-worker/map-instance-0/frozen-provider-cleanup.json'])
        if not cleanup['source_restoration']['restored'] or not cleanup['transport']['closed']:
            raise ValueError('Native transport cleanup not verified')
        for r in cleanup['transport']['requests']:
            if r['status']!=200 or digest(bodies[r['path']])!=r['sha256']:
                raise ValueError('Provider returned missing or altered native images')
        self.baseline=report['baseline'];shared=set()
        if len({c['source_task_id']for c in contracts})!=len(contracts):raise ValueError('Duplicate GPS source')
        for c in contracts:
            sid=c['source_task_id'];binding(c)
            if c.get('split')!='train' or c.get('heldout_quarantine')is not False or c['candidate_completion']['family']!='gps_overlay':
                raise ValueError('GPS training sources required')
            row=review_source(c,report,raw,bodies);shared.update(r['kind']for r in row['controls'])
            descriptor=dict(version='reviewed-gps-source-v1',source_task_id=sid,
                candidate_sha256=digest(json.dumps(c,sort_keys=True,separators=(',',':')).encode()),
                archive_sha256=config['archive']['sha256'],profile_sha256=config['profile']['sha256'])
            admission=dict(version='native-gps-normal-admission-v1',source_task_id=sid,passed=True,
                ordinary_lifecycle_verified=True,reset_verified=True,genuine_visible_tracks_verified=True,
                missing_response_rejected=True,environment_binding=self.environment_binding,
                baseline=self.baseline,actor_executed=False)
            self.sources[sid]=dict(candidate=deepcopy(c),admission=admission,baseline=self.baseline,environment_binding=self.environment_binding)
            self.descriptors[sid]=descriptor
        if not {'wrong_area','404'}<=shared:raise ValueError('Shared wrong-area and error-page controls missing')
        self.require_current()
