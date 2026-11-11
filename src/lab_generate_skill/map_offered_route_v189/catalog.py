"""Current ordinary entry over unchanged route controls and real public inputs."""
from copy import deepcopy
from pathlib import Path
import hashlib, json, os, tempfile
from lab_generate_skill.provider_review_catalog import identity
from lab_generate_skill.map_route_normal_capture import fingerprint
from map_scope_v183.registry import ScopeInputRegistry
from map_scope_v183 import input_check
from map_routes import archival
from map_routes.phase_gate import require_closed_factory

VERSION = 'website-offered-route-catalog-v189'
CHICAGO = '08473184d468a5dd8d4b'


class OfferedRouteCatalog:
    def __init__(self, config, *, project):
        self.config, self.project = deepcopy(config), Path(project).resolve()
        self.files, self.sources, self.descriptors = {}, {}, {}
        self.closed, self.registry, self.temporary = False, None, None
        self.config_sha256 = fingerprint(config)
        try:
            if config.get('version') != VERSION or config.get('source_ids') != [CHICAGO]:
                raise ValueError('Only the independently reviewed Chicago source may be exposed')
            required = {'src/lab_generate_skill/map_offered_route_v189/' + n for n in ('__init__.py', 'catalog.py', 'adapter.py')}
            required.update('scripts/map_scope_v183/' + n for n in config['qualified_scope_modules'])
            required.add('src/lab_generate_skill/reviewed_map_registry.py')
            if not required <= config['integration_files'].keys():
                raise ValueError('Complete current source integration required')
            for name, digest in config['integration_files'].items():
                if Path(name).is_absolute() or '..' in Path(name).parts:
                    raise ValueError('Contained current runtime member required')
                self.read(dict(path=str(self.project / name), sha256=digest), json_value=False)
            for name, ref in config['qualified_scope_modules'].items():
                if self.read(ref, json_value=False) != (self.project / 'scripts/map_scope_v183' / name).read_bytes():
                    raise ValueError('Qualified route scope logic changed during relocation')
            if Path(input_check.__file__).resolve() != self.project / 'scripts/map_scope_v183/input_check.py':
                raise ValueError('Current project must supply the ordinary input reader')
            self.registry = ScopeInputRegistry(self.read(config['input_registry']), project=self.project)
            index, review = self.read(config['new_input_index']), self.read(config['new_input_reader'])
            expected = set(self.registry.config['source_ids'])
            if (not index['passed'] or not index['all_factories_closed'] or index['actor_permission'] is not False
                    or not review['passed'] or not review['review']['passed']
                    or review['review']['index'] != config['new_input_index']
                    or review['review']['actor_permission'] is not False
                    or set(index['sources']) != expected or set(index['factories']) != {'shared'}
                    or set(r['source_task_id'] for r in review['review']['sources']) != expected
                    or any(index[k] != 0 for k in ('actor_calls', 'model_inference_calls', 'training_admissions'))):
                raise ValueError('Complete original native input qualification required')
            if not os.environ.get('SLURM_JOB_ID') or not os.environ.get('TMPDIR'):
                raise ValueError('Native evidence extraction requires allocated scratch')
            self.temporary = tempfile.TemporaryDirectory(prefix='offered-route-catalog-', dir=os.environ['TMPDIR'])
            work = Path(self.temporary.name)
            factory = index['factories']['shared']
            if not factory['closed']:
                raise ValueError('Original ordinary factory is not closed')
            self.read(factory['manifest'])
            self.track(factory['archive'])
            native = work / 'factory'
            archival.unpack_output(factory['archive']['path'], factory['manifest']['path'], native)
            load = lambda path: json.loads(Path(path).read_text())
            fact = load(native / 'factory.json')
            require_closed_factory(native, fact)
            source_binding = load(native / 'scope-binding.json')
            if (not source_binding['closed'] or not source_binding['one_shared_factory']
                    or source_binding['instances_started'] != 1
                    or set(source_binding['source_task_ids']) != expected
                    or source_binding['execution_binding'] != index['execution_binding']
                    or fact['asset_manifest_sha256'] != source_binding['physical_asset']['sha256']
                    or fact['asset_manifest_sha256'] != config['physical_asset_sha256']):
                raise ValueError('Original shared native factory identity differs')
            for sid in config['source_ids']:
                original = self.registry.base.resolve(sid, self.registry.base.descriptors[sid])
                source = self.registry.input_source(sid)
                candidate, part = source['candidate'], index['sources'][sid]
                if not part['passed'] or part['factory_id'] != 'shared':
                    raise ValueError('Actual source input proof missing')
                self.read(part['manifest'])
                self.track(part['archive'])
                where = work / sid
                archival.unpack_output(part['archive']['path'], part['manifest']['path'], where)
                replay = input_check.replay(where, source, execution_binding=index['execution_binding'])
                actual = load(where / 'input-result.json')
                if (not actual['passed'] or replay != actual['raw_replay']
                        or actual['site_origin'] != fact['site_origin'] or actual['route_urls'] != fact['route_urls']
                        or actual['baseline'] != source['baseline']
                        or source_binding['source_bindings'][sid] != source['scope_binding']):
                    raise ValueError('Current ordinary messages or native source binding changed')
                source.update(historical_admission=original['admission'],
                    admission=dict(version='native-website-offered-route-admission-v185', source_task_id=sid,
                        candidate_sha256=fingerprint(candidate), baseline=source['baseline'], passed=True,
                        retained_native_controls_verified=True, new_actual_input_verified=True,
                        first_actor_verified=False, training_admitted=False),
                    current_input_replay=dict(passed=True, source_task_id=sid,
                        candidate_sha256=fingerprint(candidate), raw_messages_exact_under_current_runtime=True,
                        independent_native_input_reader_passed=True, input_index=config['new_input_index'],
                        current_integration_sha256=fingerprint(config['integration_files']),
                        actual_public_input_reconstructed=True))
                self.sources[sid] = source
                self.descriptors[sid] = dict(version=VERSION, source_task_id=sid,
                    candidate_sha256=fingerprint(candidate), configuration_sha256=self.config_sha256,
                    input_index=config['new_input_index'])
            if set(self.sources) != {CHICAGO}:
                raise ValueError('Unreviewable route attempts must not enter this source catalog')
            self.require_current()
        except BaseException:
            self.close()
            raise

    def read(self, ref, *, json_value=True):
        path = Path(ref['path'])
        if not path.is_absolute() or path.is_symlink():
            raise ValueError('Pinned absolute regular evidence required')
        before, raw = identity(path), path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != ref['sha256'] or identity(path) != before:
            raise ValueError('Offered-route evidence or code changed: ' + str(path))
        self.files[path] = before
        return json.loads(raw) if json_value else raw

    def track(self, ref):
        path = Path(ref['path'])
        if not path.is_absolute() or path.is_symlink():
            raise ValueError('Pinned absolute archive required')
        before = identity(path)
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(8 * 1024**2), b''):
                digest.update(block)
        if digest.hexdigest() != ref['sha256'] or identity(path) != before:
            raise ValueError('Original source archive changed')
        self.files[path] = before

    def require_current(self):
        if (self.closed or fingerprint(self.config) != self.config_sha256
                or any(identity(path) != before for path, before in self.files.items())):
            raise ValueError('Offered-route current source changed or closed')
        if self.registry is not None:
            self.registry.require_current()

    def resolve(self, sid, descriptor):
        self.require_current()
        if sid != CHICAGO or self.descriptors.get(sid) != descriptor:
            raise ValueError('Only the exact independently reviewed source descriptor is available')
        return deepcopy(self.sources[sid])

    def close(self):
        if self.registry is not None:
            self.registry.close()
            self.registry = None
        if self.temporary is not None:
            self.temporary.cleanup()
            self.temporary = None
        self.closed = True
