"""Bind native editor controls and cold resets without repeating completed sources.

A retained source may come from a batch whose sibling failed. Its own raw
controls and terminal must independently pass; a completed continuation must
prove the common final cold reset. Historical batch outcomes are never relabelled.
"""
from copy import deepcopy
from pathlib import Path
import json
from .provider_review_catalog import ProviderReviewCatalog,digest
from .account_review_catalog import AccountReviewCatalog
from .map_node_control_review import review_source
from .source_revision_binding import binding
from .map_node_task import environment_key

DEPENDENCIES=('map_query_site','map_reset_guard','site_worker','map_candidate_start',
    'map_view','map_route','map_editor_navigation','map_native_account_bootstrap',
    'map_node_task','map_node_episode','map_node_readout','map_node_completion',
    'map_node_write_audit','map_native_write_probe','map_write_sequences',
    'map_community_fixture','source_revision_binding','gobrowse_runtime','browser_prompt_contract')
REQUIRED={'noop':'failure','wrong_object':'failure','unsaved':'failure','positive':'success'}


def selected_rows(report, selected):
    """Fail closed for duplicates, missing sources and incomplete source results."""
    if (not selected or len(set(selected))!=len(selected)
            or report.get('site_closed')is not True or report.get('actor_attempts')!=0
            or report.get('api_calls')!=0
            or report.get('write_audit_preflight',{}).get('passed')is not True):
        raise ValueError('Closed native-only batch and distinct selected sources required')
    rows=report.get('sources',[])
    if len({r['source_task_id']for r in rows})!=len(rows):
        raise ValueError('Duplicate source results')
    found={r['source_task_id']:r for r in rows if r['source_task_id']in selected}
    if set(found)!=set(selected):raise ValueError('Selected completed source missing')
    for row in found.values():
        if (row.get('passed')is not True or row.get('terminal',{}).get('status')!='success'
                or len(row.get('controls',[]))!=len(REQUIRED)
                or {r['label']:r['status']for r in row['controls']}!=REQUIRED):
            raise ValueError('All source saved/draft/wrong/noop controls required')
    return found


class NodeReviewCatalog(ProviderReviewCatalog):
    def __init__(self,config,*,project):
        self.closed=False;self.files={};self.sources={};self.descriptors={};self.config=deepcopy(config)
        packet=self.read(config['contracts']);review=self.read(config['review'])
        if (review.get('status')!='native_node_source_controls_and_cold_reset_verified'
                or review.get('reset_verified')is not True or review.get('site_closed')is not True
                or review.get('native_write_audit_verified')is not True
                or review.get('actor_attempts')!=0):
            raise ValueError('Reviewed native task controls and cold reset required')
        cs=packet['tasks'];profile=packet['editor_profile'];by_id={c['source_task_id']:c for c in cs}
        checked={r['source_task_id']:r for r in review['sources']}
        if (not cs or len(by_id)!=len(cs)or len(checked)!=len(review['sources'])or set(checked)!=set(by_id)):
            raise ValueError('Exact independent source coverage required')
        initial=None;final_reset=None;seen=set()
        for batch in config['batches']:
            v={k:self.read(batch[k])for k in ('contracts','plan','runtime_members','report','archive_index')}
            plan,report=v['plan'],v['report']
            if (v['contracts']!=packet or plan['files']['runtime-members.json']!=batch['runtime_members']['sha256']
                    or plan['external_pins'].get(batch['contracts']['path'])!=batch['contracts']['sha256']):
                raise ValueError('Executed task or runtime binding differs')
            raw=AccountReviewCatalog.archive(self,batch['archive'],batch['archive_index'])
            if json.loads(raw['report.json'])!=report:raise ValueError('Archived node report differs')
            names=['src/lab_generate_skill/'+n+'.py'for n in DEPENDENCIES]+['scripts/run_site_navigation_once.py']
            for name in names:self.read(dict(path=str(Path(project)/name),sha256=v['runtime_members'][name]['sha256']),json_value=False)
            selected=batch['source_ids'];rows=selected_rows(report,selected)
            if not set(selected)<=set(by_id)or seen.intersection(selected):
                raise ValueError('Source reused twice or outside declared contracts')
            seen.update(selected)
            for sid in selected:
                c=by_id[sid];binding(c);row=rows[sid];prior=checked[sid]
                if (c.get('split')!='train'or c.get('heldout_quarantine')is not False
                        or c.get('candidate_completion',{}).get('family')!='persisted_map_node'
                        or row.get('task_id')!=c['task_id']or prior.get('controls')!=REQUIRED
                        or any(prior.get(k)is not True for k in ('frozen_evaluator_recomputed',
                            'original_start_verified','clean_initialization_verified'))):
                    raise ValueError('Exact training source and independent review required')
                actual=review_source(c,profile,raw)
                if actual['terminal']!=row['terminal']or actual['reset_signature']!=row['reset_signature']:
                    raise ValueError('Source summary differs from raw saved state')
                signature=actual['reset_signature']
                if signature['environment']!=environment_key(c,profile):raise ValueError('Initializer differs')
                if initial is None:initial=signature
                if signature!=initial:raise ValueError('Cold source initial states differ')
                descriptor=dict(version='reviewed-native-node-source-v1',source_task_id=sid,
                    candidate_sha256=digest(json.dumps(c,sort_keys=True,separators=(',',':')).encode()),
                    review_sha256=config['review']['sha256'],contracts_sha256=config['contracts']['sha256'])
                admission=dict(version='native-node-task-admission-v1',source_task_id=sid,passed=True,
                    ordinary_lifecycle_verified=True,source_start_verified=True,persisted_controls_verified=True,
                    native_write_audit_verified=True,cold_reset_verified=True,training_publication_authorized=False)
                self.sources[sid]=dict(candidate=deepcopy(c),profile=deepcopy(profile),initial_signature=signature,admission=admission)
                self.descriptors[sid]=descriptor
            if batch.get('reset_source_id')is not None:
                if (final_reset is not None or report.get('passed')is not True
                        or report.get('reset_verified')is not True or report.get('diagnostic')
                        or batch['reset_source_id']not in selected):
                    raise ValueError('One completed final cold reset required')
                final_reset=review_source(by_id[batch['reset_source_id']],profile,raw,prefix='final-reset',reset_only=True)
        if seen!=set(by_id)or final_reset is None or final_reset['reset_signature']!=initial:
            raise ValueError('Complete source controls and common final reset required')
        self.require_current()
