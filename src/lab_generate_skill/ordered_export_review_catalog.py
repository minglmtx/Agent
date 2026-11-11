"""Frozen, exact composition proof for one ordinary Map actor attempt.

Reuses native controls/reset; never accepts a provider-only or download-only
proof. Training publication remains separate from this execution admission.
"""
from copy import deepcopy
from pathlib import Path
import json
from .provider_review_catalog import ProviderReviewCatalog,digest
from .source_revision_binding import binding
from .map_ordered_export import validate,fingerprint

DEPENDENCIES=('map_ordered_export','map_ordered_export_observation','map_export_normal',
 'map_export_transport','map_osm_artifact','map_osm_native_reference','map_provider_observation',
 'map_provider_terminal','map_frozen_provider_runtime','map_provider_environment',
 'site_worker','map_query_site','map_reset_guard','browser_downloads')

class OrderedExportReviewCatalog(ProviderReviewCatalog):
    def __init__(self,config,*,project):
        self.closed=False;self.files={};self.sources={};self.descriptors={};self.config=deepcopy(config)
        v={k:self.read(config[k])for k in ('profile','contracts','review','plan','runtime_members')}
        profile,review,plan=v['profile'],v['review'],v['plan']
        if (profile.get('version')!='map-frozen-provider-environment-v1'
            or profile.get('runtime_external_requests')is not False
            or profile.get('original_snapshot_equivalence')is not False
            or profile['contracts']!=config['contracts']
            or review.get('version')!='ordered-export-independent-review-v1'
            or review.get('passed')is not True or review.get('reset_verified')is not True
            or review.get('worker_closed')is not True
            or review.get('plan_sha256')!=config['plan']['sha256']
            or review.get('runtime_members_sha256')!=config['runtime_members']['sha256']
            or review.get('profile_sha256')!=config['profile']['sha256']
            or plan['files']['runtime-members.json']!=config['runtime_members']['sha256']
            or plan['profile']!=config['profile']['path']):
            raise ValueError('Exact reviewed composition, reset and environment required')
        self.read(profile['resources'])
        self.environment_binding=dict(version=profile['version'],manifest_sha256=config['profile']['sha256'],
            resources_sha256=profile['resources']['sha256'],contracts_sha256=config['contracts']['sha256'])
        self.baseline=review['baseline']
        if review['environment_binding']!=self.environment_binding or not isinstance(self.baseline,str)or len(self.baseline)!=64:
            raise ValueError('Composition baseline/environment differs')
        candidates=v['contracts']['tasks']
        if len(candidates)!=1 or candidates[0]!=review['candidate']:
            raise ValueError('One exact independently reviewed candidate required')
        c=candidates[0];validate(c);binding(c)
        if c.get('split')!='train' or c.get('heldout_quarantine')is not False:
            raise ValueError('Training-only original source binding required')
        required={'noop':'failure','layer_only':'failure','positive':'success','wrong_layer':'failure','reversed':'failure','404':'failure'}
        if set(review['controls'])!=set(required) or any(review['controls'][k].get('status')!=s for k,s in required.items()):
            raise ValueError('Full composition controls required')
        for name in DEPENDENCIES:
            rel='src/lab_generate_skill/'+name+'.py'
            self.read(dict(path=str(Path(project)/rel),sha256=v['runtime_members'][rel]['sha256']),json_value=False)
        sid=c['source_task_id']
        if review['source_task_id']!=sid:raise ValueError('Reviewed source changed')
        descriptor=dict(version='reviewed-ordered-export-source-v1',source_task_id=sid,
            candidate_sha256=digest(json.dumps(c,sort_keys=True,separators=(',',':')).encode()),
            review_sha256=config['review']['sha256'],profile_sha256=config['profile']['sha256'])
        admission=dict(version='native-ordered-export-admission-v1',passed=True,source_task_id=sid,
            environment_binding=self.environment_binding,baseline=self.baseline,
            full_ordered_controls_verified=True,reset_verified=True,
            composition_fingerprint=fingerprint(c),training_publication_authorized=False)
        self.sources[sid]=dict(candidate=deepcopy(c),admission=admission,environment_binding=self.environment_binding,baseline=self.baseline)
        self.descriptors[sid]=descriptor;self.require_current()
