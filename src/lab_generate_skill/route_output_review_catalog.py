"""Bind independently reviewed ordinary controls to exact task and runtime bytes.

Reuses one verified reset and recorded per-control state isolation. Does not
claim two cold cycles, an actor result, or final training publication.
"""
from copy import deepcopy
from pathlib import Path
import json
from .provider_review_catalog import ProviderReviewCatalog,digest
from .source_revision_binding import binding
from .map_route_print import require_reference

DEPENDENCIES=('map_query_site','map_reset_guard','site_worker','map_candidate_start',
    'map_view','map_route','map_route_normal_capture','map_candidate_route_controls',
    'map_candidate_route_observation','map_candidate_route_terminal','map_route_print',
    'map_route_print_layout','map_route_print_episode','map_route_highways','map_highways_episode',
    'browser_print','gobrowse_runtime','browser_prompt_contract','source_revision_binding')


class RouteOutputReviewCatalog(ProviderReviewCatalog):
    def __init__(self,config,*,project):
        self.closed=False;self.files={};self.sources={};self.descriptors={};self.config=deepcopy(config)
        v={k:self.read(config[k])for k in ('contracts','review','plan','runtime_members','report','archive_index')}
        review,plan,report=v['review'],v['plan'],v['report']
        if (review.get('status')!='ordinary_source_controls_and_reset_verified'
                or not all(review.get(k)is True and report.get(k)is True for k in ('reset_verified','site_closed'))
                or report.get('passed')is not True or review.get('actor_attempts')!=0
                or plan['files']['runtime-members.json']!=config['runtime_members']['sha256']
                or plan['external_pins'].get(config['contracts']['path'])!=config['contracts']['sha256']):
            raise ValueError('Reviewed ordinary task, reset and code binding required')
        self.read(config['archive'],json_value=False)
        if (review['archive_sha256']!=config['archive']['sha256']
                or v['archive_index']['sha256']!=review['archive_sha256']
                or v['archive_index']['files']['report.json']['sha256']!=config['report']['sha256']
                or review['archive_members']!=len(v['archive_index']['files'])):
            raise ValueError('Independent review/raw result mismatch')
        for pin in config.get('evidence_pins',[]):self.read(pin,json_value=False)
        for name in DEPENDENCIES:
            rel='src/lab_generate_skill/'+name+'.py'
            self.read(dict(path=str(Path(project)/rel),sha256=v['runtime_members'][rel]['sha256']),json_value=False)
        rel='scripts/run_site_navigation_once.py'
        self.read(dict(path=str(Path(project)/rel),sha256=v['runtime_members'][rel]['sha256']),json_value=False)
        self.baseline=report['initial_fingerprint']
        if report['final_fingerprint']!=self.baseline or len(self.baseline)!=64:
            raise ValueError('Ordinary reset baseline changed')
        reference=v['contracts']['reference'];require_reference(reference)
        tasks=v['contracts']['tasks'];ids=[c['source_task_id']for c in tasks]
        if len(ids)!=len(set(ids)) or set(ids)!={r['source_task_id']for r in report['sources']}:
            raise ValueError('Exact source coverage required')
        for c in tasks:
            binding(c);sid=c['source_task_id']
            if c.get('split')!='train' or c.get('heldout_quarantine')is not False:
                raise ValueError('Source must remain in training scope')
            printing=c.get('browser_capabilities',{}).get('print_to_pdf')is True
            if not printing and c.get('answer_fields')!={'highway_refs':'text_list'}:
                raise ValueError('Reviewed print or structured highway output required')
            required={'noop':'failure','positive':'success','wrong_route':'failure','wrong_page':'failure'}
            if not printing:required['wrong_answer']='failure'
            controls=[r for r in review['controls']if r['source_task_id']==sid]
            actual={r['control']:r['status']for r in controls}
            raw=next(r for r in report['sources']if r['source_task_id']==sid)
            if (actual!=required or len(controls)!=len(required) or raw.get('passed')is not True
                    or {r['control']:r['judgment']['status']for r in raw['controls']}!=required
                    or any(not r['frozen_evaluator_recomputed']or not r['original_start_verified']or r['ordinary_action_errors']!=0 for r in controls)):
                raise ValueError('Complete independently recomputed controls required')
            descriptor=dict(version='reviewed-native-route-output-source-v1',source_task_id=sid,
                candidate_sha256=digest(json.dumps(c,sort_keys=True,separators=(',',':')).encode()),
                review_sha256=config['review']['sha256'],contracts_sha256=config['contracts']['sha256'])
            admission=dict(version='native-route-output-admission-v1',passed=True,source_task_id=sid,
                baseline=self.baseline,ordinary_lifecycle_verified=True,native_output_controls_verified=True,
                reset_verified=True,training_publication_authorized=False)
            self.sources[sid]=dict(candidate=deepcopy(c),reference=deepcopy(reference),
                baseline=self.baseline,admission=admission)
            self.descriptors[sid]=descriptor
        self.require_current()
