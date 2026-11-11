"""Reuse completed CPU PDF reviews without decoding PDFs on the GPU worker.

The CPU reviewer must independently reconstruct controls and bind their raw
archives, contracts and tested runtime. Startup verifies those exact bytes once;
subsequent task dispatch checks file identities, not website state or rewards.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from .provider_review_catalog import identity
from .source_revision_binding import binding, fingerprint


DEPENDENCIES = ('site_worker', 'native_goal_dispatch', 'website_batch_profile',
    'map_query_site', 'map_reset_guard', 'map_candidate_start', 'map_view', 'map_route',
    'map_route_normal_capture', 'map_initial_route_proof', 'map_route_initialization_binding',
    'map_raster_site', 'map_raster_frontend', 'map_raster_observation',
    'map_raster_request', 'map_raster_scale', 'map_raster_artifact', 'map_pdf_artifact',
    'map_raster_downloads', 'frozen_raster_actor_adapter')
RUNTIME_FILES = tuple('src/lab_generate_skill/' + n + '.py' for n in DEPENDENCIES) + (
    'scripts/run_site_navigation_once.py', 'scripts/serve_map_raster.py')
NATIVE_CONTROLS = dict(positive='success', wrong_area_or_missing_route='failure',
                      no_file='failure', blank_file='failure', wrong_receipt='failure')
ORDINARY_CONTROLS = dict(noop='failure', wrong_format='failure', positive='success')


class PdfReviewCatalog:
    def __init__(self, config, *, project):
        self.closed = False; self.files = {}; self.sources = {}; self.descriptors = {}
        self.config = deepcopy(config)
        review = self.read(config['review'])
        contracts = self.read(config['contracts'])
        if (review.get('version') != 'native-pdf-compiled-admission-review-v1'
                or review.get('contracts') != config['contracts']
                or review.get('all_raw_evidence_independently_reviewed') is not True
                or review.get('render_query_policy') != 'stable-scan'
                or review.get('ordinary_factory_verified') is not True
                or review.get('reset_verified') is not True
                or review.get('actor_attempts') != 0 or review.get('api_calls') != 0
                or review.get('unresolved') != [] or not review.get('baseline')):
            raise ValueError('Completed CPU PDF control/factory review required')
        from .reviewed_code_evolution import runtime_dependencies
        runtime = runtime_dependencies(self, review.get('runtime_files', {}), RUNTIME_FILES)
        for relative, digest in runtime.items():
            self.read(dict(path=str(Path(project) / relative), sha256=digest), json_value=False)
        evidence = review.get('evidence')
        if (not isinstance(evidence, list) or not evidence
                or len({p['path'] for p in evidence}) != len(evidence)):
            raise ValueError('Distinct original evidence pins required')
        for pin in evidence:
            self.verify_file(pin)
        rows = contracts.get('tasks', [])
        reviewed = review.get('sources', [])
        by_source = {r['source_task_id']: r for r in reviewed}
        if (not rows or len({c['source_task_id'] for c in rows}) != len(rows)
                or len(by_source) != len(reviewed)
                or {c['source_task_id'] for c in rows} != set(by_source)):
            raise ValueError('Reviewed PDF source coverage differs')
        for c in rows:
            binding(c); sid = c['source_task_id']; r = by_source[sid]
            if (c['domain'] != 'map' or c.get('split') != 'train'
                    or c.get('heldout_quarantine') is not False
                    or c['candidate_completion']['family'] != 'pdf_artifact'
                    or c.get('training_admitted') is not False
                    or r.get('candidate_sha256') != fingerprint(c)
                    or r.get('native_controls') != NATIVE_CONTROLS
                    or r.get('ordinary_controls') != ORDINARY_CONTROLS
                    or r.get('initial_state_verified') is not True
                    or r.get('reset_verified') is not True
                    or r.get('unresolved') != []):
                raise ValueError('Exact PDF task, initial state and complete controls required')
            descriptor = dict(version='reviewed-native-pdf-source-v1', source_task_id=sid,
                candidate_sha256=fingerprint(c), compiled_review_sha256=config['review']['sha256'])
            admission = dict(version='native-pdf-normal-admission-v1', source_task_id=sid,
                passed=True, native_artifact_controls_verified=True,
                ordinary_lifecycle_verified=True, reset_verified=True,
                render_query_policy='stable-scan', baseline=review['baseline'])
            self.sources[sid] = dict(candidate=deepcopy(c), admission=admission, baseline=review['baseline'])
            self.descriptors[sid] = descriptor
        self.require_current()

    def read(self, pin, *, json_value=True):
        from .reviewed_evidence_snapshot import evidence_path
        path = evidence_path(self, pin)
        if not path.is_absolute():
            raise ValueError('Absolute pinned evidence required')
        before = identity(path); body = path.read_bytes()
        actual = hashlib.sha256(body).hexdigest()
        if actual != pin['sha256']:
            from .reviewed_code_evolution import accepts
            if not accepts(self, pin, path, actual, json_value=json_value):
                raise ValueError('Reviewed PDF input changed')
        if identity(path) != before:
            raise ValueError('Reviewed PDF input changed during read')
        self.files[path] = before
        return json.loads(body) if json_value else body

    def verify_file(self, pin):
        path = Path(pin['path'])
        if not path.is_absolute():
            raise ValueError('Absolute original artifact required')
        before = identity(path); h = hashlib.sha256()
        with path.open('rb') as f:
            for block in iter(lambda: f.read(4 * 1024**2), b''):
                h.update(block)
        if h.hexdigest() != pin['sha256'] or identity(path) != before:
            raise ValueError('Independently reviewed PDF evidence changed')
        self.files[path] = before

    def require_current(self):
        if self.closed or any(identity(p) != value for p, value in self.files.items()):
            raise ValueError('PDF proof changed or closed')

    def resolve(self, sid, descriptor):
        self.require_current()
        if sid not in self.sources or descriptor != self.descriptors[sid]:
            raise ValueError('Exact reviewed PDF source required')
        from .reviewed_code_evolution import require_source
        require_source(self, sid)
        return deepcopy(self.sources[sid])

    def close(self):
        self.closed = True
        self.sources.clear()
