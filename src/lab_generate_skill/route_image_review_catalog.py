"""Bind actual saved-PNG controls, initial state and reset to actor admission."""
from copy import deepcopy
from pathlib import Path
import json
from .provider_review_catalog import ProviderReviewCatalog,digest
from .source_revision_binding import binding
from .map_route_image_request import native_line

DEPENDENCIES=('map_query_site','map_reset_guard','site_worker','map_candidate_start',
    'map_view','map_route','map_route_image_request','map_route_image_downloads',
    'map_route_image_episode','map_raster_site','map_raster_frontend','map_raster_request',
    'map_raster_artifact','map_raster_observation','map_raster_downloads','map_raster_scale',
    'browser_downloads','gobrowse_runtime','browser_prompt_contract','source_revision_binding')
SCRIPTS=('run_site_navigation_once','serve_map_raster')
REQUIRED={'noop':'failure','positive':'success','alternate_endpoint':'success',
          'wrong_route':'failure','no_route':'failure','clipped':'failure'}


class RouteImageReviewCatalog(ProviderReviewCatalog):
    def __init__(self,config,*,project):
        self.closed=False;self.files={};self.sources={};self.descriptors={};self.config=deepcopy(config)
        v={k:self.read(config[k])for k in ('contracts','review','plan','runtime_members','report','archive_index')}
        review,plan,report=v['review'],v['plan'],v['report']
        if (review.get('status')!='ordinary_source_controls_and_reset_verified'
                or not all(review.get(k)is True and report.get(k)is True for k in ('reset_verified','site_closed'))
                or report.get('passed')is not True or review.get('actor_attempts')!=0
                or not review.get('independent_pixels_rechecked')or not review.get('route_overlay_changes_pixels')
                or plan['files']['runtime-members.json']!=config['runtime_members']['sha256']
                or plan['external_pins'].get(config['contracts']['path'])!=config['contracts']['sha256']):
            raise ValueError('Reviewed image task, pixel controls, reset and code binding required')
        self.read(config['archive'],json_value=False)
        if (review['archive_sha256']!=config['archive']['sha256']
                or v['archive_index']['sha256']!=review['archive_sha256']
                or v['archive_index']['files']['report.json']['sha256']!=config['report']['sha256']
                or review['archive_members']!=len(v['archive_index']['files'])):
            raise ValueError('Independent review/raw artifact mismatch')
        for pin in config.get('evidence_pins',[]):self.read(pin,json_value=False)
        names=['src/lab_generate_skill/'+n+'.py'for n in DEPENDENCIES]+['scripts/'+n+'.py'for n in SCRIPTS]
        for rel in names:
            self.read(dict(path=str(Path(project)/rel),sha256=v['runtime_members'][rel]['sha256']),json_value=False)
        self.baseline=report['initial_fingerprint']
        if report['final_fingerprint']!=self.baseline or len(self.baseline)!=64:
            raise ValueError('Image reset baseline changed')
        c=v['contracts']['candidate'];binding(c);sid=c['source_task_id']
        refs=v['contracts']['references']
        if len(refs)!=2:raise ValueError('Both independently identified endpoints required')
        for ref in refs:native_line(ref)
        if (c.get('split')!='train' or c.get('heldout_quarantine')is not False
                or c.get('candidate_completion',{}).get('family')!='route_png_artifact'
                or sid!=review.get('source_task_id')or sid!=report.get('source_task_id')):
            raise ValueError('Exact image training source required')
        controls=review['controls'];raw=report['controls']
        if (len(controls)!=len(REQUIRED)or len(raw)!=len(REQUIRED)
                or {r['control']:r['status']for r in controls}!=REQUIRED
                or {r['control']:r['judgment']['status']for r in raw}!=REQUIRED
                or any(not r['frozen_evaluator_recomputed']or not r['original_start_verified'] for r in controls)
                or any(not r['passed']or not r['integrity']for r in raw)
                or next(r for r in raw if r['control']=='positive').get('route_overlay_changes_pixels')is not True):
            raise ValueError('Complete independently recomputed image controls required')
        descriptor=dict(version='reviewed-native-route-image-source-v1',source_task_id=sid,
            candidate_sha256=digest(json.dumps(c,sort_keys=True,separators=(',',':')).encode()),
            review_sha256=config['review']['sha256'],contracts_sha256=config['contracts']['sha256'])
        admission=dict(version='native-route-image-admission-v1',passed=True,source_task_id=sid,
            baseline=self.baseline,ordinary_lifecycle_verified=True,native_artifact_controls_verified=True,
            render_query_policy='stable-scan',reset_verified=True,training_publication_authorized=False)
        self.sources[sid]=dict(candidate=deepcopy(c),references=deepcopy(refs),baseline=self.baseline,admission=admission)
        self.descriptors[sid]=descriptor;self.require_current()
