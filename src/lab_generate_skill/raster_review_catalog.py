"""Reuse pinned native PNG artifacts and each source's ordinary lifecycle proof.

Partial batch success is source-specific: another source's failed probe cannot
grant admission, but does not invalidate this source's complete controls/reset.
No websites or model inference run during admission.
"""
from copy import deepcopy
from decimal import Decimal
from io import BytesIO
import json
from pathlib import Path
import tempfile
from urllib.parse import urlsplit
from PIL import Image
from .account_review_catalog import AccountReviewCatalog
from .provider_review_catalog import digest
from .source_revision_binding import binding
from .map_candidate_start import validate_initial
from .map_raster_artifact import evaluate
from .map_raster_downloads import evaluate_downloads
from .map_raster_scale import multiplier, target_scale

DEPENDENCIES = ('site_worker', 'native_goal_dispatch', 'website_batch_profile',
    'map_query_site', 'map_reset_guard', 'map_candidate_start', 'map_view', 'map_route',
    'map_route_normal_capture', 'map_initial_route_proof', 'map_route_initialization_binding',
    'map_raster_site', 'map_raster_frontend', 'map_raster_observation',
    'map_raster_request', 'map_raster_scale', 'map_raster_artifact', 'map_raster_downloads')


class RasterReviewCatalog(AccountReviewCatalog):
    def __init__(self, config, *, project):
        self.closed = False; self.files = {}; self.sources = {}; self.descriptors = {}
        self.config = deepcopy(config)
        if config.get('layout') == 'combined-png-source-v1':
            self._combined(config, project)
            self.require_current()
            return
        native = self.archive(config['native_archive'], config['native_index'])
        native_report = json.loads(native['report.json'])
        if native_report.get('passed') is not True or native_report.get('site_closed') is not True:
            raise ValueError('Closed native artifact control batch required')
        receipts = [json.loads(line) for line in native['site/raster-receipts.jsonl'].splitlines()]
        entries = config['ordinary_sources']
        if not entries or len({e['source_task_id'] for e in entries}) != len(entries):
            raise ValueError('Distinct PNG source evidence required')
        for entry in entries:
            cfg = self.read(entry['contracts']); plan = self.read(entry['plan'])
            members = self.read(entry['runtime_members'])
            if (plan['files']['contracts.json'] != entry['contracts']['sha256']
                    or plan['files']['runtime-members.json'] != entry['runtime_members']['sha256']):
                raise ValueError('Ordinary job did not execute the pinned inputs')
            for pin in cfg['evidence_pins']:
                self.read(pin, json_value=False)
            paths = ['src/lab_generate_skill/' + n + '.py' for n in DEPENDENCIES]
            paths += ['scripts/run_site_navigation_once.py', 'scripts/serve_map_raster.py']
            for rel in paths:
                self.read(dict(path=str(Path(project) / rel), sha256=members[rel]['sha256']), json_value=False)
            raw = self.archive(entry['archive'], entry['index'])
            report = json.loads(raw['report.json']); baseline = cfg['baseline']
            if (report.get('worker_closed') is not True or report.get('actor_attempts') != 0
                    or report.get('final_fingerprint') != baseline or not baseline
                    or report.get('diagnostic') or report.get('cleanup_diagnostic')):
                raise ValueError('Ordinary worker final reset or cleanup unavailable')
            sid = entry['source_task_id']
            candidates = [c for c in cfg['tasks'] if c['source_task_id'] == sid]
            if len(candidates) != 1:
                raise ValueError('Exact source contract missing')
            c = candidates[0]; binding(c)
            if (c.get('split') != 'train' or c.get('heldout_quarantine')
                    or c['candidate_completion']['family'] != 'png_artifact'
                    or c.get('goal_revision', {}).get('derived_goal') != c['goal']):
                raise ValueError('Explicit training PNG derivative required')
            row = json.loads(raw[f'sources/{sid}/result.json'])
            if (row.get('passed') is not True or row.get('initial_fingerprint') != baseline
                    or row.get('final_fingerprint') != baseline):
                raise ValueError('Selected source did not pass full controls/reset')
            if not any(r.get('source_task_id') == sid and r.get('passed') is True for r in report['sources']):
                raise ValueError('Selected source absent from successful batch rows')
            self._ordinary(c, raw)
            self._native(c, native, receipts)
            descriptor = dict(version='reviewed-png-source-v1', source_task_id=sid,
                candidate_sha256=digest(json.dumps(c, sort_keys=True, separators=(',', ':')).encode()),
                ordinary_archive_sha256=entry['archive']['sha256'],
                native_archive_sha256=config['native_archive']['sha256'])
            admission = dict(version='native-png-normal-admission-v1', source_task_id=sid,
                passed=True, native_artifact_controls_verified=True, ordinary_lifecycle_verified=True,
                reset_verified=True, baseline=baseline)
            self.sources[sid] = dict(candidate=deepcopy(c), admission=admission, baseline=baseline)
            self.descriptors[sid] = descriptor
        self.require_current()

    @staticmethod
    def require_combined_source(report, row, sid):
        """A failed sibling does not erase complete source-specific evidence."""
        baseline=report.get('initial_fingerprint')
        if (report.get('site_closed') is not True or report.get('actor_attempts')!=0
                or report.get('diagnostic') or report.get('cleanup_diagnostic')
                or not baseline or report.get('final_fingerprint')!=baseline
                or row.get('source_task_id')!=sid or row.get('passed') is not True
                or row.get('reset_verified') is not True
                or row.get('initial_fingerprint')!=baseline or row.get('final_fingerprint')!=baseline
                or len([r for r in report.get('sources',[]) if r.get('source_task_id')==sid
                        and r.get('passed') is True])!=1):
            raise ValueError('Selected PNG source needs complete controls, reset and worker cleanup')
        return baseline

    def _combined(self, config, project):
        entries=config['sources']
        if not entries or len({e['source_task_id']for e in entries})!=len(entries):
            raise ValueError('Distinct source evidence required')
        for e in entries:
            cfg=self.read(e['contracts']);plan=self.read(e['plan']);members=self.read(e['runtime_members'])
            if (plan['files']['contracts.json']!=e['contracts']['sha256']
                    or plan['files']['runtime-members.json']!=e['runtime_members']['sha256']):
                raise ValueError('Executed PNG inputs differ from proof')
            for pin in cfg['evidence_pins']:self.read(pin,json_value=False)
            paths=['src/lab_generate_skill/'+n+'.py'for n in DEPENDENCIES]
            paths+=['scripts/run_site_navigation_once.py','scripts/serve_map_raster.py']
            for rel in paths:self.read(dict(path=str(Path(project)/rel),sha256=members[rel]['sha256']),json_value=False)
            raw=self.archive(e['archive'],e['index']);report=json.loads(raw['report.json']);sid=e['source_task_id']
            row=json.loads(raw[f'sources/{sid}/result.json'])
            baseline=self.require_combined_source(report,row,sid)
            candidates=[c for c in cfg['tasks']if c['source_task_id']==sid]
            if len(candidates)!=1:raise ValueError('Exact PNG source contract required')
            c=candidates[0];binding(c)
            if (c.get('split')!='train' or c.get('heldout_quarantine') is not False
                    or c['candidate_completion']['family']!='png_artifact'
                    or c.get('goal_revision',{}).get('derived_goal')!=c['goal']):
                raise ValueError('Explicit training PNG derivative required')
            policy=cfg.get('render_query_policy','default')
            if policy not in ('default','stable-scan') or report.get('render_query_policy','default')!=policy:
                raise ValueError('Executed renderer policy differs')
            receipts=[json.loads(line)for line in raw['site/raster-receipts.jsonl'].splitlines()]
            if any(r.get('query_policy')!=policy for r in receipts):
                raise ValueError('Actual renderer receipts use another policy')
            # Bind private execution configuration from the actual factory
            # record. Public goal/start and source revision are unchanged.
            c=deepcopy(c)
            if policy!='default':c['render_query_policy']=policy
            prefix=f'sources/{sid}/native/'
            native={sid+'/'+name[len(prefix):]:body for name,body in raw.items()if name.startswith(prefix)}
            self._ordinary(c,raw);self._native(c,native,receipts)
            if multiplier(c)!=1:
                original=json.loads(native[sid+'/initial-export-form.json'])
                submitted=json.loads(native[sid+'/submitted-request.json'])
                if (submitted['scale']!=target_scale(c,original['scale'])
                        or submitted['bbox']!=original['bbox']):
                    raise ValueError('Declared scale operation or unchanged export bounds not verified')
            descriptor=dict(version='reviewed-combined-png-source-v1',source_task_id=sid,
                candidate_sha256=digest(json.dumps(c,sort_keys=True,separators=(',',':')).encode()),
                archive_sha256=e['archive']['sha256'],render_query_policy=policy)
            self.sources[sid]=dict(candidate=deepcopy(c),baseline=baseline,admission=dict(
                version='native-png-normal-admission-v1',source_task_id=sid,passed=True,
                native_artifact_controls_verified=True,ordinary_lifecycle_verified=True,
                reset_verified=True,baseline=baseline,render_query_policy=policy))
            self.descriptors[sid]=descriptor

    @staticmethod
    def _ordinary(c, raw):
        sid = c['source_task_id']
        controls=[('noop','failure'),('positive','success')]
        if multiplier(c)!=1:controls.append(('unchanged_scale','failure'))
        for control, expected in controls:
            prefix = f'sources/{sid}/{control}/'
            terminal = json.loads(raw[prefix + 'png-terminal.json'])
            ref = json.loads(raw[prefix + 'png-reference/initial.json'])
            image = raw[prefix + 'png-reference/reference.png']
            if (ref.get('anonymous_context') is not True or ref.get('before_actor_inference') is not True
                    or ref.get('actor_context_actions') != 0 or digest(image) != ref['sha256']
                    or len(image) != ref['bytes'] or terminal.get('integrity') is not True
                    or terminal.get('capture_error') is not None
                    or terminal.get('events') != ['prepare', 'attach', 'observe_initial',
                        'capture_terminal', 'close', 'provide_trace', 'score_terminal']):
                raise ValueError('Private initial reference or complete lifecycle missing')
            for start in (ref['initial'], ref['independent_initial']):
                u = urlsplit(start['url']); origin = u.scheme + '://' + u.netloc
                validate_initial(c, origin, start['url'], start['view'], start['route'])
            if bool(ref['request']['route']) != c['candidate_completion']['retain_route']:
                raise ValueError('PNG route inclusion differs from public task')
            if multiplier(c)!=1:
                initial=ref['initial_public_request'];wanted=target_scale(c,str(initial['scale']))
                if (Decimal(str(ref['request']['scale']))!=Decimal(wanted)
                        or any(ref['request'][k]!=initial[k]for k in ('bbox','route','format'))):
                    raise ValueError('Private scaled reference differs from declared initial form')
            with tempfile.TemporaryDirectory(prefix='review-png-download-') as tmp:
                root = Path(tmp)
                for name, body in raw.items():
                    start = prefix + 'browser-downloads/'
                    if name.startswith(start):
                        local = root / name[len(start):]
                        if local.parent != root:
                            raise ValueError('Download must be a flat owned file')
                        local.write_bytes(body)
                value = evaluate_downloads(root, expected_request=ref['request'], reference_body=image,
                                           receipts=terminal['receipts'], integrity=True)
            if value != terminal['judgment'] or value['status'] != expected:
                raise ValueError('Ordinary download evidence does not reproduce its score')

    @staticmethod
    def _native(c, raw, receipts):
        sid = c['source_task_id']; row = json.loads(raw[sid + '/result.json'])
        body, reference, negative = (raw[sid + '/' + name] for name in ('download.png', 'repeat.png', 'negative.png'))
        if digest(body) != row['download_sha256']:
            raise ValueError('Native download changed')
        receipt = row['receipt']; request = {k: receipt['request'][k] for k in ('bbox', 'scale', 'format', 'route')}
        if bool(request['route']) != c['candidate_completion']['retain_route']:
            raise ValueError('Native control covers another route profile')
        wrong = [r for r in receipts if r['sha256'] == digest(negative)]
        if len(wrong) != 1:
            raise ValueError('One owned negative renderer receipt required')
        buffer = BytesIO()
        with Image.open(BytesIO(body)) as image:
            Image.new('RGB', image.size, 'white').save(buffer, 'PNG')
        cases = dict(positive=evaluate(body, receipt, request, reference),
            wrong_area_or_missing_route=evaluate(negative, wrong[0], request, reference),
            no_file=evaluate(b'', receipt, request, reference),
            blank_file=evaluate(buffer.getvalue(), receipt, request, reference),
            wrong_receipt=evaluate(body, wrong[0], request, reference))
        if (json.loads(json.dumps(cases)) != row['artifact_controls']
                or any(v['status'] != ('success' if k == 'positive' else 'failure') for k, v in cases.items())):
            raise ValueError('Native artifact control scores changed')
