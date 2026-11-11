"""Reuse pinned, independently reviewed provider evidence in a frozen worker.

This is not a new native validator. CPU preparation pins already reviewed
environment and ordinary-lifecycle records. Runtime checks the same reviews,
task definitions and relevant code once, then guards their file identities.
No website state or previous actor result is cached.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import stat

from .source_revision_binding import binding

DEPENDENCIES = ('site_worker', 'map_query_site', 'map_reset_guard',
                'map_provider_environment', 'map_provider_observation',
                'map_provider_terminal', 'map_frozen_provider_runtime',
                'map_provider_controls')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def identity(path):
    s = path.lstat()
    if not stat.S_ISREG(s.st_mode):
        raise ValueError('Pinned regular provider evidence required')
    return s.st_dev, s.st_ino, s.st_size, s.st_mode, s.st_mtime_ns, s.st_ctime_ns


class ProviderReviewCatalog:
    def __init__(self, config, *, project):
        self.closed = False
        self.files = {}
        self.sources = {}
        self.descriptors = {}
        self.config = deepcopy(config)
        values = {key: self.read(config[key]) for key in (
            'profile', 'contracts', 'environment_review', 'normal_review',
            'normal_plan', 'normal_runtime_members')}
        profile, environment, normal = (values[k] for k in
                                       ('profile', 'environment_review', 'normal_review'))
        if (profile.get('version') != 'map-frozen-provider-environment-v1'
                or profile.get('runtime_external_requests') is not False
                or profile.get('original_snapshot_equivalence') is not False
                or profile['contracts'] != config['contracts']
                or environment.get('passed') is not True or normal.get('passed') is not True
                or normal.get('plan_sha256') != config['normal_plan']['sha256']
                or values['normal_plan']['files']['runtime-members.json'] != config['normal_runtime_members']['sha256']
                or values['normal_plan']['external_pins'].get(config['environment_review']['path'])
                   != config['environment_review']['sha256']
                or values['normal_plan']['external_pins'].get(config['profile']['path'])
                   != config['profile']['sha256']):
            raise ValueError('Original reviewed provider chain changed')
        # Resources are verified by the environment installer before any page is
        # exposed. Guard the same manifest now; never substitute live downloads.
        self.read(profile['resources'])
        cycles = environment['cycles']
        if (len(cycles) != 2 or cycles[0]['factory_id'] == cycles[1]['factory_id']
                or cycles[0]['initial_fingerprint'] != cycles[1]['initial_fingerprint']):
            raise ValueError('Two distinct verified cold baselines required')
        self.baseline = cycles[0]['initial_fingerprint']
        self.environment_binding = dict(version=profile['version'],
            manifest_sha256=config['profile']['sha256'],
            resources_sha256=profile['resources']['sha256'],
            contracts_sha256=config['contracts']['sha256'])
        candidates = values['contracts']['tasks']
        ids = [c['source_task_id'] for c in candidates]
        if (not ids or len(set(ids)) != len(ids)
                or set(ids) != {r['source_task_id'] for r in environment['sources']}
                or set(ids) != {r['source_task_id'] for r in normal['sources']}):
            raise ValueError('Reviewed provider source coverage changed')
        for name in DEPENDENCIES:
            relative = 'src/lab_generate_skill/' + name + '.py'
            self.read(dict(path=str(Path(project) / relative),
                           sha256=values['normal_runtime_members'][relative]['sha256']), json_value=False)
        for c in candidates:
            sid = c['source_task_id']
            binding(c)
            if c.get('split') != 'train' or c['candidate_completion'].get('family') != 'base_layer':
                raise ValueError('Declared training provider task required')
            row = next(r for r in normal['sources'] if r['source_task_id'] == sid)
            cold = next(r for r in environment['sources'] if r['source_task_id'] == sid)
            if (row.get('passed') is not True or cold.get('full_worker_two_cold_verified') is not True
                    or row['controls']['noop']['status'] != 'failure'
                    or row['controls']['positive']['status'] != 'success'
                    or any(sid not in {r['source_task_id'] for r in cy['sources']} for cy in cycles)):
                raise ValueError('Incomplete original provider control review')
            descriptor = dict(version='reviewed-provider-source-v1', source_task_id=sid,
                candidate_sha256=digest(json.dumps(c, sort_keys=True, separators=(',', ':')).encode()),
                normal_review_sha256=config['normal_review']['sha256'],
                environment_review_sha256=config['environment_review']['sha256'],
                profile_sha256=config['profile']['sha256'])
            admission = dict(version='native-provider-normal-admission-v1',passed=True,
                two_cold_environment_verified=True,ordinary_lifecycle_verified=True,
                source_task_id=sid,environment_binding=self.environment_binding,baseline=self.baseline,
                verified_review_reused=True)
            self.sources[sid] = dict(candidate=deepcopy(c),admission=admission,
                                    environment_binding=self.environment_binding,baseline=self.baseline)
            self.descriptors[sid] = descriptor
        self.require_current()

    def read(self, record, *, json_value=True):
        from .reviewed_evidence_snapshot import evidence_path
        path = evidence_path(self, record)
        if not path.is_absolute():
            raise ValueError('Absolute frozen evidence path required')
        before = identity(path)
        raw = path.read_bytes()
        actual = digest(raw)
        if actual != record['sha256']:
            from .reviewed_code_evolution import accepts
            if not accepts(self, record, path, actual, json_value=json_value):
                raise ValueError('Provider evidence or code changed: ' + str(path))
        if identity(path) != before:
            raise ValueError('Provider evidence changed during read: ' + str(path))
        self.files[path] = before
        return json.loads(raw) if json_value else raw

    def require_current(self):
        if self.closed:
            raise ValueError('Provider proof registry is closed')
        if any(identity(p) != expected for p, expected in self.files.items()):
            raise ValueError('Verified provider evidence changed during worker lifetime')

    def resolve(self, sid, descriptor):
        self.require_current()
        if sid not in self.sources or descriptor != self.descriptors[sid]:
            raise ValueError('Exact original provider descriptor required')
        from .reviewed_code_evolution import require_source
        require_source(self, sid)
        return deepcopy(self.sources[sid])

    def close(self):
        self.closed = True
        self.sources.clear()
