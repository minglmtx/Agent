"""Current entries backed by the exact adapters used in reviewed first runs."""
from copy import deepcopy
from pathlib import Path
import csv
import hashlib
import io
import json

from lab_generate_skill.provider_review_catalog import identity
from .qualified_gps import Adapter as GPSAdapter
from .qualified_layers import Adapter as LayerAdapter


class ScopeCatalog:
    KIND = None
    ADAPTER = None

    def __init__(self, config, *, project):
        self.config = deepcopy(config)
        self.project = Path(project).resolve()
        self.files, self.sources, self.descriptors = {}, {}, {}
        self.closed = False
        self.config_digest = self.digest(config)
        try:
            if config.get('version') != 'reviewed-native-scope-entry-v190' or config.get('kind') != self.KIND:
                raise ValueError('Explicit qualified native scope family required')
            required = {'src/lab_generate_skill/map_scope_v190/' + n for n in
                        ('__init__.py', 'catalog.py', 'adapter.py', 'qualified_gps.py', 'qualified_layers.py')}
            required.add('src/lab_generate_skill/reviewed_map_registry.py')
            required.update('src/lab_generate_skill/' + name + '.py' for name in (
                'actor_protocol', 'observation_budget', 'source_revision_binding',
                'native_goal_dispatch', 'reviewed_protocol_bundle'))
            if self.KIND == 'gps_document_v190':
                required.update('scripts/' + name for name in ('gps_hooks.py', 'gps_terminal.py'))
                required.update('src/lab_generate_skill/' + name + '.py' for name in (
                    'map_gps_document_resources', 'map_frozen_provider_runtime',
                    'map_provider_contract', 'map_provider_resources'))
            else:
                required.update('src/lab_generate_skill/' + name + '.py' for name in (
                    'map_layer_scope_revision', 'map_native_layer_runtime', 'map_native_layer_completion'))
            if not required <= config['runtime_files'].keys():
                raise ValueError('Complete source entry implementation must be pinned')
            for name, digest in config['runtime_files'].items():
                if Path(name).is_absolute() or '..' in Path(name).parts:
                    raise ValueError('Contained runtime member required')
                self.read(dict(path=str(self.project / name), sha256=digest), parse=False)
            plan = self.read(config['qualified_plan'])
            original_adapter_path = str(Path(config['qualified_plan']['path']).parent / 'adapter.py')
            qualified = [r for r in plan['files'] if r['path'] == original_adapter_path]
            if len(qualified) != 1:
                raise ValueError('Original executed adapter pin required')
            local_adapter = 'qualified_gps.py' if self.KIND == 'gps_document_v190' else 'qualified_layers.py'
            if self.read(qualified[0], parse=False) != (self.project / 'src/lab_generate_skill/map_scope_v190' / local_adapter).read_bytes():
                raise ValueError('Native lifecycle adapter differs from the executed candidate')
            if self.KIND == 'gps_document_v190' and config.get('profile') != plan.get('profile'):
                raise ValueError('GPS startup profile differs from the qualified native environment')
            review = self.read(config['actor_review'])
            if not review.get('passed') or not review.get('all_archive_members_verified'):
                raise ValueError('Independent complete first-Actor review required')
            for reference in config['retained_evidence']:
                self.track(reference)
            inventory = [json.loads(line) for line in self.read(config['inventory'], parse=False).decode().splitlines()]
            inventory = {row['task_id']: row for row in inventory}
            training = list(csv.DictReader(io.StringIO(self.read(config['training_scope'], parse=False).decode('utf-8-sig'))))
            training = {row['source_task_id']: row for row in training}
            self.adapter = self.ADAPTER(plan)
            if self.KIND == 'gps_document_v190':
                candidates = {self.adapter.c['source_task_id']: self.adapter.c}
                descriptors = {sid: self.adapter.descriptor for sid in candidates}
                reviewed = {review['source_task_id']: review['task_id']}
                if review.get('first_actor_executions') != 1 or not review.get('environment_closed'):
                    raise ValueError('Closed first GPS execution required')
            else:
                candidates = self.adapter.candidates
                descriptors = {sid: dict(version='public-overlay-ordinary-admission-v190',
                    source_task_id=sid, task_id=c['task_id'], native_proof=plan['native_proof'],
                    input_review=plan['input_review']) for sid, c in candidates.items()}
                reviewed = {row['source_task_id']: row['new_task_id'] for row in review['rows']}
                if review.get('reviewed_sources') != 6 or not review.get('all_capsule_hashes_verified'):
                    raise ValueError('All six independently reviewed new overlay executions required')
                if any(not row.get('passed') or not row.get('first_execution_of_new_public_goal')
                       or row.get('status') not in ('success', 'failure') for row in review['rows']):
                    raise ValueError('Every revised source must have a reviewed valid first outcome')
            if set(candidates) != set(config['source_ids']) or len(config['source_ids']) != len(candidates):
                raise ValueError('Exact qualified source set required')
            for sid, candidate in candidates.items():
                scope, original = training.get(sid, {}), inventory.get(sid, {})
                if (scope.get('split') != 'train' or scope.get('domain') != 'map'
                        or scope.get('heldout_quarantine', '').lower() not in ('', 'false')
                        or original.get('heldout_quarantine') is not False
                        or original.get('domain') != 'map' or reviewed.get(sid) != candidate['task_id']):
                    raise ValueError('Exact non-heldout training source and reviewed new identity required')
                self.adapter.require_original_binding(candidate, candidate, original)
                admission = self.adapter.require_admission(candidate, descriptors[sid])
                self.sources[sid] = dict(candidate=deepcopy(candidate), admission=admission,
                                        training_source_verified=True)
                self.descriptors[sid] = deepcopy(descriptors[sid])
            self.require_current()
        except BaseException:
            self.close()
            raise

    @staticmethod
    def digest(value):
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

    def read(self, reference, *, parse=True):
        path = Path(reference['path'])
        if not path.is_absolute() or path.is_symlink():
            raise ValueError('Pinned absolute regular evidence required')
        before = identity(path)
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != reference['sha256'] or identity(path) != before:
            raise ValueError('Reviewed scope evidence changed: ' + str(path))
        self.files[path] = before
        return json.loads(raw) if parse else raw

    def track(self, reference):
        path = Path(reference['path'])
        if not path.is_absolute() or path.is_symlink():
            raise ValueError('Pinned absolute retained evidence required')
        before = identity(path)
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(8 * 1024 ** 2), b''):
                digest.update(block)
        if digest.hexdigest() != reference['sha256'] or identity(path) != before:
            raise ValueError('Retained native evidence changed')
        self.files[path] = before

    def require_current(self):
        if (self.closed or self.digest(self.config) != self.config_digest
                or any(identity(path) != before for path, before in self.files.items())):
            raise ValueError('Reviewed native scope catalog changed or closed')

    def resolve(self, sid, descriptor):
        self.require_current()
        if sid not in self.sources or (descriptor is not None and descriptor != self.descriptors[sid]):
            raise ValueError('Exact reviewed native scope source required')
        # None permits public contract lookup only. The bridge requires the exact
        # descriptor before native admission or lifecycle construction.
        return dict(**deepcopy(self.sources[sid]), descriptor=deepcopy(self.descriptors[sid]),
                    adapter=self.adapter)

    def close(self):
        self.closed = True


class GPSCatalog(ScopeCatalog):
    KIND = 'gps_document_v190'
    ADAPTER = GPSAdapter


class LayerCatalog(ScopeCatalog):
    KIND = 'public_overlays_v190'
    ADAPTER = LayerAdapter
