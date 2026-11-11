"""Pinned raw evidence catalog for the two native saved-content sources."""
from pathlib import Path, PurePosixPath
from copy import deepcopy
from io import BytesIO
import hashlib, json, tarfile
from lab_generate_skill.provider_review_catalog import identity
from .adapter import materialize
from .evidence import replay

PACKAGE = 'src/lab_generate_skill/map_saved_content_v187/'
RELOCATED = ('save_judge.py', 'save_capture.py', 'save_protection.py', 'save_snapshot.py', 'save_hooks.py', 'native_snapshot.rb')
CORE = ('map_account_initial', 'map_account_readout', 'map_existing_account_observation',
        'map_existing_account_site', 'map_account_profile', 'map_query_site', 'map_reset_guard',
        'browser_http_status', 'site_worker', 'website_batch_profile', 'native_goal_dispatch',
        'gobrowse_runtime', 'browser_assets', 'actor_protocol', 'runtime_profile',
        'observation_budget', 'public_read_memory')


class SaveCatalog:
    def __init__(self, config, *, project):
        self.config, self.project = deepcopy(config), Path(project)
        self.files, self.sources, self.descriptors = {}, {}, {}
        self.closed = False
        if config.get('version') != 'native-saved-content-catalog-v188':
            raise ValueError('Explicit saved-content catalog required')
        from lab_generate_skill.saved_reader_scope_review import specification, verify
        revision = specification(self, config, 'save')
        contracts, inventory = self.read(config['contracts']), self.read(config['inventory'])
        inventory = {row['task_id']: row for row in inventory}
        baseline = self.read(config['baseline'])
        native_review, ordinary_review = self.read(config['native_review']), self.read(config['ordinary_review'])
        if native_review.get('passed') is not True or ordinary_review.get('passed') is not True or len(native_review['cases']) != 8 or len(ordinary_review['cases']) != 2:
            raise ValueError('Independent native and ordinary reviews required')
        for ref in config['independent_reader_plans']:
            reader = self.read(ref)
            if reader.get('actor_calls') != 0 or reader.get('model_loads') != 0:
                raise ValueError('Qualification reader must not execute models')
        qualified_capsule = self.read(config['ordinary_capsule'])
        for relative in ['scripts/run_site_navigation_once.py'] + ['src/lab_generate_skill/' + n + '.py' for n in CORE]:
            self.read(dict(path=str(self.project / relative), sha256=qualified_capsule['members'][relative]['sha256']), json_value=False)
        required = {PACKAGE + n for n in (*RELOCATED, '__init__.py', 'adapter.py', 'catalog.py', 'evidence.py')}
        required.update({'src/lab_generate_skill/reviewed_protocol_bundle.py', 'src/lab_generate_skill/reviewed_map_registry.py', 'src/lab_generate_skill/saved_reader_scope_review.py'})
        if not required <= config['integration_files'].keys():
            raise ValueError('Complete source integration closure required')
        for relative, digest in config['integration_files'].items():
            if PurePosixPath(relative).is_absolute() or '..' in PurePosixPath(relative).parts:
                raise ValueError('Contained runtime integration member required')
            self.read(dict(path=str(self.project / relative), sha256=digest), json_value=False)
        if set(config['relocations']) != set(RELOCATED):
            raise ValueError('Exact qualified save components required')
        for name, ref in config['relocations'].items():
            original = self.read(ref, json_value=False).decode()
            if name.endswith('.py'):
                for module in ('save_judge', 'save_capture', 'save_snapshot', 'save_protection'):
                    original = original.replace('from ' + module + ' import ', 'from .' + module + ' import ')
            relative = PACKAGE + name
            if relative in revision['qualified_component_revisions']:
                change = revision['qualified_component_revisions'][relative]
                if hashlib.sha256(original.encode()).hexdigest() != change['old_sha256']:
                    raise ValueError('Scope revision belongs to another qualified component')
            elif (self.project / relative).read_text() != original:
                raise ValueError('Qualified component changed beyond package import relocation')
        archives = {}
        expected_codes = dict(upload_retained=2, diary_retained=2, native_final=0, ordinary=0)
        if set(config['batches']) != set(expected_codes):
            raise ValueError('Four original retained/ordinary evidence batches required')
        if (native_review['retained_upload_archive'] != config['batches']['upload_retained']['archive']
                or native_review['retained_diary_archive'] != config['batches']['diary_retained']['archive']
                or ordinary_review['native_control_qualification'] != config['native_review']):
            raise ValueError('Retained native evidence chain differs')
        for name, spec in config['batches'].items():
            plan = self.read(spec['plan'])
            completed, termination = self.read(spec['completed']), self.read(spec['termination'])
            if completed['returncode'] != expected_codes[name] or termination['returncode'] != expected_codes[name] or not termination['confirmed'] or termination['group'].get('live_members') or termination['scope']['live_scratch_references'] or termination['scope']['unreadable_same_uid_pids']:
                raise ValueError('Original native writer is not closed')
            if name == 'ordinary' and plan['capsule'] != config['ordinary_capsule']:
                raise ValueError('Ordinary qualification used another runtime capsule')
            if name == 'native_final' and (native_review['archive'] != spec['archive'] or native_review['plan'] != spec['plan']):
                raise ValueError('Native independent review belongs to another batch')
            if name == 'ordinary' and (ordinary_review['archive'] != spec['archive'] or ordinary_review['plan'] != spec['plan']):
                raise ValueError('Ordinary independent review belongs to another batch')
            index, raw = self.read(spec['index']), self.read(spec['archive'], json_value=False)
            if index['archive_sha256'] != spec['archive']['sha256']:
                raise ValueError('Sealed archive index differs')
            data, size = {}, 0
            with tarfile.open(fileobj=BytesIO(raw)) as archive:
                for member in archive:
                    path = PurePosixPath(member.name)
                    size += member.size
                    if not member.isfile() or path.is_absolute() or '..' in path.parts or member.name in data or member.name not in index['members'] or member.size > 128 * 1024**2 or size > 2 * 1024**3:
                        raise ValueError('Unexpected raw evidence member')
                    value = archive.extractfile(member).read()
                    if index['members'][member.name] != dict(bytes=len(value), sha256=hashlib.sha256(value).hexdigest()):
                        raise ValueError('Raw evidence member changed')
                    data[member.name] = value
            if set(data) != set(index['members']):
                raise ValueError('Incomplete raw evidence archive')
            archives[name] = data
        replayed = replay(contracts, archives, baseline, native_review, ordinary_review,
                          config['relocations']['native_snapshot.rb']['sha256'])
        self.scope_scores = verify(self, revision, contracts, baseline)
        for kind, control in contracts.items():
            sid = control['source_task_id']
            for key in ('original_initial_frame',):
                self.read(control[key], json_value=False)
            self.read(control['task_revision']['scope_plan'], json_value=False)
            if kind == 'upload':
                self.read(control['parameters']['public_file'], json_value=False)
            candidate = materialize(control, inventory[sid])
            admission = dict(version='native-saved-content-admission-v188', source_task_id=sid,
                passed=replayed['passed'], native_controls_verified=True, ordinary_lifecycle_verified=True,
                full_cold_reset_verified=True, actual_public_input_verified=True, actor_executed=False, scope_revision_verified=True)
            self.sources[sid] = dict(candidate=candidate, control_contract=control, baseline=baseline, admission=admission)
            self.descriptors[sid] = dict(version='native-saved-content-source-v188', source_task_id=sid,
                contract_sha256=hashlib.sha256(json.dumps(candidate, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
                native_review_sha256=config['native_review']['sha256'], ordinary_review_sha256=config['ordinary_review']['sha256'], scope_revision_sha256=config['scope_revision']['sha256'])
        if len(self.sources) != 2:
            raise ValueError('Exactly two independently qualified save sources required')
        self.require_current()

    def read(self, ref, *, json_value=True):
        path = Path(ref['path'])
        if not path.is_absolute():
            raise ValueError('Absolute pinned evidence path required')
        before, raw = identity(path), path.read_bytes()
        actual = hashlib.sha256(raw).hexdigest()
        if actual != ref['sha256']:
            from lab_generate_skill.reviewed_code_evolution import accepts
            if not accepts(self, ref, path, actual, json_value=json_value):
                raise ValueError('Pinned saved-content evidence changed: ' + str(path))
        if identity(path) != before:
            raise ValueError('Saved-content evidence changed during read')
        self.files[path] = before
        return json.loads(raw) if json_value else raw

    def require_current(self):
        if self.closed or any(identity(path) != previous for path, previous in self.files.items()):
            raise ValueError('Saved-content evidence changed or closed')

    def resolve(self, source_id, descriptor):
        self.require_current()
        if self.descriptors.get(source_id) != descriptor:
            raise ValueError('Exact saved-content source descriptor required')
        from lab_generate_skill.reviewed_code_evolution import require_source
        require_source(self, source_id)
        return deepcopy(self.sources[source_id])

    def close(self):
        self.closed = True
