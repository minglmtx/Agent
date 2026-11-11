"""Source-bound admission from two actual native comparison-control batches.

Read archived evidence once per worker, retain file guards, and never start
websites or execute control actions in ordinary sampling.
"""
from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit
from PIL import Image
from .account_review_catalog import AccountReviewCatalog
from .provider_review_catalog import digest
from .source_revision_binding import binding
from .map_provider_resources import validate_tile, require_candidate_resources
from .map_layer_comparison import evaluate

DEPENDENCIES = ('site_worker','map_query_site','map_reset_guard','map_provider_environment',
    'map_provider_observation','map_provider_terminal','map_provider_contract',
    'map_provider_coverage','map_provider_resources','map_frozen_provider_runtime',
    'map_layer_comparison','map_candidate_start','map_route','map_view',
    'frozen_provider_actor_adapter','website_batch_profile','native_goal_dispatch')
LIFECYCLE = ['prepare','attach','observe_initial','capture_terminal','close','score_terminal']


def require_source_controls(report, sid):
    baseline = report.get('baseline')
    if (not baseline or report.get('final_fingerprint') != baseline
            or report.get('reset_verified') is not True or report.get('worker_closed') is not True
            or report.get('actor_attempts') != 0 or report.get('diagnostic') or report.get('cleanup_diagnostic')):
        raise ValueError('Complete native baseline, reset and worker cleanup required')
    rows = [r for r in report['sources'] if r['source_task_id'] == sid]
    if len(rows) != 1: raise ValueError('Unique exact source control required')
    row = rows[0]
    if (row.get('passed') is not True or row.get('initial_fingerprint') != baseline
            or row.get('final_fingerprint') != baseline or row.get('diagnostic')):
        raise ValueError('Source control did not pass on this baseline')
    controls = row['controls']; kinds = [r['kind'] for r in controls]
    if len(kinds) != len(set(kinds)) or not {'noop','positive'} <= set(kinds):
        raise ValueError('Source-specific no-op and positive controls required')
    for control in controls:
        expected = 'success' if control['kind'] == 'positive' else 'failure'
        if (control.get('passed') is not True or control.get('integrity') is not True
                or control.get('judgment',{}).get('status') != expected
                or control.get('lifecycle') != LIFECYCLE or control.get('diagnostic')):
            raise ValueError('Source ordinary control lifecycle or score differs')
    return row


def review_source(candidate, report, raw, bodies):
    sid = candidate['source_task_id']; row = require_source_controls(report,sid)
    positive = json.loads(raw[f'sources/{sid}/positive/comparison-terminal.json'])
    code = candidate['candidate_completion']['required_codes'][1]
    templates = {f['state']['active'][0]['template'] for f in positive['frames']
                 if f['state']['active'][0]['code'] == code}
    if len(templates) != 1: raise ValueError('Observed genuine provider frame required')
    u = urlsplit(templates.pop()); server = SimpleNamespace(url=u.scheme+'://'+u.netloc,bodies=bodies)
    for control in row['controls']:
        kind = control['kind']; prefix = f'sources/{sid}/{kind}/'
        t = json.loads(raw[prefix+'comparison-terminal.json']); page = json.loads(raw[prefix+'terminal-page.json'])
        if (t['terminal'] != page or t['integrity'] is not True or t['baseline'] != report['baseline']
                or t['events'] != LIFECYCLE or t['environment_binding'] != report['binding']):
            raise ValueError('Actual terminal lifecycle or environment binding differs')
        for h in t['standard_reference_sha256'].values():
            data = raw[prefix+'standard-reference/'+h+'.png']
            if digest(data) != h: raise ValueError('Native Standard reference bytes changed')
            with Image.open(BytesIO(data)) as image:
                if image.format != 'PNG' or image.size != (256,256): raise ValueError('Invalid Standard tile')
                image.load()
        initial = json.loads(raw[prefix+'initial-page-health.json']); u = urlsplit(initial['url'])
        kwargs = dict(initial=t['initial'],terminal=t['native_terminal'],page=page,site_origin=u.scheme+'://'+u.netloc,
            frames=t['frames'],server=server,response_hashes=t['response_sha256'],standard_origin=t['standard_origin'],
            standard_references=t['standard_reference_sha256'],initial_route=t['initial_route'],
            terminal_route=t['terminal_route'],integrity=True,observed_codes=t['observed_codes'])
        actual = evaluate(candidate['candidate_completion'],**kwargs)
        if actual != t['judgment'] or actual != control['judgment']:
            raise ValueError('Actual comparison judgment cannot be reproduced')
        if kind == 'positive':
            kwargs['frames'] = [f for f in t['frames'] if f['state']['active'][0]['code'] != code]
            reduced = evaluate(candidate['candidate_completion'],**kwargs)
            if reduced['status'] != 'unknown' or reduced != control['missing_loaded_history_mutation']:
                raise ValueError('Unverified layer must not earn reward')
    return row


class ComparisonReviewCatalog(AccountReviewCatalog):
    def __init__(self,config,*,project):
        self.closed=False; self.files={}; self.sources={}; self.descriptors={}; self.config=deepcopy(config)
        profile=self.read(config['profile']); contracts=self.read(config['contracts'])['tasks']
        if (profile.get('version')!='map-frozen-provider-environment-v1'
                or profile.get('runtime_external_requests')is not False
                or profile.get('original_snapshot_equivalence')is not False
                or profile['contracts']!=config['contracts']):
            raise ValueError('Exact frozen provider profile required')
        resources=self.read(profile['resources']); require_candidate_resources(resources,contracts)
        resource_archives={}
        # Resources already have member/pixel receipts. Reuse the same verifier,
        # while tracking every archive identity for the worker lifetime.
        from .map_provider_resources import checked_archive
        for r in resources['sources']:
            self.read(dict(path=r['archive'],sha256=r['sha256']),json_value=False)
            resource_archives[r['sha256']]=checked_archive(r)
        bodies={}
        for provider,spec in resources['providers'].items():
            for key,row in spec['files'].items():
                files=resource_archives[row['archive_sha256']];validate_tile(provider,key,row,files)
                bodies['/tiles/'+provider+'/'+key]=files[row['member']]
        batches=config['batches']
        if len(batches)!=2 or len({b['archive']['sha256']for b in batches})!=2:
            raise ValueError('Two distinct completed native factory records required')
        loaded=[]
        self.environment_binding=dict(version=profile['version'],manifest_sha256=config['profile']['sha256'],
            resources_sha256=profile['resources']['sha256'],contracts_sha256=config['contracts']['sha256'])
        for b in batches:
            plan=self.read(b['plan'])
            if 'completed' in b:
                receipt=self.read(b['completed'])
                if (receipt.get('returncode') != 0
                        or receipt.get('plan_sha256') != b['plan']['sha256']
                        or receipt.get('capsule') != plan.get('capsule')
                        or receipt.get('archive') != b['archive']['path']
                        or receipt.get('archive_sha256') != b['archive']['sha256']
                        or receipt.get('actor_calls') != 0
                        or plan.get('source_ids') != b['source_ids']):
                    raise ValueError('Completed capsule/control receipt differs')
                capsule=self.read(plan['capsule'])
                self.read(dict(path=capsule['archive'],sha256=capsule['archive_sha256']),json_value=False)
                members=capsule['members']
                index=self.read(b['index'])
                if index.get('files') != receipt.get('members'):
                    raise ValueError('Completed archive members differ from index')
            else:
                members=self.read(b['runtime_members'])
                if plan['files']['runtime-members.json']!=b['runtime_members']['sha256']:
                    raise ValueError('Actual executed runtime differs')
            if plan['external_pins'].get(config['profile']['path'])!=config['profile']['sha256']:
                raise ValueError('Actual executed profile differs')
            raw=self.archive(b['archive'],b['index']);report=json.loads(raw['report.json'])
            if report.get('binding')!=self.environment_binding:raise ValueError('Native environment differs')
            for name in DEPENDENCIES:
                rel='src/lab_generate_skill/'+name+'.py'
                self.read(dict(path=str(Path(project)/rel),sha256=members[rel]['sha256']),json_value=False)
            rel='scripts/run_site_navigation_once.py'
            self.read(dict(path=str(Path(project)/rel),sha256=members[rel]['sha256']),json_value=False)
            loaded.append((b,members,raw,report))
        # The new warmup was verified on six sources; it changes initialization
        # only. Other execution and scoring dependencies must match both batches.
        latest=loaded[-1]
        rel='src/lab_generate_skill/map_tile_warmup.py'
        self.read(dict(path=str(Path(project)/rel),sha256=latest[1][rel]['sha256']),json_value=False)
        if loaded[0][3]['baseline']!=latest[3]['baseline']:raise ValueError('Cold baselines differ')
        self.baseline=latest[3]['baseline']
        repeated=config.get('cold_source_coverage')=='each_source_twice'
        if config.get('cold_source_coverage') not in (None,'each_source_twice'):
            raise ValueError('Unknown cold source coverage policy')
        selected={}
        for batch in loaded:
            b=batch[0]
            if len(b['source_ids'])!=len(set(b['source_ids'])):
                raise ValueError('Duplicate source inside a cold batch')
            for sid in b['source_ids']:selected.setdefault(sid,[]).append(batch)
        if (set(selected)!={c['source_task_id']for c in contracts}
                or any(len(v)!=(2 if repeated else 1)for v in selected.values())):
            raise ValueError('Exact declared cold source coverage required')
        shared_negative_kinds=set()
        for c in contracts:
            sid=c['source_task_id'];binding(c)
            if c.get('split')!='train' or c.get('heldout_quarantine')is not False or c['candidate_completion']['family']!='base_layer_comparison':
                raise ValueError('Training comparison source required')
            source_kinds=set()
            for b,_,raw,report in selected[sid]:
                row=review_source(c,report,raw,bodies)
                source_kinds.update(r['kind']for r in row['controls'])
            shared_negative_kinds.update(source_kinds)
            if repeated and c['candidate_completion'].get('completion_boundary')=='view_both_declared_layers_then_select_target_same_initial_area' and 'wrong_final' not in source_kinds:
                raise ValueError('Explicit final-layer goal requires a wrong-final-layer control')
            descriptor=dict(version='reviewed-comparison-source-v1',source_task_id=sid,
                candidate_sha256=digest(json.dumps(c,sort_keys=True,separators=(',',':')).encode()),
                archive_sha256=b['archive']['sha256'],profile_sha256=config['profile']['sha256'])
            if repeated:
                descriptor['cold_archive_sha256']=[entry[0]['archive']['sha256']for entry in selected[sid]]
            admission=dict(version='native-layer-comparison-normal-admission-v1',source_task_id=sid,passed=True,
                two_cold_environment_verified=True,ordinary_lifecycle_verified=True,environment_binding=self.environment_binding,
                baseline=self.baseline,observed_pair_history_verified=True,single_layer_rejected=True,
                unverified_loading_not_rewarded=True,actor_executed=False)
            self.sources[sid]=dict(candidate=deepcopy(c),admission=admission,baseline=self.baseline,environment_binding=self.environment_binding)
            self.descriptors[sid]=descriptor
        if not {'wrong_area','404'}<=shared_negative_kinds:raise ValueError('Shared wrong-area and error-page controls missing')
        self.require_current()
